# ChatGPT Tunnel Integration Design

## Goal

Let a local TermPilot stdio MCP server be reachable from a ChatGPT developer-mode custom app through OpenAI Secure MCP Tunnel, without adding Electron, browser automation, or a public HTTP server.

## User-facing CLI

TermPilot keeps its current no-argument behavior: `termpilot` starts the stdio MCP server.

Add a `chatgpt` command group:

```text
termpilot chatgpt setup --tunnel-id tunnel_...
termpilot chatgpt status
termpilot chatgpt doctor
termpilot chatgpt disconnect
```

Common optional flags:

- `--alias` defaults to `termpilot`.
- `--tunnel-client` overrides the `tunnel-client` binary path.
- `--runtime-key-env` defaults to `CONTROL_PLANE_API_KEY`.

`setup` requires a tunnel ID that already exists in OpenAI Platform and a runtime API key present in the named environment variable. TermPilot never reads the key into generated command-line arguments and never writes the key value to disk. It passes `env:<NAME>` to `tunnel-client`.

## Architecture

`src/termpilot/main.py` remains the process entry point and dispatches either the existing MCP stdio server or the ChatGPT CLI.

`src/termpilot/chatgpt.py` owns the tunnel integration. It treats `tunnel-client` as the source of truth for tunnel runtime state and only shells out to documented native commands:

```text
tunnel-client runtimes connect --alias <alias> \
  --tunnel-id <id> \
  --runtime-api-key env:<NAME> \
  --mcp-command "<current-python> -m termpilot.main" \
  --json

tunnel-client runtimes status <alias> --json
tunnel-client runtimes stop <alias> --json
```

The managed runtime launches the same TermPilot package as a child stdio MCP server. There is no second TermPilot daemon and no TermPilot-owned PID file.

## Command behavior

### setup

1. Resolve `tunnel-client` from `--tunnel-client` or `PATH`.
2. Verify the configured runtime key environment variable is present without printing its value.
3. Run `runtimes connect` using the existing tunnel ID, stdio MCP command, and key reference.
4. Run `runtimes status --json` immediately after connect.
5. Return success only when the runtime status reports a live managed process and healthy tunnel state.
6. Print the ChatGPT developer-mode next step: create a custom app with Connection = Tunnel and select/paste the tunnel ID.

### status

Read `runtimes status --json` and print a concise summary containing alias, tunnel ID, runtime state, process/health/readiness state, and local UI URL when present.

### doctor

Perform local checks in order:

1. `tunnel-client` exists and can execute.
2. The runtime-key environment variable is configured.
3. The managed alias can be inspected with `runtimes status --json`.
4. Report process, healthy, and ready state from that payload.

Doctor never displays secrets and does not mutate tunnel state.

### disconnect

Run `tunnel-client runtimes stop <alias> --json`. This stops only the local managed runtime and leaves the remote OpenAI tunnel intact.

## Error handling

- Missing `tunnel-client`: fail with an install/help message.
- Missing runtime key env var: fail before invoking `runtimes connect`.
- Non-zero tunnel-client exit: propagate a concise stderr/stdout diagnostic and exit non-zero.
- Malformed JSON from commands where JSON is required: fail closed rather than guessing state.
- `status` on an absent alias: report it as unavailable and exit non-zero.
- Existing MCP stdio mode must not emit CLI text to stdout.

## Security constraints

- Never persist or print the runtime key value.
- Use an environment reference (`env:CONTROL_PLANE_API_KEY` by default) in generated tunnel-client configuration.
- Never create a public ingress endpoint.
- Never auto-create or publish the ChatGPT custom app through browser automation.
- Preserve the existing exact-session and Shell Integration command-safety checks.

## Testing

- Unit-test CLI dispatch so no-argument `termpilot` still starts stdio MCP.
- Unit-test setup argument construction and verify the key value never appears in subprocess arguments or output.
- Unit-test status JSON normalization and malformed JSON handling.
- Unit-test doctor success and missing-binary/missing-key failures.
- Unit-test disconnect uses the local runtime stop operation.
- Run the full pytest, Ruff, formatting, and `git diff --check` verification suite.

