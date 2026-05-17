# rules-rule-units Specification

## Purpose
TBD - created by archiving change derive-rules-rule-units. Update Purpose after archive.
## Requirements
### Requirement: Rule units MUST be derived from ingested rules evidence
The system MUST derive structured rule units from ingested rule chunks and source metadata without requiring source PDFs when stored chunk text is sufficient.

#### Scenario: Derive units from stored chunks
- **WHEN** a user or agent refreshes rules indexes for a vault with stored rules chunks
- **THEN** the system MUST derive rule units from those chunks and persist them as rebuildable per-vault rules state

#### Scenario: Source PDFs unavailable
- **WHEN** stored chunk text and metadata are sufficient to derive rule units but the original source PDF path is unavailable
- **THEN** the system MUST derive rule units without requiring the PDF to be copied into the vault

### Requirement: Rule units MUST preserve source traceability
Each rule unit MUST retain the source book, page range, heading path, source chunk IDs, source content hash, and schema version needed to audit or rebuild the unit.

#### Scenario: Inspect a rule unit
- **WHEN** a user or agent inspects a derived rule unit in machine-readable mode
- **THEN** the output MUST identify the source book, page range, heading path, source chunk IDs, unit schema version, and source content hash

#### Scenario: Source text changes
- **WHEN** a source chunk hash no longer matches the hash stored on a rule unit
- **THEN** diagnostics MUST mark the rule unit stale and provide a refresh path

### Requirement: Rule units MUST classify mechanics role
The system MUST classify each rule unit by unit kind and authority role so retrieval can distinguish answerable rules from examples, flavor, and adjacent mentions.

#### Scenario: Example text is classified
- **WHEN** a stored chunk contains an example that mentions a mechanic
- **THEN** the derived rule unit MUST mark that passage as example authority rather than base-rule authority

#### Scenario: Specific power is classified
- **WHEN** a stored chunk describes a named discipline power, ritual, formula, ceremony, merit, flaw, or table row
- **THEN** the derived rule unit MUST preserve the specific unit kind and entity tags for that mechanics record

### Requirement: Rule units MUST expose answer facets
The system MUST extract answer facets from rule units when present, including cost, dice pool, target, duration, effect, limit, prerequisite, consequence, and source reference.

#### Scenario: Cost facet detected
- **WHEN** a rule unit source states a cost for a mechanic
- **THEN** the rule unit MUST expose a cost facet linked to the source evidence

#### Scenario: Missing facet reported
- **WHEN** a rule unit does not contain a requested facet
- **THEN** the unit data MUST distinguish the absent facet from an extraction failure or low-confidence facet

### Requirement: Rule-unit diagnostics MUST report extraction quality
The system MUST provide diagnostics for rule-unit derivation coverage, confidence, stale records, orphaned chunks, multi-source units, and suspected adjacent-text bleed.

#### Scenario: Human diagnostics
- **WHEN** a user runs rule-unit diagnostics without machine-readable output
- **THEN** the command MUST summarize books inspected, chunks inspected, units created, stale units, low-confidence units, orphaned chunks, and the next inspection command

#### Scenario: JSON diagnostics
- **WHEN** a user or agent runs rule-unit diagnostics in JSON mode
- **THEN** the command MUST include deterministic counts, warning codes, affected unit IDs, affected chunk IDs, schema versions, and bounded source labels

