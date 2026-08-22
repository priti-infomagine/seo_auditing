from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """
    Ensure a datetime is timezone-aware in UTC.

    If naive, assume it is already UTC and attach tzinfo=timezone.utc.
    If aware, convert to UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso(dt: datetime | None) -> str | None:
    """
    Serialize a datetime to ISO 8601 with explicit UTC offset.

    Raises ValueError if a naive datetime is passed, to prevent silent
    timezone bugs.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        raise ValueError(
            f"Naive datetime passed to to_iso(): {dt!r}. "
            "Use utc_now() or ensure_utc() to create timezone-aware datetimes."
        )
    return dt.isoformat()
