"""
Interactive Discord Views, Modals, Selects, and Permission Predicates for UDA Tournaments.
Tier 2 UI component module: depends on Tier 0 (services/config) and Tier 1 (embed builders).
Decoupled from TournamentCog via runtime client cog lookup (no static cog imports).
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from services.tournament_service import (
    Participant,
    TournamentService,
    TournamentState,
)
from services.website_sync_service import (
    parse_combined_event_datetime,
    parse_duration_and_location,
    parse_event_datetime,
)
from utils.tournament_embeds import (
    build_help_embed,
    build_roster_embed,
    build_staff_guide_embed,
    build_status_embed,
)

logger = logging.getLogger(__name__)


def check_is_tournament_admin(
    user: Union[discord.User, discord.Member],
    guild: Optional[discord.Guild],
    client: Optional[commands.Bot] = None,
) -> bool:
    """Synchronous predicate to check if a user is server owner, admin, or has tournament admin role or higher."""
    if guild is None:
        return False
    if user.id == guild.owner_id:
        return True
    if hasattr(user, "guild_permissions") and user.guild_permissions.administrator:
        return True
    if not isinstance(user, discord.Member):
        return False

    cog = client.get_cog("TournamentCog") if client else None
    target_role_id = None
    target_role_name = config.admin_role_name
    if cog and hasattr(cog, "service"):
        guild_state = cog.service.get_state(guild.id)
        target_role_id = guild_state.admin_role_id or config.admin_role_id
        target_role_name = guild_state.admin_role_name or config.admin_role_name
    else:
        target_role_id = config.admin_role_id

    threshold_role = None
    if target_role_id:
        threshold_role = guild.get_role(target_role_id)

    if not threshold_role and target_role_name:
        target_name_lower = target_role_name.strip().lower()
        threshold_role = discord.utils.find(
            lambda r: r.name.strip().lower() == target_name_lower,
            guild.roles,
        )

    if threshold_role is not None:
        if threshold_role in user.roles:
            return True
        if any(
            r.id == threshold_role.id or r.name.strip().lower() == threshold_role.name.strip().lower()
            for r in user.roles
        ):
            return True

    return False


def is_tournament_admin():
    """Custom check for administrator permission or designated Tournament Admin role or higher in hierarchy."""
    async def predicate(interaction: discord.Interaction) -> bool:
        return check_is_tournament_admin(interaction.user, interaction.guild, interaction.client)

    return app_commands.check(predicate)


def is_tournament_admin_prefix():
    """Custom check for commands.command prefix commands."""
    async def predicate(ctx: commands.Context) -> bool:
        return check_is_tournament_admin(ctx.author, ctx.guild, ctx.bot)

    return commands.check(predicate)


def check_is_event_admin(
    user: Union[discord.User, discord.Member],
    guild: Optional[discord.Guild],
    client: Optional[commands.Bot] = None,
) -> bool:
    """Synchronous predicate to check if a user is server owner, admin, has Manage Events/Guild,
    or holds the designated Event & Website role.
    Tournament Referee / Tournament Admin roles alone do NOT grant this permission."""
    if guild is None:
        return False
    if user.id == guild.owner_id:
        return True
    if hasattr(user, "guild_permissions"):
        perms = user.guild_permissions
        if perms.administrator or perms.manage_events or perms.manage_guild:
            return True
    if not isinstance(user, discord.Member):
        return False

    cog = client.get_cog("TournamentCog") if client else None
    target_role_id = None
    target_role_name = getattr(config, "event_role_name", None)
    if cog and hasattr(cog, "service"):
        guild_state = cog.service.get_state(guild.id)
        target_role_id = getattr(guild_state, "event_role_id", None) or getattr(config, "event_role_id", None)
        target_role_name = getattr(guild_state, "event_role_name", None) or getattr(config, "event_role_name", None)
    else:
        target_role_id = getattr(config, "event_role_id", None)

    if target_role_id:
        target_role = guild.get_role(target_role_id)
        if target_role and target_role in user.roles:
            return True

    if target_role_name:
        target_name_lower = target_role_name.strip().lower()
        if any(r.name.strip().lower() == target_name_lower for r in user.roles):
            return True

    return False


def is_event_admin():
    """Custom check for Discord Scheduled Events and Website Sync.
    Requires Server Administrator, Server Ownership, Manage Events, Manage Guild,
    or the designated Event & Website role.
    Tournament referee / tournament admin roles alone do NOT grant this.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        return check_is_event_admin(interaction.user, interaction.guild, interaction.client)

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
    """Interactive navigation buttons for the /help command."""

    def __init__(self, is_admin: bool = False, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.is_admin = is_admin

    @discord.ui.button(label="👥 Participants", style=discord.ButtonStyle.primary, custom_id="help_participants", row=0)
    async def participant_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_is_admin = check_is_tournament_admin(interaction.user, interaction.guild, interaction.client)
        embed = build_help_embed("participants", is_admin=user_is_admin)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🛠️ Operations", style=discord.ButtonStyle.secondary, custom_id="help_admin", row=0)
    async def admin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_is_admin = check_is_tournament_admin(interaction.user, interaction.guild, interaction.client)
        if not user_is_admin:
            await interaction.response.send_message(
                "❌ **Access Denied**: Tournament Operations controls are restricted to administrators and Tournament Staff.",
                ephemeral=True,
            )
            return
        embed = build_help_embed("admin", is_admin=True)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⚙️ Setup", style=discord.ButtonStyle.secondary, custom_id="help_setup", row=0)
    async def setup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_is_admin = check_is_tournament_admin(interaction.user, interaction.guild, interaction.client)
        if not user_is_admin:
            await interaction.response.send_message(
                "❌ **Access Denied**: Server Setup & Configuration commands are restricted to administrators and Tournament Staff.",
                ephemeral=True,
            )
            return
        embed = build_help_embed("setup", is_admin=True)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⚔️ Rules & Weapons", style=discord.ButtonStyle.secondary, custom_id="help_weapons", row=1)
    async def weapons_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_is_admin = check_is_tournament_admin(interaction.user, interaction.guild, interaction.client)
        embed = build_help_embed("weapons_regions", is_admin=user_is_admin)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🏛️ Clan Showcase", style=discord.ButtonStyle.secondary, custom_id="help_clans", row=1)
    async def clans_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_is_admin = check_is_tournament_admin(interaction.user, interaction.guild, interaction.client)
        embed = build_help_embed("clans", is_admin=user_is_admin)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="📅 Events & Website", style=discord.ButtonStyle.secondary, custom_id="help_events_sync", row=1)
    async def events_sync_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_is_event_admin = check_is_event_admin(interaction.user, interaction.guild, interaction.client)
        if not user_is_event_admin:
            await interaction.response.send_message(
                "❌ **Access Denied**: Event Scheduling and Live Website Sync commands are restricted to Server Staff and Event Managers.",
                ephemeral=True,
            )
            return
        embed = build_help_embed("events_sync", is_admin=True)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="📖 View All", style=discord.ButtonStyle.success, custom_id="help_all", row=1)
    async def all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_is_admin = check_is_tournament_admin(interaction.user, interaction.guild, interaction.client)
        embed = build_help_embed("all", is_admin=user_is_admin)
        await interaction.response.edit_message(embed=embed, view=self)


class TournamentEventModal(discord.ui.Modal, title="Schedule Tournament Event"):
    """
    Interactive modal popup for staff to schedule Discord events with website sync.
    """

    def __init__(self):
        super().__init__()
        self.event_title = discord.ui.TextInput(
            label="Tournament / Event Title",
            placeholder="e.g. UDA Winter Championship 2026",
            style=discord.TextStyle.short,
            max_length=100,
            required=True,
        )
        self.date_time = discord.ui.TextInput(
            label="Date & Time (with Timezone)",
            placeholder="e.g. 2026-11-15 18:00 EST or This Weekend 18:00 IST",
            style=discord.TextStyle.short,
            max_length=100,
            required=True,
        )
        self.duration_location = discord.ui.TextInput(
            label="Duration & Location",
            placeholder="e.g. 2 hours | Tournament Hub or Weekend | Arena",
            default=f"2 hours | {config.organization_name} Tournament Hub",
            style=discord.TextStyle.short,
            max_length=100,
            required=False,
        )
        self.description = discord.ui.TextInput(
            label="Description, Rules & Format",
            placeholder="Format, weapon rules, check-in instructions, prize info...",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False,
        )

        self.add_item(self.event_title)
        self.add_item(self.date_time)
        self.add_item(self.duration_location)
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This form must be used within a server.", ephemeral=True)
            return

        bot_member = guild.me
        if not bot_member or not bot_member.guild_permissions.manage_events:
            await interaction.response.send_message(
                "❌ The bot is missing the **Manage Events** permission to create Discord scheduled events.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=False)

        # 1. Parse Combined Date & Time
        valid, start_time, err = parse_combined_event_datetime(self.date_time.value)
        if not valid or not start_time:
            await interaction.followup.send(f"❌ {err}", ephemeral=True)
            return

        # 2. Parse Duration & Location
        dur, loc_text = parse_duration_and_location(self.duration_location.value)
        end_time = start_time + timedelta(hours=dur)

        # 3. Create Discord Scheduled Event
        event_name = self.event_title.value.strip()[:100]
        event_desc = (self.description.value or f"Official {config.organization_name} Tournament Event").strip()[:1000]

        try:
            scheduled_event = await guild.create_scheduled_event(
                name=event_name,
                description=event_desc,
                start_time=start_time,
                end_time=end_time,
                location=loc_text[:100],
                entity_type=discord.EntityType.external,
                privacy_level=discord.PrivacyLevel.guild_only,
                reason=f"Scheduled by {interaction.user} via Tournament Event Modal",
            )
        except Exception as exc:
            logger.error("Failed to create Discord scheduled event via modal: %s", exc, exc_info=True)
            await interaction.followup.send(
                f"❌ Failed to create Discord scheduled event: {exc}", ephemeral=True
            )
            return

        # 4. Automatic Website Feed Publication
        website_sync_status = (
            "✅ **Live on Website!**\n"
            "Automatically published to the live public schedule on [unitedduelingamity.org/tournaments.html](https://unitedduelingamity.org/tournaments.html)."
        )

        # 5. Build Response Embed
        embed = discord.Embed(
            title="📅 Tournament Event Scheduled!",
            description=(
                f"**Event:** [{scheduled_event.name}]({scheduled_event.url})\n"
                f"**Date & Time:** <t:{int(start_time.timestamp())}:F> (<t:{int(start_time.timestamp())}:R>)\n"
                f"**Location:** 📍 `{loc_text}`\n\n"
                f"{scheduled_event.description}"
            ),
            color=config.embed_color,
        )
        embed.add_field(
            name="📌 Discord Event Banner",
            value=f"Listed at the **top of the server**! Members can click **[Interested]({scheduled_event.url})** to receive Discord reminders before it starts.",
            inline=False,
        )
        embed.add_field(
            name="🌐 Website Feed (unitedduelingamity.org)",
            value=website_sync_status,
            inline=False,
        )
        embed.set_footer(text=f"{config.organization_name} • Event Operations")

        await interaction.followup.send(embed=embed)


class TournamentEventPanelView(discord.ui.View):
    """
    Persistent view with the 'Schedule Tournament Event' button and 'Website Sync Status' button.
    Placed in staff or operations channels for 1-click popup form scheduling.
    """

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📅 Schedule Tournament Event",
        style=discord.ButtonStyle.primary,
        custom_id="btn_schedule_tournament_event",
    )
    async def schedule_event_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ This button can only be used in a server.", ephemeral=True)
            return

        if not check_is_event_admin(interaction.user, interaction.guild, interaction.client):
            await interaction.response.send_message(
                "❌ You need Manage Events, Administrator permissions, or the Event & Website role to schedule official events.",
                ephemeral=True,
            )
            return

        modal = TournamentEventModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="🌐 Website Feed Status",
        style=discord.ButtonStyle.secondary,
        emoji="📡",
        custom_id="btn_check_website_sync",
    )
    async def check_website_sync_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="🌐 UDA Website Live Feed Status",
            description=(
                "✅ **Website REST API is Online & Operational!**\n\n"
                "Duke serves live event and leaderboard data directly to **[unitedduelingamity.org](https://unitedduelingamity.org)**.\n\n"
                "• 📅 **Tournaments Feed:** [View Live Events](https://ido-bot.onrender.com/tournaments)\n"
                "• 🛡️ **Clan Leaderboard:** [View Live Clans](https://ido-bot.onrender.com/leaderboard)\n"
                "• ⚔️ **Player Roster:** [View Live Players](https://ido-bot.onrender.com/players)\n\n"
                "*All tournaments scheduled in Discord and approved clan profiles appear on the website automatically!*"
            ),
            color=config.embed_color,
        )
        embed.set_footer(text=f"{config.organization_name} • Web Integration")
        await interaction.followup.send(embed=embed, ephemeral=True)


class TournamentStaffGuideSelect(discord.ui.Select):
    def __init__(self, current_section: str = "overview"):
        options = [
            discord.SelectOption(
                label="Overview & Directory",
                value="overview",
                emoji="📖",
                description="Staff guide directory and phase overview",
                default=(current_section == "overview"),
            ),
            discord.SelectOption(
                label="Interactive Panels & Hubs",
                value="panels",
                emoji="🎛️",
                description="Staff control center & player registration hubs",
                default=(current_section == "panels"),
            ),
            discord.SelectOption(
                label="Phase 1: Pre-Tournament Setup",
                value="phase_1",
                emoji="1️⃣",
                description="Arena builder, channels, scheduling & auto-roles",
                default=(current_section == "phase_1"),
            ),
            discord.SelectOption(
                label="Phase 2: Registration & Rosters",
                value="phase_2",
                emoji="2️⃣",
                description="Channel locks, bulk register & roster presets",
                default=(current_section == "phase_2"),
            ),
            discord.SelectOption(
                label="Phase 3: Match Day & Reminders",
                value="phase_3",
                emoji="3️⃣",
                description="Automated contestant DMs, check-in & substitute swaps",
                default=(current_section == "phase_3"),
            ),
            discord.SelectOption(
                label="Phase 4: Concluding & Archiving",
                value="phase_4",
                emoji="4️⃣",
                description="Crown champions, Challonge export & bracket wipe",
                default=(current_section == "phase_4"),
            ),
            discord.SelectOption(
                label="Match Day Quick Checklist",
                value="checklist",
                emoji="⚡",
                description="Critical timeline from T-60m to match start",
                default=(current_section == "checklist"),
            ),
            discord.SelectOption(
                label="State & Roster Persistence",
                value="persistence",
                emoji="💾",
                description="Save & restore channels & rosters across git pushes",
                default=(current_section == "persistence"),
            ),
            discord.SelectOption(
                label="Role Permissions Reference",
                value="roles",
                emoji="🛡️",
                description="Tournament Admin vs Event & Website role boundaries",
                default=(current_section == "roles"),
            ),
        ]
        super().__init__(
            placeholder="📑 Choose an operational guide section...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="select_staff_guide_page",
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        embed = build_staff_guide_embed(section=selected)
        view = TournamentStaffGuideView(current_section=selected)
        await interaction.response.edit_message(embed=embed, view=view)


class TournamentStaffGuideView(discord.ui.View):
    """
    Persistent interactive view for navigating the tournament staff operations manual.
    """
    def __init__(self, current_section: str = "overview"):
        super().__init__(timeout=None)
        self.add_item(TournamentStaffGuideSelect(current_section=current_section))


class StaffCreateTournamentModal(discord.ui.Modal, title="Create / Configure Tournament"):
    """
    Dedicated modal to configure tournament parameters (Title, Slots, Regions, Channel)
    without opening registrations immediately.
    """
    def __init__(self, service: TournamentService):
        super().__init__()
        self.service = service
        self.name_input = discord.ui.TextInput(
            label="Tournament Title",
            placeholder="e.g. Asia Tournament 2026",
            default="Official Tournament",
            max_length=100,
            required=True,
        )
        self.slots_input = discord.ui.TextInput(
            label="Max Participant Slots",
            placeholder="16",
            default="16",
            max_length=4,
            required=True,
        )
        self.regions_input = discord.ui.TextInput(
            label="Allowed Regions (comma separated)",
            placeholder="e.g. GLOBAL or ASIA, NA",
            default="GLOBAL",
            max_length=50,
            required=False,
        )
        self.channel_input = discord.ui.TextInput(
            label="Registration Channel (optional)",
            placeholder="e.g. #tournament-registration (leave blank for auto)",
            max_length=100,
            required=False,
        )
        self.add_item(self.name_input)
        self.add_item(self.slots_input)
        self.add_item(self.regions_input)
        self.add_item(self.channel_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id or 0
        slots_str = self.slots_input.value.strip()
        try:
            slots = int(slots_str)
            if slots < 2:
                await interaction.followup.send("❌ Slot capacity must be at least 2.", ephemeral=True)
                return
        except ValueError:
            await interaction.followup.send("❌ Slots must be a valid number.", ephemeral=True)
            return

        name = self.name_input.value.strip() or "Official Tournament"
        regions_raw = self.regions_input.value.strip()
        selected_regions = None
        if regions_raw and regions_raw.upper() != "GLOBAL":
            selected_regions = [r.strip().upper() for r in regions_raw.split(",") if r.strip()]

        # Check if staff specified a custom registration channel
        custom_channel_raw = self.channel_input.value.strip()
        custom_reg_channel = None
        if custom_channel_raw and interaction.guild:
            match = re.search(r"(\d{17,20})", custom_channel_raw)
            if match:
                ch = interaction.guild.get_channel(int(match.group(1)))
                if isinstance(ch, discord.TextChannel):
                    custom_reg_channel = ch
            if not custom_reg_channel:
                clean_target = custom_channel_raw.lower().lstrip("#").strip()
                for ch in interaction.guild.text_channels:
                    ch_clean = ch.name.lower().replace("📝", "").replace("・", "").replace("-", " ").strip()
                    if ch.name.lower() == clean_target or clean_target in ch_clean or clean_target in ch.name.lower():
                        custom_reg_channel = ch
                        break

        # Auto-create participant role if needed
        participant_role = None
        if interaction.guild:
            role_name = f"{name} Participant"[:100]
            participant_role = discord.utils.get(interaction.guild.roles, name=role_name)
            if not participant_role:
                participant_role = discord.utils.get(interaction.guild.roles, name=name[:100])
            if not participant_role and interaction.guild.me.guild_permissions.manage_roles:
                try:
                    participant_role = await interaction.guild.create_role(
                        name=role_name,
                        mentionable=True,
                        reason=f"Auto-created tournament participant role for {name}",
                    )
                except Exception as exc:
                    logger.warning("Could not auto-create role for %s: %s", name, exc)

        p_role_id = participant_role.id if participant_role else None
        p_role_name = participant_role.name if participant_role else None
        reg_ch_id = custom_reg_channel.id if custom_reg_channel else None

        msg = self.service.configure_tournament(
            name=name,
            slots=slots,
            regions=selected_regions,
            participant_role_id=p_role_id,
            participant_role_name=p_role_name,
            registration_channel_id=reg_ch_id,
            guild_id=guild_id,
        )

        cog = interaction.client.get_cog("TournamentCog")
        if cog and hasattr(cog, "_sync_category_region_permissions") and interaction.guild:
            try:
                await cog._sync_category_region_permissions(
                    interaction.guild,
                    regions=selected_regions,
                    reason=f"Tournament configured for {name}",
                )
            except Exception as cat_exc:
                logger.warning("Could not sync category region permissions on modal submit: %s", cat_exc)

        embed = discord.Embed(
            title="⚙️ Tournament Created & Configured",
            description=(
                f"{msg}\n"
                f"• **Registration Channel:** {custom_reg_channel.mention if custom_reg_channel else '*Auto-detected / Default*'}\n\n"
                "👉 When ready to open player signups, click **`🟢 Open Registrations`** on the panel!"
            ),
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament Operations")
        await interaction.followup.send(embed=embed, ephemeral=True)


# Backwards compatibility alias
StaffOpenTournamentModal = StaffCreateTournamentModal


class StaffAnnounceModal(discord.ui.Modal, title="Broadcast Announcement"):
    def __init__(self, service: TournamentService):
        super().__init__()
        self.service = service
        self.title_input = discord.ui.TextInput(
            label="Announcement Title",
            placeholder="e.g. Match Bracket Released!",
            default="📢 Tournament Announcement",
            max_length=100,
            required=True,
        )
        self.message_input = discord.ui.TextInput(
            label="Announcement Message",
            placeholder="Type your announcement to all contestants...",
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=True,
        )
        self.ping_input = discord.ui.TextInput(
            label="Ping Participant Role? (yes/no)",
            placeholder="yes or no",
            default="yes",
            max_length=5,
            required=False,
        )
        self.add_item(self.title_input)
        self.add_item(self.message_input)
        self.add_item(self.ping_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id or 0
        state = self.service.get_state(guild_id)

        role_mention = ""
        should_ping = self.ping_input.value.strip().lower() in ("yes", "y", "true", "1")
        if should_ping and interaction.guild and state.participant_role_id:
            role = interaction.guild.get_role(state.participant_role_id)
            if role:
                role_mention = role.mention

        embed = discord.Embed(
            title=f"📢 {self.title_input.value.strip()}",
            description=self.message_input.value.strip(),
            color=config.embed_color,
        )
        embed.set_footer(text=f"{state.name} • Tournament Announcement")

        # Determine target channel (use dedicated announcement channel if configured, otherwise current)
        target_channel = interaction.channel
        if interaction.guild and state.announcement_channel_id:
            configured_channel = interaction.guild.get_channel(state.announcement_channel_id)
            if configured_channel:
                target_channel = configured_channel

        if role_mention:
            await target_channel.send(content=f"🔔 {role_mention}", embed=embed)
        else:
            await target_channel.send(embed=embed)

        await interaction.followup.send(
            f"✅ Announcement successfully broadcasted to {target_channel.mention}!",
            ephemeral=True,
        )


class StaffSetTimeModal(discord.ui.Modal, title="Configure Tournament Match Schedule"):
    def __init__(self, service: TournamentService):
        super().__init__()
        self.service = service
        self.date_input = discord.ui.TextInput(
            label="Match Date (YYYY-MM-DD or Weekend)",
            placeholder="e.g. 2026-11-15 or This Weekend / Saturday",
            max_length=30,
            required=True,
        )
        self.time_input = discord.ui.TextInput(
            label="Match Time (HH:MM 24-hr or 12-hr)",
            placeholder="e.g. 18:00 or 6:00 PM",
            max_length=15,
            required=True,
        )
        self.timezone_input = discord.ui.TextInput(
            label="Timezone Code (e.g. IST, EST, UTC, JST)",
            placeholder="e.g. IST, EST, UTC, JST, CET",
            default="EST",
            max_length=15,
            required=False,
        )
        self.add_item(self.date_input)
        self.add_item(self.time_input)
        self.add_item(self.timezone_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        date_str = self.date_input.value.strip()
        time_str = self.time_input.value.strip()
        tz_str = self.timezone_input.value.strip().upper() or "EST"

        valid, start_dt, err = parse_event_datetime(date_str, time_str, tz_str)
        if not valid or not start_dt:
            await interaction.followup.send(f"❌ {err}", ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        ts = int(start_dt.timestamp())
        msg = self.service.set_tournament_time(
            start_time=start_dt.isoformat(),
            start_timestamp=ts,
            guild_id=guild_id,
        )

        embed = discord.Embed(
            title="⏰ Tournament Match Schedule Configured",
            description=(
                f"{msg}\n\n"
                f"**Configured Start Time:** <t:{ts}:F> (<t:{ts}:R>)\n"
                f"**Contestant Reminders:** Enabled! Contestants will automatically receive a personal DM "
                f"on the morning of the tournament and 30 minutes before match time."
            ),
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament Operations")
        await interaction.followup.send(embed=embed, ephemeral=True)


class TournamentStaffPanelView(discord.ui.View):
    """
    Persistent 1-click Tournament Staff Operations Panel.
    Can be posted to staff channels for rapid bracket and match day operations.
    """

    def __init__(self):
        super().__init__(timeout=None)

    def _get_service(self, interaction: discord.Interaction) -> TournamentService | None:
        srv = getattr(interaction.client, "tournament_service", None)
        if not srv:
            cog = interaction.client.get_cog("TournamentCog")
            if cog:
                srv = getattr(cog, "service", None)
        return srv

    @discord.ui.button(
        label="Create Tournament",
        emoji="⚙️",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_staff_create_tournament",
        row=0,
    )
    async def create_tournament_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_is_tournament_admin(interaction.user, interaction.guild, interaction.client):
            await interaction.response.send_message(
                "❌ You need the Tournament Admin role or Administrator permissions to use staff panel controls.",
                ephemeral=True,
            )
            return

        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service is unavailable.", ephemeral=True)
            return

        modal = StaffCreateTournamentModal(service)
        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)
        if state.name:
            modal.name_input.default = state.name
        if state.max_slots:
            modal.slots_input.default = str(state.max_slots)
        if state.allowed_regions:
            modal.regions_input.default = ", ".join(state.allowed_regions)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Open Registrations",
        emoji="🟢",
        style=discord.ButtonStyle.success,
        custom_id="btn_staff_open_bracket",
        row=0,
    )
    async def open_bracket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_is_tournament_admin(interaction.user, interaction.guild, interaction.client):
            await interaction.response.send_message(
                "❌ You need the Tournament Admin role or Administrator permissions to use staff panel controls.",
                ephemeral=True,
            )
            return

        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service is unavailable.", ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)

        if state.main_open:
            await interaction.response.send_message(
                f"ℹ️ Main bracket registrations for **{state.name}** are already **OPEN**.",
                ephemeral=True,
            )
            return

        # Open registrations without overriding sub status
        service.open_tournament(open_subs=None, guild_id=guild_id)

        def find_target_channel(channel_id: int | None, keywords: list[str]) -> discord.TextChannel | None:
            if not interaction.guild:
                return None
            if channel_id:
                ch = interaction.guild.get_channel(channel_id)
                if isinstance(ch, discord.TextChannel):
                    return ch
            for ch in interaction.guild.text_channels:
                # Strip non-alphanumeric characters (emojis, dots, bullet points, hyphens)
                ch_name_clean = re.sub(r"[^\w\s]", " ", ch.name.lower())
                if any(re.sub(r"[^\w\s]", " ", kw.lower()).strip() in ch_name_clean for kw in keywords):
                    return ch
            return None

        reg_channel = find_target_channel(state.registration_channel_id, ["tournament-registration", "registration", "signup", "sign-up", "register"])
        reg_posted = False

        if interaction.guild:
            cog = interaction.client.get_cog("TournamentCog")
            if cog and hasattr(cog, "_sync_category_region_permissions"):
                await cog._sync_category_region_permissions(
                    interaction.guild,
                    regions=state.allowed_regions,
                    reason=f"Registrations opened for {state.name}",
                )

        if reg_channel and interaction.guild:
            cog = interaction.client.get_cog("TournamentCog")
            if cog and hasattr(cog, "_update_channel_permission"):
                await cog._update_channel_permission(
                    interaction.guild,
                    reg_channel.id,
                    can_send=True,
                    reason=f"Registrations opened for {state.name}",
                )

            if cog and hasattr(cog, "_post_or_update_registration_panel"):
                try:
                    await cog._post_or_update_registration_panel(interaction.guild, reg_channel)
                    reg_posted = True
                except Exception as exc:
                    logger.warning("Could not auto-post registration panel to %s: %s", reg_channel.name, exc)

        status_lines = [
            f"🏆 **{state.name}** registrations are now **OPEN**!\n",
            f"• **Capacity:** `{state.max_slots}` slots",
            f"• **Regions:** `{', '.join(state.allowed_regions) if state.allowed_regions else 'GLOBAL'}`",
            f"• **Registration Channel:** {reg_channel.mention + ' (✅ Live Hub Posted)' if reg_posted else ('⚠️ Could not post' if reg_channel else '*None found (use /set-channel)*')}",
        ]
        embed = discord.Embed(
            title="🟢 Tournament Registrations Opened!",
            description="\n".join(status_lines),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament Operations")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Close Registrations",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="btn_staff_close_bracket",
        row=0,
    )
    async def close_bracket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_is_tournament_admin(interaction.user, interaction.guild, interaction.client):
            await interaction.response.send_message(
                "❌ You need the Tournament Admin role or Administrator permissions to use staff panel controls.",
                ephemeral=True,
            )
            return

        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service is unavailable.", ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)
        if not state.main_open:
            await interaction.response.send_message(
                f"ℹ️ Main bracket registrations for **{state.name}** are already **CLOSED**.",
                ephemeral=True,
            )
            return

        msg = service.close_tournament(guild_id)

        # Dynamically lock registration channel and edit panel
        cog = interaction.client.get_cog("TournamentCog")
        if cog and state.registration_channel_id and interaction.guild:
            if hasattr(cog, "_update_channel_permission"):
                await cog._update_channel_permission(
                    interaction.guild,
                    state.registration_channel_id,
                    can_send=False,
                    reason=f"Registrations closed for {state.name}",
                )
            if hasattr(cog, "_close_registration_panel"):
                await cog._close_registration_panel(interaction.guild)

        embed = discord.Embed(
            title="🔒 Tournament Registrations Closed",
            description=f"{msg}\n\n*Locked by {interaction.user.mention}*",
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament Operations")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Toggle Subs",
        emoji="🛡️",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_staff_toggle_subs",
        row=0,
    )
    async def toggle_subs_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_is_tournament_admin(interaction.user, interaction.guild, interaction.client):
            await interaction.response.send_message(
                "❌ You need the Tournament Admin role or Administrator permissions to use staff panel controls.",
                ephemeral=True,
            )
            return

        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service is unavailable.", ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)

        def find_target_channel(channel_id: int | None, keywords: list[str]) -> discord.TextChannel | None:
            if not interaction.guild:
                return None
            if channel_id:
                ch = interaction.guild.get_channel(channel_id)
                if isinstance(ch, discord.TextChannel):
                    return ch
            for ch in interaction.guild.text_channels:
                # Strip non-alphanumeric characters (emojis, dots, bullet points, hyphens)
                ch_name_clean = re.sub(r"[^\w\s]", " ", ch.name.lower())
                if any(re.sub(r"[^\w\s]", " ", kw.lower()).strip() in ch_name_clean for kw in keywords):
                    return ch
            return None

        subs_channel = find_target_channel(state.subs_channel_id, ["substitutes-bench", "substitute", "subs-bench", "substitutes", "subs"])
        cog = interaction.client.get_cog("TournamentCog")

        if not state.subs_open:
            msg = service.open_subs(guild_id=guild_id)
            subs_posted = False

            if subs_channel and interaction.guild:
                if cog and hasattr(cog, "_update_channel_permission"):
                    await cog._update_channel_permission(
                        interaction.guild,
                        subs_channel.id,
                        can_send=True,
                        reason=f"Substitutes opened for {state.name}",
                    )

                if cog and hasattr(cog, "_post_or_update_subs_panel"):
                    try:
                        await cog._post_or_update_subs_panel(interaction.guild, subs_channel)
                        subs_posted = True
                    except Exception as exc:
                        logger.warning("Could not auto-post substitutes panel to %s: %s", subs_channel.name, exc)

            embed = discord.Embed(
                title="🛡️ Standby Substitute Signups Opened",
                description=(
                    f"{msg}\n\n"
                    f"• **Channel:** {subs_channel.mention + ' (✅ Live Hub Posted)' if subs_posted else ('⚠️ Could not post' if subs_channel else '*None found (use /set-channel)*')}\n\n"
                    f"*Opened by {interaction.user.mention}*"
                ),
                color=0x3498DB,
            )
        else:
            msg = service.close_subs(guild_id=guild_id)
            if subs_channel and interaction.guild:
                if cog and hasattr(cog, "_update_channel_permission"):
                    await cog._update_channel_permission(
                        interaction.guild,
                        subs_channel.id,
                        can_send=False,
                        reason=f"Substitutes closed for {state.name}",
                    )
                if cog and hasattr(cog, "_close_subs_panel"):
                    await cog._close_subs_panel(interaction.guild)

            embed = discord.Embed(
                title="🔒 Standby Substitute Signups Closed",
                description=f"{msg}\n\n*Closed by {interaction.user.mention}*",
                color=0xE67E22,
            )

        # Sync the main registration panel live so its "Substitute Bench:" status updates immediately
        if cog and hasattr(cog, "_update_registration_panel") and interaction.guild:
            try:
                await cog._update_registration_panel(interaction.guild)
            except Exception as sync_exc:
                logger.debug("Could not auto-sync registration panel on sub toggle: %s", sync_exc)

        embed.set_footer(text=f"{config.organization_name} • Tournament Operations")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Toggle Check-In",
        emoji="🎟️",
        style=discord.ButtonStyle.primary,
        custom_id="btn_staff_toggle_checkin",
        row=0,
    )
    async def toggle_checkin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_is_tournament_admin(interaction.user, interaction.guild, interaction.client):
            await interaction.response.send_message(
                "❌ You need the Tournament Admin role or Administrator permissions to use staff panel controls.",
                ephemeral=True,
            )
            return

        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service is unavailable.", ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)

        if not state.checkin_open:
            msg = service.open_checkin(checkin_channel_id=interaction.channel_id, guild_id=guild_id)
            embed = discord.Embed(
                title="🎟️ Tournament Check-In Opened",
                description=(
                    f"{msg}\n\n"
                    f"Contestants can check in using `/checkin` or the Check-In button in registration channels.\n\n"
                    f"*Opened by {interaction.user.mention}*"
                ),
                color=0x2ECC71,
            )
        else:
            msg = service.close_checkin(guild_id=guild_id)
            embed = discord.Embed(
                title="🔒 Tournament Check-In Closed",
                description=f"{msg}\n\n*Closed by {interaction.user.mention}*",
                color=0xE67E22,
            )
        embed.set_footer(text=f"{config.organization_name} • Tournament Operations")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Promote Sub",
        emoji="🔄",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_staff_promote_sub",
        row=1,
    )
    async def promote_sub_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_is_tournament_admin(interaction.user, interaction.guild, interaction.client):
            await interaction.response.send_message(
                "❌ You need the Tournament Admin role or Administrator permissions to use staff panel controls.",
                ephemeral=True,
            )
            return

        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service is unavailable.", ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        success, msg, promoted = service.promote_substitute(guild_id=guild_id)

        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        if promoted and interaction.guild:
            promoted_mem = interaction.guild.get_member(promoted.user_id)
            if promoted_mem:
                cog = interaction.client.get_cog("TournamentCog")
                if cog and hasattr(cog, "_assign_participant_role"):
                    await cog._assign_participant_role(interaction.guild, promoted_mem)

        cog = interaction.client.get_cog("TournamentCog")
        if cog:
            if hasattr(cog, "_update_registration_panel"):
                await cog._update_registration_panel(interaction.guild)
            if hasattr(cog, "_update_subs_panel"):
                await cog._update_subs_panel(interaction.guild)

        embed = discord.Embed(
            title="🔄 Standby Substitute Promoted",
            description=f"{msg}\n\n*Executed by {interaction.user.mention}*",
            color=0x9B59B6,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament Operations")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Announce",
        emoji="📢",
        style=discord.ButtonStyle.primary,
        custom_id="btn_staff_broadcast_announce",
        row=1,
    )
    async def broadcast_announce_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_is_tournament_admin(interaction.user, interaction.guild, interaction.client):
            await interaction.response.send_message(
                "❌ You need the Tournament Admin role or Administrator permissions to use staff panel controls.",
                ephemeral=True,
            )
            return

        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service is unavailable.", ephemeral=True)
            return

        modal = StaffAnnounceModal(service)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Set Match Time",
        emoji="⏰",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_staff_set_time",
        row=1,
    )
    async def set_time_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_is_tournament_admin(interaction.user, interaction.guild, interaction.client):
            await interaction.response.send_message(
                "❌ You need the Tournament Admin role or Administrator permissions to use staff panel controls.",
                ephemeral=True,
            )
            return

        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service is unavailable.", ephemeral=True)
            return

        modal = StaffSetTimeModal(service)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Roster & Status",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_staff_live_status",
        row=1,
    )
    async def live_status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_is_tournament_admin(interaction.user, interaction.guild, interaction.client):
            await interaction.response.send_message(
                "❌ You need the Tournament Admin role or Administrator permissions to use staff panel controls.",
                ephemeral=True,
            )
            return

        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service is unavailable.", ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)
        embed = build_status_embed(state)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class UserRegistrationModal(discord.ui.Modal, title="Register for Tournament"):
    """Interactive modal popup for contestants to enter the tournament main bracket."""

    def __init__(self, service: TournamentService, state: TournamentState):
        super().__init__()
        self.service = service
        self.state = state

        self.ign_input = discord.ui.TextInput(
            label="In-Game Name (IGN)",
            placeholder="Enter your exact in-game duelist name",
            max_length=50,
            required=True,
        )
        reg_placeholder = f"e.g. {', '.join(state.allowed_regions[:3])}" if state.allowed_regions else "e.g. NA, EU, ASIA"
        self.region_input = discord.ui.TextInput(
            label="Region Tag",
            placeholder=reg_placeholder,
            max_length=20,
            required=True,
        )
        self.add_item(self.ign_input)
        self.add_item(self.region_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id or 0
        ign = self.ign_input.value.strip()
        weapon = "Standard"
        region = self.region_input.value.strip().upper()

        success, message, participant = self.service.register_participant(
            user_id=interaction.user.id,
            user_mention=interaction.user.mention,
            ign=ign,
            weapon=weapon,
            region=region,
            guild_id=guild_id,
        )

        if not success:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
            return

        cog = interaction.client.get_cog("TournamentCog")
        if cog and hasattr(cog, "_assign_participant_role"):
            await cog._assign_participant_role(interaction.guild, interaction.user)

        if cog and hasattr(cog, "_update_registration_panel"):
            await cog._update_registration_panel(interaction.guild)

        state = self.service.get_state(guild_id)
        embed = discord.Embed(
            title="🎟️ Registration Confirmed!",
            description=(
                f"Welcome **{participant.ign}** to **{state.name}**!\n\n"
                f"• **Region:** `{participant.region}`\n"
                f"• **Bracket Slot:** `{len(state.participants)}/{state.max_slots}` registered\n\n"
                "💡 *Need to adjust your IGN or Region? Run `/edit-entry` or click Withdraw on the panel.*"
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Player Registration Hub")
        await interaction.followup.send(embed=embed, ephemeral=True)


class TournamentRegistrationPanelView(discord.ui.View):
    """
    Persistent interactive Player Registration Hub posted in #tournament-registration.
    Allows duelists to register via modal form, withdraw, view roster, and check-in.
    """

    def __init__(self):
        super().__init__(timeout=None)

    def _get_service(self, interaction: discord.Interaction) -> TournamentService | None:
        srv = getattr(interaction.client, "tournament_service", None)
        if not srv:
            cog = interaction.client.get_cog("TournamentCog")
            if cog:
                srv = getattr(cog, "service", None)
        return srv

    @discord.ui.button(
        label="Register for Tournament",
        emoji="⚔️",
        style=discord.ButtonStyle.success,
        custom_id="btn_user_reg_hub",
        row=0,
    )
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service unavailable.", ephemeral=True)
            return
        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)

        if not state.main_open:
            await interaction.response.send_message(
                f"⛔ Main bracket registrations for **{state.name}** are currently closed.",
                ephemeral=True,
            )
            return

        if any(p.user_id == interaction.user.id for p in state.participants):
            await interaction.response.send_message(
                f"ℹ️ You are already registered for **{state.name}**!\n"
                "Use the **`🚪 Withdraw`** button if you need to release your slot.",
                ephemeral=True,
            )
            return

        if len(state.participants) >= state.max_slots:
            subs_ch = interaction.guild.get_channel(state.subs_channel_id) if (interaction.guild and state.subs_channel_id) else None
            subs_mention = subs_ch.mention if subs_ch else "the substitute channel"
            await interaction.response.send_message(
                f"⚠️ **Bracket is Full!** ({len(state.participants)}/{state.max_slots} slots taken).\n"
                f"If substitute signups are open, please join the Standby Bench in {subs_mention}.",
                ephemeral=True,
            )
            return

        modal = UserRegistrationModal(service, state)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Withdraw",
        emoji="🚪",
        style=discord.ButtonStyle.danger,
        custom_id="btn_user_withdraw_hub",
        row=0,
    )
    async def withdraw_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        service = self._get_service(interaction)
        if not service:
            await interaction.followup.send("❌ Tournament service unavailable.", ephemeral=True)
            return
        guild_id = interaction.guild_id or 0
        success, message = service.unregister_participant(interaction.user.id, guild_id=guild_id)
        if not success:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
            return

        cog = interaction.client.get_cog("TournamentCog")
        if cog and hasattr(cog, "_remove_participant_role"):
            await cog._remove_participant_role(interaction.guild, interaction.user)

        if cog and hasattr(cog, "_update_registration_panel"):
            await cog._update_registration_panel(interaction.guild)

        state = service.get_state(guild_id)
        embed = discord.Embed(
            title="👋 Tournament Withdrawal Confirmed",
            description=(
                f"{message}\n\n"
                f"Your slot in **{state.name}** has been released.\n"
                f"📊 Current slots: `{len(state.participants)}/{state.max_slots}`"
            ),
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Player Withdrawal")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="View Roster",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_user_roster_hub",
        row=0,
    )
    async def roster_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service unavailable.", ephemeral=True)
            return
        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)
        embed = build_roster_embed(state)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Check-In",
        emoji="🎟️",
        style=discord.ButtonStyle.primary,
        custom_id="btn_user_checkin_hub",
        row=1,
    )
    async def checkin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        service = self._get_service(interaction)
        if not service:
            await interaction.followup.send("❌ Tournament service unavailable.", ephemeral=True)
            return
        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)
        if not state.checkin_open:
            await interaction.followup.send(
                f"⏳ Tournament check-in for **{state.name}** is not currently open.",
                ephemeral=True,
            )
            return

        success, message, is_sub = service.check_in_participant(interaction.user.id, guild_id=guild_id)
        if not success:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
            return

        cog = interaction.client.get_cog("TournamentCog")
        if cog and hasattr(cog, "_update_registration_panel"):
            await cog._update_registration_panel(interaction.guild)

        embed = discord.Embed(
            title="🎟️ Check-In Confirmed",
            description=f"✅ {message}\n\nYou are marked as **READY** for **{state.name}**!",
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Match Day Check-In")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Help & Rules",
        emoji="❓",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_user_help_hub",
        row=1,
    )
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_is_admin = check_is_tournament_admin(interaction.user, interaction.guild, interaction.client)
        embed = build_help_embed("participants", is_admin=user_is_admin)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TournamentClosedRegistrationView(discord.ui.View):
    """
    Persistent view attached to the closed registration panel in #tournament-registration.
    Features a disabled indicator, optional link button jumping to the substitutes channel, and roster inspection.
    """

    def __init__(self, guild: Optional[discord.Guild] = None, state: Any = None):
        super().__init__(timeout=None)
        if guild and state and state.subs_channel_id:
            subs_ch = guild.get_channel(state.subs_channel_id)
            if subs_ch:
                self.add_item(
                    discord.ui.Button(
                        label="🛡️ Go to Substitute Bench",
                        style=discord.ButtonStyle.link,
                        url=f"https://discord.com/channels/{guild.id}/{state.subs_channel_id}",
                        row=0,
                    )
                )

    @discord.ui.button(
        label="Registrations Closed",
        emoji="🔒",
        style=discord.ButtonStyle.secondary,
        disabled=True,
        custom_id="btn_closed_reg_hub",
        row=0,
    )
    async def closed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(
        label="View Final Roster",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_closed_roster_hub",
        row=0,
    )
    async def roster_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        srv = getattr(interaction.client, "tournament_service", None)
        if not srv:
            cog = interaction.client.get_cog("TournamentCog")
            if cog:
                srv = getattr(cog, "service", None)
        if not srv:
            await interaction.response.send_message("❌ Tournament service unavailable.", ephemeral=True)
            return
        guild_id = interaction.guild_id or 0
        state = srv.get_state(guild_id)
        embed = build_roster_embed(state)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class UserSubRegistrationModal(discord.ui.Modal, title="Join Standby Substitute Bench"):
    """Interactive modal popup for contestants to enter the standby substitute queue."""

    def __init__(self, service: TournamentService, state: TournamentState):
        super().__init__()
        self.service = service
        self.state = state

        self.ign_input = discord.ui.TextInput(
            label="In-Game Name (IGN)",
            placeholder="Enter your exact in-game duelist name",
            max_length=50,
            required=True,
        )
        reg_placeholder = f"e.g. {', '.join(state.allowed_regions[:3])}" if state.allowed_regions else "e.g. NA, EU, ASIA"
        self.region_input = discord.ui.TextInput(
            label="Region Tag",
            placeholder=reg_placeholder,
            max_length=20,
            required=True,
        )
        self.add_item(self.ign_input)
        self.add_item(self.region_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id or 0
        ign = self.ign_input.value.strip()
        weapon = "Standard"
        region = self.region_input.value.strip().upper()

        success, message, sub = self.service.register_substitute(
            user_id=interaction.user.id,
            user_mention=interaction.user.mention,
            ign=ign,
            weapon=weapon,
            region=region,
            guild_id=guild_id,
        )

        if not success:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
            return

        cog = interaction.client.get_cog("TournamentCog")
        if cog and hasattr(cog, "_update_subs_panel"):
            await cog._update_subs_panel(interaction.guild)

        state = self.service.get_state(guild_id)
        pos = len(state.substitutes)
        embed = discord.Embed(
            title="🛡️ Standby Substitute Bench Joined!",
            description=(
                f"Welcome **{sub.ign}** to the standby queue for **{state.name}**!\n\n"
                f"• **Region:** `{sub.region}`\n"
                f"• **Queue Position:** `#{pos}` in line\n\n"
                "💡 *On match day, if any main players fail to check in, substitutes are promoted in order.*"
            ),
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • Standby Substitute Queue")
        await interaction.followup.send(embed=embed, ephemeral=True)


class TournamentSubsPanelView(discord.ui.View):
    """
    Persistent interactive Standby Substitute Queue Hub posted in #substitutes-bench.
    Allows standby duelists to join the queue via modal, leave queue, or check position.
    """

    def __init__(self):
        super().__init__(timeout=None)

    def _get_service(self, interaction: discord.Interaction) -> TournamentService | None:
        srv = getattr(interaction.client, "tournament_service", None)
        if not srv:
            cog = interaction.client.get_cog("TournamentCog")
            if cog:
                srv = getattr(cog, "service", None)
        return srv

    @discord.ui.button(
        label="Join Standby Bench",
        emoji="🛡️",
        style=discord.ButtonStyle.primary,
        custom_id="btn_sub_join_hub",
        row=0,
    )
    async def join_subs_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service unavailable.", ephemeral=True)
            return
        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)

        if not state.subs_open:
            await interaction.response.send_message(
                f"⛔ Standby substitute signups for **{state.name}** are currently closed.",
                ephemeral=True,
            )
            return

        if any(p.user_id == interaction.user.id for p in state.participants):
            await interaction.response.send_message(
                f"ℹ️ You are already registered as a main player in **{state.name}**!",
                ephemeral=True,
            )
            return

        if any(s.user_id == interaction.user.id for s in state.substitutes):
            await interaction.response.send_message(
                f"ℹ️ You are already on the standby substitute bench for **{state.name}**!",
                ephemeral=True,
            )
            return

        modal = UserSubRegistrationModal(service, state)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Leave Queue",
        emoji="🚪",
        style=discord.ButtonStyle.danger,
        custom_id="btn_sub_leave_hub",
        row=0,
    )
    async def leave_subs_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        service = self._get_service(interaction)
        if not service:
            await interaction.followup.send("❌ Tournament service unavailable.", ephemeral=True)
            return
        guild_id = interaction.guild_id or 0
        success, message = service.unregister_substitute(interaction.user.id, guild_id=guild_id)
        if not success:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
            return

        cog = interaction.client.get_cog("TournamentCog")
        if cog and hasattr(cog, "_update_subs_panel"):
            await cog._update_subs_panel(interaction.guild)

        state = service.get_state(guild_id)
        embed = discord.Embed(
            title="👋 Removed from Standby Queue",
            description=f"{message}\n\nStandby substitutes remaining: `{len(state.substitutes)}`",
            color=0xE74C3C,
        )
        embed.set_footer(text=f"{config.organization_name} • Standby Queue")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Queue Position",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_sub_pos_hub",
        row=0,
    )
    async def position_subs_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service unavailable.", ephemeral=True)
            return
        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)
        match_idx = None
        for i, s in enumerate(state.substitutes, start=1):
            if s.user_id == interaction.user.id:
                match_idx = i
                break

        if match_idx is None:
            await interaction.response.send_message(
                "❌ You are not currently registered in the standby substitute queue.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📊 Standby Queue Position",
            description=(
                f"🛡️ You are currently **#{match_idx}** of **{len(state.substitutes)}** substitutes in line.\n\n"
                "If any main bracket player no-shows or withdraws, substitutes are called up in FIFO queue order!"
            ),
            color=0x3498DB,
        )
        embed.set_footer(text=f"{config.organization_name} • Standby Queue")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="View Roster",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_sub_roster_hub",
        row=1,
    )
    async def roster_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service unavailable.", ephemeral=True)
            return
        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)
        embed = build_roster_embed(state)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Help & Rules",
        emoji="❓",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_sub_help_hub",
        row=1,
    )
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_is_admin = check_is_tournament_admin(interaction.user, interaction.guild, interaction.client)
        embed = build_help_embed("participants", is_admin=user_is_admin)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TournamentClosedSubsView(discord.ui.View):
    """
    Persistent view attached to the closed standby substitute queue message in #substitutes-bench.
    """

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Substitute Queue Closed",
        emoji="🔒",
        style=discord.ButtonStyle.secondary,
        disabled=True,
        custom_id="btn_closed_subs_hub",
        row=0,
    )
    async def closed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(
        label="View Roster",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_closed_subs_roster_hub",
        row=0,
    )
    async def roster_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        srv = getattr(interaction.client, "tournament_service", None)
        if not srv:
            cog = interaction.client.get_cog("TournamentCog")
            if cog:
                srv = getattr(cog, "service", None)
        if not srv:
            await interaction.response.send_message("❌ Tournament service unavailable.", ephemeral=True)
            return
        guild_id = interaction.guild_id or 0
        state = srv.get_state(guild_id)
        embed = build_roster_embed(state)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TournamentCheckinPanelView(discord.ui.View):
    """
    Persistent interactive Tournament Check-In Hub posted in #tournament-check-in.
    Features 1-click check-in, cancel check-in, status check, and active attendee list.
    """

    def __init__(self):
        super().__init__(timeout=None)

    def _get_service(self, interaction: discord.Interaction) -> TournamentService | None:
        srv = getattr(interaction.client, "tournament_service", None)
        if not srv:
            cog = interaction.client.get_cog("TournamentCog")
            if cog:
                srv = getattr(cog, "service", None)
        return srv

    def _get_cog(self, interaction: discord.Interaction):
        return interaction.client.get_cog("TournamentCog")

    @discord.ui.button(
        label="Check In",
        emoji="🎟️",
        style=discord.ButtonStyle.success,
        custom_id="btn_checkin_hub_action",
        row=0,
    )
    async def checkin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        service = self._get_service(interaction)
        cog = self._get_cog(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service unavailable.", ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)

        if not state.checkin_open:
            await interaction.response.send_message(
                f"🔒 Check-in for **{state.name}** is not currently open.",
                ephemeral=True,
            )
            return

        res = service.checkin_user(interaction.user.id, guild_id=guild_id)
        success, msg, part, role_type = res.success, res.message, res.participant, res.role_type
        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        if cog:
            await cog._update_all_live_panels(interaction.guild)
            await cog._dispatch_checkin_log(interaction.guild, part, action="checked_in", role_type=role_type)

        embed = discord.Embed(
            title="🎟️ Check-In Confirmed",
            description=msg,
            color=0x2ECC71,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament Check-In")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Cancel Check-In",
        emoji="❌",
        style=discord.ButtonStyle.danger,
        custom_id="btn_checkin_hub_cancel",
        row=0,
    )
    async def cancel_checkin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        service = self._get_service(interaction)
        cog = self._get_cog(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service unavailable.", ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)

        if not state.checkin_open:
            await interaction.response.send_message(
                f"🔒 Check-in for **{state.name}** is closed. Changes can only be made by Tournament Staff.",
                ephemeral=True,
            )
            return

        res = service.cancel_checkin(interaction.user.id, guild_id=guild_id)
        success, msg, part, role_type = res.success, res.message, res.participant, res.role_type
        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        if cog:
            await cog._update_all_live_panels(interaction.guild)
            await cog._dispatch_checkin_log(interaction.guild, part, action="cancelled", role_type=role_type)

        embed = discord.Embed(
            title="↩️ Check-In Cancelled",
            description=msg,
            color=0xE67E22,
        )
        embed.set_footer(text=f"{config.organization_name} • Tournament Check-In")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="My Status",
        emoji="📋",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_checkin_hub_status",
        row=0,
    )
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service unavailable.", ephemeral=True)
            return
        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)

        part = next((p for p in state.participants if p.user_id == interaction.user.id), None)
        if part:
            checked_str = "✅ **Checked In & Verified Ready**" if part.checked_in else "⚠️ **Not Checked In (Pending Attendance Confirmation)**"
            embed = discord.Embed(
                title=f"📋 Your Status — {state.name}",
                color=0x2ECC71 if part.checked_in else 0xE67E22,
            )
            embed.add_field(name="Roster Tier", value="Main Bracket Contestant", inline=True)
            embed.add_field(name="Registered IGN", value=f"`{part.ign}`", inline=True)
            embed.add_field(name="Weapon / Region", value=f"`{part.weapon}` / `{part.region}`", inline=True)
            embed.add_field(name="Check-In Status", value=checked_str, inline=False)
            embed.set_footer(text=f"{config.organization_name} • Contestant Record")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        sub_entry = next(((idx + 1, s) for idx, s in enumerate(state.substitutes) if s.user_id == interaction.user.id), None)
        if sub_entry:
            pos, s = sub_entry
            checked_str = "✅ **Checked In (Ready for Call-Up)**" if s.checked_in else "⚠️ **Not Checked In (Pending Call-Up Confirmation)**"
            embed = discord.Embed(
                title=f"📋 Your Status — {state.name}",
                color=0x3498DB if s.checked_in else 0xE67E22,
            )
            embed.add_field(name="Roster Tier", value="Standby Substitute Bench", inline=True)
            embed.add_field(name="Queue Position", value=f"**#{pos}** of {len(state.substitutes)}", inline=True)
            embed.add_field(name="Registered IGN", value=f"`{s.ign}`", inline=True)
            embed.add_field(name="Weapon / Region", value=f"`{s.weapon}` / `{s.region}`", inline=True)
            embed.add_field(name="Check-In Status", value=checked_str, inline=False)
            embed.set_footer(text=f"{config.organization_name} • Standby Record")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.send_message(
            f"❌ You are not registered for **{state.name}**. Use the registration hub or substitute bench to join!",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Checked-In List",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_checkin_hub_list",
        row=0,
    )
    async def list_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("❌ Tournament service unavailable.", ephemeral=True)
            return
        guild_id = interaction.guild_id or 0
        state = service.get_state(guild_id)

        main_checked = [p for p in state.participants if p.checked_in]
        subs_checked = [s for s in state.substitutes if s.checked_in]

        embed = discord.Embed(
            title=f"📊 Checked-In Attendance — {state.name}",
            color=0x2ECC71,
        )

        if main_checked:
            main_lines = [f"`{idx+1}.` **{p.ign}** ({p.user_mention}) • `{p.weapon}` [{p.region}]" for idx, p in enumerate(main_checked)]
            embed.add_field(
                name=f"Main Bracket ({len(main_checked)}/{len(state.participants)} Checked In)",
                value="\n".join(main_lines)[:1024],
                inline=False,
            )
        else:
            embed.add_field(name="Main Bracket (0 Checked In)", value="*No main players have checked in yet.*", inline=False)

        if subs_checked:
            subs_lines = [f"`#{idx+1}.` **{s.ign}** ({s.user_mention}) • `{s.weapon}` [{s.region}]" for idx, s in enumerate(subs_checked)]
            embed.add_field(
                name=f"Standby Substitutes Ready ({len(subs_checked)}/{len(state.substitutes)})",
                value="\n".join(subs_lines)[:1024],
                inline=False,
            )

        embed.set_footer(text=f"{config.organization_name} • Match Attendance")
        await interaction.response.send_message(embed=embed, ephemeral=True)


__all__ = [
    "check_is_tournament_admin",
    "is_tournament_admin",
    "is_tournament_admin_prefix",
    "check_is_event_admin",
    "is_event_admin",
    "is_server_admin",
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
]
