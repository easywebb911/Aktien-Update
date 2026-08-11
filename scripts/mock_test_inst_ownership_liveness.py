"""Mock-Tests für die inst_ownership_history-Liveness-Zeile im Digest (11.08.2026).

Muster #509 (fail-soft Backend-Leser, eine Zeile). DER DESIGN-KERN: LIVENESS,
NICHT Änderungen. Die #518-Sammlung ist change-based (Punkt nur bei 13F-Änderung,
quartalsweise) — eine „letzter neuer Punkt"-Anzeige stünde wochenlang still =
Fehlalarm-Falle. Deshalb misst die Zeile (a) die akkumulierte Datei-Struktur und
(b) ob der postclose-SAMMLER frisch lief (last_run_iso, 24h-Fenster des Digests).
Der Sammler läuft im Daily-Run → frischer Lauf = heute beobachtet, auch bei 0
neuen Punkten. Genau das trennt „Sammler tot" von „13F unverändert".

DREI ZUSTÄNDE MÜSSEN UNTERSCHEIDBAR SEIN (Kernanforderung):
  a) läuft            — Datei da + Lauf frisch
  b) noch nie gesammelt — Datei existiert nicht (KEIN Fehler, KEIN „0 beobachtet",
     KEIN „nicht ermittelbar" — HEUTIGER Zustand vor dem ersten postclose)
  c) kaputt           — Datei unlesbar/leer ODER Sammler-Lauf ausständig (tot)

Synthetische Dateien entsprechen dem #518-Schema EXAKT
({ticker: [{date, inst_ownership, insider_ownership}, …]}), aus dem Code gelesen.

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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


NOW = datetime(2026, 8, 12, 8, 47, tzinfo=timezone.utc)
FRESH = "2026-08-12T06:17:00Z"   # heute premarket → ~2.5 h → frisch
STALE = "2026-08-08T21:17:00Z"   # 4 Tage alt → Lauf ausständig

# #518-Schema exakt: {ticker: [{date, inst_ownership, insider_ownership}, …]}
SCHEMA = {
    "HTZ": [{"date": "2026-08-10", "inst_ownership": 1.187, "insider_ownership": 0.05}],
    "FTK": [{"date": "2026-08-10", "inst_ownership": 0.42, "insider_ownership": None},
            {"date": "2026-08-11", "inst_ownership": 0.44, "insider_ownership": None}],
}


def _synth(data) -> str:
    p = os.path.join(tempfile.mkdtemp(), "inst_ownership_history.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return p


def _line(path, run=FRESH, now=NOW):
    return hc.inst_ownership_liveness_line(path, last_run_iso=run, now_ts=now)


def main() -> int:
    # ── Die drei Zustände ─────────────────────────────────────────────────────
    print("=== drei Zustände a/b/c ===")
    a = _line(_synth(SCHEMA), run=FRESH)
    b = _line("/nonexistent/inst_ownership_history.json", run=FRESH)
    c_unparse = _line(_synth("__RAW__"), run=FRESH)   # überschrieben unten
    # unparsebare Datei separat schreiben (kein JSON)
    badp = os.path.join(tempfile.mkdtemp(), "x.json")
    open(badp, "w", encoding="utf-8").write("{ kein valides json")
    c_unparse = _line(badp, run=FRESH)
    c_empty = _line(_synth({}), run=FRESH)
    c_dead = _line(_synth(SCHEMA), run=STALE)

    _check("a) läuft: Datei da + Lauf frisch → 'läuft' + N Ticker + M Punkte",
           "läuft" in a and "2 Ticker" in a and "3 Punkte" in a)
    _check("b) noch nie: Datei fehlt → 'sammelt ab dem nächsten postclose'",
           "sammelt ab dem nächsten postclose" in b)
    _check("c) unparsebar → 'unlesbar/kaputt'", "unlesbar" in c_unparse)
    _check("c) leer ({}) → 'Datei leer'", "leer" in c_empty)
    _check("c) Sammler tot (Lauf ausständig) → 'ausständig'", "ausständig" in c_dead)

    # ── Kernanforderung: b und c NICHT verwechselbar ──────────────────────────
    print("\n=== b ≠ c (Kernanforderung, sonst wertlos) ===")
    _check("b nennt sich NICHT 'nicht ermittelbar'", "nicht ermittelbar" not in b)
    _check("b nennt sich NICHT '0 beobachtet'/'0 Ticker'",
           "0 beobachtet" not in b and "0 Ticker" not in b)
    _check("b nennt sich NICHT 'kaputt'/'unlesbar'/'leer'/'ausständig'",
           not any(w in b for w in ("kaputt", "unlesbar", "leer", "ausständig")))
    _check("b und c-unparsable sind VERSCHIEDENE Wortlaute", b != c_unparse)
    _check("b und c-empty sind VERSCHIEDENE Wortlaute", b != c_empty)
    _check("b und c-dead sind VERSCHIEDENE Wortlaute", b != c_dead)

    # ── SELBSTPRÜFUNG #1: Sammler tot vs 13F unverändert ──────────────────────
    print("\n=== Sammler tot vs 13F unverändert (stiller Ausfall sichtbar?) ===")
    # 13F unverändert: Lauf frisch, KEINE neuen Punkte (Datei identisch) → 'läuft'.
    unchanged = _line(_synth(SCHEMA), run=FRESH)
    dead = _line(_synth(SCHEMA), run=STALE)
    _check("13F unverändert (Lauf frisch) → 'läuft' (kein Fehlalarm trotz 0 neuer Punkte)",
           "läuft" in unchanged)
    _check("Sammler tot (Lauf ausständig) → 'ausständig' (Ausfall sichtbar)",
           "ausständig" in dead)
    _check("beide sind UNTERSCHEIDBAR (verschiedene Zeilen)", unchanged != dead)

    # ── Fail-soft (Digest darf NIE scheitern) ─────────────────────────────────
    print("\n=== fail-soft ===")
    _check("last_run_iso=None → Lauf ausständig (fail-safe: kann nicht frisch belegen)",
           "ausständig" in _line(_synth(SCHEMA), run=None))
    _check("last_run_iso kaputt → kein Crash, ausständig",
           isinstance(_line(_synth(SCHEMA), run="NICHT-ISO"), str))
    _check("Zeile ist NIE leer/None (alle Zustände)",
           all(isinstance(x, str) and x for x in (a, b, c_unparse, c_empty, c_dead)))
    # Reader ignoriert Müll ohne Crash (Nicht-Listen-Serie, Nicht-Dict-Punkt)
    junky = {"GOOD": [{"date": "2026-08-11", "inst_ownership": 0.5, "insider_ownership": 0.1}],
             "BADSERIES": "nicht-eine-liste",
             "MIXED": [{"date": "x", "inst_ownership": 0.3, "insider_ownership": None},
                       "nicht-ein-dict"]}
    jl = _line(_synth(junky), run=FRESH)
    _check("Reader zählt robust (GOOD+MIXED = 2 Ticker, 2 gültige Punkte)",
           "2 Ticker" in jl and "2 Punkte" in jl)

    # ── Schema-Treue: der Reader liest genau das #518-Format ──────────────────
    print("\n=== #518-Schema-Treue ===")
    st, counts = hc._read_inst_ownership_history(_synth(SCHEMA))
    _check("Reader: SCHEMA → ok, (2 Ticker, 3 Punkte)",
           st == "ok" and counts == (2, 3))

    # ── Digest-Verdrahtung: Zeile in allen 3 Klassen; weggelassen bei None ────
    print("\n=== format_digest_body-Verdrahtung ===")
    MARK = "🏛 Inst-Ownership: läuft · 2 Ticker · 3 Punkte"
    # OK-Klasse
    body_ok, _, _, _ = hc.format_digest_body(
        [], [], n_runs=3, last_run_iso="x", digest_date="2026-08-12",
        inst_own_line=MARK)
    # crit-Klasse
    crit = [{"id": "S3", "severity": "crit", "detail": "x", "count": 1}]
    body_crit, _, _, _ = hc.format_digest_body(
        crit, [], n_runs=3, last_run_iso="x", digest_date="2026-08-12",
        inst_own_line=MARK)
    # no-data-Klasse
    body_nd, _, _, _ = hc.format_digest_body(
        [], [], n_runs=0, last_run_iso=None, digest_date="2026-08-12",
        inst_own_line=MARK)
    _check("OK-Klasse enthält die Inst-Zeile", MARK in body_ok)
    _check("crit-Klasse enthält die Inst-Zeile", MARK in body_crit)
    _check("no-data-Klasse enthält die Inst-Zeile", MARK in body_nd)
    # backward-compat: ohne inst_own_line (Default None) keine Zeile
    body_none, _, _, _ = hc.format_digest_body(
        [], [], n_runs=3, last_run_iso="x", digest_date="2026-08-12")
    _check("Default None → keine Inst-Zeile (backward-compat)",
           "Inst-Ownership" not in body_none)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle inst_ownership-Liveness-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
