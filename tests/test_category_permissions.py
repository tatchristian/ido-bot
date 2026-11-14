"""
Unit tests for tournament category region permissions sync and weapon-free registration modals.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import discord
from services.tournament_service import TournamentService, TournamentState
from cogs.tournaments import (
    TournamentCog,
    UserRegistrationModal,
    UserSubRegistrationModal,
)
from utils.storage import StorageManager
import tempfile
import shutil
from pathlib import Path


@pytest.fixture
def service():
    temp_dir = tempfile.mkdtemp()
    storage_path = Path(temp_dir) / "tournaments.json"
    backup_path = Path(temp_dir) / "backups"
    storage = StorageManager(file_path=storage_path, backup_dir=backup_path)
    svc = TournamentService(storage=storage)
    yield svc
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_bot(service: TournamentService):
    bot = MagicMock()
    cog = TournamentCog(bot=bot, service=service)
    return cog


def test_user_registration_modal_no_weapon_field(service: TournamentService):
    """Verify registration modal contains only IGN and Region inputs (weapon removed)."""
    state = TournamentState(name="Asia Championship", allowed_regions=["ASIA"])
    modal = UserRegistrationModal(service=service, state=state)

    # Must only have 2 fields
    assert len(modal.children) == 2
    assert hasattr(modal, "ign_input")
    assert hasattr(modal, "region_input")
    assert not hasattr(modal, "weapon_input")
    assert modal.ign_input.label == "In-Game Name (IGN)"
    assert modal.region_input.label == "Region Tag"


def test_user_sub_registration_modal_no_weapon_field(service: TournamentService):
    """Verify standby sub modal contains only IGN and Region inputs (weapon removed)."""
    state = TournamentState(name="Asia Championship", allowed_regions=["ASIA"])
    modal = UserSubRegistrationModal(service=service, state=state)

    # Must only have 2 fields
    assert len(modal.children) == 2
    assert hasattr(modal, "ign_input")
    assert hasattr(modal, "region_input")
    assert not hasattr(modal, "weapon_input")
    assert modal.ign_input.label == "In-Game Name (IGN)"
    assert modal.region_input.label == "Region Tag"


@pytest.mark.asyncio
async def test_sync_category_permissions_regional_asia(mock_bot: TournamentCog, service: TournamentService):
    """Verify Asia-only tournament restricts @everyone and standard non-Asia roles, granting view to @Asia."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    guild.default_role = MagicMock(spec=discord.Role)
    guild.default_role.name = "@everyone"

    asia_role = MagicMock(spec=discord.Role)
    asia_role.name = "Asia"
    na_role = MagicMock(spec=discord.Role)
    na_role.name = "North America"
    eu_role = MagicMock(spec=discord.Role)
    eu_role.name = "Europe"

    guild.roles = [guild.default_role, asia_role, na_role, eu_role]

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_channels = True
    bot_member.guild_permissions.manage_roles = True
    guild.me = bot_member

    category = MagicMock(spec=discord.CategoryChannel)
    category.name = "🏆 TOURNAMENTS"
    category.set_permissions = AsyncMock()

    guild.categories = [category]
    guild.get_channel = MagicMock(return_value=None)

    service.open_tournament(name="Asia Cup", regions="ASIA", guild_id=guild.id)

    success, msg = await mock_bot._sync_category_region_permissions(
        guild=guild,
        regions=["ASIA"],
        category=category,
    )

    assert success is True
    assert "restricted to `@Asia`" in msg

    # Verify @everyone denied view_channel
    category.set_permissions.assert_any_call(
        guild.default_role,
        view_channel=False,
        reason="Tournament Region View Restriction (Restricted to: ASIA)",
    )

    # Verify Asia role granted view_channel
    category.set_permissions.assert_any_call(
        asia_role,
        view_channel=True,
        reason="Tournament Region View Restriction (Allowed region: ASIA)",
    )

    # Verify NA role denied view_channel
    category.set_permissions.assert_any_call(
        na_role,
        view_channel=False,
        reason="Tournament Region View Restriction (Disallowed region: NA)",
    )


@pytest.mark.asyncio
async def test_sync_category_permissions_global(mock_bot: TournamentCog, service: TournamentService):
    """Verify GLOBAL tournament resets @everyone to view_channel=True."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    guild.default_role = MagicMock(spec=discord.Role, name="@everyone")

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_channels = True
    bot_member.guild_permissions.manage_roles = True
    guild.me = bot_member

    category = MagicMock(spec=discord.CategoryChannel)
    category.name = "🏆 TOURNAMENTS"
    category.set_permissions = AsyncMock()

    guild.categories = [category]

    service.open_tournament(name="Global Championship", regions="GLOBAL", guild_id=guild.id)

    success, msg = await mock_bot._sync_category_region_permissions(
        guild=guild,
        regions=["GLOBAL"],
        category=category,
    )

    assert success is True
    assert "view opened to all regions (@everyone)" in msg
    category.set_permissions.assert_called_once_with(
        guild.default_role,
        view_channel=True,
        reason="Tournament Region View Restriction (Global Tournament - Open to All)",
    )
