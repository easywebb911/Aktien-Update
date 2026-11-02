"""Mock-Tests für redeploy-on-source-change.yml run_phase-Argument.

Hintergrund (13.05.2026): PR #132 hat
``workflow_dispatch.inputs.run_phase`` im daily-squeeze-report.yml auf
``required: true`` gestellt. Der ``redeploy-on-source-change``-Workflow
rief ``gh workflow run`` jedoch ohne ``-f run_phase=...`` auf →
GitHub-API antwortete HTTP 422 und der Auto-Redeploy nach Source-Pushes
schlug fehl (mehrfach an PR-#133/#134-Merges sichtbar).

Fix: Phase clientseitig bestimmen (analog scripts/resolve_run_phase.py +
Client-Logik aus PR #133). Seit 02.11.2026 aus US-Ostküstenzeit:
  - 09:30 ≤ ET < 16:00 → premarket
  - sonst               → postclose
(vorher feste UTC-Grenzen 13:30/20:00 — nur in der Sommerzeit richtig).

Tests:
  1. YAML enthält -f run_phase=... beim gh workflow run
  2. Logik-Replikation: 14:00 UTC → premarket
  3. Logik-Replikation: 22:00 UTC → postclose
  4. Edge: 13:29 UTC → postclose (vor Open)
  5. Edge: 13:30 UTC → premarket (genau Open, inklusiv)
  6. Edge: 20:00 UTC → postclose (genau Close, exklusiv)
  7. Bash-Vergleich nutzt 4-stelliges HHMM (kein versehentliches
     String-Compare statt Integer-Compare)
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


import subprocess  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

_ET = ZoneInfo("America/New_York")


def _phase_for(hour: int, minute: int, *, month: int = 5, day: int = 13) -> str:
    """Pythonische Nachbildung der Bash-Logik im Workflow (UTC-Eingabe,
    Umrechnung in ET wie ``TZ=America/New_York date +%H%M``).

    Bash:
        NOW_HHMM=$(TZ=America/New_York date +%H%M)
        if [ "$NOW_HHMM" -ge 930 ] && [ "$NOW_HHMM" -lt 1600 ]; then
            RUN_PHASE="premarket"
        else
            RUN_PHASE="postclose"
        fi
    Default-Datum 13.05.2026 = Sommerzeit; Winter mit month=11, day=2.
    """
    et = datetime(2026, month, day, hour, minute, tzinfo=timezone.utc).astimezone(_ET)
    hhmm = et.hour * 100 + et.minute
    return "premarket" if 930 <= hhmm < 1600 else "postclose"


def _bash_if_block() -> str:
    yml = (ROOT / ".github" / "workflows" / "redeploy-on-source-change.yml"
           ).read_text(encoding="utf-8")
    m = re.search(r"(if \[ \"\$NOW_HHMM\".*?fi)", yml, re.S)
    assert m, "if-Block mit NOW_HHMM nicht gefunden"
    return "\n".join(line.strip() for line in m.group(1).splitlines())


def _bash_phase(utc_dt: datetime) -> str:
    """Führt die ECHTE Bash-Logik aus dem Workflow aus — mit der ET-Uhrzeit,
    die ``TZ=America/New_York date -d @epoch +%H%M`` für ``utc_dt`` liefert."""
    epoch = int(utc_dt.timestamp())
    script = (f'NOW_HHMM=$(TZ=America/New_York date -d @{epoch} +%H%M)\n'
              + _bash_if_block() + '\necho "$RUN_PHASE"\n')
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
    return out.stdout.strip()


# === 1 — YAML enthält den Fix ==============================================

def test_workflow_yaml_passes_run_phase():
    yml = (ROOT / ".github" / "workflows" / "redeploy-on-source-change.yml"
           ).read_text(encoding="utf-8")
    # gh workflow run mit -f run_phase=... aufgerufen
    assert "-f run_phase=" in yml, (
        "redeploy-on-source-change.yml ruft gh workflow run noch ohne "
        "-f run_phase=... auf — HTTP 422 droht beim nächsten Source-Push")
    # NOW_HHMM-Variable in US-Ostküstenzeit (Fix 02.11.2026)
    assert "TZ=America/New_York date +%H%M" in yml, (
        "ET-Zeit-Bestimmung via `TZ=America/New_York date +%H%M` fehlt im Workflow")
    # Bash-Integer-Vergleich mit den ET-Grenzen
    assert "-ge 930" in yml and "-lt 1600" in yml, (
        "US-Session-Grenzen 930 (Open inkl.) und 1600 (Close exkl.) "
        "fehlen in der Bash-Logik")
    assert "-ge 1330" not in yml and "-lt 2000" not in yml, "alte UTC-Grenzen noch drin"
    # Beide Phasen werden gesetzt
    assert 'RUN_PHASE="premarket"' in yml, "premarket-Branch fehlt"
    assert 'RUN_PHASE="postclose"' in yml, "postclose-Branch fehlt"


# === 2-6 — Spec-Cases (Pythonische Replikation) ============================

def test_us_session_14_00_premarket():
    assert _phase_for(14, 0) == "premarket"


def test_post_close_22_00_postclose():
    assert _phase_for(22, 0) == "postclose"


def test_pre_open_13_29_postclose():
    assert _phase_for(13, 29) == "postclose"


def test_us_open_13_30_premarket():
    assert _phase_for(13, 30) == "premarket"


def test_us_close_20_00_postclose():
    assert _phase_for(20, 0) == "postclose"


# === 7 — Bash-Vergleich-Sanity =============================================

def test_bash_uses_hhmm_integer_format():
    """`%H%M` liefert vierstellige 24-h-Strings wie 0930, 1430, 2200.
    Bash `-ge`/`-lt` arbeiten korrekt damit als Integer-Vergleich. Falls
    jemand auf `%H:%M` umstellt (mit Doppelpunkt) → String-Compare würde
    `09:30 -ge 13:30` fälschlich auswerten.
    """
    yml = (ROOT / ".github" / "workflows" / "redeploy-on-source-change.yml"
           ).read_text(encoding="utf-8")
    # Doppelpunkt im Format-String wäre Bug
    assert "%H:%M" not in yml, (
        "Format %H:%M würde String-Compare statt Integer-Compare auslösen — "
        "%H%M (vierstellig, kein Doppelpunkt) verwenden")
    # Konkret muss `TZ=America/New_York date +%H%M` vorkommen
    assert re.search(r"TZ=America/New_York\s+date\s+\+%H%M", yml), (
        "Exakte Bash-Form `TZ=America/New_York date +%H%M` nicht gefunden")


# === 8 — Winterzeit + echte Bash-Ausführung (Fix 02.11.2026) ================

def test_winter_and_summer_edges_python():
    w = dict(month=11, day=2)
    assert _phase_for(14, 29, **w) == "postclose"
    assert _phase_for(14, 30, **w) == "premarket"
    assert _phase_for(20, 30, **w) == "premarket"
    assert _phase_for(21, 0, **w) == "postclose"
    assert _phase_for(20, 30) == "postclose"


def test_real_bash_logic_both_regimes():
    cases = [
        (datetime(2026, 5, 13, 13, 30, tzinfo=timezone.utc), "premarket"),   # 09:30 EDT
        (datetime(2026, 5, 13, 20, 0, tzinfo=timezone.utc), "postclose"),    # 16:00 EDT
        (datetime(2026, 5, 13, 20, 30, tzinfo=timezone.utc), "postclose"),   # 16:30 EDT
        (datetime(2026, 11, 2, 14, 29, tzinfo=timezone.utc), "postclose"),   # 09:29 EST
        (datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc), "premarket"),   # 09:30 EST
        (datetime(2026, 11, 2, 20, 30, tzinfo=timezone.utc), "premarket"),   # 15:30 EST
        (datetime(2026, 11, 2, 21, 0, tzinfo=timezone.utc), "postclose"),    # 16:00 EST
    ]
    for dt, exp in cases:
        got = _bash_phase(dt)
        assert got == exp, f"{dt.isoformat()}: Bash liefert {got}, erwartet {exp}"


# === Runner =================================================================

def main() -> None:
    tests = [
        ("YAML übergibt -f run_phase=… an gh workflow run",
         test_workflow_yaml_passes_run_phase),
        ("14:00 UTC → premarket",
         test_us_session_14_00_premarket),
        ("22:00 UTC → postclose",
         test_post_close_22_00_postclose),
        ("13:29 UTC → postclose (vor Open)",
         test_pre_open_13_29_postclose),
        ("13:30 UTC → premarket (genau Open, inklusiv)",
         test_us_open_13_30_premarket),
        ("20:00 UTC → postclose (genau Close, exklusiv)",
         test_us_close_20_00_postclose),
        ("Bash-Format %H%M (kein Doppelpunkt → kein String-Compare-Bug)",
         test_bash_uses_hhmm_integer_format),
        ("Winter-/Sommer-Kanten (Python-Nachbildung)",
         test_winter_and_summer_edges_python),
        ("Echte Bash-Logik, beide Zeitregime",
         test_real_bash_logic_both_regimes),
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
