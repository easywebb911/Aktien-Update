"""Mock-Test: Backtest-Renditen nur aus FINALEN Schlusskursen (Fix 03.11.2026).

Hintergrund (Rendite-Diagnose, Probe #645): ``update_backtest_returns`` füllte
``return_Nd`` sobald die Tageszeile T+N existierte — meist während der
US-Börsenzeit, also mit dem laufenden Intraday-Kurs — und überschrieb nie.
Fix: eine Tageszeile zählt erst, wenn ihr Datum ``<=``
``trading_date.last_final_close_date(now)`` ist (Folgetag oder ab 16:20 ET).

Fester Zeitpunkt: ``ki_agent.datetime.now`` wird auf ein festes „jetzt"
gepatcht (so läuft derselbe Test auch gegen den alten Code — Gegenprobe:
auf ``origin/main`` vor dem Fix scheitern 01/02/05/07/08/09/10/11).

  01 Winter (EST): T+3 während der Sitzung (13:00 ET)      → leer
  02 Winter: T+3 um 16:15 ET (vor dem Puffer)             → leer
  03 Winter: Folgetag 07:05 ET (seit 13.11.2026)           → gefüllt = Schluss T+3
  04 Winter: Folgetag T+4 morgens                          → gefüllt
  05 Winter: 20:25 UTC = 15:25 EST (Sommer-UTC-Grenze wäre schon vorbei) → leer
  06 Sommer (EDT): Folgetag 07:05 EDT                      → gefüllt
  07 Sommer: 20:15 UTC = 16:15 EDT                         → leer
  08 Feiertag (Thanksgiving) + Wochenende dazwischen: T+3 am Di
     während der Sitzung → leer; am Mi danach → Schluss des Di (nicht Mo)
  09 entry_price_t1 und return_Nd_t1 folgen derselben Regel
  10 SPY-Differenz (_vs_spy) nur mit finalem SPY-Schluss
  11 now_utc ist als Argument injizierbar (Determinismus)
  12 trading_date.last_final_close_date: Grenzen Sommer/Winter, naiv = UTC
  13 _trading_days_elapsed unverändert (zählt heute weiter mit)
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _install_stubs():
    if "pandas" not in sys.modules:
        sys.modules["pandas"] = types.ModuleType("pandas")
    if "requests" not in sys.modules:
        sys.modules["requests"] = types.ModuleType("requests")
    if "yfinance" not in sys.modules:
        yf_stub = types.ModuleType("yfinance")
        yf_stub.download = lambda *a, **k: None
        yf_stub.Ticker = lambda *a, **k: None
        sys.modules["yfinance"] = yf_stub


_install_stubs()
import ki_agent  # noqa: E402
import trading_date  # noqa: E402

UTC = _dt.timezone.utc
_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        _fails.append(name)


# ── Fake-pandas (nur das genutzte Interface) ────────────────────────────────
class _FakeTS:
    def __init__(self, d):
        self._d = d

    def date(self):
        return self._d


class _FakeIloc:
    def __init__(self, vals):
        self._vals = vals

    def __getitem__(self, i):
        return self._vals[i]


class _FakeCloses:
    def __init__(self, dates, vals):
        self.index = [_FakeTS(d) for d in dates]
        self._vals = vals

    @property
    def iloc(self):
        return _FakeIloc(self._vals)

    def __len__(self):
        return len(self._vals)

    def dropna(self):
        return self

    def squeeze(self):
        return self


class _FakeDF:
    empty = False

    def __init__(self, dates, vals):
        self._closes = _FakeCloses(dates, vals)

    def __contains__(self, key):
        return key == "Close"

    def __getitem__(self, key):
        if key == "Close":
            return self._closes
        raise KeyError(key)


def _run(entries, dates, vals, now, *, spy_vals=None, inject=False):
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(entries, tmp)
    tmp.close()
    tick_df = _FakeDF(dates, vals)
    spy_df = _FakeDF(dates, spy_vals) if spy_vals is not None else None

    class _FakeYf:
        def download(self, tickers, *a, **k):
            if tickers == "SPY":
                if spy_df is None:
                    raise RuntimeError("kein SPY im Test")
                return spy_df
            return tick_df

    orig = (ki_agent.BACKTEST_FILE, ki_agent.yf, ki_agent.BACKTEST_ENABLED, ki_agent.datetime)

    class _FixedDT:
        @staticmethod
        def now(tz=None):
            return now

        @staticmethod
        def strptime(s, fmt):
            return _dt.datetime.strptime(s, fmt)

    try:
        ki_agent.BACKTEST_FILE = tmp.name
        ki_agent.yf = _FakeYf()
        ki_agent.BACKTEST_ENABLED = True
        if inject:
            ki_agent.update_backtest_returns(now_utc=now)
        else:
            ki_agent.datetime = _FixedDT
            ki_agent.update_backtest_returns()
    finally:
        (ki_agent.BACKTEST_FILE, ki_agent.yf, ki_agent.BACKTEST_ENABLED, ki_agent.datetime) = orig
    out = json.loads(pathlib.Path(tmp.name).read_text(encoding="utf-8"))
    pathlib.Path(tmp.name).unlink()
    return out[0]


def _entry(date):
    return {"date": date, "ticker": "TICK", "score": 80.0, "entry_price": 10.0,
            "entry_price_t1": None,
            "return_3d": None, "return_5d": None, "return_10d": None,
            "return_3d_t1": None, "return_5d_t1": None, "return_10d_t1": None}


def _ret(c, base):
    return round((c / base - 1) * 100, 2)


# Winter: Entry Mo 02.11.2026 (EST, UTC-5). Zeilen Mo–Fr; T+3 = Do 05.11.
W_DATES = [_dt.date(2026, 11, d) for d in (2, 3, 4, 5, 6)]
W_VALS = [10.0, 10.5, 11.0, 12.0, 12.5]   # Zeile 05.11 = 12.0 (Intraday bis 16:20 ET)
# Sommer: Entry Mo 06.07.2026 (EDT, UTC-4). T+3 = Do 09.07.
S_DATES = [_dt.date(2026, 7, d) for d in (6, 7, 8, 9)]
S_VALS = [20.0, 21.0, 22.0, 23.0]


def _at(y, m, d, hh, mm):
    return _dt.datetime(y, m, d, hh, mm, tzinfo=UTC)


def test_winter():
    # Am 05.11. existiert die (laufende) Zeile 05.11 bereits im Download.
    e = _run([_entry("02.11.2026")], W_DATES[:4], W_VALS[:4], _at(2026, 11, 5, 18, 0))
    _check("01 Winter 13:00 ET am Zieltag → return_3d leer", e["return_3d"] is None, str(e["return_3d"]))
    e = _run([_entry("02.11.2026")], W_DATES[:4], W_VALS[:4], _at(2026, 11, 5, 21, 15))
    _check("02 Winter 16:15 ET → return_3d leer", e["return_3d"] is None, str(e["return_3d"]))
    e = _run([_entry("02.11.2026")], W_DATES[:4], W_VALS[:4], _at(2026, 11, 6, 12, 5))
    _check("03 Winter Folgetag 07:05 ET → gefüllt mit Schluss T+3 (seit 13.11.2026)",
           e["return_3d"] == _ret(12.0, 10.0), str(e["return_3d"]))
    e = _run([_entry("02.11.2026")], W_DATES, W_VALS, _at(2026, 11, 6, 13, 0))
    _check("04 Winter Folgetag morgens → gefüllt mit Schluss T+3",
           e["return_3d"] == _ret(12.0, 10.0), str(e["return_3d"]))
    e = _run([_entry("02.11.2026")], W_DATES[:4], W_VALS[:4], _at(2026, 11, 5, 20, 25))
    _check("05 Winter 20:25 UTC = 15:25 EST → leer (keine feste UTC-Grenze)",
           e["return_3d"] is None, str(e["return_3d"]))


def test_summer():
    e = _run([_entry("06.07.2026")], S_DATES, S_VALS, _at(2026, 7, 10, 11, 5))
    _check("06 Sommer Folgetag 11:05 UTC = 07:05 EDT → gefüllt",
           e["return_3d"] == _ret(23.0, 20.0), str(e["return_3d"]))
    e = _run([_entry("06.07.2026")], S_DATES, S_VALS, _at(2026, 7, 9, 20, 15))
    _check("07 Sommer 20:15 UTC = 16:15 EDT → leer", e["return_3d"] is None, str(e["return_3d"]))


def test_holiday_weekend():
    # Entry Mi 25.11.2026; Do 26.11. Thanksgiving (keine Zeile); Fr 27.11.;
    # Wochenende; Mo 30.11.; Di 01.12. = T+3 (dritte Zeile nach Entry).
    dates = [_dt.date(2026, 11, 25), _dt.date(2026, 11, 27), _dt.date(2026, 11, 30),
             _dt.date(2026, 12, 1)]
    vals = [10.0, 10.2, 10.4, 13.0]
    e = _run([_entry("25.11.2026")], dates, vals, _at(2026, 12, 1, 15, 0))
    _check("08 Feiertag+Wochenende: T+3 (Di) 10:00 ET → leer", e["return_3d"] is None, str(e["return_3d"]))
    e = _run([_entry("25.11.2026")], dates, vals, _at(2026, 12, 2, 12, 0))
    _check("08 am Folgetag → Schluss des Di (nicht Mo)",
           e["return_3d"] == _ret(13.0, 10.0), str(e["return_3d"]))


def test_t1_fields():
    # T+1 = Di 03.11. Am Di 13:00 ET: entry_price_t1 leer; am Mi: gefüllt.
    e = _run([_entry("02.11.2026")], W_DATES[:2], W_VALS[:2], _at(2026, 11, 3, 18, 0))
    _check("09 entry_price_t1 während der Sitzung T+1 → leer", e["entry_price_t1"] is None,
           str(e["entry_price_t1"]))
    e = _run([_entry("02.11.2026")], W_DATES[:3], W_VALS[:3], _at(2026, 11, 4, 13, 0))
    _check("09 entry_price_t1 am Folgetag → Schluss T+1", e["entry_price_t1"] == 10.5,
           str(e["entry_price_t1"]))
    # return_3d_t1 = Close[T+4] / Close[T+1]; T+4 = Fr 06.11. während der Sitzung.
    e = _run([_entry("02.11.2026")], W_DATES, W_VALS, _at(2026, 11, 6, 17, 0))
    _check("09 return_3d_t1 während der Sitzung T+4 → leer", e["return_3d_t1"] is None,
           str(e["return_3d_t1"]))
    _check("09 return_3d (T+3 Vortag) im selben Lauf gefüllt", e["return_3d"] == _ret(12.0, 10.0),
           str(e["return_3d"]))


def test_spy():
    spy = [100.0, 100.0, 100.0, 101.0]
    e = _run([_entry("02.11.2026")], W_DATES[:4], W_VALS[:4], _at(2026, 11, 6, 12, 5), spy_vals=spy)
    _check("10 _vs_spy mit endgültigem SPY-Schluss gefüllt",
           e.get("return_3d_vs_spy") == round(_ret(12.0, 10.0) - 1.0, 2), str(e.get("return_3d_vs_spy")))
    # Ticker-Zeile 05.11 final, SPY-Zeile aber nicht final → kann nicht vorkommen
    # (gleiches Datum, gleiche Grenze); stattdessen: während der Sitzung beides leer.
    e = _run([_entry("02.11.2026")], W_DATES[:4], W_VALS[:4], _at(2026, 11, 5, 18, 0), spy_vals=spy)
    _check("10 während der Sitzung: return_3d und _vs_spy leer",
           e["return_3d"] is None and e.get("return_3d_vs_spy") is None)


def test_inject():
    e = _run([_entry("02.11.2026")], W_DATES[:4], W_VALS[:4], _at(2026, 11, 5, 18, 0), inject=True)
    _check("11 now_utc injiziert: Sitzung → leer", e["return_3d"] is None)
    e = _run([_entry("02.11.2026")], W_DATES[:4], W_VALS[:4], _at(2026, 11, 6, 12, 5), inject=True)
    _check("11 now_utc injiziert: Folgetag 07:05 ET → gefüllt", e["return_3d"] == _ret(12.0, 10.0))


def test_helper():
    f = trading_date.last_final_close_date
    _check("12 Winter 21:19 UTC (16:19 EST) → Vortag", f(_at(2026, 11, 5, 21, 19)) == _dt.date(2026, 11, 4))
    _check("12 Winter 21:20 UTC (16:20 EST) → heute", f(_at(2026, 11, 5, 21, 20)) == _dt.date(2026, 11, 5))
    _check("12 Sommer 20:20 UTC (16:20 EDT) → heute", f(_at(2026, 7, 9, 20, 20)) == _dt.date(2026, 7, 9))
    _check("12 Sommer 20:19 UTC → Vortag", f(_at(2026, 7, 9, 20, 19)) == _dt.date(2026, 7, 8))
    _check("12 nach Mitternacht UTC (ET noch Vortag, nach Schluss) → ET-Tag",
           f(_at(2026, 11, 6, 2, 0)) == _dt.date(2026, 11, 5))
    _check("12 naiv = UTC", f(_dt.datetime(2026, 11, 5, 21, 20)) == _dt.date(2026, 11, 5))
    _check("12 Puffer-Grenze aus trading_date",
           trading_date.US_CLOSE_FINAL_ET == _dt.time(16, 20)
           and trading_date.US_SESSION_CLOSE_ET == _dt.time(16, 0))


def test_elapsed_unchanged():
    _check("13 _trading_days_elapsed zählt heute weiter mit",
           ki_agent._trading_days_elapsed("02.11.2026", _dt.date(2026, 11, 5)) == 3)


def main() -> int:
    for t in (test_winter, test_summer, test_holiday_weekend, test_t1_fields, test_spy,
              test_inject, test_helper, test_elapsed_unchanged):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            _check(f"{t.__name__} ohne Exception", False, f"{type(exc).__name__}: {exc}")
    print()
    if _fails:
        print(f"{len(_fails)} FAIL")
        return 1
    print("Alle backtest_returns_final_close-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
