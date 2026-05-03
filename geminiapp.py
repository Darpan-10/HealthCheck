"""
HealthCheck — Gemini AI Backend

Improvements over original
───────────────────────────
1. Follow-up list is capped at MAX_FOLLOWUP (5) after Gemini returns it —
   Gemini sometimes returns more than asked despite the prompt saying "exactly 5".

2. Deduplication is case-insensitive and also strips the initial symptom even if
   Gemini returns a slightly different form (e.g. "skin rashes" vs "skin rash").

3. _call_gemini() uses a more robust markdown-fence stripper that handles edge
   cases where Gemini wraps the JSON with text before/after the fences.

4. final_diagnosis route validates the Gemini response has all required keys
   before returning — falls back gracefully instead of sending a broken payload.

5. Rate-limit and API errors are surfaced as proper JSON error responses
   (not bare 500s) so the frontend can display them to the user.
"""

import json
import os
import re

from google import genai
from google.genai import types
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from gemini_prompts import (
    SYSTEM_INSTRUCTION,
    disease_image_prompt,
    final_diagnosis_prompt,
    medicine_image_prompt,
    predict_disease_prompt,
    search_symptoms_prompt,
    strict_json_retry_prompt,
)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
MAX_FOLLOWUP   = 5   # hard cap on follow-up questions sent to the frontend

if not GEMINI_API_KEY or GEMINI_API_KEY == "your_api_key_here":
    raise EnvironmentError(
        "GEMINI_API_KEY is not set or still has the placeholder value.\n"
        "1. Create a file named '.env' in the root directory.\n"
        "2. Add 'GEMINI_API_KEY=your_actual_key' to it.\n"
        "Get a key at: https://aistudio.google.com/app/apikey"
    )

client = genai.Client(api_key=GEMINI_API_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# Flask app
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Gemini call helper
# ─────────────────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """
    Remove markdown code fences from Gemini output.
    Handles:
      - ```json ... ```
      - ``` ... ```
      - Any stray text before the opening { or after the closing }
    """
    # Remove fences entirely
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```", "", text)
    text = text.strip()

    # If there's still garbage before the JSON object, find the first {
    start = text.find('{')
    end   = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    return text


def _call_gemini(prompt: str) -> dict:
    """
    Send a prompt to Gemini, strip markdown, parse JSON.
    Retries ONCE with a stricter correction prompt on parse failure.
    Raises ValueError with a user-friendly message on any unrecoverable error.
    """
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.15,   # low temperature = more deterministic, better JSON compliance
    )

    # ── First attempt ────────────────────────────────────────────────────────
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
    except Exception as exc:
        _raise_api_error(exc)

    raw = _strip_fences(response.text.strip())

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass   # fall through to retry

    # ── Single retry ─────────────────────────────────────────────────────────
    retry_prompt = strict_json_retry_prompt(prompt, raw)

    try:
        retry_response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=retry_prompt,
            config=config,
        )
    except Exception as exc:
        _raise_api_error(exc)

    retry_raw = _strip_fences(retry_response.text.strip())

    try:
        return json.loads(retry_raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Gemini did not return valid JSON after retry.\nRaw output: {retry_raw[:300]}"
        ) from exc


def _raise_api_error(exc: Exception):
    """Convert raw SDK exceptions to user-friendly ValueError messages."""
    msg = str(exc)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        raise ValueError(
            "The AI is currently busy (rate limit reached). "
            "Please wait 30–60 seconds and try again."
        ) from exc
    raise ValueError(f"Gemini API error: {msg}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── GET /api/search-symptoms?q=<query> ──────────────────────────────────────
@app.route("/api/search-symptoms", methods=["GET"])
def search_symptoms():
    """
    Gemini suggests real medical symptoms matching the user's partial query.
    Response: { "results": ["symptom 1", "symptom 2", ...] }
    """
    query = request.args.get("q", "").strip()

    if len(query) < 2:
        return jsonify({"results": []})

    try:
        data = _call_gemini(search_symptoms_prompt(query, max_results=10))
    except ValueError:
        return jsonify({"results": []})   # graceful degradation

    results = data.get("results", [])
    if not isinstance(results, list):
        results = []

    # Ensure all items are strings
    results = [r for r in results if isinstance(r, str)]
    return jsonify({"results": results[:10]})


# ── POST /api/predict ────────────────────────────────────────────────────────
@app.route("/api/predict", methods=["POST"])
def predict():
    """
    Step 1 — Predict disease from one symptom + ask follow-up questions.

    Request:  { "symptom": "itching", "num_days": 5 }
    Response: {
                "disease":           "Fungal infection",
                "chosen_symptom":    "itching",
                "followup_symptoms": ["skin rash", "nodal skin eruptions", ...],
                "num_days":          5
              }
    """
    body        = request.get_json(force=True)
    symptom_raw = body.get("symptom", "").strip()
    num_days    = int(body.get("num_days", 1))

    if not symptom_raw:
        return jsonify({"error": "symptom is required."}), 400

    try:
        result = _call_gemini(predict_disease_prompt(symptom_raw, num_days))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 500

    disease  = result.get("disease", "").strip()
    followup = result.get("followup_symptoms", [])

    if not disease:
        return jsonify({"error": "Could not predict a disease. Try a different symptom."}), 400

    # ── Clean and cap follow-up list ─────────────────────────────────────────
    followup = _clean_followup(followup, symptom_raw)

    return jsonify({
        "disease":           disease,
        "chosen_symptom":    symptom_raw,
        "followup_symptoms": followup,
        "num_days":          num_days,
    })


# ── POST /api/final-diagnosis ────────────────────────────────────────────────
@app.route("/api/final-diagnosis", methods=["POST"])
def final_diagnosis():
    """
    Step 2 — Full diagnosis from all confirmed symptoms.

    Request:  {
                "initial_symptom":   "itching",
                "disease":           "Fungal infection",
                "symptom_responses": { "skin rash": true, "fatigue": false },
                "num_days":          5
              }
    Response: full diagnosis JSON (see gemini_prompts.final_diagnosis_prompt for schema)
    """
    body              = request.get_json(force=True)
    initial_disease   = body.get("disease", "")
    initial_symptom   = body.get("initial_symptom", "").strip()
    symptom_responses = body.get("symptom_responses", {})
    num_days          = int(body.get("num_days", 1))

    # Collect confirmed symptoms only
    confirmed = [s for s, val in symptom_responses.items() if val is True]

    # Always prepend the original symptom
    if initial_symptom and initial_symptom not in confirmed:
        confirmed.insert(0, initial_symptom)

    # Edge-case: patient answered No to everything
    if not confirmed:
        confirmed = [initial_symptom] if initial_symptom else []

    try:
        result = _call_gemini(final_diagnosis_prompt(confirmed, num_days, initial_disease))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 500

    # ── Validate required keys are present ───────────────────────────────────
    required_keys = ["primary_disease", "severity", "severity_advice", "description", "precautions"]
    missing = [k for k in required_keys if k not in result]
    if missing:
        return jsonify({
            "error": f"Gemini response was incomplete (missing: {', '.join(missing)}). Please try again."
        }), 500

    # ── Normalise severity value ─────────────────────────────────────────────
    if result.get("severity", "").lower() not in ("mild", "serious"):
        result["severity"] = "mild"

    # ── Guarantee confirmed_symptoms is in response ──────────────────────────
    if "confirmed_symptoms" not in result:
        result["confirmed_symptoms"] = confirmed

    return jsonify(result)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clean_followup(followup: list, initial_symptom: str) -> list:
    """
    - Remove non-string items
    - Strip whitespace and underscores
    - Remove the initial symptom (exact + fuzzy match)
    - Deduplicate (case-insensitive)
    - Cap at MAX_FOLLOWUP
    """
    if not isinstance(followup, list):
        return []

    initial_norm = initial_symptom.lower().replace('_', ' ').strip()
    seen         = set()
    cleaned      = []

    for item in followup:
        if not isinstance(item, str):
            continue
        item_norm = item.lower().replace('_', ' ').strip()
        if not item_norm:
            continue
        # Skip if it's the same as the initial symptom (exact or substring match)
        if item_norm == initial_norm or initial_norm in item_norm or item_norm in initial_norm:
            continue
        if item_norm in seen:
            continue
        seen.add(item_norm)
        cleaned.append(item_norm)   # store normalised form

    return cleaned[:MAX_FOLLOWUP]


# ── Language code → full name (for Gemini prompt) ───────────────────────────
LANG_FULL_NAME = {
    'en': 'English',
    'hi': 'Hindi',
    'bn': 'Bengali',
    'te': 'Telugu',
    'kn': 'Kannada',
    'pa': 'Punjabi',
}


# ── POST /api/analyze-image ──────────────────────────────────────────────────
@app.route("/api/analyze-image", methods=["POST"])
def analyze_image():
    """
    Accepts a medicine strip / bottle image and returns structured info.

    Request (multipart/form-data):
        image : image file (jpg / png / webp / heic)
        lang  : language code (en / hi / bn / te / kn / pa)  — optional, default 'en'

    Response JSON:
        {
          "medicine_name": "Paracetamol 500mg",
          "composition":   "Paracetamol IP 500mg",
          "manufacturer":  "ABC Pharma Ltd.",
          "mfg_date":      "03/2024",
          "exp_date":      "02/2026",
          "batch_no":      "BX1234",
          "mrp":           "₹25.00",
          "dosage_form":   "Tablet",
          "purpose":       "...(in selected language)...",
          "dosage_info":   "...",
          "warnings":      "...",
          "is_expired":    false,
          "confidence":    "high"
        }
    """
    if 'image' not in request.files:
        return jsonify({"error": "No image file provided. Please upload a medicine image."}), 400

    file = request.files['image']
    lang = request.form.get('lang', 'en').strip().lower()
    lang_name = LANG_FULL_NAME.get(lang, 'English')

    # ── Validate file type ───────────────────────────────────────────────────
    allowed_types = {'image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'}
    mime = file.mimetype or 'image/jpeg'
    if mime not in allowed_types:
        return jsonify({"error": "Unsupported image format. Please upload JPG, PNG, or WebP."}), 400

    # ── Read and encode image ────────────────────────────────────────────────
    try:
        image_bytes = file.read()
    except Exception as e:
        return jsonify({"error": f"Failed to read image: {str(e)}"}), 400

    # ── Build Gemini Vision request ──────────────────────────────────────────
    prompt  = medicine_image_prompt(lang_name)
    config  = types.GenerateContentConfig(
        temperature=0.1,   # very low — we want factual OCR, not creativity
    )
    content = [
        types.Part.from_bytes(data=image_bytes, mime_type=mime),
        prompt,
    ]

    # ── First attempt ────────────────────────────────────────────────────────
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=content,
            config=config,
        )
        raw = _strip_fences(response.text.strip())
    except Exception as exc:
        msg = str(exc)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            return jsonify({"error": "The AI is currently busy. Please wait and try again."}), 429
        return jsonify({"error": f"Gemini API error: {msg}"}), 500

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # ── Retry — include image again so Gemini can re-analyze ─────────────
        retry_content = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
            strict_json_retry_prompt(prompt, raw),
        ]
        try:
            retry_resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=retry_content,
                config=config,
            )
            result = json.loads(_strip_fences(retry_resp.text.strip()))
        except Exception:
            return jsonify({"error": "Could not parse the medicine label. Please try a clearer photo."}), 500

    # ── Safety: ensure required keys exist ──────────────────────────────────
    for key in ('medicine_name', 'medicine_type', 'purpose', 'exp_date', 'mfg_date'):
        result.setdefault(key, None)

    return jsonify(result)


# ── POST /api/analyze-disease-image ──────────────────────────────────────────
@app.route("/api/analyze-disease-image", methods=["POST"])
def analyze_disease_image():
    """
    Analyzes a skin disease/condition image and provides diagnostic information.

    Request (multipart/form-data):
        image : image file (jpg / png / webp)
        lang  : language code (en / hi / bn / te / kn / pa)  — optional, default 'en'

    Response JSON:
        {
          "disease_name": "Eczema",
          "confidence": "high",
          "description": "...(in selected language)...",
          "symptoms": "...",
          "causes": "...",
          "severity": "moderate",
          "when_to_see_doctor": "...",
          "treatment_options": "...",
          "prevention": "...",
          "disclaimer": "..."
        }
    """
    if 'image' not in request.files:
        return jsonify({"error": "No image file provided. Please upload a skin image."}), 400

    file = request.files['image']
    lang = request.form.get('lang', 'en').strip().lower()
    lang_name = LANG_FULL_NAME.get(lang, 'English')

    # ── Validate file type ───────────────────────────────────────────────────
    allowed_types = {'image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'}
    mime = file.mimetype or 'image/jpeg'
    if mime not in allowed_types:
        return jsonify({"error": "Unsupported image format. Please upload JPG, PNG, or WebP."}), 400

    # ── Read and encode image ────────────────────────────────────────────────
    try:
        image_bytes = file.read()
    except Exception as e:
        return jsonify({"error": f"Failed to read image: {str(e)}"}), 400

    # ── Build Gemini Vision request ──────────────────────────────────────────
    prompt  = disease_image_prompt(lang_name)
    config  = types.GenerateContentConfig(
        temperature=0.1,
    )
    content = [
        types.Part.from_bytes(data=image_bytes, mime_type=mime),
        prompt,
    ]

    # ── First attempt ────────────────────────────────────────────────────────
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=content,
            config=config,
        )
        raw = _strip_fences(response.text.strip())
    except Exception as exc:
        msg = str(exc)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            return jsonify({"error": "The AI is currently busy. Please wait and try again."}), 429
        return jsonify({"error": f"Gemini API error: {msg}"}), 500

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # ── Retry — include image again so Gemini can re-analyze ─────────────
        retry_content = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
            strict_json_retry_prompt(prompt, raw),
        ]
        try:
            retry_resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=retry_content,
                config=config,
            )
            result = json.loads(_strip_fences(retry_resp.text.strip()))
        except Exception:
            return jsonify({"error": "Could not analyze the skin image. Please try a clearer photo."}), 500

    # ── Ensure required keys exist ─────────────────────────────────────────
    for key in ('disease_name', 'description', 'disclaimer'):
        result.setdefault(key, None)

    return jsonify(result)

if __name__ == "__main__":
    port  = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development") == "development"
    print(f"HealthCheck (Gemini) → http://localhost:{port}")
    app.run(debug=debug, port=port)