#!/usr/bin/env python3
"""WEGWERF-PROBE Mehrjahres-Rückrechnung, Schritt 1 (read-only, nur Zählungen).

Easy-Entscheid 14.11.2026 (open_item ``mehrjahres-rueckrechnung-probe``); Fix 2
nach Lauf 43606294489 (Easy-Freigabe 14.11.2026, Self-Merge). Klärt mit ZAHLEN,
ob ein Mehrjahres-Prüffeld mit freien Daten ehrlich nutzbar ist:

  P1   FINRA ``consolidatedShortInterest``: Start, Felder, Füllgrad je Quartal ab
       12/2017, Bedeutung stockSplitFlag/revisionFlag (FINRA-Metadaten),
       Veröffentlichungs-Kalender (FINRA-Seite), Symbol-Schreibweisen.
  P2F  Abgangsrate OHNE Kursquelle: Stammaktien an einem Juli-Stichtag J
       (2018–2025) — wie viele fehlen 12 / 24 Monate später in den FINRA-Dateien
       (getrennt: weiter gelistet / nach OTC / Kürzel gewechselt (gleicher Name) /
       Kürzel neu vergeben / verschwunden), nach DTC-Hälfte und Marktkennzeichen.
  P2Y  yfinance-Verfügbarkeit (2021–2025, Stichprobe) mit KONTROLLGRUPPE heute
       gelisteter Stammaktien (Gültigkeitskriterium unten, vorab festgeschrieben),
       Pakete à 20, Fehlergründe gezählt, Einzel-Gegenprobe der Fehlenden.
  P2K  Kurse für die laut P2F verschwundenen Symbole: yfinance Einzelabruf,
       Stooq (falls erreichbar) — Teilstichprobe.
  P3   SEC XBRL ausstehende Aktien (Deckung, point-in-time über ``filed``).
  P5   Nähe Proxy-Liste ↔ echte Top-10 ab 01.07.2026 — NUR Zugehörigkeit.
  P6   Splits: stockSplitFlag in aufeinanderfolgenden Dateien — Vorperiode
       angepasst oder roh?
  P7   Laufzeit-/Datenmengen-Hochrechnung (nur Gesamtlauf).

BLINDHEIT / TRENNUNG: es wird in KEINEM Zeitraum ein Ergebnisfeld berechnet oder
gelesen (keine Rendite, kein Gipfel, keine Kursveränderung nach einem Stichtag).
Kurse nur auf Verfügbarkeit, Zeilenzahl, Volumen-Plausibilität, Preis am
Stichtag (Preisklasse) und — für die Proxy-Liste — als Eingaben bis
einschließlich Tag D. Aus den Backtest-Dateien NUR ``ticker`` / ``date``.

Schreibt NUR stdout (``[rueck_probe]``) und ``--out`` (Artifact). Keine Secrets;
SEC-User-Agent generisch (.invalid). Rate-Limit (HTTP 429 / yfinance / Stooq-
Tageslimit) → Abbruch (Exit 3); vollständig abgeschlossene Abschnitte davor
bleiben Befund (Log „ABSCHNITT Pn vollständig“), kein automatischer Neustart.
Verbindungsfehler zu Stooq sind ein Befund („nicht erreichbar“), kein Abbruch.
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
DS = "consolidatedShortInterest"   # Lauf 43606294489: NYSE/Nasdaq ab 29.12.2017
YEARS_Y = (2021, 2022, 2023, 2024, 2025)          # yfinance-Messung
YEARS_F = tuple(range(2018, 2026))               # Abgangsrate aus FINRA
# Stichprobe yfinance je Jahr: ±2 pp (95 %) ohne Annahme über den Anteil:
# n = 1,96² · 0,25 / 0,02² = 2 401 (kleinere Grundgesamtheit → Vollerhebung).
SAMPLE_N = math.ceil(1.96 ** 2 * 0.25 / 0.02 ** 2)
CONTROL_N = 400
# GÜLTIGKEITSKRITERIUM — VORAB FESTGESCHRIEBEN (14.11.2026, vor Lauf 2):
# heute gelistete Stammaktien müssen mit derselben Abrufmethode zu mindestens
# 97 % Kurse liefern; sonst gilt die yfinance-Verfügbarkeitsmessung P2Y als
# UNGÜLTIG (misst die Abrufmethode, nicht das Überleben).
CONTROL_MIN = 0.97
AVAIL_WINDOW_DAYS = 60
FULL_COVERAGE_FRAC = 0.8
VOL_PLAUS_BAND = (0.2, 5.0)
SINGLE_RECHECK_N = 50            # Einzel-Gegenprobe je Jahr (bei Paketen fehlend)
VANISHED_CHECK_N = 60            # P2K: verschwundene Symbole je Basisjahr (yfinance)
STOOQ_CHECK_N = 20               # P2K: davon an Stooq (falls erreichbar)
SEC_PIT_SUBSAMPLE = 100
SPLIT_EXAMPLES_MAX = 30
PROXY_FROM = date(2026, 7, 1)
PUB_LAG_BUSINESS_DAYS = 8        # Annahme ~7 Werktage + 1 Reserve; P1 prüft gegen FINRA-Seite
YF_BATCH = 20
YF_PAUSE_S = 2.0

FINRA_API = "https://api.finra.org/data/group/otcMarket/name/{ds}"
FINRA_META = "https://api.finra.org/metadata/group/otcMarket/name/{ds}"
FINRA_PAGES = ("https://www.finra.org/filing-reporting/short-interest",
               "https://www.finra.org/filing-reporting/short-interest-reporting",
               "https://www.finra.org/finra-data/browse-catalog/equity-short-interest/glossary")
CNMS_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt"
SEC_UA = "SqueezeReportProbe/1.0 (throwaway contact squeeze-report-rueckrechnung-probe@example.invalid)"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_FRAME = "https://data.sec.gov/api/xbrl/frames/dei/EntityCommonStockSharesOutstanding/shares/CY{y}Q2I.json"
SEC_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
STOOQ_URL = "https://stooq.com/q/d/l/?s={s}.us&d1={a}&d2={b}&i=d"
ANCHORS = ("AAPL", "MSFT", "AMC", "GME", "F", "BAC", "KO", "XOM", "PFE", "T")
LISTED_CODES = frozenset({"NYSE", "NNM", "SC", "AMEX", "ARCA", "BZX", "NMS", "NGM", "NCM", "IEX", "BATS"})

# ── Zuordnungsregel FINRA → Kategorie / yfinance (vorab festgeschrieben) ─────
# Reihenfolge: Test → ETF/Fonds → Vorzug → Optionsschein → Unit → Right → Anleihe
# → Klassen-Aktie → Stammaktie → sonstiges. STAMMAKTIEN = „stamm“ + „klasse“.
# Kriterium Stammaktie: Kürzel aus 1–5 Großbuchstaben (Klasse: 1–5 Buchstaben,
# Trenner [ ./-], ein Buchstabe) UND Name ohne die Muster der übrigen Kategorien.
# yfinance-Schreibweise: Trenner [ ./] → „-“ (BRK.B / BRK B / BRK/B → BRK-B).
TEST_SYMBOLS = frozenset({"ZVZZT", "ZWZZT", "ZXZZT", "ZBZZT", "ZJZZT", "ZVV", "NTEST",
                          "ATEST", "CTEST", "PTEST", "MTEST", "ZZK", "ZZZ"})
_RE_ETF = re.compile(r"\b(ETF|ETN|FUND|TRUST|INDEX|ISHARES|SPDR|PROSHARES|PORTFOLIO)\b", re.I)
_RE_PFD = re.compile(r"\b(PFD|PREFERRED|PREF|DEP(OSITARY)?\s+SH(ARE)?S?)\b|%", re.I)
_RE_WT = re.compile(r"\b(WARRANTS?|WTS?)\b", re.I)
_RE_UNIT = re.compile(r"\bUNITS?\b", re.I)
_RE_RIGHT = re.compile(r"\bRIGHTS?\b", re.I)
_RE_NOTE = re.compile(r"\b(NOTES?|DEBENTURES?|BONDS?|SENIOR)\b", re.I)
_RE_COMMON_SYM = re.compile(r"^[A-Z]{1,5}$")
_RE_CLASS_SYM = re.compile(r"^[A-Z]{1,5}[ ./-][A-Z]$")
_RE_SYM_SUFFIX = {"vorzug": re.compile(r"([ .-]P[R]?[ .-]?[A-Z]?$|\.PR|p[A-Z]?$)"),
                  "optionsschein": re.compile(r"([ .-]WS([ .-]?[A-Z])?$|\.W$)"),
                  "unit": re.compile(r"([ .-]U$|[ .-]UN$)"),
                  "right": re.compile(r"([ .-]R$|[ .-]RT$)")}
_NAME_STOP = frozenset({"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC",
                        "HOLDINGS", "HOLDING", "GROUP", "THE", "CLASS", "CL", "A", "B", "C",
                        "COMMON", "STOCK", "ORDINARY", "SHARES", "SHS", "NEW", "LLC", "LP", "SA",
                        "NV", "AG", "SE", "ADR", "ADS", "AMERICAN", "DEPOSITARY"})

FIELD_CANDIDATES = {
    "symbol": ("symbolCode", "issueSymbolIdentifier", "symbol"),
    "date": ("settlementDate",),
    "current": ("currentShortPositionQuantity", "currentShortShareNumber"),
    "previous": ("previousShortPositionQuantity", "previousShortShareNumber"),
    "adv": ("averageDailyVolumeQuantity", "averageShortShareNumber"),
    "dtc": ("daysToCoverQuantity", "daysToCoverNumber"),
    "name": ("issueName",),
    "market": ("marketClassCode", "marketCategoryCode"),
    "split": ("stockSplitFlag",),
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
YF_ERR_CATS: dict[str, int] = {}
YF_ERR_EXAMPLES: dict[str, list] = {}
CURRENT = {"abschnitt": None}
FILE_CACHE: dict = {}


def log(msg):
    print(f"[rueck_probe] {msg}", flush=True)


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


def category(sym, name) -> str:
    """Kategorie nach der Zuordnungsregel oben (Kürzel + Name)."""
    s = (sym or "").strip().upper()
    n = name if isinstance(name, str) else ""
    if not s:
        return "sonstiges"
    if s in TEST_SYMBOLS or re.search(r"\bTEST\b", n, re.I):
        return "test"
    if _RE_ETF.search(n):
        return "etf_fonds"
    if _RE_PFD.search(n) or _RE_SYM_SUFFIX["vorzug"].search(sym or ""):
        return "vorzug"
    if _RE_WT.search(n) or _RE_SYM_SUFFIX["optionsschein"].search(s):
        return "optionsschein"
    if _RE_UNIT.search(n) or _RE_SYM_SUFFIX["unit"].search(s):
        return "unit"
    if _RE_RIGHT.search(n) or _RE_SYM_SUFFIX["right"].search(s):
        return "right"
    if _RE_NOTE.search(n):
        return "anleihe"
    if _RE_CLASS_SYM.match(s):
        return "klasse"
    if _RE_COMMON_SYM.match(s):
        return "stamm"
    return "sonstiges"


def is_stock(sym, name) -> bool:
    return category(sym, name) in ("stamm", "klasse")


def yf_symbol(sym: str) -> str:
    return re.sub(r"[ ./]", "-", (sym or "").strip().upper())


def symbol_pattern(sym: str) -> str:
    return re.sub(r"[A-Z]", "A", re.sub(r"[a-z]", "a", re.sub(r"[0-9]", "9", sym or "")))


def name_key(name) -> str:
    """Normalisierter Firmenname (erste zwei bedeutungstragende Wörter)."""
    if not isinstance(name, str):
        return ""
    toks = [t for t in re.sub(r"[^A-Z0-9 ]", " ", name.upper()).split() if t not in _NAME_STOP]
    return " ".join(toks[:2])


def draw_sample(population, year: int, n: int = SAMPLE_N) -> list:
    pop = sorted(set(population))
    if len(pop) <= n:
        return pop
    return sorted(random.Random(SEED + year).sample(pop, n))


def dtc_of(cur, adv, dtc):
    try:
        if dtc is not None and math.isfinite(float(dtc)):
            return float(dtc)
    except (TypeError, ValueError):
        pass
    try:
        cur, adv = float(cur), float(adv)
    except (TypeError, ValueError):
        return None
    return cur / adv if adv > 0 else None


def split_halves(values: dict):
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


def business_days_between(a: date, b: date, holidays=frozenset()) -> int:
    k, cur = 0, a
    while cur < b:
        cur += timedelta(days=1)
        if cur.weekday() < 5 and cur.isoformat() not in holidays:
            k += 1
    return k


def latest_usable_settlement(d: date, settlements, holidays=frozenset()):
    usable = [s for s in settlements if business_days_after(s, PUB_LAG_BUSINESS_DAYS, holidays) <= d]
    return max(usable) if usable else None


def fate(sym, base_rec, later_file, later_names) -> str:
    """Verbleib eines Stammaktien-Symbols vom Basis- zum späteren Stichtag.

    later_file: sym → Kurzsatz; later_names: name_key → set(sym).
    gelistet / otc / neu_vergeben (Kürzel da, anderer Name) /
    kuerzel_gewechselt (Name unter anderem Kürzel) / verschwunden."""
    nk = name_key(base_rec["name"])
    rec = later_file.get(sym)
    if rec is not None:
        if nk and name_key(rec["name"]) and name_key(rec["name"]) != nk:
            return "neu_vergeben"
        return "gelistet" if rec["market"] in LISTED_CODES else "otc"
    if nk and later_names.get(nk, set()) - {sym}:
        return "kuerzel_gewechselt"
    return "verschwunden"


def classify_split_flag(prev_later, cur_earlier):
    """Vorperiode im späteren Satz vs. aktuelle Position im früheren Satz."""
    try:
        a, b = float(prev_later), float(cur_earlier)
    except (TypeError, ValueError):
        return "unklar"
    if b <= 0:
        return "unklar"
    if abs(a - b) <= 0.01 * b:
        return "vorperiode_roh"
    return "vorperiode_angepasst"


def overlap_stats(pairs):
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


def yf_err_category(msg: str) -> str:
    m = (msg or "").lower()
    if "too many requests" in m or "rate limit" in m:
        return "rate_limit"
    if "delisted" in m:
        return "possibly_delisted"
    if "no data found" in m or "no price data" in m:
        return "keine_daten"
    if "timezone" in m:
        return "keine_zeitzone"
    if "timed out" in m or "timeout" in m or "connection" in m:
        return "netz"
    return "sonstiges"


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


def finra_query(body):
    hdr = {"Accept": "application/json", "Content-Type": "application/json"}
    r = http("POST", FINRA_API.format(ds=DS), "finra_api", headers=hdr, data=json.dumps(body))
    time.sleep(0.3)
    if r.status_code != 200:
        LAST_ERR[DS] = f"HTTP {r.status_code}: {r.text[:300]}"
        return r.status_code, [], r.headers
    try:
        data = r.json()
    except ValueError:
        return r.status_code, [], r.headers
    return 200, data if isinstance(data, list) else [], r.headers


def finra_all(filters, page=5000, max_pages=20):
    rows, off = [], 0
    for _ in range(max_pages):
        st, data, _ = finra_query(dict(filters, limit=page, offset=off))
        if st != 200:
            dr = (filters.get("dateRangeFilters") or [None])[0]
            if not rows and dr and dr["startDate"] == dr["endDate"] and "compareFilters" not in filters:
                FALLBACK_USED[DS] = FALLBACK_USED.get(DS, 0) + 1
                alt = {k: v for k, v in filters.items() if k != "dateRangeFilters"}
                alt["compareFilters"] = [{"compareType": "EQUAL", "fieldName": "settlementDate",
                                          "fieldValue": dr["startDate"]}]
                return finra_all(alt, page, max_pages)
            return st, rows
        rows += data
        if len(data) < page:
            return 200, rows
        off += page
    return 200, rows


def date_filter(start, end):
    return {"dateRangeFilters": [{"fieldName": "settlementDate",
                                  "startDate": start.isoformat(), "endDate": end.isoformat()}]}


def get_file(d: date) -> dict:
    """Ganze Stichtags-Datei als sym → Kurzsatz (gecacht)."""
    if d in FILE_CACHE:
        return FILE_CACHE[d]
    st, rows = finra_all(date_filter(d, d))
    out = {}
    for x in rows:
        s = pick(x, "symbol")
        if not s:
            continue
        out[s] = {"name": pick(x, "name"), "market": str(pick(x, "market")),
                  "cur": pick(x, "current"), "prev": pick(x, "previous"), "adv": pick(x, "adv"),
                  "dtc": pick(x, "dtc"), "split": pick(x, "split"), "rev": pick(x, "revision")}
    FILE_CACHE[d] = out if st == 200 else {}
    if st != 200:
        log(f"FINRA-Datei {d} HTTP {st}: {LAST_ERR.get(DS, '')[:160]}")
    return FILE_CACHE[d]


def first_on_or_after(sdates, d: date):
    c = [x for x in sdates if x >= d]
    return min(c) if c else None


def cnms_symbols(d: date):
    for back in range(0, 6):
        dd = d - timedelta(days=back)
        r = http("GET", CNMS_URL.format(d=dd.strftime("%Y%m%d")), "finra_cnms")
        if r.status_code == 200 and "|" in r.text:
            return dd, {ln.split("|")[1].strip() for ln in r.text.splitlines()[1:]
                        if len(ln.split("|")) >= 2 and ln.split("|")[1]}
    return None, set()


def sec_get(url):
    r = http("GET", url, "sec", headers={"User-Agent": SEC_UA, "Accept-Encoding": "gzip"})
    time.sleep(0.12)
    return r


BATCH_ERR = object()   # Paket-Abruf-Fehler ≠ „nicht vorhanden“


def _yf_errors_reset(yf):
    try:
        yf.shared._ERRORS.clear()
    except Exception:  # noqa: BLE001
        pass


def _yf_errors_take(yf, batch):
    errs = dict(getattr(getattr(yf, "shared", None), "_ERRORS", {}) or {})
    for t, msg in errs.items():
        cat = yf_err_category(str(msg))
        if cat == "rate_limit":
            raise RateLimited(f"yfinance: {str(msg)[:160]}")
        YF_ERR_CATS[cat] = YF_ERR_CATS.get(cat, 0) + 1
        ex = YF_ERR_EXAMPLES.setdefault(cat, [])
        if len(ex) < 3:
            ex.append(f"{t}: {str(msg)[:120]}")
    return errs


def yf_download(symbols, start, end, src="yfinance", auto_adjust=False):
    """{yf_symbol: DataFrame|None|BATCH_ERR}. Pakete à YF_BATCH. Rate-Limit → RateLimited."""
    import yfinance as yf
    out = {}
    for i in range(0, len(symbols), YF_BATCH):
        batch = symbols[i:i + YF_BATCH]
        t0 = time.monotonic()
        _yf_errors_reset(yf)
        try:
            df = yf.download(batch, start=start.isoformat(), end=end.isoformat(), interval="1d",
                             auto_adjust=auto_adjust, actions=True, group_by="ticker",
                             threads=True, progress=False)
        except Exception as exc:  # noqa: BLE001
            if "RateLimit" in type(exc).__name__ or "Too Many Requests" in str(exc):
                raise RateLimited(str(exc)) from exc
            YF_ERR_CATS["paket_ausnahme"] = YF_ERR_CATS.get("paket_ausnahme", 0) + 1
            for s in batch:
                out[s] = BATCH_ERR
            STATS.add(src, time.monotonic() - t0, 0)
            time.sleep(YF_PAUSE_S)
            continue
        _yf_errors_take(yf, batch)
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
        time.sleep(YF_PAUSE_S)
    return out


def yf_single(sym, start, end):
    """Einzelabruf über Ticker().history — True/False, Rate-Limit → RateLimited."""
    import yfinance as yf
    t0 = time.monotonic()
    _yf_errors_reset(yf)
    try:
        h = yf.Ticker(sym).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=False)
    except Exception as exc:  # noqa: BLE001
        if "RateLimit" in type(exc).__name__ or "Too Many Requests" in str(exc):
            raise RateLimited(str(exc)) from exc
        h = None
    _yf_errors_take(yf, [sym])
    STATS.add("yfinance_einzel", time.monotonic() - t0, 0)
    time.sleep(1.0)
    return h is not None and not h.empty and not h["Close"].dropna().empty


def stooq_hit(sym, start, end):
    """'daten' / 'leer' / 'key_noetig' / 'http_N' / 'nicht_erreichbar'."""
    url = STOOQ_URL.format(s=sym.lower().replace(".", "-"), a=start.strftime("%Y%m%d"),
                           b=end.strftime("%Y%m%d"))
    try:
        r = http("GET", url, "stooq")
    except RateLimited:
        raise
    except Exception:  # noqa: BLE001  Verbindungsfehler sind ein Befund
        return "nicht_erreichbar"
    finally:
        time.sleep(1.0)
    body = r.text.strip()
    if r.status_code != 200:
        return f"http_{r.status_code}"
    low = body.lower()
    if "limit" in low and "exceed" in low:
        raise RateLimited("Stooq: Tageslimit")
    if low.startswith("date,") and len(body.splitlines()) > 1:
        return "daten"
    if "apikey" in low or "api key" in low:
        return "key_noetig"
    return "leer"


# ── P1 ───────────────────────────────────────────────────────────────────────
def settlement_dates():
    st, rows = finra_all({"domainFilters": [{"fieldName": "symbolCode", "values": list(ANCHORS)}],
                          **date_filter(date(2016, 1, 1), date(2026, 12, 31))}, max_pages=4)
    return st, rows


def probe_p1(result):
    p1 = {"datensatz": DS}
    r = http("GET", FINRA_META.format(ds=DS), "finra_api")
    p1["metadata_http"] = r.status_code
    if r.status_code == 200:
        try:
            fields = r.json().get("fields") or []
            p1["felder"] = {f.get("name"): {k: v for k, v in f.items() if k != "name"} for f in fields}
        except (ValueError, AttributeError):
            p1["felder"] = r.text[:1500]
    st, rows = settlement_dates()
    p1["anker_http"] = st
    sdates = sorted({date.fromisoformat(pick(x, "date")[:10]) for x in rows
                     if pick(x, "symbol") == "AAPL" and pick(x, "date")})
    p1["stichtage"] = {"anzahl": len(sdates), "erster": str(sdates[0]) if sdates else None,
                       "letzter": str(sdates[-1]) if sdates else None,
                       "luecken_ueber_20_tage": [(str(a), str(b)) for a, b in zip(sdates, sdates[1:])
                                                 if (b - a).days > 20]}
    # Füllgrad je Quartal (erster Stichtag ab Quartalsbeginn), nur gelistete Stammaktien
    fill = {}
    flags_split, flags_rev = {}, {}
    patterns = {}
    cats_total = {}
    for y in range(2017, 2027):
        for m in (1, 4, 7, 10):
            d = first_on_or_after(sdates, date(y, m, 1))
            if d is None or (y == 2017 and m < 10) or d.year != y:
                continue
            f = get_file(d)
            stocks = {s: v for s, v in f.items() if v["market"] in LISTED_CODES and is_stock(s, v["name"])}
            n = len(stocks)
            fill[str(d)] = {
                "zeilen": len(f), "gelistet_stamm": n,
                "cur": round(sum(v["cur"] is not None for v in stocks.values()) / n, 4) if n else None,
                "adv": round(sum(v["adv"] is not None for v in stocks.values()) / n, 4) if n else None,
                "adv_gt0": round(sum(_pos(v["adv"]) for v in stocks.values()) / n, 4) if n else None,
                "dtc": round(sum(v["dtc"] is not None for v in stocks.values()) / n, 4) if n else None,
            }
            for v in f.values():
                flags_split[str(v["split"])] = flags_split.get(str(v["split"]), 0) + 1
                flags_rev[str(v["rev"])] = flags_rev.get(str(v["rev"]), 0) + 1
            if m == 7:
                for s, v in f.items():
                    if v["market"] in LISTED_CODES:
                        c = category(s, v["name"])
                        cats_total.setdefault(str(y), {})
                        cats_total[str(y)][c] = cats_total[str(y)].get(c, 0) + 1
                        if not _RE_COMMON_SYM.match(s):
                            pt = symbol_pattern(s)
                            e = patterns.setdefault(pt, {"n": 0, "beispiele": []})
                            e["n"] += 1
                            if len(e["beispiele"]) < 4:
                                e["beispiele"].append(f"{s} | {str(v['name'])[:40]} → {c}")
    p1["fuellgrad_je_quartal"] = fill
    p1["stockSplitFlag_werte"] = flags_split
    p1["revisionFlag_werte"] = flags_rev
    p1["kategorien_gelistet_juli"] = cats_total
    p1["symbol_muster_nicht_einfach"] = dict(sorted(patterns.items(), key=lambda kv: -kv[1]["n"])[:15])
    # Veröffentlichungs-Kalender / Glossar (FINRA-Seiten, Text um Schlüsselwörter)
    pages = {}
    for url in FINRA_PAGES:
        try:
            rr = http("GET", url, "finra_web", headers={"User-Agent": "Mozilla/5.0"})
            txt = re.sub(r"<[^>]+>", " ", rr.text)
            txt = re.sub(r"\s+", " ", txt)
            hits = []
            for m in re.finditer(r"(Split|Revision|Publication|Dissemination|Due Date|Settlement Date)", txt):
                hits.append(txt[max(0, m.start() - 160):m.start() + 240])
                if len(hits) >= 8:
                    break
            dates = re.findall(r"\b(?:\d{1,2}/\d{1,2}/20(?:2[5-7])|(?:January|February|March|April|May|June|"
                               r"July|August|September|October|November|December) \d{1,2}, 20(?:2[5-7]))\b", txt)
            pages[url] = {"http": rr.status_code, "ausschnitte": hits, "datumsangaben": dates[:120]}
        except RateLimited:
            raise
        except Exception as exc:  # noqa: BLE001
            pages[url] = {"fehler": str(exc)[:160]}
    p1["finra_seiten"] = pages
    result["P1"] = p1
    return sdates


def _pos(v):
    try:
        return float(v) > 0
    except (TypeError, ValueError):
        return False


# ── P2F: Abgangsrate ohne Kursquelle ─────────────────────────────────────────
def probe_p2f(result, sdates):
    out = {}
    vanished = {}
    for y in YEARS_F:
        base = first_on_or_after(sdates, date(y, 7, 1))
        if base is None:
            continue
        bf = get_file(base)
        universe = {s: v for s, v in bf.items() if v["market"] in LISTED_CODES and is_stock(s, v["name"])}
        dtcs = {s: dtc_of(v["cur"], v["adv"], v["dtc"]) for s, v in universe.items()}
        low, high, med = split_halves(dtcs)
        res_y = {"stichtag": str(base), "stammaktien_gelistet": len(universe), "dtc_median": med}
        for label, days in (("12m", 365), ("24m", 730)):
            later = first_on_or_after(sdates, base + timedelta(days=days))
            if later is None:
                res_y[label] = None
                continue
            lf = get_file(later)
            names = {}
            for s, v in lf.items():
                nk = name_key(v["name"])
                if nk:
                    names.setdefault(nk, set()).add(s)
            fates = {s: fate(s, v, lf, names) for s, v in universe.items()}

            def tally(members):
                m = [fates[s] for s in members]
                n = len(m)
                d = {k: m.count(k) for k in ("gelistet", "otc", "kuerzel_gewechselt",
                                             "neu_vergeben", "verschwunden")}
                d["abgang_gelistet"] = wilson(n - d["gelistet"], n)
                d["verschwunden_anteil"] = wilson(d["verschwunden"] + d["neu_vergeben"], n)
                return d
            mk = {}
            for s, v in universe.items():
                mk.setdefault(v["market"], []).append(s)
            res_y[label] = {"stichtag_spaeter": str(later), "gesamt": tally(list(universe)),
                            "dtc_niedrig": tally(low), "dtc_hoch": tally(high),
                            "je_marktcode": {k: tally(v) for k, v in sorted(mk.items())}}
            if label == "12m":
                vanished[y] = (base, sorted(s for s, f in fates.items()
                                            if f in ("verschwunden", "neu_vergeben")))
        out[str(y)] = res_y
        log(f"P2F {y}: {json.dumps(res_y.get('12m', {}) and res_y['12m']['gesamt'], default=str)}")
    out["hinweis"] = ("verschwunden = Delisting ODER Übernahme ODER Namens-/Kürzeländerung ohne "
                      "Namenstreffer; Datensatz hat kein CUSIP-Feld, Trennung nur über issueName")
    result["P2F"] = out
    return vanished


# ── P2Y: yfinance-Verfügbarkeit mit Kontrollgruppe ───────────────────────────
def probe_p2y(result, sdates):
    out = {}
    today = datetime.now(timezone.utc).date()
    last = max(d for d in sdates if d <= today)
    lf = get_file(last)
    ctrl_pop = [s for s, v in lf.items() if v["market"] in LISTED_CODES and is_stock(s, v["name"])]
    ctrl = draw_sample(ctrl_pop, 1, CONTROL_N)
    data = yf_download([yf_symbol(s) for s in ctrl], today - timedelta(days=AVAIL_WINDOW_DAYS), today)
    ok = [s for s in ctrl if data.get(yf_symbol(s)) is not BATCH_ERR]
    k = sum(1 for s in ok if data.get(yf_symbol(s)) is not None)
    w = wilson(k, len(ok))
    gueltig = bool(w and w["anteil"] >= CONTROL_MIN)
    miss_ctrl = [s for s in ok if data.get(yf_symbol(s)) is None]
    rec_ctrl = sum(yf_single(yf_symbol(s), today - timedelta(days=AVAIL_WINDOW_DAYS), today)
                   for s in miss_ctrl[:SINGLE_RECHECK_N])
    out["kontrolle"] = {"stichtag": str(last), "vorhanden": w, "kriterium_min": CONTROL_MIN,
                        "gueltig": gueltig, "fehlend_beispiele": miss_ctrl[:15],
                        "einzel_gegenprobe": {"geprueft": min(len(miss_ctrl), SINGLE_RECHECK_N),
                                              "gefunden": rec_ctrl}}
    log(f"P2Y Kontrolle: {json.dumps(out['kontrolle'], default=str)}")
    split_cands = []
    for y in YEARS_Y:
        base = first_on_or_after(sdates, date(y, 7, 1))
        bf = get_file(base)
        pop = {s: v for s, v in bf.items() if v["market"] in LISTED_CODES and is_stock(s, v["name"])}
        sample = draw_sample(pop, y)
        dtcs = {s: dtc_of(pop[s]["cur"], pop[s]["adv"], pop[s]["dtc"]) for s in sample}
        low, high, med = split_halves(dtcs)
        data = yf_download([yf_symbol(s) for s in sample], base, base + timedelta(days=AVAIL_WINDOW_DAYS))
        errored = {s for s in sample if data.get(yf_symbol(s)) is BATCH_ERR}
        sm = [s for s in sample if s not in errored]
        avail, price, plaus = {}, {}, {}
        for s in sm:
            df = data.get(yf_symbol(s))
            avail[s] = df is not None
            if df is not None:
                try:
                    price[s] = float(df["Close"].dropna().iloc[0])
                    adv = float(pop[s]["adv"] or 0)
                    vol = float(df["Volume"].head(20).mean())
                    plaus[s] = adv > 0 and VOL_PLAUS_BAND[0] <= vol / adv <= VOL_PLAUS_BAND[1]
                except Exception:  # noqa: BLE001
                    plaus[s] = False
                if "Stock Splits" in df:
                    spl = df["Stock Splits"]
                    for ts, f in spl[spl > 0].items():
                        split_cands.append((s, ts.date(), float(f)))
        missing = [s for s in sm if not avail[s]]
        rec = sum(yf_single(yf_symbol(s), base, base + timedelta(days=AVAIL_WINDOW_DAYS))
                  for s in draw_sample(missing, y + 500, SINGLE_RECHECK_N))

        def grp(members):
            m = [s for s in sm if s in members]
            return {"vorhanden": wilson(sum(avail[s] for s in m), len(m)),
                    "plausibel": wilson(sum(plaus.get(s, False) for s in m), len(m))}
        cheap = {s for s, p in price.items() if p < 5}
        out[str(y)] = {"stichtag": str(base), "grundgesamtheit": len(pop), "stichprobe": len(sample),
                       "abruf_fehler_ausgeschlossen": len(errored), "dtc_median": med,
                       "gesamt": grp(set(sm)), "dtc_niedrig": grp(low), "dtc_hoch": grp(high),
                       "preis_unter_5_vorhanden": len(cheap), "preis_ab_5_vorhanden": len(price) - len(cheap),
                       "einzel_gegenprobe": {"geprueft": min(len(missing), SINGLE_RECHECK_N), "gefunden": rec}}
        log(f"P2Y {y}: {json.dumps(out[str(y)]['gesamt'], default=str)}")
    out["fehlergruende_yfinance"] = {"anzahl": YF_ERR_CATS, "beispiele": YF_ERR_EXAMPLES}
    out["messung_gueltig"] = gueltig
    result["P2Y"] = out
    return split_cands


# ── P2K: Kurse für verschwundene Symbole ─────────────────────────────────────
def probe_p2k(result, vanished):
    out = {}
    stooq_state = None
    for y, (base, syms) in sorted(vanished.items()):
        if y > 2024:
            continue
        s_y = draw_sample(syms, y + 700, VANISHED_CHECK_N)
        end = base + timedelta(days=AVAIL_WINDOW_DAYS)
        yf_hits = sum(yf_single(yf_symbol(s), base, end) for s in s_y)
        st_res = {}
        if stooq_state != "nicht_erreichbar":
            for s in s_y[:STOOQ_CHECK_N]:
                h = stooq_hit(s, base, end)
                st_res[h] = st_res.get(h, 0) + 1
                if h == "nicht_erreichbar" and sum(st_res.values()) >= 3 and st_res.get("daten", 0) == 0:
                    stooq_state = "nicht_erreichbar"
                    break
        out[str(y)] = {"verschwunden_gesamt": len(syms), "geprueft": len(s_y),
                       "yfinance_einzel": wilson(yf_hits, len(s_y)), "stooq": st_res or stooq_state}
        log(f"P2K {y}: {json.dumps(out[str(y)], default=str)}")
    out["stooq_status"] = stooq_state or "erreichbar_oder_ungeprueft"
    out["tiingo_alphavantage"] = "nicht abgerufen (Key nötig)"
    result["P2K"] = out


# ── P3 ───────────────────────────────────────────────────────────────────────
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


def probe_p3(result, sdates):
    sec_map = sec_ticker_map(result)
    out = {"ticker_map_http": result.get("_sec_map_http"), "jahre": {}}
    for y in YEARS_Y:
        base = first_on_or_after(sdates, date(y, 7, 1))
        bf = get_file(base)
        pop = [s for s, v in bf.items() if v["market"] in LISTED_CODES and is_stock(s, v["name"])]
        sample = draw_sample(pop, y)
        mapped = {s: sec_map[yf_symbol(s)] for s in sample if yf_symbol(s) in sec_map}
        res = {"cik_zuordnung_aktuelle_liste": wilson(len(mapped), len(sample))}
        try:
            r = sec_get(SEC_FRAME.format(y=y))
            res["frame_http"] = r.status_code
            if r.status_code == 200:
                ciks = {int(d["cik"]) for d in r.json().get("data", [])}
                res["frame_deckung"] = wilson(sum(1 for c in mapped.values() if c in ciks), len(sample))
        except RateLimited:
            raise
        except Exception as exc:  # noqa: BLE001
            res["frame_fehler"] = str(exc)[:160]
        pit = checked = 0
        for s in draw_sample(mapped, y + 1000, SEC_PIT_SUBSAMPLE):
            r = sec_get(SEC_FACTS.format(cik=mapped[s]))
            if r.status_code == 403:
                res["companyfacts_403"] = True
                break
            checked += 1
            if r.status_code != 200:
                continue
            try:
                units = r.json()["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"]
            except (KeyError, ValueError, TypeError):
                continue
            pit += any(u.get("filed") and u.get("end") and date.fromisoformat(u["filed"]) <= base
                       and date.fromisoformat(u["end"]) >= base - timedelta(days=200) for u in units)
        res["pit_stichprobe"] = wilson(pit, checked) if checked else None
        out["jahre"][str(y)] = res
    result["P3"] = out


# ── P6 ───────────────────────────────────────────────────────────────────────
def probe_p6(result, sdates, yf_cands):
    out = {"flag_paare": {}}
    tally, examples = {}, []
    for y in (2019, 2021, 2023, 2025):
        a = first_on_or_after(sdates, date(y, 7, 1))
        b = first_on_or_after(sdates, a + timedelta(days=1)) if a else None
        if not a or not b:
            continue
        fa, fb = get_file(a), get_file(b)
        flagged = [s for s, v in fb.items() if str(v["split"]) not in ("None", "0", "", "N")]
        t = {}
        for s in flagged:
            if s in fa:
                k = classify_split_flag(fb[s]["prev"], fa[s]["cur"])
                t[k] = t.get(k, 0) + 1
                if len(examples) < 4:
                    examples.append({"symbol": s, "stichtag_vor": str(a), "stichtag_nach": str(b),
                                     "si_vor": fa[s]["cur"], "vorperiode_im_nach": fb[s]["prev"],
                                     "si_nach": fb[s]["cur"], "flag": fb[s]["split"], "klasse": k})
        out["flag_paare"][f"{a}→{b}"] = {"mit_flag": len(flagged), **t}
        for k, v in t.items():
            tally[k] = tally.get(k, 0) + v
    out["flag_gesamt"] = tally
    out["beispiele"] = examples
    out["yfinance_splits_im_p2y_fenster"] = len(yf_cands)
    result["P6"] = out


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


def probe_p5(result, sdates):
    real = real_top10()
    days = sorted(real)
    if not days:
        result["P5"] = {"fehlt": "keine echten Top-10 ab 01.07.2026"}
        return
    hol = frozenset(getattr(config, "US_MARKET_HOLIDAYS", ()))
    sets_ = [d for d in sdates if date(2026, 4, 15) <= d <= days[-1]]
    si = {d: get_file(d) for d in sets_}
    shares = {}
    r = sec_get(SEC_FRAME.format(y=2026))
    if r.status_code == 200:
        frame = {int(x["cik"]): float(x["val"]) for x in r.json().get("data", [])}
        shares = {t: frame[c] for t, c in sec_ticker_map(result).items() if c in frame}
    cand = set()
    for f in si.values():
        for s, v in f.items():
            sh = shares.get(yf_symbol(s))
            if (sh and _pos(v["cur"]) and float(v["cur"]) / sh * 100 >= config.MIN_SHORT_FLOAT
                    and v["market"] in LISTED_CODES and is_stock(s, v["name"])):
                cand.add(s)
    real_us = {d: {t for t in ts if "." not in t} for d, ts in real.items()}
    data = yf_download([yf_symbol(s) for s in sorted(cand)] + ["^GSPC"], days[0] - timedelta(days=45),
                       days[-1] + timedelta(days=1), src="yfinance_proxy", auto_adjust=True)
    spx = data.get("^GSPC")
    spx = None if spx is BATCH_ERR else spx
    pairs, in_uni = [], []
    for d in days:
        sd = latest_usable_settlement(d, sets_, hol)
        if sd is None or spx is None:
            continue
        prev = [x for x in sets_ if x < sd]
        sp = spx[spx.index.date <= d]
        if len(sp) < 22:
            continue
        spx_chg = (float(sp["Close"].iloc[-1]) / float(sp["Close"].iloc[-2]) - 1) * 100
        spx20 = (float(sp["Close"].iloc[-1]) / float(sp["Close"].iloc[-21]) - 1) * 100
        scored = []
        for s in cand:
            x = si[sd].get(s)
            df = data.get(yf_symbol(s))
            if x is None or df is None or df is BATCH_ERR:
                continue
            h = df[df.index.date <= d]
            if len(h) < 22 or h.index[-1].date() != d:
                continue
            close, opn, pc = float(h["Close"].iloc[-1]), float(h["Open"].iloc[-1]), float(h["Close"].iloc[-2])
            sh = shares.get(yf_symbol(s))
            if close < config.MIN_PRICE or not sh or close * sh > config.MAX_MARKET_CAP_B * 1e9:
                continue
            cur = float(x["cur"] or 0)
            si_pct = cur / sh * 100
            if si_pct < config.MIN_SHORT_FLOAT:
                continue
            vol20 = float(h["Volume"].iloc[-21:-1].mean())
            rvol = float(h["Volume"].iloc[-1]) / vol20 if vol20 > 0 else 0.0
            chg = (close / pc - 1) * 100
            perf20 = (close / float(h["Close"].iloc[-21]) - 1) * 100
            px = si[max(prev)].get(s) if prev else None
            si_up = px is not None and cur > float(px["cur"] or 0)
            sc = proxy_score(si_pct, dtc_of(x["cur"], x["adv"], x["dtc"]), rvol, chg - spx_chg,
                             gap_pts(opn, pc, close), rs_pts(perf20 - spx20), si_up)
            scored.append((sc, rvol >= config.MIN_REL_VOLUME, s))
        pref = sorted([t for t in scored if t[1]], reverse=True)
        rest = sorted([t for t in scored if not t[1]], reverse=True)
        pairs.append((real_us[d], {s for _, _, s in (pref + rest)[:10]}))
        in_uni.append((len(real_us[d] & {s for _, _, s in scored}), len(real_us[d])))
    result["P5"] = {
        "tage_echt": len(days), "tage_ausgewertet": len(pairs), "kandidaten_universum": len(cand),
        "aktien_aus_sec_frame": len(shares), "ueberschneidung_top10": overlap_stats(pairs),
        "echte_ticker_im_proxy_universum": {"treffer": sum(a for a, _ in in_uni),
                                           "von": sum(b for _, b in in_uni)},
        "nicht_us_ausgeschlossen": sum(len(real[d]) - len(real_us[d]) for d in days),
        "annahmen": "SI ab Stichtag + 8 Werktage; Aktienzahl aus Frame CY2026Q2I (Nähe dadurch eher "
                    "optimistisch); Short-Anteil = SI / ausstehende Aktien; ohne Float, Turnover, News, "
                    "KI, Malus, Glättung",
    }


# ── P7 ───────────────────────────────────────────────────────────────────────
def probe_p7(result):
    st = STATS.as_dict()
    yf = st.get("yfinance", {})
    n_sym = sum(v.get("stichprobe", 0) for v in result.get("P2Y", {}).values() if isinstance(v, dict))
    n_sym += CONTROL_N
    per_sym = yf["sekunden"] / n_sym if n_sym and yf else None
    b_per = yf["bytes"] / n_sym if n_sym and yf else None
    uni = max((v.get("stammaktien_gelistet", 0) for v in result.get("P2F", {}).values()
               if isinstance(v, dict)), default=0)
    fin = st.get("finra_api", {})
    result["P7"] = {
        "messung": st,
        "yfinance_sekunden_je_symbol_fenster": round(per_sym, 3) if per_sym else None,
        "hochrechnung_kurse_2018_2026": {
            "stammaktien_je_stichtag": uni,
            "symbole_ueber_9_jahre_geschaetzt_faktor_1_6": int(uni * 1.6),
            "minuten_bei_einem_abruf_je_symbol": round(per_sym * uni * 1.6 / 60, 1) if per_sym else None,
            "mb_im_speicher": round(b_per * uni * 1.6 * 252 * 9 / (AVAIL_WINDOW_DAYS * 5 / 7) / 1e6, 1)
            if b_per else None,
        },
        "finra_mb_je_stichtag_abruf": round(fin.get("bytes", 0) / max(1, len(FILE_CACHE)) / 1e6, 2) if fin else None,
        "finra_stichtage_gesamt": result.get("P1", {}).get("stichtage", {}).get("anzahl"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--nur", choices=("alle", "survivorship", "proxy"), default="alle",
                    help="survivorship = P2F/P2Y/P2K/P3/P6, proxy = P5 (P1 immer, P7 nur bei alle)")
    args = ap.parse_args(argv)
    if datetime.now(timezone.utc).date() > PROBE_END:
        log(f"no-op: nach {PROBE_END}")
        return 0
    t0 = time.monotonic()
    result = {"seed": SEED, "stichprobe_n": SAMPLE_N, "kontrolle_min": CONTROL_MIN, "nur": args.nur,
              "start_utc": datetime.now(timezone.utc).isoformat()}
    out = pathlib.Path(args.out)
    rc = 0
    try:
        start_section("P1")
        sdates = probe_p1(result)
        section_done(result, "P1")
        if sdates and args.nur in ("alle", "survivorship"):
            start_section("P2F")
            vanished = probe_p2f(result, sdates)
            section_done(result, "P2F")
            start_section("P2Y")
            cands = probe_p2y(result, sdates)
            section_done(result, "P2Y")
            start_section("P2K")
            probe_p2k(result, vanished)
            section_done(result, "P2K")
            start_section("P3")
            probe_p3(result, sdates)
            section_done(result, "P3")
            start_section("P6")
            probe_p6(result, sdates, cands)
            section_done(result, "P6")
        if sdates and args.nur in ("alle", "proxy"):
            start_section("P5")
            probe_p5(result, sdates)
            section_done(result, "P5")
        if args.nur == "alle":
            start_section("P7")
            probe_p7(result)
            section_done(result, "P7")
    except RateLimited as exc:
        result["abgebrochen_in"] = CURRENT["abschnitt"]
        result["abbruch_grund"] = str(exc)[:300]
        for k in ("P1", "P2F", "P2Y", "P2K", "P3", "P5", "P6", "P7"):
            if k not in result.get("abschnitte_vollstaendig", []):
                result.pop(k, None)
        log(f"ABBRUCH Rate-Limit in {CURRENT['abschnitt']} — nicht gezählt; "
            f"vollständig: {result.get('abschnitte_vollstaendig', [])}; Grund: {exc}")
        rc = 3
    result.pop("_sec_map_http", None)
    result["finra_ersatzfilter_genutzt"] = FALLBACK_USED
    result["finra_letzte_fehler"] = LAST_ERR
    result["laufzeit_s"] = round(time.monotonic() - t0, 1)
    log("meta " + json.dumps({k: result.get(k) for k in (
        "finra_ersatzfilter_genutzt", "finra_letzte_fehler", "laufzeit_s")}, default=str))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    log(f"{'abgebrochen' if rc else 'fertig'} in {result['laufzeit_s']} s → {out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
