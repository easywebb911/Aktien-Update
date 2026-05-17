"""Mock-Tests fuer Watchlist-Erweiterung in Chat-Kontext (17.05.2026).

Hintergrund: Chat im Hamburger-Menue bekommt STOCKS_CTX (= Output von
_build_chat_synthesis_ctx) als JSON-Block in System-Prompt. Bisher nur
today_top10 + positions. Easy fragt nach Watchlist-Tickern (AI, AMC,
IONQ, RR, CRMD), bekommt generische Antwort weil Daten fehlen.

Fix: neuer `watchlist`-Key in STOCKS_CTX mit 17 Feldern pro Ticker
(analog today_top10). Quelle: watchlist_cards-Dict. Top-10-Ticker
ausgeschlossen (sind via today_top10 abgedeckt).

Tests:
  1. STOCKS_CTX hat watchlist-Key
  2. watchlist ist Liste
  3. Top-10-Ticker werden ausgeschlossen (nicht doppelt)
  4. Pro Eintrag: 17 Pflicht-Felder vorhanden
  5. Plausibilitaets-Check: price > 0, sf >= 0
  6. Bei leerer watchlist_cards -> watchlist=[]
  7. Field-Format: setup_today gerundet, price gerundet
  8. system-prompt enthaelt WATCHLIST-DATENQUELLE-Sektion
  9. Token-Budget-Smoke-Test: JSON < 12 KB bei typischem Datenstand
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHAT_SCRIPT = (ROOT / "templates" / "chat_script.jinja").read_text(encoding="utf-8")
GR_SOURCE = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _make_stock(ticker: str, score: float = 70.0, **extra) -> dict:
    """Minimal-Stock fuer Tests."""
    base = {
        "ticker": ticker,
        "company_name": f"{ticker} Inc.",
        "score": score,
        "monster_score": score,
        "ki_signal_score": 50,
        "price": 10.0,
        "change": 1.0,
        "short_float": 20.0,
        "short_ratio": 5.0,
        "rel_volume": 2.0,
        "rsi14": 55,
        "options": {"atm_iv": 0.5},
        "earnings_days": 30,
        "sector": "Tech",
        "finra_data": {"trend": "up"},
    }
    base.update(extra)
    return base


def _make_wl_card(ticker: str, score: float = 60.0) -> dict:
    return {
        "company_name":    f"{ticker} Corp.",
        "score":           score,
        "monster_score":   score,
        "ki_signal_score": 40,
        "price":           7.5,
        "change":          -0.5,
        "change_2d":       1.2,
        "change_5d":       -3.0,
        "short_float":     15.0,
        "short_ratio":     8.0,
        "rel_volume":      1.8,
        "rsi14":           48.0,
        "atm_iv":          None,
        "earnings_days":   60,
        "sector":          "Healthcare",
        "si_trend":        "sideways",
    }


def _build_ctx():
    """Lade _build_chat_synthesis_ctx isoliert (umgeht yfinance-Import)."""
    import re
    # Module-Variable benoetigt
    ns = {
        "_FX_USD_EUR": 0.92,
        "_safe_float": float,
        "datetime": __import__("datetime").datetime,
        "log": __import__("logging").getLogger("test"),
        # Anomaly-Schwellen aus config.py (Stubs fuer Test)
        "ANOMALY_RVOL_TODAY":  5.0,
        "ANOMALY_SCORE_JUMP":  15,
    }
    # Backtest-History-Loader Stub
    ns["_load_backtest_history"] = lambda: []

    # Extrahiere die Funktion via Regex aus dem Source
    m = re.search(r"^def _build_chat_synthesis_ctx\(.*?(?=^def )",
                  GR_SOURCE, re.MULTILINE | re.DOTALL)
    assert m, "Funktion _build_chat_synthesis_ctx nicht gefunden"
    exec(m.group(0), ns)
    return ns["_build_chat_synthesis_ctx"]


_build_chat_synthesis_ctx = _build_ctx()


def test_01_ctx_has_watchlist_key() -> None:
    stocks = [_make_stock("AAA")]
    wl = {"BBB": _make_wl_card("BBB")}
    ctx = _build_chat_synthesis_ctx(stocks, {}, wl)
    assert "watchlist" in ctx, "STOCKS_CTX hat keinen watchlist-Key"


def test_02_watchlist_is_list() -> None:
    ctx = _build_chat_synthesis_ctx([_make_stock("AAA")], {},
                                     {"BBB": _make_wl_card("BBB")})
    assert isinstance(ctx["watchlist"], list)


def test_03_top10_tickers_excluded() -> None:
    # Wenn AAA in beiden ist (Top-10 UND watchlist_cards), darf AAA
    # NICHT doppelt erscheinen — Top-10 hat schon vollen Datensatz.
    stocks = [_make_stock("AAA"), _make_stock("BBB")]
    wl = {"AAA": _make_wl_card("AAA"), "CCC": _make_wl_card("CCC")}
    ctx = _build_chat_synthesis_ctx(stocks, {}, wl)
    wl_tickers = [e["ticker"] for e in ctx["watchlist"]]
    assert "AAA" not in wl_tickers, \
        "Top-10-Ticker AAA noch in watchlist (Duplikation)"
    assert "BBB" not in wl_tickers, \
        "Top-10-Ticker BBB noch in watchlist (Duplikation)"
    assert "CCC" in wl_tickers, \
        "Watchlist-Ticker CCC fehlt"


def test_04_required_fields_present() -> None:
    ctx = _build_chat_synthesis_ctx([], {}, {"XYZ": _make_wl_card("XYZ")})
    entry = ctx["watchlist"][0]
    required = [
        "ticker", "company", "setup_today", "monster_today", "ki_today",
        "price", "change", "change_2d", "change_5d", "short_float",
        "short_ratio", "rel_volume", "rsi14", "atm_iv", "earnings_days",
        "sector", "si_trend",
    ]
    for f in required:
        assert f in entry, f"Pflichtfeld '{f}' fehlt in Watchlist-Eintrag"
    assert len(required) == 17, "Field-Liste hat nicht 17 Eintraege"


def test_05_plausible_field_values() -> None:
    wl = {"AAA": _make_wl_card("AAA", score=72.5)}
    ctx = _build_chat_synthesis_ctx([], {}, wl)
    e = ctx["watchlist"][0]
    assert e["ticker"] == "AAA"
    assert e["setup_today"] == 72.5
    assert e["price"] > 0
    assert e["short_float"] >= 0
    assert e["sector"] == "Healthcare"


def test_06_empty_watchlist_cards() -> None:
    ctx = _build_chat_synthesis_ctx([_make_stock("AAA")], {}, None)
    assert ctx["watchlist"] == []
    ctx2 = _build_chat_synthesis_ctx([_make_stock("AAA")], {}, {})
    assert ctx2["watchlist"] == []


def test_07_field_format_rounded() -> None:
    wl_card = _make_wl_card("AAA")
    wl_card["score"] = 67.234567
    wl_card["price"] = 12.6789
    ctx = _build_chat_synthesis_ctx([], {}, {"AAA": wl_card})
    e = ctx["watchlist"][0]
    assert e["setup_today"] == 67.2, f"setup_today nicht auf 1 Dezimal: {e['setup_today']}"
    assert e["price"] == 12.68, f"price nicht auf 2 Dezimalen: {e['price']}"


def test_08_system_prompt_has_watchlist_section() -> None:
    assert "WATCHLIST-DATENQUELLE" in CHAT_SCRIPT, \
        "System-Prompt hat keine WATCHLIST-DATENQUELLE-Sektion"
    # Hinweis dass Watchlist NICHT gerankt ist
    assert "NICHT gerankt" in CHAT_SCRIPT, \
        "Hinweis 'Watchlist NICHT gerankt' fehlt"
    # Klare Anweisung zur Datenquellen-Wahl (case-insensitive Match auf
    # die Phrase, akzeptiert Deklinations-Varianten)
    text_lower = CHAT_SCRIPT.lower()
    assert "watchlist" in text_lower and \
           ("generische antworten" in text_lower
            or "generischen antworten" in text_lower), \
        "Anweisung 'keine generischen Antworten' fehlt"


def test_09_token_budget_smoke() -> None:
    # Aktueller typischer Datenstand: 10 Top-10 + 5 Watchlist
    stocks = [_make_stock(f"T{i:02d}", score=70 - i) for i in range(10)]
    wl = {f"W{i}": _make_wl_card(f"W{i}") for i in range(5)}
    ctx = _build_chat_synthesis_ctx(stocks, {}, wl)
    size_kb = len(json.dumps(ctx)) / 1024
    assert size_kb < 12, f"STOCKS_CTX zu gross: {size_kb:.1f} KB (Erwartung < 12 KB)"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 STOCKS_CTX hat watchlist-Key",        test_01_ctx_has_watchlist_key),
        ("02 watchlist ist Liste",                  test_02_watchlist_is_list),
        ("03 Top-10-Ticker ausgeschlossen",        test_03_top10_tickers_excluded),
        ("04 17 Pflichtfelder vorhanden",          test_04_required_fields_present),
        ("05 Plausible Field-Werte",                test_05_plausible_field_values),
        ("06 Leere watchlist_cards -> []",         test_06_empty_watchlist_cards),
        ("07 Field-Format gerundet",                test_07_field_format_rounded),
        ("08 System-Prompt WATCHLIST-Sektion",     test_08_system_prompt_has_watchlist_section),
        ("09 Token-Budget < 12 KB",                 test_09_token_budget_smoke),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
        except AssertionError as exc:
            print(f"  FAIL {name}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
            failed += 1
    print()
    print(f"Total: {len(tests)} | Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
