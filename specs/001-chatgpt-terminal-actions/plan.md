# Implementation Plan: ChatGPT Terminal Actions

**Branch**: `001-chatgpt-terminal-actions` | **Date**: 2026-09-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-chatgpt-terminal-actions/spec.md`

## Summary

Build TermPilot as a small local Python service that exposes safe, structured terminal actions over MCP while controlling the user's already-open iTerm2 sessions through iTerm2's Python API. The service lists and identifies sessions, reads terminal state, and submits an explicitly requested command only to a specific existing session. Reliable command completion and output capture use iTerm2 Shell Integration prompt metadata and `PromptMonitor`; when the target cannot be identified or is not in a state that can be acted on safely, TermPilot returns a structured refusal instead of guessing.

The MCP layer stays thin. Local development and tests use stdio. ChatGPT integration uses the same MCP server through a supported remote connection path such as Secure MCP Tunnel, because ChatGPT does not connect directly to a local MCP listener. This keeps iTerm2 control independent from the ChatGPT transport and allows the core to be tested without ChatGPT availability.

## Technical Context

**Language/Version**: Python 3.13 (matches the existing project configuration)

**Primary Dependencies**: iTerm2 Python API (`iterm2`), MCP Python SDK v2 (`mcp`), Python `asyncio`; `pytest`/`pytest-anyio` for tests

**Storage**: N/A; v1 keeps no persistent command history or session database

**Testing**: `pytest` for model/service tests, in-process MCP client contract tests, and opt-in integration tests against a running iTerm2 instance

**Target Platform**: macOS with iTerm2 and its Python API enabled; Shell Integration or equivalent prompt-detection triggers required on a target shell for safe `run_command`

**Project Type**: Local service / MCP tool server

**Performance Goals**: Session listing and terminal reads complete in under 500 ms in normal local use; command submission begins in under 250 ms after validation; completed command output becomes available within 5 seconds of iTerm2 reporting command completion

**Constraints**: Must operate on existing iTerm2 sessions; must never silently reroute to another session; command execution requires an explicit `session_id` at the execution boundary; command-like terminal text is data only; no AppleScript/keyboard simulation; no new SSH connection for an already-connected remote session; stdout must remain clean when using MCP stdio transport

**Scale/Scope**: Single-user desktop tool, normally tens of concurrent iTerm2 sessions; v1 covers shell commands and terminal inspection, not general TUI keyboard control

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution is still the unratified Spec Kit template and contains no enforceable project principles or gates. Gate status: **PASS**. The design nevertheless follows the feature specification's explicit safety boundaries: existing-session operation, deterministic targeting, no execution inferred from observed terminal text, and no blind command entry into an unknown terminal state.

**Post-design re-check**: **PASS**. Phase 1 adds no behavior that conflicts with the specification or with any ratified constitution rule. The design keeps the terminal control layer separate from transport, requires exact session identity for mutation, and exposes command execution as a distinct non-read-only tool.

## Project Structure

### Documentation (this feature)

```text
specs/001-chatgpt-terminal-actions/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── mcp-tools.md
└── tasks.md              # Generated later by $speckit-tasks
```

### Source Code (repository root)

```text
src/termpilot/
├── __init__.py
├── main.py               # Process entry point and transport selection
├── mcp_server.py         # MCP tool registration and schema boundary
├── models.py             # Session, snapshot, request, result value objects
├── errors.py             # Stable domain error codes
├── adapters/
│   └── iterm2.py         # iTerm2 connection, lookup, screen and prompt primitives
└── services/
    ├── sessions.py       # Session inventory/current-session resolution
    └── commands.py       # Safe command submission, monitoring and output capture

tests/
├── unit/
│   ├── test_sessions.py
│   └── test_commands.py
├── contract/
│   └── test_mcp_tools.py
└── integration/
    └── test_iterm2_live.py
```

**Structure Decision**: Use a single Python package. Keep iTerm2-specific RPC calls behind one adapter, put routing and execution rules in service modules, and keep MCP registration as an interface layer. This makes the high-risk behavior testable without a live terminal and allows another terminal adapter or another MCP transport to be added later without rewriting command policy.
