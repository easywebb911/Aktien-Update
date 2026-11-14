#!/usr/bin/env python3
"""Score-Abgleich (dauerhafter Wächter aus Probe 1, Easy-Entscheid 14.11.2026).

Rechnet den gespeicherten Abend-Score jeder Postclose-Top-10-Zeile aus
``score_inflation_log.jsonl`` mit ENDGÜLTIGEN Kursen nach (Tageszeile D erst ab
``trading_date.last_settled_close_date``) und meldet Abweichungen. Aufgerufen aus
``scripts/truth_check.py`` (Wahrheits-Abgleich); bewertet von Health-Check S16.

Rechenmodell (aus ``scripts/probe_halbzeile_score.py``, Lauf 43578382904:
Modell reproduziert 210/210 gespeicherte Scores): die Score-Eingaben, die aus der
LETZTEN Tageszeile rechnen, werden aus endgültigen Kursen neu bestimmt —

  * Gap & Hold (Open D, Schluss D−1, Schluss D)
  * RS vs. SPY (20 T, Aktie vs. ^GSPC bis D)
  * rvol (Volumen D / Mittel 20 bis D)
  * Kombi-Bonus (rvol ≥ 2 als eine der 4 Bedingungen, Fall 1)
  * relative Tagesbewegung (``change`` − ^GSPC-Tagesbewegung, Momentum-Teil)
    — nur für Zeilen, die ``change``/``spx_daily_perf`` gespeichert haben
    (seit Fix B, 14.11.2026); ältere Zeilen: Teil unverändert, gezählt als
    ``momentum_nicht_pruefbar``
  * rsi14 und change_2d auf Tag D → Late-Runner (×0,85)

und über dieselbe Kette wie im Lauf (score_raw → Glättung → Trend → Late-Runner
→ Agent-Boost) in einen nachgerechneten ``score_total`` überführt.

Geprüft werden nur Abende, die Fix B schon geschrieben hat (Zeilen mit
``letzte_zeile``) — ältere Abende enthalten die bekannte Halbzeile (Probe 1).

BLINDHEIT: liest nur Eingaben und Scores aus ``score_inflation_log.jsonl`` und
Kurse bis einschließlich D. Kein Ergebnisfeld, keine Ergebnisdatei.
"""
from __future__ import annotations

import math
import statistics
import sys
import pathlib
from datetime import date, datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import trading_date  # noqa: E402

ET = trading_date._NY
SPX = "^GSPC"
TOL_FEIN = 0.05     # |Δ| ab 0,05 (Info)
TOL_GROB = 0.5      # |Δ| ab 0,5  (warn/crit, Easy-Entscheid 14.11.2026)
REPRO_TOL = 0.06    # Modell reproduziert den gespeicherten score_total
MAX_EVENINGS_PER_RUN = 5
MAX_ROWS_LOGGED = 30


class RateLimited(Exception):
    pass


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ── reine Bausteine (wie im Lauf, siehe generate_report.score) ──────────────
def gap_pts(cur_open, prev_close, price) -> float:
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
    r = _f(rs)
    if r is None:
        return 0.0
    t = config.RS_SPY_THRESHOLD_PCT
    return float(round(max(-t, min(t, r)) / t * config.RS_SPY_PTS_MAX))


def rv_component(rvol, no_short: bool) -> float:
    v = _f(rvol) or 0.0
    return min((v - 1.0) / 2.0, 1.0) * (30.0 if no_short else 23.0)


def mom_component(change, spx_daily, no_short: bool) -> float:
    """Momentum-Teil von ``score()``: min(max(change − spx, 0)/8, 1) × 14 (× 20 ohne Short-Daten)."""
    adj = (_f(change) or 0.0) - ((_f(spx_daily) or 0.0) if config.USE_RELATIVE_MOMENTUM else 0.0)
    return min(max(adj, 0.0) / 8.0, 1.0) * (20.0 if no_short else 14.0)


def combo_pts(sf, sr, rvol, si_trend, no_short: bool) -> float:
    """Kombi-Bonus von ``score()`` (nur Fall 1)."""
    if no_short:
        return 0.0
    n = sum([(_f(sf) or 0) >= 30, (_f(sr) or 0) >= 5, (_f(rvol) or 0) >= 2.0, si_trend == "up"])
    return float(config.COMBO_BONUS) if n >= 3 else 0.0


def late_flag(rsi14, change_2d) -> bool:
    r = _f(rsi14) or 0.0
    c = _f(change_2d)
    return r > config.LATE_RUNNER_RSI_THRESHOLD or (
        c is not None and c / 100.0 > config.LATE_RUNNER_MOVE_2D_THRESHOLD)


def pipeline_total(score_raw, score_smoothed, trend_bonus, late, factor,
                   d_raw: float, no_short: bool) -> float:
    """Gespeicherte Kette mit verschobenem Roh-Score nachrechnen (wie Probe 1)."""
    raw = float(score_raw)
    cap = 50.0 if no_short else 100.0
    raw_new = max(0.0, min(raw + d_raw, max(cap, raw)))
    pre = float(score_smoothed) - float(trend_bonus or 0.0)
    if abs(pre - round(min(raw, 100.0), 1)) <= 0.051:
        sm = raw_new
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
    """Eingaben aus der ENDGÜLTIGEN Tageszeile D (letztes Element = D)."""
    c = [x for x in closes if _f(x) is not None]
    out = {"rsi14": None, "change_2d": None, "perf_20d": None, "gap_pts": 0.0,
           "rvol": None, "rs": None, "spx_daily": None}
    if len(c) < 3 or _f(closes[-1]) is None:
        return out
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
    if len(sc) >= 2 and sc[-2]:
        out["spx_daily"] = (sc[-1] - sc[-2]) / sc[-2] * 100
    return out


def evaluate_row(row: dict, fin: dict) -> dict:
    """Δ je Top-10-Zeile: gespeichert (Lauf) vs. nachgerechnet (endgültig)."""
    sub, drv = row.get("sub_scores") or {}, row.get("drivers_raw") or {}
    no_short = not (_f(drv.get("short_float")) or 0) and not (_f(drv.get("days_to_cover")) or 0)
    g_old, g_new = _f(sub.get("gap_pts")) or 0.0, fin["gap_pts"]
    r_old, r_new = _f(sub.get("rs_spy_pts")) or 0.0, rs_pts(fin.get("rs"))
    rv_old_val = drv.get("rel_volume")
    rv_new_val = fin["rvol"] if fin["rvol"] is not None else rv_old_val
    v_old, v_new = rv_component(rv_old_val, no_short), rv_component(rv_new_val, no_short)
    trend = drv.get("finra_si_trend")
    c_old = combo_pts(drv.get("short_float"), drv.get("days_to_cover"), rv_old_val, trend, no_short)
    c_new = combo_pts(drv.get("short_float"), drv.get("days_to_cover"), rv_new_val, trend, no_short)
    mom_ok = "change" in drv and "spx_daily_perf" in drv and fin.get("spx_daily") is not None
    if mom_ok:
        m_old = mom_component(drv.get("change"), drv.get("spx_daily_perf"), no_short)
        m_new = mom_component(drv.get("change"), fin["spx_daily"], no_short)
    else:
        m_old = m_new = 0.0
    d_raw = (g_new - g_old) + (r_new - r_old) + (v_new - v_old) + (c_new - c_old) + (m_new - m_old)
    l_old = bool(sub.get("late_runner_active"))
    l_new = late_flag(fin["rsi14"], fin["change_2d"])
    base = (row["score_raw"], row["score_smoothed"], sub.get("score_trend_bonus"))
    t_model_old = pipeline_total(*base, l_old, sub.get("agent_boost_factor"), 0.0, no_short)
    t_new = pipeline_total(*base, l_new, sub.get("agent_boost_factor"), d_raw, no_short)
    return {
        "ticker": row["ticker"], "score_total": row["score_total"],
        "modell_reproduziert": abs(t_model_old - float(row["score_total"])) <= REPRO_TOL,
        "score_neu": t_new, "delta": round(t_new - t_model_old, 2),
        "momentum_geprueft": mom_ok,
        "late_alt": l_old, "late_neu": l_new,
    }


def rank_changes(rows: list[dict]) -> int:
    old = [r["ticker"] for r in sorted(rows, key=lambda r: -float(r["score_total"]))]
    new = [r["ticker"] for r in sorted(rows, key=lambda r: -(float(r["score_total"]) + r["delta"]))]
    return sum(1 for a, b in zip(old, new) if a != b)


def summarize(rows: list[dict]) -> dict:
    def cross(r):
        a, b = float(r["score_total"]), float(r["score_total"]) + r["delta"]
        return (a < 70 <= b) or (a >= 70 > b)
    d = [r["delta"] for r in rows]
    out = {
        "zeilen": len(rows),
        "abw_ab_005": sum(1 for x in d if abs(x) >= TOL_FEIN),
        "abw_ab_05": sum(1 for x in d if abs(x) >= TOL_GROB),
        "wechsel70_mit_abw": sum(1 for r in rows if cross(r) and abs(r["delta"]) >= TOL_GROB),
        "wechsel70_info": sum(1 for r in rows if cross(r) and abs(r["delta"]) < TOL_GROB),
        "modell_nicht_reproduziert": sum(1 for r in rows if not r["modell_reproduziert"]),
        "momentum_nicht_pruefbar": sum(1 for r in rows if not r["momentum_geprueft"]),
    }
    if d:
        out["delta_max_abs"] = round(max(abs(x) for x in d), 2)
        out["delta_median"] = round(statistics.median(d), 3)
    return out


def evening_day(run_ts: str) -> date:
    """Berichtstag D eines Postclose-Laufs (vor 09:30 ET → letzter Handelstag)."""
    et = datetime.fromisoformat(run_ts.replace("Z", "+00:00")).astimezone(ET)
    d = et.date()
    if et.hour < 9 or (et.hour == 9 and et.minute < 30):
        d -= timedelta(days=1)
        while d.weekday() >= 5 or d.isoformat() in config.US_MARKET_HOLIDAYS:
            d -= timedelta(days=1)
    return d


def select_evenings(log_rows: list[dict], final_cut: date, checked: set) -> list[tuple]:
    """Postclose-Abende mit Fix B (Zeilen tragen ``letzte_zeile``), D endgültig,
    noch nicht geprüft. Älteste zuerst, höchstens ``MAX_EVENINGS_PER_RUN``."""
    by: dict = {}
    for r in log_rows:
        if (isinstance(r, dict) and r.get("run_phase") == "postclose" and r.get("ticker")
                and r.get("run_ts")):
            by.setdefault(r["run_ts"], []).append(r)
    out = []
    for ts, rows in sorted(by.items()):
        if ts in checked or not any(r.get("letzte_zeile") is not None for r in rows):
            continue
        try:
            d = evening_day(ts)
        except ValueError:
            continue
        if d > final_cut:
            continue
        out.append((ts, d, rows))
    return out[:MAX_EVENINGS_PER_RUN]


def _rate(exc) -> bool:
    return "RateLimit" in type(exc).__name__ or "Too Many Requests" in str(exc)


def fetch_evening(tickers: list[str], d: date):
    """Kurse bis einschließlich D (endgültig): {ticker: (closes, opens, volumes)}
    und ^GSPC-Closes. Nie Zeilen nach D (Blindheit)."""
    import yfinance as yf
    try:
        yf.config.debug.hide_exceptions = False
    except Exception:  # noqa: BLE001
        pass
    df = yf.download(sorted(set(tickers)) + [SPX], start=(d - timedelta(days=366)).isoformat(),
                     end=(d + timedelta(days=1)).isoformat(), auto_adjust=True,
                     group_by="ticker", progress=False, threads=False)
    out = {}
    for t in list(tickers) + [SPX]:
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
    spx = out.pop(SPX)
    return out, (spx[0] if spx else [])


def rsi_pandas_ta(closes):
    import pandas as pd
    import pandas_ta as ta
    s = ta.rsi(pd.Series(closes, dtype="float64"), length=14)
    v = None if s is None or s.empty else float(s.iloc[-1])
    return v if v is not None and math.isfinite(v) else None


def run_score_check(log_rows: list[dict], final_cut: date, checked: set,
                    fetch=fetch_evening, rsi_fn=rsi_pandas_ta) -> tuple[dict, list[str]]:
    """Ein Abgleich-Lauf. Returns ``(block_fürs_log, neu_geprüfte_run_ts)``.
    Rate-Limit → Abbruch dieses Teils, noch offene Abende bleiben offen."""
    block = {"abende": [], "zeilen": 0, "abw_ab_005": 0, "abw_ab_05": 0,
             "wechsel70_mit_abw": 0, "wechsel70_info": 0, "modell_nicht_reproduziert": 0,
             "momentum_nicht_pruefbar": 0, "rang_wechsel_max": 0, "ohne_kurse": 0,
             "rate_limit_abbruch": False, "abweichungen": []}
    done: list[str] = []
    for ts, d, rows in select_evenings(log_rows, final_cut, checked):
        try:
            data, spx = fetch([r["ticker"] for r in rows], d)
        except Exception as exc:  # noqa: BLE001
            if _rate(exc):
                block["rate_limit_abbruch"] = True
                break
            block["abende"].append({"run_ts": ts, "D": d.isoformat(), "fehler": type(exc).__name__})
            continue
        evald = []
        for r in rows:
            got = data.get(r["ticker"])
            if not got:
                block["ohne_kurse"] += 1
                continue
            evald.append(evaluate_row(r, final_inputs(*got, spx, rsi_fn)))
        s = summarize(evald)
        rk = rank_changes(evald)
        block["abende"].append({"run_ts": ts, "D": d.isoformat(), "rang_wechsel": rk, **s})
        for k in ("zeilen", "abw_ab_005", "abw_ab_05", "wechsel70_mit_abw", "wechsel70_info",
                  "modell_nicht_reproduziert", "momentum_nicht_pruefbar"):
            block[k] += s.get(k, 0)
        block["rang_wechsel_max"] = max(block["rang_wechsel_max"], rk)
        for e in evald:
            if abs(e["delta"]) >= TOL_GROB and len(block["abweichungen"]) < MAX_ROWS_LOGGED:
                block["abweichungen"].append({"ticker": e["ticker"], "D": d.isoformat(),
                                              "score_alt": e["score_total"],
                                              "score_neu": e["score_neu"], "delta": e["delta"]})
        done.append(ts)
    return block, done
