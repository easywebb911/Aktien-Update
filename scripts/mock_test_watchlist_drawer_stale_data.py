"""Mock-Tests für Watchlist-Drawer Stale-Data Fix Phase 1 (Stufe 1 + 2a).

Phase 1 adressiert zwei Symptome aus heutigem Diagnose-Bericht:

  Stufe 1: dataset.loaded-Cache-Gate in wlExpand blockierte Drawer-Re-
           Render nach erstem Open — Drawer zeigte eingefrorene HTML
           während Top-10-Fliesen live-Updates bekamen.

  Stufe 2a: Nach ki_agent-Trigger-Success wurde _WL_CARDS NICHT neu
           zugewiesen, offene Drawer behielten Stale-Daten beim
           nächsten Open.

Da der Watchlist-Drawer-Code rein clientseitig in JS lebt und nicht
ohne Browser-DOM lauffähig ist, verifizieren wir die Mechanik per
Source-Inspektion auf generate_report.py (analog Pattern aus
mock_test_token_reentry_fix.py).

Ausführung: ``python scripts/mock_test_watchlist_drawer_stale_data.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _gr_source() -> str:
    return (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _wlexpand_body() -> str:
    """Extrahiert den wlExpand-Funktions-Body grob (von der Funktion bis
    zum nächsten Marker)."""
    src = _gr_source()
    # Definition: ``window.wlExpand = function(ticker, btn) { ... }``.
    m = re.search(r"window\.wlExpand\s*=\s*function[\s\S]{0,3500}",
                  src)
    assert m, "wlExpand-Funktion im Source nicht gefunden"
    return m.group(0)


def _ki_agent_success_body() -> str:
    """Extrahiert die _kiAgentSuccess-Funktion grob."""
    src = _gr_source()
    m = re.search(r"function _kiAgentSuccess[\s\S]*?_enableKiBtn\(\);",
                  src)
    assert m, "_kiAgentSuccess-Funktion nicht gefunden"
    return m.group(0)


# === Stufe 1 — Cache-Gate entfernt =========================================

def test_no_early_return_cache_gate():
    """Der frühere ``if (body.dataset.loaded) { …; return; }``-Early-
    Return-Block ist entfernt. Wir prüfen, dass kein ``return``-Statement
    direkt aus einem ``if (body.dataset.loaded)``-Block folgt."""
    body = _wlexpand_body()
    # Pattern: `if (body.dataset.loaded) { ... return; }`  — multi-line ok
    bad = re.search(r"if\s*\(\s*body\.dataset\.loaded\s*\)\s*\{\{[^}]*?return\s*;",
                    body, re.DOTALL)
    assert not bad, (
        "wlExpand hat noch einen dataset.loaded-Early-Return — Cache-Gate "
        f"nicht entfernt. Match: {bad.group(0)[:200]}")


def test_dataset_loaded_marker_still_set():
    """``data-loaded='1'`` wird WEITERHIN gesetzt nach erfolgreichem Open
    — dient als ``[data-loaded]``-Selektor-Marker für Stufe 2a."""
    body = _wlexpand_body()
    assert "body.dataset.loaded = '1'" in body, (
        "data-loaded-Marker fehlt — Stufe 2a-Selektor kann offene "
        "Drawer nicht mehr finden")


def test_buildwl_details_called_on_every_open():
    """``buildWlDetails(ticker, d)`` wird im Open-Pfad aufgerufen
    (Sparkline-only-Fallback bleibt für ticker ohne d)."""
    body = _wlexpand_body()
    assert "buildWlDetails(ticker, d)" in body, (
        "buildWlDetails-Aufruf im Open-Pfad fehlt")
    assert "buildWlSparkOnly(ticker, WL_HIST[ticker])" in body, (
        "buildWlSparkOnly-Fallback fehlt")


def test_sparkline_redraw_runs_unconditionally():
    """Sparkline-Re-Render läuft NACH dem Re-Render (kein eigener
    Cache-Pfad mehr)."""
    body = _wlexpand_body()
    # Pattern: querySelectorAll('.spark-wrap').forEach(... drawSparkline(w) ...)
    assert re.search(
        r"body\.querySelectorAll\('\.spark-wrap'\)\.forEach\([\s\S]*?drawSparkline",
        body), "Sparkline-Re-Render im Open-Pfad fehlt"


# === Stufe 2a — ki_agent-Success-Pfad =====================================

def test_kiagent_success_reassigns_wl_cards():
    """Nach erfolgreichem ki_agent-Tick-Fetch wird ``window._WL_CARDS``
    aus ``appData.watchlist_cards`` neu zugewiesen — Fallback ``{}``
    bei null/undefined."""
    body = _ki_agent_success_body()
    assert "window._WL_CARDS = appData.watchlist_cards" in body, (
        "_WL_CARDS-Re-Assign fehlt nach ki_agent-Fetch")
    # Fallback-Pattern
    assert re.search(
        r"appData\.watchlist_cards\s*\|\|\s*\{\{\s*\}\}",
        body), "Fallback `|| {}` für null watchlist_cards fehlt"


def test_kiagent_success_invalidates_open_drawers():
    """``[data-loaded]``-Selektor findet alle offenen Drawer und
    räumt das Attribut. delete b.dataset.loaded ist idempotent."""
    body = _ki_agent_success_body()
    assert re.search(
        r"querySelectorAll\('\.wl-body\[data-loaded\]'\)",
        body), "[data-loaded]-Selektor fehlt — offene Drawer werden nicht invalidiert"
    assert "delete b.dataset.loaded" in body, (
        "delete-Mechanik für data-loaded fehlt")


def test_kiagent_success_order_wl_cards_first_then_render():
    """Reihenfolge im _kiAgentSuccess-Handler: erst _WL_CARDS-Re-Assign,
    dann data-loaded-Invalidation, dann renderAgentSignals — sonst
    sieht renderAgentSignals stale Daten."""
    body = _ki_agent_success_body()
    pos_reassign = body.find("window._WL_CARDS = appData.watchlist_cards")
    pos_invalidate = body.find("delete b.dataset.loaded")
    pos_render = body.find("renderAgentSignals(data)")
    assert pos_reassign >= 0 and pos_invalidate >= 0 and pos_render >= 0, (
        f"Eine der drei Stellen fehlt: reassign={pos_reassign}, "
        f"invalidate={pos_invalidate}, render={pos_render}")
    assert pos_reassign < pos_invalidate < pos_render, (
        f"Reihenfolge falsch — erwartet reassign({pos_reassign}) < "
        f"invalidate({pos_invalidate}) < render({pos_render})")


# === Bonus — Initial Page-Load-Fetch bleibt unverändert ===================

def test_initial_page_load_fetch_unchanged():
    """Der Initial-Fetch beim Page-Load (Z. ~9320) belegt _WL_CARDS
    bereits — wir verifizieren, dass der weiterhin existiert und nicht
    versehentlich entfernt wurde."""
    src = _gr_source()
    # Mindestens zwei Stellen, die window._WL_CARDS zuweisen:
    # 1. Initial-Fetch (DOMContentLoaded)
    # 2. ki_agent-Success-Fetch (Stufe 2a, neu)
    n = src.count("window._WL_CARDS = appData.watchlist_cards")
    assert n >= 2, (
        f"Erwartet ≥ 2 _WL_CARDS-Re-Assigns (Initial + ki_agent-Success), "
        f"gefunden: {n}")


# === Robustheit — Defensive Patterns =======================================

def test_null_watchlist_cards_fallback_empty_object():
    """Bei appData.watchlist_cards = null darf kein Crash entstehen —
    Fallback auf leeres Objekt."""
    src = _gr_source()
    # Beide Re-Assign-Stellen müssen das Fallback haben
    matches = re.findall(
        r"window\._WL_CARDS\s*=\s*appData\.watchlist_cards\s*\|\|\s*\{\{\s*\}\}",
        src)
    assert len(matches) >= 2, (
        f"Beide _WL_CARDS-Re-Assigns brauchen `|| {{}}`-Fallback "
        f"(gefunden: {len(matches)})")


# === Runner ================================================================

def main():
    tests = [
        ("Stufe 1: kein dataset.loaded-Early-Return mehr",   test_no_early_return_cache_gate),
        ("Stufe 1: dataset.loaded-Marker bleibt für 2a",     test_dataset_loaded_marker_still_set),
        ("Stufe 1: buildWlDetails wird bei jedem Open aufg.", test_buildwl_details_called_on_every_open),
        ("Stufe 1: Sparkline-Redraw unconditional",          test_sparkline_redraw_runs_unconditionally),
        ("Stufe 2a: _WL_CARDS-Re-Assign nach ki_agent",      test_kiagent_success_reassigns_wl_cards),
        ("Stufe 2a: offene Drawer werden invalidiert",       test_kiagent_success_invalidates_open_drawers),
        ("Stufe 2a: Reihenfolge reassign → invalid → render", test_kiagent_success_order_wl_cards_first_then_render),
        ("Initial Page-Load-Fetch unverändert",              test_initial_page_load_fetch_unchanged),
        ("Robustheit: null-Fallback `|| {}`",                test_null_watchlist_cards_fallback_empty_object),
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
