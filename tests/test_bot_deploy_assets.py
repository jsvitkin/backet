from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_oracle_vm_deploy_assets_are_present_and_private_by_default() -> None:
    dockerfile = _read("deploy/bot/Dockerfile")
    compose = _read("deploy/bot/docker-compose.yml")
    env_example = _read("deploy/bot/env.example")
    activate = _read("deploy/bot/activate-release.sh")
    bootstrap = _read("deploy/bot/bootstrap-llama-model.sh")
    workflow = _read(".github/workflows/deploy-backet-bot.yml")

    assert "backet[bot] @ https://github.com/jsvitkin/backet/releases/download/" in workflow
    assert "backet[bot] @ https://github.com/jsvitkin/backet/releases/download/" in dockerfile
    assert "COPY src" not in dockerfile
    assert "/srv/backet-bot/data" in compose
    assert "/srv/backet-bot/models" in compose
    assert "profiles: [\"llama\"]" in compose
    assert "ghcr.io/ggml-org/llama.cpp:server" in compose
    assert "ghcr.io/ggerganov/llama.cpp:server" not in compose
    assert "deploy/bot/Dockerfile" not in compose
    assert "replace-with-github-secret-or-vm-secret" in env_example
    assert "backet bot doctor" in activate
    assert "backet bot inspect" in activate
    assert "chmod -R a+rX" in activate
    assert "data/current" in activate
    assert "docker compose" in activate
    assert "sha256sum --check" in bootstrap
    assert "--progress-bar" in bootstrap
    assert "workflow_dispatch" in workflow
    assert "ServerAliveInterval=30" in workflow
    assert "deploy/bot/Dockerfile" in workflow
    assert "actions/upload-artifact" in workflow
    assert "retention-days: 1" in workflow
    assert "gh release" not in workflow
    assert "docker push" not in workflow
    assert "*.gguf" not in workflow


def test_deploy_assets_do_not_embed_secret_values() -> None:
    for relative in [
        "deploy/bot/Dockerfile",
        "deploy/bot/docker-compose.yml",
        "deploy/bot/env.example",
        "deploy/bot/activate-release.sh",
        "deploy/bot/bootstrap-llama-model.sh",
        ".github/workflows/deploy-backet-bot.yml",
        "docs/private-discord-bot.md",
    ]:
        text = _read(relative)
        assert "mfa." not in text
        assert "-----BEGIN OPENSSH PRIVATE KEY-----" not in text
        assert "hf_" not in text
        if "DISCORD_TOKEN=" in text:
            assert "replace-with" in text or "${{ secrets.DISCORD_TOKEN }}" in text


def test_gitignore_excludes_model_and_runtime_secret_files() -> None:
    gitignore = _read(".gitignore")

    assert "*.gguf" in gitignore
    assert ".env" in gitignore
    assert "!.env.example" in gitignore


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")
