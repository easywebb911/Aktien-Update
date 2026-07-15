"""Mock-Tests für Earliness V2 (DTC-Niveau-Basis).

Testet ``compute_earliness_pts`` aus generate_report.py mit präparierten
Stock-Dicts gegen die V2-Formel (DTC-Bucket-Mapping + Late-Runner-
Penalty). Datenbeleg aus Diagnose 13.05.2026 (Mann-Whitney-U AUC 0.77).

Ausführung: ``python scripts/mock_test_earliness_dtc.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# === Source-Extraktion =====================================================
# generate_report.py importiert Drittpakete (yfinance, requests, ...) beim
# Modul-Load, die in der Test-Sandbox fehlen. Wir extrahieren die drei
# Earliness-Helper (V1 + V2 + Dispatcher) per Source-Slice und führen sie
# in einem isolierten Namespace mit den nötigen config-Konstanten aus.

src = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _extract(func_def: str) -> str:
    pat = (rf"^def {re.escape(func_def)}\([\s\S]+?(?=^def\s|^class\s|^# ====)")
    m = re.search(pat, src, re.MULTILINE)
    assert m, f"{func_def} nicht in generate_report.py gefunden"
    return m.group(0)


helpers_src = (
    _extract("_earliness_pts_v2")
    + "\n"
    + _extract("_earliness_pts_v1")
    + "\n"
    + _extract("compute_earliness_pts")
)


class _Log:
    def info(self, *a, **k): pass
    def debug(self, *a, **k): pass
    def warning(self, *a, **k): pass


def _make_namespace(version: int) -> dict:
    """Baut einen Test-Namespace mit gegebenem EARLINESS_FORMULA_VERSION-
    Override. Wir patchen die Konstante direkt im namespace, damit der
    `use_v2`-Check in compute_earliness_pts den gewünschten Branch nimmt.
    """
    ns: dict = {"log": _Log()}
    exec(
        "from config import (\n"
        "    EARLINESS_FORMULA_VERSION, EARLINESS_PTS_MAX,\n"
        "    EARLINESS_DTC_BUCKET_1_MIN, EARLINESS_DTC_BUCKET_2_MIN,\n"
        "    EARLINESS_DTC_BUCKET_3_MIN, EARLINESS_DTC_BUCKET_4_MIN,\n"
        "    EARLINESS_DTC_BUCKET_PTS,\n"
        "    EARLINESS_LATE_RUNNER_RVOL_MAX, EARLINESS_LATE_RUNNER_FACTOR,\n"
        "    EARLINESS_ACCEL_PTS, EARLINESS_VELOCITY_PTS,\n"
        "    EARLINESS_VELOCITY_THRESHOLD, EARLINESS_MAX_CHANGE_5D_PCT,\n"
        "    EARLINESS_MAX_RSI,\n"
        "    EARLINESS_PM_VOL_LOW_PCT, EARLINESS_PM_VOL_HIGH_PCT,\n"
        "    EARLINESS_PM_VOL_PTS_LOW, EARLINESS_PM_VOL_PTS_HIGH,\n"
        "    EARLINESS_PTS_MAX_V1,\n"
        ")\n"
        + helpers_src,
        ns,
    )
    ns["EARLINESS_FORMULA_VERSION"] = version
    return ns


# === V2 — DTC-Bucket-Trennschärfe ===========================================

def test_v2_dtc_buckets():
    ns = _make_namespace(version=2)
    cases = [
        (0.0,  0,   "below_3"),
        (2.9,  0,   "below_3"),
        (3.0,  25,  "3_to_5"),
        (4.5,  25,  "3_to_5"),
        (5.0,  50,  "5_to_8"),
        (7.9,  50,  "5_to_8"),
        (8.0,  75,  "8_to_12"),
        (11.9, 75,  "8_to_12"),
        (12.0, 100, "ge_12"),
        (25.0, 100, "ge_12"),
    ]
    for dtc, exp_pts, exp_bucket in cases:
        stocks = [{"ticker": "T", "short_ratio": dtc, "rel_volume": 1.0}]
        ns["compute_earliness_pts"](stocks)
        got_pts    = stocks[0]["earliness_pts"]
        got_bucket = stocks[0]["earliness_breakdown"]["dtc_bucket"]
        assert got_pts == exp_pts, f"dtc={dtc}: erwartet {exp_pts}, got {got_pts}"
        assert got_bucket == exp_bucket, f"dtc={dtc}: erwartet {exp_bucket}, got {got_bucket}"
        assert stocks[0]["earliness_breakdown"]["version"] == 2


def test_v2_late_runner_halves_earliness():
    """RVOL > 5 halbiert den Wert. Test mit DTC=10 (Bucket 75)."""
    ns = _make_namespace(version=2)
    # Ohne Late-Runner: 75 Pkt
    stocks = [{"ticker": "T", "short_ratio": 10.0, "rel_volume": 2.0}]
    ns["compute_earliness_pts"](stocks)
    assert stocks[0]["earliness_pts"] == 75
    assert stocks[0]["earliness_breakdown"]["late_runner"] is False

    # Mit Late-Runner: 75 × 0.5 = 37.5 → round → 38
    stocks = [{"ticker": "T", "short_ratio": 10.0, "rel_volume": 7.0}]
    ns["compute_earliness_pts"](stocks)
    assert stocks[0]["earliness_pts"] == 38
    assert stocks[0]["earliness_breakdown"]["late_runner"] is True
    assert stocks[0]["earliness_breakdown"]["base_pts"] == 75


def test_v2_late_runner_boundary_at_5():
    """RVOL = 5 exakt ist KEIN Late-Runner (strikt größer)."""
    ns = _make_namespace(version=2)
    stocks = [{"ticker": "T", "short_ratio": 10.0, "rel_volume": 5.0}]
    ns["compute_earliness_pts"](stocks)
    assert stocks[0]["earliness_breakdown"]["late_runner"] is False
    assert stocks[0]["earliness_pts"] == 75


def test_v2_late_runner_with_zero_base():
    """Late-Runner-Penalty auf Bucket 0 bleibt 0 (0 × 0.5 = 0)."""
    ns = _make_namespace(version=2)
    stocks = [{"ticker": "T", "short_ratio": 2.0, "rel_volume": 10.0}]
    ns["compute_earliness_pts"](stocks)
    assert stocks[0]["earliness_pts"] == 0
    assert stocks[0]["earliness_breakdown"]["late_runner"] is True
    assert stocks[0]["earliness_breakdown"]["base_pts"] == 0


def test_v2_missing_fields_default_to_zero():
    """Bei fehlendem short_ratio / rel_volume → 0.0 → Bucket 0 → 0 Pkt."""
    ns = _make_namespace(version=2)
    stocks = [{"ticker": "T"}]
    ns["compute_earliness_pts"](stocks)
    assert stocks[0]["earliness_pts"] == 0
    assert stocks[0]["earliness_breakdown"]["dtc"] == 0.0
    assert stocks[0]["earliness_breakdown"]["rvol"] == 0.0


def test_v2_garbage_types_handled():
    """Strings / None / NaN → graceful Fallback auf 0.0."""
    ns = _make_namespace(version=2)
    stocks = [
        {"ticker": "T1", "short_ratio": None, "rel_volume": None},
        {"ticker": "T2", "short_ratio": "garbage", "rel_volume": "bad"},
        {"ticker": "T3", "short_ratio": float("nan"), "rel_volume": 0},
    ]
    ns["compute_earliness_pts"](stocks)
    for s in stocks:
        assert s["earliness_pts"] == 0


# === Conviction-Normalisierung (V2-Skala 0..100) ===========================

def test_conviction_normalization_v2_skala():
    """Replikation der Conviction-Formel:
       earl_pts = round(earliness_pts / EARLINESS_PTS_MAX * 28)
    """
    ns = _make_namespace(version=2)
    pts_max = ns["EARLINESS_PTS_MAX"]
    assert pts_max == 100, f"V2 EARLINESS_PTS_MAX muss 100 sein, got {pts_max}"

    cases = [
        (0,   0),    # 0/100 × 28 = 0
        (25,  7),    # 25/100 × 28 = 7
        (50,  14),   # 50/100 × 28 = 14
        (75,  21),   # 75/100 × 28 = 21
        (100, 28),   # 100/100 × 28 = 28
        (38,  11),   # Late-Runner-Wert 38 → 10.64 → round → 11
    ]
    for earliness_pts, expected_earl_pts in cases:
        got = int(round((float(earliness_pts) / pts_max) * 28))
        got = max(0, min(28, got))
        assert got == expected_earl_pts, (
            f"earliness_pts={earliness_pts}: erwartet {expected_earl_pts}, got {got}")


# === Version-Schalter ======================================================

def test_version_switch_flips_to_v1():
    """Bei EARLINESS_FORMULA_VERSION=1 wird der V1-Pfad genommen
    (Breakdown-Schema enthält V1-Keys, nicht V2-Keys)."""
    ns = _make_namespace(version=1)
    stocks = [{
        "ticker":           "T",
        "short_ratio":      15.0,   # würde V2-Bucket 4 = 100 ergeben
        "rel_volume":       1.0,
        "si_accel":         True,
        "si_shares_per_day": 150.0,
        "change_5d":        2.0,
        "rsi14":            50.0,
        "premarket_volume": 0.0,
        "avg_vol_20d":      1_000_000,
        "cur_open":         10.0,
        "prev_close":       10.0,
    }]
    ns["compute_earliness_pts"](stocks)
    bd = stocks[0]["earliness_breakdown"]
    assert bd["version"] == 1, f"V1-Schalter aktiv, breakdown.version sollte 1 sein, got {bd['version']}"
    assert "accel_match" in bd
    assert "velocity_match" in bd
    assert "pm_vol_match" in bd
    # V1 cap = 7, accel + velocity = 3 + 2 = 5 Pkt
    assert stocks[0]["earliness_pts"] == 5


def test_version_switch_default_is_v2():
    """Ohne expliziten Override nimmt der echte Default EARLINESS_FORMULA_VERSION
    aus config.py (sollte 2 sein)."""
    from config import EARLINESS_FORMULA_VERSION
    assert EARLINESS_FORMULA_VERSION == 2, (
        f"config.py: EARLINESS_FORMULA_VERSION muss 2 sein (Default V2), "
        f"got {EARLINESS_FORMULA_VERSION}")


# === Source-Inspektion =====================================================

def test_constants_present_in_config():
    """Alle V2-Konstanten existieren in config.py."""
    from config import (
        EARLINESS_PTS_MAX,
        EARLINESS_DTC_BUCKET_1_MIN, EARLINESS_DTC_BUCKET_2_MIN,
        EARLINESS_DTC_BUCKET_3_MIN, EARLINESS_DTC_BUCKET_4_MIN,
        EARLINESS_DTC_BUCKET_PTS,
        EARLINESS_LATE_RUNNER_RVOL_MAX, EARLINESS_LATE_RUNNER_FACTOR,
    )
    assert EARLINESS_PTS_MAX == 100
    assert EARLINESS_DTC_BUCKET_1_MIN == 3.0
    assert EARLINESS_DTC_BUCKET_2_MIN == 5.0
    assert EARLINESS_DTC_BUCKET_3_MIN == 8.0
    assert EARLINESS_DTC_BUCKET_4_MIN == 12.0
    assert EARLINESS_DTC_BUCKET_PTS == (0, 25, 50, 75, 100)
    assert EARLINESS_LATE_RUNNER_RVOL_MAX == 5.0
    assert EARLINESS_LATE_RUNNER_FACTOR == 0.5


def test_v1_constants_retained_for_rollback():
    """V1-Konstanten dürfen NICHT gelöscht sein — sonst kein Rollback-Pfad."""
    from config import (
        EARLINESS_ACCEL_PTS, EARLINESS_VELOCITY_PTS,
        EARLINESS_VELOCITY_THRESHOLD, EARLINESS_MAX_CHANGE_5D_PCT,
        EARLINESS_MAX_RSI, EARLINESS_PM_VOL_LOW_PCT,
        EARLINESS_PM_VOL_HIGH_PCT, EARLINESS_PM_VOL_PTS_LOW,
        EARLINESS_PM_VOL_PTS_HIGH, EARLINESS_PTS_MAX_V1,
    )
    assert EARLINESS_PTS_MAX_V1 == 7


# === Runner =================================================================

def main() -> None:
    tests = [
        ("V2: DTC-Bucket-Mapping (10 Stützstellen)",     test_v2_dtc_buckets),
        ("V2: Late-Runner-Penalty halbiert (DTC=10)",    test_v2_late_runner_halves_earliness),
        ("V2: Late-Runner-Boundary RVOL=5 (kein Trigger)", test_v2_late_runner_boundary_at_5),
        ("V2: Late-Runner auf Bucket 0 bleibt 0",         test_v2_late_runner_with_zero_base),
        ("V2: Fehlende Felder → 0",                       test_v2_missing_fields_default_to_zero),
        ("V2: Garbage-Typen → graceful 0",                test_v2_garbage_types_handled),
        ("Conviction-Normalisierung V2-Skala (0/25/50/75/100)",
         test_conviction_normalization_v2_skala),
        ("Version-Schalter: V1-Branch liefert V1-Schema", test_version_switch_flips_to_v1),
        ("Version-Schalter: Default in config.py ist 2",  test_version_switch_default_is_v2),
        ("Konstanten in config.py vorhanden",             test_constants_present_in_config),
        ("V1-Konstanten als Rollback-Schutz vorhanden",   test_v1_constants_retained_for_rollback),
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
