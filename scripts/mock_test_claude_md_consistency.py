"""Mock-Tests fuer CLAUDE.md-Konsistenz nach Session 16.05.2026.

Hintergrund: Doku-only-Update um etablierte Patterns und Regeln nach
einer produktiven Session (16 PRs) konsistent in CLAUDE.md zu halten.

Tests:
  1. Auto-Merge-Regel-Sektion existiert
  2. Auto-Merge-Regel-Update 16.05.: Subagent ist Bonus, kein Gatekeeper
  3. Padding-Skalierungs-Pattern dokumentiert (em statt px)
  4. .details-body und .news-panel in der Skalierungs-Sektion erwähnt
  5. KI-Agent-Coverage-Sektion erwähnt parse_monitored_tickers
  6. Conviction-Coverage Phase 1 dokumentiert
  7. Score-Delta T-1 Sektion vorhanden mit Stille-Schwelle
  8. Konfidenz-Wasserzeichen Phase 2 (Hybrid-Ansatz) dokumentiert
  9. Knaller-Trade-Label P90/P10 + Badge-Pattern dokumentiert
 10. Tier-3 success_check Recalibration in CLAUDE.md
 11. Methodik-Panel-Accordion-Sektion vorhanden (Konfidenz default-open)
 12. Health-Check S8 in der State-Invariants-Liste
 13. RVOL-Normalisierung Phase 1 (Helper + Flag OFF) dokumentiert
 14. RVOL-Definitionen erklären rvol_4d vs rvol_20d
 15. Process-Anker-Sektion (Vorsichts-Prinzip, Trading-Wert-Filter,
     Zeit-Schätzung, Uhrzeit-Regel)
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def test_01_auto_merge_section() -> None:
    assert "## Git-Workflow (PR-only)" in CMD
    assert "Auto-Merge-Regel" in CMD


def test_02_subagent_is_bonus_not_gatekeeper() -> None:
    # Neue Klarstellung 16.05.2026
    assert "Bonus" in CMD and ("kein Gatekeeper" in CMD or "Gatekeeper" in CMD), \
        "Subagent-Bonus-Klarstellung fehlt in CLAUDE.md"
    assert "finalisiert 16.05.2026" in CMD or "Verfeinerung 16.05.2026" in CMD, \
        "Datum-Marker der Verfeinerung fehlt"


def test_03_padding_em_pattern() -> None:
    # em-Padding für aufklappbare Mobile-Container
    assert "Schriftgrößen-Skalierung" in CMD, \
        "Skalierungs-Sektion fehlt"
    assert "padding-bottom: max(3em" in CMD or "0.7em 14px" in CMD or "0.8em" in CMD, \
        "em-Padding-Beispiel fehlt"


def test_04_details_news_in_scaling_section() -> None:
    # PR #181 Stellen erwähnt
    assert ".details-body" in CMD or ".news-panel" in CMD, \
        "Details-Tabelle / News-Panel in Skalierungs-Sektion fehlen"


def test_05_ki_agent_coverage_pool() -> None:
    # Phase 2 KI-Agent-Coverage
    assert "parse_monitored_tickers" in CMD, \
        "parse_monitored_tickers nicht in CLAUDE.md"
    assert "Top-10" in CMD and ("Watchlist" in CMD or "watchlist" in CMD)


def test_06_conviction_coverage_phase1() -> None:
    # apply_conviction_scores für Watchlist-Outsider
    assert ("Watchlist-Outsider" in CMD or "_wl_outsiders_for_pool" in CMD), \
        "Conviction-Coverage Phase 1 fehlt"


def test_07_score_delta_t1() -> None:
    assert "Score-Delta T-1" in CMD, "Score-Delta T-1 Sektion fehlt"
    assert "Stille-Schwelle" in CMD or "|Δ| < 2" in CMD, \
        "Stille-Schwelle nicht dokumentiert"


def test_08_konfidenz_watermark_phase2() -> None:
    assert "Hybrid-Wasserzeichen" in CMD or "Wasserzeichen" in CMD, \
        "Wasserzeichen Phase 2 fehlt"
    assert "gepunktet" in CMD or "underline dotted" in CMD or \
           "Color-Blind-safe" in CMD or "Color-Blind-sicher" in CMD


def test_09_knaller_label_pattern() -> None:
    assert "Knaller-Trade-Label" in CMD or "Knaller-Hit" in CMD, \
        "Knaller-Sektion fehlt"
    assert "P90" in CMD or "Top 10%" in CMD


def test_10_tier3_success_check_recalibration() -> None:
    assert "Tier-3-success_check-Recalibration" in CMD or \
           "r is not None" in CMD, \
        "Tier-3 success_check Recalibration fehlt"


def test_11_methodology_accordion() -> None:
    assert "Accordion-Redesign" in CMD or "methodology-card" in CMD, \
        "Methodik-Accordion fehlt"
    # Konfidenz default-open
    assert "default-open" in CMD or "default-OPEN" in CMD or \
           "details open" in CMD or "default open" in CMD


def test_12_health_check_s8() -> None:
    assert "S8" in CMD, "S8 nicht in Health-Check-Liste"
    assert "HEALTH_CHECK_S8_MAX_AGE_HOURS" in CMD or \
           "Digest-Push-Pipeline" in CMD, \
        "S8-Beschreibung fehlt"


def test_13_rvol_normalization_phase1() -> None:
    assert "RVOL-Normalisierung" in CMD, "RVOL-Normalisierung-Sektion fehlt"
    assert "RVOL_NORMALIZATION_ENABLED" in CMD
    assert "PR-α" in CMD or "PR-alpha" in CMD or "Phase 1" in CMD


def test_14_rvol_definitions_4d_vs_20d() -> None:
    assert "rvol_4d" in CMD and "rvol_20d" in CMD, \
        "rvol_4d / rvol_20d Disambiguation fehlt"


def test_15_process_anchors_section() -> None:
    # Neue Sektion "Arbeits-Regeln" mit 4 Anker-Prinzipien
    assert "Arbeits-Regeln" in CMD or "Process-Anker" in CMD, \
        "Process-Anker-Sektion fehlt"
    assert "Vorsichts-Prinzip" in CMD
    assert "Trading-Wert-Filter" in CMD
    assert "Zeit-Schätzungs-Regel" in CMD
    assert "Uhrzeit-Regel" in CMD


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 Auto-Merge-Regel-Sektion",                  test_01_auto_merge_section),
        ("02 Subagent ist Bonus (16.05. Update)",        test_02_subagent_is_bonus_not_gatekeeper),
        ("03 em-Padding-Pattern dokumentiert",           test_03_padding_em_pattern),
        ("04 .details-body / .news-panel erwähnt",       test_04_details_news_in_scaling_section),
        ("05 KI-Agent-Coverage parse_monitored_tickers", test_05_ki_agent_coverage_pool),
        ("06 Conviction-Coverage Phase 1",               test_06_conviction_coverage_phase1),
        ("07 Score-Delta T-1 + Stille-Schwelle",         test_07_score_delta_t1),
        ("08 Konfidenz-Wasserzeichen Phase 2",           test_08_konfidenz_watermark_phase2),
        ("09 Knaller-Trade-Label P90 + Badge",           test_09_knaller_label_pattern),
        ("10 Tier-3 success_check Recalibration",        test_10_tier3_success_check_recalibration),
        ("11 Methodik-Panel Accordion-Redesign",         test_11_methodology_accordion),
        ("12 Health-Check S8 in State-Invariants",       test_12_health_check_s8),
        ("13 RVOL-Normalisierung Phase 1",               test_13_rvol_normalization_phase1),
        ("14 RVOL-Definitionen rvol_4d vs 20d",          test_14_rvol_definitions_4d_vs_20d),
        ("15 Process-Anker (4 Prinzipien)",              test_15_process_anchors_section),
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
