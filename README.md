# 🐅 WHO DEY WACC — International Cost of Capital App

A Streamlit app that compares a project's **cost of equity, cost of debt and WACC in USD and in the currency of any selected country**, side by side. Orange-and-black, Bengals-fan themed.

> Fan-themed class project. Not affiliated with, endorsed by, or sponsored by the Cincinnati Bengals or the NFL. No team logos are used.

## What it does

- Pulls the latest data from four sources, shows the source, data date and fetch time for each, and has a **Refresh data** button.
- Lets you pick an **industry** and a **target country**, and adjust the **equity risk premium** and **target debt share**.
- Lets you **manually override** every fetched input: unlevered beta, U.S. and foreign corporate tax rates, USD BBB spread, and both 10-year government yields.
- The **foreign-currency BBB spread** is auto-calculated; flip the toggle to type your own.
- A **switch** chooses whether the U.S. or the selected country's tax rate is the project tax rate. One rate is used for both currencies.
- Shows results **side by side**, explains the assumptions, ranks **all industries**, and offers **CSV / Excel downloads**.

**Defaults on open:** Software (System & Application), United States as the selected country, U.S. tax rate, 6.5% equity risk premium, 30% debt.

## Data sources

| Input | Source | Link |
|---|---|---|
| Unlevered industry betas (U.S.) | Aswath Damodaran, NYU Stern — "Unlevered beta" column | https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls |
| USD BBB spread (Baa2/BBB, large non-financial service firms) | Aswath Damodaran, NYU Stern | https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html |
| Corporate tax rates (combined statutory rate) | OECD Corporate Tax Statistics | https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html |
| 10-year government bond yields | Trading Economics | https://tradingeconomics.com/bonds |

Notes on the fetch:

- **OECD.** The linked report chapter shows country rates only as a chart, not a table. The app therefore reads the same OECD Corporate Tax Statistics dataset through the OECD Data Explorer API (`sdmx.oecd.org`, dataflow `DSD_TAX_CIT@DF_CIT`), taking the *combined statutory* rate for the latest year available per country. For the U.S. this is the 21% federal rate plus average state taxes (about 25.5%); override it if you want 21%.
- **Trading Economics.** The bonds table sits behind a bot check and may not be served to a cloud server. The app makes a plain request; if no table comes back it does **not** try to get around the block.
- **Snapshot fallback.** If any live fetch fails, the app uses a dated snapshot of that source (values read from the sites on 16 Nov 2026), shows a warning banner, and labels the input "Snapshot". Use the manual overrides to enter current values.
- Russia and Taiwan have yields but no OECD tax rate; the app falls back to the U.S. rate and tells you.

## Formulas

All formulas are in one function, `compute()`, at the top of `app.py`. **Check them against the class handout.**

```
D/E            = d / (1 − d)
Levered beta   = β_U × [1 + (1 − t) × D/E]

USD
  Cost of equity = y_US + β_L × ERP
  Cost of debt   = y_US + BBB spread (USD)
  WACC           = (1 − d) × Ke + d × Kd × (1 − t)

Foreign currency
  Cost of equity = y_FC + β_L × ERP
  BBB spread     = BBB spread (USD) × (1 + y_FC) / (1 + y_US)     ← auto; can be overridden
  Cost of debt   = y_FC + BBB spread (FC)
  WACC           = (1 − d) × Ke + d × Kd × (1 − t)
```

`d` = debt share D/(D+E), `t` = project tax rate, `y` = 10-year government yield.

## Verification

The **Verification** tab re-runs these checks live on whatever inputs are on screen:

1. Equal government yields (foreign-spread override off) → USD and foreign results are identical.
2. Zero debt → WACC equals the cost of equity.
3. Overriding the foreign-currency spread → USD results do not change.

It also prints a step-by-step hand calculation with the current inputs to replicate in a spreadsheet.

Worked example (defaults, using the 16 Nov 2026 snapshot values: β_U 1.23, t 25.5285%, d 30%, ERP 6.5%, y_US 5.112%, BBB spread 1.11%):

```
D/E    = 0.30 / 0.70                              = 0.428571
β_L    = 1.23 × [1 + (1 − 0.255285) × 0.428571]    = 1.622571
Ke     = 0.05112 + 1.622571 × 0.065               = 15.6587%
Kd     = 0.05112 + 0.0111                         = 6.2220%
WACC   = 0.70 × 0.156587 + 0.30 × 0.06222 × (1 − 0.255285) = 12.3512%
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository and upload `app.py`, `requirements.txt` and `README.md`.
2. Go to https://share.streamlit.io → **Create app** → pick the repo, branch `main`, main file `app.py`.
3. Click **Deploy**.

Optional: for orange sliders and checkboxes, add a file `.streamlit/config.toml` containing:

```toml
[theme]
primaryColor = "#FB4F14"
```
