# backet

`backet` is a CLI and Codex skill pack for building and maintaining Obsidian-based Vampire: The Masquerade campaign vaults.

## Install

The supported v1 install path is a GitHub-hosted wheel installed with `pipx`.

Primary installer UX:

```bash
curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/scripts/install.sh | bash -s -- --repo OWNER/REPO
```

Transparent fallback:

```bash
pipx install https://github.com/OWNER/REPO/releases/download/v0.1.0/backet-0.1.0-py3-none-any.whl
```

Upgrade:

```bash
curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/scripts/upgrade.sh | bash -s -- --repo OWNER/REPO
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

Install or refresh the skill pack from the repository:

```bash
backet skills install --repo OWNER/REPO
backet skills update
backet skills status --json
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
