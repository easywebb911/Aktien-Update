"""Mock-Tests fuer Entry-Score-Persistenz-Vorarbeit (21.05.2026).

Zwei neue Felder in _build_backtest_extension:
- rvol_acceleration = rel_volume / rel_volume_yesterday  (Division-Guard)
- uoa_atm_ratio aus agent_signals[ticker].uoa_atm_ratio

Beide LEGITIM-leer-tolerant (None erlaubt) — bewusst NICHT in S10_MUSS_FIELDS,
nur in S10_OBSERVED_FIELDS (sonst false-positive WARN bei legitim-None-Faellen).

Pattern: Source-Inspektion + Funktional-Tests via _build_backtest_extension
direkt (yfinance-Import nicht noetig — die Funktion ist pure).

Ausfuehrung: ``python3 scripts/mock_test_entry_score_persistence.py``.
"""
from __future__ import annotations

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Drittlib-Stubs fuer die Test-Sandbox (im GH-Actions-Env existieren alle
# via requirements.txt; dort greift der Stub nicht, weil sys.modules sie
# schon hat). Die Test-Funktionen rufen nur _build_backtest_extension auf —
# das macht selbst keinen Drittlib-Call. Stubs sind reine Import-Token.
for _mod_name in ("yfinance", "bs4", "deep_translator", "lxml", "pandas"):
    if _mod_name not in sys.modules:
        _stub = types.ModuleType(_mod_name)
        sys.modules[_mod_name] = _stub

# yfinance.Ticker + .download / bs4.BeautifulSoup / deep_translator.GoogleTranslator
# werden bei generate_report-Top-Level-Import via `from`-Statement abgegriffen
# und brauchen Attribute auf dem Stub-Modul.
sys.modules["yfinance"].download = lambda *a, **kw: None
sys.modules["yfinance"].Ticker = lambda *a, **kw: None
sys.modules["bs4"].BeautifulSoup = lambda *a, **kw: None
sys.modules["deep_translator"].GoogleTranslator = lambda *a, **kw: type(
    "T", (), {"translate": staticmethod(lambda s: s)}
)()


# ── 1) Klassifikation ─────────────────────────────────────────────────────


def test_01_both_in_observed_not_muss_not_lag():
    """Beide Felder sind LEGITIM-leer-tolerant — nur OBSERVED, nicht
    MUSS, nicht LAG. Sonst false-positive WARN beim ersten Daily-Run."""
    import config
    for field in ("rvol_acceleration", "uoa_atm_ratio"):
        assert field in config.S10_OBSERVED_FIELDS, (
            f"{field} fehlt in S10_OBSERVED_FIELDS — Auto-Detect wuerde "
            f"WARN ausloesen am ersten Daily-Run nach Merge."
        )
        assert field not in config.S10_MUSS_FIELDS, (
            f"{field} darf NICHT in S10_MUSS_FIELDS — es ist legitim oft "
            f"None (rvol_acceleration bei fehlendem Vortagswert, "
            f"uoa_atm_ratio bei nicht-monitored Tickern)."
        )
        assert field not in config.S10_LAG_FIELDS, (
            f"{field} darf NICHT in S10_LAG_FIELDS — kein LAG-Outcome-Feld."
        )


# ── 2) Source-Inspektion: Felder im Extension-Return ──────────────────────


def test_02_fields_in_build_backtest_extension():
    """generate_report._build_backtest_extension schreibt beide Felder."""
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    import re
    fn_match = re.search(
        r"def _build_backtest_extension\(.*?(?=^def |\Z)",
        src, re.MULTILINE | re.DOTALL,
    )
    assert fn_match, "_build_backtest_extension nicht gefunden"
    body = fn_match.group(0)
    assert '"rvol_acceleration":' in body, (
        "_build_backtest_extension schreibt rvol_acceleration nicht."
    )
    assert '"uoa_atm_ratio":' in body, (
        "_build_backtest_extension schreibt uoa_atm_ratio nicht."
    )


def test_03_uoa_uses_sig_lookup():
    """uoa_atm_ratio wird aus dem `sig`-Dict gelesen (agent_signals-Pfad)."""
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    assert 'sig.get("uoa_atm_ratio")' in src, (
        "uoa_atm_ratio sollte via sig.get aus agent_signals geholt werden."
    )


def test_04_expected_keys_in_selftest_updated():
    """Der _test_extended_schema-Selbsttest in generate_report.py muss die
    zwei neuen Keys in expected_keys auflisten, sonst schlaegt der
    Set-Vergleich beim Selbsttest fehl."""
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # Suche im _test_extended_schema-Body
    import re
    fn_match = re.search(
        r"def _test_extended_schema\(.*?(?=^def |\Z)",
        src, re.MULTILINE | re.DOTALL,
    )
    assert fn_match
    body = fn_match.group(0)
    for key in ("rvol_acceleration", "uoa_atm_ratio"):
        assert f'"{key}"' in body, (
            f"_test_extended_schema:expected_keys muss {key!r} enthalten."
        )


# ── 3) Funktionale Tests via _build_backtest_extension direkt ─────────────


def _full_baseline_stock(rel_vol=2.4, rel_vol_yest=1.5):
    """Stock-Dict mit allen Pflicht-Feldern fuer _build_backtest_extension."""
    return {
        "ticker":         "TEST",
        "score":          70.0,
        "score_raw":      68.0,
        "price":          10.0,
        "short_float":    25.0,
        "short_ratio":    5.0,
        "rel_volume":     rel_vol,
        "rel_volume_yesterday": rel_vol_yest,
        "change":         2.5,
        "float_shares":   100_000_000,
        "avg_vol_20d":    1_000_000,
        "hist_5d":        [],   # leer → Trend-Helper liefern None
        "score_trend_bonus_pts": 0.0,
        "agent_boost_factor":    1.0,
        "finra_bonus_pts":       0.0,
        "short_float_source":    "yfinance",
        "finra_data": {"trend": "no_data", "history": [],
                        "si_trend_source": "finra"},
    }


def test_05_rvol_acceleration_normal_case():
    """Beide Werte > 0 → Division, gerundet auf 3 Nachkommastellen."""
    import generate_report as g
    stock = _full_baseline_stock(rel_vol=2.4, rel_vol_yest=1.5)
    ext = g._build_backtest_extension(stock, pool_position=3, pool_size=20,
                                       agent_signals={})
    assert ext["rvol_acceleration"] == round(2.4 / 1.5, 3), (
        f"erwartet {round(2.4/1.5, 3)}, bekam {ext['rvol_acceleration']}"
    )


def test_06_rvol_acceleration_yesterday_zero_yields_none():
    """Division-Guard: rel_volume_yesterday = 0 → None (kein Crash)."""
    import generate_report as g
    stock = _full_baseline_stock(rel_vol=2.4, rel_vol_yest=0.0)
    ext = g._build_backtest_extension(stock, pool_position=1, pool_size=20,
                                       agent_signals={})
    assert ext["rvol_acceleration"] is None, (
        f"Division durch 0 muss None liefern, bekam {ext['rvol_acceleration']}"
    )


def test_07_rvol_acceleration_yesterday_none_yields_none():
    """rel_volume_yesterday = None → None (frischer Ticker, kein Vortagswert)."""
    import generate_report as g
    stock = _full_baseline_stock()
    stock["rel_volume_yesterday"] = None
    ext = g._build_backtest_extension(stock, pool_position=1, pool_size=20,
                                       agent_signals={})
    assert ext["rvol_acceleration"] is None


def test_08_rvol_acceleration_rel_volume_zero_yields_none():
    """rel_volume = 0 → None (defensive)."""
    import generate_report as g
    stock = _full_baseline_stock(rel_vol=0.0, rel_vol_yest=1.5)
    ext = g._build_backtest_extension(stock, pool_position=1, pool_size=20,
                                       agent_signals={})
    assert ext["rvol_acceleration"] is None


def test_09_uoa_atm_ratio_from_agent_signals():
    """uoa_atm_ratio wird aus agent_signals[ticker] gelesen."""
    import generate_report as g
    stock = _full_baseline_stock()
    sigs = {"TEST": {"uoa_atm_ratio": 12.5, "combo_mult": 1.0}}
    ext = g._build_backtest_extension(stock, pool_position=1, pool_size=20,
                                       agent_signals=sigs)
    assert ext["uoa_atm_ratio"] == 12.5, (
        f"erwartet 12.5, bekam {ext['uoa_atm_ratio']}"
    )


def test_10_uoa_atm_ratio_missing_signal_yields_none():
    """Kein agent_signals-Eintrag fuer den Ticker → uoa_atm_ratio = None."""
    import generate_report as g
    stock = _full_baseline_stock()
    ext = g._build_backtest_extension(stock, pool_position=1, pool_size=20,
                                       agent_signals={})
    assert ext["uoa_atm_ratio"] is None


def test_11_uoa_atm_ratio_signal_without_uoa_field_yields_none():
    """agent_signals-Eintrag ohne uoa_atm_ratio-Key → None."""
    import generate_report as g
    stock = _full_baseline_stock()
    sigs = {"TEST": {"combo_mult": 1.0}}  # kein uoa_atm_ratio
    ext = g._build_backtest_extension(stock, pool_position=1, pool_size=20,
                                       agent_signals=sigs)
    assert ext["uoa_atm_ratio"] is None


def test_12_schema_version_unchanged():
    """Schema-Bump unterbleibt: backtest_schema_version bleibt 4
    (additiv-only Welle, kein Bruch)."""
    import generate_report as g
    stock = _full_baseline_stock()
    ext = g._build_backtest_extension(stock, pool_position=1, pool_size=20,
                                       agent_signals={})
    assert ext["backtest_schema_version"] == 4, (
        "backtest_schema_version darf nicht hochgezaehlt werden — additiv."
    )


# ── 4) Integration: S10-Auto-Detect findet die zwei Felder NICHT als unbekannt


def test_13_s10_auto_detect_does_not_warn():
    """End-to-End: V4-Eintrag mit den zwei neuen Feldern loest KEINEN
    Auto-Detect-WARN aus."""
    import health_check as hc
    entry = {
        "date": "21.05.2026", "ticker": "TEST",
        "backtest_schema_version": 4,
        "score": 70.0, "entry_price": 10.0,
        "rvol": 2.4, "dtc": 5.0, "short_float": 25.0,
        "si_trend": "up", "short_float_source": "yfinance",
        "si_trend_source": "finra",
        "score_struct": 30.0, "score_catalyst": 5.0, "score_timing": 20.0,
        "score_raw": 68.0, "combo_bonus": 0.0, "finra_bonus": 0.0,
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
        "score_normalization_version": 1,
        # NEU: Entry-Score-Vorarbeit
        "rvol_acceleration": 1.6,
        "uoa_atm_ratio": 12.5,
    }
    unknown = hc._s10_check_unknown_fields([entry])
    assert unknown == set(), (
        f"S10-Auto-Detect findet unklassifizierte Felder: {sorted(unknown)} "
        f"— rvol_acceleration und uoa_atm_ratio sollten in OBSERVED stehen."
    )


# ── 5) Existierender Selbsttest in generate_report.py laeuft durch ─────────


def test_14_extended_schema_selftest_runs():
    """g._test_extended_schema laeuft ohne AssertionError (Set-Vergleich
    muss die neuen Keys jetzt enthalten)."""
    import generate_report as g
    g._test_extended_schema()   # raises bei expected_keys-Mismatch


def main() -> int:
    tests = [
        test_01_both_in_observed_not_muss_not_lag,
        test_02_fields_in_build_backtest_extension,
        test_03_uoa_uses_sig_lookup,
        test_04_expected_keys_in_selftest_updated,
        test_05_rvol_acceleration_normal_case,
        test_06_rvol_acceleration_yesterday_zero_yields_none,
        test_07_rvol_acceleration_yesterday_none_yields_none,
        test_08_rvol_acceleration_rel_volume_zero_yields_none,
        test_09_uoa_atm_ratio_from_agent_signals,
        test_10_uoa_atm_ratio_missing_signal_yields_none,
        test_11_uoa_atm_ratio_signal_without_uoa_field_yields_none,
        test_12_schema_version_unchanged,
        test_13_s10_auto_detect_does_not_warn,
        test_14_extended_schema_selftest_runs,
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
