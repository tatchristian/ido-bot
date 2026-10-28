"""
Clan Showcase Service
Handles clan profile submission parsing, embed formatting, persistence,
and approval/rejection lifecycle management.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import discord

from config import config
from utils.storage import StorageManager

logger = logging.getLogger("ido_bot.clan_showcase")

DEFAULT_CLAN_COLOR = 0x38BDF8  # Default Sky Blue (#38bdf8)


def parse_name_and_color(raw_str: str) -> Tuple[str, int, str]:
    """
    Parses a string formatted like 'Clan Name | #38bdf8' or 'Clan Name'
    into (clan_name, color_int, hex_str).
    Falls back to DEFAULT_CLAN_COLOR (0x38bdf8) if color is omitted or invalid.
    """
    cleaned = raw_str.strip()
    if "|" in cleaned:
        parts = cleaned.split("|", 1)
        name = parts[0].strip()
        color_candidate = parts[1].strip()
    elif "," in cleaned and ("#" in cleaned or len(cleaned.split(",")[-1].strip()) == 6):
        parts = cleaned.rsplit(",", 1)
        name = parts[0].strip()
        color_candidate = parts[1].strip()
    else:
        name = cleaned
        color_candidate = ""

    # Parse hex color
    hex_str = "#38bdf8"
    color_int = DEFAULT_CLAN_COLOR

    if color_candidate:
        clean_hex = re.sub(r"[^0-9a-fA-F]", "", color_candidate)
        if len(clean_hex) == 6:
            try:
                color_int = int(clean_hex, 16)
                hex_str = f"#{clean_hex.lower()}"
            except ValueError:
                color_int = DEFAULT_CLAN_COLOR
                hex_str = "#38bdf8"

    return name or "Unnamed Clan", color_int, hex_str


def validate_image_url(url: str) -> Tuple[bool, str]:
    """
    Validates that a URL is a valid web link.
    """
    stripped = url.strip()
    if not (stripped.startswith("http://") or stripped.startswith("https://")):
        return False, "Logo/Banner URL must start with `http://` or `https://`."
    if " " in stripped:
        return False, "Logo/Banner URL cannot contain spaces."
    return True, ""


def build_clan_showcase_embed(
    clan_name: str,
    color_int: int,
    metadata_text: str,
    description_text: str,
    activities_motto_text: str,
    logo_url: str,
) -> discord.Embed:
    """
    Constructs the official Clan Showcase embed matching the exact hierarchy:
    - Author: Name = Clan Name, Icon URL = logo_url
    - Color: Hex color
    - Description:
        {metadata}

        Description:
        {description}

        Main Activities:
        {activities_motto}
    - Image: logo_url (large emblem below text)
    """
    embed = discord.Embed(
        color=color_int,
    )
    # 1. Author header
    embed.set_author(name=clan_name, icon_url=logo_url)

    # 2. Unified description markdown block
    desc_clean = description_text.strip()
    if not desc_clean.lower().startswith("description:"):
        desc_clean = f"Description:\n{desc_clean}"

    activities_clean = activities_motto_text.strip()
    if not activities_clean.lower().startswith("main activities:"):
        activities_clean = f"Main Activities:\n{activities_clean}"

    desc_blocks = [
        metadata_text.strip(),
        "",
        desc_clean,
        "",
        activities_clean,
    ]
    embed.description = "\n".join(desc_blocks)

    # 3. Main emblem image (large artwork below text)
    embed.set_image(url=logo_url)

    # 4. Standard footer
    embed.set_footer(text=f"{config.organization_name} • Official Clan Showcase")
    embed.timestamp = datetime.now(timezone.utc)

    return embed


@dataclass
class ClanSubmission:
    id: str
    guild_id: int
    applicant_id: int
    applicant_name: str
    clan_name: str
    color_hex: str
    color_int: int
    metadata_text: str
    description_text: str
    activities_motto: str
    logo_url: str
    status: str = "pending"  # "pending", "approved", "rejected"
    staff_message_id: Optional[int] = None
    showcase_message_id: Optional[int] = None
    reviewed_by_id: Optional[int] = None
    reviewed_by_name: Optional[str] = None
    reject_reason: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ClanSubmission:
        return cls(
            id=str(data.get("id", str(uuid.uuid4()))),
            guild_id=int(data.get("guild_id", 0)),
            applicant_id=int(data.get("applicant_id", 0)),
            applicant_name=str(data.get("applicant_name", "Unknown")),
            clan_name=str(data.get("clan_name", "Unnamed Clan")),
            color_hex=str(data.get("color_hex", "#38bdf8")),
            color_int=int(data.get("color_int", DEFAULT_CLAN_COLOR)),
            metadata_text=str(data.get("metadata_text", "")),
            description_text=str(data.get("description_text", "")),
            activities_motto=str(data.get("activities_motto", "")),
            logo_url=str(data.get("logo_url", "")),
            status=str(data.get("status", "pending")),
            staff_message_id=int(data["staff_message_id"]) if data.get("staff_message_id") else None,
            showcase_message_id=int(data["showcase_message_id"]) if data.get("showcase_message_id") else None,
            reviewed_by_id=int(data["reviewed_by_id"]) if data.get("reviewed_by_id") else None,
            reviewed_by_name=str(data["reviewed_by_name"]) if data.get("reviewed_by_name") else None,
            reject_reason=str(data["reject_reason"]) if data.get("reject_reason") else None,
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            updated_at=str(data.get("updated_at", datetime.now(timezone.utc).isoformat())),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_embed(self) -> discord.Embed:
        return build_clan_showcase_embed(
            clan_name=self.clan_name,
            color_int=self.color_int,
            metadata_text=self.metadata_text,
            description_text=self.description_text,
            activities_motto_text=self.activities_motto,
            logo_url=self.logo_url,
        )


class ClanShowcaseService:
    """
    Persistent management for clan submissions and guild channel routing.
    """
    def __init__(
        self,
        storage: Optional[StorageManager] = None,
        data_dir: Optional[Path] = None,
    ):
        self.data_dir = Path(data_dir or config.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage = storage or StorageManager(
            file_path=self.data_dir / "clan_submissions.json",
            backup_dir=self.data_dir / "backups",
            max_backups=config.max_backups,
        )
        self._guild_channels: Dict[int, Dict[str, int]] = {}
        self._submissions: Dict[str, ClanSubmission] = {}
        self._message_to_sub_id: Dict[int, str] = {}
        self._load()

    def _load(self):
        data = self.storage.load(default_factory=lambda: {"guild_channels": {}, "submissions": []})
        self._guild_channels = {
            int(k): v for k, v in data.get("guild_channels", {}).items()
        }
        for sub_dict in data.get("submissions", []):
            sub = ClanSubmission.from_dict(sub_dict)
            self._submissions[sub.id] = sub
            if sub.staff_message_id:
                self._message_to_sub_id[sub.staff_message_id] = sub.id

    def _persist(self):
        payload = {
            "guild_channels": {str(k): v for k, v in self._guild_channels.items()},
            "submissions": [sub.to_dict() for sub in self._submissions.values()],
        }
        self.storage.save(payload)

    def set_guild_channels(
        self,
        guild_id: int,
        showcase_channel_id: Optional[int] = None,
        staff_review_channel_id: Optional[int] = None,
    ) -> str:
        """Configures or updates target channels for a guild."""
        gdata = self._guild_channels.setdefault(guild_id, {})
        if showcase_channel_id is not None:
            gdata["showcase_channel_id"] = showcase_channel_id
        if staff_review_channel_id is not None:
            gdata["staff_review_channel_id"] = staff_review_channel_id
        self._persist()
        return "📁 Clan showcase channels successfully updated."

    def get_guild_channels(self, guild_id: int) -> Tuple[Optional[int], Optional[int]]:
        """Returns (showcase_channel_id, staff_review_channel_id) for the guild."""
        gdata = self._guild_channels.get(guild_id, {})
        showcase = gdata.get("showcase_channel_id") or config.showcase_channel_id
        review = gdata.get("staff_review_channel_id") or config.staff_review_channel_id
        return showcase, review

    def create_submission(
        self,
        guild_id: int,
        applicant_id: int,
        applicant_name: str,
        clan_name_color_raw: str,
        metadata_text: str,
        description_text: str,
        activities_motto: str,
        logo_url: str,
    ) -> ClanSubmission:
        clan_name, color_int, color_hex = parse_name_and_color(clan_name_color_raw)
        sub_id = str(uuid.uuid4())[:8]

        sub = ClanSubmission(
            id=sub_id,
            guild_id=guild_id,
            applicant_id=applicant_id,
            applicant_name=applicant_name,
            clan_name=clan_name,
            color_hex=color_hex,
            color_int=color_int,
            metadata_text=metadata_text.strip(),
            description_text=description_text.strip(),
            activities_motto=activities_motto.strip(),
            logo_url=logo_url.strip(),
        )
        self._submissions[sub.id] = sub
        self._persist()
        return sub

    def link_staff_message(self, sub_id: str, message_id: int):
        sub = self._submissions.get(sub_id)
        if sub:
            sub.staff_message_id = message_id
            sub.updated_at = datetime.now(timezone.utc).isoformat()
            self._message_to_sub_id[message_id] = sub_id
            self._persist()

    def get_submission(self, sub_id: str) -> Optional[ClanSubmission]:
        return self._submissions.get(sub_id)

    def get_submission_by_message_id(self, message_id: int) -> Optional[ClanSubmission]:
        sub_id = self._message_to_sub_id.get(message_id)
        if sub_id:
            return self._submissions.get(sub_id)
        return None

    def approve_submission(
        self,
        sub_id: str,
        reviewed_by_id: int,
        reviewed_by_name: str,
        showcase_message_id: Optional[int] = None,
    ) -> Optional[ClanSubmission]:
        sub = self._submissions.get(sub_id)
        if not sub:
            return None
        sub.status = "approved"
        sub.reviewed_by_id = reviewed_by_id
        sub.reviewed_by_name = reviewed_by_name
        if showcase_message_id:
            sub.showcase_message_id = showcase_message_id
        sub.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist()
        return sub

    def reject_submission(
        self,
        sub_id: str,
        reviewed_by_id: int,
        reviewed_by_name: str,
        reason: str,
    ) -> Optional[ClanSubmission]:
        sub = self._submissions.get(sub_id)
        if not sub:
            return None
        sub.status = "rejected"
        sub.reviewed_by_id = reviewed_by_id
        sub.reviewed_by_name = reviewed_by_name
        sub.reject_reason = reason
        sub.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist()
        return sub

    def get_guild_submissions(self, guild_id: int) -> list[ClanSubmission]:
        """Returns all submissions for a guild."""
        return [s for s in self._submissions.values() if s.guild_id == guild_id]

    def search_submission(self, guild_id: int, query: str) -> Optional[ClanSubmission]:
        """Finds a submission in the guild by ID or clan name."""
        q = query.strip().lower()
        if query in self._submissions:
            sub = self._submissions[query]
            if sub.guild_id == guild_id:
                return sub

        guild_subs = [s for s in self._submissions.values() if s.guild_id == guild_id]
        for s in guild_subs:
            if s.clan_name.lower() == q or s.id.lower() == q:
                return s

        for s in guild_subs:
            if q in s.clan_name.lower() or q in s.id.lower():
                return s

        return None

    def update_submission(
        self,
        sub_id: str,
        clan_name: Optional[str] = None,
        color_hex: Optional[str] = None,
        color_int: Optional[int] = None,
        metadata_text: Optional[str] = None,
        description_text: Optional[str] = None,
        activities_motto: Optional[str] = None,
        logo_url: Optional[str] = None,
    ) -> Optional[ClanSubmission]:
        """Updates fields of an existing submission and saves to disk."""
        sub = self._submissions.get(sub_id)
        if not sub:
            return None
        if clan_name is not None:
            sub.clan_name = clan_name
        if color_hex is not None:
            sub.color_hex = color_hex
        if color_int is not None:
            sub.color_int = color_int
        if metadata_text is not None:
            sub.metadata_text = metadata_text.strip()
        if description_text is not None:
            sub.description_text = description_text.strip()
        if activities_motto is not None:
            sub.activities_motto = activities_motto.strip()
        if logo_url is not None:
            sub.logo_url = logo_url.strip()
        sub.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist()
        return sub
