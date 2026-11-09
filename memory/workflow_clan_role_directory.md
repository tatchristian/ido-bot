# 🏛️ Workflow: Self-Serve Clan Alignment Directory

**Backlink:** [[index]] | [[clan_showcase_cog]] | [[services_layer]]

---

## ⚡ Role Directory Lifecycle

```
[ Clan Leader Submits Profile ] ──► [ Staff Clicks "Approve & Publish" ]
                                                    │
                                                    ▼
• Role Created (with `//` suffix for scanner compatibility) / Linked to ClanSubmission
• @Clanless removed from Leader
• Live Clan Directory Panel EDITED in real time with new clan dropdown option!
```

---

## 🛡️ Clean Role Rules
1. **1 Clan Limit:** Selecting any clan role strips all other approved clan roles.
2. **Clanless Enforcement:**
   - Selecting a clan role automatically removes `@Clanless`.
   - Clicking `❌ Leave Clan / Clanless` removes clan roles and restores `@Clanless`.
3. **Keyword Search Modal (`🔍 Search / Type Clan`):**
   - Single match: immediately assigns role.
   - Multiple matches: surfaces ephemeral select menu.
   - 0 matches: feedback notice.

---

## 📌 Direct Code Pointers
- `ClanRoleSelect`: `cogs/clan_showcase.py` `L1167`
- `ClanSearchModal`: `cogs/clan_showcase.py` `L1271`
- `_refresh_clan_role_panel()`: `cogs/clan_showcase.py` `L1653`
- `/post-clan-role-panel`: `cogs/clan_showcase.py` `L2098`
- `/clan-delete` (`!clan_delete`): `cogs/clan_showcase.py` `L2504` (Admin: Unregisters clan & updates directory live)
- `/clan-sync-roles` (`!clan_sync_roles`): `cogs/clan_showcase.py` `L2623` (Automated server scan importing clan roles ending with `//`)
- `on_guild_role_update`: `cogs/clan_showcase.py` `L1479` (Live listener syncing Discord role renames/colors to clan database)
