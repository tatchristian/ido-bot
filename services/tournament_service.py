"""
Domain service handling tournament business logic, registrations, validations, and roster states.
"""

from __future__ import annotations

import logging
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
STANDARD_REGIONS = ["NA", "EU", "OCE", "ASIA", "SA", "ME"]


@dataclass
class Participant:
    user_id: int
    user_mention: str
    ign: str
    weapon: str
    region: str
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
    max_slots: int = 8
    allowed_regions: list[str] = field(default_factory=lambda: ["GLOBAL"])
    approved_weapons: list[str] = field(default_factory=lambda: list(DEFAULT_WEAPONS))
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
            max_slots=int(data.get("max_slots", 8)),
            allowed_regions=list(data.get("allowed_regions", ["GLOBAL"])),
            approved_weapons=list(data.get("approved_weapons", DEFAULT_WEAPONS)),
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
            "max_slots": self.max_slots,
            "allowed_regions": self.allowed_regions,
            "approved_weapons": self.approved_weapons,
            "participants": [p.to_dict() for p in self.participants],
            "substitutes": [s.to_dict() for s in self.substitutes],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TournamentService:
    """
    Manages tournament operations, enforcing rules for registration, capacity,
    regions, and standby queue promotions.
    """

    def __init__(self, storage: StorageManager):
        self.storage = storage
        self.state: TournamentState = self._load_state()

    def _load_state(self) -> TournamentState:
        data = self.storage.load(default_factory=lambda: TournamentState().to_dict())
        try:
            return TournamentState.from_dict(data)
        except Exception as e:
            logger.error("Failed to parse tournament state, resetting to default: %s", e)
            default = TournamentState()
            self.storage.save(default.to_dict())
            return default

    def _persist(self) -> None:
        self.state.updated_at = datetime.now(timezone.utc).isoformat()
        self.storage.save(self.state.to_dict())

    def get_state(self) -> TournamentState:
        return self.state

    # ---------------------------------------------------------
    # Region Validation
    # ---------------------------------------------------------
    def parse_regions(self, regions_input: str | list[str]) -> list[str]:
        """Normalizes comma or space separated regions into an uppercase list."""
        if isinstance(regions_input, str):
            raw_tokens = [r.strip().upper() for r in regions_input.replace("/", ",").split(",") if r.strip()]
        else:
            raw_tokens = [r.strip().upper() for r in regions_input if r.strip()]

        if not raw_tokens:
            return ["GLOBAL"]

        if any(r == "GLOBAL" for r in raw_tokens):
            return ["GLOBAL"]

        return sorted(list(dict.fromkeys(raw_tokens)))

    def is_region_allowed(self, user_region: str) -> tuple[bool, str]:
        """
        Validates whether the user's selected region is allowed in this tournament.
        Returns (is_allowed, error_message_if_not).
        """
        cleaned_user = user_region.strip().upper()

        # If tournament allows GLOBAL, any region is eligible
        if "GLOBAL" in self.state.allowed_regions:
            return True, ""

        allowed_upper = [r.upper() for r in self.state.allowed_regions]

        # Check exact match or prefix match (e.g. 'NA East' contains 'NA')
        for allowed in allowed_upper:
            if cleaned_user == allowed or cleaned_user.startswith(allowed) or allowed in cleaned_user:
                return True, ""

        allowed_str = ", ".join(self.state.allowed_regions)
        return False, f"This tournament is only open to participants from: {allowed_str}"

    # ---------------------------------------------------------
    # Admin Controls
    # ---------------------------------------------------------
    def open_tournament(
        self,
        name: str | None = None,
        slots: int | None = None,
        regions: str | list[str] | None = None,
        open_subs: bool = False,
    ) -> str:
        """Opens main bracket submissions and updates tournament settings."""
        if name:
            self.state.name = name.strip()
        if slots is not None:
            if slots < 2:
                raise ValueError("Tournament slot capacity must be at least 2.")
            self.state.max_slots = slots
        if regions is not None:
            self.state.allowed_regions = self.parse_regions(regions)

        self.state.main_open = True
        self.state.subs_open = open_subs
        self._persist()

        sub_status = "OPEN" if self.state.subs_open else "CLOSED"
        regions_str = ", ".join(self.state.allowed_regions)
        return (
            f"🏆 **{self.state.name}** is now **OPEN**!\n"
            f"• Max Slots: `{self.state.max_slots}`\n"
            f"• Allowed Regions: `{regions_str}`\n"
            f"• Substitute Signups: `{sub_status}`"
        )

    def close_tournament(self) -> str:
        """Closes main bracket registrations."""
        self.state.main_open = False
        self._persist()
        return f"🔒 Main bracket submissions for **{self.state.name}** are now **CLOSED**."

    def open_subs(self) -> str:
        """Enables substitute signups."""
        self.state.subs_open = True
        self._persist()
        return f"🟢 Substitute signups for **{self.state.name}** are now **OPEN**."

    def close_subs(self) -> str:
        """Disables substitute signups."""
        self.state.subs_open = False
        self._persist()
        return f"🔴 Substitute signups for **{self.state.name}** are now **CLOSED**."

    def set_limit(self, limit: int) -> str:
        """Updates max capacity for the main bracket."""
        if limit < 2:
            raise ValueError("Participant limit must be at least 2.")
        old_limit = self.state.max_slots
        self.state.max_slots = limit
        self._persist()
        return f"📊 Tournament slot capacity updated from `{old_limit}` to `{limit}`."

    def set_regions(self, regions: str | list[str]) -> str:
        """Updates allowed regions for the tournament."""
        parsed = self.parse_regions(regions)
        self.state.allowed_regions = parsed
        self._persist()
        return f"🌍 Allowed regions updated to: `{', '.join(parsed)}`."

    def clear_tournament(self) -> str:
        """Wipes both main roster and substitute list."""
        p_count = len(self.state.participants)
        s_count = len(self.state.substitutes)
        self.state.participants.clear()
        self.state.substitutes.clear()
        self._persist()
        return f"🧹 Tournament roster wiped clean ({p_count} main players and {s_count} substitutes removed)."

    # ---------------------------------------------------------
    # Player Registration
    # ---------------------------------------------------------
    def register_participant(
        self,
        user_id: int,
        user_mention: str,
        ign: str,
        weapon: str,
        region: str,
    ) -> tuple[bool, str, Participant | None]:
        """
        Signs up a user for the main bracket. Validates state, slots, duplicates, and regions.
        """
        # 1. Check if main registration is open
        if not self.state.main_open:
            return False, "Main bracket submissions are currently closed.", None

        # 2. Check if already in main bracket
        if any(p.user_id == user_id for p in self.state.participants):
            return False, "You are already registered in the main bracket.", None

        # 3. Check if already in substitute queue
        if any(s.user_id == user_id for s in self.state.substitutes):
            return (
                False,
                "You are already in the standby substitute queue. Unregister first if you wish to join the main bracket.",
                None,
            )

        # 4. Check slot capacity
        if len(self.state.participants) >= self.state.max_slots:
            sub_hint = " You can sign up as a standby substitute with `/tournament-sub-register`." if self.state.subs_open else ""
            return (
                False,
                f"The main bracket is currently full ({len(self.state.participants)}/{self.state.max_slots} registered).{sub_hint}",
                None,
            )

        # 5. Check region validity
        allowed, err_msg = self.is_region_allowed(region)
        if not allowed:
            return False, err_msg, None

        # Add participant
        participant = Participant(
            user_id=user_id,
            user_mention=user_mention,
            ign=ign.strip(),
            weapon=weapon.strip(),
            region=region.strip().upper(),
        )
        self.state.participants.append(participant)
        self._persist()

        return True, "Successfully registered for the main bracket!", participant

    def unregister_participant(self, user_id: int) -> tuple[bool, str]:
        """Withdraws a user from the main bracket."""
        idx = next(
            (i for i, p in enumerate(self.state.participants) if p.user_id == user_id),
            None,
        )
        if idx is None:
            return False, "You are not currently registered in the main bracket."

        removed = self.state.participants.pop(idx)
        self._persist()
        return True, f"Withdrew **{removed.ign}** ({removed.user_mention}) from the main bracket."

    # ---------------------------------------------------------
    # Substitute Queue
    # ---------------------------------------------------------
    def register_substitute(
        self,
        user_id: int,
        user_mention: str,
        ign: str,
        weapon: str,
        region: str,
    ) -> tuple[bool, str, Participant | None]:
        """Signs up a user for the standby substitute queue."""
        # 1. Check if sub signups are open
        if not self.state.subs_open:
            return False, "Substitute signups are currently closed.", None

        # 2. Check if already in main bracket
        if any(p.user_id == user_id for p in self.state.participants):
            return False, "You are already registered in the main bracket.", None

        # 3. Check if already in substitute queue
        if any(s.user_id == user_id for s in self.state.substitutes):
            return False, "You are already registered in the standby substitute queue.", None

        # 4. Check region validity
        allowed, err_msg = self.is_region_allowed(region)
        if not allowed:
            return False, err_msg, None

        # Add substitute
        sub = Participant(
            user_id=user_id,
            user_mention=user_mention,
            ign=ign.strip(),
            weapon=weapon.strip(),
            region=region.strip().upper(),
        )
        self.state.substitutes.append(sub)
        self._persist()

        queue_position = len(self.state.substitutes)
        return (
            True,
            f"Successfully entered the standby substitute queue at position #{queue_position}!",
            sub,
        )

    def unregister_substitute(self, user_id: int) -> tuple[bool, str]:
        """Withdraws a user from the substitute queue."""
        idx = next(
            (i for i, s in enumerate(self.state.substitutes) if s.user_id == user_id),
            None,
        )
        if idx is None:
            return False, "You are not currently in the standby substitute queue."

        removed = self.state.substitutes.pop(idx)
        self._persist()
        return True, f"Withdrew **{removed.ign}** ({removed.user_mention}) from the substitute queue."

    # ---------------------------------------------------------
    # Standby Substitution / Promotion
    # ---------------------------------------------------------
    def promote_substitute(
        self,
        substitute_user_id: int | None = None,
        replace_user_id: int | None = None,
    ) -> tuple[bool, str, Participant | None]:
        """
        Promotes a substitute into the main bracket, optionally replacing a specific no-show player.
        If substitute_user_id is None, takes the first substitute in queue (FIFO).
        """
        if not self.state.substitutes:
            return False, "There are no substitutes currently waiting on deck.", None

        # 1. Locate the substitute to promote
        if substitute_user_id is not None:
            sub_idx = next(
                (i for i, s in enumerate(self.state.substitutes) if s.user_id == substitute_user_id),
                None,
            )
            if sub_idx is None:
                return False, f"User <@{substitute_user_id}> was not found in the substitute queue.", None
        else:
            sub_idx = 0  # Head of queue

        sub_to_promote = self.state.substitutes[sub_idx]

        # 2. Check replacement target or available slot
        replaced_player: Participant | None = None
        if replace_user_id is not None:
            rep_idx = next(
                (i for i, p in enumerate(self.state.participants) if p.user_id == replace_user_id),
                None,
            )
            if rep_idx is None:
                return (
                    False,
                    f"Target player to replace (<@{replace_user_id}>) was not found in the main bracket.",
                    None,
                )
            replaced_player = self.state.participants[rep_idx]
            # Remove replaced player and insert substitute in their spot
            self.state.participants[rep_idx] = sub_to_promote
            self.state.substitutes.pop(sub_idx)
            self._persist()

            return (
                True,
                f"🔄 Swapped out **{replaced_player.ign}** ({replaced_player.user_mention}) and promoted "
                f"substitute **{sub_to_promote.ign}** ({sub_to_promote.user_mention}) into the main bracket!",
                sub_to_promote,
            )

        # If not replacing someone, verify main bracket capacity
        if len(self.state.participants) >= self.state.max_slots:
            return (
                False,
                f"Main bracket is full ({len(self.state.participants)}/{self.state.max_slots}). "
                "Specify a player to replace (`replace:<user>`) or expand slot capacity with `/tournament-set-limit`.",
                None,
            )

        # Move sub to main bracket
        self.state.substitutes.pop(sub_idx)
        self.state.participants.append(sub_to_promote)
        self._persist()

        return (
            True,
            f"⬆️ Promoted substitute **{sub_to_promote.ign}** ({sub_to_promote.user_mention}) to the main bracket!",
            sub_to_promote,
        )
