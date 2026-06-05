# report_data.py
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

try:
    from .database.db import get_connection
    from .encryption_utils import decrypt_text, encrypt_text, is_encrypted_text
except ImportError:  # pragma: no cover - fallback for direct execution from module3/
    from database.db import get_connection
    from encryption_utils import decrypt_text, encrypt_text, is_encrypted_text

TRIBUNAL_NAME = "Tribunal Tuntutan Pengguna Malaysia"
DEFAULT_TRIBUNAL_LOCATION = "-"
DEFAULT_CLAIM_AMOUNT = "-"
DEFAULT_STATE_NAME = "-"
DEFAULT_ITEM_SERVICE = "Defect Repair During DLP"
IMPORTANT_NOTE = (
    "Laporan ini dijana oleh sistem sebagai dokumen sokongan kepada Borang 1 Tribunal Tuntutan Pengguna Malaysia (TTPM)."
)
DEFAULT_CLAIMANT_HOMEOWNER_USERNAME = os.getenv("DEFAULT_CLAIMANT_HOMEOWNER_USERNAME", "").strip()
DEFAULT_CLAIMANT_HOMEOWNER_ID = int(
    os.getenv("DEFAULT_CLAIMANT_HOMEOWNER_ID", os.getenv("SIMULATED_LOGIN_USER_ID", "1"))
)
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Kuala_Lumpur")
MAIN_DEVELOPER_USERNAMES = {
    username.strip().lower()
    for username in os.getenv("MAIN_DEVELOPER_USERNAMES", "main_developer").split(",")
    if username.strip()
}
DANIELLEE_PROJECT_NAMES = {
    project_name.strip().lower()
    for project_name in os.getenv("DANIELLEE_PROJECT_NAMES", "Skyline Pulau Pinang Central").split(",")
    if project_name.strip()
}
_REPORT_METADATA_INITIALIZED = False
_REPORT_METADATA_INITIALIZING = False


def _now_app_timezone():
    try:
        return datetime.now(ZoneInfo(APP_TIMEZONE))
    except Exception:
        if APP_TIMEZONE == "Asia/Kuala_Lumpur":
            return datetime.now(timezone.utc) + timedelta(hours=8)
        return datetime.now()


def _decrypt_or_plain(value):
    if value is None:
        return ""
    return decrypt_text(value)


def _display_text(value):
    text = _decrypt_or_plain(value)
    raw_text = str(value or "")
    if text.strip().startswith("gAAAA"):
        return ""
    if text and text != raw_text:
        return text
    if raw_text.startswith("gAAAA") or is_encrypted_text(text):
        return ""
    return text


def _display_safe(value):
    if isinstance(value, dict):
        return {key: _display_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_display_safe(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_display_safe(item) for item in value)
    if isinstance(value, str):
        return _display_text(value)
    return value


def _format_transaction_date(value):
    text = _decrypt_or_plain(value).strip()
    if not text or text == "-":
        return "-"

    for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], date_format).strftime("%d-%m-%Y")
        except Exception:
            continue

    return text


def _clean_address_text(value):
    text = _decrypt_or_plain(value)
    if not text:
        return ""
    text = re.sub(r"[\r\n\t]+", ", ", text)
    text = re.sub(r"\s*[■•·]+\s*", ", ", text)
    text = re.sub(r",\s*,+", ", ", text)
    text = re.sub(r"\s+,\s+", ", ", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r",\s*$", "", text)
    return text.strip(" ,")

STATE_CODES = {
    "Selangor": "SGR",
    "Johor": "JHR",
    "Pulau Pinang": "PNG",
    "Penang": "PNG",
    "Perak": "PRK",
    "Kedah": "KDH",
    "Perlis": "PLS",
    "Negeri Sembilan": "NSN",
    "Melaka": "MLK",
    "Pahang": "PHG",
    "Terengganu": "TRG",
    "Kelantan": "KTN",
    "Sabah": "SBH",
    "Sarawak": "SWK",
    "Kuala Lumpur": "WPKL",
    "W.P. Kuala Lumpur": "WPKL",
    "WP Kuala Lumpur": "WPKL",
    "Wilayah Persekutuan Kuala Lumpur": "WPKL",
    "Putrajaya": "WPPJ",
    "W.P. Putrajaya": "WPPJ",
    "WP Putrajaya": "WPPJ",
    "Wilayah Persekutuan Putrajaya": "WPPJ",
    "Labuan": "WPLB",
    "W.P. Labuan": "WPLB",
    "WP Labuan": "WPLB",
    "Wilayah Persekutuan Labuan": "WPLB",
}


def _normalise_state_name_for_code(value):
    text = str(value or "").strip()
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text)
    normalized = text.lower()
    normalized = normalized.replace("w.p.", "wp")
    normalized = normalized.replace("w.p", "wp")
    normalized = normalized.replace("wilayah persekutuan", "wp")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()

    aliases = {
        "wp kuala lumpur": "Kuala Lumpur",
        "kuala lumpur": "Kuala Lumpur",
        "wp putrajaya": "Putrajaya",
        "putrajaya": "Putrajaya",
        "wp labuan": "Labuan",
        "labuan": "Labuan",
        "penang": "Pulau Pinang",
        "pulau pinang": "Pulau Pinang",
    }
    return aliases.get(normalized, text)


def _state_code_for_name(state_name, negeri_codes):
    canonical_state = _normalise_state_name_for_code(state_name)
    if canonical_state in negeri_codes:
        return negeri_codes[canonical_state]

    lookup = {
        _normalise_state_name_for_code(name).lower(): code
        for name, code in (negeri_codes or {}).items()
    }
    return lookup.get(canonical_state.lower(), "UNK")

ROLE_CONTEXTS = {
    "Homeowner": {
        "report_title": "Laporan Tuntutan Kecacatan Defect Liability Period (DLP)",
        "report_purpose": "Laporan ini disediakan bagi tujuan rujukan Tribunal.",
    },
    "Developer": {
        "report_title": "Laporan Pematuhan Pembaikan Defect Liability Period (DLP)",
        "report_purpose": "Laporan ini disediakan untuk menunjukkan status pembaikan dan pematuhan pemaju terhadap kecacatan yang dilaporkan.",
    },
    "Legal": {
        "report_title": "Laporan Gambaran Keseluruhan Pematuhan Defect Liability Period (DLP)",
        "report_purpose": "Laporan ini disediakan sebagai gambaran keseluruhan status kecacatan dan pematuhan untuk rujukan Tribunal.",
    },
}

def _ensure_report_metadata_tables():
    global _REPORT_METADATA_INITIALIZED, _REPORT_METADATA_INITIALIZING
    if _REPORT_METADATA_INITIALIZED:
        return
    if _REPORT_METADATA_INITIALIZING:
        return

    _REPORT_METADATA_INITIALIZING = True
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DROP TABLE IF EXISTS report_active_claimant")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS report_homeowner_profile (
                homeowner_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                ic_number TEXT,
                email TEXT,
                phone_number TEXT,
                address TEXT,
                court_location TEXT,
                state_name TEXT,
                claim_amount TEXT,
                item_service TEXT,
                transaction_date TEXT,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN name TYPE TEXT USING name::text"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN ic_number TYPE TEXT USING ic_number::text"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN email TYPE TEXT USING email::text"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN phone_number TYPE TEXT USING phone_number::text"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN address TYPE TEXT USING address::text"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ADD COLUMN IF NOT EXISTS court_location TEXT"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN court_location TYPE TEXT USING court_location::text"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ADD COLUMN IF NOT EXISTS state_name TEXT"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN state_name TYPE TEXT USING state_name::text"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ADD COLUMN IF NOT EXISTS claim_amount TEXT"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN claim_amount TYPE TEXT USING claim_amount::text"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ADD COLUMN IF NOT EXISTS item_service TEXT"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN item_service TYPE TEXT USING item_service::text"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ADD COLUMN IF NOT EXISTS transaction_date TEXT"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN transaction_date TYPE TEXT USING transaction_date::text"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ADD COLUMN IF NOT EXISTS defect_unit TEXT"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN defect_unit TYPE TEXT USING defect_unit::text"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ADD COLUMN IF NOT EXISTS project_name TEXT"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN project_name TYPE TEXT USING project_name::text"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ADD COLUMN IF NOT EXISTS defect_state TEXT"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN defect_state TYPE TEXT USING defect_state::text"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ADD COLUMN IF NOT EXISTS defect_property_address TEXT"
        )
        cur.execute(
            "ALTER TABLE report_homeowner_profile ALTER COLUMN defect_property_address TYPE TEXT USING defect_property_address::text"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS report_respondent_profile (
                respondent_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                company_name TEXT NOT NULL,
                person_in_charge TEXT,
                registration_number TEXT,
                email TEXT,
                phone_number TEXT,
                address TEXT,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("ALTER TABLE report_respondent_profile ALTER COLUMN company_name TYPE TEXT USING company_name::text")
        cur.execute("ALTER TABLE report_respondent_profile ADD COLUMN IF NOT EXISTS person_in_charge TEXT")
        cur.execute("ALTER TABLE report_respondent_profile ALTER COLUMN person_in_charge TYPE TEXT USING person_in_charge::text")
        cur.execute("ALTER TABLE report_respondent_profile ALTER COLUMN registration_number TYPE TEXT USING registration_number::text")
        cur.execute("ALTER TABLE report_respondent_profile ALTER COLUMN email TYPE TEXT USING email::text")
        cur.execute("ALTER TABLE report_respondent_profile ALTER COLUMN phone_number TYPE TEXT USING phone_number::text")
        cur.execute("ALTER TABLE report_respondent_profile ALTER COLUMN address TYPE TEXT USING address::text")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS report_claim_registry (
                claim_id VARCHAR(64) PRIMARY KEY,
                case_key VARCHAR(255) UNIQUE NOT NULL,
                case_number VARCHAR(6) NOT NULL,
                claim_year INTEGER NOT NULL,
                date_filed TIMESTAMP NOT NULL DEFAULT NOW(),
                state VARCHAR(100) NOT NULL,
                state_code VARCHAR(20) NOT NULL,
                homeowner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                respondent_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS report_versions (
                role TEXT NOT NULL,
                version_no INTEGER NOT NULL,
                generated_at TIMESTAMP NOT NULL,
                language TEXT NOT NULL DEFAULT 'ms',
                report_text TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (role, version_no)
            )
            """
        )
        cur.execute("ALTER TABLE report_versions ALTER COLUMN role TYPE TEXT USING role::text")
        cur.execute("ALTER TABLE report_versions ALTER COLUMN language TYPE TEXT USING language::text")
        cur.execute("ALTER TABLE report_versions ALTER COLUMN report_text TYPE TEXT USING report_text::text")
        cur.execute(
            "ALTER TABLE report_claim_registry ADD COLUMN IF NOT EXISTS state VARCHAR(100)"
        )
        cur.execute(
            """
            INSERT INTO report_homeowner_profile (
                homeowner_id, name, email, phone_number, address, court_location,
                state_name, claim_amount, item_service, transaction_date
            )
            SELECT u.id, u.full_name, u.email, NULL, u.unit, NULL, NULL, NULL,
                   'Defect Repair During DLP', NULL
            FROM users u
            WHERE u.role = 'Homeowner'
              AND NOT EXISTS (
                  SELECT 1
                  FROM report_homeowner_profile p
                  WHERE p.homeowner_id = u.id
              )
            """
        )
        cur.execute(
            """
            INSERT INTO report_respondent_profile (
                respondent_id, company_name, email, phone_number, address
            )
            SELECT u.id, u.full_name, u.email, NULL, u.unit
            FROM users u
            WHERE u.role IN ('Developer', 'Legal', 'Admin')
              AND NOT EXISTS (
                  SELECT 1
                  FROM report_respondent_profile p
                  WHERE p.respondent_id = u.id
              )
            """
        )
        cur.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'report_claim_registry'
                      AND column_name = 'negeri'
                ) THEN
                    EXECUTE 'UPDATE report_claim_registry SET state = COALESCE(state, negeri)';
                END IF;
            END
            $$;
            """
        )

        conn.commit()
        _REPORT_METADATA_INITIALIZED = True
    finally:
        cur.close()
        conn.close()
        _REPORT_METADATA_INITIALIZING = False


def _migrate_profile_encryption():
    global _REPORT_METADATA_INITIALIZED
    _ensure_report_metadata_tables()
    if not _REPORT_METADATA_INITIALIZED:
        return

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT homeowner_id, name, ic_number, email, phone_number, address,
                   court_location, state_name, claim_amount, item_service, transaction_date
            FROM report_homeowner_profile
            """
        )
        for row in cur.fetchall():
            homeowner_id = row[0]
            normalized_values = (
                _display_text(row[1]).strip() or row[1],
                encrypt_text(row[2]),
                encrypt_text(row[3]),
                encrypt_text(row[4]),
                encrypt_text(row[5]),
                encrypt_text(row[6]),
                encrypt_text(row[7]),
                encrypt_text(row[8]),
                encrypt_text(row[9]),
                encrypt_text(row[10]),
            )

            if row[1:] == normalized_values:
                continue

            cur.execute(
                """
                UPDATE report_homeowner_profile
                SET name = %s,
                    ic_number = %s,
                    email = %s,
                    phone_number = %s,
                    address = %s,
                    court_location = %s,
                    state_name = %s,
                    claim_amount = %s,
                    item_service = %s,
                    transaction_date = %s,
                    updated_at = NOW()
                WHERE homeowner_id = %s
                """,
                (*normalized_values, homeowner_id),
            )

        cur.execute(
            """
            SELECT respondent_id, company_name, registration_number, email, phone_number, address
            FROM report_respondent_profile
            """
        )
        for row in cur.fetchall():
            respondent_id = row[0]
            normalized_values = (
                _display_text(row[1]).strip() or row[1],
                encrypt_text(row[2]),
                encrypt_text(row[3]),
                encrypt_text(row[4]),
                encrypt_text(row[5]),
            )

            if row[1:] == normalized_values:
                continue

            cur.execute(
                """
                UPDATE report_respondent_profile
                SET company_name = %s,
                    registration_number = %s,
                    email = %s,
                    phone_number = %s,
                    address = %s,
                    updated_at = NOW()
                WHERE respondent_id = %s
                """,
                (*normalized_values, respondent_id),
            )

        conn.commit()
    finally:
        cur.close()
        conn.close()


def ensure_profile_encryption_at_rest():
    _ensure_report_metadata_tables()
    _migrate_profile_encryption()


def _get_respondent_company_name(respondent_id):
    if respondent_id is None:
        return ""

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT company_name
            FROM report_respondent_profile
            WHERE respondent_id = %s
            LIMIT 1
            """,
            (respondent_id,),
        )
        row = cur.fetchone()
        return (_display_text(row[0]) if row and row[0] else "").strip()
    finally:
        cur.close()
        conn.close()


def _ensure_developer_project_access_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS developer_project_access (
            developer_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            project_id INTEGER NOT NULL REFERENCES developer_projects(id) ON DELETE CASCADE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (developer_user_id, project_id)
        )
        """
    )


def is_main_developer_account(user_id=None, username=None):
    normalized_username = (username or "").strip().lower()
    if normalized_username and normalized_username in MAIN_DEVELOPER_USERNAMES:
        return True

    if user_id is None:
        return False

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT username
            FROM login_accounts
            WHERE user_id = %s
              AND LOWER(role) = 'developer'
              AND is_active = TRUE
            """,
            (user_id,),
        )
        return any((row[0] or "").strip().lower() in MAIN_DEVELOPER_USERNAMES for row in cur.fetchall())
    except Exception:
        return False
    finally:
        cur.close()
        conn.close()


def get_developer_project_access_ids(user_id):
    if user_id is None:
        return []

    conn = get_connection()
    cur = conn.cursor()
    try:
        _ensure_developer_project_access_table(cur)
        cur.execute(
            """
            SELECT project_id
            FROM developer_project_access
            WHERE developer_user_id = %s
            ORDER BY project_id ASC
            """,
            (user_id,),
        )
        return [row[0] for row in cur.fetchall() if row and row[0] is not None]
    finally:
        conn.commit()
        cur.close()
        conn.close()


def get_available_projects(respondent_id=None, role=None):
    conn = get_connection()
    cur = conn.cursor()
    try:
        _ensure_developer_project_access_table(cur)
        conn.commit()
        cur.execute(
            """
            SELECT dp.id, dp.project_name, dp.state_name, dp.property_address, d.company_name, d.registration_number
            FROM developer_projects dp
            JOIN developers d
                ON dp.developer_id = d.id
            ORDER BY dp.project_name ASC
            """
        )
        rows = cur.fetchall()
        is_main_developer = role == "Developer" and is_main_developer_account(respondent_id)
        assigned_project_ids = set()
        if role == "Developer" and not is_main_developer and respondent_id is not None:
            cur.execute(
                """
                SELECT project_id
                FROM developer_project_access
                WHERE developer_user_id = %s
                """,
                (respondent_id,),
            )
            assigned_project_ids = {row[0] for row in cur.fetchall() if row and row[0] is not None}
            cur.execute(
                """
                SELECT username
                FROM login_accounts
                WHERE user_id = %s
                  AND LOWER(role) = 'developer'
                  AND is_active = TRUE
                """,
                (respondent_id,),
            )
            developer_usernames = {(row[0] or "").strip().lower() for row in cur.fetchall()}
            if "daniellee" in developer_usernames:
                assigned_project_ids.update(
                    row[0]
                    for row in rows
                    if (row[1] or "").strip().lower() in DANIELLEE_PROJECT_NAMES
                )

            cur.execute(
                """
                SELECT DISTINCT state_name
                FROM developer_contacts
                WHERE developer_id = %s
                  AND state_name IS NOT NULL
                  AND TRIM(state_name) <> ''
                """,
                (respondent_id,),
            )
            contact_state_names = {
                (row[0] or "").strip().lower()
                for row in cur.fetchall()
                if (row[0] or "").strip()
            }
            if contact_state_names:
                assigned_project_ids.update(
                    row[0]
                    for row in rows
                    if (row[2] or "").strip().lower() in contact_state_names
                )
        allow_company_fallback = os.getenv("ENABLE_DEVELOPER_COMPANY_PROJECT_FALLBACK", "0") == "1"
        allowed_company_name = _get_respondent_company_name(respondent_id) if role == "Developer" and allow_company_fallback and not assigned_project_ids and not is_main_developer else ""

        projects = []
        for row in rows:
            company_name = _display_text(row[4]) if row[4] else ""
            if role == "Developer" and not is_main_developer:
                if assigned_project_ids and row[0] not in assigned_project_ids:
                    continue
                if allowed_company_name and company_name.strip().lower() != allowed_company_name.strip().lower():
                    continue
                if not assigned_project_ids and not allowed_company_name:
                    continue

            projects.append(
                {
                    "id": row[0],
                    "project_name": _display_text(row[1]) or "-",
                    "state_name": _display_text(row[2]) or "-",
                    "property_address": _display_text(row[3]) or "-",
                    "company_name": company_name or "-",
                    "registration_number": _display_text(row[5]) or "-",
                }
            )

        return projects
    finally:
        cur.close()
        conn.close()


def get_homeowner_claimants(respondent_id=None, project_name=None, role=None, allowed_project_names=None, include_unrestricted=False):
    _ensure_report_metadata_tables()
    _migrate_profile_encryption()

    # Use provided allowed_projects if available (to avoid recalculating in context builder)
    # By default the function will build `allowed_project_names` for Developer
    # accounts to restrict claimants to projects available to the respondent.
    # If `include_unrestricted` is True we skip building this set so callers
    # can request all claimants (used by dashboard grouping logic).
    if not include_unrestricted and allowed_project_names is None and role == "Developer" and respondent_id is not None:
        allowed_project_names = {
            (project.get("project_name") or "").strip().lower()
            for project in get_available_projects(respondent_id, role=role)
        }

    normalized_project_name = (project_name or "").strip().lower()
    if role == "Developer" and normalized_project_name and allowed_project_names is not None:
        if normalized_project_name not in allowed_project_names:
            return []

    conn = get_connection()
    cur = conn.cursor()
    try:
        # Select from users and left-join report_homeowner_profile so we include
        # homeowners who don't yet have an entry in report_homeowner_profile
        # (previous implementation anchored on report_homeowner_profile omitted
        # such users and hid units like PNG-01-02).
        cur.execute(
            """
            SELECT u.id AS homeowner_id,
                   COALESCE(rhp.name, u.full_name) AS name,
                   COALESCE(rhp.defect_unit, u.unit) AS defect_unit,
                   COALESCE(rhp.email, u.email) AS email,
                   rhp.project_name
            FROM users u
            LEFT JOIN report_homeowner_profile rhp ON rhp.homeowner_id = u.id
            WHERE u.role = 'Homeowner'
            ORDER BY u.id ASC
            """
        )
        rows = cur.fetchall()
        claimant_units = sorted({
            (_display_text(row[2]) or "").strip()
            for row in rows
            if len(row) > 2 and (_display_text(row[2]) or "").strip()
        })
        unit_project_map = {}
        if claimant_units:
            cur.execute(
                """
                SELECT LOWER(TRIM(pu.unit_number)) AS unit_number_norm, dp.project_name
                FROM project_units pu
                JOIN developer_projects dp ON pu.project_id = dp.id
                WHERE LOWER(TRIM(pu.unit_number)) = ANY(%s)
                """,
                ([unit.strip().lower() for unit in claimant_units],),
            )
            unit_project_map = {
                row[0]: _display_text(row[1]) or ""
                for row in cur.fetchall()
                if row and row[0]
            }

        claimants = []
        for row in rows:
            claimant_unit = (_display_text(row[2]) or "-").strip()
            mapped_project_name = unit_project_map.get(claimant_unit.strip().lower(), "")
            row_project_name = (_display_text(row[4]) if len(row) > 4 and row[4] else "") or mapped_project_name
            if normalized_project_name and row_project_name.strip().lower() != normalized_project_name:
                continue
            if role == "Developer" and allowed_project_names is not None:
                if row_project_name.strip().lower() not in allowed_project_names:
                    continue

            claimant_name = (_display_text(row[1]) or "-").strip()
            
            # Remove any unit-like parenthesized fragments from the name to avoid duplication.
            # Handles cases like "Name(PLS-01-02) (PLS-01-02)" by removing all '(...)' groups
            claimant_name = re.sub(r"\s*\([A-Za-z0-9\-\s/]+\)\s*", " ", claimant_name).strip()
            
            # Format as "claimant_name(unit)" - unit from database column only
            display_name = f"{claimant_name}({claimant_unit})" if claimant_name != "-" and claimant_unit != "-" else claimant_name

            claimants.append(
                {
                    "homeowner_id": row[0],
                    "name": display_name,
                    "unit": claimant_unit,
                    "email": _display_text(row[3]) or "-",
                    "project_name": row_project_name or "-",
                }
            )

        if include_unrestricted and normalized_project_name and not claimants:
            # Fallback: scan all users as above and include them in the claimant
            # list (useful when project_name filtering earlier removed matches).
            cur.execute(
                """
                SELECT u.id AS homeowner_id,
                       COALESCE(rhp.name, u.full_name) AS name,
                       COALESCE(rhp.defect_unit, u.unit) AS defect_unit,
                       COALESCE(rhp.email, u.email) AS email,
                       rhp.project_name
                FROM users u
                LEFT JOIN report_homeowner_profile rhp ON rhp.homeowner_id = u.id
                WHERE u.role = 'Homeowner'
                ORDER BY u.id ASC
                """
            )
            fallback_rows = cur.fetchall()
            fallback_units = sorted({
                (_display_text(row[2]) or "").strip()
                for row in fallback_rows
                if len(row) > 2 and (_display_text(row[2]) or "").strip()
            })
            fallback_unit_project_map = {}
            if fallback_units:
                cur.execute(
                    """
                    SELECT LOWER(TRIM(pu.unit_number)) AS unit_number_norm, dp.project_name
                    FROM project_units pu
                    JOIN developer_projects dp ON pu.project_id = dp.id
                    WHERE LOWER(TRIM(pu.unit_number)) = ANY(%s)
                    """,
                    ([unit.strip().lower() for unit in fallback_units],),
                )
                fallback_unit_project_map = {
                    row[0]: _display_text(row[1]) or ""
                    for row in cur.fetchall()
                    if row and row[0]
                }

            for row in fallback_rows:
                claimant_name = (_display_text(row[1]) or "-").strip()
                claimant_unit = (_display_text(row[2]) or "-").strip()
                row_project_name = (
                    (_display_text(row[4]) if len(row) > 4 and row[4] else "")
                    or fallback_unit_project_map.get(claimant_unit.strip().lower(), "")
                )
                if normalized_project_name and row_project_name.strip().lower() != normalized_project_name:
                    continue

                # Strip unit from name if it's already there (format: "Name(Unit)")
                match = re.search(r'^(.+?)\s*\([^)]+\)\s*$', claimant_name)
                if match:
                    claimant_name = match.group(1).strip()

                display_name = f"{claimant_name}({claimant_unit})" if claimant_name != "-" and claimant_unit != "-" else claimant_name

                claimants.append(
                    {
                        "homeowner_id": row[0],
                        "name": display_name,
                        "unit": claimant_unit,
                        "email": _display_text(row[3]) or "-",
                        "project_name": row_project_name or "-",
                    }
                )

        return claimants
    finally:
        cur.close()
        conn.close()


def _is_missing_required(value):
    if value is None:
        return True
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned in {"", "-", "Unknown"}
    return False


def validate_report_requirements(role, user_id=None, claimant_user_id=None):
    report_validation = detect_missing_report_values(
        role=role,
        user_id=user_id,
        claimant_user_id=claimant_user_id,
    )
    return report_validation["messages"]


def detect_missing_report_values(role, user_id=None, claimant_user_id=None, defects=None):
    case_info, claimant, respondent, _, _, _ = _load_report_metadata(
        user_id=user_id,
        role=role,
        claimant_user_id=claimant_user_id,
    )
    active_role = (role or "").strip()

    required_case_fields = {
        "tribunal_location": "Homeowner profile (report_homeowner_profile): Court location",
        "state_name": "Homeowner profile (report_homeowner_profile): State",
        "claim_amount": "Homeowner profile (report_homeowner_profile): Claim amount",
        "transaction_date": "Homeowner profile (report_homeowner_profile): Transaction date",
        "item_service": "Homeowner profile (report_homeowner_profile): Item/service",
    }
    required_claimant_fields = {
        "name": "Homeowner profile (report_homeowner_profile): Name",
        "national_id": "Homeowner profile (report_homeowner_profile): IC number",
        "address_line_1": "Homeowner profile (report_homeowner_profile): Address",
        "phone_number": "Homeowner profile (report_homeowner_profile): Phone number",
        "email": "Homeowner profile (report_homeowner_profile): Email",
    }
    required_respondent_fields = {
        "name": "Respondent profile (report_respondent_profile): Company name",
        "registration_no": "Respondent profile (report_respondent_profile): Registration number",
        "address_line_1": "Respondent profile (report_respondent_profile): Address",
        "phone_number": "Respondent profile (report_respondent_profile): Phone number",
        "email": "Respondent profile (report_respondent_profile): Email",
    }
    required_defect_fields = {
        "id": "Defect record: ID",
        "unit": "Defect record: Unit",
        "desc": "Defect record: Description",
        "reported_date": "Defect record: Reported date",
        "deadline": "Defect record: Deadline",
        "status": "Defect record: Status",
    }

    respondent_for_validation = dict(respondent)
    if active_role in ("Developer", "Legal", "Admin") and user_id is not None:
        conn = get_connection()
        cur = conn.cursor()
        try:
            row = _fetch_respondent_profile_row(
                cur,
                claimant_user_id,
                user_id,
                allow_fallback=False,
            )
            if row:
                respondent_for_validation = _respondent_from_profile_row(row, respondent)
        finally:
            cur.close()
            conn.close()

    missing = {
        "case_info": [],
        "claimant": [],
        "respondent": [],
        "defects": [],
    }

    def _record_missing(bucket, field_key, label):
        bucket.append({"field": field_key, "label": label})

    if active_role == "Homeowner":
        for key, label in required_case_fields.items():
            if _is_missing_required(case_info.get(key)):
                _record_missing(missing["case_info"], key, label)

    if active_role in ("Homeowner", "Developer", "Legal", "Admin"):
        for key, label in required_claimant_fields.items():
            if _is_missing_required(claimant.get(key)):
                _record_missing(missing["claimant"], key, label)

    if active_role in ("Homeowner", "Developer", "Legal", "Admin"):
        for key, label in required_respondent_fields.items():
            if _is_missing_required(respondent_for_validation.get(key)):
                _record_missing(missing["respondent"], key, label)

    if defects:
        for defect in defects:
            defect_missing = []
            for key, label in required_defect_fields.items():
                if _is_missing_required(defect.get(key)):
                    defect_missing.append({"field": key, "label": label})

            if defect.get("status") == "Completed" and _is_missing_required(defect.get("completed_date")):
                defect_missing.append({"field": "completed_date", "label": "Defect record: Completion date"})

            if defect_missing:
                missing["defects"].append({
                    "defect_id": defect.get("id", "unknown"),
                    "missing": defect_missing,
                })

    messages = []
    for item in missing["case_info"]:
        messages.append(item["label"])
    for item in missing["claimant"]:
        messages.append(item["label"])
    for item in missing["respondent"]:
        messages.append(item["label"])
    for defect in missing["defects"]:
        for item in defect["missing"]:
            messages.append(f"Defect {defect['defect_id']}: {item['label']}")

    return {
        "has_missing": bool(messages),
        "messages": [f"Missing {message}" for message in messages],
        "missing": missing,
    }


def _respondent_from_profile_row(row, fallback=None):
    fallback = fallback or {}
    return {
        "name": _display_text(row[0]) or fallback.get("name", "-"),
        "registration_no": _display_text(row[1]) or fallback.get("registration_no", "-"),
        "email": _display_text(row[2]) or fallback.get("email", "-"),
        "phone_number": _display_text(row[3]) or fallback.get("phone_number", "-"),
        "address_line_1": _clean_address_text(row[4]) or fallback.get("address_line_1", "-"),
        "address_line_2": "",
        "description": "Pemaju projek perumahan",
    }


def _fetch_respondent_profile_row(cur, *preferred_ids, allow_fallback=True):
    seen_ids = set()
    for respondent_id in preferred_ids:
        if respondent_id is None or respondent_id in seen_ids:
            continue
        seen_ids.add(respondent_id)
        cur.execute(
            """
            SELECT company_name, registration_number, email, phone_number, address
            FROM report_respondent_profile
            WHERE respondent_id = %s
            LIMIT 1
            """,
            (respondent_id,),
        )
        row = cur.fetchone()
        if row:
            return row

    if not allow_fallback:
        return None

    cur.execute(
        """
        SELECT company_name, registration_number, email, phone_number, address
        FROM report_respondent_profile
        ORDER BY respondent_id ASC
        LIMIT 1
        """
    )
    return cur.fetchone()


def _load_report_metadata(user_id=None, role=None, claimant_user_id=None):
    _ensure_report_metadata_tables()
    _migrate_profile_encryption()

    conn = get_connection()
    cur = conn.cursor()
    try:
        case_info = {
            "tribunal_name": TRIBUNAL_NAME,
            "tribunal_location": DEFAULT_TRIBUNAL_LOCATION,
            "generated_date": _now_app_timezone().strftime("%d-%m-%Y"),
            "claim_amount": DEFAULT_CLAIM_AMOUNT,
            "item_service": DEFAULT_ITEM_SERVICE,
            "transaction_date": "-",
            "document_name": "Dokumen Sokongan Borang 1",
            "state_name": DEFAULT_STATE_NAME,
        }

        claimant = {
            "name": "-",
            "national_id": "-",
            "address_line_1": "-",
            "address_line_2": "-",
            "phone_number": "-",
            "email": "-",
            "unit": "-",
            "description": "-",
        }

        respondent = {
            "name": "-",
            "registration_no": "-",
            "address_line_1": "-",
            "address_line_2": "-",
            "phone_number": "-",
            "email": "-",
            "description": "-",
        }

        user_row = None
        if user_id is not None:
            cur.execute(
                """
                SELECT id, full_name, unit, role, email
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            user_row = cur.fetchone()

        if user_row:
            _, full_name, unit, user_role, user_email = user_row
            full_name = _display_text(full_name)
            unit = _display_text(unit)
            user_email = _display_text(user_email)
            active_role = role or user_role

            if active_role == "Homeowner":
                homeowner_row = None
                cur.execute(
                    """
                    SELECT name, ic_number, email, phone_number, address,
                              court_location, state_name, claim_amount, item_service, transaction_date,
                              project_name
                    FROM report_homeowner_profile
                    WHERE homeowner_id = %s
                    """,
                    (user_id,),
                )
                homeowner_row = cur.fetchone()
                if homeowner_row:
                    claimant = {
                        "name": _display_text(homeowner_row[0]) or claimant["name"],
                        "national_id": _display_text(homeowner_row[1]) or claimant["national_id"],
                        "email": _display_text(homeowner_row[2]) or claimant["email"],
                        "phone_number": _display_text(homeowner_row[3]) or claimant["phone_number"],
                        "address_line_1": _clean_address_text(homeowner_row[4]) or claimant["address_line_1"],
                        "address_line_2": "",
                        "unit": unit or claimant["unit"],
                        "description": "Pemilik unit kediaman",
                    }
                    case_info["tribunal_location"] = _display_text(homeowner_row[5]) or case_info["tribunal_location"]
                    case_info["state_name"] = _display_text(homeowner_row[6]) or case_info["state_name"]
                    case_info["claim_amount"] = _display_text(homeowner_row[7]) or case_info["claim_amount"]
                    case_info["item_service"] = _display_text(homeowner_row[8]) or case_info["item_service"]
                    case_info["transaction_date"] = _format_transaction_date(homeowner_row[9])
                    homeowner_project_name = _display_text(homeowner_row[10]) if len(homeowner_row) > 10 else ""
                else:
                    homeowner_project_name = ""
                if _is_missing_required(claimant.get("name")):
                    claimant["name"] = full_name or claimant["name"]
                if _is_missing_required(claimant.get("email")):
                    claimant["email"] = user_email or claimant["email"]
                if _is_missing_required(claimant.get("address_line_1")):
                    claimant["address_line_1"] = unit or claimant["address_line_1"]
                if _is_missing_required(claimant.get("unit")):
                    claimant["unit"] = unit or claimant["unit"]

                respondent_row = _fetch_respondent_profile_row(cur, user_id)
                if respondent_row:
                    respondent = _respondent_from_profile_row(respondent_row, respondent)
                elif homeowner_project_name:
                    cur.execute(
                        """
                        SELECT
                            d.company_name,
                            d.registration_number,
                            dc.email,
                            dc.phone_number,
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
                        (homeowner_project_name,),
                    )
                    project_respondent_row = cur.fetchone()
                    if project_respondent_row:
                        respondent = {
                            "name": _display_text(project_respondent_row[0]) or respondent["name"],
                            "registration_no": _display_text(project_respondent_row[1]) or respondent["registration_no"],
                            "email": _display_text(project_respondent_row[2]) or respondent["email"],
                            "phone_number": _display_text(project_respondent_row[3]) or respondent["phone_number"],
                            "address_line_1": _clean_address_text(project_respondent_row[4]) or respondent["address_line_1"],
                            "address_line_2": "",
                            "description": "Pemaju projek perumahan",
                        }
            elif active_role in ("Developer", "Legal", "Admin"):
                claimant_row = None

                target_homeowner_id = claimant_user_id or DEFAULT_CLAIMANT_HOMEOWNER_ID
                if target_homeowner_id:
                    cur.execute(
                        """
                        SELECT name, ic_number, email, phone_number, address,
                               court_location, state_name, claim_amount, item_service, transaction_date
                        FROM report_homeowner_profile
                        WHERE homeowner_id = %s
                        LIMIT 1
                        """,
                        (target_homeowner_id,),
                    )
                    claimant_row = cur.fetchone()

                if not claimant_row:
                    # Fallback only if configured homeowner profile is unavailable.
                    cur.execute(
                        """
                        SELECT name, ic_number, email, phone_number, address,
                               court_location, state_name, claim_amount, item_service, transaction_date
                        FROM report_homeowner_profile
                        ORDER BY homeowner_id ASC
                        LIMIT 1
                        """
                    )
                    claimant_row = cur.fetchone()
                if claimant_row:
                    claimant = {
                        "name": _display_text(claimant_row[0]) or claimant["name"],
                        "national_id": _display_text(claimant_row[1]) or claimant["national_id"],
                        "email": _display_text(claimant_row[2]) or claimant["email"],
                        "phone_number": _display_text(claimant_row[3]) or claimant["phone_number"],
                        "address_line_1": _clean_address_text(claimant_row[4]) or claimant["address_line_1"],
                        "address_line_2": "",
                        "unit": "-",
                        "description": "Pemilik unit kediaman",
                    }
                    if target_homeowner_id:
                        cur.execute(
                            "SELECT unit FROM users WHERE id = %s LIMIT 1",
                            (target_homeowner_id,),
                        )
                        claimant_unit_row = cur.fetchone()
                        if claimant_unit_row and claimant_unit_row[0]:
                            claimant["unit"] = _display_text(claimant_unit_row[0]) or claimant["unit"]
                    case_info["tribunal_location"] = _display_text(claimant_row[5]) or case_info["tribunal_location"]
                    case_info["state_name"] = _display_text(claimant_row[6]) or case_info["state_name"]
                    case_info["claim_amount"] = _display_text(claimant_row[7]) or case_info["claim_amount"]
                    case_info["item_service"] = _display_text(claimant_row[8]) or case_info["item_service"]
                    case_info["transaction_date"] = _format_transaction_date(claimant_row[9])

                respondent_row = None

                # For Legal users, prefer the developer responsible for the claimant's project/unit
                # If that cannot be determined, fall back to legal profile or saved respondent.
                if active_role == "Legal":
                    # Try to determine homeowner's project name from profile
                    homeowner_project_name = None
                    if target_homeowner_id:
                        cur.execute(
                            "SELECT project_name FROM report_homeowner_profile WHERE homeowner_id = %s LIMIT 1",
                            (target_homeowner_id,),
                        )
                        row = cur.fetchone()
                        if row and row[0]:
                            homeowner_project_name = _display_text(row[0])

                    if homeowner_project_name:
                        cur.execute(
                            """
                            SELECT
                                d.company_name,
                                d.registration_number,
                                dc.email,
                                dc.phone_number,
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
                            (homeowner_project_name,),
                        )
                        dev_row = cur.fetchone()
                        if dev_row:
                            respondent = {
                                "name": _display_text(dev_row[0]) or respondent["name"],
                                "registration_no": _display_text(dev_row[1]) or respondent["registration_no"],
                                "email": _display_text(dev_row[2]) or respondent["email"],
                                "phone_number": _display_text(dev_row[3]) or respondent["phone_number"],
                                "address_line_1": _clean_address_text(dev_row[4]) or respondent["address_line_1"],
                                "address_line_2": "",
                                "description": "Pemaju projek perumahan",
                            }
                        else:
                            # Fallback to legal profile if developer not found
                            cur.execute(
                                """
                                SELECT legal_name, phone_number, email, office_address
                                FROM report_legal_profile
                                WHERE legal_user_id = %s
                                LIMIT 1
                                """,
                                (user_id,),
                            )
                            legal_row = cur.fetchone()
                            if legal_row:
                                respondent = {
                                    "name": _display_text(legal_row[0]) or respondent["name"],
                                    "registration_no": respondent["registration_no"],
                                    "email": _display_text(legal_row[2]) or respondent["email"],
                                    "phone_number": _display_text(legal_row[1]) or respondent["phone_number"],
                                    "address_line_1": _clean_address_text(legal_row[3]) or respondent["address_line_1"],
                                    "address_line_2": "",
                                    "description": "Peguam / Wakil Undang-undang",
                                }
                    else:
                        # If we couldn't determine project, try saved respondent for homeowner
                        respondent_row = _fetch_respondent_profile_row(
                            cur,
                            target_homeowner_id,
                            user_id,
                        )
                        if respondent_row:
                            respondent = _respondent_from_profile_row(respondent_row, respondent)
                else:
                    # Prefer respondent details saved from the selected homeowner profile.
                    respondent_row = _fetch_respondent_profile_row(
                        cur,
                        target_homeowner_id,
                        user_id,
                    )
                    if respondent_row:
                        respondent = _respondent_from_profile_row(respondent_row, respondent)
                
                if _is_missing_required(respondent.get("name")):
                    respondent["name"] = full_name or respondent["name"]
                if _is_missing_required(respondent.get("email")):
                    respondent["email"] = user_email or respondent["email"]
                if _is_missing_required(respondent.get("address_line_1")):
                    respondent["address_line_1"] = unit or respondent["address_line_1"]

        negeri_codes = dict(STATE_CODES)
        role_contexts = dict(ROLE_CONTEXTS)
        nota_penting = IMPORTANT_NOTE

        return case_info, claimant, respondent, negeri_codes, role_contexts, nota_penting
    finally:
        cur.close()
        conn.close()


# ==================================================
# BUILD SUMMARY STATISTICS (FROM DASHBOARD STATS)
# ==================================================

def build_summary_stats(stats, defects=None):
    """
    Build structured statistical summary
    Includes overdue count and HDA non-compliance count
    """

    def _is_completed_status(value):
        status_value = str(value or "").strip().lower()
        return status_value in {
            "completed",
            "closed",
            "archived",
            "telah diselesaikan",
            "telah selesai",
            "selesai",
            "ditutup",
            "diarkib",
        }

    overdue_count = 0
    hda_non_compliant_count = 0
    completed_total = int(stats.get("completed", 0) or 0)
    closed_total = int(stats.get("closed", 0) or 0)

    if defects:
        overdue_count = len([d for d in defects if d.get("is_overdue")])
        hda_non_compliant_count = len([d for d in defects if d.get("hda_compliant") is False])
        if not completed_total:
            completed_total = len([
                d for d in defects
                if d.get("closed") or _is_completed_status(d.get("status"))
            ])
        if not closed_total:
            closed_total = len([
                d for d in defects
                if d.get("closed") or str(d.get("status", "")).strip().lower() in {"closed", "ditutup", "archived", "diarkib"}
            ])

    total_defects = int(stats.get("total", 0) or 0)
    completion_rate = f"{(completed_total / total_defects * 100):.1f}%" if total_defects > 0 else "0%"

    return {
        "total_defects": total_defects,
        "pending_defects": stats.get("pending", 0),
        "investigation_defects": stats.get("investigation", 0),
        "completed_defects": completed_total,
        "closed_defects": closed_total,
        "completion_rate": completion_rate,
        "critical_defects": stats.get("critical", 0),
        "overdue_defects": overdue_count,
        "hda_non_compliant_defects": hda_non_compliant_count
    }

# ==================================================
# BUILD DEFECT DETAILS (TABLE → REPORT)
# ==================================================

def build_defect_list(defects, role):
    """
    Convert raw defect data into structured report format.
    Remarks are included ONLY for Homeowner.
    """

    report_defects = []

    for d in defects:
        days_to_complete = "-"
        if d.get("reported_date") and d.get("completed_date"):
            try:
                reported_date_obj = datetime.strptime(str(d.get("reported_date"))[:10], "%Y-%m-%d").date()
                completed_date_obj = datetime.strptime(str(d.get("completed_date"))[:10], "%Y-%m-%d").date()
                days_to_complete = max((completed_date_obj - reported_date_obj).days, 0)
            except Exception:
                days_to_complete = "-"

        evidence_filename = d.get("evidence_filename")
        defect_item = {
            "defect_id": d.get("id"),
            "unit": _display_text(d.get("unit")) or "-",
            "description": _display_text(d.get("desc")) or "-",
            "status": d.get("status", "-"),
            "reported_date": d.get("reported_date", "-"),
            "deadline": d.get("deadline", "-"),
            "actual_completion_date": d.get("completed_date") if d.get("completed_date") else "-",
            "days_to_complete": days_to_complete,
            "overdue": "Yes" if d.get("is_overdue") else "No",
            "hda_compliance_30_days": "Yes" if d.get("hda_compliant") else "No",
            "priority": _display_text(d.get("urgency")) or "Normal",
            "evidence_image": f"evidence/{evidence_filename}" if evidence_filename else "-"
        }

        # Only Homeowner sees remarks
        if role == "Homeowner" and d.get("remarks"):
            defect_item["remarks"] = _display_text(d.get("remarks"))

        report_defects.append(defect_item)

    return report_defects

# ==================================================
# GENERATE CLAIM NUMBER (NO TUNTUTAN)
# Format: TTPM/SGR/2026/000001
# ==================================================

def generate_no_tuntutan(negeri, running_no, negeri_codes):
    tahun = _now_app_timezone().year

    negeri_code = _state_code_for_name(negeri, negeri_codes)
    # UNK = Unknown (safety fallback)

    return f"TTPM/{negeri_code}/{tahun}/{running_no:06d}"


def get_or_create_claim_number(state_name, negeri_codes, case_key, homeowner_id=None, respondent_id=None):
    _ensure_report_metadata_tables()

    conn = get_connection()
    cur = conn.cursor()
    try:
        claim_year = _now_app_timezone().year
        state_code = _state_code_for_name(state_name, negeri_codes)

        resolved_homeowner_id = homeowner_id
        if resolved_homeowner_id is None:
            cur.execute(
                """
                SELECT homeowner_id
                FROM report_homeowner_profile
                ORDER BY updated_at DESC, homeowner_id ASC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                resolved_homeowner_id = row[0]

        if resolved_homeowner_id is None:
            cur.execute(
                """
                SELECT id
                FROM users
                WHERE role = 'Homeowner'
                ORDER BY id ASC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                resolved_homeowner_id = row[0]

        if resolved_homeowner_id is None:
            raise ValueError("Cannot generate claim number because no homeowner profile exists.")

        unique_case_key = str(case_key or "").strip()
        if not unique_case_key:
            raise ValueError("Cannot generate claim number because case key is empty.")

        cur.execute(
            """
            SELECT claim_id
            FROM report_claim_registry
            WHERE case_key = %s
            LIMIT 1
            """,
            (unique_case_key,),
        )
        row = cur.fetchone()
        if row and row[0]:
            existing_claim_id = str(row[0])
            if "/UNK/" in existing_claim_id and state_code != "UNK":
                parts = existing_claim_id.split("/")
                case_number = parts[-1] if parts else "000001"
                repaired_claim_id = f"TTPM/{state_code}/{claim_year}/{case_number}"
                cur.execute(
                    """
                    UPDATE report_claim_registry
                    SET claim_id = %s,
                        state = %s,
                        state_code = %s,
                        updated_at = NOW()
                    WHERE case_key = %s
                    RETURNING claim_id
                    """,
                    (repaired_claim_id, state_name, state_code, unique_case_key),
                )
                repaired_row = cur.fetchone()
                conn.commit()
                return repaired_row[0]
            return row[0]

        cur.execute(
            "SELECT COALESCE(MAX(CAST(case_number AS INTEGER)), 0) + 1 FROM report_claim_registry WHERE claim_year = %s AND state_code = %s",
            (claim_year, state_code),
        )
        running_no = int(cur.fetchone()[0])
        case_number = f"{running_no:06d}"
        claim_id = f"TTPM/{state_code}/{claim_year}/{case_number}"

        cur.execute(
            """
            INSERT INTO report_claim_registry (
                claim_id, case_key, case_number, claim_year, date_filed, state, state_code, homeowner_id, respondent_id
            )
            VALUES (%s, %s, %s, %s, NOW(), %s, %s, %s, %s)
            ON CONFLICT (case_key) DO UPDATE
            SET updated_at = NOW()
            RETURNING claim_id
            """,
            (claim_id, unique_case_key, case_number, claim_year, state_name, state_code, resolved_homeowner_id, respondent_id),
        )
        row = cur.fetchone()
        conn.commit()
        return row[0]
    finally:
        cur.close()
        conn.close()

# ==================================================
# ROLE CONTEXT (AI GUIDANCE STRUCTURE)
# ==================================================

def build_role_context(role, role_contexts):
    if role in role_contexts:
        return role_contexts[role]
    if "Legal" in role_contexts:
        return role_contexts["Legal"]
    return {"report_title": "Report", "report_purpose": ""}


# ==================================================
# FINAL REPORT DATA (SEND THIS TO AI)
# ==================================================

def build_report_data(
    role,
    defects,
    stats,
    running_no=None,
    user_id=None,
    case_key=None,
    claimant_user_id=None,
    forced_claim_number=None,
):
    (
        case_info,
        claimant,
        respondent,
        negeri_codes,
        role_contexts,
        nota_penting,
    ) = _load_report_metadata(user_id=user_id, role=role, claimant_user_id=claimant_user_id)
    state_name = case_info["state_name"]

    if forced_claim_number:
        claim_number = str(forced_claim_number)
    elif case_key:
        resolved_homeowner_id = user_id if role == "Homeowner" else claimant_user_id or user_id
        claim_number = get_or_create_claim_number(
            state_name,
            negeri_codes,
            case_key,
            homeowner_id=resolved_homeowner_id,
            respondent_id=user_id if role in ("Developer", "Legal", "Admin") else None,
        )
    else:
        if running_no is None:
            running_no = 1
        claim_number = generate_no_tuntutan(state_name, running_no, negeri_codes)

    case_info = case_info.copy()
    case_info["claim_id"] = claim_number
    case_info["claim_number"] = claim_number
    case_info["state_code"] = _state_code_for_name(state_name, negeri_codes)

    return _display_safe({
        "case_info": case_info,
        "claimant": claimant,
        "respondent": respondent,
        "role_context": build_role_context(role, role_contexts),
        "summary_stats": build_summary_stats(stats, defects),
        "claimant_unit": claimant.get("unit") or case_info.get("claimant_unit") or claimant.get("address_line_1") or "",
        "defect_list": build_defect_list(defects, role),
        "important_note": nota_penting,
    })
