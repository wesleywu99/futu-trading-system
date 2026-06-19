"""US market hours utility.

Handles timezone conversion and DST automatically via zoneinfo.
US regular trading hours: Mon-Fri 9:30 AM - 4:00 PM Eastern Time.
"""

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Regular trading hours in ET
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

# Extended hours
PREMARKET_OPEN = time(4, 0)
AFTERHOURS_CLOSE = time(20, 0)


def is_us_market_open() -> bool:
    """Check if US regular trading session is currently open."""
    now_et = datetime.now(ET)
    # Mon=0, Sun=6 — market closed on weekends
    if now_et.weekday() >= 5:
        return False
    return MARKET_OPEN <= now_et.time() < MARKET_CLOSE


def is_us_extended_hours() -> bool:
    """Check if we are in pre-market or after-hours session."""
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:
        return False
    t = now_et.time()
    return PREMARKET_OPEN <= t < MARKET_OPEN or MARKET_CLOSE <= t < AFTERHOURS_CLOSE


def is_us_tradable_hours() -> bool:
    """Check if any US trading session is open (regular + extended)."""
    return is_us_market_open() or is_us_extended_hours()


def get_us_market_status() -> str:
    """Return a human-readable market status string."""
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:
        return "CLOSED (weekend)"
    t = now_et.time()
    if t < PREMARKET_OPEN:
        return "CLOSED"
    elif t < MARKET_OPEN:
        return "PRE-MARKET"
    elif t < MARKET_CLOSE:
        return "OPEN"
    elif t < AFTERHOURS_CLOSE:
        return "AFTER-HOURS"
    else:
        return "CLOSED"
