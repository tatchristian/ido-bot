"""
Domain service handling tournament business logic, registrations, validations,
check-ins, and roster states with full per-server (multi-guild) isolation.
"""

from __future__ import annotations

import csv
import io
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.storage import StorageManager

logger = logging.getLogger(__name__)

DEFAULT_WEAPONS = [
    "Daggers",
    "Katana",
    "Naginata",
    "Bo Staff",
    "Curved Swords",
    "Warhammer",
    "Kusarigama",
]

DEFAULT_REGIONS = ["GLOBAL"]
STANDARD_REGIONS = ["NA", "EU", "OCE", "ASIA", "SA"]


@dataclass
class Participant:
    user_id: int
    user_mention: str
    ign: str
    weapon: str
    region: str
    checked_in: bool = False
    registered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Participant:
        return cls(
            user_id=int(data["user_id"]),
            user_mention=str(data.get("user_mention", f"<@{data['user_id']}>")),
            ign=str(data.get("ign", "Unknown")),
            weapon=str(data.get("weapon", "Katana")),
            region=str(data.get("region", "GLOBAL")),
            checked_in=bool(data.get("checked_in", False)),
            registered_at=str(
                data.get("registered_at", datetime.now(timezone.utc).isoformat())
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TournamentState:
    name: str = "IDO Championship"
    main_open: bool = False
    subs_open: bool = False
    checkin_open: bool = False
    max_slots: int = 8
    allowed_regions: list[str] = field(default_factory=lambda: ["GLOBAL"])
    approved_weapons: list[str] = field(default_factory=lambda: list(DEFAULT_WEAPONS))
    admin_role_id: int | None = None
    admin_role_name: str | None = None
    participant_role_id: int | None = None
    participant_role_name: str | None = None
    announcement_channel_id: int | None = None
    checkin_channel_id: int | None = None
    subs_channel_id: int | None = None
    participants: list[Participant] = field(default_factory=list)
    substitutes: list[Participant] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TournamentState:
        return cls(
            name=str(data.get("name", "IDO Championship")),
            main_open=bool(data.get("main_open", False)),
            subs_open=bool(data.get("subs_open", False)),
            checkin_open=bool(data.get("checkin_open", False)),
            max_slots=int(data.get("max_slots", 8)),
            allowed_regions=list(data.get("allowed_regions", ["GLOBAL"])),
            approved_weapons=list(data.get("approved_weapons", DEFAULT_WEAPONS)),
            admin_role_id=int(data["admin_role_id"]) if data.get("admin_role_id") is not None else None,
            admin_role_name=str(data["admin_role_name"]) if data.get("admin_role_name") is not None else None,
            participant_role_id=int(data["participant_role_id"]) if data.get("participant_role_id") is not None else None,
            participant_role_name=str(data["participant_role_name"]) if data.get("participant_role_name") is not None else None,
            announcement_channel_id=int(data["announcement_channel_id"]) if data.get("announcement_channel_id") is not None else None,
            checkin_channel_id=int(data["checkin_channel_id"]) if data.get("checkin_channel_id") is not None else None,
            subs_channel_id=int(data["subs_channel_id"]) if data.get("subs_channel_id") is not None else None,
            participants=[
                Participant.from_dict(p) for p in data.get("participants", [])
            ],
            substitutes=[
                Participant.from_dict(s) for s in data.get("substitutes", [])
            ],
            created_at=str(
                data.get("created_at", datetime.now(timezone.utc).isoformat())
            ),
            updated_at=str(
                data.get("updated_at", datetime.now(timezone.utc).isoformat())
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "main_open": self.main_open,
            "subs_open": self.subs_open,
            "checkin_open": self.checkin_open,
            "max_slots": self.max_slots,
            "allowed_regions": self.allowed_regions,
            "approved_weapons": self.approved_weapons,
            "admin_role_id": self.admin_role_id,
            "admin_role_name": self.admin_role_name,
            "participant_role_id": self.participant_role_id,
            "participant_role_name": self.participant_role_name,
            "announcement_channel_id": self.announcement_channel_id,
            "checkin_channel_id": self.checkin_channel_id,
            "subs_channel_id": self.subs_channel_id,
            "participants": [p.to_dict() for p in self.participants],
            "substitutes": [s.to_dict() for s in self.substitutes],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TournamentService:
    """
    Manages tournament operations, enforcing rules for registration, capacity,
    regions, standby promotions, check-in, and tournament day flow.
    Supports isolated per-server tournament rosters (multi-guild support).
    """

    def __init__(
        self,
        storage: StorageManager | None = None,
        data_dir: Path | None = None,
        backup_dir: Path | None = None,
        max_backups: int = 20,
    ):
        self._default_storage = storage
        self.data_dir = Path(
            data_dir or (storage.file_path.parent if storage else "data")
        )
        self.backup_dir = Path(
            backup_dir or (storage.backup_dir if storage else self.data_dir / "backups")
        )
        self.max_backups = max_backups
        self._managers: dict[int, StorageManager] = {}
        self._states: dict[int, TournamentState] = {}
        self._lock = threading.Lock()

    def _get_manager(self, guild_id: int = 0) -> StorageManager:
        if guild_id in self._managers:
            return self._managers[guild_id]

        if guild_id == 0 and self._default_storage is not None:
            manager = self._default_storage
        else:
            file_name = "tournament.json" if guild_id == 0 else f"tournament_{guild_id}.json"
            file_path = self.data_dir / file_name
            backup_dir = self.backup_dir if guild_id == 0 else (self.backup_dir / str(guild_id))
            manager = StorageManager(
                file_path, backup_dir=backup_dir, max_backups=self.max_backups
            )

        self._managers[guild_id] = manager
        return manager

    def get_state(self, guild_id: int = 0) -> TournamentState:
        with self._lock:
            if guild_id not in self._states:
                manager = self._get_manager(guild_id)
                data = manager.load(default_factory=lambda: TournamentState().to_dict())
                try:
                    self._states[guild_id] = TournamentState.from_dict(data)
                except Exception as e:
                    logger.error(
                        "Failed to parse tournament state for guild %s, resetting: %s",
                        guild_id,
                        e,
                    )
                    default = TournamentState()
                    manager.save(default.to_dict())
                    self._states[guild_id] = default

            return self._states[guild_id]

    @property
    def state(self) -> TournamentState:
        """Backward-compatible default state accessor (guild_id=0)."""
        return self.get_state(0)

    def _persist(self, guild_id: int = 0) -> None:
        state = self.get_state(guild_id)
        state.updated_at = datetime.now(timezone.utc).isoformat()
        manager = self._get_manager(guild_id)
        manager.save(state.to_dict())

    # ---------------------------------------------------------
    # Region Validation
    # ---------------------------------------------------------
    def parse_regions(self, regions_input: str | list[str]) -> list[str]:
        """Normalizes comma, space, or list separated regions into a cleaned uppercase list."""
        if isinstance(regions_input, str):
            cleaned = regions_input.replace("/", ",").replace(";", ",")
            raw_tokens = [
                r.strip(" '\"`[](){}").upper()
                for r in cleaned.split(",")
                if r.strip(" '\"`[](){}")
            ]
        else:
            raw_tokens = [
                r.strip(" '\"`[](){}").upper()
                for r in regions_input
                if r.strip(" '\"`[](){}")
            ]

        if not raw_tokens:
            return ["GLOBAL"]

        if any(r == "GLOBAL" for r in raw_tokens):
            return ["GLOBAL"]

        return sorted(list(dict.fromkeys(raw_tokens)))

    def is_region_allowed(self, user_region: str, guild_id: int = 0) -> tuple[bool, str]:
        """
        Validates whether the user's selected region is allowed in this tournament.
        Returns (is_allowed, error_message_if_not).
        """
        state = self.get_state(guild_id)
        cleaned_user = user_region.strip(" '\"`[](){}").upper()

        if "GLOBAL" in state.allowed_regions:
            return True, ""

        allowed_upper = [r.strip(" '\"`[](){}").upper() for r in state.allowed_regions]

        for allowed in allowed_upper:
            if (
                cleaned_user == allowed
                or cleaned_user.startswith(allowed)
                or allowed in cleaned_user
            ):
                return True, ""

        allowed_str = ", ".join(state.allowed_regions)
        return False, f"This tournament is only open to participants from: {allowed_str}"

    # ---------------------------------------------------------
    # Admin Controls: Lifecycle & Configuration
    # ---------------------------------------------------------
    def open_tournament(
        self,
        name: str | None = None,
        slots: int | None = None,
        regions: str | list[str] | None = None,
        open_subs: bool = False,
        participant_role_id: int | None = None,
        participant_role_name: str | None = None,
        announcement_channel_id: int | None = None,
        guild_id: int = 0,
    ) -> str:
        """Opens main bracket submissions and updates tournament settings."""
        state = self.get_state(guild_id)
        if name:
            state.name = name.strip()
        if slots is not None:
            if slots < 2:
                raise ValueError("Tournament slot capacity must be at least 2.")
            state.max_slots = slots
        if regions is not None:
            state.allowed_regions = self.parse_regions(regions)
        if participant_role_id is not None:
            state.participant_role_id = participant_role_id
            state.participant_role_name = participant_role_name
        if announcement_channel_id is not None:
            state.announcement_channel_id = announcement_channel_id

        state.main_open = True
        state.subs_open = open_subs
        self._persist(guild_id)

        sub_status = "OPEN" if state.subs_open else "CLOSED"
        regions_str = ", ".join(state.allowed_regions)
        role_info = f"\n• Participant Role: `@{state.participant_role_name}`" if state.participant_role_name else ""
        return (
            f"🏆 **{state.name}** is now **OPEN**!\n"
            f"• Max Slots: `{state.max_slots}`\n"
            f"• Allowed Regions: `{regions_str}`\n"
            f"• Substitute Signups: `{sub_status}`"
            f"{role_info}"
        )

    def close_tournament(self, guild_id: int = 0) -> str:
        """Closes main bracket registrations."""
        state = self.get_state(guild_id)
        state.main_open = False
        self._persist(guild_id)
        return f"🔒 Main bracket submissions for **{state.name}** are now **CLOSED**."

    def open_subs(self, subs_channel_id: int | None = None, guild_id: int = 0) -> str:
        """Enables substitute signups."""
        state = self.get_state(guild_id)
        state.subs_open = True
        if subs_channel_id is not None:
            state.subs_channel_id = subs_channel_id
        self._persist(guild_id)
        return f"🟢 Substitute signups for **{state.name}** are now **OPEN**."

    def close_subs(self, guild_id: int = 0) -> str:
        """Disables substitute signups."""
        state = self.get_state(guild_id)
        state.subs_open = False
        self._persist(guild_id)
        return f"🔴 Substitute signups for **{state.name}** are now **CLOSED**."

    def set_limit(self, limit: int, guild_id: int = 0) -> str:
        """Updates max capacity for the main bracket."""
        if limit < 2:
            raise ValueError("Participant limit must be at least 2.")
        state = self.get_state(guild_id)
        old_limit = state.max_slots
        state.max_slots = limit
        self._persist(guild_id)
        return f"📊 Tournament slot capacity updated from `{old_limit}` to `{limit}`."

    def set_regions(self, regions: str | list[str], guild_id: int = 0) -> str:
        """Updates allowed regions for the tournament."""
        state = self.get_state(guild_id)
        parsed = self.parse_regions(regions)
        state.allowed_regions = parsed
        self._persist(guild_id)
        return f"🌍 Allowed regions updated to: `{', '.join(parsed)}`."

    def set_approved_weapons(self, weapons_input: str | list[str], guild_id: int = 0) -> str:
        """Updates approved weapons for the tournament."""
        state = self.get_state(guild_id)
        if isinstance(weapons_input, str):
            weapons = [w.strip() for w in weapons_input.split(",") if w.strip()]
        else:
            weapons = [w.strip() for w in weapons_input if w.strip()]

        if not weapons:
            state.approved_weapons = list(DEFAULT_WEAPONS)
        else:
            state.approved_weapons = weapons

        self._persist(guild_id)
        return f"⚔️ Approved weapons updated: {', '.join(state.approved_weapons)}."

    def set_admin_role(self, role_id: int, role_name: str, guild_id: int = 0) -> str:
        """Sets the threshold role required for tournament admin permissions."""
        state = self.get_state(guild_id)
        state.admin_role_id = role_id
        state.admin_role_name = role_name
        self._persist(guild_id)
        return f"🛡️ Tournament Admin threshold set to role: **{role_name}** (or higher)."

    def set_participant_role(
        self, role_id: int | None, role_name: str | None = None, guild_id: int = 0
    ) -> str:
        """Sets or clears the Discord role assigned to main bracket tournament participants."""
        state = self.get_state(guild_id)
        state.participant_role_id = role_id
        state.participant_role_name = role_name
        self._persist(guild_id)
        if role_name:
            return f"🏷️ Tournament participant role set to: **@{role_name}**."
        return "🏷️ Tournament participant role cleared."

    def set_channels(
        self,
        announcement_channel_id: int | None = None,
        checkin_channel_id: int | None = None,
        subs_channel_id: int | None = None,
        guild_id: int = 0,
    ) -> str:
        """Sets dedicated Discord channel IDs for announcements, check-in, and substitutes."""
        state = self.get_state(guild_id)
        if announcement_channel_id is not None:
            state.announcement_channel_id = announcement_channel_id
        if checkin_channel_id is not None:
            state.checkin_channel_id = checkin_channel_id
        if subs_channel_id is not None:
            state.subs_channel_id = subs_channel_id
        self._persist(guild_id)
        return "📁 Tournament dedicated channels updated."

    def clear_channels(self, guild_id: int = 0) -> str:
        """Clears all dedicated channel configurations."""
        state = self.get_state(guild_id)
        state.announcement_channel_id = None
        state.checkin_channel_id = None
        state.subs_channel_id = None
        self._persist(guild_id)
        return "📁 Tournament dedicated channels cleared."

    def clear_tournament(self, guild_id: int = 0) -> str:
        """Wipes both main roster, substitute list, and resets participant role."""
        state = self.get_state(guild_id)
        p_count = len(state.participants)
        s_count = len(state.substitutes)
        state.participants.clear()
        state.substitutes.clear()
        state.checkin_open = False
        state.participant_role_id = None
        state.participant_role_name = None
        self._persist(guild_id)
        return f"🧹 Tournament roster wiped clean ({p_count} main players and {s_count} substitutes removed)."

    # ---------------------------------------------------------
    # Essential Admin Tools (Kick & Force Register)
    # ---------------------------------------------------------
    def kick_user(self, user_id: int, reason: str = "", guild_id: int = 0) -> tuple[bool, str]:
        """Removes a user from either the main bracket or the substitute queue."""
        state = self.get_state(guild_id)
        p_idx = next(
            (i for i, p in enumerate(state.participants) if p.user_id == user_id),
            None,
        )
        if p_idx is not None:
            removed = state.participants.pop(p_idx)
            self._persist(guild_id)
            reason_str = f" Reason: *{reason}*" if reason else ""
            return (
                True,
                f"👢 Removed **{removed.ign}** ({removed.user_mention}) from the **main bracket**.{reason_str}",
            )

        s_idx = next(
            (i for i, s in enumerate(state.substitutes) if s.user_id == user_id),
            None,
        )
        if s_idx is not None:
            removed = state.substitutes.pop(s_idx)
            self._persist(guild_id)
            reason_str = f" Reason: *{reason}*" if reason else ""
            return (
                True,
                f"👢 Removed **{removed.ign}** ({removed.user_mention}) from the **standby substitute queue**.{reason_str}",
            )

        return False, f"User <@{user_id}> was not found in either the main bracket or substitute queue."

    def force_register(
        self,
        user_id: int,
        user_mention: str,
        ign: str,
        weapon: str,
        region: str,
        as_sub: bool = False,
        guild_id: int = 0,
    ) -> tuple[bool, str, Participant]:
        """
        Allows tournament admins to manually slot a player into the main bracket or substitute queue.
        Bypasses standard registration open/closed states.
        """
        state = self.get_state(guild_id)
        state.participants = [p for p in state.participants if p.user_id != user_id]
        state.substitutes = [s for s in state.substitutes if s.user_id != user_id]

        participant = Participant(
            user_id=user_id,
            user_mention=user_mention,
            ign=ign.strip(),
            weapon=weapon.strip(),
            region=region.strip().upper(),
        )

        if as_sub:
            state.substitutes.append(participant)
            queue_pos = len(state.substitutes)
            self._persist(guild_id)
            return (
                True,
                f"👑 Admin force-registered **{participant.ign}** ({participant.user_mention}) into the **substitute queue** at position #{queue_pos}.",
                participant,
            )
        else:
            state.participants.append(participant)
            slots_now = len(state.participants)
            self._persist(guild_id)
            return (
                True,
                f"👑 Admin force-registered **{participant.ign}** ({participant.user_mention}) into the **main bracket** ({slots_now}/{state.max_slots}).",
                participant,
            )

    # ---------------------------------------------------------
    # Participant Registration & Updates
    # ---------------------------------------------------------
    def register_participant(
        self,
        user_id: int,
        user_mention: str,
        ign: str,
        weapon: str,
        region: str,
        guild_id: int = 0,
    ) -> tuple[bool, str, Participant | None]:
        """Signs up a user for the main bracket."""
        state = self.get_state(guild_id)
        if not state.main_open:
            return False, "Main bracket submissions are currently closed.", None

        if any(p.user_id == user_id for p in state.participants):
            return False, "You are already registered in the main bracket.", None

        if any(s.user_id == user_id for s in state.substitutes):
            return (
                False,
                "You are already in the standby substitute queue. Unregister first if you wish to join the main bracket.",
                None,
            )

        if len(state.participants) >= state.max_slots:
            sub_hint = (
                " You can sign up as a standby substitute with `/tournament-sub-register`."
                if state.subs_open
                else ""
            )
            return (
                False,
                f"The main bracket is currently full ({len(state.participants)}/{state.max_slots} registered).{sub_hint}",
                None,
            )

        allowed, err_msg = self.is_region_allowed(region, guild_id=guild_id)
        if not allowed:
            return False, err_msg, None

        participant = Participant(
            user_id=user_id,
            user_mention=user_mention,
            ign=ign.strip(),
            weapon=weapon.strip(),
            region=region.strip().upper(),
        )
        state.participants.append(participant)
        self._persist(guild_id)

        return True, "Successfully registered for the main bracket!", participant

    def unregister_participant(self, user_id: int, guild_id: int = 0) -> tuple[bool, str]:
        """Withdraws a user from the main bracket."""
        state = self.get_state(guild_id)
        idx = next(
            (i for i, p in enumerate(state.participants) if p.user_id == user_id),
            None,
        )
        if idx is None:
            return False, "You are not currently registered in the main bracket."

        removed = state.participants.pop(idx)
        self._persist(guild_id)
        return True, f"Withdrew **{removed.ign}** ({removed.user_mention}) from the main bracket."

    def register_substitute(
        self,
        user_id: int,
        user_mention: str,
        ign: str,
        weapon: str,
        region: str,
        guild_id: int = 0,
    ) -> tuple[bool, str, Participant | None]:
        """Signs up a user for the standby substitute queue."""
        state = self.get_state(guild_id)
        if not state.subs_open:
            return False, "Substitute signups are currently closed.", None

        if any(p.user_id == user_id for p in state.participants):
            return False, "You are already registered in the main bracket.", None

        if any(s.user_id == user_id for s in state.substitutes):
            return False, "You are already registered in the standby substitute queue.", None

        allowed, err_msg = self.is_region_allowed(region, guild_id=guild_id)
        if not allowed:
            return False, err_msg, None

        sub = Participant(
            user_id=user_id,
            user_mention=user_mention,
            ign=ign.strip(),
            weapon=weapon.strip(),
            region=region.strip().upper(),
        )
        state.substitutes.append(sub)
        self._persist(guild_id)

        queue_position = len(state.substitutes)
        return (
            True,
            f"Successfully entered the standby substitute queue at position #{queue_position}!",
            sub,
        )

    def unregister_substitute(self, user_id: int, guild_id: int = 0) -> tuple[bool, str]:
        """Withdraws a user from the substitute queue."""
        state = self.get_state(guild_id)
        idx = next(
            (i for i, s in enumerate(state.substitutes) if s.user_id == user_id),
            None,
        )
        if idx is None:
            return False, "You are not currently in the standby substitute queue."

        removed = state.substitutes.pop(idx)
        self._persist(guild_id)
        return True, f"Withdrew **{removed.ign}** ({removed.user_mention}) from the substitute queue."

    def edit_entry(
        self,
        user_id: int,
        weapon: str | None = None,
        ign: str | None = None,
        region: str | None = None,
        guild_id: int = 0,
    ) -> tuple[bool, str, Participant | None]:
        """
        Allows a player in the main bracket or substitute queue to update their declaration
        without losing their slot.
        """
        state = self.get_state(guild_id)
        target = next(
            (p for p in state.participants if p.user_id == user_id),
            None,
        )
        is_sub = False
        if not target:
            target = next(
                (s for s in state.substitutes if s.user_id == user_id),
                None,
            )
            is_sub = True

        if not target:
            return False, "You are not currently registered in the tournament or substitute queue.", None

        if region is not None:
            allowed, err_msg = self.is_region_allowed(region, guild_id=guild_id)
            if not allowed:
                return False, err_msg, None
            target.region = region.strip().upper()

        if weapon is not None:
            target.weapon = weapon.strip()

        if ign is not None and ign.strip():
            target.ign = ign.strip()

        self._persist(guild_id)
        role_label = "Standby Substitute" if is_sub else "Main Bracket"
        return (
            True,
            f"✅ Updated your entry in the **{role_label}**:\n"
            f"• IGN: **{target.ign}**\n"
            f"• Weapon: `{target.weapon}`\n"
            f"• Region: `{target.region}`",
            target,
        )

    # ---------------------------------------------------------
    # Standby Substitution / Promotion
    # ---------------------------------------------------------
    def promote_substitute(
        self,
        substitute_user_id: int | None = None,
        replace_user_id: int | None = None,
        guild_id: int = 0,
    ) -> tuple[bool, str, Participant | None]:
        """
        Promotes a substitute into the main bracket, optionally replacing a specific no-show player.
        """
        state = self.get_state(guild_id)
        if not state.substitutes:
            return False, "There are no substitutes currently waiting on deck.", None

        if substitute_user_id is not None:
            sub_idx = next(
                (i for i, s in enumerate(state.substitutes) if s.user_id == substitute_user_id),
                None,
            )
            if sub_idx is None:
                return False, f"User <@{substitute_user_id}> was not found in the substitute queue.", None
        else:
            sub_idx = 0

        sub_to_promote = state.substitutes[sub_idx]

        if replace_user_id is not None:
            rep_idx = next(
                (i for i, p in enumerate(state.participants) if p.user_id == replace_user_id),
                None,
            )
            if rep_idx is None:
                return (
                    False,
                    f"Target player to replace (<@{replace_user_id}>) was not found in the main bracket.",
                    None,
                )
            replaced_player = state.participants[rep_idx]
            state.participants[rep_idx] = sub_to_promote
            state.substitutes.pop(sub_idx)
            self._persist(guild_id)

            return (
                True,
                f"🔄 Swapped out **{replaced_player.ign}** ({replaced_player.user_mention}) and promoted "
                f"substitute **{sub_to_promote.ign}** ({sub_to_promote.user_mention}) into the main bracket!",
                sub_to_promote,
            )

        if len(state.participants) >= state.max_slots:
            return (
                False,
                f"Main bracket is full ({len(state.participants)}/{state.max_slots}). "
                "Specify a player to replace (`replace:<user>`) or expand slot capacity with `/tournament-set-limit`.",
                None,
            )

        state.substitutes.pop(sub_idx)
        state.participants.append(sub_to_promote)
        self._persist(guild_id)

        return (
            True,
            f"⬆️ Promoted substitute **{sub_to_promote.ign}** ({sub_to_promote.user_mention}) to the main bracket!",
            sub_to_promote,
        )

    # ---------------------------------------------------------
    # Tournament Day Flow: Check-In System
    # ---------------------------------------------------------
    def open_checkin(self, checkin_channel_id: int | None = None, guild_id: int = 0) -> str:
        """Opens check-in for registered participants."""
        state = self.get_state(guild_id)
        state.checkin_open = True
        if checkin_channel_id is not None:
            state.checkin_channel_id = checkin_channel_id
        self._persist(guild_id)
        return (
            f"📢 **Tournament Check-In is now OPEN for {state.name}!**\n"
            "All registered main bracket participants must run `/tournament-checkin` to secure their tournament spot."
        )

    def close_checkin(self, guild_id: int = 0) -> str:
        """Closes check-in."""
        state = self.get_state(guild_id)
        state.checkin_open = False
        self._persist(guild_id)
        checked_count = sum(1 for p in state.participants if p.checked_in)
        total = len(state.participants)
        return f"🔒 Tournament Check-In is now **CLOSED**. (`{checked_count} / {total}` checked in)."

    def checkin_user(self, user_id: int, guild_id: int = 0) -> tuple[bool, str]:
        """Records participant check-in."""
        state = self.get_state(guild_id)
        if not state.checkin_open:
            return False, "Tournament check-in is not currently open."

        p = next((p for p in state.participants if p.user_id == user_id), None)
        if p:
            if p.checked_in:
                return False, f"You are already checked in for **{state.name}**!"
            p.checked_in = True
            self._persist(guild_id)
            return True, f"✅ Check-in confirmed for **{p.ign}** ({p.user_mention})!"

        s = next((s for s in state.substitutes if s.user_id == user_id), None)
        if s:
            if s.checked_in:
                return False, f"You are already checked in as an active substitute!"
            s.checked_in = True
            self._persist(guild_id)
            return True, f"✅ Standby substitute check-in confirmed for **{s.ign}** ({s.user_mention})!"

        return False, "You are not registered in the tournament roster or substitute queue."

    def get_unconfirmed_participants(self, guild_id: int = 0) -> list[Participant]:
        """Returns main bracket participants who haven't checked in yet."""
        state = self.get_state(guild_id)
        return [p for p in state.participants if not p.checked_in]

    # ---------------------------------------------------------
    # Exporting Roster for External Brackets (Challonge/Start.gg)
    # ---------------------------------------------------------
    def export_roster(
        self, format_type: str = "csv", target: str = "all", guild_id: int = 0
    ) -> tuple[str, str]:
        """
        Exports the tournament roster formatted for Challonge, Start.gg, or spreadsheets.
        target options:
          - "all": Full roster including both main bracket and standby substitutes (default for spreadsheets).
          - "main": Main bracket participants only (recommended for direct Challonge/Start.gg bracket imports).
          - "subs": Standby substitutes only.
        Returns (filename, content_string).
        """
        state = self.get_state(guild_id)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        format_norm = format_type.lower().strip()
        target_norm = target.lower().strip()

        if format_norm == "challonge":
            if target_norm == "subs":
                lines = [s.ign for s in state.substitutes]
                filename = f"challonge_subs_{timestamp}.txt"
            elif target_norm == "all":
                lines = [p.ign for p in state.participants]
                if state.substitutes:
                    lines.extend(s.ign for s in state.substitutes)
                filename = f"challonge_all_{timestamp}.txt"
            else:  # default for challonge bracket: "main"
                lines = [p.ign for p in state.participants]
                filename = f"challonge_roster_{timestamp}.txt"
            return filename, "\n".join(lines)

        if format_norm == "text":
            lines = [f"=== {state.name} Roster ==="]
            if target_norm in ("main", "all"):
                lines.append(f"Main Bracket ({len(state.participants)}/{state.max_slots}):")
                for i, p in enumerate(state.participants, 1):
                    status = "Checked In" if p.checked_in else "Pending"
                    lines.append(f"{i}. {p.ign} (Discord: {p.user_id}) - {p.weapon} | {p.region} [{status}]")
                lines.append("")
            if target_norm in ("subs", "all"):
                lines.append(f"Standby Substitutes ({len(state.substitutes)}):")
                for i, s in enumerate(state.substitutes, 1):
                    status = "Checked In" if s.checked_in else "Pending"
                    lines.append(f"{i}. {s.ign} (Discord: {s.user_id}) - {s.weapon} | {s.region} [{status}]")
            filename = f"tournament_roster_{timestamp}.txt"
            return filename, "\n".join(lines)

        # Default: CSV format
        output = io.StringIO()
        writer = csv.writer(output)

        if target_norm == "main":
            writer.writerow(["Seed", "IGN", "Discord_ID", "Weapon", "Region", "Checked_In"])
            for seed, p in enumerate(state.participants, 1):
                writer.writerow([
                    seed,
                    p.ign,
                    p.user_id,
                    p.weapon,
                    p.region,
                    "YES" if p.checked_in else "NO",
                ])
            filename = f"tournament_bracket_roster_{timestamp}.csv"
        elif target_norm == "subs":
            writer.writerow(["Queue_Position", "IGN", "Discord_ID", "Weapon", "Region", "Checked_In"])
            for pos, s in enumerate(state.substitutes, 1):
                writer.writerow([
                    pos,
                    s.ign,
                    s.user_id,
                    s.weapon,
                    s.region,
                    "YES" if s.checked_in else "NO",
                ])
            filename = f"tournament_subs_roster_{timestamp}.csv"
        else:  # "all"
            writer.writerow(["Seed", "IGN", "Discord_ID", "Weapon", "Region", "Checked_In", "Role"])
            for seed, p in enumerate(state.participants, 1):
                writer.writerow([
                    seed,
                    p.ign,
                    p.user_id,
                    p.weapon,
                    p.region,
                    "YES" if p.checked_in else "NO",
                    "Main Bracket",
                ])
            for seed, s in enumerate(state.substitutes, 1):
                writer.writerow([
                    seed,
                    s.ign,
                    s.user_id,
                    s.weapon,
                    s.region,
                    "YES" if s.checked_in else "NO",
                    "Substitute",
                ])
            filename = f"tournament_roster_{timestamp}.csv"

        return filename, output.getvalue()
