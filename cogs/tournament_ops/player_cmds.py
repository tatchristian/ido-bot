"""
Player-facing tournament slash commands: /help, /register, /unregister,
/sub, /sub-unregister, /edit-entry, /checkin, /sub-checkin, /status, /roster.
"""

from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands

from config import config
from utils.tournament_embeds import (
    build_help_embed,
    build_roster_embed,
    build_status_embed,
)
from utils.tournament_views import HelpView, check_is_tournament_admin

from .constants import HELP_SECTION_CHOICES, REGION_CHOICES, WEAPON_CHOICES


class TournamentPlayerMixin:
    """1-word top-level player slash commands for UDA Tournament registration & checkin."""

    # =========================================================================
    # Help & Guidance
    # =========================================================================

    async def _send_help(
        self,
        interaction: discord.Interaction,
        section: Optional[app_commands.Choice[str]] = None,
        ephemeral: bool = True,
    ):
        sec = section.value if section else "all"
        is_admin = check_is_tournament_admin(interaction.user, interaction.guild, self.bot)
        embed = build_help_embed(sec, is_admin=is_admin)
        view = HelpView(is_admin=is_admin)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)

    @app_commands.command(
        name="help",
        description="Interactive guide and command manual for the UDA Tournament Bot.",
    )
    @app_commands.describe(
        section="Jump directly to a specific guide category",
        ephemeral="Whether the help message is only visible to you (default: True)",
    )
    @app_commands.choices(section=HELP_SECTION_CHOICES)
    async def tournament_help(
        self,
        interaction: discord.Interaction,
        section: Optional[app_commands.Choice[str]] = None,
        ephemeral: bool = True,
    ):
        await self._send_help(interaction, section=section, ephemeral=ephemeral)

    # =========================================================================
    # Participant Commands
    # =========================================================================

    @app_commands.command(
        name="register",
        description="Sign up for the main tournament bracket. Increases live slot counter.",
    )
    @app_commands.describe(
        ign="Your In-Game Name",
        region="Your competition region (NA, EU, OCE, ASIA, SA)",
        weapon="Optional weapon choice (optional)",
    )
    @app_commands.choices(weapon=WEAPON_CHOICES, region=REGION_CHOICES)
    async def register(
        self,
        interaction: discord.Interaction,
        ign: str,
        region: app_commands.Choice[str],
        weapon: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer()
        guild_id = interaction.guild_id or 0
        chosen_weapon = weapon.value if weapon else "Standard"
        success, message, participant = self.service.register_participant(
            user_id=interaction.user.id,
            user_mention=interaction.user.mention,
            ign=ign,
            weapon=chosen_weapon,
            region=region.value,
            guild_id=guild_id,
        )

        if not success:
            await interaction.followup.send(f"❌ {message}")
            return

        await self._assign_participant_role(interaction.guild, interaction.user)
        await self._update_registration_panel(interaction.guild)

        state = self.service.get_state(guild_id)
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
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="unregister",
        description="Withdraw from the main bracket (frees up slot for others).",
    )
    async def unregister(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = interaction.guild_id or 0
        success, message = self.service.unregister_participant(interaction.user.id, guild_id=guild_id)
        if not success:
            await interaction.followup.send(f"❌ {message}")
            return

        await self._remove_participant_role(interaction.guild, interaction.user)
        await self._update_registration_panel(interaction.guild)

        state = self.service.get_state(guild_id)
        embed = discord.Embed(
            title="👋 Main Bracket Withdrawal",
            description=(
                f"{message}\n\n"
                f"📊 **Bracket Slots:** `{len(state.participants)} / {state.max_slots}` registered."
            ),
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="sub",
        description="Sign up for the standby substitute queue.",
    )
    @app_commands.describe(
        ign="Your In-Game Name",
        region="Your competition region (NA, EU, OCE, ASIA, SA)",
        weapon="Optional weapon choice (optional)",
    )
    @app_commands.choices(weapon=WEAPON_CHOICES, region=REGION_CHOICES)
    async def sub_register(
        self,
        interaction: discord.Interaction,
        ign: str,
        region: app_commands.Choice[str],
        weapon: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer()
        guild_id = interaction.guild_id or 0
        chosen_weapon = weapon.value if weapon else "Standard"
        success, message, sub = self.service.register_substitute(
            user_id=interaction.user.id,
            user_mention=interaction.user.mention,
            ign=ign,
            weapon=chosen_weapon,
            region=region.value,
            guild_id=guild_id,
        )

        if not success:
            await interaction.followup.send(f"❌ {message}")
            return

        await self._update_subs_panel(interaction.guild)

        state = self.service.get_state(guild_id)
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

        subs_ch = (
            interaction.guild.get_channel(state.subs_channel_id)
            if (interaction.guild and state.subs_channel_id)
            else None
        )
        if subs_ch and subs_ch != interaction.channel:
            perms = subs_ch.permissions_for(interaction.guild.me)
            if perms.send_messages and perms.embed_links:
                await subs_ch.send(embed=embed)
                await interaction.followup.send(
                    f"🛡️ Registered as Standby Substitute (**{sub.ign}**)!\n💡 *Logged into {subs_ch.mention} to keep this chat clean.*"
                )
                return

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="sub-unregister",
        description="Withdraw from the substitute queue.",
    )
    async def sub_unregister(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = interaction.guild_id or 0
        success, message = self.service.unregister_substitute(interaction.user.id, guild_id=guild_id)
        if not success:
            await interaction.followup.send(f"❌ {message}")
            return

        await self._update_subs_panel(interaction.guild)

        state = self.service.get_state(guild_id)
        embed = discord.Embed(
            title="👋 Substitute Queue Withdrawal",
            description=(
                f"{message}\n\n"
                f"🛡️ **Substitutes on Deck:** `{len(state.substitutes)}` remaining."
            ),
            color=0x95A5A6,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")

        subs_ch = (
            interaction.guild.get_channel(state.subs_channel_id)
            if (interaction.guild and state.subs_channel_id)
            else None
        )
        if subs_ch and subs_ch != interaction.channel:
            perms = subs_ch.permissions_for(interaction.guild.me)
            if perms.send_messages and perms.embed_links:
                await subs_ch.send(embed=embed)
                await interaction.followup.send(
                    f"{message}\n💡 *Logged into {subs_ch.mention} to keep this chat clean.*"
                )
                return

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="edit-entry",
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
        await interaction.response.defer(ephemeral=True)
        if not weapon and not ign and not region:
            await interaction.followup.send(
                "❌ Please specify at least one field (`weapon`, `ign`, or `region`) to update.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild_id or 0
        success, msg, _ = self.service.edit_entry(
            user_id=interaction.user.id,
            weapon=weapon.value if weapon else None,
            ign=ign,
            region=region.value if region else None,
            guild_id=guild_id,
        )

        if not success:
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)
            return

        await self._update_registration_panel(interaction.guild)
        await self._update_subs_panel(interaction.guild)

        embed = discord.Embed(
            title="✏️ Entry Updated",
            description=msg,
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="checkin",
        description="Confirm your presence on tournament day during the check-in window.",
    )
    async def checkin(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id or 0
        res = self.service.checkin_user(interaction.user.id, guild_id=guild_id)
        success, msg, part, role_type = res.success, res.message, res.participant, res.role_type
        if not success:
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)
            return

        await self._update_all_live_panels(interaction.guild)
        await self._dispatch_checkin_log(interaction.guild, part, action="checked_in", role_type=role_type)

        embed = discord.Embed(
            title="🎟️ Tournament Check-In",
            description=msg,
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")

        state = self.service.get_state(guild_id)
        log_ch = (
            interaction.guild.get_channel(state.checkin_log_channel_id or state.checkin_channel_id)
            if (interaction.guild and (state.checkin_log_channel_id or state.checkin_channel_id))
            else None
        )
        log_note = f"\n💡 *Audit receipt logged to {log_ch.mention}.*" if log_ch else ""
        await interaction.followup.send(f"{msg}{log_note}", ephemeral=True)

    @app_commands.command(
        name="sub-checkin",
        description="Confirm your standby availability as a substitute on tournament day.",
    )
    async def sub_checkin(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id or 0
        res = self.service.checkin_user(interaction.user.id, guild_id=guild_id)
        success, msg, part, role_type = res.success, res.message, res.participant, res.role_type
        if not success:
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)
            return

        await self._update_all_live_panels(interaction.guild)
        await self._dispatch_checkin_log(interaction.guild, part, action="checked_in", role_type=role_type)

        state = self.service.get_state(guild_id)
        log_ch = (
            interaction.guild.get_channel(state.checkin_log_channel_id or state.checkin_channel_id)
            if (interaction.guild and (state.checkin_log_channel_id or state.checkin_channel_id))
            else None
        )
        log_note = f"\n💡 *Audit receipt logged to {log_ch.mention}.*" if log_ch else ""
        await interaction.followup.send(f"{msg}{log_note}", ephemeral=True)

    @app_commands.command(
        name="status",
        description="View main & substitute status, slot counters, visual progress bar, and weapons.",
    )
    async def status(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        embed = build_status_embed(state)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="roster",
        description="View registered main bracket roster and standby substitute list.",
    )
    async def roster(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        embed = build_roster_embed(state)
        await interaction.response.send_message(embed=embed)
