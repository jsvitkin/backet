## Context

`backet` will live in one repository but target external Obsidian vaults. That means the first change needs to settle three boundaries before deeper work starts:

- where the CLI is installed and how it finds a vault
- what `backet` owns inside a vault
- how the skill pack evolves without being welded to the CLI release cadence

The current repo is effectively a blank slate with OpenSpec context only, which makes this the best point to set durable conventions rather than retrofitting them later.

## Goals / Non-Goals

**Goals:**

- Choose the first package and repository shape for the CLI and skill pack.
- Define the per-vault bootstrap contract under `.backet/`.
- Define the CLI interaction contract for human-facing and agent-facing use.
- Define how skills are installed, versioned, and updated independently from the CLI.

**Non-Goals:**

- Implement retrieval or indexing internals.
- Implement PDF ingestion or OCR.
- Design authoring workflows such as NPC, setting, or plot skills.

## Decisions

### 1. Use a global-install plus per-vault-init model

`backet` will follow the same broad mental model as `openspec`: the CLI is installed on the user's machine, then pointed at a vault with an initialization command.

Why:

- It matches the user's desired workflow and avoids treating this repo as content storage.
- It allows one CLI installation to manage multiple vaults.
- It keeps tool updates separate from campaign data.

Alternative considered:

- Repo-bound application model. Rejected because it confuses tool state with campaign state and makes multi-vault usage awkward.

### 2. Use Python for the CLI and package it as a machine-level tool

The CLI foundation will assume a Python implementation with a `src/backet/` style package layout.

Why:

- Python is a strong fit for local CLI UX, Markdown/YAML processing, SQLite, PDF tooling, and OCR orchestration.
- The user has no language preference, so the strongest ecosystem fit should win.
- It supports attractive terminal UX and practical distribution with common Python tool-install patterns.

Alternative considered:

- Deferring language choice. Rejected because foundation work such as repository layout and packaging boundaries becomes underspecified.

### 2a. Use `pipx` plus GitHub-hosted release artifacts as the default install path

The default user-facing installation path will be:

- install `pipx` if it is missing
- install `backet` from a versioned GitHub-hosted release artifact

The primary documented UX will be a short repository-hosted installer command, with a transparent fallback path of `pipx install` against a versioned release artifact URL. On this machine, `pipx` is already installed via Homebrew while `uv` is not, so `pipx` remains the cleanest default application installer.

Why:

- `pipx` is already present on this machine and is purpose-built for globally installed Python CLI applications.
- GitHub-hosted artifacts satisfy the user's desire to avoid a public package index.
- It keeps the user's Python environment isolated while still allowing one-command or near-one-command installation.
- It maps cleanly to the desired "installed globally, then initialize a vault" workflow.

Alternative considered:

- Recommending `uv tool install` by default. Rejected because `uv` is not present on this machine and would add another prerequisite without enough upside for end users.
- Recommending `pip install --user`. Rejected because it gives weaker isolation for a machine-level CLI.
- Publishing to PyPI and recommending `pipx install backet`. Rejected because the user explicitly does not want distribution to depend on a public Python package index.
- Requiring users to type a full artifact URL as the only install path. Rejected because it is transparent but not friendly enough as the primary UX.

### 2b. Use Hatchling as the default Python build backend

The default packaging backend will be `hatchling` in `pyproject.toml`.

Why:

- `hatchling` is a simple, modern backend for pure-Python CLI packaging.
- It is sufficient for building wheels and sdists that can be attached to repository releases.
- It keeps the packaging surface small while the project is still establishing its release model.

Alternative considered:

- Delaying the backend choice. Rejected because release-validation work needs a concrete build target.

### 2c. Treat wheels as the supported release artifact in v1

The supported user installation target in v1 will be a built wheel attached to a repository release. Source distributions may exist later, but they will not be part of the primary supported install path.

Why:

- Wheel installs are more predictable for end users than build-from-source flows.
- The user explicitly wants install failures caught before release, and wheel-first distribution reduces variability.

Alternative considered:

- Treating sdists and wheels as equally supported install paths in v1. Rejected because it increases install-surface variability before the release pipeline is mature.

### 3. Treat `.backet/` as the vault-owned state boundary

Each initialized vault will contain a `.backet/` directory owned by the tool.

Expected shape:

```text
.backet/
  .gitignore
  config.yaml
  state/
  memory/
  rules/
  cache/        # ignored
  temp/         # ignored
  ocr-work/     # ignored when present
```

Why:

- It keeps durable and rebuildable state scoped to one vault.
- It avoids root-level clutter and root `.gitignore` assumptions.
- It gives later changes a stable place for indexes, memory capsules, and ingested rules.

Alternative considered:

- Writing tool state into the vault root or home-directory globals. Rejected because it weakens portability and backup behavior.

### 4. Commit durable state, ignore machine-specific artifacts

`backet init` will bootstrap `.backet/.gitignore` so that portable vault state can be committed while machine-specific scratch state remains ignored.

Why:

- The user explicitly wants backed-up durable state.
- Machine-specific artifacts still need a clean rebuild path on fresh machines.

Alternative considered:

- Storing everything as untracked local cache. Rejected because it weakens reproducibility and backup.

### 5. Define one CLI surface with dual output modes

The CLI will be designed for human-first terminal usage by default, with explicit deterministic machine-readable output for agent workflows.

Likely top-level command families:

```text
backet init
backet doctor
backet skills ...
backet index ...
backet context ...
backet rules ...
```

Why:

- The same tool must serve both users and Codex-driven skills.
- A single CLI surface reduces duplicated behavior between "human mode" and "agent mode."

Alternative considered:

- Separate human and agent CLIs. Rejected because it duplicates behavior and invites drift.

### 6. Separate skill lifecycle from CLI lifecycle

The skill pack will live in the same repository but have its own install/update flow and compatibility checks.

Why:

- Skills and CLI plumbing will evolve at different speeds.
- This supports quick skill iteration without forcing a full CLI package release.

Alternative considered:

- Bundle skills directly into CLI releases only. Rejected because it slows skill iteration and couples unrelated changes.

### 7. Keep compatibility metadata authoritative in release artifacts, not vault state

The authoritative compatibility contract will live with the distributed CLI and skill pack artifacts in the repository and in machine-level `backet` installation metadata. Vault state will only keep lightweight diagnostic information such as the vault schema version and the last known CLI and skill versions that touched the vault.

Why:

- Skills are installed at machine scope, not per-vault scope.
- Compatibility rules should travel with the artifacts that actually need to interoperate.
- Keeping only lightweight diagnostics in the vault avoids duplicating or stale-copying the compatibility matrix.

Alternative considered:

- Storing the full CLI/skill compatibility matrix in `.backet/`. Rejected because it duplicates machine-level release metadata and makes vault state drift-prone.

### 7a. Keep machine-level skill installation metadata in a CLI-managed config directory

The installed skill manifest and compatibility metadata will live in a machine-level `backet` config directory rather than inside each vault.

Why:

- Skills are installed at machine scope and may be shared across multiple vaults.
- Machine-level metadata belongs next to the installed CLI and skill assets, not in per-vault state.

Alternative considered:

- Storing machine-level skill install metadata inside `.backet/`. Rejected because it duplicates state across vaults and confuses machine scope with vault scope.

### 8. Make `backet doctor` auto-fix only safe rebuildable problems

`backet doctor` will support automatic repair only for idempotent actions that do not overwrite durable user state or silently change compatibility boundaries.

Safe auto-fix examples:

- recreate missing ignored scratch directories
- rebuild caches or derived memory from canonical sources
- refresh rebuildable local artifacts when the repair path is deterministic

Manual-only examples:

- overwriting committed durable databases
- changing vault schema versions
- resolving CLI/skill incompatibility
- re-ingesting rules in ways that replace backed-up rule corpus state

Why:

- The user wants supportive recovery behavior without accidental data loss.
- It keeps `doctor --fix` trustworthy.

Alternative considered:

- Making `doctor` suggestion-only. Rejected because some repairs are safe and should reduce friction.
- Making `doctor` aggressively self-healing. Rejected because it risks overwriting durable state or hiding compatibility problems.

### 9. Add GitHub Actions quality gates from the foundation layer

The repository will include GitHub Actions workflows that:

- run tests on push and pull request events
- build installable artifacts
- run install and bootstrap smoke tests against those artifacts before publication

The v1 required release smoke matrix will include:

- macOS, because it matches the user's primary environment
- Ubuntu Linux, to catch obvious cross-platform packaging issues early

Windows support can follow in a later expansion if the CLI surface or dependency stack requires it.

Why:

- The user specifically wants broken install flows caught before release.
- Installation is part of the product, not just packaging trivia.
- Strong CI from the beginning reduces the chance that future retrieval and ingestion work quietly erodes installability.

Alternative considered:

- Adding CI later. Rejected because release and install correctness are already first-order requirements.

### 10. Use layered automated testing as the default quality strategy

The baseline testing strategy will include:

- unit tests for command logic and helpers
- integration tests against temporary vault fixtures
- smoke tests that install built release artifacts in clean environments and run `backet --version`, `backet init`, and a minimal recovery command

Why:

- Unit tests alone will not catch packaging or post-install breakage.
- The user has already experienced broken CLI releases from another ecosystem and wants that failure mode avoided here.

Alternative considered:

- Unit-test-only CI. Rejected because it would miss the exact release failure mode the user is worried about.

## Risks / Trade-offs

- [Committed per-vault state creates Git churn] -> Keep durable state compact and keep transient scratch state ignored.
- [Repository-hosted installs add release-workflow complexity] -> Keep install mechanics explicit and validate built artifacts before publish.
- [Skill/CLI compatibility drift] -> Add explicit version or compatibility metadata and surface it via `backet skills status`.
- [A flexible CLI surface can sprawl quickly] -> Keep top-level commands few and enforce consistent output conventions.
- [Thorough CI will cost more runtime] -> Keep the test pyramid layered so expensive install smoke tests are targeted and reusable.

## Migration Plan

1. Establish the repository layout and package skeleton for the CLI and skills.
2. Establish build artifacts and repository-hosted installation mechanics.
3. Implement `backet init` and `backet doctor` with `.backet/` bootstrap and recovery behavior.
4. Add skill installation and update metadata plus compatibility checks.
5. Add GitHub Actions workflows for push/PR test runs and release install-validation.
6. Use this foundation for retrieval and rules-ingestion changes.

Rollback is simple at this stage because there is no prior implementation; the main rollback concern is revising the proposed package and vault-state layout before code is written.

## Open Questions

- None at this layer.
