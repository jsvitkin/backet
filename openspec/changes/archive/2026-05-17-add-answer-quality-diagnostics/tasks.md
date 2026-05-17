## 1. Trace Contract

- [x] 1.1 Define an answer trace schema version and structured trace fields for bot runtime answers
- [x] 1.2 Add trace serialization to local JSON bot answer output without changing normal Discord responses
- [x] 1.3 Add bounded source snippet handling for diagnostic output
- [x] 1.4 Add placeholder trace fields for query planning, reranking, and answerability stages

## 2. Playground Diagnostics

- [x] 2.1 Extend bot playground output with retrieval mode, source scores, match reasons, and generation warnings
- [x] 2.2 Keep human output concise while preserving complete details in JSON output
- [x] 2.3 Ensure diagnostics sanitize mentions and never print secrets

## 3. Regression Case Support

- [x] 3.1 Define a fixture format for answer-quality cases
- [x] 3.2 Add fixture cases for learning Obfuscate, Malkavian Dementation targeting, and blood bond questions
- [x] 3.3 Implement evaluator helpers that report retrieval, answerability, and answer text status separately
- [x] 3.4 Add tests for expected evidence, forbidden evidence, and insufficiency assertions

## 4. Validation

- [x] 4.1 Add unit tests for trace serialization and snippet bounds
- [x] 4.2 Add integration tests for playground diagnostics
- [x] 4.3 Run the full test suite and OpenSpec validation
