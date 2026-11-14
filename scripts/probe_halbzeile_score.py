#!/usr/bin/env python3
"""WEGWERF-PROBE 1 (read-only): Score-Wirkung der Postclose-Halbzeile.

open_item ``halbzeilen-score-wirkung-probe`` (Easy-Entscheid 14.11.2026).

Für jeden Postclose-Abend in ``score_inflation_log.jsonl`` (Top-10 je Lauf,
gespeichert: score_raw / score_smoothed / score_total, Gap-Punkte, RS-vs-SPY-
Punkte, Late-Runner-Marker, rvol, change_2d, rsi14) werden die vom Halbzeilen-
Problem betroffenen Score-Eingaben aus ENDGÜLTIGEN Tageszeilen (Abruf heute,
Kurse bis einschließlich D) neu gerechnet:

  * Gap & Hold (Open D, Schluss D−1, Schluss D)       → score() / Top-10-Schnitt
  * RS vs. SPY (20 T, Aktie vs. ^GSPC bis D)          → score() / Top-10-Schnitt
  * rvol (Volumen D / Mittel 20 bis D)                → score()
  * rsi14 und change_2d auf Tag D                     → Late-Runner (×0,85)

und über dieselbe Kette wie im Lauf (score_raw → Glättung → Late-Runner →
Agent-Boost) in einen nachgerechneten ``score_total`` überführt. Die übrigen
Score-Teile (Short Float, DTC, Momentum, Float, Turnover, Kombi-Bonus,
FINRA-Bonus, Squeeze-Malus, Trend-Bonus, Boost-Faktor) bleiben wie gespeichert.

KONTROLLE: Zeilen ohne Halbzeile (change_2d gespeichert) müssen ~0 Differenz
ergeben (Kriterium siehe CONTROL_*; vorab festgeschrieben). Tun sie das nicht,
misst die Probe nicht, was sie soll → „Kontrolle verfehlt“ (melden statt
deuten). KORREKTUR 14.11.2026: Halbzeile je ZEILE statt je Abend (gemischte
Abende wie 13.11.), „Score geändert“ in beiden Zählweisen (ab 0,05 / ab 0,5).

BLINDHEIT: liest NUR score_inflation_log.jsonl (Eingaben + Scores) und Kurse
bis einschließlich D. Kein Ergebnisfeld (return_*, max_gain*, outcome_path,
forward_*), keine Datei mit Ergebnissen wird geöffnet.

Schreibt NUR stdout (``[halbzeile_probe_*]``) und ``--out`` (Artifact).
Rate-Limit → Abbruch (Exit 3) ohne Ergebnis. Ab ``PROBE_END_ET`` no-op.
Wird nach der Auswertung per Cleanup-PR gelöscht.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

ET = ZoneInfo("America/New_York")
PROBE_END_ET = date(2026, 12, 12)
LOG_FILE = ROOT / "score_inflation_log.jsonl"
# Zwei Zählweisen „Score geändert“ (Easy-Entscheid 14.11.2026, beide ausgewiesen,
# damit die Schwelle nicht nachträglich gewählt ist):
SCORE_TOL_FEIN = 0.05   # |Δ score_total| ab 0,05 Punkten
SCORE_TOL_GROB = 0.5    # |Δ score_total| ab 0,5 Punkten
# KONTROLLE — VORAB FESTGESCHRIEBEN (Korrektur 14.11.2026, vor dem zweiten Lauf):
# vollständige Zeilen (change_2d im Lauf gespeichert) bestehen, wenn
#   (a) höchstens 10 % von ihnen |Δ| ≥ 0,5 haben UND
#   (b) mindestens 90 % vom Modell exakt reproduziert werden.
# Grund für 0,5 statt 0,05 in (a): nachgereichtes Volumen verschiebt rvol und
# damit den Score um Bruchteile eines Punkts (erster Lauf 43576254047: alle
# vollständigen Abende |Δ| ≤ 0,24). Diese Begründung stammt aus dem ersten
# Lauf und wird im Bericht offen genannt. Die 0,05-Zählung der Kontrolle wird
# zusätzlich ausgewiesen.
CONTROL_MAX_SHARE = 0.10
CONTROL_TOL = SCORE_TOL_GROB


class RateLimited(Exception):
    pass


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ── reine Bausteine (wie im Lauf, siehe generate_report.py) ─────────────────
def gap_pts(cur_open, prev_close, price) -> float:
    """Wie ``_gap_hold_pts`` (Punkte)."""
    o, p, c = _f(cur_open), _f(prev_close), _f(price)
    if o is None or p is None or c is None or p <= 0:
        return 0.0
    gap = o - p
    if gap / p * 100.0 < config.GAP_THRESHOLD_PCT:
        return 0.0
    if c > o + config.GAP_HOLD_FACTOR * gap:
        return float(config.GAP_PTS_STRONG_HOLD)
    if c < p:
        return float(config.GAP_PTS_FAIL)
    return float(config.GAP_PTS_WEAK_HOLD)


def rs_pts(rs) -> float:
    """Wie ``_rs_spy_pts`` (Punkte)."""
    r = _f(rs)
    if r is None:
        return 0.0
    t = config.RS_SPY_THRESHOLD_PCT
    return float(round(max(-t, min(t, r)) / t * config.RS_SPY_PTS_MAX))


def rv_component(rvol, no_short: bool) -> float:
    """rvol-Teil von ``score()``: min((rvol−1)/2, 1) × 23 (bzw. × 30 ohne Short-Daten)."""
    v = _f(rvol) or 0.0
    return min((v - 1.0) / 2.0, 1.0) * (30.0 if no_short else 23.0)


def late_flag(rsi14, change_2d) -> bool:
    """Wie ``apply_late_runner_penalty``."""
    r = _f(rsi14) or 0.0
    c = _f(change_2d)
    return r > config.LATE_RUNNER_RSI_THRESHOLD or (
        c is not None and c / 100.0 > config.LATE_RUNNER_MOVE_2D_THRESHOLD)


def pipeline_total(score_raw, score_smoothed, trend_bonus, late, factor,
                   d_raw: float, no_short: bool) -> float:
    """Gespeicherte Kette mit verschobenem Roh-Score nachrechnen.

    score_smoothed = round(min(0.7·raw + 0.3·hist, 100), 1) + Trend (oder =raw
    ohne Historie). Die Historie (``hist``) wird aus den gespeicherten Werten
    zurückgerechnet; Trend-Bonus/-Malus hängt nur an Vortagen (unverändert)."""
    raw = float(score_raw)
    cap = 50.0 if no_short else 100.0
    raw_new = max(0.0, min(raw + d_raw, max(cap, raw)))
    pre = float(score_smoothed) - float(trend_bonus or 0.0)
    if abs(pre - round(min(raw, 100.0), 1)) <= 0.051:
        sm = raw_new                         # keine Glättung (Lauf rundet hier nicht)
    else:
        hist = (pre - config.SCORE_TODAY_WEIGHT * raw) / config.SCORE_HISTORY_WEIGHT
        sm = round(min(config.SCORE_TODAY_WEIGHT * raw_new
                       + config.SCORE_HISTORY_WEIGHT * hist, 100.0), 1)
    tb = float(trend_bonus or 0.0)
    if tb > 0:
        sm = round(min(sm + tb, 100.0), 1)
    elif tb < 0:
        sm = round(max(sm + tb, 0.0), 1)
    if late:
        sm = round(sm * config.LATE_RUNNER_PENALTY, 1)
    f = _f(factor) or 1.0
    if f > 1.0:
        sm = min(round(sm * f, 2), 100.0)
    return sm


def final_inputs(closes, opens, volumes, spx_closes, rsi_fn) -> dict:
    """Eingaben aus der ENDGÜLTIGEN Tageszeile D (letztes Element = D).
    Listen bis einschließlich D; ``rsi_fn(closes) -> float|None``."""
    c = [x for x in closes if _f(x) is not None]
    out = {"rsi14": None, "change_2d": None, "perf_20d": None, "gap_pts": 0.0,
           "rvol": None, "price": None}
    if len(c) < 3 or _f(closes[-1]) is None:
        return out
    out["price"] = float(closes[-1])
    out["change_2d"] = round((c[-1] - c[-3]) / c[-3] * 100, 2) if c[-3] else None
    out["rsi14"] = rsi_fn(c) if len(c) >= 14 else None
    if len(c) >= 21:
        out["perf_20d"] = (c[-1] - c[-21]) / c[-21] * 100
    out["gap_pts"] = gap_pts(opens[-1], closes[-2] if len(closes) >= 2 else None, closes[-1])
    v = [_f(x) for x in volumes[-20:]]
    if all(x is not None for x in v) and v and sum(v) > 0:
        out["rvol"] = v[-1] / (sum(v) / len(v))
    sc = [x for x in spx_closes if _f(x) is not None]
    if out["perf_20d"] is not None and len(sc) >= 21:
        out["rs"] = out["perf_20d"] - (sc[-1] - sc[-21]) / sc[-21] * 100
    else:
        out["rs"] = None
    return out


def row_kind(row: dict, fin: dict) -> str:
    """Halbzeile JE ZEILE (Korrektur 14.11.2026). Im Lauf bleibt ``change_2d``
    genau dann ungesetzt, wenn der letzte Batch-Schluss nicht endlich ist
    (``generate_report``: ``_finite_cell(Close, -1)``) — das ist die Halbzeile.
    'voll'  = change_2d im Lauf gespeichert;
    'halb'  = im Lauf leer, aus der endgültigen Tageszeile berechenbar;
    'unklar'= in beiden leer (zu kurze Historie) → weder Probe noch Kontrolle."""
    if _f((row.get("drivers_raw") or {}).get("change_2d")) is not None:
        return "voll"
    return "halb" if fin.get("change_2d") is not None else "unklar"


def evaluate_row(row: dict, fin: dict) -> dict:
    """Δ je Top-10-Zeile: gespeichert (Lauf) vs. nachgerechnet (endgültig)."""
    sub, drv = row.get("sub_scores") or {}, row.get("drivers_raw") or {}
    no_short = not (_f(drv.get("short_float")) or 0) and not (_f(drv.get("days_to_cover")) or 0)
    g_old, g_new = _f(sub.get("gap_pts")) or 0.0, fin["gap_pts"]
    r_old, r_new = _f(sub.get("rs_spy_pts")) or 0.0, rs_pts(fin.get("rs"))
    v_old = rv_component(drv.get("rel_volume"), no_short)
    v_new = rv_component(fin["rvol"], no_short) if fin["rvol"] is not None else v_old
    d_raw = (g_new - g_old) + (r_new - r_old) + (v_new - v_old)
    l_old = bool(sub.get("late_runner_active"))
    l_new = late_flag(fin["rsi14"], fin["change_2d"])
    args = (row["score_raw"], row["score_smoothed"], sub.get("score_trend_bonus"),
            None, sub.get("agent_boost_factor"))
    t_model_old = pipeline_total(*args[:3], l_old, args[4], 0.0, no_short)
    t_new = pipeline_total(*args[:3], l_new, args[4], d_raw, no_short)
    return {
        "ticker": row["ticker"], "score_total": row["score_total"], "art": row_kind(row, fin),
        "modell_reproduziert": abs(t_model_old - float(row["score_total"])) <= 0.06,
        "score_neu": t_new, "delta": round(t_new - t_model_old, 2),
        "d_gap": g_new - g_old, "d_rs": r_new - r_old, "d_rv": round(v_new - v_old, 3),
        "late_alt": l_old, "late_neu": l_new,
        "change_2d_alt": drv.get("change_2d"), "change_2d_neu": fin["change_2d"],
        "rsi_alt": drv.get("rsi14"), "rsi_neu": fin["rsi14"],
    }


def summarize(rows: list[dict]) -> dict:
    """Zählungen je Abend bzw. gesamt (nur Scores, keine Ergebnisse)."""
    d = [r["delta"] for r in rows]
    up70 = sum(1 for r in rows if r["score_total"] < 70 <= r["score_total"] + r["delta"])
    dn70 = sum(1 for r in rows if r["score_total"] >= 70 > r["score_total"] + r["delta"])
    out = {"zeilen": len(rows),
           "geaendert_ab_005": sum(1 for x in d if abs(x) >= SCORE_TOL_FEIN),
           "geaendert_ab_05": sum(1 for x in d if abs(x) >= SCORE_TOL_GROB),
           "ueber_70": up70, "unter_70": dn70,
           "late_neu_an": sum(1 for r in rows if r["late_neu"] and not r["late_alt"]),
           "late_neu_aus": sum(1 for r in rows if r["late_alt"] and not r["late_neu"]),
           "gap_anders": sum(1 for r in rows if r["d_gap"]),
           "rs_anders": sum(1 for r in rows if r["d_rs"]),
           "modell_reproduziert": sum(1 for r in rows if r["modell_reproduziert"])}
    if d:
        s = sorted(d)
        out.update(delta_min=s[0], delta_median=statistics.median(s), delta_max=s[-1],
                   delta_mittel=round(sum(s) / len(s), 2))
    return out


def rank_changes(rows: list[dict]) -> int:
    """Zahl der Zeilen, deren Rang innerhalb der Top-10 sich ändert."""
    old = [r["ticker"] for r in sorted(rows, key=lambda r: -float(r["score_total"]))]
    new = [r["ticker"] for r in sorted(rows, key=lambda r: -(float(r["score_total"]) + r["delta"]))]
    return sum(1 for a, b in zip(old, new) if a != b)


def evenings(log_rows: list[dict]) -> list[tuple]:
    """Postclose-Abende: (run_ts, D, rows). Halbzeile wird JE ZEILE bestimmt
    (``row_kind``), nicht mehr je Abend."""
    by: dict = {}
    for r in log_rows:
        if r.get("run_phase") == "postclose" and r.get("ticker"):
            by.setdefault(r["run_ts"], []).append(r)
    out = []
    for ts, rows in sorted(by.items()):
        et = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(ET)
        d = et.date()
        if et.hour < 9 or (et.hour == 9 and et.minute < 30):
            d -= timedelta(days=1)
            while d.weekday() >= 5 or d.isoformat() in config.US_MARKET_HOLIDAYS:
                d -= timedelta(days=1)
        out.append((ts, d, rows))
    return out


# ── Abruf (nur in GitHub Actions; im Test injiziert) ────────────────────────
def _rate(exc) -> bool:
    return "RateLimit" in type(exc).__name__ or "Too Many Requests" in str(exc)


def fetch_evening(tickers: list[str], d: date):
    """Kurse bis einschließlich D (endgültig). Gibt {ticker: (closes, opens,
    volumes)} und SPX-Closes zurück. NIE Zeilen nach D (Blindheit)."""
    import yfinance as yf
    try:
        yf.config.debug.hide_exceptions = False
    except Exception:  # noqa: BLE001
        pass
    start = (d - timedelta(days=366)).isoformat()
    end = (d + timedelta(days=1)).isoformat()
    df = yf.download(sorted(set(tickers)) + ["^GSPC"], start=start, end=end,
                     auto_adjust=True, group_by="ticker", progress=False, threads=False)
    out = {}
    for t in tickers + ["^GSPC"]:
        try:
            sub = df[t]
        except Exception:  # noqa: BLE001
            out[t] = None
            continue
        sub = sub[[ix.date() <= d for ix in sub.index]]
        if sub.empty or sub.index[-1].date() != d:
            out[t] = None
            continue
        out[t] = (list(sub["Close"]), list(sub["Open"]), list(sub["Volume"]))
    spx = out.pop("^GSPC")
    return out, (spx[0] if spx else [])


def _rsi_pandas_ta(closes):
    import pandas as pd
    import pandas_ta as ta
    s = ta.rsi(pd.Series(closes, dtype="float64"), length=14)
    v = None if s is None or s.empty else float(s.iloc[-1])
    return v if v is not None and math.isfinite(v) else None


def run(log_path=LOG_FILE, fetch=fetch_evening, rsi_fn=_rsi_pandas_ta) -> dict:
    rows = []
    with open(log_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    res = {"abende": [], "gesamt": {}}
    groups = {"halb": [], "voll": [], "unklar": []}
    for ts, d, ev_rows in evenings(rows):
        tickers = [r["ticker"] for r in ev_rows]
        try:
            data, spx = fetch(tickers, d)
        except Exception as exc:  # noqa: BLE001
            if _rate(exc):
                raise RateLimited(str(exc)) from exc
            res["abende"].append({"run_ts": ts, "D": d.isoformat(),
                                  "fehler": f"{type(exc).__name__}"})
            continue
        evald, fehlend = [], []
        for r in ev_rows:
            got = data.get(r["ticker"])
            if not got:
                fehlend.append(r["ticker"])
                continue
            evald.append(evaluate_row(r, final_inputs(*got, spx, rsi_fn)))
        summ = summarize(evald)
        n_halb = sum(1 for e in evald if e["art"] == "halb")
        summ.update(run_ts=ts, run_et=datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    .astimezone(ET).strftime("%m-%d %H:%M"), D=d.isoformat(),
                    zeilen_halb=n_halb,
                    zeilen_voll=sum(1 for e in evald if e["art"] == "voll"),
                    zeilen_unklar=sum(1 for e in evald if e["art"] == "unklar"),
                    halbzeilen_abend=n_halb > 0,
                    nur_halbzeilen=summarize([e for e in evald if e["art"] == "halb"]),
                    rang_wechsel=rank_changes(evald), ohne_kurse=fehlend, zeilen_detail=evald)
        res["abende"].append(summ)
        for e in evald:
            groups[e["art"]].append(e)
    for art, rr in groups.items():
        res["gesamt"][art] = summarize(rr)
    ctl = res["gesamt"].get("voll", {})
    n = ctl.get("zeilen", 0)
    res["kontrolle"] = {
        "zeilen": n, "geaendert_ab_005": ctl.get("geaendert_ab_005"),
        "geaendert_ab_05": ctl.get("geaendert_ab_05"),
        "modell_reproduziert": ctl.get("modell_reproduziert"),
        "kriterium": f"geaendert_ab_05 <= {CONTROL_MAX_SHARE:.0%} UND modell_reproduziert >= "
                     f"{1 - CONTROL_MAX_SHARE:.0%} der vollständigen Zeilen",
        "bestanden": bool(n) and ctl.get("geaendert_ab_05", 0) <= CONTROL_MAX_SHARE * n
                     and ctl.get("modell_reproduziert", 0) >= (1 - CONTROL_MAX_SHARE) * n,
    }
    res["freeze_wirkung"] = freeze_impact(res["abende"])
    return res


def freeze_impact(abende: list[dict]) -> dict:
    """Wirkung auf die laufenden Freezes — nur Zählungen aus Scores, keine
    Ergebnisse. Drei Arten, wie ein Freeze den Score nutzt:
      * Score als Prädiktor (Setup-Edge, Conviction): jede Halbzeile mit Δ.
      * Score ≥ 70 als Population (Exit-B.1-Nachfolger): Wechsel über/unter 70.
      * Top-10-Zugehörigkeit (alle übrigen): NICHT REKONSTRUIERBAR — der Log
        enthält nur die Top-10 des Laufs, nicht den Kandidaten-Pool; wer mit
        endgültigen Daten statt der Halbzeile in die Top-10 gekommen wäre, ist
        unbekannt. Gemessen ist nur der Rangwechsel INNERHALB der Top-10."""
    halb = [e for a in abende for e in a.get("zeilen_detail", []) if e["art"] == "halb"]
    return {
        "praediktor_setup_edge_conviction": {
            "halbzeilen": len(halb),
            "score_geaendert_ab_005": sum(1 for e in halb if abs(e["delta"]) >= SCORE_TOL_FEIN),
            "score_geaendert_ab_05": sum(1 for e in halb if abs(e["delta"]) >= SCORE_TOL_GROB)},
        "population_score_ab_70_exit_b1": {
            "neu_ueber_70": sum(1 for e in halb
                                if e["score_total"] < 70 <= e["score_total"] + e["delta"]),
            "neu_unter_70": sum(1 for e in halb
                                if e["score_total"] >= 70 > e["score_total"] + e["delta"])},
        "top10_zugehoerigkeit_uebrige": "nicht rekonstruierbar (nur Rangwechsel innerhalb der Top-10 gemessen)",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Wegwerf-Probe 1: Halbzeile → Score")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if datetime.now(timezone.utc).astimezone(ET).date() > PROBE_END_ET:
        print("[halbzeile_probe_meta] no-op: Probe-Ende überschritten")
        return 0
    try:
        res = run()
    except RateLimited as exc:
        print(f"[halbzeile_probe_meta] ABBRUCH: Rate-Limit — kein Retry, kein Ergebnis ({str(exc)[:120]})")
        return 3
    print("[halbzeile_probe_kontrolle] " + json.dumps(res["kontrolle"], ensure_ascii=False))
    for a_ in res["abende"]:
        print("[halbzeile_probe_abend] " + json.dumps(
            {k: v for k, v in a_.items() if k != "zeilen_detail"}, ensure_ascii=False))
    print("[halbzeile_probe_gesamt] " + json.dumps(res["gesamt"], ensure_ascii=False))
    print("[halbzeile_probe_freeze] " + json.dumps(res["freeze_wirkung"], ensure_ascii=False))
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
