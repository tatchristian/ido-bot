# 🧠 EVEROS Architecture & Procedural Memory Map

> Complete, comprehensive architectural index of the entire `ido-bot` codebase.
> Updated continuously to eliminate full-file scans and minimize token usage.

---

## 1. System Entrypoint & Configuration

### `bot.py` (161 lines)
- `class UDATournamentBot(commands.Bot)`: `L53` (Main bot client subclass initializing logging, cogs, services, and tasks)
- `setup_hook()`: `L74` (Loads cogs, starts `api_server`, syncs application slash commands)
- `on_ready()`: `L91` (Bot startup notice, guild cache check, snapshot auto-discovery, presence initialization)

### `config.py` (75 lines)
- `class Config`: `L17` (Environment settings, token, guild ID, channel IDs, organization name `UDA`, colors, timeouts)

---

## 2. Core Discord Cogs (`cogs/`)

### `cogs/tournaments.py` (3,709 lines)
- **Class:** `TournamentCog(commands.Cog)` (`L149`)
- **Panel Synchronization & Lifecycle Hooks:**
  - `_update_channel_permission()`: `L430` (Dynamically locks/unlocks text channel send permissions)
  - `_sync_category_region_permissions()`: `L469` (Restricts category channel visibility to matching region roles)
  - `_post_or_update_registration_panel()`: `L598` (Posts or edits live registration hub in `#tournament-registration`)
  - `_update_registration_panel()`: `L626` (Edits live hub: updates progress bar, slot counter, sub status)
  - `_close_registration_panel()`: `L648` (Edits live hub into the closed notice with links to subs)
  - `_post_or_update_subs_panel()`: `L666` (Posts or edits standby subs hub in `#substitutes-bench`)
  - `_update_subs_panel()`: `L694` (Edits live subs hub: updates queue size count)
  - `_close_subs_panel()`: `L716` (Edits live subs hub into closed notice)
  - `_post_or_update_checkin_panel()`: `L734` (Posts or edits live check-in hub in `#tournament-checkin`)
  - `_update_checkin_panel()`: `L762` (Edits live check-in hub: progress and sub readiness counters)
  - `_update_all_live_panels()`: `L780` (Concurrent refresh of Reg, Subs, and Check-In panels via `asyncio.gather`)
  - `_dispatch_checkin_log()`: `L791` (Dispatches audit receipt embed to `#checkin-logs`)
- **Primary Slash & Prefix Commands:**
  - `/tournament-help` (`L840`) / `/help` (`L874`)
  - `/tournament-register`: `L895`
  - `/tournament-unregister`: `L944`
  - `/tournament-sub-register`: `L970`
  - `/tournament-sub-unregister`: `L1034`
  - `/tournament-edit-entry`: `L1075`
  - `/tournament-checkin`: `L1123`
  - `/tournament-sub-checkin`: `L1154`
  - `/tournament-status`: `L1178`
  - `/tournament-roster`: `L1188`
  - `/tournament-open`: `L1202` (Opens bracket, creates participant role, sets channels, syncs category perms)
  - `/tournament-close`: `L1375` (Locks bracket, edits panel to closed)
  - `/tournament-open-subs`: `L1403` (Opens substitute queue, syncs reg panel)
  - `/tournament-close-subs`: `L1452` (Closes substitute queue, syncs reg panel)
  - `/tournament-open-checkin`: `L1487`
  - `/tournament-close-checkin`: `L1541`
  - `/tournament-kick`: `L1657`
  - `/tournament-force-register`: `L1709`
  - `/tournament-promote-sub`: `L1757`
  - `/tournament-set-limit`: `L1833`
  - `/tournament-set-regions`: `L1854` (Updates regions and updates category permissions)
  - `/tournament-set-weapons`: `L1920`
  - `/tournament-set-admin-role`: `L1941`
  - `/tournament-set-event-role`: `L1995`
  - `/tournament-set-channels`: `L2161` (Configure all channels at once)
  - `/tournament-set-channel`: `L2233` (Configure single dedicated channel)
  - `/tournament-set-time`: `L2322`
  - `/tournament-announce`: `L2459`
  - `/tournament-export`: `L2547` (Export to Challonge, Start.gg, Battlefy CSV, Text)
  - `/tournament-save-roster` (`!tournament_save_roster`): `L2594`
  - `/tournament-restore-roster` (`!tournament_restore_roster`): `L2629`
  - `/tournament-bulk-register` (`!tournament_bulk_register`): `L2729`
  - `/state-save` (`!state_save`): `L2810`
  - `/state-restore` (`!state_restore`): `L2888`
  - `/state-status`: `L2995`
  - `/tournament-clear`: `L3047`
  - `/tournament-setup-section`: `L3097` (Constructs official server categories & arenas)
  - `/tournament-remove-section`: `L3189` (Safely deletes server categories & match channels)
  - `/tournament-schedule-event`: `L3255` (Discord event + web sync)
  - `/tournament-cancel-event`: `L3448`
  - `/tournament-complete-event`: `L3503`
  - `/post-event-scheduler-panel`: `L3637`
  - `/post-tournament-staff-panel`: `L3714` (The 1-click Control Center)
  - `/post-registration-panel`: `L3767`
  - `/post-subs-panel`: `L3822`
  - `/post-checkin-panel`: `L3877`
  - `/tournament-staff-checkin`: `L3932` (Staff check-in override)
  - `/post-staff-guide`: `L3979`

### `cogs/clan_showcase.py` (2,499 lines)
- **Class:** `ClanShowcaseCog(commands.Cog)` (`L670`)
- **Interactive UI Components:**
  - `ClanSubmissionModal`: `L144` (5-field clan profile submission modal)
  - `ClanDraftPreviewView`: `L361` (Ephemeral 2-stage confirmation view with edit & discard)
  - `ClanStaffReviewView`: `L749` (Staff approval/rejection panel view)
  - `ClanRejectReasonModal`: `L982` (Interactive staff rejection reason input)
  - `ClanSubmissionPanelView`: `L1054` (Persistent submission button posted to public channel)
  - `ClanRoleSelect`: `L1152` (Self-serve clan role claim select menu with 25-option chunking)
  - `ClanRoleDirectoryView`: `L1362` (Multi-dropdown clan directory panel with search modal)
  - `ClanSearchModal`: `L1294` (Instant keyword popup search modal for clan claims)
- **Primary Slash & Prefix Commands:**
  - `/clan-submit`: `L1655`
  - `/clan-showcase-channels`: `L1737`
  - `/clan-showcase-edit`: `L1849`
  - `/post-clan-submission-panel`: `L1909`
  - `/post-clan-role-panel`: `L1949`
  - `/clan-claim`: `L2023`
  - `/clan-leave`: `L2074`
  - `/clan-set-clanless-role`: `L2144`
  - `/clan-role-edit`: `L2274`
  - `/clan-role-panel-refresh`: `L2314`
  - `/clan-delete` (`!clan_delete`): `L2358`
  - `/clan-sync-roles` (`!clan_sync_roles`): `L2492`

---

## 3. Dedicated Tournament UI Modules (`utils/`)

### `utils/tournament_views.py` (1,752 lines)
- **Role & Permission Checks:**
  - `check_is_tournament_admin()`: `L39`
  - `is_tournament_admin()`: `L87`
  - `is_tournament_admin_prefix()`: `L95`
  - `check_is_event_admin()`: `L103`
  - `is_event_admin()`: `L145`
  - `is_server_admin()`: `L157`
- **Modals (Form Popups):**
  - `TournamentEventModal`: `L237` (Schedule server event: title, date, time, timezone, description)
  - `StaffCreateTournamentModal`: `L507` (Title, slots, regions, registration channel)
  - `StaffAnnounceModal`: `L642` (Broadcast announcement message to contestants)
  - `StaffSetTimeModal`: `L708` (Match day date, time, timezone configuration)
  - `UserRegistrationModal`: `L1221` (IGN, Region Tag with validation; defaults weapon to Standard)
  - `UserSubRegistrationModal`: `L1508` (Standby substitute queue registration modal)
- **Persistent Panels & Views:**
  - `HelpView`: `L169` (Category buttons: Participant, Admin, Weapons, Scheduling, Clan, Setup)
  - `TournamentEventPanelView`: `L359` (Event Scheduler 1-click button)
  - `TournamentStaffGuideSelect`: `L416` (Operational cheat-sheet dropdown)
  - `TournamentStaffGuideView`: `L498`
  - `TournamentStaffPanelView`: `L768` (The 1-Click Staff Control Center)
    - `btn_staff_create_tournament`: `L780`
    - `btn_staff_open_bracket`: `L809`
    - `btn_staff_close_bracket`: `L941`
    - `btn_staff_toggle_subs`: `L1000`
    - `btn_staff_toggle_checkin`: `L1060`
    - `btn_staff_promote_sub`: `L1104`
    - `btn_staff_broadcast_announce`: `L1153`
    - `btn_staff_set_time`: `L1176`
    - `btn_staff_live_status`: `L1199`
  - `TournamentRegistrationPanelView`: `L1287` (Player Registration Hub View)
    - `btn_user_reg_hub`: `L1299`
    - `btn_user_withdraw_hub`: `L1342`
    - `btn_user_roster_hub`: `L1377`
    - `btn_user_checkin_hub`: `L1394`
    - `btn_user_help_hub`: `L1433`
  - `TournamentClosedRegistrationView`: `L1455` (Closed registration indicator)
  - `TournamentSubsPanelView`: `L1572` (Standby Substitute Queue Hub View)
    - `btn_sub_join_hub`: `L1584`
    - `btn_sub_leave_hub`: `L1623`
    - `btn_sub_pos_hub`: `L1655`
    - `btn_sub_roster_hub`: `L1688`
    - `btn_sub_help_hub`: `L1705`
  - `TournamentClosedSubsView`: `L1728` (Closed substitute queue indicator)
  - `TournamentCheckinPanelView`: `L1769` (Match-Day Check-In Hub View)
    - `btn_checkin_hub_action`: `L1789` (1-click smart check-in)
    - `btn_checkin_hub_cancel`: `L1833` (Cancel active check-in)
    - `btn_checkin_hub_status`: `L1869` (My status check)
    - `btn_checkin_hub_list`: `L1903` (Active checked-in list)

### `utils/tournament_embeds.py` (1,045 lines)
- `generate_progress_bar()`: `L32` (Renders ASCII visual bar, e.g. `[████░░░░] 50%`)
- `format_participant_line()`: `L57` (Renders numbered contestant line with check-in badges)
- `_chunk_lines()`: `L67` (Splits long rosters across Discord 1024-character embed limits)
- `build_status_embed()`: `L86` (Live tournament progress & status embed)
- `build_roster_embed()`: `L172` (Full registered contestant and substitute roster)
- `build_tournament_reminder_embed()`: `L263` (Automated player DM notification)
- `build_help_embed()`: `L333` (Interactive guide pages)
- `build_staff_panel_embed()`: `L518` (Official DUKE Tournament Staff Operations Panel)
- `build_staff_guide_embed()`: `L545` (Tournament Staff Phase-by-Phase manual)
- `build_registration_panel_embed()`: `L846` (Player Registration Hub embed)
- `build_registration_closed_embed()`: `L909` (Registration closed notice)
- `build_subs_panel_embed()`: `L951` (Standby Substitute Queue Hub embed)
- `build_subs_closed_embed()`: `L989` (Substitutes closed notice)
- `build_checkin_panel_embed()`: `L1015` (Check-In Hub embed with live countdown & readiness)
- `build_checkin_receipt_embed()`: `L1065` (Receipt embed posted to `#checkin-logs`)

### `utils/ui.py` (89 lines)
- Clean re-export facade connecting `utils/tournament_embeds.py` for full backward compatibility.
- `build_clan_role_panel_embed()`: `L72` (Official Clan Alignment Directory embed)

### `utils/storage.py` (164 lines)
- `class StorageManager`: `L20` (Atomic JSON persistence with rotating backups and recovery)

---

## 4. Services Layer (`services/`)

### `services/tournament_service.py` (1,274 lines)
- `class Participant`: `L53` (`user_id`, `ign`, `weapon`, `region`, `checked_in`, `registered_at`)
- `class TournamentState`: `L83` (Slots, channels, message IDs, rosters, weapons, schedule)
- `class TournamentService`: `L197`
  - `open_tournament()` / `close_tournament()`: `L387` / `L415`
  - `open_subs()` / `close_subs()`: `L422` / `L431`
  - `open_checkin()` / `close_checkin()`: `L919` / `L931`
  - `checkin_user()` / `cancel_checkin()`: `L946` / `L985`
  - `staff_set_checkin()`: `L1022`
  - `register_participant()` / `unregister_participant()`: `L673` / `L725`
  - `register_substitute()` / `unregister_substitute()`: `L740` / `L784`
  - `promote_substitute()`: `L848` (FIFO advance from sub queue into main bracket)
  - `kick_user()` / `force_register()`: `L594` / `L625`
  - `set_channels()` / `clear_channels()`: `L504` / `L528`
  - `save_roster_preset()` / `import_roster_preset()`: `L1074` / `L1100`
  - `bulk_register()`: `L1155`
  - `clear_tournament()`: `L571`
  - `_persist(guild_id)`: Saves to `data/tournament_{guild_id}.json`

### `services/clan_showcase_service.py` (686 lines)
- `class ClanSubmission`: `L339` (Includes `role_id`, `role_name`, `logo_url`, `status`)
- `class ClanShowcaseService`: `L406`
  - `get_approved_clans(guild_id)`: `L468` (Alphabetical list of verified clans)
  - `set_clan_role(sub_id, role_id, role_name)`: `L474`
  - `set_clan_role_panel_info()` / `get_clan_role_panel_info()`: `L483` / `L490`
  - `set_clanless_role_id()` / `get_clanless_role_id()`: `L495` / `L501`
  - `delete_submission(sub_id)`: `L647`
  - `_persist()`: Saves to `data/clan_submissions.json`

### `services/api_server.py` (217 lines)
- Public REST API for `unitedduelingamity.org` with CORS (`/tournaments`, `/past-results`, `/leaderboard`, `/players`, `/health`) reading directly from `TournamentService._states`.

### `services/state_snapshot_service.py` (339 lines)
- Saves, restores, and regex auto-discovers server channels, roles, and panels across deployments (`saved_state.json`), integrating directly with `bot.py` using `guild=guild` context.

### `services/past_results_service.py` (139 lines)
- Manages tournament archives, champions, runner-ups, and final scores for website rendering.

### `services/server_builder.py` (402 lines)
- Automatic generation of category channels, spectator lounges, and private dueling arenas.
- `UndoTournamentSectionView`: `L344` (Rollback view for created categories)

### `services/website_sync_service.py` (461 lines)
- REST API synchronization to `unitedduelingamity.org` for events and leaderboard clans.

---

## 5. Test Suite Registry (`tests/`)

- `test_api_server.py` (226 lines): API endpoint routing and CORS headers.
- `test_category_permissions.py` (159 lines): Category region-locking and modal input checks.
- `test_checkin_panel.py` (256 lines): Check-in hub buttons, logs, receipts, cancel actions.
- `test_clan_showcase.py` (649 lines): Clan submissions, reviews, auto-chunked dropdowns, role assignment, `@Clanless` rules.
- `test_server_builder.py` (190 lines): Category creation and arena setup.
- `test_state_snapshot.py` (105 lines): State snapshots and auto-discovery.
- `test_storage.py` (180 lines): Atomic storage read/writes, backup recovery.
- `test_tournament_service.py` (936 lines): Tournament lifecycle, slot caps, substitutions, check-in.
- `test_ui.py` (220 lines): Embed builders, progress bars, participant formatting.
- `test_website_sync.py` (230 lines): API payload formatting and sync endpoints.
