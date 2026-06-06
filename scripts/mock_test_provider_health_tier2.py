"""Mock-Tests für Health-Check Phase 2 PR 2 — Tier-2-Provider.

Pro Tier-2-Provider:
  - Source-Inspektion: Wrapper sitzt am richtigen Call-Site
  - Source-Inspektion: try/finally-Pattern + Exception bubbelt
  - Pass-Pfad + Fail-Pfad via record-Schema
  - Special: finnhub "call_attempted=True"-Gating (calls > 0)
  - Special: stockanalysis ENABLED-Gating (kein Wrapper bei Flag=False)
  - Special: earningswhispers nan_pct-Berechnung

Zusätzlich: _instrument_provider_call-Helper-Pythonische Replikation
(Pass/Fail/Exception, Akkumulator-Update).

Ausführung: ``python scripts/mock_test_provider_health_tier2.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys
import tempfile
import time
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402
from config import (        # noqa: E402
    HEALTH_CHECK_PROVIDER_TIER,
    HEALTH_CHECK_PROVIDER_EXPECTED,
)

SRC_GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
SRC_KI = (ROOT / "ki_agent.py").read_text(encoding="utf-8")


def _provider_call_node(src: str, provider: str,
                        call_name: str = "record_provider_call"):
    """AST-Anker: finde den Call ``<call_name>(provider="<provider>", …)`` +
    Parse-Tree. Distanz-/Whitespace-immun (Lesson #325/#327) — ersetzt das
    fragile Byte-Fenster ``_block_around``."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        named = ((isinstance(f, ast.Attribute) and f.attr == call_name)
                 or (isinstance(f, ast.Name) and f.id == call_name))
        if named and any(k.arg == "provider"
                         and isinstance(k.value, ast.Constant)
                         and k.value.value == provider
                         for k in node.keywords):
            return node, tree
    return None, tree


def _call_kwarg(call: ast.Call, name: str):
    """AST-Wert des Keyword-Arguments ``name`` im Call (oder None)."""
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _enclosing_if_src(src: str, tree: ast.AST, target: ast.AST):
    """Source-Segment der NÄCHSTEN umschließenden ``if``-Anweisung um target
    (innermost). AST-begrenzt statt Byte-Fenster → übersteht Kommentar-/
    Einrückungs-/Zeilenumbruch-Verschiebungen nahe dem Anker (Lesson #327).
    Returnt das Segment (str) oder None."""
    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and any(s is target for s in ast.walk(node)):
            if best is None or node.lineno > best.lineno:
                best = node
    return ast.get_source_segment(src, best) if best else None


def _provider_record_try(src: str, provider: str,
                         call_name: str = "record_provider_call"):
    """Distanz-UNABHÄNGIGER Anker (statt Byte-Fenster): parse die Quelle per
    AST und finde die ``try``-Anweisung, in deren ``finally`` ein
    ``<call_name>(provider="<provider>", …)`` steht. Immun gegen Kommentar-/
    Whitespace-Änderungen in der Nähe (Lesson #325). Gibt den ``ast.Try``-
    Knoten zurück oder ``None``."""
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
    """True wenn mindestens ein ``except``-Handler ein ``raise`` enthält."""
    return any(isinstance(sub, ast.Raise)
               for handler in try_node.handlers
               for sub in ast.walk(handler))


# ── Tier-Konstanten ════════════════════════════════════════════════════════


def test_tier2_keys_in_config():
    for key in ("finra", "finnhub", "stockanalysis", "earningswhispers"):
        assert key in HEALTH_CHECK_PROVIDER_TIER, (
            f"Tier-2-Provider {key!r} fehlt in HEALTH_CHECK_PROVIDER_TIER")
        assert HEALTH_CHECK_PROVIDER_TIER[key] == 2
        assert key in HEALTH_CHECK_PROVIDER_EXPECTED


# ── FINRA (ki_agent.py:fetch_finra_ssr) ════════════════════════════════════


def test_finra_instrumented():
    assert 'provider="finra"' in SRC_KI, (
        "finra-Instrumentierung fehlt in ki_agent.py")
    # Anchor: Aufruf an fetch_finra_ssr ist in einem try-Block
    idx_call = SRC_KI.find("finra_ssr_data = fetch_finra_ssr(tickers)")
    idx_rec  = SRC_KI.find('provider="finra"')
    assert 0 < idx_call < idx_rec, (
        "finra-Record muss NACH dem Call stehen")


def test_finra_uses_try_finally():
    t = _provider_record_try(SRC_KI, "finra")
    assert t is not None and t.finalbody, (
        "finra-Wrapper hat kein try/finally")


def test_finra_exception_bubbles():
    t = _provider_record_try(SRC_KI, "finra")
    assert t is not None and _try_has_except_raise(t), (
        "finra-Wrapper bubbelt Exceptions nicht durch")


def test_finra_run_phase_is_ki_agent_tick():
    # AST-robust: prüft das run_phase-Keyword AM finra-record_provider_call
    # selbst (statt String im Byte-Fenster). Semantik identisch: der Call
    # muss run_phase="ki_agent_tick" setzen.
    call, _ = _provider_call_node(SRC_KI, "finra")
    rp = _call_kwarg(call, "run_phase") if call else None
    assert isinstance(rp, ast.Constant) and rp.value == "ki_agent_tick", (
        "finra läuft im ki_agent — record_provider_call muss "
        'run_phase="ki_agent_tick" setzen')


# ── Finnhub (call_attempted gated) ═════════════════════════════════════════


def test_finnhub_accumulator_present():
    assert "_FINNHUB_ACCT" in SRC_GR, "Finnhub-Akkumulator fehlt"
    assert "_provider_acct_reset(_FINNHUB_ACCT)" in SRC_GR, (
        "Finnhub-Akkumulator wird in main() nicht zurückgesetzt")


def test_finnhub_instrument_call_at_call_site():
    """Helper _instrument_provider_call(_FINNHUB_ACCT, _fetch_finnhub_next_earnings, …)
    ersetzt den direkten Aufruf in _fetch_next_earnings_date."""
    pat = re.compile(
        r"_instrument_provider_call\(\s*_FINNHUB_ACCT\s*,\s*"
        r"_fetch_finnhub_next_earnings", re.DOTALL,
    )
    assert pat.search(SRC_GR), (
        "_fetch_finnhub_next_earnings wird nicht durch _instrument_provider_call gewrappt")


def test_finnhub_emit_gated_by_calls():
    """End-of-main-Emission nur wenn _FINNHUB_ACCT['calls'] > 0."""
    # AST-robust: das Gating-Statement ist die umschließende if-Anweisung des
    # record_provider_call. Prüfe die Gating-Bedingung im AST-begrenzten
    # if-Segment (statt Byte-Fenster). Semantik identisch.
    call, tree = _provider_call_node(SRC_GR, "finnhub")
    if_src = _enclosing_if_src(SRC_GR, tree, call) if call else None
    assert if_src is not None and '_fh_acct["calls"] > 0' in if_src, (
        "Finnhub-Emission ist nicht durch calls>0 gegated — würde leere "
        "Zeilen schreiben wenn keine Positionen offen")


# ── Stockanalysis (ENABLED-gated aggregate) ════════════════════════════════


def test_stockanalysis_accumulator_present():
    assert "_STOCKANALYSIS_ACCT" in SRC_GR, "Stockanalysis-Akkumulator fehlt"
    assert "_provider_acct_reset(_STOCKANALYSIS_ACCT)" in SRC_GR


def test_stockanalysis_borrow_path_wrapped_under_enabled_gate():
    """fetch_borrow_metrics-Aufruf läuft durch _instrument_provider_call
    NUR wenn STOCKANALYSIS_BORROW_ENABLED.

    Quellenwechsel 01.06.2026: nutzt seither eigenen ``_BORROW_ACCT``
    (vorher ``_STOCKANALYSIS_ACCT``) — Borrow-Pfad ist getrennt vom
    SI-Pfad, damit stiller iBorrowDesk-Tod nicht in gemischter
    coverage_pct ~50 % knapp unter Tier-2-Schwelle durchrutscht.
    """
    block = SRC_GR[SRC_GR.find("if IBKR_BORROW_ENABLED or STOCKANALYSIS_BORROW_ENABLED:"):]
    block = block[:block.find("\n    top10.sort")]
    assert "if STOCKANALYSIS_BORROW_ENABLED:" in block, (
        "Stockanalysis-Borrow-Pfad hat keinen ENABLED-Gate auf "
        "Instrumentierung")
    # Akku ist seit 01.06.2026 _BORROW_ACCT (eigener Akku, Trennung
    # vom _STOCKANALYSIS_ACCT-SI-Pfad).
    assert "_instrument_provider_call(\n                    _BORROW_ACCT" in block \
        or "_instrument_provider_call(_BORROW_ACCT, fetch_borrow_metrics" in block, (
        "fetch_borrow_metrics wird nicht durch _instrument_provider_call "
        "mit _BORROW_ACCT gewrappt")


def test_stockanalysis_si_path_wrapped():
    """fetch_stockanalysis_si im ThreadPoolExecutor durch helper gewrappt."""
    pat = re.compile(
        r"_sa_ex\.submit\(\s*_instrument_provider_call\s*,\s*"
        r"_STOCKANALYSIS_ACCT\s*,\s*fetch_stockanalysis_si",
        re.DOTALL,
    )
    assert pat.search(SRC_GR), (
        "fetch_stockanalysis_si wird im ThreadPoolExecutor nicht gewrappt")


def test_stockanalysis_emit_gated_by_calls():
    # AST-robust (umschließendes if-Segment statt Byte-Fenster), Semantik gleich.
    call, tree = _provider_call_node(SRC_GR, "stockanalysis")
    if_src = _enclosing_if_src(SRC_GR, tree, call) if call else None
    assert if_src is not None and '_sa_acct["calls"] > 0' in if_src, (
        "Stockanalysis-Emission ist nicht durch calls>0 gegated")


# ── EarningsWhispers (ENABLED-gated, inline try/finally) ═════════════════


def test_earningswhispers_instrumented():
    assert 'provider="earningswhispers"' in SRC_GR, (
        "earningswhispers-Instrumentierung fehlt")


def test_earningswhispers_outer_enabled_gate():
    """ENABLED-Flag muss VOR dem try/finally gechecked werden — sonst
    würde der Wrapper bei Disabled eine Zeile schreiben."""
    block_start = SRC_GR.find("if EARNINGSWHISPERS_ENABLED:")
    block_end   = SRC_GR.find('provider="earningswhispers"')
    assert 0 < block_start < block_end, (
        "EARNINGSWHISPERS_ENABLED-Gate fehlt vor der Instrumentierung")


def test_earningswhispers_uses_try_finally():
    t = _provider_record_try(SRC_GR, "earningswhispers")
    assert t is not None and t.finalbody, (
        "earningswhispers-Wrapper hat kein try/finally")


def test_earningswhispers_exception_bubbles():
    t = _provider_record_try(SRC_GR, "earningswhispers")
    assert t is not None and _try_has_except_raise(t), (
        "earningswhispers-Wrapper bubbelt Exceptions nicht durch")


def test_earningswhispers_nan_pct_computed():
    """nan_pct = items mit fehlender date / total."""
    # AST-robust: die nan_pct-Berechnung lebt im umschließenden
    # EARNINGSWHISPERS_ENABLED-if-Block des record_provider_call; der
    # nan_pct-Wert ist ein Keyword AM Call. Beides AST-begrenzt statt
    # Byte-Fenster. Semantik identisch.
    call, tree = _provider_call_node(SRC_GR, "earningswhispers")
    assert call is not None, "earningswhispers-record_provider_call fehlt"
    if_src = _enclosing_if_src(SRC_GR, tree, call)
    assert if_src is not None and "_ew_missing_date" in if_src, (
        "nan_pct-Berechnung (_ew_missing_date) fehlt im EnableD-Block")
    assert 'not v.get("date")' in if_src, (
        "nan_pct-Berechnung prüft nicht .get('date')")
    # nan_pct wird in record-Call durchgereicht (AST-kwarg, kein String-Pin)
    nan = _call_kwarg(call, "nan_pct")
    assert isinstance(nan, ast.Name) and nan.id == "_ew_nan", (
        "earningswhispers reicht nan_pct=_ew_nan nicht in record_provider_call")


# ── _instrument_provider_call-Helper (Pythonische Replikation) ════════════
#
# Da generate_report.py yfinance importiert (nicht in Test-Env verfügbar),
# replizieren wir die Helper-Logik 1:1 und testen damit.


def _make_helper():
    """Pythonisches Replikat von generate_report._instrument_provider_call."""
    def _provider_acct_record(acct, latency_ms, success):
        acct["latency_ms"] += int(latency_ms)
        acct["calls"]      += 1
        if success:
            acct["successes"] += 1
        else:
            acct["failures"] += 1

    def helper(acct, fn, *args, **kwargs):
        t0 = time.perf_counter()
        result = None
        raised = False
        try:
            result = fn(*args, **kwargs)
            return result
        except Exception:
            raised = True
            raise
        finally:
            try:
                ok = (not raised) and (result is not None) and (
                    result if not isinstance(result, (dict, list, tuple, set))
                    else len(result) > 0
                )
                _provider_acct_record(
                    acct,
                    int((time.perf_counter() - t0) * 1000),
                    success=bool(ok),
                )
            except Exception:
                pass
    return helper


def test_helper_pass_path():
    helper = _make_helper()
    acct = {"latency_ms": 0, "calls": 0, "failures": 0, "successes": 0}
    result = helper(acct, lambda: "ok")
    assert result == "ok"
    assert acct["calls"] == 1
    assert acct["successes"] == 1
    assert acct["failures"] == 0


def test_helper_fail_none_return():
    helper = _make_helper()
    acct = {"latency_ms": 0, "calls": 0, "failures": 0, "successes": 0}
    result = helper(acct, lambda: None)
    assert result is None
    assert acct["calls"] == 1
    assert acct["failures"] == 1
    assert acct["successes"] == 0


def test_helper_fail_empty_dict():
    helper = _make_helper()
    acct = {"latency_ms": 0, "calls": 0, "failures": 0, "successes": 0}
    result = helper(acct, lambda: {})
    assert result == {}
    assert acct["calls"] == 1
    assert acct["failures"] == 1


def test_helper_pass_nonempty_dict():
    helper = _make_helper()
    acct = {"latency_ms": 0, "calls": 0, "failures": 0, "successes": 0}
    result = helper(acct, lambda: {"a": 1})
    assert result == {"a": 1}
    assert acct["successes"] == 1


def test_helper_exception_bubbles_and_records():
    helper = _make_helper()
    acct = {"latency_ms": 0, "calls": 0, "failures": 0, "successes": 0}
    try:
        helper(acct, lambda: (_ for _ in ()).throw(ValueError("simulated")))
        assert False, "Exception sollte gebubbelt sein"
    except ValueError:
        pass
    assert acct["calls"] == 1
    assert acct["failures"] == 1
    assert acct["latency_ms"] >= 0


def test_helper_accumulates_across_multiple_calls():
    helper = _make_helper()
    acct = {"latency_ms": 0, "calls": 0, "failures": 0, "successes": 0}
    helper(acct, lambda: "a")
    helper(acct, lambda: None)
    helper(acct, lambda: "b")
    assert acct["calls"] == 3
    assert acct["successes"] == 2
    assert acct["failures"] == 1


# ── Pass / Fail-Pfad per Tier-2-Provider (record-Schema) ══════════════════


def test_tier2_pass_path_writes_status_200():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        for prov in ("finra", "finnhub", "stockanalysis", "earningswhispers"):
            hc.record_provider_call(
                provider=prov, tier=2, latency_ms=1500,
                http_status=200, item_count=10,
                run_phase="premarket", path=path,
            )
        entries = hc.read_all_provider(path)
        assert len(entries) == 4
        for e in entries:
            assert e["tier"] == 2
            assert e["http_status"] == 200
            assert e["item_count"] > 0
            assert e["error"] is None
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


def test_tier2_fail_path_writes_error_string():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        for prov, err in [("finra", "empty_result"),
                           ("finnhub", "2/3 calls failed"),
                           ("stockanalysis", "1/5 calls failed"),
                           ("earningswhispers", "empty_result")]:
            hc.record_provider_call(
                provider=prov, tier=2, latency_ms=5000,
                http_status=None, item_count=0,
                error=err,
                run_phase="premarket", path=path,
            )
        entries = hc.read_all_provider(path)
        for e in entries:
            assert e["http_status"] is None
            assert e["item_count"] == 0
            assert e["error"] is not None
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


def test_earningswhispers_nan_pct_in_record():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        # 10 items total, 2 ohne date → nan_pct = 20.0
        hc.record_provider_call(
            provider="earningswhispers", tier=2, latency_ms=1200,
            http_status=200, item_count=10, nan_pct=20.0,
            run_phase="premarket", path=path,
        )
        e = hc.read_all_provider(path)[0]
        assert e["nan_pct"] == 20.0
        assert e["item_count"] == 10
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


# ── PR-1-Sister-Regression ════════════════════════════════════════════════


def test_pr1_tier1_keys_still_present():
    """Strikt: PR 2 darf PR 1 nicht versehentlich brechen.

    finviz wurde 19.05.2026 explizit von Tier 1 → Tier 2 verschoben
    (Stufe-3-Fallback-Klassifizierung), daher nicht mehr in dieser Liste.
    """
    for key in ("yahoo_screener", "yfinance_batch", "yfinance_singletons"):
        assert HEALTH_CHECK_PROVIDER_TIER.get(key) == 1


def test_provider_health_infrastructure_intact():
    assert hasattr(hc, "record_provider_call")
    assert hasattr(hc, "prune_provider_log")
    assert hasattr(hc, "read_all_provider")
    assert hc.SCHEMA_V_PROVIDER == 1


# ── Runner =================================================================


def main() -> None:
    tests = [
        # Konstanten
        ("Tier-2-Keys in HEALTH_CHECK_PROVIDER_TIER",      test_tier2_keys_in_config),
        # FINRA
        ("finra-Instrumentierung am Call-Site",            test_finra_instrumented),
        ("finra-Wrapper try/finally",                       test_finra_uses_try_finally),
        ("finra-Wrapper Exception bubbelt",                 test_finra_exception_bubbles),
        ("finra run_phase=ki_agent_tick",                   test_finra_run_phase_is_ki_agent_tick),
        # Finnhub
        ("Finnhub-Akkumulator + Reset vorhanden",           test_finnhub_accumulator_present),
        ("Finnhub-Call durch _instrument_provider_call",    test_finnhub_instrument_call_at_call_site),
        ("Finnhub-Emission durch calls>0 gegated",          test_finnhub_emit_gated_by_calls),
        # Stockanalysis
        ("Stockanalysis-Akkumulator + Reset vorhanden",     test_stockanalysis_accumulator_present),
        ("Stockanalysis-Borrow-Pfad unter ENABLED-Gate",    test_stockanalysis_borrow_path_wrapped_under_enabled_gate),
        ("Stockanalysis-SI-Pfad gewrappt im ThreadPool",    test_stockanalysis_si_path_wrapped),
        ("Stockanalysis-Emission durch calls>0 gegated",    test_stockanalysis_emit_gated_by_calls),
        # EarningsWhispers
        ("earningswhispers-Instrumentierung",               test_earningswhispers_instrumented),
        ("earningswhispers ENABLED-Gate aussen",            test_earningswhispers_outer_enabled_gate),
        ("earningswhispers-Wrapper try/finally",             test_earningswhispers_uses_try_finally),
        ("earningswhispers-Wrapper Exception bubbelt",       test_earningswhispers_exception_bubbles),
        ("earningswhispers nan_pct berechnet + persistiert", test_earningswhispers_nan_pct_computed),
        # Helper-Pythonische Replikation
        ("_instrument_provider_call: Pass-Pfad",            test_helper_pass_path),
        ("_instrument_provider_call: None-Return",          test_helper_fail_none_return),
        ("_instrument_provider_call: empty-dict",           test_helper_fail_empty_dict),
        ("_instrument_provider_call: nonempty-dict",        test_helper_pass_nonempty_dict),
        ("_instrument_provider_call: Exception bubbelt",    test_helper_exception_bubbles_and_records),
        ("_instrument_provider_call: Akkumulation",         test_helper_accumulates_across_multiple_calls),
        # Pass/Fail per Provider
        ("Pass-Pfad pro Tier-2-Provider (http_status=200)", test_tier2_pass_path_writes_status_200),
        ("Fail-Pfad pro Tier-2-Provider (error-String)",    test_tier2_fail_path_writes_error_string),
        ("earningswhispers nan_pct in Record",              test_earningswhispers_nan_pct_in_record),
        # PR-1-Regression
        ("PR-1 Tier-1-Keys unverändert",                    test_pr1_tier1_keys_still_present),
        ("Provider-Health-Infrastruktur unverändert",       test_provider_health_infrastructure_intact),
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
