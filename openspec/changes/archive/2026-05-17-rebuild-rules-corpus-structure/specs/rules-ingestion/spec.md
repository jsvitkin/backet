## ADDED Requirements

### Requirement: Section-aware rule blocks
Rules ingestion SHALL derive and persist section-aware rule blocks from extracted rulebook text.

#### Scenario: Rule block stored
- **WHEN** a rulebook page contains a named mechanic, discipline power, ritual, table, or rules subsection
- **THEN** ingestion stores a rule block with stable block ID, book metadata, source page range, heading path, block kind, clean text, and extraction quality metadata

#### Scenario: Page furniture excluded from block text
- **WHEN** repeated book headers, page numbers, chapter running heads, or decorative page furniture surround a rule block
- **THEN** the stored clean text excludes or flags that furniture so answer retrieval can center on the rule text

#### Scenario: Compatibility fields retained
- **WHEN** existing rules query callers request source metadata
- **THEN** the system continues to provide compatible book, page, section label, excerpt, and source type fields derived from the structured block

### Requirement: Structured tables and lists
Rules ingestion SHALL preserve rule-relevant table and list structure in block metadata and clean text.

#### Scenario: Trait cost table ingested
- **WHEN** a rulebook page contains a trait-cost or similar rule table
- **THEN** ingestion preserves row labels, values, and table context sufficiently for retrieval and answer synthesis to identify the applicable cost

#### Scenario: Discipline power stat block ingested
- **WHEN** a discipline power contains cost, dice pool, system, duration, prerequisite, or amalgam fields
- **THEN** ingestion keeps those labels associated with the named power block

### Requirement: Structure metadata rebuild
Rules indexing SHALL rebuild rule-block structure metadata from stored text when source PDFs are unavailable and stored text is sufficient.

#### Scenario: Stored text is sufficient
- **WHEN** a rules store has readable chunk text but stale or missing rule-block metadata
- **THEN** `backet rules index --full` rebuilds structure metadata without requiring the source PDF

#### Scenario: Stored text is insufficient
- **WHEN** stored text is empty, art-heavy, severely OCR-corrupted, or lacks source linkage needed to create reliable blocks
- **THEN** the indexing command reports the book as a reingest candidate rather than silently producing low-confidence blocks

### Requirement: Block schema versioning
Rules ingestion SHALL version rule-block metadata separately from source extraction so later retrieval changes can detect stale structure.

#### Scenario: Metadata schema changes
- **WHEN** the rule-block schema version changes
- **THEN** audit and indexing diagnostics identify stale blocks and provide the command needed to refresh them
