from __future__ import annotations

import json
import subprocess
from io import StringIO

import pytest

from termpilot import chatgpt
from termpilot.chatgpt import (
    TunnelClient,
    TunnelClientUnavailableError,
    TunnelCommandError,
    TunnelConfigError,
    resolve_tunnel_client,
    run_cli,
)


def completed(argv: list[str], *, stdout: str = "", stderr: str = "", code: int = 0):
    return subprocess.CompletedProcess(argv, code, stdout=stdout, stderr=stderr)


def healthy_status() -> dict[str, object]:
    return {
        "alias": "termpilot",
        "tunnel_id": "tunnel_test",
        "runtime_state": "running",
        "process_running": True,
        "healthy": True,
        "ready": True,
        "ui_url": "http://127.0.0.1:61234/ui",
    }


def test_resolve_tunnel_client_fails_when_binary_is_missing(monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)

    with pytest.raises(TunnelClientUnavailableError, match="tunnel-client"):
        resolve_tunnel_client()


def test_setup_requires_runtime_key_before_starting_external_process() -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str]):
        calls.append(argv)
        return completed(argv)

    client = TunnelClient(
        binary="/usr/local/bin/tunnel-client",
        environ={},
        runner=runner,
        python_executable="/venv/bin/python",
    )

    with pytest.raises(TunnelConfigError, match="CONTROL_PLANE_API_KEY"):
        client.setup("tunnel_test")

    assert calls == []


def test_setup_connects_stdio_with_env_key_reference_and_verifies_status() -> None:
    calls: list[list[str]] = []
    outputs = [
        {"alias": "termpilot", "mode": "managed"},
        healthy_status(),
    ]

    def runner(argv: list[str]):
        calls.append(argv)
        return completed(argv, stdout=json.dumps(outputs.pop(0)))

    client = TunnelClient(
        binary="/usr/local/bin/tunnel-client",
        environ={"CONTROL_PLANE_API_KEY": "sk-secret-must-not-leak"},
        runner=runner,
        python_executable="/venv/bin/python",
    )

    result = client.setup("tunnel_test")

    assert calls == [
        [
            "/usr/local/bin/tunnel-client",
            "runtimes",
            "--json",
            "connect",
            "--alias",
            "termpilot",
            "--tunnel-id",
            "tunnel_test",
            "--runtime-api-key",
            "env:CONTROL_PLANE_API_KEY",
            "--mcp-command",
            "/venv/bin/python -m termpilot.main",
        ],
        [
            "/usr/local/bin/tunnel-client",
            "runtimes",
            "--json",
            "status",
            "termpilot",
        ],
    ]
    assert result == healthy_status()
    assert "sk-secret-must-not-leak" not in repr(calls)


def test_setup_rejects_runtime_that_is_not_healthy() -> None:
    outputs = [
        {"alias": "termpilot", "mode": "managed"},
        {
            **healthy_status(),
            "healthy": False,
            "ready": False,
        },
    ]

    def runner(argv: list[str]):
        return completed(argv, stdout=json.dumps(outputs.pop(0)))

    client = TunnelClient(
        binary="tunnel-client",
        environ={"CONTROL_PLANE_API_KEY": "secret"},
        runner=runner,
    )

    with pytest.raises(TunnelCommandError, match="not healthy"):
        client.setup("tunnel_test")


def test_status_rejects_malformed_json() -> None:
    def runner(argv: list[str]):
        return completed(argv, stdout="not-json")

    client = TunnelClient(binary="tunnel-client", environ={}, runner=runner)

    with pytest.raises(TunnelCommandError, match="invalid JSON"):
        client.status()


def test_nonzero_tunnel_client_exit_surfaces_diagnostic() -> None:
    def runner(argv: list[str]):
        return completed(argv, stderr="alias not found", code=7)

    client = TunnelClient(binary="tunnel-client", environ={}, runner=runner)

    with pytest.raises(TunnelCommandError, match="alias not found") as error:
        client.status()

    assert error.value.returncode == 7


def test_disconnect_stops_local_runtime_without_removing_alias() -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str]):
        calls.append(argv)
        return completed(argv, stdout=json.dumps({"alias": "termpilot", "stopped": True}))

    client = TunnelClient(binary="tunnel-client", environ={}, runner=runner)

    result = client.disconnect()

    assert result == {"alias": "termpilot", "stopped": True}
    assert calls == [["tunnel-client", "runtimes", "--json", "stop", "termpilot"]]


def test_doctor_reports_binary_key_and_runtime_health_without_secret() -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str]):
        calls.append(argv)
        if argv[-1] == "--version":
            return completed(argv, stdout="tunnel-client 1.2.3\n")
        return completed(argv, stdout=json.dumps(healthy_status()))

    client = TunnelClient(
        binary="tunnel-client",
        environ={"CONTROL_PLANE_API_KEY": "sk-never-print-this"},
        runner=runner,
    )

    result = client.doctor()

    assert result["ok"] is True
    assert result["checks"]["tunnel_client"]["ok"] is True
    assert result["checks"]["runtime_key"] == {
        "ok": True,
        "env": "CONTROL_PLANE_API_KEY",
    }
    assert result["checks"]["runtime"]["ok"] is True
    assert "sk-never-print-this" not in json.dumps(result)
    assert calls[0] == ["tunnel-client", "--version"]


def test_doctor_returns_unhealthy_when_runtime_key_is_missing() -> None:
    def runner(argv: list[str]):
        if argv[-1] == "--version":
            return completed(argv, stdout="tunnel-client dev\n")
        return completed(argv, stdout=json.dumps(healthy_status()))

    client = TunnelClient(binary="tunnel-client", environ={}, runner=runner)

    result = client.doctor()

    assert result["ok"] is False
    assert result["checks"]["runtime_key"] == {
        "ok": False,
        "env": "CONTROL_PLANE_API_KEY",
    }


def test_cli_setup_prints_chatgpt_tunnel_next_step_without_secret(monkeypatch) -> None:
    outputs = [
        {"alias": "termpilot", "mode": "managed"},
        healthy_status(),
    ]

    def fake_run(argv, **_kwargs):
        return completed(argv, stdout=json.dumps(outputs.pop(0)))

    monkeypatch.setattr(chatgpt.shutil, "which", lambda _name: "/opt/bin/tunnel-client")
    monkeypatch.setattr(chatgpt.subprocess, "run", fake_run)
    stdout = StringIO()
    stderr = StringIO()

    code = run_cli(
        ["setup", "--tunnel-id", "tunnel_test"],
        stdout=stdout,
        stderr=stderr,
        environ={"CONTROL_PLANE_API_KEY": "sk-secret"},
    )

    assert code == 0
    assert stderr.getvalue() == ""
    assert "Connection = Tunnel" in stdout.getvalue()
    assert "tunnel_test" in stdout.getvalue()
    assert "https://chatgpt.com/plugins" in stdout.getvalue()
    assert "sk-secret" not in stdout.getvalue()


def test_cli_doctor_returns_nonzero_and_explains_missing_runtime_key(monkeypatch) -> None:
    def fake_run(argv, **_kwargs):
        if argv[-1] == "--version":
            return completed(argv, stdout="tunnel-client dev\n")
        return completed(argv, stdout=json.dumps(healthy_status()))

    monkeypatch.setattr(chatgpt.shutil, "which", lambda _name: "/opt/bin/tunnel-client")
    monkeypatch.setattr(chatgpt.subprocess, "run", fake_run)
    stdout = StringIO()
    stderr = StringIO()

    code = run_cli(["doctor"], stdout=stdout, stderr=stderr, environ={})

    assert code == 1
    assert stderr.getvalue() == ""
    assert "CONTROL_PLANE_API_KEY" in stdout.getvalue()
    assert "missing" in stdout.getvalue().lower()


def test_cli_status_surfaces_tunnel_client_failure(monkeypatch) -> None:
    def fake_run(argv, **_kwargs):
        return completed(argv, stderr="runtime alias missing", code=3)

    monkeypatch.setattr(chatgpt.shutil, "which", lambda _name: "/opt/bin/tunnel-client")
    monkeypatch.setattr(chatgpt.subprocess, "run", fake_run)
    stdout = StringIO()
    stderr = StringIO()

    code = run_cli(["status"], stdout=stdout, stderr=stderr, environ={})

    assert code == 1
    assert stdout.getvalue() == ""
    assert "runtime alias missing" in stderr.getvalue()


def test_cli_setup_requires_tunnel_id() -> None:
    with pytest.raises(SystemExit) as error:
        run_cli(["setup"], stdout=StringIO(), stderr=StringIO(), environ={})

    assert error.value.code == 2
