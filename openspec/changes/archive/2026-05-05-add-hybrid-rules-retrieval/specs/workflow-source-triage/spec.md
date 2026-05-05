## ADDED Requirements

### Requirement: Workflow skills MUST triage source needs before drafting

Workflow-oriented skills MUST distinguish whether a user request needs vault canon, ingested rules, external research, or a combination of those sources before drafting canon.

#### Scenario: Prompt combines rules, canon, and real-world facts

- **WHEN** a user asks for a canon-bearing recommendation that depends on local chronicle state, game rules, and real-world facts
- **THEN** the workflow skill MUST gather bounded vault context, retrieve relevant rules chunks, and identify the real-world facts that require external research before presenting a recommendation

#### Scenario: Prompt is adequately answered by local sources

- **WHEN** a user request is adequately grounded by existing vault canon and ingested rules
- **THEN** the workflow skill MUST NOT imply that web research is required

### Requirement: Workflow briefs MUST separate canon, rules, external research, and choices

Workflow-oriented skills MUST present source-separated working briefs before drafting or updating canonical vault notes.

#### Scenario: Present multi-source brief

- **WHEN** a workflow skill has gathered enough context to recommend a canon direction
- **THEN** it MUST separate the brief into `Canon says`, `Rules suggest`, `External research`, and `Open choices` when those lanes are relevant

#### Scenario: External source is unavailable or not yet researched

- **WHEN** a needed real-world fact is outside the local vault and rules corpus and has not been researched yet
- **THEN** the workflow skill MUST mark that source lane as unresolved instead of inventing a factual answer

### Requirement: Vault canon MUST remain authoritative over rules and external research

Workflow-oriented skills MUST treat human-authored vault notes as the canonical source for the chronicle, with rules and external research acting as support layers.

#### Scenario: External research conflicts with vault canon

- **WHEN** external research conflicts with existing human-authored vault canon
- **THEN** the workflow skill MUST preserve vault canon as authoritative and frame the difference as a chronicle choice or revision question

#### Scenario: Rules guidance conflicts with vault canon

- **WHEN** ingested rules guidance conflicts with existing human-authored vault canon
- **THEN** the workflow skill MUST preserve vault canon as authoritative unless the user explicitly chooses to revise it

### Requirement: External research MUST be cited and non-canonical until accepted

Workflow-oriented skills MUST treat online or external research as cited support material rather than committed chronicle truth.

#### Scenario: Use external research

- **WHEN** a workflow skill uses web or external research to fill facts outside the local corpus
- **THEN** it MUST cite those sources and keep them separate from canonical vault claims until the user approves canon changes

#### Scenario: Draft after external research

- **WHEN** the user approves a draft that incorporates external research
- **THEN** the workflow skill MUST write only the approved canon and avoid embedding uncited research notes unless explicitly requested

### Requirement: Skills MUST continue to delegate local retrieval to the CLI

Workflow-oriented skills MUST continue using Backet CLI commands for vault and rules retrieval rather than parsing vault files or rule stores directly.

#### Scenario: Gather local canon and rules

- **WHEN** a workflow skill needs local canon or ingested rules
- **THEN** it MUST use bounded `backet context` and `backet rules query` calls instead of loading whole vault sections or whole rulebooks into model context
