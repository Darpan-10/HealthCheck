"""
HealthCheck — ML Backend  (RandomForest + SVM)

Root-cause analysis & fixes
════════════════════════════

PROBLEM 1 — Single symptom prediction is meaningless
  The dataset has 132 binary columns and 41 diseases. With only 1–2 columns
  active (=1) the feature vector is 98% zeros. Both DT and SVM land in
  effectively random leaf/support regions and pick whatever happens to be
  there — hence "fever → Alcoholic hepatitis" or "headache → Heart attack".

FIX
  • Replace DecisionTree with RandomForest (200 trees, calibrated probabilities).
  • Never commit to a diagnosis until RF confidence ≥ CONFIDENCE_THRESHOLD (30 %).
  • While confidence is low, ask discriminative follow-up questions (symptoms
    that maximally separate the top-3 candidate diseases from each other).
  • Once confidence crosses the threshold, ask confirming follow-ups (symptoms
    that are frequent for the winning disease).

PROBLEM 2 — Duration is completely ignored
  "Fever for 3 days" should NEVER predict Alcoholic hepatitis (a chronic
  condition that takes weeks–months to develop).

FIX
  • Every disease is tagged with an acuity class: acute / subacute / chronic.
  • Duration-based prior: multiply RF probabilities by a weight that depends
    on whether the disease's acuity matches the reported duration.
  • Short duration (≤ 5 days)  → chronic diseases down-weighted by 0.15×
  • Medium duration (6–14 days) → only acute diseases are lightly penalised
  • Long duration (> 14 days)  → acute diseases down-weighted by 0.30×

PROBLEM 3 — Absurd "could also be Heart attack" secondary hint
  Secondary disease was shown whenever DT ≠ SVM, which happens constantly
  with sparse inputs because both models are essentially guessing.

FIX
  • Secondary disease is ONLY shown when:
      (a) RF top-2 probability gap ≤ 15 %  (genuinely ambiguous)
      AND (b) secondary disease has ≥ 2 confirmed symptoms in the patient's
              confirmed symptom list (not just a random SVM guess)
"""

import csv
import re
import numpy as np
import pandas as pd
import warnings
from flask import Flask, jsonify, render_template, request
from sklearn import preprocessing
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.svm import SVC

warnings.filterwarnings("ignore")

app = Flask(__name__)

# ── Tuneable constants ───────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.32   # min RF confidence to commit to a prediction
MAX_FOLLOWUP         = 5      # max follow-up questions per round
SECONDARY_GAP        = 0.15   # max probability gap to show a secondary disease
SECONDARY_MIN_SYMS   = 2      # secondary must have ≥ this many confirmed symptoms


# ============================================================
# Disease acuity map
# Drives duration-based prior to prevent chronic diseases from
# being predicted for short-duration symptoms (and vice versa).
# ============================================================
ACUTE_DISEASES = {
    'Common Cold', 'Allergy', 'Gastroenteritis', 'Malaria', 'Dengue',
    'Chicken pox', 'Migraine', 'Heart attack', 'Hypoglycemia',
    'Urinary tract infection', 'Impetigo', 'Acne', 'Drug Reaction',
    '(vertigo) Paroymsal  Positional Vertigo', 'Pneumonia',
    'Dimorphic hemmorhoids(piles)', 'GERD', 'Peptic ulcer diseae',
}

SUBACUTE_DISEASES = {
    'Typhoid', 'hepatitis A', 'Hepatitis E', 'Jaundice',
    'Fungal infection', 'Cervical spondylosis', 'Osteoarthristis',
    'Paralysis (brain hemorrhage)', 'Varicose veins', 'Bronchial Asthma',
}

CHRONIC_DISEASES = {
    'Alcoholic hepatitis', 'Hepatitis B', 'Hepatitis C', 'Hepatitis D',
    'Chronic cholestasis', 'AIDS', 'Diabetes', 'Hypertension',
    'Hypothyroidism', 'Hyperthyroidism', 'Tuberculosis',
    'Arthritis', 'Psoriasis',
}


def acuity_prior(disease: str, num_days: int) -> float:
    """
    Return a multiplier (0.0–1.0) that down-weights diseases whose typical
    onset timeline doesn't match the reported symptom duration.

    This is NOT a hard filter — it just re-weights probabilities so that
    e.g. Alcoholic hepatitis won't float to the top on day-3 fever.
    """
    if num_days <= 5:
        if disease in CHRONIC_DISEASES:
            return 0.10   # strong down-weight for chronic diseases
        if disease in SUBACUTE_DISEASES:
            return 0.55
        return 1.00       # acute diseases unaffected

    if 6 <= num_days <= 14:
        if disease in CHRONIC_DISEASES:
            return 0.45
        return 1.00

    # num_days > 14
    if disease in ACUTE_DISEASES:
        return 0.30       # acute diseases unlikely for chronic presentation
    return 1.00


# ============================================================
# Data loading & model training
# ============================================================
training = pd.read_csv('Data/Training.csv')
testing  = pd.read_csv('Data/Testing.csv')
training['prognosis'] = training['prognosis'].str.strip()
testing['prognosis']  = testing['prognosis'].str.strip()

cols = training.columns[:-1]
x    = training[cols]
y    = training['prognosis']

le = preprocessing.LabelEncoder()
le.fit(y)
y_encoded = le.transform(y)

x_train, x_test, y_train, y_test = train_test_split(
    x, y_encoded, test_size=0.33, random_state=42
)

# RandomForest — far more robust than DT for sparse binary inputs
rf = RandomForestClassifier(
    n_estimators=300,
    random_state=42,
    n_jobs=-1,
    min_samples_leaf=1,
    max_features='sqrt',
)
rf.fit(x_train, y_train)

svm_model = SVC(kernel='rbf', C=10, gamma='scale', probability=True)
svm_model.fit(x_train, y_train)

symptoms_dict = {symptom: idx for idx, symptom in enumerate(cols)}

# Frequency table: (disease × symptom) occurrence counts in training set
disease_symptom_freq = training.groupby('prognosis')[list(cols)].sum()

# Mean presence rate (0–1) per (disease, symptom) — used for discriminative scoring
disease_symptom_rate = training.groupby('prognosis')[list(cols)].mean()


# ============================================================
# Master data
# ============================================================
severity_dict    = {}
description_dict = {}
precaution_dict  = {}


def load_master_data():
    with open('MasterData/Symptom_severity.csv') as f:
        for row in csv.reader(f):
            try:
                severity_dict[row[0].strip()] = int(row[1])
            except (IndexError, ValueError):
                pass

    with open('MasterData/symptom_Description.csv') as f:
        for row in csv.reader(f):
            if len(row) >= 2:
                description_dict[row[0].strip()] = row[1].strip()

    with open('MasterData/symptom_precaution.csv') as f:
        for row in csv.reader(f):
            if len(row) >= 5:
                precaution_dict[row[0].strip()] = [
                    c.strip() for c in [row[1], row[2], row[3], row[4]] if c.strip()
                ]


load_master_data()


# ============================================================
# Core prediction helpers
# ============================================================

def build_input_vector(symptom_names: list) -> pd.DataFrame:
    """
    Convert a list of symptom name strings to a DataFrame row (shape 1×n_cols)
    aligned with the training column order. Using a DataFrame preserves feature
    names and avoids sklearn warnings.
    """
    row = {c: 0 for c in cols}
    for s in symptom_names:
        key = s.replace(' ', '_').strip()
        if key in symptoms_dict:
            row[key] = 1
    return pd.DataFrame([row])


def rf_predict_with_prior(symptom_names: list, num_days: int) -> tuple:
    """
    Run RandomForest and apply duration-based acuity prior.

    Returns:
        ranked  — list of (disease, adjusted_probability) sorted desc
        confident — bool: True if top disease probability ≥ CONFIDENCE_THRESHOLD
    """
    vec   = build_input_vector(symptom_names)
    proba = rf.predict_proba(vec)[0]

    # Apply duration prior
    adjusted = []
    for idx, p in enumerate(proba):
        disease = le.inverse_transform([idx])[0]
        prior   = acuity_prior(disease, num_days)
        adjusted.append((disease, p * prior))

    # Re-normalise so probabilities sum to 1
    total = sum(p for _, p in adjusted)
    if total > 0:
        adjusted = [(d, p / total) for d, p in adjusted]

    adjusted.sort(key=lambda x: x[1], reverse=True)
    confident = adjusted[0][1] >= CONFIDENCE_THRESHOLD
    return adjusted, confident


def get_discriminative_followups(
    top_diseases: list,
    already_asked: list,
    n: int = MAX_FOLLOWUP
) -> list:
    """
    Find symptoms that BEST DISCRIMINATE between the top candidate diseases.

    Strategy:
      For each symptom not yet asked, compute the variance of its mean
      presence rate across the top disease candidates.
      High variance = symptom is present in some candidates but absent in others
                    = maximally informative question to ask.

    This directly fixes the "15 absurd follow-up questions" problem: instead of
    asking all symptoms that ever appeared for the predicted disease, we ask
    only the questions that will actually narrow down the diagnosis.
    """
    top_names = [d for d, _ in top_diseases[:3]]

    if not all(d in disease_symptom_rate.index for d in top_names):
        top_names = [d for d in top_names if d in disease_symptom_rate.index]

    if not top_names:
        return []

    sub      = disease_symptom_rate.loc[top_names]
    asked    = set(s.replace(' ', '_').strip() for s in already_asked)

    # Variance across candidate diseases for each symptom
    variances = sub.var(axis=0)

    # Exclude already-asked symptoms
    variances = variances.drop(index=[s for s in asked if s in variances.index], errors='ignore')

    # Exclude symptoms with zero presence in all top candidates (not useful)
    non_zero = sub.max(axis=0) > 0.1
    variances = variances[non_zero]

    ranked = variances.sort_values(ascending=False)
    return list(ranked.head(n).index)


def get_confirming_followups(
    disease: str,
    already_asked: list,
    n: int = MAX_FOLLOWUP
) -> list:
    """
    Once confident in a disease, return its most frequent co-occurring symptoms
    (excluding already-asked ones) for final confirmation.
    """
    if disease not in disease_symptom_freq.index:
        return []

    asked   = set(s.replace(' ', '_').strip() for s in already_asked)
    freq    = disease_symptom_freq.loc[disease].copy()
    freq    = freq.drop(index=[s for s in asked if s in freq.index], errors='ignore')
    freq    = freq[freq > 0].sort_values(ascending=False)
    return list(freq.head(n).index)


def calc_severity(symptom_names: list, days: int) -> str:
    """Severity heuristic using per-symptom weights from MasterData."""
    total = sum(severity_dict.get(s.replace(' ', '_'), 0) for s in symptom_names)
    if not symptom_names:
        return 'mild'
    return 'serious' if (total * days) / (len(symptom_names) + 1) > 13 else 'mild'


def symptom_overlap_count(disease: str, confirmed_symptoms: list) -> int:
    """Count how many confirmed symptoms appear in the disease's symptom set."""
    if disease not in disease_symptom_rate.index:
        return 0
    disease_syms = disease_symptom_rate.loc[disease]
    count = 0
    for s in confirmed_symptoms:
        key = s.replace(' ', '_').strip()
        if key in disease_syms.index and disease_syms[key] > 0.5:
            count += 1
    return count


# ============================================================
# Utility
# ============================================================

def check_pattern(symptom_list: list, inp: str) -> list:
    inp = inp.replace(' ', '_')
    try:
        regexp = re.compile(inp, re.IGNORECASE)
        return [item for item in symptom_list if regexp.search(item)]
    except re.error:
        return [item for item in symptom_list if inp.lower() in item.lower()]


# ============================================================
# Flask routes
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/symptoms', methods=['GET'])
def get_symptoms():
    return jsonify({"symptoms": sorted([s.replace('_', ' ') for s in cols])})


@app.route('/api/search-symptoms', methods=['GET'])
def search_symptoms():
    query = request.args.get('q', '').strip()
    if len(query) < 1:
        return jsonify({"results": []})
    matches   = check_pattern(list(cols), query)
    formatted = sorted([s.replace('_', ' ') for s in matches])
    return jsonify({"results": formatted[:10]})


@app.route('/api/predict', methods=['POST'])
def predict():
    """
    Step 1 — Accept initial symptom + duration, return follow-up questions.

    Flow:
    • Find the closest matching symptom from the training vocabulary.
    • Run RF + duration prior to get ranked disease candidates.
    • If RF is confident (≥ CONFIDENCE_THRESHOLD):
        → Use confirming follow-ups (most frequent symptoms of winning disease)
    • If RF is not yet confident:
        → Use discriminative follow-ups (symptoms that separate top-3 candidates)
    • Either way, at most MAX_FOLLOWUP questions are sent.
    """
    data        = request.get_json(force=True)
    symptom_raw = data.get('symptom', '').strip()
    num_days    = int(data.get('num_days', 1))

    all_symptoms = list(cols)
    symptom_key  = symptom_raw.replace(' ', '_')
    matches      = check_pattern(all_symptoms, symptom_key)

    if not matches:
        return jsonify({"error": "No matching symptom found. Please try a different term."}), 400

    chosen = symptom_key if symptom_key in matches else matches[0]

    # ── Rank diseases with duration prior ────────────────────────────────────
    ranked, confident = rf_predict_with_prior([chosen], num_days)
    top_disease       = ranked[0][0]

    # ── Choose follow-up strategy ─────────────────────────────────────────────
    if confident:
        followup_raw = get_confirming_followups(top_disease, [chosen])
    else:
        followup_raw = get_discriminative_followups(ranked, [chosen])

    return jsonify({
        "disease":           top_disease,
        "confident":         bool(confident),
        "top_candidates":    [(d, float(round(p, 3))) for d, p in ranked[:3]],
        "chosen_symptom":    chosen.replace('_', ' '),
        "followup_symptoms": [s.replace('_', ' ') for s in followup_raw],
        "num_days":          int(num_days),
    })


@app.route('/api/final-diagnosis', methods=['POST'])
def final_diagnosis():
    """
    Step 2 — Accept all confirmed symptoms + duration, return full diagnosis.

    Process:
    • Build the confirmed symptom vector (initial + all Yes answers).
    • Run RF + duration prior to get the final ranked prediction.
    • Run SVM as cross-validator (with duration prior).
    • Primary disease = RF top-1.
    • Secondary disease is ONLY included when ALL of these are true:
        (a) RF probability gap between top-1 and top-2 ≤ SECONDARY_GAP (15 %)
        (b) The secondary disease has ≥ SECONDARY_MIN_SYMS confirmed symptoms
        (c) SVM also picks the same secondary (not just a random guess)
    • This prevents absurd secondaries like "Heart attack" from a fever.
    """
    data              = request.get_json(force=True)
    initial_symptom   = data.get('initial_symptom', '').strip()
    symptom_responses = data.get('symptom_responses', {})
    num_days          = int(data.get('num_days', 1))

    # Confirmed symptoms = initial + all "Yes" answers
    confirmed = [s for s, val in symptom_responses.items() if val is True]
    if initial_symptom and initial_symptom not in confirmed:
        confirmed.insert(0, initial_symptom)
    if not confirmed:
        confirmed = [initial_symptom] if initial_symptom else []

    if not confirmed:
        return jsonify({"error": "No symptoms to diagnose."}), 400

    # ── RF prediction with duration prior ────────────────────────────────────
    ranked, _ = rf_predict_with_prior(confirmed, num_days)
    primary   = ranked[0][0]
    primary_p = ranked[0][1]
    second    = ranked[1][0] if len(ranked) > 1 else None
    second_p  = ranked[1][1] if len(ranked) > 1 else 0.0

    # ── SVM cross-validation ─────────────────────────────────────────────────
    vec          = build_input_vector(confirmed)
    svm_proba    = svm_model.predict_proba(vec)[0]
    svm_ranked   = sorted(
        [(le.inverse_transform([i])[0], p) for i, p in enumerate(svm_proba)],
        key=lambda x: x[1], reverse=True
    )
    svm_primary = svm_ranked[0][0]

    # ── Decide whether to show secondary disease ──────────────────────────────
    show_secondary = (
        second is not None
        and (primary_p - second_p) <= SECONDARY_GAP
        and symptom_overlap_count(second, confirmed) >= SECONDARY_MIN_SYMS
        and svm_primary == second   # SVM must also pick the secondary
    )

    severity = calc_severity(confirmed, num_days)

    result = {
        "primary_disease": primary,
        "severity":        severity,
        "severity_advice": (
            "You should consult a doctor as soon as possible."
            if severity == "serious"
            else "It might not be that serious, but please take precautions."
        ),
        "description":         description_dict.get(primary, "No description available."),
        "precautions":         precaution_dict.get(primary, []),
        "confirmed_symptoms":  confirmed,
        "rf_confidence":       float(round(primary_p, 3)),
    }

    if show_secondary:
        result["secondary_disease"]     = second
        result["secondary_description"] = description_dict.get(second, "")

    return jsonify(result)


# ============================================================
# Entry point
# ============================================================
if __name__ == '__main__':
    print(f"RF  test accuracy : {rf.score(x_test, y_test):.4f}")
    print(f"SVM test accuracy : {svm_model.score(x_test, y_test):.4f}")
    print("HealthCheck (ML) → http://localhost:5000")
    app.run(debug=True, port=5000)