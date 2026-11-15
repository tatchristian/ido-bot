"""
Tournament Cog Module.
Serves as the main orchestrator for the tournament subsystem.
Composes modular mixins from `cogs.tournament_ops`:
- TournamentHelpersMixin: Lifecycle, background loops, panels, autocomplete & role helpers.
- TournamentPlayerMixin: Player slash commands (/register, /unregister, /sub, etc.).
- TournamentConfigMixin: Server configuration (/config, /set-channel, /post panels).
- TournamentStaffMixin: Staff operations and bracket management (/t ...).
- TournamentStateMixin: Server state snapshot & disaster recovery (/state ...).
- TournamentEventMixin: Discord event scheduling and calendar sync (/event ...).
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

import config
from services.tournament_service import TournamentService

# ---------------------------------------------------------------------------
# Backwards-compatibility re-exports for existing tests and external consumers
# ---------------------------------------------------------------------------
from utils.tournament_embeds import (
    build_checkin_panel_embed,
    build_checkin_receipt_embed,
    build_help_embed,
    build_registration_closed_embed,
    build_registration_panel_embed,
    build_roster_embed,
    build_staff_guide_embed,
    build_staff_panel_embed,
    build_status_embed,
    build_subs_closed_embed,
    build_subs_panel_embed,
    build_tournament_reminder_embed,
)
from utils.tournament_views import (
    HelpView,
    StaffAnnounceModal,
    StaffCreateTournamentModal,
    StaffOpenTournamentModal,
    StaffSetTimeModal,
    TournamentCheckinPanelView,
    TournamentClosedRegistrationView,
    TournamentClosedSubsView,
    TournamentEventModal,
    TournamentEventPanelView,
    TournamentRegistrationPanelView,
    TournamentStaffGuideSelect,
    TournamentStaffGuideView,
    TournamentStaffPanelView,
    TournamentSubsPanelView,
    UserRegistrationModal,
    UserSubRegistrationModal,
    check_is_event_admin,
    check_is_tournament_admin,
    is_event_admin,
    is_server_admin,
    is_tournament_admin,
    is_tournament_admin_prefix,
)

from .tournament_ops import (
    ANNOUNCE_TARGET_CHOICES,
    EXPORT_FORMAT_CHOICES,
    EXPORT_TARGET_CHOICES,
    HELP_SECTION_CHOICES,
    PANEL_CHOICES,
    REGION_CHOICES,
    REGION_FILTER_CHOICES,
    TIMEZONE_CHOICES,
    WEAPON_CHOICES,
    TournamentConfigMixin,
    TournamentEventMixin,
    TournamentHelpersMixin,
    TournamentPlayerMixin,
    TournamentStaffMixin,
    TournamentStateMixin,
)

logger = logging.getLogger(__name__)


class TournamentCog(
    commands.Cog,
    TournamentHelpersMixin,
    TournamentPlayerMixin,
    TournamentConfigMixin,
    TournamentStaffMixin,
    TournamentStateMixin,
    TournamentEventMixin,
):
    """Slash commands and management orchestrator for UDA Tournament Roster and Substitute Queue."""

    def __init__(self, bot: commands.Bot, service: TournamentService):
        self.bot = bot
        self.service = service


async def setup(bot: commands.Bot) -> None:
    """Cog setup registration entry point."""
    service: Optional[TournamentService] = getattr(bot, "tournament_service", None)
    if not service:
        from utils.storage import StorageManager
        storage = StorageManager(config.tournament_file, config.backup_dir, config.max_backups)
        service = TournamentService(storage=storage)
        bot.tournament_service = service
    await bot.add_cog(TournamentCog(bot, service))


__all__ = [
    "TournamentCog",
    "setup",
    "ANNOUNCE_TARGET_CHOICES",
    "EXPORT_FORMAT_CHOICES",
    "EXPORT_TARGET_CHOICES",
    "HELP_SECTION_CHOICES",
    "PANEL_CHOICES",
    "REGION_CHOICES",
    "REGION_FILTER_CHOICES",
    "TIMEZONE_CHOICES",
    "WEAPON_CHOICES",
    "HelpView",
    "TournamentEventModal",
    "TournamentEventPanelView",
    "TournamentStaffGuideSelect",
    "TournamentStaffGuideView",
    "StaffCreateTournamentModal",
    "StaffOpenTournamentModal",
    "StaffAnnounceModal",
    "StaffSetTimeModal",
    "TournamentStaffPanelView",
    "UserRegistrationModal",
    "TournamentRegistrationPanelView",
    "TournamentClosedRegistrationView",
    "UserSubRegistrationModal",
    "TournamentSubsPanelView",
    "TournamentClosedSubsView",
    "TournamentCheckinPanelView",
    "check_is_tournament_admin",
    "check_is_event_admin",
    "is_tournament_admin",
    "is_tournament_admin_prefix",
    "is_event_admin",
    "is_server_admin",
    "build_checkin_panel_embed",
    "build_checkin_receipt_embed",
    "build_help_embed",
    "build_registration_closed_embed",
    "build_registration_panel_embed",
    "build_roster_embed",
    "build_staff_guide_embed",
    "build_staff_panel_embed",
    "build_status_embed",
    "build_subs_closed_embed",
    "build_subs_panel_embed",
    "build_tournament_reminder_embed",
]
