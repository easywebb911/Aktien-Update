"""Mock-Tests für DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES (Option γ).

Ziel: pro-Provider-Konsekutiv-Schwelle in ``aggregate_provider_fails``.
- finviz mit Override 100 → erst ab 100 in Folge warn.
- Andere Tier-2/3-Provider bleiben bei Default 3.
- Override-Lookup berührt NUR den Tier-2/3-Schwellen-Vergleich; Tier-1
  bleibt unangetastet (immer crit, ohne Konsekutiv-Bedingung).
- Leeres/fehlendes Override-Dict → Default 3 für alle Provider.

Zähl-Logik und Severity-Mapping selbst sind unverändert — verifiziert,
dass nur die Schwelle für den Vergleich ein anderer Wert ist.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

# Repo-Root in sys.path damit `import health_check` läuft.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import health_check as hc  # noqa: E402
import config              # noqa: E402


# ── Hilfsbau: synthetische provider_health-Einträge ───────────────────────


def _row(provider, run_ts, http_status=None, coverage_pct=None,
         tier=None, error=None):
    """Baut eine provider_health.jsonl-Zeile."""
    row = {
        "provider": provider,
        "run_ts": run_ts,
        "http_status": http_status,
        "coverage_pct": coverage_pct,
    }
    if tier is not None:
        row["tier"] = tier
    if error is not None:
        row["error"] = error
    return row


def _make_failing_run(provider, run_ts, tier=2):
    """Eine Run-Zeile, die als row_fail klassifiziert wird
    (http_status != 200 + kein coverage_pct ⇒ row_fail = True)."""
    return _row(provider, run_ts, http_status=None, tier=tier,
                error="1/2 calls failed")


def _make_success_run(provider, run_ts, tier=2):
    """Eine erfolgreiche Run-Zeile (http=200, kein coverage_fail)."""
    return _row(provider, run_ts, http_status=200, tier=tier)


_TIER_MAP_DEFAULT = {"finviz": 2, "finnhub": 2, "stockanalysis": 2}
_NOW = datetime(2026, 5, 28, 22, 0, tzinfo=timezone.utc)


# ── Cases ─────────────────────────────────────────────────────────────────


def test_01_finviz_at_22_no_warn_under_override():
    """22 in Folge bei finviz → KEIN warn (Override greift)."""
    rows = [_make_failing_run("finviz", f"2026-05-{i:02d}T20:00:00Z")
            for i in range(1, 23)]   # 22 Einträge
    fails = hc.aggregate_provider_fails(
        rows, counters={"consecutive_failures": {}, "last_seen": {}},
        tier_map=_TIER_MAP_DEFAULT, now_ts=_NOW,
    )
    fv_fails = [f for f in fails if f.get("provider") == "finviz"]
    assert not fv_fails, (
        f"22 < 100-Override → erwartet keine finviz-Fails, got {fv_fails}"
    )


def test_02_finviz_at_50_no_warn_under_override():
    """50 in Folge bei finviz → KEIN warn."""
    rows = [_make_failing_run("finviz", f"2026-05-{i:02d}T20:00:00Z")
            for i in range(1, 51)]
    fails = hc.aggregate_provider_fails(
        rows, counters={"consecutive_failures": {}, "last_seen": {}},
        tier_map=_TIER_MAP_DEFAULT, now_ts=_NOW,
    )
    fv_fails = [f for f in fails if f.get("provider") == "finviz"]
    assert not fv_fails, (
        f"50 < 100-Override → erwartet keine finviz-Fails, got {fv_fails}"
    )


def test_03_finviz_at_99_no_warn_under_override():
    """99 in Folge bei finviz → immer noch KEIN warn (knapp drunter)."""
    rows = [_make_failing_run("finviz", f"2026-05-28T{i:02d}:00:00Z")
            if i < 24
            else _make_failing_run("finviz", f"2026-06-{i-23:02d}T00:00:00Z")
            for i in range(0, 99)]
    assert len(rows) == 99
    fails = hc.aggregate_provider_fails(
        rows, counters={"consecutive_failures": {}, "last_seen": {}},
        tier_map=_TIER_MAP_DEFAULT, now_ts=_NOW,
    )
    fv_fails = [f for f in fails if f.get("provider") == "finviz"]
    assert not fv_fails, (
        f"99 < 100-Override → erwartet keine finviz-Fails, got {fv_fails}"
    )


def test_04_finviz_at_100_warn_triggers():
    """100 in Folge bei finviz → warn (Override-Grenze erreicht)."""
    counters = {"consecutive_failures": {"finviz": 99},
                "last_seen": {"finviz": "2026-05-27T00:00:00Z"}}
    rows = [_make_failing_run("finviz", "2026-05-28T20:00:00Z")]
    fails = hc.aggregate_provider_fails(
        rows, counters=counters, tier_map=_TIER_MAP_DEFAULT, now_ts=_NOW,
    )
    fv_fails = [f for f in fails if f.get("provider") == "finviz"]
    assert len(fv_fails) == 1, f"erwartet 1 finviz-fail bei 100, got {fv_fails}"
    assert fv_fails[0]["severity"] == "warn"
    assert fv_fails[0]["consecutive"] == 100


def test_05_finviz_at_101_still_warn():
    """101 → warn (Override-Grenze überschritten, blendet nicht ewig)."""
    counters = {"consecutive_failures": {"finviz": 100},
                "last_seen": {"finviz": "2026-05-27T00:00:00Z"}}
    rows = [_make_failing_run("finviz", "2026-05-28T20:00:00Z")]
    fails = hc.aggregate_provider_fails(
        rows, counters=counters, tier_map=_TIER_MAP_DEFAULT, now_ts=_NOW,
    )
    fv_fails = [f for f in fails if f.get("provider") == "finviz"]
    assert len(fv_fails) == 1 and fv_fails[0]["severity"] == "warn"
    assert fv_fails[0]["consecutive"] == 101


def test_06_other_tier2_provider_unaffected_at_3():
    """finnhub (Tier 2, KEIN Override) → bei 3 in Folge SOFORT warn.
    Beweist: Override gilt provider-spezifisch, kein globaler Effekt."""
    rows = [_make_failing_run("finnhub", f"2026-05-{i:02d}T20:00:00Z")
            for i in range(26, 29)]  # 3 Einträge
    fails = hc.aggregate_provider_fails(
        rows, counters={"consecutive_failures": {}, "last_seen": {}},
        tier_map=_TIER_MAP_DEFAULT, now_ts=_NOW,
    )
    fh_fails = [f for f in fails if f.get("provider") == "finnhub"]
    assert len(fh_fails) == 1 and fh_fails[0]["severity"] == "warn"
    assert fh_fails[0]["consecutive"] == 3


def test_07_other_tier2_provider_at_2_no_warn():
    """finnhub bei 2 → KEIN warn (Default 3 noch nicht erreicht)."""
    rows = [_make_failing_run("finnhub", f"2026-05-{i:02d}T20:00:00Z")
            for i in range(27, 29)]   # 2 Einträge
    fails = hc.aggregate_provider_fails(
        rows, counters={"consecutive_failures": {}, "last_seen": {}},
        tier_map=_TIER_MAP_DEFAULT, now_ts=_NOW,
    )
    fh_fails = [f for f in fails if f.get("provider") == "finnhub"]
    assert not fh_fails


def test_08_tier1_provider_immediate_crit_unaffected():
    """yahoo_screener (Tier 1) → SOFORT crit bei einem Fail,
    unabhängig vom Override (Override greift nur im elif-Zweig)."""
    rows = [_make_failing_run("yahoo_screener", "2026-05-28T20:00:00Z",
                              tier=1)]
    tier_map = {"yahoo_screener": 1, **_TIER_MAP_DEFAULT}
    fails = hc.aggregate_provider_fails(
        rows, counters={"consecutive_failures": {}, "last_seen": {}},
        tier_map=tier_map, now_ts=_NOW,
    )
    ys_fails = [f for f in fails if f.get("provider") == "yahoo_screener"]
    assert len(ys_fails) == 1 and ys_fails[0]["severity"] == "crit"
    assert ys_fails[0]["consecutive"] == 1


def test_09_empty_overrides_dict_falls_back_to_default():
    """Override-Dict leer → finviz fällt auf Default 3 zurück."""
    with patch.object(config, "DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES", {}):
        # health_check.py importiert beim Modul-Load. Wir patchen das
        # Modul-Attribut direkt.
        with patch.object(hc, "DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES", {}):
            rows = [_make_failing_run("finviz", f"2026-05-{i:02d}T20:00:00Z")
                    for i in range(26, 29)]  # 3 Einträge
            fails = hc.aggregate_provider_fails(
                rows, counters={"consecutive_failures": {}, "last_seen": {}},
                tier_map=_TIER_MAP_DEFAULT, now_ts=_NOW,
            )
            fv_fails = [f for f in fails if f.get("provider") == "finviz"]
            assert len(fv_fails) == 1 and fv_fails[0]["severity"] == "warn", (
                f"Override leer → finviz bei 3 erwartet warn, got {fv_fails}"
            )


def test_10_success_resets_counter_under_override():
    """Erfolgreicher Run (http=200) setzt Counter auf 0 — auch unter
    Override. Verifiziert: Reset-Logik unverändert."""
    counters = {"consecutive_failures": {"finviz": 95},
                "last_seen": {"finviz": "2026-05-27T00:00:00Z"}}
    rows = [_make_success_run("finviz", "2026-05-28T20:00:00Z")]
    fails = hc.aggregate_provider_fails(
        rows, counters=counters, tier_map=_TIER_MAP_DEFAULT, now_ts=_NOW,
    )
    fv_fails = [f for f in fails if f.get("provider") == "finviz"]
    assert not fv_fails, "Reset → keine fails erwartet"
    assert counters["consecutive_failures"]["finviz"] == 0


def test_11_override_constant_present_and_well_formed():
    """Sanity: DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES existiert in config.py,
    ist ein dict, enthält finviz=100."""
    assert hasattr(config, "DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES"), \
        "DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES fehlt in config.py"
    ov = config.DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES
    assert isinstance(ov, dict), f"erwartet dict, got {type(ov).__name__}"
    assert ov.get("finviz") == 100, f"finviz=100 erwartet, got {ov.get('finviz')}"


def test_12_source_inspection_lookup_pattern():
    """Source-Inspection: aggregate_provider_fails benutzt das
    .get(prov, DEFAULT)-Pattern für den Schwellen-Vergleich."""
    src = (Path(__file__).resolve().parent.parent
           / "health_check.py").read_text(encoding="utf-8")
    needle = "DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES.get("
    assert needle in src, (
        f"Lookup-Pattern {needle!r} fehlt — Override greift nicht!"
    )
    # Tier-1-Pfad bleibt unverändert (sofortiges crit, ohne Override)
    assert 'if tier == 1:' in src
    assert 'severity = "crit"' in src


# ── Runner ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    tests = [
        test_01_finviz_at_22_no_warn_under_override,
        test_02_finviz_at_50_no_warn_under_override,
        test_03_finviz_at_99_no_warn_under_override,
        test_04_finviz_at_100_warn_triggers,
        test_05_finviz_at_101_still_warn,
        test_06_other_tier2_provider_unaffected_at_3,
        test_07_other_tier2_provider_at_2_no_warn,
        test_08_tier1_provider_immediate_crit_unaffected,
        test_09_empty_overrides_dict_falls_back_to_default,
        test_10_success_resets_counter_under_override,
        test_11_override_constant_present_and_well_formed,
        test_12_source_inspection_lookup_pattern,
    ]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} Tests bestanden.")
