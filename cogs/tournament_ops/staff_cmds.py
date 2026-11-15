"""
Tournament Staff Management Mixin.
Handles tournament administration commands under the '/t' group and matching prefix fallbacks.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import io
import logging
import re
from typing import List, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands

import config
from services.tournament_service import Participant, TournamentService
from services.website_sync_service import parse_event_datetime
from services.server_builder import (
    UndoTournamentSectionView,
    build_tournament_section,
    delete_tournament_section,
)
from utils.tournament_embeds import (
    build_roster_embed,
    build_staff_guide_embed,
    build_status_embed,
    build_tournament_reminder_embed,
)
from utils.tournament_views import (
    TournamentStaffGuideView,
    check_is_tournament_admin,
    is_server_admin,
    is_tournament_admin,
    is_tournament_admin_prefix,
)

from .constants import (
    ANNOUNCE_TARGET_CHOICES,
    EXPORT_FORMAT_CHOICES,
    EXPORT_TARGET_CHOICES,
    REGION_CHOICES,
    REGION_FILTER_CHOICES,
    TIMEZONE_CHOICES,
    WEAPON_CHOICES,
)

logger = logging.getLogger(__name__)


class TournamentStaffMixin:
    """Tournament staff and bracket administration commands."""

    t_group = app_commands.Group(name="t", description="Tournament staff and bracket management")

    @t_group.command(
        name="open",
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
                    "• Use `/register` to sign up for the main bracket.\n"
                    "• Use `/unregister` if you need to withdraw and free your slot.\n"
                    "• Use `/status` to view open slots, regions & weapons."
                    + ("\n• Use `/sub` to join the standby substitute queue." if open_subs else "")
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

    @t_group.command(
        name="close",
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

    @t_group.command(
        name="open-subs",
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
                "• Use `/sub` to enter the standby substitute queue.\n"
                "• Use `/sub-unregister` to leave the queue.\n"
                "• Substitutes are called up in order to replace no-show players on tournament day!"
            ),
            inline=False,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @t_group.command(
        name="close-subs",
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

    @t_group.command(
        name="checkin-open",
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
                "• Main bracket players: use `/checkin` to confirm your attendance.\n"
                "• Standby substitutes: use `/sub-checkin` to confirm you are online and ready for call-ups.\n"
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

    @t_group.command(
        name="checkin-close",
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

    @t_group.command(
        name="kick",
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

    @t_group.command(
        name="force-reg",
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

    @t_group.command(
        name="promote",
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

    @t_group.command(
        name="set-limit",
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

    @t_group.command(
        name="set-regions",
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

    @t_group.command(
        name="set-weapons",
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

    @t_group.command(
        name="set-admin-role",
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

    @t_group.command(
        name="set-event-role",
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
                    f"and website sync commands (`/event create`, `/event cancel`, "
                    f"`/event complete`, `/event remove-past-result`, `/post panel:event_scheduler`).\n\n"
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

    @t_group.command(
        name="set-role",
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
                f"• `/t announce` will ping {role.mention} instead of spamming individual user tags.\n"
                + (f"• Assigned to `{assigned_count}` existing participant(s)." if assigned_count > 0 else "")
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @t_group.command(
        name="set-time",
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

    @t_group.command(
        name="test-reminder",
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

    @t_group.command(
        name="announce",
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

    @t_group.command(
        name="export",
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

    @t_group.command(
        name="bulk-reg",
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

    @t_group.command(
        name="clear",
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

    @t_group.command(
        name="setup-section",
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
                    f"• Registrations: {reg_mention} *(🔒 Locked until `/t open`)*\n"
                    f"• Substitutes: {sub_mention} *(🔒 Locked until `/t open-subs`)*\n"
                    f"• Check-in: {chk_mention} *(🔒 Locked until `/t checkin-open`)*"
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

    @t_group.command(
        name="remove-section",
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

    @t_group.command(
        name="staff-checkin",
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

