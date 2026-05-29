"""Mock-Tests fuer Health-Check-Digest Fail-Visibility-Fix (16.05.2026).

Hintergrund (Diagnose 16.05.2026):
- Workflow am 15.05. lief grün durch, aber ntfy-Send hat silent
  gefailt (state-Datei blieb mit last_digest_sent=null). Easy hat
  keinen Push bekommen und kein Workflow-Fail bemerkt.
- Cron 21 8 wurde am 15./16.05. wiederholt gedropt.

Fix:
A) Cron 21 -> 47 (workflow-yaml)
B) ntfy-Send-Fail mit aktivem NTFY_TOPIC -> sys.exit(1)
   - state-Datei trotzdem persistiert (vor exit)
   - Workflow-Commit-Step bekommt `if: always()` damit state
     committed wird auch bei exit 1
C) Neuer State-Invariant S8: digest-state-File last_digest_sent
   > 26 h alt -> warn-Eintrag

Tests:
  1. main() mit ntfy_active + sent=True -> exit 0, state updated
  2. main() mit ntfy_active + sent=False -> exit 1, state still saved
  3. main() ohne NTFY_TOPIC (Test-Mode) -> exit 0 selbst bei sent=False
  4. main() mit Exception in _ntfy_send -> exit 1 (kein silent fail)
  5. main() bei _already_sent_today + nicht force -> exit 0
  6. dry_run -> exit 0 ohne state-Update
  7. S8: state mit last_digest_sent vor 30h -> warn-Eintrag
  8. S8: state mit last_digest_sent heute -> kein S8-Eintrag
  9. S8: state-Datei fehlt -> kein S8-Eintrag (Erstaufsetzen)
 10. S8: state mit null last_digest_sent -> kein S8-Eintrag
 11. S8: state mit kaputtem JSON -> kein S8-Eintrag (graceful)
 12. S8: state mit invalid Datum -> kein S8-Eintrag
 13. Cron-Slot im workflow-yaml ist 47 8 * * *
 14. Commit-State-Step hat if: always()
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WORKFLOW_YML = (ROOT / ".github" / "workflows" / "health_check_digest.yml").read_text(encoding="utf-8")
SCRIPT_SRC = (ROOT / "scripts" / "health_check_digest.py").read_text(encoding="utf-8")

import health_check as hc
import health_check_digest as hcd  # type: ignore  # import via sys.path-Setup


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_13_cron_offset_47() -> None:
    assert "cron: '47 8 * * *'" in WORKFLOW_YML, \
        "Cron-Offset nicht auf 47 geändert"
    assert "cron: '21 8 * * *'" not in WORKFLOW_YML, \
        "Alter 21-Offset noch vorhanden"


def test_14_commit_step_always() -> None:
    # Commit-Step muss if: always() haben damit state auch bei exit 1
    # persistiert wird
    assert "Commit digest state" in WORKFLOW_YML
    # Suche nach if: always() in der Nähe des Commit-Steps
    commit_idx = WORKFLOW_YML.find("Commit digest state")
    nearby = WORKFLOW_YML[commit_idx:commit_idx + 400]
    assert "if: always()" in nearby, \
        "Commit-Step hat keinen if: always()-Guard"


# ── _digest_age_hours-Tests (S8-Helper) ──────────────────────────────────────

def _write_state(d: dict) -> str:
    fh = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                       encoding="utf-8")
    fh.write(json.dumps(d))
    fh.close()
    return fh.name


def test_09_s8_state_missing_returns_none() -> None:
    age = hc._digest_age_hours(datetime.now(timezone.utc), state_path="/nonexistent.json")
    assert age is None


def test_10_s8_null_last_digest_sent() -> None:
    path = _write_state({"last_digest_sent": None, "last_successful_run": None})
    try:
        age = hc._digest_age_hours(datetime.now(timezone.utc), state_path=path)
        assert age is None
    finally:
        os.unlink(path)


def test_11_s8_corrupt_json() -> None:
    fh = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                       encoding="utf-8")
    fh.write("{not valid json")
    fh.close()
    try:
        age = hc._digest_age_hours(datetime.now(timezone.utc), state_path=fh.name)
        assert age is None
    finally:
        os.unlink(fh.name)


def test_12_s8_invalid_date_format() -> None:
    path = _write_state({"last_digest_sent": "garbage-date"})
    try:
        age = hc._digest_age_hours(datetime.now(timezone.utc), state_path=path)
        assert age is None
    finally:
        os.unlink(path)


def test_07_s8_stale_30h_warns() -> None:
    # Referenz-Wechsel 29.05.2026 (PR S8-last_successful_run): S8 misst
    # jetzt last_successful_run (ISO-Timestamp), nicht last_digest_sent
    # (YYYY-MM-DD). Test setzt last_successful_run 2 Tage alt → > 26 h → warn.
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    path = _write_state({"last_successful_run": stale_ts})
    try:
        # evaluate über monkey-patch DIGEST_STATE_FILE
        original = hc.DIGEST_STATE_FILE
        hc.DIGEST_STATE_FILE = path
        try:
            fails = hc.evaluate_state_invariants(
                top10_tickers=[],
                setup_scores={"A": 1} * 10 if False else {f"T{i}": 50 for i in range(10)},
                positions={},
                score_history={},
                today_iso="2026-05-16",
                run_phase="postclose",
                n_inflation_lines=20,
                n_backtest_appended=1,
                agent_signal_keys=[],
                ki_agent_only=True,  # nur S2/S3/S6/S8
            )
            s8_fails = [f for f in fails if f["id"] == "S8"]
            assert len(s8_fails) == 1, f"Erwarte 1 S8-Fail, got {len(s8_fails)}: {fails}"
            assert s8_fails[0]["severity"] == "warn"
            assert "Stunden" in s8_fails[0]["detail"] or " h" in s8_fails[0]["detail"]
        finally:
            hc.DIGEST_STATE_FILE = original
    finally:
        os.unlink(path)


def test_08_s8_fresh_no_fail() -> None:
    # Referenz-Wechsel 29.05.2026: last_successful_run frisch gesetzt → kein S8.
    fresh_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = _write_state({"last_successful_run": fresh_ts})
    try:
        original = hc.DIGEST_STATE_FILE
        hc.DIGEST_STATE_FILE = path
        try:
            fails = hc.evaluate_state_invariants(
                top10_tickers=[],
                setup_scores={f"T{i}": 50 for i in range(10)},
                positions={},
                score_history={},
                today_iso="2026-05-16",
                run_phase="postclose",
                n_inflation_lines=20,
                n_backtest_appended=1,
                agent_signal_keys=[],
                ki_agent_only=True,
            )
            s8_fails = [f for f in fails if f["id"] == "S8"]
            assert s8_fails == [], f"Frischer state darf kein S8-Fail haben: {s8_fails}"
        finally:
            hc.DIGEST_STATE_FILE = original
    finally:
        os.unlink(path)


# ── main()-Pfad: exit-code-Verhalten ─────────────────────────────────────────

def _make_state_file_path() -> str:
    """Fresh tmp file für DIGEST_STATE_FILE."""
    fh = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                       encoding="utf-8")
    fh.write(json.dumps({"consecutive_failures": {}, "last_seen": {},
                          "last_digest_sent": None, "last_successful_run": None}))
    fh.close()
    return fh.name


def test_01_main_sent_true_exit0() -> None:
    state_path = _make_state_file_path()
    try:
        with patch.object(hcd, "DIGEST_STATE_FILE", pathlib.Path(state_path)), \
             patch.object(hcd, "_ntfy_send", return_value=True), \
             patch.object(hcd, "NTFY_TOPIC", "test-topic"), \
             patch.object(hcd, "NTFY_ENABLED", True), \
             patch.object(hcd, "_load_jsonl_window", return_value=[]):
            rc = hcd.main(now_ts=datetime(2026, 5, 16, 8, 47, tzinfo=timezone.utc))
            assert rc == 0
            # State sollte last_digest_sent="2026-05-16" haben
            s = json.loads(pathlib.Path(state_path).read_text())
            assert s["last_digest_sent"] == "2026-05-16"
    finally:
        os.unlink(state_path)


def test_02_main_sent_false_topic_set_exit1() -> None:
    state_path = _make_state_file_path()
    try:
        with patch.object(hcd, "DIGEST_STATE_FILE", pathlib.Path(state_path)), \
             patch.object(hcd, "_ntfy_send", return_value=False), \
             patch.object(hcd, "NTFY_TOPIC", "test-topic"), \
             patch.object(hcd, "NTFY_ENABLED", True), \
             patch.object(hcd, "_load_jsonl_window", return_value=[]):
            rc = hcd.main(now_ts=datetime(2026, 5, 16, 8, 47, tzinfo=timezone.utc))
            assert rc == 1, f"Erwarte exit 1, got {rc}"
            # State muss trotzdem geschrieben sein (fail-Visibility-Fix)
            s = json.loads(pathlib.Path(state_path).read_text())
            # last_digest_sent bleibt null weil sent=False UND ntfy aktiv
            assert s["last_digest_sent"] is None, \
                "last_digest_sent darf bei Fail nicht gesetzt sein"
    finally:
        os.unlink(state_path)


def test_03_main_no_topic_test_mode_exit0() -> None:
    state_path = _make_state_file_path()
    try:
        with patch.object(hcd, "DIGEST_STATE_FILE", pathlib.Path(state_path)), \
             patch.object(hcd, "_ntfy_send", return_value=False), \
             patch.object(hcd, "NTFY_TOPIC", ""), \
             patch.object(hcd, "NTFY_ENABLED", False), \
             patch.object(hcd, "_load_jsonl_window", return_value=[]):
            rc = hcd.main(now_ts=datetime(2026, 5, 16, 8, 47, tzinfo=timezone.utc))
            assert rc == 0, f"Test-Mode darf kein exit 1 sein, got {rc}"
            s = json.loads(pathlib.Path(state_path).read_text())
            # Trotz ntfy disabled wird last_digest_sent gesetzt (Cooldown)
            assert s["last_digest_sent"] == "2026-05-16"
    finally:
        os.unlink(state_path)


def test_04_main_exception_in_ntfy_exit1() -> None:
    state_path = _make_state_file_path()
    def _raises(*args, **kw):
        raise RuntimeError("network boom")
    try:
        with patch.object(hcd, "DIGEST_STATE_FILE", pathlib.Path(state_path)), \
             patch.object(hcd, "_ntfy_send", side_effect=_raises), \
             patch.object(hcd, "NTFY_TOPIC", "test-topic"), \
             patch.object(hcd, "NTFY_ENABLED", True), \
             patch.object(hcd, "_load_jsonl_window", return_value=[]):
            rc = hcd.main(now_ts=datetime(2026, 5, 16, 8, 47, tzinfo=timezone.utc))
            assert rc == 1, f"Exception muss zu exit 1 führen, got {rc}"
            # State trotzdem geschrieben
            assert pathlib.Path(state_path).exists()
    finally:
        os.unlink(state_path)


def test_05_main_already_sent_today_skip() -> None:
    state_path = _make_state_file_path()
    pathlib.Path(state_path).write_text(json.dumps({
        "consecutive_failures": {}, "last_seen": {},
        "last_digest_sent": "2026-05-16", "last_successful_run": None,
    }))
    try:
        with patch.object(hcd, "DIGEST_STATE_FILE", pathlib.Path(state_path)), \
             patch.object(hcd, "_ntfy_send", return_value=True) as mock_send, \
             patch.object(hcd, "NTFY_TOPIC", "test-topic"), \
             patch.object(hcd, "NTFY_ENABLED", True), \
             patch.object(hcd, "_load_jsonl_window", return_value=[]):
            rc = hcd.main(now_ts=datetime(2026, 5, 16, 8, 47, tzinfo=timezone.utc))
            assert rc == 0
            # _ntfy_send darf nicht aufgerufen worden sein (early exit)
            assert mock_send.call_count == 0, \
                "Bereits-gesendet-Schutz hat nicht gegriffen"
    finally:
        os.unlink(state_path)


def test_06_main_dry_run_exit0() -> None:
    state_path = _make_state_file_path()
    try:
        with patch.object(hcd, "DIGEST_STATE_FILE", pathlib.Path(state_path)), \
             patch.object(hcd, "_ntfy_send", return_value=False) as mock_send, \
             patch.object(hcd, "NTFY_TOPIC", "test-topic"), \
             patch.object(hcd, "NTFY_ENABLED", True), \
             patch.object(hcd, "_load_jsonl_window", return_value=[]):
            rc = hcd.main(dry_run=True,
                           now_ts=datetime(2026, 5, 16, 8, 47, tzinfo=timezone.utc))
            assert rc == 0
            assert mock_send.call_count == 0
            # State bei dry_run nicht geändert
            s = json.loads(pathlib.Path(state_path).read_text())
            assert s["last_digest_sent"] is None
    finally:
        os.unlink(state_path)


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 sent=True → exit 0 + state updated",      test_01_main_sent_true_exit0),
        ("02 sent=False + TOPIC → exit 1",             test_02_main_sent_false_topic_set_exit1),
        ("03 ohne TOPIC → exit 0 (Test-Mode)",         test_03_main_no_topic_test_mode_exit0),
        ("04 Exception in _ntfy_send → exit 1",        test_04_main_exception_in_ntfy_exit1),
        ("05 already_sent_today → skip + exit 0",      test_05_main_already_sent_today_skip),
        ("06 dry_run → exit 0 ohne send",              test_06_main_dry_run_exit0),
        ("07 S8: stale 30h → warn",                    test_07_s8_stale_30h_warns),
        ("08 S8: heute frisch → kein Fail",            test_08_s8_fresh_no_fail),
        ("09 S8: state-File fehlt → kein Fail",        test_09_s8_state_missing_returns_none),
        ("10 S8: null last_digest_sent → kein Fail",   test_10_s8_null_last_digest_sent),
        ("11 S8: kaputtes JSON → kein Fail",           test_11_s8_corrupt_json),
        ("12 S8: invalid Datum → kein Fail",           test_12_s8_invalid_date_format),
        ("13 Cron-Offset 47",                          test_13_cron_offset_47),
        ("14 Commit-Step hat if: always()",            test_14_commit_step_always),
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
