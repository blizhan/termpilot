from __future__ import annotations

import os

import pytest

from termpilot.adapters.iterm2 import Iterm2Adapter


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("TERMPILOT_LIVE_ITERM2") != "1",
    reason="set TERMPILOT_LIVE_ITERM2=1 to exercise a running iTerm2 instance",
)
async def test_live_iterm2_exposes_unique_sessions() -> None:
    sessions = await Iterm2Adapter().list_sessions()

    session_ids = [session.session_id for session in sessions]
    assert session_ids
    assert len(session_ids) == len(set(session_ids))
    assert sum(session.is_current for session in sessions) <= 1
