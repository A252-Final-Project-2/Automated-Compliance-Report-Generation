import re
import os
import json
import hashlib

try:
    from .groqai_client import get_ai_client
except ImportError:  # pragma: no cover - fallback for direct execution from module3/
    from groqai_client import get_ai_client

# ==============================
# CONFIG
# ==============================
CACHE_DIR = "cache/defects"
MODEL_NAME = "llama-3.3-70b-versatile"


# ==============================
# UTIL: ensure cache dir exists
# ==============================
def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


# ==============================
# UTIL: hash content (stable key)
# ==============================
def _hash_defects(defects):
    safe = []
    for d in defects:
        dd = d.copy()
        dd.pop("status", None)      # status backend authority
        dd.pop("_status_raw", None) # safety
        safe.append(dd)

    raw = json.dumps(safe, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def _extract_json(text):
    """
    Extract FIRST valid JSON object from AI output.
    Safe against markdown, explanations, extra text.
    """
    if not text:
        raise ValueError("Empty AI response")

    # Remove markdown fences
    text = text.replace("```json", "").replace("```", "").strip()

    # Find JSON block
    match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if not match:
        raise ValueError("No JSON found in AI response")

    return json.loads(match.group(1))

# ==============================
# MAIN TRANSLATION FUNCTION
# ==============================
def ai_translate_defects(defects, language="ms"):
    """
    Auto-translate defect JSON using AI + cache.

    language:
    - "ms" → Bahasa Malaysia
    - "en" → English

    This function:
    ✔ Does NOT modify structure
    ✔ Uses cache to save tokens
    ✔ Safe fallback if AI fails
    """

    # --------------------------------
    # SAFETY CHECKS
    # --------------------------------
    if not defects:
        return defects

    if language not in ("ms", "en"):
        return defects

    # --------------------------------
    # CACHE SETUP
    # --------------------------------
    _ensure_cache_dir()
    data_hash = _hash_defects(defects)
    cache_file = os.path.join(CACHE_DIR, f"{language}_{data_hash}.json")

    # --------------------------------
    # RETURN FROM CACHE (IF EXISTS)
    # --------------------------------
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass  # if cache corrupted → regenerate

    # --------------------------------
    # AI TRANSLATION
    # --------------------------------
    client = get_ai_client()

    target_lang = (
        "Bahasa Malaysia formal pentadbiran Tribunal"
        if language == "ms"
        else "English (formal legal / administrative tone)"
    )

    prompt = f"""
Terjemahkan data JSON berikut ke {target_lang}.

PERATURAN WAJIB:
1. Jangan ubah struktur JSON
2. Jangan tambah atau buang medan
3. Jangan buat analisis, rumusan, atau komen
4. Kekalkan ID, nombor, tarikh, unit tanpa perubahan
5. Terjemahkan desc, remarks, priority SAHAJA
6. Status MESTI KEKAL nilai asal
7. JANGAN TERJEMAH NAMA MEDAN (kunci). Hanya terjemah NILAI untuk medan `desc`, `remarks`, dan `priority`.

DATA JSON:
{json.dumps(defects, ensure_ascii=False)}
"""

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Anda ialah penterjemah dokumen rasmi Tribunal "
                        "Tuntutan Pengguna Malaysia."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
        )

        raw_output = completion.choices[0].message.content
        if not raw_output.strip():
            raise ValueError("Empty AI response")
        translated = _extract_json(raw_output)

        # --------------------------------
        # SAVE TO CACHE
        # --------------------------------
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(translated, f, ensure_ascii=False, indent=2)

        return translated

    except Exception as e:
        # --------------------------------
        # FAIL SAFE
        # --------------------------------
        print("AI translation failed:", e)
        return defects
