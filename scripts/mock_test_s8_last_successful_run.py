"""Mock-Tests für S8 — Referenz-Wechsel von last_digest_sent (Mitternacht-UTC)
auf last_successful_run (echter ISO-Timestamp).

Hintergrund (Diagnose 29.05.2026): vorher las S8 ``last_digest_sent``
(YYYY-MM-DD) und nahm Mitternacht UTC als Referenz. Bei stabilem Cron-Drift
(Digest fährt ~12:00 UTC durch statt 08:47 UTC) erzeugte das einen ~12 h
Bias → täglicher false-positive S8-warn am Vormittag (35.7 h gemessen statt
echte 23.6 h).

Tests prüfen:
- Stabile Cron-Drift (Push 24 h zurück) → KEIN warn (Alter < 26 h).
- Echter Ausfall (Push >26 h zurück) → warn.
- None / fehlendes Feld → skip (kein false-positive).
- Naiver Timestamp (ohne Z) → defensive Behandlung als UTC.
- Schwester-Feld ``last_digest_sent`` (alt) wird NICHT mehr gelesen.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Repo-Root in sys.path damit `import health_check` läuft.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import health_check as hc  # noqa: E402


def _write_state(state: dict) -> str:
    """Schreibt State-Dict in temp-Datei, returnt den Pfad."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    return path


# ── Kernverhalten ─────────────────────────────────────────────────────────


def test_01_recent_push_within_24h_no_warn():
    """Stabile Cron-Drift: Push 23.6h her (28.05 12:04Z → 29.05 11:41Z) →
    KEIN warn (Alter < 26 h). Genau das Szenario aus der 29.05.-Diagnose."""
    state = {"last_successful_run": "2026-05-28T12:04:26Z"}
    path = _write_state(state)
    try:
        now = datetime(2026, 5, 29, 11, 41, 27, tzinfo=timezone.utc)
        age = hc._digest_age_hours(now, state_path=path)
        assert age is not None
        assert 23.0 < age < 24.0, (
            f"erwartet ~23.6h, got {age:.1f}h — Bias durch Mitternacht-"
            f"Konvention nicht behoben?"
        )
    finally:
        os.unlink(path)


def test_02_real_outage_over_26h_triggers_warn():
    """Echter Ausfall: Push 28 h her → Alter > 26 h Schwelle → warn."""
    state = {"last_successful_run": "2026-05-28T08:00:00Z"}
    path = _write_state(state)
    try:
        now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
        age = hc._digest_age_hours(now, state_path=path)
        assert age is not None and age > 26.0, (
            f"erwartet > 26h (echter Ausfall), got {age:.1f}h"
        )
    finally:
        os.unlink(path)


def test_03_missing_file_returns_none():
    """Datei fehlt → None (S8 skip beim Erstaufsetzen)."""
    age = hc._digest_age_hours(
        datetime.now(timezone.utc),
        state_path="/nonexistent/digest_state.json",
    )
    assert age is None


def test_04_missing_field_returns_none():
    """Datei da, Feld None → None (Erstaufsetzen vor erstem erfolgreichem Run)."""
    state = {"last_successful_run": None,
             "last_digest_sent": None}
    path = _write_state(state)
    try:
        age = hc._digest_age_hours(
            datetime.now(timezone.utc), state_path=path)
        assert age is None
    finally:
        os.unlink(path)


def test_05_corrupt_json_returns_none():
    """JSON kaputt → None (defensive Fail-soft, S8 skip)."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("{broken json")
    try:
        age = hc._digest_age_hours(
            datetime.now(timezone.utc), state_path=path)
        assert age is None
    finally:
        os.unlink(path)


def test_06_unparsable_timestamp_returns_none():
    """Nicht-ISO-String → None (defensive Fail-soft)."""
    state = {"last_successful_run": "not-a-timestamp"}
    path = _write_state(state)
    try:
        age = hc._digest_age_hours(
            datetime.now(timezone.utc), state_path=path)
        assert age is None
    finally:
        os.unlink(path)


# ── Referenz-Wechsel ist wirksam ──────────────────────────────────────────


def test_07_old_field_last_digest_sent_no_longer_consulted():
    """``last_digest_sent`` (YYYY-MM-DD) wird NICHT mehr gelesen — selbst
    wenn es einen alten Wert enthält, muss S8 ``last_successful_run`` als
    Quelle nutzen. Bei nur altem Feld → None."""
    state = {"last_digest_sent": "2026-05-28"}  # ohne last_successful_run
    path = _write_state(state)
    try:
        age = hc._digest_age_hours(
            datetime(2026, 5, 29, 11, 41, tzinfo=timezone.utc),
            state_path=path,
        )
        assert age is None, (
            f"S8 darf last_digest_sent NICHT mehr lesen, got age={age}"
        )
    finally:
        os.unlink(path)


def test_08_29_05_real_state_no_warn():
    """Reproduziert den 29.05. NACH dem 11:41Z-Push (aktueller Stand auf
    main): last_successful_run ist genau die Push-Zeit. Alter ~0 h → kein
    warn. Vorher (mit last_digest_sent + Mitternacht-Bias) hätte S8 erst
    nach mehreren Stunden < 26 h gefallen sein."""
    state = {
        "last_successful_run": "2026-05-29T11:41:27Z",
        "last_digest_sent": "2026-05-29",
    }
    path = _write_state(state)
    try:
        now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
        age = hc._digest_age_hours(now, state_path=path)
        assert age is not None and age < 1.0, (
            f"erwartet ~0.3h, got {age:.2f}h"
        )
    finally:
        os.unlink(path)


# ── Defensive Edge-Cases ──────────────────────────────────────────────────


def test_09_naive_iso_treated_as_utc():
    """Naiver Timestamp ohne Z/+00:00 → defensive als UTC interpretieren."""
    state = {"last_successful_run": "2026-05-29T10:00:00"}  # kein Z
    path = _write_state(state)
    try:
        now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
        age = hc._digest_age_hours(now, state_path=path)
        assert age is not None
        assert 1.9 < age < 2.1, f"erwartet ~2h, got {age:.2f}h"
    finally:
        os.unlink(path)


def test_10_explicit_offset_format_accepted():
    """ISO mit explizitem +00:00 statt Z → akzeptiert."""
    state = {"last_successful_run": "2026-05-29T10:00:00+00:00"}
    path = _write_state(state)
    try:
        now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
        age = hc._digest_age_hours(now, state_path=path)
        assert age is not None
        assert 1.9 < age < 2.1, f"erwartet ~2h, got {age:.2f}h"
    finally:
        os.unlink(path)


# ── Architektur-Invariante: kein Fremd-Schreibpfad ────────────────────────


def test_11_no_external_writer_of_last_successful_run():
    """Source-Inspection: außer scripts/health_check_digest.py darf keine
    Produktions-Datei das Feld schreiben. Wenn ein anderer Pfad das Feld
    aktualisieren würde, wäre S8 nach diesem Wechsel ein toter Wächter
    (Feld dauerhaft frisch trotz Digest-Ausfall)."""
    root = Path(__file__).resolve().parent.parent
    allowed = {"scripts/health_check_digest.py"}
    bad: list[str] = []
    for p in root.rglob("*.py"):
        rel = p.relative_to(root).as_posix()
        # Tests + Health-Check selbst (nur Lese-Pfad) erlaubt
        if rel.startswith("scripts/mock_test_") or rel == "health_check.py":
            continue
        if rel in allowed:
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        # Schreib-Pattern: state["last_successful_run"] = ...
        if 'state["last_successful_run"]' in txt and "=" in txt:
            for line_no, line in enumerate(txt.splitlines(), 1):
                if 'last_successful_run' in line and '=' in line and '==' not in line:
                    if not line.lstrip().startswith("#"):
                        bad.append(f"{rel}:{line_no}: {line.strip()}")
    assert not bad, (
        "Unzulässige Schreib-Stellen für last_successful_run gefunden — "
        "S8-Referenz-Wechsel kompromittiert:\n  " + "\n  ".join(bad)
    )


# ── Source-Inspection: Wechsel wirklich vollzogen ────────────────────────


def test_12_source_uses_last_successful_run():
    """_digest_age_hours muss last_successful_run lesen, nicht last_digest_sent."""
    src = (Path(__file__).resolve().parent.parent
           / "health_check.py").read_text(encoding="utf-8")
    # _digest_age_hours-Funktions-Bereich extrahieren (defensive Heuristik)
    start = src.find("def _digest_age_hours(")
    assert start >= 0
    end = src.find("\n\ndef ", start + 1)
    body = src[start:end] if end > 0 else src[start:]
    assert 'state.get("last_successful_run")' in body, (
        "_digest_age_hours liest nicht last_successful_run!"
    )
    assert 'state.get("last_digest_sent")' not in body, (
        "_digest_age_hours liest noch last_digest_sent — Referenz-Wechsel "
        "unvollständig!"
    )


# ── Runner ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    tests = [
        test_01_recent_push_within_24h_no_warn,
        test_02_real_outage_over_26h_triggers_warn,
        test_03_missing_file_returns_none,
        test_04_missing_field_returns_none,
        test_05_corrupt_json_returns_none,
        test_06_unparsable_timestamp_returns_none,
        test_07_old_field_last_digest_sent_no_longer_consulted,
        test_08_29_05_real_state_no_warn,
        test_09_naive_iso_treated_as_utc,
        test_10_explicit_offset_format_accepted,
        test_11_no_external_writer_of_last_successful_run,
        test_12_source_uses_last_successful_run,
    ]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} Tests bestanden.")
