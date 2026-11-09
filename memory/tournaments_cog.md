# 🏆 Tournaments Cog Memory Node

**File Path:** `cogs/tournaments.py` (~4,914 lines)
**Main Cog Class:** `TournamentCog` (`L304`)
**Backlink:** [[index]] | [[services_layer]] | [[workflow_tournament_panel_sync]]

---

## 🎛️ Interactive Discord Views & Panels
- **Staff Operations Control Center:** `TournamentStaffPanelView` (`L3896`)
  - `btn_staff_create_tournament`: `L3908` -> Opens [[tournaments_cog#StaffCreateTournamentModal]]
  - `btn_staff_open_bracket`: `L3939` -> Calls `open_tournament()` & auto-posts live hub
  - `btn_staff_close_bracket`: `L4019` -> Calls `close_tournament()` & edits hub to closed notice
  - `btn_staff_toggle_subs`: `L4071` -> Toggles sub bench and syncs registration hub live
  - `btn_staff_toggle_checkin`: `L4164` -> Toggles contestant check-in window
  - `btn_staff_promote_sub`: `L4208` -> Advances next substitute in FIFO order
  - `btn_staff_broadcast_announce`: `L4257` -> Opens [[tournaments_cog#StaffAnnounceModal]]
  - `btn_staff_set_time`: `L4280` -> Opens [[tournaments_cog#StaffSetTimeModal]]
  - `btn_staff_live_status`: `L4303` -> Displays live status embed

- **Player Registration Hub View:** `TournamentRegistrationPanelView` (`L4415`)
  - `btn_user_reg_hub`: `L4423` -> Opens [[tournaments_cog#UserRegistrationModal]]
  - `btn_user_withdraw_hub`: `L4466` -> Releases player slot and updates counter
  - `btn_user_roster_hub`: `L4505` -> Renders active contestant roster
  - `btn_user_checkin_hub`: `L4522` -> Confirms match-day presence
  - `btn_user_help_hub`: `L4561` -> Renders rules & guide

- **Standby Substitute Hub View:** `TournamentSubsPanelView` (`L4709`)
  - `btn_sub_join_hub`: `L4718` -> Opens [[tournaments_cog#UserSubRegistrationModal]]
  - `btn_sub_leave_hub`: `L4757` -> Withdraws from queue
  - `btn_sub_pos_hub`: `L4789` -> Shows FIFO queue position (e.g. #1 of 5)

---

## 📋 Modal Popups
- `StaffCreateTournamentModal`: `L3646` (Title, slots, regions, registration channel)
- `StaffAnnounceModal`: `L3770` (Broadcast announcement message to players)
- `StaffSetTimeModal`: `L3836` (Date, time, and timezone configuration)
- `UserRegistrationModal`: `L4340` (IGN, weapon placeholder, Region Tag placeholder with mismatch validation)
- `UserSubRegistrationModal`: `L4636` (Standby substitute registration form)

---

## 🔗 Live Synchronization Hooks
- `_update_channel_permission()`: `L582`
- `_post_or_update_registration_panel()`: `L612`
- `_update_registration_panel()`: `L640`
- `_close_registration_panel()`: `L662`
- `_post_or_update_subs_panel()`: `L680`
- `_update_subs_panel()`: `L708`
- `_close_subs_panel()`: `L730`
