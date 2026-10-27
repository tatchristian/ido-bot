"""
Domain service handling tournament business logic, registrations, validations,
check-ins, and roster states.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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
# Standard competitive regions (ME removed as requested)
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
            "participants": [p.to_dict() for p in self.participants],
            "substitutes": [s.to_dict() for s in self.substitutes],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TournamentService:
    """
    Manages tournament operations, enforcing rules for registration, capacity,
    regions, standby promotions, check-in, and tournament day flow.
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
            raw_tokens = [
                r.strip().upper()
                for r in regions_input.replace("/", ",").split(",")
                if r.strip()
            ]
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

        if "GLOBAL" in self.state.allowed_regions:
            return True, ""

        allowed_upper = [r.upper() for r in self.state.allowed_regions]

        for allowed in allowed_upper:
            if (
                cleaned_user == allowed
                or cleaned_user.startswith(allowed)
                or allowed in cleaned_user
            ):
                return True, ""

        allowed_str = ", ".join(self.state.allowed_regions)
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

    def set_approved_weapons(self, weapons_input: str | list[str]) -> str:
        """Updates approved weapons for the tournament."""
        if isinstance(weapons_input, str):
            weapons = [w.strip() for w in weapons_input.split(",") if w.strip()]
        else:
            weapons = [w.strip() for w in weapons_input if w.strip()]

        if not weapons:
            self.state.approved_weapons = list(DEFAULT_WEAPONS)
        else:
            self.state.approved_weapons = weapons

        self._persist()
        return f"⚔️ Approved weapons updated: {', '.join(self.state.approved_weapons)}."

    def clear_tournament(self) -> str:
        """Wipes both main roster and substitute list."""
        p_count = len(self.state.participants)
        s_count = len(self.state.substitutes)
        self.state.participants.clear()
        self.state.substitutes.clear()
        self.state.checkin_open = False
        self._persist()
        return f"🧹 Tournament roster wiped clean ({p_count} main players and {s_count} substitutes removed)."

    # ---------------------------------------------------------
    # Essential Admin Tools (Kick & Force Register)
    # ---------------------------------------------------------
    def kick_user(self, user_id: int, reason: str = "") -> tuple[bool, str]:
        """Removes a user from either the main bracket or the substitute queue."""
        # Check main bracket
        p_idx = next(
            (i for i, p in enumerate(self.state.participants) if p.user_id == user_id),
            None,
        )
        if p_idx is not None:
            removed = self.state.participants.pop(p_idx)
            self._persist()
            reason_str = f" Reason: *{reason}*" if reason else ""
            return (
                True,
                f"👢 Removed **{removed.ign}** ({removed.user_mention}) from the **main bracket**.{reason_str}",
            )

        # Check substitute queue
        s_idx = next(
            (i for i, s in enumerate(self.state.substitutes) if s.user_id == user_id),
            None,
        )
        if s_idx is not None:
            removed = self.state.substitutes.pop(s_idx)
            self._persist()
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
    ) -> tuple[bool, str, Participant]:
        """
        Allows tournament admins to manually slot a player into the main bracket or substitute queue.
        Bypasses standard registration open/closed states.
        """
        # Remove from existing lists to prevent duplicates
        self.state.participants = [p for p in self.state.participants if p.user_id != user_id]
        self.state.substitutes = [s for s in self.state.substitutes if s.user_id != user_id]

        participant = Participant(
            user_id=user_id,
            user_mention=user_mention,
            ign=ign.strip(),
            weapon=weapon.strip(),
            region=region.strip().upper(),
        )

        if as_sub:
            self.state.substitutes.append(participant)
            queue_pos = len(self.state.substitutes)
            self._persist()
            return (
                True,
                f"👑 Admin force-registered **{participant.ign}** ({participant.user_mention}) into the **substitute queue** at position #{queue_pos}.",
                participant,
            )
        else:
            self.state.participants.append(participant)
            slots_now = len(self.state.participants)
            self._persist()
            return (
                True,
                f"👑 Admin force-registered **{participant.ign}** ({participant.user_mention}) into the **main bracket** ({slots_now}/{self.state.max_slots}).",
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
    ) -> tuple[bool, str, Participant | None]:
        """Signs up a user for the main bracket."""
        if not self.state.main_open:
            return False, "Main bracket submissions are currently closed.", None

        if any(p.user_id == user_id for p in self.state.participants):
            return False, "You are already registered in the main bracket.", None

        if any(s.user_id == user_id for s in self.state.substitutes):
            return (
                False,
                "You are already in the standby substitute queue. Unregister first if you wish to join the main bracket.",
                None,
            )

        if len(self.state.participants) >= self.state.max_slots:
            sub_hint = (
                " You can sign up as a standby substitute with `/tournament-sub-register`."
                if self.state.subs_open
                else ""
            )
            return (
                False,
                f"The main bracket is currently full ({len(self.state.participants)}/{self.state.max_slots} registered).{sub_hint}",
                None,
            )

        allowed, err_msg = self.is_region_allowed(region)
        if not allowed:
            return False, err_msg, None

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

    def register_substitute(
        self,
        user_id: int,
        user_mention: str,
        ign: str,
        weapon: str,
        region: str,
    ) -> tuple[bool, str, Participant | None]:
        """Signs up a user for the standby substitute queue."""
        if not self.state.subs_open:
            return False, "Substitute signups are currently closed.", None

        if any(p.user_id == user_id for p in self.state.participants):
            return False, "You are already registered in the main bracket.", None

        if any(s.user_id == user_id for s in self.state.substitutes):
            return False, "You are already registered in the standby substitute queue.", None

        allowed, err_msg = self.is_region_allowed(region)
        if not allowed:
            return False, err_msg, None

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

    def edit_entry(
        self,
        user_id: int,
        weapon: str | None = None,
        ign: str | None = None,
        region: str | None = None,
    ) -> tuple[bool, str, Participant | None]:
        """
        Allows a player in the main bracket or substitute queue to update their declaration
        without losing their slot.
        """
        target = next(
            (p for p in self.state.participants if p.user_id == user_id),
            None,
        )
        is_sub = False
        if not target:
            target = next(
                (s for s in self.state.substitutes if s.user_id == user_id),
                None,
            )
            is_sub = True

        if not target:
            return False, "You are not currently registered in the tournament or substitute queue.", None

        if region is not None:
            allowed, err_msg = self.is_region_allowed(region)
            if not allowed:
                return False, err_msg, None
            target.region = region.strip().upper()

        if weapon is not None:
            target.weapon = weapon.strip()

        if ign is not None and ign.strip():
            target.ign = ign.strip()

        self._persist()
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
    ) -> tuple[bool, str, Participant | None]:
        """
        Promotes a substitute into the main bracket, optionally replacing a specific no-show player.
        """
        if not self.state.substitutes:
            return False, "There are no substitutes currently waiting on deck.", None

        if substitute_user_id is not None:
            sub_idx = next(
                (i for i, s in enumerate(self.state.substitutes) if s.user_id == substitute_user_id),
                None,
            )
            if sub_idx is None:
                return False, f"User <@{substitute_user_id}> was not found in the substitute queue.", None
        else:
            sub_idx = 0

        sub_to_promote = self.state.substitutes[sub_idx]

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
            self.state.participants[rep_idx] = sub_to_promote
            self.state.substitutes.pop(sub_idx)
            self._persist()

            return (
                True,
                f"🔄 Swapped out **{replaced_player.ign}** ({replaced_player.user_mention}) and promoted "
                f"substitute **{sub_to_promote.ign}** ({sub_to_promote.user_mention}) into the main bracket!",
                sub_to_promote,
            )

        if len(self.state.participants) >= self.state.max_slots:
            return (
                False,
                f"Main bracket is full ({len(self.state.participants)}/{self.state.max_slots}). "
                "Specify a player to replace (`replace:<user>`) or expand slot capacity with `/tournament-set-limit`.",
                None,
            )

        self.state.substitutes.pop(sub_idx)
        self.state.participants.append(sub_to_promote)
        self._persist()

        return (
            True,
            f"⬆️ Promoted substitute **{sub_to_promote.ign}** ({sub_to_promote.user_mention}) to the main bracket!",
            sub_to_promote,
        )

    # ---------------------------------------------------------
    # Tournament Day Flow: Check-In System
    # ---------------------------------------------------------
    def open_checkin(self) -> str:
        """Opens check-in for registered participants."""
        self.state.checkin_open = True
        self._persist()
        return (
            f"📢 **Tournament Check-In is now OPEN for {self.state.name}!**\n"
            "All registered main bracket participants must run `/tournament-checkin` to secure their tournament spot."
        )

    def close_checkin(self) -> str:
        """Closes check-in."""
        self.state.checkin_open = False
        self._persist()
        checked_count = sum(1 for p in self.state.participants if p.checked_in)
        total = len(self.state.participants)
        return f"🔒 Tournament Check-In is now **CLOSED**. (`{checked_count} / {total}` checked in)."

    def checkin_user(self, user_id: int) -> tuple[bool, str]:
        """Records participant check-in."""
        if not self.state.checkin_open:
            return False, "Tournament check-in is not currently open."

        # Find in main participants
        p = next((p for p in self.state.participants if p.user_id == user_id), None)
        if p:
            if p.checked_in:
                return False, f"You are already checked in for **{self.state.name}**!"
            p.checked_in = True
            self._persist()
            return True, f"✅ Check-in confirmed for **{p.ign}** ({p.user_mention})!"

        # If in substitutes, they can also mark presence so admins know they are active
        s = next((s for s in self.state.substitutes if s.user_id == user_id), None)
        if s:
            if s.checked_in:
                return False, f"You are already checked in as an active substitute!"
            s.checked_in = True
            self._persist()
            return True, f"✅ Standby substitute check-in confirmed for **{s.ign}** ({s.user_mention})!"

        return False, "You are not registered in the tournament roster or substitute queue."

    def get_unconfirmed_participants(self) -> list[Participant]:
        """Returns main bracket participants who haven't checked in yet."""
        return [p for p in self.state.participants if not p.checked_in]

    # ---------------------------------------------------------
    # Exporting Roster for External Brackets (Challonge/Start.gg)
    # ---------------------------------------------------------
    def export_roster(self, format_type: str = "csv") -> tuple[str, str]:
        """
        Exports the tournament roster formatted for Challonge, Start.gg, or spreadsheets.
        Returns (filename, content_string).
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        format_norm = format_type.lower().strip()

        if format_norm == "challonge":
            # Challonge accepts plain text list of participant names (one per line)
            lines = [p.ign for p in self.state.participants]
            filename = f"challonge_roster_{timestamp}.txt"
            return filename, "\n".join(lines)

        if format_norm == "text":
            lines = [f"=== {self.state.name} Roster ==="]
            lines.append(f"Main Bracket ({len(self.state.participants)}/{self.state.max_slots}):")
            for i, p in enumerate(self.state.participants, 1):
                status = "Checked In" if p.checked_in else "Pending"
                lines.append(f"{i}. {p.ign} (Discord: {p.user_id}) - {p.weapon} | {p.region} [{status}]")
            lines.append("")
            lines.append(f"Standby Substitutes ({len(self.state.substitutes)}):")
            for i, s in enumerate(self.state.substitutes, 1):
                status = "Checked In" if s.checked_in else "Pending"
                lines.append(f"{i}. {s.ign} (Discord: {s.user_id}) - {s.weapon} | {s.region} [{status}]")
            filename = f"tournament_roster_{timestamp}.txt"
            return filename, "\n".join(lines)

        # Default: CSV format (compatible with Excel, Google Sheets, Battlefy, Start.gg)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Seed", "IGN", "Discord_ID", "Weapon", "Region", "Checked_In", "Role"])

        for seed, p in enumerate(self.state.participants, 1):
            writer.writerow([
                seed,
                p.ign,
                p.user_id,
                p.weapon,
                p.region,
                "YES" if p.checked_in else "NO",
                "Main Bracket",
            ])

        for seed, s in enumerate(self.state.substitutes, 1):
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
