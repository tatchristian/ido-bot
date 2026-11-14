"""
Discord Cog implementing all UDA (United Dueling Amity) Tournament slash commands, check-in flow, help manual, and admin tools.
Fully supports isolated per-server (multi-guild) tournaments.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Union

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import config
from services.server_builder import (
    UndoTournamentSectionView,
    build_tournament_section,
    delete_tournament_section,
)
from services.tournament_service import (
    DEFAULT_WEAPONS,
    STANDARD_REGIONS,
    Participant,
    TournamentService,
    TournamentState,
)
from services.website_sync_service import (
    WebsiteSyncService,
    parse_combined_event_datetime,
    parse_duration_and_location,
    parse_event_datetime,
)
from utils.tournament_embeds import (
    build_checkin_panel_embed,
    build_checkin_receipt_embed,
    build_help_embed,
    build_registration_closed_embed,
    build_registration_panel_embed,
    build_roster_embed,
    build_staff_guide_embed,
    build_staff_panel_embed,
    build_status_embed,
    build_subs_closed_embed,
    build_subs_panel_embed,
    build_tournament_reminder_embed,
)
from utils.tournament_views import (
    HelpView,
    StaffAnnounceModal,
    StaffCreateTournamentModal,
    StaffOpenTournamentModal,
    StaffSetTimeModal,
    TournamentCheckinPanelView,
    TournamentClosedRegistrationView,
    TournamentClosedSubsView,
    TournamentEventModal,
    TournamentEventPanelView,
    TournamentRegistrationPanelView,
    TournamentStaffGuideSelect,
    TournamentStaffGuideView,
    TournamentStaffPanelView,
    TournamentSubsPanelView,
    UserRegistrationModal,
    UserSubRegistrationModal,
    check_is_event_admin,
    check_is_tournament_admin,
    is_event_admin,
    is_server_admin,
    is_tournament_admin,
    is_tournament_admin_prefix,
)

logger = logging.getLogger(__name__)

TIMEZONE_CHOICES = [
    app_commands.Choice(name="EST (UTC-5) - Eastern US", value="EST"),
    app_commands.Choice(name="EDT (UTC-4) - Eastern Daylight", value="EDT"),
    app_commands.Choice(name="CST (UTC-6) - Central US", value="CST"),
    app_commands.Choice(name="CDT (UTC-5) - Central Daylight", value="CDT"),
    app_commands.Choice(name="PST (UTC-8) - Pacific US", value="PST"),
    app_commands.Choice(name="PDT (UTC-7) - Pacific Daylight", value="PDT"),
    app_commands.Choice(name="UTC / GMT (UTC+0) - Universal", value="UTC"),
    app_commands.Choice(name="CET (UTC+1) - Central European", value="CET"),
    app_commands.Choice(name="CEST (UTC+2) - Central European Summer", value="CEST"),
    app_commands.Choice(name="BST (UTC+1) - British Summer", value="BST"),
    app_commands.Choice(name="GST (UTC+4) - Gulf Standard", value="GST"),
    app_commands.Choice(name="IST (UTC+5:30) - India Standard", value="IST"),
    app_commands.Choice(name="ICT / WIB (UTC+7) - Indochina / Western Indonesia", value="ICT"),
    app_commands.Choice(name="SGT / HKT (UTC+8) - Singapore / Hong Kong / Philippines", value="SGT"),
    app_commands.Choice(name="JST / KST (UTC+9) - Japan & Korea Standard", value="JST"),
    app_commands.Choice(name="AEST (UTC+10) - Australian Eastern", value="AEST"),
    app_commands.Choice(name="AEDT (UTC+11) - Australian Daylight", value="AEDT"),
    app_commands.Choice(name="NZST (UTC+12) - New Zealand Standard", value="NZST"),
    app_commands.Choice(name="BRT (UTC-3) - Brasilia Standard", value="BRT"),
]

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
    app_commands.Choice(name="Setup & Server Configuration", value="setup"),
    app_commands.Choice(name="Weapons, Regions & Rules", value="weapons_regions"),
    app_commands.Choice(name="Clan Showcase & Submissions", value="clans"),
    app_commands.Choice(name="Events & Website Live Sync", value="events_sync"),
]


class TournamentCog(commands.Cog):
    """Slash commands for UDA Tournament Roster and Substitute Queue management."""

    def __init__(self, bot: commands.Bot, service: TournamentService):
        self.bot = bot
        self.service = service

    async def cog_load(self) -> None:
        """Register persistent views so buttons work across bot restarts."""
        panel_view = TournamentEventPanelView()
        self.bot.add_view(panel_view)
        logger.info("Registered persistent tournament event scheduler view.")
        staff_panel_view = TournamentStaffPanelView()
        self.bot.add_view(staff_panel_view)
        logger.info("Registered persistent tournament staff operations panel view.")
        guide_view = TournamentStaffGuideView()
        self.bot.add_view(guide_view)
        logger.info("Registered persistent tournament staff guide view.")
        reg_panel_view = TournamentRegistrationPanelView()
        self.bot.add_view(reg_panel_view)
        logger.info("Registered persistent tournament registration panel view.")
        subs_panel_view = TournamentSubsPanelView()
        self.bot.add_view(subs_panel_view)
        logger.info("Registered persistent tournament subs panel view.")
        closed_reg_view = TournamentClosedRegistrationView()
        self.bot.add_view(closed_reg_view)
        logger.info("Registered persistent tournament closed registration view.")
        closed_subs_view = TournamentClosedSubsView()
        self.bot.add_view(closed_subs_view)
        logger.info("Registered persistent tournament closed subs view.")
        checkin_panel_view = TournamentCheckinPanelView()
        self.bot.add_view(checkin_panel_view)
        logger.info("Registered persistent tournament check-in panel view.")
        if not self.tournament_reminder_task.is_running():
            self.tournament_reminder_task.start()
            logger.info("Started tournament match day & 30-minute reminder background task.")

    def cog_unload(self) -> None:
        """Cancel background tasks on cog unload."""
        if self.tournament_reminder_task.is_running():
            self.tournament_reminder_task.cancel()

    # -------------------------------------------------------------------------
    # Automated Contestant Reminders (Day-Of & 30-Minute Warnings)
    # -------------------------------------------------------------------------

    @tasks.loop(minutes=1)
    async def tournament_reminder_task(self):
        """Periodic background loop that monitors upcoming tournament start times
        and dispatches Day-Of and 30-Minute DM reminders to contestants."""
        await self._check_and_send_reminders()

    @tournament_reminder_task.before_loop
    async def before_tournament_reminder_task(self):
        await self.bot.wait_until_ready()

    async def _check_and_send_reminders(self) -> None:
        """Checks each guild's active tournament and dispatches Day-Of and 30-Minute DMs to contestants."""
        for guild in self.bot.guilds:
            try:
                state = self.service.get_state(guild.id)
                if not state.participants and not state.substitutes:
                    continue

                start_ts = state.start_timestamp

                # Auto-sync with Discord scheduled events if present
                active_events = getattr(guild, "scheduled_events", [])
                matched_event = None
                if state.event_id:
                    matched_event = discord.utils.get(active_events, id=state.event_id)
                if not matched_event and state.name:
                    matched_event = discord.utils.find(
                        lambda ev: ev.name.strip().lower() == state.name.strip().lower(),
                        active_events,
                    )
                if matched_event and matched_event.start_time:
                    start_ts = int(matched_event.start_time.timestamp())
                    if state.start_timestamp != start_ts or state.event_id != matched_event.id:
                        state.start_timestamp = start_ts
                        state.start_time = matched_event.start_time.isoformat()
                        state.event_id = matched_event.id
                        self.service._persist(guild.id)

                if not start_ts:
                    continue

                now_utc = datetime.now(timezone.utc)
                event_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
                diff_seconds = (event_dt - now_utc).total_seconds()

                # If event already ended more than 2 hours ago, skip
                if diff_seconds < -7200:
                    continue

                # 1. 30-Minute Warning Reminder (0 to 30 minutes before matches start)
                if 0 <= diff_seconds <= 1800:
                    await self._dispatch_reminder_to_guild(
                        guild=guild,
                        state=state,
                        start_ts=start_ts,
                        reminder_type="30_min",
                    )

                # 2. Day-Of Match Reminder (on the calendar day of the tournament, > 30 minutes out)
                elif 1800 < diff_seconds <= 86400:
                    is_same_day = (
                        event_dt.date() == now_utc.date()
                        or event_dt.astimezone().date() == now_utc.astimezone().date()
                    )
                    if is_same_day:
                        await self._dispatch_reminder_to_guild(
                            guild=guild,
                            state=state,
                            start_ts=start_ts,
                            reminder_type="day_of",
                        )

            except Exception as exc:
                logger.error("Error in tournament reminder loop for guild %s: %s", guild.id, exc, exc_info=True)

    async def _dispatch_reminder_to_guild(
        self,
        guild: discord.Guild,
        state: TournamentState,
        start_ts: int,
        reminder_type: str,
    ) -> None:
        already_sent = (
            state.thirty_min_dm_sent if reminder_type == "30_min" else state.day_of_dm_sent
        )

        # Main bracket participants
        for p in list(state.participants):
            if p.user_id in already_sent:
                continue
            embed = build_tournament_reminder_embed(
                participant=p,
                state=state,
                reminder_type=reminder_type,
                start_timestamp=start_ts,
                is_sub=False,
            )
            await self._send_single_dm(guild, p.user_id, embed)
            self.service.mark_dm_sent(p.user_id, reminder_type, guild.id)

        # Standby substitutes
        for s in list(state.substitutes):
            if s.user_id in already_sent:
                continue
            embed = build_tournament_reminder_embed(
                participant=s,
                state=state,
                reminder_type=reminder_type,
                start_timestamp=start_ts,
                is_sub=True,
            )
            await self._send_single_dm(guild, s.user_id, embed)
            self.service.mark_dm_sent(s.user_id, reminder_type, guild.id)

    async def _send_single_dm(
        self, guild: discord.Guild, user_id: int, embed: discord.Embed
    ) -> bool:
        member = guild.get_member(user_id)
        if not member:
            try:
                member = await self.bot.fetch_user(user_id)
            except Exception:
                member = None
        if not member:
            return False

        try:
            await member.send(embed=embed)
            return True
        except discord.Forbidden:
            logger.info("Could not send tournament reminder DM to %s (DMs closed or blocked)", user_id)
            return False
        except Exception as exc:
            logger.warning("Failed to DM contestant %s: %s", user_id, exc)
            return False

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

    async def _update_channel_permission(
        self,
        guild: Optional[discord.Guild],
        channel_id: Optional[int],
        can_send: bool,
        reason: str = "",
    ) -> bool:
        """
        Dynamically grants or restricts @everyone's ability to send messages in a channel.
        Keeps viewing active (view_channel=True).
        """
        if not guild or not channel_id:
            return False
        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return False
        if not guild.me.guild_permissions.manage_channels:
            return False
        try:
            state = self.service.get_state(guild.id)
            is_regional = bool(state.allowed_regions and "GLOBAL" not in [r.upper() for r in state.allowed_regions])
            if is_regional:
                await channel.set_permissions(
                    guild.default_role,
                    send_messages=can_send,
                    reason=reason,
                )
            else:
                await channel.set_permissions(
                    guild.default_role,
                    send_messages=can_send,
                    view_channel=True,
                    reason=reason,
                )
            return True
        except Exception as e:
            logger.warning("Failed to update permissions for channel %s: %s", channel_id, e)
            return False

    async def _sync_category_region_permissions(
        self,
        guild: Optional[discord.Guild],
        regions: Optional[list[str]] = None,
        category: Optional[discord.CategoryChannel] = None,
        reason: str = "Tournament Region View Restriction",
    ) -> tuple[bool, str]:
        """
        Restricts viewing permissions of the tournament category to only members holding
        the corresponding Region roles (e.g. North America, Europe, Asia, South America, Oceania, Africa).
        If regions is ['GLOBAL'] or empty, resets @everyone to view_channel=True.
        """
        if not guild:
            return False, "Guild is unavailable."
        if not guild.me.guild_permissions.manage_channels or not guild.me.guild_permissions.manage_roles:
            return False, "Bot is missing Manage Channels or Manage Roles permissions."

        state = self.service.get_state(guild.id)
        active_regions = [r.strip().upper() for r in (regions or state.allowed_regions or ["GLOBAL"])]

        # Determine target category from registration / checkin channel or passed category
        target_category = category
        if not target_category:
            for ch_id in (state.registration_channel_id, state.checkin_channel_id, state.subs_channel_id):
                if ch_id:
                    ch = guild.get_channel(ch_id)
                    if ch and getattr(ch, "category", None):
                        target_category = ch.category
                        break

        if not target_category:
            for cat in guild.categories:
                cat_clean = cat.name.lower()
                if any(kw in cat_clean for kw in ("tournament", "tourney", "event", "uda", "championship", "dueling")):
                    target_category = cat
                    break

        if not target_category:
            return False, "No tournament category found to apply region visibility."

        # Region name normalization mapping (acronym to full name and variants)
        region_map = {
            "NA": ["north america", "na"],
            "EU": ["europe", "eu"],
            "ASIA": ["asia", "as"],
            "SA": ["south america", "sa", "latin america", "latam"],
            "OCE": ["oceania", "oce", "australia"],
            "AFRICA": ["africa", "afr"],
        }

        is_global = "GLOBAL" in active_regions or not active_regions

        try:
            if is_global:
                await target_category.set_permissions(
                    guild.default_role,
                    view_channel=True,
                    reason=f"{reason} (Global Tournament - Open to All)",
                )
                return True, f"Category **{target_category.name}** view opened to all regions (@everyone)."

            # Restrict @everyone: cannot view
            await target_category.set_permissions(
                guild.default_role,
                view_channel=False,
                reason=f"{reason} (Restricted to: {', '.join(active_regions)})",
            )

            # Ensure bot has explicit view and manage access
            if guild.me:
                await target_category.set_permissions(
                    guild.me,
                    view_channel=True,
                    manage_channels=True,
                    reason=f"{reason} (Bot Access)",
                )

            # Ensure admin role has view access if configured
            admin_role = None
            if state.admin_role_id:
                admin_role = guild.get_role(state.admin_role_id)
            if not admin_role and (state.admin_role_name or config.admin_role_name):
                arn = (state.admin_role_name or config.admin_role_name or "").strip().lower()
                admin_role = discord.utils.find(lambda r: r.name.strip().lower() == arn, guild.roles)
            if admin_role:
                await target_category.set_permissions(
                    admin_role,
                    view_channel=True,
                    reason=f"{reason} (Admin Role Access)",
                )

            # Match and grant view_channel=True to the allowed region roles
            allowed_role_names = []
            for r_code in active_regions:
                aliases = region_map.get(r_code, [r_code.lower()])
                for role in guild.roles:
                    if role == guild.default_role or not isinstance(role.name, str):
                        continue
                    role_lower = role.name.lower().strip()
                    if any(alias == role_lower or role_lower.startswith(alias + " ") or role_lower.endswith(" " + alias) for alias in aliases):
                        await target_category.set_permissions(
                            role,
                            view_channel=True,
                            reason=f"{reason} (Allowed region: {r_code})",
                        )
                        allowed_role_names.append(role.name)
                        break

            # Deny view_channel for other standard region roles that are NOT allowed
            for r_code, aliases in region_map.items():
                if r_code not in active_regions:
                    for role in guild.roles:
                        if role == guild.default_role or not isinstance(role.name, str):
                            continue
                        role_lower = role.name.lower().strip()
                        if any(alias == role_lower or role_lower.startswith(alias + " ") or role_lower.endswith(" " + alias) for alias in aliases):
                            await target_category.set_permissions(
                                role,
                                view_channel=False,
                                reason=f"{reason} (Disallowed region: {r_code})",
                            )
                            break

            roles_str = ", ".join(f"`@{rn}`" for rn in set(allowed_role_names)) if allowed_role_names else f"roles for {', '.join(active_regions)}"
            return True, f"Category **{target_category.name}** visibility restricted to {roles_str}."
        except Exception as exc:
            logger.warning("Could not sync category region permissions: %s", exc)
            return False, f"Failed to sync category permissions: {exc}"

    async def _post_or_update_registration_panel(
        self, guild: discord.Guild, channel: discord.TextChannel
    ) -> discord.Message:
        """
        Posts or updates the live player registration panel in the specified channel.
        Stores the message ID in the tournament state.
        """
        state = self.service.get_state(guild.id)
        state.registration_channel_id = channel.id
        embed = build_registration_panel_embed(state, guild)
        view = TournamentRegistrationPanelView()

        msg = None
        if state.registration_message_id:
            try:
                existing = await channel.fetch_message(state.registration_message_id)
                await existing.edit(embed=embed, view=view)
                msg = existing
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                msg = None

        if not msg:
            msg = await channel.send(embed=embed, view=view)
            state.registration_message_id = msg.id

        self.service._persist(guild.id)
        return msg

    async def _update_registration_panel(self, guild: Optional[discord.Guild]) -> None:
        """Dynamically edits the live player registration panel in the designated channel."""
        if not guild:
            return
        state = self.service.get_state(guild.id)
        if not state.registration_channel_id or not state.registration_message_id:
            return
        channel = guild.get_channel(state.registration_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return
        try:
            msg = await channel.fetch_message(state.registration_message_id)
            if state.main_open:
                embed = build_registration_panel_embed(state, guild)
                view = TournamentRegistrationPanelView()
            else:
                embed = build_registration_closed_embed(state, guild)
                view = TournamentClosedRegistrationView(guild=guild, state=state)
            await msg.edit(embed=embed, view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            logger.debug("Could not live-update registration panel: %s", exc)

    async def _close_registration_panel(self, guild: Optional[discord.Guild]) -> None:
        """Edits the active registration panel into the closed notice with links to subs."""
        if not guild:
            return
        state = self.service.get_state(guild.id)
        if not state.registration_channel_id or not state.registration_message_id:
            return
        channel = guild.get_channel(state.registration_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return
        try:
            msg = await channel.fetch_message(state.registration_message_id)
            embed = build_registration_closed_embed(state, guild)
            view = TournamentClosedRegistrationView(guild=guild, state=state)
            await msg.edit(embed=embed, view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            logger.debug("Could not edit registration panel to closed: %s", exc)

    async def _post_or_update_subs_panel(
        self, guild: discord.Guild, channel: discord.TextChannel
    ) -> discord.Message:
        """
        Posts or updates the live standby substitute queue panel in the specified channel.
        Stores the message ID in the tournament state.
        """
        state = self.service.get_state(guild.id)
        state.subs_channel_id = channel.id
        embed = build_subs_panel_embed(state, guild)
        view = TournamentSubsPanelView()

        msg = None
        if state.subs_message_id:
            try:
                existing = await channel.fetch_message(state.subs_message_id)
                await existing.edit(embed=embed, view=view)
                msg = existing
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                msg = None

        if not msg:
            msg = await channel.send(embed=embed, view=view)
            state.subs_message_id = msg.id

        self.service._persist(guild.id)
        return msg

    async def _update_subs_panel(self, guild: Optional[discord.Guild]) -> None:
        """Dynamically edits the live standby substitute queue panel in the designated channel."""
        if not guild:
            return
        state = self.service.get_state(guild.id)
        if not state.subs_channel_id or not state.subs_message_id:
            return
        channel = guild.get_channel(state.subs_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return
        try:
            msg = await channel.fetch_message(state.subs_message_id)
            if state.subs_open:
                embed = build_subs_panel_embed(state, guild)
                view = TournamentSubsPanelView()
            else:
                embed = build_subs_closed_embed(state, guild)
                view = TournamentClosedSubsView()
            await msg.edit(embed=embed, view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            logger.debug("Could not live-update substitute panel: %s", exc)

    async def _close_subs_panel(self, guild: Optional[discord.Guild]) -> None:
        """Edits the active standby substitute panel into the closed notice."""
        if not guild:
            return
        state = self.service.get_state(guild.id)
        if not state.subs_channel_id or not state.subs_message_id:
            return
        channel = guild.get_channel(state.subs_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return
        try:
            msg = await channel.fetch_message(state.subs_message_id)
            embed = build_subs_closed_embed(state, guild)
            view = TournamentClosedSubsView()
            await msg.edit(embed=embed, view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            logger.debug("Could not edit substitute panel to closed: %s", exc)

    async def _post_or_update_checkin_panel(
        self, guild: discord.Guild, channel: discord.TextChannel
    ) -> discord.Message:
        """
        Posts or updates the live Tournament Check-In Hub in the specified channel.
        Stores the message ID in the tournament state.
        """
        state = self.service.get_state(guild.id)
        state.checkin_channel_id = channel.id
        embed = build_checkin_panel_embed(state, guild)
        view = TournamentCheckinPanelView()

        msg = None
        if state.checkin_message_id:
            try:
                existing = await channel.fetch_message(state.checkin_message_id)
                await existing.edit(embed=embed, view=view)
                msg = existing
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                msg = None

        if not msg:
            msg = await channel.send(embed=embed, view=view)
            state.checkin_message_id = msg.id

        self.service._persist(guild.id)
        return msg

    async def _update_checkin_panel(self, guild: Optional[discord.Guild]) -> None:
        """Dynamically edits the live tournament check-in panel in the designated channel."""
        if not guild:
            return
        state = self.service.get_state(guild.id)
        if not state.checkin_channel_id or not state.checkin_message_id:
            return
        channel = guild.get_channel(state.checkin_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return
        try:
            msg = await channel.fetch_message(state.checkin_message_id)
            embed = build_checkin_panel_embed(state, guild)
            view = TournamentCheckinPanelView()
            await msg.edit(embed=embed, view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            logger.debug("Could not live-update check-in panel: %s", exc)

    async def _update_all_live_panels(self, guild: Optional[discord.Guild]) -> None:
        """Helper to refresh Registration, Substitute, and Check-In panels concurrently."""
        if not guild:
            return
        await asyncio.gather(
            self._update_registration_panel(guild),
            self._update_subs_panel(guild),
            self._update_checkin_panel(guild),
            return_exceptions=True,
        )

    async def _dispatch_checkin_log(
        self,
        guild: Optional[discord.Guild],
        participant: Any,
        action: str,
        role_type: str = "main",
        staff_member: Optional[discord.Member] = None,
    ) -> None:
        """Dispatches an audit receipt embed to the configured check-in log channel."""
        if not guild or not participant:
            return
        state = self.service.get_state(guild.id)
        log_ch_id = state.checkin_log_channel_id or state.checkin_channel_id
        if not log_ch_id:
            return
        channel = guild.get_channel(log_ch_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return
        perms = channel.permissions_for(guild.me)
        if not perms.send_messages or not perms.embed_links:
            return
        try:
            embed = build_checkin_receipt_embed(
                state=state,
                participant=participant,
                action=action,
                role_type=role_type,
                staff_member=staff_member,
            )
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.debug("Could not send check-in receipt to log channel: %s", exc)

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
        name="tournament-help",
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

    @app_commands.command(
        name="help-tournament",
        description="Interactive guide and command manual for the UDA Tournament Bot (alias for /tournament-help).",
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
        description="Interactive guide and command manual for the UDA Tournament Bot (alias for /tournament-help).",
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
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
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
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-sub-register",
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
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
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

        await self._update_registration_panel(interaction.guild)
        await self._update_subs_panel(interaction.guild)

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
        res = self.service.checkin_user(interaction.user.id, guild_id=guild_id)
        success, msg, part, role_type = res.success, res.message, res.participant, res.role_type
        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
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
        await interaction.response.send_message(f"{msg}{log_note}", ephemeral=True)

    @app_commands.command(
        name="tournament-sub-checkin",
        description="Confirm your standby availability as a substitute on tournament day.",
    )
    async def sub_checkin(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        res = self.service.checkin_user(interaction.user.id, guild_id=guild_id)
        success, msg, part, role_type = res.success, res.message, res.participant, res.role_type
        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
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
        await interaction.response.send_message(f"{msg}{log_note}", ephemeral=True)

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
        date="Optional: Match day date (e.g. 2026-11-15 or This Weekend) for contestant reminders",
        time="Optional: Match start time (e.g. 18:00 or 6:00 PM)",
        timezone="Timezone for match day (defaults to EST)",
        registration_channel="Optional: Dedicated text channel to route registrations and announcements to",
    )
    @app_commands.choices(
        region_1=REGION_FILTER_CHOICES,
        region_2=REGION_CHOICES,
        region_3=REGION_CHOICES,
        timezone=TIMEZONE_CHOICES,
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
        date: Optional[str] = None,
        time: Optional[str] = None,
        timezone: Optional[app_commands.Choice[str]] = None,
        registration_channel: Optional[discord.TextChannel] = None,
    ):
        guild_id = interaction.guild_id or 0
        if registration_channel:
            self.service.set_channels(registration_channel_id=registration_channel.id, guild_id=guild_id)
        selected_regions: list[str] | None = None
        tag_list = [r.value for r in (region_1, region_2, region_3) if r]
        if tag_list or custom_regions:
            selected_regions = list(tag_list)
            if custom_regions:
                selected_regions.extend(self.service.parse_regions(custom_regions))

        parsed_start_time = None
        parsed_start_ts = None
        if date and time:
            tz_str = timezone.value if timezone else "EST"
            valid, start_dt, err = parse_event_datetime(date, time, tz_str)
            if not valid or not start_dt:
                await interaction.response.send_message(f"❌ {err}", ephemeral=True)
                return
            parsed_start_time = start_dt.isoformat()
            parsed_start_ts = int(start_dt.timestamp())
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
                            reason=f"Auto-created UDA tournament participant role for {tourney_name}",
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
                start_time=parsed_start_time,
                start_timestamp=parsed_start_ts,
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

            # Dynamically unlock registration channel (and subs channel if open_subs is True)
            curr_state = self.service.get_state(guild_id)
            if curr_state.registration_channel_id and interaction.guild:
                target_reg = interaction.guild.get_channel(curr_state.registration_channel_id)
                if isinstance(target_reg, discord.TextChannel):
                    await self._update_channel_permission(
                        interaction.guild,
                        curr_state.registration_channel_id,
                        can_send=True,
                        reason=f"Registrations opened for {tourney_name}",
                    )
                    try:
                        await self._post_or_update_registration_panel(interaction.guild, target_reg)
                    except Exception as exc:
                        logger.warning("Could not auto-post registration panel: %s", exc)

            if open_subs and curr_state.subs_channel_id and interaction.guild:
                target_subs = interaction.guild.get_channel(curr_state.subs_channel_id)
                if isinstance(target_subs, discord.TextChannel):
                    await self._update_channel_permission(
                        interaction.guild,
                        curr_state.subs_channel_id,
                        can_send=True,
                        reason=f"Substitutes opened for {tourney_name}",
                    )
                    try:
                        await self._post_or_update_subs_panel(interaction.guild, target_subs)
                    except Exception as exc:
                        logger.warning("Could not auto-post subs panel: %s", exc)

            if interaction.guild:
                try:
                    await self._sync_category_region_permissions(
                        interaction.guild,
                        regions=selected_regions or curr_state.allowed_regions,
                        reason=f"Tournament opened for {tourney_name}",
                    )
                except Exception as cat_exc:
                    logger.warning("Could not auto-sync category region permissions: %s", cat_exc)

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

        # Dynamically lock registration channel and edit panel
        curr_state = self.service.get_state(guild_id)
        if curr_state.registration_channel_id and interaction.guild:
            await self._update_channel_permission(
                interaction.guild,
                curr_state.registration_channel_id,
                can_send=False,
                reason="Main bracket registrations closed",
            )
            await self._close_registration_panel(interaction.guild)

        embed = discord.Embed(
            title="🔒 Main Bracket Closed",
            description=msg,
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="tournament-open-subs",
        description="[Admin] Enable the substitute sign-up section for standby players.",
    )
    @is_tournament_admin()
    async def open_subs(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        msg = self.service.open_subs(guild_id=guild_id)

        # Dynamically unlock substitutes channel and post panel
        curr_state = self.service.get_state(guild_id)
        if curr_state.subs_channel_id and interaction.guild:
            await self._update_channel_permission(
                interaction.guild,
                curr_state.subs_channel_id,
                can_send=True,
                reason="Substitute signups opened",
            )
            target_subs = interaction.guild.get_channel(curr_state.subs_channel_id)
            if isinstance(target_subs, discord.TextChannel):
                try:
                    await self._post_or_update_subs_panel(interaction.guild, target_subs)
                except Exception as exc:
                    logger.warning("Could not auto-post subs panel: %s", exc)

        # Sync the live player registration panel status
        if interaction.guild:
            try:
                await self._update_registration_panel(interaction.guild)
            except Exception as sync_exc:
                logger.debug("Could not auto-sync registration panel on open_subs: %s", sync_exc)

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
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="tournament-close-subs",
        description="[Admin] Disable substitute signups.",
    )
    @is_tournament_admin()
    async def close_subs(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        msg = self.service.close_subs(guild_id=guild_id)

        # Dynamically lock substitutes channel and edit panel
        curr_state = self.service.get_state(guild_id)
        if curr_state.subs_channel_id and interaction.guild:
            await self._update_channel_permission(
                interaction.guild,
                curr_state.subs_channel_id,
                can_send=False,
                reason="Substitute signups closed",
            )
            await self._close_subs_panel(interaction.guild)

        # Sync the live player registration panel status
        if interaction.guild:
            try:
                await self._update_registration_panel(interaction.guild)
            except Exception as sync_exc:
                logger.debug("Could not auto-sync registration panel on close_subs: %s", sync_exc)

        embed = discord.Embed(
            title="🔴 Substitute Signups Closed",
            description=msg,
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

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

        # Dynamically unlock check-in channel
        target_checkin_id = channel.id if channel else state.checkin_channel_id
        if target_checkin_id:
            await self._update_channel_permission(
                interaction.guild,
                target_checkin_id,
                can_send=True,
                reason="Tournament check-in opened",
            )

        await self._send_or_dispatch(
            interaction=interaction,
            channel=target_dest,
            embed=embed,
            confirm_message="📢 Check-in window opened in",
        )
        await self._update_all_live_panels(interaction.guild)

    @app_commands.command(
        name="tournament-close-checkin",
        description="[Admin] Close tournament day check-in.",
    )
    @is_tournament_admin()
    async def close_checkin(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        msg = self.service.close_checkin(guild_id=guild_id)

        # Dynamically lock check-in channel
        state = self.service.get_state(guild_id)
        if state.checkin_channel_id:
            await self._update_channel_permission(
                interaction.guild,
                state.checkin_channel_id,
                can_send=False,
                reason="Tournament check-in closed",
            )

        embed = discord.Embed(
            title="🔒 Tournament Check-In Closed",
            description=msg,
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await self._update_all_live_panels(interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _resolve_user_id(self, user_str: str | None, guild_id: int) -> int | None:
        """
        Resolves a user input string to a user_id integer.
        Accepts:
          - Pure digit ID (e.g. from autocomplete value or typed raw ID)
          - Discord mention (<@123456789> or <@!123456789>)
          - Participant / Substitute IGN (case-insensitive exact or substring match)
        """
        if not user_str:
            return None
        cleaned = str(user_str).strip()
        if not cleaned:
            return None

        mention_match = re.search(r"<@!?(\d+)>", cleaned)
        if mention_match:
            return int(mention_match.group(1))

        if cleaned.isdigit():
            return int(cleaned)

        state = self.service.get_state(guild_id)
        cleaned_lower = cleaned.lower()
        all_players = state.participants + state.substitutes
        for p in all_players:
            if p.ign and p.ign.lower() == cleaned_lower:
                return p.user_id

        for p in all_players:
            if p.ign and cleaned_lower in p.ign.lower():
                return p.user_id

        return None

    async def _kick_participants_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        choices: list[app_commands.Choice[str]] = []
        current_lower = current.strip().lower()

        pool = [("Main", p) for p in state.participants] + [("Sub", p) for p in state.substitutes]
        for tag, p in pool:
            ign = p.ign or f"User {p.user_id}"
            label = f"[{tag}] {ign} ({p.region}) • {p.weapon}"[:100]
            if not current_lower or current_lower in ign.lower() or current_lower in str(p.user_id):
                choices.append(app_commands.Choice(name=label, value=str(p.user_id)))
                if len(choices) >= 25:
                    break
        return choices

    async def _substitute_candidates_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        choices: list[app_commands.Choice[str]] = []
        current_lower = current.strip().lower()

        for idx, p in enumerate(state.substitutes, start=1):
            ign = p.ign or f"User {p.user_id}"
            status = "✅ Ready" if p.checked_in else "Standby"
            label = f"[Sub #{idx}] {ign} ({p.region}) • {status}"[:100]
            if not current_lower or current_lower in ign.lower() or current_lower in str(p.user_id):
                choices.append(app_commands.Choice(name=label, value=str(p.user_id)))
                if len(choices) >= 25:
                    break
        return choices

    async def _replace_candidates_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        choices: list[app_commands.Choice[str]] = []
        current_lower = current.strip().lower()

        for p in state.participants:
            ign = p.ign or f"User {p.user_id}"
            status = "✅ Checked-in" if p.checked_in else "⏳ No-show"
            label = f"[{status}] {ign} ({p.region}) • {p.weapon}"[:100]
            if not current_lower or current_lower in ign.lower() or current_lower in str(p.user_id):
                choices.append(app_commands.Choice(name=label, value=str(p.user_id)))
                if len(choices) >= 25:
                    break
        return choices

    @app_commands.command(
        name="tournament-kick",
        description="[Admin] Remove a player from the tournament by name, mention, or ID.",
    )
    @app_commands.describe(
        user="Player to kick (search IGN from dropdown, or enter mention / ID)",
        reason="Optional reason for the removal",
    )
    @is_tournament_admin()
    async def kick_user(
        self,
        interaction: discord.Interaction,
        user: str,
        reason: Optional[str] = None,
    ):
        guild_id = interaction.guild_id or 0
        user_id = self._resolve_user_id(user, guild_id)
        if not user_id:
            await interaction.response.send_message(
                f"❌ Could not find participant `{user}` in this tournament. "
                "Please select a player from the dropdown or provide a valid mention/ID.",
                ephemeral=True,
            )
            return

        success, msg = self.service.kick_user(user_id, reason or "", guild_id=guild_id)
        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        if interaction.guild:
            target_mem = interaction.guild.get_member(user_id)
            if target_mem:
                await self._remove_participant_role(interaction.guild, target_mem)

        await self._update_registration_panel(interaction.guild)
        await self._update_subs_panel(interaction.guild)

        embed = discord.Embed(
            title="👢 Tournament Removal",
            description=msg,
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @kick_user.autocomplete("user")
    async def kick_user_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._kick_participants_autocomplete(interaction, current)

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

        if success:
            await self._update_registration_panel(interaction.guild)
            await self._update_subs_panel(interaction.guild)

        embed = discord.Embed(
            title="👑 Admin Force Registration",
            description=msg,
            color=0xF1C40F,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
        substitute: Optional[str] = None,
        replace: Optional[str] = None,
    ):
        guild_id = interaction.guild_id or 0
        sub_id = self._resolve_user_id(substitute, guild_id) if substitute else None
        rep_id = self._resolve_user_id(replace, guild_id) if replace else None

        if substitute and not sub_id:
            await interaction.response.send_message(
                f"❌ Could not resolve substitute `{substitute}`. Please select from the dropdown or enter an ID/mention.",
                ephemeral=True,
            )
            return

        if replace and not rep_id:
            await interaction.response.send_message(
                f"❌ Could not resolve main bracket player `{replace}`. Please select from the dropdown or enter an ID/mention.",
                ephemeral=True,
            )
            return

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

        if rep_id and interaction.guild:
            rep_mem = interaction.guild.get_member(rep_id)
            if rep_mem:
                await self._remove_participant_role(interaction.guild, rep_mem)

        await self._update_registration_panel(interaction.guild)
        await self._update_subs_panel(interaction.guild)

        embed = discord.Embed(
            title="🔄 Substitute Promoted",
            description=message,
            color=0x9B59B6,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @promote_sub.autocomplete("substitute")
    async def promote_sub_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._substitute_candidates_autocomplete(interaction, current)

    @promote_sub.autocomplete("replace")
    async def promote_replace_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._replace_candidates_autocomplete(interaction, current)

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
            await self._update_registration_panel(interaction.guild)
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
        await self._update_registration_panel(interaction.guild)
        await self._update_subs_panel(interaction.guild)
        if interaction.guild:
            try:
                await self._sync_category_region_permissions(
                    interaction.guild,
                    regions=selected_regions,
                    reason=f"Region filter updated to {', '.join(selected_regions)}",
                )
            except Exception as cat_exc:
                logger.warning("Could not sync category region permissions on set_regions: %s", cat_exc)
        embed = discord.Embed(
            title="🌍 Allowed Regions Updated",
            description=msg,
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
        await self._update_registration_panel(interaction.guild)
        await self._update_subs_panel(interaction.guild)
        embed = discord.Embed(
            title="⚔️ Tournament Weapons Updated",
            description=msg,
            color=0xF1C40F,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
        name="tournament-set-event-role",
        description="[Server Admin] Set which role can schedule official events and manage website sync.",
    )
    @app_commands.describe(
        role="The Discord role that grants access to event scheduling and website sync commands."
    )
    @is_server_admin()
    async def set_event_role_cmd(
        self, interaction: discord.Interaction, role: Optional[discord.Role] = None
    ):
        guild_id = interaction.guild_id or 0
        if role:
            msg = self.service.set_event_role(role_id=role.id, role_name=role.name, guild_id=guild_id)
            embed = discord.Embed(
                title="📅 Event & Website Role Configured",
                description=(
                    f"{msg}\n\n"
                    f"Members with **{role.mention}** can now access all Discord scheduled event "
                    f"and website sync commands (`/tournament-schedule-event`, `/tournament-cancel-event`, "
                    f"`/tournament-complete-event`, `/tournament-remove-past-result`, `/post-event-scheduler-panel`).\n\n"
                    f"🛡️ *Note: This role is strictly isolated — it does not grant bracket management or Clan Showcase staff permissions.*"
                ),
                color=0x3498DB,
            )
        else:
            msg = self.service.set_event_role(role_id=None, role_name=None, guild_id=guild_id)
            embed = discord.Embed(
                title="📅 Event & Website Role Cleared",
                description=(
                    f"{msg}\n\n"
                    f"Only server staff with Administrator, Manage Events, or Manage Server permissions can now access event and website sync controls."
                ),
                color=0x3498DB,
            )
        embed.set_footer(text=f"{config.organization_name} • Event Operations")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="set-event-role",
        description="[Server Admin] Set which role can schedule official events and manage website sync.",
    )
    @app_commands.describe(
        role="The Discord role that grants access to event scheduling and website sync commands."
    )
    @is_server_admin()
    async def set_event_role_alias_cmd(
        self, interaction: discord.Interaction, role: Optional[discord.Role] = None
    ):
        await self.set_event_role_cmd(interaction, role)

    @app_commands.command(
        name="tournament-view-event-role",
        description="View which role is currently authorized for event scheduling and website sync.",
    )
    async def view_event_role_cmd(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        guild_state = self.service.get_state(guild_id)
        role_id = getattr(guild_state, "event_role_id", None) or getattr(config, "event_role_id", None)
        role_name = getattr(guild_state, "event_role_name", None) or getattr(config, "event_role_name", None)

        role = interaction.guild.get_role(role_id) if role_id and interaction.guild else None
        if not role and role_name and interaction.guild:
            role = discord.utils.find(
                lambda r: r.name.lower() == role_name.lower(),
                interaction.guild.roles,
            )

        role_display = role.mention if role else (f"`{role_name}`" if role_name else "*None configured (Server Administrators & Manage Events only)*")

        embed = discord.Embed(
            title="📅 Current Event & Website Role",
            description=(
                f"**Configured Role:** {role_display}\n\n"
                f"Members with this role have access to event scheduling, cancellations, completions, "
                f"and website sync commands.\n\n"
                f"🛡️ *This role does not grant access to tournament bracket operations or clan showcase controls.*"
            ),
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • Event Operations")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="view-event-role",
        description="View which role is currently authorized for event scheduling and website sync.",
    )
    async def view_event_role_alias_cmd(self, interaction: discord.Interaction):
        await self.view_event_role_cmd(interaction)

    @commands.command(name="set_event_role", aliases=["set_event_website_role", "tournament_set_event_role"])
    @commands.has_permissions(administrator=True)
    async def set_event_role_prefix(
        self, ctx: commands.Context, role: Optional[discord.Role] = None
    ):
        """Prefix command fallback (!set_event_role)."""
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a server.")
            return

        guild_id = ctx.guild.id
        if role:
            msg = self.service.set_event_role(role_id=role.id, role_name=role.name, guild_id=guild_id)
            await ctx.send(f"✅ {msg}\nMembers with **@{role.name}** can now access event and website sync commands.")
        else:
            msg = self.service.set_event_role(role_id=None, role_name=None, guild_id=guild_id)
            await ctx.send(f"✅ {msg}")

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
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
        description="[Admin] Set dedicated channels for announcements, registrations, check-in, and substitutes.",
    )
    @app_commands.describe(
        announcements="Dedicated channel for tournament announcements and brackets",
        registration="Dedicated channel for player registrations (/tournament-register)",
        checkin="Dedicated channel for tournament day check-ins",
        substitutes="Dedicated channel for standby substitute signups and queue",
    )
    @is_tournament_admin()
    async def set_channels_cmd(
        self,
        interaction: discord.Interaction,
        announcements: Optional[discord.TextChannel] = None,
        registration: Optional[discord.TextChannel] = None,
        checkin: Optional[discord.TextChannel] = None,
        substitutes: Optional[discord.TextChannel] = None,
    ):
        guild_id = interaction.guild_id or 0
        if not announcements and not registration and not checkin and not substitutes:
            await interaction.response.send_message(
                "❌ Please specify at least one channel to configure.", ephemeral=True
            )
            return

        self.service.set_channels(
            announcement_channel_id=announcements.id if announcements else None,
            registration_channel_id=registration.id if registration else None,
            checkin_channel_id=checkin.id if checkin else None,
            subs_channel_id=substitutes.id if substitutes else None,
            guild_id=guild_id,
        )

        state = self.service.get_state(guild_id)
        desc = [
            f"• **Announcements:** {interaction.guild.get_channel(state.announcement_channel_id).mention if (interaction.guild and state.announcement_channel_id) else '*None configured*'}",
            f"• **Registration:** {interaction.guild.get_channel(state.registration_channel_id).mention if (interaction.guild and state.registration_channel_id) else '*None configured*'}",
            f"• **Check-In:** {interaction.guild.get_channel(state.checkin_channel_id).mention if (interaction.guild and state.checkin_channel_id) else '*None configured*'}",
            f"• **Substitutes:** {interaction.guild.get_channel(state.subs_channel_id).mention if (interaction.guild and state.subs_channel_id) else '*None configured*'}",
            "",
            "💡 *Activity for registrations, check-ins, and substitutes will automatically be routed to these channels to keep general chats uncluttered!*",
        ]
        embed = discord.Embed(
            title="📁 Dedicated Tournament Channels Configured",
            description="\n".join(desc),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="tournament-view-channels",
        description="View the dedicated channels configured for this tournament.",
    )
    async def view_channels_cmd(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        desc = [
            f"• **Announcements:** {interaction.guild.get_channel(state.announcement_channel_id).mention if (interaction.guild and state.announcement_channel_id) else '*None configured*'}",
            f"• **Registration:** {interaction.guild.get_channel(state.registration_channel_id).mention if (interaction.guild and state.registration_channel_id) else '*None configured*'}",
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
        name="tournament-set-channel",
        description="[Admin] Set or update a specific dedicated channel (registration, announcements, check-in, subs).",
    )
    @app_commands.describe(
        target="The tournament channel function to configure",
        channel="The text channel to route activity to",
    )
    @app_commands.choices(
        target=[
            app_commands.Choice(name="Registration Channel (#tournament-registration)", value="registration"),
            app_commands.Choice(name="Announcements Channel (#tournament-announcements)", value="announcements"),
            app_commands.Choice(name="Check-In Channel (#tournament-check-in)", value="checkin"),
            app_commands.Choice(name="Check-In Log Channel (#checkin-logs)", value="checkin_logs"),
            app_commands.Choice(name="Substitutes Bench Channel (#substitutes-bench)", value="substitutes"),
        ]
    )
    @is_tournament_admin()
    async def set_single_channel_cmd(
        self,
        interaction: discord.Interaction,
        target: app_commands.Choice[str],
        channel: discord.TextChannel,
    ):
        guild_id = interaction.guild_id or 0
        kw = {}
        if target.value == "registration":
            kw["registration_channel_id"] = channel.id
        elif target.value == "announcements":
            kw["announcement_channel_id"] = channel.id
        elif target.value == "checkin":
            kw["checkin_channel_id"] = channel.id
        elif target.value == "checkin_logs":
            kw["checkin_log_channel_id"] = channel.id
        elif target.value == "substitutes":
            kw["subs_channel_id"] = channel.id

        self.service.set_channels(**kw, guild_id=guild_id)
        if target.value in ("registration", "checkin", "substitutes") and getattr(channel, "category", None) and interaction.guild:
            await self._sync_category_region_permissions(interaction.guild, category=channel.category)
        embed = discord.Embed(
            title="📁 Dedicated Tournament Channel Updated",
            description=f"✅ **{target.name}** successfully linked to {channel.mention}.\n\n"
                        f"Automated bot announcements, broadcasts, and registrations will now route to this channel.",
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament Configuration")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="set_channel", aliases=["tournament_set_channel"])
    @commands.guild_only()
    async def set_single_channel_prefix(
        self,
        ctx: commands.Context,
        target: str,
        channel: discord.TextChannel,
    ):
        """Prefix command to configure a single tournament channel."""
        if not check_is_tournament_admin(ctx.author, ctx.guild, self.bot):
            await ctx.send("❌ You do not have permission to use this command.")
            return

        tgt = target.lower().strip()
        guild_id = ctx.guild.id
        kw = {}
        if tgt in ("reg", "registration", "signup", "register"):
            kw["registration_channel_id"] = channel.id
            tname = "Registration Channel"
        elif tgt in ("ann", "announce", "announcements", "announcement"):
            kw["announcement_channel_id"] = channel.id
            tname = "Announcements Channel"
        elif tgt in ("checkin", "check-in", "check_in"):
            kw["checkin_channel_id"] = channel.id
            tname = "Check-In Channel"
        elif tgt in ("checkin_logs", "checkin-logs", "checkinlog", "checkinlogs", "logs"):
            kw["checkin_log_channel_id"] = channel.id
            tname = "Check-In Log Channel"
        elif tgt in ("sub", "subs", "substitutes", "substitute"):
            kw["subs_channel_id"] = channel.id
            tname = "Substitutes Bench Channel"
        else:
            await ctx.send("❌ Invalid target. Choose from: `registration`, `announcements`, `checkin`, `substitutes`.")
            return

        self.service.set_channels(**kw, guild_id=guild_id)
        if target.value in ("registration", "checkin", "substitutes") and getattr(channel, "category", None) and interaction.guild:
            await self._sync_category_region_permissions(interaction.guild, category=channel.category)
        await ctx.send(f"✅ **{tname}** updated to {channel.mention}.")

    @app_commands.command(
        name="tournament-set-time",
        description="[Admin] Set or update the official match day date, time, and timezone for contestant reminders.",
    )
    @app_commands.describe(
        date="Date of tournament (e.g. 2026-11-15 or 11/15/2026)",
        time="Start time (e.g. 18:00 or 6:00 PM)",
        timezone="Timezone for the start time (defaults to EST)",
    )
    @app_commands.choices(timezone=TIMEZONE_CHOICES)
    @is_tournament_admin()
    async def set_tournament_time_cmd(
        self,
        interaction: discord.Interaction,
        date: str,
        time: str,
        timezone: Optional[app_commands.Choice[str]] = None,
    ):
        tz_str = timezone.value if timezone else "EST"
        valid, start_dt, err = parse_event_datetime(date, time, tz_str)
        if not valid or not start_dt:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        ts = int(start_dt.timestamp())
        msg = self.service.set_tournament_time(
            start_time=start_dt.isoformat(),
            start_timestamp=ts,
            guild_id=guild_id,
        )

        embed = discord.Embed(
            title="⏰ Tournament Match Day Schedule Configured",
            description=(
                f"{msg}\n\n"
                f"**Configured Start Time:** <t:{ts}:F> (<t:{ts}:R>)\n"
                f"**Timezone:** `{tz_str}`\n\n"
                f"📬 **Automated Contestant Direct Messages:**\n"
                f"• **Match Day Morning / Day-Of:** All registered contestants receive a personalized match-day DM with their registered region, tournament rules, and dynamic countdown.\n"
                f"• **30 Minutes Prior:** All contestants receive an urgent 30-minute alert to join tournament channels and confirm check-in.\n"
                f"• *Each contestant's notification highlights their specific selected region!*"
            ),
            color=0x10B981,
        )
        embed.set_footer(text=f"{config.organization_name} • Match Day Reminders")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tournament-view-time",
        description="View scheduled tournament start time, dynamic timestamps, and contestant reminder status.",
    )
    async def view_tournament_time_cmd(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)

        if not state.start_timestamp:
            await interaction.response.send_message(
                "ℹ️ No match day start time is currently set for this tournament.\n"
                "Use `/tournament-set-time` or `/tournament-schedule-event` to configure one.",
                ephemeral=True,
            )
            return

        ts = state.start_timestamp
        day_of_count = len(state.day_of_dm_sent)
        thirty_min_count = len(state.thirty_min_dm_sent)
        total_contestants = len(state.participants) + len(state.substitutes)

        embed = discord.Embed(
            title=f"⏰ Match Day Schedule & Reminders — {state.name}",
            description=(
                f"**Starts At:** <t:{ts}:F>\n"
                f"**Countdown:** <t:{ts}:R>\n"
                f"**Allowed Regions:** `{', '.join(state.allowed_regions)}`\n\n"
                f"📊 **Automated Contestant DM Tracker:**\n"
                f"• **Day-Of Match Reminders Sent:** `{day_of_count} / {total_contestants}`\n"
                f"• **30-Minute Warnings Sent:** `{thirty_min_count} / {total_contestants}`\n\n"
                f"💡 *Registered contestants are personally DM'd on the day of the tournament and 30 minutes before matches begin.*"
            ),
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • Match Day Reminders")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="tournament-test-reminder",
        description="[Admin] Send yourself a preview DM of the Day-Of or 30-Minute reminder message.",
    )
    @app_commands.describe(
        reminder_type="Choose which reminder notification to preview in your DMs"
    )
    @app_commands.choices(
        reminder_type=[
            app_commands.Choice(name="📅 Day-Of Match Reminder", value="day_of"),
            app_commands.Choice(name="🚨 30-Minute Warning Reminder", value="30_min"),
        ]
    )
    @is_tournament_admin()
    async def test_tournament_reminder_cmd(
        self,
        interaction: discord.Interaction,
        reminder_type: app_commands.Choice[str],
    ):
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        start_ts = state.start_timestamp or int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp())

        # Create mock/sample participant from the user
        sample_part = Participant(
            user_id=interaction.user.id,
            user_mention=interaction.user.mention,
            ign=getattr(interaction.user, "display_name", str(interaction.user)),
            weapon=state.approved_weapons[0] if state.approved_weapons else "Katana",
            region=state.allowed_regions[0] if state.allowed_regions else "GLOBAL",
        )

        embed = build_tournament_reminder_embed(
            participant=sample_part,
            state=state,
            reminder_type=reminder_type.value,
            start_timestamp=start_ts,
            is_sub=False,
        )

        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message(
                f"✅ Sent preview `{reminder_type.name}` directly to your DMs!",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Could not deliver preview DM. Please ensure your Discord privacy settings allow Direct Messages from server members.",
                ephemeral=True,
            )

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
        name="tournament-save-roster",
        description="[Admin] Snapshot the active tournament roster & settings to a persistent preset file.",
    )
    @is_tournament_admin()
    async def save_roster_slash(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        self.service.save_roster_preset(guild_id=guild_id)
        embed = discord.Embed(
            title="💾 Tournament Roster Saved",
            description=(
                f"Successfully saved **{state.name}** roster snapshot to disk!\n"
                f"• **Main Participants:** `{len(state.participants)}`\n"
                f"• **Substitutes:** `{len(state.substitutes)}`\n"
                f"• **Max Slots:** `{state.max_slots}`\n"
                f"• **Allowed Regions:** `{', '.join(state.allowed_regions)}`\n\n"
                "💡 *This snapshot is saved to `saved_roster.json` and will survive bot redeployments.*"
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament Operations")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="tournament_save_roster")
    @is_tournament_admin_prefix()
    async def save_roster_prefix(self, ctx: commands.Context):
        """Prefix fallback: !tournament_save_roster"""
        if not ctx.guild:
            await ctx.send("❌ Command must be used in a server.")
            return
        state = self.service.get_state(ctx.guild.id)
        self.service.save_roster_preset(guild_id=ctx.guild.id)
        await ctx.send(f"💾 Saved roster snapshot for **{state.name}** ({len(state.participants)} participants).")

    @app_commands.command(
        name="tournament-restore-roster",
        description="[Admin] Restore tournament roster from saved_roster.json preset across redeployments.",
    )
    @is_tournament_admin()
    async def restore_roster_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        guild_id = interaction.guild_id or 0

        def resolver(ign: str, mention_str: str) -> tuple[int, str] | None:
            if not guild:
                return None
            clean_mention = mention_str.lstrip("@").lower()
            clean_ign = ign.lower()
            for m in guild.members:
                if (
                    m.name.lower() in (clean_mention, clean_ign)
                    or m.display_name.lower() in (clean_mention, clean_ign)
                    or clean_mention in m.name.lower()
                    or clean_ign in m.display_name.lower()
                ):
                    return m.id, m.mention
            return None

        try:
            p_count, s_count = self.service.import_roster_preset(
                guild_id=guild_id,
                file_path="saved_roster.json",
                member_resolver=resolver,
            )
        except Exception as exc:
            await interaction.followup.send(f"❌ Failed to restore roster: {exc}", ephemeral=True)
            return

        state = self.service.get_state(guild_id)

        # Update live registration panel if channel exists
        if guild:
            await self._update_registration_panel(guild)
            if state.subs_channel_id:
                await self._update_subs_panel(guild)

            # Assign participant role to registered members
            if state.participant_role_id:
                role = guild.get_role(state.participant_role_id)
                if role and role < guild.me.top_role:
                    for p in state.participants:
                        member = guild.get_member(p.user_id)
                        if member and role not in member.roles:
                            try:
                                await member.add_roles(role, reason=f"Restored to tournament {state.name}")
                            except Exception:
                                pass

        embed = discord.Embed(
            title="✅ Tournament Roster Restored",
            description=(
                f"Successfully restored **{state.name}** roster from preset!\n"
                f"• **Main Bracket:** `{p_count} / {state.max_slots}` registered\n"
                f"• **Standby Substitutes:** `{s_count}` in queue\n"
                f"• **Regions:** `{', '.join(state.allowed_regions)}`\n"
                f"• **Live Panel:** Refreshed in `#tournament-registration`"
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament Operations")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.command(name="tournament_restore_roster")
    @is_tournament_admin_prefix()
    async def restore_roster_prefix(self, ctx: commands.Context):
        """Prefix fallback: !tournament_restore_roster"""
        if not ctx.guild:
            await ctx.send("❌ Command must be used in a server.")
            return

        def resolver(ign: str, mention_str: str) -> tuple[int, str] | None:
            clean_mention = mention_str.lstrip("@").lower()
            clean_ign = ign.lower()
            for m in ctx.guild.members:
                if (
                    m.name.lower() in (clean_mention, clean_ign)
                    or m.display_name.lower() in (clean_mention, clean_ign)
                ):
                    return m.id, m.mention
            return None

        try:
            p_count, s_count = self.service.import_roster_preset(
                guild_id=ctx.guild.id,
                file_path="saved_roster.json",
                member_resolver=resolver,
            )
            await self._update_registration_panel(ctx.guild)
            state = self.service.get_state(ctx.guild.id)
            await ctx.send(f"✅ Restored **{state.name}** roster ({p_count} main, {s_count} subs).")
        except Exception as e:
            await ctx.send(f"❌ Could not restore roster: {e}")

    @app_commands.command(
        name="tournament-bulk-register",
        description="[Admin] Mass-enroll multiple contestants at once (paste lines: IGN | Weapon | Region).",
    )
    @app_commands.describe(
        entries="Multi-line player entries. Example: Player1 | Katana | ASIA\\nPlayer2 | Kusarigama | ASIA",
        default_weapon="Fallback weapon if not specified (default: Katana)",
        default_region="Fallback region if not specified (default: ASIA)",
    )
    @is_tournament_admin()
    async def bulk_register_slash(
        self,
        interaction: discord.Interaction,
        entries: str,
        default_weapon: str = "Katana",
        default_region: str = "ASIA",
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        guild_id = interaction.guild_id or 0

        def resolver(ign: str, mention_str: str) -> tuple[int, str] | None:
            if not guild:
                return None
            clean_mention = mention_str.lstrip("@").lower()
            clean_ign = ign.lower()
            for m in guild.members:
                if (
                    m.name.lower() in (clean_mention, clean_ign)
                    or m.display_name.lower() in (clean_mention, clean_ign)
                ):
                    return m.id, m.mention
            return None

        lines = [line.strip() for line in entries.split("\n") if line.strip()]
        added_main, added_subs, errors = self.service.bulk_register(
            guild_id=guild_id,
            entries=lines,
            default_weapon=default_weapon,
            default_region=default_region,
            member_resolver=resolver,
        )

        if guild:
            await self._update_registration_panel(guild)

        state = self.service.get_state(guild_id)
        err_msg = f"\n⚠️ **Notes:** {', '.join(errors[:5])}" if errors else ""
        embed = discord.Embed(
            title="⚔️ Mass Registration Complete",
            description=(
                f"Enrolled `{added_main}` into Main Bracket, `{added_subs}` into Standby Subs.\n"
                f"• **Current Main Total:** `{len(state.participants)} / {state.max_slots}`\n"
                f"• **Current Subs Total:** `{len(state.substitutes)}`\n"
                f"{err_msg}"
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament Operations")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.command(name="tournament_bulk_register")
    @is_tournament_admin_prefix()
    async def bulk_register_prefix(self, ctx: commands.Context, *, entries: str):
        """Prefix fallback: !tournament_bulk_register <IGN | Weapon | Region>"""
        if not ctx.guild:
            await ctx.send("❌ Command must be used in a server.")
            return
        lines = [l.strip() for l in entries.split("\n") if l.strip()]
        added_main, added_subs, errors = self.service.bulk_register(
            guild_id=ctx.guild.id,
            entries=lines,
        )
        await self._update_registration_panel(ctx.guild)
        state = self.service.get_state(ctx.guild.id)
        await ctx.send(f"⚔️ Enrolled `{added_main}` to main bracket, `{added_subs}` to subs. Total: `{len(state.participants)}/{state.max_slots}`.")

    # -------------------------------------------------------------------------
    # Bot Channel & Role State Persistence (/state-save, /state-restore, /state-status)
    # -------------------------------------------------------------------------

    @app_commands.command(
        name="state-save",
        description="[Admin] Snapshot configured channels, roles, and panel links to saved_state.json.",
    )
    @is_tournament_admin()
    async def state_save_slash(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        snapshot_service = getattr(self.bot, "state_snapshot_service", None)
        clan_service = getattr(self.bot, "clan_showcase_service", None)
        if not snapshot_service or not clan_service:
            await interaction.response.send_message("❌ State snapshot service is unavailable.", ephemeral=True)
            return

        # If channels are unconfigured, auto-discover first before saving
        if interaction.guild:
            snapshot_service.auto_discover_channels(interaction.guild, self.service, clan_service)

        data = snapshot_service.save_snapshot(guild_id, self.service, clan_service)
        t_info = data.get("tournament", {})
        c_info = data.get("clan_showcase", {})

        def ch_fmt(cid):
            return f"<#{cid}> (`{cid}`)" if cid else "*None*"

        def role_fmt(rid, rname=None):
            if rid:
                return f"<@&{rid}> (`{rid}`)"
            return f"`@{rname}`" if rname else "*None*"

        embed = discord.Embed(
            title="💾 Bot Channel & Role State Saved",
            description=(
                f"Successfully captured configuration for **{interaction.guild.name if interaction.guild else 'Server'}** to `saved_state.json`!\n"
                "💡 *This file survives container restarts & git pushes, and will automatically reload on boot.*"
            ),
            color=0x2ECC71,
        )
        embed.add_field(
            name="🏆 Tournament Channels & Roles",
            value=(
                f"• **Registration:** {ch_fmt(t_info.get('registration_channel_id'))}\n"
                f"• **Announcements:** {ch_fmt(t_info.get('announcement_channel_id'))}\n"
                f"• **Check-In:** {ch_fmt(t_info.get('checkin_channel_id'))}\n"
                f"• **Substitutes:** {ch_fmt(t_info.get('subs_channel_id'))}\n"
                f"• **Admin Role:** {role_fmt(t_info.get('admin_role_id'), t_info.get('admin_role_name'))}\n"
                f"• **Participant Role:** {role_fmt(t_info.get('participant_role_id'), t_info.get('participant_role_name'))}"
            ),
            inline=False,
        )
        embed.add_field(
            name="🏛️ Clan Showcase Channels & Roles",
            value=(
                f"• **Showcase Channel:** {ch_fmt(c_info.get('showcase_channel_id'))}\n"
                f"• **Staff Review Channel:** {ch_fmt(c_info.get('staff_review_channel_id'))}\n"
                f"• **Clan Roles Panel:** {ch_fmt(c_info.get('clan_role_channel_id'))}\n"
                f"• **Clanless Role:** {role_fmt(c_info.get('clanless_role_id'))}"
            ),
            inline=False,
        )
        embed.set_footer(text=f"{config.organization_name} • System Operations")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="state_save")
    @is_tournament_admin_prefix()
    async def state_save_prefix(self, ctx: commands.Context):
        """Prefix fallback: !state_save"""
        if not ctx.guild:
            await ctx.send("❌ Command must be used in a server.")
            return
        snapshot_service = getattr(self.bot, "state_snapshot_service", None)
        clan_service = getattr(self.bot, "clan_showcase_service", None)
        if not snapshot_service or not clan_service:
            await ctx.send("❌ State snapshot service is unavailable.")
            return
        snapshot_service.auto_discover_channels(ctx.guild, self.service, clan_service)
        snapshot_service.save_snapshot(ctx.guild.id, self.service, clan_service)
        await ctx.send("✅ Successfully saved channel & role configuration to `saved_state.json`!")

    @app_commands.command(
        name="state-restore",
        description="[Admin] Restore channel, role, and panel configurations from saved_state.json.",
    )
    @app_commands.describe(repost_panels="If True, re-posts/refreshes interactive panel embeds in set channels")
    @is_tournament_admin()
    async def state_restore_slash(
        self,
        interaction: discord.Interaction,
        repost_panels: bool = False,
    ):
        guild_id = interaction.guild_id or 0
        snapshot_service = getattr(self.bot, "state_snapshot_service", None)
        clan_service = getattr(self.bot, "clan_showcase_service", None)
        if not snapshot_service or not clan_service:
            await interaction.response.send_message("❌ State snapshot service is unavailable.", ephemeral=True)
            return

        try:
            snapshot = snapshot_service.restore_snapshot(
                guild_id, self.service, clan_service, guild=interaction.guild
            )
        except FileNotFoundError:
            # Fallback to auto-discovery if file does not exist
            if interaction.guild:
                found = snapshot_service.auto_discover_channels(interaction.guild, self.service, clan_service)
                snapshot = snapshot_service.capture_snapshot(guild_id, self.service, clan_service)
                snapshot_service.save_snapshot(guild_id, self.service, clan_service)
            else:
                await interaction.response.send_message("❌ `saved_state.json` preset file was not found.", ephemeral=True)
                return
            return

        # Optionally refresh or repost panels
        reposted_notes: list[str] = []
        if repost_panels and interaction.guild:
            guild = interaction.guild
            # Refresh registration panel
            if snapshot.registration_channel_id:
                try:
                    await self._update_registration_panel(guild)
                    reposted_notes.append("📝 Registration Panel synced")
                except Exception as e:
                    reposted_notes.append(f"⚠️ Registration Panel error: {e}")
            # Refresh subs panel
            if snapshot.subs_channel_id:
                try:
                    await self._update_subs_panel(guild)
                    reposted_notes.append("🛡️ Substitutes Panel synced")
                except Exception as e:
                    reposted_notes.append(f"⚠️ Substitutes Panel error: {e}")
            # Refresh clan role panel
            clan_cog = self.bot.get_cog("ClanShowcaseCog")
            if clan_cog and hasattr(clan_cog, "_refresh_clan_role_panel"):
                try:
                    await clan_cog._refresh_clan_role_panel(guild)
                    reposted_notes.append("🏛️ Clan Roles Panel synced")
                except Exception as e:
                    reposted_notes.append(f"⚠️ Clan Roles Panel error: {e}")

        def ch_fmt(cid):
            return f"<#{cid}>" if cid else "*None*"

        embed = discord.Embed(
            title="🔄 Bot State Restored",
            description=(
                f"Successfully applied channel and role bindings to **{interaction.guild.name if interaction.guild else 'Server'}**!\n\n"
                f"• **Registration:** {ch_fmt(snapshot.registration_channel_id)}\n"
                f"• **Announcements:** {ch_fmt(snapshot.announcement_channel_id)}\n"
                f"• **Check-In:** {ch_fmt(snapshot.checkin_channel_id)}\n"
                f"• **Substitutes:** {ch_fmt(snapshot.subs_channel_id)}\n"
                f"• **Clan Showcase:** {ch_fmt(snapshot.showcase_channel_id)}\n"
                f"• **Staff Review:** {ch_fmt(snapshot.staff_review_channel_id)}\n"
                f"• **Clan Roles Panel:** {ch_fmt(snapshot.clan_role_channel_id)}\n"
                + (f"\n**Panel Status:**\n" + "\n".join(f"• {n}" for n in reposted_notes) if reposted_notes else "")
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • System Operations")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="state_restore")
    @is_tournament_admin_prefix()
    async def state_restore_prefix(self, ctx: commands.Context, repost_panels: bool = False):
        """Prefix fallback: !state_restore [repost_panels=True/False]"""
        if not ctx.guild:
            await ctx.send("❌ Command must be used in a server.")
            return
        snapshot_service = getattr(self.bot, "state_snapshot_service", None)
        clan_service = getattr(self.bot, "clan_showcase_service", None)
        if not snapshot_service or not clan_service:
            await ctx.send("❌ State snapshot service is unavailable.")
            return
        try:
            snapshot = snapshot_service.restore_snapshot(ctx.guild.id, self.service, clan_service)
            msg = f"🔄 Successfully restored channels for **{ctx.guild.name}**!"
            if repost_panels:
                await self._update_registration_panel(ctx.guild)
                await self._update_subs_panel(ctx.guild)
                clan_cog = self.bot.get_cog("ClanShowcaseCog")
                if clan_cog and hasattr(clan_cog, "_refresh_clan_role_panel"):
                    await clan_cog._refresh_clan_role_panel(ctx.guild)
                msg += " (Panels refreshed)."
            await ctx.send(msg)
        except Exception as e:
            await ctx.send(f"❌ Failed to restore state: {e}")

    @app_commands.command(
        name="state-status",
        description="[Admin] Compare active channel and role bindings against saved_state.json snapshot.",
    )
    @is_tournament_admin()
    async def state_status_slash(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        snapshot_service = getattr(self.bot, "state_snapshot_service", None)
        clan_service = getattr(self.bot, "clan_showcase_service", None)
        if not snapshot_service or not clan_service:
            await interaction.response.send_message("❌ State snapshot service is unavailable.", ephemeral=True)
            return

        current = snapshot_service.capture_snapshot(guild_id, self.service, clan_service)
        try:
            saved = snapshot_service.load_snapshot()
        except FileNotFoundError:
            saved = None

        def line_diff(label: str, cur_val: Any, saved_val: Any, is_channel: bool = True):
            if is_channel:
                cur_str = f"<#{cur_val}>" if cur_val else "*Not Set*"
                sav_str = f"<#{saved_val}>" if saved_val else "*None*"
            else:
                cur_str = f"<@&{cur_val}>" if cur_val else "*Not Set*"
                sav_str = f"<@&{saved_val}>" if saved_val else "*None*"
            match_icon = "✅" if cur_val == saved_val and cur_val is not None else ("⚠️" if cur_val != saved_val else "⚪")
            return f"{match_icon} **{label}:** {cur_str} *(Saved: {sav_str})*"

        embed = discord.Embed(
            title="📊 Bot Channel & State Status",
            description=(
                f"Configuration diagnostics for **{interaction.guild.name if interaction.guild else 'Server'}**\n"
                f"**Saved Snapshot File:** `{'Found (`saved_state.json`)' if saved else '⚠️ Missing (`saved_state.json`)'}`\n\n"
                "**Channels:**\n"
                f"{line_diff('Registration', current.registration_channel_id, saved.registration_channel_id if saved else None)}\n"
                f"{line_diff('Announcements', current.announcement_channel_id, saved.announcement_channel_id if saved else None)}\n"
                f"{line_diff('Check-In', current.checkin_channel_id, saved.checkin_channel_id if saved else None)}\n"
                f"{line_diff('Substitutes', current.subs_channel_id, saved.subs_channel_id if saved else None)}\n"
                f"{line_diff('Clan Showcase', current.showcase_channel_id, saved.showcase_channel_id if saved else None)}\n"
                f"{line_diff('Staff Review', current.staff_review_channel_id, saved.staff_review_channel_id if saved else None)}\n"
                f"{line_diff('Clan Roles Panel', current.clan_role_channel_id, saved.clan_role_channel_id if saved else None)}\n\n"
                "**Roles:**\n"
                f"{line_diff('Admin Role', current.admin_role_id, saved.admin_role_id if saved else None, is_channel=False)}\n"
                f"{line_diff('Participant Role', current.participant_role_id, saved.participant_role_id if saved else None, is_channel=False)}\n"
                f"{line_diff('Clanless Role', current.clanless_role_id, saved.clanless_role_id if saved else None, is_channel=False)}"
            ),
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • System Diagnostics")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="tournament-clear",
        description="[Admin] Wipe both main roster and substitute list for a fresh event.",
    )
    @is_tournament_admin()
    async def clear_tournament(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)

        # Clean up active registration panel message if it exists
        if interaction.guild and state.registration_channel_id and state.registration_message_id:
            reg_ch = interaction.guild.get_channel(state.registration_channel_id)
            if isinstance(reg_ch, discord.TextChannel):
                try:
                    old_reg_msg = await reg_ch.fetch_message(state.registration_message_id)
                    await old_reg_msg.delete()
                except Exception:
                    pass

        # Clean up active substitutes panel message if it exists
        if interaction.guild and state.subs_channel_id and state.subs_message_id:
            subs_ch = interaction.guild.get_channel(state.subs_channel_id)
            if isinstance(subs_ch, discord.TextChannel):
                try:
                    old_subs_msg = await subs_ch.fetch_message(state.subs_message_id)
                    await old_subs_msg.delete()
                except Exception:
                    pass

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
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="tournament-setup-section",
        description="[Server Admin] Construct the official tournament categories, channels, and arenas.",
    )
    @app_commands.describe(
        confirm="Set to True to build the tournament section and link bot channels.",
    )
    @app_commands.default_permissions(administrator=True)
    @is_server_admin()
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
                registration_channel_id=cmap.get("registration"),
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
            reg_mention = f"<#{cmap['registration']}>" if "registration" in cmap else "*Not set*"
            chk_mention = f"<#{cmap['checkin']}>" if "checkin" in cmap else "*Not set*"
            sub_mention = f"<#{cmap['subs']}>" if "subs" in cmap else "*Not set*"
            embed.add_field(
                name="🔗 Linked & Protected Channels",
                value=(
                    f"• Announcements: {ann_mention} *(Read-only)*\n"
                    f"• Registrations: {reg_mention} *(🔒 Locked until `/tournament-open`)*\n"
                    f"• Substitutes: {sub_mention} *(🔒 Locked until `/tournament-open-subs`)*\n"
                    f"• Check-in: {chk_mention} *(🔒 Locked until `/tournament-open-checkin`)*"
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
        description="[Server Admin] Safely remove the tournament categories and match arenas.",
    )
    @app_commands.describe(
        confirm="Set to True to confirm removing tournament categories and channels.",
    )
    @app_commands.default_permissions(administrator=True)
    @is_server_admin()
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

    # =========================================================================
    # Scheduled Events & Website REST API Sync (unitedduelingamity.org)
    # =========================================================================

    @app_commands.command(
        name="tournament-schedule-event",
        description="Admin: Schedule an official Discord server event (with optional sync to website).",
    )
    @app_commands.describe(
        name="Tournament title or event name (e.g. UDA Winter Championship)",
        date="Date of the event (e.g. 2026-11-15 or 11/15/2026)",
        time="Start time (e.g. 18:00 or 6:00 PM)",
        timezone="Timezone for the start time (defaults to EST)",
        sync_to_website="Whether to sync and publish this event to unitedduelingamity.org (default: True)",
        description="Optional event description, rules, or tournament notes",
        duration_hours="Estimated duration in hours (default: 2.0)",
        location="Location text for external events (e.g. UDA Tournament Hub)",
        channel="Optional voice or stage arena channel for the event",
        image="Optional cover image banner for the Discord event",
    )
    @app_commands.choices(timezone=TIMEZONE_CHOICES)
    @is_event_admin()
    async def schedule_event(
        self,
        interaction: discord.Interaction,
        name: str,
        date: str,
        time: str,
        timezone: Optional[app_commands.Choice[str]] = None,
        sync_to_website: bool = True,
        description: Optional[str] = None,
        duration_hours: float = 2.0,
        location: Optional[str] = None,
        channel: Optional[discord.VoiceChannel | discord.StageChannel] = None,
        image: Optional[discord.Attachment] = None,
    ):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This command must be used within a server.", ephemeral=True)
            return

        # 1. Check Bot Permissions
        bot_member = guild.me
        if not bot_member or not bot_member.guild_permissions.manage_events:
            await interaction.response.send_message(
                "❌ The bot is missing the **Manage Events** permission in this server to create Discord scheduled events.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=False)

        # 2. Parse Date & Time
        tz_str = timezone.value if timezone else "EST"
        valid, start_time, err = parse_event_datetime(date, time, tz_str)
        if not valid or not start_time:
            await interaction.followup.send(f"❌ {err}", ephemeral=True)
            return

        # 3. Calculate End Time (required by Discord for external events)
        dur = max(0.5, duration_hours)
        end_time = start_time + timedelta(hours=dur)

        # 4. Optional Cover Image bytes
        image_bytes = None
        if image:
            try:
                image_bytes = await image.read()
            except Exception as exc:
                logger.warning("Could not read image attachment for event: %s", exc)

        # 5. Create Discord Scheduled Event
        event_name = name.strip()[:100]
        event_desc = (description or f"Official {config.organization_name} Tournament Event").strip()[:1000]

        create_kwargs = {
            "name": event_name,
            "description": event_desc,
            "start_time": start_time,
            "end_time": end_time,
            "privacy_level": discord.PrivacyLevel.guild_only,
            "reason": f"Scheduled by {interaction.user} via /tournament-schedule-event",
        }
        if image_bytes is not None:
            create_kwargs["image"] = image_bytes

        try:
            if channel:
                entity_type = (
                    discord.EntityType.stage_instance
                    if isinstance(channel, discord.StageChannel)
                    else discord.EntityType.voice
                )
                create_kwargs["channel"] = channel
                create_kwargs["entity_type"] = entity_type
                scheduled_event = await guild.create_scheduled_event(**create_kwargs)
                location_display = channel.mention
            else:
                loc_text = (location or f"{config.organization_name} Tournament Hub").strip()[:100]
                create_kwargs["location"] = loc_text
                create_kwargs["entity_type"] = discord.EntityType.external
                scheduled_event = await guild.create_scheduled_event(**create_kwargs)
                location_display = f"📍 `{loc_text}`"
        except Exception as exc:
            logger.error("Failed to create Discord scheduled event: %s", exc, exc_info=True)
            await interaction.followup.send(
                f"❌ Failed to create Discord scheduled event: {exc}", ephemeral=True
            )
            return

        # 6. Automatic Tournament Schedule & Reminders Sync
        self.service.set_tournament_time(
            start_time=start_time.isoformat(),
            start_timestamp=int(start_time.timestamp()),
            event_id=scheduled_event.id,
            guild_id=guild.id,
        )

        # 7. Automatic Website Feed Publication
        website_sync_status = (
            "✅ **Live on Website!**\n"
            "Automatically published to the live public schedule on [unitedduelingamity.org/tournaments.html](https://unitedduelingamity.org/tournaments.html)."
        )

        # 8. Build Response Embed
        embed = discord.Embed(
            title="📅 Tournament Event Scheduled!",
            description=(
                f"**Event:** [{scheduled_event.name}]({scheduled_event.url})\n"
                f"**Date & Time:** <t:{int(start_time.timestamp())}:F> (<t:{int(start_time.timestamp())}:R>)\n"
                f"**Location:** {location_display}\n\n"
                f"{scheduled_event.description}"
            ),
            color=config.embed_color,
        )
        if scheduled_event.cover_image:
            embed.set_image(url=scheduled_event.cover_image.url)

        embed.add_field(
            name="📌 Discord Event Banner",
            value=f"Listed at the **top of the server**! Members can click **[Interested]({scheduled_event.url})** to receive Discord reminders before it starts.",
            inline=False,
        )
        embed.add_field(
            name="📬 Automated Contestant DMs",
            value="Contestants will automatically receive **Day-Of** and **30-Minute** warning DMs with their registered region and dynamic countdown!",
            inline=False,
        )
        embed.add_field(
            name="🌐 Website Feed (unitedduelingamity.org)",
            value=website_sync_status,
            inline=False,
        )
        embed.set_footer(text=f"{config.organization_name} • Event Operations")

        await interaction.followup.send(embed=embed)

    # -------------------------------------------------------------------------
    # Event Management: Cancel & Complete Events, Manage Past Results
    # -------------------------------------------------------------------------

    async def _scheduled_events_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        choices = []
        guild = interaction.guild
        if guild:
            for ev in getattr(guild, "scheduled_events", []):
                status_str = str(getattr(ev, "status", "")).lower()
                if "cancel" in status_str or "complete" in status_str or "ended" in status_str:
                    continue
                date_str = ev.start_time.strftime("%m/%d") if ev.start_time else "TBD"
                display_name = f"{ev.name} ({date_str})"[:100]
                if not current or current.lower() in display_name.lower():
                    choices.append(app_commands.Choice(name=display_name, value=str(ev.id)))
                    if len(choices) >= 25:
                        break
        return choices

    async def _past_results_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        choices = []
        past_service = getattr(self.bot, "past_results_service", None)
        if not past_service:
            from services.past_results_service import PastResultsService
            past_service = PastResultsService()
            self.bot.past_results_service = past_service

        for res in past_service.get_all_results():
            display = f"{res.name} (🏆 {res.champion} | {res.date})"[:100]
            if not current or current.lower() in display.lower():
                choices.append(app_commands.Choice(name=display, value=res.id))
                if len(choices) >= 25:
                    break
        return choices

    @app_commands.command(
        name="tournament-cancel-event",
        description="Admin: Cancel and remove an upcoming scheduled event from Discord and the website schedule.",
    )
    @app_commands.describe(
        event="The scheduled tournament event to cancel and remove"
    )
    @is_event_admin()
    async def cancel_event(self, interaction: discord.Interaction, event: str):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        target_event = None
        for ev in getattr(guild, "scheduled_events", []):
            if str(ev.id) == event or ev.name.lower() == event.lower():
                target_event = ev
                break

        if not target_event:
            await interaction.response.send_message(
                f"❌ Could not find a scheduled event matching `{event}`.",
                ephemeral=True,
            )
            return

        event_name = target_event.name
        try:
            await target_event.delete(reason=f"Canceled by {interaction.user} via /tournament-cancel-event")
        except Exception as exc:
            logger.error("Failed to delete scheduled event %s: %s", target_event.id, exc)
            await interaction.response.send_message(
                f"❌ Failed to cancel scheduled event: {exc}",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🗑️ Tournament Event Canceled",
            description=(
                f"**Event:** `{event_name}`\n"
                f"**Action:** Removed from Discord server events and the website upcoming schedule.\n\n"
                f"• The top-of-server banner has been removed.\n"
                f"• [unitedduelingamity.org/tournaments.html](https://unitedduelingamity.org/tournaments.html) will no longer list this event."
            ),
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Event Operations")
        await interaction.response.send_message(embed=embed)

    @cancel_event.autocomplete("event")
    async def cancel_event_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._scheduled_events_autocomplete(interaction, current)

    @app_commands.command(
        name="tournament-complete-event",
        description="Admin: Conclude a tournament, crown the champion clan/player, and publish to Past Results.",
    )
    @app_commands.describe(
        event="The tournament or event that concluded",
        champion="The winning clan or champion player name",
        runner_up="The runner-up clan or player name (optional)",
        score="Final match score or series result (e.g. 3-1, 2-0)",
        notes="Optional tournament recap or notes",
    )
    @is_event_admin()
    async def complete_event(
        self,
        interaction: discord.Interaction,
        event: str,
        champion: str,
        runner_up: str = "",
        score: str = "",
        notes: str = "",
    ):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        target_event = None
        for ev in getattr(guild, "scheduled_events", []):
            if str(ev.id) == event or ev.name.lower() == event.lower():
                target_event = ev
                break

        event_name = target_event.name if target_event else event.strip()
        event_date = (
            target_event.start_time.strftime("%Y-%m-%d")
            if target_event and target_event.start_time
            else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        event_type = "Clan Cup" if "clan" in event_name.lower() else "Tournament"

        past_service = getattr(self.bot, "past_results_service", None)
        if not past_service:
            from services.past_results_service import PastResultsService
            past_service = PastResultsService()
            self.bot.past_results_service = past_service

        past_service.add_result(
            name=event_name,
            champion=champion,
            date=event_date,
            runner_up=runner_up,
            score=score,
            type_str=event_type,
            description=notes or (target_event.description if target_event else ""),
        )

        # Conclude the Discord scheduled event so it leaves Upcoming
        if target_event:
            try:
                await target_event.delete(reason=f"Concluded by {interaction.user} via /tournament-complete-event")
            except Exception as exc:
                logger.debug("Could not remove concluded scheduled event: %s", exc)

        embed = discord.Embed(
            title="🏆 Tournament Concluded & Published to Past Results!",
            description=(
                f"**Tournament:** `{event_name}`\n"
                f"**Date:** `{event_date}`\n\n"
                f"🥇 **Champion:** **{champion}**\n"
                f"{f'🥈 **Runner-Up:** {runner_up}' if runner_up else ''}\n"
                f"{f'📊 **Final Score:** `{score}`' if score else ''}\n"
                f"{f'📝 **Notes:** {notes}' if notes else ''}\n\n"
                f"Published to **[unitedduelingamity.org/tournaments.html](https://unitedduelingamity.org/tournaments.html)** (Past Results)."
            ),
            color=0xD4AF37,  # Official Gold
        )
        embed.set_footer(text=f"{config.organization_name} • Hall of Champions")
        await interaction.response.send_message(embed=embed)

    @complete_event.autocomplete("event")
    async def complete_event_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._scheduled_events_autocomplete(interaction, current)

    @app_commands.command(
        name="tournament-remove-past-result",
        description="Admin: Remove an entry from the website's Past Results archive.",
    )
    @app_commands.describe(
        result="Select the past result entry to delete"
    )
    @is_event_admin()
    async def remove_past_result_cmd(self, interaction: discord.Interaction, result: str):
        past_service = getattr(self.bot, "past_results_service", None)
        if not past_service:
            from services.past_results_service import PastResultsService
            past_service = PastResultsService()
            self.bot.past_results_service = past_service

        removed = past_service.remove_result(result)
        if not removed:
            await interaction.response.send_message(
                f"❌ Could not find a past result matching `{result}`.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🗑️ Past Result Removed",
            description=(
                f"**Event:** `{removed.name}` ({removed.date})\n"
                f"**Champion:** {removed.champion}\n\n"
                f"Successfully deleted from the website's Past Results archive."
            ),
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Event Operations")
        await interaction.response.send_message(embed=embed)

    @remove_past_result_cmd.autocomplete("result")
    async def remove_past_result_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._past_results_autocomplete(interaction, current)

    # -------------------------------------------------------------------------
    # Interactive Event Scheduling Panel (/post-event-scheduler-panel)
    # -------------------------------------------------------------------------

    @app_commands.command(
        name="post-event-scheduler-panel",
        description="Admin: Drop the interactive Tournament & Event Scheduler panel with 1-click modal button.",
    )
    @app_commands.describe(
        channel="Channel to post the scheduler panel in (defaults to current channel)"
    )
    @is_event_admin()
    async def post_event_scheduler_panel_slash(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        target_chan = channel or interaction.channel
        if not isinstance(target_chan, discord.TextChannel):
            await interaction.response.send_message("❌ Target must be a text channel.", ephemeral=True)
            return

        panel_embed = discord.Embed(
            title="📅 Official Tournament & Event Scheduler",
            description=(
                f"Welcome to the official **{config.organization_name}** Tournament Event Scheduler!\n\n"
                "Staff and Tournament Admins can click the button below to schedule an official event.\n\n"
                "**What happens when you schedule an event:**\n"
                "• **📌 Top of Server Banner:** Discord automatically creates the official event at the very top of the server so members can click **Interested** and get reminder pings.\n"
                "• **🌐 Website Sync:** If enabled, the event is automatically pushed to **https://unitedduelingamity.org** so it appears on the live public schedule!\n\n"
                "Click **📅 Schedule Tournament Event** below to open the form!"
            ),
            color=config.embed_color,
        )
        panel_embed.set_footer(
            text=f"{config.organization_name} • Tournament Operations"
        )

        view = TournamentEventPanelView()
        await target_chan.send(embed=panel_embed, view=view)

        await interaction.response.send_message(
            f"✅ Tournament event scheduler panel successfully posted in {target_chan.mention}!",
            ephemeral=True,
        )

    @commands.command(name="post_event_scheduler_panel")
    async def post_event_scheduler_panel_prefix(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """Prefix command fallback (!post_event_scheduler_panel)."""
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a server.")
            return

        # Restrict to Server Admins / Event Managers / Event Role
        if not check_is_event_admin(ctx.author, ctx.guild, self.bot):
            await ctx.send("❌ You need Manage Events, Administrator permissions, or the Event & Website role to post this panel.")
            return

        target_chan = channel or ctx.channel
        if not isinstance(target_chan, discord.TextChannel):
            await ctx.send("❌ Target must be a text channel.")
            return

        panel_embed = discord.Embed(
            title="📅 Official Tournament & Event Scheduler",
            description=(
                f"Welcome to the official **{config.organization_name}** Tournament Event Scheduler!\n\n"
                "Staff and Tournament Admins can click the button below to schedule an official event.\n\n"
                "**What happens when you schedule an event:**\n"
                "• **📌 Top of Server Banner:** Discord automatically creates the official event at the very top of the server so members can click **Interested** and get reminder pings.\n"
                "• **🌐 Website Sync:** If enabled, the event is automatically pushed to **https://unitedduelingamity.org** so it appears on the live public schedule!\n\n"
                "Click **📅 Schedule Tournament Event** below to open the form!"
            ),
            color=config.embed_color,
        )
        panel_embed.set_footer(
            text=f"{config.organization_name} • Tournament Operations"
        )

        view = TournamentEventPanelView()
        await target_chan.send(embed=panel_embed, view=view)
        await ctx.send(f"✅ Tournament event scheduler panel posted in {target_chan.mention}!")

    @app_commands.command(
        name="post-tournament-staff-panel",
        description="[Admin] Post the interactive 1-click Tournament Staff Operations Panel.",
    )
    @app_commands.describe(
        channel="Optional channel to post the staff operations panel into (default: current channel)",
    )
    @is_tournament_admin()
    async def post_tournament_staff_panel_cmd(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Please run this command in a text channel or specify a valid text channel.",
                ephemeral=True,
            )
            return

        embed = build_staff_panel_embed()
        view = TournamentStaffPanelView()
        await target_channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            f"✅ Tournament Staff Operations Panel posted to {target_channel.mention}!",
            ephemeral=True,
        )

    @commands.command(name="post_tournament_staff_panel", aliases=["post_staff_panel"])
    async def post_tournament_staff_panel_prefix(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """Prefix command fallback (!post_tournament_staff_panel / !post_staff_panel)."""
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a server.")
            return

        if not check_is_tournament_admin(ctx.author, ctx.guild, self.bot):
            await ctx.send("❌ You need Administrator permissions or the Tournament Admin role to post this.")
            return

        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            await ctx.send("❌ Target must be a text channel.")
            return

        embed = build_staff_panel_embed()
        view = TournamentStaffPanelView()
        await target_channel.send(embed=embed, view=view)
        if target_channel != ctx.channel:
            await ctx.send(f"✅ Tournament Staff Operations Panel posted to {target_channel.mention}!")

    @app_commands.command(
        name="post-registration-panel",
        description="[Admin] Post or refresh the live interactive Player Registration Hub in a channel.",
    )
    @app_commands.describe(
        channel="Optional channel to post into (defaults to configured registration channel or current channel)"
    )
    @is_tournament_admin()
    async def post_registration_panel_cmd(
        self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command must be run inside a server.", ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        target_channel = channel or (interaction.guild.get_channel(state.registration_channel_id) if state.registration_channel_id else None) or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message("❌ Target must be a valid text channel.", ephemeral=True)
            return

        perms = target_channel.permissions_for(interaction.guild.me)
        if not perms.send_messages or not perms.embed_links:
            await interaction.response.send_message(
                f"❌ Missing Send Messages or Embed Links permission in {target_channel.mention}.",
                ephemeral=True,
            )
            return

        await self._post_or_update_registration_panel(interaction.guild, target_channel)
        await interaction.response.send_message(
            f"✅ Player Registration Hub posted to {target_channel.mention}!", ephemeral=True
        )

    @commands.command(name="post_registration_panel", aliases=["post_reg_panel"])
    @commands.guild_only()
    async def post_registration_panel_prefix(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """Prefix command to post the interactive Player Registration Hub."""
        if not check_is_tournament_admin(ctx.author, ctx.guild, self.bot):
            await ctx.send("❌ You do not have permission to use this command.")
            return

        guild_id = ctx.guild.id
        state = self.service.get_state(guild_id)
        target_channel = channel or (ctx.guild.get_channel(state.registration_channel_id) if state.registration_channel_id else None) or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            await ctx.send("❌ Target must be a valid text channel.")
            return

        await self._post_or_update_registration_panel(ctx.guild, target_channel)
        await ctx.send(f"✅ Player Registration Hub posted to {target_channel.mention}!")

    @app_commands.command(
        name="post-subs-panel",
        description="[Admin] Post or refresh the live interactive Standby Substitute Hub in a channel.",
    )
    @app_commands.describe(
        channel="Optional channel to post into (defaults to configured substitutes channel or current channel)"
    )
    @is_tournament_admin()
    async def post_subs_panel_cmd(
        self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command must be run inside a server.", ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        target_channel = channel or (interaction.guild.get_channel(state.subs_channel_id) if state.subs_channel_id else None) or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message("❌ Target must be a valid text channel.", ephemeral=True)
            return

        perms = target_channel.permissions_for(interaction.guild.me)
        if not perms.send_messages or not perms.embed_links:
            await interaction.response.send_message(
                f"❌ Missing Send Messages or Embed Links permission in {target_channel.mention}.",
                ephemeral=True,
            )
            return

        await self._post_or_update_subs_panel(interaction.guild, target_channel)
        await interaction.response.send_message(
            f"✅ Standby Substitute Hub posted to {target_channel.mention}!", ephemeral=True
        )

    @commands.command(name="post_subs_panel", aliases=["post_sub_panel"])
    @commands.guild_only()
    async def post_subs_panel_prefix(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """Prefix command to post the interactive Standby Substitute Hub."""
        if not check_is_tournament_admin(ctx.author, ctx.guild, self.bot):
            await ctx.send("❌ You do not have permission to use this command.")
            return

        guild_id = ctx.guild.id
        state = self.service.get_state(guild_id)
        target_channel = channel or (ctx.guild.get_channel(state.subs_channel_id) if state.subs_channel_id else None) or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            await ctx.send("❌ Target must be a valid text channel.")
            return

        await self._post_or_update_subs_panel(ctx.guild, target_channel)
        await ctx.send(f"✅ Standby Substitute Hub posted to {target_channel.mention}!")

    @app_commands.command(
        name="tournament-post-checkin-panel",
        description="[Admin] Post or refresh the live interactive Tournament Check-In Hub in a channel.",
    )
    @app_commands.describe(
        channel="Optional channel to post into (defaults to configured check-in channel or current channel)"
    )
    @is_tournament_admin()
    async def post_checkin_panel_cmd(
        self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command must be run inside a server.", ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        target_channel = channel or (interaction.guild.get_channel(state.checkin_channel_id) if state.checkin_channel_id else None) or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message("❌ Target must be a valid text channel.", ephemeral=True)
            return

        perms = target_channel.permissions_for(interaction.guild.me)
        if not perms.send_messages or not perms.embed_links:
            await interaction.response.send_message(
                f"❌ Missing Send Messages or Embed Links permission in {target_channel.mention}.",
                ephemeral=True,
            )
            return

        await self._post_or_update_checkin_panel(interaction.guild, target_channel)
        await interaction.response.send_message(
            f"✅ Tournament Check-In Hub posted to {target_channel.mention}!", ephemeral=True
        )

    @commands.command(name="post_checkin_panel", aliases=["post_checkin_hub"])
    @commands.guild_only()
    async def post_checkin_panel_prefix(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """Prefix command to post the interactive Tournament Check-In Hub."""
        if not check_is_tournament_admin(ctx.author, ctx.guild, self.bot):
            await ctx.send("❌ You do not have permission to use this command.")
            return

        guild_id = ctx.guild.id
        state = self.service.get_state(guild_id)
        target_channel = channel or (ctx.guild.get_channel(state.checkin_channel_id) if state.checkin_channel_id else None) or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            await ctx.send("❌ Target must be a valid text channel.")
            return

        await self._post_or_update_checkin_panel(ctx.guild, target_channel)
        await ctx.send(f"✅ Tournament Check-In Hub posted to {target_channel.mention}!")

    @app_commands.command(
        name="tournament-staff-checkin",
        description="[Admin] Manually override and set a contestant's check-in status.",
    )
    @app_commands.describe(
        user="Discord user (or mention) to override",
        status="Target check-in status (checked_in or unconfirmed)",
    )
    @app_commands.choices(
        status=[
            app_commands.Choice(name="✅ Checked In & Ready", value="checked_in"),
            app_commands.Choice(name="❌ Unconfirmed / Not Checked In", value="unconfirmed"),
        ]
    )
    @is_tournament_admin()
    async def staff_checkin_cmd(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        status: app_commands.Choice[str],
    ):
        guild_id = interaction.guild_id or 0
        new_status = (status.value == "checked_in")
        res = self.service.staff_set_checkin(user.id, new_status, guild_id=guild_id)
        success, msg, part, role_type = res.success, res.message, res.participant, res.role_type
        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        await self._update_all_live_panels(interaction.guild)
        staff_actor = interaction.user if isinstance(interaction.user, discord.Member) else None
        await self._dispatch_checkin_log(
            interaction.guild,
            part,
            action="staff_override",
            role_type=role_type,
            staff_member=staff_actor,
        )

        embed = discord.Embed(
            title="⚙️ Staff Check-In Override",
            description=msg,
            color=0x2ECC71 if new_status else 0xE67E22,
        )
        embed.set_footer(text=f"{config.organization_name} • Staff Operations")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="post-staff-guide",
        description="[Admin] Post the tournament staff operational cheat sheet and phase guide.",
    )
    @app_commands.describe(
        channel="Optional channel to post the staff guide into (default: current channel)",
    )
    @is_tournament_admin()
    async def post_staff_guide_cmd(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Please run this command in a text channel or specify a valid text channel.",
                ephemeral=True,
            )
            return

        embed = build_staff_guide_embed(section="overview")
        view = TournamentStaffGuideView(current_section="overview")
        await target_channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            f"📖 Tournament Staff Operations Guide posted to {target_channel.mention}!",
            ephemeral=True,
        )

    @commands.command(name="post_staff_guide", aliases=["post_tournament_staff_guide"])
    async def post_staff_guide_prefix(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """Prefix command fallback (!post_staff_guide / !post_tournament_staff_guide)."""
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a server.")
            return

        if not check_is_tournament_admin(ctx.author, ctx.guild, self.bot):
            await ctx.send("❌ You need Administrator permissions or the Tournament Admin role to post this.")
            return

        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            await ctx.send("❌ Target must be a text channel.")
            return

        embed = build_staff_guide_embed(section="overview")
        view = TournamentStaffGuideView(current_section="overview")
        await target_channel.send(embed=embed, view=view)
        if target_channel != ctx.channel:
            await ctx.send(f"📖 Tournament Staff Operations Guide posted to {target_channel.mention}!")


async def setup(bot: commands.Bot):
    """Cog setup registration entry point."""
    service: TournamentService = getattr(bot, "tournament_service", None)
    if not service:
        from utils.storage import StorageManager
        storage = StorageManager(config.tournament_file, config.backup_dir, config.max_backups)
        service = TournamentService(storage=storage)
        bot.tournament_service = service
    await bot.add_cog(TournamentCog(bot, service))


__all__ = [
    "TournamentCog",
    "setup",
    "HelpView",
    "TournamentEventModal",
    "TournamentEventPanelView",
    "TournamentStaffGuideSelect",
    "TournamentStaffGuideView",
    "StaffCreateTournamentModal",
    "StaffOpenTournamentModal",
    "StaffAnnounceModal",
    "StaffSetTimeModal",
    "TournamentStaffPanelView",
    "UserRegistrationModal",
    "TournamentRegistrationPanelView",
    "TournamentClosedRegistrationView",
    "UserSubRegistrationModal",
    "TournamentSubsPanelView",
    "TournamentClosedSubsView",
    "TournamentCheckinPanelView",
    "check_is_tournament_admin",
    "check_is_event_admin",
    "is_tournament_admin",
    "is_tournament_admin_prefix",
    "is_event_admin",
    "is_server_admin",
    "build_checkin_panel_embed",
    "build_checkin_receipt_embed",
    "build_help_embed",
    "build_registration_closed_embed",
    "build_registration_panel_embed",
    "build_roster_embed",
    "build_staff_guide_embed",
    "build_staff_panel_embed",
    "build_status_embed",
    "build_subs_closed_embed",
    "build_subs_panel_embed",
    "build_tournament_reminder_embed",
]
