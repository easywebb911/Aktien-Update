"""Mock-Tests für den generischen Daten-Abdeckungs-Wächter (21.10.2026).

Folge-Projekt zum News-Coverage-Watchdog (#593): 6 weitere externe Quellen
hatten laut Inventur (``open_items.json`` "datenquellen-coverage-inventur")
KEINEN persistierten Pro-Lauf-Abdeckungszähler/Digest-Alarm —
``get_options_data``/``get_earnings_date``/``get_earnings_surprise``
(generate_report.py) sowie ``fetch_reddit_mentions``/``fetch_fda_calendar``/
``fetch_openinsider`` (ki_agent.py). EIN generisches Schema
(``coverage_history.jsonl``, Feld ``quelle``) statt 6 Spezialdateien — siehe
SESSION_HANDOVER.md für die Begründung. ``news_coverage_history.jsonl``
bleibt unverändert bestehen (eigenes Schema).

"Abdeckung" = hat der Provider-Call geantwortet (kein echter Fehler) — NICHT
ob das Ergebnis inhaltlich nicht-leer war (ein Ticker ohne Optionsmarkt/
Earnings-Termin/Insider-Käufe ist ein LEGITIMES Nicht-Ergebnis, keine
Störung). Reine Side-Effect-Zähler in den jeweiligen Except-Zweigen — KEINE
Änderung an Rückgabewerten/Verhalten.

Verriegelt die harten Invarianten:
  1  persist_coverage_row: Schema, Idempotenz über (date, run_phase, quelle),
     Flag=False → keine Datei, n_erwartet<=0 → keine Zeile.
  2  coverage_liveness_line: absent/leer/ok (+Fixture).
  3  coverage_warn_line: 0-in-allen-Läufen-im-Fenster → Warnung; mind. 1
     Treffer im Fenster → keine Warnung; nur Läufe außerhalb des Fensters →
     kein Fund (None); n_erwartet==0-Zeilen zählen nicht als "0 erhalten".
  4  coverage_overview_line: "N von M Quellen unter Baseline", nur die
     LETZTE Zeile je Quelle zählt, nie geschriebene Quellen zählen NICHT.
  5  format_digest_body-Verdrahtung: alle 3 Klassen + Backward-Compat.
  6  generate_report.py-Instrumentierung: get_options_data/get_earnings_date/
     get_earnings_surprise — echter Fehler zählt, legitime Leer-Pfade NICHT;
     Rückgabewerte unverändert (Zero-Behavior-Change-Beleg).
  7  ki_agent.py-Instrumentierung: fetch_reddit_mentions/fetch_fda_calendar/
     fetch_openinsider — dieselbe Zero-Behavior-Change-Garantie.
  8  Score-/Top-10-Gegenprobe: score() unverändert mit/ohne Coverage-Daten
     auf dem Stock-Dict (die 6 Quellen beeinflussen ohnehin nur
     _compute_sub_scores — reine Anzeigefunktion, hier zusätzlich zur
     Sicherheit erneut bewiesen).

Kategorie A: stdlib + jinja2 (Golden-Stub-Reuse), deterministisch, env-frei.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import types
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

# Import zieht _install_stubs() (yfinance/requests/bs4/deep_translator/
# watchlist) + `import generate_report as gr` (Modul-Ebene).
from mock_test_outer_page_golden import gr  # noqa: E402

import health_check as hc  # noqa: E402

# ki_agent.py braucht zusätzlich `import pandas as pd` am Modul-Kopf — die
# 3 hier getesteten Funktionen (fetch_reddit_mentions/fetch_fda_calendar/
# fetch_openinsider) nutzen pandas selbst NICHT, ein leerer Stub genügt für
# den Import (analog EXCLUDED-Begründung "pandas-Import" in
# scripts/run_ci_mock_tests.py für andere, echte-DataFrame-Ops-Tests).
if "pandas" not in sys.modules:
    _pd_stub = types.ModuleType("pandas")
    _pd_stub.DataFrame = object
    _pd_stub.Timestamp = lambda *a, **k: None
    sys.modules["pandas"] = _pd_stub

import ki_agent as ka  # noqa: E402

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def _fresh_coverage_file():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "coverage_history.jsonl")
    hc.COVERAGE_LOG_FILE = path
    return path


def _load_lines(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if s:
                out.append(json.loads(s))
    return out


# ===========================================================================
# 1: persist_coverage_row
# ===========================================================================

def test_persist_coverage_row_schema():
    path = _fresh_coverage_file()
    hc.COVERAGE_LOG_ENABLED = True
    n = hc.persist_coverage_row(
        "options_atm", 5, 4, {"TimeoutError": 1},
        report_date_iso="2026-10-21", run_phase="postclose", path=path)
    _check("1 neue Zeile geschrieben", n == 1)
    rows = _load_lines(path)
    _check("genau 1 Zeile", len(rows) == 1)
    row = rows[0]
    _check("date korrekt", row["date"] == "2026-10-21")
    _check("run_phase korrekt", row["run_phase"] == "postclose")
    _check("quelle korrekt", row["quelle"] == "options_atm")
    _check("n_erwartet == 5", row["n_erwartet"] == 5)
    _check("n_erhalten == 4", row["n_erhalten"] == 4)
    _check("error_counts korrekt", row["error_counts"] == {"TimeoutError": 1})
    _check("kompakte JSON-Kodierung", '"date":"2026-10-21"' in open(path, encoding="utf-8").readline())


def test_persist_coverage_row_idempotent():
    path = _fresh_coverage_file()
    hc.COVERAGE_LOG_ENABLED = True
    n1 = hc.persist_coverage_row("earnings_date", 10, 10, {},
                                 report_date_iso="2026-10-21",
                                 run_phase="postclose", path=path)
    n2 = hc.persist_coverage_row("earnings_date", 10, 10, {},
                                 report_date_iso="2026-10-21",
                                 run_phase="postclose", path=path)
    _check("erster Lauf schreibt 1 Zeile", n1 == 1)
    _check("zweiter Lauf (gleiche Phase/Quelle) schreibt 0 Zeilen", n2 == 0)
    _check("nur 1 Zeile in der Datei", len(_load_lines(path)) == 1)
    n3 = hc.persist_coverage_row("earnings_surprise", 10, 10, {},
                                 report_date_iso="2026-10-21",
                                 run_phase="postclose", path=path)
    _check("andere Quelle am selben Tag/Phase schreibt wieder 1 Zeile", n3 == 1)
    _check("jetzt 2 Zeilen in der Datei", len(_load_lines(path)) == 2)


def test_persist_coverage_row_flag_disabled():
    path = _fresh_coverage_file()
    hc.COVERAGE_LOG_ENABLED = False
    try:
        n = hc.persist_coverage_row("openinsider", 5, 5, {},
                                    report_date_iso="2026-10-21",
                                    run_phase="ki_agent_tick", path=path)
        _check("Flag=False → 0 Zeilen", n == 0)
        _check("Flag=False → keine Datei angelegt", not os.path.exists(path))
    finally:
        hc.COVERAGE_LOG_ENABLED = True


def test_persist_coverage_row_zero_expected_skipped():
    path = _fresh_coverage_file()
    hc.COVERAGE_LOG_ENABLED = True
    n = hc.persist_coverage_row("fda_calendar", 0, 0, {},
                                report_date_iso="2026-10-21",
                                run_phase="ki_agent_tick", path=path)
    _check("n_erwartet=0 → keine Zeile", n == 0)
    _check("keine Datei bei n_erwartet=0", not os.path.exists(path))


def test_persist_coverage_row_ki_agent_tick_multiple_per_day():
    """Befund B (22.10.2026): ``run_phase='ki_agent_tick'`` ist für JEDEN
    Tick eines Tages derselbe konstante String — die reine (date,
    run_phase, quelle)-Idempotenz hätte ab dem zweiten Tick eines Tages
    jede weitere Zeile als Duplikat verschluckt (verifiziert: 04:47-Tick
    schrieb, 10:11/11:55/15:17/19:16 desselben Tages nicht). Fix: der Key
    trägt zusätzlich die Tick-Stunde für ki_agent_tick-Zeilen -- vier
    Ticks an verschiedenen Stunden desselben Tages müssen alle vier eine
    Zeile schreiben."""
    path = _fresh_coverage_file()
    hc.COVERAGE_LOG_ENABLED = True
    results = []
    for hour in (4, 10, 11, 15, 19):
        results.append(hc.persist_coverage_row(
            "reddit_mentions", 14, 14, {},
            report_date_iso="2026-10-22", run_phase="ki_agent_tick",
            now_fn=lambda h=hour: datetime(2026, 10, 22, h, 47, tzinfo=timezone.utc),
            path=path))
    _check("alle fünf Ticks (verschiedene Stunden) schreiben je 1 Zeile",
           results == [1, 1, 1, 1, 1])
    _check("5 Zeilen in der Datei (kein Idempotenz-Kollaps mehr)",
           len(_load_lines(path)) == 5)

    # Derselbe Tick (identische Stunde) ein zweites Mal -> weiterhin
    # idempotent (echtes Duplikat innerhalb derselben Stunde wird erkannt).
    n_dup = hc.persist_coverage_row(
        "reddit_mentions", 14, 14, {},
        report_date_iso="2026-10-22", run_phase="ki_agent_tick",
        now_fn=lambda: datetime(2026, 10, 22, 19, 50, tzinfo=timezone.utc),
        path=path)
    _check("zweiter Tick in DERSELBEN Stunde (19 Uhr) -> Duplikat, 0 Zeilen",
           n_dup == 0)
    _check("weiterhin nur 5 Zeilen", len(_load_lines(path)) == 5)


def test_persist_coverage_row_premarket_postclose_unaffected_by_tick_hour():
    """generate_report.py-Verhalten (premarket/postclose, je 1×/Tag) bleibt
    unverändert — ``tick_hour`` ist dort immer ``None``, Idempotenz greift
    weiterhin rein über (date, run_phase, quelle) wie vor diesem Fix."""
    path = _fresh_coverage_file()
    hc.COVERAGE_LOG_ENABLED = True
    n1 = hc.persist_coverage_row(
        "earnings_date", 10, 10, {}, report_date_iso="2026-10-22",
        run_phase="postclose",
        now_fn=lambda: datetime(2026, 10, 22, 21, 0, tzinfo=timezone.utc), path=path)
    n2 = hc.persist_coverage_row(
        "earnings_date", 10, 10, {}, report_date_iso="2026-10-22",
        run_phase="postclose",
        now_fn=lambda: datetime(2026, 10, 22, 22, 0, tzinfo=timezone.utc), path=path)
    _check("erster postclose-Lauf schreibt 1 Zeile", n1 == 1)
    _check("zweiter postclose-Lauf (andere Stunde, GLEICHE Phase) bleibt Duplikat -> 0 Zeilen",
           n2 == 0)
    _check("nur 1 Zeile (unverändertes Verhalten)", len(_load_lines(path)) == 1)
    rows = _load_lines(path)
    _check("tick_hour ist None für premarket/postclose-Zeilen", rows[0].get("tick_hour") is None)


def test_ki_agent_persist_errors_logged_as_warning_not_debug():
    """Befund-B-Fix 22.10.2026, Auftrags-Vorgabe Punkt 2: Persist-Fehler im
    ki_agent-Coverage-Loop müssen auf log.warning stehen, nicht log.debug
    (debug blieb im Workflow-Log faktisch unsichtbar und hätte den
    stillen Idempotenz-Kollaps noch schwerer diagnostizierbar gemacht)."""
    src = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
    needle = 'log.warning("coverage_history (%s) übersprungen: %s", _cov_q, _cov_exc)'
    old_needle = 'log.debug("coverage_history (%s) übersprungen: %s", _cov_q, _cov_exc)'
    _check("coverage_history-Persist-Fehler nutzt log.warning", needle in src)
    _check("altes log.debug für diesen Fehlerpfad nicht mehr vorhanden", old_needle not in src)


def test_persist_coverage_row_legacy_rows_without_tick_hour_field():
    """Alt-Zeilen vor diesem Fix (ohne ``tick_hour``-Feld) dürfen die
    Idempotenz-Prüfung nicht crashen lassen -- ``.get("tick_hour")``
    liefert fail-soft ``None`` für sie."""
    path = _fresh_coverage_file()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "date": "2026-10-22", "run_phase": "ki_agent_tick",
            "quelle": "openinsider", "ts_utc": "2026-10-22T04:47:00+00:00",
            "n_erwartet": 14, "n_erhalten": 14, "n_mit_daten": None,
            "error_counts": {},
        }) + "\n")
    hc.COVERAGE_LOG_ENABLED = True
    n = hc.persist_coverage_row(
        "openinsider", 14, 14, {}, report_date_iso="2026-10-22",
        run_phase="ki_agent_tick",
        now_fn=lambda: datetime(2026, 10, 22, 10, 11, tzinfo=timezone.utc), path=path)
    _check("neuer Tick (andere Stunde) nach Alt-Zeile ohne tick_hour -> schreibt trotzdem (kein Crash)",
           n == 1)
    _check("2 Zeilen in der Datei", len(_load_lines(path)) == 2)


# ===========================================================================
# 2: coverage_liveness_line
# ===========================================================================

def test_coverage_liveness_line_states():
    d = tempfile.mkdtemp()
    missing = os.path.join(d, "absent.jsonl")
    line_absent = hc.coverage_liveness_line("options_atm", missing)
    _check("absent → 'sammelt ab dem nächsten Lauf'",
           "sammelt ab dem nächsten Lauf" in line_absent)

    empty_path = os.path.join(d, "empty.jsonl")
    open(empty_path, "w").close()
    line_empty = hc.coverage_liveness_line("options_atm", empty_path)
    _check("leere Datei → 'unlesbar/leer'", "unlesbar/leer" in line_empty)

    ok_path = os.path.join(d, "ok.jsonl")
    with open(ok_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "date": "2026-10-21", "run_phase": "postclose", "quelle": "options_atm",
            "ts_utc": "2026-10-21T21:30:00+00:00",
            "n_erwartet": 5, "n_erhalten": 4, "error_counts": {"Exception": 1},
        }) + "\n")
    line_ok = hc.coverage_liveness_line("options_atm", ok_path)
    _check("ok → enthält Quote", "4/5" in line_ok)
    print(f"    [Fixture-Digest-Zeile] {line_ok}")

    line_other_quelle = hc.coverage_liveness_line("earnings_date", ok_path)
    _check("andere Quelle ohne eigene Zeile → 'noch keine Zeile'",
           "noch keine Zeile" in line_other_quelle)


# ===========================================================================
# 3: coverage_warn_line
# ===========================================================================

def test_coverage_warn_line():
    d = tempfile.mkdtemp()
    now = datetime(2026, 10, 21, 22, 0, 0, tzinfo=timezone.utc)

    missing = os.path.join(d, "absent.jsonl")
    _check("absent → keine Warnzeile", hc.coverage_warn_line("options_atm", missing, now_ts=now) is None)

    zero_path = os.path.join(d, "zero.jsonl")
    with open(zero_path, "w", encoding="utf-8") as fh:
        for h in (2, 8, 14):
            fh.write(json.dumps({
                "date": "2026-10-21", "run_phase": "postclose", "quelle": "options_atm",
                "ts_utc": f"2026-10-21T{h:02d}:00:00+00:00",
                "n_erwartet": 5, "n_erhalten": 0, "error_counts": {},
            }) + "\n")
    warn = hc.coverage_warn_line("options_atm", zero_path, now_ts=now)
    _check("0 in allen Läufen im Fenster → Warnzeile", warn is not None and "Abdeckung options_atm 0" in warn)
    print(f"    [Fixture-Warnzeile] {warn}")

    mixed_path = os.path.join(d, "mixed.jsonl")
    with open(mixed_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "date": "2026-10-21", "run_phase": "premarket", "quelle": "options_atm",
            "ts_utc": "2026-10-21T02:00:00+00:00",
            "n_erwartet": 5, "n_erhalten": 0, "error_counts": {},
        }) + "\n")
        fh.write(json.dumps({
            "date": "2026-10-21", "run_phase": "postclose", "quelle": "options_atm",
            "ts_utc": "2026-10-21T21:00:00+00:00",
            "n_erwartet": 5, "n_erhalten": 3, "error_counts": {},
        }) + "\n")
    _check("mind. 1 Treffer im Fenster → keine Warnzeile",
           hc.coverage_warn_line("options_atm", mixed_path, now_ts=now) is None)

    outside_path = os.path.join(d, "outside.jsonl")
    with open(outside_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "date": "2026-10-10", "run_phase": "postclose", "quelle": "options_atm",
            "ts_utc": "2026-10-10T21:00:00+00:00",
            "n_erwartet": 5, "n_erhalten": 0, "error_counts": {},
        }) + "\n")
    _check("nur Läufe außerhalb des Fensters → kein Fund (None)",
           hc.coverage_warn_line("options_atm", outside_path, now_ts=now) is None)

    # Legitim: n_erwartet == 0 (Quelle in diesem Run gar nicht aufgerufen)
    # darf NICHT als "0 erhalten" zählen.
    no_expect_path = os.path.join(d, "no_expect.jsonl")
    with open(no_expect_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "date": "2026-10-21", "run_phase": "postclose", "quelle": "earnings_date",
            "ts_utc": "2026-10-21T21:00:00+00:00",
            "n_erwartet": 0, "n_erhalten": 0, "error_counts": {},
        }) + "\n")
    _check("n_erwartet=0-Zeilen im Fenster → kein Fund (None)",
           hc.coverage_warn_line("earnings_date", no_expect_path, now_ts=now) is None)


# ===========================================================================
# 4: coverage_overview_line
# ===========================================================================

def test_coverage_overview_line():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "overview.jsonl")
    _check("absent → 0 von N Quellen",
           "0 von 6 Quellen unter Baseline" in hc.coverage_overview_line(
               path, quellen=["a", "b", "c", "d", "e", "f"]))

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": "2026-10-21", "run_phase": "postclose",
                             "quelle": "a", "ts_utc": "x", "n_erwartet": 5, "n_erhalten": 0}) + "\n")
        fh.write(json.dumps({"date": "2026-10-21", "run_phase": "postclose",
                             "quelle": "b", "ts_utc": "x", "n_erwartet": 5, "n_erhalten": 3}) + "\n")
        fh.write(json.dumps({"date": "2026-10-21", "run_phase": "postclose",
                             "quelle": "a", "ts_utc": "y", "n_erwartet": 5, "n_erhalten": 2}) + "\n")
    overview = hc.coverage_overview_line(path, quellen=["a", "b", "c"])
    _check("nur LETZTE Zeile je Quelle zählt (a jetzt 2/5, nicht 0)",
           "0 von 3 Quellen unter Baseline" in overview)
    print(f"    [Fixture-Übersichtszeile] {overview}")

    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": "2026-10-21", "run_phase": "postclose",
                             "quelle": "a", "ts_utc": "z", "n_erwartet": 5, "n_erhalten": 0}) + "\n")
    overview2 = hc.coverage_overview_line(path, quellen=["a", "b", "c"])
    _check("a jetzt 0/5 (letzte Zeile) → 1 von 3 unter Baseline",
           "1 von 3 Quellen unter Baseline" in overview2)
    _check("Quelle 'c' ohne jemals geschriebene Zeile zählt NICHT als unter Baseline",
           "1 von 3" in overview2)


def test_known_dead_quellen_gate():
    """Wächter 23.10.2026: bekannt tote Quellen → ℹ️ nur bei offenem/
    beobachtetem Item UND ohne Daten; erledigt/fehlend/unlesbar → {}
    (normale ⚠️, fail-safe); wieder Daten → 🆕-Zeile, nicht mehr 'tot'."""
    d = tempfile.mkdtemp()
    cov = os.path.join(d, "cov.jsonl")
    oi = os.path.join(d, "oi.json")
    now = datetime(2026, 10, 23, 13, 47, tzinfo=timezone.utc)
    item = "bekannt-tote-quellen-digest"

    def _oi(status):
        with open(oi, "w", encoding="utf-8") as fh:
            json.dump({"schema_v": 1, "items": [
                {"id": item, "title": "t", "opened": "2026-10-23",
                 "description": "d", "status": status, "status_date": "2026-10-23"}]}, fh)

    def _cov(nmd_reddit):
        with open(cov, "w", encoding="utf-8") as fh:
            for q, nmd in (("reddit_mentions", nmd_reddit), ("openinsider", 0),
                           ("fda_calendar", 0)):
                fh.write(json.dumps({"date": "2026-10-23", "run_phase": "ki_agent_tick",
                                     "quelle": q, "ts_utc": "2026-10-23T13:27:00Z",
                                     "n_erwartet": 16, "n_erhalten": 0,
                                     "n_mit_daten": nmd}) + "\n")

    _cov(0)
    _oi("beobachtet")
    kd = hc.known_dead_coverage_quellen(oi, cov, now_ts=now)
    _check("beobachtet + keine Daten → alle 3 bekannt tot",
           set(kd) == {"reddit_mentions", "openinsider", "fda_calendar"})
    ov = hc.coverage_overview_line(cov, now_ts=now,
                                   quellen=["reddit_mentions", "openinsider",
                                            "fda_calendar", "options_atm"],
                                   exclude=set(kd))
    _check("Übersicht: tote Quellen weder in N noch M",
           "0 von 1 Quellen unter Baseline · 3 bekannt tot (ausgenommen)" in ov)
    _check("ohne exclude: Übersicht unverändert (3 von 4)",
           "3 von 4 Quellen unter Baseline" in hc.coverage_overview_line(
               cov, now_ts=now, quellen=["reddit_mentions", "openinsider",
                                         "fda_calendar", "options_atm"]))
    _check("ℹ️-Zeile nennt Item",
           hc.coverage_known_dead_line("openinsider", item)
           == f"ℹ️ openinsider: bekannt tot (siehe open_items: {item})")
    _check("keine 🆕-Zeile ohne Daten",
           hc.coverage_recovered_line("reddit_mentions", oi, cov, now_ts=now) is None)

    _oi("offen")
    _check("offen → ebenfalls bekannt tot",
           len(hc.known_dead_coverage_quellen(oi, cov, now_ts=now)) == 3)
    _oi("erledigt")
    _check("erledigt → {} (normale ⚠️)",
           hc.known_dead_coverage_quellen(oi, cov, now_ts=now) == {})
    os.remove(oi)
    _check("open_items fehlt → {} (fail-safe)",
           hc.known_dead_coverage_quellen(oi, cov, now_ts=now) == {})
    with open(oi, "w", encoding="utf-8") as fh:
        fh.write("{kaputt")
    _check("open_items unlesbar → {} (fail-safe)",
           hc.known_dead_coverage_quellen(oi, cov, now_ts=now) == {})

    _oi("beobachtet")
    _cov(2)
    kd2 = hc.known_dead_coverage_quellen(oi, cov, now_ts=now)
    _check("reddit liefert wieder Daten → nicht mehr 'tot'",
           "reddit_mentions" not in kd2 and len(kd2) == 2)
    rec = hc.coverage_recovered_line("reddit_mentions", oi, cov, now_ts=now)
    _check("🆕-Zeile bei wieder gelieferten Daten",
           rec is not None and rec.startswith("🆕 reddit_mentions liefert wieder Daten"))
    _check("nicht gemappte Quelle → keine 🆕-Zeile",
           hc.coverage_recovered_line("options_atm", oi, cov, now_ts=now) is None)
    later = datetime(2026, 10, 25, 13, 47, tzinfo=timezone.utc)
    _check("Daten außerhalb 24h-Fenster → wieder 'tot'",
           "reddit_mentions" in hc.known_dead_coverage_quellen(oi, cov, now_ts=later))
    print("    [Fixture] " + ov)


# ===========================================================================
# 5: format_digest_body-Verdrahtung
# ===========================================================================

def test_format_digest_body_wiring():
    body_empty, *_ = hc.format_digest_body(
        [], [], n_runs=0, last_run_iso=None, digest_date="2026-10-21",
        coverage_lines=["📡 Abdeckung options_atm: letzter Lauf 4/5"],
        coverage_warns=["⚠️ Abdeckung openinsider 0 in allen 3 Läufen der letzten 24 h"],
        coverage_overview="📡 Abdeckungs-Übersicht: 1 von 6 Quellen unter Baseline")
    _check("📭-Klasse enthält coverage_lines", "options_atm: letzter Lauf 4/5" in body_empty)
    _check("📭-Klasse enthält coverage_warns", "openinsider 0 in allen" in body_empty)
    _check("📭-Klasse enthält coverage_overview", "1 von 6 Quellen" in body_empty)

    body_ok, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-21T21:00:00Z", digest_date="2026-10-21",
        coverage_lines=["📡 Abdeckung x: letzter Lauf 1/1"])
    _check("✅-Klasse enthält coverage_lines", "letzter Lauf 1/1" in body_ok)

    body_warn, *_ = hc.format_digest_body(
        [{"id": "s1", "severity": "crit", "detail": "x", "recovered": False}], [],
        n_runs=5, last_run_iso="2026-10-21T21:00:00Z", digest_date="2026-10-21",
        coverage_overview="📡 Abdeckungs-Übersicht: 0 von 6 Quellen unter Baseline")
    _check("⚠️-Klasse enthält coverage_overview", "0 von 6 Quellen" in body_warn)

    body_compat, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-21T21:00:00Z", digest_date="2026-10-21")
    _check("Backward-Compat: kein Crash ohne neue Parameter", isinstance(body_compat, str))


# ===========================================================================
# 6: generate_report.py-Instrumentierung (options_atm/earnings_date/
#    earnings_surprise) — echter Fehler zählt, legitim-leer NICHT
# ===========================================================================

class _FakeTicker:
    def __init__(self, *, options=(), raise_on="options", chain=None,
                 fast_info=None, calendar="raise", earnings_history="raise"):
        self._options = options
        self._raise_on = raise_on
        self._chain = chain
        self.fast_info = fast_info or {}
        self._calendar = calendar
        self._earnings_history = earnings_history

    @property
    def options(self):
        if self._raise_on == "options":
            raise RuntimeError("boom")
        return self._options

    def option_chain(self, expiry):
        if self._chain is None:
            raise RuntimeError("boom")
        return self._chain

    @property
    def calendar(self):
        if self._calendar == "raise":
            raise RuntimeError("boom")
        return self._calendar

    @property
    def earnings_history(self):
        if self._earnings_history == "raise":
            raise RuntimeError("boom")
        return self._earnings_history


def test_options_atm_real_error_counted():
    gr._coverage_acct_reset()
    orig_ticker = gr.yf.Ticker
    try:
        gr.yf.Ticker = lambda t: _FakeTicker(raise_on="options")
        result = gr.get_options_data("TEST")
        _check("Exception → leeres Dict (Verhalten unverändert)", result == {})
        _check("n_fehler erhöht", gr._COVERAGE_ACCT["options_atm"]["n_fehler"] == 1)
        _check("exception_type korrekt gezählt",
               gr._COVERAGE_ACCT["options_atm"]["error_counts"].get("RuntimeError") == 1)
    finally:
        gr.yf.Ticker = orig_ticker


def test_options_atm_legitimate_empty_not_counted():
    gr._coverage_acct_reset()
    orig_ticker = gr.yf.Ticker
    try:
        # Keine Expiries → legitimes {} OHNE Exception.
        gr.yf.Ticker = lambda t: _FakeTicker(options=(), raise_on=None)
        result = gr.get_options_data("TEST")
        _check("keine Optionskette → leeres Dict (legitim)", result == {})
        _check("n_fehler NICHT erhöht (legitim-leer)",
               gr._COVERAGE_ACCT["options_atm"]["n_fehler"] == 0)
    finally:
        gr.yf.Ticker = orig_ticker


def test_earnings_date_real_error_counted():
    gr._coverage_acct_reset()
    orig_ticker = gr.yf.Ticker
    try:
        gr.yf.Ticker = lambda t: _FakeTicker(calendar="raise")
        result = gr.get_earnings_date("TEST")
        _check("Exception → (None, None) (Verhalten unverändert)", result == (None, None))
        _check("n_fehler erhöht", gr._COVERAGE_ACCT["earnings_date"]["n_fehler"] == 1)
    finally:
        gr.yf.Ticker = orig_ticker


def test_earnings_date_legitimate_empty_not_counted():
    gr._coverage_acct_reset()
    orig_ticker = gr.yf.Ticker
    try:
        # calendar=None → legitim keine anstehenden Earnings, KEINE Exception.
        gr.yf.Ticker = lambda t: _FakeTicker(calendar=None)
        result = gr.get_earnings_date("TEST")
        _check("calendar=None → (None, None) (legitim)", result == (None, None))
        _check("n_fehler NICHT erhöht (legitim-leer)",
               gr._COVERAGE_ACCT["earnings_date"]["n_fehler"] == 0)
    finally:
        gr.yf.Ticker = orig_ticker


def test_earnings_surprise_real_error_counted():
    gr._coverage_acct_reset()
    orig_ticker = gr.yf.Ticker
    try:
        gr.yf.Ticker = lambda t: _FakeTicker(earnings_history="raise")
        result = gr.get_earnings_surprise("TEST")
        _check("Exception → None (Verhalten unverändert)", result is None)
        _check("n_fehler erhöht", gr._COVERAGE_ACCT["earnings_surprise"]["n_fehler"] == 1)
    finally:
        gr.yf.Ticker = orig_ticker


def test_earnings_surprise_legitimate_empty_not_counted():
    gr._coverage_acct_reset()
    orig_ticker = gr.yf.Ticker
    try:
        # earnings_history=None → legitim keine Historie, KEINE Exception.
        gr.yf.Ticker = lambda t: _FakeTicker(earnings_history=None)
        result = gr.get_earnings_surprise("TEST")
        _check("earnings_history=None → None (legitim)", result is None)
        _check("n_fehler NICHT erhöht (legitim-leer)",
               gr._COVERAGE_ACCT["earnings_surprise"]["n_fehler"] == 0)
    finally:
        gr.yf.Ticker = orig_ticker


# ===========================================================================
# 7: ki_agent.py-Instrumentierung — Zero-Behavior-Change-Beleg
# ===========================================================================

def test_reddit_mentions_real_error_counted_behavior_unchanged():
    ka._coverage_acct_reset()
    orig_get = ka.requests.get
    try:
        def _raise(*a, **k):
            raise ConnectionError("down")
        ka.requests.get = _raise
        result = ka.fetch_reddit_mentions("TEST")
        _check("Netzwerk-Fehler → {'count':0,'sentiment':0.0} (Verhalten unverändert)",
               result == {"count": 0, "sentiment": 0.0})
        _check("n_fehler erhöht (genau 1× pro Ticker-Aufruf, nicht pro Subreddit)",
               ka._COVERAGE_ACCT["reddit_mentions"]["n_fehler"] == 1)
        _check("exception_type korrekt gezählt",
               ka._COVERAGE_ACCT["reddit_mentions"]["error_counts"].get("ConnectionError") == 1)
    finally:
        ka.requests.get = orig_get


def test_reddit_mentions_blocked_counted_as_error():
    ka._coverage_acct_reset()
    orig_get = ka.requests.get
    try:
        class _Resp403:
            status_code = 403
        ka.requests.get = lambda *a, **k: _Resp403()
        result = ka.fetch_reddit_mentions("TEST")
        _check("403 → blocked=True (Verhalten unverändert)", result.get("blocked") is True)
        _check("403-Block zählt als Fehler", ka._COVERAGE_ACCT["reddit_mentions"]["n_fehler"] == 1)
    finally:
        ka.requests.get = orig_get


def test_reddit_mentions_legitimate_empty_not_counted():
    ka._coverage_acct_reset()
    orig_get = ka.requests.get
    try:
        class _RespOK:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"data": {"children": []}}
        ka.requests.get = lambda *a, **k: _RespOK()
        orig_sleep = ka.time.sleep
        ka.time.sleep = lambda *a, **k: None
        try:
            result = ka.fetch_reddit_mentions("TEST")
        finally:
            ka.time.sleep = orig_sleep
        _check("keine Mentions → count=0 (legitim)", result == {"count": 0, "sentiment": 0.0})
        _check("n_fehler NICHT erhöht (legitim-leer)",
               ka._COVERAGE_ACCT["reddit_mentions"]["n_fehler"] == 0)
    finally:
        ka.requests.get = orig_get


def test_fda_calendar_real_error_counted():
    ka._coverage_acct_reset()
    orig_get = ka.requests.get
    try:
        def _raise(*a, **k):
            raise TimeoutError("slow")
        ka.requests.get = _raise
        result = ka.fetch_fda_calendar()
        _check("Fehler → {} (Verhalten unverändert)", result == {})
        _check("n_fehler erhöht", ka._COVERAGE_ACCT["fda_calendar"]["n_fehler"] == 1)
        _check("exception_type korrekt gezählt",
               ka._COVERAGE_ACCT["fda_calendar"]["error_counts"].get("TimeoutError") == 1)
    finally:
        ka.requests.get = orig_get


def test_fda_calendar_legitimate_empty_not_counted():
    ka._coverage_acct_reset()
    orig_get = ka.requests.get
    try:
        class _RespOK:
            status_code = 200
            text = "<rss><channel></channel></rss>"
            def raise_for_status(self): pass
        ka.requests.get = lambda *a, **k: _RespOK()
        result = ka.fetch_fda_calendar()
        _check("keine PDUFA-Treffer → {} (legitim)", result == {})
        _check("n_fehler NICHT erhöht (legitim-leer)",
               ka._COVERAGE_ACCT["fda_calendar"]["n_fehler"] == 0)
    finally:
        ka.requests.get = orig_get


def test_openinsider_real_error_counted():
    ka._coverage_acct_reset()
    orig_get = ka.requests.get
    try:
        def _raise(*a, **k):
            raise RuntimeError("down")
        ka.requests.get = _raise
        result = ka.fetch_openinsider("TEST")
        _check("Fehler → {'count':0,'csuite':False} (Verhalten unverändert)",
               result == {"count": 0, "csuite": False})
        _check("n_fehler erhöht", ka._COVERAGE_ACCT["openinsider"]["n_fehler"] == 1)
    finally:
        ka.requests.get = orig_get


def test_openinsider_legitimate_empty_not_counted():
    ka._coverage_acct_reset()
    orig_get = ka.requests.get
    try:
        class _RespOK:
            status_code = 200
            text = "<rss><channel></channel></rss>"
            def raise_for_status(self): pass
        ka.requests.get = lambda *a, **k: _RespOK()
        result = ka.fetch_openinsider("TEST")
        _check("keine Insider-Käufe → count=0 (legitim)", result == {"count": 0, "csuite": False})
        _check("n_fehler NICHT erhöht (legitim-leer)",
               ka._COVERAGE_ACCT["openinsider"]["n_fehler"] == 0)
    finally:
        ka.requests.get = orig_get


# ===========================================================================
# 8: Score-/Top-10-Gegenprobe
# ===========================================================================

def test_score_unaffected_by_coverage_instrumentation():
    base = [
        {"ticker": "AAA", "short_float": 20, "short_ratio": 8, "rel_volume": 2.5,
         "float_shares": 5_000_000, "price": 4.0, "change": 3.0},
        {"ticker": "BBB", "short_float": 10, "short_ratio": 4, "rel_volume": 1.2,
         "float_shares": 40_000_000, "price": 12.0, "change": 1.0},
    ]
    import copy
    no_opts = copy.deepcopy(base)
    with_opts = copy.deepcopy(base)
    for s in with_opts:
        s["options"] = {"pc_ratio": 1.2, "atm_iv": 0.65}
        s["earnings_days"] = 5
        s["earnings_surprise"] = {"beat": True, "pct": 12.3}

    scores_no = [round(gr.score(s), 6) for s in no_opts]
    scores_with = [round(gr.score(s), 6) for s in with_opts]
    _check("score() identisch mit/ohne options/earnings-Felder", scores_no == scores_with)

    rank_no = [s["ticker"] for s in sorted(no_opts, key=lambda x: gr.score(x), reverse=True)]
    rank_with = [s["ticker"] for s in sorted(with_opts, key=lambda x: gr.score(x), reverse=True)]
    _check("Top-10-Sortierreihenfolge identisch mit/ohne options/earnings-Felder",
           rank_no == rank_with)


def run_all():
    tests = [
        test_persist_coverage_row_schema,
        test_persist_coverage_row_idempotent,
        test_persist_coverage_row_flag_disabled,
        test_persist_coverage_row_zero_expected_skipped,
        test_persist_coverage_row_ki_agent_tick_multiple_per_day,
        test_persist_coverage_row_premarket_postclose_unaffected_by_tick_hour,
        test_ki_agent_persist_errors_logged_as_warning_not_debug,
        test_persist_coverage_row_legacy_rows_without_tick_hour_field,
        test_coverage_liveness_line_states,
        test_coverage_warn_line,
        test_coverage_overview_line,
        test_known_dead_quellen_gate,
        test_format_digest_body_wiring,
        test_options_atm_real_error_counted,
        test_options_atm_legitimate_empty_not_counted,
        test_earnings_date_real_error_counted,
        test_earnings_date_legitimate_empty_not_counted,
        test_earnings_surprise_real_error_counted,
        test_earnings_surprise_legitimate_empty_not_counted,
        test_reddit_mentions_real_error_counted_behavior_unchanged,
        test_reddit_mentions_blocked_counted_as_error,
        test_reddit_mentions_legitimate_empty_not_counted,
        test_fda_calendar_real_error_counted,
        test_fda_calendar_legitimate_empty_not_counted,
        test_openinsider_real_error_counted,
        test_openinsider_legitimate_empty_not_counted,
        test_score_unaffected_by_coverage_instrumentation,
    ]
    for t in tests:
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Coverage-Watchdog-Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle Coverage-Watchdog-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
