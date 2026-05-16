"""Mock-Tests fuer score_inflation_log Schema v2 (PR-beta, 16.05.2026).

Hintergrund:
PR-alpha (#166) hat _normalize_rvol + Feature-Flag eingebaut, Default
OFF. PR-beta sammelt 14 Tage parallele Empirik-Daten, indem der Logger
zusaetzlich rel_volume_normalized in jede Zeile schreibt — den
hypothetischen Wert mit ENABLED=True, ohne den globalen Flag zu setzen.

Schema-Aenderungen:
- schema_v: 2 (Cutover-Marker; v1-Eintraege haben keinen Marker)
- drivers_raw.rel_volume_normalized: float | None
- Alle bestehenden Felder unveraendert.

Tests:
  1. _build_entry liefert schema_v=2
  2. drivers_raw.rel_volume_normalized wird berechnet wenn normalize_rvol_fn
     uebergeben
  3. drivers_raw.rel_volume bleibt der Live-Wert (status quo)
  4. Ohne normalize_rvol_fn ist rel_volume_normalized = None (graceful)
  5. _normalize_rvol-Helper hat neuen Parameter force_enabled
  6. force_enabled=True ueberschreibt RVOL_NORMALIZATION_ENABLED=False
  7. force_enabled=False (Default) = altes Verhalten
  8. Schreib-Pfad in generate_report.py uebergibt normalize_rvol_fn=_normalize_rvol
  9. Reader-Compat: prune_log liest schema_v=1 (ohne Marker) ohne Crash
 10. Reader-Compat: read_all funktioniert mit gemischtem v1+v2-File
 11. Edge: stock ohne avg_vol_20d -> rel_volume_normalized=None
 12. Edge: stock mit avg_vol_20d=0 -> rel_volume_normalized=None
 13. Edge: stock mit rel_volume=None -> rel_volume_normalized=None
 14. Edge: normalize_rvol_fn raised Exception -> rel_volume_normalized=None
     (kein Crash, eintrag wird trotzdem geschrieben)
 15. CLAUDE.md: Schema-Version-Geschichte vorhanden
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
SIL = (ROOT / "score_inflation_log.py").read_text(encoding="utf-8")
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

# score_inflation_log ist importierbar (keine pandas-/yfinance-Abhaengigkeit)
import score_inflation_log as sil


# ── Mocks ────────────────────────────────────────────────────────────────────

def _mock_stock(
    ticker="TEST",
    rel_volume=2.0,
    avg_vol_20d=1_000_000.0,
    short_float=20.0,
    short_ratio=5.0,
    score=70.0,
):
    return {
        "ticker": ticker,
        "score": score,
        "score_raw": score,
        "score_smoothed": score,
        "rel_volume": rel_volume,
        "avg_vol_20d": avg_vol_20d,
        "change_2d": 5.0,
        "change_3d": 8.0,
        "rsi14": 65.0,
        "short_float": short_float,
        "short_ratio": short_ratio,
        "earliness_pts": 50,
        "score_trend_bonus_pts": 0,
        "agent_boost_factor": 1.0,
        "late_runner": False,
        "finra_data": {"trend": "up"},
        "finra_bonus_pts": 5,
    }


def _identity_normalize(raw_vol, avg_20d, *, run_phase=None, now_utc=None,
                        force_enabled=False):
    """Mock: returnt raw / avg (kein Skalieren — testet nur Verkabelung)."""
    if raw_vol is None or avg_20d is None or avg_20d <= 0 or raw_vol <= 0:
        return 0.0
    return raw_vol / avg_20d


def _scaling_normalize(raw_vol, avg_20d, *, run_phase=None, now_utc=None,
                       force_enabled=False):
    """Mock: returnt 10× raw/avg um zu zeigen dass normalize-Pfad genutzt wurde."""
    if raw_vol is None or avg_20d is None or avg_20d <= 0 or raw_vol <= 0:
        return 0.0
    return (raw_vol / avg_20d) * 10.0


# ── Tests ────────────────────────────────────────────────────────────────────

def test_01_build_entry_has_schema_v2() -> None:
    entry = sil._build_entry(_mock_stock(), datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
                              sub_scores={"struct": 40, "catalyst": 25, "timing": 30},
                              run_phase="premarket")
    assert entry.get("schema_v") == 2, f"schema_v fehlt oder falsch: {entry.get('schema_v')}"


def test_02_rel_volume_normalized_computed_when_fn_passed() -> None:
    entry = sil._build_entry(_mock_stock(rel_volume=3.0, avg_vol_20d=1_000_000.0),
                              datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
                              sub_scores={},
                              run_phase="premarket",
                              normalize_rvol_fn=_scaling_normalize)
    # cur_vol = 3.0 × 1_000_000 = 3_000_000
    # scaling_normalize liefert (3_000_000 / 1_000_000) × 10 = 30.0
    assert entry["drivers_raw"]["rel_volume_normalized"] == 30.0


def test_03_rel_volume_remains_live_value() -> None:
    entry = sil._build_entry(_mock_stock(rel_volume=3.0, avg_vol_20d=1_000_000.0),
                              datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
                              sub_scores={},
                              run_phase="premarket",
                              normalize_rvol_fn=_scaling_normalize)
    # rel_volume = Live-Wert (status quo), unabhaengig von normalize-fn-Output
    assert entry["drivers_raw"]["rel_volume"] == 3.0


def test_04_no_fn_means_normalized_none() -> None:
    entry = sil._build_entry(_mock_stock(),
                              datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
                              sub_scores={},
                              run_phase="premarket",
                              normalize_rvol_fn=None)
    assert entry["drivers_raw"]["rel_volume_normalized"] is None


def test_05_normalize_rvol_has_force_enabled_param() -> None:
    # Source-Inspektion: force_enabled in Signatur
    sig_start = GR.find("def _normalize_rvol(")
    sig_end = GR.find(") -> float:", sig_start)
    sig = GR[sig_start:sig_end + 50]
    assert "force_enabled: bool = False" in sig, "force_enabled-Parameter fehlt"


def test_06_force_enabled_overrides_global_flag() -> None:
    # Source-Inspektion: enabled = RVOL_NORMALIZATION_ENABLED or force_enabled
    assert "enabled = RVOL_NORMALIZATION_ENABLED or force_enabled" in GR, \
        "OR-Verknuepfung Flag + force_enabled fehlt"


def test_07_force_enabled_false_default_unchanged() -> None:
    # Source-Inspektion: Default-Wert ist False
    sig_block = GR[GR.find("def _normalize_rvol("):
                    GR.find(") -> float:", GR.find("def _normalize_rvol("))]
    assert "force_enabled: bool = False" in sig_block, \
        "Default force_enabled=False fehlt"


def test_08_generate_report_passes_normalize_fn() -> None:
    # Aufrufer in generate_report.py uebergibt normalize_rvol_fn=_normalize_rvol
    assert "normalize_rvol_fn=_normalize_rvol" in GR, \
        "Aufrufer uebergibt normalize_rvol_fn nicht"


def test_09_reader_compat_v1_entry_no_crash() -> None:
    # v1-Eintrag (ohne schema_v) muss von prune_log/read_all sauber gelesen werden
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False,
                                       encoding="utf-8") as fh:
        # v1-Eintrag (kein schema_v, kein rel_volume_normalized)
        v1_entry = {
            "run_ts": "2026-05-12T10:00:00Z",
            "run_phase": "premarket",
            "ticker": "OLD",
            "score_total": 60.0,
            "drivers_raw": {"rel_volume": 2.0},
        }
        fh.write(json.dumps(v1_entry) + "\n")
        path = fh.name
    try:
        entries = sil.read_all(path=path)
        assert len(entries) == 1
        e = entries[0]
        assert e.get("schema_v", 1) == 1, \
            "v1-Eintrag muss als schema_v=1 fallback erkannt werden"
        assert "rel_volume_normalized" not in e["drivers_raw"]
    finally:
        os.unlink(path)


def test_10_reader_compat_mixed_v1_v2() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False,
                                       encoding="utf-8") as fh:
        # v1
        fh.write(json.dumps({"run_ts": "2026-05-12T10:00:00Z", "ticker": "OLD",
                              "drivers_raw": {"rel_volume": 2.0}}) + "\n")
        # v2
        fh.write(json.dumps({"schema_v": 2, "run_ts": "2026-05-16T10:00:00Z",
                              "ticker": "NEW",
                              "drivers_raw": {"rel_volume": 3.0,
                                              "rel_volume_normalized": 30.0}}) + "\n")
        path = fh.name
    try:
        entries = sil.read_all(path=path)
        assert len(entries) == 2
        old, new = entries
        assert old.get("schema_v", 1) == 1
        assert new.get("schema_v") == 2
        assert new["drivers_raw"]["rel_volume_normalized"] == 30.0
    finally:
        os.unlink(path)


def test_11_edge_no_avg_vol_20d() -> None:
    stock = _mock_stock()
    stock.pop("avg_vol_20d", None)
    entry = sil._build_entry(stock, datetime.now(timezone.utc), sub_scores={},
                              normalize_rvol_fn=_scaling_normalize)
    assert entry["drivers_raw"]["rel_volume_normalized"] is None


def test_12_edge_avg_vol_zero() -> None:
    entry = sil._build_entry(_mock_stock(avg_vol_20d=0.0),
                              datetime.now(timezone.utc), sub_scores={},
                              normalize_rvol_fn=_scaling_normalize)
    assert entry["drivers_raw"]["rel_volume_normalized"] is None


def test_13_edge_rel_volume_none() -> None:
    stock = _mock_stock()
    stock["rel_volume"] = None
    entry = sil._build_entry(stock, datetime.now(timezone.utc), sub_scores={},
                              normalize_rvol_fn=_scaling_normalize)
    assert entry["drivers_raw"]["rel_volume_normalized"] is None


def test_14_edge_fn_raises() -> None:
    def _raises(*a, **kw):
        raise RuntimeError("boom")
    entry = sil._build_entry(_mock_stock(), datetime.now(timezone.utc),
                              sub_scores={}, normalize_rvol_fn=_raises)
    # Eintrag wird trotzdem gebaut, normalized=None
    assert entry["drivers_raw"]["rel_volume_normalized"] is None
    assert entry["ticker"] == "TEST"


def test_15_claude_md_schema_history() -> None:
    # Suche nach Schema-Version-Geschichte
    assert "schema_v" in CMD, "Schema-Version-Doku in CLAUDE.md fehlt"
    # Beide Versionen erwähnt
    assert ("v1" in CMD or "Schema v1" in CMD) and ("v2" in CMD or "Schema v2" in CMD), \
        "Schema-Versionen v1/v2 nicht beide in CLAUDE.md dokumentiert"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 _build_entry hat schema_v=2",            test_01_build_entry_has_schema_v2),
        ("02 rel_volume_normalized berechnet",        test_02_rel_volume_normalized_computed_when_fn_passed),
        ("03 rel_volume bleibt Live-Wert",            test_03_rel_volume_remains_live_value),
        ("04 ohne fn -> normalized=None",             test_04_no_fn_means_normalized_none),
        ("05 force_enabled-Param in Signatur",        test_05_normalize_rvol_has_force_enabled_param),
        ("06 force_enabled OR mit Global-Flag",       test_06_force_enabled_overrides_global_flag),
        ("07 force_enabled Default False",            test_07_force_enabled_false_default_unchanged),
        ("08 Caller uebergibt normalize_rvol_fn",     test_08_generate_report_passes_normalize_fn),
        ("09 v1-Eintrag ohne Crash lesbar",           test_09_reader_compat_v1_entry_no_crash),
        ("10 v1+v2 gemischt lesbar",                  test_10_reader_compat_mixed_v1_v2),
        ("11 Edge: kein avg_vol_20d",                 test_11_edge_no_avg_vol_20d),
        ("12 Edge: avg_vol_20d=0",                    test_12_edge_avg_vol_zero),
        ("13 Edge: rel_volume=None",                  test_13_edge_rel_volume_none),
        ("14 Edge: fn raised → None, kein Crash",     test_14_edge_fn_raises),
        ("15 CLAUDE.md Schema-Version-Geschichte",    test_15_claude_md_schema_history),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
        except AssertionError as exc:
            print(f"  FAIL {name}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
            failed += 1
    print()
    print(f"Total: {len(tests)} | Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
