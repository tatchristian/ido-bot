"""
Unit tests for the interactive Tournament Check-In Hub, 1-click checkin,
cancel checkin, staff overrides, live embed builders, and log channel dispatch.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from services.tournament_service import TournamentService, TournamentState, Participant
from utils.ui import build_checkin_panel_embed, build_checkin_receipt_embed
from utils.storage import StorageManager
import tempfile
import shutil
import os


@pytest.fixture
def service():
    temp_dir = tempfile.mkdtemp()
    storage_path = Path(temp_dir) / "tournaments.json"
    backup_path = Path(temp_dir) / "backups"
    storage = StorageManager(file_path=storage_path, backup_dir=backup_path)
    svc = TournamentService(storage=storage)
    yield svc
    shutil.rmtree(temp_dir)


def test_1click_main_participant_checkin_and_cancel(service: TournamentService):
    service.open_tournament(name="UDA Championship", slots=8, regions="GLOBAL")
    service.register_participant(101, "<@101>", "Ninja", "Katana", "NA")
    service.open_checkin()

    # 1-Click Check In
    res = service.checkin_user(101)
    assert res.success is True
    assert "Check-in confirmed for **Ninja**" in res.message
    assert res.role_type == "main"
    assert res.participant.checked_in is True

    # Duplicate check in rejected
    dup = service.checkin_user(101)
    assert dup.success is False
    assert "already checked in" in dup.message

    # Cancel Check In
    canc = service.cancel_checkin(101)
    assert canc.success is True
    assert "Check-in retracted" in canc.message
    assert canc.participant.checked_in is False

    # Second cancel rejected
    canc2 = service.cancel_checkin(101)
    assert canc2.success is False
    assert "not currently checked in" in canc2.message


def test_1click_substitute_checkin_and_cancel(service: TournamentService):
    service.open_tournament(name="UDA Championship", slots=2, regions="GLOBAL", open_subs=True)
    service.register_participant(1, "<@1>", "Main1", "Katana", "NA")
    service.register_participant(2, "<@2>", "Main2", "Katana", "NA")
    service.register_substitute(201, "<@201>", "Sub1", "Daggers", "NA")
    service.open_checkin()

    # Sub Check In
    res = service.checkin_user(201)
    assert res.success is True
    assert "Standby substitute check-in confirmed" in res.message
    assert res.role_type == "sub"
    assert res.participant.checked_in is True

    # Sub Cancel Check In
    canc = service.cancel_checkin(201)
    assert canc.success is True
    assert "Standby check-in retracted" in canc.message
    assert canc.participant.checked_in is False


def test_unregistered_user_rejected_from_checkin(service: TournamentService):
    service.open_tournament(name="UDA Championship", slots=8, regions="GLOBAL")
    service.open_checkin()

    res = service.checkin_user(999)
    assert res.success is False
    assert "not registered in the tournament roster or substitute queue" in res.message


def test_checkin_closed_rejection(service: TournamentService):
    service.open_tournament(name="UDA Championship", slots=8, regions="GLOBAL")
    service.register_participant(101, "<@101>", "Ninja", "Katana", "NA")
    # checkin is NOT open
    res = service.checkin_user(101)
    assert res.success is False
    assert "not currently open" in res.message


def test_staff_set_checkin_override(service: TournamentService):
    service.open_tournament(name="UDA Championship", slots=8, regions="GLOBAL")
    service.register_participant(101, "<@101>", "Ninja", "Katana", "NA")

    # Staff marks user as checked in even before checkin window officially opens
    res = service.staff_set_checkin(101, status=True)
    assert res.success is True
    assert "Staff Override" in res.message
    assert "Checked In" in res.message
    assert res.participant.checked_in is True

    # Staff unconfirms user
    res2 = service.staff_set_checkin(101, status=False)
    assert res2.success is True
    assert "Unconfirmed" in res2.message
    assert res2.participant.checked_in is False


def test_channel_configuration_for_checkin_logs(service: TournamentService):
    service.open_tournament(name="UDA Championship", slots=8, regions="GLOBAL")
    service.set_channels(
        checkin_channel_id=111111,
        checkin_log_channel_id=222222,
    )
    state = service.get_state()
    assert state.checkin_channel_id == 111111
    assert state.checkin_log_channel_id == 222222

    service.clear_channels()
    state_cleared = service.get_state()
    assert state_cleared.checkin_channel_id is None
    assert state_cleared.checkin_log_channel_id is None


def test_build_checkin_panel_embed_and_receipt_embed():
    state = TournamentState(
        name="UDA Masters",
        max_slots=4,
        checkin_open=True,
        participants=[
            Participant(user_id=1, user_mention="<@1>", ign="Blade", weapon="Katana", region="NA", checked_in=True),
            Participant(user_id=2, user_mention="<@2>", ign="Ghost", weapon="Daggers", region="EU", checked_in=False),
        ],
        substitutes=[
            Participant(user_id=3, user_mention="<@3>", ign="Shadow", weapon="Naginata", region="ASIA", checked_in=True),
        ]
    )

    # Panel Embed test
    panel_embed = build_checkin_panel_embed(state)
    assert "UDA Masters — Tournament Check-In Hub" in panel_embed.title
    assert "1 / 2" in panel_embed.description
    assert "**Standby Substitutes Ready:** `1 / 1` duelist(s)" in panel_embed.description

    # Receipt Embed test: checked_in
    receipt_in = build_checkin_receipt_embed(state, state.participants[0], action="checked_in", role_type="main")
    assert "Contestant Check-In Confirmed" in receipt_in.title
    fields = {f.name: f.value for f in receipt_in.fields}
    assert fields["IGN"] == "`Blade`"
    assert "Checked In & Verified Ready" in fields["Current Status"]

    # Receipt Embed test: cancelled
    receipt_canc = build_checkin_receipt_embed(state, state.participants[0], action="cancelled", role_type="main")
    assert "Contestant Check-In Retracted" in receipt_canc.title

    # Receipt Embed test: staff override
    dummy_staff = MagicMock()
    dummy_staff.mention = "<@777>"
    receipt_staff = build_checkin_receipt_embed(state, state.participants[0], action="staff_override", role_type="main", staff_member=dummy_staff)
    assert "Staff Check-In Override" in receipt_staff.title
    fields_staff = {f.name: f.value for f in receipt_staff.fields}
    assert fields_staff["Moderator"] == "<@777>"
