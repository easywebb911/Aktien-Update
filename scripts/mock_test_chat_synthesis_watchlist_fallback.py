"""Mock-Tests für Chat-Synthese Watchlist-Fallback (12.05.2026-Bug).

Diagnose aus heutiger Bestandsaufnahme: ``_build_chat_synthesis_ctx`` las
``current_price`` nur aus ``stocks`` (heutige Top-10). Position-Ticker
außerhalb der Top-10 (z.B. SABR/DMRC seit 07./11.05.) landeten mit
``current_price=null`` + ``in_top10=false`` im Chat-Kontext, obwohl das
Position-Panel im Frontend dieselben Tickers mit Live-Kursen anzeigte —
das Frontend liest aus ``app_data.json.watchlist_cards``, der Chat-Ctx
las das nie.

Dieser Test fixiert das erwartete Verhalten nach dem Fix (PR „chat-
synthesis-watchlist-fallback"):

  1. Position-Ticker in heutiger Top-10 → in_top10=true, in_watchlist_card=false,
     current_price aus stocks
  2. Position-Ticker außerhalb Top-10 mit Watchlist-Card → in_top10=false,
     in_watchlist_card=true, current_price aus watchlist_cards (NICHT null)
  3. Position-Ticker außerhalb Top-10 OHNE Watchlist-Card → in_top10=false,
     in_watchlist_card=false, current_price=null (echte Daten-Lücke)
  4. watchlist_cards=None (legacy/Backward-Compat) → kein Crash, kein
     in_watchlist_card=true (Default falsy)
  5. Top-10-Ticker wird NICHT vom Watchlist-Fallback überschrieben
     (Quellen-Priorität: stocks > watchlist_cards)
  6. setup_today / monster_today für Position-Ticker aus Watchlist-Card

Ausführung: ``python scripts/mock_test_chat_synthesis_watchlist_fallback.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import generate_report as gr  # noqa: E402


def _patch_positions(positions: dict):
    """Patcht _load_positions, damit der Test ohne positions.json läuft."""
    return patch.object(gr, "_load_positions", return_value=positions)


def _stub_top10_stock(ticker: str, **overrides) -> dict:
    base = {
        "ticker":         ticker,
        "company_name":   f"{ticker} Inc",
        "score":          72.0,
        "monster_score":  80.0,
        "ki_signal_score": 50,
        "price":          5.0,
        "change":         2.0,
        "short_float":    25.0,
        "short_ratio":    4.0,
        "rel_volume":     2.0,
        "rsi14":          60,
        "earnings_days":  None,
        "sector":         "Tech",
        "finra_data":     {"trend": "up"},
    }
    base.update(overrides)
    return base


# === 1 — Position in heutiger Top-10 =======================================

def test_position_in_top10_primary_source():
    """Position ist in der Top-10 → stocks-Eintrag ist die Quelle.
    in_watchlist_card bleibt False auch wenn ein Eintrag existiert."""
    positions = {"AAPL": {"entry_date": "2026-05-01", "entry_price": 4.0}}
    stocks = [_stub_top10_stock("AAPL", price=5.5, score=78.0, monster_score=85.0)]
    wl_cards = {"AAPL": {"price": 99.0, "score": 0.0, "monster_score": 0.0}}  # sollte ignoriert werden
    with _patch_positions(positions):
        ctx = gr._build_chat_synthesis_ctx(stocks, {}, watchlist_cards=wl_cards)
    pos = ctx["positions"][0]
    assert pos["ticker"] == "AAPL", pos
    assert pos["in_top10"] is True, pos
    assert pos["in_watchlist_card"] is False, pos
    # Wert aus stocks, nicht aus wl_cards
    assert pos["current_price"] == 5.5, pos
    assert pos["setup_today"]   == 78.0, pos
    assert pos["monster_today"] == 85.0, pos
    # PnL ist berechenbar
    assert pos["pnl_pct"] is not None, pos


# === 2 — Position außerhalb Top-10 MIT Watchlist-Card =====================

def test_position_outside_top10_uses_watchlist_card():
    """SABR/DMRC-Szenario: Position-Ticker nicht in Top-10, aber Watchlist-
    Card hat Live-Daten. current_price kommt aus watchlist_cards."""
    positions = {"SABR": {"entry_date": "2026-05-07", "entry_price": 3.50}}
    stocks = [_stub_top10_stock("OTHER")]   # SABR fehlt
    wl_cards = {
        "SABR": {"price": 4.20, "score": 65.5, "monster_score": 72.0},
    }
    with _patch_positions(positions):
        ctx = gr._build_chat_synthesis_ctx(stocks, {}, watchlist_cards=wl_cards)
    pos = ctx["positions"][0]
    assert pos["ticker"] == "SABR", pos
    assert pos["in_top10"] is False, pos
    assert pos["in_watchlist_card"] is True, pos
    # Live-Kurs aus dem Watchlist-Snapshot — KEIN null
    assert pos["current_price"] == 4.20, pos
    assert pos["setup_today"]   == 65.5, pos
    assert pos["monster_today"] == 72.0, pos
    # PnL gegen Live-Spot
    assert pos["pnl_pct"] is not None and pos["pnl_pct"] > 0, pos


# === 3 — Position weder in Top-10 noch in Watchlist-Card ===================

def test_position_no_source_returns_nulls():
    """Echte Daten-Lücke: Ticker existiert in positions.json aber weder
    in stocks noch in watchlist_cards. current_price=null, beide Flags False."""
    positions = {"GHOST": {"entry_date": "2026-04-01", "entry_price": 10.0}}
    stocks = [_stub_top10_stock("OTHER")]
    wl_cards = {"SABR": {"price": 4.0, "score": 50.0}}   # GHOST fehlt
    with _patch_positions(positions):
        ctx = gr._build_chat_synthesis_ctx(stocks, {}, watchlist_cards=wl_cards)
    pos = ctx["positions"][0]
    assert pos["ticker"] == "GHOST", pos
    assert pos["in_top10"] is False, pos
    assert pos["in_watchlist_card"] is False, pos
    assert pos["current_price"] is None, pos
    assert pos["setup_today"]   is None, pos
    assert pos["monster_today"] is None, pos
    assert pos["pnl_pct"] is None, pos


# === 4 — watchlist_cards=None (Backward-Compat) ============================

def test_backward_compat_no_watchlist_cards_arg():
    """Legacy-Aufruf ohne watchlist_cards-Parameter: kein Crash,
    in_watchlist_card immer False für Out-of-Top-10-Positionen."""
    positions = {"SABR": {"entry_date": "2026-05-07", "entry_price": 3.50}}
    stocks = [_stub_top10_stock("OTHER")]
    with _patch_positions(positions):
        # 2-Argument-Aufruf (Backward-Compat)
        ctx = gr._build_chat_synthesis_ctx(stocks, {})
    pos = ctx["positions"][0]
    assert pos["ticker"] == "SABR", pos
    assert pos["in_top10"] is False, pos
    assert pos["in_watchlist_card"] is False, pos
    assert pos["current_price"] is None, pos


# === 5 — Quellen-Priorität: stocks gewinnt gegen watchlist_cards ==========

def test_stocks_priority_over_watchlist_card():
    """Wenn ein Ticker BEIDE Quellen hat, gewinnen stocks (Top-10)."""
    positions = {"INDI": {"entry_date": "2026-05-01", "entry_price": 4.0}}
    stocks = [_stub_top10_stock("INDI", price=6.0, score=70.0)]
    wl_cards = {"INDI": {"price": 99.99, "score": 0.0, "monster_score": 0.0}}
    with _patch_positions(positions):
        ctx = gr._build_chat_synthesis_ctx(stocks, {}, watchlist_cards=wl_cards)
    pos = ctx["positions"][0]
    assert pos["in_top10"] is True, pos
    assert pos["in_watchlist_card"] is False, pos
    assert pos["current_price"] == 6.0, pos   # stocks-Wert, NICHT wl_cards
    assert pos["setup_today"]   == 70.0, pos


# === 6 — Score-Felder aus Watchlist-Card mit Edge-Cases ===================

def test_watchlist_card_score_edge_cases():
    """Watchlist-Card mit fehlendem monster_score → None, kein Crash."""
    positions = {"DMRC": {"entry_date": "2026-05-11", "entry_price": 8.0}}
    stocks = []
    wl_cards = {"DMRC": {"price": 9.5, "score": 55.3}}   # kein monster_score
    with _patch_positions(positions):
        ctx = gr._build_chat_synthesis_ctx(stocks, {}, watchlist_cards=wl_cards)
    pos = ctx["positions"][0]
    assert pos["ticker"] == "DMRC", pos
    assert pos["in_watchlist_card"] is True, pos
    assert pos["current_price"] == 9.5, pos
    assert pos["setup_today"]   == 55.3, pos
    assert pos["monster_today"] is None, pos


# === 7 — Sanity: leeres positions.json bleibt leer ========================

def test_no_positions_empty_list():
    stocks = [_stub_top10_stock("AAPL")]
    wl_cards = {"AAPL": {"price": 10}}
    with _patch_positions({}):
        ctx = gr._build_chat_synthesis_ctx(stocks, {}, watchlist_cards=wl_cards)
    assert ctx["positions"] == [], ctx


# === Runner ================================================================

def main():
    tests = [
        ("1. Position in Top-10 → stocks ist Quelle",      test_position_in_top10_primary_source),
        ("2. Position out-of-Top-10 → Watchlist-Fallback", test_position_outside_top10_uses_watchlist_card),
        ("3. Keine Quelle → current_price=null",           test_position_no_source_returns_nulls),
        ("4. Backward-Compat ohne watchlist_cards-Arg",    test_backward_compat_no_watchlist_cards_arg),
        ("5. Quellen-Priorität: stocks > Watchlist",       test_stocks_priority_over_watchlist_card),
        ("6. Watchlist-Card-Edge-Cases (kein monster)",    test_watchlist_card_score_edge_cases),
        ("7. Leeres positions.json → []",                  test_no_positions_empty_list),
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
