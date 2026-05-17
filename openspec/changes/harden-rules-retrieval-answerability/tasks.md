## 1. Planner Hardening

- [x] 1.1 Add typo and legacy aliases for known powers and mechanics, including `dementia` -> `dementation`.
- [x] 1.2 Preserve high-value raw terms even when canonical entities exist.
- [x] 1.3 Add planner tests for Dementation targeting, Blood Bonds, Obfuscate advancement, ritual timing, and messy critical consequences.

## 2. Anchored Retrieval

- [x] 2.1 Introduce anchored retrieval query groups for entity, intent evidence, and target group terms.
- [x] 2.2 Add anchored exact channels before broad fallback channels.
- [x] 2.3 Add post-filtering so broad OR matches cannot become selected evidence without entity and intent co-occurrence.
- [x] 2.4 Add bounded neighbor expansion for heading/system chunk splits.

## 3. Answerability Contract

- [x] 3.1 Replace any-cue satisfaction with entity-plus-intent evidence checks.
- [x] 3.2 Separate selected evidence from fallback context in all non-answerable cases.
- [x] 3.3 Add rejection reasons for missing anchors, missing evidence, mere mentions, degraded semantic-only hits, and low-quality sections.
- [x] 3.4 Update bot runtime behavior so insufficient rules evidence produces an abstention packet rather than a template answer over fallback chunks.

## 4. Diagnostics and Tests

- [x] 4.1 Extend JSON traces with entity anchor status, intent evidence status, semantic quality, and rejection reasons.
- [x] 4.2 Add unit and integration tests for false-confidence cases found in Prague QA.
- [x] 4.3 Run the QA workbench standard suite and document remaining failures.
