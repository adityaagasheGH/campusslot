"""Time helpers. CampusSlot runs on one fixed time zone (IST, UTC+05:30)."""
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")

_clock = None  # tests replace this with a function returning an aware datetime


def set_clock(fn):
    global _clock
    _clock = fn


def now():
    return _clock() if _clock else datetime.now(IST)


def today():
    return now().date()


def iso_now():
    return now().isoformat(timespec="seconds")


def parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def hhmm_to_minutes(hhmm):
    """'0930' or '09:30' -> 570."""
    s = hhmm.replace(":", "")
    if len(s) != 4 or not s.isdigit():
        raise ValueError(hhmm)
    h, m = int(s[:2]), int(s[2:])
    if h > 24 or m > 59 or (h == 24 and m):
        raise ValueError(hhmm)
    return h * 60 + m


def minutes_to_hhmm(minutes):
    return f"{minutes // 60:02d}{minutes % 60:02d}"


def at(day, hhmm):
    """Aware datetime for a date and an 'HHMM' time (24:00 rolls to the next day)."""
    return datetime(day.year, day.month, day.day, tzinfo=IST) + timedelta(minutes=hhmm_to_minutes(hhmm))
