#!/usr/bin/env python3
"""WEGWERF-PROBE Mehrjahres-Rückrechnung, Schritt 1 (read-only, nur Zählungen).

Easy-Entscheid 14.11.2026 (open_item ``mehrjahres-rueckrechnung-probe``). Klärt mit
ZAHLEN, ob ein Mehrjahres-Prüffeld (Entwicklung 06/2021–12/2023, Prüfung
01/2024–04/2026, vorläufig) mit freien Daten ehrlich nutzbar ist:

  P1  FINRA Short Interest: ab welchem Stichtag NYSE-/Nasdaq-Werte frei abrufbar
      sind; Felder; Symbolzahl je Stichtag; Lücken; Veröffentlichungsdatum.
  P2  Survivorship: Anteil der damaligen Symbole (Zufallsstichprobe, fester Seed)
      mit heutigen yfinance-Tageskursen über den damaligen Zeitraum, getrennt nach
      Days-to-Cover-Hälfte und Preisklasse.
  P3  Ausstehende Aktien aus SEC XBRL: Deckung, point-in-time über ``filed``.
  P4  Stooq (ohne Key) für delistete Symbole.
  P5  Nähe Proxy-Liste ↔ echte Top-10 ab 01.07.2026 — NUR Zugehörigkeit.
  P6  Splits: sind die FINRA-Stückzahlen roh oder bereinigt?
  P7  Laufzeit-/Datenmengen-Hochrechnung.

BLINDHEIT / TRENNUNG: es wird KEIN Ergebnisfeld berechnet oder gelesen (keine
Rendite, kein Gipfel, keine Kursveränderung nach einem Stichtag). Kurse werden
nur auf Verfügbarkeit, Zeilenzahl, Volumen-Plausibilität und — für die
Proxy-Liste — als Eingaben bis einschließlich Tag D genutzt. Aus den
Backtest-Dateien werden ausschließlich die Schlüssel ``ticker`` und ``date``
gelesen.

Schreibt NUR stdout (``[rueck_probe]``) und ``--out`` (Artifact). Keine
Secrets; SEC-User-Agent ist eine generische Wegwerf-Kennung (.invalid).
Rate-Limit (HTTP 429 / yfinance) → Abbruch (Exit 3) OHNE Teilbefund.
Ab ``PROBE_END`` no-op. Wird nach der Auswertung per Cleanup-PR entfernt.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
import re
import statistics
import sys
import time
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

PROBE_END = date(2026, 12, 31)
SEED = 20261114
YEARS = (2021, 2022, 2023, 2024, 2025)
# Stichprobengröße je Jahr: 95-%-Konfidenzhalbbreite ±2 pp ohne Annahme über den
# Anteil (schlechtester Fall p = 0,5): n = 1,96² · 0,25 / 0,02² = 2 401. Ist die
# Grundgesamtheit kleiner, wird sie vollständig erhoben.
SAMPLE_N = math.ceil(1.96 ** 2 * 0.25 / 0.02 ** 2)
AVAIL_WINDOW_DAYS = 60          # Kalendertage ab Stichtag: „damaliger Zeitraum“
FULL_COVERAGE_FRAC = 0.8        # „voll“ = ≥ 80 % der erwarteten Handelstage
VOL_PLAUS_BAND = (0.2, 5.0)     # yfinance-Ø-Volumen / FINRA-ADV (gleiches Papier?)
SEC_PIT_SUBSAMPLE = 100         # companyfacts-Abrufe je Jahr (filed-Datum prüfen)
STOOQ_CONTROL_N = 10
STOOQ_MISSING_N = 150           # je Jahr 2021 und 2022
SPLIT_EXAMPLES_MAX = 30
PROXY_FROM = date(2026, 7, 1)
PUB_LAG_BUSINESS_DAYS = 8       # ANNAHME FINRA-Kalender (~7 Werktage) + 1 Tag Reserve
YF_BATCH = 100

FINRA_API = "https://api.finra.org/data/group/otcMarket/name/{ds}"
FINRA_META = "https://api.finra.org/metadata/group/otcMarket/name/{ds}"
FINRA_DATASETS = ("consolidatedShortInterest", "ConsolidatedShortInterest",
                  "equityShortInterest", "EquityShortInterest")
FINRA_CATALOG = "https://www.finra.org/finra-data/browse-catalog/equity-short-interest/files"
CNMS_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt"
SEC_UA = "SqueezeReportProbe/1.0 (throwaway contact squeeze-report-rueckrechnung-probe@example.invalid)"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_FRAME = "https://data.sec.gov/api/xbrl/frames/dei/EntityCommonStockSharesOutstanding/shares/CY{y}Q2I.json"
SEC_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
STOOQ_URL = "https://stooq.com/q/d/l/?s={s}.us&d1={a}&d2={b}&i=d"
ANCHORS = ("AAPL", "MSFT", "AMC", "GME", "F", "BAC", "KO", "XOM", "PFE", "T")
NON_COMMON = re.compile(r"\b(ETF|FUND|TRUST|NOTES?|PFD|PREFERRED|WARRANTS?|RIGHTS?|UNITS?|DEP(OSITARY)? SH|ETN)\b", re.I)

FIELD_CANDIDATES = {
    "symbol": ("symbolCode", "issueSymbolIdentifier", "symbol"),
    "date": ("settlementDate",),
    "current": ("currentShortPositionQuantity", "currentShortShareNumber", "currentShortPosition"),
    "previous": ("previousShortPositionQuantity", "previousShortShareNumber", "previousShortPosition"),
    "adv": ("averageDailyVolumeQuantity", "averageDailyShareVolume", "averageDailyVolume"),
    "dtc": ("daysToCoverQuantity", "daysToCover"),
    "name": ("issueName", "securityName"),
    "market": ("marketClassCode", "marketCategoryCode", "marketCode"),
    "split": ("stockSplitFlag", "splitFlag"),
    "revision": ("revisionFlag",),
}


class RateLimited(Exception):
    pass


class Stats:
    def __init__(self):
        self.calls: dict[str, int] = {}
        self.secs: dict[str, float] = {}
        self.bytes: dict[str, int] = {}

    def add(self, src, secs, nbytes=0):
        self.calls[src] = self.calls.get(src, 0) + 1
        self.secs[src] = self.secs.get(src, 0.0) + secs
        self.bytes[src] = self.bytes.get(src, 0) + int(nbytes or 0)

    def as_dict(self):
        return {k: {"aufrufe": self.calls[k], "sekunden": round(self.secs[k], 1),
                    "bytes": self.bytes.get(k, 0)} for k in sorted(self.calls)}


STATS = Stats()
LAST_ERR: dict[str, str] = {}
FALLBACK_USED: dict[str, int] = {}
YF_BATCH_ERRORS: list[str] = []


def log(msg):
    print(f"[rueck_probe] {msg}", flush=True)


CURRENT = {"abschnitt": None}


def start_section(key):
    CURRENT["abschnitt"] = key
    log(f"ABSCHNITT {key} beginnt")


def section_done(result, key):
    """Abschnitt vollständig: Ergebnis sofort ins Log (Befund auch bei späterem Abbruch)."""
    result.setdefault("abschnitte_vollstaendig", []).append(key)
    log(f"ABSCHNITT {key} vollständig " + json.dumps(result.get(key), default=str))


# ── reine Hilfsfunktionen (getestet) ─────────────────────────────────────────
def wilson(k: int, n: int, z: float = 1.96):
    if n <= 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return {"k": k, "n": n, "anteil": round(p, 4),
            "ki95": [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]}


def pick(rec: dict, role: str):
    for k in FIELD_CANDIDATES[role]:
        if k in rec:
            return rec[k]
    return None


def yf_symbol(sym: str) -> str:
    return sym.replace(".", "-").replace("/", "-")


def is_common(name) -> bool:
    return not (isinstance(name, str) and NON_COMMON.search(name))


def draw_sample(population, year: int, n: int = SAMPLE_N) -> list:
    pop = sorted(set(population))
    if len(pop) <= n:
        return pop
    return sorted(random.Random(SEED + year).sample(pop, n))


def dtc_value(rec: dict):
    v = pick(rec, "dtc")
    try:
        if v is not None and math.isfinite(float(v)):
            return float(v)
    except (TypeError, ValueError):
        pass
    cur, adv = pick(rec, "current"), pick(rec, "adv")
    try:
        cur, adv = float(cur), float(adv)
    except (TypeError, ValueError):
        return None
    return cur / adv if adv > 0 else None


def split_halves(values: dict) -> tuple[set, set, float | None]:
    """values: sym → dtc (None erlaubt). Gibt (niedrig, hoch, median)."""
    known = {s: v for s, v in values.items() if v is not None}
    if not known:
        return set(), set(), None
    med = statistics.median(known.values())
    low = {s for s, v in known.items() if v <= med}
    return low, set(known) - low, med


def business_days_after(d: date, n: int, holidays=frozenset()) -> date:
    cur, k = d, 0
    while k < n:
        cur += timedelta(days=1)
        if cur.weekday() < 5 and cur.isoformat() not in holidays:
            k += 1
    return cur


def latest_usable_settlement(d: date, settlements, holidays=frozenset()):
    usable = [s for s in settlements if business_days_after(s, PUB_LAG_BUSINESS_DAYS, holidays) <= d]
    return max(usable) if usable else None


def classify_split(cur0, cur1, prev1, factor):
    """FINRA-Stückzahlen um einen Split zwischen zwei Stichtagen.

    factor = yfinance „Stock Splits“ (neue/alte Stücke, 0,1 = Reverse 1:10).
    Rückgabe: (stueck, vorperiode) mit stueck ∈ {folgt_split, unveraendert,
    unklar} und vorperiode ∈ {unbereinigt, bereinigt, unklar}."""
    try:
        cur0, cur1, prev1, factor = float(cur0), float(cur1), float(prev1), float(factor)
    except (TypeError, ValueError):
        return "unklar", "unklar"
    if cur0 <= 0 or factor <= 0 or 0.67 < factor < 1.5:
        return "unklar", "unklar"
    r = cur1 / cur0
    if 0.8 <= r <= 1.25:
        stueck = "unveraendert"
    elif 0.67 * factor <= r <= 1.5 * factor:
        stueck = "folgt_split"
    else:
        stueck = "unklar"
    if abs(prev1 - cur0) <= 0.01 * cur0:
        vor = "unbereinigt"
    elif abs(prev1 - cur0 * factor) <= 0.05 * cur0 * factor:
        vor = "bereinigt"
    else:
        vor = "unklar"
    return stueck, vor


def overlap_stats(pairs):
    """pairs: list of (real_set, proxy_set) → Kennzahlen der Überschneidung."""
    ov = [len(r & p) for r, p in pairs if r]
    if not ov:
        return None
    dist = {str(k): ov.count(k) for k in range(0, 11)}
    return {"tage": len(ov), "mittel": round(statistics.mean(ov), 2),
            "median": statistics.median(ov), "verteilung": dist}


def gap_pts(open_d, prev_close, close_d):
    try:
        o, pc, c = float(open_d), float(prev_close), float(close_d)
    except (TypeError, ValueError):
        return 0.0
    if not all(map(math.isfinite, (o, pc, c))) or pc <= 0:
        return 0.0
    gap = (o - pc) / pc * 100
    if gap < config.GAP_THRESHOLD_PCT:
        return 0.0
    if c > o + config.GAP_HOLD_FACTOR * (o - pc):
        return float(config.GAP_PTS_STRONG_HOLD)
    if c < pc:
        return float(config.GAP_PTS_FAIL)
    return float(config.GAP_PTS_WEAK_HOLD)


def rs_pts(rs):
    if rs is None or not math.isfinite(rs):
        return 0.0
    t = config.RS_SPY_THRESHOLD_PCT
    return float(round(max(-t, min(t, rs)) / t * config.RS_SPY_PTS_MAX))


def proxy_score(si_pct, dtc, rvol, rel_chg, gap, rs, si_up):
    """Rekonstruierbarer Teil von score() (Fall 2). Float, Turnover, News, KI,
    Squeeze-Malus, Glättung und Boni außerhalb fehlen (Ersatz-Nenner: Aktien)."""
    sf = min(max(si_pct, 0) / 50.0, 1.0) * 32
    sr = min(max(dtc or 0, 0) / 10.0, 1.0) * 23
    rv = min((rvol - 1.0) / 2.0, 1.0) * 23
    mom = min(max(rel_chg, 0) / 8.0, 1.0) * 14
    combo = sum([si_pct >= 30, (dtc or 0) >= 5, rvol >= 2.0, bool(si_up)])
    bonus = float(config.COMBO_BONUS) if combo >= 3 else 0.0
    return round(sf + sr + rv + mom + gap + rs + bonus, 2)


# ── Netz ─────────────────────────────────────────────────────────────────────
def _req():
    import requests
    return requests


def http(method, url, src, **kw):
    t0 = time.monotonic()
    r = _req().request(method, url, timeout=60, **kw)
    STATS.add(src, time.monotonic() - t0, len(r.content or b""))
    if r.status_code == 429:
        raise RateLimited(f"{src} HTTP 429 {url}")
    return r


def finra_query(ds, body, src="finra_api"):
    hdr = {"Accept": "application/json", "Content-Type": "application/json"}
    r = http("POST", FINRA_API.format(ds=ds), src, headers=hdr, data=json.dumps(body))
    time.sleep(0.3)
    if r.status_code != 200:
        LAST_ERR[ds] = f"HTTP {r.status_code}: {r.text[:300]}"
        return r.status_code, [], r.headers
    try:
        data = r.json()
    except ValueError:
        return r.status_code, [], r.headers
    return 200, data if isinstance(data, list) else [], r.headers


def finra_all(ds, filters, page=5000, max_pages=20):
    st, rows = _finra_all(ds, filters, page, max_pages)
    dr = (filters.get("dateRangeFilters") or [None])[0]
    if st not in (200, 429) and not rows and dr and dr["startDate"] == dr["endDate"]:
        # Ersatz: einzelner Stichtag über compareFilters EQUAL (falls dateRange abgelehnt)
        alt = {k: v for k, v in filters.items() if k != "dateRangeFilters"}
        alt["compareFilters"] = [{"compareType": "EQUAL", "fieldName": "settlementDate",
                                  "fieldValue": dr["startDate"]}]
        FALLBACK_USED[ds] = FALLBACK_USED.get(ds, 0) + 1
        st, rows = _finra_all(ds, alt, page, max_pages)
    return st, rows


def _finra_all(ds, filters, page=5000, max_pages=20):
    rows, off = [], 0
    for _ in range(max_pages):
        body = dict(filters, limit=page, offset=off)
        st, data, _ = finra_query(ds, body)
        if st != 200:
            return st, rows
        rows += data
        if len(data) < page:
            return 200, rows
        off += page
    return 200, rows


def date_filter(start, end):
    return {"dateRangeFilters": [{"fieldName": "settlementDate",
                                  "startDate": start.isoformat(), "endDate": end.isoformat()}]}


def cnms_symbols(d: date):
    for back in range(0, 6):
        dd = d - timedelta(days=back)
        r = http("GET", CNMS_URL.format(d=dd.strftime("%Y%m%d")), "finra_cnms")
        if r.status_code == 200 and "|" in r.text:
            syms = set()
            for ln in r.text.splitlines()[1:]:
                parts = ln.split("|")
                if len(parts) >= 2 and parts[1]:
                    syms.add(parts[1].strip())
            return dd, syms
    return None, set()


def sec_get(url):
    r = http("GET", url, "sec", headers={"User-Agent": SEC_UA, "Accept-Encoding": "gzip"})
    time.sleep(0.12)  # < 10 Anfragen/s
    return r


BATCH_ERR = object()   # Abruf-Fehler ≠ „nicht vorhanden“


def yf_download(symbols, start, end, src="yfinance", auto_adjust=True):
    """{yf_symbol: DataFrame|None|BATCH_ERR}. Rate-Limit → RateLimited."""
    import yfinance as yf
    out = {}
    for i in range(0, len(symbols), YF_BATCH):
        batch = symbols[i:i + YF_BATCH]
        t0 = time.monotonic()
        try:
            df = yf.download(batch, start=start.isoformat(), end=end.isoformat(), interval="1d",
                             auto_adjust=auto_adjust, actions=True, group_by="ticker",
                             threads=True, progress=False)
        except Exception as exc:  # noqa: BLE001
            if "RateLimit" in type(exc).__name__ or "Too Many Requests" in str(exc):
                raise RateLimited(str(exc)) from exc
            YF_BATCH_ERRORS.append(f"{type(exc).__name__}: {str(exc)[:120]}")
            for s in batch:
                out[s] = BATCH_ERR
            STATS.add(src, time.monotonic() - t0, 0)
            time.sleep(2.0)
            continue
        errs = getattr(getattr(yf, "shared", None), "_ERRORS", {}) or {}
        if any("Too Many Requests" in str(v) or "Rate limit" in str(v) for v in errs.values()):
            raise RateLimited("yfinance: " + "; ".join(list(map(str, errs.values()))[:3]))
        nbytes = 0
        for s in batch:
            sub = None
            try:
                if df is not None and not df.empty:
                    cols = df.columns
                    if getattr(cols, "nlevels", 1) > 1:
                        sub = df[s] if s in cols.get_level_values(0) else None
                    else:
                        sub = df
                    sub = sub.dropna(how="all") if sub is not None else None
                if sub is not None:
                    if sub.empty or "Close" not in sub or sub["Close"].dropna().empty:
                        sub = None
                    else:
                        nbytes += int(sub.memory_usage(deep=True).sum())
            except Exception:  # noqa: BLE001
                sub = None
            out[s] = sub
        STATS.add(src, time.monotonic() - t0, nbytes)
        time.sleep(2.0)   # Schonung gegen Yahoo-Rate-Limit
    return out


# ── P1 ───────────────────────────────────────────────────────────────────────
def probe_finra(result):
    p1 = {"datensaetze": {}}
    chosen = None
    for ds in FINRA_DATASETS:
        info = {}
        r = http("GET", FINRA_META.format(ds=ds), "finra_api")
        info["metadata_http"] = r.status_code
        if r.status_code == 200:
            try:
                meta = r.json()
                fields = meta.get("fields") if isinstance(meta, dict) else None
                info["felder"] = [f.get("name") for f in fields] if isinstance(fields, list) else str(meta)[:800]
            except ValueError:
                info["felder"] = r.text[:800]
        st, rows = finra_all(ds, {"domainFilters": [{"fieldName": "symbolCode", "values": list(ANCHORS)}],
                                  **date_filter(date(2016, 1, 1), date(2026, 12, 31))}, max_pages=4)
        info["anker_http"] = st
        info["anker_zeilen"] = len(rows)
        if st != 200:
            info["anker_fehlertext"] = LAST_ERR.get(ds)
        if rows:
            info["beispiel_schluessel"] = sorted(rows[0].keys())
            dates = sorted({pick(x, "date") for x in rows if pick(x, "date")})
            info["anker_erster_stichtag"] = dates[0] if dates else None
            info["anker_letzter_stichtag"] = dates[-1] if dates else None
            per = {}
            for x in rows:
                per.setdefault(pick(x, "symbol"), []).append(pick(x, "date"))
            info["anker_erster_stichtag_je_symbol"] = {k: min(v) for k, v in sorted(per.items())}
            mk = {}
            for x in rows:
                mk[str(pick(x, "market"))] = mk.get(str(pick(x, "market")), 0) + 1
            info["anker_marktcode"] = mk
            if chosen is None:
                chosen = (ds, rows)
        p1["datensaetze"][ds] = info
    try:
        r = http("GET", FINRA_CATALOG, "finra_web")
        links = sorted(set(re.findall(r"https?://[^\"'\s>]+?\.(?:csv|txt|zip)", r.text)))
        p1["katalog"] = {"http": r.status_code, "datei_links": links[:20], "anzahl_links": len(links)}
    except RateLimited:
        raise
    except Exception as exc:  # noqa: BLE001
        p1["katalog"] = {"fehler": str(exc)[:200]}
    if chosen is None:
        p1["verdikt_hinweis"] = "kein Datensatz mit NYSE/Nasdaq-Ankern"
        result["P1"] = p1
        return None
    ds, rows = chosen
    p1["gewaehlt"] = ds
    aapl = sorted({pick(x, "date") for x in rows if pick(x, "symbol") == "AAPL"})
    sdates = [date.fromisoformat(d[:10]) for d in aapl]
    gaps = [(a.isoformat(), b.isoformat(), (b - a).days) for a, b in zip(sdates, sdates[1:]) if (b - a).days > 20]
    p1["stichtage_aapl"] = {"anzahl": len(sdates), "erster": aapl[0] if aapl else None,
                            "letzter": aapl[-1] if aapl else None, "luecken_ueber_20_tage": gaps}
    # Symbolzahl je Stichtag (Record-Total bzw. Zählung) für alle Stichtage ab 06/2021
    counts = {}
    for d in sdates:
        if d < date(2021, 1, 1):
            continue
        st, data, hdr = finra_query(ds, {"limit": 1, **date_filter(d, d)})
        tot = None
        for k, v in (hdr or {}).items():
            if k.lower() == "record-total":
                tot = int(v)
        counts[d.isoformat()] = tot if tot is not None else (len(data) if st == 200 else f"HTTP {st}")
    p1["zeilen_je_stichtag"] = counts
    p1["veroeffentlichungsdatum_feld"] = [k for k in (p1["datensaetze"][ds].get("beispiel_schluessel") or [])
                                         if "publi" in k.lower() or "dissem" in k.lower() or "report" in k.lower()]
    result["P1"] = p1
    return ds, sdates


# ── P2/P3/P4/P6 ──────────────────────────────────────────────────────────────
def year_anchor(sdates, year):
    c = [d for d in sdates if d >= date(year, 7, 1) and d.year == year]
    return min(c) if c else None


def probe_survivorship(result, ds, sdates):
    p2, p6_cands = {}, []
    sec_map = sec_ticker_map(result)
    p3 = {"ticker_map_http": result.get("_sec_map_http"), "jahre": {}}
    for year in YEARS:
        sd = year_anchor(sdates, year)
        if sd is None:
            p2[str(year)] = {"fehlt": "kein Stichtag ab Juli"}
            continue
        st, rows = finra_all(ds, date_filter(sd, sd))
        cn_day, listed = cnms_symbols(sd)
        recs = {}
        for x in rows:
            s = pick(x, "symbol")
            if s and s in listed and is_common(pick(x, "name")):
                recs[s] = x
        sample = draw_sample(recs, year)
        dtcs = {s: dtc_value(recs[s]) for s in sample}
        low, high, med = split_halves(dtcs)
        data = yf_download([yf_symbol(s) for s in sample], sd, sd + timedelta(days=AVAIL_WINDOW_DAYS),
                           auto_adjust=False)   # Rohkurse: Preisklasse/Volumen wie damals
        errored = {s for s in sample if data.get(yf_symbol(s)) is BATCH_ERR}
        sample = [s for s in sample if s not in errored]
        exp_days = sum(1 for k in range(AVAIL_WINDOW_DAYS)
                       if (sd + timedelta(days=k)).weekday() < 5)
        avail, full, plaus, price = {}, {}, {}, {}
        for s in sample:
            df = data.get(yf_symbol(s))
            avail[s] = df is not None and len(df) > 0
            full[s] = avail[s] and len(df) >= FULL_COVERAGE_FRAC * exp_days
            if avail[s]:
                try:
                    vol = float(df["Volume"].head(20).mean())
                    adv = float(pick(recs[s], "adv") or 0)
                    plaus[s] = adv > 0 and VOL_PLAUS_BAND[0] <= vol / adv <= VOL_PLAUS_BAND[1]
                    price[s] = float(df["Close"].dropna().iloc[0])
                except Exception:  # noqa: BLE001
                    plaus[s] = False
                if "Stock Splits" in df:
                    spl = df["Stock Splits"]
                    spl = spl[spl > 0]
                    for ts, f in spl.items():
                        p6_cands.append((s, ts.date(), float(f), year))

        mcodes = {}
        for s in sample:
            mc = str(pick(recs[s], "market"))
            a_, n_ = mcodes.get(mc, (0, 0))
            mcodes[mc] = (a_ + int(avail[s]), n_ + 1)

        def grp(members):
            m = [s for s in sample if s in members]
            return {"vorhanden": wilson(sum(avail[s] for s in m), len(m)),
                    "voll": wilson(sum(full[s] for s in m), len(m)),
                    "plausibel_gleiches_papier": wilson(sum(plaus.get(s, False) for s in m), len(m))}
        cheap = {s for s, p in price.items() if p < 5}
        dear = {s for s, p in price.items() if p >= 5}
        p2[str(year)] = {
            "stichtag": sd.isoformat(), "cnms_tag": cn_day.isoformat() if cn_day else None,
            "finra_zeilen": len(rows), "gelistet_stammaktien": len(recs), "stichprobe": len(sample),
            "dtc_median": med, "ohne_dtc": sum(1 for v in dtcs.values() if v is None),
            "abruf_fehler_ausgeschlossen": len(errored),
            "vorhanden_je_marktcode": {k: wilson(*v) for k, v in sorted(mcodes.items())},
            "gesamt": grp(set(sample)), "dtc_niedrig": grp(low), "dtc_hoch": grp(high),
            "preis_unter_5_nur_vorhandene": len(cheap), "preis_ab_5_nur_vorhandene": len(dear),
            "dtc_hoch_unter_5": len(high & cheap), "dtc_niedrig_unter_5": len(low & cheap),
        }
        log(f"P2 {year}: {json.dumps(p2[str(year)]['gesamt'])}")
        p3["jahre"][str(year)] = probe_sec(year, sd, sample, sec_map)
        if year in (2021, 2022):
            p2[str(year)]["_fehlend"] = sorted(s for s in sample if not avail[s])
            p2[str(year)]["_hoch"] = sorted(high)
            p2[str(year)]["_vorhanden"] = sorted(s for s in sample if avail[s])
    result["P2"] = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in p2.items()}
    result["P3"] = p3
    section_done(result, "P2")
    section_done(result, "P3")
    start_section("P4")
    probe_stooq(result, p2)
    section_done(result, "P4")
    start_section("P6")
    probe_splits(result, ds, sdates, p6_cands)
    section_done(result, "P6")


def sec_ticker_map(result):
    try:
        r = sec_get(SEC_TICKERS)
        result["_sec_map_http"] = r.status_code
        if r.status_code != 200:
            return {}
        return {v["ticker"].upper(): int(v["cik_str"]) for v in r.json().values()}
    except RateLimited:
        raise
    except Exception as exc:  # noqa: BLE001
        result["_sec_map_http"] = f"fehler {str(exc)[:120]}"
        return {}


def probe_sec(year, sd, sample, sec_map):
    out = {}
    mapped = {s: sec_map[s.upper().replace(".", "-")] for s in sample if s.upper().replace(".", "-") in sec_map}
    out["cik_zuordnung_aktuelle_liste"] = wilson(len(mapped), len(sample))
    try:
        r = sec_get(SEC_FRAME.format(y=year))
        out["frame_http"] = r.status_code
        if r.status_code == 200:
            ciks = {int(d["cik"]) for d in r.json().get("data", [])}
            out["frame_deckung"] = wilson(sum(1 for c in mapped.values() if c in ciks), len(sample))
    except RateLimited:
        raise
    except Exception as exc:  # noqa: BLE001
        out["frame_fehler"] = str(exc)[:160]
    sub = draw_sample(mapped, year + 1000, SEC_PIT_SUBSAMPLE)
    pit = 0
    checked = 0
    for s in sub:
        r = sec_get(SEC_FACTS.format(cik=mapped[s]))
        if r.status_code == 403:
            out["companyfacts_403"] = True
            break
        checked += 1
        if r.status_code != 200:
            continue
        try:
            units = r.json()["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"]
        except (KeyError, ValueError, TypeError):
            continue
        ok = any(u.get("filed") and u.get("end") and date.fromisoformat(u["filed"]) <= sd
                 and date.fromisoformat(u["end"]) >= sd - timedelta(days=200) for u in units)
        pit += ok
    out["pit_stichprobe"] = wilson(pit, checked) if checked else None
    return out


def probe_stooq(result, p2):
    p4 = {"hinweis": "Tiingo/Alpha Vantage nicht abgerufen (Key nötig)"}
    ctrl = (p2.get("2021", {}).get("_vorhanden") or [])[:STOOQ_CONTROL_N]

    def hit(sym, sd):
        a, b = sd.strftime("%Y%m%d"), (sd + timedelta(days=AVAIL_WINDOW_DAYS)).strftime("%Y%m%d")
        r = http("GET", STOOQ_URL.format(s=sym.lower().replace(".", "-"), a=a, b=b), "stooq")
        time.sleep(1.0)
        body = r.text.strip()
        if r.status_code != 200:
            return f"http_{r.status_code}"
        if body.lower().startswith("date,") and len(body.splitlines()) > 1:
            try:
                return "daten", float(body.splitlines()[1].split(",")[4])
            except (IndexError, ValueError):
                return "daten", None
        if "limit" in body.lower() and "exceed" in body.lower():
            raise RateLimited("Stooq: Tageslimit")
        if "apikey" in body.lower() or "api key" in body.lower():
            return "key_noetig", None
        return "leer", None
    res = {}
    sd21 = date.fromisoformat(p2["2021"]["stichtag"]) if "stichtag" in p2.get("2021", {}) else None
    if sd21:
        c = [hit(s, sd21)[0] for s in ctrl]
        res["kontrolle_2021"] = {k: c.count(k) for k in set(c)}
        if c.count("daten") == 0:
            p4["ergebnis"] = res
            p4["abbruch"] = "Kontrolle ohne Daten — fehlende Symbole nicht geprüft"
            result["P4"] = p4
            return
    for y in ("2021", "2022"):
        if "stichtag" not in p2.get(y, {}):
            continue
        sd = date.fromisoformat(p2[y]["stichtag"])
        miss = draw_sample(p2[y].get("_fehlend") or [], int(y) + 2000, STOOQ_MISSING_N)
        hoch = set(p2[y].get("_hoch") or [])
        got = {s: hit(s, sd) for s in miss}
        c = [v[0] for v in got.values()]
        tr = {s: v[1] for s, v in got.items() if v[0] == "daten"}
        res[f"fehlend_{y}"] = {
            "geprueft": len(miss), **{k: c.count(k) for k in set(c)},
            "stooq_treffer_dtc_hoch": sum(1 for s in tr if s in hoch),
            "geprueft_dtc_hoch": sum(1 for s in miss if s in hoch),
            "stooq_treffer_preis_unter_5": sum(1 for p in tr.values() if p is not None and p < 5),
            "stooq_treffer_preis_ab_5": sum(1 for p in tr.values() if p is not None and p >= 5),
        }
    p4["ergebnis"] = res
    result["P4"] = p4


def probe_splits(result, ds, sdates, cands):
    allc = sorted({c for c in cands if not 0.67 < c[2] < 1.5})
    cands = [allc[i] for i in draw_sample(range(len(allc)), 9999, SPLIT_EXAMPLES_MAX)]
    tally, examples = {}, []
    for sym, sday, factor, _y in cands:
        if 0.67 < factor < 1.5:
            continue
        before = [d for d in sdates if d < sday]
        after = [d for d in sdates if d >= sday]
        if not before or not after:
            continue
        s0, s1 = max(before), min(after)
        st, rows = finra_all(ds, {"domainFilters": [{"fieldName": "symbolCode", "values": [sym]}],
                                  **date_filter(s0, s1)}, max_pages=1)
        by = {pick(x, "date")[:10]: x for x in rows if pick(x, "date")}
        r0, r1 = by.get(s0.isoformat()), by.get(s1.isoformat())
        if not r0 or not r1:
            continue
        k = classify_split(pick(r0, "current"), pick(r1, "current"), pick(r1, "previous"), factor)
        tally["/".join(k)] = tally.get("/".join(k), 0) + 1
        if len(examples) < 3:
            examples.append({"symbol": sym, "split_tag": sday.isoformat(), "faktor": factor,
                             "stichtag_vor": s0.isoformat(), "stichtag_nach": s1.isoformat(),
                             "si_vor": pick(r0, "current"), "si_nach": pick(r1, "current"),
                             "vorperiode_im_nach": pick(r1, "previous"),
                             "split_flag": pick(r1, "split"), "klasse": k})
    result["P6"] = {"splits_gefunden": len(allc), "gezogen": len(cands),
                    "faktoren": sorted({c[2] for c in cands}),
                    "auswertbar": sum(tally.values()), "klassen": tally,
                    "beispiele": examples}


# ── P5 ───────────────────────────────────────────────────────────────────────
def real_top10():
    """{date: set(ticker)} ab PROXY_FROM — NUR Schlüssel ticker/date."""
    out = {}

    def add(t, d):
        try:
            dd = datetime.strptime(d, "%d.%m.%Y").date()
        except (TypeError, ValueError):
            return
        if dd >= PROXY_FROM and isinstance(t, str):
            out.setdefault(dd, set()).add(t)
    try:
        for e in json.loads((ROOT / "backtest_history.json").read_text(encoding="utf-8")):
            if isinstance(e, dict) and not e.get("bootstrap"):
                add(e.get("ticker"), e.get("date"))
    except (OSError, ValueError):
        pass
    try:
        for ln in (ROOT / "matured_backtest_export.jsonl").read_text(encoding="utf-8").splitlines():
            if ln.strip():
                e = json.loads(ln)
                add(e.get("ticker"), e.get("date"))
    except (OSError, ValueError):
        pass
    return out


def probe_proxy(result, ds, sdates):
    real = real_top10()
    days = sorted(real)
    if not days:
        result["P5"] = {"fehlt": "keine echten Top-10 ab 01.07.2026"}
        return
    hol = frozenset(getattr(config, "US_MARKET_HOLIDAYS", ()))
    sets_ = [d for d in sdates if date(2026, 4, 15) <= d <= days[-1]]
    si = {}
    for d in sets_:
        st, rows = finra_all(ds, date_filter(d, d))
        si[d] = {pick(x, "symbol"): x for x in rows if pick(x, "symbol")}
    shares = {}
    try:
        r = sec_get(SEC_FRAME.format(y=2026))
        if r.status_code == 200:
            frame = {int(x["cik"]): float(x["val"]) for x in r.json().get("data", [])}
            m = sec_ticker_map(result)
            shares = {t: frame[c] for t, c in m.items() if c in frame}
    except RateLimited:
        raise
    except Exception:  # noqa: BLE001
        pass
    cand = set()
    for d, recs in si.items():
        for s, x in recs.items():
            sh = shares.get(s.upper().replace(".", "-"))
            cur = pick(x, "current")
            if sh and cur and float(cur) / sh * 100 >= config.MIN_SHORT_FLOAT and is_common(pick(x, "name")):
                cand.add(s)
    real_us = {d: {t for t in ts if "." not in t} for d, ts in real.items()}
    start = days[0] - timedelta(days=45)
    syms = sorted(cand | {"^GSPC"})
    data = yf_download([yf_symbol(s) for s in syms], start, days[-1] + timedelta(days=1), src="yfinance_proxy")
    spx = data.get("^GSPC")
    if spx is BATCH_ERR:
        spx = None
    pairs, in_universe = [], []
    for d in days:
        sd = latest_usable_settlement(d, sets_, hol)
        if sd is None or spx is None:
            continue
        prev = [x for x in sets_ if x < sd]
        scored = []
        for s in cand:
            x = si.get(sd, {}).get(s)
            df = data.get(yf_symbol(s))
            if x is None or df is None or df is BATCH_ERR:
                continue
            h = df[df.index.date <= d]
            if len(h) < 22 or h.index[-1].date() != d:
                continue
            close, opn, pc = float(h["Close"].iloc[-1]), float(h["Open"].iloc[-1]), float(h["Close"].iloc[-2])
            sh = shares.get(s.upper().replace(".", "-"))
            if close < config.MIN_PRICE or not sh or close * sh > config.MAX_MARKET_CAP_B * 1e9:
                continue
            cur = float(pick(x, "current") or 0)
            si_pct = cur / sh * 100
            if si_pct < config.MIN_SHORT_FLOAT:
                continue
            vol20 = float(h["Volume"].iloc[-21:-1].mean())
            rvol = float(h["Volume"].iloc[-1]) / vol20 if vol20 > 0 else 0.0
            sp = spx[spx.index.date <= d]
            spx_chg = (float(sp["Close"].iloc[-1]) / float(sp["Close"].iloc[-2]) - 1) * 100
            chg = (close / pc - 1) * 100
            perf20 = (close / float(h["Close"].iloc[-21]) - 1) * 100
            spx20 = (float(sp["Close"].iloc[-1]) / float(sp["Close"].iloc[-21]) - 1) * 100
            px = si.get(max(prev), {}).get(s) if prev else None
            si_up = px is not None and cur > float(pick(px, "current") or 0)
            sc = proxy_score(si_pct, dtc_value(x), rvol, chg - spx_chg,
                             gap_pts(opn, pc, close), rs_pts(perf20 - spx20), si_up)
            scored.append((sc, rvol >= config.MIN_REL_VOLUME, s))
        pref = sorted([t for t in scored if t[1]], reverse=True)
        rest = sorted([t for t in scored if not t[1]], reverse=True)
        top = {s for _, _, s in (pref + rest)[:10]}
        pairs.append((real_us[d], top))
        in_universe.append((len(real_us[d] & {s for _, _, s in scored}), len(real_us[d])))
    result["P5"] = {
        "tage_echt": len(days), "tage_ausgewertet": len(pairs),
        "kandidaten_universum": len(cand), "aktien_aus_sec_frame": len(shares),
        "ueberschneidung_top10": overlap_stats(pairs),
        "echte_ticker_im_proxy_universum": {"treffer": sum(a for a, _ in in_universe),
                                           "von": sum(b for _, b in in_universe)},
        "nicht_us_ausgeschlossen": sum(len(real[d]) - len(real_us[d]) for d in days),
        "annahmen": "SI ab Stichtag + 8 Werktage; Aktienzahl aus Frame CY2026Q2I (Nähe dadurch eher optimistisch); Short-Anteil = SI / ausstehende Aktien (SEC CY2026Q2I); "
                    "ohne Float, Turnover, News, KI, Malus, Glättung",
    }


# ── P7 ───────────────────────────────────────────────────────────────────────
def extrapolate(result):
    st = STATS.as_dict()
    yf = st.get("yfinance", {})
    n_sym = sum(v.get("stichprobe", 0) for v in result.get("P2", {}).values() if isinstance(v, dict))
    per_sym = yf["sekunden"] / n_sym if n_sym and yf else None
    bytes_per_sym_win = yf["bytes"] / n_sym if n_sym and yf else None
    uni = max((v.get("gelistet_stammaktien", 0) for v in result.get("P2", {}).values()
               if isinstance(v, dict)), default=0)
    trading_days_5y = 252 * 5
    win_days = AVAIL_WINDOW_DAYS * 5 / 7
    result["P7"] = {
        "messung": st,
        "yfinance_sekunden_je_symbol_fenster": round(per_sym, 3) if per_sym else None,
        "hochrechnung_kurse_5_jahre": {
            "symbole_geschaetzt": uni,
            "minuten_bei_einem_abruf_je_symbol": round(per_sym * uni / 60, 1) if per_sym else None,
            "mb_im_speicher": round(bytes_per_sym_win * uni * trading_days_5y / win_days / 1e6, 1)
            if bytes_per_sym_win else None,
        },
        "finra_stichtage_ab_06_2021": len(result.get("P1", {}).get("zeilen_je_stichtag", {})),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--nur", choices=("alle", "survivorship", "proxy"), default="alle",
                    help="survivorship = P2/P3/P4/P6, proxy = P5 (P1 und P7 immer)")
    args = ap.parse_args(argv)
    today = datetime.now(timezone.utc).date()
    if today > PROBE_END:
        log(f"no-op: nach {PROBE_END}")
        return 0
    t0 = time.monotonic()
    result = {"seed": SEED, "stichprobe_n": SAMPLE_N, "nur": args.nur,
              "start_utc": datetime.now(timezone.utc).isoformat()}
    out = pathlib.Path(args.out)
    rc = 0
    try:
        start_section("P1")
        got = probe_finra(result)
        section_done(result, "P1")
        if got:
            ds, sdates = got
            if args.nur in ("alle", "survivorship"):
                start_section("P2")
                probe_survivorship(result, ds, sdates)
            if args.nur in ("alle", "proxy"):
                start_section("P5")
                probe_proxy(result, ds, sdates)
                section_done(result, "P5")
        start_section("P7")
        extrapolate(result)
        section_done(result, "P7")
    except RateLimited as exc:
        # Lockerung Easy 14.11.2026: vollständige Abschnitte davor gelten als Befund;
        # der abgebrochene Abschnitt zählt nicht. Kein automatischer Neustart.
        result["abgebrochen_in"] = CURRENT["abschnitt"]
        result["abbruch_grund"] = str(exc)[:300]
        for k in ("P1", "P2", "P3", "P4", "P5", "P6", "P7"):
            if k not in result.get("abschnitte_vollstaendig", []):
                result.pop(k, None)
        log(f"ABBRUCH Rate-Limit in {CURRENT['abschnitt']} — nicht gezählt; "
            f"vollständig: {result.get('abschnitte_vollstaendig', [])}; Grund: {exc}")
        rc = 3
    result.pop("_sec_map_http", None)
    result["finra_ersatzfilter_genutzt"] = FALLBACK_USED
    result["finra_letzte_fehler"] = LAST_ERR
    result["yfinance_batch_fehler"] = {"anzahl": len(YF_BATCH_ERRORS), "beispiele": YF_BATCH_ERRORS[:5]}
    result["laufzeit_s"] = round(time.monotonic() - t0, 1)
    log("meta " + json.dumps({k: result.get(k) for k in (
        "finra_ersatzfilter_genutzt", "finra_letzte_fehler", "yfinance_batch_fehler", "laufzeit_s")},
        default=str))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    log(f"{'abgebrochen' if rc else 'fertig'} in {result['laufzeit_s']} s → {out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
