
"""Quick test to verify the decision tree prediction + follow-up extraction."""
import pandas as pd
import numpy as np
from sklearn import preprocessing
from sklearn.tree import DecisionTreeClassifier, _tree
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split

training = pd.read_csv('Data/Training.csv')
training['prognosis'] = training['prognosis'].str.strip()
cols = training.columns[:-1]
x = training[cols]
y = training['prognosis']
reduced_data = training.groupby(training['prognosis']).max()

le = preprocessing.LabelEncoder()
le.fit(y)
y_encoded = le.transform(y)
x_train, x_test, y_train, y_test = train_test_split(x, y_encoded, test_size=0.33, random_state=42)

# Train Decision Tree
dt_clf = DecisionTreeClassifier()
dt_clf.fit(x_train, y_train)

# Train SVM
svm_clf = SVC()
svm_clf.fit(x_train, y_train)

def print_disease(node_value):
    node_val = node_value[0]
    val = node_val.nonzero()
    disease = le.inverse_transform(val[0])
    return list(map(lambda d: d.strip(), list(disease)))

def traverse_tree(tree, feature_names, disease_input):
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
            present_disease = print_disease(tree_.value[node])
            if present_disease:
                result_disease[0] = present_disease[0]

    recurse(0)
    disease = result_disease[0]

    followup_symptoms = []
    if disease and disease in reduced_data.index:
        red_cols = reduced_data.columns
        row_values = reduced_data.loc[[disease]].values[0]
        symptom_indices = row_values.nonzero()
        followup_symptoms = list(red_cols[symptom_indices])

    return disease, followup_symptoms

def get_svm_prediction(symptom, feature_names):
    input_vector = np.zeros(len(feature_names))
    symptom_index = list(feature_names).index(symptom)
    input_vector[symptom_index] = 1
    prediction = svm_clf.predict([input_vector])
    return le.inverse_transform(prediction)[0]

# Test with multiple symptoms
test_symptoms = ['itching', 'headache', 'vomiting', 'chest_pain', 'fatigue']
print("--- Model Prediction Comparison ---")
for sym in test_symptoms:
    dt_disease, followups = traverse_tree(dt_clf, cols, sym)
    svm_disease = get_svm_prediction(sym, cols)
    print(f"\nSymptom: {sym}")
    print(f"  Decision Tree: {dt_disease}")
    print(f"  SVM: {svm_disease}")
    print(f"  Follow-up count: {len(followups)}")
    if followups:
        print(f"  First 5 follow-ups: {followups[:5]}")

print("\n--- Accuracy Scores ---")
print(f"Decision Tree Accuracy: {dt_clf.score(x_test, y_test)}")
print(f"SVM Accuracy: {svm_clf.score(x_test, y_test)}")
