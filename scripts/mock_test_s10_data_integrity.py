"""Mock-Tests fuer S10 Daten-Integritaets-Check (health_check.py).

Phase 1, minimaler erster Wurf:
- MUSS-Felder: rvol_buildup_5d, vol_stability_5d, coiled_spring_score,
  si_trend_5d_slope (alle warn_pct=30, crit_pct=70)
- LAG-Felder: return_3d (lag=3), return_5d (lag=5)
- Wochenend-Filter: weekday() >= 5 ausgeklammert
- Auto-Detect: unbekannte Felder → WARN

Tests decken alle in der Auftrag-Spec genannten Pfade ab:
  100%-null → CRIT       50% → WARN        30% → WARN         5% → OK
  LAG aged null → WARN   Wochenend-Filter  Auto-Detect WARN   is-None-vs-0.0
  (0.0-Werte sind NICHT null und duerfen den Check nicht ausloesen)

Ausfuehrung: ``python3 scripts/mock_test_s10_data_integrity.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from datetime import date


ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import health_check as hc                # noqa: E402
from config import (                      # noqa: E402
    S10_MUSS_FIELDS, S10_LAG_FIELDS, S10_WINDOW_SIZE,
    S10_MUSS_MIN_N, S10_LAG_MIN_AGED_N,
)


# ── Fixture-Helper ─────────────────────────────────────────────────────────


def _baseline_entry(date_str: str, ticker: str = "AAA") -> dict:
    """Vollstaendiger V4-Eintrag mit allen Pflicht-Feldern gefuellt.
    Trend-Felder default = numerischer Wert (0.5/0.05/50.0/0.1)."""
    return {
        "date":              date_str,
        "ticker":            ticker,
        "score":             80.0,
        "entry_price":       10.0,
        "entry_price_t1":    None,
        "short_float":       25.0,
        "dtc":               5.0,
        "rvol":              2.0,
        "si_trend":          "up",
        "si_trend_source":   "finra",
        "short_float_source": "yfinance",
        "backtest_schema_version": 4,
        # V4-Setup-Snapshot
        "score_struct":      40.0,
        "score_catalyst":    5.0,
        "score_timing":      35.0,
        "score_raw":         80.0,
        "combo_bonus":       0.0,        # legitim 0
        "finra_bonus":       0.0,        # legitim 0
        "agent_boost_factor": 1.0,
        "perfect_storm_mult": 1.0,
        "score_trend_bonus": 0.0,        # legitim 0
        "pool_member":       True,
        "pool_position":     1,
        "pool_size":         20,
        "market_regime":     "bull",
        "vix_level":         16.5,
        "max_drawdown_pct":  0.0,
        # Trend-Felder (MUSS)
        "rvol_buildup_5d":    1.2,
        "vol_stability_5d":   0.05,
        "coiled_spring_score": 50.0,
        "si_trend_5d_slope":  0.10,
        # LAG-Felder — fuer Baseline-Fixture gefuellt (entries sind
        # weit in der Vergangenheit, sollten in echten Daten Outcomes
        # haben). Tests die LAG-Pfade pruefen, setzen sie selbst auf None.
        "return_3d":         2.5,
        "return_3d_t1":      None,    # OBSERVED, kein LAG-Check
        "return_5d":         4.0,
        "return_5d_t1":      None,    # OBSERVED
        "return_10d":        None,    # OBSERVED (Phase-2-LAG)
        "return_10d_t1":     None,    # OBSERVED
    }


def _write_fixture(entries: list[dict]) -> str:
    fh = tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                     delete=False, encoding="utf-8")
    json.dump(entries, fh)
    fh.close()
    return fh.name


def _make_v4_dates(n: int, start: date = date(2026, 5, 1)) -> list[str]:
    """N Werktag-Dates (Mo-Fr), formatiert DD.MM.YYYY."""
    out: list[str] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.strftime("%d.%m.%Y"))
        d = date.fromordinal(d.toordinal() + 1)
    return out


TODAY = date(2026, 5, 21)


# ── Tests ─────────────────────────────────────────────────────────────────


def test_01_baseline_all_filled_no_fails():
    """Baseline-Fixture: alle Felder gefuellt → 0 S10-Fails."""
    dates = _make_v4_dates(20)
    entries = [_baseline_entry(d) for d in dates]
    path = _write_fixture(entries)
    try:
        fails = hc.evaluate_s10_data_integrity(bh_path=path, today=TODAY)
    finally:
        pathlib.Path(path).unlink()
    assert fails == [], f"erwartet 0 Fails, bekam: {fails}"


def test_02_muss_100pct_null_is_crit():
    """Wenn ALLE 20 Eintraege rvol_buildup_5d=None → CRIT (hist_5d-Bug-
    Klasse, der Hauptzweck dieses Checks)."""
    dates = _make_v4_dates(20)
    entries = []
    for d in dates:
        e = _baseline_entry(d)
        e["rvol_buildup_5d"] = None
        entries.append(e)
    path = _write_fixture(entries)
    try:
        fails = hc.evaluate_s10_data_integrity(bh_path=path, today=TODAY)
    finally:
        pathlib.Path(path).unlink()
    relevant = [f for f in fails
                if "rvol_buildup_5d" in f.get("detail", "")]
    assert len(relevant) == 1, f"erwartet 1 Fail fuer rvol_buildup_5d, bekam: {fails}"
    assert relevant[0]["severity"] == "crit", \
        f"erwartet crit fuer 100% null, bekam: {relevant[0]}"


def test_03_muss_50pct_null_is_warn():
    """50 % null (10 von 20) → WARN (zwischen warn_pct=30 und crit_pct=70)."""
    dates = _make_v4_dates(20)
    entries = []
    for i, d in enumerate(dates):
        e = _baseline_entry(d)
        if i < 10:
            e["coiled_spring_score"] = None
        entries.append(e)
    path = _write_fixture(entries)
    try:
        fails = hc.evaluate_s10_data_integrity(bh_path=path, today=TODAY)
    finally:
        pathlib.Path(path).unlink()
    relevant = [f for f in fails
                if "coiled_spring_score" in f.get("detail", "")]
    assert len(relevant) == 1
    assert relevant[0]["severity"] == "warn", \
        f"erwartet warn bei 50%, bekam: {relevant[0]}"


def test_04_muss_30pct_null_at_threshold_warn():
    """Exakt warn_pct (30 %) sollte WARN auslösen (>= statt >)."""
    dates = _make_v4_dates(20)
    entries = []
    for i, d in enumerate(dates):
        e = _baseline_entry(d)
        if i < 6:  # 6/20 = 30%
            e["vol_stability_5d"] = None
        entries.append(e)
    path = _write_fixture(entries)
    try:
        fails = hc.evaluate_s10_data_integrity(bh_path=path, today=TODAY)
    finally:
        pathlib.Path(path).unlink()
    relevant = [f for f in fails if "vol_stability_5d" in f.get("detail", "")]
    assert len(relevant) == 1
    assert relevant[0]["severity"] == "warn"


def test_05_muss_5pct_null_below_threshold_ok():
    """5 % null (1 von 20) → OK (unter warn_pct=30)."""
    dates = _make_v4_dates(20)
    entries = []
    for i, d in enumerate(dates):
        e = _baseline_entry(d)
        if i == 0:
            e["si_trend_5d_slope"] = None
        entries.append(e)
    path = _write_fixture(entries)
    try:
        fails = hc.evaluate_s10_data_integrity(bh_path=path, today=TODAY)
    finally:
        pathlib.Path(path).unlink()
    relevant = [f for f in fails if "si_trend_5d_slope" in f.get("detail", "")]
    assert relevant == [], f"erwartet OK bei 5% null, bekam: {relevant}"


def test_06_muss_zero_float_is_NOT_null():
    """0.0 ist legitimer numerischer Wert — darf NICHT als null zaehlen.
    Sonst false-positive bei score_trend_bonus=0.0 (95% der Faelle) etc."""
    dates = _make_v4_dates(20)
    entries = []
    for d in dates:
        e = _baseline_entry(d)
        e["coiled_spring_score"] = 0.0   # legitimer Score-Wert
        entries.append(e)
    path = _write_fixture(entries)
    try:
        fails = hc.evaluate_s10_data_integrity(bh_path=path, today=TODAY)
    finally:
        pathlib.Path(path).unlink()
    relevant = [f for f in fails if "coiled_spring_score" in f.get("detail", "")]
    assert relevant == [], \
        ("0.0 darf NICHT als null gewertet werden — sonst false-positive bei "
         f"legitim-0-Feldern. Bekam: {relevant}")


def test_07_muss_below_min_n_skipped():
    """Weniger als min_n=5 Eintraege → Check skipt, kein Fail."""
    dates = _make_v4_dates(3)
    entries = []
    for d in dates:
        e = _baseline_entry(d)
        e["rvol_buildup_5d"] = None
        entries.append(e)
    path = _write_fixture(entries)
    try:
        fails = hc.evaluate_s10_data_integrity(bh_path=path, today=TODAY)
    finally:
        pathlib.Path(path).unlink()
    relevant = [f for f in fails if "rvol_buildup_5d" in f.get("detail", "")]
    assert relevant == [], f"Bei n < min_n soll skippen, bekam: {relevant}"


def test_08_lag_aged_null_is_warn():
    """LAG-Pfad: return_3d-null bei Eintraegen ≥3 Trading-Tage alt → WARN.
    Nicht CRIT (LAG ist nie crit)."""
    # 15 alte Eintraege (sehr lange zurueck — 30+ Trading-Tage), alle ohne r3d
    old_dates = _make_v4_dates(15, start=date(2026, 4, 1))
    entries = []
    for d in old_dates:
        e = _baseline_entry(d)
        e["return_3d"] = None   # Override Baseline-Default
        entries.append(e)
    path = _write_fixture(entries)
    try:
        fails = hc.evaluate_s10_data_integrity(bh_path=path, today=TODAY)
    finally:
        pathlib.Path(path).unlink()
    relevant = [f for f in fails if "return_3d" in f.get("detail", "")]
    assert len(relevant) == 1, f"erwartet 1 LAG-Fail fuer return_3d, bekam: {fails}"
    assert relevant[0]["severity"] == "warn", \
        f"LAG ist NIE crit, bekam: {relevant[0]['severity']}"


def test_09_lag_recent_entries_not_aged_skip():
    """Wenn ALLE Eintraege juenger als lag → kein LAG-Fail (zu frueh)."""
    # 15 frische Eintraege (heute - 1 Tag), unter lag=3 fuer return_3d
    one_day_ago_dates = _make_v4_dates(15, start=date(2026, 5, 19))
    entries = [_baseline_entry(d) for d in one_day_ago_dates]
    path = _write_fixture(entries)
    try:
        fails = hc.evaluate_s10_data_integrity(bh_path=path, today=TODAY)
    finally:
        pathlib.Path(path).unlink()
    relevant = [f for f in fails if "return_3d" in f.get("detail", "")]
    # Today=21.05., entries from 19.05./20.05. Beide haben 2 bzw 1
    # Trading-Tage Lag — unter lag=3 → aged-Liste leer → skip.
    assert relevant == [], \
        f"Frische Eintraege (lag<3) sollen LAG-Pfad skippen, bekam: {relevant}"


def test_10_lag_below_min_aged_n_skipped():
    """Auch wenn alle aged-null sind: unter S10_LAG_MIN_AGED_N=10 → skip."""
    # 5 alte Eintraege ohne r3d (n=5 < min=10)
    old_dates = _make_v4_dates(5, start=date(2026, 4, 1))
    entries = []
    for d in old_dates:
        e = _baseline_entry(d)
        e["return_3d"] = None
        entries.append(e)
    path = _write_fixture(entries)
    try:
        fails = hc.evaluate_s10_data_integrity(bh_path=path, today=TODAY)
    finally:
        pathlib.Path(path).unlink()
    relevant = [f for f in fails if "return_3d" in f.get("detail", "")]
    assert relevant == [], \
        f"Aged-N unter min_aged_n soll skippen, bekam: {relevant}"


def test_11_weekend_filter_excludes_saturday_sunday():
    """Wochenend-Eintraege (date.weekday() >= 5) werden ausgefiltert —
    sonst false-positive durch die 96 Bestands-Wochenend-Leichen."""
    # 10 Werktag-Eintraege (alle Felder gefuellt) + 10 Wochenend-Eintraege
    # (alle Trend-Felder null = simuliert Bestands-Leichen).
    weekday_dates = _make_v4_dates(10)
    weekend_dates = [
        "16.05.2026", "17.05.2026",
        "09.05.2026", "10.05.2026",
        "02.05.2026", "03.05.2026",
        "25.04.2026", "26.04.2026",
        "18.04.2026", "19.04.2026",
    ]
    entries = [_baseline_entry(d) for d in weekday_dates]
    for d in weekend_dates:
        e = _baseline_entry(d)
        # Wochenend-Leichen wie in echten Daten: alle return_*_d null
        e["return_3d"] = None
        e["return_5d"] = None
        entries.append(e)
    path = _write_fixture(entries)
    try:
        v4 = hc._s10_load_v4_entries(bh_path=path)
        fails = hc.evaluate_s10_data_integrity(bh_path=path, today=TODAY)
    finally:
        pathlib.Path(path).unlink()
    assert len(v4) == 10, \
        f"Wochenend-Filter soll 10 Wochenend-Leichen ausklammern, "\
        f"v4-Pool hat {len(v4)} (erwartet 10)"
    # Da Wochenend-Eintraege weg sind, sollte kein r3d-LAG-Fail kommen
    relevant = [f for f in fails if "return_3d" in f.get("detail", "")]
    assert relevant == [], \
        f"Wochenend-Filter sollte LAG-False-Positive verhindern, bekam: {relevant}"


def test_12_auto_detect_unknown_field_warn():
    """Unbekanntes Feld in V4-Eintrag → WARN-Auto-Detect."""
    dates = _make_v4_dates(20)
    entries = []
    for d in dates:
        e = _baseline_entry(d)
        e["some_brand_new_field"] = "value"   # nicht in MUSS/LAG/OBSERVED
        entries.append(e)
    path = _write_fixture(entries)
    try:
        fails = hc.evaluate_s10_data_integrity(bh_path=path, today=TODAY)
    finally:
        pathlib.Path(path).unlink()
    auto_detect = [f for f in fails
                    if "Unklassifizierte" in f.get("detail", "")]
    assert len(auto_detect) == 1, \
        f"erwartet 1 Auto-Detect-WARN, bekam: {fails}"
    assert auto_detect[0]["severity"] == "warn"
    assert "some_brand_new_field" in auto_detect[0]["detail"]


def test_13_auto_detect_known_observed_no_warn():
    """Ein OBSERVED-Feld (z.B. return_10d) darf KEINEN Auto-Detect-WARN
    auslösen, auch wenn es 100% null ist."""
    dates = _make_v4_dates(20)
    entries = []
    for d in dates:
        e = _baseline_entry(d)
        # return_10d ist OBSERVED, nicht MUSS, nicht LAG → 100% null OK
        e["return_10d"] = None
        entries.append(e)
    path = _write_fixture(entries)
    try:
        fails = hc.evaluate_s10_data_integrity(bh_path=path, today=TODAY)
    finally:
        pathlib.Path(path).unlink()
    relevant = [f for f in fails if "return_10d" in f.get("detail", "")]
    assert relevant == [], \
        f"OBSERVED-Feld darf kein S10-Fail werfen, bekam: {relevant}"


def test_14_evaluate_state_invariants_runs_s10():
    """Integration: evaluate_state_invariants ruft S10 auf und propagiert
    Fails ins normale fails-Schema (id=S10)."""
    dates = _make_v4_dates(20)
    entries = []
    for d in dates:
        e = _baseline_entry(d)
        e["coiled_spring_score"] = None   # CRIT-Trigger
        entries.append(e)
    path = _write_fixture(entries)
    try:
        # Monkey-Patch evaluate_s10_data_integrity-Default-Pfad via wrapper
        import unittest.mock as mock
        orig = hc.evaluate_s10_data_integrity
        def patched(**kw):
            kw["bh_path"] = path
            kw.setdefault("today", TODAY)
            return orig(**kw)
        with mock.patch.object(hc, "evaluate_s10_data_integrity", patched):
            fails = hc.evaluate_state_invariants(
                top10_tickers=[f"T{i}" for i in range(10)],
                setup_scores={f"T{i}": 50.0 for i in range(10)},
                monster_scores={f"T{i}": 50.0 for i in range(10)},
                score_history={f"T{i}": [["21.05.2026", 50.0]] for i in range(10)},
                today_iso="2026-05-21",
                agent_signal_keys={f"T{i}" for i in range(10)},
                n_inflation_lines=20,
                n_backtest_appended=0,
                backtest_has_today=True,
                run_phase="postclose",
            )
    finally:
        pathlib.Path(path).unlink()
    s10_fails = [f for f in fails if f.get("id") == "S10"]
    assert s10_fails, f"S10-Fails sollten in fails-Liste auftauchen, bekam: {fails}"
    assert any(f["severity"] == "crit" for f in s10_fails)


def test_15_evaluate_state_invariants_ki_agent_only_skips_s10():
    """ki_agent_only=True überspringt S10 (KI-Tick rendert keine
    Backtest-Daten neu)."""
    import unittest.mock as mock
    # Spy auf S10
    called = []
    def spy(*a, **kw):
        called.append(True)
        return []
    with mock.patch.object(hc, "evaluate_s10_data_integrity", spy):
        hc.evaluate_state_invariants(
            setup_scores={f"T{i}": 50.0 for i in range(10)},
            monster_scores={f"T{i}": 50.0 for i in range(10)},
            ki_agent_only=True,
        )
    assert called == [], "S10 darf bei ki_agent_only=True nicht laufen"


def test_16_check_self_failure_is_warn_not_crit():
    """Wenn der S10-Check selbst crasht → WARN, nicht CRIT (fail-soft)."""
    import unittest.mock as mock
    def boom(**kw):
        raise RuntimeError("synthetic-s10-bug")
    with mock.patch.object(hc, "evaluate_s10_data_integrity", boom):
        fails = hc.evaluate_state_invariants(
            setup_scores={f"T{i}": 50.0 for i in range(10)},
            monster_scores={f"T{i}": 50.0 for i in range(10)},
            ki_agent_only=False,
        )
    s10_fails = [f for f in fails if f.get("id") == "S10"]
    assert len(s10_fails) == 1
    assert s10_fails[0]["severity"] == "warn", \
        f"S10-Check-Selbst-Fail muss WARN sein (kein crit, kein Push-Block), bekam: {s10_fails[0]}"
    assert "synthetic-s10-bug" in s10_fails[0]["detail"]


def test_17_missing_backtest_file_no_crash():
    """Fehlende backtest_history.json → S10 returnt [], kein Crash."""
    fails = hc.evaluate_s10_data_integrity(
        bh_path="/nonexistent/path/backtest_history.json", today=TODAY,
    )
    assert fails == [], f"Bei fehlender Datei: kein Fail erwarten, bekam: {fails}"


def test_18_corrupt_json_no_crash():
    """Kaputtes JSON → S10 returnt [], kein Crash."""
    fh = tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                     delete=False, encoding="utf-8")
    fh.write("not-json{")
    fh.close()
    try:
        fails = hc.evaluate_s10_data_integrity(bh_path=fh.name, today=TODAY)
    finally:
        pathlib.Path(fh.name).unlink()
    assert fails == [], f"Bei kaputtem JSON: kein Fail erwarten, bekam: {fails}"


def main() -> int:
    tests = [
        test_01_baseline_all_filled_no_fails,
        test_02_muss_100pct_null_is_crit,
        test_03_muss_50pct_null_is_warn,
        test_04_muss_30pct_null_at_threshold_warn,
        test_05_muss_5pct_null_below_threshold_ok,
        test_06_muss_zero_float_is_NOT_null,
        test_07_muss_below_min_n_skipped,
        test_08_lag_aged_null_is_warn,
        test_09_lag_recent_entries_not_aged_skip,
        test_10_lag_below_min_aged_n_skipped,
        test_11_weekend_filter_excludes_saturday_sunday,
        test_12_auto_detect_unknown_field_warn,
        test_13_auto_detect_known_observed_no_warn,
        test_14_evaluate_state_invariants_runs_s10,
        test_15_evaluate_state_invariants_ki_agent_only_skips_s10,
        test_16_check_self_failure_is_warn_not_crit,
        test_17_missing_backtest_file_no_crash,
        test_18_corrupt_json_no_crash,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except AssertionError as exc:
            print(f"  ✗ {t.__name__}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ✗ {t.__name__}: unexpected {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} Tests OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
