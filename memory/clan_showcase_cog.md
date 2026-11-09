# 🛡️ Clan Showcase Cog Memory Node

**File Path:** `cogs/clan_showcase.py` (~2,490 lines)
**Main Cog Class:** `ClanShowcaseCog` (`L1450`)
**Backlink:** [[index]] | [[services_layer]] | [[workflow_clan_role_directory]]

---

## 🎛️ Interactive Views & Select Menus
- `ClanSubmissionPanelView`: `L1094` (Public "Submit Clan Profile" button)
- `ClanReviewButtonsView`: `L749` (Staff "Approve & Publish", "Reject" buttons)
- `ClanRoleSelect`: `L1167` (Dynamic approved clan dropdown with 25-option alphabetical chunking)
- `ClanSearchResultView`: `L1347` (Select menu for multiple search matches)
- `ClanRoleAssignmentPanelView`: `L1362` (Live self-serve role directory panel)
  - `btn_clan_role_search`: Opens [[clan_showcase_cog#ClanSearchModal]]
  - `btn_clan_role_leave`: Calls `_execute_clan_leave()`
  - `btn_clan_role_help`: Displays system guide

---

## 📋 Modal Popups
- `ClanSubmissionModal`: `L126` (Clan profile submission form)
- `ClanEditModal`: `L591` (Profile and role name editor)
- `ClanSearchModal`: `L1271` (Keyword search modal for clan names/tags)
- `ClanRejectionModal`: `L511` (Staff rejection feedback)

---

## 🔄 Clean Role Management & Panel Auto-Updates
- `_get_clanless_role()`: `L1508` (Finds configured @Clanless role or falls back to name)
- `_execute_clan_role_assignment()`: `L1524` (Strips @Clanless and old clan roles, adds new)
- `_execute_clan_leave()`: `L1603` (Strips all clan roles, restores @Clanless)
- `_refresh_clan_role_panel()`: `L1653` (Live message editor for Discord directory panel)
- `on_guild_role_update`: `L1479` (Live event listener detecting server role renames/colors & editing panel)
- `/clan-sync-roles` (`!clan_sync_roles`): `L2522` (Automated scan & import of server roles with `//`)
