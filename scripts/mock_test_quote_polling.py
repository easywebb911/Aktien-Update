"""Mock-Tests für Live-Quote-Polling (Cloudflare-Worker-basiert).

Architektur-Anker: CLAUDE.md-Sektion „Live-Quote-Polling" + README in
``cloudflare/quote-proxy/``. Frontend-Modul lebt in
``generate_report.py`` (JS-Block); Worker-Code in
``cloudflare/quote-proxy/worker.js``.

Tests:
  1. Worker-File-Bundle vorhanden + valides JS-Schema
  2. Worker hat allowed-origins + CORS-Header + Yahoo-Mapping
  3. Workflow injiziert QUOTE_PROXY_URL-Secret in den Generate-Step
  4. generate_report.py liest QUOTE_PROXY_URL aus ENV mit URL-Sanitize
  5. JS-Konstante ``QUOTE_PROXY_URL`` als Render-Zeit-Placeholder
  6. JS-Polling-Modul: alle Funktionen vorhanden + window-exposed
  7. wlExpand-Pfad: Start/Stop verdrahtet
  8. Top-10 Dauer-Polling (DOMContentLoaded-Hook + _quoteEnsureLiveDot)
  9. CSS für .quote-live-dot in templates/head.jinja
 10. CLAUDE.md-Pflichtcheck: keine unescapten ${...}-Vars im f-String
 11. Pythonische Replikation des Patch-Wert-Formats (chg → "+12.9%")
 12. URL-Sanitize-Pythonisch: gültige URL akzeptiert, Garbage rejected
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# === 1-2 — Worker-Files ====================================================

def test_worker_files_exist():
    base = ROOT / "cloudflare" / "quote-proxy"
    for fn in ("worker.js", "wrangler.toml", "README.md"):
        assert (base / fn).exists(), f"{fn} fehlt in cloudflare/quote-proxy/"


def test_worker_yahoo_mapping_and_cors():
    src = (ROOT / "cloudflare" / "quote-proxy" / "worker.js").read_text(
        encoding="utf-8")
    # Yahoo v8 chart endpoint (v7 verlangt seit Mai 2026 Crumb-Auth → HTTP 401)
    assert "query1.finance.yahoo.com/v8/finance/chart/" in src, (
        "Yahoo-v8-Chart-URL fehlt im Worker (v7 ist nicht mehr ohne Crumb-Auth nutzbar)")
    assert "v7/finance/quote" not in src, (
        "v7-Quote-Endpoint sollte nicht mehr im Worker stehen — er antwortet HTTP 401")
    # CORS-Allow-List
    assert "ALLOWED_ORIGINS" in src and "easywebb911.github.io" in src, (
        "CORS-Allow-List für GitHub-Pages fehlt")
    # User-Agent (Yahoo blockt sonst)
    assert "User-Agent" in src, "User-Agent-Header fehlt im Yahoo-Fetch"
    # Mapping aus meta auf flat-Response {ticker, price, change, change_abs,
    # volume, market_state, prev_close, ts}
    for field in ("regularMarketPrice", "chartPreviousClose",
                  "regularMarketVolume", "marketState",
                  "change_abs", "prev_close", "market_state"):
        assert field in src, f"Feld {field} fehlt im Worker-Response-Mapping"
    # change_abs muss berechnet werden (price - prev_close)
    assert "price - prevClose" in src, (
        "change_abs-Berechnung (price - prevClose) fehlt im Worker")


# === 3 — Workflow ==========================================================

def test_workflow_injects_quote_proxy_url():
    yml = (ROOT / ".github" / "workflows" / "daily-squeeze-report.yml"
           ).read_text(encoding="utf-8")
    assert "QUOTE_PROXY_URL:" in yml, (
        "QUOTE_PROXY_URL-ENV fehlt im Generate-Step")
    assert "secrets.QUOTE_PROXY_URL" in yml, (
        "QUOTE_PROXY_URL wird nicht aus dem Repo-Secret gelesen")


# === 4-5 — generate_report.py ENV → JS-Konstante ==========================

def test_generate_report_reads_quote_proxy_url_env():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    assert 'os.environ.get("QUOTE_PROXY_URL"' in src, (
        "QUOTE_PROXY_URL wird nicht aus ENV gelesen")
    # Sanitize-Regex: https + Host (a-zA-Z0-9.-)
    assert "re.match" in src and "https://" in src, (
        "URL-Sanitize-Regex fehlt für QUOTE_PROXY_URL")


def test_js_constant_placeholder():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    assert "const QUOTE_PROXY_URL = '{quote_proxy_url_js}'" in src, (
        "JS-Konstante QUOTE_PROXY_URL = '{quote_proxy_url_js}' fehlt — "
        "Render-Zeit-Substitution würde nicht greifen")
    assert "QUOTE_POLL_INTERVAL_MS = 15000" in src, (
        "15-s-Polling-Intervall-Konstante fehlt")


# === 6 — Polling-Modul =====================================================

def test_polling_module_functions_defined():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    for fn_name in ("_quoteSetIndicator", "_quotePatchScope",
                    "_quoteFetchOnce", "_ensureQuoteVisibilityHook",
                    "_startQuotePoll", "_stopQuotePoll"):
        assert f"function {fn_name}(" in src, (
            f"Polling-Funktion {fn_name} fehlt im JS-Block")


def test_polling_module_window_exposed():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    assert "window._startQuotePoll = _startQuotePoll" in src, (
        "_startQuotePoll wird nicht auf window exposed — wlExpand kann "
        "es aus der WL-IIFE nicht aufrufen")
    assert "window._stopQuotePoll  = _stopQuotePoll" in src, (
        "_stopQuotePoll wird nicht auf window exposed")


def test_polling_module_visibilitychange():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    assert "visibilitychange" in src and "document.visibilityState" in src, (
        "visibilitychange-Handler fehlt im Polling-Modul")


def test_fetch_uses_v8_schema():
    """_quoteFetchOnce muss das neue flat-Schema parsen, nicht mehr
    das alte quoteResponse.result/quotes[]-Array."""
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # URL-Param ist `?ticker=` (single-ticker), nicht `?symbols=`
    assert "/?ticker=${{encodeURIComponent(ticker)}}" in src, (
        "Frontend ruft den Worker nicht mit ?ticker= auf — v8 ist single-ticker")
    # Response wird flach gelesen (q.ticker, q.price, q.change), kein quotes[]
    assert "q.ticker !== ticker" in src, (
        "Frontend prüft nicht das flat-Schema-Feld q.ticker")
    # Tages-Prozent + Tages-Absolutwert werden beide an _quotePatchScope
    # durchgereicht (Cockpit-Header: ".cockpit-change" zeigt
    # "▲ +0.69 (+12.63%)" — braucht Absolutwert in USD).
    assert "q.change, q.change_abs)" in src, (
        "Frontend reicht q.change/q.change_abs nicht an _quotePatchScope")
    # Alte Indikatoren des v7-Schemas dürfen nicht mehr im Fetch-Pfad sein
    assert "data.quotes" not in src, (
        "Alter v7-Schema-Pfad data.quotes ist noch da — sollte entfernt sein")
    assert "q.symbol !== ticker" not in src, (
        "Alter v7-Symbol-Check ist noch da")


# === 7 — wlExpand-Pfad =====================================================

def test_wl_expand_lifecycle():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # Im wlExpand-Block muss sowohl Start- als auch Stop-Aufruf vorkommen
    match = re.search(
        r"window\.wlExpand\s*=\s*function.*?console\.error\('wlExpand",
        src, re.DOTALL)
    assert match, "wlExpand-Block nicht gefunden"
    block = match.group(0)
    assert "window._startQuotePoll(body, ticker)" in block, (
        "_startQuotePoll wird in wlExpand nicht aufgerufen")
    assert "window._stopQuotePoll(ticker)" in block, (
        "_stopQuotePoll wird in wlExpand nicht aufgerufen")


# === 8 — Dauer-Polling-Pfad (Top-10) =======================================

def test_top10_continuous_polling():
    """Seit 20.05.2026 läuft das Polling für alle Top-10-Karten als
    Dauer-Polling beim Page-Load (auch wenn Karte zugeklappt ist).
    toggleDetails managed das Polling nicht mehr — Bug-Fix für
    Cockpit-".price-tag"/".cockpit-price"-Selektor-Mismatch."""
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # DOMContentLoaded-Hook iteriert über article.card[data-ticker]
    assert "article.card[data-ticker]" in src, (
        "DOMContentLoaded-Hook scannt nicht article.card[data-ticker]")
    # Im Hook wird _startQuotePoll pro Karte aufgerufen
    hook_match = re.search(
        r"DOMContentLoaded.*?_startQuotePoll\(card, ticker\)",
        src, re.DOTALL)
    assert hook_match, (
        "DOMContentLoaded-Hook ruft _startQuotePoll(card, ticker) nicht auf")
    # Live-Dot-Lazy-Inject lebt jetzt im _startQuotePoll-Pfad (Helper
    # _quoteEnsureLiveDot), damit zugeklappte Karten den Dot trotzdem
    # bekommen.
    assert "_quoteEnsureLiveDot" in src, (
        "Helper _quoteEnsureLiveDot fehlt")


# === 9 — CSS ===============================================================

def test_quote_live_dot_css():
    css = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")
    assert ".quote-live-dot" in css, "CSS-Klasse .quote-live-dot fehlt"
    for state in ("quote-live-on", "quote-live-stale", "quote-live-paused"):
        assert state in css, f"CSS-State .{state} fehlt"


# === 10 — Pflichtcheck =====================================================

def test_no_unescaped_js_template_vars():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    hits = re.findall(r"\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}", src)
    assert not hits, (
        f"Unescapte JS-Template-Vars im f-String: {hits[:5]}")


# === 11 — Wert-Format ======================================================

def _format_chg(change):
    """Pythonische Nachbildung der JS-Formel im Polling-Patcher:
        sign + change.toFixed(1) + '%'
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


def test_chg_format_basic():
    assert _format_chg(12.906854) == "+12.9%"
    assert _format_chg(-3.456)    == "-3.5%"
    assert _format_chg(0)         == "+0.0%"
    assert _format_chg(None)      is None
    assert _format_chg("garbage") is None
    assert _format_chg(float("nan")) is None


# === 12 — URL-Sanitize-Logik (Pythonisch) ==================================

_SANITIZE_RE = re.compile(r"^https://[A-Za-z0-9.\-]+(/[A-Za-z0-9._\-/]*)?$")


def test_url_sanitize_accepts_valid():
    for url in (
        "https://quote-proxy.foo.workers.dev",
        "https://quote.example.com/api",
        "https://x-y-z.workers.dev/path/sub",
    ):
        assert _SANITIZE_RE.match(url), f"Gültige URL abgelehnt: {url}"


def test_url_sanitize_rejects_invalid():
    for url in (
        "http://insecure.com",                    # nur https
        "https://foo.com?token=secret",           # kein Query
        "https://foo.com#anchor",                 # kein Anker
        "javascript:alert(1)",                    # XSS
        "https://foo bar.com",                    # Whitespace
        "",                                        # leer
    ):
        assert not _SANITIZE_RE.match(url), f"Ungültige URL akzeptiert: {url}"


# === Runner =================================================================

def main() -> None:
    tests = [
        ("Worker-File-Bundle vorhanden",                  test_worker_files_exist),
        ("Worker: Yahoo-Mapping + CORS + UA",              test_worker_yahoo_mapping_and_cors),
        ("Workflow: QUOTE_PROXY_URL-ENV im Generate-Step", test_workflow_injects_quote_proxy_url),
        ("generate_report.py: ENV-Read + Sanitize",        test_generate_report_reads_quote_proxy_url_env),
        ("JS-Konstante QUOTE_PROXY_URL als Placeholder",   test_js_constant_placeholder),
        ("Polling-Modul: alle Funktionen definiert",       test_polling_module_functions_defined),
        ("Polling-Modul: window-exposed",                  test_polling_module_window_exposed),
        ("Polling-Modul: visibilitychange-Handler",        test_polling_module_visibilitychange),
        ("Frontend: v8-Schema (ticker, price, change)",    test_fetch_uses_v8_schema),
        ("wlExpand: Start/Stop verdrahtet",                test_wl_expand_lifecycle),
        ("Top-10 Dauer-Polling (DOMContentLoaded-Hook)",   test_top10_continuous_polling),
        ("CSS .quote-live-dot + 3 States",                  test_quote_live_dot_css),
        ("Keine unescapten ${...} im f-String",            test_no_unescaped_js_template_vars),
        ("Wert-Format-Replikation",                        test_chg_format_basic),
        ("URL-Sanitize akzeptiert valide URLs",             test_url_sanitize_accepts_valid),
        ("URL-Sanitize rejected Garbage/XSS",               test_url_sanitize_rejects_invalid),
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
