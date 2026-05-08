from __future__ import annotations

import getpass
import importlib.resources
import json
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yaml

from backet import __version__
from backet.bot_access import BotCommandPolicy, load_bot_config, scan_bot_visibility, summarize_visibility
from backet.distribution import load_distribution_metadata
from backet.errors import AppError
from backet.models import CommandResult, Issue
from backet.paths import bot_config_path, bot_setup_path, rules_db_path, state_dir
from backet.vault import ensure_bootstrapped_vault

BOT_SETUP_SCHEMA_VERSION = 1
DEFAULT_DEPLOY_PATH = "/srv/backet-bot"
DEFAULT_WORKFLOW_FILE = "deploy-backet-bot.yml"
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_PORTAL_URL = "https://discord.com/developers/applications"
DISCORD_PERMISSION_VIEW_CHANNEL = 1 << 10
DISCORD_PERMISSION_SEND_MESSAGES = 1 << 11
DISCORD_PERMISSION_USE_APPLICATION_COMMANDS = 1 << 31
# View Channels + Send Messages. Slash commands come from the applications.commands
# scope, but private campaign channels still need the bot/app to be visible there.
DISCORD_INSTALL_PERMISSIONS = str(DISCORD_PERMISSION_VIEW_CHANNEL | DISCORD_PERMISSION_SEND_MESSAGES)

SETUP_PHASES = ("prerequisites", "discord", "visibility", "github", "oracle", "deploy")
PHASE_DONE = "done"
PHASE_PENDING = "pending"
PHASE_NEEDS_ACTION = "needs_action"
PHASE_FAILED = "failed"

DEFAULT_SECRET_NAMES = ("DISCORD_TOKEN", "ORACLE_VM_SSH_KEY")
OPTIONAL_SECRET_NAMES = ("MODEL_DOWNLOAD_TOKEN",)
DEFAULT_VARIABLE_NAMES = (
    "DISCORD_GUILD_ID",
    "ORACLE_VM_HOST",
    "ORACLE_VM_USER",
    "BOT_COMPOSE_PROFILES",
    "LLAMA_MODEL_RELATIVE_PATH",
    "LLAMA_MODEL_SHA256",
    "LLAMA_MODEL_URL",
)
REQUIRED_VARIABLE_NAMES = ("DISCORD_GUILD_ID", "ORACLE_VM_HOST", "ORACLE_VM_USER")
DEPLOY_REPOSITORY_FILES = (
    ".github/workflows/deploy-backet-bot.yml",
    "deploy/bot/Dockerfile",
    "deploy/bot/activate-release.sh",
    "deploy/bot/bootstrap-llama-model.sh",
    "deploy/bot/docker-compose.yml",
    "deploy/bot/env.example",
    "deploy/bot/smoke-test.sh",
)
SECRET_VALUE_KEYS = {
    "token",
    "discord_token",
    "ssh_key",
    "ssh_private_key",
    "private_key",
    "password",
    "secret",
    "model_download_token",
}


class GitHubAdapter(Protocol):
    def auth_status(self) -> AdapterResult: ...

    def repo_view(self, repo: str) -> dict[str, Any]: ...

    def list_secret_names(self, repo: str) -> set[str]: ...

    def set_secret(self, repo: str, name: str, value: str) -> AdapterResult: ...

    def set_variable(self, repo: str, name: str, value: str) -> AdapterResult: ...

    def workflow_exists(self, repo: str, workflow_file: str) -> bool: ...

    def workflow_run(self, repo: str, workflow_file: str, inputs: dict[str, str]) -> AdapterResult: ...

    def run_watch(self, repo: str) -> AdapterResult: ...


class OracleAdapter(Protocol):
    def run(self, host: str, user: str, command: str, key_path: Path | None = None) -> AdapterResult: ...


class DiscordTransport(Protocol):
    def get(self, path: str, token: str) -> Any: ...


@dataclass(slots=True)
class AdapterResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0

    def redacted(self, redactor: Redactor) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stdout": redactor.text(self.stdout),
            "stderr": redactor.text(self.stderr),
            "returncode": self.returncode,
        }


@dataclass(slots=True)
class Redactor:
    values: tuple[str, ...] = ()

    def text(self, value: Any) -> str:
        text = str(value)
        for secret in self.values:
            if secret:
                text = text.replace(secret, "[REDACTED]")
        text = re.sub(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            "[REDACTED_PRIVATE_KEY]",
            text,
            flags=re.DOTALL,
        )
        text = re.sub(r"mfa\.[A-Za-z0-9_-]+", "[REDACTED_TOKEN]", text)
        text = re.sub(r"(?i)(DISCORD_TOKEN|MODEL_DOWNLOAD_TOKEN|ORACLE_VM_SSH_KEY)=\S+", r"\1=[REDACTED]", text)
        return text

    def data(self, value: Any) -> Any:
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for key, item in value.items():
                if _is_secret_value_key(str(key)):
                    redacted[str(key)] = "[REDACTED]"
                else:
                    redacted[str(key)] = self.data(item)
            return redacted
        if isinstance(value, list):
            return [self.data(item) for item in value]
        if isinstance(value, tuple):
            return [self.data(item) for item in value]
        if isinstance(value, str):
            return self.text(value)
        return value


@dataclass(slots=True)
class SetupPhaseResult:
    phase: str
    status: str
    message: str
    next_actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "status": self.status,
            "message": self.message,
            "next_actions": self.next_actions,
            "warnings": self.warnings,
            "data": self.data,
        }


class DiscordSetupClient:
    def __init__(self, transport: DiscordTransport | None = None, api_base: str = DISCORD_API_BASE) -> None:
        self.transport = transport or UrllibDiscordTransport(api_base=api_base)

    def validate_bot_token(self, token: str) -> dict[str, Any]:
        normalized = normalize_discord_bot_token(token)
        application = self.transport.get("/oauth2/applications/@me", normalized)
        user = self.transport.get("/users/@me", normalized)
        app_id = _coerce_discord_id(application.get("id") or application.get("application", {}).get("id"))
        bot_user_id = _coerce_discord_id(user.get("id") or application.get("bot", {}).get("id"))
        if not app_id or not bot_user_id:
            raise AppError(
                code="bot_setup_discord_identity_missing",
                message="Discord did not return a complete bot application identity.",
                hint="Check that the provided value is a Discord bot token.",
                exit_code=2,
            )
        return {
            "app_id": app_id,
            "app_name": str(application.get("name") or application.get("application", {}).get("name") or ""),
            "bot_user_id": bot_user_id,
            "bot_username": str(user.get("username") or application.get("bot", {}).get("username") or ""),
            "bot_public": bool(application.get("bot_public", False)),
            "requires_code_grant": bool(application.get("bot_require_code_grant", False)),
        }

    def list_guilds(self, token: str) -> list[dict[str, Any]]:
        normalized = normalize_discord_bot_token(token)
        payload = self.transport.get("/users/@me/guilds", normalized)
        if not isinstance(payload, list):
            return []
        return [_safe_discord_object(item, ("id", "name")) for item in payload if isinstance(item, dict)]

    def list_channels(self, token: str, guild_id: str) -> list[dict[str, Any]]:
        normalized = normalize_discord_bot_token(token)
        payload = self.transport.get(f"/guilds/{guild_id}/channels", normalized)
        if not isinstance(payload, list):
            return []
        return [_safe_discord_object(item, ("id", "name", "type")) for item in payload if isinstance(item, dict)]

    def list_roles(self, token: str, guild_id: str) -> list[dict[str, Any]]:
        normalized = normalize_discord_bot_token(token)
        payload = self.transport.get(f"/guilds/{guild_id}/roles", normalized)
        if not isinstance(payload, list):
            return []
        return [_safe_discord_object(item, ("id", "name", "permissions")) for item in payload if isinstance(item, dict)]


class UrllibDiscordTransport:
    def __init__(self, api_base: str = DISCORD_API_BASE, timeout_seconds: int = 20) -> None:
        self.api_base = api_base.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get(self, path: str, token: str) -> Any:
        request = Request(
            f"{self.api_base}{path}",
            headers={
                "Authorization": f"Bot {token}",
                "User-Agent": "backet-bot-setup",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise AppError(
                code="bot_setup_discord_api_error",
                message="Discord API rejected the setup request.",
                hint="Check the bot token, guild install, and bot permissions.",
                details={"status": exc.code, "path": path},
                exit_code=2,
            ) from exc
        except URLError as exc:
            raise AppError(
                code="bot_setup_discord_network_error",
                message="Could not reach Discord while validating bot setup.",
                hint="Check your network connection and try again.",
                details={"path": path, "reason": str(exc.reason)},
                exit_code=2,
            ) from exc
        return json.loads(body) if body else {}


class GitHubCli:
    def __init__(self, executable: str = "gh", redactor: Redactor | None = None) -> None:
        self.executable = executable
        self.redactor = redactor or Redactor()

    def auth_status(self) -> AdapterResult:
        if shutil.which(self.executable) is None:
            return AdapterResult(ok=False, stderr="gh is not installed", returncode=127)
        return self._run(["auth", "status"])

    def repo_view(self, repo: str) -> dict[str, Any]:
        result = self._run(["repo", "view", repo, "--json", "nameWithOwner,isPrivate"])
        if not result.ok:
            _raise_gh_error("bot_setup_github_repo_view_failed", "Could not inspect the GitHub repository.", result, self.redactor)
        payload = json.loads(result.stdout or "{}")
        return {
            "nameWithOwner": str(payload.get("nameWithOwner") or repo),
            "isPrivate": bool(payload.get("isPrivate", False)),
        }

    def list_secret_names(self, repo: str) -> set[str]:
        result = self._run(["secret", "list", "--repo", repo, "--json", "name"])
        if not result.ok:
            _raise_gh_error("bot_setup_github_secret_list_failed", "Could not list GitHub secret names.", result, self.redactor)
        payload = json.loads(result.stdout or "[]")
        return {str(item.get("name")) for item in payload if isinstance(item, dict) and item.get("name")}

    def set_secret(self, repo: str, name: str, value: str) -> AdapterResult:
        return self._run(["secret", "set", name, "--repo", repo], stdin=value)

    def set_variable(self, repo: str, name: str, value: str) -> AdapterResult:
        return self._run(["variable", "set", name, "--repo", repo, "--body", value])

    def workflow_exists(self, repo: str, workflow_file: str) -> bool:
        result = self._run(["workflow", "view", workflow_file, "--repo", repo])
        return result.ok

    def workflow_run(self, repo: str, workflow_file: str, inputs: dict[str, str]) -> AdapterResult:
        args = ["workflow", "run", workflow_file, "--repo", repo]
        for key, value in sorted(inputs.items()):
            args.extend(["-f", f"{key}={value}"])
        return self._run(args)

    def run_watch(self, repo: str) -> AdapterResult:
        return self._run(["run", "watch", "--repo", repo])

    def _run(self, args: list[str], stdin: str | None = None) -> AdapterResult:
        completed = subprocess.run(
            [self.executable, *args],
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
        )
        return AdapterResult(
            ok=completed.returncode == 0,
            stdout=self.redactor.text(completed.stdout),
            stderr=self.redactor.text(completed.stderr),
            returncode=completed.returncode,
        )


class SshOracleAdapter:
    def __init__(self, executable: str = "ssh", redactor: Redactor | None = None) -> None:
        self.executable = executable
        self.redactor = redactor or Redactor()

    def run(self, host: str, user: str, command: str, key_path: Path | None = None) -> AdapterResult:
        if shutil.which(self.executable) is None:
            return AdapterResult(ok=False, stderr="ssh is not installed", returncode=127)
        args = [self.executable]
        if key_path is not None:
            args.extend(["-i", str(key_path)])
        args.extend(["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", f"{user}@{host}", command])
        completed = subprocess.run(args, text=True, capture_output=True, check=False)
        return AdapterResult(
            ok=completed.returncode == 0,
            stdout=self.redactor.text(completed.stdout),
            stderr=self.redactor.text(completed.stderr),
            returncode=completed.returncode,
        )


def setup_status(vault_root: Path, save: bool = True) -> CommandResult:
    state = load_or_initialize_setup_state(vault_root, save=save)
    status = _setup_status_payload(vault_root, state)
    return CommandResult(message="Backet bot setup status", issues=_issues_from_status(status), data=status)


def run_setup_overview(vault_root: Path) -> CommandResult:
    state = load_or_initialize_setup_state(vault_root, save=True)
    result = _prerequisites_phase(vault_root, state)
    save_bot_setup_state(vault_root, state)
    status = _setup_status_payload(vault_root, state)
    status["last_phase_result"] = result.to_dict()
    return CommandResult(message="Backet bot setup started", issues=_issues_from_status(status), data=status)


def resume_setup(vault_root: Path) -> CommandResult:
    state = load_or_initialize_setup_state(vault_root, save=True)
    next_phase = _next_pending_phase(state)
    next_actions = [f"Run `backet bot setup {next_phase} <vault>` to continue."] if next_phase else []
    data = _setup_status_payload(vault_root, state)
    data["resume_phase"] = next_phase
    data["next_actions"] = next_actions or ["All setup phases are complete."]
    return CommandResult(message="Backet bot setup resume point", data=data)


def reset_setup_state(vault_root: Path, yes: bool = False) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    path = bot_setup_path(vault_root)
    if not path.exists():
        return CommandResult(message="Backet bot setup state already absent", data={"vault": str(vault_root), "removed": False})
    if not yes:
        raise AppError(
            code="bot_setup_reset_confirmation_required",
            message="Resetting bot setup state requires confirmation.",
            hint="Re-run with --yes. This removes only committed-safe setup state, not GitHub secrets.",
            details={"path": str(path.relative_to(vault_root))},
            exit_code=2,
        )
    path.unlink()
    return CommandResult(
        message="Backet bot setup state reset",
        data={
            "vault": str(vault_root),
            "removed": True,
            "removed_path": str(path.relative_to(vault_root)),
            "secrets_untouched": True,
        },
    )


def install_deployment_repository_files(
    vault_root: Path,
    repo_root: Path | None = None,
    force: bool = False,
) -> CommandResult:
    ensure_bootstrapped_vault(vault_root)
    resolved_repo_root = _resolve_deploy_repo_root(vault_root, repo_root)
    created: list[str] = []
    fixed: list[str] = []
    unchanged: list[str] = []
    skipped: list[str] = []
    issues: list[Issue] = []

    for relative in DEPLOY_REPOSITORY_FILES:
        target = resolved_repo_root / relative
        content = _render_deploy_repository_file(relative)
        if target.exists():
            if target.read_bytes() == content:
                unchanged.append(relative)
                continue
            if not force:
                skipped.append(relative)
                issues.append(
                    Issue(
                        code="bot_setup_deploy_file_exists",
                        severity="warning",
                        message="Deployment file already exists and differs from the packaged template.",
                        path=relative,
                        hint="Review it, then rerun `backet bot setup files <vault> --force-files` if Backet should overwrite it.",
                        safe_to_fix=False,
                    )
                )
                continue
            fixed.append(relative)
        else:
            created.append(relative)

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        if relative.endswith(".sh"):
            target.chmod(0o755)

    state = load_or_initialize_setup_state(vault_root, save=True)
    result = _prerequisites_phase(vault_root, state, repo_root=resolved_repo_root)
    save_bot_setup_state(vault_root, state)

    next_actions = [
        "Review the created deployment files.",
        "Commit and push `.github/workflows/deploy-backet-bot.yml` and `deploy/bot/*` to the private vault repository.",
        f"Continue with `backet bot setup discord {shlex.quote(str(vault_root))}`.",
    ]
    if skipped:
        next_actions.insert(0, "Resolve or overwrite skipped deployment files before deploying.")

    status = _setup_status_payload(vault_root, state)
    status["last_phase_result"] = result.to_dict()
    status["repository_files"] = {
        "repo_root": str(resolved_repo_root),
        "created": created,
        "updated": fixed,
        "unchanged": unchanged,
        "skipped": skipped,
        "next_actions": next_actions,
    }
    return CommandResult(
        message="Backet bot deployment files checked",
        created=created,
        fixed=fixed,
        issues=issues,
        data=status,
    )


def run_discord_setup(
    vault_root: Path,
    token: str | None = None,
    guild_id: str | None = None,
    player_role_ids: list[str] | None = None,
    storyteller_role_ids: list[str] | None = None,
    canon_channel_ids: list[str] | None = None,
    client: DiscordSetupClient | None = None,
) -> CommandResult:
    redactor = Redactor((token or "",))
    state = load_or_initialize_setup_state(vault_root, save=True)
    discord_state = dict(state.get("discord", {}))
    phase_data: dict[str, Any] = {
        "developer_portal_url": DISCORD_PORTAL_URL,
        "required_scopes": ["applications.commands", "bot"],
        "message_content_intent": "disabled",
    }
    warnings: list[str] = []
    next_actions: list[str] = []

    if token:
        setup_client = client or DiscordSetupClient()
        identity = setup_client.validate_bot_token(token)
        discord_state.update(identity)
        discord_state["invite_url"] = generate_discord_install_url(identity["app_id"])
        phase_data["identity"] = identity
        phase_data["invite_url"] = discord_state["invite_url"]
        if identity.get("bot_public"):
            warnings.append("Discord reports this bot as public; restrict installation in the Developer Portal where possible.")
        if identity.get("requires_code_grant"):
            warnings.append("Discord reports this bot requires code grant; disable that for a private slash-command bot.")

        guilds = setup_client.list_guilds(token)
        phase_data["guilds"] = guilds
        selected_guild = _select_discord_object(guilds, guild_id)
        if selected_guild is not None:
            discord_state["guild_id"] = selected_guild["id"]
            discord_state["guild_name"] = selected_guild.get("name", "")
            roles = setup_client.list_roles(token, selected_guild["id"])
            channels = setup_client.list_channels(token, selected_guild["id"])
            phase_data["roles"] = roles
            phase_data["channels"] = channels
        elif guild_id:
            raise AppError(
                code="bot_setup_discord_guild_missing",
                message="The configured Discord guild is not visible to the bot.",
                hint="Install the app into that server, then rerun Discord setup.",
                details={"guild_id": guild_id},
                exit_code=2,
            )
        elif guilds:
            next_actions.append("Choose a Discord guild with `--guild-id`, then rerun Discord setup.")
        else:
            next_actions.append("Open the install URL, add the bot to your private server, then rerun Discord setup.")
    else:
        phase_data["invite_url"] = discord_state.get("invite_url")
        if not discord_state.get("app_id"):
            next_actions.extend(
                [
                    "Open the Discord Developer Portal and create an application with a bot user.",
                    "Copy the bot token and rerun with `--token-stdin` so Backet can validate it without storing it.",
                ]
            )

    selected_roles = dict(discord_state.get("selected_role_ids", {}) or {})
    if player_role_ids:
        selected_roles["player"] = _dedupe_strings(player_role_ids)
    if storyteller_role_ids:
        selected_roles["storyteller"] = _dedupe_strings(storyteller_role_ids)
    if selected_roles:
        discord_state["selected_role_ids"] = selected_roles
    if phase_data.get("roles"):
        warnings.extend(_discord_role_permission_warnings(selected_roles, list(phase_data["roles"])))

    selected_channels = dict(discord_state.get("selected_channel_ids", {}) or {})
    if canon_channel_ids:
        selected_channels["canon"] = _dedupe_strings(canon_channel_ids)
    if selected_channels:
        discord_state["selected_channel_ids"] = selected_channels

    state["discord"] = discord_state
    _sync_runtime_config_from_setup(vault_root, state)

    required = [discord_state.get("app_id"), discord_state.get("bot_user_id"), discord_state.get("guild_id")]
    roles_ready = bool(selected_roles.get("player")) and bool(selected_roles.get("storyteller"))
    status = PHASE_DONE if all(required) and roles_ready else PHASE_NEEDS_ACTION
    if status != PHASE_DONE and not next_actions:
        next_actions.append("Select the Discord guild, player role, Storyteller role, and allowed channels, then rerun setup.")
    result = SetupPhaseResult(
        phase="discord",
        status=status,
        message="Discord setup checked" if status != PHASE_DONE else "Discord setup complete",
        next_actions=next_actions,
        warnings=warnings,
        data=redactor.data(phase_data),
    )
    _record_phase(state, result)
    save_bot_setup_state(vault_root, state)
    return _phase_command_result(vault_root, state, result)


def run_visibility_setup(vault_root: Path, allow_empty_player: bool = False) -> CommandResult:
    state = load_or_initialize_setup_state(vault_root, save=True)
    decisions = scan_bot_visibility(vault_root)
    summary = summarize_visibility(decisions)
    warnings: list[str] = []
    next_actions: list[str] = []
    status = PHASE_DONE
    if summary["player_index_notes"] == 0:
        warnings.append("No notes are explicitly player-visible for bot export.")
        if not allow_empty_player:
            status = PHASE_NEEDS_ACTION
            next_actions.append(
                "Open the guided visibility editor and mark player-facing notes, or explicitly allow empty player canon."
            )
    data = {
        "summary": {
            **summary,
            "invalid_topic_notes": 0,
        },
        "rules_db_present": rules_db_path(vault_root).exists(),
        "player_can_query": ["rules", "canon"] if summary["player_index_notes"] else ["rules"],
    }
    result = SetupPhaseResult(
        phase="visibility",
        status=status,
        message="Bot visibility review complete" if status == PHASE_DONE else "Bot visibility needs attention",
        next_actions=next_actions,
        warnings=warnings,
        data=data,
    )
    _record_phase(state, result)
    save_bot_setup_state(vault_root, state)
    return _phase_command_result(vault_root, state, result)


def run_github_setup(
    vault_root: Path,
    repo: str | None = None,
    secret_values: dict[str, str] | None = None,
    variable_overrides: dict[str, str] | None = None,
    sensitive_variables: list[str] | None = None,
    allow_public: bool = False,
    adapter: GitHubAdapter | None = None,
) -> CommandResult:
    redactor = Redactor(tuple((secret_values or {}).values()))
    state = load_or_initialize_setup_state(vault_root, save=True)
    github_state = dict(state.get("github", {}) or {})
    if repo:
        github_state["repository"] = repo
    repository = str(github_state.get("repository") or "")
    if not repository:
        result = SetupPhaseResult(
            phase="github",
            status=PHASE_NEEDS_ACTION,
            message="GitHub setup needs a repository.",
            next_actions=["Rerun with `--repo owner/repo` for the private vault repository."],
            data={"required_secrets": list(DEFAULT_SECRET_NAMES), "required_variables": list(DEFAULT_VARIABLE_NAMES)},
        )
        _record_phase(state, result)
        save_bot_setup_state(vault_root, state)
        return _phase_command_result(vault_root, state, result)

    gh = adapter or GitHubCli(redactor=redactor)
    auth = gh.auth_status()
    if not auth.ok:
        result = SetupPhaseResult(
            phase="github",
            status=PHASE_NEEDS_ACTION,
            message="GitHub CLI is not ready.",
            next_actions=[
                "Install GitHub CLI if needed.",
                "Run `gh auth login`, or `gh auth refresh -h github.com -s repo -s workflow` if workflow access is missing.",
            ],
            data={"auth": auth.redacted(redactor), "repository": repository},
        )
        _record_phase(state, result)
        save_bot_setup_state(vault_root, state)
        return _phase_command_result(vault_root, state, result)

    repo_meta = gh.repo_view(repository)
    warnings: list[str] = []
    next_actions: list[str] = []
    if not repo_meta.get("isPrivate", False) and not allow_public:
        result = SetupPhaseResult(
            phase="github",
            status=PHASE_NEEDS_ACTION,
            message="GitHub repository privacy needs confirmation.",
            next_actions=["Use a private repository, or rerun with --allow-public-repo if you accept the risk."],
            warnings=["Public repositories can expose committed setup state and private workflow artifacts."],
            data={"repository": repo_meta},
        )
        _record_phase(state, result)
        save_bot_setup_state(vault_root, state)
        return _phase_command_result(vault_root, state, result)

    secret_values = secret_values or {}
    configured_secret_names = set(github_state.get("secret_names", [])) | gh.list_secret_names(repository)
    for secret_name, value in sorted(secret_values.items()):
        result = gh.set_secret(repository, secret_name, value)
        if not result.ok:
            _raise_gh_error("bot_setup_github_secret_set_failed", f"Could not set GitHub secret {secret_name}.", result, redactor)
        configured_secret_names.add(secret_name)

    variables = _github_variables_from_state(state)
    variables.update(variable_overrides or {})
    configured_variable_names = set(github_state.get("variable_names", []))
    sensitive = set(sensitive_variables or [])
    for name, value in sorted(variables.items()):
        if name in sensitive:
            result = gh.set_secret(repository, name, value)
            if not result.ok:
                _raise_gh_error("bot_setup_github_secret_set_failed", f"Could not set GitHub secret {name}.", result, redactor)
            configured_secret_names.add(name)
            continue
        result = gh.set_variable(repository, name, value)
        if not result.ok:
            _raise_gh_error("bot_setup_github_variable_set_failed", f"Could not set GitHub variable {name}.", result, redactor)
        configured_variable_names.add(name)

    workflow_file = str(github_state.get("workflow_file") or DEFAULT_WORKFLOW_FILE)
    local_workflow = Path(".github/workflows") / workflow_file
    if not local_workflow.exists():
        warnings.append(f"Local workflow file is missing: {local_workflow.as_posix()}")
        next_actions.append("Add the private bot deploy workflow before deployment.")
    elif not gh.workflow_exists(repository, workflow_file):
        warnings.append("GitHub could not see the deploy workflow yet.")
        next_actions.append("Commit and push `.github/workflows/deploy-backet-bot.yml`; refresh auth with workflow scope if push is rejected.")

    github_state.update(
        {
            "repository": repository,
            "workflow_file": workflow_file,
            "secret_names": sorted(configured_secret_names),
            "variable_names": sorted(configured_variable_names),
        }
    )
    state["github"] = github_state

    missing_required = sorted(name for name in DEFAULT_SECRET_NAMES if name not in configured_secret_names)
    missing_required_variables = sorted(name for name in REQUIRED_VARIABLE_NAMES if name not in variables)
    if missing_required:
        next_actions.append(f"Configure missing GitHub secrets: {', '.join(missing_required)}.")
    if missing_required_variables:
        next_actions.append(
            "Complete Discord and Oracle setup so Backet can configure GitHub variables: "
            + ", ".join(missing_required_variables)
            + "."
        )
    status = PHASE_DONE if not missing_required and not missing_required_variables and not next_actions else PHASE_NEEDS_ACTION
    result = SetupPhaseResult(
        phase="github",
        status=status,
        message="GitHub setup complete" if status == PHASE_DONE else "GitHub setup needs action",
        next_actions=next_actions,
        warnings=warnings,
        data={
            "repository": repo_meta,
            "secrets": {name: ("configured" if name in configured_secret_names else "missing") for name in DEFAULT_SECRET_NAMES},
            "variables": {
                name: ("configured" if name in configured_variable_names else "missing")
                for name in sorted(set(DEFAULT_VARIABLE_NAMES) | set(variables))
            },
            "workflow_file": workflow_file,
        },
    )
    _record_phase(state, result)
    save_bot_setup_state(vault_root, state)
    return _phase_command_result(vault_root, state, result)


def run_oracle_setup(
    vault_root: Path,
    host: str | None = None,
    user: str | None = None,
    deploy_path: str = DEFAULT_DEPLOY_PATH,
    ssh_key_path: Path | None = None,
    bootstrap: bool = False,
    adapter: OracleAdapter | None = None,
) -> CommandResult:
    state = load_or_initialize_setup_state(vault_root, save=True)
    oracle_state = dict(state.get("oracle", {}) or {})
    if host:
        oracle_state["host"] = host
    if user:
        oracle_state["user"] = user
    oracle_state["deploy_path"] = deploy_path or str(oracle_state.get("deploy_path") or DEFAULT_DEPLOY_PATH)
    state["oracle"] = oracle_state
    resolved_host = str(oracle_state.get("host") or "")
    resolved_user = str(oracle_state.get("user") or "")
    if not resolved_host or not resolved_user:
        result = SetupPhaseResult(
            phase="oracle",
            status=PHASE_NEEDS_ACTION,
            message="Oracle VM setup needs SSH target details.",
            next_actions=["Rerun with `--host` and `--user`; pass the SSH private key to GitHub secrets during GitHub setup."],
            data={"deploy_path": oracle_state["deploy_path"]},
        )
        _record_phase(state, result)
        save_bot_setup_state(vault_root, state)
        return _phase_command_result(vault_root, state, result)

    ssh = adapter or SshOracleAdapter()
    os_check = ssh.run(resolved_host, resolved_user, "printf 'os='; uname -s; printf 'user='; whoami", key_path=ssh_key_path)
    if not os_check.ok:
        result = SetupPhaseResult(
            phase="oracle",
            status=PHASE_FAILED,
            message="Oracle VM SSH validation failed.",
            next_actions=["Check host, user, firewall, and SSH key configuration, then rerun Oracle setup."],
            data={"ssh": os_check.redacted(Redactor()), "host": resolved_host, "user": resolved_user},
        )
        _record_phase(state, result)
        save_bot_setup_state(vault_root, state)
        return _phase_command_result(vault_root, state, result)

    if bootstrap:
        bootstrap_command = _oracle_bootstrap_command(str(oracle_state["deploy_path"]))
        bootstrap_result = ssh.run(resolved_host, resolved_user, bootstrap_command, key_path=ssh_key_path)
        if not bootstrap_result.ok:
            result = SetupPhaseResult(
                phase="oracle",
                status=PHASE_FAILED,
                message="Oracle VM bootstrap failed.",
                next_actions=["Review the remote permissions and rerun with --bootstrap when fixed."],
                data={"bootstrap": bootstrap_result.redacted(Redactor())},
            )
            _record_phase(state, result)
            save_bot_setup_state(vault_root, state)
            return _phase_command_result(vault_root, state, result)

    doctor_command = _oracle_doctor_command(str(oracle_state["deploy_path"]))
    doctor = ssh.run(resolved_host, resolved_user, doctor_command, key_path=ssh_key_path)
    status = PHASE_DONE if doctor.ok else PHASE_NEEDS_ACTION
    next_actions = [] if doctor.ok else ["Rerun Oracle setup with --bootstrap, or create the missing deploy layout on the VM."]
    result = SetupPhaseResult(
        phase="oracle",
        status=status,
        message="Oracle VM setup complete" if doctor.ok else "Oracle VM deploy layout needs action",
        next_actions=next_actions,
        data={
            "host": resolved_host,
            "user": resolved_user,
            "deploy_path": oracle_state["deploy_path"],
            "ssh": os_check.redacted(Redactor()),
            "doctor": doctor.redacted(Redactor()),
        },
    )
    _record_phase(state, result)
    save_bot_setup_state(vault_root, state)
    return _phase_command_result(vault_root, state, result)


def run_deploy_setup(
    vault_root: Path,
    vault_path: str = ".",
    release_id: str | None = None,
    watch: bool = False,
    allow_dirty: bool = False,
    adapter: GitHubAdapter | None = None,
) -> CommandResult:
    state = load_or_initialize_setup_state(vault_root, save=True)
    github_state = dict(state.get("github", {}) or {})
    repository = str(github_state.get("repository") or "")
    workflow_file = str(github_state.get("workflow_file") or DEFAULT_WORKFLOW_FILE)
    if not repository:
        result = SetupPhaseResult(
            phase="deploy",
            status=PHASE_NEEDS_ACTION,
            message="Deployment needs GitHub setup first.",
            next_actions=["Run `backet bot setup github <vault> --repo owner/repo` first."],
        )
        _record_phase(state, result)
        save_bot_setup_state(vault_root, state)
        return _phase_command_result(vault_root, state, result)
    if not allow_dirty and _git_has_unpushed_or_dirty_changes():
        result = SetupPhaseResult(
            phase="deploy",
            status=PHASE_NEEDS_ACTION,
            message="Deployment blocked by local Git changes.",
            next_actions=["Commit and push setup, workflow, deploy, vault, and rules changes before triggering GitHub Actions."],
            data={"dirty_or_unpushed": True},
        )
        _record_phase(state, result)
        save_bot_setup_state(vault_root, state)
        return _phase_command_result(vault_root, state, result)

    gh = adapter or GitHubCli()
    auth = gh.auth_status()
    if not auth.ok:
        result = SetupPhaseResult(
            phase="deploy",
            status=PHASE_NEEDS_ACTION,
            message="GitHub CLI is not ready for deployment.",
            next_actions=["Run `gh auth login`, or refresh with workflow scope and retry deployment."],
            data={"auth": auth.redacted(Redactor())},
        )
        _record_phase(state, result)
        save_bot_setup_state(vault_root, state)
        return _phase_command_result(vault_root, state, result)

    inputs = {"vault_path": vault_path}
    if release_id:
        inputs["release_id"] = release_id
    dispatch = gh.workflow_run(repository, workflow_file, inputs)
    if not dispatch.ok:
        _raise_gh_error("bot_setup_deploy_dispatch_failed", "Could not dispatch the bot deployment workflow.", dispatch, Redactor())
    watch_result = gh.run_watch(repository) if watch else AdapterResult(ok=True)
    status = PHASE_DONE if watch_result.ok else PHASE_FAILED
    result = SetupPhaseResult(
        phase="deploy",
        status=status,
        message="Deployment workflow dispatched" if status == PHASE_DONE else "Deployment workflow failed or was cancelled",
        next_actions=[] if status == PHASE_DONE else ["Open the GitHub Actions run, fix the failing phase, and rerun deploy setup."],
        data={
            "repository": repository,
            "workflow_file": workflow_file,
            "inputs": inputs,
            "dispatch": dispatch.redacted(Redactor()),
            "watch": watch_result.redacted(Redactor()),
        },
    )
    _record_phase(state, result)
    save_bot_setup_state(vault_root, state)
    return _phase_command_result(vault_root, state, result)


def configure_answer_setup(
    vault_root: Path,
    *,
    mode: str,
    model: dict[str, Any] | None = None,
) -> CommandResult:
    state = load_or_initialize_setup_state(vault_root, save=True)
    normalized_mode = str(mode).strip() or "template"
    if normalized_mode not in {"template", "llama-local"}:
        raise AppError(
            code="bot_setup_answer_mode_invalid",
            message="Unsupported bot answer mode.",
            hint="Use template or llama-local.",
            details={"mode": mode},
            exit_code=2,
        )
    answers: dict[str, Any] = {"mode": normalized_mode}
    if normalized_mode == "llama-local":
        answers["model"] = {str(key): str(value) for key, value in (model or {}).items() if value not in (None, "")}
    state["answers"] = answers
    _sync_runtime_config_from_setup(vault_root, state)
    save_bot_setup_state(vault_root, state)
    data = _setup_status_payload(vault_root, state)
    data["answer_setup"] = answers
    return CommandResult(message="Bot answer mode configured", data=data)


def setup_doctor(vault_root: Path) -> CommandResult:
    state = load_or_initialize_setup_state(vault_root, save=True)
    issues: list[Issue] = []
    data = _setup_status_payload(vault_root, state)
    runtime = load_bot_config(vault_root)
    discord = dict(state.get("discord", {}) or {})
    if discord.get("guild_id") and runtime.guild_id and str(discord["guild_id"]) != str(runtime.guild_id):
        issues.append(
            Issue(
                code="bot_setup_runtime_config_drift",
                severity="warning",
                message="Setup state guild ID differs from runtime bot config.",
                path=str(bot_config_path(vault_root).relative_to(vault_root)),
                hint="Rerun `backet bot setup discord` to regenerate runtime config.",
                safe_to_fix=False,
            )
        )
    workflow = Path(".github/workflows") / str(dict(state.get("github", {}) or {}).get("workflow_file") or DEFAULT_WORKFLOW_FILE)
    if not workflow.exists():
        issues.append(
            Issue(
                code="bot_setup_workflow_missing",
                severity="warning",
                message="Private bot deploy workflow is not present in this repository checkout.",
                path=workflow.as_posix(),
                hint="Restore `.github/workflows/deploy-backet-bot.yml` before guided deployment.",
                safe_to_fix=False,
            )
        )
    deploy_assets = [Path("deploy/bot/docker-compose.yml"), Path("deploy/bot/activate-release.sh"), Path("deploy/bot/smoke-test.sh")]
    missing_assets = [path.as_posix() for path in deploy_assets if not path.exists()]
    for missing in missing_assets:
        issues.append(
            Issue(
                code="bot_setup_deploy_asset_missing",
                severity="warning",
                message="Bot deploy asset is missing.",
                path=missing,
                hint="Restore deploy/bot assets before guided deployment.",
                safe_to_fix=False,
            )
        )
    data["doctor"] = {
        "ok": not any(issue.severity == "error" for issue in issues),
        "workflow_file": workflow.as_posix(),
        "missing_deploy_assets": missing_assets,
        "runtime_config_path": str(bot_config_path(vault_root).relative_to(vault_root)),
        "setup_state_path": str(bot_setup_path(vault_root).relative_to(vault_root)),
    }
    return CommandResult(message="Backet bot setup doctor complete", issues=issues, data=data)


def capture_secret_from_stdin_or_prompt(
    name: str,
    use_stdin: bool = False,
    prompt: bool = False,
    input_stream: Any = None,
) -> str | None:
    if use_stdin:
        stream = input_stream or sys.stdin
        value = stream.read()
        return value.rstrip("\n")
    if prompt:
        return getpass.getpass(f"{name}: ")
    return None


def generate_discord_install_url(app_id: str, guild_id: str | None = None, permissions: str = DISCORD_INSTALL_PERMISSIONS) -> str:
    query: dict[str, str] = {
        "client_id": str(app_id),
        "scope": "applications.commands bot",
        "permissions": str(permissions),
    }
    if guild_id:
        query["guild_id"] = str(guild_id)
        query["disable_guild_select"] = "true"
    return f"https://discord.com/oauth2/authorize?{urlencode(query)}"


def normalize_discord_bot_token(value: str) -> str:
    token = value.strip()
    if token.lower().startswith("bot "):
        token = token[4:].strip()
    if token.lower().startswith("bearer ") or token.startswith("mfa."):
        raise AppError(
            code="bot_setup_discord_user_token_refused",
            message="Backet cannot use Discord user-account credentials.",
            hint="Provide the bot token from the application's Bot page, not a user token, password, cookie, or OAuth bearer token.",
            exit_code=2,
        )
    if not token:
        raise AppError(
            code="bot_setup_discord_token_missing",
            message="Discord bot token is missing.",
            hint="Provide the token through hidden input or --token-stdin.",
            exit_code=2,
        )
    return token


def load_or_initialize_setup_state(vault_root: Path, save: bool = False) -> dict[str, Any]:
    ensure_bootstrapped_vault(vault_root)
    path = bot_setup_path(vault_root)
    if path.exists():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise AppError(
                code="bot_setup_state_invalid",
                message="Bot setup state must be a YAML mapping.",
                hint=f"Fix {path.relative_to(vault_root)}.",
                exit_code=2,
            )
        _validate_setup_state(payload, path)
        return _merge_default_setup_state(payload)

    state = _default_setup_state()
    runtime_config = load_bot_config(vault_root)
    if runtime_config.exists:
        state = _import_runtime_config(state, runtime_config.to_dict())
    if save:
        save_bot_setup_state(vault_root, state)
    return state


def save_bot_setup_state(vault_root: Path, state: dict[str, Any]) -> Path:
    ensure_bootstrapped_vault(vault_root)
    _validate_setup_state(state, bot_setup_path(vault_root))
    state_dir(vault_root).mkdir(parents=True, exist_ok=True)
    path = bot_setup_path(vault_root)
    path.write_text(yaml.safe_dump(_redacted_setup_state_for_disk(state), sort_keys=False), encoding="utf-8")
    return path


def _phase_command_result(vault_root: Path, state: dict[str, Any], result: SetupPhaseResult) -> CommandResult:
    status = _setup_status_payload(vault_root, state)
    status["last_phase_result"] = result.to_dict()
    return CommandResult(
        message=result.message,
        issues=[Issue(code=f"bot_setup_{result.phase}_{result.status}", severity="warning", message=warning) for warning in result.warnings],
        data=status,
    )


def _prerequisites_phase(vault_root: Path, state: dict[str, Any], repo_root: Path | None = None) -> SetupPhaseResult:
    ensure_bootstrapped_vault(vault_root)
    warnings: list[str] = []
    next_actions: list[str] = []
    resolved_repo_root = repo_root or _git_root_for(vault_root) or vault_root.resolve()
    missing_files = [relative for relative in DEPLOY_REPOSITORY_FILES if not (resolved_repo_root / relative).exists()]
    if ".github/workflows/deploy-backet-bot.yml" in missing_files:
        warnings.append("The private bot deployment workflow is not present in this repository checkout.")
    if missing_files:
        next_actions.append("Run `backet bot setup files <vault>` from the private vault repository to install deploy files.")
    if shutil.which("gh") is None:
        next_actions.append("Install GitHub CLI so Backet can configure repository secrets and dispatch deployment.")
    if shutil.which("ssh") is None:
        next_actions.append("Install OpenSSH client so Backet can validate the Oracle VM.")
    status = PHASE_DONE if not next_actions else PHASE_NEEDS_ACTION
    result = SetupPhaseResult(
        phase="prerequisites",
        status=status,
        message="Local setup prerequisites checked",
        next_actions=next_actions,
        warnings=warnings,
        data={
            "vault": str(vault_root),
            "repo_root": str(resolved_repo_root),
            "gh_available": shutil.which("gh") is not None,
            "ssh_available": shutil.which("ssh") is not None,
            "workflow_present": (resolved_repo_root / ".github/workflows/deploy-backet-bot.yml").exists(),
            "missing_deploy_files": missing_files,
        },
    )
    _record_phase(state, result)
    return result


def _resolve_deploy_repo_root(vault_root: Path, repo_root: Path | None) -> Path:
    if repo_root is not None:
        resolved = repo_root.expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    git_root = _git_root_for(vault_root) or _git_root_for(Path.cwd())
    if git_root is not None:
        return git_root
    return vault_root.resolve()


def _git_root_for(path: Path) -> Path | None:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    output = completed.stdout.strip()
    return Path(output).resolve() if output else None


def _render_deploy_repository_file(relative: str) -> bytes:
    raw = _read_packaged_deploy_file(relative)
    if relative in {".github/workflows/deploy-backet-bot.yml", "deploy/bot/Dockerfile"}:
        text = raw.decode("utf-8")
        metadata = load_distribution_metadata()
        install_spec = f"backet[bot] @ {metadata.release_artifact_url(__version__)}"
        text = re.sub(
            r"backet\[bot\] @ https://github\.com/jsvitkin/backet/releases/download/v[^/]+/backet-[^}\" ]+\.whl",
            install_spec,
            text,
        )
        return text.encode("utf-8")
    return raw


def _read_packaged_deploy_file(relative: str) -> bytes:
    try:
        resource = importlib.resources.files("backet.resources").joinpath("bot_deploy", *Path(relative).parts)
        return resource.read_bytes()
    except (FileNotFoundError, ModuleNotFoundError):
        source_root = Path(__file__).resolve().parents[2]
        return (source_root / relative).read_bytes()


def _record_phase(state: dict[str, Any], result: SetupPhaseResult) -> None:
    setup = dict(state.get("setup", {}) or {})
    phases = dict(setup.get("phases", {}) or {})
    phases[result.phase] = {
        "status": result.status,
        "updated_at": _timestamp_now(),
        "next_actions": result.next_actions,
        "warnings": result.warnings,
    }
    setup["phases"] = phases
    setup["completed_phases"] = sorted(phase for phase, payload in phases.items() if payload.get("status") == PHASE_DONE)
    setup["last_checked_at"] = _timestamp_now()
    state["setup"] = setup


def _setup_status_payload(vault_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    phases = dict(dict(state.get("setup", {}) or {}).get("phases", {}) or {})
    phase_payload = {}
    for phase in SETUP_PHASES:
        phase_payload[phase] = {
            "status": dict(phases.get(phase, {})).get("status", PHASE_PENDING),
            "next_actions": dict(phases.get(phase, {})).get("next_actions", []),
            "warnings": dict(phases.get(phase, {})).get("warnings", []),
        }
    safe_state = Redactor().data(state)
    return {
        "vault": str(vault_root),
        "setup_state_path": str(bot_setup_path(vault_root)),
        "runtime_config_path": str(bot_config_path(vault_root)),
        "schema_version": safe_state.get("schema_version"),
        "phases": phase_payload,
        "completed_phases": dict(safe_state.get("setup", {}) or {}).get("completed_phases", []),
        "next_phase": _next_pending_phase(state),
        "discord": safe_state.get("discord", {}),
        "github": _github_safe_status(safe_state),
        "oracle": safe_state.get("oracle", {}),
        "answers": safe_state.get("answers", {}),
    }


def _github_safe_status(state: dict[str, Any]) -> dict[str, Any]:
    github = dict(state.get("github", {}) or {})
    secret_names = {str(name) for name in github.get("secret_names", [])}
    variable_names = {str(name) for name in github.get("variable_names", [])}
    return {
        "repository": github.get("repository"),
        "workflow_file": github.get("workflow_file"),
        "secrets": {
            name: ("configured" if name in secret_names else "missing")
            for name in sorted(set(DEFAULT_SECRET_NAMES) | set(OPTIONAL_SECRET_NAMES) | secret_names)
        },
        "variables": {
            name: ("configured" if name in variable_names else "missing")
            for name in sorted(set(DEFAULT_VARIABLE_NAMES) | variable_names)
        },
    }


def _issues_from_status(status: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    for phase, payload in status.get("phases", {}).items():
        for warning in payload.get("warnings", []):
            issues.append(Issue(code=f"bot_setup_{phase}_warning", severity="warning", message=str(warning)))
    return issues


def _next_pending_phase(state: dict[str, Any]) -> str | None:
    phases = dict(dict(state.get("setup", {}) or {}).get("phases", {}) or {})
    for phase in SETUP_PHASES:
        if dict(phases.get(phase, {})).get("status") != PHASE_DONE:
            return phase
    return None


def _sync_runtime_config_from_setup(vault_root: Path, state: dict[str, Any]) -> None:
    discord = dict(state.get("discord", {}) or {})
    if not discord.get("guild_id"):
        return
    path = bot_config_path(vault_root)
    existing_payload: dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            existing_payload = raw
    selected_roles = dict(discord.get("selected_role_ids", {}) or {})
    selected_channels = dict(discord.get("selected_channel_ids", {}) or {})
    commands = dict(existing_payload.get("commands", {}) or {})
    canon_policy = dict(commands.get("canon", {}) or {})
    canon_policy.setdefault("min_tier", "player")
    canon_policy.setdefault("topics", ["canon"])
    canon_policy.setdefault("public_allowed", False)
    if selected_channels.get("canon"):
        canon_policy["channel_ids"] = selected_channels["canon"]
    commands["canon"] = canon_policy

    payload = dict(existing_payload)
    payload["schema_version"] = 1
    payload["guild_id"] = str(discord["guild_id"])
    payload["roles"] = {
        **dict(existing_payload.get("roles", {}) or {}),
        **({role: ids for role, ids in selected_roles.items() if ids}),
    }
    payload["commands"] = commands
    answers = dict(state.get("answers", {}) or {})
    payload["answer_mode"] = str(answers.get("mode") or payload.get("answer_mode") or "template")
    if answers.get("model"):
        payload["model"] = answers["model"]
    _reject_runtime_secret_values(payload)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _github_variables_from_state(state: dict[str, Any]) -> dict[str, str]:
    variables: dict[str, str] = {}
    discord = dict(state.get("discord", {}) or {})
    oracle = dict(state.get("oracle", {}) or {})
    answers = dict(state.get("answers", {}) or {})
    if discord.get("guild_id"):
        variables["DISCORD_GUILD_ID"] = str(discord["guild_id"])
    if oracle.get("host"):
        variables["ORACLE_VM_HOST"] = str(oracle["host"])
    if oracle.get("user"):
        variables["ORACLE_VM_USER"] = str(oracle["user"])
    if answers.get("mode") == "llama-local":
        variables["BOT_COMPOSE_PROFILES"] = "llama"
    else:
        variables["BOT_COMPOSE_PROFILES"] = ""
    model = dict(answers.get("model", {}) or {})
    for source_key, variable_name in [
        ("path", "LLAMA_MODEL_RELATIVE_PATH"),
        ("sha256", "LLAMA_MODEL_SHA256"),
        ("url", "LLAMA_MODEL_URL"),
    ]:
        if model.get(source_key):
            variables[variable_name] = str(model[source_key])
    return variables


def _default_setup_state() -> dict[str, Any]:
    return {
        "schema_version": BOT_SETUP_SCHEMA_VERSION,
        "setup": {"phases": {}, "completed_phases": [], "last_checked_at": None},
        "discord": {},
        "github": {"workflow_file": DEFAULT_WORKFLOW_FILE, "secret_names": [], "variable_names": []},
        "oracle": {"deploy_path": DEFAULT_DEPLOY_PATH},
        "answers": {"mode": "template"},
    }


def _merge_default_setup_state(payload: dict[str, Any]) -> dict[str, Any]:
    state = _default_setup_state()
    for key, value in payload.items():
        if isinstance(value, dict) and isinstance(state.get(key), dict):
            state[key] = {**state[key], **value}
        else:
            state[key] = value
    return state


def _import_runtime_config(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    discord = dict(state.get("discord", {}) or {})
    if config.get("guild_id"):
        discord["guild_id"] = str(config["guild_id"])
    roles = dict(config.get("roles", {}) or {})
    if roles:
        discord["selected_role_ids"] = {str(key): [str(item) for item in value] for key, value in roles.items()}
    commands = dict(config.get("commands", {}) or {})
    canon = commands.get("canon")
    if isinstance(canon, dict) and canon.get("channel_ids"):
        discord["selected_channel_ids"] = {"canon": [str(item) for item in canon.get("channel_ids", [])]}
    state["discord"] = discord
    state["answers"] = {"mode": str(config.get("answer_mode") or "template")}
    if config.get("model"):
        state["answers"]["model"] = config["model"]
    _record_phase(
        state,
        SetupPhaseResult(
            phase="discord",
            status=PHASE_NEEDS_ACTION if discord.get("guild_id") else PHASE_PENDING,
            message="Imported existing bot runtime config",
            next_actions=["Validate Discord application and bot install with `backet bot setup discord`."],
        ),
    )
    return state


def _validate_setup_state(payload: dict[str, Any], path: Path) -> None:
    schema_version = int(payload.get("schema_version", 1))
    if schema_version != BOT_SETUP_SCHEMA_VERSION:
        raise AppError(
            code="bot_setup_state_schema_unsupported",
            message="Unsupported bot setup state schema version.",
            hint=f"Use schema_version: {BOT_SETUP_SCHEMA_VERSION}.",
            details={"path": str(path), "schema_version": schema_version},
            exit_code=2,
        )
    _reject_setup_secret_values(payload, path)


def _reject_setup_secret_values(value: Any, path: Path, key_path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if _is_secret_value_key(key_text):
                if item not in (None, "", [], {}):
                    raise AppError(
                        code="bot_setup_secret_field",
                        message="Bot setup state must not contain secret values.",
                        hint="Store secrets in GitHub Actions secrets through setup, not in `.backet/state/bot-setup.yaml`.",
                        details={"path": str(path), "field": ".".join((*key_path, key_text))},
                        exit_code=2,
                    )
            _reject_setup_secret_values(item, path, (*key_path, key_text))
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_setup_secret_values(item, path, (*key_path, str(index)))
        return
    if isinstance(value, str) and _looks_like_secret_value(value):
        raise AppError(
            code="bot_setup_secret_value",
            message="Bot setup state appears to contain a secret value.",
            hint="Remove tokens or private keys from `.backet/state/bot-setup.yaml`.",
            details={"path": str(path), "field": ".".join(key_path)},
            exit_code=2,
        )


def _reject_runtime_secret_values(payload: dict[str, Any]) -> None:
    def walk(value: Any, key_path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                key_text = str(key)
                if _is_secret_value_key(key_text) and item not in (None, "", [], {}):
                    raise AppError(
                        code="bot_setup_runtime_secret_field",
                        message="Bot runtime config must not contain secret values.",
                        hint="Store tokens and keys in GitHub Actions secrets, not bot-config.yaml.",
                        details={"field": ".".join((*key_path, key_text))},
                        exit_code=2,
                    )
                walk(item, (*key_path, key_text))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, (*key_path, str(index)))
        elif isinstance(value, str) and _looks_like_secret_value(value):
            raise AppError(
                code="bot_setup_runtime_secret_value",
                message="Bot runtime config appears to contain a secret value.",
                hint="Remove tokens or private keys from bot-config.yaml.",
                details={"field": ".".join(key_path)},
                exit_code=2,
            )

    walk(payload)


def _redacted_setup_state_for_disk(state: dict[str, Any]) -> dict[str, Any]:
    return Redactor().data(state)


def _select_discord_object(items: list[dict[str, Any]], selected_id: str | None) -> dict[str, Any] | None:
    if selected_id:
        for item in items:
            if str(item.get("id")) == str(selected_id):
                return item
        return None
    if len(items) == 1:
        return items[0]
    return None


def _safe_discord_object(item: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: str(item[key]) for key in keys if key in item and item[key] is not None}


def _discord_role_permission_warnings(selected_roles: dict[str, list[str]], roles: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    roles_by_id = {str(role.get("id")): role for role in roles}
    for role_id in selected_roles.get("player", []):
        role = roles_by_id.get(str(role_id))
        if not role:
            continue
        permissions = _parse_discord_permissions(role.get("permissions"))
        if permissions is None:
            continue
        if not permissions & DISCORD_PERMISSION_USE_APPLICATION_COMMANDS:
            name = str(role.get("name") or role_id)
            warnings.append(
                f"Discord role `{name}` is mapped as a player role but lacks `Use Application Commands`; "
                "players with only that role may not see or run slash commands until that Discord permission is enabled."
            )
    return warnings


def _parse_discord_permissions(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _coerce_discord_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


def _raise_gh_error(code: str, message: str, result: AdapterResult, redactor: Redactor) -> None:
    hint = "Check `gh auth status`; refresh with `gh auth refresh -h github.com -s repo -s workflow` if workflow scope is missing."
    stderr = redactor.text(result.stderr)
    stdout = redactor.text(result.stdout)
    if "workflow" in f"{stderr} {stdout}".lower() and "scope" in f"{stderr} {stdout}".lower():
        hint = "Run `gh auth refresh -h github.com -s repo -s workflow`, then retry."
    raise AppError(
        code=code,
        message=message,
        hint=hint,
        details=result.redacted(redactor),
        exit_code=2,
    )


def _oracle_bootstrap_command(deploy_path: str) -> str:
    quoted = _shell_quote(deploy_path)
    return (
        "set -e; "
        f"sudo mkdir -p {quoted}/deploy {quoted}/uploads {quoted}/releases {quoted}/data {quoted}/models; "
        f"sudo chown -R \"$USER\":\"$USER\" {quoted}; "
        "command -v docker >/dev/null 2>&1 || echo 'docker-missing'; "
        "docker compose version >/dev/null 2>&1 || docker-compose version >/dev/null 2>&1 || echo 'compose-missing'"
    )


def _oracle_doctor_command(deploy_path: str) -> str:
    quoted = _shell_quote(deploy_path)
    return (
        "set -e; "
        "command -v docker >/dev/null; "
        "docker compose version >/dev/null 2>&1 || docker-compose version >/dev/null 2>&1; "
        f"test -d {quoted}/deploy; "
        f"test -d {quoted}/uploads; "
        f"test -d {quoted}/releases; "
        f"test -d {quoted}/data; "
        f"test -d {quoted}/models"
    )


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _git_has_unpushed_or_dirty_changes() -> bool:
    if not (Path(".git").exists() or _inside_git_worktree()):
        return False
    status = subprocess.run(["git", "status", "--porcelain"], text=True, capture_output=True, check=False)
    if status.returncode != 0:
        return False
    if status.stdout.strip():
        return True
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True, capture_output=True, check=False)
    if branch.returncode != 0:
        return False
    upstream = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if upstream.returncode != 0:
        return True
    ahead = subprocess.run(["git", "rev-list", "--count", "@{u}..HEAD"], text=True, capture_output=True, check=False)
    return ahead.returncode == 0 and int((ahead.stdout or "0").strip() or "0") > 0


def _inside_git_worktree() -> bool:
    result = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], text=True, capture_output=True, check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def _timestamp_now() -> str:
    return datetime.now(UTC).isoformat()


def _is_secret_value_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized in {"secret_names", "required_secrets", "secrets"}:
        return False
    return normalized in SECRET_VALUE_KEYS or normalized.endswith("_token") or normalized.endswith("_private_key")


def _looks_like_secret_value(value: str) -> bool:
    return "-----BEGIN OPENSSH PRIVATE KEY-----" in value or "-----BEGIN RSA PRIVATE KEY-----" in value or value.startswith("mfa.")
