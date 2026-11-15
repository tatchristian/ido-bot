"""
Event Calendar and Website Schedule Sync subcommands:
/event create, /event cancel, /event complete, /event remove-past-result.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands

from config import config
from services.website_sync_service import parse_event_datetime
from utils.tournament_views import is_event_admin

from .constants import TIMEZONE_CHOICES

logger = logging.getLogger(__name__)


class TournamentEventMixin:
    """Discord scheduled events creation, cancellation, conclusion, and website schedule sync."""

    event_group = app_commands.Group(
        name="event", description="Discord scheduled event and calendar management"
    )

    @event_group.command(
        name="create",
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
            "reason": f"Scheduled by {interaction.user} via /event create",
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
        seen_names = set()

        if guild:
            # 1. Native Discord scheduled events (active and recently ended/completed)
            for ev in getattr(guild, "scheduled_events", []):
                date_str = ev.start_time.strftime("%m/%d") if ev.start_time else "TBD"
                status_str = str(getattr(ev, "status", "")).lower()
                suffix = " [Ended]" if ("complete" in status_str or "ended" in status_str) else ""
                display_name = f"{ev.name} ({date_str}){suffix}"[:100]
                seen_names.add(ev.name.lower())
                if not current or current.lower() in display_name.lower() or current.lower() in ev.name.lower():
                    choices.append(app_commands.Choice(name=display_name, value=str(ev.id)))
                    if len(choices) >= 20:
                        break

            # 2. Include active tournament state / website feed if not already in choices
            if hasattr(self, "service") and len(choices) < 25:
                state = self.service.get_state(guild.id)
                if state and state.name:
                    state_name_lower = state.name.lower()
                    if state_name_lower not in seen_names:
                        status_tag = " [Canceled]" if getattr(state, "event_canceled", False) else " [Active State / Website]"
                        display_name = f"{state.name}{status_tag}"[:100]
                        if not current or current.lower() in display_name.lower():
                            choices.append(app_commands.Choice(name=display_name, value=state.name))

        return choices[:25]

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

    @event_group.command(
        name="cancel",
        description="Admin: Cancel and remove an upcoming scheduled event from Discord and the website schedule.",
    )
    @app_commands.describe(
        event="The scheduled tournament event or active tournament to cancel and remove"
    )
    @is_event_admin()
    async def cancel_event(self, interaction: discord.Interaction, event: str):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        clean_event = event.strip()
        clean_event_lower = clean_event.lower()

        target_event = None
        for ev in getattr(guild, "scheduled_events", []):
            if (
                str(ev.id) == clean_event
                or ev.name.lower() == clean_event_lower
                or clean_event_lower in ev.name.lower()
            ):
                target_event = ev
                break

        state = self.service.get_state(guild.id)
        is_state_match = (
            state
            and state.name
            and (
                clean_event_lower == state.name.lower()
                or clean_event_lower in state.name.lower()
                or state.name.lower() in clean_event_lower
                or (state.event_id and str(state.event_id) == clean_event)
                or (target_event and target_event.name.lower() == state.name.lower())
            )
        )

        if not target_event and not is_state_match:
            await interaction.response.send_message(
                f"❌ Could not find a scheduled event or active tournament matching `{event}`.",
                ephemeral=True,
            )
            return

        event_name = target_event.name if target_event else (state.name if state else clean_event)

        # 1. Delete Discord scheduled event if found
        discord_deleted = False
        if target_event:
            try:
                await target_event.delete(reason=f"Canceled by {interaction.user} via /event cancel")
                discord_deleted = True
            except Exception as exc:
                logger.warning("Could not delete Discord scheduled event %s (may already be ended): %s", target_event.id, exc)

        # 2. Mark event canceled in tournament state and clear schedule so website removes it
        if state:
            self.service.cancel_event(guild.id)

        banner_status = "Removed" if discord_deleted else "Already offline / ended"
        embed = discord.Embed(
            title="🗑️ Tournament Event Canceled",
            description=(
                f"**Event:** `{event_name}`\n"
                f"**Action:** Removed from Discord server events and the website upcoming schedule.\n\n"
                f"• **Discord Server Banner:** {banner_status}\n"
                f"• **Website Feed:** [unitedduelingamity.org/tournaments.html](https://unitedduelingamity.org/tournaments.html) will no longer list this event under Upcoming."
            ),
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Event Operations")
        await interaction.response.send_message(embed=embed)

    @cancel_event.autocomplete("event")
    async def cancel_event_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._scheduled_events_autocomplete(interaction, current)

    @event_group.command(
        name="clear-upcoming",
        description="Admin: Remove all upcoming events from the website schedule and reset event status.",
    )
    @is_event_admin()
    async def clear_upcoming_events(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        # 1. Cancel Discord scheduled events
        canceled_count = 0
        for ev in getattr(guild, "scheduled_events", []):
            try:
                await ev.delete(reason=f"Cleared by {interaction.user} via /event clear-upcoming")
                canceled_count += 1
            except Exception:
                pass

        # 2. Reset active tournament state
        state = self.service.get_state(guild.id)
        if state:
            self.service.cancel_event(guild.id)

        embed = discord.Embed(
            title="🧹 Website Upcoming Schedule Cleared",
            description=(
                f"Successfully cleared upcoming events from the website schedule!\n\n"
                f"• **Discord Server Events:** `{canceled_count}` removed\n"
                f"• **Website Feed:** [unitedduelingamity.org/tournaments.html](https://unitedduelingamity.org/tournaments.html) upcoming schedule cleared."
            ),
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Event Operations")
        await interaction.response.send_message(embed=embed)

    @event_group.command(
        name="complete",
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

        clean_event = event.strip()
        clean_event_lower = clean_event.lower()

        target_event = None
        for ev in getattr(guild, "scheduled_events", []):
            if (
                str(ev.id) == clean_event
                or ev.name.lower() == clean_event_lower
                or clean_event_lower in ev.name.lower()
            ):
                target_event = ev
                break

        state = self.service.get_state(guild.id)
        event_name = (
            target_event.name
            if target_event
            else (
                state.name
                if state and (clean_event_lower in state.name.lower() or state.name.lower() in clean_event_lower)
                else clean_event
            )
        )
        event_date = (
            target_event.start_time.strftime("%Y-%m-%d")
            if target_event and target_event.start_time
            else (
                state.start_time[:10]
                if state and state.start_time
                else datetime.now(timezone.utc).strftime("%Y-%m-%d")
            )
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
                await target_event.delete(reason=f"Concluded by {interaction.user} via /event complete")
            except Exception as exc:
                logger.debug("Could not remove concluded scheduled event: %s", exc)

        # Remove concluded event from upcoming website schedule and reset state event
        if state:
            self.service.cancel_event(guild.id)
            state.main_open = False
            state.subs_open = False
            state.checkin_open = False
            self.service._persist(guild.id)

        # Also ensure all matching states in memory/disk are marked concluded
        if hasattr(self.service, "_states"):
            for gid, s in list(self.service._states.items()):
                if s.name.lower() == event_name.lower():
                    s.event_canceled = True
                    s.event_id = None
                    s.start_time = None
                    s.start_timestamp = None
                    s.main_open = False
                    s.subs_open = False
                    s.checkin_open = False
                    self.service._persist(gid)

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

    @event_group.command(
        name="remove-past-result",
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
