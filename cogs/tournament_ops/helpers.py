"""
Lifecycle hooks, background reminder tasks, live panel refreshers,
permission synchronizers, and autocomplete resolvers for tournament operations.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import tasks

from config import config
from services.tournament_service import TournamentState
from utils.tournament_embeds import (
    build_checkin_panel_embed,
    build_checkin_receipt_embed,
    build_registration_closed_embed,
    build_registration_panel_embed,
    build_subs_closed_embed,
    build_subs_panel_embed,
    build_tournament_reminder_embed,
)
from utils.tournament_views import (
    TournamentCheckinPanelView,
    TournamentClosedRegistrationView,
    TournamentClosedSubsView,
    TournamentEventPanelView,
    TournamentRegistrationPanelView,
    TournamentStaffGuideView,
    TournamentStaffPanelView,
    TournamentSubsPanelView,
)

logger = logging.getLogger(__name__)


class TournamentHelpersMixin:
    """Lifecycle, background tasks, embed updates, and role/channel synchronizers."""

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

    async def _update_all_live_panels(
        self, guild: Optional[discord.Guild], delay: float = 0.5
    ) -> None:
        """
        Debounced helper to refresh Registration, Substitute, and Check-In panels.
        Coalesces concurrent rapid check-in / registration updates to avoid Discord HTTP 429 rate limits.
        """
        if not guild:
            return

        guild_id = guild.id
        if not hasattr(self, "_panel_update_tasks"):
            self._panel_update_tasks: dict[int, asyncio.Task] = {}
        if not hasattr(self, "_panel_update_needs_rerun"):
            self._panel_update_needs_rerun: dict[int, bool] = {}

        if guild_id in self._panel_update_tasks and not self._panel_update_tasks[guild_id].done():
            self._panel_update_needs_rerun[guild_id] = True
            return

        async def _debounced_worker():
            try:
                if delay > 0:
                    await asyncio.sleep(delay)
                while True:
                    self._panel_update_needs_rerun[guild_id] = False
                    await asyncio.gather(
                        self._update_registration_panel(guild),
                        self._update_subs_panel(guild),
                        self._update_checkin_panel(guild),
                        return_exceptions=True,
                    )
                    if self._panel_update_needs_rerun.get(guild_id):
                        if delay > 0:
                            await asyncio.sleep(delay)
                        continue
                    break
            except Exception as exc:
                logger.debug("Error in debounced live panel worker for guild %s: %s", guild_id, exc)
            finally:
                self._panel_update_tasks.pop(guild_id, None)
                self._panel_update_needs_rerun.pop(guild_id, None)

        task = asyncio.create_task(_debounced_worker())
        self._panel_update_tasks[guild_id] = task

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

    # -------------------------------------------------------------------------
    # Autocomplete Resolvers & Helpers
    # -------------------------------------------------------------------------

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
