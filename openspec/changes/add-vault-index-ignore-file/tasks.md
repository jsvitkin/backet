## 1. Index Ignore Policy Foundation

- [x] 1.1 Add path helpers and default template content for root `.backetignore`
- [x] 1.2 Add gitignore-style pattern loading and matching for vault-relative paths
- [x] 1.3 Preserve built-in safety exclusions for `.backet/` and other system paths even when `.backetignore` is missing or edited
- [x] 1.4 Add deterministic metadata for ignore policy status to index-related command results

## 2. Vault Bootstrap And Repair

- [x] 2.1 Update `backet init` to create `.backetignore` at the vault root
- [x] 2.2 Update created-file reporting for human and JSON init output
- [x] 2.3 Update `backet doctor` to report missing `.backetignore` as a safe-to-fix warning
- [x] 2.4 Update `backet doctor --fix` to create the default `.backetignore` only when it is missing
- [x] 2.5 Ensure `doctor --fix` preserves existing user-edited `.backetignore` content

## 3. Indexing And Retrieval Behavior

- [x] 3.1 Apply ignore policy filtering before Markdown fingerprinting, parsing, chunking, and embedding
- [x] 3.2 Treat newly ignored Markdown paths as deleted from the effective corpus during index state inspection
- [x] 3.3 Remove previously indexed notes and chunks when they become ignored
- [x] 3.4 Verify context retrieval cannot return sources from ignored notes
- [x] 3.5 Verify derived memory rebuilds use only indexed, non-ignored notes

## 4. Documentation And Skill Boundary

- [x] 4.1 Update README usage docs to explain `.backetignore` and how it differs from `.backet/.gitignore`
- [x] 4.2 Document the default active ignore patterns, including `Templates/`, `Archive/`, and `Daily Notes/`, plus vault-root-relative matching behavior
- [x] 4.3 Confirm no skill-pack changes are required because skills continue to rely on CLI context retrieval

## 5. Testing And Release Validation

- [x] 5.1 Add unit tests for ignore pattern matching, comments, directory patterns, globs, and negation if supported
- [x] 5.2 Add vault initialization tests for default `.backetignore` creation
- [x] 5.3 Add doctor tests for missing, fixed, and preserved `.backetignore`
- [x] 5.4 Add indexing integration tests for ignored Markdown, stale detection, and removal of previously indexed ignored notes
- [x] 5.5 Add retrieval and memory regression tests proving ignored notes do not appear in context bundles or rebuilt memory
- [x] 5.6 Run the full test suite
- [x] 5.7 If a new dependency is added, build the wheel and run install or smoke validation for release packaging
