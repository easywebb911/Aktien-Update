#!/usr/bin/env python3
"""Tests: entry_past_return_5d im Wahrheits-Abgleich nach der PRODUKTIONS-
Definition (Easy-Entscheid 13.11.2026). Ohne Netz.

Schreibpfade (geprüft):
  * Laufender Postclose ab 13.07.2026: ``_compute_entry_past_return_5d(s["price"],
    close_5td_before_entry)`` — Zähler = Kurs zum Laufzeitpunkt, gespeichert als
    ``entry_price`` (auf 4 Stellen gerundet, ``backtest_history.py``).
  * Stufe-B-Backfill 14.05.–10.07.2026 (Manifest): Schluss / Schluss.

Fälle (Kurse):
  * ARCT 01.09., AMCX 15.07., BJDX 14.07./15.07./05.08.: ECHTE Yahoo-Schlusskurse
    aus dem Beleg-Lauf 43488284245 (13.11.2026), float32 wie geliefert.
  * TTEC 01.10., INR 10.08.: Kurse REKONSTRUIERT aus den Kennzahlen des Messlaufs
    43488284245 (dort: gespeicherter Wert = entry_price / eigener Nenner innerhalb
    0,02; Schluss/Schluss-Wert = „neu“). Kein eigener Beleg, nur Konsistenz.
  * MNRO 25.08., CBRL 16.10.: Messlauf-Ursache „Aktion seit Nenner“ mit |Δ| 2,62 /
    0,45 pp. Eine Dividende NACH D skaliert Zähler und Nenner gleich (kein Δ über
    Rundung) — ein Δ dieser Größe kann nur aus einer Dividende zwischen Nenner und
    D kommen. Rekonstruiert mit Dividende in diesem Fenster.

Erwartete Verdikte: ARCT/AMCX/BJDX/TTEC/INR stimmen; MNRO/CBRL neu_adjustiert
(Dividende im Fenster, abs_delta mitgeschrieben); konstruierter Fehler (falscher
Nenner) → Abweichung; Split mit |Δ| über Schranke → Abweichung. S16 alarmiert
für keinen der geklärten Fälle. Determinismus.
"""
from __future__ import annotations

import json
import pathlib
import struct
import sys
from datetime import date, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import truth_check as tc  # noqa: E402
import mock_test_truth_check_known as mk  # noqa: E402

_fails: list[str] = []
TOL = float(tc.config.TRUTH_CHECK_TOLERANCE_PP)
FC, TODAY = date(2026, 11, 12), date(2026, 11, 13)


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


def f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


def series(closes: dict, *, splits=None, divs=None):
    rows = [{"d": date.fromisoformat(d), "c": f32(c), "h": f32(c), "l": f32(c), "div": 0.0, "split": 0.0}
            for d, c in closes.items()]
    for r in rows:
        r["split"] = (splits or {}).get(r["d"].isoformat(), r["split"])
        r["div"] = (divs or {}).get(r["d"].isoformat(), 0.0)
    return tc.Series(rows)


def classify(row, s):
    rec = tc.recompute_backtest(row, s, None, None, FC, TODAY)
    n, devs, _ = tc.compare_row("export", row, rec, {row["ticker"]: s}, TOL)
    return n, devs, rec


ARCT = series({"2026-08-24": 14.34, "2026-08-25": 15.44, "2026-08-26": 15.83, "2026-08-27": 16.17,
               "2026-08-28": 15.19, "2026-08-31": 14.76, "2026-09-01": 16.23, "2026-09-15": 15.84})
AMCX = series({"2026-07-07": 9.99, "2026-07-08": 10.07, "2026-07-09": 9.9, "2026-07-10": 9.92,
               "2026-07-13": 9.97, "2026-07-14": 9.82, "2026-07-15": 10.59, "2026-09-15": 12.19})
BJDX = series({"2026-07-07": 5.8, "2026-07-08": 5.36, "2026-07-09": 5.6, "2026-07-10": 5.8,
               "2026-07-13": 4.88, "2026-07-14": 5.0, "2026-07-15": 5.4, "2026-07-16": 5.2,
               "2026-07-17": 5.8, "2026-07-20": 4.84, "2026-07-21": 4.64, "2026-07-22": 4.6,
               "2026-07-23": 4.56, "2026-07-24": 4.12, "2026-07-27": 4.4, "2026-07-28": 4.0,
               "2026-07-29": 3.516, "2026-07-30": 3.716, "2026-07-31": 3.44, "2026-08-03": 3.768,
               "2026-08-04": 4.0, "2026-08-05": 4.96, "2026-11-03": 1.0}, splits={"2026-11-03": 0.25})


def recon(days, ep, alt, neu, div_day=None):
    """Rekonstruktion aus Messlauf-Kennzahlen: Nenner = Zähler-Definition der
    Produktion, Schluss D so, dass Schluss/Schluss = „neu“."""
    den = ep / (1 + alt / 100) if div_day is None else ep / (1 + neu / 100)
    close_d = den * (1 + neu / 100)
    closes = {d: den * (1 + 0.01 * k) for k, d in enumerate(days[:-1])}
    closes[days[0]] = den
    closes[days[-1]] = close_d
    closes["2026-11-10"] = close_d
    return series(closes, divs={div_day: 0.25} if div_day else None)


TTEC = recon(["2026-09-24", "2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"],
             1.485, 21.72, 22.13)
INR = recon(["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07", "2026-08-10"],
            13.94, 7.48, 7.56)
MNRO = recon(["2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24", "2026-08-25"],
             13.96, 17.81, 20.43, div_day="2026-08-21")
CBRL = recon(["2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"],
             68.97, 20.03, 20.48, div_day="2026-10-14")

CASES = [  # (Ticker, Datum, entry_price, gespeicherter Wert, Reihe, erwartet)
    ("ARCT", "01.09.2026", 16.225, 5.08, ARCT, "stimmt"),
    ("AMCX", "15.07.2026", 10.585, 5.11, AMCX, "stimmt"),
    ("BJDX", "14.07.2026", 1.25, -13.79, BJDX, "stimmt"),
    ("BJDX", "15.07.2026", 1.35, 0.75, BJDX, "stimmt"),
    ("BJDX", "05.08.2026", 1.24, 41.07, BJDX, "stimmt"),
    ("TTEC", "01.10.2026", 1.485, 21.72, TTEC, "stimmt"),
    ("INR", "10.08.2026", 13.94, 7.48, INR, "stimmt"),
    ("MNRO", "25.08.2026", 13.96, 17.81, MNRO, "neu_adjustiert"),
    ("CBRL", "16.10.2026", 68.97, 20.03, CBRL, "neu_adjustiert"),
]


def verdict(devs):
    if not devs:
        return "stimmt"
    return "abweichung" if any(d["klasse"] == "abweichung" for d in devs) else devs[0]["klasse"]


def test_real_cases():
    print("1 Echte/rekonstruierte Fälle → erwartetes Verdikt")
    for t, d, ep, alt, s, exp in CASES:
        row = {"ticker": t, "date": d, "entry_price": ep, "entry_past_return_5d": alt}
        n, devs, rec = classify(row, s)
        check(f"{t} {d}: {exp} (verglichen {n})", n == 1 and verdict(devs) == exp, (devs, rec))
    _, devs, _ = classify({"ticker": "MNRO", "date": "25.08.2026", "entry_price": 13.96,
                           "entry_past_return_5d": 17.81}, MNRO)
    check("MNRO: Dividende im Fenster, abs_delta 2,62 mitgeschrieben",
          devs and devs[0].get("regel") == "dividende_im_fenster"
          and abs(devs[0].get("abs_delta", 0) - 2.62) < 0.011, devs)
    _, devs, _ = classify({"ticker": "CBRL", "date": "16.10.2026", "entry_price": 68.97,
                           "entry_past_return_5d": 20.03}, CBRL)
    check("CBRL: abs_delta 0,45", devs and abs(devs[0].get("abs_delta", 0) - 0.45) < 0.011, devs)


def test_errors_alarm():
    print("2 Konstruierte Fehler → Alarm")
    # Falscher Nenner: gespeicherter Wert gegen den Schluss 4 statt 5 Tage davor.
    wrong = round((16.225 / f32(15.83) - 1) * 100, 2)
    _, devs, _ = classify({"ticker": "ARCT", "date": "01.09.2026", "entry_price": 16.225,
                           "entry_past_return_5d": wrong}, ARCT)
    check(f"ARCT mit falschem Nenner ({wrong}) → abweichung", verdict(devs) == "abweichung", devs)
    _, devs, _ = classify({"ticker": "AMCX", "date": "15.07.2026", "entry_price": 10.585,
                           "entry_past_return_5d": 5.16}, AMCX)
    check("AMCX mit Schluss/Schluss-Wert (5,16) → abweichung", verdict(devs) == "abweichung", devs)
    _, devs, _ = classify({"ticker": "BJDX", "date": "05.08.2026", "entry_price": 1.24,
                           "entry_past_return_5d": 41.3}, BJDX)
    check("BJDX Split nach D, Δ 0,23 über Schranke → abweichung", verdict(devs) == "abweichung", devs)
    # Split IM Fenster (03.11. liegt im Fenster eines späten Einstiegs) über Schranke.
    s_in = series({"2026-10-27": 4.0, "2026-10-28": 4.1, "2026-10-29": 4.2, "2026-10-30": 4.3,
                   "2026-11-02": 4.4, "2026-11-03": 4.5, "2026-11-04": 4.6, "2026-11-05": 4.7},
                  splits={"2026-11-03": 0.25})
    row = {"ticker": "XSPL", "date": "29.10.2026", "return_3d": 20.0}
    rec = tc.recompute_backtest(row, s_in, None, None, FC, TODAY)
    _, devs, _ = tc.compare_row("export", row, rec, {"XSPL": s_in}, TOL)
    check("Split im Fenster, Δ ≫ Schranke → abweichung (split_im_fenster_ueber_schranke)",
          devs and devs[0]["klasse"] == "abweichung"
          and devs[0].get("regel") == "split_im_fenster_ueber_schranke", devs)
    # Ohne entry_price: Schluss/Schluss (kein Raten).
    _, devs, rec = classify({"ticker": "ARCT", "date": "01.09.2026", "entry_past_return_5d": 5.12}, ARCT)
    check("ohne entry_price → Schluss/Schluss-Definition", rec.get("_epr_def") == "schluss" and not devs, rec)


def test_paths_and_s16():
    print("3 Schreibpfade + S16")
    manifest = json.loads((ROOT / "backfill_entry_past_return_5d_manifest.json").read_text())
    md = [datetime.strptime(r["date"], "%d.%m.%Y").date() for r in manifest]
    check("Backfill-Manifest liegt komplett vor EPR_LIVE_FROM", max(md) < tc.EPR_LIVE_FROM, max(md))
    mset = {(r["ticker"], r["date"]) for r in manifest}
    live = [tc._dmy(e["date"]) for e in tc._read_jsonl(ROOT / tc.config.MATURED_EXPORT_FILE)
            if e.get("entry_past_return_5d") is not None and (e["ticker"], e["date"]) not in mset]
    check("alle Nicht-Manifest-Werte ab EPR_LIVE_FROM", live and min(live) >= tc.EPR_LIVE_FROM, min(live))
    check("Backfill-Datum → Schluss/Schluss",
          tc.recompute_backtest({"ticker": "X", "date": "10.07.2026", "entry_price": 9.0},
                                AMCX, None, None, FC, TODAY).get("_epr_def") in (None, "schluss"))
    known = tc.load_known(ROOT / tc.KNOWN_FILE)
    check("AMCX nicht mehr in der Liste geprüfter Abweichungen",
          not any(e["ticker"] == "AMCX" for e in known), known)
    devs = []
    for t, d, ep, alt, s, _ in CASES:
        devs += classify({"ticker": t, "date": d, "entry_price": ep, "entry_past_return_5d": alt}, s)[1]
    devs += tc.apply_known([dict(x) for x in mk.REAL_8[:3]], known, TOL)
    for row in ({"ticker": "BJDX", "date": "14.07.2026", "return_10d_t1": -34.92},
                {"ticker": "BJDX", "date": "15.07.2026", "return_10d": -34.92},
                {"ticker": "BJDX", "date": "05.08.2026", "return_10d_t1": -18.32}):
        devs += classify(row, BJDX)[1]
    res, dl = mk._s16([mk._line("2026-11-14T03:20:00Z", devs)])
    check("S16 alarmiert für keinen geklärten Fall", res == [], res)
    check("keine Abweichung übrig", not [d for d in devs if d["klasse"] == "abweichung"], devs)
    a = [classify({"ticker": t, "date": d, "entry_price": ep, "entry_past_return_5d": alt}, s)
         for t, d, ep, alt, s, _ in CASES]
    b = [classify({"ticker": t, "date": d, "entry_price": ep, "entry_past_return_5d": alt}, s)
         for t, d, ep, alt, s, _ in CASES]
    check("Determinismus", a == b)


def main() -> int:
    for fn in (test_real_cases, test_errors_alarm, test_paths_and_s16):
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle entry_past_return_5d-Definitions-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
