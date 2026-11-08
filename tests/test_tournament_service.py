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


def test_configure_tournament_without_opening(service: TournamentService):
    # Configure parameters
    msg = service.configure_tournament(
        name="Asia Championship",
        slots=32,
        regions="ASIA, OCE",
        participant_role_id=999,
        participant_role_name="Asia Participant",
        registration_channel_id=888,
    )
    assert "configured" in msg.lower()

    state = service.get_state()
    assert state.name == "Asia Championship"
    assert state.max_slots == 32
    assert state.allowed_regions == ["ASIA", "OCE"]
    assert state.participant_role_id == 999
    assert state.registration_channel_id == 888
    # Main bracket is still CLOSED until staff explicitly opens it
    assert state.main_open is False

    # Open registrations directly (keeps configured parameters)
    open_msg = service.open_tournament()
    assert "open" in open_msg.lower()
    assert service.get_state().main_open is True
    assert service.get_state().name == "Asia Championship"
    assert service.get_state().max_slots == 32


def test_toggle_subs_methods(service: TournamentService):
    assert service.get_state().subs_open is False

    # Open subs
    open_msg = service.open_subs(subs_channel_id=777)
    assert "open" in open_msg.lower()
    assert service.get_state().subs_open is True
    assert service.get_state().subs_channel_id == 777

    # Close subs
    close_msg = service.close_subs()
    assert "closed" in close_msg.lower()
    assert service.get_state().subs_open is False


def test_register_success_and_capacity_limit(service: TournamentService):
    service.open_tournament(name="UDA Cup", slots=2, regions="GLOBAL", open_subs=True)

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
    service.open_tournament(name="UDA Cup", slots=8, regions="GLOBAL")

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


def test_region_parsing_strips_quotes_and_brackets(service: TournamentService):
    """Ensures quotes in user inputs (e.g. \"'NA, EU, OCE'\") are cleanly sanitized."""
    parsed = service.parse_regions("'NA, EU, OCE'")
    assert "NA" in parsed
    assert "EU" in parsed
    assert "OCE" in parsed
    assert "'NA" not in parsed

    service.open_tournament(name="Quoted Regions Event", slots=8, regions="'NA, EU, OCE'")
    allowed, _ = service.is_region_allowed("NA")
    assert allowed
    allowed_eu, _ = service.is_region_allowed("EU")
    assert allowed_eu
    allowed_oce, _ = service.is_region_allowed("OCE")
    assert allowed_oce


# =============================================================================
# Substitute Queue & Promotion Tests
# =============================================================================

def test_substitute_registration_and_unregister(service: TournamentService):
    service.open_tournament(name="UDA Cup", slots=8, regions="GLOBAL", open_subs=True)

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
    service.open_tournament(name="UDA Cup", slots=8, regions="GLOBAL", open_subs=True)

    service.register_participant(1, "<@1>", "MainPlayer", "Katana", "NA")

    ok_sub, msg_sub, _ = service.register_substitute(1, "<@1>", "MainPlayer", "Katana", "NA")
    assert not ok_sub

    service.register_substitute(2, "<@2>", "SubPlayer", "Katana", "NA")

    ok_main, msg_main, _ = service.register_participant(2, "<@2>", "SubPlayer", "Katana", "NA")
    assert not ok_main


def test_promote_substitute_fifo(service: TournamentService):
    service.open_tournament(name="UDA Cup", slots=4, regions="GLOBAL", open_subs=True)
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
    service.open_tournament(name="UDA Cup", slots=2, regions="GLOBAL", open_subs=True)
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


def test_promote_substitute_prioritizes_checked_in(service: TournamentService):
    service.open_tournament(name="UDA Cup", slots=2, regions="GLOBAL", open_subs=True)
    service.register_participant(1, "<@1>", "Player1", "Katana", "NA")
    service.register_participant(2, "<@2>", "Player2", "Katana", "NA")

    # Sub 1 registered first, but does NOT check in
    service.register_substitute(10, "<@10>", "SubFirst", "Katana", "NA")
    # Sub 2 registered second, and DOES check in
    service.register_substitute(20, "<@20>", "SubSecondReady", "Daggers", "NA")

    service.open_checkin()
    ok_sub, msg_sub = service.checkin_user(20)
    assert ok_sub
    assert "Standby substitute check-in confirmed" in msg_sub
    assert service.get_state().substitutes[1].checked_in

    # Automatic promote without specific ID should prioritize checked-in Sub 2 (id 20) over Sub 1 (id 10)
    ok, msg, promoted = service.promote_substitute(replace_user_id=1)
    assert ok
    assert promoted.user_id == 20
    assert promoted.ign == "SubSecondReady"

    # Remaining sub should be Sub 1 (id 10)
    assert len(service.get_state().substitutes) == 1
    assert service.get_state().substitutes[0].user_id == 10



# =============================================================================
# New Admin Tools Tests: Kick, Force Register & Edit Entry
# =============================================================================

def test_kick_user(service: TournamentService):
    service.open_tournament(name="UDA Cup", slots=8, regions="GLOBAL", open_subs=True)
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
    service.open_tournament(name="UDA Cup", slots=2, regions="GLOBAL")
    # Tournament registration can even be closed
    service.close_tournament()

    ok, msg, p = service.force_register(
        user_id=55, user_mention="<@55>", ign="VIPDuelist", weapon="Katana", region="NA"
    )
    assert ok
    assert p.ign == "VIPDuelist"
    assert len(service.get_state().participants) == 1


def test_edit_entry(service: TournamentService):
    service.open_tournament(name="UDA Cup", slots=8, regions="NA, EU")
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
    service.open_tournament(name="UDA Cup", slots=8, regions="GLOBAL")
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
    service.open_tournament(name="UDA Masters", slots=8, regions="GLOBAL", open_subs=True)
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
    service.open_tournament(name="UDA Cup", slots=8, regions="GLOBAL")
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


def test_participant_role_management(service: TournamentService):
    service.open_tournament(
        name="Winter Invitational",
        slots=8,
        participant_role_id=123456789,
        participant_role_name="Winter Invitational Participant",
    )
    state = service.get_state()
    assert state.participant_role_id == 123456789
    assert state.participant_role_name == "Winter Invitational Participant"

    # Set participant role manually
    msg = service.set_participant_role(555555555, "Custom Role")
    assert "Custom Role" in msg
    assert service.get_state().participant_role_id == 555555555

    # Clear tournament resets participant role
    service.clear_tournament()
    assert service.get_state().participant_role_id is None
    assert service.get_state().participant_role_name is None


def test_export_roster_targets(service: TournamentService):
    service.open_tournament(name="UDA Masters", slots=8, open_subs=True)
    service.register_participant(1, "<@1>", "MainPlayer", "Katana", "NA")
    service.register_substitute(2, "<@2>", "SubPlayer", "Daggers", "EU")

    # Target: main (bracket import) - must ONLY include MainPlayer, NOT SubPlayer
    fname_main, content_main = service.export_roster("csv", target="main")
    assert fname_main.startswith("tournament_bracket_roster_")
    assert "MainPlayer" in content_main
    assert "SubPlayer" not in content_main

    # Target: subs - must ONLY include SubPlayer
    fname_subs, content_subs = service.export_roster("csv", target="subs")
    assert fname_subs.startswith("tournament_subs_roster_")
    assert "SubPlayer" in content_subs
    assert "MainPlayer" not in content_subs

    # Target: all - includes both
    fname_all, content_all = service.export_roster("csv", target="all")
    assert "MainPlayer" in content_all
    assert "SubPlayer" in content_all
    assert "Main Bracket" in content_all
    assert "Substitute" in content_all


def test_dedicated_channel_management(service: TournamentService):
    service.open_tournament(
        name="Channel Cup",
        slots=8,
        announcement_channel_id=111,
    )
    assert service.get_state().announcement_channel_id == 111

    service.open_subs(subs_channel_id=222)
    assert service.get_state().subs_channel_id == 222

    service.open_checkin(checkin_channel_id=333)
    assert service.get_state().checkin_channel_id == 333

    # Set channels directly
    msg = service.set_channels(announcement_channel_id=999, registration_channel_id=444)
    assert "updated" in msg.lower()
    assert service.get_state().announcement_channel_id == 999
    assert service.get_state().checkin_channel_id == 333
    assert service.get_state().registration_channel_id == 444

    # Clear channels
    clear_msg = service.clear_channels()
    assert "cleared" in clear_msg.lower()
    assert service.get_state().announcement_channel_id is None
    assert service.get_state().checkin_channel_id is None
    assert service.get_state().subs_channel_id is None
    assert service.get_state().registration_channel_id is None


def test_multi_server_isolation(tmp_path: Path):
    """Verifies that Server A and Server B rosters are completely isolated."""
    service = TournamentService(data_dir=tmp_path)
    guild_test = 111111111
    guild_main = 222222222

    # Open tournament on test server with 4 slots
    service.open_tournament(name="Test Cup", slots=4, guild_id=guild_test)
    # Open tournament on main server with 16 slots
    service.open_tournament(name="Official UDA", slots=16, guild_id=guild_main)

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
    assert main_state.name == "Official UDA"
    assert main_state.max_slots == 16
    assert len(main_state.participants) == 1
    assert main_state.participants[0].ign == "Champion"

    # Wiping test server does not touch main server
    service.clear_tournament(guild_id=guild_test)
    assert len(service.get_state(guild_test).participants) == 0
    assert len(service.get_state(guild_main).participants) == 1

def test_event_role_management(service: TournamentService):
    state = service.get_state()
    assert state.event_role_id is None
    assert state.event_role_name is None

    # 1. Set event role
    msg = service.set_event_role(role_id=777888999, role_name='Event Coordinator')
    assert 'Event Coordinator' in msg
    assert service.get_state().event_role_id == 777888999
    assert service.get_state().event_role_name == 'Event Coordinator'

    # 2. Clearing tournament roster should NOT clear event role
    service.clear_tournament()
    assert service.get_state().event_role_id == 777888999

    # 3. Clear event role
    clear_msg = service.set_event_role(role_id=None, role_name=None)
    assert 'cleared' in clear_msg.lower()
    assert service.get_state().event_role_id is None
    assert service.get_state().event_role_name is None


def test_event_and_tournament_role_isolation(service: TournamentService):
    from unittest.mock import MagicMock
    import discord
    from cogs.tournaments import check_is_tournament_admin, check_is_event_admin
    from cogs.clan_showcase import is_staff_user

    guild = MagicMock()
    guild.id = 12345
    guild.owner_id = 99999

    # Configure Tournament Admin role in service
    service.set_admin_role(role_id=111, role_name='Tournament Admin', guild_id=guild.id)
    # Configure Event & Website role in service
    service.set_event_role(role_id=222, role_name='Event Planner', guild_id=guild.id)

    tourney_role = MagicMock()
    tourney_role.id = 111
    tourney_role.name = 'Tournament Admin'
    tourney_role.position = 10

    event_role = MagicMock()
    event_role.id = 222
    event_role.name = 'Event Planner'
    event_role.position = 10

    guild.roles = [tourney_role, event_role]
    guild.get_role.side_effect = lambda rid: tourney_role if rid == 111 else (event_role if rid == 222 else None)

    # Mock bot with TournamentCog
    bot = MagicMock()
    cog = MagicMock()
    cog.service = service
    bot.get_cog.side_effect = lambda name: cog if name == 'TournamentCog' else None

    # User A has ONLY Event Planner role
    user_event_only = MagicMock(spec=discord.Member)
    user_event_only.id = 1001
    user_event_only.roles = [event_role]
    user_event_only.top_role = event_role
    user_event_only.guild_permissions.administrator = False
    user_event_only.guild_permissions.manage_guild = False
    user_event_only.guild_permissions.manage_channels = False
    user_event_only.guild_permissions.manage_events = False

    # User B has ONLY Tournament Admin role
    user_tourney_only = MagicMock(spec=discord.Member)
    user_tourney_only.id = 1002
    user_tourney_only.roles = [tourney_role]
    user_tourney_only.top_role = tourney_role
    user_tourney_only.guild_permissions.administrator = False
    user_tourney_only.guild_permissions.manage_guild = False
    user_tourney_only.guild_permissions.manage_channels = False
    user_tourney_only.guild_permissions.manage_events = False

    # User A (Event only): CAN access event admin, CANNOT access tournament admin or clan showcase
    assert check_is_event_admin(user_event_only, guild, bot) is True
    assert check_is_tournament_admin(user_event_only, guild, bot) is False
    assert is_staff_user(user_event_only, guild) is False

    # User B (Tournament only): CAN access tournament admin, CANNOT access event admin or clan showcase
    assert check_is_tournament_admin(user_tourney_only, guild, bot) is True
    assert check_is_event_admin(user_tourney_only, guild, bot) is False
    assert is_staff_user(user_tourney_only, guild) is False


def test_tournament_time_and_reminder_state(service: TournamentService):
    state = service.get_state()
    assert state.start_time is None
    assert state.start_timestamp is None

    # Set tournament time
    start_iso = '2026-11-15T18:00:00+00:00'
    start_ts = 1794500000
    msg = service.set_tournament_time(start_time=start_iso, start_timestamp=start_ts, event_id=888999)
    assert f'<t:{start_ts}:F>' in msg
    assert service.get_state().start_time == start_iso
    assert service.get_state().start_timestamp == start_ts
    assert service.get_state().event_id == 888999

    # Test DM marking
    service.mark_dm_sent(12345, 'day_of')
    service.mark_dm_sent(12345, '30_min')
    assert 12345 in service.get_state().day_of_dm_sent
    assert 12345 in service.get_state().thirty_min_dm_sent

    # Updating time clears DM records
    service.set_tournament_time(start_time='2026-11-16T18:00:00+00:00', start_timestamp=1794586400)
    assert len(service.get_state().day_of_dm_sent) == 0
    assert len(service.get_state().thirty_min_dm_sent) == 0

    # Clear tournament resets time
    service.clear_tournament()
    assert service.get_state().start_time is None
    assert service.get_state().start_timestamp is None


def test_resolve_user_id_in_cog():
    from unittest.mock import MagicMock
    from cogs.tournaments import TournamentCog
    from services.tournament_service import TournamentService, Participant
    from utils.storage import StorageManager
    import tempfile
    from pathlib import Path

    temp_dir = Path(tempfile.mkdtemp())
    service = TournamentService(storage=StorageManager(temp_dir / "test_tourney.json"))
    service.open_tournament(name="Test Cup", slots=8, open_subs=True)
    service.register_participant(user_id=111, user_mention="<@111>", ign="Shadow", weapon="Katana", region="NA")
    service.register_substitute(user_id=222, user_mention="<@222>", ign="BackupNinja", weapon="Daggers", region="EU")

    bot = MagicMock()
    cog = TournamentCog(bot, service)

    # 1. Autocomplete / raw digit ID
    assert cog._resolve_user_id("111", guild_id=0) == 111
    assert cog._resolve_user_id("222", guild_id=0) == 222

    # 2. Discord mention format
    assert cog._resolve_user_id("<@111>", guild_id=0) == 111
    assert cog._resolve_user_id("<@!222>", guild_id=0) == 222

    # 3. Exact IGN match (case-insensitive)
    assert cog._resolve_user_id("shadow", guild_id=0) == 111
    assert cog._resolve_user_id("SHADOW", guild_id=0) == 111
    assert cog._resolve_user_id("BackupNinja", guild_id=0) == 222

    # 4. Partial IGN match
    assert cog._resolve_user_id("Backup", guild_id=0) == 222

    # 5. Invalid / Non-existent
    assert cog._resolve_user_id("unknown_player", guild_id=0) is None
    assert cog._resolve_user_id("", guild_id=0) is None
    assert cog._resolve_user_id(None, guild_id=0) is None


def test_panel_message_id_persistence():
    from services.tournament_service import TournamentService
    from utils.storage import StorageManager
    import tempfile
    from pathlib import Path

    temp_dir = Path(tempfile.mkdtemp())
    service = TournamentService(storage=StorageManager(temp_dir / "test_tourney.json"))
    service.open_tournament(name="Summer Clash", slots=8, open_subs=True)

    state = service.get_state(0)
    state.registration_channel_id = 11111
    state.registration_message_id = 77777
    state.subs_channel_id = 22222
    state.subs_message_id = 88888
    service._persist(0)

    # Reload from storage
    service2 = TournamentService(storage=StorageManager(temp_dir / "test_tourney.json"))
    reloaded = service2.get_state(0)
    assert reloaded.registration_channel_id == 11111
    assert reloaded.registration_message_id == 77777
    assert reloaded.subs_channel_id == 22222
    assert reloaded.subs_message_id == 88888

    # Clear tournament resets message IDs
    service2.clear_tournament(0)
    cleared = service2.get_state(0)
    assert cleared.registration_message_id is None
    assert cleared.subs_message_id is None


