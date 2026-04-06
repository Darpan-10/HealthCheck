import re
import csv
import numpy as np
import pandas as pd
from flask import Flask, render_template, jsonify, request
from sklearn import preprocessing
from sklearn.tree import DecisionTreeClassifier, _tree
from sklearn.model_selection import train_test_split
from sklearn.svm import SVC
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

app = Flask(__name__)

# Load data & train models on startup

training = pd.read_csv('Data/Training.csv')
testing = pd.read_csv('Data/Testing.csv')
# Clean prognosis names (remove trailing spaces)
training['prognosis'] = training['prognosis'].str.strip()
testing['prognosis'] = testing['prognosis'].str.strip()
cols = training.columns[:-1]
x = training[cols]
y = training['prognosis']

reduced_data = training.groupby(training['prognosis']).max()

le = preprocessing.LabelEncoder()
le.fit(y)
y_encoded = le.transform(y)

x_train, x_test, y_train, y_test = train_test_split(
    x, y_encoded, test_size=0.33, random_state=42
)

clf = DecisionTreeClassifier()
clf.fit(x_train, y_train)

svm_model = SVC()
svm_model.fit(x_train, y_train)

symptoms_dict = {symptom: index for index, symptom in enumerate(cols)}

# Load master data
severity_dict = {}
description_dict = {}
precaution_dict = {}


def load_master_data():
    global severity_dict, description_dict, precaution_dict

    with open('MasterData/Symptom_severity.csv') as f:
        reader = csv.reader(f)
        for row in reader:
            try:
                severity_dict[row[0]] = int(row[1])
            except (IndexError, ValueError):
                pass

    with open('MasterData/symptom_Description.csv') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 2:
                description_dict[row[0]] = row[1]

    with open('MasterData/symptom_precaution.csv') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 5:
                precaution_dict[row[0]] = [row[1], row[2], row[3], row[4]]


load_master_data()



def check_pattern(symptom_list, inp):
    """Find symptoms matching the input pattern."""
    inp = inp.replace(' ', '_')
    regexp = re.compile(inp, re.IGNORECASE)
    matches = [item for item in symptom_list if regexp.search(item)]
    return matches


def sec_predict(symptoms_exp):
    """Secondary prediction using the pre-trained decision tree."""
    input_vector = np.zeros(len(cols))
    for item in symptoms_exp:
        if item in symptoms_dict:
            input_vector[symptoms_dict[item]] = 1

    # Use the globally trained clf
    prediction = clf.predict([input_vector])[0]
    return le.inverse_transform([prediction])[0]


def calc_condition(exp, days):
    """Assess severity."""
    total = sum(severity_dict.get(item, 0) for item in exp)
    if len(exp) == 0:
        return "mild"
    if (total * days) / (len(exp) + 1) > 13:
        return "serious"
    else:
        return "mild"


def print_disease(node_value):
    """Convert a tree leaf node value to a disease name."""
    node_val = node_value[0]
    val = node_val.nonzero()
    disease = le.inverse_transform(val[0])
    return list(map(lambda d: d.strip(), list(disease)))


def traverse_tree(tree, feature_names, disease_input):
    """Walk the decision tree for a given symptom to find the predicted disease
    and the list of follow-up symptoms to ask about."""
    tree_ = tree.tree_
    feature_name = [
        feature_names[i] if i != _tree.TREE_UNDEFINED else "undefined!"
        for i in tree_.feature
    ]

    symptoms_present = []
    result_disease = [None]

    def recurse(node):
        if tree_.feature[node] != _tree.TREE_UNDEFINED:
            name = feature_name[node]
            threshold = tree_.threshold[node]
            val = 1 if name == disease_input else 0
            if val <= threshold:
                recurse(tree_.children_left[node])
            else:
                symptoms_present.append(name)
                recurse(tree_.children_right[node])
        else:
            # Leaf node — extract the predicted disease
            present_disease = print_disease(tree_.value[node])
            if present_disease:
                result_disease[0] = present_disease[0]

    recurse(0)

    disease = result_disease[0]

    # Get follow-up symptoms from reduced_data
    # These are ALL symptoms associated with the predicted disease
    followup_symptoms = []
    if disease and disease in reduced_data.index:
        try:
            red_cols = reduced_data.columns
            # Use [[disease]] to get a DataFrame row, so .values[0] is the full array
            row_values = reduced_data.loc[[disease]].values[0]
            symptom_indices = row_values.nonzero()
            followup_symptoms = list(red_cols[symptom_indices])
        except Exception as e:
            print(f"Error extracting follow-up symptoms: {e}")

    return disease, followup_symptoms


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/symptoms', methods=['GET'])
def get_symptoms():
    """Return sorted list of all symptoms (formatted for display)."""
    symptom_list = sorted([s.replace('_', ' ') for s in cols])
    return jsonify({"symptoms": symptom_list})


@app.route('/api/predict', methods=['POST'])
def predict():
    """
    Accept { symptom: "itching", num_days: 5 }
    Return the initial prediction + follow-up symptom questions.
    """
    data = request.get_json()
    symptom_input = data.get('symptom', '').replace(' ', '_')
    num_days = data.get('num_days', 1)

    # Check if symptom exists
    all_symptoms = list(cols)
    matches = check_pattern(all_symptoms, symptom_input)

    if not matches:
        return jsonify({"error": "No matching symptom found."}), 400

    # Use the first match (or exact match)
    chosen = matches[0]
    if symptom_input in matches:
        chosen = symptom_input

    disease, followup_symptoms = traverse_tree(clf, cols, chosen)

    if not disease:
        return jsonify({"error": "Unable to predict. Try another symptom."}), 400

    # Remove the initial symptom from follow-up list
    followup_symptoms = [s for s in followup_symptoms if s != chosen]

    return jsonify({
        "disease": disease,
        "chosen_symptom": chosen.replace('_', ' '),
        "followup_symptoms": [s.replace('_', ' ') for s in followup_symptoms],
        "num_days": num_days
    })


@app.route('/api/search-symptoms', methods=['GET'])
def search_symptoms():
    """Return symptoms matching a query string."""
    query = request.args.get('q', '')
    if len(query) < 1:
        return jsonify({"results": []})

    all_symptoms = list(cols)
    matches = check_pattern(all_symptoms, query)
    formatted = [s.replace('_', ' ') for s in matches]
    return jsonify({"results": sorted(formatted)[:10]})


def svm_predict(symptoms_exp):
    """Prediction using the pre-trained SVM model."""
    input_vector = np.zeros(len(cols))
    for item in symptoms_exp:
        if item in symptoms_dict:
            input_vector[symptoms_dict[item]] = 1

    prediction = svm_model.predict([input_vector])[0]
    return le.inverse_transform([prediction])[0]


@app.route('/api/final-diagnosis', methods=['POST'])
def final_diagnosis():
    """
    Accept {
        initial_symptom: "itching",
        disease: "Fungal infection",
        symptom_responses: { "skin rash": true, "fatigue": false, ... },
        num_days: 5
    }
    Return final diagnosis with description + precautions + severity.
    """
    data = request.get_json()
    initial_disease = data.get('disease', '')
    initial_symptom = data.get('initial_symptom', '')
    symptom_responses = data.get('symptom_responses', {})
    num_days = data.get('num_days', 1)

    # Collect confirmed symptoms (convert spaces back to underscores for model)
    confirmed = [
        s.replace(' ', '_')
        for s, val in symptom_responses.items()
        if val is True
    ]

    # Also include the initial symptom the user entered
    initial_sym_underscore = initial_symptom.replace(' ', '_')
    if initial_sym_underscore and initial_sym_underscore not in confirmed:
        confirmed.insert(0, initial_sym_underscore)

    # Predictions using both models for comparison
    dt_prediction = sec_predict(confirmed) if confirmed else initial_disease
    svm_prediction = svm_predict(confirmed) if confirmed else initial_disease

    # Severity assessment
    severity = calc_condition(confirmed, num_days)

    # Build result
    if dt_prediction == svm_prediction:
        # Both models agree — confident result
        primary = dt_prediction
        result = {
            "primary_disease": primary,
            "severity": severity,
            "severity_advice": (
                "You should consult a doctor as soon as possible."
                if severity == "serious"
                else "It might not be that serious, but please take precautions."
            ),
            "description": description_dict.get(primary, "No description available."),
            "precautions": precaution_dict.get(primary, []),
            "confirmed_symptoms": [s.replace('_', ' ') for s in confirmed],
        }
    else:
        # Models disagree — show both possibilities
        result = {
            "primary_disease": dt_prediction,
            "secondary_disease": svm_prediction,
            "severity": severity,
            "severity_advice": (
                "You should consult a doctor as soon as possible."
                if severity == "serious"
                else "It might not be that serious, but please take precautions."
            ),
            "description": description_dict.get(dt_prediction, "No description available."),
            "secondary_description": description_dict.get(
                svm_prediction, "No description available."
            ),
            "precautions": precaution_dict.get(dt_prediction, []),
            "confirmed_symptoms": [s.replace('_', ' ') for s in confirmed],
        }

    return jsonify(result)


if __name__ == '__main__':
    # --- Model Accuracy Logging ---
    print("--- Model Training & Evaluation ---")
    # Evaluate Decision Tree
    dt_accuracy = clf.score(x_test, y_test)
    print(f"Decision Tree Accuracy: {dt_accuracy:.4f}")

    # Evaluate SVM
    svm_accuracy = svm_model.score(x_test, y_test)
    print(f"SVM Accuracy: {svm_accuracy:.4f}")
    print("---------------------------------")

    print("Healthcare Chatbot running at http://localhost:5000")
    app.run(debug=True, port=5000)