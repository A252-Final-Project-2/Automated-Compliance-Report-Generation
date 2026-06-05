import base64
import hashlib
import os
from functools import lru_cache

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError as exc:  # pragma: no cover - dependency error is surfaced at runtime
    raise ImportError(
        "cryptography is required for at-rest encryption. Install it with pip install cryptography."
    ) from exc


def _derive_key_material(raw_secret):
    secret = (raw_secret or "").strip() or "dev-secret-key-change-me"
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


@lru_cache(maxsize=1)
def _get_fernet():
    raw_secret = os.getenv("REPORT_ENCRYPTION_KEY") or os.getenv("FLASK_SECRET_KEY")
    return Fernet(_derive_key_material(raw_secret))


def _candidate_secrets():
    secrets = [
        os.getenv("REPORT_ENCRYPTION_KEY"),
        os.getenv("FLASK_SECRET_KEY"),
    ]

    previous_keys = os.getenv("REPORT_ENCRYPTION_PREVIOUS_KEYS") or os.getenv("FLASK_SECRET_KEY_PREVIOUS") or ""
    for secret in previous_keys.replace(";", ",").split(","):
        secrets.append(secret)

    secrets.append("dev-secret-key-change-me")

    seen = set()
    for secret in secrets:
        normalized = (secret or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            yield normalized


def _decrypt_with_secret(secret, token):
    try:
        return Fernet(_derive_key_material(secret)).decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return None


def is_encrypted_text(value):
    token = str(value or "").strip()
    if not token.startswith("gAAAA"):
        return False

    for secret in _candidate_secrets():
        try:
            Fernet(_derive_key_material(secret)).decrypt(token.encode("utf-8"))
            return True
        except Exception:
            continue
    return False


def encrypt_text(text):
    if text is None:
        return ""

    if hasattr(text, "isoformat"):
        text = text.isoformat()

    plain_text = str(text)
    if not plain_text:
        return ""
    if is_encrypted_text(plain_text):
        return plain_text
    if plain_text.strip().startswith("gAAAA"):
        return plain_text.strip()

    return _get_fernet().encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_text(text):
    if text is None:
        return ""

    plain_text = str(text)
    if not plain_text:
        return ""

    current_text = plain_text
    for _ in range(3):
        token = current_text.strip()
        if not token.startswith("gAAAA"):
            return current_text

        decrypted_text = None
        for secret in _candidate_secrets():
            decrypted_text = _decrypt_with_secret(secret, token)
            if decrypted_text is not None:
                break

        if not decrypted_text or decrypted_text == current_text:
            return ""
        current_text = decrypted_text

    return "" if current_text.strip().startswith("gAAAA") else current_text
