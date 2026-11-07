"""Mock-Tests für scripts/paper_c_eval.py (Paper-C-Freeze, eingefroren 07.11.2026).

NUR SYNTHETISCHE DATEN. Kein Test öffnet ``matured_backtest_export.jsonl``
oder das echte ``eval_results.jsonl`` — alle Pfade zeigen auf Temp-Dateien.
Gelesen wird nur der Freeze-Block aus ``SESSION_HANDOVER.md`` (Text, keine
Ergebnisse).

Fälle (Auftrag 07.11.2026):
  a  klarer Effekt → Beleg (beide Ziele)
  b  Nulleffekt → Unklar (beide Ziele)
  c  Floor unterschritten → p = 1, „nicht auswertbar“, anderes Ziel unberührt
  d  Regime < 30 je Gruppe → „nicht prüfbar“ (eins → plausibel über den Rest;
     alle → „bedingt“)
  e  Seed-Determinismus (zweimal identisch)
  f  Abbruch bei vorhandener paper_c-Zeile — vor dem Öffnen des Exports
  g  Netto fehlt bei einem Teil → kein Crash, nur nachrangig, Urteil unberührt
Zusätzlich: Regime-Gegenrichtung → Unklar; Holm innen (2α/3) Schwellen;
Abbrüche (Ort, MD5, Block fehlt, Zählung weicht ab); End-to-End mit Push-
Stub (nur Verdikte, keine Zahlen); Quelltext-Reihenfolge Freeze-Check vor
Export-Zugriff.
"""
from __future__ import annotations

import copy
import json
import pathlib
import random
import re
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import paper_c_eval as pc  # noqa: E402

HANDOVER = ROOT / "SESSION_HANDOVER.md"
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
ENV_OK = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main"}
_fails: list[str] = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _fails.append(name)


PARAMS = pc.read_freeze(HANDOVER)
FAST = dict(PARAMS, bootstrap_n=200)   # schnelle Variante für die meisten Fälle


def _window_dates():
    d, out = date(2026, 7, 21), []
    while d <= date(2026, 10, 23):
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def make_rows(seed=1, mode="effect", regime=None, net_missing_share=0.4,
              n_window=672, n_epr_missing=4, extras=True):
    """Synthetischer Export. ``mode``: effect | null | floor | opposite_bull."""
    rng = random.Random(seed)
    dates = _window_dates()
    rows = []
    i = 0
    while len(rows) < n_window:
        d = dates[i % len(dates)]
        epr = rng.gauss(0, 10)
        if mode == "effect" or mode == "opposite_bull":
            mg = 30 + 2.5 * epr + rng.gauss(0, 4)
            r10 = 2 + 1.2 * epr + rng.gauss(0, 3)
        elif mode == "floor":
            mg = 5 + rng.random() * 20          # fast nie ≥ 30
            r10 = 2 + 1.2 * epr + rng.gauss(0, 3)
        else:  # null
            mg = 30 + rng.gauss(0, 25)
            r10 = 2 + rng.gauss(0, 12)
        reg = regime(i) if regime else ("neutral" if i % 2 else "bull")
        if mode == "opposite_bull" and reg == "bull":
            mg = 30 - 2.5 * epr + rng.gauss(0, 4)
        row = {"ticker": f"T{i:04d}", "date": d.strftime("%d.%m.%Y"),
               "provenance": "forward", "entry_price": round(5 + i * 0.013, 4),
               "entry_past_return_5d": epr, "max_gain_pct": mg, "return_10d": r10,
               "market_regime": reg}
        if rng.random() >= net_missing_share:
            row["max_gain_pct_net"] = mg - 4.0
        rows.append(row)
        i += 1
    if mode == "floor":
        for r in rows[:20]:
            r["max_gain_pct"] = 45.0           # genau 20 Treffer < Floor 40
    for r in rows[:n_epr_missing]:
        r["entry_past_return_5d"] = None
    if extras:
        rows.append(dict(rows[10]))                                        # Duplikat → Dedup
        rows.append(dict(rows[11], ticker="BF1", provenance="backfill"))   # falsche Herkunft
        rows.append(dict(rows[12], ticker="OUT1", date="20.07.2026"))      # vor dem Fenster
        rows.append(dict(rows[13], ticker="OUT2", date="26.10.2026"))      # nach dem Fenster
    return rows


def split(rows):
    used = [r for r in pc.freeze_eval._dedup_rows(rows)
            if r["provenance"] == "forward" and pc._finite(r.get("entry_past_return_5d"))
            and pc._parse_date(r["date"]) and date(2026, 7, 21) <= pc._parse_date(r["date"]) <= date(2026, 10, 23)]
    excl = [r for r in rows[:4]]
    return used, excl


def by_id(res):
    return {r["test_id"]: r for r in res}


# ── a / b ──────────────────────────────────────────────────────────────
def test_a_clear_effect_beleg():
    used, excl = split(make_rows(mode="effect"))
    res = by_id(pc.evaluate(used, excl, FAST, now=NOW))
    for tid in (pc.TEST_ID_PEAK, pc.TEST_ID_R10):
        r = res[tid]
        check(f"(a) {tid}: Beleg", r["verdict"] == "Beleg", r["verdict_reason"])
        check(f"(a) {tid}: Kriterien alle erfüllt",
              r["criteria"]["holm_significant"] and r["criteria"]["ci_lo_above_0_5"]
              and r["criteria"]["regime_split_status"] == "plausibel")


def test_b_null_effect_unklar():
    used, excl = split(make_rows(seed=7, mode="null"))
    res = by_id(pc.evaluate(used, excl, FAST, now=NOW))
    for tid in (pc.TEST_ID_PEAK, pc.TEST_ID_R10):
        r = res[tid]
        check(f"(b) {tid}: Unklar", r["verdict"] == "Unklar", r["verdict_reason"])
        check(f"(b) {tid}: Holm nicht signifikant", r["criteria"]["holm_significant"] is False)


# ── c ──────────────────────────────────────────────────────────────────
def test_c_floor_p1():
    used, excl = split(make_rows(mode="floor"))
    res = by_id(pc.evaluate(used, excl, FAST, now=NOW))
    p = res[pc.TEST_ID_PEAK]
    check("(c) Gipfel: n_a < 40", p["n_a"] < 40, p["n_a"])
    check("(c) Gipfel: p_holm_input = 1", p["p_holm_input"] == 1.0)
    check("(c) Gipfel: nicht auswertbar", p["verdict"] == "nicht auswertbar")
    check("(c) Gipfel: Holm verwirft nicht", p["holm_reject"] is False)
    r = res[pc.TEST_ID_R10]
    check("(c) 10-Tage-Ziel unberührt → Beleg", r["verdict"] == "Beleg", r["verdict_reason"])


# ── d ──────────────────────────────────────────────────────────────────
def test_d_regime_below_30():
    # bull nur auf 40 Zeilen → je Gruppe < 30 → bull nicht prüfbar, neutral prüfbar
    used, excl = split(make_rows(mode="effect", regime=lambda i: "bull" if i < 40 else "neutral"))
    res = by_id(pc.evaluate(used, excl, FAST, now=NOW))
    r = res[pc.TEST_ID_PEAK]
    check("(d) bull nicht_pruefbar", r["regime_split"]["detail"]["bull"]["status"] == "nicht_pruefbar")
    check("(d) bear (n=0) nicht_pruefbar", r["regime_split"]["detail"]["bear"]["status"] == "nicht_pruefbar")
    check("(d) Gesamt plausibel → Beleg", r["regime_split"]["status"] == "plausibel" and r["verdict"] == "Beleg")
    # kein Regime prüfbar (Regime fehlt meist) → bedingt
    used, excl = split(make_rows(mode="effect", regime=lambda i: "bull" if i < 50 else None))
    res = by_id(pc.evaluate(used, excl, FAST, now=NOW))
    r = res[pc.TEST_ID_PEAK]
    check("(d) alle nicht prüfbar → bedingt", r["regime_split"]["status"] == "nicht_pruefbar"
          and r["verdict"] == "bedingt", r["verdict"])
    check("(d) Zeilen ohne Regime gezählt", r["regime_split"]["detail"]["_ohne_regime"] > 0)


def test_regime_contradiction_unklar():
    used, excl = split(make_rows(mode="opposite_bull",
                                 regime=lambda i: "bull" if i % 4 == 0 else "neutral"))
    res = by_id(pc.evaluate(used, excl, FAST, now=NOW))
    r = res[pc.TEST_ID_PEAK]
    check("Regime-Gegenrichtung: widerlegt", r["regime_split"]["status"] == "widerlegt",
          r["regime_split"]["status"])
    check("Regime-Gegenrichtung → Unklar (keine Widerlegung der Edge)", r["verdict"] == "Unklar")


def test_regime_min_boundary():
    def mk(n):
        return [{"entry_past_return_5d": float(k), "market_regime": "neutral"} for k in range(n)]
    st, det = pc.regime_split(mk(30), mk(30), 0.7, 30)
    check("Mindestgröße: 30/30 prüfbar", det["neutral"]["status"] != "nicht_pruefbar")
    st, det = pc.regime_split(mk(30), mk(29), 0.7, 30)
    check("Mindestgröße: 30/29 nicht prüfbar", det["neutral"]["status"] == "nicht_pruefbar"
          and st == "nicht_pruefbar")


# ── Holm innen ─────────────────────────────────────────────────────────
def test_holm_inner_thresholds():
    h = pc.multiple_testing_correction([0.0160, 0.0330], labels=["a", "b"],
                                       alpha=PARAMS["alpha_paper_c"])
    rej = {r["label"]: r["holm_reject"] for r in h["results"]}
    check("Holm innen: 0,0160 < α/3 und 0,0330 < 2α/3 → beide", rej == {"a": True, "b": True})
    h = pc.multiple_testing_correction([0.0170, 0.0010], labels=["a", "b"],
                                       alpha=PARAMS["alpha_paper_c"])
    rej = {r["label"]: r["holm_reject"] for r in h["results"]}
    check("Holm innen: 0,0010 → ja, danach 0,0170 < 2α/3 → ja", rej == {"a": True, "b": True})
    h = pc.multiple_testing_correction([0.0200, 0.0300], labels=["a", "b"],
                                       alpha=PARAMS["alpha_paper_c"])
    rej = {r["label"]: r["holm_reject"] for r in h["results"]}
    check("Holm innen: kleinerer 0,0200 ≥ α/3 → Stopp, keiner", rej == {"a": False, "b": False})


# ── e ──────────────────────────────────────────────────────────────────
def test_e_determinism():
    used, excl = split(make_rows(mode="effect"))
    r1 = pc.evaluate(used, excl, FAST, now=NOW)
    r2 = pc.evaluate(copy.deepcopy(used), copy.deepcopy(excl), FAST, now=NOW)
    check("(e) zweimal identisch", json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True))
    check("(e) Seed 42 / N aus dem Block", r1[0]["bootstrap_seed"] == 42 and PARAMS["bootstrap_n"] == 2000)


# ── g ──────────────────────────────────────────────────────────────────
def test_g_net_partially_missing():
    rows = make_rows(mode="effect", net_missing_share=0.45)
    used, excl = split(rows)
    res = by_id(pc.evaluate(used, excl, FAST, now=NOW))
    n = res[pc.TEST_ID_PEAK]["net_supplement"]
    check("(g) Netto berichtet, nicht bindend", n["nachrangig_nicht_bindend"] is True and n["auc"] is not None)
    check("(g) Zeilen ohne Netto gezählt", n["n_ohne_netto"] > 0)
    stripped = [{k: v for k, v in r.items() if k != "max_gain_pct_net"} for r in used]
    res2 = by_id(pc.evaluate(stripped, excl, FAST, now=NOW))
    same = all(res[t]["verdict"] == res2[t]["verdict"] and res[t]["p_holm_input"] == res2[t]["p_holm_input"]
               for t in (pc.TEST_ID_PEAK, pc.TEST_ID_R10))
    check("(g) Urteil unabhängig vom Netto-Feld", same)
    check("(g) ganz ohne Netto kein Crash", res2[pc.TEST_ID_PEAK]["net_supplement"]["auc"] is None)


# ── f + Abbrüche + End-to-End ───────────────────────────────────────────
def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _guard_load(monkey_box):
    orig = pc._load_sample

    def _boom(*a, **k):
        monkey_box["called"] = True
        raise AssertionError("Export darf nicht geöffnet werden")
    pc._load_sample = _boom
    return orig


def test_f_lock_aborts_before_export():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        res_p = td / "eval_results.jsonl"
        _write_jsonl(res_p, [{"test_id": "exit_b1_a"}, {"test_id": "paper_c_gipfel", "family": "paper_c"}])
        box = {}
        orig = _guard_load(box)
        try:
            pc.run_paper_c(handover_path=HANDOVER, results_path=res_p,
                           export_path=td / "nope.jsonl", env=ENV_OK)
            check("(f) Abbruch bei paper_c-Zeile", False)
        except pc.PaperCAbort:
            check("(f) Abbruch bei paper_c-Zeile", True)
        finally:
            pc._load_sample = orig
        check("(f) Export nie geöffnet", not box.get("called"))
        check("(f) eval_results unverändert", len(res_p.read_text().splitlines()) == 2)


def test_aborts_location_md5_missing_block():
    box = {}
    orig = _guard_load(box)
    try:
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            for env, name in (({}, "kein Actions"), ({"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/feature"}, "falscher Branch")):
                try:
                    pc.run_paper_c(handover_path=HANDOVER, results_path=td / "r.jsonl",
                                   export_path=td / "x.jsonl", env=env)
                    check(f"Ort-Guard: {name}", False)
                except pc.PaperCAbort:
                    check(f"Ort-Guard: {name}", True)
            text = HANDOVER.read_text(encoding="utf-8")
            changed = td / "h1.md"
            block = pc.extract_freeze_block(text)
            changed.write_text(text.replace(block, block.replace("**N = 2000**", "**N = 1000**")),
                               encoding="utf-8")
            missing = td / "h2.md"
            missing.write_text(text.replace(pc.FREEZE_HEADING, "### etwas anderes", 1), encoding="utf-8")
            for path, name in ((changed, "Block geändert (MD5)"), (missing, "Block fehlt")):
                try:
                    pc.run_paper_c(handover_path=path, results_path=td / "r.jsonl",
                                   export_path=td / "x.jsonl", env=ENV_OK)
                    check(f"Abbruch: {name}", False)
                except pc.PaperCAbort:
                    check(f"Abbruch: {name}", True)
        check("Abbrüche ohne Export-Zugriff", not box.get("called"))
    finally:
        pc._load_sample = orig


def test_count_mismatch_aborts():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        exp = td / "export.jsonl"
        _write_jsonl(exp, make_rows(mode="effect", n_window=671))
        res_p = td / "eval_results.jsonl"
        try:
            pc.run_paper_c(handover_path=HANDOVER, results_path=res_p, export_path=exp, env=ENV_OK)
            check("Zählung 671 ≠ 672 → Abbruch", False)
        except pc.PaperCAbort:
            check("Zählung 671 ≠ 672 → Abbruch", True)
        check("Zählung-Abbruch schreibt nichts", not res_p.exists())


def test_end_to_end_with_push_stub():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        exp = td / "export.jsonl"
        _write_jsonl(exp, make_rows(mode="effect"))
        res_p = td / "eval_results.jsonl"
        _write_jsonl(res_p, [{"test_id": "exit_b1_a", "family": "exit_b1"},
                             {"test_id": "exit_b1_b", "family": "exit_b1"}])
        pushes = []
        rows = pc.run_paper_c(handover_path=HANDOVER, results_path=res_p, export_path=exp,
                              now=NOW, env=ENV_OK, send_push=lambda t, b: pushes.append((t, b)))
        lines = [json.loads(l) for l in res_p.read_text().splitlines() if l.strip()]
        check("E2E: 2 neue Zeilen (eine je Ziel)", len(lines) == 4 and
              [l["test_id"] for l in lines[2:]] == [pc.TEST_ID_PEAK, pc.TEST_ID_R10])
        r = lines[2]
        for key in ("schema_v", "family", "script_commit_hash", "data_hash", "freeze_block_md5",
                    "confirmatory_tests_before", "confirmatory_tests_total", "regime_split",
                    "cluster_double_run", "net_supplement", "bootstrap_seed", "bootstrap_n"):
            check(f"E2E: Feld {key}", key in r)
        check("E2E: schema_v 1 / family paper_c", r["schema_v"] == 1 and r["family"] == "paper_c")
        check("E2E: Zählung 2 vorher → 4 gesamt", r["confirmatory_tests_before"] == 2
              and r["confirmatory_tests_total"] == 4)
        check("E2E: N=2000 voll", r["bootstrap_n"] == 2000)
        check("E2E: Window-Zählung 672 / 4 ausgeschlossen", r["n_window"] == 672 and r["n_excluded"] == 4)
        check("E2E: genau ein Push", len(pushes) == 1)
        body = pushes[0][1]
        nums = re.findall(r"\d+(?:[.,]\d+)?", body)
        check("E2E: Push ohne Ergebniszahlen", set(nums) <= {"1", "2", "4", "10"}, body)
        check("E2E: Push nennt Verdikte", "Ziel 1 (Gipfel): Beleg" in body and "Ziel 2 (10-Tage): Beleg" in body, body)
        try:
            pc.run_paper_c(handover_path=HANDOVER, results_path=res_p, export_path=exp, env=ENV_OK)
            check("E2E: Zweitlauf gesperrt", False)
        except pc.PaperCAbort:
            check("E2E: Zweitlauf gesperrt", True)
        check("E2E: Rückgabe = geschriebene Zeilen", rows[0]["test_id"] == pc.TEST_ID_PEAK)


def test_main_requires_run_and_never_reads_export_locally():
    box = {}
    orig = _guard_load(box)
    try:
        check("main ohne --run → 2", pc.main([]) == 2)
        import os
        saved = {k: os.environ.pop(k, None) for k in ("GITHUB_ACTIONS", "GITHUB_REF")}
        try:
            check("main --run lokal → Abbruch 1", pc.main(["--run"]) == 1)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
        check("lokal: Export nie geöffnet", not box.get("called"))
    finally:
        pc._load_sample = orig


def test_source_order_freeze_before_export():
    src = (ROOT / "scripts" / "paper_c_eval.py").read_text(encoding="utf-8")
    body = src[src.index("def run_paper_c("):src.index("def _default_push(")]
    order = [body.index(s) for s in ("_location_guard(", "read_freeze(", "check_lock(", "_load_sample(")]
    check("Reihenfolge: Ort → Freeze → Sperre → Export", order == sorted(order))
    calls = [m.start() for m in re.finditer(r"_load_sample\(", src)]
    check("_load_sample nur in Definition + run_paper_c", len(calls) == 2)
    check("Export-Konstante nur in main()", src.count("MATURED_EXPORT_FILE") == 1)


def run_all() -> int:
    tests = [
        test_a_clear_effect_beleg, test_b_null_effect_unklar, test_c_floor_p1,
        test_d_regime_below_30, test_regime_contradiction_unklar, test_regime_min_boundary,
        test_holm_inner_thresholds, test_e_determinism, test_g_net_partially_missing,
        test_f_lock_aborts_before_export, test_aborts_location_md5_missing_block,
        test_count_mismatch_aborts, test_end_to_end_with_push_stub,
        test_main_requires_run_and_never_reads_export_locally,
        test_source_order_freeze_before_export,
    ]
    for t in tests:
        print(t.__name__)
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Paper-C-Tests fehlgeschlagen: {_fails}")
        return 1
    print(f"Alle {len(tests)} Paper-C-Testgruppen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
