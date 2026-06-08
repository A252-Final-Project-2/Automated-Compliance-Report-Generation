from flask import (
    Blueprint,
    render_template,
    send_file,
    send_from_directory,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    current_app,
    flash,
    make_response,
    abort,
)

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth

from io import BytesIO
from datetime import datetime, timedelta, timezone
import calendar
from zoneinfo import ZoneInfo
import uuid
# from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
try:
    from PIL import Image, UnidentifiedImageError
except Exception:
    Image = None
    UnidentifiedImageError = Exception
import os
import json
import re
import hashlib
from functools import wraps, lru_cache
try:
    from .database.db import get_connection
except ImportError:  # pragma: no cover - fallback for direct execution from module3/
    from database.db import get_connection

try:
    from .encryption_utils import (
        encrypt_text as _encrypt_text,
        decrypt_text as _decrypt_text,
        is_encrypted_text as _is_encrypted_text,
    )
except ImportError:  # pragma: no cover - fallback for direct execution from module3/
    from encryption_utils import (
        encrypt_text as _encrypt_text,
        decrypt_text as _decrypt_text,
        is_encrypted_text as _is_encrypted_text,
    )

# --------------------------------
# IMPORT DATA & SERVICES
# --------------------------------
try:
    from .config_pdf_labels import PDF_LABELS
    from .config_mappings import (
        STATUS_NORMALISE,
        STATUS_TRANSLATION,
        PRIORITY_TRANSLATION,
    )
    from .report_data import (
        build_report_data,
        get_available_projects,
        is_main_developer_account,
        get_homeowner_claimants,
        detect_missing_report_values,
        validate_report_requirements,
        ensure_profile_encryption_at_rest,
    )
    from .report_generator import (
        generate_ai_report,
        add_legal_metadata,
        format_legal_report,
        _fast_label,
    )
    from .prompts import get_language_config
    from .legal_metadata import get_legal_manager
except ImportError:  # pragma: no cover - fallback for direct execution from module3/
    from config_pdf_labels import PDF_LABELS
    from config_mappings import (
        STATUS_NORMALISE,
        STATUS_TRANSLATION,
        PRIORITY_TRANSLATION,
    )
    from report_data import (
        build_report_data,
        get_available_projects,
        is_main_developer_account,
        get_homeowner_claimants,
        detect_missing_report_values,
        validate_report_requirements,
        ensure_profile_encryption_at_rest,
    )
    from report_generator import (
        generate_ai_report,
        add_legal_metadata,
        format_legal_report,
    )
    from prompts import get_language_config
    from legal_metadata import get_legal_manager
# from prompts import get_language_config
try:
    from .ai_translate_cached import (
        translate_defects_cached,
        translate_report_cached,
        translate_remark_cached,
    )
except ImportError:  # pragma: no cover - fallback for direct execution from module3/
    from ai_translate_cached import (
        translate_defects_cached,
        translate_report_cached,
        translate_remark_cached,
    )

SIMULATED_LOGIN_USER_ID = int(os.getenv("SIMULATED_LOGIN_USER_ID", "1"))
AUTO_CLOSE_DAYS = int(os.getenv("AUTO_CLOSE_DAYS", "14"))
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Kuala_Lumpur")
REQUIRED_EVIDENCE_IMAGE_COUNT = 3
MODULE_ROOT = os.path.dirname(__file__)
AUDIT_DATA_DIR = os.path.join(MODULE_ROOT, "audit_data")
DELETE_DEFECT_LOG_PATH = os.path.join(AUDIT_DATA_DIR, "delete_defect.log")

# Global PDF typography constants (used by helpers like draw_footer).
# Times sizes are kept restrained so formal labels, Malay text, and long
# addresses fit A4 pages without looking cramped.
FONT_H1 = 14
FONT_H2 = 12
FONT_H3 = 11
FONT_BODY = 10.5
FONT_CAPTION = 9
FONT_MIN_READABLE = 8


def _append_delete_defect_log(entry):
    os.makedirs(AUDIT_DATA_DIR, exist_ok=True)
    with open(DELETE_DEFECT_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _draw_wrapped_text(pdf, x, y, text, max_width, leading=14, fontName='Times-Roman', fontSize=FONT_BODY):
    """Draw text on the canvas and wrap words to the next line when exceeding max_width.
    Special handling: if the text starts with a prefix like ": ", the first line will include
    the prefix but subsequent wrapped lines will be indented to align with the start of
    the first line's content (i.e., after the prefix).

    Returns number of lines drawn."""
    if not text:
        return 0
    pdf.setFont(fontName, fontSize)
    s = str(text)
    prefix = ''
    body = s
    # Detect common prefix like ': ' so wrapped lines align under the value, not under the label
    m = re.match(r'^(:\s+)(.*)$', s)
    if m:
        prefix = m.group(1)
        body = m.group(2)

    def split_oversized_word(word, available_width):
        if stringWidth(word, fontName, fontSize) <= available_width:
            return [word]

        chunks = []
        current = ""
        for char in word:
            test = current + char
            if current and stringWidth(test, fontName, fontSize) > available_width:
                chunks.append(current)
                current = char
            else:
                current = test
        if current:
            chunks.append(current)
        return chunks or [word]

    words = body.split()
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        # For the first line we must account for prefix width
        avail_width = max_width - (stringWidth(prefix, fontName, fontSize) if not lines and prefix else 0)
        if stringWidth(test, fontName, fontSize) <= avail_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
                avail_width = max_width
            chunks = split_oversized_word(w, avail_width)
            lines.extend(chunks[:-1])
            cur = chunks[-1]
    if cur:
        lines.append(cur)

    for i, line in enumerate(lines):
        if i == 0:
            # draw prefix + first line at base x
            pdf.drawString(x, y - i * leading, prefix + line)
        else:
            # subsequent lines start after prefix width
            indent_x = x + (stringWidth(prefix, fontName, fontSize) if prefix else 0)
            pdf.drawString(indent_x, y - i * leading, line)

    return len(lines)


def draw_fitted_string(pdf, x, y, text, max_width, font_name="Times-Roman", font_size=None, min_font_size=FONT_MIN_READABLE):
    """Draw one line, reducing size only when needed to keep text inside max_width."""
    text = str(text or "")
    font_size = font_size or FONT_BODY
    fitted_size = font_size
    while fitted_size > min_font_size and pdf.stringWidth(text, font_name, fitted_size) > max_width:
        fitted_size -= 0.5
    pdf.setFont(font_name, fitted_size)
    pdf.drawString(x, y, text)
    return fitted_size


def draw_centered_fitted_string(pdf, center_x, y, text, max_width, font_name="Times-Roman", font_size=None):
    text = str(text or "")
    font_size = font_size or FONT_BODY
    fitted_size = font_size
    while fitted_size > FONT_MIN_READABLE and pdf.stringWidth(text, font_name, fitted_size) > max_width:
        fitted_size -= 0.5
    pdf.setFont(font_name, fitted_size)
    pdf.drawCentredString(center_x, y, text)
    return fitted_size
ENABLE_DEMO_LOGIN_FALLBACK = os.getenv("ENABLE_DEMO_LOGIN_FALLBACK", "0") == "1"
SESSION_IDLE_TIMEOUT_MINUTES = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "120"))

DEMO_USERS = {
    "homeowner": {"password": "home123", "role": "Homeowner", "user_id": SIMULATED_LOGIN_USER_ID},
    "developer": {"password": "dev123", "role": "Developer", "user_id": None},
    "main_developer": {"password": "maindev123", "role": "Developer", "user_id": None},
    "legal": {"password": "legal123", "role": "Legal", "user_id": None},
    "admin": {"password": "admin123", "role": "Admin", "user_id": None},
}

UNIT_PROJECT_MAP = {

    "Johor": [
        "J-01-01",
        "J-01-02",
        "J-02-01",
        "J-03-03"
    ],

    "Kedah": [
        "KDH-01-01",
        "KDH-02-02",
        "KDH-03-01",
        "KDH-05-03"
    ],

    "Kelantan": [
        "KLT-01-02",
        "KLT-02-01",
        "KLT-04-03",
        "KLT-06-01"
    ],

    "Melaka": [
        "MLK-01-01",
        "MLK-03-02",
        "MLK-04-01",
        "MLK-08-03"
    ],

    "Negeri Sembilan": [
        "NS-02-08",
        "NS-03-01",
        "NS-05-02",
        "NS-07-01"
    ],

    "Pahang": [
        "PHG-01-01",
        "PHG-02-03",
        "PHG-07-01",
        "PHG-11-02"
    ],

    "Pulau Pinang": [
        "PNG-01-02",
        "PNG-04-01",
        "PNG-08-03",
        "PNG-09-01"
    ],

    "Perak": [
        "PRK-01-01",
        "PRK-03-02",
        "PRK-05-01",
        "PRK-06-04"
    ],

    "Perlis": [
        "PLS-01-02",
        "PLS-02-01",
        "PLS-03-03",
        "PLS-04-01"
    ],

    "Sabah": [
        "SBH-02-01",
        "SBH-04-02",
        "SBH-08-03",
        "SBH-12-01"
    ],

    "Sarawak": [
        "SWK-01-01",
        "SWK-03-02",
        "SWK-05-01",
        "SWK-07-03"
    ],

    "Selangor": [
        "SGR-01-01",
        "SGR-05-02",
        "SGR-10-01",
        "SGR-15-02"
    ],

    "Terengganu": [
        "TRG-01-01",
        "TRG-02-03",
        "TRG-03-02",
        "TRG-04-06"
    ],

    "Kuala Lumpur": [
        "KL-01-01",
        "KL-08-03",
        "KL-12-02",
        "KL-20-01"
    ],

    "Labuan": [
        "LBN-01-01",
        "LBN-02-02",
        "LBN-03-02",
        "LBN-04-01"
    ],

    "Putrajaya": [
        "PJY-01-01",
        "PJY-03-03",
        "PJY-06-01",
        "PJY-10-05"
    ]

}

STATE_COURT_MAP = {
    "Johor": {
        "tribunal_branches": ["Johor Bahru", "Batu Pahat", "Muar"],
        "general_locations": ["Kluang", "Segamat"],
    },
    "Kedah": {
        "tribunal_branches": ["Alor Setar", "Sungai Petani"],
        "general_locations": ["Kulim", "Langkawi"],
    },
    "Kelantan": {
        "tribunal_branches": ["Kota Bharu", "Pasir Mas"],
        "general_locations": ["Tumpat", "Tanah Merah"],
    },
    "Melaka": {
        "tribunal_branches": ["Melaka Tengah", "Alor Gajah"],
        "general_locations": ["Jasin"],
    },
    "Negeri Sembilan": {
        "tribunal_branches": ["Seremban", "Port Dickson"],
        "general_locations": ["Tampin", "Kuala Pilah"],
    },
    "Pahang": {
        "tribunal_branches": ["Kuantan", "Temerloh"],
        "general_locations": ["Pekan", "Bentong", "Raub"],
    },
    "Perak": {
        "tribunal_branches": ["Ipoh", "Taiping", "Kuala Kangsar"],
        "general_locations": ["Teluk Intan", "Sitiawan", "Parit Buntar"],
    },
    "Perlis": {
        "tribunal_branches": ["Kangar"],
        "general_locations": [],
    },
    "Pulau Pinang": {
        "tribunal_branches": ["George Town", "Seberang Jaya"],
        "general_locations": ["Bukit Mertajam"],
    },
    "Sabah": {
        "tribunal_branches": ["Kota Kinabalu", "Sandakan", "Tawau"],
        "general_locations": ["Keningau", "Beaufort", "Lahad Datu"],
    },
    "Sarawak": {
        "tribunal_branches": ["Kuching", "Sibu", "Miri"],
        "general_locations": ["Bintulu", "Sri Aman", "Limbang"],
    },
    "Selangor": {
        "tribunal_branches": ["Shah Alam", "Petaling Jaya", "Klang"],
        "general_locations": ["Kajang", "Selayang"],
    },
    "Terengganu": {
        "tribunal_branches": ["Kuala Terengganu", "Dungun"],
        "general_locations": ["Kemaman", "Besut"],
    },
    "W.P. Kuala Lumpur": {
        "tribunal_branches": ["Kuala Lumpur", "Jalan Duta"],
        "general_locations": ["Setapak"],
    },
    "W.P. Putrajaya": {
        "tribunal_branches": ["Putrajaya"],
        "general_locations": [],
    },
    "Labuan": {
        "tribunal_branches": ["Labuan"],
        "general_locations": [],
    },
    "W.P. Labuan": {
        "tribunal_branches": ["Labuan"],
        "general_locations": [],
    },
}

ITEM_SERVICE_TRANSLATIONS = {
    "Defect Repair During DLP": {
        "en": "Defect Repair During DLP",
        "ms": "Pembaikan Kecacatan Dalam Tempoh DLP",
    },
    "Home Repair Works": {
        "en": "Home Repair Works",
        "ms": "Kerja Pembaikan Rumah",
    },
    "Post-Handover Defect Rectification": {
        "en": "Post-Handover Defect Rectification",
        "ms": "Kerja Pembetulan Kecacatan Selepas Serahan Milikan",
    },
    "Others": {
        "en": "Others",
        "ms": "Lain-lain",
    },
}

ITEM_SERVICE_ALIASES = {
    "defect repair during dlp": "Defect Repair During DLP",
    "defect repairs during dlp period": "Defect Repair During DLP",
    "pembaikan kecacatan dalam tempoh dlp": "Defect Repair During DLP",
    "home repair works": "Home Repair Works",
    "kerja pembaikan rumah": "Home Repair Works",
    "post-handover defect rectification": "Post-Handover Defect Rectification",
    "defect repair after handover": "Post-Handover Defect Rectification",
    "defect repair during dlp": "Defect Repair During DLP",
    "lain-lain": "Others",
    "others": "Others",
}


def _default_item_service():
    return "Defect Repair During DLP"


def _normalise_item_service(value):
    raw = (value or "").strip()
    if not raw:
        return _default_item_service()

    if raw in ITEM_SERVICE_TRANSLATIONS:
        return raw

    return ITEM_SERVICE_ALIASES.get(raw.lower(), _default_item_service())


def _item_service_for_language(value, language):
    canonical = _normalise_item_service(value)
    language_key = "ms" if language == "ms" else "en"
    return ITEM_SERVICE_TRANSLATIONS.get(canonical, ITEM_SERVICE_TRANSLATIONS[_default_item_service()])[language_key]


def _get_court_locations_for_state(state_name):
    state_entry = STATE_COURT_MAP.get(state_name) or {}
    tribunal_branches = state_entry.get("tribunal_branches") or []
    general_locations = state_entry.get("general_locations") or []
    return tribunal_branches + [location for location in general_locations if location not in tribunal_branches]

LOGIN_ACCOUNT_SEED = [
    {
        "username": "homeowner",
        "password": "home123",
        "role": "Homeowner",
        "full_name": "Homeowner A",
        "email": "homeowner1@demo.local",
    },
    {
        "username": "developer",
        "password": "dev123",
        "role": "Developer",
        "full_name": "Developer A",
        "unit": "Developer Office",
        "email": "developer1@demo.local",
    },
    {
        "username": "main_developer",
        "password": "maindev123",
        "role": "Developer",
        "full_name": "Main Developer",
        "unit": "Main Developer Office",
        "email": "main.developer@demo.local",
    },
    {
        "username": "legal",
        "password": "legal123",
        "role": "Legal",
        "full_name": "Legal A",
        "unit": "Legal Office",
        "email": "legal1@demo.local",
    },
    {
        "username": "admin",
        "password": "admin123",
        "role": "Admin",
        "full_name": "Admin A",
        "unit": "Admin Office",
        "email": "admin1@demo.local",
    },
    {
        "username": "homeowner2",
        "password": "home223",
        "role": "Homeowner",
        "full_name": "Homeowner B",
        "unit": "A-02-02",
        "email": "homeowner2@demo.local",
    },
]


def _is_password_hash(value):
    if not value:
        return False
    return value.startswith(("scrypt:", "pbkdf2:", "argon2:", "bcrypt:"))


def _ensure_login_accounts_seeded():
    """Ensure built-in demo accounts exist and their known credentials work."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        for account in LOGIN_ACCOUNT_SEED:
            username = account["username"].strip().lower()
            password = account["password"]
            role = account["role"]
            full_name = account.get("full_name") or username
            unit = account.get("unit") or ""
            email = account.get("email") or ""
            requires_user_row = role != "Admin"

            cur.execute(
                """
                SELECT username, password, user_id
                FROM login_accounts
                WHERE LOWER(username) = LOWER(%s)
                LIMIT 1
                """,
                (username,),
            )
            existing_login = cur.fetchone()
            user_id = existing_login[2] if existing_login and existing_login[2] else None

            if requires_user_row and not user_id:
                cur.execute(
                    """
                    INSERT INTO users (full_name, unit, email, role)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (_encrypt_text(full_name), _encrypt_text(unit), _encrypt_text(email), role),
                )
                user_id = cur.fetchone()[0]

            if existing_login:
                stored_password = existing_login[1] or ""
                password_matches = (
                    check_password_hash(stored_password, password)
                    if _is_password_hash(stored_password)
                    else stored_password == password
                )
                hashed_password = (
                    stored_password
                    if _is_password_hash(stored_password) and password_matches
                    else generate_password_hash(password)
                )
                cur.execute(
                    """
                    UPDATE login_accounts
                    SET password = %s,
                        role = %s,
                        user_id = %s,
                        is_active = TRUE
                    WHERE LOWER(username) = LOWER(%s)
                    """,
                    (hashed_password, role, user_id, username),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO login_accounts (username, password, role, user_id, is_active)
                    VALUES (%s, %s, %s, %s, TRUE)
                    """,
                    (username, generate_password_hash(password), role, user_id),
                )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

# --------------------------------
# BLUEPRINT
# --------------------------------
routes = Blueprint("routes", __name__)
bp = routes

# --------------------------------
# IMAGE UPLOAD CONFIG
# --------------------------------
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'tif', 'tiff', 'jfif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _now_app_timezone():
    try:
        return datetime.now(ZoneInfo(APP_TIMEZONE))
    except Exception:
        # Fallback for environments without tzdata (common in slim containers).
        if APP_TIMEZONE == "Asia/Kuala_Lumpur":
            return datetime.now(timezone.utc) + timedelta(hours=8)
        return datetime.now()


def _resolve_evidence_image_path(evidence_dir, defect_id, evidence_filename=None):
    if not evidence_dir or not os.path.isdir(evidence_dir):
        return None

    # 1) Try exact filename from metadata.
    candidate_name = (evidence_filename or "").strip()
    if candidate_name and candidate_name != "-":
        direct_candidate = os.path.join(evidence_dir, os.path.basename(candidate_name))
        if os.path.exists(direct_candidate):
            return direct_candidate

    # 2) Case-insensitive search by metadata basename.
    if candidate_name and candidate_name != "-":
        basename_lower = os.path.basename(candidate_name).lower()
        for fname in os.listdir(evidence_dir):
            if fname.lower() == basename_lower:
                full_path = os.path.join(evidence_dir, fname)
                if os.path.isfile(full_path):
                    return full_path

    # 3) Fallback by legacy defect_<id> naming, case-insensitive and any extension.
    legacy_prefixes = (f"defect_{defect_id}.".lower(), f"defect_{defect_id}_".lower())
    for fname in os.listdir(evidence_dir):
        if fname.lower().startswith(legacy_prefixes):
            full_path = os.path.join(evidence_dir, fname)
            if os.path.isfile(full_path):
                return full_path

    return None


def _evidence_items_from_meta(evidence_meta):
    if not evidence_meta:
        return []
    if isinstance(evidence_meta, dict):
        raw_items = evidence_meta.get("files")
        if isinstance(raw_items, list):
            items = raw_items
        elif evidence_meta.get("filename"):
            items = [evidence_meta]
        else:
            items = []
    elif isinstance(evidence_meta, list):
        items = evidence_meta
    else:
        items = []

    normalized = []
    for item in items:
        if not isinstance(item, dict) or not item.get("filename"):
            continue
        normalized.append({
            "filename": item.get("filename"),
            "uploaded_at": item.get("uploaded_at") or "-",
        })
    return normalized[:REQUIRED_EVIDENCE_IMAGE_COUNT]


def _evidence_filename_index(filename):
    match = re.search(r"_(\d+)(?:_[^.]+)?\.[^.]+$", os.path.basename(filename or ""))
    if not match:
        return REQUIRED_EVIDENCE_IMAGE_COUNT + 1
    try:
        return int(match.group(1))
    except ValueError:
        return REQUIRED_EVIDENCE_IMAGE_COUNT + 1


def _delete_json_defect_entry(file_path, defect_id):
    if not os.path.exists(file_path):
        return False

    defect_key = str(defect_id)
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return False

    if not isinstance(payload, dict) or defect_key not in payload:
        return False

    payload.pop(defect_key, None)
    try:
        with open(file_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _delete_defect_sidecar_json(defect_id):
    module_root = os.path.dirname(__file__)
    sidecar_files = (
        os.path.join(module_root, "data", "remarks.json"),
        os.path.join(module_root, "data", "status.json"),
        os.path.join(module_root, "data", "completion_dates.json"),
        os.path.join(module_root, "data", "evidence.json"),
        os.path.join(module_root, "audit_data", "evidence.json"),
    )

    removed = []
    for file_path in sidecar_files:
        if _delete_json_defect_entry(file_path, defect_id):
            removed.append(os.path.relpath(file_path, module_root))
    return removed


def _collect_defect_evidence_paths(defect_id, evidence_filename=None):
    evidence_dir = os.path.join(current_app.root_path, "evidence")
    if not os.path.isdir(evidence_dir):
        return []

    paths = set()
    resolved_path = _resolve_evidence_image_path(evidence_dir, defect_id, evidence_filename)
    if resolved_path:
        paths.add(os.path.abspath(resolved_path))

    legacy_prefixes = (f"defect_{defect_id}.".lower(), f"defect_{defect_id}_".lower())
    for filename in os.listdir(evidence_dir):
        if filename.lower().startswith(legacy_prefixes):
            paths.add(os.path.abspath(os.path.join(evidence_dir, filename)))

    evidence_root = os.path.abspath(evidence_dir)
    return sorted(
        path for path in paths
        if os.path.commonpath([evidence_root, path]) == evidence_root and os.path.isfile(path)
    )


def _delete_files(paths):
    deleted = []
    failed = []
    for path in paths:
        try:
            os.remove(path)
            deleted.append(os.path.basename(path))
        except FileNotFoundError:
            pass
        except Exception as exc:
            failed.append({"file": os.path.basename(path), "error": str(exc)})
    return deleted, failed


def _delete_owned_defect(defect_id, user_id):
    conn = get_connection()
    cur = conn.cursor()
    evidence_paths = []
    evidence_filename = None
    cleanup_summary = {
        "database_tables": [],
        "files_deleted": [],
        "file_delete_errors": [],
        "sidecar_json": [],
    }

    try:
        cur.execute(
            """
            SELECT id
            FROM defects
            WHERE id = %s
              AND user_id = %s
            """,
            (defect_id, user_id),
        )
        defect = cur.fetchone()
        if not defect:
            conn.rollback()
            return None

        related_tables = {"remarks", "completion_dates", "evidence"}
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = ANY(%s)
            """,
            (list(related_tables),),
        )
        existing_related_tables = {row[0] for row in cur.fetchall()}

        if "evidence" in existing_related_tables:
            cur.execute(
                """
                SELECT filename
                FROM evidence
                WHERE defect_id = %s
                ORDER BY uploaded_at DESC
                LIMIT 1
                """,
                (defect_id,),
            )
            evidence_row = cur.fetchone()
            evidence_filename = evidence_row[0] if evidence_row else None

        evidence_paths = _collect_defect_evidence_paths(defect_id, evidence_filename)

        for table_name in ("remarks", "completion_dates", "evidence"):
            if table_name not in existing_related_tables:
                continue
            cur.execute(f"DELETE FROM {table_name} WHERE defect_id = %s", (defect_id,))
            if cur.rowcount:
                cleanup_summary["database_tables"].append(table_name)

        cur.execute("DELETE FROM defects WHERE id = %s AND user_id = %s", (defect_id, user_id))
        if cur.rowcount != 1:
            conn.rollback()
            return None

        cleanup_summary["database_tables"].append("defects")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    deleted_files, failed_files = _delete_files(evidence_paths)
    cleanup_summary["files_deleted"] = deleted_files
    cleanup_summary["file_delete_errors"] = failed_files
    cleanup_summary["sidecar_json"] = _delete_defect_sidecar_json(defect_id)
    return cleanup_summary


def _current_role():
    return session.get("role")


def _current_user_id():
    user_id = session.get("user_id")
    if user_id:
        return user_id

    if ENABLE_DEMO_LOGIN_FALLBACK:
        return SIMULATED_LOGIN_USER_ID

    username = (session.get("username") or "").strip()
    if not username:
        return None

    try:
        _ensure_login_accounts_seeded()
    except Exception:
        pass

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT user_id FROM login_accounts WHERE LOWER(username) = LOWER(%s) LIMIT 1",
            (username,),
        )
        row = cur.fetchone()
        if row and row[0]:
            return row[0]

        role = (session.get("role") or "").strip()
        if role:
            cur.execute(
                "SELECT id FROM users WHERE role = %s ORDER BY id ASC LIMIT 1",
                (role,),
            )
            row = cur.fetchone()
            if row and row[0]:
                return row[0]

        return None
    finally:
        cur.close()
        conn.close()


# Provide `role` and `user_info` to all templates automatically so templates
# don't need to pass them explicitly in every `render_template` call.
@routes.context_processor
def _inject_user_context():
    try:
        role = session.get("role")
        username = session.get("username")
        user_info = None
        user_id = _current_user_id()
        conn = None
        cur = None
        if user_id:
            try:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT
                        full_name,
                        unit,
                        role,
                        email,
                        avatar_url
                    FROM users
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (user_id,)
                )
                row = cur.fetchone()
                if row:

                    # If the session `role` is set but the resolved DB row's
                    # role doesn't match the session role, attempt to find a
                    # user record that matches the session username and role
                    # (this prevents showing Legal profile when the session
                    # is actually Developer and the `user_id` mapped to a
                    # different account).
                    if role and row[2] and row[2] != role:
                        try:
                            cur.execute(
                                """
                                SELECT u.full_name, u.unit, u.role, u.email, u.avatar_url, u.id
                                FROM users u
                                JOIN login_accounts la ON la.user_id = u.id
                                WHERE LOWER(la.username) = LOWER(%s)
                                  AND LOWER(la.role) = LOWER(%s)
                                LIMIT 1
                                """,
                                (username or '', role or '')
                            )
                            alt = cur.fetchone()
                            if alt:
                                # Replace the originally fetched row with the
                                # role-matching user row.
                                row = (alt[0], alt[1], alt[2], alt[3], alt[4])
                                # Also update user_id so downstream logic stays consistent
                                user_id = alt[5]
                        except Exception:
                            pass

                    full_name_enc, unit_enc, role_db, email_enc, avatar_url = row

                    try:
                        name = _decrypt_text(full_name_enc) if full_name_enc else None
                    except Exception:
                        name = full_name_enc

                    try:
                        unit = _decrypt_text(unit_enc) if unit_enc else None
                    except Exception:
                        unit = unit_enc

                    try:
                        email = _decrypt_text(email_enc) if email_enc else None
                    except Exception:
                        email = email_enc

                    # DEFAULT USER INFO
                    # Prefer the session role for display. Only use DB role when
                    # session role is not present. This prevents showing a Legal
                    # profile when the session is actually a Developer session.
                    display_role = role or role_db
                    user_info = {
                        "name": name or username,
                        "company_name": None,
                        "unit": unit,
                        "role": display_role,
                        "email": email,
                        "avatar_url": avatar_url,
                        "last_login": None,
                        "activity": None,
                    }

                    # LEGAL PROFILE OVERRIDE - only apply when the current
                    # session role is Legal so we don't override Developer
                    # sessions with Legal profile data.
                    if role == "Legal":

                        cur.execute(
                            """
                            SELECT
                                legal_name,
                                phone_number,
                                email,
                                office_address
                            FROM report_legal_profile
                            WHERE legal_user_id = %s
                            LIMIT 1
                            """,
                            (user_id,)
                        )

                        legal_row = cur.fetchone()

                        if legal_row:

                            legal_name = (
                                _decrypt_text(legal_row[0])
                                if legal_row[0] else None
                            )

                            legal_email = (
                                _decrypt_text(legal_row[2])
                                if legal_row[2] else None
                            )

                            user_info = {
                                "name": legal_name or username,
                                "company_name": legal_name or "Legal Practitioner",
                                "unit": "Legal Office",
                                "role": "Legal",
                                "email": legal_email or email,
                                "avatar_url": avatar_url,
                                "last_login": None,
                                "activity": None,
                            }
                    # DEVELOPER PROFILE OVERRIDE - populate company info when
                    # the current session role is Developer so the sidebar
                    # displays company-related metadata instead of a unit.
                    if role == "Developer":
                        # Always clear the `unit` for Developer sessions when
                        # the session role indicates Developer. This addresses
                        # cases where `login_accounts.user_id` points to a
                        # different-role `users` row (e.g., Legal) but the
                        # session authentication is for Developer. Prefer
                        # showing company information and avoid displaying
                        # the avatar/name from a mismatched Legal user row.
                        user_info.update({
                            "company_name": user_info.get("company_name") or user_info.get("name"),
                            "unit": "",
                            "person_in_charge": None,
                        })
                        # If the underlying DB `users` row is not a Developer
                        # (mismatched), avoid using that row's avatar/name.
                        if role_db and role_db != "Developer":
                            user_info["avatar_url"] = None
                            # prefer company_name as display name
                            if user_info.get("company_name"):
                                user_info["name"] = user_info.get("company_name")
                        try:
                            cur.execute(
                                """
                                SELECT company_name, person_in_charge, registration_number, phone_number, email, address
                                FROM report_respondent_profile
                                WHERE respondent_id = %s
                                LIMIT 1
                                """,
                                (user_id,)
                            )
                            dev_row = cur.fetchone()
                            if dev_row:
                                dev_name = _decrypt_text(dev_row[0]) if dev_row[0] else None
                                dev_pic = _decrypt_text(dev_row[1]) if dev_row[1] else None
                                dev_email = _decrypt_text(dev_row[4]) if dev_row[4] else None
                                user_info.update({
                                    "company_name": dev_name or user_info.get("company_name") or user_info.get("name"),
                                    "name": dev_name or user_info.get("company_name") or user_info.get("name"),
                                    "person_in_charge": dev_pic or user_info.get("person_in_charge"),
                                    "unit": "",
                                    "email": dev_email or user_info.get("email"),
                                })
                        except Exception:
                            pass
            except Exception:
                user_info = {"name": username, "role": role} if username or role else None
            finally:
                if cur:
                    try:
                        cur.close()
                    except Exception:
                        pass
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        return {"role": role, "user_info": user_info, "username": username}
    except Exception:
        # Safe fallback: log traceback to file for debugging and return minimal context.
        try:
            import traceback
            with open('template_context_error.log', 'a', encoding='utf-8') as fh:
                fh.write('\n--- %s ---\n' % datetime.utcnow().isoformat())
                fh.write(traceback.format_exc())
        except Exception:
            pass
        return {"role": session.get('role'), "user_info": None, "username": session.get('username')}


def _append_audit_event(action, role=None, defect_id=None, filename=None, new_status=None, details=None):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO audit_log (action, role, defect_id, filename, new_status, timestamp, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                action,
                role,
                defect_id,
                filename,
                new_status,
                _now_app_timezone().strftime("%Y-%m-%d %H:%M:%S"),
                json.dumps(details or {}),
            ),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _get_login_account(username, password, selected_role):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT username, role, user_id, password
            FROM login_accounts
            WHERE LOWER(username) = LOWER(%s)
              AND LOWER(role) = LOWER(%s)
              AND is_active = TRUE
            LIMIT 1
            """,
            (username, selected_role),
        )
        row = cur.fetchone()
        if not row:
            return None

        stored_password = row[3] or ""
        password_valid = False

        if _is_password_hash(stored_password):
            password_valid = check_password_hash(stored_password, password)
        else:
            password_valid = stored_password == password
            if password_valid:
                cur.execute(
                    "UPDATE login_accounts SET password = %s WHERE username = %s",
                    (generate_password_hash(password), row[0]),
                )
                conn.commit()

        if not password_valid:
            return None

        return {
            "username": row[0],
            "role": row[1],
            "user_id": row[2],
        }
    finally:
        cur.close()
        conn.close()


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not _current_role():
            # If this is an AJAX/fetch request or the client prefers JSON,
            # return JSON error instead of redirecting to the login page.
            try:
                is_xhr = (request.headers.get('X-Requested-With') == 'XMLHttpRequest')
                prefers_json = request.accept_mimetypes.accept_json
            except Exception:
                is_xhr = False
                prefers_json = False

            if is_xhr or prefers_json:
                return jsonify({"error": "Unauthorized"}), 401

            return redirect(url_for("routes.login"))

        last_activity_raw = session.get("last_activity")
        if last_activity_raw:
            try:
                now_local = _now_app_timezone()
                last_activity = datetime.fromisoformat(last_activity_raw)
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=now_local.tzinfo)
                if now_local - last_activity > timedelta(minutes=SESSION_IDLE_TIMEOUT_MINUTES):
                    session.clear()
                    return redirect(url_for("routes.login"))
            except Exception:
                session.clear()
                return redirect(url_for("routes.login"))

        session["last_activity"] = _now_app_timezone().isoformat()
        return func(*args, **kwargs)

    return wrapper


@routes.route("/login", methods=["GET", "POST"])
def login():
    if _current_role():
        return redirect(url_for("routes.dashboard"))

    info = session.pop('signup_info', None)
    auth_error = session.pop('auth_error', None)
    error = None
    selected_username = ""
    selected_role = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        selected_role = (request.form.get("role") or "").strip().lower()
        selected_username = username

        if not selected_role:
            error = "Please select a role"
            return render_template(
                "login.html",
                error=error,
                selected_username=selected_username,
                selected_role=selected_role,
                info=info,
            )

        account = None
        try:
            _ensure_login_accounts_seeded()
            account = _get_login_account(username, password, selected_role)
        except Exception as exc:
            current_app.logger.exception("Database login failed: %s", exc)
            # Graceful fallback if DB auth table is temporarily unavailable.
            account = None

        if not account and ENABLE_DEMO_LOGIN_FALLBACK:
            user = DEMO_USERS.get(username)
            if user and password == user["password"] and user["role"].lower() == selected_role:
                account = {
                    "username": username,
                    "role": user["role"],
                    "user_id": user.get("user_id"),
                }
                # Ensure seeded login_accounts exist and map the demo username
                # to a real `users.id` if possible so profile lookup returns the
                # correct developer/legal user rather than falling back to the
                # first user of that role.
                try:
                    _ensure_login_accounts_seeded()
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT user_id FROM login_accounts WHERE LOWER(username) = LOWER(%s) LIMIT 1",
                        (username,)
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        account["user_id"] = row[0]
                except Exception:
                    pass
                finally:
                    try:
                        cur.close()
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass

        if account:
            session.clear()
            session["username"] = account["username"]
            session["role"] = account["role"]
            session["last_activity"] = _now_app_timezone().isoformat()
            session.permanent = False
            if account.get("user_id"):
                session["user_id"] = account["user_id"]
            else:
                session.pop("user_id", None)

            _append_audit_event(
                action="Login Succeeded",
                role=account["role"],
                details={
                    "username": account["username"],
                    "selected_role": selected_role,
                },
            )
            return redirect(url_for("routes.dashboard"))

        _append_audit_event(
            action="Login Failed",
            role=selected_role.title() if selected_role else None,
            details={
                "username": username,
                "selected_role": selected_role,
                "reason": "invalid credentials",
            },
        )
        error = "Invalid username or password"

    return render_template(
        "login.html",
        error=error,
        auth_error=auth_error,
        selected_username=selected_username,
        selected_role=selected_role,
        info=info,
    )


@routes.route("/signup", methods=["GET", "POST"])
def signup():
    if _current_role():
        return redirect(url_for("routes.dashboard"))

    error = None
    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()
        unit = (request.form.get("unit") or "").strip()
        role = (request.form.get("role") or "").strip()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""
        accept_terms = request.form.get("accept_terms")

        if not full_name or not username or not role or not password:
            error = "Please complete required fields"
            return render_template("signup.html", error=error)

        if not accept_terms:
            error = "You must accept the terms and privacy policy to create an account"
            return render_template("signup.html", error=error)

        if len(username) < 3:
            error = "Username must be at least 3 characters"
            return render_template("signup.html", error=error)

        if password != confirm_password:
            error = "Passwords do not match"
            return render_template("signup.html", error=error)

        password_pattern = re.compile(
            r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])"
        )
        if (
            len(password) < 8
            or not password_pattern.search(password)
        ):
            error = (
                "Password must contain uppercase, lowercase, "
                "number and special character"
            )
            return render_template(
                "signup.html",
                error=error
            )

        # Basic email validation if provided
        if email:
            email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
            if not email_re.match(email):
                error = "Enter a valid email address"
                return render_template("signup.html", error=error)

        role_normalised = role.title()
        if role_normalised != "Homeowner":
            error = "Invalid role selected"
            return render_template("signup.html", error=error)

        conn = get_connection()
        cur = conn.cursor()
        try:
            # Check username uniqueness
            cur.execute("SELECT 1 FROM login_accounts WHERE LOWER(username) = LOWER(%s) LIMIT 1", (username,))
            if cur.fetchone():
                error = "Username already exists"
                return render_template("signup.html", error=error, error_field="username")

            # Check email uniqueness against encrypted user records.
            if email:
                cur.execute("SELECT id, email FROM users WHERE email IS NOT NULL AND email <> ''")
                email_normalized = email.strip().lower()
                for _, stored_email in cur.fetchall():
                    if (_decrypt_text(stored_email) or "").strip().lower() == email_normalized:
                        error = "Email already exists"
                        return render_template("signup.html", error=error, error_field="email")

            # Create user entry
            cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM users")
            next_user_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO users (id, full_name, unit, role, email)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (next_user_id, _encrypt_text(full_name), _encrypt_text(unit), role_normalised, _encrypt_text(email)),
            )

            # Create login account
            cur.execute(
                """
                INSERT INTO login_accounts (username, password, role, user_id, is_active)
                VALUES (%s, %s, %s, %s, TRUE)
                """,
                (username, generate_password_hash(password), role_normalised, next_user_id),
            )

            conn.commit()
        finally:
            cur.close()
            conn.close()

        _append_audit_event(action="Account Created", role=role_normalised, details={"username": username})
        session['signup_info'] = "Account created. You may now sign in."
        return redirect(url_for("routes.login"))

    return render_template("signup.html")

# CHECK USERNAME AVAILABILITY
@routes.route('/check-username')
def check_username():
    username = (
        request.args.get('username') or ''
    ).strip()
    if not username:
        return jsonify({
            'exists': False
        })
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT 1
            FROM login_accounts
            WHERE LOWER(username) = LOWER(%s)
            LIMIT 1
            """,
            (username,)
        )
        exists = cur.fetchone() is not None
        return jsonify({
            'exists': exists
        })
    finally:
        cur.close()
        conn.close()

# CHECK DUPLICATE USER DATA
@routes.route('/check-user-data')
def check_user_data():

    email = (
        request.args.get('email') or ''
    ).strip()

    phone_number = (
        request.args.get('phone_number') or ''
    ).strip()

    ic_number = (
        request.args.get('ic_number') or ''
    ).strip()

    conn = get_connection()
    cur = conn.cursor()

    result = {
        'email_exists': False,
        'phone_exists': False,
        'ic_exists': False
    }

    try:

        # EMAIL
        if email:
            cur.execute(
                """
                SELECT email
                FROM users
                WHERE email IS NOT NULL
                """
            )
            email_normalized = (
                email.strip().lower()
            )
            for row in cur.fetchall():
                stored_email = (
                    (_decrypt_text(row[0]) or '')
                    .strip()
                    .lower()
                )
                if stored_email == email_normalized:
                    result['email_exists'] = True
                    break

        # PHONE
        if phone_number:
            cur.execute(
                """
                SELECT phone_number
                FROM report_homeowner_profile
                WHERE phone_number IS NOT NULL
                """
            )
            for row in cur.fetchall():

                stored_phone = (
                    (_decrypt_text(row[0]) or '')
                    .strip()
                )
                if stored_phone == phone_number:
                    result['phone_exists'] = True
                    break

        # IC
        if ic_number:

            cur.execute(
                """
                SELECT ic_number
                FROM report_homeowner_profile
                WHERE ic_number IS NOT NULL
                """
            )

            for row in cur.fetchall():

                stored_ic = (
                    (_decrypt_text(row[0]) or '')
                    .strip()
                )

                if stored_ic == ic_number:

                    result['ic_exists'] = True
                    break

        return jsonify(result)

    finally:

        cur.close()
        conn.close()


@routes.route('/api/delete_defect/<int:defect_id>', methods=['POST', 'DELETE'])
@login_required
def api_delete_defect(defect_id):
    """API variant that always returns JSON and explicit status codes.
    This avoids fetch receiving HTML (redirect/login page) which causes
    client-side JSON parsing to fail and shows misleading error messages.
    """
    if _current_role() != "Homeowner":
            return jsonify({"success": False, "error": "Unauthorized"}), 403

    user_id = _current_user_id()

    try:
        cleanup_summary = _delete_owned_defect(defect_id, user_id)
        if cleanup_summary is None:
            return jsonify({"success": False, "error": "Defect not found"}), 404

        try:
            _append_audit_event(
                action="Defect Deleted",
                role="Homeowner",
                details={
                    "defect_id": defect_id,
                    "cleanup": cleanup_summary,
                },
            )
        except Exception:
            pass

        try:
            _append_delete_defect_log({
                "timestamp": _now_app_timezone().isoformat(),
                "action": "api_delete_defect",
                "defect_id": defect_id,
                "user_id": user_id,
                "status": "deleted",
                "cleanup": cleanup_summary,
            })
        except Exception:
            pass

        return jsonify({"success": True}), 200

    except Exception as e:
        # Log exception details for debugging
        try:
            import traceback
            _append_delete_defect_log({
                "timestamp": _now_app_timezone().isoformat(),
                "action": "api_delete_defect_error",
                "defect_id": defect_id,
                "user_id": user_id,
                "error": str(e),
                "trace": traceback.format_exc(),
            })
        except Exception:
            pass
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():

    error = None
    success = None

    if request.method == 'POST':

        username = (
            request.form.get('username') or ''
        ).strip()

        role = (
            request.form.get('role') or ''
        ).strip()

        role_map = {
            "homeowner": "Homeowner",
            "developer": "Developer",
            "legal": "Legal",
            "admin": "Admin",
        }
        role_normalised = role_map.get(role.lower(), role)

        last4 = (
            request.form.get('last4') or ''
        ).strip()
        last4_digits = re.sub(r"\D", "", last4)

        password = (
            request.form.get('password') or ''
        ).strip()

        confirm_password = (
            request.form.get('confirm_password') or ''
        ).strip()

        # VALIDATION
        if password != confirm_password:

            error = (
                "Passwords do not match."
            )

        elif len(last4_digits) != 4:

            error = (
                "Please enter the last 4 digits of your registered phone number."
            )

        elif len(password) < 8:

            error = (
                "Password must be at least 8 characters."
            )

        else:

            conn = get_connection()

            cur = conn.cursor()

            try:

                # Fetch account row (do not assume phone_number is stored on
                # login_accounts - it isn't in the current schema). Retrieve
                # user_id and hashed password, then look up a phone number
                # from the appropriate profile table depending on role.
                cur.execute(
                    """
                    SELECT user_id, password
                    FROM login_accounts
                    WHERE LOWER(username) = LOWER(%s)
                    AND LOWER(role) = LOWER(%s)
                    LIMIT 1
                    """,
                    (username, role_normalised)
                )

                row = cur.fetchone()

                if not row:
                    error = (
                        "Account not found."
                    )
                else:
                    user_id = row[0]
                    current_password = row[1] or ""

                    # Resolve stored phone from role-specific profile tables.
                    stored_phone = None
                    try:
                        if user_id:
                            role_name = role_normalised
                            if role_name == "Homeowner":
                                cur.execute(
                                    "SELECT phone_number FROM report_homeowner_profile WHERE homeowner_id = %s LIMIT 1",
                                    (user_id,),
                                )
                                r = cur.fetchone()
                                if r and r[0]:
                                    raw_phone = str(r[0] or "")
                                    stored_phone = _decrypt_display_text(raw_phone) or ("" if raw_phone.strip().startswith("gAAAA") else raw_phone)

                            elif role_name == "Developer":
                                cur.execute(
                                    "SELECT phone_number FROM report_respondent_profile WHERE respondent_id = %s LIMIT 1",
                                    (user_id,),
                                )
                                r = cur.fetchone()
                                if r and r[0]:
                                    raw_phone = str(r[0] or "")
                                    stored_phone = _decrypt_display_text(raw_phone) or ("" if raw_phone.strip().startswith("gAAAA") else raw_phone)

                            elif role_name == "Legal":
                                cur.execute(
                                    "SELECT phone_number FROM report_legal_profile WHERE legal_user_id = %s LIMIT 1",
                                    (user_id,),
                                )
                                r = cur.fetchone()
                                if r and r[0]:
                                    raw_phone = str(r[0] or "")
                                    stored_phone = _decrypt_display_text(raw_phone) or ("" if raw_phone.strip().startswith("gAAAA") else raw_phone)
                    except Exception:
                        # If any lookup fails, keep stored_phone as None so
                        # verification will fail safely below.
                        stored_phone = None

                    # VERIFY LAST 4 DIGITS
                    stored_phone_digits = re.sub(r"\D", "", str(stored_phone or ""))
                    if not stored_phone_digits or not stored_phone_digits.endswith(last4_digits):

                        error = (
                            "Phone verification failed."
                        )

                    # SAME PASSWORD
                    elif (
                        check_password_hash(current_password, password)
                        if _is_password_hash(current_password)
                        else current_password == password
                    ):

                        error = (
                            "New password cannot be the same as current password."
                        )

                    else:

                        hashed_password = (
                            generate_password_hash(
                                password
                            )
                        )

                        cur.execute(
                            """
                            UPDATE login_accounts
                            SET password = %s
                            WHERE LOWER(username) = LOWER(%s)
                            AND LOWER(role) = LOWER(%s)
                            """,
                            (
                                hashed_password,
                                username,
                                role_normalised
                            )
                        )

                        conn.commit()

                        success = (
                            "Password reset successful. Please login."
                        )

            finally:

                cur.close()

                conn.close()

    return render_template(
        'forgot_password.html',
        error=error,
        success=success
    )
    
@routes.route('/api/project-details/<project_name>')
@login_required
def get_project_details(project_name):

    conn = get_connection()
    cur = conn.cursor()

    try:

        cur.execute("""
            SELECT
                dp.id,
                dp.state_name,
                dp.property_address,

                d.company_name,
                dc.person_in_charge,
                d.registration_number,
                dc.phone_number,
                dc.email,
                dc.office_address

            FROM developer_projects dp

            JOIN developers d
                ON dp.developer_id = d.id

            LEFT JOIN developer_contacts dc
                ON dc.developer_id = d.id
                AND dc.state_name = dp.state_name

            WHERE dp.project_name = %s
        """, (project_name,))

        project = cur.fetchone()

        if not project:
            return jsonify({})

        project_id = project[0]

        cur.execute("""
            SELECT unit_number
            FROM project_units
            WHERE project_id = %s
            ORDER BY unit_number
        """, (project_id,))

        units = [row[0] for row in cur.fetchall()]

        return jsonify({
            "state": project[1],
            "address": project[2],

            "company_name": _decrypt_text(project[3]) if project[3] else "",
            "person_in_charge": _decrypt_text(project[4]) if project[4] else "",
            "registration_number": _decrypt_text(project[5]) if project[5] else "",
            "phone_number": _decrypt_text(project[6]) if project[6] else "",
            "email": _decrypt_text(project[7]) if project[7] else "",
            "developer_address": _decrypt_text(project[8]) if project[8] else "",

            "units": units
                })

    finally:
        cur.close()
        conn.close()

@routes.route('/profile')
@login_required
def profile():
    role = _current_role()
    user_info = get_current_user()
    user_id = _current_user_id()
    _users_avatar_url_column_ready()

    # account info
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT username FROM login_accounts WHERE user_id = %s LIMIT 1", (user_id,))
        acc_row = cur.fetchone()
        account = {"username": acc_row[0]} if acc_row else {"username": session.get('username')}

        # personal
        cur.execute("SELECT full_name, email, unit, role FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if row:
            personal = {
                "full_name": _decrypt_display_text(row[0]) if row[0] else "",
                "email": _decrypt_display_text(row[1]) if row[1] else "",
                "unit": _decrypt_display_text(row[2]) if row[2] else "",
                "role": row[3] or "",
            }
        else:
            personal = {"full_name": "", "email": "", "unit": "", "role": ""}

        # homeowner
        cur.execute("""
            SELECT
                name,
                phone_number,
                ic_number,
                address,
                court_location,
                state_name,
                item_service,
                transaction_date,
                claim_amount,
                defect_unit,
                project_name,
                defect_state,
                defect_property_address
            FROM report_homeowner_profile
            WHERE homeowner_id = %s
        """, (user_id,))

        hr = cur.fetchone()

        if hr:
            homeowner = {
                "name": _decrypt_text(hr[0]) if hr[0] else "",
                "phone_number": _decrypt_text(hr[1]) if hr[1] else "",
                "ic_number":_decrypt_text(hr[2]) if hr[2] else "",
                "address": _decrypt_text(hr[3]) if hr[3] else "",
                "court_location": _decrypt_text(hr[4]) if hr[4] else "",
                "state_name": _decrypt_text(hr[5]) if hr[5] else "",
                "item_service": _decrypt_text(hr[6]) if hr[6] else "",
                "transaction_date": _decrypt_text(hr[7]) if hr[7] else "",
                "claim_amount": _decrypt_text(hr[8]) if hr[8] else "",

                "defect_unit": _decrypt_text(hr[9]) if hr[9] else "",
                "project_name": _decrypt_text(hr[10]) if hr[10] else "",
                "defect_state": _decrypt_text(hr[11]) if hr[11] else "",
                "defect_property_address": _decrypt_text(hr[12]) if hr[12] else "",
            }
        else:
            homeowner = {
                "name": "",
                "phone_number": "",
                "ic_number": "",
                "address": "",
                "court_location": "",
                "state_name": "",
                "item_service": "",
                "transaction_date": "",
                "claim_amount": "",

                "defect_unit": "",
                "project_name": "",
                "defect_state": "",
                "defect_property_address": "",
            }
        # projects
        cur.execute("""
            SELECT
                dp.id,
                dp.project_name,
                dp.state_name,
                dp.property_address,

                d.company_name,
                d.registration_number

            FROM developer_projects dp

            JOIN developers d
                ON dp.developer_id = d.id

            ORDER BY dp.project_name
        """)

        project_rows = cur.fetchall()

        projects = []

        for row in project_rows:

            projects.append({
                "id": row[0],
                "project_name": row[1],
                "state_name": row[2],
                "property_address": row[3],
                "company_name": _decrypt_text(row[4]) if row[4] else "",
                "registration_number": _decrypt_text(row[5]) if row[5] else "",
            })
        respondent = {
            "company_name": "",
            "person_in_charge": "",
            "registration_number": "",
            "phone_number": "",
            "email": "",
            "address": "",
        }
        # respondent
        cur.execute("SELECT company_name, person_in_charge, registration_number, phone_number, email, address FROM report_respondent_profile WHERE respondent_id = %s", (user_id,))
        rr = cur.fetchone()
        if rr:
            respondent = {
                "company_name":
                    _decrypt_text(rr[0]) if rr[0] else "",

                "person_in_charge":
                    _decrypt_text(rr[1]) if rr[1] else "",

                "registration_number":
                    _decrypt_text(rr[2]) if rr[2] else "",

                "phone_number":
                    _decrypt_text(rr[3]) if rr[3] else "",

                "email":
                    _decrypt_text(rr[4]) if rr[4] else "",

                "address":
                    _decrypt_text(rr[5]) if rr[5] else "",
            }
        if role == "Developer":
            lookup_company = respondent.get("company_name") or user_info.get("company_name") or user_info.get("name")
            developer_row = None
            developer_id = None
            if lookup_company:
                cur.execute(
                    """
                    SELECT id, company_name, registration_number
                    FROM developers
                    WHERE LOWER(company_name) = LOWER(%s)
                    LIMIT 1
                    """,
                    (lookup_company,),
                )
                developer_row = cur.fetchone()
            if not developer_row:
                cur.execute(
                    """
                    SELECT id, company_name, registration_number
                    FROM developers
                    ORDER BY id ASC
                    LIMIT 1
                    """
                )
                developer_row = cur.fetchone()

            developer_id = developer_row[0] if developer_row and developer_row[0] else None
            if developer_row:
                respondent["company_name"] = _decrypt_text(developer_row[1]) if developer_row[1] else respondent.get("company_name", "")
                respondent["registration_number"] = _decrypt_text(developer_row[2]) if developer_row[2] else respondent.get("registration_number", "")

            if is_main_developer_account(user_id, session.get("username")):
                respondent["person_in_charge"] = ""
            elif developer_id:
                cur.execute(
                    """
                    SELECT person_in_charge, phone_number, email, office_address
                    FROM developer_contacts
                    WHERE developer_id = %s
                    ORDER BY CASE WHEN LOWER(state_name) = 'pulau pinang' THEN 0 ELSE 1 END, state_name ASC
                    LIMIT 1
                    """,
                    (developer_id,),
                )
                contact_row = cur.fetchone()
                if contact_row:
                    respondent["person_in_charge"] = _decrypt_text(contact_row[0]) if contact_row[0] else respondent.get("person_in_charge", "")
                    respondent["phone_number"] = _decrypt_text(contact_row[1]) if contact_row[1] else respondent.get("phone_number", "")
                    respondent["email"] = _decrypt_text(contact_row[2]) if contact_row[2] else respondent.get("email", "")
                    respondent["address"] = _decrypt_text(contact_row[3]) if contact_row[3] else respondent.get("address", "")
        elif homeowner.get("project_name"):
            cur.execute(
                """
                SELECT
                    d.company_name,
                    dc.person_in_charge,
                    d.registration_number,
                    dc.phone_number,
                    dc.email,
                    dc.office_address
                FROM developer_projects dp
                JOIN developers d
                    ON dp.developer_id = d.id
                LEFT JOIN developer_contacts dc
                    ON dc.developer_id = d.id
                   AND dc.state_name = dp.state_name
                WHERE dp.project_name = %s
                LIMIT 1
                """,
                (homeowner["project_name"],),
            )
            project_rr = cur.fetchone()
            if project_rr:
                respondent = {
                    "company_name": _decrypt_text(project_rr[0]) if project_rr[0] else "",
                    "person_in_charge": _decrypt_text(project_rr[1]) if project_rr[1] else "",
                    "registration_number": _decrypt_text(project_rr[2]) if project_rr[2] else "",
                    "phone_number": _decrypt_text(project_rr[3]) if project_rr[3] else "",
                    "email": _decrypt_text(project_rr[4]) if project_rr[4] else "",
                    "address": _decrypt_text(project_rr[5]) if project_rr[5] else "",
                }
        else:
            respondent = {"company_name": "", "person_in_charge": "", "registration_number": "", "phone_number": "", "address": ""}
        
        # legal
        cur.execute("SELECT legal_name, phone_number, email, office_address FROM report_legal_profile WHERE legal_user_id = %s", (user_id,))
        lr = cur.fetchone()
        if lr:
            legal = {
                "legal_name": _decrypt_text(lr[0]) if lr[0] else "",
                "phone_number": _decrypt_text(lr[1]) if lr[1] else "",
                "email": _decrypt_text(lr[2]) if lr[2] else "",
                "office_address": _decrypt_text(lr[3]) if lr[3] else "",
            }
        else:
            legal = {"legal_name": "", "phone_number": "", "email": "", "office_address": ""}
    finally:
        cur.close()
        conn.close()

    message = session.pop('profile_message', None)
    return render_template(
        'profile.html',
        role=role,
        projects=projects,
        developer_companies=projects,
        state_court_map=STATE_COURT_MAP,
        state_options=list(STATE_COURT_MAP.keys()),
        item_service_options=list(ITEM_SERVICE_TRANSLATIONS.keys()),
        user_info=user_info,
        account=account,
        personal=personal,
        homeowner=homeowner,
        respondent=respondent,
        legal=legal,
        message=message
    )


@routes.route('/defect-entry', methods=['GET', 'POST'])
@login_required
def defect_entry():
    if _current_role() != "Homeowner":
        return redirect(url_for("routes.dashboard"))

    user_id = _current_user_id()
    user_info = get_current_user()

    default_unit = (user_info.get("unit") or "") if isinstance(user_info, dict) else ""
    form_values = {
        "unit": default_unit,
        "description": "",
        "urgency": "Medium",
        "reported_date": "",
        "deadline": "",
        "remarks": "",
    }

    if request.method == 'POST':
        form_values = {
            "unit": (request.form.get('unit') or '').strip(),
            "description": (request.form.get('description') or '').strip(),
            "urgency": (request.form.get('urgency') or 'Medium').strip() or 'Medium',
            "reported_date": (request.form.get('reported_date') or '').strip(),
            "deadline": (request.form.get('deadline') or '').strip(),
            "remarks": (request.form.get('remarks') or '').strip(),
        }

        # Validate required fields
        if not form_values["unit"]:
            return render_template(
                'defect_entry.html',
                error=None,
                message=None,
                form_values=form_values,
                field_errors={"unit": "Unit/Location is required."},
            )
        
        if not form_values["description"]:
            return render_template(
                'defect_entry.html',
                error=None,
                message=None,
                form_values=form_values,
                field_errors={"description": "Defect Description is required."},
            )
        
        if len(form_values["description"]) < 10:
            return render_template(
                'defect_entry.html',
                error=None,
                message=None,
                form_values=form_values,
                field_errors={"description": "Description must be at least 10 characters."},
            )

        if not form_values["reported_date"]:
            return render_template(
                'defect_entry.html',
                error=None,
                message=None,
                form_values=form_values,
                field_errors={"reported_date": "Reported Date is required."},
            )

        if form_values["urgency"] not in {"Low", "Medium", "High"}:
            form_values["urgency"] = "Medium"

        # Parse and validate reported_date
        try:
            reported_date = datetime.strptime(
                form_values["reported_date"],
                "%Y-%m-%d"
            ).date()
            today = _now_app_timezone().date()

            if reported_date > today:
                return render_template(
                    'defect_entry.html',
                    error=None,
                    message=None,
                    form_values=form_values,
                    field_errors={"reported_date": "Reported Date cannot be in the future."},
                )
        except ValueError:
            return render_template(
                'defect_entry.html',
                error=None,
                message=None,
                form_values=form_values,
                field_errors={"reported_date": "Invalid reported date format."},
            )

        if not form_values["deadline"]:
            return render_template(
                'defect_entry.html',
                error=None,
                message=None,
                form_values=form_values,
                field_errors={"deadline": "Target Completion Date is required."},
            )

        try:
            deadline_value = datetime.strptime(
                form_values["deadline"],
                "%Y-%m-%d"
            ).date()
        except ValueError:
            return render_template(
                'defect_entry.html',
                error=None,
                message=None,
                form_values=form_values,
                field_errors={"deadline": "Invalid target completion date format."},
            )

        deadline_month_index = reported_date.month - 1 + 6
        deadline_year = reported_date.year + (deadline_month_index // 12)
        deadline_month = (deadline_month_index % 12) + 1
        deadline_day = min(
            reported_date.day,
            calendar.monthrange(deadline_year, deadline_month)[1]
        )
        minimum_deadline = reported_date.replace(
            year=deadline_year,
            month=deadline_month,
            day=deadline_day,
        )

        if deadline_value < minimum_deadline:
            return render_template(
                'defect_entry.html',
                error=None,
                message=None,
                form_values=form_values,
                field_errors={"deadline": "Target Completion Date must be at least 6 months after Reported Date."},
            )

        evidence_files = [
            file for file in request.files.getlist('evidence')
            if file and file.filename
        ]
        if len(evidence_files) != REQUIRED_EVIDENCE_IMAGE_COUNT:
            return render_template(
                'defect_entry.html',
                error=None,
                message=None,
                form_values=form_values,
                field_errors={"evidence": f"Exactly {REQUIRED_EVIDENCE_IMAGE_COUNT} supporting evidence images are required."},
            )

        for evidence_file in evidence_files:
            if not allowed_file(evidence_file.filename):
                return render_template(
                    'defect_entry.html',
                    error=None,
                    message=None,
                    form_values=form_values,
                    field_errors={"evidence": "Invalid file type. Please upload JPG, JFIF, PNG, or TIF."},
                )

        # Insert defect into database
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO defects (
                    unit,
                    description,
                    reported_date,
                    status,
                    completed_date,
                    user_id,
                    urgency,
                    deadline,
                    remarks,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                (
                    _encrypt_text(form_values["unit"]),
                    _encrypt_text(form_values["description"]),
                    reported_date,
                    "Pending",
                    user_id,
                    form_values["urgency"],
                    deadline_value,
                    _encrypt_text(form_values["remarks"]) if form_values["remarks"] else None,
                )
            )
            new_defect_id = cur.fetchone()[0]

            # Keep user profile unit aligned with newly submitted defect unit
            if form_values["unit"]:
                cur.execute(
                    "UPDATE users SET unit = %s WHERE id = %s",
                    (_encrypt_text(form_values["unit"]), user_id),
                )

            # Save remark to remarks table if provided
            if form_values["remarks"]:
                cur.execute(
                    """
                    INSERT INTO remarks (defect_id, role, remark, created_at)
                    VALUES (%s, %s, %s, NOW())
                    """,
                    (new_defect_id, "Homeowner", _encrypt_text(form_values["remarks"]))
                )

            conn.commit()
        except Exception as e:
            conn.rollback()
            return render_template(
                'defect_entry.html',
                error=f'Error saving defect: {str(e)}',
                message=None,
                form_values=form_values,
            )
        finally:
            cur.close()
            conn.close()

        # Handle evidence file uploads if provided
        try:
            # Create evidence directory if not exists
            evidence_dir = os.path.join(current_app.root_path, "evidence")
            os.makedirs(evidence_dir, exist_ok=True)

            # Save evidence metadata
            now_local = _now_app_timezone()
            uploaded_at = now_local.strftime("%Y-%m-%d %H:%M:%S")
            evidence_items = []

            for index, file in enumerate(evidence_files, 1):
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = f"defect_{new_defect_id}_{index}.{ext}"
                filepath = os.path.join(evidence_dir, filename)
                file.save(filepath)
                evidence_items.append({
                    "filename": filename,
                    "uploaded_at": uploaded_at,
                })

            evidence_store = load_evidence()
            evidence_store[str(new_defect_id)] = {
                "files": evidence_items,
                "filename": evidence_items[0]["filename"],
                "uploaded_at": uploaded_at,
            }
            save_evidence(evidence_store)

            _append_audit_event(
                action="Evidence Uploaded",
                role="Homeowner",
                defect_id=str(new_defect_id),
                filename=", ".join(item["filename"] for item in evidence_items),
                details={
                    "username": session.get("username", ""),
                    "defect_id": new_defect_id,
                    "filenames": [item["filename"] for item in evidence_items],
                    "uploaded_at": uploaded_at,
                },
            )
        except Exception as e:
            # Log error but don't fail the submission
            _append_audit_event(
                action="Evidence Upload Failed",
                role="Homeowner",
                defect_id=str(new_defect_id),
                details={
                    "error": str(e),
                },
            )

        # Audit event for defect creation
        _append_audit_event(
            action="Defect Created",
            role="Homeowner",
            defect_id=str(new_defect_id),
            details={
                "unit": form_values["unit"],
                "urgency": form_values["urgency"],
                "reported_date": form_values["reported_date"],
                "has_remark": bool(form_values["remarks"]),
                "has_evidence": len(evidence_files) == REQUIRED_EVIDENCE_IMAGE_COUNT,
            },
        )

        # Render success directly so submitted values remain visible without session-size limits.
        submitted_at = _now_app_timezone().strftime("%d/%m/%y %H:%M:%S")
        message = f"Defect submitted successfully on {submitted_at}. It will now appear in your dashboard."
        return render_template(
            'defect_entry.html',
            error=None,
            message=message,
            submitted_at=submitted_at,
            form_values=form_values,
            last_evidence_name=", ".join(file.filename for file in evidence_files),
            defect_message=session.pop('defect_message', None),
        )

    submitted_at = request.args.get('submitted_at')
    message = None
    restored_submitted_form = False
    if request.args.get('success') == '1':
        # If we have stored the last submitted form in session, restore it so the user sees their inputs
        last_form = session.pop('last_defect_form', None)
        if last_form:
            # Restore user inputs exactly as submitted.
            form_values = last_form
            restored_submitted_form = True

        # Format submitted_at to dd/mm/yy for display if present
        if submitted_at:
            try:
                dt = datetime.strptime(submitted_at, "%Y-%m-%d %H:%M:%S")
                submitted_at = dt.strftime("%d/%m/%y %H:%M:%S")
            except Exception:
                # Leave as-is if parsing fails
                pass
            message = f"Defect submitted successfully on {submitted_at}. It will now appear in your dashboard."
        else:
            message = "Defect submitted successfully! It will now appear in your dashboard."

    # Keep the default urgency blank on fresh renders only.
    if request.method == 'GET' and not restored_submitted_form:
        form_values['urgency'] = ''

    return render_template(
        'defect_entry.html',
        error=None,
        message=message,
        submitted_at=submitted_at,
        form_values=form_values,
        last_evidence_name='',
        defect_message=session.pop('defect_message', None),
    )

@routes.route('/profile/update/<section>', methods=['POST'])
@login_required
def profile_update(section):
    role = _current_role()
    user_id = _current_user_id()
    conn = get_connection()
    cur = conn.cursor()
    message = None
    try:
        if section == 'account':
            username = (request.form.get('username') or '').strip()
            password = request.form.get('password') or ''
            confirm = request.form.get('confirm_password') or ''

            cur.execute(
                "SELECT username FROM login_accounts WHERE user_id = %s LIMIT 1",
                (user_id,)
            )
            account_row = cur.fetchone()
            current_username = account_row[0] if account_row and account_row[0] else session.get('username', '')

            if username and current_username and username != current_username:
                session['profile_message'] = 'Username cannot be changed.'
                return redirect(url_for('routes.profile'))

            if password and password != confirm:
                session['profile_message'] = 'Passwords do not match.'
                return redirect(
                    url_for('routes.profile')
                )
            if password:
                password_pattern = re.compile(
                    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])"
                )
                if (
                    len(password) < 8
                    or not password_pattern.search(password)
                ):
                    session['profile_message'] = 'Password must contain uppercase, lowercase, number and special character.'
                    return redirect(
                        url_for('routes.profile')
                    )
            if password:
                cur.execute("UPDATE login_accounts SET password = %s WHERE user_id = %s", (generate_password_hash(password), user_id))
            conn.commit()
            session['username'] = current_username
            message = 'Account updated.'

        elif section == 'personal':
            full_name = (request.form.get('full_name') or '').strip()
            email = (request.form.get('email') or '').strip()
            unit = (request.form.get('unit') or '').strip()

            # Defensive: some DBs may still have legacy small VARCHAR limits.
            # Prefer running the DB migration `database/upgrade_encryption_columns.sql`.
            # Truncate plaintext to a safe limit (200 chars) so encrypted Fernet tokens
            # do not become excessively large in legacy schemas.
            MAX_PLAINTEXT_LEN = 200
            full_name = full_name[:MAX_PLAINTEXT_LEN] if full_name else full_name
            email = email[:MAX_PLAINTEXT_LEN] if email else email
            unit = unit[:MAX_PLAINTEXT_LEN] if unit else unit

            if role == 'Legal':
                cur.execute(
                    "SELECT unit FROM users WHERE id = %s LIMIT 1",
                    (user_id,)
                )
                existing_row = cur.fetchone()
                if existing_row:
                    unit = _decrypt_text(existing_row[0]) or ''

            # CHECK EMAIL DUPLICATE
            if email:
                cur.execute(
                    """
                    SELECT id, email
                    FROM users
                    WHERE id != %s
                    AND email IS NOT NULL
                    """,
                    (user_id,)
                )
                email_normalized = (
                    email.strip().lower()
                )
                for row in cur.fetchall():
                    stored_email = (
                        (_decrypt_text(row[1]) or '')
                        .strip()
                        .lower()
                    )
                    if stored_email == email_normalized:
                        session['profile_message'] = 'Email already exists.'
                        return redirect(
                            url_for('routes.profile')
                        )

            cur.execute(
                "UPDATE users SET full_name = %s, email = %s, unit = %s WHERE id = %s",
                (
                    _encrypt_text(full_name),
                    _encrypt_text(email),
                    _encrypt_text(unit),
                    user_id,
                ),
            )

            if role == "Homeowner":
                # Keep homeowner profile email aligned with personal email.
                cur.execute(
                    """
                    UPDATE report_homeowner_profile
                    SET email = %s,
                        updated_at = NOW()
                    WHERE homeowner_id = %s
                    """,
                    (
                        _encrypt_text(email),
                        user_id,
                    ),
                )

            if role == "Legal":
                cur.execute(
                    """
                    INSERT INTO report_legal_profile
                    (
                        legal_user_id,
                        legal_name,
                        email,
                        updated_at
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        NOW()
                    )
                    ON CONFLICT (legal_user_id)
                    DO UPDATE SET
                        legal_name = EXCLUDED.legal_name,
                        email = EXCLUDED.email,
                        updated_at = NOW()
                    """,
                    (
                        user_id,
                        _encrypt_text(full_name),
                        _encrypt_text(email),
                    ),
                )

            conn.commit()
            message = 'Personal details updated.'


        elif section == 'homeowner':
            if role != "Homeowner":
                session['profile_message'] = 'You are not allowed to edit homeowner details.'
                return redirect(url_for('routes.profile'))

            name = (request.form.get('name') or '').strip()
            phone = (request.form.get('phone_number') or '').strip()
            ic_number = (request.form.get('ic_number') or '').strip()

            # CHECK PHONE DUPLICATE
            if phone:

                cur.execute(
                    """
                    SELECT homeowner_id, phone_number
                    FROM report_homeowner_profile
                    WHERE homeowner_id != %s
                    AND phone_number IS NOT NULL
                    """,
                    (user_id,)
                )

                for row in cur.fetchall():

                    stored_phone = (
                        (_decrypt_text(row[1]) or '')
                        .strip()
                    )

                    if stored_phone == phone:

                        return redirect(
                            url_for('routes.profile')
                        )

            # CHECK IC DUPLICATE
            if ic_number:

                cur.execute(
                    """
                    SELECT homeowner_id, ic_number
                    FROM report_homeowner_profile
                    WHERE homeowner_id != %s
                    AND ic_number IS NOT NULL
                    """,
                    (user_id,)
                )

                for row in cur.fetchall():

                    stored_ic = (
                        (_decrypt_text(row[1]) or '')
                        .strip()
                    )

                    if stored_ic == ic_number:

                        return redirect(
                            url_for('routes.profile')
                        )

            address = (request.form.get('address') or '').strip()
            court = (request.form.get('court_location') or '').strip()
            defect_unit = (request.form.get('defect_unit') or '').strip()
            project_name = (request.form.get('project_name') or '').strip()
            defect_state = (request.form.get('defect_state') or '').strip()
            defect_property_address = (request.form.get('defect_property_address') or '').strip()

            cur.execute(
                "SELECT email FROM users WHERE id = %s",
                (user_id,),
            )
            user_email_row = cur.fetchone()
            homeowner_email = user_email_row[0] if user_email_row and user_email_row[0] else None

            cur.execute(
                """
                INSERT INTO report_homeowner_profile
                (
                    homeowner_id,
                    name,
                    email,
                    phone_number,
                    ic_number,
                    address,
                    court_location,
                    state_name,
                    item_service,
                    transaction_date,
                    claim_amount,
                    defect_unit,
                    project_name,
                    defect_state,
                    defect_property_address,
                    updated_at
                )

                VALUES
                (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    NOW()
                )

                ON CONFLICT (homeowner_id)
                DO UPDATE SET

                    name = EXCLUDED.name,
                    email = EXCLUDED.email,
                    phone_number = EXCLUDED.phone_number,
                    ic_number = EXCLUDED.ic_number,
                    address = EXCLUDED.address,
                    court_location = EXCLUDED.court_location,
                    state_name = EXCLUDED.state_name,
                    item_service = EXCLUDED.item_service,
                    transaction_date = EXCLUDED.transaction_date,
                    claim_amount = EXCLUDED.claim_amount,
                    defect_unit = EXCLUDED.defect_unit,
                    project_name = EXCLUDED.project_name,
                    defect_state = EXCLUDED.defect_state,
                    defect_property_address = EXCLUDED.defect_property_address,
                    updated_at = NOW()
                """,
                (
                    user_id,

                    _encrypt_text(name),
                    homeowner_email,
                    _encrypt_text(phone),
                    _encrypt_text(ic_number),
                    _encrypt_text(address),
                    _encrypt_text(court),

                    _encrypt_text(request.form.get('state_name')),
                    _encrypt_text(request.form.get('item_service')),
                    _encrypt_text(request.form.get('transaction_date')),
                    _encrypt_text(request.form.get('claim_amount')),

                    _encrypt_text(defect_unit),
                    _encrypt_text(project_name),
                    _encrypt_text(defect_state),
                    _encrypt_text(defect_property_address),
                )
            )
            conn.commit()
        
            # sync defect unit to user profile unit
            if defect_unit:
                cur.execute(
                    """
                    UPDATE users
                    SET unit = %s
                    WHERE id = %s
                    """,
                    (
                        _encrypt_text(defect_unit),
                        user_id
                    )
                )
                conn.commit()
            
            if project_name:
                cur.execute(
                    """
                    SELECT
                        d.company_name,
                        dc.person_in_charge,
                        d.registration_number,
                        dc.phone_number,
                        dc.email,
                        dc.office_address
                    FROM developer_projects dp
                    JOIN developers d
                        ON dp.developer_id = d.id
                    LEFT JOIN developer_contacts dc
                        ON dc.developer_id = d.id
                       AND dc.state_name = dp.state_name
                    WHERE dp.project_name = %s
                    LIMIT 1
                    """,
                    (project_name,)
                )
                project_row = cur.fetchone()

                if project_row:
                    cur.execute(
                        """
                        INSERT INTO report_respondent_profile
                        (
                            respondent_id,
                            company_name,
                            person_in_charge,
                            registration_number,
                            phone_number,
                            email,
                            address,
                            updated_at
                        )

                        VALUES
                        (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            NOW()
                        )

                        ON CONFLICT (respondent_id)

                        DO UPDATE SET

                            company_name = EXCLUDED.company_name,
                            person_in_charge = EXCLUDED.person_in_charge,
                            registration_number = EXCLUDED.registration_number,
                            phone_number = EXCLUDED.phone_number,
                            email = EXCLUDED.email,
                            address = EXCLUDED.address,
                            updated_at = NOW()
                        """,
                        (
                            user_id,
                            _encrypt_text(project_row[0]),
                            _encrypt_text(project_row[1]),
                            _encrypt_text(project_row[2]),
                            _encrypt_text(project_row[3]),
                            _encrypt_text(project_row[4]),
                            _encrypt_text(project_row[5]),
                        )
                    )
                    conn.commit()
            
            message = 'Homeowner profile updated.'
        elif section == 'respondent':

            company = (request.form.get('company_name') or '').strip()
            pic = (request.form.get('person_in_charge') or '').strip()
            reg = (request.form.get('registration_number') or '').strip()
            phone = (request.form.get('phone_number') or '').strip()
            email = (request.form.get('email') or '').strip()
            address = (request.form.get('address') or '').strip()

            cur.execute(
                """
                INSERT INTO report_respondent_profile
                (
                    respondent_id,
                    company_name,
                    person_in_charge,
                    registration_number,
                    phone_number,
                    email,
                    address,
                    updated_at
                )

                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW()
                )

                ON CONFLICT (respondent_id)

                DO UPDATE SET

                    company_name = EXCLUDED.company_name,
                    person_in_charge = EXCLUDED.person_in_charge,
                    registration_number = EXCLUDED.registration_number,
                    phone_number = EXCLUDED.phone_number,
                    email = EXCLUDED.email,
                    address = EXCLUDED.address,
                    updated_at = NOW()
                """,

                (
                    user_id,
                    _encrypt_text(company),
                    _encrypt_text(pic),
                    _encrypt_text(reg),
                    _encrypt_text(phone),
                    _encrypt_text(email),
                    _encrypt_text(address)
                )
            )

            conn.commit()
            message = 'Respondent profile updated.'
        
        elif section == 'legal':

            if role != "Legal":
                return redirect(url_for('routes.profile'))

            legal_name = (
                request.form.get('legal_name') or ''
            ).strip()

            phone = (
                request.form.get('phone_number') or ''
            ).strip()

            email = (
                request.form.get('email') or ''
            ).strip()

            office_address = (
                request.form.get('office_address') or ''
            ).strip()

            # =========================================
            # CHECK PHONE DUPLICATE
            # =========================================
            if phone:

                cur.execute(
                    """
                    SELECT legal_user_id, phone_number
                    FROM report_legal_profile
                    WHERE legal_user_id != %s
                    AND phone_number IS NOT NULL
                    """,
                    (user_id,)
                )

                for row in cur.fetchall():

                    stored_phone = (
                        (_decrypt_text(row[1]) or '')
                        .strip()
                    )

                    if stored_phone == phone:

                        session['profile_message'] = (
                            'Phone number already exists.'
                        )

                        return redirect(
                            url_for('routes.profile')
                        )

            # =========================================
            # CHECK EMAIL DUPLICATE
            # =========================================
            if email:

                cur.execute(
                    """
                    SELECT legal_user_id, email
                    FROM report_legal_profile
                    WHERE legal_user_id != %s
                    AND email IS NOT NULL
                    """,
                    (user_id,)
                )

                for row in cur.fetchall():

                    stored_email = (
                        (_decrypt_text(row[1]) or '')
                        .strip()
                        .lower()
                    )

                    if stored_email == email.lower():

                        session['profile_message'] = (
                            'Email already exists.'
                        )

                        return redirect(
                            url_for('routes.profile')
                        )

            # =========================================
            # INSERT / UPDATE LEGAL PROFILE
            # =========================================
            cur.execute(
                """
                INSERT INTO report_legal_profile
                (
                    legal_user_id,
                    legal_name,
                    phone_number,
                    email,
                    office_address,
                    updated_at
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW()
                )
                ON CONFLICT (legal_user_id)
                DO UPDATE SET
                    legal_name = EXCLUDED.legal_name,
                    phone_number = EXCLUDED.phone_number,
                    email = EXCLUDED.email,
                    office_address = EXCLUDED.office_address,
                    updated_at = NOW()
                """,
                (
                    user_id,
                    _encrypt_text(legal_name),
                    _encrypt_text(phone),
                    _encrypt_text(email),
                    _encrypt_text(office_address)
                )
            )

            # =========================================
            # SYNC USERS TABLE
            # =========================================
            cur.execute(
                """
                UPDATE users
                SET
                    full_name = %s,
                    email = %s
                WHERE id = %s
                """,
                (
                    _encrypt_text(legal_name),
                    _encrypt_text(email),
                    user_id
                )
            )

            # =========================================
            # OPTIONAL:
            # SYNC OTHER TABLES
            # =========================================
            # Example:
            #
            # cur.execute(
            #     """
            #     UPDATE tribunal_reports
            #     SET
            #         legal_name = %s,
            #         legal_phone = %s,
            #         legal_email = %s,
            #         legal_address = %s
            #     WHERE legal_user_id = %s
            #     """,
            #     (
            #         _encrypt_text(legal_name),
            #         _encrypt_text(phone),
            #         _encrypt_text(email),
            #         _encrypt_text(office_address),
            #         user_id
            #     )
            # )

            conn.commit()
            message = 'Legal profile updated successfully.'
    finally:
        cur.close()
        conn.close()

    session['profile_message'] = message
    return redirect(url_for('routes.profile'))


# Avatar upload handling
ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.jfif'}
MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2MB


def _allowed_image(filename):
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


@routes.route('/profile/upload-avatar', methods=['POST'])
@login_required
def upload_avatar():
    if _current_role() == "Admin":
        return redirect(url_for("routes.dashboard"))

    user_id = _current_user_id()
    if 'avatar' not in request.files:
        session['profile_message'] = 'No file uploaded.'
        return redirect(url_for('routes.profile'))

    f = request.files['avatar']
    if f.filename == '':
        session['profile_message'] = 'No file selected.'
        return redirect(url_for('routes.profile'))

    if not _allowed_image(f.filename):
        session['profile_message'] = 'Unsupported file type.'
        return redirect(url_for('routes.profile'))

    f.stream.seek(0, os.SEEK_END)
    size = f.stream.tell()
    f.stream.seek(0)
    if size > MAX_AVATAR_BYTES:
        session['profile_message'] = 'File too large (limit 2MB).'
        return redirect(url_for('routes.profile'))

    uploads_dir = os.path.join(
        current_app.root_path,
        'static',
        'uploads',
        'avatars'
    )
    os.makedirs(uploads_dir, exist_ok=True)

    # Save and resize using Pillow if available; otherwise save raw file
    try:
        if Image is None:
            raise RuntimeError('Pillow not available')

        img = Image.open(f.stream)
        img = img.convert('RGB')  # Normalize to RGB
        # Normalize avatar size
        avatar_size = (256, 256)
        img.thumbnail(avatar_size, Image.LANCZOS)

        out_name = f'user_{user_id}.png'
        out_path = os.path.join(uploads_dir, out_name)
        img.save(out_path, format='PNG')

        # create thumbnail
        thumb = img.copy()
        thumb.thumbnail((64, 64), Image.LANCZOS)
        thumb_name = f'user_{user_id}_thumb.png'
        thumb.save(os.path.join(uploads_dir, thumb_name), format='PNG')

        avatar_url = url_for('static', filename=f'uploads/avatars/{out_name}')
    except UnidentifiedImageError:
        session['profile_message'] = 'Uploaded file is not a valid image.'
        return redirect(url_for('routes.profile'))
    except Exception:
        # Fallback: save raw
        filename = secure_filename(f.filename)
        ext = os.path.splitext(filename)[1].lower() or '.png'
        out_name = f'user_{user_id}{ext}'
        out_path = os.path.join(uploads_dir, out_name)
        f.save(out_path)
        avatar_url = url_for('static', filename=f'uploads/avatars/{out_name}')

    avatar_url = f"{avatar_url}?v={int(datetime.now(timezone.utc).timestamp())}"

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('UPDATE users SET avatar_url = %s WHERE id = %s', (avatar_url, user_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    session['profile_message'] = 'Avatar uploaded.'
    return redirect(url_for('routes.profile'))


@routes.route("/logout")
def logout():
    _append_audit_event(
        action="Logout",
        role=_current_role(),
        details={
            "username": session.get("username", ""),
        },
    )
    session.clear()
    session['auth_error'] = 'You have been logged out successfully.'
    return redirect(url_for("routes.login"))


# --------------------------------
# DATABASE HELPERS
# --------------------------------

def _to_iso(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _format_profile_datetime(value):
    if not value:
        return None

    parsed = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text

    if not hasattr(parsed, "strftime"):
        return str(parsed)

    try:
        app_tz = ZoneInfo(APP_TIMEZONE)
    except Exception:
        app_tz = timezone(timedelta(hours=8)) if APP_TIMEZONE == "Asia/Kuala_Lumpur" else None

    if app_tz:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=app_tz)
        else:
            parsed = parsed.astimezone(app_tz)

    hour = parsed.strftime("%I").lstrip("0") or "12"
    return f"{parsed.strftime('%d %b %Y')}, {hour}:{parsed.strftime('%M %p')}"


def _get_login_activity_for_username(cur, username):
    username = (username or "").strip()
    if not username:
        return None, []

    cur.execute(
        """
        SELECT timestamp, action, details
        FROM audit_log
        WHERE LOWER(details->>'username') = LOWER(%s)
        ORDER BY timestamp DESC
        LIMIT 5
        """,
        (username,),
    )
    user_activity = [
        {
            "timestamp": _format_profile_datetime(row[0]),
            "action": row[1],
            "details": row[2],
        }
        for row in (cur.fetchall() or [])
    ]

    cur.execute(
        """
        SELECT timestamp
        FROM audit_log
        WHERE LOWER(details->>'username') = LOWER(%s)
          AND action = 'Login Succeeded'
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (username,),
    )
    last_row = cur.fetchone()
    last_login = _format_profile_datetime(last_row[0]) if last_row and last_row[0] else None
    return last_login, user_activity


@lru_cache(maxsize=1)
def _users_avatar_url_column_ready():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'users'
              AND column_name = 'avatar_url'
            LIMIT 1
            """
        )
        if cur.fetchone():
            return True

        try:
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(512)")
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False
    finally:
        cur.close()
        conn.close()

def get_current_user():
    conn = get_connection()
    cur = conn.cursor()
    try:
        user_id = _current_user_id()
        session_username = (session.get("username") or "").strip()
        session_role = (session.get("role") or "").strip()
        cur.execute(
            "SELECT id, full_name, unit, role FROM users WHERE id = %s",
            (user_id,)
        )
        row = cur.fetchone()
        if not row:
            last_login, user_activity = _get_login_activity_for_username(cur, session_username)
            return {
                "name": session_username or session_role or "User",
                "unit": "",
                "role": session_role,
                "last_login": last_login,
                "username": session_username,
                "activity": user_activity,
            }

        display_name = _decrypt_display_text(row[1]) or "User"
        # basic user fields
        user_role = row[3]
        if session_role == "Admin":
            display_name = session_username or "Admin"
            user_role = "Admin"
        # email if present
        cur.execute("SELECT email FROM users WHERE id = %s", (user_id,))
        email_row = cur.fetchone()
        email_val = email_row[0] if email_row and email_row[0] else None
        company_name = None
        registration_number = None
        person_in_charge = None
        phone_number = None
        office_address = None
        contact_state = None

        if user_role == "Homeowner":
            cur.execute(
                "SELECT name FROM report_homeowner_profile WHERE homeowner_id = %s",
                (user_id,),
            )
            homeowner_profile = cur.fetchone()
            if homeowner_profile and homeowner_profile[0]:
                display_name = _decrypt_display_text(homeowner_profile[0]) or display_name
        elif user_role == "Legal":
            cur.execute(
                """
                SELECT legal_name, email, office_address
                FROM report_legal_profile
                WHERE legal_user_id = %s
                """,
                (user_id,),
            )
            legal_profile = cur.fetchone()
            if legal_profile and legal_profile[0]:
                display_name = _decrypt_display_text(legal_profile[0]) or display_name
                company_name = display_name
                if legal_profile[1]:
                    email_val = _decrypt_display_text(legal_profile[1]) or email_val
        elif user_role in {"Developer", "Admin"}:
            login_username = (session.get("username") or "").strip().lower()

            if user_role == "Developer":
                cur.execute(
                    """
                    SELECT company_name, person_in_charge, registration_number, phone_number, email, address
                    FROM report_respondent_profile
                    WHERE respondent_id = %s
                    """,
                    (user_id,),
                )
                respondent_profile = cur.fetchone()
                if respondent_profile and respondent_profile[0]:
                    company_name = _decrypt_display_text(respondent_profile[0]) or display_name
                    display_name = company_name or display_name
                    person_in_charge = _decrypt_display_text(respondent_profile[1]) or None
                    phone_number = _decrypt_display_text(respondent_profile[3]) or None
                    if respondent_profile[4]:
                        email_val = _decrypt_display_text(respondent_profile[4]) or email_val
                    office_address = _decrypt_display_text(respondent_profile[5]) or None

                developer_id = None
                lookup_name = company_name or display_name
                if lookup_name:
                    cur.execute(
                        """
                        SELECT id, company_name, registration_number
                        FROM developers
                        WHERE LOWER(company_name) = LOWER(%s)
                        LIMIT 1
                        """,
                        (lookup_name,),
                    )
                    developer_row = cur.fetchone()
                    if developer_row and developer_row[0]:
                        developer_id = developer_row[0]
                        company_name = _decrypt_display_text(developer_row[1]) or company_name
                        display_name = company_name or display_name
                        registration_number = _decrypt_display_text(developer_row[2]) or registration_number
                if not developer_id:
                    cur.execute("SELECT id, company_name, registration_number FROM developers ORDER BY id ASC LIMIT 1")
                    developer_row = cur.fetchone()
                    if developer_row and developer_row[0]:
                        developer_id = developer_row[0]
                        company_name = _decrypt_display_text(developer_row[1]) or company_name
                        display_name = company_name or display_name
                        registration_number = _decrypt_display_text(developer_row[2]) or registration_number

                if is_main_developer_account(user_id, login_username):
                    person_in_charge = None
                elif developer_id:
                    cur.execute(
                        """
                        SELECT state_name, person_in_charge, phone_number, email, office_address
                        FROM developer_contacts
                        WHERE developer_id = %s
                        ORDER BY CASE WHEN LOWER(state_name) = 'pulau pinang' THEN 0 ELSE 1 END, state_name ASC
                        LIMIT 1
                        """,
                        (developer_id,),
                    )
                    contact_row = cur.fetchone()
                    if contact_row:
                        contact_state = _decrypt_display_text(contact_row[0]) or None
                        person_in_charge = _decrypt_display_text(contact_row[1]) or person_in_charge
                        phone_number = _decrypt_display_text(contact_row[2]) or phone_number
                        if contact_row[3]:
                            email_val = _decrypt_display_text(contact_row[3]) or email_val
                        office_address = _decrypt_display_text(contact_row[4]) or office_address

        unit_value = _decrypt_display_text(row[2]) or ""
        if session_role == "Admin":
            unit_value = ""
            email_val = None

        # include avatar_url if stored on users table
        cur.execute("SELECT avatar_url FROM users WHERE id = %s", (user_id,))
        avatar_row = cur.fetchone()
        avatar_url = avatar_row[0] if avatar_row and avatar_row[0] else None

        # Prefer the active session username so Admin does not inherit the
        # simulated fallback user's login history.
        username = session_username or None
        try:
            if not username:
                cur.execute("SELECT username FROM login_accounts WHERE user_id = %s LIMIT 1", (user_id,))
                uname_row = cur.fetchone()
                username = uname_row[0] if uname_row and uname_row[0] else None
        except Exception:
            username = None

        # last successful login time (if available) and recent activity (optional)
        last_login = None
        user_activity = []
        try:
            if username:
                last_login, user_activity = _get_login_activity_for_username(cur, username)
        except Exception:
            last_login = None

        return {
            "name": display_name,
            "company_name": company_name,
            "person_in_charge": person_in_charge,
            "phone_number": phone_number,
            "office_address": office_address,
            "contact_state": contact_state,
            "unit": unit_value,
            "avatar_url": avatar_url,
            "email": email_val,
            "role": user_role,
            "last_login": last_login,
            "username": username,
            "activity": user_activity,
        }
    finally:
        cur.close()
        conn.close()


def _get_user_unit(user_id):
    if not user_id:
        return ""

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT unit FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return _decrypt_display_text(row[0]) or ""
    finally:
        cur.close()
        conn.close()


def _normalise_unit_for_grouping(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""

    unit_match = re.search(r"\b[a-z]{1,4}-\d{1,4}(?:-\d{1,4})?\b", text, flags=re.IGNORECASE)
    if unit_match:
        return unit_match.group(0).strip().lower()

    return text


def _units_match_for_closed_appendix(left_value, right_value):
    left_unit = _normalise_unit_for_grouping(left_value)
    right_unit = _normalise_unit_for_grouping(right_value)
    return bool(left_unit and right_unit and left_unit == right_unit)
    right_compact = re.sub(r"[^a-z0-9]", "", str(right_value or "").lower())
    return bool(left_compact and right_compact and (left_compact in right_compact or right_compact in left_compact))


def get_homeowner_claim_details(user_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT court_location, state_name, item_service, transaction_date, claim_amount
            FROM report_homeowner_profile
            WHERE homeowner_id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return {
                "court_location": "",
                "state_name": "",
                "item_service": _default_item_service(),
                "transaction_date": "",
                "claim_amount": "",
            }
        return {
            "court_location": decrypt_text(row[0]) or "",
            "state_name": decrypt_text(row[1]) or "",
            "item_service": _normalise_item_service(decrypt_text(row[2]) or _default_item_service()),
            "transaction_date": decrypt_text(row[3]) or "",
            "claim_amount": decrypt_text(row[4]) or "",
        }
    finally:
        cur.close()
        conn.close()


def calculate_hda_compliance(reported_date, completed_date, status):
    if not reported_date:
        return True

    try:
        reported_date_obj = datetime.strptime(str(reported_date), "%Y-%m-%d")
    except Exception:
        return True

    if status not in {"Completed", "Closed", "Archived"} or not completed_date:
        return False

    try:
        completed_date_obj = datetime.strptime(str(completed_date), "%Y-%m-%d")
    except Exception:
        return False

    days_taken = (completed_date_obj - reported_date_obj).days
    return days_taken <= 30


def calculate_overdue(deadline, completed_date, status):
    if not deadline:
        return False

    try:
        deadline_date = datetime.strptime(str(deadline), "%Y-%m-%d")
    except Exception:
        return False

    if status in {"Completed", "Closed", "Archived"} and completed_date:
        try:
            completed_date_obj = datetime.strptime(str(completed_date), "%Y-%m-%d")
            return completed_date_obj > deadline_date
        except Exception:
            return False

    if status not in {"Completed", "Closed", "Archived"}:
        return _now_app_timezone().date() > deadline_date.date()

    return False


def calculate_days_to_complete(reported_date, completed_date):
    if not reported_date or not completed_date:
        return None

    try:
        reported_date_obj = datetime.strptime(str(reported_date)[:10], "%Y-%m-%d").date()
        completed_date_obj = datetime.strptime(str(completed_date)[:10], "%Y-%m-%d").date()
    except Exception:
        return None

    return max((completed_date_obj - reported_date_obj).days, 0)


def is_auto_closed(status, completed_date):
    if status in {"Closed", "Archived"}:
        return True

    if status != "Completed" or not completed_date:
        return False

    try:
        completed_dt = datetime.strptime(str(completed_date)[:10], "%Y-%m-%d").date()
    except Exception:
        return False

    cutoff = _now_app_timezone().date() - timedelta(days=AUTO_CLOSE_DAYS)
    return completed_dt <= cutoff


def calculate_stats(defects):
    def _status_value(defect):
        return str(defect.get("status", "")).strip().lower()

    def _is_closed(defect):
        return defect.get("closed") or _status_value(defect) in {
            "closed",
            "ditutup",
            "archived",
            "diarkib",
        }

    def _is_completed(defect):
        return not _is_closed(defect) and _status_value(defect) in {
            "completed",
            "telah diselesaikan",
            "telah selesai",
            "selesai",
        }

    def _is_pending(defect):
        return _status_value(defect) in {"pending", "belum diselesaikan", "belum selesai"}

    def _is_in_progress(defect):
        return _status_value(defect) in {"in progress", "dalam tindakan", "dalam proses"}

    def _is_delayed(defect):
        return _status_value(defect) in {"delayed", "tertangguh"}

    return {
        "total": len(defects),
        "completed": sum(1 for d in defects if _is_completed(d)),
        "pending": sum(1 for d in defects if _is_pending(d)),
        "investigation": sum(1 for d in defects if _is_in_progress(d)),
        "on_hold": sum(1 for d in defects if _is_delayed(d)),
        "appeal": 0,
        "closed": sum(1 for d in defects if _is_closed(d)),
        "overdue": sum(1 for d in defects if d.get("is_overdue") is True),
        "hda_non_compliant": sum(1 for d in defects if d.get("hda_compliant") is False),
        "critical": sum(1 for d in defects if d.get("urgency") == "High"),
    }


def calculate_system_health(stats):
    overdue = int(stats.get("overdue", 0) or 0)
    hda_non_compliant = int(stats.get("hda_non_compliant", 0) or 0)
    critical = int(stats.get("critical", 0) or 0)
    pending = int(stats.get("pending", 0) or 0)
    investigation = int(stats.get("investigation", 0) or 0)
    active_count = overdue + hda_non_compliant + critical + pending + investigation
    pending_width = min(pending * 12, 100)
    delayed_width = min(int(stats.get("on_hold", 0) or 0) * 12, 100)
    overdue_width = min(overdue * 12, 100)

    if overdue > 0 or hda_non_compliant > 0 or critical > 0:
        return {
            "level": "critical",
            "label": "Attention Needed",
            "count": overdue + hda_non_compliant + critical,
            "pending_width": pending_width,
            "delayed_width": delayed_width,
            "overdue_width": overdue_width,
            "detail": "Open overdue or non-compliant defects require review.",
        }

    if pending > 0 or investigation > 0:
        return {
            "level": "warning",
            "label": "Monitoring",
            "count": pending + investigation,
            "pending_width": pending_width,
            "delayed_width": delayed_width,
            "overdue_width": overdue_width,
            "detail": "There are active defects still in progress.",
        }

    return {
        "level": "normal",
        "label": "Normal",
        "count": active_count,
        "pending_width": pending_width,
        "delayed_width": delayed_width,
        "overdue_width": overdue_width,
        "detail": "No overdue or active defect risk detected.",
    }


def build_case_key(role, user_id, defects):
    payload = {
        "role": role,
        "user_id": user_id,
        "defects": [
            {
                "id": d.get("id"),
                "unit": d.get("unit"),
                "desc": d.get("desc"),
                "status": d.get("status"),
                "reported_date": d.get("reported_date"),
                "deadline": d.get("deadline"),
                "completed_date": d.get("completed_date"),
            }
            for d in defects
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def build_public_report_id(report_data):
    case_info = (report_data or {}).get("case_info", {})
    claim_reference = str(
        case_info.get("claim_number") or case_info.get("claim_id") or ""
    ).strip()

    if claim_reference and claim_reference.upper() not in {"N/A", "-"}:
        return claim_reference

    try:
        timestamp = _now_app_timezone().strftime("%Y%m%d-%H%M%S")
    except Exception:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"RPT/{timestamp}"


def auto_close_completed_cases(trigger_role=None):
    """Automatically close cases that stayed completed beyond the configured window."""
    cutoff_date = _now_app_timezone().date() - timedelta(days=AUTO_CLOSE_DAYS)

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, completed_date
            FROM defects
            WHERE status = 'Completed'
              AND completed_date IS NOT NULL
              AND completed_date <= %s
            """,
            (cutoff_date,),
        )
        candidates = cur.fetchall()
        if not candidates:
            return 0

        logged_count = 0
        for defect_id, completed_date in candidates:
            cur.execute(
                """
                SELECT 1
                FROM audit_log
                WHERE action = 'Case Auto Closed'
                  AND defect_id = %s
                LIMIT 1
                """,
                (defect_id,),
            )
            if cur.fetchone():
                continue

            _append_audit_event(
                action="Case Auto Closed",
                role="System",
                defect_id=str(defect_id),
                new_status="Completed",
                details={
                    "triggered_by_role": trigger_role,
                    "auto_close_days": AUTO_CLOSE_DAYS,
                    "completed_date": _to_iso(completed_date),
                },
            )
            logged_count += 1

        return logged_count
    finally:
        cur.close()
        conn.close()


def _get_related_homeowner_ids_for_current_user():
    user_id = _current_user_id()
    if not user_id:
        return []
    role = _current_role()

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT DISTINCT homeowner_id
            FROM report_claim_registry
            WHERE respondent_id = %s
              AND homeowner_id IS NOT NULL
            ORDER BY homeowner_id ASC
            """,
            (user_id,),
        )
        homeowner_ids = [row[0] for row in cur.fetchall() if row and row[0] is not None]
        if homeowner_ids:
            return homeowner_ids

        available_projects = get_available_projects(user_id, role="Developer")
        project_names = [
            (project.get("project_name") or "").strip().lower()
            for project in available_projects
            if (project.get("project_name") or "").strip()
        ]
        if not project_names:
            return []

        cur.execute(
            """
            SELECT DISTINCT homeowner_id
            FROM report_homeowner_profile
            WHERE LOWER(TRIM(COALESCE(project_name, ''))) = ANY(%s)
              AND homeowner_id IS NOT NULL
            ORDER BY homeowner_id ASC
            """,
            (project_names,),
        )
        homeowner_ids = [row[0] for row in cur.fetchall() if row and row[0] is not None]
        if homeowner_ids:
            return homeowner_ids

        if role == "Developer" and not is_main_developer_account(user_id):
            return []

        cur.execute(
            """
            SELECT DISTINCT homeowner_id
            FROM report_homeowner_profile
            WHERE homeowner_id IS NOT NULL
            ORDER BY homeowner_id ASC
            """
        )
        return [row[0] for row in cur.fetchall() if row and row[0] is not None]
    finally:
        cur.close()
        conn.close()


def get_defects_for_role(role):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if role == "Homeowner":
            user_id = _current_user_id()
            cur.execute(
                """
                SELECT d.id, d.unit, d.description, d.reported_date, d.status, d.completed_date, d.user_id, d.urgency, d.deadline, d.remarks, d.created_at, dp.project_name
                FROM defects d
                LEFT JOIN project_units pu ON d.unit = pu.unit_number
                LEFT JOIN developer_projects dp ON pu.project_id = dp.id
                WHERE d.user_id = %s
                ORDER BY d.id
                """,
                (user_id,)
            )
        elif role in {"Developer", "Legal"}:
            cur.execute(
                """
                SELECT d.id, d.unit, d.description, d.reported_date, d.status, d.completed_date, d.user_id, d.urgency, d.deadline, d.remarks, d.created_at, dp.project_name
                FROM defects d
                LEFT JOIN project_units pu ON d.unit = pu.unit_number
                LEFT JOIN developer_projects dp ON pu.project_id = dp.id
                ORDER BY d.id
                """
            )
        else:
            cur.execute(
                """
                SELECT d.id, d.unit, d.description, d.reported_date, d.status, d.completed_date, d.user_id, d.urgency, d.deadline, d.remarks, d.created_at, dp.project_name
                FROM defects d
                LEFT JOIN project_units pu ON d.unit = pu.unit_number
                LEFT JOIN developer_projects dp ON pu.project_id = dp.id
                ORDER BY d.id
                """
            )

        others_project_name = "Others / Unrelated"
        defects = []
        rows = cur.fetchall()
        # Build defects without project_name first (unit values may be encrypted)
        for row in rows:
            defect = {
                "id": row[0],
                "unit": _decrypt_display_text(row[1]) or "",
                "desc": _decrypt_display_text(row[2]) or "",
                "reported_date": _to_iso(row[3]),
                "status": row[4],
                "completed_date": _to_iso(row[5]),
                "owner_id": row[6],
                "urgency": _decrypt_display_text(row[7]) or "",
                "deadline": _to_iso(row[8]),
                "remarks": _decrypt_display_text(row[9]) or "",
                "created_at": _to_iso(row[10]),
                "project_name": others_project_name,
            }

            defect["hda_compliant"] = calculate_hda_compliance(
                defect["reported_date"],
                defect.get("completed_date"),
                defect["status"],
            )
            defect["is_overdue"] = calculate_overdue(
                defect["deadline"],
                defect.get("completed_date"),
                defect["status"],
            )
            defect["closed"] = is_auto_closed(defect["status"], defect.get("completed_date"))
            defect["display_status"] = "Closed" if defect["closed"] else defect["status"]
            defects.append(defect)

        # Resolve project_name for decrypted unit values in bulk to avoid failed SQL joins
        try:
            unit_values = sorted({d["unit"] for d in defects if d.get("unit")})
            if unit_values:
                # Normalize unit numbers for robust matching (trim + lower)
                normalized_units = [u.strip().lower() for u in unit_values]

                # Query project mapping for these unit numbers using LOWER comparison
                cur.execute(
                    """
                    SELECT LOWER(TRIM(pu.unit_number)) AS unit_number_norm, dp.project_name
                    FROM project_units pu
                    JOIN developer_projects dp ON pu.project_id = dp.id
                    WHERE LOWER(TRIM(pu.unit_number)) = ANY(%s)
                    """,
                    (normalized_units,),
                )
                mapping = {row[0]: row[1] for row in cur.fetchall()}

                # Assign mapped project_name where possible
                for d in defects:
                    if not d.get("unit"):
                        continue
                    norm = d["unit"].strip().lower()
                    d["project_name"] = mapping.get(norm) or others_project_name

                # For unmapped units, apply explicit state-prefix rules
                unmapped = [d for d in defects if d.get("project_name") == others_project_name and d.get("unit")]
                if unmapped:
                    # PNG -> Penang
                    png_candidates = [d for d in unmapped if d["unit"].strip().upper().startswith("PNG") or "PNG" in d["unit"].strip().upper()]
                    if png_candidates:
                        cur.execute(
                            """
                            SELECT project_name FROM developer_projects
                            WHERE LOWER(state_name) LIKE %s OR LOWER(state_name) LIKE %s
                            OR LOWER(project_name) LIKE %s OR LOWER(project_name) LIKE %s
                            LIMIT 1
                            """,
                            ("%penang%", "%pinang%", "%penang%", "%pinang%"),
                        )
                        row = cur.fetchone()
                        if row and row[0]:
                            for d in png_candidates:
                                d["project_name"] = row[0]

                    # J- (Johor) -> Johor
                    johor_candidates = [d for d in unmapped if d["unit"].strip().upper().startswith("J-") or "JOHOR" in d["unit"].strip().upper()]
                    if johor_candidates:
                        cur.execute(
                            """
                            SELECT project_name FROM developer_projects
                            WHERE LOWER(state_name) LIKE %s OR LOWER(project_name) LIKE %s
                            LIMIT 1
                            """,
                            ("%johor%", "%johor%"),
                        )
                        row = cur.fetchone()
                        if row and row[0]:
                            for d in johor_candidates:
                                d["project_name"] = row[0]
        except Exception:
            # If mapping fails for any reason, leave project_name blank and continue
            pass

        # Enforce exact UNIT_PROJECT_MAP mappings (user-provided canonical list)
        try:
            for state_name, unit_list in UNIT_PROJECT_MAP.items():
                try:
                    cur.execute(
                        "SELECT project_name FROM developer_projects WHERE LOWER(state_name) = LOWER(%s) LIMIT 1",
                        (state_name,),
                    )
                    pr = cur.fetchone()
                    if not pr or not pr[0]:
                        continue
                    project_name_for_state = pr[0]
                    unit_norms = {u.strip().lower() for u in unit_list}
                    for d in defects:
                        if d.get("unit") and d["unit"].strip().lower() in unit_norms:
                            d["project_name"] = project_name_for_state
                except Exception:
                    # If any state-specific lookup fails, continue with others
                    continue
        except Exception:
            pass

        if role == "Developer" and not is_main_developer_account(_current_user_id()):
            allowed_project_names = {
                (project.get("project_name") or "").strip().lower()
                for project in get_available_projects(_current_user_id(), role=role)
                if (project.get("project_name") or "").strip()
            }
            defects = [
                d for d in defects
                if (d.get("project_name") or "").strip().lower() in allowed_project_names
            ]

        # Attach evidence metadata from storage so callers receive evidence info
        try:
            evidence_store = load_evidence()
        except Exception:
            evidence_store = {}

        for d in defects:
            evidence_data = evidence_store.get(str(d.get("id"))) or {}
            evidence_files = _evidence_items_from_meta(evidence_data)
            if evidence_files:
                d["evidence_uploaded"] = True
                d["evidence_files"] = evidence_files
                d["evidence_count"] = len(evidence_files)
                d["evidence_filename"] = evidence_files[0].get("filename")
                d["evidence_uploaded_at"] = evidence_data.get("uploaded_at") or evidence_files[-1].get("uploaded_at")
            else:
                d["evidence_uploaded"] = False
                d["evidence_files"] = []
                d["evidence_count"] = 0
                d["evidence_filename"] = None
                d["evidence_uploaded_at"] = None

        return defects
    finally:
        cur.close()
        conn.close()


def _current_user_can_access_defect(defect_id):
    role = _current_role()
    if role == "Admin":
        return True

    try:
        defect_id_int = int(defect_id)
    except Exception:
        return False

    return any(
        int(defect.get("id")) == defect_id_int
        for defect in get_defects_for_role(role)
        if str(defect.get("id", "")).isdigit()
    )

def load_remarks():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT DISTINCT ON (defect_id) defect_id, remark
            FROM remarks
            ORDER BY defect_id, created_at DESC
            """
        )
        return {str(defect_id): remark for defect_id, remark in cur.fetchall()}
    finally:
        cur.close()
        conn.close()

def save_remarks(data):
    """Save remarks for defects. Handles both new and updated remarks."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        for defect_id, remark in data.items():
            defect_id_int = int(defect_id)
            remark_str = (remark or "").strip()
            
            # Get the current remark for this defect
            cur.execute(
                """
                SELECT remark FROM remarks 
                WHERE defect_id = %s 
                ORDER BY created_at DESC 
                LIMIT 1
                """,
                (defect_id_int,)
            )
            current_remark_row = cur.fetchone()
            current_remark = current_remark_row[0] if current_remark_row else None
            
            # Only save if the remark has changed
            if current_remark == remark_str:
                continue
            
            # Insert new remark record
            cur.execute(
                "INSERT INTO remarks (defect_id, role, remark) VALUES (%s, %s, %s)",
                (defect_id_int, "Homeowner", remark_str),
            )
            
            # Update defects table with the latest remark
            cur.execute(
                "UPDATE defects SET remarks = %s, updated_at = NOW() WHERE id = %s",
                (remark_str, defect_id_int),
            )
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise Exception(f"Failed to save remarks: {str(e)}")
    finally:
        cur.close()
        conn.close()

def load_status():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, status FROM defects")
        return {str(defect_id): status for defect_id, status in cur.fetchall()}
    finally:
        cur.close()
        conn.close()

def save_status(data):
    conn = get_connection()
    cur = conn.cursor()
    try:
        for defect_id, status in data.items():
            cur.execute(
                "UPDATE defects SET status = %s, updated_at = NOW() WHERE id = %s",
                (status, int(defect_id)),
            )
        conn.commit()
    finally:
        cur.close()
        conn.close()

def load_completion_dates():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT defect_id, completed_date FROM completion_dates")
        return {str(defect_id): _to_iso(completed_date) for defect_id, completed_date in cur.fetchall()}
    finally:
        cur.close()
        conn.close()

def save_completion_dates(data):
    conn = get_connection()
    cur = conn.cursor()
    try:
        for defect_id, completed_date in data.items():
            defect_id_int = int(defect_id)
            if completed_date:
                cur.execute(
                    """
                    INSERT INTO completion_dates (defect_id, completed_date)
                    VALUES (%s, %s)
                    ON CONFLICT (defect_id)
                    DO UPDATE SET completed_date = EXCLUDED.completed_date
                    """,
                    (defect_id_int, completed_date),
                )
                cur.execute(
                    "UPDATE defects SET completed_date = %s, updated_at = NOW() WHERE id = %s",
                    (completed_date, defect_id_int),
                )
            else:
                cur.execute("DELETE FROM completion_dates WHERE defect_id = %s", (defect_id_int,))
                cur.execute(
                    "UPDATE defects SET completed_date = NULL, updated_at = NOW() WHERE id = %s",
                    (defect_id_int,),
                )
        conn.commit()
    finally:
        cur.close()
        conn.close()

def load_versions():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT role, version_no, generated_at, language, report_text FROM report_versions ORDER BY role, version_no"
        )
        versions = {}
        for role, version_no, generated_at, language, report_text in cur.fetchall():
            versions.setdefault(role, []).append(
                {
                    "version": version_no,
                    "generated_at": str(generated_at),
                    "language": language,
                    "report_text": _sanitize_encrypted_fragments(report_text),
                }
            )
        return versions
    finally:
        cur.close()
        conn.close()

def save_versions(data):
    conn = get_connection()
    cur = conn.cursor()
    try:
        for role, versions in data.items():
            for v in versions:
                cur.execute(
                    "SELECT 1 FROM report_versions WHERE role = %s AND version_no = %s LIMIT 1",
                    (role, v.get("version")),
                )
                if cur.fetchone():
                    continue
                cur.execute(
                    """
                    INSERT INTO report_versions (role, language, version_no, report_text, generated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        role,
                        v.get("language", "ms"),
                        v.get("version"),
                        _sanitize_encrypted_fragments(v.get("report_text", "")),
                        v.get("generated_at", _now_app_timezone().strftime("%Y-%m-%d %H:%M:%S")),
                    ),
                )
        conn.commit()
    finally:
        cur.close()
        conn.close()

# AUDIT LOG FUNCTIONS
def load_audit():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT action, role, defect_id, filename, new_status, timestamp, details FROM audit_log ORDER BY id"
        )
        audit_rows = []
        for action, role, defect_id, filename, new_status, timestamp, details in cur.fetchall():
            row = {
                "action": action,
                "role": role,
                "defect_id": defect_id,
                "filename": filename,
                "new_status": new_status,
                "timestamp": str(timestamp),
            }
            if details:
                row["details"] = details
            audit_rows.append(row)
        return audit_rows
    finally:
        cur.close()
        conn.close()


def get_audit_filter_options():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT DISTINCT role FROM audit_log WHERE role IS NOT NULL AND role <> '' ORDER BY role"
        )
        roles = [row[0] for row in cur.fetchall()]

        cur.execute(
            "SELECT DISTINCT action FROM audit_log WHERE action IS NOT NULL AND action <> '' ORDER BY action"
        )
        actions = [row[0] for row in cur.fetchall()]
        return roles, actions
    finally:
        cur.close()
        conn.close()


def get_audit_entries_paginated(page=1, per_page=15, role_filter="", action_filter="", date_filter=""):
    conn = get_connection()
    cur = conn.cursor()
    try:
        where_clauses = []
        params = []

        if role_filter:
            where_clauses.append("LOWER(COALESCE(role, '')) = %s")
            params.append(role_filter.lower())

        if action_filter:
            where_clauses.append("LOWER(COALESCE(action, '')) = %s")
            params.append(action_filter.lower())

        parsed_date = None
        if date_filter:
            try:
                parsed_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            except ValueError:
                parsed_date = None
        if parsed_date:
            where_clauses.append("DATE(timestamp) = %s")
            params.append(parsed_date)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        cur.execute(f"SELECT COUNT(*) FROM audit_log {where_sql}", params)
        total = cur.fetchone()[0] or 0

        safe_page = max(1, int(page))
        safe_per_page = max(1, int(per_page))
        offset = (safe_page - 1) * safe_per_page

        query_params = params + [safe_per_page, offset]
        cur.execute(
            f"""
            SELECT action, role, defect_id, filename, new_status, timestamp, details
            FROM audit_log
            {where_sql}
            ORDER BY timestamp DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            query_params,
        )

        entries = []
        for action, role, defect_id, filename, new_status, timestamp, details in cur.fetchall():
            entries.append(
                {
                    "action": action,
                    "role": role,
                    "defect_id": defect_id,
                    "filename": filename,
                    "new_status": new_status,
                    "timestamp": str(timestamp),
                    "details": details,
                }
            )

        return entries, total
    finally:
        cur.close()
        conn.close()

def save_audit(data):
    conn = get_connection()
    cur = conn.cursor()
    try:
        for item in data:
            cur.execute(
                """
                SELECT 1 FROM audit_log
                WHERE action = %s
                  AND COALESCE(role, '') = COALESCE(%s, '')
                  AND COALESCE(defect_id, -1) = COALESCE(%s, -1)
                  AND COALESCE(filename, '') = COALESCE(%s, '')
                  AND COALESCE(new_status, '') = COALESCE(%s, '')
                  AND timestamp = %s
                LIMIT 1
                """,
                (
                    item.get("action"),
                    item.get("role"),
                    item.get("defect_id"),
                    item.get("filename"),
                    item.get("new_status"),
                    item.get("timestamp", _now_app_timezone().strftime("%Y-%m-%d %H:%M:%S")),
                ),
            )
            if cur.fetchone():
                continue
            cur.execute(
                """
                INSERT INTO audit_log (action, role, defect_id, filename, new_status, timestamp, details)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    item.get("action"),
                    item.get("role"),
                    item.get("defect_id"),
                    item.get("filename"),
                    item.get("new_status"),
                    item.get("timestamp", _now_app_timezone().strftime("%Y-%m-%d %H:%M:%S")),
                    json.dumps(item.get("details", {})),
                ),
            )
        conn.commit()
    finally:
        cur.close()
        conn.close()

# SIMPLE ENCRYPTION HELPERS
def encrypt_text(text):
    return _encrypt_text(text)

def decrypt_text(text):
    return _decrypt_text(text)


def _decrypt_display_text(value):
    text = decrypt_text(value)
    raw_text = str(value or "")
    if text.strip().startswith("gAAAA"):
        return ""
    if text and text != raw_text:
        return text
    if raw_text.startswith("gAAAA") or _is_encrypted_text(text):
        return ""
    return text


def _sanitize_encrypted_fragments(value):
    text = str(value or "")
    if "gAAAA" not in text:
        return text

    token_pattern = re.compile(r"gAAAA[A-Za-z0-9_\-=]+")

    def replace_token(match):
        decrypted = _decrypt_display_text(match.group(0))
        return decrypted or "[Encrypted data unavailable]"

    return token_pattern.sub(replace_token, text)


def _sanitize_for_display(value):
    if isinstance(value, dict):
        return {key: _sanitize_for_display(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_display(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_for_display(item) for item in value)
    if isinstance(value, str):
        return _sanitize_encrypted_fragments(value)
    return value

# AUTO BACKUP FUNCTION
def backup_versions():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT role, version_no, generated_at, language, report_text FROM report_versions ORDER BY role, version_no"
        )
        rows = cur.fetchall()
        if not rows:
            return None

        snapshot = {}
        for role, version_no, generated_at, language, report_text in rows:
            snapshot.setdefault(role, []).append(
                {
                    "version": version_no,
                    "generated_at": str(generated_at),
                    "language": language,
                    "report_text": _sanitize_encrypted_fragments(report_text),
                }
            )

        backup_root = os.path.join(os.path.dirname(__file__), "audit_data", "backups")
        os.makedirs(backup_root, exist_ok=True)

        backup_stamp = _now_app_timezone().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_root, f"report_versions_{backup_stamp}.json")
        manifest_file = os.path.join(backup_root, "backup_manifest.json")

        backup_payload = {
            "backup_type": "report_versions_snapshot",
            "created_at": _now_app_timezone().strftime("%Y-%m-%d %H:%M:%S"),
            "source_table": "report_versions",
            "roles": sorted(snapshot.keys()),
            "version_count": sum(len(items) for items in snapshot.values()),
            "versions": snapshot,
        }

        with open(backup_file, "w", encoding="utf-8") as handle:
            json.dump(backup_payload, handle, ensure_ascii=False, indent=2)

        manifest_payload = {
            "last_backup_at": backup_payload["created_at"],
            "latest_backup_file": os.path.basename(backup_file),
            "backup_files": [os.path.basename(backup_file)],
            "version_count": backup_payload["version_count"],
        }

        if os.path.exists(manifest_file):
            try:
                with open(manifest_file, "r", encoding="utf-8") as handle:
                    existing_manifest = json.load(handle)
                previous_files = existing_manifest.get("backup_files", [])
                if os.path.basename(backup_file) not in previous_files:
                    manifest_payload["backup_files"] = previous_files + [os.path.basename(backup_file)]
            except Exception:
                pass

        with open(manifest_file, "w", encoding="utf-8") as handle:
            json.dump(manifest_payload, handle, ensure_ascii=False, indent=2)

        return backup_payload
    finally:
        cur.close()
        conn.close()


def load_backup_manifest():
    manifest_file = os.path.join(os.path.dirname(__file__), "audit_data", "backups", "backup_manifest.json")
    if not os.path.exists(manifest_file):
        return {
            "last_backup_at": None,
            "latest_backup_file": None,
            "backup_files": [],
            "version_count": 0,
        }

    try:
        with open(manifest_file, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        return {
            "last_backup_at": manifest.get("last_backup_at"),
            "latest_backup_file": manifest.get("latest_backup_file"),
            "backup_files": manifest.get("backup_files", []),
            "version_count": manifest.get("version_count", 0),
        }
    except Exception:
        return {
            "last_backup_at": None,
            "latest_backup_file": None,
            "backup_files": [],
            "version_count": 0,
        }

def load_evidence():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT defect_id, filename, uploaded_at
            FROM evidence
            ORDER BY defect_id, uploaded_at ASC, filename ASC
            """
        )
        evidence_by_defect = {}
        for defect_id, filename, uploaded_at in cur.fetchall():
            key = str(defect_id)
            item = {
                "filename": filename,
                "uploaded_at": str(uploaded_at),
            }
            evidence_by_defect.setdefault(key, {"files": []})["files"].append(item)

        for payload in evidence_by_defect.values():
            files = payload.get("files", [])
            files.sort(key=lambda item: (_evidence_filename_index(item.get("filename")), item.get("filename") or ""))
            payload["files"] = files[:REQUIRED_EVIDENCE_IMAGE_COUNT]
            latest = max(
                payload["files"],
                key=lambda item: item.get("uploaded_at") or "",
                default={},
            )
            payload["filename"] = latest.get("filename")
            payload["uploaded_at"] = latest.get("uploaded_at")

        return evidence_by_defect
    finally:
        cur.close()
        conn.close()

def save_evidence(data):
    conn = get_connection()
    cur = conn.cursor()
    try:
        for defect_id, item in data.items():
            cur.execute("DELETE FROM evidence WHERE defect_id = %s", (int(defect_id),))
            for evidence_item in _evidence_items_from_meta(item):
                cur.execute(
                    "INSERT INTO evidence (defect_id, filename, uploaded_at) VALUES (%s, %s, %s)",
                    (
                        int(defect_id),
                        evidence_item.get("filename"),
                        evidence_item.get("uploaded_at", _now_app_timezone().strftime("%Y-%m-%d %H:%M:%S")),
                    ),
                )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_closed_evidence_appendix(role, claimant_unit=None):
    """Return closed defects for role appendix view."""
    if role not in ["Homeowner", "Developer", "Legal", "Admin"]:
        return []

    # Use one common source so closed-case appendix is consistent across roles.
    source_role = "Developer"
    defects = get_defects_for_role(source_role)
    status_store = load_status()
    completion_store = load_completion_dates()
    evidence_store = load_evidence()

    appendix_rows = []
    for d in defects:
        defect_id = str(d.get("id"))
        status = status_store.get(defect_id, d.get("status"))
        completed_date = completion_store.get(defect_id, d.get("completed_date"))
        evidence = evidence_store.get(defect_id) or {}
        evidence_files = _evidence_items_from_meta(evidence)
        first_evidence = evidence_files[0] if evidence_files else {}

        if not is_auto_closed(status, completed_date):
            continue

        appendix_rows.append(
            {
                "id": d.get("id"),
                "unit": d.get("unit", "-"),
                "status": "Closed",
                "reported_date": d.get("reported_date") or "-",
                "completed_date": completed_date or "-",
                "hda_compliant": calculate_hda_compliance(d.get("reported_date"), completed_date, status),
                "filename": first_evidence.get("filename") or evidence.get("filename", "-"),
                "evidence_files": evidence_files,
                "uploaded_at": evidence.get("uploaded_at") or first_evidence.get("uploaded_at", "-"),
            }
        )

    appendix_rows.sort(key=lambda item: int(item["id"]) if str(item.get("id", "")).isdigit() else 0)
    return appendix_rows


def _closed_appendix_field(label, value, width=24):
    return f"{label:<{width}}: {value}"


def _hda_compliance_display(value, language, status=None):
    normalized = str(value).strip().lower()
    is_compliant = normalized in {"yes", "ya", "true", "1", "mematuhi", "compliant"}
    if language == "en":
        return "Compliant" if is_compliant else "Non-Compliant"
    return "Mematuhi" if is_compliant else "Tidak Mematuhi"


def _append_closed_case_summary_lines(appendix_lines, item, language):
    closed_days = calculate_days_to_complete(item.get("reported_date"), item.get("completed_date"))

    if language == "ms":
        appendix_lines.append(_closed_appendix_field("Unit", item.get("unit", "-")))
        appendix_lines.append(_closed_appendix_field("Tarikh Dilaporkan", _format_display_date(item.get("reported_date"), language)))
        appendix_lines.append(_closed_appendix_field("Tarikh Siap", _format_display_date(item.get("completed_date"), language)))
        appendix_lines.append(_closed_appendix_field("Tempoh Siap (Hari)", closed_days if closed_days is not None else "-"))
        appendix_lines.append(_closed_appendix_field("Status Pematuhan HDA", _hda_compliance_display(item.get("hda_compliant"), language)))
        appendix_lines.append(_closed_appendix_field("Peraturan Ditutup", f"Ditutup selepas {AUTO_CLOSE_DAYS} hari dari tarikh siap"))
        appendix_lines.append("Gambar Kecacatan:")
    else:
        appendix_lines.append(_closed_appendix_field("Unit", item.get("unit", "-")))
        appendix_lines.append(_closed_appendix_field("Reported Date", _format_display_date(item.get("reported_date"), language)))
        appendix_lines.append(_closed_appendix_field("Completed", _format_display_date(item.get("completed_date"), language)))
        appendix_lines.append(_closed_appendix_field("Days to Complete", closed_days if closed_days is not None else "-"))
        appendix_lines.append(_closed_appendix_field("HDA Compliance Status", _hda_compliance_display(item.get("hda_compliant"), language)))
        appendix_lines.append(_closed_appendix_field("Closed Rule", f"Closed after {AUTO_CLOSE_DAYS} days from completion"))
        appendix_lines.append("Defect Image:")


def build_closed_appendix_lines(closed_evidence_appendix, language):
    """Build a consistent closed-case appendix text block for all roles."""
    detail_indent = "   "
    if language == "ms":
        appendix_lines = [
            "",
            "LAMPIRAN A: BUTIRAN KES DITUTUP",
            "Kes ditutup dikecualikan daripada badan laporan utama dan disenaraikan di sini untuk rujukan sahaja.",
            "",
            "Rekod Kes Ditutup Pemilik Menuntut:",
            f"{detail_indent}Unit Pemilik Menuntut: {closed_evidence_appendix.get('claimant_unit', '') if isinstance(closed_evidence_appendix, dict) else '' or 'Tiada unit pemilik menuntut direkodkan.'}",
            "",
            "Senarai Kecacatan Pemilik Menuntut:",
        ]
    else:
        appendix_lines = [
            "",
            "APPENDIX A: CLOSED CASE DETAILS",
            "Closed cases are excluded from the main report body and listed here for reference only.",
            "",
            "Claimant Owner Closed Case Records:",
            f"{detail_indent}Claimant Owner Unit: {closed_evidence_appendix.get('claimant_unit', '') if isinstance(closed_evidence_appendix, dict) else '' or 'No claimant owner unit recorded.'}",
            "",
            "Claimant Owner Defect List:",
        ]

    if not closed_evidence_appendix:
        appendix_lines.append(
            detail_indent
            + (
                "Tiada rekod kes ditutup yang tersedia pada masa ini."
                if language == "ms"
                else "No closed case records are currently available."
            )
        )
        return appendix_lines

    for idx, item in enumerate(closed_evidence_appendix, 1):
        if idx > 1:
            appendix_lines.append("")
        header_prefix = f"{chr(64 + idx)}." if idx <= 26 else f"{idx}."

        if language == "ms":
            appendix_lines.append(f"{header_prefix} Kecacatan ID {item.get('id', '-')}:")
        else:
            appendix_lines.append(f"{header_prefix} Defect ID {item.get('id', '-')}:")
        _append_closed_case_summary_lines(appendix_lines, item, language)

        appendix_lines.append("")

    return appendix_lines


def _normalise_language(language):
    value = (language or "").strip().lower()
    if value in {"ms", "bm", "bahasa", "bahasa malaysia", "malay", "melayu"}:
        return "ms"
    return "en"


def _strip_opposite_language_report(report_text, language):
    """Remove an accidentally appended second-language report block."""
    if not report_text:
        return report_text

    text = str(report_text).replace("\r\n", "\n").replace("\r", "\n").strip()
    language = _normalise_language(language)

    markers = {
        "en": (
            r"AI-GENERATED CLAIM SUMMARY REPORT",
            r"TRIBUNAL SUPPORT REPORT",
            r"Support Report for Claim",
            r"Compliance Report for Reference",
            r"Overview Report on Defect Liability Period",
            r"1\.\s*Case Background",
            r"1\.\s*Purpose of Report",
        ),
        "ms": (
            r"LAPORAN RINGKASAN TUNTUTAN DIJANA AI",
            r"LAPORAN SOKONGAN TRIBUNAL",
            r"Laporan Sokongan Bagi Tuntutan",
            r"Laporan Pematuhan Bagi Rujukan",
            r"Laporan Gambaran Keseluruhan",
            r"1\.\s*Latar Belakang Kes",
            r"1\.\s*Tujuan Laporan",
        ),
    }
    desired_markers = markers[language]
    opposite_markers = markers["ms" if language == "en" else "en"]

    def _line_marker_positions(marker_list):
        pattern = r"(?im)^\s*(?:" + "|".join(marker_list) + r")"
        return [match.start() for match in re.finditer(pattern, text)]

    desired_positions = _line_marker_positions(desired_markers)
    opposite_positions = _line_marker_positions(opposite_markers)

    if not opposite_positions:
        return text

    start = 0
    if desired_positions:
        first_desired = min(desired_positions)
        if any(pos < first_desired for pos in opposite_positions):
            start = first_desired

    end = len(text)
    for pos in opposite_positions:
        if pos > start:
            end = min(end, pos)

    return text[start:end].strip()


def strip_closed_appendix_section(report_text):
    text = (report_text or "").rstrip()
    marker = re.search(r"(?im)^(APPENDIX A:|LAMPIRAN A:)", text)
    if marker:
        return text[: marker.start()].rstrip()
    return text


def enforce_closed_appendix_format(report_text, closed_evidence_appendix, language):
    """Ensure closed appendix always uses the canonical line-by-line format."""
    text = strip_closed_appendix_section(report_text)

    appendix_lines = build_closed_appendix_lines(closed_evidence_appendix, language)
    return text + "\n" + "\n".join(appendix_lines)


def _closed_appendix_snapshot_rows(closed_evidence_appendix):
    if isinstance(closed_evidence_appendix, dict):
        rows = closed_evidence_appendix.get("all_rows", [])
    elif isinstance(closed_evidence_appendix, list):
        rows = closed_evidence_appendix
    else:
        rows = []

    return [item for item in rows if isinstance(item, dict)]


def _closed_appendix_evidence_items(item):
    if not isinstance(item, dict):
        return []
    return _evidence_items_from_meta({
        "files": item.get("evidence_files") or item.get("files") or [],
        "filename": item.get("filename"),
        "uploaded_at": item.get("uploaded_at"),
    })


def _format_generated_datetime(language):
    now = _now_app_timezone()
    if language == "ms":
        bulan_bm = {
            1: "Januari", 2: "Februari", 3: "Mac", 4: "April",
            5: "Mei", 6: "Jun", 7: "Julai", 8: "Ogos",
            9: "September", 10: "Oktober", 11: "November", 12: "Disember",
        }
        return f"{now.day:02d} {bulan_bm[now.month]} {now.year}, {now.strftime('%H:%M')}"
    return now.strftime("%d %B %Y, %H:%M")


def _format_display_date(raw_date, language):
    value = str(raw_date or "").strip()
    if not value or value in {"-", "N/A", "None"}:
        return "-"

    date_part = value[:10]
    parsed = None
    for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            parsed = datetime.strptime(date_part, date_format)
            break
        except Exception:
            continue

    if not parsed:
        return value

    if language == "ms":
        bulan_bm = {
            1: "Januari", 2: "Februari", 3: "Mac", 4: "April",
            5: "Mei", 6: "Jun", 7: "Julai", 8: "Ogos",
            9: "September", 10: "Oktober", 11: "November", 12: "Disember",
        }
        return f"{parsed.day:02d} {bulan_bm[parsed.month]} {parsed.year}"

    return parsed.strftime("%d %B %Y")


def _format_display_timestamp(raw_timestamp, language):
    value = str(raw_timestamp or "").strip()
    if not value or value == "N/A":
        return "N/A"

    parsed = None
    for date_format in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(value[:19], date_format)
            break
        except Exception:
            continue

    if not parsed:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return value

    if language == "ms":
        bulan_bm = {
            1: "Januari", 2: "Februari", 3: "Mac", 4: "April",
            5: "Mei", 6: "Jun", 7: "Julai", 8: "Ogos",
            9: "September", 10: "Oktober", 11: "November", 12: "Disember",
        }
        return f"{parsed.day:02d} {bulan_bm[parsed.month]} {parsed.year}, {parsed.strftime('%H:%M:%S')}"

    return parsed.strftime("%d %B %Y, %H:%M:%S")


def refresh_generated_datetime_line(report_text, language):
    if not report_text:
        return report_text

    # Keep the datetime line - don't remove it!
    # This function should preserve the Tarikh Jana/Generated Date line that's already in the report
    return report_text.strip()


def normalize_report_section_spacing(report_text):
    if not report_text:
        return report_text

    expanded_gap_headers = (
        r"1\.\s+Tujuan\s+Laporan",
        r"1\.\s+Purpose\s+of\s+the\s+Report",
        r"1\.\s+Latar\s+Belakang\s+Kes",
        r"1\.\s+Case\s+Background",
        r"5\.\s+Pemerhatian\s+Berkaitan\s+Pematuhan\s+Tempoh",
        r"5\.\s+Observations\s+on\s+Timeframe\s+Compliance",
        r"4\.\s+Pemerhatian\s+Berkaitan\s+Pematuhan\s+dan\s+Tarikh\s+Akhir",
        r"3\.\s+Pemerhatian\s+Berkaitan\s+Status\s+dan\s+Tempoh",
        r"3\.\s+Recorded\s+Status\s+and\s+Timeframe\s+Observations",
    )
    expanded_gap_header_pattern = "|".join(expanded_gap_headers)

    text = report_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?<!\n)\n(?=\s*\d+\.\s+)", "\n\n", text)
    text = re.sub(r"(?<!\n)\n(?=\s*(?:AI\s+DISCLAIMER|PENAFIAN\s+AI)\s*:)", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"(?m)^(\d+\.\s+[^\n]+)\n(?!\n)", r"\1\n\n", text)
    text = re.sub(r"(?im)^((?:AI\s+DISCLAIMER|PENAFIAN\s+AI)\s*:)\n(?!\n)", r"\1\n\n", text)
    text = re.sub(
        rf"(?im)\n+\s*(?=({expanded_gap_header_pattern})\s*$)",
        "\n\n\n",
        text,
    )
    return text


def normalize_report_date_values(report_text, language):
    if not report_text:
        return report_text

    date_labels = (
        "Tarikh Jana",
        "Generated Date",
        "Tarikh Dilaporkan",
        "Reported Date",
        "Tarikh Siap Dijadualkan",
        "Scheduled Completion Date",
        "Tarikh Siap Sebenar",
        "Actual Completion Date",
        "Tarikh Siap",
        "Completed",
        "Tarikh Pembelian/ Transaksi",
        "Date of Purchase/Transaction",
    )
    label_pattern = "|".join(re.escape(label) for label in date_labels)

    def replace_match(match):
        label = match.group("label")
        value = match.group("value").strip()
        if re.search(r"\d{1,2}:\d{2}", value):
            formatted_value = _format_display_timestamp(value, language)
        else:
            formatted_value = _format_display_date(value, language)
        return f"{match.group('indent')}{label}: {formatted_value}"

    return re.sub(
        rf"^(?P<indent>\s*)(?P<label>{label_pattern})\s*:\s*(?P<value>[^\n]+)$",
        replace_match,
        report_text,
        flags=re.IGNORECASE | re.MULTILINE,
    )


def normalize_legal_statistics_section(report_text):
    if not report_text:
        return report_text

    text = str(report_text)

    def replace_ms(match):
        closed = match.group(4)
        pending = match.group(5)
        overdue = match.group(6)
        hda_non_compliant = match.group(7)
        return (
            f"{match.group(1)}"
            f"Jumlah keseluruhan kecacatan: {match.group(2)}\n"
            f"Telah diselesaikan: {match.group(3)}\n"
            f"Kes Ditutup: {closed or 0}\n"
            f"Masih belum diselesaikan: {pending}\n"
            f"Direkodkan sebagai tertunggak: {overdue}\n"
            f"Tidak mematuhi tempoh 30 hari HDA: {hda_non_compliant}\n"
        )

    def replace_en(match):
        closed = match.group(4)
        pending = match.group(5)
        overdue = match.group(6)
        hda_non_compliant = match.group(7)
        return (
            f"{match.group(1)}"
            f"Total recorded defects: {match.group(2)}\n"
            f"Completed: {match.group(3)}\n"
            f"Closed Cases: {closed or 0}\n"
            f"Still unresolved: {pending}\n"
            f"Recorded as overdue: {overdue}\n"
            f"Non-compliant with 30-day HDA requirement: {hda_non_compliant}\n"
        )

    text = re.sub(
        r"(?is)(2\.\s*Kedudukan Statistik Rekod Kecacatan\s*\n+)\s*"
        r"Jumlah keseluruhan kecacatan:\s*(\d+)\.?\s*"
        r"Telah diselesaikan:\s*(\d+)\.?\s*"
        r"(?:Kes Ditutup:\s*(\d+)\.?\s*)?"
        r"Masih belum diselesaikan:\s*(\d+)\.?\s*"
        r"Direkodkan sebagai\s+tertunggak:\s*(\d+)\.?\s*"
        r"Tidak mematuhi tempoh 30 hari HDA:\s*(\d+)\.?",
        replace_ms,
        text,
    )

    text = re.sub(
        r"(?is)(2\.\s*Statistical Position of Defect Records\s*\n+)\s*"
        r"Total recorded defects:\s*(\d+)\.?\s*"
        r"Completed:\s*(\d+)\.?\s*"
        r"(?:Closed Cases:\s*(\d+)\.?\s*)?"
        r"Still unresolved:\s*(\d+)\.?\s*"
        r"Recorded as overdue:\s*(\d+)\.?\s*"
        r"Non-compliant with 30-day HDA requirement:\s*(\d+)\.?",
        replace_en,
        text,
    )

    return text


def enforce_legal_statistics_section_counts(report_text, language, summary_stats):
    if not report_text or not summary_stats:
        return report_text

    total = int(summary_stats.get("total_defects", summary_stats.get("total", 0)) or 0)
    completed = int(summary_stats.get("completed_defects", summary_stats.get("completed", 0)) or 0)
    closed = int(summary_stats.get("closed_defects", summary_stats.get("closed", 0)) or 0)
    pending = int(summary_stats.get("pending_defects", summary_stats.get("pending", 0)) or 0)
    overdue = int(summary_stats.get("overdue_defects", summary_stats.get("overdue", 0)) or 0)
    hda_non_compliant = int(summary_stats.get("hda_non_compliant_defects", summary_stats.get("hda_non_compliant", 0)) or 0)

    if language == "ms":
        section_body = (
            f"Jumlah keseluruhan kecacatan: {total}\n"
            f"Telah diselesaikan: {completed}\n"
            f"Kes Ditutup: {closed}\n"
            f"Masih belum diselesaikan: {pending}\n"
            f"Direkodkan sebagai tertunggak: {overdue}\n"
            f"Tidak mematuhi tempoh 30 hari HDA: {hda_non_compliant}\n\n"
        )
        pattern = r"(2\.\s*Kedudukan Statistik Rekod Kecacatan\s*\n+)(.*?)(?=\n\s*3\.\s|\Z)"
    else:
        section_body = (
            f"Total recorded defects: {total}\n"
            f"Completed: {completed}\n"
            f"Closed Cases: {closed}\n"
            f"Still unresolved: {pending}\n"
            f"Recorded as overdue: {overdue}\n"
            f"Non-compliant with 30-day HDA requirement: {hda_non_compliant}\n\n"
        )
        pattern = r"(2\.\s*Statistical Position of Defect Records\s*\n+)(.*?)(?=\n\s*3\.\s|\Z)"

    updated, count = re.subn(
        pattern,
        r"\1" + section_body,
        report_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not count:
        return report_text

    updated = re.sub(
        r"(Tidak mematuhi tempoh 30 hari HDA:\s*\d+)\s*\n+\s*(?=3\.\s)",
        r"\1\n\n",
        updated,
        flags=re.IGNORECASE,
    )
    updated = re.sub(
        r"(Non-compliant with 30-day HDA requirement:\s*\d+)\s*\n+\s*(?=3\.\s)",
        r"\1\n\n",
        updated,
        flags=re.IGNORECASE,
    )
    return updated


def remove_english_tribunal_title_after_subtitle(report_text, language):
    return report_text


def _report_title_for_role(labels, role):
    role_key = str(role or "").strip().lower()
    title_key = {
        "homeowner": "homeowner_report_title",
        "developer": "developer_report_title",
        "legal": "legal_report_title",
    }.get(role_key, "report_title")
    return labels.get(title_key) or labels.get("report_title", "")


def _report_subtitle_for_role(labels, role):
    role_key = str(role or "").strip().lower()
    subtitle_key = {
        "homeowner": "homeowner_report_subtitle",
        "developer": "developer_report_subtitle",
        "legal": "legal_report_subtitle",
    }.get(role_key, "legal_report_subtitle")
    return labels.get(subtitle_key, "")


def _strip_known_report_header_lines(report_text, language):
    if not report_text:
        return report_text

    labels = PDF_LABELS.get(language, PDF_LABELS["ms"])
    known_lines = {
        labels.get("ai_title", ""),
        labels.get("report_title", ""),
        labels.get("homeowner_report_title", ""),
        labels.get("developer_report_title", ""),
        labels.get("legal_report_title", ""),
        labels.get("homeowner_report_subtitle", ""),
        labels.get("developer_report_subtitle", ""),
        labels.get("legal_report_subtitle", ""),
        "AI-GENERATED CLAIM SUMMARY REPORT",
        "LAPORAN RINGKASAN TUNTUTAN DIJANA AI",
        "TRIBUNAL SUPPORT REPORT - DEFECT LIABILITY PERIOD (DLP)",
        "TRIBUNAL SUPPORT REPORT â€“ DEFECT LIABILITY PERIOD (DLP)",
        "LAPORAN SOKONGAN TRIBUNAL - TEMPOH LIABILITI KECACATAN (DLP)",
        "LAPORAN SOKONGAN TRIBUNAL â€“ TEMPOH LIABILITI KECACATAN (DLP)",
    }
    known_lines = {str(item).strip().lower() for item in known_lines if str(item or "").strip()}
    date_prefixes = ("generated date:", "tarikh jana:")

    lines = str(report_text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    index = 0
    while index < len(lines):
        candidate = lines[index].strip()
        if not candidate:
            index += 1
            continue

        normalized = candidate.lower()
        upper_candidate = candidate.upper()
        looks_like_report_title = (
            "DEFECT LIABILITY PERIOD (DLP)" in upper_candidate
            and upper_candidate.startswith(("TRIBUNAL SUPPORT REPORT", "RESPONDENT COMPLIANCE REPORT", "TRIBUNAL REFERENCE REPORT"))
        ) or (
            "TEMPOH LIABILITI KECACATAN (DLP)" in upper_candidate
            and upper_candidate.startswith("LAPORAN ")
        )
        if normalized in known_lines or normalized.startswith(date_prefixes) or looks_like_report_title:
            index += 1
            continue
        break

    return "\n".join(lines[index:]).lstrip()


def normalize_defect_detail_indentation(report_text):
    if not report_text:
        return report_text

    report_text = re.sub(
        r"(?im)(?<!\n)\n(?=[ \t]*(?:[a-z]|[A-Z])\.\s+(?:Defect ID|Kecacatan ID)\b)",
        "\n\n",
        report_text,
    )

    report_text = re.sub(
        r"(?im)^[ \t]*(Peraturan Ditutup\s*:)\s*\n[ \t]*(Ditutup selepas[^\n]*)$",
        r"\1 \2",
        report_text,
    )
    report_text = re.sub(
        r"(?im)^[ \t]*(Closed Rule\s*:)\s*\n[ \t]*(Closed after[^\n]*)$",
        r"\1 \2",
        report_text,
    )

    detail_labels = (
        "Description",
        "Keterangan",
        "Unit",
        "Reported Date",
        "Tarikh Dilaporkan",
        "Scheduled Completion Date",
        "Tarikh Siap Dijadualkan",
        "Actual Completion Date",
        "Completed",
        "Tarikh Siap Sebenar",
        "Tarikh Siap",
        "Days to Complete",
        "Tempoh Siap (Hari)",
        "Status",
        "Current Status",
        "Status Semasa",
        "Overdue Status",
        "Status Tertunggak",
        "HDA Compliance (30 Days)",
        "HDA Compliance Status",
        "Pematuhan HDA (30 Hari)",
        "Status Pematuhan HDA",
        "Priority",
        "Keutamaan",
        "Remarks",
        "Ulasan",
        "Closed Rule",
        "Peraturan Ditutup",
        "Defect Image",
        "Gambar Kecacatan",
    )
    label_pattern = "|".join(re.escape(label) for label in detail_labels)
    return re.sub(
        rf"(?m)^[ \t]*({label_pattern}\s*:)",
        r"   \1",
        report_text,
        flags=re.IGNORECASE,
    )


def normalize_priority_values_for_language(report_text, language):
    if not report_text:
        return report_text

    if language == "ms":
        replacements = {
            "high": "Tinggi",
            "medium": "Sederhana",
            "low": "Rendah",
        }
        label_pattern = r"(Keutamaan\s*:\s*)"
    else:
        replacements = {
            "tinggi": "High",
            "sederhana": "Medium",
            "rendah": "Low",
        }
        label_pattern = r"(Priority\s*:\s*)"

    def replace_priority(match):
        label = match.group(1)
        value = match.group(2)
        normalized = replacements.get(value.strip().lower(), value.strip())
        return f"{label.rstrip()} {normalized}"

    return re.sub(
        rf"(?im)^\s*{label_pattern}(high|medium|low|tinggi|sederhana|rendah)\s*$",
        replace_priority,
        report_text,
    )


def _format_claim_amount_for_report_text(raw_amount):
    value = str(raw_amount or "").strip()
    if not value or value in {"-", "Unknown"}:
        return "-"

    cleaned = value.replace("RM", "").replace(",", "").strip()
    try:
        amount_num = float(cleaned)
        return f"{amount_num:,.2f}"
    except Exception:
        return value


def enforce_case_background_section(report_text, language, claim_id, claim_amount, total_defects):
    claim_id_value = str(claim_id or "-")
    claim_amount_value = _format_claim_amount_for_report_text(claim_amount)
    defects_value = int(total_defects or 0)

    if language == "ms":
        section_text = (
            f"Nombor rujukan tuntutan untuk kes ini adalah {claim_id_value}, "
            f"dengan amaun tuntutan direkodkan sebanyak RM {claim_amount_value}. "
            f"Berdasarkan dokumen yang dikemukakan, jumlah keseluruhan kecacatan yang direkodkan adalah {defects_value}."
        )
        pattern = r"(1\.\s*Latar\s*Belakang\s*Kes\s*\n)(.*?)(?=\n\s*2\.|\Z)"
    else:
        section_text = (
            f"The claim reference number for this case is {claim_id_value}, "
            f"with a recorded claim amount of RM {claim_amount_value}. "
            f"Based on the submitted documentation, a total of {defects_value} defects have been recorded."
        )
        pattern = r"(1\.\s*Case\s*Background\s*\n)(.*?)(?=\n\s*2\.|\Z)"

    updated, count = re.subn(
        pattern,
        r"\1" + section_text + "\n\n",
        report_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return updated if count > 0 else report_text


def extract_claim_reference_from_report_text(report_text):
    text = report_text or ""
    match = re.search(r"\bTTPM/[A-Z]+/\d{4}/\d{6}\b", text)
    claim_reference = match.group(0) if match else ""
    if "/UNK/" in claim_reference:
        return ""
    return claim_reference

def draw_justified_line(pdf, text, x, y, max_width, font_name, font_size):
    words = text.split()
    if len(words) <= 1:
        pdf.drawString(x, y, text)
        return

    pdf.setFont(font_name, font_size)

    words_width = sum(pdf.stringWidth(w, font_name, font_size) for w in words)
    space_needed = max_width - words_width
    if space_needed <= 0:
        pdf.drawString(x, y, text)
        return

    gap = space_needed / (len(words) - 1)

    cursor_x = x
    for w in words:
        pdf.drawString(cursor_x, y, w)
        cursor_x += pdf.stringWidth(w, font_name, font_size) + gap

def draw_footer(pdf, width, labels):
    pdf.setFont("Times-Roman", FONT_CAPTION)
    pdf.drawRightString(
        width - 50,
        25,
        f"{labels['page']} {pdf.getPageNumber()}"
    )

def draw_wrapped_text(pdf, text, x, y, max_width, font_name="Times-Roman", font_size=FONT_BODY, leading=15):
    pdf.setFont(font_name, font_size)
    text = str(text or "")
    prefix = ""
    body = text
    prefix_match = re.match(r"^(:\s+)(.*)$", text) or re.match(r"^([^:]{1,90}:\s+)(.+)$", text)
    if prefix_match:
        prefix = prefix_match.group(1)
        body = prefix_match.group(2)

    prefix_width = pdf.stringWidth(prefix, font_name, font_size) if prefix else 0
    text_x = x + prefix_width
    text_width = max_width - prefix_width if prefix else max_width
    continuation_width = text_width

    def split_oversized_word(word, available_width):
        if pdf.stringWidth(word, font_name, font_size) <= available_width:
            return [word]

        chunks = []
        current = ""
        for char in word:
            test = current + char
            if current and pdf.stringWidth(test, font_name, font_size) > available_width:
                chunks.append(current)
                current = char
            else:
                current = test
        if current:
            chunks.append(current)
        return chunks or [word]

    words = body.split()
    lines = []
    line = ""
    for word in words:
        test = line + " " + word if line else word
        if pdf.stringWidth(test, font_name, font_size) <= text_width:
            line = test
        else:
            if line:
                lines.append(line)
            chunks = split_oversized_word(word, continuation_width)
            lines.extend(chunks[:-1])
            line = chunks[-1]
    if line:
        lines.append(line)

    if not lines and prefix:
        pdf.drawString(x, y, prefix.rstrip())
        y -= leading

    for index, line in enumerate(lines):
        if prefix and index == 0:
            pdf.drawString(x, y, prefix + line)
        elif prefix:
            pdf.drawString(text_x, y, line)
        else:
            pdf.drawString(x, y, line)
        y -= leading

    return y

def draw_claim_amount_line(pdf, label, amount, x, y, max_width, font_name="Times-Roman", font_size=FONT_BODY, leading=15):
    pdf.setFont(font_name, font_size)
    label = str(label or "").strip()
    amount = str(amount or "").strip()
    label_with_space = f"{label} "
    label_width = pdf.stringWidth(label_with_space, font_name, font_size)
    amount_width = pdf.stringWidth(amount, font_name, font_size)

    if label_width + amount_width <= max_width:
        pdf.drawString(x, y, label_with_space)
        pdf.drawString(x + label_width, y, amount)
        return y - leading

    pdf.drawString(x, y, label)
    return draw_wrapped_text(
        pdf,
        amount,
        x + 20,
        y - leading,
        max_width - 20,
        font_name=font_name,
        font_size=font_size,
        leading=leading,
    )


def draw_form_value(pdf, value, x, y, max_width, font_name="Times-Roman", font_size=None, leading=14):
    """Draw a form value after ':' with wrapping and readable sizing."""
    return draw_wrapped_text(
        pdf,
        f": {str(value or '')}",
        x,
        y,
        max_width,
        font_name,
        font_size or FONT_BODY,
        leading,
    )

def _estimate_wrapped_lines_with_font(pdf, text, font_name, font_size, max_width):
    text = str(text or "")
    prefix_match = re.match(r"^(:\s+)(.*)$", text) or re.match(r"^([^:]{1,90}:\s+)(.+)$", text)
    if prefix_match:
        prefix_width = pdf.stringWidth(prefix_match.group(1), font_name, font_size)
        text = prefix_match.group(2)
        max_width = max_width - prefix_width

    words = text.split()
    if not words:
        return 1

    line = ""
    line_count = 0
    for word in words:
        candidate = f"{line} {word}" if line else word
        if pdf.stringWidth(candidate, font_name, font_size) <= max_width:
            line = candidate
        else:
            line_count += 1
            line = word
    if line:
        line_count += 1
    return max(line_count, 1)


def _build_project_dashboard_context(role, user_id):
    if role not in {"Developer", "Legal"}:
        return {
            "available_projects": [],
            "project_claimants_map": {},
            "selected_project_name": "",
            "selected_claimant_user_id": "",
            "homeowner_claimants": [],
        }

    available_projects = get_available_projects(user_id, role=role)
    is_main_developer = role == "Developer" and is_main_developer_account(user_id)
    # Force explicit selection in UI instead of auto-selecting the first project.
    selected_project_name = ""

    # Build allowed projects set (avoid recalculating in get_homeowner_claimants)
    allowed_project_names = {p.get("project_name", "").strip().lower() for p in available_projects}

    # BUILD PROJECT CLAIMANT MAP using project_name as key
    project_claimants_map = {}
    
    # Get all claimants first to avoid duplicates. Do NOT pass allowed_project_names
    # so we can place claimants whose project names don't match available_projects
    # into "Others / Unrelated" instead of excluding them entirely.
    all_claimants = get_homeowner_claimants(
        respondent_id=user_id,
        project_name=None,
        role=role,
        allowed_project_names=None if is_main_developer else allowed_project_names,
        include_unrestricted=role != "Developer" or is_main_developer,
    )
    
    # Track which claimants have been assigned to avoid duplicates
    assigned_claimant_ids = set()
    
    # Initialize project_claimants_map with ALL available projects (even if no claimants)
    for project in available_projects:
        project_name = project.get("project_name", "").strip()
        if project_name and project_name not in project_claimants_map:
            project_claimants_map[project_name] = []
    # Build a lookup for normalized project name -> actual key to handle
    # differences in casing/whitespace between available_projects and
    # report_homeowner_profile.project_name values.
    lower_name_to_key = {
        key.strip().lower(): key
        for key in project_claimants_map.keys()
    }
    
    # Group claimants by their project_name (primary project only).
    # For Developer role, only assign to projects that are in allowed_project_names
    # (i.e., available_projects). Others will remain unassigned and go under
    # "Others / Unrelated" so they are still visible.
    for claimant in all_claimants:
        project_name = claimant.get("project_name", "").strip()

        # Skip duplicates
        if claimant.get("homeowner_id") in assigned_claimant_ids:
            continue

        # Only assign if the project_name is a known available project (normalized)
        if project_name and project_name != "-":
            normalized = project_name.strip().lower()
            target_key = lower_name_to_key.get(normalized)
            if target_key:
                # For Developer, also ensure project is allowed
                if role == "Developer" and allowed_project_names is not None:
                    if normalized not in allowed_project_names:
                        # leave unassigned
                        continue

                project_claimants_map[target_key].append(claimant)
                assigned_claimant_ids.add(claimant.get("homeowner_id"))
    
    # Find claimants with unrelated/no unit and place in "Others / Unrelated"
    unassigned_claimants = [
        c for c in all_claimants
        if c.get("homeowner_id") not in assigned_claimant_ids
    ]

    if role != "Developer" or is_main_developer or unassigned_claimants:
        project_claimants_map["Others / Unrelated"] = unassigned_claimants

    # Format available_projects list with project_name as primary
    formatted_available_projects = [
        {
            "project_name": project_name
        }
        for project_name in project_claimants_map.keys()
    ]

    return {
        "available_projects": formatted_available_projects,
        "project_claimants_map": project_claimants_map,
        "selected_project_name": selected_project_name,
        "selected_claimant_user_id": "",
        "homeowner_claimants": all_claimants,
    }
    # Debugging aid: optionally dump the resolved data to a JSON file when
    # DEBUG_PROJECT_CLAIMANTS=1 is set in the environment.
    try:
        if os.getenv('DEBUG_PROJECT_CLAIMANTS') == '1':
            import json as _json
            dump = {
                'available_projects': formatted_available_projects,
                'project_claimants_map_keys': list(project_claimants_map.keys()),
                'homeowner_claimants_count': len(all_claimants),
                'homeowner_claimants_sample': all_claimants[:20],
            }
            with open(os.path.join(os.path.dirname(__file__), 'debug_project_claimants.json'), 'w', encoding='utf-8') as fh:
                fh.write(_json.dumps(dump, ensure_ascii=False, indent=2))
    except Exception:
        pass

def _resolve_report_scope(role, user_id, project_name="", claimant_user_id=None):
    resolved_project_name = (project_name or "").strip()

    if role == "Homeowner":
        return {
            "project_name": "",
            "claimant_user_id": user_id,
        }

    if role not in {"Developer", "Legal"}:
        return {"error": "Unauthorized role"}

    available_projects = get_available_projects(user_id, role=role)
    allowed_project_names = {
        (project.get("project_name") or "").strip().lower()
        for project in available_projects
        if (project.get("project_name") or "").strip()
    }

    if not resolved_project_name:
        return {"error": "Please choose a project before generating report."}

    if resolved_project_name and resolved_project_name.strip().lower() not in allowed_project_names:
        return {"error": "Selected project is not available for this account."}

    project_claimants = get_homeowner_claimants(
        user_id,
        project_name=resolved_project_name,
        role=role,
    ) if resolved_project_name else []

    project_claimant_ids = {claimant["homeowner_id"] for claimant in project_claimants}

    if claimant_user_id is None:
        return {"error": "Please choose a claimant before generating report."}
    elif claimant_user_id not in project_claimant_ids:
        return {"error": "Selected claimant does not belong to the selected project."}

    return {
        "project_name": resolved_project_name,
        "claimant_user_id": claimant_user_id,
        "available_projects": available_projects,
        "project_claimants": project_claimants,
    }


def _filter_defects_for_report_scope(defects, project_name="", claimant_user_id=None, include_project_peers=False):
    scoped_defects = list(defects or [])

    if claimant_user_id and not include_project_peers:
        scoped_defects = [
            d for d in scoped_defects
            if d.get("owner_id") == claimant_user_id
        ]

    if project_name:
        project_name_norm = str(project_name).strip().lower()
        scoped_defects = [
            d for d in scoped_defects
            if (d.get("project_name") or "").strip().lower() == project_name_norm
        ]

    return scoped_defects

@routes.route('/delete_defect/<int:defect_id>', methods=['POST'])
@login_required
def delete_defect(defect_id):

    if _current_role() != "Homeowner":
        return jsonify({
            "success": False,
            "error": "Unauthorized"
        }), 403

    user_id = _current_user_id()

    try:

        cleanup_summary = _delete_owned_defect(defect_id, user_id)

        if cleanup_summary is None:

            return jsonify({
                "success": False,
                "error": "Defect not found"
            }), 404

        try:
            _append_audit_event(
                action="Defect Deleted",
                role="Homeowner",
                details={
                    "defect_id": defect_id,
                    "cleanup": cleanup_summary,
                },
            )
        except Exception:
            pass

        # Lightweight server-side log for debugging delete responses
        try:
            _append_delete_defect_log({
                "timestamp": _now_app_timezone().isoformat(),
                "action": "delete_defect",
                "defect_id": defect_id,
                "user_id": user_id,
                "status": "deleted",
                "cleanup": cleanup_summary,
            })
        except Exception:
            pass

        return jsonify({
            "success": True
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@routes.route('/check-password-same', methods=['POST'])
@login_required
def check_password_same():

    try:

        data = request.get_json()

        password = (
            data.get('password') or ''
        ).strip()

        if not password:

            return jsonify({
                "same": False
            })

        user_id = _current_user_id()

        conn = get_connection()

        cur = conn.cursor()

        cur.execute(
            """
            SELECT password
            FROM login_accounts
            WHERE user_id = %s
            LIMIT 1
            """,
            (user_id,)
        )

        row = cur.fetchone()

        cur.close()
        conn.close()

        if not row:

            return jsonify({
                "same": False
            })

        current_password = row[0]

        # werkzeug hash check
        same = check_password_hash(
            current_password,
            password
        )

        return jsonify({
            "same": same
        })

    except Exception as e:

        print(
            "PASSWORD CHECK ERROR:",
            e
        )

        return jsonify({
            "same": False,
            "error": str(e)
        }), 500

# =================================================
# DASHBOARD ROUTE (THIS MAKES THE UI OPEN)
# =================================================
@routes.route("/")
@login_required
def dashboard():
    role = _current_role()
    auto_close_completed_cases(trigger_role=role)

    if role == "Admin":
        defects = get_defects_for_role("Admin")
        stats = calculate_stats(defects)
        system_health = calculate_system_health(stats)
        versions = load_versions()
        backup_manifest = load_backup_manifest()
        version_groups = []
        for version_role, version_items in versions.items():
            sorted_items = sorted(
                version_items,
                key=lambda item: (item.get("version") or 0, item.get("generated_at") or ""),
                reverse=True,
            )
            version_groups.append(
                {
                    "role": version_role,
                    "count": len(version_items),
                    "latest": sorted_items[0] if sorted_items else None,
                    "entries": sorted_items,
                }
            )
        version_groups.sort(key=lambda item: item["role"].lower())
        version_total = sum(group["count"] for group in version_groups)
        latest_version_count = version_groups[0]["count"] if version_groups else 0

        audit_role = (request.args.get("audit_role") or "").strip()
        audit_action = (request.args.get("audit_action") or "").strip()
        audit_date = (request.args.get("audit_date") or "").strip()

        try:
            audit_page = int(request.args.get("audit_page", "1"))
        except ValueError:
            audit_page = 1

        per_page = 15
        audit_entries, total_audit = get_audit_entries_paginated(
            page=audit_page,
            per_page=per_page,
            role_filter=audit_role,
            action_filter=audit_action,
            date_filter=audit_date,
        )

        total_pages = (total_audit + per_page - 1) // per_page if total_audit else 1
        if audit_page > total_pages:
            audit_page = total_pages
            audit_entries, total_audit = get_audit_entries_paginated(
                page=audit_page,
                per_page=per_page,
                role_filter=audit_role,
                action_filter=audit_action,
                date_filter=audit_date,
            )

        audit_start = 0 if total_audit == 0 else (audit_page - 1) * per_page + 1
        audit_end = min(audit_page * per_page, total_audit)
        audit_roles, audit_actions = get_audit_filter_options()

        return render_template(
            "dashboard_admin.html",
            role=role,
            stats=_sanitize_for_display(stats),
            defects=_sanitize_for_display(defects),
            audit_entries=_sanitize_for_display(audit_entries),
            total_audit=total_audit,
            audit_page=audit_page,
            total_pages=total_pages,
            per_page=per_page,
            audit_start=audit_start,
            audit_end=audit_end,
            audit_role=_sanitize_for_display(audit_role),
            audit_action=_sanitize_for_display(audit_action),
            audit_date=audit_date,
            audit_roles=_sanitize_for_display(audit_roles),
            audit_actions=_sanitize_for_display(audit_actions),
            version_groups=_sanitize_for_display(version_groups),
            version_total=version_total,
            latest_version_count=latest_version_count,
            backup_manifest=_sanitize_for_display(backup_manifest),
            system_health=_sanitize_for_display(system_health),
            username=session.get("username", "admin"),
            user_info=_sanitize_for_display(get_current_user()),
        )

    defects = get_defects_for_role(role)
    remarks_store = load_remarks()
    status_store = load_status()
    completion_store = load_completion_dates()
    evidence_store = load_evidence()
    evidence_store = load_evidence()

    for d in defects:
        # Status is shared across all roles
        d["status"] = status_store.get(str(d["id"]), d["status"])

        # ðŸ”¥ RESTORE COMPLETION DATE
        d["completed_date"] = completion_store.get(
            str(d["id"]),
            d.get("completed_date")
        )

        # Restore evidence info
        evidence_data = evidence_store.get(str(d["id"]))
        evidence_files = _evidence_items_from_meta(evidence_data)
        if evidence_files:
            d["evidence_uploaded"] = True
            d["evidence_files"] = evidence_files
            d["evidence_count"] = len(evidence_files)
            d["evidence_filename"] = evidence_files[0].get("filename")
            d["evidence_uploaded_at"] = evidence_data.get("uploaded_at") or evidence_files[-1].get("uploaded_at")
        else:
            d["evidence_uploaded"] = False
            d["evidence_files"] = []
            d["evidence_count"] = 0
            d["evidence_filename"] = None
            d["evidence_uploaded_at"] = None

        # Remarks are ONLY visible to Homeowner
        if role == "Homeowner":
            d["remarks"] = remarks_store.get(str(d["id"]), "")
        else:
            d["remarks"] = ""  # Hide remarks for Developer & Legal

    stats = calculate_stats(defects)
    claim_input = None
    if role in ["Homeowner", "Developer", "Legal"]:
        user_info = get_current_user()
        if role == "Homeowner":
            claim_input = get_homeowner_claim_details(_current_user_id())
        if role == "Legal":
            conn = get_connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT legal_name, phone_number, email, office_address
                    FROM report_legal_profile
                    WHERE legal_user_id = %s
                    """,
                    (_current_user_id(),),
                )
                row = cur.fetchone()
                avatar_url = None
                try:
                    cur.execute(
                        "SELECT avatar_url FROM users WHERE id = %s LIMIT 1",
                        (_current_user_id(),),
                    )
                    avatar_row = cur.fetchone()
                    avatar_url = avatar_row[0] if avatar_row and avatar_row[0] else None
                except Exception:
                    avatar_url = None
                if row:
                    user_info = {
                        "name": _decrypt_display_text(row[0]) or user_info["name"],
                        "company_name": _decrypt_display_text(row[0]) or user_info["name"],
                        "email": _decrypt_display_text(row[2]) or user_info.get("email", ""),
                        "phone_number": _decrypt_display_text(row[1]) or "",
                        "unit": "",
                        "avatar_url": avatar_url,
                    }
                else:
                    user_info["company_name"] = user_info["name"]
                    user_info["avatar_url"] = avatar_url
            finally:
                cur.close()
                conn.close()
        elif role == "Developer":
            conn = get_connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT company_name, person_in_charge, registration_number, phone_number, email, address
                    FROM report_respondent_profile
                    WHERE respondent_id = %s
                    """,
                    (_current_user_id(),),
                )
                row = cur.fetchone()
                avatar_url = None
                try:
                    cur.execute(
                        "SELECT avatar_url FROM users WHERE id = %s LIMIT 1",
                        (_current_user_id(),),
                    )
                    avatar_row = cur.fetchone()
                    avatar_url = avatar_row[0] if avatar_row and avatar_row[0] else None
                except Exception:
                    avatar_url = None
                if row:
                    user_info = {
                        "name": _decrypt_display_text(row[0]) or user_info["name"],
                        "company_name": _decrypt_display_text(row[0]) or user_info["name"],
                        "person_in_charge": _decrypt_display_text(row[1]) or None,
                        "email": _decrypt_display_text(row[4]) or user_info.get("email", ""),
                        "phone_number": _decrypt_display_text(row[3]) or "",
                        "office_address": _decrypt_display_text(row[5]) or None,
                        "unit": "",
                        "avatar_url": avatar_url,
                    }
                else:
                    user_info["company_name"] = user_info["name"]
                    user_info["avatar_url"] = avatar_url
            finally:
                cur.close()
                conn.close()
    else:
        user_info = {"name": session.get("username", role), "unit": ""}

    project_dashboard_context = _build_project_dashboard_context(role, _current_user_id())
    homeowner_claimants = project_dashboard_context["homeowner_claimants"]

    template = (
        "dashboard_homeowner.html"
        if role == "Homeowner"
        else "dashboard_developer.html"
        if role == "Developer"
        else "dashboard_legal.html"
    )

    return render_template(
        template,
        role=role,
        defects=_sanitize_for_display(defects),
        stats=_sanitize_for_display(stats),
        user_info=_sanitize_for_display(user_info),
        claim_input=_sanitize_for_display(claim_input),
        state_court_map=STATE_COURT_MAP,
        state_options=list(STATE_COURT_MAP.keys()),
        item_service_options=list(ITEM_SERVICE_TRANSLATIONS.keys()),
        homeowner_claimants=_sanitize_for_display(homeowner_claimants),
        available_projects=_sanitize_for_display(project_dashboard_context["available_projects"]),
        project_claimants_map=_sanitize_for_display(project_dashboard_context["project_claimants_map"]),
        selected_project_name=project_dashboard_context["selected_project_name"],
        selected_claimant_user_id=project_dashboard_context["selected_claimant_user_id"],
        username=session.get("username", ""),
        current_user_id=_current_user_id()
    )


@routes.route("/save_homeowner_claim_details", methods=["POST"])
@login_required
def save_homeowner_claim_details():
    if _current_role() != "Homeowner":
        return jsonify({"success": False, "error": "Only homeowner can update claim details."}), 403

    ensure_profile_encryption_at_rest()

    data = request.get_json(silent=True) or {}
    court_location = (data.get("court_location") or "").strip()
    state_name = (data.get("state_name") or "").strip()
    item_service = (data.get("item_service") or "").strip()
    transaction_date = (data.get("transaction_date") or "").strip()
    claim_amount = (data.get("claim_amount") or "").strip()

    if not court_location:
        return jsonify({"success": False, "error": "Court location is required."}), 400
    if not state_name:
        return jsonify({"success": False, "error": "State is required."}), 400
    if not transaction_date:
        return jsonify({"success": False, "error": "Transaction date is required."}), 400
    if not claim_amount:
        return jsonify({"success": False, "error": "Claim amount is required."}), 400

    if not item_service:
        item_service = _default_item_service()
    item_service = _normalise_item_service(item_service)

    allowed_courts = _get_court_locations_for_state(state_name)
    if not allowed_courts:
        return jsonify({"success": False, "error": "Please choose a valid state from the dropdown."}), 400
    if court_location not in allowed_courts:
        return jsonify({"success": False, "error": f"Court location must match the selected state: {', '.join(allowed_courts)}."}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        user_id = _current_user_id()
        cur.execute(
            "SELECT full_name, email, unit FROM users WHERE id = %s",
            (user_id,),
        )
        user_row = cur.fetchone()
        if not user_row:
            return jsonify({"success": False, "error": "User not found."}), 404

        cur.execute(
            "SELECT name FROM report_homeowner_profile WHERE homeowner_id = %s",
            (user_id,),
        )
        existing_profile = cur.fetchone()
        profile_name = None
        if existing_profile and existing_profile[0]:
            profile_name = _decrypt_display_text(existing_profile[0]).strip()
        if not profile_name:
            profile_name = (_decrypt_display_text(user_row[0]) or "").strip()

        plain_name = profile_name
        encrypted_email = encrypt_text(user_row[1] or "")
        encrypted_address = encrypt_text(user_row[2] or "")
        encrypted_court_location = encrypt_text(court_location)
        encrypted_state_name = encrypt_text(state_name)
        encrypted_item_service = encrypt_text(item_service)
        encrypted_transaction_date = encrypt_text(transaction_date)
        encrypted_claim_amount = encrypt_text(claim_amount)

        cur.execute(
            """
            INSERT INTO report_homeowner_profile (
                homeowner_id, name, email, address, court_location, state_name, item_service, transaction_date, claim_amount, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (homeowner_id) DO UPDATE
            SET name = EXCLUDED.name,
                email = EXCLUDED.email,
                address = EXCLUDED.address,
                court_location = EXCLUDED.court_location,
                state_name = EXCLUDED.state_name,
                item_service = EXCLUDED.item_service,
                transaction_date = EXCLUDED.transaction_date,
                claim_amount = EXCLUDED.claim_amount,
                updated_at = NOW()
            """,
            (
                user_id,
                plain_name,
                encrypted_email,
                encrypted_address,
                encrypted_court_location,
                encrypted_state_name,
                encrypted_item_service,
                encrypted_transaction_date,
                encrypted_claim_amount,
            ),
        )
        conn.commit()
        return jsonify({"success": True, "message": "Claim details saved."})
    finally:
        cur.close()
        conn.close()

# =================================================
# UPLOAD EVIDENCE IMAGE
# =================================================
@routes.route("/upload_evidence", methods=["POST"])
@login_required
def upload_evidence():
    """
    Upload evidence image for a specific defect.
    Images are stored in the evidence folder with naming: defect_{id}.jpg
    Only the uploader can see their uploaded images (privacy).
    """
    try:
        files = [
            file for file in request.files.getlist('file')
            if file and file.filename
        ]
        defect_id = request.form.get('defect_id')
        replace_index_raw = request.form.get('replace_index')
        replace_index = None
        
        if not defect_id:
            return jsonify({"error": "No defect ID provided"}), 400

        if replace_index_raw:
            try:
                replace_index = int(replace_index_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid replacement image index."}), 400
            if replace_index < 1 or replace_index > REQUIRED_EVIDENCE_IMAGE_COUNT:
                return jsonify({"error": "Invalid replacement image index."}), 400
        
        if replace_index:
            if len(files) < 1 or len(files) > REQUIRED_EVIDENCE_IMAGE_COUNT:
                return jsonify({"error": f"Please choose up to {REQUIRED_EVIDENCE_IMAGE_COUNT} replacement images."}), 400
        elif len(files) != REQUIRED_EVIDENCE_IMAGE_COUNT:
            return jsonify({"error": f"Please upload exactly {REQUIRED_EVIDENCE_IMAGE_COUNT} evidence images."}), 400
        
        for file in files:
            if not allowed_file(file.filename):
                return jsonify({
                    "error": "File type not allowed. Allowed types: jpg, jpeg, png, tif, tiff, jfif"
                }), 400

        # Create evidence directory if not exists
        evidence_dir = os.path.join(current_app.root_path, "evidence")
        os.makedirs(evidence_dir, exist_ok=True)

        # Save evidence metadata with timestamp
        now_local = _now_app_timezone()

        uploaded_at = now_local.strftime("%Y-%m-%d %H:%M:%S")

        if replace_index:
            evidence_img = load_evidence()
            existing_meta = evidence_img.get(str(defect_id)) or {}
            evidence_items = _evidence_items_from_meta(existing_meta)
            if len(evidence_items) < REQUIRED_EVIDENCE_IMAGE_COUNT:
                return jsonify({
                    "error": f"Existing evidence must have {REQUIRED_EVIDENCE_IMAGE_COUNT} images before replacing one image."
                }), 400

            replaced_indices = []
            for offset, file in enumerate(files):
                target_index = ((replace_index - 1 + offset) % REQUIRED_EVIDENCE_IMAGE_COUNT) + 1
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = f"defect_{defect_id}_{target_index}_{uuid.uuid4().hex[:8]}.{ext}"
                filepath = os.path.join(evidence_dir, filename)
                file.save(filepath)
                evidence_items[target_index - 1] = {
                    "filename": filename,
                    "uploaded_at": uploaded_at,
                }
                replaced_indices.append(target_index)
            evidence_img[str(defect_id)] = {
                "files": evidence_items,
                "filename": evidence_items[0]["filename"],
                "uploaded_at": uploaded_at,
            }
            save_evidence(evidence_img)

            _append_audit_event(
                action="Evidence Replaced",
                role=_current_role(),
                defect_id=defect_id,
                filename=", ".join(evidence_items[index - 1]["filename"] for index in replaced_indices),
                details={
                    "username": session.get("username", ""),
                    "defect_id": defect_id,
                    "filenames": [evidence_items[index - 1]["filename"] for index in replaced_indices],
                    "replace_indices": replaced_indices,
                    "uploaded_at": uploaded_at,
                },
            )

            return jsonify({
                "success": True,
                "message": f"Evidence replaced for defect #{defect_id}",
                "filename": evidence_items[0]["filename"],
                "files": evidence_items,
                "defect_id": defect_id,
                "uploaded_at": uploaded_at,
                "replace_indices": replaced_indices,
            })

        evidence_items = []
        for index, file in enumerate(files, 1):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"defect_{defect_id}_{index}.{ext}"
            filepath = os.path.join(evidence_dir, filename)
            file.save(filepath)
            evidence_items.append({
                "filename": filename,
                "uploaded_at": uploaded_at,
            })

        evidence_img = load_evidence()
        evidence_img[defect_id] = {
            "files": evidence_items,
            "filename": evidence_items[0]["filename"],
            "uploaded_at": uploaded_at,
        }
        save_evidence(evidence_img)

        # AUDIT LOG - EVIDENCE UPLOADED
        _append_audit_event(
            action="Evidence Uploaded",
            role=_current_role(),
            defect_id=defect_id,
            filename=", ".join(item["filename"] for item in evidence_items),
            details={
                "username": session.get("username", ""),
                "defect_id": defect_id,
                "filenames": [item["filename"] for item in evidence_items],
                "uploaded_at": uploaded_at,
            },
        )

        return jsonify({
            "success": True,
            "message": f"Evidence uploaded for defect #{defect_id}",
            "filename": evidence_items[0]["filename"],
            "files": evidence_items,
            "defect_id": defect_id,
            "uploaded_at": uploaded_at,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def get_closed_evidence_appendix(role, claimant_unit=None, project_name=None):
    """Return closed defects for role appendix view."""
    if role not in ["Homeowner", "Developer", "Legal", "Admin"]:
        return {
            "role": role,
            "claimant_unit": claimant_unit or "",
            "project_name": project_name or "",
            "claimant_rows": [],
            "other_rows": [],
            "all_rows": [],
        }

    # Developer and Legal reports are project scoped, so Appendix A groups all
    # closed defects in the selected project by claimant vs other owners.
    defects = get_defects_for_role(role)
    status_store = load_status()
    completion_store = load_completion_dates()
    evidence_store = load_evidence()
    selected_project_name = str(project_name or "").strip().lower()
    include_other_owners = role in ["Developer", "Legal"]

    appendix_rows = []
    for d in defects:
        defect_id = str(d.get("id"))
        status = status_store.get(defect_id, d.get("status"))
        completed_date = completion_store.get(defect_id, d.get("completed_date"))
        evidence = evidence_store.get(defect_id) or {}
        evidence_files = _evidence_items_from_meta(evidence)
        first_evidence = evidence_files[0] if evidence_files else {}

        if not is_auto_closed(status, completed_date):
            continue

        row_project_name = (d.get("project_name") or "").strip().lower()
        if selected_project_name and row_project_name != selected_project_name:
            continue

        appendix_rows.append(
            {
                "id": d.get("id"),
                "unit": d.get("unit", "-"),
                "status": "Closed",
                "reported_date": d.get("reported_date") or "-",
                "completed_date": completed_date or "-",
                "hda_compliant": calculate_hda_compliance(d.get("reported_date"), completed_date, status),
                "filename": first_evidence.get("filename") or evidence.get("filename", "-"),
                "evidence_files": evidence_files,
                "uploaded_at": evidence.get("uploaded_at") or first_evidence.get("uploaded_at", "-"),
            }
        )

    appendix_rows.sort(key=lambda item: int(item["id"]) if str(item.get("id", "")).isdigit() else 0)

    claimant_rows = []
    other_rows = []
    other_owner_units = []

    if include_other_owners and project_name:
        try:
            project_claimants = get_homeowner_claimants(
                _current_user_id(),
                project_name=project_name,
                role=role,
            )
            claimant_unit_norm = _normalise_unit_for_grouping(claimant_unit)
            seen_units = set()
            for claimant in project_claimants:
                owner_unit = (claimant.get("unit") or "").strip()
                owner_unit_norm = _normalise_unit_for_grouping(owner_unit)
                if not owner_unit or not owner_unit_norm or owner_unit_norm == claimant_unit_norm:
                    continue
                if owner_unit_norm in seen_units:
                    continue
                seen_units.add(owner_unit_norm)
                other_owner_units.append(owner_unit)
        except Exception:
            other_owner_units = []

    for row in appendix_rows:
        row_unit = row.get("unit", "")
        if claimant_unit and _units_match_for_closed_appendix(row_unit, claimant_unit):
            claimant_rows.append(row)
        elif include_other_owners:
            other_rows.append(row)
            row_unit_norm = _normalise_unit_for_grouping(row_unit)
            if row_unit and row_unit_norm and all(
                _normalise_unit_for_grouping(unit) != row_unit_norm
                for unit in other_owner_units
            ):
                other_owner_units.append(row_unit)

    return {
        "role": role,
        "claimant_unit": claimant_unit or "",
        "project_name": project_name or "",
        "claimant_rows": claimant_rows,
        "other_rows": other_rows,
        "other_owner_units": other_owner_units,
        "all_rows": appendix_rows,
    }


def build_closed_appendix_lines(closed_evidence_appendix, language):
    """Build a consistent closed-case appendix text block for all roles."""
    detail_indent = "   "
    claimant_unit = closed_evidence_appendix.get("claimant_unit", "") if isinstance(closed_evidence_appendix, dict) else ""
    claimant_rows = closed_evidence_appendix.get("claimant_rows", []) if isinstance(closed_evidence_appendix, dict) else []
    other_rows = closed_evidence_appendix.get("other_rows", []) if isinstance(closed_evidence_appendix, dict) else []
    other_owner_units = closed_evidence_appendix.get("other_owner_units", []) if isinstance(closed_evidence_appendix, dict) else []
    role = closed_evidence_appendix.get("role", "") if isinstance(closed_evidence_appendix, dict) else ""
    show_other_owner_details = role in ["Developer", "Legal"]

    if language == "ms":
        appendix_lines = [
            "",
            "LAMPIRAN A: BUTIRAN KES DITUTUP",
            "Kes ditutup dikecualikan daripada badan laporan utama dan disenaraikan di sini untuk rujukan sahaja.",
            "",
            "Rekod Kes Ditutup Pemilik Menuntut:",
            f"{detail_indent}Unit Pemilik Menuntut: {claimant_unit or 'Tiada unit pemilik menuntut direkodkan.'}",
            "",
            "Senarai Kecacatan Pemilik Menuntut:",
        ]
        no_records = f"{detail_indent}Tiada rekod kes ditutup yang tersedia pada masa ini."
        other_details = "Rekod Kes Ditutup Pemilik Lain"
        other_unit_label = "Unit Pemilik Lain"
        other_section = "Senarai Kecacatan Pemilik Lain"
    else:
        appendix_lines = [
            "",
            "APPENDIX A: CLOSED CASE DETAILS",
            "Closed cases are excluded from the main report body and listed here for reference only.",
            "",
            "Claimant Owner Closed Case Records:",
            f"{detail_indent}Claimant Owner Unit: {claimant_unit or 'No claimant owner unit recorded.'}",
            "",
            "Claimant Owner Defect List:",
        ]
        no_records = f"{detail_indent}No closed case records are currently available."
        other_details = "Other Owner Closed Case Records"
        other_unit_label = "Other Owner Unit"
        other_section = "Other Owner Defect List"

    if not claimant_rows and not other_rows:
        appendix_lines.append(no_records)
        if show_other_owner_details:
            appendix_lines.extend(["", f"{other_details}:"])
            if other_owner_units:
                for owner_unit in other_owner_units:
                    appendix_lines.extend([
                        f"{detail_indent}{other_unit_label}: {owner_unit}",
                        f"{other_section}:",
                        no_records,
                        "",
                    ])
            else:
                appendix_lines.extend([
                    f"{detail_indent}{other_unit_label}: {'Tiada unit pemilik lain direkodkan.' if language == 'ms' else 'No other owner unit recorded.'}",
                    f"{other_section}:",
                    no_records,
                ])
        return appendix_lines

    if claimant_rows:
        appendix_lines.append("")
        for idx, item in enumerate(claimant_rows, 1):
            if idx > 1:
                appendix_lines.append("")
            header_prefix = f"{chr(64 + idx)}." if idx <= 26 else f"{idx}."

            if language == "ms":
                appendix_lines.append(f"{header_prefix} Kecacatan ID {item.get('id', '-')}:" )
            else:
                appendix_lines.append(f"{header_prefix} Defect ID {item.get('id', '-')}:" )
            _append_closed_case_summary_lines(appendix_lines, item, language)

            appendix_lines.append("")
    else:
        appendix_lines.append(no_records)

    if show_other_owner_details:
        appendix_lines.extend(["", f"{other_details}:"])
        rows_by_unit = {}
        for item in other_rows:
            unit_key = _normalise_unit_for_grouping(item.get("unit", "")) or str(item.get("unit", "")).strip()
            rows_by_unit.setdefault(unit_key, []).append(item)

        owner_units = list(other_owner_units)
        for item in other_rows:
            item_unit = (item.get("unit") or "-").strip()
            item_unit_norm = _normalise_unit_for_grouping(item_unit)
            if item_unit_norm and all(_normalise_unit_for_grouping(unit) != item_unit_norm for unit in owner_units):
                owner_units.append(item_unit)

        if not owner_units:
            owner_units = ["Tiada unit pemilik lain direkodkan." if language == "ms" else "No other owner unit recorded."]

        for owner_unit in owner_units:
            owner_unit_norm = _normalise_unit_for_grouping(owner_unit) or str(owner_unit or "").strip()
            unit_rows = rows_by_unit.get(owner_unit_norm, [])
            appendix_lines.extend([
                f"{detail_indent}{other_unit_label}: {owner_unit}",
                "",
                f"{other_section}:",
            ])

            if not unit_rows:
                appendix_lines.extend([no_records, ""])
                continue

            for idx, item in enumerate(unit_rows, 1):
                if idx > 1:
                    appendix_lines.append("")
                header_prefix = f"{chr(64 + idx)}." if idx <= 26 else f"{idx}."

                if language == "ms":
                    appendix_lines.append(f"{header_prefix} Kecacatan ID {item.get('id', '-')}:" )
                else:
                    appendix_lines.append(f"{header_prefix} Defect ID {item.get('id', '-')}:" )
                _append_closed_case_summary_lines(appendix_lines, item, language)

                appendix_lines.append("")

    return appendix_lines


# =================================================
# CHECK IF EVIDENCE EXISTS
# =================================================
@routes.route("/evidence_exists/<defect_id>")
@login_required
def evidence_exists(defect_id):
    """Check if evidence image exists for a defect."""
    evidence_dir = os.path.join(current_app.root_path, "evidence")

    for ext in ALLOWED_EXTENSIONS:
        for filename in (f"defect_{defect_id}.{ext}", f"defect_{defect_id}_1.{ext}"):
            filepath = os.path.join(evidence_dir, filename)
            if os.path.exists(filepath):
                return jsonify({"exists": True, "defect_id": defect_id})

    return jsonify({"exists": False, "defect_id": defect_id})


# =================================================
# SERVE EVIDENCE IMAGE
# =================================================
@routes.route('/evidence_image/<defect_id>')
@login_required
def evidence_image(defect_id):
    """Serve the evidence image file for a defect (secure path resolution)."""
    evidence_dir = os.path.join(current_app.root_path, 'evidence')
    # Load metadata to get original filename if present
    try:
        evidence_store = load_evidence()
    except Exception:
        evidence_store = {}

    evidence_meta = evidence_store.get(str(defect_id)) or {}
    evidence_items = _evidence_items_from_meta(evidence_meta)
    requested_index = request.args.get("index", "1")
    try:
        requested_index = max(int(requested_index), 1)
    except Exception:
        requested_index = 1
    filename = ""
    if evidence_items and requested_index <= len(evidence_items):
        filename = evidence_items[requested_index - 1].get("filename")
    if not filename:
        filename = evidence_meta.get('filename')
    image_path = _resolve_evidence_image_path(evidence_dir, defect_id, filename)
    if not image_path or not os.path.isfile(image_path):
        return abort(404)

    # Serve the file (conditional file serving supported)
    return send_file(image_path, conditional=True)

# =================================================
# GENERATE AI REPORT (JSON)
# =================================================
@routes.route("/generate_ai_report", methods=["POST"])
@login_required
def generate_ai_report_api():
    try:
        data = request.get_json(silent=True) or {}
        role = _current_role()
        auto_close_completed_cases(trigger_role=role)
        # ðŸ”’ Enforce backend role validation
        if role not in ["Homeowner", "Developer", "Legal"]:
            return jsonify({"error": "Unauthorized role"}), 403
        language = _normalise_language(data.get("language", "ms"))
        project_name = (data.get("project_name") or "").strip()
        claimant_user_id = data.get("claimant_user_id")
        claimant_user_id = int(claimant_user_id) if str(claimant_user_id or "").strip().isdigit() else None
        resolved_scope = _resolve_report_scope(role, _current_user_id(), project_name, claimant_user_id)
        if resolved_scope.get("error"):
            return jsonify({"error": resolved_scope["error"]}), 400

        project_name = resolved_scope.get("project_name", "")
        claimant_user_id = resolved_scope.get("claimant_user_id")

        # Enforce evidence presence for defects included in the report scope
        try:
            defects = get_defects_for_role(role)
        except Exception:
            defects = []

        defects = _filter_defects_for_report_scope(
            defects,
            project_name=project_name,
            claimant_user_id=claimant_user_id,
            include_project_peers=role in ["Developer", "Legal"],
        )

        missing_evidence = []
        for d in defects:
            closed = d.get("closed") if "closed" in d else is_auto_closed(d.get("status"), d.get("completed_date"))
            if closed:
                continue
            evidence_count = int(d.get("evidence_count") or len(d.get("evidence_files") or []))
            if evidence_count < REQUIRED_EVIDENCE_IMAGE_COUNT:
                missing_evidence.append({
                    "id": d.get("id"),
                    "unit": d.get("unit"),
                    "evidence_count": evidence_count,
                    "required_count": REQUIRED_EVIDENCE_IMAGE_COUNT,
                })

        if missing_evidence:
            return jsonify({
                "error": "Cannot generate report: some defects are missing required evidence images.",
                "missing_evidence": missing_evidence,
            }), 400

        report_gap_report = detect_missing_report_values(
            role=role,
            user_id=_current_user_id(),
            claimant_user_id=claimant_user_id,
        )
        requirement_errors = report_gap_report["messages"]
        if report_gap_report["has_missing"]:
            return jsonify(
                {
                    "error": "Cannot generate report. Required profile/case data is incomplete.",
                    "details": requirement_errors,
                    "missing_data": report_gap_report["missing"],
                }
            ), 400

        closed_evidence_appendix = get_closed_evidence_appendix(
            role,
            claimant_unit=_get_user_unit(claimant_user_id or _current_user_id()),
            project_name=project_name,
        )

        defects = get_defects_for_role(role)
        remarks_store = load_remarks()
        status_store = load_status()
        completion_store = load_completion_dates()
        evidence_store = load_evidence()

        # LOAD LATEST STATUS + CALCULATE
        for d in defects:
            d["status"] = status_store.get(str(d["id"]), d["status"])
            d["completed_date"] = completion_store.get(
                str(d["id"]),
                d.get("completed_date")
            )
            d["closed"] = is_auto_closed(d["status"], d.get("completed_date"))
            d["display_status"] = "Closed" if d["closed"] else d["status"]
            evidence_data = evidence_store.get(str(d["id"]))
            evidence_files = _evidence_items_from_meta(evidence_data)
            if evidence_files:
                d["evidence_uploaded"] = True
                d["evidence_files"] = evidence_files
                d["evidence_count"] = len(evidence_files)
                d["evidence_filename"] = evidence_files[0].get("filename")
                d["evidence_uploaded_at"] = evidence_data.get("uploaded_at") or evidence_files[-1].get("uploaded_at")
            else:
                d["evidence_uploaded"] = False
                d["evidence_files"] = []
                d["evidence_count"] = 0
                d["evidence_filename"] = None
                d["evidence_uploaded_at"] = None
            d["remarks"] = remarks_store.get(str(d["id"]), "")  # optional
            d["hda_compliant"] = calculate_hda_compliance(
                d.get("reported_date"),
                d.get("completed_date"),
                d.get("status")
            )

            d["is_overdue"] = calculate_overdue(
                d.get("deadline"),
                d.get("completed_date"),
                d.get("status")
            )
            # NORMALISE urgency â†’ priority (BEFORE translate)
            if "urgency" in d and not d.get("priority"):
                d["priority"] = d["urgency"]

        defects = _filter_defects_for_report_scope(
            defects,
            project_name=project_name,
            claimant_user_id=claimant_user_id,
            include_project_peers=role in ["Developer", "Legal"],
        )

        # Keep statistics based on the selected report scope, including closed items.
        defects_for_stats = [dict(item) for item in defects]

        # Validate: Check if there are any defects at all
        if not defects_for_stats:
            return jsonify({
                "error": "No defects available to generate report",
                "details": "Please add defects before generating a report."
            }), 400

        defects = [d for d in defects if not d.get("closed")]
        
        # Validate: Check for required fields in defects
        defect_gap_report = detect_missing_report_values(
            role=role,
            user_id=_current_user_id(),
            claimant_user_id=claimant_user_id,
            defects=defects,
        )
        missing_fields = defect_gap_report["messages"]
        
        if missing_fields:
            return jsonify({
                "error": "Missing required data in defects",
                "details": missing_fields,
                "missing_data": defect_gap_report["missing"],
            }), 400

        for d in defects_for_stats:
            if d.get("status") in STATUS_NORMALISE:
                d["status"] = STATUS_NORMALISE[d["status"]]
                
        # ==========================
        # VALIDATE DEFECT DATA
        # ==========================
        validation_errors = []

        for d in defects:
            if not d.get("reported_date"):
                validation_errors.append(f"Defect {d['id']} missing reported date")

            if not d.get("deadline"):
                validation_errors.append(f"Defect {d['id']} missing deadline")

            if d.get("status") == "Completed" and not d.get("completed_date"):
                validation_errors.append(f"Defect {d['id']} marked Completed but missing completion date")

        if validation_errors:
            return jsonify({
                "error": "Incomplete defect data",
                "details": validation_errors
            }), 400

        # AI TRANSLATION (CACHE FOLLOW ROLE)
        # This translates 'desc', 'remarks', 'priority'
        defects = translate_defects_cached(
            defects,
            language=language,
            role=role
        )

        # TRANSLATE STATUS for AI prompt display
        for d in defects:
            if d["status"] in STATUS_NORMALISE:
                d["status"] = STATUS_NORMALISE[d["status"]]

        profile_snapshot_data = build_report_data(
            role,
            [],
            calculate_stats([]),
            user_id=_current_user_id(),
            claimant_user_id=claimant_user_id,
            forced_claim_number="-",
        )

        # Reuse previously generated report when the source defect snapshot is unchanged.
        snapshot_payload = {
            "report_format_version": 8,
            "role": role,
            "language": language,
            "project_name": project_name,
            "profile": {
                "case_info": {
                    key: profile_snapshot_data.get("case_info", {}).get(key)
                    for key in (
                        "tribunal_location",
                        "claim_amount",
                        "item_service",
                        "transaction_date",
                        "state_name",
                    )
                },
                "claimant": profile_snapshot_data.get("claimant", {}),
                "respondent": profile_snapshot_data.get("respondent", {}),
            },
            "appendix_schema_version": 4 if role in ["Homeowner", "Developer", "Legal", "Admin"] else 1,
            "defects": [
                {
                    "id": d.get("id"),
                    "unit": d.get("unit"),
                    "desc": d.get("desc"),
                    "status": d.get("status"),
                    "reported_date": d.get("reported_date"),
                    "deadline": d.get("deadline"),
                    "completed_date": d.get("completed_date"),
                    "remarks": d.get("remarks"),
                    "urgency": d.get("urgency"),
                }
                for d in defects
            ],
            "closed_evidence_appendix": [
                {
                    "id": item.get("id"),
                    "filename": item.get("filename"),
                    "evidence_files": _closed_appendix_evidence_items(item),
                    "uploaded_at": item.get("uploaded_at"),
                    "completed_date": item.get("completed_date"),
                }
                for item in _closed_appendix_snapshot_rows(closed_evidence_appendix)
            ] if role in ["Homeowner", "Developer", "Legal", "Admin"] else [],
        }
        data_hash = hashlib.sha256(
            json.dumps(snapshot_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT details
                FROM audit_log
                WHERE action = 'AI Report Generated'
                  AND role = %s
                  AND details->>'language' = %s
                  AND details->>'data_hash' = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (role, language, data_hash),
            )
            existing = cur.fetchone()

            if existing and existing[0]:
                details = existing[0]
                cached_version = int(details.get("version", 0))
                if cached_version > 0:
                    cur.execute(
                        """
                        SELECT report_text
                        FROM report_versions
                        WHERE role = %s AND version_no = %s AND language = %s
                        LIMIT 1
                        """,
                        (role, cached_version, language),
                    )
                    cached_row = cur.fetchone()
                    if cached_row and cached_row[0]:
                        # Even for cached narrative, rebuild case metadata so claim reference
                        # follows the current backend serial strategy.
                        cached_stats = calculate_stats(defects_for_stats)
                        cached_case_key = build_case_key(
                            role=role,
                            user_id=claimant_user_id or _current_user_id(),
                            defects=defects,
                        )
                        cached_report_data = build_report_data(
                            role,
                            defects,
                            cached_stats,
                            user_id=_current_user_id(),
                            case_key=cached_case_key,
                            claimant_user_id=claimant_user_id,
                        )

                        report_text = enforce_closed_appendix_format(
                            cached_row[0],
                            closed_evidence_appendix,
                            language,
                        )
                        cached_case_info = cached_report_data.get("case_info", {})
                        report_text = enforce_case_background_section(
                            report_text,
                            language,
                            cached_case_info.get("claim_id"),
                            cached_case_info.get("claim_amount"),
                            cached_stats.get("total", len(defects_for_stats)),
                        )
                        report_text = _strip_opposite_language_report(report_text, language)
                        report_text = refresh_generated_datetime_line(report_text, language)
                        report_text = normalize_report_section_spacing(report_text)
                        report_text = normalize_legal_statistics_section(report_text)
                        if role == "Legal":
                            report_text = enforce_legal_statistics_section_counts(
                                report_text,
                                language,
                                cached_report_data.get("summary_stats", {}),
                            )
                        report_text = remove_english_tribunal_title_after_subtitle(report_text, language)
                        report_text = normalize_priority_values_for_language(report_text, language)
                        report_text = normalize_report_date_values(report_text, language)
                        report_text = normalize_defect_detail_indentation(report_text)
                        report_text = _sanitize_encrypted_fragments(report_text)
                        # Ensure AI disclaimer heading uses the requested language for cached reports
                        try:
                            lang_conf = get_language_config(language)
                            localized_disclaimer = lang_conf.get("disclaimer_title") or lang_conf.get("ai_title") or "PENAFIAN AI:"
                            # Normalize to single trailing colon and ensure newline after heading
                            localized_disclaimer = localized_disclaimer.rstrip(':') + ':'
                            if not localized_disclaimer.endswith('\n'):
                                localized_disclaimer = localized_disclaimer + '\n'
                            # Match 'AI DISCLAIMER' with any number of trailing colons/spaces and replace
                            report_text = re.sub(r"AI\s*DISCLAIMER[:\s]*", localized_disclaimer, report_text, flags=re.IGNORECASE)
                            report_text = re.sub(r"AI\s*Disclaimer[:\s]*", localized_disclaimer, report_text, flags=re.IGNORECASE)
                            report_text = normalize_report_section_spacing(report_text)
                        except Exception:
                            pass

                        return jsonify({
                            "generated_at": _format_display_timestamp(_now_app_timezone().strftime("%Y-%m-%d %H:%M:%S"), language),
                            "role": role,
                            "language": language,
                            "report": report_text
                        })
        finally:
            cur.close()
            conn.close()

        # BUILD REPORT
        stats = calculate_stats(defects_for_stats)
        case_key = build_case_key(role=role, user_id=claimant_user_id or _current_user_id(), defects=defects)
        report_data = build_report_data(
            role,
            defects,
            stats,
            user_id=_current_user_id(),
            case_key=case_key,
            claimant_user_id=claimant_user_id,
        )

        # Keep boolean-like fields aligned with selected language before prompting AI.
        for item in report_data.get("defect_list", []):
            overdue_value = str(item.get("overdue", "")).strip().lower()
            hda_value = str(item.get("hda_compliance_30_days", "")).strip().lower()

            if language == "ms":
                item["overdue"] = "Tertunggak" if overdue_value in {"yes", "ya", "overdue", "tertunggak"} else "Tidak Tertunggak"
                item["hda_compliance_30_days"] = (
                    "Mematuhi"
                    if hda_value in {"yes", "ya", "mematuhi", "compliant"}
                    else "Tidak Mematuhi"
                )
            else:
                item["overdue"] = "Overdue" if overdue_value in {"yes", "ya", "overdue", "tertunggak"} else "Not Overdue"
                item["hda_compliance_30_days"] = (
                    "Compliant"
                    if hda_value in {"yes", "ya", "mematuhi", "compliant"}
                    else "Non-Compliant"
                )

        report_data.setdefault("case_info", {})["item_service"] = _item_service_for_language(
            report_data.get("case_info", {}).get("item_service"),
            language,
        )

        report = generate_ai_report(role, report_data, language)
        # Prepend consistent header for English reports so saved versions match PDF/preview
        try:
            lang_conf = get_language_config(language)
            ai_title = lang_conf.get("ai_title") or ("AI-GENERATED CLAIM SUMMARY REPORT" if language == "en" else "LAPORAN RINGKASAN TUNTUTAN DIJANA AI")
            pdf_labels = PDF_LABELS.get(language, PDF_LABELS["ms"])
            report_title = _report_title_for_role(pdf_labels, role)
            generated_label = lang_conf.get("generated_label") or ("Generated Date" if language == "en" else "Tarikh Jana")
            subtitle = _report_subtitle_for_role(pdf_labels, role)

            header_dt = _format_display_timestamp(_now_app_timezone().strftime("%Y-%m-%d %H:%M:%S"), language)
            header = f"{ai_title}\n\n{report_title}\n{generated_label}: {header_dt}\n\n{subtitle}\n\n"

            # Only insert header for English outputs or when missing
            if language == 'en' and not report.lstrip().lower().startswith(ai_title.lower()):
                report = header + report
        except Exception:
            pass

        versions = load_versions()
        role_versions = versions.get(role, [])
        new_version_number = len(role_versions)

        # FORCE STATUS LANGUAGE IN AI PREVIEW (REGEX SAFE)
        if language == "ms":
            report = re.sub(
                r"(Current Status|Status Semasa|Status)\s*:\s*Completed",
                "Status Semasa: Telah Diselesaikan",
                report,
                flags=re.IGNORECASE
            )
            report = re.sub(
                r"(Current Status|Status Semasa|Status)\s*:\s*Pending",
                "Status Semasa: Belum Diselesaikan",
                report,
                flags=re.IGNORECASE
            )
            report = re.sub(
                r"(Current Status|Status Semasa|Status)\s*:\s*In Progress",
                "Status Semasa: Dalam Tindakan",
                report,
                flags=re.IGNORECASE
            )
            report = re.sub(
                r"(Current Status|Status Semasa|Status)\s*:\s*Delayed",
                "Status Semasa: Tertangguh",
                report,
                flags=re.IGNORECASE
            )

            # Force overdue + HDA boolean wording to Bahasa Malaysia.
            report = re.sub(
                r"^\s*(Overdue Status|Status Tertunggak)\s*:\s*(Yes|Ya|Overdue|Tertunggak)\s*$",
                "Status Tertunggak: Tertunggak",
                report,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            report = re.sub(
                r"^\s*(Overdue Status|Status Tertunggak)\s*:\s*(No|Tidak|Not Overdue|Tidak Tertunggak)\s*$",
                "Status Tertunggak: Tidak Tertunggak",
                report,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            report = re.sub(
                r"^\s*(HDA Compliance \(30 Days\)|HDA Compliance Status|Pematuhan HDA \(30 Hari\)|Status Pematuhan HDA)\s*:\s*(Yes|Ya|Compliant|Mematuhi)\s*$",
                "   Status Pematuhan HDA: Mematuhi",
                report,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            report = re.sub(
                r"^\s*(HDA Compliance \(30 Days\)|HDA Compliance Status|Pematuhan HDA \(30 Hari\)|Status Pematuhan HDA)\s*:\s*(Tidak Mematuhi|Non-Compliant|No|Tidak)\s*$",
                "   Status Pematuhan HDA: Tidak Mematuhi",
                report,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            report = re.sub(
                r"^\s*(HDA Compliance \(30 Days\)|HDA Compliance Status|Pematuhan HDA \(30 Hari\)|Status Pematuhan HDA)\s*:\s*(Under Review|Dalam Semakan)\s*$",
                "   Status Pematuhan HDA: Tidak Mematuhi",
                report,
                flags=re.IGNORECASE | re.MULTILINE,
            )
        else:
            # Force overdue + HDA boolean wording to English.
            report = re.sub(
                r"^\s*(Overdue Status|Status Tertunggak)\s*:\s*(Ya|Yes|Tertunggak|Overdue)\s*$",
                "   Overdue Status: Overdue",
                report,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            report = re.sub(
                r"^\s*(Overdue Status|Status Tertunggak)\s*:\s*(Tidak|No|Tidak Tertunggak|Not Overdue)\s*$",
                "   Overdue Status: Not Overdue",
                report,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            report = re.sub(
                r"^\s*(HDA Compliance \(30 Days\)|HDA Compliance Status|Pematuhan HDA \(30 Hari\)|Status Pematuhan HDA)\s*:\s*(Ya|Yes|Mematuhi|Compliant)\s*$",
                "   HDA Compliance Status: Compliant",
                report,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            report = re.sub(
                r"^\s*(HDA Compliance \(30 Days\)|HDA Compliance Status|Pematuhan HDA \(30 Hari\)|Status Pematuhan HDA)\s*:\s*(Tidak Mematuhi|Non-Compliant|Tidak|No)\s*$",
                "   HDA Compliance Status: Non-Compliant",
                report,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            report = re.sub(
                r"^\s*(HDA Compliance \(30 Days\)|HDA Compliance Status|Pematuhan HDA \(30 Hari\)|Status Pematuhan HDA)\s*:\s*(Dalam Semakan|Under Review)\s*$",
                "   HDA Compliance Status: Non-Compliant",
                report,
                flags=re.IGNORECASE | re.MULTILINE,
            )

        # PREPARE CORRECT CLAIM SUMMARY (BACKEND)
        summary = report_data.get("summary_stats", {})

        total_defects = summary.get("total_defects", 0)
        pending_count = summary.get("pending_defects", 0)
        completed_count = summary.get("completed_defects", 0)

        if language == "en":
            correct_summary = (
                "Claim Summary:\n"
                f"Total Defects Reported: {total_defects}\n"
                f"Pending: {pending_count}\n"
                f"Completed: {completed_count}"
            )
        else:
            correct_summary = (
                "Ringkasan Tuntutan:\n"
                f"Jumlah Kecacatan Dilaporkan: {total_defects}\n"
                f"Belum Diselesaikan: {pending_count}\n"
                f"Telah Diselesaikan: {completed_count}"
            )

        # import re
        # Replace ONLY the Claim Summary section in AI text
        report = re.sub(
            r"(Claim Summary:.*?)(?=\n[A-Z]|\Z)",
            correct_summary + "\n",
            report,
            flags=re.DOTALL
        )

        report = re.sub(
            r"(Ringkasan Tuntutan:.*?)(?=\n[A-Z]|\Z)",
            correct_summary + "\n",
            report,
            flags=re.DOTALL
        )

        # Keep section 1 (Case Background) aligned with backend/PDF values.
        case_info = report_data.get("case_info", {})
        report = enforce_case_background_section(
            report,
            language,
            case_info.get("claim_id"),
            case_info.get("claim_amount"),
            total_defects,
        )

        if role in ["Homeowner", "Developer", "Legal", "Admin"]:
            report = enforce_closed_appendix_format(report, closed_evidence_appendix, language)

        report = _strip_opposite_language_report(report, language)
        report = refresh_generated_datetime_line(report, language)
        report = normalize_report_section_spacing(report)
        report = normalize_legal_statistics_section(report)
        if role == "Legal":
            report = enforce_legal_statistics_section_counts(
                report,
                language,
                report_data.get("summary_stats", {}),
            )
        report = remove_english_tribunal_title_after_subtitle(report, language)
        report = normalize_priority_values_for_language(report, language)
        report = normalize_report_date_values(report, language)
        report = normalize_defect_detail_indentation(report)
        report = _sanitize_encrypted_fragments(report)

        # Ensure AI disclaimer heading uses the requested language (force replacement of English variants)
        try:
            lang_conf = get_language_config(language)
            localized_disclaimer = lang_conf.get("disclaimer_title") or lang_conf.get("ai_title") or "PENAFIAN AI:"
            # Normalize to a single trailing colon and ensure newline after heading
            localized_disclaimer = localized_disclaimer.rstrip(':') + ':'
            if not localized_disclaimer.endswith('\n'):
                localized_disclaimer = localized_disclaimer + '\n'
            # Match 'AI DISCLAIMER' with any number of trailing colons/spaces and replace
            report = re.sub(r"AI\s*DISCLAIMER[:\s]*", localized_disclaimer, report, flags=re.IGNORECASE)
            report = re.sub(r"AI\s*Disclaimer[:\s]*", localized_disclaimer, report, flags=re.IGNORECASE)
            report = normalize_report_section_spacing(report)
        except Exception:
            pass

        # Validate AI report is not empty
        if not report or len(report.strip()) < 50:
            raise Exception("AI generated empty or insufficient report")

        # ==========================
        # SAVE REPORT VERSION (FINAL TEXT)
        # ==========================
        def _normalise_report_text(text):
            if not text:
                return ""
            text = re.sub(r"^Generated Date:\s.*$", "", text, flags=re.MULTILINE)
            text = re.sub(r"^Tarikh Jana:\s.*$", "", text, flags=re.MULTILINE)
            return text.strip()

        latest_same_language = None
        for item in reversed(role_versions):
            if item.get("language") == language:
                latest_same_language = item
                break

        if latest_same_language and _normalise_report_text(latest_same_language.get("report_text")) == _normalise_report_text(report):
            new_version_number = latest_same_language.get("version", len(role_versions))
        else:
            new_version_number = len(role_versions) + 1
            now_local = _now_app_timezone()

            role_versions.append({
                "version": new_version_number,
                "generated_at": now_local.strftime("%Y-%m-%d %H:%M:%S"),
                "language": language,
                "report_text": report
            })

            versions[role] = role_versions
            save_versions(versions)
            backup_versions()

        # AUDIT LOG: AI REPORT GENERATED
        _append_audit_event(
            action="AI Report Generated",
            role=role,
            details={
                "username": session.get("username", ""),
                "language": language,
                "version": new_version_number,
                "data_hash": data_hash,
                "defect_count": len(defects),
            },
        )

        now_local = _now_app_timezone()

        # Ensure the returned report preview has a consistent header matching Malay layout
        try:
            lang_conf = get_language_config(language)
            ai_title = lang_conf.get("ai_title") or ("AI-GENERATED CLAIM SUMMARY REPORT" if language == "en" else "LAPORAN RINGKASAN TUNTUTAN DIJANA AI")
            pdf_labels = PDF_LABELS.get(language, PDF_LABELS["ms"])
            report_title = _report_title_for_role(pdf_labels, role)
            generated_label = lang_conf.get("generated_label") or ("Generated Date" if language == "en" else "Tarikh Jana")
            subtitle = _report_subtitle_for_role(pdf_labels, role)

            header = f"{ai_title}\n\n{report_title}\n{generated_label}: {_format_display_timestamp(now_local.strftime('%Y-%m-%d %H:%M:%S'), language)}\n\n{subtitle}\n\n"

            report = _strip_known_report_header_lines(report, language)

            if not report.lstrip().lower().startswith(ai_title.lower()):
                report = header + report
        except Exception:
            pass

        return jsonify({
            "generated_at": _format_display_timestamp(now_local.strftime("%Y-%m-%d %H:%M:%S"), language),
            "role": role,
            "language": language,
            "report": _sanitize_encrypted_fragments(report)
        })

    except Exception as e:
        # DEBUG
        current_app.logger.error(f"AI Report Generation Failed: {str(e)}")
        
        # Provide more helpful error messages
        error_message = str(e)
        if "quota" in error_message.lower() or "429" in error_message:
            error_details = "API rate limit exceeded. Please try again later."
        elif "401" in error_message or "api_key" in error_message.lower():
            error_details = "API key invalid or missing. Check your GROQ_API_KEY."
        elif "timeout" in error_message.lower():
            error_details = "Request timed out. Please try again."
        else:
            error_details = str(e)

        return jsonify({
            "error": "Failed to generate AI report",
            "details": error_details,
            "debug": str(e) if current_app.debug else None
        }), 500

# =================================================
# EXPORT PDF - BORANG 1 TTPM FORMAT WITH AI REPORT
# PDF EXPORT ROUTE
# =================================================
@routes.route("/export_pdf", methods=["POST"])
@login_required
def export_pdf():
    role = _current_role()
    auto_close_completed_cases(trigger_role=role)
    # ðŸ”’ Enforce backend role validation
    if role not in ["Homeowner", "Developer", "Legal"]:
        return jsonify({"error": "Unauthorized role"}), 403
    language = _normalise_language(request.form.get("language", "ms"))
    project_name = (request.form.get("project_name") or "").strip()
    ai_report_text = request.form.get("ai_report", "")
    claimant_user_id = request.form.get("claimant_user_id", "")
    claimant_user_id = int(claimant_user_id) if str(claimant_user_id).strip().isdigit() else None
    resolved_scope = _resolve_report_scope(role, _current_user_id(), project_name, claimant_user_id)
    if resolved_scope.get("error"):
        return jsonify({"error": resolved_scope["error"]}), 400

    project_name = resolved_scope.get("project_name", "")
    claimant_user_id = resolved_scope.get("claimant_user_id")

    if not ai_report_text or not ai_report_text.strip():
        return jsonify(
            {
                "error": "Please generate AI report before exporting PDF.",
            }
        ), 400

    report_gap_report = detect_missing_report_values(
        role=role,
        user_id=_current_user_id(),
        claimant_user_id=claimant_user_id,
    )
    requirement_errors = report_gap_report["messages"]
    if report_gap_report["has_missing"]:
        return jsonify(
            {
                "error": "Cannot export PDF. Required profile/case data is incomplete.",
                "details": requirement_errors,
                "missing_data": report_gap_report["missing"],
            }
        ), 400

    closed_evidence_appendix = get_closed_evidence_appendix(
        role,
        claimant_unit=_get_user_unit(claimant_user_id or _current_user_id()),
        project_name=project_name,
    )

    # Load language-specific labels
    labels = PDF_LABELS.get(language, PDF_LABELS["ms"])

    defects = get_defects_for_role(role)
    remarks_store = load_remarks()
    status_store = load_status()
    completion_store = load_completion_dates()
    evidence_store = load_evidence()

    # LOAD DATA AND NORMALISE FIELDS
    for d in defects:
        # Load latest status from storage
        d["status"] = status_store.get(str(d["id"]), d["status"])

        d["completed_date"] = completion_store.get(
            str(d["id"]),
            d.get("completed_date")
        )
        d["closed"] = is_auto_closed(d["status"], d.get("completed_date"))
        d["display_status"] = "Closed" if d["closed"] else d["status"]

        evidence_data = evidence_store.get(str(d["id"]))
        evidence_files = _evidence_items_from_meta(evidence_data)
        if evidence_files:
            d["evidence_uploaded"] = True
            d["evidence_files"] = evidence_files
            d["evidence_count"] = len(evidence_files)
            d["evidence_filename"] = evidence_files[0].get("filename")
            d["evidence_uploaded_at"] = evidence_data.get("uploaded_at") or evidence_files[-1].get("uploaded_at")
        else:
            d["evidence_uploaded"] = False
            d["evidence_files"] = []
            d["evidence_count"] = 0
            d["evidence_filename"] = None
            d["evidence_uploaded_at"] = None

        d["hda_compliant"] = calculate_hda_compliance(
            d["reported_date"],
            d.get("completed_date"),
            d["status"]
        )

        d["is_overdue"] = calculate_overdue(
            d["deadline"],
            d.get("completed_date"),
            d["status"]
        )
        # Load remarks (Homeowner only, filtered later)
        d["remarks"] = remarks_store.get(str(d["id"]), "")

        # Normalise urgency â†’ priority if priority is missing
        if "urgency" in d and not d.get("priority"):
            d["priority"] = d["urgency"]

    defects = _filter_defects_for_report_scope(
        defects,
        project_name=project_name,
        claimant_user_id=claimant_user_id,
        include_project_peers=role in ["Developer", "Legal"],
    )

    # Enforce evidence presence for defects included in this export scope
    try:
        scoped_defects = list(defects)

        missing_evidence = []
        for d in scoped_defects:
            closed = d.get("closed") if "closed" in d else is_auto_closed(d.get("status"), d.get("completed_date"))
            if closed:
                continue
            evidence_count = int(d.get("evidence_count") or len(d.get("evidence_files") or []))
            if evidence_count < REQUIRED_EVIDENCE_IMAGE_COUNT:
                missing_evidence.append({
                    "id": d.get("id"),
                    "unit": d.get("unit"),
                    "evidence_count": evidence_count,
                    "required_count": REQUIRED_EVIDENCE_IMAGE_COUNT,
                })
        if missing_evidence:
            return jsonify({
                "error": "Cannot export PDF: some defects in the selected scope are missing required evidence images.",
                "missing_evidence": missing_evidence,
            }), 400
    except Exception:
        # Silently continue on unexpected errors and let later checks/failures surface
        pass

    # Keep statistics based on the selected project scope, including closed items.
    defects_for_stats = [dict(item) for item in defects]

    if role in ["Homeowner", "Developer", "Legal", "Admin"]:
        defects = [d for d in defects if not d.get("closed")]

    # LOCK STATUS (BACKEND AUTHORITY)
    # Status must NEVER be modified by AI
    for d in defects:
        d["_status_raw"] = d["status"]  # Always English internally

    # TRANSLATE DEFECT TEXT (AI, CACHED)
    # Status is NOT translated here
    defects = translate_defects_cached(
        defects,
        language=language,
        role=role
    )

    # =================================================
    # NORMALISE STATUS FOR STATISTICS (ALWAYS ENGLISH)
    # =================================================
    for d in defects_for_stats:
        if d.get("status") in STATUS_NORMALISE:
            d["status"] = STATUS_NORMALISE[d["status"]]

    # CALCULATE STATISTICS (STATUS MUST BE ENGLISH)
    stats = calculate_stats(defects_for_stats)

    # TRANSLATE STATUS, PRIORITY FOR PDF DISPLAY
    for d in defects:
        if d.get("status") in STATUS_NORMALISE:
            d["status"] = STATUS_NORMALISE[d["status"]]
        d["status"] = STATUS_TRANSLATION.get(language, {}).get(d["status"], d["status"])
        if d.get("priority"):
            d["priority"] = PRIORITY_TRANSLATION.get(language, {}).get(d["priority"], d["priority"])

    preview_claim_id = extract_claim_reference_from_report_text(ai_report_text)
    case_key = build_case_key(role=role, user_id=claimant_user_id or _current_user_id(), defects=defects)
    report_data = build_report_data(
        role,
        defects,
        stats,
        user_id=_current_user_id(),
        case_key=case_key,
        claimant_user_id=claimant_user_id,
        forced_claim_number=preview_claim_id,
    )
    if preview_claim_id:
        report_data.setdefault("case_info", {})["claim_id"] = preview_claim_id
        report_data.setdefault("case_info", {})["claim_number"] = preview_claim_id
    report_data.setdefault("case_info", {})["item_service"] = _item_service_for_language(
        report_data.get("case_info", {}).get("item_service"),
        language,
    )
    project_name_display = (
        project_name
        or report_data.get("case_info", {}).get("project_name")
        or next(
            (
                str(d.get("project_name") or "").strip()
                for d in defects
                if str(d.get("project_name") or "").strip()
                and str(d.get("project_name") or "").strip().lower() not in {"-", "others / unrelated", "others / unassigned", "__others__"}
            ),
            "",
        )
    )
    report_data.setdefault("case_info", {})["project_name"] = project_name_display or "-"

    claimant_unit_for_grouping = _get_user_unit(claimant_user_id or _current_user_id())
    claimant_unit_normalized = _normalise_unit_for_grouping(claimant_unit_for_grouping)

    if role in ["Developer", "Legal"] and claimant_unit_normalized:
        claimant_defects_for_pdf = [
            d for d in defects
            if _normalise_unit_for_grouping(d.get("unit", "")) == claimant_unit_normalized
        ]
        other_defects_for_pdf = [
            d for d in defects
            if _normalise_unit_for_grouping(d.get("unit", "")) != claimant_unit_normalized
        ]
        defects = claimant_defects_for_pdf + other_defects_for_pdf
    else:
        claimant_defects_for_pdf = []
        other_defects_for_pdf = defects

    # Keep AI preview and exported PDF fully aligned by using the submitted preview text.

    if role in ["Homeowner", "Developer", "Legal", "Admin"]:
        ai_report_text = _strip_opposite_language_report(ai_report_text, language)
        ai_report_text = strip_closed_appendix_section(ai_report_text)
        ai_report_text = remove_english_tribunal_title_after_subtitle(ai_report_text, language)
    ai_report_text = _sanitize_encrypted_fragments(ai_report_text)

    # HIDE REMARKS FOR NON-HOMEOWNER ROLES (after translation and data prep)
    if role != "Homeowner":
        for d in defects:
            d["remarks"] = ""
    # =============================================
    # GENERATE LEGAL METADATA & DIGITAL SIGNATURES
    # =============================================
    report_id = build_public_report_id(report_data)
    legal_metadata = add_legal_metadata(
        report_content=ai_report_text,
        report_id=report_id,
        user_id=_current_user_id(),
        role=role,
        defects=defects,
        status_store=status_store,
        completion_store=completion_store,
        language=language
    )
    
    # Log PDF export event
    legal_manager = get_legal_manager()
    legal_manager.log_event(
        action="pdf_export",
        report_id=report_id,
        user_id=_current_user_id(),
        role=role,
        details={
            "defect_count": len(defects),
            "language": language,
            "signature_id": legal_metadata.get("signature", {}).get("signature_id")
        }
    )

    # START PDF GENERATION
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    # Load language-specific labels
    labels = PDF_LABELS.get(language, PDF_LABELS["ms"])
    width, height = A4

    # Standardised font sizes: use module-level font constants for consistency
    # (see module-level FONT_H1/FONT_H2/FONT_H3/FONT_BODY/FONT_CAPTION)

    # Ensure evidence directory exists
    evidence_dir = os.path.join(current_app.root_path, "evidence")
    os.makedirs(evidence_dir, exist_ok=True)

    # ============================================
    # PAGE 1: BORANG 1 HEADER & PARTIES
    # ============================================
    
    # --- HEADER (Centered) ---
    TOP_MARGIN = 40
    LINE_SPACING_SMALL = 13
    LINE_SPACING_MEDIUM = 16
    LINE_SPACING_LARGE = 22

    y = height - TOP_MARGIN

    # ---------------------------
    # ACT TITLE
    # ---------------------------
    pdf.setFont("Times-Bold", FONT_H3)

    if language == "en":
        draw_centered_fitted_string(pdf, width/2, y, "CONSUMER PROTECTION ACT 1999", width - 100, "Times-Bold", FONT_H3)
    else:
        draw_centered_fitted_string(pdf, width/2, y, "AKTA PERLINDUNGAN PENGGUNA 1999", width - 100, "Times-Bold", FONT_H3)

    y -= LINE_SPACING_MEDIUM


    # ---------------------------
    # REGULATIONS TITLE
    # ---------------------------
    pdf.setFont("Times-Bold", FONT_H2)

    if language == "en":
        draw_centered_fitted_string(pdf, width/2, y, "CONSUMER PROTECTION REGULATIONS", width - 100, "Times-Bold", FONT_H2)
    else:
        draw_centered_fitted_string(pdf, width/2, y, "PERATURAN-PERATURAN PERLINDUNGAN PENGGUNA", width - 100, "Times-Bold", FONT_H2)

    y -= LINE_SPACING_SMALL


    # ---------------------------
    # TRIBUNAL REFERENCE
    # ---------------------------
    if language == "en":
        draw_centered_fitted_string(pdf, width/2, y, "(CONSUMER CLAIMS TRIBUNAL) 1999", width - 100, "Times-Bold", FONT_H2)
    else:
        draw_centered_fitted_string(pdf, width/2, y, "(TRIBUNAL TUNTUTAN PENGGUNA) 1999", width - 100, "Times-Bold", FONT_H2)

    y -= LINE_SPACING_LARGE


    # ---------------------------
    # FORM TITLE
    # ---------------------------
    pdf.setFont("Times-Bold", FONT_H2)

    if language == "en":
        draw_centered_fitted_string(pdf, width/2, y, "FORM 1", width - 100, "Times-Bold", FONT_H2)
    else:
        draw_centered_fitted_string(pdf, width/2, y, "BORANG 1", width - 100, "Times-Bold", FONT_H2)

    y -= LINE_SPACING_SMALL


    pdf.setFont("Times-Roman", FONT_BODY)

    if language == "en":
        draw_centered_fitted_string(pdf, width/2, y, "(Regulation 5)", width - 100, "Times-Roman", FONT_BODY)
    else:
        draw_centered_fitted_string(pdf, width/2, y, "(Peraturan 5)", width - 100, "Times-Roman", FONT_BODY)

    y -= LINE_SPACING_LARGE


    # ---------------------------
    # STATEMENT TITLE
    # ---------------------------
    pdf.setFont("Times-Bold", FONT_H3)

    if language == "en":
        draw_centered_fitted_string(pdf, width/2, y, "STATEMENT OF CLAIM", width - 100, "Times-Bold", FONT_H3)
    else:
        draw_centered_fitted_string(pdf, width/2, y, "PERNYATAAN TUNTUTAN", width - 100, "Times-Bold", FONT_H3)

    y -= LINE_SPACING_MEDIUM


    pdf.setFont("Times-Roman", FONT_BODY)

    if language == "en":
        draw_centered_fitted_string(pdf, width/2, y, "IN THE CONSUMER CLAIMS TRIBUNAL", width - 100, "Times-Roman", FONT_BODY)
    else:
        draw_centered_fitted_string(pdf, width/2, y, "DALAM TRIBUNAL TUNTUTAN PENGGUNA", width - 100, "Times-Roman", FONT_BODY)

    y -= 16


    # ============================================
    # LOCATION & CLAIM NUMBER
    # ============================================

    pdf.setFont("Times-Roman", FONT_BODY)

    lokasi = report_data["case_info"]["tribunal_location"]
    negeri = report_data["case_info"]["state_name"]
    no_tuntutan = report_data["case_info"]["claim_number"]
    project_name_for_header = str(report_data["case_info"].get("project_name") or "-").upper()

    if language == "en":
        draw_centered_fitted_string(pdf, width/2, y, f"AT {lokasi}".upper(), width - 100, "Times-Roman", FONT_BODY)
        y -= LINE_SPACING_MEDIUM

        draw_centered_fitted_string(pdf, width/2, y, f"IN THE STATE OF {negeri}, MALAYSIA".upper(), width - 100, "Times-Roman", FONT_BODY)
        y -= LINE_SPACING_LARGE

        draw_fitted_string(pdf, 50, y, f"CLAIM NO.: {no_tuntutan}", width - 100, "Times-Roman", FONT_BODY)
        y -= LINE_SPACING_MEDIUM
        draw_fitted_string(pdf, 50, y, f"PROJECT NAME: {project_name_for_header}", width - 100, "Times-Roman", FONT_BODY)
    else:
        draw_centered_fitted_string(pdf, width/2, y, f"DI {lokasi}".upper(), width - 100, "Times-Roman", FONT_BODY)
        y -= LINE_SPACING_MEDIUM

        draw_centered_fitted_string(pdf, width/2, y, f"DI NEGERI {negeri}, MALAYSIA".upper(), width - 100, "Times-Roman", FONT_BODY)
        y -= LINE_SPACING_LARGE

        draw_fitted_string(pdf, 50, y, f"TUNTUTAN NO.: {no_tuntutan}", width - 100, "Times-Roman", FONT_BODY)
        y -= LINE_SPACING_MEDIUM
        draw_fitted_string(pdf, 50, y, f"NAMA PROJEK: {project_name_for_header}", width - 100, "Times-Roman", FONT_BODY)

    # --- PIHAK YANG MENUNTUT (Claimant) ---
    PARTY_HEADING_TOP_GAP = 32
    y -= PARTY_HEADING_TOP_GAP
    pdf.setFont("Times-Bold", FONT_H2)
    if language == "en":
        pdf.drawString(50, y, "CLAIMANT")
    else:
        pdf.drawString(50, y, "PIHAK YANG MENUNTUT")
    
    # Draw box for claimant details
    box_x = 50
    box_y = y - 120
    box_width = width - 100
    box_height = 110
    pdf.rect(box_x, box_y, box_width, box_height)

    # Define consistent inner padding and column positions for boxed content
    BOX_PADDING = 10
    label_x = box_x + BOX_PADDING + 10
    value_x = box_x + BOX_PADDING + 150
    form_value_width = box_x + box_width - BOX_PADDING - value_x

    # Claimant form fields (use padded coordinates)
    # position first row a bit lower from the top of the claimant box
    content_start_y = box_y + box_height - BOX_PADDING - 8
    y = content_start_y
    pdf.setFont("Times-Roman", FONT_BODY)
    claimant = report_data['claimant']
    if language == "en":
        pdf.drawString(label_x, y, "Claimant Name")
        y = draw_form_value(pdf, claimant.get('name', ''), value_x, y, form_value_width)
        y -= 4
        pdf.drawString(label_x, y, "IC/Passport No.")
        # Encrypt NRIC before displaying (simulation of encryption at rest)
        encrypted_nric = encrypt_text(claimant.get('national_id', ''))
        decrypted_nric = decrypt_text(encrypted_nric)

        y = draw_form_value(pdf, decrypted_nric, value_x, y, form_value_width)
        y -= 4
        pdf.drawString(label_x, y, "Correspondence Address")
        y = draw_form_value(pdf, claimant.get('address_line_1', ''), value_x, y, form_value_width)
        y -= 4
        pdf.drawString(label_x, y, "Phone No.")
        y = draw_form_value(pdf, claimant.get('phone_number', ''), value_x, y, form_value_width)
        y -= 4
        pdf.drawString(label_x, y, "Fax/Email")
        y = draw_form_value(pdf, claimant.get('email', ''), value_x, y, form_value_width)
    else:
        pdf.drawString(label_x, y, "Nama Pihak Yang Menuntut")
        y = draw_form_value(pdf, claimant.get('name', ''), value_x, y, form_value_width)
        y -= 4
        pdf.drawString(label_x, y, "No. Kad Pengenalan/Pasport")
        # Encrypt NRIC before displaying (simulation of encryption at rest)
        encrypted_nric = encrypt_text(claimant.get('national_id', ''))
        decrypted_nric = decrypt_text(encrypted_nric)

        y = draw_form_value(pdf, decrypted_nric, value_x, y, form_value_width)
        y -= 4
        pdf.drawString(label_x, y, "Alamat Surat Menyurat")
        y = draw_form_value(pdf, claimant.get('address_line_1', ''), value_x, y, form_value_width)
        y -= 4
        pdf.drawString(label_x, y, "No. Telefon")
        y = draw_form_value(pdf, claimant.get('phone_number', ''), value_x, y, form_value_width)
        y -= 4
        pdf.drawString(label_x, y, "No. Faks/ E-mel")
        y = draw_form_value(pdf, claimant.get('email', ''), value_x, y, form_value_width)
    
    # --- PENENTANG (Respondent/Developer) ---
    y -= 45
    pdf.setFont("Times-Bold", FONT_H2)
    if language == "en":
        pdf.drawString(50, y, "RESPONDENT")
    else:
        pdf.drawString(50, y, "PENENTANG")
    
    # Draw box for respondent details - make it taller to fit all content
    box_top = y - 10
    box_height = 170
    pdf.rect(box_x, box_top - box_height, box_width, box_height)
    
    # Respondent form fields
    # position first row a bit lower from the top of the respondent box
    content_start_y = box_top - BOX_PADDING - 8
    y = content_start_y
    pdf.setFont("Times-Roman", FONT_BODY)
    respondent = report_data['respondent']
    form_value_width = box_x + box_width - BOX_PADDING - value_x
    if language == "en":
        pdf.drawString(label_x, y, "Name of Respondent/Company/")
        y = draw_form_value(pdf, respondent.get('name', ''), value_x, y, form_value_width)
        y -= 2
        pdf.drawString(label_x, y, "Corporation/Organisation/Firm")
        y -= 18
        pdf.drawString(label_x, y, "Identity Card No./")
        y = draw_form_value(pdf, respondent.get('registration_no', ''), value_x, y, form_value_width)
        y -= 2
        pdf.drawString(label_x, y, "Company Registration No./")
        y -= 12
        pdf.drawString(label_x, y, "Corporation/Organisation/Firm")
        y -= 18
        pdf.drawString(label_x, y, "Correspondence Address")
        y = draw_form_value(pdf, respondent.get('address_line_1', ''), value_x, y, form_value_width)
        y -= 2
        pdf.drawString(label_x, y, "Telephone No.")
        y = draw_form_value(pdf, respondent.get('phone_number', ''), value_x, y, form_value_width)
        y -= 2
        pdf.drawString(label_x, y, "Fax/E-mail")
        y = draw_form_value(pdf, respondent.get('email', ''), value_x, y, form_value_width)
    else:
        pdf.drawString(label_x, y, "Nama Penentang/Syarikat/")
        y = draw_form_value(pdf, respondent.get('name', ''), value_x, y, form_value_width)
        y -= 2
        pdf.drawString(label_x, y, "Pertubuhan Perbadanan/Firma")
        y -= 18
        pdf.drawString(label_x, y, "No. Kad Pengenalan/")
        y = draw_form_value(pdf, respondent.get('registration_no', ''), value_x, y, form_value_width)
        y -= 2
        pdf.drawString(label_x, y, "No. Pendaftaran Syarikat/")
        y -= 12
        pdf.drawString(label_x, y, "Pertubuhan Perbadanan/Firma")
        y -= 18
        pdf.drawString(label_x, y, "Alamat Surat Menyurat")
        y = draw_form_value(pdf, respondent.get('address_line_1', ''), value_x, y, form_value_width)
        y -= 2
        pdf.drawString(label_x, y, "No. Telefon")
        y = draw_form_value(pdf, respondent.get('phone_number', ''), value_x, y, form_value_width)
        y -= 2
        pdf.drawString(label_x, y, "No. Faks/E-mel")
        y = draw_form_value(pdf, respondent.get('email', ''), value_x, y, form_value_width)

    # Move y below the PENENTANG box
    y = box_top - box_height - 30
    
    # --- PERNYATAAN TUNTUTAN (Claim Amount) - on same page ---
    pdf.setFont("Times-Bold", FONT_H2)
    if language == "en":
        pdf.drawString(50, y, "STATEMENT OF CLAIM")
        y -= 20
        pdf.setFont("Times-Roman", FONT_BODY)
        y = draw_claim_amount_line(
            pdf,
            "The Claimant's claim is for the amount of RM:",
            report_data["case_info"]["claim_amount"],
            50,
            y,
            width - 100,
        )
    else:
        pdf.drawString(50, y, "PERNYATAAN TUNTUTAN")
        y -= 20
        pdf.setFont("Times-Roman", FONT_BODY)
        y = draw_claim_amount_line(
            pdf,
            "Tuntutan Pihak Yang Menuntut ialah untuk jumlah RM:",
            report_data["case_info"]["claim_amount"],
            50,
            y,
            width - 100,
        )
    
    # --- BUTIR-BUTIR TUNTUTAN (Claim Details) ---
    y -= 14
    pdf.setFont("Times-Bold", FONT_H2)
    if language == "en":
        pdf.drawString(50, y, "Claim Details")
    else:
        pdf.drawString(50, y, "Butir-butir Tuntutan")
    
    # Draw box for claim details - box starts below title
    box_top = y - 10
    box_height = 95
    box_x = 50
    box_width = width - 100
    pdf.rect(box_x, box_top - box_height, box_width, box_height)

    # consistent padding/columns inside claim details box
    BOX_PADDING = 10
    label_x = box_x + BOX_PADDING + 10
    value_x = box_x + BOX_PADDING + 200
    form_value_width = box_x + box_width - BOX_PADDING - value_x

    y = box_top - BOX_PADDING - 8
    pdf.setFont("Times-Roman", FONT_BODY)
    if language == "en":
        pdf.drawString(label_x, y, "Goods/Services")
        y = draw_form_value(pdf, report_data['case_info'].get('item_service', 'Defect Repairs During DLP Period'), value_x, y, form_value_width)
        y -= 4
        pdf.drawString(label_x, y, "Date of Purchase/Transaction")
        y = draw_form_value(
            pdf,
            _format_display_date(report_data['case_info'].get('transaction_date', report_data['case_info']['generated_date']), language),
            value_x,
            y,
            form_value_width,
        )
        y -= 4
        pdf.drawString(label_x, y, "Amount Paid")
        y = draw_form_value(pdf, report_data['case_info']['claim_amount'], value_x, y, form_value_width)
    else:
        pdf.drawString(label_x, y, "Barangan/Perkhidmatan")
        y = draw_form_value(pdf, report_data['case_info'].get('item_service', 'Pembaikan Kecacatan Dalam Tempoh DLP'), value_x, y, form_value_width)
        y -= 4
        pdf.drawString(label_x, y, "Tarikh Pembelian/ Transaksi")
        y = draw_form_value(
            pdf,
            _format_display_date(report_data['case_info'].get('transaction_date', report_data['case_info']['generated_date']), language),
            value_x,
            y,
            form_value_width,
        )
        y -= 4
        pdf.drawString(label_x, y, "Jumlah yang dibayar")
        y = draw_form_value(pdf, report_data['case_info']['claim_amount'], value_x, y, form_value_width)

    # ============================================
    # PAGE 2: RINGKASAN & SENARAI KECACATAN
    # ============================================
    draw_footer(pdf, width, labels)
    pdf.showPage()
    y = height - 50
    
    # --- RINGKASAN TUNTUTAN (Claim Summary) ---
    pdf.setFont("Times-Bold", FONT_H2)
    if language == "en":
        pdf.drawString(50, y, "Claim Summary:")
    else:
        pdf.drawString(50, y, "Ringkasan Tuntutan:")

    # Draw box for claim summary
    box_top = y - 10
    box_height = 135
    box_x = 50
    box_width = width - 100
    pdf.rect(box_x, box_top - box_height, box_width, box_height)

    # Summary statistics inside the box (simple label: value lines)
    y -= 25
    pdf.setFont("Times-Roman", FONT_BODY)
    summary = report_data['summary_stats']
    if language == "en":
        pdf.drawString(60, y, f"Total Reported: {summary['total_defects']}")
        y -= 15
        pdf.drawString(60, y, f"Pending: {summary['pending_defects']}")
        y -= 15
        pdf.drawString(60, y, f"In Progress: {summary.get('investigation_defects', 0)}")
        y -= 15
        pdf.drawString(60, y, f"Closed Cases: {summary.get('closed_defects', 0)}")
        y -= 15
        pdf.drawString(60, y, f"Completed: {summary['completed_defects']}")
        y -= 15
        pdf.drawString(60, y, f"Overdue: {summary.get('overdue_defects', 0)}")
        y -= 15
        pdf.drawString(60, y, f"Non-Compliant (30-Day HDA): {summary.get('hda_non_compliant_defects', 0)}")
        y -= 15
    else:
        pdf.drawString(60, y, f"Jumlah Dilaporkan: {summary['total_defects']}")
        y -= 15
        pdf.drawString(60, y, f"Belum Diselesaikan: {summary['pending_defects']}")
        y -= 15
        pdf.drawString(60, y, f"Dalam Tindakan: {summary.get('investigation_defects', 0)}")
        y -= 15
        pdf.drawString(60, y, f"Kes Ditutup: {summary.get('closed_defects', 0)}")
        y -= 15
        pdf.drawString(60, y, f"Telah Diselesaikan: {summary['completed_defects']}")
        y -= 15
        pdf.drawString(60, y, f"Tertunggak: {summary.get('overdue_defects', 0)}")
        y -= 15
        pdf.drawString(60, y, f"Tidak Mematuhi Tempoh 30 Hari: {summary.get('hda_non_compliant_defects', 0)}")
        y -= 15
    # Move y below the box
    y = box_top - box_height - 20

    if role in ["Homeowner", "Developer", "Legal"] and closed_evidence_appendix:
        pdf.setFont("Times-Italic", 10)
        if language == "en":
            y = draw_wrapped_text(
                pdf,
                "Note: Closed cases are included in the claim summary and also listed in Appendix A for reference. This rule is applied consistently across Homeowner, Developer, and Legal roles.",
                50,
                y,
                width - 100,
                "Times-Italic",
                8,
                12,
            )
        else:
            y = draw_wrapped_text(
                pdf,
                "Nota: Kes berstatus Ditutup disertakan dalam Ringkasan Tuntutan dan turut disenaraikan dalam Lampiran A untuk rujukan. Peraturan ini digunakan secara konsisten bagi peranan Pemilik Rumah, Pemaju dan Perundangan.",
                50,
                y,
                width - 100,
                "Times-Italic",
                8,
                12,
            )
        y -= 6
    
    # --- SENARAI KECACATAN (Defect List) ---
    y -= 35
    main_defect_title = "Defect List" if language == "en" else "Senarai Kecacatan"
    # Draw main defect list heading so it's always shown before any group titles
    pdf.setFont("Times-Bold", FONT_H2)
    pdf.drawString(50, y, f"{main_defect_title}:")
    y -= 18

    def _defect_group_title(defect):
        if role not in ["Developer", "Legal"] or not claimant_unit_normalized:
            return ""

        defect_unit = _normalise_unit_for_grouping(defect.get("unit", ""))
        if defect_unit == claimant_unit_normalized:
            return (
                "Claimant Owner"
                if language == "en"
                else "Pemilik Menuntut"
            )
        return (
            "Other Owners in Case"
            if language == "en"
            else "Pemilik Lain Dalam Kes"
        )

    def _draw_defect_list_heading(y_pos, group_title="", continued=False):
        pdf.setFont("Times-Bold", FONT_H2)
        suffix = " (continued)" if language == "en" and continued else " (sambungan)" if continued else ""
        pdf.drawString(50, y_pos, f"{main_defect_title}{suffix}:")
        y_pos -= 18
        if group_title:
            pdf.setFont("Times-Bold", FONT_H2)
            pdf.drawString(60, y_pos, f"{group_title}{suffix}:")
            y_pos -= 18
        return y_pos
    
    current_group_title = None
    group_item_counts = {}
    claimant_group_title = "Claimant Owner" if language == "en" else "Pemilik Menuntut"

    if role in ["Developer", "Legal"] and claimant_unit_normalized and not claimant_defects_for_pdf:
        pdf.setFont("Times-Bold", FONT_H2)
        pdf.drawString(60, y, f"{claimant_group_title}:")
        y -= 28

    for i, defect in enumerate(defects, 1):
        group_title = _defect_group_title(defect)
        if group_title != current_group_title:
            if y < 110:
                draw_footer(pdf, width, labels)
                pdf.showPage()
                y = height - 50
                y = _draw_defect_list_heading(y, group_title, continued=True)
            else:
                if current_group_title is not None:
                    y -= 10
                if group_title:
                    pdf.setFont("Times-Bold", FONT_H2)
                    pdf.drawString(60, y, f"{group_title}:")
                    y -= 18
            current_group_title = group_title

        group_counter_key = group_title or main_defect_title
        group_item_counts[group_counter_key] = group_item_counts.get(group_counter_key, 0) + 1
        item_index = group_item_counts[group_counter_key]

        # ===============================
        # CONSISTENT INDENT POSITIONS
        # ===============================
        HEADER_X = 50      # a. Kecacatan ID
        LABEL_X  = 70      # Keterangan / Unit / Status
        VALUE_X  = 220     # isi selepas :
        RIGHT_MARGIN = 50
        TEXT_WIDTH = width - VALUE_X - RIGHT_MARGIN

        # Keep a full defect block together when possible.
        desc_lines = _estimate_wrapped_lines_with_font(pdf, f": {defect.get('desc', '-')}", "Times-Roman", FONT_BODY, TEXT_WIDTH)
        remarks_lines = 0
        if role == "Homeowner" and defect.get("remarks"):
            remarks_lines = _estimate_wrapped_lines_with_font(pdf, f": {defect.get('remarks', '')}", "Times-Roman", FONT_BODY, TEXT_WIDTH)

        hda_message = _hda_compliance_display(defect.get("hda_compliant"), language, defect.get("status"))
        hda_lines = _estimate_wrapped_lines_with_font(pdf, f": {hda_message}", "Times-Roman", FONT_BODY, TEXT_WIDTH)

        evidence_items_for_height = _evidence_items_from_meta({
            "files": defect.get("evidence_files") or [],
            "filename": defect.get("evidence_filename"),
            "uploaded_at": defect.get("evidence_uploaded_at"),
        })
        image_paths_for_height = [
            _resolve_evidence_image_path(evidence_dir, defect.get("id"), item.get("filename"))
            for item in evidence_items_for_height
        ]
        image_paths_for_height = [path for path in image_paths_for_height if path]

        estimated_height = 0
        estimated_height += 16                              # defect header
        estimated_height += desc_lines * 16                # description
        estimated_height += 16 * 6                         # unit/status/reported/deadline/actual/days lines
        estimated_height += hda_lines * 16                 # HDA line (wrapped)
        estimated_height += 16                             # overdue line
        if defect.get("priority"):
            estimated_height += 16
        if remarks_lines > 0:
            estimated_height += remarks_lines * 16
        if image_paths_for_height:
            estimated_height += 144                        # evidence label + side-by-side images + dates
        estimated_height += 25                             # space between defects

        # Ensure enough space for ONE full defect block
        if y - estimated_height < 80:
            draw_footer(pdf, width, labels)
            pdf.showPage()
            y = height - 50
            y = _draw_defect_list_heading(y, current_group_title or "", continued=True)

        # ===== DEFECT HEADER =====
        pdf.setFont("Times-Bold", FONT_H2)
        pdf.drawString(
            HEADER_X,
            y,
            f"{chr(64 + item_index) if item_index <= 26 else item_index}. {labels['defect_id']} {defect['id']}:"
        )
        y -= 16

        pdf.setFont("Times-Roman", FONT_BODY)

        def draw_defect_field(label, value, current_y):
            pdf.setFont("Times-Roman", FONT_BODY)
            pdf.drawString(LABEL_X, current_y, str(label or ""))
            return draw_wrapped_text(
                pdf,
                f": {str(value if value is not None else '-')}",
                VALUE_X,
                current_y,
                TEXT_WIDTH,
                "Times-Roman",
                FONT_BODY,
                16,
            )

        # ---- Keterangan ----
        y = draw_defect_field(labels["description"], defect.get("desc", "-"), y)

        # ---- Unit ----
        y = draw_defect_field(labels["unit"], defect.get("unit", "-"), y)

        # ---- Status ----
        status_text = defect["status"]
        y = draw_defect_field(labels["status"], status_text, y)

        # ---- Reported Date ----
        y = draw_defect_field(
            labels.get("reported_date", "Reported Date"),
            _format_display_date(defect.get("reported_date"), language),
            y,
        )


        # ---- Scheduled Completion Date ----
        y = draw_defect_field(
            labels.get("deadline", "Scheduled Completion Date"),
            _format_display_date(defect.get("deadline"), language),
            y,
        )

        # ---- Actual Completion Date ----
        y = draw_defect_field(
            labels.get("actual_completion_date", "Actual Completion Date"),
            _format_display_date(defect.get("completed_date"), language),
            y,
        )

        # ---- Days to Complete ----
        days_to_complete = calculate_days_to_complete(
            defect.get("reported_date"),
            defect.get("completed_date"),
        )
        if language == "en":
            y = draw_defect_field("Days to Complete", days_to_complete if days_to_complete is not None else "-", y)
        else:
            y = draw_defect_field("Tempoh Siap (Hari)", days_to_complete if days_to_complete is not None else "-", y)

        # ---- HDA Compliance ----
        pdf.setFont("Times-Roman", FONT_BODY)

        if language == "en":
            hda_label = "HDA Compliance Status"
        else:
            hda_label = "Status Pematuhan HDA"
        message = _hda_compliance_display(defect.get("hda_compliant"), language, defect.get("status"))

        y = draw_defect_field(hda_label, message, y)

        # ---- Overdue ----
        pdf.setFont("Times-Roman", FONT_BODY)

        is_overdue = defect.get("is_overdue", False)

        if language == "en":
            y = draw_defect_field("Overdue Status", "Overdue" if is_overdue else "Not Overdue", y)
        else:
            y = draw_defect_field("Status Tertunggak", "Tertunggak" if is_overdue else "Tidak Tertunggak", y)

        # ---- Keutamaan (jika ada) ----
        if defect.get("priority"):
            y = draw_defect_field(labels["priority"], defect["priority"], y)

        # ---- Ulasan (Homeowner sahaja) ----
        if role == "Homeowner" and defect.get("remarks"):
            y = draw_defect_field(labels["remarks"], defect["remarks"], y)

        # ---- Bukti Kecacatan ----
        evidence_items = _evidence_items_from_meta({
            "files": defect.get("evidence_files") or [],
            "filename": defect.get("evidence_filename"),
            "uploaded_at": defect.get("evidence_uploaded_at"),
        })
        evidence_images = []
        for item in evidence_items:
            image_path = _resolve_evidence_image_path(
                evidence_dir,
                defect.get("id"),
                item.get("filename"),
            )
            if image_path:
                evidence_images.append((image_path, item.get("uploaded_at", "-")))

        # If evidence exists, draw all images side by side.
        if evidence_images:

            if y < 180:
                draw_footer(pdf, width, labels)
                pdf.showPage()
                y = height - 50

            pdf.setFont("Times-Roman", FONT_BODY)
            pdf.drawString(LABEL_X, y, f"{labels['evidence']}:")
            y -= 16

            thumb_width = 150
            thumb_height = 88
            thumb_gap = 10
            image_y = y - thumb_height
            pdf.setFont("Times-Roman", FONT_CAPTION)
            for index, (image_path, upload_time) in enumerate(evidence_images[:REQUIRED_EVIDENCE_IMAGE_COUNT]):
                image_x = LABEL_X + index * (thumb_width + thumb_gap)
                pdf.drawImage(
                    ImageReader(image_path),
                    image_x,
                    image_y,
                    width=thumb_width,
                    height=thumb_height
                )
                date_label = "Uploaded" if language == "en" else "Muat Naik"
                pdf.drawString(image_x, image_y - 10, f"{date_label}: {_format_display_timestamp(upload_time, language)}")

            y = image_y - 24

        # Space between defects
        y -= 25

    # ============================================
    # AI REPORT SECTION (Ringkasan Tuntutan)
    # ============================================
    if ai_report_text:
        draw_footer(pdf, width, labels)
        pdf.showPage()
        y = height - 50

        # Margins & spacing
        LEFT_MARGIN = 50
        PARAGRAPH_INDENT = 70
        RIGHT_MARGIN = width - 50
        LINE_HEIGHT = 15
        TEXT_WIDTH = RIGHT_MARGIN - PARAGRAPH_INDENT

        # AI Report Header (3-line format: AI Title, Tribunal Title, Generated Date)
        ai_title = labels.get(
            "ai_title",
            "AI-GENERATED CLAIM SUMMARY REPORT" if language == "en" else "LAPORAN RINGKASAN TUNTUTAN DIJANA AI",
        )
        report_title = _report_title_for_role(labels, role)
        generated_label = labels.get("generated_at", "Generated Date" if language == "en" else "Tarikh Jana")
        generated_value = _format_display_timestamp(_now_app_timezone().strftime("%Y-%m-%d %H:%M:%S"), language)
        role_key = (role or "").strip().lower()
        default_role_subtitles = {
            "ms": {
                "homeowner": "Laporan Sokongan Bagi Tuntutan Tribunal Tuntutan Pengguna Malaysia (TTPM)",
                "developer": "Laporan Pematuhan Bagi Rujukan Tribunal Tuntutan Pengguna Malaysia (TTPM)",
                "legal": "Laporan Gambaran Keseluruhan Pematuhan Tempoh Liabiliti Kecacatan (DLP)",
            },
            "en": {
                "homeowner": "Support Report for Claim before the Malaysia Consumer Claims Tribunal (TTPM)",
                "developer": "Compliance Report for Reference before the Malaysia Consumer Claims Tribunal (TTPM)",
                "legal": "Overview Report on Defect Liability Period (DLP) Compliance",
            },
        }
        fallback_subtitles = default_role_subtitles.get(language, default_role_subtitles["ms"])
        role_subtitles = tuple(
            value for value in (
                labels.get("homeowner_report_subtitle") or fallback_subtitles["homeowner"],
                labels.get("developer_report_subtitle") or fallback_subtitles["developer"],
                labels.get("legal_report_subtitle") or fallback_subtitles["legal"],
            )
            if value
        )
        if role_key == "homeowner":
            subtitle = labels.get("homeowner_report_subtitle") or fallback_subtitles["homeowner"]
        elif role_key == "developer":
            subtitle = labels.get("developer_report_subtitle") or fallback_subtitles["developer"]
        else:
            subtitle = labels.get("legal_report_subtitle") or fallback_subtitles["legal"]

        # Extract header lines and date in new order: AI Title, Tribunal Title, Date
        # Be permissive: titles may be on the same line (no newline) or separated by whitespace/newlines.
        header_match = re.match(
            rf"^\s*(?:{re.escape(ai_title)}|LAPORAN RINGKASAN TUNTUTAN DIJANA AI|AI-GENERATED CLAIM SUMMARY REPORT)"
            rf"(?:[\s\-â€“:.,]+|\n)+?(?:{re.escape(report_title)}|TRIBUNAL SUPPORT REPORT â€“ DEFECT LIABILITY PERIOD \(DLP\))"
            rf"(?:[\s\-â€“:.,]+|\n)+?(?:{re.escape(generated_label)}|Generated Date|Tarikh Jana)\s*:\s*(.+?)\s*(?:\n+|$)",
            ai_report_text or "",
            flags=re.IGNORECASE,
        )
        if header_match:
            generated_value = header_match.group(1).strip() or generated_value
            ai_report_text = ai_report_text[header_match.end():].lstrip()

        # Also defensively remove any duplicated header block that may appear
        # again later in the submitted text (some AI outputs or saved previews
        # occasionally include a second copy). Remove the first such block.
        try:
            subtitle_variants = "|".join(re.escape(item) for item in role_subtitles)
            subtitle_line_pattern = rf"(?:{subtitle_variants})" if subtitle_variants else re.escape(subtitle)
            # Allow titles to be on the same line or separated by newlines/whitespace/punctuation
            header_block_pattern = rf"(?:\s*(?:{re.escape(ai_title)})(?:[\s\-â€“:.,]+(?:{re.escape(report_title)}))?|(?:{re.escape(report_title)}))"
            header_block_pattern = rf"(?:{header_block_pattern}(?:[\s\-â€“:.,\n]+(?:{re.escape(generated_label)}\s*:\s*.*))?(?:[\s\-â€“:.,\n]+(?:{subtitle_line_pattern}))?\s*\n+)"
            ai_report_text = re.sub(header_block_pattern, "", ai_report_text, count=1, flags=re.IGNORECASE)
        except Exception:
            pass
        ai_report_text = _strip_known_report_header_lines(ai_report_text, language)

        # Draw header: for English include AI title + tribunal title; for Malay skip those
        page_width = width
        role_header_font_size = FONT_H2
        role_header_leading = 14
        if language == 'en':
            draw_centered_fitted_string(pdf, page_width / 2, y, ai_title, width - 100, "Times-Bold", FONT_H2)
            y -= 24
            y = draw_wrapped_text(pdf, report_title, LEFT_MARGIN, y, width - 100, "Times-Bold", role_header_font_size, role_header_leading)
        else:
            draw_centered_fitted_string(pdf, page_width / 2, y, ai_title, width - 100, "Times-Bold", FONT_H2)
            y -= 24

            y = draw_wrapped_text(pdf, report_title, LEFT_MARGIN, y, width - 100, "Times-Bold", role_header_font_size, role_header_leading)

        # Generated date (left-aligned) with extra spacing afterwards
        pdf.setFont("Times-Roman", FONT_BODY)
        date_line = f"{generated_label}: {generated_value}"
        draw_fitted_string(pdf, LEFT_MARGIN, y, date_line, width - 100, "Times-Roman", FONT_BODY)
        # add a larger gap between the date and the subtitle to match requested spacing
        y -= 28

        # Draw role-specific subtitle left-aligned and bold
        if subtitle and language == 'en':
            # Role subtitle: left-aligned at LEFT_MARGIN, bold, same size as other header lines
            subtitle_x = LEFT_MARGIN
            y = draw_wrapped_text(pdf, subtitle, subtitle_x, y, width - 100, "Times-Bold", role_header_font_size, role_header_leading)
            # Extra space after subtitle
            y -= 4
        elif subtitle and language != 'en':
            subtitle_x = LEFT_MARGIN
            y = draw_wrapped_text(pdf, subtitle, subtitle_x, y, width - 100, "Times-Bold", role_header_font_size, role_header_leading)
            y -= 4

        # Clean AI report text
        clean_text = ai_report_text
        clean_text = _strip_known_report_header_lines(clean_text, language)
        summary = report_data.get("summary_stats", {})

        clean_text = re.sub(
            r"Total number of defects.*?\.",
            f"Total number of defects reported is {summary.get('total_defects',0)}.",
            clean_text
        )
        # Remove any remaining header lines from body
        # Remove AI/tribunal header even if titles are concatenated on a single line
        clean_text = re.sub(
            rf"^\s*(?:{re.escape(ai_title)}|LAPORAN RINGKASAN TUNTUTAN DIJANA AI|AI-GENERATED CLAIM SUMMARY REPORT)(?:[\s\-â€“:.,]+(?:{re.escape(report_title)}|TRIBUNAL SUPPORT REPORT â€“ DEFECT LIABILITY PERIOD \(DLP\)))?\s*(?:\n|[\s\-â€“:.,])*",
            "",
            clean_text,
            flags=re.IGNORECASE,
        )
        clean_text = re.sub(
            rf"^\s*(?:{re.escape(report_title)}|TRIBUNAL SUPPORT REPORT â€“ DEFECT LIABILITY PERIOD \(DLP\))\s*\n",
            "",
            clean_text,
            flags=re.IGNORECASE,
        )
        clean_text = re.sub(
            rf"^\s*(?:{re.escape(generated_label)}|Generated Date|Tarikh Jana)\s*:\s*.*$\n?",
            "",
            clean_text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        clean_text = clean_text.replace('**', '')
        clean_text = clean_text.replace('*', '')
        clean_text = clean_text.replace('##', '')
        clean_text = clean_text.replace('#', '')
        clean_text = clean_text.replace('\r\n', '\n')
        clean_text = clean_text.replace('\r', '\n')
        clean_text = clean_text.encode("utf-8", "ignore").decode("utf-8")
        clean_text = normalize_report_section_spacing(clean_text)
        clean_text = normalize_legal_statistics_section(clean_text)
        if role == "Legal":
            clean_text = enforce_legal_statistics_section_counts(
                clean_text,
                language,
                report_data.get("summary_stats", {}),
            )
        for subtitle_variant in role_subtitles:
            clean_text = re.sub(
                rf"^\s*{re.escape(subtitle_variant)}\s*$\n?",
                "",
                clean_text,
                flags=re.IGNORECASE | re.MULTILINE,
            )
        # Defensively remove any repeated header blocks or stray header/title/date
        try:
            header_variants = rf"(?:{re.escape(ai_title)}|LAPORAN RINGKASAN TUNTUTAN DIJANA AI|AI-GENERATED CLAIM SUMMARY REPORT)"
            report_title_variants = rf"(?:{re.escape(report_title)}|TRIBUNAL SUPPORT REPORT â€“ DEFECT LIABILITY PERIOD \(DLP\))"
            date_label_variants = rf"(?:{re.escape(generated_label)}|Generated Date|Tarikh Jana)"

            # Pattern matching a full 3-line header (title, report title, generated date) possibly repeated
            repeated_header_pattern = rf"(?:\s*{header_variants}\s*\n\s*{report_title_variants}\s*\n\s*{date_label_variants}\s*:\s*.*?(?:\n|$))+"
            clean_text = re.sub(repeated_header_pattern, "", clean_text, flags=re.IGNORECASE)

            # Also remove any stray single-line header/report/date occurrences
            clean_text = re.sub(rf"^\s*{header_variants}\s$", "", clean_text, flags=re.IGNORECASE | re.MULTILINE)
            clean_text = re.sub(rf"^\s*{report_title_variants}\s$", "", clean_text, flags=re.IGNORECASE | re.MULTILINE)
            clean_text = re.sub(rf"^\s*{date_label_variants}\s*:\s*.*$", "", clean_text, flags=re.IGNORECASE | re.MULTILINE)
            for subtitle_variant in role_subtitles:
                clean_text = re.sub(rf"^\s*{re.escape(subtitle_variant)}\s*$", "", clean_text, flags=re.IGNORECASE | re.MULTILINE)
        except Exception:
            pass
        # TRANSLATE STATUS/OVERDUE/HDA/PRIORITY INSIDE AI REPORT TEXT
        if language == "en":
            clean_text = clean_text.replace("Status: Telah Diselesaikan", "Status: Completed")
            clean_text = clean_text.replace("Status: Belum Diselesaikan", "Status: Pending")
            clean_text = clean_text.replace("Status: Dalam Semakan", "Status: Pending")
            clean_text = clean_text.replace("Status: Dalam Tindakan", "Status: In Progress")
            clean_text = clean_text.replace("Status: Dalam Proses Pematuhan", "Status: In Progress")
            clean_text = clean_text.replace("Status: Tertangguh", "Status: Delayed")

            clean_text = clean_text.replace("Unit Pihak Yang Menuntut:", "Claimant Unit:")
            clean_text = clean_text.replace("Kecacatan Berkaitan Pihak Yang Menuntut:", "Defects Related to Claimant:")
            clean_text = clean_text.replace("Kecacatan Lain Dalam Kes:", "Other Defects in Case:")
            clean_text = clean_text.replace("Maklumat Pemilik Menuntut:", "Claimant Owner Closed Case Records:")
            clean_text = clean_text.replace("Rekod Kes Ditutup Pemilik Menuntut:", "Claimant Owner Closed Case Records:")
            clean_text = clean_text.replace("Unit Pemilik Menuntut:", "Claimant Owner Unit:")
            clean_text = clean_text.replace("Senarai Kecacatan Pemilik Lain Dalam Kes:", "Other Owner Defect List in Case:")
            clean_text = clean_text.replace("Senarai Kecacatan Pemilik Menuntut:", "Claimant Owner Defect List:")
            clean_text = clean_text.replace("Maklumat Pemilik Lain:", "Other Owner Closed Case Records:")
            clean_text = clean_text.replace("Rekod Kes Ditutup Pemilik Lain Lain:", "Other Owner Closed Case Records:")
            clean_text = clean_text.replace("Rekod Kes Ditutup Pemilik Lain:", "Other Owner Closed Case Records:")
            clean_text = clean_text.replace("Unit Pemilik Lain:", "Other Owner Unit:")
            clean_text = clean_text.replace("Senarai Kecacatan Pemilik Lain:", "Other Owner Defect List:")

            clean_text = clean_text.replace("Status Tertunggak:", "Overdue Status:")
            clean_text = clean_text.replace("Pematuhan HDA (30 Hari):", "HDA Compliance Status:")
            clean_text = clean_text.replace("Status Pematuhan HDA:", "HDA Compliance Status:")

            clean_text = re.sub(r"^\s*Overdue\s*Status\s*:\s*(Ya|Yes|Tertunggak|Overdue)\s*$", "   Overdue Status: Overdue", clean_text, flags=re.IGNORECASE | re.MULTILINE)
            clean_text = re.sub(r"^\s*Overdue\s*Status\s*:\s*(Tidak|No|Tidak Tertunggak|Not Overdue)\s*$", "   Overdue Status: Not Overdue", clean_text, flags=re.IGNORECASE | re.MULTILINE)
            clean_text = re.sub(r"^\s*HDA\s*Compliance(?:\s*\(30\s*Days\)|\s*Status)?\s*:\s*(Ya|Yes|Mematuhi|Compliant)\s*$", "   HDA Compliance Status: Compliant", clean_text, flags=re.IGNORECASE | re.MULTILINE)
            clean_text = re.sub(r"^\s*HDA\s*Compliance(?:\s*\(30\s*Days\)|\s*Status)?\s*:\s*(Tidak Mematuhi|Non-Compliant|Tidak|No)\s*$", "   HDA Compliance Status: Non-Compliant", clean_text, flags=re.IGNORECASE | re.MULTILINE)
            clean_text = re.sub(r"^\s*HDA\s*Compliance(?:\s*\(30\s*Days\)|\s*Status)?\s*:\s*(Dalam Semakan|Under Review)\s*$", "   HDA Compliance Status: Non-Compliant", clean_text, flags=re.IGNORECASE | re.MULTILINE)

            clean_text = clean_text.replace("Keutamaan:", "Priority:")
        else:
            clean_text = clean_text.replace("Status: Completed", "Status: Telah Diselesaikan")
            clean_text = clean_text.replace("Status: Pending", "Status: Belum Diselesaikan")
            clean_text = clean_text.replace("Status: Under Review", "Status: Belum Diselesaikan")
            clean_text = clean_text.replace("Status: In Progress", "Status: Dalam Tindakan")
            clean_text = clean_text.replace("Status: Compliance In Progress", "Status: Dalam Tindakan")
            clean_text = clean_text.replace("Status: Delayed", "Status: Tertangguh")

            clean_text = clean_text.replace("Status Semasa: Completed", "Status Semasa: Telah Diselesaikan")
            clean_text = clean_text.replace("Status Semasa: Pending", "Status Semasa: Belum Diselesaikan")
            clean_text = clean_text.replace("Status Semasa: Under Review", "Status Semasa: Belum Diselesaikan")
            clean_text = clean_text.replace("Status Semasa: In Progress", "Status Semasa: Dalam Tindakan")
            clean_text = clean_text.replace("Status Semasa: Compliance In Progress", "Status Semasa: Dalam Tindakan")
            clean_text = clean_text.replace("Status Semasa: Delayed", "Status Semasa: Tertangguh")

            clean_text = clean_text.replace("Current Status: Completed", "Status Semasa: Telah Diselesaikan")
            clean_text = clean_text.replace("Current Status: Pending", "Status Semasa: Belum Diselesaikan")
            clean_text = clean_text.replace("Current Status: Under Review", "Status Semasa: Belum Diselesaikan")
            clean_text = clean_text.replace("Current Status: In Progress", "Status Semasa: Dalam Tindakan")
            clean_text = clean_text.replace("Current Status: Compliance In Progress", "Status Semasa: Dalam Tindakan")
            clean_text = clean_text.replace("Current Status: Delayed", "Status Semasa: Tertangguh")

            clean_text = clean_text.replace("Claimant Unit:", "Unit Pihak Yang Menuntut:")
            clean_text = clean_text.replace("Defects Related to Claimant:", "Kecacatan Berkaitan Pihak Yang Menuntut:")
            clean_text = clean_text.replace("Other Defects in Case:", "Kecacatan Lain Dalam Kes:")
            clean_text = clean_text.replace("Claimant Owner Details:", "Rekod Kes Ditutup Pemilik Menuntut:")
            clean_text = clean_text.replace("Claimant Owner Closed Case Records:", "Rekod Kes Ditutup Pemilik Menuntut:")
            clean_text = clean_text.replace("Claimant Owner Unit:", "Unit Pemilik Menuntut:")
            clean_text = clean_text.replace("Other Owner Defect List in Case:", "Senarai Kecacatan Pemilik Lain Dalam Kes:")
            clean_text = clean_text.replace("Claimant Owner Defect List:", "Senarai Kecacatan Pemilik Menuntut:")
            clean_text = clean_text.replace("Other Owner Details:", "Rekod Kes Ditutup Pemilik Lain:")
            clean_text = clean_text.replace("Other Owner Closed Case Records:", "Rekod Kes Ditutup Pemilik Lain:")
            clean_text = clean_text.replace("Other Owner Unit:", "Unit Pemilik Lain:")
            clean_text = clean_text.replace("Other Owner Defect List:", "Senarai Kecacatan Pemilik Lain:")

            clean_text = clean_text.replace("Overdue Status:", "Status Tertunggak:")
            clean_text = clean_text.replace("HDA Compliance (30 Days):", "Status Pematuhan HDA:")
            clean_text = clean_text.replace("HDA Compliance Status:", "Status Pematuhan HDA:")

            clean_text = re.sub(r"^\s*Status\s*Tertunggak\s*:\s*(Yes|Ya|Overdue|Tertunggak)\s*$", "   Status Tertunggak: Tertunggak", clean_text, flags=re.IGNORECASE | re.MULTILINE)
            clean_text = re.sub(r"^\s*Status\s*Tertunggak\s*:\s*(No|Tidak|Not Overdue|Tidak Tertunggak)\s*$", "   Status Tertunggak: Tidak Tertunggak", clean_text, flags=re.IGNORECASE | re.MULTILINE)
            clean_text = re.sub(r"^\s*(?:Pematuhan\s*HDA\s*\(30\s*Hari\)|Status\s*Pematuhan\s*HDA)\s*:\s*(Yes|Ya|Compliant|Mematuhi)\s*$", "   Status Pematuhan HDA: Mematuhi", clean_text, flags=re.IGNORECASE | re.MULTILINE)
            clean_text = re.sub(r"^\s*(?:Pematuhan\s*HDA\s*\(30\s*Hari\)|Status\s*Pematuhan\s*HDA)\s*:\s*(Tidak Mematuhi|Non-Compliant|No|Tidak)\s*$", "   Status Pematuhan HDA: Tidak Mematuhi", clean_text, flags=re.IGNORECASE | re.MULTILINE)
            clean_text = re.sub(r"^\s*(?:Pematuhan\s*HDA\s*\(30\s*Hari\)|Status\s*Pematuhan\s*HDA)\s*:\s*(Under Review|Dalam Semakan)\s*$", "   Status Pematuhan HDA: Tidak Mematuhi", clean_text, flags=re.IGNORECASE | re.MULTILINE)

            clean_text = clean_text.replace("Priority:", "Keutamaan:")
        clean_text = normalize_priority_values_for_language(clean_text, language)
        clean_text = normalize_report_date_values(clean_text, language)
        clean_text = normalize_defect_detail_indentation(clean_text)

        # =================================================
        # FIX REMARKS LANGUAGE USING DEFECT DATA (AUTHORITATIVE)
        # =================================================
        if language == "ms":
            for defect in defects:
                if defect.get("remarks"):
                    clean_text = clean_text.replace(
                        "Ulasan:",
                        "Ulasan:"
                    )

        elif language == "en":
            for defect in defects:
                if defect.get("remarks"):
                    clean_text = clean_text.replace(
                        "Remarks:",
                        "Remarks:"
                    )

        # Split AI report into lines
        lines = clean_text.split('\n')

        MAIN_SECTION_HEADER_PREFIXES = (
            'PENAFIAN AI',
            'Penafian AI',
            'AI Disclaimer',
            'AI DISCLAIMER',
            'Laporan Sokongan',
            'Laporan Pematuhan',
            'Laporan Gambaran',
            'Claimant Unit',
            'Unit Pihak Yang Menuntut',
            'Claimant Owner Details',
            'Claimant Owner Closed Case Records',
            'Claimant Owner Unit',
            'Claimant Owner Defect List',
            'Other Owner Defect List',
            'Maklumat Pemilik Menuntut',
            'Rekod Kes Ditutup Pemilik Menuntut',
            'Rekod Kes Ditutup Pemilik Lain',
            'Unit Pemilik Menuntut',
            'Senarai Kecacatan Pemilik Menuntut',
            'Senarai Kecacatan Pemilik Lain',
            'Defects Related to Claimant',
            'Kecacatan Berkaitan Pihak Yang Menuntut',
            'Other Defects in Case',
            'Kecacatan Lain Dalam Kes',
            'Purpose of the Report',
            'Summary of Reported Defects',
            'Defect List',
            'Defects That Have Exceeded',
            'Formal Request',
            'Conclusion',
            'Tribunal Support Report',
        )

        def _estimate_wrapped_lines(text, max_width, font_size=FONT_BODY):
            text = str(text or "")
            prefix_match = re.match(r"^([^:]{1,90}:\s+)(.+)$", text)
            if prefix_match:
                prefix_width = pdf.stringWidth(prefix_match.group(1), "Times-Roman", font_size)
                text = prefix_match.group(2)
                max_width = max_width - prefix_width

            words = text.split()
            if not words:
                return 1

            count = 0
            current_line = ""
            for word in words:
                test_line = current_line + " " + word if current_line else word
                if pdf.stringWidth(test_line, "Times-Roman", font_size) <= max_width:
                    current_line = test_line
                else:
                    count += 1
                    current_line = word
            if current_line:
                count += 1
            return max(count, 1)

        def _is_main_section_header(text):
            if not text:
                return False

            if re.match(r"^\d+\.\s", text):
                return True

            return text.startswith(MAIN_SECTION_HEADER_PREFIXES)

        def _uses_expanded_section_gap(text):
            if not text:
                return False
            return bool(re.match(
                r"^(?:"
                r"1\.\s+Tujuan\s+Laporan|"
                r"1\.\s+Purpose\s+of\s+the\s+Report|"
                r"1\.\s+Latar\s+Belakang\s+Kes|"
                r"1\.\s+Case\s+Background|"
                r"5\.\s+Pemerhatian\s+Berkaitan\s+Pematuhan\s+Tempoh|"
                r"5\.\s+Observations\s+on\s+Timeframe\s+Compliance|"
                r"4\.\s+Pemerhatian\s+Berkaitan\s+Pematuhan\s+dan\s+Tarikh\s+Akhir|"
                r"3\.\s+Pemerhatian\s+Berkaitan\s+Status\s+dan\s+Tempoh|"
                r"3\.\s+Recorded\s+Status\s+and\s+Timeframe\s+Observations"
                r")$",
                text,
                flags=re.IGNORECASE,
            ))

        def _is_subtopic_header(text):
            if not text:
                return False
            return bool(re.match(r"^[A-Za-z]\.\s", text))

        def _is_keep_together_header(text):
            return _is_main_section_header(text) or _is_subtopic_header(text)

        def _required_keep_with_next_height(start_idx):
            current = lines[start_idx].strip()
            current_is_main = _is_main_section_header(current)
            seen_first_subtopic = False

            block_end = len(lines)
            for j in range(start_idx + 1, len(lines)):
                nxt = lines[j].strip()
                if current_is_main:
                    if _is_main_section_header(nxt):
                        block_end = j
                        break
                    if _is_subtopic_header(nxt):
                        if seen_first_subtopic:
                            block_end = j
                            break
                        seen_first_subtopic = True
                elif _is_keep_together_header(nxt):
                    block_end = j
                    break

            required_height = 0
            for j in range(start_idx, block_end):
                candidate = lines[j].strip()
                if not candidate:
                    required_height += 8
                else:
                    wrapped_count = _estimate_wrapped_lines(candidate, TEXT_WIDTH)
                    required_height += wrapped_count * LINE_HEIGHT

            return required_height

        def _minimum_keep_with_next_height(start_idx):
            current = lines[start_idx].strip()
            keep_lines = 1
            non_empty_after = 0
            max_following_lines = 4 if _is_main_section_header(current) else 3

            for j in range(start_idx + 1, len(lines)):
                candidate = lines[j].strip()
                if not candidate:
                    keep_lines += 1
                    continue
                if _is_main_section_header(candidate):
                    break

                keep_lines += _estimate_wrapped_lines(candidate, TEXT_WIDTH)
                non_empty_after += 1
                if non_empty_after >= max_following_lines:
                    break

            return max(keep_lines * LINE_HEIGHT, LINE_HEIGHT)

        prev_line_is_sub_item = False

        for idx, line in enumerate(lines):
            # Empty line spacing
            if not line.strip():
                y -= 8
                prev_line_is_sub_item = False
                continue

            # Page break
            if y < 80:
                draw_footer(pdf, width, labels)
                pdf.showPage()
                y = height - 50

            stripped = line.strip()

            # Keep each header/subtopic block together when possible.
            if _is_keep_together_header(stripped):
                required_height = _required_keep_with_next_height(idx)
                minimum_height = _minimum_keep_with_next_height(idx)

                page_usable_height = (height - 50) - 80
                if (
                    (required_height <= page_usable_height and y - required_height < 80)
                    or y - minimum_height < 80
                ):
                    draw_footer(pdf, width, labels)
                    pdf.showPage()
                    y = height - 50

            # -----------------------------------------
            # FORMAL SPACING RULES (TRIBUNAL-GRADE)
            # -----------------------------------------

            # Extra space before main sections (numbered or named like PENAFIAN AI)
            if _is_main_section_header(stripped):
                y -= 12   # space before new main section
                if _uses_expanded_section_gap(stripped):
                    y -= 8
                if re.match(r"^(AI\s+DISCLAIMER|PENAFIAN\s+AI)\s*:", stripped, flags=re.IGNORECASE):
                    y -= 4

            # Extra space before lettered items (A., B., C.)
            if stripped[:2] in ["A.", "B.", "C.", "D.", "E.", "F."]:
                y -= 8    # space before each defect item

            # Detect headers (LEFT ALIGN ONLY)
            is_numbered_header = _is_main_section_header(stripped)
            is_role_subtitle = any(
                stripped.lower() == subtitle_variant.lower()
                for subtitle_variant in role_subtitles
            )

            lower_line = stripped.lower()
            SUB_ITEM_PREFIXES = tuple(f"{chr(i)}." for i in range(ord('a'), ord('z') + 1))
            is_sub_item = lower_line.startswith(SUB_ITEM_PREFIXES)

            # Defect detail fields
            BASE_FIELDS = (
                "unit:",
                "status:",
            )

            MS_FIELDS = (
                "keterangan:",
                "keutamaan:",
                "ulasan:",
                "tarikh dilaporkan:",
                "tarikh siap dijadualkan:",
                "tarikh siap:",
                "tarikh siap sebenar:",
                "tempoh siap (hari):",
                "status tertunggak:",
                "status semasa:",
                "pematuhan hda (30 hari):",
                "status pematuhan hda:",
            )

            EN_FIELDS = (
                "description:",
                "priority:",
                "remarks:",
                "reported date:",
                "scheduled completion date:",
                "actual completion date:",
                "days to complete:",
                "current status:",
                "overdue status:",
                "hda compliance (30 days):",
                "hda compliance status:",
            )

            DEFECT_FIELD_PREFIXES = BASE_FIELDS + MS_FIELDS + EN_FIELDS
            is_defect_field = stripped.lower().startswith(DEFECT_FIELD_PREFIXES)
            LEGAL_STAT_FIELDS = {
                "jumlah keseluruhan kecacatan",
                "telah diselesaikan",
                "kes ditutup",
                "masih belum diselesaikan",
                "direkodkan sebagai tertunggak",
                "tidak mematuhi tempoh 30 hari hda",
                "total recorded defects",
                "completed",
                "closed cases",
                "still unresolved",
                "recorded as overdue",
                "non-compliant with 30-day hda requirement",
            }

            # Font & indent
            if is_role_subtitle:
                pdf.setFont("Times-Bold", FONT_H2)
                x_pos = PARAGRAPH_INDENT
                wrap_font_name = "Times-Bold"
                wrap_font_size = FONT_H2
            elif is_numbered_header:
                pdf.setFont("Times-Bold", FONT_H2)
                x_pos = LEFT_MARGIN
                wrap_font_name = "Times-Bold"
                wrap_font_size = FONT_H3
            elif is_sub_item:
                pdf.setFont("Times-Bold", FONT_H2)
                x_pos = LEFT_MARGIN + 20
                wrap_font_name = "Times-Bold"
                wrap_font_size = FONT_BODY
            else:
                pdf.setFont("Times-Roman", FONT_BODY)
                wrap_font_name = "Times-Roman"
                wrap_font_size = FONT_BODY
                if is_defect_field:
                    x_pos = LEFT_MARGIN + 40
                else:
                    x_pos = PARAGRAPH_INDENT

            prev_line_is_sub_item = is_sub_item
            effective_text_width = RIGHT_MARGIN - x_pos

            if not (is_numbered_header or is_role_subtitle or is_sub_item):
                colon_match = re.match(r"^([^:]{1,90})\s*:\s+(.+)$", stripped)
                if colon_match:
                    label_text = colon_match.group(1).strip()
                    value_text = colon_match.group(2).strip()
                    is_legal_stat_field = label_text.lower() in LEGAL_STAT_FIELDS
                    colon_x = 335 if is_legal_stat_field else 230
                    value_x = colon_x + 14
                    if not is_legal_stat_field and pdf.stringWidth(label_text, wrap_font_name, wrap_font_size) > (colon_x - x_pos - 6):
                        colon_x = min(
                            x_pos + pdf.stringWidth(label_text, wrap_font_name, wrap_font_size) + 8,
                            RIGHT_MARGIN - 120,
                        )
                        value_x = colon_x + 14

                    pdf.setFont(wrap_font_name, wrap_font_size)
                    pdf.drawString(x_pos, y, label_text)
                    pdf.drawString(colon_x, y, ":")
                    y = draw_wrapped_text(
                        pdf,
                        value_text,
                        value_x,
                        y,
                        RIGHT_MARGIN - value_x,
                        wrap_font_name,
                        wrap_font_size,
                        LINE_HEIGHT,
                    )
                    continue

            # ============================================
            # WORD WRAP + JUSTIFY (ISI PERENGGAN SAHAJA)
            # ============================================
            words = stripped.split()
            current_line = ""

            for word in words:
                test_line = current_line + " " + word if current_line else word
                if pdf.stringWidth(test_line, wrap_font_name, wrap_font_size) <= effective_text_width:
                    current_line = test_line
                else:
                    if is_numbered_header or is_role_subtitle:
                        # Header â†’ kiri sahaja
                        pdf.setFont(wrap_font_name, wrap_font_size)
                        pdf.drawString(x_pos, y, current_line)
                    else:
                        # ISI â†’ JUSTIFY DI SINI
                        draw_justified_line(
                            pdf,
                            current_line,
                            x_pos,
                            y,
                            effective_text_width,
                            "Times-Roman",
                            FONT_BODY
                        )

                    y -= LINE_HEIGHT
                    if y < 80:
                        draw_footer(pdf, width, labels)
                        pdf.showPage()
                        y = height - 50
                        pdf.setFont(wrap_font_name, wrap_font_size)

                    current_line = word

            # Last line (JANGAN justify â€“ standard dokumen rasmi)
            if current_line:
                pdf.setFont(wrap_font_name, wrap_font_size)
                pdf.drawString(x_pos, y, current_line)
                y -= LINE_HEIGHT

    # ============================================
    # APPENDIX: CLOSED CASE DETAILS (SAME FORMAT AS AI PREVIEW)
    # ============================================
    if role in ["Homeowner", "Developer", "Legal", "Admin"]:
        draw_footer(pdf, width, labels)
        pdf.showPage()
        y = height - 50

        appendix_lines = build_closed_appendix_lines(closed_evidence_appendix, language)
        current_appendix_item = None
        appendix_font_size = FONT_BODY
        appendix_line_height = 16

        def _is_appendix_header(text):
            return bool(
                re.match(r"^[A-Z]\.\s+(Defect ID|Kecacatan ID)", text)
                or re.match(r"^\d+\.\s+(Defect ID|Kecacatan ID)", text)
                or text.startswith("APPENDIX A:")
                or text.startswith("LAMPIRAN A:")
                or text.startswith("Maklumat Pemilik Menuntut:")
                or text.startswith("Maklumat Pemilik Lain:")
                or text.startswith("Rekod Kes Ditutup Pemilik Menuntut:")
                or text.startswith("Rekod Kes Ditutup Pemilik Lain:")
                or text.startswith("Unit Pemilik Lain:")
                or text.startswith("Senarai Kecacatan Pemilik Menuntut:")
                or text.startswith("Senarai Kecacatan Pemilik Lain:")
                or text.startswith("Senarai Kecacatan Pemilik Lain Dalam Kes:")
                or text.startswith("Claimant Owner Details:")
                or text.startswith("Claimant Owner Closed Case Records:")
                or text.startswith("Claimant Owner Unit:")
                or text.startswith("Claimant Owner Defect List:")
                or text.startswith("Other Owner Details:")
                or text.startswith("Other Owner Closed Case Records:")
                or text.startswith("Other Owner Unit:")
                or text.startswith("Other Owner Defect List:")
                or text.startswith("Other Owner Defect List in Case:")
            )

        def _appendix_line_style(text):
            stripped_text = (text or "").strip()
            field_label = stripped_text.split(":", 1)[0].strip() if ":" in stripped_text else stripped_text
            if not stripped_text:
                return "Times-Roman", appendix_font_size, 50

            if stripped_text.startswith(("APPENDIX A:", "LAMPIRAN A:")):
                return "Times-Bold", FONT_H2, 50

            if stripped_text.startswith((
                "Maklumat Pemilik Menuntut:",
                "Maklumat Pemilik Lain:",
                "Rekod Kes Ditutup Pemilik Menuntut:",
                "Rekod Kes Ditutup Pemilik Lain:",
                "Senarai Kecacatan Pemilik Menuntut:",
                "Senarai Kecacatan Pemilik Lain:",
                "Senarai Kecacatan Pemilik Lain Dalam Kes:",
                "Claimant Owner Details:",
                "Claimant Owner Closed Case Records:",
                "Claimant Owner Defect List:",
                "Other Owner Details:",
                "Other Owner Closed Case Records:",
                "Other Owner Defect List:",
                "Other Owner Defect List in Case:",
            )):
                return "Times-Bold", appendix_font_size, 50

            if stripped_text.startswith((
                "Claimant Owner Unit:",
                "Other Owner Unit:",
                "Unit Pemilik Menuntut:",
                "Unit Pemilik Lain:",
            )):
                return "Times-Roman", appendix_font_size, 70

            if stripped_text in (
                "Tiada rekod kes ditutup yang tersedia pada masa ini.",
                "No closed case records are currently available.",
            ):
                return "Times-Roman", appendix_font_size, 70

            if re.match(r"^[A-Z]\.|^\d+\.", stripped_text):
                return "Times-Bold", appendix_font_size, 50

            if field_label in (
                "Unit",
                "Tarikh Dilaporkan",
                "Tarikh Siap",
                "Tempoh Siap (Hari)",
                "Pematuhan HDA (30 Hari)",
                "Status Pematuhan HDA",
                "Peraturan Ditutup",
                "Muat Naik",
                "Reported Date",
                "Completed",
                "Days to Complete",
                "HDA Compliance (30 Days)",
                "HDA Compliance Status",
                "Closed Rule",
                "Uploaded",
            ):
                return "Times-Roman", FONT_BODY, 70

            if stripped_text.startswith((
                "Unit:",
                "Tarikh Dilaporkan:",
                "Tarikh Siap:",
                "Tempoh Siap (Hari):",
                "Pematuhan HDA (30 Hari):",
                "Status Pematuhan HDA:",
                "Peraturan Ditutup:",
                "Muat Naik:",
                "Gambar Kecacatan:",
                "Muat Naik:",
                "Reported Date:",
                "Completed:",
                "Days to Complete:",
                "HDA Compliance (30 Days):",
                "HDA Compliance Status:",
                "Closed Rule:",
                "Uploaded:",
                "Defect Image:",
            )):
                return "Times-Roman", FONT_BODY, 70

            return "Times-Roman", appendix_font_size, 50

        appendix_field_labels = {
            "Unit",
            "Tarikh Dilaporkan",
            "Tarikh Siap",
            "Tempoh Siap (Hari)",
            "Pematuhan HDA (30 Hari)",
            "Status Pematuhan HDA",
            "Peraturan Ditutup",
            "Muat Naik",
            "Reported Date",
            "Completed",
            "Days to Complete",
            "HDA Compliance (30 Days)",
            "HDA Compliance Status",
            "Closed Rule",
            "Uploaded",
        }

        def _appendix_field_parts(text):
            stripped_text = (text or "").strip()
            if stripped_text.startswith(("Defect Image:", "Gambar Kecacatan:")):
                return None
            match = re.match(r"^(.{1,80}?)\s*:\s*(.*)$", stripped_text)
            if not match:
                return None
            label = match.group(1).strip()
            if label not in appendix_field_labels:
                return None
            return label, match.group(2).strip()

        def _draw_appendix_field(text, y_position):
            parts = _appendix_field_parts(text)
            if not parts:
                return None
            label, value = parts
            label_x = 70
            colon_x = 230 if language == "ms" else 220
            value_x = colon_x + 14
            pdf.setFont("Times-Roman", FONT_BODY)
            pdf.drawString(label_x, y_position, label)
            pdf.drawString(colon_x, y_position, ":")
            return draw_wrapped_text(
                pdf,
                value or "-",
                value_x,
                y_position,
                width - value_x - 50,
                "Times-Roman",
                FONT_BODY,
                appendix_line_height,
            )

        for idx, raw_line in enumerate(appendix_lines):
            line = (raw_line or "").rstrip()

            if y < 80:
                draw_footer(pdf, width, labels)
                pdf.showPage()
                y = height - 50

            if not line:
                y -= 9
                continue

            is_header = _is_appendix_header(line)
            is_owner_block_header = line.startswith((
                "Maklumat Pemilik Menuntut:",
                "Maklumat Pemilik Lain:",
                "Rekod Kes Ditutup Pemilik Menuntut:",
                "Rekod Kes Ditutup Pemilik Lain:",
                "Claimant Owner Details:",
                "Claimant Owner Closed Case Records:",
                "Other Owner Details:",
                "Other Owner Closed Case Records:",
            ))
            is_defect_list_header = line.startswith((
                "Senarai Kecacatan Pemilik Menuntut:",
                "Senarai Kecacatan Pemilik Lain:",
                "Senarai Kecacatan Pemilik Lain Dalam Kes:",
                "Claimant Owner Defect List:",
                "Other Owner Defect List:",
                "Other Owner Defect List in Case:",
            ))
            is_defect_header = bool(re.match(r"^(?:[A-Z]|\d+)\.\s+(?:Defect ID|Kecacatan ID)\s+[^:]+:", line))
            is_image_label = line.startswith(("Defect Image:", "Gambar Kecacatan:"))

            if is_owner_block_header:
                y -= 8
            elif is_defect_list_header:
                y -= 4
            elif is_defect_header:
                y -= 7
            elif is_image_label:
                y -= 5

            header_match = re.match(r"^(?:[A-Z]|\d+)\.\s+(?:Defect ID|Kecacatan ID)\s+([^:]+):", line)
            if header_match:
                defect_id_text = header_match.group(1).strip()
                current_appendix_item = next(
                    (
                        item
                        for item in _closed_appendix_snapshot_rows(closed_evidence_appendix)
                        if str(item.get("id")) == defect_id_text
                    ),
                    None,
                )

                # Keep one full appendix item together when there is enough space on a fresh page.
                appendix_images = []
                if current_appendix_item:
                    for evidence_item in _closed_appendix_evidence_items(current_appendix_item):
                        appendix_image_path = _resolve_evidence_image_path(
                            evidence_dir,
                            current_appendix_item.get("id"),
                            evidence_item.get("filename"),
                        )
                        if appendix_image_path:
                            appendix_images.append((appendix_image_path, evidence_item.get("uploaded_at", "-")))

                block_end = len(appendix_lines)
                for j in range(idx + 1, len(appendix_lines)):
                    nxt = (appendix_lines[j] or "").strip()
                    if not nxt:
                        block_end = j + 1
                        break

                required_height = 0
                for j in range(idx, block_end):
                    candidate = (appendix_lines[j] or "").strip()
                    if not candidate:
                        required_height += 10
                    else:
                        wrapped_count = _estimate_wrapped_lines(candidate, width - 100, appendix_font_size)
                        required_height += wrapped_count * appendix_line_height

                if appendix_images:
                    required_height += 142

                if current_appendix_item and idx + 1 < len(appendix_lines):
                    next_line = (appendix_lines[idx + 1] or "").strip()
                    if next_line.startswith(("Uploaded:", "Muat Naik:")):
                        required_height += appendix_line_height

                page_usable_height = (height - 50) - 80
                if required_height <= page_usable_height and y - required_height < 80:
                    draw_footer(pdf, width, labels)
                    pdf.showPage()
                    y = height - 50

            font_name, font_size, x = _appendix_line_style(line)

            if line.startswith(":"):
                x = 70
            if line.startswith(("APPENDIX A:", "LAMPIRAN A:")):
                draw_centered_fitted_string(pdf, width / 2, y, line, width - 100, font_name, FONT_H2)
                y -= appendix_line_height + 3
                continue

            rendered_line = line.lstrip() if line.startswith(" ") else line
            field_y = _draw_appendix_field(rendered_line, y)
            if field_y is not None:
                y = field_y
                continue

            y = draw_wrapped_text(pdf, rendered_line, x, y, width - 100, font_name, font_size, appendix_line_height)

            if line.startswith("Defect Image:") or line.startswith("Gambar Kecacatan:"):
                appendix_images = []
                if current_appendix_item:
                    for evidence_item in _closed_appendix_evidence_items(current_appendix_item):
                        appendix_image_path = _resolve_evidence_image_path(
                            evidence_dir,
                            current_appendix_item.get("id"),
                            evidence_item.get("filename"),
                        )
                        if appendix_image_path:
                            appendix_images.append((appendix_image_path, evidence_item.get("uploaded_at", "-")))

                if appendix_images:
                    if y < 205:
                        draw_footer(pdf, width, labels)
                        pdf.showPage()
                        y = height - 50

                    thumb_width = 150
                    thumb_height = 88
                    thumb_gap = 10
                    y -= 8
                    image_y = y - thumb_height
                    pdf.setFont("Times-Roman", FONT_CAPTION)
                    date_label = "Uploaded" if language == "en" else "Muat Naik"
                    for image_index, (appendix_image_path, upload_time) in enumerate(
                        appendix_images[:REQUIRED_EVIDENCE_IMAGE_COUNT]
                    ):
                        image_x = 70 + image_index * (thumb_width + thumb_gap)
                        pdf.drawImage(
                            ImageReader(appendix_image_path),
                            image_x,
                            image_y,
                            width=thumb_width,
                            height=thumb_height,
                        )
                        pdf.drawString(image_x, image_y - 10, f"{date_label}: {_format_display_timestamp(upload_time, language)}")

                    y = image_y - 30

            if line.startswith(("Uploaded:", "Muat Naik:")):
                y -= 4

            if line.startswith((
                "Maklumat Pemilik Menuntut:",
                "Maklumat Pemilik Lain:",
                "Rekod Kes Ditutup Pemilik Menuntut:",
                "Rekod Kes Ditutup Pemilik Lain:",
                "Senarai Kecacatan Pemilik Menuntut:",
                "Senarai Kecacatan Pemilik Lain:",
                "Senarai Kecacatan Pemilik Lain Dalam Kes:",
                "Claimant Owner Details:",
                "Claimant Owner Closed Case Records:",
                "Claimant Owner Defect List:",
                "Other Owner Details:",
                "Other Owner Closed Case Records:",
                "Other Owner Defect List:",
                "Other Owner Defect List in Case:",
            )):
                y -= 4

    # =============================================
    # APPEND LEGAL METADATA PAGE
    # =============================================
    draw_footer(pdf, width, labels)
    pdf.showPage()

    signature = legal_metadata.get("signature", {})
    certificate = legal_metadata.get("certificate", {})
    timeline = legal_metadata.get("timeline", {})

    # Get language labels
    t = PDF_LABELS[language]["legal_metadata"]
    legal_title = t.get("titles", {}).get(role, {}).get(language, t["title"])

    # Page setup
    y = height - 50
    LEFT_MARGIN = 50
    CONTENT_WIDTH = width - (LEFT_MARGIN * 2)
    LINE_SPACING = 15
    SECTION_GAP = 18
    LABEL_END_X = LEFT_MARGIN + 112
    VALUE_X = LABEL_END_X + 6

    page_labels = {
        "ms": {
            "subtitle": "",
            "report_information": "Maklumat Laporan",
            "compliance_status": "Status Pematuhan",
            "defect_summary": "Ringkasan Kecacatan",
            "data_integrity": "Integriti Data",
            "timeline_summary": "Ringkasan Garis Masa",
            "report_id": "ID Laporan",
            "signature_id": "ID Tandatangan",
            "timestamp": "Tarikh & Masa",
            "status": "Status",
            "status_values": {
                "COMPLIANT": "Mematuhi",
                "PENDING_REVIEW": "Tidak Mematuhi",
                "PENDING": "Tidak Mematuhi",
                "NON_COMPLIANT": "Tidak Mematuhi",
            },
            "total_defects": "Jumlah Kecacatan",
            "completed": "Bilangan Kecacatan Diselesaikan",
            "completion_rate": "Kadar Penyelesaian",
            "integrity_hash": "Cincang Pengesahan Dokumen (SHA-256):",
            "integrity_note": "Sijil ini dijana secara digital. Nilai cincang di atas digunakan untuk mengesahkan ketulenan dan integriti dokumen ini.",
            "timeline_completed": "Telah Siap",
            "timeline_pending": "Belum Selesai / Dalam Proses",
            "initial_report": "Laporan Awal",
            "last_update": "Kemas Kini Terakhir",
            "footer_note": "Sijil ini hendaklah dibaca bersama halaman pengesahan dan tandatangan.",
            "certificate_no": "No. Sijil",
        },
        "en": {
            "subtitle": "",
            "report_information": "Report Information",
            "compliance_status": "Compliance Status",
            "defect_summary": "Defect Summary",
            "data_integrity": "Data Integrity",
            "timeline_summary": "Timeline Summary",
            "report_id": "Report ID",
            "signature_id": "Signature ID",
            "timestamp": "Timestamp",
            "status": "Status",
            "status_values": {
                "COMPLIANT": "Compliant",
                "PENDING_REVIEW": "Non-Compliant",
                "PENDING": "Non-Compliant",
                "NON_COMPLIANT": "Non-Compliant",
            },
            "total_defects": "Total Defects",
            "completed": "Completed Defects",
            "completion_rate": "Resolution Rate",
            "integrity_hash": "Document Verification Hash (SHA-256)",
            "integrity_note": "This certificate has been digitally generated. The hash value above is used to verify the authenticity and integrity of this document.",
            "timeline_completed": "Completed",
            "timeline_pending": "Pending / In Progress",
            "initial_report": "Initial Report",
            "last_update": "Last Update",
            "footer_note": "This certificate shall be read together with the verification and signature page.",
            "certificate_no": "Certificate No.",
        },
    }
    page = page_labels.get(language, page_labels["ms"])
    BOX_LEFT = 50
    BOX_WIDTH = width - (BOX_LEFT * 2)
    BOX_PADDING_X = 14
    BOX_PADDING_TOP = 17
    ROW_HEIGHT = 16
    LABEL_X = BOX_LEFT + BOX_PADDING_X
    COLON_X = BOX_LEFT + 215
    VALUE_X = COLON_X + 14
    VALUE_WIDTH = BOX_LEFT + BOX_WIDTH - VALUE_X - BOX_PADDING_X

    def _fit_certificate_value(value, max_width, font_name="Times-Roman", font_size=FONT_BODY):
        text = str(value or "")
        if pdf.stringWidth(text, font_name, font_size) <= max_width:
            return text

        ellipsis = "..."
        available_width = max_width - pdf.stringWidth(ellipsis, font_name, font_size)
        if available_width <= 0:
            return ellipsis

        fitted = ""
        for char in text:
            if pdf.stringWidth(fitted + char, font_name, font_size) > available_width:
                break
            fitted += char
        return fitted.rstrip() + ellipsis

    def draw_certificate_section(title, rows, current_y, box_height=None):
        row_count = max(len(rows), 1)
        box_height = box_height or (BOX_PADDING_TOP + 13 + (row_count * ROW_HEIGHT) + 11)
        bottom_y = current_y - box_height

        pdf.saveState()
        pdf.setLineWidth(0.85)
        pdf.rect(BOX_LEFT, bottom_y, BOX_WIDTH, box_height, stroke=1, fill=0)
        pdf.restoreState()

        title_y = current_y - BOX_PADDING_TOP
        pdf.setFont("Times-Bold", FONT_H2)
        pdf.drawString(LABEL_X, title_y, title)

        row_y = title_y - 20
        for label, value in rows:
            pdf.setFont("Times-Roman", FONT_BODY)
            pdf.drawString(LABEL_X, row_y, str(label))
            pdf.drawString(COLON_X, row_y, ":")
            value_text = _fit_certificate_value(value, VALUE_WIDTH)
            pdf.setFont("Times-Roman", FONT_BODY)
            pdf.drawString(VALUE_X, row_y, value_text)
            row_y -= ROW_HEIGHT

        return bottom_y - 34

    def _wrap_certificate_text(text, max_width, font_name="Times-Roman", font_size=FONT_BODY):
        words = str(text or "").split()
        lines = []
        current = ""

        for word in words:
            candidate = f"{current} {word}".strip()
            if pdf.stringWidth(candidate, font_name, font_size) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            if pdf.stringWidth(word, font_name, font_size) <= max_width:
                current = word
                continue

            chunk = ""
            for char in word:
                if pdf.stringWidth(chunk + char, font_name, font_size) <= max_width:
                    chunk += char
                else:
                    if chunk:
                        lines.append(chunk)
                    chunk = char
            current = chunk

        if current:
            lines.append(current)
        return lines or [""]

    def draw_data_integrity_section(current_y, hash_value):
        label_lines = _wrap_certificate_text(page["integrity_hash"], BOX_WIDTH - (BOX_PADDING_X * 2))
        hash_lines = _wrap_certificate_text(hash_value, BOX_WIDTH - (BOX_PADDING_X * 2), "Times-Roman", FONT_BODY)
        note_lines = _wrap_certificate_text(page["integrity_note"], BOX_WIDTH - (BOX_PADDING_X * 2), "Times-Roman", FONT_CAPTION)
        box_height = (
            BOX_PADDING_TOP
            + 16
            + (len(label_lines) * ROW_HEIGHT)
            + 4
            + (len(hash_lines) * ROW_HEIGHT)
            + 8
            + (len(note_lines) * ROW_HEIGHT)
            + 12
        )
        bottom_y = current_y - box_height

        pdf.saveState()
        pdf.setLineWidth(0.85)
        pdf.rect(BOX_LEFT, bottom_y, BOX_WIDTH, box_height, stroke=1, fill=0)
        pdf.restoreState()

        row_y = current_y - BOX_PADDING_TOP
        pdf.setFont("Times-Bold", FONT_H2)
        pdf.drawString(LABEL_X, row_y, page["data_integrity"])
        row_y -= 20

        pdf.setFont("Times-Roman", FONT_BODY)
        for line in label_lines:
            pdf.drawString(LABEL_X, row_y, line)
            row_y -= ROW_HEIGHT

        row_y -= 2
        for line in hash_lines:
            pdf.drawString(LABEL_X, row_y, line)
            row_y -= ROW_HEIGHT

        row_y -= 6
        pdf.setFont("Times-Italic", FONT_CAPTION)
        for line in note_lines:
            pdf.drawString(LABEL_X, row_y, line)
            row_y -= ROW_HEIGHT

        return bottom_y - 28

    # =========================
    # TITLE
    # =========================
    pdf.setFont("Times-Bold", FONT_H1)
    pdf.drawCentredString(width / 2, y, legal_title)
    y -= 24

    pdf.saveState()
    pdf.setLineWidth(0.75)
    pdf.setDash(1.2, 2.0)
    pdf.line((width - 250) / 2, y, (width + 250) / 2, y)
    pdf.restoreState()
    y -= 32

    subtitle = page["subtitle"].strip()
    if subtitle:
        pdf.setFont("Times-Roman", FONT_BODY)
        pdf.drawString(LEFT_MARGIN, y, subtitle)
        y -= 18

    # =========================
    # REPORT INFO
    # =========================
    y = draw_certificate_section(page["report_information"], [
        (page["report_id"], legal_metadata.get("report_id", "N/A")),
        (page["certificate_no"], certificate.get("certificate_no", certificate.get("certificate_id", "N/A"))),
        (page["signature_id"], signature.get("signature_id", "N/A")),
        (page["timestamp"], _format_display_timestamp(signature.get("timestamp", "N/A"), language)),
    ], y, box_height=102)

    # =========================
    # COMPLIANCE STATUS
    # =========================
    compliance_status = certificate.get("compliance_status", "PENDING")
    compliance_status_display = page.get("status_values", {}).get(compliance_status, compliance_status)
    y = draw_certificate_section(page["compliance_status"], [
        (page["status"], compliance_status_display),
    ], y, box_height=72)

    # =========================
    # DEFECT SUMMARY
    # =========================
    stats = certificate.get("statistics", {})
    y = draw_certificate_section(page["defect_summary"], [
        (page["total_defects"], str(stats.get("total_defects", 0))),
        (page["completed"], str(stats.get("completed", 0))),
        (page["completion_rate"], str(stats.get("completion_rate", "0%"))),
    ], y, box_height=92)

    # =========================
    # TIMELINE
    # =========================
    timeline_data = {
        page["timeline_completed"]: str(certificate.get("statistics", {}).get("completed", 0)),
        page["timeline_pending"]: str(certificate.get("statistics", {}).get("pending", 0)),
        page["initial_report"]: _format_display_timestamp(legal_metadata.get("created_at", signature.get("timestamp", "N/A")), language),
        page["last_update"]: _format_display_timestamp(timeline.get("timeline_generated", signature.get("timestamp", "N/A")), language),
    }
    y = draw_certificate_section(page["timeline_summary"], [
        (page["timeline_completed"], timeline_data[page["timeline_completed"]]),
        (page["timeline_pending"], timeline_data[page["timeline_pending"]]),
        (page["initial_report"], timeline_data[page["initial_report"]]),
        (page["last_update"], timeline_data[page["last_update"]]),
    ], y, box_height=108)

    # =========================
    # DATA INTEGRITY
    # =========================
    integrity_hash = signature.get("content_hash", "N/A")
    y = draw_data_integrity_section(y, integrity_hash)

    pdf.setFont("Times-Italic", FONT_CAPTION)
    footer_note = page["footer_note"]
    pdf.drawCentredString(width / 2, y + 4, footer_note)

    # ============================================
    # SIGNATURE & METERAI (HALAMAN BERASINGAN)
    # ============================================
    draw_footer(pdf, width, labels)
    pdf.showPage()
    y = height - 50

    signature_title = "Verification and Signature" if language == "en" else "Pengesahan dan Tandatangan"
    pdf.setFont("Times-Bold", FONT_H1)
    pdf.drawCentredString(width / 2, y, signature_title)
    y -= 110

    pdf.setFont("Times-Roman", FONT_BODY)

    column_gap = 18
    column_width = (width - (2 * 50) - (2 * column_gap)) / 3
    line_margin = 4

    def draw_signature_column(x0, line_y, label_y, top_text, label_text, draw_line=True):
        line_left = x0 + line_margin
        line_right = x0 + column_width - line_margin
        center_x = x0 + (column_width / 2)

        if draw_line:
            pdf.saveState()
            pdf.setLineWidth(0.55)
            pdf.setDash(0.8, 2.2)
            pdf.line(line_left, line_y, line_right, line_y)
            pdf.restoreState()
        else:
            pdf.setFont("Times-Bold", FONT_H2)
            pdf.drawCentredString(center_x, line_y - 3, top_text)

        pdf.setFont("Times-Roman", FONT_BODY)
        pdf.drawCentredString(center_x, label_y, label_text)

    left_x = 50
    center_x = left_x + column_width + column_gap
    right_x = center_x + column_width + column_gap
    first_row_y = y
    second_row_y = y - 78
    first_label_y = first_row_y - 18
    second_label_y = second_row_y - 18

    if language == "en":
        draw_signature_column(left_x, first_row_y, first_label_y, "", "Date", draw_line=True)
        draw_signature_column(right_x, first_row_y, first_label_y, "", "Signature/Thumbprint of Claimant", draw_line=True)
        draw_signature_column(left_x, second_row_y, second_label_y, "", "Filing Date", draw_line=True)
        draw_signature_column(right_x, second_row_y, second_label_y, "", "Tribunal Secretary/Officer", draw_line=True)
    else:
        draw_signature_column(left_x, first_row_y, first_label_y, "", "Tarikh", draw_line=True)
        draw_signature_column(right_x, first_row_y, first_label_y, "", "Tandatangan/Cap ibu jari Pihak Yang Menuntut", draw_line=True)
        draw_signature_column(left_x, second_row_y, second_label_y, "", "Tarikh Pemfailan", draw_line=True)
        draw_signature_column(right_x, second_row_y, second_label_y, "", "Setiausaha/Pegawai Tribunal", draw_line=True)

    y = second_row_y - 70

    pdf.setFont("Times-Bold", FONT_H2)
    if language == "en":
        pdf.drawCentredString(width / 2, y, "(SEAL)")
    else:
        pdf.drawCentredString(width / 2, y, "(METERAI)")

    # Filename based on role
    if role == "Legal":
        filename = labels["legal_filename"]
    elif role == "Developer":
        filename = labels["developer_filename"]
    else:
        filename = labels["homeowner_filename"]

    pdf.setTitle(os.path.splitext(filename)[0])
    pdf.setAuthor("Automated Compliance Report Generation")
    pdf.setSubject("Tribunal Compliance Report")

    report_string = json.dumps(report_data, sort_keys=True)
    digital_hash = hashlib.sha256(report_string.encode()).hexdigest()

    draw_footer(pdf, width, labels)

    # =========================
    # FOOTER
    # =========================
    pdf.save()
    buffer.seek(0)

    # ==========================
    # AUDIT LOG: PDF EXPORTED
    # ==========================
    _append_audit_event(
        action="PDF Exported",
        role=role,
        filename=filename,
        details={
            "username": session.get("username", ""),
            "language": language,
            "filename": filename,
            "hash": digital_hash,
        },
    )

    # Return the generated PDF to the client
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
    
# =================================================
# API ENDPOINTS FOR DASHBOARD UPDATES
# =================================================

@routes.route("/add_remark", methods=["POST"])
@login_required
def add_remark():
    """
    Save remark for a defect (Homeowner only)
    """
    try:
        data = request.get_json() or {}
        defect_id = data.get("id")
        remark = data.get("remark", "").strip()
        role = data.get("role", "Homeowner")
        
        if not defect_id or not str(defect_id).isdigit():
            return jsonify({"success": False, "error": "Invalid defect ID"}), 400
        
        if role != "Homeowner":
            return jsonify({"success": False, "error": "Only Homeowner can save remarks"}), 403
        
        # Save remarks using the existing function
        save_remarks({str(defect_id): remark})
        
        _append_audit_event(
            action="Remark Added",
            role=_current_role(),
            defect_id=defect_id,
            details={
                "username": session.get("username", ""),
                "remark_length": len(remark),
            },
        )
        
        return jsonify({"success": True, "message": "Remark saved successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@routes.route("/update_description", methods=["POST"])
@login_required
def update_description():
    """
    Allow Homeowner to update defect description for defects they own.
    """
    try:
        data = request.get_json() or {}
        defect_id = data.get("id")
        description = (data.get("description") or "").strip()

        if not defect_id or not str(defect_id).isdigit():
            return jsonify({"success": False, "error": "Invalid defect ID"}), 400

        if _current_role() != "Homeowner":
            return jsonify({"success": False, "error": "Only Homeowner can update description"}), 403

        defect_id_int = int(defect_id)
        user_id = _current_user_id()

        conn = get_connection()
        cur = conn.cursor()
        try:
            # Verify ownership
            cur.execute("SELECT user_id FROM defects WHERE id = %s", (defect_id_int,))
            row = cur.fetchone()
            if not row:
                return jsonify({"success": False, "error": "Defect not found"}), 404
            owner = row[0]
            if owner != user_id:
                return jsonify({"success": False, "error": "Not allowed to edit this defect"}), 403

            # Update encrypted description
            cur.execute(
                "UPDATE defects SET description = %s, updated_at = NOW() WHERE id = %s",
                (_encrypt_text(description), defect_id_int),
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

        _append_audit_event(
            action="Description Updated",
            role="Homeowner",
            defect_id=str(defect_id_int),
            details={
                "username": session.get("username", ""),
                "length": len(description),
            },
        )

        return jsonify({"success": True, "message": "Description updated"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@routes.route("/update_status", methods=["POST"])
@login_required
def update_status():
    """
    Update status for a defect (Developer and Legal)
    Also saves completion date if status is 'Completed'
    """
    try:
        role = _current_role()
        if role not in ["Developer", "Legal", "Admin"]:
            return jsonify({"success": False, "error": "Only Developer, Legal, or Admin can update status"}), 403
        
        data = request.get_json() or {}
        defect_id = data.get("id")
        new_status = data.get("status", "").strip()
        completed_date = data.get("completed_date", "").strip()
        
        if not defect_id or not str(defect_id).isdigit():
            return jsonify({"success": False, "error": "Invalid defect ID"}), 400
        if not _current_user_can_access_defect(defect_id):
            return jsonify({"success": False, "error": "Not allowed to update this defect"}), 403
        
        if not new_status:
            return jsonify({"success": False, "error": "Status is required"}), 400
        
        # Normalize status
        if new_status in STATUS_NORMALISE:
            new_status = STATUS_NORMALISE[new_status]

        allowed_statuses = {"Pending", "In Progress", "Completed", "Delayed"}
        if new_status not in allowed_statuses:
            return jsonify({"success": False, "error": "Invalid status value"}), 400

        if new_status == "Completed" and not completed_date:
            return jsonify({"success": False, "error": "Completion date is required when status is Completed"}), 400
        
        # Validate date format if provided (YYYY-MM-DD)
        if completed_date:
            try:
                completed_date_obj = datetime.strptime(completed_date, "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"success": False, "error": "Invalid date format. Use YYYY-MM-DD"}), 400
            if completed_date_obj > _now_app_timezone().date():
                return jsonify({"success": False, "error": "Completion date cannot be in the future"}), 400
        
        # Save status using the existing function
        save_status({str(defect_id): new_status})
        
        # If status is Completed and completion date is provided, save it
        if new_status == "Completed" and completed_date:
            save_completion_dates({str(defect_id): completed_date})
        elif new_status != "Completed":
            # Clear completion date if status is not Completed
            save_completion_dates({str(defect_id): None})
            completed_date = ""

        cur_completed_date = completed_date if new_status == "Completed" else None
        cur = None
        conn = None
        reported_date = None
        deadline = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT reported_date, deadline FROM defects WHERE id = %s", (defect_id,))
            row = cur.fetchone()
            if row:
                reported_date, deadline = row[0], row[1]
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

        closed = is_auto_closed(new_status, cur_completed_date)
        is_overdue = calculate_overdue(deadline, cur_completed_date, new_status)
        hda_compliant = calculate_hda_compliance(reported_date, cur_completed_date, new_status)
        
        _append_audit_event(
            action="Status Updated",
            role=role,
            defect_id=defect_id,
            new_status=new_status,
            details={
                "username": session.get("username", ""),
                "new_status": new_status,
                "completed_date": completed_date or "None",
            },
        )
        
        return jsonify({
            "success": True,
            "message": "Status updated successfully",
            "new_status": new_status,
            "display_status": "Closed" if closed else new_status,
            "completed_date": completed_date,
            "closed": closed,
            "is_overdue": is_overdue,
            "hda_compliant": hda_compliant,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@routes.route("/update_completion_date", methods=["POST"])
@login_required
def update_completion_date():
    """
    Update completion date for a defect (Developer and Legal)
    """
    try:
        role = _current_role()
        if role not in ["Developer", "Legal", "Admin"]:
            return jsonify({"success": False, "error": "Only Developer, Legal, or Admin can update completion date"}), 403
        
        data = request.get_json() or {}
        defect_id = data.get("id")
        completed_date = data.get("completed_date", "").strip()
        
        if not defect_id or not str(defect_id).isdigit():
            return jsonify({"success": False, "error": "Invalid defect ID"}), 400
        if not _current_user_can_access_defect(defect_id):
            return jsonify({"success": False, "error": "Not allowed to update this defect"}), 403
        
        # Validate date format (YYYY-MM-DD)
        if completed_date:
            try:
                datetime.strptime(completed_date, "%Y-%m-%d")
            except ValueError:
                return jsonify({"success": False, "error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        # Save completion date using the existing function
        save_completion_dates({str(defect_id): completed_date if completed_date else None})
        
        _append_audit_event(
            action="Completion Date Updated",
            role=role,
            defect_id=defect_id,
            details={
                "username": session.get("username", ""),
                "completed_date": completed_date,
            },
        )
        
        return jsonify({"success": True, "message": "Completion date updated successfully", "completed_date": completed_date})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
