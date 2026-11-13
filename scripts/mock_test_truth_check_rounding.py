#!/usr/bin/env python3
"""Tests Rundungsschranke nach Kapitalmaßnahme im Wahrheits-Abgleich (Easy-
Entscheid 13.11.2026, BJDX-Klasse). Ohne Netz.

Kursdaten = ECHTE Yahoo-Werte BJDX aus dem Beleg-Lauf 43488284245 (13.11.2026
19:02 UTC, Wegwerf-Probe #691, inzwischen entfernt): float32-Werte, Reverse-Split 1:4 am
03.11.2026 (``Stock Splits`` 0.25), davor 29.01.2026.

 1  Die drei echten BJDX-Fälle vom 13.11. → neu_adjustiert (regel
    rundung_nach_aktion) mit Schranke aus der Formel.
 2  Gleiche Aktion, |Δ| über der Schranke → abweichung (voller Alarm).
 3  Keine Aktion in der Reihe → abweichung.
 4  Schranken-Formel nachgerechnet (k = 3, F = 4, h = 0,002).
 5  Nur Kursverhältnis-Felder; _vs_spy / max / vix nie.
 6  Echte 8 Fälle 13.11.: mit Liste + Regel bleibt nur ARCT als Abweichung (S16).
 7  Determinismus.
"""
from __future__ import annotations

import json
import pathlib
import struct
import sys
import tempfile
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402
import truth_check as tc  # noqa: E402

_fails: list[str] = []
TOL = float(tc.config.TRUTH_CHECK_TOLERANCE_PP)


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


def f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


# Schlusskurse BJDX (bereinigt, Stand 13.11.2026) aus dem Beleg-Lauf.
BJDX = {
    "2026-07-01": 4.8, "2026-07-02": 4.56, "2026-07-06": 4.64, "2026-07-07": 5.8, "2026-07-08": 5.36,
    "2026-07-09": 5.6, "2026-07-10": 5.8, "2026-07-13": 4.88, "2026-07-14": 5.0, "2026-07-15": 5.4,
    "2026-07-16": 5.2, "2026-07-17": 5.8, "2026-07-20": 4.84, "2026-07-21": 4.64, "2026-07-22": 4.6,
    "2026-07-23": 4.56, "2026-07-24": 4.12, "2026-07-27": 4.4, "2026-07-28": 4.0, "2026-07-29": 3.516,
    "2026-07-30": 3.716, "2026-07-31": 3.44, "2026-08-03": 3.768, "2026-08-04": 4.0, "2026-08-05": 4.96,
    "2026-08-06": 4.6, "2026-08-07": 4.28, "2026-08-10": 3.948, "2026-08-11": 4.28, "2026-08-12": 4.2,
    "2026-08-13": 4.24, "2026-08-14": 4.2, "2026-08-17": 4.08, "2026-08-18": 3.88, "2026-08-19": 3.84,
    "2026-08-20": 3.756, "2026-08-21": 3.644, "2026-08-24": 3.6, "2026-08-25": 3.664,
}
CASES = [  # die drei echten S16-Fälle vom 13.11.2026
    {"ticker": "BJDX", "date": "14.07.2026", "return_10d_t1": -34.92},
    {"ticker": "BJDX", "date": "15.07.2026", "return_10d": -34.92},
    {"ticker": "BJDX", "date": "05.08.2026", "return_10d_t1": -18.32},
]


def bjdx_series(with_split=True):
    rows = [{"d": date.fromisoformat(d), "c": f32(c), "h": f32(c), "l": f32(c), "div": 0.0, "split": 0.0}
            for d, c in BJDX.items()]
    rows.append({"d": date(2026, 11, 3), "c": f32(1.0), "h": f32(1.0), "l": f32(1.0), "div": 0.0,
                 "split": 0.25 if with_split else 0.0})
    return tc.Series(rows)


FC, TODAY = date(2026, 11, 12), date(2026, 11, 13)


def classify(row, s):
    rec = tc.recompute_backtest(row, s, None, None, FC, TODAY)
    return tc.compare_row("export", row, rec, {"BJDX": s}, TOL)[1]


def test_real_bjdx():
    print("1 Echte BJDX-Fälle → neu_adjustiert")
    s = bjdx_series()
    for row in CASES:
        devs = classify(dict(row), s)
        ok = len(devs) == 1 and devs[0]["klasse"] == "neu_adjustiert" \
            and devs[0].get("regel") == "rundung_nach_aktion"
        check(f"{row['date']} → neu_adjustiert (Schranke {devs[0].get('schranke') if devs else None})", ok, devs)
    print("2 gleiche Aktion, Δ über Schranke → Alarm")
    for row in CASES:
        r = dict(row)
        f = [k for k in r if k.startswith("return_")][0]
        r[f] = round(r[f] - 0.15, 2)
        devs = classify(r, s)
        check(f"{row['date']} {f} −0,15 → abweichung", devs and devs[0]["klasse"] == "abweichung", devs)
    print("3 keine Aktion → Alarm")
    s0 = bjdx_series(with_split=False)
    for row in CASES:
        devs = classify(dict(row), s0)
        check(f"{row['date']} ohne Split → abweichung", devs and devs[0]["klasse"] == "abweichung", devs)
    print("7 Determinismus")
    check("gleiche Kursdaten → gleiche Klassierung",
          [classify(dict(r), bjdx_series()) for r in CASES] == [classify(dict(r), bjdx_series()) for r in CASES])


def test_formula():
    print("4 Schranke nachgerechnet")
    s = bjdx_series()
    span = (date(2026, 7, 14), date(2026, 7, 29))
    b = tc.rounding_bound(s, "return_10d_t1", span)
    a_, b_ = f32(5.4), f32(3.516)
    exp = 100 * (b_ / a_) * (0.002 / a_ + 0.002 / b_) + 0.01      # k=3, F=4 → h=0,002
    check("k = 3 (Rohkurs 0,879), F = 4, h = 0,002", abs(b - exp) < 1e-9, (b, exp))
    check("Schranke ≈ 0,071 pp", abs(b - 0.0711) < 0.001, b)
    check("_net kleiner als brutto", tc.rounding_bound(s, "return_10d_net", (date(2026, 7, 15), date(2026, 7, 29)))
          < tc.rounding_bound(s, "return_10d", (date(2026, 7, 15), date(2026, 7, 29))))
    print("5 nur Kursverhältnis-Felder")
    for f in ("return_10d_vs_spy", "max_gain_pct", "max_drawdown_pct", "vix_level", "market_regime"):
        check(f"{f} → keine Regel", tc.rounding_bound(s, f, span) is None)
    s_pre = bjdx_series(False)
    s_pre.rows[0]["split"] = 0.25           # Aktion am 01.07., vor dem Fenster 14.07.–29.07.
    check("Aktion VOR Fensterbeginn zählt nicht", tc.rounding_bound(s_pre, "return_10d", span) is None)
    check("ohne Aktion keine Regel", tc.rounding_bound(bjdx_series(False), "return_10d", span) is None)


def test_real_8():
    print("6 Echte 8 Fälle 13.11. (Liste + Regel)")
    import mock_test_truth_check_known as mk  # echte Fälle + Hilfen
    s = bjdx_series()
    known = mk._known()
    cls = tc.apply_known([dict(d) for d in mk.REAL_8], known, TOL)
    out = []
    for d in cls:
        if d["ticker"] == "BJDX" and d["klasse"] == "abweichung":
            row = next(dict(r) for r in CASES if r["date"] == d["date"])
            d = classify(row, s)[0]
        out.append(d)
    rest = [(d["ticker"], d["date"]) for d in out if d["klasse"] == "abweichung"]
    check("nur ARCT bleibt Abweichung", rest == [("ARCT", "01.09.2026")], rest)
    check("BJDX×3 neu_adjustiert", sum(d["klasse"] == "neu_adjustiert" for d in out) == 3)
    res, _ = mk._s16([mk._line("2026-11-13T03:20:51Z", out)])
    det = res[0]["detail"] if res else ""
    check("S16 alarmiert nur noch für ARCT", res and "ARCT" in det and "BJDX" not in det
          and "GRPN" not in det and "AMCX" not in det, res)


def main() -> int:
    for fn in (test_real_bjdx, test_formula, test_real_8):
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle truth_check-Rundungsschranken-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
