#!/usr/bin/env python3
"""Mock-Tests für entry_score.py (Entry-Timing-Score, Shadow-Mode).

PURE — importiert NUR entry_score (stdlib), kein yfinance/requests →
CI-gate-bar (in der Allowlist des run_ci_mock_tests-Runners).

Deckt ab: die 5 Normalisierungen (inkl. Clamps + EXAKTE Bucket-Grenzwerte
−0.8/−0.2/1.0/5.0 mit ≤-Konvention), die Re-Norm-Aggregation (Option B:
fehlende Komponente fällt raus, Gleichgewichtung, 0→None) und die
anomaly-Run-Level-Lesart (Option (c): Map-gefüllt→0, Map-leer→drop).
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import entry_score as E  # noqa: E402

_fails = []


def _eq(name, got, exp):
    ok = got == exp
    print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  got={got} exp={exp}"))
    if not ok:
        _fails.append(name)


# ── 1. anomaly_freshness → ×100 ─────────────────────────────────────────────
def test_anomaly():
    _eq("anomaly 1.0→100",  E.normalize_anomaly_freshness(1.0), 100.0)
    _eq("anomaly 0.5→50",   E.normalize_anomaly_freshness(0.5), 50.0)
    _eq("anomaly 0.0→0",    E.normalize_anomaly_freshness(0.0), 0.0)
    _eq("anomaly 0.9→90",   E.normalize_anomaly_freshness(0.9), 90.0)
    _eq("anomaly None→None", E.normalize_anomaly_freshness(None), None)


# ── 2. score_delta_t1 → (x+15)/30×100, Clamp ────────────────────────────────
def test_score_delta():
    _eq("delta 0→50",      E.normalize_score_delta_t1(0.0), 50.0)
    _eq("delta +15→100",   E.normalize_score_delta_t1(15.0), 100.0)
    _eq("delta -15→0",     E.normalize_score_delta_t1(-15.0), 0.0)
    _eq("delta +7.5→75",   E.normalize_score_delta_t1(7.5), 75.0)
    _eq("delta +30→clamp100", E.normalize_score_delta_t1(30.0), 100.0)   # raw-Range
    _eq("delta -57→clamp0",   E.normalize_score_delta_t1(-57.0), 0.0)    # raw-Range
    _eq("delta None→None", E.normalize_score_delta_t1(None), None)


# ── 3. uoa_atm_ratio → min(x,4)/4×100 (Cap 4.0) ─────────────────────────────
def test_uoa():
    _eq("uoa 4.0→100",     E.normalize_uoa_atm_ratio(4.0), 100.0)
    _eq("uoa 2.0→50",      E.normalize_uoa_atm_ratio(2.0), 50.0)
    _eq("uoa 0.355→8.88",  E.normalize_uoa_atm_ratio(0.355), 8.88)   # echter Median n=87
    _eq("uoa 4.5→clamp100", E.normalize_uoa_atm_ratio(4.5), 100.0)   # echter max, geclippt
    _eq("uoa None→None",   E.normalize_uoa_atm_ratio(None), None)


# ── 4. rvol_buildup_5d → min(x,6)/6×100 (Cap 6.0), Proxy ────────────────────
def test_rvol_buildup():
    _eq("rvol 6.0→100",    E.normalize_rvol_buildup_5d(6.0), 100.0)
    _eq("rvol 3.0→50",     E.normalize_rvol_buildup_5d(3.0), 50.0)
    _eq("rvol 1.475→24.58", E.normalize_rvol_buildup_5d(1.475), 24.58)  # echter Median n=149
    _eq("rvol 153.547→clamp100", E.normalize_rvol_buildup_5d(153.547), 100.0)  # echter max
    _eq("rvol None→None",  E.normalize_rvol_buildup_5d(None), None)


# ── 5. si_trend_5d → 5 Buckets, EXAKTE Grenzwerte (≤-Konvention) ────────────
def test_si_trend_buckets():
    # Grenzwerte fallen in den UNTEREN Bucket:
    _eq("si -0.8 (Grenze)→0",   E.normalize_si_trend_5d(-0.8), 0.0)
    _eq("si -0.2 (Grenze)→25",  E.normalize_si_trend_5d(-0.2), 25.0)
    _eq("si  1.0 (Grenze)→50",  E.normalize_si_trend_5d(1.0), 50.0)
    _eq("si  5.0 (Grenze)→75",  E.normalize_si_trend_5d(5.0), 75.0)
    # knapp jenseits der Grenzen → nächster Bucket:
    _eq("si -0.81→0",   E.normalize_si_trend_5d(-0.81), 0.0)
    _eq("si -0.79→25",  E.normalize_si_trend_5d(-0.79), 25.0)
    _eq("si  5.0001→100", E.normalize_si_trend_5d(5.0001), 100.0)
    # echte Extreme (n=222):
    _eq("si -0.994(min)→0", E.normalize_si_trend_5d(-0.994), 0.0)
    _eq("si 374.0(max)→100", E.normalize_si_trend_5d(374.0), 100.0)
    _eq("si 0.30(median)→50", E.normalize_si_trend_5d(0.30), 50.0)
    _eq("si None→None", E.normalize_si_trend_5d(None), None)


# ── 6. Aggregation: alle 5 vorhanden ────────────────────────────────────────
def test_agg_all_five():
    # anomaly0.5→50, delta0→50, uoa2→50, rvol3→50, si1.0→50 → Schnitt 50, n=5
    sc, comps, n = E.compute_entry_score(0.5, 0.0, 2.0, 3.0, 1.0,
                                         push_history_available=True)
    _eq("agg5 score=50", sc, 50.0)
    _eq("agg5 n=5", n, 5)
    _eq("agg5 anomaly-comp=50", comps["anomaly_freshness"], 50.0)


# ── 7. Re-Norm: 2 fehlende Komponenten → Schnitt über 3 ─────────────────────
def test_agg_two_missing():
    # anomaly None (Map LEER→drop), delta None, uoa2→50, rvol6→100, si5.0→75
    # → incoming [50,100,75] → 75, n=3
    sc, comps, n = E.compute_entry_score(None, None, 2.0, 6.0, 5.0,
                                         push_history_available=False)
    _eq("renorm3 score=75", sc, 75.0)
    _eq("renorm3 n=3", n, 3)
    _eq("renorm3 anomaly dropped", comps["anomaly_freshness"], None)
    _eq("renorm3 delta dropped", comps["score_delta_t1"], None)


# ── 8. 0 Komponenten → None ─────────────────────────────────────────────────
def test_agg_zero_components():
    sc, comps, n = E.compute_entry_score(None, None, None, None, None,
                                         push_history_available=False)
    _eq("zero score=None", sc, None)
    _eq("zero n=0", n, 0)
    _eq("zero alle comps None", all(v is None for v in comps.values()), True)


# ── 9. Option (c): Map GEFÜLLT, Ticker fehlt → anomaly=0 im Schnitt ─────────
def test_c_map_filled_ticker_absent():
    # anomaly None ABER push_history_available=True (Map gefüllt, Ticker nie
    # gepusht) → anomaly = echte 0. delta15→100, Rest None.
    # incoming [0 (anomaly), 100 (delta)] → 50, n=2
    sc, comps, n = E.compute_entry_score(None, 15.0, None, None, None,
                                         push_history_available=True)
    _eq("(c)filled anomaly→0", comps["anomaly_freshness"], 0.0)
    _eq("(c)filled n=2", n, 2)
    _eq("(c)filled score=50", sc, 50.0)


# ── 10. Option (c): Map LEER → anomaly raus, Re-Norm über Rest, Flag=False ──
def test_c_map_empty():
    # anomaly None + push_history_available=False (Daten-Ausfall) → anomaly
    # fällt raus. delta15→100, Rest None → incoming [100] → 100, n=1.
    sc, comps, n = E.compute_entry_score(None, 15.0, None, None, None,
                                         push_history_available=False)
    _eq("(c)empty anomaly dropped", comps["anomaly_freshness"], None)
    _eq("(c)empty n=1", n, 1)
    _eq("(c)empty score=100", sc, 100.0)


# ── 11. Determinismus: gleiche Inputs → gleiches Ergebnis ───────────────────
def test_determinism():
    a = E.compute_entry_score(0.5, 3.0, 1.5, 2.0, 0.5, push_history_available=True)
    b = E.compute_entry_score(0.5, 3.0, 1.5, 2.0, 0.5, push_history_available=True)
    _eq("determ identisch", a, b)


def main() -> int:
    for fn in (test_anomaly, test_score_delta, test_uoa, test_rvol_buildup,
               test_si_trend_buckets, test_agg_all_five, test_agg_two_missing,
               test_agg_zero_components, test_c_map_filled_ticker_absent,
               test_c_map_empty, test_determinism):
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("Alle entry_score-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
