## 1. Runtime Profile Model

- [x] 1.1 Define lite, rag-standard, and rag-quality runtime profiles
- [x] 1.2 Add profile configuration parsing to bot setup state
- [x] 1.3 Add profile and fallback policy metadata to bot bundle manifests
- [x] 1.4 Preserve current deployment behavior as the lite default

## 2. Service Configuration

- [x] 2.1 Define configuration fields for embedding, reranker, and answer model service roles
- [x] 2.2 Keep model credentials and download tokens in secret storage only
- [x] 2.3 Ensure model files remain outside bot data bundles and Git-tracked assets

## 3. Doctor and Health Checks

- [x] 3.1 Add local doctor checks for embedding capability and compatibility metadata
- [x] 3.2 Add doctor checks for reranker capability and timeout behavior
- [x] 3.3 Add doctor checks for answer model completion capability and timeout behavior
- [x] 3.4 Add runtime health output for profile, service status, fallback policy, and degraded mode

## 4. Deploy Assets

- [x] 4.1 Update Docker Compose and environment examples for optional model service endpoints
- [x] 4.2 Update guided setup to explain profile trade-offs and required services
- [x] 4.3 Update deployment docs with upgrade paths from lite to stronger RAG profiles
- [x] 4.4 Ensure third-party hosted model APIs are rejected or clearly unsupported in this initial slice

## 5. Validation

- [x] 5.1 Add unit tests for profile parsing, manifest metadata, and secret exclusion
- [x] 5.2 Add integration tests for doctor checks with healthy, degraded, and missing services
- [x] 5.3 Add deployment asset tests for profile environment variables and model cache boundaries
- [x] 5.4 Run full tests and OpenSpec validation
