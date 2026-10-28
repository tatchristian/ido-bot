"""
Unit tests for the IDO Automated Server Layout Builder service.
"""

from __future__ import annotations

import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import discord

from services.server_builder import (
    LAYOUT_SPEC,
    is_3v3_reference,
    build_server_layout,
    delete_server_layout,
)


def test_is_3v3_reference():
    # True positives: All variations of 3v3 / 3ჸ3 / 3&3
    assert is_3v3_reference("3ჸ3")
    assert is_3v3_reference("❖┊3ჸ3_x_alliance 🤝")
    assert is_3v3_reference("🏛 ⭒-3ჸ3 — (I.D.O) ORGANIZATION HUB-⭒")
    assert is_3v3_reference("❖┊3ჸ3-announcements")
    assert is_3v3_reference("❤️‍🔥 3ჸ3-tier")
    assert is_3v3_reference("3&3")
    assert is_3v3_reference("3x3")
    assert is_3v3_reference("3v3")
    assert is_3v3_reference("3 ჸ 3")
    assert is_3v3_reference("3 & 3")
    assert is_3v3_reference("3 x 3")

    # False positives: Normal channels with letters or numbers
    assert not is_3v3_reference("📜┊official-clan_x_alliances-list")
    assert not is_3v3_reference("🔊・trio-lounge")
    assert not is_3v3_reference("🍵🌸┊general-chat")
    assert not is_3v3_reference("⚖️✾┊ido-supreme-court 🏛")
    assert not is_3v3_reference("Admin/Mod")
    assert not is_3v3_reference("👋｜welcome")


def test_layout_spec_has_no_3v3_items():
    """Validates that the production layout spec does not include any 3v3 references."""
    for group in LAYOUT_SPEC:
        cat = group.get("category")
        if cat:
            assert not is_3v3_reference(cat), f"Category '{cat}' contains 3v3 reference!"
        for ch in group.get("channels", []):
            name = ch["name"]
            assert not is_3v3_reference(name), f"Channel '{name}' contains 3v3 reference!"


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_build_server_layout_missing_permissions():
    guild = MagicMock()
    bot_member = MagicMock()
    bot_member.guild_permissions.manage_channels = False
    guild.me = bot_member

    results = run_async(build_server_layout(guild, delay=0))
    assert len(results["errors"]) == 1
    assert "missing" in results["errors"][0].lower()


def test_build_server_layout_success_and_idempotency():
    guild = MagicMock()
    bot_member = MagicMock()
    bot_member.guild_permissions.manage_channels = True
    guild.me = bot_member
    guild.features = ["COMMUNITY"]
    guild.default_role = MagicMock()

    guild.categories = []
    guild.channels = []

    # Mock creation coroutines
    async def fake_create_category(name, **kwargs):
        cat = MagicMock()
        cat.name = name
        cat.channels = []
        guild.categories.append(cat)
        return cat

    async def fake_create_text(name, category=None, news=False, **kwargs):
        ch = MagicMock()
        ch.name = name
        ch.category = category
        if category:
            category.channels.append(ch)
        guild.channels.append(ch)
        return ch

    async def fake_create_voice(name, category=None, user_limit=0, **kwargs):
        ch = MagicMock()
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
    # First execution: Should create all categories and channels
    results = run_async(build_server_layout(guild, log_callback=logs.append, delay=0))

    assert results["categories_created"] > 0
    assert results["channels_created"] > 0
    assert results["categories_existing"] == 0
    assert results["channels_existing"] == 0
    assert len(results["errors"]) == 0

    # Second execution on the same guild: Should skip existing without errors (idempotent)
    guild.create_category.reset_mock()
    guild.create_text_channel.reset_mock()
    guild.create_voice_channel.reset_mock()

    results2 = run_async(build_server_layout(guild, delay=0))

    assert results2["categories_created"] == 0
    assert results2["channels_created"] == 0
    assert results2["categories_existing"] == results["categories_created"]
    assert results2["channels_existing"] == results["channels_created"]
    guild.create_category.assert_not_called()
    guild.create_text_channel.assert_not_called()
    guild.create_voice_channel.assert_not_called()


def test_delete_server_layout_success():
    guild = MagicMock()
    bot_member = MagicMock()
    bot_member.guild_permissions.manage_channels = True
    guild.me = bot_member

    # Create matching IDO category with channels
    ido_cat = MagicMock()
    ido_cat.name = "🏛 ⭒-(I.D.O) ORGANIZATION HUB-⭒"
    ido_ch1 = MagicMock()
    ido_ch1.name = "📜❖┊rules"
    ido_ch1.delete = AsyncMock()
    ido_cat.channels = [ido_ch1]
    ido_cat.delete = AsyncMock()

    # Create unrelated category that should NOT be deleted
    unrelated_cat = MagicMock()
    unrelated_cat.name = "Custom Gaming Area"
    unrelated_ch = MagicMock()
    unrelated_ch.name = "minecraft-chat"
    unrelated_ch.delete = AsyncMock()
    unrelated_cat.channels = [unrelated_ch]
    unrelated_cat.delete = AsyncMock()

    guild.categories = [ido_cat, unrelated_cat]

    # Root channels
    ido_root = MagicMock()
    ido_root.name = "👋｜welcome"
    ido_root.category = None
    ido_root.delete = AsyncMock()

    unrelated_root = MagicMock()
    unrelated_root.name = "general"
    unrelated_root.category = None
    unrelated_root.delete = AsyncMock()

    guild.channels = [ido_ch1, unrelated_ch, ido_root, unrelated_root]

    results = run_async(delete_server_layout(guild, delay=0))

    assert results["categories_deleted"] == 1
    assert results["channels_deleted"] == 2  # ido_ch1 and ido_root
    assert len(results["errors"]) == 0

    # IDO channels/category were deleted
    ido_ch1.delete.assert_called_once()
    ido_cat.delete.assert_called_once()
    ido_root.delete.assert_called_once()

    # Unrelated channels/category were NOT deleted
    unrelated_cat.delete.assert_not_called()
    unrelated_ch.delete.assert_not_called()
    unrelated_root.delete.assert_not_called()


