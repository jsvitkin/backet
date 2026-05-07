from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backet.bot_access import ACCESS_TIER_STORYTELLER
from backet.bot_runtime import (
    BotAnswer,
    BotBundle,
    answer_bot_query,
    resolve_access_tier,
    sanitize_discord_mentions,
    split_discord_response,
)
from backet.errors import AppError
from backet.models import CommandResult

LOGGER = logging.getLogger("backet.bot.discord")
DISCORD_ERROR_MESSAGE = "Backet hit an internal bot error before it could finish this command. The operator logs have the details."


@dataclass(slots=True)
class DiscordRequestContext:
    guild_id: str | None
    user_id: str | None
    role_ids: list[str]
    channel_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "guild_id": self.guild_id,
            "user_id": self.user_id,
            "role_ids": self.role_ids,
            "channel_id": self.channel_id,
        }


def run_discord_bot_result(bundle_root: Path, token: str | None = None, guild_id: str | None = None) -> CommandResult:
    run_discord_bot(bundle_root=bundle_root, token=token, guild_id=guild_id)
    return CommandResult(message="Discord bot stopped", data={"bundle_root": str(bundle_root)})


def run_discord_bot(bundle_root: Path, token: str | None = None, guild_id: str | None = None) -> None:
    _configure_logging()
    discord = _require_discord()
    bundle = BotBundle.load(bundle_root)
    resolved_token = token or os.environ.get("DISCORD_TOKEN")
    if not resolved_token:
        raise AppError(
            code="bot_discord_token_missing",
            message="Discord bot token is missing.",
            hint="Set DISCORD_TOKEN in the runtime environment.",
            exit_code=2,
        )
    resolved_guild_id = guild_id or str(bundle.manifest.get("bot", {}).get("guild_id") or os.environ.get("DISCORD_GUILD_ID") or "")
    if not resolved_guild_id:
        raise AppError(
            code="bot_discord_guild_missing",
            message="Discord guild ID is missing.",
            hint="Set guild_id in bot-config.yaml or DISCORD_GUILD_ID in the runtime environment.",
            exit_code=2,
        )

    client = _BacketDiscordClient(discord_module=discord, bundle=bundle, guild_id=resolved_guild_id)
    try:
        client.run(resolved_token, log_handler=None)
    except KeyboardInterrupt:
        LOGGER.info("discord_bot_shutdown_requested")


def evaluate_discord_request(
    bundle: BotBundle,
    context: DiscordRequestContext,
    command: str,
    question: str,
    private_requested: bool | None = None,
    limit: int = 4,
) -> BotAnswer:
    configured_guild_id = str(bundle.manifest.get("bot", {}).get("guild_id") or "")
    if configured_guild_id and str(context.guild_id) != configured_guild_id:
        return _denial_answer(command, "This bot is not configured for this Discord server.")

    policy = _command_policy(bundle, command)
    channel_ids = {str(value) for value in policy.get("channel_ids", [])}
    if channel_ids and str(context.channel_id) not in channel_ids:
        return _denial_answer(command, "This bot command is not available in this channel.")

    private = private_requested
    if private is False and not bool(policy.get("public_allowed", False)):
        private = True

    started = time.monotonic()
    answer = answer_bot_query(
        bundle,
        command=command,
        question=question,
        user_id=context.user_id,
        role_ids=context.role_ids,
        private=private,
        limit=limit,
    )
    elapsed_ms = round((time.monotonic() - started) * 1000)
    generation = dict(answer.diagnostics.get("answer_generation", {}) or {})
    generation_diag = dict(generation.get("diagnostics", {}) or {})
    log_fields: dict[str, Any] = {
        "command": answer.command,
        "access_tier": answer.access_tier,
        "retrieval_attempted": answer.retrieval_attempted,
        "denied": answer.denied,
        "source_count": len(answer.sources),
        "source_refs": [_log_source_reference(source) for source in answer.sources[:5]],
        "answer_mode": generation.get("mode"),
        "fallback_used": generation.get("fallback_used"),
        "fallback_reason": generation_diag.get("fallback_reason"),
        "question_fingerprint": generation_diag.get("question_fingerprint") or _fingerprint_question(question),
        "question_length": len(question),
        "response_chars": len(answer.text),
        "response_parts": len(answer.parts),
        "elapsed_ms": elapsed_ms,
    }
    if os.environ.get("BACKET_BOT_LOG_QUESTION_TEXT") == "1":
        log_fields["question_preview"] = " ".join(question.strip().split())[:120]
    LOGGER.info(
        "discord_bot_command %s",
        _format_log_fields(log_fields),
        extra={
            "command": answer.command,
            "access_tier": answer.access_tier,
            "retrieval_attempted": answer.retrieval_attempted,
            "denied": answer.denied,
            "source_count": len(answer.sources),
        },
    )
    return answer


def build_discord_health(bundle: BotBundle, context: DiscordRequestContext) -> dict[str, Any]:
    access = resolve_access_tier(bundle.manifest.get("bot", {}), user_id=context.user_id, role_ids=context.role_ids)
    if access.tier != ACCESS_TIER_STORYTELLER:
        return {
            "ready": True,
            "bundle_schema_version": bundle.manifest.get("schema_version"),
            "answer_mode": bundle.manifest.get("bot", {}).get("answer_mode", "template"),
        }
    return {
        "ready": True,
        "bundle_schema_version": bundle.manifest.get("schema_version"),
        "guild_id": bundle.manifest.get("bot", {}).get("guild_id"),
        "indexes": bundle.manifest.get("indexes", {}),
        "rules": bundle.manifest.get("rules", {}),
        "answer_mode": bundle.manifest.get("bot", {}).get("answer_mode", "template"),
        "exported_at": bundle.manifest.get("exported_at"),
    }


class _BacketDiscordClient:
    def __init__(self, discord_module: Any, bundle: BotBundle, guild_id: str) -> None:
        intents = discord_module.Intents.default()
        intents.message_content = False
        intents.members = False
        intents.presences = False
        self.discord = discord_module
        self.bundle = bundle
        self.guild_id = str(guild_id)
        self.recent_answers: dict[str, BotAnswer] = {}
        self.client = discord_module.Client(intents=intents)
        self.tree = discord_module.app_commands.CommandTree(self.client)
        self._register_commands()
        self.client.setup_hook = self._setup_hook

    def run(self, token: str, log_handler: Any | None = None) -> None:
        if log_handler is None:
            self.client.run(token)
            return
        self.client.run(token, log_handler=log_handler)

    async def _setup_hook(self) -> None:
        guild = self.discord.Object(id=int(self.guild_id))
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        LOGGER.info("discord_bot_commands_synced", extra={"guild_id": self.guild_id, "command_count": len(synced)})

    def _register_commands(self) -> None:
        discord = self.discord
        rules = discord.app_commands.Group(name="rules", description="Ask rules questions.")
        canon = discord.app_commands.Group(name="canon", description="Ask player-safe canon questions.")
        storyteller = discord.app_commands.Group(name="st", description="Storyteller-only questions.")
        bot = discord.app_commands.Group(name="bot", description="Inspect Backet bot runtime state.")

        @rules.command(name="ask", description="Ask a rules question.")
        async def rules_ask(interaction: Any, question: str, private: bool = True) -> None:
            await self._handle_question(interaction, "rules.ask", question, private)

        @canon.command(name="ask", description="Ask a player-safe canon question.")
        async def canon_ask(interaction: Any, question: str, private: bool = True) -> None:
            await self._handle_question(interaction, "canon.ask", question, private)

        @storyteller.command(name="ask", description="Ask a Storyteller-only question.")
        async def st_ask(interaction: Any, question: str) -> None:
            await self._handle_question(interaction, "st.ask", question, True)

        @storyteller.command(name="npc", description="Ask about Storyteller-only NPC material.")
        async def st_npc(interaction: Any, question: str) -> None:
            await self._handle_question(interaction, "st.npc", question, True)

        @storyteller.command(name="plot", description="Ask about Storyteller-only plot material.")
        async def st_plot(interaction: Any, question: str) -> None:
            await self._handle_question(interaction, "st.plot", question, True)

        @bot.command(name="sources", description="Show sources from your most recent bot answer.")
        async def bot_sources(interaction: Any) -> None:
            try:
                await self._handle_sources(interaction)
            except Exception:
                LOGGER.exception("discord_bot_command_failed", extra={"command": "bot.sources"})
                await self._send_error(interaction)

        @bot.command(name="health", description="Show bot health.")
        async def bot_health(interaction: Any) -> None:
            try:
                await self._handle_health(interaction)
            except Exception:
                LOGGER.exception("discord_bot_command_failed", extra={"command": "bot.health"})
                await self._send_error(interaction)

        @bot.command(name="help", description="Show Backet bot commands.")
        async def bot_help(interaction: Any) -> None:
            try:
                await interaction.response.send_message(
                    _format_help(),
                    ephemeral=True,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except Exception:
                LOGGER.exception("discord_bot_command_failed", extra={"command": "bot.help"})
                await self._send_error(interaction)

        self.tree.add_command(rules)
        self.tree.add_command(canon)
        self.tree.add_command(storyteller)
        self.tree.add_command(bot)

    async def _handle_question(self, interaction: Any, command: str, question: str, private: bool | None) -> None:
        try:
            context = _context_from_interaction(interaction)
            preliminary_private = True if command.startswith("st.") else private
            await interaction.response.defer(
                ephemeral=preliminary_private if preliminary_private is not None else True,
                thinking=True,
            )
            answer = await asyncio.to_thread(
                evaluate_discord_request,
                self.bundle,
                context,
                command,
                question,
                preliminary_private,
            )
            if context.user_id:
                self.recent_answers[str(context.user_id)] = answer
            for part in answer.parts:
                await interaction.followup.send(
                    part,
                    ephemeral=answer.response_private,
                    allowed_mentions=self.discord.AllowedMentions.none(),
                )
        except Exception:
            LOGGER.exception("discord_bot_command_failed", extra={"command": command})
            await self._send_error(interaction)

    async def _handle_sources(self, interaction: Any) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        context = _context_from_interaction(interaction)
        answer = self.recent_answers.get(str(context.user_id))
        if answer is None:
            await interaction.followup.send(
                "No recent bot answer found for you.",
                ephemeral=True,
                allowed_mentions=self.discord.AllowedMentions.none(),
            )
            return
        lines = [_source_summary(source) for source in answer.sources] or ["No sources were used."]
        text = sanitize_discord_mentions("\n".join(lines))
        for part in split_discord_response(text):
            await interaction.followup.send(
                part,
                ephemeral=True,
                allowed_mentions=self.discord.AllowedMentions.none(),
            )

    async def _handle_health(self, interaction: Any) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        context = _context_from_interaction(interaction)
        health = build_discord_health(self.bundle, context)
        text = sanitize_discord_mentions(_format_health(health))
        for part in split_discord_response(text):
            await interaction.followup.send(
                part,
                ephemeral=True,
                allowed_mentions=self.discord.AllowedMentions.none(),
            )

    async def _send_error(self, interaction: Any) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    DISCORD_ERROR_MESSAGE,
                    ephemeral=True,
                    allowed_mentions=self.discord.AllowedMentions.none(),
                )
                return
            await interaction.response.send_message(
                DISCORD_ERROR_MESSAGE,
                ephemeral=True,
                allowed_mentions=self.discord.AllowedMentions.none(),
            )
        except Exception:
            LOGGER.exception("discord_bot_error_response_failed")


def _require_discord() -> Any:
    try:
        import discord
    except ImportError as exc:
        raise AppError(
            code="bot_discord_dependency_missing",
            message="Discord bot dependencies are not installed.",
            hint="Install Backet with the `bot` optional dependency group, for example `pip install '.[bot]'.`",
            exit_code=2,
        ) from exc
    return discord


def _configure_logging() -> None:
    level_name = os.environ.get("BACKET_LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _context_from_interaction(interaction: Any) -> DiscordRequestContext:
    user = getattr(interaction, "user", None)
    roles = getattr(user, "roles", []) or []
    role_ids = [str(getattr(role, "id")) for role in roles if getattr(role, "id", None) is not None]
    return DiscordRequestContext(
        guild_id=str(getattr(interaction, "guild_id", "")) if getattr(interaction, "guild_id", None) else None,
        user_id=str(getattr(user, "id", "")) if getattr(user, "id", None) else None,
        role_ids=role_ids,
        channel_id=str(getattr(interaction, "channel_id", "")) if getattr(interaction, "channel_id", None) else None,
    )


def _command_policy(bundle: BotBundle, command: str) -> dict[str, Any]:
    command_root = command.split(".", 1)[0]
    return dict(bundle.manifest.get("bot", {}).get("commands", {}).get(command_root, {}))


def _denial_answer(command: str, message: str) -> BotAnswer:
    text = sanitize_discord_mentions(message)
    return BotAnswer(
        command=command,
        access_tier="unknown",
        text=text,
        parts=split_discord_response(text),
        sources=[],
        response_private=True,
        denied=True,
        retrieval_attempted=False,
        diagnostics={"discord_denial": True},
    )


def _source_summary(source: dict[str, Any]) -> str:
    if source.get("source_type") == "vault":
        return f"[{source['citation']}] {source['title']} ({source['relative_path']})"
    return f"[{source['citation']}] {source['book_title']} p. {source['page_start']} ({source['section_label']})"


def _log_source_reference(source: dict[str, Any]) -> str:
    if source.get("source_type") == "vault":
        return f"{source.get('citation')}:vault"
    page = source.get("page_start")
    if source.get("page_end") and source.get("page_end") != source.get("page_start"):
        page = f"{source.get('page_start')}-{source.get('page_end')}"
    return f"{source.get('citation')}:rules@p{page}"


def _fingerprint_question(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def _format_log_fields(fields: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in fields.items():
        if value in (None, [], {}):
            continue
        parts.append(f"{key}={_format_log_value(value)}")
    return " ".join(parts)


def _format_log_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(_format_log_value(item) for item in value) + "]"
    text = str(value).replace("\n", " ")
    if any(character.isspace() for character in text) or text == "":
        return repr(text)
    return text


def _format_health(health: dict[str, Any]) -> str:
    lines = [
        f"ready: {_format_bool(health.get('ready'))}",
        f"bundle schema: {health.get('bundle_schema_version', 'unknown')}",
        f"answer mode: {health.get('answer_mode', 'template')}",
    ]
    if health.get("guild_id"):
        lines.append(f"guild id: {health['guild_id']}")
    if health.get("exported_at"):
        lines.append(f"exported at: {health['exported_at']}")
    indexes = dict(health.get("indexes") or {})
    for scope in ("player", "storyteller"):
        meta = dict(indexes.get(scope) or {})
        if meta:
            lines.append(f"{scope} index: {meta.get('note_count', 0)} notes, {meta.get('chunk_count', 0)} chunks")
    rules = dict(health.get("rules") or {})
    if rules:
        included = "included" if rules.get("included") else "not included"
        size = _format_bytes(int(rules.get("size_bytes") or 0)) if rules.get("size_bytes") else "unknown size"
        path = rules.get("path") or "unknown path"
        lines.append(f"rules: {included}, {size}, {path}")
    return "\n".join(lines)


def _format_help() -> str:
    return "\n".join(
        [
            "Backet bot commands:",
            "/rules ask - ask player-available rules questions.",
            "/canon ask - ask player-safe canon questions.",
            "/st ask - ask Storyteller-only mixed questions.",
            "/st npc - ask Storyteller-only NPC questions.",
            "/st plot - ask Storyteller-only plot questions.",
            "/bot sources - show sources from your latest bot answer.",
            "/bot health - show runtime health.",
            "/bot help - show this help.",
        ]
    )


def _format_bool(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"
