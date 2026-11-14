#!/usr/bin/env python3
"""Tests für Schritt 2 (Plan 14.11.2026): nan_pct im Kurs-Batch, entry_price im
Wahrheits-Abgleich (S16), S17-Zusätze (Preis- und Datums-Plausibilität).
Nur synthetische Daten, kein Netz."""
from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import health_check as hc  # noqa: E402
import truth_check as tc  # noqa: E402

_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {str(detail)[:300]}"))
    if not cond:
        _fails.append(name)


def _extract_func(src: str, name: str) -> str:
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", src, re.S | re.M)
    return m.group(0) if m else ""


def test_nan_pct():
    print("nan_pct (yfinance_batch)")
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    ns: dict = {}
    exec(_extract_func(src, "_batch_nan_pct"), ns)  # noqa: S102
    f = ns["_batch_nan_pct"]
    check("74 von 78 → 94,9", f((74, 78)) == 94.9, f((74, 78)))
    check("0 von 78 → 0,0", f((0, 78)) == 0.0)
    check("None / leer / 0 Ticker → None", f(None) is None and f((0, 0)) is None and f(()) is None)
    check("Record übergibt nan_pct, bei Fehler None",
          "nan_pct=(None if _yfb_err is not None" in src
          and "_batch_nan_pct(_YF_BATCH_HALFROW_COUNT)" in src)
    check("Zählung nur bei vorhandenem Download (sonst kein falsches 0 %)",
          'if hist_batch is not None and not getattr(hist_batch, "empty", True):\n'
          '            globals()["_YF_BATCH_HALFROW_COUNT"] = (_probe_n, len(tickers))' in src)
    i_reset = src.find('globals()["_YF_BATCH_HALFROW_COUNT"] = None')
    i_dl = src.find("hist_batch = yf.download(", i_reset)
    check("Reset vor jedem Download", 0 < i_reset < i_dl < i_reset + 200, (i_reset, i_dl))


def test_halfrow_line():
    print("Digest-Zeile Halbzeilen")
    rows = [
        {"provider": "yfinance_batch", "run_phase": "postclose", "run_ts": "2026-11-13T01:00:00Z", "nan_pct": 10.0},
        {"provider": "yfinance_batch", "run_phase": "postclose", "run_ts": "2026-11-14T01:43:00Z", "nan_pct": 94.9},
        {"provider": "yfinance_batch", "run_phase": "premarket", "run_ts": "2026-11-13T12:00:00Z", "nan_pct": 0.0},
        {"provider": "yfinance_batch", "run_phase": "premarket", "run_ts": "2026-11-13T13:00:00Z", "nan_pct": None},
        {"provider": "finviz", "run_phase": "postclose", "run_ts": "2026-11-14T02:00:00Z", "nan_pct": 50.0},
    ]
    line = hc.batch_halfrow_line(rows)
    check("jüngster Postclose + Premarket", "Postclose 14.11. 01:43 UTC 94,9 %" in line
          and "Premarket 13.11. 12:00 UTC 0,0 %" in line, line)
    check("Hinweis, kein Alarm", "kein Alarm" in line)
    check("ohne Messung", "keine Messung" in hc.batch_halfrow_line([]))
    check("kaputte Eingabe → nie Exception", isinstance(hc.batch_halfrow_line([None, 3, {"x": 1}]), str))
    body, title, *_ = hc.format_digest_body([], [], n_runs=3, last_run_iso=None,
                                            digest_date="2026-11-14", halfrow_line=line)
    check("OK-Digest enthält die Zeile, Titel bleibt OK", line in body and "OK" in title, title)
    body2, *_ = hc.format_digest_body([], [], n_runs=0, last_run_iso=None,
                                      digest_date="2026-11-14", halfrow_line=line)
    check("Leer-Digest enthält die Zeile", line in body2)
    fails = [{"id": "S1", "severity": "crit", "detail": "x"}]
    body3, *_ = hc.format_digest_body(fails, [], n_runs=3, last_run_iso=None,
                                      digest_date="2026-11-14", halfrow_line=line)
    check("Fail-Digest enthält die Zeile", line in body3)
    dsrc = (ROOT / "scripts" / "health_check_digest.py").read_text(encoding="utf-8")
    check("Digest verdrahtet", "hc.batch_halfrow_line(prov_entries)" in dsrc
          and "halfrow_line=halfrow_line" in dsrc)


def _series(rows):
    return tc.Series([{"d": d, "c": c, "h": c, "l": c, "div": dv, "split": sp}
                      for d, c, dv, sp in rows])


D = date(2026, 11, 6)
FC = date(2026, 11, 13)
TODAY = date(2026, 11, 14)


def _base(extra=()):
    days = [date(2026, 10, 30), date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4),
            date(2026, 11, 5), D, date(2026, 11, 9), date(2026, 11, 10)]
    rows = [(d, 10.0 + i * 0.1, 0.0, 0.0) for i, d in enumerate(days)]
    return rows + list(extra)


def _cmp(row, s):
    rec = tc.recompute_backtest(row, s, None, None, FC, TODAY)
    return tc.compare_row("export", row, rec, {row["ticker"]: s}, config.TRUTH_CHECK_TOLERANCE_PP)


def test_truth_entry_price():
    print("Wahrheits-Abgleich entry_price")
    s = _series(_base())
    close_d = 10.5
    ok_row = {"ticker": "AAA", "date": "06.11.2026", "entry_price": close_d}
    n, devs, md = _cmp(ok_row, s)
    check("gleich → keine Abweichung", n >= 1 and not [d for d in devs if d["feld"] == "entry_price"], devs)
    _, devs, md = _cmp(dict(ok_row, entry_price=10.501), s)
    check("0,0095 % → innerhalb 0,02 %", not [d for d in devs if d["feld"] == "entry_price"], devs)
    _, devs, md = _cmp(dict(ok_row, entry_price=10.4), s)
    ep = [d for d in devs if d["feld"] == "entry_price"]
    check("Vortagskurs (Datumsverschiebung) → abweichung", ep and ep[0]["klasse"] == "abweichung"
          and ep[0]["abw_pct"] > 0.9, ep)
    check("max_abs_delta enthält entry_price nicht (pp-Einheit)", md is None, md)
    old = {"ticker": "AAA", "date": "04.11.2026", "entry_price": 1.0}
    _, devs, _ = _cmp(old, s)
    check("Einstieg vor TRUTH_CHECK_ENTRY_PRICE_FROM → nicht geprüft",
          not [d for d in devs if d["feld"] == "entry_price"], devs)
    # Reverse-Split 1:4 nach D: bereinigte Kurse ×4 vor dem Split.
    adj = [(d, c * 4.0, dv, sp) for d, c, dv, sp in _base()]
    adj.append((date(2026, 11, 12), 44.0, 0.0, 0.25))
    s_sp = _series(adj)
    _, devs, _ = _cmp(dict(ok_row, ticker="SPL"), s_sp)
    check("Split nach D → über Split-Faktor zurückgerechnet, keine Abweichung",
          not [d for d in devs if d["feld"] == "entry_price"], devs)
    # Dividende nach D: bereinigter Schluss D kleiner als Rohkurs.
    dv = [(d, c * 0.98 if d <= D else c, 0.0, 0.0) for d, c, _, _ in _base()]
    dv.append((date(2026, 11, 12), 11.0, 0.3, 0.0))
    s_dv = _series(dv)
    _, devs, _ = _cmp(dict(ok_row, ticker="DIV"), s_dv)
    ep = [d for d in devs if d["feld"] == "entry_price"]
    check("Dividende nach D → neu_adjustiert, ohne pp-abs_delta",
          ep and ep[0]["klasse"] == "neu_adjustiert" and "abs_delta" not in ep[0]
          and "abw_pct" in ep[0], ep)
    _, devs, _ = _cmp(dict(ok_row, ticker="SPL", entry_price=11.0), s_sp)
    ep = [d for d in devs if d["feld"] == "entry_price"]
    check("Split nach D + echte Abweichung → abweichung, regel split_nach_d",
          ep and ep[0]["klasse"] == "abweichung" and ep[0].get("regel") == "split_nach_d", ep)
    known = [{"datei": "export", "ticker": "AAA", "date": "06.11.2026", "feld": "entry_price",
              "alt": 10.4, "vergleich": 10.5}]
    dev = {"datei": "export", "ticker": "AAA", "date": "06.11.2026", "feld": "entry_price",
           "alt": 10.4, "neu": 10.501, "klasse": "abweichung"}
    check("apply_known: entry_price relativ (0,01 % neben Vergleich) → bekannt",
          tc.apply_known([dev], [dict(known[0], verweis="x")], 0.02)[0]["klasse"] == "bekannt")
    check("apply_known: entry_price 0,1 % neben Vergleich → bleibt Alarm",
          tc.apply_known([dict(dev, neu=10.52)], [dict(known[0], verweis="x")], 0.02)[0]["klasse"]
          == "abweichung")
    rec = tc.recompute_backtest(dict(ok_row, date="13.11.2026"), s, None, None, date(2026, 11, 10), TODAY)
    check("D nach letzter endgültiger Zeile → nicht nachgerechnet", "entry_price" not in rec, rec)


def _w(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_s17_extra():
    print("S17-Zusätze")
    bars = [{"h": 10.0 + i, "l": 9.0 + i} for i in range(11)]
    op = [
        {"ticker": "A", "date": "06.11.2026", "close_d": 10.0, "bars": bars},
        {"ticker": "B", "date": "06.11.2026", "close_d": 10.0, "bars": bars},
        {"ticker": "C", "date": "06.11.2026", "close_d": 10.0, "bars": bars, "dividende_im_fenster": True},
        {"ticker": "D", "date": "02.10.2026", "close_d": 10.0, "bars": bars},
    ]
    ex = [
        {"ticker": "A", "date": "06.11.2026", "entry_price": 10.0},
        {"ticker": "B", "date": "06.11.2026", "entry_price": 9.5},
        {"ticker": "C", "date": "06.11.2026", "entry_price": 9.5},
        {"ticker": "D", "date": "02.10.2026", "entry_price": 9.5},
        {"ticker": "E", "date": "07.11.2026", "entry_price": 5.0},   # Samstag, neu
        {"ticker": "F", "date": "26.11.2026", "entry_price": 5.0},   # Thanksgiving
        {"ticker": "G", "date": "04.10.2026", "entry_price": 5.0},   # Sonntag, alt
    ]
    with tempfile.TemporaryDirectory() as td:
        pe, po = pathlib.Path(td) / "e.jsonl", pathlib.Path(td) / "o.jsonl"
        _w(pe, ex)
        _w(po, op)
        c = hc.s17_rolling_window_counts(str(pe), str(po))
        fails = hc.evaluate_s17_rolling_window(str(pe), str(po))
        _w(pe, ex[:1] + ex[3:4] + ex[6:])
        fails_old = hc.evaluate_s17_rolling_window(str(pe), str(po))
    check("Preis: geprüft 4, neu 1, alt 1, mit Kapitalmaßnahme 1",
          (c["preis_geprueft"], c["preis_neu"], c["preis_alt"], c["preis_aktion"]) == (4, 1, 1, 1), c)
    hol = "2026-11-26" in config.US_MARKET_HOLIDAYS
    check("Datum: Samstag + Feiertag neu, Sonntag alt",
          c["kein_handelstag_neu"] == (2 if hol else 1) and c["kein_handelstag_alt"] == 1, c)
    pl = [f for f in fails if "Plausibilität" in f["detail"]]
    check("warn bei neuen Funden, nur Zählung", len(pl) == 1 and pl[0]["severity"] == "warn"
          and "nur Zählung" in pl[0]["detail"], fails)
    check("nur Altbestand → kein warn", not [f for f in fails_old if "Plausibilität" in f["detail"]], fails_old)
    check("Ausgabe ohne Ticker", not any(t in pl[0]["detail"] for t in ("A ", "B ", "\"B\"")))


def main() -> int:
    for fn in (test_nan_pct, test_halfrow_line, test_truth_entry_price, test_s17_extra):
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle Schritt-2-Plausibilitäts-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
