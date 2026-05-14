"""Mock-Tests für buildPositionPanel Locked-State (Token-Session abgelaufen).

Hintergrund (Diagnose 14.05.2026): buildPositionPanel machte einen
passiven getToken()-Check ohne _hasEncryptedToken()-Fallback. Auf
iOS-Safari nach Tab-Restart ist sessionStorage leer, aber das
encrypted Blob liegt im localStorage. Resultat: „Token fehlt"-Fehler
auf der Watchlist-Karte, obwohl der User nur Master-Passwort eingeben
müsste. Latenter Bug seit PR #125.

Fix: Drei-Zustände-Routing —
  1. Token aktiv → Panel rendert normal
  2. Token leer + Blob da → Locked-State mit Unlock-Button
  3. Token leer + kein Blob → bisheriger „Token fehlt"-Pfad

Plus Helper _unlockFromPositionPanel(ticker) → _ensureToken →
_refreshPositionPanel (Single-Source-of-Truth, Unlock-Modal kommt
automatisch).

Tests (Source-Inspektion + Logik-Replikation):
  1. buildPositionPanel hat einen _hasEncryptedToken-Check
  2. Locked-State rendert position-panel-locked + pos-btn-unlock
  3. Disabled-State (kein Blob) bleibt erhalten
  4. _unlockFromPositionPanel ruft _ensureToken + _refreshPositionPanel
  5. CSS-Klassen .position-panel-locked + .pos-btn-unlock in head.jinja
  6. Pythonische Replikation: 3 Zustände → korrekte HTML-Klasse
  7. Helper ist auf window exposed (für inline-onclick)
  8. _ensureToken-Orchestrator unverändert (Vorsichts-Prinzip)
  9. CLAUDE.md-Pflichtcheck: keine unescapten ${...}-Vars
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
CSS_SRC = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")


def _extract_function_body(name: str) -> str:
    """Extrahiert Funktions-Body bis zur nächsten Top-Level- oder Inner-
    Function-Deklaration (`function …` / `window.… = function`). Toleriert
    f-String-escaped `{{...}}`-Patterns."""
    start_pat = re.compile(
        rf"function {re.escape(name)}\([^)]*\)\s*\{{",
        re.MULTILINE,
    )
    m = start_pat.search(SRC)
    assert m, f"{name} nicht gefunden"
    start = m.start()
    rest = SRC[m.end():]
    next_decl = re.search(r"^\s*(?:function\s+[A-Za-z_]|window\.[A-Za-z_]\w*\s*=)",
                          rest, re.MULTILINE)
    end = m.end() + next_decl.start() if next_decl else len(SRC)
    return SRC[start:end]


# === 1 — buildPositionPanel hat den neuen Check ===========================

def test_panel_checks_has_encrypted_token():
    body = _extract_function_body("buildPositionPanel")
    assert "_hasEncryptedToken" in body, (
        "buildPositionPanel fragt nicht _hasEncryptedToken — der Drei-"
        "Zustände-Routing-Fix fehlt")


# === 2 — Locked-State-HTML ================================================

def test_locked_state_renders_unlock_button():
    body = _extract_function_body("buildPositionPanel")
    assert "position-panel-locked" in body, (
        "Locked-State-CSS-Klasse fehlt im Render")
    assert "pos-btn-unlock" in body, "Unlock-Button-CSS-Klasse fehlt"
    assert "_unlockFromPositionPanel" in body, (
        "Unlock-Button ruft _unlockFromPositionPanel nicht auf")
    assert "Token-Session abgelaufen" in body, (
        "User-sichtbarer Locked-State-Text fehlt")


# === 3 — Disabled-State (kein Blob) bleibt erhalten =======================

def test_disabled_state_unchanged():
    body = _extract_function_body("buildPositionPanel")
    assert "position-panel-disabled" in body
    assert "Token fehlt — Position-Tracking ben" in body, (
        "Ursprüngliche Token-fehlt-Meldung wurde entfernt — der Pfad "
        "für 'kein Blob, kein Token' muss erhalten bleiben")


# === 4 — _unlockFromPositionPanel ruft _ensureToken =======================

def test_unlock_helper_routes_through_ensure_token():
    # Helper wird via window.… = function gesetzt, daher zwei Patterns.
    helper_pat = re.compile(
        r"window\._unlockFromPositionPanel\s*=\s*function\([^)]*\)\s*\{\{(.*?)\}\};",
        re.DOTALL,
    )
    m = helper_pat.search(SRC)
    assert m, "_unlockFromPositionPanel-Helper nicht gefunden"
    body = m.group(1)
    assert "_ensureToken" in body, (
        "Unlock-Helper ruft _ensureToken nicht — Unlock-Modal-Routing fehlt")
    assert "_refreshPositionPanel" in body, (
        "Unlock-Helper refresht das Panel nach Success nicht")


# === 5 — CSS-Klassen in head.jinja ========================================

def test_css_classes_present():
    assert ".position-panel-locked" in CSS_SRC, (
        ".position-panel-locked-CSS fehlt in head.jinja")
    assert ".pos-btn-unlock" in CSS_SRC, (
        ".pos-btn-unlock-CSS fehlt in head.jinja")


# === 6 — Pythonische Replikation der 3 Zustände ===========================

def _render_state(has_session_token: bool, has_blob: bool, has_gist_id: bool) -> str:
    """Replikation der buildPositionPanel-Routing-Logik (ohne DOM)."""
    if not has_gist_id:
        return "disabled-no-gist"
    if not has_session_token:
        if has_blob:
            return "locked"
        return "disabled-no-token"
    return "active"


def test_state_token_present():
    assert _render_state(True, True, True)  == "active"
    assert _render_state(True, False, True) == "active"


def test_state_locked_blob_only():
    assert _render_state(False, True, True) == "locked"


def test_state_disabled_no_token():
    assert _render_state(False, False, True) == "disabled-no-token"


def test_state_disabled_no_gist():
    assert _render_state(False, True, False) == "disabled-no-gist"
    assert _render_state(True, True, False)  == "disabled-no-gist"


# === 7 — Helper auf window exposed ========================================

def test_unlock_helper_on_window():
    assert "window._unlockFromPositionPanel" in SRC, (
        "_unlockFromPositionPanel ist nicht auf window — inline-onclick "
        "kann den Helper nicht aufrufen")


# === 8 — _ensureToken-Orchestrator unverändert ============================

def test_ensure_token_orchestrator_intact():
    """Strikt: PR darf _ensureToken nicht modifizieren (Vorsichts-Prinzip)."""
    body = _extract_function_body("_ensureToken")
    # Original-Pfad-Marker müssen erhalten sein
    assert "_hasEncryptedToken()" in body
    assert "tok-modal-unlock" in body
    assert "tok-modal-setup" in body
    assert "tok-modal-migrate" in body


# === 9 — Pflichtcheck =====================================================

def test_no_unescaped_js_template_vars():
    hits = re.findall(r"\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}", SRC)
    assert not hits, f"Unescapte JS-Template-Vars: {hits[:5]}"


# === 10 — DOM-Smoke: HTML-Snippet für Locked-State validierbar ===========

def test_locked_html_snippet_well_formed():
    """Locked-State-HTML soll vier Elemente enthalten: div.position-panel-locked,
    p.pos-msg, div.pos-actions, button.pos-btn-unlock — exakt 1× jeweils."""
    body = _extract_function_body("buildPositionPanel")
    # Locked-Block extrahieren
    m = re.search(
        r"_hasEncryptedToken\(\).*?return\s*`(<div class=\"position-panel position-panel-locked\".+?</div>)`",
        body, re.DOTALL,
    )
    assert m, "Locked-HTML-Block nicht parsbar"
    snippet = m.group(1)
    # Element-Count
    for tag in ('class="position-panel position-panel-locked"',
                'class="pos-msg"',
                'class="pos-actions"',
                'class="pos-btn pos-btn-unlock"'):
        assert snippet.count(tag) == 1, (
            f"{tag!r} sollte genau 1× vorkommen, got {snippet.count(tag)}")


# === Runner =================================================================

def main() -> None:
    tests = [
        ("buildPositionPanel: _hasEncryptedToken-Check vorhanden",
         test_panel_checks_has_encrypted_token),
        ("Locked-State rendert Unlock-Button + CSS-Klassen",
         test_locked_state_renders_unlock_button),
        ("Disabled-State (kein Blob) unverändert",
         test_disabled_state_unchanged),
        ("_unlockFromPositionPanel: _ensureToken + _refreshPositionPanel",
         test_unlock_helper_routes_through_ensure_token),
        ("CSS .position-panel-locked + .pos-btn-unlock",
         test_css_classes_present),
        ("3-Zustände-Replikation: Token vorhanden",
         test_state_token_present),
        ("3-Zustände-Replikation: Locked (Blob da, Session leer)",
         test_state_locked_blob_only),
        ("3-Zustände-Replikation: Disabled (kein Token, kein Blob)",
         test_state_disabled_no_token),
        ("3-Zustände-Replikation: Disabled (Gist nicht konfiguriert)",
         test_state_disabled_no_gist),
        ("Helper auf window exposed (inline-onclick-kompatibel)",
         test_unlock_helper_on_window),
        ("_ensureToken unverändert (Vorsichts-Prinzip)",
         test_ensure_token_orchestrator_intact),
        ("Keine unescapten ${...} im f-String",
         test_no_unescaped_js_template_vars),
        ("Locked-HTML-Snippet wohlgeformt",
         test_locked_html_snippet_well_formed),
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
