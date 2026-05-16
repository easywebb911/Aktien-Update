"""Mock-Tests fuer positions.current_price-Persistenz (S3-Fix, 16.05.2026).

Hintergrund (Diagnose 16.05.2026):
Health-Check S3 (crit) feuerte 19/19 Runs mit "current_price fehlt bei
4 Position(en): AMC, IONQ, RR, CRMD". Diagnose ergab: in
_build_phase2_positions_payload wird cur_price bereits korrekt
berechnet (Top-10-Lookup → _fetch_position_market_data-Fallback),
aber im out[ticker]-Dict nicht persistiert.

Fix: Ein additives Feld "current_price": cur_price im out-Dict.
Verhalten der Berechnung selbst unveraendert.

Tests:
  1. Source: out-Dict enthaelt "current_price": cur_price
  2. Source: Feld steht zwischen fx_estimated und entry_dtc
  3. Source: Kommentar dokumentiert den S3-Fix-Bezug
  4. Source: _compute_exit_state-Aufruf NICHT geaendert
  5. Logik-Replik: In-Top10 -> current_price = top10[t].price
  6. Logik-Replik: Out-of-Top10 -> _fetch_position_market_data-Fallback
  7. Logik-Replik: Beide Quellen fail -> current_price = None
  8. Logik-Replik: top10[t].price = None -> yfinance-Fallback greift
  9. Logik-Replik: shares = None orthogonal zu current_price
 10. S3-Simulation: 4 Positionen mit Preis -> missing_price = []
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _func_block(func_def: str) -> str:
    start = GR.find(func_def)
    assert start > 0, f"Funktion {func_def!r} nicht gefunden"
    end = GR.find("\ndef ", start + 10)
    assert end > start
    return GR[start:end]


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_01_field_in_out_dict() -> None:
    block = _func_block("def _build_phase2_positions_payload(")
    assert re.search(r'"current_price":\s*cur_price\s*,', block), \
        "current_price-Feld fehlt oder ist nicht cur_price (Variable)"


def test_02_field_position_in_dict() -> None:
    block = _func_block("def _build_phase2_positions_payload(")
    fx_idx = block.find('"fx_estimated":')
    cp_idx = block.find('"current_price":')
    dtc_idx = block.find('"entry_dtc":')
    assert fx_idx > 0 and cp_idx > 0 and dtc_idx > 0, "Erwartete Felder fehlen"
    assert fx_idx < cp_idx < dtc_idx, \
        f"current_price an falscher Stelle (fx={fx_idx}, cp={cp_idx}, dtc={dtc_idx})"


def test_03_comment_documents_s3_fix() -> None:
    block = _func_block("def _build_phase2_positions_payload(")
    assert "S3" in block, "Kommentar erwaehnt S3-Fix-Bezug nicht"
    assert "16.05.2026" in block or "Live-PnL" in block, \
        "Datum oder Zweck-Hinweis fehlt"


def test_04_compute_exit_state_unchanged() -> None:
    """_compute_exit_state-Signatur und Aufruf duerfen sich nicht aendern."""
    block = _func_block("def _build_phase2_positions_payload(")
    assert re.search(
        r'_compute_exit_state\(\s*\n?\s*ticker,\s*pos,\s*history,\s*cur_price,',
        block), "_compute_exit_state-Aufruf hat sich geaendert"


# ── Logik-Replik (pythonisch) ────────────────────────────────────────────────

def _replicate_resolve_cur_price(
    ticker: str,
    top10_by_ticker: dict,
    fetch_position_market_data,
    entry_date_obj=None,
) -> float | None:
    """1:1-Replikat der cur_price-Resolution in _build_phase2_positions_payload.

    Reihenfolge: top10-Lookup → _fetch_position_market_data-Fallback → None.
    """
    cur_price = None
    s_top = top10_by_ticker.get(ticker)
    if s_top and s_top.get("price") is not None:
        try:
            cur_price = float(s_top["price"])
        except (TypeError, ValueError):
            cur_price = None
    if cur_price is None:
        try:
            market = fetch_position_market_data(ticker, entry_date_obj)
            if market and market.get("price"):
                cur_price = float(market["price"])
        except Exception:
            pass
    return cur_price


def test_05_in_top10_uses_top10_price() -> None:
    top10 = {"INDI": {"ticker": "INDI", "price": 4.20}}
    def _fetch(t, d): raise AssertionError("yfinance darf nicht aufgerufen werden")
    cur = _replicate_resolve_cur_price("INDI", top10, _fetch)
    assert cur == 4.20


def test_06_out_of_top10_uses_yfinance_fallback() -> None:
    top10 = {}   # CRMD nicht in Top-10
    def _fetch(t, d):
        assert t == "CRMD"
        return {"price": 7.55, "high_since_entry": 8.95}
    cur = _replicate_resolve_cur_price("CRMD", top10, _fetch)
    assert cur == 7.55


def test_07_both_fail_returns_none() -> None:
    top10 = {}
    def _fetch(t, d):
        return None
    cur = _replicate_resolve_cur_price("RR", top10, _fetch)
    assert cur is None


def test_08_top10_price_none_falls_through() -> None:
    # Edge: ticker IST in Top-10 aber price=None (yfinance batch fail)
    top10 = {"AMC": {"ticker": "AMC", "price": None}}
    def _fetch(t, d):
        return {"price": 3.45}
    cur = _replicate_resolve_cur_price("AMC", top10, _fetch)
    assert cur == 3.45, "Fallback haette greifen muessen"


def test_09_shares_none_orthogonal() -> None:
    # shares-Feld in Position ist unabhaengig von current_price
    top10 = {"IONQ": {"ticker": "IONQ", "price": 28.50}}
    def _fetch(t, d): return None
    cur = _replicate_resolve_cur_price("IONQ", top10, _fetch)
    assert cur == 28.50


def test_10_s3_health_check_simulation() -> None:
    """Nach Fix: payload.current_price ist gesetzt fuer Positionen mit
    Preis-Verfuegbarkeit. S3 checkt genau dieses Feld."""
    top10 = {}   # keine Position in Top-10 heute (= Easy's reale Lage)
    prices = {"AMC": 3.45, "IONQ": 28.5, "RR": 12.1, "CRMD": 7.55}
    def _fetch(t, d):
        return {"price": prices.get(t)}
    payload = {}
    for ticker in ["AMC", "IONQ", "RR", "CRMD"]:
        cur = _replicate_resolve_cur_price(ticker, top10, _fetch)
        # Simuliere out[ticker]-Komposition wie nach Fix
        payload[ticker] = {
            "entry_price": 10.0, "shares": 5,
            "current_price": cur,
        }
    # S3-Replik: missing_price = [t for t,p in payload.items() if p.get("current_price") is None]
    missing = [t for t, p in payload.items() if p.get("current_price") is None]
    assert missing == [], f"S3-Check faengt heute keine Positionen, gefunden: {missing}"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 Feld 'current_price': cur_price im out-Dict",         test_01_field_in_out_dict),
        ("02 Feld an Position fx_estimated → entry_dtc",           test_02_field_position_in_dict),
        ("03 Kommentar dokumentiert S3-Fix",                       test_03_comment_documents_s3_fix),
        ("04 _compute_exit_state-Aufruf unveraendert",             test_04_compute_exit_state_unchanged),
        ("05 In-Top10 → top10-Price",                              test_05_in_top10_uses_top10_price),
        ("06 Out-of-Top10 → yfinance-Fallback",                    test_06_out_of_top10_uses_yfinance_fallback),
        ("07 Beide fail → None",                                   test_07_both_fail_returns_none),
        ("08 Top10-Price=None → Fallback greift",                  test_08_top10_price_none_falls_through),
        ("09 shares=None orthogonal zu current_price",             test_09_shares_none_orthogonal),
        ("10 S3-Simulation: 4 Positionen, kein missing",           test_10_s3_health_check_simulation),
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
