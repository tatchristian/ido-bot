import pytest
from services.tournament_service import Participant, TournamentState
from utils.ui import build_help_embed, build_roster_embed, build_status_embed, generate_progress_bar


def test_progress_bar_empty():
    bar = generate_progress_bar(current=0, total=8, bar_length=8)
    assert "[`░░░░░░░░`] 0%" == bar


def test_progress_bar_twelve_percent():
    bar = generate_progress_bar(current=1, total=8, bar_length=8)
    assert "[`█░░░░░░░`] 12%" == bar


def test_progress_bar_half():
    bar = generate_progress_bar(current=4, total=8, bar_length=8)
    assert "[`████░░░░`] 50%" == bar


def test_progress_bar_full():
    bar = generate_progress_bar(current=8, total=8, bar_length=8)
    assert "[`████████`] 100%" == bar


def test_build_status_embed():
    state = TournamentState(
        name="UDA Masters 2026",
        main_open=True,
        subs_open=False,
        max_slots=8,
        allowed_regions=["NA", "EU"],
    )
    state.participants.append(
        Participant(1, "<@1>", "Shadow", "Katana", "NA")
    )

    embed = build_status_embed(state, org_name="UDA")
    assert "UDA Masters 2026" in embed.title
    assert "**Main Bracket Submissions:** 🟢 **OPEN**" in embed.description
    assert "**Substitute Signups:** 🔴 **CLOSED**" in embed.description
    assert "Allowed Regions:** `NA, EU`" in embed.description
    assert any(f.name == "Approved Weapons" for f in embed.fields)
    assert any(f.name == "Quick Commands" for f in embed.fields)


def test_build_roster_embed():
    state = TournamentState(
        name="UDA Masters 2026",
        main_open=True,
        subs_open=True,
        max_slots=8,
    )
    state.participants.append(
        Participant(1, "<@1>", "Shadow", "Katana", "NA")
    )
    state.substitutes.append(
        Participant(2, "<@2>", "Backup", "Daggers", "EU")
    )

    embed = build_roster_embed(state, org_name="UDA")
    assert "UDA Masters 2026 — Tournament Roster" in embed.title
    main_field = next(f for f in embed.fields if "Main Bracket" in f.name)
    assert "#01" in main_field.value
    assert "Shadow" in main_field.value

    sub_field = next(f for f in embed.fields if "Standby Substitutes" in f.name)
    assert "#01" in sub_field.value
    assert "Backup" in sub_field.value


def test_build_roster_embed_large_bracket_pagination():
    state = TournamentState(name="Asia Tournament", max_slots=32)
    for i in range(20):
        state.participants.append(
            Participant(
                user_id=1000 + i,
                user_mention=f"@Player{i+1}",
                ign=f"LongDuelistName_{i+1}",
                weapon="Katana",
                region="ASIA",
            )
        )
    embed = build_roster_embed(state, org_name="UDA")
    main_fields = [f for f in embed.fields if "Main Bracket" in f.name]
    assert len(main_fields) > 1  # Verify it paginated across multiple fields!
    for f in main_fields:
        assert len(f.value) <= 1024  # Under Discord's limit
    # Verify player 1 and player 20 are both visible
    all_text = "\n".join(f.value for f in main_fields)
    assert "#01" in all_text
    assert "#20" in all_text
    assert "LongDuelistName_20" in all_text


def test_build_help_embed():
    # Test all section for non-admin (admin & event sync should be omitted)
    embed_all_user = build_help_embed("all", org_name="UDA", is_admin=False)
    user_field_names = [f.name for f in embed_all_user.fields]
    assert any("Participant Commands" in name for name in user_field_names)
    assert any("Weapons, Regions & Rules" in name for name in user_field_names)
    assert any("Clan Profile Showcase Portal" in name for name in user_field_names)
    assert not any("Tournament Admin Controls" in name for name in user_field_names)
    assert not any("Events & Website Live Sync" in name for name in user_field_names)

    # Test all section for admin (admin & event sync should be included)
    embed_all_admin = build_help_embed("all", org_name="UDA", is_admin=True)
    admin_field_names = [f.name for f in embed_all_admin.fields]
    assert any("Participant Commands" in name for name in admin_field_names)
    assert any("Tournament Admin Controls" in name for name in admin_field_names)
    assert any("Events & Website Live Sync" in name for name in admin_field_names)
    assert any("Weapons, Regions & Rules" in name for name in admin_field_names)

    # Test participant only section
    embed_part = build_help_embed("participants")
    assert len(embed_part.fields) == 1
    assert "Participant Commands" in embed_part.fields[0].name

    # Test admin section for non-admin vs admin
    embed_admin_denied = build_help_embed("admin", is_admin=False)
    assert len(embed_admin_denied.fields) == 1
    assert "Admin Access Restricted" in embed_admin_denied.fields[0].name

    embed_admin_allowed = build_help_embed("admin", is_admin=True)
    assert len(embed_admin_allowed.fields) == 2
    assert any("Operations" in f.name for f in embed_admin_allowed.fields)
    assert any("/tournament-open" in f.value for f in embed_admin_allowed.fields)

    # Test setup section for non-admin vs admin
    embed_setup_denied = build_help_embed("setup", is_admin=False)
    assert len(embed_setup_denied.fields) == 1
    assert "Admin Access Restricted" in embed_setup_denied.fields[0].name

    embed_setup_allowed = build_help_embed("setup", is_admin=True)
    assert len(embed_setup_allowed.fields) == 2
    assert any("Server Setup" in f.name for f in embed_setup_allowed.fields)
    assert any("/tournament-setup-section" in f.value for f in embed_setup_allowed.fields)
    assert any("/tournament-set-channel" in f.value for f in embed_setup_allowed.fields)

    # Test clans only section
    embed_clans = build_help_embed("clans")
    assert len(embed_clans.fields) == 1
    assert "Clan Profile Showcase Portal" in embed_clans.fields[0].name
    assert "/clan-showcase-edit" in embed_clans.fields[0].value

    # Test events_sync section for non-admin vs admin
    embed_events_denied = build_help_embed("events_sync", is_admin=False)
    assert len(embed_events_denied.fields) == 1
    assert "Admin Access Restricted" in embed_events_denied.fields[0].name

    embed_events_allowed = build_help_embed("events_sync", is_admin=True)
    assert len(embed_events_allowed.fields) == 1
    assert "Events & Website Live Sync" in embed_events_allowed.fields[0].name
    assert "/tournament-complete-event" in embed_events_allowed.fields[0].value

    assert all(len(f.value) <= 1024 for f in embed_all_admin.fields)


def test_build_tournament_reminder_embed():
    from utils.ui import build_tournament_reminder_embed
    from services.tournament_service import Participant, TournamentState

    state = TournamentState(
        name='UDA Summer Championship',
        allowed_regions=['NA', 'EU', 'SA'],
        approved_weapons=['Katana', 'Longsword'],
    )

    p = Participant(
        user_id=456,
        user_mention='<@456>',
        ign='ShadowDuelist',
        weapon='Katana',
        region='SA',
    )
    start_ts = 1794500000

    # 1. Day-Of Match Reminder
    embed_day_of = build_tournament_reminder_embed(
        participant=p,
        state=state,
        reminder_type='day_of',
        start_timestamp=start_ts,
        is_sub=False,
    )
    assert 'TODAY' in embed_day_of.description
    assert 'UDA Summer Championship' in embed_day_of.title
    assert 'NA, EU, SA' in embed_day_of.description
    assert '**SA**' in embed_day_of.description
    assert f'<t:{start_ts}:F>' in embed_day_of.description
    assert f'<t:{start_ts}:R>' in embed_day_of.description

    # 2. 30-Minute Warning Reminder
    embed_30 = build_tournament_reminder_embed(
        participant=p,
        state=state,
        reminder_type='30_min',
        start_timestamp=start_ts,
        is_sub=True,
    )
    assert '30 minutes' in embed_30.description
    assert 'Standby Substitute' in embed_30.description
    assert '**SA**' in embed_30.description
    assert f'<t:{start_ts}:F>' in embed_30.description


def test_build_staff_panel_embed():
    from utils.ui import build_staff_panel_embed
    embed = build_staff_panel_embed(org_name="UDA")
    assert "Tournament Staff Operations Panel" in embed.title
    assert "Create Tournament" in embed.description
    assert "Open Bracket" in embed.description
    assert "Close Bracket" in embed.description
    assert "Toggle Subs" in embed.description
    assert "Toggle Check-In" in embed.description
    assert "Promote Standby Sub" in embed.description
    assert "Broadcast Announce" in embed.description
    assert "Set Match Time" in embed.description
    assert "Live Roster & Status" in embed.description


def test_build_staff_guide_embed():
    from utils.ui import build_staff_guide_embed
    # 1. Overview
    overview_embed = build_staff_guide_embed(section="overview", org_name="UDA")
    assert "Staff Operational Guide" in overview_embed.title
    assert "Operational Phase Directory" in overview_embed.description

    # 2. Individual phases
    p1 = build_staff_guide_embed(section="phase_1", org_name="UDA")
    assert "Phase 1: Pre-Tournament Setup" in p1.title
    p3 = build_staff_guide_embed(section="phase_3", org_name="UDA")
    assert "Phase 3: Match Day" in p3.title

    # 3. All / Cheat Sheet
    embed = build_staff_guide_embed(section="all", org_name="UDA")
    assert "Staff Operational Guide & Cheat Sheet" in embed.title
    field_names = [f.name for f in embed.fields]
    assert any("Phase 1: Pre-Tournament Setup" in name for name in field_names)
    assert any("Phase 2: Registration & Roster Monitoring" in name for name in field_names)
    assert any("Phase 3: Match Day & Reminders" in name for name in field_names)
    assert any("Phase 4: Concluding & Archiving" in name for name in field_names)
    assert any("Role Permissions Reference" in name for name in field_names)


def test_staff_guide_view_structure():
    import discord
    from cogs.tournaments import TournamentStaffGuideView
    view = TournamentStaffGuideView(current_section="overview")
    select_items = [i for i in view.children if isinstance(i, discord.ui.Select)]
    assert len(select_items) == 1
    select = select_items[0]
    assert select.custom_id == "select_staff_guide_page"
    values = [opt.value for opt in select.options]
    assert "overview" in values
    assert "phase_1" in values
    assert "phase_2" in values
    assert "phase_3" in values
    assert "phase_4" in values
    assert "roles" in values


def test_registration_and_subs_panel_embeds():
    from services.tournament_service import TournamentState, Participant
    from utils.ui import (
        build_registration_panel_embed,
        build_registration_closed_embed,
        build_subs_panel_embed,
        build_subs_closed_embed,
    )

    state = TournamentState(
        name="Asia Championship",
        max_slots=16,
        main_open=True,
        subs_open=True,
        allowed_regions=["ASIA"],
        approved_weapons=["Katana", "Naginata"],
        participants=[
            Participant(user_id=1, user_mention="<@1>", ign="Shadow", weapon="Katana", region="ASIA")
        ],
        substitutes=[
            Participant(user_id=2, user_mention="<@2>", ign="Blade", weapon="Naginata", region="ASIA")
        ]
    )

    # 1. Live Registration Panel Embed
    reg_embed = build_registration_panel_embed(state)
    assert "Asia Championship — Player Registration Hub" in reg_embed.title
    assert "REGISTRATIONS ARE OPEN" in reg_embed.description
    assert "1/16" in reg_embed.description
    assert "15 slots remaining" in reg_embed.description
    assert "ASIA" in reg_embed.description
    assert "`Katana`" in reg_embed.description

    # 2. Closed Registration Embed
    closed_reg_embed = build_registration_closed_embed(state)
    assert "Registrations Are CLOSED" in closed_reg_embed.title
    assert "REGISTRATION HAS CLOSED. CHECK FOR SUB REGISTRATION IF AVAILABLE!" in closed_reg_embed.description

    # 3. Live Subs Panel Embed
    subs_embed = build_subs_panel_embed(state)
    assert "Standby Substitute Hub" in subs_embed.title
    assert "STANDBY SUBSTITUTE QUEUE IS OPEN" in subs_embed.description
    assert "`1` duelist(s) waiting in FIFO queue order" in subs_embed.description

    # 4. Closed Subs Embed
    closed_subs_embed = build_subs_closed_embed(state)
    assert "Substitute Queue CLOSED" in closed_subs_embed.title
    assert "STANDBY SUBSTITUTE REGISTRATIONS HAVE CLOSED" in closed_subs_embed.description


def test_registration_and_subs_views():
    import discord
    from unittest.mock import MagicMock
    from services.tournament_service import TournamentState
    from cogs.tournaments import (
        TournamentRegistrationPanelView,
        TournamentClosedRegistrationView,
        TournamentSubsPanelView,
        TournamentClosedSubsView,
    )

    # 1. Registration Panel View
    reg_view = TournamentRegistrationPanelView()
    custom_ids = [btn.custom_id for btn in reg_view.children if hasattr(btn, "custom_id")]
    assert "btn_user_reg_hub" in custom_ids
    assert "btn_user_withdraw_hub" in custom_ids
    assert "btn_user_roster_hub" in custom_ids
    assert "btn_user_checkin_hub" in custom_ids
    assert "btn_user_help_hub" in custom_ids

    # 2. Closed Registration View (without and with subs link)
    closed_view = TournamentClosedRegistrationView()
    c_ids = [btn.custom_id for btn in closed_view.children if hasattr(btn, "custom_id")]
    assert "btn_closed_reg_hub" in c_ids
    assert "btn_closed_roster_hub" in c_ids

    mock_guild = MagicMock(spec=discord.Guild)
    mock_guild.id = 9999
    mock_subs_channel = MagicMock(spec=discord.TextChannel)
    mock_subs_channel.id = 12345
    mock_guild.get_channel.return_value = mock_subs_channel

    state = TournamentState(name="Asia Cup", subs_channel_id=12345)
    closed_view_with_link = TournamentClosedRegistrationView(guild=mock_guild, state=state)
    link_buttons = [btn for btn in closed_view_with_link.children if getattr(btn, "style", None) == discord.ButtonStyle.link]
    assert len(link_buttons) == 1
    assert "https://discord.com/channels/9999/12345" == link_buttons[0].url

    # 3. Subs Panel View
    subs_view = TournamentSubsPanelView()
    s_ids = [btn.custom_id for btn in subs_view.children if hasattr(btn, "custom_id")]
    assert "btn_sub_join_hub" in s_ids
    assert "btn_sub_leave_hub" in s_ids
    assert "btn_sub_pos_hub" in s_ids
    assert "btn_sub_roster_hub" in s_ids
    assert "btn_sub_help_hub" in s_ids

    # 4. Closed Subs View
    closed_subs_view = TournamentClosedSubsView()
    cs_ids = [btn.custom_id for btn in closed_subs_view.children if hasattr(btn, "custom_id")]
    assert "btn_closed_subs_hub" in cs_ids
    assert "btn_closed_subs_roster_hub" in cs_ids

