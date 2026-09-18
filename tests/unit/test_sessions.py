from __future__ import annotations

from datetime import UTC, datetime

import pytest

from termpilot.errors import ErrorCode, NoCurrentSessionError, SessionNotFoundError
from termpilot.models import (
    ExecutionReadiness,
    MatchStatus,
    TerminalSession,
    TerminalSnapshot,
)
from termpilot.services.sessions import SessionService, match_sessions


def make_session(
    session_id: str,
    *,
    hostname: str | None = None,
    tab_title: str | None = None,
    is_current: bool = False,
) -> TerminalSession:
    return TerminalSession(
        session_id=session_id,
        hostname=hostname,
        tab_title=tab_title,
        is_current=is_current,
        execution_readiness=ExecutionReadiness.READY,
    )


class FakeSessionBackend:
    def __init__(
        self, sessions: list[TerminalSession], current: TerminalSession | None = None
    ) -> None:
        self.sessions = sessions
        self.current = current
        self.reads: list[str] = []

    async def list_sessions(self) -> list[TerminalSession]:
        return list(self.sessions)

    async def get_current_session(self) -> TerminalSession | None:
        return self.current

    async def get_session(self, session_id: str) -> TerminalSession | None:
        return next(
            (session for session in self.sessions if session.session_id == session_id), None
        )

    async def read_terminal(
        self, session_id: str, *, max_lines: int, max_chars: int
    ) -> TerminalSnapshot:
        self.reads.append(session_id)
        return TerminalSnapshot(
            session_id=session_id,
            content="visible",
            line_count=1,
            execution_readiness=ExecutionReadiness.READY,
            captured_at=datetime.now(UTC),
        )


def test_session_match_outcomes_are_explicit() -> None:
    sessions = [
        make_session("one", hostname="example-host", tab_title="ops"),
        make_session("two", hostname="example-host", tab_title="dev"),
    ]

    unique = match_sessions(sessions, tab_title="ops")
    ambiguous = match_sessions(sessions, hostname="example-host")
    not_found = match_sessions(sessions, hostname="missing")

    assert unique.status is MatchStatus.UNIQUE
    assert unique.session_ids == ("one",)
    assert unique.matched_on == ("tab_title",)
    assert ambiguous.status is MatchStatus.AMBIGUOUS
    assert ambiguous.session_ids == ("one", "two")
    assert not_found.status is MatchStatus.NOT_FOUND
    assert not_found.session_ids == ()


@pytest.mark.asyncio
async def test_session_service_returns_current_session_and_sorted_inventory() -> None:
    second = make_session("two", is_current=False)
    first = make_session("one", is_current=True)
    backend = FakeSessionBackend([second, first], current=first)
    service = SessionService(backend)

    current = await service.get_current_session()
    sessions = await service.list_sessions()

    assert current.session_id == "one"
    assert [session.session_id for session in sessions] == ["one", "two"]


@pytest.mark.asyncio
async def test_session_service_reports_missing_current_and_exact_session() -> None:
    backend = FakeSessionBackend([], current=None)
    service = SessionService(backend)

    with pytest.raises(NoCurrentSessionError) as current:
        await service.get_current_session()
    with pytest.raises(SessionNotFoundError) as missing:
        await service.require_session("gone")

    assert current.value.code is ErrorCode.NO_CURRENT_SESSION
    assert missing.value.code is ErrorCode.SESSION_NOT_FOUND


@pytest.mark.asyncio
async def test_session_service_reads_the_requested_session_with_bounds() -> None:
    session = make_session("one")
    backend = FakeSessionBackend([session])
    service = SessionService(backend)

    snapshot = await service.read_terminal("one", max_lines=10, max_chars=100)

    assert snapshot.session_id == "one"
    assert backend.reads == ["one"]
