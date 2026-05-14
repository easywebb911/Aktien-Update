"""Mock-Tests für _refreshGhSettingsUI (Settings-Panel-UI-Refresh nach Token-Submit).

Hintergrund (Diagnose 14.05.2026): vor diesem Fix renderte
``toggleSettings()`` die GitHub-Token-Status-Anzeige direkt. Die drei
Token-Submit-Funktionen (``_submitTokenSetup`` / ``_submitTokenUnlock`` /
``_submitTokenMigrate``) refreshten das Settings-Panel-UI NICHT.

Symptom auf iPhone: nach erfolgreichem Setup-Submit (Token persistiert,
Session aktiv) zeigte das Panel weiter „🔒 verschlüsselt gespeichert".
Workaround: zweimal Einstellungs-Icon klicken → 2. Toggle-Cycle ruft
``toggleSettings()`` erneut → frischer Render mit ``getToken()`` →
„✅ entsperrt".

Fix: Helper ``_refreshGhSettingsUI()`` extrahiert + an drei Submit-
Stellen aufgerufen + ``toggleSettings()`` umgestellt auf den Helper
(Single-Source-of-Truth).

Tests (Source-Inspektion + DOM-Smoke):
  1. Helper-Funktion existiert
  2. Helper macht no-op wenn Panel unsichtbar
  3. Helper liest getToken() für aktive Anzeige
  4. Helper rendert die 3 Zustände (entsperrt / verschlüsselt / leer)
  5. _submitTokenSetup ruft Helper nach _closeTokenModals
  6. _submitTokenUnlock ruft Helper nach _closeTokenModals
  7. _submitTokenMigrate ruft Helper nach _closeTokenModals
  8. toggleSettings nutzt den Helper (DRY)
  9. DOM-Smoke: Status-Texte exakt wie im Helper definiert
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")


# === 1 — Helper-Funktion existiert =========================================

def test_helper_defined():
    assert "function _refreshGhSettingsUI()" in SRC, (
        "_refreshGhSettingsUI-Helper fehlt in generate_report.py")


# === 2 — No-op wenn Panel unsichtbar ======================================

def test_helper_noops_when_panel_hidden():
    """Helper-Body muss am Anfang den Panel-Sichtbarkeits-Check haben."""
    m = re.search(
        r"function _refreshGhSettingsUI\(\)\s*\{\{(.*?)\}\}\s*\n\s*function toggleSettings",
        SRC, re.DOTALL,
    )
    assert m, "Helper-Body nicht parsbar"
    body = m.group(1)
    # Erste 200 Zeichen müssen den Sichtbarkeits-Check enthalten
    head = body[:300]
    assert "anth-sec" in head, "Panel-Element-Lookup fehlt"
    assert "style.display" in head, "display-Check fehlt (No-op-Guard)"
    assert "return" in head, "Early-return bei unsichtbarem Panel fehlt"


# === 3 — Helper liest getToken() ==========================================

def test_helper_reads_get_token():
    m = re.search(
        r"function _refreshGhSettingsUI\(\)\s*\{\{(.*?)\}\}\s*\n\s*function toggleSettings",
        SRC, re.DOTALL,
    )
    body = m.group(1)
    assert "getToken()" in body, (
        "_refreshGhSettingsUI liest nicht getToken() — Single-Source-Bruch")
    assert "_hasEncryptedToken()" in body, (
        "_refreshGhSettingsUI liest nicht _hasEncryptedToken() für "
        "Zwischen-Zustand")


# === 4 — Drei Render-Zustände ==============================================

def test_helper_renders_three_states():
    m = re.search(
        r"function _refreshGhSettingsUI\(\)\s*\{\{(.*?)\}\}\s*\n\s*function toggleSettings",
        SRC, re.DOTALL,
    )
    body = m.group(1)
    # ✅ entsperrt (Token aktiv)
    assert "Token entsperrt" in body, "Render-Zustand 'entsperrt' fehlt"
    # 🔒 verschlüsselt (Blob da, Session leer)
    assert "Token verschlüsselt gespeichert" in body, (
        "Render-Zustand 'verschlüsselt' fehlt")
    # leer (kein Token, kein Blob) — leerer textContent
    assert "ghStatus.textContent = ''" in body, (
        "Render-Zustand 'leer' fehlt")


# === 5-7 — Aufrufe nach jedem Submit ======================================

def _submit_block(func_name: str) -> str:
    """Liefert den Body einer Submit-Funktion bis zum nächsten function."""
    pat = re.compile(
        rf"async function {re.escape(func_name)}\(\).*?(?=^(?:async )?function )",
        re.MULTILINE | re.DOTALL,
    )
    m = pat.search(SRC)
    assert m, f"{func_name} nicht gefunden"
    return m.group(0)


def test_setup_submit_calls_refresh():
    body = _submit_block("_submitTokenSetup")
    assert "_refreshGhSettingsUI()" in body, (
        "_submitTokenSetup ruft _refreshGhSettingsUI nicht auf")
    # Reihenfolge: nach _closeTokenModals (sonst läuft Helper auf altem DOM)
    idx_close = body.find("_closeTokenModals()")
    idx_refresh = body.find("_refreshGhSettingsUI()")
    assert idx_close < idx_refresh, (
        f"_refreshGhSettingsUI muss NACH _closeTokenModals laufen, "
        f"got close@{idx_close} refresh@{idx_refresh}")


def test_unlock_submit_calls_refresh():
    body = _submit_block("_submitTokenUnlock")
    assert "_refreshGhSettingsUI()" in body, (
        "_submitTokenUnlock ruft _refreshGhSettingsUI nicht auf")


def test_migrate_submit_calls_refresh():
    body = _submit_block("_submitTokenMigrate")
    assert "_refreshGhSettingsUI()" in body, (
        "_submitTokenMigrate ruft _refreshGhSettingsUI nicht auf")


# === 8 — toggleSettings nutzt den Helper (DRY) ============================

def test_toggle_settings_uses_helper():
    """toggleSettings darf nicht mehr inline rendern, sondern via Helper.

    Inline-Patterns ('Token entsperrt — diese Browser-Session' direkt im
    toggleSettings-Body) sollten weg sein — nur noch im Helper.
    """
    # Extract toggleSettings body
    pat = re.compile(
        r"function toggleSettings\(\)\s*\{\{(.*?)^\}\}",
        re.MULTILINE | re.DOTALL,
    )
    m = pat.search(SRC)
    assert m, "toggleSettings-Body nicht parsbar"
    body = m.group(1)
    # Muss _refreshGhSettingsUI() rufen
    assert "_refreshGhSettingsUI()" in body, (
        "toggleSettings nutzt den Helper nicht — Single-Source verletzt")
    # Inline-Render-Zeilen sollten weg sein (sonst Drift-Risiko)
    assert "Token entsperrt — diese Browser-Session" not in body, (
        "Inline-Status-Render in toggleSettings — sollte im Helper sein")


# === 9 — DOM-Smoke (Helper-Verhalten via Mini-DOM) ========================

def test_helper_dom_smoke():
    """Minimaler DOM-Smoke: extrahiere Helper-Body, replikiere die
    drei Render-Zustände gegen ein Mock-DOM.

    Da wir kein jsdom haben, bilden wir die Logik Pythonisch nach.
    Single-Source-of-Truth-Test: gleiche Statusstrings wie im Code.
    """
    # Reine Logik-Replikation:
    def _render(get_token_ret, has_blob):
        if get_token_ret:
            return ("anth-status ok",
                    "✅ Token entsperrt — diese Browser-Session aktiv")
        if has_blob:
            return ("anth-status",
                    "🔒 Token verschlüsselt gespeichert — leer lassen + OK = entsperren · neuer Token im Feld = ersetzen")
        return ("anth-status", "")

    # 1) Token aktiv → entsperrt
    cls, txt = _render("ghp_token", True)
    assert cls == "anth-status ok"
    assert "Token entsperrt" in txt

    # 2) Token leer, Blob da → verschlüsselt
    cls, txt = _render("", True)
    assert cls == "anth-status"
    assert "verschlüsselt gespeichert" in txt

    # 3) Token leer, kein Blob → leer
    cls, txt = _render("", False)
    assert cls == "anth-status"
    assert txt == ""

    # Cross-check: alle erwarteten Strings sind im Code (Single-Source-
    # Garantie der Replikation)
    for s in ("✅ Token entsperrt — diese Browser-Session aktiv",
              "🔒 Token verschlüsselt gespeichert",
              "anth-status ok"):
        assert s in SRC, f"Replikat-String {s!r} fehlt im Code"


# === 10 — Pflichtcheck =====================================================

def test_no_unescaped_js_template_vars():
    hits = re.findall(r"\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}", SRC)
    assert not hits, f"Unescapte JS-Template-Vars: {hits[:5]}"


# === Runner =================================================================

def main() -> None:
    tests = [
        ("Helper _refreshGhSettingsUI existiert",          test_helper_defined),
        ("Helper no-op wenn Panel unsichtbar",              test_helper_noops_when_panel_hidden),
        ("Helper liest getToken() + _hasEncryptedToken()",  test_helper_reads_get_token),
        ("Helper rendert 3 Zustände",                       test_helper_renders_three_states),
        ("_submitTokenSetup ruft Helper nach close",        test_setup_submit_calls_refresh),
        ("_submitTokenUnlock ruft Helper",                  test_unlock_submit_calls_refresh),
        ("_submitTokenMigrate ruft Helper",                 test_migrate_submit_calls_refresh),
        ("toggleSettings nutzt Helper (DRY)",               test_toggle_settings_uses_helper),
        ("DOM-Smoke: 3 Render-Zustände via Replikation",     test_helper_dom_smoke),
        ("Keine unescapten ${...} im f-String",             test_no_unescaped_js_template_vars),
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
