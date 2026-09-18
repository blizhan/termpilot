"""Explicit command validation and orchestration."""

from __future__ import annotations

import logging
from typing import Any

from termpilot.errors import (
    ErrorCode,
    InvalidRequestError,
    SessionNotFoundError,
    SessionNotReadyError,
    ShellIntegrationRequiredError,
    TermPilotError,
)
from termpilot.models import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    DEFAULT_MAX_OUTPUT_CHARS,
    Availability,
    CommandRequest,
    CommandResult,
    CommandStatus,
    ExecutionReadiness,
)
from termpilot.services.sessions import SessionService

LOGGER = logging.getLogger(__name__)


class CommandService:
    """Validate and execute commands against one exact existing session."""

    def __init__(self, backend: Any, sessions: SessionService | None = None) -> None:
        self._backend = backend
        self._sessions = sessions or SessionService(backend)

    @staticmethod
    def _rejected(request: CommandRequest, error: TermPilotError) -> CommandResult:
        return CommandResult(
            request_id=request.request_id,
            session_id=request.session_id,
            command=request.command,
            status=CommandStatus.REJECTED,
            error_code=error.code.value,
            message=error.message,
        )

    @staticmethod
    def _error(request: CommandRequest, error: TermPilotError) -> CommandResult:
        return CommandResult(
            request_id=request.request_id,
            session_id=request.session_id,
            command=request.command,
            status=CommandStatus.ERROR,
            error_code=error.code.value,
            message=error.message,
        )

    async def execute(
        self,
        session_id: str,
        command: str,
        *,
        wait_for_completion: bool = True,
        timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    ) -> CommandResult:
        try:
            request = CommandRequest(
                session_id=session_id,
                command=command,
                wait_for_completion=wait_for_completion,
                timeout_seconds=timeout_seconds,
                max_output_chars=max_output_chars,
            )
        except ValueError as exc:
            raise InvalidRequestError(str(exc)) from exc

        try:
            session = await self._sessions.require_session(request.session_id)
        except SessionNotFoundError as exc:
            return self._rejected(request, exc)

        if session.availability is not Availability.AVAILABLE:
            return self._rejected(request, SessionNotFoundError(request.session_id))
        if session.execution_readiness is ExecutionReadiness.SHELL_INTEGRATION_REQUIRED:
            return self._rejected(
                request,
                TermPilotError(
                    ErrorCode.SHELL_INTEGRATION_REQUIRED,
                    "Shell Integration is required before a command can be submitted safely.",
                ),
            )
        if session.execution_readiness is not ExecutionReadiness.READY:
            return self._rejected(
                request,
                TermPilotError(
                    ErrorCode.SESSION_NOT_READY,
                    f"Session '{request.session_id}' is not at a verified shell command boundary.",
                ),
            )

        try:
            return await self._backend.run_command(request)
        except (
            SessionNotFoundError,
            SessionNotReadyError,
            ShellIntegrationRequiredError,
        ) as exc:
            return self._rejected(request, exc)
        except TermPilotError as exc:
            return self._error(request, exc)
        except Exception:
            LOGGER.exception("Unexpected command failure for %s", request.session_id)
            return self._error(
                request,
                TermPilotError(ErrorCode.INTERNAL_ERROR, "Unexpected command execution failure."),
            )
