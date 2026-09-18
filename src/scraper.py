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


BLANK_FILES_DIR = r"D:\Corrupted Files"


def get_deadline_minutes_remaining(page: Page, course_id: str, assignment_number: str) -> int:
    page.select_option("#courseId", value=course_id)
    try:
        page.wait_for_selector("table.table-hover tbody tr:not(:first-child)", timeout=5000)
    except TimeoutError:
        return -1

    result = page.evaluate("""(assignNum) => {
        const rows = Array.from(document.querySelectorAll("table.table-hover tbody tr")).slice(1);
        for (const row of rows) {
            const cells = row.querySelectorAll("td");
            if (cells.length < 8) continue;
            if (cells[0].innerText.trim() !== assignNum) continue;
            const small = cells[7].querySelector("small");
            if (!small) continue;
            return small.getAttribute("title") || small.innerText;
        }
        return null;
    }""", assignment_number)

    if not result:
        return -1

    try:
        deadline_str = result.split("-")[0].strip()
        deadline_dt = datetime.strptime(deadline_str, "%d %B %Y")
        now = datetime.now()
        diff_minutes = int((deadline_dt - now).total_seconds() / 60)
        return diff_minutes
    except Exception:
        return -1


def upload_blank_file(page: Page, course_id: str, course_name: str, assignment_number: str, assignment_name: str) -> bool:
    print(f"[UPLOAD] Attempting to upload blank file for {course_name} - {assignment_name}...")

    page.select_option("#courseId", value=course_id)
    try:
        page.wait_for_selector("table.table-hover tbody tr:not(:first-child)", timeout=5000)
    except TimeoutError:
        print(f"[UPLOAD] No assignments table found.")
        return False

    submit_url = page.evaluate("""(assignNum) => {
        const rows = Array.from(document.querySelectorAll("table.table-hover tbody tr")).slice(1);
        for (const row of rows) {
            const cells = row.querySelectorAll("td");
            if (cells.length < 8) continue;
            if (cells[0].innerText.trim() !== assignNum) continue;
            const actionCell = cells[6];
            const submitLink = actionCell.querySelector("a[href*='Submit']");
            if (submitLink) return submitLink.getAttribute("href");
        }
        return null;
    }""", assignment_number)

    if not submit_url:
        print(f"[UPLOAD] No submit button found for assignment {assignment_number}.")
        return False

    full_url = f"https://lms.bahria.edu.pk/Student/{submit_url}" if not submit_url.startswith("http") else submit_url
    page.goto(full_url, wait_until="networkidle")

    page.wait_for_selector("input[type='file']", timeout=10000)

    accepted_types = page.evaluate("""() => {
        const fileInput = document.querySelector('input[type="file"]');
        return fileInput ? fileInput.accept : '';
    }""")

    if ".pdf" in accepted_types.lower():
        blank_file = os.path.join(BLANK_FILES_DIR, "Assignment.pdf")
    elif ".doc" in accepted_types.lower():
        blank_file = os.path.join(BLANK_FILES_DIR, "Assignment.docx")
    else:
        blank_file = os.path.join(BLANK_FILES_DIR, "Assignment.pdf")

    if not os.path.exists(blank_file):
        print(f"[UPLOAD] Blank file not found: {blank_file}")
        return False

    page.set_input_files("input[type='file']", blank_file)
    print(f"[UPLOAD] Selected file: {blank_file}")

    submit_btn = page.query_selector("input[type='submit'], button[type='submit']")
    if submit_btn:
        submit_btn.click()
        page.wait_for_load_state("networkidle")
        print(f"[UPLOAD] File submitted successfully.")
        return True
    else:
        print(f"[UPLOAD] Submit button not found on upload page.")
        return False


def check_and_upload_emergency(page: Page) -> list[dict]:
    uploaded = []

    if "Assignments.php" not in page.url:
        page.goto(config.LMS_ASSIGNMENTS_URL, wait_until="networkidle")

    subjects = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('#courseId option'))
            .filter(opt => opt.value !== "")
            .map(opt => ({ id: opt.value, name: opt.innerText.trim() }));
    }""")

    for course in subjects:
        page.select_option("#courseId", value=course["id"])

        try:
            page.wait_for_selector("table.table-hover tbody tr:not(:first-child)", timeout=5000)
        except TimeoutError:
            continue

        table_data = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll("table.table-hover tbody tr")).slice(1);
            return rows.map(row => {
                const cells = row.querySelectorAll("td");
                if (cells.length < 8) return null;
                const action = cells[6].innerText;
                if (!action.includes("Submit")) return null;
                const deadlineSmall = cells[7].querySelector("small");
                const deadlineTitle = deadlineSmall ? deadlineSmall.getAttribute("title") : "";
                const deadlineText = deadlineSmall ? deadlineSmall.innerText : "";
                return {
                    assignment_number: cells[0].innerText.trim(),
                    assignment_name: cells[1].innerText.trim(),
                    deadline_text: deadlineText,
                    deadline_title: deadlineTitle,
                };
            }).filter(item => item !== null);
        }""")

        for item in table_data:
            deadline_str = item["deadline_text"].split("-")[0].strip()
            if not deadline_str:
                continue

            try:
                deadline_dt = datetime.strptime(deadline_str, "%d %B %Y")
                now = datetime.now()
                diff_minutes = int((deadline_dt - now).total_seconds() / 60)

                if diff_minutes <= 3 and diff_minutes >= -5:
                    print(f"[EMERGENCY] {course['name']} - {item['assignment_name']} has {diff_minutes} minutes remaining!")
                    success = upload_blank_file(
                        page, course["id"], course["name"],
                        item["assignment_number"], item["assignment_name"]
                    )
                    if success:
                        uploaded.append({
                            "subject": course["name"],
                            "assignment_name": item["assignment_name"],
                            "minutes_remaining": diff_minutes,
                        })
            except ValueError:
                continue

    return uploaded
