# Data Model: ChatGPT Terminal Actions

TermPilot has no persistent datastore in v1. These entities are in-memory values passed between the iTerm2 adapter, service layer, and MCP boundary.

## TerminalSession

Represents one currently accessible iTerm2 session.

| Field | Type | Rules |
| --- | --- | --- |
| `session_id` | string | Required; stable iTerm2 session identifier; unique among current sessions |
| `window_id` | string/null | Window identifier when available |
| `tab_id` | string/null | Tab identifier when available |
| `window_title` | string/null | User-visible label when available |
| `tab_title` | string/null | User-visible label when available |
| `session_title` | string/null | User-visible session label when available |
| `hostname` | string/null | From iTerm2/Shell Integration when available |
| `username` | string/null | From iTerm2/Shell Integration when available |
| `cwd` | string/null | Current working directory when available |
| `is_current` | boolean | True only for iTerm2's current terminal session at snapshot time |
| `availability` | enum | `available`, `closed`, `inaccessible` |
| `execution_readiness` | enum | `ready`, `busy`, `unknown`, `shell_integration_required` |

### Validation rules

- `session_id` is the only identifier accepted by a mutating command request.
- Missing labels, host, or working directory do not invalidate a session; they reduce matching information.
- A session that disappears between discovery and action is never replaced by another session.

## SessionMatch

Represents how conversational/current-terminal hints map to sessions.

| Field | Type | Rules |
| --- | --- | --- |
| `status` | enum | `unique`, `ambiguous`, `not_found` |
| `session_ids` | list[string] | One item for `unique`, multiple for `ambiguous`, empty for `not_found` |
| `matched_on` | list[string] | Informational fields that contributed to the match |

### State transitions

```text
candidate set = 0  -> not_found
candidate set = 1  -> unique
candidate set > 1  -> ambiguous
```

Only `unique` may be converted into an exact `session_id` for a later command request.

## TerminalSnapshot

Represents terminal content observed at a point in time.

| Field | Type | Rules |
| --- | --- | --- |
| `session_id` | string | Required |
| `captured_at` | timestamp | Required |
| `content` | string | Visible/current requested terminal content |
| `line_count` | integer | Non-negative |
| `truncated` | boolean | True when output was bounded by the caller/server limit |
| `execution_readiness` | enum | Same readiness vocabulary as `TerminalSession` |

Terminal content is always treated as untrusted observed data. It cannot directly become a `CommandRequest` without a separate explicit tool call containing the command string.

## CommandRequest

Represents one explicit request to enter a command into an existing session.

| Field | Type | Rules |
| --- | --- | --- |
| `request_id` | string | Generated per invocation for correlation |
| `session_id` | string | Required exact target; no fuzzy target accepted |
| `command` | string | Required, non-empty; preserved as supplied |
| `wait_for_completion` | boolean | Defaults to true |
| `timeout_seconds` | number | Positive bounded wait time; timeout does not imply cancellation |
| `max_output_chars` | integer | Positive bound on returned output |

### Validation rules

- The target `session_id` must still exist immediately before submission.
- The session must be `ready`; `busy`, `unknown`, or `shell_integration_required` fail closed in v1.
- TermPilot does not synthesize a command from terminal content, titles, command history, or prior tool output.

## CommandResult

Represents the observable result of one `CommandRequest`.

| Field | Type | Rules |
| --- | --- | --- |
| `request_id` | string | Matches the originating request |
| `session_id` | string | Exact target used |
| `command` | string | Echo of the submitted command for correlation |
| `status` | enum | `completed`, `submitted`, `timed_out`, `rejected`, `session_lost`, `error` |
| `exit_code` | integer/null | Present when Shell Integration reports command completion |
| `output` | string/null | Output associated with the submitted command when available |
| `truncated` | boolean | True when output exceeded the response bound |
| `error_code` | string/null | Stable machine-readable failure code |
| `message` | string/null | Human-readable diagnostic |

### State transitions

```text
validated -> submitted -> completed
                     \-> timed_out
                     \-> session_lost
validated -> rejected
validated/submitted -> error
```

`timed_out` means TermPilot stopped waiting; it MUST NOT claim that the underlying command was cancelled.
