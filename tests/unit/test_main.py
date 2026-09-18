from __future__ import annotations

import pytest

from termpilot import main as main_module


class FakeServer:
    def __init__(self) -> None:
        self.started = False

    async def run_stdio_async(self) -> None:
        self.started = True


def test_main_runs_the_mcp_server_over_stdio(monkeypatch) -> None:
    server = FakeServer()
    calls: list[object] = []

    monkeypatch.setattr(main_module, "create_server", lambda: server)

    def fake_asyncio_run(coro):
        calls.append(coro)
        coro.close()

    monkeypatch.setattr(main_module.asyncio, "run", fake_asyncio_run)

    main_module.main([])

    assert len(calls) == 1


def test_main_dispatches_chatgpt_cli_without_starting_stdio(monkeypatch) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(
        main_module,
        "run_chatgpt_cli",
        lambda argv: calls.append(list(argv)) or 0,
    )
    monkeypatch.setattr(
        main_module.asyncio,
        "run",
        lambda _coro: pytest.fail("stdio MCP server must not start for chatgpt commands"),
    )

    main_module.main(["chatgpt", "status"])

    assert calls == [["status"]]


def test_main_propagates_chatgpt_cli_failure_as_exit_status(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "run_chatgpt_cli", lambda _argv: 7)

    with pytest.raises(SystemExit) as error:
        main_module.main(["chatgpt", "doctor"])

    assert error.value.code == 7
