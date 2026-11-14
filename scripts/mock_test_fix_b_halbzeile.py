#!/usr/bin/env python3
"""Tests für Fix B (Halbzeile im Postclose, 14.11.2026) und den Score-Abgleich
(Wächter im Wahrheits-Abgleich). Ohne pandas/yfinance (CI-tauglich): reine
Funktionen per Quelltext-Extraktion, Rest per Quelltext-Prüfung."""
from __future__ import annotations

import json
import math
import pathlib
import re
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import health_check as hc  # noqa: E402
import score_check as sc  # noqa: E402

_fails: list[str] = []
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
BH = (ROOT / "backtest_history.py").read_text(encoding="utf-8")


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {str(detail)[:300]}"))
    if not cond:
        _fails.append(name)


def _func(src: str, name: str) -> str:
    m = re.search(rf"^def {name}\(.*?(?=^def |^[A-Z_]+ *[:=]|^# ──|\Z)", src, re.S | re.M)
    return m.group(0) if m else ""


def _ns():
    ns = {"math": math, "datetime": datetime, "timezone": timezone, "ZoneInfo": ZoneInfo}
    m = re.search(r"^_LAST_BAR_CELLS = \(.*?^\)\n", GR, re.S | re.M)
    exec(m.group(0), ns)  # noqa: S102
    for line in ("LAST_BAR_COMPLETE", "LAST_BAR_FILLED", "LAST_BAR_PRIOR", "_NY_TZ"):
        mm = re.search(rf"^{line} = .*$", GR, re.M)
        exec(mm.group(0), ns)  # noqa: S102
    for fn in ("_halfrow_probe_num", "_info_market_date_et", "_last_bar_decision"):
        exec(_func(GR, fn), ns)  # noqa: S102
    return ns


def test_decision():
    print("Entscheidung letzte Tageszeile (pure)")
    ns = _ns()
    dec = ns["_last_bar_decision"]
    d = date(2026, 11, 13)
    ts = datetime(2026, 11, 13, 21, 0, 1, tzinfo=timezone.utc).timestamp()
    info = {"regularMarketOpen": 2.085, "regularMarketDayHigh": 2.92, "regularMarketDayLow": 1.77,
            "regularMarketPrice": 2.61, "regularMarketVolume": 73554559.0, "regularMarketTime": ts}
    full = {"Open": 1, "High": 2, "Low": 0.5, "Close": 1.5, "Volume": 10}
    half = {"Open": float("nan"), "High": float("nan"), "Low": float("nan"),
            "Close": float("nan"), "Volume": 73554559.0}
    check("vollständig → unverändert", dec(d, full, info) == ("vollstaendig", {}))
    hk, fills = dec(d, half, info)
    check("Halbzeile + .info gleicher Tag → gefüllt (nur fehlende Zellen, Volumen bleibt)",
          hk == "aus_info_gefuellt" and fills == {"Open": 2.085, "High": 2.92, "Low": 1.77,
                                                   "Close": 2.61}, (hk, fills))
    check("ISSC-Fall (.info vom 28.10.) → Vortag-Rückfall",
          dec(d, dict(half, Volume=None), dict(info, regularMarketTime=ts - 16 * 86400))[0]
          == "vortag_rueckfall")
    check("benötigter Wert nicht endlich → Vortag-Rückfall",
          dec(d, half, dict(info, regularMarketPrice=float("nan")))[0] == "vortag_rueckfall")
    check("Preis ≤ 0 → Vortag-Rückfall", dec(d, half, dict(info, regularMarketPrice=0))[0]
          == "vortag_rueckfall")
    check("ohne .info → Vortag-Rückfall", dec(d, half, {})[0] == "vortag_rueckfall")
    check("^GSPC: nur Close geprüft",
          dec(d, {"Close": float("nan"), "Volume": None}, info, ("Close",))
          == ("aus_info_gefuellt", {"Close": 2.61}))
    # 21:00 UTC am 13.11. = 16:00 ET → ET-Datum 13.11.; 03:00 UTC 14.11. = 22:00 ET 13.11.
    ts2 = datetime(2026, 11, 14, 3, 0, tzinfo=timezone.utc).timestamp()
    check("ET-Datum (nicht UTC) entscheidet", dec(d, half, dict(info, regularMarketTime=ts2))[0]
          == "aus_info_gefuellt")
    check("Determinismus: gleiche Eingaben → gleiches Ergebnis",
          dec(d, half, info) == dec(d, dict(half), dict(info)))


def test_wiring():
    print("Verdrahtung: eine Stelle, nur Postclose")
    body = GR[GR.find("def get_yfinance_batch("):GR.find("# News-Coverage-Watchdog")]
    check("Reparatur nur im Postclose", '_repair_on = _REPORT_RUN_PHASE == "postclose"' in body)
    check("_hist_stats liest über _df_for", "df = _df_for(ticker)\n                if df is not None"
          in body)
    check("change_2d/3d/5d lesen über _df_for", "_df = _df_for(ticker)\n            _c_now" in body)
    check("kein zweiter direkter Batch-Zugriff außer _raw_df_for und Log-Probe",
          body.count("hist_batch[ticker]") == 1, body.count("hist_batch[ticker]"))
    check("Herkunft im Ergebnis", '"letzte_zeile":   _last_bar.get(ticker)' in body)
    check("bar_date aus dem reparierten Frame", "(_df_for(ticker))),\n            # Fix B" in body)
    check("Log-Probe (nan_pct) misst den Rohzustand vor der Reparatur",
          body.find("_halfrow_probe_lines(hist_batch") < body.find("_frames: dict = {}"))
    main = GR[GR.find("def main():"):]
    check("^GSPC-Reparatur nur im Postclose",
          'if run_phase == "postclose":\n                _spx_close, _spx_hk = _spx_close_with_repair(_spx_hist)'
          in main)
    check("Nachtlauf (#698): leere Zeile NACH dem Berichtstag zuerst verwerfen",
          "report_day=_REPORT_DAY_ET" in body and "if last_day > report_day and incomplete" in GR)
    check("^GSPC-.info mit Timeout", ".result(timeout=15)" in GR[GR.find("def _spx_close_with_repair"):])
    check("Kartenhinweis in v1 und v2", GR.count("_momentum_5t_row_html(s) + _last_bar_note_row_html(s)") == 2)


def test_backtest_and_s15():
    print("Backtest-Kennzeichen, Verwurfsgrund, S15, Digest")
    check("eigener Verwurfsgrund zeile_nicht_fuellbar", '"zeile_nicht_fuellbar"' in BH
          and 's.get("letzte_zeile") == "vortag_rueckfall"' in BH)
    check("Herkunftsfelder forward-only (nur wenn gesetzt)",
          'if s.get("letzte_zeile") is not None:\n            entry["letzte_zeile"]' in BH
          and 'entry["spx_letzte_zeile"]' in BH)
    check("S10_OBSERVED", "letzte_zeile" in config.S10_OBSERVED_FIELDS
          and "spx_letzte_zeile" in config.S10_OBSERVED_FIELDS)
    now = datetime(2026, 11, 17, 3, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "vg.jsonl"
        recs = [{"ts_utc": "2026-11-17T02:00:00Z", "report_date": "16.11.2026",
                 "reason": "zeile_nicht_fuellbar", "ticker_count": 2, "now_et": "2026-11-16T21:00:00-05:00"},
                {"ts_utc": "2026-11-12T02:00:00Z", "report_date": "11.11.2026",
                 "reason": "zeile_nicht_fuellbar", "ticker_count": 1},
                {"ts_utc": "2026-11-17T02:00:00Z", "report_date": "16.11.2026",
                 "reason": "holiday_or_prior_bar", "ticker_count": 5}]
        p.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        line = hc.unfillable_entries_line(p, now_ts=now)
        fails = hc.evaluate_state_invariants(
            run_phase="postclose", vintage_guard_log_path=str(p), now_utc=now,
            ki_agent_only=False) if "now_utc" in hc.evaluate_state_invariants.__code__.co_varnames else None
    check("Digest: 24 h und 7 Tage getrennt gezählt",
          line == "🧩 2 Einträge entfallen: Zeile nicht füllbar (24 h) · 3 in 7 Tagen", line)
    src = (ROOT / "health_check.py").read_text(encoding="utf-8")
    check("S15 meldet entfallene Einträge (eigener warn)",
          "Backtest-Einträge entfallen: letzte Tageszeile" in src
          and "reasons=(_S15_UNFILLABLE_REASON,)" in src)
    dsrc = (ROOT / "scripts" / "health_check_digest.py").read_text(encoding="utf-8")
    check("Digest verdrahtet", "hc.unfillable_entries_line(" in dsrc and "unfillable_line=unfillable_line" in dsrc)
    _ = fails


def _row(t, *, gap=0.0, rs=0.0, late=False, total=60.0, rvol=1.0, chg=None, spx=None,
         sf=30.0, dtc=5.0, trend="no_data", lz="aus_info_gefuellt", ts="2026-11-17T02:30:00Z"):
    drv = {"rel_volume": rvol, "change_2d": 1.0, "rsi14": 50.0, "short_float": sf,
           "days_to_cover": dtc, "finra_si_trend": trend}
    if chg is not None:
        drv["change"] = chg
        drv["spx_daily_perf"] = spx
    return {"run_ts": ts, "run_phase": "postclose", "ticker": t, "score_total": total,
            "score_raw": total, "score_smoothed": total, "letzte_zeile": lz,
            "sub_scores": {"gap_pts": gap, "rs_spy_pts": rs, "late_runner_active": late,
                           "score_trend_bonus": 0.0, "agent_boost_factor": 1.0},
            "drivers_raw": drv}


def test_score_check_model():
    print("Score-Abgleich: Modell")
    n = 60
    cl = [10.0 + 0.01 * i for i in range(n)]
    spx = [100.0] * (n - 1) + [101.0]   # ^GSPC +1 % an D
    fin = sc.final_inputs(cl, list(cl), [1000.0] * n, spx, lambda c: 50.0)
    check("^GSPC-Tagesbewegung aus endgültigen Kursen", abs(fin["spx_daily"] - 1.0) < 1e-9, fin)
    r = _row("A", gap=fin["gap_pts"], rs=sc.rs_pts(fin["rs"]), rvol=fin["rvol"], chg=5.0, spx=1.0)
    e = sc.evaluate_row(r, fin)
    check("gleiche Eingaben → Δ 0, Modell reproduziert", e["delta"] == 0 and e["modell_reproduziert"], e)
    e2 = sc.evaluate_row(dict(r, drivers_raw=dict(r["drivers_raw"], spx_daily_perf=0.0)), fin)
    check("relative Tagesbewegung: ^GSPC 0 → 1 % senkt Momentum um 14/8 Pkt",
          abs(e2["delta"] - (-14 / 8)) < 0.02 and e2["momentum_geprueft"], e2)
    e3 = sc.evaluate_row(_row("B", gap=fin["gap_pts"], rs=sc.rs_pts(fin["rs"]), rvol=fin["rvol"]), fin)
    check("alte Zeile ohne change/spx → Momentum nicht geprüft, Δ 0",
          e3["delta"] == 0 and not e3["momentum_geprueft"], e3)
    # Kombi: sf≥30, dtc≥5 (2 Bedingungen), gespeichert rvol 1 → final rvol ≥ 2 → 3 → +5
    cl2 = list(cl)
    vol = [1000.0] * (n - 1) + [3000.0]
    fin2 = sc.final_inputs(cl2, list(cl2), vol, spx, lambda c: 50.0)
    r4 = _row("C", gap=fin2["gap_pts"], rs=sc.rs_pts(fin2["rs"]), rvol=1.0, trend="no_data")
    e4 = sc.evaluate_row(r4, fin2)
    exp = sc.rv_component(fin2["rvol"], False) - sc.rv_component(1.0, False) + 5.0
    check("Kombi-Bonus kippt mit rvol", abs(e4["delta"] - round(exp, 2)) < 0.02, (e4, exp))
    s = sc.summarize([dict(e, score_total=69.8, delta=0.3), dict(e, score_total=69.0, delta=1.2),
                      dict(e, delta=0.6)])
    check("Wechsel um 70: mit |Δ|≥0,5 vs. Info",
          s["wechsel70_mit_abw"] == 1 and s["wechsel70_info"] == 1 and s["abw_ab_05"] == 2, s)


def test_score_check_run():
    print("Score-Abgleich: Lauf (Auswahl, Rate-Limit, Blindheit)")
    n = 60
    cl = [10.0 + 0.01 * i for i in range(n)]
    fin = sc.final_inputs(cl, list(cl), [1000.0] * n, [100.0] * n, lambda c: 50.0)
    good = [_row(t, gap=fin["gap_pts"], rs=sc.rs_pts(fin["rs"]), rvol=fin["rvol"], chg=2.0, spx=0.0)
            for t in ("A", "B")]
    old = [dict(_row("Z", lz=None, ts="2026-11-11T01:28:00Z"))]
    pending = [_row("Y", ts="2026-11-18T02:00:00Z")]
    rows = good + old + pending
    calls = []

    def fetch(tickers, d):
        calls.append(d)
        return {t: (cl, list(cl), [1000.0] * n) for t in tickers}, [100.0] * n
    blk, done = sc.run_score_check(rows, date(2026, 11, 16), set(), fetch=fetch, rsi_fn=lambda c: 50.0)
    check("nur Abende mit Fix B und D endgültig", calls == [date(2026, 11, 16)] and done
          == ["2026-11-17T02:30:00Z"], (calls, done))
    check("0 Abweichungen bei identischen Eingaben", blk["abw_ab_05"] == 0 and blk["zeilen"] == 2, blk)
    blk2, done2 = sc.run_score_check(rows, date(2026, 11, 16), set(done), fetch=fetch,
                                     rsi_fn=lambda c: 50.0)
    check("geprüfter Abend wird nicht erneut geprüft", done2 == [] and not blk2["abende"])

    def fetch_rl(tickers, d):
        class YFRateLimitError(Exception):
            pass
        raise YFRateLimitError("Too Many Requests")
    blk3, done3 = sc.run_score_check(rows, date(2026, 11, 16), set(), fetch=fetch_rl)
    check("Rate-Limit → Abbruch, Abend bleibt offen", blk3["rate_limit_abbruch"] and done3 == [])
    src = (ROOT / "scripts" / "score_check.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith(("#", '"', "*", "`")))
    check("Blindheit: keine Ergebnisfelder/-dateien im Code",
          not any(k in code for k in ("return_3d", "return_10d", "max_gain", "outcome_path",
                                      "forward_", "backtest_history", "matured_backtest_export")))
    tsrc = (ROOT / "scripts" / "truth_check.py").read_text(encoding="utf-8")
    check("truth_check: eigener Block + eigener State-Schlüssel",
          '"score_abgleich": score_block' in tsrc and 'new_state["score_abgleich_abende"]' in tsrc)


def test_s16_thresholds():
    print("S16-Schwellen (Easy-Entscheid 14.11.2026)")
    f = hc._s16_score_check_reasons
    check("0 → kein Fail", f({"abw_ab_05": 0, "wechsel70_mit_abw": 0, "wechsel70_info": 3}) == [])
    check("1 Zeile → warn", [s for s, _ in f({"abw_ab_05": 1, "wechsel70_mit_abw": 0})] == ["warn"])
    check("3 Zeilen → crit", [s for s, _ in f({"abw_ab_05": 3, "wechsel70_mit_abw": 0})] == ["crit"])
    check("Wechsel um 70 mit |Δ|≥0,5 → crit",
          [s for s, _ in f({"abw_ab_05": 1, "wechsel70_mit_abw": 1})] == ["crit"])
    check("Modell nicht reproduziert → warn",
          [s for s, _ in f({"abw_ab_05": 0, "modell_nicht_reproduziert": 2})] == ["warn"])
    check("Fehler im Block → warn", [s for s, _ in f({"fehler": "X"})] == ["warn"])
    check("kein Block → nichts", f(None) == [])
    check("Digest-Zusatz nur bei geprüftem Abend",
          hc._score_check_digest_suffix({"abende": []}) == ""
          and "Score-Abgleich 1 Abend" in hc._score_check_digest_suffix(
              {"abende": [{}], "zeilen": 10, "abw_ab_05": 0}))


def test_inflation_log_fields():
    print("score_inflation_log: Eingaben der relativen Tagesbewegung")
    src = (ROOT / "score_inflation_log.py").read_text(encoding="utf-8")
    check("change/spx_daily_perf/letzte_zeile werden geschrieben",
          '"change":                _coerce_float(stock.get("change"))' in src
          and '"spx_daily_perf":        _coerce_float(stock.get("spx_daily_perf"))' in src
          and '"letzte_zeile": stock.get("letzte_zeile")' in src)


def main() -> int:
    for fn in (test_decision, test_wiring, test_backtest_and_s15, test_score_check_model,
               test_score_check_run, test_s16_thresholds, test_inflation_log_fields):
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle Fix-B-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
