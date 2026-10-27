# ⚔️ IDO Tournament Bot

A dedicated, high-reliability Discord Tournament and Roster Management Bot designed for the **International Dueling Organization (IDO)**. Built in **Python 3.11+** using **discord.py** (Slash Commands), atomic JSON storage with crash recovery, and **Docker** for continuous 24/7 cloud deployment.

---

## ✨ Features

- **🏆 Main Bracket & Standby Substitute Queue**:
  - Live participant tracking: Discord mention, In-Game Name (IGN), approved weapon, and region.
  - Dedicated substitute queue to handle standby players and replace no-shows seamlessly.
  - Live ASCII visual slot capacity progress bar (`[████░░░░] 50%` / `[█░░░░░░░] 12%`).
- **🌍 Region Lock & Strict Validation**:
  - Configurable tournament region filters: single region (e.g. `NA`), combinations (e.g. `NA, EU`), or `GLOBAL`.
  - Rejects ineligible registrations with: `"This tournament is only open to participants from: [allowed regions]"`.
- **⚔️ IDO Approved Weapons Support**:
  - Built-in choices for standard dueling weapons: `Daggers`, `Katana`, `Naginata`, `Bo Staff`, `Curved Swords`, `Warhammer`, `Kusarigama`.
- **🛡️ High Reliability & Atomic Persistence**:
  - Atomic JSON writes via tempfile + `os.replace` to prevent corrupted state on sudden shutdowns.
  - Automatic rotating backup snapshots (`data/backups/`) with auto-pruning.
  - Self-healing crash recovery that automatically detects corrupt storage and rolls back to the latest valid backup.
- **🐳 24/7 Cloud Ready**:
  - Production `Dockerfile` and `docker-compose.yml`.
  - Turnkey deployment to cloud platforms like **Koyeb**, **Railway**, or any VPS.

---

## 📜 Tournament Commands

### 👤 Participant Commands

| Command | Usage | Description |
| :--- | :--- | :--- |
| `/tournament-register` | `/tournament-register ign:<name> weapon:<choice> region:<choice>` | Sign up for the main tournament bracket. Increases live slot counter. |
| `/tournament-unregister` | `/tournament-unregister` | Withdraw from the main bracket (frees up slot for others). |
| `/tournament-sub-register` | `/tournament-sub-register ign:<name> weapon:<choice> region:<choice>` | Sign up for the standby substitute queue. |
| `/tournament-sub-unregister`| `/tournament-sub-unregister` | Withdraw from the substitute queue. |
| `/tournament-status` | `/tournament-status` | View main & substitute status, slot counters, visual progress bar, allowed regions, and approved weapons. |
| `/tournament-roster` | `/tournament-roster` | View registered main bracket roster and standby substitute list. |

### 🛠️ Admin Controls

*Requires Server Administrator permissions or the `Tournament Admin` role.*

| Command | Usage | Description |
| :--- | :--- | :--- |
| `/tournament-open` | `[Admin] /tournament-open [name] [slots] [regions] [open_subs]` | Open main bracket registrations, set slot capacity, allowed regions, and substitute signups. |
| `/tournament-close` | `[Admin] /tournament-close` | Close main bracket registrations. |
| `/tournament-open-subs` | `[Admin] /tournament-open-subs` | Enable the substitute sign-up section for standby players. |
| `/tournament-close-subs` | `[Admin] /tournament-close-subs` | Disable substitute signups. |
| `/tournament-promote-sub` | `[Admin] /tournament-promote-sub [substitute:<user>] [replace:<user>]` | Swap a no-show player with a standby substitute or promote the next sub in queue into an open slot. |
| `/tournament-set-limit` | `[Admin] /tournament-set-limit limit:<number>` | Adjust the maximum participant limit counter (e.g. 8, 16, 32, 64). |
| `/tournament-set-regions`| `[Admin] /tournament-set-regions regions:<regions>` | Update the allowed regions filter (e.g. `GLOBAL`, `NA`, or `NA, EU`). |
| `/tournament-clear` | `[Admin] /tournament-clear` | Wipe both main roster and substitute list for a fresh event. |

---

## 📁 Project Architecture

```
ido-bot/
├── cogs/
│   └── tournaments.py        # Slash command cog, UI interactions, and permission checks
├── services/
│   └── tournament_service.py # Pure domain logic: registrations, region validation, substitutions
├── utils/
│   ├── storage.py            # Atomic JSON writes, crash recovery, and backup management
│   └── ui.py                 # Discord Embed and ASCII progress bar formatters
├── tests/
│   ├── test_storage.py       # Atomic writes and backup recovery unit tests
│   ├── test_tournament_service.py # Core registration, capacity, region, and sub queue tests
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

### Discord Bot Portal Permissions
When creating your bot in the [Discord Developer Portal](https://discord.com/developers/applications):
1. **Privileged Gateway Intents**: Enable **Server Members Intent** (`intents.members`).
2. **OAuth2 URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History`, `Use Slash Commands`.

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

The bot includes persistent volume mounts to preserve your tournament state and backups across restarts and container rebuilds.

```bash
# Build and start container in detached mode
docker compose up -d --build

# View container logs
docker compose logs -f

# Stop container
docker compose down
```

---

## ☁️ 24/7 Cloud Deployment on Koyeb

[Koyeb](https://www.koyeb.com/) provides seamless container hosting with automatic restarts:

1. **Push Code to GitHub**:
   Push your bot repository to GitHub (ensure `.env` is **not** committed; it is ignored by default).
2. **Create New Service on Koyeb**:
   - Go to the Koyeb Control Panel and click **Create Service**.
   - Choose **GitHub** as the deployment source and select your `ido-bot` repository.
   - Choose **Worker** (or Web Service without exposed port, since Discord bots connect outbound to Discord Gateway).
3. **Attach Persistent Storage**:
   - In the **Volumes** section, create and attach a persistent volume:
     - Mount path: `/app/data`
     - Size: `1 GB` (plenty for JSON data and hundreds of backups).
4. **Environment Variables**:
   - Under **Environment Variables**, add:
     - `DISCORD_TOKEN`: `your_bot_token_here`
     - `DATA_DIR`: `/app/data`
     - `MAX_BACKUPS`: `20`
     - `ADMIN_ROLE_NAME`: `Tournament Admin`
     - `ORGANIZATION_NAME`: `IDO`
5. **Deploy**:
   - Click **Deploy**. Koyeb will automatically build the `Dockerfile`, mount the persistent `/app/data` volume, and keep the bot running 24/7.
