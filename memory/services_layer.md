# 🗄️ Services Layer Memory Node

**Files:** `services/*.py`
**Backlink:** [[index]] | [[tournaments_cog]] | [[clan_showcase_cog]]

---

## 🏆 `TournamentService` (`services/tournament_service.py`)
- `class Participant`: `L37` (`user_id`, `ign`, `weapon`, `region`, `checked_in`, `timestamp`)
- `class TournamentState`: `L67` (Slots, channels, message IDs, rosters, weapons, schedule)
- `class TournamentService`: `L175`
  - `configure_tournament()`: `L185` (Sets parameters, participant role, registration channel)
  - `open_tournament()` / `close_tournament()`: `L215` / `L240`
  - `open_subs()` / `close_subs()`: `L255` / `L275`
  - `register_participant()` / `unregister_participant()`: `L310` / `L355`
  - `register_substitute()` / `unregister_substitute()`: `L385` / `L430`
  - `promote_substitute()`: `L455` (Advances next sub from queue into main bracket)
  - `set_channels()`: `L500` (Stores persistent channel IDs)
  - `save_roster_preset()`: `L1047` (Exports active roster snapshot to preset JSON file, e.g. `saved_roster.json`)
  - `import_roster_preset()`: `L1072` (Imports & restores roster parameters, participants & subs from preset file)
  - `bulk_register()`: `L1128` (Batch-enrolls duelists from delimited string/list with auto fallback defaults)
  - `_persist(guild_id)`: Saves to `storage/tournaments_{guild_id}.json`

---

## 🛡️ `ClanShowcaseService` (`services/clan_showcase_service.py`)
- `class ClanSubmission`: `L339` (Includes `role_id`, `role_name`, `logo_url`, `status`)
- `class ClanShowcaseService`: `L406`
  - `get_approved_clans(guild_id)`: `L468` (Alphabetical list of verified clans)
  - `set_clan_role(sub_id, role_id, role_name)`: `L474`
  - `set_clan_role_panel_info()` / `get_clan_role_panel_info()`: `L483` / `L490`
  - `set_clanless_role_id()` / `get_clanless_role_id()`: `L495` / `L501`
  - `delete_submission(sub_id)`: `L647` (Deletes clan from registry and saves to disk)
  - `_persist()`: Saves to `storage/clan_showcases.json`

---

## 🌐 Other Specialized Services
- **`WebsiteSyncService` (`services/website_sync_service.py`):** `L341` (REST sync to `unitedduelingamity.org`)
- **`StateSnapshotService` (`services/state_snapshot_service.py`):** Saves, restores, and regex auto-discovers server channels, roles, and panels across deployments (`saved_state.json`)
- **`ServerBuilder` (`services/server_builder.py`):** Auto-creates categories and dueling arenas
- **`PastResultsService` (`services/past_results_service.py`):** Concluded tournaments archive
