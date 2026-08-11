"""Mock-Tests für die reg_sho_history-Liveness-Zeile im Digest (11.08.2026).

Muster #520/#525. Heartbeat-basiert (Sidecar last_run + Quell-Health). Drei
Zustände unterscheidbar (läuft / noch nie / kaputt). Die Zeile surfaced die
Börsen-Lücke via „K geprüft / M none".

Kategorie A: stdlib only, deterministisch.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402

_fails: list[str] = []
NOW = datetime(2026, 8, 11, 8, 47, tzinfo=timezone.utc)


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def _files(state=None, hist=None):
    d = tempfile.mkdtemp()
    H = os.path.join(d, "reg_sho_history.json")
    S = os.path.join(d, "reg_sho_state.json")
    if state is not None:
        with open(S, "w", encoding="utf-8") as fh:
            fh.write(state if isinstance(state, str) else json.dumps(state))
    if hist is not None:
        with open(H, "w", encoding="utf-8") as fh:
            fh.write(hist if isinstance(hist, str) else json.dumps(hist))
    return H, S


_DATA = {"TNXP": [{"date": "2026-08-11", "restricted": True, "reason": None,
                   "exchange": "NMS", "source": "nasdaq", "source_date": "2026-08-10"}]}


def main() -> int:
    # b) noch nie
    H, S = _files()
    b = hc.reg_sho_liveness_line(H, S, now_ts=NOW)
    _check("b) never → 'sammelt ab dem nächsten postclose'",
           "sammelt ab dem nächsten postclose" in b)
    _check("b) kein Fehlerton", "kaputt" not in b and "überfällig" not in b)

    # a) läuft — surfaced die Börsen-Lücke (geprüft/none)
    H, S = _files(state={"last_run": "2026-08-11T02:00:00Z", "nasdaq_result": "ok:70",
                         "nyse_result": "not_resolved", "last_checked": 8, "last_none": 2},
                  hist=_DATA)
    a = hc.reg_sho_liveness_line(H, S, now_ts=NOW)
    _check("a) läuft + nasdaq=ok + Börsen-Lücke sichtbar (8 geprüft / 2 none)",
           "läuft" in a and "nasdaq=ok:70" in a and "8 geprüft / 2 none" in a
           and "nyse=not_resolved" in a)

    # c) überfällig
    H, S = _files(state={"last_run": "2026-08-01T02:00:00Z", "nasdaq_result": "ok:70"}, hist=_DATA)
    c1 = hc.reg_sho_liveness_line(H, S, now_ts=NOW)
    _check("c) überfällig → 'Sammler-Lauf überfällig'", "überfällig" in c1 and "2026-08-01" in c1)

    # c) Nasdaq-Quelle tot (frischer Heartbeat)
    H, S = _files(state={"last_run": "2026-08-11T02:00:00Z", "nasdaq_result": "fetch_failed"}, hist=_DATA)
    c2 = hc.reg_sho_liveness_line(H, S, now_ts=NOW)
    _check("c) Nasdaq tot → 'läuft, aber Nasdaq-Quelle kaputt'",
           "Nasdaq-Quelle kaputt" in c2 and "fetch_failed" in c2)

    # c) State unlesbar
    H, S = _files(state="{broken", hist=_DATA)
    c3 = hc.reg_sho_liveness_line(H, S, now_ts=NOW)
    _check("c) State unlesbar → 'State-Datei unlesbar/kaputt'", "State-Datei unlesbar/kaputt" in c3)

    # b ≠ c
    _check("b) ≠ jede c)-Variante", len({b, a, c1, c2, c3}) == 5)

    # fail-soft
    for lbl, arg in [("None", (None, None)), ("dir", (tempfile.mkdtemp(), tempfile.mkdtemp()))]:
        try:
            r = hc.reg_sho_liveness_line(arg[0], arg[1], now_ts=NOW)
            _check(f"fail-soft {lbl}: nicht-leerer String", isinstance(r, str) and r.strip())
        except Exception as exc:
            _check(f"fail-soft {lbl}: keine Exception ({exc!r})", False)

    # Wiring in alle 3 Push-Klassen
    T = "🚫 Reg-SHO: TESTLINE-XYZ"
    b1, *_ = hc.format_digest_body([], [], n_runs=0, last_run_iso=None,
                                   digest_date="2026-08-11", reg_sho_line=T)
    b2, *_ = hc.format_digest_body([], [], n_runs=5, last_run_iso="2026-08-11T08:00:00Z",
                                   digest_date="2026-08-11", reg_sho_line=T)
    b3, *_ = hc.format_digest_body([{"id": "S1", "severity": "crit", "detail": "x"}], [],
                                   n_runs=5, last_run_iso="2026-08-11T08:00:00Z",
                                   digest_date="2026-08-11", reg_sho_line=T)
    _check("wiring K1/K2/K3", T in b1 and T in b2 and T in b3)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle reg_sho_liveness-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
