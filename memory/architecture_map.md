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

### `cogs/tournaments.py` (161 lines)
- **Class:** `TournamentCog(commands.Cog, TournamentHelpersMixin, TournamentPlayerMixin, TournamentConfigMixin, TournamentStaffMixin, TournamentStateMixin, TournamentEventMixin)` (`L76`)
- Main orchestrator cog composing all tournament modular mixins located in `cogs/tournament_ops/`.
- Re-exports persistent views, modals, and embeds for backwards compatibility with tests.

### `cogs/tournament_ops/` (Modular Mixins & Constants - 3,877 lines total)
- **`constants.py` (84 lines):**
  - Choice definitions for `TIMEZONE_CHOICES`, `WEAPON_CHOICES`, `REGION_CHOICES`, `REGION_FILTER_CHOICES`, `EXPORT_FORMAT_CHOICES`, `EXPORT_TARGET_CHOICES`, `ANNOUNCE_TARGET_CHOICES`, `HELP_SECTION_CHOICES`, `PANEL_CHOICES`.
- **`helpers.py` (804 lines) - `TournamentHelpersMixin`:**
  - `cog_load()` / `cog_unload()`: `L41` (View registration & loop management)
  - `tournament_reminder_task()`: `L86` (Background 1-minute reminder loop)
  - `_check_and_send_reminders()`: `L95` (Day-of and 30-minute reminder checks)
  - `_assign_participant_role()` / `_remove_participant_role()`: `L245`, `L269`
  - `_update_channel_permission()`: `L320` (Dynamically locks/unlocks channel send permissions)
  - `_sync_category_region_permissions()`: `L359` (Restricts category channels to allowed region roles)
  - `_post_or_update_registration_panel()`: `L488`
  - `_update_registration_panel()` / `_close_registration_panel()`: `L516`, `L538`
  - `_post_or_update_subs_panel()`: `L556`
  - `_update_subs_panel()` / `_close_subs_panel()`: `L584`, `L606`
  - `_post_or_update_checkin_panel()`: `L624`
  - `_update_checkin_panel()`: `L652`
  - `_update_all_live_panels()`: `L670` (Concurrent refresh via `asyncio.gather`)
  - `_dispatch_checkin_log()`: `L681` (Dispatches audit receipt embed to `#checkin-logs`)
  - Autocomplete resolvers (`_resolve_user_id`, `_kick_participants_autocomplete`, `_substitute_candidates_autocomplete`, `_replace_candidates_autocomplete`): `L719`-`L788`
- **`player_cmds.py` (365 lines) - `TournamentPlayerMixin`:**
  - `/help`: `L52` (Interactive guide & command manual with dropdown categories)
  - `/register`: `L74` (Main bracket registration modal or direct command)
  - `/unregister`: `L117` (Withdraw from main bracket and free slot)
  - `/sub`: `L149` (Join standby substitute FIFO queue)
  - `/sub-unregister`: `L207` (Withdraw from standby substitute queue)
  - `/edit-entry`: `L248` (Update registered IGN or region)
  - `/checkin`: `L296` (Confirm tournament match presence)
  - `/sub-checkin`: `L327` (Confirm standby sub readiness for call-ups)
  - `/status`: `L351` (Live slots, regions, weapon restrictions, and phase status)
  - `/roster`: `L361` (Paginated view of active bracket duelists and subs)
- **`config_cmds.py` (373 lines) - `TournamentConfigMixin`:**
  - `/config`: `L39` (Configuration dashboard showing server state, roles, channels, and limits)
  - `/set-channel` / `!set_channel`: `L66`, `L115` (Channel routing: registration, subs, checkin, checkin_logs, announcements)
  - `/post`: `L147` (Interactive panel poster: staff, guide, reg, subs, checkin, event_scheduler, clan_submit, clan_roles)
  - Prefix fallbacks: `!post_event_scheduler_panel` (`L257`), `!post_tournament_staff_panel` (`L296`), `!post_registration_panel` (`L320`), `!post_subs_panel` (`L340`), `!post_checkin_panel` (`L360`)
- **`staff_cmds.py` (1,415 lines) - `TournamentStaffMixin`:**
  - `t_group = app_commands.Group(name="t", description="Tournament staff and bracket management")`: `L47`
  - `/t open` / `!tournament_open`: `L58`
  - `/t close` / `!tournament_close`: `L231`
  - `/t open-subs` / `!tournament_open_subs`: `L259`
  - `/t close-subs` / `!tournament_close_subs`: `L308`
  - `/t checkin-open` / `!tournament_open_checkin`: `L343`
  - `/t checkin-close` / `!tournament_close_checkin`: `L397`
  - `/t kick` / `!tournament_kick`: `L425`
  - `/t force-reg` / `!tournament_force_register`: `L477`
  - `/t promote` / `!tournament_promote_sub`: `L525`
  - `/t set-limit` / `!tournament_set_limit`: `L601`
  - `/t set-regions` / `!tournament_set_regions`: `L622`
  - `/t set-weapons` / `!tournament_set_weapons`: `L688`
  - `/t set-admin-role` / `!tournament_set_admin_role`: `L709`
  - `/t set-event-role` / `!set_event_role`: `L732`, `L770`
  - `/t set-role` / `!tournament_set_role`: `L788`
  - `/t set-time` / `!tournament_set_time`: `L829`
  - `/t test-reminder` / `!tournament_test_reminder`: `L877`
  - `/t announce` / `!tournament_announce`: `L929`
  - `/t export` / `!tournament_export`: `L1017`
  - `/t bulk-reg` / `!tournament_bulk_register`: `L1064`, `L1125`
  - `/t clear` / `!tournament_clear`: `L1141`
  - `/t setup-section` / `!tournament_setup_section`: `L1191`
  - `/t remove-section` / `!tournament_remove_section`: `L1283`
  - `/t staff-checkin`: `L1345` (Manual staff check-in override)
  - `!post_staff_guide`: `L1392`
- **`state_cmds.py` (397 lines) - `TournamentStateMixin`:**
  - `state_group = app_commands.Group(name="state", description="Server state snapshot and disaster recovery")`: `L27`
  - `/state save-roster` / `!tournament_save_roster`: `L33`, `L54` (Preset snapshot to `saved_roster.json`)
  - `/state restore-roster` / `!tournament_restore_roster`: `L68`, `L134` (Manual preset restore)
  - `/state save` / `!state_save`: `L168`, `L227` (Channels, roles, panel links snapshot)
  - `/state restore` / `!state_restore`: `L247`, `L323` (Channel/role recovery with panel refresh)
  - `/state status`: `L352` (Diagnostic comparison of active channels vs saved snapshot)
- **`event_cmds.py` (399 lines) - `TournamentEventMixin`:**
  - `event_group = app_commands.Group(name="event", description="Discord event scheduling and calendar")`: `L30`
  - `/event create`: `L35` (Schedule Discord server event and sync to website)
  - `/event cancel`: `L232` (Cancel scheduled event and sync cancellation)
  - `/event complete`: `L291` (Conclude tournament, record champion, and publish to website)
  - `/event remove-past-result`: `L370` (Remove historical tournament result)

### `cogs/clan_showcase.py` (2,766 lines)
- **Class:** `ClanShowcaseCog(commands.Cog, name="ClanShowcase")` (`L1422`)
- **Command Group:**
  - `clan_group = app_commands.Group(name="clan", description="Clan management and showcase")`
- **Interactive UI Components:**
  - `ClanSubmissionModal`: `L126` (Clan profile submission form)
  - `ClanDraftPreviewView`: `L380` (Ephemeral 2-stage confirmation view with live color editor)
  - `ClanStaffReviewView`: `L749` (Staff approval/rejection panel view)
  - `ClanSubmissionPanelView`: `L1094` (Persistent submission button posted to public channel)
  - `ClanRoleSelect`: `L1167` (Self-serve clan role claim select menu with 25-option chunking)
  - `ClanRoleAssignmentPanelView`: `L1334` (Live self-serve role directory panel)
  - `ClanSearchModal`: `L1271` (Instant keyword popup search modal for clan claims)
- **Primary Slash & Prefix Commands (`/clan <subcommand>`):**
  - `/clan submit`: `L1657` (Submit clan profile with mobile photo picker or image URL)
  - `/clan channels`: `L1843` (Configure or inspect showcase and staff review channels)
  - `/clan edit`: `L1918` (Staff live profile editor modal with autocomplete)
  - `/clan preview`: `L1992` (Preview Sapphire-identical showcase embed live)
  - `/clan claim`: `L2107` (Claim or switch to official clan role with autocomplete)
  - `/clan leave`: `L2237` (Leave current clan and restore `@Clanless` status)
  - `/clan set-clanless-role`: `L2277` (Configure the default `@Clanless` role)
  - `/clan role-edit`: `L2321` (Edit, rename, or link a Discord role for an approved clan)
  - `/clan refresh-panel`: `L2409` (Manually re-sync and refresh Clan Role Assignment Panel)
  - `/clan delete`: `L2455` (Remove clan from database & Claim Role panel, optional role deletion)
  - `/clan sync-roles`: `L2573` (Scan server roles ending with `//` and auto-import clans)

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
