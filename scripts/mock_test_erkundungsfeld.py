#!/usr/bin/env python3
"""Mock-Test: Erkundungsfeld Stufe 1 (PR B, 17.11.2026). Kein Netz, kein pandas.

Belegt u. a.: Kalender (09.01.2025 Sonderschließung), Veröffentlichungsregel
(+7 Handelstage, nutzbar ab dem Handelstag danach), Merkmale für Tag t nur aus
Zeilen <= t (Kürzungstest), harte Kurs-Obergrenzen, unveränderte score(),
Namensvergleich + Schwelle, Determinismus, kein Konsument im Tool.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import random
import sys
import tempfile
import types
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "golden_harness_ef", ROOT / "scripts" / "mock_test_outer_page_golden.py")
golden = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(golden)
gr = golden.gr
import erkundungsfeld as ef  # noqa: E402

FAILS: list[str] = []


def check(name, cond, detail=""):
    print(("OK  " if cond else "FAIL") + f"  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# ── Kalender + Veröffentlichung ─────────────────────────────────────────────
check("01 09.01.2025 kein Handelstag (Sonderschließung nur im Feld)",
      not ef.is_trading_day(date(2025, 1, 9)) and "2025-01-09" not in __import__("config").US_MARKET_HOLIDAYS)
check("02 03.07.2026 kein Handelstag, 02.07. ja", not ef.is_trading_day(date(2026, 7, 3))
      and ef.is_trading_day(date(2026, 7, 2)))
check("03 Stichtag 31.12.2024 → veröffentlicht 13.01.2025, nutzbar ab 14.01.2025",
      ef.publication_date(date(2024, 12, 31)) == date(2025, 1, 13)
      and ef.usable_from(date(2024, 12, 31)) == date(2025, 1, 14),
      (ef.publication_date(date(2024, 12, 31)), ef.usable_from(date(2024, 12, 31))))
days = ef.trading_days(ef.FIELD_START, ef.FIELD_END)
check("04 Feld-Handelstage: Start 02.01.2025, Ende 02.07.2026, ~375",
      days[0] == date(2025, 1, 2) and days[-1] == date(2026, 7, 2) and 360 <= len(days) <= 385, len(days))

# ── FINRA ───────────────────────────────────────────────────────────────────
raw = [
    {"symbolCode": "AAA", "settlementDate": "2025-01-15", "currentShortPositionQuantity": 500000,
     "daysToCoverQuantity": 4.2, "averageDailyVolumeQuantity": 120000, "marketClassCode": "NNM", "stockSplitFlag": None},
    {"symbolCode": "BBB.W", "settlementDate": "2025-01-15", "currentShortPositionQuantity": 1, "marketClassCode": "NNM"},
    {"symbolCode": "OTCX", "settlementDate": "2025-01-15", "currentShortPositionQuantity": 9, "marketClassCode": "u"},
    {"issueSymbolIdentifier": "CCC", "settlementDate": "2025-01-15", "currentShortShareNumber": 7,
     "marketClassCode": "NYSE", "stockSplitFlag": "S"},
]
n = ef.normalize_finra(raw)
check("05 nur gelistete Stammaktien, Feld-Aliasse, Split-Kennzeichen",
      sorted(n) == ["AAA", "CCC"] and n["AAA"]["qty"] == 500000 and n["AAA"]["dtc"] == 4.2
      and n["CCC"]["split"] == "S", n)
check("06 Feldprobe: ok mit Feldern, nicht ok ohne", ef.finra_fields_ok(raw)
      and not ef.finra_fields_ok([{"x": 1}]) and not ef.finra_fields_ok([]))
finra = {date(2025, 1, 15): {"AAA": {"qty": 100, "dtc": 3.0, "adv": None, "split": None}},
         date(2025, 1, 31): {"AAA": {"qty": 120, "dtc": 3.5, "adv": None, "split": None}}}
uf_31 = ef.usable_from(date(2025, 1, 31))
cur, prev = ef.usable_records(finra, "AAA", uf_31 - timedelta(days=1))
check("07 vor Nutzbar-ab gilt der ältere Stichtag", cur[0] == date(2025, 1, 15) and prev is None)
cur, prev = ef.usable_records(finra, "AAA", uf_31)
check("08 ab Nutzbar-ab gilt der neue, Trend aus zwei Ständen (+20 % → up)",
      cur[0] == date(2025, 1, 31) and prev[0] == date(2025, 1, 15) and ef.si_trend(cur, prev) == "up")
check("09 SEC-Aktienzahl erst Periodenende + 90 Tage",
      ef.sec_shares_known({1: [(date(2025, 3, 31), 1e6)]}, 1, date(2025, 6, 28)) is None
      and ef.sec_shares_known({1: [(date(2025, 3, 31), 1e6)]}, 1, date(2025, 6, 29)) == 1e6)

# ── Merkmale: nur Zeilen <= t ───────────────────────────────────────────────
rng = random.Random(20261117)
bars, px, d = [], 5.0, date(2024, 11, 15)
while d <= date(2025, 6, 30):
    if ef.is_trading_day(d):
        o = px * (1 + rng.uniform(-0.05, 0.05))
        c = o * (1 + rng.uniform(-0.1, 0.12))
        bars.append((d, o, max(o, c) * 1.02, min(o, c) * 0.98, c, rng.randint(100_000, 3_000_000)))
        px = c
    d += timedelta(days=1)
tests = [b[0] for b in bars[30:]]
same = all(ef.features_at(bars, t) == ef.features_at([b for b in bars if b[0] <= t], t) for t in tests)
check("10 Kürzungstest: Merkmale für t mit/ohne spätere Zeilen identisch", same)
fut = list(bars)
fut[-1] = (fut[-1][0], 999.0, 999.0, 999.0, 999.0, 10**9)
t_mid = tests[50]
check("11 Änderung an späteren Zeilen ändert Tag t nicht",
      ef.features_at(bars, t_mid) == ef.features_at(fut, t_mid))
check("12 Tag ohne Zeile / zu wenig Historie → None",
      ef.features_at(bars, date(2025, 1, 4)) is None and ef.features_at(bars, bars[5][0]) is None)
spx = [(b[0], 100, 101, 99, 100 + i * 0.1, 10**9) for i, b in enumerate(bars)]
f = ef.features_at(bars, t_mid)
sf = ef.features_at(spx, t_mid)
st = ef.build_stock("AAA", f, sf, (date(2025, 1, 15), {"qty": 300000, "dtc": 6.0, "adv": None, "split": None}),
                    None, 1_000_000, 2_000_000)
check("13 Short Float = FINRA-Bestand / Float heute (30 %), Marktkap = Kurs × Aktienzahl heute",
      abs(st["short_float"] - 30.0) < 1e-9 and abs(st["_mcap"] - f["price"] * 2_000_000) < 1e-6)
score_val = gr.score(st)
check("14 unveränderte generate_report.score() nimmt das Dict an (endlich, 0..100)",
      0.0 <= score_val <= 100.0, score_val)
check("15 Filter: Preis, SI, Marktkap, Ø-Volumen — rvol seit 17.11.2026 kein harter Filter",
      ef.passes_filter(dict(st, price=2, rel_volume=2, _sf=20, _mcap=1e8), 400_000)
      and not ef.passes_filter(dict(st, price=0.9, rel_volume=2, _sf=20, _mcap=1e8), 400_000)
      and ef.passes_filter(dict(st, price=2, rel_volume=1.4, _sf=20, _mcap=1e8), 400_000)
      and ef.filter_failures(dict(st, price=2, rel_volume=0.5, _sf=20, _mcap=1e8), 400_000) == []
      and not ef.passes_filter(dict(st, price=2, rel_volume=2, _sf=14.9, _mcap=1e8), 400_000)
      and not ef.passes_filter(dict(st, price=2, rel_volume=2, _sf=20, _mcap=2e9), 400_000)
      and not ef.passes_filter(dict(st, price=2, rel_volume=2, _sf=20, _mcap=1e8), 299_999))

# ── Rangliste ───────────────────────────────────────────────────────────────
bars_map = {}
fin2 = {date(2024, 12, 31): {}}
for i in range(40):
    sym = f"T{i:02d}"
    b2 = [(b[0], b[1], b[2], b[3], b[4], b[5] * (3 if b[0] == t_mid else 1)) for b in bars]
    bars_map[sym] = b2
    fin2[date(2024, 12, 31)][sym] = {"qty": 200000 + i * 1000, "dtc": 2 + i * 0.1, "adv": None, "split": None}
fin2[date(2024, 12, 31)]["NOPX"] = {"qty": 1, "dtc": 1, "adv": None, "split": None}
fmap = {s: (1_000_000, 1_500_000) for s in bars_map}
lst, ohne = ef.rank_day(t_mid, set(bars_map) | {"NOPX"}, bars_map, sf, fin2, fmap, gr.score)
lst2, _ = ef.rank_day(t_mid, set(bars_map) | {"NOPX"}, bars_map, sf, fin2, fmap, gr.score)
check("16 höchstens 30 Namen, Rang 1..n, Score absteigend",
      0 < len(lst) <= 30 and [r for r, *_ in lst] == list(range(1, len(lst) + 1))
      and all(lst[i][2] >= lst[i + 1][2] for i in range(len(lst) - 1)), len(lst))
check("17 deterministisch (zweimal gleich)", lst == lst2)
check("18 Kandidat ohne Kurse zählt als Lücke", ohne == ["NOPX"])
lk = {}
pre = {(date(2024, 12, 31), "T00")}
lst_p, _ = ef.rank_day(t_mid, set(bars_map), bars_map, sf, fin2, fmap, gr.score, prefilter_ok=pre,
                       splits={"T00": [t_mid + timedelta(days=3)]}, cap=ef.FIELD_END, luecken=lk)
check("18b Vorfilter je Tag: nur (Stichtag, Ticker) mit bestandenem Vorfilter",
      [s for _, s, *_ in lst_p] == ["T00"], lst_p)
check("18c Split nach dem Tag und seit dem Stichtag gekennzeichnet",
      lst_p[0][3]["split_nach_tag"] is True and lst_p[0][3]["split_seit_stichtag"] is True)
fmap2 = dict(fmap)
fmap2.pop("T01")
ef.rank_day(t_mid, {"T01"}, bars_map, sf, fin2, fmap2, gr.score, luecken=lk)
check("18d Kurs da, Float fehlt → Lücke ohne_float", lk.get("ohne_float") == 1, lk)
check("19 Merkmale tragen Kennzeichen „Nenner heutig“ und Stichtag",
      all(m["kennz"] == "Nenner heutig" and m["si_stichtag"] == "2024-12-31" for *_, m in lst))

# ── Namensvergleich + Schwelle ──────────────────────────────────────────────
d1, d2 = date(2026, 7, 21), date(2026, 7, 22)
lists = {d1: [(i + 1, f"N{i}", 0, {}) for i in range(30)], d2: [(i + 1, f"M{i}", 0, {}) for i in range(30)]}
real = {d1: [f"N{i}" for i in (0, 5, 15, 25, 29)] + ["X1", "X2", "X3", "X4", "X5"], d2: ["Z"] * 10}
c = ef.compare(lists, real)
check("20 Treffer je Tag in 10/20/30", c["je_tag"][0]["top10"] == 2 and c["je_tag"][0]["top20"] == 3
      and c["je_tag"][0]["top30"] == 5 and c["je_tag"][1]["top30"] == 0, c["je_tag"])
check("21 Median + Verteilung", c["top30"]["median"] == 2.5 and c["top30"]["verteilung"]["5"] == 1)
check("22 Schwelle: >=5 bestanden, 3–4 Grenzfall, <3 nicht weiterbauen",
      ef.verdict(5) == "bestanden" and ef.verdict(4) == "grenzfall" and ef.verdict(3) == "grenzfall"
      and ef.verdict(2.5) == "nicht_weiterbauen" and ef.verdict(None) == "nicht_messbar"
      and ef.verdict(7, vollstaendig=False) == "unvollstaendig")
with tempfile.TemporaryDirectory() as td:
    p = pathlib.Path(td) / "exp.jsonl"
    rows = [{"date": "21.07.2026", "ticker": f"R{i}", "pool_position": 11 - i, "provenance": "forward"} for i in range(11)]
    rows += [{"date": "20.07.2026", "ticker": "OLD", "pool_position": 1, "provenance": "forward"},
             {"date": "21.07.2026", "ticker": "BOOT", "pool_position": 1, "provenance": "bootstrap"}]
    p.write_text("\n".join(json.dumps(r) for r in rows))
    rt = ef.real_top10(p, ef.WIN_START, ef.WIN_END)
    check("23 echte Top-10: nur forward, nur Fenster, nach pool_position, max 10",
          list(rt) == [date(2026, 7, 21)] and len(rt[date(2026, 7, 21)]) == 10
          and rt[date(2026, 7, 21)][0] == "R10" and "BOOT" not in rt[date(2026, 7, 21)])
    g = pathlib.Path(td) / "a.jsonl.gz"
    ef.write_gz_jsonl(g, [{"b": 1, "a": 2}])
    b1 = g.read_bytes()
    ef.write_gz_jsonl(g, [{"b": 1, "a": 2}])
    check("24 gzip deterministisch (mtime 0, sortierte Schlüssel)", b1 == g.read_bytes())

# ── Kurs-Obergrenzen ────────────────────────────────────────────────────────
try:
    ef.fetch_bars({"X"}, ef.WIN_FETCH_START, date(2026, 10, 24), ef.WIN_END)
    ok = False
except ValueError:
    ok = True
check("25 Abruf über die Obergrenze → Abbruch", ok)
calls = []


class _Idx:
    def __init__(self, d): self._d = d
    def date(self): return self._d


class _Sub:
    def __init__(self, rows): self.rows = rows
    def dropna(self, subset=None): return _Sub([r for r in self.rows if r[1].get("Close") is not None])
    def iterrows(self): return iter(self.rows)


class _Cols:
    nlevels = 2
    def __init__(self, syms): self.syms = syms
    def get_level_values(self, i): return list(self.syms)


class _DF:
    def __init__(self, rows, syms): self.rows, self.columns = rows, _Cols(syms)
    def __getitem__(self, k): return _Sub(self.rows)


def _dl(batch, start, end, **kw):
    calls.append((tuple(batch), start, end))
    rows = [(_Idx(date(2026, 7, 1)), {"Open": 1, "High": 1, "Low": 1, "Close": 1, "Volume": 1}),
            (_Idx(date(2026, 7, 2)), {"Open": 1, "High": 1, "Low": 1, "Close": 2, "Volume": 1}),
            (_Idx(date(2026, 7, 6)), {"Open": 9, "High": 9, "Low": 9, "Close": 9, "Volume": 9})]
    rows[1][1]["Stock Splits"] = 0.25
    return _DF(rows, batch)


_shared = types.SimpleNamespace(_ERRORS={})
sys.modules["yfinance"] = types.SimpleNamespace(download=_dl, shared=_shared)
_sleep = ef.time.sleep
ef.time.sleep = lambda s: None
spl = {}
try:
    out, miss = ef.fetch_bars({"A", "B"}, ef.FIELD_FETCH_START, ef.FIELD_END, ef.FIELD_END, splits_out=spl)
    one, miss1 = ef.fetch_bars({"Z"}, ef.FIELD_FETCH_START, ef.FIELD_END, ef.FIELD_END)

    def _dl_rl(batch, start, end, **kw):
        _shared._ERRORS.update({b: "YFRateLimitError('Too Many Requests')" for b in batch})
        return _DF([], [])
    sys.modules["yfinance"].download = _dl_rl
    ef.STOPS.clear()
    rl, miss_rl = ef.fetch_bars({"Q1", "Q2"}, ef.FIELD_FETCH_START, ef.FIELD_END, ef.FIELD_END)
finally:
    ef.time.sleep = _sleep
check("26 Abruf endet am 02.07.2026 (end exklusiv 03.07.), spätere Zeilen verworfen",
      calls and calls[0][2] == "2026-07-03" and all(r[0] <= ef.FIELD_END for r in out["A"])
      and miss == [], calls)
src = (ROOT / "scripts" / "erkundungsfeld.py").read_text(encoding="utf-8")
check("26b einzelner Ticker mit MultiIndex wird gelesen, Split-Tage erfasst",
      "Z" in one and miss1 == [] and spl.get("A") == [date(2026, 7, 2)], (miss1, spl))
check("26c gemeldetes Rate-Limit (shared._ERRORS) → kein Retry, Lücke, Abbruchgrund",
      rl == {} and miss_rl == ["Q1", "Q2"] and "rate_limit_kurse" in ef.STOPS)
check("27 main nutzt die Obergrenzen 02.07. (Feld) und 23.10. (Vergleich)",
      "fetch_bars(field_t | {\"^GSPC\"}, FIELD_FETCH_START, FIELD_END, FIELD_END" in src
      and "fetch_bars(win_t | {\"^GSPC\"}, WIN_FETCH_START, WIN_END, WIN_END" in src)
check("28 Vergleichsfenster speichert nur Namen + Rang (keine Merkmale/Kurse)",
      '{"date": t.isoformat(), "rang": r, "ticker": s}' in src)
check("29 keine Rendite/Treffer-Rechnung (kein return_/max_gain/outcome_path im Modul)",
      not any(k in src for k in ("return_10d", "max_gain", "outcome_path", "forward_")))

# ── Isolation + Workflow ────────────────────────────────────────────────────
leak = [f for f in ("generate_report.py", "ki_agent.py", "health_check.py", "backtest_history.py")
        if "erkundungsfeld" in (ROOT / f).read_text(encoding="utf-8")]
check("30 kein Konsument im Tool", leak == [], leak)
wf = (ROOT / ".github" / "workflows" / "erkundungsfeld.yml").read_text(encoding="utf-8")
check("31 Workflow nur Hand-Start, committet nur erkundungsfeld/",
      "workflow_dispatch" in wf and "schedule" not in wf and "git add erkundungsfeld" in wf
      and wf.count("git add") == 1)
check("32 Schwelle im Code wie festgeschrieben (5 / 3, Top 30)",
      (ef.SCHWELLE_BESTANDEN, ef.SCHWELLE_GRENZFALL, ef.TOP_N) == (5, 3, 30))

# ── Fehl-Analyse (Easy-Entscheid 17.11.2026, nur Namen) ─────────────────────
sd0 = date(2024, 12, 31)
tick = {f"T{i:02d}": 1000 + i for i in range(40) if i != 5}
sec = {1000 + i: [(date(2024, 9, 30), 1_500_000.0)] for i in range(40)}
sec[1006] = [(date(2024, 9, 30), 10**9)]           # T06: Bestand/Aktienzahl < 5 %
bars_fa = {k: v for k, v in bars_map.items() if k != "T07"}
fmap_fa = dict(fmap)
fmap_fa.pop("T08")
fmap_fa["T09"] = (10**9, 1_500_000)                  # Short Float winzig → Filter
cands_fa, _ = ef.score_candidates(t_mid, set(bars_fa), bars_fa, sf, fin2, fmap_fa, gr.score)
ranks_fa = {sym: i + 1 for i, (_, sym, _) in enumerate(cands_fa)}
def _cm(sym, ranks=ranks_fa):
    return ef.classify_miss(t_mid, sym, fin2, tick, sec, bars_fa, fmap_fa, sf, ranks)
cm = {k: _cm(k) for k in ("ZZZ", "BRK.B", "T05", "T06", "T07", "T08", "T09")}
check("39 Fehl-Analyse: genau eine Kategorie je Stufe (FINRA/SEC/Vorfilter/Yahoo/Filter)",
      cm["ZZZ"]["kat"] == 1 and cm["BRK.B"]["detail"].startswith("Kürzelformat")
      and cm["T05"] == {"kat": 2, "detail": "kein CIK", "si": 205000}
      and cm["T06"]["kat"] == 3 and cm["T07"]["detail"] == "kein Yahoo-Kurs am Tag"
      and cm["T08"]["detail"] == "kein Float heute"
      and cm["T09"]["kat"] == 5 and cm["T09"]["detail"] == "short_float", cm)
check("39b außerhalb des Kandidatensets → Kategorie 1 (nicht 6); Kategorie 2/3 bleiben erhalten",
      ef.classify_miss(t_mid, "T10", fin2, tick, sec, bars_fa, fmap_fa, sf, {"T10": 35},
                       candidates={"T11"}) == {"kat": 1, "detail": "Stichtag veraltet (nicht im Kandidatenset)"}
      and ef.classify_miss(t_mid, "T05", fin2, tick, sec, bars_fa, fmap_fa, sf, {}, candidates={"T11"})["kat"] == 2
      and ef.classify_miss(t_mid, "T06", fin2, tick, sec, bars_fa, fmap_fa, sf, {}, candidates={"T11"})["kat"] == 3)
in30 = next(sym for sym, r in ranks_fa.items() if r <= 30)
r6 = _cm("T10", ranks={"T10": 35})
check("40 Rang <= 30 → kein Fehlfall; Rang > 30 → Kategorie 6 mit Rang",
      _cm(in30) is None and r6 == {"kat": 6, "detail": "Rang 35", "rang": 35}, (in30, r6))
check("41 score_candidates liefert alle, rank_day nur die ersten 30 (gleiche Reihenfolge)",
      [s for _, s, *_ in ef.rank_day(t_mid, set(bars_fa), bars_fa, sf, fin2, fmap_fa, gr.score)[0]]
      == [s for _, s, _ in cands_fa[:30]])
cases = [{"kat": 6, "ticker": "A", "detail": "Rang 40", "rang": 40},
         {"kat": 6, "ticker": "B", "detail": "Rang 120", "rang": 120},
         {"kat": 5, "ticker": "A", "detail": "short_float"},
         {"kat": 1, "ticker": "C", "detail": "x"}]
sm = ef.summarize_misses(cases)
check("42 Tabelle: Fälle, Anteil, häufigste Ticker, Rangbereiche; alle 6 Kategorien",
      sm["faelle"] == 4 and sm["kategorien"]["6"]["anteil_pct"] == 50.0
      and sm["kategorien"]["6"]["rang_bereiche"] == {"31-50": 1, "51-100": 0, ">100": 1}
      and sm["kategorien"]["5"]["haeufigste"] == [["A", 1]] and len(sm["kategorien"]) == 6
      and sm == ef.summarize_misses(list(cases)), sm)
with tempfile.TemporaryDirectory() as td:
    ex = pathlib.Path(td) / "e.jsonl"
    ex.write_text(json.dumps({"ticker": "A", "date": "22.07.2026", "provenance": "forward",
                              "short_float": 31.0, "rvol": 2.0, "return_10d": 99.0,
                              "max_gain_pct": 50.0}) + "\n", encoding="utf-8")
    tv = ef.tool_values(ex, ef.WIN_START, ef.WIN_END)
check("43 Export: nur erlaubte Felder vom Listentag (keine Renditen)",
      tv == {(date(2026, 7, 22), "A"): {"source_pools": None, "short_float": 31.0,
                                         "short_float_source": None, "rvol": 2.0,
                                         "entry_price": None, "dtc": None}}
      and not any(k.startswith(("return", "max_", "forward")) for k in ef.EXPORT_FELDER_ERLAUBT), tv)
fa_src = src[src.index("def run_fehlanalyse"):src.index("def _exchange_today")]
check("44 Fehl-Analyse: Kurse nur bis 23.10., FINRA aus Datei, schreibt nur fehlanalyse*",
      "WIN_FETCH_START, WIN_END, WIN_END" in fa_src and "finra_si.jsonl.gz" in fa_src
      and "finra_settlement(" not in fa_src
      and sorted(set(__import__("re").findall(r'OUT_DIR / "([^"]+)"', fa_src))) ==
      ["fehlanalyse.json", "fehlanalyse_faelle.jsonl.gz", "finra_si.jsonl.gz", "vergleich_namen.jsonl.gz"]
      and 'c["unsicher"] = "abbruch:"' in fa_src and "candidates=win_t" in fa_src)
check("45 Workflow: Modus fehlanalyse wählbar, Commit bei voll und fehlanalyse",
      "- fehlanalyse" in wf and "inputs.modus != 'probe'" in wf)

# ── rvol-Regel wie im Tool (Easy-Entscheid 17.11.2026) ──────────────────────
# Tool (generate_report.py, Auswahl top10_vol):
#   top10_vol = [c for c in enriched if c.get("rel_volume", 0) >= MIN_REL_VOLUME]
#   top10 = top10_vol[:10] if len(top10_vol) >= 10 else enriched[:10]
def _c(sym, sc, vor):
    return (sc, sym, {"rvol_vorrang": vor})
cands_u = [_c(f"S{i:02d}", 100 - i, i % 2 == 0) for i in range(24)]   # 12 mit Vorrang
ch, auf = ef.select_tool_order(cands_u)
check("47 Vorrang greift (>= 10 Namen über 1,5): nur diese, Score-Reihenfolge, nicht aufgefüllt",
      [s for _, s, _ in ch] == [f"S{i:02d}" for i in range(0, 24, 2)] and auf is False, [s for _, s, _ in ch])
cands_9 = [_c(f"S{i:02d}", 100 - i, i < 9) for i in range(24)]          # nur 9 mit Vorrang
ch9, auf9 = ef.select_tool_order(cands_9)
check("48 < 10 Namen über 1,5: Liste aller Kandidaten in Score-Reihenfolge, aufgefüllt",
      [s for _, s, _ in ch9] == [f"S{i:02d}" for i in range(24)] and auf9 is True)
cands_10 = [_c(f"S{i:02d}", 100 - i, i >= 14) for i in range(24)]       # genau 10 mit Vorrang
ch10, auf10 = ef.select_tool_order(cands_10)
check("49 Grenze genau 10 → Vorrang (wie len(top10_vol) >= 10)",
      [s for _, s, _ in ch10] == [f"S{i:02d}" for i in range(14, 24)] and auf10 is False)

# Ganzer Tag über rank_day: 12 Ticker mit Volumen-Spitze (rvol ≈ 3), 28 ohne (rvol ≈ 1)
def _bars_spike(spike):
    return [(b[0], b[1], b[2], b[3], b[4], b[5] * (3 if (spike and b[0] == t_mid) else 1)) for b in bars]
bars_v = {f"T{i:02d}": _bars_spike(i < 12) for i in range(40)}
aw = {}
lst_v, _ = ef.rank_day(t_mid, set(bars_v), bars_v, sf, fin2, fmap, gr.score, auswahl=aw)
check("50 Tag mit >= 10 über 1,5: Liste = genau die 12 Vorrang-Namen (Liste kürzer als 30, nicht aufgefüllt)",
      sorted(s for _, s, *_ in lst_v) == [f"T{i:02d}" for i in range(12)]
      and aw == {"aufgefuellt": False, "n_vorrang": 12}
      and all(m["rvol_vorrang"] and m["rvol20"] >= 1.5 for *_, m in lst_v), (len(lst_v), aw))
bars_w = {f"T{i:02d}": _bars_spike(i < 5) for i in range(40)}
aw2 = {}
lst_w, _ = ef.rank_day(t_mid, set(bars_w), bars_w, sf, fin2, fmap, gr.score, auswahl=aw2)
cands_w, _ = ef.score_candidates(t_mid, set(bars_w), bars_w, sf, fin2, fmap, gr.score)
check("51 Tag mit < 10 über 1,5: aufgefüllt aus allen, erste 30 nach Score (auch Namen unter 1,5)",
      [s for _, s, *_ in lst_w] == [s for _, s, _ in cands_w[:30]] and len(lst_w) == 30
      and aw2 == {"aufgefuellt": True, "n_vorrang": 5}
      and any(not m["rvol_vorrang"] for *_, m in lst_w), aw2)
lst_w2, _ = ef.rank_day(t_mid, set(bars_w), bars_w, sf, fin2, fmap, gr.score)
check("52 deterministisch (zweimal gleich, mit und ohne auswahl-Dict)", lst_w == lst_w2)
src_main = src[src.index("def main("):]
check("53 Bericht nennt Tage mit Auffüllen; Schwelle und Kandidatenkreis unverändert",
      '"vergleich_tage_aufgefuellt"' in src_main and "rvol_regel" in src_main
      and (ef.MIN_RVOL, ef.MIN_PRICE, ef.MIN_SI_PCT, ef.MAX_MCAP, ef.MIN_AVG_VOL, ef.PREFILTER_SEC_PCT)
      == (1.5, 1.0, 15.0, 2e9, 300_000, 5.0))

print()
if FAILS:
    print(f"FEHLER: {len(FAILS)} Test(s) rot: {FAILS}")
    sys.exit(1)
print("Alle 53 Checks grün.")
