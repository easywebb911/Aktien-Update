"""Mock-Tests für Watchlist-Drawer Live-Sync der Momentum-Box.

Hintergrund (Diagnose 13.05.2026): ``buildWlDetails`` Variante A nutzt
das server-seitig vorgerenderte ``card_html`` aus ``_WL_CARDS[ticker]``,
in dem ``change`` zum Daily-Run-Zeitpunkt eingebrannt wurde. Zwischen
Daily-Runs zeigt der Drawer veraltete Tagesgewinne — DMRC am 13.05.:
Drawer +0,8 % (aus 12:05-Premarket-Run), real +12,9 % (mid-day).

Fix in generate_report.py: Helper ``_patchWlMomentumLive(scope, ticker)``
patcht nach jedem ``body.innerHTML = ...``-Insert in ``wlExpand`` die
Momentum-Box mit dem aktuellen ``_WL_CARDS[ticker].change``-Wert. Andere
Felder (Score, RVOL, DTC etc.) bleiben eingebrannt.

Tests:
  1. Helper-Funktion existiert im JS-Block
  2. Aufruf nach body.innerHTML = ... vorhanden
  3. Wert-Formel: 12.9 → "+12.9%" / -3.5 → "-3.5%" / 0 → "+0.0%"
  4. Null/undefined/NaN → keine Änderung (Selektor läuft, aber early return)
  5. Sparkline-Sync-Code ist noch vorhanden (kein Regression)
  6. Service-Worker für app_data.json ist network-first
  7. Patch trifft die Momentum-Box im realen card_html (Regex-Smoke)
  8. CLAUDE.md-Pflichtcheck: keine unescapten ${...}-Vars

Ausführung: ``python scripts/mock_test_watchlist_drawer_live_momentum.py``.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _format_chg(change):
    """Pythonische Nachbildung der JS-Formel:
        sign + change.toFixed(1) + '%'
    Mit JS-Verhalten: -0.0 → "-0.0%" (negative Zero behalten),
    NaN/None/non-finite → return None (Helper macht no-op).
    """
    if change is None:
        return None
    try:
        c = float(change)
    except (TypeError, ValueError):
        return None
    import math
    if not math.isfinite(c):
        return None
    sign = "+" if c >= 0 else ""
    return f"{sign}{c:.1f}%"


# === 1-2 — Source-Inspektion ===============================================

def test_helper_function_defined():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    assert "function _patchWlMomentumLive(scope, ticker)" in src, (
        "_patchWlMomentumLive-Helper fehlt in generate_report.py")
    # Muss change-Wert lesen, Selektor auf .m-lbl='Momentum' filtern
    assert "_WL_CARDS" in src and ".change" in src, "_WL_CARDS.change-Lookup fehlt"
    assert "'Momentum'" in src, "Filter auf Momentum-Label fehlt im Helper"


def test_helper_called_after_body_innerhtml():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # Aufruf direkt nach body.innerHTML = ... in wlExpand
    pattern = re.compile(
        r"body\.innerHTML\s*=\s*d\s*\?\s*buildWlDetails.*?\s*"
        r".*?_patchWlMomentumLive\(body,\s*ticker\)",
        re.DOTALL)
    assert pattern.search(src), (
        "_patchWlMomentumLive(body, ticker) wird nicht direkt nach "
        "body.innerHTML in wlExpand aufgerufen")


# === 3-4 — Wert-Formel (Pythonische Replikation) ============================

def test_chg_format_positive():
    assert _format_chg(12.906854) == "+12.9%"


def test_chg_format_negative():
    assert _format_chg(-3.456) == "-3.5%"


def test_chg_format_zero():
    assert _format_chg(0) == "+0.0%"


def test_chg_format_null_no_op():
    # Helper macht early-return bei null/undefined/NaN — kein Crash
    assert _format_chg(None) is None
    assert _format_chg("garbage") is None
    assert _format_chg(float("nan")) is None
    assert _format_chg(float("inf")) is None


# === 5 — Sparkline-Sync nicht regressed =====================================

def test_sparkline_sync_intact():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # Pattern in wlExpand — drawSparkline-Loop muss erhalten bleiben
    assert "body.querySelectorAll('.spark-wrap').forEach(w =>" in src, (
        "Sparkline-Live-Sync in wlExpand wurde durch den Momentum-Patch "
        "versehentlich entfernt")


# === 6 — Service-Worker entfernt (17.05.2026, iOS-Safari-Cache-Quirks) =====

def test_service_worker_removed():
    # Service-Worker wurde entfernt — iOS-Safari hat den Network-First-Modus
    # nicht korrekt umgesetzt (innerer fetch(req) respektierte WebKit-HTTP-
    # Cache → CSS-Merges stundenlang unsichtbar). Easy ist iPhone-Trader,
    # immer online — Offline-Wert war null.
    assert not (ROOT / "service_worker.js").exists(), (
        "service_worker.js existiert noch — sollte 17.05.2026 entfernt sein")
    gr = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    assert "navigator.serviceWorker.register" not in gr, (
        "SW-Registrierung noch in generate_report.py")
    assert "_write_service_worker" not in gr, (
        "_write_service_worker-Funktion noch in generate_report.py")


# === 7 — Smoke: Regex-Patch trifft das echte card_html =====================

def test_regex_patch_finds_momentum_box():
    """Lädt das reale card_html aus app_data.json (falls vorhanden) und
    verifiziert, dass die Momentum-Box per .m-lbl='Momentum' findbar ist.

    Ohne app_data.json (frischer Clone, lokaler Test) → wird übersprungen.
    """
    ad_path = ROOT / "app_data.json"
    if not ad_path.exists():
        print("    (app_data.json nicht da — Smoke übersprungen)")
        return
    ad = json.loads(ad_path.read_text(encoding="utf-8"))
    cards = ad.get("watchlist_cards", {}) or {}
    if not cards:
        print("    (keine watchlist_cards in app_data.json — Smoke übersprungen)")
        return
    # Eine Karte stichprobenartig prüfen (erste mit nicht-leerem card_html)
    found = False
    for ticker, d in cards.items():
        ch = (d or {}).get("card_html") or ""
        if not ch:
            continue
        # Suche metric-box mit m-lbl=Momentum (das ist der Selektor-Match
        # im JS-Helper)
        m = re.search(
            r'<div class="metric-box"[^>]*>\s*<span class="m-val">'
            r'([^<]+)(?:<br>[^<]*<span[^>]*>[^<]*</span>)?</span>\s*'
            r'<span class="m-lbl">Momentum</span>',
            ch)
        if m:
            found = True
            print(f"    (Smoke: {ticker} hat Momentum-Box mit Wert "
                  f"{m.group(1)!r})")
            break
    assert found, (
        "Keine Momentum-Box im card_html der watchlist_cards gefunden — "
        "Selektor-Annahme des JS-Helpers ist falsch")


# === 8 — CLAUDE.md-Pflichtcheck =============================================

def test_no_unescaped_js_template_vars():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    hits = re.findall(r"\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}", src)
    assert not hits, (
        f"Unescapte JS-Template-Variablen im f-String: {hits[:5]}")


# === Runner =================================================================

def main() -> None:
    tests = [
        ("Helper _patchWlMomentumLive existiert",          test_helper_function_defined),
        ("Aufruf nach body.innerHTML in wlExpand",          test_helper_called_after_body_innerhtml),
        ("Wert-Formel: +12.9 → '+12.9%'",                   test_chg_format_positive),
        ("Wert-Formel: -3.5 → '-3.5%'",                     test_chg_format_negative),
        ("Wert-Formel: 0 → '+0.0%'",                        test_chg_format_zero),
        ("Wert-Formel: null/NaN/Garbage → no-op",           test_chg_format_null_no_op),
        ("Sparkline-Sync nicht regressed",                  test_sparkline_sync_intact),
        ("Service-Worker entfernt (iOS-Cache-Quirks)",       test_service_worker_removed),
        ("Regex-Smoke: Momentum-Box im realen card_html",   test_regex_patch_finds_momentum_box),
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
