#!/usr/bin/env python3
"""Mock-Test: Datenprüfung Aktienbasis / Short Float (PR C, 17.11.2026).

Kein Netz (FINRA-POST gemockt). FGL 16.11.2026 als Fixture:
  Marktkap 77.069 $ < 0,9 × Float 609.806 × Kurs 1,02  → Kennzeichen (a)
  Short Float 38,86 % gegen FINRA 28.526 / 609.806 = 4,7 % → Kennzeichen (b)
Prüft außerdem: Veröffentlichungsregel (nur am Tag bekannte Stichtage),
nicht prüfbar statt Abbruch, Cache/Zeitlimit/Rate-Limit ohne Retry, Karte
v1 == v2, Risiko-Text, Digest-Zeile, Determinismus und dass Score/Liste
unverändert bleiben.
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import pathlib
import sys
import tempfile
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "golden_harness_ab", ROOT / "scripts" / "mock_test_outer_page_golden.py")
golden = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(golden)
gr = golden.gr
import aktienbasis_check as ab  # noqa: E402
import config  # noqa: E402

FAILS: list[str] = []


def check(name, cond, detail=""):
    print(("OK  " if cond else "FAIL") + f"  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# FINRA consolidatedShortInterest FGL (Easy, 17.11.2026), Rohformat wie API.
FGL_RAW = [
    {"symbolCode": "FGL", "settlementDate": "2026-10-30", "currentShortPositionQuantity": 28526, "stockSplitFlag": None},
    {"symbolCode": "FGL", "settlementDate": "2026-10-15", "currentShortPositionQuantity": 10661, "stockSplitFlag": None},
    {"symbolCode": "FGL", "settlementDate": "2026-09-30", "currentShortPositionQuantity": 11803, "stockSplitFlag": None},
    {"symbolCode": "FGL", "settlementDate": "2026-09-15", "currentShortPositionQuantity": 20308, "stockSplitFlag": "S"},
    {"symbolCode": "FGL", "settlementDate": "2026-08-31", "currentShortPositionQuantity": 406154, "stockSplitFlag": None},
    {"symbolCode": "FGL", "settlementDate": "2026-08-14", "currentShortPositionQuantity": 96779, "stockSplitFlag": None},
]
FGL = {"ticker": "FGL", "yf_market_cap": 77069, "market_cap": 77069, "float_shares": 609806,
       "shares_outstanding": 75560, "price": 1.02, "short_float": 38.86,
       "short_float_source": "yfinance"}
D = date(2026, 11, 16)
NOW = datetime(2026, 11, 17, 4, 10, tzinfo=timezone.utc)


class _Resp:
    def __init__(self, code, body):
        self.status_code = code
        self._b = body
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        return self._b


def _poster(table, calls):
    def post(url, json=None, timeout=None, headers=None):  # noqa: A002
        sym = json["compareFilters"][0]["fieldValue"]
        calls.append(sym)
        code, body = table.get(sym, (200, []))
        return _Resp(code, body)
    return post


recs = ab.normalize_records(FGL_RAW)
fin = {"status": "ok", "records": recs, "quelle": "api", "abgerufen_utc": NOW.isoformat()}

# ── 01–06 Kennzeichen mit den FGL-Zahlen ─────────────────────────────────────
r = ab.evaluate(FGL, fin, D)
check("01 (a) Aktienbasis widersprüchlich (77.069 < 0,9 × 609.806 × 1,02)",
      r["aktienbasis"] == "widerspruechlich", r["aktienbasis"])
check("02 (b) Short Float abweichend (38,86 % gegen FINRA)", r["short_float_pruefung"] == "abweichend")
check("03 FINRA-Short-Float = 28.526 / 609.806 = 4,68 %", r["finra_short_float"] == 4.68, r["finra_short_float"])
check("04 Stichtag 30.10.2026, veröffentlicht 10.11.2026 (7 Handelstage)",
      r["finra_stichtag"] == "2026-10-30" and r["finra_veroeffentlicht"] == "2026-11-10",
      (r["finra_stichtag"], r["finra_veroeffentlicht"]))
check("05 Rohwerte gespeichert (Marktkap, Float, Aktienzahl, Bestand)",
      (r["marktkap"], r["float_aktien"], r["aktienzahl"], r["finra_bestand"]) == (77069.0, 609806, 75560, 28526))
txt = ab.warning_text(r)
check("06 Warntext nennt 4,7 % und den Stichtag",
      "FINRA-Bestand ergibt 4,7 %" in txt and "30.10.2026" in txt and "Aktienbasis widersprüchlich" in txt, txt)

# ── 07–09 zeitlich sauber + Split-Kennzeichen ───────────────────────────────
r9 = ab.evaluate(FGL, fin, date(2026, 11, 9))
check("07 Berichtstag 09.11.: 30.10. noch nicht veröffentlicht → Stichtag 15.10.",
      r9["finra_stichtag"] == "2026-10-15" and r9["finra_bestand"] == 10661, r9["finra_stichtag"])
r_old = ab.evaluate(FGL, fin, date(2026, 8, 20))
check("08 kein veröffentlichter Stichtag → nicht prüfbar (Grund)",
      r_old["short_float_pruefung"] == "nicht_pruefbar"
      and r_old["short_float_grund"] == "kein_veroeffentlichter_stichtag")
r_sp = ab.evaluate(FGL, fin, date(2026, 10, 1))  # 15.09. (S) ist jüngster bekannter
check("09 FINRA-Split-Kennzeichen wird ausgewiesen", r_sp["finra_split"] == "S"
      and r_sp["finra_split_kuerzlich"] is True and "Zusammenlegung" in ab.warning_text(r_sp))

# ── 10–13 unauffällig / nicht prüfbar ───────────────────────────────────────
OK = dict(FGL, ticker="OKAY", yf_market_cap=50e6, market_cap=50e6, short_float=20.0)
fin_ok = {"status": "ok", "records": [{"settlement_date": "2026-10-30", "bestand": 120000,
                                      "split": None, "revision": None}]}
r_ok = ab.evaluate(OK, fin_ok, D)
check("10 Gegenprobe: plausible Werte → beide ok, kein Hinweis",
      r_ok["aktienbasis"] == "ok" and r_ok["short_float_pruefung"] == "ok"
      and not ab.is_auffaellig(r_ok) and ab.warning_text(r_ok) == "")
check("11 FINRA-Fehler → nicht prüfbar (finra_fehler), (a) trotzdem geprüft",
      (lambda x: x["short_float_pruefung"] == "nicht_pruefbar" and x["short_float_grund"] == "finra_fehler"
       and x["aktienbasis"] == "widerspruechlich")(ab.evaluate(FGL, {"status": "fehler"}, D)))
check("12 FINRA kennt Ticker nicht → nicht prüfbar",
      ab.evaluate(FGL, {"status": "ok", "records": []}, D)["short_float_grund"] == "finra_kennt_ticker_nicht")
r_nf = ab.evaluate(dict(FGL, float_shares=0), fin, D)
check("13 Float fehlt → beide nicht prüfbar, Bestand trotzdem gespeichert",
      r_nf["aktienbasis_grund"] == "float_fehlt" and r_nf["short_float_grund"] == "float_fehlt"
      and r_nf["finra_bestand"] == 28526)
check("14 beide Werte < 1 % → kein Kennzeichen",
      ab.evaluate(dict(OK, short_float=0.2), {"status": "ok", "records": [
          {"settlement_date": "2026-10-30", "bestand": 0, "split": None, "revision": None}]}, D)
      ["short_float_pruefung"] == "ok")
check("14b Short Float 0 bzw. Quelle „none“ → nicht prüfbar (kein Fehlalarm)",
      all(ab.evaluate(x, fin, D)["short_float_pruefung"] == "nicht_pruefbar"
          and ab.evaluate(x, fin, D)["short_float_grund"] == "short_float_fehlt"
          for x in (dict(FGL, short_float=0.0), dict(FGL, short_float_source="none"))))
check("15 Determinismus: gleiche Eingabe → gleiches Ergebnis",
      ab.evaluate(FGL, fin, D) == ab.evaluate(copy.deepcopy(FGL), copy.deepcopy(fin), D))

# ── 16–21 Abruf: Cache, Rate-Limit ohne Retry, Zeitlimit ────────────────────
calls: list[str] = []
cache = {"schema_v": 1, "tickers": {}}
out = ab.get_records(["FGL", "AAA", "BBB"], now_utc=NOW, cache=cache,
                     post_fn=_poster({"FGL": (200, FGL_RAW), "AAA": (500, None)}, calls))
check("16 Abruf: FGL ok, AAA Fehler, BBB unbekannt (leer)",
      out["FGL"]["status"] == "ok" and out["AAA"]["status"] == "fehler"
      and out["BBB"]["status"] == "ok" and out["BBB"]["records"] == [])
check("17 genau ein Abruf je Ticker (kein Retry)", sorted(calls) == ["AAA", "BBB", "FGL"], calls)
calls2: list[str] = []
out2 = ab.get_records(["FGL"], now_utc=NOW, cache=cache, post_fn=_poster({}, calls2))
check("18 Cache-Treffer (< 20 h) ohne Abruf", calls2 == [] and out2["FGL"]["quelle"] == "cache")
calls3: list[str] = []
later = datetime(2026, 11, 18, 4, 0, tzinfo=timezone.utc)
ab.get_records(["FGL"], now_utc=later, cache=cache, post_fn=_poster({"FGL": (200, FGL_RAW)}, calls3))
check("19 Cache älter als 20 h → neuer Abruf", calls3 == ["FGL"])
calls4: list[str] = []
out4 = ab.get_records(["A1", "A2", "A3"], now_utc=NOW, cache={"tickers": {}},
                      post_fn=_poster({"A1": (429, None)}, calls4))
check("20 Rate-Limit: kein Retry, übrige als rate_limit, keine weiteren Abrufe",
      calls4 == ["A1"] and out4["A2"]["status"] == "rate_limit" and out4["A3"]["status"] == "rate_limit")
_t = iter([0.0, 0.0, 100.0, 100.0])
calls5: list[str] = []
out5 = ab.get_records(["B1", "B2"], now_utc=NOW, cache={"tickers": {}},
                      post_fn=_poster({}, calls5), budget_s=60, clock=lambda: next(_t))
check("21 Zeitlimit → Rest „zeitlimit“, kein Abbruch",
      calls5 == ["B1"] and out5["B2"]["status"] == "zeitlimit", (calls5, out5["B2"]))

with tempfile.TemporaryDirectory() as td:
    cp = pathlib.Path(td) / "c.json"
    c = {"tickers": {"OLD": {"abgerufen_utc": "2026-09-01T00:00:00+00:00", "records": []},
                     "NEW": {"abgerufen_utc": NOW.isoformat(), "records": []}}}
    ab.save_cache(c, cp, now_utc=NOW)
    saved = json.loads(cp.read_text())
    check("22 Cache-Prune nach 30 Tagen", list(saved["tickers"]) == ["NEW"])

    # run(): setzt nur das eine Feld, ändert sonst nichts am Stock-Dict
    s1 = copy.deepcopy(FGL)
    before = copy.deepcopy(s1)
    res = ab.run([s1], report_day=D, now_utc=NOW, cache_path=cp,
                 post_fn=_poster({"FGL": (200, FGL_RAW)}, []))
    added = set(s1) - set(before)
    check("23 run() fügt nur aktienbasis_pruefung hinzu, sonst unverändert",
          added == {ab.FIELD} and all(s1[k] == before[k] for k in before))
    check("24 Log-Zeile nennt FGL auffällig", "auffällig 1 (FGL)" in ab.log_line(res), ab.log_line(res))
    s_broken = {"ticker": "X", "price": "kaputt"}
    ab.run([s_broken], report_day=D, now_utc=NOW, cache_path=cp,
           post_fn=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("netz")))
    check("25 Netzfehler im Lauf → nicht prüfbar, keine Exception",
          s_broken[ab.FIELD]["short_float_pruefung"] == "nicht_pruefbar")

    # Digest-Zeile
    bh = pathlib.Path(td) / "bh.json"
    bh.write_text(json.dumps([
        {"date": "13.11.2026", "ticker": "OLD1", ab.FIELD: ab.evaluate(FGL, fin, D)},
        {"date": "16.11.2026", "ticker": "FGL", ab.FIELD: r},
        {"date": "16.11.2026", "ticker": "OKAY", ab.FIELD: r_ok},
        {"date": "16.11.2026", "ticker": "NP", ab.FIELD: ab.evaluate(FGL, {"status": "fehler"}, D)},
        {"date": "16.11.2026", "ticker": "ALT"},
    ]))
    dl = ab.digest_line(bh)
    check("26 Digest: jüngster Tag, x von n auffällig mit Tickern, FINRA nicht prüfbar",
          dl == "🟡 Datenprüfung Short Float (16.11.): 2 von 3 auffällig (FGL, NP) · FINRA nicht prüfbar 1", dl)
    bh.write_text("[]")
    check("27 Digest ohne Feld → sammelt ab dem nächsten Postclose", "noch kein Eintrag" in ab.digest_line(bh))

# ── 28–31 Karte, Risiko-Text ────────────────────────────────────────────────
s_card = dict(golden._fixture_stocks()[0])
s_card[ab.FIELD] = r
h1 = gr._card(0, s_card)
check("28 Karte v1: Kachel-Hinweis + Zeile in Short-Daten + Marktkap markiert",
      '<span class="sf-doubt"' in h1 and "sf-doubt-row" in h1 and "⚠ widersprüchlich" in h1
      and "4,7 %" in h1)
h_plain = gr._card(0, dict(golden._fixture_stocks()[0]))
check("29 Karte ohne Prüffeld: kein Hinweis", "sf-doubt" not in h_plain)
_real_dt = gr.datetime
gr.datetime = golden._FixedDateTime
try:
    _st = golden._fixture_stocks()
    _st[0][ab.FIELD] = r
    gr._render_test(_st, golden._FIXED_REPORT_DATE)
    ok = True
except Exception as exc:  # noqa: BLE001
    ok = False
    print("   ", exc)
finally:
    gr.datetime = _real_dt
check("30 v1 == v2 mit Hinweis (_render_test)", ok)
s_risk = dict(s_card)
lv_flag, _, txt_flag = gr.risk_assessment(s_risk)
s_risk.pop(ab.FIELD)
lv_plain, _, _ = gr.risk_assessment(dict(s_risk, market_cap=77069, yf_market_cap=77069))
lv_flag2, _, txt_flag2 = gr.risk_assessment(dict(s_risk, market_cap=77069, yf_market_cap=77069,
                                                  **{ab.FIELD: r}))
check("31 Risiko-Text: keine Marktkap als Tatsache, Risiko-Stufe unverändert",
      "$77,069" not in txt_flag2 and "unsicher" in txt_flag2 and lv_flag2 == lv_plain, txt_flag2)

# ── 32–35 keine Wirkung auf Score/Liste ─────────────────────────────────────
st_a = golden._fixture_stocks()
st_b = copy.deepcopy(st_a)
for x in st_b:
    x[ab.FIELD] = r
check("32 score() identisch mit/ohne Prüffeld",
      [gr.score(x) for x in st_a] == [gr.score(x) for x in st_b])
check("33 _compute_sub_scores identisch mit/ohne Prüffeld",
      [gr._compute_sub_scores(x) for x in st_a] == [gr._compute_sub_scores(x) for x in st_b])
src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
tree = ast.parse(src)
_forbidden = {"score", "score_bonus", "_compute_sub_scores", "compute_conviction_score",
              "apply_conviction_scores", "apply_agent_boost", "apply_late_runner_penalty",
              "apply_score_smoothing", "apply_monster_score", "compute_earliness_pts",
              "_passes_cap_filter", "get_short_float_with_fallback"}
leak = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in _forbidden
        and ("aktienbasis" in ast.get_source_segment(src, n))]
check("34 kein Score-/Filter-/Conviction-Pfad liest die Prüfung", leak == [], leak)
check("35 Aufruf erst nach Step 3c (Short-Float-Korrekturen), vor dem Rendern",
      src.index("Step 3c2") < src.index("_abc.run(") < src.index('log.info("Step 4 – Generating HTML report'))
check("35b Prüfung läuft VOR dem Postclose-Backtest-Append (Feld beim Append gesetzt)",
      src.index("_abc.run(") < src.index("_n_backtest_appended = _append_backtest_entries("))

# ── 36–39 Persistenz, Workflow, Konstanten ──────────────────────────────────
bsrc = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
check("36 Backtest-Eintrag: Feld aus dem Stock-Dict, unbekannt = null",
      "entry[_AKTIENBASIS_FIELD] = dict(_ab) if isinstance(_ab, dict) else None" in bsrc)
check("37 S10_OBSERVED enthält aktienbasis_pruefung", ab.FIELD in config.S10_OBSERVED_FIELDS)
wf = (ROOT / ".github/workflows/daily-squeeze-report.yml").read_text(encoding="utf-8")
check("38 Daily-Workflow committet den Cache", f"git add {config.FINRA_CSI_CACHE_FILE}" in wf)
check("39 Schwellen als Konstanten (0,9 / Faktor 2 / 1 %)",
      (config.AKTIENBASIS_MCAP_FLOAT_FACTOR, config.SHORT_FLOAT_FINRA_ABWEICHUNG_FAKTOR,
       config.SHORT_FLOAT_FINRA_MIN_PCT) == (0.9, 2.0, 1.0))

print()
if FAILS:
    print(f"FEHLER: {len(FAILS)} Test(s) rot: {FAILS}")
    sys.exit(1)
print("Alle 41 Checks grün.")
