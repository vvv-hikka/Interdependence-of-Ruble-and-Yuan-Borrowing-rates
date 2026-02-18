# Data specification: table date ranges and sources

Per-table expected date range and main source. Use this to avoid analyzing periods with no data. Ranges are indicative and may change after pipeline runs.

| Table | Expected date range | Main source |
|-------|---------------------|-------------|
| **cbr_key_rate** | 2013–present (monthly) | CBR API |
| **cbr_gcurve** | ~2015–present (monthly) | CBR |
| **currency_rates** | 2015–present (monthly) | CBR |
| **russian_bond_yields** | 2019–present (monthly) | MOEX / CBR |
| **russian_macro** | 2015–2022-03 (partial; CPI, industrial prod) | FRED |
| **pboc_lpr** | 2019–present | AKShare |
| **chinese_bond_yields** | Limited (e.g. 2020–2021 from AKShare); extend via manual ChinaBond file | AKShare, ChinaBond manual |
| **chinese_macro** | Varies by series | AKShare, FRED |
| **global_indicators** | 2015–present (monthly) | FRED |
| **business_activity** | 2015–present (partial) | FRED |

Update this table when new tables or sources are added. The optional script `scripts/check_data_status.py` prints current row counts and date ranges for all base tables.
