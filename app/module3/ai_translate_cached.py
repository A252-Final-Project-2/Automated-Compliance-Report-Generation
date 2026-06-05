import hashlib
import json
import os
import re

BASE_CACHE = "cache"
DEFECT_TRANSLATION_CACHE_VERSION = "v6"
REPORT_TRANSLATION_CACHE_VERSION = "v4"
REMARK_TRANSLATION_CACHE_VERSION = "v5"
FIELD_TRANSLATION_CACHE_VERSION = "v4"
AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "180"))
ENABLE_AI_REPORT_GENERATION = os.getenv("ENABLE_AI_REPORT_GENERATION", "0") == "1"
ENABLE_AI_TRANSLATION = os.getenv("ENABLE_AI_TRANSLATION", "1") == "1"
MODEL_NAME = "llama-3.3-70b-versatile"

try:
    from .groqai_client import get_ai_client
except ImportError:  # pragma: no cover - fallback for direct execution from module3/
    from groqai_client import get_ai_client


EN_MARKERS = {
    "the", "and", "or", "not", "for", "with", "on", "from", "to", "in", "is", "it", "are", "was",
    "be", "that", "this", "these", "have", "has", "can", "will", "should", "must", "pending", "completed",
}

MS_MARKERS = {
    "dan", "atau", "yang", "tidak", "untuk", "dengan", "pada", "dari", "ke", "di", "ini", "itu", "adalah",
    "telah", "akan", "boleh", "mesti", "belum", "selesai", "ulasan", "keterangan",
}

# Glossary of domain-specific term mappings to avoid incorrect literal translations
# Keys are lowercase source phrases; values are preferred target translations.
GLOSSARY_MS_TO_EN = {
    "mozek": "mosaic tile",
    "mozek berlubang": "mosaic tile with holes",
}


def _extract_json(text):
    if not text:
        return None
    text = re.sub(r"```json\n?", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip()
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    return match.group(0) if match else None


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _hash_json(data):
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _hash_text(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _cache_path(category, key):
    folder = os.path.join(BASE_CACHE, category)
    _ensure_dir(folder)
    return os.path.join(folder, f"{key}.cache")


def _read_text_cache(cache_file):
    if not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = f.read().strip()
        return cached or None
    except Exception:
        return None


def _write_text_cache(cache_file, value):
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(value)
    except Exception:
        pass


def _read_json_cache(cache_file):
    if not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)
        return cached
    except Exception:
        return None


def _write_json_cache(cache_file, value):
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _tokenize(text):
    # Capture Latin letters including extended characters (Malay/English/Latin-based)
    return re.findall(r"[A-Za-z\u00C0-\u024F]+", (text or "").lower())


def _has_en(text):
    tokens = _tokenize(text)
    return any(token in EN_MARKERS for token in tokens)


def _has_ms(text):
    tokens = _tokenize(text)
    return any(token in MS_MARKERS for token in tokens)


def _is_mixed_language(text):
    return bool(text) and _has_en(text) and _has_ms(text)


def _looks_wrong_language(text, language):
    if not text:
        return False
    if language == "ms":
        return _has_en(text) and not _has_ms(text)
    return _has_ms(text) and not _has_en(text)


def _safe_to_cache_translation(text, language):
    return bool(text) and not _is_mixed_language(text) and not _looks_wrong_language(text, language)


def _defect_cache_usable(defects, language):
    if not isinstance(defects, list):
        return False
    for defect in defects:
        if not isinstance(defect, dict):
            continue
        for key in ("desc", "remarks", "priority"):
            value = defect.get(key)
            if isinstance(value, str) and value.strip() and not _safe_to_cache_translation(value, language):
                return False
    return True


def _translate_text_with_ai(client, text, language, label):
    if not text:
        return text

    target = "Bahasa Malaysia" if language == "ms" else "English"
    prompt = f"""
Translate the following {label} into {target} only.

STRICT RULES:
1. Output ONLY the translated text.
2. Do not mix languages.
3. Preserve original meaning exactly.
4. Keep numbers, IDs, dates, unit names, and proper nouns unchanged.
5. Do not add explanation.

TEXT:
{text}
"""

    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0,
            max_tokens=512,
            timeout=AI_TIMEOUT_SECONDS,
            messages=[
                {
                    "role": "system",
                    "content": f"You are a strict legal translator. Output only {target}. Never mix languages.",
                },
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as e:
        raise e

    translated = (res.choices[0].message.content or "").strip()
    return translated or text


def translate_text_cached(text, language, label, role=""):
    if not text or language not in ("ms", "en"):
        return text

    # Quick glossary override: handle exact or inline domain terms to avoid
    # language-model mistakes (e.g., 'mozek' being mistaken for Polish 'brain').
    if language == 'en':
        lowered = (text or '').lower()
        for src, tgt in GLOSSARY_MS_TO_EN.items():
            # replace whole-word occurrences
            pattern = r"\b" + re.escape(src) + r"\b"
            if re.search(pattern, lowered):
                # apply replacement preserving surrounding text
                replaced = re.sub(pattern, tgt, text, flags=re.IGNORECASE)
                return replaced

    key = f"{FIELD_TRANSLATION_CACHE_VERSION}_{label}_{language}_{role}_{_hash_text(text)}"
    cache_file = _cache_path("fields", key)

    cached = _read_text_cache(cache_file)
    if cached and _safe_to_cache_translation(cached, language):
        return cached

    if not ENABLE_AI_TRANSLATION:
        return text

    try:
        client = get_ai_client()
    except Exception:
        return text

    # First attempt
    try:
        translated = _translate_text_with_ai(client, text, language, label)
    except Exception:
        return text

    # If mixed language detected, retry up to 4 more times with progressively stricter prompts
    retries = 0
    while _is_mixed_language(translated) and retries < 4:
        retries += 1
        translated = _translate_text_with_ai(client, translated, language, f"{label} (retry {retries})")

    # Final fallback: ask AI to force output strictly in target language with ultra-strict prompt
    if _is_mixed_language(translated):
        target = "Bahasa Malaysia" if language == "ms" else "English"
        other_target = "English" if language == "ms" else "Bahasa Malaysia"
        strict_label = f"{label} (FINAL FORCE {language})"
        try:
            # Call with ultra-strict final override prompt
            final_prompt = f"""YOU MUST OUTPUT ONLY IN {target.upper()} AND ZERO WORDS IN {other_target.upper()}.
REMOVE ANY {other_target.upper()} WORDS ENTIRELY.
OUTPUT THE TEXT IN {target.upper()} ONLY.
{translated}"""
            client = get_ai_client()
            res = client.chat.completions.create(
                model=MODEL_NAME,
                temperature=0,
                max_tokens=512,
                timeout=AI_TIMEOUT_SECONDS,
                messages=[
                    {
                        "role": "system",
                        "content": f"MANDATORY: Output ONLY in {target}. ZERO tolerance for mixing languages.",
                    },
                    {"role": "user", "content": final_prompt},
                ],
            )
            translated = (res.choices[0].message.content or "").strip()
        except Exception:
            pass

    if not translated:
        translated = text

    if _safe_to_cache_translation(translated, language):
        _write_text_cache(cache_file, translated)

    return translated


def translate_defects_cached(defects, language="ms", role="Homeowner"):
    if not defects or language not in ("ms", "en"):
        return defects

    full_key_payload = {
        "language": language,
        "role": role,
        "defects": defects,
    }
    full_key = f"{DEFECT_TRANSLATION_CACHE_VERSION}_{_hash_json(full_key_payload)}"
    full_cache = _cache_path("defects", full_key)
    cached_defects = _read_json_cache(full_cache)
    if _defect_cache_usable(cached_defects, language):
        return cached_defects

    translated_defects = []
    full_cache_safe = True

    for defect in defects:
        if not isinstance(defect, dict):
            translated_defects.append(defect)
            continue

        item = dict(defect)

        if isinstance(item.get("desc"), str) and item.get("desc").strip():
            item["desc"] = translate_text_cached(
                item.get("desc", ""),
                language,
                "defect_desc",
                role=role,
            )
            full_cache_safe = full_cache_safe and _safe_to_cache_translation(item["desc"], language)

        # Translate remarks for all roles — ensure report language is consistent
        if isinstance(item.get("remarks"), str) and item.get("remarks").strip():
            item["remarks"] = translate_text_cached(
                item.get("remarks", ""),
                language,
                "defect_remarks",
                role=role,
            )
            full_cache_safe = full_cache_safe and _safe_to_cache_translation(item["remarks"], language)

        if isinstance(item.get("priority"), str) and item.get("priority").strip():
            item["priority"] = translate_text_cached(
                item.get("priority", ""),
                language,
                "defect_priority",
                role=role,
            )
            full_cache_safe = full_cache_safe and _safe_to_cache_translation(item["priority"], language)

        translated_defects.append(item)

    if full_cache_safe:
        _write_json_cache(full_cache, translated_defects)

    return translated_defects


def translate_report_cached(report_text, language="ms", role="Homeowner"):
    if not report_text or language not in ("ms", "en"):
        return report_text

    # Apply glossary overrides for known domain phrases before invoking AI
    if language == 'en':
        replaced = report_text
        for src, tgt in GLOSSARY_MS_TO_EN.items():
            pattern = r"\b" + re.escape(src) + r"\b"
            if re.search(pattern, replaced, flags=re.IGNORECASE):
                replaced = re.sub(pattern, tgt, replaced, flags=re.IGNORECASE)
        if replaced != report_text:
            return replaced

    key = f"{REPORT_TRANSLATION_CACHE_VERSION}_report_{language}_{role}_{_hash_text(report_text)}"
    cache_file = _cache_path("reports", key)

    cached = _read_text_cache(cache_file)
    if cached and not _is_mixed_language(cached) and not _looks_wrong_language(cached, language):
        return cached

    if not ENABLE_AI_TRANSLATION or not ENABLE_AI_REPORT_GENERATION:
        return report_text

    target = "Bahasa Malaysia" if language == "ms" else "English"
    try:
        client = get_ai_client()
    except Exception:
        return report_text
    prompt = f"""
Translate the full report into {target} only.

STRICT RULES:
1. Output plain translated report text only.
2. Do not mix languages.
3. Keep IDs, dates, numbers, and legal references unchanged.
4. Keep list/section structure.

REPORT:
{report_text}
"""

    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0,
            max_tokens=4096,
            timeout=AI_TIMEOUT_SECONDS,
            messages=[
                {
                    "role": "system",
                    "content": f"You are a strict legal translator. Output only {target}. Never mix languages.",
                },
                {"role": "user", "content": prompt},
            ],
        )
    except Exception:
        return report_text

    translated = (res.choices[0].message.content or "").strip() or report_text

    # If mixed language, retry with stricter prompts (similar to translate_text_cached)
    retries = 0
    while _is_mixed_language(translated) and retries < 3:
        retries += 1
        translated = _translate_text_with_ai(client, translated, language, f"full report (retry {retries})")

    # Final ultra-strict override if still mixed
    if _is_mixed_language(translated):
        target = "Bahasa Malaysia" if language == "ms" else "English"
        try:
            final_prompt = f"""YOU MUST OUTPUT ONLY IN {target.upper()} AND ZERO WORDS IN THE OTHER LANGUAGE.
REMOVE ALL MIXED LANGUAGE.
OUTPUT IN {target.upper()} ONLY:
{translated}"""
            res = client.chat.completions.create(
                model=MODEL_NAME,
                temperature=0,
                max_tokens=4096,
                timeout=AI_TIMEOUT_SECONDS,
                messages=[
                    {
                        "role": "system",
                        "content": f"MANDATORY: Output ONLY in {target}. Zero tolerance for language mixing.",
                    },
                    {"role": "user", "content": final_prompt},
                ],
            )
            translated = (res.choices[0].message.content or "").strip()
        except Exception:
            pass

    if translated and not _is_mixed_language(translated) and not _looks_wrong_language(translated, language):
        _write_text_cache(cache_file, translated)

    return translated


def translate_remark_cached(remark_text, language="ms", role="Homeowner"):
    if not remark_text or language not in ("ms", "en"):
        return remark_text

    key = f"{REMARK_TRANSLATION_CACHE_VERSION}_remark_{language}_{role}_{_hash_text(remark_text)}"
    cache_file = _cache_path("remarks", key)

    cached = _read_text_cache(cache_file)
    if cached and _safe_to_cache_translation(cached, language):
        return cached

    if not ENABLE_AI_TRANSLATION:
        return remark_text

    translated = translate_text_cached(remark_text, language, "single_remark", role=role)

    if _safe_to_cache_translation(translated, language):
        _write_text_cache(cache_file, translated)

    return translated


def translate_defect_payload_cached(defects, language="ms", role="Homeowner", include_remarks=False):
    translated = translate_defects_cached(defects, language=language, role=role)
    normalized = []

    for source, item in zip(defects or [], translated or []):
        if not isinstance(item, dict):
            normalized.append(item)
            continue

        defect = dict(item)
        if include_remarks:
            source_remarks = ""
            if isinstance(source, dict):
                source_remarks = source.get("remarks", "")
            remarks = defect.get("remarks") or source_remarks
            defect["remarks"] = translate_remark_cached(remarks, language=language, role=role) if remarks else ""
        else:
            defect["remarks"] = ""
        normalized.append(defect)

    return normalized
