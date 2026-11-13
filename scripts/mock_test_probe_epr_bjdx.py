#!/usr/bin/env python3
"""Tests für scripts/probe_epr_measure.py + scripts/probe_bjdx_actions.py —
nur synthetische Daten, kein Netz."""
from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import probe_bjdx_actions as pb  # noqa: E402
import probe_epr_measure as pe  # noqa: E402
import truth_check as tc  # noqa: E402

_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


def _days(start: date, n: int, skip=()):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5 and d.isoformat() not in pe.config.US_MARKET_HOLIDAYS and d not in skip:
            out.append(d)
        d += timedelta(days=1)
    return out


def _series(closes, start=date(2026, 9, 1), skip=(), actions=None):
    ds = _days(start, len(closes), skip)
    return tc.Series([{"d": d, "c": c, "h": c, "l": c, "div": 0.0,
                       "split": (actions or {}).get(d, 0.0)} for d, c in zip(ds, closes)]), ds


TOL = 0.02
FC = date(2026, 11, 12)
TODAY = date(2026, 11, 13)


def test_evaluate():
    s, ds = _series([10, 10, 10, 10, 10, 11, 11, 11])
    e = ds[5]
    r = pe.evaluate_one(10.0, 11.0, s, e, FC, TODAY, TOL)
    check("stimmt (11/10 = +10 %)", r["status"] == "stimmt" and r["neu"] == 10.0, r)
    r = pe.evaluate_one(10.0, None, s, e, FC, TODAY, TOL)
    check("deterministisch: gleiche Daten → gleiches Ergebnis",
          r == pe.evaluate_one(10.0, None, s, e, FC, TODAY, TOL))
    r = pe.evaluate_one(9.0, 10.9, s, e, FC, TODAY, TOL)
    check("Zähler = Laufzeitkurs erkannt", r["status"] == "abweichung" and r["ursache"] == "zaehler_laufzeitkurs", r)
    r = pe.evaluate_one(9.0, None, s, e, FC, TODAY, TOL)
    check("sonst → sonstiges", r["ursache"] == "sonstiges", r)
    r = pe.evaluate_one(-5.0, None, s, e, FC, TODAY, TOL)
    check("Vorzeichen-Wechsel gezählt", r["vorzeichen_wechsel"] is True, r)
    check("Toleranzrand 0,02 stimmt", pe.evaluate_one(10.02, None, s, e, FC, TODAY, TOL)["status"] == "stimmt")
    # Lücke: Ticker fehlt an einem US-Handelstag zwischen Nenner und Einstieg.
    gap = _days(date(2026, 9, 1), 8)[3]
    s2, ds2 = _series([10, 10, 10, 10, 10, 11, 11, 11], skip=(gap,))
    e2 = ds2[5]
    r = pe.evaluate_one(5.0, None, s2, e2, FC, TODAY, TOL)
    check("Lücke im gemeinsamen Index erkannt", r["ursache"] == "luecke_index"
          and r["nenner_eigen"] != r["nenner_kalender"], r)
    s3, ds3 = _series([10, 10, 10, 10, 10, 11, 11, 11, 11, 11],
                      actions={_days(date(2026, 9, 1), 10)[8]: 0.25})
    r = pe.evaluate_one(9.0, None, s3, ds3[5], FC, TODAY, TOL)
    check("Aktion zwischen Nenner und heute → aktion_seit_nenner", r["ursache"] == "aktion_seit_nenner", r)
    check("kein Wert → unbekannt", pe.evaluate_one(None, None, s, e, FC, TODAY, TOL)["grund"] == "kein_gespeicherter_wert")
    check("keine Reihe → unbekannt", pe.evaluate_one(1.0, None, None, e, FC, TODAY, TOL)["grund"] == "keine_kursreihe")
    check("< 5 Tage davor → unbekannt", pe.evaluate_one(1.0, None, s, ds[3], FC, TODAY, TOL)["grund"] == "zu_wenig_tage_davor")
    check("nicht endgültig → unbekannt",
          pe.evaluate_one(1.0, None, s, e, ds[4], TODAY, TOL)["grund"] == "nicht_endgueltig")


def test_rank_and_summary():
    rs = pe.rank_summary([(1, 1), (2, 2), (3, 3), (4, 4)])
    check("Spearman identisch = 1", rs["spearman"] == 1.0 and rs["rang_wandert_ueber_2"] == 0, rs)
    rs = pe.rank_summary([(1, 4), (2, 3), (3, 2), (4, 1)])
    check("Spearman umgekehrt = -1", rs["spearman"] == -1.0 and rs["rang_wanderung_max"] == 3.0, rs)
    res = [{"status": "abweichung", "delta": 0.5, "vorzeichen_wechsel": False, "ursache": "sonstiges",
            "ticker": "XYZ", "date": "30.10.2026", "alt": 1.0, "neu": 1.5},
           {"status": "stimmt", "delta": 0.0, "vorzeichen_wechsel": False, "ticker": "ABC",
            "date": "30.10.2026", "alt": 2.0, "neu": 2.0},
           {"status": "unbekannt", "grund": "keine_kursreihe"}]
    b = pe.summarize(res, blind=True)
    check("Blind: keine Ticker/Daten in der Zusammenfassung",
          "XYZ" not in json.dumps(b) and "30.10.2026" not in json.dumps(b), b)
    check("Blind: Anzahl + Größe vorhanden", b["weicht_ab"] == 1 and b["groesste"][0]["delta"] == 0.5)
    p = pe.summarize(res, blind=False)
    check("Vorfenster: Ticker der größten Fälle", p["groesste"][0]["ticker"] == "XYZ")
    check("unbekannt nach Grund", p["unbekannt"] == {"keine_kursreihe": 1}, p["unbekannt"])


def test_load_rows_blind():
    with tempfile.TemporaryDirectory() as t:
        r = pathlib.Path(t)
        ex = [{"ticker": "A", "date": "30.10.2026", "provenance": "forward", "entry_past_return_5d": 1.0,
               "return_10d": 99.0, "max_gain_pct": 50.0, "entry_price": 2.0},
              {"ticker": "B", "date": "15.07.2026", "provenance": "backfill", "entry_past_return_5d": 3.0}]
        (r / pe.config.MATURED_EXPORT_FILE).write_text("\n".join(json.dumps(x) for x in ex) + "\n")
        bh = [{"ticker": "A", "date": "30.10.2026", "entry_past_return_5d": 1.5, "return_3d": 7.0},
              {"ticker": "C", "date": "01.08.2026", "entry_past_return_5d": 2.0},
              {"ticker": "D", "date": "01.08.2026", "source": "bootstrap", "entry_past_return_5d": 2.0},
              {"ticker": "E", "date": "01.07.2026", "entry_past_return_5d": 2.0}]
        (r / pe.config.BACKTEST_FILE).write_text(json.dumps(bh))
        rows, diff = pe.load_rows(r)
    check("forward ∪ bh ab 21.07. ohne Bootstrap/Backfill", sorted(rows) == [("A", "30.10.2026"), ("C", "01.08.2026")], rows)
    check("Export-Wert hat Vorrang, Unterschied gezählt", rows[("A", "30.10.2026")]["wert"] == 1.0 and diff == 1)
    check("Projektion: kein Ergebnisfeld übernommen",
          all(set(v) == {"wert", "entry_price", "quelle"} for v in rows.values()))
    src = (ROOT / "scripts" / "probe_epr_measure.py").read_text(encoding="utf-8")
    bad = [p for p in (r"(?<!past_)return_\d+d", r"_t1\b", r"_net\b", "vs_spy", "max_gain",
                       "max_drawdown", "forward_", "outcome") if re.search(p, src)]
    check("BLINDHEIT: Skript nennt kein Ergebnisfeld", not bad, bad)
    check("KEEP enthält nur Prädiktor + Kennung + Kurs-Snapshot",
          set(pe.KEEP) == {"ticker", "date", "provenance", "source", "entry_price", "entry_past_return_5d"})


def test_main_rate_limit_and_writes():
    with tempfile.TemporaryDirectory() as t:
        out = pathlib.Path(t) / "x" / "epr.json"
        orig_fa, orig_lr = tc.fetch_all, pe.load_rows
        pe.load_rows = lambda root=None: ({("A", "30.09.2026"): {"wert": 1.0, "entry_price": None,
                                                                  "quelle": "export"}}, 0)
        tc.fetch_all = lambda *a, **k: ({}, {"A": "rate_limit"})
        try:
            rc = pe.main(["--out", str(out), "--now", "2026-11-13T18:00:00Z"])
            check("Rate-Limit → Exit 3, keine Ergebnisdatei", rc == 3 and not out.exists())
            s, ds = _series([10, 10, 10, 10, 10, 11], start=date(2026, 9, 23))
            pe.load_rows = lambda root=None: ({("A", ds[5].strftime("%d.%m.%Y")):
                                               {"wert": 10.0, "entry_price": None, "quelle": "export"}}, 0)
            tc.fetch_all = lambda *a, **k: ({"A": s}, {})
            rc = pe.main(["--out", str(out), "--now", "2026-11-13T18:00:00Z"])
            res = json.loads(out.read_text())
            check("Lauf ok → genau Ergebnisdatei", rc == 0 and res["vor_2410"]["stimmt"] == 1, res)
            check("no-op nach Probe-Ende", pe.main(["--out", str(out), "--now", "2026-12-07T18:00:00Z"]) == 0)
        finally:
            tc.fetch_all, pe.load_rows = orig_fa, orig_lr
    for p in ("probe_epr_measure.py", "probe_bjdx_actions.py"):
        src = (ROOT / "scripts" / p).read_text(encoding="utf-8")
        check(f"{p}: öffnet keine Datei zum Schreiben im Repo",
              not re.search(r"open\([^)]*['\"][wa]['\"]", src) and "ROOT /" not in src.split("write_text")[0][-400:])
    wf = (ROOT / ".github" / "workflows" / "probe_epr_bjdx.yml").read_text(encoding="utf-8")
    check("Workflow: nur Hand-Start, nur lesen, keine Secrets, kein Push",
          "workflow_dispatch" in wf and "schedule" not in wf and "contents: read" in wf
          and "git push" not in wf and "secrets." not in wf)


def test_bjdx():
    check("Nachkommastellen 5.4 → 1", pb.decimals(5.400000095367432) == 1)
    check("Nachkommastellen 1.2345 → 4", pb.decimals(1.2345) == 4)
    check("Nachkommastellen None", pb.decimals(None) is None)
    check("BJDX-Daten alle vor Blind-Fenster", all(tc._dmy(d) < pb.BLIND_FROM for d in pb.BJDX_DATES))

    class RL(Exception):
        pass
    RL.__name__ = "YFRateLimitError"
    orig = pb.fetch
    pb.fetch = lambda t, end: (_ for _ in ()).throw(RL("x"))
    try:
        with tempfile.TemporaryDirectory() as t:
            out = pathlib.Path(t) / "b.json"
            rc = pb.main(["--out", str(out)])
            check("BJDX-Probe: Rate-Limit → Exit 3, keine Datei", rc == 3 and not out.exists())
    finally:
        pb.fetch = orig


def main() -> int:
    for fn in (test_evaluate, test_rank_and_summary, test_load_rows_blind,
               test_main_rate_limit_and_writes, test_bjdx):
        print(fn.__name__)
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle probe_epr_bjdx-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
