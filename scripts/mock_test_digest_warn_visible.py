"""Mock-Test — aktive warns im OK-Digest sichtbar (07.11.2026).

Bis zur Schwelle (≥ 3 warn oder ≥ 1 crit → warn-Klasse) tauchten einzelne
warns im OK-Digest gar nicht auf. Belegt: S8 an 12.10./19.10./01.11.2026 (aus
health_check_log.jsonl, unten als feste Daten eingebettet) — Easy sah nur
„✅ Health-Check OK“. Jetzt: je aktive warn (State + Provider) eine Zeile
„🟡 <id>: …“; Titel/Priorität unverändert; S15-Sonderweg in die allgemeine
Regel überführt (keine Doppelzeile); crit-/warn-Klasse unverändert.

  A  1 State-warn ohne crit → Zeile sichtbar, Titel OK, Priorität default.
  B  Provider-warn → Zeile „🟡 <provider> (Tier n): <reason>“.
  C  Die 3 echten S8-Tage (Log-Auszug) → S8-Zeile sichtbar.
  D  S15 genau einmal; erholte warns nur „↩︎“, keine 🟡-Zeile.
  E  3 warns → warn-Klasse wie bisher (keine 🟡-OK-Zeilen), crit → warn-
     Klasse mit State-Fails-Liste (unverändert).
  F  Überlänge: Detail gekappt (≤ 240 Zeichen + „…“); Body > 3800 Bytes →
     warn-Zeilen bis auf die erste durch „🟡 +N weitere warn“ ersetzt.
Gegenprobe alter Stand: A, B, C, F scheitern.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402

_fails: list[str] = []


def _check(name, cond, detail=""):
    print(("  OK  " if cond else "  FAIL ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


def _body(state_fails, provider_fails=(), **kw):
    return hc.format_digest_body(list(state_fails), list(provider_fails), n_runs=5,
                                 last_run_iso="2026-11-07T10:00:00Z",
                                 digest_date="2026-11-07", **kw)


def _agg(fails, ts="2026-11-07T09:00:00Z"):
    return hc.aggregate_state_fails([{"run_ts": ts, "run_phase": "premarket",
                                      "state_fails": fails}])


# Echte Log-Auszüge (health_check_log.jsonl, 24-h-Fenster vor dem Digest).
S8_DAYS = json.loads(r"""{
 "2026-10-12": {
  "digest_ts": "2026-10-12T18:11:47Z",
  "entries": [
   {
    "run_ts": "2026-10-11T20:17:49Z",
    "run_phase": "ki_agent_tick",
    "state_fails": []
   },
   {
    "run_ts": "2026-10-12T00:32:58Z",
    "run_phase": "ki_agent_tick",
    "state_fails": []
   },
   {
    "run_ts": "2026-10-12T07:21:50Z",
    "run_phase": "ki_agent_tick",
    "state_fails": []
   },
   {
    "run_ts": "2026-10-12T15:28:00Z",
    "run_phase": "premarket",
    "state_fails": [
     {
      "id": "S8",
      "severity": "warn",
      "detail": "kein erfolgreicher Digest-Push seit 30.6 h (Schwelle 26 h) — silent ntfy-Fail oder Cron-Drop"
     }
    ]
   },
   {
    "run_ts": "2026-10-12T15:28:46Z",
    "run_phase": "ki_agent_tick",
    "state_fails": [
     {
      "id": "S8",
      "severity": "warn",
      "detail": "kein erfolgreicher Digest-Push seit 30.6 h (Schwelle 26 h) — silent ntfy-Fail oder Cron-Drop"
     }
    ]
   },
   {
    "run_ts": "2026-10-12T17:55:38Z",
    "run_phase": "ki_agent_tick",
    "state_fails": [
     {
      "id": "S8",
      "severity": "warn",
      "detail": "kein erfolgreicher Digest-Push seit 33.1 h (Schwelle 26 h) — silent ntfy-Fail oder Cron-Drop"
     }
    ]
   }
  ]
 },
 "2026-10-19": {
  "digest_ts": "2026-10-19T15:51:35Z",
  "entries": [
   {
    "run_ts": "2026-10-18T18:06:24Z",
    "run_phase": "ki_agent_tick",
    "state_fails": []
   },
   {
    "run_ts": "2026-10-18T20:44:12Z",
    "run_phase": "ki_agent_tick",
    "state_fails": []
   },
   {
    "run_ts": "2026-10-18T23:13:34Z",
    "run_phase": "ki_agent_tick",
    "state_fails": []
   },
   {
    "run_ts": "2026-10-19T01:17:41Z",
    "run_phase": "ki_agent_tick",
    "state_fails": []
   },
   {
    "run_ts": "2026-10-19T07:47:13Z",
    "run_phase": "ki_agent_tick",
    "state_fails": []
   },
   {
    "run_ts": "2026-10-19T13:18:25Z",
    "run_phase": "premarket",
    "state_fails": [
     {
      "id": "S8",
      "severity": "warn",
      "detail": "kein erfolgreicher Digest-Push seit 26.2 h (Schwelle 26 h) — silent ntfy-Fail oder Cron-Drop"
     }
    ]
   },
   {
    "run_ts": "2026-10-19T13:19:31Z",
    "run_phase": "ki_agent_tick",
    "state_fails": [
     {
      "id": "S8",
      "severity": "warn",
      "detail": "kein erfolgreicher Digest-Push seit 26.2 h (Schwelle 26 h) — silent ntfy-Fail oder Cron-Drop"
     }
    ]
   },
   {
    "run_ts": "2026-10-19T15:36:40Z",
    "run_phase": "ki_agent_tick",
    "state_fails": [
     {
      "id": "S8",
      "severity": "warn",
      "detail": "kein erfolgreicher Digest-Push seit 28.5 h (Schwelle 26 h) — silent ntfy-Fail oder Cron-Drop"
     }
    ]
   }
  ]
 },
 "2026-11-01": {
  "digest_ts": "2026-11-01T15:26:51Z",
  "entries": [
   {
    "run_ts": "2026-10-31T17:44:13Z",
    "run_phase": "ki_agent_tick",
    "state_fails": []
   },
   {
    "run_ts": "2026-10-31T21:35:21Z",
    "run_phase": "ki_agent_tick",
    "state_fails": []
   },
   {
    "run_ts": "2026-11-01T01:10:35Z",
    "run_phase": "ki_agent_tick",
    "state_fails": []
   },
   {
    "run_ts": "2026-11-01T07:33:14Z",
    "run_phase": "ki_agent_tick",
    "state_fails": []
   },
   {
    "run_ts": "2026-11-01T15:09:54Z",
    "run_phase": "ki_agent_tick",
    "state_fails": [
     {
      "id": "S8",
      "severity": "warn",
      "detail": "kein erfolgreicher Digest-Push seit 26.7 h (Schwelle 26 h) — silent ntfy-Fail oder Cron-Drop"
     }
    ]
   }
  ]
 }
}""")


def main():
    print("=== A — 1 State-warn ===")
    w = {"id": "S5", "severity": "warn", "detail": "score_inflation_log: 4 neue Zeile(n)"}
    body, title, prio, tags = _body(_agg([w]))
    _check("A Zeile sichtbar", "🟡 S5: score_inflation_log: 4 neue Zeile(n)" in body, body)
    _check("A Titel/Priorität unverändert", (title, prio, tags) == ("✅ Health-Check OK", "default", None),
           (title, prio, tags))

    print("\n=== B — Provider-warn ===")
    pf = [{"provider": "finra", "tier": 2, "severity": "warn", "reason": "3 Runs in Folge HTTP 503",
           "consecutive": 3}]
    body, title, _p, _t = _body([], pf)
    _check("B Provider-Zeile", "🟡 finra (Tier 2): 3 Runs in Folge HTTP 503" in body, body)
    _check("B Titel OK", title == "✅ Health-Check OK")

    print("\n=== C — echte S8-Tage ===")
    for day, d in S8_DAYS.items():
        agg = hc.aggregate_state_fails(d["entries"])
        body, title, _p, _t = _body(agg)
        _check(f"C {day} S8 sichtbar", "🟡 S8: kein erfolgreicher Digest-Push" in body
               and title == "✅ Health-Check OK", body)

    print("\n=== D — S15 einmal / erholt ===")
    s15 = {"id": "S15", "severity": "warn", "detail": "Postclose für 04.11.2026 fehlt"}
    body, _t, _p, _x = _body(_agg([s15]))
    _check("D S15 genau eine Zeile", body.count("S15") == 1 and "🟡 S15: Postclose" in body, body)
    rec = hc.aggregate_state_fails([
        {"run_ts": "2026-11-06T09:00:00Z", "run_phase": "premarket", "state_fails": [s15]},
        {"run_ts": "2026-11-07T09:00:00Z", "run_phase": "premarket", "state_fails": []}])
    body, _t, _p, _x = _body(rec)
    _check("D erholt → nur ↩︎", "↩︎ S15 erholt" in body and "🟡" not in body, body)
    body0, _t, _p, _x = _body([])
    _check("D ohne warn keine 🟡-Zeile", "🟡" not in body0)

    print("\n=== E — warn-/crit-Klasse unverändert ===")
    three = [{"id": f"S{i}", "severity": "warn", "detail": f"d{i}"} for i in (5, 6, 7)]
    body, title, prio, _x = _body(_agg(three))
    _check("E 3 warns → warn-Klasse", title == "⚠️ Health-Check-Digest" and prio == "high", title)
    _check("E warn-Klasse ohne 🟡-OK-Zeilen", "🟡 S5:" not in body and "  • S5: d5" in body, body)
    crit = [{"id": "S1", "severity": "crit", "detail": "x"}, w]
    body, title, _p, _x = _body(_agg(crit))
    _check("E crit → warn-Klasse, Liste wie bisher",
           title == "⚠️ Health-Check-Digest" and "  • S1: x" in body and "  • S5:" in body
           and "🟡 S5:" not in body, body)

    print("\n=== F — Überlänge ===")
    longw = {"id": "S10", "severity": "warn", "detail": "ä" * 1000}
    body, _t, _p, _x = _body(_agg([longw]))
    line = [l for l in body.splitlines() if l.startswith("🟡 S10:")][0]
    _check("F Detail gekappt", line.endswith("…") and len(line) <= len("🟡 S10: ") + hc._OK_WARN_DETAIL_MAX,
           len(line))
    w2 = [{"id": "S10", "severity": "warn", "detail": "a" * 1000},
          {"id": "S11", "severity": "warn", "detail": "b" * 1000}]
    filler = ["x" * 300 for _ in range(11)]   # ~3,3 KB übrige Zeilen
    body, title, _p, _x = _body(_agg(w2), weekly_lines=filler)
    _check("F Body ≤ DIGEST_BODY_SAFE_BYTES", len(body.encode("utf-8")) <= hc.DIGEST_BODY_SAFE_BYTES,
           len(body.encode("utf-8")))
    _check("F erste warn bleibt, Rest „+1 weitere“",
           "🟡 S10:" in body and "🟡 S11:" not in body and "🟡 +1 weitere warn" in body, body[-400:])
    _check("F Titel OK", title == "✅ Health-Check OK")
    big = _body(_agg(w2))[0]
    print(f"  (Worst Case OK-Klasse: 2 warns à 240 Zeichen → "
          f"{sum(len(l.encode('utf-8')) for l in big.splitlines() if l.startswith('🟡'))} Bytes warn-Zeilen)")

    if _fails:
        print(f"\n{len(_fails)} Fehler: {_fails}")
        sys.exit(1)
    print("\nAlle OK-Digest-warn-Tests bestanden.")


if __name__ == "__main__":
    main()
