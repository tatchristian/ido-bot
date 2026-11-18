"""
Bracket Engine
Pure mathematical and tournament tree generation engine for Single and Double Elimination.
Supports standard seeding, power-of-2 normalization, automatic bye resolution,
dynamic ready-state pipeline for out-of-order match play, and result undo.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


def generate_seed_order(bracket_size: int) -> List[int]:
    """
    Generates standard competitive tournament pairing order so Seed 1 and Seed 2
    can only meet in the Finals.
    e.g. 4 -> [1, 4, 2, 3]
         8 -> [1, 8, 4, 5, 2, 7, 3, 6]
    """
    if bracket_size <= 1:
        return [1]
    prev = generate_seed_order(bracket_size // 2)
    order = []
    for x in prev:
        order.append(x)
        order.append(bracket_size + 1 - x)
    return order


@dataclass
class BracketMatch:
    match_id: str                       # e.g. "WB-R1-M1", "LB-R1-M1", "GF", "GF-RESET"
    section: str                        # "winners", "losers", "finals"
    round_number: int                   # 1, 2, 3...
    match_number: int                   # 1, 2, 3...
    player1_id: Optional[int] = None    # Discord User ID
    player1_ign: str = "TBD"            # IGN, "BYE", or "TBD"
    player1_clan: Optional[str] = None
    player1_checked_in: bool = False
    player2_id: Optional[int] = None
    player2_ign: str = "TBD"
    player2_clan: Optional[str] = None
    player2_checked_in: bool = False
    score: Optional[str] = None
    winner_id: Optional[int] = None
    winner_ign: Optional[str] = None
    loser_id: Optional[int] = None
    loser_ign: Optional[str] = None
    state: str = "pending"              # "pending", "ready", "completed", "bye"
    next_match_id: Optional[str] = None
    next_match_slot: int = 1            # 1 or 2
    loser_match_id: Optional[str] = None
    loser_match_slot: int = 1           # 1 or 2

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BracketMatch:
        known = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class TournamentBracket:
    format: str = "single"              # "single" or "double"
    is_locked: bool = False             # False = Draft (auto-updates); True = Live in progress
    seed_mode: str = "registration"     # "registration" or "random"
    bracket_size: int = 0               # Power of 2 (4, 8, 16, 32, 64)
    total_rounds_wb: int = 0
    total_rounds_lb: int = 0
    matches: Dict[str, BracketMatch] = field(default_factory=dict)
    champion_id: Optional[int] = None
    champion_ign: Optional[str] = None
    runner_up_id: Optional[int] = None
    runner_up_ign: Optional[str] = None
    third_place_id: Optional[int] = None
    third_place_ign: Optional[str] = None
    channel_id: Optional[int] = None
    message_id: Optional[int] = None

    @property
    def total_rounds(self) -> int:
        return self.total_rounds_wb

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["matches"] = {k: v.to_dict() for k, v in self.matches.items()}
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TournamentBracket:
        raw_matches = data.get("matches", {})
        parsed_matches = {k: BracketMatch.from_dict(v) for k, v in raw_matches.items()}
        known = cls.__dataclass_fields__.keys()
        kwargs = {k: v for k, v in data.items() if k in known and k != "matches"}
        kwargs["matches"] = parsed_matches
        return cls(**kwargs)


class BracketEngine:
    """Core algorithmic engine for tournament bracket generation and progression."""

    @staticmethod
    def calculate_bracket_size(participant_count: int) -> int:
        """Calculates nearest power of 2 >= participant_count (min 2)."""
        if participant_count <= 2:
            return 2
        return 1 << (participant_count - 1).bit_length()

    @classmethod
    def build_bracket(
        cls,
        participants: List[Dict[str, Any]],
        format: str = "single",
        seed_mode: str = "registration",
        custom_seed_ids: Optional[List[int]] = None,
    ) -> TournamentBracket:
        """
        Builds a complete single or double elimination bracket tree from a list of participants.
        Automatically resolves Round 1 Byes and flags active matches as READY.
        """
        if not participants:
            return TournamentBracket(format=format)

        count = len(participants)
        bracket_size = cls.calculate_bracket_size(count)
        wb_rounds = int(math.log2(bracket_size))

        # 1. Order participants by seed
        ordered_players: List[Optional[Dict[str, Any]]] = []
        if seed_mode == "random":
            shuffled = list(participants)
            random.shuffle(shuffled)
            ordered_players = list(shuffled)
        elif custom_seed_ids:
            p_map = {p.get("user_id"): p for p in participants}
            ordered_players = [p_map[uid] for uid in custom_seed_ids if uid in p_map]
            for p in participants:
                if p not in ordered_players:
                    ordered_players.append(p)
        else:
            ordered_players = list(participants)

        # Pad with BYEs up to bracket_size
        seeds_map: Dict[int, Optional[Dict[str, Any]]] = {}
        for idx in range(bracket_size):
            seeds_map[idx + 1] = ordered_players[idx] if idx < len(ordered_players) else None

        bracket = TournamentBracket(
            format=format,
            is_locked=False,
            seed_mode=seed_mode,
            bracket_size=bracket_size,
            total_rounds_wb=wb_rounds,
            total_rounds_lb=max(1, (wb_rounds - 1) * 2) if format == "double" else 0,
        )

        # 2. Build Winners Bracket matches
        cls._build_winners_bracket(bracket, seeds_map, wb_rounds, bracket_size)

        # 3. Build Losers Bracket & Finals if double elimination
        if format == "double" and wb_rounds > 1:
            cls._build_double_elim_routes(bracket, wb_rounds)

        # 4. Propagate Byes and evaluate READY states
        cls.evaluate_ready_states(bracket)
        return bracket

    @classmethod
    def _build_winners_bracket(
        cls,
        bracket: TournamentBracket,
        seeds_map: Dict[int, Optional[Dict[str, Any]]],
        wb_rounds: int,
        bracket_size: int,
    ) -> None:
        """Constructs binary tree for Winners Bracket."""
        seed_pairing = generate_seed_order(bracket_size)

        # Round 1 matches
        r1_matches_count = bracket_size // 2
        for m_idx in range(1, r1_matches_count + 1):
            match_id = f"WB-R1-M{m_idx}"
            s1 = seed_pairing[(m_idx - 1) * 2]
            s2 = seed_pairing[(m_idx - 1) * 2 + 1]
            p1 = seeds_map.get(s1)
            p2 = seeds_map.get(s2)

            next_m = (m_idx + 1) // 2
            next_slot = 1 if (m_idx % 2 != 0) else 2
            next_id = f"WB-R2-M{next_m}" if wb_rounds > 1 else "GF"

            bm = BracketMatch(
                match_id=match_id,
                section="winners",
                round_number=1,
                match_number=m_idx,
                player1_id=p1.get("user_id") if p1 else None,
                player1_ign=p1.get("ign", "BYE") if p1 else "BYE",
                player1_clan=p1.get("clan") if p1 else None,
                player1_checked_in=p1.get("checked_in", False) if p1 else False,
                player2_id=p2.get("user_id") if p2 else None,
                player2_ign=p2.get("ign", "BYE") if p2 else "BYE",
                player2_clan=p2.get("clan") if p2 else None,
                player2_checked_in=p2.get("checked_in", False) if p2 else False,
                next_match_id=next_id,
                next_match_slot=next_slot,
            )
            bracket.matches[match_id] = bm

        # Round 2..N matches
        for r in range(2, wb_rounds + 1):
            matches_in_r = bracket_size // (1 << r)
            for m_idx in range(1, matches_in_r + 1):
                match_id = f"WB-R{r}-M{m_idx}"
                next_m = (m_idx + 1) // 2
                next_slot = 1 if (m_idx % 2 != 0) else 2
                next_id = f"WB-R{r+1}-M{next_m}" if r < wb_rounds else "GF"

                bm = BracketMatch(
                    match_id=match_id,
                    section="winners" if r < wb_rounds else "finals",
                    round_number=r,
                    match_number=m_idx,
                    next_match_id=next_id,
                    next_match_slot=next_slot,
                )
                bracket.matches[match_id] = bm

        # Finals (Grand Finals match if format is double or single)
        if "GF" not in bracket.matches and wb_rounds == 1:
            # 2 players directly in finals
            pass

    @classmethod
    def _build_double_elim_routes(cls, bracket: TournamentBracket, wb_rounds: int) -> None:
        """Sets up Losers Bracket structure and Grand Finals match routing."""
        # Add Grand Finals match
        gf = BracketMatch(
            match_id="GF",
            section="finals",
            round_number=wb_rounds + 1,
            match_number=1,
        )
        bracket.matches["GF"] = gf

        # Losers bracket rounds
        total_lb_rounds = (wb_rounds - 1) * 2
        for lr in range(1, total_lb_rounds + 1):
            # Matches count halves every 2 rounds
            stage = (lr + 1) // 2
            matches_count = (bracket.bracket_size // 4) // (1 << (stage - 1))
            matches_count = max(1, matches_count)

            for m_idx in range(1, matches_count + 1):
                match_id = f"LB-R{lr}-M{m_idx}"
                if lr < total_lb_rounds:
                    if lr % 2 != 0:
                        # Odd round -> advances to same match index in next even round (slot 2)
                        next_id = f"LB-R{lr+1}-M{m_idx}"
                        next_slot = 2
                    else:
                        # Even round -> advances to halved index in next odd round (slot 1)
                        next_id = f"LB-R{lr+1}-M{(m_idx + 1) // 2}"
                        next_slot = 1 if m_idx % 2 != 0 else 2
                else:
                    # Winner of Losers Finals advances to Grand Finals slot 2!
                    next_id = "GF"
                    next_slot = 2

                bm = BracketMatch(
                    match_id=match_id,
                    section="losers",
                    round_number=lr,
                    match_number=m_idx,
                    next_match_id=next_id,
                    next_match_slot=next_slot,
                )
                bracket.matches[match_id] = bm

        # Route WB Round 1 losers to LB Round 1
        r1_wb_count = bracket.bracket_size // 2
        for m_idx in range(1, r1_wb_count + 1):
            wb_id = f"WB-R1-M{m_idx}"
            lb_id = f"LB-R1-M{(m_idx + 1) // 2}"
            if wb_id in bracket.matches and lb_id in bracket.matches:
                bracket.matches[wb_id].loser_match_id = lb_id
                bracket.matches[wb_id].loser_match_slot = 1 if m_idx % 2 != 0 else 2

        # Route WB Round 2..N losers to corresponding drop-down LB rounds
        for r in range(2, wb_rounds + 1):
            matches_in_r = bracket.bracket_size // (1 << r)
            target_lb_round = 2 * (r - 1)
            for m_idx in range(1, matches_in_r + 1):
                wb_id = f"WB-R{r}-M{m_idx}"
                lb_id = f"LB-R{target_lb_round}-M{m_idx}"
                if wb_id in bracket.matches and lb_id in bracket.matches:
                    bracket.matches[wb_id].loser_match_id = lb_id
                    bracket.matches[wb_id].loser_match_slot = 1

    @classmethod
    def evaluate_ready_states(cls, bracket: TournamentBracket) -> None:
        """
        Processes byes and calculates match 'ready' states.
        A match is 'ready' the exact moment both player1 and player2 slots are filled!
        """
        changed = True
        while changed:
            changed = False
            for m in list(bracket.matches.values()):
                # Auto-resolve BYEs
                if m.state not in ("completed", "bye"):
                    if m.player1_ign == "BYE" and m.player2_ign != "BYE" and m.player2_id is not None:
                        m.state = "bye"
                        m.winner_id = m.player2_id
                        m.winner_ign = m.player2_ign
                        cls._advance_winner(bracket, m)
                        cls._drop_bye_loser(bracket, m)
                        changed = True
                    elif m.player2_ign == "BYE" and m.player1_ign != "BYE" and m.player1_id is not None:
                        m.state = "bye"
                        m.winner_id = m.player1_id
                        m.winner_ign = m.player1_ign
                        cls._advance_winner(bracket, m)
                        cls._drop_bye_loser(bracket, m)
                        changed = True
                    elif m.player1_ign == "BYE" and m.player2_ign == "BYE":
                        m.state = "bye"
                        m.winner_ign = "BYE"
                        cls._advance_winner(bracket, m)
                        cls._drop_bye_loser(bracket, m)
                        changed = True

                # Evaluate READY state: both players present, non-BYE, not yet completed
                if m.state == "pending":
                    p1_valid = m.player1_id is not None or (m.player1_ign not in ("TBD", "BYE"))
                    p2_valid = m.player2_id is not None or (m.player2_ign not in ("TBD", "BYE"))
                    if p1_valid and p2_valid:
                        m.state = "ready"
                        changed = True

    @classmethod
    def _advance_winner(cls, bracket: TournamentBracket, match: BracketMatch) -> None:
        """Places match winner into next match slot."""
        if not match.next_match_id or match.next_match_id not in bracket.matches:
            # Finals complete
            if match.match_id in ("GF", "GF-RESET", f"WB-R{bracket.total_rounds_wb}-M1"):
                bracket.champion_id = match.winner_id
                bracket.champion_ign = match.winner_ign
                bracket.runner_up_id = match.loser_id
                bracket.runner_up_ign = match.loser_ign
            return

        target = bracket.matches[match.next_match_id]
        if match.next_match_slot == 1:
            target.player1_id = match.winner_id
            target.player1_ign = match.winner_ign or "TBD"
            target.player1_clan = match.player1_clan if match.winner_id == match.player1_id else match.player2_clan
            target.player1_checked_in = match.player1_checked_in if match.winner_id == match.player1_id else match.player2_checked_in
        else:
            target.player2_id = match.winner_id
            target.player2_ign = match.winner_ign or "TBD"
            target.player2_clan = match.player1_clan if match.winner_id == match.player1_id else match.player2_clan
            target.player2_checked_in = match.player1_checked_in if match.winner_id == match.player1_id else match.player2_checked_in

    @classmethod
    def _drop_loser(cls, bracket: TournamentBracket, match: BracketMatch) -> None:
        """In Double Elimination, routes loser to their designated Losers Bracket match slot."""
        if not match.loser_match_id or match.loser_match_id not in bracket.matches:
            return
        target = bracket.matches[match.loser_match_id]
        loser_clan = match.player1_clan if match.loser_id == match.player1_id else match.player2_clan
        loser_checked = match.player1_checked_in if match.loser_id == match.player1_id else match.player2_checked_in
        if match.loser_match_slot == 1:
            target.player1_id = match.loser_id
            target.player1_ign = match.loser_ign or "TBD"
            target.player1_clan = loser_clan
            target.player1_checked_in = loser_checked
        else:
            target.player2_id = match.loser_id
            target.player2_ign = match.loser_ign or "TBD"
            target.player2_clan = loser_clan
            target.player2_checked_in = loser_checked

    @classmethod
    def _drop_bye_loser(cls, bracket: TournamentBracket, match: BracketMatch) -> None:
        """In Double Elimination, routes a BYE into the Losers Bracket when a match has no loser."""
        if not match.loser_match_id or match.loser_match_id not in bracket.matches:
            return
        target = bracket.matches[match.loser_match_id]
        if match.loser_match_slot == 1:
            target.player1_id = None
            target.player1_ign = "BYE"
        else:
            target.player2_id = None
            target.player2_ign = "BYE"

    @classmethod
    def report_match(
        cls,
        bracket: TournamentBracket,
        match_id: str,
        winner_id: int,
        score: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[BracketMatch]]:
        """
        Records match result. Winner advances to next match.
        Supports out-of-order execution as long as the match is in 'ready' state.
        """
        if match_id not in bracket.matches:
            return False, f"Match `{match_id}` not found in bracket.", None

        match = bracket.matches[match_id]
        if match.state == "completed":
            return False, f"Match `{match_id}` is already completed. Use undo to revert.", match
        if match.state not in ("ready", "pending"):
            return False, f"Match `{match_id}` is not ready to be played.", match

        # Verify winner is in match
        if winner_id == match.player1_id:
            winner_ign = match.player1_ign
            loser_id = match.player2_id
            loser_ign = match.player2_ign
        elif winner_id == match.player2_id:
            winner_ign = match.player2_ign
            loser_id = match.player1_id
            loser_ign = match.player1_ign
        else:
            return False, f"User <@{winner_id}> is not a participant in match `{match_id}`.", match

        match.winner_id = winner_id
        match.winner_ign = winner_ign
        match.loser_id = loser_id
        match.loser_ign = loser_ign
        match.score = score
        match.state = "completed"

        # Check for Double Elimination Grand Finals Reset rule
        if match.match_id == "GF" and bracket.format == "double":
            # If Losers Bracket champion (slot 2) wins GF Game 1, trigger GF-RESET!
            if winner_id == match.player2_id and "GF-RESET" not in bracket.matches:
                reset_match = BracketMatch(
                    match_id="GF-RESET",
                    section="finals",
                    round_number=match.round_number + 1,
                    match_number=1,
                    player1_id=match.player1_id,
                    player1_ign=match.player1_ign,
                    player2_id=match.player2_id,
                    player2_ign=match.player2_ign,
                    state="ready",
                )
                bracket.matches["GF-RESET"] = reset_match
                cls.evaluate_ready_states(bracket)
                return True, f"⚔️ Losers Bracket Champion **{winner_ign}** won Grand Finals! **Grand Finals Reset Match (Game 2)** triggered!", match

        cls._advance_winner(bracket, match)
        if bracket.format == "double":
            cls._drop_loser(bracket, match)

        cls.evaluate_ready_states(bracket)
        return True, f"✅ Match `{match_id}` completed: **{winner_ign}** won!", match

    @classmethod
    def undo_match(cls, bracket: TournamentBracket, match_id: str) -> Tuple[bool, str]:
        """Reverts a completed match result back to ready."""
        if match_id not in bracket.matches:
            return False, f"Match `{match_id}` not found."

        match = bracket.matches[match_id]
        if match.state != "completed":
            return False, f"Match `{match_id}` is not completed."

        # Check if downstream winner match is already played
        if match.next_match_id and match.next_match_id in bracket.matches:
            downstream = bracket.matches[match.next_match_id]
            if downstream.state == "completed":
                return False, f"Cannot undo `{match_id}`: next match `{downstream.match_id}` has already been completed. Undo that match first."

            # Remove player from downstream
            if match.next_match_slot == 1:
                downstream.player1_id = None
                downstream.player1_ign = "TBD"
                downstream.player1_clan = None
                downstream.player1_checked_in = False
            else:
                downstream.player2_id = None
                downstream.player2_ign = "TBD"
                downstream.player2_clan = None
                downstream.player2_checked_in = False
            downstream.state = "pending"

        # Check if downstream loser match is already played
        if match.loser_match_id and match.loser_match_id in bracket.matches:
            downstream_l = bracket.matches[match.loser_match_id]
            if downstream_l.state == "completed":
                return False, f"Cannot undo `{match_id}`: loser's next match `{downstream_l.match_id}` has already been completed. Undo that match first."

            # Remove loser from downstream
            if match.loser_match_slot == 1:
                downstream_l.player1_id = None
                downstream_l.player1_ign = "TBD"
                downstream_l.player1_clan = None
                downstream_l.player1_checked_in = False
            else:
                downstream_l.player2_id = None
                downstream_l.player2_ign = "TBD"
                downstream_l.player2_clan = None
                downstream_l.player2_checked_in = False
            downstream_l.state = "pending"

        # If this was GF and triggered GF-RESET, clean up GF-RESET
        if match.match_id == "GF" and "GF-RESET" in bracket.matches:
            reset_m = bracket.matches["GF-RESET"]
            if reset_m.state == "completed":
                return False, "Cannot undo `GF`: Grand Finals Reset match has already been completed. Undo `GF-RESET` first."
            del bracket.matches["GF-RESET"]

        # Clear champion if this was finals
        if bracket.champion_id == match.winner_id:
            bracket.champion_id = None
            bracket.champion_ign = None
            bracket.runner_up_id = None
            bracket.runner_up_ign = None

        match.winner_id = None
        match.winner_ign = None
        match.loser_id = None
        match.loser_ign = None
        match.score = None
        match.state = "ready"
        cls.evaluate_ready_states(bracket)
        return True, f"↩️ Match `{match_id}` result reverted to READY."

    @classmethod
    def get_ready_matches(cls, bracket: TournamentBracket) -> List[BracketMatch]:
        """Returns all matches currently ready to be played (ignoring round order)."""
        return [m for m in bracket.matches.values() if m.state == "ready"]
