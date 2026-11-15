#!/usr/bin/env python3
"""SUW — „Leerverkäufer unter Wasser“ (von Beschwitz/Massa, „Biased Shorts“).

Setzt die Regel aus open_items.json, Item ``regel-suw-shorts-unter-wasser``
(festgeschrieben 15.11.2026, Commit 8cd6d065) WÖRTLICH um. Nichts dazu
erfunden; wo der Regeltext eine Umsetzungsfrage offenlässt, steht die
gewählte Lesart unten unter „Lesarten“ und im Ergebnis (``lesarten``).

MERKMAL je Einstieg (D = Einstiegsdatum, Tag 0):
  sv_t = ShortVolume des Tickers aus der FINRA-Tagesdatei CNMSshvol (nur diese).
  c_t  = Tagesschlusskurs (Yahoo, endgültige Tageszeile, split-bereinigt;
         yfinance auto_adjust=False, Spalte Close — OHNE Dividenden-Bereinigung).
  Fenster: die 20 Handelstage VOR D (D−20 … D−1), D selbst nicht.
  R   = Summe(sv_t × c_t) / Summe(sv_t)
  SUW = c_D / R − 1
  Fehlen mehr als 5 der 20 Tage (Datei oder Ticker): kein Wert. Unbekannt ≠ 0.

AUSWERTUNG: V = Schluss Tag 10 / Eröffnung Tag 1 − 1 (outcome_path.jsonl).
Je Einstiegstag Einträge mit Wert nach SUW ordnen; obere Hälfte = höchste SUW,
untere = niedrigste; ungerade Zahl → mittlerer Eintrag fällt weg; Tage mit < 4
Werten entfallen; Gleichstand: bessere pool_position, dann Ticker alphabetisch.
Hauptzahl 1 = je Tag Mittel V oben − unten, über die Tage gemittelt.
Hauptzahl 2 = dasselbe für den Anteil mit Hoch Tag 1–10 ≥ Eröffnung Tag 1 × 1,30.
Je Hauptzahl: 95-%-Bereich (Bootstrap 2000, Seed 42, nach Einstiegstag),
erste/zweite Hälfte der Einstiegstage, Wert ohne die 3 extremsten Einträge.

BETRIEBSARTEN (harte Datumsriegel, durch Tests belegt):
  nachrechnen  nur Einstiege ≤ 23.10.2026 (offenes Fenster). Vergleicht mit den
               im Chat gerechneten Soll-Werten (Toleranz unten, vor dem Lauf
               festgeschrieben).
  test         nur Einstiege ≥ 24.10.2026 (Blindfenster) und NUR wenn der
               Auslöser erfüllt ist (60 Einstiegstage mit endgültigem Schluss
               Tag 10). Vorher: nur Zählerstand, keine Kurse, keine FINRA-
               Dateien, keine Rendite. Die eigentliche Freeze-Auswertung (F1/F2,
               Holm) kommt mit dem Freeze-Block; bis dahin bricht „test“ auch
               bei erreichtem Auslöser ab, ohne Rendite zu laden.

Lesarten (Regeltext lässt sie offen; gewählt und offen gelegt):
  L1 Handelstage = US-Börsentage (Mo–Fr ohne config.US_MARKET_HOLIDAYS), nicht
     die Kursreihe des Tickers — sonst könnte ein fehlender Kurstag nie als
     „fehlend“ zählen.
  L2 Ein Fenstertag zählt als vorhanden, wenn die CNMS-Datei des Tages existiert,
     den Ticker (exakte Schreibweise) mit ShortVolume enthält UND Yahoo für den
     Tag einen endlichen Schluss > 0 hat. ShortVolume 0 zählt als vorhanden.
  L3 c_D fehlt bei Yahoo → kein Wert. Summe(sv) = 0 → kein Wert.
  L4 Kursverlauf vollständig = 11 Tageszeilen mit endlichem Open Tag 1 > 0,
     endlichem Schluss Tag 10 und endlichem Hoch Tag 1–10 (sonst „ohne
     vollständige Kurse“, zählt nicht als Eintrag mit Wert).
  L5 Zeithälften: Schnitt am (unteren) Median der verwendeten Einstiegstage;
     erste Hälfte = Tage ≤ Median-Datum.
  L6 „ohne die 3 extremsten Einträge“: die 3 Einträge mit dem größten |V| unter
     allen Einträgen der oberen und unteren Hälften werden entfernt (die
     Hälften-Zuordnung bleibt), danach neu gemittelt; ein Tag, an dem eine
     Hälfte leer wird, entfällt. Für Hauptzahl 2 dieselben 3 Einträge.
  L7 Kosten 1,9 % multiplikativ wie backtest_history.apply_round_trip_haircut.
  L8 „bessere pool_position“ = kleinere Zahl (Platz 1 vor Platz 2); fehlende
     pool_position sortiert ans Ende.
  L9 95-%-Bereich = sortierte Bootstrap-Werte, Index int(0,025·N) und
     int(0,975·N) − 1 (bei N = 2000: 50 und 1949), wie in den bisherigen
     Erkundungen.

Datenquellen-Robustheit: fehlen bei mehr als 5 % der Ticker die Yahoo-Kurse →
Ergebnis „nicht auswertbar“ (keine Schätzung). FINRA-/Yahoo-Fehler werden je
Datei bzw. Ticker gezählt und genannt; kein Retry bei Rate-Limit.

Schreibt NUR die Ergebnisdatei (Pfad per --out, gedacht als Artifact), nie in
eine Repo-Datei. Keine Secrets.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import pathlib
import random
import statistics as st
import sys
import time
from datetime import date, timedelta
from typing import Callable, Iterable, Sequence

_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config  # noqa: E402

# ── Konstanten (Regel) ──────────────────────────────────────────────────────
EXPORT_FILE = "matured_backtest_export.jsonl"
OUTCOME_FILE = "outcome_path.jsonl"
PROVENANCE = "forward"
NACH_TO = date(2026, 10, 23)      # Betriebsart nachrechnen: D ≤ 23.10.2026
TEST_FROM = date(2026, 10, 24)    # Betriebsart test: D ≥ 24.10.2026
TRIGGER_DAYS = 60                 # Auslöser test (Easy-Entscheid 15.11.2026)
WINDOW = 20
MAX_MISSING = 5
MIN_VALUES_PER_DAY = 4
TARGET = 1.30
N_BARS = 11
N_BOOT = 2000
SEED = 42
HAIRCUT_DESC = 1.9
N_EXTREME = 3
MAX_TICKER_FAIL_SHARE = 0.05
FINRA_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt"
FINRA_PAUSE_S = 0.25
YAHOO_PAUSE_S = 0.4

# Soll-Werte der Nachrechnung (im Chat gerechnet, open_item regel-suw-…) und
# Toleranz (Easy 15.11.2026, VOR dem Lauf festgeschrieben).
SOLL = {"n_value": 664, "days": 67, "hz1": 4.48, "hz2": 3.81,
        "hz1_h1": 4.20, "hz1_h2": 4.75, "upper_mean_v": 1.29, "lower_mean_v": -3.03}
TOL = {"hz1": 0.3, "hz2": 0.5, "n_value": 3}

MODES = ("nachrechnen", "test")


class SuwAbort(Exception):
    pass


# ── Datum / Kalender ────────────────────────────────────────────────────────
def parse_dmy(s) -> date | None:
    try:
        d, m, y = str(s).split(".")
        return date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def is_trading_day(d: date, holidays=None) -> bool:
    hol = config.US_MARKET_HOLIDAYS if holidays is None else holidays
    return d.weekday() < 5 and d.isoformat() not in hol


def window_days(d: date, n: int = WINDOW, holidays=None) -> list[date]:
    """Die n US-Börsentage VOR d (aufsteigend), d selbst nicht (L1)."""
    out: list[date] = []
    x = d - timedelta(days=1)
    while len(out) < n:
        if is_trading_day(x, holidays):
            out.append(x)
        x -= timedelta(days=1)
    return sorted(out)


def in_mode(d: date | None, mode: str) -> bool:
    """Harter Datumsriegel je Betriebsart."""
    if d is None:
        return False
    if mode == "nachrechnen":
        return d <= NACH_TO
    if mode == "test":
        return d >= TEST_FROM
    raise SuwAbort(f"unbekannte Betriebsart {mode!r}")


# ── Lesen (datumsgefiltert, nur benötigte Felder) ───────────────────────────
def _iter_jsonl(path) -> Iterable[dict]:
    try:
        fh = open(path, "r", encoding="utf-8")
    except OSError as exc:
        raise SuwAbort(f"Datei nicht lesbar: {path} ({exc!r})") from exc
    with fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
            if isinstance(obj, dict):
                yield obj


def load_population(export_path, mode: str) -> list[dict]:
    """Export-Zeilen provenance forward im Riegel der Betriebsart; nur
    ticker/date/pool_position werden übernommen; Dedupe (ticker, date)."""
    seen, out = set(), []
    for obj in _iter_jsonl(export_path):
        if obj.get("provenance") != PROVENANCE:
            continue
        d = parse_dmy(obj.get("date"))
        if not in_mode(d, mode):
            continue
        key = (obj.get("ticker"), obj.get("date"))
        if key in seen:
            continue
        seen.add(key)
        out.append({"ticker": obj.get("ticker"), "date": obj.get("date"), "d": d,
                    "pool_position": obj.get("pool_position")})
    return out


def count_trigger_days(outcome_path, mode: str = "test") -> int:
    """Zählt Einstiegstage im Riegel mit mindestens einer outcome_path-Zeile
    ohne ``grund`` (= endgültiger Schluss Tag 10 vorhanden). Liest NUR date und
    grund; Kurse werden nicht angefasst."""
    days = set()
    for obj in _iter_jsonl(outcome_path):
        d = parse_dmy(obj.get("date"))
        if not in_mode(d, mode):
            continue
        if obj.get("grund") is None:
            days.add(d)
    return len(days)


def load_outcomes(outcome_path, keys: set, mode: str) -> dict:
    """(ticker, date) → Zeile, nur für Schlüssel der Population im Riegel."""
    out = {}
    for obj in _iter_jsonl(outcome_path):
        d = parse_dmy(obj.get("date"))
        if not in_mode(d, mode):
            continue
        k = (obj.get("ticker"), obj.get("date"))
        if k in keys and k not in out:
            out[k] = obj
    return out


def outcome_entry(z: dict | None) -> tuple[str | None, dict | None]:
    """L4. (Grund, None) oder (None, {v, hit})."""
    if z is None:
        return "zeile_fehlt", None
    if z.get("grund") is not None:
        return f"grund:{z.get('grund')}", None
    bars = z.get("bars")
    if not isinstance(bars, list) or len(bars) != N_BARS or not all(isinstance(b, dict) for b in bars):
        return "bars_unvollstaendig", None
    o1 = bars[1].get("o")
    c10 = bars[10].get("c")
    highs = [b.get("h") for b in bars[1:]]
    if not (_finite(o1) and o1 > 0 and _finite(c10) and all(_finite(h) for h in highs)):
        return "bars_unvollstaendig", None
    v = (c10 / o1 - 1) * 100
    hit = max(highs) >= o1 * TARGET
    return None, {"v": v, "hit": hit}


# ── Rechenkern (rein) ───────────────────────────────────────────────────────
def suw_value(d: date, wdays: Sequence[date], sv: dict, close: dict) -> tuple[float | None, str, int]:
    """SUW eines Einstiegs. ``sv``: {date: ShortVolume} des Tickers (nur Tage,
    deren CNMS-Datei den Ticker enthält); ``close``: {date: Schluss}.
    Returnt (Wert|None, Grund, fehlende Tage)."""
    num = den = 0.0
    missing = 0
    for t in wdays:
        s = sv.get(t)
        c = close.get(t)
        if not (_finite(s) and s >= 0 and _finite(c) and c > 0):
            missing += 1
            continue
        num += s * c
        den += s
    if missing > MAX_MISSING:
        return None, "zu_viele_fehlende_tage", missing
    cd = close.get(d)
    if not (_finite(cd) and cd > 0):
        return None, "c_D_fehlt", missing
    if den <= 0:
        return None, "summe_sv_null", missing
    r = num / den
    return (cd / r - 1) * 100, "ok", missing


def day_halves(entries: Sequence[dict]) -> tuple[list[dict], list[dict]] | None:
    """entries: Einträge eines Tages mit 'suw', 'pool_position', 'ticker'.
    Sortierung: höchste SUW zuerst; Gleichstand → kleinere pool_position, dann
    Ticker alphabetisch. Returnt (obere, untere) oder None (< 4 Werte)."""
    if len(entries) < MIN_VALUES_PER_DAY:
        return None

    def pos(e):
        p = e.get("pool_position")
        return p if _finite(p) else float("inf")

    rs = sorted(entries, key=lambda e: (-e["suw"], pos(e), str(e["ticker"])))
    h = len(rs) // 2
    upper = rs[:h]
    lower = rs[len(rs) - h:]
    return upper, lower


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def day_diff(upper, lower, key: str) -> float | None:
    if not upper or not lower:
        return None
    f = (lambda e: (100.0 if e["hit"] else 0.0)) if key == "hit" else (lambda e: e["v"])
    return _mean(f(e) for e in upper) - _mean(f(e) for e in lower)


def headline(days: dict, use: Sequence[date], key: str) -> float | None:
    vals = [day_diff(days[x][0], days[x][1], key) for x in use]
    vals = [v for v in vals if v is not None]
    return _mean(vals)


def bootstrap(days: dict, key: str, n: int = N_BOOT, seed: int = SEED) -> tuple[float, float]:
    keys = sorted(days)
    diffs = {x: day_diff(days[x][0], days[x][1], key) for x in keys}
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        s = [diffs[rng.choice(keys)] for _ in keys]
        out.append(sum(s) / len(s))
    out.sort()
    return out[int(0.025 * n)], out[int(0.975 * n) - 1]


def split_halves(day_keys: Sequence[date]) -> tuple[date, list[date], list[date]]:
    ks = sorted(day_keys)
    med = ks[(len(ks) - 1) // 2]
    return med, [x for x in ks if x <= med], [x for x in ks if x > med]


def without_extremes(days: dict, n: int = N_EXTREME) -> tuple[dict, list[dict]]:
    allx = [e for x in sorted(days) for e in (days[x][0] + days[x][1])]
    ex = sorted(allx, key=lambda e: (-abs(e["v"]), str(e["ticker"]), str(e["date"])))[:n]
    exid = {id(e) for e in ex}
    out = {}
    for x, (u, l) in days.items():
        u2 = [e for e in u if id(e) not in exid]
        l2 = [e for e in l if id(e) not in exid]
        if u2 and l2:
            out[x] = (u2, l2)
    return out, ex


def _haircut_fn() -> Callable:
    """apply_round_trip_haircut per AST aus backtest_history.py (ohne yfinance-
    Import) — dieselbe Formel wie im Repo (L7)."""
    src = (_ROOT / "backtest_history.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "apply_round_trip_haircut"]
    if len(fn) != 1:
        raise SuwAbort("apply_round_trip_haircut nicht eindeutig gefunden.")
    mod = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
                           fn[0]], type_ignores=[])
    ast.fix_missing_locations(mod)
    ns = {"HAIRCUT_ROUND_TRIP_PCT": config.HAIRCUT_ROUND_TRIP_PCT}
    exec(compile(mod, "backtest_history.py:apply_round_trip_haircut", "exec"), ns)  # noqa: S102
    return ns["apply_round_trip_haircut"]


def describe(group: Sequence[dict], hc: Callable) -> dict:
    v = [e["v"] for e in group]
    if not v:
        return {"n": 0}
    return {"n": len(v), "mittel_v": _mean(v), "median_v": st.median(v),
            "mittel_v_nach_1_9": _mean(hc(x, HAIRCUT_DESC) for x in v),
            "treffer_pct": 100 * sum(e["hit"] for e in group) / len(group),
            "im_plus_pct": 100 * sum(x > 0 for x in v) / len(v),
            "median_suw": st.median(e["suw"] for e in group)}


def evaluate(entries: Sequence[dict], hc: Callable) -> dict:
    """Reiner Auswertungskern über Einträge mit 'suw','v','hit','d',… ."""
    by = {}
    for e in entries:
        by.setdefault(e["d"], []).append(e)
    days, dropped = {}, []
    for x in sorted(by):
        r = day_halves(by[x])
        if r is None:
            dropped.append(x)
        else:
            days[x] = r
    if not days:
        raise SuwAbort("keine auswertbaren Einstiegstage")
    med, d1, d2 = split_halves(list(days))
    days_ex, ex = without_extremes(days)
    res = {"tage": len(days), "tage_entfallen": len(dropped),
           "median_datum": med.isoformat(), "tage_h1": len(d1), "tage_h2": len(d2),
           "extreme": [{"ticker": e["ticker"], "date": e["date"], "v": round(e["v"], 2),
                        "haelfte": "obere" if any(e is u for x in days for u in days[x][0]) else "untere"}
                       for e in ex]}
    for key, name in (("v", "hz1"), ("hit", "hz2")):
        lo, hi = bootstrap(days, key)
        res[name] = {"wert": headline(days, sorted(days), key), "ki95": [lo, hi],
                     "h1": headline(days, d1, key), "h2": headline(days, d2, key),
                     "ohne_3_extreme": headline(days_ex, sorted(days_ex), key)}
    upper = [e for x in sorted(days) for e in days[x][0]]
    lower = [e for x in sorted(days) for e in days[x][1]]
    res["obere"] = describe(upper, hc)
    res["untere"] = describe(lower, hc)
    res["ausgelassen_mitte"] = sum(len(by[x]) - len(days[x][0]) - len(days[x][1]) for x in days)
    return res


def verdict(res: dict) -> str:
    h = res["hz1"]
    if h["h1"] is not None and h["h2"] is not None and h["h1"] > 0 and h["h2"] > 0:
        lo, hi = h["ki95"]
        return "trägt stark" if (lo > 0 or hi < 0) else "trägt"
    return "trägt nicht"


def compare_soll(res: dict, n_value: int) -> dict:
    checks = {
        "hz1": abs(res["hz1"]["wert"] - SOLL["hz1"]) <= TOL["hz1"],
        "hz2": abs(res["hz2"]["wert"] - SOLL["hz2"]) <= TOL["hz2"],
        "n_value": abs(n_value - SOLL["n_value"]) <= TOL["n_value"],
        "hz1_haelften_positiv": res["hz1"]["h1"] > 0 and res["hz1"]["h2"] > 0,
    }
    return {"soll": SOLL, "toleranz": TOL, "checks": checks, "bestanden": all(checks.values())}


# ── Netz (injizierbar) ──────────────────────────────────────────────────────
def parse_finra(text: str, symbols: set) -> dict:
    """CNMS-Datei → {Symbol: ShortVolume} für gesuchte Symbole (exakt)."""
    out = {}
    lines = text.splitlines()
    if not lines:
        return out
    head = [h.strip() for h in lines[0].split("|")]
    try:
        i_sym, i_sv = head.index("Symbol"), head.index("ShortVolume")
    except ValueError:
        return out
    for ln in lines[1:]:
        p = ln.split("|")
        if len(p) <= max(i_sym, i_sv):
            continue
        sym = p[i_sym].strip()
        if sym in symbols:
            try:
                out[sym] = float(p[i_sv])
            except ValueError:
                continue
    return out


def fetch_finra_default(d: date) -> tuple[str | None, str]:
    import requests
    try:
        r = requests.get(FINRA_URL.format(d=d.strftime("%Y%m%d")), timeout=30,
                         headers={"User-Agent": "squeeze-report-suw-eval"})
    except Exception as exc:  # noqa: BLE001
        return None, f"fehler:{type(exc).__name__}"
    if r.status_code != 200:
        return None, f"http_{r.status_code}"
    return r.text, "ok"


def fetch_yahoo_default(ticker: str, start: date, end_excl: date) -> tuple[dict | None, str]:
    import yfinance as yf
    try:
        h = yf.Ticker(ticker).history(start=start.isoformat(), end=end_excl.isoformat(),
                                      interval="1d", auto_adjust=False)
    except Exception as exc:  # noqa: BLE001 — Rate-Limit u. a.: kein Retry
        return None, f"fehler:{type(exc).__name__}"
    if h is None or h.empty or "Close" not in h:
        return None, "leer"
    out = {}
    for idx, c in h["Close"].items():
        c = float(c)
        if math.isfinite(c) and c > 0:
            out[idx.date()] = c
    return (out or None), ("ok" if out else "leer")


# ── Ablauf ──────────────────────────────────────────────────────────────────
def run(mode: str, *, export_path, outcome_path, fetch_finra=fetch_finra_default,
        fetch_yahoo=fetch_yahoo_default, sleep=time.sleep, holidays=None) -> dict:
    if mode not in MODES:
        raise SuwAbort(f"unbekannte Betriebsart {mode!r}")
    res: dict = {"betriebsart": mode, "lesarten": "L1–L9 siehe Kopf von scripts/suw_eval.py"}
    if mode == "test":
        n_trig = count_trigger_days(outcome_path, "test")
        res["ausloeser"] = {"tage_mit_schluss_tag10": n_trig, "noetig": TRIGGER_DAYS,
                            "erreicht": n_trig >= TRIGGER_DAYS}
        if n_trig < TRIGGER_DAYS:
            res["status"] = "nur_zaehler"
            return res
        res["status"] = "ausloeser_erreicht_auswertung_nicht_implementiert"
        return res

    pop = load_population(export_path, mode)
    keys = {(p["ticker"], p["date"]) for p in pop}
    outs = load_outcomes(outcome_path, keys, mode)
    excl = {}
    ents = []
    for p in pop:
        why, e = outcome_entry(outs.get((p["ticker"], p["date"])))
        if why:
            excl[why] = excl.get(why, 0) + 1
            continue
        ents.append({**p, **e})
    res["einstiege"] = len(pop)
    res["ohne_vollstaendige_kurse"] = excl

    tickers = sorted({p["ticker"] for p in pop})
    wdays = {(e["ticker"], e["date"]): window_days(e["d"], holidays=holidays) for e in ents}
    need_dates = sorted({t for w in wdays.values() for t in w})
    max_d = max(p["d"] for p in pop)
    min_d = min(need_dates) if need_dates else max_d
    if not all(in_mode(t, mode) for t in need_dates) or max_d > NACH_TO:
        raise SuwAbort("Datumsriegel verletzt")

    sv_by_t: dict = {}
    finra_status = {}
    sym = set(tickers)
    for i, d in enumerate(need_dates):
        if i:
            sleep(FINRA_PAUSE_S)
        text, why = fetch_finra(d)
        finra_status[d.isoformat()] = why
        if text is None:
            continue
        for s, v in parse_finra(text, sym).items():
            sv_by_t.setdefault(s, {})[d] = v
    res["finra_dateien"] = {"benoetigt": len(need_dates),
                            "fehlend": sorted(k for k, v in finra_status.items() if v != "ok")}
    res["finra_ticker_nie_gefunden"] = sorted(t for t in tickers if t not in sv_by_t)

    close_by_t: dict = {}
    yahoo_fail = {}
    for i, t in enumerate(tickers):
        if i:
            sleep(YAHOO_PAUSE_S)
        c, why = fetch_yahoo(t, min_d - timedelta(days=5), max_d + timedelta(days=1))
        if c is None:
            yahoo_fail[t] = why
            continue
        close_by_t[t] = {k: v for k, v in c.items() if k <= max_d}
    res["yahoo_ohne_kurse"] = yahoo_fail
    share = len(yahoo_fail) / len(tickers) if tickers else 1.0
    if share > MAX_TICKER_FAIL_SHARE:
        res["status"] = "nicht_auswertbar"
        res["grund"] = f"Yahoo ohne Kurse bei {len(yahoo_fail)}/{len(tickers)} Tickern (> 5 %)"
        return res

    no_value = {}
    with_val = []
    for e in ents:
        k = (e["ticker"], e["date"])
        v, why, _miss = suw_value(e["d"], wdays[k], sv_by_t.get(e["ticker"], {}),
                                  close_by_t.get(e["ticker"], {}))
        if v is None:
            no_value[why] = no_value.get(why, 0) + 1
            continue
        with_val.append({**e, "suw": v})
    res["ohne_wert"] = no_value
    res["mit_wert"] = len(with_val)
    res["ticker"] = len(tickers)

    hc = _haircut_fn()
    r1 = evaluate(with_val, hc)
    r2 = evaluate(sorted(with_val, key=lambda e: (e["date"], e["ticker"])), hc)
    res["deterministisch"] = (r1["hz1"] == r2["hz1"] and r1["hz2"] == r2["hz2"])
    res.update(r1)
    res["urteil_nach_regel"] = verdict(r1)
    res["abgleich_soll"] = compare_soll(r1, len(with_val))
    res["status"] = "ok"
    return res


def _fmt(x, nd=2):
    return "—" if x is None else f"{x:+.{nd}f}"


def log_table(res: dict) -> str:
    L = [f"SUW-Auswertung — Betriebsart {res['betriebsart']} — Status {res.get('status')}"]
    if res["betriebsart"] == "test":
        a = res["ausloeser"]
        L.append(f"Auslöser: {a['tage_mit_schluss_tag10']}/{a['noetig']} Einstiegstage — keine Rendite geladen")
        return "\n".join(L)
    L.append(f"Einstiege {res.get('einstiege')} | ohne vollständige Kurse {res.get('ohne_vollstaendige_kurse')}"
             f" | ohne Wert {res.get('ohne_wert')} | mit Wert {res.get('mit_wert')} | Ticker {res.get('ticker')}")
    L.append(f"FINRA-Dateien {res['finra_dateien']} | FINRA nie gefunden {res.get('finra_ticker_nie_gefunden')}"
             f" | Yahoo ohne Kurse {res.get('yahoo_ohne_kurse')}")
    if res.get("status") != "ok":
        L.append(f"NICHT AUSWERTBAR: {res.get('grund')}")
        return "\n".join(L)
    L.append(f"Tage {res['tage']} (entfallen {res['tage_entfallen']}), Median-Datum {res['median_datum']}"
             f" ({res['tage_h1']}/{res['tage_h2']}), ausgelassen Mitte {res['ausgelassen_mitte']}")
    for k, name in (("hz1", "Hauptzahl 1 (V oben−unten)"), ("hz2", "Hauptzahl 2 (Treffer oben−unten)")):
        h = res[k]
        L.append(f"| {name} | {_fmt(h['wert'])} | KI95 {_fmt(h['ki95'][0])} … {_fmt(h['ki95'][1])}"
                 f" | H1 {_fmt(h['h1'])} / H2 {_fmt(h['h2'])} | ohne 3 {_fmt(h['ohne_3_extreme'])} |")
    L.append(f"Extreme: {res['extreme']}")
    for g in ("obere", "untere"):
        x = res[g]
        L.append(f"{g}: n {x['n']} Mittel {_fmt(x['mittel_v'])} Median {_fmt(x['median_v'])}"
                 f" nach 1,9 % {_fmt(x['mittel_v_nach_1_9'])} Treffer {x['treffer_pct']:.1f}%"
                 f" im Plus {x['im_plus_pct']:.1f}% Median SUW {_fmt(x['median_suw'], 1)}")
    L.append(f"Urteil nach Regel: {res['urteil_nach_regel']} | deterministisch: {res['deterministisch']}")
    a = res["abgleich_soll"]
    L.append(f"Abgleich Soll (Toleranz HZ1 ±0,3, HZ2 ±0,5, n ±3, Hälften HZ1 > 0): "
             f"{'BESTANDEN' if a['bestanden'] else 'NICHT BESTANDEN'} {a['checks']}")
    return "\n".join(L)


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, date):
        return o.isoformat()
    if isinstance(o, float):
        return round(o, 4)
    return o


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=MODES)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        res = run(a.mode, export_path=_ROOT / EXPORT_FILE, outcome_path=_ROOT / OUTCOME_FILE)
    except SuwAbort as exc:
        print(f"ABBRUCH: {exc}")
        return 2
    pathlib.Path(a.out).write_text(json.dumps(_jsonable(res), ensure_ascii=False, indent=2), encoding="utf-8")
    print(log_table(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
