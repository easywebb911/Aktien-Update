#!/usr/bin/env python3
"""Tests für scripts/probe_halbzeile_score.py — nur synthetische Daten, kein Netz,
kein pandas (Abruf und RSI injiziert)."""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import probe_halbzeile_score as pr  # noqa: E402

_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {str(detail)[:300]}"))
    if not cond:
        _fails.append(name)


def test_blocks():
    print("Bausteine wie im Lauf")
    check("Gap: kein Gap < 3 % → 0", pr.gap_pts(10.2, 10.0, 10.5) == 0.0)
    check("Gap: strong hold → +5", pr.gap_pts(10.5, 10.0, 10.9) == 5.0)
    check("Gap: weak hold → +2", pr.gap_pts(10.5, 10.0, 10.1) == 2.0)
    check("Gap: fail → −3", pr.gap_pts(10.5, 10.0, 9.9) == -3.0)
    check("Gap: Open fehlt (Halbzeile) → 0", pr.gap_pts(None, 10.0, 10.9) == 0.0)
    check("RS: +7 % → +3, −2,5 % → −2 (round wie im Lauf)",
          pr.rs_pts(7) == 3.0 and pr.rs_pts(-2.5) == -2.0)
    check("Late: RSI 76 → an, 2T +21 % → an, None → aus",
          pr.late_flag(76, None) and pr.late_flag(50, 21.0) and not pr.late_flag(50, None))


def test_pipeline():
    print("Kette score_raw → Glättung → Late-Runner → Boost")
    # ohne Historie, ohne Trend, kein Late, Faktor 1.10
    t = pr.pipeline_total(60.0, 60.0, 0.0, False, 1.10, 0.0, False)
    check("Modell reproduziert ohne Δ", t == 66.0, t)
    t2 = pr.pipeline_total(60.0, 60.0, 0.0, False, 1.10, 5.0, False)
    check("Δraw +5 ohne Historie → +5,5 nach Boost", t2 == 71.5, t2)
    # mit Historie hist=50: smoothed = 0.7*60+0.3*50 = 57.0
    t3 = pr.pipeline_total(60.0, 57.0, 0.0, False, 1.0, 10.0, False)
    check("mit Glättung wirkt Δraw ×0,7", t3 == 64.0, t3)
    t4 = pr.pipeline_total(60.0, 57.0, 0.0, True, 1.0, 0.0, False)
    check("Late-Runner ×0,85", t4 == round(57.0 * 0.85, 1), t4)


def _series(n, last_open=None, last_close=None):
    closes = [10.0 + 0.01 * i for i in range(n)]
    opens = list(closes)
    vols = [1000.0] * n
    if last_close is not None:
        closes[-1] = last_close
    if last_open is not None:
        opens[-1] = last_open
    return closes, opens, vols


def _row(t, *, gap=0.0, rs=0.0, late=False, c2d=1.0, rsi=50.0, total=70.0, raw=70.0,
         sm=70.0, rvol=1.0):
    return {"run_ts": "2026-11-11T01:28:00Z", "run_phase": "postclose", "ticker": t,
            "score_total": total, "score_raw": raw, "score_smoothed": sm,
            "sub_scores": {"gap_pts": gap, "rs_spy_pts": rs, "late_runner_active": late,
                           "score_trend_bonus": 0.0, "agent_boost_factor": 1.0},
            "drivers_raw": {"rel_volume": rvol, "change_2d": c2d, "rsi14": rsi,
                            "short_float": 30.0, "days_to_cover": 5.0}}


def test_evaluate():
    print("Zeile: Kontrolle ~0, Halbzeile mit Gap → Δ")
    spx = [100.0] * 60
    rsi = lambda c: 50.0  # noqa: E731
    cl, op, vo = _series(60)
    fin = pr.final_inputs(cl, op, vo, spx, rsi)
    # gespeicherte Werte passend zu den endgültigen → Δ 0 (Kontrolle)
    row = _row("AAA", gap=fin["gap_pts"], rs=pr.rs_pts(fin["rs"]), c2d=fin["change_2d"],
               rvol=fin["rvol"])
    ev = pr.evaluate_row(row, fin)
    check("Kontrolle: Δ = 0, Modell reproduziert", ev["delta"] == 0 and ev["modell_reproduziert"], ev)
    # Halbzeile: gespeichert gap 0, change_2d None; endgültig strong hold
    cl2, op2, vo2 = _series(60, last_open=10.9, last_close=11.6)
    fin2 = pr.final_inputs(cl2, op2, vo2, spx, rsi)
    row2 = _row("BBB", gap=0.0, rs=pr.rs_pts(fin2["rs"]), c2d=None, rvol=fin2["rvol"])
    ev2 = pr.evaluate_row(row2, fin2)
    check("Halbzeile: Gap +5 → Δ > 0", ev2["d_gap"] == 5.0 and ev2["delta"] > 0, ev2)
    s = pr.summarize([ev, ev2])
    check("Zusammenfassung zählt geänderte Zeilen", s["geaendert"] == 1 and s["zeilen"] == 2, s)


def test_run_and_control():
    print("Lauf mit injiziertem Abruf: Abende, Kontrolle, Blindheit")
    rsi = lambda c: 50.0  # noqa: E731
    cl, op, vo = _series(60)
    fin = pr.final_inputs(cl, op, vo, [100.0] * 60, rsi)
    voll = [dict(_row(t, gap=fin["gap_pts"], rs=pr.rs_pts(fin["rs"]), c2d=fin["change_2d"],
                      rvol=fin["rvol"]), run_ts="2026-11-10T03:47:00Z") for t in ("A", "B")]
    halb = [dict(_row(t, c2d=None, rvol=fin["rvol"]), run_ts="2026-11-11T01:28:00Z") for t in ("C", "D")]
    calls = []

    def fetch(tickers, d):
        calls.append(d)
        return {t: (cl, op, vo) for t in tickers}, [100.0] * 60
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "sil.jsonl"
        p.write_text("".join(json.dumps(r) + "\n" for r in voll + halb + [
            {"run_ts": "x", "run_phase": "premarket", "ticker": "Z"}]), encoding="utf-8")
        res = pr.run(log_path=p, fetch=fetch, rsi_fn=rsi)
    arts = {a["D"]: a["art"] for a in res["abende"]}
    check("D aus ET-Datum: 03:47 UTC = 22:47 ET 09.11., 01:28 UTC = 20:28 ET 10.11.",
          arts == {"2026-11-09": "voll", "2026-11-10": "halb"}, arts)
    check("Premarket ignoriert", all(a["art"] in ("voll", "halb") for a in res["abende"]))
    check("Kontrolle bestanden (voll ~0)", res["kontrolle"]["bestanden"], res["kontrolle"])
    check("Abruf nur bis D (Datum = D)", calls == [date(2026, 11, 9), date(2026, 11, 10)], calls)
    src = (ROOT / "scripts" / "probe_halbzeile_score.py").read_text(encoding="utf-8")
    check("Blindheit: kein Ergebnisfeld/-datei im Quelltext",
          not any(k in src for k in ("return_3d", "return_10d", "max_gain_pct", "outcome_path.jsonl",
                                     "forward_10d", "backtest_history.json",
                                     "matured_backtest_export")))

    def fetch_rl(tickers, d):
        class YFRateLimitError(Exception):
            pass
        raise YFRateLimitError("Too Many Requests")
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "sil.jsonl"
        p.write_text(json.dumps(halb[0]) + "\n", encoding="utf-8")
        try:
            pr.run(log_path=p, fetch=fetch_rl, rsi_fn=rsi)
            ok = False
        except pr.RateLimited:
            ok = True
    check("Rate-Limit → Abbruch ohne Ergebnis", ok)
    wf = (ROOT / ".github" / "workflows" / "probe_halbzeile_score.yml").read_text(encoding="utf-8")
    check("Workflow: nur Hand-Start, nur lesen, kein Push, keine Secrets",
          "workflow_dispatch" in wf and "schedule" not in wf and "contents: read" in wf
          and "git push" not in wf and "secrets." not in wf)


def main() -> int:
    for fn in (test_blocks, test_pipeline, test_evaluate, test_run_and_control):
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle probe_halbzeile_score-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
