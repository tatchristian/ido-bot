"""
Unit tests for MatchHistoryService: recording matches, querying, voiding,
player leaderboard calculations, and active win streak tracking.
"""

from pathlib import Path
import pytest
from services.match_history_service import MatchHistoryService
from utils.storage import StorageManager


def test_record_and_get_matches(tmp_path: Path):
    storage = StorageManager(tmp_path / "test_matches.json")
    service = MatchHistoryService(storage=storage)

    # 1. Record matches
    m1 = service.record_match(
        winner_id=101,
        winner_ign="Typal_BFC",
        winner_clan="Blue Fire",
        loser_id=102,
        loser_ign="TRWinner129",
        loser_clan="MIZU",
        score="2 - 1",
        tournament_name="Asia Tournament",
        round_name="Round 1",
    )
    assert m1.winner_ign == "Typal_BFC"
    assert m1.score == "2 - 1"

    m2 = service.record_match(
        winner_id=103,
        winner_ign="Spider",
        winner_clan="Yume",
        loser_id=104,
        loser_ign="DaFlowSta_Og",
        loser_clan="KAZE",
        score="2 - 0",
        tournament_name="Asia Tournament",
        round_name="Round 1",
    )

    # 2. Query all matches
    all_matches = service.get_matches()
    assert len(all_matches) == 2
    # Newest first
    assert all_matches[0].winner_ign == "Spider"
    assert all_matches[1].winner_ign == "Typal_BFC"

    # 3. Filter by player
    typal_matches = service.get_matches(player_id=101)
    assert len(typal_matches) == 1
    assert typal_matches[0].match_id == m1.match_id

    # 4. Filter by clan
    yume_matches = service.get_matches(clan="Yume")
    assert len(yume_matches) == 1
    assert yume_matches[0].match_id == m2.match_id


def test_void_match(tmp_path: Path):
    storage = StorageManager(tmp_path / "test_matches.json")
    service = MatchHistoryService(storage=storage)

    m = service.record_match(
        winner_id=101,
        winner_ign="Typal_BFC",
        loser_id=102,
        loser_ign="TRWinner129",
    )

    # Void the match
    assert service.void_match(m.match_id, reason="Score dispute resolved") is True
    assert service.get_matches(include_void=False) == []

    void_matches = service.get_matches(include_void=True)
    assert len(void_matches) == 1
    assert void_matches[0].is_void is True
    assert void_matches[0].void_reason == "Score dispute resolved"


def test_player_stats_and_streaks(tmp_path: Path):
    storage = StorageManager(tmp_path / "test_matches.json")
    service = MatchHistoryService(storage=storage)

    # Player 1 wins 3 in a row
    service.record_match(1, "DaFlow", 2, "Spider", winner_clan="KAZE", loser_clan="Yume")
    service.record_match(1, "DaFlow", 3, "Typal", winner_clan="KAZE", loser_clan="Blue Fire")
    service.record_match(1, "DaFlow", 4, "Zumbo", winner_clan="KAZE")

    # Player 2 wins 1, then loses
    service.record_match(2, "Spider", 5, "nxve", winner_clan="Yume")
    service.record_match(3, "Typal", 2, "Spider", winner_clan="Blue Fire", loser_clan="Yume")

    stats = service.get_player_stats()
    assert len(stats) >= 4

    # DaFlow should be #1 with 3W 0L and 3 streak
    top = stats[0]
    assert top["ign"] == "DaFlow"
    assert top["wins"] == 3
    assert top["losses"] == 0
    assert top["streak"] == 3
    assert top["clan"] == "KAZE"

    # Spider should have 1W 2L and 0 streak (lost last match)
    spider = next(p for p in stats if p["ign"] == "Spider")
    assert spider["wins"] == 1
    assert spider["losses"] == 2
    assert spider["streak"] == 0


@pytest.mark.asyncio
async def test_supabase_sync_helpers(tmp_path: Path):
    from unittest.mock import patch, MagicMock

    storage = StorageManager(tmp_path / "test_matches.json")
    service = MatchHistoryService(
        storage=storage,
        supabase_url="https://mockproject.supabase.co",
        supabase_key="mockanonkey",
    )
    assert service.has_supabase is True

    # Test sync_match_to_supabase
    record = service.record_match(
        winner_id=1,
        winner_ign="Winner",
        loser_id=2,
        loser_ign="Loser",
    )

    class MockResponse:
        def __init__(self, status, data=None):
            self.status = status
            self._data = data

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def json(self):
            return self._data or []

        async def text(self):
            return ""

    with patch("aiohttp.ClientSession.post", return_value=MockResponse(201)):
        ok = await service.sync_match_to_supabase(record)
        assert ok is True

    with patch("aiohttp.ClientSession.patch", return_value=MockResponse(204)):
        void_ok = await service.sync_void_to_supabase(record.match_id, "Mistake")
        assert void_ok is True

    mock_cloud_data = [
        {
            "match_id": "M-CLOUD-1",
            "tournament_name": "Cloud Cup",
            "guild_id": 0,
            "winner_id": 99,
            "winner_ign": "CloudPlayer",
            "loser_id": 88,
            "loser_ign": "LocalPlayer",
            "completed_at": "2026-11-17T12:00:00Z",
        }
    ]
    with patch("aiohttp.ClientSession.get", return_value=MockResponse(200, mock_cloud_data)):
        pulled = await service.sync_from_supabase()
        assert pulled == 1
        assert any(m.match_id == "M-CLOUD-1" for m in service.get_matches())


@pytest.mark.asyncio
async def test_supabase_connectivity_no_creds(tmp_path: Path):
    storage = StorageManager(tmp_path / "test_matches.json")
    service = MatchHistoryService(storage=storage, supabase_url="", supabase_key="")
    ok, msg, metrics = await service.test_supabase_connectivity()
    assert ok is False
    assert "not configured" in msg


@pytest.mark.asyncio
async def test_supabase_connectivity_mock_probe(tmp_path: Path):
    from unittest.mock import patch

    storage = StorageManager(tmp_path / "test_matches.json")
    service = MatchHistoryService(
        storage=storage,
        supabase_url="https://mock.supabase.co",
        supabase_key="mock-key",
    )

    class MockProbeResponse:
        def __init__(self, status=200, data=None):
            self.status = status
            self._data = data

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def json(self):
            return self._data or []

        async def text(self):
            return ""

    with patch("aiohttp.ClientSession.post", return_value=MockProbeResponse(201)), \
         patch("aiohttp.ClientSession.get", return_value=MockProbeResponse(200, [{"match_id": "TEST_probe"}])), \
         patch("aiohttp.ClientSession.patch", return_value=MockProbeResponse(204)), \
         patch("aiohttp.ClientSession.delete", return_value=MockProbeResponse(204)), \
         patch("uuid.uuid4") as mock_uuid:
        mock_uuid.return_value.hex = "probe12345678"
        expected_id = f"TEST_{'probe12345678'[:8]}"
        with patch("aiohttp.ClientSession.get", return_value=MockProbeResponse(200, [{"match_id": expected_id}])):
            ok, msg, metrics = await service.test_supabase_connectivity()
        assert ok is True
        assert "verified successfully" in msg
        assert "insert_ms" in metrics
        assert "query_ms" in metrics
        assert "patch_ms" in metrics
        assert "delete_ms" in metrics
