"""Process entry point for the TermPilot MCP server."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence

from termpilot.chatgpt import run_cli as run_chatgpt_cli
from termpilot.mcp_server import create_server


async def run_server() -> None:
    """Run the configured server on the MCP stdio transport."""

    await create_server().run_stdio_async()


def main(argv: Sequence[str] | None = None) -> None:
    """Start stdio MCP by default, or dispatch an explicit human CLI command."""

    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        asyncio.run(run_server())
        return

    if args[0] == "chatgpt":
        exit_code = run_chatgpt_cli(args[1:])
        if exit_code:
            raise SystemExit(exit_code)
        return

    raise SystemExit(f"Unknown TermPilot command: {args[0]}")


if __name__ == "__main__":
    main()
