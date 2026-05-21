"""Mock-Tests fuer PR-γ-1: score_normalization_version-Marker.

Reiner additiver Schema-Marker — KEINE Score-Logik-Aenderung.
RVOL_NORMALIZATION_ENABLED bleibt False, dieser PR aendert nichts am
Score-Verhalten.

Was getestet wird:
- Konstante SCORE_NORMALIZATION_VERSION existiert + ist int 1
- Konstante ist VERSCHIEDEN von RVOL_NORMALIZATION_ENABLED (eigene Semantik)
- _append_backtest_entries schreibt das Feld in jeden neuen Eintrag mit Wert 1
- S10-Auto-Detect (OBSERVED_FIELDS) kennt das neue Feld → KEIN
  false-positive WARN "Unklassifiziertes Feld" beim ersten γ-1-Run

Ausfuehrung: ``python3 scripts/mock_test_score_normalization_version.py``.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── Konstanten-Tests ──────────────────────────────────────────────────────


def test_01_constant_exists_in_config():
    """SCORE_NORMALIZATION_VERSION ist in config.py definiert, int 1."""
    import config
    assert hasattr(config, "SCORE_NORMALIZATION_VERSION"), (
        "config.SCORE_NORMALIZATION_VERSION fehlt"
    )
    v = config.SCORE_NORMALIZATION_VERSION
    assert isinstance(v, int) and v == 1, (
        f"erwartet int 1 (pre-γ), bekam {v!r}"
    )


def test_02_rvol_normalization_still_disabled():
    """Sanity: PR-γ-1 darf NICHTS am Score-Verhalten aendern —
    RVOL_NORMALIZATION_ENABLED muss weiterhin False sein."""
    import config
    assert config.RVOL_NORMALIZATION_ENABLED is False, (
        "PR-γ-1 darf RVOL_NORMALIZATION_ENABLED nicht flippen — "
        "das ist γ-2."
    )


def test_03_marker_in_s10_observed_fields():
    """S10-Auto-Detect-Schutz: score_normalization_version ist in
    S10_OBSERVED_FIELDS aufgenommen. Sonst wuerde der naechste Daily-Run
    nach γ-1-Merge eine WARN-S10-Zeile schreiben (siehe PR #246
    Auto-Detect-Pfad)."""
    import config
    assert "score_normalization_version" in config.S10_OBSERVED_FIELDS, (
        "score_normalization_version muss in S10_OBSERVED_FIELDS — "
        "sonst feuert S10-Auto-Detect false-positive."
    )


# ── Schreibe-Tests ────────────────────────────────────────────────────────


def test_04_field_in_append_backtest_entries_source():
    """Source-Inspection: _append_backtest_entries schreibt das neue Feld
    in den entry-Dict. Funktionaler Test ueber _append_backtest_entries
    selbst ist nicht moeglich (braucht yfinance + Live-Data), daher
    Source-Check.
    """
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # Suche im Body von _append_backtest_entries nach dem Feld-Eintrag.
    import re
    fn_match = re.search(
        r"def _append_backtest_entries\(.*?(?=^def |\Z)",
        src, re.MULTILINE | re.DOTALL,
    )
    assert fn_match, "_append_backtest_entries nicht gefunden"
    fn_body = fn_match.group(0)
    assert '"score_normalization_version": SCORE_NORMALIZATION_VERSION' in fn_body, (
        "_append_backtest_entries muss das Feld score_normalization_version "
        "aus der config-Konstante in jeden neuen Eintrag schreiben."
    )


def test_05_field_inside_entry_dict_not_extension():
    """Schreibe-Position: Marker im entry-Dict-Literal (main-Loop), NICHT
    im _build_backtest_extension. Damit der Marker unabhaengig von Bahn-B-
    Schema-Erweiterungen mitwandert (auch wenn _build_backtest_extension
    irgendwann durch andere Bahn ersetzt wird).
    """
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # Finde die Stelle direkt nach "vix_level":
    idx_vix = src.find('"vix_level":        vix_level,')
    idx_marker = src.find('"score_normalization_version"')
    assert idx_vix > 0 and idx_marker > 0
    # Marker muss INNERHALB des entry-Dict-Literals stehen (nach vix_level,
    # nahebei — innerhalb 500 Zeichen Distanz reicht als Heuristik)
    distance = idx_marker - idx_vix
    assert 0 < distance < 500, (
        f"Marker sollte direkt nach vix_level im entry-Dict stehen, "
        f"Distanz war {distance} Zeichen"
    )


# ── Integrations-Bestaetigung: S10-Auto-Detect feuert NICHT auf das Feld ──


def test_06_s10_does_not_warn_about_known_field():
    """End-to-End: ein V4-Eintrag mit score_normalization_version=1 darf
    bei S10-Auto-Detect KEINE Unklassifiziert-WARN ausloesen.
    """
    import health_check as hc
    # Minimal-V4-Eintrag bauen
    entry = {
        "date":              "21.05.2026",
        "ticker":            "TEST",
        "backtest_schema_version": 4,
        "score":             80.0,
        "entry_price":       10.0,
        "rvol":              2.0,
        "dtc":               5.0,
        "short_float":       25.0,
        "si_trend":          "up",
        "short_float_source": "yfinance",
        "si_trend_source":   "finra",
        "score_struct":      40.0,
        "score_catalyst":    5.0,
        "score_timing":      35.0,
        "score_raw":         80.0,
        "combo_bonus":       0.0,
        "finra_bonus":       0.0,
        "agent_boost_factor": 1.0,
        "perfect_storm_mult": 1.0,
        "score_trend_bonus": 0.0,
        "pool_member":       True,
        "pool_position":     1,
        "pool_size":         20,
        "market_regime":     "bull",
        "vix_level":         16.5,
        "max_drawdown_pct":  0.0,
        "rvol_buildup_5d":   1.2,
        "vol_stability_5d":  0.05,
        "coiled_spring_score": 50.0,
        "si_trend_5d_slope": 0.10,
        "return_3d":         2.5,
        "return_5d":         4.0,
        "return_3d_t1":      None,
        "return_5d_t1":      None,
        "return_10d":        None,
        "return_10d_t1":     None,
        "entry_price_t1":    None,
        # NEU: PR-γ-1 Marker
        "score_normalization_version": 1,
    }
    unknown = hc._s10_check_unknown_fields([entry])
    assert unknown == set(), (
        f"S10-Auto-Detect findet unklassifizierte Felder: {sorted(unknown)} "
        f"— score_normalization_version sollte in OBSERVED stehen."
    )


def test_07_full_s10_run_with_marker_no_extra_fails():
    """End-to-End: ein V4-Eintrag mit score_normalization_version=1 erzeugt
    keine zusaetzlichen S10-Fails (nur die regulaeren MUSS/LAG-Checks).
    """
    import health_check as hc
    from datetime import date
    dates_iso = ["14.05.2026", "15.05.2026", "16.05.2026", "17.05.2026",
                 "18.05.2026", "19.05.2026", "20.05.2026"]
    # Wir generieren 10 Werktag-Eintraege fuer 10 verschiedene Werktag-Dates
    # rueckwaerts ab 2026-05-20
    from datetime import timedelta
    work_dates = []
    d = date(2026, 5, 20)
    while len(work_dates) < 10:
        if d.weekday() < 5:
            work_dates.append(d.strftime("%d.%m.%Y"))
        d -= timedelta(days=1)
    entries = []
    for d_str in work_dates:
        e = {
            "date":              d_str, "ticker": f"T{len(entries)}",
            "backtest_schema_version": 4, "score": 80.0,
            "entry_price": 10.0, "rvol": 2.0, "dtc": 5.0,
            "short_float": 25.0, "si_trend": "up",
            "short_float_source": "yfinance", "si_trend_source": "finra",
            "score_struct": 40.0, "score_catalyst": 5.0,
            "score_timing": 35.0, "score_raw": 80.0,
            "combo_bonus": 0.0, "finra_bonus": 0.0,
            "agent_boost_factor": 1.0, "perfect_storm_mult": 1.0,
            "score_trend_bonus": 0.0,
            "pool_member": True, "pool_position": 1, "pool_size": 20,
            "market_regime": "bull", "vix_level": 16.5,
            "max_drawdown_pct": 0.0,
            "rvol_buildup_5d": 1.2, "vol_stability_5d": 0.05,
            "coiled_spring_score": 50.0, "si_trend_5d_slope": 0.10,
            "return_3d": 2.5, "return_5d": 4.0,
            "return_3d_t1": None, "return_5d_t1": None,
            "return_10d": None, "return_10d_t1": None,
            "entry_price_t1": None,
            "score_normalization_version": 1,   # PR-γ-1 Marker
        }
        entries.append(e)
    fh = tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                     delete=False, encoding="utf-8")
    json.dump(entries, fh)
    fh.close()
    try:
        fails = hc.evaluate_s10_data_integrity(
            bh_path=fh.name, today=date(2026, 5, 21),
        )
    finally:
        pathlib.Path(fh.name).unlink()
    # Erwartung: alle MUSS gefuellt, alle LAG-aged-Returns gefuellt,
    # KEIN unklassifiziertes Feld → 0 Fails.
    assert fails == [], (
        f"S10 darf bei sauberen Eintraegen mit Marker keine Fails werfen, "
        f"bekam: {fails}"
    )


def main() -> int:
    tests = [
        test_01_constant_exists_in_config,
        test_02_rvol_normalization_still_disabled,
        test_03_marker_in_s10_observed_fields,
        test_04_field_in_append_backtest_entries_source,
        test_05_field_inside_entry_dict_not_extension,
        test_06_s10_does_not_warn_about_known_field,
        test_07_full_s10_run_with_marker_no_extra_fails,
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
