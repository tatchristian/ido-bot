"""
Application configuration for the UDA (United Dueling Amity) Discord Bot.
Loads configuration options from environment variables or .env file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    token: str = os.getenv("DISCORD_TOKEN", "")
    guild_id: int | None = (
        int(os.getenv("GUILD_ID"))
        if os.getenv("GUILD_ID") and os.getenv("GUILD_ID").strip().isdigit()
        else None
    )
    target_guild_id: int | None = (
        int(os.getenv("TARGET_GUILD_ID"))
        if os.getenv("TARGET_GUILD_ID") and os.getenv("TARGET_GUILD_ID").strip().isdigit()
        else None
    )
    admin_role_id: int | None = (
        int(os.getenv("ADMIN_ROLE_ID"))
        if os.getenv("ADMIN_ROLE_ID") and os.getenv("ADMIN_ROLE_ID").strip().isdigit()
        else None
    )
    admin_role_name: str = os.getenv("ADMIN_ROLE_NAME", "Tournament Admin")
    showcase_channel_id: int | None = (
        int(os.getenv("SHOWCASE_CHANNEL_ID"))
        if os.getenv("SHOWCASE_CHANNEL_ID") and os.getenv("SHOWCASE_CHANNEL_ID").strip().isdigit()
        else None
    )
    staff_review_channel_id: int | None = (
        int(os.getenv("STAFF_REVIEW_CHANNEL_ID"))
        if os.getenv("STAFF_REVIEW_CHANNEL_ID") and os.getenv("STAFF_REVIEW_CHANNEL_ID").strip().isdigit()
        else None
    )
    data_dir: Path = Path(os.getenv("DATA_DIR", "data"))
    max_backups: int = int(os.getenv("MAX_BACKUPS", "20"))
    organization_name: str = os.getenv("ORGANIZATION_NAME", "UDA")
    organization_full_name: str = os.getenv("ORGANIZATION_FULL_NAME", "United Dueling Alliances")
    embed_color: int = int(os.getenv("EMBED_COLOR", "0x10B981"), 16)  # Official UDA Emerald Green
    accent_gold: int = 0xD4AF37  # Official UDA Antique Gold
    primary_emerald: int = 0x10B981  # Official UDA Emerald Gemstone
    website_api_url: str = os.getenv("WEBSITE_API_URL", "https://unitedduelingamity.org/api/sync")
    website_api_key: str = os.getenv("WEBSITE_API_KEY", "")

    @property
    def tournament_file(self) -> Path:
        return self.data_dir / "tournament.json"

    @property
    def clan_submissions_file(self) -> Path:
        return self.data_dir / "clan_submissions.json"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"


config = Config()

