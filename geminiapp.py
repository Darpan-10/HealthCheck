"""
app.py  —  Healthcare Chatbot (100% Gemini-powered)
=====================================================
All diagnostic data — symptom suggestions, disease predictions, descriptions,
precautions, and severity assessments — comes exclusively from Google Gemini.
No local CSV datasets are loaded or referenced.

Required packages:
  pip install flask google-genai python-dotenv

Setup:
  1. Copy .env (provided) and fill in your GEMINI_API_KEY.
  2. Run:  python app.py
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
    final_diagnosis_prompt,
    predict_disease_prompt,
    search_symptoms_prompt,
    strict_json_retry_prompt,
)

# ---------------------------------------------------------------------------
# Environment & Gemini setup
# ---------------------------------------------------------------------------

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

if not GEMINI_API_KEY or GEMINI_API_KEY == "your_api_key_here":
    raise EnvironmentError(
        "GEMINI_API_KEY is not set or still has the placeholder value.\n"
        "1. Create a file named '.env' in the root directory.\n"
        "2. Add 'GEMINI_API_KEY=your_actual_key' to it.\n"
        "Get a key at: https://aistudio.google.com/app/apikey"
    )

# Initialize the new Google Gen AI SDK client
client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Gemini call helper
# ---------------------------------------------------------------------------

def _call_gemini(prompt: str) -> dict:
    """
    Send a prompt to Gemini using the new SDK, strip any accidental markdown fences,
    and parse the response as JSON.
    Retries once with a stricter correction prompt on parse failure.
    """
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.2, # Lower temperature for more consistent JSON
    )

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config
        )
    except Exception as exc:
        err_msg = str(exc)
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            raise ValueError(
                "The AI is currently receiving too many requests (Rate Limit). "
                "Please wait about 30-60 seconds and try again."
            ) from exc
        raise ValueError(f"Gemini API error: {err_msg}") from exc

    raw = response.text.strip()

    # Remove markdown code fences and any text outside them if Gemini adds them
    raw = re.sub(r"^.*?```(?:json)?\s*", "", raw, flags=re.DOTALL)
    raw = re.sub(r"\s*```.*?$",          "", raw, flags=re.DOTALL)

    try:
        return json.loads(raw)

    except json.JSONDecodeError:
        # --- single retry ---
        retry_prompt    = strict_json_retry_prompt(prompt, raw)
        try:
            retry_response  = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=retry_prompt,
                config=config
            )
        except Exception as exc:
            err_msg = str(exc)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                raise ValueError(
                    "The AI is currently receiving too many requests (Rate Limit). "
                    "Please wait about 30-60 seconds and try again."
                ) from exc
            raise ValueError(f"Gemini API error during retry: {err_msg}") from exc

        retry_raw       = retry_response.text.strip()
        # Improved regex to handle text before/after code blocks if necessary
        retry_raw       = re.sub(r"^.*?```(?:json)?\s*", "", retry_raw, flags=re.DOTALL)
        retry_raw       = re.sub(r"\s*```.*?$",          "", retry_raw, flags=re.DOTALL)

        try:
            return json.loads(retry_raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Gemini did not return valid JSON after retry.\nRaw: {retry_raw}"
            ) from exc


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ------------------------------------------------------------------
# GET /api/search-symptoms?q=<query>
# ------------------------------------------------------------------
@app.route("/api/search-symptoms", methods=["GET"])
def search_symptoms():
    """
    Gemini suggests real medical symptoms matching the user's partial query.
    Replaces the old CSV-based pattern matcher entirely.

    Response: { "results": ["symptom 1", "symptom 2", ...] }
    """
    query = request.args.get("q", "").strip()

    if len(query) < 2:
        # Don't waste an API call on single characters
        return jsonify({"results": []})

    prompt = search_symptoms_prompt(query, max_results=10)

    try:
        data = _call_gemini(prompt)
    except ValueError:
        return jsonify({"results": []})  # graceful degradation on error

    results = data.get("results", [])

    # Safety: ensure it's a plain list of strings
    if not isinstance(results, list):
        results = []

    return jsonify({"results": results[:10]})


# ------------------------------------------------------------------
# POST /api/predict
# Body: { "symptom": "itching", "num_days": 5 }
# ------------------------------------------------------------------
@app.route("/api/predict", methods=["POST"])
def predict():
    """
    Step 1 — Gemini predicts the most likely disease from a single symptom
    and returns follow-up symptoms to ask the patient about.

    Response:
    {
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

    prompt = predict_disease_prompt(symptom_raw, num_days)

    try:
        result = _call_gemini(prompt)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 500

    disease  = result.get("disease", "")
    followup = result.get("followup_symptoms", [])

    # Drop the initial symptom if Gemini echoed it back
    followup = [s for s in followup if s.lower() != symptom_raw.lower()]

    if not disease:
        return jsonify({"error": "Gemini could not predict a disease. Try another symptom."}), 400

    return jsonify({
        "disease":           disease,
        "chosen_symptom":    symptom_raw,
        "followup_symptoms": followup,
        "num_days":          num_days,
    })


# ------------------------------------------------------------------
# POST /api/final-diagnosis
# Body:
# {
#     "initial_symptom":    "itching",
#     "disease":            "Fungal infection",
#     "symptom_responses":  { "skin rash": true, "fatigue": false },
#     "num_days":           5
# }
# ------------------------------------------------------------------
@app.route("/api/final-diagnosis", methods=["POST"])
def final_diagnosis():
    """
    Step 2 — Gemini produces a complete diagnosis from all confirmed symptoms.
    All medical content (description, precautions, severity) comes from Gemini.

    Response (confident):
    {
        "primary_disease":   "Fungal infection",
        "severity":          "mild",
        "severity_advice":   "It might not be that serious...",
        "description":       "...",
        "precautions":       ["...", "..."],
        "confirmed_symptoms": [...]
    }

    Response (uncertain — two diseases):
    {
        "primary_disease":        "Fungal infection",
        "secondary_disease":      "Allergy",
        "severity":               "mild",
        "severity_advice":        "...",
        "description":            "...",
        "secondary_description":  "...",
        "precautions":            ["...", "..."],
        "confirmed_symptoms":     [...]
    }
    """
    body              = request.get_json(force=True)
    initial_disease   = body.get("disease", "")
    initial_symptom   = body.get("initial_symptom", "").strip()
    symptom_responses = body.get("symptom_responses", {})
    num_days          = int(body.get("num_days", 1))

    # Collect only the symptoms the patient confirmed as present
    confirmed = [s for s, val in symptom_responses.items() if val is True]

    # Always include the initial symptom at the front
    if initial_symptom and initial_symptom not in confirmed:
        confirmed.insert(0, initial_symptom)

    # Edge-case: patient confirmed nothing — fall back to just the initial symptom
    if not confirmed:
        confirmed = [initial_symptom] if initial_symptom else []

    prompt = final_diagnosis_prompt(confirmed, num_days, initial_disease)

    try:
        result = _call_gemini(prompt)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 500

    # Guarantee confirmed_symptoms is always in the response
    if "confirmed_symptoms" not in result:
        result["confirmed_symptoms"] = confirmed

    return jsonify(result)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development") == "development"
    print(f"Healthcare Chatbot (Gemini) → http://localhost:{port}")
    app.run(debug=debug, port=port)