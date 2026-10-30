"""
Unit tests for the public REST API endpoints serving https://unitedduelingamity.org.
Tests CORS headers, preflight OPTIONS, and JSON formatting for:
- /tournaments
- /leaderboard & /clans
- /players
- /health & /
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from services.api_server import CORS_HEADERS, create_api_app
from services.clan_showcase_service import ClanSubmission
from services.tournament_service import Participant, TournamentState


class DummyGuild:
    def __init__(self, name="UDA Main Server"):
        self.name = name
        self.scheduled_events = []


class DummyEvent:
    def __init__(self, name, start_time, description="", status="scheduled", event_id=123):
        self.id = event_id
        self.name = name
        self.start_time = start_time
        self.description = description
        self.status = status
        self.url = f"https://discord.com/events/123/{event_id}"


class DummyBot:
    def __init__(self):
        self.guilds = []
        self.tournament_service = MagicMock()
        self.tournament_service._guild_states = {}
        self.clan_showcase_service = MagicMock()
        self.clan_showcase_service._submissions = {}


class TestApiServer(AioHTTPTestCase):
    async def get_application(self):
        self.bot = DummyBot()
        return create_api_app(self.bot)

    @unittest_run_loop
    async def test_health_check_returns_ok_with_cors(self):
        resp = await self.client.get("/health")
        assert resp.status == 200
        text = await resp.text()
        assert "UDA Duke Bot API is operational" in text
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"

    @unittest_run_loop
    async def test_options_preflight_returns_204_with_cors(self):
        resp = await self.client.options("/tournaments")
        assert resp.status == 204
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"
        assert "GET" in resp.headers.get("Access-Control-Allow-Methods", "")

    @unittest_run_loop
    async def test_tournaments_empty_list_initially(self):
        resp = await self.client.get("/tournaments")
        assert resp.status == 200
        data = await resp.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @unittest_run_loop
    async def test_tournaments_scheduled_events_and_states(self):
        # Setup scheduled Discord event
        guild = DummyGuild()
        event_time = datetime(2026, 11, 8, 18, 0, tzinfo=timezone.utc)
        guild.scheduled_events.append(
            DummyEvent("Autumn Clan Cup", event_time, "Best of 3 clan battle.")
        )
        self.bot.guilds.append(guild)

        # Setup active tournament state
        state = TournamentState(name="Winter Amity Open", created_at="2026-12-01T12:00:00Z")
        state.participants.append(
            Participant(user_id=1, user_mention="<@1>", ign="ShadowBlade", weapon="Katana", region="NA")
        )
        self.bot.tournament_service._guild_states[12345] = state

        resp = await self.client.get("/tournaments")
        assert resp.status == 200
        data = await resp.json()
        assert len(data) == 2

        # Verify exact schema expected by script.js: name, date, type, description
        ev1 = next(e for e in data if e["name"] == "Autumn Clan Cup")
        assert ev1["date"] == "2026-11-08"
        assert ev1["type"] == "Clan Cup"
        assert "Best of 3" in ev1["description"]

        ev2 = next(e for e in data if e["name"] == "Winter Amity Open")
        assert ev2["date"] == "2026-12-01"
        assert ev2["type"] == "Championship"

    @unittest_run_loop
    async def test_leaderboard_and_clans_endpoint(self):
        # Add approved and pending clans
        sub1 = ClanSubmission(
            id="sub-1",
            guild_id=100,
            applicant_id=200,
            applicant_name="LeaderOne",
            clan_name="Cerberus Elite",
            color_hex="#10b981",
            color_int=0x10B981,
            metadata_text="NA | Founded 2026",
            description_text="Top dueling squad.",
            activities_motto="Victory through unity.",
            logo_url="https://i.imgur.com/logo1.png",
            status="approved",
        )
        sub1.banner_points = 350

        sub2 = ClanSubmission(
            id="sub-2",
            guild_id=100,
            applicant_id=201,
            applicant_name="LeaderTwo",
            clan_name="Pending Clan",
            color_hex="#ffffff",
            color_int=0xFFFFFF,
            metadata_text="",
            description_text="",
            activities_motto="",
            logo_url="",
            status="pending",
        )

        self.bot.clan_showcase_service._submissions = {
            "sub-1": sub1,
            "sub-2": sub2,
        }

        # Test /leaderboard
        resp = await self.client.get("/leaderboard")
        assert resp.status == 200
        data = await resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Cerberus Elite"
        assert data[0]["score"] == 350
        assert data[0]["color_hex"] == "#10b981"
        assert data[0]["logo_url"] == "https://i.imgur.com/logo1.png"

        # Test /clans alias
        resp_alias = await self.client.get("/clans")
        assert resp_alias.status == 200
        data_alias = await resp_alias.json()
        assert data_alias == data

    @unittest_run_loop
    async def test_players_endpoint(self):
        state = TournamentState(name="Test Cup")
        state.participants.append(
            Participant(user_id=101, user_mention="<@101>", ign="Viper", weapon="Daggers", region="EU")
        )
        state.participants.append(
            Participant(user_id=102, user_mention="<@102>", ign="Kensei", weapon="Katana", region="NA")
        )
        self.bot.tournament_service._guild_states[999] = state

        resp = await self.client.get("/players")
        assert resp.status == 200
        data = await resp.json()
        assert len(data) == 2
        # script.js expects name and score
        assert any(p["name"] == "Viper" and p["score"] == 1000 for p in data)
        assert any(p["name"] == "Kensei" and p["score"] == 1000 for p in data)

    @unittest_run_loop
    async def test_canceled_and_completed_events_excluded_from_upcoming(self):
        guild = DummyGuild()
        now = datetime.now(timezone.utc)
        guild.scheduled_events.append(
            DummyEvent("Active Cup", now, status="scheduled", event_id=1)
        )
        guild.scheduled_events.append(
            DummyEvent("Canceled Cup", now, status="canceled", event_id=2)
        )
        guild.scheduled_events.append(
            DummyEvent("Finished Cup", now, status="completed", event_id=3)
        )
        self.bot.guilds.append(guild)

        resp = await self.client.get("/tournaments")
        assert resp.status == 200
        data = await resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Active Cup"

    @unittest_run_loop
    async def test_past_results_endpoint(self):
        from services.past_results_service import PastResultsService
        storage = MagicMock()
        storage.load.return_value = {"results": []}
        past_svc = PastResultsService(storage=storage)
        past_svc._results.clear()
        past_svc.add_result(
            name="Autumn Clan Cup 2026",
            champion="Cerberus Elite",
            date="2026-10-15",
            runner_up="Shadow Syndicate",
            score="3 - 1",
            type_str="Clan Cup",
            description="Championship Finals",
        )
        self.bot.past_results_service = past_svc

        resp = await self.client.get("/past-results")
        assert resp.status == 200
        data = await resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Autumn Clan Cup 2026"
        assert data[0]["champion"] == "Cerberus Elite"
        assert data[0]["runner_up"] == "Shadow Syndicate"
        assert data[0]["score"] == "3 - 1"

        # Check alias
        resp_alias = await self.client.get("/tournaments/past")
        assert resp_alias.status == 200
        data_alias = await resp_alias.json()
        assert data_alias == data
