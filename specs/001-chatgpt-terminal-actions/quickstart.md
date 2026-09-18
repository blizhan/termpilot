# Quickstart Validation: ChatGPT Terminal Actions

This guide describes the end-to-end checks the implementation must satisfy. It is a validation guide, not implementation code.

## Prerequisites

- macOS with iTerm2 running.
- iTerm2 Python API enabled.
- Shell Integration (or equivalent prompt-detection triggers) installed in every shell/remote shell used for `run_command` validation.
- Python 3.13 and `uv`.
- At least one ordinary shell session. For multi-session validation, open three distinguishable sessions, including an existing `ssh example-host` session if available.

## 1. Install and run locally

After implementation, from the repository root:

```bash
uv sync
uv run pytest
uv run termpilot
```

The stdio server should start without writing protocol-breaking text to stdout. Operational logs go to stderr.

## 2. Verify session discovery

Using an MCP client/inspector, call `list_sessions` and then `get_current_session`.

Expected outcome:

- Every returned session has a unique `session_id`.
- The currently focused iTerm2 pane is marked/currently returned consistently.
- Host and working directory are returned when Shell Integration provides them.
- If multiple tabs are named `example-host`, their stable IDs still distinguish them.

Contract: [contracts/mcp-tools.md](./contracts/mcp-tools.md)

## 3. Verify terminal inspection

In one session, run a visible harmless command manually, such as:

```bash
printf 'termpilot-read-test\n'
```

Call `read_terminal` with that session's exact `session_id`.

Expected outcome: the returned snapshot contains `termpilot-read-test`, is associated with the requested session ID, and reports whether truncation occurred.

## 4. Verify safe command execution

With the selected shell sitting at a prompt, invoke `run_command` with:

```text
command: printf 'termpilot-run-test\n'
```

Expected outcome:

- The command appears only in the selected session.
- The result status is `completed`.
- Exit code is `0` when reported by Shell Integration.
- Output contains `termpilot-run-test`.
- No new terminal or SSH connection is created.

Repeat against an already-established remote shell. Confirm the command executes in that existing remote context.

## 5. Verify wrong-session prevention

Open at least three sessions. Record the target `session_id`, then close that session before calling `run_command`.

Expected outcome: `run_command` returns `session_not_found`; no other session receives the command.

Then create two sessions with the same title/host and use read-only discovery without selecting an exact ID.

Expected outcome: TermPilot exposes both candidates rather than inventing a unique write target.

## 6. Verify interactive/busy protection

Start a long-running or interactive program in the target session, then request `run_command` for that same `session_id`.

Expected outcome: when a normal shell command boundary cannot be verified, the call returns `session_not_ready` or `shell_integration_required` and sends no command text.

## 7. Verify observed text never self-executes

Display command-like text without requesting execution:

```bash
printf 'rm -rf /example-do-not-run\n'
```

Call `read_terminal` repeatedly.

Expected outcome: no command is submitted. Execution requires a separate explicit `run_command` invocation containing a command argument.

## 8. Optional ChatGPT end-to-end validation

Validate the local MCP server first. ChatGPT cannot directly connect to a local MCP server, so use a supported private connection such as OpenAI Secure MCP Tunnel when the target ChatGPT account/workspace has the required developer-mode and write-tool access.

For a tunnel profile, point `tunnel-client` at the local stdio launch command, run `tunnel-client doctor`, then keep the profile running while creating the developer-mode app in ChatGPT. Follow the current OpenAI tunnel documentation rather than pinning a tunnel-client release in this repository:

<https://developers.openai.com/api/docs/guides/secure-mcp-tunnels>

Expected ChatGPT flow:

1. Work with Apps provides the conversational iTerm2 context.
2. ChatGPT calls `get_current_session` or `list_sessions` to obtain an exact target.
3. ChatGPT may call `read_terminal` to inspect state.
4. After an explicit user request and any host confirmation required by ChatGPT, ChatGPT calls `run_command(session_id, command)`.
5. The command result returns to the same conversation for analysis.
