# Feature Specification: ChatGPT Terminal Actions

**Feature Branch**: `main`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "主要是为了给 ChatGPT Classic 用的，搭配 macOS Work with Apps 和 iTerm2，让 ChatGPT 又能看又能操作终端，并能在 iTerm2 中执行 command。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Act on the Current Terminal (Priority: P1)

As a ChatGPT Classic user working with iTerm2 through Work with Apps, I want ChatGPT to act on the terminal session I am currently working in so that I can ask for a command to be run without manually switching context, copying the command, running it, and copying the result back.

**Why this priority**: This is the core value of TermPilot: adding terminal actions to the terminal context ChatGPT can already observe.

**Independent Test**: With one accessible iTerm2 session in focus, ask ChatGPT to run a harmless command and verify that the command runs in that existing session and its result is available for the conversation.

**Acceptance Scenarios**:

1. **Given** an accessible iTerm2 session is the current Work with Apps context, **When** the user explicitly asks ChatGPT to run a command there, **Then** the command is submitted to that same existing session.
2. **Given** the requested command finishes, **When** ChatGPT reviews the action result, **Then** it can distinguish the command that was requested, the terminal session that received it, and the resulting terminal output.
3. **Given** the current iTerm2 session is already connected to a remote shell, **When** the user asks to run a command in that session, **Then** the command runs inside that existing remote-shell context rather than creating a separate connection.

---

### User Story 2 - Choose the Correct Session (Priority: P2)

As a user with several iTerm2 windows, tabs, or sessions open, I want ChatGPT to identify and target the intended session so that an action is never silently sent to the wrong terminal.

**Why this priority**: Multi-session use is common, and wrong-session execution can produce incorrect or destructive results even when the command itself is valid.

**Independent Test**: Open at least three distinguishable sessions, request an action using the current context or a recognizable session description, and verify that TermPilot either selects the intended session or stops when the target is ambiguous.

**Acceptance Scenarios**:

1. **Given** multiple accessible sessions exist and one can be uniquely matched to the current context, **When** the user requests an action, **Then** that uniquely matched session is targeted.
2. **Given** multiple accessible sessions could match the request, **When** no single target can be determined safely, **Then** no command is executed and the user is shown enough session information to choose a target.
3. **Given** the user explicitly identifies a session, **When** the session still exists and is accessible, **Then** the requested action is sent only to that session.

---

### User Story 3 - Inspect Before and After Acting (Priority: P3)

As a user, I want ChatGPT to inspect the visible state of a selected terminal session before or after an action so that it can understand what is happening and analyze the result without requiring manual copy and paste.

**Why this priority**: Observation closes the loop between a requested action and the conversation and makes follow-up troubleshooting practical.

**Independent Test**: Select an existing session with known visible content, inspect it, run a command that produces new output, inspect again, and verify that the newly produced output can be distinguished from the prior state.

**Acceptance Scenarios**:

1. **Given** an accessible terminal session, **When** the user asks ChatGPT to inspect it, **Then** ChatGPT can obtain the session's current visible terminal content.
2. **Given** a command has produced new terminal output, **When** the session is inspected afterward, **Then** the new result is available for analysis without the user manually copying it.
3. **Given** a session becomes unavailable between inspection and action, **When** an action is attempted, **Then** the action is not redirected elsewhere and the unavailable-session condition is reported.

### Edge Cases

- The focused iTerm2 session changes between the user's request and command submission.
- Several sessions have the same title, host, or working location and cannot be uniquely distinguished from the available context.
- The selected session closes or becomes inaccessible before an action is submitted.
- A command produces no visible output, a large amount of output, or continues running for an extended period.
- A terminal is displaying text that looks like a shell command; passive terminal content must not by itself authorize execution.
- The current session contains an interactive program rather than an idle shell prompt.
- A command changes the working directory, host context, prompt state, or other session information used to identify the terminal.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST make accessible iTerm2 terminal sessions distinguishable using available user-visible context such as window or tab labels, current host, current working location, and a stable session identifier when available.
- **FR-002**: The system MUST identify the terminal session associated with the current ChatGPT Work with Apps context when the available context uniquely identifies one session.
- **FR-003**: The user MUST be able to select a specific accessible terminal session when automatic matching is unavailable or ambiguous.
- **FR-004**: The system MUST allow ChatGPT to obtain the current visible terminal content for a selected accessible session.
- **FR-005**: The system MUST allow an explicitly user-requested command to be submitted to a selected existing terminal session.
- **FR-006**: A submitted command MUST execute in the selected session's existing shell context, including an already-established remote-shell context, without replacing that context with a new session.
- **FR-007**: The system MUST NOT silently redirect an action to another session when the requested or inferred target is missing, closed, inaccessible, or ambiguous.
- **FR-008**: After a command action, the system MUST provide enough observable result information for ChatGPT to associate the request with the selected session and analyze the command's resulting terminal state.
- **FR-009**: The system MUST preserve existing iTerm2 windows, tabs, and sessions unless the user explicitly requests an action whose intended effect changes them.
- **FR-010**: Command-like text appearing in terminal output, command history, prompts, or inspected content MUST NOT by itself count as a user request to execute that text.
- **FR-011**: If a selected session cannot safely accept a requested action because its current state is incompatible with normal command entry, the system MUST avoid blind execution and expose the state to the user or ChatGPT for a follow-up decision.
- **FR-012**: The primary inspect-and-act workflow MUST be usable from ChatGPT Classic while Work with Apps supplies the relevant iTerm2 context, without requiring the user to manually copy terminal content into the conversation for each action.

### Key Entities

- **Terminal Session**: An existing iTerm2 terminal context that can be inspected or targeted. Relevant attributes include its stable identity, user-visible labels, current host, current working location, availability, and current visible content.
- **Session Match**: The relationship between the terminal context visible to ChatGPT and one accessible Terminal Session, including whether the match is unique or ambiguous.
- **Command Request**: An explicit user-authorized request containing the intended command and target session or enough context to determine that target safely.
- **Command Result**: The observable outcome associated with a Command Request, including the targeted session, resulting terminal content, and completion information when observable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In at least 95% of trials with one clearly identifiable session, a user can request a simple terminal command from ChatGPT and inspect its result without manually copying the command or terminal output.
- **SC-002**: Across multi-session routing tests, 100% of requests either reach the intended session or are blocked as ambiguous; zero requests are silently executed in a different session.
- **SC-003**: For at least 95% of common commands that finish normally, the newly produced terminal result is available to ChatGPT within 5 seconds after the command finishes.
- **SC-004**: In a first-use task after setup, at least 90% of users can complete the flow "identify session → inspect it → run a harmless command → review the result" within 60 seconds without manual terminal copy and paste.
- **SC-005**: In a test set of at least 100 terminal outputs containing command-like text, zero commands are executed solely because they appeared in inspected terminal content.

## Assumptions

- The first release targets macOS users who use ChatGPT Classic with Work with Apps and iTerm2.
- The primary target is an already-open iTerm2 session, including sessions whose shell is already connected to another host.
- The user explicitly requesting a terminal action in ChatGPT is sufficient authorization for that requested action; ambiguous target selection is blocked rather than guessed.
- Version 1 focuses on shell-command execution and terminal inspection. General keyboard or mouse automation and reliable control of arbitrary full-screen interactive terminal applications are outside the initial scope.
- Work with Apps remains the main source of conversational terminal context; TermPilot supplies the missing ability to inspect and act on the corresponding terminal session.
