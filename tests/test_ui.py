import pytest
from services.tournament_service import Participant, TournamentState
from utils.ui import build_roster_embed, build_status_embed, generate_progress_bar


def test_progress_bar_empty():
    bar = generate_progress_bar(current=0, total=8, bar_length=8)
    assert "[`░░░░░░░░`] 0%" == bar


def test_progress_bar_twelve_percent():
    # 1/8 is 12.5% -> 12%
    bar = generate_progress_bar(current=1, total=8, bar_length=8)
    assert "[`█░░░░░░░`] 12%" == bar


def test_progress_bar_half():
    # 4/8 is 50%
    bar = generate_progress_bar(current=4, total=8, bar_length=8)
    assert "[`████░░░░`] 50%" == bar


def test_progress_bar_full():
    bar = generate_progress_bar(current=8, total=8, bar_length=8)
    assert "[`████████`] 100%" == bar


def test_build_status_embed():
    state = TournamentState(
        name="IDO Masters 2026",
        main_open=True,
        subs_open=False,
        max_slots=8,
        allowed_regions=["NA", "EU"],
    )
    state.participants.append(
        Participant(1, "<@1>", "Shadow", "Katana", "NA")
    )

    embed = build_status_embed(state, org_name="IDO")
    assert "IDO Masters 2026" in embed.title
    assert "**Main Bracket Submissions:** 🟢 **OPEN**" in embed.description
    assert "**Substitute Signups:** 🔴 **CLOSED**" in embed.description
    assert "Allowed Regions:** `NA, EU`" in embed.description
    assert any(f.name == "Approved Weapons" for f in embed.fields)
    assert any(f.name == "Quick Commands" for f in embed.fields)


def test_build_roster_embed():
    state = TournamentState(
        name="IDO Masters 2026",
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

    embed = build_roster_embed(state, org_name="IDO")
    assert "IDO Masters 2026 — Tournament Roster" in embed.title
    main_field = next(f for f in embed.fields if "Main Bracket" in f.name)
    assert "#01" in main_field.value
    assert "Shadow" in main_field.value

    sub_field = next(f for f in embed.fields if "Standby Substitutes" in f.name)
    assert "#01" in sub_field.value
    assert "Backup" in sub_field.value
