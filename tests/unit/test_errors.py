from termpilot.errors import (
    ErrorCode,
    SessionNotFoundError,
    TermPilotError,
    error_payload,
)


def test_domain_error_exposes_stable_code_and_message() -> None:
    error = SessionNotFoundError("session-1")

    assert error.code is ErrorCode.SESSION_NOT_FOUND
    assert error.message == "Session 'session-1' was not found."
    assert error_payload(error) == {
        "error_code": "session_not_found",
        "message": "Session 'session-1' was not found.",
    }


def test_generic_domain_error_can_carry_every_contract_code() -> None:
    error = TermPilotError(ErrorCode.SESSION_NOT_READY, "busy")

    assert str(error) == "busy"
    assert error_payload(error) == {
        "error_code": "session_not_ready",
        "message": "busy",
    }
