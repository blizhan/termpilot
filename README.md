# TermPilot

[English](README.md) | [简体中文](README.zh-CN.md)

TermPilot gives ChatGPT a structured way to inspect and act on the iTerm2
sessions that are already open on a Mac. It is designed for ChatGPT Classic
with macOS Work with Apps: Work with Apps provides the terminal context, and
TermPilot provides four MCP tools for session discovery, bounded inspection,
and explicit command execution.

## Prerequisites

- macOS with iTerm2 running.
- Python 3.13 and [uv](https://docs.astral.sh/uv/).
- iTerm2's Python API enabled. See the [iTerm2 Python API
  documentation](https://iterm2.com/python-api/).
- iTerm2 [Shell Integration](https://iterm2.com/documentation-shell-integration.html)
  installed in each shell where `run_command` will be used. Shell Integration
  provides the prompt state and command completion metadata needed for safe
  execution.

## Install and run

From the repository root:

```bash
uv sync
uv run termpilot
```

`termpilot` speaks MCP over stdio. It keeps stdout reserved for MCP messages;
diagnostic logging is sent to stderr. A local MCP client can use a configuration
like this, replacing the directory with the absolute path of this checkout:

```json
{
  "mcpServers": {
    "termpilot": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/termpilot",
        "termpilot"
      ]
    }
  }
}
```

## Tools

| Tool | Purpose | Access |
| --- | --- | --- |
| `list_sessions` | List accessible sessions and their IDs, labels, host, user, cwd, current marker, and readiness | Read-only |
| `get_current_session` | Resolve the iTerm2 session currently in focus | Read-only |
| `read_terminal` | Read bounded visible content from one exact `session_id` | Read-only |
| `run_command` | Send an explicitly supplied command to one exact `session_id` and optionally wait for completion | Mutating |

The normal flow is:

1. Call `get_current_session` or `list_sessions`.
2. Use the returned exact `session_id` with `read_terminal` when inspection is useful.
3. Call `run_command` only after the user has explicitly requested the command.
4. Review the correlated session ID, command, status, exit code, and bounded output.

## Safety behavior

- `run_command` requires an exact `session_id`; labels and fuzzy matches are
  never used as a write target.
- A missing, closed, inaccessible, or ambiguous target fails closed and is
  never redirected to another session.
- Terminal content, command history, titles, and prior tool output are
  observation data. They are never copied into a command request implicitly.
- Commands are sent through the existing iTerm2 session with broadcast input
  suppressed where the API supports it. TermPilot does not create a new shell,
  window, or SSH connection.
- Command execution requires a verified normal shell prompt. Busy or
  interactive sessions are rejected without sending text.
- A timeout stops waiting for the result; it does not claim that the shell
  command was cancelled.

## Validation

Run the automated checks with:

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

The live test is opt-in and only checks a running iTerm2 instance's session
inventory:

```bash
TERMPILOT_LIVE_ITERM2=1 uv run pytest tests/integration/test_iterm2_live.py -q
```

For the complete manual inspect → act → inspect scenarios, see
[`specs/001-chatgpt-terminal-actions/quickstart.md`](specs/001-chatgpt-terminal-actions/quickstart.md).

## ChatGPT connection

ChatGPT cannot use a local stdio process directly. TermPilot can connect the
same MCP server through [OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
using the official `tunnel-client` managed runtime.

### 1. Install `tunnel-client`

On macOS with Homebrew:

```bash
brew install openai/tools/tunnel-client
tunnel-client --version
```

TermPilot does not bundle or pin `tunnel-client`; it uses the binary available
on `PATH`.

### 2. Create a tunnel and runtime key

Open the OpenAI Platform pages exposed by `tunnel-client help quickstart`:

- [Tunnels management](https://platform.openai.com/settings/organization/tunnels):
  create a tunnel and copy its `tunnel_...` ID.
- [Runtime API keys](https://platform.openai.com/settings/organization/api-keys):
  create the key used by the long-running tunnel runtime. The principal that
  creates/uses it needs **Tunnels Read + Use** for the target tunnel.
- [Admin API keys](https://platform.openai.com/settings/organization/admin-keys)
  are only needed for tunnel CRUD through `tunnel-client admin ...`; do not use
  an admin key as the long-running runtime key.

If you prefer to create the tunnel from the CLI, configure an admin key first
and use the native `tunnel-client` tunnel-management command (at least one
organization or workspace scope is required):

```bash
export OPENAI_ADMIN_KEY="sk-admin-..."
tunnel-client admin tunnels create \
  --name "termpilot" \
  --description "TermPilot local iTerm2 MCP" \
  --organization-id org_...
```

You can use `--workspace-id ws_...` instead of or together with
`--organization-id`. Copy the returned `tunnel_...` ID. Once the tunnel exists,
TermPilot only needs that ID and a runtime API key; the admin key is no longer
needed by the runtime.

### 3. Store and load the runtime key

The recommended local setup is a repository `.env` file:

```dotenv
CONTROL_PLANE_API_KEY=sk-...
```

`.env` is ignored by this repository, but neither TermPilot nor
`tunnel-client` automatically loads it. Load it into the current shell before
`setup`, `status`, or `doctor`:

```bash
set -a
source .env
set +a
```

Alternatively, export it directly:

```bash
export CONTROL_PLANE_API_KEY="sk-..."
```

TermPilot stores only the reference `env:CONTROL_PLANE_API_KEY` in the generated
tunnel profile; it does not put the secret value into the command line or print
it.

### 4. Start the managed runtime

Connect TermPilot to the existing tunnel:

```bash
uv run termpilot chatgpt setup --tunnel-id tunnel_0123456789abcdef0123456789abcdef
```

`setup` launches a long-running managed `tunnel-client` process, which in turn
starts this checkout's `python -m termpilot.main` stdio MCP server. A healthy
setup reports `Process running: yes`, `Healthy: yes`, and `Ready: yes`.

Inspect or troubleshoot the connection with:

```bash
uv run termpilot chatgpt status
uv run termpilot chatgpt doctor
```

After a reboot or after stopping the managed runtime, load `.env` again and run
the same `setup --tunnel-id ...` command. The existing tunnel is reused.

To stop the local runtime without deleting the remote tunnel:

```bash
uv run termpilot chatgpt disconnect
```

### 5. Add TermPilot to ChatGPT Classic

After `setup` succeeds:

1. Open **ChatGPT Settings → Plugins** (or
   [ChatGPT Plugins](https://chatgpt.com/plugins)).
2. Create a new developer-mode plugin/app, for example named `termpilot`.
3. Under **Connection**, choose **Tunnel**, not **Server URL**.
4. Select the tunnel or paste its `tunnel_id`.
5. Save the plugin and allow the TermPilot tools you want ChatGPT to use.

The tunnel runtime must remain running while ChatGPT discovers or calls the MCP
tools. You do not need OAuth for the local TermPilot MCP server when using the
Secure MCP Tunnel connection.

## Frequently Asked Questions

### `tunnel-client is not installed or is not available on PATH`

Install the supported client and verify it is visible:

```bash
brew install openai/tools/tunnel-client
which tunnel-client
tunnel-client --version
```

### I put `CONTROL_PLANE_API_KEY` in `.env`, but TermPilot says it is missing

Creating `.env` does not export its variables. Load it into each shell/process
that starts or diagnoses the tunnel runtime:

```bash
set -a
source .env
set +a
uv run termpilot chatgpt setup --tunnel-id tunnel_...
```

### What is the difference between `CONTROL_PLANE_API_KEY` and `OPENAI_ADMIN_KEY`?

`CONTROL_PLANE_API_KEY` is the runtime key used by the long-running tunnel
daemon. It needs **Tunnels Read + Use**. `OPENAI_ADMIN_KEY` is for administrative
tunnel CRUD such as `tunnel-client admin tunnels create`; the TermPilot runtime
does not need it when attaching to an existing tunnel.

### Why does a manual `tunnel-client runtimes connect` complain about a missing key?

The generated profile contains an environment reference such as
`env:CONTROL_PLANE_API_KEY`. The process starting that profile must therefore
have the variable exported. Prefer `uv run termpilot chatgpt setup ...`, which
supplies the correct runtime-key reference and MCP command consistently.

### ChatGPT sends a command, but TermPilot says `iTerm2 is not running or its Python API is disabled`

First verify iTerm2 itself:

1. Open **iTerm2 → Settings → General → Magic**.
2. Enable **Python API**.
3. Set it to **Allow all apps to connect** (or explicitly allow the process that
   runs TermPilot).

Then test the iTerm2 API directly from the TermPilot environment:

```bash
uv run python - <<'PY'
import asyncio
import iterm2

async def main():
    connection = await iterm2.Connection.async_create()
    app = await iterm2.async_get_app(connection)
    print([s.session_id for w in app.windows for t in w.tabs for s in t.sessions])

asyncio.run(main())
PY
```

If this prints session IDs, the iTerm2 API is working and the problem is in the
TermPilot/iTerm2 boundary rather than the ChatGPT tunnel.

### Why did an older TermPilot build fail even though the direct iTerm2 test worked?

An earlier adapter called `iterm2.async_get_app(..., create_if_needed=False)`.
With iTerm2 3.6.x this can return `None` even while iTerm2 is already running.
TermPilot now allows the SDK to create its `App` wrapper, matching the working
`iterm2.async_get_app(connection)` call.

### The tunnel log says `dispatcher forwarded command to MCP server`, but ChatGPT still gets an iTerm2 error

That log line proves the path **ChatGPT → Secure MCP Tunnel → TermPilot MCP** is
working. Debug the local **TermPilot → iTerm2 Python API** boundary next instead
of recreating the ChatGPT plugin or tunnel.

### ChatGPT's plugin dialog shows `Server URL` and `Tunnel`. Which one should I use?

Choose **Tunnel** and select/paste the `tunnel_id`. `Server URL` is for a
network-reachable HTTP/SSE MCP server and is not the TermPilot setup described
here.

### `Codex detected without Tunnel MCP plugin` appears in the tunnel-client log

This message is about optional Codex integration. It does not prevent the
ChatGPT Classic developer-mode plugin from using the TermPilot tunnel.

### How do I know which layer is broken?

Use this order:

1. `uv run termpilot chatgpt status` → runtime should be running, healthy, and ready.
2. Tunnel log contains `dispatcher forwarded command to MCP server` → ChatGPT to
   TermPilot transport is working.
3. Run the direct iTerm2 Python snippet above → local iTerm2 API is working.
4. Finally test `list_sessions` from the ChatGPT TermPilot plugin.
