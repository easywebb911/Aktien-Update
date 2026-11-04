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
  7. Edge (seit 04.11.2026): 20:00/20:19 UTC (16:00/16:19 EDT) + premarket →
     bleibt premarket; 20:20 UTC (16:20 EDT, finaler Schluss) → postclose.
  8. Empty/garbage Input → premarket-Fallback
  9. CLI-Skript schreibt RUN_PHASE in $GITHUB_ENV
 10.–15. Winterzeit (14:30/21:00 UTC), Kanten, Umstellungstage (Fix 02.11.2026)

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
    # 06:17-UTC-Cron ist `premarket` per YAML-Definition. Selbst wenn die
    # Cron-Zeit theoretisch im US-Pre-Open liegt, gilt der Cron-Mapping.
    # (Minute-17-Offset gegen GitHub-Actions-Drops zur vollen Stunde.)
    phase, reason = resolve_run_phase(
        event_name="schedule",
        schedule="17 6 * * 1-5",
        user_input=None,
        now_utc=_at(6, 17),
    )
    assert phase == "premarket", phase
    assert reason is None, reason


def test_cron_ignores_override_logic_postclose():
    # 21:37-UTC-Cron (seit 04.11.2026) ist `postclose` — kein Override-Pfad
    # für Schedule-Trigger. Der alte String "17 21" bleibt für den Übergang
    # postclose (bereits eingereihter Lauf).
    for sched in ("37 21 * * 1-5", "17 21 * * 1-5"):
        phase, reason = resolve_run_phase(
            event_name="schedule",
            schedule=sched,
            user_input=None,
            now_utc=_at(21, 37),
        )
        assert phase == "postclose", (sched, phase)
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
    # Seit 04.11.2026: Postclose-Grenze = finaler Schluss 16:20 ET
    # (trading_date.US_CLOSE_FINAL_ET). Sommer (EDT): 20:00/20:19 UTC =
    # 16:00/16:19 ET → premarket bleibt; postclose wird zu premarket.
    # 20:20 UTC = 16:20 ET → premarket wird zu postclose.
    def d(inp, h, m):
        return resolve_run_phase(event_name="workflow_dispatch", schedule=None,
                                 user_input=inp, now_utc=_at(h, m))
    assert d("premarket", 20, 0) == ("premarket", None)
    assert d("premarket", 20, 19) == ("premarket", None)
    assert d("postclose", 20, 0) == ("premarket", "close_not_final_override")
    assert d("postclose", 20, 19) == ("premarket", "close_not_final_override")
    assert d("premarket", 20, 20) == ("postclose", "post_close_override")
    assert d("postclose", 20, 20) == ("postclose", None)


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


# === Winterzeit / Umstellungstage (Fix 02.11.2026: Grenzen in US/Eastern) ===
# Sommer (EDT, UTC-4): Open 13:30 UTC, Close 20:00 UTC.
# Winter (EST, UTC-5): Open 14:30 UTC, Close 21:00 UTC.
# Umstellung 2026: Beginn So 08.03., Ende So 01.11.

def _d(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, 0, tzinfo=timezone.utc)


def _disp(choice, when):
    return resolve_run_phase(event_name="workflow_dispatch", schedule=None,
                             user_input=choice, now_utc=when)


def test_winter_2030_postclose_is_overridden():
    # 20:30 UTC im Winter = 15:30 ET → Session läuft → Override auf premarket.
    assert _disp("postclose", _d(2026, 11, 2, 20, 30)) == ("premarket", "us_session_override")


def test_summer_2030_postclose_not_overridden():
    # 20:30 UTC im Sommer = 16:30 ET → nach Close → postclose bleibt.
    assert _disp("postclose", _d(2026, 7, 15, 20, 30)) == ("postclose", None)


def test_winter_open_and_close_edges():
    assert _disp("postclose", _d(2026, 11, 2, 14, 29)) == ("postclose", None)          # 09:29 ET
    assert _disp("postclose", _d(2026, 11, 2, 14, 30)) == ("premarket", "us_session_override")  # 09:30 ET
    assert _disp("postclose", _d(2026, 11, 2, 20, 59)) == ("premarket", "us_session_override")  # 15:59 ET
    assert _disp("premarket", _d(2026, 11, 2, 21, 0)) == ("premarket", None)                    # 16:00 ET
    assert _disp("postclose", _d(2026, 11, 2, 21, 19)) == ("premarket", "close_not_final_override")  # 16:19 ET
    assert _disp("premarket", _d(2026, 11, 2, 21, 20)) == ("postclose", "post_close_override")  # 16:20 ET
    assert _disp("postclose", _d(2026, 11, 2, 21, 20)) == ("postclose", None)                   # 16:20 ET
    assert _disp("premarket", _d(2026, 11, 2, 20, 59)) == ("premarket", None)


def test_winter_1400_postclose_not_overridden():
    # 14:00 UTC im Winter = 09:00 ET → vor Open → User-Wahl bleibt.
    assert _disp("postclose", _d(2026, 11, 2, 14, 0)) == ("postclose", None)


def test_dst_switch_days():
    # Fr 30.10. (noch EDT): 20:30 UTC = 16:30 ET → nach Close.
    assert _disp("postclose", _d(2026, 10, 30, 20, 30)) == ("postclose", None)
    # Mo 02.11. (erster Handelstag EST): 20:30 UTC = 15:30 ET → Session.
    assert _disp("postclose", _d(2026, 11, 2, 20, 30)) == ("premarket", "us_session_override")
    # Fr 06.03. (noch EST): 14:00 UTC = 09:00 ET → vor Open.
    assert _disp("postclose", _d(2026, 3, 6, 14, 0)) == ("postclose", None)
    # Mo 09.03. (erster Handelstag EDT): 14:00 UTC = 10:00 ET → Session.
    assert _disp("postclose", _d(2026, 3, 9, 14, 0)) == ("premarket", "us_session_override")


def test_cron_still_ignores_override_in_winter():
    p, r = resolve_run_phase(event_name="schedule", schedule="37 21 * * 1-5",
                             user_input=None, now_utc=_d(2026, 11, 2, 20, 30))
    assert (p, r) == ("postclose", None)


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
            "EVENT_SCHEDULE": "37 21 * * 1-5",
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
        ("Cron 21:37 (+ alter 21:17 Übergang) → postclose (Override ignoriert)",
         test_cron_ignores_override_logic_postclose),
        ("Edge 13:29 UTC + postclose → kein Override (vor Open)",
         test_pre_us_open_no_override),
        ("Edge 13:30 UTC + postclose → Override (Open inklusiv)",
         test_us_open_boundary_inclusive),
        ("Edge 16:00/16:19/16:20 EDT (finaler Schluss 16:20 inklusiv)",
         test_us_close_boundary_premarket_overridden),
        ("Empty Input → premarket-Fallback",
         test_empty_input_falls_back_to_premarket),
        ("Garbage Input → premarket-Fallback",
         test_garbage_input_falls_back_to_premarket),
        ("CLI schreibt RUN_PHASE in $GITHUB_ENV",
         test_cli_writes_run_phase_to_github_env),
        ("Winter 20:30 UTC + postclose → Override (15:30 ET)",
         test_winter_2030_postclose_is_overridden),
        ("Sommer 20:30 UTC + postclose → kein Override (16:30 ET)",
         test_summer_2030_postclose_not_overridden),
        ("Winter Kanten 14:29/14:30/20:59/21:00/21:19/21:20 UTC",
         test_winter_open_and_close_edges),
        ("Winter 14:00 UTC + postclose → kein Override (09:00 ET)",
         test_winter_1400_postclose_not_overridden),
        ("Umstellungstage März/November",
         test_dst_switch_days),
        ("Cron im Winter ignoriert Override",
         test_cron_still_ignores_override_in_winter),
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
