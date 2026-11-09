"""
State Snapshot Service
Handles saving, restoring, and auto-discovering configured Discord channels,
roles, and panel message bindings across bot deployments and container restarts.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import discord

from config import config

logger = logging.getLogger("uda_bot.state_snapshot")

DEFAULT_STATE_FILE = "saved_state.json"


@dataclass
class ChannelStateSnapshot:
    guild_id: int = 0
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Tournament channels & roles
    announcement_channel_id: Optional[int] = None
    registration_channel_id: Optional[int] = None
    checkin_channel_id: Optional[int] = None
    subs_channel_id: Optional[int] = None
    admin_role_id: Optional[int] = None
    admin_role_name: Optional[str] = None
    participant_role_id: Optional[int] = None
    participant_role_name: Optional[str] = None
    event_role_id: Optional[int] = None
    event_role_name: Optional[str] = None
    registration_message_id: Optional[int] = None
    subs_message_id: Optional[int] = None

    # Clan Showcase channels & roles
    showcase_channel_id: Optional[int] = None
    staff_review_channel_id: Optional[int] = None
    clan_role_channel_id: Optional[int] = None
    clan_role_message_id: Optional[int] = None
    clanless_role_id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChannelStateSnapshot:
        # Support nested structure if present, or flat
        t_data = data.get("tournament", {})
        c_data = data.get("clan_showcase", {})
        return cls(
            guild_id=int(data.get("guild_id", 0)),
            updated_at=str(data.get("updated_at", datetime.now(timezone.utc).isoformat())),
            announcement_channel_id=t_data.get("announcement_channel_id") or data.get("announcement_channel_id"),
            registration_channel_id=t_data.get("registration_channel_id") or data.get("registration_channel_id"),
            checkin_channel_id=t_data.get("checkin_channel_id") or data.get("checkin_channel_id"),
            subs_channel_id=t_data.get("subs_channel_id") or data.get("subs_channel_id"),
            admin_role_id=t_data.get("admin_role_id") or data.get("admin_role_id"),
            admin_role_name=t_data.get("admin_role_name") or data.get("admin_role_name"),
            participant_role_id=t_data.get("participant_role_id") or data.get("participant_role_id"),
            participant_role_name=t_data.get("participant_role_name") or data.get("participant_role_name"),
            event_role_id=t_data.get("event_role_id") or data.get("event_role_id"),
            event_role_name=t_data.get("event_role_name") or data.get("event_role_name"),
            registration_message_id=t_data.get("registration_message_id") or data.get("registration_message_id"),
            subs_message_id=t_data.get("subs_message_id") or data.get("subs_message_id"),
            showcase_channel_id=c_data.get("showcase_channel_id") or data.get("showcase_channel_id"),
            staff_review_channel_id=c_data.get("staff_review_channel_id") or data.get("staff_review_channel_id"),
            clan_role_channel_id=c_data.get("clan_role_channel_id") or data.get("clan_role_channel_id"),
            clan_role_message_id=c_data.get("clan_role_message_id") or data.get("clan_role_message_id"),
            clanless_role_id=c_data.get("clanless_role_id") or data.get("clanless_role_id"),
        )


class StateSnapshotService:
    """Manages channel and role snapshots to survive git pushes and ephemeral container restarts."""

    def __init__(self, file_path: Path | str = DEFAULT_STATE_FILE):
        self.file_path = Path(file_path)

    def capture_snapshot(
        self,
        guild_id: int,
        tournament_service: Any,
        clan_showcase_service: Any,
    ) -> ChannelStateSnapshot:
        """Reads currently active configurations from tournament and clan showcase services."""
        t_state = tournament_service.get_state(guild_id)
        showcase_ch, review_ch = clan_showcase_service.get_guild_channels(guild_id)
        role_panel_ch, role_panel_msg = clan_showcase_service.get_clan_role_panel_info(guild_id)
        clanless_id = clan_showcase_service.get_clanless_role_id(guild_id)

        snapshot = ChannelStateSnapshot(
            guild_id=guild_id,
            updated_at=datetime.now(timezone.utc).isoformat(),
            announcement_channel_id=t_state.announcement_channel_id,
            registration_channel_id=t_state.registration_channel_id,
            checkin_channel_id=t_state.checkin_channel_id,
            subs_channel_id=t_state.subs_channel_id,
            admin_role_id=t_state.admin_role_id,
            admin_role_name=t_state.admin_role_name,
            participant_role_id=t_state.participant_role_id,
            participant_role_name=t_state.participant_role_name,
            event_role_id=getattr(t_state, "event_role_id", None),
            event_role_name=getattr(t_state, "event_role_name", None),
            registration_message_id=t_state.registration_message_id,
            subs_message_id=t_state.subs_message_id,
            showcase_channel_id=showcase_ch,
            staff_review_channel_id=review_ch,
            clan_role_channel_id=role_panel_ch,
            clan_role_message_id=role_panel_msg,
            clanless_role_id=clanless_id,
        )
        return snapshot

    def save_snapshot(
        self,
        guild_id: int,
        tournament_service: Any,
        clan_showcase_service: Any,
        file_path: Path | str | None = None,
    ) -> dict[str, Any]:
        """Captures active state and writes it to JSON."""
        target_path = Path(file_path) if file_path else self.file_path
        snapshot = self.capture_snapshot(guild_id, tournament_service, clan_showcase_service)

        data = {
            "guild_id": snapshot.guild_id,
            "updated_at": snapshot.updated_at,
            "tournament": {
                "announcement_channel_id": snapshot.announcement_channel_id,
                "registration_channel_id": snapshot.registration_channel_id,
                "checkin_channel_id": snapshot.checkin_channel_id,
                "subs_channel_id": snapshot.subs_channel_id,
                "admin_role_id": snapshot.admin_role_id,
                "admin_role_name": snapshot.admin_role_name,
                "participant_role_id": snapshot.participant_role_id,
                "participant_role_name": snapshot.participant_role_name,
                "event_role_id": snapshot.event_role_id,
                "event_role_name": snapshot.event_role_name,
                "registration_message_id": snapshot.registration_message_id,
                "subs_message_id": snapshot.subs_message_id,
            },
            "clan_showcase": {
                "showcase_channel_id": snapshot.showcase_channel_id,
                "staff_review_channel_id": snapshot.staff_review_channel_id,
                "clan_role_channel_id": snapshot.clan_role_channel_id,
                "clan_role_message_id": snapshot.clan_role_message_id,
                "clanless_role_id": snapshot.clanless_role_id,
            },
        }

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info("Saved channel state snapshot to %s for guild %d", target_path, guild_id)
        return data

    def load_snapshot(self, file_path: Path | str | None = None) -> ChannelStateSnapshot:
        """Reads snapshot from JSON."""
        target_path = Path(file_path) if file_path else self.file_path
        if not target_path.exists():
            raise FileNotFoundError(f"State file not found: {target_path}")

        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return ChannelStateSnapshot.from_dict(data)

    def restore_snapshot(
        self,
        guild_id: int,
        tournament_service: Any,
        clan_showcase_service: Any,
        snapshot: ChannelStateSnapshot | None = None,
        file_path: Path | str | None = None,
        guild: Optional[discord.Guild] = None,
    ) -> ChannelStateSnapshot:
        """Applies snapshot parameters back into tournament and clan showcase services."""
        if snapshot is None:
            snapshot = self.load_snapshot(file_path=file_path)

        t_state = tournament_service.get_state(guild_id)
        if snapshot.announcement_channel_id is not None:
            t_state.announcement_channel_id = snapshot.announcement_channel_id
        if snapshot.registration_channel_id is not None:
            t_state.registration_channel_id = snapshot.registration_channel_id
        if snapshot.checkin_channel_id is not None:
            t_state.checkin_channel_id = snapshot.checkin_channel_id
        if snapshot.subs_channel_id is not None:
            t_state.subs_channel_id = snapshot.subs_channel_id
        if snapshot.admin_role_id is not None:
            t_state.admin_role_id = snapshot.admin_role_id
        if snapshot.admin_role_name is not None:
            t_state.admin_role_name = snapshot.admin_role_name
        if snapshot.participant_role_id is not None:
            t_state.participant_role_id = snapshot.participant_role_id
        if snapshot.participant_role_name is not None:
            t_state.participant_role_name = snapshot.participant_role_name
        if snapshot.event_role_id is not None:
            setattr(t_state, "event_role_id", snapshot.event_role_id)
        if snapshot.event_role_name is not None:
            setattr(t_state, "event_role_name", snapshot.event_role_name)
        if snapshot.registration_message_id is not None:
            t_state.registration_message_id = snapshot.registration_message_id
        if snapshot.subs_message_id is not None:
            t_state.subs_message_id = snapshot.subs_message_id

        tournament_service._persist(guild_id)

        # Clan Showcase restoration
        showcase_ch = snapshot.showcase_channel_id
        review_ch = snapshot.staff_review_channel_id
        if showcase_ch is not None or review_ch is not None:
            clan_showcase_service.set_guild_channels(guild_id, showcase_ch, review_ch)

        if snapshot.clan_role_channel_id is not None and snapshot.clan_role_message_id is not None:
            clan_showcase_service.set_clan_role_panel_info(
                guild_id, snapshot.clan_role_channel_id, snapshot.clan_role_message_id
            )
        if snapshot.clanless_role_id is not None:
            clan_showcase_service.set_clanless_role_id(guild_id, snapshot.clanless_role_id)

        # If any channels are still missing and guild is provided, auto-discover them
        if guild:
            discovered = self.auto_discover_channels(guild, tournament_service, clan_showcase_service)
            if discovered:
                # Update snapshot with discovered values
                snapshot = self.capture_snapshot(guild_id, tournament_service, clan_showcase_service)
                try:
                    self.save_snapshot(guild_id, tournament_service, clan_showcase_service)
                except Exception:
                    pass

        logger.info("Restored channel state snapshot for guild %d", guild_id)
        return snapshot

    def auto_discover_channels(
        self,
        guild: discord.Guild,
        tournament_service: Any,
        clan_showcase_service: Any,
    ) -> dict[str, int]:
        """
        Scans guild channels against recognized regex patterns to automatically discover
        unbound channels when no snapshot exists or when channels were created manually.
        Returns a mapping of found role keys to channel IDs.
        """
        discovered: dict[str, int] = {}
        t_state = tournament_service.get_state(guild.id)
        showcase_ch, review_ch = clan_showcase_service.get_guild_channels(guild.id)

        patterns = {
            "registration": re.compile(r"(?=.*(?:reg|registration|entry|bracket))(?!.*clan)", re.IGNORECASE),
            "announcements": re.compile(r"announce|announcements", re.IGNORECASE),
            "checkin": re.compile(r"checkin|check-in", re.IGNORECASE),
            "subs": re.compile(r"subs|substitute|bench", re.IGNORECASE),
            "showcase": re.compile(r"clan.*reg|reg.*clan|clan.*showcase|showcase.*clan|clan-profile", re.IGNORECASE),
            "staff_review": re.compile(r"clan-review|staff-review|clan-approval|review", re.IGNORECASE),
            "clan_role": re.compile(r"clan-roles|claim.*clan|clan-directory|official.*clan", re.IGNORECASE),
        }

        for ch in getattr(guild, "text_channels", []):
            clean_name = ch.name.lower()

            if t_state.registration_channel_id is None and patterns["registration"].search(clean_name):
                t_state.registration_channel_id = ch.id
                discovered["registration"] = ch.id
            elif t_state.announcement_channel_id is None and patterns["announcements"].search(clean_name):
                t_state.announcement_channel_id = ch.id
                discovered["announcements"] = ch.id
            elif t_state.checkin_channel_id is None and patterns["checkin"].search(clean_name):
                t_state.checkin_channel_id = ch.id
                discovered["checkin"] = ch.id
            elif t_state.subs_channel_id is None and patterns["subs"].search(clean_name):
                t_state.subs_channel_id = ch.id
                discovered["subs"] = ch.id

            if showcase_ch is None and patterns["showcase"].search(clean_name):
                showcase_ch = ch.id
                discovered["showcase"] = ch.id
            if review_ch is None and patterns["staff_review"].search(clean_name):
                review_ch = ch.id
                discovered["staff_review"] = ch.id

            role_panel_ch, _ = clan_showcase_service.get_clan_role_panel_info(guild.id)
            if role_panel_ch is None and patterns["clan_role"].search(clean_name):
                clan_showcase_service.set_clan_role_panel_info(guild.id, ch.id, 0)
                discovered["clan_role"] = ch.id

        # Auto-discover roles if unconfigured
        for r in getattr(guild, "roles", []):
            r_name = r.name.lower().strip()
            if t_state.admin_role_id is None and ("tournament admin" in r_name or r_name == "admin"):
                t_state.admin_role_id = r.id
                t_state.admin_role_name = r.name
                discovered["admin_role"] = r.id
            if t_state.participant_role_id is None and "participant" in r_name:
                t_state.participant_role_id = r.id
                t_state.participant_role_name = r.name
                discovered["participant_role"] = r.id
            if clan_showcase_service.get_clanless_role_id(guild.id) is None and "clanless" in r_name:
                clan_showcase_service.set_clanless_role_id(guild.id, r.id)
                discovered["clanless_role"] = r.id

        if discovered:
            tournament_service._persist(guild.id)
            clan_showcase_service.set_guild_channels(guild.id, showcase_ch, review_ch)
            logger.info("Auto-discovered %d channels/roles for guild %d: %s", len(discovered), guild.id, discovered)

        return discovered

        if discovered:
            tournament_service._persist(guild.id)
            clan_showcase_service.set_guild_channels(guild.id, showcase_ch, review_ch)
            logger.info("Auto-discovered %d channels for guild %d: %s", len(discovered), guild.id, discovered)

        return discovered
