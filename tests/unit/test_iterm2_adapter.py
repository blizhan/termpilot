from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from termpilot.adapters.iterm2 import Iterm2Adapter, readiness_from_prompt
from termpilot.errors import (
    ErrorCode,
    Iterm2UnavailableError,
    OutputUnavailableError,
    SessionNotFoundError,
    SessionNotReadyError,
    ShellIntegrationRequiredError,
)
from termpilot.models import (
    CommandRequest,
    CommandStatus,
    ExecutionReadiness,
)


class FakeTransaction:
    def __init__(self, _connection) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None


@dataclass
class FakePrompt:
    state: object
    unique_id: str = "prompt-1"
    command_range: object | None = None
    output_range: object | None = None


class FakePromptMonitor:
    active = False

    class Mode:
        COMMAND_END = "command_end"

    def __init__(self, _connection, _session_id, _modes=None) -> None:
        self.events = [(self.Mode.COMMAND_END, 7)]

    async def __aenter__(self):
        type(self).active = True
        return self

    async def __aexit__(self, *_args) -> None:
        type(self).active = False
        return None

    async def async_get(self, include_id=False):
        event = self.events.pop(0)
        return (*event, "prompt-event") if include_id else event


class FakeIterm2:
    class PromptState:
        EDITING = "editing"
        RUNNING = "running"
        FINISHED = "finished"
        UNKNOWN = "unknown"

    Transaction = FakeTransaction
    PromptMonitor = FakePromptMonitor

    def __init__(self, prompts: dict[str, FakePrompt] | None = None) -> None:
        self.prompts = prompts or {}

    async def async_get_last_prompt(self, _connection, session_id: str):
        return self.prompts.get(session_id)

    async def async_get_prompt_by_id(self, _connection, session_id: str, prompt_id: str):
        if prompt_id != "prompt-event":
            return None
        return self.prompts.get(f"{session_id}:final")


class FakeLine:
    def __init__(self, text: str, hard_eol: bool = True) -> None:
        self.string = text
        self.hard_eol = hard_eol

    def string_at(self, x: int) -> str:
        return self.string[x]


class FakeScreen:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self.number_of_lines = len(lines)

    def line(self, index: int) -> FakeLine:
        return FakeLine(self._lines[index])


class FakeSession:
    def __init__(self, session_id: str, *, variables=None, screen=None) -> None:
        self.session_id = session_id
        self.name = "profile-name"
        self.variables = variables or {}
        self.screen = screen or FakeScreen([])
        self.sent: list[tuple[str, bool]] = []
        self.sent_while_monitor_active: list[bool] = []
        self.tab = None

    async def async_get_variable(self, name: str):
        return self.variables.get(name, "")

    async def async_get_screen_contents(self):
        return self.screen

    async def async_get_contents(self, _first_line: int, _number_of_lines: int):
        return [FakeLine("hello")]

    async def async_send_text(self, text: str, suppress_broadcast: bool = False):
        self.sent.append((text, suppress_broadcast))
        self.sent_while_monitor_active.append(FakePromptMonitor.active)


class FakeTab:
    def __init__(self, tab_id: str, sessions: list[FakeSession], *, title="tab-title") -> None:
        self.tab_id = tab_id
        self.sessions = sessions
        self.all_sessions = sessions
        self.current_session = sessions[0] if sessions else None
        self.title = title
        self.window = None
        for session in sessions:
            session.tab = self

    async def async_get_variable(self, name: str):
        return self.title if name == "title" else ""


class FakeWindow:
    def __init__(
        self, window_id: str, tabs: list[FakeTab], *, number=1, title="window-title"
    ) -> None:
        self.window_id = window_id
        self.tabs = tabs
        self.window_number = number
        self.title = title
        self.current_tab = tabs[0] if tabs else None
        for tab in tabs:
            tab.window = self

    async def async_get_variable(self, name: str):
        return self.title if name == "titleOverride" else ""


class FakeApp:
    def __init__(self, windows: list[FakeWindow]) -> None:
        self.terminal_windows = windows
        self.windows = windows
        self.buried_sessions = []
        self.current_terminal_window = windows[0] if windows else None

    def get_session_by_id(self, session_id: str, include_buried=True):
        del include_buried
        for window in self.windows:
            for tab in window.tabs:
                for session in tab.all_sessions:
                    if session.session_id == session_id:
                        return session
        return None


@pytest.fixture
def fake_environment():
    session = FakeSession(
        "session-1",
        variables={
            "name": "ssh example-host",
            "hostname": "example-host",
            "username": "example-user",
            "path": "/home/example",
            "tty": "/dev/ttys003",
        },
        screen=FakeScreen(["$ printf hello", "hello", "$ "]),
    )
    tab = FakeTab("tab-1", [session])
    window = FakeWindow("window-1", [tab])
    app = FakeApp([window])
    empty_command_range = SimpleNamespace(
        start=SimpleNamespace(x=0, y=2),
        end=SimpleNamespace(x=0, y=2),
    )
    prompt = FakePrompt(
        FakeIterm2.PromptState.EDITING,
        command_range=empty_command_range,
    )
    final_prompt = FakePrompt(
        FakeIterm2.PromptState.EDITING,
        unique_id="prompt-2",
        command_range=empty_command_range,
        output_range=SimpleNamespace(
            start=SimpleNamespace(x=0, y=1),
            end=SimpleNamespace(x=0, y=2),
        ),
    )
    module = FakeIterm2({"session-1": prompt, "session-1:final": final_prompt})
    return session, app, module


def test_readiness_from_prompt_only_allows_editing_prompt() -> None:
    assert (
        readiness_from_prompt(FakePrompt(FakeIterm2.PromptState.EDITING), FakeIterm2)
        is ExecutionReadiness.READY
    )
    assert (
        readiness_from_prompt(FakePrompt(FakeIterm2.PromptState.RUNNING), FakeIterm2)
        is ExecutionReadiness.BUSY
    )
    assert readiness_from_prompt(None, FakeIterm2) is ExecutionReadiness.SHELL_INTEGRATION_REQUIRED


@pytest.mark.asyncio
async def test_list_sessions_returns_identity_and_shell_metadata(fake_environment) -> None:
    session, app, module = fake_environment
    adapter = Iterm2Adapter(connection=object(), app=app, iterm2_module=module)

    sessions = await adapter.list_sessions()

    assert [item.session_id for item in sessions] == ["session-1"]
    assert sessions[0].is_current is True
    assert sessions[0].hostname == "example-host"
    assert sessions[0].cwd == "/home/example"
    assert sessions[0].tty == "/dev/ttys003"
    assert sessions[0].execution_readiness is ExecutionReadiness.READY
    assert session.sent == []


@pytest.mark.asyncio
async def test_adapter_lazily_connects_to_iterm2_and_loads_the_app(fake_environment) -> None:
    _session, app, module = fake_environment
    created_connections = []

    class Connection:
        @staticmethod
        async def async_create():
            connection = object()
            created_connections.append(connection)
            return connection

    async def async_get_app(connection, create_if_needed=True):
        assert connection is created_connections[0]
        assert create_if_needed is True
        return app

    module.Connection = Connection
    module.async_get_app = async_get_app
    adapter = Iterm2Adapter(iterm2_module=module)

    current = await adapter.get_current_session()

    assert current is not None
    assert current.session_id == "session-1"
    assert len(created_connections) == 1


@pytest.mark.asyncio
async def test_adapter_bounds_connection_attempts(monkeypatch) -> None:
    class SlowConnection:
        @staticmethod
        async def async_create():
            await asyncio.sleep(1)

    module = SimpleNamespace(Connection=SlowConnection)
    monkeypatch.setattr("termpilot.adapters.iterm2.ITERM2_CONNECT_TIMEOUT_SECONDS", 0.001)
    adapter = Iterm2Adapter(iterm2_module=module)

    with pytest.raises(Iterm2UnavailableError):
        await asyncio.wait_for(adapter.list_sessions(), timeout=0.05)


@pytest.mark.asyncio
async def test_read_terminal_bounds_content_and_reports_truncation(fake_environment) -> None:
    _session, app, module = fake_environment
    adapter = Iterm2Adapter(connection=object(), app=app, iterm2_module=module)

    snapshot = await adapter.read_terminal("session-1", max_lines=2, max_chars=5)

    assert snapshot.session_id == "session-1"
    assert snapshot.content == "o\n$ \n"
    assert snapshot.truncated is True
    assert snapshot.line_count == 2


@pytest.mark.asyncio
async def test_run_command_sends_only_to_exact_session_and_correlates_result(
    fake_environment,
) -> None:
    session, app, module = fake_environment
    adapter = Iterm2Adapter(connection=object(), app=app, iterm2_module=module)
    request = CommandRequest(session_id="session-1", command="printf hello")

    result = await adapter.run_command(request)

    assert result.status is CommandStatus.COMPLETED
    assert result.session_id == "session-1"
    assert result.exit_code == 7
    assert result.output == "hello\n"
    assert session.sent == [("printf hello\r", True)]
    assert session.sent_while_monitor_active == [True]


@pytest.mark.asyncio
async def test_run_command_rejects_missing_or_busy_session_without_sending(
    fake_environment,
) -> None:
    session, app, module = fake_environment
    adapter = Iterm2Adapter(connection=object(), app=app, iterm2_module=module)
    request = CommandRequest(session_id="session-1", command="printf hello")

    with pytest.raises(SessionNotFoundError) as missing:
        await adapter.run_command(request.__class__(session_id="gone", command="printf hello"))
    assert missing.value.code is ErrorCode.SESSION_NOT_FOUND

    module.prompts["session-1"].state = FakeIterm2.PromptState.RUNNING
    with pytest.raises(SessionNotReadyError):
        await adapter.run_command(request)
    assert session.sent == []


@pytest.mark.asyncio
async def test_run_command_rejects_editing_prompt_with_pending_input(fake_environment) -> None:
    session, app, module = fake_environment
    module.prompts["session-1"].command_range = SimpleNamespace(
        start=SimpleNamespace(x=0, y=2),
        end=SimpleNamespace(x=7, y=2),
    )
    adapter = Iterm2Adapter(connection=object(), app=app, iterm2_module=module)
    request = CommandRequest(session_id="session-1", command="printf hello")

    with pytest.raises(SessionNotReadyError):
        await adapter.run_command(request)

    assert session.sent == []


@pytest.mark.asyncio
async def test_run_command_does_not_send_when_completion_monitor_is_unavailable(fake_environment):
    session, app, module = fake_environment
    module.PromptMonitor = None
    adapter = Iterm2Adapter(connection=object(), app=app, iterm2_module=module)
    request = CommandRequest(session_id="session-1", command="printf hello")

    with pytest.raises(ShellIntegrationRequiredError):
        await adapter.run_command(request)

    assert session.sent == []


@pytest.mark.asyncio
async def test_run_command_without_wait_returns_submitted(fake_environment) -> None:
    session, app, module = fake_environment
    adapter = Iterm2Adapter(connection=object(), app=app, iterm2_module=module)
    request = CommandRequest(
        session_id="session-1", command="printf hello", wait_for_completion=False
    )

    result = await adapter.run_command(request)

    assert result.status is CommandStatus.SUBMITTED
    assert result.output is None
    assert session.sent == [("printf hello\r", True)]


@pytest.mark.asyncio
async def test_run_command_captures_same_line_output_range(fake_environment) -> None:
    session, app, module = fake_environment
    module.prompts["session-1:final"].output_range = SimpleNamespace(
        start=SimpleNamespace(x=3, y=4),
        end=SimpleNamespace(x=8, y=4),
    )
    reads: list[tuple[int, int]] = []

    async def async_get_contents(first_line: int, number_of_lines: int):
        reads.append((first_line, number_of_lines))
        if number_of_lines == 0:
            return []
        return [FakeLine("xxxhelloz", hard_eol=False)]

    session.async_get_contents = async_get_contents
    adapter = Iterm2Adapter(connection=object(), app=app, iterm2_module=module)
    request = CommandRequest(session_id="session-1", command="printf hello")

    result = await adapter.run_command(request)

    assert result.status is CommandStatus.COMPLETED
    assert result.output == "hello"
    assert reads == [(4, 1)]


def test_output_range_is_required_for_completed_output() -> None:
    assert OutputUnavailableError().code is ErrorCode.OUTPUT_UNAVAILABLE
