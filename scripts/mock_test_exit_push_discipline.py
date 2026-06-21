"""Regressionstest: Exit-Push-Disziplin (Bug-Fix 21.06.2026).

Zwei getrennte, unabhängig getestete Defekte aus der Diagnose 21.06.
(5 Wochenend-Pushes LUCK/PDYN/AI/GIII/IONQ, alle price=None/drop_pct=None
aber crit=True):

FIX A — Validity-Gate (ki_agent.process_exit_signals crit-Push-Loop):
  Ein gespeicherter crit ohne gültige Datenbasis (stale Altbestand:
  available-Key absent, details.price=None) darf NICHT gepusht werden.
  Writer-Seite (generate_report) setzt jetzt ``available=True`` EXPLIZIT in
  jedem Trigger-Success-Branch; der Consumer pusht nur bei
  ``available is True``.

FIX B — Markt-/Holiday-Gate (ganze Pipeline):
  Exit-Pushes feuern NUR an US-Handelstagen. Wochenende ODER
  ``config.US_MARKET_HOLIDAYS`` → komplette Pipeline geskippt.

Determinismus (EXZELLENZ #4): ``now`` injizierbar; jeder Lauf nutzt frischen
State → idempotent, unabhängig von vorherigen Aufrufen.

Kategorie A: stdlib + Heavy-Dep-Stubs, deterministisch, env-frei, CI-gate-bar.
"""
from __future__ import annotations

import pathlib
import sys
import types
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_fails: list[str] = []


def _check(name, cond):
    if cond:
        print(f"  OK  {name}")
    else:
        _fails.append(name)
        print(f"  FAIL {name}")


def _install_stubs() -> None:
    for m in ("pandas", "requests", "yfinance"):
        if m not in sys.modules:
            sys.modules[m] = types.ModuleType(m)


_install_stubs()
import ki_agent  # noqa: E402

# ── Zeitpunkte (UTC, tz-aware) — ET-Datum bestimmt das Gate ────────────────
WEEKDAY = datetime(2026, 6, 18, 18, 0, tzinfo=timezone.utc)  # Do → ET 14:00, kein Feiertag
WEEKEND = datetime(2026, 6, 20, 18, 0, tzinfo=timezone.utc)  # Sa
HOLIDAY = datetime(2026, 6, 19, 18, 0, tzinfo=timezone.utc)  # Juneteenth Fr → ET 14:00

# ── Trigger-Fixtures ───────────────────────────────────────────────────────
# STALE = exakt der belegte Juneteenth-Altbestand: crit=True, available-Key
# ABSENT, details.price=None.
STALE   = {"crit": True, "score": 100,
           "details": {"ma21": 8.24, "price": None, "drop_pct": None}}
VALID   = {"crit": True, "score": 100, "available": True,
           "details": {"ma21": 8.24, "price": 7.0, "drop_pct": 15.05}}
UNAVAIL = {"crit": True, "score": 100, "available": False, "details": {}}


def _app_data(trigger: dict) -> dict:
    # exit_pressure=30 < Eskalation(>75)/Warnung(55–75) → nur der crit-Push-
    # Pfad wird exerziert, keine Composite-Pushes.
    return {"positions": {"TST": {"no_exit_alerts": False, "exit_state": {
        "exit_pressure": 30, "prev_exit_pressure": 10,
        "triggers": {"trend_break": trigger}}}}}


def _run(app_data: dict, now: datetime) -> list:
    """Frischer State pro Lauf → deterministisch, kein Cooldown-Übertrag."""
    sent: list = []
    state: dict = {}
    orig = ki_agent._send_exit_p2_push
    ki_agent._send_exit_p2_push = (
        lambda ticker, body, severity="trigger": (
            sent.append((ticker, severity, body)) or True))
    try:
        ki_agent.process_exit_signals(app_data, state, now=now)
    finally:
        ki_agent._send_exit_p2_push = orig
    return sent


def main() -> int:
    print("=== FIX A — Validity-Gate (Werktag, isoliert von Fix B) ===")
    _check("01 stale Altbestand (available absent, price=None) → SUPPRESSED",
           _run(_app_data(STALE), WEEKDAY) == [])
    _check("02 valider Crit (available=True, details komplett) → PUSH",
           len(_run(_app_data(VALID), WEEKDAY)) == 1)
    _check("03 explizit available=False → SUPPRESSED",
           _run(_app_data(UNAVAIL), WEEKDAY) == [])

    print("\n=== FIX B — Markt-/Holiday-Gate (valider Crit, isoliert von Fix A) ===")
    _check("04 Wochenende (Sa) + valider Crit → SUPPRESSED",
           _run(_app_data(VALID), WEEKEND) == [])
    _check("05 US-Feiertag (Juneteenth 19.06.) + valider Crit → SUPPRESSED",
           _run(_app_data(VALID), HOLIDAY) == [])
    _check("06 Werktag (Do, kein Feiertag) + valider Crit → PUSH (Baseline)",
           len(_run(_app_data(VALID), WEEKDAY)) == 1)

    print("\n=== KOMBINIERT — beide Gates zusammen ===")
    _check("07 Werktag + valid → PUSH",
           len(_run(_app_data(VALID), WEEKDAY)) == 1)
    _check("08 Wochenende + valid → SUPPRESSED (Fix B greift)",
           _run(_app_data(VALID), WEEKEND) == [])
    _check("09 Werktag + invalid → SUPPRESSED (Fix A greift)",
           _run(_app_data(STALE), WEEKDAY) == [])

    print("\n=== DETERMINISMUS (EXZELLENZ #4) — gleicher Input → gleicher Output ===")
    r1 = _run(_app_data(VALID), WEEKDAY)
    r2 = _run(_app_data(VALID), WEEKDAY)
    _check("10 zweimal Werktag+valid → identisch (frischer State, idempotent)",
           len(r1) == 1 and len(r2) == 1)
    h1 = _run(_app_data(VALID), HOLIDAY)
    h2 = _run(_app_data(VALID), HOLIDAY)
    _check("11 zweimal Holiday+valid → identisch leer", h1 == [] and h2 == [])

    print("\n=== Writer-Seite: generate_report Success-Branches setzen available=True ===")
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # Sechs Trigger-Success-Returns müssen "available": True tragen.
    _check("12 generate_report hat ≥6 'available': True in Trigger-Branches",
           src.count('"available": True') >= 6)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle Exit-Push-Disziplin-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
