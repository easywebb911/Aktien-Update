#!/usr/bin/env python3
"""Allowlist-Runner für die deterministischen (Kategorie-A) Mock-Tests.

Phase-2-Gate-Ausbau: bündelt die datums-/netz-stabilen ``mock_test_*.py``
in EINEM CI-Step (``.github/workflows/pr-checks.yml``), statt ~79 einzelne
yml-Steps zu pflegen.

KERN-PRINZIP — EXPLIZITE ALLOWLIST, KEIN Laufzeit-Glob für die Auswahl:
Welche Tests gefahren werden, steht als STATISCHE Liste ``ALLOWLIST`` unten.
Ein neuer Test (besonders ein data-flaky-B- oder yfinance-ENV-Test) läuft
NICHT automatisch mit — er muss bewusst in ``ALLOWLIST`` (gate-safe) oder
``EXCLUDED`` (mit Grund) eingetragen werden. Glob wird AUSSCHLIESSLICH im
Drift-Guard verwendet (Konsistenz-Prüfung), nie zur Test-Auswahl.

DRIFT-GUARD (vor den Test-Läufen): jeder vorhandene ``mock_test_*.py`` MUSS
in ALLOWLIST ODER EXCLUDED stehen. Ein unklassifizierter Test → der Runner
failt SOFORT mit dem Namen, damit „neuen Test vergessen einzuordnen" laut
statt still wird (kein stiller Schutz-Verlust).

CI-Install-Vertrag: die ALLOWLIST-Tests laufen auf ``stdlib + jinja2 +
pyyaml`` (siehe pr-checks.yml). yfinance-Importer stehen in EXCLUDED;
generate_report-Importer in der ALLOWLIST stubben yfinance selbst.

Ausführung: ``python scripts/run_ci_mock_tests.py``. Exit 0 = alle grün,
Exit 1 = mind. ein Test rot ODER Drift erkannt.
"""
from __future__ import annotations

import glob
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# ── ALLOWLIST (77) — abgeleitet zur Bauzeit (ls mock_test_*.py − EXCLUDED),
#    danach statisch festgeschrieben. Kategorie A: deterministisch, kein
#    Real-State-/Datums-Read, läuft auf stdlib+jinja2+pyyaml. ───────────────
ALLOWLIST = [
    "backtest_data_integrity", "borrow_iborrowdesk", "card_cockpit_stage1", "card_cockpit_stage2",
    "chat_watchlist_ctx", "claude_md_consistency", "claude_md_pr_status", "cockpit_delta",
    "conviction_coverage_extension", "data_maturity_gate", "details_news_padding", "digest",
    "earliness_dtc", "earliness_pm_vol", "earliness_trend_log", "entry_raw_twin_fields",
    "entry_score", "entry_shadow_persist", "entry_thesis", "exit_push_discipline", "exit_shadow",
    "finnhub_skip_logging", "gitattributes_union_merge",
    "gist_action_token_routing", "health_check", "health_check_digest_persistence",
    "html_assertions", "jekyll_exclude", "jsformat_escape", "ki_agent_coverage",
    "ki_agent_rvol_disambiguation", "ki_analyse_padding", "knaller_label", "methodology_display",
    "methodology_panel_redesign", "news_coverage_extension", "outer_page_golden",
    "position_panel_locked", "positions_current_price", "probe_quote_proxy", "provider_consecutive_threshold_override",
    "provider_health", "provider_health_tier2", "provider_health_tier3", "provider_liveness",
    "push_history", "push_inflation_gating", "quote_polling", "quote_proxy_url_injection",
    "recalc_dispatch_run_phase", "redeploy_workflow_run_phase", "report_date_et", "rs_spy_merged_row",
    "run_phase_resolution", "runphase_pill", "rvol_normalization", "s10_data_integrity",
    "s11_s12_phase_frequency", "s14_gist_pull_liveness", "s7_race_gate", "s8_last_successful_run", "score_block_grid_layout",
    "score_block_label_scoping", "score_confidence", "score_confidence_watermark", "score_delta_t1",
    "score_inflation_log", "score_inflation_log_v2", "score_multiplier_sync", "score_normalization_version",
    "sector_rs_removal", "selector_consistency", "service_worker_removed", "session_wrap_indexeddb",
    "staleness_banner",
    "short_situation_none_guard",
    "setup_score_cursor_removed", "split_label_consistency", "tier3_success_check_recalibration", "token_reentry_fix",
    "token_settings_ui_refresh", "token_storage_diagnose", "vintage_guard",
    "watchlist_drawer_stale_data",
]

# ── EXCLUDED (10) — bewusst NICHT im Gate, je mit Grund. ───────────────────
EXCLUDED = {
    # B — Ergebnis hängt von echten Repo-Daten ab → datums-/content-flaky:
    "topten_entry_anomaly":             "liest ROOT/backtest_history.json (content-flaky)",
    "watchlist_drawer_live_momentum":   "liest ROOT/app_data.json (content-flaky)",
    # ENV — importieren yfinance (im CI/Sandbox nicht installiert):
    "catalyst":                          "yfinance-Import",
    "chat_synthesis_watchlist_fallback": "yfinance-Import",
    "postclose_run":                     "yfinance-Import",
    "score_history_pruning":             "yfinance-Import",
    "setup_erosion":                     "yfinance-Import",
    # TEMP — brauchen `requests`, das der Minimal-CI-Install (#316: nur
    # jinja2+pyyaml) NICHT hat. Bis #336 den requests-Stub ergänzt (analog
    # outer_page_golden), dann ZURÜCK in ALLOWLIST (Ziel 79). NICHT dauerhaft:
    "entry_score_persistence":           "TEMP: import generate_report ohne requests-Stub → #336",
    "health_check_ntfy_url_pattern":     "TEMP: zieht health_check_digest→requests → #336",
    "ntfy_fail_visibility":              "TEMP: zieht health_check_digest→requests → #336",
}


def present_tests() -> list[str]:
    """Ist-Menge aller mock_test_*.py (Namen ohne Präfix/Suffix). Glob NUR
    für den Drift-Guard — NICHT für die Test-Auswahl."""
    return sorted(p.split("mock_test_")[1][:-3]
                  for p in glob.glob(str(SCRIPTS / "mock_test_*.py")))


def check_coverage(present: list[str], allowlist: list[str],
                   excluded) -> dict[str, list[str]]:
    """Reiner Drift-Guard. Jeder vorhandene Test MUSS in allowlist ODER
    excluded sein; allowlist ∩ excluded == leer; keine gelisteten Phantome.

    Returnt {"overlap", "unclassified", "phantom"} — alle leer = sauber.
    Deterministisch (nur Mengen-Operationen auf den Eingaben).
    """
    present_s, allow_s, excl_s = set(present), set(allowlist), set(excluded)
    classified = allow_s | excl_s
    return {
        "overlap":      sorted(allow_s & excl_s),       # in BEIDEN → inkonsistent
        "unclassified": sorted(present_s - classified), # neuer Test, nicht eingeordnet
        "phantom":      sorted(classified - present_s),  # gelistet, aber Datei fehlt
    }


def main() -> int:
    present = present_tests()

    # ── Drift-Guard ZUERST (vor jedem Test-Lauf) ──────────────────────────
    drift = check_coverage(present, ALLOWLIST, EXCLUDED)
    if drift["overlap"] or drift["unclassified"] or drift["phantom"]:
        print("✗ DRIFT erkannt — ALLOWLIST/EXCLUDED inkonsistent zur Ist-Menge:")
        if drift["overlap"]:
            print(f"    in ALLOWLIST UND EXCLUDED (verboten): {drift['overlap']}")
        if drift["unclassified"]:
            print(f"    weder ALLOWLIST noch EXCLUDED (neuer Test? einordnen!): "
                  f"{drift['unclassified']}")
        if drift["phantom"]:
            print(f"    gelistet, aber Datei fehlt: {drift['phantom']}")
        print("  → einordnen (ALLOWLIST wenn Kategorie A, sonst EXCLUDED+Grund).")
        return 1

    # ── Alle ALLOWLIST-Tests fahren — KEIN Short-Circuit ──────────────────
    failed: list[str] = []
    for name in ALLOWLIST:
        path = SCRIPTS / f"mock_test_{name}.py"
        rc = subprocess.run([sys.executable, str(path)], cwd=str(ROOT)).returncode
        status = "✓" if rc == 0 else "✗"
        print(f"  {status} {name}" + ("" if rc == 0 else f"  (exit {rc})"))
        if rc != 0:
            failed.append(name)

    print()
    if failed:
        print(f"{len(failed)} von {len(ALLOWLIST)} Tests fehlgeschlagen: {failed}")
        return 1
    print(f"{len(ALLOWLIST)} Tests bestanden (Drift-Guard sauber).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
