# 🧪 Testing Suite Memory Node

**Directory:** `tests/`
**Backlink:** [[index]] | [[services_layer]] | [[tournaments_cog]] | [[clan_showcase_cog]]

---

## 📋 Test Modules Overview
- `tests/test_ui.py`:
  - Embed builders for status, rosters, reminders, and help menus.
  - Interactive player registration and substitute queue hubs (`build_registration_panel_embed`, `build_subs_panel_embed`).
  - Progress bar generation and participant formatting.
- `tests/test_tournament_service.py`:
  - Tournament lifecycle: create, configure, open/close registrations, sub bench toggles.
  - Slot capacity limits, participant registration/unregistration, and check-in confirmation.
  - Standby substitute FIFO promotion logic.
- `tests/test_clan_showcase.py`:
  - Clan profile submissions, modal parsing, and hex color validation.
  - Staff review actions (approve & publish, rejection feedback).
  - Self-serve clan role directory (`ClanRoleSelect` auto-chunking, `ClanSearchModal`).
  - `@Clanless` role assignment and removal on clan claim/leave.
- `tests/test_storage.py`:
  - `StorageManager` atomic writes, JSON serialization, and backup recovery.
- `tests/test_website_sync.py`:
  - `WebsiteSyncService` REST payloads and sync endpoints.
- `tests/test_server_builder.py`:
  - Category creation, dueling arena setup, and cleanup rollback view.
- `tests/test_api_server.py`:
  - Internal API routes and health endpoints.

---

## ⚡ Execution Command
Always run unit tests in quiet mode to minimize output tokens:
```bash
pytest -q
```
