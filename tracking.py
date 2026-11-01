"""Rules about where an application stands that the desktop and Android versions share (see shared_tests/)."""
from datetime import date

FOLLOW_UP_DAYS = 14


def days_since(iso_day, today):
    """Whole days from an ISO date (YYYY-MM-DD) to today, or None when the date is missing or not a date."""
    try:
        return (today - date.fromisoformat(iso_day)).days
    except (TypeError, ValueError):
        return None


def needs_follow_up(status, applied_on, today):
    """A posting still at Applied 14 or more days after the applied date is due for a follow-up."""
    d = days_since(applied_on, today) if status == "applied" else None
    return d is not None and d >= FOLLOW_UP_DAYS


def weekly_summary(days, applied, interviews, rejected, upcoming, waiting):
    """The plain-facts block on the Weekly page. Each argument after days is a count."""
    lines = [f"Job search, last {days} days:", f"- {applied} application(s) sent"]
    if interviews:
        lines.append(f"- {interviews} moved to a phone screen or interview")
    if rejected:
        lines.append(f"- {rejected} closed out")
    if upcoming:
        lines.append(f"- {upcoming} interview or follow-up coming up in the next 2 weeks")
    if waiting:
        lines.append(f"- {waiting} application(s) waiting 14+ days with no word, due for a follow-up")
    return "\n".join(lines)


def interview_rate(applied, interviews):
    return f"{round(100 * interviews / applied)}%" if applied else "n/a"
