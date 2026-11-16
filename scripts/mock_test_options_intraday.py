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
crons = re.findall(r"cron:\s*'(\d+) (\d+) \* \* 1-5'", wf)
check("07 drei werktägliche Cron-Slots", len(crons) == 3, str(crons))
check("08 jeder Slot in Sommer- UND Winterzeit im Fenster",
      all(O.run_window_ok(at(SUMMER, int(h), int(m)))[0] and O.run_window_ok(at(WINTER, int(h), int(m)))[0]
          for m, h in crons))
adds = {a.rstrip(";") for a in re.findall(r"git add (\S+)", wf)}
check("09 Workflow committet nur die zwei eigenen Dateien",
      adds == {"options_intraday_state.json", "options_chain_intraday.jsonl"}, str(adds))
check("10 kein Fehler-Verschlucken im Workflow", "|| true" not in wf and "2>/dev/null" not in wf)

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
