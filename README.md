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
  - **On Approval:** Publishes embed live to `#official-clan-list`, disables staff review buttons, logs approver, and DMs the applicant with a link to their post.
  - **On Rejection:** Opens an interactive modal prompting staff for a rejection reason, updates the staff log, and DMs the applicant explaining what to fix.
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

### 🏛️ 2. Clan Showcase Commands *(Clan Leaders & Members — Public)*

| Interface / Command | Description |
| :--- | :--- |
| **`📋 Submit Clan Profile` Button** | Placed in your designated clan intake channel. Click this button to open the submission form and enter your details with an image link. |
| **`📱 Choose Photo from Device` Button** | Guidance button on the submission panel explaining how to pick a photo directly from your mobile camera roll or saved GIFs without needing links. |
| `/clan-submit [image] [image_url]` | **Dual-Choice Intake:** Upload a photo/GIF directly from your device library (`image`) or provide an image link (`image_url`). Automatically opens the submission form with your image attached! *(Prefix fallback: `!clan_submit`)* |
| `/clan-showcase-preview` | Test how your clan showcase embed will look before submitting. Specify clan name, optional hex color, and direct logo URL. *(Ephemeral: only visible to you)* |

---

### 🛠️ 3. Tournament Admin Commands *(Staff / Admins Only)*

*Requires Server Administrator permissions or the configured `Tournament Admin` role.*

| Command | Description |
| :--- | :--- |
| `/tournament-open` | Open main bracket registrations, set slot capacity, allowed regions, and substitute signups. |
| `/tournament-close` | Close main bracket registrations. |
| `/tournament-open-subs` / `/tournament-close-subs` | Enable or disable standby substitute queue signups. |
| `/tournament-open-checkin` / `/tournament-close-checkin` | Open or close the check-in window before tournament start. |
| `/tournament-promote-sub` | Swap a no-show player with a standby sub or promote the next sub in queue. |
| `/tournament-kick` | Remove a player from either the main bracket or substitute queue. |
| `/tournament-force-register` | Manually insert a player or VIP into main bracket or substitute queue. |
| `/tournament-set-limit` | Adjust the maximum participant limit counter (e.g. 16, 32, 64). |
| `/tournament-set-regions` | Update allowed regions filter (e.g. `GLOBAL`, `NA`, or `NA, EU`). |
| `/tournament-set-weapons` | Set approved weapon classes for the event. |
| `/tournament-set-role` / `/tournament-view-role` | Set or view the Discord role auto-assigned to tournament participants. |
| `/tournament-set-channels` / `/tournament-view-channels` | Configure or view dedicated tournament channels. |
| `/tournament-set-admin-role` / `/tournament-view-admin-role` | Select which role (and higher) can manage tournaments. |
| `/tournament-announce` | Ping registered main players, substitutes, or everyone with an announcement. |
| `/tournament-schedule-event` | Schedule an official Discord server event (displayed at the top of the server) which automatically feeds to `unitedduelingamity.org`. |
| `/tournament-cancel-event` | Cancel and delete an upcoming event from Discord and automatically remove it from the website schedule. |
| `/tournament-complete-event` | Conclude a tournament, crown the champion and runner-up, and publish to website Past Results. |
| `/tournament-remove-past-result` | Remove an event record from the website's Past Results archive. |
| `/post-event-scheduler-panel` | Post the 1-click interactive Tournament & Event Scheduler panel with persistent modal button in staff channels *(Prefix: `!post_event_scheduler_panel`)*. |
| `/tournament-export` | Download a roster export formatted for **Challonge**, **Start.gg / Battlefy (CSV)**, or Text. |
| `/tournament-clear` | Wipe both main roster and substitute list for a fresh event. |
| `/tournament-setup-section` | Auto-construct complete tournament category, channel layout, and permissions. |
| `/tournament-remove-section` | Safely clean up and delete the auto-generated tournament section. |

---

### 🔒 4. Clan Showcase Admin Commands *(Staff / Admins Only)*

*Requires Server Administrator permissions, Manage Server, or designated Tournament Admin role.*

| Command | Usage | Description |
| :--- | :--- | :--- |
| `/post-clan-submission-panel` | `/post-clan-submission-panel [channel]` | Post the official clan intake panel with the persistent **`📋 Submit Clan Profile`** button in the target channel *(Prefix fallback: `!post_clan_submission_panel`)*. |
| `/clan-showcase-channels` | `/clan-showcase-channels [showcase_channel] [staff_review_channel]` | Configure where approved embeds are published and where private staff reviews appear. |
| `/clan-showcase-view-channels`| `/clan-showcase-view-channels` | Inspect current showcase and review channel routing. |
| `/clan-showcase-edit` | `/clan-showcase-edit clan:<name_or_id>` | Search and live-edit any clan profile. Automatically edits the live published embed in Discord *(Prefix fallback: `!clan_edit <name>`)*. |
| **`Approve & Publish` Button** | Click on review message | Instantly publishes finished embed to the public showcase channel, updates the website directory, and notifies the applicant via DM. |
| **`Reject` Button** | Click on review message | Opens modal for rejection reason, updates staff log, and DMs applicant with the explanation. |

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
  * **Date & Time:** (e.g. `2026-11-15 18:00 EST` or `11/15 6:00 PM EST`)
  * **Duration & Location:** (e.g. `2 hours | Dueling Grounds Arena`)
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
