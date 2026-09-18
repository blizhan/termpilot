from __future__ import annotations

import asyncio

import pytest

from termpilot.errors import (
    ErrorCode,
    InvalidRequestError,
    SessionNotReadyError,
    ShellIntegrationRequiredError,
)
from termpilot.models import (
    CommandResult,
    CommandStatus,
    ExecutionReadiness,
    TerminalSession,
)
from termpilot.services.commands import CommandService


def make_session(session_id: str, readiness: ExecutionReadiness) -> TerminalSession:
    return TerminalSession(session_id=session_id, execution_readiness=readiness)


class FakeCommandBackend:
    def __init__(self, session: TerminalSession | None) -> None:
        self.session = session
        self.requests = []
        self.result = None
        self.delay = 0

    async def get_session(self, session_id: str):
        if self.session is not None and self.session.session_id == session_id:
            return self.session
        return None

    async def run_command(self, request):
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.result or CommandResult(
            request_id=request.request_id,
            session_id=request.session_id,
            command=request.command,
            status=CommandStatus.COMPLETED,
            exit_code=0,
            output="ok\n",
        )


@pytest.mark.asyncio
async def test_command_service_executes_in_existing_exact_session() -> None:
    backend = FakeCommandBackend(make_session("session-1", ExecutionReadiness.READY))
    service = CommandService(backend)

    result = await service.execute("session-1", "printf ok")

    assert result.status is CommandStatus.COMPLETED
    assert result.session_id == "session-1"
    assert result.output == "ok\n"
    assert [request.session_id for request in backend.requests] == ["session-1"]


@pytest.mark.asyncio
async def test_command_service_rejects_busy_session_without_sending() -> None:
    backend = FakeCommandBackend(make_session("session-1", ExecutionReadiness.BUSY))
    service = CommandService(backend)

    result = await service.execute("session-1", "printf ok")

    assert result.status is CommandStatus.REJECTED
    assert result.error_code == ErrorCode.SESSION_NOT_READY.value
    assert backend.requests == []


@pytest.mark.parametrize(
    ("backend_error", "error_code"),
    [
        (
            SessionNotReadyError("Session became busy before submission."),
            ErrorCode.SESSION_NOT_READY,
        ),
        (
            ShellIntegrationRequiredError(),
            ErrorCode.SHELL_INTEGRATION_REQUIRED,
        ),
    ],
)
@pytest.mark.asyncio
async def test_command_service_rejects_final_pre_submission_readiness_failure(
    backend_error, error_code
) -> None:
    class RecheckingBackend(FakeCommandBackend):
        async def run_command(self, request):
            self.requests.append(request)
            raise backend_error

    backend = RecheckingBackend(make_session("session-1", ExecutionReadiness.READY))
    service = CommandService(backend)

    result = await service.execute("session-1", "printf ok")

    assert result.status is CommandStatus.REJECTED
    assert result.error_code == error_code.value


@pytest.mark.asyncio
async def test_command_service_does_not_reroute_when_target_disappears() -> None:
    backend = FakeCommandBackend(None)
    service = CommandService(backend)

    result = await service.execute("closed", "printf must-not-run")

    assert result.status is CommandStatus.REJECTED
    assert result.error_code == ErrorCode.SESSION_NOT_FOUND.value
    assert backend.requests == []


@pytest.mark.asyncio
async def test_command_service_preserves_backend_timeout_without_claiming_cancellation() -> None:
    backend = FakeCommandBackend(make_session("session-1", ExecutionReadiness.READY))
    backend.result = CommandResult(
        request_id="backend-timeout",
        session_id="session-1",
        command="sleep 10",
        status=CommandStatus.TIMED_OUT,
        error_code=ErrorCode.COMMAND_TIMEOUT.value,
        message="Stopped waiting; the command may still be running.",
    )
    service = CommandService(backend)

    result = await service.execute("session-1", "sleep 10", timeout_seconds=0.001)

    assert result.status is CommandStatus.TIMED_OUT
    assert result.error_code == ErrorCode.COMMAND_TIMEOUT.value
    assert "may still be running" in result.message
    assert len(backend.requests) == 1


@pytest.mark.asyncio
async def test_command_service_does_not_timeout_before_no_wait_submission_finishes() -> None:
    backend = FakeCommandBackend(make_session("session-1", ExecutionReadiness.READY))
    backend.delay = 0.02
    backend.result = CommandResult(
        request_id="backend-result",
        session_id="session-1",
        command="printf ok",
        status=CommandStatus.SUBMITTED,
    )
    service = CommandService(backend)

    result = await service.execute(
        "session-1",
        "printf ok",
        wait_for_completion=False,
        timeout_seconds=0.001,
    )

    assert result.status is CommandStatus.SUBMITTED
    assert len(backend.requests) == 1


@pytest.mark.asyncio
async def test_command_service_rejects_invalid_command_request() -> None:
    backend = FakeCommandBackend(make_session("session-1", ExecutionReadiness.READY))
    service = CommandService(backend)

    with pytest.raises(InvalidRequestError) as error:
        await service.execute("session-1", " ")

    assert error.value.code is ErrorCode.INVALID_REQUEST
