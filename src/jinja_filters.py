from datetime import timedelta
from zoneinfo import ZoneInfo


def dt_format(value, format="%H:%M", tz=None) -> str:
    """Format a datetime object according to the specified format and timezone.

    Args:
        value: The datetime object to format
        format: The format string (default: '%H:%M')
        tz: Optional timezone name (e.g., 'UTC', 'America/New_York')
            If provided, the datetime will be converted to this timezone before formatting

    Returns:
        Formatted datetime string
    """
    if isinstance(value, str):
        return value

    if tz is not None and hasattr(value, "astimezone"):
        timezone = ZoneInfo(tz)
        value = value.astimezone(timezone)

    return value.strftime(format)


def td_format(value) -> str:
    """Format a timedelta object into a readable string.

    Formats as "2d 3h 45m 12s" but only displays non-zero elements.
    For example, if the duration is only 12 seconds, it returns "12s".

    Args:
        value: The timedelta object to format

    Returns:
        Formatted timedelta string
    """
    if not isinstance(value, timedelta):
        return str(value)

    # Extract days, hours, minutes, seconds
    total_seconds = int(value.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    # Build the string parts, only including non-zero elements
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if (
        seconds > 0 or not parts
    ):  # Include seconds if non-zero or if all other parts are zero
        parts.append(f"{seconds}s")

    # Join the parts with spaces
    return " ".join(parts)


def register_filters(app):
    """Register all Jinja template filters with the Flask application.

    Args:
        app: Flask application instance
    """
    app.jinja_env.filters["dt_format"] = dt_format
    app.jinja_env.filters["td_format"] = td_format
