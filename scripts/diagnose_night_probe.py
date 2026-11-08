#!/usr/bin/env python3
"""WEGWERF-DIAGNOSE: Nacht-Probe (open_item ``berichtsdatum-wurzelloesung-nacht-probe``).

Read-only. Schreibt NICHTS ins Repo — nur stdout (Job-Log) und eine JSON-Datei
unter ``$RUNNER_TEMP`` (wird als Artifact hochgeladen). Kein Produktionscode,
keine Daten-Datei wird verändert. Wird nach der Auswertung per Cleanup-PR
rückstandsfrei gelöscht (zusammen mit ``.github/workflows/diagnose_night_probe.yml``
und ``scripts/mock_test_diagnose_night_probe.py``).

Fragen:
  1  Liefert yfinance nachts (00:00–09:30 ET) die Tageszeile des letzten
     Handelstags D FINAL (OHLCV vollständig + identisch mit derselben Zeile,
     nach 09:30 ET erneut geladen; Toleranz 0,02 pp)? Und auf welchen Tag
     beziehen sich ``.info``-Werte nachts?
  2  Options-OI nachts vs. nach 09:30 ET vs. Produktions-Postclose von D.
  3  Nachts geladene Zeile D vs. das, was der Produktions-Postclose für D
     gespeichert hat (backtest_history: entry_price, rvol,
     entry_past_return_5d; Halbzeilen-Hinweise aus ``[halfrow_probe]``).

Modi:
  --mode auto      (Workflow) --kind night: wartet bis zu den Nacht-Zielzeiten
                   (ET) und misst je einmal; --kind day: misst einmal
                   (Tag-Referenz).
  --mode once      genau eine Messung jetzt.
  --evaluate F...  wertet Messdateien/Job-Logs aus (Verdikte + Tabellen).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

ET = ZoneInfo("America/New_York")
TOL_PP = 0.02                       # wie S16 (config.TRUTH_CHECK_TOLERANCE_PP)
BENCH = "SPY"
# Bewusst illiquide Titel aus dem Universum (fest, deterministisch). Auswahl
# offline am 08.11.2026: Ticker aus backtest_history (Einträge ab 08.10.2026),
# geschätzter Tages-Dollarumsatz = shares_short (si_position_history, letzter
# Stand) / dtc × entry_price; die drei kleinsten mit dtc ≥ 1:
# SDHC ≈ 0,45 Mio $, CURV ≈ 0,48 Mio $, TTEC ≈ 0,74 Mio $.
ILLIQUID = ("SDHC", "CURV", "TTEC")
NIGHT_TARGETS_ET = ("00:10", "01:30", "02:50")   # Nacht-Messpunkte (ET)
DAY_OPEN_ET = (9, 30)
PROBE_END_ET = date(2026, 11, 21)   # danach no-op (Sicherheitsnetz bis Cleanup)
PRICE_FIELDS = ("o", "h", "l", "c")
INFO_KEYS = ("regularMarketPrice", "regularMarketPreviousClose", "previousClose",
             "regularMarketTime", "regularMarketOpen", "regularMarketDayHigh",
             "regularMarketDayLow", "regularMarketVolume", "marketState")
MAX_STRIKES = 80                    # je Seite, nächster Verfall

VERDICT_RULES = """\
VERDIKT-REGELN (fest, alle Messschritte zählen):
Paar = (Nacht-Messung N, Tag-Referenz T) mit gleichem D; T = späteste Messung mit
Phase 'tag' und gleichem D. Nur Messungen mit Phase 'nacht' (00:00 ≤ ET < 09:30)
zählen als Nacht; jede Messung ab 09:30 ET (auch abends) ist 'tag'.
F1-Zeile (Batch-Download = Produktionspfad UND Einzelabruf; Paar-Klasse =
  schlechteste der beiden Wege): je Ticker
  unbestimmt  = Abruf-Fehler/keine Daten in N oder T (auch Rate-Limit)
  nicht_final = Zeile D fehlt in N, oder ein OHLCV-Feld in N leer (Halbzeile),
                oder |N/T−1|·100 > 0,02 bei O/H/L/C oder Volumen
  final       = sonst
  JA = ≥ 2 verschiedene D mit Paaren, kein nicht_final, unbestimmt ≤ 20 %
  NEIN = mindestens ein nicht_final
  UNBESTIMMT = sonst
F1-.info: je Ticker in N: Bezugstag = ET-Datum von regularMarketTime;
  passt = Bezugstag == D und |regularMarketPrice/Close_T(D)−1|·100 ≤ 0,02
  JA = ≥ 2 D, alle auswertbaren passen, unbestimmt ≤ 20 %; NEIN = einer passt
  nicht; UNBESTIMMT = sonst
F2-OI (nächster gemeinsamer Verfall, gemeinsame Strikes, exakte Gleichheit):
  je Ticker: nacht==tag? und nacht==prod(D, options_chain_raw)?
  JA (nachts schon Tagesstand) = ≥ 2 D, ≥ 5 Ticker-Paare, alle nacht==tag
  NEIN = mindestens ein nacht!=tag; UNBESTIMMT = sonst
  Zeitpunkt der Änderung: 'über Nacht' = nacht!=prod; 'vor Handelsbeginn' =
  nacht==prod und tag!=nacht
F3 (Top-10 von D): entry_price vs Close_N(D) (0,02 pp), rvol vs Volumen_N(D)/
  Mittel der letzten 20 Volumen bis D (gespeichert auf 3 Stellen: |Δ| ≤ 0,0011), entry_past_return_5d vs
  (Close_N(D)/Close_N(D−5)−1)·100 (0,02 pp absolut)
  gleich = entry_price + alle übrigen vergleichbaren Felder passen; anders =
  Nacht-Zeile selbst unvollständig oder Abweichung; vollstaendiger = Abweichung und
  Produktion hatte für D eine Halbzeile ([halfrow_probe]); anders = sonst
  JA (Nacht = Produktion) = ≥ 2 D, alle gleich; NEIN = ein anders/vollstaendiger;
  UNBESTIMMT = sonst
"""


# ── Zeit / Kalender ──────────────────────────────────────────────────────────
def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in config.US_MARKET_HOLIDAYS


def last_trading_day_before(d: date) -> date:
    x = d - timedelta(days=1)
    for _ in range(15):
        if is_trading_day(x):
            return x
        x -= timedelta(days=1)
    return x


def phase_of(now_et: datetime) -> str:
    """'nacht' = 00:00 ≤ ET < 09:30 (zählt als Nachtmessung); sonst 'tag'
    (Referenz — ab 09:30 ET ist Zeile D in jedem Fall endgültig). Ein Lauf vor
    Mitternacht ET ist damit nie eine Nachtmessung."""
    return "nacht" if (now_et.hour, now_et.minute) < DAY_OPEN_ET else "tag"


def d_for(now_et: datetime) -> date:
    """D = letzter US-Handelstag strikt vor dem ET-Kalendertag der Messung."""
    return last_trading_day_before(now_et.date())


# ── Repo-Referenzen (nur lesend) ─────────────────────────────────────────────
def _dmy(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def load_backtest(root=ROOT) -> list:
    try:
        with open(root / config.BACKTEST_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def ticker_set(bh: list, D: date) -> tuple[list, str]:
    """Top-10 des Postclose-Berichts von D (sortiert) + SPY + ILLIQUID.
    Fehlt D (z. B. Postclose ausgefallen), wird der jüngste Tag < D genommen."""
    rows = [e for e in bh if isinstance(e, dict) and e.get("source") != "bootstrap"]
    dates = set()
    for e in rows:
        try:
            dates.add(datetime.strptime(str(e.get("date")), "%d.%m.%Y").date())
        except ValueError:
            continue
    src = D if D in dates else max((x for x in dates if x < D), default=None)
    top = sorted({e["ticker"] for e in rows if src and e.get("date") == _dmy(src)})
    extra = [t for t in (BENCH, *ILLIQUID) if t not in top]
    return top + extra, (src.isoformat() if src else "keine")


def prod_refs(bh: list, chain_path, D: date, tickers: list) -> dict:
    out = {}
    for e in bh:
        if isinstance(e, dict) and e.get("date") == _dmy(D) and e.get("ticker") in tickers \
                and e.get("source") != "bootstrap":
            out[e["ticker"]] = {"entry_price": e.get("entry_price"), "rvol": e.get("rvol"),
                                "entry_past_return_5d": e.get("entry_past_return_5d")}
    try:
        with open(chain_path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("date") != D.isoformat() or r.get("ticker") not in tickers:
                    continue
                exps = r.get("expiries") or []
                if not exps:
                    continue
                ex = exps[0]
                out.setdefault(r["ticker"], {})["chain"] = {
                    "expiry": ex.get("expiry"),
                    "fetch_ts_utc": r.get("fetch_ts_utc"),
                    "calls": {str(c.get("strike")): c.get("openInterest") for c in ex.get("calls") or []},
                    "puts": {str(c.get("strike")): c.get("openInterest") for c in ex.get("puts") or []},
                }
    except OSError:
        pass
    return out


# ── Zahlen ───────────────────────────────────────────────────────────────────
def num(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def rel_pp(a, b):
    a, b = num(a), num(b)
    if a is None or b is None or b == 0:
        return None
    return abs(a / b - 1.0) * 100.0


# ── Yahoo-Abrufe (nur im Workflow; Tests injizieren Fakes) ───────────────────
def classify_error(exc: BaseException) -> str:
    name = type(exc).__name__
    if "RateLimit" in name:
        return "rate_limit"
    msg = str(exc)
    if name in ("YFTzMissingError",) or "No data found" in msg or "not found" in msg.lower():
        return "leer"
    return "fehler"


def _df_rows(df) -> list:
    rows = []
    if df is None or getattr(df, "empty", True):
        return rows
    for ts, r in df.iterrows():
        rows.append({"d": ts.date().isoformat(),
                     "o": num(r.get("Open")), "h": num(r.get("High")), "l": num(r.get("Low")),
                     "c": num(r.get("Close")), "v": num(r.get("Volume"))})
    return rows


def real_fetchers():
    import yfinance as yf

    def batch(tickers):
        # identisch zu generate_report._hist_stats Phase A
        df = yf.download(tickers, period="1y", group_by="ticker", auto_adjust=True,
                         threads=True, progress=False)
        errs = {}
        try:
            errs = {k: str(v)[:120] for k, v in dict(getattr(yf.shared, "_ERRORS", {}) or {}).items()}
        except Exception:  # noqa: BLE001
            errs = {}
        out = {}
        for t in tickers:
            try:
                sub = df if len(tickers) == 1 else df[t]
                out[t] = _df_rows(sub)
            except Exception:  # noqa: BLE001
                out[t] = []
        return out, errs

    def single(t):
        try:
            yf.config.debug.hide_exceptions = False
        except Exception:  # noqa: BLE001
            pass
        return _df_rows(yf.Ticker(t).history(period="3mo", interval="1d", auto_adjust=True,
                                             actions=False))

    def info(t):
        inf = yf.Ticker(t).info or {}
        return {k: inf.get(k) for k in INFO_KEYS}

    def chain(t, prefer_expiry, X):
        tk = yf.Ticker(t)
        exps = list(tk.options or [])
        if not exps:
            return None
        exp = prefer_expiry if prefer_expiry in exps else next(
            (e for e in exps if e >= X.isoformat()), exps[0])
        oc = tk.option_chain(exp)

        def side(df):
            d = {}
            for _, r in df.iterrows():
                d[str(float(r["strike"]))] = int(r["openInterest"]) if num(r.get("openInterest")) is not None else None
            return dict(list(d.items())[:MAX_STRIKES])
        return {"expiry": exp, "calls": side(oc.calls), "puts": side(oc.puts)}

    return {"batch": batch, "single": single, "info": info, "chain": chain}


# ── Messung ──────────────────────────────────────────────────────────────────
def measure(now_utc: datetime, fetchers, root=ROOT, sleep=time.sleep) -> dict:
    now_et = now_utc.astimezone(ET)
    D = d_for(now_et)
    bh = load_backtest(root)
    tickers, top_src = ticker_set(bh, D)
    refs = prod_refs(bh, root / config.OPTIONS_CHAIN_RAW_FILE, D, tickers)
    meta = {"run_utc": now_utc.isoformat(timespec="seconds"),
            "run_et": now_et.isoformat(timespec="seconds"), "phase": phase_of(now_et),
            "D": D.isoformat(), "top10_quelle": top_src, "tickers": tickers,
            "tol_pp": TOL_PP, "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT")}
    recs = {t: {"ticker": t, "prod": refs.get(t, {})} for t in tickers}
    stop = False
    try:
        bmap, berr = fetchers["batch"](tickers)
        for t in tickers:
            recs[t]["batch"] = bmap.get(t) or []
            recs[t]["batch_err"] = berr.get(t)
    except Exception as exc:  # noqa: BLE001
        cls = classify_error(exc)
        stop = cls == "rate_limit"
        for t in tickers:
            recs[t]["batch"], recs[t]["batch_err"] = [], f"{cls}:{type(exc).__name__}"
    for t in tickers:
        r = recs[t]
        for key, fn, args in (("single", fetchers["single"], (t,)),
                              ("info", fetchers["info"], (t,)),
                              ("chain", fetchers["chain"],
                               (t, (r["prod"].get("chain") or {}).get("expiry"), now_et.date()))):
            if stop:
                r[key], r[key + "_err"] = None, "rate_limit"
                continue
            try:
                r[key], r[key + "_err"] = fn(*args), None
            except Exception as exc:  # noqa: BLE001 — Fehler getrennt protokollieren
                cls = classify_error(exc)
                r[key], r[key + "_err"] = None, f"{cls}:{type(exc).__name__}:{str(exc)[:100]}"
                if cls == "rate_limit":
                    stop = True     # KEIN Retry; Rest = unbestimmt
            sleep(0.3)
        # Batch-Reihe auf die letzten 25 Zeilen kürzen (Log-Größe)
        r["batch"] = r["batch"][-25:]
        if isinstance(r.get("single"), list):
            r["single"] = r["single"][-25:]
    meta["rate_limit_abbruch"] = stop
    return {"meta": meta, "records": [recs[t] for t in tickers]}


def emit(m: dict, out_dir: pathlib.Path | None):
    print("[night_probe_meta] " + json.dumps(m["meta"], ensure_ascii=False), flush=True)
    for r in m["records"]:
        print("[night_probe] " + json.dumps({"run_utc": m["meta"]["run_utc"], **r},
                                            ensure_ascii=False, separators=(",", ":")), flush=True)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        fn = out_dir / f"night_probe_{m['meta']['run_utc'].replace(':', '')}.json"
        fn.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


def plan_targets(now_et: datetime, kind: str = "night") -> list[datetime]:
    """Messzeitpunkte. kind 'day' → sofort eine Messung. kind 'night': Start vor
    09:30 ET → die heute noch ausstehenden Nacht-Ziele (keins mehr → sofort);
    Start ab 16:00 ET (abends) → die Ziele des Folgetags; Start 09:30–16:00 ET
    (Verspätung > 7 h) → sofort eine Messung (zählt dann als Tag-Referenz)."""
    if kind == "day":
        return [now_et]
    hm = (now_et.hour, now_et.minute)
    if hm < DAY_OPEN_ET:
        day = now_et.date()
    elif hm >= (16, 0):
        day = now_et.date() + timedelta(days=1)
    else:
        return [now_et]
    out = []
    for hhmm in NIGHT_TARGETS_ET:
        h, m = map(int, hhmm.split(":"))
        t = datetime(day.year, day.month, day.day, h, m, tzinfo=ET)
        if t > now_et:
            out.append(t)
    return out or [now_et]


def run_auto(fetchers, out_dir, kind="night", now_fn=lambda: datetime.now(timezone.utc),
             sleep=time.sleep):
    start = now_fn()
    start_et = start.astimezone(ET)
    print(VERDICT_RULES, flush=True)
    if start_et.date() > PROBE_END_ET:
        print(f"[night_probe] Probe abgelaufen ({PROBE_END_ET}) — no-op", flush=True)
        return 0
    for tgt in plan_targets(start_et, kind):
        wait = (tgt.astimezone(timezone.utc) - now_fn()).total_seconds()
        if wait > 0:
            print(f"[night_probe] warte bis {tgt.isoformat()} ({int(wait)} s)", flush=True)
            sleep(wait)
        emit(measure(now_fn(), fetchers), out_dir)
    return 0


# ── Auswertung ───────────────────────────────────────────────────────────────
def load_measurements(paths) -> list[dict]:
    """Liest Artifact-JSONs ODER Job-Logs (Zeilen mit [night_probe_meta]/[night_probe])."""
    ms: dict = {}
    for p in paths:
        text = pathlib.Path(p).read_text(encoding="utf-8", errors="replace")
        if text.lstrip().startswith("{"):
            try:
                m = json.loads(text)
                ms[m["meta"]["run_utc"]] = m
                continue
            except (ValueError, KeyError):
                pass
        for line in text.splitlines():
            for tag in ("[night_probe_meta] ", "[night_probe] "):
                i = line.find(tag)
                if i < 0:
                    continue
                try:
                    obj = json.loads(line[i + len(tag):])
                except ValueError:
                    break
                if tag.startswith("[night_probe_meta"):
                    ms.setdefault(obj["run_utc"], {"meta": obj, "records": []})["meta"] = obj
                else:
                    ms.setdefault(obj["run_utc"], {"meta": None, "records": []})["records"].append(obj)
                break
    return [m for _, m in sorted(ms.items()) if m.get("meta")]


def _row(rows, D):
    for r in rows or []:
        if r.get("d") == D:
            return r
    return None


def _fetch_ok(rec) -> bool:
    return bool(rec.get("batch")) and not str(rec.get("batch_err") or "").startswith("rate_limit")


def _rvol_at(rows, D):
    idx = next((i for i, r in enumerate(rows or []) if r.get("d") == D), None)
    if idx is None:
        return None
    vols = [num(r.get("v")) for r in rows[max(0, idx - 19):idx + 1]]
    if any(v is None for v in vols) or not vols:
        return None
    avg = sum(vols) / len(vols)
    return vols[-1] / avg if avg > 0 else None


def _epr_at(rows, D):
    idx = next((i for i, r in enumerate(rows or []) if r.get("d") == D), None)
    if idx is None or idx < 5:
        return None
    a, b = num(rows[idx]["c"]), num(rows[idx - 5]["c"])
    return round((a / b - 1) * 100, 2) if a and b else None


def evaluate(ms: list[dict], halfrow: dict | None = None) -> dict:
    """Pure. ``halfrow``: {D_iso: set(tickers)} aus den [halfrow_probe]-Zeilen."""
    halfrow = halfrow or {}
    nights = [m for m in ms if m["meta"]["phase"] == "nacht"]
    days = {}
    for m in ms:
        if m["meta"]["phase"] == "tag":
            days[m["meta"]["D"]] = m          # späteste gewinnt (sortiert)
    f1, f1i, f2, f3 = [], [], [], []
    for n in nights:
        D = n["meta"]["D"]
        t = days.get(D)
        trec = {r["ticker"]: r for r in (t["records"] if t else [])}
        for r in n["records"]:
            tk = r["ticker"]
            base = {"D": D, "run_utc": n["meta"]["run_utc"], "run_et": n["meta"]["run_et"], "ticker": tk}
            tr = trec.get(tk)
            # F1 Zeile — BEIDE Abrufwege zählen (Batch = Produktionspfad, Einzel-
            # abruf = Zweitbeleg); Paar-Klasse = schlechteste der beiden.
            def _cls(nrows, trows, ok_n, ok_t):
                if not t or not tr:
                    return "unbestimmt", "kein Tag-Paar"
                if not ok_n or not ok_t:
                    return "unbestimmt", "Abruf-Fehler/keine Daten"
                nr, trow = _row(nrows, D), _row(trows, D)
                if trow is None:
                    return "unbestimmt", "Zeile D fehlt in Tag-Referenz"
                if nr is None:
                    return "nicht_final", "Zeile D fehlt nachts"
                if any(nr.get(k) is None for k in (*PRICE_FIELDS, "v")):
                    return "nicht_final", "Halbzeile nachts"
                diffs = {k: rel_pp(nr[k], trow[k]) for k in (*PRICE_FIELDS, "v")}
                bad = {k: (None if v is None else round(v, 4)) for k, v in diffs.items()
                       if v is None or v > TOL_PP}
                return ("final", "") if not bad else ("nicht_final", f"Δ {bad}")
            c_b = _cls(r.get("batch"), (tr or {}).get("batch"), _fetch_ok(r), _fetch_ok(tr or {}))
            c_s = _cls(r.get("single"), (tr or {}).get("single"),
                       bool(r.get("single")), bool((tr or {}).get("single")))
            rank = {"nicht_final": 2, "unbestimmt": 1, "final": 0}
            cls, detail = max((c_b, c_s), key=lambda c: rank[c[0]])
            detail = f"batch={c_b[0]} {c_b[1]} | einzeln={c_s[0]} {c_s[1]}".strip()
            f1.append({**base, "klasse": cls, "detail": detail})
            # F1 .info
            inf = r.get("info") or {}
            rmt = num(inf.get("regularMarketTime"))
            if rmt is None or not tr or not _row(tr.get("batch"), D):
                f1i.append({**base, "klasse": "unbestimmt", "bezugstag": None, "rmp": inf.get("regularMarketPrice")})
            else:
                bez = datetime.fromtimestamp(rmt, tz=timezone.utc).astimezone(ET).date().isoformat()
                dd = rel_pp(inf.get("regularMarketPrice"), _row(tr["batch"], D)["c"])
                ok = bez == D and dd is not None and dd <= TOL_PP
                f1i.append({**base, "klasse": "passt" if ok else "passt_nicht", "bezugstag": bez,
                            "rmp": inf.get("regularMarketPrice"),
                            "prev_close": inf.get("previousClose"), "delta_pp": None if dd is None else round(dd, 4)})
            # F2 OI
            nc, tc = r.get("chain"), (tr or {}).get("chain")
            pc = (r.get("prod") or {}).get("chain")
            if not nc or not tc or nc.get("expiry") != tc.get("expiry"):
                f2.append({**base, "klasse": "unbestimmt", "nacht_eq_tag": None, "nacht_eq_prod": None})
            else:
                def eq(a, b):
                    if not a or not b or a.get("expiry") != b.get("expiry"):
                        return None
                    common = [(s, k) for s in ("calls", "puts") for k in (a.get(s) or {})
                              if k in (b.get(s) or {})]
                    if not common:
                        return None
                    return all(a[s][k] == b[s][k] for s, k in common)
                e_t, e_p = eq(nc, tc), eq(nc, pc)
                f2.append({**base, "klasse": "unbestimmt" if e_t is None else ("gleich" if e_t else "anders"),
                           "nacht_eq_tag": e_t, "nacht_eq_prod": e_p, "expiry": nc.get("expiry")})
            # F3 (nur Top-10 von D mit Prod-Werten)
            p = r.get("prod") or {}
            if "entry_price" in p:
                nr = _row(r.get("batch"), D)
                if not _fetch_ok(r) or nr is None:
                    f3.append({**base, "klasse": "unbestimmt"})
                else:
                    checks = {}
                    if num(p.get("entry_price")) is not None and num(nr.get("c")) is not None:
                        checks["entry_price"] = rel_pp(p["entry_price"], nr["c"]) <= TOL_PP
                    rv = _rvol_at(r["batch"], D)
                    if num(p.get("rvol")) is not None and rv is not None:
                        # rvol ist mit 3 Nachkommastellen gespeichert
                        checks["rvol"] = abs(p["rvol"] - round(rv, 3)) <= 0.0011
                    ep = _epr_at(r["batch"], D)
                    if num(p.get("entry_past_return_5d")) is not None and ep is not None:
                        checks["entry_past_return_5d"] = abs(p["entry_past_return_5d"] - ep) <= TOL_PP + 1e-9
                    if any(nr.get(k) is None for k in (*PRICE_FIELDS, "v")):
                        cls = "anders"          # Nacht-Zeile selbst unvollständig
                    elif "entry_price" not in checks:
                        cls = "unbestimmt"
                    elif all(checks.values()):
                        cls = "gleich"
                    elif tk in halfrow.get(D, set()):
                        cls = "vollstaendiger"
                    else:
                        cls = "anders"
                    f3.append({**base, "klasse": cls, "checks": checks, "prod": {k: p.get(k) for k in
                               ("entry_price", "rvol", "entry_past_return_5d")},
                               "nacht": {"close": nr.get("c"), "rvol": rv, "epr": ep}})

    def verdict(rows, good, bad_set, min_d=2, min_pairs=1):
        ds = {r["D"] for r in rows if r["klasse"] != "unbestimmt"}
        n = len(rows)
        n_unb = sum(r["klasse"] == "unbestimmt" for r in rows)
        if any(r["klasse"] in bad_set for r in rows):
            return "NEIN"
        if len(ds) >= min_d and sum(r["klasse"] == good for r in rows) >= min_pairs \
                and n and n_unb / n <= 0.20:
            return "JA"
        return "UNBESTIMMT"

    v1 = verdict(f1, "final", {"nicht_final"})
    v1i = verdict(f1i, "passt", {"passt_nicht"})
    v2 = verdict(f2, "gleich", {"anders"}, min_pairs=5)
    v3 = verdict(f3, "gleich", {"anders", "vollstaendiger"})
    when = {"über_nacht": sum(1 for r in f2 if r.get("nacht_eq_prod") is False),
            "vor_handelsbeginn": sum(1 for r in f2 if r.get("nacht_eq_prod") is True and r.get("nacht_eq_tag") is False),
            "unverändert": sum(1 for r in f2 if r.get("nacht_eq_prod") is True and r.get("nacht_eq_tag") is True)}
    return {"verdikte": {"F1_zeile": v1, "F1_info": v1i, "F2_oi": v2, "F3_produktion": v3},
            "f2_zeitpunkt": when, "f1": f1, "f1_info": f1i, "f2": f2, "f3": f3,
            "n_nacht_messungen": len(nights), "n_tag_messungen": len(days),
            "D_mit_tagpaar": sorted({n["meta"]["D"] for n in nights if n["meta"]["D"] in days})}


def parse_halfrow(paths) -> dict:
    out: dict = {}
    for p in paths:
        for line in pathlib.Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
            if "[halfrow_probe] ticker=" not in line:
                continue
            kv = dict(x.split("=", 1) for x in line.split("[halfrow_probe] ", 1)[1].split() if "=" in x)
            if kv.get("ticker") and kv.get("row_date"):
                out.setdefault(kv["row_date"], set()).add(kv["ticker"])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("auto", "once"), default="auto")
    ap.add_argument("--kind", choices=("night", "day"), default="night")
    ap.add_argument("--evaluate", nargs="*")
    ap.add_argument("--halfrow", nargs="*", default=[])
    ap.add_argument("--out", default=os.environ.get("RUNNER_TEMP", "") + "/night_probe"
                    if os.environ.get("RUNNER_TEMP") else None)
    a = ap.parse_args(argv)
    if a.evaluate is not None:
        res = evaluate(load_measurements(a.evaluate), parse_halfrow(a.halfrow))
        print(VERDICT_RULES)
        print(json.dumps(res, ensure_ascii=False, indent=1, default=list))
        return 0
    out = pathlib.Path(a.out) if a.out else None
    f = real_fetchers()
    if a.mode == "once":
        print(VERDICT_RULES, flush=True)
        emit(measure(datetime.now(timezone.utc), f), out)
        return 0
    return run_auto(f, out, kind=a.kind)


if __name__ == "__main__":
    sys.exit(main())
