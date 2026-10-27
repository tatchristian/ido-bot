import pytest
from pathlib import Path
from services.tournament_service import TournamentService, STANDARD_REGIONS
from utils.storage import StorageManager


@pytest.fixture
def service(tmp_path: Path):
    storage_file = tmp_path / "tournament.json"
    storage = StorageManager(storage_file)
    return TournamentService(storage)


# =============================================================================
# Regions Configuration Test
# =============================================================================

def test_standard_regions_excludes_me():
    assert "ME" not in STANDARD_REGIONS
    assert "NA" in STANDARD_REGIONS
    assert "EU" in STANDARD_REGIONS
    assert "OCE" in STANDARD_REGIONS
    assert "ASIA" in STANDARD_REGIONS
    assert "SA" in STANDARD_REGIONS


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

    ok1, msg1, p1 = service.register_participant(
        user_id=1, user_mention="<@1>", ign="PlayerOne", weapon="Katana", region="NA"
    )
    assert ok1
    assert p1.ign == "PlayerOne"
    assert len(service.get_state().participants) == 1

    ok2, msg2, p2 = service.register_participant(
        user_id=2, user_mention="<@2>", ign="PlayerTwo", weapon="Daggers", region="EU"
    )
    assert ok2
    assert len(service.get_state().participants) == 2

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

    for region in ["NA", "EU", "OCE", "ASIA", "SA"]:
        allowed, msg = service.is_region_allowed(region)
        assert allowed
        assert msg == ""


def test_region_validation_single_region(service: TournamentService):
    service.open_tournament(name="NA Showdown", slots=8, regions="NA")

    allowed_na, _ = service.is_region_allowed("NA")
    assert allowed_na

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

    ok, msg, sub = service.register_substitute(
        user_id=201, user_mention="<@201>", ign="SubOne", weapon="Naginata", region="NA"
    )
    assert ok
    assert sub.ign == "SubOne"
    assert len(service.get_state().substitutes) == 1

    ok_dup, msg_dup, _ = service.register_substitute(
        user_id=201, user_mention="<@201>", ign="SubOne", weapon="Naginata", region="NA"
    )
    assert not ok_dup

    ok_unreg, unreg_msg = service.unregister_substitute(201)
    assert ok_unreg
    assert len(service.get_state().substitutes) == 0


def test_cross_registration_prevention(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=8, regions="GLOBAL", open_subs=True)

    service.register_participant(1, "<@1>", "MainPlayer", "Katana", "NA")

    ok_sub, msg_sub, _ = service.register_substitute(1, "<@1>", "MainPlayer", "Katana", "NA")
    assert not ok_sub

    service.register_substitute(2, "<@2>", "SubPlayer", "Katana", "NA")

    ok_main, msg_main, _ = service.register_participant(2, "<@2>", "SubPlayer", "Katana", "NA")
    assert not ok_main


def test_promote_substitute_fifo(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=4, regions="GLOBAL", open_subs=True)
    service.register_participant(1, "<@1>", "Player1", "Katana", "NA")

    service.register_substitute(10, "<@10>", "FirstSub", "Daggers", "NA")
    service.register_substitute(20, "<@20>", "SecondSub", "Bo Staff", "EU")

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
# New Admin Tools Tests: Kick, Force Register & Edit Entry
# =============================================================================

def test_kick_user(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=8, regions="GLOBAL", open_subs=True)
    service.register_participant(1, "<@1>", "BadPlayer", "Katana", "NA")
    service.register_substitute(2, "<@2>", "BadSub", "Katana", "NA")

    # Kick from main
    ok, msg = service.kick_user(1, reason="Inappropriate conduct")
    assert ok
    assert "main bracket" in msg
    assert len(service.get_state().participants) == 0

    # Kick from sub
    ok_sub, msg_sub = service.kick_user(2, reason="Inactive")
    assert ok_sub
    assert "substitute queue" in msg_sub
    assert len(service.get_state().substitutes) == 0


def test_force_register(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=2, regions="GLOBAL")
    # Tournament registration can even be closed
    service.close_tournament()

    ok, msg, p = service.force_register(
        user_id=55, user_mention="<@55>", ign="VIPDuelist", weapon="Katana", region="NA"
    )
    assert ok
    assert p.ign == "VIPDuelist"
    assert len(service.get_state().participants) == 1


def test_edit_entry(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=8, regions="NA, EU")
    service.register_participant(1, "<@1>", "OldIGN", "Katana", "NA")

    # Edit weapon and IGN
    ok, msg, updated = service.edit_entry(user_id=1, weapon="Naginata", ign="NewIGN")
    assert ok
    assert updated.weapon == "Naginata"
    assert updated.ign == "NewIGN"
    assert updated.region == "NA"

    # Reject region change to unallowed region
    ok_fail, msg_fail, _ = service.edit_entry(user_id=1, region="ASIA")
    assert not ok_fail
    assert "This tournament is only open to participants from:" in msg_fail


# =============================================================================
# Tournament Day Flow: Check-in & Export Tests
# =============================================================================

def test_checkin_flow(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=8, regions="GLOBAL")
    service.register_participant(1, "<@1>", "ReadyPlayer", "Katana", "NA")
    service.register_participant(2, "<@2>", "NoShowPlayer", "Katana", "NA")

    # Cannot check in when check-in is closed
    ok, msg = service.checkin_user(1)
    assert not ok

    # Open checkin
    service.open_checkin()
    assert service.get_state().checkin_open

    # Checkin Player 1
    ok1, msg1 = service.checkin_user(1)
    assert ok1
    assert "confirmed" in msg1.lower()
    assert service.get_state().participants[0].checked_in

    # Unconfirmed participants list
    unconfirmed = service.get_unconfirmed_participants()
    assert len(unconfirmed) == 1
    assert unconfirmed[0].user_id == 2


def test_export_roster(service: TournamentService):
    service.open_tournament(name="IDO Masters", slots=8, regions="GLOBAL", open_subs=True)
    service.register_participant(1, "<@1>", "Champion", "Katana", "NA")
    service.register_substitute(2, "<@2>", "Standby", "Daggers", "EU")

    # Export CSV
    fname_csv, content_csv = service.export_roster("csv")
    assert fname_csv.endswith(".csv")
    assert "Champion" in content_csv
    assert "Standby" in content_csv

    # Export Challonge
    fname_ch, content_ch = service.export_roster("challonge")
    assert fname_ch.endswith(".txt")
    assert "Champion" in content_ch

    # Export Text
    fname_txt, content_txt = service.export_roster("text")
    assert fname_txt.endswith(".txt")
    assert "Main Bracket" in content_txt


def test_admin_set_admin_role_and_clear(service: TournamentService):
    service.open_tournament(name="IDO Cup", slots=8, regions="GLOBAL")
    service.register_participant(1, "<@1>", "Player1", "Katana", "NA")

    # Set admin role threshold
    role_msg = service.set_admin_role(role_id=987654321, role_name="Head Referee")
    assert "Head Referee" in role_msg
    assert service.get_state().admin_role_id == 987654321
    assert service.get_state().admin_role_name == "Head Referee"

    # Set limit
    service.set_limit(16)
    assert service.get_state().max_slots == 16

    # Clear tournament
    clear_msg = service.clear_tournament()
    assert "wiped clean" in clear_msg.lower()
    assert len(service.get_state().participants) == 0


def test_multi_server_isolation(tmp_path: Path):
    """Verifies that Server A and Server B rosters are completely isolated."""
    service = TournamentService(data_dir=tmp_path)
    guild_test = 111111111
    guild_main = 222222222

    # Open tournament on test server with 4 slots
    service.open_tournament(name="Test Cup", slots=4, guild_id=guild_test)
    # Open tournament on main server with 16 slots
    service.open_tournament(name="Official IDO", slots=16, guild_id=guild_main)

    # Register in test server
    service.register_participant(1, "<@1>", "Tester", "Katana", "NA", guild_id=guild_test)

    # Register in main server
    service.register_participant(2, "<@2>", "Champion", "Naginata", "EU", guild_id=guild_main)

    # Check test server state
    test_state = service.get_state(guild_test)
    assert test_state.name == "Test Cup"
    assert test_state.max_slots == 4
    assert len(test_state.participants) == 1
    assert test_state.participants[0].ign == "Tester"

    # Check main server state
    main_state = service.get_state(guild_main)
    assert main_state.name == "Official IDO"
    assert main_state.max_slots == 16
    assert len(main_state.participants) == 1
    assert main_state.participants[0].ign == "Champion"

    # Wiping test server does not touch main server
    service.clear_tournament(guild_id=guild_test)
    assert len(service.get_state(guild_test).participants) == 0
    assert len(service.get_state(guild_main).participants) == 1
