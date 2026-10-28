"""
Standalone Automated Server Layout Builder for IDO Tournament Server.

Usage:
    python build_ido_server.py
    python build_ido_server.py --guild-id 123456789012345678
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure local packages can be imported
sys.path.insert(0, str(Path(__file__).parent))

import discord
from config import config
from services.server_builder import build_server_layout

load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Automated layout builder for the official IDO Tournament Discord Server."
    )
    parser.add_argument(
        "--guild-id",
        type=int,
        default=config.target_guild_id or config.guild_id,
        help="Target Discord Server/Guild ID to build layout in.",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=config.token,
        help="Bot authentication token (defaults to DISCORD_TOKEN in .env).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.2,
        help="Delay in seconds between Discord API creation calls (default: 1.2s).",
    )
    return parser.parse_args()


class LayoutBuilderClient(discord.Client):
    def __init__(self, target_guild_id: int | None, delay: float):
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(intents=intents)
        self.target_guild_id = target_guild_id
        self.delay = delay

    async def on_ready(self):
        print("=" * 60)
        print(f"🤖 Connected as {self.user} (ID: {self.user.id})")
        print("=" * 60)

        guild = None
        if self.target_guild_id:
            guild = self.get_guild(self.target_guild_id)
            if not guild:
                # Try fetching via API if not in cache
                try:
                    guild = await self.fetch_guild(self.target_guild_id)
                except Exception:
                    guild = None

        if not guild:
            # If not provided or not found, list available guilds
            available_guilds = list(self.guilds)
            if not available_guilds:
                print("❌ The bot is not currently in any servers!")
                print("👉 Please invite the bot to your new server first using an OAuth2 invite link.")
                await self.close()
                return

            if len(available_guilds) == 1:
                guild = available_guilds[0]
                print(f"ℹ️ Auto-selected the only server the bot is in: '{guild.name}' (ID: {guild.id})")
            else:
                print("\nAvailable Servers:")
                for idx, g in enumerate(available_guilds, 1):
                    print(f"  [{idx}] {g.name} (ID: {g.id})")

                print(
                    "\n⚠️ Please specify the target guild by passing --guild-id <ID> or setting TARGET_GUILD_ID in .env."
                )
                await self.close()
                return

        print(f"\n🚀 Target Server: '{guild.name}' (ID: {guild.id})")
        print(f"⏱️ Rate Limit Throttling: {self.delay}s per Discord creation call")
        print("-" * 60)

        # Run layout builder
        results = await build_server_layout(
            guild=guild,
            log_callback=lambda msg: print(msg),
            delay=self.delay,
        )

        print("-" * 60)
        print("📊 Execution Summary:")
        print(f"  • Categories Created:  {results['categories_created']}")
        print(f"  • Categories Existing: {results['categories_existing']}")
        print(f"  • Channels Created:    {results['channels_created']}")
        print(f"  • Channels Existing:   {results['channels_existing']}")
        if results["channels_skipped_filter"] > 0:
            print(f"  • Filtered (3v3):      {results['channels_skipped_filter']}")
        if results["errors"]:
            print(f"  • Errors Encountered:  {len(results['errors'])}")
            for err in results["errors"]:
                print(f"    - {err}")
        else:
            print("  • Errors:              0 (All steps succeeded smoothly!)")
        print("=" * 60)

        await self.close()


async def main():
    args = parse_args()

    token = args.token or os.getenv("DISCORD_TOKEN")
    if not token or token == "your_bot_token_here":
        print("❌ Error: No Discord bot token found!")
        print("👉 Please set DISCORD_TOKEN in your .env file or pass --token <BOT_TOKEN>.")
        sys.exit(1)

    client = LayoutBuilderClient(target_guild_id=args.guild_id, delay=args.delay)

    try:
        await client.start(token)
    except discord.LoginFailure:
        print("❌ Login Failed: The bot token provided is invalid.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Execution error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Execution interrupted by user.")
        sys.exit(0)
