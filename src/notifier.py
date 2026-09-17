from playwright.sync_api import sync_playwright, Page, BrowserContext
from datetime import datetime
import json
import requests
import os

from . import config


def send_notification(title: str, message: str, priority: int):
    if not config.NTFY_SERVER:
        print("[SKIP] NTFY_SERVER not set, skipping notification.")
        return

    try:
        resp = requests.post(
            f"https://ntfy.sh/{config.NTFY_SERVER}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": str(priority)},
            timeout=10,
        )
        resp.raise_for_status()
        print(f"[NTFY] Sent: {title}")
    except requests.RequestException as e:
        print(f"[NTFY] Failed to send: {e}")


def send_batched_notification(title: str, messages: list[str], priority: int):
    if not messages:
        return
    combined = "\n".join(messages)
    send_notification(title, combined, priority)


def fetch_cached_notifications() -> list[dict]:
    if not config.NTFY_SERVER:
        return []

    cached = []
    titles = [
        "Assignment Due Today",
        "Assignment Due Soon",
        "Upcoming Assignments",
        "New Assignment Detected",
    ]

    for title in titles:
        try:
            resp = requests.get(
                f"https://ntfy.sh/{config.NTFY_SERVER}/json?poll=1",
                timeout=10,
            )
            for line in resp.text.splitlines():
                if line.strip():
                    data = json.loads(line)
                    if data.get("title") == title:
                        cached.append({"id": data["id"], "message": data["message"]})
        except Exception:
            pass

    return cached


def delete_cached_notification(notification_id: str):
    if not config.NTFY_SERVER:
        return
    try:
        requests.delete(f"https://ntfy.sh/{config.NTFY_SERVER}/{notification_id}", timeout=5)
    except Exception:
        pass


def alert_deadlines(deadlines: list[dict]):
    today = datetime.today().date()
    max_days = config.LEVEL_TO_MAX_DAYS.get(config.NOTIFICATION_LEVEL, 0)

    for dl in deadlines:
        deadline_date = dl["deadline_date"]
        days_left = (deadline_date - today).days
        submitted = dl["submitted"]
        extended = dl["extended"]

        if submitted and not (config.NOTIFY_EXTENDED and extended):
            continue

        if days_left > max_days:
            continue

        display_date = deadline_date.strftime("%d %B")
        msg = f"{dl['assignment_number']}. {dl['subject']} - {display_date}"

        if days_left == 0:
            priority = 5
            title = "Assignment Due TODAY"
            send_notification(title, msg, priority)
        elif days_left <= 2:
            priority = 5
            title = f"URGENT: {days_left} day(s) left"
            send_notification(title, msg, priority)
        elif days_left <= 4:
            priority = 4
            title = f"Assignment Due in {days_left} days"
            send_notification(title, msg, priority)
        elif days_left <= 7:
            priority = 3
            title = f"Upcoming Assignment ({days_left} days)"
            send_notification(title, msg, priority)
        else:
            priority = 2
            title = "Upcoming Assignment"
            send_notification(title, msg, priority)


def alert_new_assignments(new_assignments: list[dict]):
    if not new_assignments:
        return

    messages = []
    for dl in new_assignments:
        display_date = dl["deadline_date"].strftime("%d %B")
        messages.append(
            f"NEW: {dl['assignment_number']}. {dl['subject']}\n"
            f"   {dl['assignment_name']} | Due: {display_date}"
        )

    send_batched_notification(
        f"New Assignment(s) Detected ({len(new_assignments)})",
        messages,
        4,
    )
