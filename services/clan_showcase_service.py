"""
Clan Showcase Service
Handles clan profile submission parsing, embed formatting, persistence,
and approval/rejection lifecycle management.
"""

from __future__ import annotations

import io
import logging
import re
import struct
import urllib.request
import uuid
import zlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import discord

from config import config
from utils.storage import StorageManager

logger = logging.getLogger("uda_bot.clan_showcase")

DEFAULT_CLAN_COLOR = 0x10B981  # Official UDA Emerald Green (#10b981)

# Named color mapping for easy English names (e.g. "red", "gold", "blue")
NAMED_CLAN_COLORS: Dict[str, Tuple[str, int]] = {
    "emerald": ("#10b981", 0x10B981),
    "green": ("#10b981", 0x10B981),
    "gold": ("#d4af37", 0xD4AF37),
    "yellow": ("#f1c40f", 0xF1C40F),
    "red": ("#e74c3c", 0xE74C3C),
    "crimson": ("#e74c3c", 0xE74C3C),
    "blue": ("#3498db", 0x3498DB),
    "sapphire": ("#3498db", 0x3498DB),
    "purple": ("#9b59b6", 0x9B59B6),
    "orange": ("#e67e22", 0xE67E22),
    "cyan": ("#00e5ff", 0x00E5FF),
    "aqua": ("#00e5ff", 0x00E5FF),
    "teal": ("#1abc9c", 0x1ABC9C),
    "black": ("#2c3e50", 0x2C3E50),
    "dark": ("#2c3e50", 0x2C3E50),
    "onyx": ("#2c3e50", 0x2C3E50),
    "white": ("#ecf0f1", 0xECF0F1),
    "silver": ("#bdc3c7", 0xBDC3C7),
}


def fetch_image_bytes(url: str, timeout: float = 6.0, max_bytes: int = 5 * 1024 * 1024) -> Optional[bytes]:
    """Downloads image bytes from a URL with browser headers and redirects handling."""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return None
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(max_bytes)
    except Exception as exc:
        logger.debug("Failed to fetch image bytes from %s: %s", url, exc)
        return None


def extract_dominant_color_from_bytes(data: bytes) -> Optional[Tuple[str, int]]:
    """
    Extracts the dominant vibrant (non-neutral) color from image bytes (PNG, JPEG, WebP, GIF, etc.).
    Returns: (hex_str, color_int) or None if unparseable/neutral.
    """
    if not data or len(data) < 30:
        return None

    try:
        from PIL import Image

        im = Image.open(io.BytesIO(data))
        im = im.convert("RGBA")
        im.thumbnail((120, 120))

        raw = im.tobytes()
        candidates = []
        for i in range(0, len(raw), 4):
            r, g, b, a = raw[i:i+4]
            if a < 100:
                continue
            max_c = max(r, g, b)
            min_c = min(r, g, b)
            diff = max_c - min_c
            # Filter out grayscale/neutral pixels
            if diff < 20:
                continue
            # Filter out near-pure blacks and near-pure whites
            if max_c < 30 or min_c > 240:
                continue
            candidates.append((r, g, b))

        if not candidates:
            # Fallback for monochromatic / grayscale logos
            for i in range(0, len(raw), 4):
                r, g, b, a = raw[i:i+4]
                if a >= 100 and 30 <= r <= 235:
                    candidates.append((r, g, b))

        if not candidates:
            return None

        # Group colors into 16-step buckets to cluster similar shades
        buckets: Dict[Tuple[int, int, int], int] = {}
        for r, g, b in candidates:
            key = ((r // 16) * 16, (g // 16) * 16, (b // 16) * 16)
            buckets[key] = buckets.get(key, 0) + 1

        best_bucket = max(buckets.items(), key=lambda item: item[1])[0]
        in_bucket = [
            c for c in candidates
            if (c[0] // 16) * 16 == best_bucket[0]
            and (c[1] // 16) * 16 == best_bucket[1]
            and (c[2] // 16) * 16 == best_bucket[2]
        ]
        avg_r = sum(c[0] for c in in_bucket) // len(in_bucket)
        avg_g = sum(c[1] for c in in_bucket) // len(in_bucket)
        avg_b = sum(c[2] for c in in_bucket) // len(in_bucket)

        hex_str = f"#{avg_r:02x}{avg_g:02x}{avg_b:02x}"
        color_int = (avg_r << 16) + (avg_g << 8) + avg_b
        return hex_str, color_int
    except Exception as exc:
        logger.debug("Could not extract dominant color from image bytes: %s", exc)
        return None


def parse_name_and_color(raw_str: str, override_color: Optional[str] = None) -> Tuple[str, int, str]:
    """
    Parses a clan name string with optional color override or embedded '| #hex' or color name.
    Supports:
    1. override_color passed directly from dropdown (e.g. '#3498db', 'auto', or 'red')
    2. 'Clan Name | #hex' or 'Clan Name | red'
    3. Plain 'Clan Name' (defaults to DEFAULT_CLAN_COLOR)
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

    # Override takes precedence if provided and valid
    target_candidate = override_color.strip() if override_color else color_candidate

    hex_str = "#10b981"
    color_int = DEFAULT_CLAN_COLOR

    if target_candidate:
        cand_lower = target_candidate.lower().strip()
        # Check named colors (e.g. 'gold', 'red', 'blue')
        if cand_lower in NAMED_CLAN_COLORS:
            hex_str, color_int = NAMED_CLAN_COLORS[cand_lower]
        else:
            clean_hex = re.sub(r"[^0-9a-fA-F]", "", target_candidate)
            if len(clean_hex) == 6:
                try:
                    color_int = int(clean_hex, 16)
                    hex_str = f"#{clean_hex.lower()}"
                except ValueError:
                    color_int = DEFAULT_CLAN_COLOR
                    hex_str = "#10b981"

    return name or "Unnamed Clan", color_int, hex_str


DISCORD_MESSAGE_LINK_REGEX = re.compile(
    r"^https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)/?$",
    re.IGNORECASE,
)


def validate_image_url(url: str) -> Tuple[bool, str]:
    """
    Validates that a URL is a valid web link.
    Accepts HTTP/HTTPS image links, Discord CDN, Imgur, Tenor, Giphy, etc.
    """
    stripped = url.strip()
    if not stripped:
        return False, "Logo/Banner URL cannot be empty."
    if not (stripped.startswith("http://") or stripped.startswith("https://")):
        return False, "Logo/Banner URL must start with `http://` or `https://`."
    if " " in stripped:
        return False, "Logo/Banner URL cannot contain spaces."
    return True, ""


async def resolve_image_url(
    bot_client: Optional[discord.Client],
    raw_url: str,
) -> Tuple[bool, str, str]:
    """
    Validates and resolves an image URL.
    Supports:
    1. Direct HTTP/HTTPS URLs (PNG, JPG, JPEG, WEBP, GIF, Imgur, Discord CDN).
    2. Discord message links (e.g. https://discord.com/channels/.../.../...) -
       fetches the referenced message and extracts the image attachment or embed URL.
    Returns: (is_valid, resolved_url, error_message)
    """
    stripped = raw_url.strip()
    if not stripped:
        return False, "", "Logo/Banner URL cannot be empty."

    # Check for Discord message link (common when mobile users tap 'Copy Link' on chat images)
    match = DISCORD_MESSAGE_LINK_REGEX.match(stripped)
    if match and bot_client:
        _guild_id = int(match.group(1))
        channel_id = int(match.group(2))
        message_id = int(match.group(3))
        try:
            channel = bot_client.get_channel(channel_id)
            if not channel:
                channel = await bot_client.fetch_channel(channel_id)
            if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
                target_msg = await channel.fetch_message(message_id)
                # Check message attachments for photo/GIF
                for att in target_msg.attachments:
                    content_type = att.content_type or ""
                    filename = att.filename.lower()
                    if content_type.startswith("image/") or any(
                        filename.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")
                    ):
                        return True, att.url, ""
                # Check embeds for image or thumbnail
                for emb in target_msg.embeds:
                    if emb.image and emb.image.url:
                        return True, emb.image.url, ""
                    if emb.thumbnail and emb.thumbnail.url:
                        return True, emb.thumbnail.url, ""
                return (
                    False,
                    stripped,
                    "The linked Discord message does not contain any image or GIF attachments.",
                )
        except Exception as exc:
            logger.warning("Failed to resolve image from message link '%s': %s", stripped, exc)
            return (
                False,
                stripped,
                f"Could not access the linked Discord message: {exc}",
            )

    # Standard URL validation
    is_valid, err = validate_image_url(stripped)
    if not is_valid:
        return False, stripped, err

    return True, stripped, ""


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
            color_hex=str(data.get("color_hex", "#10b981")),
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
        self._drafts: Dict[Tuple[int, int], Dict[str, str]] = {}
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

    def save_draft(self, guild_id: int, user_id: int, data: Dict[str, str]) -> None:
        """Saves a user's unconfirmed draft."""
        self._drafts[(guild_id, user_id)] = data

    def get_draft(self, guild_id: int, user_id: int) -> Optional[Dict[str, str]]:
        """Retrieves a user's unconfirmed draft if one exists."""
        return self._drafts.get((guild_id, user_id))

    def clear_draft(self, guild_id: int, user_id: int) -> None:
        """Clears a user's unconfirmed draft."""
        self._drafts.pop((guild_id, user_id), None)

    def get_applicant_pending_submission(
        self, guild_id: int, applicant_id: int
    ) -> Optional[ClanSubmission]:
        """Returns any active pending submission by an applicant in a guild."""
        for sub in self._submissions.values():
            if sub.guild_id == guild_id and sub.applicant_id == applicant_id and sub.status == "pending":
                return sub
        return None

    def get_applicant_submission(
        self, guild_id: int, applicant_id: int
    ) -> Optional[ClanSubmission]:
        """Returns the most recent submission by an applicant in a guild."""
        subs = [
            s for s in self._submissions.values()
            if s.guild_id == guild_id and s.applicant_id == applicant_id
        ]
        if not subs:
            return None
        subs.sort(key=lambda s: s.created_at, reverse=True)
        return subs[0]
