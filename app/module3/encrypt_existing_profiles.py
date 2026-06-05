import argparse
import base64
import hashlib
import os
import sys

SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def _load_env_files():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    project_root = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
    candidates = [
        os.path.join(project_root, ".env"),
        os.path.join(SCRIPT_DIR, ".env"),
    ]
    for env_path in candidates:
        if os.path.exists(env_path):
            load_dotenv(env_path, override=False)


_load_env_files()

try:
    from cryptography.fernet import Fernet, InvalidToken
    from encryption_utils import encrypt_text, is_encrypted_text
except ImportError:
    from cryptography.fernet import Fernet, InvalidToken
    from .encryption_utils import encrypt_text, is_encrypted_text


def _derive_key_material(raw_secret):
    secret = (raw_secret or "").strip() or "dev-secret-key-change-me"
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def _get_fernet(secret):
    return Fernet(_derive_key_material(secret))


def _decrypt_with_secret(secret, value):
    if value is None:
        return ""

    plain_text = str(value)
    if not plain_text:
        return ""

    try:
        return _get_fernet(secret).decrypt(plain_text.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError, UnicodeDecodeError):
        return plain_text


def _rekey_value(value, current_secret, legacy_secret=None):
    if value in (None, ""):
        return ""

    text = str(value)
    current_plain = _decrypt_with_secret(current_secret, text)
    if current_plain != text:
        return encrypt_text(current_plain)

    if legacy_secret:
        legacy_plain = _decrypt_with_secret(legacy_secret, text)
        if legacy_plain != text:
            return encrypt_text(legacy_plain)

    return encrypt_text(text)


def _connect_db():
    db_hosts = []
    configured_host = os.getenv("DB_HOST", "").strip()
    if configured_host:
        db_hosts.append(configured_host)
    if "localhost" not in db_hosts:
        db_hosts.append("localhost")
    if "127.0.0.1" not in db_hosts:
        db_hosts.append("127.0.0.1")

    last_error = None
    for host in db_hosts:
        try:
            return psycopg2.connect(
                host=host,
                database=os.getenv("DB_NAME", "compliance_db"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", "nabilah"),
                port=os.getenv("DB_PORT", "5432"),
                connect_timeout=5,
            ), host
        except Exception as exc:
            last_error = exc

    raise last_error


def main():
    parser = argparse.ArgumentParser(
        description="Encrypt existing plaintext profile rows in report_homeowner_profile and report_respondent_profile."
    )
    parser.parse_args()

    current_secret = os.getenv("REPORT_ENCRYPTION_KEY") or os.getenv("FLASK_SECRET_KEY")
    legacy_secret = "dev-secret-key-change-me"

    # Repair rows that were previously encrypted with the fallback dev secret
    # or inserted manually in plaintext before the app encryption path ran.
    conn, db_host = _connect_db()
    print(f"Using database host: {db_host}")
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
            updated_values = (
                row[1],
                _rekey_value(row[2], current_secret, legacy_secret),
                _rekey_value(row[3], current_secret, legacy_secret),
                _rekey_value(row[4], current_secret, legacy_secret),
                _rekey_value(row[5], current_secret, legacy_secret),
                _rekey_value(row[6], current_secret, legacy_secret),
                _rekey_value(row[7], current_secret, legacy_secret),
                _rekey_value(row[8], current_secret, legacy_secret),
                _rekey_value(row[9], current_secret, legacy_secret),
                _rekey_value(row[10], current_secret, legacy_secret),
                row[0],
            )
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
                updated_values,
            )

        cur.execute(
            """
            SELECT respondent_id, company_name, registration_number, email, phone_number, address
            FROM report_respondent_profile
            """
        )
        for row in cur.fetchall():
            updated_values = (
                row[1],
                _rekey_value(row[2], current_secret, legacy_secret),
                _rekey_value(row[3], current_secret, legacy_secret),
                _rekey_value(row[4], current_secret, legacy_secret),
                _rekey_value(row[5], current_secret, legacy_secret),
                row[0],
            )
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
                updated_values,
            )

        conn.commit()
    finally:
        cur.close()
        conn.close()

    print("Profile rows normalized. Plaintext private fields were encrypted where needed.")


if __name__ == "__main__":
    main()