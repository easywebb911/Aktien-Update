"""Mock-Tests für den Reload-Bestätigungs-Toast (Anzeige, 24.07.2026).

Nach Klick auf den Reload-Button erscheint auf der frisch geladenen Seite eine
zentrierte Erfolgs-Pille „Aktualisiert · Stand <Marktdaten-Stand>". Da
``reloadPage()`` eine Cache-Bust-Vollnavigation ist (window.location.replace),
gibt es KEIN In-Page-Erfolgs-Callback — der Toast wird über ein sessionStorage-
Flag getriggert, das die Navigation überlebt, und beim DOMContentLoaded der
neuen Seite gezeigt.

Reine Quell-Inspektion (kein yfinance/requests/Netzwerk). Verankert:
  1. Toast-Element ``#reload-toast`` mit rt-title „Aktualisiert" + rt-sub-Slot.
  2. CSS ``.reload-toast`` (fixed, zentriert, grüner Rand, pointer-events:none)
     + ``.visible``-Toggle (Mechanik analog #234 .wl-sync-warn).
  3. ``reloadPage()`` setzt das sessionStorage-Flag VOR der Navigation.
  4. ZEITSTEMPEL-EHRLICHKEIT: ``_showReloadToast`` liest den Marktdaten-Stand
     aus ``.hdr-ts`` (strippt „Marktdaten:"-Präfix) — NICHT die Klick-Zeit,
     NICHT ``Date.now()``/``new Date()``.
  5. FEHLER-FALL NICHT GRÜN: der Toast wird NUR bei gesetztem Flag gezeigt
     (``_reloadToastCheck`` guarded) — kein unbedingter Show-Pfad.
  6. Auto-Hide ~2,5 s via setTimeout.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
HJ = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")

_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def test_01_element_present() -> None:
    _check("01 #reload-toast-Element vorhanden",
           'id="reload-toast"' in GR and 'class="reload-toast"' in GR)
    _check("01 rt-title 'Aktualisiert' + rt-sub-Slot",
           '<div class="rt-title">Aktualisiert</div>' in GR
           and 'id="reload-toast-sub"' in GR)
    _check("01 role=status/aria-live (a11y, nicht taps-blockierend)",
           'role="status"' in GR and 'aria-live="polite"' in GR)


def test_02_css_base() -> None:
    m = re.search(r"\.reload-toast\{([^}]*)\}", HJ)
    _check("02 .reload-toast-Regel vorhanden", bool(m))
    body = m.group(1) if m else ""
    _check("02 position:fixed + zentriert (translate -50%,-50%)",
           "position:fixed" in body and "translate(-50%,-50%)" in body,
           f"got {body!r}")
    _check("02 pointer-events:none (blockiert keine Taps)",
           "pointer-events:none" in body)
    _check("02 grüner Rand (Erfolgs-Grün #22c55e)",
           "#22c55e" in body)
    _check("02 .visible-Toggle (Mechanik analog .wl-sync-warn #234)",
           ".reload-toast.visible" in HJ and ".wl-sync-warn.visible" in HJ)


def test_03_flag_set_in_reloadpage() -> None:
    m = re.search(r"function reloadPage\(\)\{\{.*?\n\}\}", GR, re.DOTALL)
    _check("03 reloadPage-Body gefunden", bool(m))
    body = m.group(0) if m else ""
    _check("03 reloadPage setzt sessionStorage-Flag VOR der Navigation",
           "sessionStorage.setItem('_reloadToast'" in body
           and body.index("sessionStorage.setItem('_reloadToast'")
           < body.index("window.location.replace"),
           "Flag muss vor der Navigation gesetzt werden")


def test_04_timestamp_honesty() -> None:
    m = re.search(r"function _showReloadToast\(\)\{\{.*?\n\}\}", GR, re.DOTALL)
    _check("04 _showReloadToast-Body gefunden", bool(m))
    body = m.group(0) if m else ""
    # Liest aus dem Header (.hdr-ts), strippt „Marktdaten:" — gleiche Quelle,
    # gleiches Format wie die Header-Zeile.
    _check("04 liest Marktdaten-Stand aus .hdr-ts",
           ".hdr-ts" in body and "Marktdaten:" in body)
    # KEINE Klick-Zeit / kein neuer Render-Timestamp im Toast-Text.
    _check("04 KEINE Klick-Zeit (Date.now/new Date) im Toast-Reader",
           "Date.now()" not in body and "new Date()" not in body,
           "Toast darf NICHT die Klick-Zeit zeigen (Zeitstempel-Ehrlichkeit)")
    _check("04 Sub-Zeile 'Stand ' + echter Stand",
           "'Stand '" in body)


def test_05_error_case_guarded() -> None:
    m = re.search(r"function _reloadToastCheck\(\)\{\{.*?\n\}\}", GR, re.DOTALL)
    _check("05 _reloadToastCheck-Body gefunden", bool(m))
    body = m.group(0) if m else ""
    # Toast NUR bei gesetztem Flag; Flag wird beim Lesen entfernt (once).
    _check("05 Toast nur bei gesetztem Flag (getItem-Guard) → Fehler = kein Toast",
           "sessionStorage.getItem('_reloadToast')" in body
           and "removeItem('_reloadToast')" in body
           and "_showReloadToast()" in body)
    # Kein unbedingter Show-Aufruf außerhalb des Guards. Nur Call-Sites zählen
    # (mit Semikolon) — die Funktions-DEFINITION `function _showReloadToast()`
    # trägt keins.
    show_calls = GR.count("_showReloadToast();")
    _check("05 _showReloadToast() nur EINMAL aufgerufen (im Guard)",
           show_calls == 1, f"got {show_calls} Call-Sites")


def test_06_autohide() -> None:
    m = re.search(r"function _showReloadToast\(\)\{\{.*?\n\}\}", GR, re.DOTALL)
    body = m.group(0) if m else ""
    _check("06 Auto-Hide ~2,5 s via setTimeout (kein Tap nötig)",
           "setTimeout" in body and "2500" in body
           and "classList.remove('visible')" in body)


def test_07_readystate_robust() -> None:
    # DOMContentLoaded evtl. schon gefeuert → readyState-Fallback, sonst
    # würde der Toast bei spät eingebundenem Script nie erscheinen.
    _check("07 readyState-robust (DOMContentLoaded ODER sofort)",
           "document.readyState === 'loading'" in GR
           and "addEventListener('DOMContentLoaded', _reloadToastCheck)" in GR)


def main() -> None:
    print("── Reload-Bestätigungs-Toast ──────────────────────────────────────")
    for fn in (test_01_element_present, test_02_css_base,
               test_03_flag_set_in_reloadpage, test_04_timestamp_honesty,
               test_05_error_case_guarded, test_06_autohide,
               test_07_readystate_robust):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            _fails.append(fn.__name__)
            print(f"  FAIL {fn.__name__}: {exc!r}")
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        sys.exit(1)
    print("✓ Alle Tests bestanden (Element + CSS + Flag + Zeitstempel-Ehrlichkeit "
          "+ Fehler-Fall-Guard + Auto-Hide).")


if __name__ == "__main__":
    main()
