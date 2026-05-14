"""Mock-Tests für Storage-Diagnose-Panel im Settings (iPhone-Token-Verlust-Debug).

Hintergrund (14.05.2026): Easys iPhone verliert den encrypted Token-Blob
mehrmals täglich trotz Standalone-PWA-Modus. Vorherige Diagnose-Vermutung
„ITP 7-Tage-Cap" ist im Standalone-Modus unwahrscheinlich. Dieser PR
fügt eine On-Page-Diagnose hinzu, damit Easy beim nächsten Verlust den
genauen Storage-Zustand abrufen kann (Blob/Session/Keep-Alive-Alter +
Standalone-Erkennung).

Strikt: nur Anzeige, keine Token-/Passwort-Werte werden geleakt.

Tests:
  1. _buildStorageSnapshot-Helper existiert
  2. _renderStorageDiagnose schreibt in #tok-diag-output
  3. _copyStorageSnapshot existiert + nutzt navigator.clipboard mit Fallback
  4. Helper rendert NUR Längen + Existenz-Flags, KEINE Token-Werte
  5. Standalone-Erkennung über beide Methoden (navigator + matchMedia)
  6. Diagnose-Block-HTML im Settings-Panel präsent
  7. _refreshGhSettingsUI ruft _renderStorageDiagnose
  8. Snapshot enthält erwartete Top-Level-Keys
  9. Keep-Alive-Alter Berechnung korrekt (Pythonische Replikation)
 10. Pflichtcheck: keine unescapten ${...}-Vars
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")


# === 1 — Helper existieren =================================================

def test_helpers_defined():
    for fn in ("_buildStorageSnapshot", "_renderStorageDiagnose",
               "_copyStorageSnapshot"):
        assert f"function {fn}(" in SRC, f"Helper {fn} fehlt"


# === 2 — _renderStorageDiagnose schreibt in DOM-Element ===================

def test_render_targets_diag_output():
    body = _extract_function_body("_renderStorageDiagnose")
    assert "'tok-diag-output'" in body, "Falsches DOM-Ziel im Render"
    assert "JSON.stringify" in body, "Snapshot wird nicht als JSON gerendert"


# === 3 — Copy-Helper mit Clipboard-API + Fallback =========================

def test_copy_helper_has_clipboard_and_fallback():
    body = _extract_function_body("_copyStorageSnapshot")
    assert "navigator.clipboard" in body, "navigator.clipboard-Pfad fehlt"
    assert "execCommand('copy')" in body, "execCommand-Fallback fehlt"
    assert "createElement('textarea')" in body, "Fallback-Textarea fehlt"


# === 4 — Kein Token-/Passwort-Leak ========================================

def _extract_function_body(name: str) -> str:
    """Extrahiert den vollständigen Body einer Top-Level-Funktion.
    Funktioniert auch bei verschachtelten `{{...}}`-Patterns (Python-f-
    String-Escape im Source). Sucht: von `function <name>(` bis zur
    NÄCHSTEN top-level `function `-Deklaration.
    """
    start_pat = re.compile(rf"^function {re.escape(name)}\(", re.MULTILINE)
    m = start_pat.search(SRC)
    assert m, f"{name} nicht gefunden"
    start = m.start()
    rest = SRC[m.end():]
    next_top = re.search(r"^function\s+[A-Za-z_]", rest, re.MULTILINE)
    end = m.end() + next_top.start() if next_top else len(SRC)
    return SRC[start:end]


def test_snapshot_does_not_leak_secrets():
    """Snapshot darf keine Token-/Passwort-Werte enthalten — nur Längen +
    Flags. Wir prüfen, dass die Setter im Snapshot keine `lsBlob` oder
    `ssTok` ROHWERT zurückgeben."""
    body = _extract_function_body("_buildStorageSnapshot")
    return_block = body[body.find("return {{"):]
    # Roh-Wert-Rückgabe-Pattern: `<key>:<ws>lsBlob,` oder `…ssTok,` —
    # nur als direkter Value, nicht innerhalb eines Ausdrucks. Wir prüfen
    # die "leak"-Pattern explizit: Key gefolgt von ":" + Whitespace +
    # genau dem Variablen-Namen + Komma.
    leak_patterns = [
        r":\s+lsBlob\s*,",      # direkter Roh-Wert
        r":\s+ssTok\s*,",
        r":\s+lsLegacy\s*,",
        r":\s+_inMemoryToken\s*,",
    ]
    for p in leak_patterns:
        assert not re.search(p, return_block), (
            f"Snapshot returnt Roh-Wert ({p}) — Token-Leak-Risiko")
    # Konstruktiv: erlaubte Pattern müssen vorhanden sein
    assert re.search(r"!!lsBlob", return_block), (
        "Snapshot meldet blob nicht als boolean-Flag (!!lsBlob)")
    assert re.search(r"_len\(lsBlob\)", return_block), (
        "Snapshot meldet blob_len nicht via _len-Helper")
    # Master-Passwort: kommt aus dem Modal-Input, soll generell NIE
    # in Storage stehen — keine Passwort-Lookup-Patterns im Snapshot.
    assert "tok-setup-pw" not in body, "Snapshot referenziert Master-Passwort-Input"
    assert "tok-unlock-pw" not in body
    # Erlaubte Felder (Längen / Flags / Timestamps) müssen drin sein
    for required in ("blob_present", "blob_len", "session_token_len",
                     "in_memory_token_len", "keepalive_age_h"):
        assert required in return_block, (
            f"Erwartetes Längen-/Flag-Feld {required} fehlt im Snapshot")


# === 5 — Standalone-Erkennung beide Methoden ==============================

def test_standalone_detection_two_methods():
    body = _extract_function_body("_buildStorageSnapshot")
    assert "navigator.standalone" in body, (
        "iOS-spezifische navigator.standalone-Erkennung fehlt")
    assert "matchMedia" in body and "display-mode: standalone" in body, (
        "matchMedia-Erkennung fehlt")
    # Beide Werte werden ins Snapshot-Dict gepackt + Aggregat-Flag
    return_block = body[body.find("return {{"):]
    for key in ("standalone_navigator", "standalone_media", "is_standalone"):
        assert key in return_block, f"Standalone-Feld {key} fehlt"


# === 6 — HTML-Block im Settings-Panel =====================================

def test_diagnose_block_in_settings_panel():
    assert "tok-diag-output" in SRC, "Diagnose-Output-Element fehlt im HTML"
    assert "tok-diag-summary" in SRC, "Details-Summary fehlt"
    assert "_copyStorageSnapshot()" in SRC, "Copy-Button-onclick fehlt"
    # Block sollte innerhalb des Settings-Panels (anth-sec) sein
    panel_start = SRC.find('id="anth-sec"')
    panel_end   = SRC.find('<!-- Phase 3: Token-Encryption-Modals')
    assert panel_start < panel_end, "Settings-Panel-Bereich nicht parsbar"
    panel = SRC[panel_start:panel_end]
    assert "tok-diag-output" in panel, (
        "Diagnose-Block ist NICHT innerhalb von #anth-sec")


# === 7 — _refreshGhSettingsUI ruft Diagnose-Render ========================

def test_refresh_ui_calls_diagnose_render():
    body = _extract_function_body("_refreshGhSettingsUI")
    assert "_renderStorageDiagnose()" in body, (
        "_refreshGhSettingsUI ruft _renderStorageDiagnose nicht — "
        "Diagnose wäre nie aktuell")


# === 8 — Snapshot-Top-Level-Keys ==========================================

def test_snapshot_has_expected_keys():
    expected = {
        "timestamp", "blob_present", "blob_len",
        "legacy_present", "session_token_present", "session_token_len",
        "in_memory_token_present", "in_memory_token_len",
        "keepalive_ts", "keepalive_age_h",
        "standalone_navigator", "standalone_media", "is_standalone",
        "localStorage_total_keys", "localStorage_keys",
        "user_agent", "platform", "auth_fail_count",
    }
    body = _extract_function_body("_buildStorageSnapshot")
    for key in expected:
        assert f"{key}:" in body, f"Snapshot-Key {key!r} fehlt"


# === 9 — Keep-Alive-Alter Berechnung (Pythonische Replikation) ============

def _keepalive_age_h(now_ms: float, ts_ms: float) -> float | None:
    """Replikation der JS-Logik:
        Math.round((Date.now() - ts) / 36000) / 100
    Liefert das Alter in Stunden mit 2 Nachkommastellen.
    """
    if ts_ms is None or ts_ms <= 0:
        return None
    return round(round((now_ms - ts_ms) / 36000) / 100, 2)


def test_keepalive_age_calc_fresh():
    # 1 Stunde zurück = 3.6M ms
    assert _keepalive_age_h(now_ms=10_000_000, ts_ms=10_000_000 - 3_600_000) == 1.0


def test_keepalive_age_calc_7_days():
    # 7 Tage = 7*24*3.6M = 604.8M ms
    age = _keepalive_age_h(now_ms=1_000_000_000, ts_ms=1_000_000_000 - 7*24*3_600_000)
    assert age == 168.0, age


def test_keepalive_age_calc_zero_ts():
    assert _keepalive_age_h(now_ms=10_000, ts_ms=0) is None
    assert _keepalive_age_h(now_ms=10_000, ts_ms=None) is None


# === 10 — Pflichtcheck =====================================================

def test_no_unescaped_js_template_vars():
    hits = re.findall(r"\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}", SRC)
    assert not hits, f"Unescapte JS-Template-Vars: {hits[:5]}"


# === 11 — Snapshot-Helper meidet sensible Inputs ==========================

def test_snapshot_no_password_input_lookups():
    """Snapshot-Helper darf nicht document.getElementById('tok-*-pw') o.Ä.
    aufrufen — Master-Passwort-Werte sind Modal-Inputs und sollen NIE
    geleakt werden."""
    body = _extract_function_body("_buildStorageSnapshot")
    bad_patterns = ("'tok-setup-pw'", "'tok-unlock-pw'", "'tok-mig-pw'",
                    "anth-inp", "ANT_KEY_LS")
    for p in bad_patterns:
        assert p not in body, (
            f"Snapshot-Helper liest verbotenen Wert {p} — Leak-Risiko")


# === Runner =================================================================

def main() -> None:
    tests = [
        ("Helper _buildStorageSnapshot/_renderStorageDiagnose/_copyStorageSnapshot existieren",
         test_helpers_defined),
        ("_renderStorageDiagnose schreibt in #tok-diag-output",
         test_render_targets_diag_output),
        ("_copyStorageSnapshot: navigator.clipboard + execCommand-Fallback",
         test_copy_helper_has_clipboard_and_fallback),
        ("Snapshot leakt KEINE Token-/Passwort-Werte (nur Längen/Flags)",
         test_snapshot_does_not_leak_secrets),
        ("Standalone-Erkennung via navigator.standalone + matchMedia",
         test_standalone_detection_two_methods),
        ("Diagnose-HTML-Block innerhalb #anth-sec",
         test_diagnose_block_in_settings_panel),
        ("_refreshGhSettingsUI ruft _renderStorageDiagnose",
         test_refresh_ui_calls_diagnose_render),
        ("Snapshot-Top-Level-Keys komplett",
         test_snapshot_has_expected_keys),
        ("Keep-Alive-Alter: 1h Berechnung",
         test_keepalive_age_calc_fresh),
        ("Keep-Alive-Alter: 7-Tage-Berechnung",
         test_keepalive_age_calc_7_days),
        ("Keep-Alive-Alter: ts=0/None → None",
         test_keepalive_age_calc_zero_ts),
        ("Keine unescapten ${...} im f-String",
         test_no_unescaped_js_template_vars),
        ("Snapshot meidet sensible Inputs (Master-Passwort etc.)",
         test_snapshot_no_password_input_lookups),
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
