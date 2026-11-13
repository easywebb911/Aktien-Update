#!/usr/bin/env python3
"""Tests für scripts/probe_quote_spread.py — nur synthetische Daten, kein Netz."""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import probe_quote_spread as pq  # noqa: E402

_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


NOW = datetime(2026, 11, 16, 14, 40, tzinfo=timezone.utc)   # Mo 09:40 ET


def test_assess():
    a = pq.assess({"bid": 9.9, "ask": 10.1, "regularMarketPrice": 10.0, "regularMarketTime": NOW.timestamp() - 30}, NOW)
    check("Spanne 2 %", abs(a["spread_pct"] - 2.0) < 1e-9 and a["grund"] is None, a)
    check("letzter Kurs im Quote", a["last_in_quote"] is True)
    check("Alter 30 s", a["quote_age_s"] == 30.0, a["quote_age_s"])
    check("Geld fehlt → null + Grund", pq.assess({"ask": 1.0}, NOW)["grund"] == "geld_oder_brief_fehlt")
    check("Geld 0 → null + Grund (unbekannt ≠ 0)", pq.assess({"bid": 0, "ask": 1.0}, NOW)["grund"] == "geld_oder_brief_null")
    b = pq.assess({"bid": 1.1, "ask": 1.0}, NOW)
    check("Brief ≤ Geld → null + Grund", b["grund"] == "brief_nicht_ueber_geld" and b["spread_pct"] is None)
    check("NaN → fehlt", pq.assess({"bid": float("nan"), "ask": 1.0}, NOW)["grund"] == "geld_oder_brief_fehlt")


def test_measure():
    bh = [{"date": "13.11.2026", "ticker": "AAA", "source": "daily"},
          {"date": "13.11.2026", "ticker": "BBB"},
          {"date": "13.11.2026", "ticker": "ZZZ", "source": "bootstrap"},
          {"date": "12.11.2026", "ticker": "OLD"}]
    calls = []

    def fake(t):
        calls.append(t)
        if t == "BBB":
            raise RuntimeError("boom")
        return {"bid": 1.0, "ask": 1.02, "regularMarketPrice": 1.01, "exchangeDataDelayedBy": 0, "extra": 1}
    m = pq.measure(NOW, fetch=fake, bh=bh)
    check("D = Freitag 13.11. (Montag-Messung)", m["meta"]["D"] == "2026-11-13", m["meta"]["D"])
    check("Ticker: Top-10 von D ohne Bootstrap + Extras",
          m["meta"]["tickers"] == ["AAA", "BBB", "SPY", "SDHC", "CURV", "TTEC"], m["meta"]["tickers"])
    check("Minuten nach Eröffnung = 10", m["meta"]["min_nach_eroeffnung"] == 10.0, m["meta"]["min_nach_eroeffnung"])
    check("in Handelszeit (Mo 09:40 ET)", m["meta"]["in_handelszeit"] is True)
    late = pq.measure(datetime(2026, 11, 16, 21, 5, tzinfo=timezone.utc), fetch=fake, bh=bh)
    check("nach Schluss (16:05 ET) zählt nicht", late["meta"]["in_handelszeit"] is False)
    sat = pq.measure(datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc), fetch=fake, bh=bh)
    check("Samstag zählt nicht", sat["meta"]["in_handelszeit"] is False)
    rb = [r for r in m["records"] if r["ticker"] == "BBB"][0]
    check("Fehler je Ticker fail-soft", rb["fehler"] and rb["grund"] == "geld_oder_brief_fehlt", rb)
    check("nur INFO_KEYS gespeichert", "extra" not in m["records"][0]["info"])
    s = pq.summary(m)
    check("Zusammenfassung", s["n"] == 6 and s["mit_spanne"] == 5 and s["fehler"] == 1, s)
    m2 = pq.measure(NOW, fetch=fake, bh=[{"date": "12.11.2026", "ticker": "OLD"}])
    check("fehlt D → jüngster Tag davor", m2["meta"]["top10_quelle"] == "2026-11-12" and m2["meta"]["tickers"][0] == "OLD")


def test_main_writes_only_out():
    with tempfile.TemporaryDirectory() as t:
        orig = pq.measure
        pq.measure = lambda now, **k: {"meta": {"run_utc": "2026-11-16T14:40:00+00:00"}, "records": []}
        try:
            rc = pq.main(["--out", t])
        finally:
            pq.measure = orig
        files = list(pathlib.Path(t).iterdir())
        check("main schreibt genau eine Datei nach --out", rc == 0 and len(files) == 1, files)
        check("Datei ist JSON", isinstance(json.loads(files[0].read_text()), dict))
    src = (ROOT / "scripts" / "probe_quote_spread.py").read_text(encoding="utf-8")
    check("schreibt keine Repo-Datei", "open(ROOT" not in src.replace('open(ROOT / config.BACKTEST_FILE, encoding="utf-8")', ""))
    wf = (ROOT / ".github" / "workflows" / "probe_quote_spread.yml").read_text(encoding="utf-8")
    check("Workflow: nur Hand-Start, nur lesen", "workflow_dispatch" in wf and "schedule" not in wf
          and "contents: read" in wf and "git push" not in wf and "secrets." not in wf)


def main() -> int:
    for fn in (test_assess, test_measure, test_main_writes_only_out):
        print(fn.__name__)
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle probe_quote_spread-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
