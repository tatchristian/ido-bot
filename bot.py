"""
Main entry point for the IDO Tournament Discord Bot.
Handles client lifecycle, cog loading, slash command syncing, and graceful shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

import discord
from discord.ext import commands

from config import config
from services.tournament_service import TournamentService
from utils.storage import StorageManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ido_bot")


class IDOTournamentBot(commands.Bot):
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

    async def setup_hook(self) -> None:
        """Invoked before the bot establishes its gateway connection."""
        logger.info("Initializing bot services and loading extensions...")
        await self.load_extension("cogs.tournaments")

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
        logger.info("IDO Tournament Bot is ready and operational.")


async def main():
    bot = IDOTournamentBot()

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
