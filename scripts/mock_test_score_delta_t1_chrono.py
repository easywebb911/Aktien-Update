"""Mock-Test: score_delta_t1 / _raw + Entry-Score-Schatten CHRONOLOGISCH
(Fix 11.11.2026, open_item backtest-score-delta-t1-textsortierung).

Echte Kette ohne Netz: ``apply_score_smoothing`` (Score-History gemockt, kein
Schreiben) → ``s["sparkline_view"]`` → ``backtest_history.
_build_backtest_extension`` → ``score_delta_t1`` / ``score_delta_t1_raw`` /
``entry_score``.

Geprüft:
  1. Monatswechsel (Okt → Nov): Δ = heute − jüngster Vorlauf (nicht der
     Text-größte Tag 31.10.).
  2. Jahreswechsel (Dez → Jan).
  3. Regressionsfall HZO 10.08.2026 (unabhängig aus den Git-Ständen von
     score_history.json nachgerechnet): Vorlauf 27.07.2026 = 69,66, heute
     82,28 → +12,6 (gespeichert war −12,6 durch Text-Sortierung).
  4. Gegenprobe: die alte Text-Sortierung (Replik des entfernten Blocks)
     liefert für dieselben Daten −12,6 — der Test unterscheidet alt/neu.
  5. Determinismus: jede Reihenfolge der History-Einträge → gleiche Werte.
  6. Cap ±15 und Entry-Score folgen dem chronologischen Wert.
  7. Kein Score-Effekt: ``s["score"]`` unabhängig von der Kurve.
"""
from __future__ import annotations

import importlib.util
import itertools
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Netzfreie Stubs (yfinance/bs4/…) wie im Golden-Harness; liefert ``gr``.
_spec = importlib.util.spec_from_file_location(
    "golden_harness", ROOT / "scripts" / "mock_test_outer_page_golden.py")
golden = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(golden)
gr = golden.gr

import backtest_history as bh  # noqa: E402
import entry_score as es  # noqa: E402

_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


def E(d, sc):
    return {"date": d, "score": sc, "drivers": []}


def _run(ticker, history_entries, today, today_raw):
    """apply_score_smoothing mit gemockter History → Backtest-Extension."""
    hist = {ticker: [dict(e) for e in history_entries]}
    orig = (gr._load_score_history, gr._save_score_history)
    gr._load_score_history = lambda: hist
    gr._save_score_history = lambda h, dirty=True: None
    try:
        s = {"ticker": ticker, "score": today_raw}
        gr.apply_score_smoothing([s], today)
    finally:
        gr._load_score_history, gr._save_score_history = orig
    s.update({"price": 10.0, "short_float": 25.0, "short_ratio": 5.0,
              "rel_volume": 2.0, "rel_volume_yesterday": 1.0, "change": 1.0,
              "float_shares": 1e8, "avg_vol_20d": 1e6, "hist_5d": [],
              "agent_boost_factor": 1.0, "finra_bonus_pts": 0.0,
              "short_float_source": "yfinance",
              "finra_data": {"trend": "no_data", "history": [],
                             "si_trend_source": "finra"}})
    ext = bh._build_backtest_extension(
        s, pool_position=1, pool_size=20, agent_signals={},
        compute_sub_scores_fn=lambda _s: {"struct": 0, "catalyst": 0, "timing": 0},
        safe_float_fn=lambda v, d=0.0: float(v) if v not in (None, "") else d,
        latest_push_ts_by_ticker={}, now_dt=None)
    return s, ext


def _old_text_sorted_delta(entries, today, today_raw):
    """Replik des ENTFERNTEN Blocks (Text-Sortierung TT.MM.JJJJ) — nur Gegenprobe."""
    es_ = [e for e in entries if e["date"] != today] + [E(today, today_raw)]
    last7 = sorted(es_, key=lambda x: x.get("date", ""))[-7:]
    sc = [round(e["score"], 1) for e in last7]
    return round(sc[-1] - sc[-2], 2) if len(sc) >= 2 else None


MONTH = [E("27.10.2026", 66.85), E("28.10.2026", 85.5), E("29.10.2026", 91.45),
         E("30.10.2026", 70.0), E("31.10.2026", 72.0), E("02.11.2026", 85.82),
         E("03.11.2026", 80.0)]
YEAR = [E("28.12.2026", 40.0), E("29.12.2026", 45.0), E("30.12.2026", 50.0),
        E("31.12.2026", 57.0)]
HZO = [E("27.07.2026", 69.66)]


def test_month():
    s, ext = _run("ULCC", MONTH, "04.11.2026", 66.19)
    check("Monatswechsel: raw = heute − 03.11. (66,2 − 80,0)",
          ext["score_delta_t1_raw"] == -13.8, ext["score_delta_t1_raw"])
    check("Monatswechsel: Kurve endet heute (ISO)",
          s["sparkline_view"]["dates"][-1] == "2026-11-04", s["sparkline_view"]["dates"])
    # Text-Sortierung: 02.11. < 03.11. < 04.11. < 27.10. … < 31.10. → [-1]=31.10., [-2]=30.10.
    check("Gegenprobe: alte Text-Sortierung = 31.10. − 30.10. = +2,0",
          _old_text_sorted_delta(MONTH, "04.11.2026", 66.19) == 2.0)


def test_year():
    _s, ext = _run("AAAA", YEAR, "04.01.2027", 60.0)
    check("Jahreswechsel: raw = 60,0 − 57,0", ext["score_delta_t1_raw"] == 3.0,
          ext["score_delta_t1_raw"])
    # Text-Sortierung: 04.01.2027 < 28.12. … < 31.12. → 31.12. − 30.12. = +7,0
    check("Gegenprobe: alte Text-Sortierung = +7,0",
          _old_text_sorted_delta(YEAR, "04.01.2027", 60.0) == 7.0)


def test_hzo_regression():
    s, ext = _run("HZO", HZO, "10.08.2026", 82.28)
    check("HZO 10.08.: score_delta_t1_raw = +12,6", ext["score_delta_t1_raw"] == 12.6,
          ext["score_delta_t1_raw"])
    check("HZO 10.08.: score_delta_t1 = +12,6 (unter Cap)", ext["score_delta_t1"] == 12.6,
          ext["score_delta_t1"])
    check("HZO Gegenprobe: alte Text-Sortierung = −12,6 (gespeicherter Wert)",
          _old_text_sorted_delta(HZO, "10.08.2026", 82.28) == -12.6)
    exp, _c, _n = es.compute_entry_score(None, 12.6, None, None, None,
                                         push_history_available=False)
    check("HZO: Entry-Score aus dem chronologischen Δ", ext["entry_score"] == exp,
          (ext["entry_score"], exp))
    check("kein Score-Effekt (1 Vorlauf → keine Glättung)", s["score"] == 82.28, s["score"])


def test_cap():
    _s, ext = _run("CAPX", [E("30.10.2026", 40.0), E("31.10.2026", 90.0)], "02.11.2026", 70.0)
    check("Cap: raw −20,0, gecappt −15,0",
          ext["score_delta_t1_raw"] == -20.0 and ext["score_delta_t1"] == -15.0,
          (ext["score_delta_t1_raw"], ext["score_delta_t1"]))


def test_determinism():
    rnd = random.Random(42)
    ref = _run("ULCC", MONTH, "04.11.2026", 66.19)[1]
    keys = ("score_delta_t1", "score_delta_t1_raw", "entry_score")
    ok = True
    perms = list(itertools.islice(itertools.permutations(MONTH), 50))
    for _ in range(50):
        p = MONTH[:]
        rnd.shuffle(p)
        perms.append(p)
    for p in perms:
        ext = _run("ULCC", list(p), "04.11.2026", 66.19)[1]
        if any(ext[k] != ref[k] for k in keys):
            ok = False
            break
    check(f"Determinismus ({len(perms)} Reihenfolgen)", ok)


def run_all() -> int:
    for t in (test_month, test_year, test_hzo_regression, test_cap, test_determinism):
        print(t.__name__)
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle score_delta_t1-Chrono-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
