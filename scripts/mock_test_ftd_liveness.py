"""Mock-Tests für die ftd_history-Liveness-Zeile im Digest (11.08.2026).

Muster #520. FTD schreibt neue Punkte nur, wenn SEC ein neues Halbmonats-File
veröffentlicht (~2×/Monat) — „Punkte wachsen nicht" ist der NORMALFALL, nicht
„kaputt". Die Frische kommt deshalb aus dem HEARTBEAT (Sidecar last_run), nicht
aus dem neuesten Punkt-Datum.

DREI ZUSTÄNDE MÜSSEN UNTERSCHEIDBAR SEIN:
  a) läuft — Heartbeat frisch + gesunder last_result.
  b) noch nie gesammelt — kein State + keine Daten (KEIN Fehlerton).
  c) kaputt — State/Datei unlesbar, Heartbeat überfällig, oder Quelle kaputt.

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


def _files(state=None, hist=None):
    d = tempfile.mkdtemp()
    H = os.path.join(d, "ftd_history.json")
    S = os.path.join(d, "ftd_history_state.json")
    if state is not None:
        with open(S, "w", encoding="utf-8") as fh:
            fh.write(state if isinstance(state, str) else json.dumps(state))
    if hist is not None:
        with open(H, "w", encoding="utf-8") as fh:
            fh.write(hist if isinstance(hist, str) else json.dumps(hist))
    return H, S


_DATA = {"TNXP": [{"settlement_date": "2026-07-01", "first_available": "2026-08-05",
                   "fails": 123, "price": 1.2, "source_file": "cnsfails202607a.zip"}]}


def main() -> int:
    # ── b) noch nie: kein State, keine Datei ──────────────────────────────────
    H, S = _files()
    line_b = hc.ftd_liveness_line(H, S, now_ts=NOW)
    _check("b) never → 'sammelt ab dem nächsten postclose'",
           "sammelt ab dem nächsten postclose" in line_b)
    _check("b) never trägt KEINEN Fehlerton (kein 'kaputt'/'überfällig')",
           "kaputt" not in line_b and "überfällig" not in line_b)

    # ── a) läuft: frischer Heartbeat + no_new_file + Daten ────────────────────
    H, S = _files(state={"last_run": "2026-08-11T02:00:00Z", "last_result": "no_new_file",
                         "last_ingested_file": "cnsfails202607a.zip"}, hist=_DATA)
    line_a = hc.ftd_liveness_line(H, S, now_ts=NOW)
    _check("a) frisch+no_new_file+Daten → 'läuft'", "läuft" in line_a)
    _check("a) zeigt neuestes File + Ticker/Punkte + zuletzt-verfügbar",
           "cnsfails202607a.zip" in line_a and "1 Ticker" in line_a
           and "1 Punkte" in line_a and "2026-08-05" in line_a)
    _check("a) 'kein neues File' ist NICHT als kaputt markiert",
           "kaputt" not in line_a and "überfällig" not in line_a)

    # ── c) überfällig: Heartbeat > 90h alt ───────────────────────────────────
    H, S = _files(state={"last_run": "2026-08-01T02:00:00Z", "last_result": "no_new_file"},
                  hist=_DATA)
    line_overdue = hc.ftd_liveness_line(H, S, now_ts=NOW)
    _check("c) überfällig → 'Sammler-Lauf überfällig' + letzter Lauf",
           "überfällig" in line_overdue and "2026-08-01" in line_overdue)

    # ── c) Quelle kaputt: frischer Heartbeat, aber fetch_failed ───────────────
    H, S = _files(state={"last_run": "2026-08-11T02:00:00Z",
                         "last_result": "fetch_failed:overview"}, hist=_DATA)
    line_src = hc.ftd_liveness_line(H, S, now_ts=NOW)
    _check("c) Quelle kaputt → 'läuft, aber Quelle kaputt'",
           "Quelle kaputt" in line_src and "fetch_failed:overview" in line_src)

    # ── c) State-Datei unlesbar ───────────────────────────────────────────────
    H, S = _files(state="{broken json", hist=_DATA)
    line_sx = hc.ftd_liveness_line(H, S, now_ts=NOW)
    _check("c) State unlesbar → 'State-Datei unlesbar/kaputt'",
           "State-Datei unlesbar/kaputt" in line_sx)

    # ── c) History-Datei unlesbar (State ok) ──────────────────────────────────
    H, S = _files(state={"last_run": "2026-08-11T02:00:00Z", "last_result": "no_new_file"},
                  hist="{broken")
    line_hx = hc.ftd_liveness_line(H, S, now_ts=NOW)
    _check("c) History unlesbar → 'Datei unlesbar/kaputt'",
           "Datei unlesbar/kaputt" in line_hx and "State" not in line_hx)

    # ── b) ≠ c): alle Wortlaute eindeutig verschieden ─────────────────────────
    variants = [line_b, line_a, line_overdue, line_src, line_sx, line_hx]
    _check("b) ≠ jeder c)-Wortlaut (unterscheidbar)",
           line_b not in [line_overdue, line_src, line_sx, line_hx]
           and len(set(variants)) == len(variants))

    # ── Fail-soft: nie Exception, nie leer ────────────────────────────────────
    for lbl, arg in [("beide-None", (None, None)), ("dir", (tempfile.mkdtemp(), tempfile.mkdtemp()))]:
        try:
            r = hc.ftd_liveness_line(arg[0], arg[1], now_ts=NOW)
            _check(f"fail-soft {lbl}: nicht-leerer String", isinstance(r, str) and r.strip())
        except Exception as exc:
            _check(f"fail-soft {lbl}: KEINE Exception ({exc!r})", False)

    # ── Wiring in alle 3 Digest-Push-Klassen ──────────────────────────────────
    T = "📉 FTD: TESTLINE-XYZ"
    b1, *_ = hc.format_digest_body([], [], n_runs=0, last_run_iso=None,
                                   digest_date="2026-08-11", ftd_line=T)
    b2, *_ = hc.format_digest_body([], [], n_runs=5, last_run_iso="2026-08-11T08:00:00Z",
                                   digest_date="2026-08-11", ftd_line=T)
    b3, *_ = hc.format_digest_body([{"id": "S1", "severity": "crit", "detail": "x"}], [],
                                   n_runs=5, last_run_iso="2026-08-11T08:00:00Z",
                                   digest_date="2026-08-11", ftd_line=T)
    _check("wiring K1/K2/K3: Zeile in allen drei Bodies",
           T in b1 and T in b2 and T in b3)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle ftd_liveness-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
