"""Mock-Tests für den Setup-Edge/Conviction-Freeze-Zähler im Health-Check-
Digest (11.10.2026, "🧪 Freeze-Zähler").

Deckt ab:
  1  Grenzfälle Population (SESSION_HANDOVER.md, Setup-Edge-Re-Test-Freeze,
     Punkt 2): Eintrittsdatum == Freeze-Datum (10.10.2026) zaehlt NICHT,
     Eintrittsdatum > Freeze-Datum (12.10.2026) zaehlt; fehlende
     return_5d/return_10d zaehlen nicht; provenance=="backfill" zaehlt NIE;
     Dubletten (ticker, date) zaehlen einmal.
  2  Rate (letzte ``_FREEZE_RATE_WINDOW_DAYS`` = 28 Kalendertage, Wächter-
     Fix 30.10.2026 — war 14T, zu kurz fuer die ~15-Kalendertage-Reifezeit
     eines Eintrags, zeigte praktisch immer 0): nur Freeze-Population-
     Zeilen innerhalb des Fensters, reine Zaehlung (zeilen, distinct
     Handelstage). test_09b belegt den Unterschied explizit gegen das alte
     14T-Fenster (gleiche Daten, zwei "now"-Werte).
  3  KI-Abdeckung des letzten Report-Tags (backtest_history.json):
     10/10, 7/10, 0/10 (Schluessel vorhanden, aber alle None) und "n/a"
     (kein Eintrag traegt den Schluessel ki_signal_ts ueberhaupt).
  4  Fail-soft: fehlende/kaputte Dateien -> "n/a"/"nicht ermittelbar", nie
     eine Exception; Verdrahtung in format_digest_body (alle 3 Klassen,
     backward-compat ohne freeze_line).
  5  Vorher/Nachher-Beleg: der §4-Zaehler (_count_matured_retest) liefert
     nach dem Shared-Helper-Refactor exakt denselben Wert wie vorher
     (siehe test_10).

KEINE Outcome-Statistiken (keine Renditen/Trefferquoten/AUC/Quantile) —
reine Zaehlung von Zeilen und Tagen. REIN LESEND, kein Netzwerk,
deterministisch (Kategorie A).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402

FREEZE_DATE = hc._FREEZE_DATE_STR  # "10.10.2026" — aus config.py gespiegelt


def _tmp_jsonl(lines: list[str], name: str = "matured_backtest_export.jsonl") -> str:
    d = tempfile.mkdtemp()
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))
    return p


def _tmp_json(obj, name: str = "backtest_history.json") -> str:
    d = tempfile.mkdtemp()
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    return p


def _row(ticker, date, provenance="forward", score=75.0,
         return_5d=1.0, return_10d=2.0) -> str:
    return json.dumps({
        "ticker": ticker, "date": date, "provenance": provenance,
        "score": score, "return_5d": return_5d, "return_10d": return_10d,
    })


# ── 1. Population-Grenzfälle ────────────────────────────────────────────────

def test_01_entry_date_equal_freeze_not_counted() -> None:
    p = _tmp_jsonl([_row("A", FREEZE_DATE)])  # == 10.10.2026, NICHT zählen
    n, total = hc._count_setup_edge_freeze_population(p)
    assert n == 0, f"Eintrittsdatum == Freeze-Datum zählt fälschlich: n={n}"
    assert total == 1


def test_02_entry_date_after_freeze_counted() -> None:
    p = _tmp_jsonl([_row("A", "12.10.2026")])  # > 10.10.2026, zählt
    n, total = hc._count_setup_edge_freeze_population(p)
    assert n == 1, f"Eintrittsdatum > Freeze-Datum zählt nicht: n={n}"
    assert total == 1


def test_03_missing_returns_not_counted() -> None:
    p = _tmp_jsonl([
        _row("A", "12.10.2026", return_5d=None),
        _row("B", "12.10.2026", return_10d=None),
        _row("C", "12.10.2026", return_5d=None, return_10d=None),
    ])
    n, total = hc._count_setup_edge_freeze_population(p)
    assert n == 0, f"fehlende Returns zählen fälschlich: n={n}"
    assert total == 3


def test_04_backfill_never_counted() -> None:
    p = _tmp_jsonl([_row("A", "12.10.2026", provenance="backfill")])
    n, total = hc._count_setup_edge_freeze_population(p)
    assert n == 0, f"backfill zählt fälschlich: n={n}"
    assert total == 1


def test_05_duplicates_ticker_date_count_once() -> None:
    p = _tmp_jsonl([
        _row("A", "12.10.2026"),
        _row("A", "12.10.2026"),   # exakte Dublette (ticker, date) → 1×
        _row("A", "13.10.2026"),   # anderes Datum, selber Ticker → eigener Eintrag
    ])
    n, total = hc._count_setup_edge_freeze_population(p)
    assert n == 2, f"Dubletten nicht korrekt dedupliziert: n={n} (erwartet 2)"
    assert total == 3


def test_06_all_scores_counted_no_ge70_filter() -> None:
    # Im Unterschied zu §4: KEIN score>=70-Filter — auch niedrige Scores zählen.
    p = _tmp_jsonl([
        _row("A", "12.10.2026", score=10.0),
        _row("B", "12.10.2026", score=None),  # score fehlt ist hier egal (kein Filter)
    ])
    n, total = hc._count_setup_edge_freeze_population(p)
    assert n == 2, f"Freeze-Population filtert fälschlich nach Score: n={n}"


def test_07_missing_file_none() -> None:
    assert hc._count_setup_edge_freeze_population("/nonexistent/x.jsonl") is None


def test_08_empty_file_zero() -> None:
    p = _tmp_jsonl([])
    assert hc._count_setup_edge_freeze_population(p) == (0, 0)


# ── 2. Rate (letzte 28 Kalendertage, war 14T — Wächter-Fix 30.10.2026) ──────

def test_09_rate_counts_only_within_window() -> None:
    assert hc._FREEZE_RATE_WINDOW_DAYS == 28, \
        "Fenster-Konstante muss 28 sein (Wächter-Fix 30.10.2026)"
    now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)  # cutoff = 27.09.2026
    p = _tmp_jsonl([
        _row("A", "12.10.2026"),   # innerhalb (>= 27.09.)
        _row("B", "20.10.2026"),   # innerhalb
        _row("C", "01.10.2026"),   # VOR Freeze-Datum (10.10.) → fällt eh raus (nicht Population)
        _row("D", "15.09.2026"),   # weit außerhalb UND vor Freeze
    ])
    zeilen, tage = hc._freeze_rate_last_14d(p, now=now)
    assert zeilen == 2, f"Rate-Fenster falsch gezählt: zeilen={zeilen} (erwartet 2)"
    assert tage == 2, f"distinct Handelstage falsch: tage={tage} (erwartet 2)"


def test_09b_rate_28d_window_catches_entries_14d_window_missed() -> None:
    # Direkter Vorher/Nachher-Beleg des Wächter-Befunds (30.10.2026): dieselben
    # Zeilen, die unter dem ALTEN 14-Tage-Fenster rausgefallen waeren, werden
    # unter dem NEUEN 28-Tage-Fenster gezaehlt. "now" bewusst 14 Tage nach den
    # Eintraegen gewaehlt, damit der alte 14T-Cutoff sie gerade eben ausschliesst,
    # der neue 28T-Cutoff sie aber noch erfasst.
    now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    p = _tmp_jsonl([
        _row("A", "12.10.2026"),   # 27 Tage vor "now" -> innerhalb 28T, ausserhalb altem 14T
        _row("B", "20.10.2026"),   # 19 Tage vor "now" -> innerhalb 28T, ausserhalb altem 14T
    ])
    zeilen, tage = hc._freeze_rate_last_14d(p, now=now)
    assert (zeilen, tage) == (2, 2), (
        f"28T-Fenster muss beide Zeilen erfassen: got=({zeilen},{tage})")

    # Kontrollprobe: mit dem ALTEN 14-Tage-Fenster (manuell nachgebildet,
    # ohne die Produktionskonstante zu nutzen) waeren beide Zeilen ausserhalb
    # des Fensters gelegen -- das ist exakt der "zeigt praktisch immer 0"-Bug.
    from datetime import timedelta
    old_cutoff = now.date() - timedelta(days=14)
    assert old_cutoff > datetime(2026, 10, 20).date(), (
        "Testannahme verletzt: alter 14T-Cutoff muesste nach beiden "
        "Eintragsdaten liegen, um den Bug zu demonstrieren")


def test_10_rate_missing_file_none() -> None:
    assert hc._freeze_rate_last_14d("/nonexistent/x.jsonl") is None


def test_11_rate_dedup_same_as_population() -> None:
    now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    p = _tmp_jsonl([_row("A", "12.10.2026"), _row("A", "12.10.2026")])
    zeilen, tage = hc._freeze_rate_last_14d(p, now=now)
    assert zeilen == 1, f"Dublette in Rate nicht dedupliziert: zeilen={zeilen}"
    assert tage == 1


# ── 3. KI-Abdeckung letzter Report-Tag ───────────────────────────────────────

def _bt_entry(ticker, date, ki_signal_ts="__OMIT__"):
    e = {"ticker": ticker, "date": date}
    if ki_signal_ts != "__OMIT__":
        e["ki_signal_ts"] = ki_signal_ts
    return e


def test_12_ki_coverage_full() -> None:
    data = [_bt_entry(t, "09.10.2026", "2026-10-09T12:00:00Z") for t in "ABCDEFGHIJ"]
    p = _tmp_json(data)
    assert hc._freeze_ki_coverage_last_report_day(p) == "10/10"


def test_13_ki_coverage_partial() -> None:
    data = ([_bt_entry(t, "09.10.2026", "2026-10-09T12:00:00Z") for t in "ABCDEFG"]
            + [_bt_entry(t, "09.10.2026", None) for t in "HIJ"])
    p = _tmp_json(data)
    assert hc._freeze_ki_coverage_last_report_day(p) == "7/10"


def test_14_ki_coverage_zero_but_key_present() -> None:
    # Schlüssel ist bei jedem Eintrag vorhanden (Fresh-KI-Fetch fehlgeschlagen),
    # aber überall None → echte 0/10-Coverage, KEIN "n/a".
    data = [_bt_entry(t, "09.10.2026", None) for t in "ABCDEFGHIJ"]
    p = _tmp_json(data)
    assert hc._freeze_ki_coverage_last_report_day(p) == "0/10"


def test_15_ki_coverage_key_absent_is_na() -> None:
    # Vor PR #587: der Schlüssel existiert bei KEINEM Eintrag des Tages.
    data = [_bt_entry(t, "09.10.2026") for t in "ABCDEFGHIJ"]
    p = _tmp_json(data)
    assert hc._freeze_ki_coverage_last_report_day(p) == "n/a"


def test_16_ki_coverage_missing_file_na() -> None:
    assert hc._freeze_ki_coverage_last_report_day("/nonexistent/x.json") == "n/a"


def test_17_ki_coverage_empty_list_na() -> None:
    p = _tmp_json([])
    assert hc._freeze_ki_coverage_last_report_day(p) == "n/a"


def test_18_ki_coverage_uses_last_date_only() -> None:
    # Nur der jüngste Tag zählt — ältere Tage (auch mit Schlüssel) ignoriert.
    data = ([_bt_entry("OLD", "01.10.2026", "2026-10-01T12:00:00Z")]
            + [_bt_entry(t, "09.10.2026") for t in "AB"])  # jüngster Tag ohne Schlüssel
    p = _tmp_json(data)
    assert hc._freeze_ki_coverage_last_report_day(p) == "n/a", \
        "jüngster Tag ohne Schlüssel muss n/a liefern, nicht den älteren Tag nutzen"


# ── 4. Fail-soft + Verdrahtung ───────────────────────────────────────────────

def test_19_freeze_counter_line_never_raises() -> None:
    for ep in ["/nonexistent/x.jsonl", _tmp_jsonl([]), _tmp_jsonl(["{bad"])]:
        for bp in ["/nonexistent/x.json", _tmp_json([]), _tmp_json({"not": "a list"})]:
            line = hc.freeze_counter_line(ep, bp)
            assert isinstance(line, str) and line, f"leere/None-Zeile: {line!r}"
            assert "🧪 Freeze-Zähler" in line


def test_20_freeze_counter_line_example_output() -> None:
    now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    ep = _tmp_jsonl([
        _row("A", "12.10.2026"), _row("B", "13.10.2026"),
        _row("C", "01.09.2026"),  # vor Freeze, fällt raus
    ])
    bp = _tmp_json([_bt_entry(t, "24.10.2026", "2026-10-24T12:00:00Z") for t in "ABCDE"])
    line = hc.freeze_counter_line(ep, bp, now=now)
    assert "n = 2/250" in line
    assert "2 Zeilen/2 Handelstage (28T)" in line
    assert "5/5" in line


def test_21_digest_body_includes_freeze_line_all_classes() -> None:
    MARK = "🧪 Freeze-Zähler: Setup/Conviction n = 0/250 · Rate 0 Zeilen/0 Handelstage (28T) · KI-Abdeckung (letzter Report-Tag) n/a"
    body_ok, _, _, _ = hc.format_digest_body(
        [], [], n_runs=3, last_run_iso="x", digest_date="2026-10-11",
        freeze_line=MARK)
    assert MARK in body_ok, "OK-Klasse ohne Freeze-Zähler-Zeile"
    crit = [{"id": "S3", "severity": "crit", "detail": "x", "count": 1}]
    body_dg, _, _, _ = hc.format_digest_body(
        crit, [], n_runs=3, last_run_iso="x", digest_date="2026-10-11",
        freeze_line=MARK)
    assert MARK in body_dg, "Digest-Klasse ohne Freeze-Zähler-Zeile"
    body_nd, _, _, _ = hc.format_digest_body(
        [], [], n_runs=0, last_run_iso=None, digest_date="2026-10-11",
        freeze_line=MARK)
    assert MARK in body_nd, "ohne-Daten-Klasse ohne Freeze-Zähler-Zeile"


def test_22_digest_body_omits_when_none() -> None:
    body, _, _, _ = hc.format_digest_body(
        [], [], n_runs=3, last_run_iso="x", digest_date="2026-10-11")
    assert "Freeze-Zähler" not in body, "Freeze-Zähler-Zeile trotz None aufgetaucht"


# ── 5. Vorher/Nachher-Beleg für den §4-Zähler ───────────────────────────────

def test_23_sect4_counter_unchanged_after_shared_helper_refactor() -> None:
    """Belegt, dass der §4-Zähler nach dem Umzug auf den gemeinsamen
    _read_matured_export_rows-Helper exakt denselben Wert liefert wie vorher
    (Exzellenz-Punkt 1: Vorher/Nachher-Vergleich). Fixture mit denselben
    Fällen wie scripts/mock_test_retest_counter.py Test 01."""
    rows = [
        json.dumps({"ticker": "A", "provenance": "forward",  "score": 80.0, "date": "21.07.2026"}),
        json.dumps({"ticker": "B", "provenance": "forward",  "score": 70,   "date": "21.07.2026"}),
        json.dumps({"ticker": "C", "provenance": "forward",  "score": 69.9, "date": "21.07.2026"}),
        json.dumps({"ticker": "D", "provenance": "forward",  "score": None, "date": "21.07.2026"}),
        json.dumps({"ticker": "E", "provenance": "forward",                 "date": "21.07.2026"}),
        json.dumps({"ticker": "F", "provenance": "forward",  "score": True, "date": "21.07.2026"}),
        json.dumps({"ticker": "G", "provenance": "backfill", "score": 90,   "date": "01.06.2026"}),
        json.dumps({"ticker": "H", "provenance": "backfill", "score": 60,   "date": "01.06.2026"}),
        "",
        "{ this is not valid json",
    ]
    p = _tmp_jsonl(rows)
    n, total = hc._count_matured_retest(p)
    assert n == 2, f"§4-Zähler-Wert hat sich durch den Refactor verändert: n={n} (erwartet 2)"
    assert total == 9, f"§4-total hat sich verändert: total={total} (erwartet 9)"


def main() -> int:
    tests = [
        ("01 Eintrittsdatum == Freeze-Datum NICHT gezählt", test_01_entry_date_equal_freeze_not_counted),
        ("02 Eintrittsdatum > Freeze-Datum gezählt",        test_02_entry_date_after_freeze_counted),
        ("03 fehlende Returns nicht gezählt",                test_03_missing_returns_not_counted),
        ("04 backfill nie gezählt",                          test_04_backfill_never_counted),
        ("05 Dubletten (ticker,date) zählen einmal",         test_05_duplicates_ticker_date_count_once),
        ("06 alle Scores gezählt (kein >=70-Filter)",        test_06_all_scores_counted_no_ge70_filter),
        ("07 Datei fehlt -> None",                           test_07_missing_file_none),
        ("08 leere Datei -> (0,0)",                          test_08_empty_file_zero),
        ("09 Rate: nur Fenster letzte 28 Kalendertage",      test_09_rate_counts_only_within_window),
        ("09b Rate: 28T-Fix faengt, was 14T verpasst hätte", test_09b_rate_28d_window_catches_entries_14d_window_missed),
        ("10 Rate: Datei fehlt -> None",                     test_10_rate_missing_file_none),
        ("11 Rate: Dedup wie Population",                    test_11_rate_dedup_same_as_population),
        ("12 KI-Abdeckung 10/10",                            test_12_ki_coverage_full),
        ("13 KI-Abdeckung 7/10",                             test_13_ki_coverage_partial),
        ("14 KI-Abdeckung 0/10 (Schlüssel da, alle None)",   test_14_ki_coverage_zero_but_key_present),
        ("15 KI-Abdeckung n/a (Schlüssel fehlt komplett)",   test_15_ki_coverage_key_absent_is_na),
        ("16 KI-Abdeckung: Datei fehlt -> n/a",              test_16_ki_coverage_missing_file_na),
        ("17 KI-Abdeckung: leere Liste -> n/a",              test_17_ki_coverage_empty_list_na),
        ("18 KI-Abdeckung: nur jüngster Tag zählt",          test_18_ki_coverage_uses_last_date_only),
        ("19 freeze_counter_line nie Exception/leer",        test_19_freeze_counter_line_never_raises),
        ("20 freeze_counter_line Beispielausgabe",           test_20_freeze_counter_line_example_output),
        ("21 Digest-Body: Zeile in allen 3 Klassen",         test_21_digest_body_includes_freeze_line_all_classes),
        ("22 Digest-Body: weggelassen bei None",             test_22_digest_body_omits_when_none),
        ("23 §4-Zähler unverändert nach Refactor",           test_23_sect4_counter_unchanged_after_shared_helper_refactor),
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
