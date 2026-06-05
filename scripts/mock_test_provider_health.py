"""Mock-Tests für health_check.py Provider-Health (Phase 2 PR 1).

Pro Tier-1-Provider: Schema-Validierung + Persistenz + Source-
Inspektion (Wrapper sitzt um den richtigen Call-Site). Zusätzlich:
Prune-Verhalten, Fail-soft, Schema-Marker, ki_agent-Emission.

Ausführung: ``python scripts/mock_test_provider_health.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402
from config import (        # noqa: E402
    HEALTH_CHECK_PROVIDER_TIER,
    HEALTH_CHECK_PROVIDER_EXPECTED,
)

SRC_GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
SRC_KI = (ROOT / "ki_agent.py").read_text(encoding="utf-8")


# ── Schema + Persistenz ────────────────────────────────────────────────────


def test_record_writes_schema_v1():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        ok = hc.record_provider_call(
            provider="yahoo_screener", tier=1, latency_ms=1234,
            http_status=200, item_count=150, error=None,
            run_phase="premarket",
            run_ts=datetime(2026, 5, 14, 10, 17, tzinfo=timezone.utc),
            path=path,
        )
        assert ok
        entries = hc.read_all_provider(path)
        assert len(entries) == 1
        e = entries[0]
        # Pflicht-Felder
        for k in ("run_ts", "run_phase", "provider", "tier", "http_status",
                  "latency_ms", "item_count", "coverage_pct", "nan_pct",
                  "error", "schema_v"):
            assert k in e, f"Pflicht-Feld {k!r} fehlt"
        assert e["schema_v"] == 1
        assert e["provider"] == "yahoo_screener"
        assert e["tier"] == 1
        assert e["item_count"] == 150
        assert e["run_ts"] == "2026-05-14T10:17:00Z"
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


def test_record_append_only():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        hc.record_provider_call("finviz", 1, 2000, 200, 90,
                                run_phase="premarket", path=path)
        hc.record_provider_call("yfinance_batch", 1, 8000, 200, 78,
                                coverage_pct=78.0,
                                run_phase="premarket", path=path)
        entries = hc.read_all_provider(path)
        assert len(entries) == 2
        assert entries[0]["provider"] == "finviz"
        assert entries[1]["provider"] == "yfinance_batch"
        assert entries[1]["coverage_pct"] == 78.0
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


def test_record_fail_with_error_string():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        hc.record_provider_call(
            "yahoo_screener", 1, 20000, None, 0,
            error="empty_result", run_phase="premarket", path=path,
        )
        e = hc.read_all_provider(path)[0]
        assert e["http_status"] is None
        assert e["error"] == "empty_result"
        assert e["item_count"] == 0
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


# ── Prune ──────────────────────────────────────────────────────────────────


def test_prune_removes_old_keeps_fresh():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=35)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fresh = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(path, "w") as f:
            f.write(json.dumps({"run_ts": old, "provider": "x", "tier": 1,
                                "schema_v": 1, "run_phase": "premarket",
                                "http_status": 200, "latency_ms": 1000,
                                "item_count": 1, "coverage_pct": None,
                                "nan_pct": None, "error": None}) + "\n")
            f.write(json.dumps({"run_ts": fresh, "provider": "x", "tier": 1,
                                "schema_v": 1, "run_phase": "postclose",
                                "http_status": 200, "latency_ms": 1000,
                                "item_count": 1, "coverage_pct": None,
                                "nan_pct": None, "error": None}) + "\n")
        n_removed = hc.prune_provider_log(max_days=30, path=path)
        assert n_removed == 1
        entries = hc.read_all_provider(path)
        assert len(entries) == 1
        assert entries[0]["run_ts"] == fresh
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


def test_prune_preserves_broken_lines():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        with open(path, "w") as f:
            f.write("nicht-parsebar\n")
            f.write(json.dumps({"run_ts": "2026-05-14T10:17:00Z",
                                "provider": "x", "tier": 1,
                                "schema_v": 1, "run_phase": "premarket",
                                "http_status": 200, "latency_ms": 100,
                                "item_count": 1, "coverage_pct": None,
                                "nan_pct": None, "error": None}) + "\n")
        hc.prune_provider_log(max_days=30, path=path)
        content = open(path).read()
        assert "nicht-parsebar" in content, "kaputte Zeile gelöscht — Datenverlust"
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


# ── Fail-soft ──────────────────────────────────────────────────────────────


def test_record_does_not_raise_on_bad_path():
    ok = hc.record_provider_call(
        "yahoo_screener", 1, 100, 200, 1,
        run_phase="premarket",
        path="/nonexistent/dir/provider_health.jsonl",
    )
    assert ok is False


# ── Tier-Constants ─────────────────────────────────────────────────────────


def test_tier_constants_match_pr1_scope():
    # finviz wurde 19.05.2026 von Tier 1 → Tier 2 verschoben (Stufe-3-
    # Fallback, nicht primär). Bleibt im EXPECTED-Map als Coverage-Eintrag.
    for key in ("yahoo_screener", "yfinance_batch", "yfinance_singletons"):
        assert key in HEALTH_CHECK_PROVIDER_TIER, (
            f"PR-1-Provider {key!r} fehlt in HEALTH_CHECK_PROVIDER_TIER")
        assert HEALTH_CHECK_PROVIDER_TIER[key] == 1, (
            f"Provider {key!r} sollte Tier 1 sein")
        assert key in HEALTH_CHECK_PROVIDER_EXPECTED
    assert HEALTH_CHECK_PROVIDER_TIER.get("finviz") == 2, (
        "finviz sollte seit 19.05.2026 Tier 2 sein (Stufe-3-Fallback)")
    assert "finviz" in HEALTH_CHECK_PROVIDER_EXPECTED


def test_yfinance_singletons_expected_is_3():
    assert HEALTH_CHECK_PROVIDER_EXPECTED["yfinance_singletons"] == 3, (
        "yfinance_singletons expected = 3 (VIX + SPY + FX)")


# ── Source-Inspektion: Instrumentierung sitzt am richtigen Call-Site ──────


def test_yahoo_screener_instrumented():
    """yahoo_screener-record_provider_call existiert direkt nach
    get_yahoo_screener_candidates()-Aufruf."""
    assert 'provider="yahoo_screener"' in SRC_GR, (
        "yahoo_screener-record_provider_call fehlt in generate_report.py")
    # Aufruf ist zeitlich nach get_yahoo_screener_candidates()
    idx_call = SRC_GR.find("candidates = get_yahoo_screener_candidates()")
    idx_rec  = SRC_GR.find('provider="yahoo_screener"')
    assert 0 < idx_call < idx_rec, (
        "yahoo_screener-Record sollte NACH dem Call stehen")


def test_finviz_aggregator_present():
    assert "_FINVIZ_ACCT" in SRC_GR, "Finviz-Aggregator fehlt"
    assert "_finviz_acct_reset" in SRC_GR
    assert "_finviz_acct_record" in SRC_GR
    # Final-Emission existiert
    assert 'provider="finviz"' in SRC_GR, (
        "Finviz-Aggregator-Emission fehlt")


def test_finviz_v161_and_v111_call_sites_instrumented():
    """Beide Screener-Aufrufe füttern den Aggregator."""
    # Block um get_finviz_candidates herum
    m = re.search(
        r"candidates = get_finviz_candidates\([^)]*\)\s*\n\s*"
        r"_finviz_acct_record\(",
        SRC_GR, re.DOTALL,
    )
    assert m, "v161-Call wird nicht instrumentiert"
    m2 = re.search(
        r"fv_extra = get_finviz_screener_v111\(\)\s*\n\s*"
        r"_finviz_acct_record\(",
        SRC_GR, re.DOTALL,
    )
    assert m2, "v111-Call wird nicht instrumentiert"


def test_finviz_quote_page_fallback_instrumented():
    """Per-Ticker-Quote-Page-Fallback in get_short_float_with_fallback
    füttert ebenfalls den Aggregator (Latency-Beitrag, kein item_count)."""
    body = SRC_GR[SRC_GR.find("def get_short_float_with_fallback"):]
    body = body[:body.find("\ndef ")]  # bis nächste Top-Level-Funktion
    assert "_finviz_acct_record(" in body, (
        "_fetch_short_float_finviz wird nicht instrumentiert "
        "(Quote-Page-Fallback)")


def test_yfinance_batch_instrumented():
    assert 'provider="yfinance_batch"' in SRC_GR, (
        "yfinance_batch-record_provider_call fehlt")
    # Aufruf nach dem batch_yfd-Assignment
    idx_batch = SRC_GR.find("batch_yfd = _yf_ex.submit(get_yfinance_batch")
    idx_rec   = SRC_GR.find('provider="yfinance_batch"')
    assert 0 < idx_batch < idx_rec


def test_yfinance_batch_coverage_pct_computed():
    """coverage_pct = ok_items / pool_size × 100."""
    assert "_yfb_ok_items" in SRC_GR
    assert "_yfb_cov" in SRC_GR
    # Field wird in record_provider_call durchgereicht
    block = SRC_GR[SRC_GR.find('provider="yfinance_batch"'):]
    block = block[:block.find("\n        )")]
    assert "coverage_pct=" in block, (
        "yfinance_batch übergibt kein coverage_pct")


def test_yfinance_singletons_daily_run_side():
    """Daily-Run emittiert yfinance_singletons-Zeile (SPY + FX, max 2)."""
    assert SRC_GR.count('provider="yfinance_singletons"') >= 1, (
        "yfinance_singletons-Emission im Daily-Run fehlt")
    assert "_yfs_spy_ok" in SRC_GR
    assert "_yfs_fx_ok" in SRC_GR
    # Beide Boolean-Flags werden in der Emission-Logik konsumiert
    block_idx = SRC_GR.find('provider="yfinance_singletons"')
    pre = SRC_GR[max(0, block_idx - 600):block_idx]
    assert "_yfs_items = int(_yfs_spy_ok) + int(_yfs_fx_ok)" in pre, (
        "Daily-Run-Emission rechnet items nicht aus SPY+FX-Flags")


def test_yfinance_singletons_ki_agent_side():
    """KI-Agent emittiert eigene yfinance_singletons-Zeile (VIX)."""
    assert 'provider="yfinance_singletons"' in SRC_KI, (
        "yfinance_singletons-Emission im KI-Agent fehlt (VIX)")
    # KI-Agent-Zeile nutzt run_phase="ki_agent_tick"
    block_idx = SRC_KI.find('provider="yfinance_singletons"')
    block_end = SRC_KI.find(")", block_idx)
    block_full = SRC_KI[block_idx:block_end + 1]
    assert 'run_phase="ki_agent_tick"' in block_full or \
           "ki_agent_tick" in SRC_KI[block_idx:block_idx + 800], (
        "KI-Agent-Emission nutzt nicht run_phase='ki_agent_tick'")


# ── Wrapper-Pattern: try/finally + Pass/Fail-Pfad pro Provider ════════════


def _provider_record_try(src: str, provider: str,
                         call_name: str = "record_provider_call"):
    """Distanz-UNABHÄNGIGER Anker (statt Byte-Fenster): parse die Quelle per
    AST und finde die ``try``-Anweisung, in deren ``finally`` ein
    ``<call_name>(provider="<provider>", …)`` steht. Immun gegen Kommentar-/
    Whitespace-Änderungen in der Nähe.

    Lesson #325: das alte ``_block_around``-Byte-Fenster (before=800/600)
    brach, als ein +600-Zeichen-Kommentarblock im finally die Struktur-
    Keywords aus dem Fenster schob (finally bei Distanz 812 > 800) —
    obwohl der Code funktional unverändert war. AST kennt keine Distanz.

    Gibt den ``ast.Try``-Knoten zurück oder ``None``.
    """
    def _call_named(call: ast.Call) -> bool:
        f = call.func
        return ((isinstance(f, ast.Attribute) and f.attr == call_name)
                or (isinstance(f, ast.Name) and f.id == call_name))

    def _has_provider(call: ast.Call) -> bool:
        return any(k.arg == "provider"
                   and isinstance(k.value, ast.Constant)
                   and k.value.value == provider
                   for k in call.keywords)

    match = None
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Try):
            continue
        for fin_stmt in node.finalbody:
            for sub in ast.walk(fin_stmt):
                if (isinstance(sub, ast.Call) and _call_named(sub)
                        and _has_provider(sub)):
                    match = node
    return match


def _try_has_except_raise(try_node: ast.Try) -> bool:
    """True wenn mindestens ein ``except``-Handler ein ``raise`` enthält
    (Exception bubbelt durch, wird nicht geschluckt)."""
    return any(isinstance(sub, ast.Raise)
               for handler in try_node.handlers
               for sub in ast.walk(handler))


def test_yahoo_screener_uses_try_finally():
    """Wrapper muss try/finally nutzen, damit Latency auch bei Exception
    in record_provider_call landet. (Return non-None ⇒ record liegt im
    finally eines try-Blocks.)"""
    t = _provider_record_try(SRC_GR, "yahoo_screener")
    assert t is not None and t.finalbody, (
        "yahoo_screener-record_provider_call steht nicht im finally eines "
        "try-Blocks — Latency-Capture bei Exception nicht garantiert")


def test_yahoo_screener_exception_bubbles():
    """Wrapper darf Exceptions NICHT swallowen — except-Handler muss raise enthalten."""
    t = _provider_record_try(SRC_GR, "yahoo_screener")
    assert t is not None and _try_has_except_raise(t), (
        "yahoo_screener-Wrapper bubbelt Exceptions nicht durch")


def test_yfinance_batch_uses_try_finally():
    t = _provider_record_try(SRC_GR, "yfinance_batch")
    assert t is not None and t.finalbody, (
        "yfinance_batch-Wrapper hat kein try/finally")


def test_yfinance_batch_exception_bubbles():
    t = _provider_record_try(SRC_GR, "yfinance_batch")
    assert t is not None and _try_has_except_raise(t), (
        "yfinance_batch-Wrapper bubbelt Exceptions nicht durch")


def test_yfinance_singletons_ki_uses_try_finally():
    t = _provider_record_try(SRC_KI, "yfinance_singletons")
    assert t is not None and t.finalbody, (
        "yfinance_singletons (KI-Agent) hat kein try/finally")


def test_yfinance_singletons_ki_exception_bubbles():
    t = _provider_record_try(SRC_KI, "yfinance_singletons")
    assert t is not None and _try_has_except_raise(t), (
        "yfinance_singletons (KI-Agent) bubbelt Exceptions nicht durch")


def test_wrapper_pattern_replication_latency_captured_on_exception():
    """Pythonische Replikation des try/finally-Wrapper-Patterns: bei
    Exception muss Latency dennoch im record-Block landen."""
    import time as _time
    captured = {"latency_ms": None, "called": False}

    def fake_record(latency_ms):
        captured["latency_ms"] = latency_ms
        captured["called"] = True

    def wrapped_call(should_raise: bool):
        t0 = _time.perf_counter()
        try:
            if should_raise:
                raise RuntimeError("simulated")
            return "ok"
        finally:
            fake_record(int((_time.perf_counter() - t0) * 1000))

    # Fail-Pfad: Exception bubbelt + Latency wurde captured
    try:
        wrapped_call(True)
        assert False, "Exception sollte gebubbelt sein"
    except RuntimeError:
        pass
    assert captured["called"], "record() wurde nicht aus finally aufgerufen"
    assert captured["latency_ms"] is not None and captured["latency_ms"] >= 0


def test_wrapper_pattern_replication_pass_path():
    """Pass-Pfad: gleicher Wrapper, kein Exception, Latency captured."""
    import time as _time
    captured = {"latency_ms": None, "called": False}

    def fake_record(latency_ms):
        captured["latency_ms"] = latency_ms
        captured["called"] = True

    def wrapped_call():
        t0 = _time.perf_counter()
        try:
            return "ok"
        finally:
            fake_record(int((_time.perf_counter() - t0) * 1000))

    result = wrapped_call()
    assert result == "ok"
    assert captured["called"]
    assert captured["latency_ms"] is not None and captured["latency_ms"] >= 0


def test_wrapper_record_failure_does_not_break_pipeline():
    """Wenn record_provider_call selbst crasht, darf der Wrapper NICHT
    raisen — Pipeline-Robustheit."""
    import time as _time

    def wrapped_call():
        t0 = _time.perf_counter()
        try:
            return "ok"
        finally:
            try:
                # Simulierter Crash von record_provider_call
                raise OSError("disk full")
            except Exception:
                pass  # genauso wie health_check.record_provider_call intern

    # Darf NICHT raisen
    result = wrapped_call()
    assert result == "ok"


# ── Pass / Fail per Tier-1-Provider via record-Schema ═════════════════════


def test_provider_pass_path_writes_status_200():
    """Pass-Pfad pro Provider: erfolgreicher Call schreibt http_status=200
    und item_count > 0."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        for prov in ("yahoo_screener", "finviz", "yfinance_batch",
                     "yfinance_singletons"):
            hc.record_provider_call(
                provider=prov, tier=1, latency_ms=1500,
                http_status=200, item_count=50,
                run_phase="premarket", path=path,
            )
        entries = hc.read_all_provider(path)
        assert len(entries) == 4
        for e in entries:
            assert e["http_status"] == 200
            assert e["item_count"] > 0
            assert e["error"] is None
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


def test_provider_fail_path_writes_error_string():
    """Fail-Pfad pro Provider: gescheiterter Call schreibt http_status=null,
    error-String, item_count=0."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        for prov, err in [("yahoo_screener", "empty_result"),
                           ("finviz", "2/3 calls failed"),
                           ("yfinance_batch", "timeout_after_45s"),
                           ("yfinance_singletons", "spy_failed")]:
            hc.record_provider_call(
                provider=prov, tier=1, latency_ms=45000,
                http_status=None, item_count=0,
                error=err,
                run_phase="premarket", path=path,
            )
        entries = hc.read_all_provider(path)
        assert len(entries) == 4
        for e in entries:
            assert e["http_status"] is None
            assert e["item_count"] == 0
            assert e["error"] is not None
            assert isinstance(e["error"], str) and len(e["error"]) > 0
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


def test_provider_partial_failure_path():
    """yfinance_singletons Daily-Run-Seite: ein Symbol erfolgreich,
    eines nicht — item_count=1, coverage_pct=50.0, error='spy_failed'."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        hc.record_provider_call(
            provider="yfinance_singletons", tier=1, latency_ms=20000,
            http_status=None, item_count=1, coverage_pct=50.0,
            error="spy_failed",
            run_phase="premarket", path=path,
        )
        e = hc.read_all_provider(path)[0]
        assert e["item_count"] == 1
        assert e["coverage_pct"] == 50.0
        assert e["error"] == "spy_failed"
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


# ── Phase-1-Sister-Tests bleiben unverändert =================================


def test_phase1_state_invariants_intact():
    """Strikt: dieser PR darf Phase 1 State-Invariants nicht brechen."""
    assert "def evaluate_state_invariants" in open(
        ROOT / "health_check.py").read()
    assert "def record_run" in open(ROOT / "health_check.py").read()
    assert "def run_and_record" in open(ROOT / "health_check.py").read()


def test_no_unescaped_js_template_vars():
    hits = re.findall(r"\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}", SRC_GR)
    assert not hits, f"Unescapte JS-Template-Vars: {hits[:5]}"


# ── Runner =================================================================


def main() -> None:
    tests = [
        # Schema + Persistenz
        ("record_provider_call schreibt schema_v=1",     test_record_writes_schema_v1),
        ("record_provider_call append-only",             test_record_append_only),
        ("record_provider_call mit Fehler-String",       test_record_fail_with_error_string),
        # Prune
        ("prune_provider_log entfernt alte, behält frische",
         test_prune_removes_old_keeps_fresh),
        ("prune_provider_log behält kaputte Zeilen",     test_prune_preserves_broken_lines),
        # Fail-soft
        ("record crasht nicht bei Bad-Path",             test_record_does_not_raise_on_bad_path),
        # Konstanten
        ("Tier-Konstanten decken PR-1-Scope",            test_tier_constants_match_pr1_scope),
        ("yfinance_singletons expected = 3",             test_yfinance_singletons_expected_is_3),
        # Source-Inspektion
        ("yahoo_screener-Instrumentierung am Call-Site", test_yahoo_screener_instrumented),
        ("Finviz-Aggregator + Final-Emission existieren", test_finviz_aggregator_present),
        ("Finviz v161/v111-Calls werden instrumentiert", test_finviz_v161_and_v111_call_sites_instrumented),
        ("Finviz Quote-Page-Fallback instrumentiert",    test_finviz_quote_page_fallback_instrumented),
        ("yfinance_batch-Instrumentierung am Call-Site", test_yfinance_batch_instrumented),
        ("yfinance_batch übergibt coverage_pct",         test_yfinance_batch_coverage_pct_computed),
        ("yfinance_singletons Daily-Run-Seite (SPY+FX)", test_yfinance_singletons_daily_run_side),
        ("yfinance_singletons KI-Agent-Seite (VIX)",     test_yfinance_singletons_ki_agent_side),
        # Wrapper-Pattern: try/finally + Exception-Bubble
        ("yahoo_screener-Wrapper try/finally",           test_yahoo_screener_uses_try_finally),
        ("yahoo_screener-Wrapper Exception bubbelt",     test_yahoo_screener_exception_bubbles),
        ("yfinance_batch-Wrapper try/finally",           test_yfinance_batch_uses_try_finally),
        ("yfinance_batch-Wrapper Exception bubbelt",     test_yfinance_batch_exception_bubbles),
        ("yfinance_singletons KI-Wrapper try/finally",   test_yfinance_singletons_ki_uses_try_finally),
        ("yfinance_singletons KI-Wrapper Exception bubbelt",
         test_yfinance_singletons_ki_exception_bubbles),
        # Pythonische Wrapper-Pattern-Replikation
        ("Wrapper-Pattern: Latency-Capture bei Exception",
         test_wrapper_pattern_replication_latency_captured_on_exception),
        ("Wrapper-Pattern: Pass-Pfad Latency-Capture",
         test_wrapper_pattern_replication_pass_path),
        ("Wrapper-Pattern: record-Crash bricht Pipeline nicht",
         test_wrapper_record_failure_does_not_break_pipeline),
        # Pass + Fail-Pfad per Provider
        ("Pass-Pfad pro Provider (http_status=200)",     test_provider_pass_path_writes_status_200),
        ("Fail-Pfad pro Provider (error-String)",        test_provider_fail_path_writes_error_string),
        ("Partial-Failure-Pfad (yfinance_singletons)",   test_provider_partial_failure_path),
        # Phase-1-Sister
        ("Phase 1 State-Invariants unverändert",         test_phase1_state_invariants_intact),
        ("Keine unescapten ${...} im f-String",          test_no_unescaped_js_template_vars),
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
