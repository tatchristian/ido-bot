# 🏆 Tournament Bracket & Cumulative Match History System

**Architecture Document & Operational Runbook**
**Files:** `services/bracket_engine.py`, `services/match_history_service.py`, `services/api_server.py`, `utils/tournament_views.py`, `utils/tournament_embeds.py`, `cogs/tournament_ops/staff_cmds.py`
**Backlink:** [[index]] | [[services_layer]] | [[tournaments_cog]]

---

## 📌 System Overview
The tournament bracket system equips DUKE with an automated esports bracket pipeline:
1. **Dynamic Draft Mode:** The bracket tree automatically builds and adjusts in draft mode as players register (`/register`) or withdraw (`/unregister`).
2. **Dual Format:** Supports **Single Elimination** and **Double Elimination** with an interactive toggle button.
3. **Soft Check-In:** All registered players are seeded into the tree regardless of check-in status. Status badges (`[✅]` vs `[⏳]`) visually display check-in presence.
4. **Out-of-Order Match Play:** Matches become `READY` the moment both opponent slots are known, letting fast brackets advance without waiting for delayed earlier matches.
5. **Grand Finals Reset:** In Double Elimination, if the Losers Bracket champion wins Grand Finals Game 1, a `GF-RESET` match is created automatically.
6. **Cumulative Match Ledger:** Every completed duel is permanently recorded to **Supabase** cloud database (`tournament_matches` table) and local disk (`data/match_history.json`).
7. **External REST API:** Exposes endpoints (`/matches`, `/matches/stats`) for the companion bot (**Herald**) to ingest wins and calculate Clan Banner Points.

---

## 🌳 Bracket Engine (`services/bracket_engine.py`)
- **Seeding:** Standard tournament pairing (`[1, 4, 2, 3]` for 4 players; `[1, 8, 4, 5, 2, 7, 3, 6]` for 8) so Seed 1 and Seed 2 meet only in the Finals.
- **Power of 2 & Odd Rosters:** Automatically rounds up to nearest power of 2 (2, 4, 8, 16, 32, 64) and fills remaining slots with `BYE`. Supports arbitrary odd or even contestant counts (e.g. 3, 5, 7, 9, 11).
- **Automatic Byes:** Byes are automatically resolved during `evaluate_ready_states()`, advancing seeded contestants immediately. In Double Elimination, unplayed BYE matches propagate a `BYE` into the corresponding Losers Bracket slot via `_drop_bye_loser()`, auto-advancing losers and preventing bracket stall.
- **Double Elimination Routing:**
  - Losers of `WB-R1` drop to `LB-R1`.
  - Losers of `WB-R{r}` (`r >= 2`) drop to `LB-R{2*(r-1)}` in slot 1.
  - Winner of Losers Finals advances to `GF` slot 2.
- **Downstream Undo Protection:**
  - Reverting a match checks both the winner's downstream match and the loser's downstream match.
  - If either downstream match has already been played, undo is blocked until downstream matches are reverted.
  - Reverting clears downstream slots back to `TBD` and `pending`.

---

## 🗄️ Match History & Supabase Ledger (`services/match_history_service.py`)
- **Cloud Database:** Connects to Supabase via `aiohttp` over HTTPS REST (port 443) using `SUPABASE_URL` and `SUPABASE_KEY`.
- **Local Fallback:** Writes to `data/match_history.json` with atomic rename and 60-second backup rotation throttling.
- **Collision-Proof Match IDs:** Formatted as `{guild_id}_{state.tournament_id}_{match_id}` (e.g. `123_a1b2c3d4_WB-R1-M1`). Rotating `tournament_id` on tournament reset ensures consecutive tournaments never collide in Supabase.
- **Non-Destructive Voids:** When a match is undone or disputed, `is_void = true` is set with a reason rather than hard-deleting the row, preserving audit trails.
- **Aggregation:** `get_player_stats()` computes total wins, losses, win rates, and active winning streaks.

---

## 🌐 Public REST API Endpoints (`services/api_server.py`)
- **`GET /matches` (or `/api/matches`):**
  - Query parameters: `?since=...&player=...&clan=...&tournament=...&limit=...`
  - Returns array of match records with CORS headers enabled (`Access-Control-Allow-Origin: *`).
- **`GET /matches/stats` (or `/api/matches/stats`):**
  - Returns aggregated leaderboard stats (wins, losses, current win streaks) consumed by Herald bot.

---

## 🎛️ Interactive Discord UI (`utils/tournament_views.py`, `utils/tournament_embeds.py`)
- **Bracket Panel View:** `TournamentBracketPanelView`
  - `◀️ Prev` / `Next ▶️`: Page through tournament rounds.
  - `🏆 Winners` / `🛡️ Losers` / `👑 Finals`: Switch division views in Double Elimination.
  - `⚔️ Record Match`: Opens `TournamentMatchReportSelectView` listing all currently `READY` matches.
  - `🔀 Shuffle`: Randomizes seeds (draft mode only).
  - `Format: Single/Double`: One-click toggle between elimination types (draft mode only).
  - `🔒 Lock Bracket` / `🔓 Unlock Bracket`: Toggles between draft mode (auto-updating with registrations) and live tournament mode.
  - `🔄 Refresh`: Redraws the bracket embed in-place.
- **Match Reporting View:** `TournamentMatchReportSelectView`
  - Dropdown of all `READY` matches.
  - On match selection, opens buttons: `🏆 Player 1 Won`, `🏆 Player 2 Won`, `🏳️ Forfeit Player 1`, `🏳️ Forfeit Player 2`.
  - Winner buttons launch `TournamentMatchReportModal` to input optional score (e.g. `2-0`, `2-1`).
  - Automatically updates the public bracket panel embed upon submission.

---

## ⌨️ Commands (`cogs/tournament_ops/staff_cmds.py`)
- **Slash Commands (`/bracket` Group):**
  - `/bracket view [section] [round]`
  - `/bracket lock`
  - `/bracket unlock`
  - `/bracket format <single|double>`
  - `/bracket shuffle`
  - `/bracket report <match_id> <winner> [score]`
  - `/bracket undo <match_id>`
  - `/bracket forfeit <match_id> <player>`
  - `/bracket test [mode] [count] [bracket_format]` — Automated diagnostic self-test: probes Supabase cloud DB (Insert/Select/Patch/Delete) and/or seeds 2 to 16 mock duelists with live bracket panel.
  - `/post panel:Live Tournament Bracket Panel`
- **Prefix Fallbacks:**
  - `!t_bracket [section] [round]`
  - `!t_report <match_id> <@winner> [score]`
  - `!t_undo <match_id>`
  - `!t_forfeit <match_id> <@player>`
  - `!t_test [full|cloud|mock|cleanup] [count] [single|double]` — Prefix fallback for diagnostic probe and mock bracket generator.

---

## 🧹 Lifecycle & Wipes
- Calling `/t clear` wipes:
  - Active participants and substitutes.
  - `bracket_data = None`.
  - Clears stored panel message and channel IDs.
  - Rotates `tournament_id = uuid.uuid4().hex[:8]` so the next tournament starts fresh with unique match IDs.
