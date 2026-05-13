"""Mock-Tests für redeploy-on-source-change.yml run_phase-Argument.

Hintergrund (13.05.2026): PR #132 hat
``workflow_dispatch.inputs.run_phase`` im daily-squeeze-report.yml auf
``required: true`` gestellt. Der ``redeploy-on-source-change``-Workflow
rief ``gh workflow run`` jedoch ohne ``-f run_phase=...`` auf →
GitHub-API antwortete HTTP 422 und der Auto-Redeploy nach Source-Pushes
schlug fehl (mehrfach an PR-#133/#134-Merges sichtbar).

Fix: Phase clientseitig aus aktueller UTC-Zeit bestimmen (analog
scripts/resolve_run_phase.py + Client-Logik aus PR #133):
  - 13:30 ≤ UTC < 20:00 → premarket
  - sonst                → postclose

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


def _phase_for(hour: int, minute: int) -> str:
    """Pythonische Nachbildung der Bash-Logik im Workflow.

    Bash:
        NOW_HHMM=$(date -u +%H%M)
        if [ "$NOW_HHMM" -ge 1330 ] && [ "$NOW_HHMM" -lt 2000 ]; then
            RUN_PHASE="premarket"
        else
            RUN_PHASE="postclose"
        fi
    """
    hhmm = hour * 100 + minute
    return "premarket" if 1330 <= hhmm < 2000 else "postclose"


# === 1 — YAML enthält den Fix ==============================================

def test_workflow_yaml_passes_run_phase():
    yml = (ROOT / ".github" / "workflows" / "redeploy-on-source-change.yml"
           ).read_text(encoding="utf-8")
    # gh workflow run mit -f run_phase=... aufgerufen
    assert "-f run_phase=" in yml, (
        "redeploy-on-source-change.yml ruft gh workflow run noch ohne "
        "-f run_phase=... auf — HTTP 422 droht beim nächsten Source-Push")
    # NOW_HHMM-Variable für UTC-Zeit-Berechnung
    assert "date -u +%H%M" in yml, (
        "UTC-Zeit-Bestimmung via `date -u +%H%M` fehlt im Workflow")
    # Bash-Integer-Vergleich mit den richtigen Grenzen
    assert "-ge 1330" in yml and "-lt 2000" in yml, (
        "US-Session-Grenzen 1330 (Open inkl.) und 2000 (Close exkl.) "
        "fehlen in der Bash-Logik")
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
    # Konkret muss `date -u +%H%M` vorkommen
    assert re.search(r"date\s+-u\s+\+%H%M", yml), (
        "Exakte Bash-Form `date -u +%H%M` nicht gefunden")


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
