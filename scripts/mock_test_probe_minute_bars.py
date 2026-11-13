#!/usr/bin/env python3
"""Tests für scripts/probe_minute_bars.py — nur synthetische Daten, kein Netz."""
from __future__ import annotations

import pathlib
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import probe_minute_bars as pm  # noqa: E402

_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


D = date(2026, 11, 12)


def bars(n_skip=(), pre=0, post=0, empty=()):
    out = []
    t0 = datetime(2026, 11, 12, 9, 30, tzinfo=pm.ET)
    for k in range(-pre, 390 + post):
        t = t0 + timedelta(minutes=k)
        if k in n_skip:
            continue
        v = None if k in empty else 100.0
        out.append({"t": t, "o": 10 + k * 0.001, "h": 10.1 + k * 0.001, "l": 9.9 + k * 0.001,
                    "c": 10 + k * 0.001, "v": v})
    return out


def test_summary():
    s = pm.summarize_bars(bars(), D)
    check("390 reguläre Minuten, nichts fehlt", s["reg_bars"] == 390 and s["missing_minutes"] == 0, s)
    s = pm.summarize_bars(bars(n_skip={5, 6, 100}), D)
    check("Lücke: 3 Minuten fehlen (nicht aufgefüllt)", s["reg_bars"] == 387 and s["missing_minutes"] == 3, s)
    s = pm.summarize_bars(bars(pre=30, post=20), D)
    check("vor-/nachbörslich getrennt gezählt", s["pre_bars"] == 30 and s["post_bars"] == 20 and s["reg_bars"] == 390, s)
    s = pm.summarize_bars(bars(empty={7}), D)
    check("Volumen leer ≠ 0", s["vol_none"] == 1 and s["vol_zero"] == 0, s)
    s = pm.summarize_bars([], D)
    check("keine Balken → kein Hoch/Tief erfunden", "m_high" not in s and s["missing_minutes"] == 390, s)


def test_compare():
    s = pm.summarize_bars(bars(), D)
    day = {"o": s["m_open"], "h": s["m_high"], "l": s["m_low"], "c": s["m_close"], "v": s["m_vol"]}
    c = pm.compare_daily(s, day)
    check("gleiche Werte → Abweichung 0", c["d_high"] == 0 and c["d_close"] == 0 and c["vol_ratio"] == 1.0, c)
    day2 = dict(day, c=day["c"] * 1.01)
    check("Schluss 1 % anders → 1,0", abs(pm.compare_daily(s, day2)["d_close"] - 0.9901) < 0.001)
    check("ohne Tageszeile → leer", pm.compare_daily(s, None) == {})


def test_misc():
    check("D vor Montag = Freitag", pm.last_trading_day_before(date(2026, 11, 16)) == date(2026, 11, 13))
    bh = [{"date": "12.11.2026", "ticker": "AAA"}, {"date": "12.11.2026", "ticker": "ZZZ", "source": "bootstrap"}]
    check("Top-10 ohne Bootstrap", pm.top10_of(bh, D)[0] == ["AAA"])

    class RL(Exception):
        pass
    RL.__name__ = "YFRateLimitError"
    orig = pm.fetch_minutes
    pm.fetch_minutes = lambda *a, **k: (_ for _ in ()).throw(RL("x"))
    try:
        with tempfile.TemporaryDirectory() as t:
            out = pathlib.Path(t) / "x" / "m.json"
            rc = pm.main(["--out", str(out)])
            check("Rate-Limit → Exit 3, keine Datei", rc == 3 and not out.exists())
    finally:
        pm.fetch_minutes = orig
    wf = (ROOT / ".github" / "workflows" / "probe_minute_bars.yml").read_text(encoding="utf-8")
    check("Workflow: nur Hand-Start, nur lesen, keine Secrets, kein Push",
          "workflow_dispatch" in wf and "schedule" not in wf and "contents: read" in wf
          and "git push" not in wf and "secrets." not in wf)
    src = (ROOT / "scripts" / "probe_minute_bars.py").read_text(encoding="utf-8")
    check("schreibt nichts ins Repo", "open(ROOT" not in src.replace(
        'open(ROOT / config.BACKTEST_FILE, encoding="utf-8")', ""))


def main() -> int:
    for fn in (test_summary, test_compare, test_misc):
        print(fn.__name__)
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle probe_minute_bars-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
