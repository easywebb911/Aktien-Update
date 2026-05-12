"""Mock-Tests für die Zwei-Run-Architektur (12.05.2026).

Spec: 10:00-UTC-Cron schreibt ``run_phase=premarket`` (Vorschau, RVOL
nicht final), 21:00-UTC-Cron schreibt ``run_phase=postclose`` (EOD-
Wahrheit). Workflow-Dispatch defaultet auf postclose.

Tests:
  1. _resolve_run_phase liest ENV korrekt
  2. _resolve_run_phase fällt bei garbage auf premarket zurück + Warning
  3. _resolve_run_phase ohne ENV → premarket (Default für lokale Runs)
  4. _build_entry in score_inflation_log persistiert run_phase
  5. record_top10_inflation propagiert run_phase in alle Einträge
  6. score_inflation_log: run_phase und trading_session_phase koexistieren

  7. Workflow-File parsed sauber, hat zwei Cron-Schedules
  8. Workflow setzt RUN_PHASE-ENV abhängig vom Trigger

Ausführung: ``python scripts/mock_test_postclose_run.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import generate_report as gr  # noqa: E402
import score_inflation_log as sil  # noqa: E402


# === 1-3 — _resolve_run_phase ENV-Resolution ==============================

def test_resolve_run_phase_postclose():
    with patch.dict("os.environ", {"RUN_PHASE": "postclose"}, clear=False):
        assert gr._resolve_run_phase() == "postclose"


def test_resolve_run_phase_premarket():
    with patch.dict("os.environ", {"RUN_PHASE": "premarket"}, clear=False):
        assert gr._resolve_run_phase() == "premarket"


def test_resolve_run_phase_garbage_falls_back():
    with patch.dict("os.environ", {"RUN_PHASE": "garbage"}, clear=False):
        assert gr._resolve_run_phase() == "premarket"


def test_resolve_run_phase_default_premarket():
    with patch.dict("os.environ", {}, clear=False):
        os.environ.pop("RUN_PHASE", None)
        assert gr._resolve_run_phase() == "premarket"


def test_resolve_run_phase_case_insensitive():
    with patch.dict("os.environ", {"RUN_PHASE": "POSTCLOSE"}, clear=False):
        assert gr._resolve_run_phase() == "postclose"


# === 4-6 — score_inflation_log run_phase-Persistenz =======================

def _stub_stock(ticker="TEST"):
    return {
        "ticker": ticker, "score": 72.5, "score_raw": 75.2,
        "rel_volume": 2.31, "change_2d": 6.16, "change_3d": 11.51,
        "rsi14": 62.4, "short_float": 30.0, "short_ratio": 5.0,
        "finra_data": {"trend": "up"}, "finra_bonus_pts": 5.0,
        "earliness_pts": 3,
    }


def _stub_subs(stock):
    return {"struct": 28, "catalyst": 12, "timing": 22,
            "struct_max": 33, "catalyst_max": 32, "timing_max": 30,
            "turnover_pts": 6, "gap_pts": 5, "rs_spy_pts": 2}


def test_build_entry_persists_run_phase():
    entry = sil._build_entry(
        _stub_stock(), datetime(2026, 5, 12, 21, 0, tzinfo=timezone.utc),
        _stub_subs(None), run_phase="postclose")
    assert entry["run_phase"] == "postclose", entry
    assert entry["trading_session_phase"] == "postclose", entry  # ET 17:00


def test_build_entry_run_phase_optional():
    entry = sil._build_entry(
        _stub_stock(), datetime(2026, 5, 12, 14, 0, tzinfo=timezone.utc),
        _stub_subs(None))
    assert entry["run_phase"] is None, entry


def test_record_top10_propagates_run_phase():
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "score_inflation_log.jsonl"
        n = sil.record_top10_inflation(
            [_stub_stock("AAA"), _stub_stock("BBB")],
            _stub_subs,
            run_ts=datetime(2026, 5, 12, 21, 0, tzinfo=timezone.utc),
            path=str(path),
            run_phase="postclose")
        assert n == 2
        with open(path) as fh:
            entries = [json.loads(l) for l in fh if l.strip()]
    assert len(entries) == 2
    for e in entries:
        assert e["run_phase"] == "postclose", e
        # trading_session_phase ist parallel da (Wall-Clock-ET)
        assert "trading_session_phase" in e, e


def test_run_phase_and_session_phase_independent():
    """run_phase (Workflow-Phase) und trading_session_phase (ET-Slot)
    können unterschiedlich sein: ein premarket-Workflow um 12:00 UTC
    läuft im ET-„open"-Slot. Beide Felder bleiben separat."""
    entry = sil._build_entry(
        _stub_stock(),
        datetime(2026, 5, 12, 14, 0, tzinfo=timezone.utc),  # 10:00 ET = open
        _stub_subs(None), run_phase="premarket")
    assert entry["run_phase"] == "premarket", entry
    assert entry["trading_session_phase"] == "open", entry


# === 7-8 — Workflow-File =================================================

def test_workflow_yaml_has_two_crons():
    path = ROOT / ".github" / "workflows" / "daily-squeeze-report.yml"
    content = path.read_text(encoding="utf-8")
    # Beide Crons drin
    assert "cron: '0 10 * * 1-5'" in content, "10:00-UTC-Cron fehlt"
    assert "cron: '0 21 * * 1-5'" in content, "21:00-UTC-Cron fehlt"


def test_workflow_yaml_sets_run_phase_env():
    path = ROOT / ".github" / "workflows" / "daily-squeeze-report.yml"
    content = path.read_text(encoding="utf-8")
    # ENV-Block für RUN_PHASE existiert
    assert "RUN_PHASE:" in content, "RUN_PHASE-ENV im Generate-Step fehlt"
    # workflow_dispatch-Input für run_phase definiert
    assert "run_phase:" in content, "workflow_dispatch.inputs.run_phase fehlt"
    assert "default: 'postclose'" in content, (
        "workflow_dispatch defaultet nicht auf postclose")
    # Mapping: Cron-Schedule 21:00 → postclose
    assert "'0 21 * * 1-5' && 'postclose'" in content, (
        "21:00-Cron → postclose Mapping fehlt")


def test_workflow_yaml_parseable():
    """Falls PyYAML installiert ist, parsen wir die Datei voll durch."""
    try:
        import yaml  # noqa
    except ImportError:
        print("    (PyYAML nicht installiert — Strukturcheck übersprungen)")
        return
    path = ROOT / ".github" / "workflows" / "daily-squeeze-report.yml"
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    # `on` ist in YAML wahr (true) — daher Key True statt "on"
    on = data.get("on") or data.get(True)
    assert on is not None, list(data.keys())
    schedules = on.get("schedule") or []
    assert len(schedules) == 2, schedules
    crons = sorted(s.get("cron") for s in schedules)
    assert crons == ["0 10 * * 1-5", "0 21 * * 1-5"], crons


# === Runner ================================================================

def main():
    tests = [
        ("_resolve_run_phase: postclose-Env",          test_resolve_run_phase_postclose),
        ("_resolve_run_phase: premarket-Env",          test_resolve_run_phase_premarket),
        ("_resolve_run_phase: garbage → premarket",    test_resolve_run_phase_garbage_falls_back),
        ("_resolve_run_phase: kein Env → premarket",   test_resolve_run_phase_default_premarket),
        ("_resolve_run_phase: case-insensitive",       test_resolve_run_phase_case_insensitive),
        ("score_inflation: _build_entry mit run_phase", test_build_entry_persists_run_phase),
        ("score_inflation: run_phase optional",         test_build_entry_run_phase_optional),
        ("record_top10 propagiert run_phase",           test_record_top10_propagates_run_phase),
        ("run_phase ≠ trading_session_phase",           test_run_phase_and_session_phase_independent),
        ("Workflow: zwei Cron-Schedules",              test_workflow_yaml_has_two_crons),
        ("Workflow: RUN_PHASE-ENV gesetzt",             test_workflow_yaml_sets_run_phase_env),
        ("Workflow: YAML strukturell parsebar",         test_workflow_yaml_parseable),
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
