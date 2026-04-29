# backet

`backet` is a CLI and Codex skill pack for building and maintaining Obsidian-based Vampire: The Masquerade campaign vaults.

## Install

Requirements:

- Python 3.11 or newer
- `pipx` for release installs

The supported v1 install path is a GitHub-hosted wheel installed with `pipx`.

On macOS or Linux, the installer can bootstrap `pipx` if needed:

```bash
curl -fsSL https://raw.githubusercontent.com/jsvitkin/backet/main/scripts/install.sh | bash
```

On any platform with `pipx` already available, install the release wheel directly:

```bash
pipx install https://github.com/jsvitkin/backet/releases/download/v0.1.0/backet-0.1.0-py3-none-any.whl
```

On Windows PowerShell, use the Python launcher if `pipx` is not on PATH yet:

```powershell
py -3 -m pip install --user pipx
py -3 -m pipx ensurepath
py -3 -m pipx install https://github.com/jsvitkin/backet/releases/download/v0.1.0/backet-0.1.0-py3-none-any.whl
```

Upgrade on macOS or Linux:

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

Scaffold and inspect the default city workflow targets:

```bash
backet blueprint apply /path/to/vault city-by-night-v1
backet --json blueprint status /path/to/vault city-by-night-v1
backet blueprint apply /path/to/vault city-by-night-v1 --slot-path aesthetic-mood="Setting/City Tone.md"
```

The default skill pack now includes `workflow-authoring` and `city-foundation`. Those skills are meant to discuss and align with you before writing canon, while using bounded `backet context` and `backet rules query` calls as needed.

Ingest and query local rulebook PDFs:

```bash
backet rules ingest /path/to/vault /path/to/core-rulebook.pdf --book-id core-v5 --title "Core Rulebook" --tier core
backet rules ingest /path/to/vault /path/to/camarilla.pdf --book-id camarilla --title "Camarilla" --tier supplement --scope-tag camarilla
backet --json rules query /path/to/vault "feeding rights blood doll" --scope-tag camarilla
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
scripts/smoke-install.sh dist/backet-0.1.0-py3-none-any.whl "$PWD"
```

On native Windows PowerShell, validate the built wheel with `pipx`:

```powershell
py -3 -m pipx install --force .\dist\backet-0.1.0-py3-none-any.whl
backet --version
py -3 -m pipx uninstall backet
```
