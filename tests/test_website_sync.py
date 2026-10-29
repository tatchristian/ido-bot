"""
Unit tests for Website REST API Sync Service and Event Datetime Parser.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services.website_sync_service import (
    TIMEZONE_OFFSETS,
    WebsiteSyncService,
    parse_event_datetime,
)


def test_parse_event_datetime_valid_24hr():
    # Future date
    future_year = datetime.now(timezone.utc).year + 1
    date_str = f"{future_year}-11-15"
    time_str = "18:30"

    valid, dt, err = parse_event_datetime(date_str, time_str, "EST")
    assert valid is True
    assert dt is not None
    assert dt.year == future_year
    assert dt.month == 11
    assert dt.day == 15
    assert dt.hour == 18
    assert dt.minute == 30
    # EST is UTC-5
    assert dt.utcoffset() == timedelta(hours=-5)


def test_parse_event_datetime_valid_12hr_pm():
    future_year = datetime.now(timezone.utc).year + 1
    date_str = f"12/25/{future_year}"
    time_str = "7:45 PM"

    valid, dt, err = parse_event_datetime(date_str, time_str, "PST")
    assert valid is True
    assert dt is not None
    assert dt.hour == 19
    assert dt.minute == 45
    # PST is UTC-8
    assert dt.utcoffset() == timedelta(hours=-8)


def test_parse_event_datetime_past_date_fails():
    # Past date in 2020
    valid, dt, err = parse_event_datetime("2020-01-01", "12:00", "UTC")
    assert valid is False
    assert dt is None
    assert "future" in err.lower()


def test_parse_event_datetime_invalid_formats():
    valid1, _, err1 = parse_event_datetime("not-a-date", "18:00")
    assert valid1 is False
    assert "invalid date" in err1.lower()

    future_year = datetime.now(timezone.utc).year + 1
    valid2, _, err2 = parse_event_datetime(f"{future_year}-11-15", "not-a-time")
    assert valid2 is False
    assert "invalid time" in err2.lower()


def test_website_sync_service_configuration():
    # Unconfigured (default)
    service_unconf = WebsiteSyncService(api_url="https://example.com/api", api_key="")
    assert service_unconf.is_configured() is False

    service_placeholder = WebsiteSyncService(
        api_url="https://example.com/api", api_key="your_secret_api_key_here"
    )
    assert service_placeholder.is_configured() is False

    # Configured
    service_conf = WebsiteSyncService(
        api_url="https://unitedduelingamity.org/api/sync", api_key="sec_uda_12345"
    )
    assert service_conf.is_configured() is True


def test_website_sync_unconfigured_skips_cleanly():
    service = WebsiteSyncService(api_url="https://example.com", api_key="")
    # Synchronously call coroutine without network
    coro = service.sync_event({"name": "Test Event"})
    try:
        coro.send(None)
    except StopIteration as exc:
        ok, msg = exc.value
        assert ok is False
        assert "not configured" in msg.lower()


def test_website_sync_payload_structures():
    service = WebsiteSyncService(api_url="https://example.com", api_key="")

    # Verify sync_tournament_results returns unconfigured message gracefully
    coro = service.sync_tournament_results({"name": "UDA Cup"})
    try:
        coro.send(None)
    except StopIteration as exc:
        ok, msg = exc.value
        assert ok is False
        assert "not configured" in msg.lower()
