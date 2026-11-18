"""
Visual Bracket Image Renderer
Generates professional esports bracket tree graphics (PNG) from TournamentBracket data,
matching Challonge / Start.gg visual style with dark theme, match cards, orange score badges,
and crisp connector elbow lines.
"""

from __future__ import annotations

import io
import math
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from services.bracket_engine import BracketMatch, TournamentBracket


def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Safe cross-platform font loader with fallback to PIL scalable default."""
    font_names = [
        "arialbd.ttf" if bold else "arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "LiberationSans-Bold.ttf" if bold else "LiberationSans.ttf",
        "segoeuib.ttf" if bold else "segoeui.ttf",
    ]
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


class BracketImageRenderer:
    """
    Renders dynamic visual tournament bracket trees into PNG images.
    Supports Winners Bracket, Losers Bracket, and Finals with out-of-order state indicators.
    """

    BG_COLOR = (24, 24, 27)             # #18181b Dark Charcoal
    CARD_BG = (39, 39, 42)              # #27272a Slate Card
    CARD_BORDER = (63, 63, 70)          # #3f3f46 Muted Border
    READY_BORDER = (56, 189, 248)       # #38bdf8 Cyan Glow for active matches
    COMPLETED_BORDER = (82, 82, 91)     # #52525b
    SEED_BG = (28, 28, 32)              # #1c1c20 Darker Seed Pocket
    SEED_TEXT = (161, 161, 170)         # #a1a1aa
    DIVIDER_COLOR = (55, 55, 60)        # Divider between player 1 and 2
    TEXT_WHITE = (244, 244, 245)        # #f4f4f5
    TEXT_MUTED = (113, 113, 122)        # #71717a for BYE / TBD
    SCORE_WINNER_BG = (234, 88, 12)     # #ea580c Vibrant Orange (Challonge style)
    SCORE_WINNER_TEXT = (255, 255, 255)
    SCORE_LOSER_BG = (63, 63, 70)       # #3f3f46 Dark Slate
    SCORE_LOSER_TEXT = (161, 161, 170)
    LINE_COLOR = (113, 113, 122)        # #71717a Connector lines
    HEADER_TEXT = (212, 212, 216)       # #d4d4d8 Column Headers
    HEADER_BG = (30, 30, 34)            # Top banner
    TITLE_GOLD = (250, 204, 21)         # #facc15 Trophy Gold

    CARD_WIDTH = 190
    CARD_HEIGHT = 58
    SLOT_HEIGHT = 29
    COL_GAP = 55
    PADDING_LEFT = 35
    PADDING_TOP = 85
    PADDING_BOTTOM = 35

    @classmethod
    def render(
        cls,
        bracket: TournamentBracket,
        tournament_name: str = "UDA Championship",
        section: str = "winners",
    ) -> io.BytesIO:
        """
        Renders the requested bracket section into an in-memory PNG BytesIO buffer.
        """
        sec = section.lower().strip()
        if sec == "losers" and bracket.format == "double":
            return cls._render_losers(bracket, tournament_name)
        elif sec == "finals" and bracket.format == "double":
            return cls._render_finals(bracket, tournament_name)
        return cls._render_winners(bracket, tournament_name)

    @classmethod
    def _render_winners(
        cls,
        bracket: TournamentBracket,
        tournament_name: str,
    ) -> io.BytesIO:
        """Renders Winners Bracket tree (Round 1 to Finals)."""
        wb_rounds = max(1, bracket.total_rounds_wb)
        b_size = max(2, bracket.bracket_size or 2)
        r1_matches_count = b_size // 2

        # Calculate canvas size
        canvas_width = cls.PADDING_LEFT + (wb_rounds * cls.CARD_WIDTH) + ((wb_rounds - 1) * cls.COL_GAP) + cls.PADDING_LEFT
        base_unit = cls.CARD_HEIGHT + 24
        canvas_height = cls.PADDING_TOP + (r1_matches_count * base_unit) + cls.PADDING_BOTTOM
        canvas_height = max(320, canvas_height)

        img = Image.new("RGB", (canvas_width, canvas_height), color=cls.BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Fonts
        font_title = _get_font(18, bold=True)
        font_sub = _get_font(11, bold=False)
        font_col = _get_font(13, bold=True)
        font_player = _get_font(12, bold=True)
        font_meta = _get_font(10, bold=False)

        # Top Banner
        sec_title = "Winners Bracket" if bracket.format == "double" else "Tournament Bracket"
        fmt_badge = f"{bracket.format.title()} Elimination"
        status_text = "Locked Live" if bracket.is_locked else "Draft Mode"

        draw.rectangle([0, 0, canvas_width, 58], fill=cls.HEADER_BG)
        draw.line([(0, 58), (canvas_width, 58)], fill=cls.CARD_BORDER, width=1)
        draw.text((cls.PADDING_LEFT, 12), f"{tournament_name} — {sec_title}", fill=cls.TITLE_GOLD, font=font_title)
        draw.text((cls.PADDING_LEFT, 36), f"{fmt_badge} • {status_text} • {bracket.bracket_size} Slots", fill=cls.TEXT_MUTED, font=font_sub)

        # Round column coordinates & centers
        match_coords: Dict[str, Tuple[int, int]] = {}  # match_id -> (center_x, center_y)

        # 1. Compute positions and draw column headers
        for r in range(1, wb_rounds + 1):
            col_x = cls.PADDING_LEFT + (r - 1) * (cls.CARD_WIDTH + cls.COL_GAP)
            # Column header label
            if r == wb_rounds:
                col_name = "Finals"
            elif r == wb_rounds - 1:
                col_name = "Semifinals"
            elif r == wb_rounds - 2:
                col_name = "Quarterfinals"
            else:
                col_name = f"Round {r}"

            draw.text((col_x + cls.CARD_WIDTH // 2 - 20, 68), col_name, fill=cls.HEADER_TEXT, font=font_col)

            # Match positions
            matches_in_r = b_size // (1 << r)
            for m_idx in range(1, matches_in_r + 1):
                m_id = f"WB-R{r}-M{m_idx}"
                if r == 1:
                    center_y = cls.PADDING_TOP + 15 + (m_idx - 1) * base_unit + cls.CARD_HEIGHT // 2
                else:
                    # Parent match centers
                    p1_id = f"WB-R{r-1}-M{2 * m_idx - 1}"
                    p2_id = f"WB-R{r-1}-M{2 * m_idx}"
                    y1 = match_coords.get(p1_id, (0, 0))[1]
                    y2 = match_coords.get(p2_id, (0, 0))[1]
                    center_y = (y1 + y2) // 2

                match_coords[m_id] = (col_x, center_y)

        # 2. Draw connector lines between rounds
        for r in range(1, wb_rounds):
            matches_in_r = b_size // (1 << r)
            for m_idx in range(1, matches_in_r + 1):
                m_id = f"WB-R{r}-M{m_idx}"
                if m_id not in match_coords:
                    continue
                start_x = match_coords[m_id][0] + cls.CARD_WIDTH
                start_y = match_coords[m_id][1]

                # Target in next round
                target_m = (m_idx + 1) // 2
                target_id = f"WB-R{r+1}-M{target_m}"
                if target_id not in match_coords:
                    continue
                end_x = match_coords[target_id][0]
                end_y = match_coords[target_id][1]

                mid_x = start_x + cls.COL_GAP // 2

                # Line from feeder to mid_x
                draw.line([(start_x, start_y), (mid_x, start_y)], fill=cls.LINE_COLOR, width=2)
                # Vertical line toward target center
                draw.line([(mid_x, start_y), (mid_x, end_y)], fill=cls.LINE_COLOR, width=2)
                # Horizontal line into target match
                draw.line([(mid_x, end_y), (end_x, end_y)], fill=cls.LINE_COLOR, width=2)

        # 3. Draw Match Cards
        for r in range(1, wb_rounds + 1):
            matches_in_r = b_size // (1 << r)
            for m_idx in range(1, matches_in_r + 1):
                m_id = f"WB-R{r}-M{m_idx}"
                if m_id not in match_coords:
                    continue
                card_x, center_y = match_coords[m_id]
                card_y = center_y - cls.CARD_HEIGHT // 2

                m_data = bracket.matches.get(m_id)
                cls._draw_match_card(draw, card_x, card_y, m_data, m_id, font_player, font_meta)

        # Save to PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    @classmethod
    def _render_losers(
        cls,
        bracket: TournamentBracket,
        tournament_name: str,
    ) -> io.BytesIO:
        """Renders Losers Bracket tree leading to Losers Finals."""
        lb_rounds = max(1, bracket.total_rounds_lb)
        wb_rounds = max(1, bracket.total_rounds_wb)
        b_size = max(4, bracket.bracket_size or 4)
        r1_lb_count = max(1, b_size // 4)

        canvas_width = cls.PADDING_LEFT + (lb_rounds * cls.CARD_WIDTH) + ((lb_rounds - 1) * cls.COL_GAP) + cls.PADDING_LEFT
        base_unit = cls.CARD_HEIGHT + 24
        canvas_height = cls.PADDING_TOP + (r1_lb_count * base_unit) + cls.PADDING_BOTTOM
        canvas_height = max(360, canvas_height)

        img = Image.new("RGB", (canvas_width, canvas_height), color=cls.BG_COLOR)
        draw = ImageDraw.Draw(img)

        font_title = _get_font(18, bold=True)
        font_sub = _get_font(11, bold=False)
        font_col = _get_font(13, bold=True)
        font_player = _get_font(12, bold=True)
        font_meta = _get_font(10, bold=False)

        # Top Banner
        draw.rectangle([0, 0, canvas_width, 58], fill=cls.HEADER_BG)
        draw.line([(0, 58), (canvas_width, 58)], fill=cls.CARD_BORDER, width=1)
        draw.text((cls.PADDING_LEFT, 12), f"{tournament_name} — Losers Bracket", fill=(147, 197, 253), font=font_title)
        draw.text((cls.PADDING_LEFT, 36), f"Double Elimination • {lb_rounds} Losers Rounds • Winner Advances to Grand Finals", fill=cls.TEXT_MUTED, font=font_sub)

        # Match coordinates
        match_coords: Dict[str, Tuple[int, int]] = {}

        # 1. Compute positions
        for lr in range(1, lb_rounds + 1):
            col_x = cls.PADDING_LEFT + (lr - 1) * (cls.CARD_WIDTH + cls.COL_GAP)
            col_name = "Losers Finals" if lr == lb_rounds else f"Losers R{lr}"
            draw.text((col_x + cls.CARD_WIDTH // 2 - 28, 68), col_name, fill=cls.HEADER_TEXT, font=font_col)

            stage = (lr + 1) // 2
            matches_count = max(1, (b_size // 4) // (1 << (stage - 1)))

            for m_idx in range(1, matches_count + 1):
                m_id = f"LB-R{lr}-M{m_idx}"
                if lr == 1:
                    center_y = cls.PADDING_TOP + 15 + (m_idx - 1) * base_unit + cls.CARD_HEIGHT // 2
                elif lr % 2 == 0:
                    # Same match index as previous odd round
                    prev_id = f"LB-R{lr-1}-M{m_idx}"
                    center_y = match_coords.get(prev_id, (col_x, cls.PADDING_TOP + 30))[1]
                else:
                    # Averages two previous even round matches
                    p1_id = f"LB-R{lr-1}-M{2 * m_idx - 1}"
                    p2_id = f"LB-R{lr-1}-M{2 * m_idx}"
                    y1 = match_coords.get(p1_id, (0, 0))[1]
                    y2 = match_coords.get(p2_id, (0, 0))[1]
                    center_y = (y1 + y2) // 2 if (y1 and y2) else (y1 or y2)

                match_coords[m_id] = (col_x, center_y)

        # 2. Draw connector lines
        for lr in range(1, lb_rounds):
            stage = (lr + 1) // 2
            matches_count = max(1, (b_size // 4) // (1 << (stage - 1)))
            for m_idx in range(1, matches_count + 1):
                m_id = f"LB-R{lr}-M{m_idx}"
                if m_id not in match_coords:
                    continue
                start_x = match_coords[m_id][0] + cls.CARD_WIDTH
                start_y = match_coords[m_id][1]

                target_m = m_idx if (lr % 2 != 0) else ((m_idx + 1) // 2)
                target_id = f"LB-R{lr+1}-M{target_m}"
                if target_id not in match_coords:
                    continue
                end_x = match_coords[target_id][0]
                end_y = match_coords[target_id][1]

                mid_x = start_x + cls.COL_GAP // 2
                draw.line([(start_x, start_y), (mid_x, start_y)], fill=cls.LINE_COLOR, width=2)
                draw.line([(mid_x, start_y), (mid_x, end_y)], fill=cls.LINE_COLOR, width=2)
                draw.line([(mid_x, end_y), (end_x, end_y)], fill=cls.LINE_COLOR, width=2)

        # 3. Draw cards
        for lr in range(1, lb_rounds + 1):
            stage = (lr + 1) // 2
            matches_count = max(1, (b_size // 4) // (1 << (stage - 1)))
            for m_idx in range(1, matches_count + 1):
                m_id = f"LB-R{lr}-M{m_idx}"
                if m_id not in match_coords:
                    continue
                card_x, center_y = match_coords[m_id]
                card_y = center_y - cls.CARD_HEIGHT // 2
                m_data = bracket.matches.get(m_id)
                cls._draw_match_card(draw, card_x, card_y, m_data, m_id, font_player, font_meta)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    @classmethod
    def _render_finals(
        cls,
        bracket: TournamentBracket,
        tournament_name: str,
    ) -> io.BytesIO:
        """Renders Grand Finals & Reset stage with Champion podium banner."""
        canvas_width = 540
        canvas_height = 360

        img = Image.new("RGB", (canvas_width, canvas_height), color=cls.BG_COLOR)
        draw = ImageDraw.Draw(img)

        font_title = _get_font(18, bold=True)
        font_sub = _get_font(11, bold=False)
        font_col = _get_font(13, bold=True)
        font_player = _get_font(12, bold=True)
        font_meta = _get_font(10, bold=False)
        font_champ = _get_font(15, bold=True)

        # Top Banner
        draw.rectangle([0, 0, canvas_width, 58], fill=cls.HEADER_BG)
        draw.line([(0, 58), (canvas_width, 58)], fill=cls.CARD_BORDER, width=1)
        draw.text((cls.PADDING_LEFT, 12), f"{tournament_name} — Grand Finals", fill=cls.TITLE_GOLD, font=font_title)
        draw.text((cls.PADDING_LEFT, 36), "Winners Champion vs Losers Champion", fill=cls.TEXT_MUTED, font=font_sub)

        # Draw Grand Finals card
        gf_match = bracket.matches.get("GF")
        draw.text((60, 80), "Grand Finals (Game 1)", fill=cls.HEADER_TEXT, font=font_col)
        cls._draw_match_card(draw, 60, 105, gf_match, "GF", font_player, font_meta)

        # Draw Reset card if it exists
        reset_match = bracket.matches.get("GF-RESET")
        if reset_match:
            draw.text((300, 80), "Bracket Reset (Game 2)", fill=cls.HEADER_TEXT, font=font_col)
            cls._draw_match_card(draw, 300, 105, reset_match, "GF-RESET", font_player, font_meta)
            # Connector between Game 1 and Game 2
            draw.line([(250, 105 + cls.CARD_HEIGHT // 2), (300, 105 + cls.CARD_HEIGHT // 2)], fill=cls.LINE_COLOR, width=2)

        # Champion Showcase Podium
        if bracket.champion_ign:
            draw.rounded_rectangle([60, 200, 480, 280], radius=8, fill=(35, 30, 20), outline=cls.TITLE_GOLD, width=2)
            draw.text((80, 215), "TOURNAMENT CHAMPION", fill=cls.TITLE_GOLD, font=font_col)
            draw.text((80, 240), f"{bracket.champion_ign}", fill=(255, 255, 255), font=font_champ)
            if bracket.runner_up_ign:
                draw.text((300, 242), f"Runner-up: {bracket.runner_up_ign}", fill=cls.TEXT_MUTED, font=font_sub)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    @classmethod
    def _draw_match_card(
        cls,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        match: Optional[BracketMatch],
        match_id: str,
        font_player: ImageFont.ImageFont,
        font_meta: ImageFont.ImageFont,
    ) -> None:
        """Draws a single rounded match card with Player 1 and Player 2 rows."""
        w = cls.CARD_WIDTH
        h = cls.CARD_HEIGHT
        half_h = cls.SLOT_HEIGHT

        # Match status border color
        border_col = cls.CARD_BORDER
        if match:
            if match.state == "ready":
                border_col = cls.READY_BORDER
            elif match.state == "completed":
                border_col = cls.COMPLETED_BORDER

        # Draw Card Body
        draw.rounded_rectangle([x, y, x + w, y + h], radius=4, fill=cls.CARD_BG, outline=border_col, width=1)
        # Slot Divider
        draw.line([(x, y + half_h), (x + w, y + half_h)], fill=cls.DIVIDER_COLOR, width=1)

        # Player Data
        p1_ign = match.player1_ign if match else "TBD"
        p2_ign = match.player2_ign if match else "TBD"
        p1_seed = match.player1_seed if match else None
        p2_seed = match.player2_seed if match else None
        p1_won = bool(match and match.state == "completed" and match.winner_id == match.player1_id)
        p2_won = bool(match and match.state == "completed" and match.winner_id == match.player2_id)

        # Parse score if recorded (e.g. "2-0", "2 - 1")
        s1 = ""
        s2 = ""
        if match and match.score and "-" in match.score:
            parts = match.score.split("-")
            s1 = parts[0].strip()
            s2 = parts[1].strip() if len(parts) > 1 else ""
        elif match and match.state == "completed":
            s1 = "W" if p1_won else "L"
            s2 = "W" if p2_won else "L"

        # --- Top Slot (Player 1) ---
        cls._draw_player_slot(
            draw=draw,
            x=x,
            y=y,
            w=w,
            h=half_h,
            ign=p1_ign,
            seed=p1_seed,
            score=s1,
            is_winner=p1_won,
            is_loser=p2_won,
            font_player=font_player,
            font_meta=font_meta,
        )

        # --- Bottom Slot (Player 2) ---
        cls._draw_player_slot(
            draw=draw,
            x=x,
            y=y + half_h,
            w=w,
            h=half_h,
            ign=p2_ign,
            seed=p2_seed,
            score=s2,
            is_winner=p2_won,
            is_loser=p1_won,
            font_player=font_player,
            font_meta=font_meta,
        )

    @classmethod
    def _draw_player_slot(
        cls,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        w: int,
        h: int,
        ign: str,
        seed: Optional[int],
        score: str,
        is_winner: bool,
        is_loser: bool,
        font_player: ImageFont.ImageFont,
        font_meta: ImageFont.ImageFont,
    ) -> None:
        """Draws one half of a match card (seed pocket, player name, score badge)."""
        seed_w = 22
        score_w = 26

        # Seed Pocket (Left)
        draw.rectangle([x, y, x + seed_w, y + h], fill=cls.SEED_BG)
        seed_str = str(seed) if seed is not None else ("-" if ign not in ("BYE", "TBD") else "")
        if seed_str:
            draw.text((x + 5, y + 7), seed_str, fill=cls.SEED_TEXT, font=font_meta)

        # Text position
        text_x = x + seed_w + 6

        # Text color
        if ign in ("BYE", "TBD"):
            t_color = cls.TEXT_MUTED
        elif is_winner:
            t_color = (255, 255, 255)
        elif is_loser:
            t_color = (161, 161, 170)
        else:
            t_color = cls.TEXT_WHITE

        # Truncate long IGNs
        display_ign = ign
        if len(display_ign) > 13:
            display_ign = display_ign[:12] + "…"

        draw.text((text_x, y + 7), display_ign, fill=t_color, font=font_player)

        # Score Box (Right)
        if score:
            score_bg = cls.SCORE_WINNER_BG if is_winner else cls.SCORE_LOSER_BG
            score_fg = cls.SCORE_WINNER_TEXT if is_winner else cls.SCORE_LOSER_TEXT
            draw.rectangle([x + w - score_w, y, x + w, y + h], fill=score_bg)
            draw.text((x + w - score_w + 8, y + 7), score, fill=score_fg, font=font_meta)
        elif is_winner:
            draw.rectangle([x + w - score_w, y, x + w, y + h], fill=cls.SCORE_WINNER_BG)
            draw.text((x + w - score_w + 8, y + 7), "W", fill=cls.SCORE_WINNER_TEXT, font=font_meta)
