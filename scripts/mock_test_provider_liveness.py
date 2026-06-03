"""Mock-Test: provider_liveness (dynamische Datenquellen-Anzeige, 02.06.2026).

Prüft den Liveness-Diskriminator (REIN ANZEIGE, kein Score-Effekt), der die
hartkodierte Datenquellen-Liste ersetzt. Nutzt die bestehende Konsekutiv-/
Stale-/Coverage-Logik (DIGEST_CONSECUTIVE_THRESHOLD / DIGEST_STALE_DAYS /
DIGEST_COVERAGE_THRESHOLD_*).

Tests:
  1. 1-Lauf-Hiccup (fail dann ok) → live (Anti-Flacker, Kern-Anforderung)
  2. 3-in-Folge-Fail (Tier 2) → stale
  3. disabled-Flag hat Vorrang (auch mit Erfolg-Log) → disabled
  4. verstummt > DIGEST_STALE_DAYS (kein recent log) → stale
  5. Tier 1 ein coverage<80-Fail → sofort stale (Schwelle 1)
  6. kein Log + nicht disabled → stale (verstummt)
  7. static-Provider-Pattern: leerer entries → alle Flag-Keys bekommen Status

Ausführung: ``python scripts/mock_test_provider_liveness.py``.
"""
from __future__ import annotations

import pathlib
import sys
import types
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Heavy-Deps stubben (health_check importiert config, das ist leichtgewichtig,
# aber zur Sicherheit gegen transitive Imports).
for _m in ("yfinance", "pandas", "requests"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)

import health_check as hc  # noqa: E402

_NOW = datetime(2026, 6, 2, 18, 0, tzinfo=timezone.utc)


def _ts(hours_ago: float) -> str:
    return (_NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(provider, tier, http, cov, hours_ago):
    return {"provider": provider, "tier": tier, "http_status": http,
            "coverage_pct": cov, "run_ts": _ts(hours_ago)}


def test_one_run_hiccup_stays_live():
    e = [_row("px", 2, 500, None, 3),
         _row("px", 2, 200, 90, 2),
         _row("px", 2, 200, 90, 1)]
    assert hc.provider_liveness(e, {"px": 2}, now_ts=_NOW)["px"] == "live"


def test_three_consecutive_fails_stale():
    e = [_row("px", 2, 500, None, 3),
         _row("px", 2, 500, None, 2),
         _row("px", 2, 500, None, 1)]
    assert hc.provider_liveness(e, {"px": 2}, now_ts=_NOW)["px"] == "stale"


def test_disabled_flag_wins():
    e = [_row("px", 2, 200, 90, 1)]  # trotz Erfolg
    out = hc.provider_liveness(e, {"px": 2}, {"px": False}, now_ts=_NOW)
    assert out["px"] == "disabled"


def test_silent_over_stale_days_stale():
    old = (_NOW - timedelta(days=9)).strftime("%Y-%m-%dT%H:%M:%SZ")
    e = [{"provider": "px", "tier": 2, "http_status": 200,
          "coverage_pct": 90, "run_ts": old}]
    assert hc.provider_liveness(e, {"px": 2}, now_ts=_NOW)["px"] == "stale"


def test_tier1_single_coverage_fail_stale():
    e = [_row("y", 1, 200, 60, 1)]   # coverage 60 < 80 (Tier1-Schwelle)
    assert hc.provider_liveness(e, {"y": 1}, now_ts=_NOW)["y"] == "stale"


def test_no_log_not_disabled_stale():
    # Provider im tier_map, aber kein Log, kein disabled-Flag → stale.
    out = hc.provider_liveness([], {"ghost": 2}, now_ts=_NOW)
    assert out["ghost"] == "stale"


def test_disabled_without_log_is_disabled():
    # disabled-Flag greift auch ohne jeden Log-Eintrag (stocktwits-Fall).
    out = hc.provider_liveness([], {"st": 3}, {"st": False}, now_ts=_NOW)
    assert out["st"] == "disabled"


def main():
    tests = [
        ("1-Lauf-Hiccup → live (Anti-Flacker)",      test_one_run_hiccup_stays_live),
        ("3-in-Folge-Fail → stale",                  test_three_consecutive_fails_stale),
        ("disabled-Flag hat Vorrang",                test_disabled_flag_wins),
        ("verstummt >7d → stale",                    test_silent_over_stale_days_stale),
        ("Tier1 coverage<80 → sofort stale",         test_tier1_single_coverage_fail_stale),
        ("kein Log + nicht disabled → stale",        test_no_log_not_disabled_stale),
        ("disabled ohne Log → disabled",             test_disabled_without_log_is_disabled),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {name}: UNERWARTET {exc!r}")
    print()
    if failed:
        print(f"{failed} Test(s) FEHLGESCHLAGEN.")
        sys.exit(1)
    print(f"{len(tests)} Tests bestanden.")


if __name__ == "__main__":
    main()
