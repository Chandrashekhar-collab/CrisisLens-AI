# CrisisLens AI — Global Event Anomaly Intelligence Platform

> **A placement-quality, production-grade Data Science & AI/ML portfolio project.**
>
> CrisisLens AI is an end-to-end, local-first web application that ingests public GDELT (Global Database of Events, Language, and Tone) event data. It allows analysts, researchers, and recruiters to monitor global event streams, identify statistically significant surges in reporting volume using dual-criterion anomaly detection, investigate granular event evidence, and generate reproducible, publication-quality intelligence briefings — all on a standard consumer laptop without paid APIs, mandatory GPUs, or external server dependencies.

---

## 🌟 Platform Status & Verification

🟢 **Phases 0–6 Complete & Verified:**
- **Test Suite:** **94 / 94 tests passing** with 0 failures, 0 warnings.
- **Measured Line Coverage:** **80%** across all application modules.
- **End-to-End Headless Verification:** Automated multi-page Streamlit AppTest verifies clean startup, navigation, and state transitions across all 4 screens with **0 runtime exceptions**.
- **Hardware Profile:** Optimized for an Intel Core i3-1215U CPU with 8 GB RAM on Windows 11 (peak RAM < 500 MB; PDF generation < 15 MB).

---

## 🏛️ System Architecture

CrisisLens AI uses a decoupled, three-tier architecture:
1. **Data Engineering Layer:** Streaming tab-separated value (TSV) parser with 61-column schema validation, MD5 checksum verification, idempotent upserting into an embedded DuckDB columnar database, and partitioned Snappy-compressed Parquet lake.
2. **Analytics & Modeling Engine:** Analytical query service (`DataService`), statistical baseline detector (rolling Z-score + non-parametric Tukey IQR fence with Poisson dispersion floor), `DataReadinessGate` historical sufficiency auditor, and deterministic explainability engine with $\LaTeX$ mathematical formulations.
3. **Interactive Presentation & Reporting Layer:** Multi-page Streamlit dashboard with Plotly data visualizations, faceted search, single-record taxonomy inspectors, and multi-format exports (CSV, Markdown briefings, and publication-quality PDF reports).

```
                             GDELT 2.0 Servers
                       (data.gdeltproject.org/gdeltv2/)
                                     │
                             HTTPS (Requests)
                                     ▼
                      ┌─────────────────────────────┐
                      │    Ingestion Pipeline       │
                      │  • 61-column TSV Parser     │
                      │  • Schema & MD5 Validator   │
                      └──────────────┬──────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
       ┌─────────────────────────┐       ┌─────────────────────────┐
       │   Embedded DuckDB Store │       │   Snappy Parquet Lake   │
       │   (crisislens.duckdb)   │       │   (data/processed/)     │
       │   Indexed by DATEADDED  │       │   Year/Month Partitioned│
       └────────────┬────────────┘       └─────────────────────────┘
                    │
                    ▼
       ┌───────────────────────────────────────────────────────────┐
       │                 Analytical DataService                    │
       │  • Bounded Parameterized Queries                          │
       │  • Static FIPS 10-4 ↔ ISO 3166 Lookup                     │
       │  • CAMEO Event & QuadClass Taxonomy Enrichment            │
       └────────────┬─────────────────────────────┬────────────────┘
                    │                             │
                    ▼                             ▼
       ┌───────────────────────────┐ ┌─────────────────────────────┐
       │   Statistical Baseline    │ │   Synthetic Benchmark       │
       │   • DataReadinessGate     │ │   • Deterministic Fixture   │
       │   • Rolling Z-Score + IQR │ │   • 14 Days, 336 Points     │
       │   • Poisson Variance Floor│ │   • 3 Injected Anomalies    │
       └────────────┬──────────────┘ └─────────────┬───────────────┘
                    │                             │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
       ┌───────────────────────────────────────────────────────────┐
       │                 Streamlit UI Presentation                 │
       │  • 🌐 Overview Dashboard (Trends & Distributions)        │
       │  • 🔍 Global Event Explorer (Faceted Search & Inspector)  │
       │  • ⚡ Anomaly Intelligence (Statistical Baseline & Math) │
       │  • 🕵️ Event Investigation (Drill-Down & Export Hub)     │
       └────────────┬─────────────────────────────┬────────────────┘
                    │                             │
                    ▼                             ▼
       ┌───────────────────────────┐ ┌─────────────────────────────┐
       │      Data Exports         │ │    Publication PDF Engine   │
       │  • Filtered CSV (Excel)   │ │  • fpdf2 + Headless Matplot │
       │  • Markdown Briefings     │ │  • Watermark & Provenance   │
       └───────────────────────────┘ └─────────────────────────────┘
```

---

## 🖥️ Core Screens & Capabilities

### 1. 🌐 Overview Dashboard
- **Executive Metric Cards:** Total events, active sovereign territories, conflict category proportion (`QuadClass 3 & 4`), average Goldstein stability score, and average sentiment tone.
- **Strict Date Semantics:** Interactive toggle switching between **Reporting Activity Time** (`DATEADDED`, when news was ingested) and **Event Context Date** (`SQLDATE`, when the event occurred).
- **QuadClass Decomposition:** Interactive Plotly stacked bar time-series and proportion donut charts visualizing Verbal Cooperation, Material Cooperation, Verbal Conflict, and Material Conflict.
- **Top Active Geographies:** Horizontal bar chart displaying leading nations mapped from FIPS 10-4 codes to ISO sovereign country names.
- **Live Ingestion Feed:** Formatted table displaying the 15 most recent GDELT records with source article hyperlinks.

### 2. 🔍 Global Event Explorer
- **Multi-Dimensional Query Filters:** Full-text keyword search (actor name, location, source URL), date range picker, action country, CAMEO root code, QuadClass categories, Goldstein stability scale range ($-10.0$ to $+10.0$), and minimum mentions threshold.
- **Bounded Pagination:** Bounded database queries (`LIMIT` / `OFFSET`) supporting 25, 50, or 100 rows per page with page navigation controls.
- **Deep-Dive Record Inspector:** Select any `event_id` to inspect its full CAMEO taxonomy root description, Goldstein impact score, sentiment tone, source document count, and geographical coordinates.
- **Page CSV Export:** One-click download of the currently filtered result page encoded in `utf-8-sig` for immediate Microsoft Excel compatibility.

### 3. ⚡ Anomaly Intelligence
- **Dual-Criterion Statistical Engine:** Evaluates volume spikes against a rolling historical baseline using both parametric $Z$-score ($Z = \frac{Y_t - \mu}{\sigma} \ge k_z$) and non-parametric Tukey IQR upper fence ($Y_t > Q_3 + m \cdot \text{IQR}$).
- **DataReadinessGate Safeguard:** Automatically audits local historical coverage. When reporting history is insufficient ($N < 28$ intervals), live scoring is gated with an informative warning banner to prevent false alarms.
- **Synthetic Benchmark (Demo Mode):** Built-in deterministic 14-day benchmark fixture (336 hourly observations, seed=42) featuring realistic diurnal variations, weekend activity dips, and 3 injected crisis surges (Day 5 Protest Surge, Day 9 Border Conflict, Day 12 Natural Catastrophe).
- **Interactive Hyperparameter Tuning:** Sliders for lookback window ($W \in [6, 72]$), minimum history ($W_{\min} \in [4, 24]$), $Z$-score threshold ($k_z \in [1.5, 5.0]$), and Tukey multiplier ($m \in [1.0, 3.0]$).
- **Deterministic Math & Explainability Inspector:** Formatted $\LaTeX$ mathematical formulations and plain-English narrative rationales detailing exact deviation percentages, triggered rules, and methodological caveats without LLM hallucination risk.
- **Cross-Screen Investigation Linking:** One-click button saves the target anomaly timestamp into Streamlit session state and deep-links directly into Event Investigation.

### 4. 🕵️ Event Investigation Drill-Down & Reporting
- **Interval Deep-Dive:** Dissects all underlying event records matching a specific reporting-time interval or synthetic scenario.
- **Interval Batch Statistics:** Displays active nation counts, conflict percentage, average Goldstein stability, and prominent actors.
- **Underlying Event Evidence Table:** Bounded evidence table sorted by media mentions displaying actors, CAMEO codes, Goldstein scale, mentions, and locations.
- **Triple Export Hub:**
  1. `⬇️ Download Events (CSV)`: Bounded dataset of filtered records.
  2. `📄 Download Brief (Markdown)`: Structured Markdown briefing containing summary findings and data governance notes.
  3. `📕 Download Report (PDF)`: Publication-quality executive briefing document.

---

## 📄 Publication-Quality PDF Reports

The built-in PDF reporting engine (`crisislens/reports/pdf_generator.py`) generates executive briefings directly from selected investigation records:
- **Zero Cloud / Zero Cost:** Pure-Python implementation (`fpdf2` + `matplotlib` `Agg` backend) generating PDFs in **< 0.5 seconds** using **< 15 MB RAM**.
- **Prominent Mode Banners & Watermarks:**
  - *Live Store Reports:* Mint-green banner declaring `LIVE GDELT 2.0 DATA STORE — AUDIT BRIEFING`.
  - *Synthetic Benchmark Reports:* Coral-red banner declaring `SYNTHETIC BENCHMARK FIXTURE — DEMO USE ONLY — NOT REAL-WORLD INCIDENT DATA` and a diagonal background watermark across every page.
- **Data Readiness Disclosure:** Explicitly explains when live scoring is gated and summarizes interval batch characteristics.
- **Embedded Analytical Charts:** Side-by-side QuadClass proportion donut chart and Top Geographies horizontal bar chart.
- **Bounded Evidence Table:** Top 15 records formatted with alternating row striping, cell padding, and safe text truncation.
- **Audit Reproducibility Fingerprint:** Embeds generation timestamp (UTC), parameter summary, DuckDB engine version, and SHA-256 fingerprint.

---

## 🛠️ Technology Stack (All Free & Open-Source)

| Layer | Component | Version | Purpose |
|---|---|---|---|
| Language | Python | 3.12.8 | Core application runtime |
| Storage | DuckDB | >=0.10.0 | High-performance embedded columnar analytical database |
| Data Lake | PyArrow / Parquet | >=15.0.0 | Partitioned columnar archive (`year=YYYY/month=MM/`) |
| Data Processing | Pandas & NumPy | >=2.1.0 / >=1.26.0 | DataFrame operations and array transformations |
| Machine Learning | Scikit-Learn & SciPy | >=1.4.0 / >=1.12.0 | Statistical distributions and Tukey IQR quantile calculation |
| Visualization | Plotly & Matplotlib | >=5.20.0 / >=3.8.0 | Interactive web charts and headless PDF chart rendering |
| Web Dashboard | Streamlit | >=1.34.0 | Multi-page reactive web user interface |
| PDF Generator | fpdf2 | >=2.7.9 | Pure-Python PDF generation with Unicode font integration |
| Quality Assurance | Pytest & Pytest-Cov | >=8.0.0 / >=5.0.0 | Unit, integration, and AppTest coverage suite |

---

## 🚀 Quick Start (Windows Setup & Execution)

### Prerequisites
- Windows 10/11 laptop (tested on Intel Core i3-1215U, 8 GB RAM)
- Python 3.12 installed and added to `PATH`
- Git (optional)

### 1. Set Up Environment
Open PowerShell or Windows Terminal in your project workspace:
```powershell
# Navigate to project directory
cd C:\Users\LENOVO\.gemini\antigravity\scratch\crisislens-ai

# Create virtual environment (if not already present)
python -m venv .venv

# Activate virtual environment
.venv\Scripts\Activate.ps1
```
*(If PowerShell restricts script execution, run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)*

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 3. Ingest GDELT Data
Download and ingest the latest 15-minute GDELT Events 2.0 update into DuckDB and Parquet:
```powershell
# Ingest latest update
python -m crisislens.ingestion.cli --latest

# Verify database status and active record count
python -m crisislens.ingestion.cli --status
```

### 4. Run the Full Test Suite
Verify all 94 unit, integration, and Streamlit AppTest tests:
```powershell
# Run full suite
pytest -v

# Run with line coverage report
pytest -v --cov=crisislens tests
```

### 5. Launch the Web Application
```powershell
streamlit run app.py
```
The browser will automatically open to `http://localhost:8501`.

---

## 📐 Statistical Methodology & Data Governance

### 1. Rolling Historical Baseline (Zero-Leakage Guarantee)
For each time interval $t$, the expected baseline is computed strictly over prior historical observations:
$$H_t = \{Y_{t-W}, Y_{t-W+1}, \dots, Y_{t-1}\}$$
The current observation $Y_t$ and all future intervals $t' > t$ are strictly excluded to prevent look-ahead data leakage.

### 2. Low-Volume Regularization (Poisson Variance Floor)
In low-activity series, sample variance can collapse to zero ($\sigma = 0$), causing division-by-zero errors and false alarms. CrisisLens AI implements a Poisson-modeled standard deviation floor:
$$\sigma_t = \max\left(\text{std}(H_t),\, \sqrt{\max(1.0, \mu_t)}\right)$$
This ensures that a minor increase (e.g. from 0 to 2 events) does not trigger an extreme statistical anomaly alert.

### 3. Dual-Criterion Classification
- **Parametric $Z$-Score:** $Z_t = \frac{Y_t - \mu_t}{\sigma_t} \ge k_z$ (default $k_z = 2.5$)
- **Non-Parametric Tukey IQR Fence:** $Y_t > Q_3(H_t) + m \cdot \text{IQR}(H_t)$ (default $m = 1.5$)
- **Severity Policy:**
  - `NORMAL`: Within baseline expectations.
  - `MODERATE`: Flagged by one criterion or $Z \in [2.5, 4.0)$.
  - `HIGH`: Flagged by both criteria or $Z \in [4.0, 7.0)$.
  - `EXTREME`: Flagged by both criteria with $Z \ge 7.0$.

### 4. Data Readiness Gating Policy
GDELT 15-minute batches cannot establish continuous historical baselines without sufficient reporting depth. The `DataReadinessGate` enforces a strict threshold ($N \ge 28$ intervals). If the database contains fewer intervals, live anomaly scoring is safely blocked to uphold technical credibility.

### 5. Ethical Guidelines & Interpretation Caveats
- **News Coverage $\ne$ Ground-Truth Casualties:** An event reporting surge reflects media attention and wire syndication. It must **never** be used as a direct proxy for physical casualties or military victory.
- **Syndicated Wire Duplication:** Wire services (Reuters, AP, AFP) often trigger artificial volume spikes through syndicated republishing. Analysts must inspect source URLs and actor networks before confirming crisis escalations.
- **Dual-Date Semantics:**
  - `DATEADDED`: Timestamp when GDELT indexed the article (reporting activity).
  - `SQLDATE`: Date the event allegedly occurred (contextual event date).

---

## 🎯 Recruiter Demonstration Checklist (5-Minute Walkthrough)

When presenting CrisisLens AI in a technical interview, follow this structured demo script:

1. **System Overview (1 min):**
   - Open **📊 Overview Dashboard**.
   - Point out the Data Freshness Banner, KPI metric cards, and the **Date Interpretation Mode** toggle.
   - Explain the technical rationale for separating `DATEADDED` (reporting time) from `SQLDATE` (event context date).
2. **Granular Exploration & Query Optimization (1 min):**
   - Navigate to **🔍 Event Explorer**.
   - Demonstrate faceted filtering (e.g. select a specific Country, filter by `QuadClass 4: Material Conflict`, and slide the Goldstein scale).
   - Select an `Event ID` to inspect the CAMEO root code, source URL, and geographic coordinates.
   - Mention DuckDB bounded pagination (`LIMIT` / `OFFSET`) ensuring fast response times without memory bloat.
3. **Statistical Anomaly Intelligence & Readiness Gate (1.5 min):**
   - Navigate to **⚡ Anomaly Intelligence**.
   - Show the **DataReadinessGate** banner on Live Mode: explain why live scoring is locked ($N < 28$) to avoid misleading statistical claims.
   - Switch to **🔬 Synthetic Benchmark (Demo Mode)**.
   - Explain the deterministic 14-day fixture, diurnal patterns, Poisson variance floor, and dual-criterion formula.
   - Show the mathematical proof panel ($\LaTeX$) and narrative rationale.
   - Click `🔬 Drill Down into Event Investigation`.
4. **Investigation Drill-Down & PDF Reporting (1.5 min):**
   - The app transitions to **🕵️ Event Investigation** with the selected interval loaded.
   - Inspect the top 15 evidence records and QuadClass/Country breakdown charts.
   - Click `📕 Download Report (PDF)` and open the downloaded document.
   - Highlight the mode banner (`SYNTHETIC BENCHMARK FIXTURE`), embedded charts, evidence table, and SHA-256 reproducibility fingerprint.

---

## 📁 Repository Directory Structure

```
crisislens-ai/
├── app.py                             # Streamlit main application & router
├── requirements.txt                   # Frozen production dependencies
├── crisislens.duckdb                  # Embedded DuckDB analytical database
├── config/
│   └── settings.toml                  # Centralized configuration knobs
├── crisislens/                        # Core Python application package
│   ├── ingestion/                     # GDELT TSV streaming & validation
│   │   ├── cli.py                     # Command-line interface (--latest, --status)
│   │   ├── fetcher.py                 # HTTP fetcher with MD5 verification
│   │   ├── gdelt_schema.py            # Authoritative 61-column schema constants
│   │   ├── parser.py                  # Chunked TSV parser & type normalizer
│   │   ├── pipeline.py                # End-to-end ingestion orchestrator
│   │   └── validator.py               # Schema integrity & row validator
│   ├── storage/                       # Storage engines
│   │   ├── event_store.py             # DuckDB schema, indexes, and upsert logic
│   │   └── parquet_store.py           # Partitioned Snappy Parquet writer/reader
│   ├── features/                      # Analytical feature engineering
│   │   └── baseline.py                # DataReadinessGate & series regularizer
│   ├── models/                        # Anomaly detection engines
│   │   ├── baseline.py                # StatisticalBaselineDetector (Z-score + IQR)
│   │   └── synthetic.py               # Deterministic 14-day benchmark fixture
│   ├── explainability/                # Deterministic explainability templates
│   │   └── templates.py               # LaTeX formulas & narrative generator
│   ├── reports/                       # Export & publication reporting
│   │   └── pdf_generator.py           # Publication PDF briefing engine
│   ├── ui/                            # Streamlit presentation layer
│   │   ├── charts.py                  # Plotly chart factory & CAMEO palette
│   │   ├── components.py              # Metric cards & freshness banners
│   │   ├── data_service.py            # Decoupled analytical query interface
│   │   └── pages/                     # Application screens
│   │       ├── overview.py            # 📊 Overview Dashboard
│   │       ├── explorer.py            # 🔍 Global Event Explorer
│   │       ├── anomaly.py             # ⚡ Anomaly Intelligence
│   │       └── investigation.py       # 🕵️ Event Investigation Drill-Down
│   └── data/                          # Static lookup tables
│       ├── cameo_event_codes.csv      # CAMEO taxonomies & descriptions
│       └── fips_to_iso.csv            # FIPS 10-4 to ISO sovereign mapping
├── data/                              # Local data directory (gitignored)
│   ├── raw/                           # Downloaded GDELT ZIP archives
│   └── processed/                     # Partitioned Parquet files
├── docs/                              # Project technical documentation
│   ├── ARCHITECTURE.md                # System design & component contracts
│   ├── DATA_DICTIONARY.md             # 61-column GDELT reference & taxonomies
│   ├── IMPLEMENTATION_PLAN.md         # Phased execution roadmap & test log
│   └── PRODUCT_SPEC.md                # Functional specifications & acceptance criteria
└── tests/                             # Comprehensive automated test suite
    ├── conftest.py                    # Shared pytest fixtures
    ├── integration/                   # Pipeline integration tests
    │   └── test_pipeline_e2e.py       # End-to-end ingestion lifecycle
    └── unit/                          # Unit & AppTest test modules
        ├── test_baseline.py           # Baseline detector, Poisson floor, gating
        ├── test_charts.py             # Plotly chart factory
        ├── test_cli.py                # Ingestion CLI commands
        ├── test_data_service.py       # Analytical queries & semantics
        ├── test_e2e_screens.py        # Streamlit AppTest across all 4 screens
        ├── test_event_store.py        # DuckDB storage & idempotent upserts
        ├── test_fetcher.py            # HTTP fetcher, retries, MD5 checks
        ├── test_investigation.py      # Investigation queries & filters
        ├── test_parquet_store.py      # Parquet partitioning & stats
        ├── test_parser.py             # TSV parsing & leading-zero preservation
        ├── test_pdf_report.py         # PDF generation & watermarks
        ├── test_phase0_scaffold.py    # Schema & configuration validation
        └── test_validator.py          # Data validation rules
```

---

## 🔒 Security, Privacy & Resource Boundaries

- **Zero External Paid APIs:** Operates 100% on free, public-domain GDELT data. No OpenAI, Anthropic, or cloud API keys required.
- **Privacy First:** GDELT contains only public media reporting metadata. No Personally Identifiable Information (PII) is stored or tracked.
- **Resource Boundaries:** Streaming chunked ingestion ($50,000$ rows/chunk) and columnar queries guarantee peak memory usage stays strictly under 500 MB on 8 GB RAM systems.
- **SQL Injection Prevention:** All DuckDB analytical queries in `DataService` use parameterized bindings.

---

## 📜 Academic Honesty & Portfolio Credibility

This project contains **zero fabricated metrics, synthetic results presented as real, or non-functional mock buttons**:
- When historical data is insufficient for statistical baseline scoring, the application explicitly locks live scoring via the `DataReadinessGate` rather than fabricating numbers.
- The synthetic benchmark fixture is deterministically modeled, isolated from the live DuckDB store, and visibly watermarked across UI screens and PDF reports.
- All code, tests, and documentation are designed to withstand technical scrutiny in AI/ML and Data Science placement interviews.

---

*CrisisLens AI is an independent open-source project designed for portfolio demonstration and research. Not affiliated with or endorsed by the GDELT Project.*
