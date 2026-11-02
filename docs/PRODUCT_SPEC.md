# CrisisLens AI — Product Specification

> **Status:** Verified Product Specification (Phases 0–6 Complete & Audited).

---

## 1. Product Goals

| Goal | Measurable Criterion |
|---|---|
| Useful | A user can explore 30 days of global events, identify anomalies, and read a plain-English explanation in under 5 minutes |
| Visually polished | All charts use consistent colour palette; no default Streamlit grey; maps show country fill and tooltips |
| Technically credible | Every statistic and model output is traceable to raw GDELT rows |
| Explainable | Every anomaly score is accompanied by the contributing features and their values |
| Reproducible | Given the same date range and settings.toml, two independent runs produce identical output |

---

## 2. Users and Use Cases

### 2.1 Primary Users

| Persona | Goal | CrisisLens Feature |
|---|---|---|
| Student researcher | Explore global conflict patterns for a paper | Event Explorer + Research Export |
| DS/ML intern candidate | Demonstrate a complete real-data ML pipeline | All screens |
| Journalism student | Identify unusual spikes in event reporting | Anomaly Intelligence |
| Policy analyst | Drill into a specific country's event profile | Event Explorer + Investigation |

### 2.2 Non-Users (Out of Scope)

- Organisations requiring real-time streaming (< 15-min latency)
- Users needing proprietary restricted data
- Automated production monitoring systems

---

## 3. Screen Specifications

---

### Screen 1: Overview

**Purpose:** Provide an at-a-glance health check of global event activity over the selected date range.

#### Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  [Date Range Picker]   [Country Filter]   [Refresh Data Button]      │
├──────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌────────────┐  ┌───────────────────┐  │
│  │ Total    │  │ Avg/Day  │  │ Anomaly    │  │ Top Conflict      │  │
│  │ Events   │  │          │  │ Days Found │  │ Country           │  │
│  └──────────┘  └──────────┘  └────────────┘  └───────────────────┘  │
│  ┌──────────────────────────────────┐  ┌──────────────────────────┐  │
│  │ Event Count Trend (line chart)   │  │ World Heat Map           │  │
│  │ with anomaly markers             │  │ (event density by country│  │
│  └──────────────────────────────────┘  └──────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ Recent Events Table (last 25 events, source URL column)          │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

#### Acceptance Criteria

| ID | Criterion |
|---|---|
| OV-01 | Total events metric shows an integer count matching the DuckDB query result |
| OV-02 | Trend chart renders in ≤ 3 seconds for 30-day window |
| OV-03 | Anomaly days count matches the number of flagged dates in the Anomaly Intelligence screen |
| OV-04 | Heat map renders all countries with at least 1 event in the selected window |
| OV-05 | Recent events table shows `event_date`, `actor1_name`, `actor2_name`, `event_code`, `action_geo_name`, `source_url` |
| OV-06 | Source URL cells are clickable hyperlinks |
| OV-07 | All metrics update when the date range or country filter changes |

#### Data Requirements

- `daily_event_count` time series (from DuckDB aggregate)
- `country_event_count` (from DuckDB aggregate, for heat map)
- Latest 25 raw event rows (from DuckDB, ordered by `date_added DESC`)
- Anomaly flags (from models module)

---

### Screen 2: Event Explorer

**Purpose:** Allow full-text search and multi-dimensional filtering of event records.

#### Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  Filters:                                                           │
│  [Date Range] [Country] [CAMEO Root Code] [QuadClass] [Text Search] │
│  [Min Goldstein] ────────────────────────────── [Max Goldstein]     │
│  [Min Mentions] [Apply Filters]  [Reset]                            │
├─────────────────────────────────────────────────────────────────────┤
│  Results: 1,234 events found   [Download CSV]                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ Date | Actor 1 | Actor 2 | CAMEO | QuadClass | Goldstein |      ││
│  │ Geo  | Mentions | Source URL                                    ││
│  │ ─────────────────────────────────────────────────────────────  ││
│  │ (sortable, paginated, max 5,000 rows)                          ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

#### Acceptance Criteria

| ID | Criterion |
|---|---|
| EE-01 | Filters apply within 2 seconds for a 30-day dataset |
| EE-02 | CAMEO root-code filter shows human-readable labels alongside codes |
| EE-03 | Text search filters on `actor1_name`, `actor2_name`, and `action_geo_name` simultaneously |
| EE-04 | Result count updates when any filter changes |
| EE-05 | CSV download contains all filtered columns, not just displayed ones |
| EE-06 | Table is capped at 5,000 rows with a visible warning when exceeded |
| EE-07 | Goldstein scale slider has range −10 to +10 with 0.5 step |
| EE-08 | Empty result set shows "No events match your filters" message, not an error |

---

### Screen 3: Anomaly Intelligence

**Purpose:** Surface statistically unusual days in event activity and explain why they are flagged.

#### Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  [Date Range] [Country/Global] [Detection Level: 1 | 2 | 3]        │
│  [Sensitivity Slider: z-score threshold 1.5–3.5]                   │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Anomaly Score Timeline                                        │   │
│  │ (dual-axis: event count + z-score; anomaly days highlighted) │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Anomaly Map: flagged events plotted on world map             │   │
│  │ (circle radius = anomaly severity)                           │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Flagged Anomaly Table                                        │   │
│  │ Date | Event Count | z-score | IQR Flag | Model Level |     │   │
│  │ [Investigate →] link per row                                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ℹ️  Model: Level 1 (z-score + IQR baseline) | Trained on: N/A     │
└─────────────────────────────────────────────────────────────────────┘
```

#### Acceptance Criteria

| ID | Criterion |
|---|---|
| AN-01 | Timeline chart shows raw event count as a bar series and z-score as a line series |
| AN-02 | Anomaly days are marked with a red dot or vertical highlight band |
| AN-03 | Changing sensitivity slider updates anomaly flags without page reload |
| AN-04 | Anomaly table shows at minimum: date, event count, z-score, IQR flag, detection level |
| AN-05 | "Investigate →" link navigates to Screen 4 pre-filtered to that date |
| AN-06 | When < 14 days of data exist, display a warning that baseline reliability is limited |
| AN-07 | Model metadata footer shows which level is active and why |
| AN-08 | Level 3 (Isolation Forest) is shown only when ≥ 90 days data is available |
| AN-09 | No anomaly days claimed if z-score calculation has < 7 data points |

---

### Screen 4: Event Investigation

**Purpose:** Deep-dive into a single flagged anomaly date. Provide supporting evidence, source articles, and a transparent, non-ML plain-English explanation.

#### Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  Investigating: 2026-10-15  [← Back to Anomaly Intelligence]        │
├─────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  📊 Why is this date flagged?                                 │  │
│  │  "Event count (347) was 3.2 standard deviations above the     │  │
│  │   7-day average (128). Normal range: 85 – 171. This exceeds  │  │
│  │   the IQR upper fence of 201."                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────┐  ┌──────────────────────────────────┐ │
│  │ Top Actors               │  │ Top CAMEO Event Types            │ │
│  │ (bar chart, top 10)      │  │ (horizontal bar, top 10 codes)   │ │
│  └──────────────────────────┘  └──────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Supporting Event Records (all events on this date)           │  │
│  │  Date | Actor 1 | Actor 2 | CAMEO | Goldstein | Source URL   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Feature Contribution (Level 3 only)                          │  │
│  │  Bar chart: which features pushed this day's IF score highest │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

#### Acceptance Criteria

| ID | Criterion |
|---|---|
| IV-01 | Plain-English explanation uses actual computed values (not placeholders) |
| IV-02 | Top Actors chart ranks by event count on that specific date |
| IV-03 | Top CAMEO chart shows human-readable category labels, not raw codes |
| IV-04 | Supporting event table is filterable by actor and CAMEO code within the page |
| IV-05 | Source URLs open in a new browser tab |
| IV-06 | Feature Contribution section is hidden (with a note) when Level 1 or 2 is active |
| IV-07 | All values in the explanation panel are traceable to the DuckDB query shown in expandable section |
| IV-08 | Page is reachable via direct URL parameter (e.g., `?page=investigate&date=2026-10-15`) |

---

### Screen 5: Research & Export

**Purpose:** Export filtered data and generate a reproducible research summary report.

#### Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  Export Configuration                                               │
│  [Date Range] [Country] [CAMEO Filter] [Include Anomaly Scores Y/N] │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Data Summary Preview                                        │   │
│  │  Rows: 4,312  |  Date range: 2026-10-01 to 2026-10-29       │   │
│  │  Anomaly days in range: 3                                    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  [⬇ Download Filtered CSV]   [⬇ Generate PDF Report]               │
├─────────────────────────────────────────────────────────────────────┤
│  Methodology Note (expandable)                                      │
│  Data source: GDELT Events 2.0                                      │
│  Ingestion date: 2026-10-29                                         │
│  Detection method: Level 1 (z-score threshold = 2.5)               │
│  Config hash: sha256:...                                            │
│  Reproducibility: Re-run with same config and date range           │
└─────────────────────────────────────────────────────────────────────┘
```

#### Acceptance Criteria

| ID | Criterion |
|---|---|
| RE-01 | CSV export downloads within 5 seconds for up to 30 days of data |
| RE-02 | CSV uses UTF-8-BOM encoding for Excel compatibility |
| RE-03 | PDF report contains: title, date range, summary stats table, top-10 countries chart, anomaly table, methodology section |
| RE-04 | PDF is generated without internet access after initial GDELT data fetch |
| RE-05 | Methodology note shows exact config values (thresholds, window size, detection level) |
| RE-06 | Config hash is a SHA-256 of the serialised `settings.toml` content |
| RE-07 | Both exports reflect the same filter state as the Data Summary Preview |

---

## 4. Non-Functional Requirements

| Requirement | Target |
|---|---|
| First-load time (cached data) | < 10 seconds |
| Page navigation time | < 2 seconds |
| Memory ceiling | < 1.5 GB RSS |
| Works offline | Yes — after initial data fetch |
| No external API key required | Yes |
| Python version | 3.11+ |
| Supported OS | Windows 10/11 (primary), macOS, Linux |

---

## 5. Completed Implementation & Roadmap Status

### Completed MVP & Production Features (Phases 0–6)

- [x] GDELT Events 2.0 streaming ingestion with MD5 verification and retry policy
- [x] DuckDB columnar analytical database (`crisislens.duckdb`) with idempotent upserts
- [x] Partitioned Snappy Parquet data lake archive (`data/processed/year=YYYY/month=MM/`)
- [x] Overview Dashboard: executive KPIs, Date Semantics toggle, QuadClass donuts, Top Geographies, live ingestion feed
- [x] Global Event Explorer: full-text search, faceted filtering, bounded pagination, single-record inspector
- [x] Level 1 Statistical Anomaly Engine: rolling Z-score + Tukey IQR with Poisson dispersion floor
- [x] DataReadinessGate: historical sufficiency auditor preventing false alarms ($N \ge 28$)
- [x] Deterministic 14-day synthetic benchmark fixture (336 hourly observations, seed=42)
- [x] Event Investigation Drill-Down: interval analysis, actor networks, and underlying evidence table
- [x] Deterministic Explainability Engine with LaTeX formulations and narrative rationales
- [x] Excel-compatible CSV export (`utf-8-sig`) and Markdown investigation briefings
- [x] Publication-quality in-memory PDF reporting engine (`fpdf2` + `matplotlib` + DejaVu Unicode fonts) with mode watermarking
- [x] Comprehensive test suite (94 tests, 80% line coverage, zero AppTest headless exceptions)

### Phase 7 (Optional / Future Advanced ML)

- [ ] Level 2 anomaly detection (seasonal STL decomposition)
- [ ] Level 3 anomaly detection (multivariate Isolation Forest)
- [ ] Actor network graph visualization (NetworkX + Plotly)
- [ ] Historical year-over-year baseline comparison

### Out of Scope (Never)

- Real-time sub-second streaming
- User authentication or multi-tenant database
- Paid external AI/LLM APIs
- Fabricated or unwatermarked benchmark data presented as real live events

---

## 6. Assumptions

1. GDELT Events 2.0 files are consistently available at `data.gdeltproject.org`. Brief outages are handled by retry logic.
2. The user's machine has a working Python 3.11 environment with pip.
3. Network bandwidth is sufficient to download ~150 MB per 30-day window of Events data.
4. The GDELT schema has been stable at 61 columns since 2015 and will not change mid-project.
5. No ground-truth labels exist for GDELT anomalies; anomaly detection is unsupervised.

---

*Last updated: Design phase, 2026-10-29*
