import sys
import os
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
)
from src.notifier import alert_deadlines, alert_new_assignments, send_notification

SEEN_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seen_assignments.json")


def main():
    print(f"\n{'='*50}")
    print(f"Bahria Assignment Notifier - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
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

        seen = load_seen_assignments(SEEN_FILE)
        new_assignments = detect_new_assignments(deadlines, seen)
        save_seen_assignments(SEEN_FILE, seen)

        print(f"\n--- Assignment Summary ---")
        for dl in sorted(deadlines, key=lambda x: x["deadline_date"]):
            days_left = (dl["deadline_date"] - datetime.today().date()).days
            status = "SUBMITTED" if dl["submitted"] else f"{days_left}d left"
            marker = " [NEW]" if dl in new_assignments else ""
            print(f"  {dl['assignment_number']}. {dl['subject']} | {dl['assignment_name']} | {status}{marker}")

        print(f"\n[NOTIFY] Sending deadline alerts...")
        alert_deadlines(deadlines)

        if new_assignments:
            print(f"\n[NOTIFY] Sending new assignment alerts ({len(new_assignments)} found)...")
            alert_new_assignments(new_assignments)

        print(f"\n[DONE] Completed successfully.\n")

    except Exception as e:
        print(f"\n[FATAL] Error: {e}")
        send_notification("Assignment Bot Error", f"Error: {str(e)}", 5)
        sys.exit(1)


if __name__ == "__main__":
    main()
