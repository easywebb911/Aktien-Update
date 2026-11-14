#!/usr/bin/env python3
"""Mock-Test Berichtsdatum Variante A (Easy-Entscheid 14.11.2026).

Ohne Netz, ohne pandas (yfinance & Co. gestubbt).

 1  trading_date.report_trading_date: 23:50 ET (unverändert), 00:30 ET,
    01:28 ET (Fall 27.08.2026), 09:29 ET, 09:31 ET, Freitag-Nacht/Samstag,
    Sonntag, Montag früh, Feiertag (Thanksgiving), Tag nach Feiertag.
 2  Determinismus: gleiche ET-Uhrzeit → gleiches Datum, unabhängig vom UTC-Datum
    (Sommer-/Winterzeit), naive Eingabe = UTC.
 3  _resolve_report_day (generate_report): nur Postclose verschiebt; Premarket
    behält das Kalenderdatum; Abendlauf vor Mitternacht unverändert.
 4  Vintage-Guard: 01:28-Lauf schreibt für D; Gegenprobe alter Code (Kalender-
    datum) verwirft den Tag; 09:29 append; 09:31 verwerfen; Fenster-Ende.
 5  _append_backtest_entries End-to-End (echter Schreibpfad, temp-Verzeichnis):
    Nachtlauf schreibt D mit nacht_lauf_et; Abendlauf ohne Feld (unverändert);
    zweiter Lauf für dasselbe D schreibt nichts doppelt; alter Code: 0 Einträge.
 6  Hand-Start „postclose“ zwischen 00:00 und 09:30 ET bleibt postclose.
 7  Wiring in main(): Sammler, Health-Check und Earnings-Tage auf demselben Tag.
 8  S15-Zusatz: Postclose-Verwurf aus vintage_guard_log → warn; erwartete
    Skips (holiday_or_prior_bar) und alte Zeilen → kein Fail.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import shutil
import sys
import tempfile
import types
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

for _m in ("yfinance", "bs4", "deep_translator", "lxml", "pandas"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)
sys.modules["yfinance"].download = lambda *a, **k: None
sys.modules["yfinance"].Ticker = lambda *a, **k: None
sys.modules["bs4"].BeautifulSoup = lambda *a, **k: None
sys.modules["deep_translator"].GoogleTranslator = lambda *a, **k: type(
    "T", (), {"translate": staticmethod(lambda s: s)})()

import backtest_history as bh  # noqa: E402
import config  # noqa: E402
import health_check as hc  # noqa: E402
import trading_date as td  # noqa: E402

ET = ZoneInfo("America/New_York")
H = config.US_MARKET_HOLIDAYS
GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {str(detail)[:300]}"))
    if not cond:
        _fails.append(name)


def et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


def rtd(dt):
    return td.report_trading_date(dt, H)


def test_report_trading_date():
    print("1 report_trading_date")
    check("Mi 23:50 ET → Mi (unverändert)", rtd(et(2026, 11, 11, 23, 50)) == date(2026, 11, 11))
    check("Do 00:30 ET → Mi", rtd(et(2026, 11, 12, 0, 30)) == date(2026, 11, 11))
    check("Fr 28.08. 01:28 ET (Fall 27.08.) → Do 27.08.",
          rtd(et(2026, 8, 28, 1, 28)) == date(2026, 8, 27))
    check("Di 09:29 ET → Mo", rtd(et(2026, 11, 10, 9, 29)) == date(2026, 11, 9))
    check("Di 09:31 ET → Di (Kalenderdatum)", rtd(et(2026, 11, 10, 9, 31)) == date(2026, 11, 10))
    check("Sa 00:30 ET (Freitag-Nacht) → Fr", rtd(et(2026, 11, 14, 0, 30)) == date(2026, 11, 13))
    check("So 08:00 ET → Fr", rtd(et(2026, 11, 15, 8, 0)) == date(2026, 11, 13))
    check("Mo 01:00 ET → Fr", rtd(et(2026, 11, 16, 1, 0)) == date(2026, 11, 13))
    check("Thanksgiving Do 26.11. 01:00 ET → Mi 25.11.",
          rtd(et(2026, 11, 26, 1, 0)) == date(2026, 11, 25))
    check("Fr 27.11. 01:00 ET (nach Feiertag) → Mi 25.11.",
          rtd(et(2026, 11, 27, 1, 0)) == date(2026, 11, 25))
    check("Sa 14:00 ET → Kalenderdatum Sa (Regel nur vor 09:30 ET)",
          rtd(et(2026, 11, 14, 14, 0)) == date(2026, 11, 14))
    check("Fenster-Ende Fr → Mo 09:30 ET",
          td.postclose_window_end(date(2026, 11, 13), H) == et(2026, 11, 16, 9, 30))
    check("Fenster-Ende Mi 25.11. → Fr 27.11. 09:30 ET (Thanksgiving übersprungen)",
          td.postclose_window_end(date(2026, 11, 25), H) == et(2026, 11, 27, 9, 30))


def test_determinism():
    print("2 Determinismus")
    # 00:30 ET im Sommer (EDT, UTC 04:30 gleicher Tag) und im Winter (EST, 05:30 UTC)
    s = datetime(2026, 8, 28, 4, 30, tzinfo=timezone.utc)
    w = datetime(2026, 11, 12, 5, 30, tzinfo=timezone.utc)
    check("Sommer 00:30 ET → Vortag", rtd(s) == date(2026, 8, 27))
    check("Winter 00:30 ET → Vortag", rtd(w) == date(2026, 11, 11))
    # 23:50 ET Winter = 04:50 UTC des Folgetags: UTC-Datum ≠ ET-Datum → ET zählt
    late = datetime(2026, 11, 12, 4, 50, tzinfo=timezone.utc)
    check("Mi 23:50 ET (UTC schon Do) → Mi", rtd(late) == date(2026, 11, 11))
    check("naive Eingabe = UTC", rtd(datetime(2026, 11, 12, 4, 50)) == date(2026, 11, 11))
    check("gleiche Eingabe → gleiches Ergebnis", rtd(late) == rtd(late))


def _resolver():
    start = GR_SRC.index("def _resolve_report_day(")
    end = GR_SRC.index("\n\n\ndef ", start)
    ns = {"trading_date": td, "US_MARKET_HOLIDAYS": H, "datetime": datetime, "date": date}
    exec(compile(GR_SRC[start:end], "<resolve_report_day>", "exec"), ns)
    return ns["_resolve_report_day"]


def test_resolver():
    print("3 _resolve_report_day")
    f = _resolver()
    night = et(2026, 8, 28, 1, 28).astimezone(timezone.utc)
    eve = et(2026, 8, 27, 22, 0).astimezone(timezone.utc)
    check("postclose 01:28 ET → D 27.08.", f("postclose", night) == date(2026, 8, 27))
    check("premarket 01:28 ET → Kalenderdatum 28.08.", f("premarket", night) == date(2026, 8, 28))
    check("postclose 22:00 ET (vor Mitternacht) → unverändert 27.08.",
          f("postclose", eve) == date(2026, 8, 27)
          and f("postclose", eve) == td.us_trading_date(eve))
    # Abendläufe 16:20–23:59 ET an allen Handelstagen Okt./Nov.: identisch zum alten Code
    diffs = []
    d = date(2026, 10, 1)
    while d <= date(2026, 11, 30):
        if td.is_us_trading_day(d, H):
            for hh, mm in ((16, 20), (17, 37), (20, 28), (21, 29), (23, 59)):
                u = et(d.year, d.month, d.day, hh, mm).astimezone(timezone.utc)
                if f("postclose", u) != td.us_trading_date(u):
                    diffs.append((d, hh, mm))
        d += timedelta(days=1)
    check("alle Abendläufe Okt./Nov. byte-gleich wie vorher", not diffs, diffs[:5])


def test_guard():
    print("4 Vintage-Guard")
    D = "27.08.2026"
    now = et(2026, 8, 28, 1, 28)
    check("neu: Nachtlauf 01:28 → append", bh._vintage_gate_decision(D, "2026-08-27", now)
          == ("append", "ok"))
    check("Gegenprobe alter Code: Berichtsdatum 28.08. → skip pre_open (Tag verloren)",
          bh._vintage_gate_decision("28.08.2026", "2026-08-28", now) == ("skip", "pre_open"))
    check("09:29 ET → append", bh._vintage_gate_decision(
        "09.11.2026", "2026-11-09", et(2026, 11, 10, 9, 29)) == ("append", "ok"))
    rd31 = rtd(et(2026, 11, 10, 9, 31)).strftime("%d.%m.%Y")
    check("09:31 ET (Berichtsdatum = heute) → verwerfen (before_close)",
          bh._vintage_gate_decision(rd31, "2026-11-10", et(2026, 11, 10, 9, 31))
          == ("skip", "before_close"))
    check("Fenster-Ende: D=Fr, Lauf Mo 09:31 → after_window",
          bh._vintage_gate_decision("13.11.2026", "2026-11-13", et(2026, 11, 16, 9, 31))
          == ("skip", "after_window"))
    check("Abendlauf 22:00 ET am Tag D → unverändert append",
          bh._vintage_gate_decision("27.08.2026", "2026-08-27", et(2026, 8, 27, 22, 0))
          == ("append", "ok"))
    check("Vortags-Bar im Nachtlauf → weiter skip (holiday_or_prior_bar)",
          bh._vintage_gate_decision(D, "2026-08-26", now) == ("skip", "holiday_or_prior_bar"))


def _real_safe_float():
    """ECHTE generate_report._safe_float per Source-Extraktion (kein Import der
    vollen generate_report-Kette)."""
    start = GR_SRC.index("def _safe_float(")
    end = GR_SRC.index("\n\n\n", start)
    ns = {"math": math}
    exec(compile(GR_SRC[start:end], "<safe_float>", "exec"), ns)
    return ns["_safe_float"]


_safe_float = _real_safe_float()


def _stock(t):
    return {"ticker": t, "score": 70.0, "price": 10.0, "short_float": 25.0,
            "short_ratio": 5.0, "rel_volume": 2.4, "float_shares": 1e8,
            "avg_vol_20d": 1e6, "hist_5d": [], "score_trend_bonus_pts": 0.0,
            "agent_boost_factor": 1.0, "finra_bonus_pts": 0.0,
            "short_float_source": "yfinance",
            "finra_data": {"trend": "no_data", "history": [], "si_trend_source": "finra"},
            "sparkline_view": None, "bar_date": "2026-08-27"}


def _append(tmp, report_date, now_et, tickers=("AAA", "BBB")):
    cwd = os.getcwd()
    os.chdir(tmp)
    try:
        return bh._append_backtest_entries(
            [_stock(t) for t in tickers], report_date, pool_size=len(tickers),
            compute_sub_scores_fn=lambda s: {"struct": 0, "catalyst": 0, "timing": 0},
            safe_float_fn=_safe_float, now_et=now_et)
    finally:
        os.chdir(cwd)


def _read(tmp):
    with open(os.path.join(tmp, "backtest_history.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _fresh_dir():
    tmp = tempfile.mkdtemp(prefix="mock_berichtsdatum_")
    with open(os.path.join(tmp, "agent_signals.json"), "w") as fh:
        json.dump({"signals": {}}, fh)
    with open(os.path.join(tmp, "backtest_history.json"), "w") as fh:
        json.dump([], fh)
    return tmp


def test_append_end_to_end():
    print("5 _append_backtest_entries End-to-End")
    flags = ("BACKTEST_ENABLED", "SSR_RESTRICTION_ENABLED", "MATERIAL_8K_ENABLED",
             "WIKI_ATTENTION_ENABLED")
    orig = {k: getattr(bh, k) for k in flags}
    bh.BACKTEST_ENABLED = True
    for k in flags[1:]:          # kein Netz im Test
        setattr(bh, k, False)
    try:
        tmp = _fresh_dir()
        try:
            night = et(2026, 8, 28, 1, 28)
            rd = rtd(night).strftime("%d.%m.%Y")
            n1 = _append(tmp, rd, night)
            rows = _read(tmp)
            check("Nachtlauf 01:28 schreibt 2 Einträge für 27.08.",
                  n1 == 2 and {r["date"] for r in rows} == {"27.08.2026"}, (n1, rows[:1]))
            check("Kennzeichen nacht_lauf_et = Laufzeit ET",
                  all(r.get("nacht_lauf_et") == "2026-08-28T01:28:00-04:00" for r in rows), rows[:1])
            n2 = _append(tmp, rd, et(2026, 8, 28, 2, 50))
            check("zweiter Lauf für dasselbe D: nichts doppelt", n2 == 0 and len(_read(tmp)) == 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        tmp = _fresh_dir()
        try:
            n = _append(tmp, "27.08.2026", et(2026, 8, 27, 22, 0))
            rows = _read(tmp)
            check("Abendlauf vor Mitternacht: Einträge OHNE nacht_lauf_et (unverändert)",
                  n == 2 and all("nacht_lauf_et" not in r for r in rows))
            n3 = _append(tmp, rtd(et(2026, 8, 28, 1, 28)).strftime("%d.%m.%Y"),
                         et(2026, 8, 28, 1, 28))
            check("Nachtlauf nach Abendlauf (gleiches D): nichts doppelt",
                  n3 == 0 and len(_read(tmp)) == 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        tmp = _fresh_dir()
        try:
            n_old = _append(tmp, "28.08.2026", et(2026, 8, 28, 1, 28))
            check("Gegenprobe alter Code (Berichtsdatum = Kalendertag): 0 Einträge",
                  n_old == 0 and _read(tmp) == [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    finally:
        for k, v in orig.items():
            setattr(bh, k, v)
    check("nacht_lauf_et in S10_OBSERVED_FIELDS (kein S10-Fehlalarm)",
          "nacht_lauf_et" in config.S10_OBSERVED_FIELDS)


def test_hand_start():
    print("6 Hand-Start")
    import resolve_run_phase as rrp
    for hh, mm in ((0, 5), (1, 28), (9, 29)):
        ph, _ = rrp.resolve_run_phase("workflow_dispatch", None, "postclose",
                                      et(2026, 11, 12, hh, mm).astimezone(timezone.utc))
        check(f"Hand-Start postclose {hh:02d}:{mm:02d} ET bleibt postclose", ph == "postclose", ph)


def test_wiring():
    print("7 Wiring main()")
    m = GR_SRC[GR_SRC.index("def main():"):]
    check("report_date aus _resolve_report_day",
          "_report_day = _resolve_report_day(run_phase, _run_now_utc)" in m
          and 'report_date = _report_day.strftime("%d.%m.%Y")' in m)
    check("Sammler-Datum = Berichts-Handelstag",
          "_us_trading_date_iso = _report_day.isoformat()" in m
          and not [l for l in m.splitlines()
                   if "us_trading_date_iso()" in l and not l.strip().startswith("#")])
    check("Health-Check-Tag = Berichts-Handelstag", "_today_iso = _us_trading_date_iso" in m)
    check("S15-Hook bekommt vintage_guard_log", 'vintage_guard_log_path="vintage_guard_log.jsonl"' in m)
    check("Earnings-Tage ab Berichts-Handelstag",
          "_today_et = _report_day" in m and 'globals()["_REPORT_DAY_ET"] = _report_day' in m
          and "today = _REPORT_DAY_ET or" in GR_SRC)
    check("keine bestehende Cron-Zeile geändert",
          "'17 6 * * 1-5'" in (ROOT / ".github/workflows/daily-squeeze-report.yml").read_text()
          and "'37 21 * * 1-5'" in (ROOT / ".github/workflows/daily-squeeze-report.yml").read_text())


def test_reg_sho_anchor():
    print("9 Reg SHO: NYSE-Abfragetag im Nachtlauf wie abends (D−1)")
    import reg_sho_history as rs
    seen = []

    def nyse(url):
        seen.append(url.split("selectedDate=")[1].split("&")[0])
        return (200, "Symbol|Security Name|Market Category\n", None)

    def nasdaq(url):
        return (404, "", None)
    with tempfile.TemporaryDirectory() as t:
        kw = dict(run_phase="postclose", get_nasdaq_text_fn=nasdaq, get_nyse_text_fn=nyse,
                  hist_path=os.path.join(t, "h.json"), state_path=os.path.join(t, "s.json"))
        uni = [{"ticker": "XX", "exchange": "NYQ"}]
        # Abend Mi 11.11. 22:00 ET → Liste Di 10.11.
        rs.collect_and_persist(uni, report_date_iso="2026-11-11", anchor_date_iso="2026-11-11",
                               now_utc=et(2026, 11, 11, 22, 0).astimezone(timezone.utc), **kw)
        # Nacht Do 12.11. 01:28 ET, Berichtstag Mi → ebenfalls Di 10.11.
        rs.collect_and_persist(uni, report_date_iso="2026-11-11", anchor_date_iso="2026-11-11",
                               now_utc=et(2026, 11, 12, 1, 28).astimezone(timezone.utc), **kw)
        # ohne Anker (alter Weg): Nacht fragt Mi 11.11. ab
        rs.collect_and_persist(uni, report_date_iso="2026-11-11",
                               now_utc=et(2026, 11, 12, 1, 28).astimezone(timezone.utc), **kw)
    check("Abend und Nacht fragen dieselbe Liste (D−1) ab; ohne Anker wie bisher",
          seen[:3] == ["2026-11-10", "2026-11-10", "2026-11-11"], seen)
    check("main() übergibt den Berichts-Handelstag als Anker",
          "anchor_date_iso=_us_trading_date_iso" in GR_SRC)


def test_s15():
    print("8 S15 vintage_guard_log")
    now = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "vg.jsonl")

        def line(ts, reason, rd="12.11.2026", now_et="2026-11-13T00:30:00-05:00"):
            return json.dumps({"ts_utc": ts, "report_date": rd, "bar_date": None,
                               "now_et": now_et, "reason": reason, "ticker_count": 10}) + "\n"
        with open(p, "w") as fh:
            fh.write(line("2026-11-13T05:30:00Z", "pre_open"))
        fails = hc.evaluate_state_invariants(today_iso="2026-11-12", run_phase="postclose",
                                             now_utc=now, vintage_guard_log_path=p)
        s15 = [f for f in fails if f["id"] == "S15"]
        check("pre_open in 26 h → S15 warn", len(s15) == 1 and s15[0]["severity"] == "warn"
              and "pre_open" in s15[0]["detail"] and "00:30 ET" in s15[0]["detail"], s15)
        with open(p, "w") as fh:
            fh.write(line("2026-11-13T05:30:00Z", "holiday_or_prior_bar"))
            fh.write(line("2026-11-10T05:30:00Z", "pre_open"))
            fh.write("kaputt\n")
        fails = hc.evaluate_state_invariants(today_iso="2026-11-12", run_phase="postclose",
                                             now_utc=now, vintage_guard_log_path=p)
        check("erwarteter Skip + alte Zeile + kaputte Zeile → kein S15",
              not [f for f in fails if f["id"] == "S15"], fails)
        fails = hc.evaluate_state_invariants(today_iso="2026-11-12", run_phase="postclose",
                                             now_utc=now, vintage_guard_log_path=os.path.join(t, "nix"))
        check("fehlende Datei → kein S15", not [f for f in fails if f["id"] == "S15"])
        fails = hc.evaluate_state_invariants(today_iso="2026-11-12", run_phase="postclose",
                                             now_utc=now, ki_agent_only=True,
                                             vintage_guard_log_path=p)
        check("ki_agent-Pfad prüft S15 nicht", not [f for f in fails if f["id"] == "S15"])


def main() -> int:
    for fn in (test_report_trading_date, test_determinism, test_resolver, test_guard,
               test_append_end_to_end, test_hand_start, test_wiring, test_reg_sho_anchor, test_s15):
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle Berichtsdatum-Variante-A-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
