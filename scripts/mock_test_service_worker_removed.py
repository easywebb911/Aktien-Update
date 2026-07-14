"""Mock-Tests fuer Service-Worker-Entfernung (17.05.2026).

Hintergrund: Service-Worker mit Network-First-Strategie hatte einen
versteckten Bug: `fetch(req)` ohne explizite `cache`-Option respektiert
den WebKit-HTTP-Cache (max-age=600 bei GitHub-Pages). iOS-Safari hat
deshalb PR #185 + #186 stundenlang als alte Version ausgeliefert
obwohl beide gemerged waren. Easy ist iPhone-Trader, immer online —
Offline-Wert war null. Service-Worker komplett entfernt.

Strategie: alte SW-Instanzen werden beim naechsten Page-Load aktiv
deregistriert (Unregister-Block im Inline-JS), Caches geleert. Easy
muss einmalig nach diesem Merge Cache-Bust durchfuehren, danach
SW-frei. Bei kuenftigen CSS-Merges sofortige Sichtbarkeit.

Tests:
  1. service_worker.js existiert nicht mehr im Repo-Root
  2. _write_service_worker-Funktion entfernt aus generate_report.py
  3. SW_ENABLED-Konstante entfernt aus config.py
  4. navigator.serviceWorker.register nicht mehr in generate_report.py
  5. Unregister-Block in generate_report.py vorhanden
     (getRegistrations + unregister fuer Clean-up alter Instanzen)
  6. Cache-Loeschung im Unregister-Block (caches.keys + caches.delete)
  7. Workflow daily-squeeze-report.yml hat keinen service_worker.js
     git-add-Eintrag mehr
  8. _config.yml hat keine service_worker.js-Erwaehnung mehr
  9. Apple-Meta-Tags bleiben (rein deklarativ, kein SW-Bezug)
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
CFG = (ROOT / "config.py").read_text(encoding="utf-8")
HJ = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "daily-squeeze-report.yml").read_text(encoding="utf-8")
JEKYLL_CFG = (ROOT / "_config.yml").read_text(encoding="utf-8")


def test_01_sw_file_removed() -> None:
    assert not (ROOT / "service_worker.js").exists(), \
        "service_worker.js existiert noch — sollte git rm'd sein"


def test_02_write_sw_function_removed() -> None:
    assert "def _write_service_worker" not in GR, \
        "_write_service_worker-Funktion noch in generate_report.py"
    assert "_write_service_worker()" not in GR, \
        "_write_service_worker()-Aufrufstelle noch in generate_report.py"


def test_03_sw_enabled_constant_removed() -> None:
    assert "SW_ENABLED" not in CFG, "SW_ENABLED-Konstante noch in config.py"
    assert "SW_ENABLED" not in GR, "SW_ENABLED-Referenz noch in generate_report.py"


def test_04_no_sw_registration() -> None:
    assert "navigator.serviceWorker.register" not in GR, \
        "navigator.serviceWorker.register noch in generate_report.py"


def test_05_unregister_block_present() -> None:
    # Cleanup-Block fuer existierende SW-Instanzen auf User-Browsern
    assert "navigator.serviceWorker.getRegistrations()" in GR, \
        "Unregister-Block (getRegistrations) fehlt — alte SW-Instanzen " \
        "auf Easy's iPhone wuerden nicht aufgeraeumt"
    assert "reg.unregister()" in GR, \
        "reg.unregister()-Call fehlt im Cleanup-Block"


def test_06_cache_cleanup_present() -> None:
    # Alle vom alten SW angelegten Caches loeschen
    assert "caches.keys()" in GR, "caches.keys()-Cleanup fehlt"
    assert "caches.delete" in GR, "caches.delete-Cleanup fehlt"


def test_07_workflow_no_sw_git_add() -> None:
    assert "service_worker.js" not in WORKFLOW, \
        "service_worker.js noch in daily-squeeze-report.yml (git add)"


def test_08_jekyll_config_no_sw_mention() -> None:
    assert "service_worker.js" not in JEKYLL_CFG, \
        "service_worker.js noch in _config.yml-Kommentar"


def test_09_apple_meta_tags_preserved() -> None:
    # Deklarative iOS-Meta-Tags haben keinen SW-Bezug und bleiben —
    # iOS rendert die Seite weiterhin nett im "Zum Home-Bildschirm"-Modus.
    assert 'name="apple-mobile-web-app-capable"' in HJ, \
        "apple-mobile-web-app-capable Meta-Tag entfernt"
    assert 'name="apple-mobile-web-app-title"' in HJ, \
        "apple-mobile-web-app-title Meta-Tag entfernt"


# ── Cache-Bust-Konsistenz im Recalculate-Reload (Fix 14.07.) ────────────────
# reloadPage (Menü) nutzt das bustende ?v=-Muster; die Recalculate-Abschluss-
# Reloads (Countdown-Auto + _manualReload) nutzten plain reload() → respektierten
# den GitHub-Pages max-age. Angeglichen an dasselbe #373-Muster.

_BUST = "window.location.replace(location.pathname + '?v=' + Date.now())"


def _manual_reload_body() -> str:
    start = GR.find("function _manualReload(){{")
    assert start != -1, "_manualReload-Funktion nicht gefunden"
    end = GR.find("window.addEventListener('beforeunload'", start)
    return GR[start:end]


def test_10_reloadpage_pattern_present() -> None:
    # Referenz-Muster (Menü-Refresh) unveraendert vorhanden.
    assert _BUST in GR, "reloadPage-?v=-Bust-Muster fehlt (Referenz)"


def test_11_recalc_countdown_reload_busts() -> None:
    # Countdown-Auto-Reload (n<=0) nutzt das bustende ?v=-Muster.
    assert f"_cdInterval = null; {_BUST}" in GR, \
        "Recalculate-Countdown-Reload nutzt nicht das bustende ?v=-Muster"


def test_12_manual_reload_busts() -> None:
    body = _manual_reload_body()
    assert _BUST in body, "_manualReload nutzt nicht das bustende ?v=-Muster"
    assert "window.location.reload()" not in body, \
        "_manualReload hat noch plain reload() (respektiert HTTP-Cache)"


def test_13_no_plain_reload_in_recalc_countdown() -> None:
    # Kein plain reload() mehr im Countdown-Auto-Pfad.
    assert "_cdInterval = null; window.location.reload()" not in GR, \
        "Plain reload() im Recalculate-Countdown-Pfad verblieben"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 service_worker.js entfernt",            test_01_sw_file_removed),
        ("02 _write_service_worker-Funktion weg",    test_02_write_sw_function_removed),
        ("03 SW_ENABLED-Konstante entfernt",          test_03_sw_enabled_constant_removed),
        ("04 Keine SW-Registrierung mehr",            test_04_no_sw_registration),
        ("05 Unregister-Block fuer alte Instanzen",  test_05_unregister_block_present),
        ("06 Cache-Cleanup im Unregister-Block",      test_06_cache_cleanup_present),
        ("07 Workflow: kein git add service_worker", test_07_workflow_no_sw_git_add),
        ("08 _config.yml: kein SW-Hinweis",          test_08_jekyll_config_no_sw_mention),
        ("09 Apple-Meta-Tags erhalten",              test_09_apple_meta_tags_preserved),
        ("10 reloadPage-?v=-Muster vorhanden",       test_10_reloadpage_pattern_present),
        ("11 Recalc-Countdown-Reload bustet",        test_11_recalc_countdown_reload_busts),
        ("12 _manualReload bustet (kein plain)",     test_12_manual_reload_busts),
        ("13 kein plain reload() im Countdown",      test_13_no_plain_reload_in_recalc_countdown),
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
