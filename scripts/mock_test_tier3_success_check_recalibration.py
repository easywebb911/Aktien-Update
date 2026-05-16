"""Mock-Tests fuer Tier-3 success_check-Recalibration (16.05.2026).

Hintergrund (Diagnose 16.05.2026):
Vier Tier-3-Provider (edgar_8k, edgar_form4, edgar_13d_g, stocktwits)
zeigten 100% Fail-Rate im Provider-Health-Log. Root-Cause: Fetcher
schluckten Exception/HTTP-Error und returnten identische "leer"-Tuples
fuer drei Pfade (echter Fail / HTTP-Block / legitim leer).
success_check klassifizierte alle drei als fail.

Fix: Fetcher returnen None bei echtem Provider-Fehler. Legitim "keine
Daten" returnt weiterhin den Default-Wert. success_check vereinfacht
auf `lambda r: r is not None`.

Tests (Source + pythonische Replikation):
  1. Source: fetch_sec_8k Signatur returnt Tuple | None
  2. Source: fetch_sec_8k 403-Pfad gibt None zurueck
  3. Source: fetch_sec_8k Exception-Pfad gibt None zurueck
  4. Source: fetch_sec_8k Erfolg-aber-leer Pfad gibt (False, "", None)
  5. Source: fetch_sec_form4 analog (Tuple | None)
  6. Source: fetch_edgar_filings analog (list | None)
  7. Source: fetch_stocktwits_sentiment analog (dict | None)
  8. Source: _unpack_or_default-Helper existiert
  9. Source: Alle 4 Caller nutzen success_check=lambda r: r is not None
 10. Source: Alle 4 Caller nutzen _unpack_or_default mit korrektem Default
 11. Pythonisch: _unpack_or_default mit None
 12. Pythonisch: _unpack_or_default mit valid result
 13. Pythonisch: success_check-Logik klassifiziert legitim leer als success
 14. Pythonisch: success_check klassifiziert None als fail
 15. CLAUDE.md: Tier-3-Sektion erwaehnt Recalibration
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
KI = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def _func_block(func_def: str) -> str:
    start = KI.find(func_def)
    assert start > 0, f"Funktion {func_def!r} nicht gefunden"
    end = KI.find("\ndef ", start + 10)
    assert end > start
    return KI[start:end]


# ── Source: fetch_sec_8k ─────────────────────────────────────────────────────

def test_01_sec_8k_signature() -> None:
    assert "def fetch_sec_8k(ticker: str) -> tuple[bool, str, datetime | None] | None:" in KI, \
        "fetch_sec_8k Signatur fehlt oder nicht | None"


def test_02_sec_8k_403_returns_none() -> None:
    block = _func_block("def fetch_sec_8k(")
    # 403-Block: muss explizit return None (statt False-Tuple)
    pos_403 = block.find("status_code == 403")
    assert pos_403 > 0
    snippet = block[pos_403:pos_403 + 200]
    assert "return None" in snippet, "403-Pfad returnt nicht None"
    assert "return False, \"\", None" not in snippet, \
        "403-Pfad returnt noch False-Tuple"


def test_03_sec_8k_exception_returns_none() -> None:
    block = _func_block("def fetch_sec_8k(")
    # Exception-Pfad: return None statt fall-through zum False-Tuple
    assert "except Exception as exc:" in block
    # Im Exception-Block selbst muss `return None` stehen
    exc_idx = block.find("except Exception as exc:")
    exc_block = block[exc_idx:exc_idx + 300]
    assert "return None" in exc_block, "Exception-Pfad returnt nicht None"


def test_04_sec_8k_legit_empty_returns_tuple() -> None:
    block = _func_block("def fetch_sec_8k(")
    # Fall-through am Ende: (False, "", None) — legitim leer
    # Letzte Zeile vor naechster def
    assert "return False, \"\", None" in block, \
        "Legitim-leer-Pfad returnt nicht (False, '', None)"


# ── Source: fetch_sec_form4 ──────────────────────────────────────────────────

def test_05_sec_form4_analog() -> None:
    assert "def fetch_sec_form4(ticker: str) -> tuple[bool, str] | None:" in KI, \
        "fetch_sec_form4 Signatur fehlt"
    block = _func_block("def fetch_sec_form4(")
    # 403-Pfad: None
    assert block.count("return None") >= 2, \
        "Form4: < 2 None-Returns (sollte 403 + Exception abdecken)"
    # Legitim-leer: (False, "")
    assert "return False, \"\"" in block, "Form4: Legitim-leer-Tuple fehlt"


# ── Source: fetch_edgar_filings ──────────────────────────────────────────────

def test_06_edgar_filings_analog() -> None:
    assert "def fetch_edgar_filings(top10: list[dict]) -> list[dict] | None:" in KI, \
        "fetch_edgar_filings Signatur fehlt"
    block = _func_block("def fetch_edgar_filings(")
    # 3 Fail-Pfade: HTTP-non-200, Exception, ParseError
    assert block.count("return None") >= 3, \
        f"Erwarte >=3 None-Returns, gefunden {block.count('return None')}"
    # ENABLED=False / leeres top10 -> [] (kein Call, kein Fail)
    assert "return []" in block


# ── Source: fetch_stocktwits_sentiment ───────────────────────────────────────

def test_07_stocktwits_analog() -> None:
    assert "def fetch_stocktwits_sentiment(ticker: str) -> dict | None:" in KI, \
        "fetch_stocktwits_sentiment Signatur fehlt"
    block = _func_block("def fetch_stocktwits_sentiment(")
    # 2 Fail-Pfade: HTTP != 200, Exception
    assert block.count("return None") >= 2
    # ENABLED=False bzw empty ticker: Default-Dict ohne None
    assert '"bull_ratio": None, "msg_per_h": 0, "n_total": 0' in block


# ── Source: Caller-Anpassung ─────────────────────────────────────────────────

def test_08_unpack_helper_exists() -> None:
    assert "def _unpack_or_default(result, default)" in KI, \
        "_unpack_or_default-Helper fehlt"


def test_09_callers_use_new_success_check() -> None:
    # Anzahl der lambda r: r is not None Aufrufe muss >= 4 sein
    matches = re.findall(r'success_check=lambda r:\s*r is not None', KI)
    assert len(matches) >= 4, \
        f"Erwarte >=4 success_check-Lambdas (r is not None), gefunden {len(matches)}"
    # Alte Lambdas duerfen nicht mehr existieren
    assert "success_check=lambda r: bool(r and r[0])" not in KI, \
        "Alter has_8k/form4 success_check noch da"
    assert 'success_check=lambda r: bool(r and r.get("n_total", 0) > 0)' not in KI, \
        "Alter stocktwits success_check noch da"


def test_10_callers_use_unpack_default() -> None:
    # 4 Aufrufe von _unpack_or_default erwartet (8k/form4/13d_g/stocktwits)
    matches = re.findall(r'_unpack_or_default\(', KI)
    assert len(matches) >= 4, \
        f"Erwarte >=4 _unpack_or_default-Aufrufe, gefunden {len(matches)}"
    # SEC-8K-Tuple-Default
    assert "_unpack_or_default(\n                _r, (False, \"\", None))" in KI \
        or "_unpack_or_default(_r, (False, \"\", None))" in KI, \
        "8K-Default fehlt"
    # Form4-Tuple-Default
    assert '_unpack_or_default(_r, (False, ""))' in KI, "Form4-Default fehlt"
    # 13D/G-List-Default
    assert "_unpack_or_default(_r, [])" in KI, "13D/G-Default fehlt"
    # StockTwits-Dict-Default
    assert '"bull_ratio": None' in KI and '"n_total": 0' in KI


# ── Pythonisch: Helper-Logik ─────────────────────────────────────────────────

def _replicate_unpack(result, default):
    return result if result is not None else default


def test_11_unpack_none_returns_default() -> None:
    assert _replicate_unpack(None, (False, "", None)) == (False, "", None)
    assert _replicate_unpack(None, []) == []
    assert _replicate_unpack(None, {"bull_ratio": None}) == {"bull_ratio": None}


def test_12_unpack_valid_passes_through() -> None:
    assert _replicate_unpack((True, "title", None), (False, "", None)) == (True, "title", None)
    assert _replicate_unpack([{"a": 1}], []) == [{"a": 1}]
    assert _replicate_unpack({"n_total": 5}, {"n_total": 0}) == {"n_total": 5}


# ── Pythonisch: success_check-Semantik ──────────────────────────────────────

def _success(r):
    return r is not None


def test_13_legit_empty_is_success() -> None:
    # (False, "", None) — legitim leer 8-K
    assert _success((False, "", None)) is True, "Legitim-leer 8-K muss success sein"
    # (False, "") — legitim leer Form4
    assert _success((False, "")) is True
    # [] — legitim leer 13D/G
    assert _success([]) is True
    # Default-Dict mit n_total=0 — legitim leer stocktwits
    assert _success({"bull_ratio": None, "n_total": 0}) is True


def test_14_none_is_fail() -> None:
    assert _success(None) is False, "None muss fail sein"


# ── CLAUDE.md ────────────────────────────────────────────────────────────────

def test_15_claude_md_section() -> None:
    # Tier-3-Sektion muss Recalibration erwaehnen
    assert ("success_check" in CMD and
            ("r is not None" in CMD or "Recalibration" in CMD)), \
        "CLAUDE.md erwaehnt Recalibration nicht"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 fetch_sec_8k Signatur Tuple|None",       test_01_sec_8k_signature),
        ("02 8k 403 → None",                          test_02_sec_8k_403_returns_none),
        ("03 8k Exception → None",                    test_03_sec_8k_exception_returns_none),
        ("04 8k legit-leer → Tuple",                  test_04_sec_8k_legit_empty_returns_tuple),
        ("05 form4 analog",                           test_05_sec_form4_analog),
        ("06 edgar_filings analog",                   test_06_edgar_filings_analog),
        ("07 stocktwits analog",                      test_07_stocktwits_analog),
        ("08 _unpack_or_default-Helper",              test_08_unpack_helper_exists),
        ("09 Alle Caller: lambda r: r is not None",   test_09_callers_use_new_success_check),
        ("10 Caller _unpack_or_default mit Default",  test_10_callers_use_unpack_default),
        ("11 Pythonisch: None → default",             test_11_unpack_none_returns_default),
        ("12 Pythonisch: valid → passthrough",        test_12_unpack_valid_passes_through),
        ("13 Pythonisch: legit-leer = success",       test_13_legit_empty_is_success),
        ("14 Pythonisch: None = fail",                test_14_none_is_fail),
        ("15 CLAUDE.md Recalibration-Hinweis",        test_15_claude_md_section),
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
