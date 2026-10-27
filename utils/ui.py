"""
Discord Embed and Visual Progress Bar UI Formatters for IDO Tournament Bot.
Matches the official IDO aesthetic, tournament status/roster layouts, and help guides.
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
    Builds the /tournament-status embed matching the official IDO layout.
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
    Builds the /tournament-roster embed matching the official IDO layout.
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

    embed.add_field(
        name=f"🛡️ Standby Substitutes ({sub_count})",
        value=sub_text,
        inline=False,
    )

    embed.set_footer(text=f"{org} • International Dueling Organization")
    return embed


def build_help_embed(
    section: str = "all",
    org_name: str | None = None,
    color: int | None = None,
) -> discord.Embed:
    """
    Builds the /tournament-help command manual.
    Sections: 'all', 'participants', 'admin', 'weapons_regions'.
    """
    org = org_name or config.organization_name
    embed_color = color or config.embed_color

    embed = discord.Embed(
        title=f"📖 {org} Tournament Bot — Command Manual",
        description=(
            "Welcome to the official **International Dueling Organization (IDO)** Tournament Bot.\n"
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
            "• `/tournament-status` — View registration status, slots & progress bar.\n"
            "• `/tournament-roster` — View full player list and check-in status."
        )
        embed.add_field(
            name="👥 Participant Commands",
            value=participant_cmds,
            inline=False,
        )

    if section in ("all", "admin"):
        admin_cmds = (
            "• `/tournament-open` — Open bracket, set capacity & region filters.\n"
            "• `/tournament-close` — Close main bracket registrations.\n"
            "• `/tournament-open-subs` / `/tournament-close-subs` — Toggle substitute signups.\n"
            "• `/tournament-open-checkin` / `/tournament-close-checkin` — Run check-in window.\n"
            "• `/tournament-promote-sub` — Swap a no-show player with standby sub.\n"
            "• `/tournament-kick` — Remove specific player from main or sub queue.\n"
            "• `/tournament-force-register` — Manually add a participant or VIP.\n"
            "• `/tournament-set-limit` — Adjust max participant capacity (e.g. 16, 32).\n"
            "• `/tournament-set-regions` — Update allowed regions filter.\n"
            "• `/tournament-set-weapons` — Set approved weapon classes for the event.\n"
            "• `/tournament-announce` — Broadcast announcement to players.\n"
            "• `/tournament-export` — Download CSV (Excel/Start.gg) or Challonge roster.\n"
            "• `/tournament-clear` — Wipe roster clean for next event."
        )
        embed.add_field(
            name="🛠️ Tournament Admin Controls",
            value=admin_cmds,
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

    embed.set_footer(text=f"{org} • International Dueling Organization")
    return embed

