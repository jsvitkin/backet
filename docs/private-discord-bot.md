# Private Discord Bot

Backet can run a private Discord bot for one Storyteller-controlled server. The bot is not published, the source PDFs are not copied, and the hosted VM reads only an exported runtime bundle.

The preferred setup path is the guided CLI:

```bash
backet bot setup /path/to/vault
```

In an interactive terminal, that command is a real wizard. It prompts through local deploy files, Discord bot validation and server/role/channel selection, visibility review, answer mode, GitHub secrets/variables, Oracle SSH validation, and deployment. You can stop and resume at any point.

For a menu covering the whole bot command surface:

```bash
backet bot
```

That command guides setup, visibility, policy review, bundle export, bundle doctor/inspect, dry-run questions, model checks, and foreground bot runtime.

For a non-interactive, paste-safe status view:

```bash
backet bot setup --no-guided /path/to/vault
```

## Guided Flow

The main wizard runs these phases in order. The same focused commands remain available for automation or retrying one phase:

```bash
backet bot setup /path/to/vault
backet bot setup files /path/to/vault
backet bot setup discord /path/to/vault
backet bot setup visibility /path/to/vault
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO
backet bot setup deploy /path/to/vault --vault-path .
```

Useful status commands:

```bash
backet bot setup status /path/to/vault
backet bot setup resume /path/to/vault
backet bot setup doctor /path/to/vault
```

The setup wizard writes non-secret facts to:

```text
.backet/state/bot-setup.yaml
```

The bot runtime still reads:

```text
.backet/state/bot-config.yaml
```

Secrets are never written to either file.

## Runtime Profiles

The bot now treats answer quality as an explicit hosting profile:

- `lite` is the default. It keeps the current low-resource deployment path, template/source-grounded answers, and degraded semantic retrieval fallback.
- `rag-standard` requires compatible embedding support. Reranking and model synthesis can be added, but fallback remains allowed and is reported in diagnostics.
- `rag-quality` requires embedding, reranker, and answer model services. Missing required services fail closed instead of silently falling back to weaker answers.

Model services in this initial slice must be local or self-hosted inside your operator-controlled deployment boundary. Third-party hosted model APIs such as OpenAI, Anthropic, Cohere, or similar providers are deliberately unsupported until there is a separate privacy and licensing decision.

The profile and non-secret model-service compatibility metadata are written into the exported bundle manifest. API keys, tokens, SSH keys, model download credentials, and model weights are not written into the manifest or data bundle.

If setup reports that the deployment workflow or deploy assets are missing, the interactive wizard asks to install them. You can also run the focused command:

```bash
backet bot setup files /path/to/vault
```

Run this from the private vault repository. If the vault is a subdirectory, pass the repository root explicitly:

```bash
backet bot setup files /path/to/vault --repo-root /path/to/private-repo
```

This writes `.github/workflows/deploy-backet-bot.yml` and `deploy/bot/*`. Existing changed files are not overwritten unless you rerun with `--force-files`.

## Discord Phase

The wizard cannot safely create the Discord application for you, because that would require automating your Discord user account. It guides the browser-only parts and validates the result from the terminal.

The main wizard guides this phase. The focused command is:

```bash
backet bot setup discord /path/to/vault
```

It will point you to the Discord Developer Portal and tell you to:

- create an application
- add a bot user
- keep Message Content Intent disabled
- use Guild Install
- use the `applications.commands` and `bot` scopes
- grant the bot minimal server permissions for `View Channels` and `Send Messages`
- install the bot only into your private server

In the interactive wizard, paste the bot token into the hidden prompt. For the focused command, pass it through stdin so it does not land in shell history:

```bash
backet bot setup discord /path/to/vault --token-stdin
```

Then paste the token and press Enter. Backet validates it, generates the install URL, discovers the bot's guilds, channels, and roles, and lets you choose the mappings by number in the terminal.

If you already know the server and role IDs:

```bash
backet bot setup discord /path/to/vault \
  --token-stdin \
  --guild-id 123456789012345678 \
  --player-role-id 234567890123456789 \
  --storyteller-role-id 345678901234567890 \
  --canon-channel-id 456789012345678901
```

Backet refuses Discord user tokens, passwords, cookies, and OAuth bearer tokens. It only uses bot-token plus browser-consent flows.

If commands work for server admins but not for a player role in a private channel, check Discord channel permissions before changing Backet access policy. Private channels commonly deny `@everyone` and allow only player roles such as `Kindred`; the Backet bot/app also needs an explicit channel overwrite or role that allows `View Channel` and `Send Messages`. Players also need Discord's `Use Application Commands` permission in that channel. The Discord setup phase warns when a selected player role is missing that slash-command permission.

## Visibility Phase

Players see only notes explicitly marked player-visible:

```yaml
---
backet:
  visibility: player
  bot_topics:
    - canon
---
```

The setup wizard runs this review before deployment and can open the visibility editor when notes need classification. You can open the editor directly:

```bash
backet bot visibility
```

From outside the vault, pass the vault explicitly:

```bash
backet bot visibility --vault /path/to/vault
```

The editor audits the vault, explains that unmarked notes stay Storyteller-only, then shows numbered choices to mark player-visible notes, mark Storyteller-only notes, exclude notes from export, review unclassified notes, clear metadata, refresh, or finish. For write actions it suggests notes and folders from the scanned vault, lets you pick a number or type a vault-relative path, previews the update, and asks before writing.

The focused audit command is:

```bash
backet bot setup visibility /path/to/vault
```

The wizard summarizes player-visible, Storyteller-only, bot-excluded, unmarked, missing-topic, and rules corpus state. If there are no player-visible notes, deployment is blocked until you either mark notes through the editor or confirm that an empty player canon index is intentional. For automation or scripts, the focused commands remain available:

```bash
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --dry-run
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --yes
backet bot setup visibility /path/to/vault
```

Unmarked notes default to Storyteller-only for player safety.

## GitHub Phase

Backet deploys through the private GitHub Actions workflow. The wizard uses `gh` to configure secrets and variables when available:

```bash
gh auth login
gh auth refresh -h github.com -s repo -s workflow
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO
```

Secret values are sent to GitHub Actions secrets, not written to disk. The wizard prompts for the Discord token and SSH key path. Focused commands can configure them one at a time through stdin:

```bash
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO --discord-token-stdin
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO --oracle-ssh-key-stdin
```

GitHub secrets:

- `DISCORD_TOKEN`
- `ORACLE_VM_SSH_KEY`
- `MODEL_DOWNLOAD_TOKEN` only when your model download URL requires it

GitHub variables:

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

The workflow also accepts Oracle host/user as secrets if you choose to hide those values, but variables are the default.

Your private repository must contain:

- vault Markdown needed for bot indexes
- `.backet/config.yaml`
- `.backet/state/bot-setup.yaml`
- `.backet/state/bot-config.yaml`
- `.backet/rules/rules.sqlite3` when rules answers are enabled
- explicit note visibility metadata
- `deploy/bot/*`
- `.github/workflows/deploy-backet-bot.yml`

The installed workflow uses the public Backet release wheel plus bot dependencies, so your private vault repository does not need to contain the Backet source code.

## Oracle Phase

V1 assumes you already have an SSH-reachable Oracle Always Free VM. Backet does not create Oracle cloud resources yet.

The wizard asks for the Oracle host, SSH user, deploy path, and local key path for validation. The focused command is:

```bash
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu
```

To validate with a local key file:

```bash
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu --ssh-key ~/.ssh/backet_bot_deploy
```

To ask Backet to create/check the remote deploy layout:

```bash
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu --bootstrap
```

Expected VM layout:

```text
/srv/backet-bot/
  deploy/
  uploads/
  releases/
  data/
  models/
```

The SSH private key value belongs in the GitHub secret `ORACLE_VM_SSH_KEY`, not in `.backet`.

Model weights belong under `/srv/backet-bot/models` or another operator-controlled cache. They are not committed, uploaded in bot data bundles, or copied out of the VM cache during export.

## Deploy Phase

After setup files are committed and pushed, the wizard offers to deploy. The focused command is:

```bash
backet bot setup deploy /path/to/vault --vault-path . --watch
```

The wizard dispatches `.github/workflows/deploy-backet-bot.yml`. GitHub Actions exports the private bundle, uploads it to the VM, activates the release, restarts the containers, and runs the smoke check.

If local setup files are dirty or unpushed, deployment is blocked because GitHub Actions cannot see them yet.

## Local Bundle Reference

You can still export and test manually:

```bash
backet bot export /path/to/vault --output dist/bot-data --force
backet bot doctor dist/bot-data
backet bot ask dist/bot-data "What does the court know about Elysium?" --command canon.ask --role-id player-role
```

For faster answer debugging, use the playground command. It exports a temporary bundle, runs the same bot runtime locally, uses fast template mode by default, and prints retrieved source scores and match reasons:

```bash
backet bot playground /path/to/vault "How does social combat work?" --command rules.ask --role-id player-role --limit 8
```

From inside the vault directory, you can omit the path:

```bash
backet bot playground "Whats the hunting dicepool for an alley cat predator type vampire" --command rules.ask --role-id player-role
```

Run a small regression set with repeated `--question` options:

```bash
backet bot playground /path/to/vault \
  --question "How long does it take to perform rituals in general?" \
  --question "My character rolled a messy critical on their wits + awareness roll. what are the potential messy consequences?" \
  --question "Whats a blood hunt?" \
  --command rules.ask \
  --limit 8
```

Add `--use-model` when you specifically want to test the configured local Llama endpoint. Add `--bundle-output dist/bot-playground --force` when you want to keep the exported bundle for inspection.

Current template answers are tuned for direct, source-grounded replies rather than raw retrieval dumps. Broad rules questions should receive short explanations with the main procedure, consequences, and caveats. Specific lookup questions, such as predator-type dice pools, should answer the requested value first and then cite sources. The answer body should not expose internal source labels such as `[R1]`; those belong in the source detail shown after the answer.

The bundle shape is:

```text
bot-data/
  manifest.json
  access-policy.json
  indexes/
    player-vault-index.sqlite3
    storyteller-vault-index.sqlite3
  rules/
    rules.sqlite3
```

The bundle does not include source PDFs, model files, tokens, SSH keys, or the full Obsidian vault.

## Upgrading From Lite

Start with `lite` until access policy, visibility, and rules retrieval are working. Then move in this order:

1. Set `runtime_profile: rag-standard` in `.backet/state/bot-config.yaml`.
2. Configure `model_services.embedding` with a local or self-hosted endpoint, model identifier, expected dimensions, and timeout.
3. Run `backet bot setup doctor /path/to/vault`, then export and run `backet bot doctor dist/bot-data`.
4. Add a reranker and answer model service only after embedding diagnostics are clean.
5. Switch to `rag-quality` when all three services are configured and startup diagnostics can fail closed safely.

Rollback is just setting `runtime_profile: lite` and redeploying the bundle.

## Answer Diagnostics

When a deployed Discord answer looks too short, too slow, or based on the wrong source, start with the playground and the deployed logs.

Use a broader source limit for explanation questions:

```bash
backet bot playground /path/to/vault "How does social combat work?" --command rules.ask --limit 8
```

The playground output shows the chosen sources, retrieval scores, and match reasons. If the local template answer is good but Discord is slow, test the model path with `--use-model`; the Oracle Always Free VM can be slow with CPU-only Llama and should keep template fallback enabled.

The Discord runtime writes one structured log line per command. It includes:

- `command`
- `access_tier`
- `source_count`
- `answer_mode`
- `fallback_used`
- `fallback_reason`
- `question_fingerprint`
- `response_chars`
- `response_parts`
- `elapsed_ms`

By default, logs include a short sanitized question preview so bad answers can be traced back to the prompt that produced them. Logs still avoid vault note titles, vault paths, and secret values. Source references are non-revealing, such as `R1:rules@p307` or `V1:vault`. Set `BACKET_BOT_LOG_QUESTION_TEXT=0` in the bot runtime environment if you need to suppress question previews.

## Optional Local Llama

Template answers are the default and work without a model. For local Llama, configure the runtime model and let the VM cache the GGUF file under `/srv/backet-bot/models`.

Recommended first model: Llama 3.2 3B Instruct GGUF Q4. Keep fallback to template enabled, because Always Free CPU-only resources can be slow.

Model files are VM-local cache assets. They are not committed and not bundled.

## Troubleshooting

### Missing player-visible notes

Run:

```bash
backet bot setup visibility /path/to/vault
```

Then open the guided visibility editor and mark approved notes. Unmarked notes stay Storyteller-only.

### Incompatible bundle

Run:

```bash
backet bot doctor dist/bot-data
```

Fix the reported manifest, policy, index, or rules database issue, then export and deploy again.

### GitHub setup pending

Run:

```bash
gh auth status
gh auth refresh -h github.com -s repo -s workflow
backet bot setup github /path/to/vault --repo OWNER/PRIVATE_REPO
```

### Oracle setup pending

Run:

```bash
backet bot setup oracle /path/to/vault --host ORACLE_VM_HOST --user ubuntu --bootstrap
```
