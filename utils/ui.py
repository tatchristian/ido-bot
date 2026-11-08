"""
Discord Embed and Visual Progress Bar UI Formatters for UDA (United Dueling Amity) Tournament Bot.
Matches the official UDA aesthetic, tournament status/roster layouts, and help guides.
"""

from __future__ import annotations

import discord
from config import config
from services.tournament_service import DEFAULT_WEAPONS, STANDARD_REGIONS, Participant, TournamentState


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


def build_status_embed(
    state: TournamentState,
    org_name: str | None = None,
    color: int | None = None,
) -> discord.Embed:
    """
    Builds the /tournament-status embed matching the official UDA layout.
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
        "• `/tournament-register` — Enter main bracket\n"
        "• `/tournament-sub-register` — Enter as substitute\n"
        "• `/tournament-roster` — View full roster\n"
        "• `/tournament-checkin` — Confirm tournament day check-in\n"
        "• `/help` — View interactive command manual"
    )
    embed.add_field(
        name="Quick Commands",
        value=commands_text,
        inline=True,
    )

    embed.set_footer(text=f"{org} • Tournament System")
    return embed


def build_roster_embed(
    state: TournamentState,
    org_name: str | None = None,
    color: int | None = None,
) -> discord.Embed:
    """
    Builds the /tournament-roster embed matching the official UDA layout.
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

    if state.participants:
        main_lines = [
            format_participant_line(i + 1, p, show_checkin=show_checkin)
            for i, p in enumerate(state.participants)
        ]
        main_text = "\n".join(main_lines)
        if len(main_text) > 1024:
            main_text = main_text[:1020] + "..."
    else:
        main_text = "*No participants registered yet.*"

    checked_in_count = sum(1 for p in state.participants if p.checked_in)
    bracket_title = (
        f"⚔️ Main Bracket ({cur_slots} registered • {checked_in_count} checked in)"
        if show_checkin
        else f"⚔️ Main Bracket ({cur_slots})"
    )

    embed.add_field(
        name=bracket_title,
        value=main_text,
        inline=False,
    )

    sub_count = len(state.substitutes)
    sub_checked_count = sum(1 for s in state.substitutes if s.checked_in)
    if state.substitutes:
        sub_lines = [
            format_participant_line(i + 1, s, show_checkin=show_checkin)
            for i, s in enumerate(state.substitutes)
        ]
        sub_text = "\n".join(sub_lines)
        if len(sub_text) > 1024:
            sub_text = sub_text[:1020] + "..."
    else:
        sub_text = "*No substitutes on deck.*"

    sub_title = (
        f"🛡️ Standby Substitutes ({sub_count} standby • {sub_checked_count} ready [✅])"
        if show_checkin
        else f"🛡️ Standby Substitutes ({sub_count})"
    )

    embed.add_field(
        name=sub_title,
        value=sub_text,
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
    Builds the /tournament-help command manual.
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
            "• `/tournament-register` — Enter the main tournament bracket.\n"
            "• `/tournament-unregister` — Withdraw and free up your bracket slot.\n"
            "• `/tournament-sub-register` — Join standby substitute queue.\n"
            "• `/tournament-sub-unregister` — Withdraw from substitute queue.\n"
            "• `/tournament-edit-entry` — Update weapon, IGN, or region without losing slot.\n"
            "• `/tournament-checkin` — Confirm presence during tournament check-in.\n"
            "• `/tournament-sub-checkin` — Confirm availability as a standby substitute.\n"
            "• `/tournament-status` — View registration status, slots & progress bar.\n"
            "• `/tournament-roster` — View full player list and check-in status."
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
                "• `/tournament-open` — Open bracket, set capacity, regions & optional channel.\n"
                "• `/tournament-close` — Close main bracket registrations.\n"
                "• `/tournament-open-subs` / `/tournament-close-subs` — Toggle substitute signups.\n"
                "• `/tournament-open-checkin` / `/tournament-close-checkin` — Run check-in window.\n"
                "• `/tournament-promote-sub` — Swap no-show player with standby sub (with autocomplete).\n"
                "• `/tournament-kick` — Remove player from main or sub queue (with autocomplete).\n"
                "• `/tournament-announce` — Broadcast announcement to players.\n"
                "• `/tournament-clear` — Wipe roster clean for next event."
            )
            embed.add_field(
                name="🛠️ Tournament Admin Controls — Operations",
                value=admin_lifecycle,
                inline=False,
            )

            admin_config = (
                "• `/tournament-set-time` — Set match day date, time & timezone for contestant reminders.\n"
                "• `/tournament-view-time` — View match schedule & reminder delivery stats.\n"
                "• `/tournament-test-reminder` — Send preview Day-Of or 30-min DM to yourself.\n"
                "• `/tournament-force-register` — Manually add a participant or VIP.\n"
                "• `/tournament-set-limit` — Adjust max participant capacity (e.g. 16, 32).\n"
                "• `/tournament-set-regions` — Update allowed regions filter.\n"
                "• `/tournament-set-weapons` — Set approved weapon classes for the event.\n"
                "• `/tournament-export` — Download CSV (Excel/Start.gg) or Challonge roster."
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
                "• `/tournament-setup-section` (or `!tournament_setup_section`) — One-click setup wizard creating category & channels automatically.\n"
                "• `/tournament-set-channels` — Link dedicated channels for announcements, registration, checkin, subs.\n"
                "• `/tournament-set-channel` (or `!set_channel`) — Quickly set or re-link a specific channel.\n"
                "• `/tournament-view-channels` — View configured tournament channels and status.\n"
                "• `/tournament-set-admin-role` (or `!set_admin_role`) — Configure staff role required for tournament admin.\n"
                "• `/tournament-view-admin-role` — View current authorized tournament staff role.\n"
                "• `/tournament-set-event-role` (or `/set-event-role`) — Configure role authorized for event scheduling & sync.\n"
                "• `/tournament-view-event-role` — View current authorized event manager role.\n"
                "• `/tournament-set-role` / `/tournament-view-role` — Configure automatic contestant role."
            )
            embed.add_field(
                name="⚙️ Server Setup & Channels",
                value=setup_channels,
                inline=False,
            )

            setup_panels = (
                "• `/post-tournament-staff-panel` — Post 1-click Staff Control Center panel.\n"
                "• `/post-staff-guide` — Post interactive Staff Guide with phase dropdown selector.\n"
                "• `/post-event-scheduler-panel` — Post 1-click Event Scheduler for banners & web sync.\n"
                "• `/post-clan-submission-panel` — Post interactive Clan Showcase intake portal.\n"
                "• `/clan-showcase-channels` — Configure showcase and staff review channels for clans.\n"
                "• `/clan-showcase-view-channels` — View configured clan showcase channels."
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
            "• `/clan-submit` — Submit or draft your clan profile (choose photo/GIF directly from phone or paste link).\n"
            "• `/post-clan-submission-panel` (or `!post_clan_submission_panel`) — Post interactive submission panel with persistent buttons.\n"
            "• `/clan-showcase-channels` — Configure target showcase and staff review channels.\n"
            "• `/clan-showcase-view-channels` — View current configured channels for submissions.\n"
            "• `/clan-showcase-edit` — Edit any existing clan profile live (updates database & published embed).\n"
            "• `/clan-showcase-preview` — Test embed rendering with custom colors and artwork.\n"
            "• **Clan Intake Flow:** Leaders submit via `/clan-submit` or click **`📋 Submit Clan Profile`** on the panel.\n"
            "• **Staff Workflow:** Review submissions with **`Approve & Publish`** or **`Reject`** (with custom reason prompt)."
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
                "• `/tournament-set-event-role` (or `/set-event-role`) — Set or clear specific role authorized for event scheduling & website sync.\n"
                "• `/tournament-view-event-role` — View which role is currently authorized for event controls.\n"
                "• `/post-event-scheduler-panel` (or `!post_event_scheduler_panel`) — Post interactive 1-click event scheduler panel in staff channels.\n"
                "• `/tournament-schedule-event` — Schedule an official Discord server event (displayed at the top of the server banner).\n"
                "• `/tournament-cancel-event` — Cancel and delete an upcoming event (removes from Discord & website schedule).\n"
                "• `/tournament-complete-event` — Conclude a tournament, crown champion & runner-up, and publish to website Past Results.\n"
                "• `/tournament-remove-past-result` — Delete an archived result from the website Past Results list.\n"
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
            "• 🟢 **Open Bracket** — Open registrations, set slots & regions via popup form.\n"
            "• 🔒 **Close Bracket** — Lock registrations to finalize bracket entries.\n"
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
    Supports individual phase views ('overview', 'phase_1', 'phase_2', 'phase_3', 'phase_4', 'roles', 'all').
    """
    org = org_name or config.organization_name
    full_name = getattr(config, "organization_full_name", "United Dueling Amity")

    sec = section.lower().strip()

    if sec == "phase_1":
        embed = discord.Embed(
            title=f"1️⃣ {org} Staff Guide — Phase 1: Pre-Tournament Setup",
            description=(
                "**Prepare brackets, schedule matches, and configure participant roles.**\n\n"
                "• **Open Registrations:** Click `🟢 Open Registrations` on the Staff Panel or run `/tournament-open`. "
                "Specify capacity (e.g. 16), regions, and whether the standby substitute queue is active.\n\n"
                "• **Configure Match Day & Time:** Run `/tournament-set-time` or click `⏰ Set Match Time`. "
                "This arms the automated DM system to notify contestants on match day morning and 30 minutes before start time.\n\n"
                "• **Automatic Participant Role:** The bot automatically creates and assigns `@{Tournament} Participant` "
                "to every entrant upon registration, making announcement pings effortless.\n\n"
                "• **Weapons & Region Filters:** Restrict allowed weapons via `/tournament-set-weapons` and regions via `/tournament-set-regions`."
            ),
            color=0x2ECC71,
        )
    elif sec == "phase_2":
        embed = discord.Embed(
            title=f"2️⃣ {org} Staff Guide — Phase 2: Registration & Roster Monitoring",
            description=(
                "**Monitor entries, add VIPs manually, and remove rule-breakers.**\n\n"
                "• **Real-Time Bracket Status:** Click `📊 Roster & Status` on the panel (ephemeral) or run `/tournament-status` "
                "to monitor filled slots, substitute counts, and registration state.\n\n"
                "• **Player Autocomplete Kick:** Run `/tournament-kick user:` — type the first 1-2 letters of any player's IGN "
                "to select them directly from the dropdown (`[Main]`, `[Sub]`). Mentions and raw user IDs also work.\n\n"
                "• **Admin Manual Entry:** Use `/tournament-force-register` to bypass open registration windows and directly "
                "seed contestants or VIPs into the main bracket or substitute queue."
            ),
            color=0x3498DB,
        )
    elif sec == "phase_3":
        embed = discord.Embed(
            title=f"3️⃣ {org} Staff Guide — Phase 3: Match Day, Check-In & Substitutes",
            description=(
                "**Manage match day check-ins, automated reminders, and substitute promotions.**\n\n"
                "• **Automated Player DMs:** Contestants automatically receive personal DMs on tournament morning "
                "and 30 minutes before match time showing their selected region and Discord's live dynamic timestamp.\n\n"
                "• **Check-In Window:** Click `🎟️ Toggle Check-In` on the panel or run `/tournament-open-checkin` to allow "
                "registered players and standby substitutes to confirm readiness via `/tournament-checkin`.\n\n"
                "• **Promote Standby Substitutes:** Click `🔄 Promote Sub` on the panel to instantly advance the next sub in line, "
                "or use `/tournament-promote-sub` with full autocomplete showing `[✅ Ready]` vs `[⏳ No-show]`.\n\n"
                "• **Broadcast Announcements:** Click `📢 Announce` on the panel to open the broadcast modal with optional role mention."
            ),
            color=0xF1C40F,
        )
    elif sec == "phase_4":
        embed = discord.Embed(
            title=f"4️⃣ {org} Staff Guide — Phase 4: Concluding & Archiving",
            description=(
                "**Crown champions, export brackets, sync to website, and reset.**\n\n"
                "• **Crown Champion & Website Sync:** Run `/tournament-complete-event` to record the tournament champion. "
                "The result automatically syncs to [unitedduelingamity.org](https://unitedduelingamity.org) and server feeds.\n\n"
                "• **Export CSV Rosters:** Run `/tournament-export` to generate instant Challonge and spreadsheet-compatible CSV files.\n\n"
                "• **Wipe Bracket for Next Event:** Run `/tournament-clear` (ephemeral) to wipe the active roster, delete the "
                "temporary participant role, and prepare for the next tournament cycle."
            ),
            color=0x9B59B6,
        )
    elif sec == "roles":
        embed = discord.Embed(
            title=f"🛡️ {org} Staff Guide — Role Permissions Reference",
            description=(
                "**Understand permission boundaries and authorizations across staff tiers.**\n\n"
                "• **Tournament Admin Role (`/tournament-set-admin-role`):**\n"
                "  Authorized for tournament operations: staff panel, registrations, check-in, kicks, match schedules, and roster controls.\n"
                "  *Strictly restricted from server administrative settings, clan approvals, or website event feeds.*\n\n"
                "• **Event & Website Role (`/tournament-set-event-role`):**\n"
                "  Authorized for scheduling official Discord server banner events and pushing public schedule updates to the website.\n\n"
                "• **Server Administrator:**\n"
                "  Server Owner and members with Discord `Administrator` permissions. Full access to system building, role assignments, and resets."
            ),
            color=0xE67E22,
        )
    elif sec == "all":
        embed = discord.Embed(
            title=f"📖 {org} Tournament Staff Operational Guide & Cheat Sheet",
            description=(
                f"Welcome to the **{full_name} ({org})** Staff Operations Manual.\n"
                "Pin this message in your staff channels for quick access and mod onboarding.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0x3498DB,
        )
        embed.add_field(
            name="1️⃣ Phase 1: Pre-Tournament Setup",
            value=(
                "• **Open Registrations:** Click `🟢 Open Registrations` or `/tournament-open`.\n"
                "• **Set Match Time:** Set date & time via `/tournament-set-time` for automated DMs.\n"
                "• **Auto-Role:** Bot automatically assigns `@{Tournament} Participant` to players.\n"
                "• **Weapons & Regions:** Limits via `/tournament-set-weapons` & `/tournament-set-regions`."
            ),
            inline=False,
        )
        embed.add_field(
            name="2️⃣ Phase 2: Registration & Roster Monitoring",
            value=(
                "• **Monitor Slots:** Check status with `/tournament-status` or the `📊 Roster & Status` button.\n"
                "• **Quick Kicking:** Use `/tournament-kick` with instant player autocomplete.\n"
                "• **Manual Entry:** Use `/tournament-force-register` to add VIPs or participants manually."
            ),
            inline=False,
        )
        embed.add_field(
            name="3️⃣ Phase 3: Match Day & Reminders",
            value=(
                "• **Automated DMs:** Contestants receive DMs on match day and 30m before start.\n"
                "• **Check-In Window:** Click `🎟️ Toggle Check-In` on the panel or `/tournament-open-checkin`.\n"
                "• **Swap No-Shows:** Use `/tournament-promote-sub` or click `🔄 Promote Sub`.\n"
                "• **Player Pings:** Use `/tournament-announce` to broadcast notices into announcement channels."
            ),
            inline=False,
        )
        embed.add_field(
            name="4️⃣ Phase 4: Concluding & Archiving",
            value=(
                "• **Record Champions:** Use `/tournament-complete-event` to crown the winner and publish to website.\n"
                "• **Export Records:** Use `/tournament-export` to download Challonge/Excel CSV rosters.\n"
                "• **Wipe Roster:** Use `/tournament-clear` (ephemeral) to prep for the next cycle."
            ),
            inline=False,
        )
        embed.add_field(
            name="🛡️ Role Permissions Reference",
            value=(
                "• **Tournament Admin Role (`/tournament-set-admin-role`):** Operations, bracket runner, check-in & kicks.\n"
                "• **Event & Website Role (`/tournament-set-event-role`):** Server banner events & website publishing.\n"
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
                "• 1️⃣ **Phase 1: Pre-Tournament Setup** — Bracket setup, time scheduling & auto-roles\n"
                "• 2️⃣ **Phase 2: Registration & Roster** — Slot capacity monitoring & player autocomplete kicks\n"
                "• 3️⃣ **Phase 3: Match Day & Reminders** — Automated contestant DMs, check-in & sub swaps\n"
                "• 4️⃣ **Phase 4: Concluding & Archiving** — Crown champions, export rosters & clean resets\n"
                "• 🛡️ **Role Permissions Reference** — Tournament Admin vs. Event & Website staff boundaries\n\n"
                "💡 *Select an operational phase below to view step-by-step guidance.*"
            ),
            color=0x3498DB,
        )

    embed.set_footer(text=f"{org} • Staff Operations Manual")
    return embed

