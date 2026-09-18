# ChatGPT Tunnel Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `termpilot chatgpt setup/status/doctor/disconnect` around OpenAI tunnel-client managed runtimes while preserving the existing no-argument stdio MCP entry point.

**Architecture:** Keep OpenAI tunnel lifecycle state inside `tunnel-client`; TermPilot is a thin typed subprocess wrapper plus CLI dispatcher. The managed runtime launches the current Python interpreter with `-m termpilot.main` so the existing stdio server remains the only MCP implementation.

**Tech Stack:** Python 3.13, argparse, subprocess, JSON, pytest, Ruff, OpenAI `tunnel-client` CLI.

**Spec:** `docs/superpowers/specs/2026-09-16-chatgpt-tunnel-design.md`

## Global Constraints

- `termpilot` with no arguments must continue to start MCP over stdio with no human-readable stdout output.
- Runtime API key values must never be printed, persisted, or placed directly in subprocess arguments; use `env:<NAME>` references.
- The default managed runtime alias is `termpilot`.
- The default runtime key environment variable is `CONTROL_PLANE_API_KEY`.
- TermPilot must not create public ingress or automate ChatGPT browser UI.
- Existing terminal execution safety behavior must remain unchanged.

---

### Task 1: Managed tunnel-client wrapper

**Files:**
- Create: `src/termpilot/chatgpt.py`
- Create: `tests/unit/test_chatgpt.py`

**Interfaces:**
- Produces: `TunnelClient`, `TunnelCommandError`, and result dictionaries for `setup()`, `status()`, `doctor()`, and `disconnect()`.
- Consumes: `sys.executable`, process environment, and external `tunnel-client` only at the subprocess boundary.

- [ ] **Step 1: Write failing tests for setup/status/disconnect**

Tests must cover: missing binary, missing runtime-key env var, exact `runtimes connect` arguments with `env:CONTROL_PLANE_API_KEY`, post-connect status verification, JSON parsing, malformed JSON rejection, and `runtimes stop` for disconnect.

- [ ] **Step 2: Run the focused tests and verify they fail because `termpilot.chatgpt` does not exist**

Run: `uv run pytest -q tests/unit/test_chatgpt.py`

- [ ] **Step 3: Implement the minimal subprocess wrapper**

Use `subprocess.run(..., capture_output=True, text=True, check=False)` behind an injectable runner, `shutil.which` for discovery, and `shlex.join([sys.executable, "-m", "termpilot.main"])` for the MCP command.

- [ ] **Step 4: Run focused tests until green**

Run: `uv run pytest -q tests/unit/test_chatgpt.py`

### Task 2: ChatGPT CLI dispatch and diagnostics

**Files:**
- Modify: `src/termpilot/main.py`
- Modify: `tests/unit/test_main.py`
- Modify: `src/termpilot/chatgpt.py`
- Modify: `tests/unit/test_chatgpt.py`

**Interfaces:**
- Produces: `termpilot chatgpt setup/status/doctor/disconnect` CLI with integer exit status.
- Preserves: `termpilot` no-argument stdio MCP behavior.

- [ ] **Step 1: Write failing CLI/doctor tests**

Tests must prove no-argument dispatch remains stdio-only, `chatgpt` commands do not call `asyncio.run`, setup requires `--tunnel-id`, doctor reports binary/key/runtime checks without secrets, and failures return non-zero.

- [ ] **Step 2: Run focused tests and verify expected failures**

Run: `uv run pytest -q tests/unit/test_main.py tests/unit/test_chatgpt.py`

- [ ] **Step 3: Implement argparse dispatch and doctor formatting**

Keep parser construction and human CLI output outside the MCP server path. Return structured exit codes from ChatGPT subcommands and let `main()` raise `SystemExit` only for non-zero ChatGPT outcomes.

- [ ] **Step 4: Run focused tests until green**

Run: `uv run pytest -q tests/unit/test_main.py tests/unit/test_chatgpt.py`

### Task 3: Documentation and complete verification

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`

**Interfaces:**
- Documents: prerequisites, environment key, setup/status/doctor/disconnect commands, ChatGPT custom-app connection step, and the fact that disconnect leaves the remote tunnel intact.

- [ ] **Step 1: Update English and Chinese quickstart sections**

Document `CONTROL_PLANE_API_KEY`, an existing `tunnel_id`, the four TermPilot commands, and ChatGPT developer-mode Connection = Tunnel setup.

- [ ] **Step 2: Run complete verification**

Run:

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
git diff --check
```

- [ ] **Step 3: Inspect the final diff for secret leakage and unintended MCP changes**

Search the diff for API-key-like literals and confirm existing MCP tools remain unchanged.

