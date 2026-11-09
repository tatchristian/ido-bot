# 📝 Workflow: User Registration & Region Catcher

**Backlink:** [[index]] | [[tournaments_cog]] | [[services_layer]]

---

## ⚡ Registration Lifecycle

```
[ Player clicks "⚔️ Register for Tournament" on Registration Hub ]
                                │
                                ▼
        [ UserRegistrationModal Pops Up (Single Modal) ]
             • In-Game Name (IGN): [ Required Input ]
             • Approved Weapon:    [ Placeholder e.g. Daggers ]
             • Region Tag:         [ Empty Input with gray placeholder e.g. ASIA, NA ]
                                │
                                ▼
                       [ Player Clicks Submit ]
                                │
            ┌───────────────────┴───────────────────┐
            │                                       │
     [ Region Allowed? ]                    [ Region Mismatched? ]
            │                                       │
            ▼                                       ▼
• Registered in Main Bracket             • Registration REJECTED immediately
• Live Slot Counter ticked up            • Ephemeral notice: "Restricted to ASIA"
• @Tournament Participant assigned       • Zero slots taken / bracket kept clean
```

---

## 📌 Direct Code Pointers
- **Modal Definition:** `cogs/tournaments.py` `L4340`
  - `region_input`: `L4362` (No default; uses gray placeholder showing tournament regions)
- **Validation Engine:** `cogs/tournaments.py` `L4367` & `services/tournament_service.py` `L310`
