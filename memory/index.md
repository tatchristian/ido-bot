# 🗺️ Master Mind Map: Architecture & Navigation Index

> Central navigation hub for the UDA / DUKE Tournament Bot (`ido-bot`).
> Use this index to jump directly to specific subsystem notes without reading entire code files.

---

## 📌 Subsystem Architecture Notes

| Note | Scope & Contents | Source File |
| :--- | :--- | :--- |
| [[tournaments_cog]] | Bracket management, Staff Operations Panel (L3896), Player Registration Hub (L4415), Substitute Hub (L4709), and slash commands. | `cogs/tournaments.py` |
| [[clan_showcase_cog]] | Clan profile submission, staff review panel (L749), self-serve clan role directory (L1362), automated role scanner (L2522), and `@Clanless` role enforcement. | `cogs/clan_showcase.py` |
| [[services_layer]] | `TournamentService` (bracket state, FIFO queue), `ClanShowcaseService` (approved clans), `WebsiteSyncService`, `ServerBuilder`. | `services/*.py` |
| [[ui_components]] | Embed builders (`utils/ui.py`), ASCII progress bars, participant formatters, and closed panel notices. | `utils/ui.py` |
| [[testing_suite]] | Pytest test suite breakdown across all 7 test modules and execution standards. | `tests/*.py` |
| [[architecture_map]] | Complete consolidated code index with line-by-line function, class, and command pointers. | Full repository |

---

## ⚡ Operational Workflow Notes

| Note | Purpose & Flow |
| :--- | :--- |
| [[workflow_tournament_panel_sync]] | Explains how Staff Panel actions (e.g. `Toggle Subs`) dynamically edit live channel embeds in real time. |
| [[workflow_user_registration]] | Documents the single modal registration flow and active Region Tag mismatch validation. |
| [[workflow_clan_role_directory]] | Documents self-serve clan alignment, 25-option select chunking, search modal, automated role scanner, and `@Clanless` switching rules. |
