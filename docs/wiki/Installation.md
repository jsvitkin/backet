# Installation

This page explains how to install `backet`, install its Codex skill pack, and check that the tool is ready to use with an Obsidian vault.

`backet` has two pieces:

- The `backet` command-line tool.
- The Codex skill pack, installed separately with `backet skills install`.

Install the CLI first, then install or update the skill pack.

## Requirements

You need:

- Python 3.11 or newer.
- `pipx` for direct wheel or source installs. The macOS/Linux installer can bootstrap `pipx` if it is missing.
- An Obsidian vault directory, once you are ready to initialize a vault.

Optional:

- Git, if you install from source or work on the project locally.
- Tesseract, if you want OCR fallback for scanned or image-only rulebook PDFs.
- Sentence Transformers, if you want higher-quality local semantic retrieval.

## Current Release

The current release is `v0.1.26`.

Use the release installer for normal macOS/Linux installs. Use direct `pipx` installs on Windows or when you already have `pipx` set up. Use the source install path only when you want the current `main` branch instead of the latest release.

## Recommended Install on macOS or Linux

The supported release install path is the installer script:

```bash
curl -fsSL https://raw.githubusercontent.com/jsvitkin/backet/main/scripts/install.sh | bash
```

Run this command from any terminal location. It does not need to run inside your Obsidian vault.

The script:

- Finds the latest GitHub Release.
- Installs the matching wheel with `pipx`.
- Bootstraps `pipx` if it is missing.
- Does not create vault folders or modify vault content.

To inspect the script before running it:

```bash
curl -fsSL https://raw.githubusercontent.com/jsvitkin/backet/main/scripts/install.sh -o install-backet.sh
less install-backet.sh
bash install-backet.sh
```

To install the current release explicitly:

```bash
curl -fsSL https://raw.githubusercontent.com/jsvitkin/backet/main/scripts/install.sh | bash -s -- --version 0.1.26
```

If your default `python3` is not Python 3.11 or newer, point the installer at the right interpreter:

```bash
curl -fsSL https://raw.githubusercontent.com/jsvitkin/backet/main/scripts/install.sh | bash -s -- --python /path/to/python3.11
```

## Direct `pipx` Install

On any platform with `pipx` already available, install the release wheel directly:

```bash
pipx install https://github.com/jsvitkin/backet/releases/download/v0.1.26/backet-0.1.26-py3-none-any.whl
```

On Windows PowerShell, use the Python launcher if `pipx` is not on `PATH` yet:

```powershell
py -3 -m pip install --user pipx
py -3 -m pipx ensurepath
py -3 -m pipx install https://github.com/jsvitkin/backet/releases/download/v0.1.26/backet-0.1.26-py3-none-any.whl
```

If you need to choose a specific Python interpreter for `pipx`:

```bash
pipx install --python /path/to/python3.11 https://github.com/jsvitkin/backet/releases/download/v0.1.26/backet-0.1.26-py3-none-any.whl
```

After installation, open a new terminal if `backet` is not found immediately.

The installer and direct `pipx` commands install only the CLI. They do not initialize a vault. Vault files are created later by `backet init /path/to/vault`.

Check the CLI:

```bash
backet --version
backet --help
```

## Install From Source

Use this path when you want the current `main` branch.

On macOS or Linux:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
python3 -m pipx install "git+https://github.com/jsvitkin/backet.git"
```

If `pipx` is already on your `PATH`, this is enough:

```bash
pipx install "git+https://github.com/jsvitkin/backet.git"
```

On Windows PowerShell:

```powershell
py -3 -m pip install --user pipx
py -3 -m pipx ensurepath
py -3 -m pipx install "git+https://github.com/jsvitkin/backet.git"
```

For a source install with a specific Python interpreter:

```bash
pipx install --python /path/to/python3.11 "git+https://github.com/jsvitkin/backet.git"
```

## Install the Skill Pack

The CLI and skills are intentionally separate. After installing the CLI, install the Codex skill pack:

```bash
backet skills install
```

By default, release installs fetch the skill pack from the matching release tag. That keeps the CLI and skills on the same compatibility line.

Check the skill installation:

```bash
backet skills status
```

Update the skills later:

```bash
backet skills update
```

Use `backet skills install --ref main` only when you intentionally want the current `main` branch skill pack instead of the release-matched one.

The skill pack is installed at machine scope, not inside each vault. By default, skills go under `~/.codex/skills`. If `CODEX_HOME` is set, they go under `$CODEX_HOME/skills`.

## Initialize a Vault

Create or choose an existing Obsidian vault directory:

```bash
mkdir -p /path/to/vault
backet init /path/to/vault
```

On Windows PowerShell:

```powershell
mkdir C:\path\to\vault
backet init C:\path\to\vault
```

`backet init` expects the vault directory to already exist.

This is the step that creates Backet's per-vault files and folders. You can run it from anywhere as long as you pass the vault path. If your terminal is already inside the vault, `backet init .` is fine.

Check the vault:

```bash
backet doctor /path/to/vault
```

If safe rebuildable folders are missing, repair them:

```bash
backet doctor --fix /path/to/vault
```

## Optional: OCR Support

Rulebook PDF ingestion can read normal embedded PDF text directly. Scanned or image-only PDFs may need OCR.

Install Tesseract on macOS:

```bash
brew install tesseract
```

Install Tesseract on Debian or Ubuntu:

```bash
sudo apt-get install tesseract-ocr
```

On Windows, install Tesseract and make sure the `tesseract` command is available on `PATH`.

## Optional: Better Local Semantic Retrieval

`backet` works without Sentence Transformers, but installing it can improve local semantic retrieval quality.

For a `pipx` install:

```bash
pipx inject backet "sentence-transformers>=3.4.1"
```

This can be a large install because it pulls in machine-learning dependencies.

## Upgrade

After the first release install, use Backet's built-in CLI updater:

```bash
backet update check
backet update apply
```

Normal interactive `backet` commands also run an update preflight before command work. If a newer stable CLI release is available, Backet asks whether to update, applies the update through `pipx` when you accept, and reruns the original command under the updated CLI.

Agents and other non-interactive callers are not prompted. If a newer CLI release is required before a command runs, Backet returns an `update_required` error. The agent should run:

```bash
backet update apply --yes
```

and then retry the original command.

CLI update checks are cached in Backet's machine-level config directory, not in any vault. Declining an interactive update prompt snoozes that specific latest version for a short period, while newer future versions will still be offered.

The older macOS/Linux upgrade script remains useful for repair or reinstall flows:

```bash
curl -fsSL https://raw.githubusercontent.com/jsvitkin/backet/main/scripts/upgrade.sh | bash
```

For source installs:

```bash
pipx install --force "git+https://github.com/jsvitkin/backet.git"
backet skills update
```

`backet update apply` updates the CLI package. `backet skills update` refreshes the installed Codex skill pack and does not reinstall the CLI.

Check the result:

```bash
backet --version
backet skills status
```

## Uninstall

Remove the CLI:

```bash
pipx uninstall backet
```

This does not delete your vaults.

To remove installed skills, delete the installed skill directories from your Codex skills folder, usually:

```bash
rm -rf ~/.codex/skills/workflow-authoring ~/.codex/skills/city-foundation
```

If you use `CODEX_HOME`, remove them from `$CODEX_HOME/skills` instead.

## Development Install

Use this path if you are working on `backet` itself.

```bash
git clone https://github.com/jsvitkin/backet.git
cd backet
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Install skills from the checked-out repository:

```bash
backet skills install --source skills
```

Run tests:

```bash
python -m pytest --cov=backet --cov-report=term-missing
```

Build a wheel:

```bash
python -m build --wheel
```

## Troubleshooting

`backet: command not found`

Open a new terminal, then run:

```bash
pipx ensurepath
```

`No GitHub Release was found`

Check your network connection and the repository URL. If GitHub is unavailable, use the source install path.

`Python interpreter not found`

Install Python 3.11 or newer, or pass the interpreter explicitly with `--python`.

`Vault is not bootstrapped for backet yet`

Run:

```bash
backet init /path/to/vault
```

`No installed skill pack metadata was found`

Run:

```bash
backet skills install
```
