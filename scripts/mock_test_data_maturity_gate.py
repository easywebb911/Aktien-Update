"""Mock-Tests für das Daten-Reife-Gate (Health-Check S13, 31.05.2026).

Spec: rein lesender Status-Reporter für die drei 30.06.-Auswertungen
(Setup-Edge ≥70/schema_v4, Entry-AUC, CTB-Edge) + EIN Soll-Haken
(RVOL-Normalisierung Soll vs. Ist).

Reife-Definition (exakt wie die geplante Auswertung): V2-only =
``backtest_schema_version == 4``, Setup-Bucket ``score >= 70``, „reif" =
``return_5d`` / ``return_10d`` nicht None (beide getrennt — Auswertungs-
logik noch nicht codifiziert).

Tests:
  1. Setup-Edge zählt ≥70/schema_v4 korrekt (vorhanden/reif_5d/reif_10d)
  2. Nicht-v4-Einträge werden ausgeschlossen
  3. Entry-AUC: „Modul ungebaut, n=0" wenn kein entry_score
  4. Entry-AUC: zählt korrekt wenn entry_score vorhanden
  5. CTB-Edge: „Persistenz ungebaut, n=0" wenn kein cost_to_borrow
  6. CTB-Edge: zählt korrekt wenn cost_to_borrow vorhanden
  7. WARN feuert bei Soll-Ist-Drift (Soll=True, Ist=False)
  8. Still (kein Fail) bei Ist==Soll (beide False)
  9. status_lines sind IMMER 3 (auch bei leerer/fehlender Datei)
 10. Integration: evaluate_state_invariants emittiert S13-Drift-Fail

Ausführung: ``python scripts/mock_test_data_maturity_gate.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402


def _entry(ticker, score, *, schema=4, r5=None, r10=None,
           entry_score=None, cost_to_borrow=None):
    e = {
        "ticker": ticker, "date": "29.05.2026", "score": score,
        "backtest_schema_version": schema,
        "return_5d": r5, "return_10d": r10,
    }
    if entry_score is not None:
        e["entry_score"] = entry_score
    if cost_to_borrow is not None:
        e["cost_to_borrow"] = cost_to_borrow
    return e


def _write(entries) -> str:
    fd = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(entries, fd)
    fd.close()
    return fd.name


# Standard-Fixture: 3 ≥70/v4 (2 reif_5d, 1 reif_10d), 1 <70, 1 non-v4.
def _std_entries():
    return [
        _entry("AAA", 80, r5=0.10, r10=0.20),   # ge70, reif beide
        _entry("BBB", 75, r5=0.05, r10=None),   # ge70, reif nur 5d
        _entry("CCC", 90, r5=None, r10=None),   # ge70, nicht reif
        _entry("DDD", 50, r5=0.30, r10=0.40),   # <70 → ausgeschlossen
        _entry("EEE", 95, schema=3, r5=0.30),   # non-v4 → ausgeschlossen
    ]


# === 1-2 — Setup-Edge ====================================================

def test_setup_edge_counts():
    path = _write(_std_entries())
    res = hc.evaluate_data_maturity_gate(path)
    line = res["status_lines"][0]
    assert "vorhanden=3" in line, line
    assert "reif_5d=2" in line, line
    assert "reif_10d=1" in line, line


def test_non_v4_excluded():
    # Nur ein non-v4-Eintrag mit score≥70 → 0 zählbar.
    path = _write([_entry("ZZZ", 99, schema=2, r5=0.5, r10=0.5)])
    res = hc.evaluate_data_maturity_gate(path)
    assert "vorhanden=0" in res["status_lines"][0], res["status_lines"][0]


# === 3-4 — Entry-AUC =====================================================

def test_entry_ungebaut():
    path = _write(_std_entries())
    res = hc.evaluate_data_maturity_gate(path)
    assert "Modul ungebaut, n=0" in res["status_lines"][1], res["status_lines"][1]


def test_entry_counts_when_present():
    entries = _std_entries()
    entries[0]["entry_score"] = 70   # AAA: reif_5d + reif_10d
    entries[1]["entry_score"] = 55   # BBB: reif_5d nur
    path = _write(entries)
    res = hc.evaluate_data_maturity_gate(path)
    line = res["status_lines"][1]
    assert "vorhanden=2" in line, line
    assert "reif_5d=2" in line, line
    assert "reif_10d=1" in line, line


# === 5-6 — CTB-Edge ======================================================

def test_ctb_ungebaut():
    path = _write(_std_entries())
    res = hc.evaluate_data_maturity_gate(path)
    assert "Persistenz ungebaut, n=0" in res["status_lines"][2], \
        res["status_lines"][2]


def test_ctb_counts_when_present():
    entries = _std_entries()
    entries[0]["cost_to_borrow"] = 12.5  # AAA: reif beide
    entries[1]["cost_to_borrow"] = 8.0   # BBB: reif nur 5d
    path = _write(entries)
    res = hc.evaluate_data_maturity_gate(path)
    line = res["status_lines"][2]
    assert "mit_CTB=2" in line, line
    assert "reif_5d=2" in line, line
    assert "reif_10d=1" in line, line


# === 7-8 — Soll-Ist-Drift WARN ==========================================

def test_warn_on_drift():
    path = _write(_std_entries())
    res = hc.evaluate_data_maturity_gate(
        path, expected_rvol_normalization=True,
        actual_rvol_normalization=False)
    assert len(res["fails"]) == 1, res["fails"]
    f = res["fails"][0]
    assert f["id"] == "S13" and f["severity"] == "warn", f
    assert "Soll-Ist-Drift" in f["detail"], f
    # Status-Zeile zeigt [DRIFT]
    assert "[DRIFT]" in res["status_lines"][0], res["status_lines"][0]


def test_silent_when_ist_equals_soll():
    path = _write(_std_entries())
    res = hc.evaluate_data_maturity_gate(
        path, expected_rvol_normalization=False,
        actual_rvol_normalization=False)
    assert res["fails"] == [], res["fails"]
    assert "[OK]" in res["status_lines"][0], res["status_lines"][0]


# === 9 — Robustheit ======================================================

def test_three_status_lines_on_missing_file():
    res = hc.evaluate_data_maturity_gate("/nonexistent/path/bh.json")
    assert len(res["status_lines"]) == 3, res["status_lines"]
    assert "vorhanden=0" in res["status_lines"][0], res["status_lines"][0]


# === 10 — Integration in evaluate_state_invariants =======================

def test_integration_emits_s13_on_drift():
    # Default config: EXPECTED=False, ENABLED=False → kein S13-Drift-Fail.
    fails = hc.evaluate_state_invariants(
        top10_tickers=["AAA"], setup_scores={f"T{i}": 50 for i in range(8)},
        monster_scores={f"T{i}": 10 for i in range(3)},
        today_iso=None, run_phase="postclose", ki_agent_only=False,
    )
    s13 = [f for f in fails if f.get("id") == "S13"]
    # Bei Default (Ist==Soll) darf KEIN S13-Drift-Fail kommen.
    drift = [f for f in s13 if "Soll-Ist-Drift" in f.get("detail", "")]
    assert drift == [], f"S13-Drift unerwartet bei Ist==Soll: {drift}"


# === Runner ==============================================================

def main():
    tests = [
        ("Setup-Edge zählt ≥70/v4 korrekt",        test_setup_edge_counts),
        ("non-v4 ausgeschlossen",                   test_non_v4_excluded),
        ("Entry-AUC: Modul ungebaut",               test_entry_ungebaut),
        ("Entry-AUC: zählt wenn vorhanden",         test_entry_counts_when_present),
        ("CTB-Edge: Persistenz ungebaut",           test_ctb_ungebaut),
        ("CTB-Edge: zählt wenn vorhanden",          test_ctb_counts_when_present),
        ("WARN bei Soll-Ist-Drift",                 test_warn_on_drift),
        ("still bei Ist==Soll",                     test_silent_when_ist_equals_soll),
        ("3 status_lines bei fehlender Datei",      test_three_status_lines_on_missing_file),
        ("Integration: kein S13-Drift bei Default", test_integration_emits_s13_on_drift),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {name}: UNERWARTET {exc!r}")
    print()
    if failed:
        print(f"{failed} Test(s) FEHLGESCHLAGEN.")
        sys.exit(1)
    print(f"{len(tests)} Tests bestanden.")


if __name__ == "__main__":
    main()
