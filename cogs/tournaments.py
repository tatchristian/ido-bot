"""
Discord Cog implementing all IDO Tournament slash commands, check-in flow, help manual, and admin tools.
Fully supports isolated per-server (multi-guild) tournaments.
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from services.server_builder import (
    UndoTournamentSectionView,
    build_tournament_section,
    delete_tournament_section,
)
from services.tournament_service import (
    DEFAULT_WEAPONS,
    STANDARD_REGIONS,
    TournamentService,
)
from utils.ui import build_help_embed, build_roster_embed, build_status_embed

logger = logging.getLogger(__name__)

# Predefined slash command choices (ME removed as requested)
WEAPON_CHOICES = [
    app_commands.Choice(name=w, value=w) for w in DEFAULT_WEAPONS
]

REGION_CHOICES = [
    app_commands.Choice(name=r, value=r) for r in STANDARD_REGIONS
]

REGION_FILTER_CHOICES = [
    app_commands.Choice(name="GLOBAL (All Regions Allowed)", value="GLOBAL"),
    app_commands.Choice(name="NA (North America)", value="NA"),
    app_commands.Choice(name="EU (Europe)", value="EU"),
    app_commands.Choice(name="OCE (Oceania)", value="OCE"),
    app_commands.Choice(name="ASIA (Asia)", value="ASIA"),
    app_commands.Choice(name="SA (South America)", value="SA"),
]

EXPORT_FORMAT_CHOICES = [
    app_commands.Choice(name="CSV (Excel / Start.gg / Battlefy)", value="csv"),
    app_commands.Choice(name="Challonge (Player Name List)", value="challonge"),
    app_commands.Choice(name="Formatted Text", value="text"),
]

EXPORT_TARGET_CHOICES = [
    app_commands.Choice(name="Main Bracket (For Challonge / Start.gg Import — Excludes Subs)", value="main"),
    app_commands.Choice(name="All (Full Roster with Substitutes)", value="all"),
    app_commands.Choice(name="Substitutes Only", value="subs"),
]

ANNOUNCE_TARGET_CHOICES = [
    app_commands.Choice(name="Main Bracket Only", value="main"),
    app_commands.Choice(name="Substitutes Only", value="subs"),
    app_commands.Choice(name="Everyone (Main + Subs)", value="all"),
]

HELP_SECTION_CHOICES = [
    app_commands.Choice(name="Overview (All Commands)", value="all"),
    app_commands.Choice(name="Participant Commands", value="participants"),
    app_commands.Choice(name="Admin Controls", value="admin"),
    app_commands.Choice(name="Weapons, Regions & Rules", value="weapons_regions"),
]


def is_tournament_admin():
    """Custom check for administrator permission or designated Tournament Admin role or higher in hierarchy."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False

        if interaction.user.id == interaction.guild.owner_id:
            return True

        if interaction.permissions.administrator:
            return True

        if not isinstance(interaction.user, discord.Member):
            return False

        cog = interaction.client.get_cog("TournamentCog")
        target_role_id = None
        target_role_name = config.admin_role_name
        if cog and hasattr(cog, "service"):
            guild_state = cog.service.get_state(interaction.guild_id or 0)
            target_role_id = guild_state.admin_role_id or config.admin_role_id
            target_role_name = guild_state.admin_role_name or config.admin_role_name
        else:
            target_role_id = config.admin_role_id

        threshold_role = None
        if target_role_id:
            threshold_role = interaction.guild.get_role(target_role_id)

        if not threshold_role and target_role_name:
            target_name_lower = target_role_name.strip().lower()
            threshold_role = discord.utils.find(
                lambda r: r.name.strip().lower() == target_name_lower,
                interaction.guild.roles,
            )

        if threshold_role is not None:
            if interaction.user.top_role.position >= threshold_role.position:
                return True

        return False

    return app_commands.check(predicate)


def is_server_admin():
    """Strict check: requires Server Administrator permission or Server Ownership."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False
        if interaction.user.id == interaction.guild.owner_id:
            return True
        return interaction.permissions.administrator

    return app_commands.check(predicate)


class HelpView(discord.ui.View):
    """Interactive navigation buttons for the /tournament-help command."""

    def __init__(self, timeout: float = 180.0):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="👥 Participants", style=discord.ButtonStyle.primary, custom_id="help_participants")
    async def participant_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_help_embed("participants")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🛠️ Admins", style=discord.ButtonStyle.secondary, custom_id="help_admin")
    async def admin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_help_embed("admin")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⚔️ Rules & Weapons", style=discord.ButtonStyle.secondary, custom_id="help_weapons")
    async def weapons_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_help_embed("weapons_regions")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="📖 View All", style=discord.ButtonStyle.success, custom_id="help_all")
    async def all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_help_embed("all")
        await interaction.response.edit_message(embed=embed, view=self)


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
            guild_state = self.service.get_state(interaction.guild_id or 0)
            role_name = guild_state.admin_role_name or config.admin_role_name
            msg = (
                f"❌ **Permission Denied**: You need Administrator permissions or the "
                f"`{role_name}` role (or higher in server role hierarchy) to run this command."
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

    async def _assign_participant_role(
        self, guild: Optional[discord.Guild], user: discord.User | discord.Member
    ):
        """Safely assigns the tournament participant role to a member if configured and permitted."""
        if not guild or not user:
            return
        member = user if isinstance(user, discord.Member) else guild.get_member(user.id)
        if not member:
            return
        state = self.service.get_state(guild.id)
        if not state.participant_role_id:
            return
        role = guild.get_role(state.participant_role_id)
        if (
            role
            and guild.me.guild_permissions.manage_roles
            and role < guild.me.top_role
        ):
            try:
                if role not in member.roles:
                    await member.add_roles(role, reason=f"Participant in {state.name}")
            except (discord.Forbidden, discord.HTTPException) as exc:
                logger.warning("Failed to assign role %s to user %s: %s", role.id, member.id, exc)

    async def _remove_participant_role(
        self, guild: Optional[discord.Guild], user: discord.User | discord.Member
    ):
        """Safely removes the tournament participant role from a member if configured and permitted."""
        if not guild or not user:
            return
        member = user if isinstance(user, discord.Member) else guild.get_member(user.id)
        if not member:
            return
        state = self.service.get_state(guild.id)
        if not state.participant_role_id:
            return
        role = guild.get_role(state.participant_role_id)
        if (
            role
            and guild.me.guild_permissions.manage_roles
            and role < guild.me.top_role
        ):
            try:
                if role in member.roles:
                    await member.remove_roles(role, reason=f"Removed from {state.name}")
            except (discord.Forbidden, discord.HTTPException) as exc:
                logger.warning("Failed to remove role %s from user %s: %s", role.id, member.id, exc)

    async def _send_or_dispatch(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel],
        embed: discord.Embed,
        content: Optional[str] = None,
        allowed_mentions: Optional[discord.AllowedMentions] = None,
        confirm_message: str = "Dispatched",
    ):
        """Sends to target channel if specified and distinct; otherwise sends in the current interaction channel."""
        if channel and interaction.guild and channel != interaction.channel:
            perms = channel.permissions_for(interaction.guild.me)
            if not perms.send_messages or not perms.embed_links:
                await interaction.response.send_message(
                    f"❌ I don't have permissions to send messages/embeds in {channel.mention}.",
                    ephemeral=True,
                )
                return
            await channel.send(content=content, embed=embed, allowed_mentions=allowed_mentions)
            await interaction.response.send_message(
                f"✅ {confirm_message} to {channel.mention}.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                content=content, embed=embed, allowed_mentions=allowed_mentions
            )

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
        embed = build_help_embed(sec)
        view = HelpView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)

    @app_commands.command(
        name="tournament-help",
        description="Interactive guide and command manual for the IDO Tournament Bot.",
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

    @app_commands.command(
        name="help-tournament",
        description="Interactive guide and command manual for the IDO Tournament Bot (alias for /tournament-help).",
    )
    @app_commands.describe(
        section="Jump directly to a specific guide category",
        ephemeral="Whether the help message is only visible to you (default: True)",
    )
    @app_commands.choices(section=HELP_SECTION_CHOICES)
    async def help_tournament_alias(
        self,
        interaction: discord.Interaction,
        section: Optional[app_commands.Choice[str]] = None,
        ephemeral: bool = True,
    ):
        await self._send_help(interaction, section=section, ephemeral=ephemeral)

    @app_commands.command(
        name="help",
        description="Interactive guide and command manual for the IDO Tournament Bot (alias for /tournament-help).",
    )
    @app_commands.describe(
        section="Jump directly to a specific guide category",
        ephemeral="Whether the help message is only visible to you (default: True)",
    )
    @app_commands.choices(section=HELP_SECTION_CHOICES)
    async def help_alias(
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
        guild_id = interaction.guild_id or 0
        success, message, participant = self.service.register_participant(
            user_id=interaction.user.id,
            user_mention=interaction.user.mention,
            ign=ign,
            weapon=weapon.value,
            region=region.value,
            guild_id=guild_id,
        )

        if not success:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        await self._assign_participant_role(interaction.guild, interaction.user)

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
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-unregister",
        description="Withdraw from the main bracket (frees up slot for others).",
    )
    async def unregister(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        success, message = self.service.unregister_participant(interaction.user.id, guild_id=guild_id)
        if not success:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        await self._remove_participant_role(interaction.guild, interaction.user)

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
        guild_id = interaction.guild_id or 0
        success, message, sub = self.service.register_substitute(
            user_id=interaction.user.id,
            user_mention=interaction.user.mention,
            ign=ign,
            weapon=weapon.value,
            region=region.value,
            guild_id=guild_id,
        )

        if not success:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

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
                await interaction.response.send_message(
                    f"🛡️ Registered as Standby Substitute (**{sub.ign}**)!\n💡 *Logged into {subs_ch.mention} to keep this chat clean.*",
                    ephemeral=True,
                )
                return

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-sub-unregister",
        description="Withdraw from the substitute queue.",
    )
    async def sub_unregister(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        success, message = self.service.unregister_substitute(interaction.user.id, guild_id=guild_id)
        if not success:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

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
                await interaction.response.send_message(
                    f"{message}\n💡 *Logged into {subs_ch.mention} to keep this chat clean.*",
                    ephemeral=True,
                )
                return

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

        guild_id = interaction.guild_id or 0
        success, msg, _ = self.service.edit_entry(
            user_id=interaction.user.id,
            weapon=weapon.value if weapon else None,
            ign=ign,
            region=region.value if region else None,
            guild_id=guild_id,
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
        guild_id = interaction.guild_id or 0
        success, msg = self.service.checkin_user(interaction.user.id, guild_id=guild_id)
        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎟️ Tournament Check-In",
            description=msg,
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")

        state = self.service.get_state(guild_id)
        checkin_ch = (
            interaction.guild.get_channel(state.checkin_channel_id)
            if (interaction.guild and state.checkin_channel_id)
            else None
        )
        if checkin_ch and checkin_ch != interaction.channel:
            perms = checkin_ch.permissions_for(interaction.guild.me)
            if perms.send_messages and perms.embed_links:
                await checkin_ch.send(embed=embed)
                await interaction.response.send_message(
                    f"{msg}\n💡 *Logged into {checkin_ch.mention} to keep this chat clean.*",
                    ephemeral=True,
                )
                return

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-sub-checkin",
        description="Confirm your standby availability as a substitute on tournament day.",
    )
    async def sub_checkin(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        success, msg = self.service.checkin_user(interaction.user.id, guild_id=guild_id)
        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        embed = discord.Embed(
            title="🛡️ Substitute Check-In Confirmed",
            description=msg,
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")

        state = self.service.get_state(guild_id)
        target_ch_id = state.subs_channel_id or state.checkin_channel_id
        target_ch = (
            interaction.guild.get_channel(target_ch_id)
            if (interaction.guild and target_ch_id)
            else None
        )
        if target_ch and target_ch != interaction.channel:
            perms = target_ch.permissions_for(interaction.guild.me)
            if perms.send_messages and perms.embed_links:
                await target_ch.send(embed=embed)
                await interaction.response.send_message(
                    f"{msg}\n💡 *Logged into {target_ch.mention} to keep this chat clean.*",
                    ephemeral=True,
                )
                return

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-status",
        description="View main & substitute status, slot counters, visual progress bar, and weapons.",
    )
    async def status(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        embed = build_status_embed(state)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-roster",
        description="View registered main bracket roster and standby substitute list.",
    )
    async def roster(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
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
        region_1="Primary allowed region tag (e.g. GLOBAL, NA, EU)",
        region_2="Additional allowed region tag",
        region_3="Additional allowed region tag",
        custom_regions="Optional: Type custom comma-separated regions if not using tags",
        open_subs="Whether to open substitute signups immediately (default: False)",
    )
    @app_commands.choices(
        region_1=REGION_FILTER_CHOICES,
        region_2=REGION_CHOICES,
        region_3=REGION_CHOICES,
    )
    @is_tournament_admin()
    async def open_tournament(
        self,
        interaction: discord.Interaction,
        name: Optional[str] = None,
        slots: Optional[int] = None,
        region_1: Optional[app_commands.Choice[str]] = None,
        region_2: Optional[app_commands.Choice[str]] = None,
        region_3: Optional[app_commands.Choice[str]] = None,
        custom_regions: Optional[str] = None,
        open_subs: bool = False,
    ):
        selected_regions: list[str] | None = None
        tag_list = [r.value for r in (region_1, region_2, region_3) if r]
        if tag_list or custom_regions:
            selected_regions = list(tag_list)
            if custom_regions:
                selected_regions.extend(self.service.parse_regions(custom_regions))
        try:
            guild_id = interaction.guild_id or 0
            current_state = self.service.get_state(guild_id)
            tourney_name = name.strip() if name else current_state.name

            # Auto-manage tournament participant role based on tournament name
            participant_role = None
            if interaction.guild:
                role_name = f"{tourney_name} Participant"[:100]
                participant_role = discord.utils.get(interaction.guild.roles, name=role_name)
                if not participant_role:
                    participant_role = discord.utils.get(interaction.guild.roles, name=tourney_name[:100])

                if not participant_role and interaction.guild.me.guild_permissions.manage_roles:
                    try:
                        participant_role = await interaction.guild.create_role(
                            name=role_name,
                            mentionable=True,
                            reason=f"Auto-created IDO tournament participant role for {tourney_name}",
                        )
                    except (discord.Forbidden, discord.HTTPException) as exc:
                        logger.warning("Could not auto-create role for %s: %s", tourney_name, exc)

            p_role_id = participant_role.id if participant_role else None
            p_role_name = participant_role.name if participant_role else None

            msg = self.service.open_tournament(
                name=name,
                slots=slots,
                regions=selected_regions,
                open_subs=open_subs,
                participant_role_id=p_role_id,
                participant_role_name=p_role_name,
                guild_id=guild_id,
            )

            # Assign role to any players already registered
            if (
                participant_role
                and interaction.guild
                and interaction.guild.me.guild_permissions.manage_roles
                and participant_role < interaction.guild.me.top_role
            ):
                for p in self.service.get_state(guild_id).participants:
                    mem = interaction.guild.get_member(p.user_id)
                    if mem and participant_role not in mem.roles:
                        try:
                            await mem.add_roles(participant_role, reason=f"Participant in {tourney_name}")
                        except (discord.Forbidden, discord.HTTPException):
                            pass

            embed = discord.Embed(
                title="🏆 Tournament Registrations Opened",
                description=msg,
                color=0x2ECC71,
            )
            embed.add_field(
                name="📝 How to Enter",
                value=(
                    "• Use `/tournament-register` to sign up for the main bracket.\n"
                    "• Use `/tournament-unregister` if you need to withdraw and free your slot.\n"
                    "• Use `/tournament-status` to view open slots, regions & weapons."
                    + ("\n• Use `/tournament-sub-register` to join the standby substitute queue." if open_subs else "")
                ),
                inline=False,
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
        guild_id = interaction.guild_id or 0
        msg = self.service.close_tournament(guild_id=guild_id)
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
        guild_id = interaction.guild_id or 0
        msg = self.service.open_subs(guild_id=guild_id)
        embed = discord.Embed(
            title="🟢 Substitute Signups Opened",
            description=msg,
            color=0x3498DB,
        )
        embed.add_field(
            name="🛡️ How to Join the Standby Queue",
            value=(
                "• Use `/tournament-sub-register` to enter the standby substitute queue.\n"
                "• Use `/tournament-sub-unregister` to leave the queue.\n"
                "• Substitutes are called up in order to replace no-show players on tournament day!"
            ),
            inline=False,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-close-subs",
        description="[Admin] Disable substitute signups.",
    )
    @is_tournament_admin()
    async def close_subs(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        msg = self.service.close_subs(guild_id=guild_id)
        embed = discord.Embed(
            title="🔴 Substitute Signups Closed",
            description=msg,
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-open-checkin",
        description="[Admin] Open tournament day check-in for participants and standby substitutes.",
    )
    @app_commands.describe(
        channel="Optional channel to broadcast check-in into (defaults to current or configured checkin channel)"
    )
    @is_tournament_admin()
    async def open_checkin(
        self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None
    ):
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        msg = self.service.open_checkin(checkin_channel_id=channel.id if channel else None, guild_id=guild_id)
        embed = discord.Embed(
            title="📢 Tournament Check-In Opened",
            description=msg,
            color=0x2ECC71,
        )
        embed.add_field(
            name="⏰ Required Action for Players & Substitutes",
            value=(
                "• Main bracket players: use `/tournament-checkin` to confirm your attendance.\n"
                "• Standby substitutes: use `/tournament-sub-checkin` to confirm you are online and ready for call-ups.\n"
                "• Unconfirmed main players may be replaced by verified substitutes!"
            ),
            inline=False,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")

        target_dest = channel or (
            interaction.guild.get_channel(state.checkin_channel_id)
            if (interaction.guild and state.checkin_channel_id)
            else None
        )
        await self._send_or_dispatch(
            interaction=interaction,
            channel=target_dest,
            embed=embed,
            confirm_message="📢 Check-in window opened in",
        )

    @app_commands.command(
        name="tournament-close-checkin",
        description="[Admin] Close tournament day check-in.",
    )
    @is_tournament_admin()
    async def close_checkin(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        msg = self.service.close_checkin(guild_id=guild_id)
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
        guild_id = interaction.guild_id or 0
        success, msg = self.service.kick_user(user.id, reason or "", guild_id=guild_id)
        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        await self._remove_participant_role(interaction.guild, user)

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
        guild_id = interaction.guild_id or 0
        success, msg, _ = self.service.force_register(
            user_id=user.id,
            user_mention=user.mention,
            ign=ign,
            weapon=weapon.value,
            region=region.value,
            as_sub=as_sub,
            guild_id=guild_id,
        )

        if success and not as_sub:
            await self._assign_participant_role(interaction.guild, user)

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
        guild_id = interaction.guild_id or 0
        sub_id = substitute.id if substitute else None
        rep_id = replace.id if replace else None

        success, message, promoted = self.service.promote_substitute(
            substitute_user_id=sub_id,
            replace_user_id=rep_id,
            guild_id=guild_id,
        )

        if not success:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        if promoted and interaction.guild:
            promoted_mem = interaction.guild.get_member(promoted.user_id)
            if promoted_mem:
                await self._assign_participant_role(interaction.guild, promoted_mem)

        if replace:
            await self._remove_participant_role(interaction.guild, replace)

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
            guild_id = interaction.guild_id or 0
            msg = self.service.set_limit(limit, guild_id=guild_id)
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
        description="[Admin] Set allowed tournament regions using dedicated tags or custom text.",
    )
    @app_commands.describe(
        region_1="Primary allowed region (or choose GLOBAL to allow all)",
        region_2="Additional allowed region tag",
        region_3="Additional allowed region tag",
        region_4="Additional allowed region tag",
        region_5="Additional allowed region tag",
        custom_regions="Optional: Type custom comma-separated regions if not using tags",
    )
    @app_commands.choices(
        region_1=REGION_FILTER_CHOICES,
        region_2=REGION_CHOICES,
        region_3=REGION_CHOICES,
        region_4=REGION_CHOICES,
        region_5=REGION_CHOICES,
    )
    @is_tournament_admin()
    async def set_regions(
        self,
        interaction: discord.Interaction,
        region_1: Optional[app_commands.Choice[str]] = None,
        region_2: Optional[app_commands.Choice[str]] = None,
        region_3: Optional[app_commands.Choice[str]] = None,
        region_4: Optional[app_commands.Choice[str]] = None,
        region_5: Optional[app_commands.Choice[str]] = None,
        custom_regions: Optional[str] = None,
    ):
        selected_regions: list[str] = []
        for r_choice in (region_1, region_2, region_3, region_4, region_5):
            if r_choice:
                selected_regions.append(r_choice.value)

        if custom_regions:
            selected_regions.extend(self.service.parse_regions(custom_regions))

        if not selected_regions:
            await interaction.response.send_message(
                "❌ Please specify at least one region tag (e.g. `region_1: NA`) or type in `custom_regions`.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild_id or 0
        msg = self.service.set_regions(selected_regions, guild_id=guild_id)
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
        guild_id = interaction.guild_id or 0
        msg = self.service.set_approved_weapons(weapons or "", guild_id=guild_id)
        embed = discord.Embed(
            title="⚔️ Tournament Weapons Updated",
            description=msg,
            color=0xF1C40F,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-set-admin-role",
        description="[Server Admin] Select which role (and any higher role) can use tournament admin commands.",
    )
    @app_commands.describe(
        role="The threshold role. Any member with this role or higher in server settings can use tournament commands."
    )
    @is_server_admin()
    async def set_admin_role_cmd(self, interaction: discord.Interaction, role: discord.Role):
        guild_id = interaction.guild_id or 0
        msg = self.service.set_admin_role(role_id=role.id, role_name=role.name, guild_id=guild_id)
        embed = discord.Embed(
            title="🛡️ Tournament Admin Role Configured",
            description=(
                f"{msg}\n\n"
                f"Members with **{role.mention}** or any role positioned higher in your server's role list "
                f"can now use all tournament admin commands."
            ),
            color=0xF1C40F,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-view-admin-role",
        description="View which role is currently authorized to use tournament admin commands.",
    )
    async def view_admin_role_cmd(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        guild_state = self.service.get_state(guild_id)
        role_id = guild_state.admin_role_id or config.admin_role_id
        role_name = guild_state.admin_role_name or config.admin_role_name

        role = interaction.guild.get_role(role_id) if role_id and interaction.guild else None
        if not role and role_name and interaction.guild:
            role = discord.utils.find(
                lambda r: r.name.lower() == role_name.lower(),
                interaction.guild.roles,
            )

        role_display = role.mention if role else (f"`{role_name}`" if role_name else "*None configured (Server Administrators only)*")

        embed = discord.Embed(
            title="🛡️ Current Tournament Admin Role",
            description=(
                f"**Configured Role:** {role_display}\n\n"
                f"Members with this role or any role positioned higher in the server role list "
                f"have full access to all tournament admin commands."
            ),
            color=0xF1C40F,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="tournament-set-role",
        description="[Admin] Set or link a Discord role assigned to main bracket tournament participants.",
    )
    @app_commands.describe(role="The Discord role to give to registered main bracket participants")
    @is_tournament_admin()
    async def set_role_cmd(self, interaction: discord.Interaction, role: discord.Role):
        guild_id = interaction.guild_id or 0
        msg = self.service.set_participant_role(guild_id=guild_id, role_id=role.id, role_name=role.name)

        # Retroactively grant to already-registered participants
        assigned_count = 0
        if interaction.guild and interaction.guild.me.guild_permissions.manage_roles and role < interaction.guild.me.top_role:
            if not role.mentionable:
                try:
                    await role.edit(mentionable=True, reason="Enable mentions for tournament announcements")
                except (discord.Forbidden, discord.HTTPException):
                    pass
            state = self.service.get_state(guild_id)
            for p in state.participants:
                mem = interaction.guild.get_member(p.user_id)
                if mem and role not in mem.roles:
                    try:
                        await mem.add_roles(role, reason="Tournament participant role configured")
                        assigned_count += 1
                    except (discord.Forbidden, discord.HTTPException):
                        pass

        embed = discord.Embed(
            title="🏷️ Tournament Participant Role Configured",
            description=(
                f"{msg}\n\n"
                f"• Registered participants will automatically receive {role.mention}.\n"
                f"• `/tournament-announce` will ping {role.mention} instead of spamming individual user tags.\n"
                + (f"• Assigned to `{assigned_count}` existing participant(s)." if assigned_count > 0 else "")
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-view-role",
        description="View the current participant role configured for this tournament.",
    )
    async def view_role_cmd(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        role = interaction.guild.get_role(state.participant_role_id) if (state.participant_role_id and interaction.guild) else None
        role_display = role.mention if role else (f"`{state.participant_role_name}`" if state.participant_role_name else "*None configured*")
        embed = discord.Embed(
            title="🏷️ Tournament Participant Role",
            description=f"**Current Role:** {role_display}\n\nThis role is automatically given to players registered in the main bracket.",
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="tournament-set-channels",
        description="[Admin] Set dedicated channels for announcements, check-in, and substitutes.",
    )
    @app_commands.describe(
        announcements="Dedicated channel for tournament announcements and brackets",
        checkin="Dedicated channel for tournament day check-ins",
        substitutes="Dedicated channel for standby substitute signups and queue",
    )
    @is_tournament_admin()
    async def set_channels_cmd(
        self,
        interaction: discord.Interaction,
        announcements: Optional[discord.TextChannel] = None,
        checkin: Optional[discord.TextChannel] = None,
        substitutes: Optional[discord.TextChannel] = None,
    ):
        guild_id = interaction.guild_id or 0
        if not announcements and not checkin and not substitutes:
            await interaction.response.send_message(
                "❌ Please specify at least one channel to configure.", ephemeral=True
            )
            return

        self.service.set_channels(
            announcement_channel_id=announcements.id if announcements else None,
            checkin_channel_id=checkin.id if checkin else None,
            subs_channel_id=substitutes.id if substitutes else None,
            guild_id=guild_id,
        )

        state = self.service.get_state(guild_id)
        desc = [
            f"• **Announcements:** {interaction.guild.get_channel(state.announcement_channel_id).mention if (interaction.guild and state.announcement_channel_id) else '*None configured*'}",
            f"• **Check-In:** {interaction.guild.get_channel(state.checkin_channel_id).mention if (interaction.guild and state.checkin_channel_id) else '*None configured*'}",
            f"• **Substitutes:** {interaction.guild.get_channel(state.subs_channel_id).mention if (interaction.guild and state.subs_channel_id) else '*None configured*'}",
            "",
            "💡 *Activity for check-ins and substitutes will automatically be routed to these channels to keep general chats uncluttered!*",
        ]
        embed = discord.Embed(
            title="📁 Dedicated Tournament Channels Configured",
            description="\n".join(desc),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-view-channels",
        description="View the dedicated channels configured for this tournament.",
    )
    async def view_channels_cmd(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        desc = [
            f"• **Announcements:** {interaction.guild.get_channel(state.announcement_channel_id).mention if (interaction.guild and state.announcement_channel_id) else '*None configured*'}",
            f"• **Check-In:** {interaction.guild.get_channel(state.checkin_channel_id).mention if (interaction.guild and state.checkin_channel_id) else '*None configured*'}",
            f"• **Substitutes:** {interaction.guild.get_channel(state.subs_channel_id).mention if (interaction.guild and state.subs_channel_id) else '*None configured*'}",
        ]
        embed = discord.Embed(
            title="📁 Dedicated Tournament Channels",
            description="\n".join(desc),
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="tournament-announce",
        description="[Admin] Ping and announce tournament information to registered players.",
    )
    @app_commands.describe(
        message="The announcement message to broadcast",
        target="Who to ping (Main Bracket, Substitutes, or Everyone)",
        channel="Optional channel to send the announcement to (defaults to current or configured announcements channel)",
    )
    @app_commands.choices(target=ANNOUNCE_TARGET_CHOICES)
    @is_tournament_admin()
    async def announce(
        self,
        interaction: discord.Interaction,
        message: str,
        target: Optional[app_commands.Choice[str]] = None,
        channel: Optional[discord.TextChannel] = None,
    ):
        target_val = target.value if target else "main"
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)

        mentions_text = ""
        role = (
            interaction.guild.get_role(state.participant_role_id)
            if (interaction.guild and state.participant_role_id)
            else None
        )

        if target_val == "main":
            if role:
                mentions_text = role.mention
            elif state.participants:
                mentions_text = " ".join(p.user_mention for p in state.participants)
            else:
                await interaction.response.send_message(
                    "❌ No participants found in the main bracket.", ephemeral=True
                )
                return
        elif target_val == "subs":
            if state.substitutes:
                mentions_text = " ".join(s.user_mention for s in state.substitutes)
            else:
                await interaction.response.send_message(
                    "❌ No substitutes found on standby.", ephemeral=True
                )
                return
        else:  # "all"
            if role:
                sub_mentions = [s.user_mention for s in state.substitutes]
                mentions_text = (
                    f"{role.mention} " + " ".join(sub_mentions)
                    if sub_mentions
                    else role.mention
                )
            else:
                all_mentions = [p.user_mention for p in state.participants] + [
                    s.user_mention for s in state.substitutes
                ]
                if not all_mentions:
                    await interaction.response.send_message(
                        "❌ No participants or substitutes found.", ephemeral=True
                    )
                    return
                mentions_text = " ".join(all_mentions)

        embed = discord.Embed(
            title=f"📢 Tournament Announcement — {state.name}",
            description=message,
            color=0xF1C40F,
        )
        embed.set_footer(text=f"Announced by {interaction.user.display_name} • {config.organization_name}")

        allowed = discord.AllowedMentions(roles=True, users=True)
        target_dest = channel or (
            interaction.guild.get_channel(state.announcement_channel_id)
            if (interaction.guild and state.announcement_channel_id)
            else None
        )
        await self._send_or_dispatch(
            interaction=interaction,
            channel=target_dest,
            embed=embed,
            content=mentions_text,
            allowed_mentions=allowed,
            confirm_message="📢 Announcement published",
        )

    @app_commands.command(
        name="tournament-export",
        description="[Admin] Export tournament roster for Challonge, Start.gg, or Excel.",
    )
    @app_commands.describe(
        format="Export file format (CSV, Challonge text, or formatted summary)",
        target="Roster scope (Main Bracket for Challonge/Start.gg bracket import, or All for spreadsheet)",
    )
    @app_commands.choices(format=EXPORT_FORMAT_CHOICES, target=EXPORT_TARGET_CHOICES)
    @is_tournament_admin()
    async def export_roster(
        self,
        interaction: discord.Interaction,
        format: Optional[app_commands.Choice[str]] = None,
        target: Optional[app_commands.Choice[str]] = None,
    ):
        fmt = format.value if format else "csv"
        target_val = target.value if target else ("main" if fmt == "challonge" else "main")
        guild_id = interaction.guild_id or 0
        filename, content = self.service.export_roster(fmt, target=target_val, guild_id=guild_id)
        file_bytes = io.BytesIO(content.encode("utf-8"))
        discord_file = discord.File(file_bytes, filename=filename)

        format_name = format.name if format else "CSV"
        state = self.service.get_state(guild_id)

        target_names = {
            "main": "Main Bracket (Bracket-ready, excludes subs)",
            "all": "Full Roster (Main Bracket + Substitutes)",
            "subs": "Standby Substitutes Only",
        }
        target_label = target_names.get(target_val, target_val.title())

        embed = discord.Embed(
            title=f"📥 Tournament Roster Export — {state.name}",
            description=(
                f"**Format:** `{format_name}`\n"
                f"**Scope:** `{target_label}`\n"
                f"**Main Participants:** `{len(state.participants)}`\n"
                f"**Substitutes:** `{len(state.substitutes)}`\n\n"
                f"💡 *Tip: For Start.gg or Challonge bracket generation, use **Main Bracket** so substitutes are not accidentally seeded into round 1 matches.*"
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, file=discord_file, ephemeral=True)

    @app_commands.command(
        name="tournament-clear",
        description="[Admin] Wipe both main roster and substitute list for a fresh event.",
    )
    @is_tournament_admin()
    async def clear_tournament(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        if interaction.guild and state.participant_role_id:
            role = interaction.guild.get_role(state.participant_role_id)
            if (
                role
                and interaction.guild.me.guild_permissions.manage_roles
                and role < interaction.guild.me.top_role
            ):
                try:
                    await role.delete(reason="Tournament cleared by admin")
                except (discord.Forbidden, discord.HTTPException):
                    pass

        msg = self.service.clear_tournament(guild_id=guild_id)
        embed = discord.Embed(
            title="🧹 Tournament Reset",
            description=msg,
            color=0xE67E22,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-setup-section",
        description="[Admin] Construct the official tournament categories, channels, and arenas.",
    )
    @app_commands.describe(
        confirm="Set to True to build the tournament section and link bot channels.",
    )
    @app_commands.default_permissions(administrator=True)
    @is_tournament_admin()
    async def setup_tournament_section(self, interaction: discord.Interaction, confirm: bool = False):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command must be used within a server.", ephemeral=True)
            return

        if not confirm:
            await interaction.response.send_message(
                "⚠️ **Safety Confirmation Required**:\n"
                "This will build the official tournament categories (Tournament Hub, Match Arenas, Operations) "
                "and link announcements, check-in, and substitute channels to the bot.\n"
                "Please rerun with `confirm: True` to proceed.",
                ephemeral=True,
            )
            return

        bot_member = interaction.guild.me
        if not bot_member or not bot_member.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ The bot is missing the **Manage Channels** permission required to create categories and channels.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        results = await build_tournament_section(interaction.guild)
        guild_id = interaction.guild_id or 0

        # Automatically link created channels to tournament service
        cmap = results.get("channel_map", {})
        if cmap:
            self.service.set_channels(
                announcement_channel_id=cmap.get("announcements"),
                checkin_channel_id=cmap.get("checkin"),
                subs_channel_id=cmap.get("subs"),
                guild_id=guild_id,
            )

        embed = discord.Embed(
            title="🏆 Tournament Section Built & Linked",
            description=(
                f"Successfully built the tournament section in **{interaction.guild.name}**!\n"
                f"Bot channel routing has been automatically configured."
            ),
            color=0x2ECC71 if not results["errors"] else 0xF39C12,
        )
        embed.add_field(
            name="📊 Categories",
            value=f"• Created: `{results['categories_created']}`\n• Existing: `{results['categories_existing']}`",
            inline=True,
        )
        embed.add_field(
            name="💬 Channels & Arenas",
            value=f"• Created: `{results['channels_created']}`\n• Existing: `{results['channels_existing']}`",
            inline=True,
        )
        if cmap:
            ann_mention = f"<#{cmap['announcements']}>" if "announcements" in cmap else "*Not set*"
            chk_mention = f"<#{cmap['checkin']}>" if "checkin" in cmap else "*Not set*"
            sub_mention = f"<#{cmap['subs']}>" if "subs" in cmap else "*Not set*"
            embed.add_field(
                name="🔗 Linked Bot Channels",
                value=(
                    f"• Announcements: {ann_mention}\n"
                    f"• Check-in: {chk_mention}\n"
                    f"• Substitutes: {sub_mention}"
                ),
                inline=False,
            )
        if results["errors"]:
            embed.add_field(
                name="⚠️ Notices / Errors",
                value="\n".join(f"• {e[:100]}" for e in results["errors"][:5]),
                inline=False,
            )
        embed.set_footer(text=f"{config.organization_name} • Tournament Section Builder")

        view = UndoTournamentSectionView(interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="tournament-remove-section",
        description="[Admin] Safely remove the tournament categories and match arenas.",
    )
    @app_commands.describe(
        confirm="Set to True to confirm removing tournament categories and channels.",
    )
    @app_commands.default_permissions(administrator=True)
    @is_tournament_admin()
    async def remove_tournament_section(self, interaction: discord.Interaction, confirm: bool = False):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command must be used within a server.", ephemeral=True)
            return

        if not confirm:
            await interaction.response.send_message(
                "⚠️ **Safety Confirmation Required**:\n"
                "This will delete all categories and channels under the Tournament Hub, Match Arenas, and Tournament Operations.\n"
                "Please rerun with `confirm: True` to proceed.",
                ephemeral=True,
            )
            return

        bot_member = interaction.guild.me
        if not bot_member or not bot_member.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ The bot is missing the **Manage Channels** permission in this server.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild_id or 0
        self.service.clear_channels(guild_id)
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
        embed.set_footer(text=f"{config.organization_name} • Tournament System")

        await interaction.followup.send(embed=embed, ephemeral=True)




async def setup(bot: commands.Bot):
    """Cog setup registration entry point."""
    service: TournamentService = getattr(bot, "tournament_service", None)
    if not service:
        from utils.storage import StorageManager
        storage = StorageManager(config.tournament_file, config.backup_dir, config.max_backups)
        service = TournamentService(storage=storage)
        bot.tournament_service = service
    await bot.add_cog(TournamentCog(bot, service))
