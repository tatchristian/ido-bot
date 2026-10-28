"""
Unit tests for the Tournament Section Builder service.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

from services.server_builder import (
    TOURNAMENT_SECTION_SPEC,
    build_tournament_section,
    delete_tournament_section,
)


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_tournament_section_spec_structure():
    """Validates categories and required channel roles in the specification."""
    cat_names = [group["category"] for group in TOURNAMENT_SECTION_SPEC]
    assert "🏆 TOURNAMENT HUB 🏆" in cat_names
    assert "⚔️ MATCH ARENAS ⚔️" in cat_names
    assert "🔒 TOURNAMENT OPERATIONS" in cat_names

    # Check key role mappings exist
    hub = next(g for g in TOURNAMENT_SECTION_SPEC if g["category"] == "🏆 TOURNAMENT HUB 🏆")
    hub_ch_names = [ch["name"] for ch in hub["channels"]]
    assert "📣・tournament-announcements" in hub_ch_names
    assert "✅・tournament-checkin" in hub_ch_names
    assert "🛡️・substitutes-bench" in hub_ch_names
    assert "📝・tournament-registration" in hub_ch_names


def test_build_tournament_section_missing_permissions():
    guild = MagicMock()
    bot_member = MagicMock()
    bot_member.guild_permissions.manage_channels = False
    guild.me = bot_member

    results = run_async(build_tournament_section(guild, delay=0))
    assert len(results["errors"]) == 1
    assert "missing" in results["errors"][0].lower()


def test_build_tournament_section_success_and_channel_mapping():
    guild = MagicMock()
    bot_member = MagicMock()
    bot_member.guild_permissions.manage_channels = True
    guild.me = bot_member
    guild.features = ["COMMUNITY"]
    guild.default_role = MagicMock()

    guild.categories = []
    guild.channels = []

    channel_id_counter = 1000

    # Mock creation coroutines
    async def fake_create_category(name, **kwargs):
        cat = MagicMock()
        cat.name = name
        cat.channels = []
        guild.categories.append(cat)
        return cat

    async def fake_create_text(name, category=None, news=False, **kwargs):
        nonlocal channel_id_counter
        channel_id_counter += 1
        ch = MagicMock()
        ch.id = channel_id_counter
        ch.name = name
        ch.category = category
        if category:
            category.channels.append(ch)
        guild.channels.append(ch)
        return ch

    async def fake_create_voice(name, category=None, user_limit=0, **kwargs):
        nonlocal channel_id_counter
        channel_id_counter += 1
        ch = MagicMock()
        ch.id = channel_id_counter
        ch.name = name
        ch.category = category
        ch.user_limit = user_limit
        if category:
            category.channels.append(ch)
        guild.channels.append(ch)
        return ch

    guild.create_category = AsyncMock(side_effect=fake_create_category)
    guild.create_text_channel = AsyncMock(side_effect=fake_create_text)
    guild.create_voice_channel = AsyncMock(side_effect=fake_create_voice)

    logs = []
    # First execution: Creates 3 categories and all channels
    results = run_async(build_tournament_section(guild, log_callback=logs.append, delay=0))

    assert results["categories_created"] == 3
    assert results["channels_created"] == 14
    assert results["categories_existing"] == 0
    assert results["channels_existing"] == 0
    assert len(results["errors"]) == 0

    # Verify channel map has announcements, registration, checkin, and subs
    cmap = results["channel_map"]
    assert "announcements" in cmap
    assert "registration" in cmap
    assert "checkin" in cmap
    assert "subs" in cmap

    # Second execution on the same guild: Should skip existing (idempotent)
    guild.create_category.reset_mock()
    guild.create_text_channel.reset_mock()
    guild.create_voice_channel.reset_mock()

    results2 = run_async(build_tournament_section(guild, delay=0))

    assert results2["categories_created"] == 0
    assert results2["channels_created"] == 0
    assert results2["categories_existing"] == 3
    assert results2["channels_existing"] == 14
    assert results2["channel_map"] == cmap
    guild.create_category.assert_not_called()
    guild.create_text_channel.assert_not_called()
    guild.create_voice_channel.assert_not_called()


def test_delete_tournament_section_success():
    guild = MagicMock()
    bot_member = MagicMock()
    bot_member.guild_permissions.manage_channels = True
    guild.me = bot_member

    # Create matching Tournament Hub category with channels
    tourney_cat = MagicMock()
    tourney_cat.name = "🏆 TOURNAMENT HUB 🏆"
    tourney_ch = MagicMock()
    tourney_ch.name = "📣・tournament-announcements"
    tourney_ch.delete = AsyncMock()
    tourney_cat.channels = [tourney_ch]
    tourney_cat.delete = AsyncMock()

    # Create unrelated user category that should NOT be touched
    unrelated_cat = MagicMock()
    unrelated_cat.name = "💬 U.D.A. COMMUNITY 💬"
    unrelated_ch = MagicMock()
    unrelated_ch.name = "general"
    unrelated_ch.delete = AsyncMock()
    unrelated_cat.channels = [unrelated_ch]
    unrelated_cat.delete = AsyncMock()

    guild.categories = [tourney_cat, unrelated_cat]
    guild.channels = [tourney_ch, unrelated_ch]

    results = run_async(delete_tournament_section(guild, delay=0))

    assert results["categories_deleted"] == 1
    assert results["channels_deleted"] == 1
    assert len(results["errors"]) == 0

    # Tournament category and channel deleted
    tourney_ch.delete.assert_called_once()
    tourney_cat.delete.assert_called_once()

    # Unrelated community category and channel untouched
    unrelated_ch.delete.assert_not_called()
    unrelated_cat.delete.assert_not_called()
