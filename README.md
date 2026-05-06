# backet

`backet` is a CLI and Codex skill pack for building and maintaining Obsidian-based Vampire: The Masquerade campaign vaults.

## Install

Requirements:

- Python 3.11 or newer
- `pipx` for release installs

The supported release install path is a GitHub-hosted wheel installed with `pipx`.

On macOS or Linux, the installer can bootstrap `pipx` if needed:

```bash
curl -fsSL https://raw.githubusercontent.com/jsvitkin/backet/main/scripts/install.sh | bash
```

Run the installer from any terminal location. It does not need to run inside an Obsidian vault, and it does not create vault folders. It only installs or upgrades the `backet` CLI in a user-level `pipx` environment.

On any platform with `pipx` already available, install the release wheel directly:

```bash
pipx install https://github.com/jsvitkin/backet/releases/download/v0.1.17/backet-0.1.17-py3-none-any.whl
```

On Windows PowerShell, use the Python launcher if `pipx` is not on PATH yet:

```powershell
py -3 -m pip install --user pipx
py -3 -m pipx ensurepath
py -3 -m pipx install https://github.com/jsvitkin/backet/releases/download/v0.1.17/backet-0.1.17-py3-none-any.whl
```

After the first install, update the CLI through Backet itself:

```bash
backet update check
backet update apply
```

Normal interactive `backet` commands also check for newer stable CLI releases before doing command work. When an update is available, Backet prompts, applies the update through `pipx` if you accept, and reruns the original command under the updated CLI.

Agent and other non-interactive calls do not get prompted. When an update is required, Backet exits before command work with an `update_required` error. The retry contract is:

```bash
backet update apply --yes
# then rerun the original backet command
```

Update checks always query the configured repository and do not use cached release metadata. Declining an interactive prompt records a short machine-level snooze for that specific latest version; a newer future release will still be offered. CLI package updates use the supported `pipx install --force <release-wheel>` boundary. Set `BACKET_PIPX` if Backet needs a specific `pipx` command.

The legacy macOS/Linux upgrade script remains available for repair or reinstall flows:

```bash
curl -fsSL https://raw.githubusercontent.com/jsvitkin/backet/main/scripts/upgrade.sh | bash
```

If `pipx` is missing on macOS:

```bash
brew install pipx
pipx ensurepath
```

## Usage

Initialize a vault on macOS or Linux:

```bash
mkdir -p /path/to/vault
backet init /path/to/vault
```

Initialize a vault on Windows PowerShell:

```powershell
mkdir C:\path\to\vault
backet init C:\path\to\vault
```

`backet init` expects the vault directory to already exist.

`backet init` is the step that creates Backet's per-vault files and folders inside the target vault.

Check vault health:

```bash
backet doctor /path/to/vault
```

See machine-readable output:

```bash
backet --json doctor /path/to/vault
```

Index vault Markdown for retrieval:

```bash
backet index /path/to/vault
```

`backet init` creates a root `.backetignore` file that controls which Markdown files are treated as indexable vault canon. Patterns are relative to the vault root and use gitignore-style matching. The default policy excludes `.backet/`, `.obsidian/`, `.git/`, `.trash/`, `Templates/`, `Archive/`, and `Daily Notes/`.

This is separate from `.backet/.gitignore`: `.backetignore` controls retrieval indexing, while `.backet/.gitignore` controls Git ignore behavior for Backet-owned scratch state.

Retrieve bounded context bundles:

```bash
backet --json context /path/to/vault note Sabine --query "Prince Sabine feeding permits"
backet context /path/to/vault subtree "11. Plotlines" --query "blood doll witnesses"
```

Rebuild readable memory capsules:

```bash
backet memory build /path/to/vault
```

Install or refresh the skill pack from the repository:

```bash
backet skills install
backet skills update
backet --json skills status
```

By default, release installs fetch the skill pack from the matching release tag. Use `backet skills install --ref main` only when you intentionally want the current `main` branch skill pack. `backet update apply` updates the CLI package; `backet skills update` refreshes installed skills and does not reinstall the CLI.

Scaffold and inspect the default city workflow targets:

```bash
backet blueprint apply /path/to/vault city-by-night-v1
backet --json blueprint status /path/to/vault city-by-night-v1
backet blueprint apply /path/to/vault city-by-night-v1 --slot-path aesthetic-mood="Setting/City Tone.md"
```

The default skill pack now includes `workflow-authoring` and `city-foundation`. Those skills are meant to discuss and align with you before writing canon, while using bounded `backet context` and `backet rules query` calls as needed. For real-world facts outside the local vault and rules corpus, agents should do cited external research and keep it separate from chronicle canon until you approve it.

Ingest and query local rulebook PDFs:

```bash
backet rules ingest /path/to/vault /path/to/core-rulebook.pdf --book-id core-v5 --title "Core Rulebook" --tier core
backet rules ingest /path/to/vault /path/to/camarilla.pdf --book-id camarilla --title "Camarilla" --tier supplement
backet rules index /path/to/vault
backet --json rules query /path/to/vault "feeding rights blood doll" --scope-tag camarilla
backet rules scope audit /path/to/vault --book-id camarilla
backet --json rules scope export /path/to/vault --book-id camarilla
backet rules audit /path/to/vault
```

Human `rules ingest` runs show progress by default while the PDF is inspected, extracted, OCR-processed, stored, scoped, indexed, semantically indexed when a local embedding backend is available, and summarized. Interactive terminals use live progress; redirected non-JSON runs print plain phase lines. Use `--json` when a script or agent needs deterministic machine-readable output.

Ingest automatically generates local rule scope assertions from PDF structure, headings, known Vampire: The Masquerade aliases, and mechanics/lore markers. High-confidence assertions are applied to chunks; uncertain assertions stay reviewable through `backet rules scope audit`, `export`, and `apply`. Scope manifests are exported on demand; SQLite under `.backet/rules/` remains the canonical rules state. Source PDFs stay outside the vault.

`backet rules audit` is the human-first entry point for extraction quality across all ingested books. It prints a bounded per-book summary, then interactive terminals guide you through pending review cards one at a time. Use `--no-review` when you only want the summary, or `--json` when a script or agent needs the full deterministic payload.

The audit separates maintenance work, reviewable pages, and notices:

- Maintenance means generated search state needs refreshing, usually with `backet rules index`.
- Review means extracted text may need a human decision in the guided flow.
- Notices are usually OCR fallback, title, art-heavy, blank, table-of-contents, or index pages that do not need action unless you want them to answer rules queries.
- Scope audit is separate: `backet rules scope audit` reviews generated scope assertions, not OCR quality.

For each review card, choose one of the durable decisions in the prompt:

`accepted` and `ignored` hide the same unchanged finding from later urgent review. `ignored` does not affect retrieval. `excluded` also hides the finding and removes the current chunks for that page from `backet rules query` results. `skipped` records that you looked but leaves the finding unresolved.

If automatic repair is appropriate, choose OCR retry in the guided prompt. Backet uses the stored source PDF path and fingerprint.

Repair only runs when the stored source PDF is available and fingerprint-verified. Relinking a matching PDF is normal. Relinking a mismatched PDF requires explicit force, which makes that PDF the new trusted repair source and records relink history.

When automatic repair cannot recover good text, choose manual replacement in the guided prompt. Backet opens your editor for corrected page text. The non-interactive `rules review`, `rules repair`, `rules replace`, and `rules relink-source` commands are still available for agents, tests, and scripts.

Manual replacement refreshes the page audit row, chunks, exact search index, retrieval metadata, scope application, and semantic coverage for that page. Empty or unusable replacement text is rejected; use `ignored` or `excluded` when the right decision is not to store new rules text.

`backet rules query` uses hybrid local retrieval when rule embeddings are available: exact FTS/BM25 matches plus semantic vector matches, with source metadata, generated scope assertions, supplement precedence, and extraction-quality penalties preserved. JSON output reports the retrieval mode, embedding backend/model, candidate counts, and match reasons. If semantic retrieval is missing or unavailable, rules queries fall back to exact search and report that mode.

Run `backet rules index /path/to/vault` after installing or changing the optional embedding backend, after restoring an older rules store, or when `backet rules audit` reports stale semantic coverage. Use `--book-id <id>` to refresh one book or `--full` to rebuild all rule embeddings and derived retrieval-quality metadata for the selected scope.

`backet` stores the ingested rules corpus under `.backet/rules/` so it can travel with the vault backup.

OCR fallback needs Tesseract on the local machine. On macOS:

```bash
brew install tesseract
```

For higher-quality local semantic retrieval, install the optional Sentence Transformers backend into the `pipx` environment:

```bash
pipx inject backet "sentence-transformers>=3.4.1"
```

## Private Discord Bot Bundles

Backet can export a private Discord bot bundle for a single Storyteller-controlled server. The bot is not a public downloadable rules bot: it runs from a private read-only bundle containing access-scoped vault indexes, `access-policy.json`, `manifest.json`, and the shared `.backet/rules/rules.sqlite3` when rules are enabled. Source PDFs, OCR scratch state, model files, deploy credentials, and the full vault workflow stay out of the hosted runtime.

Mark player-visible canon explicitly in note frontmatter:

```yaml
---
backet:
  visibility: player
  bot_topics:
    - canon
---
```

Unmarked notes default to Storyteller-only for player safety. Use the CLI instead of hand-editing large folders:

```bash
backet bot visibility audit /path/to/vault
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --dry-run
backet bot visibility set /path/to/vault "Player Facing" --visibility player --topic canon --recursive --yes
backet bot export /path/to/vault --output dist/bot-data --force
backet bot doctor dist/bot-data
backet bot ask dist/bot-data "What are Elysium customs?" --command canon.ask --role-id player-role
```

Hosted deployment targets an Oracle Always Free VM with Docker Compose and outbound Discord Gateway access. Install the optional bot dependency group in the runtime image with `.[bot]`. Local Llama synthesis is optional; template answers remain the deterministic fallback, and GGUF model files stay in a VM-local model cache rather than in Git or bot bundles.

See [docs/private-discord-bot.md](docs/private-discord-bot.md) for Discord Developer Portal setup, role/channel mapping, local Llama configuration, GitHub Actions deploy secrets, Oracle VM layout, rollback, and troubleshooting.

## Development

Use a normal Python virtual environment and `pip`. The project requires Python 3.11 or newer.

Create and activate a virtual environment on macOS or Linux:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Create and activate a virtual environment on Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If PowerShell blocks activation scripts, run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Confirm the local CLI is available:

```bash
backet --help
```

Run tests:

```bash
python -m pytest --cov=backet --cov-report=term-missing
```

Build a wheel:

```bash
python -m build --wheel
```

Run the install smoke test against a built wheel on macOS, Linux, WSL, or Git Bash:

```bash
scripts/smoke-install.sh dist/backet-0.1.17-py3-none-any.whl "$PWD"
```

On native Windows PowerShell, validate the built wheel with `pipx`:

```powershell
py -3 -m pipx install --force .\dist\backet-0.1.17-py3-none-any.whl
backet --version
py -3 -m pipx uninstall backet
```
