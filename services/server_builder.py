"""
Automated Tournament Section Builder for Discord Servers.
Constructs tournament categories, text channels, voice arenas, and staff channels
with rate-limit throttling and automatic channel linking.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

import discord

logger = logging.getLogger("uda_bot.tournament_builder")

RATE_LIMIT_DELAY: float = 1.2

# Tournament section specification directly tailored to competitive dueling operations
TOURNAMENT_SECTION_SPEC: List[Dict[str, Any]] = [
    {
        "category": "🏆 TOURNAMENT HUB 🏆",
        "channels": [
            {
                "name": "📣・tournament-announcements",
                "type": "news",
                "read_only": True,
                "role_key": "announcements",
            },
            {
                "name": "📜・tournament-rules-and-info",
                "type": "text",
                "read_only": True,
            },
            {
                "name": "📝・tournament-registration",
                "type": "text",
                "read_only": True,
                "role_key": "registration",
            },
            {
                "name": "🛡️・substitutes-bench",
                "type": "text",
                "read_only": True,
                "role_key": "subs",
            },
            {
                "name": "✅・tournament-checkin",
                "type": "text",
                "read_only": True,
                "role_key": "checkin",
            },
            {
                "name": "📊・bracket-and-roster",
                "type": "text",
                "read_only": True,
            },
            {
                "name": "⚔️・match-results-and-disputes",
                "type": "text",
            },
        ],
    },
    {
        "category": "⚔️ MATCH ARENAS ⚔️",
        "channels": [
            {
                "name": "🎙️ Stream & Casters Booth",
                "type": "voice",
                "user_limit": 4,
            },
            {
                "name": "🥊 On Deck / Waiting Room",
                "type": "voice",
            },
            {
                "name": "⚔️ Arena 1 (Match Alpha)",
                "type": "voice",
                "user_limit": 2,
            },
            {
                "name": "⚔️ Arena 2 (Match Bravo)",
                "type": "voice",
                "user_limit": 2,
            },
            {
                "name": "🏆 Grand Finals Arena",
                "type": "voice",
            },
        ],
    },
    {
        "category": "🔒 TOURNAMENT OPERATIONS",
        "private": True,
        "channels": [
            {
                "name": "💻・tourney-staff-chat",
                "type": "text",
                "private": True,
            },
            {
                "name": "🤖・bot-control",
                "type": "text",
                "private": True,
            },
        ],
    },
]


async def build_tournament_section(
    guild: discord.Guild,
    log_callback: Optional[Callable[[str], None]] = None,
    delay: float = RATE_LIMIT_DELAY,
) -> Dict[str, Any]:
    """
    Builds the complete tournament category and channel architecture in the guild.
    Throttles API calls and records created/existing channel mappings.
    """
    def log(msg: str):
        logger.info(msg)
        if log_callback:
            try:
                log_callback(msg)
            except Exception as e:
                logger.debug("Error in log callback: %s", e)

    results = {
        "categories_created": 0,
        "categories_existing": 0,
        "channels_created": 0,
        "channels_existing": 0,
        "channel_map": {},  # role_key: channel_id
        "errors": [],
    }

    bot_member = guild.me
    if not bot_member or not bot_member.guild_permissions.manage_channels:
        err = "Bot is missing 'Manage Channels' permission in target server."
        log(f"❌ {err}")
        results["errors"].append(err)
        return results

    is_community = "COMMUNITY" in guild.features

    for group in TOURNAMENT_SECTION_SPEC:
        cat_name = group["category"]
        is_cat_private = group.get("private", False)

        # Check existing category
        target_category = discord.utils.find(
            lambda c: c.name.strip().lower() == cat_name.strip().lower(),
            guild.categories,
        )

        if target_category:
            results["categories_existing"] += 1
            log(f"📁 Category exists: '{cat_name}'")
        else:
            cat_overwrites = {}
            if is_cat_private and guild.default_role:
                cat_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                cat_overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, manage_channels=True)

            cat_kwargs = {"overwrites": cat_overwrites} if cat_overwrites else {}
            try:
                target_category = await guild.create_category(name=cat_name, **cat_kwargs)
                results["categories_created"] += 1
                log(f"✨ Created Category: '{cat_name}'")
                await asyncio.sleep(delay)
            except Exception as e:
                err = f"Failed to create category '{cat_name}': {e}"
                log(f"❌ {err}")
                results["errors"].append(err)
                continue

        # Channels inside category
        for ch_info in group.get("channels", []):
            ch_name = ch_info["name"]
            ch_type = ch_info.get("type", "text")
            user_limit = ch_info.get("user_limit", 0)
            is_private = ch_info.get("private", False) or is_cat_private
            read_only = ch_info.get("read_only", False)
            role_key = ch_info.get("role_key")

            # Check existing
            existing_ch = discord.utils.find(
                lambda c: c.name.strip().lower() == ch_name.strip().lower(),
                target_category.channels,
            )

            if existing_ch:
                results["channels_existing"] += 1
                if role_key:
                    results["channel_map"][role_key] = existing_ch.id
                log(f"  📌 Channel exists: '{ch_name}'")
                continue

            extra_kwargs: Dict[str, Any] = {}
            overwrites: Dict[Any, discord.PermissionOverwrite] = {}

            if is_private and guild.default_role:
                overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, manage_channels=True)
            elif read_only and guild.default_role:
                overwrites[guild.default_role] = discord.PermissionOverwrite(
                    send_messages=False,
                    add_reactions=True,
                    view_channel=True,
                )
                overwrites[guild.me] = discord.PermissionOverwrite(
                    send_messages=True,
                    view_channel=True,
                    manage_channels=True,
                )

            if overwrites:
                extra_kwargs["overwrites"] = overwrites

            try:
                created_ch = None
                if ch_type == "voice":
                    created_ch = await guild.create_voice_channel(
                        name=ch_name,
                        category=target_category,
                        user_limit=user_limit,
                        **extra_kwargs,
                    )
                    log(f"  🔊 Created Voice Arena: '{ch_name}' (limit: {user_limit or 'unlimited'})")
                elif ch_type == "news":
                    if is_community:
                        try:
                            created_ch = await guild.create_text_channel(
                                name=ch_name,
                                category=target_category,
                                news=True,
                                **extra_kwargs,
                            )
                            log(f"  📣 Created Announcement Channel: '{ch_name}'")
                        except Exception:
                            created_ch = await guild.create_text_channel(
                                name=ch_name,
                                category=target_category,
                                **extra_kwargs,
                            )
                            log(f"  💬 Created Text Channel (news fallback): '{ch_name}'")
                    else:
                        created_ch = await guild.create_text_channel(
                            name=ch_name,
                            category=target_category,
                            **extra_kwargs,
                        )
                        log(f"  💬 Created Text Channel: '{ch_name}'")
                else:
                    created_ch = await guild.create_text_channel(
                        name=ch_name,
                        category=target_category,
                        **extra_kwargs,
                    )
                    log(f"  💬 Created Text Channel: '{ch_name}'")

                if created_ch and role_key:
                    results["channel_map"][role_key] = created_ch.id

                results["channels_created"] += 1
                await asyncio.sleep(delay)

            except Exception as e:
                err = f"Failed to create channel '{ch_name}': {e}"
                log(f"  ❌ {err}")
                results["errors"].append(err)

    log(
        f"🏁 Tournament section build complete! Created {results['categories_created']} categories, "
        f"{results['channels_created']} channels."
    )
    return results


async def delete_tournament_section(
    guild: discord.Guild,
    log_callback: Optional[Callable[[str], None]] = None,
    delay: float = RATE_LIMIT_DELAY,
) -> Dict[str, Any]:
    """
    Safely removes all tournament categories and their channels defined in TOURNAMENT_SECTION_SPEC.
    """
    def log(msg: str):
        logger.info(msg)
        if log_callback:
            try:
                log_callback(msg)
            except Exception as e:
                logger.debug("Error in log callback: %s", e)

    results = {
        "categories_deleted": 0,
        "channels_deleted": 0,
        "errors": [],
    }

    bot_member = guild.me
    if not bot_member or not bot_member.guild_permissions.manage_channels:
        err = "Bot is missing 'Manage Channels' permission in target server."
        log(f"❌ {err}")
        results["errors"].append(err)
        return results

    spec_category_names = {
        group["category"].strip().lower()
        for group in TOURNAMENT_SECTION_SPEC
    }

    for cat in list(guild.categories):
        if cat.name.strip().lower() in spec_category_names:
            for ch in list(cat.channels):
                try:
                    await ch.delete(reason="Remove Tournament Section")
                    results["channels_deleted"] += 1
                    log(f"  🗑️ Deleted channel in '{cat.name}': '{ch.name}'")
                    await asyncio.sleep(delay)
                except Exception as e:
                    err = f"Failed to delete channel '{ch.name}': {e}"
                    log(f"  ❌ {err}")
                    results["errors"].append(err)

            try:
                await cat.delete(reason="Remove Tournament Section")
                results["categories_deleted"] += 1
                log(f"🗑️ Deleted category: '{cat.name}'")
                await asyncio.sleep(delay)
            except Exception as e:
                err = f"Failed to delete category '{cat.name}': {e}"
                log(f"❌ {err}")
                results["errors"].append(err)

    log(
        f"🏁 Tournament section removal complete: Deleted {results['categories_deleted']} categories and "
        f"{results['channels_deleted']} channels."
    )
    return results


class UndoTournamentSectionView(discord.ui.View):
    """
    Interactive View with an Undo button to safely delete the tournament section if needed.
    """
    def __init__(self, author_id: int):
        super().__init__(timeout=900)
        self.author_id = author_id

    @discord.ui.button(
        label="Undo Tournament Section",
        style=discord.ButtonStyle.danger,
        emoji="↩️",
    )
    async def undo_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_admin = False
        if interaction.guild:
            if interaction.user.id == interaction.guild.owner_id:
                is_admin = True
            elif isinstance(interaction.user, discord.Member):
                is_admin = interaction.user.guild_permissions.administrator

        if not is_admin:
            await interaction.response.send_message(
                "❌ **Permission Denied**: Only the Server Owner or members with Administrator permissions can remove the tournament section.",
                ephemeral=True,
            )
            return

        button.disabled = True
        button.label = "Removing tournament section..."
        await interaction.response.edit_message(view=self)

        results = await delete_tournament_section(interaction.guild)

        embed = discord.Embed(
            title="🧹 Tournament Section Removed",
            description=f"Cleaned up tournament categories and channels in **{interaction.guild.name}**.",
            color=0xE74C3C,
        )
        embed.add_field(
            name="📊 Channels Removed",
            value=f"`{results['channels_deleted']}`",
            inline=True,
        )
        embed.add_field(
            name="📁 Categories Removed",
            value=f"`{results['categories_deleted']}`",
            inline=True,
        )
        if results["errors"]:
            embed.add_field(
                name="⚠️ Notices / Errors",
                value="\n".join(f"• {e[:100]}" for e in results["errors"][:5]),
                inline=False,
            )
        embed.set_footer(text="Tournament System • Section Management")

        button.label = "Section Removed"
        await interaction.edit_original_response(embed=embed, view=self)
