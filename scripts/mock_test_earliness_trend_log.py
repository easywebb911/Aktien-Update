"""Mock-Tests für Earliness-Trend-Logging (Backtest-Schema v4).

Hintergrund: PR „Earliness-Trend-Logging" loggt vier prospektive
Sub-Signale (`si_trend_5d_slope`, `rvol_buildup_5d`, `vol_stability_5d`,
`coiled_spring_score`) pro neuem `backtest_history.json`-Eintrag. Reines
Logging — kein Conviction-/Score-Effekt. Validierungs-Pfad: nach
14–30 Tagen Live-Daten AUC-Vergleich gegen `return_10d`.

Tests:
  1. _compute_si_slope_5d: ≥5 Punkte → Slope; < 5 → None;
     si_old ≤ 0 → None; positiver / negativer / Null-Slope
  2. _compute_rvol_buildup_5d: ≥5 Volumes → Quotient; < 5 → None;
     avg_vol_20d ≤ 0 → None; Division-by-zero → None
  3. _compute_vol_stability_5d: ≥5 Werte je Liste → ATR-Ratio;
     < 5 → None; avg_close ≤ 0 → None
  4. _compute_coiled_spring_score: beide Eingaben → 0..100;
     None → None; negativer Slope → 0-Beitrag; Caps wirksam
  5. Edge-Cases: alle None / leere Listen / Typ-Fehler

Ausführung: ``python scripts/mock_test_earliness_trend_log.py``.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# === Source-Extraktion =====================================================

# Die vier Earliness-Trend-Helper UND _build_backtest_extension wurden
# 23.05.2026 nach backtest_history.py extrahiert (Helper-Refactor) →
# Source-Inspektion dieser folgt dem Umzug (``src``). _hist_stats + sein
# Caller + der _test_extended_schema-Selbsttest blieben in generate_report.py
# (``src_gr``).
src = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
src_gr = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _extract(func_def: str) -> str:
    pat = rf"^def {re.escape(func_def)}\([\s\S]+?(?=^def\s|^class\s|^# ====)"
    m = re.search(pat, src, re.MULTILINE)
    assert m, f"{func_def} nicht in backtest_history.py gefunden"
    return m.group(0)


helpers_src = (
    _extract("_finite")
    + "\n"
    + _extract("_compute_si_slope_5d")
    + "\n"
    + _extract("_compute_rvol_buildup_5d")
    + "\n"
    + _extract("_compute_vol_stability_5d")
    + "\n"
    + _extract("_compute_coiled_spring_score")
)


ns: dict = {}
exec(
    "import math\n"
    "from config import (\n"
    "    EARLINESS_TREND_LOG_WINDOW_DAYS,\n"
    "    EARLINESS_TREND_MIN_FINRA_POINTS,\n"
    "    EARLINESS_TREND_SI_SLOPE_CAP,\n"
    "    EARLINESS_TREND_VOL_STAB_CAP,\n"
    ")\n"
    + helpers_src,
    ns,
)
_si_slope        = ns["_compute_si_slope_5d"]
_rvol_buildup    = ns["_compute_rvol_buildup_5d"]
_vol_stability   = ns["_compute_vol_stability_5d"]
_coiled_spring   = ns["_compute_coiled_spring_score"]


# === 1 — _compute_si_slope_5d ==============================================

def test_si_slope_positive():
    """Aufbauender SI-Trend: 500 → 600 (alt) ... 1000 (neu) → > 0."""
    hist = [
        {"short_interest": 1000},
        {"short_interest":  900},
        {"short_interest":  800},
        {"short_interest":  700},
        {"short_interest":  500},   # ältester
    ]
    slope = _si_slope(hist)
    assert slope is not None and slope > 0, slope
    # (1000 - 500) / 500 = 1.0
    assert slope == 1.0, slope


def test_si_slope_negative():
    """Abnehmender SI-Trend → negativer Slope."""
    hist = [
        {"short_interest": 500},
        {"short_interest": 600},
        {"short_interest": 700},
        {"short_interest": 800},
        {"short_interest": 1000},   # ältester
    ]
    slope = _si_slope(hist)
    # (500 - 1000) / 1000 = -0.5
    assert slope == -0.5, slope


def test_si_slope_zero():
    """Konstanter SI → Slope 0."""
    hist = [{"short_interest": 1000}] * 5
    assert _si_slope(hist) == 0.0


def test_si_slope_insufficient_data():
    """< 5 Punkte → None."""
    assert _si_slope([]) is None
    assert _si_slope(None) is None
    assert _si_slope([{"short_interest": 100}] * 4) is None


def test_si_slope_zero_old_value():
    """si_old == 0 → None (Division durch null verhindert)."""
    hist = [
        {"short_interest": 100},
        {"short_interest":  80},
        {"short_interest":  50},
        {"short_interest":  10},
        {"short_interest":   0},   # ältester
    ]
    assert _si_slope(hist) is None


def test_si_slope_missing_keys_graceful():
    """Fehlende short_interest-Keys → 0-Default → si_old=0 → None."""
    hist = [{}] * 5
    assert _si_slope(hist) is None


# === 2 — _compute_rvol_buildup_5d ==========================================

def test_rvol_buildup_increasing():
    """Volumen baut auf: erste 2 Tage niedrig, letzte 3 hoch."""
    # avg_vol_20d = 1M, volumes_5d = [500k, 500k, 2M, 2M, 2M]
    # early_avg = 500k → rvol_early = 0.5
    # late_avg  = 2M   → rvol_late  = 2.0
    # buildup = 2.0 / 0.5 = 4.0
    result = _rvol_buildup([500_000, 500_000, 2_000_000, 2_000_000, 2_000_000], 1_000_000)
    assert result == 4.0, result


def test_rvol_buildup_decreasing():
    """Volumen abnehmend → buildup < 1."""
    # volumes_5d = [2M, 2M, 500k, 500k, 500k]
    # early_avg = 2M → rvol_early = 2.0
    # late_avg  = 500k → rvol_late  = 0.5
    # buildup = 0.5 / 2.0 = 0.25
    result = _rvol_buildup([2_000_000, 2_000_000, 500_000, 500_000, 500_000], 1_000_000)
    assert result == 0.25, result


def test_rvol_buildup_constant():
    """Konstantes Volumen → buildup = 1.0."""
    assert _rvol_buildup([1_000_000] * 5, 1_000_000) == 1.0


def test_rvol_buildup_insufficient_data():
    """< 5 Volumes → None."""
    assert _rvol_buildup([], 1_000_000) is None
    assert _rvol_buildup(None, 1_000_000) is None
    assert _rvol_buildup([100_000] * 4, 1_000_000) is None


def test_rvol_buildup_zero_avg_vol():
    """avg_vol_20d ≤ 0 → None (Division-by-zero verhindert)."""
    assert _rvol_buildup([100_000] * 5, 0) is None
    assert _rvol_buildup([100_000] * 5, -100) is None
    assert _rvol_buildup([100_000] * 5, None) is None


def test_rvol_buildup_zero_early_volumes():
    """Erste 2 Tage 0 → rvol_early = 0 → Division-by-zero → None."""
    assert _rvol_buildup([0, 0, 1_000_000, 1_000_000, 1_000_000], 1_000_000) is None


def test_rvol_buildup_garbage_types():
    """Strings in der Liste → TypeError abgefangen → None."""
    assert _rvol_buildup(["a", "b", "c", "d", "e"], 1_000_000) is None


# === 3 — _compute_vol_stability_5d =========================================

def test_vol_stability_compressed():
    """Niedrige Range = stabil (z.B. 1 % bei avg_close 100)."""
    # ranges = [1, 1, 1, 1, 1] (immer 1$ Range pro Tag)
    # atr = 1, avg_close = 100 → stability = 0.01
    highs  = [100.5] * 5
    lows   = [ 99.5] * 5
    closes = [100.0] * 5
    assert _vol_stability(highs, lows, closes) == 0.01


def test_vol_stability_volatile():
    """Hohe Range = volatil (z.B. 20 % bei avg_close 100)."""
    highs  = [110.0] * 5
    lows   = [ 90.0] * 5
    closes = [100.0] * 5
    # range = 20, atr = 20, avg_close = 100 → 0.20
    assert _vol_stability(highs, lows, closes) == 0.2


def test_vol_stability_insufficient_data():
    """< 5 Werte → None."""
    assert _vol_stability([], [], []) is None
    assert _vol_stability(None, None, None) is None
    assert _vol_stability([100] * 4, [99] * 4, [99.5] * 4) is None


def test_vol_stability_zero_avg_close():
    """avg_close ≤ 0 → None."""
    assert _vol_stability([1] * 5, [0] * 5, [0] * 5) is None


def test_vol_stability_garbage_types():
    """Strings → TypeError abgefangen → None."""
    assert _vol_stability(["a"]*5, ["b"]*5, ["c"]*5) is None


# === 4 — _compute_coiled_spring_score ======================================

def test_coiled_spring_perfect():
    """Vol-Stab = 0 (perfekt stabil) + Slope = 0.20 (max) → 100."""
    # stability_inv = 1 - min(0, 0.10)/0.10 = 1.0
    # slope_norm    = min(0.20, 0.20)/0.20 = 1.0
    # → 100
    assert _coiled_spring(0.0, 0.20) == 100.0


def test_coiled_spring_high_vol_low_slope():
    """Hohe Volatilität (≥ Cap 10%) → stability_inv = 0 → Score = 0."""
    assert _coiled_spring(0.15, 0.10) == 0.0


def test_coiled_spring_negative_slope():
    """Negativer Slope → slope_norm = 0 → Score = 0 (kein Aufbau)."""
    assert _coiled_spring(0.02, -0.10) == 0.0


def test_coiled_spring_middle():
    """Mid-Case: Stab 5 % (stability_inv = 0.5) + Slope 10 % (slope_norm = 0.5)
    → 0.5 × 0.5 × 100 = 25.0
    """
    assert _coiled_spring(0.05, 0.10) == 25.0


def test_coiled_spring_caps_applied():
    """Wert über Cap wird gecappt — nicht überschießen."""
    # Slope > Cap → wird auf Cap gecappt (slope_norm = 1.0)
    assert _coiled_spring(0.0, 0.50) == 100.0
    # Stability > Cap → stability_inv = 0
    assert _coiled_spring(0.50, 0.20) == 0.0


def test_coiled_spring_none_inputs():
    """None-Eingaben → None."""
    assert _coiled_spring(None, 0.10) is None
    assert _coiled_spring(0.05, None) is None
    assert _coiled_spring(None, None) is None


# === 4b — NaN-Härtung (15.08.2026, Wurzel-Fix-PR) ==========================
#
# Diagnose 15.08.2026 belegte: die drei Guards unten prüften vorher nur
# "<= 0" bzw. "is None" — beide Formen lassen NaN durch (nan <= 0 und
# nan is None sind beide False). Der Coiled-Spring-Fall war der
# insidiöseste: max(0.0, 1.0 - min(nan, cap)/cap) löst sich zu 0.0 auf —
# ein STILLER Fake-Wert statt eines ehrlichen None. Diese Tests belegen
# NaN-Eingang -> None (nicht 0.0), UND separat, dass ein echter finiter
# Eingang, der legitim 0.0 ergibt, weiterhin 0.0 liefert — die beiden
# dürfen nie verschmelzen.

def test_rvol_buildup_nan_volume_element_returns_none():
    """NaN in EINEM der 5 Volumes -> None (nicht bis in round() propagiert)."""
    volumes = [500_000, 500_000, float("nan"), 2_000_000, 2_000_000]
    assert _rvol_buildup(volumes, 1_000_000) is None


def test_rvol_buildup_nan_avg_vol_20d_returns_none():
    """NaN als avg_vol_20d (z.B. aus s.get('avg_vol_20d') or 0 mit NaN-
    Input) -> None. Alter Guard war 'avg_vol_20d <= 0' (nan <= 0 = False)."""
    assert _rvol_buildup([1_000_000] * 5, float("nan")) is None


def test_rvol_buildup_inf_volume_element_returns_none():
    """Inf ist ebenfalls nicht-endlich — _finite() faengt beide gleich."""
    volumes = [500_000, 500_000, float("inf"), 2_000_000, 2_000_000]
    assert _rvol_buildup(volumes, 1_000_000) is None


def test_vol_stability_nan_in_highs_returns_none():
    highs  = [float("nan"), 100.5, 100.5, 100.5, 100.5]
    lows   = [99.5] * 5
    closes = [100.0] * 5
    assert _vol_stability(highs, lows, closes) is None


def test_vol_stability_nan_in_lows_returns_none():
    highs  = [100.5] * 5
    lows   = [99.5, 99.5, float("nan"), 99.5, 99.5]
    closes = [100.0] * 5
    assert _vol_stability(highs, lows, closes) is None


def test_vol_stability_nan_in_closes_returns_none():
    highs  = [100.5] * 5
    lows   = [99.5] * 5
    closes = [100.0, 100.0, 100.0, 100.0, float("nan")]
    assert _vol_stability(highs, lows, closes) is None


def test_coiled_spring_nan_vol_stability_returns_none_not_zero():
    """KRITISCH — die eigentliche Regression: vorher loeste sich
    max(0.0, 1.0 - min(nan, cap)/cap) zu 0.0 auf (stiller Fake-Wert).
    Nach dem Fix muss NaN als Eingang None liefern."""
    result = _coiled_spring(float("nan"), 0.20)
    assert result is None, f"NaN-vol_stability muss None ergeben, nicht {result!r}"


def test_coiled_spring_nan_si_slope_returns_none_not_zero():
    """Dieselbe Haertung fuer den zweiten Eingang."""
    result = _coiled_spring(0.02, float("nan"))
    assert result is None, f"NaN-si_slope muss None ergeben, nicht {result!r}"


def test_coiled_spring_inf_inputs_return_none():
    assert _coiled_spring(float("inf"), 0.20) is None
    assert _coiled_spring(0.02, float("-inf")) is None


def test_coiled_spring_real_zero_output_never_confused_with_nan_input():
    """GEGENPROBE (darf mit dem NaN-Fall NIE verschmelzen): ein echter,
    endlicher Eingang, der legitim auf Output 0.0 fuehrt (hohe
    Volatilitaet ODER negativer Slope), bleibt 0.0 -- NICHT None. Das
    ist dieselbe Rechnung wie test_coiled_spring_high_vol_low_slope /
    test_coiled_spring_negative_slope, hier explizit als Gegenprobe zur
    NaN->None-Haertung benannt: 0.0 (echtes Ergebnis) und None
    (unbenutzbarer Eingang) sind zwei verschiedene, nie zu vermengende
    Zustaende."""
    real_zero_high_vol = _coiled_spring(0.15, 0.10)
    real_zero_neg_slope = _coiled_spring(0.02, -0.10)
    assert real_zero_high_vol == 0.0 and real_zero_high_vol is not None
    assert real_zero_neg_slope == 0.0 and real_zero_neg_slope is not None
    assert _coiled_spring(float("nan"), 0.10) is None


def test_source_hardened_with_finite_not_only_le_zero():
    """Quelltext-Deckung: die drei Compute-Helper rufen jetzt _finite()
    auf ihren Eingaengen, nicht mehr nur '<= 0'/'is None' allein."""
    assert "not _finite(avg_vol_20d)" in src
    assert "not all(_finite(v) for v in volumes_5d)" in src
    assert "not all(_finite(v) for v in highs_5d)" in src
    assert "not all(_finite(v) for v in lows_5d)" in src
    assert "not all(_finite(v) for v in closes_5d)" in src
    assert "not _finite(vol_stability) or not _finite(si_slope)" in src


# === 5 — Integration: Schema-Selbsttest in generate_report.py ==============

def test_extended_schema_includes_trend_fields():
    """``_test_extended_schema`` (Selbsttest in generate_report.py) muss
    die neuen Keys in seinem expected_keys-Set haben — ohne yfinance-
    Import, daher Source-Inspektion."""
    for key in ("si_trend_5d_slope", "rvol_buildup_5d",
                "vol_stability_5d", "coiled_spring_score",
                "backtest_schema_version"):
        assert f'"{key}"' in src_gr, (
            f"Selbsttest in generate_report.py erwartet {key!r} nicht — "
            f"_test_extended_schema:expected_keys ergänzen")


def test_build_backtest_extension_writes_trend_fields():
    """Source-Smoke: _build_backtest_extension setzt die 5 neuen Keys
    und ruft die 4 Helper auf."""
    assert "_compute_si_slope_5d(finra_hist)" in src
    assert "_compute_rvol_buildup_5d(volumes_5d, avg_vol_20)" in src
    assert "_compute_vol_stability_5d(highs_5d, lows_5d, closes_5d)" in src
    assert "_compute_coiled_spring_score(vol_stability, si_slope_5d)" in src
    assert '"backtest_schema_version": 4' in src


def test_hist_stats_returns_15_elements():
    """_hist_stats returnt jetzt 15-Tupel (hist_5d + close_5td_before_entry
    am Ende). Caller muss entsprechend auspacken.

    Erweiterung 05.07.2026 (Hypothese-A-Vorbau Stufe A): tail-Element
    close_5td_before_entry für _compute_entry_past_return_5d in
    _build_backtest_extension.
    """
    # Default-Return: 13 None/0.0 + leere Liste + None (close_5td_before_entry)
    assert "0.0, 0.0, 0.0, None, None, None, None, None, None, None, None, None, None, [], None" in src_gr, (
        "_hist_stats default-return wurde nicht um close_5td_before_entry "
        "am Ende erweitert")
    # Caller-Auspack-Stelle muss hist_5d UND close_5td_before_entry enthalten
    assert "cur_close, hist_5d, close_5td_before_entry = _hist_stats(ticker)" in src_gr, (
        "_hist_stats-Caller wurde nicht um close_5td_before_entry erweitert")
    # Stock-Dict bekommt s["hist_5d"] UND s["close_5td_before_entry"]
    assert '"hist_5d":        hist_5d,' in src_gr, (
        "Stock-Dict bekommt kein hist_5d-Feld vom Caller")
    assert '"close_5td_before_entry": close_5td_before_entry,' in src_gr, (
        "Stock-Dict bekommt kein close_5td_before_entry-Feld vom Caller")


# === Runner =================================================================

def main() -> None:
    tests = [
        # _compute_si_slope_5d
        ("si_slope: positiver Trend → > 0",             test_si_slope_positive),
        ("si_slope: negativer Trend → < 0",             test_si_slope_negative),
        ("si_slope: konstanter Trend → 0",              test_si_slope_zero),
        ("si_slope: < 5 Punkte → None",                  test_si_slope_insufficient_data),
        ("si_slope: si_old == 0 → None",                 test_si_slope_zero_old_value),
        ("si_slope: fehlende Keys → None",               test_si_slope_missing_keys_graceful),
        # _compute_rvol_buildup_5d
        ("rvol_buildup: steigend → > 1",                 test_rvol_buildup_increasing),
        ("rvol_buildup: abnehmend → < 1",                test_rvol_buildup_decreasing),
        ("rvol_buildup: konstant → 1.0",                 test_rvol_buildup_constant),
        ("rvol_buildup: < 5 Werte → None",                test_rvol_buildup_insufficient_data),
        ("rvol_buildup: avg_vol_20d ≤ 0 → None",          test_rvol_buildup_zero_avg_vol),
        ("rvol_buildup: erste 2 Tage 0 → None",           test_rvol_buildup_zero_early_volumes),
        ("rvol_buildup: garbage types → None",            test_rvol_buildup_garbage_types),
        # _compute_vol_stability_5d
        ("vol_stability: kompromierte Range",             test_vol_stability_compressed),
        ("vol_stability: volatile Range",                 test_vol_stability_volatile),
        ("vol_stability: < 5 Werte → None",                test_vol_stability_insufficient_data),
        ("vol_stability: avg_close ≤ 0 → None",            test_vol_stability_zero_avg_close),
        ("vol_stability: garbage types → None",            test_vol_stability_garbage_types),
        # _compute_coiled_spring_score
        ("coiled_spring: perfekt (stab=0, slope=cap)",     test_coiled_spring_perfect),
        ("coiled_spring: hohe Volatilität → 0",            test_coiled_spring_high_vol_low_slope),
        ("coiled_spring: negativer Slope → 0",             test_coiled_spring_negative_slope),
        ("coiled_spring: mid-Case 25.0",                   test_coiled_spring_middle),
        ("coiled_spring: Caps wirksam",                    test_coiled_spring_caps_applied),
        ("coiled_spring: None-Eingaben → None",            test_coiled_spring_none_inputs),
        # NaN-Härtung (15.08.2026)
        ("rvol_buildup: NaN-Volume-Element → None",         test_rvol_buildup_nan_volume_element_returns_none),
        ("rvol_buildup: NaN-avg_vol_20d → None",            test_rvol_buildup_nan_avg_vol_20d_returns_none),
        ("rvol_buildup: Inf-Volume-Element → None",         test_rvol_buildup_inf_volume_element_returns_none),
        ("vol_stability: NaN in highs → None",              test_vol_stability_nan_in_highs_returns_none),
        ("vol_stability: NaN in lows → None",               test_vol_stability_nan_in_lows_returns_none),
        ("vol_stability: NaN in closes → None",             test_vol_stability_nan_in_closes_returns_none),
        ("coiled_spring: NaN-vol_stability → None (KRITISCH)", test_coiled_spring_nan_vol_stability_returns_none_not_zero),
        ("coiled_spring: NaN-si_slope → None (KRITISCH)",   test_coiled_spring_nan_si_slope_returns_none_not_zero),
        ("coiled_spring: Inf-Eingaben → None",              test_coiled_spring_inf_inputs_return_none),
        ("coiled_spring: echte 0.0 ≠ NaN→None (Gegenprobe)", test_coiled_spring_real_zero_output_never_confused_with_nan_input),
        ("Quelltext: _finite()-Härtung in allen 3 Helpern",  test_source_hardened_with_finite_not_only_le_zero),
        # Integration
        ("Selbsttest expected_keys enthält Trend-Felder",  test_extended_schema_includes_trend_fields),
        ("_build_backtest_extension ruft Helper auf",      test_build_backtest_extension_writes_trend_fields),
        ("_hist_stats returnt 15-Tupel + Caller updated",  test_hist_stats_returns_15_elements),
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
