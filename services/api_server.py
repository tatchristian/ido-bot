"""
Public Web REST API Server for United Dueling Amity (UDA).
Provides live JSON endpoints for https://unitedduelingamity.org:
- GET /tournaments : Upcoming and active tournament events
- GET /past-results (alias /tournaments/past) : Historical champions and match scores
- GET /leaderboard (alias /clans) : Approved clan standings and Banner Points
- GET /players     : Registered player roster and competitive ratings
- GET /health (or /) : Service health check for Railway/Koyeb deployments
Includes full CORS support for browser access from unitedduelingamity.org.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aiohttp import web

logger = logging.getLogger("uda_bot.api_server")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
}


def create_api_app(bot: Any) -> web.Application:
    """
    Constructs an aiohttp web application configured with CORS
    and routes for tournaments, clans, and players.
    """
    app = web.Application()

    async def preflight_handler(request: web.Request) -> web.Response:
        """Handles HTTP OPTIONS preflight requests from browsers."""
        return web.Response(status=204, headers=CORS_HEADERS)

    async def health_handler(request: web.Request) -> web.Response:
        """Health check endpoint for cloud platforms (Railway, Koyeb, Docker)."""
        return web.Response(
            text="UDA Duke Bot API is operational!",
            content_type="text/plain",
            headers=CORS_HEADERS,
        )

    async def tournaments_handler(request: web.Request) -> web.Response:
        """
        Returns a list of tournament events for script.js to render.
        Format expected by https://unitedduelingamity.org:
        [
          {
            "id": "123456789",
            "name": "Autumn Clan Cup",
            "date": "2026-11-08",
            "type": "Clan Cup",
            "description": "Best of 3."
          }
        ]
        """
        events: List[Dict[str, Any]] = []

        # Collect names of concluded/past results to prevent them from showing as upcoming
        concluded_names = set()
        past_service = getattr(bot, "past_results_service", None)
        if past_service:
            try:
                concluded_names = {r.name.strip().lower() for r in past_service.get_all_results() if r.name}
            except Exception as exc:
                logger.debug("Could not read concluded events: %s", exc)

        # 1. Inspect native Discord Scheduled Events from connected guilds
        if hasattr(bot, "guilds"):
            for guild in bot.guilds:
                try:
                    for ev in getattr(guild, "scheduled_events", []):
                        # Filter out canceled or completed events
                        status_str = str(getattr(ev, "status", "")).lower()
                        if "cancel" in status_str or "complete" in status_str or "ended" in status_str:
                            continue
                        if ev.name.strip().lower() in concluded_names:
                            continue

                        # Extract YYYY-MM-DD date required by script.js date parser
                        start_date = (
                            ev.start_time.strftime("%Y-%m-%d")
                            if ev.start_time
                            else datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        )
                        ev_type = "Clan Cup" if "clan" in ev.name.lower() else "Tournament"
                        events.append({
                            "id": str(ev.id),
                            "name": ev.name,
                            "date": start_date,
                            "type": ev_type,
                            "description": (ev.description or "Official UDA Tournament Event").strip()[:300],
                            "url": ev.url if hasattr(ev, "url") else None,
                        })
                except Exception as exc:
                    logger.debug("Could not read scheduled events for guild %s: %s", guild, exc)

        # 2. Inspect active tournament states from TournamentService
        if hasattr(bot, "tournament_service"):
            states = getattr(bot.tournament_service, "_states", getattr(bot.tournament_service, "_guild_states", {}))
            for gid, state in states.items():
                if getattr(state, "event_canceled", False):
                    continue
                if state.name.strip().lower() in concluded_names:
                    continue
                if state.participants or state.main_open or state.subs_open:
                    event_date = (
                        state.start_time[:10]
                        if getattr(state, "start_time", None)
                        else (
                            state.created_at[:10]
                            if getattr(state, "created_at", None)
                            else datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        )
                    )
                    # Don't duplicate if already listed in scheduled events
                    if not any(e["name"].lower() == state.name.lower() for e in events):
                        events.append({
                            "id": f"guild-{gid}",
                            "name": state.name,
                            "date": event_date,
                            "type": "Championship",
                            "description": f"Slots: {len(state.participants)}/{state.max_slots} | Regions: {', '.join(state.allowed_regions)}",
                        })

        # Sort chronologically by date
        events.sort(key=lambda x: str(x.get("date", "")))
        return web.json_response(events, headers=CORS_HEADERS)

    async def past_results_handler(request: web.Request) -> web.Response:
        """
        Returns past tournament results, champions, runner-ups, and final scores.
        Format:
        [
          {
            "id": "1a2b3c4d",
            "name": "Autumn Clan Cup",
            "date": "2026-11-08",
            "champion": "Cerberus Elite",
            "runner_up": "Shadow Syndicate",
            "score": "3 - 1",
            "type": "Clan Cup",
            "description": "Final bracket showdown"
          }
        ]
        """
        past_service = getattr(bot, "past_results_service", None)
        if not past_service:
            from services.past_results_service import PastResultsService
            past_service = PastResultsService()
            bot.past_results_service = past_service

        results = [r.to_dict() for r in past_service.get_all_results()]
        return web.json_response(results, headers=CORS_HEADERS)

    async def leaderboard_handler(request: web.Request) -> web.Response:
        """
        Returns approved clans with Banner Points for the clan leaderboard.
        Format expected by script.js:
        [
          {
            "name": "Clan One",
            "score": 250
          }
        ]
        """
        clans: List[Dict[str, Any]] = []

        # Read approved clans from ClanShowcaseService
        showcase_service = getattr(bot, "clan_showcase_service", None)
        if showcase_service and hasattr(showcase_service, "_submissions"):
            for sub in showcase_service._submissions.values():
                if sub.status == "approved":
                    clans.append({
                        "name": sub.clan_name,
                        "score": getattr(sub, "banner_points", 0),
                        "logo_url": sub.logo_url,
                        "color_hex": sub.color_hex,
                        "metadata": sub.metadata_text,
                        "description": sub.description_text,
                        "motto": sub.activities_motto,
                    })

        # Sort descending by score
        clans.sort(key=lambda c: int(c.get("score", 0)), reverse=True)
        return web.json_response(clans, headers=CORS_HEADERS)

    async def players_handler(request: web.Request) -> web.Response:
        """
        Returns registered players and their competitive ratings.
        Format expected by script.js:
        [
          {
            "name": "Player One",
            "score": 2150
          }
        ]
        """
        players: List[Dict[str, Any]] = []
        seen_igns = set()

        if hasattr(bot, "tournament_service"):
            states = getattr(bot.tournament_service, "_states", getattr(bot.tournament_service, "_guild_states", {}))
            for state in states.values():
                for p in getattr(state, "participants", []):
                    if p.ign and p.ign not in seen_igns:
                        seen_igns.add(p.ign)
                        players.append({
                            "name": p.ign,
                            "score": 1000,  # Baseline starting rating
                            "weapon": p.weapon,
                            "region": p.region,
                        })

        players.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
        return web.json_response(players, headers=CORS_HEADERS)

    async def matches_handler(request: web.Request) -> web.Response:
        """
        Returns completed match records for Herald or website consumption.
        Supports query parameters: ?since=...&player=...&clan=...&tournament=...&limit=...
        """
        match_service = getattr(bot, "match_history_service", None)
        if not match_service:
            return web.json_response([], headers=CORS_HEADERS)

        params = request.query
        since = params.get("since")
        clan = params.get("clan")
        tourney = params.get("tournament")
        limit_str = params.get("limit", "100")
        try:
            limit = min(int(limit_str), 500)
        except ValueError:
            limit = 100

        player_id = None
        player_param = params.get("player")
        if player_param and player_param.strip().isdigit():
            player_id = int(player_param.strip())

        matches = match_service.get_matches(
            tournament_name=tourney,
            player_id=player_id,
            clan=clan,
            since=since,
            limit=limit,
        )
        return web.json_response([m.to_dict() for m in matches], headers=CORS_HEADERS)

    async def match_stats_handler(request: web.Request) -> web.Response:
        """Returns aggregated duelist win records and streaks for leaderboards."""
        match_service = getattr(bot, "match_history_service", None)
        if not match_service:
            return web.json_response([], headers=CORS_HEADERS)
        stats = match_service.get_player_stats()
        return web.json_response(stats, headers=CORS_HEADERS)

    async def bracket_image_handler(request: web.Request) -> web.Response:
        """Returns the visual tournament bracket tree rendered as a PNG image."""
        from utils.bracket_renderer import BracketImageRenderer
        t_service = getattr(bot, "tournament_service", None)
        if not t_service:
            return web.Response(status=404, text="Tournament service not available.", headers=CORS_HEADERS)

        section = request.query.get("section", "winners")
        guild_id = 0
        if "guild_id" in request.query and request.query["guild_id"].isdigit():
            guild_id = int(request.query["guild_id"])
        elif hasattr(t_service, "_guild_states") and t_service._guild_states:
            guild_id = next(iter(t_service._guild_states.keys()))

        bracket = t_service.get_bracket(guild_id)
        state = t_service.get_state(guild_id)
        buf = BracketImageRenderer.render(bracket, state.name, section)
        headers = dict(CORS_HEADERS)
        headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return web.Response(body=buf.getvalue(), content_type="image/png", headers=headers)

    # Register Routes
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/tournaments", tournaments_handler)
    app.router.add_get("/past-results", past_results_handler)
    app.router.add_get("/tournaments/past", past_results_handler)
    app.router.add_get("/leaderboard", leaderboard_handler)
    app.router.add_get("/clans", leaderboard_handler)
    app.router.add_get("/players", players_handler)
    app.router.add_get("/matches", matches_handler)
    app.router.add_get("/api/matches", matches_handler)
    app.router.add_get("/matches/stats", match_stats_handler)
    app.router.add_get("/api/matches/stats", match_stats_handler)
    app.router.add_get("/bracket/image", bracket_image_handler)
    app.router.add_get("/api/bracket/image", bracket_image_handler)

    # CORS Preflight OPTIONS routes
    app.router.add_route("OPTIONS", "/{tail:.*}", preflight_handler)

    return app
