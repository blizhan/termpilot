"""MCP interface for TermPilot."""

from __future__ import annotations

import json
from typing import Any

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from termpilot.adapters.iterm2 import Iterm2Adapter
from termpilot.errors import ErrorCode, InvalidRequestError, TermPilotError, error_payload
from termpilot.models import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    DEFAULT_MAX_LINES,
    DEFAULT_MAX_OUTPUT_CHARS,
)
from termpilot.services.commands import CommandService
from termpilot.services.sessions import SessionService

SERVER_NAME = "TermPilot"
SERVER_DESCRIPTION = "Terminal actions for ChatGPT Work with Apps using existing iTerm2 sessions."


def _result(payload: dict[str, Any], *, summary: str, is_error: bool = False) -> CallToolResult:
    text = summary if summary else json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return CallToolResult(
        content=[TextContent(text=text)],
        structuredContent=payload,
        isError=is_error,
    )


def _success(payload: dict[str, Any], summary: str) -> CallToolResult:
    return _result(payload, summary=summary)


def _failure(error: TermPilotError) -> CallToolResult:
    payload = error_payload(error)
    return _result(payload, summary=f"{payload['error_code']}: {payload['message']}", is_error=True)


def _unexpected_failure(_error: Exception) -> CallToolResult:
    return _failure(TermPilotError(ErrorCode.INTERNAL_ERROR, "Unexpected TermPilot failure."))


def create_server(backend: Any | None = None) -> MCPServer:
    """Create a configured MCP server, optionally with an injected backend."""

    if backend is None:
        backend = Iterm2Adapter()
    sessions = SessionService(backend)
    commands = CommandService(backend, sessions)
    server = MCPServer(
        SERVER_NAME,
        description=SERVER_DESCRIPTION,
        version="0.1.0",
    )

    @server.tool(
        name="list_sessions",
        description="List accessible existing iTerm2 sessions and their observable metadata.",
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
        structured_output=False,
    )
    async def list_sessions() -> CallToolResult:
        try:
            items = await sessions.list_sessions()
            payload = {"sessions": [session.to_dict() for session in items]}
            return _success(payload, f"Found {len(items)} accessible iTerm2 session(s).")
        except TermPilotError as error:
            return _failure(error)
        except Exception as error:
            return _unexpected_failure(error)

    @server.tool(
        name="get_current_session",
        description="Return the iTerm2 terminal session currently in focus.",
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
        structured_output=False,
    )
    async def get_current_session() -> CallToolResult:
        try:
            session = await sessions.get_current_session()
            return _success(session.to_dict(), f"Current session: {session.session_id}.")
        except TermPilotError as error:
            return _failure(error)
        except Exception as error:
            return _unexpected_failure(error)

    @server.tool(
        name="read_terminal",
        description="Read bounded visible content from one exact existing iTerm2 session.",
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
        structured_output=False,
    )
    async def read_terminal(
        session_id: str,
        max_lines: int = DEFAULT_MAX_LINES,
        max_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    ) -> CallToolResult:
        try:
            snapshot = await sessions.read_terminal(
                session_id,
                max_lines=max_lines,
                max_chars=max_chars,
            )
            return _success(snapshot.to_dict(), f"Read terminal session {session_id}.")
        except TermPilotError as error:
            return _failure(error)
        except ValueError as error:
            return _failure(InvalidRequestError(str(error)))
        except Exception as error:
            return _unexpected_failure(error)

    @server.tool(
        name="run_command",
        description=(
            "Submit an explicitly requested shell command to one exact existing iTerm2 session. "
            "The command is never inferred from terminal content."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        ),
        structured_output=False,
    )
    async def run_command(
        session_id: str,
        command: str,
        wait_for_completion: bool = True,
        timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    ) -> CallToolResult:
        try:
            result = await commands.execute(
                session_id,
                command,
                wait_for_completion=wait_for_completion,
                timeout_seconds=timeout_seconds,
                max_output_chars=max_output_chars,
            )
            return _success(
                result.to_dict(), f"Command {result.status.value} in session {session_id}."
            )
        except TermPilotError as error:
            return _failure(error)
        except Exception as error:
            return _unexpected_failure(error)

    return server
