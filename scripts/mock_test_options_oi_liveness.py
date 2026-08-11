"""Mock-Tests für die options_oi_history-Liveness-Zeile im Digest (11.08.2026).

Muster #520 (inst_ownership_liveness): eine fail-soft Backend-Zeile, die LIVENESS
zeigt (nicht Änderungen). Der Sammler läuft NUR postclose → die Frische kommt aus
dem neuesten ``date`` IN DER DATEI, nicht aus dem generischen Daily-Run-Stempel.

DREI ZUSTÄNDE MÜSSEN UNTERSCHEIDBAR SEIN:
  a) läuft — Datei da + Stand frisch → „läuft · …".
  b) noch nie gesammelt — Datei fehlt → „sammelt ab dem nächsten postclose" (KEIN
     Fehlerton).
  c) kaputt — Datei unlesbar/leer, ODER Stand überfällig, ODER letzter Lauf 0 Ketten.

Wenn b) und c) gleich aussehen, ist die Überwachung wertlos → hier verriegelt.

Kategorie A: stdlib only, deterministisch, env-frei.
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


def _write(obj_or_text):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "options_oi_history.json")
    with open(p, "w", encoding="utf-8") as fh:
        if isinstance(obj_or_text, str):
            fh.write(obj_or_text)
        else:
            json.dump(obj_or_text, fh)
    return p


def _pt(date, chain=True):
    if not chain:
        return {"date": date, "expiry": None, "spot": 3.2,
                "shares_outstanding": None, "calls": None, "puts": None}
    return {"date": date, "expiry": "2026-08-15", "spot": 4.4,
            "shares_outstanding": 12_000_000,
            "calls": [{"strike": 5.0, "oi": 60, "iv": 0.8}], "puts": []}


def main() -> int:
    # ── b) noch nie gesammelt — Datei fehlt (KEIN Fehler) ─────────────────────
    absent = os.path.join(tempfile.mkdtemp(), "options_oi_history.json")
    line_b = hc.options_oi_liveness_line(absent, now_ts=NOW)
    _check("b) absent → 'sammelt ab dem nächsten postclose'",
           "sammelt ab dem nächsten postclose" in line_b)
    _check("b) absent trägt KEINEN Fehlerton (kein 'kaputt'/'überfällig'/'0 Ketten')",
           "kaputt" not in line_b and "überfällig" not in line_b
           and "0 Ketten" not in line_b)

    # ── c) kaputt: unparsable ─────────────────────────────────────────────────
    line_unparse = hc.options_oi_liveness_line(_write("{nope"), now_ts=NOW)
    _check("c) unparsable → 'Datei unlesbar/kaputt'",
           "unlesbar/kaputt" in line_unparse)

    # ── c) kaputt: empty dict ─────────────────────────────────────────────────
    line_empty = hc.options_oi_liveness_line(_write({}), now_ts=NOW)
    _check("c) empty → 'Datei leer'", "Datei leer" in line_empty)

    # ── a) läuft — frischer Stand + Kette da ──────────────────────────────────
    data_ok = {"TNXP": [_pt("2026-08-11", chain=True)],
               "INHD": [_pt("2026-08-11", chain=False)]}
    line_a = hc.options_oi_liveness_line(_write(data_ok), now_ts=NOW)
    _check("a) frisch → 'läuft'", "läuft" in line_a)
    _check("a) zählt Ticker-mit-Kette getrennt (1 von 2)",
           "1 Ticker mit Kette" in line_a and "von 2" in line_a)
    _check("a) trägt Gesamt-Ticker + Gesamt-Punkte (stiller-Ausfall-Sichtbarkeit)",
           "2 gesamt" in line_a and "2 Punkte" in line_a)

    # ── c) kaputt: Stand überfällig (>5 Kalendertage) ─────────────────────────
    data_old = {"TNXP": [_pt("2026-08-01", chain=True)]}   # 10 Tage alt
    line_overdue = hc.options_oi_liveness_line(_write(data_old), now_ts=NOW)
    _check("c) überfällig → 'Sammler-Lauf überfällig' + letzter Stand",
           "überfällig" in line_overdue and "2026-08-01" in line_overdue)

    # ── c) kaputt: letzter Lauf erfasste 0 Ketten (alle no_chain) ─────────────
    data_nochain = {"INHD": [_pt("2026-08-11", chain=False)]}
    line_0chains = hc.options_oi_liveness_line(_write(data_nochain), now_ts=NOW)
    _check("c) 0 Ketten am neuesten Datum → 'erfasste 0 Ketten' (kaputt/leer)",
           "0 Ketten" in line_0chains)

    # ── b) ≠ c): die Wortlaute sind eindeutig verschieden ─────────────────────
    _check("b) absent-Wortlaut ≠ jeder c)-Wortlaut (unterscheidbar)",
           line_b != line_unparse and line_b != line_empty
           and line_b != line_overdue and line_b != line_0chains)

    # ── Fail-soft: nie Exception, nie leer ────────────────────────────────────
    for label, arg in [("None-path", None), ("dir-statt-datei", tempfile.mkdtemp())]:
        try:
            r = hc.options_oi_liveness_line(arg, now_ts=NOW)
            _check(f"fail-soft {label}: liefert nicht-leeren String",
                   isinstance(r, str) and r.strip() != "")
        except Exception as exc:
            _check(f"fail-soft {label}: KEINE Exception ({exc!r})", False)

    # ── Reachability-Invariante: STALE_DAYS deckt das lange Wochenende ────────
    _check("STALE_DAYS ≥ 5 (Fr-Stand am Di-Digest ist 4 Tage → kein Fehlalarm)",
           hc._OPTIONS_OI_STALE_DAYS >= 5)

    # ── format_digest_body hängt options_oi_line in ALLE drei Push-Klassen ────
    TEST = "🎯 Options-OI: TESTLINE-XYZ"
    # Klasse 1: n_runs == 0 ("ohne Daten")
    b1, *_ = hc.format_digest_body([], [], n_runs=0, last_run_iso=None,
                                   digest_date="2026-08-11", options_oi_line=TEST)
    _check("wiring Klasse 1 (n_runs=0): Zeile im Body", TEST in b1)
    # Klasse 2: OK (n_runs>0, keine Fails)
    b2, *_ = hc.format_digest_body([], [], n_runs=5, last_run_iso="2026-08-11T08:00:00Z",
                                   digest_date="2026-08-11", options_oi_line=TEST)
    _check("wiring Klasse 2 (OK): Zeile im Body", TEST in b2)
    # Klasse 3: Fails (≥1 crit)
    crit = [{"id": "S1", "severity": "crit", "detail": "x"}]
    b3, *_ = hc.format_digest_body(crit, [], n_runs=5, last_run_iso="2026-08-11T08:00:00Z",
                                   digest_date="2026-08-11", options_oi_line=TEST)
    _check("wiring Klasse 3 (Fails): Zeile im Body", TEST in b3)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle options_oi_liveness-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
