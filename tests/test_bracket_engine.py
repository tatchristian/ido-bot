"""
Unit tests for Tournament Bracket Engine:
- Seeding distribution and power-of-2 normalization
- Single Elimination with odd-roster byes
- Out-of-order ready-state match progression
- Match result undo safeguards
- Double Elimination routing and Grand Finals Reset
"""

import pytest
from services.bracket_engine import BracketEngine, generate_seed_order


def test_seed_order_generation():
    assert generate_seed_order(2) == [1, 2]
    assert generate_seed_order(4) == [1, 4, 2, 3]
    assert generate_seed_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]
    assert generate_seed_order(16) == [1, 16, 8, 9, 4, 13, 5, 12, 2, 15, 7, 10, 3, 14, 6, 11]


def test_calculate_bracket_size():
    assert BracketEngine.calculate_bracket_size(2) == 2
    assert BracketEngine.calculate_bracket_size(3) == 4
    assert BracketEngine.calculate_bracket_size(4) == 4
    assert BracketEngine.calculate_bracket_size(7) == 8
    assert BracketEngine.calculate_bracket_size(8) == 8
    assert BracketEngine.calculate_bracket_size(19) == 32


def test_single_elimination_byes_and_progression():
    # 3 players -> 4 slot bracket. Seed 1 gets a BYE to the Finals.
    participants = [
        {"user_id": 101, "ign": "Ninja", "clan": "KAZE"},
        {"user_id": 102, "ign": "Shadow", "clan": "Yume"},
        {"user_id": 103, "ign": "Blaze", "clan": "Blue Fire"},
    ]
    bracket = BracketEngine.build_bracket(participants, format="single")
    assert bracket.bracket_size == 4
    assert bracket.total_rounds_wb == 2

    # Match 1 was Seed 1 vs Seed 4 (BYE), so it auto-completed and advanced Ninja to Finals!
    m1 = bracket.matches["WB-R1-M1"]
    assert m1.state == "bye"
    assert m1.winner_id == 101

    # Match 2 (Shadow vs Blaze) is ready to play
    m2 = bracket.matches["WB-R1-M2"]
    assert m2.state == "ready"
    assert m2.player1_id == 102
    assert m2.player2_id == 103

    # Finals is waiting on winner of M2
    finals = bracket.matches["WB-R2-M1"]
    assert finals.player1_id == 101  # Ninja is already seated!
    assert finals.player2_ign == "TBD"
    assert finals.state == "pending"

    # Play Match 2: Shadow (102) wins 2-1
    ok, msg, m2_done = BracketEngine.report_match(bracket, "WB-R1-M2", winner_id=102, score="2 - 1")
    assert ok is True
    assert m2_done.winner_id == 102

    # Finals is now READY between Ninja and Shadow!
    assert finals.state == "ready"
    assert finals.player1_id == 101
    assert finals.player2_id == 102

    # Play Finals: Ninja (101) wins
    ok_f, msg_f, _ = BracketEngine.report_match(bracket, "WB-R2-M1", winner_id=101, score="3 - 0")
    assert ok_f is True
    assert bracket.champion_id == 101
    assert bracket.champion_ign == "Ninja"
    assert bracket.runner_up_id == 102


def test_out_of_order_match_play():
    # 8 players
    participants = [{"user_id": i, "ign": f"Player_{i}"} for i in range(1, 9)]
    bracket = BracketEngine.build_bracket(participants, format="single")

    ready = BracketEngine.get_ready_matches(bracket)
    assert len(ready) == 4  # All 4 Round 1 matches are ready

    # Play Match 1 (R1-M1) and Match 2 (R1-M2) early
    BracketEngine.report_match(bracket, "WB-R1-M1", winner_id=1)
    BracketEngine.report_match(bracket, "WB-R1-M2", winner_id=4)

    # Round 2 Match 1 (WB-R2-M1) becomes READY immediately,
    # even though Round 1 Match 3 & Match 4 haven't even started!
    r2_m1 = bracket.matches["WB-R2-M1"]
    assert r2_m1.state == "ready"
    assert r2_m1.player1_id == 1
    assert r2_m1.player2_id == 4

    # Staff can report Round 2 Match 1 out of order!
    ok, _, _ = BracketEngine.report_match(bracket, "WB-R2-M1", winner_id=1)
    assert ok is True
    assert r2_m1.state == "completed"


def test_match_undo_and_downstream_protection():
    participants = [{"user_id": i, "ign": f"Player_{i}"} for i in range(1, 5)]
    bracket = BracketEngine.build_bracket(participants, format="single")

    # Round 1 Match 1
    BracketEngine.report_match(bracket, "WB-R1-M1", winner_id=1)
    finals = bracket.matches["WB-R2-M1"]
    assert finals.player1_id == 1

    # Undoing M1 clears slot in finals
    ok_undo, _ = BracketEngine.undo_match(bracket, "WB-R1-M1")
    assert ok_undo is True
    assert bracket.matches["WB-R1-M1"].state == "ready"
    assert finals.player1_id is None
    assert finals.player1_ign == "TBD"

    # Play M1 and M2, then play Finals
    BracketEngine.report_match(bracket, "WB-R1-M1", winner_id=1)
    BracketEngine.report_match(bracket, "WB-R1-M2", winner_id=2)
    BracketEngine.report_match(bracket, "WB-R2-M1", winner_id=1)
    assert bracket.champion_id == 1

    # Attempting to undo M1 while Finals is completed must be blocked!
    fail_undo, err = BracketEngine.undo_match(bracket, "WB-R1-M1")
    assert fail_undo is False
    assert "Undo that match first" in err


def test_double_elimination_grand_finals_reset():
    # 4 players in Double Elimination
    participants = [{"user_id": i, "ign": f"Player_{i}"} for i in range(1, 5)]
    bracket = BracketEngine.build_bracket(participants, format="double")

    assert bracket.format == "double"
    assert "GF" in bracket.matches

    # R1: Player 1 beats 4; Player 2 beats 3
    BracketEngine.report_match(bracket, "WB-R1-M1", winner_id=1)
    BracketEngine.report_match(bracket, "WB-R1-M2", winner_id=2)

    # LB R1: Player 3 defeats Player 4 and advances to Losers Finals slot 2
    assert bracket.matches["LB-R1-M1"].state == "ready"
    assert bracket.matches["LB-R1-M1"].player1_id == 4
    assert bracket.matches["LB-R1-M1"].player2_id == 3
    BracketEngine.report_match(bracket, "LB-R1-M1", winner_id=3)

    # Winners Finals: Player 1 beats Player 2 -> Player 1 advances to GF slot 1
    # AND Player 2 automatically drops into Losers Finals (LB-R2-M1) slot 1!
    BracketEngine.report_match(bracket, "WB-R2-M1", winner_id=1)
    gf = bracket.matches["GF"]
    assert gf.player1_id == 1

    # Verify Losers Finals (LB-R2-M1) automatically received Player 2
    lb_finals = bracket.matches["LB-R2-M1"]
    assert lb_finals.state == "ready"
    assert lb_finals.player1_id == 2
    assert lb_finals.player2_id == 3

    # Player 2 wins Losers Finals -> advances to Grand Finals slot 2
    BracketEngine.report_match(bracket, "LB-R2-M1", winner_id=2)
    assert gf.state == "ready"
    assert gf.player2_id == 2
    assert gf.player2_ign == "Player_2"

    # If Losers Bracket champion (Player 2, slot 2) wins GF Game 1:
    ok_gf, msg_gf, _ = BracketEngine.report_match(bracket, "GF", winner_id=2, score="2 - 1")
    assert ok_gf is True
    assert "Reset Match (Game 2)" in msg_gf
    assert "GF-RESET" in bracket.matches
    assert bracket.champion_id is None  # Champion not yet crowned!

    # Play GF-RESET: Player 2 wins Game 2 -> Player 2 is crowned Champion!
    ok_reset, _, _ = BracketEngine.report_match(bracket, "GF-RESET", winner_id=2, score="2 - 0")
    assert ok_reset is True
    assert bracket.champion_id == 2
    assert bracket.champion_ign == "Player_2"


def test_double_elimination_undo_protection():
    participants = [{"user_id": i, "ign": f"Player_{i}"} for i in range(1, 5)]
    bracket = BracketEngine.build_bracket(participants, format="double")

    # Play WB R1
    BracketEngine.report_match(bracket, "WB-R1-M1", winner_id=1)
    BracketEngine.report_match(bracket, "WB-R1-M2", winner_id=2)

    # Play LB R1
    BracketEngine.report_match(bracket, "LB-R1-M1", winner_id=3)

    # Attempting to undo WB-R1-M1 must be BLOCKED because its loser (Player 4) already completed LB-R1-M1!
    ok_undo, err = BracketEngine.undo_match(bracket, "WB-R1-M1")
    assert ok_undo is False
    assert "loser's next match" in err.lower()

    # If we undo LB-R1-M1 first, then undoing WB-R1-M1 succeeds and clears the loser from LB!
    ok_lb_undo, _ = BracketEngine.undo_match(bracket, "LB-R1-M1")
    assert ok_lb_undo is True

    ok_wb_undo, _ = BracketEngine.undo_match(bracket, "WB-R1-M1")
    assert ok_wb_undo is True
    assert bracket.matches["LB-R1-M1"].player1_id is None
    assert bracket.matches["LB-R1-M1"].state == "pending"


def test_build_bracket_embed_rendering():
    from utils.tournament_embeds import build_bracket_embed

    participants = [
        {"user_id": 1, "ign": "Alice", "clan": "ALPHA", "checked_in": True},
        {"user_id": 2, "ign": "Bob", "clan": "BETA", "checked_in": False},
        {"user_id": 3, "ign": "Charlie", "clan": None, "checked_in": True},
        {"user_id": 4, "ign": "Diana", "clan": None, "checked_in": False},
    ]
    bracket = BracketEngine.build_bracket(participants, format="double")
    embed = build_bracket_embed(bracket, tournament_name="Grand Prix", section="winners", round_num=1)

    assert "Grand Prix" in embed.title
    assert "Winners Bracket" in embed.title
    assert len(embed.fields) >= 1
    # Check soft check-in badges
    field_text = embed.fields[0].value
    assert "[ALPHA] Alice" in field_text
    assert "[BETA] Bob" in field_text

    # Crown champion and verify champion banner
    bracket.champion_ign = "Alice"
    bracket.champion_id = 1
    embed_champ = build_bracket_embed(bracket, tournament_name="Grand Prix", section="finals", round_num=1)
    assert "TOURNAMENT CHAMPION" in embed_champ.description
    assert "Alice" in embed_champ.description


def test_tournament_bracket_panel_view_button_sync(tmp_path):
    from services.tournament_service import TournamentService
    from utils.storage import StorageManager
    from utils.tournament_views import TournamentBracketPanelView

    service = TournamentService(StorageManager(tmp_path / "t.json"))
    service.open_tournament(name="Panel Cup", slots=4)
    service.register_participant(1, "<@1>", "A", "Katana", "NA")
    service.register_participant(2, "<@2>", "B", "Katana", "NA")

    view = TournamentBracketPanelView(service, guild_id=0, section="winners", round_num=1)
    assert view.btn_prev.disabled is True  # Already on round 1
    assert view.btn_lock.label == "🔒 Lock Bracket"
    assert view.btn_toggle_format.disabled is False  # Unlocked bracket can toggle format

    # Lock bracket
    service.lock_bracket(0)
    view._sync_buttons()
    assert view.btn_lock.label == "🔓 Unlock Bracket"
    assert view.btn_shuffle.disabled is True  # Locked bracket cannot shuffle
    assert view.btn_toggle_format.disabled is True


def test_double_elimination_odd_roster_byes():
    # 3 players in double elimination:
    participants = [
        {"user_id": 1, "ign": "P1"},
        {"user_id": 2, "ign": "P2"},
        {"user_id": 3, "ign": "P3"},
    ]
    bracket = BracketEngine.build_bracket(participants, format="double")
    assert bracket.bracket_size == 4
    assert bracket.matches["WB-R1-M1"].state == "bye"
    assert bracket.matches["WB-R1-M2"].state == "ready"

    # Play WB-R1-M2: P2 beats P3
    BracketEngine.report_match(bracket, "WB-R1-M2", winner_id=2)
    # P3 drops into LB-R1-M1 slot 2; since slot 1 was a BYE, LB-R1-M1 auto-resolves as bye!
    assert bracket.matches["LB-R1-M1"].state == "bye"
    # P3 automatically advances to Losers Finals (LB-R2-M1)!
    assert bracket.matches["LB-R2-M1"].player2_id == 3

    # Play WB-R2-M1 (Winners Finals): P1 beats P2
    BracketEngine.report_match(bracket, "WB-R2-M1", winner_id=1)
    # P1 advances to Grand Finals (GF) slot 1!
    assert bracket.matches["GF"].player1_id == 1
    # P2 drops to Losers Finals slot 1 to face P3!
    assert bracket.matches["LB-R2-M1"].state == "ready"
    assert bracket.matches["LB-R2-M1"].player1_id == 2
    assert bracket.matches["LB-R2-M1"].player2_id == 3

    # Play Losers Finals: P2 beats P3
    BracketEngine.report_match(bracket, "LB-R2-M1", winner_id=2)
    assert bracket.matches["GF"].state == "ready"
    assert bracket.matches["GF"].player2_id == 2

    # Play Grand Finals: P1 beats P2
    BracketEngine.report_match(bracket, "GF", winner_id=1)
    assert bracket.champion_id == 1
    assert bracket.runner_up_id == 2

