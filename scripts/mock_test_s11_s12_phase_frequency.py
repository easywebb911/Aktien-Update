"""Mock-Tests für S11/S12 Phasen-Sammel-Frequenz-Wächter.

S11 (warn): premarket-Sammel-Frequenz — letzter run_phase==tsp=='premarket'
  im score_inflation_log älter als HEALTH_CHECK_S11_MAX_WORKDAYS_NO_PREMARKET
  Werktagen.
S12 (crit, NUR-REPORTING): analog für postclose.

KRITISCH: S12-crit darf den blockierenden S9-CRIT-Exit-Pfad
(generate_report.py:16128) NICHT triggern. Verifiziert via Source-Inspection,
dass der Exit-Filter strikt auf ``id == "S9"`` eingegrenzt bleibt.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Repo-Root in sys.path damit `import health_check` / `import config` läuft.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import health_check as hc  # noqa: E402
import config              # noqa: E402


def _make_log(rows):
    """Schreibt JSONL-Zeilen in eine temp-Datei, returnt den Pfad."""
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


# ── Helper-Tests (_last_phase_run_age_workdays) ───────────────────────────


def test_01_skip_when_file_missing():
    """Datei fehlt → return None (analog _digest_age_hours)."""
    age = hc._last_phase_run_age_workdays(
        "premarket", "premarket",
        datetime(2026, 5, 28, tzinfo=timezone.utc),
        log_path="/nonexistent/score_inflation_log.jsonl",
    )
    assert age is None, f"erwartet None, got {age}"


def test_02_skip_when_no_matching_line():
    """Datei da, aber keine echte premarket-Zeile → None."""
    path = _make_log([
        {"run_phase": "premarket", "trading_session_phase": "open",
         "run_ts": "2026-05-27T11:00:00Z"},
        {"run_phase": "postclose", "trading_session_phase": "postclose",
         "run_ts": "2026-05-27T21:00:00Z"},
    ])
    try:
        age = hc._last_phase_run_age_workdays(
            "premarket", "premarket",
            datetime(2026, 5, 28, tzinfo=timezone.utc),
            log_path=path,
        )
        assert age is None, f"erwartet None, got {age}"
    finally:
        os.unlink(path)


def test_03_recent_premarket_zero_workdays():
    """Letzter echter premarket heute → 0 Werktage."""
    path = _make_log([
        {"run_phase": "premarket", "trading_session_phase": "premarket",
         "run_ts": "2026-05-28T11:49:51Z"},
    ])
    try:
        age = hc._last_phase_run_age_workdays(
            "premarket", "premarket",
            datetime(2026, 5, 28, 14, 0, tzinfo=timezone.utc),
            log_path=path,
        )
        assert age == 0, f"erwartet 0, got {age}"
    finally:
        os.unlink(path)


def test_04_old_premarket_counted_mon_fri_only():
    """Mi 27.05. letzter echter premarket, heute Mi 03.06. → 5 Mo-Fr-Tage
    (Do 28, Fr 29, Mo 1, Di 2, Mi 3; Sa 30 + So 31 raus)."""
    path = _make_log([
        {"run_phase": "premarket", "trading_session_phase": "premarket",
         "run_ts": "2026-05-27T11:49:51Z"},
    ])
    try:
        age = hc._last_phase_run_age_workdays(
            "premarket", "premarket",
            datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc),
            log_path=path,
        )
        assert age == 5, f"erwartet 5 Werktage, got {age}"
    finally:
        os.unlink(path)


def test_05_drift_does_not_count_as_real_premarket():
    """Gedrifteter Cron (run_phase=premarket aber tsp=open) zählt NICHT
    als echter premarket-Run — exakt der 28.05.-Diagnose-Befund."""
    path = _make_log([
        {"run_phase": "premarket", "trading_session_phase": "premarket",
         "run_ts": "2026-05-20T12:40:00Z"},     # letzter echter
        {"run_phase": "premarket", "trading_session_phase": "open",
         "run_ts": "2026-05-28T14:02:00Z"},     # drift, zählt nicht
    ])
    try:
        # 20.05 Mi → 21,22,[23,24 WE],25,26,27,28 = 6 Mo-Fr-Tage
        age = hc._last_phase_run_age_workdays(
            "premarket", "premarket",
            datetime(2026, 5, 28, 16, 0, tzinfo=timezone.utc),
            log_path=path,
        )
        assert age == 6, f"erwartet 6 (drift nicht zählen), got {age}"
    finally:
        os.unlink(path)


def test_06_postclose_filter_independent_from_premarket():
    """Filter trennt sauber zwischen 'premarket' und 'postclose'."""
    path = _make_log([
        {"run_phase": "premarket", "trading_session_phase": "premarket",
         "run_ts": "2026-05-28T11:00:00Z"},
    ])
    try:
        pm = hc._last_phase_run_age_workdays(
            "premarket", "premarket",
            datetime(2026, 5, 28, 16, 0, tzinfo=timezone.utc),
            log_path=path,
        )
        pc = hc._last_phase_run_age_workdays(
            "postclose", "postclose",
            datetime(2026, 5, 28, 16, 0, tzinfo=timezone.utc),
            log_path=path,
        )
        assert pm == 0, f"premarket erwartet 0, got {pm}"
        assert pc is None, f"postclose erwartet None, got {pc}"
    finally:
        os.unlink(path)


def test_07_corrupt_jsonl_lines_tolerated():
    """Defekte Zeilen werden überlesen, intakte gezählt."""
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("not-json\n")
        fh.write(json.dumps({
            "run_phase": "premarket",
            "trading_session_phase": "premarket",
            "run_ts": "2026-05-27T11:49:51Z",
        }) + "\n")
        fh.write("\n")           # leere Zeile
        fh.write("{broken}\n")   # JSON kaputt
    try:
        age = hc._last_phase_run_age_workdays(
            "premarket", "premarket",
            datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc),
            log_path=path,
        )
        assert age == 1, f"erwartet 1 (Do 28 nach Mi 27), got {age}"
    finally:
        os.unlink(path)


# ── Konstanten / Konfiguration ────────────────────────────────────────────


def test_08_constants_present_in_config():
    """S11/S12-Konstanten in config.py vorhanden + plausibel."""
    assert hasattr(config, "HEALTH_CHECK_S11_MAX_WORKDAYS_NO_PREMARKET"), \
        "HEALTH_CHECK_S11_MAX_WORKDAYS_NO_PREMARKET fehlt in config.py"
    assert hasattr(config, "HEALTH_CHECK_S12_MAX_WORKDAYS_NO_POSTCLOSE"), \
        "HEALTH_CHECK_S12_MAX_WORKDAYS_NO_POSTCLOSE fehlt in config.py"
    assert config.HEALTH_CHECK_S11_MAX_WORKDAYS_NO_PREMARKET >= 1
    assert config.HEALTH_CHECK_S12_MAX_WORKDAYS_NO_POSTCLOSE >= 1


# ── Source-Inspection: Exit-Pfad-Schutz für S12 ───────────────────────────


def test_09_s9_exit_filter_isolates_S12():
    """generate_report.py:16128 filtert EXPLIZIT auf ``id == "S9"``.
    S12 mit ``id='S12'`` kann den blockierenden Exit-Pfad strukturell
    NICHT triggern — DAS ist der S12-Schutz.

    Refactor-Falle: wenn der Filter auf reine ``severity == "crit"``
    umgestellt wird, würde S12 plötzlich blockieren. Dieser Test fängt
    diesen Bruch (Bypass nur mit explizit angepasstem Test).
    """
    src = (Path(__file__).resolve().parent.parent
           / "generate_report.py").read_text(encoding="utf-8")
    needle = 'f.get("id") == "S9" and f.get("severity") == "crit"'
    assert needle in src, (
        f"EXIT-PFAD-FILTER {needle!r} fehlt in generate_report.py — "
        "S12-Schutz kompromittiert! Refactor angepasst werden müssen "
        "oder explizite id-Whitelist sicherstellen."
    )


# ── Source-Inspection: S11/S12 sauber im Check eingehängt ─────────────────


def test_10_s11_s12_block_present_with_ki_agent_only_gate():
    """S11/S12-Blöcke in evaluate_state_invariants vorhanden und durch
    ``if not ki_agent_only:``-Gate geschützt (analog S5)."""
    src = (Path(__file__).resolve().parent.parent
           / "health_check.py").read_text(encoding="utf-8")
    assert '"id": "S11"' in src, "S11-Block fehlt in health_check.py"
    assert '"id": "S12"' in src, "S12-Block fehlt in health_check.py"
    assert '_last_phase_run_age_workdays' in src, \
        "Helper-Aufruf fehlt in health_check.py"

    s11_idx = src.find('"id": "S11"')
    region_before_s11 = src[max(0, s11_idx - 600):s11_idx]
    assert 'if not ki_agent_only' in region_before_s11, \
        "S11 ist nicht durch ki_agent_only-Gate geschützt (Soll analog S5)"

    s12_idx = src.find('"id": "S12"')
    region_before_s12 = src[max(0, s12_idx - 600):s12_idx]
    assert 'if not ki_agent_only' in region_before_s12, \
        "S12 ist nicht durch ki_agent_only-Gate geschützt"


# ── Test-Runner ───────────────────────────────────────────────────────────


if __name__ == "__main__":
    tests = [
        test_01_skip_when_file_missing,
        test_02_skip_when_no_matching_line,
        test_03_recent_premarket_zero_workdays,
        test_04_old_premarket_counted_mon_fri_only,
        test_05_drift_does_not_count_as_real_premarket,
        test_06_postclose_filter_independent_from_premarket,
        test_07_corrupt_jsonl_lines_tolerated,
        test_08_constants_present_in_config,
        test_09_s9_exit_filter_isolates_S12,
        test_10_s11_s12_block_present_with_ki_agent_only_gate,
    ]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} Tests bestanden.")
