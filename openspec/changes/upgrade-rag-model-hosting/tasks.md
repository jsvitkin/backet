## 1. Runtime Profile Model

- [ ] 1.1 Define lite, rag-standard, and rag-quality runtime profiles
- [ ] 1.2 Add profile configuration parsing to bot setup state
- [ ] 1.3 Add profile and fallback policy metadata to bot bundle manifests
- [ ] 1.4 Preserve current deployment behavior as the lite default

## 2. Service Configuration

- [ ] 2.1 Define configuration fields for embedding, reranker, and answer model service roles
- [ ] 2.2 Keep model credentials and download tokens in secret storage only
- [ ] 2.3 Ensure model files remain outside bot data bundles and Git-tracked assets

## 3. Doctor and Health Checks

- [ ] 3.1 Add local doctor checks for embedding capability and compatibility metadata
- [ ] 3.2 Add doctor checks for reranker capability and timeout behavior
- [ ] 3.3 Add doctor checks for answer model completion capability and timeout behavior
- [ ] 3.4 Add runtime health output for profile, service status, fallback policy, and degraded mode

## 4. Deploy Assets

- [ ] 4.1 Update Docker Compose and environment examples for optional model service endpoints
- [ ] 4.2 Update guided setup to explain profile trade-offs and required services
- [ ] 4.3 Update deployment docs with upgrade paths from lite to stronger RAG profiles
- [ ] 4.4 Ensure third-party hosted model APIs are rejected or clearly unsupported in this initial slice

## 5. Validation

- [ ] 5.1 Add unit tests for profile parsing, manifest metadata, and secret exclusion
- [ ] 5.2 Add integration tests for doctor checks with healthy, degraded, and missing services
- [ ] 5.3 Add deployment asset tests for profile environment variables and model cache boundaries
- [ ] 5.4 Run full tests and OpenSpec validation
