#!/usr/bin/env python3
"""Mock-Test: §4-Sensitivitätsprüfung (scripts/s4_sensitivity_eval.py).

Nur synthetische Populationen, festes "now", kein Real-State, kein Netz.

  01 Leere Ausschlussliste → identisch zur eingefrorenen Hauptfunktion
     (gleiche Verdikte, gleiche Kennzahlen) — Gleichheits-Gegenprobe.
  02 Records an eingefrorenen Ausschluss-Tagen werden entfernt, alle
     anderen bleiben (auch score<70/backfill, die filtert erst freeze_eval).
  03 K1-Zählung: nur Postclose-Läufe (ET >= 16:00), nur Close-leer am
     Entry-Tag, verschiedene Ticker; Schwelle 20.
  04 Tage nach FROZEN_UNTIL: K1 entscheidet; zu alt → NichtPruefbar.
  05 Entscheidungsregel (wörtlich aus dem Protokolleintrag).
  06 Kein Schreibzugriff ohne --write; freeze_eval.py unverändert genutzt.
"""
from __future__ import annotations

import pathlib
import random
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import freeze_eval as fe  # noqa: E402
import s4_sensitivity_eval as s4  # noqa: E402

_fails: list[str] = []
NOW = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)


def _check(name, cond, debug=None):
    print(("  OK  " if cond else "  FAIL ") + name
          + ("" if cond or debug is None else f"  (debug: {debug!r})"))
    if not cond:
        _fails.append(name)


def _rows(n, *, seed, dates, offset_5=4.0, offset_10=1.0, offset_3=2.5):
    rng = random.Random(seed)
    regimes = ("bull", "bear", "neutral")
    out = []
    for i in range(n):
        out.append({
            "ticker": f"T{i}", "date": dates[i % len(dates)], "score": 80.0,
            "provenance": "forward",
            "return_5d": offset_5 + rng.gauss(0, 1.0),
            "return_10d": offset_10 + rng.gauss(0, 1.0),
            "return_3d": offset_3 + rng.gauss(0, 1.0),
            "market_regime": regimes[i % 3],
        })
    return out


def _strip(res):
    return {k: {kk: vv for kk, vv in v.items()} for k, v in res["tests"].items()}


def test_01_empty_exclusion_equals_main():
    rows = _rows(120, seed=7, dates=["15.10.2026", "16.10.2026"])  # nicht ausgeschlossen
    orig = s4.EXCLUDED_DAYS_FROZEN
    try:
        s4.EXCLUDED_DAYS_FROZEN = frozenset()
        sens = s4.run_sensitivity(rows, gap_rows=[], now=NOW)
    finally:
        s4.EXCLUDED_DAYS_FROZEN = orig
    main = fe.evaluate_exit_b1_family(rows, now=NOW)
    _check("01 leere Liste → Tests identisch zur Hauptfunktion",
           _strip(sens) == _strip(main))
    _check("01 n_rows_kept == n_rows_in", sens["sensitivity"]["n_rows_kept"] == 120)
    # Auch mit der echten Liste identisch, wenn kein Record an einem Ausschluss-Tag liegt
    sens2 = s4.run_sensitivity(rows, gap_rows=[], now=NOW)
    _check("01 echte Liste, keine Treffer → identisch", _strip(sens2) == _strip(main))


def test_02_frozen_days_removed():
    rows = [{"date": "13.10.2026", "ticker": "A"}, {"date": "14.10.2026", "ticker": "B"},
            {"date": "01.09.2026", "ticker": "C", "score": 50},
            {"date": "21.07.2026", "ticker": "D", "provenance": "backfill"}]
    ex = s4.excluded_days_for({"2026-10-13", "2026-10-14", "2026-09-01", "2026-07-21"}, [], NOW)
    _check("02 Ausschlussmenge = {13.10., 01.09.}", ex == {"2026-10-13", "2026-09-01"}, ex)
    kept = s4.filter_population(rows, ex)
    _check("02 nur B und D bleiben", [r["ticker"] for r in kept] == ["B", "D"])
    _check("02 eingefrorene Liste hat 22 Tage", len(s4.EXCLUDED_DAYS_FROZEN) == 22)


def _gap(run_ts, ticker, day, cells=("High", "Low", "Close"), reason="nonfinite_cell"):
    return {"run_ts": run_ts, "ticker": ticker, "reason": reason,
            "dropped_day": f"{day} 00:00:00", "missing_cells": list(cells)}


def test_03_k1_counting():
    g = [_gap("2026-11-03T00:40:00Z", f"X{i}", "2026-11-02") for i in range(25)]
    g += [_gap("2026-11-03T00:40:00Z", "X1", "2026-11-02")]             # Duplikat
    g += [_gap("2026-11-02T13:00:00Z", f"P{i}", "2026-11-02") for i in range(30)]  # premarket
    g += [_gap("2026-11-04T00:40:00Z", f"V{i}", "2026-11-03", cells=("Volume",)) for i in range(30)]
    g += [_gap("2026-11-04T00:40:00Z", f"O{i}", "2026-10-30") for i in range(30)]  # anderer Tag
    c = s4.k1_affected_days(g)
    _check("03 Postclose 02.11.: 25 verschiedene Ticker", c.get("2026-11-02") == 25, c)
    _check("03 Volume-only und fremde Tage zählen nicht", "2026-11-03" not in c, c)


def test_04_after_frozen():
    now = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)
    g = [_gap("2026-11-03T00:40:00Z", f"X{i}", "2026-11-02") for i in range(20)]
    g += [_gap("2026-11-04T00:40:00Z", f"Y{i}", "2026-11-03") for i in range(19)]
    ex = s4.excluded_days_for({"2026-11-02", "2026-11-03"}, g, now)
    _check("04 K1 ≥20 → 02.11. ausgeschlossen, 19 → 03.11. nicht", ex == {"2026-11-02"}, ex)
    try:
        s4.excluded_days_for({"2026-11-02"}, g, datetime(2026, 12, 20, tzinfo=timezone.utc))
        _check("04 zu alter Tag → NichtPruefbar", False)
    except s4.NichtPruefbar:
        _check("04 zu alter Tag → NichtPruefbar", True)
    try:
        s4.excluded_days_for({"2026-11-02"}, None, now)
        _check("04 Gap-Log fehlt → NichtPruefbar", False)
    except s4.NichtPruefbar:
        _check("04 Gap-Log fehlt → NichtPruefbar", True)


def test_05_decision_rule():
    """Alle 9 Kombinationen (Haupt × Sensitivität) mit erwartetem Gesamturteil
    (Nachschärfung 02.11.2026: Sensitivität "bedingt" zählt als robust)."""
    expected = {
        ("Beleg", "Beleg"): "belegt",
        ("Beleg", "bedingt"): "belegt",
        ("Beleg", "Unklar"): "belegt, aber nicht robust",
        ("bedingt", "Beleg"): "nicht belegt",
        ("bedingt", "bedingt"): "nicht belegt",
        ("bedingt", "Unklar"): "nicht belegt",
        ("Unklar", "Beleg"): "nicht belegt",
        ("Unklar", "bedingt"): "nicht belegt",
        ("Unklar", "Unklar"): "nicht belegt",
    }
    for (m, sv), exp in expected.items():
        got = s4.combine_verdict(m, sv)
        _check(f"05 Haupt {m} + Sens {sv} → {exp}", got == exp, got)


def test_06_no_write_by_default():
    src = (ROOT / "scripts" / "s4_sensitivity_eval.py").read_text(encoding="utf-8")
    _check("06 Schreiben nur hinter --write", "if args.write:" in src
           and src.count("_append_results(") == 1)
    _check("06 schreibt nie eval_results.jsonl",
           'SENS_RESULTS_FILE = "eval_results_sensitivity.jsonl"' in src
           and "_append_results(str(ROOT / SENS_RESULTS_FILE)" in src)
    _check("06 nutzt eingefrorene Funktion", "fe.evaluate_exit_b1_family(kept, now=now)" in src)


def main() -> int:
    for t in (test_01_empty_exclusion_equals_main, test_02_frozen_days_removed,
              test_03_k1_counting, test_04_after_frozen, test_05_decision_rule,
              test_06_no_write_by_default):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            _check(f"{t.__name__} ohne Exception", False, f"{type(exc).__name__}: {exc}")
    print()
    if _fails:
        print(f"{len(_fails)} FAIL")
        return 1
    print("Alle s4_sensitivity_eval-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
