"""
Match History Service
Permanently records, indexes, queries, and aggregates completed tournament and scrim duels.
Provides cumulative ledger data for Herald bot integration and web leaderboard sync.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from config import config
from utils.storage import StorageManager

logger = logging.getLogger("uda_bot.match_history")


@dataclass
class MatchRecord:
    match_id: str
    tournament_name: str
    guild_id: int
    winner_id: int
    winner_ign: str
    loser_id: int
    loser_ign: str
    winner_clan: Optional[str] = None
    loser_clan: Optional[str] = None
    score: Optional[str] = None
    round_name: str = "Match"
    bracket_format: str = "single"
    match_type: str = "tournament"  # "tournament" or "scrim"
    recorded_by: Optional[int] = None
    completed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    is_void: bool = False
    void_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MatchRecord:
        known_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in known_keys}
        return cls(**filtered)


class MatchHistoryService:
    """
    Manages the permanent historical log of all matches played across all tournaments.
    Provides filtering, player statistics, winning streak tracking, and REST payloads.
    """

    def __init__(
        self,
        storage: Optional[StorageManager] = None,
        data_dir: Optional[Path] = None,
        file_name: str = "match_history.json",
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ):
        base_dir = Path(data_dir or (storage.file_path.parent if storage else "data"))
        self.storage = storage or StorageManager(
            file_path=base_dir / file_name,
            backup_dir=base_dir / "backups",
            max_backups=20,
            min_backup_interval=60.0,
        )
        self.supabase_url = (supabase_url or config.supabase_url or "").rstrip("/")
        self.supabase_key = supabase_key or config.supabase_key or ""
        self._matches: List[MatchRecord] = []
        self._load()

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    async def sync_from_supabase(self) -> int:
        """Pulls match records from Supabase into memory and local cache."""
        if not self.has_supabase:
            return 0
        url = f"{self.supabase_url}/rest/v1/tournament_matches?select=*&order=completed_at.desc"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Accept": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8.0)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        existing_ids = {m.match_id for m in self._matches}
                        count = 0
                        for row in data:
                            rec = MatchRecord.from_dict(row)
                            if rec.match_id not in existing_ids:
                                self._matches.append(rec)
                                existing_ids.add(rec.match_id)
                                count += 1
                        if count > 0:
                            self._matches.sort(key=lambda m: m.completed_at)
                            self._persist()
                        logger.info("Synced %d new matches from Supabase cloud.", count)
                        return count
                    else:
                        logger.warning("Supabase pull returned HTTP %s", resp.status)
        except Exception as exc:
            logger.warning("Failed to sync from Supabase: %s", exc)
        return 0

    async def sync_match_to_supabase(self, record: MatchRecord) -> bool:
        """Pushes a single recorded match to Supabase."""
        if not self.has_supabase:
            return False
        url = f"{self.supabase_url}/rest/v1/tournament_matches"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=record.to_dict(), timeout=aiohttp.ClientTimeout(total=8.0)) as resp:
                    if resp.status in (200, 201):
                        logger.info("Successfully pushed match %s to Supabase.", record.match_id)
                        return True
                    else:
                        text = await resp.text()
                        logger.warning("Supabase insert returned HTTP %s: %s", resp.status, text)
        except Exception as exc:
            logger.warning("Failed to push match %s to Supabase: %s", record.match_id, exc)
        return False

    async def sync_void_to_supabase(self, match_id: str, reason: str) -> bool:
        """Updates a match's is_void status on Supabase."""
        if not self.has_supabase:
            return False
        url = f"{self.supabase_url}/rest/v1/tournament_matches?match_id=eq.{match_id}"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        payload = {"is_void": True, "void_reason": reason}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.patch(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=8.0)) as resp:
                    return resp.status in (200, 204)
        except Exception as exc:
            logger.warning("Failed to void match %s on Supabase: %s", match_id, exc)
        return False

    def _load(self) -> None:
        data = self.storage.load(default_factory=lambda: {"matches": []})
        raw_list = data.get("matches", [])
        self._matches = []
        for m in raw_list:
            try:
                self._matches.append(MatchRecord.from_dict(m))
            except Exception as exc:
                logger.warning("Could not parse match record: %s (error: %s)", m, exc)

    def _persist(self, force_backup: bool = False) -> None:
        payload = {"matches": [m.to_dict() for m in self._matches]}
        self.storage.save(payload, force_backup=force_backup)

    def record_match(
        self,
        winner_id: int,
        winner_ign: str,
        loser_id: int,
        loser_ign: str,
        tournament_name: str = "Tournament",
        guild_id: int = 0,
        winner_clan: Optional[str] = None,
        loser_clan: Optional[str] = None,
        score: Optional[str] = None,
        round_name: str = "Match",
        bracket_format: str = "single",
        match_type: str = "tournament",
        recorded_by: Optional[int] = None,
        match_id: Optional[str] = None,
    ) -> MatchRecord:
        """Records a completed duel into permanent match history."""
        m_id = match_id or f"M-{uuid.uuid4().hex[:10]}"
        record = MatchRecord(
            match_id=m_id,
            tournament_name=tournament_name,
            guild_id=guild_id,
            winner_id=winner_id,
            winner_ign=winner_ign,
            loser_id=loser_id,
            loser_ign=loser_ign,
            winner_clan=winner_clan,
            loser_clan=loser_clan,
            score=score,
            round_name=round_name,
            bracket_format=bracket_format,
            match_type=match_type,
            recorded_by=recorded_by,
        )
        self._matches.append(record)
        self._persist()
        if self.has_supabase:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.sync_match_to_supabase(record))
            except RuntimeError:
                pass
        logger.info(
            "Match recorded: %s defeated %s (%s) in %s [%s]",
            winner_ign,
            loser_ign,
            score or "N/A",
            tournament_name,
            m_id,
        )
        return record

    def void_match(self, match_id: str, reason: str = "") -> bool:
        """Marks a match as voided (soft-delete) so consumers like Herald can revert rewards."""
        for m in self._matches:
            if m.match_id == match_id:
                m.is_void = True
                m.void_reason = reason or "Voided by staff"
                self._persist(force_backup=True)
                if self.has_supabase:
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self.sync_void_to_supabase(match_id, m.void_reason or ""))
                    except RuntimeError:
                        pass
                logger.info("Match %s voided: %s", match_id, reason)
                return True
        return False

    def get_matches(
        self,
        tournament_name: Optional[str] = None,
        player_id: Optional[int] = None,
        clan: Optional[str] = None,
        since: Optional[str] = None,
        include_void: bool = False,
        limit: int = 100,
    ) -> List[MatchRecord]:
        """Queries match records with optional filters."""
        results: List[MatchRecord] = []
        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except Exception:
                since_dt = None

        # Iterate reverse chronological (newest first)
        for m in reversed(self._matches):
            if not include_void and m.is_void:
                continue
            if tournament_name and tournament_name.lower() not in m.tournament_name.lower():
                continue
            if player_id and m.winner_id != player_id and m.loser_id != player_id:
                continue
            if clan:
                w_clan = (m.winner_clan or "").lower()
                l_clan = (m.loser_clan or "").lower()
                target_clan = clan.lower()
                if target_clan != w_clan and target_clan != l_clan:
                    continue
            if since_dt:
                try:
                    m_dt = datetime.fromisoformat(m.completed_at.replace("Z", "+00:00"))
                    if m_dt <= since_dt:
                        continue
                except Exception:
                    pass

            results.append(m)
            if len(results) >= limit:
                break

        return results

    def get_player_stats(self, guild_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Computes all-time duelist stats: wins, losses, win rate, and active win streaks.
        Matches the 'Duelists (Wins)' leaderboard structure.
        """
        stats: Dict[int, Dict[str, Any]] = {}

        for m in self._matches:
            if m.is_void:
                continue
            if guild_id is not None and guild_id != 0 and m.guild_id != guild_id:
                continue

            # Winner tracking
            w_id = m.winner_id
            if w_id not in stats:
                stats[w_id] = {
                    "discord_id": w_id,
                    "ign": m.winner_ign,
                    "clan": m.winner_clan or "None",
                    "wins": 0,
                    "losses": 0,
                    "streak": 0,
                }
            stats[w_id]["wins"] += 1
            stats[w_id]["streak"] += 1
            if m.winner_clan:
                stats[w_id]["clan"] = m.winner_clan
            stats[w_id]["ign"] = m.winner_ign

            # Loser tracking
            l_id = m.loser_id
            if l_id not in stats:
                stats[l_id] = {
                    "discord_id": l_id,
                    "ign": m.loser_ign,
                    "clan": m.loser_clan or "None",
                    "wins": 0,
                    "losses": 0,
                    "streak": 0,
                }
            stats[l_id]["losses"] += 1
            stats[l_id]["streak"] = 0  # Streak broken
            if m.loser_clan:
                stats[l_id]["clan"] = m.loser_clan
            stats[l_id]["ign"] = m.loser_ign

        leaderboard = list(stats.values())
        leaderboard.sort(key=lambda p: (p["wins"], -p["losses"]), reverse=True)
        return leaderboard
