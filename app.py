"""
WHO DEY WACC - International Cost of Capital App
=================================================
Compares a project's cost of equity, cost of debt and WACC in USD and in the
currency of a selected country.

Data sources (fetched live, with a dated snapshot fallback if a site blocks us):
  1. Unlevered industry betas ... Damodaran, betas.xls
  2. BBB (Baa2/BBB) USD spread .. Damodaran, ratings.html (large non-financial firms)
  3. Corporate tax rates ........ OECD Corporate Tax Statistics (combined statutory rate)
  4. 10-year government yields .. Trading Economics, /bonds

ALL FORMULAS LIVE IN ONE FUNCTION: compute().  Check it against the formulas
handed out in class before you rely on any number this app produces.

Fan-themed class project. Not affiliated with the Cincinnati Bengals or the NFL.
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone

import altair as alt
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
ORANGE, BLACK, WHITE = "#FB4F14", "#000000", "#FFFFFF"

BETAS_XLS_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"
BETAS_HTML_URL = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/Betas.html"
RATINGS_URL = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html"
OECD_REPORT_URL = (
    "https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/"
    "full-report/statutory-corporate-income-tax-rates_440f9286.html"
)
OECD_SDMX_URL = (
    "https://sdmx.oecd.org/public/rest/data/OECD.CTP.TPS,DSD_TAX_CIT@DF_CIT,/all"
    "?startPeriod={start}&dimensionAtObservation=AllDimensions&format=csvfilewithlabels"
)
TE_URL = "https://tradingeconomics.com/bonds"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 20

DEFAULT_INDUSTRY = "Software (System & Application)"
DEFAULT_COUNTRY = "United States"
DEFAULT_ERP = 6.5      # %
DEFAULT_DEBT = 30.0    # %

# Trading Economics country name -> (ISO3 used by OECD, currency code)
COUNTRIES = {
    "United States": ("USA", "USD"), "United Kingdom": ("GBR", "GBP"), "Japan": ("JPN", "JPY"),
    "Australia": ("AUS", "AUD"), "Germany": ("DEU", "EUR"), "Brazil": ("BRA", "BRL"),
    "Russia": ("RUS", "RUB"), "India": ("IND", "INR"), "Canada": ("CAN", "CAD"),
    "Italy": ("ITA", "EUR"), "France": ("FRA", "EUR"), "South Africa": ("ZAF", "ZAR"),
    "China": ("CHN", "CNY"), "Switzerland": ("CHE", "CHF"), "Mexico": ("MEX", "MXN"),
    "Netherlands": ("NLD", "EUR"), "New Zealand": ("NZL", "NZD"), "Portugal": ("PRT", "EUR"),
    "South Korea": ("KOR", "KRW"), "Spain": ("ESP", "EUR"), "Greece": ("GRC", "EUR"),
    "Turkey": ("TUR", "TRY"), "Finland": ("FIN", "EUR"), "Lithuania": ("LTU", "EUR"),
    "Norway": ("NOR", "NOK"), "Poland": ("POL", "PLN"), "Romania": ("ROU", "RON"),
    "Slovakia": ("SVK", "EUR"), "Slovenia": ("SVN", "EUR"), "Sweden": ("SWE", "SEK"),
    "Hungary": ("HUN", "HUF"), "Iceland": ("ISL", "ISK"), "Ireland": ("IRL", "EUR"),
    "Austria": ("AUT", "EUR"), "Belgium": ("BEL", "EUR"), "Croatia": ("HRV", "EUR"),
    "Czech Republic": ("CZE", "CZK"), "Denmark": ("DNK", "DKK"), "Peru": ("PER", "PEN"),
    "Chile": ("CHL", "CLP"), "Colombia": ("COL", "COP"), "Singapore": ("SGP", "SGD"),
    "Taiwan": ("TWN", "TWD"), "Thailand": ("THA", "THB"), "Vietnam": ("VNM", "VND"),
    "Hong Kong": ("HKG", "HKD"), "Indonesia": ("IDN", "IDR"), "Israel": ("ISR", "ILS"),
    "Malaysia": ("MYS", "MYR"), "Pakistan": ("PAK", "PKR"), "Philippines": ("PHL", "PHP"),
    "Zambia": ("ZMB", "ZMW"), "Kenya": ("KEN", "KES"), "Nigeria": ("NGA", "NGN"),
    "Bulgaria": ("BGR", "BGN"), "Egypt": ("EGY", "EGP"), "Kazakhstan": ("KAZ", "KZT"),
    "Qatar": ("QAT", "QAR"), "Sri Lanka": ("LKA", "LKR"), "Ukraine": ("UKR", "UAH"),
    "Serbia": ("SRB", "RSD"), "Morocco": ("MAR", "MAD"), "Saudi Arabia": ("SAU", "SAR"),
    "Argentina": ("ARG", "ARS"), "Luxembourg": ("LUX", "EUR"), "Malta": ("MLT", "EUR"),
    "Latvia": ("LVA", "EUR"), "Estonia": ("EST", "EUR"), "Mauritius": ("MUS", "MUR"),
    "Namibia": ("NAM", "NAD"), "Botswana": ("BWA", "BWP"), "Jordan": ("JOR", "JOD"),
    "Bahrain": ("BHR", "BHD"), "Uganda": ("UGA", "UGX"), "Bangladesh": ("BGD", "BDT"),
}
NOT_COUNTRIES = {"Euro area", "Euro Area"}

# --------------------------------------------------------------------------- #
# Dated snapshots - used ONLY if a live fetch fails. Every number below was
# read from the named source on the stated date; nothing is estimated.
# --------------------------------------------------------------------------- #
SNAP_BETAS_ASOF = "January 2026 (snapshot read 16 Nov 2026)"
SNAP_BETAS = (
    "Advertising=0.93;Aerospace/Defense=0.85;Air Transport=0.70;Apparel=0.76;Auto & Truck=1.27;"
    "Auto Parts=1.02;Bank (Money Center)=0.34;Banks (Regional)=0.29;Beverage (Alcoholic)=0.61;"
    "Beverage (Soft)=0.56;Broadcasting=0.29;Brokerage & Investment Banking=0.58;"
    "Building Materials=0.93;Business & Consumer Services=0.77;Cable TV=0.35;Chemical (Basic)=0.58;"
    "Chemical (Diversified)=0.37;Chemical (Specialty)=0.79;Coal & Related Energy=1.02;"
    "Computer Services=0.92;Computers/Peripherals=1.31;Construction Supplies=1.02;Diversified=0.79;"
    "Drugs (Biotechnology)=1.03;Drugs (Pharmaceutical)=0.89;Education=0.66;Electrical Equipment=1.15;"
    "Electronics (Consumer & Office)=0.83;Electronics (General)=0.90;Engineering/Construction=1.09;"
    "Entertainment=0.74;Environmental & Waste Services=0.81;Farming/Agriculture=0.81;"
    "Financial Svcs. (Non-bank & Insurance)=0.32;Food Processing=0.46;Food Wholesalers=0.64;"
    "Furn/Home Furnishings=0.62;Green & Renewable Energy=0.46;Healthcare Products=0.83;"
    "Healthcare Support Services=0.69;Heathcare Information and Technology=0.99;Homebuilding=0.78;"
    "Hospitals/Healthcare Facilities=0.55;Hotel/Gaming=0.83;Household Products=0.72;"
    "Information Services=0.74;Insurance (General)=0.56;Insurance (Life)=0.43;"
    "Insurance (Prop/Cas.)=0.44;Investments & Asset Management=0.53;Machinery=0.87;"
    "Metals & Mining=0.96;Office Equipment & Services=0.98;Oil/Gas (Integrated)=0.27;"
    "Oil/Gas (Production and Exploration)=0.56;Oil/Gas Distribution=0.47;Oilfield Svcs/Equip.=0.74;"
    "Packaging & Container=0.72;Paper/Forest Products=0.72;Power=0.31;Precious Metals=0.79;"
    "Publishing & Newspapers=0.48;R.E.I.T.=0.39;Real Estate (Development)=0.48;"
    "Real Estate (General/Diversified)=0.58;Real Estate (Operations & Services)=0.81;Recreation=0.70;"
    "Reinsurance=0.44;Restaurant/Dining=0.77;Retail (Automotive)=0.70;Retail (Building Supply)=1.31;"
    "Retail (Distributors)=0.78;Retail (General)=0.76;Retail (Grocery and Food)=0.80;"
    "Retail (REITs)=0.44;Retail (Special Lines)=0.95;Rubber& Tires=0.14;Semiconductor=1.49;"
    "Semiconductor Equip=1.35;Shipbuilding & Marine=0.64;Shoe=0.93;Software (Entertainment)=1.01;"
    "Software (Internet)=1.55;Software (System & Application)=1.23;Steel=0.90;Telecom (Wireless)=0.39;"
    "Telecom. Equipment=0.86;Telecom. Services=0.37;Tobacco=0.68;Transportation=0.68;"
    "Transportation (Railroads)=0.81;Trucking=0.85;Utility (General)=0.15;Utility (Water)=0.28;"
    "Total Market=0.72;Total Market (without financials)=0.88"
)

SNAP_SPREAD = 1.11  # % Baa2/BBB, large non-financial service firms
SNAP_SPREAD_ASOF = "January 2026 (snapshot read 16 Nov 2026)"

# OECD combined statutory CIT rate (%), latest year available per jurisdiction.
SNAP_TAX_ASOF = "2026 rates; 2025 for TUR, ISR, COL (snapshot read 16 Nov 2026)"
SNAP_TAX_YEAR_EXC = {"TUR": 2025, "ISR": 2025, "COL": 2025}
SNAP_TAX = (
    "BEN:30,COD:30,GAB:30,HTI:30,KEN:30,MSR:30,NGA:30,PNG:30,LCA:30,SEN:30,LKA:30,TTO:30,ZMB:30,"
    "AUS:30,CRI:30,MEX:30,HND:25,BEL:25,ESP:25,TUR:25,GBR:25,AGO:25,ATG:25,CHN:25,CIV:25,DJI:25,"
    "DMA:25,FJI:25,JAM:25,LBR:25,MRT:25,MCO:25,MNG:25,PAN:25,PHL:25,SYC:25,SLE:25,URY:25,SWZ:25,"
    "GTM:25,KNA:25,AND:10,ARM:18,ABW:22,BRB:9,BIH:10,BWA:22,BRA:34,BRN:18.5,BGR:10,BFA:27.5,"
    "CPV:20.4,CMR:33,COG:28,HRV:18,DOM:27,EGY:22.5,FRO:18,GRL:26.5,GRD:28,HKG:16.5,IND:25.17,"
    "IDN:22,LIE:12.5,MAC:12,MYS:24,MDA:12,MAR:35,NAM:32,MKD:10,PAK:29,PRY:10,PER:29.5,QAT:10,"
    "ROU:16,VCT:28,WSM:27,SMR:18,SGP:17,ZAF:27,TGO:27,UKR:18,ARE:9,AUT:23,CAN:26,CHL:27,CZE:21,"
    "FRA:36.13,DEU:30.133,HUN:9,ISL:20,IRL:12.5,ISR:23,ITA:27.81,JPN:29.74,KOR:27.5,LTU:17,"
    "LUX:23.87,NLD:25.8,PRT:29.5,SVK:24,SWE:20.6,CHE:19.4719,USA:25.5285,GIB:15,POL:19,DNK:22,"
    "EST:22,GRC:22,NOR:22,SVN:22,NZL:28,ALB:15,CUW:15,GEO:15,KWT:15,MDV:15,MUS:15,MNE:15,OMN:15,"
    "SRB:15,TUN:20,UZB:15,ARG:35,MLT:35,COL:35,AZE:20,COK:20,JOR:20,KAZ:20,SAU:20,THA:20,VNM:20,"
    "FIN:20,LVA:20,AIA:0,BHS:0,BHR:0,GGY:0,BLZ:0,BMU:0,VGB:0,CYM:0,IMN:0,JEY:0,TCA:0"
)

# Trading Economics 10Y yields (%), read from tradingeconomics.com/bonds on 16 Nov 2026.
SNAP_YIELDS_ASOF = "16 Nov 2026 (snapshot)"
SNAP_YIELDS = (
    "United States=5.1120;United Kingdom=5.3523;Japan=2.8880;Australia=5.1090;Germany=3.3766;"
    "Brazil=15.3250;Russia=16.7400;India=7.3180;Canada=3.8090;Italy=4.4490;France=4.9410;"
    "South Africa=8.7200;China=1.6331;Switzerland=0.5760;Mexico=9.3080;Netherlands=3.4710;"
    "New Zealand=4.7740;Portugal=3.8210;South Korea=3.9860;Spain=3.9500;Greece=4.2910;"
    "Turkey=36.4750;Finland=3.7570;Lithuania=4.3420;Norway=4.3910;Poland=6.3190;Romania=7.1600;"
    "Slovakia=4.3000;Slovenia=3.9450;Sweden=3.1000;Hungary=5.5250;Iceland=6.8100;Ireland=3.5150;"
    "Austria=3.6200;Belgium=4.3760;Croatia=3.8668;Czech Republic=5.2580;Denmark=3.1690;"
    "Peru=6.2414;Chile=6.0100;Colombia=12.6980;Singapore=2.3429;Taiwan=1.8700;Thailand=1.9830;"
    "Vietnam=4.5730;Hong Kong=3.9960;Indonesia=7.6070;Israel=4.1310;Malaysia=3.8654;"
    "Pakistan=12.6220;Philippines=7.7030;Zambia=14.7400;Kenya=12.5000;Nigeria=16.5980"
)


# --------------------------------------------------------------------------- #
# THE MODEL - verify these formulas against the class handout
# --------------------------------------------------------------------------- #
def compute(beta_u, tax, debt_share, erp, y_us, y_fc, spread_usd, spread_fc_override=None):
    """All inputs are decimals (0.065 = 6.5%). Returns a dict of decimals.

    Shared across both currencies: unlevered beta, tax rate, debt share, ERP.

      D/E            = d / (1 - d)
      Levered beta   = beta_U * [1 + (1 - t) * D/E]

      USD
        Cost of equity = y_US + beta_L * ERP
        Cost of debt   = y_US + BBB spread (USD)
        WACC           = (1 - d) * Ke + d * Kd * (1 - t)

      Foreign currency (FC)
        Cost of equity = y_FC + beta_L * ERP
        BBB spread FC  = BBB spread USD * (1 + y_FC) / (1 + y_US)   [auto]
                         ...or the manual override
        Cost of debt   = y_FC + BBB spread FC
        WACC           = (1 - d) * Ke + d * Kd * (1 - t)
    """
    d = debt_share
    de = d / (1.0 - d)
    beta_l = beta_u * (1.0 + (1.0 - tax) * de)

    ke_usd = y_us + beta_l * erp
    kd_usd = y_us + spread_usd
    wacc_usd = (1.0 - d) * ke_usd + d * kd_usd * (1.0 - tax)

    spread_fc_auto = spread_usd * (1.0 + y_fc) / (1.0 + y_us)
    spread_fc = spread_fc_auto if spread_fc_override is None else spread_fc_override
    ke_fc = y_fc + beta_l * erp
    kd_fc = y_fc + spread_fc
    wacc_fc = (1.0 - d) * ke_fc + d * kd_fc * (1.0 - tax)

    return dict(
        de=de, beta_l=beta_l,
        ke_usd=ke_usd, kd_usd=kd_usd, kd_usd_at=kd_usd * (1 - tax), wacc_usd=wacc_usd,
        spread_fc_auto=spread_fc_auto, spread_fc=spread_fc,
        ke_fc=ke_fc, kd_fc=kd_fc, kd_fc_at=kd_fc * (1 - tax), wacc_fc=wacc_fc,
    )


# --------------------------------------------------------------------------- #
# Parsers (pure functions so they can be tested without a network)
# --------------------------------------------------------------------------- #
def _clean(x) -> str:
    return re.sub(r"\s+", " ", str(x)).strip()


def _to_float(x):
    try:
        return float(str(x).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_betas_xls(content: bytes):
    """Find the 'Industry Name' header row and the exact 'Unlevered beta' column."""
    sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)
    names = sorted(sheets, key=lambda s: 0 if "industry" in s.lower() else 1)
    for name in names:
        raw = sheets[name]
        as_of = None
        for i in range(min(len(raw), 40)):
            row = [_clean(v).lower() for v in raw.iloc[i].tolist()]
            if as_of is None:
                for j, v in enumerate(row):
                    if v.startswith("date updated"):
                        rest = [x for x in raw.iloc[i].tolist()[j + 1:] if pd.notna(x)]
                        if rest:
                            val = rest[0]
                            as_of = val.strftime("%d %b %Y") if hasattr(val, "strftime") else _clean(val)
            if "industry name" in row and "unlevered beta" in row:
                ci, cb = row.index("industry name"), row.index("unlevered beta")
                body = raw.iloc[i + 1:, [ci, cb]].copy()
                body.columns = ["Industry", "Unlevered beta"]
                body["Industry"] = body["Industry"].map(_clean)
                body["Unlevered beta"] = pd.to_numeric(body["Unlevered beta"], errors="coerce")
                body = body.dropna(subset=["Unlevered beta"])
                body = body[~body["Industry"].isin(["", "nan"])]
                if len(body) >= 20:
                    return body.reset_index(drop=True), as_of
    raise ValueError("Could not find 'Industry Name' / 'Unlevered beta' columns in betas.xls")


def _html_as_of(text: str):
    m = re.search(r"Data used is as of\s+([A-Za-z]+\s+\d{4})", text)
    return m.group(1) if m else None


def parse_betas_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        rows = [[_clean(c.get_text()) for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]
        rows = [r for r in rows if r]
        if not rows:
            continue
        head = [h.lower() for h in rows[0]]
        if "industry name" in head and "unlevered beta" in head:
            ci, cb = head.index("industry name"), head.index("unlevered beta")
            data = [(r[ci], _to_float(r[cb])) for r in rows[1:] if len(r) > max(ci, cb)]
            df = pd.DataFrame([d for d in data if d[0] and d[1] is not None],
                              columns=["Industry", "Unlevered beta"])
            if len(df) >= 20:
                return df, _html_as_of(soup.get_text(" "))
    raise ValueError("Could not find the betas table in Betas.html")


def parse_ratings_html(html: str):
    """First Baa2/BBB in a row = the 'large non-financial service firms' block (left side)."""
    soup = BeautifulSoup(html, "html.parser")
    for tr in soup.find_all("tr"):
        cells = [_clean(c.get_text()) for c in tr.find_all(["td", "th"])]
        if "Baa2/BBB" in cells:
            i = cells.index("Baa2/BBB")
            val = _to_float(cells[i + 1]) if i + 1 < len(cells) else None
            if val is not None:
                return val, _html_as_of(soup.get_text(" "))
    raise ValueError("Could not find the Baa2/BBB row in ratings.html")


def parse_oecd_csv(text: str):
    """Combined (central + sub-central) statutory CIT rate, latest year per jurisdiction."""
    df = pd.read_csv(io.StringIO(text))
    df = df[(df["MEASURE"] == "CIT_C") & (df["TARGETING"] == "ST")].dropna(subset=["OBS_VALUE"])
    if df.empty:
        raise ValueError("OECD response had no combined statutory CIT rates")
    df = df.sort_values("TIME_PERIOD").groupby("REF_AREA", as_index=False).tail(1)
    out = pd.DataFrame({
        "iso3": df["REF_AREA"].values,
        "oecd_name": df["Reference area"].values,
        "rate": df["OBS_VALUE"].astype(float).values,
        "year": df["TIME_PERIOD"].astype(int).values,
    })
    return out.reset_index(drop=True)


def parse_te_html(html: str):
    """Rows look like <tr data-symbol=...><td><a><b>Country</b></a></td><td id="p">5.11</td>...<td id="date">."""
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for tr in soup.find_all("tr", attrs={"data-symbol": True}):
        a, p, d = tr.find("a"), tr.find("td", id="p"), tr.find("td", id="date")
        val = _to_float(p.get_text()) if p else None
        if a and val is not None:
            name = _clean(a.get_text())
            if name and name not in out:
                out[name] = (val, _clean(d.get_text()) if d else "")
    if "United States" not in out or len(out) < 5:
        raise ValueError("No yield table in the Trading Economics response")
    return out


# --------------------------------------------------------------------------- #
# Fetchers
# --------------------------------------------------------------------------- #
def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _get(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r


def _kv(s, sep=";", eq="="):
    return {k: float(v) for k, v in (item.rsplit(eq, 1) for item in s.split(sep))}


def fetch_betas():
    errors = []
    for url, parser, binary in ((BETAS_XLS_URL, parse_betas_xls, True),
                                (BETAS_HTML_URL, parse_betas_html, False)):
        try:
            r = _get(url)
            df, as_of = parser(r.content if binary else r.text)
            return dict(df=df, status="Live", url=url, fetched=_now(), error=None,
                        as_of=as_of or r.headers.get("Last-Modified", "see source"))
        except Exception as e:  # noqa: BLE001 - any failure -> next option
            errors.append(f"{url.rsplit('/', 1)[-1]}: {e}")
    snap = _kv(SNAP_BETAS)
    df = pd.DataFrame({"Industry": list(snap), "Unlevered beta": list(snap.values())})
    return dict(df=df, status="Snapshot", url=BETAS_XLS_URL, fetched=_now(),
                as_of=SNAP_BETAS_ASOF, error=" | ".join(errors))


def fetch_spread():
    try:
        val, as_of = parse_ratings_html(_get(RATINGS_URL).text)
        return dict(value=val, status="Live", url=RATINGS_URL, fetched=_now(),
                    as_of=as_of or "see source", error=None)
    except Exception as e:  # noqa: BLE001
        return dict(value=SNAP_SPREAD, status="Snapshot", url=RATINGS_URL, fetched=_now(),
                    as_of=SNAP_SPREAD_ASOF, error=str(e))


def fetch_tax():
    try:
        url = OECD_SDMX_URL.format(start=datetime.now().year - 2)
        df = parse_oecd_csv(_get(url).text)
        yrs = df["year"]
        return dict(df=df, status="Live", url=url, fetched=_now(), error=None,
                    as_of=f"latest year per country ({yrs.min()}-{yrs.max()})")
    except Exception as e:  # noqa: BLE001
        snap = _kv(SNAP_TAX, sep=",", eq=":")
        df = pd.DataFrame({"iso3": list(snap), "oecd_name": list(snap), "rate": list(snap.values()),
                           "year": [SNAP_TAX_YEAR_EXC.get(k, 2026) for k in snap]})
        return dict(df=df, status="Snapshot", url=OECD_REPORT_URL, fetched=_now(),
                    as_of=SNAP_TAX_ASOF, error=str(e))


def fetch_yields():
    errors = []
    # Plain GETs only. Trading Economics sits behind a bot challenge; if it does not
    # hand us the table we fall back to the snapshot rather than work around it.
    for url in (TE_URL, TE_URL + "?partial=markets"):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            data = parse_te_html(r.text)
            return dict(data=data, status="Live", url=TE_URL, fetched=_now(), error=None,
                        as_of="quote date shown per country")
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
    data = {k: (v, SNAP_YIELDS_ASOF) for k, v in _kv(SNAP_YIELDS).items()}
    return dict(data=data, status="Snapshot", url=TE_URL, fetched=_now(),
                as_of=SNAP_YIELDS_ASOF, error=" | ".join(errors))


@st.cache_data(ttl=6 * 3600, show_spinner="Fetching the latest data... WHO DEY!")
def load_data():
    return dict(betas=fetch_betas(), spread=fetch_spread(), tax=fetch_tax(), yields=fetch_yields())


def tax_lookup(tax_df: pd.DataFrame, country: str):
    """Return (rate %, year) or (None, None)."""
    iso = COUNTRIES.get(country, (None, None))[0]
    hit = tax_df[tax_df["iso3"] == iso] if iso else tax_df.iloc[0:0]
    if hit.empty:
        key = country.lower()
        hit = tax_df[tax_df["oecd_name"].astype(str).str.lower() == key]
    if hit.empty:
        return None, None
    return float(hit["rate"].iloc[0]), int(hit["year"].iloc[0])


# --------------------------------------------------------------------------- #
# Page + theme
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="WHO DEY WACC | International Cost of Capital",
                   page_icon="🐅", layout="wide")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@500;700&display=swap');
h1, h2, h3, .jungle-title, .card-title, [data-testid="stMetricValue"] {{
    font-family: 'Oswald', 'Arial Narrow', sans-serif !important; letter-spacing: .5px;
}}
.stripes {{
    height: 14px; border-radius: 3px; margin: 0 0 10px 0;
    background: repeating-linear-gradient(115deg, {ORANGE} 0 26px, {BLACK} 26px 38px,
                {ORANGE} 38px 52px, {BLACK} 52px 58px);
}}
.jungle-banner {{
    background: {BLACK}; color: {WHITE}; padding: 22px 28px; border-radius: 10px;
    border-left: 12px solid {ORANGE}; border-right: 12px solid {ORANGE}; margin-bottom: 8px;
}}
.jungle-title {{ font-size: 2.6rem; font-weight: 700; line-height: 1.05; text-transform: uppercase; }}
.jungle-title span {{ color: {ORANGE}; }}
.jungle-sub {{ color: #d9d9d9; margin-top: 6px; font-size: 1.0rem; }}
.jungle-tags {{ color: {ORANGE}; font-weight: 700; margin-top: 8px; letter-spacing: 1px; }}
.card {{
    background: {BLACK}; color: {WHITE}; border-radius: 10px; padding: 16px 20px;
    border-top: 8px solid {ORANGE}; height: 100%;
}}
.card.alt {{ background: {ORANGE}; border-top: 8px solid {BLACK}; }}
.card-title {{ font-size: 1.35rem; text-transform: uppercase; margin-bottom: 8px; }}
.card table {{ width: 100%; border-collapse: collapse; }}
.card td {{ padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,.25); font-size: 1.02rem; }}
.card td:last-child {{ text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; }}
.card .big td {{ font-size: 1.45rem; border-bottom: none; padding-top: 10px;
                 font-family: 'Oswald', sans-serif; }}
section[data-testid="stSidebar"] {{ background: {BLACK}; border-right: 6px solid {ORANGE}; }}
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3, section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] small {{ color: {WHITE} !important; }}
section[data-testid="stSidebar"] input, section[data-testid="stSidebar"] div[data-baseweb="select"] span,
section[data-testid="stSidebar"] div[data-baseweb="select"] div {{ color: {BLACK} !important; }}
section[data-testid="stSidebar"] summary span, section[data-testid="stSidebar"] summary p {{ color: {ORANGE} !important; }}
section[data-testid="stSidebar"] details {{ border: 1px solid {ORANGE}; }}
.stButton > button, .stDownloadButton > button {{
    background: {ORANGE}; color: {BLACK}; border: 2px solid {BLACK}; font-weight: 700;
    text-transform: uppercase; letter-spacing: .5px;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
    background: {BLACK}; color: {ORANGE}; border-color: {ORANGE};
}}
section[data-testid="stSidebar"] .stButton > button p {{ color: {BLACK} !important; }}
section[data-testid="stSidebar"] .stButton > button:hover p {{ color: {ORANGE} !important; }}
h2, h3 {{ border-bottom: 4px solid {ORANGE}; padding-bottom: 4px; text-transform: uppercase; }}
.foot {{ color: #666; font-size: .8rem; margin-top: 30px; }}
</style>
<div class="stripes"></div>
<div class="jungle-banner">
  <div class="jungle-title">WHO DEY <span>WACC</span></div>
  <div class="jungle-sub">International Cost of Capital &mdash; USD vs. local currency, side by side.
       Who dey think gonna beat that hurdle rate?</div>
  <div class="jungle-tags">#WHODEY &nbsp;&bull;&nbsp; #RULETHEJUNGLE &nbsp;&bull;&nbsp; SEIZE THE DEY 🐅</div>
</div>
<div class="stripes"></div>
""", unsafe_allow_html=True)

data = load_data()
betas_df = data["betas"]["df"]
tax_df = data["tax"]["df"]
yields = {k: v for k, v in data["yields"]["data"].items() if k not in NOT_COUNTRIES}

industries = betas_df["Industry"].tolist()
countries = sorted(yields, key=lambda c: (c != DEFAULT_COUNTRY, c))

# --------------------------------------------------------------------------- #
# Sidebar - the playbook
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("## 🐅 The Playbook")
    if st.button("🔄 Refresh data", width="stretch",
                 help="Clears the cache and re-fetches all four sources."):
        load_data.clear()
        st.rerun()

    industry = st.selectbox(
        "Industry", industries,
        index=industries.index(DEFAULT_INDUSTRY) if DEFAULT_INDUSTRY in industries else 0)
    country = st.selectbox("Target country", countries, index=0)
    is_us = country == DEFAULT_COUNTRY
    ccy = COUNTRIES.get(country, (None, "local currency"))[1]
    fc_label = "USD (selected country = U.S.)" if is_us else f"{ccy} ({country})"

    erp_pct = st.number_input("Equity risk premium (%)", 0.0, 30.0, DEFAULT_ERP, 0.25, format="%.2f")
    debt_pct = st.slider("Target debt share, D/(D+E) (%)", 0.0, 95.0, DEFAULT_DEBT, 1.0)

    tax_choice = st.radio(
        "Project tax rate - switch", ["U.S.", "Selected country"],
        index=0, horizontal=True,
        format_func=lambda o: o if (o == "U.S." or is_us) else country,
        help="One tax rate is applied to BOTH currencies (beta levering and the debt tax shield).")
    use_us_tax = tax_choice == "U.S."

    # ---- fetched values (percent units) ----
    f_beta = float(betas_df.loc[betas_df["Industry"] == industry, "Unlevered beta"].iloc[0])
    f_spread = float(data["spread"]["value"])
    f_y_us, f_y_us_date = yields[DEFAULT_COUNTRY]
    f_y_fc, f_y_fc_date = yields[country]
    f_tax_us, f_tax_us_year = tax_lookup(tax_df, DEFAULT_COUNTRY)
    f_tax_fc, f_tax_fc_year = tax_lookup(tax_df, country)

    st.markdown("### ✍️ Manual overrides")
    st.caption("Tick a box to replace a fetched value with your own.")

    def override(label, fetched, key, step, fmt="%.2f", lo=0.0, hi=100.0):
        on = st.checkbox(f"Override {label}", key=f"on_{key}")
        if on:
            start = fetched if fetched is not None else 0.0
            return st.number_input(label, lo, hi, float(start), step, format=fmt, key=f"v_{key}"), True
        return fetched, False

    with st.expander("Open overrides", expanded=False):
        beta_u, m_beta = override("unlevered beta", f_beta, "beta", 0.01, lo=0.0, hi=5.0)
        tax_us_pct, m_tax_us = override("U.S. corporate tax rate (%)", f_tax_us, "taxus", 0.25)
        if is_us:
            tax_fc_pct, m_tax_fc = tax_us_pct, m_tax_us
        else:
            tax_fc_pct, m_tax_fc = override(f"{country} corporate tax rate (%)", f_tax_fc, "taxfc", 0.25)
        spread_pct, m_spread = override("USD BBB spread (%)", f_spread, "spread", 0.05)
        y_us_pct, m_y_us = override("U.S. 10Y yield (%)", f_y_us, "yus", 0.05, fmt="%.4f", lo=-5.0)
        if is_us:
            y_fc_pct, m_y_fc = y_us_pct, m_y_us
        else:
            y_fc_pct, m_y_fc = override(f"{country} 10Y yield (%)", f_y_fc, "yfc", 0.05, fmt="%.4f", lo=-5.0)

        spread_fc_on = st.toggle(f"Manual {ccy} BBB spread", value=False,
                                 help="Off = auto: USD spread x (1 + y_FC) / (1 + y_US)")
        auto_fc_spread = spread_pct * (1 + y_fc_pct / 100) / (1 + y_us_pct / 100)
        if spread_fc_on:
            spread_fc_pct = st.number_input(f"{ccy} BBB spread (%)", 0.0, 100.0,
                                            float(round(auto_fc_spread, 4)), 0.05, format="%.4f")
        else:
            spread_fc_pct = None
            st.caption(f"Auto {ccy} BBB spread: **{auto_fc_spread:.4f}%**")

# ---- project tax rate ----
tax_note = None
if use_us_tax:
    tax_pct, tax_src = tax_us_pct, "U.S."
else:
    tax_pct, tax_src = tax_fc_pct, country
if tax_pct is None:
    tax_note = (f"OECD has no statutory rate for **{tax_src}**. Using the U.S. rate instead - "
                f"tick *Override {tax_src} corporate tax rate* in the sidebar to enter one.")
    tax_pct, tax_src = tax_us_pct, "U.S. (fallback)"
if tax_pct is None:
    st.error("No U.S. tax rate available. Enter one under Manual overrides.")
    st.stop()

res = compute(beta_u, tax_pct / 100, debt_pct / 100, erp_pct / 100, y_us_pct / 100, y_fc_pct / 100,
              spread_pct / 100, None if spread_fc_pct is None else spread_fc_pct / 100)

# --------------------------------------------------------------------------- #
# Data status
# --------------------------------------------------------------------------- #
snap = [k for k in ("betas", "spread", "tax", "yields") if data[k]["status"] != "Live"]
if snap:
    labels = {"betas": "Damodaran betas", "spread": "Damodaran BBB spread",
              "tax": "OECD tax rates", "yields": "Trading Economics yields"}
    st.warning(
        "**Using a dated snapshot for: " + ", ".join(labels[k] for k in snap) + ".** "
        "The live fetch did not return data (the site may be blocking automated requests). "
        "Hit *Refresh data* to retry, or enter current values under *Manual overrides*.")
if tax_note:
    st.warning(tax_note)

# --------------------------------------------------------------------------- #
# Scoreboard - side by side
# --------------------------------------------------------------------------- #
def pct(x, n=2):
    return f"{x * 100:.{n}f}%"


st.markdown(f"## 🏈 The Scoreboard &mdash; {industry}")

def card(title, cls, rf, ke, sp, kd, kd_at, wacc):
    return f"""<div class="card {cls}"><div class="card-title">{title}</div><table>
    <tr><td>10Y government yield (risk-free)</td><td>{pct(rf, 4)}</td></tr>
    <tr><td>Cost of equity</td><td>{pct(ke)}</td></tr>
    <tr><td>BBB spread</td><td>{pct(sp, 4)}</td></tr>
    <tr><td>Cost of debt (pre-tax)</td><td>{pct(kd)}</td></tr>
    <tr><td>Cost of debt (after-tax)</td><td>{pct(kd_at)}</td></tr>
    <tr class="big"><td>WACC</td><td>{pct(wacc)}</td></tr></table></div>"""

c1, c2 = st.columns(2)
c1.markdown(card("🇺🇸 USD", "", y_us_pct / 100, res["ke_usd"], spread_pct / 100,
                 res["kd_usd"], res["kd_usd_at"], res["wacc_usd"]), unsafe_allow_html=True)
c2.markdown(card(f"🌍 {fc_label}", "alt", y_fc_pct / 100, res["ke_fc"], res["spread_fc"],
                 res["kd_fc"], res["kd_fc_at"], res["wacc_fc"]), unsafe_allow_html=True)

st.write("")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Unlevered beta", f"{beta_u:.2f}")
m2.metric("Levered beta", f"{res['beta_l']:.3f}")
m3.metric("Debt / Equity", f"{res['de']:.3f}")
m4.metric(f"Project tax rate ({tax_src})", f"{tax_pct:.2f}%")
m5.metric("WACC gap (selected - USD)" if is_us else f"WACC gap ({ccy} - USD)", f"{(res['wacc_fc'] - res['wacc_usd']) * 100:+.2f} pp")

results_df = pd.DataFrame({
    "Metric": ["10Y government yield", "Cost of equity", "BBB spread", "Cost of debt (pre-tax)",
               "Cost of debt (after-tax)", "WACC"],
    "USD (%)": [y_us_pct, res["ke_usd"] * 100, spread_pct, res["kd_usd"] * 100,
                res["kd_usd_at"] * 100, res["wacc_usd"] * 100],
    f"{ccy} (%)": [y_fc_pct, res["ke_fc"] * 100, res["spread_fc"] * 100, res["kd_fc"] * 100,
                   res["kd_fc_at"] * 100, res["wacc_fc"] * 100],
})
results_df["Difference (pp)"] = results_df[f"{ccy} (%)"] - results_df["USD (%)"]


def origin(manual, key):
    return "Manual override" if manual else data[key]["status"]


inputs_df = pd.DataFrame([
    ["Industry", industry, "Selection", "", ""],
    ["Target country", country, "Selection", "", ""],
    ["Unlevered beta", f"{beta_u:.4f}", origin(m_beta, "betas"), data["betas"]["url"], data["betas"]["as_of"]],
    ["Equity risk premium (%)", f"{erp_pct:.2f}", "User input", "", ""],
    ["Target debt share (%)", f"{debt_pct:.2f}", "User input", "", ""],
    ["U.S. corporate tax rate (%)", "n/a" if tax_us_pct is None else f"{tax_us_pct:.4f}",
     origin(m_tax_us, "tax"), data["tax"]["url"], f"{f_tax_us_year or ''}"],
    [f"{country} corporate tax rate (%)", "n/a" if tax_fc_pct is None else f"{tax_fc_pct:.4f}",
     origin(m_tax_fc, "tax"), data["tax"]["url"], f"{f_tax_fc_year or ''}"],
    ["Project tax rate used (%)", f"{tax_pct:.4f}", tax_src, "", ""],
    ["USD BBB spread (%)", f"{spread_pct:.4f}", origin(m_spread, "spread"), data["spread"]["url"], data["spread"]["as_of"]],
    [f"{ccy} BBB spread (%)", f"{res['spread_fc'] * 100:.4f}",
     "Manual override" if spread_fc_pct is not None else "Auto-calculated", "", ""],
    ["U.S. 10Y yield (%)", f"{y_us_pct:.4f}", origin(m_y_us, "yields"), data["yields"]["url"], f_y_us_date],
    [f"{country} 10Y yield (%)", f"{y_fc_pct:.4f}", origin(m_y_fc, "yields"), data["yields"]["url"], f_y_fc_date],
], columns=["Input", "Value", "Origin", "Source", "As of"])

sources_df = pd.DataFrame([
    ["Industry unlevered betas", "Aswath Damodaran (NYU Stern)", data["betas"]["url"],
     data["betas"]["as_of"], data["betas"]["fetched"], data["betas"]["status"]],
    ["BBB (Baa2/BBB) spread, large non-financial firms", "Aswath Damodaran (NYU Stern)",
     data["spread"]["url"], data["spread"]["as_of"], data["spread"]["fetched"], data["spread"]["status"]],
    ["Combined statutory corporate income tax rates", "OECD Corporate Tax Statistics",
     data["tax"]["url"], data["tax"]["as_of"], data["tax"]["fetched"], data["tax"]["status"]],
    ["10-year government bond yields", "Trading Economics", data["yields"]["url"],
     data["yields"]["as_of"], data["yields"]["fetched"], data["yields"]["status"]],
], columns=["Data", "Provider", "URL", "Data as of", "Fetched", "Status"])

# --------------------------------------------------------------------------- #
# All-industry comparison
# --------------------------------------------------------------------------- #
def all_industries():
    rows = []
    for ind, b in zip(betas_df["Industry"], betas_df["Unlevered beta"]):
        b = beta_u if ind == industry else float(b)   # honour the override for the selected industry
        r = compute(b, tax_pct / 100, debt_pct / 100, erp_pct / 100, y_us_pct / 100, y_fc_pct / 100,
                    spread_pct / 100, None if spread_fc_pct is None else spread_fc_pct / 100)
        rows.append({
            "Industry": ind, "Unlevered beta": b, "Levered beta": r["beta_l"],
            "Cost of equity USD (%)": r["ke_usd"] * 100, "Cost of debt USD (%)": r["kd_usd"] * 100,
            "WACC USD (%)": r["wacc_usd"] * 100,
            f"Cost of equity {ccy} (%)": r["ke_fc"] * 100, f"Cost of debt {ccy} (%)": r["kd_fc"] * 100,
            f"WACC {ccy} (%)": r["wacc_fc"] * 100,
        })
    return pd.DataFrame(rows)


all_df = all_industries()

tab_cmp, tab_assume, tab_check, tab_src, tab_dl = st.tabs(
    ["📊 All industries", "📋 Assumptions", "✅ Verification", "🔗 Sources & dates", "⬇️ Downloads"])

with tab_cmp:
    st.markdown("### The whole league")
    st.caption("Every Damodaran industry under the same tax rate, debt share, ERP, yields and spreads. "
               "Your selected industry is in orange.")
    metric_opts = ["WACC USD (%)", f"WACC {ccy} (%)", "Cost of equity USD (%)", f"Cost of equity {ccy} (%)"]
    metric_opts = list(dict.fromkeys(metric_opts))
    metric = st.selectbox("Rank by", metric_opts, index=0)
    chart_df = all_df.assign(Selected=all_df["Industry"] == industry)
    chart = (
        alt.Chart(chart_df)
        .mark_bar()
        .encode(
            y=alt.Y("Industry:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X(f"{metric}:Q", title=metric),
            color=alt.condition(alt.datum.Selected, alt.value(ORANGE), alt.value(BLACK)),
            tooltip=["Industry", alt.Tooltip("Unlevered beta:Q", format=".2f"),
                     alt.Tooltip("Levered beta:Q", format=".3f"),
                     alt.Tooltip("WACC USD (%):Q", format=".2f"),
                     alt.Tooltip(f"WACC {ccy} (%):Q", format=".2f")],
        )
        .properties(height=max(400, 16 * len(chart_df)))
    )
    st.altair_chart(chart, width="stretch")
    st.dataframe(all_df.sort_values(metric, ascending=False).style.format(
        {c: "{:.2f}" for c in all_df.columns if c != "Industry"} | {"Levered beta": "{:.3f}"}),
        width="stretch", hide_index=True)

with tab_assume:
    st.markdown("### How the numbers are built")
    st.markdown(f"""
**Shared across both currencies:** unlevered beta, project tax rate ({tax_src}: {tax_pct:.2f}%),
debt share ({debt_pct:.0f}%) and equity risk premium ({erp_pct:.2f}%).
Only the 10-year government yield and the BBB spread differ by currency.

| Step | Formula |
|---|---|
| Debt/equity | `D/E = d / (1 - d)` |
| Levered beta | `beta_L = beta_U x [1 + (1 - t) x D/E]` |
| Cost of equity (each currency) | `Ke = 10Y yield + beta_L x ERP` |
| USD cost of debt | `Kd = U.S. 10Y yield + USD BBB spread` |
| {ccy} BBB spread (auto) | `USD spread x (1 + y_{ccy}) / (1 + y_US)` |
| {ccy} cost of debt | `Kd = {country} 10Y yield + {ccy} BBB spread` |
| WACC (each currency) | `(1 - d) x Ke + d x Kd x (1 - t)` |

**Main assumptions**
- The 10-year government yield stands in for the risk-free rate in each currency. For countries with
  sovereign default risk the local yield embeds a default premium, so local-currency figures are upper bounds.
- The industry beta is Damodaran's **U.S.** unlevered beta ("Unlevered beta" column, not the
  cash-corrected one). It is applied unchanged to the foreign project.
- The equity risk premium is the same number in both currencies (per the assignment).
- The auto {ccy} spread scales the USD spread by relative yields, which keeps the USD and {ccy}
  cost of debt consistent with interest-rate parity. Switch on the manual toggle to replace it.
- Tax rates are the OECD **combined** statutory rate (central + sub-central). For the U.S. that is the
  21% federal rate plus average state taxes; override it if your class uses 21%.
- The project is financed at a constant target debt share and borrows at a BBB rating.
""")
    st.markdown("### Inputs in use")
    st.dataframe(inputs_df, width="stretch", hide_index=True)

with tab_check:
    st.markdown("### Film review: check the tape")
    st.caption("These tests re-run the model live on your current inputs.")
    base = dict(beta_u=beta_u, tax=tax_pct / 100, debt_share=debt_pct / 100, erp=erp_pct / 100,
                y_us=y_us_pct / 100, spread_usd=spread_pct / 100)
    tol = 1e-12
    t1 = compute(y_fc=y_us_pct / 100, **base)
    ok1 = all(abs(t1[a] - t1[b]) < tol for a, b in
              (("ke_usd", "ke_fc"), ("kd_usd", "kd_fc"), ("wacc_usd", "wacc_fc")))
    t2 = compute(y_fc=y_fc_pct / 100, **{**base, "debt_share": 0.0})
    ok2 = abs(t2["wacc_usd"] - t2["ke_usd"]) < tol and abs(t2["wacc_fc"] - t2["ke_fc"]) < tol
    t3a = compute(y_fc=y_fc_pct / 100, **base)
    t3b = compute(y_fc=y_fc_pct / 100, spread_fc_override=t3a["spread_fc_auto"] + 0.02, **base)
    ok3 = all(abs(t3a[k] - t3b[k]) < tol for k in ("ke_usd", "kd_usd", "wacc_usd")) and \
        abs(t3a["wacc_fc"] - t3b["wacc_fc"]) > 0 if debt_pct > 0 else \
        all(abs(t3a[k] - t3b[k]) < tol for k in ("ke_usd", "kd_usd", "wacc_usd"))
    for ok, txt in (
        (ok1, "Equal government yields (foreign-spread override off) give identical USD and foreign results"),
        (ok2, "Zero debt makes WACC equal the cost of equity in both currencies"),
        (ok3, "Overriding the foreign-currency spread leaves every USD result unchanged"),
    ):
        (st.success if ok else st.error)(("PASS - " if ok else "FAIL - ") + txt)

    st.markdown("### Hand-check: replicate this in a spreadsheet")
    t, d, e = tax_pct / 100, debt_pct / 100, erp_pct / 100
    st.code(f"""Inputs
  beta_U = {beta_u:.4f}   t = {t:.6f}   d = {d:.4f}   ERP = {e:.4f}
  y_US = {y_us_pct / 100:.6f}   y_{ccy} = {y_fc_pct / 100:.6f}   USD BBB spread = {spread_pct / 100:.6f}

Shared
  D/E    = {d:.4f} / (1 - {d:.4f})                         = {res['de']:.6f}
  beta_L = {beta_u:.4f} x [1 + (1 - {t:.6f}) x {res['de']:.6f}]   = {res['beta_l']:.6f}

USD
  Ke   = {y_us_pct / 100:.6f} + {res['beta_l']:.6f} x {e:.4f}            = {res['ke_usd']:.6f}
  Kd   = {y_us_pct / 100:.6f} + {spread_pct / 100:.6f}                     = {res['kd_usd']:.6f}
  WACC = {1 - d:.4f} x {res['ke_usd']:.6f} + {d:.4f} x {res['kd_usd']:.6f} x (1 - {t:.6f}) = {res['wacc_usd']:.6f}

{ccy}
  Spread = {'manual override' if spread_fc_pct is not None else f"{spread_pct / 100:.6f} x (1 + {y_fc_pct / 100:.6f}) / (1 + {y_us_pct / 100:.6f})"} = {res['spread_fc']:.6f}
  Ke   = {y_fc_pct / 100:.6f} + {res['beta_l']:.6f} x {e:.4f}            = {res['ke_fc']:.6f}
  Kd   = {y_fc_pct / 100:.6f} + {res['spread_fc']:.6f}                     = {res['kd_fc']:.6f}
  WACC = {1 - d:.4f} x {res['ke_fc']:.6f} + {d:.4f} x {res['kd_fc']:.6f} x (1 - {t:.6f}) = {res['wacc_fc']:.6f}
""", language="text")

with tab_src:
    st.markdown("### Sources and dates")
    st.dataframe(sources_df, width="stretch", hide_index=True,
                 column_config={"URL": st.column_config.LinkColumn("URL")})
    st.caption(f"OECD chapter referenced by the assignment: {OECD_REPORT_URL}. That page shows the rates "
               "only as a chart, so the app reads the same OECD Corporate Tax Statistics dataset through "
               "the OECD Data Explorer API, which also carries the most recent year.")
    for k, lab in (("betas", "Betas"), ("spread", "BBB spread"), ("tax", "Tax rates"), ("yields", "Yields")):
        if data[k]["error"]:
            st.caption(f"⚠️ {lab} live fetch failed: {data[k]['error']}")
    with st.expander("All fetched 10Y yields"):
        st.dataframe(pd.DataFrame([(k, v[0], v[1]) for k, v in yields.items()],
                                  columns=["Country", "10Y yield (%)", "Quote date"]),
                     width="stretch", hide_index=True)
    with st.expander("All fetched corporate tax rates"):
        st.dataframe(tax_df.rename(columns={"iso3": "ISO3", "oecd_name": "Jurisdiction",
                                            "rate": "Combined statutory rate (%)", "year": "Year"}),
                     width="stretch", hide_index=True)

with tab_dl:
    st.markdown("### Take it to the house")
    stamp = datetime.now().strftime("%Y%m%d")
    d1, d2, d3 = st.columns(3)
    d1.download_button("Results (CSV)", results_df.to_csv(index=False).encode("utf-8"),
                       f"cost_of_capital_{ccy}_{stamp}.csv", "text/csv", width="stretch")
    d2.download_button("All industries (CSV)", all_df.to_csv(index=False).encode("utf-8"),
                       f"all_industries_{ccy}_{stamp}.csv", "text/csv", width="stretch")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        results_df.to_excel(xw, sheet_name="Results", index=False)
        inputs_df.to_excel(xw, sheet_name="Inputs", index=False)
        all_df.to_excel(xw, sheet_name="All industries", index=False)
        sources_df.to_excel(xw, sheet_name="Sources", index=False)
    d3.download_button("Full workbook (Excel)", buf.getvalue(), f"who_dey_wacc_{ccy}_{stamp}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")
    st.dataframe(results_df.style.format({c: "{:.4f}" for c in results_df.columns if c != "Metric"}),
                 width="stretch", hide_index=True)

st.markdown('<div class="stripes" style="margin-top:24px"></div>'
            '<div class="foot">Fan-themed class project. Not affiliated with, endorsed by, or sponsored by '
            'the Cincinnati Bengals or the NFL. Educational use only; not investment advice.</div>',
            unsafe_allow_html=True)
