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
    fails = hc.evaluate_state_invariants(
        top10_tickers=TOP10,
        setup_scores=_full_setup(TOP10),
        monster_scores=_full_monster(TOP10),
        score_history=_full_history(TOP10),
        today_iso=TODAY,
        n_inflation_lines=10,
        n_backtest_appended=0,    # postclose MUSS schreiben
        agent_signal_keys=set(TOP10),
        run_phase="postclose",
    )
    assert "S4" in _ids(fails)


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
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        fails = hc.run_and_record(
            run_phase="premarket",
            path=path,
            top10_tickers=TOP10,
            setup_scores=_full_setup(TOP10),
            monster_scores=_full_monster(TOP10),
            score_history=_full_history(TOP10),
            today_iso=TODAY,
            n_inflation_lines=10,
            n_backtest_appended=0,
            agent_signal_keys=set(TOP10),
        )
        assert fails == [], f"erwartet keine Fails, got {fails}"
        # Schreib-Smoketest:
        entries = hc.read_all(path)
        assert len(entries) == 1
        assert entries[0]["state_fails"] == []
    finally:
        try:
            pathlib.Path(path).unlink()
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
        ("S4 fail: postclose ohne appends",                test_s4_fail_postclose_no_appends),
        ("S4 pass: premarket ohne appends",                test_s4_pass_premarket_no_appends),
        ("S4 pass: postclose mit appends",                 test_s4_pass_postclose_with_appends),
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
