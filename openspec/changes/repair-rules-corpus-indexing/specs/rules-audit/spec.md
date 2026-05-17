## ADDED Requirements

### Requirement: Corpus health actions
Rules audit SHALL summarize corpus health actions as none, reindex, repair, or reingest.

#### Scenario: Full reindex needed
- **WHEN** metadata or semantic indexes are stale but source text is usable
- **THEN** audit human output recommends `backet rules index <vault> --full`

#### Scenario: Source repair needed
- **WHEN** a book requires OCR repair or reingestion
- **THEN** audit output identifies the book, stored source path or missing source fingerprint, and the safest next command

### Requirement: Human output is interpreted
Rules audit human output SHALL explain corpus health findings without dumping raw JSON dictionaries or internal payload keys.

#### Scenario: Corpus health has issues
- **WHEN** audit finds stale metadata and reingest candidates
- **THEN** human output groups them under concise headings with actionable commands

