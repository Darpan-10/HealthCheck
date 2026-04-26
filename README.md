# 🏥 Healthcare Chatbot

## 🎯 Purpose

The Healthcare Chatbot is an intelligent assistant designed to help users identify potential medical conditions based on their symptoms. By engaging in a conversational interface, the application prompts users for symptoms, evaluates the severity and duration, and provides a preliminary medical diagnosis along with descriptions and preventive measures. It serves as a sophisticated first point of reference for health-related queries, though it does not replace professional medical consultation.

## 🛠️ Tech Stack & Requirements

The project is built with Python, emphasizing machine learning and modern generative AI technologies.

- **Backend:** Flask (Python web framework)
- **Machine Learning & Data Processing:** `scikit-learn`, `pandas`, `numpy`
- **Generative AI:** `google-genai` (Google Gemini SDK)
- **Other Utilities:** `python-dotenv` (for loading environment variables), `pyttsx3`, `pydantic`
- **Frontend:** HTML, CSS (Vanilla Custom Styles), JavaScript

**`requirements.txt`:**

```text
scikit-learn
pandas
pyttsx3
flask
google-genai
pydantic>=2.0
python-dotenv
```

## 🧠 Machine Learning Strategies

The project explores different approaches for disease prediction based on patient symptoms:

- **Support Vector Classifier (SVC) — [IN USE]:** The primary traditional machine learning model deployed for accurate pattern recognition in symptom-to-disease mapping. It evaluates a unified input vector of confirmed symptoms to predict the underlying condition robustly.
- **Decision Tree — [NOT IN USE]:** While implemented code exists in earlier portions, the Decision Tree approach is functionally sidelined in favor of SVC's reliability.
- **Google Gemini API Integration 🎉:** Moving beyond traditional static datasets, the application integrates **Google Gemini** (via the new `google-genai` SDK) for a fully dynamic, conversational AI flow. In the modern iteration, Gemini intelligently handles:
  - Smart symptom extraction and fuzzy search matching.
  - Generating context-aware follow-up symptom questions tailored to the initially reported issue.
  - Formulating the comprehensive final diagnosis, assessing severity, and advising on detailed precautions.

## ⚙️ Setup Process

Follow these steps to get the project running locally:

1. **Clone the Repository**

   ```bash
   git clone <repository_url>
   cd healthcare-chatbot
   ```

2. **Create a Virtual Environment**

   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables Configuration**
   - Create a `.env` file in the root directory. You can use `.env.example` as a template.
   - Add your Google Gemini API key:

     ```env
     GEMINI_API_KEY=your_actual_key_here
     ```

     *(You can get a free API key at [Google AI Studio](https://aistudio.google.com/app/apikey))*

5. **Run the Application**
   - To launch the fully AI-driven version:

     ```bash
     python geminiapp.py
     ```

   - Alternatively, to launch the traditional ML-based version:

     ```bash
     python app.py
     ```

6. **Access the Web App**
   Open your browser and navigate to `http://localhost:5000`.

---
*Disclaimer: This tool is for informational purposes only. In case of a medical emergency or serious symptoms, please consult a qualified healthcare professional immediately.*
