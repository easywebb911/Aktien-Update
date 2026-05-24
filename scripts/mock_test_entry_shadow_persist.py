"""Mock-Tests fuer Entry-Modul-Shadow-Persist (25.05.2026).

Zwei vorgezogene Felder in _build_backtest_extension (backtest_history.py),
damit sie frueh fuer die Entry-AUC ~30.06. sammeln — KEIN Score-/Push-Effekt:
- score_delta_t1    = clamp(sparkline.scores[-1] - [-2], +/-15); None bei < 2
- anomaly_freshness = max(1 - age_h/72, 0) aus push_history-ts; None ohne Push

Beide LEGITIM-leer-tolerant (None erlaubt) -> nur S10_OBSERVED_FIELDS, NICHT
MUSS/LAG. Schema bleibt v4 (additiv, KEIN Bump — sonst wuerde der
S10-v4-Filter `== 4` neue Eintraege aus der Ueberwachung ausschliessen).

Pattern: Source-Inspektion + Funktional-Tests via pure Helper direkt.

Ausfuehrung: ``python3 scripts/mock_test_entry_shadow_persist.py``.
"""
from __future__ import annotations

import pathlib
import sys
import types
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Drittlib-Stubs fuer die Test-Sandbox (im GH-Actions-Env existieren alle
# via requirements.txt). backtest_history importiert yfinance top-level.
for _mod_name in ("yfinance", "bs4", "deep_translator", "lxml", "pandas"):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)
sys.modules["yfinance"].download = lambda *a, **kw: None
sys.modules["yfinance"].Ticker = lambda *a, **kw: None
sys.modules["bs4"].BeautifulSoup = lambda *a, **kw: None
sys.modules["deep_translator"].GoogleTranslator = lambda *a, **kw: type(
    "T", (), {"translate": staticmethod(lambda s: s)}
)()

import backtest_history as bh   # noqa: E402


# ── 1) Klassifikation ─────────────────────────────────────────────────────


def test_01_both_in_observed_not_muss_not_lag():
    """Beide Felder LEGITIM-leer-tolerant -> nur OBSERVED, nicht MUSS/LAG."""
    import config
    for field in ("score_delta_t1", "anomaly_freshness"):
        assert field in config.S10_OBSERVED_FIELDS, (
            f"{field} fehlt in S10_OBSERVED_FIELDS -> Auto-Detect-WARN am "
            f"ersten Daily-Run nach Merge."
        )
        assert field not in config.S10_MUSS_FIELDS, (
            f"{field} darf NICHT in S10_MUSS_FIELDS (legitim oft None)."
        )
        assert field not in config.S10_LAG_FIELDS, (
            f"{field} darf NICHT in S10_LAG_FIELDS (kein LAG-Outcome)."
        )


# ── 2) Source-Inspektion ──────────────────────────────────────────────────


def test_02_fields_in_build_backtest_extension():
    """Beide Felder stehen im return-dict von _build_backtest_extension."""
    src = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    for field in ('"score_delta_t1":', '"anomaly_freshness":'):
        assert field in src, (
            f"_build_backtest_extension schreibt {field} nicht."
        )


def test_03_schema_version_stays_4():
    """Schema bleibt v4 (additiv, KEIN Bump) — sonst S10-v4-Filter-Falle."""
    src = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    assert '"backtest_schema_version": 4,' in src, (
        "backtest_schema_version muss 4 bleiben (kein v5-Bump — sonst "
        "schliesst _s10_load_v4_entries die neuen Eintraege aus)."
    )
    assert '"backtest_schema_version": 5' not in src, "Unerwarteter v5-Bump!"


def test_04_expected_keys_in_selftest():
    """Der _test_extended_schema-Selbsttest listet beide neuen Keys."""
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    import re
    m = re.search(r"def _test_extended_schema\(.*?(?=^def |\Z)",
                  src, re.MULTILINE | re.DOTALL)
    assert m, "_test_extended_schema nicht gefunden"
    body = m.group(0)
    for key in ("score_delta_t1", "anomaly_freshness"):
        assert f'"{key}"' in body, (
            f"_test_extended_schema:expected_keys muss {key!r} enthalten."
        )


# ── 3) Funktional: score_delta_t1 ─────────────────────────────────────────


def test_05_score_delta_normal():
    assert bh._compute_score_delta_t1([50.0, 57.0]) == 7.0
    assert bh._compute_score_delta_t1([57.0, 50.0]) == -7.0


def test_06_score_delta_cap_plus15():
    assert bh._compute_score_delta_t1([10.0, 99.0]) == 15.0


def test_07_score_delta_cap_minus15():
    assert bh._compute_score_delta_t1([99.0, 10.0]) == -15.0


def test_08_score_delta_none_below_two():
    assert bh._compute_score_delta_t1([50.0]) is None
    assert bh._compute_score_delta_t1([]) is None
    assert bh._compute_score_delta_t1(None) is None


def test_09_score_delta_uses_last_two():
    """Nur die letzten zwei Werte zaehlen (oldest->newest)."""
    assert bh._compute_score_delta_t1([10.0, 20.0, 30.0, 33.0]) == 3.0


# ── 4) Funktional: anomaly_freshness ──────────────────────────────────────


def _ts(now, hours_ago):
    return (now - timedelta(hours=hours_ago)).isoformat()


def test_10_freshness_age_zero_is_one():
    now = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    assert bh._compute_anomaly_freshness(_ts(now, 0), now) == 1.0


def test_11_freshness_age36_is_half():
    now = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    assert abs(bh._compute_anomaly_freshness(_ts(now, 36), now) - 0.5) < 0.01


def test_12_freshness_over_72h_is_zero_not_none():
    """Push aelter als 72h -> 0.0 (legit-leer), NICHT None."""
    now = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    v = bh._compute_anomaly_freshness(_ts(now, 80), now)
    assert v == 0.0, f"erwartet 0.0, bekam {v}"
    assert v is not None


def test_13_freshness_no_ts_is_none():
    """Kein Push-ts -> None (Ticker nie gepusht / unparsebar)."""
    now = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    assert bh._compute_anomaly_freshness(None, now) is None
    assert bh._compute_anomaly_freshness("", now) is None
    assert bh._compute_anomaly_freshness("garbage", now) is None


# ── 5) Integration: _build_backtest_extension end-to-end ──────────────────


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


def test_14_integration_score_delta_from_sparkline():
    ext = _build(_baseline_stock([50.0, 57.0]))
    assert ext["score_delta_t1"] == 7.0, ext["score_delta_t1"]


def test_15_integration_score_delta_none_without_sparkline():
    ext = _build(_baseline_stock(None))
    assert ext["score_delta_t1"] is None


def test_16_integration_freshness_from_push_map():
    now = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    ext = _build(_baseline_stock([50.0, 57.0]),
                 push_map={"TEST": _ts(now, 0)}, now=now)
    assert ext["anomaly_freshness"] == 1.0, ext["anomaly_freshness"]


def test_17_integration_freshness_none_when_ticker_absent():
    now = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    ext = _build(_baseline_stock([50.0, 57.0]),
                 push_map={"OTHER": _ts(now, 0)}, now=now)
    assert ext["anomaly_freshness"] is None


def test_18_integration_both_keys_present():
    ext = _build(_baseline_stock([50.0, 57.0]))
    assert "score_delta_t1" in ext and "anomaly_freshness" in ext
    assert ext["backtest_schema_version"] == 4


# ── 6) S10-Auto-Detect findet die zwei Felder NICHT als unbekannt ─────────


def test_19_s10_auto_detect_does_not_warn():
    import health_check as hc
    entry = {
        "date": "21.05.2026", "ticker": "TEST", "score": 70.0,
        "entry_price": 10.0, "short_float": 25.0, "dtc": 5.0, "rvol": 2.4,
        "si_trend": "up", "backtest_schema_version": 4,
        "short_float_source": "yfinance", "si_trend_source": "finra",
        "score_struct": 30, "score_catalyst": 20, "score_timing": 25,
        "score_raw": 68.0, "combo_bonus": 5.0, "finra_bonus": 0.0,
        "agent_boost_factor": 1.0, "perfect_storm_mult": 1.0,
        "score_trend_bonus": 0.0, "pool_member": True, "pool_position": 1,
        "pool_size": 20, "market_regime": "neutral", "vix_level": 18.0,
        "max_drawdown_pct": 0.0, "rvol_buildup_5d": 1.2,
        "vol_stability_5d": 0.05, "coiled_spring_score": 50.0,
        "si_trend_5d_slope": 0.10, "return_3d": 2.5, "return_5d": 4.0,
        "return_3d_t1": None, "return_5d_t1": None, "return_10d": None,
        "return_10d_t1": None, "entry_price_t1": None,
        "score_normalization_version": 1,
        "rvol_acceleration": 1.6, "uoa_atm_ratio": 12.5,
        # NEU: Shadow-Persist
        "score_delta_t1": 7.0, "anomaly_freshness": 1.0,
    }
    unknown = hc._s10_check_unknown_fields([entry])
    assert unknown == set(), (
        f"S10-Auto-Detect findet unklassifizierte Felder: {sorted(unknown)} "
        f"— score_delta_t1 + anomaly_freshness sollten in OBSERVED stehen."
    )


def main() -> int:
    tests = [
        test_01_both_in_observed_not_muss_not_lag,
        test_02_fields_in_build_backtest_extension,
        test_03_schema_version_stays_4,
        test_04_expected_keys_in_selftest,
        test_05_score_delta_normal,
        test_06_score_delta_cap_plus15,
        test_07_score_delta_cap_minus15,
        test_08_score_delta_none_below_two,
        test_09_score_delta_uses_last_two,
        test_10_freshness_age_zero_is_one,
        test_11_freshness_age36_is_half,
        test_12_freshness_over_72h_is_zero_not_none,
        test_13_freshness_no_ts_is_none,
        test_14_integration_score_delta_from_sparkline,
        test_15_integration_score_delta_none_without_sparkline,
        test_16_integration_freshness_from_push_map,
        test_17_integration_freshness_none_when_ticker_absent,
        test_18_integration_both_keys_present,
        test_19_s10_auto_detect_does_not_warn,
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
