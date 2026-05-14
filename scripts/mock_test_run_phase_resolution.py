"""Mock-Tests für scripts/resolve_run_phase.py (UX-Falle workflow_dispatch).

Hintergrund (13.05.2026): drei manuell-getriggerte Daily-Runs wurden mit
dem damaligen workflow_dispatch-Default `postclose` während laufender
US-Session ausgeführt. Folge: 22 Intraday-Mid-Day-Backtest-Einträge,
bereinigt in PR #131. Dieser Fix entfernt den Default, macht den Input
``required: true`` und führt eine Plausibilitäts-Override-Logik ein.

Test-Matrix (alle Cases im Auftrag):

  1. 14:00 UTC + postclose-Input → wird zu premarket  (US-Session-Override)
  2. 22:00 UTC + premarket-Input → wird zu postclose  (Post-Close-Override)
  3. 14:00 UTC + premarket-Input → bleibt premarket   (plausibel, kein Override)
  4. 22:00 UTC + postclose-Input → bleibt postclose   (plausibel, kein Override)
  5. Cron-Trigger ignoriert die Override-Logik       (festen YAML-Wert nehmen)

Zusatz-Cases:
  6. Edge: 13:29 UTC + postclose → bleibt postclose  (vor US-Open)
  7. Edge: 20:00 UTC + premarket → wird zu postclose (Close-Grenze inkl.)
  8. Empty/garbage Input → premarket-Fallback
  9. CLI-Skript schreibt RUN_PHASE in $GITHUB_ENV

Ausführung: ``python scripts/mock_test_run_phase_resolution.py``
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from resolve_run_phase import resolve_run_phase  # noqa: E402


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 13, hour, minute, 0, tzinfo=timezone.utc)


# === Spec-Cases =============================================================

def test_us_session_postclose_overridden_to_premarket():
    phase, reason = resolve_run_phase(
        event_name="workflow_dispatch",
        schedule=None,
        user_input="postclose",
        now_utc=_at(14, 0),
    )
    assert phase == "premarket", phase
    assert reason == "us_session_override", reason


def test_post_close_premarket_overridden_to_postclose():
    phase, reason = resolve_run_phase(
        event_name="workflow_dispatch",
        schedule=None,
        user_input="premarket",
        now_utc=_at(22, 0),
    )
    assert phase == "postclose", phase
    assert reason == "post_close_override", reason


def test_us_session_premarket_stays_premarket():
    phase, reason = resolve_run_phase(
        event_name="workflow_dispatch",
        schedule=None,
        user_input="premarket",
        now_utc=_at(14, 0),
    )
    assert phase == "premarket", phase
    assert reason is None, reason


def test_post_close_postclose_stays_postclose():
    phase, reason = resolve_run_phase(
        event_name="workflow_dispatch",
        schedule=None,
        user_input="postclose",
        now_utc=_at(22, 0),
    )
    assert phase == "postclose", phase
    assert reason is None, reason


def test_cron_ignores_override_logic_premarket():
    # 10:17-UTC-Cron ist `premarket` per YAML-Definition. Selbst wenn die
    # Cron-Zeit theoretisch im US-Pre-Open liegt, gilt der Cron-Mapping.
    # (Minute-17-Offset gegen GitHub-Actions-Drops zur vollen Stunde.)
    phase, reason = resolve_run_phase(
        event_name="schedule",
        schedule="17 10 * * 1-5",
        user_input=None,
        now_utc=_at(10, 17),
    )
    assert phase == "premarket", phase
    assert reason is None, reason


def test_cron_ignores_override_logic_postclose():
    # 21:17-UTC-Cron ist `postclose`. Diese Zeit liegt nach US-Close — der
    # Override würde hier keinen Schaden anrichten, aber wir wollen
    # konsistente Cron-Semantik (kein Override-Pfad für Schedule-Trigger).
    phase, reason = resolve_run_phase(
        event_name="schedule",
        schedule="17 21 * * 1-5",
        user_input=None,
        now_utc=_at(21, 17),
    )
    assert phase == "postclose", phase
    assert reason is None, reason


# === Edge-Cases =============================================================

def test_pre_us_open_no_override():
    # 13:29 UTC = exakt vor US-Open. postclose bleibt postclose (User
    # könnte z.B. EOD-Konsolidierung der Vortags-Daten triggern wollen).
    phase, reason = resolve_run_phase(
        event_name="workflow_dispatch",
        schedule=None,
        user_input="postclose",
        now_utc=_at(13, 29),
    )
    assert phase == "postclose", phase
    assert reason is None, reason


def test_us_open_boundary_inclusive():
    # 13:30 UTC = US-Open. Override greift ab dieser Minute.
    phase, reason = resolve_run_phase(
        event_name="workflow_dispatch",
        schedule=None,
        user_input="postclose",
        now_utc=_at(13, 30),
    )
    assert phase == "premarket", phase
    assert reason == "us_session_override", reason


def test_us_close_boundary_premarket_overridden():
    # 20:00 UTC = US-Close. premarket wird zu postclose (Daten konsolidieren
    # ab jetzt — Backtest ist sinnvoll).
    phase, reason = resolve_run_phase(
        event_name="workflow_dispatch",
        schedule=None,
        user_input="premarket",
        now_utc=_at(20, 0),
    )
    assert phase == "postclose", phase
    assert reason == "post_close_override", reason


def test_empty_input_falls_back_to_premarket():
    phase, reason = resolve_run_phase(
        event_name="workflow_dispatch",
        schedule=None,
        user_input="",
        now_utc=_at(14, 0),
    )
    assert phase == "premarket", phase
    assert reason == "no_input_fallback", reason


def test_garbage_input_falls_back_to_premarket():
    phase, reason = resolve_run_phase(
        event_name="workflow_dispatch",
        schedule=None,
        user_input="random_garbage",
        now_utc=_at(14, 0),
    )
    assert phase == "premarket", phase
    assert reason == "no_input_fallback", reason


# === CLI-Skript-Smoke-Test ==================================================

def test_cli_writes_run_phase_to_github_env():
    """Das Skript muss RUN_PHASE in $GITHUB_ENV schreiben (Workflow-Vertrag)."""
    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".env", delete=False) as tmp:
        env_file = tmp.name
    try:
        env = os.environ.copy()
        env.update({
            "EVENT_NAME":     "schedule",
            "EVENT_SCHEDULE": "17 21 * * 1-5",
            "USER_INPUT":     "",
            "GITHUB_ENV":     env_file,
        })
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "resolve_run_phase.py")],
            env=env, capture_output=True, text=True, check=True)
        assert "phase=postclose" in proc.stdout, proc.stdout
        with open(env_file, encoding="utf-8") as fh:
            content = fh.read()
        assert "RUN_PHASE=postclose" in content, content
    finally:
        try:
            os.unlink(env_file)
        except OSError:
            pass


# === Runner =================================================================

def main() -> None:
    tests = [
        ("14:00 UTC + postclose → premarket (US-Session-Override)",
         test_us_session_postclose_overridden_to_premarket),
        ("22:00 UTC + premarket → postclose (Post-Close-Override)",
         test_post_close_premarket_overridden_to_postclose),
        ("14:00 UTC + premarket → bleibt premarket",
         test_us_session_premarket_stays_premarket),
        ("22:00 UTC + postclose → bleibt postclose",
         test_post_close_postclose_stays_postclose),
        ("Cron 10:00 → premarket (Override ignoriert)",
         test_cron_ignores_override_logic_premarket),
        ("Cron 21:00 → postclose (Override ignoriert)",
         test_cron_ignores_override_logic_postclose),
        ("Edge 13:29 UTC + postclose → kein Override (vor Open)",
         test_pre_us_open_no_override),
        ("Edge 13:30 UTC + postclose → Override (Open inklusiv)",
         test_us_open_boundary_inclusive),
        ("Edge 20:00 UTC + premarket → Override (Close inklusiv)",
         test_us_close_boundary_premarket_overridden),
        ("Empty Input → premarket-Fallback",
         test_empty_input_falls_back_to_premarket),
        ("Garbage Input → premarket-Fallback",
         test_garbage_input_falls_back_to_premarket),
        ("CLI schreibt RUN_PHASE in $GITHUB_ENV",
         test_cli_writes_run_phase_to_github_env),
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
