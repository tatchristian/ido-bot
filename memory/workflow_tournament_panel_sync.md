# 🔄 Workflow: Tournament Panel Live Synchronization

**Backlink:** [[index]] | [[tournaments_cog]] | [[ui_components]]

---

## 🔁 Real-Time Synchronization Lifecycle

```
[ Staff Clicks Button on Staff Operations Panel ]
                      │
                      ├── "Open Registrations" ──► Locks/Unlocks Channel & Drops Live Registration Hub
                      │
                      ├── "Close Registrations" ─► Locks Channel & Edits Hub to Closed Notice
                      │
                      ├── "Toggle Subs" ────────► Unlocks Subs Channel, Drops Subs Hub,
                      │                           AND updates Registration Hub live (Disabled ➔ Active)
                      │
                      └── "Promote Sub" ────────► Advances next sub into bracket,
                                                  updates both Registration Hub & Subs Hub counters
```

---

## 📌 Direct Code Pointers
1. **Sub Toggle Sync:**
   - In `TournamentStaffPanelView.toggle_subs_button` (`cogs/tournaments.py` `L4071`):
     Calls `_update_registration_panel(interaction.guild)` so `#tournament-registration` immediately flips status.
2. **Channel Resolution:**
   - In `find_target_channel` (`cogs/tournaments.py` `L3977` & `L4099`):
     Uses regex stripping non-alphanumerics so channels with prefix emojis (e.g. `📝・tournament-registration`) are automatically detected.
3. **Dedicated Channel Override:**
   - `/tournament-set-channel target:Registration channel:#custom-reg` (`L2153`).
