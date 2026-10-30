"""
Past Tournament Results Service
Persists and manages completed tournament history, champions, runner-ups,
and final bracket scores for display on https://unitedduelingamity.org.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import config
from utils.storage import StorageManager

logger = logging.getLogger("uda_bot.past_results")


@dataclass
class PastResult:
    id: str
    name: str
    date: str  # YYYY-MM-DD
    champion: str
    runner_up: str = ""
    score: str = ""
    type: str = "Tournament"
    description: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PastResult:
        return cls(
            id=str(data.get("id", str(uuid.uuid4()))),
            name=str(data.get("name", "Unnamed Event")),
            date=str(data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))),
            champion=str(data.get("champion", "TBD")),
            runner_up=str(data.get("runner_up", "")),
            score=str(data.get("score", "")),
            type=str(data.get("type", "Tournament")),
            description=str(data.get("description", "")),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PastResultsService:
    """
    Manages tournament archives, champions, and scores.
    """

    def __init__(
        self,
        storage: Optional[StorageManager] = None,
        data_dir: Optional[Path] = None,
    ):
        self.data_dir = Path(data_dir or config.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage = storage or StorageManager(
            file_path=self.data_dir / "past_results.json",
            backup_dir=self.data_dir / "backups",
            max_backups=config.max_backups,
        )
        self._results: Dict[str, PastResult] = {}
        self._load()

    def _load(self):
        data = self.storage.load(default_factory=lambda: {"results": []})
        for item in data.get("results", []):
            res = PastResult.from_dict(item)
            self._results[res.id] = res

    def _persist(self):
        self.storage.save({"results": [r.to_dict() for r in self._results.values()]})

    def add_result(
        self,
        name: str,
        champion: str,
        date: Optional[str] = None,
        runner_up: str = "",
        score: str = "",
        type_str: str = "Tournament",
        description: str = "",
    ) -> PastResult:
        date_clean = (
            date.strip()
            if date
            else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        res = PastResult(
            id=str(uuid.uuid4())[:8],
            name=name.strip(),
            date=date_clean,
            champion=champion.strip(),
            runner_up=runner_up.strip(),
            score=score.strip(),
            type=type_str.strip() or "Tournament",
            description=description.strip(),
        )
        self._results[res.id] = res
        self._persist()
        return res

    def remove_result(self, query: str) -> Optional[PastResult]:
        """Removes a result by ID or exact/fuzzy name."""
        q = query.strip().lower()
        if query in self._results:
            res = self._results.pop(query)
            self._persist()
            return res

        for res_id, res in list(self._results.items()):
            if res.name.lower() == q or res.id.lower() == q:
                del self._results[res_id]
                self._persist()
                return res

        for res_id, res in list(self._results.items()):
            if q in res.name.lower():
                del self._results[res_id]
                self._persist()
                return res

        return None

    def get_all_results(self) -> List[PastResult]:
        """Returns all past results sorted chronologically descending."""
        results = list(self._results.values())
        results.sort(key=lambda r: r.date, reverse=True)
        return results

