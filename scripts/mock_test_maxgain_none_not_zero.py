"""Mock-Test — max_gain/max_drawdown: „unbekannt" ist None, nie 0.0 (05.11.2026).

open_item ``daily-maxgain-null-statt-0`` (Easy-Entscheid Variante A): Der
Postclose-Lauf startet meist nach Mitternacht UTC. ``_append_backtest_entries``
legt den neuen Eintrag an und rollt im SELBEN Lauf das max_gain/max_drawdown-
Fenster (Alter per ``date.today()`` = UTC → frischer Eintrag ist „1 Tag alt").
Im Fenster liegt dann nur die Entry-Tageszeile. Vorher speicherte das
``max_gain_pct = 0.0``, ``max_drawdown_pct = 0.0`` und ein erfundenes
``max_gain_pct_net = −3,92`` (Haircut auf den 0.0-Platzhalter).

Echter Schreibpfad (``backtest_history._append_backtest_entries``), Fake-Kurse
ohne Netz und ohne pandas, feste Zeitpunkte:
  A  Lauf 1 (00:30 UTC 05.11. = 19:30 ET 04.11.): neuer Eintrag 04.11., nur
     1 finale Zeile → alle drei Felder None (nicht 0.0, nicht −3,92); Keys
     vorhanden.
  B  Lauf 2 (00:30 UTC 06.11.): Eintrag 04.11. hat 2 finale Zeilen → echte
     Werte, Netto = Haircut(Brutto); neuer Eintrag 05.11. wieder None.
  C  Lauf 3 (Yahoo liefert nur noch 1 Zeile): vorhandene echte Werte von 04.11.
     bleiben stehen (nicht überschrieben, nicht gelöscht).
  D  Helper: None/leer/1 Zeile → None; 2 Zeilen → Zahl; flach → 0.0 (echte
     Null bleibt 0.0); apply_round_trip_haircut(None) is None.
  E  Alt-Record ohne Felder bleibt ohne Felder (Guards ``in e``/``not in e``).
Gegenprobe: auf dem alten Code scheitern A und D.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import pathlib
import shutil
import sys
import tempfile
import types
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _m in ("yfinance", "bs4", "deep_translator", "lxml", "pandas"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)
sys.modules["yfinance"].download = lambda *a, **kw: None
sys.modules["yfinance"].Ticker = lambda *a, **kw: None
sys.modules["bs4"].BeautifulSoup = lambda *a, **kw: None
sys.modules["deep_translator"].GoogleTranslator = lambda *a, **kw: type(
    "T", (), {"translate": staticmethod(lambda s: s)})()

import backtest_history as bh  # noqa: E402

ET = ZoneInfo("America/New_York")
UTC = _dt.timezone.utc
_fails: list[str] = []


def _check(name, cond, detail=""):
    print(("  OK  " if cond else "  FAIL ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


# ── Fake-DataFrame (nur das von _final_window/_compute_* genutzte Interface) ─
class _Series:
    def __init__(self, v): self._v = list(v)
    def _op(self, o, f):
        ov = o._v if isinstance(o, _Series) else [o] * len(self._v)
        return _Series([f(a, b) for a, b in zip(self._v, ov)])
    def __sub__(self, o): return self._op(o, lambda a, b: a - b)
    def __truediv__(self, o): return self._op(o, lambda a, b: a / b)
    def __mul__(self, o): return self._op(o, lambda a, b: a * b)
    def cummax(self):
        out, m = [], -math.inf
        for x in self._v:
            m = max(m, x); out.append(m)
        return _Series(out)
    def cummin(self):
        out, m = [], math.inf
        for x in self._v:
            m = min(m, x); out.append(m)
        return _Series(out)
    def min(self): return min(self._v)
    def max(self): return max(self._v)
    def __len__(self): return len(self._v)


class _TS:
    def __init__(self, d): self._d = d
    def date(self): return self._d


class _Idx(list):
    @property
    def date(self): return [t.date() for t in self]


class _DF:
    def __init__(self, dates, cols):
        self.index = _Idx(_TS(d) for d in dates)
        self._c = cols
    @property
    def empty(self): return len(self.index) == 0
    def __len__(self): return len(self.index)
    def __getitem__(self, k):
        if isinstance(k, list):
            keep = [i for i, b in enumerate(k) if b]
            return _DF([self.index[i].date() for i in keep],
                       {c: [v[i] for i in keep] for c, v in self._c.items()})
        return _Series(self._c[k])
    @property
    def iloc(self):
        s = self

        class _I:
            def __getitem__(self, k):
                return _DF([t.date() for t in s.index][k],
                           {c: v[k] for c, v in s._c.items()})
        return _I()


D4, D5, D6 = _dt.date(2026, 11, 4), _dt.date(2026, 11, 5), _dt.date(2026, 11, 6)
# Kurse: 04.11. High 10.5 / Low 9.5, 05.11. High 12.0 / Low 9.0
# → max_gain +33.33 (Tief 9.0 → Hoch 12.0), max_drawdown −25.0 (Hoch 12.0 → Tief 9.0)
ROWS = {D4: (10.5, 9.5), D5: (12.0, 9.0)}


def _frame(dates):
    return _DF(dates, {"High": [ROWS[d][0] for d in dates],
                       "Low": [ROWS[d][1] for d in dates]})


def _safe_float(v, default=0.0):
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _stock(bar_date):
    return {"ticker": "TST", "score": 70.0, "price": 10.0, "short_float": 25.0,
            "short_ratio": 5.0, "rel_volume": 2.4, "float_shares": 1e8,
            "avg_vol_20d": 1e6, "hist_5d": [], "score_trend_bonus_pts": 0.0,
            "agent_boost_factor": 1.0, "finra_bonus_pts": 0.0,
            "short_float_source": "yfinance", "sparkline": None,
            "finra_data": {"trend": "no_data", "history": [],
                           "si_trend_source": "finra"},
            "bar_date": bar_date.isoformat()}


def _run(workdir, report_day, utc_now, yahoo_dates):
    """Ein echter Postclose-Lauf: now_et = utc_now in ET, date.today() = UTC-
    Datum von utc_now, Yahoo liefert ``yahoo_dates``."""
    class _FixedDate(_dt.date):
        @classmethod
        def today(cls):
            return utc_now.date()
    orig_date, orig_dl = bh.date, bh.yf.download

    def _dl(*a, **kw):
        return _frame(yahoo_dates) if kw.get("period") == "1mo" else None
    cwd = os.getcwd()
    try:
        bh.date, bh.yf.download = _FixedDate, _dl
        os.chdir(workdir)
        bh._append_backtest_entries(
            [_stock(report_day)], report_day.strftime("%d.%m.%Y"), 1,
            compute_sub_scores_fn=lambda s: {"struct": 0, "catalyst": 0, "timing": 0},
            safe_float_fn=_safe_float, now_et=utc_now.astimezone(ET))
        with open("backtest_history.json") as fh:
            return {(e["ticker"], e["date"]): e for e in json.load(fh)}
    finally:
        os.chdir(cwd)
        bh.date, bh.yf.download = orig_date, orig_dl


F = ("max_gain_pct", "max_drawdown_pct", "max_gain_pct_net")


def main():
    wd = tempfile.mkdtemp(prefix="mock_maxgain_none_")
    try:
        with open(os.path.join(wd, "agent_signals.json"), "w") as fh:
            json.dump({"signals": {}}, fh)
        # Alt-Record ohne die drei Felder (Backwards-Compat-Guard, E)
        with open(os.path.join(wd, "backtest_history.json"), "w") as fh:
            json.dump([{"ticker": "OLD", "date": "03.11.2026", "score": 50.0}], fh)

        print("=== A — Lauf nach Mitternacht UTC, nur 1 finale Zeile ===")
        h1 = _run(wd, D4, _dt.datetime(2026, 11, 5, 0, 30, tzinfo=UTC), [D4])
        e = h1[("TST", "04.11.2026")]
        for f in F:
            _check(f"A {f} Key vorhanden", f in e)
            _check(f"A {f} is None (nicht 0.0 / −3,92)", e.get(f) is None, repr(e.get(f)))

        print("\n=== B — Folgetag, 2 finale Zeilen → echte Werte ===")
        h2 = _run(wd, D5, _dt.datetime(2026, 11, 6, 0, 30, tzinfo=UTC), [D4, D5])
        e = h2[("TST", "04.11.2026")]
        _check("B max_gain_pct = +33.33 (rollendes Tief 9.0 → Hoch 12.0)", e["max_gain_pct"] == 33.33, repr(e["max_gain_pct"]))
        _check("B max_drawdown_pct = −25.0 (rollendes Hoch 12.0 → Tief 9.0)", e["max_drawdown_pct"] == -25.0, repr(e["max_drawdown_pct"]))
        _check("B max_gain_pct_net = Haircut(Brutto)",
               e["max_gain_pct_net"] == bh.apply_round_trip_haircut(33.33), repr(e["max_gain_pct_net"]))
        n = h2[("TST", "05.11.2026")]
        _check("B neuer Eintrag 05.11. wieder None", all(n.get(f) is None for f in F), repr([n.get(f) for f in F]))

        print("\n=== C — Yahoo liefert weniger Zeilen → echter Wert bleibt ===")
        h3 = _run(wd, D6, _dt.datetime(2026, 11, 7, 0, 30, tzinfo=UTC), [D4])
        e = h3[("TST", "04.11.2026")]
        _check("C max_gain_pct bleibt 33.33", e["max_gain_pct"] == 33.33, repr(e["max_gain_pct"]))
        _check("C max_drawdown_pct bleibt −25.0", e["max_drawdown_pct"] == -25.0, repr(e["max_drawdown_pct"]))
        _check("C max_gain_pct_net bleibt", e["max_gain_pct_net"] == bh.apply_round_trip_haircut(33.33), repr(e["max_gain_pct_net"]))

        print("\n=== E — Alt-Record ohne Felder bleibt ohne Felder ===")
        o = h3[("OLD", "03.11.2026")]
        _check("E Alt-Record unverändert ohne die drei Felder", not any(f in o for f in F), repr(o))
    finally:
        shutil.rmtree(wd, ignore_errors=True)

    print("\n=== D — Helper ===")
    for fn in (bh._compute_max_gain_pct, bh._compute_max_drawdown):
        nm = fn.__name__
        _check(f"D {nm}(None) is None", fn(None) is None, repr(fn(None)))
        _check(f"D {nm}(leer) is None", fn(_frame([])) is None, repr(fn(_frame([]))))
        _check(f"D {nm}(1 Zeile) is None", fn(_frame([D4])) is None, repr(fn(_frame([D4]))))
        _check(f"D {nm}(2 Zeilen) ist Zahl", isinstance(fn(_frame([D4, D5])), float))
    flat = _DF([D4, D5], {"High": [10.0, 10.0], "Low": [10.0, 10.0]})
    _check("D echte Null bleibt 0.0 (flach, 2 Zeilen)", bh._compute_max_gain_pct(flat) == 0.0)
    _check("D apply_round_trip_haircut(None) is None", bh.apply_round_trip_haircut(None) is None)

    if _fails:
        print(f"\n{len(_fails)} Fehler: {_fails}")
        sys.exit(1)
    print("\nAlle max_gain/max_drawdown-None-Tests bestanden.")


if __name__ == "__main__":
    main()
