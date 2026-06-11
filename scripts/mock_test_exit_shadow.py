"""Boundary-Mock-Test für das Exit-Shadow-Log (Kategorie A: pures stdlib,
env-frei, zeit-injiziert, deterministisch, CI-gate-bar).

Prüft die PURE-Logik von exit_shadow.py: Record-Building (6 Trigger geflattet),
Settled-postclose-Gate, Re-Write-by-(ticker,date), Backfill-Abbruchbedingung
(fertige Records übersprungen), Forward-Return-Vorzeichen. KEINE Auswertung,
KEIN Netz, KEIN Live-Effekt.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import exit_shadow as es  # noqa: E402

ET = ZoneInfo("America/New_York")
_fails: list[str] = []


def _check(name, got, want):
    if got == want:
        print(f"  OK  {name}")
    else:
        _fails.append(f"{name}: got {got!r}, want {want!r}")
        print(f"  FAIL {name}: got {got!r}, want {want!r}")


def _et(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=ET)


# Mock-exit_state (wie _compute_exit_state liefert)
def _mock_state(pressure=42, with_unavail=True):
    triggers = {
        "score_decay":   {"score": 10, "warn": False, "crit": False},
        "profit_lock":   {"score": 0, "warn": False, "crit": False,
                          "available": False, "reason": "kein aktueller Preis"},
        "overheated":    {"score": 30, "warn": True, "crit": False},
        "setup_erosion": {"score": 5, "warn": False, "crit": False},
        "catalyst":      {"score": 0, "warn": False, "crit": False},
        "trend_break":   {"score": 100, "warn": True, "crit": True,
                          "ma21": 7.6, "drop_pct": 8.68},
    }
    if not with_unavail:
        triggers["profit_lock"] = {"score": 20, "warn": False, "crit": False}
    return {
        "exit_pressure": pressure, "triggers": triggers,
        "peak_score_since_entry": 88.0, "peak_pnl_pct_since_entry": 0.12,
        "current_score": 70.0, "current_pnl_pct": -0.05,
        "prev_exit_pressure": 40,
        "computed_at": "2026-06-10T21:30:00Z",
    }


print("=== 1 — Record-Building (6 Trigger geflattet, alle Felder) ===")
rec = es.build_exit_shadow_record("DBI", "10.06.2026", "postclose",
                                  _mock_state(), 6.985)
_check("01 schema_v", rec["schema_v"], 1)
_check("02 date/ticker/run_phase", (rec["date"], rec["ticker"], rec["run_phase"]),
       ("10.06.2026", "DBI", "postclose"))
_check("03 exit_pressure", rec["exit_pressure"], 42)
_check("04 signal_price (Referenz)", rec["signal_price"], 6.985)
_check("05 current_pnl_pct + peak", (rec["current_pnl_pct"], rec["peak_pnl_pct"]),
       (-0.05, 0.12))
_check("06 alle 6 Trigger present", sorted(rec["triggers"].keys()),
       sorted(es._TRIGGER_NAMES))
_check("07 trend_break geflattet (nur 4 Kernfelder)",
       sorted(rec["triggers"]["trend_break"].keys()),
       ["available", "crit", "score", "warn"])
_check("08 trend_break crit + score", (rec["triggers"]["trend_break"]["crit"],
       rec["triggers"]["trend_break"]["score"]), (True, 100))
_check("09 profit_lock available=False (unavail-Pfad)",
       rec["triggers"]["profit_lock"]["available"], False)
_check("10 overheated available default True (available-Pfad ohne Key)",
       rec["triggers"]["overheated"]["available"], True)
_check("11 forward_* initial None",
       (rec["forward_3d"], rec["forward_5d"], rec["forward_10d"]),
       (None, None, None))

print("\n=== 2 — Settled-postclose-Gate ===")
_check("12 postclose 17:17 ET → log",
       es.should_log_exit_shadow("postclose", _et(2026, 6, 10, 17, 17)), True)
_check("13 premarket 17:17 ET → skip",
       es.should_log_exit_shadow("premarket", _et(2026, 6, 10, 17, 17)), False)
_check("14 postclose 15:42 ET (pre-close) → skip",
       es.should_log_exit_shadow("postclose", _et(2026, 6, 10, 15, 42)), False)
_check("15 postclose 16:00 ET exakt → log",
       es.should_log_exit_shadow("postclose", _et(2026, 6, 10, 16, 0)), True)
_check("16 leere run_phase (off-schedule/Default) → skip",
       es.should_log_exit_shadow("", _et(2026, 6, 10, 17, 17)), False)

print("\n=== 3 — Re-Write-by-(ticker,date): kein Duplikat, forward carry-over ===")
old = [
    {"ticker": "DBI", "date": "10.06.2026", "exit_pressure": 20,
     "forward_3d": -4.1, "forward_5d": None, "forward_10d": None},
    {"ticker": "IONQ", "date": "09.06.2026", "exit_pressure": 67,
     "forward_3d": None, "forward_5d": None, "forward_10d": None},
]
new = [es.build_exit_shadow_record("DBI", "10.06.2026", "postclose",
                                   _mock_state(pressure=55), 7.0)]
merged = es.merge_exit_shadow(old, new)
_check("17 genau ein DBI/10.06-Record (kein Duplikat)",
       sum(1 for r in merged if r["ticker"] == "DBI" and r["date"] == "10.06.2026"), 1)
dbi = next(r for r in merged if r["ticker"] == "DBI" and r["date"] == "10.06.2026")
_check("18 Re-Write übernahm neuen exit_pressure", dbi["exit_pressure"], 55)
_check("19 forward_3d carry-over (alter Backfill-Wert erhalten)",
       dbi["forward_3d"], -4.1)
_check("20 anderer Ticker/Datum unangetastet", len(merged), 2)

print("\n=== 4 — Backfill-Abbruch + Horizont-Logik (forward_fields_to_fill) ===")
done = {"forward_3d": -4.1, "forward_5d": -6.0, "forward_10d": -8.0}
_check("21 fertiger Record (forward_10d gesetzt) → leer (NIE wieder anfassen)",
       es.forward_fields_to_fill(done, sig_idx=10, n_closes=30), {})
_check("22 is_record_complete(done)", es.is_record_complete(done), True)
partial = {"forward_3d": None, "forward_5d": None, "forward_10d": None}
# sig_idx=10, n_closes=20 → +3 (13), +5 (15), +10 (20=out of range, nicht fällig)
_check("23 fällige Horizonte +3/+5 da, +10 noch nicht (out of window)",
       es.forward_fields_to_fill(partial, sig_idx=10, n_closes=16),
       {"forward_3d": 13, "forward_5d": 15})
_check("24 alle Horizonte erreicht (n_closes groß)",
       es.forward_fields_to_fill(partial, sig_idx=5, n_closes=30),
       {"forward_3d": 8, "forward_5d": 10, "forward_10d": 15})
_check("25 sig_idx<0 (Datum nicht im 90d-Fenster) → leer (bleibt None)",
       es.forward_fields_to_fill(partial, sig_idx=-1, n_closes=30), {})
already = {"forward_3d": -2.0, "forward_5d": None, "forward_10d": None}
_check("26 bereits gefülltes forward_3d wird nicht neu zugewiesen",
       es.forward_fields_to_fill(already, sig_idx=5, n_closes=30),
       {"forward_5d": 10, "forward_10d": 15})

print("\n=== 5 — Forward-Return-Vorzeichen (NEGATIV = Kurs fiel = gutes Signal) ===")
_check("27 Kurs fiel 7.41→6.98 → NEGATIV (gutes Exit-Signal)",
       es.compute_forward_return(7.41, 6.98) < 0, True)
_check("28 exakter Wert (6.98-7.41)/7.41*100",
       es.compute_forward_return(7.41, 6.98), round((6.98 - 7.41) / 7.41 * 100, 2))
_check("29 Kurs stieg → POSITIV (Fehlsignal, 08.06-Fall)",
       es.compute_forward_return(7.0, 8.0) > 0, True)
_check("30 sig_close<=0 → None", es.compute_forward_return(0.0, 5.0), None)

print("\n=== 6 — write/load Round-Trip (I/O, Tempfile) ===")
_tmp = tempfile.mktemp(suffix=".jsonl")
try:
    n = es.write_exit_shadow_records([rec], path=_tmp)
    _check("31 write returnt n=1", n, 1)
    loaded = es._load_jsonl(_tmp)
    _check("32 round-trip: 1 Record geladen", len(loaded), 1)
    _check("33 round-trip ticker", loaded[0]["ticker"], "DBI")
    # zweiter Write same (ticker,date) → Re-Write, kein Duplikat
    es.write_exit_shadow_records(
        [es.build_exit_shadow_record("DBI", "10.06.2026", "postclose",
                                     _mock_state(pressure=99), 7.0)], path=_tmp)
    loaded2 = es._load_jsonl(_tmp)
    _check("34 nach 2. Write weiterhin 1 Record (Re-Write)", len(loaded2), 1)
    _check("35 Re-Write übernahm pressure=99", loaded2[0]["exit_pressure"], 99)
finally:
    if os.path.exists(_tmp):
        os.unlink(_tmp)

print()
if _fails:
    print(f"{len(_fails)} FAIL:")
    for f in _fails:
        print("  -", f)
    sys.exit(1)
print("Alle Exit-Shadow-Boundary-Tests bestanden.")
