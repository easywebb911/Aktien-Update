"""Mock-Tests für den _translate()-Google-Fehlerseiten-Guard (26.08.2026).

Hintergrund (Diagnose 21.08.2026, NUR-DIAGNOSE-Session zuvor): ``_translate()``
(generate_report.py) nutzt ``GoogleTranslator`` (deep_translator, kostenloser
inoffizieller Google-Translate-Wrapper). Bei Google-Rate-Limit/Überlastung
wirft die Bibliothek KEINE Exception — sie liefert Googles generische
Fehlerseite als vermeintlich erfolgreiche "Übersetzung" zurück. Der bestehende
``except``-Block fängt das nicht ab (kein Fehler geworfen). Live beobachtet
über mehrere Tage bei mehreren Tickern (NVAX/BKKT/RXRX/ASST), intermittierend
— der Fehlertext landete unverändert im News-Panel, in der "Zusammenfassung"
und im KI-Analyse-Prompt.

Wörtlich beobachteter Fehlertext (Diagnose-Log, App-Live-Daten):
    "Error 500 (Server Error)!!1500.That's an error.There was an error.
     Please try again later.That's all we know."
(typografischer Apostroph im Original — siehe _REAL_ERROR_PAGE unten.)

Fix-Prinzip (analog Reg-SHO/None-Semantik): unbekannt/fehlgeschlagen darf
nicht als falsches Ergebnis durchrutschen, aber der bekannte, nutzbare
Original-Text darf dabei nicht verloren gehen — ``_translate()`` gibt bei
erkannter Fehlerseite (oder leerer Rückgabe) den unübersetzten Original-Text
zurück statt der Fehlerseite oder eines leeren Strings.

Test-Standard: Sektion 1-7 treiben die ECHTE ``generate_report._translate()``
über einen monkeygepatchten ``GoogleTranslator`` an (kein echter Netzwerk-
/Google-Call) — der Guard wird durch das tatsächliche Verhalten der Funktion
bewiesen, nicht durch eine Nachbildung der Erkennungslogik. Sektion 8 zählt
per AST alle ``_translate()``-Call-Sites im Produktionscode (Exzellenz-Block
Punkt 4/6: neuer, bisher unbekannter Aufrufer soll aktiv auffallen statt
still durchzurutschen).

Kategorie A: stdlib only, deterministisch, env-frei — KEIN echter Netzwerk-
/GoogleTranslator-Call in der Test-Suite.
"""
from __future__ import annotations

import ast
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


# ── Heavy-Dependency-Stubs (identisch zu mock_test_outer_page_golden.py) ────
def _install_stubs() -> None:
    if "yfinance" not in sys.modules:
        yf = types.ModuleType("yfinance")
        yf.download = lambda *a, **k: None
        yf.Ticker = lambda *a, **k: None
        sys.modules["yfinance"] = yf
    if "requests" not in sys.modules:
        rq = types.ModuleType("requests")
        rq.Session = lambda *a, **k: types.SimpleNamespace(
            headers=types.SimpleNamespace(update=lambda *a, **k: None))
        rq.get = lambda *a, **k: None
        rq.exceptions = types.SimpleNamespace(RequestException=Exception)
        sys.modules["requests"] = rq
    if "bs4" not in sys.modules:
        bs4 = types.ModuleType("bs4")
        bs4.BeautifulSoup = lambda *a, **k: None
        sys.modules["bs4"] = bs4
    if "deep_translator" not in sys.modules:
        dt = types.ModuleType("deep_translator")
        dt.GoogleTranslator = lambda *a, **k: types.SimpleNamespace(
            translate=lambda s: s)
        sys.modules["deep_translator"] = dt
    if "watchlist" not in sys.modules:
        wl = types.ModuleType("watchlist")
        wl.WATCHLIST = []
        sys.modules["watchlist"] = wl


_install_stubs()
import generate_report as gr  # noqa: E402


# Wörtlich aus der Live-Diagnose 21.08.2026 (echter Response-Body des
# RXRX/NVAX/BKKT-Vorfalls) — KEINE Erfindung, inkl. typografischem Apostroph.
_REAL_ERROR_PAGE = (
    "Error 500 (Server Error)!!1500.That’s an error.There was an error. "
    "Please try again later.That’s all we know."
)


class _FixedTranslator:
    """Ersetzt GoogleTranslator(...): .translate(text) liefert IMMER die
    modul-global gesetzte Rückgabe, unabhängig vom Input — simuliert exakt
    den beobachteten Fehlermodus (kein Raise, nur eine falsche Rückgabe)."""
    _RETURN: object = None

    def __init__(self, *a, **k):
        pass

    def translate(self, text):
        return self._RETURN


class _RaisingTranslator:
    """Simuliert einen ECHTEN Netzwerk-/API-Fehler (Exception) — muss
    weiterhin vom bestehenden except-Block abgefangen werden (Regression)."""

    def __init__(self, *a, **k):
        pass

    def translate(self, text):
        raise RuntimeError("simulated network failure")


def _with_fixed_translate(return_value) -> None:
    _FixedTranslator._RETURN = return_value
    gr.GoogleTranslator = _FixedTranslator


def main() -> int:
    _orig_gt = gr.GoogleTranslator

    # ── 1: echte Google-Fehlerseite (wörtlich aus der Diagnose) ─────────────
    _with_fixed_translate(_REAL_ERROR_PAGE)
    out = gr._translate("Zacks Analyst Blog Highlights Recursion Pharmaceuticals")
    _check("01 echte Fehlerseite (Diagnose-Wortlaut) -> Original-Text, "
           "NICHT die Fehlerseite",
           out == "Zacks Analyst Blog Highlights Recursion Pharmaceuticals")
    _check("01b Fehlerseite selbst wird von _looks_like_translate_error_page() erkannt",
           gr._looks_like_translate_error_page(_REAL_ERROR_PAGE) is True)

    # ── 2: normale, echte Übersetzung -> unverändert durchgereicht ──────────
    _with_fixed_translate("Zacks-Analystenblog hebt Recursion Pharmaceuticals hervor")
    out2 = gr._translate("Zacks Analyst Blog Highlights Recursion Pharmaceuticals")
    _check("02 normale Übersetzung kommt unverändert durch (kein False-Positive)",
           out2 == "Zacks-Analystenblog hebt Recursion Pharmaceuticals hervor")

    # ── 3: Wortlaut-Drift bei Google — nur '!!1' übrig -> trotzdem erkannt ──
    _with_fixed_translate("Something totally different broke !!1 nothing else matches")
    out3 = gr._translate("Original headline text")
    _check("03 nur der '!!1'-Marker (Rest des Wortlauts anders) reicht allein "
           "zur Erkennung — robust gegen Google-Wortlaut-Änderungen",
           out3 == "Original headline text")

    # ── 4: EIN generischer Marker allein -> KEIN False-Positive ─────────────
    _with_fixed_translate("Firma X meldet server error beim Zahlungsdienstleister")
    out4 = gr._translate("Company X reports a server error at its payment processor")
    _check("04 EIN generischer Marker ('server error') allein blockiert NICHT "
           "— legitime Finanz-News dürfen das Wort enthalten",
           out4 == "Firma X meldet server error beim Zahlungsdienstleister")

    # ── 5: ZWEI generische Marker zusammen (ohne '!!1') -> erkannt ──────────
    _with_fixed_translate("That's an error, and that's all we know about the outage")
    out5 = gr._translate("Original text about an outage")
    _check("05 ZWEI generische Marker zusammen (ohne '!!1') werden erkannt",
           out5 == "Original text about an outage")

    # ── 6: typografischer Apostroph in der Fehlerseite ohne '!!1' -> über den
    #      Zwei-Marker-Fallback trotzdem erkannt (Apostroph-Normalisierung) ──
    _drifted = _REAL_ERROR_PAGE.replace("!!1500", "").replace("Error 500 (Server Error)", "")
    _check("06 Vorbereitung: Drift-Fixture enthält kein '!!1' mehr",
           "!!1" not in _drifted)
    _with_fixed_translate(_drifted)
    out6 = gr._translate("Original headline text")
    _check("06 Fehlerseite ohne '!!1' (nur noch typografische Apostroph-Phrasen) "
           "wird über den Zwei-Marker-Fallback erkannt — beweist die "
           "Apostroph-Normalisierung wirkt, nicht nur der starke Marker",
           out6 == "Original headline text")

    # ── 7: leere/None-Rückgabe von GoogleTranslator -> Original, kein Crash ─
    _with_fixed_translate("")
    out7 = gr._translate("Original headline text")
    _check("07a leere Übersetzungs-Rückgabe -> Original-Text (kein leerer String)",
           out7 == "Original headline text")
    _with_fixed_translate(None)
    out7b = gr._translate("Original headline text")
    _check("07b None-Rückgabe -> Original-Text (kein Crash, kein None-Titel)",
           out7b == "Original headline text")

    # ── 8: echte Exception weiterhin abgefangen (bestehendes Verhalten) ─────
    gr.GoogleTranslator = _RaisingTranslator
    out8 = gr._translate("Original headline text")
    _check("08 echte Exception weiterhin via except abgefangen -> Original-Text "
           "(Regression — bestehendes Verhalten bleibt unangetastet)",
           out8 == "Original headline text")

    # ── 9: Kurztext weiterhin ohne Translate-Aufruf früh zurückgegeben ──────
    gr.GoogleTranslator = _orig_gt
    _check("09 Kurztext (<4 Zeichen) weiterhin unverändert früh zurückgegeben "
           "(Verhalten unverändert)",
           gr._translate("ab") == "ab" and gr._translate("") == "")

    # ── 10: ALLE _translate()-Aufrufer bekannt/gezählt (Exzellenz-Block 4+6) ─
    tree = ast.parse(SRC)
    callers = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_translate"
    ]
    _check("10 exakt 4 bekannte _translate()-Call-Sites im Produktionscode "
           f"(gefunden bei Zeilen {callers}) — ein 5. Aufrufer wäre ein "
           "Mini-Stopp-Fall (neu bewerten, nicht raten), kein stiller Drift",
           len(callers) == 4)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle _translate-Error-Guard-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
