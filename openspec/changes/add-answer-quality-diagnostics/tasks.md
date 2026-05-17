## 1. Trace Contract

- [ ] 1.1 Define an answer trace schema version and structured trace fields for bot runtime answers
- [ ] 1.2 Add trace serialization to local JSON bot answer output without changing normal Discord responses
- [ ] 1.3 Add bounded source snippet handling for diagnostic output
- [ ] 1.4 Add placeholder trace fields for query planning, reranking, and answerability stages

## 2. Playground Diagnostics

- [ ] 2.1 Extend bot playground output with retrieval mode, source scores, match reasons, and generation warnings
- [ ] 2.2 Keep human output concise while preserving complete details in JSON output
- [ ] 2.3 Ensure diagnostics sanitize mentions and never print secrets

## 3. Regression Case Support

- [ ] 3.1 Define a fixture format for answer-quality cases
- [ ] 3.2 Add fixture cases for learning Obfuscate, Malkavian Dementation targeting, and blood bond questions
- [ ] 3.3 Implement evaluator helpers that report retrieval, answerability, and answer text status separately
- [ ] 3.4 Add tests for expected evidence, forbidden evidence, and insufficiency assertions

## 4. Validation

- [ ] 4.1 Add unit tests for trace serialization and snippet bounds
- [ ] 4.2 Add integration tests for playground diagnostics
- [ ] 4.3 Run the full test suite and OpenSpec validation
