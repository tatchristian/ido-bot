# 🏆 Tournaments Cog Memory Node

**File Path:** `cogs/tournaments.py` (161 lines)
**Main Cog Class:** `TournamentCog`
**Architecture:** Composed via modular mixins under `cogs/tournament_ops/` (total 4,038 lines)
**Extracted Modules:**
- `cogs/tournament_ops/constants.py` (84 lines): Choice definitions for regions, weapons, timezones, formats, panels, and help sections.
- `cogs/tournament_ops/helpers.py` (804 lines): Lifecycle hooks (`cog_load`, `cog_unload`), background reminder loop (`tournament_reminder_task`), participant role management, channel permissions & region locking, live panel synchronization (`asyncio.gather`), autocomplete resolvers.
- `cogs/tournament_ops/player_cmds.py` (365 lines): 1-word player slash commands (`/help`, `/register`, `/unregister`, `/sub`, `/sub-unregister`, `/edit-entry`, `/checkin`, `/sub-checkin`, `/status`, `/roster`).
- `cogs/tournament_ops/config_cmds.py` (373 lines): Server configuration (`/config`, `/set-channel`, `/post` panels, prefix fallbacks).
- `cogs/tournament_ops/staff_cmds.py` (1,415 lines): Staff bracket management (`t_group = app_commands.Group(name="t", ...)` with 24 subcommands and prefix fallbacks).
- `cogs/tournament_ops/state_cmds.py` (397 lines): State snapshot and disaster recovery (`state_group = app_commands.Group(name="state", ...)` with 5 subcommands and prefix fallbacks).
- `cogs/tournament_ops/event_cmds.py` (399 lines): Discord event scheduling and website sync (`event_group = app_commands.Group(name="event", ...)` with 4 subcommands).
- `utils/tournament_views.py` (persistent views, selects, modals, admin checks).
- `utils/tournament_embeds.py` (embed builders, visual helpers, color palette).
**Backlink:** [[index]] | [[services_layer]] | [[ui_components]] | [[workflow_tournament_panel_sync]]

---

## 🎛️ Interactive Discord Views & Panels (`utils/tournament_views.py`)
- **Staff Operations Control Center:** `TournamentStaffPanelView`
  - `btn_staff_create_tournament` -> Opens `StaffCreateTournamentModal`
  - `btn_staff_open_bracket` -> Calls `open_tournament()` & auto-posts live hub
  - `btn_staff_close_bracket` -> Calls `close_tournament()` & edits hub to closed notice
  - `btn_staff_toggle_subs` -> Toggles sub bench and syncs registration hub live
  - `btn_staff_toggle_checkin` -> Toggles contestant check-in window
  - `btn_staff_promote_sub` -> Advances next substitute in FIFO order
  - `btn_staff_broadcast_announce` -> Opens `StaffAnnounceModal`
  - `btn_staff_set_time` -> Opens `StaffSetTimeModal`
  - `btn_staff_live_status` -> Displays live status embed

- **Player Registration Hub View:** `TournamentRegistrationPanelView`
  - `btn_user_reg_hub` -> Opens `UserRegistrationModal`
  - `btn_user_withdraw_hub` -> Releases player slot and updates counter
  - `btn_user_roster_hub` -> Renders active contestant roster
  - `btn_user_checkin_hub` -> Confirms match-day presence
  - `btn_user_help_hub` -> Renders rules & guide

- **Standby Substitute Hub View:** `TournamentSubsPanelView`
  - `btn_sub_join_hub` -> Opens `UserSubRegistrationModal`
  - `btn_sub_leave_hub` -> Withdraws from queue
  - `btn_sub_pos_hub` -> Shows FIFO queue position (e.g. #1 of 5)
  - `btn_sub_roster_hub` -> Renders active contestant roster
  - `btn_sub_help_hub` -> Renders rules & guide

- **Closed Notice Views:**
  - `TournamentClosedRegistrationView` -> Disabled indicator with optional link button jumping to subs bench
  - `TournamentClosedSubsView` -> Disabled indicator and roster inspection

- **Match-Day Check-In Hub View:** `TournamentCheckinPanelView` (persistent, timeout=None)
  - `btn_checkin_hub_action`: 1-click check-in for main duelists or standby subs. Updates panels and dispatches receipt to `#checkin-logs`.
  - `btn_checkin_hub_cancel`: Retracts an active check-in during the window, resetting status to unconfirmed.
  - `btn_checkin_hub_status`: Ephemeral check showing tier, verified IGN, weapon/region, and sub queue spot.
  - `btn_checkin_hub_list`: Renders formatted list of all checked-in contestants.

- **Staff Operations Guide View:** `TournamentStaffGuideView` & `TournamentStaffGuideSelect`
  - `select_staff_guide_page`: 9 operational sections (overview, panels, phase 1-4, checklist, persistence, roles).

- **Navigation Help View:** `HelpView`
  - Ephemeral view (`timeout=180.0`) for `/help` command navigation.

---

## 📋 Modal Popups (`utils/tournament_views.py`)
- `TournamentEventModal`: Discord scheduled event creator with website sync.
- `StaffCreateTournamentModal`: Configure title, slots, regions, registration channel.
- `StaffOpenTournamentModal`: Backwards-compatible alias for `StaffCreateTournamentModal`.
- `StaffAnnounceModal`: Broadcast announcement message to players.
- `StaffSetTimeModal`: Date, time, and timezone configuration.
- `UserRegistrationModal`: IGN and Region Tag only (weapon defaults to "Standard").
- `UserSubRegistrationModal`: Standby substitute registration form (weapon defaults to "Standard").

---

## 🛡️ Permission Predicates & Checks (`utils/tournament_views.py`)
- `check_is_tournament_admin`: Owner, admin perms, or tournament admin role check.
- `is_tournament_admin`: App commands check decorator.
- `is_tournament_admin_prefix`: Prefix command check decorator.
- `check_is_event_admin`: Owner, admin, manage events/guild, or event role check.
- `is_event_admin`: App commands check decorator for event scheduling.
- `is_server_admin`: Strict administrator permission or server ownership check.

---

## 🔗 Live Synchronization Hooks (`cogs/tournament_ops/helpers.py`)
- `_sync_category_region_permissions()`: Category permission sync restricting visibility exclusively to allowed region roles (`North America`, `Europe`, `Asia`, `South America`, `Oceania`, `Africa`) when a regional tournament is opened, or resetting to `@everyone` if `GLOBAL`.
- `_update_channel_permission()`: Locks/unlocks channel send perms.
- `_post_or_update_registration_panel()`
- `_update_registration_panel()`
- `_close_registration_panel()`
- `_post_or_update_subs_panel()`
- `_update_subs_panel()`
- `_close_subs_panel()`
- `_post_or_update_checkin_panel()`
- `_update_checkin_panel()`
- `_update_all_live_panels()`
- `_dispatch_checkin_log()`

---

## 💾 Roster & State Persistence Commands (`cogs/tournament_ops/state_cmds.py`)
- `/state save` / `!state_save`: Snapshots all set channels, roles, and panel links to `saved_state.json`.
- `/state restore` / `!state_restore`: Restores all channels and roles; optionally re-syncs panels.
- `/state status`: Compares active channels against saved snapshot with diagnostics.
- `/state save-roster` / `!tournament_save_roster`: Saves active roster to `saved_roster.json` preset.
- `/state restore-roster` / `!tournament_restore_roster`: Loads preset file and restores roster into active tournament.
- `/t bulk-reg` / `!tournament_bulk_register`: Enrolls batch list of contestants with auto delimiter parsing.
- `bot.py` `on_ready`: Auto-restores `saved_state.json` (or regex auto-discovers channels) on startup. Roster restoration from `saved_roster.json` is strictly manual via `/state restore-roster` to prevent overwriting new tournaments.
