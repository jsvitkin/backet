## 1. Planner Data Model

- [ ] 1.1 Define the rules query plan data structure and diagnostic serialization
- [ ] 1.2 Add intent labels for definition, advancement, targeting, cost, dice pool, consequence, and broad explanation
- [ ] 1.3 Add entity fields for clans, disciplines, sects, mechanics, powers, and raw unknown terms

## 2. Normalization

- [ ] 2.1 Build normalization helpers for plurals, compounds, punctuation variants, and low-value terms
- [ ] 2.2 Reuse the existing rules scope taxonomy for clan, sect, discipline, and mechanic aliases
- [ ] 2.3 Add targeted aliases for screenshot failures such as blood bond, Dementation, and discipline acquisition phrasing
- [ ] 2.4 Add unit tests for normalization and ambiguity warnings

## 3. Retrieval Integration

- [ ] 3.1 Route CLI rules queries through the planner before retrieval
- [ ] 3.2 Route Discord rules retrieval through the planner without changing authorization behavior
- [ ] 3.3 Generate multiple retrieval queries and preserve raw query fallback diagnostics
- [ ] 3.4 Expose query plans in JSON rules query and local bot answer diagnostics

## 4. Validation

- [ ] 4.1 Add regression coverage for learning Obfuscate, blood bond, and Malkavian Dementation questions
- [ ] 4.2 Verify planned retrieval does not widen vault or rules access scope
- [ ] 4.3 Run full tests and OpenSpec validation
