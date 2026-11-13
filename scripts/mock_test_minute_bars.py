#!/usr/bin/env python3
"""Mock-Test: Minutenkurse Tag 1 (scripts/minute_bars_update.py) + Digest-Zeile.

Ohne Netz, ohne pandas/yfinance (Abrufe injiziert).

 1  Voller Tag: 390 reguläre Minuten, vor-/nachbörslich gekennzeichnet.
 2  Lücke: Minuten ohne Handel bleiben leer (kein Auffüllen).
 3  Prüf-Kennzeichen Hoch/Tief ≤ 0,5 % (ok) / > 0,5 % (ok=False, kein
    Ausschluss) / ohne Tageszeile (ok=None, Grund).
 4  Verpasster Tag: Yahoo liefert nicht mehr → null + ausserhalb_yahoo_fenster;
    Mehrtages-Fenster fällt auf Einzeltage zurück.
 5  Keine Minuten: erst Retry, nach RETRY_DAYS vormerken, null erst wenn ein
    späterer Lauf (anderer ET-Tag) auch leer ist; transient leer → echte Zeile.
 6  Doppel-Lauf überschreibt nichts; neuer Tag hängt ein gzip-Glied an
    (alte Bytes = Präfix, alles lesbar).
 7  Rate-Limit: Abbruch ohne Retry, keine Zeile, Flag im State.
 8  Reife: Tag 1 erst nach endgültigem Close; vor START_DATE nichts.
 9  Determinismus (gleiche Eingabe → gleiche Bytes).
10  Keine Auswertung: Log/State ohne Kurse; kaputte Datei → nichts geschrieben.
11  CI ohne pandas/yfinance.
12  Digest-Zeile: drei Zustände.
13  Workflow + Probe-Dateien entfernt.
"""
from __future__ import annotations

import gzip
import json
import pathlib
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import minute_bars_update as mb  # noqa: E402

_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {str(detail)[:400]}"))
    if not cond:
        _fails.append(name)


D = date(2026, 11, 5)            # Do → Tag 1 = Fr 06.11.
D1 = date(2026, 11, 6)
NOW = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)   # Mo, 09:00 ET → Fr settled


def minute_bars(day, skip=(), pre=0, post=0, hi_bump=0.0):
    out = []
    t0 = datetime(day.year, day.month, day.day, 9, 30, tzinfo=mb.ET)
    for k in range(-pre, 390 + post):
        if k in skip:
            continue
        p = 10 + (k % 7) * 0.01
        out.append({"t": t0 + timedelta(minutes=k), "o": p, "h": p + 0.05 + (hi_bump if k == 200 else 0),
                    "l": p - 0.05, "c": p, "v": 100.0})
    return out


def daily(days):
    # Hoch/Tief passend zu minute_bars ohne bump: max h = 10.06+0.05, min l = 10-0.05
    return [{"d": d, "o": 10.0, "h": 10.11, "l": 9.95, "c": 10.03, "v": 50000} for d in days]


def write_inputs(tmp, entries):
    (tmp / "bh.json").write_text(json.dumps(entries), encoding="utf-8")
    (tmp / "ex.jsonl").write_text("", encoding="utf-8")


def kw(tmp, **extra):
    k = dict(out_dir=tmp / "mb", state_path=tmp / "st.json", backtest_path=tmp / "bh.json",
             export_path=tmp / "ex.jsonl", log=lambda *_: None)
    k.update(extra)
    return k


def read_all(d):
    out = []
    for f in sorted(pathlib.Path(d).glob("*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            out += [json.loads(l) for l in fh if l.strip()]
    return out


def test_record():
    print("1–3 Zeile")
    bars = minute_bars(D1, pre=20, post=10) + minute_bars(D, pre=5)   # D-Balken ignoriert
    r = mb.build_record("AAA", D, bars, "NMS", daily([D, D1]), fetched_utc="x")
    check("Tag 1 = nächster Handelstag", r["tag1"] == "2026-11-06")
    check("390 reg, 20 vor, 10 nach, 0 ohne Handel",
          r["anzahl"] == {"vor": 20, "reg": 390, "nach": 10, "reg_ohne_handel": 0}, r["anzahl"])
    check("Sitzung je Balken gekennzeichnet",
          r["minuten"][0][1] == "vor" and r["minuten"][20][:2] == ["09:30", "reg"]
          and r["minuten"][-1][1] == "nach", r["minuten"][:1])
    check("Tageszeilen D und Tag 1 gespeichert (Einstieg/Schluss aus Tageszeile)",
          r["tageszeile_d"]["c"] == 10.03 and r["tageszeile_tag1"]["c"] == 10.03)
    check("Prüfung ok bei exakter Übereinstimmung",
          r["pruefung"]["ok"] is True and r["pruefung"]["hoch_abw_pct"] == 0.0, r["pruefung"])
    g = mb.build_record("AAA", D, minute_bars(D1, skip={3, 4, 100}), None, daily([D1]), fetched_utc="x")
    check("Lücke: 3 Minuten ohne Handel, nicht aufgefüllt",
          g["anzahl"]["reg"] == 387 and g["anzahl"]["reg_ohne_handel"] == 3
          and "09:33" not in [m[0] for m in g["minuten"]], g["anzahl"])
    b = mb.build_record("AAA", D, minute_bars(D1, hi_bump=0.2), None, daily([D1]), fetched_utc="x")
    check("Hoch 1,8 % daneben → ok=False, Zeile bleibt (kein Ausschluss)",
          b["pruefung"]["ok"] is False and b["grund"] is None and len(b["minuten"]) == 390, b["pruefung"])
    edge = mb.build_record("AAA", D, minute_bars(D1), None,
                           [{"d": D1, "o": 10, "h": 10.11 * 1.005, "l": 9.95, "c": 10, "v": 1}],
                           fetched_utc="x")
    check("genau 0,5 % → ok (Toleranz inklusiv)", edge["pruefung"]["ok"] is True, edge["pruefung"])
    n = mb.build_record("AAA", D, minute_bars(D1), None, [], fetched_utc="x")
    check("ohne Tageszeile → ok=None + Grund", n["pruefung"]["ok"] is None
          and n["pruefung"]["grund"] == "keine_tageszeile", n["pruefung"])
    e = mb.build_record("AAA", D, [], None, daily([D1]), fetched_utc="x")
    check("keine Minuten → null + Grund, nichts erfunden",
          e["grund"] == mb.GRUND_KEINE_MINUTEN and e["minuten"] == []
          and e["anzahl"]["reg_ohne_handel"] is None)
    h = mb.build_record("AAA", D, [dict(minute_bars(D1)[0], c=float("nan"))], None, [], fetched_utc="x")
    check("Halbbalken (NaN) weggelassen", h["minuten"] == [] and h["grund"] == mb.GRUND_KEINE_MINUTEN)


class YFPricesMissingError(Exception):
    pass


class YFRateLimitError(Exception):
    pass


def test_window_and_retry():
    print("4–5 Yahoo-Fenster, Retry")
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        old_d, old_d1 = date(2026, 11, 2), date(2026, 11, 3)
        write_inputs(tmp, [{"ticker": "AAA", "date": old_d.strftime("%d.%m.%Y")},
                           {"ticker": "AAA", "date": D.strftime("%d.%m.%Y")}])
        calls = []

        def mfn(t, s, e):
            calls.append((s, e))
            if s <= old_d1:
                raise YFPricesMissingError(f"$AAA: 1m data not available for startTime=1 (Yahoo error)")
            return minute_bars(D1), "NMS"

        s = mb.run(now_utc=NOW, minute_fn=mfn, daily_fn=lambda t, s, e: daily([old_d, old_d1, D, D1]),
                   **kw(tmp))
        recs = {r["date"]: r for r in read_all(tmp / "mb")}
        check("Mehrtages-Fenster → Einzeltage nachgeholt", len(calls) == 3, calls)
        check("alter Tag → null + ausserhalb_yahoo_fenster",
              recs["02.11.2026"]["grund"] == mb.GRUND_FENSTER and recs["02.11.2026"]["minuten"] == [])
        check("Tag im Fenster gespeichert", recs["05.11.2026"]["anzahl"]["reg"] == 390)
        check("State zählt null nach Grund", s["davon_null_nach_grund"] == {mb.GRUND_FENSTER: 1}, s)

    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        write_inputs(tmp, [{"ticker": "BBB", "date": D.strftime("%d.%m.%Y")}])
        k = kw(tmp, minute_fn=lambda t, s, e: ([], None), daily_fn=lambda t, s, e: daily([D, D1]))
        s = mb.run(now_utc=NOW, **k)
        check("keine Minuten: zuerst Retry, nichts geschrieben",
              s["geschrieben"] == 0 and s["erneut_versuchen"] == 1, s)
        later = NOW + timedelta(days=config.MINUTE_BARS_RETRY_DAYS)
        s = mb.run(now_utc=later, **k)
        check("nach Retry-Fenster erst vorgemerkt, nichts geschrieben",
              s["geschrieben"] == 0 and len(s["leer_vorgemerkt"]) == 1, s)
        s = mb.run(now_utc=later + timedelta(hours=2), **k)
        check("gleicher ET-Tag: weiter nur vorgemerkt", s["geschrieben"] == 0, s)
        s = mb.run(now_utc=later + timedelta(days=1), **k)
        check("späterer Lauf weiter leer → null + Grund",
              s["geschrieben"] == 1 and s["davon_null_nach_grund"] == {mb.GRUND_KEINE_MINUTEN: 1}
              and s["leer_vorgemerkt"] == {}, s)
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        write_inputs(tmp, [{"ticker": "BBB", "date": D.strftime("%d.%m.%Y")}])
        late = NOW + timedelta(days=config.MINUTE_BARS_RETRY_DAYS)
        mb.run(now_utc=late, minute_fn=lambda t, s, e: ([], None),
               daily_fn=lambda t, s, e: daily([D, D1]), **kw(tmp))
        s = mb.run(now_utc=late + timedelta(days=1), minute_fn=lambda t, s, e: (minute_bars(D1), "NMS"),
                   daily_fn=lambda t, s, e: daily([D, D1]), **kw(tmp))
        check("transient leer, dann Daten → echte Zeile statt null",
              s["geschrieben"] == 1 and s["davon_null_nach_grund"] == {}, s)


def test_append_and_double_run():
    print("6/9 Append-only, Doppel-Lauf, Determinismus")
    entries = [{"ticker": "AAA", "date": D.strftime("%d.%m.%Y")},
               {"ticker": "BBB", "date": D.strftime("%d.%m.%Y")}]
    fns = dict(minute_fn=lambda t, s, e: (minute_bars(D1), "NMS"),
               daily_fn=lambda t, s, e: daily([D, D1]))
    blobs = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            write_inputs(tmp, entries)
            mb.run(now_utc=NOW, **fns, **kw(tmp))
            blobs.append((tmp / "mb" / "2026-11-06.jsonl.gz").read_bytes())
            if len(blobs) == 2:
                first = blobs[1]
                s = mb.run(now_utc=NOW + timedelta(hours=3), **fns, **kw(tmp))
                check("Doppel-Lauf: nichts neu, Datei unverändert",
                      s["geschrieben"] == 0 and (tmp / "mb" / "2026-11-06.jsonl.gz").read_bytes() == first, s)
                entries2 = entries + [{"ticker": "CCC", "date": D.strftime("%d.%m.%Y")}]
                write_inputs(tmp, entries2)
                s = mb.run(now_utc=NOW + timedelta(hours=4), **fns, **kw(tmp))
                now_b = (tmp / "mb" / "2026-11-06.jsonl.gz").read_bytes()
                check("neuer Einstieg: gzip-Glied angehängt, alte Bytes = Präfix",
                      s["geschrieben"] == 1 and now_b.startswith(first) and len(now_b) > len(first), s)
                check("mehrgliedrige Datei vollständig lesbar, keine Dublette",
                      sorted(r["ticker"] for r in read_all(tmp / "mb")) == ["AAA", "BBB", "CCC"])
    check("Determinismus: gleiche Eingabe → gleiche Bytes", blobs[0] == blobs[1])


def test_ratelimit_ready():
    print("7–8 Rate-Limit, Reife")
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        write_inputs(tmp, [{"ticker": t, "date": D.strftime("%d.%m.%Y")} for t in ("A1", "B2", "C3", "D4")])
        calls = []

        def rl(t, s, e):
            calls.append(t)
            raise YFRateLimitError("Too Many Requests")

        s = mb.run(now_utc=NOW, minute_fn=lambda t, s, e: (minute_bars(D1), None), daily_fn=rl, **kw(tmp))
        check("Rate-Limit: Abbruch, kein Retry, keine Zeile",
              s["rate_limit_abbruch"] and s["geschrieben"] == 0 and len(calls) <= 2
              and not (tmp / "mb").exists(), (s, calls))
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        write_inputs(tmp, [{"ticker": "AAA", "date": D.strftime("%d.%m.%Y")},
                           {"ticker": "OLD", "date": "01.10.2026"}])
        early = datetime(2026, 11, 6, 23, 0, tzinfo=timezone.utc)   # Fr 18:00 ET → Tag 1 noch offen
        called = []
        s = mb.run(now_utc=early, minute_fn=lambda *a: called.append(a) or ([], None),
                   daily_fn=lambda *a: [], **kw(tmp))
        check("Tag 1 vor endgültigem Close → nicht reif, kein Abruf",
              s["nicht_reif"] == 1 and s["geschrieben"] == 0 and not called, s)
        check("Einstieg vor START_DATE ignoriert", date(2026, 10, 1) < config.MINUTE_BARS_START_DATE)


def test_blind_and_broken():
    print("10 keine Auswertung, kaputte Datei")
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        write_inputs(tmp, [{"ticker": "AAA", "date": D.strftime("%d.%m.%Y")}])
        logs = []
        mb.run(now_utc=NOW, minute_fn=lambda t, s, e: (minute_bars(D1), "NMS"),
               daily_fn=lambda t, s, e: daily([D, D1]), **kw(tmp, log=logs.append))
        txt = "\n".join(logs) + (tmp / "st.json").read_text()
        check("Log/State ohne Kurse", "10.0" not in txt and "9.95" not in txt and "10.11" not in txt, txt)
        f = tmp / "mb" / "2026-11-06.jsonl.gz"
        f.write_bytes(f.read_bytes()[:-5])
        write_inputs(tmp, [{"ticker": "AAA", "date": D.strftime("%d.%m.%Y")},
                           {"ticker": "ZZZ", "date": D.strftime("%d.%m.%Y")}])
        before = f.read_bytes()
        s = mb.run(now_utc=NOW, minute_fn=lambda t, s, e: (minute_bars(D1), "NMS"),
                   daily_fn=lambda t, s, e: daily([D, D1]), **kw(tmp))
        check("kaputte Datei → nichts geschrieben, State meldet es",
              s["geschrieben"] == 0 and s.get("datei_kaputt") and f.read_bytes() == before, s)
    src = (ROOT / "scripts" / "minute_bars_update.py").read_text(encoding="utf-8")
    check("schreibt nie in Bestandsdateien",
          "matured_backtest_export.jsonl\", \"w" not in src and "open(BACKTEST_FILE, \"w" not in src)
    check("CI ohne pandas/yfinance", "pandas" not in sys.modules and "yfinance" not in sys.modules)


def test_digest():
    print("12 Digest-Zeile")
    import health_check as hc
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        line = hc.minute_bars_liveness_line(tmp / "mb", tmp / "st.json", now_ts=NOW)
        check("noch nie gelaufen", "ersten Lauf" in line, line)
        write_inputs(tmp, [{"ticker": "AAA", "date": D.strftime("%d.%m.%Y")}])
        mb.run(now_utc=NOW, minute_fn=lambda t, s, e: (minute_bars(D1), "NMS"),
               daily_fn=lambda t, s, e: daily([D, D1]), **kw(tmp))
        line = hc.minute_bars_liveness_line(tmp / "mb", tmp / "st.json", now_ts=NOW)
        check("läuft · 1 Einstiege · jüngster Tag 1 06.11.2026",
              "läuft · 1 Einstiege · jüngster Tag 1 06.11.2026" in line, line)
        late = NOW + timedelta(days=config.MINUTE_BARS_STALE_DAYS + 1)
        check("überfällig", "überfällig" in hc.minute_bars_liveness_line(
            tmp / "mb", tmp / "st.json", now_ts=late))
        (tmp / "st.json").write_text("{kaputt", encoding="utf-8")
        check("kaputt", "kaputt" in hc.minute_bars_liveness_line(tmp / "mb", tmp / "st.json", now_ts=NOW))
    body = hc.format_digest_body([], [], n_runs=1, last_run_iso=None, digest_date="2026-11-09",
                                 minute_bars_line="🕐 Minutenkurse: läuft")
    check("Zeile im Digest", "🕐 Minutenkurse: läuft" in body[0], body[0][:300])


def test_workflow():
    print("13 Workflow, Probe entfernt")
    wf = (ROOT / ".github" / "workflows" / "minute_bars.yml").read_text(encoding="utf-8")
    check("eigener Cron + Hand-Start, eigene concurrency-Gruppe",
          "cron: '41 13 * * 1-5'" in wf and "workflow_dispatch" in wf and "group: minute-bars" in wf)
    check("committet nur minute_bars/ + State",
          "git add minute_bars_state.json" in wf and "git add minute_bars" in wf
          and "git add -A" not in wf and "git add ." not in wf)
    for p in (".github/workflows/probe_minute_bars.yml", "scripts/probe_minute_bars.py",
              "scripts/mock_test_probe_minute_bars.py"):
        check(f"Probe entfernt: {p}", not (ROOT / p).exists())


def main() -> int:
    for fn in (test_record, test_window_and_retry, test_append_and_double_run,
               test_ratelimit_ready, test_blind_and_broken, test_digest, test_workflow):
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle minute_bars-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
