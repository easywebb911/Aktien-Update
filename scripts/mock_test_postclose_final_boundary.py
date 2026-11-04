"""Mock-Tests — Postclose-Grenze 16:20 ET (Easy-Entscheid 03./04.11.2026).

Ziel: Kein Lauf vor 16:20 ET (``trading_date.US_CLOSE_FINAL_ET``, finaler
Schlusskurs) darf als postclose gelten oder Backtest-Einträge anlegen.

Geprüft (feste Zeitpunkte, keine Wall-Clock, kein Netz):
- (A) ``trading_date.us_session_state``: 'closing' für 16:00–16:19 ET,
  'post' ab 16:20 ET — Sommer (EDT) und Winter (EST).
- (B) ``resolve_run_phase``: Handstart postclose um 16:19 ET → premarket
  (``close_not_final_override``), um 16:20 ET → postclose; premarket um
  16:19 bleibt premarket, um 16:20 → postclose. Sommer + Winter.
- (C) Append-Gate (``_append_backtest_entries``): 16:19 ET → kein Append
  (Rückgabe 0, History nicht geladen); 16:20 ET → Gate passiert. Sommer +
  Winter.
- (D) Cron: Postclose-Cron ist ``37 21 * * 1-5`` (Workflow == Python-
  Zuordnung), 21:37 UTC liegt im Winter (16:37 ET) und Sommer (17:37 ET)
  nach 16:20 → resolve=postclose UND Append-Gate passiert. Premarket-Cron
  unverändert ``17 6 * * 1-5``.
- (E) Eine Quelle: Vintage-Guard, Exit-Shadow, Frontend-Konstante und
  Redeploy-Grenze (1620) hängen an ``US_CLOSE_FINAL_ET``.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import types
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

if "yfinance" not in sys.modules:   # backtest_history importiert yf modul-weit
    _yf = types.ModuleType("yfinance")
    _yf.download = lambda *a, **k: None
    _yf.Ticker = lambda *a, **k: None
    sys.modules["yfinance"] = _yf

import trading_date  # noqa: E402
import backtest_history as bh  # noqa: E402
import exit_shadow  # noqa: E402
from resolve_run_phase import resolve_run_phase, POSTCLOSE_CRONS  # noqa: E402

ET = ZoneInfo("America/New_York")
_fails: list[str] = []


def _check(name: str, got, want) -> None:
    if got == want:
        print(f"  OK  {name}")
    else:
        _fails.append(f"{name}: got {got!r}, want {want!r}")
        print(f"  FAIL {name}: got {got!r}, want {want!r}")


def _utc(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


# Sommer: Mi 10.06.2026 (EDT, UTC-4) · Winter: Mi 04.11.2026 (EST, UTC-5)
SUMMER = (2026, 6, 10, 4)   # (y, mo, d, utc_offset_h)
WINTER = (2026, 11, 4, 5)


def _at_et(season, h, mi):
    y, mo, d, off = season
    return _utc(y, mo, d, h + off, mi)


def _rd(season):
    y, mo, d, _ = season
    return f"{d:02d}.{mo:02d}.{y}"


print("=== A — us_session_state (Sommer/Winter) ===")
for name, season in (("Sommer", SUMMER), ("Winter", WINTER)):
    _check(f"A {name} 15:59 ET open",
           trading_date.us_session_state(_at_et(season, 15, 59)), "open")
    _check(f"A {name} 16:00 ET closing",
           trading_date.us_session_state(_at_et(season, 16, 0)), "closing")
    _check(f"A {name} 16:19 ET closing",
           trading_date.us_session_state(_at_et(season, 16, 19)), "closing")
    _check(f"A {name} 16:20 ET post",
           trading_date.us_session_state(_at_et(season, 16, 20)), "post")


def _disp(inp, now):
    return resolve_run_phase(event_name="workflow_dispatch", schedule=None,
                             user_input=inp, now_utc=now)


print("\n=== B — resolve_run_phase Handstart (Sommer/Winter) ===")
for name, season in (("Sommer", SUMMER), ("Winter", WINTER)):
    _check(f"B {name} 16:19 postclose → premarket",
           _disp("postclose", _at_et(season, 16, 19)),
           ("premarket", "close_not_final_override"))
    _check(f"B {name} 16:20 postclose → postclose",
           _disp("postclose", _at_et(season, 16, 20)), ("postclose", None))
    _check(f"B {name} 16:19 premarket bleibt",
           _disp("premarket", _at_et(season, 16, 19)), ("premarket", None))
    _check(f"B {name} 16:20 premarket → postclose",
           _disp("premarket", _at_et(season, 16, 20)),
           ("postclose", "post_close_override"))


class _GatePassed(Exception):
    pass


def _append_outcome(season, h, mi) -> str:
    """Ruft das echte ``_append_backtest_entries`` mit festem ``now_et``.
    'skip' = Rückgabe 0 vor dem Laden; 'append' = Gate passiert (Laden der
    History wird abgefangen, nichts geschrieben)."""
    now_et = _at_et(season, h, mi).astimezone(ET)
    orig_load, orig_log = bh._load_backtest_history, bh._VINTAGE_GUARD_LOG
    tmp = tempfile.mktemp(suffix=".jsonl")

    def _boom():
        raise _GatePassed()
    try:
        bh._load_backtest_history = _boom
        bh._VINTAGE_GUARD_LOG = tmp
        try:
            n = bh._append_backtest_entries(
                [{"ticker": "TST"}], _rd(season), 1,
                compute_sub_scores_fn=lambda s: {}, safe_float_fn=lambda v: v,
                now_et=now_et)
        except _GatePassed:
            return "append"
        return "skip" if n == 0 else f"n={n}"
    finally:
        bh._load_backtest_history = orig_load
        bh._VINTAGE_GUARD_LOG = orig_log
        try:
            os.unlink(tmp)
        except OSError:
            pass


print("\n=== C — Append-Gate (echtes _append_backtest_entries) ===")
for name, season in (("Sommer", SUMMER), ("Winter", WINTER)):
    _check(f"C {name} 16:19 ET → kein Append", _append_outcome(season, 16, 19), "skip")
    _check(f"C {name} 16:20 ET → Append", _append_outcome(season, 16, 20), "append")

print("\n=== D — Cron-Läufe ===")
wf = open(os.path.join(ROOT, ".github", "workflows", "daily-squeeze-report.yml"),
          encoding="utf-8").read()
crons = re.findall(r"cron:\s*'([^']+)'", wf)
_check("D Workflow-Crons", sorted(crons), sorted(["17 6 * * 1-5", "37 21 * * 1-5"]))
_check("D Postclose-Cron == POSTCLOSE_CRONS[0]", POSTCLOSE_CRONS[0], "37 21 * * 1-5")
_check("D Premarket-Cron → premarket",
       resolve_run_phase("schedule", "17 6 * * 1-5", None, _utc(2026, 11, 4, 6, 17)),
       ("premarket", None))
for name, season, utc_h in (("Winter", WINTER, 21), ("Sommer", SUMMER, 21)):
    y, mo, d, _ = season
    t = _utc(y, mo, d, utc_h, 37)
    _check(f"D {name} Cron 21:37 UTC → postclose",
           resolve_run_phase("schedule", "37 21 * * 1-5", None, t), ("postclose", None))
    _check(f"D {name} 21:37 UTC nach 16:20 ET",
           t.astimezone(ET).time() >= trading_date.US_CLOSE_FINAL_ET, True)
    et = t.astimezone(ET)
    _check(f"D {name} Cron 21:37 UTC → Append",
           _append_outcome(season, et.hour, et.minute), "append")

print("\n=== E — eine Quelle ===")
_check("E Vintage-Guard", bh._VINTAGE_MKT_CLOSE is trading_date.US_CLOSE_FINAL_ET, True)
_check("E Exit-Shadow", exit_shadow._MKT_CLOSE is trading_date.US_CLOSE_FINAL_ET, True)
_check("E Exit-Shadow 16:19 postclose → kein Log",
       exit_shadow.should_log_exit_shadow("postclose", _at_et(WINTER, 16, 19).astimezone(ET)), False)
gr = open(os.path.join(ROOT, "generate_report.py"), encoding="utf-8").read()
_check("E Frontend-Konstante aus trading_date",
       "_US_CLOSE_FINAL_ET_MIN = trading_date.US_CLOSE_FINAL_ET.hour * 60 + "
       "trading_date.US_CLOSE_FINAL_ET.minute" in gr, True)
_check("E Frontend 'closing'-Zweig",
       "if (mins < {_US_CLOSE_FINAL_ET_MIN}) return 'closing';" in gr, True)
rd = open(os.path.join(ROOT, ".github", "workflows", "redeploy-on-source-change.yml"),
          encoding="utf-8").read()
_hhmm = trading_date.US_CLOSE_FINAL_ET.hour * 100 + trading_date.US_CLOSE_FINAL_ET.minute
_check("E Redeploy-Grenze == US_CLOSE_FINAL_ET", f'-lt {_hhmm} ]' in rd, True)

if _fails:
    print(f"\n{len(_fails)} Fehler:")
    for f in _fails:
        print("  -", f)
    sys.exit(1)
print("\nAlle Postclose-Grenz-Tests bestanden.")
