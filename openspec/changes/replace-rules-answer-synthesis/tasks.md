## 1. Answer Outline Model

- [x] 1.1 Define a grounded answer outline structure with stance, claims, source IDs, missing evidence, and answer shape.
- [x] 1.2 Convert existing `AnswerPacket` data into outlines for answerable and non-answerable cases.
- [x] 1.3 Add unit tests for yes/no, definition, procedure, timing, cost, consequence, and insufficient outlines.

## 2. Deterministic Composer

- [x] 2.1 Replace first-source sentence picking with outline-based deterministic composition.
- [x] 2.2 Generalize current hard-coded helpers into reusable answer-shape detectors or remove them where the outline covers the behavior.
- [x] 2.3 Ensure deterministic output cites selected evidence and never cites fallback context.

## 3. Local Model Synthesis

- [x] 3.1 Build prompts from answer outlines and selected evidence only.
- [x] 3.2 Validate model output for required stance, citation coverage, source-label validity, length, outline support, and non-answer compliance.
- [x] 3.3 Respect runtime profile fallback policy for model unavailable and validation-failed cases.

## 4. Diagnostics and QA

- [x] 4.1 Extend answer traces with outline, synthesis mode, validation result, and fallback reason.
- [x] 4.2 Add QA workbench assertions for synthesis-stage failures.
- [x] 4.3 Run standard QA cases after retrieval hardening and record remaining synthesis gaps.
