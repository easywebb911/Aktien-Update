#!/usr/bin/env python3
"""Mock-Test Options-Sammlung in der Handelszeit (options_intraday.py, 16.11.2026).

Kein Netz (Test-Double statt yfinance). Prüft Lauf-Fenster (Sommer/Winter,
Feiertag, Wochenende), Cron-Slots im Workflow, Top-10-Quelle (letzter Postclose,
Datum als Datum gelesen), Verfallswahl ab Tag 10, Strike-Filter, „leer statt
Abbruch“, Rate-Limit ohne Retry, Zeitlimit, nur Anhängen, Digest-Zeile und
Trennung von der Nachtsammlung.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import options_intraday as O  # noqa: E402

FAILS: list[str] = []
N = 0


def check(name, cond, detail=""):
    global N
    N += 1
    print(("OK  " if cond else "FAIL") + f"  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


U = timezone.utc
SUMMER = date(2026, 7, 15)   # Mi, EDT
WINTER = date(2026, 12, 9)   # Mi, EST


def at(d, hh, mm):
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=U)


# ── 1) Fenster ──────────────────────────────────────────────────────────────
check("01 Sommer 15:07 UTC (11:07 ET) im Fenster", O.run_window_ok(at(SUMMER, 15, 7))[0])
check("02 Winter 15:07 UTC (10:07 ET) im Fenster", O.run_window_ok(at(WINTER, 15, 7))[0])
check("03 Winter 14:50 UTC (09:50 ET) vor Fenster", O.run_window_ok(at(WINTER, 14, 50)) == (False, "vor_fenster"))
check("04 Sommer 19:30 UTC (15:30 ET) nach Fenster", O.run_window_ok(at(SUMMER, 19, 30)) == (False, "nach_fenster"))
check("05 Thanksgiving 26.11.2026 kein Handelstag",
      O.run_window_ok(at(date(2026, 11, 26), 16, 0)) == (False, "kein_handelstag"))
check("06 Samstag kein Handelstag", O.run_window_ok(at(date(2026, 11, 21), 16, 0))[1] == "kein_handelstag")

# ── 2) Cron-Slots im Workflow ───────────────────────────────────────────────
wf = (ROOT / ".github" / "workflows" / "options_intraday.yml").read_text(encoding="utf-8")
import yaml  # noqa: E402
_wfy = yaml.safe_load(wf)
_on = _wfy.get(True) or _wfy.get("on") or {}
_wr = _on.get("workflow_run") or {}
_names = set()
for _f in (ROOT / ".github" / "workflows").glob("*.yml"):
    _n = (yaml.safe_load(_f.read_text(encoding="utf-8")) or {}).get("name")
    if _n:
        _names.add(_n)
check("07 Auslöser workflow_run nach Tageslauf + KI-Lauf, completed, nur main; kein Zeitplan mehr",
      set(_wr.get("workflows") or []) == {"Daily Squeeze Report", "KI-Agent Squeeze Monitor"}
      and _wr.get("types") == ["completed"] and _wr.get("branches") == ["main"]
      and "schedule" not in _on and "workflow_dispatch" in _on, str(_on))
check("08 die genannten Workflow-Namen existieren wirklich (Tippfehler = nie ausgelöst)",
      {"Daily Squeeze Report", "KI-Agent Squeeze Monitor"} <= _names, str(sorted(_names)))
check("08b Auslöser-Werte nur über env, nicht direkt im run-Text (keine Einschleusung)",
      "${{ github.event.workflow_run" not in "\n".join(
          l for l in wf.splitlines() if not l.strip().startswith("AUSLOESER_")))
adds = {a.rstrip(";") for a in re.findall(r"git add (\S+)", wf)}
check("09 Workflow committet nur die zwei eigenen Dateien",
      adds == {"options_intraday_state.json", "options_chain_intraday.jsonl"}, str(adds))
check("10 kein Fehler-Verschlucken im Workflow", "|| true" not in wf and "2>/dev/null" not in wf)

# ── 11) Verkürzte Handelstage (23.11.2026) ─────────────────────────────────
EC = {"2026-11-27": "13:00", "2026-12-24": "13:00"}
check("11 Fensterende an verkürztem Tag = Schluss − 30 min (12:30 ET)",
      O.window_end_et(date(2026, 11, 27), EC) == (12, 30)
      and O.window_end_et(date(2026, 11, 25), EC) == (15, 30))
check("12 27.11.: 12:29 ET (17:29 UTC) im Fenster, 12:30 ET nach_fenster",
      O.run_window_ok(at(date(2026, 11, 27), 17, 29), early_close=EC) == (True, "ok")
      and O.run_window_ok(at(date(2026, 11, 27), 17, 30), early_close=EC) == (False, "nach_fenster"))
check("13 normaler Tag unverändert bis 15:30 ET",
      O.run_window_ok(at(date(2026, 11, 25), 20, 29), early_close=EC)[0]
      and not O.run_window_ok(at(date(2026, 11, 25), 20, 30), early_close=EC)[0])
import config as _cfg  # noqa: E402
check("14 config: 27.11.2026 und 24.12.2026 eingetragen (13:00)",
      _cfg.US_EARLY_CLOSE_DAYS.get("2026-11-27") == "13:00"
      and _cfg.US_EARLY_CLOSE_DAYS.get("2026-12-24") == "13:00")

# ── 15) Warnung nach 3 Handelstagen ohne Messung ───────────────────────────
from datetime import datetime as _dt, timezone as _tz  # noqa: E402


def _utc(y, mo, d, h, mi):
    return _dt(y, mo, d, h, mi, tzinfo=_tz.utc)


# letzte Messung Mi 25.11.; Do 26.11. Feiertag, Fr 27.11. verkürzt (zählt), Mo 30.11., Di 01.12.
check("15 Feiertag zählt nicht: bis Mo 30.11. abends 2 verpasste Tage",
      O.missed_trading_days("2026-11-25", _utc(2026, 12, 1, 2, 0), early_close=EC) == 2)
check("16 heute zählt erst nach Fensterende (Di 01.12. 15:00 UTC = 10:00 ET → noch 2)",
      O.missed_trading_days("2026-11-25", _utc(2026, 12, 1, 15, 0), early_close=EC) == 2)
check("17 nach Fensterende Di 01.12. → 3",
      O.missed_trading_days("2026-11-25", _utc(2026, 12, 1, 21, 0), early_close=EC) == 3)
with tempfile.TemporaryDirectory() as _td:
    _sp = pathlib.Path(_td) / "st.json"
    _sp.write_text(json.dumps({"last_run_date": "2026-11-25"}))
    _w2 = O.warn_lines(_sp, _utc(2026, 12, 1, 2, 0), early_close=EC)
    _w3 = O.warn_lines(_sp, _utc(2026, 12, 1, 21, 0), early_close=EC)
    check("18 Warnzeile erst ab 3 Handelstagen",
          not any("keine Messung" in x for x in _w2)
          and any("seit 3 Handelstagen keine Messung" in x and "25.11." in x for x in _w3), (_w2, _w3))
    check("19 Liste verkürzter Tage veraltet → Warnung (kein Eintrag für 2027)",
          any("veraltet" in x and "2027" in x
              for x in O.warn_lines(_sp, _utc(2027, 1, 5, 21, 0), early_close=EC))
          and not any("veraltet" in x for x in _w3))
    check("20 State fehlt → „noch keine Messung“, kaputt → Warnung statt Stille",
          any("noch keine Messung" in x for x in O.warn_lines(pathlib.Path(_td) / "x.json",
                                                             _utc(2026, 12, 1, 21, 0), early_close=EC)))

# ── 21) Obergrenze: höchstens eine Messung je Handelstag ───────────────────
with tempfile.TemporaryDirectory() as _td:
    (pathlib.Path(_td) / O.STATE_FILE).write_text(json.dumps({"last_run_date": "2026-11-25"}))
    _calls = []
    _st = O.run(now_utc=_utc(2026, 11, 25, 17, 0), root=_td,
                ticker_factory=lambda t: _calls.append(t))
    check("21 zweiter Auslöser am selben Handelstag: kein Abruf, State unverändert",
          _calls == [] and _st.get("last_run_date") == "2026-11-25"
          and not (pathlib.Path(_td) / O.DATA_FILE).exists())
dg = (ROOT / "scripts" / "health_check_digest.py").read_text(encoding="utf-8")
check("22 Digest hängt die Warnzeilen an die Alarmzeilen",
      "options_intraday.warn_lines(" in dg and "list(_oi_warn)" in dg)

# ── 3) Top-10-Quelle ────────────────────────────────────────────────────────
bt = [
    {"date": "30.11.2026", "ticker": "OLD", "pool_position": 1},
    {"date": "01.12.2026", "ticker": "BBB", "pool_position": 2},
    {"date": "01.12.2026", "ticker": "AAA", "pool_position": 1},
    {"date": "01.12.2026", "ticker": "NOP", "pool_position": None},
    {"date": "05.12.2026", "ticker": "BOOT", "pool_position": 1, "source": "bootstrap"},
] + [{"date": "01.12.2026", "ticker": f"T{i:02d}", "pool_position": 3 + i} for i in range(12)]
with tempfile.TemporaryDirectory() as td:
    p = pathlib.Path(td) / "bt.json"
    p.write_text(json.dumps(bt), encoding="utf-8")
    d, tick = O.load_last_postclose_top10(p)
check("11 jüngstes Datum als Datum (01.12. > 30.11.), Bootstrap ignoriert", d == date(2026, 12, 1), str(d))
check("12 nach pool_position sortiert, auf 10 gekappt, ohne Position zuletzt",
      tick[:3] == ["AAA", "BBB", "T00"] and len(tick) == 10 and "NOP" not in tick, str(tick))

# ── 4) Verfallswahl ─────────────────────────────────────────────────────────
tag10 = date(2026, 12, 15)
check("13 erster Verfall >= Tag 10 und der folgende",
      O.pick_expiries(["2026-12-11", "2027-01-15", "2026-12-18", "kaputt", "2026-12-15"], tag10)
      == ["2026-12-15", "2026-12-18"])
check("14 kein Verfall ab Tag 10 → leer", O.pick_expiries(["2026-12-11"], tag10) == [])
check("15 Tag 10 = 10. Handelstag nach D (Kalender inkl. Feiertag)",
      O.trading_date.nth_trading_day_after(date(2026, 11, 20), 10, O.US_MARKET_HOLIDAYS) == date(2026, 12, 7))


# ── 5) Strike-Filter / Rohwerte ─────────────────────────────────────────────
class DF:
    def __init__(self, cols):
        self._c = cols
        self.columns = list(cols)

    def __getitem__(self, k):
        return self._c[k]


nan = float("nan")
df = DF({"strike": [5.0, 10.0, 12.0, 14.0], "bid": [1.0, 0.5, nan, 0.1], "ask": [1.2, 0.6, 0.3, 0.2],
         "lastPrice": [1.1, 0.55, 0.2, 0.15], "volume": [1, nan, 3, 4], "openInterest": [5, 6, 7, 8],
         "impliedVolatility": [0.9, 0.8, 0.7, 0.6], "lastTradeDate": ["2026-12-01T15:00:00+00:00", "NaT", None, "x"]})
rows = O.extract_rows(df, 10.0)
check("16 nur Strikes ±30 % um den Kurs (5 und 14 raus)",
      [r["strike"] for r in rows] == [10.0, 12.0], str([r["strike"] for r in rows]))
check("17 NaN → None, nie 0", rows[1]["bid"] is None and rows[0]["volume"] is None and rows[0]["lastTradeDate"] is None)


# ── 6) Sammeln mit Test-Double ──────────────────────────────────────────────
class Chain:
    def __init__(self, spot, calls, puts):
        self.underlying = {"regularMarketPrice": spot, "regularMarketTime": 1765300000} if spot else {}
        self.calls, self.puts = calls, puts


def mk(bid=1.0, ask=1.1):
    return DF({"strike": [9.0, 10.0, 11.0], "bid": [bid] * 3, "ask": [ask] * 3, "lastPrice": [1.0] * 3,
               "volume": [1] * 3, "openInterest": [1] * 3, "impliedVolatility": [1.0] * 3,
               "lastTradeDate": [None] * 3})


class Tk:
    calls = 0

    def __init__(self, t, mode):
        self.t, self.mode = t, mode
        self.options = ["2026-12-04", "2026-12-18", "2027-01-15", "2027-02-19"]

    def option_chain(self, ex):
        Tk.calls += 1
        if self.mode == "rate":
            raise RuntimeError("Too Many Requests. Rate limited.")
        if self.mode == "nochain":
            raise ValueError("no data")
        if self.mode == "nospot":
            return Chain(None, mk(), mk())
        if self.mode == "zero":
            return Chain(10.0, mk(0.0, 0.0), mk(0.0, 0.0))
        return Chain(10.0, mk(), mk())


now = at(WINTER, 15, 7)
d0, t10 = date(2026, 12, 1), date(2026, 12, 15)
r_ok = O.collect_ticker("AAA", d0, t10, now_utc=now, ticker_factory=lambda t: Tk(t, "ok"))
check("18 zwei Verfälle ab Tag 10 gesammelt, Kurs aus demselben Abruf",
      [e["expiry"] for e in r_ok["expiries"]] == ["2026-12-18", "2027-01-15"] and r_ok["spot"] == 10.0
      and r_ok["spot_source"] == "option_chain.underlying" and r_ok["spot_time_utc"] and r_ok["grund"] is None)
check("19 ATM-Paar vollständig erkannt", O.atm_pair_ok(r_ok["expiries"][0], r_ok["spot"]))
r_zero = O.collect_ticker("Z", d0, t10, now_utc=now, ticker_factory=lambda t: Tk(t, "zero"))
check("20 Geld/Brief 0 → kein vollständiges Paar", not O.atm_pair_ok(r_zero["expiries"][0], r_zero["spot"]))
r_nc = O.collect_ticker("N", d0, t10, now_utc=now, ticker_factory=lambda t: Tk(t, "nochain"))
check("21 Kette fehlt → Zeile mit Grund, kein Abbruch",
      r_nc["grund"] == "kurs_fehlt" and all(e["grund"] == "kette_fehlt" for e in r_nc["expiries"]))
r_ns = O.collect_ticker("S", d0, t10, now_utc=now, ticker_factory=lambda t: Tk(t, "nospot"))
check("22 Kurs fehlt → Grund kurs_fehlt, keine Strikes geraten",
      r_ns["grund"] == "kurs_fehlt" and r_ns["spot"] is None and not r_ns["expiries"][0]["calls"])

# ── 7) Lauf: Anhängen, State, Skip, Rate-Limit, Zeitlimit ───────────────────
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    (root / O.BACKTEST_FILE).write_text(json.dumps(
        [{"date": "01.12.2026", "ticker": t, "pool_position": i + 1} for i, t in enumerate(["A", "B", "C"])]),
        encoding="utf-8")
    (root / O.DATA_FILE).write_text('{"alt": 1}\n', encoding="utf-8")
    st = O.run(now_utc=now, root=root, ticker_factory=lambda t: Tk(t, "ok"), sleep=lambda s: None)
    lines = (root / O.DATA_FILE).read_text(encoding="utf-8").splitlines()
    check("23 nur angehängt (alte Zeile bleibt erste Zeile), 3 neue Zeilen",
          lines[0] == '{"alt": 1}' and len(lines) == 4)
    check("24 State: Kette 3/3, Paar 3/3, Status fertig",
          st["n_with_chain"] == 3 and st["n_pair_ok"] == 3 and st["status"] == "fertig"
          and st["tag10"] == "2026-12-15")
    st2 = O.run(now_utc=now + timedelta(hours=1), root=root, ticker_factory=lambda t: Tk(t, "ok"),
                sleep=lambda s: None)
    check("25 zweiter Slot am selben Tag → kein Abruf, nichts angehängt",
          len((root / O.DATA_FILE).read_text(encoding="utf-8").splitlines()) == 4 and st2 == st)
    check("26 außerhalb des Fensters → kein Abruf",
          O.run(now_utc=at(date(2026, 12, 10), 13, 0), root=root, ticker_factory=lambda t: Tk(t, "ok"),
                sleep=lambda s: None) == st)
    Tk.calls = 0
    st3 = O.run(now_utc=at(date(2026, 12, 10), 15, 7), root=root, ticker_factory=lambda t: Tk(t, "rate"),
                sleep=lambda s: None)
    last = [json.loads(x) for x in (root / O.DATA_FILE).read_text(encoding="utf-8").splitlines()[-3:]]
    check("27 Rate-Limit: genau ein Abrufversuch, kein Retry, Rest mit Grund rate_limit",
          Tk.calls == 1 and [r["grund"] for r in last] == ["rate_limit"] * 3 and st3["status"] == "rate_limit")
    st_rl = O.run(now_utc=at(date(2026, 12, 10), 17, 0), root=root, ticker_factory=lambda t: Tk(t, "ok"),
                  sleep=lambda s: None)
    check("27b späterer Slot nach Rate-Limit am selben Tag holt nicht nach (kein Retry)",
          Tk.calls == 1 and st_rl == st3)
    ticks = iter([0, 0, 10_000, 10_000, 10_000])
    st4 = O.run(now_utc=at(date(2026, 12, 11), 15, 7), root=root, ticker_factory=lambda t: Tk(t, "ok"),
                sleep=lambda s: None, monotonic=lambda: next(ticks))
    last = [json.loads(x) for x in (root / O.DATA_FILE).read_text(encoding="utf-8").splitlines()[-3:]]
    check("28 Zeitlimit: restliche Ticker mit Grund zeitlimit, kein Abbruch",
          last[0]["grund"] is None and [r["grund"] for r in last[1:]] == ["zeitlimit"] * 2
          and st4["status"] == "zeitlimit")
    check("29 Zeilen mit sortierten Schlüsseln (deterministisch)",
          all(list(json.loads(x)) == sorted(json.loads(x))
              for x in (root / O.DATA_FILE).read_text(encoding="utf-8").splitlines()[1:]))
    dl = O.digest_line(root / O.STATE_FILE)
    check("30 Digest-Zeile mit Status bei Abbruch", dl.startswith("🧾 Optionen Handelszeit (11.12.)")
          and "Status zeitlimit" in dl, dl)
    check("30b veraltete Top-10 (Postclose vom 01.12., erwartet 10.12.) gekennzeichnet, nur 3 Ticker",
          st4["top10_aktuell"] is False and st4["erwartet_entry_date"] == "2026-12-10"
          and "Top-10 vom 01.12. (veraltet)" in dl and "nur 3 Ticker" in dl, dl)
    root2 = pathlib.Path(td) / "r2"
    root2.mkdir()
    (root2 / O.BACKTEST_FILE).write_text(json.dumps(
        [{"date": "08.12.2026", "ticker": f"X{i}", "pool_position": i + 1} for i in range(10)]),
        encoding="utf-8")
    st5 = O.run(now_utc=at(WINTER, 15, 7), root=root2, ticker_factory=lambda t: Tk(t, "ok"),
                sleep=lambda s: None)
    dl5 = O.digest_line(root2 / O.STATE_FILE)
    check("30c aktueller Postclose (08.12. für Lauf am 09.12.) → nicht veraltet, kein Zusatz",
          st5["top10_aktuell"] is True and "veraltet" not in dl5 and "nur" not in dl5, dl5)
    check("31 Digest ohne State → noch kein Lauf",
          O.digest_line(root / "fehlt.json") == "🧾 Optionen Handelszeit: noch kein Lauf")

# ── 8) Trennung / kein Netz beim Import ─────────────────────────────────────
src = (ROOT / "options_intraday.py").read_text(encoding="utf-8")
check("32 schreibt nie in options_chain_raw.jsonl", "options_chain_raw" not in src.replace(
      "``options_chain_raw.jsonl``", "").replace("options_chain_raw.jsonl``", ""))
check("33 yfinance nur im echten Lauf importiert", "\nimport yfinance" not in src)
dg = (ROOT / "scripts" / "health_check_digest.py").read_text(encoding="utf-8")
check("34 Digest bindet die Zeile fail-soft ein",
      "options_intraday.digest_line(" in dg and "Options-Handelszeit-Digest unerwartet" in dg)

print()
if FAILS:
    print(f"FEHLER: {len(FAILS)} von {N} Checks rot: {FAILS}")
    sys.exit(1)
print(f"Alle {N} Checks grün.")
