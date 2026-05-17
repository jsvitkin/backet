# Hosting Backet Bot

This is the friendly path for getting your private Backet Bot into your Discord server.

This page describes the v0.2.0 bot hosting model. The default path still works on a low-resource Oracle VM, but the release now makes answer quality an explicit runtime choice instead of an accidental side effect of the first free-hosting setup.

The main command is:

```bash
backet bot setup /path/to/vault
```

In an interactive terminal this is a guided wizard. It prompts you phase by phase, installs local deploy files when you confirm, asks for secrets through hidden input or file paths, uses `gh` for GitHub setup, validates Discord through the bot API, SSH-checks the Oracle VM, and offers to dispatch the deploy workflow.

You can also start from the bot command center:

```bash
backet bot
```

That menu guides setup, visibility, policy review, export, bundle checks, dry-run questions, model checks, and foreground bot runtime.

For paste-safe status without prompts:

```bash
backet bot setup --no-guided /path/to/vault
```

## Before You Start

You need:

- a Backet-initialized vault
- a private GitHub repository for that vault
- an Oracle Always Free VM reachable over SSH
- GitHub CLI: `gh`
- an SSH client
- a Discord account that can create apps and add bots to your server

Check progress anytime:

```bash
backet bot setup status /path/to/vault
backet bot setup resume /path/to/vault
backet bot setup doctor /path/to/vault
```

## 1. Start The Wizard

```bash
backet bot setup /path/to/vault
```

You can stop whenever the wizard asks to continue. Run the same command again later and it resumes from `.backet/state/bot-setup.yaml`.

Backet creates:

```text
.backet/state/bot-setup.yaml
```

This file stores non-secret setup facts, such as app ID, server ID, role IDs, GitHub repo, Oracle host/user, deploy path, answer mode, and runtime profile.

Secrets are never stored there.

The default runtime profile is `lite`, which preserves the current low-resource Oracle path. Stronger profiles are available when you operate the required model services yourself:

- `lite`: template/source-grounded answers, exact or degraded semantic retrieval, no required model services.
- `rag-standard`: compatible embedding support is required; reranker and answer model services are optional and fallback is reported as degraded mode.
- `rag-quality`: embedding, reranker, and answer model services are required; missing services fail closed.

Only local or self-hosted model services are supported in this initial hosting upgrade. Do not configure third-party hosted model APIs until Backet has an explicit privacy and licensing mode for that.

The exported bot bundle records non-secret runtime compatibility metadata in `manifest.json`: profile, fallback policy, model-service roles, backend/model identifiers, endpoint roles, dimensions, and whether model files were bundled. Secrets and model weights are deliberately excluded.

If Backet says the deployment workflow or deploy assets are missing, the wizard asks whether to install them. The focused command is also available:

```bash
backet bot setup files /path/to/vault
```

Run this from the private vault repository. If your vault is not the repository root, point Backet at the repo:

```bash
backet bot setup files /path/to/vault --repo-root /path/to/private-repo
```

This creates `.github/workflows/deploy-backet-bot.yml` and `deploy/bot/*`. Review, commit, and push them before deploying.

## 2. Set Up Discord

The main wizard guides this phase. The focused command is:

```bash
backet bot setup discord /path/to/vault
```

Backet tells you to open the Discord Developer Portal and:

- create an application
- add a bot
- keep Message Content Intent off
- use Guild Install
- use the `applications.commands` and `bot` scopes
- grant the bot minimal server permissions for `View Channels` and `Send Messages`
- install the bot only into your private server

In the interactive wizard, paste the bot token into the hidden prompt. For the focused command, pass it through stdin:

```bash
backet bot setup discord /path/to/vault --token-stdin
```

Paste the token and press Enter.

After the bot is installed in your server, the wizard lists visible servers, roles, and channels so you can choose by number. If you already know the IDs, the focused command accepts them:

```bash
backet bot setup discord /path/to/vault \
  --token-stdin \
  --guild-id YOUR_SERVER_ID \
  --player-role-id PLAYER_ROLE_ID \
  --storyteller-role-id STORYTELLER_ROLE_ID \
  --canon-channel-id PLAYER_SAFE_CHANNEL_ID
```

Backet validates the bot token and discovers guilds, roles, and channels through Discord's bot APIs. It does not ask for your Discord password, user token, cookies, or browser session.

If you use private Discord channels, add the Backet bot/app to each bot-enabled channel with `View Channel` and `Send Messages` allowed. This is separate from the Backet player role mapping. For example, a channel may allow the `Kindred` role but deny `@everyone`; in that case the bot also needs its own channel overwrite or it cannot answer normal players there. Make sure the player role also has Discord's `Use Application Commands` permission in that channel. The Discord setup phase warns when a selected player role is missing that slash-command permission.

## 3. Review Player Visibility

The setup wizard runs this review before deployment. If player-visible canon is empty, it offers to open the visibility editor. You can open that editor directly:

```bash
backet bot visibility
```

From outside the vault:

```bash
backet bot visibility --vault /path/to/vault
```

It audits the vault, explains that unmarked notes stay Storyteller-only, then shows numbered choices:

- mark player-facing notes as player-visible
- mark hidden notes as Storyteller-only
- exclude notes from bot export
- review unclassified notes
- clear bot visibility metadata
- refresh or finish

When you choose a write action, the editor suggests notes and folders from the scanned vault. Pick a number or type a vault-relative path, review the dry-run preview, then confirm before files are changed.

The focused audit command is:

```bash
backet bot setup visibility /path/to/vault
```

If players should see a folder, choose the player-visible action in the editor, select the suggested folder, keep the default `canon` topic if appropriate, and confirm the preview. For automation or scripts, the focused command remains available:

```bash
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --dry-run
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --yes
```

Then rerun:

```bash
backet bot setup visibility /path/to/vault
```

Unmarked notes are Storyteller-only. That is intentional.

## 4. Check The Oracle VM

The wizard asks for the Oracle host, SSH user, deploy path, and local key path for validation. The focused command is:

```bash
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu
```

If the deploy layout is missing:

```bash
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu --bootstrap
```

Expected layout:

```text
/srv/backet-bot/
  deploy/
  uploads/
  releases/
  data/
  models/
```

Backet validates SSH, Docker/Compose availability, and the deploy directories. It does not store your SSH private key.

Model weights stay in `/srv/backet-bot/models` or another VM-local/operator-controlled cache. They are not bundled, committed, or uploaded as bot data.

## 5. Connect GitHub

Authenticate GitHub CLI:

```bash
gh auth login
gh auth refresh -h github.com -s repo -s workflow
```

The wizard asks for the private repository, sends required secrets to `gh secret set`, and writes non-secret deploy facts to GitHub variables. The focused command is:

```bash
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO
```

Set secrets through focused commands:

```bash
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO --discord-token-stdin
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO --oracle-ssh-key-stdin
```

Required GitHub secrets:

- `DISCORD_TOKEN`
- `ORACLE_VM_SSH_KEY`

Optional GitHub secret:

- `MODEL_DOWNLOAD_TOKEN`

GitHub variables Backet can configure:

- `DISCORD_GUILD_ID`
- `ORACLE_VM_HOST`
- `ORACLE_VM_USER`
- `BACKET_RAG_PROFILE`
- `BACKET_MODEL_CACHE`
- `BACKET_EMBEDDING_ENDPOINT`
- `BACKET_RERANKER_ENDPOINT`
- `BACKET_ANSWER_MODEL_ENDPOINT`
- `BOT_COMPOSE_PROFILES`
- `LLAMA_MODEL_RELATIVE_PATH`
- `LLAMA_MODEL_SHA256`
- `LLAMA_MODEL_URL`

`BACKET_RAG_PROFILE` should match the profile exported in `.backet/state/bot-config.yaml`. `COMPOSE_PROFILES` controls which optional containers Docker Compose starts, for example `llama`, `rag-standard`, `rag-quality`, or a comma-separated combination such as `llama,rag-quality` when quality mode uses the bundled local Llama service. Keep model API keys, download tokens, and SSH keys in GitHub secrets or VM-local secret storage, not in `.backet/state/*.yaml`, `.env.example`, or the exported bot bundle.

The repository needs:

- your bot-visible vault Markdown
- `.backet/config.yaml`
- `.backet/state/bot-setup.yaml`
- `.backet/state/bot-config.yaml`
- `.backet/rules/rules.sqlite3` if rules answers are enabled
- note visibility metadata
- `deploy/bot/*`
- `.github/workflows/deploy-backet-bot.yml`

The workflow installed by `backet bot setup files` installs the released Backet wheel with bot dependencies. Your private vault repository does not need to contain the Backet source tree.

## 6. Commit And Push

Before deploying, commit and push:

- `.backet/state/bot-setup.yaml`
- `.backet/state/bot-config.yaml`
- visibility metadata changes
- rules SQLite state if needed
- deploy assets and workflow files

GitHub Actions can only deploy what exists in the repository.

## 7. Deploy

The wizard offers to deploy after all previous phases pass. The focused command is:

```bash
backet bot setup deploy /path/to/vault --vault-path . --watch
```

Backet dispatches the private GitHub Actions workflow. The workflow exports the bundle, uploads it to the Oracle VM, activates the release, restarts containers, and smoke-checks the bot.

## Upgrading RAG Quality

Use this path when `lite` is working and you want better retrieval or answer synthesis:

1. Keep `lite` until visibility, rules indexes, and basic Discord answers are correct.
2. Change `.backet/state/bot-config.yaml` to `runtime_profile: rag-standard`.
3. Add `model_services.embedding` with a self-hosted endpoint, model identifier, expected dimensions, and timeout.
4. Run `backet bot setup doctor /path/to/vault`, then export and run `backet bot doctor dist/bot-data`.
5. Add reranker and answer model services and switch to `rag-quality` only when all required checks are green.

If the stronger profile is not ready, switch back to `runtime_profile: lite` and redeploy.

Example profile configuration:

```yaml
runtime_profile: rag-standard
fallback_policy: degrade
model_services:
  embedding:
    provider: self-hosted
    endpoint: http://embedding:8080/embed
    model: bge-small
    dimensions: 384
    timeout_seconds: 5
```

For `rag-quality`, add required `reranker` and `answer` service entries as well. Use endpoint environment variable names such as `BACKET_EMBEDDING_ENDPOINT`, `BACKET_RERANKER_ENDPOINT`, and `BACKET_ANSWER_MODEL_ENDPOINT` for deploy wiring. Do not put raw API keys or tokens in this YAML.

## Measured Local Runtime Baseline

The v0.2.0 local quality baseline was measured on May 17, 2026 with:

- Windows 11
- AMD Ryzen 7 7800X3D, 8 cores / 16 logical processors
- 32 GB system RAM
- AMD Radeon RX 7800 XT
- Ollama 0.24.0 installed at `H:\Tools\Ollama`
- model cache at `H:\OllamaModels`
- local API at `http://127.0.0.1:11434`

Windows WMI reported the RX 7800 XT `AdapterRAM` as about 4 GB during the doctor run, which can underreport modern GPU VRAM. Treat the model benchmark as more reliable than that single inventory field.

Pulled and measured models:

| Role | Model | Size | Details | Result |
| --- | --- | ---: | --- | --- |
| Embedding | `nomic-embed-text:latest` | 274 MB | 137M, F16, 768 dimensions | works |
| Answer | `llama3.2:3b` | 2.0 GB | 3.2B, Q4_K_M | works |
| Answer candidate | `llama3.1:8b` | 4.9 GB | 8B, Q4_K_M | pulled, but failed this run with GPU memory/KV cache allocation errors |

The first useful local profile is:

```yaml
answer_mode: ollama-local
model:
  provider: ollama
  endpoint: http://127.0.0.1:11434
  model: llama3.2:3b
  timeout_seconds: 90
  token_budget: 700
runtime_profile: rag-standard
fallback_policy: degrade
model_services:
  embedding:
    provider: ollama
    endpoint: http://127.0.0.1:11434
    endpoint_env: BACKET_OLLAMA_ENDPOINT
    model: nomic-embed-text
    dimensions: 768
    timeout_seconds: 30
    required: true
    enabled: true
  answer:
    provider: ollama
    endpoint: http://127.0.0.1:11434
    endpoint_env: BACKET_OLLAMA_ENDPOINT
    model: llama3.2:3b
    timeout_seconds: 90
    required: false
    enabled: true
```

Local benchmark command used for Prague QA:

```powershell
$env:OLLAMA_MODELS = 'H:\OllamaModels'
$env:BACKET_OLLAMA_ENDPOINT = 'http://127.0.0.1:11434'
$env:BACKET_EMBEDDING_BACKEND = 'ollama'
$env:BACKET_EMBEDDING_MODEL = 'nomic-embed-text'

backet bot runtime doctor --model-cache H:\OllamaModels
backet bot runtime benchmark E:\Projects\prague-by-night `
  --case-file docs\qa\prague-rules-answer-cases.json `
  --role-id 1117554581904294018 `
  --model-cache H:\OllamaModels `
  --report-output E:\Projects\prague-by-night\.backet\qa\local-runtime
```

Measured results from that run:

- embedding call: `nomic-embed-text`, 768 dimensions, about 0.02 seconds warm
- answer smoke call: `llama3.2:3b`, about 0.8 seconds warm, first token at about 0.15 seconds, about 138 tokens/second
- Ollama process working set: about 2.7 GB
- deterministic QA workbench: 5 of 5 Prague cases passed
- configured-model QA workbench: 5 of 5 passed after validation fallback
- local `llama3.2:3b` quality caveat: it omitted required source citations or outline support in answerable cases, so the validator rejected the model prose and used deterministic outline answers instead
- remaining content gap: Dementation targeting now fails honestly with "missing evidence: dementation" because the permitted corpus did not contain a direct targeting rule; it no longer answers from unrelated Malkavian/Obfuscate clan text

This is enough for `rag-standard` local testing. It is not enough to call the profile `rag-quality` yet, because no reranker service is configured and the small local answer model repeatedly fails answer validation. For first production sizing, start from at least this machine class: 32 GB RAM, fast SSD model cache, and GPU/runtime compatibility proven with the same benchmark command. Do not size final production from synthetic model latency alone; require the QA workbench to pass without frequent model fallbacks.

llama.cpp Vulkan remains the advanced fallback path. The helper script at `scripts/setup-llama-cpp-vulkan-windows.ps1` documents a Windows Vulkan build and starts a llama.cpp-compatible endpoint at `http://127.0.0.1:8080/completion`. Use it only when Ollama cannot provide the required service mix or quality.

## Safe Example Transcript

The status output is intentionally paste-safe:

```text
Backet bot setup status
phases:
  discord: done
  visibility: done
  oracle: done
  github: needs_action
github:
  secrets:
    DISCORD_TOKEN: configured
    ORACLE_VM_SSH_KEY: missing
  variables:
    DISCORD_GUILD_ID: configured
    ORACLE_VM_HOST: configured
next_phase: github
runtime:
  profile: lite
  fallback_policy: template
```

Tokens, private keys, and model download tokens are not printed.

## Local Answer Playground

When a Discord answer looks wrong, test the same question locally first:

```bash
backet bot playground /path/to/vault "How does social combat work?" --command rules.ask --role-id player-role --limit 8
```

From inside the vault directory, you can also run:

```bash
backet bot playground "Whats the hunting dicepool for an alley cat predator type vampire" --command rules.ask --role-id player-role
```

You can test several questions in one run:

```bash
backet bot playground /path/to/vault \
  --question "How long does it take to perform rituals in general?" \
  --question "My character rolled a messy critical on their wits + awareness roll. what are the potential messy consequences?" \
  --question "Whats a blood hunt?" \
  --command rules.ask \
  --limit 8
```

The playground exports a temporary bot bundle, answers in fast template mode, and shows which sources were retrieved with scores and match reasons. Use `--use-model` only when you want to test the configured local Llama endpoint. Use `--bundle-output dist/bot-playground --force` if you want to keep the bundle for manual inspection.

Run the QA workbench before redeploying answer-quality changes:

```bash
backet bot qa /path/to/vault --case-file docs/qa/prague-rules-answer-cases.json --limit 6
```

The QA report groups failures by planner, retrieval, answerability, synthesis, citation, runtime, or output policy so you can tell which layer needs work before changing the live Discord bot.

Current answers are generated from an evidence-aware packet and grounded answer outline rather than raw retrieval snippets. Broad rules questions should produce a short procedure-oriented explanation. Specific lookup questions should put the requested value first. If retrieved chunks are related but do not answer the question, the bot should say what evidence is missing instead of bluffing. Internal source labels such as `[R1]` should not appear in the answer body; source details belong after the answer.

## Answer Logs

When the bot runs in Discord, each command writes a structured diagnostic log. It includes the command route, access tier, number of sources, answer mode, runtime profile, degraded mode, fallback reason, response size, elapsed time, and a question fingerprint.

The logs include a short sanitized question preview by default so bad answers can be traced back to the prompt that produced them. They remain paste-safe for vault content and secrets:

- no vault note paths
- no vault note titles
- no token or key values

Set `BACKET_BOT_LOG_QUESTION_TEXT=0` in the runtime environment if you need to suppress question previews.

## Day-To-Day Redeploy

When canon or rules change:

```bash
backet bot setup visibility /path/to/vault
git add .
git commit -m "Update bot canon"
git push
backet bot setup deploy /path/to/vault --vault-path . --watch
```

## Troubleshooting

Discord setup pending:

- install the bot into the server
- rerun Discord setup with `--token-stdin`
- choose guild, role, and channel IDs

GitHub setup pending:

- run `gh auth status`
- run `gh auth refresh -h github.com -s repo -s workflow`
- set missing secrets through `--discord-token-stdin` or `--oracle-ssh-key-stdin`

Oracle setup pending:

- check SSH connectivity
- rerun with `--bootstrap`
- make sure Docker and Docker Compose work

Player answers are empty:

- open the visibility editor and mark player-facing notes
- rerun the visibility setup check
- redeploy

Local model answers are slow:

- use template mode
- use a smaller answer model such as `llama3.2:3b`
- keep template fallback enabled
- run `backet bot runtime benchmark` and compare QA pass/fail before deploying a model change

Runtime profile is degraded or unavailable:

- run `backet bot doctor dist/bot-data`
- check `runtime_health` for the missing or unsupported service role
- make sure required services are local or self-hosted
- switch back to `runtime_profile: lite` if you need the bot online before stronger services are ready
