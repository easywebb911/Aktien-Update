"""Mock-Tests für score_inflation_log.py.

Acht Szenarien (User-Spec):
  1. Phase-Mapping: 5 UTC-Timestamps decken alle 5 Phasen ab
  2. Schema-Vollständigkeit: alle Pflichtfelder belegt
  3. Append-only: zweimaliger Aufruf hängt an, überschreibt nicht
  4. Prune: 35-Tage-alter Eintrag fällt raus, 25-Tage-alter bleibt
  5. Edge: leere Datei → 0 zurückgeschrieben
  6. Edge: kaputte JSONL-Zeile in der Mitte → bleibt erhalten,
     nachfolgende Einträge bleiben lesbar
  7. SI-Trend-Mapping: sideways → flat, no_data → flat
  8. FINRA-Combo-Active: n_combo >= 3 → True

Ausführung: ``python scripts/mock_test_score_inflation_log.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import score_inflation_log as sil  # noqa: E402


def _dt(year, month, day, hour, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _stub_stock(ticker: str = "TEST", **overrides) -> dict:
    base = {
        "ticker":      ticker,
        "score":       72.5,
        "score_raw":   75.2,
        "score_smoothed": 72.8,
        "rel_volume":  2.31,
        "change_2d":   6.16,
        "change_3d":   11.51,
        "rsi14":       62.4,
        "short_float": 30.56,
        "short_ratio": 18.36,
        "finra_data":  {"trend": "down"},
        "finra_bonus_pts": 5.0,
        "earliness_pts": 3,
        "score_trend_bonus_pts": 0.0,
        "agent_boost_factor": 1.05,
        "late_runner": False,
    }
    base.update(overrides)
    return base


def _stub_sub_scores(stock: dict) -> dict:
    return {
        "struct":         28.3,
        "catalyst":       12.5,
        "timing":         22.8,
        "struct_max":     33,
        "catalyst_max":   32,
        "timing_max":     30,
        "turnover_pts":   6,
        "gap_pts":        5,
        "rs_spy_pts":     2,
    }


# === 1. Phase-Mapping ======================================================

def test_session_phase_premarket():
    # 13:29 UTC im EDT = 09:29 ET → premarket
    assert sil._session_phase(_dt(2026, 5, 12, 13, 29)) == "premarket"


def test_session_phase_open():
    # 14:00 UTC im EDT = 10:00 ET → open
    assert sil._session_phase(_dt(2026, 5, 12, 14, 0)) == "open"


def test_session_phase_midday():
    # 17:00 UTC im EDT = 13:00 ET → midday
    assert sil._session_phase(_dt(2026, 5, 12, 17, 0)) == "midday"


def test_session_phase_preclose():
    # 19:30 UTC im EDT = 15:30 ET → preclose
    assert sil._session_phase(_dt(2026, 5, 12, 19, 30)) == "preclose"


def test_session_phase_postclose():
    # 21:00 UTC im EDT = 17:00 ET → postclose
    assert sil._session_phase(_dt(2026, 5, 12, 21, 0)) == "postclose"


# === 2. Schema-Vollständigkeit ============================================

def test_schema_all_required_fields():
    stock = _stub_stock()
    entry = sil._build_entry(stock, _dt(2026, 5, 12, 19, 30),
                             _stub_sub_scores(stock))
    # Top-Level
    for key in ("run_ts", "ticker", "score_total", "score_raw",
                "score_smoothed", "sub_scores", "drivers_raw",
                "trading_session_phase"):
        assert key in entry, f"Pflichtfeld {key} fehlt: {entry}"
    # sub_scores
    for key in ("struct", "catalyst", "timing", "earliness_pts",
                "agent_boost_factor", "late_runner_active"):
        assert key in entry["sub_scores"], f"sub_scores.{key} fehlt"
    # drivers_raw — alle User-Spec-Felder
    for key in ("rel_volume", "change_2d", "change_3d", "rsi14",
                "short_float", "days_to_cover", "finra_si_trend",
                "finra_combo_active", "finra_bonus_pts"):
        assert key in entry["drivers_raw"], f"drivers_raw.{key} fehlt"
    # Wertschau einiger Felder
    assert entry["ticker"] == "TEST"
    assert entry["score_total"] == 72.5
    assert entry["drivers_raw"]["days_to_cover"] == 18.36, entry
    assert entry["drivers_raw"]["finra_si_trend"] == "down", entry
    assert entry["trading_session_phase"] == "preclose", entry


# === 3. Append-Only ========================================================

def test_append_only_two_calls():
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "score_inflation_log.jsonl"
        sil.record_top10_inflation(
            [_stub_stock("AAA"), _stub_stock("BBB")],
            _stub_sub_scores, run_ts=_dt(2026, 5, 12, 14, 0), path=str(path))
        sil.record_top10_inflation(
            [_stub_stock("CCC")], _stub_sub_scores,
            run_ts=_dt(2026, 5, 12, 19, 30), path=str(path))
        with open(path, "r", encoding="utf-8") as fh:
            lines = [json.loads(l) for l in fh if l.strip()]
    assert len(lines) == 3, lines
    assert [l["ticker"] for l in lines] == ["AAA", "BBB", "CCC"], lines
    assert lines[0]["trading_session_phase"] == "open", lines[0]
    assert lines[2]["trading_session_phase"] == "preclose", lines[2]


# === 4. Prune ==============================================================

def test_prune_removes_old_keeps_recent():
    """35-Tage-alter Eintrag raus, 25-Tage-alter bleibt."""
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "score_inflation_log.jsonl"
        with open(path, "w", encoding="utf-8") as fh:
            old = {
                "run_ts": (now - timedelta(days=35)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "ticker": "OLD",
            }
            recent = {
                "run_ts": (now - timedelta(days=25)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "ticker": "NEW",
            }
            fh.write(json.dumps(old) + "\n")
            fh.write(json.dumps(recent) + "\n")
        n_removed = sil.prune_log(max_days=30, path=str(path))
        with open(path, "r", encoding="utf-8") as fh:
            lines = [json.loads(l) for l in fh if l.strip()]
    assert n_removed == 1, n_removed
    assert len(lines) == 1, lines
    assert lines[0]["ticker"] == "NEW", lines


# === 5. Empty file =========================================================

def test_prune_empty_file():
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "does_not_exist.jsonl"
        n = sil.prune_log(max_days=30, path=str(path))
    assert n == 0, n


# === 6. Broken JSONL line in middle =======================================

def test_broken_line_preserved_and_subsequent_readable():
    """Kaputte JSONL-Zeile bleibt erhalten (kein stiller Datenverlust),
    valide Folge-Einträge bleiben lesbar."""
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "score_inflation_log.jsonl"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "run_ts": (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "ticker": "FIRST"}) + "\n")
            fh.write("{this is broken json\n")           # kaputt
            fh.write(json.dumps({
                "run_ts": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "ticker": "AFTER_BROKEN"}) + "\n")
        # read_all skippt kaputte Zeilen
        read = sil.read_all(path=str(path))
        assert len(read) == 2, read
        assert [r["ticker"] for r in read] == ["FIRST", "AFTER_BROKEN"], read
        # Prune lässt kaputte Zeile stehen (kein stiller Drop)
        sil.prune_log(max_days=30, path=str(path))
        with open(path, "r", encoding="utf-8") as fh:
            raw_lines = [l for l in fh if l.strip()]
    assert any("broken" in l for l in raw_lines), raw_lines
    assert any("AFTER_BROKEN" in l for l in raw_lines), raw_lines


# === 7. SI-Trend mapping ===================================================

def test_si_trend_mapping():
    assert sil._normalize_si_trend("up") == "up"
    assert sil._normalize_si_trend("down") == "down"
    assert sil._normalize_si_trend("sideways") == "flat"
    assert sil._normalize_si_trend("no_data") == "flat"
    assert sil._normalize_si_trend(None) == "flat"
    assert sil._normalize_si_trend("garbage") == "flat"


# === 8. FINRA combo flag ==================================================

def test_finra_combo_active_true():
    """SF >= 30, DTC >= 5, RVOL >= 2, SI-Trend=up → n_combo = 4 → True."""
    stock = _stub_stock(
        short_float=35.0, short_ratio=8.0, rel_volume=2.5,
        finra_data={"trend": "up"})
    assert sil._finra_combo_active(stock) is True


def test_finra_combo_active_false():
    """SF >= 30 only → n_combo = 1 → False."""
    stock = _stub_stock(
        short_float=35.0, short_ratio=1.0, rel_volume=0.5,
        finra_data={"trend": "down"})
    assert sil._finra_combo_active(stock) is False


# === Runner ================================================================

def main():
    tests = [
        ("Phase: premarket (13:29 UTC EDT)",      test_session_phase_premarket),
        ("Phase: open (14:00 UTC EDT)",           test_session_phase_open),
        ("Phase: midday (17:00 UTC EDT)",         test_session_phase_midday),
        ("Phase: preclose (19:30 UTC EDT)",       test_session_phase_preclose),
        ("Phase: postclose (21:00 UTC EDT)",      test_session_phase_postclose),
        ("Schema: alle Pflichtfelder belegt",     test_schema_all_required_fields),
        ("Append-only: zwei Calls hängen an",     test_append_only_two_calls),
        ("Prune: 35d raus, 25d bleibt",           test_prune_removes_old_keeps_recent),
        ("Prune: leere Datei → 0",                test_prune_empty_file),
        ("Broken line preserved + readable",      test_broken_line_preserved_and_subsequent_readable),
        ("SI-Trend mapping (up/down/sideways/none)", test_si_trend_mapping),
        ("FINRA Combo aktiv (n>=3)",              test_finra_combo_active_true),
        ("FINRA Combo inaktiv (n=1)",             test_finra_combo_active_false),
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
