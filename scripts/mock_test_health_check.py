"""Mock-Tests für health_check.py (Phase 1).

Pro State-Invariant ein Fail-Pfad + ein Pass-Pfad. Zusätzlich:
- ki_agent_only-Modus (Skip-Logik für S1/S4/S5/S7)
- Persistenz (record_run + read_all Round-Trip)
- Prune (älter als HEALTH_CHECK_CUTOFF_DAYS wird entfernt)
- Fail-soft (Schreibfehler crasht nicht)
- Schema-Marker (schema_v=1)

Ausführung: ``python scripts/mock_test_health_check.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest.mock as mock
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402
from config import (        # noqa: E402
    HEALTH_CHECK_S2_MIN_TICKERS,
    HEALTH_CHECK_S5_MIN_INFLATION_LINES,
    HEALTH_CHECK_S6_MIN_MONSTER_NONZERO,
    HEALTH_CHECK_S7_MIN_AGENT_OVERLAP,
)

TODAY = "2026-05-14"
TOP10 = ["AAA", "BBB", "CCC", "DDD", "EEE",
         "FFF", "GGG", "HHH", "III", "JJJ"]


def _full_history(tickers, date=TODAY):
    return {t: [[date, 50.0]] for t in tickers}


def _full_setup(tickers):
    return {t: 60.0 for t in tickers}


def _full_monster(tickers):
    # alle > 0
    return {t: 50.0 for t in tickers}


def _ids(fails: list[dict]) -> set[str]:
    return {f["id"] for f in fails}


# ── S1: score_history hat heute ────────────────────────────────────────────


def test_s1_fail_missing_today():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history={t: [["2026-05-13", 50]] for t in TOP10},
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S1" in _ids(fails), f"S1-Fail-Path verfehlt: {fails}"


def test_s1_pass():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S1" not in _ids(fails), f"S1-Pass-Path fehlerhaft: {fails}"


def test_s1_accepts_de_format():
    """``DD.MM.YYYY`` muss als heutiges Datum erkannt werden."""
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10[:3],
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history={t: [["14.05.2026", 50]] for t in TOP10[:3]},
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S1" not in _ids(fails), f"S1-DE-Format wurde nicht akzeptiert: {fails}"


# ── S2: setup_scores ≥ N ───────────────────────────────────────────────────


def test_s2_fail_too_few():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores={t: 60.0 for t in TOP10[:HEALTH_CHECK_S2_MIN_TICKERS - 1]},
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S2" in _ids(fails)


def test_s2_pass():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S2" not in _ids(fails)


# ── S3: Position-current_price ─────────────────────────────────────────────


def test_s3_fail_missing_price():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        positions={"AMC": {"current_price": None}, "GME": {"current_price": 10.0}},
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S3" in _ids(fails)


def test_s3_pass_all_have_price():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        positions={"AMC": {"current_price": 4.5}, "GME": {"current_price": 10.0}},
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S3" not in _ids(fails)


def test_s3_pass_no_positions():
    """Leere Positionen-Map = kein Fail (Easy hält gerade nichts)."""
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        positions={},
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S3" not in _ids(fails)


# ── S4: backtest-Disziplin Premarket/Postclose ─────────────────────────────


def test_s4_fail_premarket_with_appends():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=10,    # premarket-Run darf KEINE schreiben
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S4" in _ids(fails)


def test_s4_fail_postclose_no_appends():
    """Postclose-Run mit n_appended=0 UND backtest_has_today=False
    (= echter Daten-Lücken-Pfad: weder dieser Run noch ein früherer
    Run heute hat angehängt) muss WARN auslösen.
    """
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        backtest_has_today=False,  # Tages-Invariante: kein Eintrag heute
        agent_signal_keys=set(TOP10),
        run_phase="postclose",
    )
    assert "S4" in _ids(fails)


def test_s4_pass_postclose_re_trigger():
    """Postclose-Re-Trigger am selben Tag (n_appended=0 wegen Idempotenz,
    aber backtest_has_today=True weil ein früherer Run heute angehängt
    hat) darf KEIN WARN auslösen — das war der False-Positive vor dem
    Tages-Basis-Fix.
    """
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        backtest_has_today=True,   # Tag hat schon Eintrag
        agent_signal_keys=set(TOP10),
        run_phase="postclose",
    )
    assert "S4" not in _ids(fails)


def test_s4_pass_premarket_no_appends():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S4" not in _ids(fails)


def test_s4_pass_postclose_with_appends():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=10,
        agent_signal_keys=set(TOP10),
        run_phase="postclose",
    )
    assert "S4" not in _ids(fails)


# ── S4 Wochenend-Gate (30.05.2026) ─────────────────────────────────────────


def test_s4_pass_postclose_saturday_no_appends():
    """Sa-postclose-Run ohne backtest-Eintrag schweigt — Wochenend-Gate
    greift, weil postclose-Cron Mo-Fr ist und Sa per Design kein
    backtest-Append erwartet."""
    # 2026-05-30 = Samstag
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso="2026-05-30",
        n_inflation_lines=10,
        n_backtest_appended=0,
        backtest_has_today=False,
        agent_signal_keys=set(TOP10),
        run_phase="postclose",
    )
    assert "S4" not in _ids(fails), \
        "S4 sollte am Samstag schweigen (Wochenend-Gate)"


def test_s4_pass_postclose_sunday_no_appends():
    """So-postclose-Run ohne backtest-Eintrag schweigt — Gate greift
    für beide Wochenend-Tage."""
    # 2026-05-31 = Sonntag
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso="2026-05-31",
        n_inflation_lines=10,
        n_backtest_appended=0,
        backtest_has_today=False,
        agent_signal_keys=set(TOP10),
        run_phase="postclose",
    )
    assert "S4" not in _ids(fails), \
        "S4 sollte am Sonntag schweigen (Wochenend-Gate)"


def test_s4_fail_postclose_monday_no_appends():
    """Mo-postclose-Run ohne backtest-Eintrag flaggt weiter — Mo-Fr-
    Catch-Wert intakt nach dem Gate."""
    # 2026-05-25 = Montag
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso="2026-05-25",
        n_inflation_lines=10,
        n_backtest_appended=0,
        backtest_has_today=False,
        agent_signal_keys=set(TOP10),
        run_phase="postclose",
    )
    assert "S4" in _ids(fails), \
        "S4 muss Mo-Fr weiter flaggen (Catch-Wert intakt)"


def test_s4_pass_postclose_friday_late_with_saturday_today_iso():
    """Fr-postclose-Run nach Berlin-Mitternacht (z.B. 22:24Z = Sa Berlin):
    today_iso wird vom Caller als Sa-Datum gesetzt → Gate greift auf
    today_iso (Sa), nicht auf 'jetzt' (Fr UTC). Genau der 29.05.22:24Z-
    Fall aus der Diagnose 30.05.2026."""
    # today_iso = 2026-05-30 (Berlin-Sa) — der Caller hat das schon so
    # gesetzt, auch wenn der Run-Wallclock UTC noch Fr war.
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso="2026-05-30",  # Sa
        n_inflation_lines=10,
        n_backtest_appended=0,
        backtest_has_today=False,
        agent_signal_keys=set(TOP10),
        run_phase="postclose",
    )
    assert "S4" not in _ids(fails), \
        "S4-Gate muss am today_iso (Sa) prüfen, nicht an 'jetzt'"


def test_s4_fail_postclose_parse_error_falls_back_to_old_behavior():
    """today_iso-Parse-Fehler → defensive: kein Crash, kein stiller Skip
    des ganzen Catch-Werts — S4 verhält sich wie vor dem Gate-Fix
    (flaggt). Lieber Wochenend-Lärm in einem Edge-Case als blinder
    Mo-Fr-Verlust."""
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso="garbage-not-a-date",
        n_inflation_lines=10,
        n_backtest_appended=0,
        backtest_has_today=False,
        agent_signal_keys=set(TOP10),
        run_phase="postclose",
    )
    assert "S4" in _ids(fails), \
        "Bei Parse-Fehler muss S4 weiter flaggen (defensive)"


# ── S5: score_inflation_log ≥ N Zeilen ─────────────────────────────────────


def test_s5_fail_too_few_lines():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=HEALTH_CHECK_S5_MIN_INFLATION_LINES - 1,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S5" in _ids(fails)


def test_s5_pass():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=HEALTH_CHECK_S5_MIN_INFLATION_LINES,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S5" not in _ids(fails)


# ── S6: monster_scores > 0 ─────────────────────────────────────────────────


def test_s6_fail_too_few_nonzero():
    monster = {t: 0.0 for t in TOP10}
    monster["AAA"] = 50.0  # nur 1 nonzero, Schwelle 3
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=monster,
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S6" in _ids(fails)


def test_s6_pass():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S6" not in _ids(fails)


# ── S7: agent_signals ∩ top10 ≥ N ──────────────────────────────────────────


def test_s7_fail_no_overlap():
    """KI-Score-Drift 14.05.2026: agent_signals hat alte Top-10."""
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys={"OLD1", "OLD2", "OLD3", "OLD4", "OLD5"},
        run_phase="premarket",
    )
    assert "S7" in _ids(fails)


def test_s7_fail_partial_overlap_below_threshold():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        # Nur 4 Top-10-Ticker da, Schwelle 5
        agent_signal_keys=set(TOP10[:HEALTH_CHECK_S7_MIN_AGENT_OVERLAP - 1]),
        run_phase="premarket",
    )
    assert "S7" in _ids(fails)


def test_s7_pass():
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
        run_phase="premarket",
    )
    assert "S7" not in _ids(fails)


# ── ki_agent_only-Modus: S1/S4/S5/S7 müssen geskippt werden ────────────────


def test_ki_agent_only_skips_s1_s4_s5_s7():
    """Auch wenn S1/S4/S5/S7 failen würden — ki_agent_only=True
    überspringt sie. Nur S2/S3/S6 werden bewertet."""
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        # alle würden im Daily-Run failen:
        score_history={},                  # S1-Fail-Bedingung
        today_iso=TODAY,
        n_inflation_lines=0,               # S5-Fail-Bedingung
        n_backtest_appended=99,            # S4-Fail-Bedingung (premarket)
        agent_signal_keys=set(),           # S7-Fail-Bedingung
        run_phase="ki_agent_tick",
        ki_agent_only=True,
    )
    ids = _ids(fails)
    assert "S1" not in ids, f"S1 sollte geskippt sein: {fails}"
    assert "S4" not in ids, f"S4 sollte geskippt sein: {fails}"
    assert "S5" not in ids, f"S5 sollte geskippt sein: {fails}"
    assert "S7" not in ids, f"S7 sollte geskippt sein: {fails}"


def test_ki_agent_only_still_checks_s2_s3_s6():
    """ki_agent_only=True muss S2/S3/S6 weiterhin prüfen."""
    fails = hc.evaluate_state_invariants(
        setup_scores={"AAA": 50},                            # S2-Fail
        monster_scores={"AAA": 50, "BBB": 0, "CCC": 0},      # S6-Fail
        positions={"GME": {"current_price": None}},          # S3-Fail
        run_phase="ki_agent_tick",
        ki_agent_only=True,
    )
    ids = _ids(fails)
    assert "S2" in ids, f"S2 muss prüfbar bleiben: {fails}"
    assert "S3" in ids, f"S3 muss prüfbar bleiben: {fails}"
    assert "S6" in ids, f"S6 muss prüfbar bleiben: {fails}"


# ── Persistenz: record_run + read_all + schema_v=1 ─────────────────────────


def test_record_and_read_roundtrip():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        # Reset file (NamedTemporaryFile leaves bytes)
        open(path, "w").close()
        ok = hc.record_run([{"id": "S2", "severity": "crit", "detail": "x"}],
                           run_phase="premarket",
                           run_ts=datetime(2026, 5, 14, 10, 17, tzinfo=timezone.utc),
                           path=path)
        assert ok, "record_run hat False returnt"
        entries = hc.read_all(path)
        assert len(entries) == 1, f"erwartet 1 Eintrag, got {len(entries)}"
        e = entries[0]
        assert e["schema_v"] == 1, f"schema_v muss 1 sein: {e}"
        assert e["run_phase"] == "premarket"
        assert e["state_fails"][0]["id"] == "S2"
        assert e["provider_fails"] == []
        assert e["run_ts"] == "2026-05-14T10:17:00Z"
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


def test_record_appends():
    """Zweimaliger record_run hängt an, überschreibt nicht."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        hc.record_run([], run_phase="premarket", path=path)
        hc.record_run([{"id": "S6", "severity": "warn", "detail": "y"}],
                      run_phase="postclose", path=path)
        entries = hc.read_all(path)
        assert len(entries) == 2, f"erwartet 2 Einträge, got {len(entries)}"
        assert entries[0]["run_phase"] == "premarket"
        assert entries[1]["run_phase"] == "postclose"
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


# ── Prune ──────────────────────────────────────────────────────────────────


def test_prune_removes_old_keeps_fresh():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=35)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fresh = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(path, "w") as f:
            f.write(json.dumps({"run_ts": old, "run_phase": "premarket",
                                "schema_v": 1, "state_fails": [],
                                "provider_fails": []}) + "\n")
            f.write(json.dumps({"run_ts": fresh, "run_phase": "postclose",
                                "schema_v": 1, "state_fails": [],
                                "provider_fails": []}) + "\n")
        n_removed = hc.prune_log(max_days=30, path=path)
        assert n_removed == 1, f"erwartet 1 entfernt, got {n_removed}"
        entries = hc.read_all(path)
        assert len(entries) == 1
        assert entries[0]["run_ts"] == fresh
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


def test_prune_preserves_broken_lines():
    """Kaputte JSONL-Zeilen sollen NICHT gelöscht werden — operator
    entscheidet bei Manual-Cleanup."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        with open(path, "w") as f:
            f.write("nicht-parsebar\n")
            f.write(json.dumps({"run_ts": "2026-05-14T10:17:00Z",
                                "run_phase": "premarket", "schema_v": 1,
                                "state_fails": [],
                                "provider_fails": []}) + "\n")
        hc.prune_log(max_days=30, path=path)
        with open(path) as f:
            content = f.read()
        assert "nicht-parsebar" in content, "kaputte Zeile gelöscht — Datenverlust"
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


# ── Fail-soft ──────────────────────────────────────────────────────────────


def test_run_and_record_does_not_raise_on_bad_path():
    """run_and_record darf NIE re-raisen — Daily-Run-Crash-Schutz."""
    # Pfad in nicht-existierendem Verzeichnis → OSError beim Schreiben
    bad_path = "/nonexistent/dir/health_check_log.jsonl"
    fails = hc.run_and_record(
        run_phase="premarket",
        path=bad_path,
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,
        agent_signal_keys=set(TOP10),
    )
    # evaluate_state_invariants liefert immer noch eine Liste
    assert isinstance(fails, list), "Fail-soft verletzt — Liste erwartet"


def test_run_and_record_returns_fails_on_pass():
    # DATUMS-STABIL (analog #331-Golden-Stub): run_and_record fährt S1-S14.
    # Die state-/datums-abhängigen Checks lesen sonst REALE Dateien über
    # Default-Pfade und feuern am Wochenende (gealterte Stände):
    #   S8  → DIGEST_STATE_FILE       (last_successful_run, age > 26h)
    #   S14 → GIST_PULL_STATE_FILE    (last_successful_gist_pull, age > 26h)
    #   S11 → SCORE_INFLATION_LOG_FILE (echter premarket, > N Werktage)
    #   S12 → SCORE_INFLATION_LOG_FILE (echter postclose,  > N Werktage)
    #   S13 → evaluate_data_maturity_gate (config-Drift + produktive
    #          backtest_history — analog dem schon gemockten S10)
    # → Quellen auf kontrollierte „alles frisch"-Fixtures umlenken +
    # now_utc fixieren. run_and_record läuft VOLL (S1-S7 echt gegen die
    # übergebenen Fixtures geprüft) — KEIN Wegmocken von run_and_record.
    FIXED_NOW = datetime(2026, 5, 14, 21, 0, 0, tzinfo=timezone.utc)
    iso = FIXED_NOW.isoformat()
    tmp: list[str] = []

    def _mk(content: str, suffix: str = ".json") -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix,
                                         delete=False) as fh:
            fh.write(content)
            tmp.append(fh.name)
            return fh.name

    log_path = _mk("", suffix=".jsonl")
    # S8: frischer Digest-Marker → age ~0 < 26h
    digest_path = _mk(json.dumps({"last_successful_run": iso}))
    # S14: frischer Gist-Pull-Marker → age ~0 < 26h
    gist_path = _mk(json.dumps({"last_successful_gist_pull": iso}))
    # S11/S12: je ein echter premarket-/postclose-Run am FIXED_NOW-Tag
    # (run_phase == trading_session_phase) → last_date >= today → 0 Werktage.
    infl_path = _mk(
        json.dumps({"run_phase": "premarket",
                    "trading_session_phase": "premarket", "run_ts": iso})
        + "\n"
        + json.dumps({"run_phase": "postclose",
                      "trading_session_phase": "postclose", "run_ts": iso})
        + "\n",
        suffix=".jsonl")
    try:
        # S10 + S13 mocken (beide lesen die produktive backtest_history —
        # der Test soll S1-S7 + die kontrollierten S8/S11/S12/S14 prüfen,
        # nicht den produktiven Datenstand).
        with mock.patch.object(hc, "evaluate_s10_data_integrity",
                               return_value=[]), \
             mock.patch.object(hc, "evaluate_data_maturity_gate",
                               return_value={"status_lines": [], "fails": []}), \
             mock.patch.object(hc, "DIGEST_STATE_FILE", digest_path), \
             mock.patch.object(hc, "GIST_PULL_STATE_FILE", gist_path), \
             mock.patch.object(hc, "SCORE_INFLATION_LOG_FILE", infl_path):
            fails = hc.run_and_record(
                run_phase="premarket",
                path=log_path,
                top10_tickers=TOP10,
                setup_scores=_full_setup(TOP10),
                monster_scores=_full_monster(TOP10),
                score_history=_full_history(TOP10),
                today_iso=TODAY,
                n_inflation_lines=10,
                n_backtest_appended=0,
                agent_signal_keys=set(TOP10),
                now_utc=FIXED_NOW,
            )
        assert fails == [], f"erwartet keine Fails, got {fails}"
        # Schreib-Smoketest:
        entries = hc.read_all(log_path)
        assert len(entries) == 1
        assert entries[0]["state_fails"] == []
    finally:
        for p in tmp:
            try:
                pathlib.Path(p).unlink()
            except FileNotFoundError:
                pass


# ── Runner ─────────────────────────────────────────────────────────────────


def main() -> None:
    tests = [
        # S1
        ("S1 fail: kein heutiger Eintrag",                test_s1_fail_missing_today),
        ("S1 pass: heutige Einträge vorhanden",            test_s1_pass),
        ("S1 akzeptiert DD.MM.YYYY",                       test_s1_accepts_de_format),
        # S2
        ("S2 fail: zu wenig Tickers",                      test_s2_fail_too_few),
        ("S2 pass: ≥ Schwelle",                            test_s2_pass),
        # S3
        ("S3 fail: fehlender current_price",               test_s3_fail_missing_price),
        ("S3 pass: alle Positionen haben Kurs",            test_s3_pass_all_have_price),
        ("S3 pass: keine Positionen",                      test_s3_pass_no_positions),
        # S4
        ("S4 fail: premarket mit appends",                 test_s4_fail_premarket_with_appends),
        ("S4 fail: postclose ohne heutigen Eintrag",       test_s4_fail_postclose_no_appends),
        ("S4 pass: postclose Re-Trigger (Tages-Basis)",    test_s4_pass_postclose_re_trigger),
        ("S4 pass: premarket ohne appends",                test_s4_pass_premarket_no_appends),
        ("S4 pass: postclose mit appends",                 test_s4_pass_postclose_with_appends),
        # S4 Wochenend-Gate (30.05.2026)
        ("S4 pass: Sa-postclose ohne Eintrag (Gate)",      test_s4_pass_postclose_saturday_no_appends),
        ("S4 pass: So-postclose ohne Eintrag (Gate)",      test_s4_pass_postclose_sunday_no_appends),
        ("S4 fail: Mo-postclose ohne Eintrag (Catch)",     test_s4_fail_postclose_monday_no_appends),
        ("S4 pass: Fr-postclose >Berlin-Mitternacht (Sa)", test_s4_pass_postclose_friday_late_with_saturday_today_iso),
        ("S4 fail: today_iso-Parse-Fehler (defensive)",    test_s4_fail_postclose_parse_error_falls_back_to_old_behavior),
        # S5
        ("S5 fail: zu wenig Inflation-Zeilen",             test_s5_fail_too_few_lines),
        ("S5 pass: ≥ Schwelle",                            test_s5_pass),
        # S6
        ("S6 fail: zu wenig monster > 0",                  test_s6_fail_too_few_nonzero),
        ("S6 pass: ≥ Schwelle",                            test_s6_pass),
        # S7
        ("S7 fail: agent_signals ∩ top10 = 0",             test_s7_fail_no_overlap),
        ("S7 fail: Overlap unter Schwelle",                test_s7_fail_partial_overlap_below_threshold),
        ("S7 pass: voller Overlap",                        test_s7_pass),
        # ki_agent_only
        ("ki_agent_only skipt S1/S4/S5/S7",                test_ki_agent_only_skips_s1_s4_s5_s7),
        ("ki_agent_only prüft S2/S3/S6",                   test_ki_agent_only_still_checks_s2_s3_s6),
        # Persistenz
        ("record_run + read_all Round-Trip + schema_v=1",  test_record_and_read_roundtrip),
        ("record_run append-only",                         test_record_appends),
        # Prune
        ("prune entfernt alte, behält frische",            test_prune_removes_old_keeps_fresh),
        ("prune behält kaputte Zeilen",                    test_prune_preserves_broken_lines),
        # Fail-soft
        ("run_and_record crasht nicht bei Bad-Path",       test_run_and_record_does_not_raise_on_bad_path),
        ("run_and_record returnt fails-Liste",             test_run_and_record_returns_fails_on_pass),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {name}\n      {exc}")
        except Exception as exc:
            failed += 1
            print(f"  ✗ {name}\n      Unexpected: {type(exc).__name__}: {exc}")
    print()
    if failed:
        print(f"{failed} Test(s) fehlgeschlagen.")
        sys.exit(1)
    print(f"{len(tests)} Tests bestanden.")
    sys.exit(0)


if __name__ == "__main__":
    main()
