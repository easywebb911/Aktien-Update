"""Mock-Tests für den Status-Drift-Wecker (Teil 2).

Der Wecker erinnert im TÄGLICHEN Daily-Run an fällige Score-Validierungs-
Re-Tests (config.SCORE_STATUS_LABELS.review_by). Reine ntfy-Erinnerung —
ändert NICHTS. Gedrosselt deterministisch via Wochentag-+postclose-Gate.

Tests (kein Netzwerk — send_fn injiziert / gate rein):
  1. find_due_reviews: nur review_by in der Vergangenheit ist fällig.
  2. find_due_reviews: review_by=None (falsif./datengetrieben) wird übersprungen.
  3. find_due_reviews: ungültiges Datum → übersprungen (fail-soft).
  4. gate_open: nur am WECKER-Wochentag UND im postclose-Lauf.
  5. run(): gate offen + fälliges review_by → Push feuert (BELEG, EXZELLENZ 1c).
  6. run(): gate geschlossen (falscher Tag/Phase) → 0 Pushes.
  7. run(): ENABLED=False → 0 Pushes.
  8. Live-Pfad: generate_report.main() ruft status_review_reminder.run.
  9. config: Wecker-Konstanten vorhanden; Weekday im gültigen Bereich.
"""
from __future__ import annotations

import datetime as dt
import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import status_review_reminder as srr  # noqa: E402
import config  # noqa: E402

GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _first_weekday_on_or_after(base: dt.datetime, weekday: int) -> dt.datetime:
    d = base
    while d.weekday() != weekday:
        d += dt.timedelta(days=1)
    return d


_LABELS = {
    "past":   {"status": "unvalidiert", "status_date": "2026-01-01",
               "review_by": "2026-01-01"},
    "future": {"status": "unvalidiert", "status_date": "2026-01-01",
               "review_by": "2999-01-01"},
    "nulled": {"status": "falsifiziert", "status_date": "2026-01-01",
               "review_by": None, "review_cond": "kein Re-Test"},
    "bad":    {"status": "x", "status_date": "2026-01-01",
               "review_by": "nicht-ein-datum"},
}
_NOW = dt.datetime(2026, 7, 15, 21, 30)   # nach 'past', vor 'future'


def test_01_due_only_past() -> None:
    due = srr.find_due_reviews(_LABELS, _NOW)
    scores = {d["score"] for d in due}
    assert scores == {"past"}, f"nur 'past' fällig, got {scores}"


def test_02_none_review_by_skipped() -> None:
    due = srr.find_due_reviews(_LABELS, _NOW)
    assert "nulled" not in {d["score"] for d in due}, \
        "review_by=None darf NICHT fällig werden"


def test_03_bad_date_skipped() -> None:
    due = srr.find_due_reviews(_LABELS, _NOW)
    assert "bad" not in {d["score"] for d in due}, \
        "ungültiges review_by muss fail-soft übersprungen werden"


def test_04_gate_only_weekday_postclose() -> None:
    wd = config.STATUS_REVIEW_WECKER_WEEKDAY
    monday = _first_weekday_on_or_after(dt.datetime(2026, 7, 1), wd)
    other  = monday + dt.timedelta(days=1)
    assert srr.gate_open(monday, "postclose") is True
    assert srr.gate_open(monday, "premarket") is False, "premarket → zu"
    assert srr.gate_open(other, "postclose") is False, "falscher Wochentag → zu"


def test_05_run_fires_on_due(monkeypatch=None) -> None:
    # BELEG (EXZELLENZ 1c): ein review_by in der Vergangenheit → Push feuert.
    wd = config.STATUS_REVIEW_WECKER_WEEKDAY
    monday = _first_weekday_on_or_after(dt.datetime(2026, 7, 1), wd).replace(hour=21)
    captured = []
    srr.SCORE_STATUS_LABELS = _LABELS          # kontrollierte Liste
    try:
        n = srr.run(monday, "postclose",
                    send_fn=lambda item: captured.append(item["score"]) or True)
    finally:
        importlib.reload(srr)                   # echten Zustand wiederherstellen
        sys.path.insert(0, str(ROOT))
    assert n == 1, f"genau 1 Push erwartet (past), got {n}"
    assert captured == ["past"], captured


def test_06_run_gate_closed_no_push() -> None:
    wd = config.STATUS_REVIEW_WECKER_WEEKDAY
    monday = _first_weekday_on_or_after(dt.datetime(2026, 7, 1), wd).replace(hour=21)
    captured = []
    srr.SCORE_STATUS_LABELS = _LABELS
    try:
        n_pre = srr.run(monday, "premarket",
                        send_fn=lambda i: captured.append(i) or True)
        other = monday + dt.timedelta(days=1)
        n_day = srr.run(other, "postclose",
                        send_fn=lambda i: captured.append(i) or True)
    finally:
        importlib.reload(srr)
        sys.path.insert(0, str(ROOT))
    assert n_pre == 0 and n_day == 0 and captured == [], \
        "gate geschlossen darf nicht pushen"


def test_07_disabled_no_push() -> None:
    wd = config.STATUS_REVIEW_WECKER_WEEKDAY
    monday = _first_weekday_on_or_after(dt.datetime(2026, 7, 1), wd).replace(hour=21)
    srr.STATUS_REVIEW_WECKER_ENABLED = False
    srr.SCORE_STATUS_LABELS = _LABELS
    try:
        n = srr.run(monday, "postclose", send_fn=lambda i: True)
    finally:
        importlib.reload(srr)
        sys.path.insert(0, str(ROOT))
    assert n == 0, "ENABLED=False → kein Push"


def test_08_wired_into_daily_run() -> None:
    # EXZELLENZ 6: der Prüfpfad liegt in einem TÄGLICH laufenden Codepfad.
    assert "import status_review_reminder" in GR_SRC, \
        "Daily-Run importiert den Wecker nicht"
    assert "status_review_reminder.run(" in GR_SRC, \
        "Daily-Run ruft status_review_reminder.run nicht auf"


def test_09_config_constants() -> None:
    assert isinstance(config.STATUS_REVIEW_WECKER_ENABLED, bool)
    assert 0 <= config.STATUS_REVIEW_WECKER_WEEKDAY <= 6
    assert config.STATUS_REVIEW_WECKER_TITLE
    assert config.STATUS_REVIEW_WECKER_PRIORITY in (
        "min", "low", "default", "high", "urgent")


def main() -> None:
    tests = [
        ("01 find_due nur Vergangenheit",     test_01_due_only_past),
        ("02 review_by=None übersprungen",     test_02_none_review_by_skipped),
        ("03 bad-Datum fail-soft",             test_03_bad_date_skipped),
        ("04 gate nur Wochentag+postclose",    test_04_gate_only_weekday_postclose),
        ("05 run feuert bei fälligem Review",  test_05_run_fires_on_due),
        ("06 gate zu → kein Push",             test_06_run_gate_closed_no_push),
        ("07 ENABLED=False → kein Push",       test_07_disabled_no_push),
        ("08 im Daily-Run verdrahtet",         test_08_wired_into_daily_run),
        ("09 config-Konstanten gültig",        test_09_config_constants),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERR  {name}: {type(e).__name__}: {e}")
    print(f"\nTotal: {len(tests)} | Failed: {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
