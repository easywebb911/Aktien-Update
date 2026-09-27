"""Mock-Tests für den BS4-Parser-Fix in ``get_finviz_screener_v111()``
(27.09.2026).

BEFUND (Diagnose 27.09.2026, per Easy-Live-Check bestätigt): der frühere
Regex-Parser (``quote\\?t=<TICKER>``-Link-Muster über den rohen Response-
Text) lieferte in allen 46 geprüften Läufen der letzten 30 Tage
``item_count=0`` — die URL/Filter-Parameter selbst funktionieren nachweislich
(Easy hat die exakte URL live im Browser geprüft: 12 valide Ticker,
XNDU/TYRA/SRZN/SHOE/PRME/OXM/ORIC/MATW/LRMR/IMVT/GRAL/AESI), der Regex griff
aber nicht mehr auf das aktuelle Markup.

FIX (generate_report.py:get_finviz_screener_v111(), ~Z. 824): Regex ersetzt
durch BS4-Tabellen-Parsing — exakt dasselbe Grundmuster wie das bereits
funktionierende ``get_finviz_candidates()`` (v141): Tabelle über die
Header-Zeile ("Ticker"-Spalte) finden, Ticker-Wert aus der entsprechenden
Zelle jeder Datenzeile lesen. NUR der Parser wurde geändert — URL, Filter-
Parameter, FINVIZ_MAX_TICKERS-Cap und die Aufrufstelle (Zeile ~17364)
bleiben unverändert.

Test-Standard: treibt die ECHTE ``generate_report.get_finviz_screener_v111()``
über einen gemockten ``requests.get`` (reale HTML-Fixtures, kein
Logik-Replikat). Drei Pflicht-Szenarien + eine Cap-Gegenprobe:
  1. Realistische Tabellen-Struktur mit den 12 live-bestätigten Tickern
     → korrekte Extraktion (der eigentliche Bug-Fix-Nachweis).
  2. Leere Ergebnis-Tabelle (echtes "0 Treffer"-Szenario, Header vorhanden,
     keine Datenzeilen) → [] ohne Crash (kein False-Positive).
  3. Kaputte/unerwartete HTML-Struktur (keine Tabelle mit "Ticker"-Spalte,
     z. B. eine Fehler-/Redirect-Seite) → fail-soft [] ohne Crash.
  4. ``max_tickers``-Cap wird tatsächlich respektiert (Gegenprobe, dass der
     Cap durch den Parser-Wechsel nicht versehentlich verändert wurde).

HINWEIS ZUR CI-EINORDNUNG: dieser Test treibt echtes BeautifulSoup-
Tabellen-Parsing (``bs4``/``lxml``) — keine Stub-Attrappe. Die Minimal-CI
(``pr-checks.yml`` installiert bewusst NUR jinja2+pyyaml, kein
``requirements.txt``/bs4/lxml) kann das nicht ausführen. Analog zu
``mock_test_atm_iv_zero_guard.py`` (EXCLUDED, Grund "pandas erforderlich")
gehört dieser Test in dieselbe EXCLUDED-Kategorie (Grund: "bs4/lxml
erforderlich"), NICHT in die ALLOWLIST. Lokal verifiziert (bs4+lxml
installiert) — alle Tests grün.

Ausführung: ``python scripts/mock_test_finviz_v111_bs4_parser.py``.
"""
from __future__ import annotations

import pathlib
import sys
import types
from unittest import mock

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


# ── Heavy-Dependency-Stubs (identisch zu mock_test_atm_iv_zero_guard.py,
#    NUR yfinance/requests/deep_translator/watchlist — bs4 bleibt ECHT,
#    weil get_finviz_screener_v111() jetzt reale BS4-Tabellen-Operationen
#    ausführt; das ist der genaue Umkehrfall zu atm_iv, wo pandas echt
#    blieb und bs4 gestubbt war). ─────────────────────────────────────────
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


class _FakeResp:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


# Live-bestätigte Ticker (Easy-Browser-Check 27.09.2026, exakte v=111-URL).
LIVE_TICKERS = ["XNDU", "TYRA", "SRZN", "SHOE", "PRME", "OXM",
                "ORIC", "MATW", "LRMR", "IMVT", "GRAL", "AESI"]

# Realistische Finviz-Screener-Spalten (Reihenfolge/Namen analog zur
# bestehenden get_finviz_candidates()-Erwartung — "Ticker" ist eine von
# mehreren Spalten, nicht die einzige).
_HEADERS = ["No.", "Ticker", "Company", "Sector", "Industry", "Country",
            "Market Cap", "P/E", "Price", "Change", "Volume"]


def _row_html(cells: list[str]) -> str:
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def _data_row(i: int, ticker: str) -> str:
    return _row_html([str(i), ticker, f"{ticker} Inc", "Healthcare",
                       "Biotechnology", "USA", "500.00M", "12.34",
                       "5.67", "3.20%", "1234567"])


def _build_screener_html(tickers: list[str]) -> str:
    """Baut eine realistische Finviz-Screener-Seite: MEHRERE <table>-
    Elemente (Layout-Tabellen kommen auf echten Finviz-Seiten vor), nur
    eine davon ist die Datentabelle mit "Ticker"-Header-Spalte — die
    Such-Logik muss die richtige unter mehreren finden."""
    layout_table = "<table><tr><td>Finviz</td><td>Header-Leiste</td></tr></table>"
    header_row = _row_html(_HEADERS)
    data_rows = "".join(_data_row(i, t) for i, t in enumerate(tickers, start=1))
    data_table = f"<table>{header_row}{data_rows}</table>"
    return f"<html><body>{layout_table}{data_table}</body></html>"


def _build_empty_results_html() -> str:
    """Echtes '0 Treffer'-Szenario: Header-Zeile vorhanden (Finviz rendert
    die Tabellen-Struktur auch bei leerem Filter-Ergebnis), aber keine
    Datenzeilen darunter."""
    header_row = _row_html(_HEADERS)
    data_table = f"<table>{header_row}</table>"
    return f"<html><body>{data_table}</body></html>"


def _build_broken_html() -> str:
    """Kaputte/unerwartete Struktur: Tabellen vorhanden, aber KEINE mit
    einer "Ticker"-Spalte — z. B. eine Fehler-/Redirect-/Consent-Seite."""
    return ("<html><body>"
            "<table><tr><td>Please verify you are human</td></tr></table>"
            "<table><tr><td>Cloudflare</td><td>Checking your browser</td></tr></table>"
            "</body></html>")


def _run(html: str, status_code: int = 200, max_tickers=None):
    with mock.patch.object(gr.requests, "get",
                            lambda *a, **k: _FakeResp(html, status_code)):
        return gr.get_finviz_screener_v111(max_tickers=max_tickers)


def test_1_realistic_table_extracts_live_confirmed_tickers():
    html = _build_screener_html(LIVE_TICKERS)
    result = _run(html)
    tickers = [c["ticker"] for c in result]
    _check("T1 alle 12 live-bestätigten Ticker extrahiert",
           tickers == LIVE_TICKERS, tickers)
    _check("T1 n == 12", len(result) == 12, len(result))
    first = result[0]
    _check("T1 Candidate-Dict-Schema vollständig",
           first.get("ticker") == "XNDU"
           and first.get("market") == "US"
           and first.get("source") == "finviz_screener_v111"
           and first.get("source_pools") == [gr.SOURCE_POOL_FINVIZ_V111]
           and first.get("short_float") == 0.0
           and first.get("short_ratio") == 0.0
           and first.get("rel_volume") == 0.0
           and first.get("company_name") == "XNDU",
           first)


def test_2_empty_results_returns_empty_list_no_crash():
    html = _build_empty_results_html()
    result = _run(html)
    _check("T2 leere Ergebnis-Tabelle -> []", result == [], result)


def test_3_broken_markup_fails_soft_no_crash():
    html = _build_broken_html()
    result = _run(html)
    _check("T3 kaputtes/fremdes Markup -> [] (kein Crash)", result == [], result)


def test_3b_no_table_at_all_fails_soft():
    html = "<html><body><p>Access Denied</p></body></html>"
    result = _run(html)
    _check("T3b gar keine Tabelle -> [] (kein Crash)", result == [], result)


def test_3c_http_error_still_returns_empty_unaffected_by_parser_change():
    result = _run("<html>ignored</html>", status_code=503)
    _check("T3c HTTP-Fehler weiterhin -> [] (Parser-Wechsel berührt das "
           "HTTP-Guard nicht)", result == [], result)


def test_4_max_tickers_cap_respected():
    result = _run(_build_screener_html(LIVE_TICKERS), max_tickers=5)
    _check("T4 max_tickers-Cap respektiert (5 von 12)",
           len(result) == 5, len(result))
    _check("T4 Cap liefert die ersten 5 in Tabellen-Reihenfolge",
           [c["ticker"] for c in result] == LIVE_TICKERS[:5],
           [c["ticker"] for c in result])


def test_5_default_cap_is_finviz_max_tickers_unverändert():
    # FINVIZ_MAX_TICKERS selbst nicht geändert (Auftrag: Cap unverändert
    # übernehmen) — Gegenprobe direkt gegen die Konstante, kein Hardcode.
    _check("T5 FINVIZ_MAX_TICKERS unverändert bei 50",
           gr.FINVIZ_MAX_TICKERS == 50, gr.FINVIZ_MAX_TICKERS)


def test_6_disabled_flag_short_circuits_before_any_request():
    with mock.patch.object(gr, "FINVIZ_SCREENER_ENABLED", False):
        with mock.patch.object(
                gr.requests, "get",
                lambda *a, **k: (_ for _ in ()).throw(
                    AssertionError("requests.get haette nicht aufgerufen werden duerfen"))):
            result = gr.get_finviz_screener_v111()
    _check("T6 FINVIZ_SCREENER_ENABLED=False -> [] ohne Request", result == [])


def main() -> int:
    test_1_realistic_table_extracts_live_confirmed_tickers()
    test_2_empty_results_returns_empty_list_no_crash()
    test_3_broken_markup_fails_soft_no_crash()
    test_3b_no_table_at_all_fails_soft()
    test_3c_http_error_still_returns_empty_unaffected_by_parser_change()
    test_4_max_tickers_cap_respected()
    test_5_default_cap_is_finviz_max_tickers_unverändert()
    test_6_disabled_flag_short_circuits_before_any_request()

    if _fails:
        print(f"\n{len(_fails)} Test(s) FEHLGESCHLAGEN: {_fails}")
        return 1
    print("\nAlle finviz_v111_bs4_parser-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
