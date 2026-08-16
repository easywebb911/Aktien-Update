"""Mock-Tests für die drei am 16.08.2026 gehärteten NaN-Geschwister-Stellen.

Hintergrund: PR #534 hatte bei der systematischen .iloc[-Suche drei weitere
unguardete Fundstellen gemeldet, aber bewusst nicht gefixt (siehe PR-Body).
Easy hat entschieden: alle drei werden gehärtet, ein PR.

  1. get_yfinance_data/_hist_stats -> price-Merge (generate_report.py):
     ``c["price"] = yfd.get("price") or c.get("price")`` ließ eine NaN
     durch (NaN ist truthy). Fix: positive Vergleichsform (_finite + >0)
     statt "or" — identisches Fallback-Verhalten für alle anderen Fälle
     (None/0/negativ), nur NaN wird jetzt zusätzlich korrekt abgefangen.
     Zusätzlich: _normalize_rvol hielt seine eigene Doku-Zusage nicht ein
     (Guard "raw <= 0" fängt NaN nicht) — auf _finite umgestellt (siehe
     mock_test_rvol_normalization.py Tests 20-24, hier nicht dupliziert).

  2. get_watchlist_candidates (generate_report.py): "UNBEKANNT SCHLIESST
     AUS" — ist cur_vol/avg_vol oder price nicht endlich, wird der
     Kandidat NICHT aufgenommen (continue, wie ein gerissener Filter),
     geloggt mit Ticker+Grund. Zusätzlich: prev_close NaN erzeugt keinen
     stillen 0.0-"change" mehr, sondern None.

  3. fetch_uoa_signal (ki_agent.py): Guard "if spot <= 0" auf _finite
     erweitert (beide Vorkommen). Die Kette landete vorher zufällig bei
     einem harmlosen None (Glück durch pandas-NaN-Vergleichssemantik) —
     nach dem Fix ist das Absicht: eine NaN aus fast_info löst jetzt
     korrekt den history-Fallback aus (vorher übersprungen), eine NaN aus
     der history-Zeile führt zum sauberen, geloggten Abbruch.

Tests:
  A. price-Merge (Stelle 1): NaN -> Fallback, reguläre Fälle unverändert.
  B. get_watchlist_candidates (Stelle 2): NaN -> Ausschluss (nicht im
     Pool), Log-Nachweis, kein stiller 0.0-change, valide Daten
     unverändert.
  C. fetch_uoa_signal (Stelle 3): NaN aus fast_info löst Fallback aus,
     NaN aus history -> sauberer Abbruch mit Log, valide Daten
     unverändert.
  D. Gegenprobe: kein stiller Ersatzwert (0.0/$0.00/erfundene Zahl)
     irgendwo eingeführt.

Ausführung: ``python scripts/mock_test_watchlist_uoa_price_nan_hardening.py``.
"""
from __future__ import annotations

import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

src_gr = (ROOT / "generate_report.py").read_text(encoding="utf-8")
src_ki = (ROOT / "ki_agent.py").read_text(encoding="utf-8")


def _finite(v) -> bool:
    """Lokale Replik (identischer Vertrag zu generate_report._finite /
    ki_agent._finite — beide bereits dupliziert im Repo, kein Import nötig)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return math.isfinite(v)


# === A — price-Merge (Stelle 1) =============================================

def _price_merge_replica(yfd_price, c_price):
    """Replik der gehärteten Merge-Zeile:
    _yfd_price = _yfd_price if (_finite(_yfd_price) and _yfd_price > 0) else None
    "price": _yfd_price or c.get("price")
    """
    _yfd_price = yfd_price if (_finite(yfd_price) and yfd_price > 0) else None
    return _yfd_price or c_price


def test_price_merge_nan_falls_back_to_screener_price():
    result = _price_merge_replica(float("nan"), 4.20)
    assert result == 4.20, f"Erwarte Fallback auf 4.20, bekam {result!r}"
    assert not (isinstance(result, float) and math.isnan(result))


def test_price_merge_none_zero_negative_unchanged_regression():
    """Regression: None/0.0/negativ verhalten sich exakt wie vorher (alte
    'or'-Semantik) — nur NaN ist neu abgefangen."""
    assert _price_merge_replica(None, 4.20) == 4.20
    assert _price_merge_replica(0.0, 4.20) == 4.20
    assert _price_merge_replica(-1.0, 4.20) == 4.20


def test_price_merge_valid_price_used_directly():
    assert _price_merge_replica(5.55, 4.20) == 5.55


def test_price_merge_both_bad_yields_none_not_fake_zero():
    """Wenn auch der Screener-Preis fehlt: None, KEIN erfundenes $0.00."""
    result = _price_merge_replica(float("nan"), None)
    assert result is None


def test_price_merge_source_uses_finite_not_or():
    seg = src_gr[src_gr.find('_yfd_price = yfd.get("price")'):
                 src_gr.find('c.update({')]
    assert seg, "price-Merge-Segment nicht gefunden"
    assert "_finite(_yfd_price) and _yfd_price > 0" in seg
    assert '"price":               yfd.get("price") or c.get("price")' not in src_gr, (
        "alte 'or'-Form ist noch im Source")
    assert '"price":               _yfd_price or c.get("price"),' in src_gr


# === B — get_watchlist_candidates (Stelle 2) ================================

def _watchlist_candidate_replica(avg_vol, cur_vol, price, prev_close, *,
                                  market="US", min_price=1.0,
                                  min_rel_volume=2.0, min_rel_volume_intl=1.5):
    """Replik der gehärteten Kandidaten-Filter-Kette (Werte-Ebene, keine
    pandas-Simulation — die Guard-LOGIK wird getestet, nicht .iloc/.mean)."""
    log = []
    if not (_finite(avg_vol) and _finite(cur_vol)):
        log.append(f"skip_volume avg={avg_vol!r} cur={cur_vol!r}")
        return None, log
    if avg_vol < 1000:
        return None, log
    rel_vol = cur_vol / avg_vol if avg_vol > 0 else 0.0
    vol_threshold = min_rel_volume_intl if market != "US" else min_rel_volume
    if rel_vol < vol_threshold:
        return None, log
    if not _finite(price):
        log.append(f"skip_price price={price!r}")
        return None, log
    if price < min_price:
        return None, log
    chg = ((price - prev_close) / prev_close * 100
           if _finite(prev_close) and prev_close > 0 else None)
    return {
        "price": price,
        "change": round(chg, 2) if chg is not None else None,
        "rel_volume": round(rel_vol, 2),
    }, log


def test_watchlist_nan_cur_vol_excludes_candidate():
    """KERNFALL: NaN cur_vol -> Kandidat wird NICHT aufgenommen (None), UND
    das Log dokumentiert den Ausschluss (kein stiller Skip)."""
    cand, log = _watchlist_candidate_replica(
        avg_vol=50_000, cur_vol=float("nan"), price=10.0, prev_close=9.5)
    assert cand is None, "NaN-cur_vol darf den Kandidaten NICHT ins Ergebnis lassen"
    assert len(log) == 1 and "skip_volume" in log[0]


def test_watchlist_nan_avg_vol_excludes_candidate():
    cand, log = _watchlist_candidate_replica(
        avg_vol=float("nan"), cur_vol=100_000, price=10.0, prev_close=9.5)
    assert cand is None
    assert len(log) == 1 and "skip_volume" in log[0]


def test_watchlist_nan_price_excludes_candidate():
    cand, log = _watchlist_candidate_replica(
        avg_vol=50_000, cur_vol=200_000, price=float("nan"), prev_close=9.5)
    assert cand is None, "NaN-price darf den Kandidaten NICHT ins Ergebnis lassen"
    assert len(log) == 1 and "skip_price" in log[0]


def test_watchlist_nan_prev_close_no_silent_zero_change():
    """Kandidat wird trotzdem aufgenommen (price/volume sind valide), aber
    'change' ist None statt einer vorgetäuschten 0.0 %-Bewegung."""
    cand, log = _watchlist_candidate_replica(
        avg_vol=50_000, cur_vol=200_000, price=10.0, prev_close=float("nan"))
    assert cand is not None, "gültige price/volume -> Kandidat bleibt drin"
    assert cand["change"] is None, (
        f"change muss None sein bei unbekanntem prev_close, nicht {cand['change']!r}")


def test_watchlist_valid_data_unchanged_regression():
    """Regression: vollständige, endliche Daten liefern exakt dasselbe
    Ergebnis wie vor der Härtung."""
    cand, log = _watchlist_candidate_replica(
        avg_vol=50_000, cur_vol=200_000, price=10.0, prev_close=9.5)
    assert cand is not None
    assert log == []
    assert cand["price"] == 10.0
    assert cand["rel_volume"] == round(200_000 / 50_000, 2)
    expected_chg = round((10.0 - 9.5) / 9.5 * 100, 2)
    assert cand["change"] == expected_chg


def test_watchlist_below_threshold_still_excluded_unrelated_to_nan():
    """Gegenprobe: ein regulärer (nicht NaN-bedingter) Filter-Miss bleibt
    unverändert ein Ausschluss ohne NaN-Log-Eintrag."""
    cand, log = _watchlist_candidate_replica(
        avg_vol=50_000, cur_vol=51_000, price=10.0, prev_close=9.5)  # rel_vol ~1.02 < 2.0
    assert cand is None
    assert log == [], "regulärer Schwellen-Miss darf keinen NaN-Log-Eintrag erzeugen"


def test_watchlist_source_uses_finite_guards_and_logs():
    seg = src_gr[src_gr.find('avg_vol = float(df["Volume"].iloc[:-1].mean())'):
                 src_gr.find("results.append({")]
    assert seg, "get_watchlist_candidates-Filterblock nicht gefunden"
    assert "not (_finite(avg_vol) and _finite(cur_vol))" in seg
    assert "not _finite(price)" in seg
    assert "log.info(" in seg and seg.count("log.info(") >= 2, (
        "mindestens 2 Log-Aufrufe (Volumen + Preis) erwartet")
    assert "_finite(prev_close) and prev_close > 0 else None" in seg


# === C — fetch_uoa_signal (Stelle 3) ========================================

def _uoa_spot_resolution_replica(fast_info_last_price, history_available, history_close):
    """Replik der gehärteten Spot-Resolution-Kette (beide Guards)."""
    log = []
    spot = float(fast_info_last_price or 0.0)
    if not _finite(spot) or spot <= 0:
        if history_available:
            spot = float(history_close)
    if not _finite(spot) or spot <= 0:
        log.append(f"skip spot={spot!r}")
        return None, log
    return spot, log


def test_uoa_nan_fast_info_triggers_history_fallback():
    """KERNFALL (vorher kaputt): eine NaN aus fast_info sprang den
    history-Fallback komplett über (nan <= 0 war False -> Fallback-Block
    nie betreten). Nach der Härtung wird der Fallback korrekt versucht."""
    spot, log = _uoa_spot_resolution_replica(
        fast_info_last_price=float("nan"), history_available=True, history_close=42.0)
    assert spot == 42.0, f"Fallback hätte greifen müssen, bekam {spot!r}"
    assert log == []


def test_uoa_nan_history_close_clean_abort_with_log():
    spot, log = _uoa_spot_resolution_replica(
        fast_info_last_price=float("nan"), history_available=True, history_close=float("nan"))
    assert spot is None
    assert len(log) == 1 and "skip" in log[0]


def test_uoa_no_history_available_clean_abort():
    spot, log = _uoa_spot_resolution_replica(
        fast_info_last_price=float("nan"), history_available=False, history_close=None)
    assert spot is None
    assert len(log) == 1


def test_uoa_valid_fast_info_used_directly_regression():
    spot, log = _uoa_spot_resolution_replica(
        fast_info_last_price=88.5, history_available=True, history_close=99.9)
    assert spot == 88.5, "valider fast_info-Preis darf den Fallback nicht auslösen"
    assert log == []


def test_uoa_zero_fast_info_still_triggers_fallback_regression():
    """Regression: 0.0 (legitimer 'keine Daten'-Sentinel) löste den
    Fallback schon VOR der Härtung aus — das bleibt unverändert."""
    spot, log = _uoa_spot_resolution_replica(
        fast_info_last_price=0.0, history_available=True, history_close=55.0)
    assert spot == 55.0
    assert log == []


def test_uoa_source_uses_finite_on_both_guards():
    seg = src_ki[src_ki.find("# Spot-Preis als ATM-Referenz"):
                 src_ki.find("# Nächste Expiration")]
    assert seg, "Spot-Resolution-Segment nicht gefunden"
    assert seg.count("not _finite(spot) or spot <= 0") == 2, (
        "beide Guards (vor UND nach dem history-Fallback) müssen gehärtet sein")
    assert "log.debug(" in seg


# === D — Gegenprobe: kein stiller Ersatzwert (coiled_spring-Muster) ========

def test_no_silent_fake_value_anywhere():
    # price-Merge: fehlt beides -> None, kein $0.00
    assert _price_merge_replica(float("nan"), None) is None
    # watchlist: NaN-Volumen -> ganz raus, keine 0.0-rel_volume-Karte
    cand, _ = _watchlist_candidate_replica(
        avg_vol=float("nan"), cur_vol=200_000, price=10.0, prev_close=9.5)
    assert cand is None
    # watchlist: NaN-prev_close -> change None, nicht 0.0
    cand2, _ = _watchlist_candidate_replica(
        avg_vol=50_000, cur_vol=200_000, price=10.0, prev_close=float("nan"))
    assert cand2["change"] is None and cand2["change"] != 0.0
    # UOA: beide Quellen kaputt -> None, kein erfundener ATM-Ratio-Ansatzpunkt
    spot, _ = _uoa_spot_resolution_replica(float("nan"), True, float("nan"))
    assert spot is None


# === Runner ==================================================================

def main() -> None:
    tests = [
        ("A1 price-Merge: NaN -> Fallback auf Screener-Preis",   test_price_merge_nan_falls_back_to_screener_price),
        ("A2 price-Merge: None/0/negativ unverändert (Regression)", test_price_merge_none_zero_negative_unchanged_regression),
        ("A3 price-Merge: valider Preis direkt verwendet",       test_price_merge_valid_price_used_directly),
        ("A4 price-Merge: beides kaputt -> None, kein $0.00",    test_price_merge_both_bad_yields_none_not_fake_zero),
        ("A5 Quelltext: price-Merge nutzt _finite() statt 'or'", test_price_merge_source_uses_finite_not_or),
        ("B1 watchlist: NaN cur_vol -> Kandidat ausgeschlossen", test_watchlist_nan_cur_vol_excludes_candidate),
        ("B2 watchlist: NaN avg_vol -> Kandidat ausgeschlossen", test_watchlist_nan_avg_vol_excludes_candidate),
        ("B3 watchlist: NaN price -> Kandidat ausgeschlossen",   test_watchlist_nan_price_excludes_candidate),
        ("B4 watchlist: NaN prev_close -> change=None, kein 0.0", test_watchlist_nan_prev_close_no_silent_zero_change),
        ("B5 watchlist: valide Daten unverändert (Regression)",  test_watchlist_valid_data_unchanged_regression),
        ("B6 watchlist: regulärer Miss ohne NaN-Log",            test_watchlist_below_threshold_still_excluded_unrelated_to_nan),
        ("B7 Quelltext: watchlist nutzt _finite() + loggt",      test_watchlist_source_uses_finite_guards_and_logs),
        ("C1 UOA: NaN fast_info löst history-Fallback aus",      test_uoa_nan_fast_info_triggers_history_fallback),
        ("C2 UOA: NaN history -> sauberer Abbruch + Log",        test_uoa_nan_history_close_clean_abort_with_log),
        ("C3 UOA: keine History verfügbar -> sauberer Abbruch",  test_uoa_no_history_available_clean_abort),
        ("C4 UOA: valider fast_info direkt (Regression)",        test_uoa_valid_fast_info_used_directly_regression),
        ("C5 UOA: 0.0-Sentinel löst weiter Fallback aus (Regression)", test_uoa_zero_fast_info_still_triggers_fallback_regression),
        ("C6 Quelltext: beide UOA-Guards nutzen _finite()",      test_uoa_source_uses_finite_on_both_guards),
        ("D Gegenprobe: kein stiller Ersatzwert irgendwo",       test_no_silent_fake_value_anywhere),
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
