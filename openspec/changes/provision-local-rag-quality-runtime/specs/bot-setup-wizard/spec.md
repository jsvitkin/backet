## ADDED Requirements

### Requirement: Local quality runtime setup
The bot setup workflow SHALL configure local model runtime profiles, endpoint metadata, and fallback policy without storing secrets.

#### Scenario: Configure standard profile
- **WHEN** the user selects local standard RAG profile
- **THEN** setup writes embedding and answer endpoint metadata and marks reranker as optional unless validated

#### Scenario: Configure quality profile
- **WHEN** the user selects local quality RAG profile
- **THEN** setup requires embedding, reranker, and answer service doctor checks before marking the profile ready

### Requirement: Runtime install guidance
The setup workflow SHALL provide platform-specific install guidance for missing local runtime dependencies.

#### Scenario: Windows AMD runtime missing
- **WHEN** Windows detects an AMD Radeon GPU but no local runtime command is available
- **THEN** setup recommends native Ollama first and llama.cpp Vulkan as an advanced fallback

