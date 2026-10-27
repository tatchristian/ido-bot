"""
Discord Embed and Visual Progress Bar UI Formatters for IDO Tournament Bot.
Matches the official IDO aesthetic and tournament status/roster layouts.
"""

from __future__ import annotations

import discord
from config import config
from services.tournament_service import Participant, TournamentState


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


def format_participant_line(index: int, p: Participant) -> str:
    """
    Formats a single participant entry:
    `#01` **IGN** (<@user_id>) — `Weapon` | *Region*
    """
    num_str = f"#{index:02d}"
    return f"`{num_str}` **{p.ign}** ({p.user_mention}) — `{p.weapon}` | *{p.region}*"


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
    cur_slots = len(state.participants)
    max_slots = state.max_slots
    bar = generate_progress_bar(cur_slots, max_slots, bar_length=8)
    sub_count = len(state.substitutes)
    regions_str = ", ".join(state.allowed_regions)

    desc_lines = [
        f"**Main Bracket Submissions:** {main_status}",
        f"**Substitute Signups:** {subs_status}",
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

    # Approved weapons field
    weapons_text = "\n".join(f"• `{w}`" for w in state.approved_weapons)
    embed.add_field(
        name="Approved Weapons",
        value=weapons_text or "• All weapons allowed",
        inline=True,
    )

    # Quick commands field
    commands_text = (
        "• `/tournament-register` — Enter main bracket\n"
        "• `/tournament-sub-register` — Enter as substitute\n"
        "• `/tournament-roster` — View full roster"
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

    desc_lines = [
        f"**Main Slots:** `{cur_slots} / {max_slots}`",
        f"{bar}",
    ]

    embed = discord.Embed(
        title=f"📋 {state.name} — Tournament Roster",
        description="\n".join(desc_lines),
        color=embed_color,
    )

    # Main bracket field
    if state.participants:
        main_lines = [
            format_participant_line(i + 1, p)
            for i, p in enumerate(state.participants)
        ]
        # Chunk if exceeds Discord 1024-char field limit
        main_text = "\n".join(main_lines)
        if len(main_text) > 1024:
            main_text = main_text[:1020] + "..."
    else:
        main_text = "*No participants registered yet.*"

    embed.add_field(
        name=f"⚔️ Main Bracket ({cur_slots})",
        value=main_text,
        inline=False,
    )

    # Substitutes field
    sub_count = len(state.substitutes)
    if state.substitutes:
        sub_lines = [
            format_participant_line(i + 1, s)
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
