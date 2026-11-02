# CrisisLens AI — Architecture

> **Status:** Verified System Architecture (Phases 0–6 Complete & Audited).

---

## 1. System Overview

CrisisLens AI is a **single-machine, batch-refresh Python web application**. It runs entirely on a local Windows laptop, ingests publicly available GDELT Events 2.0 data, stores processed records in a local DuckDB database and Parquet cache, applies statistical and ML-based anomaly detection, and renders results through a multi-page Streamlit UI.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        User's Browser                               │
│                     (localhost:8501)                                 │
└────────────────────────────┬────────────────────────────────────────┘
                             │  HTTP (Streamlit)
┌────────────────────────────▼────────────────────────────────────────┐
│                     Streamlit Application Layer                      │
│  ┌────────────┐ ┌──────────────┐ ┌────────────┐ ┌───────────────┐  │
│  │  Overview  │ │Event Explorer│ │  Anomaly   │ │Investigation  │  │
│  │   Page     │ │    Page      │ │Intelligence│ │  & Report     │  │
│  └─────┬──────┘ └──────┬───────┘ └─────┬──────┘ └──────┬────────┘  │
│        └───────────────┴───────────────┴───────────────┘           │
│                             │ Python function calls                  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│                      crisislens Package                              │
│                                                                      │
│  ┌───────────┐   ┌──────────┐   ┌──────────┐   ┌───────────────┐   │
│  │ ingestion │──▶│ storage  │──▶│ features │──▶│    models     │   │
│  │  module   │   │  module  │   │  module  │   │    module     │   │
│  └───────────┘   └──────────┘   └──────────┘   └───────┬───────┘   │
│                                                         │           │
│                        ┌──────────────┐  ┌─────────────▼────────┐  │
│                        │explainability│  │       reports        │  │
│                        │   module     │  │       module         │  │
│                        └──────────────┘  └──────────────────────┘  │
└────────────────────────────┬────────────────────────────────────────┘
                             │ SQL / Parquet I/O
┌────────────────────────────▼────────────────────────────────────────┐
│                         Local Data Layer                             │
│                                                                      │
│   data/raw/          data/processed/         crisislens.duckdb       │
│   (ZIP files)        (Parquet files)         (metadata + indexes)    │
└─────────────────────────────────────────────────────────────────────┘
                             ▲
                             │ HTTPS fetch (on-demand)
                     GDELT Project Servers
                 (data.gdeltproject.org/gdeltv2/)
```

---

## 2. Module Contracts

### 2.1 `crisislens.ingestion`

**Responsibility:** Download and parse GDELT Events 2.0 files. Produce a clean, typed DataFrame. Emit no side-effects beyond writing to `data/raw/`.

| Function | Signature (design) | Description |
|---|---|---|
| `fetch_masterlist()` | `-> pd.DataFrame` | Parse `lastupdate.txt` or `masterfilelist.txt` |
| `download_file(url, dest)` | `-> Path` | Idempotent download; skips if file exists and MD5 matches |
| `parse_events_file(path)` | `-> pd.DataFrame` | Read TSV, assign all 61 column names, cast types |
| `fetch_range(start, end)` | `-> list[Path]` | Download all 15-min intervals in a date range |

**Key constraints:**
- All 61 GDELT column names must be declared in a single constant list in `gdelt_schema.py`.
- Files without a valid header must be detected and skipped with a logged warning.
- Parsing must use `dtype=str` on first pass, then explicit casting post-parse.
- Chunked reading (`chunksize=50_000`) for files exceeding 100 MB.

---

### 2.2 `crisislens.storage`

**Responsibility:** Persist ingested data efficiently. Serve the analytics layer with typed, indexed results. Abstract all SQL/Parquet details away from the UI.

| Component | Technology | Purpose |
|---|---|---|
| `EventStore` | DuckDB | Metadata catalog, deduplication index, aggregation queries |
| `ParquetStore` | PyArrow Parquet | Bulk row storage; partitioned by `year/month/day` |
| `CacheManager` | In-memory dict + `st.cache_data` | Layer-1 query cache inside Streamlit |

**Schema (primary `events` table in DuckDB):**

```sql
CREATE TABLE events (
    event_id         BIGINT PRIMARY KEY,   -- GLOBALEVENTID
    event_date       DATE    NOT NULL,     -- parsed from SQLDATE
    year             SMALLINT,
    month_year       INTEGER,
    actor1_code      VARCHAR,
    actor1_name      VARCHAR,
    actor1_country   CHAR(3),
    actor2_code      VARCHAR,
    actor2_name      VARCHAR,
    actor2_country   CHAR(3),
    event_code       VARCHAR(4),           -- CAMEO code (preserve leading zeros)
    event_base_code  VARCHAR(3),
    event_root_code  CHAR(2),
    quad_class       TINYINT,             -- 1-4
    goldstein_scale  FLOAT,              -- -10 to +10
    num_mentions     INTEGER,
    num_sources      INTEGER,
    num_articles     INTEGER,
    confidence       SMALLINT,
    action_lat       FLOAT,
    action_lon       FLOAT,
    action_country   CHAR(3),
    action_geo_name  VARCHAR,
    source_url       VARCHAR,
    date_added       BIGINT,
    parquet_path     VARCHAR             -- back-reference to Parquet shard
);
```

---

### 2.3 `crisislens.features`

**Responsibility:** Transform raw event records into ML-ready feature vectors and time-series aggregates.

| Feature | Derivation | Type |
|---|---|---|
| `daily_event_count` | COUNT per `event_date` | integer time series |
| `daily_conflict_ratio` | `quad_class IN (3,4)` / total | float [0,1] |
| `mean_goldstein_daily` | AVG `goldstein_scale` by date | float |
| `country_event_count` | COUNT per `(event_date, action_country)` | integer |
| `rolling_7d_mean` | 7-day rolling average of `daily_event_count` | float |
| `rolling_7d_std` | 7-day rolling std of `daily_event_count` | float |
| `z_score` | `(value - rolling_mean) / rolling_std` | float |

All derived features must be recomputable deterministically from the raw events table.

---

### 2.4 `crisislens.models`

**Responsibility:** Detect anomalies. Return a score and a label for each time-series point. Enforce a progression discipline: fit simpler models first; add complexity only when justified.

#### Anomaly Detection Progression

```
Level 1 (Baseline — always active):
  → 7-day rolling z-score threshold (|z| > 2.5)
  → IQR fence on 30-day window (Q3 + 1.5×IQR)
  → Rule: flag if EITHER condition is met

Level 2 (Intermediate — optional, requires ≥ 60 days data):
  → STL seasonal decomposition + residual z-score
  → Catches day-of-week and recurring patterns that fool Level 1

Level 3 (Advanced — optional, requires ≥ 90 days data):
  → Isolation Forest on multi-dimensional daily feature vector
  → Hyperparameters: contamination=0.05, n_estimators=100, random_state=42

Active level is recorded in the model artifact metadata and displayed in the UI.
```

**Model artifact format:** Each trained model is saved as `models/<name>_<YYYYMMDD>.pkl` with a sidecar `models/<name>_<YYYYMMDD>_meta.json` containing:

```json
{
  "model_name": "isolation_forest",
  "level": 3,
  "trained_on": "2026-10-29",
  "training_window_days": 90,
  "n_training_samples": 90,
  "hyperparameters": { "contamination": 0.05, "n_estimators": 100, "random_state": 42 },
  "threshold_used": null,
  "performance_note": "No ground-truth labels available; contamination is a design assumption."
}
```

---

### 2.5 `crisislens.explainability`

**Responsibility:** Translate model output into plain English suitable for a non-technical audience and for interview explanation.

| Output | Source | Format |
|---|---|---|
| Anomaly reason string | z-score value + IQR fence | "Event count was 3.2 standard deviations above the 7-day average" |
| Baseline comparison | rolling stats | "Normal range for this period: 120–180 events/day. Observed: 347 events" |
| Top contributing actors | value-count on anomaly window | "Most frequent actor: USA (87 events)" |
| Top contributing CAMEO codes | value-count on anomaly window | "Top event type: CAMEO 14 — Protest (42 events)" |
| Feature importance (Level 3) | IF mean anomaly score per feature | "Most influential features: conflict_ratio (0.41), goldstein_scale (0.29)" |

All explanation text must be **templated strings**, not LLM output, to ensure reproducibility and avoid hallucination risk.

---

### 2.6 `crisislens.reports`

**Responsibility:** Generate exportable CSV and PDF summaries from filtered query results.

- CSV export: raw filtered event rows + derived features
- PDF export: auto-generated report containing date range, filter criteria, summary statistics, anomaly table, top countries chart (as embedded PNG), and methodology section
- Both exports must include a reproducibility footer: data source URL, config hash, and generation timestamp

---

## 3. Data Flow

```
GDELT Servers
    │
    │ HTTPS (requests)
    ▼
data/raw/*.export.CSV.zip          (retained for 30 days, then purged)
    │
    │ parse_events_file()  →  validate schema → cast types → drop nulls
    ▼
data/processed/year=YYYY/month=MM/day=DD/*.parquet    (columnar, compressed)
    │
    │ DuckDB COPY / INSERT
    ▼
crisislens.duckdb  events table    (deduplicated by event_id)
    │
    │ feature engineering  (run at query time, cached in st.cache_data)
    ▼
Feature DataFrame (daily aggregates, rolling stats)
    │
    │ anomaly model  (loaded from models/*.pkl or fit on-the-fly)
    ▼
Anomaly Score Series  →  Flagged events list
    │
    │ explainability layer
    ▼
Human-readable explanation dict
    │
    │ Streamlit UI components
    ▼
Charts + Maps + Tables + Report Download
```

---

## 4. Configuration (`config/settings.toml`)

All runtime knobs are centralised. No magic numbers in application code.

```toml
[data]
rolling_window_days = 30        # How many days of events to keep in memory
max_raw_file_age_days = 30      # Purge raw ZIPs older than this
chunk_size = 50_000             # Rows per pandas chunk during ingestion
parquet_compression = "snappy"  # snappy | gzip | zstd

[models]
default_level = 1               # 1 = z-score; 2 = STL; 3 = Isolation Forest
zscore_threshold = 2.5
iqr_multiplier = 1.5
if_contamination = 0.05
if_n_estimators = 100
random_seed = 42                # Fixed for reproducibility

[ui]
map_default_zoom = 2
max_table_rows = 5_000          # Cap to prevent browser slowdown
date_format = "%Y-%m-%d"

[export]
csv_encoding = "utf-8-sig"      # Excel-compatible BOM
pdf_page_size = "A4"
```

---

## 5. Performance Constraints

| Constraint | Target | Mitigation if Exceeded |
|---|---|---|
| App cold-start time | < 10 seconds | Parquet pre-aggregated summary cache |
| Dashboard page render | < 3 seconds | `st.cache_data` with 10-min TTL |
| 30-day ingestion | < 5 minutes | Parallelise with `concurrent.futures.ThreadPoolExecutor` (2 workers) |
| Peak RAM usage | < 1.5 GB | Chunked I/O; DuckDB query pushdown; Parquet column pruning |
| DuckDB query (30 days) | < 2 seconds | Date-partitioned Parquet + DuckDB columnar scan |

---

## 6. Failure Modes and Mitigations

| Failure | Detection | Mitigation |
|---|---|---|
| GDELT server unavailable | HTTP timeout / non-200 response | Retry with exponential back-off (3 attempts); show stale-data warning in UI |
| Corrupted ZIP file | `zipfile.BadZipFile` exception | Skip file; log error; do not halt pipeline |
| Column count mismatch | `len(df.columns) != 61` check | Log warning; drop file; alert in UI |
| Insufficient data for Level 2/3 model | `len(daily_series) < threshold` | Gracefully fall back to Level 1; display informational banner |
| DuckDB file lock (two Streamlit instances) | `duckdb.IOException` | Open DB in read-only mode in UI; write-only in ingestion process |

---

## 7. Technology Decision Log

| Decision | Chosen | Rejected | Rationale |
|---|---|---|---|
| Database | DuckDB + Parquet | SQLite, PostgreSQL | DuckDB is columnar, embeds with zero config, and can scan Parquet natively |
| Map library | Folium (Leaflet.js) | Plotly Scattergeo, Deck.gl | Folium renders in Streamlit via `st.components.html`; no API key; richer tooltip control |
| Anomaly model | z-score → IQR → Isolation Forest | LSTM, Prophet, ARIMA | Progression strategy: explainable baselines first; complex models only when data allows |
| PDF export | fpdf2 | WeasyPrint, reportlab | fpdf2 is pure Python, no system dependencies, easy to install on Windows |
| Config format | TOML | YAML, JSON, .env | TOML is Python-native (stdlib `tomllib` since 3.11), human-readable, typed |

---

## 8. Security and Privacy

- No user authentication required (local-only deployment).
- No PII is collected or stored. GDELT data contains only news-derived public events.
- Source URLs are stored as-is; clicking them opens the original news article.
- No telemetry or analytics tracking.

---

## 9. Architectural Decisions & Resolution Log

| # | Question / Decision | Resolution | Technical Details |
|---|---|---|---|
| Q1 | Historical baseline window configuration | Resolved | Implemented configurable rolling lookback window ($W \in [6, 72]$ hours, default 24h) with $W_{\min} \in [4, 24]$. Gated by `DataReadinessGate` enforcing $N \ge 28$ intervals before live scoring unlocks. |
| Q2 | GDELT Mentions stream integration | Resolved | Embedded mentions attributes (`NumMentions`, `NumSources`, `NumArticles`) directly from GDELT Events 2.0 schema columns 31–33. Defer separate multi-gigabyte Mentions TSV stream. |
| Q3 | DuckDB vs Parquet query roles | Resolved | DuckDB serves as the primary analytical store (`crisislens.duckdb` with index on `DATEADDED` and `event_id`). Snappy Parquet serves as partitioned cold archive (`year=YYYY/month=MM/`). |
| Q4 | Country-code mapping (FIPS 10-4 to ISO 3166) | Resolved | Shipped static `crisislens/data/fips_to_iso.csv` cross-reference table loaded into memory cache at `DataService` startup. |
| Q5 | PDF generation library | Resolved | Selected `fpdf2` (v2.8.9) with `matplotlib` for headless figure generation and `DejaVuSans` TrueType Unicode fonts. Bounded RAM (< 15 MB) and fast execution (< 0.5s). |

---

*Verified and audited: Phase 6 verification, November 2026*
