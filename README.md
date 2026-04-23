# backet

`backet` is a CLI and Codex skill pack for building and maintaining Obsidian-based Vampire: The Masquerade campaign vaults.

## Install

The supported v1 install path is a GitHub-hosted wheel installed with `pipx`.

Primary installer UX:

```bash
curl -fsSL https://raw.githubusercontent.com/jsvitkin/backet/main/scripts/install.sh | bash
```

Transparent fallback:

```bash
pipx install https://github.com/jsvitkin/backet/releases/download/v0.1.0/backet-0.1.0-py3-none-any.whl
```

Upgrade:

```bash
curl -fsSL https://raw.githubusercontent.com/jsvitkin/backet/main/scripts/upgrade.sh | bash
```

If `pipx` is missing on macOS:

```bash
brew install pipx
pipx ensurepath
```

## Usage

Initialize a vault:

```bash
backet init /path/to/vault
```

Check vault health:

```bash
backet doctor /path/to/vault
```

See machine-readable output:

```bash
backet doctor /path/to/vault --json
```

Index vault Markdown for retrieval:

```bash
backet index /path/to/vault
```

Retrieve bounded context bundles:

```bash
backet context /path/to/vault note Sabine --query "Prince Sabine feeding permits" --json
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
backet skills status --json
```

Ingest and query local rulebook PDFs:

```bash
backet rules ingest /path/to/vault /path/to/core-rulebook.pdf --book-id core-v5 --title "Core Rulebook" --tier core
backet rules ingest /path/to/vault /path/to/camarilla.pdf --book-id camarilla --title "Camarilla" --tier supplement --scope-tag camarilla
backet rules query /path/to/vault "feeding rights blood doll" --scope-tag camarilla --json
backet rules audit /path/to/vault
```

Source PDFs stay outside the vault. `backet` stores the ingested rules corpus under `.backet/rules/` so it can travel with the vault backup.

OCR fallback needs Tesseract on the local machine. On macOS:

```bash
brew install tesseract
```

For higher-quality local semantic retrieval, install the optional Sentence Transformers backend into the `pipx` environment:

```bash
pipx inject backet "sentence-transformers>=3.4.1"
```

## Development

Install development dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

Run tests:

```bash
pytest --cov=backet --cov-report=term-missing
```

Build a wheel:

```bash
python3 -m build --wheel
```

Run the install smoke test against a built wheel:

```bash
scripts/smoke-install.sh dist/backet-0.1.0-py3-none-any.whl "$PWD"
```
