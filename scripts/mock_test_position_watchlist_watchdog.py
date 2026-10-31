"""Mock-Tests für den Position-ohne-Watchlist-Wächter (31.10.2026).

Geister-Positionen-Bug-Klasse (open_items.json "geister-positionen-ionq-pdyn"):
eine Position bleibt im Positions-Gist stehen, obwohl der Ticker längst von
der persönlichen Watchlist verschwunden ist — bisher KEIN automatischer
Wächter, nur Zufallsfund. Dieser Wächter gleicht täglich
``app_data.json["positions"]`` gegen ``watchlist_personal.json`` ab und
meldet Positionen seit > 1 Handelstag ohne Watchlist-Eintrag — rein
anzeigend/warnend, KEINE automatische Löschung.

Verriegelt die harten Invarianten:
  1  Position auf der Watchlist -> nie ein Fail, State-Eintrag wird geräumt.
  2  Erstbefund (kein State-Eintrag) -> noch KEIN Fail (Grace-Tag 0), aber
     State wird mit dem heutigen Datum angelegt.
  3  1 Handelstag seit Erstbefund -> noch KEIN Fail ("> 1", nicht ">= 1").
  4  > 1 Handelstag seit Erstbefund -> Fail mit korrekter Handelstag-Zahl.
  5  Wochenende wird bei der Handelstag-Zählung übersprungen (Mo-Fr).
  6  "Unbekannt ≠ ok": Watchlist nicht lesbar (fehlt/kaputt/falscher Typ)
     -> eigener Fail, State bleibt UNVERÄNDERT (keine Uhr startet/läuft
     ohne verlässliche Watchlist-Quelle weiter).
  7  Ticker verschwindet aus den Positionen (Position geschlossen) ->
     State-Pruning, kein Fail, kein Geister-Eintrag.
  8  Ticker kehrt auf die Watchlist zurück -> State-Eintrag wird geräumt,
     kein Fail mehr, auch wenn der alte Erstbefund-Tag weit zurückliegt.
  9  position_watchlist_watchdog_lines (I/O-Wrapper): liest app_data.json +
     watchlist_personal.json + State-Datei, schreibt den State zurück,
     formatiert Fails zu Digest-Zeilen; leere Liste bei 0 Fails.
  10 write_state=False (dry-run) schreibt die State-Datei NICHT.
  11 Fehlende/kaputte app_data.json/State-Datei -> fail-soft, kein Crash.
  12 format_digest_body-Verdrahtung: neuer watchdog_lines-Parameter in
     allen 3 Klassen (OK/warn/keine-Daten) + Backward-Compat ohne Parameter.
  13 Score-/Top-10-Gegenprobe: check_position_watchlist_staleness berührt
     score()/Top-10 gar nicht (reiner Positions-/Watchlist-Vergleich).

Kategorie A: stdlib, deterministisch, env-frei (kein yfinance/requests-
Import nötig — health_check.py ist standalone importierbar).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


# ===========================================================================
# 1-8: check_position_watchlist_staleness (pure)
# ===========================================================================

def test_on_watchlist_never_fails():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    fails, state = hc.check_position_watchlist_staleness(
        {"AMC": {}}, {"AMC", "WOLF"}, {}, now)
    _check("auf Watchlist -> kein Fail", fails == [])
    _check("auf Watchlist -> kein State-Eintrag", "AMC" not in state)


def test_first_seen_no_fail_yet_but_state_set():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)  # Samstag
    fails, state = hc.check_position_watchlist_staleness(
        {"GRPN": {}}, {"AMC"}, {}, now)
    _check("Erstbefund -> noch kein Fail", fails == [])
    _check("Erstbefund -> State mit heutigem Datum", state.get("GRPN") == "2026-10-31")


def test_one_workday_elapsed_no_fail():
    # Erstbefund Freitag 30.10., heute Montag 02.11. -> genau 1 Handelstag.
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    fails, state = hc.check_position_watchlist_staleness(
        {"GRPN": {}}, {"AMC"}, {"GRPN": "2026-10-30"}, now)
    _check("genau 1 Handelstag -> noch kein Fail (> 1 nicht erfüllt)", fails == [])
    _check("State bleibt bestehen", state.get("GRPN") == "2026-10-30")


def test_more_than_one_workday_fails():
    # Erstbefund Freitag 30.10., heute Dienstag 03.11. -> 2 Handelstage.
    now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
    fails, state = hc.check_position_watchlist_staleness(
        {"GRPN": {}}, {"AMC"}, {"GRPN": "2026-10-30"}, now)
    _check("> 1 Handelstag -> genau 1 Fail", len(fails) == 1)
    _check("Fail-Schema korrekt", fails and fails[0]["id"] == "WL1"
           and fails[0]["severity"] == "warn")
    _check("Detail nennt Ticker + Handelstage", fails and "GRPN" in fails[0]["detail"]
           and "2" in fails[0]["detail"])


def test_weekend_skipped_in_workday_count():
    # Erstbefund Donnerstag 29.10., heute Montag 02.11. -> Fr+Mo = 2 Handelstage
    # (Sa/So zählen nicht), also > 1 -> Fail.
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    fails, _ = hc.check_position_watchlist_staleness(
        {"GRPN": {}}, {"AMC"}, {"GRPN": "2026-10-29"}, now)
    _check("Wochenende übersprungen -> 2 Handelstage -> Fail", len(fails) == 1
           and "2 Handelstagen" in fails[0]["detail"])


def test_unknown_watchlist_state_untouched():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    prev_state = {"GRPN": "2026-10-20"}
    fails, state = hc.check_position_watchlist_staleness(
        {"GRPN": {}}, None, prev_state, now)
    _check("Unbekannt -> genau 1 Fail", len(fails) == 1)
    _check("Unbekannt != ok -> eigener Detail-Text",
           fails and "Unbekannt" in fails[0]["detail"])
    _check("State bleibt bei Unbekannt unverändert", state == prev_state)


def test_position_closed_prunes_state():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    fails, state = hc.check_position_watchlist_staleness(
        {}, {"AMC"}, {"IONQ": "2026-08-25", "PDYN": "2026-08-25"}, now)
    _check("keine Positionen mehr -> kein Fail", fails == [])
    _check("geschlossene Positionen werden aus dem State geräumt", state == {})


def test_ticker_returns_to_watchlist_clears_state():
    now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
    fails, state = hc.check_position_watchlist_staleness(
        {"GRPN": {}}, {"GRPN"}, {"GRPN": "2026-08-25"}, now)
    _check("zurück auf Watchlist -> kein Fail trotz alter Uhr", fails == [])
    _check("zurück auf Watchlist -> State geräumt", "GRPN" not in state)


# ===========================================================================
# 9-11: position_watchlist_watchdog_lines (I/O-Wrapper)
# ===========================================================================

def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def test_watchdog_lines_end_to_end_and_state_persisted():
    d = tempfile.mkdtemp()
    app_data_path = os.path.join(d, "app_data.json")
    wl_path = os.path.join(d, "watchlist_personal.json")
    state_path = os.path.join(d, "position_watchlist_state.json")
    _write_json(app_data_path, {"positions": {"GRPN": {}, "AMC": {}}})
    _write_json(wl_path, ["AMC"])
    _write_json(state_path, {"GRPN": "2026-10-29"})

    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    lines = hc.position_watchlist_watchdog_lines(
        now, app_data_path=app_data_path, watchlist_path=wl_path,
        state_path=state_path)
    _check("end-to-end liefert genau eine Zeile", len(lines) == 1)
    _check("Zeile enthält Ticker", lines and "GRPN" in lines[0])

    with open(state_path, "r", encoding="utf-8") as fh:
        persisted = json.load(fh)
    _check("State nach Lauf weiterhin vorhanden (AMC nicht reingerutscht)",
           "AMC" not in persisted and persisted.get("GRPN") == "2026-10-29")


def test_watchdog_lines_dry_run_does_not_write_state():
    d = tempfile.mkdtemp()
    app_data_path = os.path.join(d, "app_data.json")
    wl_path = os.path.join(d, "watchlist_personal.json")
    state_path = os.path.join(d, "position_watchlist_state.json")
    _write_json(app_data_path, {"positions": {"GRPN": {}}})
    _write_json(wl_path, ["AMC"])
    # Kein State-File vorhanden -> Erstbefund-Pfad würde normalerweise
    # eine Datei anlegen.
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    lines = hc.position_watchlist_watchdog_lines(
        now, app_data_path=app_data_path, watchlist_path=wl_path,
        state_path=state_path, write_state=False)
    _check("dry-run liefert leere Liste bei Erstbefund (kein Fail)", lines == [])
    _check("dry-run schreibt KEINE State-Datei", not os.path.exists(state_path))


def test_watchdog_lines_missing_app_data_fail_soft():
    d = tempfile.mkdtemp()
    wl_path = os.path.join(d, "watchlist_personal.json")
    _write_json(wl_path, ["AMC"])
    lines = hc.position_watchlist_watchdog_lines(
        datetime.now(timezone.utc),
        app_data_path=os.path.join(d, "nicht_da.json"),
        watchlist_path=wl_path,
        state_path=os.path.join(d, "position_watchlist_state.json"))
    _check("fehlende app_data.json -> kein Crash, leere Liste "
           "(keine Positionen -> nichts zu prüfen)", lines == [])


def test_watchdog_lines_broken_json_fail_soft():
    d = tempfile.mkdtemp()
    app_data_path = os.path.join(d, "app_data.json")
    with open(app_data_path, "w", encoding="utf-8") as fh:
        fh.write("{kaputt")
    lines = hc.position_watchlist_watchdog_lines(
        datetime.now(timezone.utc),
        app_data_path=app_data_path,
        watchlist_path=os.path.join(d, "watchlist_personal.json"),
        state_path=os.path.join(d, "position_watchlist_state.json"))
    _check("kaputte app_data.json -> kein Crash", isinstance(lines, list))


def test_read_watchlist_tickers_distinguishes_unknown_from_empty():
    d = tempfile.mkdtemp()
    missing_path = os.path.join(d, "fehlt.json")
    _check("fehlende Datei -> None (Unbekannt)",
           hc._read_watchlist_tickers_for_watchdog(missing_path) is None)

    empty_path = os.path.join(d, "leer.json")
    _write_json(empty_path, [])
    _check("leere, aber valide Liste -> leeres Set (nicht None)",
           hc._read_watchlist_tickers_for_watchdog(empty_path) == set())

    wrong_type_path = os.path.join(d, "falsch.json")
    _write_json(wrong_type_path, {"not": "a list"})
    _check("falscher Typ -> None (Unbekannt)",
           hc._read_watchlist_tickers_for_watchdog(wrong_type_path) is None)


# ===========================================================================
# 12: format_digest_body-Verdrahtung
# ===========================================================================

def test_format_digest_body_watchdog_wiring():
    wd_lines = ["👁 Position GRPN ohne Watchlist-Eintrag seit 2 Handelstagen"]

    body_ok, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-31T21:00:00Z", digest_date="2026-10-31",
        watchdog_lines=wd_lines)
    _check("✅-Klasse enthält watchdog_lines", "GRPN" in body_ok)

    body_warn, *_ = hc.format_digest_body(
        [{"id": "s1", "severity": "crit"}], [], n_runs=5,
        last_run_iso="2026-10-31T21:00:00Z", digest_date="2026-10-31",
        watchdog_lines=wd_lines)
    _check("⚠️-Klasse enthält watchdog_lines", "GRPN" in body_warn)

    body_no_data, *_ = hc.format_digest_body(
        [], [], n_runs=0, last_run_iso=None, digest_date="2026-10-31",
        watchdog_lines=wd_lines)
    _check("📭-Klasse enthält watchdog_lines", "GRPN" in body_no_data)

    body_compat, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-31T21:00:00Z", digest_date="2026-10-31")
    _check("Backward-Compat: kein Crash ohne neuen Parameter", isinstance(body_compat, str))

    body_empty, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-31T21:00:00Z", digest_date="2026-10-31",
        watchdog_lines=[])
    _check("leere Liste -> kein Crash, keine Zusatzzeile", isinstance(body_empty, str))


# ===========================================================================
# 13: Score-/Top-10-Gegenprobe
# ===========================================================================

def test_no_score_module_touch():
    import inspect
    src = inspect.getsource(hc.check_position_watchlist_staleness)
    _check("Pure Funktion referenziert score()/Top-10 nirgends",
           "score(" not in src and "top10" not in src.lower())


def run_all():
    tests = [
        test_on_watchlist_never_fails,
        test_first_seen_no_fail_yet_but_state_set,
        test_one_workday_elapsed_no_fail,
        test_more_than_one_workday_fails,
        test_weekend_skipped_in_workday_count,
        test_unknown_watchlist_state_untouched,
        test_position_closed_prunes_state,
        test_ticker_returns_to_watchlist_clears_state,
        test_watchdog_lines_end_to_end_and_state_persisted,
        test_watchdog_lines_dry_run_does_not_write_state,
        test_watchdog_lines_missing_app_data_fail_soft,
        test_watchdog_lines_broken_json_fail_soft,
        test_read_watchlist_tickers_distinguishes_unknown_from_empty,
        test_format_digest_body_watchdog_wiring,
        test_no_score_module_touch,
    ]
    for t in tests:
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Position-Watchlist-Watchdog-Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle Position-Watchlist-Watchdog-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
