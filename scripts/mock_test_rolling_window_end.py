"""Mock-Test: Rolling-Fenster max_gain_pct/max_drawdown_pct endet erst mit
finalem Tag 10 (Fix 13.11.2026, open_item max-gain-rolling-fenster-abgeschnitten).

Befund: ``_append_backtest_entries`` beendete das Rolling-Update nach 14
Kalendertagen (``0 < (date.today() − D) ≤ 14``, UTC-Datum des Laufs). Bei Lauf
nach Mitternacht UTC, ausgefallenem Postclose oder Feiertag im Fenster blieb das
Fenster vor Tag 10 stehen; der append-only-Export fror den Wert ein.

Geprüft (deterministisch, kein Netz):
  1. Handelskalender: Tag 10 über Wochenenden und Thanksgiving.
  2. Gegenprobe alte Regel ROT / neue Regel GRÜN: DFH-artiger Fall (D 22.10.,
     Tag 10 = 05.11., Postclose läuft 00:30 UTC am 06.11.) und Feiertags-Fall.
  3. Determinismus: gleiche Kursdaten + gleicher finaler Tag → gleiche Werte,
     egal ob der Lauf vor oder nach Mitternacht UTC stattfindet.
  4. Nie kürzeres Fenster überschreiben; Nachfrist-Ende.
  5. Export-Gate: erst bei vollständigem Fenster (oder nach Nachfrist).
  6. Wächter S17 meldet einen Rückfall (abgeschnittene Zeile ab Fix-Naht),
     Altbestand nur als Zahl; Ausgabe ohne Werte.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib  # noqa: E402
import types  # noqa: E402

try:  # CI-Slot hat kein pandas (stdlib+jinja2+pyyaml) → DataFrame-Teil dort übersprungen
    import pandas as pd  # noqa: E402
except ImportError:  # pragma: no cover
    pd = None

# Netzfreie Stubs nur, wenn die Pakete lokal fehlen (CI installiert sie).
for _m in ("yfinance", "bs4", "deep_translator"):
    try:
        importlib.import_module(_m)
    except ImportError:
        sys.modules[_m] = types.ModuleType(_m)

import backtest_history as bh  # noqa: E402
import config  # noqa: E402
import health_check as hc  # noqa: E402
import matured_export as me  # noqa: E402
import trading_date as td  # noqa: E402

_fails: list[str] = []
H = config.US_MARKET_HOLIDAYS


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


def _old_rule(edate: date, run_utc: datetime) -> bool:
    """Replik der ENTFERNTEN Regel (nur Gegenprobe)."""
    days_old = (run_utc.date() - edate).days
    return 0 < days_old <= 14


def _days(edate: date, n: int) -> list:
    days, d = [edate], edate
    while len(days) < n:
        d += timedelta(days=1)
        if td.is_us_trading_day(d, H):
            days.append(d)
    return days


def _bars(edate: date, n: int, highs=None):
    days = _days(edate, n)
    highs = highs or [10.0 + i for i in range(n)]
    return pd.DataFrame({"High": highs[:n], "Low": [9.0] * n, "Close": [9.5] * n,
                         "Open": [9.5] * n},
                        index=pd.DatetimeIndex([pd.Timestamp(x) for x in days]))


def test_calendar():
    check("Tag 10 nach Do 22.10.2026 = Do 05.11.2026",
          td.nth_trading_day_after(date(2026, 10, 22), 10, H) == date(2026, 11, 5))
    check("Tag 10 nach Fr 13.11.2026 = Mo 30.11.2026 (Thanksgiving 26.11.)",
          td.nth_trading_day_after(date(2026, 11, 13), 10, H) == date(2026, 11, 30))
    check("n = 0 → D selbst", td.nth_trading_day_after(date(2026, 11, 13), 0, H) == date(2026, 11, 13))


def test_old_red_new_green():
    d = date(2026, 10, 22)
    run = datetime(2026, 11, 6, 0, 30, tzinfo=timezone.utc)    # Postclose 05.11. nach Mitternacht UTC
    final_cut = td.last_final_close_date(run)
    check("final_cut = 05.11. (19:30 ET am 05.11.)", final_cut == date(2026, 11, 5), final_cut)
    check("Gegenprobe alte Regel: Tag-10-Lauf NICHT aktiv (ROT)", _old_rule(d, run) is False)
    e = {"rolling_window_n": 8}
    check("neue Regel: Tag-10-Lauf aktiv (GRÜN)",
          bh._rolling_window_active(e, d, final_cut, run.date()) is True)
    # Feiertags-Fall: D 13.11., Tag 10 = 30.11. (17 Kalendertage).
    d2 = date(2026, 11, 13)
    run2 = datetime(2026, 11, 30, 22, 0, tzinfo=timezone.utc)
    check("Gegenprobe alte Regel: Feiertags-Fenster an Tag 10 inaktiv (ROT)", _old_rule(d2, run2) is False)
    check("neue Regel: Feiertags-Fenster an Tag 10 aktiv (GRÜN)",
          bh._rolling_window_active({"rolling_window_n": None}, d2,
                                    td.last_final_close_date(run2), run2.date()) is True)
    # Nachfrist-Ende: Tag 10 + 7 + 1 → inaktiv.
    late = bh._rolling_window_end(d) + timedelta(days=config.ROLLING_WINDOW_GRACE_DAYS + 1)
    check("nach Nachfrist inaktiv", bh._rolling_window_active(e, d, late, late) is False)
    check("vor D inaktiv", bh._rolling_window_active(e, d, d - timedelta(days=1), d) is False)
    check("11 Zeilen, aber Tag 10 erst heute final → noch aktiv (Halbzeilen-Schutz)",
          bh._rolling_window_active({"rolling_window_n": 11}, d, final_cut, run.date()) is True)
    check("11 Zeilen und Tag 10 vor dem letzten finalen Schluss → inaktiv (wie Export-Gate)",
          bh._rolling_window_active({"rolling_window_n": 11}, d, date(2026, 11, 6), run.date()) is False)
    # Altbestand ohne Key: alte Regel unverändert.
    check("Altbestand ohne Key: alte Regel (Tag 15 inaktiv)",
          bh._rolling_window_active({}, d, final_cut, date(2026, 11, 6)) is False)
    check("Altbestand ohne Key: alte Regel (Tag 5 aktiv)",
          bh._rolling_window_active({}, d, final_cut, date(2026, 10, 27)) is True)


def test_determinism_and_update():
    if pd is None:
        print("  (übersprungen: pandas nicht verfügbar — CI-Slot; läuft lokal/im Daily-Run-Environment)")
        return
    d = date(2026, 10, 22)
    df = _bars(d, 13, highs=[10, 10.4, 10.7, 10.3, 10.3, 10.3, 10.7, 11.0, 10.9, 12.9, 13.3, 20, 20])
    res = []
    for run in (datetime(2026, 11, 5, 23, 30, tzinfo=timezone.utc),     # vor Mitternacht UTC
                datetime(2026, 11, 6, 0, 30, tzinfo=timezone.utc),      # nach Mitternacht UTC
                datetime(2026, 11, 6, 4, 59, tzinfo=timezone.utc)):     # 23:59 ET
        e = {"max_drawdown_pct": None, "max_gain_pct": None, "rolling_window_n": None}
        bh._apply_rolling_window(e, df, d, td.last_final_close_date(run))
        res.append((e["max_gain_pct"], e["max_drawdown_pct"], e["rolling_window_n"]))
    check("Determinismus: vor/nach Mitternacht UTC gleiche Werte", len(set(res)) == 1, res)
    check("volles Fenster = 11 Zeilen, Tag 11/12 nicht enthalten",
          res[0][2] == 11 and res[0][0] == round((13.3 / 9.0 - 1) * 100, 2), res[0])
    # Halbzeile an Tag 10 (Close/High/Low NaN, Postclose ~20:28 ET) zählt nicht.
    half = df.copy()
    half.iloc[10, half.columns.get_loc("Close")] = float("nan")
    half.iloc[10, half.columns.get_loc("High")] = float("nan")
    e = {"max_drawdown_pct": None, "max_gain_pct": None, "rolling_window_n": None}
    bh._apply_rolling_window(e, half, d, date(2026, 11, 5))
    check("Halbzeile an Tag 10 → rolling_window_n = 10 (Fenster bleibt offen)",
          e["rolling_window_n"] == 10, e)
    # Nie kürzer überschreiben.
    e = {"max_drawdown_pct": -5.0, "max_gain_pct": 47.78, "rolling_window_n": 11}
    out = bh._apply_rolling_window(e, df, d, date(2026, 11, 2))   # nur 8 Zeilen final
    check("kürzeres Fenster überschreibt nicht", out == (False, False) and e["max_gain_pct"] == 47.78
          and e["rolling_window_n"] == 11, e)


def test_export_gate():
    d = "22.10.2026"
    base = {"ticker": "AAA", "date": d, "return_10d": 1.0, "max_gain_pct": 1.0,
            "max_drawdown_pct": -1.0, "source": "daily"}
    now_after_14 = datetime(2026, 11, 6, 0, 30, tzinfo=timezone.utc)   # 15 Kalendertage
    with tempfile.TemporaryDirectory() as tmp:
        ex = os.path.join(tmp, "ex.jsonl")
        open(ex, "w").write(json.dumps({"ticker": "OLD", "date": "01.08.2026"}) + "\n")
        n = me.export_matured_records([dict(base, rolling_window_n=8)], export_path=ex, now=now_after_14)
        check("unvollständiges Fenster (8) nach 15 Kalendertagen NICHT exportiert", n == 0, n)
        n = me.export_matured_records([dict(base, rolling_window_n=11)], export_path=ex, now=now_after_14)
        check("11 Zeilen, Tag 10 erst seit diesem Abend final → noch NICHT exportiert", n == 0, n)
        next_eve = datetime(2026, 11, 6, 22, 0, tzinfo=timezone.utc)
        n = me.export_matured_records([dict(base, rolling_window_n=11)], export_path=ex, now=next_eve)
        check("vollständiges Fenster (11), Folgetag final → exportiert", n == 1, n)
        late = datetime(2026, 11, 14, 22, 0, tzinfo=timezone.utc)
        n = me.export_matured_records([dict(base, ticker="BBB", rolling_window_n=8)], export_path=ex, now=late)
        check("nach Nachfrist auch unvollständig exportiert (S17 zählt es)", n == 1, n)
        legacy = dict(base, ticker="CCC")
        n = me.export_matured_records([legacy], export_path=ex, now=now_after_14)
        check("Altbestand ohne Key: alte 14-Tage-Regel", n == 1, n)


def test_s17_watchdog():
    d_old, d_new = date(2026, 10, 22), date(2026, 11, 13)
    def bars_rows(edate):
        highs = [10, 10.4, 10.7, 10.3, 10.3, 10.3, 10.7, 11.0, 10.9, 12.9, 13.3]
        return [{"d": str(x), "o": 9.5, "h": float(h), "l": 9.0, "c": 9.5}
                for x, h in zip(_days(edate, 11), highs)]
    full = round((13.3 / 9 - 1) * 100, 2)
    cut7 = round((11.0 / 9 - 1) * 100, 2)
    with tempfile.TemporaryDirectory() as tmp:
        op = os.path.join(tmp, "op.jsonl")
        ex = os.path.join(tmp, "ex.jsonl")
        with open(op, "w") as fh:
            for t, dd in (("OLD", d_old), ("NEW", d_new), ("OK", d_new)):
                fh.write(json.dumps({"ticker": t, "date": dd.strftime("%d.%m.%Y"), "bars": bars_rows(dd)}) + "\n")
        def write(rows):
            with open(ex, "w") as fh:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")
        dd_full = round((9 / 10 - 1) * 100, 2)  # laufendes Hoch 10 an D, Tief 9
        write([{"ticker": "OLD", "date": "22.10.2026", "max_gain_pct": cut7, "max_drawdown_pct": dd_full},
               {"ticker": "OK", "date": "13.11.2026", "max_gain_pct": full, "max_drawdown_pct": dd_full,
                "rolling_window_n": 11}])
        c = hc.s17_rolling_window_counts(ex, op, d_new)
        check("Altbestand gezählt, kein Rückfall",
              {k: c.get(k) for k in ("geprueft", "neu", "alt", "unvollstaendig")}
              == {"geprueft": 2, "neu": 0, "alt": 1, "unvollstaendig": 0}, c)
        check("Altbestand allein → kein warn", hc.evaluate_s17_rolling_window(ex, op, d_new) == [])
        write([{"ticker": "NEW", "date": "13.11.2026", "max_gain_pct": cut7, "max_drawdown_pct": dd_full,
                "rolling_window_n": 11}])
        f = hc.evaluate_s17_rolling_window(ex, op, d_new)
        check("Rückfall ab Fix-Naht → warn S17", len(f) == 1 and f[0]["id"] == "S17" and f[0]["severity"] == "warn", f)
        check("S17-Detail ohne Werte/Ticker", f and str(cut7).replace(".", ",") not in f[0]["detail"]
              and str(cut7) not in f[0]["detail"] and "NEW" not in f[0]["detail"], f)
        write([{"ticker": "OK", "date": "13.11.2026", "max_gain_pct": full, "max_drawdown_pct": dd_full,
                "rolling_window_n": 9}])
        f = hc.evaluate_s17_rolling_window(ex, op, d_new)
        check("Export mit rolling_window_n < 11 → warn", len(f) == 1 and "1 mit unvollständigem" in f[0]["detail"], f)
        check("fehlende Dateien → SKIP", hc.evaluate_s17_rolling_window(ex, os.path.join(tmp, "x"), d_new) == [])
    src = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    check("alte 14-Tage-Schranke nur noch im Altbestand-Zweig",
          src.count("0 < days_old <= 14") == 1 and "days_old > 14:" not in src)


def run_all() -> int:
    for t in (test_calendar, test_old_red_new_green, test_determinism_and_update,
              test_export_gate, test_s17_watchdog):
        print(t.__name__)
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle Rolling-Fenster-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
