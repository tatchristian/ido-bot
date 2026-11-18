"""
Tournament Operations Package.
Contains modular mixins and constants for the TournamentCog system.
"""

from .constants import (
    ANNOUNCE_TARGET_CHOICES,
    BRACKET_FORMAT_CHOICES,
    BRACKET_SECTION_CHOICES,
    EXPORT_FORMAT_CHOICES,
    EXPORT_TARGET_CHOICES,
    HELP_SECTION_CHOICES,
    PANEL_CHOICES,
    REGION_CHOICES,
    REGION_FILTER_CHOICES,
    TIMEZONE_CHOICES,
    WEAPON_CHOICES,
)
from .helpers import TournamentHelpersMixin
from .player_cmds import TournamentPlayerMixin
from .config_cmds import TournamentConfigMixin
from .staff_cmds import TournamentStaffMixin
from .state_cmds import TournamentStateMixin
from .event_cmds import TournamentEventMixin

__all__ = [
    "ANNOUNCE_TARGET_CHOICES",
    "BRACKET_FORMAT_CHOICES",
    "BRACKET_SECTION_CHOICES",
    "EXPORT_FORMAT_CHOICES",
    "EXPORT_TARGET_CHOICES",
    "HELP_SECTION_CHOICES",
    "PANEL_CHOICES",
    "REGION_CHOICES",
    "REGION_FILTER_CHOICES",
    "TIMEZONE_CHOICES",
    "WEAPON_CHOICES",
    "TournamentHelpersMixin",
    "TournamentPlayerMixin",
    "TournamentConfigMixin",
    "TournamentStaffMixin",
    "TournamentStateMixin",
    "TournamentEventMixin",
]
