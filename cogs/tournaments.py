"""
Discord Cog implementing all IDO Tournament slash commands, check-in flow, and admin tools.
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from services.tournament_service import (
    DEFAULT_WEAPONS,
    STANDARD_REGIONS,
    TournamentService,
)
from utils.ui import build_roster_embed, build_status_embed

logger = logging.getLogger(__name__)

# Predefined slash command choices (ME removed as requested)
WEAPON_CHOICES = [
    app_commands.Choice(name=w, value=w) for w in DEFAULT_WEAPONS
]

REGION_CHOICES = [
    app_commands.Choice(name=r, value=r) for r in STANDARD_REGIONS
]

EXPORT_FORMAT_CHOICES = [
    app_commands.Choice(name="CSV (Excel / Start.gg / Battlefy)", value="csv"),
    app_commands.Choice(name="Challonge (Player Name List)", value="challonge"),
    app_commands.Choice(name="Formatted Text", value="text"),
]

ANNOUNCE_TARGET_CHOICES = [
    app_commands.Choice(name="Main Bracket Only", value="main"),
    app_commands.Choice(name="Substitutes Only", value="subs"),
    app_commands.Choice(name="Everyone (Main + Subs)", value="all"),
]


def is_tournament_admin():
    """Custom check for administrator permission or designated Tournament Admin role."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False

        if interaction.user.id == interaction.guild.owner_id:
            return True

        if interaction.permissions.administrator:
            return True

        if isinstance(interaction.user, discord.Member):
            for role in interaction.user.roles:
                if role.name.lower() == config.admin_role_name.lower():
                    return True

        return False

    return app_commands.check(predicate)


class TournamentCog(commands.Cog):
    """Slash commands for IDO Tournament Roster and Substitute Queue management."""

    def __init__(self, bot: commands.Bot, service: TournamentService):
        self.bot = bot
        self.service = service

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """Global error handler for tournament cog commands."""
        if isinstance(error, app_commands.CheckFailure):
            msg = (
                f"❌ **Permission Denied**: You need Administrator permissions or the "
                f"`{config.admin_role_name}` role to run this command."
            )
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        logger.error("Unhandled error in tournament command: %s", error, exc_info=True)
        err_msg = "❌ An unexpected error occurred while processing the command."
        if interaction.response.is_done():
            await interaction.followup.send(err_msg, ephemeral=True)
        else:
            await interaction.response.send_message(err_msg, ephemeral=True)

    # =========================================================================
    # Participant Commands
    # =========================================================================

    @app_commands.command(
        name="tournament-register",
        description="Sign up for the main tournament bracket. Increases live slot counter.",
    )
    @app_commands.describe(
        ign="Your In-Game Name",
        weapon="Your selected approved weapon",
        region="Your competition region (NA, EU, OCE, ASIA, SA)",
    )
    @app_commands.choices(weapon=WEAPON_CHOICES, region=REGION_CHOICES)
    async def register(
        self,
        interaction: discord.Interaction,
        ign: str,
        weapon: app_commands.Choice[str],
        region: app_commands.Choice[str],
    ):
        success, message, participant = self.service.register_participant(
            user_id=interaction.user.id,
            user_mention=interaction.user.mention,
            ign=ign,
            weapon=weapon.value,
            region=region.value,
        )

        if not success:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        state = self.service.get_state()
        embed = discord.Embed(
            title="✅ Registered for Main Bracket",
            description=(
                f"**Participant:** {participant.ign} ({participant.user_mention})\n"
                f"**Weapon:** `{participant.weapon}`\n"
                f"**Region:** `{participant.region}`\n\n"
                f"📊 **Bracket Slots:** `{len(state.participants)} / {state.max_slots}` registered."
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-unregister",
        description="Withdraw from the main bracket (frees up slot for others).",
    )
    async def unregister(self, interaction: discord.Interaction):
        success, message = self.service.unregister_participant(interaction.user.id)
        if not success:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        state = self.service.get_state()
        embed = discord.Embed(
            title="👋 Main Bracket Withdrawal",
            description=(
                f"{message}\n\n"
                f"📊 **Bracket Slots:** `{len(state.participants)} / {state.max_slots}` registered."
            ),
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-sub-register",
        description="Sign up for the standby substitute queue.",
    )
    @app_commands.describe(
        ign="Your In-Game Name",
        weapon="Your selected approved weapon",
        region="Your competition region (NA, EU, OCE, ASIA, SA)",
    )
    @app_commands.choices(weapon=WEAPON_CHOICES, region=REGION_CHOICES)
    async def sub_register(
        self,
        interaction: discord.Interaction,
        ign: str,
        weapon: app_commands.Choice[str],
        region: app_commands.Choice[str],
    ):
        success, message, sub = self.service.register_substitute(
            user_id=interaction.user.id,
            user_mention=interaction.user.mention,
            ign=ign,
            weapon=weapon.value,
            region=region.value,
        )

        if not success:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        state = self.service.get_state()
        embed = discord.Embed(
            title="🛡️ Registered as Standby Substitute",
            description=(
                f"**Substitute:** {sub.ign} ({sub.user_mention})\n"
                f"**Weapon:** `{sub.weapon}`\n"
                f"**Region:** `{sub.region}`\n\n"
                f"🛡️ **Queue Position:** `#{len(state.substitutes)}` on deck."
            ),
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-sub-unregister",
        description="Withdraw from the substitute queue.",
    )
    async def sub_unregister(self, interaction: discord.Interaction):
        success, message = self.service.unregister_substitute(interaction.user.id)
        if not success:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        state = self.service.get_state()
        embed = discord.Embed(
            title="👋 Substitute Queue Withdrawal",
            description=(
                f"{message}\n\n"
                f"🛡️ **Substitutes on Deck:** `{len(state.substitutes)}` remaining."
            ),
            color=0x95A5A6,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-edit-entry",
        description="Update your weapon declaration, IGN, or region without losing your bracket spot.",
    )
    @app_commands.describe(
        weapon="Update your weapon choice",
        ign="Update your In-Game Name",
        region="Update your competition region",
    )
    @app_commands.choices(weapon=WEAPON_CHOICES, region=REGION_CHOICES)
    async def edit_entry(
        self,
        interaction: discord.Interaction,
        weapon: Optional[app_commands.Choice[str]] = None,
        ign: Optional[str] = None,
        region: Optional[app_commands.Choice[str]] = None,
    ):
        if not weapon and not ign and not region:
            await interaction.response.send_message(
                "❌ Please specify at least one field (`weapon`, `ign`, or `region`) to update.",
                ephemeral=True,
            )
            return

        success, msg, _ = self.service.edit_entry(
            user_id=interaction.user.id,
            weapon=weapon.value if weapon else None,
            ign=ign,
            region=region.value if region else None,
        )

        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        embed = discord.Embed(
            title="✏️ Entry Updated",
            description=msg,
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="tournament-checkin",
        description="Confirm your presence on tournament day during the check-in window.",
    )
    async def checkin(self, interaction: discord.Interaction):
        success, msg = self.service.checkin_user(interaction.user.id)
        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎟️ Tournament Check-In",
            description=msg,
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-status",
        description="View main & substitute status, slot counters, visual progress bar, and weapons.",
    )
    async def status(self, interaction: discord.Interaction):
        state = self.service.get_state()
        embed = build_status_embed(state)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-roster",
        description="View registered main bracket roster and standby substitute list.",
    )
    async def roster(self, interaction: discord.Interaction):
        state = self.service.get_state()
        embed = build_roster_embed(state)
        await interaction.response.send_message(embed=embed)

    # =========================================================================
    # Admin Controls
    # =========================================================================

    @app_commands.command(
        name="tournament-open",
        description="[Admin] Open main bracket registrations and set slot capacity.",
    )
    @app_commands.describe(
        name="Tournament title / event name",
        slots="Maximum participant capacity (e.g. 8, 16, 32, 64)",
        regions="Allowed regions filter (e.g. 'GLOBAL', 'NA', 'EU', or 'NA, EU')",
        open_subs="Whether to open substitute signups immediately (default: False)",
    )
    @is_tournament_admin()
    async def open_tournament(
        self,
        interaction: discord.Interaction,
        name: Optional[str] = None,
        slots: Optional[int] = None,
        regions: Optional[str] = None,
        open_subs: bool = False,
    ):
        try:
            msg = self.service.open_tournament(
                name=name, slots=slots, regions=regions, open_subs=open_subs
            )
            embed = discord.Embed(
                title="🏆 Tournament Registrations Opened",
                description=msg,
                color=0x2ECC71,
            )
            embed.set_footer(text=f"{config.organization_name} • Tournament System")
            await interaction.response.send_message(embed=embed)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)

    @app_commands.command(
        name="tournament-close",
        description="[Admin] Close main bracket registrations.",
    )
    @is_tournament_admin()
    async def close_tournament(self, interaction: discord.Interaction):
        msg = self.service.close_tournament()
        embed = discord.Embed(
            title="🔒 Main Bracket Closed",
            description=msg,
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-open-subs",
        description="[Admin] Enable the substitute sign-up section for standby players.",
    )
    @is_tournament_admin()
    async def open_subs(self, interaction: discord.Interaction):
        msg = self.service.open_subs()
        embed = discord.Embed(
            title="🟢 Substitute Signups Opened",
            description=msg,
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-close-subs",
        description="[Admin] Disable substitute signups.",
    )
    @is_tournament_admin()
    async def close_subs(self, interaction: discord.Interaction):
        msg = self.service.close_subs()
        embed = discord.Embed(
            title="🔴 Substitute Signups Closed",
            description=msg,
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-open-checkin",
        description="[Admin] Open tournament day check-in for participants.",
    )
    @is_tournament_admin()
    async def open_checkin(self, interaction: discord.Interaction):
        msg = self.service.open_checkin()
        embed = discord.Embed(
            title="📢 Tournament Check-In Opened",
            description=msg,
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-close-checkin",
        description="[Admin] Close tournament day check-in.",
    )
    @is_tournament_admin()
    async def close_checkin(self, interaction: discord.Interaction):
        msg = self.service.close_checkin()
        embed = discord.Embed(
            title="🔒 Tournament Check-In Closed",
            description=msg,
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-kick",
        description="[Admin] Remove a specific user from either the main bracket or substitute queue.",
    )
    @app_commands.describe(
        user="The Discord user to remove",
        reason="Optional reason for the removal",
    )
    @is_tournament_admin()
    async def kick_user(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: Optional[str] = None,
    ):
        success, msg = self.service.kick_user(user.id, reason or "")
        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        embed = discord.Embed(
            title="👢 Tournament Removal",
            description=msg,
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-force-register",
        description="[Admin] Manually register a user into the main bracket or substitute queue.",
    )
    @app_commands.describe(
        user="The Discord member to register",
        ign="The In-Game Name for this player",
        weapon="Assigned weapon",
        region="Assigned region (NA, EU, OCE, ASIA, SA)",
        as_sub="Register into substitute queue instead of main bracket (default: False)",
    )
    @app_commands.choices(weapon=WEAPON_CHOICES, region=REGION_CHOICES)
    @is_tournament_admin()
    async def force_register(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        ign: str,
        weapon: app_commands.Choice[str],
        region: app_commands.Choice[str],
        as_sub: bool = False,
    ):
        success, msg, _ = self.service.force_register(
            user_id=user.id,
            user_mention=user.mention,
            ign=ign,
            weapon=weapon.value,
            region=region.value,
            as_sub=as_sub,
        )

        embed = discord.Embed(
            title="👑 Admin Force Registration",
            description=msg,
            color=0xF1C40F,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-promote-sub",
        description="[Admin] Swap a no-show player with a standby substitute.",
    )
    @app_commands.describe(
        substitute="Specific standby substitute to promote (leave blank for next in line)",
        replace="No-show player in main bracket to replace (leave blank to fill empty slot)",
    )
    @is_tournament_admin()
    async def promote_sub(
        self,
        interaction: discord.Interaction,
        substitute: Optional[discord.Member] = None,
        replace: Optional[discord.Member] = None,
    ):
        sub_id = substitute.id if substitute else None
        rep_id = replace.id if replace else None

        success, message, _ = self.service.promote_substitute(
            substitute_user_id=sub_id,
            replace_user_id=rep_id,
        )

        if not success:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔄 Substitute Promoted",
            description=message,
            color=0x9B59B6,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-set-limit",
        description="[Admin] Adjust the maximum participant limit counter (e.g. 16, 32, 64).",
    )
    @app_commands.describe(limit="New maximum slot capacity")
    @is_tournament_admin()
    async def set_limit(self, interaction: discord.Interaction, limit: int):
        try:
            msg = self.service.set_limit(limit)
            embed = discord.Embed(
                title="📊 Capacity Limit Updated",
                description=msg,
                color=0xF1C40F,
            )
            embed.set_footer(text=f"{config.organization_name} • Tournament System")
            await interaction.response.send_message(embed=embed)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)

    @app_commands.command(
        name="tournament-set-regions",
        description="[Admin] Adjust the allowed competition regions filter.",
    )
    @app_commands.describe(
        regions="Allowed regions (e.g. 'GLOBAL', 'NA', 'EU', or 'NA, EU, OCE')"
    )
    @is_tournament_admin()
    async def set_regions(self, interaction: discord.Interaction, regions: str):
        msg = self.service.set_regions(regions)
        embed = discord.Embed(
            title="🌍 Allowed Regions Updated",
            description=msg,
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-set-weapons",
        description="[Admin] Set approved weapon classes for this event (comma-separated).",
    )
    @app_commands.describe(
        weapons="Comma-separated approved weapons (e.g. 'Katana, Naginata' or leave blank for default)"
    )
    @is_tournament_admin()
    async def set_weapons(self, interaction: discord.Interaction, weapons: Optional[str] = None):
        msg = self.service.set_approved_weapons(weapons or "")
        embed = discord.Embed(
            title="⚔️ Tournament Weapons Updated",
            description=msg,
            color=0xF1C40F,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-announce",
        description="[Admin] Ping and announce tournament information to registered players.",
    )
    @app_commands.describe(
        message="The announcement message to broadcast",
        target="Who to ping (Main Bracket, Substitutes, or Everyone)",
    )
    @app_commands.choices(target=ANNOUNCE_TARGET_CHOICES)
    @is_tournament_admin()
    async def announce(
        self,
        interaction: discord.Interaction,
        message: str,
        target: Optional[app_commands.Choice[str]] = None,
    ):
        target_val = target.value if target else "main"
        state = self.service.get_state()

        mentions = []
        if target_val in ("main", "all"):
            mentions.extend(p.user_mention for p in state.participants)
        if target_val in ("subs", "all"):
            mentions.extend(s.user_mention for s in state.substitutes)

        if not mentions:
            await interaction.response.send_message(
                "❌ No participants found in the selected target group.", ephemeral=True
            )
            return

        mentions_text = " ".join(mentions)
        embed = discord.Embed(
            title=f"📢 Tournament Announcement — {state.name}",
            description=message,
            color=0xF1C40F,
        )
        embed.set_footer(text=f"Announced by {interaction.user.display_name} • {config.organization_name}")

        await interaction.response.send_message(content=mentions_text, embed=embed)

    @app_commands.command(
        name="tournament-export",
        description="[Admin] Export tournament roster for Challonge, Start.gg, or Excel.",
    )
    @app_commands.describe(format="Export file format")
    @app_commands.choices(format=EXPORT_FORMAT_CHOICES)
    @is_tournament_admin()
    async def export_roster(
        self,
        interaction: discord.Interaction,
        format: Optional[app_commands.Choice[str]] = None,
    ):
        fmt = format.value if format else "csv"
        filename, content = self.service.export_roster(fmt)
        file_bytes = io.BytesIO(content.encode("utf-8"))
        discord_file = discord.File(file_bytes, filename=filename)

        format_name = format.name if format else "CSV"
        state = self.service.get_state()
        await interaction.response.send_message(
            content=(
                f"📁 **Roster Export Ready**\n"
                f"• Event: **{state.name}**\n"
                f"• Format: `{format_name}`\n"
                f"• Players: `{len(state.participants)}` main, `{len(state.substitutes)}` subs"
            ),
            file=discord_file,
            ephemeral=True,
        )

    @app_commands.command(
        name="tournament-clear",
        description="[Admin] Wipe both main roster and substitute list for a fresh event.",
    )
    @is_tournament_admin()
    async def clear_tournament(self, interaction: discord.Interaction):
        msg = self.service.clear_tournament()
        embed = discord.Embed(
            title="🧹 Tournament Reset",
            description=msg,
            color=0xE67E22,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    """Cog setup registration entry point."""
    service: TournamentService = getattr(bot, "tournament_service", None)
    if not service:
        from utils.storage import StorageManager
        storage = StorageManager(config.tournament_file, config.backup_dir, config.max_backups)
        service = TournamentService(storage)
        bot.tournament_service = service
    await bot.add_cog(TournamentCog(bot, service))
