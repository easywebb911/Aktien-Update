"""Mock-Tests fuer KI-Agent-Coverage-Erweiterung Phase 2 (16.05.2026).

Hintergrund: Phase 1 (PR #176) hat Conviction fuer Watchlist-Outsider
bereitgestellt. Phase 2 erweitert nun den KI-Agent-Coverage-Pool auf
Top-10 ∪ persoenliche Watchlist ∪ aktive Positionen.

Push-Spam-Schutz: Conviction-Gating ≥ 75 in detect_anomalies wirkt
weiterhin. Defensive Erweiterung: bei _conv_today=None UND Ticker
NICHT in Top-10 → suppress (vermeidet Push-Spam bei Daten-Luecken).

Tests:
  1. Source: parse_monitored_tickers existiert + Signatur list[str]
  2. Source: main() ruft parse_monitored_tickers statt parse_top_tickers
  3. Source: max_workers von 8 auf 10 erhoeht
  4. Source: edgar_monitored statt edgar_top10 (Pool-aware Naming)
  5. Source: defensive Conviction-Gating Erweiterung (None + outsider)
  6. Source: _top10_set wird vor dem Loop berechnet
  7. Pythonisch: Pool-Set-Union (Top-10 ∪ Watchlist ∪ Positions)
  8. Pythonisch: Edge: fehlende watchlist_personal.json → nur Top-10 + Pos
  9. Pythonisch: Edge: fehlende positions.json → nur Top-10 + WL
 10. Pythonisch: Edge: beide leer → nur Top-10
 11. Pythonisch: Duplicate-Handling (Position in Watchlist)
 12. Pythonisch: Ticker-Hygiene (TICKER, leere, zu lang)
 13. Pythonisch: Gating Top-10 ohne Conviction: NICHT suppress
 14. Pythonisch: Gating Outsider ohne Conviction: suppress
 15. Pythonisch: Gating Conviction < 75: suppress (Status quo)
 16. Pythonisch: Gating conviction_high: nie suppress
 17. CLAUDE.md Phase-2-Sektion vorhanden
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
KI = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def _func_block(func_def: str) -> str:
    start = KI.find(func_def)
    assert start > 0, f"Funktion {func_def!r} nicht gefunden"
    end = KI.find("\ndef ", start + 10)
    assert end > start
    return KI[start:end]


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_01_helper_exists() -> None:
    assert "def parse_monitored_tickers() -> list[str]:" in KI, \
        "parse_monitored_tickers Signatur fehlt"


def test_02_main_uses_new_helper() -> None:
    # parse_top_tickers() wird ersetzt
    assert "tickers = parse_monitored_tickers()" in KI, \
        "main() ruft parse_monitored_tickers nicht"
    # Alter direkter Aufruf (tickers = parse_top_tickers()) darf nicht
    # mehr existieren — parse_top_tickers() bleibt als interner Helper
    # innerhalb parse_monitored_tickers() noch verfuegbar.
    pattern = r"\n    tickers = parse_top_tickers\(\)"
    assert not re.search(pattern, KI), \
        "main() ruft noch parse_top_tickers direkt auf"


def test_03_max_workers_increased() -> None:
    assert "ThreadPoolExecutor(max_workers=10)" in KI, \
        "Worker-Pool nicht auf 10 erhoeht"
    assert "ThreadPoolExecutor(max_workers=8)" not in KI, \
        "Alter max_workers=8 noch vorhanden"


def test_04_edgar_var_renamed() -> None:
    # edgar_top10 wurde umbenannt zu edgar_monitored
    assert "edgar_monitored" in KI, "edgar_monitored-Variable fehlt"
    assert "edgar_top10" not in KI, "Alter edgar_top10-Name noch vorhanden"


def test_05_defensive_gating_extension() -> None:
    # Suche nach defensive None-Gating-Logik
    pattern = r"_conv_today is None and ticker not in _top10_set"
    assert re.search(pattern, KI), \
        "Defensive None-Gating fuer Watchlist-Outsider fehlt"


def test_06_top10_set_built() -> None:
    assert "_top10_set = set(parse_top_tickers())" in KI, \
        "_top10_set-Berechnung fehlt"


# ── Pythonische Replikation Pool-Logik ──────────────────────────────────────

_TICKER_RE = re.compile(r"^[A-Z0-9]{1,6}$")


def _replicate_pool(top10: list, watchlist_payload, positions_payload) -> list:
    tickers = set(top10)
    if isinstance(watchlist_payload, list):
        for raw in watchlist_payload:
            if not raw:
                continue
            t = str(raw).strip().upper().split(".")[0]
            if _TICKER_RE.match(t):
                tickers.add(t)
    if isinstance(positions_payload, dict):
        for raw in positions_payload.keys():
            t = str(raw).strip().upper().split(".")[0]
            if _TICKER_RE.match(t):
                tickers.add(t)
    return sorted(tickers)


def test_07_pool_union() -> None:
    pool = _replicate_pool(
        top10=["SKYQ", "GEMI", "PZZA"],
        watchlist_payload=["AMC", "IONQ", "RR", "CRMD", "AI"],
        positions_payload={"AMC": {}, "IONQ": {}, "CRMD": {}},
    )
    expected = sorted({"SKYQ", "GEMI", "PZZA", "AMC", "IONQ", "RR", "CRMD", "AI"})
    assert pool == expected, f"Pool falsch: {pool}"


def test_08_missing_watchlist() -> None:
    pool = _replicate_pool(
        top10=["SKYQ", "GEMI"],
        watchlist_payload=None,
        positions_payload={"CRMD": {}},
    )
    assert pool == sorted(["SKYQ", "GEMI", "CRMD"])


def test_09_missing_positions() -> None:
    pool = _replicate_pool(
        top10=["SKYQ"],
        watchlist_payload=["AI", "AMC"],
        positions_payload=None,
    )
    assert pool == sorted(["SKYQ", "AI", "AMC"])


def test_10_both_empty() -> None:
    pool = _replicate_pool(
        top10=["SKYQ", "GEMI"],
        watchlist_payload=None,
        positions_payload=None,
    )
    assert pool == sorted(["SKYQ", "GEMI"])


def test_11_duplicate_handling() -> None:
    # Position UND Watchlist haben CRMD → einmal im Pool
    pool = _replicate_pool(
        top10=["GEMI"],
        watchlist_payload=["CRMD", "AMC"],
        positions_payload={"CRMD": {}, "RR": {}},
    )
    assert sorted(pool) == sorted(["GEMI", "CRMD", "AMC", "RR"]), \
        f"Duplikate: {pool}"


def test_12_ticker_hygiene() -> None:
    pool = _replicate_pool(
        top10=["AAPL"],
        watchlist_payload=["TOOLONG7CHAR", "", None, "AMC", "  ionq  "],
        positions_payload={"VALID6": {}},
    )
    # TOOLONG7CHAR und "" werden gefiltert, "  ionq  " wird normalized,
    # None gefiltert, VALID6 akzeptiert
    assert "TOOLONG7CHAR" not in pool
    assert "" not in pool
    assert "AMC" in pool
    assert "IONQ" in pool
    assert "VALID6" in pool


# ── Defensive Gating-Logik (replikat) ───────────────────────────────────────

_THRESHOLD = 75


def _replicate_gating(trigger: str, conv_today, ticker: str,
                      top10_set: set) -> bool:
    """Returnt True wenn Push SUPPRIMED werden soll."""
    suppress = False
    if trigger != "conviction_high":
        if isinstance(conv_today, (int, float)) and conv_today < _THRESHOLD:
            suppress = True
        elif conv_today is None and ticker not in top10_set:
            suppress = True
    return suppress


def test_13_top10_without_conviction_NOT_suppressed() -> None:
    # Top-10-Ticker, Conviction None → NICHT suppress (Phase-1-Defekt)
    assert _replicate_gating("rvol_explosion", None, "SKYQ",
                              {"SKYQ", "GEMI"}) is False


def test_14_outsider_without_conviction_suppressed() -> None:
    # Outsider-Ticker, Conviction None → suppress (defensive)
    assert _replicate_gating("rvol_explosion", None, "AMC",
                              {"SKYQ", "GEMI"}) is True


def test_15_low_conviction_suppressed() -> None:
    # Conviction 50 < 75 → suppress (Status quo)
    assert _replicate_gating("rvol_explosion", 50, "AMC",
                              {"SKYQ", "GEMI"}) is True
    assert _replicate_gating("rvol_explosion", 50, "SKYQ",
                              {"SKYQ", "GEMI"}) is True


def test_16_conviction_high_never_suppressed() -> None:
    # conviction_high-Trigger wird NIE suppress'd
    assert _replicate_gating("conviction_high", 50, "AMC",
                              {"SKYQ", "GEMI"}) is False
    assert _replicate_gating("conviction_high", None, "AMC",
                              {"SKYQ", "GEMI"}) is False


# ── CLAUDE.md ────────────────────────────────────────────────────────────────

def test_17_claude_md_section() -> None:
    # Phase-2-Coverage-Erweiterung sollte in CLAUDE.md sein
    assert ("KI-Agent-Coverage" in CMD or "parse_monitored_tickers" in CMD
            or "Coverage-Pool" in CMD), \
        "Coverage-Sektion in CLAUDE.md fehlt"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 parse_monitored_tickers Signatur",            test_01_helper_exists),
        ("02 main() ruft parse_monitored_tickers",         test_02_main_uses_new_helper),
        ("03 max_workers 10",                              test_03_max_workers_increased),
        ("04 edgar_monitored statt edgar_top10",           test_04_edgar_var_renamed),
        ("05 Defensive None-Gating fuer Outsider",         test_05_defensive_gating_extension),
        ("06 _top10_set wird gebaut",                      test_06_top10_set_built),
        ("07 Pool-Union (top10 ∪ wl ∪ pos)",               test_07_pool_union),
        ("08 Edge: missing watchlist",                     test_08_missing_watchlist),
        ("09 Edge: missing positions",                     test_09_missing_positions),
        ("10 Edge: beide leer",                            test_10_both_empty),
        ("11 Duplicate-Handling",                          test_11_duplicate_handling),
        ("12 Ticker-Hygiene",                              test_12_ticker_hygiene),
        ("13 Top-10 + None Conviction → NICHT suppress",   test_13_top10_without_conviction_NOT_suppressed),
        ("14 Outsider + None Conviction → suppress",       test_14_outsider_without_conviction_suppressed),
        ("15 Conviction < 75 → suppress (Status quo)",     test_15_low_conviction_suppressed),
        ("16 conviction_high → nie suppress",              test_16_conviction_high_never_suppressed),
        ("17 CLAUDE.md Phase-2-Sektion",                   test_17_claude_md_section),
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
