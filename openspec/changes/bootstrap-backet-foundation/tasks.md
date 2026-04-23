## 1. CLI and repository foundation

- [x] 1.1 Create the initial Python package layout for the `backet` CLI and supporting repository directories
- [x] 1.2 Add `pyproject.toml` packaging metadata using the chosen build backend and a baseline entrypoint for `backet`
- [x] 1.3 Define repository locations for skills, templates, and compatibility metadata

## 2. Distribution and release plumbing

- [x] 2.1 Build versioned CLI release artifacts hosted by the repository instead of relying on a public package index
- [x] 2.2 Implement the documented user installation and upgrade path for repository-hosted artifacts
- [x] 2.3 Add a clean-environment smoke test flow that installs built artifacts and verifies baseline CLI behavior before release publication

## 3. Vault bootstrap contract

- [x] 3.1 Implement `backet init` to create `.backet/` durable state and `.backet/.gitignore`
- [x] 3.2 Implement bootstrap detection so re-running initialization does not silently overwrite an existing vault setup
- [x] 3.3 Implement `backet doctor` with safe auto-fix behavior for rebuildable local artifacts and clear manual guidance for unsafe repairs

## 4. CLI interaction contract

- [x] 4.1 Define shared output conventions for human-readable terminal output and deterministic `--json` output
- [x] 4.2 Implement shared error formatting with actionable recovery hints
- [x] 4.3 Add tests covering dual output modes, bootstrap failure cases, and safe versus unsafe doctor repair behavior

## 5. Skill lifecycle plumbing

- [x] 5.1 Add a skill installation and update command surface that is separate from CLI installation
- [x] 5.2 Add compatibility/version checks between the installed CLI and the installed skill pack
- [x] 5.3 Persist machine-level skill installation metadata outside vault state

## 6. CI and release quality gates

- [x] 6.1 Add GitHub Actions workflows that run the automated test suite on push and pull request events
- [x] 6.2 Add layered automated coverage including unit tests, temporary-vault integration tests, and install/bootstrap smoke tests
- [x] 6.3 Gate release publication on successful artifact build, install smoke validation, and test completion
