"""ChatGPT Secure MCP Tunnel integration.

TermPilot deliberately delegates tunnel lifecycle and persistence to the
official ``tunnel-client`` executable. This module only builds bounded CLI
calls and normalizes their JSON results for TermPilot's user-facing CLI.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from io import TextIOBase
from pathlib import Path
from typing import Any

DEFAULT_ALIAS = "termpilot"
DEFAULT_RUNTIME_KEY_ENV = "CONTROL_PLANE_API_KEY"
CHATGPT_PLUGINS_URL = "https://chatgpt.com/plugins"

ProcessRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class TunnelError(RuntimeError):
    """Base error for ChatGPT tunnel integration failures."""


class TunnelClientUnavailableError(TunnelError):
    """Raised when the tunnel-client executable cannot be resolved."""


class TunnelConfigError(TunnelError):
    """Raised when required local tunnel configuration is absent."""


class TunnelCommandError(TunnelError):
    """Raised when tunnel-client fails or returns unusable output."""

    def __init__(self, message: str, *, returncode: int | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode


def _default_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
    )


def resolve_tunnel_client(explicit: str | None = None) -> str:
    """Resolve the tunnel-client executable without launching it."""

    if explicit:
        candidate = shutil.which(explicit)
        if candidate is None:
            path = Path(explicit).expanduser()
            if path.is_file() and os.access(path, os.X_OK):
                candidate = str(path.resolve())
        if candidate is not None:
            return candidate
        raise TunnelClientUnavailableError(f"tunnel-client executable not found: {explicit}")

    candidate = shutil.which("tunnel-client")
    if candidate is None:
        raise TunnelClientUnavailableError(
            "tunnel-client is not installed or is not available on PATH."
        )
    return candidate


class TunnelClient:
    """Thin wrapper around tunnel-client's managed runtime commands."""

    def __init__(
        self,
        *,
        binary: str,
        alias: str = DEFAULT_ALIAS,
        runtime_key_env: str = DEFAULT_RUNTIME_KEY_ENV,
        environ: Mapping[str, str] | None = None,
        runner: ProcessRunner | None = None,
        python_executable: str | None = None,
    ) -> None:
        self.binary = binary
        self.alias = alias
        self.runtime_key_env = runtime_key_env
        self.environ = os.environ if environ is None else environ
        self._runner = _default_runner if runner is None else runner
        self.python_executable = sys.executable if python_executable is None else python_executable

    def _run_json(self, arguments: Sequence[str]) -> dict[str, Any]:
        argv = [self.binary, *arguments]
        result = self._runner(argv)
        if result.returncode != 0:
            diagnostic = (result.stderr or result.stdout or "").strip()
            if not diagnostic:
                diagnostic = f"tunnel-client exited with status {result.returncode}"
            raise TunnelCommandError(diagnostic, returncode=result.returncode)

        try:
            payload = json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise TunnelCommandError("tunnel-client returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise TunnelCommandError("tunnel-client returned invalid JSON payload shape.")
        return payload

    def _run_text(self, arguments: Sequence[str]) -> str:
        argv = [self.binary, *arguments]
        result = self._runner(argv)
        if result.returncode != 0:
            diagnostic = (result.stderr or result.stdout or "").strip()
            if not diagnostic:
                diagnostic = f"tunnel-client exited with status {result.returncode}"
            raise TunnelCommandError(diagnostic, returncode=result.returncode)
        return (result.stdout or result.stderr or "").strip()

    def status(self) -> dict[str, Any]:
        """Return native managed runtime state for this alias."""

        return self._run_json(["runtimes", "--json", "status", self.alias])

    def setup(self, tunnel_id: str) -> dict[str, Any]:
        """Connect TermPilot's stdio MCP server to an existing tunnel."""

        tunnel_id = tunnel_id.strip()
        if not tunnel_id:
            raise TunnelConfigError("A tunnel ID is required.")
        if not self.environ.get(self.runtime_key_env):
            raise TunnelConfigError(
                f"Runtime API key environment variable {self.runtime_key_env} is not set."
            )

        mcp_command = shlex.join([self.python_executable, "-m", "termpilot.main"])
        self._run_json(
            [
                "runtimes",
                "--json",
                "connect",
                "--alias",
                self.alias,
                "--tunnel-id",
                tunnel_id,
                "--runtime-api-key",
                f"env:{self.runtime_key_env}",
                "--mcp-command",
                mcp_command,
            ]
        )
        status = self.status()
        if status.get("process_running") is not True or status.get("healthy") is not True:
            raise TunnelCommandError(f"Managed runtime '{self.alias}' started but is not healthy.")
        return status

    def disconnect(self) -> dict[str, Any]:
        """Stop only the local managed runtime, leaving the remote tunnel intact."""

        return self._run_json(["runtimes", "--json", "stop", self.alias])

    def doctor(self) -> dict[str, Any]:
        """Run non-mutating local diagnostics for the managed runtime."""

        checks: dict[str, dict[str, Any]] = {}
        try:
            version = self._run_text(["--version"])
        except TunnelCommandError as exc:
            checks["tunnel_client"] = {
                "ok": False,
                "path": self.binary,
                "error": str(exc),
            }
            return {"ok": False, "checks": checks}

        checks["tunnel_client"] = {
            "ok": True,
            "path": self.binary,
            "version": version,
        }
        checks["runtime_key"] = {
            "ok": bool(self.environ.get(self.runtime_key_env)),
            "env": self.runtime_key_env,
        }

        status: dict[str, Any] | None = None
        try:
            status = self.status()
            runtime_ok = status.get("process_running") is True and status.get("healthy") is True
            checks["runtime"] = {
                "ok": runtime_ok,
                "process_running": status.get("process_running"),
                "healthy": status.get("healthy"),
                "ready": status.get("ready"),
            }
        except TunnelCommandError as exc:
            checks["runtime"] = {"ok": False, "error": str(exc)}

        return {
            "ok": all(check.get("ok") is True for check in checks.values()),
            "checks": checks,
            "status": status,
        }


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--alias", default=DEFAULT_ALIAS)
    parser.add_argument("--tunnel-client")
    parser.add_argument("--runtime-key-env", default=DEFAULT_RUNTIME_KEY_ENV)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="termpilot chatgpt",
        description="Connect TermPilot to ChatGPT through OpenAI Secure MCP Tunnel.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    setup = commands.add_parser("setup", help="Connect a managed local tunnel runtime.")
    _add_common_arguments(setup)
    setup.add_argument("--tunnel-id", required=True)

    status = commands.add_parser("status", help="Show managed runtime status.")
    _add_common_arguments(status)

    doctor = commands.add_parser("doctor", help="Run non-mutating local diagnostics.")
    _add_common_arguments(doctor)

    disconnect = commands.add_parser("disconnect", help="Stop the local managed runtime.")
    _add_common_arguments(disconnect)
    return parser


def _yes_no(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _write_status(payload: Mapping[str, Any], stream: TextIOBase) -> None:
    stream.write(f"Alias: {payload.get('alias', 'unknown')}\n")
    stream.write(f"Tunnel: {payload.get('tunnel_id', 'unknown')}\n")
    stream.write(f"Runtime state: {payload.get('runtime_state', 'unknown')}\n")
    stream.write(f"Process running: {_yes_no(payload.get('process_running'))}\n")
    stream.write(f"Healthy: {_yes_no(payload.get('healthy'))}\n")
    stream.write(f"Ready: {_yes_no(payload.get('ready'))}\n")
    if payload.get("ui_url"):
        stream.write(f"Local UI: {payload['ui_url']}\n")


def _write_doctor(payload: Mapping[str, Any], stream: TextIOBase) -> None:
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        checks = {}

    binary = checks.get("tunnel_client", {})
    if isinstance(binary, dict):
        label = "ok" if binary.get("ok") is True else "failed"
        stream.write(f"tunnel-client: {label}")
        if binary.get("version"):
            stream.write(f" ({binary['version']})")
        if binary.get("error"):
            stream.write(f" - {binary['error']}")
        stream.write("\n")

    key = checks.get("runtime_key", {})
    if isinstance(key, dict):
        env_name = key.get("env", DEFAULT_RUNTIME_KEY_ENV)
        label = "set" if key.get("ok") is True else "missing"
        stream.write(f"runtime key {env_name}: {label}\n")

    runtime = checks.get("runtime", {})
    if isinstance(runtime, dict):
        label = "ok" if runtime.get("ok") is True else "failed"
        stream.write(f"runtime: {label}")
        if runtime.get("error"):
            stream.write(f" - {runtime['error']}")
        stream.write("\n")


def run_cli(
    argv: Sequence[str],
    *,
    stdout: TextIOBase | None = None,
    stderr: TextIOBase | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Run the human-facing ChatGPT tunnel CLI and return a process exit code."""

    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    environment = os.environ if environ is None else environ
    args = _build_parser().parse_args(list(argv))

    try:
        binary = resolve_tunnel_client(args.tunnel_client)
        client = TunnelClient(
            binary=binary,
            alias=args.alias,
            runtime_key_env=args.runtime_key_env,
            environ=environment,
        )

        if args.command == "setup":
            status = client.setup(args.tunnel_id)
            stdout.write("TermPilot tunnel runtime connected.\n")
            _write_status(status, stdout)
            stdout.write("\nNext: open ChatGPT Plugins and create a developer-mode app.\n")
            stdout.write("Choose Connection = Tunnel and select or paste this tunnel ID:\n")
            stdout.write(f"  {args.tunnel_id}\n")
            stdout.write(f"  {CHATGPT_PLUGINS_URL}\n")
            return 0

        if args.command == "status":
            _write_status(client.status(), stdout)
            return 0

        if args.command == "doctor":
            result = client.doctor()
            _write_doctor(result, stdout)
            return 0 if result.get("ok") is True else 1

        if args.command == "disconnect":
            client.disconnect()
            stdout.write(
                f"Stopped local tunnel runtime '{args.alias}'. The remote tunnel was not deleted.\n"
            )
            return 0
    except TunnelError as exc:
        stderr.write(f"Error: {exc}\n")
        return 1

    stderr.write(f"Error: unsupported chatgpt command: {args.command}\n")
    return 2
