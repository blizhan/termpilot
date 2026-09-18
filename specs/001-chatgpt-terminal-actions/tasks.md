# Tasks: ChatGPT Terminal Actions

**Input**: Design documents from `/specs/001-chatgpt-terminal-actions/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/mcp-tools.md`, `quickstart.md`

**Tests**: The feature specification does not require a TDD workflow, so this task list does not add separate automated-test tasks. Each user story keeps an explicit independent validation criterion, and the final phase runs the end-to-end scenarios in `quickstart.md`.

**Organization**: Tasks are grouped by user story so the P1 terminal-action flow can be delivered as the MVP before multi-session discovery and richer inspection are added.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches a different file and does not depend on an incomplete task.
- **[Story]**: Maps a task to a user story from `spec.md`.
- Every task names the concrete file or files it changes.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Turn the bootstrap repository into the Python package described by the implementation plan.

- [X] T001 Configure Python 3.13 project dependencies, the `termpilot` console entry point, and development tooling in `pyproject.toml`
- [X] T002 [P] Create package initializers in `src/termpilot/__init__.py`, `src/termpilot/adapters/__init__.py`, and `src/termpilot/services/__init__.py`

**Checkpoint**: The repository has an installable `src/termpilot` package and a declared executable entry point.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define the shared domain boundary and iTerm2/MCP process scaffolding used by every story.

**CRITICAL**: Complete this phase before implementing any user story.

- [X] T003 [P] Implement `TerminalSession`, `SessionMatch`, `TerminalSnapshot`, `CommandRequest`, `CommandResult`, status enums, and validation defaults from `data-model.md` in `src/termpilot/models.py`
- [X] T004 [P] Define the stable domain error codes from `contracts/mcp-tools.md` and exception-to-result helpers in `src/termpilot/errors.py`
- [X] T005 Implement the reusable iTerm2 connection lifecycle, exact `session_id` lookup, current-session lookup, Shell Integration metadata reads, and execution-readiness detection in `src/termpilot/adapters/iterm2.py`
- [X] T006 Create the MCP server factory, shared service wiring, structured error mapping, and empty tool-registration boundary in `src/termpilot/mcp_server.py`
- [X] T007 Implement the stdio process entry point with stderr-only operational logging and clean protocol stdout in `src/termpilot/main.py`

**Checkpoint**: TermPilot can start as an MCP stdio process, connect to iTerm2, represent sessions/results with stable models, and report adapter failures without any story-specific tools registered yet.

---

## Phase 3: User Story 1 - Act on the Current Terminal (Priority: P1) MVP

**Goal**: Let ChatGPT act on the currently focused existing iTerm2 session, wait for a normal shell command to finish, and return the correlated output without opening another terminal or SSH connection.

**Independent Test**: With one accessible iTerm2 shell focused, resolve it with `get_current_session`, execute a harmless command through `run_command`, and verify the command runs in that exact existing session and its output/exit status are returned. Repeat inside an already-open remote shell and verify no new SSH connection is created.

### Implementation for User Story 1

- [X] T008 [US1] Implement current-session resolution and exact-session revalidation for command actions in `src/termpilot/services/sessions.py`
- [X] T009 [US1] Add safe command submission primitives using iTerm2 transactions, broadcast suppression, prompt monitoring, command-end detection, and bounded command-output extraction in `src/termpilot/adapters/iterm2.py`
- [X] T010 [US1] Implement `run_command` orchestration with explicit `session_id`, non-empty command validation, readiness checks, request correlation, timeout semantics, exit-code capture, and no-reroute behavior in `src/termpilot/services/commands.py`
- [X] T011 [US1] Register the read-only `get_current_session` MCP tool with the contract response shape and `no_current_session` handling in `src/termpilot/mcp_server.py`
- [X] T012 [US1] Register the mutating `run_command` MCP tool with exact input bounds, write/destructive annotations, structured success/rejection responses, and no implicit command source in `src/termpilot/mcp_server.py`

**Checkpoint**: User Story 1 is usable as the MVP: current terminal → explicit command → same-session result.

---

## Phase 4: User Story 2 - Choose the Correct Session (Priority: P2)

**Goal**: Make multiple iTerm2 sessions distinguishable and ensure users/ChatGPT can select an exact target without TermPilot guessing among ambiguous candidates.

**Independent Test**: Open at least three distinguishable sessions, including two with overlapping labels. Verify `list_sessions` returns stable unique IDs and useful host/cwd/title metadata, then close a selected session and verify a later command to its old ID returns `session_not_found` and is never redirected elsewhere.

### Implementation for User Story 2

- [X] T013 [US2] Expand session inventory extraction with window/tab/session labels, host, username, cwd, current-session marker, availability, and readiness metadata in `src/termpilot/adapters/iterm2.py`
- [X] T014 [US2] Implement deterministic session inventory plus `unique`/`ambiguous`/`not_found` candidate matching semantics without fuzzy write targeting in `src/termpilot/services/sessions.py`
- [X] T015 [US2] Register the read-only `list_sessions` MCP tool with stable `session_id` output and nullable metadata behavior from `contracts/mcp-tools.md` in `src/termpilot/mcp_server.py`
- [X] T016 [US2] Enforce final exact-session existence checks immediately before command submission and map disappeared targets to `session_not_found` with zero fallback routing in `src/termpilot/services/commands.py`

**Checkpoint**: User Story 2 independently proves that multi-session discovery is useful while every mutation still targets one exact session ID or fails closed.

---

## Phase 5: User Story 3 - Inspect Before and After Acting (Priority: P3)

**Goal**: Let ChatGPT inspect bounded terminal content and readiness before/after actions without allowing observed command-like text to become executable input.

**Independent Test**: Read a selected session containing known text, execute a command that adds new output, read it again, and verify the new snapshot is associated with the same session. Display command-like text and repeatedly inspect it; verify no execution occurs unless a separate `run_command(session_id, command)` invocation is made.

### Implementation for User Story 3

- [X] T017 [US3] Add bounded screen/scrollback reading with `max_lines`, `max_chars`, truncation reporting, and session-lost handling in `src/termpilot/adapters/iterm2.py`
- [X] T018 [US3] Implement `TerminalSnapshot` creation, line/character bounds, capture timestamp, readiness propagation, and untrusted-observation handling in `src/termpilot/services/sessions.py`
- [X] T019 [US3] Register the read-only `read_terminal` MCP tool with exact-session lookup, bounded input validation, and structured snapshot output in `src/termpilot/mcp_server.py`
- [X] T020 [US3] Keep observation and mutation paths structurally separate so `TerminalSnapshot.content`, titles, history, and prior tool output can never be forwarded implicitly as `CommandRequest.command` in `src/termpilot/mcp_server.py`

**Checkpoint**: All three user stories work independently and together as inspect → select → act → inspect.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Finish the user-facing setup path, remove bootstrap leftovers, and validate the full design contract.

- [X] T021 [P] Replace the bootstrap README with installation, iTerm2 Python API/Shell Integration prerequisites, local MCP usage, four-tool reference, safety model, and optional ChatGPT Secure MCP Tunnel setup in `README.md`
- [X] T022 [P] Remove the obsolete bootstrap program in `hello.py` after the `termpilot` entry point in `src/termpilot/main.py` is working
- [X] T023 Reconcile implementation behavior and annotations against every tool/error definition in `specs/001-chatgpt-terminal-actions/contracts/mcp-tools.md`
- [X] T024 Run every applicable scenario in `specs/001-chatgpt-terminal-actions/quickstart.md`, fix implementation/documentation mismatches in the files referenced by the failing scenario, and leave the quickstart runnable end-to-end

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Starts immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 and blocks all user stories.
- **User Story 1 (Phase 3)**: Depends only on Phase 2 and is the MVP.
- **User Story 2 (Phase 4)**: Depends on Phase 2. It can be developed in parallel with US1 after the shared adapter/service boundaries exist, but T016 assumes the command service from T010 is present before final integration.
- **User Story 3 (Phase 5)**: Depends on Phase 2. It can be developed in parallel with US1/US2 after the shared adapter/service boundaries exist.
- **Polish (Phase 6)**: Depends on all desired user stories being implemented; T024 is the final end-to-end validation task.

### User Story Dependencies

```text
Phase 1 Setup
    ↓
Phase 2 Foundation
    ├──→ US1 Act on Current Terminal (MVP)
    ├──→ US2 Choose Correct Session
    └──→ US3 Inspect Before/After
              ↓
        Phase 6 Polish + Quickstart
```

- **US1** has no dependency on US2 or US3 for its single-current-session MVP path.
- **US2** reuses the shared session identity and command boundary; its multi-session inventory is independently testable.
- **US3** reuses exact session lookup but its read-only snapshot path is independently testable.

### Within Each User Story

- Adapter primitives before service orchestration when the service depends on a new iTerm2 capability.
- Service orchestration before MCP registration when the tool delegates to that service.
- Exact session validation always occurs again immediately before mutation.
- A story reaches its checkpoint only after its independent test criterion can be demonstrated.

### Parallel Opportunities

- T002 can run in parallel with T001.
- T003 and T004 can run in parallel after the package directories exist.
- After Phase 2, US1, US2, and US3 can be developed by separate workers, except that T016 integrates with the command service introduced by T010.
- T021 and T022 can run in parallel after the implementation entry point is stable.

---

## Parallel Example: User Story 1

After Phase 2, split work by file where dependencies permit:

```text
Worker A: T008 in src/termpilot/services/sessions.py
Worker B: T009 in src/termpilot/adapters/iterm2.py

Then:
T010 consumes T008 + T009
T011 and T012 register the completed service behavior in src/termpilot/mcp_server.py
```

## Parallel Example: User Story 2 and User Story 3

Once the shared adapter/service boundaries are stable:

```text
Worker A: T013-T015 for multi-session inventory (US2)
Worker B: T017-T019 for terminal snapshots (US3)

T016 follows T010 because it tightens the existing command service.
T020 follows the MCP tool boundaries created by T012 and T019.
```

---

## Implementation Strategy

### MVP First: User Story 1

1. Complete T001-T007 (Setup + Foundation).
2. Complete T008-T012 (US1).
3. Validate the US1 independent criterion against a local shell and an already-open remote shell.
4. Stop here for the first usable TermPilot release if desired.

### Incremental Delivery

1. **Foundation**: installable MCP stdio service with iTerm2 connectivity and stable domain models.
2. **US1**: current session + explicit command + correlated result.
3. **US2**: robust multi-session discovery and zero-fallback targeting.
4. **US3**: bounded terminal inspection and inspect/act/inspect workflow.
5. **Polish**: README, contract reconciliation, and full quickstart validation including optional ChatGPT tunnel integration when available.

### Scope Guardrails

- Do not add general keyboard/mouse automation or arbitrary TUI control in v1.
- Do not create a second SSH connection when acting on an existing remote-shell session.
- Do not accept fuzzy labels as the target of `run_command`; writes require an exact `session_id`.
- Do not infer executable commands from observed terminal text, history, titles, or prior tool output.
- Do not add public/LAN HTTP ingress as part of the terminal-control core; ChatGPT connectivity remains a separate transport concern.

---

## Notes

- `[P]` means the task changes a different file and has no dependency on another incomplete task at that point.
- `[US1]`, `[US2]`, and `[US3]` map directly to the stories in `spec.md`.
- `run_command` is the only mutating MCP tool in v1; all other tools are read-only.
- Timeout means TermPilot stops waiting; it must not report that the underlying shell command was cancelled.
- Commit after each task or coherent task group so story checkpoints remain reviewable.
