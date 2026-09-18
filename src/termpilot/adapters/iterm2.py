"""Adapter for the iTerm2 Python scripting API.

All iTerm2-specific objects stay in this module. The service layer only sees
the transport-independent models and domain errors.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from termpilot.errors import (
    ErrorCode,
    Iterm2UnavailableError,
    OutputUnavailableError,
    SessionNotFoundError,
    SessionNotReadyError,
    ShellIntegrationRequiredError,
    TermPilotError,
)
from termpilot.models import (
    MAX_COMMAND_TIMEOUT_SECONDS,
    MAX_LINES,
    MAX_OUTPUT_CHARS,
    Availability,
    CommandRequest,
    CommandResult,
    CommandStatus,
    ExecutionReadiness,
    TerminalSession,
    TerminalSnapshot,
)

try:  # pragma: no cover - the import branch depends on the host environment.
    import iterm2 as _default_iterm2
except ImportError:  # pragma: no cover - exercised by packaging on non-macOS hosts.
    _default_iterm2 = None


LOGGER = logging.getLogger(__name__)
ITERM2_CONNECT_TIMEOUT_SECONDS = 5.0


def _state_name(state: Any) -> str:
    name = getattr(state, "name", None)
    if name:
        return str(name).lower()
    return str(state).rsplit(".", 1)[-1].lower()


def readiness_from_prompt(prompt: Any, iterm2_module: Any) -> ExecutionReadiness:
    """Translate iTerm2 prompt state into TermPilot's fail-closed states."""

    if prompt is None:
        return ExecutionReadiness.SHELL_INTEGRATION_REQUIRED

    state = getattr(prompt, "state", None)
    prompt_state = getattr(iterm2_module, "PromptState", None)
    editing = getattr(prompt_state, "EDITING", object())
    running = getattr(prompt_state, "RUNNING", object())
    finished = getattr(prompt_state, "FINISHED", object())
    unknown = getattr(prompt_state, "UNKNOWN", object())

    if state == editing or _state_name(state) == "editing":
        return ExecutionReadiness.READY
    if state == running or _state_name(state) == "running":
        return ExecutionReadiness.BUSY
    if state == finished or _state_name(state) == "finished":
        return ExecutionReadiness.BUSY
    if state == unknown or _state_name(state) == "unknown":
        return ExecutionReadiness.UNKNOWN
    return ExecutionReadiness.UNKNOWN


def _value_as_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _line_text(lines: Iterable[Any]) -> str:
    result: list[str] = []
    for line in lines:
        result.append(str(getattr(line, "string", line)))
        if getattr(line, "hard_eol", False):
            result.append("\n")
    return "".join(result)


def _point_xy(point: Any) -> tuple[int, int] | None:
    x = getattr(point, "x", None)
    y = getattr(point, "y", None)
    if not isinstance(x, int) or isinstance(x, bool):
        return None
    if not isinstance(y, int) or isinstance(y, bool):
        return None
    return x, y


def _prompt_command_buffer_is_empty(prompt: Any) -> bool:
    command_range = getattr(prompt, "command_range", None)
    start = _point_xy(getattr(command_range, "start", None))
    end = _point_xy(getattr(command_range, "end", None))
    return start is not None and start == end


def _line_cell_text(line: Any, start: int, end: int | None = None) -> str:
    string_at = getattr(line, "string_at", None)
    if string_at is None:
        return str(getattr(line, "string", line))[start:end]

    result: list[str] = []
    x = start
    while end is None or x < end:
        try:
            result.append(str(string_at(x)))
        except IndexError:
            break
        x += 1
    return "".join(result)


def _coord_range_text(
    lines: Iterable[Any],
    *,
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
) -> str:
    result: list[str] = []
    for offset, line in enumerate(lines):
        y = start_y + offset
        line_start = start_x if y == start_y else 0
        line_end = end_x if y == end_y else None
        result.append(_line_cell_text(line, line_start, line_end))
        if y < end_y and getattr(line, "hard_eol", False):
            result.append("\n")
    return "".join(result)


def _bound_text(text: str, max_lines: int, max_chars: int) -> tuple[str, int, bool]:
    lines = text.splitlines(keepends=True)
    line_limited = len(lines) > max_lines
    if line_limited:
        text = "".join(lines[-max_lines:])
    char_limited = len(text) > max_chars
    if char_limited:
        text = text[-max_chars:]
    line_count = len(text.splitlines()) if text else 0
    return text, line_count, line_limited or char_limited


def _validate_read_bounds(max_lines: int, max_chars: int) -> None:
    if (
        isinstance(max_lines, bool)
        or not isinstance(max_lines, int)
        or not 0 < max_lines <= MAX_LINES
    ):
        raise ValueError(f"max_lines must be an integer between 1 and {MAX_LINES}")
    if (
        isinstance(max_chars, bool)
        or not isinstance(max_chars, int)
        or not 0 < max_chars <= MAX_OUTPUT_CHARS
    ):
        raise ValueError(f"max_chars must be an integer between 1 and {MAX_OUTPUT_CHARS}")


def _validate_timeout(timeout_seconds: float) -> None:
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool):
        raise ValueError("timeout_seconds must be a number")
    if not 0 < timeout_seconds <= MAX_COMMAND_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout_seconds must be greater than 0 and at most {MAX_COMMAND_TIMEOUT_SECONDS}"
        )


class Iterm2Adapter:
    """Async access to currently open iTerm2 sessions."""

    def __init__(
        self,
        *,
        connection: Any | None = None,
        app: Any | None = None,
        iterm2_module: Any | None = None,
    ) -> None:
        self._connection = connection
        self._app = app
        self._iterm2 = _default_iterm2 if iterm2_module is None else iterm2_module

    async def _ensure_connected(self) -> Any:
        if self._app is not None:
            return self._app
        if self._iterm2 is None:
            raise Iterm2UnavailableError()
        try:
            if self._connection is None:
                connection_type = getattr(self._iterm2, "Connection", None)
                if connection_type is None:
                    raise Iterm2UnavailableError("The iTerm2 Python API has no Connection type.")
                self._connection = await asyncio.wait_for(
                    connection_type.async_create(), timeout=ITERM2_CONNECT_TIMEOUT_SECONDS
                )
            get_app = getattr(self._iterm2, "async_get_app", None)
            if get_app is None:
                raise Iterm2UnavailableError("The iTerm2 Python API has no async_get_app function.")
            self._app = await asyncio.wait_for(
                get_app(self._connection, create_if_needed=True),
                timeout=ITERM2_CONNECT_TIMEOUT_SECONDS,
            )
        except TermPilotError:
            raise
        except Exception as exc:  # The API exposes several version-specific exception classes.
            LOGGER.debug("Unable to connect to iTerm2", exc_info=True)
            raise Iterm2UnavailableError(
                str(exc) or "Timed out while connecting to the iTerm2 Python API."
            ) from exc
        if self._app is None:
            raise Iterm2UnavailableError("iTerm2 is not running or its Python API is disabled.")
        return self._app

    async def _get_variable(self, obj: Any, name: str) -> Any:
        getter = getattr(obj, "async_get_variable", None)
        if getter is None:
            return None
        try:
            return await getter(name)
        # Metadata is optional; a single missing variable must not hide a session.
        except Exception:
            LOGGER.debug("Unable to read iTerm2 variable %s", name, exc_info=True)
            return None

    async def _first_variable(self, obj: Any, names: Iterable[str]) -> str | None:
        if obj is None:
            return None
        for name in names:
            value = _value_as_text(await self._get_variable(obj, name))
            if value is not None:
                return value
        return None

    def _current_raw_session(self, app: Any) -> Any | None:
        window = getattr(app, "current_terminal_window", None)
        if window is None:
            window = getattr(app, "current_window", None)
        tab = getattr(window, "current_tab", None) if window is not None else None
        return getattr(tab, "current_session", None) if tab is not None else None

    def _iter_raw_sessions(self, app: Any) -> Iterable[Any]:
        seen: set[str] = set()
        windows = getattr(app, "terminal_windows", None)
        if windows is None:
            windows = getattr(app, "windows", ())
        for window in windows or ():
            for tab in getattr(window, "tabs", ()) or ():
                sessions = getattr(tab, "all_sessions", None)
                if sessions is None:
                    sessions = getattr(tab, "sessions", ())
                for session in sessions or ():
                    session_id = getattr(session, "session_id", None)
                    if session_id and session_id not in seen:
                        seen.add(session_id)
                        yield session
        for session in getattr(app, "buried_sessions", ()) or ():
            session_id = getattr(session, "session_id", None)
            if session_id and session_id not in seen:
                seen.add(session_id)
                yield session

    def _find_raw_session(self, app: Any, session_id: str) -> Any | None:
        getter = getattr(app, "get_session_by_id", None)
        if getter is not None:
            try:
                session = getter(session_id, include_buried=True)
            except TypeError:
                session = getter(session_id)
            if session is not None:
                return session
        return next(
            (
                session
                for session in self._iter_raw_sessions(app)
                if session.session_id == session_id
            ),
            None,
        )

    async def _readiness(self, session_id: str) -> ExecutionReadiness:
        getter = getattr(self._iterm2, "async_get_last_prompt", None)
        if getter is None or self._connection is None:
            return ExecutionReadiness.SHELL_INTEGRATION_REQUIRED
        try:
            prompt = await getter(self._connection, session_id)
        except Exception:
            LOGGER.debug("Unable to read the latest prompt for %s", session_id, exc_info=True)
            return ExecutionReadiness.SHELL_INTEGRATION_REQUIRED
        return readiness_from_prompt(prompt, self._iterm2)

    async def _to_session(self, session: Any, *, is_current: bool) -> TerminalSession:
        tab = getattr(session, "tab", None)
        window = getattr(tab, "window", None)
        session_name = await self._first_variable(session, ("name", "presentationName"))
        if session_name is None:
            session_name = _value_as_text(getattr(session, "name", None))
        tab_title = await self._first_variable(tab, ("title", "titleOverride"))
        window_title = await self._first_variable(window, ("titleOverride", "title"))
        window_number = getattr(window, "window_number", None)
        readiness = await self._readiness(session.session_id)
        return TerminalSession(
            session_id=session.session_id,
            window_id=_value_as_text(getattr(window, "window_id", None)),
            tab_id=_value_as_text(getattr(tab, "tab_id", None)),
            window_title=window_title,
            tab_title=tab_title,
            session_title=session_name,
            hostname=_value_as_text(await self._get_variable(session, "hostname")),
            username=_value_as_text(await self._get_variable(session, "username")),
            cwd=_value_as_text(await self._get_variable(session, "path")),
            tty=_value_as_text(await self._get_variable(session, "tty")),
            window_number=window_number if isinstance(window_number, int) else None,
            is_current=is_current,
            availability=Availability.AVAILABLE,
            execution_readiness=readiness,
        )

    async def list_sessions(self) -> list[TerminalSession]:
        app = await self._ensure_connected()
        current = self._current_raw_session(app)
        current_id = getattr(current, "session_id", None)
        return [
            await self._to_session(session, is_current=session.session_id == current_id)
            for session in self._iter_raw_sessions(app)
        ]

    async def get_current_session(self) -> TerminalSession | None:
        app = await self._ensure_connected()
        current = self._current_raw_session(app)
        if current is None:
            return None
        return await self._to_session(current, is_current=True)

    async def get_session(self, session_id: str) -> TerminalSession | None:
        app = await self._ensure_connected()
        raw = self._find_raw_session(app, session_id)
        if raw is None:
            return None
        current = self._current_raw_session(app)
        return await self._to_session(
            raw, is_current=getattr(current, "session_id", None) == session_id
        )

    async def _require_raw_session(self, session_id: str) -> Any:
        app = await self._ensure_connected()
        raw = self._find_raw_session(app, session_id)
        if raw is None:
            raise SessionNotFoundError(session_id)
        return raw

    async def read_terminal(
        self,
        session_id: str,
        *,
        max_lines: int = 200,
        max_chars: int = 32_768,
    ) -> TerminalSnapshot:
        _validate_read_bounds(max_lines, max_chars)
        session = await self._require_raw_session(session_id)
        try:
            screen = await session.async_get_screen_contents()
            lines = [screen.line(index) for index in range(screen.number_of_lines)]
            content, line_count, truncated = _bound_text(_line_text(lines), max_lines, max_chars)
        except (SessionNotFoundError, TermPilotError):
            raise
        except Exception as exc:
            LOGGER.debug("Unable to read screen for %s", session_id, exc_info=True)
            raise TermPilotError(
                ErrorCode.INTERNAL_ERROR, f"Unable to read session '{session_id}'."
            ) from exc
        return TerminalSnapshot(
            session_id=session_id,
            content=content,
            line_count=line_count,
            truncated=truncated,
            execution_readiness=await self._readiness(session_id),
            captured_at=datetime.now(UTC),
        )

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[None]:
        transaction_type = getattr(self._iterm2, "Transaction", None)
        if transaction_type is None or self._connection is None:
            yield
            return
        async with transaction_type(self._connection):
            yield

    @asynccontextmanager
    async def _command_monitor(self, session_id: str) -> AsyncIterator[Any]:
        monitor_type = getattr(self._iterm2, "PromptMonitor", None)
        if monitor_type is None or self._connection is None:
            raise ShellIntegrationRequiredError()
        mode_type = getattr(monitor_type, "Mode", None)
        command_end = getattr(mode_type, "COMMAND_END", 3)
        try:
            context = monitor_type(self._connection, session_id, [command_end])
            monitor = await context.__aenter__()
        except TermPilotError:
            raise
        except Exception as exc:
            LOGGER.debug("Unable to monitor command completion for %s", session_id, exc_info=True)
            raise ShellIntegrationRequiredError(
                "Shell Integration could not monitor command completion safely."
            ) from exc
        try:
            yield monitor
        finally:
            try:
                await context.__aexit__(None, None, None)
            except Exception:
                LOGGER.debug("Unable to close command monitor for %s", session_id, exc_info=True)

    async def _wait_for_command_end(self, monitor: Any) -> tuple[int | None, str | None]:
        mode_type = getattr(type(monitor), "Mode", None)
        command_end = getattr(mode_type, "COMMAND_END", 3)
        try:
            while True:
                try:
                    event = await monitor.async_get(include_id=True)
                except TypeError:
                    event = await monitor.async_get()
                if event is None:
                    raise ShellIntegrationRequiredError(
                        "This iTerm2 version did not report a command completion event."
                    )
                mode, value = event[:2]
                prompt_id = event[2] if len(event) > 2 else None
                if mode == command_end or mode == 3:
                    return (int(value) if value is not None else None, prompt_id)
        except TermPilotError:
            raise
        except Exception as exc:
            LOGGER.debug("Unable to monitor command completion", exc_info=True)
            raise TermPilotError(
                ErrorCode.INTERNAL_ERROR, "Unable to monitor command completion."
            ) from exc

    async def _command_output(self, session: Any, prompt_id: str | None) -> str:
        by_id = getattr(self._iterm2, "async_get_prompt_by_id", None)
        if prompt_id and by_id is not None:
            final_prompt = await by_id(self._connection, session.session_id, prompt_id)
        else:
            get_last = getattr(self._iterm2, "async_get_last_prompt", None)
            final_prompt = (
                await get_last(self._connection, session.session_id) if get_last else None
            )
        if final_prompt is None:
            raise OutputUnavailableError()
        output_range = getattr(final_prompt, "output_range", None)
        start = _point_xy(getattr(output_range, "start", None))
        end = _point_xy(getattr(output_range, "end", None))
        if start is None or end is None:
            raise OutputUnavailableError()
        start_x, start_y = start
        end_x, end_y = end
        if end_y < start_y or (end_y == start_y and end_x < start_x):
            raise OutputUnavailableError()
        if start == end:
            return ""

        line_count = end_y - start_y + (1 if end_x > 0 else 0)
        lines = await session.async_get_contents(start_y, line_count)
        if len(lines) != line_count:
            raise OutputUnavailableError()
        return _coord_range_text(
            lines,
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
        )

    async def run_command(self, request: CommandRequest) -> CommandResult:
        _validate_timeout(request.timeout_seconds)
        session = await self._require_raw_session(request.session_id)
        get_last = getattr(self._iterm2, "async_get_last_prompt", None)
        if get_last is None or self._connection is None:
            raise ShellIntegrationRequiredError()
        prompt = await get_last(self._connection, request.session_id)
        readiness = readiness_from_prompt(prompt, self._iterm2)
        if readiness is ExecutionReadiness.SHELL_INTEGRATION_REQUIRED:
            raise ShellIntegrationRequiredError()
        if readiness is not ExecutionReadiness.READY:
            raise SessionNotReadyError(
                f"Session '{request.session_id}' is not at a verified shell command boundary."
            )
        if not _prompt_command_buffer_is_empty(prompt):
            raise SessionNotReadyError(
                f"Session '{request.session_id}' has pending input at the shell prompt."
            )

        async def send_command() -> None:
            try:
                async with self._transaction():
                    await session.async_send_text(request.command + "\r", suppress_broadcast=True)
            except Exception as exc:
                LOGGER.debug("Unable to send command to %s", request.session_id, exc_info=True)
                if (
                    self._app is not None
                    and self._find_raw_session(self._app, request.session_id) is None
                ):
                    raise SessionNotFoundError(request.session_id) from exc
                raise TermPilotError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Unable to submit command to session '{request.session_id}'.",
                ) from exc

        if not request.wait_for_completion:
            await send_command()
            return CommandResult(
                request_id=request.request_id,
                session_id=request.session_id,
                command=request.command,
                status=CommandStatus.SUBMITTED,
            )

        try:
            async with self._command_monitor(request.session_id) as monitor:
                await send_command()
                exit_code, prompt_id = await asyncio.wait_for(
                    self._wait_for_command_end(monitor),
                    timeout=request.timeout_seconds,
                )
        except TimeoutError:
            return CommandResult(
                request_id=request.request_id,
                session_id=request.session_id,
                command=request.command,
                status=CommandStatus.TIMED_OUT,
                error_code=ErrorCode.COMMAND_TIMEOUT.value,
                message=(
                    f"Stopped waiting after {request.timeout_seconds:g} seconds; "
                    "the command may still be running."
                ),
            )

        try:
            async with self._transaction():
                output = await self._command_output(session, prompt_id)
        except SessionNotFoundError:
            raise
        except OutputUnavailableError as exc:
            return CommandResult(
                request_id=request.request_id,
                session_id=request.session_id,
                command=request.command,
                status=CommandStatus.ERROR,
                exit_code=exit_code,
                error_code=exc.code.value,
                message=exc.message,
            )
        except Exception:
            LOGGER.debug(
                "Unable to capture command output for %s", request.session_id, exc_info=True
            )
            return CommandResult(
                request_id=request.request_id,
                session_id=request.session_id,
                command=request.command,
                status=CommandStatus.ERROR,
                exit_code=exit_code,
                error_code=ErrorCode.INTERNAL_ERROR.value,
                message="Unable to capture command output.",
            )

        output, _line_count, truncated = _bound_text(output, MAX_LINES, request.max_output_chars)
        return CommandResult(
            request_id=request.request_id,
            session_id=request.session_id,
            command=request.command,
            status=CommandStatus.COMPLETED,
            exit_code=exit_code,
            output=output,
            truncated=truncated,
        )
