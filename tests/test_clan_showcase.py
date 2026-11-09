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


def test_parse_name_and_color_override_and_names():
    # Test named colors
    name, color_int, hex_str = parse_name_and_color("Cerberus | gold")
    assert name == "Cerberus"
    assert color_int == 0xD4AF37
    assert hex_str == "#d4af37"

    name_blue, color_int_blue, hex_blue = parse_name_and_color("Aquila | blue")
    assert name_blue == "Aquila"
    assert color_int_blue == 0x3498DB
    assert hex_blue == "#3498db"

    # Test override_color argument (from dropdown selector)
    name_ov, color_int_ov, hex_ov = parse_name_and_color("Apex", override_color="#e74c3c")
    assert name_ov == "Apex"
    assert color_int_ov == 0xE74C3C
    assert hex_ov == "#e74c3c"


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


def test_clan_draft_confirmation_view_structure():
    from cogs.clan_showcase import ClanDraftConfirmationView
    temp_dir = Path(tempfile.mkdtemp())
    try:
        service = ClanShowcaseService(storage=StorageManager(temp_dir / "temp.json"), data_dir=temp_dir)
        draft = {
            "clan_name": "Cerberus Elite",
            "clan_color": "#d4af37",
            "clan_name_color": "Cerberus Elite | #d4af37",
            "metadata": "Region: NA\nLeader: Duke",
            "description": "Premier UDA Clan",
            "activities_motto": "Motto: Power & Glory",
            "logo_url": "https://example.com/logo.png",
        }
        view = ClanDraftConfirmationView(service, draft)
        assert view.color_select.row == 0
        assert any(opt.value == "#d4af37" and opt.default for opt in view.color_select.options)
        labels = [item.label for item in view.children if hasattr(item, "label")]
        assert "Confirm & Send to Staff" in labels
        assert "Custom Hex" in labels
        assert "Edit Info" in labels
        assert "Discard Draft" in labels
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_extract_dominant_color_from_png_and_jpeg():
    import io
    from PIL import Image
    from services.clan_showcase_service import extract_dominant_color_from_bytes

    # Create a red square on black background
    img = Image.new("RGB", (100, 100), (10, 10, 10))
    for x in range(30, 70):
        for y in range(30, 70):
            img.putpixel((x, y), (230, 60, 20))

    # Test JPEG
    jpeg_buf = io.BytesIO()
    img.save(jpeg_buf, format="JPEG")
    res_jpeg = extract_dominant_color_from_bytes(jpeg_buf.getvalue())
    assert res_jpeg is not None
    assert res_jpeg[0].startswith("#")

    # Test PNG
    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")
    res_png = extract_dominant_color_from_bytes(png_buf.getvalue())
    assert res_png is not None
    assert res_png[0].startswith("#")


def test_clan_draft_confirmation_view_preset_selection():
    from cogs.clan_showcase import ClanDraftConfirmationView
    temp_dir = Path(tempfile.mkdtemp())
    try:
        service = ClanShowcaseService(storage=StorageManager(temp_dir / "temp.json"), data_dir=temp_dir)
        draft = {
            "clan_name": "Phoenix Order",
            "clan_color": "#e74c3c",
            "clan_name_color": "Phoenix Order | #e74c3c",
            "metadata": "Region: Global",
            "description": "Rising from the ashes",
            "activities_motto": "Motto: Unbroken",
            "logo_url": "https://example.com/logo.png",
        }
        view = ClanDraftConfirmationView(service, draft)
        red_opt = next(opt for opt in view.color_select.options if opt.value == "#e74c3c")
        assert red_opt.default is True
        assert "Crimson Red" in red_opt.label
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_fetch_image_bytes_validation():
    from services.clan_showcase_service import fetch_image_bytes
    assert run_coro(fetch_image_bytes("invalid_url")) is None
    assert run_coro(fetch_image_bytes("")) is None
    assert run_coro(fetch_image_bytes("ftp://example.com/logo.png")) is None


def test_clan_submission_role_fields_serialization():
    """Verify role_id and role_name serialize and deserialize properly."""
    sub = ClanSubmission(
        id="sub_test_1",
        guild_id=123,
        applicant_id=456,
        applicant_name="Tester",
        clan_name="Test Clan",
        color_hex="#10b981",
        color_int=0x10B981,
        metadata_text="Region: NA",
        description_text="Description",
        activities_motto="Motto",
        logo_url="https://example.com/logo.png",
        role_id=987654321,
        role_name="Test Clan Role",
    )
    data = sub.to_dict()
    assert data["role_id"] == 987654321
    assert data["role_name"] == "Test Clan Role"

    reloaded = ClanSubmission.from_dict(data)
    assert reloaded.role_id == 987654321
    assert reloaded.role_name == "Test Clan Role"


def test_clan_showcase_service_role_panel_and_clanless_persistence():
    """Verify panel info and clanless role ID persist in ClanShowcaseService."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        service = ClanShowcaseService(storage=StorageManager(temp_dir / "temp.json"), data_dir=temp_dir)
        service.set_clan_role_panel_info(1001, 2002, 3003)
        chan_id, msg_id = service.get_clan_role_panel_info(1001)
        assert chan_id == 2002
        assert msg_id == 3003

        service.set_clanless_role_id(1001, 7777)
        assert service.get_clanless_role_id(1001) == 7777
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_clan_showcase_service_get_approved_clans_and_set_role():
    """Verify get_approved_clans filters by status and sorts alphabetically."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        service = ClanShowcaseService(storage=StorageManager(temp_dir / "temp.json"), data_dir=temp_dir)
        # Create Zeta (approved), Beta (pending), Alpha (approved)
        s_zeta = service.create_submission(1, 10, "UserZ", "Zeta Clan", "#ffffff", "meta", "desc", "motto")
        s_beta = service.create_submission(1, 11, "UserB", "Beta Clan", "#ffffff", "meta", "desc", "motto")
        s_alpha = service.create_submission(1, 12, "UserA", "Alpha Clan", "#ffffff", "meta", "desc", "motto")

        # Approve Zeta and Alpha
        service.approve_submission(s_zeta.id, 99, "Admin", 1001)
        service.approve_submission(s_alpha.id, 99, "Admin", 1002)

        approved = service.get_approved_clans(1)
        assert len(approved) == 2
        assert [c.clan_name for c in approved] == ["Alpha Clan", "Zeta Clan"]

        # Link role to Alpha Clan
        service.set_clan_role(s_alpha.id, 5555, "Alpha Clan Role")
        updated_alpha = service.get_submission(s_alpha.id)
        assert updated_alpha.role_id == 5555
        assert updated_alpha.role_name == "Alpha Clan Role"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_build_clan_role_panel_embed():
    """Verify clan role panel embed builder produces expected content."""
    from utils.ui import build_clan_role_panel_embed

    clans = [
        ClanSubmission(
            id="1",
            guild_id=1,
            applicant_id=10,
            applicant_name="A",
            clan_name="Solaris",
            color_hex="#fff",
            color_int=0xFFFFFF,
            metadata_text="meta",
            description_text="desc",
            activities_motto="motto",
            logo_url="https://example.com/logo.png",
        ),
        ClanSubmission(
            id="2",
            guild_id=1,
            applicant_id=20,
            applicant_name="B",
            clan_name="Lunaris",
            color_hex="#000",
            color_int=0x000000,
            metadata_text="meta",
            description_text="desc",
            activities_motto="motto",
            logo_url="https://example.com/logo.png",
        ),
    ]

    embed = build_clan_role_panel_embed(clans, org_name="DUKE")
    assert "DUKE Clan Alignment" in embed.title
    assert "`2` active clan(s)" in embed.description
    assert "Dropdown Menu" in embed.description
    assert "Search by Keyword" in embed.description
    assert "Clanless" in embed.description


def test_clan_role_panel_view_structure():
    """Verify ClanRoleAssignmentPanelView buttons and dropdowns."""
    from cogs.clan_showcase import ClanRoleAssignmentPanelView

    temp_dir = Path(tempfile.mkdtemp())
    try:
        service = ClanShowcaseService(storage=StorageManager(temp_dir / "temp.json"), data_dir=temp_dir)
        clans = [
            ClanSubmission(
                id="c1",
                guild_id=1,
                applicant_id=10,
                applicant_name="A",
                clan_name="Omega",
                color_hex="#fff",
                color_int=0xFFFFFF,
                metadata_text="meta",
                description_text="desc",
                activities_motto="motto",
                logo_url="https://example.com/logo.png",
                role_id=111,
            ),
            ClanSubmission(
                id="c2",
                guild_id=1,
                applicant_id=20,
                applicant_name="B",
                clan_name="Delta",
                color_hex="#000",
                color_int=0x000000,
                metadata_text="meta",
                description_text="desc",
                activities_motto="motto",
                logo_url="https://example.com/logo.png",
                role_id=222,
            ),
        ]

        view = ClanRoleAssignmentPanelView(service, clans=clans)
        custom_ids = [item.custom_id for item in view.children if hasattr(item, "custom_id")]

        assert "btn_clan_role_search" in custom_ids
        assert "btn_clan_role_leave" in custom_ids
        assert "btn_clan_role_help" in custom_ids
        assert "clan_role_menu_0" in custom_ids
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_clan_role_panel_multi_chunk_dropdown():
    """Verify that > 25 clans are chunked across multiple dropdown menus."""
    from cogs.clan_showcase import ClanRoleAssignmentPanelView
    import discord

    temp_dir = Path(tempfile.mkdtemp())
    try:
        service = ClanShowcaseService(storage=StorageManager(temp_dir / "temp.json"), data_dir=temp_dir)
        many_clans = [
            ClanSubmission(
                id=f"c_{i}",
                guild_id=1,
                applicant_id=i,
                applicant_name=f"User_{i}",
                clan_name=f"Clan {i:02d}",
                color_hex="#ffffff",
                color_int=0xFFFFFF,
                metadata_text="meta",
                description_text="desc",
                activities_motto="motto",
                logo_url="https://example.com/logo.png",
                role_id=1000 + i,
            )
            for i in range(30)
        ]

        view = ClanRoleAssignmentPanelView(service, clans=many_clans)
        selects = [item for item in view.children if isinstance(item, discord.ui.Select)]
        assert len(selects) == 2
        assert selects[0].custom_id == "clan_role_menu_0"
        assert len(selects[0].options) == 25
        assert selects[1].custom_id == "clan_role_menu_1"
        assert len(selects[1].options) == 5
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_clan_role_helpers_and_clanless_lookup():
    """Verify _get_clanless_role finds configured ID and falls back to name matching."""
    from unittest.mock import MagicMock
    from cogs.clan_showcase import ClanShowcaseCog

    temp_dir = Path(tempfile.mkdtemp())
    try:
        service = ClanShowcaseService(storage=StorageManager(temp_dir / "temp.json"), data_dir=temp_dir)
        bot = MagicMock()
        cog = ClanShowcaseCog(bot, service=service)

        guild = MagicMock()
        role_configured = MagicMock()
        role_configured.id = 8888
        role_configured.name = "Unranked Duelists"

        role_named_clanless = MagicMock()
        role_named_clanless.id = 9999
        role_named_clanless.name = "Clanless"

        guild.roles = [role_configured, role_named_clanless]
        guild.get_role.side_effect = lambda rid: role_configured if rid == 8888 else (role_named_clanless if rid == 9999 else None)

        # 1. Without configuration: matches by name "clanless"
        found = cog._get_clanless_role(guild)
        assert found == role_named_clanless

        # 2. With configured ID: returns configured role
        service.set_clanless_role_id(guild.id, 8888)
        found_configured = cog._get_clanless_role(guild)
        assert found_configured == role_configured
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_clan_sync_roles_and_role_update_listener():
    """Verify scanning roles with '//' imports clans and on_guild_role_update updates them."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from cogs.clan_showcase import ClanShowcaseCog
    import discord

    temp_dir = Path(tempfile.mkdtemp())
    try:
        service = ClanShowcaseService(storage=StorageManager(temp_dir / "temp.json"), data_dir=temp_dir)
        bot = MagicMock()
        cog = ClanShowcaseCog(bot, service=service)
        cog._refresh_clan_role_panel = AsyncMock()

        guild = MagicMock()
        guild.id = 12345
        guild.name = "Test Guild"
        guild.owner_id = 1

        role1 = MagicMock()
        role1.id = 101
        role1.name = "Blue Fire //"
        role1.is_default.return_value = False
        role1.managed = False
        role1.color.value = 0x3498DB
        role1.members = [MagicMock(), MagicMock()]

        role2 = MagicMock()
        role2.id = 102
        role2.name = "🌊 MIZU //"
        role2.is_default.return_value = False
        role2.managed = False
        role2.color.value = 0x00E5FF
        role2.members = [MagicMock()]

        normal_role = MagicMock()
        normal_role.id = 999
        normal_role.name = "Member"
        normal_role.is_default.return_value = False
        normal_role.managed = False

        guild.roles = [role1, role2, normal_role]

        ctx = MagicMock()
        ctx.guild = guild
        ctx.author = MagicMock()
        ctx.author.id = 1
        guild.get_member.return_value = ctx.author
        async def dummy_refresh(*args, **kwargs):
            pass
        cog._refresh_clan_role_panel = dummy_refresh

        async def dummy_send(*args, **kwargs):
            pass
        ctx.send = dummy_send

        run_coro(cog.clan_sync_roles_prefix.callback(cog, ctx, suffix="//"))

        approved = service.get_approved_clans(guild.id)
        assert len(approved) == 2
        names = [c.clan_name for c in approved]
        assert "Blue Fire" in names
        assert "🌊 MIZU" in names

        blue_fire = next(c for c in approved if c.clan_name == "Blue Fire")
        assert blue_fire.role_id == 101
        assert blue_fire.status == "approved"

        # Now test on_guild_role_update: rename Blue Fire // -> Blue Fire
        before_role = MagicMock()
        before_role.id = 101
        before_role.name = "Blue Fire //"
        before_role.color.value = 0x3498DB

        after_role = MagicMock()
        after_role.guild = guild
        after_role.id = 101
        after_role.name = "Blue Fire"
        after_role.color.value = 0xFF5500

        run_coro(cog.on_guild_role_update(before_role, after_role))

        updated_bf = service.get_submission(blue_fire.id)
        assert updated_bf.clan_name == "Blue Fire"
        assert updated_bf.role_name == "Blue Fire"
        assert updated_bf.color_int == 0xFF5500
        assert updated_bf.color_hex == "#ff5500"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)






