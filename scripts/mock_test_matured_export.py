"""Mock-Tests für den append-only Matured-Backtest-Export (04.08.2026).

Deckt die harten Abnahmekriterien ab:
  1  Umfang: gereifte daily-Records exportiert; unmatured/bootstrap raus; KEIN
     score-Filter.
  1b REIFE-GATE #2 (days_old > 14): gereift heißt return_10d gefüllt UND > 14
     Kalendertage alt (sonst evtl. nicht-finale Rolling-Felder max_gain/-drawdown).
     Grenz-Tests bei exakt 14 (raus) vs. 15 (rein) + Reife-Übergang.
  2  IDEMPOTENZ: Doppel-Lauf → Zeilenzahl konstant (der geforderte Test).
  3  APPEND-ONLY: bestehende Zeilen bleiben byte-verbatim, wenn neue dazukommen.
  4  LOOK-AHEAD-SAFE: ein zum Export fehlendes Feld wird NIE nachgetragen; ein
     bereits exportierter Record wird nie überschrieben.
  5  PROVENANCE: erster Lauf „backfill", danach „forward".
  6  FAIL-SOFT: fehlende Datei / korrupte Datei → kein Crash, Export läuft.
  7  DETERMINISMUS: Batch nach (date,ticker) sortiert, Feld-Reihenfolge stabil.
  8  Verdrahtung (source-inspection): Flag, fail-soft-Caller im postclose-Pfad,
     Workflow-git-add, KEIN Frontend-Fetch / nicht im Golden.
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

import matured_export as M  # noqa: E402

GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
GOLDEN = (ROOT / "tests/golden/report_outer_page.html").read_text(encoding="utf-8")
WF = (ROOT / ".github/workflows/daily-squeeze-report.yml").read_text(encoding="utf-8")

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def _tmp():
    d = tempfile.mkdtemp()
    return os.path.join(d, "matured_backtest_export.jsonl")


def _rows(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


# ── 1. Umfang ─────────────────────────────────────────────────────────────────

def test_01_scope_matured_only_no_score_filter() -> None:
    p = _tmp()
    hist = [
        {"ticker": "AAA", "date": "13.07.2026", "return_10d": 5.0, "score": 80},
        {"ticker": "BBB", "date": "13.07.2026", "return_10d": None, "score": 90},   # unmatured
        {"ticker": "BOOT", "date": "01.05.2026", "return_10d": 3.0, "source": "bootstrap"},
        {"ticker": "LOW", "date": "14.07.2026", "return_10d": -2.0, "score": 12},   # score<70
    ]
    n = M.export_matured_records(hist, export_path=p, now=NOW)
    tk = sorted(r["ticker"] for r in _rows(p))
    assert n == 2, f"erwartet 2 exportiert, war {n}"
    assert tk == ["AAA", "LOW"], f"KEIN score-Filter + matured-only verletzt: {tk}"
    assert "BBB" not in tk, "unmatured (return_10d None) darf nicht exportiert werden"
    assert "BOOT" not in tk, "bootstrap darf nicht exportiert werden"


# ── 2. Idempotenz (Doppel-Lauf) ──────────────────────────────────────────────

def test_02_idempotent_double_run() -> None:
    p = _tmp()
    hist = [
        {"ticker": "AAA", "date": "13.07.2026", "return_10d": 5.0},
        {"ticker": "CCC", "date": "15.07.2026", "return_10d": 2.0},
    ]
    n1 = M.export_matured_records(hist, export_path=p, now=NOW)
    lines1 = len(_rows(p))
    n2 = M.export_matured_records(hist, export_path=p, now=NOW)   # exakt gleicher Lauf
    n3 = M.export_matured_records(hist, export_path=p, now=NOW)   # noch mal
    lines3 = len(_rows(p))
    assert n1 == 2 and n2 == 0 and n3 == 0, f"Re-Run schrieb erneut: {n1},{n2},{n3}"
    assert lines1 == lines3 == 2, f"Zeilenzahl nicht konstant: {lines1} vs {lines3}"


def test_02b_idempotent_across_growing_history() -> None:
    # derselbe Record bleibt einmalig, auch wenn die History wächst
    p = _tmp()
    h1 = [{"ticker": "AAA", "date": "13.07.2026", "return_10d": 5.0}]
    M.export_matured_records(h1, export_path=p, now=NOW)
    h2 = h1 + [{"ticker": "DDD", "date": "16.07.2026", "return_10d": 1.0}]
    n = M.export_matured_records(h2, export_path=p, now=NOW)
    assert n == 1, "nur der neue Record darf dazukommen"
    assert sorted(r["ticker"] for r in _rows(p)) == ["AAA", "DDD"]


# ── 3./4. Append-only + Look-ahead ────────────────────────────────────────────

def test_03_existing_lines_byte_verbatim() -> None:
    p = _tmp()
    M.export_matured_records([{"ticker": "AAA", "date": "13.07.2026", "return_10d": 5.0}],
                             export_path=p, now=NOW)
    with open(p, encoding="utf-8") as fh:
        line_before = fh.readlines()[0]
    # zweiter Lauf fügt neuen Record hinzu
    M.export_matured_records(
        [{"ticker": "AAA", "date": "13.07.2026", "return_10d": 5.0},
         {"ticker": "ZZZ", "date": "20.07.2026", "return_10d": 9.0}],
        export_path=p, now=datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc))
    with open(p, encoding="utf-8") as fh:
        line_after = fh.readlines()[0]
    assert line_before == line_after, "bestehende Zeile wurde verändert (nicht append-only)"


def test_04_lookahead_missing_field_never_backfilled() -> None:
    p = _tmp()
    # Export 1: Record OHNE Feld 'entry_past_return_5d'
    M.export_matured_records(
        [{"ticker": "AAA", "date": "13.07.2026", "return_10d": 5.0}],
        export_path=p, now=NOW)
    # Export 2: SELBER Record, jetzt MIT dem Feld → darf die Zeile NICHT ändern
    M.export_matured_records(
        [{"ticker": "AAA", "date": "13.07.2026", "return_10d": 5.0,
          "entry_past_return_5d": -3.3}],
        export_path=p, now=datetime(2026, 8, 6, tzinfo=timezone.utc))
    rows = _rows(p)
    assert len(rows) == 1, "Record wurde dupliziert"
    assert "entry_past_return_5d" not in rows[0], \
        "später aufgetauchtes Feld wurde nachgetragen (LOOK-AHEAD-Verletzung)"


# ── 5. Provenance ─────────────────────────────────────────────────────────────

def test_05_provenance_backfill_then_forward() -> None:
    p = _tmp()
    M.export_matured_records([{"ticker": "AAA", "date": "13.07.2026", "return_10d": 5.0}],
                             export_path=p, now=NOW)
    M.export_matured_records(
        [{"ticker": "AAA", "date": "13.07.2026", "return_10d": 5.0},
         {"ticker": "NEW", "date": "20.07.2026", "return_10d": 1.0}],
        export_path=p, now=datetime(2026, 8, 5, tzinfo=timezone.utc))
    prov = {r["ticker"]: r["provenance"] for r in _rows(p)}
    assert prov["AAA"] == "backfill", "erster Lauf muss backfill sein"
    assert prov["NEW"] == "forward", "späterer Lauf muss forward sein"


# ── 6. Fail-soft ──────────────────────────────────────────────────────────────

def test_06_missing_file_creates() -> None:
    p = _tmp()
    assert not os.path.exists(p)
    n = M.export_matured_records([{"ticker": "AAA", "date": "13.07.2026", "return_10d": 5.0}],
                                 export_path=p, now=NOW)
    assert n == 1 and os.path.exists(p)


def test_06b_corrupt_file_fail_soft() -> None:
    p = _tmp()
    with open(p, "w", encoding="utf-8") as fh:
        fh.write('{"ticker":"OLD","date":"10.07.2026","return_10d":1}\n')
        fh.write("{ this is not valid json\n")   # korrupte Zeile
    # darf nicht crashen; exportiert neuen Record, überspringt Korrupt-Zeile
    n = M.export_matured_records([{"ticker": "AAA", "date": "13.07.2026", "return_10d": 5.0}],
                                 export_path=p, now=NOW)
    tk = sorted(r["ticker"] for r in _rows(p))
    assert "AAA" in tk, "Export lief trotz korrupter Zeile nicht"
    assert "OLD" in tk, "gültige Bestands-Zeile ging verloren"


def test_06c_empty_history_noop() -> None:
    p = _tmp()
    assert M.export_matured_records([], export_path=p, now=NOW) == 0
    assert not os.path.exists(p), "leerer Lauf soll keine Datei anlegen"


# ── 7. Determinismus ──────────────────────────────────────────────────────────

def test_07_batch_sorted_and_stable_fields() -> None:
    p = _tmp()
    hist = [
        {"ticker": "ZZZ", "date": "20.07.2026", "return_10d": 1.0},
        {"ticker": "AAA", "date": "13.07.2026", "return_10d": 1.0},
        {"ticker": "MMM", "date": "13.07.2026", "return_10d": 1.0},
    ]
    M.export_matured_records(hist, export_path=p, now=NOW)
    order = [(r["date"], r["ticker"]) for r in _rows(p)]
    assert order == [("13.07.2026", "AAA"), ("13.07.2026", "MMM"), ("20.07.2026", "ZZZ")], \
        f"Batch nicht nach (date,ticker) sortiert: {order}"
    # Feld-Reihenfolge stabil (sort_keys) → Keys in der Roh-Zeile aufsteigend
    with open(p, encoding="utf-8") as fh:
        raw = fh.readline()
    keys = [k for k in json.loads(raw).keys()]
    assert keys == sorted(keys), f"Feld-Reihenfolge nicht stabil sortiert: {keys}"


# ── 8. Verdrahtung (source-inspection) ───────────────────────────────────────

def test_08_flag_and_failsoft_caller_in_postclose() -> None:
    assert "MATURED_EXPORT_ENABLED" in GR, "Flag-Gate im Caller fehlt"
    assert "matured_export.export_matured_records(" in GR, "Export-Aufruf fehlt"
    # fail-soft: Aufruf steht in try/except mit log.warning
    idx = GR.index("matured_export.export_matured_records(")
    ctx = GR[idx - 400:idx + 400]
    assert "try:" in ctx and "except Exception" in ctx and "fail-soft" in ctx, \
        "Export-Aufruf ist nicht fail-soft gewrappt"
    # nur im postclose-Zweig (nach _append_backtest_entries)
    assert GR.index("_append_backtest_entries(") < idx < GR.index("premarket-Phase"), \
        "Export-Aufruf nicht im postclose-Pfad"


def test_09_no_frontend_consumer_not_in_golden() -> None:
    # KEIN client-seitiger Fetch der Export-Datei
    assert "matured_backtest_export" not in GR or \
        "fetch('./matured_backtest_export" not in GR, "Frontend-Fetch der Export-Datei?"
    assert "fetch('./matured_backtest_export" not in GR
    assert "matured_backtest_export" not in GOLDEN, "Export-Datei im Golden referenziert"


def test_10_workflow_git_add_present() -> None:
    assert "git add matured_backtest_export.jsonl" in WF, \
        "Workflow-git-add für die Export-Datei fehlt (sonst nicht persistiert)"


# ── 1b. Reife-Gate #2: days_old > 14 (Rolling-Felder final) ──────────────────

def test_11_matured_but_young_not_exported() -> None:
    # return_10d gefüllt, aber erst 10 Kalendertage alt → max_gain/max_drawdown
    # evtl. noch rollend → NICHT exportieren (sonst nicht-finaler Peak eingefroren)
    p = _tmp()
    hist = [{"ticker": "YNG", "date": "25.07.2026", "return_10d": 5.0}]   # 10 Tage
    n = M.export_matured_records(hist, export_path=p, now=NOW)
    assert n == 0, "gereifter aber junger Record (<=14 Tage) darf NICHT exportiert werden"
    assert not os.path.exists(p), "kein Export → keine Datei angelegt"


def test_12_boundary_day14_out_day15_in() -> None:
    # exakte Grenze: 14 Tage raus (<=14 → continue), 15 Tage rein (>14)
    p = _tmp()
    hist = [
        {"ticker": "D14", "date": "21.07.2026", "return_10d": 1.0},   # exakt 14 Tage alt
        {"ticker": "D15", "date": "20.07.2026", "return_10d": 1.0},   # exakt 15 Tage alt
    ]
    n = M.export_matured_records(hist, export_path=p, now=NOW)
    tk = sorted(r["ticker"] for r in _rows(p))
    assert tk == ["D15"], f"Grenze verletzt — nur >14 (ab Tag 15) darf rein: {tk}"
    assert n == 1, f"erwartet genau 1 exportiert, war {n}"


def test_13_young_record_matures_and_exports_later() -> None:
    # derselbe Record: heute jung (<=14) → nicht exportiert; später (>14) → genau
    # einmal exportiert. Beweist: die zweite Schranke verzögert nur, verliert kein n.
    p = _tmp()
    rec = {"ticker": "TRN", "date": "25.07.2026", "return_10d": 5.0}
    n_young = M.export_matured_records([rec], export_path=p,
                                       now=datetime(2026, 8, 4, tzinfo=timezone.utc))   # 10 Tage
    n_old = M.export_matured_records([rec], export_path=p,
                                     now=datetime(2026, 8, 10, tzinfo=timezone.utc))    # 16 Tage
    assert n_young == 0, "jung (<=14) → noch nicht exportiert"
    assert n_old == 1, "nach Reife (>14) → genau einmal exportiert"
    assert len(_rows(p)) == 1, "kein Duplikat über den Reife-Übergang"


def test_14_unparsable_date_conservative_skip() -> None:
    # unparsebares Datum → _calendar_days_old None → konservativ übersprungen, kein Crash
    p = _tmp()
    n = M.export_matured_records(
        [{"ticker": "BAD", "date": "not-a-date", "return_10d": 5.0}],
        export_path=p, now=NOW)
    assert n == 0, "unparsebares Datum → konservativ übersprungen"


def main() -> int:
    tests = [
        ("01 Umfang: matured-only, kein score-Filter", test_01_scope_matured_only_no_score_filter),
        ("02 Idempotenz Doppel-Lauf",                  test_02_idempotent_double_run),
        ("02b Idempotenz wachsende History",           test_02b_idempotent_across_growing_history),
        ("03 Append-only: Zeilen byte-verbatim",       test_03_existing_lines_byte_verbatim),
        ("04 Look-ahead: kein Nachtragen",             test_04_lookahead_missing_field_never_backfilled),
        ("05 Provenance backfill→forward",             test_05_provenance_backfill_then_forward),
        ("06 Fail-soft: fehlende Datei",               test_06_missing_file_creates),
        ("06b Fail-soft: korrupte Datei",              test_06b_corrupt_file_fail_soft),
        ("06c Leerer Lauf = no-op",                    test_06c_empty_history_noop),
        ("07 Determinismus: Sort + Feld-Order",        test_07_batch_sorted_and_stable_fields),
        ("08 Flag + fail-soft-Caller postclose",       test_08_flag_and_failsoft_caller_in_postclose),
        ("09 Kein Frontend/Golden-Konsument",          test_09_no_frontend_consumer_not_in_golden),
        ("10 Workflow-git-add vorhanden",              test_10_workflow_git_add_present),
        ("11 Reife-Gate: matured aber jung → raus",    test_11_matured_but_young_not_exported),
        ("12 Grenze: Tag 14 raus, Tag 15 rein",        test_12_boundary_day14_out_day15_in),
        ("13 Reife-Übergang: jung→alt, genau 1×",      test_13_young_record_matures_and_exports_later),
        ("14 Unparsebares Datum → konservativ raus",   test_14_unparsable_date_conservative_skip),
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
