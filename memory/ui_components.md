# 🎨 UI Components & Embeds Memory Node

**File Paths:**
- `utils/tournament_embeds.py` (~1,134 lines) — Pure tournament embed builders & visual meter formatters (Tier 1)
- `utils/tournament_views.py` (~1,994 lines) — Persistent interactive Discord views, components, modals & permission checks (Tier 2)
- `utils/ui.py` (~100 lines) — Compatibility bridge re-exporting all tournament builders alongside `build_clan_role_panel_embed`
**Backlink:** [[index]] | [[tournaments_cog]] | [[clan_showcase_cog]]

---

## 📊 Live Progress & Formatters (`utils/tournament_embeds.py`)
- `COLOR_*`: Standard color palette constants (`COLOR_EMERALD`, `COLOR_CRIMSON`, `COLOR_BLUE`, `COLOR_ORANGE`, `COLOR_GOLD`, `COLOR_PURPLE`, `COLOR_SLATE`, `COLOR_TURQUOISE`)
- `generate_progress_bar()`: Draws visual ASCII bracket meter, e.g. `[████░░░░] 50%`
- `format_participant_line()`: Renders numbered contestant line with check-in badges
- `_chunk_lines()`: Splits formatted contestant lines into sub-1000 char blocks for Discord embed fields
- `build_status_embed()`: Live tournament progress & status embed
- `build_roster_embed()`: Full registered main bracket & substitute roster; paginates large 16+ / 32 player brackets across multiple embed fields to prevent 1024-char truncation
- `build_tournament_reminder_embed()`: Direct message (DM) alert for day-of and 30-min reminders

---

## 🎛️ Panel Embed Builders (`utils/tournament_embeds.py`)
- `build_staff_panel_embed()`: Official DUKE Tournament Staff Operations Panel
- `build_staff_guide_embed()`: Tournament Staff Phase manual with 9 interactive phases: Overview, Panels, Phase 1-4, Checklist, State Persistence, and Roles
- `build_registration_panel_embed()`: Player Registration Hub embed
- `build_registration_closed_embed()`: Registration closed notice
- `build_subs_panel_embed()`: Standby Substitute Queue Hub embed
- `build_subs_closed_embed()`: Substitutes closed notice
- `build_checkin_panel_embed()`: Live match-day check-in hub displaying attendance stats (`X/Y Checked In`), visual progress bar, standby sub availability, and match start countdown
- `build_checkin_receipt_embed()`: Audit receipt embed dispatched to `#checkin-logs` tracking contestant, IGN, weapon, region, status, and optional staff moderator

---

## 🏛️ Clan Role Embed (`utils/ui.py`)
- `build_clan_role_panel_embed()`: Official Clan Alignment Directory embed for #clan-roles / #choose-your-clan
