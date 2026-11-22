#!/usr/bin/env python3
"""Mock-Test Pool-Schatten (22.11.2026). Feste Uhr, kein Netz.

 1  Vorrang-Tag: Top-10-Markierung = angezeigte Liste, Regel „vorrang“
 2  Auffüll-Tag: Top-10-Markierung = angezeigte Liste, Regel „auffuellen“
 3  Top-10 passt nicht zur Regel → Kennzeichen + Warnung, kein Abbruch
 4  Rangkontrolle: steigender Score in Rangfolge → rang_konsistent=false
 5  Idempotenz: zweiter Lauf schreibt nichts, Datei byte-gleich
 6  Fehler beim Schreiben bricht den Lauf nicht ab (run + Haken im Daily-Run)
 7  null bleibt null (NaN/None nie 0), Score None → rang_konsistent None
 8  Vintage: Zeilen bleiben + Grund; Laufzeit-Gate/Wochenende schreiben nichts
 9  Monatsdateien + Digest-Zeile über alle Monate
10  Warnzeile bei Postclose-Tag ohne Zeilen
11  keine Mutation der Kandidaten; Determinismus; Merkmale-Regeln
12  Konsumenten: nur Digest; Haken außerhalb der geschützten Zone
"""
from __future__ import annotations

import copy
import json
import os
import pathlib
import re
import sys
import tempfile
import types
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _m in ("yfinance", "pandas", "requests"):
    try:
        __import__(_m)
    except ImportError:
        _mod = types.ModuleType(_m)
        if _m == "requests":
            class _E(Exception):
                pass
            _mod.get = _mod.post = lambda *a, **k: None
            _mod.RequestException = _E
            _mod.exceptions = types.SimpleNamespace(RequestException=_E, Timeout=_E)
        sys.modules[_m] = _mod

import pool_schatten as ps  # noqa: E402
from backtest_history import _vintage_gate_decision as GATE  # noqa: E402

FAILS: list[str] = []
ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 23, 17, 30, tzinfo=ET)      # Montag, nach 16:20 ET
RD = "23.11.2026"
RUN_TS = "2026-11-23T22:30:00Z"


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def cand(t, score, rvol, **kw):
    c = {"ticker": t, "score": score, "rel_volume": rvol, "price": 5.0,
         "bar_date": "2026-11-23", "letzte_zeile": "vollstaendig",
         "source": "yahoo_screener", "source_pools": ["yahoo_most_shorted"],
         "short_float": 25.0, "short_ratio": 6.0}
    c.update(kw)
    return c


def simulate_run(enriched):
    """Bildet main() nach: Sortierung, Auswahl, danach Score-Mutation der Top-10."""
    enriched.sort(key=lambda x: x.get("score") or 0, reverse=True)
    vol = [c for c in enriched if c.get("rel_volume", 0) >= 1.5]
    top10 = vol[:10] if len(vol) >= 10 else enriched[:10]
    for s in top10:                       # FINRA-Bonus + Glättung wie im Lauf
        bonus = 3.0 if s["ticker"].endswith("0") else 0.0
        s["finra_bonus_pts"] = bonus
        if bonus:
            s["score"] = round(min(s["score"] + bonus, 100.0), 2)
        s["score_raw"] = s["score"]
        s["score"] = round(s["score"] * 0.9 + 3, 1)   # geglättet, verändert
    top10.sort(key=lambda x: x["score"], reverse=True)
    return enriched, top10


def run(enriched, top10, root, **kw):
    kw.setdefault("now_et", NOW)
    kw.setdefault("run_ts", RUN_TS)
    kw.setdefault("min_rvol", 1.5)
    kw.setdefault("gate_fn", GATE)
    # CIK-Quelle fest (kein Prozess-Zustand aus material_8k im Test, 22.11.2026)
    kw.setdefault("cik_fn", lambda t: (None, "keine eindeutige CIK") if str(t).startswith("X")
                  else ("0000000001", None))
    return ps.run(enriched, top10, report_date=kw.pop("rd", RD), root=root, **kw)


def rows_of(root, month="2026-11"):
    return ps._read_jsonl(os.path.join(root, "pool_schatten", f"{month}.jsonl"))


# 1 Vorrang-Tag
with tempfile.TemporaryDirectory() as d:
    en = [cand(f"V{i}", 90 - i * 2.5, 2.0 if i not in (2, 5, 9) else 1.0) for i in range(14)]
    en, top = simulate_run(en)
    res = run(en, top, d, code_sha="abc123")
    rows = rows_of(d)
    shown = {s["ticker"] for s in top}
    marked = {r["ticker"] for r in rows if r["top10"]}
    check(res["status"] == "geschrieben" and len(rows) == 14 == res["pool_size"],
          f"Vorrang-Tag: Zeilen = pool_size ({len(rows)})")
    check(marked == shown and len(marked) == 10, "Vorrang-Tag: Top-10-Markierung = angezeigte Liste")
    check(all(r["tag_regel"] == "vorrang" for r in rows)
          and all((r["top10_regel"] == "vorrang") == r["top10"] for r in rows),
          "Vorrang-Tag: Regel vorrang")
    check(all(r["rang_konsistent"] is True for r in rows), "Vorrang-Tag: rang_konsistent überall true")
    check([r["rang"] for r in rows] == list(range(1, 15)), "Zeilen in Rangfolge")
    check(all(r["code_sha"] == "abc123" and r["top10_markierung_konsistent"] for r in rows),
          "code_sha + Markierung konsistent")
    anz = {r["ticker"]: r["top10_anzeige_rang"] for r in rows if r["top10"]}
    check(anz == {s["ticker"]: i for i, s in enumerate(top, 1)}, "top10_anzeige_rang = angezeigte Reihenfolge")
    t0 = next(r for r in rows if r["ticker"] == "V0")
    check(t0["score_auswahl"] == 90.0 and t0["score_auswahl_quelle"] == "zurueckgerechnet",
          f"Top-10 mit FINRA-Bonus: Auswahl-Score zurückgerechnet ({t0['score_auswahl']})")
    nt = [r for r in rows if not r["top10"]]
    check(all(r["score_auswahl_quelle"] == "direkt" for r in nt), "Rang 11+: Score direkt")
    check(not ps.is_warning(res), "Vorrang-Tag: keine Warnung")

# 2 Auffüll-Tag
with tempfile.TemporaryDirectory() as d:
    en = [cand(f"A{i}", 80 - i, 2.0 if i % 3 == 0 else 0.8) for i in range(13)]
    en, top = simulate_run(en)
    res = run(en, top, d)
    rows = rows_of(d)
    check({r["ticker"] for r in rows if r["top10"]} == {s["ticker"] for s in top}
          and res["regel"] == "auffuellen" and len(rows) == 13,
          "Auffüll-Tag: Top-10-Markierung = angezeigte Liste, Regel auffuellen")
    check(all(r["rang_konsistent"] is True for r in rows), "Auffüll-Tag: rang_konsistent überall true")
    check(all(r["rang_vorrang"] is None for r in rows if not r["rvol_vorrang"]), "rang_vorrang nur bei rvol-Vorrang")

# 3 Top-10 passt nicht zur Regel
with tempfile.TemporaryDirectory() as d:
    en = [cand(f"M{i}", 80 - i, 2.0) for i in range(12)]
    en, top = simulate_run(en)
    top = top[:9] + [en[11]]
    res = run(en, top, d)
    check(res["status"] == "geschrieben" and res["top10_konsistent"] is False
          and ps.is_warning(res) and "passt nicht" in ps.log_line(res),
          "Abweichung Markierung/Regel → Kennzeichen + Warnung, kein Abbruch")

# 4 Rangkontrolle
with tempfile.TemporaryDirectory() as d:
    en = [cand(f"R{i}", 80 - i, 2.0) for i in range(14)]
    en, top = simulate_run(en)
    en[12]["score"] = 99.0                # Rang 13 höher als Rang 12
    res = run(en, top, d)
    rows = rows_of(d)
    bad = {r["rang"] for r in rows if r["rang_konsistent"] is False}
    check(bad == {12, 13} and res["rang_inkonsistent"] == 2 and ps.is_warning(res)
          and res["status"] == "geschrieben",
          f"Rangkontrolle markiert betroffene Zeilen {sorted(bad)}, kein Abbruch")
    rows2 = [{"score_auswahl": 50.0}, {"score_auswahl": 50.004}, {"score_auswahl": 49.0}]
    check(ps.rang_check(rows2) == 0, "Rundungs-Toleranz 0,01")

# 5 Idempotenz
with tempfile.TemporaryDirectory() as d:
    en = [cand(f"I{i}", 80 - i, 2.0) for i in range(12)]
    en, top = simulate_run(en)
    r1 = run(en, top, d)
    p = os.path.join(d, "pool_schatten", "2026-11.jsonl")
    b1 = open(p, "rb").read()
    r2 = run(en, top, d, run_ts="2026-11-23T23:59:00Z")
    check(r1["status"] == "geschrieben" and r2["status"] == "schon_vorhanden"
          and open(p, "rb").read() == b1, "Idempotenz: zweiter Lauf schreibt nichts, byte-gleich")

# 6 Schreibfehler
with tempfile.TemporaryDirectory() as d:
    en = [cand(f"E{i}", 80 - i, 2.0) for i in range(11)]
    en, top = simulate_run(en)

    def boom(rows, root):
        raise OSError("Platte voll")
    res = run(en, top, d, write_fn=boom)
    check(res["status"] == "fehler" and "Platte voll" in res["grund"] and ps.is_warning(res),
          "Schreibfehler → status fehler, keine Ausnahme")
    res_g = run(en, top, d, gate_fn=lambda *a: 1 / 0)
    check(res_g["status"] == "fehler", "Fehler im Gate → status fehler, keine Ausnahme")
src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
i = src.index("import pool_schatten as _pool_schatten")
blk = src[src.rindex("try:", 0, i):i + 900]
check("except Exception as _ps_exc" in blk, "Daily-Run-Haken steht in try/except")
j_end = src.index("# PROTECTED-ZONE-END: filter-top10-selection")
j_bt = src.index("_n_backtest_appended = _append_backtest_entries(")
check(j_end < j_bt < i, "Haken nach Zonen-Ende und nach dem Backtest-Append")
branch = src[src.rindex('if run_phase == "postclose":', 0, j_bt):i]
check("else:" not in branch.split("_n_backtest_appended = _append_backtest_entries(")[0][-400:],
      "Haken im postclose-Zweig")

# 7 null bleibt null
with tempfile.TemporaryDirectory() as d:
    en = [cand(f"N{i}", 80 - i, 2.0) for i in range(11)]
    en.append(cand("NAN", 10.0, float("nan"), price=float("nan"), short_ratio=None,
                   short_float=float("inf")))
    en.append(cand("NOS", None, 2.0))
    en, top = simulate_run(en)
    run(en, top, d)
    rows = {r["ticker"]: r for r in rows_of(d)}
    n = rows["NAN"]
    check(n["price"] is None and n["merkmale"]["rel_volume"] is None
          and n["merkmale"]["short_ratio"] is None and n["merkmale"]["short_float"] is None
          and n["rvol_vorrang"] is False, "NaN/None/Inf → null, nie 0")
    s = rows["NOS"]
    check(s["score_auswahl"] is None and s["rang_konsistent"] is None, "Score None → rang_konsistent null")

# 8 Vintage
with tempfile.TemporaryDirectory() as d:
    en = [cand(f"G{i}", 80 - i, 2.0) for i in range(11)]
    en[3]["bar_date"] = "2026-11-20"
    en[4]["bar_date"] = "2026-11-20"
    en[4]["letzte_zeile"] = "vortag_rueckfall"
    en[5]["bar_date"] = None
    en, top = simulate_run(en)
    run(en, top, d)
    rows = {r["ticker"]: r for r in rows_of(d)}
    check(len(rows) == 11 and rows["G3"]["vintage_zeile"] == "holiday_or_prior_bar"
          and rows["G4"]["vintage_zeile"] == "zeile_nicht_fuellbar"
          and rows["G5"]["vintage_zeile"] == "missing_bar" and rows["G0"]["vintage_zeile"] == "ok",
          "Vintage je Zeile: behalten und gekennzeichnet")
with tempfile.TemporaryDirectory() as d:
    en, top = simulate_run([cand(f"H{i}", 80 - i, 2.0) for i in range(11)])
    r_early = run(en, top, d, now_et=datetime(2026, 11, 23, 16, 0, tzinfo=ET))
    r_wk = run(en, top, d, rd="21.11.2026", now_et=datetime(2026, 11, 21, 18, 0, tzinfo=ET))
    check(r_early["status"] == "uebersprungen" and r_early["grund"] == "before_close"
          and r_wk["grund"] == "wochenende"
          and not os.path.exists(os.path.join(d, "pool_schatten")),
          "Laufzeit-Gate + Wochenende: nichts geschrieben")

# 9 Monatsdateien + Digest
with tempfile.TemporaryDirectory() as d:
    check("noch keine Zeile" in ps.digest_line(d), "Digest ohne Daten")
    en, top = simulate_run([cand(f"K{i}", 80 - i, 2.0) for i in range(12)])
    run(en, top, d, rd="30.10.2026", now_et=datetime(2026, 10, 30, 18, 0, tzinfo=ET))
    en, top = simulate_run([cand(f"L{i}", 80 - i, 2.0) for i in range(20)])
    run(en, top, d)
    files = sorted(os.listdir(os.path.join(d, "pool_schatten")))
    line = ps.digest_line(d)
    check(files == ["2026-10.jsonl", "2026-11.jsonl"], f"Monatsdateien {files}")
    check(line == "🗂 Pool-Schatten: läuft · letzter Tag 23.11. · Zeilen 32 · Kandidaten je Tag (Median) 16 · CIK 20/20",
          f"Digest-Zeile: {line}")

# 10 Warnzeile
with tempfile.TemporaryDirectory() as d:
    bh = os.path.join(d, "bh.json")
    json.dump([{"date": "24.11.2026", "ticker": "X"}, {"date": "25.11.2026", "ticker": "Y", "bootstrap": True}],
              open(bh, "w"))
    check(ps.warn_line(d, bh) is None, "Warnzeile: ohne Pool-Daten keine Warnung (vor dem Start)")
    en, top = simulate_run([cand(f"W{i}", 80 - i, 2.0) for i in range(11)])
    run(en, top, d)
    check(ps.warn_line(d, bh) == "⚠️ Pool-Schatten: Postclose 24.11. ohne Zeilen", "Warnzeile bei fehlendem Tag")
    json.dump([{"date": "23.11.2026", "ticker": "X"}], open(bh, "w"))
    check(ps.warn_line(d, bh) is None, "keine Warnzeile, wenn Tag vorhanden")

# 11 keine Mutation, Determinismus, Merkmale
with tempfile.TemporaryDirectory() as d1:
    en, top = simulate_run([cand(f"D{i}", 80 - i, 2.0, news=[{"t": "x"}], card_html="<b>",
                                 _intern=1, long_list=list(range(800)), manual_personal=(i == 11))
                            for i in range(12)])
    before = copy.deepcopy(en)
    run(en, top, d1)
    check(en == before, "Kandidaten-Objekte unverändert")
    r = rows_of(d1)[0]
    check(not {"news", "card_html", "_intern", "long_list"} & set(r["merkmale"])
          and r["merkmale_ausgelassen"] == ["long_list:laenge"],
          f"Merkmale ohne News/HTML/intern, lange Werte benannt ({r['merkmale_ausgelassen']})")
    wl = [x for x in rows_of(d1) if x["ticker"] == "D11"][0]
    check(wl["watchlist_bypass"] is True, "Watchlist-Ticker gekennzeichnet")
    d3 = tempfile.mkdtemp()
    en3 = copy.deepcopy(before)
    by_t = {x["ticker"]: x for x in en3}
    run(en3, [by_t[t["ticker"]] for t in top], d3)
    check(open(os.path.join(d1, "pool_schatten", "2026-11.jsonl"), "rb").read()
          == open(os.path.join(d3, "pool_schatten", "2026-11.jsonl"), "rb").read(),
          "Determinismus: gleiche Eingabe → gleiche Bytes")

# 11b Datenschutz-Sperre
_priv = {"position_size": 3, "entry_price": 1.0, "pnl_pct": 2.0, "shares": 35, "gist_id": "x",
         "token_hint": "y", "thesis": "t", "Position": 1}
m, _ = ps.merkmale_of({"ticker": "P", "score": 1.0, "shares_outstanding": 10, **_priv})
check(not set(_priv) & set(m) and m.get("shares_outstanding") == 10,
      f"Positions-/Nutzerfelder nie in merkmale ({sorted(set(_priv) & set(m))})")

# 12 Konsumenten
users = []
for p in ROOT.rglob("*"):
    if p.is_file() and p.suffix in (".py", ".yml", ".jinja", ".js", ".html") and ".git" not in p.parts:
        try:
            if "pool_schatten" in p.read_text(encoding="utf-8", errors="ignore"):
                users.append(str(p.relative_to(ROOT)))
        except OSError:
            pass
allowed = {"pool_schatten.py", "generate_report.py", "scripts/health_check_digest.py",
           "scripts/mock_test_pool_schatten.py", "scripts/run_ci_mock_tests.py",
           "scripts/mock_test_verwaesserung.py",
           ".github/workflows/daily-squeeze-report.yml"}
check(set(users) <= allowed, f"Konsumenten nur Digest/Writer/Workflow/Tests: {sorted(set(users) - allowed)}")
gr_uses = re.findall(r"_pool_schatten\.(\w+)", src)
check(set(gr_uses) <= {"run", "log_line", "is_warning"}, f"Daily-Run ruft nur run/log_line/is_warning: {set(gr_uses)}")

print()
if FAILS:
    print(f"{len(FAILS)} FEHLER")
    sys.exit(1)
print("OK — alle Checks grün")
