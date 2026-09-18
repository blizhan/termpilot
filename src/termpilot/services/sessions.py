"""Session inventory, matching, and read-only terminal operations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from termpilot.errors import NoCurrentSessionError, SessionNotFoundError
from termpilot.models import (
    MAX_LINES,
    MAX_OUTPUT_CHARS,
    Availability,
    MatchStatus,
    SessionMatch,
    TerminalSession,
    TerminalSnapshot,
)


def _same_value(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.casefold() == expected.casefold()
    return actual == expected


def match_sessions(
    sessions: Iterable[TerminalSession],
    *,
    session_id: str | None = None,
    window_title: str | None = None,
    tab_title: str | None = None,
    session_title: str | None = None,
    hostname: str | None = None,
    username: str | None = None,
    cwd: str | None = None,
    is_current: bool | None = None,
) -> SessionMatch:
    """Return a deterministic match outcome without ever choosing ambiguously."""

    candidates = list(sessions)
    matched_on: list[str] = []
    filters = (
        ("session_id", session_id),
        ("window_title", window_title),
        ("tab_title", tab_title),
        ("session_title", session_title),
        ("hostname", hostname),
        ("username", username),
        ("cwd", cwd),
        ("is_current", is_current),
    )
    for field_name, expected in filters:
        if expected is None:
            continue
        candidates = [
            session for session in candidates if _same_value(getattr(session, field_name), expected)
        ]
        matched_on.append(field_name)

    candidates.sort(key=lambda session: session.session_id)
    ids = tuple(session.session_id for session in candidates)
    if not ids:
        return SessionMatch(MatchStatus.NOT_FOUND, matched_on=tuple(matched_on))
    if len(ids) == 1:
        return SessionMatch(MatchStatus.UNIQUE, ids, tuple(matched_on))
    return SessionMatch(MatchStatus.AMBIGUOUS, ids, tuple(matched_on))


def _session_sort_key(session: TerminalSession) -> tuple[Any, ...]:
    return (
        session.window_number is None,
        session.window_number or 0,
        session.window_id or "",
        session.tab_id or "",
        session.session_id,
    )


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


class SessionService:
    """Application-level session operations over an injected terminal backend."""

    def __init__(self, backend: Any) -> None:
        self._backend = backend

    async def list_sessions(self) -> list[TerminalSession]:
        sessions = await self._backend.list_sessions()
        return sorted(sessions, key=_session_sort_key)

    async def get_current_session(self) -> TerminalSession:
        session = await self._backend.get_current_session()
        if session is None:
            raise NoCurrentSessionError()
        return session

    async def require_session(self, session_id: str) -> TerminalSession:
        if not isinstance(session_id, str) or not session_id.strip():
            raise SessionNotFoundError(str(session_id))
        session = await self._backend.get_session(session_id)
        if session is None or session.availability is not Availability.AVAILABLE:
            raise SessionNotFoundError(session_id)
        return session

    async def read_terminal(
        self,
        session_id: str,
        *,
        max_lines: int = 200,
        max_chars: int = 32_768,
    ) -> TerminalSnapshot:
        _validate_read_bounds(max_lines, max_chars)
        await self.require_session(session_id)
        return await self._backend.read_terminal(
            session_id,
            max_lines=max_lines,
            max_chars=max_chars,
        )
