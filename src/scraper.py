from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError
from datetime import datetime
from time import sleep
import json
import os

from . import config

MAX_RETRIES = 3
RETRY_DELAY = 10


def create_browser(p) -> BrowserContext:
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-blink-features=AutomationControlled",
            "--blink-settings=imagesEnabled=false",
            "--disable-background-networking",
            "--mute-audio",
        ],
    )

    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )

    context.route(
        "**/*",
        lambda route: (
            route.abort()
            if route.request.resource_type in ["image", "media", "font", "stylesheet"]
            or "google-analytics" in route.request.url
            or "fontawesome" in route.request.url
            else route.continue_()
        ),
    )

    return context


def check_server_status(page: Page) -> bool:
    resp = page.goto(config.CMS_URL, wait_until="commit", timeout=15000)
    if resp and resp.status >= 500:
        print(f"[ERROR] Server returned status {resp.status}. The Bahria CMS may be down.")
        return False
    title = page.title()
    if "Runtime Error" in title or "Error" in title:
        print(f"[ERROR] Server returned error page: {title}")
        return False
    return True


def login(page: Page) -> bool:
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"[LOGIN] Attempt {attempt}/{MAX_RETRIES} - Navigating to CMS login...")

        try:
            resp = page.goto(config.CMS_URL, wait_until="commit", timeout=30000)

            if resp and resp.status >= 500:
                print(f"[ERROR] Server returned {resp.status}. Retrying in {RETRY_DELAY}s...")
                if attempt < MAX_RETRIES:
                    sleep(RETRY_DELAY)
                continue

            title = page.title()
            if "Runtime Error" in title:
                print(f"[ERROR] Server error page. Retrying in {RETRY_DELAY}s...")
                if attempt < MAX_RETRIES:
                    sleep(RETRY_DELAY)
                continue

            page.fill("#BodyPH_tbEnrollment", config.ENROLLMENT_NUMBER)
            page.fill("#BodyPH_tbPassword", config.PASSWORD)
            page.select_option("#BodyPH_ddlInstituteID", "1")

            campus_selector = f"#pageContent > div.container-fluid > div.row > div > div:nth-child({config.INSTITUTION})"
            page.click(campus_selector)

            page.click("#BodyPH_btnLogin")
            print(f"[LOGIN] Logged in as {config.ENROLLMENT_NUMBER}")

            lms_button = page.wait_for_selector("#sideMenuList > a:nth-child(16)", timeout=30000)
            page.evaluate("el => el.removeAttribute('target')", lms_button)
            lms_button.click()

            if "QualityAssuranceSurveys.aspx" in page.url:
                print("[ERROR] Quality Assurance Survey pending. Complete it manually first.")
                return False

            print("[LOGIN] LMS portal opened successfully.")
            return True

        except TimeoutError:
            print(f"[ERROR] Timeout on attempt {attempt}. Retrying...")
            if attempt < MAX_RETRIES:
                sleep(RETRY_DELAY)
        except Exception as e:
            print(f"[ERROR] Login failed: {e}")
            if attempt < MAX_RETRIES:
                sleep(RETRY_DELAY)

    print("[FATAL] All login attempts failed.")
    return False


def fetch_assignments(page: Page) -> list[dict]:
    print("[SCRAPER] Fetching assignments from LMS...")

    if "Assignments.php" not in page.url:
        page.goto(config.LMS_ASSIGNMENTS_URL, wait_until="networkidle")

    subjects = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('#courseId option'))
            .filter(opt => opt.value !== "")
            .map(opt => ({ id: opt.value, name: opt.innerText.trim() }));
    }""")

    print(f"[SCRAPER] Found {len(subjects)} subjects.")

    deadlines = []

    for course in subjects:
        page.select_option("#courseId", value=course["id"])

        try:
            page.wait_for_selector("table.table-hover tbody tr:not(:first-child)", timeout=5000)
        except TimeoutError:
            print(f"[SCRAPER] No assignments for {course['name']}, skipping.")
            continue

        table_data = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll("table.table-hover tbody tr")).slice(1);
            return rows.map(row => {
                const cells = row.querySelectorAll("td");
                if (cells.length < 8) return null;
                const deadlineSmall = cells[7].querySelector("small");
                return {
                    action: cells[6].innerText,
                    assignment_number: cells[0].innerText.trim(),
                    assignment_name: cells[1].innerText.trim(),
                    deadline_text: deadlineSmall ? deadlineSmall.innerText : "",
                    deadline_title: deadlineSmall ? deadlineSmall.getAttribute("title") : "",
                };
            }).filter(item => item !== null);
        }""")

        for item in table_data:
            has_submit = "Submit" in item["action"]
            has_delete = "Delete" in item["action"]

            if not has_submit and not has_delete:
                continue

            deadline_text = item["deadline_text"].split("-")[0].strip()
            if not deadline_text:
                continue

            try:
                deadline_date = datetime.strptime(deadline_text, "%d %B %Y").date()
            except ValueError:
                print(f"[SCRAPER] Could not parse date: {deadline_text}")
                continue

            deadlines.append({
                "assignment_number": item["assignment_number"],
                "subject": course["name"],
                "assignment_name": item["assignment_name"],
                "deadline_date": deadline_date,
                "deadline_text": deadline_text,
                "submitted": has_delete,
                "extended": "Extended" in (item["deadline_title"] or ""),
            })

    print(f"[SCRAPER] Found {len(deadlines)} active assignments across all subjects.")
    return deadlines


def load_seen_assignments(filepath: str) -> dict:
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}


def save_seen_assignments(filepath: str, data: dict):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def detect_new_assignments(deadlines: list[dict], seen: dict) -> list[dict]:
    new = []
    for dl in deadlines:
        key = f"{dl['assignment_number']}_{dl['subject']}_{dl['deadline_text']}"
        if key not in seen:
            new.append(dl)
            seen[key] = {
                "first_seen": datetime.now().isoformat(),
                "deadline": dl["deadline_text"],
            }
    return new
