# Data Sources: Status & Methods

> Last updated: 2026-02-18

This document catalogues every data source attempted in the pipeline, the method used to fetch it, whether it succeeded, and what ended up in the database.

---

## Summary Table

| Source | Method | Status | Data Retrieved | Notes |
|--------|--------|--------|----------------|-------|
| **CBR Key Rate** | HTML scrape (`cbr.ru/hd_base/KeyRate/`) | **OK** | 150 monthly rows, 2013–2026 | XML endpoint fails (malformed); HTML fallback works reliably |
| **CBR G-Curve** | HTML scrape (`cbr.ru/hd_base/zcyc_params/`), year-by-year | **OK** | 133 monthly rows, 2015–2026 | Yields for 1Y, 3Y, 5Y, 10Y+ maturities |
| **CBR Currency Rates** | XML API (`cbr.ru/scripts/XML_dynamic.asp`) | **OK** | 134 monthly rows, 2015–2026 | USD/RUB, CNY/RUB, EUR/RUB |
| **MOEX OFZ Yields** | ISS REST API (`iss.moex.com`) | **OK** | 85 monthly rows, 2019–2026 | 7 maturities (2Y–20Y); uses benchmark bond ISINs |
| **FRED Russia Macro** | CSV download (`fred.stlouisfed.org`) | **Partial** | 87 rows (CPI, IP), 2015–2022 | Consumer confidence (RUSCCUSMA02STM) discontinued (404) |
| **FRED China Macro** | CSV download | **Partial** | CPI (124 rows), USD/CNY (2778 rows) | Industrial production (CHNPROINDMISMEI) discontinued (404) |
| **FRED Global** | CSV download | **OK** | 134 monthly rows, 2015–2026 | DGS10, DGS2, FEDFUNDS, Brent, USD Index, IPMAN, UMCSENT |
| **FRED Business Activity** | CSV download | **OK** | 132 monthly rows | RU industrial production, US IPMAN, UMCSENT |
| **AKShare China Bonds** | `ak.bond_china_yield()` | **Limited** | 738 daily → 12 monthly | Only ~1 year of monthly data (2020-02 to 2021-01) |
| **AKShare PBOC LPR** | `ak.macro_china_lpr()` | **OK** | 1568 rows, 1991–2026 | LPR 1Y and 5Y rates |
| **AKShare China CPI** | `ak.macro_china_cpi_monthly()` | **OK** | 357 rows | Monthly CPI data |
| **AKShare China PPI** | `ak.macro_china_ppi_monthly()` (fallback methods) | **OK** | 241 rows | |
| **AKShare China PMI** | `ak.macro_china_pmi()` | **OK** | 217 rows | Manufacturing PMI |
| **AKShare Services PMI** | `ak.macro_china_pmi_services()` / fallback | **OK** | 217 rows | |
| **AKShare China GDP** | `ak.macro_china_gdp()` | **OK** | 80 rows | Quarterly |
| **AKShare Money Supply** | `ak.macro_china_money_supply()` | **OK** | 217 rows | M0, M1, M2 |
| **AKShare Trade Balance** | `ak.macro_china_trade_balance()` | **OK** | 565 rows | |
| **AKShare Reserve Ratio** | `ak.macro_china_reserve_requirement_ratio()` | **OK** | 58 rows | PBOC RRR history |
| **Embedded PBOC LPR** | Hardcoded CSV in `chinabond.py` | **OK** | 66 rows, 2019–2025 | Fallback for AKShare |
| **Embedded CBR Key Rate** | Hardcoded CSV in `cbr.py` | **Fallback** | 40 rows, 2013–2024 | Used only if both XML and HTML fail |
| **IMF IFS (Russia)** | REST API (`dataservices.imf.org`) | **FAILED** | 0 rows | All 5 series timeout consistently |
| **IMF IFS (China)** | REST API | **FAILED** | 0 rows | All 5 series timeout consistently |
| **IMF IFS (Business)** | REST API | **FAILED** | 0 rows | All 8 series timeout consistently |
| **BIS** | Placeholder (no real fetch) | **FAILED** | 0 rows | Requires manual CSV download |
| **ChinaBond Manual** | Loader reads all `.xlsx` and `.csv` in `src/data_manual/` | **N/A** | Varies | Place ChinaBond yield curve exports in `src/data_manual/`; all files combined by date |
| **CBR Ind. Production** | Placeholder (info messages only) | **FAILED** | 0 rows | Rosstat is the actual source |
| **CBR Business Confidence** | Placeholder (info messages only) | **FAILED** | 0 rows | |
| **AKShare Ind. Production** | `macro_china_industrial_*` (multiple names tried) | **FAILED** | 0 rows | No matching akshare method |
| **AKShare Biz Confidence** | `macro_china_business_confidence` etc. | **FAILED** | 0 rows | No matching akshare method |
| **FRED RUSCCUSMA02STM** | CSV download | **FAILED** | 0 rows | Series discontinued (HTTP 404) |
| **FRED CHNPROINDMISMEI** | CSV download | **FAILED** | 0 rows | Series discontinued (HTTP 404) |

---

## Database Tables

After a successful pipeline run, the database contains these tables:

| Table | Description | Rows | Key Columns | Period |
|-------|-------------|------|-------------|--------|
| `cbr_key_rate` | CBR key interest rate | 150 | `date`, `cbr_key_rate` | 2013-09 – 2026-02 |
| `cbr_gcurve` | G-Curve yields | 133 | `date`, `RU_1Y`, `RU_3Y`, `RU_5Y`, `RU_10Y` | 2015-01 – 2026-01 |
| `currency_rates` | FX rates | 134 | `date`, `usd_rub`, `cny_rub`, `eur_rub` | 2015-01 – 2026-02 |
| `russian_bond_yields` | OFZ yields | 85 | `date`, `RU_2Y`..`RU_20Y` | 2019-02 – 2026-02 |
| `russian_macro` | Russia CPI & IP | 87 | `date`, `RUSCPIALLMINMEI`, `RUSPROINDMISMEI` | 2015-01 – 2022-03 |
| `pboc_lpr` | PBOC LPR | ~1568 | `date`, `LPR1Y`, `LPR5Y` | 1991 – 2026-01 |
| `chinese_bond_yields` | CN govt yields | 12 | `date`, `CN_3M`..`CN_30Y` | 2020-02 – 2021-01 |
| `chinese_macro` | CN macro indicators | ~3700 | `date`, plus AKShare + FRED columns | 1981 – 2026-02 |
| `global_indicators` | US rates, oil, USD index | 134 | `date`, `DGS10`, `DGS2`, `FEDFUNDS`, `DCOILBRENTEU`, `DTWEXBGS`, `IPMAN`, `UMCSENT` | 2015-01 – 2026-02 |
| `business_activity` | Business activity | 132 | `date`, `RU_RUSPROINDMISMEI`, `IPMAN`, `UMCSENT` | 2015-01 – 2025-12 |
| `combined_monthly` | Outer-join of all above | ~3700 | All columns prefixed by table name | varies |

---

## Source Details

### 1. Bank of Russia (CBR)

**Module:** `src/fetchers/cbr.py`

- **Key Rate**: Tries XML endpoint first (`XML_KeyRate.asp`), falls back to HTML table scrape with date range parameters. Returns full history since 2013.
- **G-Curve**: Scrapes the HTML yield table at `hd_base/zcyc_params/` year-by-year (to avoid timeout with large ranges). Returns yields for standard maturities, resampled to monthly last-of-month. Column names are mapped from numeric (0.25, 1, 3, 5...) to `RU_3M`, `RU_1Y`, etc.
- **Currency Rates**: Uses the XML dynamic rates API (`XML_dynamic.asp`) with CBR currency codes (R01235=USD, R01375=CNY, R01239=EUR). Returns daily rates, resampled to monthly.

### 2. MOEX ISS (Moscow Exchange)

**Module:** `src/fetchers/moex.py`

- **OFZ Yields**: Fetches historical bond data for benchmark OFZ ISINs per maturity bucket (2Y, 3Y, 5Y, 7Y, 10Y, 15Y, 20Y). Uses `YIELDCLOSE` field. Paginated (100 records per request). Results pivoted to wide format with monthly resampling.

### 3. FRED (Federal Reserve Economic Data)

**Module:** `src/fetchers/fred.py`

- **Method**: When `FRED_API_KEY` is set (env or config), uses FRED REST API. Otherwise falls back to CSV download from `fred.stlouisfed.org/graph/fredgraph.csv`. Retries on 502 / connection errors (up to 3 attempts with exponential backoff).
- **Russia**: `RUSCPIALLMINMEI` (CPI, OK), `RUSPROINDMISMEI` (Industrial Production, OK). Data ends ~2022-03 (FRED stopped updating Russian series after sanctions).
- **China**: `CHNCPIALLMINMEI` (CPI, OK), `DEXCHUS` (USD/CNY, OK).
- **Global**: `DGS10`, `DGS2`, `FEDFUNDS`, `DCOILBRENTEU`, `DTWEXBGS`, `IPMAN`, `UMCSENT` — all working.
- **Removed (discontinued)**: `RUSCCUSMA02STM` (Russia Consumer Confidence), `CHNPROINDMISMEI` (China IP) — both return 404.

### 4. AKShare (Chinese Financial Data)

**Module:** `src/fetchers/akshare_cn.py`

- **Method**: Python API calls via the `akshare` library. No authentication needed.
- **Bond Yields**: `bond_china_yield()` returns daily data, resampled to monthly. Column names normalized from Chinese characters to ASCII (`CN_3M`, `CN_1Y`, etc.). Limited to ~12 months of data.
- **PBOC LPR**: `macro_china_lpr()` — full history since 1991. 1Y and 5Y LPR.
- **Macro indicators**: CPI, PPI, PMI, Services PMI, GDP, money supply, trade balance, reserve ratio — all working via dedicated `macro_china_*` functions.
- **Not available**: Industrial production and business confidence — no matching akshare method found (multiple names tried via `getattr` fallback).

### 5. IMF IFS — REMOVED from pipeline

**Module:** `src/fetchers/imf.py` (retained but not called)

- **Method**: REST API at `dataservices.imf.org/REST/SDMX_JSON.svc`
- **Result**: ALL requests timeout (120s) for both Russia and China. Likely blocked by network or API rate limits. 18 series attempted, 0 succeeded.
- **Decision**: Removed from pipeline to save ~10 minutes of timeout delays per run. Module kept for future use if API access is restored.

### 6. BIS — REMOVED from pipeline

**Module:** `src/fetchers/bis.py` (retained but not called)

- **Result**: Placeholder implementation only. Returns empty DataFrames with info messages.
- **Decision**: Removed from pipeline. Can be used if manual CSV downloads are placed in `data/manual/`.

### 7. ChinaBond Manual Loader

**Module:** `src/fetchers/chinabond.py`

- **Method**: Scans `src/data_manual/` for all `.xlsx` and `.csv` files (excluding template/placeholder). Loads each via `load_from_excel` or `load_from_csv`, applies `_process_chinabond_data`, and merges on date (outer). Overlapping maturities are coalesced (first non-null).
- **To use**: Place ChinaBond yield curve exports in `src/data_manual/`. The loader combines all files into one yield curve table. AKShare data is merged when both sources are available; the source with more rows is used as base.

---

## Known Limitations

1. **Russian macro ends 2022-03**: FRED stopped updating many Russian series after international sanctions.
2. **Chinese bond yields sparse**: Only ~12 monthly observations from AKShare. Manual ChinaBond download needed for longer history.
3. **No Russia business confidence**: FRED series discontinued; no alternative automated source.
4. **No China industrial production**: Both FRED and AKShare methods fail; consider NBS direct data.

---

## Pipeline Performance

| Version | Sources | Runtime | Notes |
|---------|---------|---------|-------|
| Before optimization | CBR + MOEX + FRED + AKShare + IMF + BIS + CBR placeholders | ~27 min | IMF timeouts dominate; AKShare called 3x |
| After optimization | CBR + MOEX + FRED + AKShare (cached) | ~5-8 min | IMF/BIS removed; AKShare cached once |
