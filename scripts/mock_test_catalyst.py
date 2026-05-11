"""Mock-Tests für Phase 2 Trigger 5 (catalyst).

Testet die Trigger-Funktion + Helper aus generate_report.py mit
gemockten Fetchern und gemockten requests/yfinance — keine echten
Netzwerk-Calls.

Sechs Szenarien:
  1. Finnhub-Hit (Earnings in 1 Tag) → score 50, warn=True
  2. Finnhub-Miss + yfinance-Hit (Earnings in 2 Tagen, Rand) → score 50, warn=True
  3. Beide Quellen leer → available=False
  4. Ticker ohne Earnings (Fetcher returnt None) → available=False
  5. Earnings heute (days_until=0) → score 100, crit=True
  6. Earnings in 3 Tagen (außerhalb Window) → score 0, kein Trigger

Ausführung: ``python scripts/mock_test_catalyst.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import generate_report as gr  # noqa: E402
from config import CATALYST_DAYS_WINDOW  # noqa: E402


def _now_utc() -> datetime:
    """Anker-Zeit: Montag 11.05.2026 14:00 UTC = Eastern 10:00 (Markt offen)."""
    return datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc)


def _today_east() -> date:
    return _now_utc().astimezone(gr.EASTERN).date()


def _stub_fetcher(date_val: date | None):
    """Returns a fetcher(ticker, today) -> date_val."""
    def fn(ticker: str, today: date) -> date | None:
        return date_val
    return fn


def test_finnhub_hit_in_window():
    """Case 1: Earnings in 1 Tag → warn (score 50)."""
    today = _today_east()
    earn = today + timedelta(days=1)  # Dienstag = Trading-Tag
    result = gr._exit_p2_trigger_catalyst(
        "TEST", _now_utc(), fetcher=_stub_fetcher(earn))
    # available wird nur bei False gesetzt (Pattern andere Trigger).
    assert result.get("available", True) is True, result
    assert result["score"] == 50, result
    assert result["warn"] is True, result
    assert result["crit"] is False, result
    assert result["details"]["trading_days_until"] == 1, result


def test_finnhub_miss_yfinance_hit_rand():
    """Case 2: Earnings in 2 Tagen (Window-Rand) → warn (score 50)."""
    today = _today_east()
    # +2 Trading-Days = Mittwoch von Montag aus
    earn = today + timedelta(days=2)
    result = gr._exit_p2_trigger_catalyst(
        "TEST", _now_utc(), fetcher=_stub_fetcher(earn))
    assert result["score"] == 50, result
    assert result["warn"] is True, result
    assert result["crit"] is False, result
    assert result["details"]["trading_days_until"] == CATALYST_DAYS_WINDOW, result


def test_both_sources_empty():
    """Case 3: Beide Quellen leer (Fetcher returnt None) → available=False."""
    result = gr._exit_p2_trigger_catalyst(
        "TEST", _now_utc(), fetcher=_stub_fetcher(None))
    assert result["available"] is False, result
    assert result["score"] == 0, result
    assert "Finnhub/yfinance" in result.get("reason", "") \
           or "Earnings" in result.get("reason", ""), result


def test_position_ohne_earnings():
    """Case 4: Fetcher kennt keinen Termin → available=False (gleich wie Case 3)."""
    result = gr._exit_p2_trigger_catalyst(
        "NOERN", _now_utc(), fetcher=_stub_fetcher(None))
    assert result["available"] is False, result
    assert result["score"] == 0, result


def test_earnings_today_crit():
    """Case 5: Earnings heute → score 100, crit=True."""
    today = _today_east()
    result = gr._exit_p2_trigger_catalyst(
        "TODAY", _now_utc(), fetcher=_stub_fetcher(today))
    assert result["score"] == 100, result
    assert result["warn"] is True, result
    assert result["crit"] is True, result
    assert result["details"]["trading_days_until"] == 0, result


def test_outside_window_3_trading_days():
    """Case 6: Earnings in 3 Trading-Days (außerhalb Window=2) → kein Trigger."""
    today = _today_east()
    # Montag + 3 Trading-Days = Donnerstag
    earn = today + timedelta(days=3)
    result = gr._exit_p2_trigger_catalyst(
        "TEST", _now_utc(), fetcher=_stub_fetcher(earn))
    assert result["score"] == 0, result
    assert result["warn"] is False, result
    assert result["crit"] is False, result
    assert result["details"]["trading_days_until"] == 3, result


def test_weekend_skipped():
    """Bonus: Earnings am nächsten Montag (= 5 Kalender-Tage) → 1 Trading-Day
    von Freitag aus → warn. Verifiziert dass Wochenende übersprungen wird."""
    # Anker: Freitag 08.05.2026 14:00 UTC
    fri_now = datetime(2026, 5, 8, 14, 0, tzinfo=timezone.utc)
    fri = fri_now.astimezone(gr.EASTERN).date()
    assert fri.weekday() == 4, fri  # Freitag
    mon = fri + timedelta(days=3)   # Montag (Sa, So, Mo)
    result = gr._exit_p2_trigger_catalyst(
        "WKND", fri_now, fetcher=_stub_fetcher(mon))
    assert result["details"]["trading_days_until"] == 1, result
    assert result["score"] == 50, result


def test_finnhub_real_path_no_key(monkeypatch=None):
    """Finnhub-Helper ohne API-Key → None ohne Netzwerk-Call."""
    today = _today_east()
    with patch.dict("os.environ", {}, clear=False):
        # FINNHUB_API_KEY explizit entfernen
        import os as _os
        _os.environ.pop("FINNHUB_API_KEY", None)
        edate = gr._fetch_finnhub_next_earnings("AAPL", today)
    assert edate is None, edate


def test_finnhub_real_path_mocked_response():
    """Finnhub-Helper mit gemocktem requests-Response."""
    today = _today_east()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(return_value=None)
    mock_resp.json = MagicMock(return_value={
        "earningsCalendar": [
            {"date": (today + timedelta(days=5)).strftime("%Y-%m-%d"), "symbol": "AAPL"},
            {"date": (today + timedelta(days=1)).strftime("%Y-%m-%d"), "symbol": "AAPL"},
        ]
    })
    with patch.object(gr.requests, "get", return_value=mock_resp):
        edate = gr._fetch_finnhub_next_earnings("AAPL", today, api_key="dummy")
    # Soll den NÄCHSTEN (=kleinsten ≥ today) zurückliefern
    assert edate == today + timedelta(days=1), edate


def test_yfinance_real_path_mocked():
    """yfinance-Fallback mit gemocktem Calendar-Dict."""
    today = _today_east()
    fake_ticker = MagicMock()
    fake_ticker.calendar = {
        "Earnings Date": [today + timedelta(days=4)],
    }
    with patch.object(gr.yf, "Ticker", return_value=fake_ticker):
        edate = gr._fetch_yfinance_next_earnings("AAPL", today)
    assert edate == today + timedelta(days=4), edate


def main():
    tests = [
        ("Case 1: Finnhub-Hit in window (days=1)",   test_finnhub_hit_in_window),
        ("Case 2: Yfinance-Hit am Window-Rand (days=2)", test_finnhub_miss_yfinance_hit_rand),
        ("Case 3: Beide Quellen leer",                test_both_sources_empty),
        ("Case 4: Position ohne Earnings",            test_position_ohne_earnings),
        ("Case 5: Earnings heute (crit)",             test_earnings_today_crit),
        ("Case 6: Außerhalb Window (days=3)",         test_outside_window_3_trading_days),
        ("Bonus: Wochenend-Skip Fr→Mo",               test_weekend_skipped),
        ("Bonus: Finnhub ohne API-Key",               test_finnhub_real_path_no_key),
        ("Bonus: Finnhub-Helper mit gemocktem Response", test_finnhub_real_path_mocked_response),
        ("Bonus: yfinance-Fallback mit gemocktem Cal", test_yfinance_real_path_mocked),
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
