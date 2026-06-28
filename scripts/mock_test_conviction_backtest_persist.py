"""Mock-Tests für Conviction-Edge-Persistenz (VORWÄRTS-ERHEBUNG 28.06.2026).

Ziel: conviction_score + conviction_components als additive Felder im
backtest_history-schema_v=4, damit die Conviction-Achse (Cockpit-Donut,
≥75-Push-Gating) später edge-validierbar wird. KEIN Auswertungs-Anspruch
zum Zeitpunkt des Builds; reine Erhebung.

Verifiziert (mechanik-zentriert, kein Edge-Computing):
- _build_backtest_extension schreibt conviction_score + conviction_components,
  wenn ``s["conviction"]`` als Dict mit score + components vorhanden ist.
- Beide Felder sind None-tolerant, wenn ``s["conviction"]`` fehlt/None ist
  (kein Crash, kein KeyError) — der Reihenfolge-Tausch verhindert das im
  echten Pfad, aber der Defensive-Pfad muss trotzdem funktionieren.
- schema_version bleibt 4 (additiv, kein v4→v5-Bump → S10-Loader-Filter
  bleibt funktional).
- NICHT in S10_MUSS_FIELDS/_LAG_FIELDS/_OBSERVED_FIELDS — sonst feuert
  S10 sofort auf Alt-Einträgen ohne das Feld.
- Reihenfolge-Tausch im generate_report-Pfad (apply_conviction_scores VOR
  _append_backtest_entries) ist verifizierbar per Source-Inspektion.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Heavy-deps stubben (analog mock_test_entry_raw_twin_fields).
for _mod_name in ("yfinance", "bs4", "deep_translator", "lxml", "pandas",
                  "requests"):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)
sys.modules["yfinance"].download = lambda *a, **kw: None
sys.modules["yfinance"].Ticker = lambda *a, **kw: None

import backtest_history as bh  # noqa: E402
import config                  # noqa: E402


# ── Helper ────────────────────────────────────────────────────────────────


def _baseline_stock(conviction=None):
    s = {
        "ticker": "TEST", "score": 70.0, "score_raw": 68.0, "price": 10.0,
        "short_float": 25.0, "short_ratio": 5.0, "rel_volume": 2.4,
        "rel_volume_yesterday": 1.5, "change": 2.5, "float_shares": 1e8,
        "avg_vol_20d": 1e6, "hist_5d": [],
        "score_trend_bonus_pts": 0.0, "agent_boost_factor": 1.0,
        "finra_bonus_pts": 0.0, "short_float_source": "yfinance",
        "finra_data": {"trend": "no_data", "history": [],
                       "si_trend_source": "finra"},
        "sparkline": None,
    }
    if conviction is not None:
        s["conviction"] = conviction
    return s


def _build(stock):
    return bh._build_backtest_extension(
        stock, pool_position=1, pool_size=20, agent_signals={},
        compute_sub_scores_fn=lambda s: {"struct": 0, "catalyst": 0, "timing": 0},
        safe_float_fn=lambda v, d=0.0: float(v) if v not in (None, "") else d,
        latest_push_ts_by_ticker=None,
        now_dt=None,
    )


def _full_conviction(score=72, components=None):
    """Realistisches conviction-Dict analog apply_conviction_scores."""
    return {
        "score": score,
        "level": "high",
        "action_text": "Conviction hoch.",
        "components": components or {
            "setup": 28, "earliness": 21, "anomaly": 14, "regime": 11,
        },
    }


# ── Tests ─────────────────────────────────────────────────────────────────


def test_01_conviction_score_written_when_present():
    """Conviction-Dict mit score=72 + voller Components → conviction_score=72.0."""
    ext = _build(_baseline_stock(_full_conviction(score=72)))
    assert ext["conviction_score"] == 72.0, ext.get("conviction_score")
    assert isinstance(ext["conviction_components"], dict), \
        ext.get("conviction_components")
    assert ext["conviction_components"]["setup"] == 28
    assert ext["conviction_components"]["earliness"] == 21
    assert ext["conviction_components"]["anomaly"] == 14
    assert ext["conviction_components"]["regime"] == 11


def test_02_conviction_components_subset_of_4_keys():
    """conviction_components enthält EXAKT die 4 Komponenten-Keys."""
    ext = _build(_baseline_stock(_full_conviction()))
    cc = ext["conviction_components"]
    assert set(cc.keys()) == {"setup", "earliness", "anomaly", "regime"}, cc.keys()


def test_03_none_when_conviction_missing():
    """s ohne 'conviction'-Key → beide Felder None, kein Crash.
    Realistisch falls Reihenfolge-Tausch noch nicht griff (Defensive)."""
    ext = _build(_baseline_stock(conviction=None))
    assert ext["conviction_score"] is None, ext.get("conviction_score")
    assert ext["conviction_components"] is None, \
        ext.get("conviction_components")


def test_04_none_when_conviction_score_none():
    """conviction={'score': None, ...} → conviction_score None."""
    ext = _build(_baseline_stock({"score": None, "components": {}}))
    assert ext["conviction_score"] is None, ext.get("conviction_score")


def test_05_score_rounded_to_2_decimals():
    """conviction_score auf 2 Nachkommastellen gerundet (Persistenz-Disziplin)."""
    ext = _build(_baseline_stock(_full_conviction(score=72.3456)))
    assert ext["conviction_score"] == 72.35, ext.get("conviction_score")


def test_06_components_with_none_values_tolerated():
    """Einzelne component-Werte None bleiben None (kein Convert/Defaults)."""
    cv = _full_conviction(components={
        "setup": 30, "earliness": None, "anomaly": 14, "regime": None,
    })
    ext = _build(_baseline_stock(cv))
    cc = ext["conviction_components"]
    assert cc["setup"] == 30
    assert cc["earliness"] is None
    assert cc["anomaly"] == 14
    assert cc["regime"] is None


def test_07_components_dict_missing_falls_back_to_none():
    """conviction={'score':50} ohne 'components' → conviction_components None."""
    ext = _build(_baseline_stock({"score": 50}))
    assert ext["conviction_score"] == 50.0
    assert ext["conviction_components"] is None, \
        ext.get("conviction_components")


def test_08_schema_version_stays_4():
    """Schema bleibt v4 — additiv, KEIN Bump (S10-v4-Filter-Falle)."""
    ext = _build(_baseline_stock(_full_conviction()))
    assert ext["backtest_schema_version"] == 4, \
        ext.get("backtest_schema_version")


def test_09_s10_classification_observed_only():
    """conviction_score + conviction_components MÜSSEN in S10_OBSERVED_FIELDS
    (Whitelist bekannter Felder) — sonst feuert _s10_check_unknown_fields
    ab dem ersten neuen Record dauerhaft WARN (Guardian-Befund 28.06.).

    Gleichzeitig dürfen sie NICHT in S10_MUSS_FIELDS / _LAG_FIELDS —
    dort würde wegen der None-Belegung auf Alt-Einträgen tatsächlich ein
    false-positive feuern (legitim leere Werte bestünden den Pflicht-Check
    nicht). Präzedenz: monster_score/ki_signal_score (config.py:1284) sind
    im selben Muster genau in OBSERVED, nicht MUSS/LAG."""
    for f in ("conviction_score", "conviction_components"):
        assert f in config.S10_OBSERVED_FIELDS, (
            f"{f} fehlt in S10_OBSERVED_FIELDS — _s10_check_unknown_fields "
            "würde WARN feuern, sobald ein neuer Record das Feld trägt. "
            "Eintragen analog 'monster_score'/'ki_signal_score'.")
        assert f not in config.S10_MUSS_FIELDS, \
            f"{f} fälschlich in S10_MUSS_FIELDS (None-Belegung auf Alt-Records "\
            f"würde false-positive auslösen)"
        assert f not in config.S10_LAG_FIELDS, \
            f"{f} fälschlich in S10_LAG_FIELDS (kein Lag-Outcome sinnvoll für "\
            f"Compose-Felder)"


def test_10_reorder_apply_conviction_before_append():
    """Source-Inspektion: apply_conviction_scores(top10, ...) wird im
    generate_report.main()-Pfad VOR _append_backtest_entries(...) aufgerufen.
    Wenn die Reihenfolge wieder kippt, ist conviction_score in jedem
    Backtest-Record ab dem nächsten Daily-Run None — der Test fängt das."""
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # Suche den main()-Pipeline-Bereich (zwischen Step-3-Abschluss-Print und
    # dem Conviction-Watchlist-Outsider-Block). Beide Funktionen werden
    # mehrfach im File erwähnt (Definitionen + Tests), aber der spezifische
    # Aufruf-Patternstring "apply_conviction_scores(top10," ist eindeutig.
    pos_apply = src.find("apply_conviction_scores(top10,")
    pos_append = src.find("_n_backtest_appended = _append_backtest_entries(")
    assert pos_apply > 0, "apply_conviction_scores(top10,...) nicht gefunden"
    assert pos_append > 0, "_append_backtest_entries(...)-Aufruf nicht gefunden"
    assert pos_apply < pos_append, (
        "REIHENFOLGE BRECHEN: apply_conviction_scores(top10,...) muss VOR "
        "_append_backtest_entries(...) stehen, sonst sieht das Backtest-"
        "Schema kein s['conviction']-Feld → conviction_score=None für alle "
        f"neuen Records. Gefunden: apply@{pos_apply}, append@{pos_append}"
    )


def test_11_extension_dict_has_both_new_keys():
    """Strict-Key-Inventur: conviction_score + conviction_components stehen
    immer im Ext-Dict (auch wenn Werte None) — kein dynamisches Wegfallen."""
    ext = _build(_baseline_stock(conviction=None))
    assert "conviction_score" in ext, list(ext.keys())
    assert "conviction_components" in ext, list(ext.keys())


# ── Runner ────────────────────────────────────────────────────────────────


def main():
    tests = [
        test_01_conviction_score_written_when_present,
        test_02_conviction_components_subset_of_4_keys,
        test_03_none_when_conviction_missing,
        test_04_none_when_conviction_score_none,
        test_05_score_rounded_to_2_decimals,
        test_06_components_with_none_values_tolerated,
        test_07_components_dict_missing_falls_back_to_none,
        test_08_schema_version_stays_4,
        test_09_s10_classification_observed_only,
        test_10_reorder_apply_conviction_before_append,
        test_11_extension_dict_has_both_new_keys,
    ]
    failed = []
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, repr(e)))
            print(f"  ✗ {t.__name__}: {e!r}")
    print()
    if failed:
        print(f"{len(failed)} von {len(tests)} Tests FEHLGESCHLAGEN")
        sys.exit(1)
    print(f"{len(tests)} Tests bestanden.")


if __name__ == "__main__":
    main()
