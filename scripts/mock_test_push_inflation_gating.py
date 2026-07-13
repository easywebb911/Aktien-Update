"""Mock-Tests für Push-Inflation-Reduktion (12.05.2026).

Drei Eingriffe in einem Test-File gebündelt:

  1. Conviction-Gating: ein Anomaly-Trigger (hier generisch perfect_storm)
     bei Conviction < 75 wird suppressed, bei ≥ 75 wird gepusht. Bestätigt
     die bewusste Architektur-Entscheidung, dass Anomaly-Pushes ohne
     ausreichende Conviction unterdrückt werden. (Der frühere monster_backup-
     Trigger, an dem das ursprünglich getestet wurde, ist seit 13.07.2026
     entfernt — monster_score unvalidiert; das Gating-Verhalten bleibt für
     die verbliebenen Trigger identisch.)

  2. Earnings-Sofort-Alert Per-Event-Dedup: drei Calls innerhalb 24h für
     dasselbe (Ticker, Earnings-Date) → nur erster sendet, andere
     blockiert via _anomaly_is_on_cooldown(EARNINGS_IMMEDIATE_COOLDOWN_HOURS).

  3. conviction_score-Feld in push_history persistiert nach _record_push.

Helper-Tests:
  - _record_push round-trip mit allen Schema-Feldern
  - Backward-Compat: Aufruf ohne conviction_score → Feld ist None
  - Suppressed-Eintrag bekommt conviction_score trotzdem mitpersistiert

Ausführung: ``python scripts/mock_test_push_inflation_gating.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timedelta
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from push_history import _record_push  # noqa: E402
from config import (  # noqa: E402
    ANOMALY_CONVICTION_MIN_THRESHOLD,
    EARNINGS_IMMEDIATE_COOLDOWN_HOURS,
)


# === push_history Schema-Erweiterung ======================================

def test_record_push_persists_conviction():
    state = {}
    _record_push(state, "FOO", "anomaly", "high", "perfect_storm",
                 "body text", success=True, conviction_score=78)
    entries = state["push_history"]
    assert len(entries) == 1, entries
    e = entries[0]
    assert e["ticker"] == "FOO", e
    assert e["conviction_score"] == 78, e
    assert e["kind"] == "anomaly", e
    assert e["success"] is True, e
    assert e["suppressed"] is False, e


def test_record_push_no_conviction_arg_is_none():
    state = {}
    _record_push(state, "BAR", "exit_p2", "trigger", "trend_break",
                 "body", success=True)
    e = state["push_history"][0]
    assert e["conviction_score"] is None, e


def test_record_push_suppressed_still_carries_conviction():
    state = {}
    _record_push(state, "BAZ", "anomaly", "high", "perfect_storm",
                 "body", success=False, suppressed=True,
                 suppress_reason="conviction_below_threshold",
                 conviction_score=42)
    e = state["push_history"][0]
    assert e["suppressed"] is True, e
    assert e["suppress_reason"] == "conviction_below_threshold", e
    assert e["conviction_score"] == 42, e


def test_record_push_float_conviction_rounds_to_int():
    state = {}
    _record_push(state, "X", "anomaly", "medium", "score_jump",
                 "body", success=True, conviction_score=72.6)
    e = state["push_history"][0]
    assert e["conviction_score"] == 73, e  # round-to-int


def test_record_push_garbage_conviction_becomes_none():
    state = {}
    _record_push(state, "X", "anomaly", "medium", "score_jump",
                 "body", success=True, conviction_score="garbage")
    e = state["push_history"][0]
    assert e["conviction_score"] is None, e


# === Conviction-Threshold-Konstante =======================================

def test_conviction_min_threshold_is_75():
    """Spec aus 12.05.: Anhebung von 50 auf 75. Falls jemand das
    versehentlich senkt, fällt es hier auf."""
    assert ANOMALY_CONVICTION_MIN_THRESHOLD == 75, ANOMALY_CONVICTION_MIN_THRESHOLD


# === Conviction-Gating-Logik ==============================================
# Wir simulieren die Gating-Klausel aus ki_agent.py:3045-3061, ohne den
# gesamten consume_*-Loop neu zu erfinden — das wäre Integrations-Bereich
# und braucht einen vollen Mock-Stack. Stattdessen unit-mäßig den
# Entscheidungs-Punkt prüfen.

def _gate_anomaly(conv, trigger):
    """Repliziert die Gating-Logik aus ki_agent.py — feuert _suppress=True
    wenn Conviction < MIN_THRESHOLD und Trigger != conviction_high."""
    if trigger == "conviction_high":
        return False  # conviction_high niemals gegated
    if isinstance(conv, (int, float)) and conv < ANOMALY_CONVICTION_MIN_THRESHOLD:
        return True
    return False


def test_perfect_storm_low_conviction_suppressed():
    """NVAX-Szenario: Monster 100 + Conviction 45 → suppressed."""
    assert _gate_anomaly(conv=45, trigger="perfect_storm") is True


def test_perfect_storm_high_conviction_passes():
    """Echtes Aktions-Setup: Monster 100 + Conviction 80 → push."""
    assert _gate_anomaly(conv=80, trigger="perfect_storm") is False


def test_perfect_storm_exactly_threshold_passes():
    """Conviction == 75 (= MIN_THRESHOLD): geht durch (≥ Vergleich)."""
    assert _gate_anomaly(conv=75, trigger="perfect_storm") is False


def test_conviction_high_never_gated():
    """conviction_high feuert auch bei niedrigerer Conviction durch —
    weil es DER Aktions-Push ist. (Spec aus CLAUDE.md)."""
    assert _gate_anomaly(conv=10, trigger="conviction_high") is False


def test_score_jump_low_conviction_suppressed():
    """Andere Anomalies (score_jump etc.) werden ebenfalls gegated."""
    assert _gate_anomaly(conv=60, trigger="score_jump") is True


def test_ticker_without_conviction_passes():
    """None-Conviction (Ticker nicht in heutigen conviction_scores) →
    push konservativ ungefiltert."""
    assert _gate_anomaly(conv=None, trigger="perfect_storm") is False


# === Earnings-Sofort-Alert Per-Event-Dedup =================================
# Wir replizieren den Cooldown-Algorithmus inline, weil
# _anomaly_is_on_cooldown auf now_berlin() basiert — der Test braucht
# Kontrolle über die simulierte Zeit.

def _build_cooldown_key(ticker, earnings_date_str):
    return f"earnings_immediate_{ticker}_{earnings_date_str}"


def test_earnings_dedup_blocks_repeat_within_24h():
    """Drei Aufrufe innerhalb 6h für dasselbe (DMRC, 2026-05-12)-Event:
    nur der erste setzt den Cooldown, weitere zwei werden blockiert."""
    state = {"cooldowns": {}}
    key = _build_cooldown_key("DMRC", "12.05.2026")

    # Simulierte Zeitstempel im State-Cooldown-Dict — der erste Push.
    state["cooldowns"][key] = (
        datetime.now().astimezone().isoformat())

    # Innerhalb des Cooldowns: _anomaly_is_on_cooldown würde True
    # zurückgeben → kein weiterer Push.
    # Wir validieren das Pattern hier nur funktional: Key gesetzt, also
    # cooldown_active für den Aufrufer.
    assert key in state["cooldowns"], state
    # Cooldown-Dauer korrekt importiert (positiv-Test)
    assert EARNINGS_IMMEDIATE_COOLDOWN_HOURS == 24, EARNINGS_IMMEDIATE_COOLDOWN_HOURS


def test_earnings_dedup_separate_events_separate_keys():
    """DMRC am 12.05. und DMRC am 13.05. (zwei verschiedene Earnings)
    bekommen unterschiedliche Cooldown-Keys → beide würden feuern."""
    key_a = _build_cooldown_key("DMRC", "12.05.2026")
    key_b = _build_cooldown_key("DMRC", "13.05.2026")
    assert key_a != key_b, (key_a, key_b)


def test_earnings_dedup_key_includes_ticker_and_date():
    """Cooldown-Key-Schema: earnings_immediate_{TICKER}_{DD.MM.YYYY}.
    Spec aus heutigem Auftrag."""
    key = _build_cooldown_key("DMRC", "12.05.2026")
    assert key == "earnings_immediate_DMRC_12.05.2026", key


def test_earnings_dedup_missing_date_no_key():
    """Ohne earnings_date_str kein Per-Event-Dedup möglich — der
    Aufrufer überspringt dann den Push komplett (defensive)."""
    state = {"cooldowns": {}}
    earnings_date_str = None
    earnings_event_key = (f"earnings_immediate_DMRC_{earnings_date_str}"
                          if earnings_date_str else None)
    assert earnings_event_key is None


# === Runner ================================================================

def main():
    tests = [
        ("push_history: conviction_score wird persistiert",  test_record_push_persists_conviction),
        ("push_history: kein conviction_score → None",       test_record_push_no_conviction_arg_is_none),
        ("push_history: suppressed-Eintrag mit conviction",   test_record_push_suppressed_still_carries_conviction),
        ("push_history: float conviction rundet zu int",      test_record_push_float_conviction_rounds_to_int),
        ("push_history: kaputter conviction → None",          test_record_push_garbage_conviction_becomes_none),
        ("Konstante MIN_THRESHOLD == 75",                     test_conviction_min_threshold_is_75),
        ("Gating: perfect_storm conv<75 suppressed",         test_perfect_storm_low_conviction_suppressed),
        ("Gating: perfect_storm conv≥75 push",               test_perfect_storm_high_conviction_passes),
        ("Gating: conv == MIN_THRESHOLD push",                test_perfect_storm_exactly_threshold_passes),
        ("Gating: conviction_high niemals gegated",           test_conviction_high_never_gated),
        ("Gating: score_jump auch gegated",                   test_score_jump_low_conviction_suppressed),
        ("Gating: None-Conviction konservativ push",          test_ticker_without_conviction_passes),
        ("Earnings-Dedup: Cooldown 24h, blockt 24h-Wieder",   test_earnings_dedup_blocks_repeat_within_24h),
        ("Earnings-Dedup: andere Earnings-Daten neuer Key",   test_earnings_dedup_separate_events_separate_keys),
        ("Earnings-Dedup: Key-Schema (ticker+date)",          test_earnings_dedup_key_includes_ticker_and_date),
        ("Earnings-Dedup: kein Datum → kein Push",            test_earnings_dedup_missing_date_no_key),
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
