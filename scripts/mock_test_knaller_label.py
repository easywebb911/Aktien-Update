"""Mock-Tests fuer Knaller-Trade-Label Phase 2 (16.05.2026).

Hintergrund: Knaller-Begriff war heute nur Bucket-Statistik im Backtest-
Panel. Phase 2 markiert einzelne closed_trades als Knaller-Hit oder
-Crash basierend auf der Backtest-Bucket-P90/P10-Verteilung.

Definition:
  - Knaller-Hit:   pnl_pct >= P90(return_10d) im passenden
                   entry_score_bucket UND pnl_pct >= +10% (Floor)
  - Knaller-Crash: pnl_pct <= P10(return_10d) im passenden Bucket
                   UND pnl_pct <= -10% (Floor)
  - Fallback bei n<30 im Bucket: rein absolute Schwellen
                   Hit >= +25%, Crash <= -20%

Tests:
  1. Source: _btPercentile-Helper existiert
  2. Source: _btBucketStats liefert p90/p10
  3. Source: _tjBucketRef existiert + async + cached via window
  4. Source: _tjIsKnaller mit drei Return-Werten hit/crash/null
  5. Source: _tjKnallerTooltip baut konkreten Tooltip-Text
  6. Source: window._BT_DATA wird beim _btData-Load gesetzt (Bridge)
  7. Source: renderTradeJournal nutzt bucketRef + _tjIsKnaller
  8. Source: Statistik-Zelle Knaller-Block vorhanden
  9. Source: CSS .tj-trade-knaller-hit / -crash in head.jinja
 10. Pythonisch: P90/P10 linear-interpolation (Type-7) korrekt
 11. Pythonisch: _tjIsKnaller hit-Pfad mit valid Bucket
 12. Pythonisch: _tjIsKnaller hit-Pfad Floor unterhalb P90 -> null
 13. Pythonisch: _tjIsKnaller crash-Pfad mit valid Bucket
 14. Pythonisch: _tjIsKnaller crash-Pfad Floor oberhalb P10 -> null
 15. Pythonisch: Fallback bei n<30: absolute Schwellen
 16. Pythonisch: Trade ohne entry_score_bucket -> Fallback via entry_score
 17. Pythonisch: pnl_pct null -> null
 18. Pythonisch: ref leer -> Fallback absolute Schwellen
"""
from __future__ import annotations

import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
HJ = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_01_percentile_helper_exists() -> None:
    assert "function _btPercentile(arr, p)" in GR, \
        "_btPercentile-Helper fehlt"
    assert "(p / 100) * (v.length - 1)" in GR, \
        "Linear-interpolation Pattern fehlt"


def test_02_btBucketStats_has_p90_p10() -> None:
    # Beide Schluessel im return-Dict + Berechnung via _btPercentile
    assert "p90  = _btPercentile(vals, 90)" in GR, "p90-Berechnung fehlt"
    assert "p10  = _btPercentile(vals, 10)" in GR, "p10-Berechnung fehlt"
    # Im return-Dict
    assert "med, mean, min, max, spread, p90, p10, n: vals.length" in GR


def test_03_tjBucketRef_exists() -> None:
    assert "async function _tjBucketRef()" in GR, \
        "_tjBucketRef-Helper fehlt oder nicht async"
    assert "window._TJ_BUCKET_REF" in GR, "Cache-Slot fehlt"
    assert "window._BT_DATA" in GR, "Fallback via _BT_DATA fehlt"


def test_04_tjIsKnaller_three_returns() -> None:
    assert "function _tjIsKnaller(trade, ref)" in GR
    # 'hit' / 'crash' / null als moegliche Returns
    block_start = GR.find("function _tjIsKnaller(")
    block_end = GR.find("\n}", block_start)
    block = GR[block_start:block_end]
    assert "return 'hit'" in block
    assert "return 'crash'" in block
    assert "return null" in block


def test_05_tooltip_helper_exists() -> None:
    assert "function _tjKnallerTooltip(kind, trade, ref)" in GR
    block_start = GR.find("function _tjKnallerTooltip(")
    block_end = GR.find("\n}", block_start)
    block = GR[block_start:block_end]
    assert "P90" in block
    assert "P10" in block
    assert "Floor" in block


def test_06_bt_data_bridge_set() -> None:
    # window._BT_DATA = _btData; — als Bridge zwischen Backtest-Panel und
    # Trade-Journal
    assert "window._BT_DATA = _btData" in GR


def test_07_renderTradeJournal_uses_bucketRef() -> None:
    rt_start = GR.find("async function renderTradeJournal")
    rt_end = GR.find("\n// ESC schließt Drawer", rt_start)
    block = GR[rt_start:rt_end]
    assert "await _tjBucketRef()" in block, \
        "renderTradeJournal awaited _tjBucketRef nicht"
    assert "_tjIsKnaller(t, bucketRef)" in block, \
        "Pro-Trade-Klassifikation fehlt"


def test_08_stats_cell_present() -> None:
    rt_start = GR.find("async function renderTradeJournal")
    rt_end = GR.find("\n// ESC schließt Drawer", rt_start)
    block = GR[rt_start:rt_end]
    assert "tj-stat-lbl\">Knaller" in block, "Knaller-Stat-Zelle fehlt"
    # Badge-Variante (16.05.2026): Pfeil-Marker ▲/▼ statt Emoji
    assert "▲ " in block and "▼ " in block, \
        "Stats-Block hat keine Pfeil-Marker (Badge-Variante)"
    # Trade-Liste: Badge mit Klassen + Text
    assert "tj-knaller-badge" in block, "Per-Trade-Badge fehlt"
    assert "▲ TOP 10%" in block and "▼ BOT 10%" in block, \
        "Per-Trade Badge-Text fehlt"


def test_09_css_classes_in_head_jinja() -> None:
    # Container-Akzent (Border) bleibt aus PR #172
    assert ".tj-trade-knaller-hit{" in HJ, "Hit-Container-CSS fehlt"
    assert ".tj-trade-knaller-crash{" in HJ, "Crash-Container-CSS fehlt"
    # Neue Badge-Klassen (16.05.2026): ersetzen .tj-knaller-icon
    assert ".tj-knaller-badge{" in HJ, "Badge-Basis-CSS fehlt"
    assert ".tj-knaller-hit{" in HJ, "Hit-Badge-CSS fehlt"
    assert ".tj-knaller-crash{" in HJ, "Crash-Badge-CSS fehlt"
    # Alte Icon-Klasse darf nicht mehr existieren
    assert ".tj-knaller-icon{" not in HJ, \
        "Alte Icon-Klasse noch da — sollte entfernt sein"


# ── Pythonische Replikation der Logik ────────────────────────────────────────

def _btPercentile(arr, p):
    """Replikat von _btPercentile (Type 7 linear interpolation)."""
    v = sorted(float(x) for x in arr
                if x is not None and isinstance(x, (int, float))
                and not (isinstance(x, float) and math.isnan(x)))
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    idx = (p / 100) * (len(v) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return v[lo]
    return v[lo] + (v[hi] - v[lo]) * (idx - lo)


_TJ_FLOOR_HIT   = 10
_TJ_FLOOR_CRASH = -10
_TJ_FALLBACK_HIT   = 25
_TJ_FALLBACK_CRASH = -20
_TJ_MIN_N      = 30


def _bucket_for_score(score):
    if score is None:
        return None
    s = float(score)
    if s < 50:
        return "<50"
    if s < 70:
        return "50-69"
    return "≥70"


def _tjIsKnaller(trade, ref):
    """Replikat der JS-Logik."""
    if not trade:
        return None
    pnl = trade.get("pnl_pct")
    if pnl is None or not isinstance(pnl, (int, float)):
        return None
    pnl = float(pnl)
    bucket = trade.get("entry_score_bucket")
    if not bucket:
        es = trade.get("entry_score")
        if isinstance(es, (int, float)):
            bucket = _bucket_for_score(es)
    bRef = (ref or {}).get(bucket) if bucket else None
    # Hit
    if pnl >= _TJ_FLOOR_HIT:
        if bRef and bRef.get("n_with_returns", 0) >= _TJ_MIN_N \
                and bRef.get("p90") is not None \
                and pnl >= bRef["p90"]:
            return "hit"
        if (not bRef or bRef.get("n_with_returns", 0) < _TJ_MIN_N) \
                and pnl >= _TJ_FALLBACK_HIT:
            return "hit"
    # Crash
    if pnl <= _TJ_FLOOR_CRASH:
        if bRef and bRef.get("n_with_returns", 0) >= _TJ_MIN_N \
                and bRef.get("p10") is not None \
                and pnl <= bRef["p10"]:
            return "crash"
        if (not bRef or bRef.get("n_with_returns", 0) < _TJ_MIN_N) \
                and pnl <= _TJ_FALLBACK_CRASH:
            return "crash"
    return None


def test_10_percentile_type7() -> None:
    # 10 Werte 1..10, P90 -> 9.1 (idx 8.1, interpoliert zwischen 9 und 10)
    vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert abs(_btPercentile(vals, 90) - 9.1) < 1e-9
    # P50 = 5.5
    assert abs(_btPercentile(vals, 50) - 5.5) < 1e-9
    # Empty -> None
    assert _btPercentile([], 90) is None
    # Single value -> returns itself
    assert _btPercentile([42], 90) == 42


def test_11_hit_with_valid_bucket() -> None:
    ref = {"≥70": {"n_with_returns": 118, "p90": 18.0, "p10": -8.0}}
    trade = {"pnl_pct": 28.0, "entry_score_bucket": "≥70"}
    assert _tjIsKnaller(trade, ref) == "hit"


def test_12_floor_below_p90_no_hit() -> None:
    # P90 = 18, Floor = 10, pnl = 12: pnl >= Floor aber pnl < P90 -> no hit
    ref = {"≥70": {"n_with_returns": 118, "p90": 18.0, "p10": -8.0}}
    trade = {"pnl_pct": 12.0, "entry_score_bucket": "≥70"}
    assert _tjIsKnaller(trade, ref) is None


def test_13_crash_with_valid_bucket() -> None:
    ref = {"≥70": {"n_with_returns": 118, "p90": 18.0, "p10": -8.0}}
    trade = {"pnl_pct": -15.0, "entry_score_bucket": "≥70"}
    assert _tjIsKnaller(trade, ref) == "crash"


def test_14_crash_above_p10_no_crash() -> None:
    # P10 = -8, Floor = -10, pnl = -9: pnl > Floor (= keine Crash-Pruefung)
    ref = {"≥70": {"n_with_returns": 118, "p90": 18.0, "p10": -8.0}}
    trade = {"pnl_pct": -9.0, "entry_score_bucket": "≥70"}
    assert _tjIsKnaller(trade, ref) is None


def test_15_fallback_when_bucket_too_small() -> None:
    # Bucket existiert aber n<30 -> Fallback-Schwelle 25
    ref = {"<50": {"n_with_returns": 5, "p90": 50.0, "p10": -50.0}}
    # pnl=20 < 25 -> no hit trotz P90=50
    trade1 = {"pnl_pct": 20.0, "entry_score_bucket": "<50"}
    assert _tjIsKnaller(trade1, ref) is None
    # pnl=30 >= 25 -> hit (Fallback)
    trade2 = {"pnl_pct": 30.0, "entry_score_bucket": "<50"}
    assert _tjIsKnaller(trade2, ref) == "hit"
    # pnl=-25 <= -20 -> crash (Fallback)
    trade3 = {"pnl_pct": -25.0, "entry_score_bucket": "<50"}
    assert _tjIsKnaller(trade3, ref) == "crash"


def test_16_bucket_from_entry_score() -> None:
    # entry_score_bucket fehlt, aber entry_score=75 -> "≥70"
    ref = {"≥70": {"n_with_returns": 118, "p90": 18.0, "p10": -8.0}}
    trade = {"pnl_pct": 25.0, "entry_score": 75}
    assert _tjIsKnaller(trade, ref) == "hit"


def test_17_pnl_none_returns_null() -> None:
    ref = {"≥70": {"n_with_returns": 118, "p90": 18.0, "p10": -8.0}}
    assert _tjIsKnaller({"pnl_pct": None, "entry_score_bucket": "≥70"}, ref) is None
    assert _tjIsKnaller({"entry_score_bucket": "≥70"}, ref) is None


def test_18_empty_ref_falls_back() -> None:
    # Kein bucket-Ref vorhanden -> komplett auf Fallback
    trade1 = {"pnl_pct": 30.0, "entry_score_bucket": "≥70"}
    assert _tjIsKnaller(trade1, {}) == "hit"
    trade2 = {"pnl_pct": -25.0, "entry_score_bucket": "≥70"}
    assert _tjIsKnaller(trade2, {}) == "crash"
    trade3 = {"pnl_pct": 15.0, "entry_score_bucket": "≥70"}
    assert _tjIsKnaller(trade3, {}) is None   # < Fallback-Schwelle 25


# ── CLAUDE.md ────────────────────────────────────────────────────────────────

def test_19_claude_md_section() -> None:
    assert "Knaller-Trade-Label" in CMD or "Knaller-Hit" in CMD, \
        "Knaller-Sektion fehlt in CLAUDE.md"
    assert "P90" in CMD or "Top 10%" in CMD, "Definition fehlt"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 _btPercentile-Helper existiert",               test_01_percentile_helper_exists),
        ("02 _btBucketStats liefert p90/p10",               test_02_btBucketStats_has_p90_p10),
        ("03 _tjBucketRef async + window-Cache",            test_03_tjBucketRef_exists),
        ("04 _tjIsKnaller hit/crash/null",                  test_04_tjIsKnaller_three_returns),
        ("05 _tjKnallerTooltip baut konkreten Text",        test_05_tooltip_helper_exists),
        ("06 window._BT_DATA Bridge gesetzt",               test_06_bt_data_bridge_set),
        ("07 renderTradeJournal nutzt bucketRef",           test_07_renderTradeJournal_uses_bucketRef),
        ("08 Knaller-Stat-Zelle vorhanden",                 test_08_stats_cell_present),
        ("09 CSS-Klassen in head.jinja",                    test_09_css_classes_in_head_jinja),
        ("10 P90/P10 Linear-interpolation Type-7",          test_10_percentile_type7),
        ("11 Hit mit valid Bucket",                         test_11_hit_with_valid_bucket),
        ("12 Floor unter P90 → kein Hit",                   test_12_floor_below_p90_no_hit),
        ("13 Crash mit valid Bucket",                       test_13_crash_with_valid_bucket),
        ("14 pnl knapp ueber P10 → kein Crash",             test_14_crash_above_p10_no_crash),
        ("15 Fallback bei n<30",                            test_15_fallback_when_bucket_too_small),
        ("16 Bucket-Fallback via entry_score",              test_16_bucket_from_entry_score),
        ("17 pnl_pct None → null",                          test_17_pnl_none_returns_null),
        ("18 leerer ref → Fallback-Schwellen",              test_18_empty_ref_falls_back),
        ("19 CLAUDE.md Knaller-Sektion",                    test_19_claude_md_section),
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
