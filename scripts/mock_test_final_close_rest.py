"""Mock-Test: „nur finale Schlusskurse" an den drei Rest-Stellen (03.11.2026).

Gleiche Regel wie #647 (update_backtest_returns): eine Tageszeile zählt nur,
wenn ihr Datum <= trading_date.last_final_close_date(jetzt) ist (Folgetag
oder ab 16:20 ET). Synthetische Kurse, fester Zeitpunkt, kein Netz.

  A  backtest_history._final_window (max_gain_pct/max_drawdown_pct-Fenster)
     A1 laufender Tag (Sitzung, Winter) nicht im Fenster
     A2 nach 16:20 ET drin; Folgetag drin
     A3 Sommerzeit-Grenze 20:19/20:20 UTC; Winterzeit 21:19/21:20 UTC
     A4 Wochenende/Feiertag dazwischen: Fenster = 11 Handelstage, nicht mehr
     A5 _append_backtest_entries nutzt _final_window mit now_et (Quelle)
  B  ki_agent.update_exit_shadow_forwards
     B1 Horizont am laufenden Tag (Sitzung) → leer
     B2 16:25 ET → leer (seit 13.11.2026); Folgetag 07:05 ET → gefüllt
     B3 Sommer Folgetag 07:05 EDT gefüllt, Winter 20:25 UTC = 15:25 EST leer
     B4 Feiertag (Thanksgiving) + Wochenende dazwischen
     B5 Signal-Tag selbst nicht final → nichts gefüllt
  C  backtest_bootstrap
     C1 _final_rows schneidet die laufende Zeile ab
     C2 _process_ticker: Return am laufenden Zieltag leer, Folgetag gefüllt
     C3 RVOL-Signal nur aus finalen Zeilen (laufender Tag erzeugt kein Signal)
  D  _trading_days_elapsed unverändert; ki_agent-Signatur injizierbar
Gegenprobe: auf dem alten Code scheitern A1/A3/B1/B3/B5/C1–C3.
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
sys.path.insert(0, str(ROOT / "scripts"))


def _install_stubs():
    for name in ("pandas", "requests"):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    if "yfinance" not in sys.modules:
        yf_stub = types.ModuleType("yfinance")
        yf_stub.download = lambda *a, **k: None
        yf_stub.Ticker = lambda *a, **k: None
        sys.modules["yfinance"] = yf_stub


_install_stubs()
import trading_date  # noqa: E402
import ki_agent  # noqa: E402
import exit_shadow  # noqa: E402
import backtest_history as bh  # noqa: E402
import backtest_bootstrap as bb  # noqa: E402

UTC = _dt.timezone.utc
_fails: list[str] = []


def _check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        _fails.append(name)


def _at(y, m, d, hh, mm):
    return _dt.datetime(y, m, d, hh, mm, tzinfo=UTC)


def _days(start, n, skip=()):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5 and d not in skip:
            out.append(d)
        d += _dt.timedelta(days=1)
    return out


# ── Fake-DataFrame (nur das genutzte Interface) ─────────────────────────────
class _TS:
    def __init__(self, d): self._d = d
    def date(self): return self._d


class _Idx(list):
    @property
    def date(self):
        return [t.date() for t in self]


class _Series:
    def __init__(self, vals): self._v = list(vals)
    @property
    def iloc(self):
        s = self

        class _I:
            def __getitem__(self, k):
                if isinstance(k, slice):
                    return _Series(s._v[k])
                return s._v[k]
        return _I()
    def __len__(self): return len(self._v)
    def mean(self): return sum(self._v) / len(self._v)
    def dropna(self): return self


class _DF:
    def __init__(self, dates, cols):
        self.index = _Idx(_TS(d) for d in dates)
        self._c = cols
    @property
    def empty(self): return len(self.index) == 0
    def __len__(self): return len(self.index)
    def __contains__(self, k): return k in self._c
    def __getitem__(self, k):
        if isinstance(k, list):          # Bool-Maske
            keep = [i for i, b in enumerate(k) if b]
            return _DF([self.index[i].date() for i in keep],
                       {c: [v[i] for i in keep] for c, v in self._c.items()})
        return _Series(self._c[k])
    @property
    def iloc(self):
        s = self

        class _I:
            def __getitem__(self, k):
                return _DF([t.date() for t in s.index][k], {c: v[k] for c, v in s._c.items()})
        return _I()


# ── A: max_gain/max_drawdown-Fenster ─────────────────────────────────────────
def test_a_window():
    dates = _days(_dt.date(2026, 10, 19), 14)            # 19.10. … 05.11. (Do)
    df = _DF(dates, {"High": [1.0] * 14, "Low": [1.0] * 14})
    entry = _dt.date(2026, 10, 22)
    w = bh._final_window(df, entry, trading_date.last_final_close_date(_at(2026, 11, 5, 18, 0)))
    _check("A1 Winter 13:00 ET: laufender Tag 05.11. nicht im Fenster",
           _dt.date(2026, 11, 5) not in w.index.date and w.index.date[0] == entry, str(w.index.date))
    w = bh._final_window(df, entry, trading_date.last_final_close_date(_at(2026, 11, 5, 21, 25)))
    _check("A2 Winter 16:25 ET: 05.11. im Fenster", w.index.date[-1] == _dt.date(2026, 11, 5))
    w = bh._final_window(df, entry, trading_date.last_final_close_date(_at(2026, 11, 6, 13, 0)))
    _check("A2 Folgetag: 05.11. im Fenster", _dt.date(2026, 11, 5) in w.index.date)
    w = bh._final_window(df, entry, trading_date.last_final_close_date(_at(2026, 11, 5, 21, 19)))
    _check("A3 Winter 21:19 UTC (16:19 EST): 05.11. nicht drin", _dt.date(2026, 11, 5) not in w.index.date)
    sdates = _days(_dt.date(2026, 7, 6), 5)
    sdf = _DF(sdates, {"High": [1.0] * 5, "Low": [1.0] * 5})
    w = bh._final_window(sdf, sdates[0], trading_date.last_final_close_date(_at(2026, 7, 10, 20, 19)))
    _check("A3 Sommer 20:19 UTC (16:19 EDT): 10.07. nicht drin", _dt.date(2026, 7, 10) not in w.index.date)
    w = bh._final_window(sdf, sdates[0], trading_date.last_final_close_date(_at(2026, 7, 10, 20, 20)))
    _check("A3 Sommer 20:20 UTC (16:20 EDT): 10.07. drin", _dt.date(2026, 7, 10) in w.index.date)
    hol = _days(_dt.date(2026, 11, 20), 16, skip={_dt.date(2026, 11, 26)})
    hdf = _DF(hol, {"High": [1.0] * 16, "Low": [1.0] * 16})
    w = bh._final_window(hdf, hol[0], trading_date.last_final_close_date(_at(2026, 12, 20, 12, 0)))
    _check("A4 Feiertag/Wochenende: genau 11 Handelstage ab Entry",
           len(w) == 11 and w.index.date == hol[:11], str(w.index.date))
    src = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    _check("A5 Rolling-Block nutzt _final_window mit last_final_close_date(now_et)",
           # seit 13.11.2026 in _apply_rolling_window ausgelagert
           "_apply_rolling_window(e, df, edate, _final_cut)" in src
           and "df_since = _final_window(df, edate, final_cut)" in src
           and "_final_cut = trading_date.last_final_close_date(now_et)" in src)


# ── B: Exit-Shadow-Forwards ──────────────────────────────────────────────────
class _Closes:
    def __init__(self, pairs):
        self.index = [_TS(d) for d, _ in pairs]
        self._v = [v for _, v in pairs]
    @property
    def iloc(self):
        v = self._v

        class _I:
            def __getitem__(self, i): return v[i]
        return _I()
    def __len__(self): return len(self._v)
    def dropna(self): return self


class _CDF:
    def __init__(self, pairs): self._c = _Closes(pairs)
    def __contains__(self, k): return k == "Close"
    def __getitem__(self, k): return self._c


def _es_run(sig_date, pairs, now, inject=False):
    d = pathlib.Path(tempfile.mkdtemp())
    log = d / "exit_shadow_log.jsonl"
    log.write_text(json.dumps({"date": sig_date, "ticker": "AAA", "forward_3d": None,
                               "forward_5d": None, "forward_10d": None}) + "\n", encoding="utf-8")

    class _Yf:
        def download(self, *a, **k): return _CDF(pairs)
    orig = (exit_shadow.EXIT_SHADOW_LOG, ki_agent.yf, ki_agent.datetime)

    class _FixedDT:
        @staticmethod
        def now(tz=None): return now
        @staticmethod
        def strptime(s, f): return _dt.datetime.strptime(s, f)
    try:
        exit_shadow.EXIT_SHADOW_LOG = str(log)
        ki_agent.yf = _Yf()
        if inject:
            ki_agent.update_exit_shadow_forwards(now_utc=now)
        else:
            ki_agent.datetime = _FixedDT
            ki_agent.update_exit_shadow_forwards()
    finally:
        exit_shadow.EXIT_SHADOW_LOG, ki_agent.yf, ki_agent.datetime = orig
    return json.loads(log.read_text(encoding="utf-8").splitlines()[0])


def test_b_exit_shadow():
    dates = _days(_dt.date(2026, 11, 2), 4)                # Mo 02.11. … Do 05.11.
    pairs = list(zip(dates, [10.0, 10.5, 11.0, 12.0]))
    fwd = exit_shadow.compute_forward_return(10.0, 12.0)
    r = _es_run("02.11.2026", pairs, _at(2026, 11, 5, 18, 0))
    _check("B1 Winter 13:00 ET am Zieltag → forward_3d leer", r["forward_3d"] is None, str(r))
    r = _es_run("02.11.2026", pairs, _at(2026, 11, 5, 21, 25))
    _check("B2 16:25 ET am Zieltag → leer (seit 13.11.2026)", r["forward_3d"] is None, str(r))
    r = _es_run("02.11.2026", pairs, _at(2026, 11, 6, 12, 5))
    _check("B2 Folgetag 07:05 ET → forward_3d = Schluss T+3", r["forward_3d"] == fwd, str(r))
    r = _es_run("02.11.2026", pairs, _at(2026, 11, 6, 13, 0), inject=True)
    _check("B2 Folgetag (now_utc injiziert) → gefüllt", r["forward_3d"] == fwd, str(r))
    r = _es_run("02.11.2026", pairs, _at(2026, 11, 5, 20, 25))
    _check("B3 Winter 20:25 UTC = 15:25 EST → leer", r["forward_3d"] is None, str(r))
    sd = _days(_dt.date(2026, 7, 6), 4)
    r = _es_run("06.07.2026", list(zip(sd, [10.0, 10.5, 11.0, 12.0])), _at(2026, 7, 10, 11, 5))
    _check("B3 Sommer Folgetag 07:05 EDT → gefüllt", r["forward_3d"] == fwd, str(r))
    hd = [_dt.date(2026, 11, 25), _dt.date(2026, 11, 27), _dt.date(2026, 11, 30), _dt.date(2026, 12, 1)]
    hp = list(zip(hd, [10.0, 10.2, 10.4, 13.0]))
    r = _es_run("25.11.2026", hp, _at(2026, 12, 1, 15, 0))
    _check("B4 Thanksgiving + Wochenende: T+3 (Di) während der Sitzung → leer", r["forward_3d"] is None)
    r = _es_run("25.11.2026", hp, _at(2026, 12, 2, 12, 0))
    _check("B4 am Folgetag → Schluss des Di", r["forward_3d"] == exit_shadow.compute_forward_return(10.0, 13.0))
    r = _es_run("05.11.2026", pairs + [(_dt.date(2026, 11, 6), 9.0), (_dt.date(2026, 11, 9), 9.0),
                                       (_dt.date(2026, 11, 10), 9.0)], _at(2026, 11, 5, 18, 0))
    _check("B5 Signal-Tag selbst nicht final → nichts gefüllt",
           all(r[f"forward_{n}d"] is None for n in (3, 5, 10)), str(r))


# ── C: Bootstrap ─────────────────────────────────────────────────────────────
def _boot_hist(n_hist=26, spike_last=False):
    dates = _days(_dt.date(2026, 9, 28), n_hist)         # endet Mo 02.11.? → siehe unten
    vols = [100.0] * n_hist
    closes = [10.0 + 0.1 * i for i in range(n_hist)]
    vols[20] = 500.0                                     # Signal-Tag (Index 20)
    if spike_last:
        vols[-1] = 900.0                                 # Spike nur am laufenden Tag
    return dates, _DF(dates, {"Close": closes, "Volume": vols})


def _boot(df, now):
    class _Tk:
        info = {}
        def history(self, *a, **k): return df
    orig = bb.yf.Ticker
    bb.yf.Ticker = lambda t: _Tk()
    try:
        return bb._process_ticker("AAA", {}, now_utc=now)
    finally:
        bb.yf.Ticker = orig


def test_c_bootstrap():
    dates, df = _boot_hist()
    last = dates[-1]
    nowrun = _dt.datetime.combine(last, _dt.time(18, 0), tzinfo=UTC)   # 13:00 ET am letzten Tag
    cut = bb._final_rows(df, trading_date.last_final_close_date(nowrun))
    _check("C1 _final_rows schneidet die laufende Zeile ab",
           len(cut) == len(df) - 1 and cut.index.date[-1] == dates[-2])
    sig = dates[20]
    i_last = len(dates) - 1
    win = next((w for w in (3, 5) if 20 + w == i_last), None)
    new, _ = _boot(df, nowrun)
    e = next((x for x in new if x["date"] == sig.strftime("%d.%m.%Y")), None)
    _check("C2 Signal-Tag erkannt", e is not None, str([x["date"] for x in new]))
    if e is not None and win is not None:
        _check(f"C2 return_{win}d am laufenden Zieltag leer", e[f"return_{win}d"] is None, str(e))
        nxt = _dt.datetime.combine(last + _dt.timedelta(days=1), _dt.time(13, 0), tzinfo=UTC)
        e2 = next(x for x in _boot(df, nxt)[0] if x["date"] == e["date"])
        _check(f"C2 Folgetag → return_{win}d gefüllt", e2[f"return_{win}d"] is not None)
    dates2, df2 = _boot_hist(spike_last=True)
    new2, _ = _boot(df2, nowrun)
    _check("C3 Volumen-Spike nur am laufenden Tag erzeugt kein Signal",
           all(x["date"] != dates2[-1].strftime("%d.%m.%Y") for x in new2),
           str([x["date"] for x in new2]))


def test_d_misc():
    _check("D _trading_days_elapsed unverändert (zählt heute mit)",
           ki_agent._trading_days_elapsed("02.11.2026", _dt.date(2026, 11, 5)) == 3)
    import inspect
    _check("D update_exit_shadow_forwards(now_utc=None) injizierbar",
           "now_utc" in inspect.signature(ki_agent.update_exit_shadow_forwards).parameters)
    _check("D _process_ticker(..., now_utc=None) injizierbar",
           "now_utc" in inspect.signature(bb._process_ticker).parameters)


def main() -> int:
    for t in (test_a_window, test_b_exit_shadow, test_c_bootstrap, test_d_misc):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            _check(f"{t.__name__} ohne Exception", False, f"{type(exc).__name__}: {exc}")
    print()
    if _fails:
        print(f"{len(_fails)} FAIL")
        return 1
    print("Alle final_close_rest-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
