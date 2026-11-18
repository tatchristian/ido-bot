"""
Root configuration, channel routing, and panel poster commands:
/config, /set-channel, /post, and legacy prefix poster fallbacks.
"""

from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from utils.tournament_embeds import (
    build_bracket_embed,
    build_config_embed,
    build_staff_guide_embed,
    build_staff_panel_embed,
)
from utils.tournament_views import (
    TournamentBracketPanelView,
    TournamentEventPanelView,
    TournamentStaffGuideView,
    TournamentStaffPanelView,
    check_is_event_admin,
    check_is_tournament_admin,
    is_tournament_admin,
)

from .constants import PANEL_CHOICES


class TournamentConfigMixin:
    """Server-wide configuration dashboard, single channel setter, and interactive panel poster."""

    @app_commands.command(
        name="config",
        description="View active server roles, channels, bracket limits, and schedule.",
    )
    async def config_cmd(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)
        embed = build_config_embed(state, guild=interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="set-channel",
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
        if tgt in ("reg", "registration", "checkin", "sub", "subs") and getattr(channel, "category", None) and ctx.guild:
            await self._sync_category_region_permissions(ctx.guild, category=channel.category)
        await ctx.send(f"✅ **{tname}** updated to {channel.mention}.")

    @app_commands.command(
        name="post",
        description="[Admin] Deploy an interactive control panel, registration hub, or portal.",
    )
    @app_commands.describe(
        panel="The interactive panel to post",
        channel="Target text channel (defaults to current or configured channel)",
    )
    @app_commands.choices(panel=PANEL_CHOICES)
    @is_tournament_admin()
    async def post_panel_cmd(
        self,
        interaction: discord.Interaction,
        panel: app_commands.Choice[str],
        channel: Optional[discord.TextChannel] = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        state = self.service.get_state(guild_id)
        val = panel.value

        if val == "staff":
            target = channel or interaction.channel
            if not isinstance(target, discord.TextChannel):
                await interaction.response.send_message("❌ Target must be a text channel.", ephemeral=True)
                return
            embed = build_staff_panel_embed()
            view = TournamentStaffPanelView()
            msg = await target.send(embed=embed, view=view)
            state.staff_channel_id = target.id
            state.staff_message_id = msg.id
            self.service._persist(guild_id)
            await interaction.response.send_message(f"✅ Staff Operations Center posted to {target.mention}!", ephemeral=True)

        elif val == "guide":
            target = channel or interaction.channel
            if not isinstance(target, discord.TextChannel):
                await interaction.response.send_message("❌ Target must be a text channel.", ephemeral=True)
                return
            embed = build_staff_guide_embed(section="overview")
            view = TournamentStaffGuideView(current_section="overview")
            msg = await target.send(embed=embed, view=view)
            state.guide_channel_id = target.id
            state.guide_message_id = msg.id
            self.service._persist(guild_id)
            await interaction.response.send_message(f"✅ Staff Operations Guide posted to {target.mention}!", ephemeral=True)

        elif val == "reg":
            target = channel or (interaction.guild.get_channel(state.registration_channel_id) if state.registration_channel_id else None) or interaction.channel
            if not isinstance(target, discord.TextChannel):
                await interaction.response.send_message("❌ Target must be a valid text channel.", ephemeral=True)
                return
            perms = target.permissions_for(interaction.guild.me)
            if not perms.send_messages or not perms.embed_links:
                await interaction.response.send_message(f"❌ Missing Send Messages or Embed Links permission in {target.mention}.", ephemeral=True)
                return
            await self._post_or_update_registration_panel(interaction.guild, target)
            await interaction.response.send_message(f"✅ Player Registration Hub posted to {target.mention}!", ephemeral=True)

        elif val == "subs":
            target = channel or (interaction.guild.get_channel(state.subs_channel_id) if state.subs_channel_id else None) or interaction.channel
            if not isinstance(target, discord.TextChannel):
                await interaction.response.send_message("❌ Target must be a valid text channel.", ephemeral=True)
                return
            perms = target.permissions_for(interaction.guild.me)
            if not perms.send_messages or not perms.embed_links:
                await interaction.response.send_message(f"❌ Missing Send Messages or Embed Links permission in {target.mention}.", ephemeral=True)
                return
            await self._post_or_update_subs_panel(interaction.guild, target)
            await interaction.response.send_message(f"✅ Standby Substitute Hub posted to {target.mention}!", ephemeral=True)

        elif val == "checkin":
            target = channel or (interaction.guild.get_channel(state.checkin_channel_id) if state.checkin_channel_id else None) or interaction.channel
            if not isinstance(target, discord.TextChannel):
                await interaction.response.send_message("❌ Target must be a valid text channel.", ephemeral=True)
                return
            perms = target.permissions_for(interaction.guild.me)
            if not perms.send_messages or not perms.embed_links:
                await interaction.response.send_message(f"❌ Missing Send Messages or Embed Links permission in {target.mention}.", ephemeral=True)
                return
            await self._post_or_update_checkin_panel(interaction.guild, target)
            await interaction.response.send_message(f"✅ Tournament Check-In Hub posted to {target.mention}!", ephemeral=True)

        elif val == "bracket":
            target = channel or (interaction.guild.get_channel(state.bracket_channel_id) if state.bracket_channel_id else None) or interaction.channel
            if not isinstance(target, discord.TextChannel):
                await interaction.response.send_message("❌ Target must be a valid text channel.", ephemeral=True)
                return
            perms = target.permissions_for(interaction.guild.me)
            if not perms.send_messages or not perms.embed_links:
                await interaction.response.send_message(f"❌ Missing Send Messages or Embed Links permission in {target.mention}.", ephemeral=True)
                return
            bracket = self.service.get_bracket(guild_id)
            view = TournamentBracketPanelView(self.service, guild_id=guild_id, section="winners", round_num=1)
            embed, file = view.get_render_payload()
            msg = await target.send(embed=embed, file=file, view=view)
            view.message = msg
            state.bracket_channel_id = target.id
            state.bracket_message_id = msg.id
            self.service._persist(guild_id)
            await interaction.response.send_message(f"✅ Live Tournament Bracket Panel posted to {target.mention}!", ephemeral=True)

        elif val == "event_scheduler":
            target = channel or interaction.channel
            if not isinstance(target, discord.TextChannel):
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
            panel_embed.set_footer(text=f"{config.organization_name} • Tournament Operations")
            view = TournamentEventPanelView()
            msg = await target.send(embed=panel_embed, view=view)
            state.event_channel_id = target.id
            state.event_message_id = msg.id
            self.service._persist(guild_id)
            await interaction.response.send_message(f"✅ Tournament event scheduler panel posted in {target.mention}!", ephemeral=True)

        elif val == "clan_submit":
            clan_cog = self.bot.get_cog("ClanShowcase") or self.bot.get_cog("ClanShowcaseCog")
            if clan_cog and hasattr(clan_cog, "post_clan_submission_panel"):
                await clan_cog.post_clan_submission_panel(interaction, channel=channel)
            else:
                await interaction.response.send_message("❌ Clan showcase system is currently unavailable.", ephemeral=True)

        elif val == "clan_roles":
            clan_cog = self.bot.get_cog("ClanShowcase") or self.bot.get_cog("ClanShowcaseCog")
            if clan_cog and hasattr(clan_cog, "post_clan_role_panel"):
                await clan_cog.post_clan_role_panel(interaction, channel=channel)
            else:
                await interaction.response.send_message("❌ Clan showcase system is currently unavailable.", ephemeral=True)

    @commands.command(name="post_event_scheduler_panel")
    async def post_event_scheduler_panel_prefix(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """Prefix command fallback (!post_event_scheduler_panel)."""
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a server.")
            return

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
        msg = await target_chan.send(embed=panel_embed, view=view)
        state = self.service.get_state(ctx.guild.id)
        state.event_channel_id = target_chan.id
        state.event_message_id = msg.id
        self.service._persist(ctx.guild.id)
        await ctx.send(f"✅ Tournament event scheduler panel posted in {target_chan.mention}!")

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
        msg = await target_channel.send(embed=embed, view=view)
        state = self.service.get_state(ctx.guild.id)
        state.staff_channel_id = target_channel.id
        state.staff_message_id = msg.id
        self.service._persist(ctx.guild.id)
        if target_channel != ctx.channel:
            await ctx.send(f"✅ Tournament Staff Operations Panel posted to {target_channel.mention}!")

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
