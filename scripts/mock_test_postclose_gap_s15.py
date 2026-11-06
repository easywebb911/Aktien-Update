"""Mock-Test — S15: Postclose des letzten Handelstags fehlt (06.11.2026).

Anlass: Postclose 04.11.2026 ausgefallen (GitHub verwarf vermutlich den
wartenden 21:17-Lauf beim Cron-Wechsel #656) und 27.08.2026 (Lauf startete
01:28 ET am Folgetag → Berichtsdatum 28.08., Vintage-Guard ``pre_open``).
S12 (crit) meldet erst nach > 2 Werktagen; S15 macht EINEN fehlenden Tag im
nächsten Digest als warn sichtbar.

Feste Daten, feste Zeitpunkte, kein Netz:
  A  Echter Fall 04.11. (Datenstand wie auf main am 05./06.11.): Premarket
     05.11. 14:41 UTC und Postclose 06.11. 01:48 UTC → S15 „04.11.2026";
     Premarket 06.11. 14:17 UTC (05.11. vorhanden) → still.
  B  Normaler Tag (Vortag vorhanden) → still.
  C  Montag nach Freitag-Ausfall → S15 „06.11.2026"; Wochenend-Lauf ebenso.
  D  Feiertag (Thanksgiving 26.11.2026) wird übersprungen → Freitag 27.11.
     prüft 25.11.; fehlt 25.11. → S15 „25.11.2026".
  E  Mitternachts-Falle 28.08.2026 01:28 ET → S15 „27.08.2026".
  F  Prune/alte Daten: letzter Handelstag älter als der älteste Eintrag → still;
     Bootstrap-Einträge zählen nicht.
  G  Rückwärts-kompatibel: ohne backtest_path / ki_agent_only / Datei fehlt /
     kaputt → kein S15.
  H  Digest: einzelne S15-warn erscheint im OK-Digest als Hinweis-Zeile
     (Titel bleibt OK); ohne S15 kein Hinweis; im warn-Digest gelistet;
     crit-Digest + Diagnose-Prompt bleibt ≤ DIGEST_BODY_SAFE_BYTES.
Gegenprobe: auf dem alten Stand (ohne S15) scheitern A, C, D, E, H.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402

_fails: list[str] = []


def _check(name, cond, detail=""):
    print(("  OK  " if cond else "  FAIL ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


def _utc(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def _write(path, days, *, bootstrap_days=()):
    rows = []
    for d in days:
        for i in range(10):
            rows.append({"ticker": f"T{i}", "date": d.strftime("%d.%m.%Y"),
                         "score": 50.0})
    for d in bootstrap_days:
        rows.append({"ticker": "BOOT", "date": d.strftime("%d.%m.%Y"),
                     "source": "bootstrap"})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)


def _s15(path, now, **kw):
    """S15-Fails aus dem echten evaluate_state_invariants (Daily-Run-Pfad).
    Andere Invarianten lesen ihre Dateien relativ zum cwd (tmp, leer) —
    hier zählt nur S15."""
    fails = hc.evaluate_state_invariants(
        run_phase=kw.pop("run_phase", "premarket"), now_utc=now,
        backtest_path=path, **kw)
    return [f for f in fails if f.get("id") == "S15"]


def main():
    wd = tempfile.mkdtemp(prefix="mock_s15_")
    cwd = os.getcwd()
    os.chdir(wd)
    try:
        bt = os.path.join(wd, "backtest_history.json")
        D = lambda d, m: date(2026, m, d)  # noqa: E731

        print("=== A — echter Fall 04.11.2026 ===")
        stand = [D(29, 10), D(30, 10), D(2, 11), D(3, 11)]
        _write(bt, stand)
        f = _s15(bt, _utc(2026, 11, 5, 14, 41))
        _check("A Premarket 05.11. meldet 04.11.", len(f) == 1 and "04.11.2026" in f[0]["detail"], f)
        _check("A severity warn", bool(f) and f[0]["severity"] == "warn", f)
        _write(bt, stand + [D(5, 11)])
        f = _s15(bt, _utc(2026, 11, 6, 1, 48), run_phase="postclose")
        _check("A Postclose 05.11. (06.11. 01:48 UTC) meldet weiter 04.11.",
               len(f) == 1 and "04.11.2026" in f[0]["detail"], f)
        f = _s15(bt, _utc(2026, 11, 6, 14, 17))
        _check("A Premarket 06.11. (05.11. vorhanden) still", f == [], f)

        print("\n=== B — normaler Tag ===")
        _write(bt, [D(2, 11), D(3, 11)])
        _check("B Premarket 04.11. (03.11. vorhanden) still",
               _s15(bt, _utc(2026, 11, 4, 14, 32)) == [])
        _check("B Postclose 03.11. nach Mitternacht UTC (ET noch 03.11.) still",
               _s15(bt, _utc(2026, 11, 4, 1, 26), run_phase="postclose") == [])

        print("\n=== C — Montag nach Freitag-Ausfall ===")
        _write(bt, [D(4, 11), D(5, 11)])   # Fr 06.11. fehlt
        f = _s15(bt, _utc(2026, 11, 9, 14, 30))
        _check("C Montag 09.11. meldet Freitag 06.11.", len(f) == 1 and "06.11.2026" in f[0]["detail"], f)
        f = _s15(bt, _utc(2026, 11, 7, 15, 0))
        _check("C Samstag-Lauf meldet ebenfalls 06.11.", len(f) == 1 and "06.11.2026" in f[0]["detail"], f)
        _write(bt, [D(5, 11), D(6, 11)])
        _check("C Montag mit Freitag vorhanden still", _s15(bt, _utc(2026, 11, 9, 14, 30)) == [])

        print("\n=== D — Feiertag (Thanksgiving 26.11.2026) ===")
        _check("D 26.11.2026 ist in US_MARKET_HOLIDAYS",
               "2026-11-26" in hc.config.US_MARKET_HOLIDAYS)
        _write(bt, [D(24, 11), D(25, 11)])
        _check("D Freitag 27.11. prüft 25.11. (vorhanden) → still",
               _s15(bt, _utc(2026, 11, 27, 14, 30)) == [])
        _write(bt, [D(23, 11), D(24, 11)])
        f = _s15(bt, _utc(2026, 11, 27, 14, 30))
        _check("D fehlt 25.11. → meldet 25.11. (nicht den Feiertag)",
               len(f) == 1 and "25.11.2026" in f[0]["detail"], f)

        print("\n=== E — Mitternachts-Falle 27.08.2026 ===")
        _write(bt, [D(25, 8), D(26, 8)])
        f = _s15(bt, _utc(2026, 8, 28, 5, 28), run_phase="postclose")
        _check("E Lauf 01:28 ET am 28.08. meldet 27.08.",
               len(f) == 1 and "27.08.2026" in f[0]["detail"], f)

        print("\n=== F — Prune / alte Daten / Bootstrap ===")
        _write(bt, [D(2, 9), D(3, 9)])
        _check("F letzter Handelstag älter als ältester Eintrag → still",
               _s15(bt, _utc(2026, 6, 10, 14, 0)) == [])
        _write(bt, [D(2, 11), D(3, 11)], bootstrap_days=[D(4, 11), D(1, 1)])
        f = _s15(bt, _utc(2026, 11, 5, 14, 41))
        _check("F Bootstrap-Eintrag mit Datum 04.11. zählt nicht",
               len(f) == 1 and "04.11.2026" in f[0]["detail"], f)

        print("\n=== G — Rückwärts-kompatibel ===")
        _write(bt, [D(2, 11), D(3, 11)])
        fails = hc.evaluate_state_invariants(run_phase="premarket",
                                             now_utc=_utc(2026, 11, 5, 14, 41))
        _check("G ohne backtest_path kein S15", not any(x["id"] == "S15" for x in fails))
        fails = hc.evaluate_state_invariants(run_phase="premarket", ki_agent_only=True,
                                             now_utc=_utc(2026, 11, 5, 14, 41),
                                             backtest_path=bt)
        _check("G ki_agent_only kein S15", not any(x["id"] == "S15" for x in fails))
        _check("G Datei fehlt → kein S15",
               _s15(os.path.join(wd, "fehlt.json"), _utc(2026, 11, 5, 14, 41)) == [])
        with open(bt, "w") as fh:
            fh.write("{kaputt")
        _check("G kaputte Datei → kein S15", _s15(bt, _utc(2026, 11, 5, 14, 41)) == [])

        print("\n=== H — Digest ===")
        s15 = {"id": "S15", "severity": "warn",
               "detail": "Postclose für 04.11.2026 fehlt (keine Backtest-Einträge "
                         "mit diesem Datum) — Datenlücke, Nachholen nicht mehr möglich"}
        entries = [{"run_ts": "2026-11-05T14:41:00Z", "run_phase": "premarket",
                    "state_fails": [s15]}]
        agg = hc.aggregate_state_fails(entries)
        body, title, prio, _tags = hc.format_digest_body(
            agg, [], n_runs=5, last_run_iso="2026-11-05T14:41:00Z",
            digest_date="2026-11-05")
        _check("H OK-Digest zeigt S15-Zeile", "🟡 S15: Postclose für 04.11.2026 fehlt" in body, body)
        _check("H Titel bleibt OK, Priorität default",
               title == "✅ Health-Check OK" and prio == "default", (title, prio))
        body0, title0, _p, _t = hc.format_digest_body(
            [], [], n_runs=5, last_run_iso="2026-11-05T14:41:00Z",
            digest_date="2026-11-05")
        _check("H ohne S15 keine Hinweis-Zeile", "S15" not in body0 and title0 == title)
        rec = [{"run_ts": "2026-11-05T14:41:00Z", "run_phase": "premarket",
                "state_fails": [s15]},
               {"run_ts": "2026-11-06T14:17:00Z", "run_phase": "premarket",
                "state_fails": []}]
        body_r, _t1, _p1, _x = hc.format_digest_body(
            hc.aggregate_state_fails(rec), [], n_runs=5,
            last_run_iso="2026-11-06T14:17:00Z", digest_date="2026-11-06")
        _check("H erholt → kein 🟡, nur ↩︎-Hinweis",
               "🟡 S15" not in body_r and "↩︎ S15 erholt" in body_r, body_r)
        warns = [s15] + [{"id": f"S{i}", "severity": "warn", "detail": "x"} for i in (5, 6)]
        body_w, title_w, _p2, _x2 = hc.format_digest_body(
            hc.aggregate_state_fails([{"run_ts": "2026-11-05T14:41:00Z",
                                       "run_phase": "premarket",
                                       "state_fails": warns}]), [],
            n_runs=5, last_run_iso="x", digest_date="2026-11-05")
        _check("H warn-Digest listet S15 genau einmal",
               title_w == "⚠️ Health-Check-Digest" and body_w.count("S15:") == 1, body_w)
        crit = [s15] + [{"id": f"S{i}", "severity": "crit",
                         "detail": "y" * 120} for i in (1, 2, 3, 12)]
        body_c, _t3, _p3, _x3 = hc.format_digest_body(
            hc.aggregate_state_fails([{"run_ts": "2026-11-05T14:41:00Z",
                                       "run_phase": "premarket",
                                       "state_fails": crit}]), [],
            n_runs=5, last_run_iso="x", digest_date="2026-11-05")
        _check("H crit-Digest ≤ DIGEST_BODY_SAFE_BYTES",
               len(body_c.encode("utf-8")) <= hc.DIGEST_BODY_SAFE_BYTES,
               len(body_c.encode("utf-8")))
        print(f"  (S15-Zeile: {len(('🟡 S15: ' + s15['detail']).encode('utf-8'))} Bytes)")
    finally:
        os.chdir(cwd)
        shutil.rmtree(wd, ignore_errors=True)

    if _fails:
        print(f"\n{len(_fails)} Fehler: {_fails}")
        sys.exit(1)
    print("\nAlle S15-Tests bestanden.")


if __name__ == "__main__":
    main()
