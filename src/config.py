import os
from dotenv import load_dotenv

load_dotenv()

ENROLLMENT_NUMBER = os.getenv("ENROLLMENT_NUMBER", "")
PASSWORD = os.getenv("PASSWORD", "")
NTFY_SERVER = os.getenv("NTFY_SERVER", "")
INSTITUTION = int(os.getenv("INSTITUTION", "6"))
NOTIFICATION_LEVEL = int(os.getenv("NOTIFICATION_LEVEL", "0"))
NOTIFY_EXTENDED = int(os.getenv("NOTIFY_EXTENDED", "1"))

CMS_URL = "https://cms.bahria.edu.pk/Logins/Student/Login.aspx"
LMS_ASSIGNMENTS_URL = "https://lms.bahria.edu.pk/Student/Assignments.php"
LMS_LOGOUT_URL = "https://lms.bahria.edu.pk/Student/includes/studentprocess.php?s=signout"
CMS_LOGOUT_URL = "https://cms.bahria.edu.pk/Sys/Student/Logoff.aspx"

LEVEL_TO_MAX_DAYS = {0: 0, 1: 4, 2: 7, 3: 14, 4: float("inf")}


def validate():
    errors = []
    if not ENROLLMENT_NUMBER:
        errors.append("ENROLLMENT_NUMBER is not set.")
    if not PASSWORD:
        errors.append("PASSWORD is not set.")
    if not NTFY_SERVER:
        errors.append("NTFY_SERVER is not set.")
    if NOTIFICATION_LEVEL < 0 or NOTIFICATION_LEVEL > 4:
        errors.append("NOTIFICATION_LEVEL must be between 0 and 4.")
    return errors
