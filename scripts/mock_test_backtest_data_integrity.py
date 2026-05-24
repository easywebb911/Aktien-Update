"""Mock-Tests fuer Backtest-Daten-Integritaet (PR-Folge Diagnose 21.05.2026).

Zwei Source-Inspection-Tests, die die zwei Bugs gegen Regression sichern:

1. hist_5d-Propagation im Enrichment-c.update-Block
   - Vor Fix: hist_5d ist im yfd-Dict, wird aber NICHT auf das Top-10-
     Stock-Dict gemerged. Die drei Helper (_compute_rvol_buildup_5d,
     _compute_vol_stability_5d, _compute_coiled_spring_score) lesen
     s.get("hist_5d"), bekommen None, returnen None. Trend-Felder
     bleiben in backtest_history.json zu 0 % gefuellt.
   - Nach Fix: c.update enthaelt hist_5d-Zeile, die drei Felder werden
     ab naechstem Daily-Run-postclose befuellt.

2. Wochenend-Schreibschutz in _append_backtest_entries
   - Vor Fix: manuelle workflow_dispatch-Trigger am Sa/So schreiben
     Backtest-Eintraege mit Wochenend-Datum. yfinance hat keine Sa/So-
     Close-Werte → update_backtest_returns skippt sie permanent → die
     Eintraege haben NIE Outcomes (96 betroffene Eintraege per 21.05.).
   - Nach Fix: Wochenend-Eintraege werden nicht mehr geschrieben.
     Bestehende Leichen bleiben unangetastet (separater Cleanup-PR).

Beide Tests sind Source-Inspection (Pattern-Matching gegen den Code-
String). Funktionale Mock-Tests gegen ``_append_backtest_entries``
selbst sind nicht ausfuehrbar (yfinance-Import nicht in Sandbox), aber
das Pattern-Match deckt die Praesenz der Schutz-Logik zuverlaessig ab.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _read(p: str) -> str:
    return pathlib.Path(p).read_text(encoding="utf-8")


# ── Bug 1: hist_5d-Propagation ──────────────────────────────────────────────


def test_01_hist_5d_in_c_update_block():
    """Der c.update-Block im Enrichment-Loop muss hist_5d propagieren.
    Vor 21.05.2026 fehlte dieser Eintrag → backtest_history hatte 3 von 4
    Trend-Feldern dauerhaft 0 % gefuellt seit PR #142.
    """
    src = _read("generate_report.py")  # c.update-Caller blieb in generate_report.py
    # Wir suchen einen c.update-Block, der "hist_5d" als Key + yfd.get(...)
    # als Value enthaelt. Robust gegen Whitespace-Variationen; non-greedy
    # zwischen Container-Start und Container-Ende (DOTALL).
    pattern = re.compile(
        r'c\.update\(\{.*?"hist_5d"\s*:\s*yfd\.get\("hist_5d"\).*?\}\)',
        re.DOTALL,
    )
    assert pattern.search(src), (
        "Bug 1 Regression: c.update propagiert hist_5d NICHT mehr aus yfd. "
        "Folge: 3 Trend-Felder (rvol_buildup_5d, vol_stability_5d, "
        "coiled_spring_score) sind in backtest_history.json wieder 0 % "
        "gefuellt."
    )


def test_02_hist_5d_consumed_in_build_backtest_extension():
    """Der Backtest-Extension-Builder muss s.get('hist_5d') lesen — wenn
    diese Konsumentenstelle wegfaellt, ist der Propagations-Fix nutzlos.
    """
    src = _read("backtest_history.py")
    assert 's.get("hist_5d")' in src, (
        "_build_backtest_extension liest hist_5d nicht mehr — der "
        "Propagations-Fix ohne Konsument waere wirkungslos."
    )


def test_03_yfd_writes_hist_5d():
    """Source-Pfad: get_yfinance_data schreibt hist_5d ins yfd-Dict.
    Falls dieser Schreibe wegfaellt, ist der c.update-Merge ohne Quelle.
    """
    src = _read("generate_report.py")  # get_yfinance_data blieb in generate_report.py
    # Suche nach dem yfd-Schreibe-Pattern: "hist_5d":        hist_5d,
    assert re.search(r'"hist_5d"\s*:\s*hist_5d', src), (
        "get_yfinance_data setzt yfd['hist_5d'] = hist_5d nicht mehr — "
        "Source-Pfad fuer Trend-Felder waere kaputt."
    )


# ── Bug 2: Wochenend-Schreibschutz ─────────────────────────────────────────


def test_04_weekend_guard_in_append_backtest_entries():
    """_append_backtest_entries muss Wochenend-report_date als early-return
    behandeln. Vor 21.05.2026 wurden Sa/So-Eintraege geschrieben, deren
    Outcomes update_backtest_returns permanent skipt — 96 Leichen
    Bestandsaufnahme.
    """
    src = _read("backtest_history.py")
    # Suche im Body von _append_backtest_entries nach einer weekday-Pruefung.
    fn_match = re.search(
        r"def _append_backtest_entries\(.*?(?=^def |\Z)",
        src, re.MULTILINE | re.DOTALL,
    )
    assert fn_match, "_append_backtest_entries-Funktion nicht gefunden"
    fn_body = fn_match.group(0)
    # weekday() >= 5 ist der kanonische Sa/So-Check in Python.
    assert "weekday() >= 5" in fn_body, (
        "Bug 2 Regression: _append_backtest_entries hat keine weekday()-"
        "Pruefung mehr — Wochenend-Eintraege ohne Outcomes wuerden wieder "
        "akkumulieren."
    )
    # Die Pruefung muss VOR _load_backtest_history stehen, sonst wuerden
    # bereits Liste/Lookups laufen — defensive sanity check.
    weekday_pos = fn_body.find("weekday() >= 5")
    load_pos    = fn_body.find("_load_backtest_history()")
    assert weekday_pos > 0 and load_pos > 0, (
        "weekday-Pruefung oder _load_backtest_history nicht im Funktions-Body"
    )
    assert weekday_pos < load_pos, (
        "Wochenend-Schreibschutz muss VOR _load_backtest_history greifen, "
        "damit keine teure History-Operation fuer Sa/So-Runs anfaellt."
    )


def test_05_weekend_guard_returns_zero():
    """Im Wochenend-Pfad muss return 0 stehen (Health-Check S4 liest den
    n_added-Wert; ein Sa/So-Run soll als 'nichts angehaengt' gelten, nicht
    als Fehler).
    """
    src = _read("backtest_history.py")
    fn_match = re.search(
        r"def _append_backtest_entries\(.*?(?=^def |\Z)",
        src, re.MULTILINE | re.DOTALL,
    )
    assert fn_match
    fn_body = fn_match.group(0)
    # Zwischen "weekday() >= 5" und dem naechsten "return" oder "history ="
    # muss ein "return 0" stehen.
    wk_idx = fn_body.find("weekday() >= 5")
    tail   = fn_body[wk_idx:wk_idx + 800]
    assert "return 0" in tail, (
        "Wochenend-Schreibschutz fehlt return 0 — Funktion wuerde nach "
        "dem warning weiterlaufen und Eintraege schreiben."
    )


def test_06_weekend_guard_logs_warning():
    """Easy braucht im Workflow-Log einen sichtbaren Hinweis warum nichts
    angehaengt wurde."""
    src = _read("backtest_history.py")
    fn_match = re.search(
        r"def _append_backtest_entries\(.*?(?=^def |\Z)",
        src, re.MULTILINE | re.DOTALL,
    )
    assert fn_match
    fn_body = fn_match.group(0)
    wk_idx = fn_body.find("weekday() >= 5")
    tail   = fn_body[wk_idx:wk_idx + 800]
    assert "log.warning" in tail, (
        "Wochenend-Skip muss log.warning emittieren, damit Easy im "
        "Workflow-Log sieht warum nichts angehaengt wurde."
    )


def test_07_backtest_enabled_check_remains_first():
    """Der bestehende BACKTEST_ENABLED-Check muss ZUERST greifen — der
    Wochenend-Guard kommt danach. Reihenfolge sichert: bei disabled
    Backtest gar nichts tun, kein Datums-Parse-Versuch.
    """
    src = _read("backtest_history.py")
    fn_match = re.search(
        r"def _append_backtest_entries\(.*?(?=^def |\Z)",
        src, re.MULTILINE | re.DOTALL,
    )
    assert fn_match
    fn_body = fn_match.group(0)
    enabled_pos = fn_body.find("BACKTEST_ENABLED")
    weekday_pos = fn_body.find("weekday() >= 5")
    assert enabled_pos > 0 and weekday_pos > 0
    assert enabled_pos < weekday_pos, (
        "BACKTEST_ENABLED-Check muss vor weekday-Guard greifen."
    )


def main() -> int:
    tests = [
        test_01_hist_5d_in_c_update_block,
        test_02_hist_5d_consumed_in_build_backtest_extension,
        test_03_yfd_writes_hist_5d,
        test_04_weekend_guard_in_append_backtest_entries,
        test_05_weekend_guard_returns_zero,
        test_06_weekend_guard_logs_warning,
        test_07_backtest_enabled_check_remains_first,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except AssertionError as exc:
            print(f"  ✗ {t.__name__}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ✗ {t.__name__}: unexpected {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} Tests OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
