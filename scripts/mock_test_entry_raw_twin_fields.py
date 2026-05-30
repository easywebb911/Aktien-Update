"""Mock-Tests für Twin-Roh-Felder score_delta_t1_raw + anomaly_push_age_h
(Shadow-Persist 29.05.2026).

Ziel: ungecappte/un-transformierte Pendants neben den zensierten Feldern
score_delta_t1 (Clamp ±15) und anomaly_freshness (Decay + 0-Floor), damit
die Cap-vs-Perzentil-Auswertung ~30.06. nicht auf zensierten Werten läuft.

Verifiziert:
- score_delta_t1_raw ungecappt (>15 / <−15 bleibt erhalten), während
  score_delta_t1 daneben geclampt ist.
- anomaly_push_age_h roh (h vor Decay), freshness daneben transformiert.
- beide None-tolerant.
- beide in S10_OBSERVED_FIELDS, schema_version weiterhin == 4.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# yfinance & Co. sind in der Test-Sandbox nicht installiert (nur via
# requirements.txt im CI). backtest_history importiert yfinance top-level —
# Stub analog mock_test_entry_shadow_persist.py.
for _mod_name in ("yfinance", "bs4", "deep_translator", "lxml", "pandas"):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)
sys.modules["yfinance"].download = lambda *a, **kw: None
sys.modules["yfinance"].Ticker = lambda *a, **kw: None

import backtest_history as bh  # noqa: E402
import config                  # noqa: E402
import health_check as hc      # noqa: E402,F401


# ── Helper-Tests: Roh-Compute-Funktionen ──────────────────────────────────


def test_01_raw_delta_uncapped_positive():
    """Roh-Delta > +15 bleibt erhalten; geclamptes Twin liegt bei 15."""
    scores = [10.0, 50.0]   # delta = +40
    raw = bh._compute_score_delta_t1_raw(scores)
    clamped = bh._compute_score_delta_t1(scores)
    assert raw == 40.0, f"erwartet 40.0 ungecappt, got {raw}"
    assert clamped == 15.0, f"erwartet 15.0 geclampt, got {clamped}"


def test_02_raw_delta_uncapped_negative():
    """Roh-Delta < −15 bleibt erhalten; geclamptes Twin liegt bei −15."""
    scores = [80.0, 23.0]   # delta = −57 (echter raw-Range-Rand laut CLAUDE.md)
    raw = bh._compute_score_delta_t1_raw(scores)
    clamped = bh._compute_score_delta_t1(scores)
    assert raw == -57.0, f"erwartet −57.0 ungecappt, got {raw}"
    assert clamped == -15.0, f"erwartet −15.0 geclampt, got {clamped}"


def test_03_raw_delta_within_range_equals_clamped():
    """Innerhalb ±15 sind raw und geclampt identisch."""
    scores = [50.0, 57.0]   # delta = +7
    assert bh._compute_score_delta_t1_raw(scores) == 7.0
    assert bh._compute_score_delta_t1(scores) == 7.0


def test_04_raw_delta_none_guards():
    """Gleiche None-/Längen-Guards wie das geclampte Twin."""
    assert bh._compute_score_delta_t1_raw(None) is None
    assert bh._compute_score_delta_t1_raw([]) is None
    assert bh._compute_score_delta_t1_raw([50.0]) is None         # < 2 Werte
    assert bh._compute_score_delta_t1_raw(["x", "y"]) is None     # nicht-konvertierbar


def test_05_push_age_raw_vs_freshness_transform():
    """age_h roh; freshness = max(1 − age/72, 0) daneben."""
    now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    ts  = (now - timedelta(hours=36)).isoformat()   # 36 h alt
    age = bh._compute_anomaly_push_age_h(ts, now)
    fresh = bh._compute_anomaly_freshness(ts, now)
    assert abs(age - 36.0) < 0.01, f"erwartet ~36.0 h roh, got {age}"
    # freshness = max(1 − 36/72, 0) = 0.5
    assert abs(fresh - 0.5) < 0.01, f"erwartet ~0.5 transformiert, got {fresh}"


def test_06_push_age_raw_survives_72h_floor():
    """age_h > 72 h bleibt roh erhalten, während freshness auf 0.0 floort."""
    now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    ts  = (now - timedelta(hours=200)).isoformat()  # 200 h — weit über 72 h
    age = bh._compute_anomaly_push_age_h(ts, now)
    fresh = bh._compute_anomaly_freshness(ts, now)
    assert abs(age - 200.0) < 0.01, f"erwartet ~200.0 h roh, got {age}"
    assert fresh == 0.0, f"freshness muss auf 0.0 floored sein, got {fresh}"


def test_07_push_age_none_guards():
    """Gleiche None-Guards wie freshness."""
    now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    assert bh._compute_anomaly_push_age_h(None, now) is None
    assert bh._compute_anomaly_push_age_h("", now) is None
    assert bh._compute_anomaly_push_age_h("garbage", now) is None


# ── Integration: _build_backtest_extension end-to-end ──────────────────────


def _baseline_stock(sparkline_scores=None):
    return {
        "ticker": "TEST", "score": 70.0, "score_raw": 68.0, "price": 10.0,
        "short_float": 25.0, "short_ratio": 5.0, "rel_volume": 2.4,
        "rel_volume_yesterday": 1.5, "change": 2.5, "float_shares": 1e8,
        "avg_vol_20d": 1e6, "hist_5d": [],
        "score_trend_bonus_pts": 0.0, "agent_boost_factor": 1.0,
        "finra_bonus_pts": 0.0, "short_float_source": "yfinance",
        "finra_data": {"trend": "no_data", "history": [],
                       "si_trend_source": "finra"},
        "sparkline": ({"scores": sparkline_scores}
                      if sparkline_scores is not None else None),
    }


def _build(stock, push_map=None, now=None):
    return bh._build_backtest_extension(
        stock, pool_position=1, pool_size=20, agent_signals={},
        compute_sub_scores_fn=lambda s: {"struct": 0, "catalyst": 0, "timing": 0},
        safe_float_fn=lambda v, d=0.0: float(v) if v not in (None, "") else d,
        latest_push_ts_by_ticker=push_map,
        now_dt=now,
    )


def test_08_integration_raw_delta_uncapped_in_entry():
    """End-to-end: score_delta_t1_raw ungecappt, score_delta_t1 geclampt."""
    ext = _build(_baseline_stock([10.0, 50.0]))   # delta +40
    assert ext["score_delta_t1_raw"] == 40.0, ext.get("score_delta_t1_raw")
    assert ext["score_delta_t1"] == 15.0, ext.get("score_delta_t1")


def test_09_integration_push_age_raw_in_entry():
    """End-to-end: anomaly_push_age_h roh, anomaly_freshness transformiert."""
    now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    ts  = (now - timedelta(hours=36)).isoformat()
    ext = _build(_baseline_stock([50.0, 57.0]), push_map={"TEST": ts}, now=now)
    assert abs(ext["anomaly_push_age_h"] - 36.0) < 0.01, ext.get("anomaly_push_age_h")
    assert abs(ext["anomaly_freshness"] - 0.5) < 0.01, ext.get("anomaly_freshness")


def test_10_integration_none_tolerant():
    """Fehlende Quellen → beide Roh-Felder None, kein Crash."""
    ext = _build(_baseline_stock(None), push_map=None)   # keine Sparkline, kein Push
    assert ext["score_delta_t1_raw"] is None, ext.get("score_delta_t1_raw")
    assert ext["anomaly_push_age_h"] is None, ext.get("anomaly_push_age_h")
    # Bestehende Twins ebenfalls None (Konsistenz)
    assert ext["score_delta_t1"] is None
    assert ext["anomaly_freshness"] is None


def test_11_schema_version_stays_4():
    """Schema bleibt v4 — additiv, KEIN Bump (S10-v4-Filter-Falle)."""
    ext = _build(_baseline_stock([50.0, 57.0]))
    assert ext["backtest_schema_version"] == 4, ext.get("backtest_schema_version")


# ── Schema-Disziplin: S10_OBSERVED_FIELDS ─────────────────────────────────


def test_12_new_fields_in_s10_observed():
    """Beide neuen Keys in S10_OBSERVED_FIELDS (nicht MUSS/LAG)."""
    assert "score_delta_t1_raw" in config.S10_OBSERVED_FIELDS, \
        "score_delta_t1_raw fehlt in S10_OBSERVED_FIELDS"
    assert "anomaly_push_age_h" in config.S10_OBSERVED_FIELDS, \
        "anomaly_push_age_h fehlt in S10_OBSERVED_FIELDS"
    # Negativ: NICHT in MUSS/LAG (sonst false-positive S10-Fail)
    assert "score_delta_t1_raw" not in config.S10_MUSS_FIELDS
    assert "score_delta_t1_raw" not in config.S10_LAG_FIELDS
    assert "anomaly_push_age_h" not in config.S10_MUSS_FIELDS
    assert "anomaly_push_age_h" not in config.S10_LAG_FIELDS


def test_13_no_unknown_field_in_s10_autodetect():
    """S10-Auto-Detect (unbekannte Felder) darf die neuen Keys NICHT flaggen
    — sonst false-positive WARN 'Feld aufgetaucht, nicht klassifiziert'."""
    import health_check as hc
    ext = _build(_baseline_stock([50.0, 57.0]))
    # Simuliere ein V4-Entry mit allen Feldern + Pflicht-Datums-/Ticker-Keys
    entry = dict(ext)
    entry.update({"date": "29.05.2026", "ticker": "TEST"})
    unknown = hc._s10_check_unknown_fields([entry])
    assert "score_delta_t1_raw" not in unknown, \
        f"score_delta_t1_raw als unbekannt geflaggt: {unknown}"
    assert "anomaly_push_age_h" not in unknown, \
        f"anomaly_push_age_h als unbekannt geflaggt: {unknown}"


# ── Runner ─────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    tests = [
        test_01_raw_delta_uncapped_positive,
        test_02_raw_delta_uncapped_negative,
        test_03_raw_delta_within_range_equals_clamped,
        test_04_raw_delta_none_guards,
        test_05_push_age_raw_vs_freshness_transform,
        test_06_push_age_raw_survives_72h_floor,
        test_07_push_age_none_guards,
        test_08_integration_raw_delta_uncapped_in_entry,
        test_09_integration_push_age_raw_in_entry,
        test_10_integration_none_tolerant,
        test_11_schema_version_stays_4,
        test_12_new_fields_in_s10_observed,
        test_13_no_unknown_field_in_s10_autodetect,
    ]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} Tests bestanden.")
