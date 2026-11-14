"""
Discord Embed and Visual Progress Bar UI Formatters for UDA (United Dueling Amity) Tournament Bot.
Matches the official UDA aesthetic, tournament status/roster layouts, and help guides.
"""

from __future__ import annotations

from typing import Any

import discord

from config import config
from utils.tournament_embeds import (
    COLOR_BLUE,
    COLOR_CRIMSON,
    COLOR_EMERALD,
    COLOR_GOLD,
    COLOR_ORANGE,
    COLOR_PURPLE,
    COLOR_SLATE,
    COLOR_TURQUOISE,
    _chunk_lines,
    build_checkin_panel_embed,
    build_checkin_receipt_embed,
    build_help_embed,
    build_registration_closed_embed,
    build_registration_panel_embed,
    build_roster_embed,
    build_staff_guide_embed,
    build_staff_panel_embed,
    build_status_embed,
    build_subs_closed_embed,
    build_subs_panel_embed,
    build_tournament_reminder_embed,
    format_participant_line,
    generate_progress_bar,
)


def build_clan_role_panel_embed(clans: list[Any], org_name: str | None = None) -> discord.Embed:
    """
    Builds the interactive Clan Role Assignment Panel embed posted in #clan-roles / #choose-your-clan.
    Displays instructions, active verified clan count, and role switching rules.
    """
    org = org_name or config.organization_name
    count = len(clans)

    desc_lines = [
        "Welcome duelist! Claim your official clan alignment role below.",
        "Clan roles grant access to your team's private strategy war rooms, scrim channels, and roster pings.",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "**📋 How to Claim or Change Your Clan Role:**",
        "• **Dropdown Menu:** Pick your clan directly from the select menu below.",
        "• **Search by Keyword:** Click **`🔍 Search / Type Clan`** to type your clan name or tag.",
        "• **Switching Clans:** Selecting a new clan automatically removes your previous clan role.",
        "• **Clean Role Management:** Selecting a clan removes `@Clanless`. Leaving a clan restores `@Clanless`.",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🛡️ **Verified Registered Clans:** `{count}` active clan(s)",
    ]

    if count == 0:
        desc_lines.append("\n*No approved clans are currently registered. Use `/clan-submit` to submit a profile!*")

    embed = discord.Embed(
        title=f"🏛️ {org} Clan Alignment — Select Your Official Clan Role",
        description="\n".join(desc_lines),
        color=0x10B981,  # Emerald Green
    )
    embed.set_footer(text=f"{org} • Clan Alignment Directory")
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
    "build_roster_embed",
    "build_tournament_reminder_embed",
    "build_help_embed",
    "build_staff_panel_embed",
    "build_staff_guide_embed",
    "build_registration_panel_embed",
    "build_registration_closed_embed",
    "build_subs_panel_embed",
    "build_subs_closed_embed",
    "build_clan_role_panel_embed",
    "build_checkin_panel_embed",
    "build_checkin_receipt_embed",
]
