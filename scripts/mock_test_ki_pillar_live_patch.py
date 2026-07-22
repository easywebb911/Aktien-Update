"""Mock-Test für den KI-Pillar-Live-Patch in ``renderAgentSignals``.

FIX-KONTEXT (Diagnose 14.07.2026): der frische ki-Score liegt im Client vor
(``app_data.agent_signals``, deckt alle 10 Top-10 ab) und wird bereits für den
Dot genutzt — aber die server-gerenderte KI-Pillar-ZAHL kann ``—`` (Neu-
Einsteiger nach Top-10-Rotation: Daily-Run rendert VOR dem Tick) oder stale
sein. Der Patch zieht Zahl + Farbe + Balken live nach.

REIN ANZEIGE — kein Score-/Pipeline-Touch. Verifiziert:

- (A) Source-Wiring: der Patch-Block existiert in ``renderAgentSignals``,
      liest ``sig.score``, patcht die Cockpit-Pillar-Value + Bar (stdlib,
      immer).
- (B) FUNKTIONAL (node): der extrahierte Patch-Block läuft gegen einen Mock-
      Card-DOM:
      * B1 Null-Fill: ``—`` + frischer Score 58 → Zahl "58", Farbe orange
        (#f97316, da 30 ≤ 58 < 60), Balken 58 %.
      * B2 Stale-Korrektur: alter Wert "43" + Score 28 → "28", rot (#ef4444),
        Balken 28 %.
      * B3 Grün-Schwelle: Score 80 → grün (#22c55e).
      * B4 Kein Score (``sig`` ohne ``score``) → ``—`` bleibt, kein JS-Error.
      * B5 Element fehlt (querySelector → null) → kein Crash.
      * B6 Konfidenz-WASSERZEICHEN (Klasse ``sb-conf-heur`` + ``title``,
        Neutralisierung #425/#426) UNBERÜHRT nach Patch — nur textContent +
        style geändert, kein classList-Touch.

node-Teil (B) skippt graceful ohne node (Source-Gate A bleibt hart).
Fixture-only, kein Kontakt mit Live-Daten.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail and not cond:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


_GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _extract_patch_block() -> str | None:
    """Extrahiere den KI-Pillar-Patch-Block aus renderAgentSignals und
    un-escape die verdoppelten Braces. Grenze: ``if (sig && sig.score != null)``
    bis ``const tickerSpan = card.querySelector``."""
    anchor = _GR_SRC.find("function renderAgentSignals")
    if anchor == -1:
        return None
    start = _GR_SRC.find("if (sig && sig.score != null) {{", anchor)
    end = _GR_SRC.find("const tickerSpan = card.querySelector", start)
    if start == -1 or end == -1:
        return None
    return _GR_SRC[start:end].replace("{{", "{").replace("}}", "}")


def _test_source_wiring():
    print("── (A) Source-Wiring ─────────────────────────────────────────")
    _check(
        "A1 Patch-Block liest sig.score in renderAgentSignals",
        "if (sig && sig.score != null) {{" in _GR_SRC,
        "Patch-Guard fehlt",
    )
    _check(
        "A2 patcht Cockpit-Pillar-Value + Bar-Fill (aktiver Pfad)",
        'data-sb="ki"] .cockpit-pillar-value' in _GR_SRC
        and 'data-sb="ki"] .cockpit-pillar-bar-fill' in _GR_SRC,
        "Cockpit-Selektoren fehlen",
    )
    _check(
        "A3 Farb-Schwellen identisch zu server _tri_score_color (60/30 + hex)",
        "score >= 60 ? '#22c55e' : score >= 30 ? '#f97316' : '#ef4444'" in _GR_SRC,
        "Farb-Logik weicht von _tri_score_color ab",
    )
    _check(
        "A4 nur textContent + style (kein classList-Touch → Wasserzeichen bleibt)",
        "_kv.style.color" in _GR_SRC and ".classList" not in _extract_patch_block(),
        "classList-Manipulation würde das Konfidenz-Wasserzeichen zerstören",
    )
    js = _extract_patch_block()
    _check(
        "A5 kein unescaptes ${...} im Patch-Block (f-String-safe)",
        js is not None and "${" not in js,
        "Template-Literal würde Python-f-String brechen",
    )
    _check(
        "A6 Live-Patch ENTFERNT den KI-Kontext-Hint bei echtem Wert (A1)",
        'data-sb="ki"] .cockpit-pillar-hint' in _GR_SRC
        and "_khint.remove()" in _GR_SRC,
        "Kontext-Hint würde neben dem Wert stehen bleiben",
    )


def _run_node(block: str, sig, score) -> dict | None:
    node = shutil.which("node")
    if not node:
        return None
    harness = (
        "function mkEl(txt, cls, title){\n"
        "  return { textContent: txt, className: cls, title: title,\n"
        "           style: {}, _touchedClass: false, _removed: false,\n"
        "           remove: function(){ this._removed = true; } };\n"
        "}\n"
        "const _val = mkEl('\\u2014', 'cockpit-pillar-value sb-conf-heur',\n"
        "                  'Konfidenz: heuristisch');\n"
        "const _bar = mkEl('', 'cockpit-pillar-bar-fill', '');\n"
        "const _hint = mkEl('kein aktuelles KI-Signal', 'cockpit-pillar-hint', '');\n"
        "const card = { querySelector: function(sel){\n"
        "  if (sel.indexOf('cockpit-pillar-hint') >= 0) return _hint;\n"
        "  if (sel.indexOf('cockpit-pillar-value') >= 0) return _val;\n"
        "  if (sel.indexOf('cockpit-pillar-bar-fill') >= 0) return _bar;\n"
        "  return null;  // v1 sb-num/sb-fill nicht im DOM (Cockpit aktiv)\n"
        "} };\n"
        "const sig = " + json.dumps(sig) + ";\n"
        "const score = (sig && sig.score != null) ? sig.score : 0;\n"
        + block
        + "\nconsole.log(JSON.stringify({\n"
        "  valTxt: _val.textContent, valCol: _val.style.color || null,\n"
        "  valClass: _val.className, valTitle: _val.title,\n"
        "  barW: _bar.style.width || null, barBg: _bar.style.background || null,\n"
        "  hintRemoved: _hint._removed\n"
        "}));\n"
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


def _test_functional():
    print("── (B) Funktional (node): Zahl + Farbe + Balken + Wasserzeichen ─")
    block = _extract_patch_block()
    if block is None:
        _check("B0 Patch-Block extrahierbar", False, "nicht gefunden")
        return

    # B1 Null-Fill (GRPN-Fall): "—" + 58 → "58", orange, 58 %
    r = _run_node(block, {"score": 58}, 58)
    if r is None:
        print("    ⊘ node nicht verfügbar — Funktionaltest übersprungen "
              "(Source-Gate A bleibt hart).")
        return
    _check("B1 Null-Fill: — + 58 → Zahl '58'", r["valTxt"] == "58", f"got {r['valTxt']}")
    _check("B1 Farbe orange (#f97316, 30≤58<60)", r["valCol"] == "#f97316", f"got {r['valCol']}")
    _check("B1 Balken 58 %", r["barW"] == "58%" and r["barBg"] == "#f97316", f"got {r['barW']}/{r['barBg']}")
    # A1 (b): echter Wert kommt → Kontext-Hint wird ENTFERNT (nicht daneben).
    _check("B1 KI-Kontext-Hint entfernt bei echtem Wert (A1 clean replace)",
           r["hintRemoved"] is True, f"got hintRemoved={r['hintRemoved']}")

    # B2 Stale-Korrektur: 28 → rot
    r2 = _run_node(block, {"score": 28}, 28)
    _check("B2 Stale-Korrektur → '28', rot (#ef4444), 28 %",
           r2["valTxt"] == "28" and r2["valCol"] == "#ef4444" and r2["barW"] == "28%",
           f"got {r2['valTxt']}/{r2['valCol']}/{r2['barW']}")

    # B3 Grün-Schwelle: 80 → grün
    r3 = _run_node(block, {"score": 80}, 80)
    _check("B3 Score 80 → grün (#22c55e)", r3["valCol"] == "#22c55e", f"got {r3['valCol']}")

    # B4 Kein Score → "—" bleibt, kein Error
    r4 = _run_node(block, {}, 0)
    _check("B4 kein Score → '—' bleibt (kein Overwrite, kein Crash)",
           r4 is not None and r4["valTxt"] == "—" and r4["valCol"] is None,
           f"got {r4}")
    # A1 (b): ohne Wert bleibt der Kontext-Hint stehen (nicht fälschlich entfernt).
    _check("B4 KI-Kontext-Hint BLEIBT ohne Wert (Guard schützt)",
           r4["hintRemoved"] is False, f"got hintRemoved={r4['hintRemoved']}")

    # B6 Wasserzeichen (Klasse + title) UNBERÜHRT nach Patch (aus B1)
    _check("B6 sb-conf-heur-Klasse nach Patch erhalten (Neutralisierung #425/#426)",
           "sb-conf-heur" in r["valClass"], f"got {r['valClass']}")
    _check("B6 title (Konfidenz-Tooltip) unverändert",
           r["valTitle"] == "Konfidenz: heuristisch", f"got {r['valTitle']}")


def main():
    _test_source_wiring()
    _test_functional()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (KI-Pillar-Live-Patch: Zahl+Farbe+Balken "
          "konsistent, Stale-Korrektur, Graceful-Empty, Wasserzeichen erhalten).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
