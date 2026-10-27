"""
Application configuration for the IDO Tournament Discord Bot.
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
    data_dir: Path = Path(os.getenv("DATA_DIR", "data"))
    max_backups: int = int(os.getenv("MAX_BACKUPS", "20"))
    admin_role_name: str = os.getenv("ADMIN_ROLE_NAME", "Tournament Admin")
    organization_name: str = os.getenv("ORGANIZATION_NAME", "IDO")
    embed_color: int = int(os.getenv("EMBED_COLOR", "0xF1C40F"), 16)

    @property
    def tournament_file(self) -> Path:
        return self.data_dir / "tournament.json"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"


config = Config()
