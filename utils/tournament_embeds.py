"""
Tournament Embed Builders and Visual UI Formatters for UDA (United Dueling Amity).
Pure presentation layer (Tier 1) with zero dependencies on views or command cogs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import discord

from config import config
from services.bracket_engine import BracketMatch, TournamentBracket
from services.tournament_service import (
    DEFAULT_WEAPONS,
    STANDARD_REGIONS,
    Participant,
    TournamentState,
)

# Standard Color Palette Constants
COLOR_EMERALD = 0x2ECC71  # Success / Open / Checked In
COLOR_CRIMSON = 0xE74C3C  # Danger / Closed / Withdrawn
COLOR_BLUE = 0x3498DB     # Standby / Info / Queues
COLOR_ORANGE = 0xE67E22   # Warning / Check-in Cancelled / Closed
COLOR_GOLD = 0xF1C40F     # Admin / Phase 3 / Warning
COLOR_PURPLE = 0x9B59B6   # Promotion / Phase 4
COLOR_SLATE = 0x95A5A6    # Inactive / Neutral / Check-in Closed
COLOR_TURQUOISE = 0x1ABC9C  # Staff Guide Panels


def generate_progress_bar(
    current: int,
    total: int,
    bar_length: int = 8,
    fill_char: str = "█",
    empty_char: str = "░",
) -> str:
    """
    Renders an ASCII block progress bar with percentage.
    Example: [████░░░░] 50% or [█░░░░░░░] 12%
    """
    if total <= 0:
        pct = 0
        filled = 0
    else:
        ratio = max(0.0, min(1.0, current / total))
        pct = int(ratio * 100)
        filled = round(ratio * bar_length)

    filled = min(bar_length, max(0, filled))
    empty = bar_length - filled
    blocks = (fill_char * filled) + (empty_char * empty)
    return f"[`{blocks}`] {pct}%"


def format_participant_line(index: int, p: Participant, show_checkin: bool = False) -> str:
    """
    Formats a single participant entry:
    `#01` **IGN** (<@user_id>) [✅] — `Weapon` | *Region*
    """
    num_str = f"#{index:02d}"
    checkin_badge = " `[✅]`" if (show_checkin and p.checked_in) else (" `[⏳]`" if show_checkin else "")
    return f"`{num_str}` **{p.ign}** ({p.user_mention}){checkin_badge} — `{p.weapon}` | *{p.region}*"


def _chunk_lines(lines: list[str], max_chars: int = 1000) -> list[str]:
    """Splits formatted lines into chunks that fit within Discord embed field length limits."""
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0
    for line in lines:
        line_len = len(line) + 1
        if current_chunk and (current_len + line_len > max_chars):
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_len = line_len
        else:
            current_chunk.append(line)
            current_len += line_len
    if current_chunk:
        chunks.append("\n".join(current_chunk))
    return chunks


def build_status_embed(
    state: TournamentState,
    org_name: str | None = None,
    color: int | None = None,
) -> discord.Embed:
    """
    Builds the /status embed matching the official UDA layout.
    """
    org = org_name or config.organization_name
    embed_color = color or config.embed_color

    main_status = "🟢 **OPEN**" if state.main_open else "🔴 **CLOSED**"
    subs_status = "🟢 **OPEN**" if state.subs_open else "🔴 **CLOSED**"
    checkin_status = "🟢 **OPEN**" if state.checkin_open else "🔴 **CLOSED**"
    cur_slots = len(state.participants)
    max_slots = state.max_slots
    bar = generate_progress_bar(cur_slots, max_slots, bar_length=8)
    sub_count = len(state.substitutes)
    regions_str = ", ".join(state.allowed_regions)

    desc_lines = [
        f"**Main Bracket Submissions:** {main_status}",
        f"**Substitute Signups:** {subs_status}",
        f"**Tournament Check-In:** {checkin_status}",
        "",
        f"📊 **Main Slots:** `{cur_slots} / {max_slots}` registered",
        f"{bar}",
        "",
        f"🛡️ **Substitutes on Deck:** `{sub_count}` standby players",
        f"🌍 **Allowed Regions:** `{regions_str}`",
    ]
    if getattr(state, "start_timestamp", None):
        desc_lines.append(f"⏰ **Match Day Start:** <t:{state.start_timestamp}:F> (<t:{state.start_timestamp}:R>)")
    if state.checkin_open:
        main_checked = sum(1 for p in state.participants if p.checked_in)
        sub_checked = sum(1 for s in state.substitutes if s.checked_in)
        desc_lines.append(f"🎟️ **Check-In Readiness:** `{main_checked}/{cur_slots}` main • `{sub_checked}/{sub_count}` subs ready")
    if state.participant_role_name:
        desc_lines.append(f"🏷️ **Participant Role:** `@{state.participant_role_name}`")
    if (
        state.announcement_channel_id
        or state.checkin_channel_id
        or state.subs_channel_id
        or state.registration_channel_id
    ):
        channels_str = []
        if state.announcement_channel_id:
            channels_str.append(f"Announce: <#{state.announcement_channel_id}>")
        if state.registration_channel_id:
            channels_str.append(f"Reg: <#{state.registration_channel_id}>")
        if state.checkin_channel_id:
            channels_str.append(f"Check-In: <#{state.checkin_channel_id}>")
        if state.subs_channel_id:
            channels_str.append(f"Subs: <#{state.subs_channel_id}>")
        desc_lines.append(f"📁 **Dedicated Channels:** {', '.join(channels_str)}")

    embed = discord.Embed(
        title=f"🏆 {state.name}",
        description="\n".join(desc_lines),
        color=embed_color,
    )

    weapons_text = "\n".join(f"• `{w}`" for w in state.approved_weapons)
    embed.add_field(
        name="Approved Weapons",
        value=weapons_text or "• All weapons allowed",
        inline=True,
    )

    commands_text = (
        "• `/register` — Enter main bracket\n"
        "• `/sub` — Enter as substitute\n"
        "• `/roster` — View full roster\n"
        "• `/checkin` — Confirm tournament day check-in\n"
        "• `/help` — View interactive command manual"
    )
    embed.add_field(
        name="Quick Commands",
        value=commands_text,
        inline=True,
    )

    embed.set_footer(text=f"{org} • Tournament System")
    return embed


def build_config_embed(
    state: TournamentState,
    guild: discord.Guild | None = None,
    org_name: str | None = None,
) -> discord.Embed:
    """Builds a diagnostic overview of active tournament and server configuration settings."""
    org = org_name or config.organization_name
    embed = discord.Embed(
        title=f"⚙️ Configuration Dashboard — {state.name}",
        description="Comprehensive overview of server roles, operational channels, limits, and scheduling.",
        color=config.embed_color,
    )
    admin_r = f"<@&{state.admin_role_id}>" if state.admin_role_id else (f"`@{state.admin_role_name}`" if state.admin_role_name else "`None`")
    event_r = f"<@&{state.event_role_id}>" if state.event_role_id else (f"`@{state.event_role_name}`" if state.event_role_name else "`None`")
    part_r = f"<@&{state.participant_role_id}>" if state.participant_role_id else (f"`@{state.participant_role_name}`" if state.participant_role_name else "`None`")
    roles_text = (
        f"• **Tournament Admin:** {admin_r}\n"
        f"• **Event Admin:** {event_r}\n"
        f"• **Participant Role:** {part_r}"
    )
    embed.add_field(name="🛡️ Configured Roles", value=roles_text, inline=False)

    reg_ch = f"<#{state.registration_channel_id}>" if state.registration_channel_id else "`Not Set`"
    sub_ch = f"<#{state.subs_channel_id}>" if state.subs_channel_id else "`Not Set`"
    chk_ch = f"<#{state.checkin_channel_id}>" if state.checkin_channel_id else "`Not Set`"
    log_ch = f"<#{state.checkin_log_channel_id}>" if getattr(state, "checkin_log_channel_id", None) else "`Not Set`"
    ann_ch = f"<#{state.announcement_channel_id}>" if state.announcement_channel_id else "`Not Set`"
    channels_text = (
        f"• **Registration Hub:** {reg_ch}\n"
        f"• **Substitutes Bench:** {sub_ch}\n"
        f"• **Check-In Hub:** {chk_ch}\n"
        f"• **Check-In Logs:** {log_ch}\n"
        f"• **Announcements:** {ann_ch}"
    )
    embed.add_field(name="📁 Operational Channels", value=channels_text, inline=False)

    regions = ", ".join(state.allowed_regions) if state.allowed_regions else "GLOBAL"
    time_str = f"<t:{state.start_timestamp}:F> (<t:{state.start_timestamp}:R>)" if getattr(state, "start_timestamp", None) else "`Not Set`"
    params_text = (
        f"• **Max Bracket Slots:** `{state.max_slots}`\n"
        f"• **Allowed Regions:** `{regions}`\n"
        f"• **Match Day Start:** {time_str}\n"
        f"• **Status:** Main: `{'OPEN' if state.main_open else 'CLOSED'}` | Subs: `{'OPEN' if state.subs_open else 'CLOSED'}` | Check-In: `{'OPEN' if state.checkin_open else 'CLOSED'}`"
    )
    embed.add_field(name="📊 Parameters & Scheduling", value=params_text, inline=False)

    embed.set_footer(text=f"{org} • Configuration Center")
    return embed


def build_roster_embed(
    state: TournamentState,
    org_name: str | None = None,
    color: int | None = None,
) -> discord.Embed:
    """
    Builds the /roster embed matching the official UDA layout.
    Automatically paginates main bracket and substitute rosters across multiple
    embed fields when the list exceeds Discord's 1024-character field limit.
    """
    org = org_name or config.organization_name
    embed_color = color or config.embed_color

    cur_slots = len(state.participants)
    max_slots = state.max_slots
    bar = generate_progress_bar(cur_slots, max_slots, bar_length=8)
    show_checkin = state.checkin_open or any(p.checked_in for p in state.participants)

    checkin_note = " *(Legend: `[✅]` Checked In, `[⏳]` Pending)*\n" if show_checkin else ""
    desc_lines = [
        f"**Main Slots:** `{cur_slots} / {max_slots}`",
        f"{bar}",
        checkin_note,
    ]

    embed = discord.Embed(
        title=f"📋 {state.name} — Tournament Roster",
        description="\n".join(line for line in desc_lines if line),
        color=embed_color,
    )

    checked_in_count = sum(1 for p in state.participants if p.checked_in)
    bracket_title = (
        f"⚔️ Main Bracket ({cur_slots} registered • {checked_in_count} checked in)"
        if show_checkin
        else f"⚔️ Main Bracket ({cur_slots})"
    )

    if state.participants:
        main_lines = [
            format_participant_line(i + 1, p, show_checkin=show_checkin)
            for i, p in enumerate(state.participants)
        ]
        main_chunks = _chunk_lines(main_lines, max_chars=1000)
        for idx, chunk in enumerate(main_chunks):
            field_name = (
                bracket_title
                if len(main_chunks) == 1
                else f"{bracket_title} (Part {idx + 1}/{len(main_chunks)})"
            )
            embed.add_field(name=field_name, value=chunk, inline=False)
    else:
        embed.add_field(
            name=bracket_title,
            value="*No participants registered yet.*",
            inline=False,
        )

    sub_count = len(state.substitutes)
    sub_checked_count = sum(1 for s in state.substitutes if s.checked_in)
    sub_title = (
        f"🛡️ Standby Substitutes ({sub_count} standby • {sub_checked_count} ready [✅])"
        if show_checkin
        else f"🛡️ Standby Substitutes ({sub_count})"
    )

    if state.substitutes:
        sub_lines = [
            format_participant_line(i + 1, s, show_checkin=show_checkin)
            for i, s in enumerate(state.substitutes)
        ]
        sub_chunks = _chunk_lines(sub_lines, max_chars=1000)
        for idx, chunk in enumerate(sub_chunks):
            field_name = (
                sub_title
                if len(sub_chunks) == 1
                else f"{sub_title} (Part {idx + 1}/{len(sub_chunks)})"
            )
            embed.add_field(name=field_name, value=chunk, inline=False)
    else:
        embed.add_field(
            name=sub_title,
            value="*No substitutes on deck.*",
            inline=False,
        )

    full_name = getattr(config, "organization_full_name", "United Dueling Amity")
    embed.set_footer(text=f"{org} • {full_name}")
    return embed


def build_tournament_reminder_embed(
    participant: Participant,
    state: TournamentState,
    reminder_type: str,  # "day_of" or "30_min"
    start_timestamp: int,
    is_sub: bool = False,
    org_name: str | None = None,
) -> discord.Embed:
    """
    Builds the personalized direct message (DM) embed sent to contestants:
    1. On tournament match day ("day_of").
    2. 30 minutes before event begins ("30_min").
    Includes:
    - Notification that tournament is today
    - Tournament name and all allowed regions
    - Contestant's specific registered region (satisfies "if multiple regions use the region player selected")
    - Discord dynamic auto-adjusting timestamp (<t:{start_timestamp}:F> and <t:{start_timestamp}:R>)
    - Contestant's weapon and entry status (Main Bracket or Standby Substitute)
    """
    org = org_name or config.organization_name
    tourney_name = state.name
    regions_display = ", ".join(state.allowed_regions) if state.allowed_regions else "GLOBAL"
    player_region = participant.region or "GLOBAL"
    entry_type = "Standby Substitute" if is_sub else "Main Bracket Contestant"
    weapon_display = participant.weapon or "Any"

    if reminder_type == "day_of":
        title = f"📅 Tournament Today: {tourney_name}"
        header_text = (
            f"👋 Greetings **{participant.ign}**!\n\n"
            f"This is an official match-day alert: **{tourney_name}** takes place **TODAY**!"
        )
        call_to_action = (
            "💡 **Reminders & Preparation:**\n"
            "• Keep notifications active in the server for when check-in opens.\n"
            "• You will receive a final reminder **30 minutes** before matches begin!\n"
            "• If you can no longer attend, please unregister to allow substitutes to play."
        )
        embed_color = 0x10B981  # Emerald Green
    else:  # "30_min"
        title = f"🚨 30-Minute Warning: {tourney_name} Starting Soon!"
        header_text = (
            f"⚠️ Urgent Alert for **{participant.ign}**!\n\n"
            f"**{tourney_name}** begins in approximately **30 minutes**!"
        )
        call_to_action = (
            "⚡ **Immediate Actions:**\n"
            "• Head over to the tournament channel now!\n"
            "• Confirm your tournament check-in if check-in is active.\n"
            "• Be ready in Discord for match callouts and bracket assignments."
        )
        embed_color = 0xE67E22  # High-visibility warning Orange

    embed = discord.Embed(
        title=title,
        description=(
            f"{header_text}\n\n"
            f"⏰ **Start Time:** <t:{start_timestamp}:F> (<t:{start_timestamp}:R>)\n"
            f"🌍 **Tournament Regions:** `{regions_display}`\n"
            f"📍 **Your Registered Region:** **{player_region}**\n"
            f"⚔️ **Your Weapon:** `{weapon_display}`\n"
            f"📋 **Your Entry:** **{entry_type}**\n\n"
            f"{call_to_action}"
        ),
        color=embed_color,
    )
    embed.set_footer(text=f"{org} • Official Match Day Reminders")
    return embed


def build_help_embed(
    section: str = "all",
    org_name: str | None = None,
    color: int | None = None,
    is_admin: bool = False,
) -> discord.Embed:
    """
    Builds the /help command manual.
    Sections: 'all', 'participants', 'admin', 'setup', 'weapons_regions', 'clans', 'events_sync'.
    Admin, Setup, and Event Sync sections are strictly restricted to verified administrators.
    """
    org = org_name or config.organization_name
    embed_color = color or config.embed_color
    full_name = getattr(config, "organization_full_name", "United Dueling Amity")

    embed = discord.Embed(
        title=f"📖 {org} Tournament Bot — Command Manual",
        description=(
            f"Welcome to the official **{full_name} ({org})** Tournament Bot.\n"
            "Use the command reference below or switch categories using the buttons below."
        ),
        color=embed_color,
    )

    if section in ("all", "participants"):
        participant_cmds = (
            "• `/register` — Enter the main tournament bracket.\n"
            "• `/unregister` — Withdraw and free up your bracket slot.\n"
            "• `/sub` — Join standby substitute queue.\n"
            "• `/sub-unregister` — Withdraw from substitute queue.\n"
            "• `/edit-entry` — Update weapon, IGN, or region without losing slot.\n"
            "• `/checkin` — Confirm presence during tournament check-in.\n"
            "• `/sub-checkin` — Confirm availability as a standby substitute.\n"
            "• `/status` — View registration status, slots & progress bar.\n"
            "• `/roster` — View full player list and check-in status."
        )
        embed.add_field(
            name="👥 Participant Commands",
            value=participant_cmds,
            inline=False,
        )

    if section in ("all", "admin"):
        if not is_admin:
            if section == "admin":
                embed.add_field(
                    name="🔒 Admin Access Restricted",
                    value="❌ Tournament Admin commands are restricted to server administrators and Tournament Staff.",
                    inline=False,
                )
        else:
            admin_lifecycle = (
                "• `/t open` — Open bracket, set capacity, regions & optional channel.\n"
                "• `/t close` — Close main bracket registrations.\n"
                "• `/t open-subs` / `/t close-subs` — Toggle substitute signups.\n"
                "• `/t checkin-open` / `/t checkin-close` — Run check-in window.\n"
                "• `/t promote` — Swap no-show player with standby sub (with autocomplete).\n"
                "• `/t kick` — Remove player from main or sub queue (with autocomplete).\n"
                "• `/t force-reg` — Manually add a participant or VIP.\n"
                "• `/t announce` — Broadcast announcement to players.\n"
                "• `/t staff-checkin` — Manually override and set a contestant's check-in status.\n"
                "• `/t clear` — Wipe roster clean for next event."
            )
            embed.add_field(
                name="🛠️ Tournament Admin Controls — Operations",
                value=admin_lifecycle,
                inline=False,
            )

            admin_config = (
                "• `/t set-time` — Set match day date, time & timezone for contestant reminders.\n"
                "• `/t test-reminder` — Send preview Day-Of or 30-min DM to yourself.\n"
                "• `/t set-limit` — Adjust max participant capacity (e.g. 16, 32).\n"
                "• `/t set-regions` — Update allowed regions filter.\n"
                "• `/t set-weapons` — Set approved weapon classes for the event.\n"
                "• `/t export` — Download CSV (Excel/Start.gg) or Challonge roster.\n"
                "• `/t bulk-reg` — Batch register duelists from text list."
            )
            embed.add_field(
                name="🛠️ Tournament Admin Controls — Roster & Config",
                value=admin_config,
                inline=False,
            )

    if section in ("all", "setup"):
        if not is_admin:
            if section == "setup":
                embed.add_field(
                    name="🔒 Admin Access Restricted",
                    value="❌ Server Setup & Configuration commands are restricted to server administrators and Tournament Staff.",
                    inline=False,
                )
        else:
            setup_channels = (
                "• `/t setup-section` — One-click setup wizard creating category & channels automatically.\n"
                "• `/t remove-section` — Safely clean up tournament categories and arena channels.\n"
                "• `/set-channel` (or `!set_channel`) — Quickly set or re-link a specific channel.\n"
                "• `/config` — Diagnostic overview of all roles, channels, and limits.\n"
                "• `/t set-admin-role` — Configure staff role required for tournament admin.\n"
                "• `/t set-event-role` (or `!set_event_role`) — Configure role authorized for event scheduling & sync.\n"
                "• `/t set-role` — Configure automatic contestant role.\n"
                "• `/state save` / `/state restore` / `/state status` — Disaster recovery and snapshots.\n"
                "• `/state save-roster` / `/state restore-roster` — Snapshot & restore active roster presets."
            )
            embed.add_field(
                name="⚙️ Server Setup & Channels",
                value=setup_channels,
                inline=False,
            )

            setup_panels = (
                "• `/post panel:[staff]` — Post 1-click Staff Control Center panel.\n"
                "• `/post panel:[guide]` — Post interactive Staff Guide with phase dropdown selector.\n"
                "• `/post panel:[reg]` — Post Player Registration Hub panel.\n"
                "• `/post panel:[subs]` — Post Standby Substitutes Bench panel.\n"
                "• `/post panel:[checkin]` — Post Match-Day Check-In Hub panel.\n"
                "• `/post panel:[clan_submit]` — Post interactive Clan Showcase intake portal.\n"
                "• `/post panel:[clan_roles]` — Post self-serve Clan Role Directory panel."
            )
            embed.add_field(
                name="⚙️ Interactive Panels & Portals",
                value=setup_panels,
                inline=False,
            )

    if section in ("all", "weapons_regions"):
        weapons_str = ", ".join(f"`{w}`" for w in DEFAULT_WEAPONS)
        regions_str = ", ".join(f"`{r}`" for r in STANDARD_REGIONS)
        rules_text = (
            f"**Approved Weapons:** {weapons_str}\n"
            f"**Supported Regions:** {regions_str} *(or `GLOBAL`)*\n"
            f"**Region Validation:** If a tournament is locked (e.g. `NA, EU`), "
            "players from other regions are prevented from registering automatically."
        )
        embed.add_field(
            name="⚔️ Weapons, Regions & Rules",
            value=rules_text,
            inline=False,
        )

    if section in ("all", "clans"):
        clan_cmds = (
            "• `/clan submit` — Submit or draft your clan profile (choose photo/GIF directly from phone or paste link).\n"
            "• `/clan claim` / `/clan leave` — Self-serve clan role alignment in `#clan-roles`.\n"
            "• `/clan edit` — Edit any existing clan profile live (updates database & published embed).\n"
            "• `/clan delete` — Remove clan from database and directory panel.\n"
            "• `/clan sync-roles` — Scan server roles ending in `//`.\n"
            "• `/clan channels` — Configure target showcase and staff review channels.\n"
            "• `/post panel:[clan_submit]` — Post interactive submission panel with persistent buttons.\n"
            "• `/post panel:[clan_roles]` — Post interactive clan directory dropdown panel."
        )
        embed.add_field(
            name="🏛️ Clan Profile Showcase Portal",
            value=clan_cmds,
            inline=False,
        )

    if section in ("all", "events_sync"):
        if not is_admin:
            if section == "events_sync":
                embed.add_field(
                    name="🔒 Admin Access Restricted",
                    value="❌ Event Scheduling and Live Website Sync commands are restricted to Server Staff and Event Managers.",
                    inline=False,
                )
        else:
            events_sync_cmds = (
                "• `/event create` — Schedule an official Discord server event (displayed at the top of the server banner).\n"
                "• `/event cancel` — Cancel and delete an upcoming event (removes from Discord & website schedule).\n"
                "• `/event complete` — Conclude a tournament, crown champion & runner-up, and publish to website Past Results.\n"
                "• `/event remove-past-result` — Delete an archived result from the website Past Results list.\n"
                "• **Live Website Sync:** All active Discord events and approved clans automatically feed into `unitedduelingamity.org`!"
            )
            embed.add_field(
                name="📅 Events & Website Live Sync",
                value=events_sync_cmds,
                inline=False,
            )

    full_name = getattr(config, "organization_full_name", "United Dueling Amity")
    embed.set_footer(text=f"{org} • {full_name}")
    return embed


def build_staff_panel_embed(org_name: str | None = None) -> discord.Embed:
    """Builds the embed for the 1-click Tournament Staff Operations Panel."""
    org = org_name or config.organization_name
    embed = discord.Embed(
        title=f"🛡️ {org} Tournament Staff Operations Panel",
        description=(
            f"Welcome to the official **{org}** Tournament Control Center!\n"
            "Staff and Tournament Admins can manage registrations, check-in, matches, and announcements "
            "using the interactive buttons below.\n\n"
            "**Control Center Actions:**\n"
            "• ⚙️ **Create Tournament** — Configure tournament title, slots, regions & channel.\n"
            "• 🟢 **Open Bracket** — Open registrations & auto-post registration banner.\n"
            "• 🔒 **Close Bracket** — Lock registrations to finalize bracket entries.\n"
            "• 🛡️ **Toggle Subs** — Open or close the standby substitute queue.\n"
            "• 🎟️ **Toggle Check-In** — Open or close the match day check-in window.\n"
            "• 🔄 **Promote Standby Sub** — Advance the next substitute in line into the bracket.\n"
            "• 📢 **Broadcast Announce** — Send a tournament announcement ping to players.\n"
            "• ⏰ **Set Match Time** — Configure match day date & automated contestant DMs.\n"
            "• 📊 **Live Roster & Status** — Check active slots, check-in readiness & player list.\n\n"
            "💡 *Click any button below to execute an operational action!*"
        ),
        color=config.embed_color,
    )
    embed.set_footer(text=f"{org} • Tournament Operations Center")
    return embed


def build_staff_guide_embed(section: str = "overview", org_name: str | None = None) -> discord.Embed:
    """
    Builds the interactive operational cheat sheet designed to be pinned in staff channels.
    Supports individual phase views ('overview', 'panels', 'phase_1', 'phase_2', 'phase_3', 'phase_4', 'checklist', 'persistence', 'roles', 'all').
    """
    org = org_name or config.organization_name
    full_name = getattr(config, "organization_full_name", "United Dueling Amity")

    sec = section.lower().strip()

    if sec == "panels":
        embed = discord.Embed(
            title=f"🎛️ {org} Staff Guide — Interactive Panels & 1-Click Operations",
            description=(
                "**Operate your entire tournament without typing repetitive slash commands!**\n"
                "DUKE uses persistent, interactive Discord buttons so staff can control brackets with 1 click, "
                "and players can sign up, check in, and withdraw via pop-up modals.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=COLOR_TURQUOISE,
        )
        embed.add_field(
            name="📍 Where to Deploy Each Panel",
            value=(
                "• **Staff Operations Panel (`/post panel:staff`):**\n"
                "  Post in your private staff channel (e.g. `#tournament-staff`). Only staff and Tournament Admins can see and click these buttons.\n\n"
                "• **Player Registration Hub (`/post panel:reg`):**\n"
                "  Post in `#tournament-registration`. The public entry banner for duelists.\n\n"
                "• **Standby Substitute Queue Hub (`/post panel:subs`):**\n"
                "  Post in `#substitutes-bench`. The standby bench for late sign-ups.\n\n"
                "• **Staff Operations Guide (`/post panel:guide`):**\n"
                "  Post in `#staff-announcements` or pin in staff channels as your permanent operational manual."
            ),
            inline=False,
        )
        embed.add_field(
            name="🕹️ Staff Operations Panel: Button-by-Button Guide",
            value=(
                "1. ⚙️ **Create Tournament:** Opens a modal to set tournament name, max slots (e.g. 32), allowed regions (e.g. ASIA), and registration channel without opening the bracket yet.\n"
                "2. ⏰ **Set Match Time:** Sets date, time, and timezone. Arms automatic contestant DMs on tournament day and 30m prior.\n"
                "3. 🟢 **Open Bracket:** Unlocks `#tournament-registration` automatically, arms player buttons, and announces the tournament.\n"
                "4. 🛡️ **Toggle Subs:** Opens or closes `#substitutes-bench` live with automatic channel unlock/lock.\n"
                "5. 🎟️ **Toggle Check-In:** Click at T - 60m to unlock `#tournament-checkin`. Click at T - 10m to lock and list no-shows.\n"
                "6. 🔄 **Promote Standby Sub:** Advances the next checked-in FIFO sub directly into the main bracket.\n"
                "7. 📢 **Broadcast Announce:** Opens a modal to send stylized embed notices to players with optional role ping.\n"
                "8. 📊 **Live Roster & Status:** Instant ephemeral diagnostic of current slots, percentages, and check-in readiness.\n"
                "9. 🔒 **Close Bracket:** Locks `#tournament-registration` and updates the player hub to the closed notice."
            ),
            inline=False,
        )
        embed.add_field(
            name="👥 Player Self-Serve Registration & Subs Experience",
            value=(
                "• **In `#tournament-registration`:**\n"
                "  Players do **not** type commands. They click `⚔️ Register`, type their IGN and Weapon into the modal popup, and the bot automatically reserves their slot, updates the visual bracket bar, and assigns `@{Tournament} Participant`.\n"
                "  If they cannot attend, they click `🚪 Withdraw` to immediately free up their slot.\n\n"
                "• **In `#substitutes-bench`:**\n"
                "  Standby players click `🛡️ Join Subs Queue` to get waitlisted in FIFO order, or click `📍 Queue Position` to check where they stand."
            ),
            inline=False,
        )
        embed.add_field(
            name="🔒 Automated Channel Synchronization",
            value=(
                "Every panel button dynamically manages Discord permissions in real time:\n"
                "• Opening registrations unlocks `#tournament-registration` (send messages).\n"
                "• Closing registrations locks the channel so chat cannot clutter the hub.\n"
                "• Opening check-in unlocks `#tournament-checkin`, and closing check-in locks it."
            ),
            inline=False,
        )
    elif sec == "phase_1":
        embed = discord.Embed(
            title=f"1️⃣ {org} Staff Guide — Phase 1: Pre-Tournament Setup & Arenas",
            description=(
                "**Build arena categories, schedule matches, and configure participant roles.**\n\n"
                "• **Auto-Build Categories & Arenas:** Run `/t setup-section` to auto-construct "
                "`🏆 TOURNAMENT HUB 🏆` and `⚔️ MATCH ARENAS ⚔️` with pre-configured permissions.\n\n"
                "• **Bind Dedicated Channels:** Run `/set-channel` to connect your announcements, "
                "registration, check-in, and subs channels.\n\n"
                "• **Schedule Match & Arm Automated DMs:** Run `/t set-time` or `/event create`. "
                "The bot automatically dispatches private DMs to contestants on match morning and 30 minutes before match time.\n\n"
                "• **Automatic Participant Role:** The bot automatically creates and assigns `@{Tournament} Participant` "
                "to every entrant upon registration, making announcement pings effortless.\n\n"
                "• **Weapons & Region Restrictions:** Restrict approved weapons via `/t set-weapons` and regions via `/t set-regions`."
            ),
            color=COLOR_EMERALD,
        )
    elif sec == "phase_2":
        embed = discord.Embed(
            title=f"2️⃣ {org} Staff Guide — Phase 2: Registration & Roster Monitoring",
            description=(
                "**Open sign-ups, monitor entries, mass-register players, and handle kicks.**\n\n"
                "• **Open Sign-Ups:** Click `🟢 Open Bracket` on the Staff Panel or run `/t open`. "
                "Specify capacity (e.g. 16 or 32), allowed regions, and whether the substitute queue is active. "
                "This unlocks `#tournament-registration` and posts the interactive player hub.\n\n"
                "• **Close Sign-Ups:** Click `🔒 Close Bracket` on the Staff Panel or run `/t close`. "
                "Locks `#tournament-registration` and edits the live hub into a closed notice directing players to subs.\n\n"
                "• **Bulk / Mass Registration:** Run `/t bulk-reg` to mass-enroll contestants from a text block (`IGN | Weapon | Region`).\n\n"
                "• **Roster Snapshot & Backups:** Run `/state save-roster` to snapshot your active roster into `saved_roster.json`. "
                "On fresh container deploys or bot restarts, the bot automatically restores your full roster on boot!\n\n"
                "• **Player Autocomplete Kick:** Run `/t kick user:` — type the first letters of any player's IGN "
                "to select and kick them directly. Mentions and raw user IDs also work.\n\n"
                "• **Admin Manual Entry:** Use `/t force-reg` to bypass open registration windows and directly "
                "seed contestants or VIPs into the main bracket or substitute queue."
            ),
            color=COLOR_BLUE,
        )
    elif sec == "phase_3":
        embed = discord.Embed(
            title=f"3️⃣ {org} Staff Guide — Phase 3: Match Day, Check-In & Substitutes",
            description=(
                "**Manage match day check-ins, automated reminders, and substitute promotions.**\n\n"
                "• **Automated Player DMs:** Contestants automatically receive personal DMs on tournament morning "
                "and 30 minutes before match time showing their selected region and Discord's live dynamic timestamp.\n\n"
                "• **Open Check-In (T - 60m):** Click `🎟️ Toggle Check-In` on the panel or run `/t checkin-open`. "
                "Unlocks `#tournament-checkin` and enables check-in buttons on player registration hubs.\n\n"
                "• **Close Check-In (T - 10m):** Click `🎟️ Toggle Check-In` or run `/t checkin-close`. "
                "Locks `#tournament-checkin`, closes the window, and reports ready players vs no-shows.\n\n"
                "• **Promote Standby Substitutes (T - 05m):** Click `🔄 Promote Sub` on the panel or run "
                "`/t promote replace:@NoShow` to swap in checked-in FIFO substitutes.\n\n"
                "• **Broadcast Announcements:** Click `📢 Broadcast Announce` on the panel or run `/t announce` "
                "to send formatted embed pings to contestants."
            ),
            color=COLOR_GOLD,
        )
    elif sec == "phase_4":
        embed = discord.Embed(
            title=f"4️⃣ {org} Staff Guide — Phase 4: Concluding, Archiving & Website Sync",
            description=(
                "**Crown champions, export brackets, sync to website, and reset.**\n\n"
                "• **Export Brackets for Challonge & Start.gg:** Run `/t export format:Challonge target:Main` "
                "(or CSV/Text) to generate instant seed lists without substitutes accidentally mixed in.\n\n"
                "• **Crown Champion & Website Sync:** Run `/event complete` to record the tournament champion. "
                "The result automatically syncs to [unitedduelingamity.org](https://unitedduelingamity.org) and server feeds.\n\n"
                "• **Wipe Bracket for Next Event:** Run `/t clear` to wipe the active roster and temporary "
                "roles for a fresh tournament cycle (preserves configured channels).\n\n"
                "• **Clean Up Arenas:** Run `/t remove-section` to safely remove match categories and voice channels."
            ),
            color=COLOR_PURPLE,
        )
    elif sec == "checklist":
        embed = discord.Embed(
            title=f"⚡ {org} Staff Guide — Match Day Quick Checklist",
            description=(
                "**Critical operational timeline for tournament referees & admins.**\n\n"
                "• **T - 60m (Open Check-In):**\n"
                "  Run `/t checkin-open` or click `🎟️ Toggle Check-In` on the Staff Panel. "
                "Unlocks `#tournament-checkin` and arms player check-in buttons.\n\n"
                "• **T - 10m (Close Check-In):**\n"
                "  Run `/t checkin-close` or toggle the panel button. "
                "Locks `#tournament-checkin` and lists confirmed players vs no-shows.\n\n"
                "• **T - 05m (Promote Ready Subs):**\n"
                "  Run `/t promote replace:@NoShow` or click `🔄 Promote Sub` to advance checked-in subs into open slots.\n\n"
                "• **T - 00m (Seed Bracket & Start):**\n"
                "  Run `/t export format:Challonge target:Main` ➔ Import into Challonge/Start.gg ➔ Run `/t announce` with match pairings!"
            ),
            color=COLOR_CRIMSON,
        )
    elif sec == "persistence":
        embed = discord.Embed(
            title=f"💾 {org} Staff Guide — State Preservation & Host Redeployment",
            description=(
                "**Never lose your channels, roles, or rosters after a git push or server restart.**\n\n"
                "• **Save Channels & Roles (`/state save`):**\n"
                "  Once your channels are set, run `/state save`. Writes all channel IDs, role IDs, and panel links to `saved_state.json`.\n\n"
                "• **Restore After Deploy (`/state restore`):**\n"
                "  Run `/state restore [repost_panels:True]` to immediately re-bind all channels and re-sync interactive button embeds.\n\n"
                "• **Status & Diagnostics (`/state status`):**\n"
                "  Shows a side-by-side diagnostic check comparing active Discord server channels vs. saved disk snapshots.\n\n"
                "• **Zero-Click Auto-Restore on Boot:**\n"
                "  Whenever the bot boots up on your host (Discloud/Docker), it automatically loads `saved_state.json` and `saved_roster.json` on startup!"
            ),
            color=0x34495E,
        )
    elif sec == "roles":
        embed = discord.Embed(
            title=f"🛡️ {org} Staff Guide — Role Permissions Reference",
            description=(
                "**Understand permission boundaries and authorizations across staff tiers.**\n\n"
                "• **Tournament Admin Role (`/t set-admin-role`):**\n"
                "  Authorized for tournament operations: staff panel, registrations, check-in, kicks, match schedules, and roster controls.\n"
                "  *Strictly restricted from server administrative settings, clan approvals, or website event feeds.*\n\n"
                "• **Event & Website Role (`/t set-event-role`):**\n"
                "  Authorized for scheduling official Discord server banner events and pushing public schedule updates to the website.\n\n"
                "• **Server Administrator:**\n"
                "  Server Owner and members with Discord `Administrator` permissions. Full access to system building, role assignments, and resets."
            ),
            color=COLOR_ORANGE,
        )
    elif sec == "all":
        embed = discord.Embed(
            title=f"📖 {org} Tournament Staff Operational Guide & Cheat Sheet",
            description=(
                f"Welcome to the **{full_name} ({org})** Staff Operations Manual.\n"
                "Pin this message in your staff channels for quick access and mod onboarding.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=COLOR_BLUE,
        )
        embed.add_field(
            name="🎛️ 1-Click Operations Control Center",
            value=(
                "• `/post panel:staff` — Spawns the 1-click button operations center.\n"
                "• `/post panel:reg` — Spawns player registration hub in `#tournament-registration`.\n"
                "• `/post panel:subs` — Spawns standby substitute hub in `#substitutes-bench`."
            ),
            inline=False,
        )
        embed.add_field(
            name="1️⃣ Phase 1: Pre-Tournament Setup",
            value=(
                "• **Build Arenas:** `/t setup-section` (Builds categories, match arenas & voice booths).\n"
                "• **Set Channels:** `/set-channel` (Binds announcements, registration, check-in & subs).\n"
                "• **Schedule Match:** `/t set-time` (Arms automated contestant DMs for match morning & 30m before).\n"
                "• **Weapons & Regions:** Limits via `/t set-weapons` & `/t set-regions`."
            ),
            inline=False,
        )
        embed.add_field(
            name="2️⃣ Phase 2: Registration & Roster Monitoring",
            value=(
                "• **Open/Close Sign-Ups:** Click Staff Panel buttons or run `/t open` / `/t close` (auto-locks channel).\n"
                "• **Bulk Registration:** `/t bulk-reg` (Mass enrolls lists of contestants).\n"
                "• **Roster Persistence:** `/state save-roster` (Saves roster to `saved_roster.json` & auto-restores on boot).\n"
                "• **Quick Kicking & Manual Entry:** `/t kick` (instant autocomplete) & `/t force-reg`."
            ),
            inline=False,
        )
        embed.add_field(
            name="3️⃣ Phase 3: Match Day & Reminders",
            value=(
                "• **Check-In Window (T - 60m):** `/t checkin-open` (Unlocks `#tournament-checkin`).\n"
                "• **Close Check-In (T - 10m):** `/t checkin-close` (Locks channel & lists no-shows).\n"
                "• **Promote Subs (T - 05m):** `/t promote replace:@NoShow` (Swaps in ready FIFO subs).\n"
                "• **Broadcast Alerts:** `/t announce` (Pings contestants with stylized embed)."
            ),
            inline=False,
        )
        embed.add_field(
            name="4️⃣ Phase 4: Concluding & Archiving",
            value=(
                "• **Export Seed List:** `/t export format:Challonge target:Main` (Start.gg/Excel ready).\n"
                "• **Crown Champion:** `/event complete` (Publishes winner to website & server feeds).\n"
                "• **Wipe Roster:** `/t clear` (Wipes contestants for next event while keeping channels).\n"
                "• **Clean Up Arenas:** `/t remove-section` (Safely deletes temporary arena channels)."
            ),
            inline=False,
        )
        embed.add_field(
            name="⚡ Match Day Quick Checklist",
            value=(
                "• **T - 60m:** `/t checkin-open` (or click Toggle Check-In)\n"
                "• **T - 10m:** `/t checkin-close` (Locks channel)\n"
                "• **T - 05m:** `/t promote replace:@NoShow` (Promotes ready subs)\n"
                "• **T - 00m:** `/t export format:Challonge target:Main` ➔ Seed ➔ `/t announce`"
            ),
            inline=False,
        )
        embed.add_field(
            name="💾 State Preservation Across Git Pushes",
            value=(
                "• `/state save` — Saves all channel IDs and roles to `saved_state.json`.\n"
                "• `/state restore [repost_panels:True]` — Re-binds all channels & refreshes live embeds.\n"
                "• `/state status` — Diagnostics check of active channels vs saved disk snapshot."
            ),
            inline=False,
        )
        embed.add_field(
            name="🛡️ Role Permissions Reference",
            value=(
                "• **Tournament Admin Role (`/t set-admin-role`):** Operations, bracket runner, check-in & kicks.\n"
                "• **Event & Website Role (`/t set-event-role`):** Server banner events & website publishing.\n"
                "• **Server Administrator:** System setup, channel builder & role assignments."
            ),
            inline=False,
        )
    else:  # overview
        embed = discord.Embed(
            title=f"📖 {org} Tournament Staff Operational Guide",
            description=(
                f"Welcome to the **{full_name} ({org})** Staff Control Manual!\n\n"
                "Use the **interactive dropdown menu below** to jump directly to any operational phase without channel clutter.\n\n"
                "**Operational Phase Directory:**\n"
                "• 🎛️ **Interactive Panels** — 1-click operations control center & player hubs\n"
                "• 1️⃣ **Phase 1: Pre-Tournament Setup** — Category builder, channel bindings & scheduling\n"
                "• 2️⃣ **Phase 2: Registration & Rosters** — Auto channel locks, bulk enrollment & snapshot presets\n"
                "• 3️⃣ **Phase 3: Match Day & Reminders** — Automated contestant DMs, check-in & FIFO sub swaps\n"
                "• 4️⃣ **Phase 4: Concluding & Archiving** — Crown champions, Challonge export & bracket wipe\n"
                "• ⚡ **Match Day Quick Checklist** — Critical timeline from T-60m to T-00m\n"
                "• 💾 **State Preservation** — Saving channels & rosters across bot redeployments (`/state save`)\n"
                "• 🛡️ **Role Permissions Reference** — Tournament Admin vs. Event & Website staff boundaries\n\n"
                "💡 *Select an operational phase below to view step-by-step guidance.*"
            ),
            color=COLOR_BLUE,
        )

    embed.set_footer(text=f"{org} • Staff Operations Manual")
    return embed


def build_registration_panel_embed(state: Any, guild: discord.Guild | None = None) -> discord.Embed:
    """
    Builds the interactive live player registration hub embed posted in #tournament-registration.
    Displays live slot counters, visual progress bar, capacity badges, and instructions.
    """
    org = config.organization_name
    p_count = len(state.participants)
    max_slots = state.max_slots
    is_full = p_count >= max_slots
    slots_left = max(0, max_slots - p_count)

    pct = min(1.0, p_count / max_slots) if max_slots > 0 else 0.0
    bar_len = 10
    filled = int(round(pct * bar_len))
    bar = "█" * filled + "░" * (bar_len - filled)

    role_mention = f"<@&{state.participant_role_id}>" if state.participant_role_id else "*Auto-assigned*"
    regions_str = ", ".join(state.allowed_regions) if state.allowed_regions else "GLOBAL"
    weapons_str = ", ".join(f"`{w}`" for w in state.approved_weapons[:6])
    if len(state.approved_weapons) > 6:
        weapons_str += f" *(+{len(state.approved_weapons) - 6} more)*"

    time_str = f"<t:{state.start_timestamp}:F> (<t:{state.start_timestamp}:R>)" if state.start_timestamp else "*TBD*"

    if is_full:
        status_badge = "⚠️ **BRACKET FULL — JOIN STANDBY SUBS**"
        embed_color = 0xF39C12  # Orange/Gold
    else:
        status_badge = "🟢 **REGISTRATIONS ARE OPEN**"
        embed_color = COLOR_EMERALD

    desc_lines = [
        f"Welcome duelist! Registrations for **{state.name}** are live.",
        "",
        f"### {status_badge}",
        f"**Capacity Progress:** `[{bar}]` **{p_count}/{max_slots}** ({slots_left} slots remaining)",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "**🏆 Tournament Information:**",
        f"• **Allowed Regions:** `{regions_str}`",
        f"• **Approved Weapons:** {weapons_str}",
        f"• **Auto-Role:** {role_mention}",
        f"• **Match Start:** {time_str}",
        f"• **Substitute Bench:** `{'Active' if state.subs_open else 'Disabled'}`",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "**⚔️ How to Enter:**",
        "• Click **`⚔️ Register for Tournament`** below to open the popup entry form!",
        "• Click **`🚪 Withdraw`** if you need to leave and free your slot.",
        "• Click **`📊 View Roster`** to inspect the live bracket entries.",
    ]
    if state.checkin_open:
        desc_lines.append("• 🎟️ **Match Day Check-In is OPEN!** Click **`🎟️ Check-In`** to confirm presence.")

    embed = discord.Embed(
        title=f"🏆 {state.name} — Player Registration Hub",
        description="\n".join(desc_lines),
        color=embed_color,
    )
    embed.set_footer(text=f"{org} • Official Tournament Registration Hub")
    return embed


def build_registration_closed_embed(state: Any, guild: discord.Guild | None = None) -> discord.Embed:
    """
    Builds the closed registration embed that automatically replaces the active hub
    when staff closes bracket signups.
    """
    org = config.organization_name
    p_count = len(state.participants)
    max_slots = state.max_slots

    subs_channel_mention = "*Check with Staff*"
    if state.subs_channel_id and guild:
        ch = guild.get_channel(state.subs_channel_id)
        if ch:
            subs_channel_mention = ch.mention

    time_str = f"<t:{state.start_timestamp}:F> (<t:{state.start_timestamp}:R>)" if state.start_timestamp else "*TBD*"

    desc_lines = [
        "## ⛔ REGISTRATION HAS CLOSED. CHECK FOR SUB REGISTRATION IF AVAILABLE!",
        "",
        f"Main bracket signups for **{state.name}** have concluded.",
        f"• **Final Main Entries:** `{p_count}/{max_slots}` registered duelists",
        f"• **Match Start:** {time_str}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "**🛡️ Want to Compete as a Standby Substitute?**",
        "If main players no-show or withdraw on match day, substitutes in line are promoted into the bracket!",
        f"👉 Head over to {subs_channel_mention} to register for the Standby Substitute Queue.",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💡 *Click `📊 View Final Roster` below to view the official contestant bracket.*"
    ]

    embed = discord.Embed(
        title=f"🔒 {state.name} — Registrations Are CLOSED",
        description="\n".join(desc_lines),
        color=COLOR_CRIMSON,
    )
    embed.set_footer(text=f"{org} • Registration Closed")
    return embed


def build_subs_panel_embed(state: Any, guild: discord.Guild | None = None) -> discord.Embed:
    """
    Builds the interactive live standby substitute queue hub embed posted in #substitutes-bench.
    """
    org = config.organization_name
    s_count = len(state.substitutes)
    regions_str = ", ".join(state.allowed_regions) if state.allowed_regions else "GLOBAL"
    time_str = f"<t:{state.start_timestamp}:F> (<t:{state.start_timestamp}:R>)" if state.start_timestamp else "*TBD*"

    desc_lines = [
        f"Welcome standby duelist! The substitute bench for **{state.name}** is active.",
        "",
        "### 🛡️ **STANDBY SUBSTITUTE QUEUE IS OPEN**",
        f"**Active Standby Queue:** `{s_count}` duelist(s) waiting in FIFO queue order.",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "**ℹ️ How the Standby Bench Works:**",
        "• If any main player fails to check in on match day, substitutes who checked in are promoted in queue order.",
        "• Joining the substitute queue guarantees first priority when open spots appear.",
        f"• **Allowed Regions:** `{regions_str}`",
        f"• **Match Start:** {time_str}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "**🛡️ How to Join:**",
        "• Click **`🛡️ Join Standby Bench`** below to submit your substitute entry form!",
        "• Click **`🚪 Leave Queue`** if you are no longer available.",
        "• Click **`📊 View Queue Position`** to check your spot in line.",
    ]

    embed = discord.Embed(
        title=f"🛡️ {state.name} — Standby Substitute Hub",
        description="\n".join(desc_lines),
        color=COLOR_BLUE,
    )
    embed.set_footer(text=f"{org} • Standby Substitute Queue")
    return embed


def build_subs_closed_embed(state: Any, guild: discord.Guild | None = None) -> discord.Embed:
    """
    Builds the closed standby substitute embed when substitute signups are locked.
    """
    org = config.organization_name
    s_count = len(state.substitutes)

    desc_lines = [
        "## ⛔ STANDBY SUBSTITUTE REGISTRATIONS HAVE CLOSED",
        "",
        f"Substitute queue signups for **{state.name}** are currently locked.",
        f"• **Total Standby Subs in Queue:** `{s_count}` duelists",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💡 *Check announcements in the server for match day start times and further instructions.*"
    ]

    embed = discord.Embed(
        title=f"🔒 {state.name} — Substitute Queue CLOSED",
        description="\n".join(desc_lines),
        color=COLOR_ORANGE,
    )
    embed.set_footer(text=f"{org} • Substitutes Closed")
    return embed


def build_checkin_panel_embed(state: Any, guild: discord.Guild | None = None) -> discord.Embed:
    """
    Builds the interactive live Tournament Check-In Hub embed posted in #tournament-check-in.
    Displays live check-in progress, time remaining, and instructions.
    """
    org = config.organization_name
    main_total = len(state.participants)
    main_checked = sum(1 for p in state.participants if p.checked_in)
    subs_total = len(state.substitutes)
    subs_checked = sum(1 for s in state.substitutes if s.checked_in)

    pct = int((main_checked / main_total) * 100) if main_total > 0 else 0
    bar = generate_progress_bar(main_checked, max(main_total, 1), bar_length=8)

    time_str = f"<t:{state.start_timestamp}:F> (<t:{state.start_timestamp}:R>)" if state.start_timestamp else "*TBD*"
    status_header = "### 🎟️ **TOURNAMENT CHECK-IN IS OPEN**" if state.checkin_open else "### 🔒 **TOURNAMENT CHECK-IN IS CLOSED**"
    color = COLOR_EMERALD if state.checkin_open else COLOR_SLATE

    desc_lines = [
        f"Welcome duelist! The official check-in desk for **{state.name}** is active.",
        "",
        status_header,
        f"**Main Bracket Attendance:** `{main_checked} / {main_total}` ({pct}%)",
        f"`{bar}`",
        f"**Standby Substitutes Ready:** `{subs_checked} / {subs_total}` duelist(s)",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "**ℹ️ Check-In Rules & Match Flow:**",
        "• All main bracket participants **must** check in before the match start.",
        "• Unconfirmed main players when the bracket launches will be replaced by verified substitutes in queue order.",
        "• Standby substitutes who check in are locked in prioritized FIFO queue order for call-up.",
        f"• **Scheduled Match Start:** {time_str}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "**🎟️ How to Check In:**",
        "• Click **`🎟️ Check In`** below for instant 1-click confirmation.",
        "• Click **`❌ Cancel Check-In`** if you are no longer able to attend.",
        "• Click **`📋 My Status`** to inspect your attendance and registration details.",
        "• Click **`📊 Checked-In List`** to see who is verified ready.",
    ]

    embed = discord.Embed(
        title=f"🎟️ {state.name} — Tournament Check-In Hub",
        description="\n".join(desc_lines),
        color=color,
    )
    embed.set_footer(text=f"{org} • Match-Day Check-In System")
    return embed


def build_checkin_receipt_embed(
    state: Any,
    participant: Any,
    action: str,  # "checked_in", "cancelled", "staff_override"
    role_type: str = "main",  # "main" or "sub"
    staff_member: discord.Member | None = None,
) -> discord.Embed:
    """
    Builds the audit receipt embed dispatched to the designated check-in log channel.
    """
    org = config.organization_name
    role_label = "Main Bracket Contestant" if role_type == "main" else "Standby Substitute"

    if action == "checked_in":
        title = "🎟️ Contestant Check-In Confirmed"
        color = COLOR_EMERALD
        status_str = f"✅ **Checked In & Verified Ready** ({role_label})"
    elif action == "cancelled":
        title = "↩️ Contestant Check-In Retracted"
        color = COLOR_ORANGE
        status_str = f"⚠️ **Check-In Cancelled / Unconfirmed** ({role_label})"
    else:  # staff_override
        title = "⚙️ Staff Check-In Override"
        color = COLOR_BLUE
        status_str = f"🛠️ **Updated by Staff** ({role_label})"

    embed = discord.Embed(
        title=title,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Duelist", value=participant.user_mention, inline=True)
    embed.add_field(name="IGN", value=f"`{participant.ign}`", inline=True)
    embed.add_field(name="Weapon", value=f"`{participant.weapon}`", inline=True)
    embed.add_field(name="Region", value=f"`{participant.region}`", inline=True)
    embed.add_field(name="Current Status", value=status_str, inline=True)
    embed.add_field(name="Tournament", value=f"**{state.name}**", inline=True)

    if staff_member:
        embed.add_field(name="Moderator", value=staff_member.mention, inline=True)

    embed.set_footer(text=f"{org} • Check-In Audit Logs")
    return embed


def build_bracket_embed(
    bracket: TournamentBracket,
    tournament_name: str = "Tournament",
    section: str = "winners",
    round_num: int = 1,
) -> discord.Embed:
    """
    Renders the visual bracket view for the specified bracket section and round.
    Shows soft check-in indicators ([✅] vs [⏳]), match statuses, scores, and champion banner.
    """
    org = config.organization_name or "United Dueling Amity"
    format_label = "Double Elimination" if bracket.format == "double" else "Single Elimination"
    lock_status = "🔒 **LIVE BRACKET** (Locked)" if bracket.is_locked else "📝 **DRAFT BRACKET** (Auto-updates with roster)"
    seed_status = "🔀 Random Shuffled" if bracket.seed_mode == "random" else "📋 Registration Order"

    # Color selection
    if bracket.champion_ign:
        color = COLOR_GOLD
    elif bracket.is_locked:
        color = COLOR_EMERALD
    else:
        color = COLOR_BLUE

    # Normalize section
    section = section.lower()
    if bracket.format != "double" and section != "winners":
        section = "winners"

    section_titles = {
        "winners": "🏆 Winners Bracket",
        "losers": "🛡️ Losers Bracket",
        "finals": "👑 Grand Finals",
    }
    sec_title = section_titles.get(section, "🏆 Winners Bracket")

    # Filter matches
    if section == "finals":
        matches = [m for m in bracket.matches.values() if m.section == "finals"]
        round_header = "Grand Finals"
        total_r = 1
    elif section == "losers":
        matches = [m for m in bracket.matches.values() if m.section == "losers" and m.round_number == round_num]
        total_r = max(1, bracket.total_rounds_lb)
        round_header = f"Losers Round {round_num}"
    else:
        matches = [m for m in bracket.matches.values() if m.section == "winners" and m.round_number == round_num]
        total_r = max(1, bracket.total_rounds_wb)
        round_header = f"Winners Round {round_num}"

    embed = discord.Embed(
        title=f"🏆 {tournament_name} — {sec_title}",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    desc_lines = [
        f"**Format:** `{format_label}` • **Seeding:** `{seed_status}`",
        f"**Status:** {lock_status}",
    ]
    if bracket.champion_ign:
        desc_lines.append(f"\n🎉 👑 **TOURNAMENT CHAMPION:** **{bracket.champion_ign}** 👑 🎉\n")
    else:
        if section != "finals":
            desc_lines.append(
                f"**Viewing:** `{sec_title}` — `Round {round_num} of {total_r}` *(use ◀️ / ▶️ to flip rounds)*\n"
            )
        else:
            desc_lines.append(f"**Viewing:** `{sec_title}`\n")

    embed.description = "\n".join(desc_lines)

    if not matches:
        embed.add_field(
            name=round_header,
            value="*No matches scheduled for this round yet.*",
            inline=False,
        )
    else:
        match_blocks = []
        for m in sorted(matches, key=lambda x: x.match_number):
            if m.state == "bye":
                badge = "⏭️ `BYE`"
            elif m.state == "completed":
                badge = "✅ `FINAL`"
            elif m.state == "ready":
                badge = "⚔️ `READY`"
            else:
                badge = "⏳ `WAITING`"

            # Player 1 formatting
            p1_badge = "[✅]" if m.player1_checked_in else "[⏳]"
            p1_clan = f"[{m.player1_clan}] " if m.player1_clan else ""
            if m.player1_id:
                p1_line = f"{p1_badge} **{p1_clan}{m.player1_ign}**"
            else:
                p1_line = f"`{p1_clan}{m.player1_ign}`"

            # Player 2 formatting
            p2_badge = "[✅]" if m.player2_checked_in else "[⏳]"
            p2_clan = f"[{m.player2_clan}] " if m.player2_clan else ""
            if m.player2_id:
                p2_line = f"{p2_badge} **{p2_clan}{m.player2_ign}**"
            else:
                p2_line = f"`{p2_clan}{m.player2_ign}`"

            # Outcome line
            if m.state == "completed":
                score_str = f" `{m.score}`" if m.score else ""
                outcome = f"👑 **Winner:** **{m.winner_ign}**{score_str}"
            elif m.state == "ready":
                outcome = "🟢 *Match is ready to play!*"
            elif m.state == "bye":
                outcome = f"⏭️ *Auto-advanced: {m.winner_ign}*"
            else:
                outcome = "⚪ *Awaiting prior match results*"

            match_blocks.append(
                f"**`{m.match_id}`** {badge}\n"
                f"  ├ {p1_line}\n"
                f"  └ {p2_line}\n"
                f"  ↳ {outcome}"
            )

        # Discord field limit is 1024 characters; chunk matches into fields if needed
        current_chunk = []
        current_len = 0
        field_num = 1
        for block in match_blocks:
            if current_len + len(block) > 900:
                embed.add_field(
                    name=f"{round_header} (Part {field_num})",
                    value="\n\n".join(current_chunk),
                    inline=False,
                )
                current_chunk = [block]
                current_len = len(block)
                field_num += 1
            else:
                current_chunk.append(block)
                current_len += len(block) + 2

        if current_chunk:
            field_name = round_header if field_num == 1 else f"{round_header} (Part {field_num})"
            embed.add_field(name=field_name, value="\n\n".join(current_chunk), inline=False)

    embed.set_footer(text=f"{org} • DUKE Tournament Bracket Engine")
    return embed


__all__ = [
    "COLOR_EMERALD",
    "COLOR_CRIMSON",
    "COLOR_BLUE",
    "COLOR_ORANGE",
    "COLOR_GOLD",
    "COLOR_PURPLE",
    "COLOR_SLATE",
    "COLOR_TURQUOISE",
    "generate_progress_bar",
    "format_participant_line",
    "_chunk_lines",
    "build_status_embed",
    "build_config_embed",
    "build_roster_embed",
    "build_tournament_reminder_embed",
    "build_help_embed",
    "build_staff_panel_embed",
    "build_staff_guide_embed",
    "build_registration_panel_embed",
    "build_registration_closed_embed",
    "build_subs_panel_embed",
    "build_subs_closed_embed",
    "build_checkin_panel_embed",
    "build_checkin_receipt_embed",
    "build_bracket_embed",
]
