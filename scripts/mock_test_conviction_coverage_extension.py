"""Mock-Tests fuer Conviction-Coverage-Erweiterung Phase 1 (16.05.2026).

Hintergrund: Vorbereitung fuer KI-Agent-Coverage Phase 2. Conviction-
Gating ist die Schutzwand gegen Push-Spam. Heute berechnet
apply_conviction_scores nur fuer Top-10. Watchlist-Outsider haben
kein conviction_scores[t]-Eintrag in app_data.json, der Gating-Filter
faellt fuer sie weg.

Fix: enriched-Items mit manual_personal=True, die NICHT in Top-10
sind, durch compute_earliness_pts + apply_conviction_scores schicken.
Vor- und nachgelagerte Pipelines (Top-10) unveraendert.

Tests:
  1. Source: _wl_outsiders_for_pool wird einmal gebaut (Single-
     Source-of-Truth) und sowohl von compute_earliness_pts als auch
     apply_conviction_scores genutzt
  2. Source: compute_earliness_pts wird zusaetzlich fuer Outsider-Pool
     aufgerufen
  3. Source: apply_conviction_scores wird zusaetzlich fuer Outsider-Pool
     aufgerufen
  4. Source: _conviction_scores-Sammler enthaelt Watchlist-Outsider
  5. Source: Top-10-Aufrufe sind UNVERAENDERT (gleicher Aufruf, gleiche
     Parameter)
  6. Source: Pool-Definition korrekt (manual_personal AND nicht in Top-10)
  7. Source: Edge-Case `_wl_outsiders_for_pool == []` wird abgefangen
  8. compute_conviction_score-Logik UNVERAENDERT (kein Score-Format-
     Change)
  9. Pythonisch: Pool-Berechnung (Set-Subtraction)
 10. Pythonisch: Bei missing earliness_pts → Conviction-earl_pts = 0
 11. Pythonisch: Bei vorhandenem earliness_pts → Komponente berechnet
 12. CLAUDE.md: Coverage-Sektion vorhanden
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_01_pool_built_once() -> None:
    # _wl_outsiders_for_pool wird einmal in main() gebaut (vor compute_
    # earliness_pts(top10)-Call). Doppel-Build vermeiden.
    matches = re.findall(r"_wl_outsiders_for_pool\s*=\s*\[", GR)
    assert len(matches) == 1, \
        f"_wl_outsiders_for_pool sollte einmal definiert sein, gefunden {len(matches)}"
    # _top10_tickers_for_pool als Bau-Hilfsvariable
    assert "_top10_tickers_for_pool" in GR, "Tickers-Set fehlt"


def test_02_compute_earliness_called_for_pool() -> None:
    # compute_earliness_pts(top10) UND compute_earliness_pts(_wl_outsiders_for_pool)
    assert "compute_earliness_pts(top10)" in GR, \
        "Top-10 compute_earliness_pts-Aufruf entfernt?"
    assert "compute_earliness_pts(_wl_outsiders_for_pool)" in GR, \
        "Watchlist-Outsider compute_earliness_pts-Aufruf fehlt"


def test_03_apply_conviction_called_for_pool() -> None:
    # Top-10-Aufruf UNVERAENDERT
    assert "apply_conviction_scores(top10, _anomalies_today, _vix_for_conv)" in GR
    # Pool-Aufruf — gleiche anomalies/vix
    assert "apply_conviction_scores(_wl_outsiders_for_pool," in GR, \
        "Watchlist-Outsider apply_conviction_scores-Aufruf fehlt"


def test_04_conviction_dict_collects_outsiders() -> None:
    # _conviction_scores-Sammler hat sowohl Top-10 als auch Outsider-Iteration
    # Top-10 Comprehension bleibt
    pat_top10 = r"_conviction_scores\s*=\s*\{s\[\"ticker\"\]:\s*s\.get\(\"conviction\"\)\s*for s in top10"
    assert re.search(pat_top10, GR), "Top-10 _conviction_scores-Comprehension fehlt"
    # Outsider-Loop danach
    pat_outsider = r'for _s in _wl_outsiders_for_pool:\s*\n\s*if _s\.get\("ticker"\) and _s\.get\("conviction"\):'
    assert re.search(pat_outsider, GR), "Outsider-Loop fuer _conviction_scores fehlt"


def test_05_top10_pipeline_unchanged() -> None:
    # apply_conviction_scores(top10, ...) und compute_earliness_pts(top10)
    # muessen unveraendert + an alter Stelle bleiben.
    assert "apply_conviction_scores(top10, _anomalies_today, _vix_for_conv)" in GR
    assert "compute_earliness_pts(top10)" in GR


def test_06_pool_definition_correct() -> None:
    # Pool: manual_personal AND nicht in Top-10
    block_start = GR.find("_wl_outsiders_for_pool = [")
    assert block_start > 0
    block_end = GR.find("]", block_start) + 1
    block = GR[block_start:block_end]
    assert 'c.get("manual_personal")' in block, \
        "Pool-Filter manual_personal fehlt"
    assert "_top10_tickers_for_pool" in block, "Top-10-Tickers-Subtraktion fehlt"
    assert "not in" in block, "Subtraktions-Operator fehlt"


def test_07_edge_case_empty_pool_guarded() -> None:
    # if _wl_outsiders_for_pool: vor compute_earliness_pts UND vor
    # apply_conviction_scores
    matches = re.findall(r"if _wl_outsiders_for_pool:", GR)
    assert len(matches) >= 2, \
        f"Erwarte >=2 if-Guards, gefunden {len(matches)}"


def test_08_conviction_score_logic_unchanged() -> None:
    # compute_conviction_score-Body wurde NICHT touchiert
    # (Anomaly None-Fallback, setup/earliness/anomaly/regime-Komponenten)
    func_start = GR.find("def compute_conviction_score(")
    func_end = GR.find("\ndef ", func_start + 10)
    block = GR[func_start:func_end]
    # Kern-Logik-Anker
    assert "setup_pts + earl_pts + anomaly_pts + regime_pts" in block, \
        "Conviction-Score-Komposition geaendert?"
    assert "if score >= 75:" in block, "High-Schwelle veraendert?"
    assert "if score >= 50:" in block, "Medium-Schwelle veraendert?"


# ── Pythonische Replikation ─────────────────────────────────────────────────

def _replicate_pool(enriched: list, top10_tickers: set) -> list:
    return [
        c for c in enriched
        if c.get("manual_personal")
        and c.get("ticker")
        and c.get("ticker") not in top10_tickers
    ]


def test_09_pool_replication() -> None:
    enriched = [
        {"ticker": "SKYQ", "manual_personal": False},   # Top-10 only
        {"ticker": "AMC",  "manual_personal": True},    # Outsider
        {"ticker": "IONQ", "manual_personal": True},    # Outsider
        {"ticker": "GEMI", "manual_personal": True},    # Top-10 UND watchlist → NICHT outsider
        {"ticker": "AI",   "manual_personal": True},    # Outsider (Watchlist-only)
        {"ticker": None,   "manual_personal": True},    # ungueltig
    ]
    top10_tickers = {"SKYQ", "GEMI", "PZZA"}
    pool = _replicate_pool(enriched, top10_tickers)
    assert [c["ticker"] for c in pool] == ["AMC", "IONQ", "AI"], \
        f"Pool falsch: {[c.get('ticker') for c in pool]}"


def _replicate_conviction(setup_raw, earliness_raw, anomaly_count, vix,
                           earl_max=100,
                           vix_warn=25.0, vix_pause=35.0):
    """1:1-Replik compute_conviction_score (Komponenten-Setup)."""
    setup_pts = 0 if setup_raw is None else \
        max(0, min(33, int(round((float(setup_raw) / 100.0) * 33))))
    earl_pts = 0 if earliness_raw is None else \
        max(0, min(28, int(round((float(earliness_raw) / earl_max) * 28))))
    if anomaly_count >= 2:
        anomaly_pts = 28
    elif anomaly_count == 1:
        anomaly_pts = 14
    else:
        anomaly_pts = 0
    if vix is None:
        regime_pts = 0
    else:
        v = float(vix)
        if v < vix_warn:
            regime_pts = 11
        elif v < vix_pause:
            regime_pts = 6
        else:
            regime_pts = 0
    return setup_pts + earl_pts + anomaly_pts + regime_pts


def test_10_no_earliness_caps_conviction() -> None:
    # Watchlist-Outsider ohne earliness_pts (None) → earl_pts = 0
    # → Conviction = setup + 0 + anomaly + regime
    # Test: Setup 80, no earliness, no anomaly, VIX 18 (calm) → 26 + 0 + 0 + 11 = 37
    res = _replicate_conviction(setup_raw=80, earliness_raw=None,
                                  anomaly_count=0, vix=18.0)
    assert 37 == res, f"Erwarte 37, got {res}"


def test_11_with_earliness_full_conviction() -> None:
    # Watchlist-Outsider MIT compute_earliness_pts: earliness_raw 70 (von 100)
    # → earl_pts = round(70/100 * 28) = 20
    # Setup 80 (26) + Earliness 70 (20) + Anomaly 1 (14) + VIX 18 (11) = 71
    res = _replicate_conviction(setup_raw=80, earliness_raw=70,
                                  anomaly_count=1, vix=18.0)
    assert res == 71, f"Erwarte 71, got {res}"


# ── CLAUDE.md ────────────────────────────────────────────────────────────────

def test_12_claude_md_section() -> None:
    assert "Conviction-Coverage" in CMD or "Watchlist-Outsider" in CMD, \
        "CLAUDE.md erwaehnt Coverage nicht"
    assert "Phase 1" in CMD or "Phase 2" in CMD, \
        "Phase-Bezug fehlt"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 Pool-Build einmal (Single-Source)",        test_01_pool_built_once),
        ("02 compute_earliness fuer Pool",              test_02_compute_earliness_called_for_pool),
        ("03 apply_conviction fuer Pool",               test_03_apply_conviction_called_for_pool),
        ("04 _conviction_scores sammelt Pool",          test_04_conviction_dict_collects_outsiders),
        ("05 Top-10-Pipeline UNVERAENDERT",             test_05_top10_pipeline_unchanged),
        ("06 Pool-Definition korrekt",                  test_06_pool_definition_correct),
        ("07 Edge: leerer Pool → if-Guard",             test_07_edge_case_empty_pool_guarded),
        ("08 compute_conviction_score-Logik unchanged", test_08_conviction_score_logic_unchanged),
        ("09 Pool-Replikation (Set-Subtraktion)",       test_09_pool_replication),
        ("10 No-earliness → niedrige Conviction",       test_10_no_earliness_caps_conviction),
        ("11 Mit earliness → realistische Conviction",  test_11_with_earliness_full_conviction),
        ("12 CLAUDE.md Coverage-Sektion",               test_12_claude_md_section),
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
