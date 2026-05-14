"""Mock-Tests für gist-Action-Token-Routing (PR-Folge zu #149).

Hintergrund (Diagnose 14.05.2026): vier User-Aktionen, die über
gistLoad/gistSave persistieren, hatten passiven getToken()-Check
ohne _ensureToken-Routing. Symptome:
  - HIGH: Trade-Journal silent leer (User glaubt "keine Trades")
  - HIGH: Watchlist-Remove vom Drawer löschte nur Repo-Datei, ließ
    Position im Gist stehen → Geister-Position für process_exit_signals
  - MEDIUM: Watchlist-Add silent skip im Gist-Sync (lokal sichtbar
    aber kein Cross-Device-Sync, keine Position-Trigger-Snapshots)
  - MEDIUM: wlSubmitPosition/wlSubmitClose-Fehlermeldung „Token-Scope
    prüfen" obwohl echtes Problem die leere Session war

Fix:
  - Vier Action-Pfade durch _ensureToken-Wrapper:
      wlSubmitPosition, wlSubmitClose, wlAddManual, wlRemoveFromExpanded
  - Trade-Journal Display-Pfad bekommt Drei-Zustände-Routing wie
    buildPositionPanel: Token aktiv → Statistik + Liste, Session leer
    + Blob da → .gist-locked-box + _unlockFromTradeJournal-Button,
    kein Blob → bisheriger Konfig-Hinweis
  - Generische CSS-Klasse .gist-locked-box in head.jinja

Tests (Source-Inspektion + Pythonische Logik-Replikation):
  1. Jede der 4 Funktionen wrappt ihren Body in _ensureToken(...)
  2. Trade-Journal hat _hasEncryptedToken + .gist-locked-box-Render
  3. _unlockFromTradeJournal-Helper exposed auf window
  4. _unlockFromTradeJournal ruft _ensureToken + renderTradeJournal
  5. CSS .gist-locked-box + .gist-locked-msg + .gist-locked-actions
  6. _ensureToken-Orchestrator unverändert (Vorsichts-Prinzip)
  7. _unlockFromPositionPanel-Helper aus PR #149 unverändert
  8. CLAUDE.md-Pflichtcheck: keine unescapten ${...}-Vars
  9. Pythonische Replikation 3-Zustände → korrekte HTML-Klasse
 10. DOMContentLoaded-Preload bleibt silent (kein _ensureToken)
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
CSS_SRC = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")


def _extract_window_assignment(name: str) -> str:
    """Extrahiert ``window.<name> = function(...){...}`` bis zur nächsten
    Top-Level-Function-/window-Deklaration. Toleriert f-String-escaped
    ``{{...}}``-Patterns."""
    pat = re.compile(rf"window\.{re.escape(name)}\s*=\s*(?:async\s+)?function\b",
                     re.MULTILINE)
    m = pat.search(SRC)
    assert m, f"window.{name} nicht gefunden"
    start = m.start()
    rest = SRC[m.end():]
    next_decl = re.search(
        r"^\s*(?:function\s+[A-Za-z_]|window\.[A-Za-z_]\w*\s*=)",
        rest, re.MULTILINE)
    end = m.end() + next_decl.start() if next_decl else len(SRC)
    return SRC[start:end]


def _extract_function_body(name: str) -> str:
    pat = re.compile(rf"function {re.escape(name)}\([^)]*\)\s*\{{",
                     re.MULTILINE)
    m = pat.search(SRC)
    assert m, f"{name} nicht gefunden"
    start = m.start()
    rest = SRC[m.end():]
    next_decl = re.search(
        r"^\s*(?:function\s+[A-Za-z_]|window\.[A-Za-z_]\w*\s*=)",
        rest, re.MULTILINE)
    end = m.end() + next_decl.start() if next_decl else len(SRC)
    return SRC[start:end]


# === 1 — Vier Action-Pfade gewrappt =======================================

def test_wlSubmitPosition_wrapped():
    body = _extract_window_assignment("wlSubmitPosition")
    assert "_ensureToken(" in body, (
        "wlSubmitPosition ruft _ensureToken nicht — Action-Routing fehlt")
    # Wrapper-Aufruf muss VOR dem gistLoad/gistSave stehen
    idx_ensure = body.find("_ensureToken(")
    idx_save   = body.find("gistSave(")
    assert idx_ensure < idx_save, (
        f"_ensureToken muss VOR gistSave stehen: ensure@{idx_ensure} "
        f"vs save@{idx_save}")


def test_wlSubmitClose_wrapped():
    body = _extract_window_assignment("wlSubmitClose")
    assert "_ensureToken(" in body
    idx_ensure = body.find("_ensureToken(")
    idx_save   = body.find("gistSave(")
    assert idx_ensure < idx_save


def test_wlAddManual_wrapped():
    body = _extract_window_assignment("wlAddManual")
    assert "_ensureToken(" in body, (
        "wlAddManual ruft _ensureToken nicht")
    # Validierung läuft VOR _ensureToken (kein unnötiges Modal bei
    # ungültigem Ticker)
    idx_regex   = body.find("_WL_RE.test(")
    idx_ensure  = body.find("_ensureToken(")
    assert 0 <= idx_regex < idx_ensure, (
        f"Ticker-Validierung sollte vor _ensureToken laufen: "
        f"regex@{idx_regex} vs ensure@{idx_ensure}")


def test_wlRemoveFromExpanded_wrapped():
    body = _extract_window_assignment("wlRemoveFromExpanded")
    assert "_ensureToken(" in body
    # confirm() läuft VOR _ensureToken — sonst Modal-Spawn ohne User-Intent
    idx_confirm = body.find("confirm(")
    idx_ensure  = body.find("_ensureToken(")
    assert 0 <= idx_confirm < idx_ensure


# === 2 — Trade-Journal Drei-Zustände-Routing ==============================

def test_trade_journal_has_locked_state():
    body = _extract_function_body("renderTradeJournal")
    assert "_hasEncryptedToken" in body, (
        "renderTradeJournal hat kein _hasEncryptedToken-Check — "
        "Drei-Zustände-Routing fehlt")
    assert "gist-locked-box" in body, (
        "renderTradeJournal rendert keine .gist-locked-box")
    assert "_unlockFromTradeJournal" in body, (
        "Unlock-Button verweist nicht auf _unlockFromTradeJournal")
    assert "verschl" in body, (
        "Locked-State-Text 'verschlüsselt' fehlt")


def test_trade_journal_locked_state_returns_early():
    """Locked-State-Block muss MIT return enden, damit gistLoad
    nicht trotzdem läuft (würde 401 produzieren)."""
    body = _extract_function_body("renderTradeJournal")
    m = re.search(
        r"if\s*\(\s*!_tokNow\s*&&\s*_hasEnc\s*\)\s*\{\{(.*?)\}\}",
        body, re.DOTALL,
    )
    assert m, "Locked-State-Block nicht parsbar"
    block = m.group(1)
    assert "return;" in block, (
        "Locked-State-Block hat kein early-return — Code fällt durch zu "
        "gistLoad")


# === 3 — _unlockFromTradeJournal-Helper ===================================

def test_unlock_tradejournal_helper_exposed():
    assert "window._unlockFromTradeJournal" in SRC, (
        "_unlockFromTradeJournal nicht auf window — inline-onclick "
        "kann den Helper nicht aufrufen")


def test_unlock_tradejournal_helper_routes_through_ensure_token():
    # Helper wird via window.… = function gesetzt, daher zwei Patterns.
    m = re.search(
        r"window\._unlockFromTradeJournal\s*=\s*function\([^)]*\)\s*"
        r"\{\{(.*?)\}\};",
        SRC, re.DOTALL,
    )
    assert m, "_unlockFromTradeJournal-Helper nicht gefunden"
    body = m.group(1)
    assert "_ensureToken" in body, (
        "Unlock-Helper ruft _ensureToken nicht")
    assert "renderTradeJournal" in body, (
        "Unlock-Helper ruft renderTradeJournal nicht nach Success")


# === 4 — CSS-Klassen =====================================================

def test_css_classes_present():
    assert ".gist-locked-box" in CSS_SRC, (
        ".gist-locked-box-CSS fehlt in head.jinja")
    assert ".gist-locked-msg" in CSS_SRC, (
        ".gist-locked-msg-CSS fehlt")
    assert ".gist-locked-actions" in CSS_SRC, (
        ".gist-locked-actions-CSS fehlt")


# === 5 — _ensureToken-Orchestrator unverändert ============================

def test_ensure_token_orchestrator_intact():
    """Strikt: PR darf _ensureToken nicht modifizieren (Vorsichts-Prinzip)."""
    body = _extract_function_body("_ensureToken")
    assert "_hasEncryptedToken()" in body
    assert "tok-modal-unlock" in body
    assert "tok-modal-setup" in body
    assert "tok-modal-migrate" in body


# === 6 — PR #149 Position-Panel-Locked-State unverändert =================

def test_position_panel_locked_state_intact():
    """Strikt: dieser PR darf PR #149 nicht versehentlich brechen."""
    assert "window._unlockFromPositionPanel" in SRC, (
        "_unlockFromPositionPanel von PR #149 ist verschwunden")
    assert ".position-panel-locked" in CSS_SRC, (
        "PR #149 CSS-Klasse weg")


# === 7 — gistLoad/gistSave selbst unverändert (defensive catch-net) ======

def test_gistLoad_inner_check_intact():
    body = _extract_function_body("gistLoad")
    # Innerer Token-Skip muss als defensive catch-net bestehen bleiben
    assert "if (!token) return null" in body, (
        "gistLoad innerer Token-Guard versehentlich entfernt")


def test_gistSave_inner_check_intact():
    body = _extract_function_body("gistSave")
    assert "if (!token)" in body, (
        "gistSave innerer Token-Guard versehentlich entfernt")


# === 8 — DOMContentLoaded-Preload bleibt silent ===========================

def test_dom_content_loaded_preload_silent():
    """gistLoad()-Preload im DOMContentLoaded-Listener darf KEIN
    _ensureToken-Routing haben — passiv ist die Spec."""
    m = re.search(
        r"DOMContentLoaded.*?gistLoad\(\)\.catch\(",
        SRC, re.DOTALL,
    )
    assert m, "DOMContentLoaded-gistLoad-Preload nicht gefunden"
    # Im 200-Zeichen-Kontext um den Preload sollte kein _ensureToken sein
    ctx = SRC[max(0, m.start() - 200):m.end() + 200]
    # _ensureToken kommt im weiteren JS-Block vor — hier nur prüfen, dass
    # der Preload-Aufruf selbst NICHT in einem _ensureToken-Wrapper sitzt.
    preload_idx = ctx.find("gistLoad().catch(")
    assert preload_idx > 0
    # 80 Zeichen vor dem Preload-Aufruf — wenn _ensureToken da steht,
    # wäre der Preload gewrappt.
    pre_window = ctx[max(0, preload_idx - 80):preload_idx]
    assert "_ensureToken(" not in pre_window, (
        "DOMContentLoaded-Preload wurde versehentlich gewrappt — "
        "soll silent bleiben")


# === 9 — Pythonische Replikation der 3 Zustände ===========================

def _render_state(has_session_token: bool, has_blob: bool,
                  has_gist_load: bool = True) -> str:
    """Replikation der renderTradeJournal-Routing-Logik (ohne DOM)."""
    if not has_gist_load:
        return "no-gist"
    if not has_session_token and has_blob:
        return "locked"
    return "active"


def test_state_token_present():
    assert _render_state(True, True)  == "active"
    assert _render_state(True, False) == "active"


def test_state_locked_blob_only():
    assert _render_state(False, True) == "locked"


def test_state_no_gist_function():
    assert _render_state(False, False, has_gist_load=False) == "no-gist"


# === 10 — Pflichtcheck ====================================================

def test_no_unescaped_js_template_vars():
    hits = re.findall(r"\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}", SRC)
    assert not hits, f"Unescapte JS-Template-Vars: {hits[:5]}"


# === Runner =================================================================

def main() -> None:
    tests = [
        # Action-Pfade
        ("wlSubmitPosition durch _ensureToken gewrappt",
         test_wlSubmitPosition_wrapped),
        ("wlSubmitClose durch _ensureToken gewrappt",
         test_wlSubmitClose_wrapped),
        ("wlAddManual durch _ensureToken gewrappt (nach Validierung)",
         test_wlAddManual_wrapped),
        ("wlRemoveFromExpanded durch _ensureToken gewrappt (nach confirm)",
         test_wlRemoveFromExpanded_wrapped),
        # Trade-Journal Display-Pfad
        ("renderTradeJournal: _hasEncryptedToken + Locked-Box-Render",
         test_trade_journal_has_locked_state),
        ("Locked-State-Block returnt early",
         test_trade_journal_locked_state_returns_early),
        ("_unlockFromTradeJournal auf window exposed",
         test_unlock_tradejournal_helper_exposed),
        ("_unlockFromTradeJournal ruft _ensureToken + renderTradeJournal",
         test_unlock_tradejournal_helper_routes_through_ensure_token),
        # CSS
        ("CSS .gist-locked-box/-msg/-actions in head.jinja",
         test_css_classes_present),
        # Unveränderbar
        ("_ensureToken unverändert (Vorsichts-Prinzip)",
         test_ensure_token_orchestrator_intact),
        ("PR #149 Position-Panel-Locked-State unverändert",
         test_position_panel_locked_state_intact),
        ("gistLoad innerer Token-Guard catch-net erhalten",
         test_gistLoad_inner_check_intact),
        ("gistSave innerer Token-Guard catch-net erhalten",
         test_gistSave_inner_check_intact),
        # Silent-Pfad
        ("DOMContentLoaded-Preload bleibt silent",
         test_dom_content_loaded_preload_silent),
        # Pythonische Replikation
        ("3-Zustände: Token vorhanden", test_state_token_present),
        ("3-Zustände: Locked (Blob, Session leer)",
         test_state_locked_blob_only),
        ("3-Zustände: Kein Gist (Konfig-Hinweis)",
         test_state_no_gist_function),
        # Pflichtcheck
        ("Keine unescapten ${...} im f-String",
         test_no_unescaped_js_template_vars),
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
