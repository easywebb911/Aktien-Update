"""Mock-Tests fuer positions.current_price-Persistenz (S3-Fix, 16.05.2026)
+ Preserve-on-None/price_asof-Resilienz (26.07.2026, Tests 11-18).

Resilienz-Hintergrund (Diagnose 26.07.2026): ein transienter yfinance-
Singleton-Fehler klobberte den guten Freitag-Kurs mit None → S3-crit 14
ki_agent-Ticks lang. Fix: bei cur_price is None den letzten guten Wert aus
prev_pos preserven (analog entry_fx) + price_asof-Stempel macht Stale sichtbar.
NUR das Anzeige-/S3-Feld; der Trigger-Pfad (_compute_exit_state) bleibt frisch.

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
    # Seit der Preserve-on-None-Resilienz (26.07.2026) schreibt das out-Dict
    # `resolved_price` (frisch ODER preserved), nicht mehr direkt `cur_price`.
    assert re.search(r'"current_price":\s*resolved_price\s*,', block), \
        "current_price-Feld fehlt oder ist nicht resolved_price (Resilienz-Variable)"


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


# ── Preserve-on-None + price_asof-Resilienz (26.07.2026) ─────────────────────

def test_11_price_asof_field_present() -> None:
    block = _func_block("def _build_phase2_positions_payload(")
    assert re.search(r'"price_asof":\s*price_asof\s*,', block), \
        "price_asof-Feld fehlt im out-Dict"


def test_12_preserve_block_present() -> None:
    """Der Resilienz-Block muss bei cur_price is None den prev-Wert preserven
    und den alten price_asof behalten."""
    block = _func_block("def _build_phase2_positions_payload(")
    assert 'prev_pos.get("current_price")' in block, \
        "Preserve liest prev_pos.current_price nicht"
    assert 'prev_pos.get("price_asof")' in block, \
        "Preserve behält den alten price_asof nicht"
    assert re.search(r'price_asof\s*=\s*now_utc\.strftime', block), \
        "frischer Fetch stempelt price_asof nicht mit now_utc"


def _replicate_resolve_with_preserve(cur_price, prev_pos, now_iso):
    """1:1-Replikat des Resilienz-Blocks → (resolved_price, price_asof)."""
    if cur_price is not None:
        return cur_price, now_iso
    prev_price = prev_pos.get("current_price")
    if isinstance(prev_price, (int, float)) and not isinstance(prev_price, bool):
        return float(prev_price), prev_pos.get("price_asof")
    return None, None


_NOW = "2026-07-27T06:20:00Z"
_OLD = "2026-07-24T22:30:00Z"


def test_13_fresh_fetch_stamps_now() -> None:
    rp, asof = _replicate_resolve_with_preserve(4.20, {}, _NOW)
    assert rp == 4.20 and asof == _NOW, (rp, asof)


def test_14_saturday_clobber_now_preserves() -> None:
    """DER 25.07.-KLOBBER-FALL: guter Freitag-Wert + Fetch-None →
    frueher wurde None geschrieben, JETZT bleibt der Wert erhalten, asof alt."""
    prev = {"current_price": 3.45, "price_asof": _OLD}
    rp, asof = _replicate_resolve_with_preserve(None, prev, _NOW)
    assert rp == 3.45, f"Wert nicht preserved (Klobber!): {rp}"
    assert asof == _OLD, f"alter asof nicht behalten (Stale unsichtbar): {asof}"
    # Nachweis der Verhaltens-Aenderung: das alte Verhalten (unbedingtes cur_price)
    # haette None geschrieben.
    old_behavior = None
    assert rp != old_behavior, "Verhalten identisch zum alten Klobber — Fix wirkt nicht"


def test_15_first_time_no_price_stays_none() -> None:
    """Erstaufnahme ohne Preis: nie einen Preis erfinden → None/None."""
    rp, asof = _replicate_resolve_with_preserve(None, {}, _NOW)
    assert rp is None and asof is None, (rp, asof)


def test_16_alt_state_without_price_asof_null_tolerant() -> None:
    """Alt-State: prev hat current_price aber KEIN price_asof-Feld →
    preserve den Preis, asof = None (null-tolerant, kein KeyError)."""
    prev = {"current_price": 7.55}   # kein price_asof
    rp, asof = _replicate_resolve_with_preserve(None, prev, _NOW)
    assert rp == 7.55 and asof is None, (rp, asof)


def test_17_prev_price_none_not_preserved() -> None:
    """prev hatte selbst keinen Preis (None) → nichts zu preserven → None/None."""
    prev = {"current_price": None, "price_asof": None}
    rp, asof = _replicate_resolve_with_preserve(None, prev, _NOW)
    assert rp is None and asof is None, (rp, asof)


def test_18_s3_clears_after_preserve() -> None:
    """S3-Replik: nach Preserve ist current_price != None → S3 fängt die
    Position NICHT mehr (der 14-Tick-crit wäre so nie entstanden)."""
    prev = {"AMC": {"current_price": 3.45, "price_asof": _OLD}}
    payload = {}
    for t in ["AMC"]:
        rp, asof = _replicate_resolve_with_preserve(None, prev[t], _NOW)
        payload[t] = {"current_price": rp, "price_asof": asof}
    missing = [t for t, p in payload.items() if p.get("current_price") is None]
    assert missing == [], f"S3 faengt trotz Preserve: {missing}"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 Feld 'current_price': resolved_price im out-Dict",    test_01_field_in_out_dict),
        ("02 Feld an Position fx_estimated → entry_dtc",           test_02_field_position_in_dict),
        ("03 Kommentar dokumentiert S3-Fix",                       test_03_comment_documents_s3_fix),
        ("04 _compute_exit_state-Aufruf unveraendert",             test_04_compute_exit_state_unchanged),
        ("05 In-Top10 → top10-Price",                              test_05_in_top10_uses_top10_price),
        ("06 Out-of-Top10 → yfinance-Fallback",                    test_06_out_of_top10_uses_yfinance_fallback),
        ("07 Beide fail → None",                                   test_07_both_fail_returns_none),
        ("08 Top10-Price=None → Fallback greift",                  test_08_top10_price_none_falls_through),
        ("09 shares=None orthogonal zu current_price",             test_09_shares_none_orthogonal),
        ("10 S3-Simulation: 4 Positionen, kein missing",           test_10_s3_health_check_simulation),
        ("11 price_asof-Feld im out-Dict",                         test_11_price_asof_field_present),
        ("12 Preserve-Block liest prev + stempelt now",            test_12_preserve_block_present),
        ("13 frischer Fetch stempelt now",                         test_13_fresh_fetch_stamps_now),
        ("14 Sa-Klobber-Fall: preserved + asof alt",               test_14_saturday_clobber_now_preserves),
        ("15 Erstaufnahme ohne Preis → None/None",                 test_15_first_time_no_price_stays_none),
        ("16 Alt-State ohne price_asof → null-tolerant",           test_16_alt_state_without_price_asof_null_tolerant),
        ("17 prev-Preis None → nicht preserved",                   test_17_prev_price_none_not_preserved),
        ("18 S3 clears nach Preserve",                             test_18_s3_clears_after_preserve),
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
