"""
HealthCheck — Gemini Prompt Templates

Improvements over original
───────────────────────────
1. predict_disease_prompt now asks for follow-ups ranked by diagnostic importance,
   capped at exactly 5 (not 4-7, which was too vague and produced long noisy lists).

2. Follow-up symptoms are required to be symptoms a doctor would specifically look
   for to CONFIRM OR RULE OUT the predicted disease — not just generic symptoms.

3. final_diagnosis_prompt has clearer severity criteria and explicitly instructs
   Gemini not to guess when confidence is low.

4. SYSTEM_INSTRUCTION is tightened: no filler text, strict format rules.
"""


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM INSTRUCTION  (injected as system prompt on every call)
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_INSTRUCTION = """
You are a clinical AI assistant supporting a medical symptom-checker application.
Your sole function is to return structured JSON based on the user's symptom data.

STRICT RULES — violating any of these makes the response unusable:
1. Output ONLY a single valid JSON object. No markdown, no code fences (```),
   no prose, no preamble, no trailing text of any kind.
2. Start your response with { and end with }. Nothing else.
3. "severity" must be exactly the string "mild" or the string "serious".
4. "precautions" must be a JSON array of 3–4 short, actionable strings.
5. Descriptions must be factual, 2–3 sentences, written for a general audience.
6. All symptom strings must be plain English, lowercase, no underscores.
7. Never hallucinate diseases. If you are not confident, express uncertainty by
   returning both primary_disease and secondary_disease.
8. Never include the patient's confirmed symptoms in a free-text field —
   only in the confirmed_symptoms array.
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# 1. SYMPTOM SEARCH
# ─────────────────────────────────────────────────────────────────────────────

def search_symptoms_prompt(query: str, max_results: int = 10) -> str:
    """
    Return real medical symptom names that match the user's partial input.
    Used for the autocomplete dropdown.
    """
    return f"""
A user is typing into a medical symptom search box. The text typed so far: "{query}"

Return up to {max_results} real, clinically documented symptoms that:
- Match or begin with the typed text
- Are written in plain English, lowercase, no underscores
- Are specific enough to be diagnostically useful (e.g. "sharp chest pain" not just "pain")

Respond ONLY with this JSON (no markdown, no extra text):
{{"results": ["<symptom 1>", "<symptom 2>", "..."]}}
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# 2. PREDICT — initial symptom → predicted disease + follow-up questions
# ─────────────────────────────────────────────────────────────────────────────

def predict_disease_prompt(symptom: str, num_days: int) -> str:
    """
    Given ONE primary symptom and its duration, predict the most likely disease
    and return exactly 5 follow-up symptoms — ranked by diagnostic importance.

    The follow-ups must be symptoms that a physician would specifically check
    to CONFIRM or RULE OUT the predicted disease. They must NOT be:
    - Generic symptoms that occur in almost every illness (e.g. "fatigue", "headache")
      unless they are genuinely discriminating for this specific disease
    - A rephrasing of the original symptom
    - Vague descriptors (e.g. "feeling unwell")
    """
    return f"""
A patient reports ONE primary symptom: "{symptom}"
Duration: {num_days} day(s)

Task:
1. Identify the single most likely disease or condition for this symptom and duration.
2. List EXACTLY 5 follow-up symptoms that a clinician would ask about specifically
   to CONFIRM OR RULE OUT this disease.
   - Order them from MOST to LEAST diagnostically important for this disease
   - Each must be a distinct, specific symptom (not vague or generic)
   - Use plain English, lowercase, no underscores
   - Do NOT include "{symptom}" itself

Respond ONLY with this JSON (no markdown, no extra text):
{{
  "disease": "<predicted disease name>",
  "followup_symptoms": ["<most important>", "<2nd>", "<3rd>", "<4th>", "<5th>"]
}}
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# 3. FINAL DIAGNOSIS — all confirmed symptoms → complete health report
# ─────────────────────────────────────────────────────────────────────────────

def final_diagnosis_prompt(
    confirmed_symptoms: list,
    num_days: int,
    initial_disease: str,
) -> str:
    """
    Given all confirmed symptoms + duration, produce a complete, accurate diagnosis.

    Severity rules (be strict — do not over-diagnose as serious):
    - "serious" ONLY when:
        • Symptoms include high-risk indicators: chest pain, difficulty breathing,
          altered consciousness, high fever (>103°F/39.4°C), severe abdominal pain,
          sudden weakness/paralysis, or blood in stool/urine/vomit
        • OR symptom duration > 7 days with worsening trend
    - "mild" in all other cases

    If you are uncertain between two diseases (symptom overlap ≥ 60%), provide both.
    """
    symptoms_str  = ", ".join(confirmed_symptoms) if confirmed_symptoms else "none reported"
    symptoms_json = str(confirmed_symptoms)  # safe Python list repr for JSON embedding

    return f"""
Patient's confirmed symptoms: {symptoms_str}
Symptom duration: {num_days} day(s)
Working diagnosis from step 1 (use as context, not a constraint): {initial_disease}

Using your medical knowledge:
1. Determine the most accurate diagnosis based on ALL confirmed symptoms + duration.
   Revise the working diagnosis if the full symptom picture suggests something different.
2. Assess severity using the strict rules below:
   - "serious": high-risk symptom present (chest pain, breathlessness, altered consciousness,
     high fever, severe pain, blood in excretions) OR symptoms > 7 days and worsening
   - "mild": all other cases — do NOT default to "serious" without clear indicators
3. Write a factual description of the primary disease (2–3 sentences, plain language).
4. List 3–4 concrete, actionable precaution steps the patient should take NOW.
5. Set severity_advice:
   - "serious" → "You should consult a doctor as soon as possible."
   - "mild"    → "It might not be that serious, but please take precautions."

If CONFIDENT in one disease, respond ONLY with:
{{
  "primary_disease": "<disease>",
  "severity": "mild",
  "severity_advice": "<advice>",
  "description": "<description>",
  "precautions": ["<step 1>", "<step 2>", "<step 3>"],
  "confirmed_symptoms": {symptoms_json}
}}

If UNCERTAIN between two diseases (significant symptom overlap), respond ONLY with:
{{
  "primary_disease": "<most likely disease>",
  "secondary_disease": "<second possibility>",
  "severity": "mild",
  "severity_advice": "<advice>",
  "description": "<primary description>",
  "secondary_description": "<secondary description>",
  "precautions": ["<step 1>", "<step 2>", "<step 3>"],
  "confirmed_symptoms": {symptoms_json}
}}
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# 4. STRICT JSON RETRY  (used when Gemini's first response is not valid JSON)
# ─────────────────────────────────────────────────────────────────────────────

def medicine_image_prompt(language_name: str) -> str:
    """
    Sent alongside a base64 medicine image to Gemini Vision.
    Instructs Gemini to OCR the label and return structured info
    about the medicine — including type, purpose, MFD, EXP, dosage, warnings.
    Response must be in the user's selected language.
    """
    return f"""
You are a medical label analysis assistant. The user has uploaded a photo of a
medicine strip, bottle, or packaging.

Your job:
1. Read ALL visible text on the label carefully using OCR.
2. Extract and return the following fields in structured JSON.
3. Write ALL human-readable fields (purpose, warnings, dosage, composition)
   in {language_name} language. Keep medicine names, dates, and batch numbers
   in their original form — do not translate those.

Fields to extract:
- medicine_name    : Brand/generic name of the medicine (string)
- medicine_type    : Category of the medicine (e.g., "Antibiotic", "Painkiller", 
                     "Antipyretic", "Antacid", "Vitamin", "Antihistamine", etc.)
                     Classify based on the composition and uses (string)
- composition      : Active ingredients and their strengths (string)
- manufacturer     : Name of the manufacturing company (string)
- mfg_date         : Manufacturing date as printed (string, e.g. "03/2024")
- exp_date         : Expiry date as printed (string, e.g. "02/2026")
- batch_no         : Batch or lot number (string)
- mrp              : Maximum retail price if visible (string, e.g. "₹45.00")
- dosage_form      : Tablet / Capsule / Syrup / Injection / etc. (string)
- purpose          : What this medicine is used to treat — explain clearly in
                     {language_name} in 2–4 sentences for a general audience.
- dosage_info      : Recommended dose/frequency if visible on label (string in {language_name})
- warnings         : Any warnings, contraindications, or storage instructions
                     visible on the label (string in {language_name})
- is_expired       : true if expiry date has passed today's date, false otherwise,
                     null if expiry date could not be read (boolean or null)
- confidence       : "high" / "medium" / "low" — how clearly the label was readable

If a field is not visible or not readable in the image, set it to null.
Do NOT guess or hallucinate any field — only report what is visible.

Respond ONLY with a single valid JSON object. No markdown, no code fences,
no prose before or after. Start with {{ and end with }}.

Example structure (do not copy values, only the keys):
{{
  "medicine_name": "...",
  "medicine_type": "...",
  "composition": "...",
  "manufacturer": "...",
  "mfg_date": "...",
  "exp_date": "...",
  "batch_no": "...",
  "mrp": "...",
  "dosage_form": "...",
  "purpose": "...",
  "dosage_info": "...",
  "warnings": "...",
  "is_expired": false,
  "confidence": "high"
}}
""".strip()


def disease_image_prompt(language_name: str) -> str:
    """
    Analyze a skin disease/condition image and return structured diagnostic info.
    Response in the user's selected language.
    """
    return f"""
You are a dermatology assistant analyzing a skin condition image.

IMPORTANT: This is for informational purposes ONLY. You are NOT diagnosing or
prescribing treatment. Always recommend professional medical evaluation.

Analyze the image and extract:
- disease_name       : Most likely skin condition name (string)
- confidence         : "high" / "medium" / "low" — how clearly visible is the condition
- description        : What this condition is — explain in {language_name} in 2–3 sentences
- symptoms           : Common symptoms of this condition — in {language_name}
- causes             : Known causes or risk factors — in {language_name}
- severity           : "mild" / "moderate" / "severe" — based on visible appearance
- when_to_see_doctor : When to seek professional help — in {language_name}
- treatment_options  : General information about typical treatments (NOT medical advice)
                       in {language_name}
- prevention         : How to prevent or manage this condition — in {language_name}
- disclaimer         : Always include a statement that professional medical evaluation
                       is necessary — in {language_name}

Rules:
- Do NOT make a definitive diagnosis — say "appears to be" or "consistent with"
- Do NOT recommend specific medicines
- Do NOT provide medical advice
- Only describe what is visible in the image
- If the image is not a skin condition, say so clearly
- Set confidence to "low" if the image is unclear or not a skin issue

Respond ONLY with valid JSON. No markdown, no code fences, no prose.
{{
  "disease_name": "...",
  "confidence": "high",
  "description": "...",
  "symptoms": "...",
  "causes": "...",
  "severity": "mild",
  "when_to_see_doctor": "...",
  "treatment_options": "...",
  "prevention": "...",
  "disclaimer": "..."
}}
""".strip()


def strict_json_retry_prompt(original_prompt: str, bad_response: str) -> str:
    """
    Wrap a failed Gemini response in a correction request and retry once.
    Shows only the first 600 chars of the bad response to stay within limits.
    """
    return f"""
Your previous response was not valid JSON and could not be parsed.

What you returned (first 600 chars):
---
{bad_response[:600]}
---

You MUST now return ONLY a raw JSON object:
- Start with {{
- End with }}
- No markdown, no code fences, no explanation, no text outside the JSON

Original task (repeat your answer for this task as valid JSON):
{original_prompt}
""".strip()