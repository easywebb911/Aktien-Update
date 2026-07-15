"""Mock-Test — Bootstrap-Shell PHASE 0 (Parser-Repoint, KEIN Flip).

KONTEXT (Diagnose 14.07.): iOS-PWA-Launcher öffnet die parameterlose start_url
aus dem Standalone-Cache → alte index.html. Der strukturelle Fix ist eine
Bootstrap-Shell (Phase 1). Phase 0 legt den kanonischen Content-Pfad ``app.html``
neben ``index.html`` an und stellt ALLE Content-Parser darauf um — während
``index.html`` unverändert die volle Seite bleibt (KEIN Flip, nichts bricht).

Verifiziert:

- (A) Flip-Write (seit Phase 1): app.html = voller Content, index.html = Shell
      (_SHELL_HTML). Details der Shell selbst in mock_test_bootstrap_shell_phase1.
- (A-alt, Phase 0, historisch): Doppel-Write index.html UND
      app.html (byte-identisch, gleiche ``html``-Variable) — Content-Write UND
      Error-Page. index.html-Write bleibt erhalten (kein Flip).
- (B) S9-Repoint: html_path="app.html" + crit-Re-Read open("app.html")
      (der gefährlichste Punkt — S9-crit = sys.exit = kein Deploy).
- (C) config.APP_HTML = Path("app.html"); INDEX_HTML bleibt index.html.
- (D) ki_agent.parse_top_tickers liest app.html (bevorzugt), Fallback index.html,
      leer nur wenn beide fehlen — KRITISCH: die Top-10-Quelle.
- (E) alert.parse_index_html liest app.html (bevorzugt), Fallback index.html.
- (F) Golden unberührt: mock_test_outer_page_golden rendert in-memory
      (generate_html_v1), liest KEINE Datei → vom Split unabhängig.
- (G) Workflow git-add app.html; Jekyll-Exclude deckt app.html.

Fixture-only (Parser gegen Temp-Dateien via Monkeypatch der Modul-Konstanten).
Kein Kontakt mit Live-index.html/app.html.
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import types

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


def _install_stubs() -> None:
    for n in ("yfinance", "requests", "bs4", "deep_translator", "watchlist"):
        if n in sys.modules:
            continue
        m = types.ModuleType(n)
        if n == "yfinance":
            m.download = lambda *a, **k: None
            m.Ticker = lambda *a, **k: None
        elif n == "requests":
            m.Session = lambda *a, **k: types.SimpleNamespace(
                headers=types.SimpleNamespace(update=lambda *a, **k: None))
            m.get = lambda *a, **k: None
            m.post = lambda *a, **k: None
            m.exceptions = types.SimpleNamespace(RequestException=Exception)
        elif n == "bs4":
            m.BeautifulSoup = lambda *a, **k: None
        elif n == "deep_translator":
            m.GoogleTranslator = lambda *a, **k: types.SimpleNamespace(
                translate=lambda s: s)
        elif n == "watchlist":
            m.WATCHLIST = []
        sys.modules[n] = m


_GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def test_a_flip_write() -> None:
    # (A) — seit Phase 1 (Flip): app.html trägt den vollen Content, index.html
    # ist die Shell (_SHELL_HTML). Vorher Phase 0: beide byte-identisch.
    print("── (A) Flip-Write: app.html=Content, index.html=Shell (Phase 1) ──")
    _check("A1 Content-Write app.html = voller html",
           _GR.count('with open("app.html", "w", encoding="utf-8") as fh:\n        fh.write(html)') >= 1,
           "app.html-Content-Write fehlt")
    _check("A2 index.html = _SHELL_HTML (Flip)",
           'with open("index.html", "w", encoding="utf-8") as fh:\n        fh.write(_SHELL_HTML)' in _GR,
           "index.html schreibt nicht die Shell → kein Flip")
    _check("A3 kein voller Content mehr nach index.html",
           'with open("index.html", "w", encoding="utf-8") as fh:\n        fh.write(html)' not in _GR,
           "index.html schreibt noch die volle Seite (html)")
    _check("A4 Error-Page → app.html; index.html = Shell",
           'log.info("Error page → app.html (Content); index.html = Shell")' in _GR)


def test_b_s9_repoint() -> None:
    print("── (B) S9-Repoint auf app.html (crit-Exit-Pfad) ──────────────")
    _check("B1 S9 html_path=\"app.html\"", 'html_path="app.html"' in _GR,
           "S9 prüft nicht app.html → Shell würde crit-Exit auslösen")
    _check("B2 S9-crit-Re-Read open(app.html)",
           'with open("app.html", "r", encoding="utf-8") as _fh:' in _GR)
    _check("B3 kein S9 html_path=\"index.html\" mehr",
           'html_path="index.html"' not in _GR)


def test_c_config() -> None:
    print("── (C) config.APP_HTML / INDEX_HTML ─────────────────────────")
    import config
    _check("C1 config.APP_HTML == Path('app.html')",
           str(config.APP_HTML) == "app.html", f"got {config.APP_HTML}")
    _check("C2 config.INDEX_HTML bleibt index.html (Seite, kein Flip)",
           str(config.INDEX_HTML) == "index.html", f"got {config.INDEX_HTML}")


def _write(p: pathlib.Path, s: str) -> None:
    p.write_text(s, encoding="utf-8")


_KI = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
_AL = (ROOT / "alert.py").read_text(encoding="utf-8")

# Kanonisches Repoint-Muster (Source-Grep, CI-minimal-safe — kein Import).
_REPOINT = "_src = APP_HTML if APP_HTML.exists() else INDEX_HTML"


def test_d_ki_agent_parse() -> None:
    print("── (D) ki_agent.parse_top_tickers → app.html (Top-10-Quelle) ─")
    # (D-Source, immer): der Repoint + Fallback steht im Code. CI-minimal-safe —
    # ki_agent importiert pandas/yfinance (nicht im CI-Install), daher KEIN
    # Modul-Import im harten Gate (Lehre §8n Sandbox-CI-Divergenz; analog
    # mock_test_ki_agent_coverage, das ebenfalls nur Source liest).
    _check("D-src1 parse_top_tickers: app.html bevorzugt, Fallback index.html",
           _REPOINT in _KI, "Repoint-Muster fehlt in ki_agent.parse_top_tickers")
    _check("D-src2 liest über _src.read_text (nicht mehr INDEX_HTML.read_text)",
           "_src.read_text(encoding=\"utf-8\")" in _KI
           and "INDEX_HTML.read_text" not in _KI,
           "ki_agent liest noch direkt INDEX_HTML")
    # (D-Live, best-effort): echter Funktions-Lauf, wenn die Deps da sind (Dev-
    # Env). In CI-minimal übersprungen → Source-Gate oben bleibt hart.
    _install_stubs()
    try:
        import ki_agent
    except Exception as exc:
        print(f"    ⊘ ki_agent-Import übersprungen (CI-minimal: {type(exc).__name__}) "
              "— D-Source bleibt hart.")
        return
    tmp = pathlib.Path(tempfile.mkdtemp())
    app, idx = tmp / "app.html", tmp / "index.html"
    ki_agent.APP_HTML, ki_agent.INDEX_HTML = app, idx
    _write(app, '<span class="ticker">FOO</span><span class="ticker">BAR</span>')
    _write(idx, '<span class="ticker">WRONG</span>')
    _check("D1 liest app.html (FOO,BAR — nicht index/WRONG)",
           ki_agent.parse_top_tickers() == ["FOO", "BAR"],
           f"got {ki_agent.parse_top_tickers()}")
    app.unlink()
    _check("D2 Fallback → index.html wenn app.html fehlt (WRONG)",
           ki_agent.parse_top_tickers() == ["WRONG"],
           f"got {ki_agent.parse_top_tickers()}")
    idx.unlink()
    _check("D3 beide fehlen → [] (kein Crash)",
           ki_agent.parse_top_tickers() == [])


def test_e_alert_parse() -> None:
    print("── (E) alert.parse_index_html → app.html ────────────────────")
    _check("E-src1 parse_index_html: app.html bevorzugt, Fallback index.html",
           _REPOINT in _AL, "Repoint-Muster fehlt in alert.parse_index_html")
    _check("E-src2 alert hat eigenes APP_HTML = Path('app.html')",
           'APP_HTML        = Path("app.html")' in _AL,
           "alert.APP_HTML fehlt")
    _install_stubs()
    try:
        import alert
    except Exception as exc:
        print(f"    ⊘ alert-Import übersprungen (CI-minimal: {type(exc).__name__}) "
              "— E-Source bleibt hart.")
        return
    tmp = pathlib.Path(tempfile.mkdtemp())
    app, idx = tmp / "app.html", tmp / "index.html"
    alert.APP_HTML, alert.INDEX_HTML = app, idx
    _write(app, '<article class="card" id="c0"><span class="ticker">FOO</span></article>')
    _write(idx, '<article class="card" id="c0"><span class="ticker">WRONG</span></article>')
    got = [r.get("ticker") for r in alert.parse_index_html()]
    _check("E1 liest app.html (FOO — nicht WRONG)", got == ["FOO"], f"got {got}")
    app.unlink()
    got2 = [r.get("ticker") for r in alert.parse_index_html()]
    _check("E2 Fallback → index.html (WRONG)", got2 == ["WRONG"], f"got {got2}")


def test_f_golden_path_agnostic() -> None:
    print("── (F) Golden unberührt (in-memory-Render) ──────────────────")
    gsrc = (ROOT / "scripts" / "mock_test_outer_page_golden.py").read_text(encoding="utf-8")
    _check("F1 Golden rendert generate_html_v1 (kein Datei-Read)",
           "generate_html_v1(" in gsrc
           and 'open("index.html"' not in gsrc and 'open("app.html"' not in gsrc,
           "Golden liest eine HTML-Datei → wäre vom Split betroffen")


def test_g_deploy_and_jekyll() -> None:
    print("── (G) Workflow git-add + Jekyll-Exclude ────────────────────")
    wf = (ROOT / ".github" / "workflows" / "daily-squeeze-report.yml").read_text(encoding="utf-8")
    _check("G1 Workflow git add app.html", "git add app.html" in wf)
    _check("G2 Workflow git add index.html erhalten", "git add index.html" in wf)
    import yaml
    cfg = yaml.safe_load((ROOT / "_config.yml").read_text(encoding="utf-8"))
    excluded = set(cfg.get("exclude", []))
    _check("G3 app.html NICHT in _config.yml exclude",
           "app.html" not in excluded, f"exclude={excluded}")


def main() -> int:
    for fn in (test_a_flip_write, test_b_s9_repoint, test_c_config,
               test_d_ki_agent_parse, test_e_alert_parse,
               test_f_golden_path_agnostic, test_g_deploy_and_jekyll):
        fn()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (Bootstrap-Shell Phase 0: Doppel-Write + "
          "S9-Repoint + ki_agent/alert lesen app.html + Fallback + Golden "
          "unberührt + Deploy/Jekyll).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
