"""Mock-Test — Bootstrap-Shell PHASE 1 (Flip der ausgelieferten Seite).

KONTEXT: Nach Phase 0 (#434, `app.html` = kanonischer Content-Pfad, alle Parser
repointed) ist Phase 1 der **Flip**: `index.html` wird von der vollen Seite zur
**winzigen Shell** (`_SHELL_HTML`), die auf `app.html?v=<ts>` weiterleitet — der
einzige strukturelle Fix gegen den iOS-PWA-Launcher-Cache (iOS öffnet die
parameterlose start_url; die gecachte Shell bounct auf eine eindeutige
`?v=`-URL → Cache-Miss → frische Bytes).

Verifiziert (Source-Inspektion, stdlib-only → CI-minimal-safe):

- (A) Shell-Inhalt vollständig PWA-tauglich:
      * Apple-Meta ALLE DREI (capable / status-bar-style / title) — sonst
        verliert der Launch Standalone/Icon/Titel.
      * viewport + charset + <title>.
      * `location.replace('app.html?v=' + Date.now())` (replace = kein
        History-Eintrag, #373-Muster).
      * Fallback-Kette: <noscript>-Refresh (JS aus) + sichtbarer
        <a href="app.html">-Link (app.html-404-Mitigation).
- (B) Shell ist WINZIG (< 2 KB) und enthält KEINEN Score/Content (kein
      cockpit/data-ticker/sb-num/backtest).
- (C) Flip-Write + app.html-FIRST-Ordering (Deploy-Race + S9-vor-Ordering):
      in beiden Write-Sites steht der `app.html`-Write VOR dem index.html-Shell-
      Write.
- (D) KEIN Content-Konsument liest index.html primär: alle Parser bevorzugen
      app.html (`_src = APP_HTML if APP_HTML.exists() else INDEX_HTML`), S9
      `html_path="app.html"`, smoke_render app.html-first.

Fixture-/Source-only. Kein Import von generate_report (zieht pandas → CI-rot,
§8n) und kein Live-Datei-Read.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
_KI = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
_AL = (ROOT / "alert.py").read_text(encoding="utf-8")
_SR = (ROOT / "scripts" / "smoke_render.js").read_text(encoding="utf-8")

_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail and not cond:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def _shell() -> str:
    m = re.search(r'_SHELL_HTML = """(.*?)"""', _GR, re.DOTALL)
    return m.group(1) if m else ""


def test_a_shell_pwa_complete() -> None:
    print("── (A) Shell vollständig PWA-tauglich ────────────────────────")
    sh = _shell()
    _check("A0 _SHELL_HTML-Konstante vorhanden", bool(sh), "_SHELL_HTML fehlt")
    for meta in ('name="apple-mobile-web-app-capable" content="yes"',
                 'name="apple-mobile-web-app-status-bar-style"',
                 'name="apple-mobile-web-app-title" content="Squeeze Report"'):
        _check(f"A-meta {meta[:38]}…", meta in sh,
               "Apple-Meta fehlt → PWA verliert Standalone/Icon/Titel")
    _check("A viewport-Meta", 'name="viewport"' in sh)
    _check("A charset", "charset" in sh)
    _check("A <title>", "<title>Squeeze Report</title>" in sh)
    _check("A location.replace('app.html?v=' + Date.now())",
           "location.replace('app.html?v=' + Date.now())" in sh,
           "Redirect-Weiche fehlt/abweichend")
    _check("A <noscript>-Refresh (JS aus)",
           "<noscript>" in sh and 'http-equiv="refresh"' in sh
           and "url=app.html" in sh)
    _check("A sichtbarer Fallback-Link <a href=app.html>",
           'href="app.html"' in sh, "sichtbarer Fallback-Link fehlt (404-Mitigation)")


def test_b_shell_small_no_content() -> None:
    print("── (B) Shell winzig (<2 KB) + KEIN Content ───────────────────")
    sh = _shell()
    n = len(sh.encode("utf-8"))
    _check(f"B1 Shell < 2 KB (ist {n} B)", n < 2048, f"{n} B ≥ 2048")
    low = sh.lower()
    _check("B2 kein Score/Content in der Shell",
           not any(k in low for k in ("cockpit", "data-ticker", "sb-num",
                                      "backtest", "conviction", "app_data")),
           "Shell enthält Content-Marker → wäre keine reine Weiche")


def test_c_flip_ordering() -> None:
    print("── (C) Flip-Write + app.html-FIRST (Race/S9-Ordering) ────────")
    # Content-Write: app.html (html) VOR index.html (_SHELL_HTML).
    content = (
        'with open("app.html", "w", encoding="utf-8") as fh:\n'
        '        fh.write(html)\n'
        '    with open("index.html", "w", encoding="utf-8") as fh:\n'
        '        fh.write(_SHELL_HTML)'
    )
    _check("C1 Content: app.html-Write VOR index.html-Shell-Write",
           content in _GR, "app.html-first-Ordering im Content-Write fehlt")
    # Error-Write: gleiches Muster.
    _check("C2 Error-Page: app.html VOR index.html-Shell",
           _GR.count(content) >= 2, "app.html-first fehlt im Error-Pfad")
    _check("C3 index.html schreibt NUR die Shell (nie html)",
           'with open("index.html", "w", encoding="utf-8") as fh:\n        fh.write(html)' not in _GR)


def test_d_no_content_consumer_on_index() -> None:
    print("── (D) Kein Content-Konsument liest index.html primär ────────")
    repoint = "_src = APP_HTML if APP_HTML.exists() else INDEX_HTML"
    _check("D1 ki_agent bevorzugt app.html (_src-Repoint)", repoint in _KI)
    _check("D2 alert bevorzugt app.html (_src-Repoint)", repoint in _AL)
    _check("D3 S9 prüft app.html (html_path)", 'html_path="app.html"' in _GR)
    _check("D4 smoke_render app.html-first",
           "fs.existsSync(APP_HTML_PATH) ? APP_HTML_PATH : INDEX_HTML_PATH" in _SR)
    # Es darf kein DIREKTER Content-Read von index.html mehr existieren
    # (INDEX_HTML.read_text ohne _src-Fallback).
    _check("D5 kein direkter INDEX_HTML.read_text in ki_agent/alert",
           "INDEX_HTML.read_text" not in _KI and "INDEX_HTML.read_text" not in _AL,
           "direkter index.html-Content-Read verblieben → Bruch nach Flip")


def main() -> int:
    for fn in (test_a_shell_pwa_complete, test_b_shell_small_no_content,
               test_c_flip_ordering, test_d_no_content_consumer_on_index):
        fn()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (Bootstrap-Shell Phase 1: PWA-vollständige "
          "Shell + winzig/kein Content + app.html-first-Flip + kein Content-"
          "Konsument auf index.html).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
