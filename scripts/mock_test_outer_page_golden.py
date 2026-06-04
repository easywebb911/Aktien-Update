"""Golden-File-Regressionstest für die Outer-Page des Reports (03.06.2026).

Beweist byte-genau, ob eine Code-Änderung den HTML-Output von
``generate_html_v1`` (der ~6900-Zeilen-f-String: Header, Watchlist,
Backtesting, Methodik, Datenquellen, JS, Footer) unbeabsichtigt verändert.

Der bestehende ``_render_test`` deckt nur Karten-Snippets ab; dieser Test
schließt die Outer-Page-Lücke — genau die Blöcke, in die real eingegriffen
wird.

SCOPE-SCHNITT (head.jinja/CSS ausgeklammert):
  Der Output ist ``f"\"\"{head_html}\\n<body>\\n…"\"\"`` (generate_report.py
  ~Z. 6601). ``head_html`` rendert das statische CSS+``<head>`` aus
  ``templates/head.jinja`` (89 KB, reines Jinja, würde nur Diff-Rauschen
  erzeugen). Der Golden beginnt beim **``<body>``**-Marker — HTML-strukturell
  eindeutig (genau 1× im Output, 0× in head.jinja), eine fundamentale
  HTML-Grenze, die nie still driftet. ``output[output.index("<body>"):]``.
  → CSS NICHT im Golden, dynamischer Body inkl. **JS-Block IST im Golden**
  (die JS-im-f-String-Bugs wie der ``.price-tag``-Vorfall sind der wertvollste
  Schutz; JS-Code ist render-deterministischer Literal-Text).

DETERMINISMUS (Fixture + Fixed-Clock, NULL Masking):
  - Fixed-Clock: ``datetime`` in generate_report auf einen festen Zeitpunkt
    gepatcht → der ``timestamp`` „Stand: …, HH:MM Uhr" ist fix (kein Masking).
  - ``_load_backtest_history`` → feste Liste (sonst backtest_count volatil).
  - ``_load_score_history`` → festes Dict (sonst wl_*_json volatil).
  - ``_SCORE_CONFIDENCE`` global leer ({} → computed_at "—", deterministisch).
  - ``_FX_USD_EUR`` global auf festen Wert (Default 0.92 reicht, explizit gesetzt).
  - ``stocks`` / ``watchlist_cards`` = eingefrorene Fixtures.
  Die ~15 ``Date.now()``-Treffer im Output sind **JavaScript** (Literal-Text,
  laufen erst im Browser) → render-deterministisch, bewusst NICHT neutralisiert.

GOLDEN: ``tests/golden/report_outer_page.html`` (committet, lesbar im Diff).
UPDATE: ``UPDATE_GOLDEN=1 python scripts/mock_test_outer_page_golden.py``
  schreibt das Golden neu (für GEWOLLTE Änderungen). Ohne Flag: Vergleich,
  bei Diff ROT mit Kontext-Hunk (±3 Zeilen, Zeilennummern, erwartet/ist).

Grenzen: KEINE Änderung an generate_html_v1 / Report-Logik. Nur Test +
Fixture + Golden. Kein Score-/Filter-Touch.
"""
from __future__ import annotations

import difflib
import os
import pathlib
import sys
import types
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GOLDEN_FILE = ROOT / "tests" / "golden" / "report_outer_page.html"

# Fester Render-Zeitpunkt für die Fixed-Clock (deterministischer timestamp).
_FIXED_NOW = datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc)
_FIXED_REPORT_DATE = "01.06.2026"


# ── Heavy-Dependency-Stubs (vor generate_report-Import) ─────────────────────
def _install_stubs() -> None:
    """generate_report importiert yfinance/bs4/requests/deep_translator/
    watchlist auf Modul-Ebene — im Sandbox/CI nicht (alle) installiert.
    Minimal stubben, ohne render-relevante Logik zu berühren."""
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


# ── Fixture: eingefrorener Test-Input ───────────────────────────────────────
def _fixture_stock(ticker: str, *, score: float, price: float,
                   change: float, rsi14: float | None = 61.0) -> dict:
    """Vollständig eingefrorener Stock — alle render-relevanten Felder fix.
    Fehlende Felder fängt _card via .get()-Defaults ab; die hier gesetzten
    decken die sichtbaren Render-Pfade (Score-Block, Detail-Tabelle, Drivers,
    Sparkline) ab.

    ``rsi14`` ist parametrierbar, um BEIDE Render-Zweige der RSI-Detail-Zeile
    abzudecken: ein Wert (61.0) rendert die ``<tr>RSI (14T)…``-Zeile, ``None``
    lässt sie weg (``_rsi_row = ""``) + leeres ``data-rsi``-Attribut."""
    return {
        "ticker": ticker, "score": score, "score_raw": score + 2.0,
        "price": price, "change": change, "change_5d": 4.2, "change_2d": 3.1,
        "change_3d": 5.0,
        "short_float": 28.0, "short_ratio": 6.5, "rel_volume": 3.4,
        "rsi14": rsi14, "ma50": price * 0.95, "ma200": price * 0.8,
        "market_cap": 1.2e9, "yf_market_cap": 1.2e9,
        "monster_score": score * 1.1, "setup": score, "earliness": 75,
        "agent_boost_score": 5, "agent_boost_pts": 5,
        "atm_iv": 0.85, "earnings_days": 9, "earnings_date_str": "10.06.2026",
        "sector": "Technology", "industry": "Software",
        "inst_ownership": 0.42, "borrow_rate": 12.0, "cost_to_borrow": 12.0,
        "utilization": None, "pc_ratio": 0.4, "regime": "bull",
        "sec_13f_note": "Insider-Käufe Q1", "expiry": "2026-06-19",
        "finra_data": {"trend": "up", "trend_pct": 22.0, "history": [],
                       "si_trend_source": "yfinance"},
        "short_float_source": "yfinance",
        "conviction": {"score": 78, "level": "high",
                       "action_text": "Conviction hoch — Setup, Earliness und "
                                      "Timing konvergieren.",
                       "components": {"setup": 28, "earliness": 21,
                                      "anomaly": 14, "regime": 11}},
        "ki_signal_score": 80, "ki_signal_drivers": "RVOL 3.4× + SEC 8-K",
        "options": {"pc_ratio": 0.4},
        "news": [], "anomaly": None,
        "sparkline": {"scores": [50.0, 55.0, score],
                      "dates": ["28.05.2026", "29.05.2026", "01.06.2026"],
                      "drivers": [[], [], ["RVOL 3.4×"]],
                      "trend": "up", "col": "#22c55e", "today": "01.06.2026"},
        "manual_personal": False,
    }


def _fixture_stocks() -> list[dict]:
    # AAAA: rsi14=61.0 → RSI-Detail-Zeile gerendert (Wert-Zweig).
    # BBBB: rsi14=None → RSI-Zeile weggelassen (None-Zweig) — deckt beide
    # Render-Pfade in EINEM Golden ab.
    return [
        _fixture_stock("AAAA", score=82.0, price=5.10, change=6.3),
        _fixture_stock("BBBB", score=71.5, price=12.40, change=-2.1,
                       rsi14=None),
    ]


def _fixture_backtest_history() -> list[dict]:
    """Feste Liste — nur die Länge (backtest_count) fließt in den Output."""
    return [{"date": "01.06.2026", "ticker": "AAAA", "score": 82.0,
             "return_10d": 5.0, "backtest_schema_version": 4}
            for _ in range(123)]


def _fixture_score_history() -> dict:
    """Festes Dict — fließt in wl_scores_json / wl_hist_json."""
    return {
        "AAAA": [["29.05.2026", 78.0], ["01.06.2026", 82.0]],
        "CRMD": [["29.05.2026", 60.0], ["01.06.2026", 56.0]],
    }


# ── Fixed-Clock-Datetime (deterministischer timestamp, kein Masking) ────────
class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return _FIXED_NOW.astimezone(tz) if tz else _FIXED_NOW.replace(tzinfo=None)


def _render_outer_page() -> str:
    """Rendert generate_html_v1 deterministisch und schneidet ab ``<body>``.

    Patcht NUR im Modul-Namespace des Tests (kein Produktionscode-Touch):
    datetime (Fixed-Clock), _load_backtest_history, _load_score_history,
    _SCORE_CONFIDENCE, _FX_USD_EUR, _DAILY_REPORT_COUNTS.
    """
    _orig = {
        "datetime": gr.datetime,
        "_load_backtest_history": gr._load_backtest_history,
        "_load_score_history": gr._load_score_history,
        "_SCORE_CONFIDENCE": getattr(gr, "_SCORE_CONFIDENCE", {}),
        "_FX_USD_EUR": getattr(gr, "_FX_USD_EUR", 0.92),
        "_DAILY_REPORT_COUNTS": getattr(gr, "_DAILY_REPORT_COUNTS", {}),
    }
    try:
        gr.datetime = _FixedDateTime
        gr._load_backtest_history = _fixture_backtest_history
        gr._load_score_history = _fixture_score_history
        gr._SCORE_CONFIDENCE = {}          # leer → computed_at "—" (determ.)
        gr._FX_USD_EUR = 0.92               # fester FX
        # Daily-Report-Häufigkeit fix (main() füllt das normal aus
        # backtest_history; der Test umgeht main()) — deckt den
        # „N× im Daily-Report"-Tag-Render-Pfad ab.
        gr._DAILY_REPORT_COUNTS = {"AAAA": 7, "BBBB": 3}
        full = gr.generate_html_v1(
            _fixture_stocks(), _FIXED_REPORT_DATE, watchlist_cards=None)
    finally:
        gr.datetime = _orig["datetime"]
        gr._load_backtest_history = _orig["_load_backtest_history"]
        gr._load_score_history = _orig["_load_score_history"]
        gr._SCORE_CONFIDENCE = _orig["_SCORE_CONFIDENCE"]
        gr._FX_USD_EUR = _orig["_FX_USD_EUR"]
        gr._DAILY_REPORT_COUNTS = _orig["_DAILY_REPORT_COUNTS"]

    # Scope-Schnitt: ab <body> (head.jinja/CSS raus). <body> ist genau 1× da.
    idx = full.find("<body>")
    if idx < 0:
        raise AssertionError("Scope-Schnitt-Marker '<body>' nicht im Output "
                             "gefunden — Struktur geändert?")
    return full[idx:]


def _context_diff(expected: str, actual: str) -> str:
    """Unified-Diff mit ±3 Zeilen Kontext + Zeilennummern."""
    diff = difflib.unified_diff(
        expected.splitlines(), actual.splitlines(),
        fromfile="golden (erwartet)", tofile="render (ist)",
        n=3, lineterm="")
    return "\n".join(diff)


def main() -> None:
    rendered = _render_outer_page()

    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_FILE.write_text(rendered, encoding="utf-8")
        n = rendered.count("\n") + 1
        print(f"  ✓ UPDATE_GOLDEN: Golden neu geschrieben "
              f"({len(rendered)} Bytes, {n} Zeilen) → {GOLDEN_FILE}")
        return

    if not GOLDEN_FILE.exists():
        print(f"  ✗ Golden fehlt: {GOLDEN_FILE}")
        print(f"    Erzeuge es einmalig mit: "
              f"UPDATE_GOLDEN=1 python {pathlib.Path(__file__).name}")
        sys.exit(1)

    expected = GOLDEN_FILE.read_text(encoding="utf-8")
    if rendered == expected:
        n = rendered.count("\n") + 1
        print(f"  ✓ Outer-Page-Golden byte-identisch "
              f"({len(rendered)} Bytes, {n} Zeilen).")
        return

    print("  ✗ Outer-Page-Output WEICHT VOM GOLDEN AB:")
    hunk = _context_diff(expected, rendered)
    # Bei riesigem Diff nur die ersten ~60 Zeilen Hunk zeigen (reicht zum Finden).
    lines = hunk.splitlines()
    print("\n".join("    " + l for l in lines[:60]))
    if len(lines) > 60:
        print(f"    … ({len(lines) - 60} weitere Diff-Zeilen)")
    print("\n  Wenn die Änderung GEWOLLT ist: "
          "UPDATE_GOLDEN=1 python " + pathlib.Path(__file__).name)
    sys.exit(1)


if __name__ == "__main__":
    main()
