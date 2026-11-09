"""
Main entry point for the UDA (United Dueling Amity) Discord Bot.
Handles client lifecycle, cog loading, slash command syncing, and graceful shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import signal
import sys

import discord
from discord.ext import commands

from aiohttp import web

from config import config
from services.api_server import create_api_app
from services.clan_showcase_service import ClanShowcaseService
from services.past_results_service import PastResultsService
from services.state_snapshot_service import StateSnapshotService
from services.tournament_service import TournamentService
from utils.storage import StorageManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("uda_bot")


async def start_api_server(bot: UDATournamentBot) -> web.AppRunner | None:
    """Starts the public REST API and health server for Railway/Koyeb and unitedduelingamity.org."""
    raw_port = os.getenv("PORT", "8000")
    if not raw_port or not raw_port.isdigit():
        return None

    port = int(raw_port)
    app = create_api_app(bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Public Web API and health server listening on 0.0.0.0:%d", port)
    return runner


class UDATournamentBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True  # Required for member resolution and role checks
        super().__init__(
            command_prefix="!",  # Primary interface is Slash Commands
            intents=intents,
            help_command=None,
        )

        # Initialize persistence and service layers
        self.storage = StorageManager(
            file_path=config.tournament_file,
            backup_dir=config.backup_dir,
            max_backups=config.max_backups,
        )
        self.tournament_service = TournamentService(self.storage)
        self.clan_showcase_service = ClanShowcaseService(data_dir=config.data_dir)
        self.past_results_service = PastResultsService(data_dir=config.data_dir)
        self.state_snapshot_service = StateSnapshotService()

    async def setup_hook(self) -> None:
        """Invoked before the bot establishes its gateway connection."""
        logger.info("Initializing bot services and loading extensions...")
        await start_api_server(self)
        await self.load_extension("cogs.tournaments")
        await self.load_extension("cogs.clan_showcase")

        # Slash command tree synchronization
        if config.guild_id:
            guild_obj = discord.Object(id=config.guild_id)
            self.tree.copy_global_to(guild=guild_obj)
            synced = await self.tree.sync(guild=guild_obj)
            logger.info("Synced %d slash commands to Guild ID: %d", len(synced), config.guild_id)
        else:
            synced = await self.tree.sync()
            logger.info("Synced %d global slash commands.", len(synced))

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (ID: %d)", self.user, self.user.id)
        activity = discord.Activity(
            type=discord.ActivityType.competing,
            name=f"{config.organization_name} Tournaments (/tournament-status)",
        )
        await self.change_presence(activity=activity)

        # Auto-restore channel and role state from saved_state.json preset if channels are missing
        state_file = Path("saved_state.json")
        target_guilds = list(self.guilds)
        if config.guild_id and not any(g.id == config.guild_id for g in target_guilds):
            configured_g = self.get_guild(config.guild_id)
            if configured_g:
                target_guilds.append(configured_g)

        for guild in target_guilds:
            try:
                t_state = self.tournament_service.get_state(guild.id)
                showcase_ch, _ = self.clan_showcase_service.get_guild_channels(guild.id)
                if t_state.registration_channel_id is None or showcase_ch is None:
                    if state_file.exists():
                        self.state_snapshot_service.restore_snapshot(
                            guild.id, self.tournament_service, self.clan_showcase_service, file_path=state_file
                        )
                        logger.info("Auto-restored channel state snapshot from saved_state.json for guild %d", guild.id)
                    else:
                        # Fallback: Regex auto-discovery across existing server channels
                        self.state_snapshot_service.auto_discover_channels(
                            guild, self.tournament_service, self.clan_showcase_service
                        )
            except Exception as exc:
                logger.warning("Failed channel state auto-restore for guild %d: %s", guild.id, exc)

        # Auto-restore tournament roster from saved_roster.json preset if active roster is empty
        preset_file = Path("saved_roster.json")
        if preset_file.exists():
            for guild in target_guilds:
                try:
                    state = self.tournament_service.get_state(guild.id)
                    if len(state.participants) == 0:
                        def _resolver(ign: str, mention_str: str) -> tuple[int, str] | None:
                            clean_name = mention_str.lstrip("@").strip().lower()
                            member = discord.utils.find(
                                lambda m: (
                                    m.name.lower() == clean_name
                                    or m.display_name.lower() == clean_name
                                    or m.name.lower() == ign.lower()
                                    or m.display_name.lower() == ign.lower()
                                ),
                                guild.members,
                            )
                            if member:
                                return member.id, member.mention
                            return None

                        p_cnt, s_cnt = self.tournament_service.import_roster_preset(
                            guild.id, preset_file, member_resolver=_resolver
                        )
                        logger.info(
                            "Auto-restored tournament roster for %s (%d): %d main, %d subs",
                            guild.name,
                            guild.id,
                            p_cnt,
                            s_cnt,
                        )
                except Exception as exc:
                    logger.warning("Failed to auto-restore preset roster for guild %d: %s", guild.id, exc)

        logger.info("UDA Tournament Bot is ready and operational.")


# Backwards compatibility alias
IDOTournamentBot = UDATournamentBot


async def main():
    bot = UDATournamentBot()

    # Graceful shutdown handler
    def handle_signal():
        logger.info("Shutdown signal received. Closing bot connection...")
        asyncio.create_task(bot.close())

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except (NotImplementedError, AttributeError):
            pass

    async with bot:
        await bot.start(config.token)


if __name__ == "__main__":
    if not config.token:
        logger.critical(
            "DISCORD_TOKEN is missing! Please configure it in your environment or .env file."
        )
        sys.exit(1)

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot process stopped.")
