# 🗺️ Master Mind Map: Architecture & Navigation Index

> Central navigation hub for the UDA / DUKE Tournament Bot (`ido-bot`).
> Use this index to jump directly to specific subsystem notes without reading entire code files.

---

## 📌 Subsystem Architecture Notes

| Note | Scope & Contents | Source File |
| :--- | :--- | :--- |
| [[tournaments_cog]] | Bracket management, slash commands, background reminder loops, and channel permissions. | `cogs/tournaments.py` |
| [[clan_showcase_cog]] | Clan profile submission, staff review panel (L749), self-serve clan role directory (L1362), automated role scanner (L2522), and `@Clanless` role enforcement. | `cogs/clan_showcase.py` |
| [[services_layer]] | `TournamentService` (bracket state, FIFO queue), `ClanShowcaseService` (approved clans), `WebsiteSyncService`, `ServerBuilder`. | `services/*.py` |
| [[ui_components]] | Extracted tournament UI: persistent views (`utils/tournament_views.py`), embed builders (`utils/tournament_embeds.py`), and facade (`utils/ui.py`). | `utils/` |
| [[testing_suite]] | Pytest test suite breakdown across all 7 test modules and execution standards. | `tests/*.py` |
| [[architecture_map]] | Complete consolidated code index with line-by-line function, class, and command pointers. | Full repository |

---

## ⚡ Operational Workflow Notes

| Note | Purpose & Flow |
| :--- | :--- |
| [[workflow_tournament_panel_sync]] | Explains how Staff Panel actions (e.g. `Toggle Subs`) dynamically edit live channel embeds in real time. |
| [[workflow_user_registration]] | Documents the single modal registration flow and active Region Tag mismatch validation. |
| [[workflow_clan_role_directory]] | Documents self-serve clan alignment, 25-option select chunking, search modal, automated role scanner, and `@Clanless` switching rules. |
| [[workflow_bracket_system]] | Documents the Single/Double elimination bracket engine, out-of-order ready match pipeline, Supabase cloud sync, and Herald REST API. |
