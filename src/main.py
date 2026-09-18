import sys
import os
import argparse
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.scraper import (
    create_browser,
    login,
    fetch_assignments,
    load_seen_assignments,
    save_seen_assignments,
    detect_new_assignments,
    check_and_upload_emergency,
)
from src.notifier import (
    alert_deadlines,
    alert_new_assignments,
    send_summary,
    load_submitted,
    mark_submitted,
    unmark_submitted,
    get_assignment_key,
    send_notification,
)

SEEN_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seen_assignments.json"
)

MAX_RETRIES = 8
RETRY_INTERVAL_MINUTES = 15


def trigger_retry(run_number: int):
    if run_number >= MAX_RETRIES:
        print(f"[RETRY] Max retries ({MAX_RETRIES}) reached. Giving up.")
        send_notification(
            "Bot Giving Up",
            f"Server still down after {MAX_RETRIES} retries ({MAX_RETRIES * RETRY_INTERVAL_MINUTES} minutes). Will try again at next scheduled run.",
            5,
        )
        return

    github_token = os.getenv("GITHUB_TOKEN", "")
    repo = os.getenv("GITHUB_REPOSITORY", "")

    if not github_token or not repo:
        print("[RETRY] Not in GitHub Actions or GITHUB_TOKEN not set. Cannot schedule retry.")
        print(f"[RETRY] Retry {run_number + 1}/{MAX_RETRIES} would run in {RETRY_INTERVAL_MINUTES} minutes.")
        return

    print(f"[RETRY] Scheduling retry {run_number + 1}/{MAX_RETRIES} in {RETRY_INTERVAL_MINUTES} minutes...")

    try:
        resp = requests.post(
            f"https://api.github.com/repos/{repo}/actions/workflows/check-assignments.yml/dispatches",
            json={
                "ref": "main",
                "inputs": {
                    "retry": str(run_number + 1),
                },
            },
            headers={
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=10,
        )

        if resp.status_code == 204:
            print(f"[RETRY] Retry {run_number + 1} scheduled successfully.")
        else:
            print(f"[RETRY] Failed to schedule retry: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"[RETRY] Error scheduling retry: {e}")


def parse_args():
    parser = argparse.ArgumentParser(description="Bahria Assignment Notifier")
    sub = parser.add_subparsers(dest="command", help="Commands")

    sub.add_parser("check", help="Check assignments and send notifications")
    sub.add_parser("summary", help="Send a summary of all assignments")
    sub.add_parser("emergency-upload", help="Upload blank files for assignments due within 3 minutes")

    sub_add = sub.add_parser("submit", help="Mark an assignment as submitted")
    sub_add.add_argument("pattern", help="Search pattern (subject or assignment name)")

    sub_remove = sub.add_parser("unsubmit", help="Unmark a submitted assignment")
    sub_remove.add_argument("pattern", help="Search pattern to remove")

    sub.add_parser("submitted", help="List all submitted assignments")

    parser.add_argument("--retry", type=int, default=0, help="Retry attempt number (used internally)")

    return parser.parse_args()


def do_check():
    retry_num = int(os.environ.get("RETRY_NUMBER", "0"))

    print(f"\n{'='*50}")
    print(f"Bahria Assignment Notifier — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if retry_num > 0:
        print(f"Retry attempt: {retry_num}/{MAX_RETRIES}")
    print(f"{'='*50}\n")

    errors = config.validate()
    if errors:
        for e in errors:
            print(f"[CONFIG ERROR] {e}")
        sys.exit(1)

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = create_browser(p)
            page = browser.new_page()
            page.set_default_timeout(60000)

            if not login(page):
                print("[FATAL] Login failed.")
                send_notification("Bot Error - Login Failed", "Bahria CMS/LMS server is down. Retrying in 15 minutes...", 5)
                browser.close()
                trigger_retry(retry_num)
                sys.exit(1)

            deadlines = fetch_assignments(page)
            browser.close()

        if retry_num > 0:
            send_notification(
                "Bot Back Online",
                f"Server is back! Checked successfully after {retry_num} retry attempt(s).",
                3,
            )

        if not deadlines:
            print("\n[RESULT] No active assignments found.")
            return

        seen = load_seen_assignments(SEEN_FILE)
        new_assignments = detect_new_assignments(deadlines, seen)
        save_seen_assignments(SEEN_FILE, seen)

        print(f"\n--- Assignment Summary ---\n")
        for dl in sorted(deadlines, key=lambda x: x["deadline_date"]):
            days_left = (dl["deadline_date"] - datetime.today().date()).days
            key = get_assignment_key(dl)
            from src.notifier import is_submitted
            status = "DONE" if dl["submitted"] or is_submitted(key) else f"{days_left}d left"
            marker = " [NEW]" if dl in new_assignments else ""
            print(f"  {dl['assignment_number']}. {dl['subject']}")
            print(f"     {dl['assignment_name']} | {status}{marker}")
            print()

        print(f"\n[NOTIFY] Sending deadline alerts...")
        alert_deadlines(deadlines)

        if new_assignments:
            print(f"\n[NOTIFY] Sending new assignment alerts ({len(new_assignments)} found)...")
            alert_new_assignments(new_assignments)

        print(f"\n[DONE] Completed successfully.\n")

    except Exception as e:
        print(f"\n[FATAL] Error: {e}")
        send_notification("Bot Error", f"Something went wrong: {str(e)[:200]}", 5)
        trigger_retry(retry_num)
        sys.exit(1)


def do_summary():
    print(f"\n{'='*50}")
    print(f"Bahria Assignment Summary — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    errors = config.validate()
    if errors:
        for e in errors:
            print(f"[CONFIG ERROR] {e}")
        sys.exit(1)

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = create_browser(p)
            page = browser.new_page()
            page.set_default_timeout(60000)

            if not login(page):
                print("[FATAL] Login failed. Exiting.")
                browser.close()
                sys.exit(1)

            deadlines = fetch_assignments(page)
            browser.close()

        if not deadlines:
            print("\n[RESULT] No active assignments found.")
            return

        print(f"\n--- Assignment Summary ---\n")
        today = datetime.today().date()
        for dl in sorted(deadlines, key=lambda x: x["deadline_date"]):
            days_left = (dl["deadline_date"] - today).days
            key = get_assignment_key(dl)
            from src.notifier import is_submitted
            submitted = dl["submitted"] or is_submitted(key)
            status = "DONE" if submitted else f"{days_left}d left"
            print(f"  {dl['assignment_number']}. {dl['subject']}")
            print(f"     {dl['assignment_name']} | {status}")
            print()

        send_summary(deadlines)
        print(f"\n[DONE] Summary sent.\n")

    except Exception as e:
        print(f"\n[FATAL] Error: {e}")
        sys.exit(1)


def do_submit(pattern: str):
    print(f"\nSearching for assignments matching '{pattern}'...\n")
    errors = config.validate()
    if errors:
        for e in errors:
            print(f"[CONFIG ERROR] {e}")
        sys.exit(1)

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = create_browser(p)
            page = browser.new_page()
            page.set_default_timeout(60000)

            if not login(page):
                print("[FATAL] Login failed. Exiting.")
                browser.close()
                sys.exit(1)

            deadlines = fetch_assignments(page)
            browser.close()

        matches = []
        pattern_lower = pattern.lower()
        for dl in deadlines:
            if (
                pattern_lower in dl["subject"].lower()
                or pattern_lower in dl["assignment_name"].lower()
            ):
                matches.append(dl)

        if not matches:
            print(f"No assignments found matching '{pattern}'.")
            print("\nAvailable assignments:")
            for dl in deadlines:
                key = get_assignment_key(dl)
                from src.notifier import is_submitted
                status = "DONE" if dl["submitted"] or is_submitted(key) else "PENDING"
                print(f"  [{status}] {dl['assignment_number']}. {dl['subject']} — {dl['assignment_name']}")
            return

        print(f"Found {len(matches)} matching assignment(s):\n")
        for i, dl in enumerate(matches, 1):
            key = get_assignment_key(dl)
            from src.notifier import is_submitted
            status = "DONE" if dl["submitted"] or is_submitted(key) else "PENDING"
            print(f"  {i}. [{status}] {dl['subject']} — {dl['assignment_name']}")
            print(f"     Due: {dl['deadline_date'].strftime('%d %B')}")
            print()

        choice = input("Enter number to mark as submitted (or 'all' for all, 'q' to cancel): ").strip()

        if choice == "q":
            print("Cancelled.")
            return

        if choice == "all":
            for dl in matches:
                key = get_assignment_key(dl)
                mark_submitted(key)
            print(f"\nMarked {len(matches)} assignment(s) as submitted.")
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(matches):
                key = get_assignment_key(matches[idx])
                mark_submitted(key)
                print(f"\nMarked as submitted: {matches[idx]['subject']} — {matches[idx]['assignment_name']}")
            else:
                print("Invalid selection.")
        except ValueError:
            print("Invalid input.")

    except Exception as e:
        print(f"\n[FATAL] Error: {e}")
        sys.exit(1)


def do_unsubmit(pattern: str):
    submitted = load_submitted()
    if not submitted:
        print("No submitted assignments tracked.")
        return

    print(f"\nSubmitted assignments:\n")
    matches = []
    pattern_lower = pattern.lower()
    for key, data in submitted.items():
        if pattern_lower in key.lower():
            matches.append((key, data))

    if not matches:
        print(f"No submitted assignments matching '{pattern}'.")
        print("\nAll submitted:")
        for key in submitted:
            print(f"  • {key}")
        return

    for i, (key, data) in enumerate(matches, 1):
        print(f"  {i}. {key}")
        print(f"     Submitted at: {data.get('submitted_at', 'unknown')}")

    choice = input("\nEnter number to unmark (or 'all' for all, 'q' to cancel): ").strip()

    if choice == "q":
        return

    if choice == "all":
        for key, _ in matches:
            unmark_submitted(key)
        print(f"Unmarked {len(matches)} assignment(s).")
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(matches):
            unmark_submitted(matches[idx][0])
            print(f"Unmarked: {matches[idx][0]}")
        else:
            print("Invalid selection.")
    except ValueError:
        print("Invalid input.")


def do_list_submitted():
    submitted = load_submitted()
    if not submitted:
        print("\nNo submitted assignments tracked.")
        return

    print(f"\n--- Submitted Assignments ---\n")
    for key, data in submitted.items():
        print(f"  ✅ {key}")
        print(f"     Submitted: {data.get('submitted_at', 'unknown')}")
    print()


def do_emergency_upload():
    print(f"\n{'='*50}")
    print(f"Emergency Upload Check — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    errors = config.validate()
    if errors:
        for e in errors:
            print(f"[CONFIG ERROR] {e}")
        sys.exit(1)

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = create_browser(p)
            page = browser.new_page()
            page.set_default_timeout(60000)

            if not login(page):
                print("[FATAL] Login failed.")
                send_notification("Emergency Upload Failed", "Server down. Could not check for emergency uploads.", 5)
                browser.close()
                sys.exit(1)

            uploaded = check_and_upload_emergency(page)
            browser.close()

        if uploaded:
            messages = []
            for item in uploaded:
                messages.append(
                    f" Uploaded blank file for:\n"
                    f" {item['subject']} - {item['assignment_name']}\n"
                    f" Deadline was in {item['minutes_remaining']} minutes\n"
                )
            combined = "\n".join(messages)
            send_notification(
                f"Emergency Upload Complete ({len(uploaded)} file(s))",
                combined,
                5,
            )
            print(f"\n[DONE] Uploaded {len(uploaded)} blank file(s).")
        else:
            print("\n[RESULT] No assignments due for emergency upload.")

    except Exception as e:
        print(f"\n[FATAL] Error: {e}")
        send_notification("Emergency Upload Error", f"Error: {str(e)[:200]}", 5)
        sys.exit(1)


if __name__ == "__main__":
    args = parse_args()

    if args.command == "submit":
        do_submit(args.pattern)
    elif args.command == "unsubmit":
        do_unsubmit(args.pattern)
    elif args.command == "submitted":
        do_list_submitted()
    elif args.command == "summary":
        do_summary()
    elif args.command == "emergency-upload":
        do_emergency_upload()
    else:
        do_check()
