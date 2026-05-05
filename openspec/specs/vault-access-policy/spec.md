# vault-access-policy Specification

## Purpose
TBD - created by archiving change add-discord-query-bot. Update Purpose after archive.
## Requirements
### Requirement: Vault notes MUST support explicit bot visibility metadata
The system MUST support Obsidian note metadata that explicitly classifies whether a note is player-visible, Storyteller-only, or excluded from bot export.

#### Scenario: Player-visible frontmatter
- **WHEN** a Markdown note contains Backet frontmatter marking it as player-visible
- **THEN** the access policy evaluator MUST classify that note as eligible for player bot indexes unless a higher-priority exclusion applies

#### Scenario: Storyteller-only frontmatter
- **WHEN** a Markdown note contains Backet frontmatter marking it as Storyteller-only
- **THEN** the access policy evaluator MUST exclude that note from player bot indexes while allowing it in Storyteller bot indexes when otherwise eligible

#### Scenario: Bot-excluded frontmatter
- **WHEN** a Markdown note contains Backet frontmatter marking it as bot-excluded
- **THEN** the access policy evaluator MUST exclude that note from all bot indexes even if the note remains available to normal local vault retrieval

#### Scenario: Invalid visibility value
- **WHEN** a Markdown note contains an unsupported bot visibility value
- **THEN** policy validation MUST fail with a deterministic error before bot export creates a deployable bundle

### Requirement: CLI commands MUST manage bot visibility metadata
The system MUST provide CLI commands for auditing, listing, setting, clearing, and bulk-updating bot visibility metadata so users do not need to hand-edit frontmatter for every note.

#### Scenario: Set one note visible to players
- **WHEN** a user runs the visibility set command for one Markdown note with player visibility and canon topic
- **THEN** the system MUST update that note's Backet frontmatter with explicit visibility and topic metadata

#### Scenario: Set a folder recursively
- **WHEN** a user runs the visibility set command for a folder with recursive mode
- **THEN** the system MUST update each eligible Markdown note under that folder with explicit visibility and topic metadata rather than creating an implicit path policy

#### Scenario: Dry-run recursive update
- **WHEN** a user runs a recursive visibility command in dry-run mode
- **THEN** the system MUST report which notes would change without modifying any files

#### Scenario: Clear visibility metadata
- **WHEN** a user runs the visibility clear command for a note
- **THEN** the system MUST remove bot visibility metadata from that note while preserving unrelated frontmatter

#### Scenario: Refuse unsafe target
- **WHEN** a visibility command targets an ignored, Backet-owned, non-Markdown, or ambiguous path
- **THEN** the system MUST refuse or require explicit confirmation according to the documented safety policy

### Requirement: Bot visibility MUST be default-deny for players
The system MUST classify notes without explicit bot visibility metadata as Storyteller-only for player bot export.

#### Scenario: Legacy note without metadata
- **WHEN** a Markdown note has no bot visibility metadata
- **THEN** the note MUST be excluded from player bot indexes by default

#### Scenario: Missing optional bot configuration
- **WHEN** a user runs bot export without optional bot configuration
- **THEN** the system MUST still apply the safe default that excludes unmarked notes from player indexes and MUST warn the user in human and JSON output

#### Scenario: Recursive command applies explicit metadata
- **WHEN** a user wants a whole folder to become player-visible
- **THEN** the supported path is a recursive visibility command that writes explicit metadata to each note, not a path policy that implicitly marks the folder

### Requirement: Policy precedence MUST be deterministic
The system MUST apply visibility policy in a documented and deterministic order.

#### Scenario: Built-in safety exclusion
- **WHEN** a note path is under a built-in excluded directory such as `.backet/`
- **THEN** the note MUST be excluded before any bot visibility rule is considered

#### Scenario: Explicit bot exclusion
- **WHEN** note metadata explicitly excludes a note from bot export
- **THEN** that exclusion MUST override player-visible or Storyteller-visible classifications

#### Scenario: Explicit visibility controls scope
- **WHEN** note metadata explicitly marks a note as player-visible or Storyteller-only
- **THEN** the system MUST apply that visibility consistently during access-scoped index creation

#### Scenario: Unmarked note fallback
- **WHEN** a note has no explicit bot visibility metadata
- **THEN** the system MUST classify it as Storyteller-only for bot export diagnostics and exclude it from player indexes

### Requirement: Bot topics MUST constrain command eligibility
The system MUST allow explicit note metadata to classify notes by bot topics such as canon, rules-summary, NPC, plotline, and stat block.

#### Scenario: Player canon query
- **WHEN** a player asks a canon command
- **THEN** the bot MUST retrieve only from player-visible notes whose metadata topics are eligible for the canon command

#### Scenario: Storyteller NPC query
- **WHEN** a Storyteller asks an NPC command
- **THEN** the bot MAY retrieve from Storyteller-visible notes explicitly tagged for NPC-related topics

#### Scenario: Topic missing
- **WHEN** a note has explicit visibility but no explicit topic
- **THEN** the system MUST apply a documented default topic behavior and report missing-topic counts in export diagnostics

#### Scenario: Invalid topic value
- **WHEN** a note contains an unsupported bot topic
- **THEN** policy validation MUST fail with a deterministic error before bot export creates a deployable bundle

### Requirement: Policy evaluation MUST be inspectable
The system MUST provide deterministic diagnostics explaining why notes are included in or excluded from each bot access scope.

#### Scenario: Human policy summary
- **WHEN** a user runs a bot policy, visibility audit, or export command without JSON output
- **THEN** the system MUST summarize counts by visibility, topic, explicit metadata, exclusion, missing topic, and unclassified default

#### Scenario: JSON policy details
- **WHEN** a user runs a bot policy, visibility audit, or export command with JSON output
- **THEN** the system MUST include per-note policy decisions, effective visibility, topics, metadata source, and exclusion reasons

#### Scenario: Player visibility audit
- **WHEN** a user requests a player visibility audit
- **THEN** the system MUST list all notes that would be exported to the player index so the Storyteller can review the player-visible corpus before deployment

