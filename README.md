# ⚔️ UDA Tournament & Clan Showcase Bot (DUKE)

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![discord.py 2.x](https://img.shields.io/badge/discord.py-2.x-5865F2.svg)](https://github.com/Rapptz/discord.py)
[![Docker Ready](https://img.shields.io/badge/docker-ready-2496ED.svg)](https://www.docker.com/)
[![Tests Passing](https://img.shields.io/badge/tests-45%20passed-brightgreen.svg)]()

A high-reliability, modular Discord Bot engineered for **United Dueling Amity (UDA)**. Provides end-to-end competitive tournament roster management, automated server layout construction, and an interactive, Sapphire-style **Clan Profile Showcase & Staff Approval System**.

---

## 🎨 Official UDA Brand Identity & Color Palette

Rooted in the official **UDA Cerberus emblem** (3-headed white wolf with gold collar and emerald gemstones):

| Element | Color Name | Hex Code | Purpose in Bot |
| :--- | :--- | :--- | :--- |
| **Primary Theme** | Emerald Gemstone | `#10B981` | Default embed borders, check-in badges, success indicators |
| **Accent & Trim** | Royal Antique Gold | `#D4AF37` | Warning badges, tournament titles, and admin highlight accents |
| **Contrast / Text**| Marble White | `#F8FAFC` | Roster text, author lines, and modal placeholders |
| **Background** | Onyx Slate | `#0F172A` | Deep dark mode embed backdrop matching Discord |

---

## ✨ Core Systems & Features

### 🏆 1. Complete Tournament Engine
- **Main Bracket & Standby Substitute Queue**:
  - Live participant tracking: Discord mention, In-Game Name (IGN), approved weapon class, region, and check-in status.
  - Dedicated substitute queue with FIFO promotion and automatic no-show replacements (`/tournament-promote-sub`).
  - Live ASCII visual slot capacity progress bar (`[████░░░░] 50%` / `[█░░░░░░░] 12%`).
- **🌍 Region Lock & Strict Validation**:
  - Configurable tournament region filters: single region (e.g. `NA`), combinations (e.g. `NA, EU`), or `GLOBAL`.
  - Standard supported regions: `NA`, `EU`, `OCE`, `ASIA`, `SA`.
- **⚔️ UDA Approved Weapons**:
  - Default choices: `Daggers`, `Katana`, `Naginata`, `Bo Staff`, `Curved Swords`, `Warhammer`, `Kusarigama`, `Gauntlets`.
  - Customizable per-tournament rules via `/tournament-set-weapons`.
- **🎟️ Check-In Window & Readiness**:
  - Open and close tournament day check-in (`/tournament-open-checkin` & `/tournament-checkin`).
  - Visual status badges on the roster (`[✅]` Checked In vs `[⏳]` Pending).
  - Broadcast targeted announcements to main players or substitutes via `/tournament-announce`.
- **📁 1-Click Tournament Bracket Export**:
  - Download formatted roster files ready for bulk import into **Challonge**, **Start.gg**, **Battlefy (CSV)**, or Plain Text.
- **🛡️ 1-Click Staff Operations Control Center (`/post-tournament-staff-panel`)**:
  - Persistent control center panel for staff channels with instant 1-click actions and private (ephemeral) operational receipts.
  - Dedicated **`⚙️ Create Tournament`** configuration form (sets title, capacity, regions, and channel without opening registrations prematurely).
  - 1-click **`🟢 Open Registrations`** (instantly opens signups, unlocks `#tournament-registration`, and broadcasts welcome banner).
  - 1-click **`🛡️ Toggle Subs`** (instantly toggles standby substitute bench and auto-posts substitute banner).
  - 1-click **`🔒 Close Registrations`**, **`🎟️ Toggle Check-In`**, **`🔄 Promote Sub`**, and **`📊 Roster & Status`**.

---

### 🏛️ 2. Automated Clan Profile Showcase (Sapphire Replacement)
Replaces manual embed bot dashboards (like Sapphire) with a 100% native, automated Discord UI workflow:
- **Persistent Submission Panel**:
  - Admin command `/post-clan-submission-panel` drops an embed with a permanent **`📋 Submit Clan Profile`** button.
  - Survives bot reboots and container redeployments (`timeout=None`).
- **Interactive 5-Field Modal Intake**:
  - **Clan Name & Color (Optional):** Enter clan name (with optional `#hexcode` for custom border color; defaults to official UDA emerald-green `#10b981`).
  - **Clan Metadata:** Region, Founded Date, Leaders, Co-Leaders, Status (supports plain IGNs or `@mentions`).
  - **Clan Description & Philosophy:** Clan backstory, vision, and goals.
  - **Activities & Motto:** Clan wars, scrims, training schedule, and clan motto.
  - **Logo URL:** Direct image link (Discord CDN, Imgur, PNG, JPG).
- **Safe 2-Stage Draft & Confirmation Flow**:
  - Submitting the modal does **not** send directly to staff. Instead, it generates a private (ephemeral) **Draft Preview**.
  - Includes **`🚀 Confirm & Send to Staff`**, **`✏️ Edit Draft`**, and **`🗑️ Discard Draft`** buttons.
  - Decisions are **never final until confirmed**.
  - If a user closes out accidentally, DUKE **auto-restores their draft** upon clicking the button again.
- **Sapphire-Identical Embed Staging**:
  - **Author Header:** Clan Name + circular emblem icon.
  - **Description Block:** Unified markdown layout with metadata, description, activities, and motto.
  - **Large Bottom Image:** Emblem artwork rendered large below the text (`embed.set_image`).
- **Staff Review & Approval Workflow**:
  - Submissions are staged in a private staff channel (`STAFF_REVIEW_CHANNEL_ID` or `/clan-showcase-channels`).
  - Attached persistent review buttons: **`Approve & Publish`** and **`Reject`**.
  - **On Approval:** Publishes embed live to `#official-clan-list`, creates Discord clan role with ` //` suffix (for server clan scanner compatibility), assigns role to leader, removes `@Clanless`, disables staff review buttons, logs approver, and DMs the applicant.
  - **On Rejection:** Opens an interactive modal prompting staff for a rejection reason, updates the staff log, and DMs the applicant explaining what to fix.
- **Self-Serve Clan Role Directory & Alignment Panel (`/post-clan-role-panel`)**:
  - Interactive public panel in `#clan-roles` where members self-select their clan role from dynamic dropdowns.
  - **Scalable Alphabetical Chunking:** Automatically divides clans across select menus (e.g. `A – M`, `N – Z`) to surpass Discord's 25-option limit.
  - **`🔍 Search / Type Clan` Modal:** Instant keyword search popup to find and claim any clan role.
  - **`@Clanless` Enforcement:** Automatically removes `@Clanless` on joining a clan, restricts users to 1 clan at a time, and restores `@Clanless` when clicking `❌ Leave Clan`.
  - **Live Auto-Updates:** Panel updates in real time on approvals, renames, edits, or deletions with zero manual refresh needed.
- **Automated Clan Scanner & Live Role Sync**:
  - `/clan-sync-roles`: Scans all server roles ending with `//`, imports clean names into the verified database, and binds Discord role IDs in seconds.
  - `on_guild_role_update`: Automatically detects clan role renames and color changes in Server Settings and updates the database & panel live.
- **Clan Deletion (`/clan-delete`)**:
  - Unregisters a clan from the database and directory panel with optional automatic Discord role deletion.
- **Live Admin Editing (`/clan-showcase-edit`)**:
  - Admins can edit any existing clan profile live at any time.
  - Live autocomplete dropdown to pick any registered clan.
  - Pre-fills modal with the clan's current data.
  - Submitting edits automatically updates both the database **and edits the live published Discord embed in real time**.

---

### 🏗️ 3. Automated Server Section Builder
- **Build Section & Link Channels:** `/tournament-setup-section confirm:True`
  - Constructs `🏆 TOURNAMENT HUB 🏆`, `⚔️ MATCH ARENAS ⚔️`, and `🔒 TOURNAMENT OPERATIONS`.
  - Automatically configures channel permissions (read-only for announcements & rules, private for staff).
  - Automatically links `#tournament-announcements`, `#tournament-checkin`, and `#substitutes-bench` to the bot.
  - Includes an interactive **Undo Tournament Section** button on the confirmation embed.
- **Remove Tournament Section:** `/tournament-remove-section confirm:True`
  - Safely deletes only the tournament categories and channels created by DUKE without touching community channels.

---

### 🛡️ 4. High-Reliability Atomic Storage
- Atomic JSON writes via temporary files and `os.replace` to prevent corrupted state on sudden container restarts.
- Automatic rotating backup snapshots (`data/backups/`) with auto-pruning.
- Self-healing crash recovery that automatically detects corrupt storage and rolls back to the latest valid backup.

---

## 📜 Complete Command Reference

### 👤 1. Tournament Participant Commands *(Public)*

| Command | Usage | Description |
| :--- | :--- | :--- |
| `/tournament-help` | `/tournament-help [section:<category>] [ephemeral:<bool>]` | Interactive command manual with quick-filter navigation buttons. |
| `/tournament-register` | `/tournament-register ign:<name> weapon:<choice> region:<choice>` | Sign up for the main tournament bracket. |
| `/tournament-unregister` | `/tournament-unregister` | Withdraw from the main bracket (frees up slot for others). |
| `/tournament-sub-register` | `/tournament-sub-register ign:<name> weapon:<choice> region:<choice>` | Sign up for the standby substitute queue. |
| `/tournament-sub-unregister`| `/tournament-sub-unregister` | Withdraw from the substitute queue. |
| `/tournament-edit-entry` | `/tournament-edit-entry [weapon:<choice>] [ign:<name>] [region:<choice>]` | Update your weapon, IGN, or region without losing your bracket slot. |
| `/tournament-checkin` | `/tournament-checkin` | Confirm your presence on tournament day during the check-in window. |
| `/tournament-sub-checkin` | `/tournament-sub-checkin` | Confirm your active standby availability as a substitute on tournament day. |
| `/tournament-status` | `/tournament-status` | View main & substitute status, slot counters, visual progress bar, check-in status, allowed regions, and weapons. |
| `/tournament-roster` | `/tournament-roster` | View registered main bracket roster, check-in indicators, and standby substitute list. |

---

### 🏛️ 2. Clan Showcase & Role Directory Commands *(Public)*

| Interface / Command | Description |
| :--- | :--- |
| **`📋 Submit Clan Profile` Button** | Placed in your designated clan intake channel. Click this button to open the submission form with a clean, grayed-out generic template. |
| **`📱 Choose Photo from Device` Button** | Guidance button on the submission panel explaining how to pick a photo directly from your mobile camera roll or saved GIFs without needing links. |
| `/clan-submit [image] [image_url]` | **Dual-Choice Intake:** Upload a photo/GIF directly from your device library (`image`) or provide an image link (`image_url`). Automatically opens the submission form with your image attached! *(Prefix fallback: `!clan_submit`)* |
| `/clan-showcase-preview` | Test how your clan showcase embed will look before submitting. Specify clan name, optional hex color, and direct logo URL. *(Ephemeral: only visible to you)* |
| `/clan-claim clan:<name>` | Claim your approved clan role directly via command with autocomplete search. Automatically removes `@Clanless`. |
| `/clan-leave` | Leave your active clan role and immediately restore the `@Clanless` role. |

---

### 🛠️ 3. Tournament Admin Controls — Operations *(Staff / Admins Only)*

*Requires Server Administrator permissions or the configured `Tournament Admin` role.*

| Command | Description |
| :--- | :--- |
| `/tournament-open` | Open main bracket registrations, set slot capacity, allowed regions, substitute signups, and optional custom registration channel. Automatically broadcasts announcement banner! |
| `/tournament-close` | Close main bracket registrations. |
| `/tournament-open-subs` / `/tournament-close-subs` | Enable or disable standby substitute queue signups. |
| `/tournament-open-checkin` / `/tournament-close-checkin` | Open or close the check-in window before tournament start. |
| `/tournament-set-time` | Set official match day date, time, and timezone for automated contestant reminder DMs *(supports relative keywords like `This Weekend` or `Saturday`)*. |
| `/tournament-view-time` | View scheduled match day date, time, and contestant reminder delivery status. |
| `/tournament-test-reminder` | Preview and test-send the Day-Of morning reminder or 30-minute reminder DM to yourself. |
| `/tournament-promote-sub` | Swap a no-show player with a standby sub or promote next sub in queue *(with player autocomplete)*. |
| `/tournament-kick` | Remove a player from either the main bracket or substitute queue *(with player autocomplete)*. |
| `/tournament-force-register` | Manually insert a player or VIP into main bracket or substitute queue. |
| `/tournament-set-limit` | Adjust the maximum participant limit counter (e.g. 16, 32, 64). |
| `/tournament-set-regions` | Update allowed regions filter (e.g. `GLOBAL`, `NA`, or `NA, EU`). |
| `/tournament-set-weapons` | Set approved weapon classes for the event. |
| `/tournament-announce` | Ping registered main players, substitutes, or everyone with an announcement. |
| `/tournament-export` | Download a roster export formatted for **Challonge**, **Start.gg / Battlefy (CSV)**, or Text. |
| `/tournament-clear` | Wipe both main roster and substitute list for a fresh event *(ephemeral confirmation)*. |

---

### ⚙️ 4. Server Setup & Configuration Commands *(Staff / Admins Only)*

*Commands used during server onboarding, channel restructuring, or linking bot components.*

| Command | Usage | Description |
| :--- | :--- | :--- |
| `/tournament-setup-section` | `/tournament-setup-section confirm:True` | **1-Click Auto-Builder:** Constructs `🏆 TOURNAMENT HUB`, `⚔️ MATCH ARENAS`, and `🔒 TOURNAMENT OPERATIONS` categories, channels, and permissions *(Prefix: `!tournament_setup_section`)*. |
| `/tournament-set-channels` | `/tournament-set-channels [announcements] [registration] [checkin] [substitutes]` | Batch-link dedicated channels for announcements, registration, check-in, and substitutes. |
| `/tournament-set-channel` | `/tournament-set-channel target:[registration\|announcements\|checkin\|substitutes] channel:#channel` | **Quick Channel Routing:** Set or update an individual dedicated channel if channels are deleted, renamed, or recreated *(Prefix: `!set_channel <target> <#channel>`)*. |
| `/tournament-view-channels` | `/tournament-view-channels` | View current dedicated tournament channel links and status. |
| `/tournament-set-admin-role` | `/tournament-set-admin-role role:@Role` | Set which staff role is authorized to execute tournament administration controls *(Prefix: `!set_admin_role`)*. |
| `/tournament-view-admin-role`| `/tournament-view-admin-role` | View current authorized tournament staff admin role. |
| `/tournament-set-event-role` | `/tournament-set-event-role role:@Role` | Set role authorized for Discord scheduled events & live website sync *(Prefix: `/set-event-role`)*. |
| `/tournament-view-event-role`| `/tournament-view-event-role` | View current authorized event manager role. |
| `/tournament-set-role` | `/tournament-set-role role:@Role` | Configure or link the Discord role auto-assigned to tournament participants upon registration. |
| `/tournament-view-role` | `/tournament-view-role` | View current participant role. |
| `/post-tournament-staff-panel`| `/post-tournament-staff-panel [channel]` | Post the 1-click interactive Staff Operations Control Center with buttons in staff channels *(Prefix: `!post_tournament_staff_panel`)*. |
| `/post-registration-panel` | `/post-registration-panel [channel]` | Post or refresh the live interactive Player Registration Hub with entry modal, live progress bar, and slot counter *(Prefix: `!post_registration_panel`)*. |
| `/post-subs-panel` | `/post-subs-panel [channel]` | Post or refresh the live interactive Standby Substitute Hub with queue modal and position tracker *(Prefix: `!post_subs_panel`)*. |
| `/post-staff-guide` | `/post-staff-guide [channel]` | Post the interactive Tournament Staff Guide & Cheat Sheet with phase dropdown selector *(Prefix: `!post_staff_guide`)*. |
| `/post-event-scheduler-panel` | `/post-event-scheduler-panel [channel]` | Post 1-click interactive Event Scheduler panel for top-of-server banners and website sync *(Prefix: `!post_event_scheduler_panel`)*. |
| `/post-clan-submission-panel` | `/post-clan-submission-panel [channel]` | Post interactive Clan Showcase intake portal panel *(Prefix: `!post_clan_submission_panel`)*. |
| `/post-clan-role-panel` | `/post-clan-role-panel [channel]` | Post the live self-serve Clan Role Selection directory panel with alphabetical chunking & search modal *(Prefix: `!post_clan_role_panel`)*. |
| `/clan-showcase-channels` | `/clan-showcase-channels [showcase] [staff_review]` | Configure target showcase channel and staff review channel for clan profiles. |
| `/clan-showcase-view-channels`| `/clan-showcase-view-channels` | Inspect current clan showcase and review channel routing. |
| `/clan-set-clanless-role` | `/clan-set-clanless-role role:@Role` | Designate which Discord role is auto-enforced for `@Clanless` members *(Prefix: `!set_clanless_role`)*. |
| `/clan-role-edit` | `/clan-role-edit clan:<name>` | Modify the linked Discord role or metadata for any approved clan profile. |
| `/clan-role-panel-refresh` | `/clan-role-panel-refresh` | Manually force-refresh the live Clan Role Assignment Panel *(Prefix: `!refresh_clan_role_panel`)*. |
| `/clan-sync-roles` | `/clan-sync-roles [suffix]` | Automated scanner: scan server roles ending with `//` and import into clan database *(Prefix: `!clan_sync_roles`)*. |
| `/clan-delete` | `/clan-delete clan:<name> [delete_discord_role]` | Delete a clan from database & Claim Role panel with optional Discord role removal *(Prefix: `!clan_delete`)*. |
| `/tournament-remove-section`| `/tournament-remove-section confirm:True` | Safely remove the auto-generated tournament channels and categories without touching other server channels. |

---

### 🌐 5. Tournament Event Scheduling & Website Live Sync (`unitedduelingamity.org`)

Duke hosts a public REST API server with full CORS support directly feeding **`https://unitedduelingamity.org`**. 

No manual API keys or push commands are needed—events scheduled in Discord and approved clan profiles appear on the website automatically.

#### 📅 1-Click Interactive Scheduler Panel
Staff can drop a permanent interactive scheduler panel into any admin channel:
```
/post-event-scheduler-panel [channel:#channel]
```
*(Or prefix command: `!post_event_scheduler_panel`)*

* **`📅 Schedule Tournament Event` Button:** Opens a 4-field modal:
  * **Event Title:** (e.g. `Autumn Clan Cup 2026`)
  * **Date & Time (with Timezone):** Supports calendar dates or natural weekend phrases:
    * Relative: `This Weekend 18:00 IST`, `Saturday 6:00 PM EST`, `Sunday 14:00 UTC`, `Tomorrow 19:00 CST`.
    * Exact: `2026-11-15 18:00 EST` or `11/15/2026 6:00 PM EST`.
    * **International Timezone Codes:** Universal support for standard international timezone abbreviations (`IST`, `EST`, `CST`, `PST`, `UTC`, `GMT`, `CET`, `BST`, `GST`, `JST`, `KST`, `SGT`, `HKT`, `AEST`, `BRT`, `NZST`, or numeric `UTC±H(:M)`). Strictly standard codes only—no city names!
  * **Duration & Location:** Supports multi-day durations and locations:
    * `Weekend | DUKE Tournament Hub` (automatically computes 48.0 hours).
    * `3 days | Arena` (72.0 hours).
    * `1 day | Tournament Hub` (24.0 hours).
    * `2 hours | Dueling Grounds Arena`.
  * **Description:** Format, weapon rules, and prize info.
* **`🌐 Website Feed Status` Button:** Ephemeral button that displays the live status of the public REST API and provides direct links to verify upcoming events and leaderboard feeds.

#### ⚡ Automatic Live Sync
* **Top-of-Server Event:** Discord immediately displays the event at the top of the server banner so members can click **Interested** for reminders.
* **Website Upcoming Schedule:** Duke's API server serves the event at `GET /tournaments`. The website's `script.js` renders the date badge, event tag, title, and description automatically.

#### 🗑️ Canceling an Upcoming Event
To cancel an event and remove it from both Discord and the website:
```
/tournament-cancel-event event:<event_name_or_id>
```
*(Features interactive Discord autocomplete of currently scheduled events)*.

#### 🏆 Concluding an Event & Publishing to Past Results
When a tournament finishes, crown the champion and publish to the website's Past Results archive:
```
/tournament-complete-event event:<event> champion:<clan_or_player> [runner_up:<name>] [score:<3-1>] [notes:<text>]
```
* Concludes the Discord scheduled event so it leaves the "Upcoming" list.
* Saves the historical record to `data/past_results.json`.
* Exposes the record via `GET /past-results` (and `GET /tournaments/past`) for the website's Past Results section.

#### ❌ Deleting a Past Result
To delete an archived result from the website:
```
/tournament-remove-past-result result:<event_name_or_id>
```
*(Features interactive Discord autocomplete of past tournament archives)*.

#### 📡 Public REST API Endpoints
| Endpoint | Method | Output | Description |
| :--- | :--- | :--- | :--- |
| `/tournaments` | `GET` | JSON Array | Active & upcoming scheduled events for `tournaments.html`. |
| `/past-results` | `GET` | JSON Array | Historical champions, runner-ups, and match scores. |
| `/leaderboard` (or `/clans`) | `GET` | JSON Array | Approved clans, logos, Banner Points, and mottos for `leaderboard.html`. |
| `/players` | `GET` | JSON Array | Registered players, ratings, and weapon masteries. |
| `/health` | `GET` | Text | Health check for 24/7 cloud hosts (Render / Koyeb). |

---

## 📁 Project Architecture

```
ido-bot/
├── memory/                       # Obsidian Second Brain & Architectural Mind Map
│   ├── index.md                  # Master mind map navigation hub
│   ├── tournaments_cog.md        # Bracket management, staff operations & registration hubs
│   ├── clan_showcase_cog.md      # Clan profile intake, role directory, scanner & deletion
│   ├── services_layer.md         # TournamentService, ClanShowcaseService, WebsiteSync
│   └── workflow_*.md             # Operational lifecycle & sync workflows
├── Bot_Memory_Map.canvas         # Interactive visual Obsidian Canvas node map
├── cogs/
│   ├── tournaments.py            # Tournament bracket slash commands, checkin, and help menu
│   └── clan_showcase.py          # Clan modal forms, persistent buttons, staff review flow, live admin edit
├── services/
│   ├── tournament_service.py     # Core domain logic: registrations, substitutions, check-in, regions, export
│   ├── clan_showcase_service.py  # Clan submission lifecycle, embed formatting engine, atomic JSON persistence
│   └── server_builder.py         # Automated Discord server category & channel builder with safety undo
├── utils/
│   ├── storage.py                # Atomic JSON persistence with rotating backup rotation and crash recovery
│   └── ui.py                     # Discord Embed formatters, progress bars, and help manual builder
├── tests/
│   ├── test_tournament_service.py# Registration, check-in, FIFO substitution queue tests
│   ├── test_clan_showcase.py     # Color parser, URL validator, embed builder, and submission lifecycle tests
│   ├── test_server_builder.py    # Channel generation and permission overwrites tests
│   ├── test_storage.py           # Atomic writes, backup recovery, and corruption healing tests
│   └── test_ui.py                # Progress bar and embed rendering unit tests
├── data/                         # Persistent storage volume (mapped in Docker / Koyeb)
│   ├── tournament.json           # Live tournament state
│   ├── clan_submissions.json     # Live clan profiles and staff review mappings
│   └── backups/                  # Automated backup rotation archives
├── bot.py                        # Bot entry point, extension loader, health check server, graceful shutdown
├── config.py                     # Environment variables and typed configuration loader
├── Dockerfile                    # Production container image definition
├── docker-compose.yml            # Docker Compose specification
├── requirements.txt              # Production Python dependencies
└── .env.example                  # Environment template
```

---

## ⚙️ Environment Variables (.env)

Create a `.env` file in the project root:

```env
# Required: Discord Bot Application Token (from Discord Developer Portal)
DISCORD_TOKEN=your_bot_token_here

# Optional: Specific Guild ID for instant slash command registration (leave blank for global sync)
GUILD_ID=

# Storage Directory
DATA_DIR=data
MAX_BACKUPS=20

# Roles and Permissions
ADMIN_ROLE_NAME=Tournament Admin
ADMIN_ROLE_ID=

# Clan Profile Showcase Extension Channels
SHOWCASE_CHANNEL_ID=
STAFF_REVIEW_CHANNEL_ID=

# Branding & Colors (Official UDA Emerald Gemstone #10B981)
ORGANIZATION_NAME=UDA
EMBED_COLOR=0x10B981
```

---

## 🚀 Local Setup & Testing

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/tatchristian/ido-bot.git
cd ido-bot

python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Run the Full Test Suite
```bash
pytest tests/ -v
```

### 3. Start the Bot
```bash
python bot.py
```

---

## 🐳 Docker Deployment

Run with Docker Compose:

```bash
# Build and run detached
docker compose up -d --build

# View real-time logs
docker compose logs -f

# Stop container
docker compose down
```

---

## ☁️ 24/7 Cloud Deployment (Koyeb / Render)

### Koyeb
1. **Repository**: Link your GitHub repository `tatchristian/ido-bot`.
2. **Service Type**: Worker (or Web with port `8000`).
3. **Persistent Volume**:
   - Mount path: `/app/data`
   - Size: `1 GB` (ensures `tournament.json` and `clan_submissions.json` survive restarts).
4. **Environment Variables**:
   - Add `DISCORD_TOKEN`, `DATA_DIR=/app/data`, `ADMIN_ROLE_NAME=Tournament Admin`, `ORGANIZATION_NAME=UDA`, `EMBED_COLOR=0x10B981`, `SHOWCASE_CHANNEL_ID`, `STAFF_REVIEW_CHANNEL_ID`.
5. **Deploy**: Click Deploy. Koyeb builds the image and keeps the bot running 24/7.

### Render
1. Create a **Background Worker** (or **Web Service** with Health Check on `/health`).
2. Set Environment to **Python 3**.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python bot.py`
5. Add a **Persistent Disk** mounted at `/app/data`.
6. Add environment variables in the Render Dashboard (`ORGANIZATION_NAME=UDA`, `EMBED_COLOR=0x10B981`, etc.).
