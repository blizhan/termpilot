"""Stable domain errors shared by adapters, services, and MCP handlers."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    ITERM2_UNAVAILABLE = "iterm2_unavailable"
    SESSION_NOT_FOUND = "session_not_found"
    NO_CURRENT_SESSION = "no_current_session"
    SESSION_NOT_READY = "session_not_ready"
    SHELL_INTEGRATION_REQUIRED = "shell_integration_required"
    COMMAND_TIMEOUT = "command_timeout"
    OUTPUT_UNAVAILABLE = "output_unavailable"
    INVALID_REQUEST = "invalid_request"
    INTERNAL_ERROR = "internal_error"


class TermPilotError(Exception):
    """An expected failure with a stable machine-readable error code."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class Iterm2UnavailableError(TermPilotError):
    def __init__(self, message: str = "iTerm2 Python API is unavailable.") -> None:
        super().__init__(ErrorCode.ITERM2_UNAVAILABLE, message)


class SessionNotFoundError(TermPilotError):
    def __init__(self, session_id: str) -> None:
        super().__init__(ErrorCode.SESSION_NOT_FOUND, f"Session '{session_id}' was not found.")


class NoCurrentSessionError(TermPilotError):
    def __init__(self, message: str = "iTerm2 has no current terminal session.") -> None:
        super().__init__(ErrorCode.NO_CURRENT_SESSION, message)


class SessionNotReadyError(TermPilotError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.SESSION_NOT_READY, message)


class ShellIntegrationRequiredError(TermPilotError):
    def __init__(self, message: str = "Shell Integration is required for this operation.") -> None:
        super().__init__(ErrorCode.SHELL_INTEGRATION_REQUIRED, message)


class OutputUnavailableError(TermPilotError):
    def __init__(self, message: str = "The command output is unavailable.") -> None:
        super().__init__(ErrorCode.OUTPUT_UNAVAILABLE, message)


class InvalidRequestError(TermPilotError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INVALID_REQUEST, message)


def error_payload(error: TermPilotError) -> dict[str, Any]:
    """Return the stable error representation used by MCP responses."""

    return {"error_code": error.code.value, "message": error.message}
