from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backet.bot_setup import (
    AdapterResult,
    DiscordSetupClient,
    Redactor,
    generate_discord_install_url,
    install_deployment_repository_files,
    load_or_initialize_setup_state,
    run_deploy_setup,
    run_discord_setup,
    run_github_setup,
    run_oracle_setup,
    run_visibility_setup,
    save_bot_setup_state,
)
from backet.cli import app
from backet.errors import AppError
from backet.vault import initialize_vault


def test_setup_status_creates_committed_safe_state_and_imports_runtime_config(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    (vault / ".backet" / "state" / "bot-config.yaml").write_text(
        "schema_version: 1\n"
        "guild_id: guild-a\n"
        "roles:\n"
        "  player:\n"
        "    - player-role\n"
        "  storyteller:\n"
        "    - st-role\n"
        "commands:\n"
        "  canon:\n"
        "    channel_ids:\n"
        "      - canon-channel\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--json", "bot", "setup", "status", str(vault)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["discord"]["guild_id"] == "guild-a"
    assert payload["data"]["discord"]["selected_role_ids"]["player"] == ["player-role"]
    assert payload["data"]["github"]["secrets"]["DISCORD_TOKEN"] == "missing"
    setup_text = (vault / ".backet" / "state" / "bot-setup.yaml").read_text(encoding="utf-8")
    assert "guild-a" in setup_text
    assert "secret_names: []" in setup_text
    assert "never-store" not in setup_text


def test_setup_state_rejects_secret_values(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    path = vault / ".backet" / "state" / "bot-setup.yaml"
    path.write_text("schema_version: 1\ndiscord:\n  token: never-store-this\n", encoding="utf-8")

    with pytest.raises(AppError) as error:
        load_or_initialize_setup_state(vault)

    assert error.value.code == "bot_setup_secret_field"


def test_redactor_scrubs_explicit_values_and_private_keys() -> None:
    redactor = Redactor(("super-secret-token",))
    text = redactor.text(
        "DISCORD_TOKEN=super-secret-token\n"
        "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"
    )

    assert "super-secret-token" not in text
    assert "abc" not in text
    assert "DISCORD_TOKEN=[REDACTED]" in text


def test_discord_setup_validates_token_discovers_ids_and_writes_runtime_config(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    client = DiscordSetupClient(transport=FakeDiscordTransport())

    result = run_discord_setup(
        vault,
        token="bot-token",
        guild_id="guild-a",
        player_role_ids=["role-player"],
        storyteller_role_ids=["role-st"],
        canon_channel_ids=["channel-canon"],
        client=client,
    )

    assert result.data["last_phase_result"]["status"] == "done"
    state = load_or_initialize_setup_state(vault)
    assert state["discord"]["app_id"] == "app-a"
    assert state["discord"]["guild_id"] == "guild-a"
    assert "bot-token" not in (vault / ".backet" / "state" / "bot-setup.yaml").read_text(encoding="utf-8")
    runtime = (vault / ".backet" / "state" / "bot-config.yaml").read_text(encoding="utf-8")
    assert "guild-a" in runtime
    assert "role-player" in runtime
    assert "channel-canon" in runtime
    assert "bot-token" not in runtime


def test_discord_setup_refuses_user_token(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)

    with pytest.raises(AppError) as error:
        run_discord_setup(vault, token="mfa.user-token", client=DiscordSetupClient(transport=FakeDiscordTransport()))

    assert error.value.code == "bot_setup_discord_user_token_refused"


def test_discord_setup_warns_when_player_role_cannot_use_slash_commands(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    client = DiscordSetupClient(transport=FakeDiscordTransport(player_permissions="1024"))

    result = run_discord_setup(
        vault,
        token="bot-token",
        guild_id="guild-a",
        player_role_ids=["role-player"],
        storyteller_role_ids=["role-st"],
        client=client,
    )

    warnings = result.data["last_phase_result"]["warnings"]
    assert any("Use Application Commands" in warning for warning in warnings)
    assert any("Players" in warning for warning in warnings)


def test_install_url_uses_bot_and_application_command_scopes() -> None:
    url = generate_discord_install_url("123", guild_id="456")

    assert "client_id=123" in url
    assert "applications.commands+bot" in url
    assert "permissions=3072" in url
    assert "guild_id=456" in url


def test_visibility_setup_blocks_empty_player_index_unless_confirmed(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write(vault / "Hidden.md", "storyteller", ["plotline"], "# Hidden\n")

    blocked = run_visibility_setup(vault)
    allowed = run_visibility_setup(vault, allow_empty_player=True)

    assert blocked.data["last_phase_result"]["status"] == "needs_action"
    assert allowed.data["last_phase_result"]["status"] == "done"


def test_github_setup_uses_secrets_via_adapter_and_variables_from_state(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    state = load_or_initialize_setup_state(vault)
    state["discord"]["guild_id"] = "guild-a"
    state["oracle"]["host"] = "203.0.113.10"
    state["oracle"]["user"] = "ubuntu"
    save_bot_setup_state(vault, state)
    adapter = FakeGitHubAdapter(existing_secrets={"DISCORD_TOKEN"})

    result = run_github_setup(
        vault,
        repo="owner/private-vault",
        secret_values={"ORACLE_VM_SSH_KEY": "PRIVATE-KEY-VALUE"},
        adapter=adapter,
    )

    assert result.data["last_phase_result"]["status"] == "done"
    assert adapter.secrets["ORACLE_VM_SSH_KEY"] == "PRIVATE-KEY-VALUE"
    assert adapter.variables["DISCORD_GUILD_ID"] == "guild-a"
    assert adapter.variables["ORACLE_VM_HOST"] == "203.0.113.10"
    assert adapter.variables["BOT_COMPOSE_PROFILES"] == "none"
    assert "PRIVATE-KEY-VALUE" not in (vault / ".backet" / "state" / "bot-setup.yaml").read_text(encoding="utf-8")


def test_github_setup_enables_llama_profile_for_llama_answer_mode(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    state = load_or_initialize_setup_state(vault)
    state["discord"]["guild_id"] = "guild-a"
    state["oracle"]["host"] = "203.0.113.10"
    state["oracle"]["user"] = "ubuntu"
    state["answers"] = {
        "mode": "llama-local",
        "model": {
            "path": "qwen/model.gguf",
            "url": "https://example.test/qwen.gguf",
        },
    }
    save_bot_setup_state(vault, state)
    adapter = FakeGitHubAdapter(existing_secrets={"DISCORD_TOKEN", "ORACLE_VM_SSH_KEY"})

    result = run_github_setup(vault, repo="owner/private-vault", adapter=adapter)

    assert result.data["last_phase_result"]["status"] == "done"
    assert adapter.variables["BOT_COMPOSE_PROFILES"] == "llama"
    assert adapter.variables["LLAMA_MODEL_RELATIVE_PATH"] == "qwen/model.gguf"
    assert adapter.variables["LLAMA_MODEL_URL"] == "https://example.test/qwen.gguf"


def test_github_setup_reports_public_repo_until_confirmed(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    adapter = FakeGitHubAdapter(private=False, existing_secrets={"DISCORD_TOKEN", "ORACLE_VM_SSH_KEY"})

    result = run_github_setup(vault, repo="owner/public-vault", adapter=adapter)

    assert result.data["last_phase_result"]["status"] == "needs_action"
    assert "Public repositories" in result.data["last_phase_result"]["warnings"][0]


def test_github_setup_reports_missing_auth_and_workflow_scope_errors(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)

    missing_auth = run_github_setup(vault, repo="owner/private-vault", adapter=MissingAuthGitHubAdapter())

    assert missing_auth.data["last_phase_result"]["status"] == "needs_action"
    assert "gh auth login" in missing_auth.data["last_phase_result"]["next_actions"][1]

    with pytest.raises(AppError) as error:
        run_github_setup(
            vault,
            repo="owner/private-vault",
            secret_values={"DISCORD_TOKEN": "token"},
            adapter=WorkflowScopeFailGitHubAdapter(),
        )

    assert error.value.code == "bot_setup_github_secret_set_failed"
    assert "workflow" in error.value.hint
    assert "token" not in json.dumps(error.value.details)


def test_oracle_setup_doctors_remote_layout_with_adapter(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    adapter = FakeOracleAdapter()

    result = run_oracle_setup(vault, host="203.0.113.10", user="ubuntu", adapter=adapter)

    assert result.data["last_phase_result"]["status"] == "done"
    assert result.data["oracle"]["host"] == "203.0.113.10"
    assert any("docker compose" in command for command in adapter.commands)


def test_oracle_setup_reports_unreachable_host(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)

    result = run_oracle_setup(vault, host="203.0.113.10", user="ubuntu", adapter=FailingOracleAdapter())

    assert result.data["last_phase_result"]["status"] == "failed"
    assert "SSH validation failed" in result.message


def test_deploy_setup_dispatches_workflow_with_adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _make_vault(tmp_path)
    state = load_or_initialize_setup_state(vault)
    state["github"]["repository"] = "owner/private-vault"
    state["github"]["workflow_file"] = "deploy-backet-bot.yml"
    save_bot_setup_state(vault, state)
    adapter = FakeGitHubAdapter(existing_secrets={"DISCORD_TOKEN", "ORACLE_VM_SSH_KEY"})
    monkeypatch.setattr("backet.bot_setup._git_has_unpushed_or_dirty_changes", lambda: False)

    result = run_deploy_setup(vault, vault_path=".", release_id="test-release", adapter=adapter)

    assert result.data["last_phase_result"]["status"] == "done"
    assert adapter.workflow_inputs == {"vault_path": ".", "release_id": "test-release"}


def test_cli_setup_overview_and_focused_status_are_json_safe(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)

    overview = runner.invoke(app, ["--json", "bot", "setup", str(vault)])
    status = runner.invoke(app, ["--json", "bot", "setup", "status", str(vault)])

    assert overview.exit_code == 0, overview.stdout
    assert status.exit_code == 0, status.stdout
    assert json.loads(overview.stdout)["data"]["phases"]["prerequisites"]["status"] in {"done", "needs_action"}
    assert json.loads(status.stdout)["data"]["setup_state_path"].endswith(".backet/state/bot-setup.yaml")


def test_cli_setup_overview_uses_guided_human_output(runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _make_vault(tmp_path)
    monkeypatch.chdir(vault)

    result = runner.invoke(app, ["bot", "setup"])

    assert result.exit_code == 0, result.output
    assert "Backet bot setup" in result.output
    assert "Progress" in result.output
    assert "What To Do Next" in result.output
    assert "local deployment files from the prerequisites step" in result.output
    assert "backet bot setup files" not in result.output
    assert "phases:" not in result.output
    assert "last_phase_result:" not in result.output
    assert "{'prerequisites'" not in result.output


def test_setup_files_installs_private_deploy_workflow_and_assets(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    repo_root = tmp_path / "private-repo"

    result = runner.invoke(app, ["bot", "setup", "files", str(vault), "--repo-root", str(repo_root)])

    assert result.exit_code == 0, result.output
    assert (repo_root / ".github/workflows/deploy-backet-bot.yml").exists()
    assert (repo_root / "deploy/bot/Dockerfile").exists()
    assert (repo_root / "deploy/bot/docker-compose.yml").exists()
    assert (repo_root / "deploy/bot/activate-release.sh").exists()
    workflow = (repo_root / ".github/workflows/deploy-backet-bot.yml").read_text(encoding="utf-8")
    dockerfile = (repo_root / "deploy/bot/Dockerfile").read_text(encoding="utf-8")
    assert "backet[bot] @ https://github.com/jsvitkin/backet/releases/download/v0.1.27/backet-0.1.27-py3-none-any.whl" in workflow
    assert "backet[bot] @ https://github.com/jsvitkin/backet/releases/download/v0.1.27/backet-0.1.27-py3-none-any.whl" in dockerfile
    state = load_or_initialize_setup_state(vault)
    assert state["setup"]["phases"]["prerequisites"]["status"] == "done"
    assert "Deployment Files" in result.output
    assert "phases:" not in result.output


def test_cli_setup_guided_installs_missing_deploy_files_before_stopping(runner, tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    repo_root = tmp_path / "private-repo"

    result = runner.invoke(
        app,
        ["bot", "setup", "--guided", "--repo-root", str(repo_root), str(vault)],
        input="y\nn\n",
    )

    assert result.exit_code == 0, result.output
    assert "Backet bot setup wizard" in result.output
    assert "Install or refresh those deployment files now?" in result.output
    assert "Continue to the next setup phase?" in result.output
    assert (repo_root / ".github/workflows/deploy-backet-bot.yml").exists()
    assert (repo_root / "deploy/bot/docker-compose.yml").exists()
    assert "phases:" not in result.output
    assert "{'prerequisites'" not in result.output


def test_setup_files_refuses_to_overwrite_changed_files_without_force(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    repo_root = tmp_path / "private-repo"
    install_deployment_repository_files(vault, repo_root=repo_root)
    workflow = repo_root / ".github/workflows/deploy-backet-bot.yml"
    workflow.write_text("custom workflow\n", encoding="utf-8")

    result = install_deployment_repository_files(vault, repo_root=repo_root)
    forced = install_deployment_repository_files(vault, repo_root=repo_root, force=True)

    assert result.issues
    assert ".github/workflows/deploy-backet-bot.yml" in result.data["repository_files"]["skipped"]
    assert ".github/workflows/deploy-backet-bot.yml" in forced.fixed
    assert "custom workflow" not in workflow.read_text(encoding="utf-8")


class FakeDiscordTransport:
    def __init__(self, player_permissions: str = "2147483648") -> None:
        self.player_permissions = player_permissions

    def get(self, path: str, token: str) -> Any:
        assert token == "bot-token"
        if path == "/oauth2/applications/@me":
            return {"id": "app-a", "name": "Backet Bot", "bot_public": False, "bot_require_code_grant": False}
        if path == "/users/@me":
            return {"id": "bot-user-a", "username": "Backet"}
        if path == "/users/@me/guilds":
            return [{"id": "guild-a", "name": "Prague by Night"}]
        if path == "/guilds/guild-a/roles":
            return [
                {"id": "role-player", "name": "Players", "permissions": self.player_permissions},
                {"id": "role-st", "name": "Storyteller", "permissions": "2147483656"},
            ]
        if path == "/guilds/guild-a/channels":
            return [{"id": "channel-canon", "name": "canon", "type": 0}]
        raise AssertionError(path)


class FakeGitHubAdapter:
    def __init__(self, private: bool = True, existing_secrets: set[str] | None = None) -> None:
        self.private = private
        self.existing_secrets = set(existing_secrets or set())
        self.secrets: dict[str, str] = {}
        self.variables: dict[str, str] = {}
        self.workflow_inputs: dict[str, str] | None = None

    def auth_status(self) -> AdapterResult:
        return AdapterResult(ok=True)

    def repo_view(self, repo: str) -> dict[str, Any]:
        return {"nameWithOwner": repo, "isPrivate": self.private}

    def list_secret_names(self, repo: str) -> set[str]:
        return set(self.existing_secrets) | set(self.secrets)

    def set_secret(self, repo: str, name: str, value: str) -> AdapterResult:
        self.secrets[name] = value
        return AdapterResult(ok=True)

    def set_variable(self, repo: str, name: str, value: str) -> AdapterResult:
        self.variables[name] = value
        return AdapterResult(ok=True)

    def workflow_exists(self, repo: str, workflow_file: str) -> bool:
        return True

    def workflow_run(self, repo: str, workflow_file: str, inputs: dict[str, str]) -> AdapterResult:
        self.workflow_inputs = dict(inputs)
        return AdapterResult(ok=True, stdout="run url: https://github.test/run/1")

    def run_watch(self, repo: str) -> AdapterResult:
        return AdapterResult(ok=True)


class MissingAuthGitHubAdapter(FakeGitHubAdapter):
    def auth_status(self) -> AdapterResult:
        return AdapterResult(ok=False, stderr="not logged in", returncode=1)


class WorkflowScopeFailGitHubAdapter(FakeGitHubAdapter):
    def set_secret(self, repo: str, name: str, value: str) -> AdapterResult:
        return AdapterResult(ok=False, stderr=f"missing workflow scope for {value}", returncode=1)


class FakeOracleAdapter:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def run(self, host: str, user: str, command: str, key_path: Path | None = None) -> AdapterResult:
        self.commands.append(command)
        if "uname -s" in command:
            return AdapterResult(ok=True, stdout="os=Linux\nuser=ubuntu\n")
        if "docker compose" in command:
            return AdapterResult(ok=True, stdout="ok\n")
        return AdapterResult(ok=True)


class FailingOracleAdapter:
    def run(self, host: str, user: str, command: str, key_path: Path | None = None) -> AdapterResult:
        return AdapterResult(ok=False, stderr="permission denied", returncode=255)


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    initialize_vault(vault, cli_version="0.1.0")
    return vault


def _write(path: Path, visibility: str, topics: list[str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    topic_lines = "".join(f"    - {topic}\n" for topic in topics)
    topics_block = f"  bot_topics:\n{topic_lines}" if topics else ""
    path.write_text(f"---\nbacket:\n  visibility: {visibility}\n{topics_block}---\n\n{body}\n", encoding="utf-8")
