"""Mock-Tests für Health-Check Digest (Phase 3).

Drei Test-Säulen:
  1. Aggregations-Helper (pure Funktionen in health_check.py)
     - aggregate_state_fails: leer / 1 crit / 2 warn / mixed
     - aggregate_provider_fails: Tier-1-sofort vs Tier-2/3-3-in-Folge
     - format_digest_body: 4 Cases (OK / leer / crit / warn-Schwelle)

  2. Konsekutiv-Counter
     - 3 Fail-Runs hintereinander → counter = 3 → provider_fail emittiert
     - Erfolgreicher 4. Run → counter zurück auf 0
     - 7-Tage-Drift-Schutz: stale counter wird zurückgesetzt

  3. Workflow + Script-Integration
     - YAML-Validität von health_check_digest.yml
     - Cron 13 8 * * *
     - last_digest_sent Mehrfach-Trigger-Schutz
     - ntfy-POST monkey-patched (kein echter Netzwerk-Call)
     - Leere JSONL → "📭 Health-Check ohne Daten"-Klasse

Ausführung: ``python scripts/mock_test_digest.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import importlib
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest.mock as mock
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402


def _ts(year, month, day, hour=8, minute=0) -> str:
    return datetime(year, month, day, hour, minute,
                    tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# === 1. aggregate_state_fails =============================================


def test_state_fails_empty():
    assert hc.aggregate_state_fails([]) == []
    assert hc.aggregate_state_fails(None) == []


def test_state_fails_one_crit():
    entries = [{"state_fails": [
        {"id": "S2", "severity": "crit", "detail": "too few tickers"}]}]
    out = hc.aggregate_state_fails(entries)
    assert len(out) == 1
    assert out[0]["id"] == "S2"
    assert out[0]["severity"] == "crit"
    assert out[0]["count"] == 1


def test_state_fails_count_increments_across_runs():
    entries = [
        {"state_fails": [{"id": "S5", "severity": "warn", "detail": "few lines"}]},
        {"state_fails": [{"id": "S5", "severity": "warn", "detail": "few lines"}]},
        {"state_fails": [{"id": "S5", "severity": "warn", "detail": "still few"}]},
    ]
    out = hc.aggregate_state_fails(entries)
    assert len(out) == 1
    assert out[0]["count"] == 3
    assert out[0]["detail"] == "still few"   # jüngster Detail-String


def test_state_fails_crit_overrides_warn():
    entries = [
        {"state_fails": [{"id": "S6", "severity": "warn", "detail": "low"}]},
        {"state_fails": [{"id": "S6", "severity": "crit", "detail": "zero"}]},
    ]
    out = hc.aggregate_state_fails(entries)
    assert out[0]["severity"] == "crit"


def test_state_fails_stable_order():
    """Reihenfolge S1 → S7 unabhängig von Eintrags-Reihenfolge."""
    entries = [
        {"state_fails": [
            {"id": "S5", "severity": "warn", "detail": "a"},
            {"id": "S1", "severity": "crit", "detail": "b"},
            {"id": "S3", "severity": "crit", "detail": "c"},
        ]},
    ]
    out = hc.aggregate_state_fails(entries)
    assert [f["id"] for f in out] == ["S1", "S3", "S5"]


# === 2. aggregate_provider_fails + Konsekutiv-Counter =====================


def test_provider_tier1_immediate_fail():
    """Tier-1: ein einziger Fail → sofort crit-Eintrag."""
    entries = [{
        "run_ts": _ts(2026, 5, 15, 10), "provider": "yahoo_screener",
        "tier": 1, "http_status": None, "coverage_pct": None,
        "error": "empty_result",
    }]
    counters: dict = {}
    out = hc.aggregate_provider_fails(
        entries, counters, tier_map={"yahoo_screener": 1})
    assert len(out) == 1
    assert out[0]["severity"] == "crit"
    assert out[0]["consecutive"] == 1


def test_provider_tier2_needs_three_in_a_row():
    """Tier-2: erst ab 3-in-Folge wird ein Fail emittiert."""
    counters: dict = {}
    # now_ts nahe den run_ts (15.05.) übergeben, sonst nullt der Stale-
    # Counter-Reset (> 7 d) den Counter bei wall-clock-now (Vorlage Z.191+).
    now = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    # Lauf 1: fail
    out1 = hc.aggregate_provider_fails(
        [{"run_ts": _ts(2026, 5, 15, 1), "provider": "finra", "tier": 2,
          "http_status": None, "coverage_pct": None, "error": "empty"}],
        counters, tier_map={"finra": 2}, now_ts=now)
    assert out1 == []   # erst beim 3-Lauf
    # Lauf 2 (kumulativ)
    out2 = hc.aggregate_provider_fails(
        [{"run_ts": _ts(2026, 5, 15, 2), "provider": "finra", "tier": 2,
          "http_status": None, "coverage_pct": None, "error": "empty"}],
        counters, tier_map={"finra": 2}, now_ts=now)
    assert out2 == []
    # Lauf 3 → Schwelle erreicht
    out3 = hc.aggregate_provider_fails(
        [{"run_ts": _ts(2026, 5, 15, 3), "provider": "finra", "tier": 2,
          "http_status": None, "coverage_pct": None, "error": "empty"}],
        counters, tier_map={"finra": 2}, now_ts=now)
    assert len(out3) == 1
    assert out3[0]["severity"] == "warn"
    assert out3[0]["consecutive"] == 3


def test_provider_tier2_success_resets_counter():
    """Tier-2 erfolgreicher Run nach 2 Fails → counter back to 0."""
    counters = {"consecutive_failures": {"finra": 2}, "last_seen": {}}
    out = hc.aggregate_provider_fails(
        [{"run_ts": _ts(2026, 5, 15, 4), "provider": "finra", "tier": 2,
          "http_status": 200, "coverage_pct": 95.0, "error": None}],
        counters, tier_map={"finra": 2})
    assert out == []
    assert counters["consecutive_failures"]["finra"] == 0


def test_provider_coverage_threshold_tier1():
    """Tier-1: coverage < 80 % → sofort fail."""
    counters: dict = {}
    out = hc.aggregate_provider_fails(
        [{"run_ts": _ts(2026, 5, 15, 5), "provider": "yfinance_batch",
          "tier": 1, "http_status": 200, "coverage_pct": 60.0, "error": None}],
        counters, tier_map={"yfinance_batch": 1})
    assert len(out) == 1
    assert out[0]["severity"] == "crit"


def test_provider_coverage_threshold_tier2_at_50():
    """Tier-2: coverage < 50 % (Spec). 49 → fail, 60 → OK."""
    counters: dict = {}
    # now_ts nahe den run_ts (15.05.), sonst nullt der Stale-Reset (> 7 d)
    # den Counter bei wall-clock-now (Vorlage Z.191+).
    now = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    # 49 → fail-Schwelle gerissen
    out_fail = hc.aggregate_provider_fails(
        [{"run_ts": _ts(2026, 5, 15, 1), "provider": "finnhub", "tier": 2,
          "http_status": 200, "coverage_pct": 49.0, "error": None}],
        counters, tier_map={"finnhub": 2}, now_ts=now)
    assert out_fail == []   # nicht 3-in-Folge
    assert counters["consecutive_failures"]["finnhub"] == 1
    # 60 → ok, counter reset
    out_ok = hc.aggregate_provider_fails(
        [{"run_ts": _ts(2026, 5, 15, 2), "provider": "finnhub", "tier": 2,
          "http_status": 200, "coverage_pct": 60.0, "error": None}],
        counters, tier_map={"finnhub": 2}, now_ts=now)
    assert out_ok == []
    assert counters["consecutive_failures"]["finnhub"] == 0


def test_provider_stale_counter_drift_reset():
    """Provider, der seit > 7 Tagen nicht erschienen ist, bekommt counter
    automatisch auf 0 zurück (Drift-Schutz bei ENABLED-Toggle)."""
    eight_days_ago = _ts(2026, 5, 7, 12)
    counters = {
        "consecutive_failures": {"stocktwits": 5},
        "last_seen":             {"stocktwits": eight_days_ago},
    }
    now = datetime(2026, 5, 15, 8, 0, tzinfo=timezone.utc)
    # leere entries — stocktwits taucht nicht auf
    hc.aggregate_provider_fails([], counters,
                                  tier_map={"stocktwits": 3}, now_ts=now)
    assert counters["consecutive_failures"]["stocktwits"] == 0, (
        "Stale counter > 7d sollte zurückgesetzt werden")


# === 3. format_digest_body ===============================================


def test_format_body_all_ok():
    body, title, prio, tags = hc.format_digest_body(
        state_fails=[], provider_fails=[],
        n_runs=26, last_run_iso=_ts(2026, 5, 15, 7),
        digest_date="2026-05-15",
    )
    assert title == "✅ Health-Check OK"
    assert prio == "default"
    assert tags is None
    assert "✅ Health-Check OK" in body
    assert "26 Runs" in body


def test_format_body_no_runs_separate_class():
    """Leere JSONL → eigene Klasse, nicht missverstaendlich als OK."""
    body, title, prio, tags = hc.format_digest_body(
        state_fails=[], provider_fails=[],
        n_runs=0, last_run_iso=None,
        digest_date="2026-05-15",
    )
    assert title == "📭 Health-Check ohne Daten"
    assert prio == "high"
    assert "0 Runs" in body


def test_format_body_one_crit():
    body, title, prio, tags = hc.format_digest_body(
        state_fails=[{"id": "S2", "severity": "crit",
                      "detail": "9 tickers", "count": 1}],
        provider_fails=[],
        n_runs=26, last_run_iso=_ts(2026, 5, 15, 7),
        digest_date="2026-05-15",
    )
    assert title == "⚠️ Health-Check-Digest"
    assert prio == "high"
    assert "1 crit" in body
    assert "S2: 9 tickers" in body


def test_format_body_warn_below_threshold_is_ok():
    """1-2 warns sind unter Spec-Schwelle (≥ 3 warn) → bleibt OK-Push."""
    body, title, prio, tags = hc.format_digest_body(
        state_fails=[{"id": "S6", "severity": "warn", "detail": "low", "count": 2}],
        provider_fails=[],
        n_runs=26, last_run_iso=_ts(2026, 5, 15, 7),
        digest_date="2026-05-15",
    )
    assert title == "✅ Health-Check OK"


def test_format_body_three_warn_triggers_digest():
    """≥ 3 warn → Digest-Push high priority."""
    body, title, prio, tags = hc.format_digest_body(
        state_fails=[
            {"id": "S5", "severity": "warn", "detail": "a", "count": 1},
            {"id": "S6", "severity": "warn", "detail": "b", "count": 1},
            {"id": "S7", "severity": "warn", "detail": "c", "count": 1},
        ],
        provider_fails=[],
        n_runs=26, last_run_iso=_ts(2026, 5, 15, 7),
        digest_date="2026-05-15",
    )
    assert title == "⚠️ Health-Check-Digest"
    assert prio == "high"
    assert "3 warn" in body


def test_format_body_mixed_crit_warn():
    body, title, prio, tags = hc.format_digest_body(
        state_fails=[{"id": "S3", "severity": "crit",
                      "detail": "AMC missing price", "count": 5}],
        provider_fails=[
            {"provider": "finnhub", "tier": 2, "severity": "warn",
             "reason": "coverage 0%", "consecutive": 3},
            {"provider": "edgar_13d_g", "tier": 3, "severity": "warn",
             "reason": "HTTP 403", "consecutive": 3},
        ],
        n_runs=26, last_run_iso=_ts(2026, 5, 15, 7),
        digest_date="2026-05-15",
    )
    assert title == "⚠️ Health-Check-Digest"
    assert "S3: AMC missing price" in body
    assert "5 Runs in Folge" in body
    assert "finnhub (Tier 2): coverage 0% (3 Runs in Folge)" in body
    assert "edgar_13d_g (Tier 3)" in body


# === 4. Skript-Integration: digest-main + Multi-Trigger-Schutz ============


def _import_digest_module():
    """Importiert scripts/health_check_digest.py frisch (für isolierte Tests)."""
    spec = importlib.util.spec_from_file_location(
        "_dgst", ROOT / "scripts" / "health_check_digest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_already_sent_today_blocks_second_run():
    """``last_digest_sent`` == today_iso → Skript skipt zweiten Aufruf."""
    dg = _import_digest_module()
    state = {"last_digest_sent": "2026-05-15"}
    assert dg._already_sent_today(state, "2026-05-15") is True
    assert dg._already_sent_today(state, "2026-05-14") is False
    assert dg._already_sent_today({}, "2026-05-15") is False


def test_jsonl_window_filter_cutoff():
    """``_load_jsonl_window`` skipt Einträge älter als cutoff."""
    dg = _import_digest_module()
    now = datetime(2026, 5, 15, 8, 0, tzinfo=timezone.utc)
    cutoff = now - timedelta(hours=24)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = pathlib.Path(fh.name)
    try:
        fh.close()
        path.write_text(
            json.dumps({"run_ts": "2026-05-13T08:00:00Z", "old": True}) + "\n"
            + json.dumps({"run_ts": "2026-05-15T07:00:00Z", "new": True}) + "\n",
            encoding="utf-8",
        )
        entries = dg._load_jsonl_window(path, cutoff)
        assert len(entries) == 1
        assert entries[0].get("new") is True
    finally:
        path.unlink(missing_ok=True)


def test_jsonl_window_tolerates_broken_lines():
    dg = _import_digest_module()
    cutoff = datetime(2026, 5, 14, 0, 0, tzinfo=timezone.utc)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = pathlib.Path(fh.name)
    try:
        fh.close()
        path.write_text(
            "nicht-parsebar\n"
            + json.dumps({"run_ts": "2026-05-15T07:00:00Z", "good": True}) + "\n",
            encoding="utf-8",
        )
        entries = dg._load_jsonl_window(path, cutoff)
        assert len(entries) == 1
        assert entries[0].get("good") is True
    finally:
        path.unlink(missing_ok=True)


def test_main_dry_run_does_not_write_state():
    """dry_run=True schreibt keine state-Datei zurück."""
    dg = _import_digest_module()
    # Use a tmp state path via monkey-patch
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp) / "state.json"
        with mock.patch.object(dg, "DIGEST_STATE_FILE", tmp_path):
            rc = dg.main(now_ts=datetime(2026, 5, 15, 8, 13, tzinfo=timezone.utc),
                         dry_run=True)
        assert rc == 0
        assert not tmp_path.exists(), "dry_run sollte keine state-Datei schreiben"


def test_main_persists_state_on_real_run():
    dg = _import_digest_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_state = pathlib.Path(tmp) / "state.json"
        with mock.patch.object(dg, "DIGEST_STATE_FILE", tmp_state), \
             mock.patch.object(dg, "_ntfy_send", return_value=False), \
             mock.patch.object(dg, "NTFY_TOPIC", ""):
            dg.main(now_ts=datetime(2026, 5, 15, 8, 13, tzinfo=timezone.utc))
        assert tmp_state.exists()
        state = json.loads(tmp_state.read_text())
        assert state["last_digest_sent"] == "2026-05-15"


def test_main_sets_last_successful_run_even_with_fails():
    """Regression: ``last_successful_run`` muss auch bei n_runs>0 + Fails
    gesetzt werden (vor 22.05.2026 nur bei 0 Fails, deshalb toter Code
    seit 14.05.). Liveness-Marker, nicht 0-Fails-Marker.
    """
    dg = _import_digest_module()
    # JSONL mit echten Daten füttern, damit n_runs > 0 ist und State-
    # Fails entstehen (das ist genau die heutige Pre-22.05.-Lage).
    fixture_run = {
        "run_ts":     "2026-05-21T09:00:00Z",
        "run_phase":  "postclose",
        "state_fails": [{"id": "S6", "severity": "warn", "detail": "x"}],
        "provider_fails": [],
        "schema_v":   1,
    }
    with tempfile.TemporaryDirectory() as tmp:
        tmp_state = pathlib.Path(tmp) / "state.json"
        with mock.patch.object(dg, "DIGEST_STATE_FILE", tmp_state), \
             mock.patch.object(dg, "_ntfy_send", return_value=False), \
             mock.patch.object(dg, "NTFY_TOPIC", ""), \
             mock.patch.object(dg, "_load_jsonl_window",
                                return_value=[fixture_run]):
            dg.main(now_ts=datetime(2026, 5, 21, 8, 47,
                                     tzinfo=timezone.utc))
        state = json.loads(tmp_state.read_text())
    assert state.get("last_successful_run"), (
        f"last_successful_run muss bei n_runs>0 gesetzt sein, auch "
        f"wenn state_fails da sind. Bekam: {state.get('last_successful_run')!r}"
    )
    # Letzte run_ts aus dem Fenster wird übernommen.
    assert state["last_successful_run"] == "2026-05-21T09:00:00Z", \
        f"erwartet last-run-Timestamp aus Fenster, bekam: {state['last_successful_run']!r}"


def test_main_skips_when_already_sent_today():
    dg = _import_digest_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_state = pathlib.Path(tmp) / "state.json"
        tmp_state.write_text(json.dumps({
            "last_digest_sent": "2026-05-15",
            "consecutive_failures": {}, "last_seen": {},
        }))
        sent_calls = []
        def _spy_send(*a, **kw):
            sent_calls.append((a, kw))
            return True
        with mock.patch.object(dg, "DIGEST_STATE_FILE", tmp_state), \
             mock.patch.object(dg, "_ntfy_send", side_effect=_spy_send):
            rc = dg.main(now_ts=datetime(2026, 5, 15, 9, 0,
                                          tzinfo=timezone.utc))
        assert rc == 0
        assert len(sent_calls) == 0, (
            "Mehrfach-Trigger-Schutz verletzt — Push wurde doppelt gesendet")


def test_main_force_overrides_already_sent():
    dg = _import_digest_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_state = pathlib.Path(tmp) / "state.json"
        tmp_state.write_text(json.dumps({
            "last_digest_sent": "2026-05-15",
            "consecutive_failures": {}, "last_seen": {},
        }))
        sent = {"calls": 0}
        def _spy_send(*a, **kw):
            sent["calls"] += 1
            return True
        with mock.patch.object(dg, "DIGEST_STATE_FILE", tmp_state), \
             mock.patch.object(dg, "_ntfy_send", side_effect=_spy_send), \
             mock.patch.object(dg, "NTFY_TOPIC", "test-topic"):
            dg.main(now_ts=datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc),
                    force=True)
        assert sent["calls"] == 1


def test_ntfy_send_skipped_when_disabled():
    dg = _import_digest_module()
    with mock.patch.object(dg, "NTFY_TOPIC", ""):
        ok = dg._ntfy_send("title", "body", "default", None)
    assert ok is False


def test_ntfy_send_monkey_patched_post():
    """ntfy-Send geht durch requests.post — wird komplett gemockt.

    URL-Pattern-Adoption (17.05.2026): zurueck auf
    POST https://ntfy.sh/{topic} mit Title-Header (ASCII-only).
    Body bleibt UTF-8 (als data=).
    """
    dg = _import_digest_module()
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.text = "ok"
    with mock.patch.object(dg, "NTFY_TOPIC", "test-topic"), \
         mock.patch.object(dg, "NTFY_ENABLED", True), \
         mock.patch.object(dg, "requests") as mock_requests:
        mock_requests.post.return_value = mock_resp
        # Title mit Emoji — wird ASCII-gestrippt im Send
        ok = dg._ntfy_send("⚠️ Health-Check-Digest", "body mit ⚠️ emoji",
                           "high", "warning")
        assert ok is True
        assert mock_requests.post.call_count == 1
        call_args = mock_requests.post.call_args
        # POST geht zu https://ntfy.sh/{topic} (URL-Pattern)
        assert call_args[0][0] == "https://ntfy.sh/test-topic"
        # Body als UTF-8-Bytes
        assert call_args[1]["data"] == "body mit ⚠️ emoji".encode("utf-8")
        # Title-Header ist ASCII-only (Emoji entfernt)
        headers = call_args[1]["headers"]
        assert "Title" in headers
        title_bytes = headers["Title"].encode("ascii")  # Darf nicht raisen
        assert b"Health-Check-Digest" in title_bytes
        assert headers["Priority"] == "high"
        assert headers["Tags"] == "warning"


# === 5. YAML-Workflow-Validität ============================================


def test_workflow_yaml_valid():
    import yaml as _yaml
    path = ROOT / ".github" / "workflows" / "health_check_digest.yml"
    data = _yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data is not None
    assert "jobs" in data
    assert "digest" in data["jobs"]


def test_workflow_cron_matches_user_choice():
    """Cron `47 8 * * *` (Migration 16.05.2026 — zweite Drift-Korrektur,
    21-Offset wurde am 15./16.05. wiederholt gedropt)."""
    import yaml as _yaml
    path = ROOT / ".github" / "workflows" / "health_check_digest.yml"
    data = _yaml.safe_load(path.read_text(encoding="utf-8"))
    triggers = data["on" if "on" in data else True]
    schedule = triggers["schedule"] if isinstance(triggers, dict) else None
    assert schedule, "schedule-Trigger fehlt"
    cron = schedule[0]["cron"]
    assert cron == "47 8 * * *", f"Cron sollte '47 8 * * *' sein, ist {cron!r}"


def test_workflow_has_workflow_dispatch():
    import yaml as _yaml
    path = ROOT / ".github" / "workflows" / "health_check_digest.yml"
    data = _yaml.safe_load(path.read_text(encoding="utf-8"))
    triggers = data["on" if "on" in data else True]
    assert "workflow_dispatch" in (triggers if isinstance(triggers, dict) else {})


def test_workflow_writes_contents_permission():
    import yaml as _yaml
    path = ROOT / ".github" / "workflows" / "health_check_digest.yml"
    data = _yaml.safe_load(path.read_text(encoding="utf-8"))
    perms = data.get("permissions") or {}
    assert perms.get("contents") == "write", (
        "permissions.contents=write fehlt — git push würde scheitern")


def test_workflow_runs_digest_script():
    path = ROOT / ".github" / "workflows" / "health_check_digest.yml"
    text = path.read_text(encoding="utf-8")
    assert "scripts/health_check_digest.py" in text
    assert "NTFY_TOPIC" in text


# === Runner ================================================================


def main() -> None:
    tests = [
        # State-Fails
        ("aggregate_state_fails: leer",                     test_state_fails_empty),
        ("aggregate_state_fails: 1 crit",                   test_state_fails_one_crit),
        ("aggregate_state_fails: count über mehrere Runs",  test_state_fails_count_increments_across_runs),
        ("aggregate_state_fails: crit überschreibt warn",   test_state_fails_crit_overrides_warn),
        ("aggregate_state_fails: stabile Reihenfolge",      test_state_fails_stable_order),
        # Provider-Fails
        ("Tier 1: ein Fail → sofort crit",                  test_provider_tier1_immediate_fail),
        ("Tier 2: 3-in-Folge nötig für warn",               test_provider_tier2_needs_three_in_a_row),
        ("Tier 2: erfolgreicher Run resettet Counter",      test_provider_tier2_success_resets_counter),
        ("Tier 1: coverage < 80 → sofort crit",             test_provider_coverage_threshold_tier1),
        ("Tier 2: coverage < 50 → counter, > 50 reset",     test_provider_coverage_threshold_tier2_at_50),
        ("Stale counter > 7d → reset (Drift-Schutz)",       test_provider_stale_counter_drift_reset),
        # Body-Format
        ("format_body: alles ok",                            test_format_body_all_ok),
        ("format_body: 0 Runs → eigene Klasse",              test_format_body_no_runs_separate_class),
        ("format_body: 1 crit → Digest high",                test_format_body_one_crit),
        ("format_body: 2 warn → bleibt OK",                  test_format_body_warn_below_threshold_is_ok),
        ("format_body: 3 warn → Digest high",                test_format_body_three_warn_triggers_digest),
        ("format_body: gemischt crit+warn",                  test_format_body_mixed_crit_warn),
        # Skript-Integration
        ("_already_sent_today blockt 2. Run",                test_already_sent_today_blocks_second_run),
        ("_load_jsonl_window: cutoff-Filter",                test_jsonl_window_filter_cutoff),
        ("_load_jsonl_window: kaputte Zeilen geskippt",      test_jsonl_window_tolerates_broken_lines),
        ("main(dry_run=True) schreibt keinen state",         test_main_dry_run_does_not_write_state),
        ("main() persistiert state",                          test_main_persists_state_on_real_run),
        ("last_successful_run bei n_runs>0 + Fails",         test_main_sets_last_successful_run_even_with_fails),
        ("main() skipt bei already-sent-today",              test_main_skips_when_already_sent_today),
        ("main(force=True) überschreibt skip",               test_main_force_overrides_already_sent),
        ("_ntfy_send: disabled → no-op",                     test_ntfy_send_skipped_when_disabled),
        ("_ntfy_send: monkey-patched POST mit Headers",      test_ntfy_send_monkey_patched_post),
        # Workflow-YAML
        ("Workflow-YAML parsbar",                            test_workflow_yaml_valid),
        ("Workflow-Cron = '47 8 * * *'",                     test_workflow_cron_matches_user_choice),
        ("Workflow workflow_dispatch verfügbar",             test_workflow_has_workflow_dispatch),
        ("Workflow contents=write Permission",               test_workflow_writes_contents_permission),
        ("Workflow ruft digest-Script + NTFY_TOPIC",         test_workflow_runs_digest_script),
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
