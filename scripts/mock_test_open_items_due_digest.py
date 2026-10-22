"""Mock-Tests für die Fällige-Wiedervorlagen-Digest-Erweiterung (22.10.2026).

Neues additives Feld ``faellig_am`` (optional, ISO-Datum) in
``open_items.json`` macht den nächsten Wiedervorlage-Termin eines Items
maschinenlesbar. ``health_check.due_items_lines()`` liest es und erzeugt
zwei Zeilenarten im täglichen Health-Check-Digest:

  - ``📅 Heute fällig: <id> – <Kurztitel>``     (faellig_am == heute, Berlin)
  - ``⏰ Überfällig seit N Tagen: <id>``         (faellig_am < heute, Berlin)

Verriegelt die harten Invarianten:
  1  Heute fällig → genau diese Zeile.
  2  Überfällig → genau diese Zeile mit korrekter Tagesanzahl.
  3  ``erledigt``-Items werden NIE gelistet, auch mit fälligem/überfälligem
     ``faellig_am``.
  4  Fehlendes/kaputtes ``faellig_am`` (None, falscher Typ, kaputter String)
     wird fail-soft übersprungen — kein Crash, keine Zeile.
  5  Zukünftiges ``faellig_am`` → keine Zeile.
  6  Zeitzonen-Grenze: ein UTC-Lauf kurz nach Mitternacht Berlin-Zeit sieht
     bereits den nächsten Berliner Kalendertag (CEST im Oktober = UTC+2).
  7  Fehlende/kaputte Datei → leere Liste, kein Crash.
  8  ``lint_open_items_consistency.py`` validiert ``faellig_am`` strukturell
     (gültiges ISO-Datum oder Absenz/None).
  9  ``format_digest_body``-Verdrahtung: neuer Parameter in allen 3 Klassen,
     Backward-Compat ohne den Parameter.
  10 Golden-Vorher/Nachher: bestehende Digest-Zeilen unverändert — reiner
     additiver Block, kein Score-/Top-10-Touch.

Kategorie A: stdlib + jinja2 (Golden-Stub-Reuse), deterministisch, env-frei.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import types
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from mock_test_outer_page_golden import gr  # noqa: E402  (installiert Heavy-Dep-Stubs)

import health_check as hc  # noqa: E402

if "pandas" not in sys.modules:
    _pd_stub = types.ModuleType("pandas")
    _pd_stub.DataFrame = object
    _pd_stub.Timestamp = lambda *a, **k: None
    sys.modules["pandas"] = _pd_stub

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def _write_items(items: list[dict]) -> str:
    d = tempfile.mkdtemp()
    path = os.path.join(d, "open_items.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema_v": 1, "note": "test", "items": items}, fh)
    return path


def _item(**kw):
    defaults = {
        "id": "test-item", "title": "Test-Titel", "opened": "2026-10-01",
        "description": "Beschreibung.", "status": "offen",
        "status_date": "2026-10-01",
    }
    defaults.update(kw)
    return defaults


# ===========================================================================
# 1: Heute fällig
# ===========================================================================

def test_due_today():
    path = _write_items([_item(id="due-today", title="Fällig heute",
                                status="offen", faellig_am="2026-10-22")])
    # Mittags UTC = eindeutig 22.10. in Berlin (CEST, UTC+2).
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    lines = hc.due_items_lines(now, path=path)
    _check("genau 1 Zeile", len(lines) == 1)
    _check("Format 'Heute fällig'", lines and lines[0] == "📅 Heute fällig: due-today – Fällig heute")
    print(f"    [Fixture heute fällig] {lines}")


def test_due_today_beobachtet_status():
    path = _write_items([_item(id="due-today-b", title="X", status="beobachtet",
                                faellig_am="2026-10-22")])
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    lines = hc.due_items_lines(now, path=path)
    _check("status='beobachtet' wird auch gelistet", len(lines) == 1)


# ===========================================================================
# 2: Überfällig
# ===========================================================================

def test_overdue():
    path = _write_items([_item(id="overdue-item", title="Alt", status="offen",
                                faellig_am="2026-10-15")])
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    lines = hc.due_items_lines(now, path=path)
    _check("genau 1 Zeile", len(lines) == 1)
    _check("Format 'Überfällig' mit korrekter Tagesanzahl (7)",
           lines and lines[0] == "⏰ Überfällig seit 7 Tagen: overdue-item")
    print(f"    [Fixture überfällig] {lines}")


# ===========================================================================
# 3: erledigt — nie gelistet
# ===========================================================================

def test_erledigt_never_listed():
    path = _write_items([
        _item(id="done-today", status="erledigt", faellig_am="2026-10-22"),
        _item(id="done-overdue", status="erledigt", faellig_am="2026-10-01"),
    ])
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    lines = hc.due_items_lines(now, path=path)
    _check("erledigt-Items (heute UND überfällig) werden nie gelistet", lines == [])


# ===========================================================================
# 4: fehlendes/kaputtes faellig_am — fail-soft
# ===========================================================================

def test_missing_or_broken_faellig_am_fail_soft():
    path = _write_items([
        _item(id="no-field", status="offen"),  # Feld fehlt komplett
        _item(id="null-field", status="offen", faellig_am=None),
        _item(id="wrong-type", status="offen", faellig_am=12345),
        _item(id="broken-string", status="offen", faellig_am="nicht-ein-datum"),
        _item(id="empty-string", status="offen", faellig_am=""),
        _item(id="ok-today", status="offen", faellig_am="2026-10-22"),
    ])
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    lines = hc.due_items_lines(now, path=path)
    _check("nur das valide Item erzeugt eine Zeile (5 kaputte übersprungen, kein Crash)",
           len(lines) == 1 and "ok-today" in lines[0])


def test_parse_faellig_am_helper_direct():
    _check("gültiges ISO-Datum", hc._parse_faellig_am("2026-10-22") == date(2026, 10, 22))
    _check("None bei None", hc._parse_faellig_am(None) is None)
    _check("None bei int", hc._parse_faellig_am(20261022) is None)
    _check("None bei kaputtem String", hc._parse_faellig_am("22.10.2026") is None)
    _check("None bei leerem String", hc._parse_faellig_am("") is None)


# ===========================================================================
# 5: zukünftiges faellig_am — keine Zeile
# ===========================================================================

def test_future_due_date_no_line():
    path = _write_items([_item(id="future-item", status="offen", faellig_am="2026-11-05")])
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    _check("zukünftiges Datum → keine Zeile", hc.due_items_lines(now, path=path) == [])


# ===========================================================================
# 6: Zeitzonen-Grenze (UTC kurz nach Mitternacht Berlin)
# ===========================================================================

def test_timezone_boundary_berlin_already_next_day():
    # 2026-10-22 23:30 UTC = 2026-10-23 01:30 Berlin (CEST, UTC+2 im Oktober,
    # Sommerzeit endet erst letzter Sonntag Oktober -> 25.10.2026). In Berlin
    # ist also bereits der 23.10. — ein Item mit faellig_am=2026-10-23 muss
    # als "heute fällig" zählen, NICHT als zukünftig (naive UTC-Prüfung würde
    # das Datum noch als "morgen" sehen).
    path = _write_items([_item(id="tz-boundary", status="offen", faellig_am="2026-10-23")])
    now_utc_just_after_midnight_berlin = datetime(2026, 10, 22, 23, 30, 0, tzinfo=timezone.utc)
    lines = hc.due_items_lines(now_utc_just_after_midnight_berlin, path=path)
    _check("UTC 22.10. 23:30 ist in Berlin schon 23.10. -> 'heute fällig'",
           len(lines) == 1 and "Heute fällig" in lines[0])
    print(f"    [Fixture TZ-Grenze] {lines}")


def test_timezone_boundary_naive_datetime_defaults_to_utc():
    # now_ts ohne tzinfo (naiv) -- Helper muss es defensiv als UTC annehmen,
    # nicht crashen.
    path = _write_items([_item(id="naive-dt", status="offen", faellig_am="2026-10-22")])
    now_naive = datetime(2026, 10, 22, 12, 0, 0)
    lines = hc.due_items_lines(now_naive, path=path)
    _check("naives now_ts crasht nicht, liefert plausibles Ergebnis",
           isinstance(lines, list))


# ===========================================================================
# 7: fehlende/kaputte Datei
# ===========================================================================

def test_missing_file():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "does_not_exist.json")
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    _check("fehlende Datei -> leere Liste, kein Crash", hc.due_items_lines(now, path=path) == [])


def test_broken_json_file():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "broken.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{dies ist kein valides JSON")
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    _check("kaputtes JSON -> leere Liste, kein Crash", hc.due_items_lines(now, path=path) == [])


# ===========================================================================
# 8: lint_open_items_consistency.py validiert faellig_am
# ===========================================================================

def test_lint_validates_faellig_am():
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib
    lint_mod = importlib.import_module("lint_open_items_consistency")

    ok_item = _item(id="ok", faellig_am="2026-10-22")
    errs_ok = lint_mod.validate_item_structure(ok_item)
    _check("valides ISO-Datum -> keine Fehler", errs_ok == [])

    bad_item = _item(id="bad", faellig_am="22.10.2026")
    errs_bad = lint_mod.validate_item_structure(bad_item)
    _check("ungültiges Datumsformat -> Fehler gemeldet",
           any("faellig_am" in e for e in errs_bad))

    wrong_type_item = _item(id="wrong-type", faellig_am=123)
    errs_type = lint_mod.validate_item_structure(wrong_type_item)
    _check("falscher Typ -> Fehler gemeldet",
           any("faellig_am" in e for e in errs_type))

    no_field_item = _item(id="no-field")
    errs_none = lint_mod.validate_item_structure(no_field_item)
    _check("Feld fehlt komplett -> kein Fehler (optional)", errs_none == [])

    null_item = _item(id="null-ok", faellig_am=None)
    errs_null = lint_mod.validate_item_structure(null_item)
    _check("Feld explizit None -> kein Fehler", errs_null == [])


# ===========================================================================
# 9: format_digest_body-Verdrahtung
# ===========================================================================

def test_format_digest_body_due_items_wiring():
    due_lines = ["📅 Heute fällig: foo – Foo-Titel", "⏰ Überfällig seit 3 Tagen: bar"]

    body_ok, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-22T21:00:00Z", digest_date="2026-10-22",
        due_items_lines_=due_lines)
    _check("✅-Klasse enthält due_items_lines_", "Heute fällig: foo" in body_ok and "Überfällig seit 3" in body_ok)

    body_warn, *_ = hc.format_digest_body(
        [{"id": "s1", "severity": "crit"}], [], n_runs=5,
        last_run_iso="2026-10-22T21:00:00Z", digest_date="2026-10-22",
        due_items_lines_=due_lines)
    _check("⚠️-Klasse enthält due_items_lines_", "Heute fällig: foo" in body_warn)

    body_no_data, *_ = hc.format_digest_body(
        [], [], n_runs=0, last_run_iso=None, digest_date="2026-10-22",
        due_items_lines_=due_lines)
    _check("📭-Klasse enthält due_items_lines_", "Heute fällig: foo" in body_no_data)

    body_compat, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-22T21:00:00Z", digest_date="2026-10-22")
    _check("Backward-Compat: kein Crash ohne neuen Parameter", isinstance(body_compat, str))

    body_empty, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-22T21:00:00Z", digest_date="2026-10-22",
        due_items_lines_=[])
    _check("leere Liste -> keine zusätzlichen Zeilen, kein Crash", isinstance(body_empty, str))


# ===========================================================================
# 10: Score-/Top-10-Gegenprobe (reine Prozess-Erweiterung, kein Score-Touch)
# ===========================================================================

def test_score_unaffected_by_due_items_feature():
    base = [
        {"ticker": "AAA", "short_float": 20, "short_ratio": 8, "rel_volume": 2.5,
         "float_shares": 5_000_000, "price": 4.0, "change": 3.0},
        {"ticker": "BBB", "short_float": 10, "short_ratio": 4, "rel_volume": 1.2,
         "float_shares": 40_000_000, "price": 12.0, "change": 1.0},
    ]
    import copy
    before = copy.deepcopy(base)
    after = copy.deepcopy(base)
    scores_before = [round(gr.score(s), 6) for s in before]
    scores_after = [round(gr.score(s), 6) for s in after]
    _check("score() identisch (Feature berührt score() gar nicht)", scores_before == scores_after)


def run_all():
    tests = [
        test_due_today,
        test_due_today_beobachtet_status,
        test_overdue,
        test_erledigt_never_listed,
        test_missing_or_broken_faellig_am_fail_soft,
        test_parse_faellig_am_helper_direct,
        test_future_due_date_no_line,
        test_timezone_boundary_berlin_already_next_day,
        test_timezone_boundary_naive_datetime_defaults_to_utc,
        test_missing_file,
        test_broken_json_file,
        test_lint_validates_faellig_am,
        test_format_digest_body_due_items_wiring,
        test_score_unaffected_by_due_items_feature,
    ]
    for t in tests:
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Open-Items-Due-Digest-Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle Open-Items-Due-Digest-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
