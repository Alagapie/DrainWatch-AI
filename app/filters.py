from datetime import datetime, timezone


def time_ago(iso: str) -> str:
    try:
        then = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    seconds = int((datetime.now(timezone.utc) - then).total_seconds())
    if seconds < 60:
        return "just now"
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            n = seconds // size
            return f"{n} {unit}{'s' if n > 1 else ''} ago"
    return iso


def short_datetime(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y, %H:%M UTC")
    except (TypeError, ValueError):
        return iso or ""


def register(app) -> None:
    app.add_template_filter(time_ago, "ago")
    app.add_template_filter(short_datetime, "datetime")
