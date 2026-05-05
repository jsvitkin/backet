## ADDED Requirements

### Requirement: Workflow skills MUST follow an explore-first authoring loop

The system MUST make workflow-oriented authoring skills begin in discussion mode, inspect existing context first, and require explicit user approval before creating or updating canonical vault notes.

#### Scenario: Start a workflow discussion

- **WHEN** a user invokes a workflow authoring skill for a canon-bearing task
- **THEN** the skill MUST summarize current context, identify the next decision surface, and remain in discussion mode until the user asks it to draft or update canon

### Requirement: Workflow skills MUST present a structured working brief before drafting

Before proposing concrete prose, the system MUST present a working brief that distinguishes existing canon, bounded rules guidance, and unresolved choices.

#### Scenario: Present a briefing frame

- **WHEN** a workflow skill has gathered enough context to move from discovery into recommendation
- **THEN** it MUST present a brief that separates at least `Canon says`, `Rules suggest`, and `Open choices`

### Requirement: Workflow skills MUST use bounded vault and rules context

Workflow skills MUST ground themselves in bounded vault retrieval and, when relevant to the topic, bounded rules retrieval from ingested rulebooks rather than implying whole-vault or whole-book prompt loading.

#### Scenario: Rules-sensitive workflow topic

- **WHEN** the workflow topic is mechanics-sensitive, lore-sensitive, or materially underdefined in the vault
- **THEN** the skill MUST retrieve bounded canon context and relevant rule chunks with source metadata before making recommendations

#### Scenario: Canon-first workflow topic

- **WHEN** the workflow topic is adequately defined by existing vault canon and does not require rules-sensitive guidance
- **THEN** the skill MUST be allowed to proceed from vault context alone without forcing an unnecessary rules lookup

### Requirement: Vault canon MUST remain authoritative over derived memory and baseline rules

The system MUST treat human-authored vault notes as the canonical source of truth, with derived memory and rulebook retrieval acting as support layers rather than silent override sources.

#### Scenario: Existing canon diverges from retrieved rules

- **WHEN** retrieved rule or lore guidance conflicts with existing vault canon
- **THEN** the workflow skill MUST preserve the vault note as authoritative and frame the difference as a deliberate chronicle choice or an explicit revision question

### Requirement: Workflow skills MUST surface unresolved rules ambiguity instead of guessing

When rules retrieval cannot determine a single authoritative specific source, the system MUST surface the ambiguity to the user instead of drafting from an unresolved conflict.

#### Scenario: Conflicting supplement sources

- **WHEN** bounded rules retrieval returns multiple supplement-specific matches with unresolved precedence
- **THEN** the workflow skill MUST ask for narrower filters or user choice before drafting canon that depends on those rules
