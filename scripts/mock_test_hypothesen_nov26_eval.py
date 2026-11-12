#!/usr/bin/env python3
"""Tests für scripts/hypothesen_nov26_eval.py — NUR synthetische Daten.

Kein Zugriff auf matured_backtest_export.jsonl, outcome_path.jsonl oder
inst_ownership_history.json (Blindheit). Aus SESSION_HANDOVER.md wird nur
der Freeze-Block-Text gelesen (MD5-Pin, keine Daten).

Gruppen:
  1  Freeze-Block auf dem Stand: MD5-Pin + Zahlen-Gegenprobe; MD5-Abweichung → Abbruch
  2  Lauf-Ort-Guard
  3  Zielgröße A.1: Gap über das Ziel (+30 % angerechnet), Open Tag 1 fehlt,
     grund gesetzt, bars unvollständig, Close Tag 10 fehlt (nur H-G)
  4  Prädiktoren: inst-Punkt (größtes date ≤ D, späterer Punkt ignoriert),
     kein Punkt; 8-K ja/nein, nicht gesammelt, truncated gezählt
  5  Bekannte Ergebnisse: alle drei „Beleg“ (Richtung je Hypothese)
  6  Kein Regime prüfbar → „bedingt“; genau ein prüfbares Regime → „Beleg“ (Block A.8)
  7  Floor verfehlt → „nicht auswertbar“ und p = 1 im Holm-Schritt
  8  Einseitiger Wilcoxon-p nach Block B.4 (Handrechnung) + Gegenprobe
  9  Netto-Funktion = backtest_history.apply_round_trip_haircut (AST-Quelle)
 10  Sperre greift; Stufe 2: Abbruch ohne Voraussetzungen / vor Auslöser
 11  Stufe 1 verwirft Zeilen ≥ 24.10.2026 beim Einlesen; Zählung ≠ Block E → Abbruch
 12  Determinismus: gleicher Input → byte-gleiche eval_results-Ausgabe
 13  Push-Text ohne Ergebniszahlen
"""
from __future__ import annotations

import json
import math
import pathlib
import random
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import hypothesen_nov26_eval as hy  # noqa: E402
from stats_helpers import _normal_cdf  # noqa: E402

_fails: list[str] = []
ENV = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main"}
NOW = __import__("datetime").datetime(2026, 11, 13, 12, 0, tzinfo=__import__("datetime").timezone.utc)


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


def _block_text() -> str:
    text = (ROOT / "SESSION_HANDOVER.md").read_text(encoding="utf-8")
    return hy.extract_freeze_block(text)


# ── Synthetische Daten ──────────────────────────────────────────────────
def _bars(o1, max_h, c10, d_close=None):
    d_close = o1 * 0.98 if d_close is None else d_close
    bars = [{"d": "D", "o": d_close, "h": d_close, "l": d_close, "c": d_close}]
    for k in range(1, 11):
        h = max_h if k == 5 else o1 * 1.01
        c = c10 if k == 10 else o1
        bars.append({"d": f"T{k}", "o": o1 if k == 1 else o1, "h": h, "l": o1 * 0.9, "c": c})
    return bars, d_close


def make_dataset(n_hit=60, n_miss=200, regime=lambda i, hit: "neutral", seed=1,
                 start_day=1, hk_hit_share=0.8, hk_miss_share=0.2, inst_hit=(0.05, 0.35),
                 inst_miss=(0.55, 0.95)):
    """Treffer: Hoch +35 % ab Open Tag 1, Halten +5 %; Nicht-Treffer: Hoch +20 %,
    Halten zufällig −15…+15 %. Inst: Treffer niedrig, Nicht-Treffer hoch.
    8-K: Treffer häufiger ja."""
    rng = random.Random(seed)
    export, op, inst = [], [], {}
    from datetime import date, timedelta
    d0 = date(2026, 7, 21)
    i = 0
    for kind, n in (("hit", n_hit), ("miss", n_miss)):
        for _ in range(n):
            t = f"T{i:04d}"
            d = d0 + timedelta(days=(i % 90))
            ds = d.strftime("%d.%m.%Y")
            hit = kind == "hit"
            o1 = 10.0
            c10 = o1 * (1.05 if hit else 1 + rng.uniform(-0.15, 0.15))
            bars, cd = _bars(o1, o1 * (1.35 if hit else 1.20), c10)
            mg = (max(b["h"] for b in bars[1:]) / cd - 1) * 100
            share = hk_hit_share if hit else hk_miss_share
            export.append({"ticker": t, "date": ds, "provenance": "forward", "entry_price": 9.8 + i * 0.01,
                           "market_regime": regime(i, hit),
                           "entry_past_return_5d": rng.uniform(-10, 10),
                           "material_8k_events": {"collected": True, "truncated": False,
                                                  "events": [{"x": 1}] if rng.random() < share else []}})
            op.append({"ticker": t, "date": ds, "grund": None, "bars": bars, "close_d": cd,
                       "max_gain_from_entry_pct": mg, "split_im_fenster": False,
                       "dividende_im_fenster": False})
            lo, hi_ = inst_hit if hit else inst_miss
            inst[t] = [{"date": (d - timedelta(days=3)).isoformat(), "inst_ownership": rng.uniform(lo, hi_)},
                       {"date": (d + timedelta(days=2)).isoformat(), "inst_ownership": 5.0}]
            i += 1
    return export, op, inst


def write_files(tmp: pathlib.Path, export, op, inst, results_rows=(), block=None):
    (tmp / "ho.md").write_text("# x\n\n" + (block or _block_text()) + "\n### Ende\n", encoding="utf-8")
    (tmp / "exp.jsonl").write_text("".join(json.dumps(r) + "\n" for r in export), encoding="utf-8")
    (tmp / "op.jsonl").write_text("".join(json.dumps(r) + "\n" for r in op), encoding="utf-8")
    (tmp / "inst.json").write_text(json.dumps(inst), encoding="utf-8")
    (tmp / "res.jsonl").write_text("".join(json.dumps(r) + "\n" for r in results_rows), encoding="utf-8")


def counts_of(export, op, inst, stage=1):
    data = {"window": hy.freeze_eval._dedup_rows([r for r in export if hy._in_stage(hy._parse_dmy(r["date"]), stage)]),
            "op": {(z["ticker"], z["date"]): z for z in op}, "inst": inst}
    b = hy.build_rows(data)
    return {"n_window": b["n_window"], "n_usable_a1": b["n_usable_a1"], "n_hi": len(b["rows"]["hi"]),
            "n_hk": len(b["rows"]["hk"]), "n_hk_ja": sum(r["_x"] for r in b["rows"]["hk"])}


def run(tmp, export, op, inst, stage=1, env=ENV, push=None, expected=None):
    return hy.run_stage(stage, handover_path=tmp / "ho.md", results_path=tmp / "res.jsonl",
                        export_path=tmp / "exp.jsonl", outcome_path=tmp / "op.jsonl",
                        inst_path=tmp / "inst.json", now=NOW, env=env, send_push=push,
                        s1_expected=expected if expected is not None else counts_of(export, op, inst, stage))


def _abort(fn) -> str | None:
    try:
        fn()
    except hy.HypAbort as exc:
        return str(exc)
    return None


# ── Tests ───────────────────────────────────────────────────────────────
def test_freeze():
    print("1 Freeze-Block")
    check("MD5-Pin + Gegenprobe auf main-Stand", hy.read_freeze(ROOT / "SESSION_HANDOVER.md") == hy.FREEZE_BLOCK_MD5)
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        e, o, i = make_dataset()
        write_files(tmp, e, o, i, block=_block_text().replace("Seed = 42", "Seed = 43", 1))
        msg = _abort(lambda: run(tmp, e, o, i))
        check("MD5-Abweichung → Abbruch", msg is not None and "MD5" in msg, msg)
        check("bei Abbruch nichts geschrieben", (tmp / "res.jsonl").read_text() == "")


def test_location():
    print("2 Lauf-Ort-Guard")
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        e, o, i = make_dataset()
        write_files(tmp, e, o, i)
        msg = _abort(lambda: run(tmp, e, o, i, env={"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/x"}))
        check("nicht main → Abbruch", msg is not None and "main" in msg, msg)


def test_a1_and_predictors():
    print("3/4 Zielgröße A.1 und Prädiktoren")
    from datetime import date
    bars, cd = _bars(10.0, 10.0, 10.0)
    bars[3] = {"d": "T3", "o": 14.0, "h": 15.0, "l": 13.0, "c": 14.5}   # Gap über das Ziel
    why, e = hy.a1_entry({"grund": None, "bars": bars, "close_d": cd})
    check("Gap: Treffer, g = 50", why is None and e["hit"] and abs(e["g"] - 50.0) < 1e-9, (why, e and e["g"]))
    built = hy.build_rows({"window": [{"ticker": "A", "date": "22.07.2026", "market_regime": "bull",
                                       "material_8k_events": {"collected": True, "events": []}}],
                           "op": {("A", "22.07.2026"): {"grund": None, "bars": bars, "close_d": cd}},
                           "inst": {}})
    r = built["rows"]["hg"][0]
    check("Gap: rule = 30 (nur +30 % angerechnet), hold = Close T10/Open T1 − 1 = 0",
          r["_rule"] == 30.0 and abs(r["_hold"]) < 1e-9, (r["_rule"], r["_hold"]))
    b2, _ = _bars(10.0, 12.0, 10.0)
    b2[1]["o"] = None
    check("Open Tag 1 fehlt → open_tag1_fehlt", hy.a1_entry({"grund": None, "bars": b2})[0] == "open_tag1_fehlt")
    check("grund gesetzt → grund:<Wert>", hy.a1_entry({"grund": "tag_fehlt", "bars": b2})[0] == "grund:tag_fehlt")
    check("Zeile fehlt → zeile_fehlt", hy.a1_entry(None)[0] == "zeile_fehlt")
    b3, _ = _bars(10.0, 12.0, 10.0)
    check("10 statt 11 bars → bars_unvollstaendig", hy.a1_entry({"grund": None, "bars": b3[:10]})[0] == "bars_unvollstaendig")
    b4, _ = _bars(10.0, 12.0, 10.0)
    b4[10]["c"] = float("nan")
    built = hy.build_rows({"window": [{"ticker": "B", "date": "22.07.2026"}],
                           "op": {("B", "22.07.2026"): {"grund": None, "bars": b4}},
                           "inst": {"B": [{"date": "2026-07-20", "inst_ownership": 0.4}]}})
    check("Close Tag 10 fehlt → nur H-G aus", not built["rows"]["hg"] and len(built["rows"]["hi"]) == 1
          and built["excl"]["hg"] == {"close_tag10_fehlt": 1}, built["excl"])
    check("8-K Feld fehlt → nicht_gesammelt", built["excl"]["hk"] == {"nicht_gesammelt": 1})
    inst = {"C": [{"date": "2026-07-10", "inst_ownership": 0.2}, {"date": "2026-07-20", "inst_ownership": 0.3},
                  {"date": "2026-07-23", "inst_ownership": 0.9}, {"date": "kaputt", "inst_ownership": 0.1}]}
    v, age, bad = hy._inst_point(inst, "C", date(2026, 7, 22))
    check("inst: größtes date ≤ D, späterer Punkt ignoriert", v == 0.3 and age == 2 and bad == 1, (v, age, bad))
    check("inst: kein Punkt ≤ D → None", hy._inst_point(inst, "C", date(2026, 7, 1))[0] is None)
    check("inst: Rohwert > 1 bleibt", hy._inst_point({"D": [{"date": "2026-07-01", "inst_ownership": 1.187}]},
                                                       "D", date(2026, 7, 2))[0] == 1.187)
    bb, _ = _bars(10.0, 12.0, 10.0)
    built = hy.build_rows({"window": [
        {"ticker": "E", "date": "22.07.2026", "material_8k_events": {"collected": True, "truncated": True, "events": [{}]}},
        {"ticker": "F", "date": "22.07.2026", "material_8k_events": {"collected": False, "events": [{}]}}],
        "op": {("E", "22.07.2026"): {"grund": None, "bars": bb}, ("F", "22.07.2026"): {"grund": None, "bars": bb}},
        "inst": {}})
    check("8-K: ja + truncated gezählt; collected false → nicht_gesammelt",
          [r["_x"] for r in built["rows"]["hk"]] == [1] and built["hk_truncated"] == 1
          and built["excl"]["hk"] == {"nicht_gesammelt": 1}, built["excl"]["hk"])


def _by(rows):
    return {r["test_id"]: r for r in rows}


def test_known_results():
    print("5 Bekannte Ergebnisse (alle Beleg) / 6 Regime-Regeln / 7 Floor")
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        e, o, i = make_dataset(regime=lambda k, hit: "neutral" if k % 7 else "bull")
        write_files(tmp, e, o, i)
        rows = _by(run(tmp, e, o, i))
        check("drei Zeilen hg_s1/hi_s1/hk_s1", set(rows) == {"hg_s1", "hi_s1", "hk_s1"}, list(rows))
        check("H-G Beleg (Regel besser)", rows["hg_s1"]["verdict"] == "Beleg", rows["hg_s1"]["verdict_reason"])
        check("H-G mean Δ > 0", rows["hg_s1"]["statistic"]["mean_delta"] > 0)
        check("H-I Beleg (AUC < 0,5)", rows["hi_s1"]["verdict"] == "Beleg" and rows["hi_s1"]["statistic"]["auc"] < 0.5,
              rows["hi_s1"]["verdict_reason"])
        check("H-K Beleg (AUC > 0,5)", rows["hk_s1"]["verdict"] == "Beleg" and rows["hk_s1"]["statistic"]["auc"] > 0.5,
              rows["hk_s1"]["verdict_reason"])
        check("Regime: neutral prüfbar, bull nicht", rows["hi_s1"]["regime_split"]["detail"]["neutral"]["status"] == "plausibel"
              and rows["hi_s1"]["regime_split"]["detail"]["bull"]["status"] == "nicht_pruefbar")
        check("Holm k = 3, α = 0,05", rows["hg_s1"]["holm"]["k"] == 3 and rows["hg_s1"]["holm"]["alpha"] == 0.05)
        check("Holm-adjustierter p in jeder Zeile", all("p_holm_adjusted" in rows[k] for k in rows))
        check("Pflichtangaben vorhanden", all(k in rows["hk_s1"] for k in (
            "excluded_a1", "excluded_hypothesis", "p_raw", "p_holm_input", "regime_split", "cluster_double_run",
            "data_hash_files", "script_commit_hash", "bootstrap_n", "bootstrap_seed", "n_split_im_fenster",
            "n_dividende_im_fenster", "confirmatory_tests_total")))
        check("Vergleich ab Close D berichtet", "ab_close_d" in rows["hg_s1"]["nur_berichtet"]
              and "ab_close_d" in rows["hi_s1"]["nur_berichtet"])
        check("Bootstrap N/Seed aus Block", rows["hg_s1"]["bootstrap_n"] == 2000 and rows["hg_s1"]["bootstrap_seed"] == 42)
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        e, o, i = make_dataset(regime=lambda k, hit: None)
        write_files(tmp, e, o, i)
        rows = _by(run(tmp, e, o, i))
        check("kein Regime prüfbar (alle unbekannt) → bedingt (alle drei)",
              all(rows[k]["verdict"] == "bedingt" for k in rows), {k: rows[k]["verdict"] for k in rows})
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        e, o, i = make_dataset(n_hit=30, n_miss=200)
        write_files(tmp, e, o, i)
        rows = _by(run(tmp, e, o, i))
        check("Floor verfehlt → nicht auswertbar, p = 1 im Holm",
              all(rows[k]["verdict"] == "nicht auswertbar" and rows[k]["p_holm_input"] == 1.0 for k in rows),
              {k: (rows[k]["verdict"], rows[k]["p_holm_input"]) for k in rows})
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        e, o, i = make_dataset(hk_hit_share=0.1, hk_miss_share=0.1)
        for r in e[:300]:
            r["material_8k_events"]["events"] = []
        write_files(tmp, e, o, i)
        rows = _by(run(tmp, e, o, i))
        check("H-K: < 40 Zeilen „ja“ → nicht auswertbar", rows["hk_s1"]["verdict"] == "nicht auswertbar"
              and rows["hk_s1"]["p_holm_input"] == 1.0)


def test_wilcoxon():
    print("8 Einseitiger Wilcoxon-p (B.4)")
    rule = [30.0, 30.0, 30.0, 5.0, 2.0, 30.0]
    hold = [10.0, 20.0, 40.0, 5.0, 2.0, 25.0]
    w = hy.wilcoxon_one_sided(rule, hold)
    # d = 20, 10, −10, 0, 0, 5 → |d| ohne Nullen: 20,10,10,5 → Ränge 4, 2.5, 2.5, 1; W⁺ = 4+2.5+1 = 7.5
    n, wp = 4, 7.5
    var = n * (n + 1) * (2 * n + 1) / 24 - (2 ** 3 - 2) / 48
    p = 1 - _normal_cdf((wp - n * (n + 1) / 4 - 0.5) / math.sqrt(var))
    check("W⁺ = 7,5, n = 4, 2 Nullen", w["w_plus"] == 7.5 and w["n_nonzero"] == 4 and w["n_zero_dropped"] == 2, w)
    check("p einseitig = Formel B.4", abs(w["p_one_sided"] - p) < 1e-15, (w["p_one_sided"], p))
    w2 = hy.wilcoxon_one_sided([0.0, 0.0], [0.0, 0.0])
    check("keine Differenz ≠ 0 → p None", w2["p_one_sided"] is None)


def test_holm_adjusted():
    print("8b Holm-adjustierter p")
    adj, thr = hy.holm_adjusted({"hg": 0.01, "hi": 0.04, "hk": 0.03}, ["hg", "hi", "hk"])
    check("adj = 0,03 / 0,06 / 0,06", abs(adj["hg"] - 0.03) < 1e-12 and abs(adj["hk"] - 0.06) < 1e-12
          and abs(adj["hi"] - 0.06) < 1e-12, adj)
    check("Schwellen α/3, α/2, α", abs(thr["hg"] - 0.05 / 3) < 1e-12 and thr["hk"] == 0.025 and thr["hi"] == 0.05, thr)
    adj2, _ = hy.holm_adjusted({"hg": 1.0, "hi": 0.5}, ["hg", "hi"])
    check("Kappung auf 1", adj2["hg"] == 1.0 and adj2["hi"] == 1.0, adj2)


def test_haircut():
    print("9 Netto-Funktion")
    f = hy._haircut_fn()
    check("haircut(100) = round((2·0,98/1,02 − 1)·100, 2)", f(100.0) == round((2 * 0.98 / 1.02 - 1) * 100, 2), f(100.0))
    check("haircut(None) = None", f(None) is None)


def test_lock_and_stage2():
    print("10 Sperre / Stufe 2")
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        e, o, i = make_dataset()
        write_files(tmp, e, o, i, results_rows=[{"family": "hyp_nov26_s1", "test_id": "hg_s1", "verdict": "Beleg"}])
        msg = _abort(lambda: run(tmp, e, o, i))
        check("Sperre Stufe 1 greift", msg is not None and "hyp_nov26_s1" in msg, msg)
        msg = _abort(lambda: run(tmp, e, o, i, stage=2))
        check("Stufe 2 ohne Replikation/Paper C handelbar → Abbruch", msg is not None and "paper_c_replikation" in msg, msg)
        write_files(tmp, e, o, i, results_rows=[{"family": "paper_c_replikation", "test_id": "x"},
                                                {"family": "paper_c_handelbar", "test_id": "y"},
                                                {"family": "hyp_nov26_s1", "test_id": "hg_s1", "verdict": "Unklar"},
                                                {"family": "hyp_nov26_s1", "test_id": "hi_s1", "verdict": "nicht auswertbar"},
                                                {"family": "hyp_nov26_s1", "test_id": "hk_s1", "verdict": "Unklar"}])
        msg = _abort(lambda: run(tmp, e, o, i, stage=2))
        check("Stufe 2 mit k = 0 → Abbruch", msg is not None and "k = 0" in msg, msg)
        from datetime import date, timedelta
        e2, o2, i2 = make_dataset()
        for r in e2 + o2:
            d = hy._parse_dmy(r["date"]) + timedelta(days=100)
            r["date"] = d.strftime("%d.%m.%Y")
        write_files(tmp, e2, o2, i2, results_rows=[{"family": "paper_c_replikation", "test_id": "x"},
                                                   {"family": "paper_c_handelbar", "test_id": "y"},
                                                   {"family": "hyp_nov26_s1", "test_id": "hg_s1", "verdict": "Beleg"},
                                                   {"family": "hyp_nov26_s1", "test_id": "hi_s1", "verdict": "bedingt"},
                                                   {"family": "hyp_nov26_s1", "test_id": "hk_s1", "verdict": "Unklar"}])
        before = (tmp / "res.jsonl").read_text()
        msg = _abort(lambda: run(tmp, e2, o2, i2, stage=2))
        check("Stufe 2: n < 500 → Abbruch vor Auswertung", msg is not None and "Auslöser" in msg and "hk" not in msg, msg)
        check("Stufe 2: nichts geschrieben", (tmp / "res.jsonl").read_text() == before)


def test_window_and_counts():
    print("11 Fenster-Verwerfen / Zählung")
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        e, o, i = make_dataset()
        exp = counts_of(e, o, i)
        late_e = dict(e[0], ticker="LATE", date="24.10.2026")
        late_o = {"ticker": "LATE", "date": "24.10.2026", "grund": None, "bars": "MUELL"}
        e.append(late_e)
        o.append(late_o)
        write_files(tmp, e, o, i)
        data = hy.load_stage(1, export_path=tmp / "exp.jsonl", outcome_path=tmp / "op.jsonl", inst_path=tmp / "inst.json")
        check("Zeile ≥ 24.10. nicht eingelesen (Export + outcome_path)",
              all(r["ticker"] != "LATE" for r in data["window"]) and ("LATE", "24.10.2026") not in data["op"])
        rows = run(tmp, e, o, i, expected=exp)
        check("Lauf ignoriert Zeile ≥ 24.10.", rows[0]["n_window"] == exp["n_window"])
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        e, o, i = make_dataset()
        write_files(tmp, e, o, i)
        exp = dict(counts_of(e, o, i), n_window=999)
        msg = _abort(lambda: run(tmp, e, o, i, expected=exp))
        check("Zählung ≠ Block E → Abbruch", msg is not None and "Block E" in msg, msg)
        check("Block E im Skript = 672/669/508/669/164",
              hy.S1_EXPECTED == {"n_window": 672, "n_usable_a1": 669, "n_hi": 508, "n_hk": 669, "n_hk_ja": 164})


def test_determinism_and_push():
    print("12 Determinismus / 13 Push")
    import os
    outs = []
    os.environ["GITHUB_SHA"] = "0" * 40
    try:
        for _ in range(2):
            with tempfile.TemporaryDirectory() as t:
                tmp = pathlib.Path(t)
                e, o, i = make_dataset(seed=7)
                write_files(tmp, e, o, i)
                sent = []
                run(tmp, e, o, i, push=lambda title, body: sent.append((title, body)))
                outs.append(((tmp / "res.jsonl").read_bytes(), sent))
    finally:
        os.environ.pop("GITHUB_SHA", None)
    check("gleicher Input → byte-gleiche Ausgabe", outs[0][0] == outs[1][0])
    sent = outs[0][1]
    check("genau ein Push", len(sent) == 1, sent)
    body = sent[0][1] if sent else ""
    check("Push nennt Verdikte, keine Kommazahlen", "H-G" in body and not any(ch in body for ch in ("0.", "0,")),
          body)


def main() -> int:
    for fn in (test_freeze, test_location, test_a1_and_predictors, test_known_results, test_wilcoxon,
               test_holm_adjusted, test_haircut, test_lock_and_stage2, test_window_and_counts, test_determinism_and_push):
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle hypothesen_nov26-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
