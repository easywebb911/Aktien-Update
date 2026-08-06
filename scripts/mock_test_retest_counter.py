"""Mock-Tests für den §4-Re-Test-Zähler im Health-Check-Digest (06.08.2026).

Deckt ab:
  1  §4-MENGE EXAKT: n = provenance=='forward' UND score>=70 — weder forward
     allein, noch score>=70 allein. Boundary score==70 zählt.
  2  FAIL-SOFT: Datei fehlt → None/„nicht ermittelbar"; leer → (0,0);
     unparsebare Zeile → in total, nicht in n; score None/fehlend/bool → nicht in n.
  3  retest_counter_line-Format (verfügbar + nicht ermittelbar).
  4  Verdrahtung: format_digest_body hängt die Zeile in allen 3 Klassen an,
     wenn übergeben; lässt sie weg, wenn None (backward-compat).

REIN LESEND, kein Netzwerk, deterministisch (Kategorie A).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402


def _tmp(lines: list[str]) -> str:
    d = tempfile.mkdtemp()
    p = os.path.join(d, "matured_backtest_export.jsonl")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))
    return p


_FIXTURE = [
    json.dumps({"ticker": "A", "provenance": "forward",  "score": 80.0, "date": "21.07.2026"}),
    json.dumps({"ticker": "B", "provenance": "forward",  "score": 70,   "date": "21.07.2026"}),  # boundary ==70 → zählt
    json.dumps({"ticker": "C", "provenance": "forward",  "score": 69.9, "date": "21.07.2026"}),  # <70 → nicht
    json.dumps({"ticker": "D", "provenance": "forward",  "score": None, "date": "21.07.2026"}),  # None → nicht
    json.dumps({"ticker": "E", "provenance": "forward",                 "date": "21.07.2026"}),  # score fehlt → nicht
    json.dumps({"ticker": "F", "provenance": "forward",  "score": True, "date": "21.07.2026"}),  # bool → nicht
    json.dumps({"ticker": "G", "provenance": "backfill", "score": 90,   "date": "01.06.2026"}),  # backfill → nicht
    json.dumps({"ticker": "H", "provenance": "backfill", "score": 60,   "date": "01.06.2026"}),  # backfill → nicht
    "",                        # Leerzeile → übersprungen, zählt nicht
    "{ this is not valid json",  # unparsebar → in total, nicht in n
]


def test_01_counts_exactly_sect4_set() -> None:
    p = _tmp(_FIXTURE)
    res = hc._count_matured_retest(p)
    assert res is not None, "lesbare Datei darf nicht None liefern"
    n, total = res
    # n = nur A(80) + B(70) — forward UND score>=70
    assert n == 2, f"§4-Menge falsch: n={n} (erwartet 2 — A,B)"
    # total = 9 nicht-leere Zeilen (8 Records + 1 unparsebar; Leerzeile raus)
    assert total == 9, f"total falsch: {total} (erwartet 9 nicht-leere Zeilen)"


def test_02_neither_condition_alone() -> None:
    # forward allein (score<70) zählt nicht; score>=70 allein (backfill) zählt nicht
    p = _tmp([
        json.dumps({"ticker": "X", "provenance": "forward",  "score": 50}),
        json.dumps({"ticker": "Y", "provenance": "backfill", "score": 99}),
    ])
    n, total = hc._count_matured_retest(p)
    assert n == 0, f"weder-Bedingung-allein verletzt: n={n} (erwartet 0)"
    assert total == 2


def test_03_missing_file_none() -> None:
    assert hc._count_matured_retest("/nonexistent/does_not_exist.jsonl") is None


def test_04_empty_file_zero() -> None:
    p = _tmp([])
    assert hc._count_matured_retest(p) == (0, 0), "leere Datei → (0,0), nicht None"


def test_05_line_format_available() -> None:
    p = _tmp(_FIXTURE)
    line = hc.retest_counter_line(p)
    assert "n = 2/250" in line, f"Zähler-Format falsch: {line!r}"
    assert "Export 9 Zeilen" in line, f"Zeilen-Format falsch: {line!r}"


def test_06_line_format_not_available() -> None:
    line = hc.retest_counter_line("/nonexistent/x.jsonl")
    assert "nicht ermittelbar" in line, f"Fail-soft-Format falsch: {line!r}"


def test_07_line_never_raises() -> None:
    # niemals Exception, niemals leer — auch bei kaputtem Pfad-Typ
    for bad in ["/nonexistent/x.jsonl", _tmp([]), _tmp(["{bad"])]:
        line = hc.retest_counter_line(bad)
        assert isinstance(line, str) and line, f"leere/None-Zeile: {line!r}"


def test_08_digest_body_includes_line_all_classes() -> None:
    MARK = "📊 Re-Test-Zähler (§4): n = 2/250 · Export 9 Zeilen"
    # OK-Klasse (keine Fails)
    body_ok, _, _, _ = hc.format_digest_body(
        [], [], n_runs=3, last_run_iso="x", digest_date="2026-08-06",
        retest_line=MARK)
    assert MARK in body_ok, "OK-Klasse ohne Zähler-Zeile"
    # Digest-Klasse (1 crit)
    crit = [{"id": "S3", "severity": "crit", "detail": "x", "count": 1}]
    body_dg, _, _, _ = hc.format_digest_body(
        crit, [], n_runs=3, last_run_iso="x", digest_date="2026-08-06",
        retest_line=MARK)
    assert MARK in body_dg, "Digest-Klasse ohne Zähler-Zeile"
    # ohne-Daten-Klasse (n_runs=0)
    body_nd, _, _, _ = hc.format_digest_body(
        [], [], n_runs=0, last_run_iso=None, digest_date="2026-08-06",
        retest_line=MARK)
    assert MARK in body_nd, "ohne-Daten-Klasse ohne Zähler-Zeile"


def test_09_digest_body_omits_when_none() -> None:
    # backward-compat: ohne retest_line (Default None) keine Zähler-Zeile
    body, _, _, _ = hc.format_digest_body(
        [], [], n_runs=3, last_run_iso="x", digest_date="2026-08-06")
    assert "Re-Test-Zähler" not in body, "Zähler-Zeile trotz None aufgetaucht"


def main() -> int:
    tests = [
        ("01 §4-Menge exakt (forward ∧ score≥70)", test_01_counts_exactly_sect4_set),
        ("02 weder Bedingung allein",             test_02_neither_condition_alone),
        ("03 Datei fehlt → None",                 test_03_missing_file_none),
        ("04 leere Datei → (0,0)",                test_04_empty_file_zero),
        ("05 Zeilen-Format (verfügbar)",          test_05_line_format_available),
        ("06 Zeilen-Format (nicht ermittelbar)",  test_06_line_format_not_available),
        ("07 Zeile nie Exception/leer",           test_07_line_never_raises),
        ("08 Digest-Body: Zeile in allen 3 Klassen", test_08_digest_body_includes_line_all_classes),
        ("09 Digest-Body: weggelassen bei None",  test_09_digest_body_omits_when_none),
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
