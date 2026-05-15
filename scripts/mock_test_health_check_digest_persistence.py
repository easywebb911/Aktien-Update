"""Mock-Tests für Health-Check-JSONL-Persistenz + Cron-Offset.

Diagnose 15.05.2026: kein Digest-Push am Morgen. Drei strukturelle
Probleme:
  1. health_check_log.jsonl + provider_health.jsonl werden nie in
     git add aufgenommen → leeren Files bei jedem Workflow-Start
  2. Cron 13 8 * * * wurde gedropt (State-Commit erst 10:37 UTC)
  3. ntfy-Push gescheitert, aber Log-Output zu dünn für Diagnose

Tests:
  1. daily-squeeze-report.yml git-add-Liste enthält beide JSONL
  2. ki_agent.yml git-add-Liste enthält beide JSONL
  3. health_check_digest.yml Cron auf '21 8 * * *'
  4. health_check_digest.py ntfy-Send loggt HTTP-Status auch bei Success
  5. health_check_digest.py ntfy-Send loggt Exception-Type bei Fail
  6. YAML-Validität der 3 Workflow-Files
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

DAILY_RUN_YML = ROOT / ".github" / "workflows" / "daily-squeeze-report.yml"
KI_AGENT_YML  = ROOT / ".github" / "workflows" / "ki_agent.yml"
DIGEST_YML    = ROOT / ".github" / "workflows" / "health_check_digest.yml"
DIGEST_PY     = ROOT / "scripts" / "health_check_digest.py"


# === 1 — JSONL-Persistenz in beiden Pipelines =============================


def test_daily_run_adds_health_check_log():
    text = DAILY_RUN_YML.read_text(encoding="utf-8")
    assert "git add health_check_log.jsonl" in text, (
        "daily-squeeze-report.yml fehlt 'git add health_check_log.jsonl' — "
        "JSONL persistiert nicht zwischen Runs")


def test_daily_run_adds_provider_health():
    text = DAILY_RUN_YML.read_text(encoding="utf-8")
    assert "git add provider_health.jsonl" in text, (
        "daily-squeeze-report.yml fehlt 'git add provider_health.jsonl'")


def test_daily_run_jsonl_adds_use_safe_pattern():
    """Robust gegen fehlende File — || true verhindert Pipeline-Crash."""
    text = DAILY_RUN_YML.read_text(encoding="utf-8")
    assert re.search(
        r"git add health_check_log\.jsonl\s+2>/dev/null\s+\|\|\s+true", text), (
        "health_check_log.jsonl-Add ist nicht || true-geschützt")
    assert re.search(
        r"git add provider_health\.jsonl\s+2>/dev/null\s+\|\|\s+true", text), (
        "provider_health.jsonl-Add ist nicht || true-geschützt")


def test_ki_agent_adds_health_check_log():
    text = KI_AGENT_YML.read_text(encoding="utf-8")
    assert "git add health_check_log.jsonl" in text, (
        "ki_agent.yml fehlt 'git add health_check_log.jsonl'")


def test_ki_agent_adds_provider_health():
    text = KI_AGENT_YML.read_text(encoding="utf-8")
    assert "git add provider_health.jsonl" in text, (
        "ki_agent.yml fehlt 'git add provider_health.jsonl'")


def test_ki_agent_jsonl_adds_use_safe_pattern():
    text = KI_AGENT_YML.read_text(encoding="utf-8")
    assert re.search(
        r"git add health_check_log\.jsonl\s+2>/dev/null\s+\|\|\s+true", text)
    assert re.search(
        r"git add provider_health\.jsonl\s+2>/dev/null\s+\|\|\s+true", text)


# === 2 — Cron-Offset Digest-Workflow ======================================


def test_digest_cron_is_21_8():
    """Cron 21 8 * * * (Spec-Wortlaut '0 8' → '13 8' → '21 8') —
    weiter weg vom Stunden-Last-Peak."""
    import yaml
    data = yaml.safe_load(DIGEST_YML.read_text(encoding="utf-8"))
    triggers = data["on" if "on" in data else True]
    cron = triggers["schedule"][0]["cron"]
    assert cron == "21 8 * * *", (
        f"Cron sollte '21 8 * * *' sein, ist {cron!r}")


def test_digest_cron_comment_documents_drift():
    """Workflow-File dokumentiert die 13→21-Verschiebung mit Datum + Grund."""
    text = DIGEST_YML.read_text(encoding="utf-8")
    assert "15.05.2026" in text, "Datum der Cron-Migration fehlt im Comment"
    assert "21 8 * * *" in text


# === 3 — Logging-Erweiterung ntfy_send ===================================


def test_ntfy_send_logs_http_status_on_success():
    """INFO-Level-Log bei HTTP < 400 — beim ersten Push-Ausbleiben war
    nicht klar, ob Push überhaupt rausging."""
    text = DIGEST_PY.read_text(encoding="utf-8")
    pat = re.compile(
        r'log\.info\("ntfy-Push HTTP %d \(OK\)',
        re.DOTALL,
    )
    assert pat.search(text), (
        "_ntfy_send loggt HTTP-Status bei Success nicht (INFO-Level)")


def test_ntfy_send_logs_exception_type_on_failure():
    """Exception-Type mit-loggen — zwischen Timeout / SSL / DNS unter-
    scheiden."""
    text = DIGEST_PY.read_text(encoding="utf-8")
    pat = re.compile(
        r'log\.warning\("ntfy-Push Netzwerk-Fehler %s:.*?type\(exc\)\.__name__',
        re.DOTALL,
    )
    assert pat.search(text), (
        "_ntfy_send loggt type(exc).__name__ bei Exception nicht")


def test_ntfy_send_existing_fail_path_intact():
    """HTTP >= 400-Fail-Pfad bleibt erhalten — keine Regression."""
    text = DIGEST_PY.read_text(encoding="utf-8")
    # Vorsichts-Prinzip: existing FAIL-Pfad mit return False intakt
    assert 'log.warning("ntfy-Push HTTP %d (FAIL)' in text or \
           'log.warning("ntfy-Push HTTP %d:' in text, (
        "HTTP-Fail-Logging fehlt")
    assert text.count("return False") >= 3, (
        "Fail-Pfad-Anzahl reduziert — ungewollte Regression")


# === 4 — YAML-Validität der drei Workflow-Files ==========================


def test_all_workflow_yamls_valid():
    import yaml
    for path in (DAILY_RUN_YML, KI_AGENT_YML, DIGEST_YML):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data is not None, f"{path.name} parsed zu None"
        assert "jobs" in data, f"{path.name} hat kein 'jobs'-Key"


def test_digest_workflow_still_has_workflow_dispatch():
    """workflow_dispatch-Trigger nicht versehentlich entfernt."""
    import yaml
    data = yaml.safe_load(DIGEST_YML.read_text(encoding="utf-8"))
    triggers = data["on" if "on" in data else True]
    assert "workflow_dispatch" in triggers


# === 5 — Vorsichts-Prinzip ==============================================


def test_digest_logic_unchanged():
    """Digest-Aggregation/Push-Klassen-Logik wurde NICHT angefasst —
    nur Logging + Cron. Sanity: alle 3 Push-Klassen-Strings sind noch da."""
    import health_check as hc
    body_ok, title_ok, _, _ = hc.format_digest_body(
        [], [], n_runs=10, last_run_iso=None, digest_date="2026-05-15")
    assert "✅ Health-Check OK" in title_ok
    body_empty, title_empty, _, _ = hc.format_digest_body(
        [], [], n_runs=0, last_run_iso=None, digest_date="2026-05-15")
    assert "📭 Health-Check ohne Daten" in title_empty
    body_warn, title_warn, _, _ = hc.format_digest_body(
        [{"id": "S2", "severity": "crit", "detail": "x", "count": 1}],
        [], n_runs=10, last_run_iso=None, digest_date="2026-05-15")
    assert "⚠️ Health-Check-Digest" in title_warn


def test_health_check_helpers_untouched():
    """instrument_provider_call + record_run usw. unangetastet."""
    import health_check as hc
    assert hasattr(hc, "record_run")
    assert hasattr(hc, "record_provider_call")
    assert hasattr(hc, "instrument_provider_call")
    assert hasattr(hc, "aggregate_state_fails")
    assert hasattr(hc, "aggregate_provider_fails")


# === Runner =============================================================


def main() -> None:
    sys.path.insert(0, str(ROOT))   # health_check importierbar
    tests = [
        # JSONL-Persistenz
        ("daily-squeeze-report.yml: git add health_check_log.jsonl",
         test_daily_run_adds_health_check_log),
        ("daily-squeeze-report.yml: git add provider_health.jsonl",
         test_daily_run_adds_provider_health),
        ("daily-squeeze-report.yml: || true-geschützt",
         test_daily_run_jsonl_adds_use_safe_pattern),
        ("ki_agent.yml: git add health_check_log.jsonl",
         test_ki_agent_adds_health_check_log),
        ("ki_agent.yml: git add provider_health.jsonl",
         test_ki_agent_adds_provider_health),
        ("ki_agent.yml: || true-geschützt",
         test_ki_agent_jsonl_adds_use_safe_pattern),
        # Cron-Offset
        ("Digest-Cron auf '21 8 * * *'", test_digest_cron_is_21_8),
        ("Cron-Migration dokumentiert (15.05.2026)",
         test_digest_cron_comment_documents_drift),
        # Logging
        ("ntfy_send loggt HTTP-Status bei Success",
         test_ntfy_send_logs_http_status_on_success),
        ("ntfy_send loggt Exception-Type bei Fail",
         test_ntfy_send_logs_exception_type_on_failure),
        ("HTTP-Fail-Pfad unverändert",
         test_ntfy_send_existing_fail_path_intact),
        # YAML
        ("Alle 3 Workflow-YAMLs parsbar", test_all_workflow_yamls_valid),
        ("Digest-Workflow workflow_dispatch erhalten",
         test_digest_workflow_still_has_workflow_dispatch),
        # Vorsichts-Prinzip
        ("Digest-Aggregations-Logik unverändert (3 Push-Klassen)",
         test_digest_logic_unchanged),
        ("health_check-Helper unangetastet",
         test_health_check_helpers_untouched),
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
