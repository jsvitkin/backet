# discord-query-bot Specification

## Purpose
TBD - created by archiving change add-discord-query-bot. Update Purpose after archive.
## Requirements
### Requirement: The bot MUST use private guild-scoped Discord commands
The system MUST provide a private Discord bot intended for configured guilds, using slash commands as the primary user interface and avoiding free-form message monitoring in the initial slice.

#### Scenario: Register guild commands
- **WHEN** the bot starts with a configured Discord guild ID
- **THEN** it MUST register or verify the expected guild-scoped slash commands for rules, canon, Storyteller, source, and health workflows

#### Scenario: Avoid message-content dependency
- **WHEN** a player invokes the bot through normal gameplay
- **THEN** the bot MUST accept the question through a slash command option rather than requiring access to ordinary channel message content

#### Scenario: Reject unauthorized guild
- **WHEN** the bot receives an event or interaction from a guild that is not configured for the bundle
- **THEN** it MUST reject or ignore the request without querying any vault or rules corpus

### Requirement: The bot MUST authorize requests before retrieval
The system MUST resolve the Discord user's configured access tier before selecting any vault index, rules corpus behavior, or answer mode.

#### Scenario: Player asks a player-safe rules question
- **WHEN** a Discord user with player access invokes a rules command
- **THEN** the bot MUST select only player-allowed context sources and rules behavior before retrieval begins

#### Scenario: Player asks for hidden material
- **WHEN** a Discord user without Storyteller access invokes a Storyteller, NPC, plotline, stat block, or hidden-canon command
- **THEN** the bot MUST return a permission denial without querying Storyteller-only vault data

#### Scenario: Storyteller asks a hidden canon question
- **WHEN** a Discord user with Storyteller access invokes a Storyteller command
- **THEN** the bot MAY query Storyteller-authorized vault and rules sources according to the command scope

#### Scenario: Role mapping is missing
- **WHEN** a Discord user invokes a bot command and no configured user or role mapping grants access
- **THEN** the bot MUST treat the user as the lowest configured access tier or deny the command according to the command policy

### Requirement: The bot MUST control response visibility
The system MUST choose public, ephemeral, or private responses according to command type, channel policy, user tier, and explicit command options.

#### Scenario: Storyteller command response
- **WHEN** a Storyteller-only command returns an answer
- **THEN** the bot MUST send the response as ephemeral or otherwise private to the invoking Storyteller by default

#### Scenario: Permission denial
- **WHEN** the bot denies a request because of insufficient permissions
- **THEN** the denial MUST be visible only to the invoking user unless the command policy explicitly allows public denials

#### Scenario: Player public answer disabled
- **WHEN** a player invokes a player-safe command in a public channel and the command is configured as private by default
- **THEN** the bot MUST return an ephemeral response unless the user and command policy explicitly request a public answer

#### Scenario: Prevent unwanted mentions
- **WHEN** the bot sends a Discord response containing user-provided text or retrieved source text
- **THEN** it MUST suppress unintended mentions through the Discord allowed-mentions controls or equivalent sanitization

### Requirement: Bot answers MUST be source-grounded and bounded
The system MUST answer Discord questions only from already-authorized retrieved sources, with citations or source references included in the response.

#### Scenario: Sufficient permitted sources exist
- **WHEN** retrieval returns permitted vault or rules sources that can answer the user's question
- **THEN** the bot MUST produce a compact Discord-sized answer that cites the relevant source notes, books, pages, sections, or chunks

#### Scenario: Permitted sources are insufficient
- **WHEN** retrieval finds no permitted source that can answer the user's question
- **THEN** the bot MUST refuse with a source-grounded insufficiency message instead of inventing an answer

#### Scenario: Multiple authoritative rule sources conflict
- **WHEN** rules retrieval reports ambiguity between comparable supplement-specific sources
- **THEN** the bot MUST surface the ambiguity and ask for a narrower book, scope tag, or Storyteller decision rather than silently choosing one

#### Scenario: Answer exceeds Discord limits
- **WHEN** the generated answer would exceed the configured Discord message or embed limits
- **THEN** the bot MUST shorten, split, or summarize the answer while preserving source references and not broadening retrieval scope

### Requirement: Rules retrieval MUST use the shared rules corpus in v1
The system MUST use one shared bundled rules SQLite corpus for all bot tiers in the initial bot implementation while keeping vault canon retrieval access-scoped.

#### Scenario: Player rules command
- **WHEN** a player invokes a rules command
- **THEN** the bot MUST query the shared rules corpus and MAY combine it only with player-visible vault canon

#### Scenario: Storyteller rules command
- **WHEN** a Storyteller invokes a rules command or Storyteller command that needs rules context
- **THEN** the bot MUST query the same shared rules corpus and MAY combine it with Storyteller-authorized vault canon

#### Scenario: Hidden canon requested through rules command
- **WHEN** a player rules question also asks for hidden chronicle implications, plotlines, NPC details, or stat blocks
- **THEN** the bot MUST answer only the rules-safe portion or deny the hidden portion before retrieving Storyteller vault context

### Requirement: Local Llama synthesis MUST be optional and guarded
The system MUST support local Llama-family answer synthesis as an optional step after retrieval, with deterministic fallback and strict prompt boundaries.

#### Scenario: Llama synthesis enabled
- **WHEN** the bot is configured for local Llama synthesis and retrieved permitted sources are available
- **THEN** the bot MAY send only those permitted source snippets, source metadata, and the user question to the local model service

#### Scenario: Llama service unavailable
- **WHEN** the local model service times out, errors, or is disabled
- **THEN** the bot MUST fall back to deterministic/template answer composition or return a clear unavailable message without widening retrieval scope

#### Scenario: Llama asks for hidden context
- **WHEN** model output implies the need for hidden or unavailable context
- **THEN** the bot MUST not perform additional unauthorized retrieval and MUST either refuse or ask the user to narrow the question within their permitted access

#### Scenario: Model output lacks source grounding
- **WHEN** local model output omits required citations or includes claims not supported by the provided sources
- **THEN** the bot MUST repair the response with source references, fall back to template output, or refuse the answer

### Requirement: Bot health MUST be inspectable without leaking secrets
The system MUST provide diagnostics for bot readiness, bundle compatibility, Discord configuration, retrieval availability, and answer-generation mode without exposing tokens or private source text.

#### Scenario: Storyteller checks bot health
- **WHEN** an authorized Storyteller invokes the bot health command
- **THEN** the bot MUST report bundle version, guild binding, command status, retrieval modes, model mode, and warnings without displaying secret values

#### Scenario: Player checks bot health
- **WHEN** a player invokes any health or status surface that is available to players
- **THEN** the bot MUST return only non-sensitive readiness information and MUST NOT expose hidden corpus counts, role IDs, file paths, or model prompts

#### Scenario: Bundle incompatible at startup
- **WHEN** the bot starts with an incompatible or missing bundle
- **THEN** it MUST fail closed, avoid connecting as a usable bot, and log a diagnostic that identifies the missing or incompatible component

### Requirement: Bot answer synthesis MUST be evidence-aware
The bot MUST choose answer behavior from vetted evidence status rather than from raw source overlap alone.

#### Scenario: Evidence supports answer
- **WHEN** retrieval returns evidence marked answerable for the planned question
- **THEN** the bot MUST produce a compact answer grounded only in the selected evidence and cite the relevant sources

#### Scenario: Evidence is insufficient
- **WHEN** retrieval returns sources that mention query terms but do not satisfy the required evidence
- **THEN** the bot MUST say that the permitted sources are insufficient instead of presenting the mention as an answer

#### Scenario: Evidence is ambiguous
- **WHEN** retrieval reports multiple comparable authoritative sources or an ambiguity requiring a narrower scope
- **THEN** the bot MUST ask for a narrower book, scope, clan, discipline, or Storyteller decision rather than silently choosing one

#### Scenario: Evidence conflicts
- **WHEN** retrieval reports conflicting evidence
- **THEN** the bot MUST identify that the permitted sources conflict and MUST NOT invent a reconciliation

### Requirement: Template fallback MUST honor evidence status
Template answer mode MUST remain available but MUST be driven by evidence status.

#### Scenario: Template answer from answerable evidence
- **WHEN** template mode receives answerable evidence
- **THEN** it MUST format a concise answer and source detail from selected evidence

#### Scenario: Template refusal from insufficient evidence
- **WHEN** template mode receives insufficient evidence
- **THEN** it MUST return a concise insufficiency message with closest-source diagnostics only in local debug surfaces

#### Scenario: Template ambiguity response
- **WHEN** template mode receives ambiguous or conflicting evidence
- **THEN** it MUST return a concise narrowing or conflict message and preserve source references where safe

### Requirement: Model synthesis MUST be bounded by evidence
Optional model-generated answers MUST use only permitted evidence supplied by the runtime.

#### Scenario: Model prompt receives answer packet
- **WHEN** model synthesis is enabled and evidence is answerable
- **THEN** the model prompt MUST include only the question, answer-shape instructions, selected permitted evidence, and source labels needed for citation

#### Scenario: Model cannot override insufficiency
- **WHEN** evidence status is insufficient
- **THEN** model synthesis MUST NOT turn the response into a substantive answer unless new authorized evidence is retrieved by an allowed retrieval path

#### Scenario: Model output lacks grounding
- **WHEN** model output omits required citations, cites unavailable sources, exceeds response limits, or violates evidence status
- **THEN** the bot MUST repair the response, fall back to evidence-aware template mode, or refuse

### Requirement: Discord answer formatting MUST remain compact and safe
The bot MUST format evidence-aware responses for Discord without leaking hidden content or triggering unwanted mentions.

#### Scenario: Answer fits Discord
- **WHEN** an answer and source detail fit within Discord limits
- **THEN** the bot MUST send a compact response with direct answer first and source detail after it

#### Scenario: Answer needs splitting
- **WHEN** an answer exceeds safe Discord message limits
- **THEN** the bot MUST split or shorten the response while preserving source references and evidence status

#### Scenario: Retrieved text contains mentions
- **WHEN** retrieved source text or user input contains Discord mention syntax
- **THEN** the bot MUST sanitize the response and use allowed-mentions controls to prevent unwanted mentions

