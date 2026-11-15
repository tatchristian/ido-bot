"""
Bot state persistence, channel/role backup and disaster recovery commands:
/state save, /state restore, /state status, /state save-roster, /state restore-roster.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from utils.tournament_views import (
    is_tournament_admin,
    is_tournament_admin_prefix,
)


class TournamentStateMixin:
    """State persistence, JSON snapshots, and disaster recovery commands."""

    state_group = app_commands.Group(
        name="state", description="Bot channel, role, and roster persistence & recovery"
    )

    @state_group.command(
        name="save-roster",
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

    @state_group.command(
        name="restore-roster",
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
            m_id = re.search(r"<@!?(\d+)>", mention_str)
            if m_id:
                member_by_id = guild.get_member(int(m_id.group(1)))
                if member_by_id:
                    return member_by_id.id, member_by_id.mention
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
            m_id = re.search(r"<@!?(\d+)>", mention_str)
            if m_id:
                member_by_id = ctx.guild.get_member(int(m_id.group(1)))
                if member_by_id:
                    return member_by_id.id, member_by_id.mention
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

    @state_group.command(
        name="save",
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

    @state_group.command(
        name="restore",
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
                snapshot_service.auto_discover_channels(interaction.guild, self.service, clan_service)
                snapshot_service.save_snapshot(guild_id, self.service, clan_service)
                snapshot = snapshot_service.capture_snapshot(guild_id, self.service, clan_service)
            else:
                await interaction.response.send_message("❌ `saved_state.json` preset file was not found.", ephemeral=True)
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
            clan_cog = self.bot.get_cog("ClanShowcase") or self.bot.get_cog("ClanShowcaseCog")
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
                clan_cog = self.bot.get_cog("ClanShowcase") or self.bot.get_cog("ClanShowcaseCog")
                if clan_cog and hasattr(clan_cog, "_refresh_clan_role_panel"):
                    await clan_cog._refresh_clan_role_panel(ctx.guild)
                msg += " (Panels refreshed)."
            await ctx.send(msg)
        except Exception as e:
            await ctx.send(f"❌ Failed to restore state: {e}")

    @state_group.command(
        name="status",
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
            saved = snapshot_service.load_snapshot(guild_id=guild_id)
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
            color=0x34495E,
        )
        embed.set_footer(text=f"{config.organization_name} • System Diagnostics")
        await interaction.response.send_message(embed=embed, ephemeral=True)
