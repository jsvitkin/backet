## Why

`backet` needs a stable product boundary before retrieval, rules ingestion, or authoring workflows can be designed safely. Right now the repo has project intent but no agreed install model, no per-vault bootstrap contract, and no explicit separation between CLI lifecycle, skill lifecycle, and vault state.

## What Changes

- Establish `backet` as a globally installed CLI plus a per-vault initialization flow, rather than a repo-bound application.
- Define the first repository and package boundaries for the CLI, skill pack, templates, and release metadata.
- Define repository-hosted installation and upgrade paths so users can install `backet` without relying on a public Python package index.
- Define the `.backet/` contract inside a vault, including what is durable and committed versus ignored as machine-specific scratch state.
- Define the user-facing and agent-facing CLI contract, including deterministic machine-readable output modes.
- Define how Codex skills are distributed and updated independently from the CLI, while still living in the same repository.
- Define CI and release-quality gates, including GitHub Actions test runs on push and pull request events and release-candidate install smoke tests before publication.

### Non-Goals

- Implement retrieval, indexing, embeddings, or rules ingestion internals.
- Define workflow-specific skills such as NPC, plot, or handout authoring.
- Lock the future vault information architecture to the current Prague-by-Night chapter layout.

## Capabilities

### New Capabilities

- `vault-bootstrap`: Initialize a target Obsidian vault for `backet` with a stable `.backet/` layout, recovery expectations, and scoped Git ignore behavior.
- `cli-contract`: Provide a CLI surface that is pleasant for humans by default and deterministic for agents when explicit machine-readable output is requested.
- `repo-distribution`: Distribute and install the CLI from repository-hosted release artifacts instead of a public Python package index.
- `skill-distribution`: Install, inspect, and update the `backet` skill pack independently from the CLI package version.
- `quality-gates`: Enforce automated tests and release-installation validation through GitHub Actions before changes or releases are accepted.

### Modified Capabilities

- None.

## Impact

- Affects repository layout, package boundaries, CLI command structure, and per-vault bootstrap behavior.
- Affects distribution, upgrade, CI, and release workflows in addition to the CLI itself.
- Introduces versioning and compatibility concerns between the CLI package and the skill pack.
- Creates the foundation that later retrieval and rules-ingestion changes will build on.
