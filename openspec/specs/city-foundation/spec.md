# city-foundation Specification

## Purpose
TBD - created by archiving change add-explore-first-workflow-skills. Update Purpose after archive.
## Requirements
### Requirement: The system MUST support a top-down city-foundation workflow

The system MUST provide a workflow that helps the user establish high-level city canon before lower-level districts, factions, named SPCs, or plotlines are authored in detail.

#### Scenario: Begin a new city foundation

- **WHEN** a user starts the `city-foundation` workflow in a bootstrapped vault
- **THEN** the system MUST orient the discussion around city-wide pressure, tone, reputation, and current-night structure rather than jumping directly to individual character generation

### Requirement: City foundation MUST cover a defined top-level slot set

The `city-foundation` workflow MUST target a bounded set of semantic slots for top-level city canon: `aesthetic-mood`, `historical-trauma-memory`, `kindred-reputation`, `human-cultural-tone`, and `present-night-pressure`.

#### Scenario: Scaffolded city-foundation targets

- **WHEN** the user applies the default city blueprint and enters the `city-foundation` workflow
- **THEN** the system MUST be able to identify note targets corresponding to each required semantic slot

### Requirement: City foundation MUST refine existing canon instead of duplicating it

If some top-level city slots already contain canon, the workflow MUST reuse and refine those notes rather than generating parallel duplicate notes for the same semantic purpose.

#### Scenario: Partially completed city foundation

- **WHEN** one or more city-foundation note targets already exist with canonical content
- **THEN** the workflow MUST discuss those notes as existing truth, identify remaining gaps or tensions, and avoid creating duplicate city-foundation notes for the same slots

### Requirement: City foundation MUST stage writing selectively after alignment

The `city-foundation` workflow MUST be able to conclude with explicit write targets and MUST only draft or update the slots the user chooses to commit in that step.

#### Scenario: Approve a subset of city-foundation writes

- **WHEN** the user agrees with only part of the city-foundation brief
- **THEN** the workflow MUST support drafting only the approved city slots while leaving unapproved slots in discussion state

