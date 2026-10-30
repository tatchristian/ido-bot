"""
Main entry point for the UDA (United Dueling Amity) Discord Bot.
Handles client lifecycle, cog loading, slash command syncing, and graceful shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

import discord
from discord.ext import commands

from aiohttp import web

from config import config
from services.api_server import create_api_app
from services.clan_showcase_service import ClanShowcaseService
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
