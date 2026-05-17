## ADDED Requirements

### Requirement: Retrieval uses structured rule blocks
Hybrid rules retrieval SHALL prefer structured rule blocks over raw page-like chunks when current block metadata is available.

#### Scenario: Structured block available
- **WHEN** a rules query matches a block with current structure metadata
- **THEN** selected evidence references the block ID, heading path, block kind, page range, and clean source window

#### Scenario: Structured block unavailable
- **WHEN** a rules query runs against an older store without current block metadata
- **THEN** retrieval falls back to existing chunk behavior and reports the corpus structure blocker in diagnostics

### Requirement: Source windows honor block boundaries
Hybrid rules retrieval SHALL create excerpts and evidence windows centered on matched rule block content.

#### Scenario: Matched rule starts mid-page
- **WHEN** the matching rule block starts after page furniture or another unrelated rule
- **THEN** the returned excerpt starts near the matched block rather than at the raw page start

#### Scenario: Adjacent block needed
- **WHEN** a named heading block and its system text are split across adjacent structured blocks
- **THEN** retrieval may include a bounded neighbor block and reports the expansion reason
