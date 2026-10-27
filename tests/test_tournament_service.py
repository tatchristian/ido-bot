import pytest
from pathlib import Path
from services.tournament_service import TournamentService
from utils.storage import StorageManager


@pytest.fixture
def service(tmp_path: Path):
    storage_file = tmp_path / "tournament.json"
    storage = StorageManager(storage_file)
    return TournamentService(storage)


# =============================================================================
# Registration & Capacity Limit Tests
# =============================================================================

def test_register_when_closed(service: TournamentService):
    success, msg, p = service.register_participant(
        user_id=101, user_mention="<@101>", ign="Shadow", weapon="Katana", region="NA"
    )
    assert not success
    assert "closed" in msg.lower()
    assert p is None


def test_register_success_and_capacity_limit(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=2, regions="GLOBAL", open_subs=True)

    # 1. Register first participant
    ok1, msg1, p1 = service.register_participant(
        user_id=1, user_mention="<@1>", ign="PlayerOne", weapon="Katana", region="NA"
    )
    assert ok1
    assert p1.ign == "PlayerOne"
    assert len(service.get_state().participants) == 1

    # 2. Register second participant (reaches capacity)
    ok2, msg2, p2 = service.register_participant(
        user_id=2, user_mention="<@2>", ign="PlayerTwo", weapon="Daggers", region="EU"
    )
    assert ok2
    assert len(service.get_state().participants) == 2

    # 3. Third participant should be rejected due to slot limit
    ok3, msg3, p3 = service.register_participant(
        user_id=3, user_mention="<@3>", ign="PlayerThree", weapon="Bo Staff", region="OCE"
    )
    assert not ok3
    assert "full" in msg3.lower()
    assert p3 is None
    assert len(service.get_state().participants) == 2


def test_duplicate_registration_rejected(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=8, regions="GLOBAL")

    ok1, _, _ = service.register_participant(
        user_id=10, user_mention="<@10>", ign="Shadow", weapon="Katana", region="NA"
    )
    assert ok1

    # Duplicate in main bracket
    ok2, msg2, _ = service.register_participant(
        user_id=10, user_mention="<@10>", ign="Shadow", weapon="Katana", region="NA"
    )
    assert not ok2
    assert "already registered" in msg2.lower()


# =============================================================================
# Region Validation Tests
# =============================================================================

def test_region_validation_global(service: TournamentService):
    service.open_tournament(name="Global Duel", slots=8, regions="GLOBAL")

    # Any region should be accepted when GLOBAL is set
    for region in ["NA", "EU", "OCE", "ASIA", "SA", "ME"]:
        allowed, msg = service.is_region_allowed(region)
        assert allowed
        assert msg == ""


def test_region_validation_single_region(service: TournamentService):
    service.open_tournament(name="NA Showdown", slots=8, regions="NA")

    # NA should be allowed
    allowed_na, _ = service.is_region_allowed("NA")
    assert allowed_na

    # EU should be rejected with exact required message
    allowed_eu, err_eu = service.is_region_allowed("EU")
    assert not allowed_eu
    assert err_eu == "This tournament is only open to participants from: NA"


def test_region_validation_multi_region(service: TournamentService):
    service.open_tournament(name="Transatlantic Clash", slots=8, regions="NA, EU")

    assert service.is_region_allowed("NA")[0]
    assert service.is_region_allowed("EU")[0]

    allowed_oce, err_oce = service.is_region_allowed("OCE")
    assert not allowed_oce
    assert err_oce == "This tournament is only open to participants from: EU, NA" or \
           err_oce == "This tournament is only open to participants from: NA, EU"

    # Registering participant with invalid region must be rejected
    ok, reg_msg, _ = service.register_participant(
        user_id=50, user_mention="<@50>", ign="OceaniaWarrior", weapon="Warhammer", region="OCE"
    )
    assert not ok
    assert "This tournament is only open to participants from:" in reg_msg


# =============================================================================
# Substitute Queue & Promotion Tests
# =============================================================================

def test_substitute_registration_and_unregister(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=8, regions="GLOBAL", open_subs=True)

    # Register as substitute
    ok, msg, sub = service.register_substitute(
        user_id=201, user_mention="<@201>", ign="SubOne", weapon="Naginata", region="NA"
    )
    assert ok
    assert sub.ign == "SubOne"
    assert len(service.get_state().substitutes) == 1

    # Cannot register duplicate in substitute queue
    ok_dup, msg_dup, _ = service.register_substitute(
        user_id=201, user_mention="<@201>", ign="SubOne", weapon="Naginata", region="NA"
    )
    assert not ok_dup

    # Unregister substitute
    ok_unreg, unreg_msg = service.unregister_substitute(201)
    assert ok_unreg
    assert len(service.get_state().substitutes) == 0


def test_cross_registration_prevention(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=8, regions="GLOBAL", open_subs=True)

    # Register in main
    service.register_participant(1, "<@1>", "MainPlayer", "Katana", "NA")

    # Main player cannot also register as sub
    ok_sub, msg_sub, _ = service.register_substitute(1, "<@1>", "MainPlayer", "Katana", "NA")
    assert not ok_sub

    # Register another user as sub
    service.register_substitute(2, "<@2>", "SubPlayer", "Katana", "NA")

    # Sub player cannot register for main while in sub queue
    ok_main, msg_main, _ = service.register_participant(2, "<@2>", "SubPlayer", "Katana", "NA")
    assert not ok_main


def test_promote_substitute_fifo(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=4, regions="GLOBAL", open_subs=True)
    service.register_participant(1, "<@1>", "Player1", "Katana", "NA")

    # Add two substitutes
    service.register_substitute(10, "<@10>", "FirstSub", "Daggers", "NA")
    service.register_substitute(20, "<@20>", "SecondSub", "Bo Staff", "EU")

    # Promote first in line (FIFO)
    ok, msg, promoted = service.promote_substitute()
    assert ok
    assert promoted.user_id == 10
    assert len(service.get_state().participants) == 2
    assert len(service.get_state().substitutes) == 1
    assert service.get_state().substitutes[0].user_id == 20


def test_promote_substitute_replace_no_show(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=2, regions="GLOBAL", open_subs=True)
    service.register_participant(1, "<@1>", "NoShowPlayer", "Katana", "NA")
    service.register_participant(2, "<@2>", "ReadyPlayer", "Katana", "NA")

    service.register_substitute(99, "<@99>", "ClutchSub", "Kusarigama", "NA")

    # Swap no-show player with standby sub
    ok, msg, promoted = service.promote_substitute(
        substitute_user_id=99, replace_user_id=1
    )
    assert ok
    assert promoted.user_id == 99

    participants = service.get_state().participants
    assert len(participants) == 2
    participant_ids = [p.user_id for p in participants]
    assert 99 in participant_ids
    assert 1 not in participant_ids
    assert len(service.get_state().substitutes) == 0


# =============================================================================
# Admin Controls & Roster Wiping Tests
# =============================================================================

def test_admin_set_limit_and_clear(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=8, regions="GLOBAL")
    service.register_participant(1, "<@1>", "Player1", "Katana", "NA")
    service.open_subs()
    service.register_substitute(2, "<@2>", "Sub1", "Katana", "NA")

    # Change limit
    service.set_limit(16)
    assert service.get_state().max_slots == 16

    # Clear tournament
    clear_msg = service.clear_tournament()
    assert "wiped clean" in clear_msg.lower()
    assert len(service.get_state().participants) == 0
    assert len(service.get_state().substitutes) == 0
