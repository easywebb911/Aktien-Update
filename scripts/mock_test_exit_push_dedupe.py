"""Mock-Tests für das Exit-Push-Dedupe (Flanke + Tages-Cap, 23.07.2026).

Kontext (Easy 23.07.): Die Phase-2-Exit-Pushes fluteten — derselbe (Ticker,
Trigger) feuerte bei jedem stündlichen Tick erneut (Warnung alle 12h, jeder
Crit-Trigger alle 24h, unbebündelt). Messung: 62 exit_p2-Pushes in 8 Tagen,
AI/IONQ 4×/Tag, LENZ/PDYN/WOLF derselbe trend_break 6 Tage in Folge.

Neue Mechanik in ``ki_agent.process_exit_signals``:
  - Bundle-Kanal (Warnung + Crit-Trigger < 75): max 1 gebündelter Push pro
    Ticker pro US-Handelstag, nur beim Flanken-Übergang inaktiv→aktiv.
  - Eskalations-Kanal (pressure > 75): once-per-band-episode, durchbricht den
    Tages-Cap (Easy-Entscheid).
  - State: state["exit_push_dedupe"][ticker]. Fail-safe: fehlt/korrupt → Push.

Kein Netzwerk: ``_send_exit_p2_push`` wird gemockt (Call-Recorder). ``now`` wird
injiziert (deterministische Handelstage). Reiner In-Memory-Test.

EXZELLENZ-Abdeckung:
  (a) gleicher Trigger über 5 Ticks → genau 1 Push
  (b) zweiter Ticker parallel → eigener Push, nie verschluckt
  (c) Flapping (an/aus/an am selben Tag) → 1 Push (Tages-Cap fängt Flattern)
  (d) neuer Handelstag → wieder scharf (bei frischer Flanke) — sustained bleibt 1
  (e) korrupter State → Push geht raus
  + Bündelung, Eskalations-Durchbruch, once-per-episode, Validity-Gate,
    Nicht-Handelstag-Gate, Send-Fehler-Retry, Pruning, Realismus-Replay.
"""
from __future__ import annotations

import pathlib
import sys
import types
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Minimal-CI (#316: nur jinja2+pyyaml) hat pandas/requests/yfinance NICHT —
# ki_agent importiert die aber auf Modul-Ebene. Stub-Module einschieben, damit
# der Import durchläuft (wir rufen nur process_exit_signals, kein Netz/Daten).
for _m in ("pandas", "requests", "yfinance"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)

import ki_agent  # noqa: E402

_fails: list[str] = []
_CALLS: list[dict] = []
_SEND_OK = [True]  # mutable flag: steuert _send_exit_p2_push-Erfolg


def _fake_send(ticker: str, body: str, severity: str = "trigger") -> bool:
    _CALLS.append({"ticker": ticker, "body": body, "severity": severity})
    return _SEND_OK[0]


# Monkeypatch: kein Netzwerk, kein ntfy.
ki_agent._send_exit_p2_push = _fake_send

# Handelstage (alle Wochentage, keine US-Feiertage im Juli nach dem 4.):
# Mo 20.07., Di 21.07., Mi 22.07., Do 23.07.2026. ET = UTC-4 (EDT).
D = {
    1: datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc),  # Mo → ET 11:00
    2: datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc),  # Di
    3: datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc),  # Mi
    4: datetime(2026, 7, 23, 15, 0, tzinfo=timezone.utc),  # Do
}
SAT = datetime(2026, 7, 25, 15, 0, tzinfo=timezone.utc)     # Samstag


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def _reset():
    _CALLS.clear()
    _SEND_OK[0] = True


def _appdata(*positions):
    """positions: (ticker, pressure, triggers_dict, prev_pressure|None).
    triggers_dict: {tname: (crit_bool, available_bool)}."""
    pos = {}
    for tk, pressure, trigs, prev in positions:
        es = {
            "exit_pressure": pressure,
            "triggers": {n: {"crit": c, "available": a, "details": {}}
                         for n, (c, a) in (trigs or {}).items()},
        }
        if prev is not None:
            es["prev_exit_pressure"] = prev
        pos[tk] = {"exit_state": es}
    return {"positions": pos}


def _tick(app_data, state, now):
    ki_agent.process_exit_signals(app_data, state, now=now)


# ─────────────────────────────────────────────────────────────────────────────
def test_a_same_trigger_5_ticks_one_push():
    _reset()
    state = {}
    for h in range(5):  # 5 Ticks am selben Handelstag
        ad = _appdata(("AI", 40.0, {"trend_break": (True, True)}, 30.0))
        _tick(ad, state, D[1] + timedelta(hours=h))
    _check("(a) gleicher Trigger über 5 Ticks → genau 1 Push",
           len(_CALLS) == 1, f"got {len(_CALLS)}: {[c['body'] for c in _CALLS]}")


def test_b_second_ticker_own_push():
    _reset()
    state = {}
    ad = _appdata(("AI", 40.0, {"trend_break": (True, True)}, 30.0),
                  ("IONQ", 40.0, {"trend_break": (True, True)}, 30.0))
    _tick(ad, state, D[1])
    tickers = sorted(c["ticker"] for c in _CALLS)
    _check("(b) zweiter Ticker parallel → eigener Push (nie verschluckt)",
           tickers == ["AI", "IONQ"], f"got {tickers}")


def test_c_flapping_same_day_one_push():
    _reset()
    state = {}
    seq = [(True, True), (False, True), (True, True)]  # an / aus / an
    for h, (crit, avail) in enumerate(seq):
        ad = _appdata(("AI", 40.0, {"trend_break": (crit, avail)}, 30.0))
        _tick(ad, state, D[1] + timedelta(hours=h))
    _check("(c) Flapping an/aus/an am selben Tag → 1 Push (Tages-Cap)",
           len(_CALLS) == 1, f"got {len(_CALLS)}")


def test_d_new_day_rearms_on_edge():
    _reset()
    state = {}
    # D1: aktiv → Push. Später am D1 inaktiv. D2: aktiv → frische Flanke → Push.
    _tick(_appdata(("AI", 40.0, {"trend_break": (True, True)}, 30.0)), state, D[1])
    _tick(_appdata(("AI", 40.0, {"trend_break": (False, True)}, 30.0)),
          state, D[1] + timedelta(hours=1))
    _tick(_appdata(("AI", 40.0, {"trend_break": (True, True)}, 30.0)), state, D[2])
    _check("(d) neuer Handelstag + frische Flanke → wieder scharf (2 Pushes)",
           len(_CALLS) == 2, f"got {len(_CALLS)}")


def test_d2_sustained_across_days_stays_one():
    _reset()
    state = {}
    # Realismus-Replay LENZ: derselbe trend_break crit an 4 Handelstagen in Folge,
    # NIE zwischendurch inaktiv → darf nur 1× pushen (Anti-Flut-Kern).
    for day in (1, 2, 3, 4):
        ad = _appdata(("LENZ", 39.0, {"trend_break": (True, True)}, 30.0))
        _tick(ad, state, D[day])
    _check("(d2) SUSTAINED über 4 Handelstage → genau 1 Push (Anti-Flut)",
           len(_CALLS) == 1, f"got {len(_CALLS)}: {[c['ticker'] for c in _CALLS]}")


def test_e_corrupt_state_pushes():
    _reset()
    # State-Dedupe-Sub-Dict korrupt (kein Dict) → fail-safe → Push.
    state = {"exit_push_dedupe": "NOT-A-DICT"}
    ad = _appdata(("AI", 40.0, {"trend_break": (True, True)}, 30.0))
    _tick(ad, state, D[1])
    ok1 = len(_CALLS) == 1
    # Pro-Ticker-Eintrag korrupt (String statt Dict) → fail-safe → Push.
    _reset()
    state = {"exit_push_dedupe": {"AI": "CORRUPT"}}
    _tick(_appdata(("AI", 40.0, {"trend_break": (True, True)}, 30.0)), state, D[1])
    ok2 = len(_CALLS) == 1
    _check("(e) korrupter State (Sub-Dict + Pro-Ticker) → Push geht raus",
           ok1 and ok2, f"sub={ok1} ticker={ok2}")


def test_bundling_multi_trigger_one_push():
    _reset()
    state = {}
    ad = _appdata(("AI", 40.0,
                   {"trend_break": (True, True), "profit_lock": (True, True)},
                   30.0))
    _tick(ad, state, D[1])
    body = _CALLS[0]["body"] if _CALLS else ""
    _check("Bündelung: 2 Crit-Trigger → 1 Push der BEIDE nennt",
           len(_CALLS) == 1 and "trend_break" in body and "profit_lock" in body,
           f"n={len(_CALLS)} body={body!r}")


def test_warning_bundled_with_trigger():
    _reset()
    state = {}
    # pressure 60 (Warnung) + ein Crit-Trigger → EIN Push, severity=trigger.
    ad = _appdata(("AI", 60.0, {"trend_break": (True, True)}, 30.0))
    _tick(ad, state, D[1])
    _check("Warnung + Crit → 1 gebündelter Push (severity=trigger)",
           len(_CALLS) == 1 and _CALLS[0]["severity"] == "trigger"
           and "pressure 60" in _CALLS[0]["body"],
           f"{_CALLS}")


def test_warning_only_deduped_across_day():
    _reset()
    state = {}
    # AI-Warnung-Fall: pressure parkt in 55..75 über mehrere Ticks → 1 Push
    # (vorher: alle 12h neu).
    for h in (0, 6, 12, 18):
        ad = _appdata(("AI", 63.0, {}, 40.0))
        _tick(ad, state, D[1] + timedelta(hours=h))
    _check("Reine Warnung parkt in 55..75 → 1 Push/Tag (kein 12h-Repeat)",
           len(_CALLS) == 1 and _CALLS[0]["severity"] == "warning",
           f"got {len(_CALLS)}")


def test_escalation_punches_through_day_cap():
    _reset()
    state = {}
    # Morgens Warnung (Tages-Cap gesetzt), nachmittags Cross >75 → Eskalation
    # MUSS trotz Tages-Cap durch.
    _tick(_appdata(("AI", 60.0, {}, 40.0)), state, D[1])              # warning
    _tick(_appdata(("AI", 82.0, {}, 60.0)), state, D[1] + timedelta(hours=4))  # cross
    sevs = [c["severity"] for c in _CALLS]
    _check("Eskalation durchbricht den Tages-Cap (warning → escalation)",
           sevs == ["warning", "escalation"], f"got {sevs}")


def test_escalation_once_per_episode():
    _reset()
    state = {}
    # Cross → esc. Sustained >75 (prev bleibt 60, Daily-Run-Wert) → KEIN Repeat.
    # Drop < 55, dann erneuter Cross → wieder esc.
    _tick(_appdata(("AI", 80.0, {}, 60.0)), state, D[1])                       # esc
    _tick(_appdata(("AI", 82.0, {}, 60.0)), state, D[1] + timedelta(hours=1))  # sustained
    _tick(_appdata(("AI", 85.0, {}, 60.0)), state, D[1] + timedelta(hours=2))  # sustained
    n_after_sustained = len(_CALLS)
    _tick(_appdata(("AI", 50.0, {}, 60.0)), state, D[2])                       # drop <55
    _tick(_appdata(("AI", 80.0, {}, 60.0)), state, D[2] + timedelta(hours=1))  # re-cross
    sevs = [c["severity"] for c in _CALLS]
    _check("Eskalation once-per-band-episode (sustained kein Repeat)",
           n_after_sustained == 1, f"after sustained got {n_after_sustained}")
    _check("Eskalation re-armt nach Drop <75 + erneutem Cross",
           sevs == ["escalation", "escalation"], f"got {sevs}")


def test_validity_gate_suppresses():
    _reset()
    state = {}
    # crit=True aber available=False → zählt NICHT als aktiv → kein Push.
    ad = _appdata(("AI", 40.0, {"trend_break": (True, False)}, 30.0))
    _tick(ad, state, D[1])
    _check("Validity-Gate: crit=True + available=False → kein Push",
           len(_CALLS) == 0, f"got {len(_CALLS)}")


def test_non_trading_day_skips_all():
    _reset()
    state = {}
    ad = _appdata(("AI", 82.0, {"trend_break": (True, True)}, 40.0))
    _tick(ad, state, SAT)  # Samstag
    _check("Nicht-Handelstag (Samstag) → gesamte Pipeline skippt",
           len(_CALLS) == 0, f"got {len(_CALLS)}")


def test_send_failure_retries_next_tick():
    _reset()
    state = {}
    _SEND_OK[0] = False  # Send scheitert
    _tick(_appdata(("AI", 40.0, {"trend_break": (True, True)}, 30.0)),
          state, D[1])
    failed_attempt = len(_CALLS)  # 1 Versuch, aber _ok=False → kein State-Consume
    _SEND_OK[0] = True  # Send klappt nächsten Tick
    _tick(_appdata(("AI", 40.0, {"trend_break": (True, True)}, 30.0)),
          state, D[1] + timedelta(hours=1))
    _check("Send-Fehler → kein State-Consume → nächster Tick retried (Push geht raus)",
           failed_attempt == 1 and len(_CALLS) == 2
           and _CALLS[1]["ticker"] == "AI",
           f"attempts={failed_attempt} total={len(_CALLS)}")


def test_no_exit_alerts_optout():
    _reset()
    state = {}
    ad = {"positions": {"AI": {
        "no_exit_alerts": True,
        "exit_state": {"exit_pressure": 82.0, "prev_exit_pressure": 40.0,
                       "triggers": {"trend_break": {"crit": True,
                                                    "available": True}}}}}}
    _tick(ad, state, D[1])
    _check("no_exit_alerts=True → komplett unterdrückt",
           len(_CALLS) == 0, f"got {len(_CALLS)}")


def test_prune_removes_stale():
    state = {"exit_push_dedupe": {
        "OLD": {"last_active": [], "last_push_date": "2026-06-01",
                "esc_alerted": False,
                "updated": (ki_agent.now_berlin() - timedelta(days=40)).isoformat()},
        "FRESH": {"last_active": [], "last_push_date": "2026-07-23",
                  "esc_alerted": False,
                  "updated": ki_agent.now_berlin().isoformat()},
        "BAD": {"last_active": [], "updated": "not-a-date"},
    }}
    ki_agent._exit_dedupe_prune(state, now=ki_agent.now_berlin())
    keys = set(state["exit_push_dedupe"].keys())
    _check("Pruning: alte (>30d) + unparsebare Einträge raus, frische bleiben",
           keys == {"FRESH"}, f"got {keys}")


def test_realism_replay_ai_daily_collapse():
    _reset()
    state = {}
    # AI vorher: 4 Pushes/Tag (2 Warnung + trend_break + profit_lock). Mit Dedupe
    # sollte pro Handelstag mit SUSTAINED Zustand nur der erste Flanken-Tag pushen.
    for day in (1, 2, 3):
        for h in (0, 12):  # zwei Ticks/Tag (wie 06:xx + 21:xx grob)
            ad = _appdata(("AI", 63.0,
                           {"trend_break": (True, True),
                            "profit_lock": (True, True)}, 40.0))
            _tick(ad, state, D[day] + timedelta(hours=h))
    _check("Realismus: AI sustained über 3 Tage/6 Ticks → 1 Push (vorher ~12)",
           len(_CALLS) == 1, f"got {len(_CALLS)}")


def main():
    tests = [
        test_a_same_trigger_5_ticks_one_push,
        test_b_second_ticker_own_push,
        test_c_flapping_same_day_one_push,
        test_d_new_day_rearms_on_edge,
        test_d2_sustained_across_days_stays_one,
        test_e_corrupt_state_pushes,
        test_bundling_multi_trigger_one_push,
        test_warning_bundled_with_trigger,
        test_warning_only_deduped_across_day,
        test_escalation_punches_through_day_cap,
        test_escalation_once_per_episode,
        test_validity_gate_suppresses,
        test_non_trading_day_skips_all,
        test_send_failure_retries_next_tick,
        test_no_exit_alerts_optout,
        test_prune_removes_stale,
        test_realism_replay_ai_daily_collapse,
    ]
    print("── Exit-Push-Dedupe (Flanke + Tages-Cap) ──────────────────────────")
    for fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            _fails.append(fn.__name__)
            print(f"  FAIL {fn.__name__}: {exc!r}")
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print(f"✓ Alle {len(tests)} Tests bestanden (Flanke + Tages-Cap + Eskalations-"
          f"Durchbruch + Fail-safe + Pruning).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
