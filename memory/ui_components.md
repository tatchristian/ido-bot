# 🎨 UI Components & Embeds Memory Node

**File Path:** `utils/ui.py` (~860 lines)
**Backlink:** [[index]] | [[tournaments_cog]] | [[clan_showcase_cog]]

---

## 📊 Live Progress & Formatters
- `generate_progress_bar()`: `L13` (Draws visual ASCII bracket meter, e.g. `[████░░░░] 6/16`)
- `format_participant_line()`: `L38` (Renders numbered contestant line with check-in badges)
- `build_status_embed()`: `L48` (Live tournament progress & status embed)
- `build_roster_embed()`: `L134` (Full registered main bracket & substitute roster)

---

## 🎛️ Panel Embed Builders
- `build_staff_panel_embed()`: `L472` (Official DUKE Tournament Staff Operations Panel)
- `build_staff_guide_embed()`: `L499` (Tournament Staff Phase manual)
- `build_registration_panel_embed()`: `L659` (Player Registration Hub embed)
- `build_registration_closed_embed()`: `L722` (Registration closed notice)
- `build_subs_panel_embed()`: `L764` (Standby Substitute Queue Hub embed)
- `build_subs_closed_embed()`: `L802` (Substitutes closed notice)
- `build_clan_role_panel_embed()`: `L828` (Official Clan Alignment Directory embed)
