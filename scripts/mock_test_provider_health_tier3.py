"""Mock-Tests für Health-Check Phase 2 PR 3 — Tier-3-Provider.

7 getrennte Provider-Keys (statt Spec-Wortlaut-Aggregate, Klärung
15.05.2026):
  stocktwits, uoa, news_rss, edgar_13f, edgar_8k, edgar_form4, edgar_13d_g

Pro Provider:
  - Source-Inspektion: Call-Site, success_check (für Tuple/Rich-Dict),
    try/finally implizit via instrument_provider_call
  - Pass-Pfad + Fail-Pfad via record-Schema
Plus Special-Tests:
  - EDGAR: 403 Rate-Limit als error persistiert (nicht als success)
  - News-RSS: partial failure (3 von 5 Sources) → calls=5, successes=3
  - success_check-Helper: Tuple-/Dict-Erfolgsdefinition korrekt
  - PR-1/2-Regression: Tier-1/2-Keys unverändert

Ausführung: ``python scripts/mock_test_provider_health_tier3.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

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

TIER3_KEYS = ("stocktwits", "uoa", "news_rss",
              "edgar_13f", "edgar_8k", "edgar_form4", "edgar_13d_g")


# ── Tier-Konstanten + Reuse aus health_check ══════════════════════════════


def test_all_seven_tier3_keys_in_config():
    for k in TIER3_KEYS:
        assert k in HEALTH_CHECK_PROVIDER_TIER, (
            f"Tier-3-Provider {k!r} fehlt in HEALTH_CHECK_PROVIDER_TIER")
        assert HEALTH_CHECK_PROVIDER_TIER[k] == 3, (
            f"Provider {k!r} sollte Tier 3 sein")
        assert k in HEALTH_CHECK_PROVIDER_EXPECTED


def test_instrument_provider_call_lives_in_health_check():
    """PR 3: Helper wurde aus generate_report.py nach health_check.py
    umgezogen für ki_agent.py-Reuse."""
    assert hasattr(hc, "instrument_provider_call"), (
        "instrument_provider_call fehlt in health_check (PR-3-Refactor)")
    assert hasattr(hc, "provider_acct_reset")
    assert hasattr(hc, "provider_acct_record")


def test_success_check_parameter_supported():
    """instrument_provider_call akzeptiert ``success_check``-Kwarg."""
    acct = {"latency_ms": 0, "calls": 0, "failures": 0, "successes": 0}
    # Tuple ``(False, "", None)`` ist truthy als Tuple (len > 0),
    # aber tuple[0]=False → mit success_check soll es als Failure zählen.
    result = hc.instrument_provider_call(
        acct, lambda: (False, "", None),
        success_check=lambda r: bool(r and r[0]),
    )
    assert result == (False, "", None)
    assert acct["calls"] == 1
    assert acct["failures"] == 1
    assert acct["successes"] == 0


def test_success_check_passes_when_tuple_first_is_true():
    acct = {"latency_ms": 0, "calls": 0, "failures": 0, "successes": 0}
    hc.instrument_provider_call(
        acct, lambda: (True, "8-K title", datetime.now(timezone.utc)),
        success_check=lambda r: bool(r and r[0]),
    )
    assert acct["successes"] == 1
    assert acct["failures"] == 0


def test_success_check_default_dict_with_zero_values_still_truthy():
    """Default-Heuristik (ohne success_check) würde ``{"k": 0}`` als
    success melden — daher müssen Tier-3-Provider mit Rich-Dict-Returns
    success_check mitgeben."""
    acct = {"latency_ms": 0, "calls": 0, "failures": 0, "successes": 0}
    hc.instrument_provider_call(acct, lambda: {"n_total": 0, "bull_ratio": None})
    # Default-Heuristik: nicht-leeres Dict → success. Dokumentiert.
    assert acct["successes"] == 1, (
        "Default-Heuristik sollte non-empty dict als success melden "
        "(daher braucht stocktwits explizites success_check)")


def test_success_check_handles_exception_in_check_function():
    """Wenn success_check selbst raised, fall-back auf Failure."""
    acct = {"latency_ms": 0, "calls": 0, "failures": 0, "successes": 0}
    def broken_check(r):
        raise ValueError("simulated check crash")
    hc.instrument_provider_call(
        acct, lambda: "ok", success_check=broken_check)
    assert acct["calls"] == 1
    assert acct["failures"] == 1


# ── Source-Inspektion: Tier-3-Akkumulatoren ═══════════════════════════════


def test_ki_agent_has_six_tier3_accumulators():
    for var in ("_STOCKTWITS_ACCT", "_UOA_ACCT", "_NEWS_RSS_ACCT",
                "_EDGAR_8K_ACCT", "_EDGAR_FORM4_ACCT", "_EDGAR_13D_G_ACCT"):
        assert var in SRC_KI, f"Akkumulator {var} fehlt in ki_agent.py"
    assert "_reset_tier3_accumulators" in SRC_KI


def test_generate_report_has_edgar_13f_accumulator():
    assert "_EDGAR_13F_ACCT" in SRC_GR
    assert "_provider_acct_reset(_EDGAR_13F_ACCT)" in SRC_GR


def test_ki_agent_main_resets_tier3_accumulators():
    """Reset-Aufruf am Anfang von main() vorhanden."""
    block = SRC_KI[SRC_KI.find("def main()"):]
    block = block[:block.find("\n\ndef ")]
    if len(block) > 5000:
        block = block[:5000]
    assert "_reset_tier3_accumulators()" in block, (
        "_reset_tier3_accumulators muss in ki_agent.main() aufgerufen werden")


# ── Source-Inspektion: Wrappers an Call-Sites ═════════════════════════════


def test_stocktwits_wrapped_with_success_check():
    pat = re.compile(
        r"instrument_provider_call\(\s*\n?\s*_STOCKTWITS_ACCT\s*,\s*"
        r"fetch_stocktwits_sentiment.*?success_check\s*=",
        re.DOTALL,
    )
    assert pat.search(SRC_KI), (
        "fetch_stocktwits_sentiment ist nicht durch instrument_provider_call "
        "mit success_check gewrappt")


def test_uoa_wrapped_with_success_check():
    pat = re.compile(
        r"instrument_provider_call\(\s*\n?\s*_UOA_ACCT\s*,\s*"
        r"fetch_uoa_signal.*?success_check\s*=",
        re.DOTALL,
    )
    assert pat.search(SRC_KI), (
        "fetch_uoa_signal ist nicht mit success_check gewrappt — "
        "Default-Heuristik würde Tuple (0,[],{}) als success melden")


def test_news_rss_wraps_yahoo_news():
    pat = re.compile(
        r"instrument_provider_call\(\s*\n?\s*_NEWS_RSS_ACCT\s*,\s*fetch_yahoo_news",
        re.DOTALL,
    )
    assert pat.search(SRC_KI), "fetch_yahoo_news läuft nicht durch news_rss-Wrapper"


def test_news_rss_wraps_all_five_rss_sources():
    """5+ RSS-Sources werden alle aggregiert (gemeinsamer Akkumulator).

    Mai 2026: finviz RSS-Feed deaktiviert (liefert HTML statt Feed),
    daher 5 statt vorher 6 Wrappings (Yahoo + 4 generische: Google,
    UnusualWhales, MarketBeat, SeekingAlpha).
    """
    # Heuristik: Anzahl Vorkommen von _NEWS_RSS_ACCT in Wrap-Position
    matches = re.findall(
        r"instrument_provider_call\(\s*\n?\s*_NEWS_RSS_ACCT", SRC_KI)
    assert len(matches) >= 5, (
        f"erwartet ≥ 5 News-RSS-Wrappings (Yahoo + 4 generische), "
        f"gefunden {len(matches)}")


def test_edgar_8k_wrapped_with_tuple_success_check():
    pat = re.compile(
        r"instrument_provider_call\(\s*\n?\s*_EDGAR_8K_ACCT\s*,\s*"
        r"fetch_sec_8k.*?success_check\s*=",
        re.DOTALL,
    )
    assert pat.search(SRC_KI), (
        "fetch_sec_8k muss mit success_check=lambda r: r[0] gewrappt sein")


def test_edgar_form4_wrapped_with_tuple_success_check():
    pat = re.compile(
        r"instrument_provider_call\(\s*\n?\s*_EDGAR_FORM4_ACCT\s*,\s*"
        r"fetch_sec_form4.*?success_check\s*=",
        re.DOTALL,
    )
    assert pat.search(SRC_KI), (
        "fetch_sec_form4 muss mit success_check=lambda r: r[0] gewrappt sein")


def test_edgar_13d_g_wrapped():
    pat = re.compile(
        r"instrument_provider_call\(\s*\n?\s*_EDGAR_13D_G_ACCT\s*,\s*"
        r"fetch_edgar_filings",
        re.DOTALL,
    )
    assert pat.search(SRC_KI), "fetch_edgar_filings ist nicht gewrappt"


def test_edgar_13f_wrapped_in_threadpool_submit():
    """edgar_13f läuft im Daily-Run ThreadPool — Wrap durch helper als
    submitable. Gleicher Pattern wie stockanalysis-SI in PR 2."""
    pat = re.compile(
        r"_13f_ex\.submit\(\s*\n?\s*_instrument_provider_call\s*,\s*"
        r"_EDGAR_13F_ACCT\s*,\s*fetch_sec_13f",
        re.DOTALL,
    )
    assert pat.search(SRC_GR), (
        "fetch_sec_13f wird im ThreadPool nicht durch _instrument_provider_call "
        "gewrappt")


# ── Emission-Block am Ende von main() ════════════════════════════════════


def test_ki_agent_emits_all_six_tier3_rows_gated():
    """End-of-ki_agent.main() iteriert über 6 Tier-3-Provider und
    emittiert nur bei calls > 0."""
    block_start = SRC_KI.find("# Health-Check Phase 2 PR 3 — Tier-3-Provider-Aggregator-Zeilen.")
    assert block_start > 0, "Tier-3-Emission-Block in ki_agent fehlt"
    block_end = SRC_KI.find("# Health-Check Phase 1", block_start)
    block = SRC_KI[block_start:block_end]
    for key in ("stocktwits", "uoa", "news_rss",
                "edgar_8k", "edgar_form4", "edgar_13d_g"):
        assert f'"{key}"' in block, (
            f"Tier-3-Emission für {key!r} fehlt im ki_agent-main-Block")
    assert 'acct["calls"] <= 0' in block, (
        "Emission ist nicht durch calls>0 gegated — würde leere Zeilen "
        "schreiben für nie aufgerufene Provider")


def test_generate_report_emits_edgar_13f_gated():
    # Erste Vorkommnis ist im Comment, zweite ist die echte record-Zeile.
    # Suche nach dem record_provider_call-Block direkt.
    rec_idx = SRC_GR.find('record_provider_call(\n                provider="edgar_13f"')
    assert rec_idx > 0, "edgar_13f record_provider_call-Block nicht gefunden"
    # Gate via _13f_acct["calls"] > 0 muss im Pre-Kontext stehen
    pre_block = SRC_GR[max(0, rec_idx - 600):rec_idx]
    assert '_13f_acct["calls"] > 0' in pre_block, (
        "edgar_13f-Emission ist nicht durch calls>0 gegated")


# ── Pass + Fail-Pfad per Provider (record-Schema) ═══════════════════════


def test_tier3_pass_path_writes_status_200():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        for prov in TIER3_KEYS:
            hc.record_provider_call(
                provider=prov, tier=3, latency_ms=900,
                http_status=200, item_count=5,
                run_phase="ki_agent_tick", path=path,
            )
        entries = hc.read_all_provider(path)
        assert len(entries) == 7
        for e in entries:
            assert e["tier"] == 3
            assert e["http_status"] == 200
            assert e["error"] is None
            assert e["item_count"] > 0
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


def test_tier3_fail_path_writes_error_string():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        for prov, err in [("stocktwits", "5/10 calls failed"),
                           ("uoa", "8/10 calls failed"),
                           ("news_rss", "3/30 calls failed"),
                           ("edgar_13f", "1/8 calls failed"),
                           ("edgar_8k", "10/10 calls failed"),
                           ("edgar_form4", "10/10 calls failed"),
                           ("edgar_13d_g", "1/1 calls failed")]:
            hc.record_provider_call(
                provider=prov, tier=3, latency_ms=2000,
                http_status=None, item_count=0,
                error=err,
                run_phase="ki_agent_tick", path=path,
            )
        entries = hc.read_all_provider(path)
        for e in entries:
            assert e["http_status"] is None
            assert e["error"] is not None
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


# ── EDGAR-Special: 403 Rate-Limit als Fehler-Pfad ════════════════════════


def test_edgar_403_recorded_as_failure_not_silent():
    """SEC EDGAR antwortet bei Rate-Limit mit HTTP 403. Mock-Provider-
    Funktion gibt leeres Resultat zurück; Default-Heuristik markiert
    leeres list/[]/dict als failure. Record-Eintrag persistiert
    item_count=0 + error-String (Phase 3 Digest erkennt das)."""
    acct = {"latency_ms": 0, "calls": 0, "failures": 0, "successes": 0}
    def edgar_403_mock():
        # fail-soft Return analog fetch_edgar_filings bei 403
        return []
    hc.instrument_provider_call(acct, edgar_403_mock)
    assert acct["calls"] == 1
    assert acct["failures"] == 1, (
        "EDGAR 403 → leere Liste muss als failure persistiert werden")
    assert acct["successes"] == 0


def test_edgar_403_provider_record_persists_error_message():
    """Record-Eintrag fuer EDGAR-403 ist diagnostizierbar."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        hc.record_provider_call(
            provider="edgar_13d_g", tier=3, latency_ms=12000,
            http_status=None, item_count=0,
            error="HTTP 403 rate_limited",
            run_phase="ki_agent_tick", path=path,
        )
        e = hc.read_all_provider(path)[0]
        assert "403" in e["error"]
        assert e["http_status"] is None
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


# ── News-RSS-Special: partial failure (3 von 5 Sources) ══════════════════


def test_news_rss_partial_failure_aggregation():
    """5 RSS-Source-Calls: 3 erfolgreich, 2 leer. Accumulator-State
    nach allen Calls: successes=3, failures=2, calls=5."""
    acct = {"latency_ms": 0, "calls": 0, "failures": 0, "successes": 0}
    # 3 erfolgreich (News-Items)
    for _ in range(3):
        hc.instrument_provider_call(acct, lambda: ["headline 1", "headline 2"])
    # 2 leere Listen (z. B. RSS down / rate-limited)
    for _ in range(2):
        hc.instrument_provider_call(acct, lambda: [])
    assert acct["calls"] == 5
    assert acct["successes"] == 3
    assert acct["failures"] == 2


def test_news_rss_partial_failure_persisted():
    """End-of-main emittiert eine Zeile mit dem aggregierten State."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        path = fh.name
    try:
        open(path, "w").close()
        # Simulate end-of-main row aus accumulator-state
        acct = {"latency_ms": 3500, "calls": 5, "failures": 2, "successes": 3}
        hc.record_provider_call(
            provider="news_rss", tier=3, latency_ms=acct["latency_ms"],
            http_status=200 if acct["successes"] > 0 else None,
            item_count=acct["successes"],
            error=None if acct["failures"] == 0
                  else f"{acct['failures']}/{acct['calls']} calls failed",
            run_phase="ki_agent_tick", path=path,
        )
        e = hc.read_all_provider(path)[0]
        assert e["item_count"] == 3
        assert e["error"] == "2/5 calls failed"
        assert e["http_status"] == 200   # mind. 1 success → status OK
    finally:
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass


# ── PR-1/2-Regression ═══════════════════════════════════════════════════


def test_tier1_keys_still_tier_1():
    # finviz wurde 19.05.2026 nach Tier 2 verschoben (Stufe-3-Fallback).
    for k in ("yahoo_screener", "yfinance_batch", "yfinance_singletons"):
        assert HEALTH_CHECK_PROVIDER_TIER.get(k) == 1


def test_tier2_keys_still_tier_2():
    for k in ("finra", "finnhub", "stockanalysis", "earningswhispers"):
        assert HEALTH_CHECK_PROVIDER_TIER.get(k) == 2


def test_pr1_helper_backward_compat_aliases():
    """PR 2 nutzt _instrument_provider_call (mit underscore) als
    Modul-Funktion. PR 3 hat sie nach health_check.py umgezogen +
    Backward-compat-Alias in generate_report.py beibehalten."""
    assert "_instrument_provider_call = health_check.instrument_provider_call" in SRC_GR


def test_pr2_finnhub_path_intact():
    """Sister-Check: PR 2 Finnhub-Wrapping ist noch intakt."""
    assert "_instrument_provider_call(\n        _FINNHUB_ACCT" in SRC_GR \
        or "_instrument_provider_call(_FINNHUB_ACCT," in SRC_GR


# ── Runner ═════════════════════════════════════════════════════════════


def main() -> None:
    tests = [
        # Konstanten + Helper-Reuse
        ("Alle 7 Tier-3-Keys in config",                  test_all_seven_tier3_keys_in_config),
        ("instrument_provider_call in health_check",      test_instrument_provider_call_lives_in_health_check),
        ("success_check-Parameter unterstützt",            test_success_check_parameter_supported),
        ("success_check Tuple-first=True → success",       test_success_check_passes_when_tuple_first_is_true),
        ("Default-Heuristik: non-empty dict → success",   test_success_check_default_dict_with_zero_values_still_truthy),
        ("success_check-Exception → failure (no crash)",   test_success_check_handles_exception_in_check_function),
        # Akkumulatoren
        ("ki_agent.py: 6 Tier-3-Akkumulatoren",            test_ki_agent_has_six_tier3_accumulators),
        ("generate_report.py: edgar_13f-Akkumulator",      test_generate_report_has_edgar_13f_accumulator),
        ("ki_agent.main() resettet Tier-3-Akkus",          test_ki_agent_main_resets_tier3_accumulators),
        # Wrappers
        ("stocktwits-Wrapper + success_check",             test_stocktwits_wrapped_with_success_check),
        ("uoa-Wrapper + success_check (Tuple-fail-soft)", test_uoa_wrapped_with_success_check),
        ("news_rss: yahoo_news gewrappt",                  test_news_rss_wraps_yahoo_news),
        ("news_rss: ≥ 5 Wrappings (alle Sources, finviz seit Mai 2026 aus)",
                                                           test_news_rss_wraps_all_five_rss_sources),
        ("edgar_8k-Wrapper + Tuple-success_check",         test_edgar_8k_wrapped_with_tuple_success_check),
        ("edgar_form4-Wrapper + Tuple-success_check",      test_edgar_form4_wrapped_with_tuple_success_check),
        ("edgar_13d_g-Wrapper (default success_check)",    test_edgar_13d_g_wrapped),
        ("edgar_13f-Wrapper im ThreadPool submit",         test_edgar_13f_wrapped_in_threadpool_submit),
        # Emission
        ("ki_agent emittiert 6 Tier-3-Provider gated",     test_ki_agent_emits_all_six_tier3_rows_gated),
        ("generate_report emittiert edgar_13f gated",      test_generate_report_emits_edgar_13f_gated),
        # Pass + Fail per Provider
        ("Pass-Pfad pro Tier-3-Provider",                  test_tier3_pass_path_writes_status_200),
        ("Fail-Pfad pro Tier-3-Provider (error-String)",   test_tier3_fail_path_writes_error_string),
        # EDGAR-Special
        ("EDGAR 403 als Failure, nicht silent",            test_edgar_403_recorded_as_failure_not_silent),
        ("EDGAR 403-Record persistiert error-Message",     test_edgar_403_provider_record_persists_error_message),
        # News-RSS-Special
        ("News-RSS partial failure: 3/5 erfolgreich",      test_news_rss_partial_failure_aggregation),
        ("News-RSS partial failure: Record persistiert",   test_news_rss_partial_failure_persisted),
        # PR-1/2-Regression
        ("PR-1 Tier-1-Keys unverändert",                   test_tier1_keys_still_tier_1),
        ("PR-2 Tier-2-Keys unverändert",                   test_tier2_keys_still_tier_2),
        ("PR-2 Backward-compat-Alias (Helper-Move)",       test_pr1_helper_backward_compat_aliases),
        ("PR-2 Finnhub-Wrapping intakt",                   test_pr2_finnhub_path_intact),
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
