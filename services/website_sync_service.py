"""
Website REST API Sync Service
Synchronizes scheduled events, tournament results, and clan/player leaderboards
with the official UDA web platform (https://unitedduelingamity.org).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from config import config

logger = logging.getLogger("uda_bot.website_sync")

# Common timezone offsets from UTC in hours (Standard international timezone codes)
TIMEZONE_OFFSETS: Dict[str, float] = {
    "UTC": 0.0,
    "GMT": 0.0,
    "EST": -5.0,
    "EDT": -4.0,
    "CST": -6.0,
    "CDT": -5.0,
    "MST": -7.0,
    "MDT": -6.0,
    "PST": -8.0,
    "PDT": -7.0,
    "AKST": -9.0,
    "AKDT": -8.0,
    "HST": -10.0,
    "AST": -4.0,
    "ADT": -3.0,
    "BRT": -3.0,
    "ART": -3.0,
    "CLT": -3.0,
    "CET": 1.0,
    "CEST": 2.0,
    "BST": 1.0,
    "WET": 0.0,
    "WEST": 1.0,
    "EET": 2.0,
    "EEST": 3.0,
    "MSK": 3.0,
    "GST": 4.0,
    "PKT": 5.0,
    "IST": 5.5,
    "ICT": 7.0,
    "WIB": 7.0,
    "WITA": 8.0,
    "WIT": 9.0,
    "SGT": 8.0,
    "HKT": 8.0,
    "PHT": 8.0,
    "JST": 9.0,
    "KST": 9.0,
    "AWST": 8.0,
    "ACST": 9.5,
    "ACDT": 10.5,
    "AEST": 10.0,
    "AEDT": 11.0,
    "NZST": 12.0,
    "NZDT": 13.0,
}


def resolve_timezone_info(tz_name: str) -> Tuple[timezone, str]:
    """
    Resolves standard international timezone abbreviation or offset string (e.g. 'IST', 'UTC+5:30', 'GMT-4')
    to a python timezone object and canonical code name.
    """
    tz_upper = tz_name.strip().upper()
    if tz_upper in TIMEZONE_OFFSETS:
        return timezone(timedelta(hours=TIMEZONE_OFFSETS[tz_upper])), tz_upper

    # Check for numeric offsets like UTC+5, UTC+5:30, GMT-4, +05:30, etc.
    offset_match = re.match(r"^(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})(?::(\d{2}))?$", tz_upper)
    if offset_match:
        sign = 1.0 if offset_match.group(1) == "+" else -1.0
        hours = float(offset_match.group(2))
        mins = float(offset_match.group(3) or 0)
        total_hours = sign * (hours + (mins / 60.0))
        canonical = f"UTC{offset_match.group(1)}{int(hours):02d}:{int(mins):02d}"
        return timezone(timedelta(hours=total_hours)), canonical

    # Default fallback to EST (-5.0)
    return timezone(timedelta(hours=-5.0)), tz_upper or "EST"


def parse_event_datetime(
    date_str: str,
    time_str: str,
    tz_name: str = "EST",
) -> Tuple[bool, Optional[datetime], str]:
    """
    Parses a user-supplied date, time, and timezone into a timezone-aware UTC datetime.
    Supports formats like:
      Date: 2026-11-15, 11/15/2026, 11/15, This Weekend, Saturday, Sunday, Tomorrow, Today
      Time: 18:00, 6:00 PM, 6pm, 7:30am
      Timezone: Standard international codes (e.g. IST, EST, CST, PST, UTC, CET, JST)
    """
    tz, tz_upper = resolve_timezone_info(tz_name)

    cleaned_date = date_str.strip().lower()
    cleaned_time = time_str.strip()

    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(tz)
    current_year = now_local.year
    parsed_date = None

    # 1. Check relative date keywords (Weekends, Tomorrow, Specific Days of Week)
    weekday_map = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6,
    }

    # Weekend phrases: "this weekend", "the weekend", "weekend", "sat & sun", "saturday & sunday"
    if cleaned_date in ("this weekend", "the weekend", "weekend", "sat & sun", "saturday & sunday", "saturday and sunday"):
        # Target upcoming Saturday
        days_ahead = (5 - now_local.weekday()) % 7
        target_dt = now_local + timedelta(days=days_ahead)
        parsed_date = (target_dt.year, target_dt.month, target_dt.day)
    elif cleaned_date in ("next weekend",):
        days_ahead = ((5 - now_local.weekday()) % 7) + 7
        target_dt = now_local + timedelta(days=days_ahead)
        parsed_date = (target_dt.year, target_dt.month, target_dt.day)
    elif cleaned_date in ("tomorrow",):
        target_dt = now_local + timedelta(days=1)
        parsed_date = (target_dt.year, target_dt.month, target_dt.day)
    elif cleaned_date in ("today",):
        parsed_date = (now_local.year, now_local.month, now_local.day)
    elif cleaned_date in weekday_map:
        target_wd = weekday_map[cleaned_date]
        days_ahead = (target_wd - now_local.weekday()) % 7
        target_dt = now_local + timedelta(days=days_ahead)
        parsed_date = (target_dt.year, target_dt.month, target_dt.day)

    # If not a relative keyword, parse standard calendar patterns
    if not parsed_date:
        date_patterns = [
            ("%Y-%m-%d", False),
            ("%m/%d/%Y", False),
            ("%m-%d-%Y", False),
            ("%m/%d", True),
            ("%m-%d", True),
        ]

        for fmt, needs_year in date_patterns:
            try:
                target_str = f"{date_str.strip()}/{current_year}" if needs_year else date_str.strip()
                target_fmt = f"{fmt}/%Y" if needs_year else fmt
                dt = datetime.strptime(target_str, target_fmt)
                parsed_date = (dt.year, dt.month, dt.day)
                break
            except ValueError:
                continue

    if not parsed_date:
        return (
            False,
            None,
            f"Invalid date format `{date_str}`. Please use `YYYY-MM-DD` (e.g. `2026-11-15`), `MM/DD/YYYY`, or relative keywords like `This Weekend`, `Saturday`, or `Tomorrow`.",
        )

    # 2. Parse Time
    time_clean = re.sub(r"\s+", " ", cleaned_time).upper()
    parsed_time = None

    time_patterns = [
        "%H:%M",
        "%I:%M %p",
        "%I:%M%p",
        "%I %p",
        "%I%p",
    ]

    for fmt in time_patterns:
        try:
            t = datetime.strptime(time_clean, fmt)
            parsed_time = (t.hour, t.minute)
            break
        except ValueError:
            continue

    if not parsed_time:
        return (
            False,
            None,
            f"Invalid time format `{time_str}`. Please use `18:00` (24hr) or `6:00 PM` / `6pm` (12hr).",
        )

    # 3. Construct Datetime in Target Timezone
    try:
        local_dt = datetime(
            year=parsed_date[0],
            month=parsed_date[1],
            day=parsed_date[2],
            hour=parsed_time[0],
            minute=parsed_time[1],
            tzinfo=tz,
        )
    except ValueError as exc:
        return False, None, f"Invalid date/time combination: {exc}"

    # If a day of week or weekend was specified and the time has already passed today, advance by 7 days
    if cleaned_date in weekday_map or cleaned_date in ("this weekend", "the weekend", "weekend", "sat & sun", "saturday & sunday", "saturday and sunday"):
        if local_dt <= now_local:
            local_dt += timedelta(days=7)

    # 4. Check if in the future
    if local_dt <= now_local:
        return (
            False,
            None,
            f"Event time must be in the future. `{local_dt.strftime('%Y-%m-%d %I:%M %p')} {tz_upper}` has already passed.",
        )

    return True, local_dt, ""


def parse_combined_event_datetime(raw_str: str) -> Tuple[bool, Optional[datetime], str]:
    """
    Parses a single combined string like '2026-11-15 18:00 EST', 'This Weekend 18:00 IST',
    or 'Saturday 6:00 PM UTC'. Detects international timezone, time, and date automatically.
    """
    cleaned = raw_str.strip()
    if not cleaned:
        return False, None, "Date and time cannot be empty."

    # Look for timezone abbreviation or offset string (sorted longest first to avoid partial matches)
    tz_str = "EST"
    sorted_tz = sorted(TIMEZONE_OFFSETS.keys(), key=lambda k: len(k), reverse=True)
    for tz_candidate in sorted_tz:
        pattern = rf"\b{tz_candidate}\b"
        if re.search(pattern, cleaned, re.IGNORECASE):
            tz_str = tz_candidate.upper()
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
            break
    else:
        # Check for explicit offset e.g. UTC+5:30 or GMT-4
        offset_match = re.search(r"\b(?:UTC|GMT)?[+-]\d{1,2}(?::\d{2})?\b", cleaned, re.IGNORECASE)
        if offset_match:
            tz_str = offset_match.group(0).upper()
            cleaned = cleaned.replace(offset_match.group(0), "").strip()

    # Clean filler words
    cleaned = re.sub(r"\bat\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace(",", " ").strip()

    # Look for time pattern
    time_match = re.search(
        r"(\d{1,2}:\d{2}\s*(?:AM|PM)?|\d{1,2}\s*(?:AM|PM))", cleaned, re.IGNORECASE
    )
    if time_match:
        time_part = time_match.group(1).strip()
        date_part = cleaned.replace(time_match.group(0), "").strip()
    else:
        # If no time given, check if a weekend / relative keyword was used (default to 18:00)
        lower_cleaned = cleaned.lower()
        if any(kw in lower_cleaned for kw in ("weekend", "saturday", "sunday", "friday", "tomorrow")):
            time_part = "18:00"
            date_part = cleaned
        else:
            return (
                False,
                None,
                f"Could not find a valid time in `{raw_str}`. Example: `2026-11-15 18:00 EST` or `This Weekend 18:00 IST`.",
            )

    if not date_part:
        return (
            False,
            None,
            f"Could not find a valid date in `{raw_str}`. Example: `2026-11-15 18:00 EST` or `This Weekend 18:00 IST`.",
        )

    return parse_event_datetime(date_part, time_part, tz_str)


def parse_duration_and_location(raw_str: str) -> Tuple[float, str]:
    """
    Parses 'Duration & Location' field, e.g. '2 hours | UDA Tournament Hub',
    'Weekend | DUKE Tournament Hub', '3 days | Arena', or '48 hours'.
    Returns (duration_hours, location_string).
    """
    cleaned = raw_str.strip()
    duration = 2.0
    location = f"{config.organization_name} Tournament Hub"

    dur_str = ""
    loc_str = ""
    if "|" in cleaned:
        parts = cleaned.split("|", 1)
        dur_str = parts[0].strip()
        loc_str = parts[1].strip()
        if loc_str:
            location = loc_str
    else:
        dur_str = cleaned

    dur_lower = dur_str.lower().strip()

    # Check multi-day and weekend keywords
    if any(k in dur_lower for k in ("full weekend", "weekend", "sat & sun", "saturday & sunday", "2 days", "two days")):
        duration = 48.0
    elif any(k in dur_lower for k in ("3 days", "three days", "fri-sun", "friday to sunday")):
        duration = 72.0
    elif any(k in dur_lower for k in ("1 day", "one day", "full day", "all day", "24 hours", "24h")):
        duration = 24.0
    else:
        # Check explicit day pattern e.g. "4 days"
        day_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:days?|d)\b", dur_lower)
        if day_match:
            try:
                duration = float(day_match.group(1)) * 24.0
            except ValueError:
                duration = 2.0
        else:
            num_match = re.search(r"(\d+(?:\.\d+)?)", dur_str)
            if num_match:
                try:
                    duration = float(num_match.group(1))
                except ValueError:
                    duration = 2.0
            elif not loc_str and cleaned:
                # If no pipe and no number/keyword matched, treat whole string as location
                location = cleaned

    return max(0.5, duration), location


class WebsiteSyncService:
    """
    Manages REST API synchronization between the Discord Bot and https://unitedduelingamity.org.
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.api_url = api_url or getattr(config, "website_api_url", "https://unitedduelingamity.org/api/sync")
        self.api_key = api_key or getattr(config, "website_api_key", "")

    def is_configured(self) -> bool:
        """Returns True if the API key and URL are configured."""
        return bool(self.api_url and self.api_key and self.api_key != "your_secret_api_key_here")

    async def _post(self, payload: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Internal helper to POST JSON payloads to the website REST API.
        """
        if not self.is_configured():
            return (
                False,
                "Website API Key (`WEBSITE_API_KEY`) is not configured yet in `.env`. Event was created in Discord only.",
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": f"UDA-Discord-Bot/{config.organization_name}",
        }

        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.api_url, json=payload, headers=headers) as resp:
                    resp_text = await resp.text()
                    if resp.status in (200, 201):
                        logger.info("Successfully synced payload to website: status=%d", resp.status)
                        return True, "Synced successfully to unitedduelingamity.org"
                    elif resp.status == 401:
                        logger.warning("Website API rejected authentication (401 Unauthorized)")
                        return False, "Website API error: 401 Unauthorized (Invalid WEBSITE_API_KEY)."
                    elif resp.status == 404:
                        logger.warning("Website API endpoint not found: %s", self.api_url)
                        return False, f"Website API error: 404 Not Found at `{self.api_url}`."
                    else:
                        logger.warning("Website API returned error status %d: %s", resp.status, resp_text[:200])
                        return False, f"Website API returned status {resp.status} ({resp_text[:100]})."
        except aiohttp.ClientConnectorError as exc:
            logger.warning("Failed to connect to website API: %s", exc)
            return False, f"Could not connect to `{self.api_url}` (Server unreachable or offline)."
        except TimeoutError:
            logger.warning("Website API request timed out after 10 seconds.")
            return False, "Website API request timed out after 10 seconds."
        except Exception as exc:
            logger.error("Unexpected error syncing to website: %s", exc, exc_info=True)
            return False, f"Website sync failed: {exc}"

    async def sync_event(self, event_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Pushes a newly created or updated Discord Scheduled Event to the website.
        """
        payload = {
            "type": "event",
            "action": "create",
            "source": "discord_bot",
            "organization": config.organization_name,
            "data": event_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return await self._post(payload)

    async def sync_tournament_results(self, tournament_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Pushes completed tournament bracket results, champions, and standings to the website.
        """
        payload = {
            "type": "tournament_results",
            "action": "completed",
            "source": "discord_bot",
            "organization": config.organization_name,
            "data": tournament_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return await self._post(payload)

    async def sync_leaderboards(
        self,
        clans: List[Dict[str, Any]],
        players: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[bool, str]:
        """
        Pushes current clan rankings and individual player leaderboards to the website.
        """
        payload = {
            "type": "leaderboards",
            "action": "update",
            "source": "discord_bot",
            "organization": config.organization_name,
            "data": {
                "clans": clans,
                "players": players or [],
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return await self._post(payload)

    async def test_connection(self) -> Tuple[bool, str]:
        """
        Tests the REST API connection to the website.
        """
        payload = {
            "type": "ping",
            "source": "discord_bot",
            "organization": config.organization_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return await self._post(payload)
