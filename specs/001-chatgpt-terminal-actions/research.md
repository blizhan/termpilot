# Phase 0 Research: ChatGPT Terminal Actions

## Decision: Use iTerm2's Python API as the terminal control boundary

**Decision**: Use the official iTerm2 Python API for session discovery, screen reads, session variables, and text submission.

**Rationale**: The current API provides stable session identifiers, `async_get_screen_contents()`, session variables, and `async_send_text()`. It therefore operates directly on the already-open session the user is viewing and avoids creating a second shell/SSH connection or simulating keyboard input through AppleScript.

**Alternatives considered**:

- AppleScript/System Events: rejected because it targets UI focus rather than a stable session identity and makes wrong-session execution harder to prevent.
- Opening a fresh subprocess or SSH connection: rejected because it loses the existing terminal's shell state, current directory, environment, remote connection, and interactive history.
- Parsing the macOS accessibility tree: useful for observation but unnecessary for v1 control because iTerm2 already exposes a structured API.

**Sources**: <https://iterm2.com/python-api/> and <https://iterm2.com/python-api/session.html>

## Decision: Require Shell Integration for reliable command execution

**Decision**: `run_command` requires prompt metadata from iTerm2 Shell Integration (or equivalent prompt-detection triggers). Sessions without it remain listable/readable but are not eligible for blind command submission in v1.

**Rationale**: iTerm2 Shell Integration reports prompt boundaries, command start/end, exit status, host, and working directory. iTerm2's own documented “Run a Command and Return its Output” example combines a transaction, `async_send_text`, `PromptMonitor(COMMAND_END)`, and prompt output ranges to associate one submitted command with its output. That gives TermPilot a much stronger completion boundary than screen-diff heuristics.

**Alternatives considered**:

- Sleep and read the screen: rejected because long-running commands, silent commands, progress UIs, and prompt redraws make timing unreliable.
- Append a shell sentinel such as `; echo ...`: rejected for v1 because modifying arbitrary user command text changes shell semantics and behaves poorly around multi-line commands, shell syntax, and remote/interactive contexts.
- Always send text even when readiness is unknown: rejected because it violates the requirement to avoid blind execution in an interactive program or busy shell.

**Sources**: <https://iterm2.com/documentation-shell-integration.html>, <https://iterm2.com/python-api/prompt.html>, and <https://iterm2.com/python-api/examples/runcommand.html>

## Decision: Separate session observation from command mutation

**Decision**: Expose four small MCP tools: `list_sessions`, `get_current_session`, `read_terminal`, and `run_command`. Read tools may locate the current session; the mutating `run_command` call always receives a concrete `session_id` and a concrete `command`.

**Rationale**: The split makes the model's workflow inspectable and prevents terminal output from becoming an implicit command source. It also gives the MCP host a clear distinction between read-only operations and an operation that changes the user's environment.

**Alternatives considered**:

- One `terminal(action, ...)` super-tool: rejected because it weakens schemas, permissions, and auditability.
- Let `run_command` accept only fuzzy labels such as hostname/title: rejected because ambiguous labels are common and a write tool should not guess its target.
- Automatically execute text found in Work with Apps or terminal output: rejected because observation is untrusted data and does not constitute an execution request.

## Decision: Use MCP tool annotations as metadata, with enforcement in TermPilot

**Decision**: Mark inventory/read tools as read-only and `run_command` as non-read-only and potentially destructive. Enforce targeting/readiness rules inside TermPilot rather than relying on annotations for safety.

**Rationale**: MCP annotations are useful hints for host confirmation UX, but the MCP specification treats them as hints rather than enforcement. TermPilot therefore validates session existence, exact identity, and execution readiness before sending text.

**Alternatives considered**:

- Rely on ChatGPT confirmation alone: rejected because the core should remain safe when called by another MCP host.
- Maintain a hardcoded shell-command allowlist: rejected for v1 because the product's purpose is general terminal action; target validation and explicit user/tool invocation are the primary boundary. A policy plugin can be added later if needed.

**Source**: <https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/>

## Decision: Use MCP stdio locally and keep ChatGPT connectivity as a transport concern

**Decision**: Implement the MCP server so it can run over stdio for local development and automated contract tests. For ChatGPT, connect the same local server through a supported private MCP path such as Secure MCP Tunnel rather than building public ingress into TermPilot v1.

**Rationale**: The MCP Python SDK supports stdio and HTTP transports. Current ChatGPT custom-app documentation states that ChatGPT cannot connect directly to a local MCP server; Secure MCP Tunnel can forward requests to a private stdio or HTTP server without opening inbound ports. Keeping this outside the iTerm2 adapter avoids coupling core behavior to ChatGPT deployment mechanics.

**Alternatives considered**:

- Bind an unauthenticated HTTP server to the LAN/public internet: rejected because it creates unnecessary remote command exposure.
- Make ChatGPT tunneling part of the terminal-control core: rejected because local development, Codex, MCP Inspector, and future hosts should use the same core without ChatGPT-specific code.
- Stdio only forever: rejected because ChatGPT requires a remotely reachable/tunneled MCP path for custom app access.

**Sources**: <https://py.sdk.modelcontextprotocol.io/> and <https://developers.openai.com/api/docs/guides/secure-mcp-tunnels>

## Decision: Treat ChatGPT write availability as an integration prerequisite

**Decision**: TermPilot's core implementation does not assume that every ChatGPT account can invoke mutating MCP tools. The quickstart validates the core locally first, then treats ChatGPT developer-mode/write-tool availability as an external prerequisite for the final end-to-end path.

**Rationale**: Current ChatGPT developer-mode documentation differentiates plans/workspaces and states that full MCP write support is not universally available. This is a product capability constraint, not a reason to weaken or duplicate the TermPilot core.

**Alternatives considered**:

- Build around an unsupported local-only ChatGPT connection: rejected because it would make the documented end-to-end path depend on behavior ChatGPT does not expose.
- Block all implementation until the ChatGPT entitlement exists: rejected because session discovery, inspection, command execution, MCP contracts, and local validation are independently useful and testable.

**Source**: <https://help.openai.com/en/articles/12584461-developer-mode-and-custom-apps-in-chatgpt>
