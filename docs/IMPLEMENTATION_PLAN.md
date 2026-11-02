# CrisisLens AI — Implementation Plan

> **Status:** Design-phase document. No code exists yet. This plan requires approval before implementation begins.

---

## 1. Implementation Philosophy

1. **Work in testable vertical slices.** Each phase delivers a runnable, demonstrable increment.
2. **Earn complexity.** No ML model is added until the simpler baseline is working and verified.
3. **No fabricated data or metrics.** Every chart and number must be reproducible from real GDELT data.
4. **Config over magic numbers.** Every tunable parameter lives in `config/settings.toml`.
5. **Test as you build.** Write unit tests alongside each module, not after.

---

## 2. Phase Overview

| Phase | Name | Deliverable | Status |
|---|---|---|---|
| 0 | Scaffold | Project structure, config, schema constants | **Completed** (7 tests) |
| 1 | Data Pipeline | GDELT ingestion + DuckDB + Parquet storage | **Completed** (34 tests) |
| 2 | Core UI | Overview + Event Explorer screens | **Completed** (46 tests) |
| 3 | Anomaly Baseline | Level 1 detection + Statistical Audit | **Completed** (74 tests) |
| 4 | Investigation | Event Investigation drill-down + Export | **Completed** (83 tests) |
| 5 | PDF Reporting | Publication-quality PDF reports + Watermark + Reproducibility | **Completed** (89 tests) |
| 6 | Polish & Verification | Full test suite, multi-page AppTest, documentation, UI polish | **Completed** (94 tests, 80% cov) |
| 7 | (Optional) Level 2/3 | STL decomposition + Isolation Forest | Deferred (Future) |

**Total MVP estimate:** ~17–25 coding days (evenings + weekends).

---

## 3. Phase 0 — Scaffold

### Goal
Establish the repository structure, development environment specification, and shared constants. No functional code yet.

### Tasks

| Task | File(s) | Notes |
|---|---|---|
| Create directory tree | All directories | Match layout in README.md exactly |
| Write `requirements.txt` | `requirements.txt` | Pin all versions |
| Write `config/settings.toml` | `config/settings.toml` | All default values defined |
| Write GDELT column name constants | `crisislens/ingestion/gdelt_schema.py` | 61-element list, authoritative source of truth |
| Write CAMEO lookup CSVs | `crisislens/data/cameo_event_codes.csv`, `fips_to_iso.csv` | Static reference files |
| Write `conftest.py` | `tests/conftest.py` | Shared pytest fixtures |
| Set up `.gitignore` | `.gitignore` | Exclude `data/`, `models/`, `.venv/`, `*.duckdb` |

### Acceptance Criteria
- `pytest tests/` runs with 0 collected test errors (empty test suite is OK at Phase 0).
- All directories exist as specified in README.
- `python -c "import tomllib; print('OK')"` succeeds.

---

## 4. Phase 1 — Data Pipeline

### Goal
Reliably download, parse, store, and deduplicate 7–30 days of GDELT Events 2.0 data on the target hardware.

### Tasks

| Task | Module | Key Design Points |
|---|---|---|
| `fetch_masterlist()` | `ingestion/fetcher.py` | Parse `lastupdate.txt`; return DataFrame of (url, size, md5) |
| `download_file()` | `ingestion/fetcher.py` | Idempotent; skip if MD5 matches; retry on failure |
| `fetch_range()` | `ingestion/fetcher.py` | Accepts `start_date`, `end_date`; calls `download_file` per interval |
| `parse_events_file()` | `ingestion/parser.py` | 61-column TSV; `dtype=str`; validate column count; type cast |
| `validate_dataframe()` | `ingestion/validator.py` | Check column count = 61; check GLOBALEVENTID not null; log issues |
| `EventStore` class | `storage/event_store.py` | DuckDB wrapper; `upsert()`, `query()`, `get_daily_counts()` |
| `ParquetStore` class | `storage/parquet_store.py` | Write/read partitioned Parquet; column pruning on read |
| `ingest_pipeline()` | `ingestion/pipeline.py` | Orchestrates fetch → parse → validate → store; writes `ingestion_log` |
| CLI entry point | `__main__.py` | `python -m crisislens.ingestion.fetch --days 7` |

### Unit Tests

| Test | File | What it checks |
|---|---|---|
| `test_parse_events_file` | `tests/unit/test_parser.py` | Fixture TSV → correct 61-column DataFrame, correct types |
| `test_validate_wrong_columns` | `tests/unit/test_validator.py` | File with 60 columns raises `SchemaError` |
| `test_goldstein_null_handling` | `tests/unit/test_parser.py` | Empty GoldsteinScale → NaN float, not crash |
| `test_event_code_preserves_zeros` | `tests/unit/test_parser.py` | `"010"` stays `"010"`, not integer `10` |
| `test_upsert_deduplication` | `tests/unit/test_event_store.py` | Inserting same `event_id` twice → 1 row in DB |

### Integration Tests

| Test | File | What it checks |
|---|---|---|
| `test_round_trip_parquet` | `tests/integration/test_storage.py` | Write 1000 rows → read back → assert equal |
| `test_ingestion_log_populated` | `tests/integration/test_pipeline.py` | After pipeline run, `ingestion_log` has 1 row |

### Acceptance Criteria
- Parse 1 real GDELT 15-minute Events file without errors.
- Store and re-query 7 days of events; row counts match between Parquet and DuckDB.
- Memory usage during parse does not exceed 500 MB for a single daily file.
- Pipeline completes 7-day ingestion in under 3 minutes on target hardware.

---

## 5. Phase 2 — Core UI

### Goal
Build the Overview and Event Explorer screens with real data. No anomaly detection yet.

### Tasks

| Task | Module | Notes |
|---|---|---|
| `app.py` entry point | `app.py` | Multi-page Streamlit navigation |
| Colour theme | `crisislens/ui/theme.py` | Consistent Plotly colour palette; dark/light aware |
| Metric cards component | `crisislens/ui/components.py` | `render_metric_card(label, value, delta)` |
| Daily trend chart | `crisislens/ui/charts.py` | Plotly line + bar combo; hover shows z-score |
| World heat map | `crisislens/ui/maps.py` | Folium choropleth; country fill by event count |
| Overview page | `crisislens/ui/pages/overview.py` | Assemble layout from components |
| Explorer filters | `crisislens/ui/pages/explorer.py` | Streamlit widgets → DuckDB WHERE clause |
| Explorer table | `crisislens/ui/pages/explorer.py` | Paginated `st.dataframe` with column config |
| CSV download button | `crisislens/ui/pages/explorer.py` | `st.download_button` with CSV bytes |

### Acceptance Criteria
- Overview page loads with real data in < 10 seconds on cold start.
- Heat map renders without crashing for 30-day window.
- All 7 acceptance criteria for OV screen (OV-01 to OV-07) pass.
- All 8 acceptance criteria for EE screen (EE-01 to EE-08) pass.

---

## 6. Phase 3 — Anomaly Baseline (Level 1)

### Goal
Implement the rolling z-score + IQR baseline detector. Surface results in the Anomaly Intelligence screen.

### Tasks

| Task | Module | Notes |
|---|---|---|
| `compute_rolling_stats()` | `features/time_series.py` | 7-day rolling mean + std; min_periods=7 |
| `compute_iqr_fence()` | `features/time_series.py` | 30-day rolling IQR fence; min_periods=30 |
| `compute_z_scores()` | `features/time_series.py` | Element-wise z-score; NaN for first 6 days |
| `BaselineDetector` class | `models/baseline.py` | `fit(series)`, `predict(series)` → anomaly flags |
| `AnomalyRecord` dataclass | `models/base.py` | `date`, `score`, `is_anomaly`, `level`, `reason_code` |
| `explain_anomaly()` | `explainability/explainer.py` | Template-based plain-English generation |
| Anomaly timeline chart | `ui/charts.py` | Dual-axis Plotly; anomaly markers |
| Anomaly map | `ui/maps.py` | Folium scatter; circle radius = severity |
| Anomaly Intelligence page | `ui/pages/anomaly.py` | Full layout; sensitivity slider |

### Unit Tests

| Test | What it checks |
|---|---|
| `test_zscore_known_spike` | Series with artificial spike at day 10 → `is_anomaly[10] == True` |
| `test_zscore_insufficient_data` | Series < 7 points → all z-scores = NaN; no anomalies flagged |
| `test_iqr_fence_skewed` | Right-skewed series: IQR fence catches outlier that z-score misses |
| `test_explanation_template` | `explain_anomaly()` returns string containing actual numeric values |
| `test_no_false_positives_uniform` | Perfectly uniform series → 0 anomalies flagged |

### Acceptance Criteria
- All 9 Anomaly Intelligence acceptance criteria (AN-01 to AN-09) pass.
- No anomaly is flagged when fewer than 7 data points exist.
- Explanation strings contain real computed values (no hardcoded placeholders).
- "Investigate →" link correctly routes to Investigation page with pre-filled date.

---

## 7. Phase 4 — Event Investigation

### Goal
Build the deep-dive investigation screen. Translate anomaly scores into human-readable explanations backed by supporting event records.

### Tasks

| Task | Module | Notes |
|---|---|---|
| `get_events_on_date()` | `storage/event_store.py` | All raw events for a specific date |
| `top_actors_on_date()` | `features/aggregation.py` | value_counts on actor1_name |
| `top_cameo_on_date()` | `features/aggregation.py` | value_counts on event_root_code → join labels |
| `generate_explanation()` | `explainability/explainer.py` | Full explanation dict; all fields populated |
| Investigation page | `ui/pages/investigation.py` | Full layout per PRODUCT_SPEC §3 Screen 4 |
| DuckDB trace expander | `ui/pages/investigation.py` | Expandable section showing SQL query used |
| URL routing | `app.py` | `st.query_params` to route `?page=investigate&date=X` |

### Acceptance Criteria
- All 8 Investigation acceptance criteria (IV-01 to IV-08) pass.
- Page loads in < 3 seconds for a single date with up to 5,000 events.
- Plain-English explanation contains actual computed values.
- DuckDB SQL expander shows the actual query string used.

---

## 8. Phase 5 — Export & Research Screen

### Goal
Enable CSV and PDF export. Build the Research & Export screen.

### Tasks

| Task | Module | Notes |
|---|---|---|
| `export_csv()` | `reports/csv_export.py` | Apply filters; UTF-8-BOM; streaming for large files |
| `generate_pdf()` | `reports/pdf_export.py` | fpdf2-based; includes stats, chart PNG, methodology |
| `render_methodology_note()` | `reports/methodology.py` | Config hash, detection level, thresholds |
| Research page | `ui/pages/research.py` | Full layout per PRODUCT_SPEC §3 Screen 5 |

### Acceptance Criteria
- All 7 Research & Export acceptance criteria (RE-01 to RE-07) pass.
- PDF renders without internet access after initial data fetch.
- CSV file is importable by Microsoft Excel without encoding errors.

---

## 9. Phase 6 — Polish & Tests

### Goal
Reach a portfolio-presentable, fully documented, tested state.

### Tasks

| Task | Notes |
|---|---|
| Complete unit test suite | Achieve ≥ 80% line coverage on `crisislens/` package (exclude UI pages) |
| Integration test: full pipeline run | Fetch 7 days → ingest → detect → export → assert CSV row count |
| UI test: smoke test | `streamlit run app.py` with `--headless` does not crash within 30 seconds |
| README.md: Quick Start section | Verify all commands work on a clean environment |
| Finalise `docs/` | Ensure all four docs are up to date and internally consistent |
| requirements.txt version pins | Freeze all dependency versions after successful full run |
| Add `.github/` or `CONTRIBUTING.md` | Minimal contribution guide for portfolio credibility |

### Acceptance Criteria
- `pytest tests/ --tb=short` exits with code 0.
- Test coverage report shows ≥ 80% for core modules.
- App runs from a fresh `pip install -r requirements.txt` on a clean virtualenv.

---

## 10. Phase 7 (Optional) — Advanced Anomaly Detection

### Prerequisite
- ≥ 60 days of ingested data for Level 2.
- ≥ 90 days of ingested data for Level 3.

### Tasks

| Task | Module | Notes |
|---|---|---|
| STL decomposition | `models/stl_detector.py` | `statsmodels.tsa.seasonal.STL`; residual z-score |
| `Level2Detector` class | `models/stl_detector.py` | Extends `BaselineDetector` interface |
| Isolation Forest | `models/isolation_forest.py` | `sklearn.ensemble.IsolationForest`; `random_state=42` |
| `Level3Detector` class | `models/isolation_forest.py` | Multi-feature input: 5 daily features |
| Feature importance (IF) | `explainability/if_explainer.py` | Mean anomaly score per feature across training set |
| Model serialisation | `models/model_registry.py` | Save/load `.pkl` + `.json` sidecar |
| UI: Level selector | `ui/pages/anomaly.py` | Disable Level 2/3 buttons when data insufficient |

### Acceptance Criteria
- Level 2 flags at least 1 anomaly in 60 days of real data (indicative, not a guarantee).
- Isolation Forest `contamination=0.05` flags approximately 5% of days as anomalous.
- Feature importance chart displays 5 bars with non-zero values.
- Model artifacts are written to `models/` and reloaded correctly on restart.

---

## 11. Required `requirements.txt` (Proposed Versions)

```
# Core data
pandas>=2.1.0
numpy>=1.26.0
pyarrow>=15.0.0
duckdb>=0.10.0

# ML & stats
scikit-learn>=1.4.0
scipy>=1.12.0
statsmodels>=0.14.0  # Phase 7 only

# Visualisation
plotly>=5.20.0
folium>=0.16.0
streamlit>=1.34.0

# Reports
fpdf2>=2.7.9

# Utilities
requests>=2.31.0
tomllib  # stdlib in Python 3.11+; no install needed
```

> **Note:** Do not install these packages until implementation begins. This list is a design specification.

---

## 12. Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| GDELT server unavailability | Low | High | Retry logic; offline mode with cached data; document fallback |
| 61-column schema changes | Very low | High | Validate column count at parse time; alert loudly on mismatch |
| RAM exhaustion during ingestion | Medium | High | Chunked reading (50,000 rows); Parquet column pruning; 30-day cap |
| DuckDB write lock (two processes) | Medium | Medium | Open DuckDB in read-only mode in UI; write only in ingestion process |
| FIPS→ISO code mapping errors | Medium | Medium | Ship static lookup CSV; log unmapped codes; show "Unknown" gracefully |
| STL divergence on short series | Medium | Medium | Require ≥ 60 days; fall back to Level 1 with UI warning |
| PDF generation font issues on Windows | Low | Low | Bundle a free TrueType font; test on target machine in Phase 5 |
| Streamlit state management complexity | Medium | Medium | Minimise `st.session_state` usage; prefer URL query params for navigation |

---

## 13. Interview Talking Points (Prepared Per Phase)

| Question | Honest Answer |
|---|---|
| "How big is your dataset?" | "30 days of GDELT Events 2.0 produces roughly 150 MB of raw TSV — about 500,000 event rows. I process it in chunks to stay within 8 GB RAM." |
| "Why z-score before Isolation Forest?" | "Z-score is interpretable and falsifiable. I can explain every flagged day to a non-technical audience. IF is more powerful but harder to explain, so I validate the baseline first." |
| "How do you know your anomaly detector is working?" | "There's no ground truth for GDELT, so I validate qualitatively: I check that flagged dates correspond to known major news events, and I test the algorithm on synthetic series where I know the answer." |
| "Why DuckDB instead of SQLite?" | "DuckDB is columnar and can scan Parquet natively. For analytical queries like GROUP BY date or country across millions of rows, it's 10–50× faster than SQLite with zero configuration." |
| "How reproducible is this?" | "Everything depends on `settings.toml`, a fixed random seed (42), and the GDELT data files for a given date range. Given those three inputs, the output is deterministic." |
| "What's your model's accuracy?" | "There are no ground-truth labels for this problem, so accuracy is undefined. I instead report the contamination assumption (5%), validate flagged dates qualitatively, and display the explanation transparently in the UI." |

---

*Last updated: Design phase, 2026-10-29*
