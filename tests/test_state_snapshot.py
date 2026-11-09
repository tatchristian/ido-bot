import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from services.clan_showcase_service import ClanShowcaseService
from services.state_snapshot_service import StateSnapshotService, ChannelStateSnapshot
from services.tournament_service import TournamentService
from utils.storage import StorageManager


@pytest.fixture
def test_env(tmp_path: Path):
    t_file = tmp_path / "tournaments.json"
    c_dir = tmp_path / "clan_data"
    c_dir.mkdir(parents=True, exist_ok=True)
    state_file = tmp_path / "saved_state.json"

    t_service = TournamentService(StorageManager(t_file))
    c_service = ClanShowcaseService(data_dir=c_dir)
    snapshot_service = StateSnapshotService(file_path=state_file)

    return {
        "t_service": t_service,
        "c_service": c_service,
        "snapshot_service": snapshot_service,
        "state_file": state_file,
    }


def test_save_and_load_snapshot(test_env):
    t_service = test_env["t_service"]
    c_service = test_env["c_service"]
    snapshot_service = test_env["snapshot_service"]
    state_file = test_env["state_file"]
    guild_id = 12345

    # 1. Set up some channels & roles
    t_state = t_service.get_state(guild_id)
    t_state.registration_channel_id = 101
    t_state.announcement_channel_id = 102
    t_state.checkin_channel_id = 103
    t_state.subs_channel_id = 104
    t_state.admin_role_id = 201
    t_state.participant_role_id = 202
    t_service._persist(guild_id)

    c_service.set_guild_channels(guild_id, showcase_channel_id=301, staff_review_channel_id=302)
    c_service.set_clan_role_panel_info(guild_id, channel_id=303, message_id=401)
    c_service.set_clanless_role_id(guild_id, 203)

    # 2. Save snapshot
    data = snapshot_service.save_snapshot(guild_id, t_service, c_service)
    assert state_file.exists()
    assert data["guild_id"] == guild_id
    assert data["tournament"]["registration_channel_id"] == 101
    assert data["clan_showcase"]["showcase_channel_id"] == 301

    # 3. Clear existing states
    t_service.clear_channels(guild_id)
    cleared_t = t_service.get_state(guild_id)
    assert cleared_t.registration_channel_id is None

    # Overwrite clan channels with dummy new IDs to simulate drift
    c_service.set_guild_channels(guild_id, showcase_channel_id=999, staff_review_channel_id=998)
    assert c_service.get_guild_channels(guild_id) == (999, 998)

    # 4. Restore snapshot
    snapshot = snapshot_service.restore_snapshot(guild_id, t_service, c_service)
    restored_t = t_service.get_state(guild_id)
    assert restored_t.registration_channel_id == 101
    assert restored_t.announcement_channel_id == 102
    assert restored_t.checkin_channel_id == 103
    assert restored_t.subs_channel_id == 104
    assert restored_t.admin_role_id == 201

    showcase_ch, review_ch = c_service.get_guild_channels(guild_id)
    assert showcase_ch == 301
    assert review_ch == 302
    role_panel_ch, role_panel_msg = c_service.get_clan_role_panel_info(guild_id)
    assert role_panel_ch == 303
    assert role_panel_msg == 401
    assert c_service.get_clanless_role_id(guild_id) == 203


def test_auto_discover_channels(test_env):
    t_service = test_env["t_service"]
    c_service = test_env["c_service"]
    snapshot_service = test_env["snapshot_service"]
    guild_id = 99999

    # Mock Discord Guild with channels
    mock_guild = MagicMock()
    mock_guild.id = guild_id

    ch1 = MagicMock()
    ch1.id = 551
    ch1.name = "📝・tournament-registration"

    ch2 = MagicMock()
    ch2.id = 552
    ch2.name = "📣・tournament-announcements"

    ch3 = MagicMock()
    ch3.id = 553
    ch3.name = "clan-showcase"

    mock_guild.text_channels = [ch1, ch2, ch3]

    discovered = snapshot_service.auto_discover_channels(mock_guild, t_service, c_service)
    assert discovered["registration"] == 551
    assert discovered["announcements"] == 552
    assert discovered["showcase"] == 553

    t_state = t_service.get_state(guild_id)
    assert t_state.registration_channel_id == 551
    assert t_state.announcement_channel_id == 552
    showcase_ch, _ = c_service.get_guild_channels(guild_id)
    assert showcase_ch == 553
