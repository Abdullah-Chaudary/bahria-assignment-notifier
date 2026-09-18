from datetime import datetime
import json
import requests
import os

from . import config

SUBMITTED_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "submitted.json"
)


def load_submitted() -> dict:
    if os.path.exists(SUBMITTED_FILE):
        with open(SUBMITTED_FILE, "r") as f:
            return json.load(f)
    return {}


def save_submitted(data: dict):
    with open(SUBMITTED_FILE, "w") as f:
        json.dump(data, f, indent=2)


def mark_submitted(assignment_key: str):
    data = load_submitted()
    data[assignment_key] = {
        "submitted_at": datetime.now().isoformat(),
    }
    save_submitted(data)
    print(f"[SUBMITTED] Marked as submitted: {assignment_key}")


def unmark_submitted(assignment_key: str):
    data = load_submitted()
    if assignment_key in data:
        del data[assignment_key]
        save_submitted(data)
        print(f"[UNSUBMITTED] Removed from submitted: {assignment_key}")


def is_submitted(assignment_key: str) -> bool:
    return assignment_key in load_submitted()


def get_assignment_key(dl: dict) -> str:
    return f"{dl['assignment_number']}_{dl['subject']}_{dl['deadline_text']}"


def send_notification(title: str, message: str, priority: int):
    if not config.NTFY_SERVER:
        print("[SKIP] NTFY_SERVER not set, skipping notification.")
        return

    try:
        resp = requests.post(
            f"https://ntfy.sh/{config.NTFY_SERVER}",
            data=message,
            headers={
                "Title": title,
                "Priority": str(priority),
            },
            timeout=10,
        )
        resp.raise_for_status()
        print(f"[NTFY] Sent: {title}")
    except requests.RequestException as e:
        print(f"[NTFY] Failed to send: {e}")


def _urgency_emoji(days_left: int) -> str:
    if days_left == 0:
        return "🔴"
    elif days_left <= 2:
        return "🟠"
    elif days_left <= 4:
        return "🟡"
    elif days_left <= 7:
        return "🟢"
    else:
        return "⚪"


def _status_emoji(submitted: bool, extended: bool) -> str:
    if submitted:
        return "✅"
    if extended:
        return "🔄"
    return "⏳"


def alert_deadlines(deadlines: list[dict]):
    today = datetime.today().date()
    max_days = config.LEVEL_TO_MAX_DAYS.get(config.NOTIFICATION_LEVEL, 0)

    pending = []
    for dl in deadlines:
        days_left = (dl["deadline_date"] - today).days
        key = get_assignment_key(dl)
        submitted = dl["submitted"] or is_submitted(key)

        if submitted and not (config.NOTIFY_EXTENDED and dl["extended"]):
            continue
        if days_left > max_days:
            continue

        pending.append(dl)

    if not pending:
        return

    for dl in sorted(pending, key=lambda x: x["deadline_date"]):
        days_left = (dl["deadline_date"] - today).days
        key = get_assignment_key(dl)
        submitted = dl["submitted"] or is_submitted(key)
        display_date = dl["deadline_date"].strftime("%d %B")
        emoji = _urgency_emoji(days_left)
        status = _status_emoji(submitted, dl["extended"])

        if days_left == 0:
            days_str = "TODAY"
        elif days_left == 1:
            days_str = "1 day left"
        else:
            days_str = f"{days_left} days left"

        msg = (
            f"{emoji} {dl['subject']}\n"
            f"📝 {dl['assignment_name']}\n"
            f"📅 Due: {display_date}\n"
            f"⏳ {days_str}\n"
            f"📊 Status: {status} {'Submitted' if submitted else 'Pending'}"
        )

        if days_left == 0:
            priority = 5
            title = "Assignment Due TODAY"
        elif days_left <= 2:
            priority = 5
            title = f"URGENT - {days_left} day(s) left"
        elif days_left <= 4:
            priority = 4
            title = f"Due in {days_left} days"
        elif days_left <= 7:
            priority = 3
            title = f"Due in {days_left} days"
        else:
            priority = 2
            title = f"Upcoming - {days_left} days"

        send_notification(title, msg, priority)


def alert_new_assignments(new_assignments: list[dict]):
    if not new_assignments:
        return

    today = datetime.today().date()
    lines = []

    for dl in sorted(new_assignments, key=lambda x: x["deadline_date"]):
        days_left = (dl["deadline_date"] - today).days
        display_date = dl["deadline_date"].strftime("%d %b")
        emoji = _urgency_emoji(days_left)

        lines.append(
            f"{emoji} NEW — {dl['subject']}\n"
            f"📝 {dl['assignment_name']}\n"
            f"📅 {display_date} ({days_left}d left)"
        )

    combined = "\n\n".join(lines)
    send_notification(
        f"{len(new_assignments)} New Assignment(s) Detected",
        combined,
        4,
    )


def send_summary(deadlines: list[dict]):
    today = datetime.today().date()
    pending = []
    submitted_count = 0

    for dl in deadlines:
        key = get_assignment_key(dl)
        submitted = dl["submitted"] or is_submitted(key)
        if submitted:
            submitted_count += 1
        else:
            pending.append(dl)

    urgent = [dl for dl in pending if (dl["deadline_date"] - today).days <= 3]
    upcoming = [dl for dl in pending if (dl["deadline_date"] - today).days > 3]

    summary = "📊 ASSIGNMENT SUMMARY\n\n"

    if urgent:
        summary += "🔴 URGENT (≤3 days):\n"
        for dl in sorted(urgent, key=lambda x: x["deadline_date"]):
            days_left = (dl["deadline_date"] - today).days
            display_date = dl["deadline_date"].strftime("%d %b")
            summary += (
                f"  • {dl['subject']}\n"
                f"    {dl['assignment_name']}\n"
                f"    📅 {display_date} ({days_left}d left)\n\n"
            )

    if upcoming:
        summary += "🟢 UPCOMING (>3 days):\n"
        for dl in sorted(upcoming, key=lambda x: x["deadline_date"]):
            days_left = (dl["deadline_date"] - today).days
            display_date = dl["deadline_date"].strftime("%d %b")
            summary += (
                f"  • {dl['subject']}\n"
                f"    {dl['assignment_name']}\n"
                f"    📅 {display_date} ({days_left}d left)\n\n"
            )

    summary += f"📋 Total: {len(deadlines)} | ⏳ Pending: {len(pending)} | ✅ Done: {submitted_count}"

    send_notification("Assignment Summary", summary, 3)
