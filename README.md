# 🏥 HealthCheck AI — Intelligent Medical Assistant

HealthCheck AI is a modern, multilingual healthcare companion designed to provide preliminary medical assessments, analyze medicine labels, and help users locate nearby medical facilities. Combining traditional Machine Learning (SVC) with cutting-edge Generative AI (Google Gemini 2.0), it offers a seamless, mobile-first experience.

---

## ✨ Key Features

### 💬 Modern Conversational UI
- **WhatsApp-Inspired Experience**: Clean, bubble-based chat interface with "tails" and smooth animations.
- **Project-Themed Aesthetics**: A beautiful Emerald and Warm Cream theme with a professional `Doctor-Consultation.jpg` background.
- **Interactive UX**: Welcome hero with quick-start symptom chips and intelligent autocomplete for over 130+ symptoms.

### 🌍 Global Accessibility (i18n)
Full native support for multiple languages, including:
- 🇬🇧 **English** | 🇮🇳 **Hindi** (हिन्दी) | 🇮🇳 **Bengali** (বাংলা)
- 🇮🇳 **Telugu** (తెలుగు) | 🇮🇳 **Kannada** (ಕನ್ನಡ) | 🇮🇳 **Punjabi** (ਪੰਜਾਬੀ)

### 📸 AI Image Analysis (Exclusive to `geminiapp.py`)
- **Medicine Scanner**: Upload images of medicine strips or bottles to extract:
  - Manufacturer, MFG/EXP dates, Batch No, and MRP.
  - Usage instructions, composition, and therapeutic purpose.
- **Skin Condition Analysis**: Analyze images of skin rashes, infections, or other issues for a preliminary assessment and recommended precautions.

### 📍 Advanced Facility Tracker
- **Smart Proximity Search**: Locate **Hospitals, Pharmacies, and Clinics** within a **25 km radius**.
- **Major Institute Support**: Specifically optimized to find major complexes using OpenStreetMap data.
- **One-Tap Navigation**: Integrated Google Maps directions for every result.

---

## 🛠️ Tech Stack

- **Backend**: Flask (Python)
- **AI/LLM**: Google Gemini 2.0 Flash (`google-genai` SDK)
- **ML Engine**: Scikit-Learn (SVC - Support Vector Classifier)
- **Data Handling**: Pandas, NumPy
- **Frontend**: Vanilla HTML5, CSS3 (Modern Flex/Grid), JavaScript (ES6+)
- **Map Data**: OpenStreetMap via Overpass API

---

## ⚙️ Setup & Installation

### 1. Prerequisites
- Python 3.9+
- A Google Gemini API Key (Get it at [Google AI Studio](https://aistudio.google.com/))

### 2. Configuration
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash
```

### 3. Running the App
- **For the full AI-powered experience** (including Image Analysis & Location Search):
  ```bash
  python geminiapp.py
  ```
- **For the traditional ML-based version**:
  ```bash
  python app.py
  ```

---

## ⚠️ Disclaimer
*HealthCheck AI is for informational purposes only and is NOT a substitute for professional medical advice, diagnosis, or treatment. Always seek the advice of your physician or other qualified health providers with any questions you may have regarding a medical condition. In case of a medical emergency, call your local emergency services immediately.*

---
© 2026 HealthCheck AI. All rights reserved.
