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

import config  # noqa: E402  (COLLECT_STATUS_FIELDS = Feldliste, Single-Source)

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
    # A6: Feldliste kommt aus config (Single-Source) + Injektion verdrahtet.
    _check(
        "A6 config.COLLECT_STATUS_FIELDS = 5 Einträge (roh, label, status)",
        len(config.COLLECT_STATUS_FIELDS) == 5
        and all(len(t) == 3 for t in config.COLLECT_STATUS_FIELDS),
        f"got {len(config.COLLECT_STATUS_FIELDS)}",
    )
    _check(
        "A7 JS-Konstante server-injiziert (const _COLLECT_STATUS_FIELDS = {...})",
        "const _COLLECT_STATUS_FIELDS = {collect_status_fields_js};" in _GR_SRC
        and '"collect_status_fields_js": json.dumps(COLLECT_STATUS_FIELDS' in _GR_SRC,
        "Render-Injektion fehlt — Kachel bekäme keine Feldliste",
    )
    # A8: LOOK-AHEAD-SAFETY (Kern von Option A) — die Backtest-Feldnamen dürfen
    # NICHT als quoted-Literal im generate_report.py-Source stehen (nur in
    # config.py + injiziert). Sonst reißen die Isolations-Guards. Prüft die
    # zwei Felder mit Regex-Guard (si_velocity_pub) bzw. bewusst mit-geführt.
    for fld in ("si_velocity_pub", "entry_past_return_5d", "days_to_earnings"):
        quoted = ("'" + fld + "'", '"' + fld + '"')
        _check(
            f"A8-{fld}: kein quoted-Literal im generate_report.py-Source",
            not any(q in _GR_SRC for q in quoted),
            "Feldname als Literal → Look-Ahead-Guard würde reißen (Option A verletzt)",
        )


def _run_node(js_func: str, data: list) -> str | None:
    """Führe die extrahierte JS-Funktion in node gegen `data` aus und gib das
    an innerHTML geschriebene HTML zurück. None wenn node fehlt."""
    node = shutil.which("node")
    if not node:
        return None
    # Die Funktion liest die server-injizierte Konstante _COLLECT_STATUS_FIELDS
    # (aus config.COLLECT_STATUS_FIELDS). Im Harness definieren wir sie analog.
    fields_js = json.dumps(config.COLLECT_STATUS_FIELDS, ensure_ascii=False)
    harness = (
        "const _COLLECT_STATUS_FIELDS = " + fields_js + ";\n"
        + js_func
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


def _extract_si_js() -> str | None:
    """Extrahiere den SI-Block (_btSiCount + _btSiRenderRow + _btSiCollectStatus)
    aus dem f-String und un-escape die verdoppelten Braces. Grenze: bis
    `function _btRenderHitRates`."""
    start = _GR_SRC.find("function _btSiCount(obj){{")
    if start == -1:
        return None
    end = _GR_SRC.find("function _btRenderHitRates(data){{", start)
    if end == -1:
        return None
    return _GR_SRC[start:end].replace("{{", "{").replace("}}", "}")


def _test_si_source_wiring():
    print("── (D) SI-Eintrag Source-Wiring ──────────────────────────────")
    _check(
        "D1 SI-Host-Div (id=bt-collect-si-status) vorhanden",
        'id="bt-collect-si-status"' in _GR_SRC,
        "SI-Container-Div fehlt im Panel",
    )
    _check(
        "D2 _btSiCollectStatus wird in _btRender aufgerufen",
        "_btSiCollectStatus();" in _GR_SRC,
        "SI-Render-Aufruf fehlt",
    )
    _check(
        "D3 config.SI_POSITION_STATUS_ROW = 3-Tupel (label, status, datei)",
        isinstance(config.SI_POSITION_STATUS_ROW, tuple)
        and len(config.SI_POSITION_STATUS_ROW) == 3,
        f"got {config.SI_POSITION_STATUS_ROW!r}",
    )
    _check(
        "D4 JS-Konstante server-injiziert (const _SI_POSITION_STATUS = {...})",
        "const _SI_POSITION_STATUS = {si_position_status_row_js};" in _GR_SRC
        and '"si_position_status_row_js": json.dumps(SI_POSITION_STATUS_ROW' in _GR_SRC,
        "SI-Injektion fehlt — Eintrag bekäme kein Label/Status",
    )
    # D5 Weg-A: das Label darf NICHT als Frontend-Literal im Source stehen (nur
    # in config.py + injiziert) — analog A8. Der Dateiname (si_position_history)
    # lebt legitim in der Persist-Kette; darauf zielt der Guard NICHT.
    _check(
        "D5 SI-Label kein quoted-Literal im generate_report.py-Source (Weg-A)",
        config.SI_POSITION_STATUS_ROW[0] not in _GR_SRC,
        "Label als Frontend-Literal → Weg-A verletzt",
    )
    js = _extract_si_js()
    _check(
        "D6 kein unescaptes ${...} im SI-Block (f-String-safe)",
        js is not None and "${" not in js,
        "Template-Literal-Variable würde Python-f-String brechen",
    )


def _run_si_node(js_block: str, data) -> dict | None:
    """Führe _btSiCount(data) + _btSiRenderRow gegen einen Mock-Host in node aus.
    Returnt {count: {ge2,total}, html: <gerendert>}. None wenn node fehlt."""
    node = shutil.which("node")
    if not node:
        return None
    status_js = json.dumps(list(config.SI_POSITION_STATUS_ROW), ensure_ascii=False)
    harness = (
        "const _SI_POSITION_STATUS = " + status_js + ";\n"
        + js_block
        + "\nconst __data = " + json.dumps(data) + ";\n"
        + "const __c = _btSiCount(__data);\n"
        + "let __html = '';\n"
        + "const __host = { set innerHTML(v){ __html = v; } };\n"
        + "_btSiRenderRow(__host, __c.ge2, __c.total);\n"
        + "console.log(JSON.stringify({ count: __c, html: __html }));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(harness)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=20)
        if out.returncode != 0:
            print(f"    node stderr: {out.stderr[:300]}")
            return None
        return json.loads(out.stdout.strip())
    finally:
        pathlib.Path(path).unlink(missing_ok=True)


def _test_si_functional():
    print("── (E) SI Zähl-Logik + Graceful-Empty + KEINE Werte (node) ───")
    js = _extract_si_js()
    if js is None:
        _check("E0 SI-JS-Block extrahierbar", False, "_btSiCount nicht gefunden")
        return

    # Fixture mit bekannten Serienlängen. shares_short bewusst distinktiv
    # (7777777) — darf NICHT im Output erscheinen (nur Zähler/Status).
    p = lambda: {"settlement_date": "2026-06-30", "shares_short": 7777777,
                 "short_pct_float": 50.0, "pub_date": "2026-07-10"}
    data = {
        "AAA": [p(), p()],        # 2 Punkte → ≥2
        "BBB": [p()],             # 1 Punkt  → nur total
        "CCC": [p(), p(), p()],   # 3 Punkte → ≥2
        "DDD": "kaputt",          # kein Array → ignoriert
        "EEE": [],                # leeres Array → total, nicht ≥2
    }
    res = _run_si_node(js, data)
    if res is None:
        print("    ⊘ node nicht verfügbar — SI-Funktionaltest übersprungen "
              "(Source-Gate D bleibt hart).")
        return

    _check(
        "E1 ge2 (Ticker mit ≥2 Punkten) == 2 (AAA, CCC)",
        res["count"]["ge2"] == 2, f"got {res['count']['ge2']}",
    )
    _check(
        "E2 total (Ticker mit Array-Serie) == 4 (AAA,BBB,CCC,EEE; DDD kein Array)",
        res["count"]["total"] == 4, f"got {res['count']['total']}",
    )
    _check(
        "E3 gerenderte Zeile zeigt n=2 (4 Ticker)",
        "n=2 (4 Ticker)" in res["html"], f"html={res['html'][:160]}",
    )
    # Graceful-Empty: leeres Objekt → n=0 (0 Ticker), kein Error.
    res0 = _run_si_node(js, {})
    if res0 is not None:
        _check(
            "E4 Graceful-Empty: {} → n=0 (0 Ticker)",
            res0["count"] == {"ge2": 0, "total": 0}
            and "n=0 (0 Ticker)" in res0["html"],
            f"got {res0['count']}",
        )
    # KEINE Serien-Werte im Output — distinktiver shares_short darf nicht auftauchen.
    _check(
        "E5 kein Serien-Wert '7777777' im Output (nur Zähler/Status)",
        "7777777" not in res["html"],
        "shares_short wird gerendert — das wäre als SI-Position lesbar!",
    )
    # Status-Text ist der neutrale config-Text, KEINE Delta-/Signal-Sprache.
    _check(
        "E6 neutraler Status-Text (config), kein Signal",
        config.SI_POSITION_STATUS_ROW[1] in res["html"]
        and "sammelt" in res["html"] and "unvalidiert" in res["html"],
        "neutraler Auffanglinie-Status fehlt im Output",
    )


def main():
    _test_source_wiring()
    _test_functional_counts()
    _test_si_source_wiring()
    _test_si_functional()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (Sammel-Felder-Status: Wiring + dynamische "
          "non-null-Zähler + KEINE Feld-Werte + SI-Positions-Eintrag: "
          "≥2-Punkte-Zähler + Graceful-Empty + KEINE Serien-Werte).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
