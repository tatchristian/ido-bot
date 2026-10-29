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

# Common timezone offsets from UTC in hours
TIMEZONE_OFFSETS: Dict[str, float] = {
    "EST": -5.0,
    "EDT": -4.0,
    "CST": -6.0,
    "CDT": -5.0,
    "MST": -7.0,
    "MDT": -6.0,
    "PST": -8.0,
    "PDT": -7.0,
    "UTC": 0.0,
    "GMT": 0.0,
    "CET": 1.0,
    "CEST": 2.0,
    "BST": 1.0,
    "IST": 5.5,
    "AEST": 10.0,
    "AEDT": 11.0,
}


def parse_event_datetime(
    date_str: str,
    time_str: str,
    tz_name: str = "EST",
) -> Tuple[bool, Optional[datetime], str]:
    """
    Parses a user-supplied date, time, and timezone into a timezone-aware UTC datetime.
    Supports formats like:
      Date: 2026-11-15, 11/15/2026, 11/15
      Time: 18:00, 6:00 PM, 6pm, 7:30am
      Timezone: EST, CST, PST, UTC, CET, IST, etc.
    """
    tz_upper = tz_name.strip().upper()
    offset_hours = TIMEZONE_OFFSETS.get(tz_upper, -5.0)  # Default to EST (-5)
    tz = timezone(timedelta(hours=offset_hours))

    cleaned_date = date_str.strip()
    cleaned_time = time_str.strip()

    # 1. Parse Date
    now_utc = datetime.now(timezone.utc)
    current_year = now_utc.year
    parsed_date = None

    date_patterns = [
        ("%Y-%m-%d", False),
        ("%m/%d/%Y", False),
        ("%m-%d-%Y", False),
        ("%m/%d", True),
        ("%m-%d", True),
    ]

    for fmt, needs_year in date_patterns:
        try:
            target_str = f"{cleaned_date}/{current_year}" if needs_year else cleaned_date
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
            f"Invalid date format `{date_str}`. Please use `YYYY-MM-DD` (e.g. `2026-11-15`) or `MM/DD/YYYY` (e.g. `11/15/2026`).",
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

    # 4. Check if in the future
    if local_dt <= now_utc:
        return (
            False,
            None,
            f"Event time must be in the future. `{local_dt.strftime('%Y-%m-%d %I:%M %p')} {tz_upper}` has already passed.",
        )

    return True, local_dt, ""


def parse_combined_event_datetime(raw_str: str) -> Tuple[bool, Optional[datetime], str]:
    """
    Parses a single combined string like '2026-11-15 18:00 EST' or '11/15/2026 6:00 PM EST'.
    Detects timezone, time, and date automatically.
    """
    cleaned = raw_str.strip()
    if not cleaned:
        return False, None, "Date and time cannot be empty."

    # Look for timezone abbreviation (e.g. EST, CST, PST, UTC, CET, IST)
    tz_str = "EST"
    for tz_candidate in TIMEZONE_OFFSETS.keys():
        pattern = rf"\b{tz_candidate}\b"
        if re.search(pattern, cleaned, re.IGNORECASE):
            tz_str = tz_candidate.upper()
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
            break

    # Clean filler words
    cleaned = re.sub(r"\bat\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace(",", " ").strip()

    # Look for time pattern
    time_match = re.search(
        r"(\d{1,2}:\d{2}\s*(?:AM|PM)?|\d{1,2}\s*(?:AM|PM))", cleaned, re.IGNORECASE
    )
    if not time_match:
        return (
            False,
            None,
            f"Could not find a valid time in `{raw_str}`. Example: `2026-11-15 18:00 EST` or `11/15/2026 6:00 PM EST`.",
        )

    time_part = time_match.group(1).strip()
    # Date part is whatever is left after extracting the time
    date_part = cleaned.replace(time_match.group(0), "").strip()

    if not date_part:
        return (
            False,
            None,
            f"Could not find a valid date in `{raw_str}`. Example: `2026-11-15 18:00 EST`.",
        )

    return parse_event_datetime(date_part, time_part, tz_str)


def parse_duration_and_location(raw_str: str) -> Tuple[float, str]:
    """
    Parses 'Duration & Location' field, e.g. '2 hours | UDA Tournament Hub' or '3 | Arena'.
    Returns (duration_hours, location_string).
    """
    cleaned = raw_str.strip()
    duration = 2.0
    location = f"{config.organization_name} Tournament Hub"

    if "|" in cleaned:
        parts = cleaned.split("|", 1)
        dur_str = parts[0].strip()
        loc_str = parts[1].strip()
        num_match = re.search(r"(\d+(?:\.\d+)?)", dur_str)
        if num_match:
            try:
                duration = float(num_match.group(1))
            except ValueError:
                duration = 2.0
        if loc_str:
            location = loc_str
    else:
        num_match = re.match(r"^(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)?$", cleaned, re.IGNORECASE)
        if num_match:
            try:
                duration = float(num_match.group(1))
            except ValueError:
                duration = 2.0
        elif cleaned:
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
