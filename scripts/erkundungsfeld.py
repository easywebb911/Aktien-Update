#!/usr/bin/env python3
"""Erkundungsfeld 2025/26 — Stufe 1 (Easy-Entscheid 16./17.11.2026, PR B).

ZIEL: eine belastbare Zahl, ob eine aus FINRA + Yahoo nachgebaute Kandidaten-
liste unsere echte Top-10 abbildet. Stufe 1 lädt KEINE Kurse nach dem
jeweiligen Listentag und rechnet KEINE Renditen oder Treffer.

ABLAUF (Hand-Start, Workflow ``erkundungsfeld.yml``):
  1. FINRA ``consolidatedShortInterest`` je Stichtag (gelistete Stammaktien).
  2. SEC XBRL-Frames ``EntityCommonStockSharesOutstanding`` je Quartal +
     ``company_tickers.json`` → Vorfilter FINRA-Bestand / Aktienzahl >= 5 %
     (Easy-Entscheid 17.11.2026 „Hybrid“; Aktienzahl nur, wenn Periodenende
     + 90 Tage <= Nutzbar-ab des Stichtags — kein Look-ahead).
  3. Yahoo-Tageskurse je Ticker in EINEM Abruf (Variante A), harte Obergrenze
     02.07.2026 (Feld) bzw. 23.10.2026 (Namensvergleich). Merkmale für Tag t
     nur aus Zeilen <= t (Kürzungstest im Mock-Test).
  4. Heutiger Yahoo-Float (+ Aktienzahl) nur für vorgefilterte Ticker mit
     Kursen; gekennzeichnet „Nenner heutig“. Rate-Limit → kein Retry, Rest Lücke.
  5. Je Handelstag: Stock-Dict mit den nachbildbaren Feldern → unveränderte
     ``generate_report.score()`` → Filter → 30 Namen mit Rang.
  6. Namensvergleich 21.07.–23.10.2026: echte Top-10 (Export, provenance
     forward) gegen die ersten 10/20/30 je Tag. Median + Verteilung.
  7. Lücke: Kandidaten ohne Yahoo-Kurse je Monat.

SCHWELLE (vorab festgeschrieben, Easy 16.11.2026): Median der echten Top-10-
Namen unter den ersten 30 der Annäherung >= 5 → bestanden; 3–4 → Grenzfall
(Easy entscheidet); < 3 → nicht weiterbauen.

FINRA-Nutzbarkeit: Stichtag + 7 US-Handelstage (``finra_publication_date``-
Regel) = Veröffentlichung; nutzbar ab dem Handelstag DANACH (+1 Tag Puffer).
Sonderschließung 09.01.2025 (Staatstrauertag) wird nur hier geführt.

Kein Score-/Filter-/Push-/Anzeige-Effekt im Tool. Nichts liest diese Dateien.
"""
from __future__ import annotations

import bisect
import contextlib
import functools
import gzip
import io
import json
import math
import os
import re
import statistics
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import (  # noqa: E402
    FINRA_PUB_OFFSET_BUSINESS_DAYS,
    SI_TREND_DOWN_THRESHOLD,
    SI_TREND_UP_THRESHOLD,
    SQUEEZE_DETECTION_DAYS,
    SQUEEZE_MIN_GAIN,
    SQUEEZE_MIN_RVOL,
    US_MARKET_HOLIDAYS,
)

# ── Festgeschriebene Rahmen (Easy 16./17.11.2026) ────────────────────────────
FIELD_START = date(2025, 1, 2)
FIELD_END = date(2026, 7, 2)          # harte Obergrenze Kurse fürs Feld
WIN_START = date(2026, 7, 21)
WIN_END = date(2026, 10, 23)          # harte Obergrenze Kurse für den Namensvergleich
FIELD_FETCH_START = date(2024, 11, 15)  # 20-Tage-Fenster + Squeeze-Rückblick
WIN_FETCH_START = date(2026, 2, 20)     # 90-Tage-Squeeze-Rückblick vor 21.07.
FINRA_FROM = date(2024, 10, 1)
EXTRA_CLOSED = frozenset({"2025-01-09"})   # Staatstrauertag, nicht in config
SEC_LAG_DAYS = 90
PREFILTER_SEC_PCT = 5.0
MIN_PRICE = 1.0
MIN_RVOL = 1.5
MIN_SI_PCT = 15.0
MAX_MCAP = 2e9
MIN_AVG_VOL = 300_000
TOP_N = 30
SCHWELLE_BESTANDEN = 5
SCHWELLE_GRENZFALL = 3
LISTED_CODES = frozenset({"NYSE", "NNM", "SC", "AMEX", "ARCA", "BZX", "NMS", "NGM", "NCM", "IEX", "BATS"})
_RE_COMMON = re.compile(r"^[A-Z]{1,5}$")

FINRA_URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_FRAME = "https://data.sec.gov/api/xbrl/frames/dei/EntityCommonStockSharesOutstanding/shares/CY{y}Q{q}I.json"
OUT_DIR = ROOT / "erkundungsfeld"
YF_BATCH = 100
YF_PAUSE_S = 2.0
INFO_PAUSE_S = 0.4

F_SYMBOL = ("symbolCode", "issueSymbolIdentifier", "symbol")
F_DATE = ("settlementDate",)
F_QTY = ("currentShortPositionQuantity", "currentShortShareNumber")
F_DTC = ("daysToCoverQuantity", "daysToCoverNumber")
F_ADV = ("averageDailyVolumeQuantity", "averageShortShareNumber")
F_MARKET = ("marketClassCode", "marketCategoryCode")
F_SPLIT = ("stockSplitFlag",)


class RateLimited(Exception):
    pass


def log(msg: str) -> None:
    print(f"[erkundungsfeld] {msg}", flush=True)


def _pick(rec, keys):
    for k in keys:
        if k in rec:
            return rec[k]
    return None


def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ── Kalender ────────────────────────────────────────────────────────────────
def is_trading_day(d: date) -> bool:
    iso = d.isoformat()
    return d.weekday() < 5 and iso not in US_MARKET_HOLIDAYS and iso not in EXTRA_CLOSED


def next_trading_day(d: date) -> date:
    c = d + timedelta(days=1)
    while not is_trading_day(c):
        c += timedelta(days=1)
    return c


def trading_days(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def publication_date(settlement: date) -> date:
    d = settlement
    for _ in range(FINRA_PUB_OFFSET_BUSINESS_DAYS):
        d = next_trading_day(d)
    return d


@functools.lru_cache(maxsize=None)
def usable_from(settlement: date) -> date:
    """Handelstag NACH der Veröffentlichung (+1 Tag Puffer, Plan §2)."""
    return next_trading_day(publication_date(settlement))


# ── FINRA ───────────────────────────────────────────────────────────────────
def normalize_finra(rows) -> dict:
    """Rohzeilen eines Stichtags → {sym: {qty, dtc, adv, split}}; nur gelistete Stammaktien."""
    out = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        sym = str(_pick(r, F_SYMBOL) or "").strip().upper()
        if not _RE_COMMON.match(sym):
            continue
        if str(_pick(r, F_MARKET) or "") not in LISTED_CODES:
            continue
        qty = _num(_pick(r, F_QTY))
        if qty is None or qty < 0:
            continue
        split = _pick(r, F_SPLIT)
        out[sym] = {"qty": int(qty), "dtc": _num(_pick(r, F_DTC)), "adv": _num(_pick(r, F_ADV)),
                    "split": (str(split).strip() or None) if split not in (None, "") else None}
    return out


def finra_fields_ok(rows) -> bool:
    """Probe: erwartete Felder vorhanden (sonst Abbruch vor dem Lauf)."""
    if not rows:
        return False
    r = rows[0]
    return all(_pick(r, f) is not None for f in (F_SYMBOL, F_DATE, F_QTY, F_MARKET))


def _finra_post(body, post_fn):
    r = post_fn(FINRA_URL, json=body, timeout=60,
                headers={"Accept": "application/json", "Content-Type": "application/json"})
    if r.status_code == 429:
        raise RateLimited("FINRA HTTP 429")
    if r.status_code == 204:
        return []
    if r.status_code != 200:
        raise RuntimeError(f"FINRA HTTP {r.status_code}")
    data = r.json() if (r.text or "").strip() else []
    if not isinstance(data, list):
        raise RuntimeError("FINRA Antwort keine Liste")
    return data


def finra_settlement(d: date, post_fn, page: int = 5000, max_pages: int = 40) -> list:
    rows, off = [], 0
    for _ in range(max_pages):
        data = _finra_post({"limit": page, "offset": off, "compareFilters": [
            {"compareType": "EQUAL", "fieldName": "settlementDate", "fieldValue": d.isoformat()}]},
            post_fn)
        rows += data
        if len(data) < page:
            return rows
        off += page
        time.sleep(0.3)
    return rows


def finra_settlement_dates(post_fn, start: date, end: date) -> list[date]:
    """Stichtage über einen liquiden Anker (AAPL) ermitteln."""
    data = _finra_post({"limit": 200, "compareFilters": [
        {"compareType": "EQUAL", "fieldName": "symbolCode", "fieldValue": "AAPL"}],
        "dateRangeFilters": [{"fieldName": "settlementDate", "startDate": start.isoformat(),
                              "endDate": end.isoformat()}]}, post_fn)
    out = set()
    for r in data:
        try:
            out.add(date.fromisoformat(str(_pick(r, F_DATE))[:10]))
        except ValueError:
            continue
    return sorted(out)


def usable_records(finra: dict, sym: str, t: date):
    """Jüngster und zweitjüngster am Tag t nutzbare Stand eines Tickers."""
    got = []
    for sd in sorted(finra, reverse=True):
        if usable_from(sd) <= t and sym in finra[sd]:
            got.append((sd, finra[sd][sym]))
            if len(got) == 2:
                break
    cur = got[0] if got else None
    prev = got[1] if len(got) > 1 else None
    return cur, prev


def si_trend(cur, prev) -> str:
    if not cur or not prev or not prev[1]["qty"]:
        return "no_data"
    ch = (cur[1]["qty"] - prev[1]["qty"]) / prev[1]["qty"]
    if ch >= SI_TREND_UP_THRESHOLD:
        return "up"
    if ch <= SI_TREND_DOWN_THRESHOLD:
        return "down"
    return "sideways"


# ── SEC (Vorfilter) ─────────────────────────────────────────────────────────
def sec_quarters(start: date, end: date) -> list[tuple[int, int]]:
    out, y, q = [], start.year, (start.month - 1) // 3 + 1
    while (y, q) <= (end.year, (end.month - 1) // 3 + 1):
        out.append((y, q))
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


def sec_shares_known(sec: dict, cik: int, at: date):
    """Jüngste SEC-Aktienzahl mit Periodenende + SEC_LAG_DAYS <= at."""
    best = None
    for end, val in sec.get(cik, []):
        if end + timedelta(days=SEC_LAG_DAYS) <= at and (best is None or end > best[0]):
            best = (end, val)
    return best[1] if best else None


# ── Merkmale aus Tageskursen (nur Zeilen <= t) ──────────────────────────────
def detect_recent_squeeze(closes: list, vols: list):
    """Wie generate_report._detect_recent_squeeze (dort verschachtelt, nicht
    importierbar); dieselben config-Konstanten, dieselbe Logik."""
    if len(closes) < 26 or len(vols) < 26:
        return None
    max_offset = min(SQUEEZE_DETECTION_DAYS, len(closes) - 6)
    for offset in range(0, max_offset):
        end_i = len(closes) - 1 - offset
        start_i = end_i - 5
        if start_i < 20:
            break
        c0, c1 = closes[start_i], closes[end_i]
        if not c0 or c0 <= 0:
            continue
        gain = (c1 - c0) / c0
        if gain < SQUEEZE_MIN_GAIN:
            continue
        win_vol = sum(vols[start_i:end_i + 1]) / (end_i + 1 - start_i)
        prior_vol = sum(vols[start_i - 20:start_i]) / 20
        if prior_vol <= 0 or win_vol < SQUEEZE_MIN_RVOL * prior_vol:
            continue
        return {"found": True, "days_ago": offset, "gain_pct": round(gain * 100, 1)}
    return None


_DATES: dict = {}


def _rows_upto(bars: list, t: date) -> list:
    key = id(bars)
    ds = _DATES.get(key)
    if ds is None or ds[0] is not bars:
        ds = (bars, [b[0] for b in bars])
        _DATES[key] = ds
    return bars[:bisect.bisect_right(ds[1], t)]


def features_at(bars: list, t: date, with_squeeze: bool = True):
    """``bars`` = [(date, o, h, l, c, v)] aufsteigend. Nur Zeilen <= t.
    None, wenn t selbst keine vollständige Zeile hat oder < 21 Zeilen."""
    rows = _rows_upto(bars, t)
    if len(rows) < 21 or rows[-1][0] != t:
        return None
    d, o, h, l, c, v = rows[-1]
    if not all(_num(x) for x in (o, c)) or _num(v) is None:
        return None
    prior = rows[-21:-1]
    avg20 = sum(r[5] or 0 for r in prior) / 20
    prev_close = rows[-2][4]
    if not prev_close or not avg20:
        return None
    c20 = rows[-21][4]
    sq = None
    if with_squeeze:
        sq = detect_recent_squeeze([r[4] for r in rows], [r[5] or 0 for r in rows])
    return {
        "price": c, "cur_open": o, "prev_close": prev_close, "cur_vol": v,
        "avg_vol_20d": avg20, "rel_volume": v / avg20,
        "change": (c / prev_close - 1) * 100,
        "perf_20d": (c / c20 - 1) * 100 if c20 else None,
        "recent_squeeze": sq,
    }


def build_stock(sym, feat, spx, cur, prev, float_today, shares_today) -> dict:
    """Stock-Dict für generate_report.score() (Felder laut Guardian-Liste)."""
    qty = cur[1]["qty"]
    sf = qty / float_today * 100 if float_today else None
    rs = (feat["perf_20d"] - spx["perf_20d"]) if (feat.get("perf_20d") is not None
                                                  and spx.get("perf_20d") is not None) else None
    return {
        "ticker": sym,
        "short_float": sf or 0.0,
        "short_ratio": cur[1]["dtc"] or 0.0,
        "rel_volume": feat["rel_volume"],
        "float_shares": float_today or 0,
        "cur_vol": feat["cur_vol"],
        "change": feat["change"],
        "spx_daily_perf": spx["change"],
        "finra_data": {"trend": si_trend(cur, prev)},
        "recent_squeeze": feat["recent_squeeze"],
        "cur_open": feat["cur_open"], "prev_close": feat["prev_close"], "price": feat["price"],
        "rel_strength_20d": rs,
        "_sf": sf, "_mcap": feat["price"] * shares_today if shares_today else None,
    }


def passes_filter(st: dict, avg_vol: float) -> bool:
    return (st["price"] >= MIN_PRICE and st["rel_volume"] >= MIN_RVOL
            and st["_sf"] is not None and st["_sf"] >= MIN_SI_PCT
            and st["_mcap"] is not None and st["_mcap"] < MAX_MCAP
            and avg_vol >= MIN_AVG_VOL)


def _score_fn():
    import generate_report as gr
    return gr.score


def rank_day(t, tickers, bars, spx_feat, finra, float_map, score_fn,
             prefilter_ok=None, splits=None, cap=None, luecken=None):
    """Kandidatenliste Tag t: (liste[(rang, sym, score, merkmale)], ohne_kurs[sym])."""
    cands, ohne_kurs = score_candidates(t, tickers, bars, spx_feat, finra, float_map, score_fn,
                                        prefilter_ok=prefilter_ok, splits=splits, cap=cap,
                                        luecken=luecken)
    return [(i + 1, s, round(sc, 2), m) for i, (sc, s, m) in enumerate(cands[:TOP_N])], ohne_kurs


def score_candidates(t, tickers, bars, spx_feat, finra, float_map, score_fn,
                     prefilter_ok=None, splits=None, cap=None, luecken=None):
    """ALLE Kandidaten von Tag t, die den Filter bestehen, sortiert (Score ab,
    Ticker auf): (liste[(score, sym, merkmale)], ohne_kurs[sym]).

    ``prefilter_ok``: Menge (stichtag, sym), die den SEC-Vorfilter mit dem am
    Nutzbar-ab bekannten Stand bestanden haben — Vorfilter je Tag point-in-time
    (Guardian #736). ``luecken``: dict, zählt ``ohne_float`` (Kurs da, Float fehlt).
    """
    cands, ohne_kurs = [], []
    for sym in sorted(tickers):
        cur, prev = usable_records(finra, sym, t)
        if not cur:
            continue
        if prefilter_ok is not None and (cur[0], sym) not in prefilter_ok:
            continue
        if sym not in bars:
            ohne_kurs.append(sym)
            continue
        feat = features_at(bars[sym], t, with_squeeze=False)
        if feat is None:
            continue
        fl, sh = float_map.get(sym, (None, None))
        if not fl and luecken is not None:
            luecken["ohne_float"] = luecken.get("ohne_float", 0) + 1
        st = build_stock(sym, feat, spx_feat, cur, prev, fl, sh)
        if not passes_filter(st, feat["avg_vol_20d"]):
            continue
        # Squeeze-Erkennung erst nach dem Filter (Laufzeit; gleiche Zeilen <= t)
        st["recent_squeeze"] = features_at(bars[sym], t)["recent_squeeze"]
        with contextlib.redirect_stdout(io.StringIO()):
            sc = score_fn(st)
        cands.append((sc, sym, {
            "dtc": cur[1]["dtc"], "si": cur[1]["qty"], "si_stichtag": cur[0].isoformat(),
            "si_nutzbar_ab": usable_from(cur[0]).isoformat(), "si_split": cur[1]["split"],
            "si_trend": st["finra_data"]["trend"], "rvol20": round(feat["rel_volume"], 3),
            "chg_rel_spy": round(feat["change"] - spx_feat["change"], 3),
            "rs_spy": None if st["rel_strength_20d"] is None else round(st["rel_strength_20d"], 3),
            "sf_naeherung": round(st["_sf"], 3), "mcap_naeherung": round(st["_mcap"]),
            "float_heute": fl, "kennz": "Nenner heutig",
            # Yahoo-Kurse sind split-bereinigt bis zur Abruf-Obergrenze; FINRA-Bestand nicht.
            "split_nach_tag": bool(splits and cap and any(t < x <= cap for x in splits.get(sym, ()))),
            "split_seit_stichtag": bool(splits and any(cur[0] < x for x in splits.get(sym, ())))}))
    cands.sort(key=lambda x: (-x[0], x[1]))
    return cands, ohne_kurs


# ── Namensvergleich ─────────────────────────────────────────────────────────
def real_top10(export_path, start: date, end: date) -> dict:
    """{date: [ticker…]} echte Top-10 (Export, provenance forward), nach pool_position."""
    by = {}
    with open(export_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("provenance") != "forward":
                continue
            try:
                dd, mm, yy = str(e["date"]).split(".")
                d = date(int(yy), int(mm), int(dd))
            except (KeyError, ValueError):
                continue
            if start <= d <= end:
                by.setdefault(d, []).append((e.get("pool_position") or 99, e["ticker"]))
    return {d: [t for _, t in sorted(set(v))][:10] for d, v in sorted(by.items())}


def compare(lists: dict, real: dict) -> dict:
    rows = []
    for d in sorted(real):
        if d not in lists:
            continue
        names = [s for _, s, *_ in lists[d]]
        r = set(real[d])
        rows.append({"date": d.isoformat(), "top10": len(r & set(names[:10])),
                     "top20": len(r & set(names[:20])), "top30": len(r & set(names[:30])),
                     "n_liste": len(names)})
    def dist(k):
        vals = [x[k] for x in rows]
        return {"median": statistics.median(vals) if vals else None,
                "min": min(vals) if vals else None, "max": max(vals) if vals else None,
                "verteilung": {str(i): vals.count(i) for i in range(11)}}
    return {"tage": len(rows), "je_tag": rows,
            "top10": dist("top10"), "top20": dist("top20"), "top30": dist("top30")}


def verdict(median30, vollstaendig: bool = True) -> str:
    if not vollstaendig:
        return "unvollstaendig"
    if median30 is None:
        return "nicht_messbar"
    if median30 >= SCHWELLE_BESTANDEN:
        return "bestanden"
    if median30 >= SCHWELLE_GRENZFALL:
        return "grenzfall"
    return "nicht_weiterbauen"


# ── Yahoo ───────────────────────────────────────────────────────────────────
STOPS: list = []      # Abbruchgründe (Zeitlimit/Rate-Limit/Quellen-Fehler) → Urteil „unvollstaendig“


def fetch_bars(symbols, start: date, end_incl: date, cap: date, deadline=None,
               splits_out=None) -> tuple[dict, list]:
    """Ein Abruf je Ticker (Pakete à YF_BATCH). ``end_incl`` > ``cap`` → Abbruch
    (harter Riegel). Rate-Limit → kein Retry, Rest als ``nicht_abgerufen``."""
    if end_incl > cap:
        raise ValueError(f"Kurs-Obergrenze verletzt: {end_incl} > {cap}")
    import yfinance as yf
    out, missing = {}, []
    syms = sorted(symbols)
    for i in range(0, len(syms), YF_BATCH):
        batch = syms[i:i + YF_BATCH]
        if deadline and time.monotonic() > deadline:
            missing += syms[i:]
            log("Zeitlimit Kurse erreicht")
            STOPS.append("zeitlimit_kurse")
            break
        try:
            shared = getattr(yf, "shared", None)
            if shared is not None and isinstance(getattr(shared, "_ERRORS", None), dict):
                shared._ERRORS.clear()
            df = yf.download(batch, start=start.isoformat(),
                             end=(end_incl + timedelta(days=1)).isoformat(), interval="1d",
                             auto_adjust=True, actions=True, group_by="ticker", threads=True,
                             progress=False)
        except Exception as exc:  # noqa: BLE001
            if "RateLimit" in type(exc).__name__ or "Too Many Requests" in str(exc):
                log("Yahoo Rate-Limit (Kurse) — kein Retry")
                missing += syms[i:]
                STOPS.append("rate_limit_kurse")
                break
            missing += batch
            continue
        if _yf_rate_limited(yf):
            log("Yahoo Rate-Limit (Kurse, gemeldet) — kein Retry")
            missing += syms[i:]
            STOPS.append("rate_limit_kurse")
            break
        for s in batch:
            rows = _df_rows(df, s, len(batch) > 1, end_incl, splits_out)
            if rows:
                out[s] = rows
            else:
                missing.append(s)
        time.sleep(YF_PAUSE_S)
    return out, sorted(set(missing))


def _df_rows(df, sym, multi, end_incl, splits_out=None):
    """Zeilen eines Tickers; Ticker-Level immer über die Spalten auflösen
    (auch bei einem einzelnen Ticker liefert yfinance oft MultiIndex)."""
    try:
        cols = df.columns
        if getattr(cols, "nlevels", 1) > 1:
            if sym not in cols.get_level_values(0):
                return []
            sub = df[sym]
        else:
            sub = df
        sub = sub.dropna(subset=["Close"])
    except Exception:  # noqa: BLE001
        return []
    rows = []
    for idx, r in sub.iterrows():
        d = idx.date()
        if d > end_incl:
            continue
        sp = _num(r.get("Stock Splits"))
        if sp and splits_out is not None:
            splits_out.setdefault(sym, []).append(d)
        rows.append((d, _num(r.get("Open")), _num(r.get("High")), _num(r.get("Low")),
                     _num(r.get("Close")), _num(r.get("Volume"))))
    return rows


def _yf_rate_limited(yf) -> bool:
    """yf.download wirft bei Rate-Limit oft nicht, sondern meldet es in shared._ERRORS."""
    errs = getattr(getattr(yf, "shared", None), "_ERRORS", None) or {}
    return any("Rate" in str(m) or "Too Many Requests" in str(m) for m in errs.values())


def fetch_float_today(symbols, deadline=None) -> tuple[dict, list]:
    import yfinance as yf
    out, missing = {}, []
    syms = sorted(symbols)
    for i, s in enumerate(syms):
        if deadline and time.monotonic() > deadline:
            missing += syms[i:]
            STOPS.append("zeitlimit_float")
            break
        try:
            info = yf.Ticker(s).info or {}
        except Exception as exc:  # noqa: BLE001
            if "RateLimit" in type(exc).__name__ or "Too Many Requests" in str(exc):
                log("Yahoo Rate-Limit (Float) — kein Retry")
                missing += syms[i:]
                STOPS.append("rate_limit_float")
                break
            missing.append(s)
            continue
        fl, sh = _num(info.get("floatShares")), _num(info.get("sharesOutstanding"))
        if fl and fl > 0:
            out[s] = (fl, sh if sh and sh > 0 else None)
        else:
            missing.append(s)
        time.sleep(INFO_PAUSE_S)
    return out, missing


# ── Fehl-Analyse (Easy-Entscheid 17.11.2026, nur Namen) ──────────────────────
# Je echtem Top-10-Namen eines Vergleichstags, der NICHT unter den ersten 30
# der Annäherung steht, genau EINE Kategorie (erste Stufe, an der er
# herausfällt). Keine Kurse nach dem Listentag, keine Renditen, keine Treffer.
KAT_FINRA, KAT_SEC, KAT_VORFILTER, KAT_YAHOO, KAT_FILTER, KAT_RANG = 1, 2, 3, 4, 5, 6
KAT_NAMEN = {
    KAT_FINRA: "nicht in der FINRA-Liste / Kürzel-Abweichung",
    KAT_SEC: "kein SEC-Nenner (Aktienzahl) — Vorfilter",
    KAT_VORFILTER: "Vorfilter FINRA-Bestand / Aktienzahl < 5 %",
    KAT_YAHOO: "kein Float heute / kein Yahoo-Kurs",
    KAT_FILTER: "am nachgebildeten Filter gescheitert",
    KAT_RANG: "im Rennen, aber Rang > 30",
}
# Nur diese Export-Felder werden gelesen (Merkmale vom Listentag; nie Renditen).
EXPORT_FELDER_ERLAUBT = ("ticker", "date", "provenance", "pool_position", "source_pools",
                         "short_float", "short_float_source", "rvol", "entry_price", "dtc")


def filter_failures(st: dict, avg_vol: float) -> list[str]:
    """Alle nicht erfüllten Filterbedingungen, feste Reihenfolge wie ``passes_filter``."""
    out = []
    if not st["price"] >= MIN_PRICE:
        out.append("kurs")
    if not st["rel_volume"] >= MIN_RVOL:
        out.append("rvol")
    if st["_sf"] is None or not st["_sf"] >= MIN_SI_PCT:
        out.append("short_float")
    if st["_mcap"] is None or not st["_mcap"] < MAX_MCAP:
        out.append("marktwert")
    if not avg_vol >= MIN_AVG_VOL:
        out.append("durchschnittsvolumen")
    return out


def classify_miss(t, sym, finra, tick, sec, bars, float_map, spx_feat, ranks,
                  candidates=None) -> dict:
    """Eine Kategorie je (Tag, echter Name). ``ranks`` = {sym: rang} ALLER Kandidaten
    von Tag t. Rang <= TOP_N → ``None`` (kein Fehlfall). ``candidates`` = das
    Kandidatenset der Pipeline (``win_t``): ein Name, der den Vorfilter besteht,
    aber außerhalb liegt (jüngster Stichtag zu alt, Guardian #739), wird in der
    Pipeline nie bewertet → Kategorie 1 (erst NACH den Vorfilter-Stufen geprüft,
    damit Kategorie 2/3 erhalten bleiben)."""
    cur, prev = usable_records(finra, sym, t)
    if not cur:
        if not _RE_COMMON.match(sym):
            det = "Kürzelformat (Klasse/Ausland)"
        elif any(sym in recs for recs in finra.values()):
            det = "am Tag kein nutzbarer Stichtag"
        else:
            det = "nie in gelisteten FINRA-Stammaktien"
        return {"kat": KAT_FINRA, "detail": det}
    cik = tick.get(sym)
    sh = sec_shares_known(sec, cik, usable_from(cur[0])) if cik else None
    if not sh:
        return {"kat": KAT_SEC, "detail": "kein CIK" if not cik else "keine Aktienzahl",
                "si": cur[1]["qty"]}
    pct = cur[1]["qty"] / sh * 100
    if pct < PREFILTER_SEC_PCT:
        return {"kat": KAT_VORFILTER, "detail": f"{pct:.1f} %", "si": cur[1]["qty"]}
    # Vorfilter am Tag-t-Stichtag bestanden, aber nicht im Kandidatenset der
    # Pipeline (``win_t`` enthält nur Stichtage mit Nutzbar-ab im Fenster) →
    # in der Pipeline nie bewertet: Kategorie 1, nicht 6 (Guardian #739).
    if candidates is not None and sym not in candidates:
        return {"kat": KAT_FINRA, "detail": "Stichtag veraltet (nicht im Kandidatenset)"}
    feat = features_at(bars[sym], t, with_squeeze=False) if sym in bars else None
    fl, sh_today = float_map.get(sym, (None, None))
    # „kein Float heute“ zählt hier zu Kategorie 4 (Easys Kategorienliste). In der
    # Pipeline scheitert so ein Name erst am Filter (_sf=None) — gleiches Ergebnis.
    if feat is None:
        return {"kat": KAT_YAHOO, "detail": "kein Yahoo-Kurs am Tag"}
    if not fl:
        return {"kat": KAT_YAHOO, "detail": "kein Float heute"}
    st = build_stock(sym, feat, spx_feat, cur, prev, fl, sh_today)
    fails = filter_failures(st, feat["avg_vol_20d"])
    if fails:
        return {"kat": KAT_FILTER, "detail": fails[0], "alle": fails,
                "werte": {"kurs": round(st["price"], 4), "rvol": round(st["rel_volume"], 3),
                          "sf_naeherung": round(st["_sf"], 2) if st["_sf"] is not None else None,
                          "mcap_naeherung": round(st["_mcap"]) if st["_mcap"] else None,
                          "avg_vol_20d": round(feat["avg_vol_20d"])}}
    rang = ranks.get(sym)
    if rang is not None and rang <= TOP_N:
        return None
    return {"kat": KAT_RANG, "detail": f"Rang {rang}" if rang else "ohne Rang", "rang": rang}


def tool_values(export_path, start: date, end: date) -> dict:
    """{(date, ticker): Merkmale} der echten Top-10 — nur ``EXPORT_FELDER_ERLAUBT``."""
    out = {}
    with open(export_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            e = {k: e.get(k) for k in EXPORT_FELDER_ERLAUBT}
            if e["provenance"] != "forward":
                continue
            try:
                dd, mm, yy = str(e["date"]).split(".")
                d = date(int(yy), int(mm), int(dd))
            except ValueError:
                continue
            if start <= d <= end:
                out[(d, e["ticker"])] = {k: e[k] for k in ("source_pools", "short_float",
                                                           "short_float_source", "rvol",
                                                           "entry_price", "dtc")}
    return out


def summarize_misses(cases: list[dict], n_top: int = 10) -> dict:
    """Tabelle: Fälle je Kategorie, Anteil, die häufigsten Ticker je Kategorie
    (und je Filter-Bedingung). Deterministisch sortiert."""
    from collections import Counter
    total = len(cases)
    out = {"faelle": total, "kategorien": {}}
    for k in sorted(KAT_NAMEN):
        sub = [c for c in cases if c["kat"] == k]
        tick = Counter(c["ticker"] for c in sub)
        det = Counter(c["detail"] for c in sub) if k != KAT_RANG else None
        row = {"name": KAT_NAMEN[k], "faelle": len(sub),
               "anteil_pct": round(100 * len(sub) / total, 1) if total else None,
               "namen": len(tick),
               "haeufigste": [[t, n] for t, n in sorted(tick.items(), key=lambda x: (-x[1], x[0]))[:n_top]]}
        if det is not None:
            row["gruende"] = dict(sorted(det.items(), key=lambda x: (-x[1], x[0])))
        if k == KAT_RANG:
            rr = sorted(c["rang"] for c in sub if c.get("rang"))
            row["rang_median"] = statistics.median(rr) if rr else None
            row["rang_bereiche"] = {"31-50": sum(31 <= r <= 50 for r in rr),
                                    "51-100": sum(51 <= r <= 100 for r in rr),
                                    ">100": sum(r > 100 for r in rr)}
        out["kategorien"][str(k)] = row
    return out


def run_fehlanalyse(deadline, ua) -> int:
    """Fehl-Analyse über Namen (Vergleichsfenster). FINRA aus der gespeicherten
    Datei; SEC + Yahoo frisch (Kurse nur bis WIN_END)."""
    import requests
    from collections import Counter
    finra = {}
    if not (OUT_DIR / "finra_si.jsonl.gz").exists():
        log("ABBRUCH: erkundungsfeld/finra_si.jsonl.gz fehlt (erst Modus voll laufen lassen)")
        return 1
    with gzip.open(OUT_DIR / "finra_si.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            finra.setdefault(date.fromisoformat(r["stichtag"]), {})[r["ticker"]] = {
                "qty": r["qty"], "dtc": r["dtc"], "adv": r["adv"], "split": r["split"]}
    hdr = {"User-Agent": ua, "Accept-Encoding": "gzip"}
    try:
        r = requests.get(SEC_TICKERS, headers=hdr, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        tick = {v["ticker"].upper(): int(v["cik_str"]) for v in r.json().values()}
    except Exception as exc:  # noqa: BLE001 — ohne Zuordnung keine Analyse
        log(f"ABBRUCH: SEC-Tickerliste nicht abrufbar: {exc!r}")
        return 1
    sec, sec_fehlend = {}, []
    for y, q in sec_quarters(FINRA_FROM - timedelta(days=200), WIN_END - timedelta(days=SEC_LAG_DAYS)):
        try:
            rr = requests.get(SEC_FRAME.format(y=y, q=q), headers=hdr, timeout=60)
            time.sleep(0.15)
            if rr.status_code != 200:
                raise RuntimeError(f"HTTP {rr.status_code}")
            for row in rr.json().get("data", []):
                try:
                    sec.setdefault(int(row["cik"]), []).append(
                        (date.fromisoformat(row["end"]), float(row["val"])))
                except (KeyError, ValueError, TypeError):
                    continue
        except Exception as exc:  # noqa: BLE001
            sec_fehlend.append(f"CY{y}Q{q}I")
            log(f"SEC-Frame CY{y}Q{q}I fehlt: {exc!r}")
    prefilter_ok, win_t = set(), set()
    for sd, recs in finra.items():
        uf = usable_from(sd)
        for sym, rec in recs.items():
            cik = tick.get(sym)
            sh = sec_shares_known(sec, cik, uf) if cik else None
            if sh and rec["qty"] / sh * 100 >= PREFILTER_SEC_PCT:
                prefilter_ok.add((sd, sym))
                if WIN_START - timedelta(days=45) <= uf <= WIN_END:
                    win_t.add(sym)
    real = real_top10(ROOT / "matured_backtest_export.jsonl", WIN_START, WIN_END)
    tvals = tool_values(ROOT / "matured_backtest_export.jsonl", WIN_START, WIN_END)
    real_names = {s for v in real.values() for s in v}
    bars, miss_bars = fetch_bars((win_t | real_names | {"^GSPC"}), WIN_FETCH_START, WIN_END, WIN_END,
                                 deadline)
    float_map, miss_float = fetch_float_today(((set(bars) - {"^GSPC"}) | real_names), deadline)
    score_fn = _score_fn()
    spx = bars.get("^GSPC") or []
    cases, top10_ann, stored_agree = [], Counter(), [0, 0]
    stored = {}
    try:
        with gzip.open(OUT_DIR / "vergleich_namen.jsonl.gz", "rt", encoding="utf-8") as fh:
            for line in fh:
                x = json.loads(line)
                stored.setdefault(x["date"], []).append((x["rang"], x["ticker"]))
    except OSError:
        pass
    ann_features = {}
    for t in trading_days(WIN_START, WIN_END):
        if t not in real:
            continue
        sf = features_at(spx, t)
        if sf is None:
            continue
        cands, _ = score_candidates(t, win_t, bars, sf, finra, float_map, score_fn,
                                    prefilter_ok=prefilter_ok)
        ranks = {sym: i + 1 for i, (_, sym, _) in enumerate(cands)}
        top30 = [sym for _, sym, _ in cands[:TOP_N]]
        old = [tk for _, tk in sorted(stored.get(t.isoformat(), []))]
        stored_agree[0] += len(set(old) & set(top30))
        stored_agree[1] += len(old)
        for _, sym, m in cands[:10]:
            top10_ann[sym] += 1
            ann_features.setdefault(sym, []).append(m)
        for sym in real[t]:
            res = classify_miss(t, sym, finra, tick, sec, bars, float_map, sf, ranks,
                                candidates=win_t)
            if res is None:
                continue
            res.update({"date": t.isoformat(), "ticker": sym,
                        "tool": tvals.get((t, sym))})
            if res["kat"] in (KAT_SEC, KAT_VORFILTER):
                fl = float_map.get(sym, (None, None))[0]
                res["mit_float_nenner_bestanden"] = (
                    None if not fl else bool(res["si"] / fl * 100 >= PREFILTER_SEC_PCT))
            cases.append(res)
    # Abbruch (Rate-/Zeitlimit) → fehlende Kurse/Floats sind nicht zwingend echt:
    # Kategorie-4-Fälle werden dann als unsicher markiert (Guardian #739).
    if STOPS:
        for c in cases:
            if c["kat"] == KAT_YAHOO:
                c["unsicher"] = "abbruch:" + ",".join(sorted(set(STOPS)))
    summ = summarize_misses(cases)
    summ["kat4_unsicher_wegen_abbruch"] = sum(1 for c in cases if c.get("unsicher"))
    # Punkt 2: Kategorie (2)+(3) mit Nenner „Float heute“ (gekennzeichnet).
    s23 = [c for c in cases if c["kat"] in (KAT_SEC, KAT_VORFILTER)]
    summ["kat2_3_mit_float_heute"] = {
        "faelle": len(s23),
        "bestanden": sum(1 for c in s23 if c.get("mit_float_nenner_bestanden") is True),
        "nicht_bestanden": sum(1 for c in s23 if c.get("mit_float_nenner_bestanden") is False),
        "ohne_float": sum(1 for c in s23 if c.get("mit_float_nenner_bestanden") is None),
        "namen_bestanden": len({c["ticker"] for c in s23 if c.get("mit_float_nenner_bestanden")}),
        "kennz": "Nenner heutig"}
    # Kategorie (5): Werte des echten Tools (Listentag) für die gescheiterte Bedingung.
    f5 = [c for c in cases if c["kat"] == KAT_FILTER and c["detail"] == "short_float"]
    tool_sf = [c["tool"]["short_float"] for c in f5 if c.get("tool") and _num(c["tool"].get("short_float"))]
    summ["kat5_short_float_tool_vs_naeherung"] = {
        "faelle": len(f5),
        "tool_sf_median": round(statistics.median(tool_sf), 1) if tool_sf else None,
        "naeherung_sf_median": (round(statistics.median([c["werte"]["sf_naeherung"] for c in f5
                                                          if c["werte"]["sf_naeherung"] is not None]), 1)
                                if any(c["werte"]["sf_naeherung"] is not None for c in f5) else None),
        "tool_quellen": dict(Counter((c.get("tool") or {}).get("short_float_source") or "?" for c in f5))}
    # Herkunft der echten Fehlfälle im Tool (Screener-Pool / Watchlist).
    summ["herkunft_fehlfaelle"] = dict(sorted(Counter(
        p for c in cases for p in ((c.get("tool") or {}).get("source_pools") or ["(leer)"])).items(),
        key=lambda x: (-x[1], x[0])))
    # Punkt 3: Gegenrichtung — oft in den ersten 10 der Annäherung, nie in der echten Top-10.
    gegen = []
    for sym, n in sorted(top10_ann.items(), key=lambda x: (-x[1], x[0])):
        if sym in real_names:
            continue
        ms = ann_features.get(sym, [])
        def _med(key):
            vals = [m[key] for m in ms if _num(m.get(key)) is not None]
            return round(statistics.median(vals), 2) if vals else None
        gegen.append({"ticker": sym, "tage_in_top10": n, "sf_naeherung_median": _med("sf_naeherung"),
                      "mcap_naeherung_median": _med("mcap_naeherung"), "rvol20_median": _med("rvol20"),
                      "float_heute": ms[0].get("float_heute") if ms else None})
        if len(gegen) >= 15:
            break
    gegen_syms = [g["ticker"] for g in gegen]
    summ["gegenrichtung"] = gegen
    summ["gegenrichtung_boerse_heute"] = _exchange_today(gegen_syms)
    summ["laeufe"] = {"vergleichstage": len({c["date"] for c in cases}) if cases else 0,
                      "echte_namen": len(real_names), "ohne_kurs": len(miss_bars),
                      "ohne_float": len(miss_float), "sec_frames_fehlend": sec_fehlend,
                      "abbrueche": sorted(set(STOPS)), "vollstaendig": not STOPS,
                      "nachrechnung_top30_wie_gespeichert_pct": (
                          round(100 * stored_agree[0] / stored_agree[1], 1) if stored_agree[1] else None)}
    summ["rahmen"] = {"vergleich": [WIN_START.isoformat(), WIN_END.isoformat()],
                      "regel": "§7·0a (b): nur Namen/Ränge/Merkmale vom Listentag, keine Renditen"}
    (OUT_DIR / "fehlanalyse.json").write_text(
        json.dumps(summ, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    write_gz_jsonl(OUT_DIR / "fehlanalyse_faelle.jsonl.gz",
                   sorted(cases, key=lambda c: (c["date"], c["ticker"])))
    log("FEHLANALYSE " + json.dumps({k: v["faelle"] for k, v in summ["kategorien"].items()}))
    print(json.dumps({"kategorien": {k: [v["faelle"], v["anteil_pct"]] for k, v in summ["kategorien"].items()},
                      "laeufe": summ["laeufe"]}, ensure_ascii=False))
    return 0


def _exchange_today(symbols) -> dict:
    """Börsenplatz/Typ HEUTE (Yahoo .info, gekennzeichnet) — nur für die
    Gegenrichtung (≤ 15 Namen). Fail-soft."""
    out = {}
    try:
        import yfinance as yf
    except Exception:  # noqa: BLE001
        return out
    for s in symbols:
        try:
            info = yf.Ticker(s).info or {}
            out[s] = {"exchange": info.get("exchange"), "quoteType": info.get("quoteType"),
                      "kennz": "heutig"}
        except Exception:  # noqa: BLE001
            out[s] = None
        time.sleep(INFO_PAUSE_S)
    return out


# ── Ausgabe ─────────────────────────────────────────────────────────────────
def write_gz_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for r in rows:
            gz.write((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(buf.getvalue())
    os.replace(tmp, path)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--modus", choices=("probe", "voll", "fehlanalyse"), default="probe")
    ap.add_argument("--zeitlimit-min", type=float, default=130.0)
    args = ap.parse_args(argv)
    import requests
    deadline = time.monotonic() + args.zeitlimit_min * 60
    ua = os.environ.get("EDGAR_USER_AGENT") or "Squeeze Report erkundungsfeld contact@example.com"
    if args.modus == "fehlanalyse":
        return run_fehlanalyse(deadline, ua)
    bericht = {"modus": args.modus, "start_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "rahmen": {"feld": [FIELD_START.isoformat(), FIELD_END.isoformat()],
                          "vergleich": [WIN_START.isoformat(), WIN_END.isoformat()],
                          "schwelle": {"bestanden_ab": SCHWELLE_BESTANDEN, "grenzfall_ab": SCHWELLE_GRENZFALL}}}

    # 1. FINRA
    try:
        sdates = finra_settlement_dates(requests.post, FINRA_FROM, WIN_END)
        probe_rows = finra_settlement(sdates[0], requests.post, page=5, max_pages=1) if sdates else []
    except RateLimited:
        log("FINRA Rate-Limit — Abbruch ohne Retry")
        return 2
    except Exception as exc:  # noqa: BLE001 — ohne Stichtage kein Lauf
        log(f"ABBRUCH: FINRA-Stichtage nicht abrufbar: {exc!r}")
        return 1
    bericht["finra_stichtage"] = len(sdates)
    bericht["finra_felder_ok"] = finra_fields_ok(probe_rows)
    log(f"FINRA: {len(sdates)} Stichtage, Felder ok={bericht['finra_felder_ok']}; "
        f"Feldnamen Probe: {sorted(probe_rows[0]) if probe_rows else []}")
    if not bericht["finra_felder_ok"]:
        log("ABBRUCH: erwartete FINRA-Felder fehlen")
        print(json.dumps(bericht, ensure_ascii=False))
        return 1
    if args.modus == "probe":
        print(json.dumps(bericht, ensure_ascii=False))
        return 0
    finra, finra_fehlend = {}, []
    for i, sd in enumerate(sdates):
        try:
            finra[sd] = normalize_finra(finra_settlement(sd, requests.post))
        except RateLimited:
            log("FINRA Rate-Limit — kein Retry, Rest fehlt")
            finra_fehlend += [x.isoformat() for x in sdates[i:]]
            STOPS.append("rate_limit_finra")
            break
        except Exception as exc:  # noqa: BLE001 — Lücke statt Absturz
            log(f"FINRA {sd}: Fehler {exc!r} — Stichtag fehlt")
            finra_fehlend.append(sd.isoformat())
            continue
        log(f"FINRA {sd}: {len(finra[sd])} gelistete Stammaktien")
    bericht["finra_stichtage_fehlend"] = finra_fehlend
    if finra_fehlend:
        STOPS.append("finra_stichtage_fehlend")
    write_gz_jsonl(OUT_DIR / "finra_si.jsonl.gz",
                   ({"stichtag": sd.isoformat(), "ticker": s, **v}
                    for sd in sorted(finra) for s, v in sorted(finra[sd].items())))

    # 2. SEC-Vorfilter
    hdr = {"User-Agent": ua, "Accept-Encoding": "gzip"}
    try:
        r = requests.get(SEC_TICKERS, headers=hdr, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        # HEUTIGE Zuordnung Ticker → CIK (Survivorship/Kürzel-Wiederverwendung: Kennzeichen im Bericht)
        tick = {v["ticker"].upper(): int(v["cik_str"]) for v in r.json().values()}
    except Exception as exc:  # noqa: BLE001 — ohne Zuordnung kein Vorfilter möglich
        log(f"ABBRUCH: SEC-Tickerliste nicht abrufbar: {exc!r}")
        bericht["urteil"] = "unvollstaendig"
        print(json.dumps(bericht, ensure_ascii=False))
        return 1
    sec, sec_fehlend = {}, []
    # nur Quartale, deren Ende + 90 Tage im Messzeitraum liegen kann (spätere gibt es noch nicht)
    for y, q in sec_quarters(FINRA_FROM - timedelta(days=200), WIN_END - timedelta(days=SEC_LAG_DAYS)):
        try:
            r = requests.get(SEC_FRAME.format(y=y, q=q), headers=hdr, timeout=60)
            time.sleep(0.15)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            data = r.json().get("data", [])
        except Exception as exc:  # noqa: BLE001
            log(f"SEC-Frame CY{y}Q{q}I fehlt: {exc!r}")
            sec_fehlend.append(f"CY{y}Q{q}I")
            continue
        for row in data:
            try:
                sec.setdefault(int(row["cik"]), []).append((date.fromisoformat(row["end"]), float(row["val"])))
            except (KeyError, ValueError, TypeError):
                continue
    bericht["sec_frames_fehlend"] = sec_fehlend
    if sec_fehlend:
        STOPS.append("sec_frames_fehlend")
    # Vorfilter je Stichtag mit dem am Nutzbar-ab bekannten SEC-Stand (point-in-time
    # je Tag; rank_day prüft den an Tag t gültigen Stichtag gegen prefilter_ok).
    field_t, win_t, ohne_sec, prefilter_ok = set(), set(), set(), set()
    for sd, recs in finra.items():
        uf = usable_from(sd)
        for sym, rec in recs.items():
            cik = tick.get(sym)
            sh = sec_shares_known(sec, cik, uf) if cik else None
            if not sh:
                ohne_sec.add(sym)
                continue
            if rec["qty"] / sh * 100 < PREFILTER_SEC_PCT:
                continue
            prefilter_ok.add((sd, sym))
            # Stichtag kann für Tage des Zeitraums der jüngste nutzbare sein
            if FIELD_START - timedelta(days=45) <= uf <= FIELD_END:
                field_t.add(sym)
            if WIN_START - timedelta(days=45) <= uf <= WIN_END:
                win_t.add(sym)
    bericht["vorfilter"] = {"feld_ticker": len(field_t), "vergleich_ticker": len(win_t),
                            "ohne_sec_nenner": len(ohne_sec),
                            "kennz": "Ticker→CIK aus der HEUTIGEN SEC-Liste (Survivorship, Kürzel-Wiederverwendung)"}
    log(f"Vorfilter: Feld {len(field_t)}, Vergleich {len(win_t)}, ohne SEC-Nenner {len(ohne_sec)}")

    # 3. Kurse (Variante A, harte Obergrenzen)
    splits_f, splits_w = {}, {}
    bars_f, miss_f = fetch_bars(field_t | {"^GSPC"}, FIELD_FETCH_START, FIELD_END, FIELD_END, deadline,
                                splits_out=splits_f)
    bars_w, miss_w = fetch_bars(win_t | {"^GSPC"}, WIN_FETCH_START, WIN_END, WIN_END, deadline,
                                splits_out=splits_w)

    # 4. Heutiger Float nur für Ticker mit Kursen
    float_map, miss_float = fetch_float_today((set(bars_f) | set(bars_w)) - {"^GSPC"}, deadline)
    bericht["luecken"] = {"ohne_kurs_feld": len(miss_f), "ohne_kurs_vergleich": len(miss_w),
                          "ohne_float_heute": len(miss_float)}

    score_fn = _score_fn()

    def run_days(days, tickers, bars, splits, cap):
        spx = bars.get("^GSPC") or []
        lists, gap = {}, {}
        for t in days:
            sf = features_at(spx, t)
            if sf is None:
                continue
            lk = {}
            lst, ohne = rank_day(t, tickers, bars, sf, finra, float_map, score_fn,
                                 prefilter_ok=prefilter_ok, splits=splits, cap=cap, luecken=lk)
            lists[t] = lst
            g = gap.setdefault(t.strftime("%Y-%m"), [0, 0, 0])
            g[0] += len(ohne)
            g[1] += lk.get("ohne_float", 0)
            g[2] += 1
        return lists, gap

    field_lists, gap_f = run_days(trading_days(FIELD_START, FIELD_END), field_t, bars_f, splits_f, FIELD_END)
    win_lists, gap_w = run_days(trading_days(WIN_START, WIN_END), win_t, bars_w, splits_w, WIN_END)
    n_eintr = sum(len(v) for v in field_lists.values())
    bericht["split_kennzeichen_feld"] = {
        "eintraege": n_eintr,
        "split_nach_tag": sum(1 for v in field_lists.values() for *_, m in v if m["split_nach_tag"]),
        "split_seit_stichtag": sum(1 for v in field_lists.values() for *_, m in v if m["split_seit_stichtag"])}
    write_gz_jsonl(OUT_DIR / "kandidaten.jsonl.gz",
                   ({"date": t.isoformat(), "rang": r, "ticker": s, "score_ann": sc, "merkmale": m}
                    for t in sorted(field_lists) for r, s, sc, m in field_lists[t]))
    # Vergleichsfenster: nur Namen + Rang (§7·0a b)
    write_gz_jsonl(OUT_DIR / "vergleich_namen.jsonl.gz",
                   ({"date": t.isoformat(), "rang": r, "ticker": s}
                    for t in sorted(win_lists) for r, s, *_ in win_lists[t]))
    real = real_top10(ROOT / "matured_backtest_export.jsonl", WIN_START, WIN_END)
    cmp_ = compare(win_lists, real)
    bericht["vergleich"] = {k: cmp_[k] for k in ("tage", "top10", "top20", "top30")}
    bericht["abbrueche"] = sorted(set(STOPS))
    bericht["vollstaendig"] = not STOPS
    bericht["urteil"] = verdict(cmp_["top30"]["median"], vollstaendig=not STOPS)
    bericht["median_top30_trotz_luecken"] = cmp_["top30"]["median"]
    bericht["luecke_je_monat"] = {m: {"ohne_kurs_ticker_tage": v[0], "ohne_float_ticker_tage": v[1],
                                      "tage": v[2]}
                                  for m, v in sorted({**gap_f, **gap_w}.items())}
    bericht["feld_tage_mit_liste"] = len(field_lists)
    bericht["ende_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (OUT_DIR / "stufe1_bericht.json").write_text(
        json.dumps(bericht, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    write_gz_jsonl(OUT_DIR / "vergleich_je_tag.jsonl.gz", cmp_["je_tag"])
    log("URTEIL " + bericht["urteil"] + " — " + json.dumps(bericht["vergleich"]["top30"], ensure_ascii=False))
    print(json.dumps(bericht, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
