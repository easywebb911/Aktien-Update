#!/usr/bin/env python3
"""Mock-Test: [halfrow_probe] — reine Log-Probe (02.11.2026).

Deterministisch, ohne pandas/Netz (Fake-DataFrame), CI-tauglich
(stdlib + jinja2 + pyyaml, Drittlibs gestubbt).

  01 künstliche halbe Zeile → genau eine Probe-Zeile, Felder korrekt
  02 fehlende/NaN-Felder → "None", nie 0 (echte 0 bleibt 0.0)
  03 keine halbe Zeile → keine Probe-Zeile, Zähler 0
  04 Begrenzung auf max_lines, Zähler zählt alle
  05 Probe ist rein lesend (Eingaben unverändert) und im Lauf nur stdout
     (Aufruf in try/except, keine Zuweisung an results/Dateien)
"""
from __future__ import annotations

import copy
import math
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _install_stubs() -> None:
    if "yfinance" not in sys.modules:
        yf = types.ModuleType("yfinance")
        yf.download = lambda *a, **k: None
        yf.Ticker = lambda *a, **k: None
        sys.modules["yfinance"] = yf
    if "requests" not in sys.modules:
        rq = types.ModuleType("requests")
        rq.Session = lambda *a, **k: types.SimpleNamespace(
            headers=types.SimpleNamespace(update=lambda *a, **k: None))
        rq.get = lambda *a, **k: None
        rq.exceptions = types.SimpleNamespace(RequestException=Exception)
        sys.modules["requests"] = rq
    if "bs4" not in sys.modules:
        bs4 = types.ModuleType("bs4")
        bs4.BeautifulSoup = lambda *a, **k: None
        sys.modules["bs4"] = bs4
    if "deep_translator" not in sys.modules:
        dt_mod = types.ModuleType("deep_translator")
        dt_mod.GoogleTranslator = lambda *a, **k: types.SimpleNamespace(
            translate=lambda s: s)
        sys.modules["deep_translator"] = dt_mod
    if "watchlist" not in sys.modules:
        wl = types.ModuleType("watchlist")
        wl.WATCHLIST = []
        sys.modules["watchlist"] = wl


_install_stubs()
import generate_report as g  # noqa: E402

_fails: list[str] = []


def _check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        _fails.append(name)


class _Col:
    def __init__(self, vals):
        self._v = vals

    @property
    def iloc(self):
        return self._v


class _DF:
    def __init__(self, dates, cols):
        self.index = dates
        self._cols = cols
        self.columns = list(cols)
        self.empty = len(dates) == 0

    def __getitem__(self, k):
        return _Col(self._cols[k])


class _Batch:
    empty = False

    def __init__(self, per):
        self._p = per

    def __getitem__(self, t):
        return self._p[t]


NAN = float("nan")


def _df(close_last, vol_last=1_000_000.0):
    return _DF(["2026-10-29 00:00:00", "2026-10-30 00:00:00"],
               {"Close": [10.0, close_last], "Volume": [900_000.0, vol_last],
                "High": [10.5, NAN], "Low": [9.5, NAN], "Open": [10.0, 10.2]})


INFO = {"regularMarketPrice": 10.4, "regularMarketPreviousClose": 10.0,
        "regularMarketOpen": 10.2, "regularMarketDayHigh": 10.9,
        "regularMarketDayLow": 10.1, "regularMarketVolume": 1_234_567,
        "regularMarketTime": 1761854400}   # 2025-10-30T20:00:00Z (beliebig, fix)


def test_01_halfrow_line():
    batch = _Batch({"AAA": _df(NAN), "BBB": _df(11.0)})
    lines, n = g._halfrow_probe_lines(batch, ["AAA", "BBB"], {"AAA": INFO, "BBB": INFO})
    _check("01 genau eine Probe-Zeile", len(lines) == 1 and n == 1, (lines, n))
    ln = lines[0] if lines else ""
    print("     Beispiel:", ln)
    for frag in ("[halfrow_probe] ticker=AAA", "row_date=2026-10-30",
                 "row_volume=1000000.0", "regularMarketPrice=10.4",
                 "regularMarketPreviousClose=10.0", "regularMarketOpen=10.2",
                 "regularMarketDayHigh=10.9", "regularMarketDayLow=10.1",
                 "regularMarketVolume=1234567.0",
                 "regularMarketTime_utc=2025-10-30T20:00:00+00:00",
                 "regularMarketTime_et_date=2025-10-30", "postMarketPrice=None"):
        _check(f"01 enthält {frag}", frag in ln, ln)


def test_02_none_never_zero():
    info = {"regularMarketPrice": NAN, "regularMarketOpen": None,
            "regularMarketVolume": 0}
    lines, _ = g._halfrow_probe_lines(_Batch({"AAA": _df(NAN, vol_last=NAN)}),
                                      ["AAA", "X"], {"AAA": info})
    ln = lines[0]
    _check("02 NaN-Preis → None", "regularMarketPrice=None" in ln, ln)
    _check("02 fehlendes Feld → None", "regularMarketDayHigh=None" in ln, ln)
    _check("02 None-Feld → None", "regularMarketOpen=None" in ln, ln)
    _check("02 NaN-Volumen der Zeile → None", "row_volume=None" in ln, ln)
    _check("02 Zeit fehlt → None", "regularMarketTime_utc=None" in ln, ln)
    _check("02 echte 0 bleibt 0.0", "regularMarketVolume=0.0" in ln, ln)
    _check("02 nirgends '=0 '", "=0 " not in ln + " ", ln)
    lines2, _ = g._halfrow_probe_lines(_Batch({"AAA": _df(NAN)}), ["AAA", "X"], {})
    _check("02 kein .info → alle Felder None",
           all(f"{k}=None" in lines2[0] for k in g._HALFROW_PROBE_FIELDS), lines2)


def test_03_no_halfrow():
    lines, n = g._halfrow_probe_lines(_Batch({"AAA": _df(11.0), "BBB": _df(12.0)}),
                                      ["AAA", "BBB"], {"AAA": INFO})
    _check("03 keine Probe-Zeile", lines == [] and n == 0, (lines, n))
    lines, n = g._halfrow_probe_lines(None, ["AAA"], {})
    _check("03 kein Batch → leer", lines == [] and n == 0)

    class _NpLike:  # verhält sich wie ein numpy-Skalar (int64): nur __float__
        def __init__(self, v):
            self.v = v

        def __float__(self):
            return float(self.v)

    lines, n = g._halfrow_probe_lines(_Batch({"AAA": _df(_NpLike(11))}), ["AAA", "B"], {})
    _check("03 numpy-artiger Close (int64) gilt als voll → keine Zeile", n == 0, (lines, n))
    lines, _ = g._halfrow_probe_lines(_Batch({"AAA": _df(NAN, vol_last=_NpLike(6))}), ["AAA", "B"],
                                      {"AAA": {"regularMarketTime": _NpLike(1761854400)}})
    _check("03 numpy-artiges Volumen/Zeit wird formatiert",
           "row_volume=6.0" in lines[0] and "regularMarketTime_et_date=2025-10-30" in lines[0], lines)


def test_04_limit():
    tick = [f"T{i}" for i in range(7)]
    batch = _Batch({t: _df(NAN) for t in tick})
    lines, n = g._halfrow_probe_lines(batch, tick, {}, max_lines=3)
    _check("04 max 3 Zeilen, Zähler 7", len(lines) == 3 and n == 7, (len(lines), n))
    _check("04 Standard-Limit 100", g._HALFROW_PROBE_MAX_LINES == 100)


def test_05_read_only_and_stdout_only():
    info_map = {"AAA": dict(INFO)}
    before = copy.deepcopy(info_map)
    g._halfrow_probe_lines(_Batch({"AAA": _df(NAN)}), ["AAA", "B"], info_map)
    _check("05 info_map unverändert", info_map == before)
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    i = src.index("# [halfrow_probe] REINE LOG-PROBE")
    j = src.index("def _detect_recent_squeeze", i)
    block = src[i:j]
    _check("05 Aufruf in try/except", "try:" in block and "except Exception" in block)
    _check("05 nur print, keine Zuweisung an results/info_map/Dateien",
           "results[" not in block and "info_map[" not in block and "open(" not in block
           and "record_" not in block, block)


def main() -> int:
    for t in (test_01_halfrow_line, test_02_none_never_zero, test_03_no_halfrow,
              test_04_limit, test_05_read_only_and_stdout_only):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            _check(f"{t.__name__} ohne Exception", False, f"{type(exc).__name__}: {exc}")
    print()
    if _fails:
        print(f"{len(_fails)} FAIL")
        return 1
    print("Alle halfrow_probe-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
