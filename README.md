# 🎓 Campus Lost and Found NLP Challenge

An intelligent, NLP-driven Lost and Found management and semantic matching system for university campuses. Designed to bridge the gap between divergent student vocabularies (e.g., *"Charger is missing"* vs. *"Charging adapter found in library"*), this system leverages **Natural Language Processing (NLP)**, **Domain Ontologies**, **Entity Extraction**, and **Hybrid Semantic Similarity** rather than brittle exact-keyword matching.

---

## 🌟 Key Objectives & Core Features

1. **Natural Language Item Reporting**:
   - Students report lost or found items in everyday conversational language without needing structured, rigid forms.
   - Built-in **Web Speech API Voice Input** allowing students to dictate their descriptions directly.

2. **Synonym & Paraphrase Disambiguation**:
   - Automatically maps semantic variations to canonical concept spaces:
     - `charger` ↔ `charging adapter` ↔ `power brick` ↔ `USB-C cable`
     - `specs` ↔ `spectacles` ↔ `reading glasses` ↔ `shades`
     - `airpods` ↔ `earbuds` ↔ `wireless earphones` ↔ `buds`
     - `hydro flask` ↔ `water bottle` ↔ `tumbler` ↔ `sipper`
     - `id card` ↔ `student badge` ↔ `hall ticket` ↔ `campus pass`
     - `backpack` ↔ `college bag` ↔ `rucksack` ↔ `knapsack`

3. **Hybrid Semantic Matching Pipeline**:
   - **Text Normalization**: Contraction expansion, noise/stopword filtration, tokenization.
   - **Information Extraction (IE)**: Auto-extracts category, visual attributes (color, brand), and campus zones (*Central Library, CS Block, Cafeteria, Sports Complex, Hostel, Laboratories*).
   - **TF-IDF + Sublinear N-gram Cosine Similarity**: Captures morphological and subword variations.
   - **Multi-Attribute Weighted Fusion**:
     $$\text{Total Match Score} = (0.40 \times \text{Text Similarity}) + (0.35 \times \text{Concept Cluster}) + (0.15 \times \text{Location Proximity}) + (0.10 \times \text{Attributes})$$

4. **Automated Notification Dispatch**:
   - When a student posts a report, the matching engine cross-references active counterpart reports in real time.
   - Generates high-confidence alerts ($\ge 65\%$) for both the owner and finder with a 1-click claim and contact workflow.

5. **Interactive NLP Laboratory**:
   - Academic playground to compare any two arbitrary student descriptions.
   - Displays real-time gauges, vector similarity, token extraction, and **Explainable AI (XAI)** justifications.

## Student Accounts, Matching & Alert Delivery

- Registration and sign-in are restricted to the configured university email domain. The default is `kanchiuniv.ac.in`; change `UNIVERSITY_EMAIL_DOMAINS` only to a university-approved domain list.
- Accounts have individual passwords stored as password hashes. Students must create their own app password; do not reuse a Student Portal password.
- A domain allowlist checks the email suffix only. This project does **not** verify that the student owns or can receive mail at that address; add an email verification service before treating it as verified university identity.
- When a lost/found pair scores at least 65%, each participating account receives its own private in-app notification. Active tabs check for updates about every 15 seconds, and alerts are also stored for the next sign-in.
- Students can save a search to receive alerts when a matching opposite-type report appears. Saving a search also checks existing active reports. Users need to select **Save search alert**; ordinary searches are not subscribed automatically.
- This project does not send email, SMS, or push notifications. The live contact email is disclosed only to a student involved in a report match; demo records contain no contact details.
- Reports, accounts, saved searches, and alerts are stored in the SQLite database at `DATABASE_PATH` (default: `data/campus_lost_found.sqlite3`). Existing JSON files are not automatically imported, to avoid unexpectedly exposing sample contact details.
- Synthetic benchmark records are enabled by default for local development but disabled when `APP_ENV=production`. Set `DEMO_SEED=1` only when intentionally running a demonstration dataset.

For a real deployment, use HTTPS, set a stable random `SECRET_KEY`, and point `DATABASE_PATH` at durable storage. The SQLite file must not be placed on an ephemeral/serverless filesystem. Set `APP_ENV=production` so secure session cookies are required. A university email domain allowlist alone is not an identity-verification system.

---

## 📊 Benchmark & Academic Evaluation

An automated benchmark evaluation suite (`evaluate_nlp.py`) validates the semantic engine against positive synonym challenges and negative distractor pairs:

```text
================================================================================
 CAMPUS LOST & FOUND NLP CHALLENGE - SEMANTIC BENCHMARK EVALUATION
================================================================================
ID      | Type     | Score  | Verdict                      | Result | Scenario
--------------------------------------------------------------------------------
POS-01  | positive |  91.5% | High Confidence Match        | PASS   | Charger vs Charging Adapter
POS-02  | positive |  93.4% | High Confidence Match        | PASS   | Specs vs Spectacles
POS-03  | positive |  90.4% | High Confidence Match        | PASS   | AirPods vs Wireless Earbuds
POS-04  | positive |  94.7% | High Confidence Match        | PASS   | Hydro Flask vs Water Bottle
POS-05  | positive |  91.3% | High Confidence Match        | PASS   | ID Card vs Campus Badge
POS-06  | positive |  95.6% | High Confidence Match        | PASS   | Backpack vs College Bag
POS-07  | positive |  93.7% | High Confidence Match        | PASS   | Calculator vs Calc
POS-08  | positive |  94.5% | High Confidence Match        | PASS   | Bunch of keys vs Key ring
NEG-01  | negative |   5.6% | Low Likelihood Match         | PASS   | Bottle vs Charger (Distractor)
NEG-02  | negative |   5.4% | Low Likelihood Match         | PASS   | Keys vs Calculator (Distractor)
NEG-03  | negative |  10.9% | Low Likelihood Match         | PASS   | Laptop vs Earbuds (Distractor)
NEG-04  | negative |   6.5% | Low Likelihood Match         | PASS   | Wallet vs Sunglasses (Distractor)
NEG-05  | negative |  15.5% | Low Likelihood Match         | PASS   | Red umbrella vs Raincoat
NEG-06  | negative |   2.3% | Low Likelihood Match         | PASS   | ID card vs Bag at different zone
================================================================================
Total Test Cases:       14
Accuracy:               100.00%
Precision:              100.00%
Recall:                 100.00%
F1-Score:               100.00%
Average Positive Score: 93.14%
Average Negative Score: 7.70%
Separation Margin:      85.44%
Query Latency:          5.2 ms / query
================================================================================
```

---

## 📁 Project Architecture

```
NLP_CAMPUS LOSTAND SEARCH/
│
├── .venv/                      # Python Virtual Environment
├── data/                       # Runtime SQLite database (ignored by Git)
│   └── campus_lost_found.sqlite3
│
├── static/                     # Premium Dark-Theme Web Interface
│   ├── index.html              # Single Page Application structure
│   ├── style.css               # Glassmorphism, animations & design system
│   └── app.js                  # Frontend logic, live NLP, voice recognition
│
├── nlp_engine.py               # Core NLP Semantic Engine & Ontologies
├── app.py                      # Flask REST API Web Server
├── evaluate_nlp.py             # Academic Evaluation Benchmark Script
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation
```

---

## 🚀 Quickstart Guide

### 1. Activate Virtual Environment
In PowerShell:
```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Run the Benchmark Evaluation
```powershell
python evaluate_nlp.py
```

### 3. Launch the Web Application
```powershell
$env:UNIVERSITY_EMAIL_DOMAINS = "kanchiuniv.ac.in"
python app.py
```
Open your browser and navigate to:
👉 **`http://127.0.0.1:5000`**

The development server generates a temporary session key if `SECRET_KEY` is unset; sessions reset when it restarts. For deployment, set `SECRET_KEY`, `APP_ENV=production`, and a persistent `DATABASE_PATH` in the hosting provider's environment settings.

---

## 🧪 Demonstration Walkthrough

1. **Dashboard & Feed**:
   - Browse existing lost and found reports. Try typing `"charging adapter in library"` in the natural language search bar to see instant matching.
2. **Report New Item**:
   - Select *"I Lost an Item"*.
   - Type description: `"My charger is missing, it is black color 65W with USB-C cable forgotten near library reading hall"`.
   - Observe the **Live NLP Entity Extractor** panel detect the canonical concept `Charger`, color `Black`, location `Central Library`, and alert you in real time that a matching found adapter exists!
   - Submit the report to see instant match notifications.
3. **Smart Matches**:
   - View automated cross-matches with similarity percentages and explanations.
4. **NLP Laboratory**:
   - Click the preset *"1. Charger ↔ Adapter (User Case)"* and click *"Run NLP Matcher"*.
   - View the 91.5% similarity score, gauge, and extracted semantic attribute comparison.
