"""Mock-Tests für S14 — Gist-Pull-Liveness-Wächter (Schritt 2/2).

Liest ``last_successful_gist_pull`` aus ``gist_pull_state.json`` und meldet
WARN, wenn der Marker > ``HEALTH_CHECK_S14_MAX_AGE_HOURS`` (26 h) alt ist.
Fängt die Stille-Tod-Klasse vom 02.06.2026 (toter GIST_TOKEN → Gist-Read
scheitert über Zeit → Marker altert → Geister-Positionen).

Exakt nach S8-Muster (``mock_test_s8_last_successful_run.py``):
- None-/Fehlende-Datei-/unparsbar-Toleranz → SKIP (kein false-positive).
- tz-aware UTC-Vergleich, naiver Timestamp defensiv als UTC.
- Determinismus: fixer ``now``-Wert (kein ``datetime.now()`` im Vergleich).
- Integration: S14 läuft in BEIDEN Pfaden (daily + ki_agent_only).

Alle Tests nutzen fixe Timestamps → reproduzierbar, kein Zeit-Flackern.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

# Repo-Root in sys.path damit `import health_check` läuft.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import health_check as hc  # noqa: E402


def _write_state(state: dict) -> str:
    """Schreibt State-Dict in temp-Datei, returnt den Pfad."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    return path


# ── Kernverhalten: _gist_pull_age_hours ───────────────────────────────────


def test_01_fresh_marker_small_age():
    """Frischer Marker (2 h her) → kleines Alter, < 26 h → kein WARN."""
    state = {"last_successful_gist_pull": "2026-06-03T12:00:00Z"}
    path = _write_state(state)
    try:
        now = datetime(2026, 6, 3, 14, 0, 0, tzinfo=timezone.utc)
        age = hc._gist_pull_age_hours(now, state_path=path)
        assert age is not None
        assert 1.9 < age < 2.1, f"erwartet ~2h, got {age:.2f}h"
        assert age <= hc.HEALTH_CHECK_S14_MAX_AGE_HOURS
    finally:
        os.unlink(path)


def test_02_stale_marker_over_26h():
    """Marker 28 h her → Alter > 26 h Schwelle → WARN-Bereich."""
    state = {"last_successful_gist_pull": "2026-06-02T08:00:00Z"}
    path = _write_state(state)
    try:
        now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
        age = hc._gist_pull_age_hours(now, state_path=path)
        assert age is not None and age > hc.HEALTH_CHECK_S14_MAX_AGE_HOURS, (
            f"erwartet > 26h (Stille-Tod), got {age:.1f}h"
        )
    finally:
        os.unlink(path)


def test_03_missing_file_returns_none():
    """Datei fehlt (vor erstem Pull) → None (S14 SKIP)."""
    age = hc._gist_pull_age_hours(
        datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc),
        state_path="/nonexistent/gist_pull_state.json",
    )
    assert age is None


def test_04_null_field_returns_none():
    """Feld null (Erstaufsetzen) → None (S14 SKIP)."""
    state = {"last_successful_gist_pull": None}
    path = _write_state(state)
    try:
        age = hc._gist_pull_age_hours(
            datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc),
            state_path=path)
        assert age is None
    finally:
        os.unlink(path)


def test_05_missing_field_returns_none():
    """Datei da, Feld fehlt komplett → None (defensive)."""
    state = {"irgendwas": "anderes"}
    path = _write_state(state)
    try:
        age = hc._gist_pull_age_hours(
            datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc),
            state_path=path)
        assert age is None
    finally:
        os.unlink(path)


def test_06_corrupt_json_returns_none():
    """JSON kaputt → None (fail-soft, S14 SKIP)."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("{broken json")
    try:
        age = hc._gist_pull_age_hours(
            datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc),
            state_path=path)
        assert age is None
    finally:
        os.unlink(path)


def test_07_unparsable_timestamp_returns_none():
    """Nicht-ISO-String → None (defensive)."""
    state = {"last_successful_gist_pull": "not-a-timestamp"}
    path = _write_state(state)
    try:
        age = hc._gist_pull_age_hours(
            datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc),
            state_path=path)
        assert age is None
    finally:
        os.unlink(path)


# ── tz-aware-Sicherheit (fragile Annahme aus dem Auftrag) ──────────────────


def test_08_naive_iso_treated_as_utc():
    """Naiver Marker ohne Z/+00:00 → defensive als UTC, KEIN Crash/Fehlvergl.
    Beweist, dass naiv-vs-aware nicht den 'can't subtract offset-naive and
    offset-aware'-TypeError wirft."""
    state = {"last_successful_gist_pull": "2026-06-03T10:00:00"}  # kein Z
    path = _write_state(state)
    try:
        now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
        age = hc._gist_pull_age_hours(now, state_path=path)
        assert age is not None
        assert 1.9 < age < 2.1, f"erwartet ~2h, got {age:.2f}h"
    finally:
        os.unlink(path)


def test_09_explicit_offset_format_accepted():
    """ISO mit explizitem +00:00 statt Z → akzeptiert."""
    state = {"last_successful_gist_pull": "2026-06-03T10:00:00+00:00"}
    path = _write_state(state)
    try:
        now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
        age = hc._gist_pull_age_hours(now, state_path=path)
        assert age is not None
        assert 1.9 < age < 2.1, f"erwartet ~2h, got {age:.2f}h"
    finally:
        os.unlink(path)


def test_10_real_marker_format_from_pull_gist_data():
    """Reales Marker-Format wie #310 es schreibt
    (``strftime('%Y-%m-%dT%H:%M:%SZ')``) → parsebar, korrektes Alter.
    Mini-Stopp-Absicherung: falls das Format unerwartet wäre, würde dieser
    Test rot."""
    written = datetime(2026, 6, 3, 9, 30, 0, tzinfo=timezone.utc)
    state = {"last_successful_gist_pull":
             written.strftime("%Y-%m-%dT%H:%M:%SZ")}
    path = _write_state(state)
    try:
        now = datetime(2026, 6, 3, 12, 30, 0, tzinfo=timezone.utc)
        age = hc._gist_pull_age_hours(now, state_path=path)
        assert age is not None
        assert 2.9 < age < 3.1, f"erwartet ~3h, got {age:.2f}h"
    finally:
        os.unlink(path)


# ── Integration: S14 in evaluate_state_invariants (beide Pfade) ────────────


def _base_invariant_kwargs() -> dict:
    """Minimal-Setup, das S1-S7/S10 NICHT failen lässt (10 Tickers überall),
    damit nur S14 als Variable isoliert beobachtbar ist."""
    return dict(
        top10_tickers=[f"T{i}" for i in range(10)],
        setup_scores={f"T{i}": 50.0 for i in range(10)},
        monster_scores={f"T{i}": 50.0 for i in range(10)},
        score_history={f"T{i}": [["03.06.2026", 50.0]] for i in range(10)},
        today_iso="2026-06-03",
        agent_signal_keys={f"T{i}" for i in range(10)},
        n_inflation_lines=20,
        n_backtest_appended=0,
        backtest_has_today=True,
        run_phase="postclose",
    )


def test_11_integration_stale_marker_fires_s14_warn():
    """Vorhanden + alt (28 h) → genau 1 S14-Fail, severity warn, Detail
    nennt die Composite-Liveness-Formulierung (NICHT 'Token tot')."""
    state = {"last_successful_gist_pull": "2026-06-02T08:00:00Z"}
    path = _write_state(state)
    try:
        now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
        with mock.patch.object(hc, "GIST_PULL_STATE_FILE", path):
            fails = hc.evaluate_state_invariants(now_utc=now,
                                                 **_base_invariant_kwargs())
        s14 = [f for f in fails if f["id"] == "S14"]
        assert len(s14) == 1, f"erwartet genau 1 S14-Fail, got: {fails}"
        assert s14[0]["severity"] == "warn"
        assert "Gist-Pull seit" in s14[0]["detail"]
        assert "Composite-Liveness" in s14[0]["detail"]
        assert "Token tot" not in s14[0]["detail"], (
            "Detail darf NICHT 'Token tot' behaupten (Composite-Liveness)"
        )
    finally:
        os.unlink(path)


def test_12_integration_fresh_marker_no_s14():
    """Vorhanden + frisch (1 h) → KEIN S14-Fail."""
    state = {"last_successful_gist_pull": "2026-06-03T11:00:00Z"}
    path = _write_state(state)
    try:
        now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
        with mock.patch.object(hc, "GIST_PULL_STATE_FILE", path):
            fails = hc.evaluate_state_invariants(now_utc=now,
                                                 **_base_invariant_kwargs())
        s14 = [f for f in fails if f["id"] == "S14"]
        assert s14 == [], f"frischer Marker darf kein S14 haben: {s14}"
    finally:
        os.unlink(path)


def test_13_integration_missing_file_no_s14():
    """Datei fehlt → S14 SKIP (kein Fail)."""
    now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
    with mock.patch.object(hc, "GIST_PULL_STATE_FILE",
                           "/nonexistent/gist_pull_state.json"):
        fails = hc.evaluate_state_invariants(now_utc=now,
                                             **_base_invariant_kwargs())
    s14 = [f for f in fails if f["id"] == "S14"]
    assert s14 == [], f"fehlende Datei darf kein S14 haben: {s14}"


def test_14_integration_ki_agent_only_runs_s14():
    """S14 läuft AUCH im ki_agent_only-Pfad (beide Pfade, wie S8).
    Stale Marker → S14 feuert trotz ki_agent_only=True."""
    state = {"last_successful_gist_pull": "2026-06-02T08:00:00Z"}
    path = _write_state(state)
    try:
        now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
        with mock.patch.object(hc, "GIST_PULL_STATE_FILE", path):
            fails = hc.evaluate_state_invariants(
                now_utc=now,
                setup_scores={f"T{i}": 50.0 for i in range(10)},
                monster_scores={f"T{i}": 50.0 for i in range(10)},
                ki_agent_only=True,
            )
        s14 = [f for f in fails if f["id"] == "S14"]
        assert len(s14) == 1, (
            f"S14 muss im ki_agent_only-Pfad laufen, got: {fails}"
        )
        assert s14[0]["severity"] == "warn"
    finally:
        os.unlink(path)


# ── Determinismus: gleicher Input → gleiches Ergebnis ──────────────────────


def test_15_deterministic_same_input_same_output():
    """Zweimal identischer (Marker, now) → identisches Alter (kein
    verstecktes Zeit-/Zufallselement)."""
    state = {"last_successful_gist_pull": "2026-06-02T08:00:00Z"}
    path = _write_state(state)
    try:
        now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
        a1 = hc._gist_pull_age_hours(now, state_path=path)
        a2 = hc._gist_pull_age_hours(now, state_path=path)
        assert a1 == a2, f"nicht-deterministisch: {a1} != {a2}"
        assert a1 == 28.0, f"erwartet exakt 28.0h, got {a1}"
    finally:
        os.unlink(path)


# ── Architektur-Invariante: Schreibpfad bleibt #310-exklusiv ──────────────


def test_16_marker_writer_is_pull_gist_data_only():
    """Source-Inspection: außer scripts/pull_gist_data.py darf keine
    Produktions-Datei last_successful_gist_pull SCHREIBEN. Sonst wäre S14
    ein toter Wächter (Feld künstlich frisch trotz Gist-Ausfall)."""
    root = Path(__file__).resolve().parent.parent
    allowed = {"scripts/pull_gist_data.py"}
    bad: list[str] = []
    for p in root.rglob("*.py"):
        rel = p.relative_to(root).as_posix()
        if rel.startswith("scripts/mock_test_") or rel == "health_check.py":
            continue
        if rel in allowed:
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for line_no, line in enumerate(txt.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            # Schreib-Pattern: ...["last_successful_gist_pull"] = ...
            if ('"last_successful_gist_pull"' in line
                    and "=" in line and "==" not in line
                    and "json.dumps" not in line):
                bad.append(f"{rel}:{line_no}: {line.strip()}")
    assert not bad, (
        "Unzulässige Schreib-Stellen für last_successful_gist_pull:\n  "
        + "\n  ".join(bad)
    )


def test_17_source_s14_reads_correct_field():
    """_gist_pull_age_hours liest last_successful_gist_pull (nicht ein
    fremdes Feld), und der S14-Block existiert in evaluate_state_invariants."""
    src = (Path(__file__).resolve().parent.parent
           / "health_check.py").read_text(encoding="utf-8")
    assert '"last_successful_gist_pull"' in src
    start = src.find("def _gist_pull_age_hours(")
    assert start >= 0, "_gist_pull_age_hours fehlt"
    end = src.find("\n\ndef ", start + 1)
    body = src[start:end] if end > 0 else src[start:]
    assert "last_successful_gist_pull" in body
    # S14-Block in evaluate_state_invariants
    assert '"id": "S14"' in src, "S14-Fail-Block fehlt"
    assert "HEALTH_CHECK_S14_MAX_AGE_HOURS" in src


# ── Runner ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    tests = [
        test_01_fresh_marker_small_age,
        test_02_stale_marker_over_26h,
        test_03_missing_file_returns_none,
        test_04_null_field_returns_none,
        test_05_missing_field_returns_none,
        test_06_corrupt_json_returns_none,
        test_07_unparsable_timestamp_returns_none,
        test_08_naive_iso_treated_as_utc,
        test_09_explicit_offset_format_accepted,
        test_10_real_marker_format_from_pull_gist_data,
        test_11_integration_stale_marker_fires_s14_warn,
        test_12_integration_fresh_marker_no_s14,
        test_13_integration_missing_file_no_s14,
        test_14_integration_ki_agent_only_runs_s14,
        test_15_deterministic_same_input_same_output,
        test_16_marker_writer_is_pull_gist_data_only,
        test_17_source_s14_reads_correct_field,
    ]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} Tests bestanden.")
