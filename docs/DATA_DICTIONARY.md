# CrisisLens AI — Data Dictionary

> **Status:** Verified Data Dictionary & Schema Specification (Phases 0–6 Complete & Audited).

---

## 1. GDELT Events 2.0 — Raw Schema (61 columns)

All files are tab-delimited TSV with no header row. Column order is fixed. Source: [GDELT Events Codebook](http://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf)

> **Ingestion rule:** Read all 61 columns as `dtype=str` on first pass. Cast to typed columns using the table below after loading.

| # | Column Name | Raw Type | Cast Type | Nullable | Notes |
|---|---|---|---|---|---|
| 1 | `GLOBALEVENTID` | str | int64 | No | Unique event identifier. Use as primary key. |
| 2 | `SQLDATE` | str | date (parsed via `YYYYMMDD`) | No | Contextual Event Date (when the incident allegedly took place) |
| 3 | `MonthYear` | str | int32 | No | Format: YYYYMM |
| 4 | `Year` | str | int16 | No | Four-digit year |
| 5 | `FractionDate` | str | float32 | No | Decimal year (e.g., 2026.82) |
| 6 | `Actor1Code` | str | str | Yes | CAMEO actor code — Actor 1 |
| 7 | `Actor1Name` | str | str | Yes | Full resolved name |
| 8 | `Actor1CountryCode` | str | str(3) | Yes | CAMEO/FIPS country code |
| 9 | `Actor1KnownGroupCode` | str | str | Yes | Known group membership |
| 10 | `Actor1EthnicCode` | str | str | Yes | Ethnic group code |
| 11 | `Actor1Religion1Code` | str | str | Yes | Primary religion code |
| 12 | `Actor1Religion2Code` | str | str | Yes | Secondary religion code |
| 13 | `Actor1Type1Code` | str | str | Yes | CAMEO actor type 1 |
| 14 | `Actor1Type2Code` | str | str | Yes | CAMEO actor type 2 |
| 15 | `Actor1Type3Code` | str | str | Yes | CAMEO actor type 3 |
| 16 | `Actor2Code` | str | str | Yes | CAMEO actor code — Actor 2 |
| 17 | `Actor2Name` | str | str | Yes | Full resolved name |
| 18 | `Actor2CountryCode` | str | str(3) | Yes | CAMEO/FIPS country code |
| 19 | `Actor2KnownGroupCode` | str | str | Yes | Known group membership |
| 20 | `Actor2EthnicCode` | str | str | Yes | Ethnic group code |
| 21 | `Actor2Religion1Code` | str | str | Yes | Primary religion code |
| 22 | `Actor2Religion2Code` | str | str | Yes | Secondary religion code |
| 23 | `Actor2Type1Code` | str | str | Yes | CAMEO actor type 1 |
| 24 | `Actor2Type2Code` | str | str | Yes | CAMEO actor type 2 |
| 25 | `Actor2Type3Code` | str | str | Yes | CAMEO actor type 3 |
| 26 | `IsRootEvent` | str | int8 (0/1) | No | 1 = root event; 0 = sub-event |
| 27 | `EventCode` | str | str(4) | No | CAMEO event code. **Must preserve leading zeros.** |
| 28 | `EventBaseCode` | str | str(3) | No | Three-digit CAMEO base code |
| 29 | `EventRootCode` | str | str(2) | No | Two-digit CAMEO root code |
| 30 | `QuadClass` | str | int8 | No | 1=Verbal Coop, 2=Material Coop, 3=Verbal Conflict, 4=Material Conflict |
| 31 | `GoldsteinScale` | str | float32 | Yes | Theoretical event stability impact: −10 (destabilising) to +10 (stabilising) |
| 32 | `NumMentions` | str | int32 | No | Total mentions across all source articles |
| 33 | `NumSources` | str | int16 | No | Number of distinct source documents |
| 34 | `NumArticles` | str | int16 | No | Number of distinct articles |
| 35 | `AvgTone` | str | float32 | Yes | Average sentiment tone of covering articles (negative = negative tone) |
| 36 | `Actor1Geo_Type` | str | int8 | Yes | 1=Country, 2=US State, 3=US City, 4=World City, 5=World State |
| 37 | `Actor1Geo_FullName` | str | str | Yes | Full resolved geographic name |
| 38 | `Actor1Geo_CountryCode` | str | str(2) | Yes | FIPS 2-char country code |
| 39 | `Actor1Geo_ADM1Code` | str | str | Yes | Admin 1 code (state/province) |
| 40 | `Actor1Geo_ADM2Code` | str | str | Yes | Admin 2 code |
| 41 | `Actor1Geo_Lat` | str | float32 | Yes | Latitude |
| 42 | `Actor1Geo_Long` | str | float32 | Yes | Longitude |
| 43 | `Actor1Geo_FeatureID` | str | str | Yes | GeoNames feature ID |
| 44 | `Actor2Geo_Type` | str | int8 | Yes | Same type codes as Actor1Geo_Type |
| 45 | `Actor2Geo_FullName` | str | str | Yes | Full resolved geographic name |
| 46 | `Actor2Geo_CountryCode` | str | str(2) | Yes | FIPS 2-char country code |
| 47 | `Actor2Geo_ADM1Code` | str | str | Yes | Admin 1 code |
| 48 | `Actor2Geo_ADM2Code` | str | str | Yes | Admin 2 code |
| 49 | `Actor2Geo_Lat` | str | float32 | Yes | Latitude |
| 50 | `Actor2Geo_Long` | str | float32 | Yes | Longitude |
| 51 | `Actor2Geo_FeatureID` | str | str | Yes | GeoNames feature ID |
| 52 | `ActionGeo_Type` | str | int8 | Yes | Geography of the action itself |
| 53 | `ActionGeo_FullName` | str | str | Yes | Primary display geography |
| 54 | `ActionGeo_CountryCode` | str | str(2) | Yes | Used for country-level aggregation |
| 55 | `ActionGeo_ADM1Code` | str | str | Yes | Admin 1 code |
| 56 | `ActionGeo_ADM2Code` | str | str | Yes | Admin 2 code |
| 57 | `ActionGeo_Lat` | str | float32 | Yes | Primary latitude for map rendering |
| 58 | `ActionGeo_Long` | str | float32 | Yes | Primary longitude for map rendering |
| 59 | `ActionGeo_FeatureID` | str | str | Yes | GeoNames feature ID |
| 60 | `DATEADDED` | str | int64 | No | Reporting Activity Time: when article was indexed (format: YYYYMMDDHHmmSS) |
| 61 | `SOURCEURL` | str | str | Yes | URL of the source article |

**Critical ingestion & date semantic notes:**
- `DATEADDED` (Column 60) represents the **Reporting Activity Time** when news was captured and indexed by GDELT. Anomaly detection is performed strictly on time-series aggregated by `DATEADDED`.
- `SQLDATE` (Column 2) represents the **Contextual Event Date** when the reported incident allegedly took place. A historical report indexed today might refer to an event that occurred last year.
- `EventCode` must remain a string to preserve leading zeros (e.g., `"010"` not `10`).
- `GoldsteinScale` can be empty string for some records — cast to float with `pd.to_numeric(..., errors='coerce')`.
- `SQLDATE` format is `YYYYMMDD` (integer-like string) — parse with `pd.to_datetime(df['SQLDATE'], format='%Y%m%d')`.

---

## 2. CAMEO Taxonomy Reference

### 2.1 QuadClass Values

| Value | Label | Colour Code (UI) |
|---|---|---|
| 1 | Verbal Cooperation | `#2196F3` (blue) |
| 2 | Material Cooperation | `#4CAF50` (green) |
| 3 | Verbal Conflict | `#FF9800` (orange) |
| 4 | Material Conflict | `#F44336` (red) |

### 2.2 CAMEO Event Root Codes (top-level, 20 categories)

| Root Code | Label | Description |
|---|---|---|
| 01 | Make Public Statement | Verbal acts of making public statements |
| 02 | Appeal | Requests or demands |
| 03 | Express Intent | Expressions of intent to cooperate |
| 04 | Consult | Consultations and meetings |
| 05 | Engage in Diplomatic Cooperation | Formal diplomatic exchanges |
| 06 | Engage in Material Cooperation | Provide material aid or support |
| 07 | Provide Aid | Humanitarian or economic aid |
| 08 | Yield | Concessions or capitulations |
| 09 | Investigate | Investigations and inquiries |
| 10 | Demand | Demands and ultimatums |
| 11 | Disapprove | Criticism and condemnation |
| 12 | Reject | Refusals and vetoes |
| 13 | Threaten | Threats |
| 14 | Protest | Demonstrations and boycotts |
| 15 | Exhibit Force Posture | Military manoeuvres |
| 16 | Reduce Relations | Diplomatic downgrades |
| 17 | Coerce | Coercion and sanctions |
| 18 | Assault | Armed attacks |
| 19 | Fight | Armed conflict |
| 20 | Engage in Unconventional Mass Violence | Terrorism, mass atrocities |

> **Implementation note:** Ship a static `cameo_event_codes.csv` lookup table mapping all 4-digit codes to root code, base code, and human-readable label. This file must be included in the repository and read at startup.

---

## 3. Derived Feature Dictionary

These fields are computed by `crisislens.features` and are not present in raw GDELT files.

| Field Name | Data Type | Source | Formula | Null-safe? |
|---|---|---|---|---|
| `daily_event_count` | int | `events` table | `COUNT(*) GROUP BY event_date` | Yes |
| `daily_conflict_ratio` | float [0,1] | `events` table | `SUM(quad_class IN (3,4)) / COUNT(*)` | Yes (0.0 if no events) |
| `mean_goldstein_daily` | float | `events` table | `AVG(goldstein_scale) GROUP BY event_date` | Yes (NaN if all null) |
| `rolling_7d_mean` | float | `daily_event_count` | `pd.Series.rolling(7).mean()` | No (first 6 days = NaN) |
| `rolling_7d_std` | float | `daily_event_count` | `pd.Series.rolling(7).std()` | No (first 6 days = NaN) |
| `rolling_30d_iqr_upper` | float | `daily_event_count` | Q3 + 1.5 × IQR over 30-day window | No (first 29 days = NaN) |
| `z_score` | float | above rolling stats | `(daily_event_count - rolling_7d_mean) / rolling_7d_std` | No |
| `is_anomaly_l1` | bool | `z_score` + IQR | `abs(z_score) > threshold OR daily_count > iqr_upper` | Yes |
| `is_anomaly_l2` | bool | STL residual | `abs(stl_residual_zscore) > threshold` | Requires ≥ 60 days |
| `is_anomaly_l3` | bool | Isolation Forest | `if_score < contamination_threshold` | Requires ≥ 90 days |
| `country_event_count` | int | `events` table | `COUNT(*) GROUP BY event_date, action_country` | Yes |
| `top_actor_on_date` | str | `events` table | `MODE(actor1_name) WHERE event_date = X` | Yes (empty string if all null) |

---

## 4. DuckDB Schema Definitions

### 4.1 `events` table (primary analytics table)

See `ARCHITECTURE.md §2.2` for the full `CREATE TABLE` statement.

### 4.2 `ingestion_log` table (pipeline audit trail)

```sql
CREATE TABLE ingestion_log (
    run_id        VARCHAR PRIMARY KEY,   -- UUID v4
    started_at    TIMESTAMP NOT NULL,
    completed_at  TIMESTAMP,
    files_fetched INTEGER DEFAULT 0,
    files_failed  INTEGER DEFAULT 0,
    rows_inserted BIGINT DEFAULT 0,
    rows_skipped  BIGINT DEFAULT 0,
    date_range_start DATE,
    date_range_end   DATE,
    error_message VARCHAR
);
```

### 4.3 `model_runs` table (model version tracking)

```sql
CREATE TABLE model_runs (
    run_id          VARCHAR PRIMARY KEY,
    model_name      VARCHAR NOT NULL,
    level           TINYINT NOT NULL,
    trained_at      TIMESTAMP NOT NULL,
    window_start    DATE,
    window_end      DATE,
    n_samples       INTEGER,
    threshold       FLOAT,
    artifact_path   VARCHAR,
    config_hash     VARCHAR(64)         -- SHA-256 of settings.toml
);
```

---

## 5. Geography Reference

### 5.1 GDELT Country Code System

GDELT uses **FIPS 10-4** country codes (2-character), not ISO 3166-1 alpha-2 or alpha-3.

| GDELT/FIPS | ISO 3166-1 Alpha-2 | Country |
|---|---|---|
| US | US | United States |
| UK | GB | United Kingdom |
| RS | RU | Russia |
| CH | CN | China |
| IN | IN | India |
| FR | FR | France |
| GM | DE | Germany |

> **Implementation note:** Ship a static `fips_to_iso.csv` mapping file. This is required for map rendering because Folium/Plotly use ISO codes, not FIPS codes.

### 5.2 `ActionGeo_Type` Values

| Value | Meaning |
|---|---|
| 0 | Unknown |
| 1 | Country level |
| 2 | US state |
| 3 | US city/town |
| 4 | World city/town |
| 5 | World state/province |

Only `ActionGeo_Type IN (1,4,5)` should be used for international heat map rendering. Types 2 and 3 are US-specific subdivisions.

---

## 6. Glossary

| Term | Definition |
|---|---|
| **GDELT** | Global Database of Events, Language, and Tone. A freely available global event database monitoring the world's broadcast, print, and web news media. |
| **CAMEO** | Conflict and Mediation Event Observations taxonomy. A hierarchical coding scheme for political and social events used by GDELT. |
| **GoldsteinScale** | A numerical score from −10 (maximally destabilising) to +10 (maximally stabilising) associated with each CAMEO event type. Defined by scholar Joshua Goldstein. |
| **QuadClass** | A simplified 4-category classification of CAMEO events: Verbal Cooperation, Material Cooperation, Verbal Conflict, Material Conflict. |
| **Root Event** | The primary event record (`IsRootEvent = 1`). Multiple news articles about the same event produce multiple rows, but only one is the root. |
| **z-score** | A standardised measure of how many standard deviations an observation is from the mean. |
| **IQR fence** | A non-parametric outlier threshold: Q3 + 1.5 × (Q3 − Q1). More robust than z-score for skewed distributions. |
| **STL** | Seasonal-Trend decomposition using Loess. Separates a time series into seasonal, trend, and residual components. |
| **Isolation Forest** | An unsupervised ML algorithm that detects anomalies by isolating observations in a random forest structure. |
| **Contamination** | Isolation Forest hyperparameter representing the assumed proportion of anomalies in the dataset (e.g., 0.05 = 5%). A design assumption, not a measured quantity. |
| **Parquet** | A columnar storage file format optimised for analytical queries. Produced by Apache Arrow / PyArrow. |
| **DuckDB** | An in-process analytical SQL database. No server required. Reads Parquet natively. |
| **FIPS 10-4** | Federal Information Processing Standard for country codes, used by GDELT (differs from ISO 3166). |

---

*Last updated: Design phase, 2026-10-29*
