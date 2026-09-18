"""Stable, transport-independent values used by TermPilot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

MAX_COMMAND_LENGTH = 8_192
DEFAULT_COMMAND_TIMEOUT_SECONDS = 30.0
MAX_COMMAND_TIMEOUT_SECONDS = 300.0
DEFAULT_MAX_OUTPUT_CHARS = 32_768
MAX_OUTPUT_CHARS = 131_072
DEFAULT_MAX_LINES = 200
MAX_LINES = 2_000


class Availability(StrEnum):
    """Whether iTerm2 still exposes a session to the adapter."""

    AVAILABLE = "available"
    CLOSED = "closed"
    INACCESSIBLE = "inaccessible"


class ExecutionReadiness(StrEnum):
    """Whether a session is at a verified shell command boundary."""

    READY = "ready"
    BUSY = "busy"
    UNKNOWN = "unknown"
    SHELL_INTEGRATION_REQUIRED = "shell_integration_required"


class MatchStatus(StrEnum):
    """Outcome of matching conversational hints to sessions."""

    UNIQUE = "unique"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


class CommandStatus(StrEnum):
    """Lifecycle outcome of a command request."""

    COMPLETED = "completed"
    SUBMITTED = "submitted"
    TIMED_OUT = "timed_out"
    REJECTED = "rejected"
    SESSION_LOST = "session_lost"
    ERROR = "error"


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    if "\x00" in value:
        raise ValueError(f"{field_name} must not contain NUL characters")
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


@dataclass(frozen=True, slots=True)
class TerminalSession:
    """An existing iTerm2 session and its latest observable metadata."""

    session_id: str
    window_id: str | None = None
    tab_id: str | None = None
    window_title: str | None = None
    tab_title: str | None = None
    session_title: str | None = None
    hostname: str | None = None
    username: str | None = None
    cwd: str | None = None
    tty: str | None = None
    window_number: int | None = None
    is_current: bool = False
    availability: Availability = Availability.AVAILABLE
    execution_readiness: ExecutionReadiness = ExecutionReadiness.UNKNOWN

    def __post_init__(self) -> None:
        _require_text(self.session_id, "session_id")

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True, slots=True)
class SessionMatch:
    """The safe result of matching session hints to candidate session IDs."""

    status: MatchStatus
    session_ids: tuple[str, ...] = ()
    matched_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status is MatchStatus.UNIQUE and len(self.session_ids) != 1:
            raise ValueError("unique match must contain exactly one session_id")
        if self.status is MatchStatus.AMBIGUOUS and len(self.session_ids) < 2:
            raise ValueError("ambiguous match must contain at least two session_ids")
        if self.status is MatchStatus.NOT_FOUND and self.session_ids:
            raise ValueError("not_found match must not contain session_ids")

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True, slots=True)
class TerminalSnapshot:
    """A bounded observation of a session's visible terminal content."""

    session_id: str
    content: str
    line_count: int
    truncated: bool = False
    execution_readiness: ExecutionReadiness = ExecutionReadiness.UNKNOWN
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        _require_text(self.session_id, "session_id")
        if self.line_count < 0:
            raise ValueError("line_count must be non-negative")
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must include timezone information")

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True, slots=True)
class CommandRequest:
    """An explicit request to enter a command into one existing session."""

    session_id: str
    command: str
    wait_for_completion: bool = True
    timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS
    request_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        _require_text(self.session_id, "session_id")
        command = _require_text(self.command, "command")
        if len(command) > MAX_COMMAND_LENGTH:
            raise ValueError(f"command must be at most {MAX_COMMAND_LENGTH} characters")
        if not isinstance(self.wait_for_completion, bool):
            raise ValueError("wait_for_completion must be a boolean")
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(
            self.timeout_seconds, bool
        ):
            raise ValueError("timeout_seconds must be a number")
        if not 0 < self.timeout_seconds <= MAX_COMMAND_TIMEOUT_SECONDS:
            raise ValueError(
                f"timeout_seconds must be greater than 0 and at most {MAX_COMMAND_TIMEOUT_SECONDS}"
            )
        if not isinstance(self.max_output_chars, int) or isinstance(self.max_output_chars, bool):
            raise ValueError("max_output_chars must be an integer")
        if not 0 < self.max_output_chars <= MAX_OUTPUT_CHARS:
            raise ValueError(
                f"max_output_chars must be greater than 0 and at most {MAX_OUTPUT_CHARS}"
            )

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Observable outcome correlated to one command request."""

    request_id: str
    session_id: str
    command: str
    status: CommandStatus
    exit_code: int | None = None
    output: str | None = None
    truncated: bool = False
    error_code: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.request_id, "request_id")
        _require_text(self.session_id, "session_id")
        _require_text(self.command, "command")

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))
