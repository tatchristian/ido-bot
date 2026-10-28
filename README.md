# ⚔️ IDO Tournament Bot

A dedicated, high-reliability Discord Tournament and Roster Management Bot designed for the **International Dueling Organization (IDO)**. Built in **Python 3.11+** using **discord.py** (Slash Commands), atomic JSON storage with crash recovery, and **Docker** for continuous 24/7 cloud deployment.

---

## ✨ Features

- **🏆 Main Bracket & Standby Substitute Queue**:
  - Live participant tracking: Discord mention, In-Game Name (IGN), approved weapon, region, and check-in status.
  - Dedicated substitute queue to handle standby players and replace no-shows seamlessly.
  - Live ASCII visual slot capacity progress bar (`[████░░░░] 50%` / `[█░░░░░░░] 12%`).
- **🌍 Region Lock & Strict Validation**:
  - Configurable tournament region filters: single region (e.g. `NA`), combinations (e.g. `NA, EU`), or `GLOBAL`.
  - Standard supported regions: `NA`, `EU`, `OCE`, `ASIA`, `SA`.
  - Rejects ineligible registrations with: `"This tournament is only open to participants from: [allowed regions]"`.
- **⚔️ IDO Approved Weapons Support**:
  - Built-in choices for standard dueling weapons: `Daggers`, `Katana`, `Naginata`, `Bo Staff`, `Curved Swords`, `Warhammer`, `Kusarigama`.
  - Customizable per-tournament weapon rules via `/tournament-set-weapons`.
- **🎟️ Tournament Day Flow & Check-In System**:
  - Open and close tournament day check-ins (`/tournament-open-checkin` & `/tournament-checkin`).
  - Visual status badges on the roster (`[✅]` Checked In vs `[⏳]` Pending).
  - Broadcast mentions to participants via `/tournament-announce`.
- **📁 Bracket Export (Challonge / Start.gg / CSV)**:
  - Generate one-click exports directly formatted for Challonge bulk import, Start.gg, Battlefy, or Excel/Sheets (`/tournament-export`).
- **🛡️ High Reliability & Atomic Persistence**:
  - Atomic JSON writes via tempfile + `os.replace` to prevent corrupted state on sudden shutdowns.
  - Automatic rotating backup snapshots (`data/backups/`) with auto-pruning.
  - Self-healing crash recovery that automatically detects corrupt storage and rolls back to the latest valid backup.
- **🐳 24/7 Cloud Ready**:
  - Production `Dockerfile` and `docker-compose.yml`.
  - Ready for Koyeb, Railway, or VPS deployment.

---

## 📜 Tournament Commands

### 👤 Participant Commands

| Command | Usage | Description |
| :--- | :--- | :--- |
| `/help` | `/help [section:<category>] [ephemeral:<bool>]` | Interactive guide & command manual with quick-filter navigation buttons. |
| `/tournament-register` | `/tournament-register ign:<name> weapon:<choice> region:<choice>` | Sign up for the main tournament bracket. Increases live slot counter. |
| `/tournament-unregister` | `/tournament-unregister` | Withdraw from the main bracket (frees up slot for others). |
| `/tournament-sub-register` | `/tournament-sub-register ign:<name> weapon:<choice> region:<choice>` | Sign up for the standby substitute queue. |
| `/tournament-sub-unregister`| `/tournament-sub-unregister` | Withdraw from the substitute queue. |
| `/tournament-edit-entry` | `/tournament-edit-entry [weapon:<choice>] [ign:<name>] [region:<choice>]` | Update your weapon, IGN, or region without losing your bracket slot. |
| `/tournament-checkin` | `/tournament-checkin` | Confirm your presence on tournament day during the check-in window. |
| `/tournament-sub-checkin` | `/tournament-sub-checkin` | Confirm your active standby availability as a substitute on tournament day. |
| `/tournament-status` | `/tournament-status` | View main & substitute status, slot counters, visual progress bar, check-in status, allowed regions, and weapons. |
| `/tournament-roster` | `/tournament-roster` | View registered main bracket roster, check-in indicators, and standby substitute list. |

### 🛠️ Admin Controls

*Requires Server Administrator permissions or the `Tournament Admin` role.*

| Command | Usage | Description |
| :--- | :--- | :--- |
| `/tournament-open` | `[Admin] /tournament-open [name] [slots] [regions] [open_subs]` | Open main bracket registrations, set slot capacity, allowed regions, and substitute signups. |
| `/tournament-close` | `[Admin] /tournament-close` | Close main bracket registrations. |
| `/tournament-open-subs` | `[Admin] /tournament-open-subs` | Enable the substitute sign-up section for standby players. |
| `/tournament-close-subs` | `[Admin] /tournament-close-subs` | Disable substitute signups. |
| `/tournament-open-checkin` | `[Admin] /tournament-open-checkin` | Open the check-in window (e.g. 30-60m before tournament start). |
| `/tournament-close-checkin`| `[Admin] /tournament-close-checkin` | Close the check-in window. |
| `/tournament-promote-sub` | `[Admin] /tournament-promote-sub [substitute:<user>] [replace:<user>]` | Swap a no-show player with a standby substitute or promote the next sub in queue into an open slot. |
| `/tournament-kick` | `[Admin] /tournament-kick user:<user> [reason:<text>]` | Remove a specific user from either the main bracket or substitute queue. |
| `/tournament-force-register`| `[Admin] /tournament-force-register user:<user> ign:<name> weapon:<choice> region:<choice> [as_sub:bool]` | Manually slot a player into the main bracket or substitute queue (bypassing normal open/closed checks). |
| `/tournament-set-limit` | `[Admin] /tournament-set-limit limit:<number>` | Adjust the maximum participant limit counter (e.g. 8, 16, 32, 64). |
| `/tournament-set-regions`| `[Admin] /tournament-set-regions regions:<regions>` | Update the allowed regions filter (e.g. `GLOBAL`, `NA`, or `NA, EU`). |
| `/tournament-set-weapons`| `[Admin] /tournament-set-weapons [weapons:<text>]` | Set approved weapon classes for the event (e.g. Katana only, or custom list). |
| `/tournament-set-role`   | `[Admin] /tournament-set-role role:<role>` | Set or link the Discord role auto-assigned to main bracket participants. |
| `/tournament-view-role`  | `/tournament-view-role` | View the currently configured participant role. |
| `/tournament-set-channels`| `[Admin] /tournament-set-channels [announcements] [checkin] [subs]` | Configure dedicated channels for announcements, check-ins, and substitutes. |
| `/tournament-view-channels`| `/tournament-view-channels` | View the dedicated tournament channels currently configured. |
| `/tournament-set-admin-role`| `[Admin] /tournament-set-admin-role role:<role>` | Select which role (and higher) can manage tournaments. |
| `/tournament-view-admin-role`| `/tournament-view-admin-role` | View the currently configured tournament admin role. |
| `/tournament-announce` | `[Admin] /tournament-announce message:<text> [target:<group>]` | Ping registered main players, substitutes, or everyone with an announcement. |
| `/tournament-export` | `[Admin] /tournament-export [format:<choice>] [target:<scope>]` | Download a roster export formatted for **Challonge**, **Start.gg / Battlefy (CSV)**, or Text (excludes subs for bracket import by default). |
| `/tournament-clear` | `[Admin] /tournament-clear` | Wipe both main roster and substitute list for a fresh event. |

---

## 📁 Project Architecture

```
ido-bot/
├── cogs/
│   └── tournaments.py        # Slash command cog, UI interactions, and permission checks
├── services/
│   └── tournament_service.py # Pure domain logic: registrations, check-in, regions, substitutions, export
├── utils/
│   ├── storage.py            # Atomic JSON writes, crash recovery, and backup management
│   └── ui.py                 # Discord Embed and ASCII progress bar formatters
├── tests/
│   ├── test_storage.py       # Atomic writes and backup recovery unit tests
│   ├── test_tournament_service.py # Core registration, checkin, capacity, region, and sub queue tests
│   └── test_ui.py            # Embed formatting and progress bar tests
├── data/                     # Persistent storage directory (volume mounted in Docker)
│   └── backups/              # Automated rotating snapshot archives
├── bot.py                    # Bot initialization, command syncing, and graceful shutdown
├── config.py                 # Environment variables and configuration loader
├── Dockerfile                # Production Docker container definition
├── docker-compose.yml        # Docker Compose configuration
├── requirements.txt          # Python dependencies
└── .env.example              # Sample environment configuration
```

---

## ⚙️ Configuration (.env)

Create a `.env` file in the project root:

```env
# Required: Discord Bot Application Token
DISCORD_TOKEN=your_bot_token_here

# Optional: Specific Guild ID for instant slash command registration (leave blank for global sync)
GUILD_ID=

# Storage configuration
DATA_DIR=data
MAX_BACKUPS=20

# Roles and Permissions
ADMIN_ROLE_NAME=Tournament Admin

# Branding & Appearance
ORGANIZATION_NAME=IDO
EMBED_COLOR=0xF1C40F
```

---

## 🚀 Local Setup & Testing

### 1. Install Dependencies
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Run the Unit Test Suite
```bash
pytest tests/ -v
```

### 3. Start the Bot Locally
```bash
python bot.py
```

---

## 🐳 Docker & Docker Compose Deployment

```bash
# Build and start container in detached mode
docker compose up -d --build

# View container logs
docker compose logs -f

# Stop container
docker compose down
```

---

## 🏛️ Automated Server Layout Builder

If recreating or configuring an official IDO tournament community server, you can automatically build the complete category and channel architecture with built-in rate-limit throttling (1.2s delay) and automatic 3v3 filtering:

### Option A: Standalone Python Script
```bash
# Using TARGET_GUILD_ID from .env:
python build_ido_server.py

# Or target a specific server directly:
python build_ido_server.py --guild-id 123456789012345678
```

### Option B: Hidden Administrator Commands
- **Slash Command:** `/build-ido-template confirm:True` (Requires Administrator permissions; only visible to admins).
- **Prefix Command:** `!build-ido-template yes` (Hidden prefix command that does not appear in autocomplete).


---

## ☁️ 24/7 Cloud Deployment on Koyeb

1. **Push Code to GitHub**:
   Push your bot repository to GitHub (`.env` is ignored by default).
2. **Create New Service on Koyeb**:
   - Go to Koyeb and click **Create Service**.
   - Choose **GitHub** as the source and select your `ido-bot` repository.
   - Choose **Worker** service type.
3. **Attach Persistent Storage**:
   - In the **Volumes** section, create and attach a persistent volume:
     - Mount path: `/app/data`
     - Size: `1 GB`
4. **Environment Variables**:
   - Add:
     - `DISCORD_TOKEN`: `your_bot_token_here`
     - `DATA_DIR`: `/app/data`
     - `MAX_BACKUPS`: `20`
     - `ADMIN_ROLE_NAME`: `Tournament Admin`
     - `ORGANIZATION_NAME`: `IDO`
5. **Deploy**:
   - Click **Deploy**. Koyeb builds the `Dockerfile`, mounts `/app/data`, and keeps the bot running 24/7.
