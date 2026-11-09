# 🧠 EVEROS Architecture & Procedural Memory Map

> Complete, comprehensive architectural index of the entire `ido-bot` codebase.
> Updated continuously to eliminate full-file scans and minimize token usage.

---

## 1. System Entrypoint & Configuration

### `bot.py`
- `class UDATournamentBot(commands.Bot)`: Main bot client subclass initializing logging, cogs, services, and tasks.
- `setup_hook()`: Loads cogs (`TournamentCog`, `ClanShowcase`), starts `api_server`, syncs application slash commands.
- `on_ready()`: Bot startup notice, guild cache check, presence initialization.

### `config.py`
- `class BotConfig`: Environment settings, token, guild ID, channel IDs, organization name (`DUKE` / `UDA`), colors, timeouts.

---

## 2. Core Discord Cogs (`cogs/`)

### `cogs/tournaments.py` (~4,914 lines)
- **Class:** `TournamentCog(commands.Cog)` (`L304`)
- **Interactive Help:**
  - `HelpView`: `L236` (Category buttons: Participant, Admin, Weapons, Scheduling, Clan, Setup)
- **Panel Synchronization & Lifecycle Hooks:**
  - `_update_channel_permission()`: `L582` (Dynamically locks/unlocks text channel send permissions)
  - `_post_or_update_registration_panel()`: `L612` (Posts or edits live registration hub in `#tournament-registration`)
  - `_update_registration_panel()`: `L640` (Edits live hub: updates progress bar, slot counter, sub status)
  - `_close_registration_panel()`: `L662` (Edits live hub into the closed notice with links to subs)
  - `_post_or_update_subs_panel()`: `L680` (Posts or edits standby subs hub in `#substitutes-bench`)
  - `_update_subs_panel()`: `L708` (Edits live subs hub: updates queue size count)
  - `_close_subs_panel()`: `L730` (Edits live subs hub into closed notice)
- **Modals (Forms):**
  - `TournamentEventModal`: `L3393` (Schedule server event: title, date, time, timezone, description)
  - `StaffCreateTournamentModal`: `L3646` (Title, slots, regions, registration channel)
  - `StaffAnnounceModal`: `L3770` (Broadcast announcement message to contestants)
  - `StaffSetTimeModal`: `L3836` (Match day date, time, timezone configuration)
  - `UserRegistrationModal`: `L4340` (IGN, weapon sample placeholder, Region Tag placeholder with validation)
  - `UserSubRegistrationModal`: `L4636` (Standby substitute queue registration modal)
- **Persistent Panels & Views:**
  - `TournamentStaffPanelView`: `L3896` (The 1-click Control Center)
    - `btn_staff_create_tournament`: `L3908` (Opens `StaffCreateTournamentModal`)
    - `btn_staff_open_bracket`: `L3939` (Opens bracket, posts live hub)
    - `btn_staff_close_bracket`: `L4019` (Closes bracket, edits hub to closed notice)
    - `btn_staff_toggle_subs`: `L4071` (Toggles sub bench & syncs registration hub live!)
    - `btn_staff_toggle_checkin`: `L4164` (Opens/closes match day check-in window)
    - `btn_staff_promote_sub`: `L4208` (Advances next sub into bracket)
    - `btn_staff_broadcast_announce`: `L4257` (Opens `StaffAnnounceModal`)
    - `btn_staff_set_time`: `L4280` (Opens `StaffSetTimeModal`)
    - `btn_staff_live_status`: `L4303` (Ephemeral live roster & status embed)
  - `TournamentRegistrationPanelView`: `L4415` (Player Registration Hub View)
    - `btn_user_reg_hub`: `L4423` (Opens `UserRegistrationModal`)
    - `btn_user_withdraw_hub`: `L4466` (Withdraws & releases slot)
    - `btn_user_roster_hub`: `L4505` (Displays live roster embed)
    - `btn_user_checkin_hub`: `L4522` (Confirms match day check-in)
    - `btn_user_help_hub`: `L4561` (Opens rules embed)
  - `TournamentClosedRegistrationView`: `L4583` (Closed registration placeholder view)
  - `TournamentSubsPanelView`: `L4709` (Standby Substitute Queue Hub View)
    - `btn_sub_join_hub`: `L4718` (Opens `UserSubRegistrationModal`)
    - `btn_sub_leave_hub`: `L4757` (Leaves standby queue)
    - `btn_sub_pos_hub`: `L4789` (Checks FIFO queue position)
  - `TournamentClosedSubsView`: `L4865` (Closed substitute queue placeholder view)
  - `TournamentEventPanelView`: `L3515` (Event Scheduler 1-click button)
  - `TournamentStaffGuideView`: `L3637` (Operational cheat-sheet dropdown)
- **Primary Slash & Prefix Commands:**
  - `/tournament-open`: `L1172` (Opens bracket, creates participant role, sets channels)
  - `/tournament-close`: `L1311` (Locks bracket, edits panel to closed)
  - `/tournament-open-subs`: `L1340` (Opens substitute queue, syncs reg panel)
  - `/tournament-close-subs`: `L1381` (Closes substitute queue, syncs reg panel)
  - `/tournament-open-checkin`: `L1417`
  - `/tournament-close-checkin`: `L1470`
  - `/tournament-kick`: `L1585`
  - `/tournament-force-register`: `L1637`
  - `/tournament-promote-sub`: `L1685`
  - `/tournament-set-channels`: `L2081` (Configure all 4 channels at once)
  - `/tournament-set-channel`: `L2153` (Configure single dedicated channel)
  - `/tournament-set-time`: `L2231`
  - `/tournament-announce`: `L2368`
  - `/tournament-export`: `L2456`
  - `/tournament-clear`: `L2503` (Wipes roster & sub queues for a fresh event)
  - `/tournament-setup-section`: `L2553` (Constructs official server categories & arenas)
  - `/tournament-remove-section`: `L2645` (Safely deletes server categories & match channels)
  - `/tournament-schedule-event`: `L2711` (Discord event + web sync)
  - `/tournament-cancel-event`: `L2904`
  - `/tournament-complete-event`: `L2959`
  - `/post-tournament-staff-panel`: `L3170`
  - `/post-registration-panel`: `L3223`
  - `/post-subs-panel`: `L3278`
  - `/post-staff-guide`: `L3333`

---

### `cogs/clan_showcase.py` (~2,490 lines)
- **Class:** `ClanShowcaseCog(commands.Cog)` (`L1450`)
- **Modals:**
  - `ClanCustomHexModal`: `L84`
  - `ClanSubmissionModal`: `L126` (Clan profile submission form)
  - `ClanRejectionModal`: `L511` (Staff rejection feedback)
  - `ClanEditModal`: `L591` (Live edit form for clan profiles & role names)
  - `ClanSearchModal`: `L1271` (Search & Claim clan role text popup)
- **Views:**
  - `ClanDraftConfirmationView`: `L270`
  - `ClanReviewButtonsView`: `L749` (Staff Approve & Publish, Reject buttons)
  - `ClanSubmissionPanelView`: `L1094` (Public submit button panel)
  - `ClanRoleSelect`: `L1167` (Dynamic approved clan dropdown with 25-option chunking)
  - `ClanSearchResultView`: `L1347` (Search result select menu)
  - `ClanRoleAssignmentPanelView`: `L1362` (Self-serve clan role directory panel)
- **Internal Role Logic & Auto-Updates:**
  - `on_guild_role_update`: `L1479` (Live listener syncing Discord role renames/colors to database & refreshing panel)
  - `_get_clanless_role()`: `L1507` (Finds configured @Clanless role or falls back to name)
  - `_execute_clan_role_assignment()`: `L1519` (Strips @Clanless and old clan roles, adds new)
  - `_execute_clan_leave()`: `L1598` (Strips all clan roles, restores @Clanless)
  - `_refresh_clan_role_panel()`: `L1653` (Live message editor for Discord directory panel)
- **Commands:**
  - `/clan-submit`: `L1468`
  - `/clan-showcase-channels`: `L1696`
  - `/clan-showcase-edit`: `L1784`
  - `/post-clan-role-panel`: `L2068`
  - `/clan-claim`: `L2140`
  - `/clan-leave`: `L2242`
  - `/clan-set-clanless-role`: `L2280`
  - `/clan-role-edit`: `L2354`
  - `/clan-role-panel-refresh`: `L2476`
  - `/clan-delete` (`!clan_delete`): `L2504` (Admin: Remove clan from registry & panel, optional role deletion)
  - `/clan-sync-roles` (`!clan_sync_roles`): `L2623` (Automated scan & import of server roles ending with `//`)

---

## 3. Services Layer (`services/`)

### `services/tournament_service.py` (~540 lines)
- `class Participant`: `L37` (`user_id`, `ign`, `weapon`, `region`, `checked_in`, `timestamp`)
- `class TournamentState`: `L67` (Tracks slots, channels, message IDs, rosters, weapons, schedule)
- `class TournamentService`: `L175`
  - `configure_tournament()`: Sets slots, title, regions, participant role, reg channel.
  - `open_tournament()` / `close_tournament()`
  - `open_subs()` / `close_subs()`
  - `open_checkin()` / `close_checkin()`
  - `register_participant()` / `unregister_participant()`
  - `register_substitute()` / `unregister_substitute()`
  - `promote_substitute()`: FIFO advance from sub queue into main bracket.
  - `set_channels()`: Sets persistent channel IDs per guild.
  - `clear_tournament()`: Wipes state.
  - `_persist(guild_id)`: Saves to `storage/tournaments_{guild_id}.json`.

### `services/clan_showcase_service.py` (~500 lines)
- `class ClanSubmission`: `L339` (Includes `role_id`, `role_name`, `logo_url`, `status`)
- `class ClanShowcaseService`: `L406`
  - `get_approved_clans(guild_id)`: Returns approved clans sorted alphabetically.
  - `set_clan_role(sub_id, role_id, role_name)`: Links Discord role to submission.
  - `set_clan_role_panel_info()` / `get_clan_role_panel_info()`
  - `set_clanless_role_id()` / `get_clanless_role_id()`
  - `delete_submission(sub_id)`: Removes clan from database and persists.
  - `_persist()`: Saves to `storage/clan_showcases.json`.

### `services/past_results_service.py`
- `class PastResult`: `L23` (Concluded event details, champions, runner-ups, scores)
- `class PastResultsService`: `L54` (CRUD operations and local storage)

### `services/server_builder.py`
- Automatic generation of category channels, spectator lounges, and private dueling arenas.
- `UndoTournamentSectionView`: `L344` (Rollback view for created categories)

### `services/website_sync_service.py`
- `class WebsiteSyncService`: `L341` (REST API synchronization to `unitedduelingamity.org` for events and leaderboard clans)

### `services/api_server.py`
- Lightweight local aiohttp server for internal status and metrics.

---

## 4. Utilities Layer (`utils/`)

### `utils/ui.py` (~860 lines)
- `generate_progress_bar()`: `L13` (Renders visual filled/empty bar, e.g. `[████░░░░] 6/16`)
- `format_participant_line()`: `L38` (Renders numbered contestant list with weapon & check-in badges)
- `build_status_embed()`: `L48` (Live tournament progress & status embed)
- `build_roster_embed()`: `L134` (Full registered contestant and substitute roster)
- `build_tournament_reminder_embed()`: `L217` (Automated player DM notification)
- `build_help_embed()`: `L287` (Interactive guide pages)
- `build_staff_panel_embed()`: `L472` (Official DUKE Tournament Staff Operations Panel)
- `build_staff_guide_embed()`: `L499` (Tournament Staff Phase-by-Phase manual)
- `build_registration_panel_embed()`: `L659` (Player Registration Hub embed)
- `build_registration_closed_embed()`: `L722` (Registration closed notice)
- `build_subs_panel_embed()`: `L764` (Standby Substitute Queue Hub embed)
- `build_subs_closed_embed()`: `L802` (Substitutes closed notice)
- `build_clan_role_panel_embed()`: `L828` (Official Clan Alignment Directory embed)

### `utils/storage.py`
- `class StorageManager`: `L20` (Atomic JSON persistence with backup safeguards)

---

## 5. Test Suite Registry (`tests/`)

- `test_ui.py`: Embed builders, progress bars, participant formatting.
- `test_tournament_service.py`: Tournament lifecycle, slot caps, substitutions, check-in.
- `test_clan_showcase.py`: Clan submissions, reviews, auto-chunked dropdowns, role assignment, `@Clanless` rules.
- `test_storage.py`: Atomic storage read/writes, backup recovery.
- `test_website_sync.py`: API payload formatting and sync endpoints.
- `test_server_builder.py`: Category creation and arena setup.
- `test_api_server.py`: API endpoint routing.
