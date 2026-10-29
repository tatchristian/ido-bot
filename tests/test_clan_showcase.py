"""
Unit tests for Clan Showcase Service, embed builder, and submission lifecycle.
"""

import shutil
import tempfile
from pathlib import Path
import pytest

from services.clan_showcase_service import (
    DEFAULT_CLAN_COLOR,
    ClanShowcaseService,
    ClanSubmission,
    build_clan_showcase_embed,
    parse_name_and_color,
    resolve_image_url,
    validate_image_url,
)
from utils.storage import StorageManager


def run_coro(coro):
    """Executes a pure coroutine without spinning an event loop."""
    try:
        coro.send(None)
    except StopIteration as exc:
        return exc.value
    raise RuntimeError("Coroutine did not finish synchronously")


def test_parse_name_and_color_standard():
    name, color_int, hex_str = parse_name_and_color("Yume | #38bdf8")
    assert name == "Yume"
    assert color_int == 0x38BDF8
    assert hex_str == "#38bdf8"


def test_parse_name_and_color_without_hash():
    name, color_int, hex_str = parse_name_and_color("Vanguard | FF5500")
    assert name == "Vanguard"
    assert color_int == 0xFF5500
    assert hex_str == "#ff5500"


def test_parse_name_and_color_comma_separated():
    name, color_int, hex_str = parse_name_and_color("Eclipse, #00FFCC")
    assert name == "Eclipse"
    assert color_int == 0x00FFCC
    assert hex_str == "#00ffcc"


def test_parse_name_and_color_fallback():
    # No color provided
    name, color_int, hex_str = parse_name_and_color("Solo Warriors")
    assert name == "Solo Warriors"
    assert color_int == DEFAULT_CLAN_COLOR
    assert hex_str == "#10b981"

    # Invalid hex provided
    name2, color_int2, hex_str2 = parse_name_and_color("Solo Warriors | not-a-color")
    assert name2 == "Solo Warriors"
    assert color_int2 == DEFAULT_CLAN_COLOR
    assert hex_str2 == "#10b981"


def test_validate_image_url():
    valid, _ = validate_image_url("https://cdn.discordapp.com/attachments/123/456/logo.png")
    assert valid is True

    valid_http, _ = validate_image_url("http://i.imgur.com/logo.jpg")
    assert valid_http is True

    invalid_proto, err1 = validate_image_url("ftp://example.com/logo.png")
    assert invalid_proto is False
    assert "http://" in err1 or "https://" in err1

    invalid_text, err2 = validate_image_url("not a url")
    assert invalid_text is False

    invalid_spaces, err3 = validate_image_url("https://example.com/bad url.png")
    assert invalid_spaces is False
    assert "spaces" in err3


def test_resolve_image_url_direct_link():
    valid, resolved, err = run_coro(
        resolve_image_url(None, "https://cdn.discordapp.com/attachments/123/456/logo.png")
    )
    assert valid is True
    assert resolved == "https://cdn.discordapp.com/attachments/123/456/logo.png"
    assert err == ""

    valid_gif, resolved_gif, _ = run_coro(
        resolve_image_url(None, "https://media.tenor.com/image.gif")
    )
    assert valid_gif is True
    assert resolved_gif == "https://media.tenor.com/image.gif"


def test_resolve_image_url_invalid():
    valid_empty, _, err_empty = run_coro(resolve_image_url(None, "   "))
    assert valid_empty is False
    assert "empty" in err_empty.lower()

    valid_bad, _, err_bad = run_coro(resolve_image_url(None, "not_a_link"))
    assert valid_bad is False
    assert "http" in err_bad.lower()


def test_build_clan_showcase_embed():
    clan_name = "Yume"
    color_int = 0x38BDF8
    meta = "Region: Mumbai, India\nFounded: 7 July\nLeader: Ragnarok\nStatus: Active"
    desc = "Yume is a competitive clan."
    act = "• Tournaments\n• Scrims\n\nMotto: \"Dream. Train. Dominate.\" 🌙"
    logo = "https://cdn.discordapp.com/attachments/123/456/yume.png"

    embed = build_clan_showcase_embed(
        clan_name=clan_name,
        color_int=color_int,
        metadata_text=meta,
        description_text=desc,
        activities_motto_text=act,
        logo_url=logo,
    )

    # 1. Author Name & Icon
    assert embed.author.name == "Yume"
    assert embed.author.icon_url == logo

    # 2. Embed Color
    assert embed.color.value == 0x38BDF8

    # 3. Main Emblem Image
    assert embed.image.url == logo

    # 4. Description Blocks
    assert "Region: Mumbai, India" in embed.description
    assert "Description:" in embed.description
    assert "Yume is a competitive clan." in embed.description
    assert "Main Activities:" in embed.description
    assert "Dream. Train. Dominate." in embed.description


def test_clan_showcase_service_lifecycle():
    temp_dir = Path(tempfile.mkdtemp())
    try:
        storage = StorageManager(temp_dir / "test_clan.json")
        service = ClanShowcaseService(storage=storage, data_dir=temp_dir)

        # 1. Configure guild channels
        service.set_guild_channels(
            guild_id=999,
            showcase_channel_id=1001,
            staff_review_channel_id=1002,
        )
        s_id, r_id = service.get_guild_channels(999)
        assert s_id == 1001
        assert r_id == 1002

        # 2. Create submission
        sub = service.create_submission(
            guild_id=999,
            applicant_id=12345,
            applicant_name="Ragnarok#0001",
            clan_name_color_raw="Yume | #38bdf8",
            metadata_text="Region: Mumbai, India",
            description_text="Competitive clan",
            activities_motto="• Tournaments",
            logo_url="https://example.com/logo.png",
        )
        assert sub.clan_name == "Yume"
        assert sub.color_hex == "#38bdf8"
        assert sub.status == "pending"

        # 3. Link staff message
        service.link_staff_message(sub.id, message_id=8888)
        found_sub = service.get_submission_by_message_id(8888)
        assert found_sub is not None
        assert found_sub.id == sub.id

        # 4. Approve submission
        approved = service.approve_submission(
            sub_id=sub.id,
            reviewed_by_id=555,
            reviewed_by_name="StaffMod",
            showcase_message_id=9999,
        )
        assert approved.status == "approved"
        assert approved.reviewed_by_id == 555
        assert approved.showcase_message_id == 9999

        # 5. Verify persistence across fresh service instance reload
        fresh_service = ClanShowcaseService(
            storage=StorageManager(temp_dir / "test_clan.json"),
            data_dir=temp_dir,
        )
        reloaded_sub = fresh_service.get_submission(sub.id)
        assert reloaded_sub is not None
        assert reloaded_sub.clan_name == "Yume"
        assert reloaded_sub.status == "approved"

        # 6. Rejection flow
        sub2 = fresh_service.create_submission(
            guild_id=999,
            applicant_id=67890,
            applicant_name="RejectMe#0002",
            clan_name_color_raw="Rejected Clan",
            metadata_text="Meta",
            description_text="Desc",
            activities_motto="Act",
            logo_url="https://example.com/logo2.png",
        )
        rejected = fresh_service.reject_submission(
            sub_id=sub2.id,
            reviewed_by_id=555,
            reviewed_by_name="StaffMod",
            reason="Invalid logo image format.",
        )
        assert rejected.status == "rejected"
        assert rejected.reject_reason == "Invalid logo image format."

        # 7. Search and Update flow (Admin editing)
        found_by_name = fresh_service.search_submission(999, "yume")
        assert found_by_name is not None
        assert found_by_name.id == sub.id

        updated = fresh_service.update_submission(
            sub_id=sub.id,
            clan_name="Yume Reborn",
            color_hex="#ff0055",
            color_int=0xFF0055,
            metadata_text="Region: Global\nStatus: Elite",
        )
        assert updated is not None
        assert updated.clan_name == "Yume Reborn"
        assert updated.color_hex == "#ff0055"
        assert updated.metadata_text == "Region: Global\nStatus: Elite"

        # 8. User Draft Management
        fresh_service.save_draft(999, 12345, {"clan_name_color": "DraftClan"})
        draft = fresh_service.get_draft(999, 12345)
        assert draft is not None
        assert draft["clan_name_color"] == "DraftClan"

        fresh_service.clear_draft(999, 12345)
        assert fresh_service.get_draft(999, 12345) is None

        # 9. Applicant Submissions Lookup
        applicant_sub = fresh_service.get_applicant_submission(999, 12345)
        assert applicant_sub is not None
        assert applicant_sub.clan_name == "Yume Reborn"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

