"""Mock-Tests für Phase 2 Trigger 4 (setup_erosion).

Testet die Trigger-Funktion ``_exit_p2_trigger_setup_erosion`` aus
generate_report.py mit synthetischen Position- und cur_setup-Dicts —
keine echten Netzwerk-Calls, keine yfinance.

Szenarien:
  1. Bestandsposition ohne entry_snapshot_ts → available=False
     (reason=no_entry_snapshot)
  2. Snapshot vorhanden, alle current-Werte null → available=False
     (reason=all_drivers_null)
  3. Snapshot vorhanden, ein Driver null, andere bewertbar → available=True
  4. Drop < WARN_THRESHOLD bei allen → score 0
  5. Einzelner Driver in warn-Stufe → score 50, warn=True, reason zeigt nur ihn
  6. Einzelner Driver in crit-Stufe → score 100, crit=True
  7. Zwei Drivers in warn → Combo-Bonus hebt auf score 100 (crit)
  8. Zwei Drivers in crit → score 100, combo_crit=True, reason endet mit "· COMBO"
  9. Negative Drop (Driver hat sich verbessert) → clamped auf 0
  10. entry-Wert ≤ 0 (kaputter Snapshot-Wert) → Driver wird übersprungen,
      andere Drivers bleiben bewertbar
  11. CTB nicht in Combo-Zählung wenn CTB-Endpunkte fehlen
  12. Reason-String-Format mit Prozentwerten

Ausführung: ``python scripts/mock_test_setup_erosion.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import generate_report as gr  # noqa: E402
from config import (  # noqa: E402
    SETUP_EROSION_WARN_THRESHOLD,
    SETUP_EROSION_CRIT_THRESHOLD,
)


def _pos_with_snapshot(**overrides) -> dict:
    """Default: entry_dtc=10, entry_short_float=30, entry_cost_to_borrow=20."""
    base = {
        "entry_dtc":            10.0,
        "entry_short_float":    30.0,
        "entry_cost_to_borrow": 20.0,
        "entry_snapshot_ts":    "2026-04-27T14:00:00Z",
    }
    base.update(overrides)
    return base


# === 1 — Bestandsposition ohne Snapshot ===================================

def test_no_entry_snapshot_unavailable():
    pos = {"entry_date": "2026-04-01", "entry_price": 5.5}
    result = gr._exit_p2_trigger_setup_erosion(pos,
        cur_setup={"dtc": 5.0, "short_float": 20.0, "cost_to_borrow": 10.0})
    assert result["available"] is False, result
    assert result["score"] == 0, result
    assert result["reason"] == "no_entry_snapshot", result


# === 2 — Snapshot da, current alle null ====================================

def test_all_drivers_null_unavailable():
    pos = _pos_with_snapshot()
    result = gr._exit_p2_trigger_setup_erosion(pos,
        cur_setup={"dtc": None, "short_float": None, "cost_to_borrow": None})
    assert result["available"] is False, result
    assert result["reason"] == "all_drivers_null", result


# === 3 — Einer null, andere bewertbar → available=True =====================

def test_partial_drivers_available():
    pos = _pos_with_snapshot()
    result = gr._exit_p2_trigger_setup_erosion(pos,
        cur_setup={"dtc": 8.0, "short_float": 25.0, "cost_to_borrow": None})
    # available=True wenn mindestens ein Driver bewertbar — Felder
    # ohne available-Key sollen available=True implizieren (Pattern
    # andere Trigger).
    assert result.get("available", True) is True, result


# === 4 — Alle Drops < WARN → score 0 =======================================

def test_all_drops_below_warn():
    # dtc 10→9 = 10 % drop, sf 30→28 = 6,67 %, ctb 20→18 = 10 %
    pos = _pos_with_snapshot()
    result = gr._exit_p2_trigger_setup_erosion(pos,
        cur_setup={"dtc": 9.0, "short_float": 28.0, "cost_to_borrow": 18.0})
    assert result["score"] == 0, result
    assert result["warn"] is False, result
    assert result["crit"] is False, result
    assert result["reason"] == "", result


# === 5 — Einzelner Driver in warn-Stufe ====================================

def test_single_driver_warn():
    # dtc 10→6,5 = 35 % drop ≥ 30 % WARN → stage 50
    # sf  30→28 = 6,67 % → 0
    # ctb 20→18 = 10 %   → 0
    pos = _pos_with_snapshot()
    result = gr._exit_p2_trigger_setup_erosion(pos,
        cur_setup={"dtc": 6.5, "short_float": 28.0, "cost_to_borrow": 18.0})
    assert result["score"] == 50, result
    assert result["warn"] is True, result
    assert result["crit"] is False, result
    assert "dtc -35%" in result["reason"], result
    # Andere Drivers tauchen nicht im Reason-String auf (unter WARN)
    assert "sf -" not in result["reason"], result
    assert "ctb -" not in result["reason"], result


# === 6 — Einzelner Driver in crit-Stufe ====================================

def test_single_driver_crit():
    # sf 30→14 = 53,3 % drop ≥ 50 % CRIT → stage 100
    pos = _pos_with_snapshot()
    result = gr._exit_p2_trigger_setup_erosion(pos,
        cur_setup={"dtc": 9.5, "short_float": 14.0, "cost_to_borrow": 18.5})
    assert result["score"] == 100, result
    assert result["warn"] is True, result
    assert result["crit"] is True, result
    assert "sf -53%" in result["reason"], result
    # Einzeln, kein COMBO
    assert "COMBO" not in result["reason"], result


# === 7 — Zwei Drivers in warn → Combo-Bonus → 100 (crit) ===================

def test_two_drivers_warn_combo_to_crit():
    # dtc 10→6,5 = 35 % (warn), sf 30→19 = 36,67 % (warn), ctb 20→18 (kein Drop)
    pos = _pos_with_snapshot()
    result = gr._exit_p2_trigger_setup_erosion(pos,
        cur_setup={"dtc": 6.5, "short_float": 19.0, "cost_to_borrow": 18.0})
    # Beide Drivers stehen einzeln in warn → max(50, 50) = 50, aber
    # Combo-Bonus hebt auf 100. combo_crit bleibt False (keiner ist in crit).
    assert result["score"] == 100, result
    assert result["crit"] is True, result
    assert result["details"]["drivers_above_warn"] == 2, result
    assert result["details"]["drivers_at_crit"] == 0, result
    assert result["details"]["combo_crit"] is False, result
    # Reason zeigt beide Drivers, kein COMBO-Suffix
    assert "dtc -35%" in result["reason"], result
    assert "sf -37%" in result["reason"], result
    assert "COMBO" not in result["reason"], result


# === 8 — Zwei Drivers in crit → combo_crit=True + COMBO-Suffix =============

def test_two_drivers_crit_combo_suffix():
    # dtc 10→4 = 60 % (crit), sf 30→14 = 53,3 % (crit), ctb null
    pos = _pos_with_snapshot()
    result = gr._exit_p2_trigger_setup_erosion(pos,
        cur_setup={"dtc": 4.0, "short_float": 14.0, "cost_to_borrow": None})
    assert result["score"] == 100, result
    assert result["crit"] is True, result
    assert result["details"]["drivers_at_crit"] == 2, result
    assert result["details"]["combo_crit"] is True, result
    assert result["reason"].endswith("· COMBO"), result
    assert "dtc -60%" in result["reason"], result
    assert "sf -53%" in result["reason"], result


# === 9 — Negativer Drop (Verbesserung) → 0-Clamp ===========================

def test_negative_drop_clamped():
    # dtc 10→12 = -20 % (Verbesserung); sf 30→15 = 50 % (crit)
    pos = _pos_with_snapshot()
    result = gr._exit_p2_trigger_setup_erosion(pos,
        cur_setup={"dtc": 12.0, "short_float": 15.0, "cost_to_borrow": 18.0})
    # Negative auf 0 geclampt — Score kommt nur aus sf
    assert result["details"]["dtc_drop"] == 0.0, result
    assert result["details"]["dtc_stage"] == 0, result
    assert result["score"] == 100, result   # sf stage 100
    assert "dtc -" not in result["reason"], result


# === 10 — Kaputter entry-Wert (≤ 0) → Driver übersprungen ==================

def test_entry_value_zero_skipped():
    # entry_dtc=0 → div-by-zero verhindert; andere Drivers bewertbar
    pos = _pos_with_snapshot(entry_dtc=0.0)
    result = gr._exit_p2_trigger_setup_erosion(pos,
        cur_setup={"dtc": 5.0, "short_float": 14.0, "cost_to_borrow": 18.0})
    assert result["details"]["dtc_drop"] is None, result
    assert result["details"]["dtc_stage"] == 0, result
    # sf crit (30→14 = 53 %) gibt Score
    assert result["score"] == 100, result
    assert result.get("available", True) is True, result


# === 11 — CTB nicht in Combo-Zählung ohne Endpunkte ========================

def test_ctb_not_counted_in_combo_when_unavailable():
    # dtc 10→6,5 = 35 % (warn); sf 30→28 (kein Drop); ctb komplett null
    pos = _pos_with_snapshot()
    result = gr._exit_p2_trigger_setup_erosion(pos,
        cur_setup={"dtc": 6.5, "short_float": 28.0, "cost_to_borrow": None})
    # Nur ein Driver in warn — kein Combo
    assert result["score"] == 50, result
    assert result["details"]["drivers_above_warn"] == 1, result
    assert result["details"]["ctb_stage"] is None, result


# === 12 — Reason-String-Format ==============================================

def test_reason_string_format():
    pos = _pos_with_snapshot()
    result = gr._exit_p2_trigger_setup_erosion(pos,
        cur_setup={"dtc": 6.0, "short_float": 14.0, "cost_to_borrow": 13.0})
    # dtc 40 % (warn), sf 53 % (crit), ctb 35 % (warn) — alle ≥ WARN
    assert "dtc -40%" in result["reason"], result
    assert "sf -53%" in result["reason"], result
    assert "ctb -35%" in result["reason"], result
    assert " | " in result["reason"], result   # Separator
    # 3 Drivers above warn → Combo-Bonus auf 100, aber nur 1 in crit
    # → combo_crit bleibt False (≥ 2 in crit erforderlich).
    assert result["score"] == 100, result
    assert result["details"]["combo_crit"] is False, result
    assert "COMBO" not in result["reason"], result


# === Threshold-Konstanten-Sanity ==========================================

def test_thresholds_match_spec():
    """Sicherstellen, dass die Konstanten aus config.py mit der Spec
    (0.30 warn / 0.50 crit) übereinstimmen — falls jemand sie absenkt,
    fällt das hier auf."""
    assert SETUP_EROSION_WARN_THRESHOLD == 0.30, SETUP_EROSION_WARN_THRESHOLD
    assert SETUP_EROSION_CRIT_THRESHOLD == 0.50, SETUP_EROSION_CRIT_THRESHOLD


# === Runner ================================================================

def main():
    tests = [
        ("1. no_entry_snapshot → available=False",     test_no_entry_snapshot_unavailable),
        ("2. all_drivers_null → available=False",      test_all_drivers_null_unavailable),
        ("3. Partial drivers → available=True",        test_partial_drivers_available),
        ("4. Alle Drops < WARN → score 0",             test_all_drops_below_warn),
        ("5. Einzelner Driver in warn",                test_single_driver_warn),
        ("6. Einzelner Driver in crit",                test_single_driver_crit),
        ("7. Zwei Drivers in warn → Combo → 100",      test_two_drivers_warn_combo_to_crit),
        ("8. Zwei Drivers in crit → COMBO-Suffix",     test_two_drivers_crit_combo_suffix),
        ("9. Negativer Drop → 0-clamp",                test_negative_drop_clamped),
        ("10. entry-Wert ≤ 0 → Driver übersprungen",   test_entry_value_zero_skipped),
        ("11. CTB nicht in Combo ohne Endpunkte",      test_ctb_not_counted_in_combo_when_unavailable),
        ("12. Reason-String-Format mit Prozent",       test_reason_string_format),
        ("Thresholds 0.30/0.50 match spec",            test_thresholds_match_spec),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {name}\n      {exc}")
        except Exception as exc:
            failed += 1
            print(f"  ✗ {name}\n      Unexpected: {type(exc).__name__}: {exc}")
    print()
    if failed:
        print(f"{failed} Test(s) fehlgeschlagen.")
        sys.exit(1)
    print(f"{len(tests)} Tests bestanden.")
    sys.exit(0)


if __name__ == "__main__":
    main()
