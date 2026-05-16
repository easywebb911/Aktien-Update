"""Mock-Tests fuer Finnhub-Skip-Logging-Fix (16.05.2026).

Hintergrund:
FINNHUB_API_KEY war seit Inception nie konfiguriert. yfinance-Fallback
liefert die Earnings-Daten. Der Provider-Health-Wrapper zaehlte aber
jeden Aufruf als 'Fail' obwohl _fetch_finnhub_next_earnings einen
Hard-Skip vor dem HTTP-Call macht (`if not key: return None`).

Symptom (Diagnose 16.05.2026): Digest-Push meldet "finnhub: 4/4 calls
failed, latency 0ms" — pures Logging-Rauschen, kein funktionaler
Outage. yfinance-Fallback liefert weiter.

Fix: _fetch_next_earnings_date prueft FINNHUB_API_KEY vorab. Wenn
None oder leer -> direkt yfinance-Fallback, ohne den
_instrument_provider_call-Wrapper zu durchlaufen. Damit bleibt
_FINNHUB_ACCT["calls"] bei 0, main() emittiert keine Zeile
(call_attempted-Gating wirkt wie spezifiziert).

Tests:
  1. Source: _fetch_next_earnings_date prueft FINNHUB_API_KEY vor Wrapper
  2. Source: Wenn-Branch ruft _instrument_provider_call
  3. Source: Else-Branch setzt edate=None (yfinance-Pfad bleibt)
  4. Source: yfinance-Fallback wird in beiden Faellen aufgerufen wenn
     edate is None
  5. Source: Kommentar dokumentiert Fix-Begruendung (Diagnose-Memo
     16.05.2026)
  6. Logik-Replik: key=None -> _FINNHUB_ACCT bleibt unveraendert
  7. Logik-Replik: key="valid" -> _FINNHUB_ACCT.calls += 1
  8. Logik-Replik: yfinance-Date wird zurueckgegeben wenn Finnhub None
  9. Logik-Replik: Finnhub-Date hat Vorrang (mit Key)
 10. Logik-Replik: beide None -> Return None (kein Crash)
"""
from __future__ import annotations

import pathlib
import re
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")


# ── Helper: Funktions-Block extrahieren ─────────────────────────────────────

def _func_block(func_def: str) -> str:
    start = GR.find(func_def)
    assert start > 0, f"Funktion {func_def!r} nicht gefunden"
    end = GR.find("\ndef ", start + 10)
    assert end > start
    return GR[start:end]


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_01_checks_env_var_before_wrapper() -> None:
    block = _func_block("def _fetch_next_earnings_date(")
    # Env-Check muss vor _instrument_provider_call kommen
    env_check_idx = block.find('os.environ.get("FINNHUB_API_KEY")')
    wrapper_idx   = block.find("_instrument_provider_call")
    assert env_check_idx > 0, "Env-Check fehlt"
    assert wrapper_idx > 0, "_instrument_provider_call fehlt"
    assert env_check_idx < wrapper_idx, \
        "Env-Check kommt nicht vor _instrument_provider_call"


def test_02_if_branch_calls_wrapper() -> None:
    block = _func_block("def _fetch_next_earnings_date(")
    # if env var: _instrument_provider_call(_FINNHUB_ACCT, ...)
    assert 'if os.environ.get("FINNHUB_API_KEY"):' in block, \
        "if-Branch-Bedingung fehlt"
    # Wrapper-Call innerhalb des if-Blocks (auf den if-Zeilen folgend)
    if_pos = block.find('if os.environ.get("FINNHUB_API_KEY"):')
    after_if = block[if_pos:]
    next_else = after_if.find("else:")
    if_body = after_if[:next_else]
    assert "_instrument_provider_call" in if_body, \
        "Wrapper-Call nicht im if-Body"
    assert "_FINNHUB_ACCT" in if_body, "_FINNHUB_ACCT nicht im if-Body"


def test_03_else_branch_sets_none() -> None:
    block = _func_block("def _fetch_next_earnings_date(")
    # else: edate = None
    assert re.search(r"else:\s*\n\s*edate\s*=\s*None", block), \
        "else: edate=None fehlt"


def test_04_yfinance_fallback_still_present() -> None:
    block = _func_block("def _fetch_next_earnings_date(")
    # if edate is None: edate = _fetch_yfinance_next_earnings(...)
    assert "_fetch_yfinance_next_earnings(ticker, today)" in block, \
        "yfinance-Fallback fehlt"
    # Fallback steht NACH dem if/else-Block
    fallback_idx = block.find("_fetch_yfinance_next_earnings")
    else_idx = block.find("else:")
    assert fallback_idx > else_idx, "yfinance-Fallback steht nicht nach else"


def test_05_comment_documents_fix() -> None:
    block = _func_block("def _fetch_next_earnings_date(")
    assert "Skip-Logging-Fix" in block or "Diagnose-Memo 16.05.2026" in block, \
        "Fix-Begruendung als Kommentar fehlt"


# ── Logik-Replik: Pythonische 1:1-Replikation ──────────────────────────────

class _Acct:
    def __init__(self):
        self.calls = 0
        self.fails = 0


def _replicate_fetch_next_earnings_date(
    ticker, today,
    env_key,
    finnhub_result,
    yfinance_result,
    acct: _Acct,
):
    """1:1-Replikat der neuen Code-Pfad-Logik.

    - env_key: simulierter Inhalt von FINNHUB_API_KEY env
    - finnhub_result: was _fetch_finnhub_next_earnings liefern wuerde
                      (None wenn Hard-Skip oder kein Result)
    - yfinance_result: was _fetch_yfinance_next_earnings liefern wuerde
    - acct: Mock fuer _FINNHUB_ACCT
    """
    edate = None
    if env_key:
        # Replik von _instrument_provider_call: Counter inkrementieren,
        # Funktion ausfuehren, success_check anwenden.
        acct.calls += 1
        edate = finnhub_result
        if edate is None:
            acct.fails += 1
    # else: kein Counter-Update, edate bleibt None
    if edate is None:
        edate = yfinance_result
    return edate


def test_06_no_key_no_acct_increment() -> None:
    acct = _Acct()
    res = _replicate_fetch_next_earnings_date(
        ticker="AMC", today=date(2026, 5, 16),
        env_key=None,         # FINNHUB_API_KEY nicht gesetzt
        finnhub_result=None,  # wuerde via Hard-Skip None liefern, wird aber nie aufgerufen
        yfinance_result=date(2026, 6, 1),
        acct=acct,
    )
    assert acct.calls == 0, f"calls duerfen nicht inkrementiert sein, got {acct.calls}"
    assert acct.fails == 0, f"fails duerfen nicht inkrementiert sein, got {acct.fails}"
    assert res == date(2026, 6, 1), "yfinance-Result wird zurueckgegeben"


def test_07_with_key_acct_increments() -> None:
    acct = _Acct()
    res = _replicate_fetch_next_earnings_date(
        ticker="IONQ", today=date(2026, 5, 16),
        env_key="sk_test_valid",
        finnhub_result=date(2026, 5, 28),
        yfinance_result=None,
        acct=acct,
    )
    assert acct.calls == 1, f"calls muss inkrementiert sein, got {acct.calls}"
    assert acct.fails == 0, "Finnhub-Result war non-None, also kein Fail"
    assert res == date(2026, 5, 28), "Finnhub-Result hat Vorrang"


def test_08_yfinance_takes_over_when_finnhub_none() -> None:
    acct = _Acct()
    res = _replicate_fetch_next_earnings_date(
        ticker="RR", today=date(2026, 5, 16),
        env_key="sk_test_valid",
        finnhub_result=None,        # Finnhub liefert None (z.B. kein Eintrag)
        yfinance_result=date(2026, 7, 15),
        acct=acct,
    )
    assert acct.calls == 1
    assert acct.fails == 1, "Finnhub None counts als fail im Provider-Health"
    assert res == date(2026, 7, 15), "yfinance-Fallback uebernimmt"


def test_09_finnhub_priority_over_yfinance() -> None:
    acct = _Acct()
    res = _replicate_fetch_next_earnings_date(
        ticker="CRMD", today=date(2026, 5, 16),
        env_key="sk_test_valid",
        finnhub_result=date(2026, 6, 5),
        yfinance_result=date(2026, 7, 1),
        acct=acct,
    )
    assert res == date(2026, 6, 5), "Finnhub hat Vorrang vor yfinance"


def test_10_both_none_returns_none() -> None:
    acct = _Acct()
    res = _replicate_fetch_next_earnings_date(
        ticker="UNKNOWN", today=date(2026, 5, 16),
        env_key=None,
        finnhub_result=None,
        yfinance_result=None,
        acct=acct,
    )
    assert res is None, "Beide None → Return None"
    assert acct.calls == 0


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 Env-Check vor Wrapper",                  test_01_checks_env_var_before_wrapper),
        ("02 if-Branch ruft Wrapper",                 test_02_if_branch_calls_wrapper),
        ("03 else-Branch setzt edate=None",           test_03_else_branch_sets_none),
        ("04 yfinance-Fallback unveraendert",         test_04_yfinance_fallback_still_present),
        ("05 Kommentar dokumentiert Fix",             test_05_comment_documents_fix),
        ("06 Key=None → kein Acct-Increment",         test_06_no_key_no_acct_increment),
        ("07 Key valid → Acct+1",                     test_07_with_key_acct_increments),
        ("08 Finnhub None → yfinance-Fallback",       test_08_yfinance_takes_over_when_finnhub_none),
        ("09 Finnhub-Vorrang bei valid",              test_09_finnhub_priority_over_yfinance),
        ("10 Beide None → Return None",               test_10_both_none_returns_none),
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
