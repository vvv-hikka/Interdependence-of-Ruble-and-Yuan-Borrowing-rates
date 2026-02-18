# Data Status and Future Work Plan

Based on the pipeline run output (terminal 11), this document summarizes **what data you have**, **what is missing or broken**, **what is wrong with the current structure**, and a **concrete plan** for cleaning fetches, trying new sources, and updating analysis.

---

## 1. Data You Have (Working)

| Table | Rows | Status | Notes |
|-------|------|--------|--------|
| **cbr_key_rate** | 150 | OK | CBR key rate, monthly, 2013–2026 |
| **currency_rates** | 134 | OK | USD/RUB, CNY/RUB, EUR/RUB, monthly |
| **russian_bond_yields** | 85 | OK | OFZ yields 2Y–20Y, monthly, 2019–2026 |
| **russian_macro** | 87 | Partial | CPI + Industrial Production only; no consumer confidence; ends 2022-03 |
| **pboc_lpr** | 1568 | OK | LPR 1Y/5Y; has both `TRADE_DATE` and `date` (redundant) |
| **global_indicators** | 134 | OK | DGS10, DGS2, FEDFUNDS, Brent, DTWEXBGS, IPMAN, UMCSENT |
| **business_activity** | 132 | Partial | RU industrial prod + US IPMAN + UMCSENT only |
| **cbr_gcurve** | 133 | Saved but error | 133 rows saved; "Error processing G-Curve: ['date']" suggests a bug in monthly processing (e.g. duplicate/rename of `date`) |

**Chinese data (limited):**

| Table | Rows | Status | Notes |
|-------|------|--------|--------|
| **chinese_bond_yields** | 12 | Very limited | Only 2020-02–2021-01; columns show as "3?", "6?" (encoding) |
| **chinese_macro** | 2886 | Messy | Many columns; names like `CN_bond_yields_????`, `3?` (encoding / Chinese chars) |

---

## 2. Data Missing or Failing

### 2.1 FRED

- **RUSCCUSMA02STM** (Russia Consumer Confidence): **404 Not Found** — series likely discontinued or ID changed.
- **CHNPROINDMISMEI** (China Industrial Production): **404 Not Found**.
- **CHNCPIALLMINMEI**, **DEXCHUS**: sometimes **502 Bad Gateway** or connection errors (transient).

**Action:** Find replacement FRED series or alternative sources for Russia consumer confidence and China industrial production; add retries/backoff for 502s.

### 2.2 AKShare (API changes)

- `macro_china_ppi_monthly` — **no attribute** (removed/renamed in current akshare).
- `macro_china_industrial_output` — **no attribute**.
- `macro_china_enterprise_confidence` — **no attribute**.

**Action:** Check akshare docs/changelog for new function names (e.g. `macro_china_ppi`, `macro_china_industrial_*`, enterprise/confidence); use getattr + fallback so pipeline does not crash when one series is missing.

### 2.3 IMF IFS

- All tested series (RUS/CHN CPI, PPI, exchange rate, policy rate, M2, business activity): **timeouts** or **NameResolutionError** (e.g. `dataservices.imf.org` not resolved).

**Action:** Increase timeout; optional proxy/VPN if blocked; consider pre-downloaded IMF CSV as fallback.

**IMF CSV fallback (optional):** If the API fails consistently, you can place a CSV under `data/raw/` or `data/manual/` (e.g. `imf_ifs_russia_china.csv`) with columns: `date` (YYYY-MM or YYYY-MM-DD), `country` (e.g. RUS, CHN), `series_code` (IFS code), `value` (numeric). The pipeline can be extended to load this file and merge into russian_macro / chinese_macro when the API is unavailable.

### 2.4 Manual / Other

- **ChinaBond yields**: manual file not found (`data/manual/chinabond_yields.xlsx` or `.csv`). Pipeline still saves 12 rows from AKShare only.
- **BIS**: placeholder only; no real fetch. Use manual download (see below).
- **CBR** industrial production / business confidence: info-only messages; no data written.

### 2.5 Manual data files (path and format)

**ChinaBond (Chinese government bond yields)**  
- **Path:** `data/manual/chinabond_yields.xlsx` or `data/manual/chinabond_yields.csv` (project root is the repo root).  
- **Format:** One column for date (any standard date format), plus one column per maturity for yields (e.g. 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 15Y, 20Y, 30Y). The fetcher normalizes names to `CN_3M`, `CN_1Y`, etc.  
- **Source:** [ChinaBond](https://www.chinabond.com.cn/) or [yield.chinabond.com.cn](https://yield.chinabond.com.cn/) — download yield curve data and save to the path above.

**BIS (Bank for International Settlements)**  
- **Status:** Manual only. The BIS fetcher is a placeholder; it does not fetch data automatically.  
- To use BIS data: download from [BIS statistics](https://www.bis.org/statistics/) and place files in `data/manual/` (format can be documented later if a CSV loader is added).

---

## 3. What Is Wrong With the Data (Structure and Quality)

### 3.1 Combined monthly view is broken (critical)

- `create_combined_monthly_view()` uses **all** tables from `list_tables()`, including **`combined_monthly`**.
- So each run merges the **previous** combined table with others → column names get prefixed again:  
  `combined_monthly_global_indicators_DGS10` → then  
  `combined_monthly_combined_monthly_global_indicators_DGS10`, etc.
- Result: 288 columns, many with long repeated prefixes; analysis and joins become unclear.

**Fix:** Exclude derived table `combined_monthly` (and any other “view” tables) when building the combined view. Only merge **base** tables (cbr_key_rate, cbr_gcurve, currency_rates, russian_bond_yields, russian_macro, pboc_lpr, chinese_bond_yields, chinese_macro, global_indicators, business_activity).

### 3.2 Chinese bond yields: sparse and encoding

- Only **12 monthly rows** (one year); column names like "3?", "6?" suggest encoding issues (e.g. "3Y", "6Y" stored or displayed incorrectly).
- Need: more history (manual file or another source) and stable, ASCII-friendly column names (e.g. `CN_3Y`, `CN_10Y`).

### 3.3 Chinese macro: noisy column names

- Names such as `CN_bond_yields_????` and `3?` come from Chinese characters or AKShare column names not normalized.
- Pipeline should: normalize column names (e.g. strip non-ASCII, map maturities to `CN_3Y`, `CN_5Y`, etc.) before save so analysis and combined view stay readable.

### 3.4 Redundant / duplicate columns

- **pboc_lpr**: both `TRADE_DATE` and `date`; standardize on one (e.g. `date`) and drop or rename the other before saving.

### 3.5 G-Curve processing bug

- "Error processing G-Curve: ['date']" in CBR fetcher: likely a KeyError or duplicate `date` when building monthly DataFrame (e.g. after `resample('ME').last().reset_index()` the date column might be in the index or named differently). Fix the CBR G-Curve monthly aggregation so 133 rows are correct and no fallback overwrites good data.

### 3.6 Russian macro end date

- Russian macro stops at **2022-03** (FRED/IMF availability); document this and optionally add a note in config or in the combined view metadata so analysis does not assume recent Russian macro.

---

## 4. Plan for Future Work

### Phase 1: Fix pipeline and database structure (priority)

1. **Exclude `combined_monthly` when building combined view**  
   In `src/database/manager.py`, in `create_combined_monthly_view()`, filter out `combined_monthly` (and any other derived/view tables) from `tables` before the loop. Optionally define a list of “base” tables and only merge those.

2. **Fix CBR G-Curve monthly processing**  
   In `src/fetchers/cbr.py`, in `fetch_gcurve_monthly()`, ensure the monthly DataFrame has a single `date` column (no duplicate, correct after `reset_index()`). Fix the `rename(columns=new_cols)` logic so it does not raise (e.g. handle index name vs column name).

3. **Normalize column names before save**  
   - Chinese bond yields: map "3?", "6?" etc. to `CN_3M`, `CN_6M`, `CN_1Y`, … in pipeline or in chinabond/akshare fetcher.  
   - Chinese macro: sanitize AKShare column names (ASCII, consistent prefixes like `CN_ppi_`, `CN_cpi_`) in pipeline or in akshare_cn.

4. **pboc_lpr: single date column**  
   In pipeline or in chinabond fetcher: keep one `date` column, drop or rename `TRADE_DATE` so downstream and combined view stay consistent.

5. **One-time: rebuild combined view**  
   After the fix: drop `combined_monthly` table (or truncate), then run pipeline once so the new combined view has clean column names (one prefix per base table, e.g. `cbr_key_rate_cbr_key_rate`, `global_indicators_DGS10`).

### Phase 2: Clean notebooks and remove unnecessary fetches

6. **Audit notebooks**  
   - Remove or comment out cells that fetch data that always fails (e.g. IMF if you keep timeouts, or specific FRED series that are 404).  
   - Keep only fetches that are used for analysis or that you intend to fix (new sources / new APIs).

7. **Optional: “data status” notebook**  
   - One notebook or script that: loads each base table, prints shape, date range, and % missing; does not run full pipeline. Helps avoid redundant full runs during cleanup.

### Phase 3: New or alternative data sources

8. **FRED**  
   - Search FRED for replacement series for Russia consumer confidence and China industrial production (e.g. different IDs or “alternative” series).  
   - Add retries/backoff for 502/connection errors; optionally use fredapi instead of CSV if more stable.

9. **AKShare**  
   - Check current akshare API for: PPI, industrial production, enterprise/confidence (new names or alternative endpoints).  
   - Wrap calls in getattr/try-except and skip series if not available so pipeline still saves other China macro data.

10. **IMF**  
    - Increase timeout; add retry.  
    - If still failing: consider pre-downloaded IMF IFS CSV (manual or script) and a small “imf_csv” fetcher that loads from `data/raw/` or `data/manual/`.

11. **ChinaBond**  
    - Add README or config note with exact path and expected format for `data/manual/chinabond_yields.xlsx`.  
    - Optionally: try other akshare bond endpoints or another source for longer Chinese yield history.

12. **BIS**  
    - Either implement a real BIS API/CSV fetcher or remove from pipeline and document “BIS: manual only” so logs are not misleading.

### Phase 4: Statistical analysis updates

13. **Analysis assumes clean combined view**  
    - After Phase 1, `combined_monthly` will have predictable columns (e.g. `global_indicators_DGS10`, `cbr_key_rate_cbr_key_rate`).  
    - In `src/analysis/statistics.py`: ensure variable selection (e.g. for correlation, regression) uses these names and does not depend on the old long recursive prefixes. Add a small list of “analysis variables” (Ruble/Yuan rates, key macro) in config or in the module.

14. **Handle missing and short series**  
    - In analysis: explicit handling of NaNs and short Chinese bond series (e.g. 12 rows); optional start_date/end_date so that models use a common sample where key series are non-missing.

15. **Document date ranges**  
    - In config or in a short “data_spec” document: list each table’s expected date range and main source. Reduces risk of analyzing periods with no data.

---

## 5. Suggested order of work

1. Fix combined view (exclude `combined_monthly`) and rebuild it.  
2. Fix G-Curve and pboc_lpr structure; normalize Chinese column names.  
3. Update analysis to use the new combined column names and handle missing/short series.  
4. Clean notebooks (remove or guard failing fetches).  
5. Add alternative FRED series and akshare replacements; then IMF/BIS/ChinaBond as needed.

This keeps the pipeline and database structure correct first, then improves coverage and analysis without fighting broken views and naming.
