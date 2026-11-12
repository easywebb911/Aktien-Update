#!/usr/bin/env python3
"""Mock-Test Messlauf (scripts/settled_close_measure.py). Kein Netz.

  M1  stimmt / weicht_ab / neu_adjustiert / nicht_pruefbar richtig gezählt
  M2  nur ENDGÜLTIGE Zeilen (Zieltag nach final_cut → nicht_pruefbar)
  M3  Blindheit: Replikationsfenster ohne Werte, ohne Richtung
  M4  Verteilung |Δ| + Vorzeichen-Wechsel nur vor Replikation
  M5  Füllzeit-Eimer (ET) und Feldgruppen
  M6  Workflow: nur workflow_dispatch, kein Commit/Push, Rate-Limit-Abbruch,
      Daily-Run-Sperre, Git-Historie (fetch-depth 0)
  M7  Skript öffnet keine Datei zum Schreiben außer --out
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import settled_close_measure as m  # noqa: E402
import truth_check as tc  # noqa: E402

_fails: list[str] = []
UTC = _dt.timezone.utc


def _check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        _fails.append(name)


def _series(start, closes, div_at=None):
    rows, d, i = [], start, 0
    while i < len(closes):
        if d.weekday() < 5:
            rows.append({"d": d, "c": closes[i], "h": closes[i], "l": closes[i],
                         "div": 0.1 if div_at == i else 0.0, "split": 0.0})
            i += 1
        d += _dt.timedelta(days=1)
    return tc.Series(rows)


def test_eval():
    # Vor Replikation: Entry Mo 05.10.2026, T+3 = Do 08.10.
    s_pre = _series(_dt.date(2026, 10, 5), [10.0, 10.5, 11.0, 12.0, 12.5, 13.0])
    good = {"date": "05.10.2026", "ticker": "AAA", "return_3d": 20.0}
    bad = {"date": "05.10.2026", "ticker": "BBB", "return_3d": -1.0}   # neu +20 → Vorzeichenwechsel
    s_bbb = _series(_dt.date(2026, 10, 5), [10.0, 10.5, 11.0, 12.0, 12.5, 13.0])
    s_div = _series(_dt.date(2026, 10, 5), [10.0, 10.5, 11.0, 12.0, 12.5, 13.0], div_at=2)
    adj = {"date": "05.10.2026", "ticker": "CCC", "return_3d": 5.0}
    unk = {"date": "05.10.2026", "ticker": "DDD", "return_3d": 5.0}
    # Replikation: Entry Mo 26.10.2026, T+3 = Do 29.10.
    s_rep = _series(_dt.date(2026, 10, 26), [10.0, 10.5, 11.0, 12.0, 12.5])
    rep = {"date": "26.10.2026", "ticker": "EEE", "return_3d": 3.33}
    late = {"date": "26.10.2026", "ticker": "FFF", "return_5d": 1.0}   # T+5 = 02.11. > final_cut
    series = {"AAA": s_pre, "BBB": s_bbb, "CCC": s_div, "EEE": s_rep, "FFF": s_rep}
    items = [{"datei": "backtest", "row": r, "feld": f, "bucket": "zieltag_1620_2100"}
             for r, f in ((good, "return_3d"), (bad, "return_3d"), (adj, "return_3d"),
                          (unk, "return_3d"), (rep, "return_3d"), (late, "return_5d"))]
    ev = m.evaluate(items, series, {"DDD": "yahoo_fehler"}, _dt.date(2026, 10, 30), 0.02)
    c = ev["counts"]
    pre = c[("vor_replikation", "return", "zieltag_1620_2100")]
    _check("M1 vor Replikation: 1 stimmt, 1 weicht ab, 1 neu_adjustiert, 1 nicht prüfbar",
           pre == {"geprueft": 3, "stimmt": 1, "weicht_ab": 1, "neu_adjustiert": 1,
                   "nicht_pruefbar": 1}, str(pre))
    rp = c[("replikation", "return", "zieltag_1620_2100")]
    _check("M1 Replikation: 1 weicht ab", rp["weicht_ab"] == 1, str(rp))
    _check("M2 T+5 nach final_cut → nicht prüfbar", rp["nicht_pruefbar"] == 1, str(rp))
    _check("M4 Vorzeichen-Wechsel nur vor Replikation gezählt",
           ev["sign_pre"] == {"return": 1}, str(ev["sign_pre"]))
    _check("M4 |Δ| nur vor Replikation", list(ev["deltas_pre"]) == ["return"]
           and len(ev["deltas_pre"]["return"]) == 1)
    out = m.summarize(ev, {})
    txt = json.dumps(out)
    _check("M3 Ausgabe enthält keinen Replikations-Wert (3.33 / Ticker EEE)",
           "3.33" not in txt and "EEE" not in txt and "FFF" not in txt)
    _check("M3 Ausgabe enthält keine Ticker", not any(t in txt for t in ("AAA", "BBB", "CCC", "DDD")))
    rep_rows = [r for r in out["tabelle"] if r["fenster"] == "replikation"]
    _check("M3 Replikations-Zeilen nur Zählfelder",
           all(set(r) == {"fenster", "feldgruppe", "fuellzeit", "geprueft", "stimmt",
                          "weicht_ab", "neu_adjustiert", "nicht_pruefbar"} for r in rep_rows))


def test_buckets():
    tgt = _dt.date(2026, 11, 5)
    at = lambda hh, mm, d=5: _dt.datetime(2026, 11, d, hh, mm, tzinfo=m._NY)
    _check("M5 15:00 ET → zieltag_vor_1620", m.bucket_of(at(15, 0), tgt) == "zieltag_vor_1620")
    _check("M5 17:40 ET → zieltag_1620_2100", m.bucket_of(at(17, 40), tgt) == "zieltag_1620_2100")
    _check("M5 22:00 ET → zieltag_ab_2100", m.bucket_of(at(22, 0), tgt) == "zieltag_ab_2100")
    _check("M5 Folgetag → folgetag_oder_spaeter", m.bucket_of(at(8, 0, 6), tgt) == "folgetag_oder_spaeter")
    _check("M5 Gruppen", [m.group_of(f) for f in ("return_3d", "return_5d_t1", "return_10d_net", "forward_5d")]
           == ["return", "t1", "net", "forward"])
    _check("M5 Offsets", m.offset_of("return_10d_t1") == 11 and m.offset_of("forward_3d") == 3)


def test_workflow_and_source():
    wf = (ROOT / ".github/workflows/settled_close_measure.yml").read_text(encoding="utf-8")
    _check("M6 nur workflow_dispatch", "workflow_dispatch" in wf and "schedule" not in wf)
    _check("M6 kein Commit/Push", "git push" not in wf and "git commit" not in wf)
    _check("M6 contents: read", "contents: read" in wf)
    _check("M6 Daily-Run-Sperre", "daily-squeeze-report.yml" in wf)
    _check("M6 fetch-depth 0", "fetch-depth: 0" in wf)
    _check("M6 Artifact", "upload-artifact" in wf)
    src = (ROOT / "scripts/settled_close_measure.py").read_text(encoding="utf-8")
    _check("M7 nur --out wird geschrieben",
           src.count("write_text(") == 1 and "open(" not in src.replace("pathlib", ""))
    _check("M7 Rate-Limit → Exit 3", "return 3" in src)
    _check("M7 Grenze = last_settled_close_date", "last_settled_close_date(now)" in src)


def main() -> int:
    for t in (test_eval, test_buckets, test_workflow_and_source):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            _check(f"{t.__name__} ohne Exception", False, f"{type(exc).__name__}: {exc}")
    print()
    if _fails:
        print(f"{len(_fails)} FAIL")
        return 1
    print("Alle settled_close_measure-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
