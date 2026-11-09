"""Mock-Test Wegwerf-Diagnose Nacht-Probe (scripts/diagnose_night_probe.py).

Ohne Netz, ohne pandas/yfinance. Prüft Phase/D-Bestimmung, Zielzeiten,
Ticker-Set, Fehler-Trennung (Rate-Limit → kein Retry), Read-only und die
Verdikt-Regeln (alle Messschritte zählen). Wird im Cleanup-PR mitgelöscht.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import diagnose_night_probe as p  # noqa: E402

_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_time():
    n = utc("2026-11-10T06:30:00").astimezone(p.ET)          # Di 01:30 ET
    check("Phase nacht", p.phase_of(n) == "nacht")
    check("D = Mo 09.11.", p.d_for(n) == date(2026, 11, 9))
    t = utc("2026-11-10T14:47:00").astimezone(p.ET)
    check("Phase tag, D gleich", p.phase_of(t) == "tag" and p.d_for(t) == date(2026, 11, 9))
    e = utc("2026-11-10T04:41:00").astimezone(p.ET)           # Mo 23:41 ET
    check("vor Mitternacht ist nie Nacht", p.phase_of(e) == "tag")
    tg = p.plan_targets(e)
    check("3 Nacht-Ziele am Folgetag", [x.strftime("%m-%d %H:%M") for x in tg] ==
          ["11-10 00:10", "11-10 01:30", "11-10 02:50"], tg)
    late = utc("2026-11-10T07:00:00").astimezone(p.ET)        # 02:00 ET
    check("verspätet: nur noch 02:50", [x.strftime("%H:%M") for x in p.plan_targets(late)] == ["02:50"])
    vlate = utc("2026-11-10T09:00:00").astimezone(p.ET)       # 04:00 ET
    check("nach letztem Ziel: sofort", p.plan_targets(vlate) == [vlate])
    check("Tag-Lauf: sofort eine Messung", p.plan_targets(t, "day") == [t])
    check("Nacht-Lauf 7 h verspätet: sofort", p.plan_targets(t, "night") == [t])
    sat = utc("2026-11-14T06:30:00").astimezone(p.ET)
    check("Sa-Nacht D = Fr", p.d_for(sat) == date(2026, 11, 13))
    tday = utc("2026-11-27T06:30:00").astimezone(p.ET)        # Fr nach Thanksgiving
    check("Feiertag übersprungen", p.d_for(tday) == date(2026, 11, 25))


def _rows(D, n=30, half=False, bump=0.0):
    out = []
    import datetime as _dt
    d = D - _dt.timedelta(days=n * 2)
    i = 0
    while d <= D:
        if p.is_trading_day(d):
            c = 10 + i * 0.1
            out.append({"d": d.isoformat(), "o": c, "h": c + 1, "l": c - 1, "c": c, "v": 1000 + i})
            i += 1
        d += _dt.timedelta(days=1)
    if half:
        out[-1].update(c=None, h=None, l=None, o=None)
    if bump:
        out[-1]["c"] *= 1 + bump
    return out


def _fetchers(D, half=(), rl=None, calls=None):
    calls = calls if calls is not None else []

    def batch(ts):
        return {t: _rows(D, half=t in half) for t in ts}, {}

    def single(t):
        calls.append(t)
        if rl and t == rl:
            raise type("YFRateLimitError", (Exception,), {})("Too Many Requests")
        return _rows(D)

    def info(t):
        return {"regularMarketPrice": _rows(D)[-1]["c"],
                "regularMarketTime": datetime(D.year, D.month, D.day, 21, tzinfo=timezone.utc).timestamp()}

    def chain(t, pref, X):
        return {"expiry": "2026-11-13", "calls": {"5.0": 10}, "puts": {"5.0": 20}}
    return {"batch": batch, "single": single, "info": info, "chain": chain}


def _root(D):
    td = pathlib.Path(tempfile.mkdtemp())
    bh = [{"date": D.strftime("%d.%m.%Y"), "ticker": t, "entry_price": round(_rows(D)[-1]["c"], 4),
           "rvol": round(_rows(D)[-1]["v"] / (sum(r["v"] for r in _rows(D)[-20:]) / 20), 3),
           "entry_past_return_5d": round((_rows(D)[-1]["c"] / _rows(D)[-6]["c"] - 1) * 100, 2)}
          for t in ("AAA", "BBB")]
    bh.append({"date": D.strftime("%d.%m.%Y"), "ticker": "ZZZ", "source": "bootstrap"})
    (td / "backtest_history.json").write_text(json.dumps(bh))
    chain = {"date": D.isoformat(), "ticker": "AAA", "expiries": [{"expiry": "2026-11-13",
             "calls": [{"strike": 5.0, "openInterest": 10}], "puts": [{"strike": 5.0, "openInterest": 20}]}]}
    (td / "options_chain_raw.jsonl").write_text(json.dumps(chain) + "\n")
    return td


def _m(when, D, **kw):
    root = _root(D)
    return p.measure(utc(when), _fetchers(D, **kw), root=root, sleep=lambda s: None), root


def test_measure_and_readonly():
    D = date(2026, 11, 9)
    m, root = _m("2026-11-10T06:30:00", D)
    check("Ticker-Set Top-10 + SPY + illiquide, ohne Bootstrap",
          m["meta"]["tickers"] == ["AAA", "BBB", "SPY", "SDHC", "CURV", "TTEC"], m["meta"]["tickers"])
    check("Prod-Chain gelesen", m["records"][0]["prod"]["chain"]["calls"] == {"5.0": 10})
    files = sorted(x.name for x in root.iterdir())
    check("nichts ins Repo geschrieben", files == ["backtest_history.json", "options_chain_raw.jsonl"], files)
    calls = []
    m2, _ = _m("2026-11-10T06:30:00", D, rl="BBB", calls=calls)
    check("Rate-Limit: kein Retry", calls.count("BBB") == 1, calls)
    check("nach Rate-Limit kein Abruf mehr", "SPY" not in calls, calls)
    check("Rate-Limit markiert", m2["meta"]["rate_limit_abbruch"] is True)
    src = (ROOT / "scripts" / "diagnose_night_probe.py").read_text(encoding="utf-8")
    writes = re.findall(r"(write_text|open\([^)]*['\"]w['\"])", src)
    check("einziger Schreibpfad = out_dir (RUNNER_TEMP)", writes == ["write_text"], writes)


def test_verdicts():
    D1, D2 = date(2026, 11, 9), date(2026, 11, 10)
    ms = []
    for D, nt, tt in ((D1, "2026-11-10T06:30:00", "2026-11-10T14:47:00"),
                      (D2, "2026-11-11T06:30:00", "2026-11-11T14:47:00")):
        ms += [_m(nt, D)[0], _m(tt, D)[0]]
    r = p.evaluate(ms)
    check("alles final → F1 JA", r["verdikte"]["F1_zeile"] == "JA", r["verdikte"])
    check("F1-info JA", r["verdikte"]["F1_info"] == "JA", r["f1_info"][:2])
    check("F2 JA (6 Paare je Nacht)", r["verdikte"]["F2_oi"] == "JA", r["verdikte"])
    check("F3 JA", r["verdikte"]["F3_produktion"] == "JA", r["f3"][:2])
    check("OI unverändert gezählt", r["f2_zeitpunkt"]["unverändert"] >= 1, r["f2_zeitpunkt"])
    # Halbzeile nachts → NEIN
    ms2 = [_m("2026-11-10T06:30:00", D1, half=("AAA",))[0], ms[1], ms[2], ms[3]]
    r2 = p.evaluate(ms2)
    check("Halbzeile → F1 NEIN", r2["verdikte"]["F1_zeile"] == "NEIN")
    check("Halbzeile → F3 nicht gleich", r2["verdikte"]["F3_produktion"] in ("NEIN", "UNBESTIMMT"))
    # nur eine Nacht → UNBESTIMMT (nicht JA)
    r3 = p.evaluate(ms[:2])
    check("nur 1 D → UNBESTIMMT", r3["verdikte"]["F1_zeile"] == "UNBESTIMMT", r3["verdikte"])
    # Abend-Messung zählt nicht
    ev = _m("2026-11-10T04:41:00", D1)[0]
    check("Abend-Messung zählt nicht als Nacht", p.evaluate([ev, ms[1]])["n_nacht_messungen"] == 0)
    # Rate-Limit nachts → unbestimmt, nicht NEIN
    rl = _m("2026-11-10T06:30:00", D1)[0]
    for rec in rl["records"]:
        rec["batch"], rec["batch_err"], rec["single"] = [], "rate_limit:X", None
    r4 = p.evaluate([rl, ms[1], ms[2], ms[3]])
    check("Flakiness → kein NEIN", r4["verdikte"]["F1_zeile"] != "NEIN", r4["verdikte"])
    # Volumen 0 in Nacht und Tag → final (kein falsches NEIN)
    z1, z2 = _m("2026-11-10T06:30:00", D1)[0], _m("2026-11-10T14:47:00", D1)[0]
    for mm in (z1, z2):
        for rec in mm["records"]:
            for key in ("batch", "single"):
                rec[key][-1]["v"] = 0.0
    r5 = p.evaluate([z1, z2, ms[2], ms[3]])
    check("Volumen 0 beidseitig → kein NEIN", r5["verdikte"]["F1_zeile"] == "JA", r5["f1"][:1])
    # Nachadjustierung (Dividende nach D) → unbestimmt statt NEIN
    a1, a2 = _m("2026-11-10T06:30:00", D1)[0], _m("2026-11-10T14:47:00", D1)[0]
    for rec in a2["records"]:
        for key in ("batch", "single"):
            rec[key][-1]["c"] *= 0.98
        rec["single"].append({"d": "2026-11-10", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1,
                              "action": {"div": 0.1, "split": None}})
    r6 = p.evaluate([a1, a2, ms[2], ms[3]])
    check("Dividende nach D → kein NEIN", r6["verdikte"]["F1_zeile"] != "NEIN", r6["f1"][:1])
    check("Klasse neu_adjustiert sichtbar", "neu_adjustiert" in r6["f1"][0]["detail"], r6["f1"][0])
    # rvol: NaN-Volumen im Fenster wird übersprungen (wie pandas)
    rows = _rows(D1)
    rows[-3]["v"] = None
    check("rvol überspringt NaN-Volumen", p._rvol_at(rows, D1.isoformat()) is not None)
    # Log-Parser = Artifact-Inhalt
    with tempfile.TemporaryDirectory() as td:
        lp = pathlib.Path(td) / "log.txt"
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            for m in ms:
                p.emit(m, None)
        lp.write_text("2026-11-10T06:30:01Z " + buf.getvalue().replace("\n", "\n2026Z "))
        back = p.load_measurements([lp])
        check("Job-Log rücklesbar (4 Messungen)", len(back) == 4 and
              p.evaluate(back)["verdikte"] == r["verdikte"], len(back))
        hl = pathlib.Path(td) / "daily.txt"
        hl.write_text("x [halfrow_probe] ticker=AAA row_date=2026-11-09 row_volume=None\n")
        check("halfrow-Zeilen geparst", p.parse_halfrow([hl]) == {"2026-11-09": {"AAA"}})


def test_workflow():
    wf = (ROOT / ".github" / "workflows" / "diagnose_night_probe.yml").read_text(encoding="utf-8")
    check("permissions nur contents: read", "contents: read" in wf and "write" not in wf.split("permissions:")[1].split("concurrency")[0])
    check("keine Secrets", "secrets." not in wf)
    check("kein git push/commit", "git push" not in wf and "git commit" not in wf)
    check("Zeitplan Nacht + Tag", "'41 4 * * 2-6'" in wf and "'47 14 * * 2-6'" in wf)


def run_all() -> int:
    for t in (test_time, test_measure_and_readonly, test_verdicts, test_workflow):
        print(t.__name__)
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Nacht-Probe-Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle Nacht-Probe-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
