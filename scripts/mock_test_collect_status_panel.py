"""Mock-Tests für die Sammel-Felder-Status-Ansicht im #bt-section-Panel.

REIN ANZEIGE-Feature (Datenerhebungs-Fortschritt) — kein Score-/Filter-/Signal-
Effekt. Verifiziert:

- (A) Source-Wiring: HTML-Kachel + CSS-Klassen + _btCollectStatus-Aufruf in
      _btRender vorhanden (stdlib, immer).
- (B) FUNKTIONALER Count-Beweis (Fixture mit bekannten n): die JS-Funktion
      _btCollectStatus wird aus generate_report.py extrahiert, der f-String-
      Doppel-Brace un-escaped und in node gegen eine Fixture ausgeführt. Zählt
      pro Feld die non-null Einträge korrekt (inkl. 0.0 = non-null).
- (C) KEINE Feld-WERTE im Output: die distinktiven Fixture-Werte (12.3, -4.0,
      1.2) dürfen NICHT im gerenderten HTML auftauchen — nur Zähler + Status.

node-Teil (B/C) skippt graceful, wenn node nicht verfügbar ist (Source-Gate A
bleibt hart). Fixture-only, kein Kontakt mit Live-Daten.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


_GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _extract_js_func() -> str | None:
    """Extrahiere den _btCollectStatus-JS-Body aus dem f-String und un-escape
    die verdoppelten Braces ({{ → {, }} → }). Grenze: bis zum nächsten
    `function _btRenderHitRates`."""
    start = _GR_SRC.find("function _btCollectStatus(data){{")
    if start == -1:
        return None
    end = _GR_SRC.find("function _btRenderHitRates(data){{", start)
    if end == -1:
        return None
    snippet = _GR_SRC[start:end]
    # f-String-Un-Escaping: nur die verdoppelten Braces zurückdrehen.
    return snippet.replace("{{", "{").replace("}}", "}")


def _test_source_wiring():
    print("── (A) Source-Wiring ─────────────────────────────────────────")
    _check(
        "A1 HTML-Kachel (id=bt-collect-status) vorhanden",
        'id="bt-collect-status"' in _GR_SRC,
        "Container-Div fehlt im bt-section-Panel",
    )
    _check(
        "A2 Kachel-Titel + neutraler Kopftext vorhanden",
        "Sammel-Felder — Datenerhebung (Fortschritt)" in _GR_SRC
        and "keine Handelsempfehlung, kein Signal" in _GR_SRC
        and "kein Alpha-Generator" in _GR_SRC,
        "neutraler Auffanglinie-Kopftext fehlt/geändert",
    )
    _check(
        "A3 _btCollectStatus wird in _btRender aufgerufen",
        "_btCollectStatus(data);" in _GR_SRC,
        "Render-Aufruf fehlt — Kachel bliebe leer",
    )
    _check(
        "A4 CSS-Klassen vorhanden (.bt-collect-row/.bt-collect-n)",
        ".bt-collect-row{{" in _GR_SRC and ".bt-collect-n{{" in _GR_SRC,
        "CSS für die Status-Zeilen fehlt",
    )
    # Kein rohes ${...}-Template-Literal in der neuen Funktion (f-String-Safety)
    js = _extract_js_func()
    _check(
        "A5 kein unescaptes ${...} in _btCollectStatus (f-String-safe)",
        js is not None and "${" not in js,
        "Template-Literal-Variable würde Python-f-String brechen",
    )


def _run_node(js_func: str, data: list) -> str | None:
    """Führe die extrahierte JS-Funktion in node gegen `data` aus und gib das
    an innerHTML geschriebene HTML zurück. None wenn node fehlt."""
    node = shutil.which("node")
    if not node:
        return None
    harness = (
        js_func
        + "\nlet __captured = '';\n"
        + "global.document = { getElementById: function(id){"
        + " return id === 'bt-collect-status'"
        + " ? { set innerHTML(v){ __captured = v; } } : null; } };\n"
        + "const __data = " + json.dumps(data) + ";\n"
        + "_btCollectStatus(__data);\n"
        + "console.log(JSON.stringify({ html: __captured }));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(harness)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True,
                             timeout=20)
        if out.returncode != 0:
            print(f"    node stderr: {out.stderr[:300]}")
            return None
        return json.loads(out.stdout.strip())["html"]
    finally:
        pathlib.Path(path).unlink(missing_ok=True)


def _test_functional_counts():
    print("── (B/C) Funktionaler Count-Beweis (node) ────────────────────")
    js = _extract_js_func()
    if js is None:
        _check("B0 JS-Funktion extrahierbar", False, "_btCollectStatus nicht gefunden")
        return

    # Fixture mit BEKANNTEN non-null-Zählern. 0.0 zählt als non-null (Wert),
    # null/undefined NICHT.
    data = [
        {"max_gain_pct": 12.3, "conviction_score": 50, "days_to_earnings": 5,
         "entry_past_return_5d": -4.0, "si_velocity_pub": 1.2},
        {"max_gain_pct": 0.0, "conviction_score": None},   # max_gain 0.0 = non-null
        {"max_gain_pct": None},                             # alles null/absent
        {"conviction_score": 30, "si_velocity_pub": None},
    ]
    # Erwartete non-null-Zähler:
    expected = {
        "max_gain_pct": 2,          # 12.3, 0.0
        "conviction_score": 2,      # 50, 30
        "days_to_earnings": 1,      # 5
        "entry_past_return_5d": 1,  # -4.0
        "si_velocity_pub": 1,       # 1.2
    }

    html = _run_node(js, data)
    if html is None:
        print("    ⊘ node nicht verfügbar — funktionaler Count-Test übersprungen "
              "(Source-Gate A bleibt hart).")
        return

    # Pro Feld: die Zeile enthält den Roh-Feldnamen (in Klammer) + 'n=<zahl>'.
    # Wir prüfen, dass die richtige n-Zahl im Output steht.
    for key, exp_n in expected.items():
        # Suche die Zeile mit dem Roh-Feldnamen, extrahiere das folgende n=.
        # Reihenfolge im HTML: name(...key...) ... n=X ... status
        m = re.search(re.escape(key) + r"\).*?n=(\d+)", html, re.DOTALL)
        got = int(m.group(1)) if m else None
        _check(
            f"B-{key}: n={exp_n} korrekt gezählt (non-null)",
            got == exp_n,
            f"got n={got}",
        )

    # (C) KEINE Feld-WERTE im Output — distinktive Fixture-Floats dürfen nicht
    # auftauchen (nur Zähler + Status werden gerendert).
    for forbidden in ("12.3", "-4.0", "1.2"):
        _check(
            f"C kein Feld-Wert '{forbidden}' im Output (nur Zähler/Status)",
            forbidden not in html,
            "Feld-Wert wird gerendert — das wäre als Performance lesbar!",
        )


def main():
    _test_source_wiring()
    _test_functional_counts()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (Sammel-Felder-Status: Wiring + dynamische "
          "non-null-Zähler + KEINE Feld-Werte).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
