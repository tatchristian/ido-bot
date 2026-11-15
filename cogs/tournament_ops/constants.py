"""
Constants and choice definitions for tournament slash commands and operations.
"""

from discord import app_commands
from services.tournament_service import DEFAULT_WEAPONS, STANDARD_REGIONS

TIMEZONE_CHOICES = [
    app_commands.Choice(name="EST (UTC-5) - Eastern US", value="EST"),
    app_commands.Choice(name="EDT (UTC-4) - Eastern Daylight", value="EDT"),
    app_commands.Choice(name="CST (UTC-6) - Central US", value="CST"),
    app_commands.Choice(name="CDT (UTC-5) - Central Daylight", value="CDT"),
    app_commands.Choice(name="PST (UTC-8) - Pacific US", value="PST"),
    app_commands.Choice(name="PDT (UTC-7) - Pacific Daylight", value="PDT"),
    app_commands.Choice(name="UTC / GMT (UTC+0) - Universal", value="UTC"),
    app_commands.Choice(name="CET (UTC+1) - Central European", value="CET"),
    app_commands.Choice(name="CEST (UTC+2) - Central European Summer", value="CEST"),
    app_commands.Choice(name="BST (UTC+1) - British Summer", value="BST"),
    app_commands.Choice(name="GST (UTC+4) - Gulf Standard", value="GST"),
    app_commands.Choice(name="IST (UTC+5:30) - India Standard", value="IST"),
    app_commands.Choice(name="ICT / WIB (UTC+7) - Indochina / Western Indonesia", value="ICT"),
    app_commands.Choice(name="SGT / HKT (UTC+8) - Singapore / Hong Kong / Philippines", value="SGT"),
    app_commands.Choice(name="JST / KST (UTC+9) - Japan & Korea Standard", value="JST"),
    app_commands.Choice(name="AEST (UTC+10) - Australian Eastern", value="AEST"),
    app_commands.Choice(name="AEDT (UTC+11) - Australian Daylight", value="AEDT"),
    app_commands.Choice(name="NZST (UTC+12) - New Zealand Standard", value="NZST"),
    app_commands.Choice(name="BRT (UTC-3) - Brasilia Standard", value="BRT"),
]

WEAPON_CHOICES = [
    app_commands.Choice(name=w, value=w) for w in DEFAULT_WEAPONS
]

REGION_CHOICES = [
    app_commands.Choice(name=r, value=r) for r in STANDARD_REGIONS
]

REGION_FILTER_CHOICES = [
    app_commands.Choice(name="GLOBAL (All Regions Allowed)", value="GLOBAL"),
    app_commands.Choice(name="NA (North America)", value="NA"),
    app_commands.Choice(name="EU (Europe)", value="EU"),
    app_commands.Choice(name="OCE (Oceania)", value="OCE"),
    app_commands.Choice(name="ASIA (Asia)", value="ASIA"),
    app_commands.Choice(name="SA (South America)", value="SA"),
]

EXPORT_FORMAT_CHOICES = [
    app_commands.Choice(name="CSV (Excel / Start.gg / Battlefy)", value="csv"),
    app_commands.Choice(name="Challonge (Player Name List)", value="challonge"),
    app_commands.Choice(name="Formatted Text", value="text"),
]

EXPORT_TARGET_CHOICES = [
    app_commands.Choice(name="Main Bracket (For Challonge / Start.gg Import — Excludes Subs)", value="main"),
    app_commands.Choice(name="All (Full Roster with Substitutes)", value="all"),
    app_commands.Choice(name="Substitutes Only", value="subs"),
]

ANNOUNCE_TARGET_CHOICES = [
    app_commands.Choice(name="Main Bracket Only", value="main"),
    app_commands.Choice(name="Substitutes Only", value="subs"),
    app_commands.Choice(name="Everyone (Main + Subs)", value="all"),
]

HELP_SECTION_CHOICES = [
    app_commands.Choice(name="Overview (All Commands)", value="all"),
    app_commands.Choice(name="Participant Commands", value="participants"),
    app_commands.Choice(name="Admin Controls", value="admin"),
    app_commands.Choice(name="Setup & Server Configuration", value="setup"),
    app_commands.Choice(name="Weapons, Regions & Rules", value="weapons_regions"),
    app_commands.Choice(name="Clan Showcase & Submissions", value="clans"),
    app_commands.Choice(name="Events & Website Live Sync", value="events_sync"),
]

PANEL_CHOICES = [
    app_commands.Choice(name="Staff Operations Center", value="staff"),
    app_commands.Choice(name="Staff Interactive Guide", value="guide"),
    app_commands.Choice(name="Player Registration Hub", value="reg"),
    app_commands.Choice(name="Standby Substitutes Bench", value="subs"),
    app_commands.Choice(name="Match-Day Check-In Hub", value="checkin"),
    app_commands.Choice(name="Event Scheduler Panel", value="event_scheduler"),
    app_commands.Choice(name="Clan Profile Submission Portal", value="clan_submit"),
    app_commands.Choice(name="Clan Role Directory Panel", value="clan_roles"),
]
