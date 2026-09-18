from datetime import UTC, datetime

import pytest

from termpilot.models import (
    Availability,
    CommandRequest,
    CommandResult,
    CommandStatus,
    ExecutionReadiness,
    MatchStatus,
    SessionMatch,
    TerminalSession,
    TerminalSnapshot,
)


def test_terminal_session_serializes_enum_values_and_identity_fields() -> None:
    session = TerminalSession(
        session_id="session-1",
        window_id="window-1",
        tab_id="tab-1",
        session_title="ssh example-host",
        hostname="example-host",
        cwd="/home/example",
        is_current=True,
        availability=Availability.AVAILABLE,
        execution_readiness=ExecutionReadiness.READY,
    )

    assert session.to_dict() == {
        "session_id": "session-1",
        "window_id": "window-1",
        "tab_id": "tab-1",
        "window_title": None,
        "tab_title": None,
        "session_title": "ssh example-host",
        "hostname": "example-host",
        "username": None,
        "cwd": "/home/example",
        "tty": None,
        "window_number": None,
        "is_current": True,
        "availability": "available",
        "execution_readiness": "ready",
    }


def test_command_request_rejects_empty_or_unsafe_values() -> None:
    with pytest.raises(ValueError, match="session_id"):
        CommandRequest(session_id="", command="printf ok")

    with pytest.raises(ValueError, match="command"):
        CommandRequest(session_id="session-1", command="   ")

    with pytest.raises(ValueError, match="NUL"):
        CommandRequest(session_id="session-1", command="printf '\x00'")

    with pytest.raises(ValueError, match="timeout_seconds"):
        CommandRequest(session_id="session-1", command="printf ok", timeout_seconds=0)

    with pytest.raises(ValueError, match="timeout_seconds"):
        CommandRequest(session_id="session-1", command="printf ok", timeout_seconds="1")

    with pytest.raises(ValueError, match="max_output_chars"):
        CommandRequest(session_id="session-1", command="printf ok", max_output_chars=True)


def test_session_match_requires_candidate_count_to_match_status() -> None:
    assert SessionMatch(MatchStatus.UNIQUE, ("session-1",)).to_dict() == {
        "status": "unique",
        "session_ids": ["session-1"],
        "matched_on": [],
    }

    with pytest.raises(ValueError, match="exactly one"):
        SessionMatch(MatchStatus.UNIQUE, ("session-1", "session-2"))

    with pytest.raises(ValueError, match="at least two"):
        SessionMatch(MatchStatus.AMBIGUOUS, ("session-1",))


def test_command_result_and_snapshot_are_json_ready() -> None:
    captured_at = datetime(2026, 9, 16, 1, 2, 3, tzinfo=UTC)
    snapshot = TerminalSnapshot(
        session_id="session-1",
        content="hello\n",
        line_count=1,
        captured_at=captured_at,
    )
    result = CommandResult(
        request_id="request-1",
        session_id="session-1",
        command="printf hello",
        status=CommandStatus.COMPLETED,
        exit_code=0,
        output="hello\n",
    )

    assert snapshot.to_dict()["captured_at"] == "2026-09-16T01:02:03+00:00"
    assert result.to_dict()["status"] == "completed"
    assert result.to_dict()["exit_code"] == 0
