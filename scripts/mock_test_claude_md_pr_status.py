"""Mock-Tests fuer CLAUDE.md PR-Status-Meldungs-Sektion (17.05.2026).

Hintergrund: Aktien-Update-Repo hat keine CI-Workflows fuer PR-
Validation. Claude hat aber nach jedem PR-Push gemeldet "Warte auf
Webhook-Events", die nie kommen. Easy musste explizit zum Merge
auffordern.

Fix: CLAUDE.md-Regel zementiert "Ready for Merge"-Meldung statt
Webhook-Warten. Code liest CLAUDE.md beim Session-Start und folgt
dem Pattern.

Tests:
  1. Sub-Sektion "PR-Status-Meldung nach Push" in CLAUDE.md
  2. Hinweis dass Repo KEINE CI-Workflows fuer PR-Validation hat
  3. Regel "Ready for Merge" als Klassifikation dokumentiert
  4. Explizite "Was Claude NICHT mehr melden soll"-Liste
  5. Subscribe-pr-activity-Ausnahme dokumentiert
  6. Sektion ist im Auto-Merge-Bereich (nicht z.B. unter Lint-Regeln)
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def test_01_pr_status_section_exists() -> None:
    assert "### PR-Status-Meldung nach Push" in CMD, \
        "Sub-Sektion 'PR-Status-Meldung nach Push' fehlt in CLAUDE.md"


def test_02_no_ci_workflows_hint() -> None:
    # Klare Begruendung warum Webhook-Warten sinnlos ist
    assert "keine GitHub-Actions-CI-Workflows" in CMD or \
           "keine CI-Workflows" in CMD, \
        "Hinweis auf fehlende CI-Workflows fehlt"


def test_03_ready_for_merge_rule() -> None:
    assert "ready for merge" in CMD.lower(), \
        "'Ready for Merge'-Klassifikation nicht dokumentiert"


def test_04_dont_meld_webhook_events() -> None:
    # Explizite Negativliste
    assert "Warte auf Webhook-Events" in CMD, \
        "Negativliste 'Warte auf Webhook-Events' fehlt"
    assert "CI läuft" in CMD or "Es gibt keine CI" in CMD or \
           "es gibt keine CI-Workflows" in CMD, \
        "'CI laeuft' als unzulaessige Meldung nicht aufgefuehrt"


def test_05_subscribe_pr_activity_exception() -> None:
    assert "subscribe_pr_activity" in CMD, \
        "subscribe_pr_activity-Ausnahme fehlt"
    assert "Review-Comment" in CMD or "review-comment" in CMD.lower(), \
        "Review-Comment-Webhooks-Hinweis fehlt"


def test_06_section_in_auto_merge_area() -> None:
    # Sektion sollte VOR der Template-Sicherheitsregel kommen
    # (im Auto-Merge-Workflow-Bereich)
    idx_pr_status = CMD.find("### PR-Status-Meldung nach Push")
    idx_template_rule = CMD.find("## generate_report.py — Template-Sicherheitsregel")
    assert idx_pr_status > 0
    assert idx_template_rule > 0
    assert idx_pr_status < idx_template_rule, \
        "Sub-Sektion liegt im falschen Bereich (sollte vor Template-Regel)"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 PR-Status-Sektion existiert",         test_01_pr_status_section_exists),
        ("02 Hinweis 'keine CI-Workflows'",         test_02_no_ci_workflows_hint),
        ("03 'Ready for Merge'-Regel",              test_03_ready_for_merge_rule),
        ("04 Negativliste 'Webhook-Events'",        test_04_dont_meld_webhook_events),
        ("05 subscribe_pr_activity-Ausnahme",       test_05_subscribe_pr_activity_exception),
        ("06 Sektion im Auto-Merge-Bereich",        test_06_section_in_auto_merge_area),
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
