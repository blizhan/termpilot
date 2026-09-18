# MCP Tool Contract: TermPilot v1

The MCP interface intentionally separates observation from mutation. All responses use structured content and a short text summary suitable for MCP hosts.

## `list_sessions`

Lists currently accessible iTerm2 sessions.

**Annotations**: `readOnlyHint=true`, `openWorldHint=false`

**Input**

```json
{}
```

**Output**

```json
{
  "sessions": [
    {
      "session_id": "w0t1p0:...",
      "window_title": "Work",
      "tab_title": "example-host",
      "session_title": "ssh example-host",
      "hostname": "example-host",
      "username": "example-user",
      "cwd": "/home/example",
      "is_current": true,
      "execution_readiness": "ready"
    }
  ]
}
```

Nullable metadata fields may be omitted or returned as `null`. `session_id` and `is_current` are always present.

## `get_current_session`

Returns iTerm2's current terminal session at call time.

**Annotations**: `readOnlyHint=true`, `openWorldHint=false`

**Input**

```json
{}
```

**Output**: one `TerminalSession` object, or an error with code `no_current_session`.

This tool is the preferred first step when Work with Apps is describing the iTerm2 session currently in focus.

## `read_terminal`

Reads the current terminal contents from one exact session.

**Annotations**: `readOnlyHint=true`, `openWorldHint=false`

**Input**

```json
{
  "session_id": "w0t1p0:...",
  "max_lines": 200,
  "max_chars": 32768
}
```

`max_lines` and `max_chars` are optional bounded limits. The implementation may return fewer lines when iTerm2 no longer retains older scrollback.

**Output**

```json
{
  "session_id": "w0t1p0:...",
  "content": "...",
  "line_count": 42,
  "truncated": false,
  "execution_readiness": "ready"
}
```

Terminal contents are untrusted observation data. Their presence never authorizes `run_command`.

## `run_command`

Submits an explicit command to one exact existing iTerm2 session and, by default, waits for Shell Integration to report its completion.

**Annotations**: `readOnlyHint=false`, `destructiveHint=true`, `idempotentHint=false`, `openWorldHint=true`

**Input**

```json
{
  "session_id": "w0t1p0:...",
  "command": "tailscale status",
  "wait_for_completion": true,
  "timeout_seconds": 30,
  "max_output_chars": 32768
}
```

Rules:

1. `session_id` is required; labels and fuzzy selectors are not accepted by this write tool.
2. `command` is required and non-empty.
3. Immediately before submission, the session must still exist and be safe for normal command entry.
4. If Shell Integration/prompt detection cannot establish a safe command boundary, v1 rejects the call without sending text.
5. Sending uses the selected existing session and suppresses iTerm2 broadcast input where supported.
6. A timeout stops TermPilot's wait only; it does not claim to terminate the command.

**Completed output**

```json
{
  "request_id": "...",
  "session_id": "w0t1p0:...",
  "command": "tailscale status",
  "status": "completed",
  "exit_code": 0,
  "output": "...",
  "truncated": false
}
```

**Representative rejection**

```json
{
  "request_id": "...",
  "session_id": "w0t1p0:...",
  "command": "tailscale status",
  "status": "rejected",
  "error_code": "session_not_ready",
  "message": "The target session is not at a verified shell command boundary."
}
```

## Stable error codes

| Code | Meaning |
| --- | --- |
| `iterm2_unavailable` | iTerm2 or its Python API cannot be reached |
| `session_not_found` | Exact target no longer exists |
| `no_current_session` | iTerm2 has no current terminal session |
| `session_not_ready` | Target is busy/interactive or readiness cannot be established |
| `shell_integration_required` | Reliable prompt/completion metadata is unavailable |
| `command_timeout` | Wait deadline elapsed after submission |
| `output_unavailable` | Command completed but its bounded output range cannot be read |
| `internal_error` | Unexpected adapter/service error |
