#!/usr/bin/env python3
"""Mock-Tests für scripts/suw_eval.py (Regel SUW, Easy-Entscheid 15.11.2026).

Kein Netz: FINRA- und Yahoo-Abrufe werden injiziert. Prüft den Rechenkern an
einem von Hand nachvollziehbaren Beispiel, fehlende Tage, Gleichstand, die
harten Datumsriegel beider Betriebsarten und dass „test“ vor (und auch nach)
dem Auslöser keine Kurse, Dateien oder Renditen lädt.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
import tempfile
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import suw_eval as S  # noqa: E402

FAILS: list[str] = []


def check(name, cond, detail=""):
    print(("OK  " if cond else "FAIL") + f"  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def dmy(d: date) -> str:
    return d.strftime("%d.%m.%Y")


NOHOL: frozenset = frozenset()

# ── 1) Hand-Beispiel Rechenkern ─────────────────────────────────────────────
D = date(2026, 9, 15)  # Dienstag
W = S.window_days(D, holidays=NOHOL)
check("01 Fenster: 20 Tage, D selbst nicht, nur Mo–Fr", len(W) == 20 and D not in W
      and all(x.weekday() < 5 for x in W) and max(W) == date(2026, 9, 14))
# 10 Tage sv=1 @ 10 $, 10 Tage sv=3 @ 20 $ → R = (10·1·10 + 10·3·20)/(10·1+10·3)
#   = (100 + 600)/40 = 17,5 ; c_D = 21 → SUW = 21/17,5 − 1 = +20 %.
sv = {t: (1.0 if i < 10 else 3.0) for i, t in enumerate(W)}
cl = {t: (10.0 if i < 10 else 20.0) for i, t in enumerate(W)}
cl[D] = 21.0
v, why, miss = S.suw_value(D, W, sv, cl)
check("02 Hand-Beispiel SUW = +20,00 %", v is not None and abs(v - 20.0) < 1e-9 and miss == 0, f"{v} {why}")

# ── 2) Fehlende Tage ────────────────────────────────────────────────────────
sv5 = dict(sv)
for t in W[:3]:
    del sv5[t]          # 3 Tage fehlt der Ticker in der FINRA-Datei
cl5 = dict(cl)
for t in W[3:5]:
    del cl5[t]          # 2 Tage fehlt der Yahoo-Kurs
v5, why5, m5 = S.suw_value(D, W, sv5, cl5)
check("03 genau 5 fehlende Tage → Wert", v5 is not None and m5 == 5, f"{why5} {m5}")
sv6 = dict(sv5)
del sv6[W[10]]
v6, why6, m6 = S.suw_value(D, W, sv6, cl5)
check("04 6 fehlende Tage → kein Wert (nicht 0)", v6 is None and why6 == "zu_viele_fehlende_tage" and m6 == 6)
clD = dict(cl)
del clD[D]
check("05 c_D fehlt → kein Wert", S.suw_value(D, W, sv, clD)[0] is None)
sv0 = {t: 0.0 for t in W}
check("06 Summe sv = 0 → kein Wert", S.suw_value(D, W, sv0, cl)[1] == "summe_sv_null")
clnan = dict(cl)
clnan[W[0]] = float("nan")
check("07 NaN-Kurs zählt als fehlend", S.suw_value(D, W, sv, clnan)[2] == 1)

# ── 3) Kalender ─────────────────────────────────────────────────────────────
hol = frozenset({"2026-09-07"})  # Montag als Feiertag
W2 = S.window_days(date(2026, 9, 9), n=3, holidays=hol)
check("08 Feiertag wird übersprungen", W2 == [date(2026, 9, 3), date(2026, 9, 4), date(2026, 9, 8)], str(W2))

# ── 4) Tageshälften und Gleichstand ─────────────────────────────────────────
def ent(t, suw, pos, vv=0.0, hit=False, d=D):
    return {"ticker": t, "suw": suw, "pool_position": pos, "v": vv, "hit": hit, "d": d, "date": dmy(d)}


five = [ent("A", 5, 1), ent("B", 4, 2), ent("C", 3, 3), ent("D", 2, 4), ent("E", 1, 5)]
u, l = S.day_halves(five)
check("09 ungerade Zahl: mittlerer fällt weg", [e["ticker"] for e in u] == ["A", "B"]
      and [e["ticker"] for e in l] == ["D", "E"])
check("10 < 4 Werte → Tag entfällt", S.day_halves(five[:3]) is None)
tie = [ent("Z", 2, 5), ent("Y", 2, 1), ent("X", 2, 1), ent("W", 1, 9)]
u, l = S.day_halves(tie)
check("11 Gleichstand: bessere pool_position, dann Ticker", [e["ticker"] for e in u] == ["X", "Y"]
      and [e["ticker"] for e in l] == ["Z", "W"], str([e["ticker"] for e in u + l]))
nopos = [ent("A", 3, None), ent("B", 3, 2), ent("C", 1, 3), ent("D", 0, 4)]
u, _l = S.day_halves(nopos)
check("12 fehlende pool_position sortiert nach hinten", [e["ticker"] for e in u] == ["B", "A"])

# ── 5) Auswertungskern an Mini-Daten ────────────────────────────────────────
days = [date(2026, 9, 1) + timedelta(days=i) for i in range(4)]
ents = []
for i, d in enumerate(days):
    # oben V = 10+i, unten V = i → Tagesdifferenz immer 10; Treffer oben ja, unten nein
    ents += [ent(f"U{i}a", 9, 1, 10 + i, True, d), ent(f"U{i}b", 8, 2, 10 + i, True, d),
             ent(f"L{i}a", 1, 3, i, False, d), ent(f"L{i}b", 0, 4, i, False, d)]
hc = S._haircut_fn()
r = S.evaluate(ents, hc)
check("13 Hauptzahl 1 = Mittel der Tagesdifferenzen (10)", abs(r["hz1"]["wert"] - 10) < 1e-9)
check("14 Hauptzahl 2 = Treffer-Anteil oben − unten (100 Pkt)", abs(r["hz2"]["wert"] - 100) < 1e-9)
check("15 Bootstrap konstante Differenz → KI = [10;10]", r["hz1"]["ki95"] == [10.0, 10.0] or
      tuple(r["hz1"]["ki95"]) == (10.0, 10.0))
check("16 Zeithälften am unteren Median", r["median_datum"] == "2026-09-02" and r["tage_h1"] == 2 and r["tage_h2"] == 2)
check("17 ohne 3 Extreme: Tage mit leerer Hälfte entfallen, Rest = 10",
      abs(r["hz1"]["ohne_3_extreme"] - 10) < 1e-9 and len(r["extreme"]) == 3)
r2 = S.evaluate(list(reversed(ents)), hc)
check("18 deterministisch (Eingabe-Reihenfolge egal)", r2["hz1"] == r["hz1"] and r2["hz2"] == r["hz2"])
check("19 Urteil konstante +10 → trägt stark", S.verdict(r) == "trägt stark")
neg = [dict(e, v=-e["v"]) for e in ents]
check("20 Urteil negative Differenz → trägt nicht", S.verdict(S.evaluate(neg, hc)) == "trägt nicht")
g = 10.0
exp = ((1 + g / 100) * (1 - 0.019 / 2) / (1 + 0.019 / 2) - 1) * 100
check("21 Kosten 1,9 % multiplikativ wie apply_round_trip_haircut (Repo rundet auf 2 Stellen)", hc(g, 1.9) == round(exp, 2), f"{hc(g, 1.9)} {exp}")

# ── 6) outcome_entry und FINRA-Parser ───────────────────────────────────────
bars = [{"d": "x", "o": 10, "h": 10, "l": 9, "c": 10} for _ in range(11)]
bars[1]["o"] = 10.0
bars[5]["h"] = 13.0
bars[10]["c"] = 11.0
why, e = S.outcome_entry({"grund": None, "bars": bars})
check("22 V = Schluss Tag 10 / Eröffnung Tag 1 − 1; Treffer bei Hoch ≥ 1,30 × Eröffnung",
      why is None and abs(e["v"] - 10.0) < 1e-9 and e["hit"] is True)
bars2 = [dict(b) for b in bars]
bars2[5]["h"] = 12.99
check("23 Hoch knapp unter 1,30 → kein Treffer", S.outcome_entry({"grund": None, "bars": bars2})[1]["hit"] is False)
check("24 grund gesetzt → ohne vollständige Kurse", S.outcome_entry({"grund": "ticker_ohne_kursdaten", "bars": []})[0]
      == "grund:ticker_ohne_kursdaten")
txt = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n20260915|ABC|1234.0|0|5000|B,Q,N\n20260915|ABCD|7|0|9|Q\n1234\n"
check("25 FINRA-Parser exakte Schreibweise", S.parse_finra(txt, {"ABC", "XYZ"}) == {"ABC": 1234.0})


# ── 7) Datumsriegel und Betriebsart test ────────────────────────────────────
def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


check("26 Riegel nachrechnen", S.in_mode(date(2026, 10, 23), "nachrechnen") and not S.in_mode(date(2026, 10, 24), "nachrechnen"))
check("27 Riegel test", S.in_mode(date(2026, 10, 24), "test") and not S.in_mode(date(2026, 10, 23), "test"))

with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    exp_p, out_p = td / "export.jsonl", td / "outcome.jsonl"
    old_d, new_d = date(2026, 10, 23), date(2026, 10, 26)
    write_jsonl(exp_p, [
        {"provenance": "forward", "ticker": "OLD", "date": dmy(old_d), "pool_position": 1},
        {"provenance": "forward", "ticker": "NEW", "date": dmy(new_d), "pool_position": 1},
        {"provenance": "bootstrap", "ticker": "BOO", "date": dmy(old_d), "pool_position": 2},
    ])
    pn = S.load_population(exp_p, "nachrechnen")
    pt = S.load_population(exp_p, "test")
    check("28 Population nachrechnen nur ≤ 23.10, nur forward", [p["ticker"] for p in pn] == ["OLD"])
    check("29 Population test nur ≥ 24.10", [p["ticker"] for p in pt] == ["NEW"])

    class Boom(Exception):
        pass

    def boom(*a, **k):
        raise Boom("darf nicht aufgerufen werden")

    # outcome-Zeilen für 3 Testtage; Kurse als Köder
    rows = [{"ticker": "NEW", "date": dmy(new_d + timedelta(days=i)), "grund": None,
             "bars": [{"o": 1, "h": 1, "l": 1, "c": 1}] * 11} for i in range(3)]
    rows.append({"ticker": "OLD", "date": dmy(old_d), "grund": None, "bars": []})
    write_jsonl(out_p, rows)
    saved = (S.outcome_entry, S.evaluate, S.suw_value, S.load_outcomes)
    S.outcome_entry = S.evaluate = S.suw_value = S.load_outcomes = boom
    try:
        res = S.run("test", export_path=exp_p, outcome_path=out_p, fetch_finra=boom, fetch_yahoo=boom,
                    sleep=boom)
        ok = res["status"] == "nur_zaehler" and res["ausloeser"]["tage_mit_schluss_tag10"] == 3
        check("30 test vor Auslöser: nur Zähler, kein Abruf, keine Rendite", ok, str(res))
        old_trig = S.TRIGGER_DAYS
        S.TRIGGER_DAYS = 3
        aborted = []
        try:
            for kw in ({},  # außerhalb GitHub → Ort-Sperre
                       {"env": {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main"},
                        "handover_path": exp_p}):  # Handover ohne Block → MD5-Sperre
                try:
                    S.run("test", export_path=exp_p, outcome_path=out_p, fetch_finra=boom, fetch_yahoo=boom,
                          sleep=boom, freeze_kwargs=kw)
                except S.SuwAbort as exc:
                    aborted.append(str(exc))
        finally:
            S.TRIGGER_DAYS = old_trig
        check("31 test mit Auslöser: Ort-/MD5-Sperre greift vor jedem Datenzugriff",
              len(aborted) == 2 and "main" in aborted[0] and "Freeze-Block" in aborted[1], str(aborted))
    finally:
        S.outcome_entry, S.evaluate, S.suw_value, S.load_outcomes = saved
    check("32 count_trigger_days zählt nur ≥ 24.10 und nur Zeilen ohne grund",
          S.count_trigger_days(out_p, "test") == 3)

# ── 8) nachrechnen end-to-end mit Fake-Abrufen ──────────────────────────────
with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    exp_p, out_p = td / "export.jsonl", td / "outcome.jsonl"
    ds = [date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)]
    tick = ["AA", "BB", "CC", "DD"]
    exp_rows, out_rows = [], []
    for d in ds:
        for j, t in enumerate(tick):
            exp_rows.append({"provenance": "forward", "ticker": t, "date": dmy(d), "pool_position": j + 1})
            b = [{"o": 10.0, "h": 10.0, "l": 10.0, "c": 10.0} for _ in range(11)]
            b[10]["c"] = 10.0 + (4 - j)  # AA bestes V
            out_rows.append({"ticker": t, "date": dmy(d), "grund": None, "bars": b})
    # Köder im Blindfenster: darf nicht gelesen werden
    exp_rows.append({"provenance": "forward", "ticker": "AA", "date": "26.10.2026", "pool_position": 1})
    out_rows.append({"ticker": "AA", "date": "26.10.2026", "grund": None, "bars": []})
    write_jsonl(exp_p, exp_rows)
    write_jsonl(out_p, out_rows)
    calls = {"finra": [], "yahoo": []}
    level = {"AA": 30.0, "BB": 20.0, "CC": 10.0, "DD": 5.0}  # Kurs D relativ zu R

    def ff(d):
        calls["finra"].append(d)
        return "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n" + "".join(
            f"x|{t}|100|0|200|Q\n" for t in tick), "ok"

    def fy(t, start, end_excl):
        calls["yahoo"].append((t, end_excl))
        out = {}
        x = start
        while x < end_excl:
            out[x] = 100.0
            x += timedelta(days=1)
        for d in ds:
            out[d] = 100.0 * (1 + level[t] / 100)
        return out, "ok"

    res = S.run("nachrechnen", export_path=exp_p, outcome_path=out_p, fetch_finra=ff, fetch_yahoo=fy,
                sleep=lambda s: None)
    check("33 nachrechnen: kein Abruf nach 23.10", max(calls["finra"]) <= date(2026, 10, 23)
          and all(e <= date(2026, 10, 24) for _, e in calls["yahoo"]))
    check("34 nachrechnen: Population ohne Blindfenster", res["einstiege"] == 16, str(res.get("einstiege")))
    check("35 nachrechnen: Status ok, deterministisch", res["status"] == "ok" and res["deterministisch"] is True,
          str(res.get("status")))
    # Kurs 100 an allen Tagen außer den Einstiegstagen (100 × (1 + Level));
    # SUW-Reihenfolge je Tag AA > BB > CC > DD. V: AA 40 %, BB 30 %, CC 20 %,
    # DD 10 % → oben Mittel 35, unten 15 → Differenz 20 Pkt an jedem Tag.
    check("36 Hauptzahl 1 im Mini-Fall = +20 Pkt (V in %)", abs(res["hz1"]["wert"] - 20.0) < 1e-9,
          str(res["hz1"]["wert"]))

    def fy_fail(t, start, end_excl):
        return (None, "fehler:YFRateLimitError") if t in ("AA",) else fy(t, start, end_excl)

    res_f = S.run("nachrechnen", export_path=exp_p, outcome_path=out_p, fetch_finra=ff, fetch_yahoo=fy_fail,
                  sleep=lambda s: None)
    check("37 > 5 % Ticker ohne Kurse → nicht auswertbar", res_f["status"] == "nicht_auswertbar"
          and res_f["yahoo_ohne_kurse"] == {"AA": "fehler:YFRateLimitError"})

    def ff_miss(d):
        return (None, "http_404") if d == date(2026, 10, 16) else ff(d)

    res_m = S.run("nachrechnen", export_path=exp_p, outcome_path=out_p, fetch_finra=ff_miss, fetch_yahoo=fy,
                  sleep=lambda s: None)
    check("38 fehlende FINRA-Datei wird genannt", "2026-10-16" in res_m["finra_dateien"]["fehlend"])

check("39 Soll/Toleranz vor dem Lauf festgeschrieben",
      S.SOLL["hz1"] == 4.48 and S.SOLL["hz2"] == 3.81 and S.SOLL["n_value"] == 664
      and S.TOL == {"hz1": 0.3, "hz2": 0.5, "n_value": 3})
src = (ROOT / "scripts" / "suw_eval.py").read_text(encoding="utf-8")
check("40 Kursart auto_adjust=False (ohne Dividenden-Bereinigung)", "auto_adjust=False" in src
      and "auto_adjust=True" not in src)
check("41 nur CNMS-Datei", "CNMSshvol" in src and "FNSQ" not in src and "FNQC" not in src)
fr = src[src.index("def freeze_run("):]
check("42 Schreibwege: nur --out und (nur freeze_run) eval_results anhängen",
      src.count("write_text") == 1 and src.count('open(rp, "a"') == 1 and 'open(rp, "a"' in fr
      and src.count(', "w"') == 0)

# ── 9) Teil B: Freeze-Block, Sperre, F1/F2 ──────────────────────────────────
HANDOVER = ROOT / "SESSION_HANDOVER.md"
try:
    md5 = S.read_freeze(HANDOVER)
    ok43 = md5 == S.FREEZE_BLOCK_MD5
except S.SuwAbort as exc:
    ok43, md5 = False, str(exc)
check("43 MD5-Pin des SUW-Freeze-Blocks + Pflicht-Textstellen", ok43, md5)
blk = S.extract_freeze_block(HANDOVER.read_text(encoding="utf-8"))
lesarten_src = src[src.index("  L1 Handelstage"):src.index("\nDatenquellen-Robustheit")].rstrip()
check("44 Lesarten L1–L9 wörtlich im Block", lesarten_src in blk)
check("45 Regeltext des open_items wörtlich im Block",
      "R = Summe(sv_t × c_t) / Summe(sv_t)." in blk and "SUW = c_D / R − 1." in blk
      and "Gleichstand: bessere pool_position, dann Ticker alphabetisch." in blk)

GH = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main"}


def trading_days(start: date, n: int) -> list:
    out, x = [], start
    while len(out) < n:
        if S.is_trading_day(x):
            out.append(x)
        x += timedelta(days=1)
    return out


def build_test_world(td: pathlib.Path, n_days: int):
    exp_p, out_p = td / "export.jsonl", td / "outcome.jsonl"
    ds = trading_days(date(2026, 10, 26), n_days)
    tick = ["AA", "BB", "CC", "DD"]
    lvl = {"AA": 30.0, "BB": 20.0, "CC": 10.0, "DD": 5.0}
    exp_rows, out_rows = [], []
    for d in ds:
        for j, t in enumerate(tick):
            exp_rows.append({"provenance": "forward", "ticker": t, "date": dmy(d), "pool_position": j + 1,
                             "market_regime": "neutral"})
            b = [{"o": 10.0, "h": 10.0, "l": 10.0, "c": 10.0} for _ in range(11)]
            b[10]["c"] = 10.0 + (4 - j)
            out_rows.append({"ticker": t, "date": dmy(d), "grund": None, "bars": b})
    write_jsonl(exp_p, exp_rows)
    write_jsonl(out_p, out_rows)

    def ff(d):
        return ("Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
                + "".join(f"x|{t}|100|0|200|Q\n" for t in tick)), "ok"

    def fy(t, start, end_excl):
        out, x = {}, start
        while x < end_excl:
            out[x] = 100.0
            x += timedelta(days=1)
        for d in ds:
            out[d] = 100.0 * (1 + lvl[t] / 100)
        return out, "ok"
    return exp_p, out_p, ff, fy, len(ds)


with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    exp_p, out_p, ff, fy, nd = build_test_world(td, 45)
    res_p = td / "eval_results.jsonl"
    res_p.write_text(json.dumps({"family": "x", "test_id": "x1"}) + "\n", encoding="utf-8")
    old_trig = S.TRIGGER_DAYS
    S.TRIGGER_DAYS = 45
    try:
        kw = {"env": GH, "handover_path": HANDOVER, "results_path": res_p}
        r = S.run("test", export_path=exp_p, outcome_path=out_p, fetch_finra=ff, fetch_yahoo=fy,
                  sleep=lambda s: None, freeze_kwargs=kw)
        rows = [json.loads(x) for x in res_p.read_text(encoding="utf-8").splitlines()]
        suw = [x for x in rows if x.get("family") == "suw"]
        f1 = next(x for x in suw if x["test_id"] == "suw_f1")
        f2 = next(x for x in suw if x["test_id"] == "suw_f2")
        check("46 Auswertung: 2 Zeilen family suw angehängt, Vorzeile unberührt",
              r["status"] == "ausgewertet" and len(rows) == 3 and rows[0]["test_id"] == "x1" and len(suw) == 2)
        check("47 F1: Hauptzahl 1 = 20, Bereich [20;20], Beleg", abs(f1["statistic"]["wert"] - 20) < 1e-9
              and f1["statistic"]["ci95"] == [20.0, 20.0] and f1["verdict"] == "Beleg", f1["verdict_reason"])
        exp_net = (S._haircut_fn()(40.0) + S._haircut_fn()(30.0)) / 2
        check("48 F2: Mittel N1 obere Hälfte (−4 % multiplikativ), Beleg",
              abs(f2["statistic"]["wert"] - exp_net) < 1e-9 and f2["verdict"] == "Beleg", f2["verdict_reason"])
        check("49 Holm k = 2, MD5 und Bestätigungstests gesamt in der Zeile",
              f1["freeze_block_md5"] == S.FREEZE_BLOCK_MD5 and f1["confirmatory_tests_total"] == 3
              and f1["holm_significant"] is True)
        try:
            S.run("test", export_path=exp_p, outcome_path=out_p, fetch_finra=boom, fetch_yahoo=boom,
                  sleep=boom, freeze_kwargs=kw)
            locked = False
        except S.SuwAbort as exc:
            locked = "bereits" in str(exc)
        check("50 Sperre: zweiter Lauf bricht vor jedem Abruf ab", locked)
    finally:
        S.TRIGGER_DAYS = old_trig

with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    exp_p, out_p, ff, fy, nd = build_test_world(td, 12)
    res_p = td / "eval_results.jsonl"
    old_trig = S.TRIGGER_DAYS
    S.TRIGGER_DAYS = 12
    try:
        S.run("test", export_path=exp_p, outcome_path=out_p, fetch_finra=ff, fetch_yahoo=fy,
              sleep=lambda s: None, freeze_kwargs={"env": GH, "handover_path": HANDOVER, "results_path": res_p})
    finally:
        S.TRIGGER_DAYS = old_trig
    v = {json.loads(x)["test_id"]: json.loads(x)["verdict"] for x in res_p.read_text().splitlines()}
    check("51 Floor: < 40 Tage bzw. < 40 obere Zeilen → nicht auswertbar", v == {
        "suw_f1": "nicht auswertbar", "suw_f2": "nicht auswertbar"}, str(v))

check("52 Auslöser-Konstante 60 Einstiegstage", S.TRIGGER_DAYS == 60)
dg = (ROOT / "scripts" / "health_check_digest.py").read_text(encoding="utf-8")
check("53 Digest-Zähler SUW: nur Zählung, eigener Fail-soft-Guard",
      "suw_eval.count_trigger_days(" in dg and "SUW-Zähler unerwartet" in dg and "freeze_run" not in dg)

print()
if FAILS:
    print(f"FEHLER: {len(FAILS)} Test(s) rot: {FAILS}")
    sys.exit(1)
print("Alle Tests grün.")
