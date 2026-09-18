from __future__ import annotations

from datetime import UTC, datetime

import pytest
from mcp import Client

from termpilot.mcp_server import create_server
from termpilot.models import (
    CommandResult,
    CommandStatus,
    ExecutionReadiness,
    TerminalSession,
    TerminalSnapshot,
)


class FakeMcpBackend:
    def __init__(self, *, current: TerminalSession | None = None) -> None:
        self.session = TerminalSession(
            session_id="session-1",
            tab_title="example-host",
            hostname="example-host",
            cwd="/home/example",
            is_current=current is not None,
            execution_readiness=ExecutionReadiness.READY,
        )
        self.current = current or self.session
        self.commands: list[str] = []

    async def list_sessions(self) -> list[TerminalSession]:
        return [self.session]

    async def get_current_session(self) -> TerminalSession | None:
        return self.current

    async def get_session(self, session_id: str) -> TerminalSession | None:
        return self.session if session_id == self.session.session_id else None

    async def read_terminal(
        self, session_id: str, *, max_lines: int, max_chars: int
    ) -> TerminalSnapshot:
        return TerminalSnapshot(
            session_id=session_id,
            content="visible output\n",
            line_count=1,
            execution_readiness=ExecutionReadiness.READY,
            captured_at=datetime.now(UTC),
        )

    async def run_command(self, request) -> CommandResult:
        self.commands.append(request.command)
        return CommandResult(
            request_id=request.request_id,
            session_id=request.session_id,
            command=request.command,
            status=CommandStatus.COMPLETED,
            exit_code=0,
            output="command output\n",
        )


@pytest.mark.asyncio
async def test_mcp_server_exposes_the_four_contract_tools() -> None:
    backend = FakeMcpBackend()
    server = create_server(backend)

    async with Client(server) as client:
        result = await client.list_tools()

    assert {tool.name for tool in result.tools} == {
        "list_sessions",
        "get_current_session",
        "read_terminal",
        "run_command",
    }
    annotations = {tool.name: tool.annotations for tool in result.tools}
    assert annotations["run_command"].read_only_hint is False
    assert annotations["run_command"].destructive_hint is True
    assert annotations["read_terminal"].read_only_hint is True


@pytest.mark.asyncio
async def test_read_tools_return_structured_data_and_write_tool_correlates_result() -> None:
    backend = FakeMcpBackend()
    server = create_server(backend)

    async with Client(server) as client:
        current = await client.call_tool("get_current_session", {})
        snapshot = await client.call_tool("read_terminal", {"session_id": "session-1"})
        command = await client.call_tool(
            "run_command",
            {"session_id": "session-1", "command": "printf ok"},
        )

    assert current.is_error is False
    assert current.structured_content["session_id"] == "session-1"
    assert snapshot.structured_content["content"] == "visible output\n"
    assert command.structured_content["status"] == "completed"
    assert command.structured_content["session_id"] == "session-1"
    assert backend.commands == ["printf ok"]


@pytest.mark.asyncio
async def test_observed_terminal_content_never_becomes_an_implicit_command() -> None:
    backend = FakeMcpBackend()
    server = create_server(backend)

    async with Client(server) as client:
        result = await client.call_tool("read_terminal", {"session_id": "session-1"})

    assert "command output" not in result.structured_content["content"]
    assert backend.commands == []


@pytest.mark.asyncio
async def test_missing_current_session_is_a_machine_readable_mcp_error() -> None:
    backend = FakeMcpBackend(current=None)
    backend.current = None
    server = create_server(backend)

    async with Client(server) as client:
        result = await client.call_tool("get_current_session", {})

    assert result.is_error is True
    assert result.structured_content == {
        "error_code": "no_current_session",
        "message": "iTerm2 has no current terminal session.",
    }


@pytest.mark.asyncio
async def test_invalid_read_bounds_are_machine_readable_mcp_errors() -> None:
    server = create_server(FakeMcpBackend())

    async with Client(server) as client:
        result = await client.call_tool(
            "read_terminal", {"session_id": "session-1", "max_lines": 0}
        )

    assert result.is_error is True
    assert result.structured_content["error_code"] == "invalid_request"
