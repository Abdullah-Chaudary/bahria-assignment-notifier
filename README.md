# Bahria Assignment Notifier

Automated bot that checks Bahria University LMS for assignments and sends push notifications via [Ntfy.sh](https://ntfy.sh) before deadlines.

## What It Does

1. Logs into `cms.bahria.edu.pk` with your credentials
2. Navigates to the LMS portal
3. Scans every subject for assignments
4. Detects **new** assignments and tracks them
5. Sends **push notifications** based on deadline urgency:
   - Due today / 1-2 days left = max priority
   - Due in 3-4 days = high priority
   - Due in 5-7 days = normal priority
   - New assignment detected = notification

## Setup

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/bahria-assignment-notifier.git
cd bahria-assignment-notifier
pip install -r requirements.txt
playwright install chromium
```

### 2. Create Ntfy Topic

1. Install the **Ntfy** app on your phone ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iOS](https://apps.apple.com/app/ntfy/id1625396347))
2. Subscribe to a topic (e.g., `bahria-assignments- YOURNAME`)
3. Use that topic name as `NTFY_SERVER`

### 3. Configure

Create a `.env` file:

```bash
cp .env.example .env
```

Edit `.env`:

```
ENROLLMENT_NUMBER=01-134252-139
PASSWORD=your_cms_password
NTFY_SERVER=bahria-assignments-yourname
INSTITUTION=6
NOTIFICATION_LEVEL=0
NOTIFY_EXTENDED=1
```

| Variable | Description |
|----------|-------------|
| `ENROLLMENT_NUMBER` | Your Bahria enrollment number |
| `PASSWORD` | Your CMS password |
| `NTFY_SERVER` | Your Ntfy.sh topic name |
| `INSTITUTION` | Campus number (6 = Islamabad E-8) |
| `NOTIFICATION_LEVEL` | 0=all, 1=4 days, 2=7 days, 3=14 days, 4=overdue only |
| `NOTIFY_EXTENDED` | 1=notify about extended deadlines too |

### 4. Run Locally

```bash
python -m src.main
```

### 5. GitHub Actions (Auto-run every 3 hours)

1. Push this repo to GitHub
2. Go to **Settings > Secrets and variables > Actions**
3. Add these secrets:
   - `ENROLLMENT_NUMBER`
   - `PASSWORD`
   - `NTFY_SERVER`
   - `INSTITUTION` (optional, defaults to 6)
   - `NOTIFICATION_LEVEL` (optional, defaults to 0)
   - `NOTIFY_EXTENDED` (optional, defaults to 1)
4. The workflow runs automatically every 3 hours

You can also trigger it manually from the **Actions** tab.

## How Notifications Work

| Days Left | Priority | Meaning |
|-----------|----------|---------|
| 0 (today) | 5 (max) | Assignment due TODAY |
| 1-2 days | 5 (max) | URGENT - submit soon |
| 3-4 days | 4 (high) | Coming up soon |
| 5-7 days | 3 (normal) | Upcoming |
| 8+ days | 2 (low) | Future assignment |

The bot tracks which assignments it has already notified you about (stored in `seen_assignments.json`) so you only get notified about **new** assignments once, plus deadline reminders as they approach.

## Project Structure

```
bahria-assignment-notifier/
├── .github/workflows/
│   └── check-assignments.yml   # GitHub Actions (runs every 3h)
├── src/
│   ├── __init__.py
│   ├── config.py               # Environment variables
│   ├── scraper.py              # Playwright CMS/LMS automation
│   ├── notifier.py             # Ntfy.sh push notifications
│   └── main.py                 # Entry point
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Credits

Built from scratch for Bahria University Islamabad E-8 Campus. Inspired by [Mujtaba0150/Bahria-University-Automation](https://github.com/Mujtaba0150/Bahria-University-Automation).
