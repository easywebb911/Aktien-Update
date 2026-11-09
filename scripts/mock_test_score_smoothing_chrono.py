"""Mock-Test: Score-Glättung chronologisch (Fix 09.11.2026, open_item
``score-smoothing-textsortierung-monatswechsel``).

``apply_score_smoothing`` wählt die „letzten 3 Läufe“ jetzt über das geparste
Datum statt über den TT.MM.JJJJ-Text. Geprüft (ohne Netz, Golden-Harness-Stubs):
  1. ULCC 09.11.2026 (Regression, echte Rohwerte aus score_history.json):
     3-Tage-Schnitt aus 03./04./05.11., Trend fallend → Malus −3 → 62,2
     (nachgerechnet im Test, nicht abgeschrieben); vorher 71,3.
  2. Monatswechsel (Okt → Nov) und Jahreswechsel (Dez 2026 → Jan 2027).
  3. Determinismus: jede Reihenfolge der Einträge in der Datei → gleicher Score.
  4. Unparsbares Datum: Eintrag nicht verwendet, laut geloggt, nie 0.
  5. Trend-Bonus bei chronologisch steigender Folge; < 2 Vorläufe → Rohwert.
"""
from __future__ import annotations

import importlib.util
import itertools
import logging
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "golden_harness", ROOT / "scripts" / "mock_test_outer_page_golden.py")
golden = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(golden)
gr = golden.gr

_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


def expected(raw, past_scores):
    """Unabhängige Nachrechnung der Formel (70 % heute + 30 % Ø der 3
    jüngsten Vorläufe, danach Trend ±3 bei streng monotoner Folge)."""
    if len(past_scores) < 2:
        return raw
    v = round(min(gr.SCORE_TODAY_WEIGHT * raw
                  + gr.SCORE_HISTORY_WEIGHT * sum(past_scores) / len(past_scores), 100.0), 1)
    if len(past_scores) >= gr.SCORE_TREND_DAYS:
        asc = list(reversed(past_scores[:gr.SCORE_TREND_DAYS]))   # alt → neu
        if all(asc[i] < asc[i + 1] for i in range(len(asc) - 1)):
            v = round(min(v + gr.SCORE_TREND_BONUS, 100.0), 1)
        elif all(asc[i] > asc[i + 1] for i in range(len(asc) - 1)):
            v = round(max(v - gr.SCORE_TREND_MALUS, 0.0), 1)
    return v


def run_smoothing(entries, today, raw, ticker="TST"):
    hist = {ticker: [{"date": d, "score": s, "drivers": []} for d, s in entries]}
    orig = (gr._load_score_history, gr._save_score_history)
    gr._load_score_history = lambda: {k: list(v) for k, v in hist.items()}
    gr._save_score_history = lambda h, dirty=True: None
    try:
        stocks = [{"ticker": ticker, "score": raw}]
        gr.apply_score_smoothing(stocks, today)
        return stocks[0]
    finally:
        gr._load_score_history, gr._save_score_history = orig


ULCC = [("27.10.2026", 66.85), ("28.10.2026", 85.5), ("29.10.2026", 91.45),
        ("02.11.2026", 85.82), ("03.11.2026", 85.82), ("04.11.2026", 66.19),
        ("05.11.2026", 60.46), ("09.11.2026", 62.72)]


def test_ulcc_regression():
    s = run_smoothing(ULCC, "09.11.2026", 62.72, "ULCC")
    want = expected(62.72, [60.46, 66.19, 85.82])        # 05.11, 04.11, 03.11
    check("ULCC = Nachrechnung chronologisch", s["score"] == want, (s["score"], want))
    check("ULCC = 62,2", s["score"] == 62.2, s["score"])
    check("ULCC Trend = Malus −3 (nicht Bonus)", s["score_trend_bonus_pts"] == -3.0,
          s["score_trend_bonus_pts"])
    check("ULCC nicht mehr 71,3", s["score"] != 71.3)
    check("score_raw unverändert", s["score_raw"] == 62.72)


def test_month_and_year():
    m = [("28.10.2026", 50.0), ("29.10.2026", 55.0), ("30.10.2026", 60.0),
         ("02.11.2026", 40.0), ("03.11.2026", 45.0)]
    s = run_smoothing(m, "04.11.2026", 70.0)
    check("Monatswechsel: 03.11/02.11/30.10", s["score"] == expected(70.0, [45.0, 40.0, 60.0]),
          s["score"])
    y = [("29.12.2026", 30.0), ("30.12.2026", 35.0), ("31.12.2026", 40.0),
         ("02.01.2027", 80.0)]
    s = run_smoothing(y, "04.01.2027", 50.0)
    want = expected(50.0, [80.0, 40.0, 35.0])            # 02.01.27, 31.12, 30.12
    check("Jahreswechsel: 02.01.27 zählt als jüngster", s["score"] == want, (s["score"], want))
    check("Jahreswechsel: Trend steigend → Bonus", s["score_trend_bonus_pts"] == 3.0,
          s["score_trend_bonus_pts"])


def test_determinism():
    base = [e for e in ULCC if e[0] != "09.11.2026"]
    results = set()
    for perm in itertools.islice(itertools.permutations(base), 0, 5040, 37):
        results.add(run_smoothing(list(perm), "09.11.2026", 62.72)["score"])
    rnd = random.Random(7)
    for _ in range(50):
        sh = base[:]
        rnd.shuffle(sh)
        results.add(run_smoothing(sh, "09.11.2026", 62.72)["score"])
    check("gleiche Historie → gleicher Score (Reihenfolge egal)", results == {62.2}, results)


def test_unparsable():
    msgs = []

    class H(logging.Handler):
        def emit(self, rec):
            msgs.append(rec.getMessage())
    h = H()
    gr.log.addHandler(h)
    try:
        e = [("03.11.2026", 50.0), ("04.11.2026", 55.0), ("kaputt", 0.0), ("31.02.2026", 99.0)]
        s = run_smoothing(e, "05.11.2026", 60.0)
    finally:
        gr.log.removeHandler(h)
    check("unparsbare Einträge nicht verwendet", s["score"] == expected(60.0, [55.0, 50.0]),
          s["score"])
    check("Warnung geloggt", sum("unparsbarem Datum" in m for m in msgs) == 2, msgs)


def test_edge():
    s = run_smoothing([("04.11.2026", 50.0)], "05.11.2026", 60.0)
    check("< 2 Vorläufe → Rohwert", s["score"] == 60.0, s["score"])
    s = run_smoothing([("02.11.2026", 40.0), ("03.11.2026", 50.0), ("04.11.2026", 60.0),
                       ("05.11.2026", 77.0)], "05.11.2026", 77.0)
    check("heutiger Eintrag zählt nicht als Vorlauf",
          s["score"] == expected(77.0, [60.0, 50.0, 40.0]), s["score"])


def test_source_guard():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    i = src.index("def apply_score_smoothing(")
    body = src[i:src.index("# Score-Trend-Bonus/-Malus", i)]
    check("Glättung sortiert nicht mehr nach Datums-Text",
          'key=lambda x: x.get("date", "")' not in body)
    check("Glättung nutzt _parse_de_date", "_parse_de_date(" in body)


def run_all() -> int:
    for t in (test_ulcc_regression, test_month_and_year, test_determinism,
              test_unparsable, test_edge, test_source_guard):
        print(t.__name__)
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Glättungs-Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle Glättungs-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
