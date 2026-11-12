#!/usr/bin/env python3
"""Mock-Test: Einmal-Felder (return_*/_t1/_net, Exit-Shadow forward_*) erst
aus ENDGÜLTIGEM Schlusskurs (Fix 13.11.2026, open_item
rendite-forward-abendzeile-nicht-final).

Grenze: der Close von Tag X gilt ab 07:00 ET des folgenden Kalendertags als
endgültig (trading_date.last_settled_close_date). Kein Netz, kein pandas.

  S1  trading_date: Zieltag 16:30 / 18:00 / 20:30 ET → nicht endgültig
  S2  Folgetag 06:59 ET → nein, 07:00 ET → ja (Winter + Sommer)
  S3  Freitag-Zieltag → Samstag 07:00 ET endgültig; Montag-Lauf ebenso
  S4  Determinismus: gleiche ET-Zeit, verschiedenes UTC-Datum → gleich
  R1  update_backtest_returns: Zieltag 16:30/18:00/20:30 ET → kein Füllen
  R2  Folgetag vor 07:00 ET → kein Füllen; nach 07:00 ET → gefüllt (+ _net)
  R3  Feiertag/Wochenende zwischen Zieltag und Lauf → Schluss des Zieltags
  R4  bereits gefülltes Feld wird NICHT überschrieben
  R5  Log-Zeile "N Felder zurückgestellt bis endgültig"
  E1  update_exit_shadow_forwards: Zieltag 16:30/18:00/20:30 ET → leer
  E2  Folgetag vor/nach 07:00 ET
  G1  Gegenprobe: mit der alten Grenze (last_final_close_date) würde um
      16:30/18:00/20:30 ET gefüllt (alter Code = rot)
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import mock_test_backtest_returns_final_close as R  # noqa: E402  (installiert Stubs)
import mock_test_final_close_rest as X  # noqa: E402
import exit_shadow  # noqa: E402
import ki_agent  # noqa: E402
import trading_date  # noqa: E402

UTC = _dt.timezone.utc
_fails: list[str] = []


def _check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        _fails.append(name)


def _et(y, m, d, hh, mm):
    """ET-Wanduhrzeit → UTC-datetime."""
    return _dt.datetime(y, m, d, hh, mm, tzinfo=trading_date._NY).astimezone(UTC)


# Winter: Entry Mo 02.11.2026, T+3 = Do 05.11.
WD, WV = R.W_DATES[:4], R.W_VALS[:4]
EVENING = [(16, 30), (18, 0), (20, 30)]


def test_trading_date():
    D = _dt.date(2026, 11, 5)
    for hh, mm in EVENING:
        _check(f"S1 Zieltag {hh:02d}:{mm:02d} ET → nicht endgültig",
               not trading_date.close_is_settled(D, _et(2026, 11, 5, hh, mm)))
    _check("S2 Winter Folgetag 06:59 ET → nein",
           not trading_date.close_is_settled(D, _et(2026, 11, 6, 6, 59)))
    _check("S2 Winter Folgetag 07:00 ET → ja",
           trading_date.close_is_settled(D, _et(2026, 11, 6, 7, 0)))
    S = _dt.date(2026, 7, 9)
    _check("S2 Sommer Folgetag 06:59 EDT → nein",
           not trading_date.close_is_settled(S, _et(2026, 7, 10, 6, 59)))
    _check("S2 Sommer Folgetag 07:00 EDT → ja",
           trading_date.close_is_settled(S, _et(2026, 7, 10, 7, 0)))
    F = _dt.date(2026, 11, 6)  # Freitag
    _check("S3 Freitag → Samstag 07:00 ET endgültig",
           trading_date.close_is_settled(F, _et(2026, 11, 7, 7, 0)))
    _check("S3 Freitag → Montag 05:00 ET endgültig",
           trading_date.close_is_settled(F, _et(2026, 11, 9, 5, 0)))
    # 20:30 ET Winter = 01:30 UTC Folgetag; 18:00 ET = 23:00 UTC Zieltag
    a = trading_date.last_settled_close_date(_et(2026, 11, 5, 18, 0))
    b = trading_date.last_settled_close_date(_et(2026, 11, 5, 20, 30))
    _check("S4 Determinismus: 18:00 ET (UTC Zieltag) == 20:30 ET (UTC Folgetag)",
           a == b == _dt.date(2026, 11, 4), f"{a} {b}")
    _check("S4 naiv = UTC", trading_date.last_settled_close_date(
        _dt.datetime(2026, 11, 6, 12, 0)) == _dt.date(2026, 11, 5))


def test_returns():
    for hh, mm in EVENING:
        e = R._run([R._entry("02.11.2026")], WD, WV, _et(2026, 11, 5, hh, mm), inject=True)
        _check(f"R1 Zieltag {hh:02d}:{mm:02d} ET → return_3d leer",
               e["return_3d"] is None and e.get("return_3d_net") is None, str(e["return_3d"]))
    e = R._run([R._entry("02.11.2026")], WD, WV, _et(2026, 11, 6, 6, 55), inject=True)
    _check("R2 Folgetag 06:55 ET → leer", e["return_3d"] is None)
    e = R._run([R._entry("02.11.2026")], WD, WV, _et(2026, 11, 6, 7, 5), inject=True)
    _check("R2 Folgetag 07:05 ET → gefüllt", e["return_3d"] == R._ret(12.0, 10.0), str(e["return_3d"]))
    _check("R2 _net mitgefüllt", e.get("return_3d_net") is not None)
    _check("R2 entry_price_t1 gefüllt", e["entry_price_t1"] == 10.5)
    # Freitag-Zieltag: Entry Di 03.11., T+3 = Fr 06.11.; Lauf Montag 09.11. 03:00 ET
    d = [_dt.date(2026, 11, x) for x in (3, 4, 5, 6)]
    e = R._run([R._entry("03.11.2026")], d, [10.0, 10.5, 11.0, 13.0], _et(2026, 11, 7, 6, 0), inject=True)
    _check("R3 Fr-Zieltag, Sa 06:00 ET → leer", e["return_3d"] is None)
    e = R._run([R._entry("03.11.2026")], d, [10.0, 10.5, 11.0, 13.0], _et(2026, 11, 9, 3, 0), inject=True)
    _check("R3 Fr-Zieltag, Mo 03:00 ET → gefüllt mit Fr-Schluss", e["return_3d"] == R._ret(13.0, 10.0))
    # Thanksgiving 26.11.2026: Entry Mo 23.11., Zeilen 23,24,25,27 → T+3 = Fr 27.11.
    d = [_dt.date(2026, 11, x) for x in (23, 24, 25, 27)]
    e = R._run([R._entry("23.11.2026")], d, [10.0, 10.5, 11.0, 14.0], _et(2026, 11, 27, 18, 0), inject=True)
    _check("R3 Feiertag dazwischen, Zieltag Fr 18:00 ET → leer", e["return_3d"] is None)
    e = R._run([R._entry("23.11.2026")], d, [10.0, 10.5, 11.0, 14.0], _et(2026, 11, 28, 7, 30), inject=True)
    _check("R3 Feiertag dazwischen, Sa 07:30 ET → gefüllt", e["return_3d"] == R._ret(14.0, 10.0))
    pre = R._entry("02.11.2026")
    pre["return_3d"] = 99.99
    e = R._run([pre], WD, WV, _et(2026, 11, 6, 12, 0), inject=True)
    _check("R4 gefülltes return_3d bleibt", e["return_3d"] == 99.99)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R._run([R._entry("02.11.2026")], WD, WV, _et(2026, 11, 5, 18, 0), inject=True)
    _check("R5 Log 'Felder zurückgestellt bis endgültig'",
           "zurückgestellt bis endgültig" in buf.getvalue(), buf.getvalue()[-200:])


def test_exit_shadow():
    dates = [_dt.date(2026, 11, x) for x in (2, 3, 4, 5)]
    pairs = list(zip(dates, [10.0, 10.5, 11.0, 12.0]))
    fwd = exit_shadow.compute_forward_return(10.0, 12.0)
    for hh, mm in EVENING:
        r = X._es_run("02.11.2026", pairs, _et(2026, 11, 5, hh, mm), inject=True)
        _check(f"E1 Zieltag {hh:02d}:{mm:02d} ET → forward_3d leer", r["forward_3d"] is None, str(r))
    r = X._es_run("02.11.2026", pairs, _et(2026, 11, 6, 6, 55), inject=True)
    _check("E2 Folgetag 06:55 ET → leer", r["forward_3d"] is None)
    r = X._es_run("02.11.2026", pairs, _et(2026, 11, 6, 7, 5), inject=True)
    _check("E2 Folgetag 07:05 ET → gefüllt", r["forward_3d"] == fwd, str(r))


def test_gegenprobe():
    orig = trading_date.last_settled_close_date
    try:
        trading_date.last_settled_close_date = trading_date.last_final_close_date
        for hh, mm in EVENING:
            e = R._run([R._entry("02.11.2026")], WD, WV, _et(2026, 11, 5, hh, mm), inject=True)
            _check(f"G1 alte Grenze: Zieltag {hh:02d}:{mm:02d} ET hätte gefüllt (rot)",
                   e["return_3d"] is not None)
            r = X._es_run("02.11.2026", list(zip(WD, WV)), _et(2026, 11, 5, hh, mm), inject=True)
            _check(f"G1 alte Grenze: forward_3d {hh:02d}:{mm:02d} ET hätte gefüllt (rot)",
                   r["forward_3d"] is not None)
    finally:
        trading_date.last_settled_close_date = orig


def test_source():
    src = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
    _check("Q1 ki_agent nutzt last_settled_close_date in beiden Füll-Pfaden",
           src.count("final_cut = trading_date.last_settled_close_date(now)") == 2)
    _check("Q2 ki_agent liest last_final_close_date nicht mehr",
           "last_final_close_date(" not in src)


def main() -> int:
    for t in (test_trading_date, test_returns, test_exit_shadow, test_gegenprobe, test_source):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            _check(f"{t.__name__} ohne Exception", False, f"{type(exc).__name__}: {exc}")
    print()
    if _fails:
        print(f"{len(_fails)} FAIL")
        return 1
    print("Alle settled_close_fill-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
