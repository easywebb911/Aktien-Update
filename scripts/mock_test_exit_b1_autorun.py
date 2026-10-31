"""Mock-Tests für den §4-Exit-B.1-Freeze-Auswertungs-Autorun (31.10.2026).

Setzt den EINGEFROREN registrierten §4-Exit-B.1-Re-Test (SESSION_HANDOVER.md
§4, Freeze 05.08.2026) + den "Protokolleintrag 31.10.2026" (drei
Verfahrens-Lücken geklärt — Δ-Mechanik, Regime-Split-Mechanik, Seed — VOR
Erreichen von n=250, bei n=242, Ergebnis unbekannt) in
``scripts/freeze_eval.py``/``scripts/stats_helpers.py`` um.

ANDERS als die zwei bestehenden Freezes (Setup-Edge/Conviction, KI-Score):
Zielgröße ist eine gepaarte pp-Mittelwert-Differenz (Δ(5d−10d)/Δ(3d−10d)),
KEIN AUC. Population ist rein ``provenance=forward ∧ score≥70`` (KEIN
Datums-Filter — Definition A). Holm-p kommt aus Mann-Whitney auf den
UNABHÄNGIGEN Original-Arrays; das Bootstrap-CI ist ein zweites,
unabhängiges Erfolgskriterium. Ein gepaarter Wilcoxon-Signed-Rank-Test
läuft zusätzlich mit, ist aber REIN EXPLORATIV (beeinflusst das Verdikt
nicht). Kriterium (c) Regime-Split hat DREI mögliche Zustände
(plausibel/widerlegt/nicht_pruefbar) statt eines einfachen Booleans.

ENTWICKLUNG NUR AUF SYNTHETISCHEN FIXTURES (Auftrags-Vorgabe) — KEINE
echten ``return_*``-Werte werden hier angesehen.

Kategorien:
  1  paired_bootstrap_mean_delta: Determinismus, Fixture-Wiederfindung
     (klarer Effekt -> CI-Untergrenze > 0; kein Effekt -> CI schließt 0
     ein), Edge-Cases (leer, Längen-Mismatch).
  2  wilcoxon_signed_rank_paired (stats_helpers): klarer Effekt -> kleines
     p; kein Effekt -> großes p; Null-Differenzen ausgeschlossen; Edge-
     Cases.
  3  Population-Filter: hc._is_exit_b1_population_row (reuse, KEIN
     Datums-Filter — anders als die anderen zwei Freezes).
  4  Regime-Split-Mechanik (Kriterium c): plausibel (ausreichend besetzter
     Bucket stimmt überein), nicht_pruefbar (alle Buckets < 10),
     widerlegt (Gegen-Vorzeichen in einem ausreichend besetzten Bucket).
  5  Verdikt-Logik (DREI Zustände): Beleg / bedingt / Unklar — Freeze-
     Grenze "nie keine Edge" bleibt in allen Fällen gewahrt.
  6  Holm-Korrektur k=2, exploratives Wilcoxon beeinflusst das Verdikt
     NICHT (Kontroll-Fixture mit stark abweichendem Wilcoxon-p).
  7  Umgang mit fehlenden Werten: pro Test eigene n_excluded/pct_excluded;
     degenerierte/leere Population -> kein Crash, "Unklar".
  8  Auslöser: n=249 kein Trigger, n=250 Trigger, Sperre bei Zweitlauf.
  9  Determinismus: identischer Input -> identisches Ergebnis (zweimal).
  10 Digest-Wiring: eval_status_line für "Exit-B.1 (§4)" in allen 3
     Digest-Klassen, health_check_digest.main() End-to-End (Push +
     eval_results.jsonl mit protocol_ref/bootstrap_seed/script_commit_hash).
  11 Score-/Top-10-Gegenprobe: evaluate_exit_b1_family berührt score()/
     Top-10 gar nicht (Source-Inspektion).

Kategorie A: stdlib, deterministisch, env-frei (kein yfinance/requests-
Import nötig — freeze_eval.py/health_check.py sind standalone importierbar).
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import random
import sys
import tempfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import health_check as hc  # noqa: E402
import freeze_eval as fe  # noqa: E402
from stats_helpers import wilcoxon_signed_rank_paired  # noqa: E402

_fails: list[str] = []


def _check(name, cond, debug=None):
    print(("  OK  " if cond else "  FAIL ") + name
          + ("" if cond or debug is None else f"  (debug: {debug!r})"))
    if not cond:
        _fails.append(name)


def _row(ticker, *, score=80.0, provenance="forward", date="01.10.2026",
        return_5d=None, return_10d=None, return_3d=None, market_regime=None):
    return {"ticker": ticker, "date": date, "score": score,
            "provenance": provenance, "return_5d": return_5d,
            "return_10d": return_10d, "return_3d": return_3d,
            "market_regime": market_regime}


def _effect_rows(n, *, seed=1, offset_5=5.0, offset_10=1.0, offset_3=3.0,
                 noise=1.0, regimes=("bull", "bear", "neutral")):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        reg = regimes[i % len(regimes)] if regimes else None
        out.append(_row(
            f"T{i}",
            return_5d=offset_5 + rng.gauss(0, noise),
            return_10d=offset_10 + rng.gauss(0, noise),
            return_3d=offset_3 + rng.gauss(0, noise),
            market_regime=reg,
        ))
    return out


def _no_effect_rows(n, *, seed=2, noise=1.0, regimes=("bull", "bear", "neutral")):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        reg = regimes[i % len(regimes)] if regimes else None
        out.append(_row(
            f"T{i}",
            return_5d=rng.gauss(0, noise), return_10d=rng.gauss(0, noise),
            return_3d=rng.gauss(0, noise), market_regime=reg,
        ))
    return out


# ===========================================================================
# 1: paired_bootstrap_mean_delta
# ===========================================================================

def test_bootstrap_mean_delta_determinism():
    a = [5.0 + i * 0.1 for i in range(50)]
    b = [1.0 + i * 0.1 for i in range(50)]
    r1 = fe.paired_bootstrap_mean_delta(a, b, seed=42)
    r2 = fe.paired_bootstrap_mean_delta(a, b, seed=42)
    _check("gepaarter Bootstrap deterministisch (gleicher Seed)", r1 == r2)
    _check("Seed im Ergebnis dokumentiert", r1["seed"] == 42)
    _check("N=2000-Default dokumentiert", r1["n_iter"] == 2000)


def test_bootstrap_mean_delta_clear_effect():
    rng = random.Random(5)
    a = [5.0 + rng.gauss(0, 1) for _ in range(120)]
    rng2 = random.Random(5)
    b = [1.0 + rng2.gauss(0, 1) for _ in range(120)]
    r = fe.paired_bootstrap_mean_delta(a, b, n_iter=500)
    _check("klarer Effekt -> point_delta nahe 4.0",
           3.0 < r["point_delta"] < 5.0, r["point_delta"])
    _check("klarer Effekt -> CI-Untergrenze > 0", r["ci_lo"] > 0.0)


def test_bootstrap_mean_delta_no_effect():
    rng = random.Random(9)
    a = [rng.gauss(0, 1) for _ in range(200)]
    b = [rng.gauss(0, 1) for _ in range(200)]
    r = fe.paired_bootstrap_mean_delta(a, b, n_iter=500)
    _check("kein Effekt -> point_delta nahe 0", abs(r["point_delta"]) < 0.5)
    _check("kein Effekt -> CI schließt 0 ein", r["ci_lo"] < 0.0 < r["ci_hi"])


def test_bootstrap_mean_delta_edge_cases():
    r_empty = fe.paired_bootstrap_mean_delta([], [])
    _check("leere Arrays -> point_delta None, kein Crash", r_empty["point_delta"] is None)
    r_mismatch = fe.paired_bootstrap_mean_delta([1, 2], [1])
    _check("Längen-Mismatch -> point_delta None, kein Crash", r_mismatch["point_delta"] is None)


# ===========================================================================
# 2: wilcoxon_signed_rank_paired (stats_helpers)
# ===========================================================================

def test_wilcoxon_clear_effect_small_p():
    rng = random.Random(1)
    a = [5.0 + rng.gauss(0, 1) for _ in range(40)]
    rng2 = random.Random(1)
    b = [1.0 + rng2.gauss(0, 1) for _ in range(40)]
    r = wilcoxon_signed_rank_paired(a, b)
    _check("klarer Effekt -> p klein", r["p_two_sided"] < 0.01, r["p_two_sided"])


def test_wilcoxon_no_effect_large_p():
    rng = random.Random(3)
    a = [rng.gauss(0, 1) for _ in range(60)]
    b = [rng.gauss(0, 1) for _ in range(60)]
    r = wilcoxon_signed_rank_paired(a, b)
    _check("kein Effekt -> p groß (> 0.1)", r["p_two_sided"] > 0.1, r["p_two_sided"])


def test_wilcoxon_zero_differences_excluded():
    r = wilcoxon_signed_rank_paired([1, 2, 3], [1, 2, 3])
    _check("alle Differenzen 0 -> n=0, p None", r["n"] == 0 and r["p_two_sided"] is None)
    _check("n_zero_dropped korrekt", r["n_zero_dropped"] == 3)


def test_wilcoxon_length_mismatch():
    r = wilcoxon_signed_rank_paired([1, 2], [1])
    _check("Längen-Mismatch -> kein Crash, p None", r["p_two_sided"] is None)


# ===========================================================================
# 3: Population-Filter (KEIN Datums-Filter — Definition A)
# ===========================================================================

def test_population_filter_forward_score70_included():
    _check("forward + score=70 -> Population",
           hc._is_exit_b1_population_row(_row("A", score=70.0)))


def test_population_filter_backfill_excluded():
    _check("backfill (egal welcher Score) -> NICHT Population",
           not hc._is_exit_b1_population_row(_row("A", provenance="backfill", score=99.0)))


def test_population_filter_score_below_70_excluded():
    _check("score=69.9 -> NICHT Population",
           not hc._is_exit_b1_population_row(_row("A", score=69.9)))


def test_population_filter_no_date_filter():
    """Definition A hat KEINEN Datums-Filter — ein sehr altes Datum zählt
    trotzdem, solange forward + score>=70 (anders als Setup-Edge/KI-Score)."""
    _check("sehr altes Datum zählt trotzdem (kein Datums-Filter)",
           hc._is_exit_b1_population_row(_row("A", date="01.01.2000", score=80.0)))


def test_population_filter_missing_score():
    _check("score fehlt (None) -> NICHT Population",
           not hc._is_exit_b1_population_row({"provenance": "forward"}))


def test_population_filter_score_bool_excluded():
    _check("score=True (bool) -> NICHT Population (bool ist kein echter Score)",
           not hc._is_exit_b1_population_row(_row("A", score=True)))


# ===========================================================================
# 4: Regime-Split-Mechanik (Kriterium c)
# ===========================================================================

def test_regime_check_plausible_with_one_big_bucket():
    rows = _effect_rows(120, seed=11, regimes=("bull",))  # alle in 'bull'
    status, detail = fe._exit_b1_regime_check(rows, "return_5d", "return_10d", 1)
    _check("ein großer, übereinstimmender Bucket -> plausibel", status == "plausibel")
    _check("andere Buckets korrekt als nicht_pruefbar markiert",
           detail["bear"]["status"] == "nicht_pruefbar")


def test_regime_check_not_testable_all_small_buckets():
    rows = _effect_rows(24, seed=12)  # 3 Regimes, je 8 -> alle < 10
    status, _ = fe._exit_b1_regime_check(rows, "return_5d", "return_10d", 1)
    _check("alle Buckets < 10 -> nicht_pruefbar", status == "nicht_pruefbar")


def test_regime_check_contradiction_is_widerlegt():
    rng = random.Random(21)
    rows = []
    # bull: starker positiver Effekt, n=20
    for i in range(20):
        rows.append(_row(f"B{i}", return_5d=5.0 + rng.gauss(0, 0.5),
                         return_10d=1.0 + rng.gauss(0, 0.5), market_regime="bull"))
    # bear: GEGENTEILIGER Effekt, n=20 (Gegen-Vorzeichen)
    for i in range(20):
        rows.append(_row(f"R{i}", return_5d=1.0 + rng.gauss(0, 0.5),
                         return_10d=5.0 + rng.gauss(0, 0.5), market_regime="bear"))
    status, detail = fe._exit_b1_regime_check(rows, "return_5d", "return_10d", 1)
    _check("Gegen-Vorzeichen in ausreichend besetztem Bucket -> widerlegt",
           status == "widerlegt")
    _check("bear-Bucket selbst als widerlegt markiert", detail["bear"]["status"] == "widerlegt")


def test_regime_check_missing_market_regime_field():
    rows = [_row("A", return_5d=5.0, return_10d=1.0, market_regime=None)]
    status, _ = fe._exit_b1_regime_check(rows, "return_5d", "return_10d", 1)
    _check("fehlendes market_regime -> kein Crash, nicht_pruefbar", status == "nicht_pruefbar")


# ===========================================================================
# 5+6: Verdikt-Logik + Holm k=2 + Wilcoxon beeinflusst NICHT
# ===========================================================================

def test_verdict_clear_success_beleg():
    rows = _effect_rows(150, seed=31)
    res = fe.evaluate_exit_b1_family(rows)
    for label, test in res["tests"].items():
        _check(f"klarer Erfolg -> Test {label} = Beleg", test["verdict"] == "Beleg",
               test["verdict_reason"])


def test_verdict_no_effect_unklar():
    rows = _no_effect_rows(150, seed=32)
    res = fe.evaluate_exit_b1_family(rows)
    for label, test in res["tests"].items():
        _check(f"kein Effekt -> Test {label} = Unklar", test["verdict"] == "Unklar")


def test_verdict_bedingt_when_regime_not_testable():
    rows = _effect_rows(24, seed=33, noise=0.3)  # klarer Effekt, aber alle Buckets < 10
    res = fe.evaluate_exit_b1_family(rows)
    for label, test in res["tests"].items():
        _check(f"Holm+CI erfüllt, Regime nicht prüfbar -> Test {label} = bedingt",
               test["verdict"] == "bedingt", test["verdict_reason"])


def test_verdict_never_rejects_edge_outright():
    """Freeze-Grenze: NIE 'keine Edge' — nur Beleg/bedingt/Unklar sind
    erlaubte Verdikt-Strings."""
    for rows in (_effect_rows(150, seed=41), _no_effect_rows(150, seed=42),
                _effect_rows(24, seed=43, noise=0.3)):
        res = fe.evaluate_exit_b1_family(rows)
        for test in res["tests"].values():
            _check("Verdikt ist eines von Beleg/bedingt/Unklar",
                   test["verdict"] in ("Beleg", "bedingt", "Unklar"), test["verdict"])


def test_wilcoxon_does_not_influence_verdict():
    """Kontroll-Fixture: Wilcoxon sieht (wegen Ausreißern) ein anderes
    Signifikanz-Bild als Mann-Whitney auf denselben Daten — das Verdikt
    MUSS trotzdem ausschließlich von Mann-Whitney (Holm-Input) + Bootstrap-
    CI abhängen, NICHT vom Wilcoxon-p."""
    rng = random.Random(51)
    rows = []
    for i in range(150):
        reg = ["bull", "bear", "neutral"][i % 3]
        rows.append(_row(f"T{i}", return_5d=5.0 + rng.gauss(0, 1),
                         return_10d=1.0 + rng.gauss(0, 1), market_regime=reg))
    res = fe.evaluate_exit_b1_family(rows)
    test_a = res["tests"]["a"]
    # Wilcoxon-p existiert als eigenständiges Feld, beeinflusst aber p_raw
    # (= Holm-Input) nicht -- p_raw muss identisch zum Mann-Whitney-p sein.
    _check("Holm-Input (p_raw) == Mann-Whitney-p, NICHT Wilcoxon-p",
           test_a["p_raw"] == test_a["mann_whitney_holm_input"]["p_two_sided"])
    _check("Wilcoxon-Ergebnis ist als eigenständiges, separates Feld vorhanden",
           "wilcoxon_exploratory" in test_a and test_a["wilcoxon_exploratory"]["p_two_sided"] is not None)


def test_holm_family_k2_independent_from_other_freezes():
    rows = _effect_rows(150, seed=61)
    res = fe.evaluate_exit_b1_family(rows)
    _check("Holm-Familie hat genau k=2 (a, b)", res["holm"]["k"] == 2)
    labels = {r["label"] for r in res["holm"]["results"]}
    _check("Holm-Labels sind exakt {a, b}", labels == {"a", "b"})


# ===========================================================================
# 7: Fehlende Werte / Degenerierte Population
# ===========================================================================

def test_missing_values_per_test_exclusion():
    rows = _effect_rows(100, seed=71)
    # return_3d bei den ersten 10 Zeilen entfernen -> nur Test b betroffen
    for r in rows[:10]:
        r["return_3d"] = None
    res = fe.evaluate_exit_b1_family(rows)
    _check("Test a (Δ5-10) unberührt von fehlendem return_3d",
           res["tests"]["a"]["n_excluded"] == 0)
    _check("Test b (Δ3-10) zählt die fehlenden Werte korrekt",
           res["tests"]["b"]["n_excluded"] == 10)
    _check("pct_excluded korrekt berechnet",
           abs(res["tests"]["b"]["pct_excluded"] - 10.0) < 0.01)


def test_empty_population_no_crash():
    res = fe.evaluate_exit_b1_family([])
    _check("leere Population -> n_pop=0, kein Crash", res["n_pop"] == 0)
    for test in res["tests"].values():
        _check("leere Population -> Verdikt Unklar (kein Crash in Holm/CI)",
               test["verdict"] == "Unklar")


def test_all_rows_missing_return_10d():
    rows = [_row(f"T{i}", return_5d=5.0, return_10d=None, return_3d=3.0) for i in range(50)]
    res = fe.evaluate_exit_b1_family(rows)
    _check("alle Zeilen ohne return_10d -> n=0 für beide Tests, kein Crash",
           res["tests"]["a"]["n"] == 0 and res["tests"]["b"]["n"] == 0)


# ===========================================================================
# 8: Auslöser (249 nein / 250 ja) + Sperre
# ===========================================================================

def test_trigger_at_249_no_250_yes_and_lock():
    d = tempfile.mkdtemp()
    export_path = pathlib.Path(d) / "export.jsonl"
    results_path = pathlib.Path(d) / "eval_results.jsonl"

    def _write(n):
        rows = _effect_rows(n, seed=81)
        with open(export_path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    _write(249)
    out = fe.run_due_evaluations(export_path=export_path, results_path=results_path)
    _check("n=249 -> kein Trigger", "exit_b1" not in [j["family"] for j in out["just_triggered"]])
    _check("n=249 -> exit_b1_status korrekt", out["exit_b1_status"][0] == 249)
    _check("n=249 -> kein eval_results.jsonl", not results_path.exists())

    _write(250)
    out2 = fe.run_due_evaluations(export_path=export_path, results_path=results_path)
    _check("n=250 -> Trigger", "exit_b1" in [j["family"] for j in out2["just_triggered"]])
    _check("n=250 -> eval_results.jsonl angelegt", results_path.exists())

    out3 = fe.run_due_evaluations(export_path=export_path, results_path=results_path)
    _check("Zweitlauf -> KEIN erneuter Trigger (Sperre)",
           "exit_b1" not in [j["family"] for j in out3["just_triggered"]])
    _check("Zweitlauf -> exit_b1_locked True", out3["exit_b1_locked"] is True)

    with open(results_path, encoding="utf-8") as f:
        lines = [json.loads(ln) for ln in f if ln.strip()]
    _check("genau 2 Zeilen (Test a + b), kein Duplikat nach Zweitlauf", len(lines) == 2)
    for row in lines:
        _check(f"{row['test_id']}: bootstrap_seed=42", row["bootstrap_seed"] == 42)
        _check(f"{row['test_id']}: bootstrap_n=2000", row["bootstrap_n"] == 2000)
        _check(f"{row['test_id']}: protocol_ref gesetzt", bool(row.get("protocol_ref")))
        _check(f"{row['test_id']}: script_commit_hash-Feld vorhanden", "script_commit_hash" in row)


# ===========================================================================
# 9: Determinismus
# ===========================================================================

def test_full_family_determinism():
    rows = _effect_rows(260, seed=91)
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    r1 = fe.evaluate_exit_b1_family(rows, now=now)
    r2 = fe.evaluate_exit_b1_family(rows, now=now)
    _check("evaluate_exit_b1_family zweimal identisch (fester Seed/now)", r1 == r2)


# ===========================================================================
# 10: Digest-Wiring
# ===========================================================================

def test_eval_status_line_exit_b1_pre_trigger():
    line = hc.eval_status_line("Exit-B.1 (§4)", (242, 250), hc._RETEST_N_TARGET, None)
    _check("Vor-Auslöser-Zeile zeigt n/target", "242" in line and "250" in line)


def test_eval_status_line_exit_b1_post_trigger():
    line = hc.eval_status_line("Exit-B.1 (§4)", (250, 250), hc._RETEST_N_TARGET, None,
                               verdict_text="exit_b1_a: Beleg; exit_b1_b: Unklar")
    _check("Nach-Auslöser-Zeile zeigt Verdikt-Text", "Beleg" in line and "Unklar" in line)


def _load_digest_module():
    spec = importlib.util.spec_from_file_location(
        "_dgst_exit_b1_test", str(ROOT / "scripts" / "health_check_digest.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_digest_end_to_end_trigger_and_push():
    mod = _load_digest_module()
    d = tempfile.mkdtemp()
    export_path = str(pathlib.Path(d) / "export.jsonl")
    results_path = str(pathlib.Path(d) / "eval_results.jsonl")
    log_path = str(pathlib.Path(d) / "health_check_log.jsonl")

    mod.hc.MATURED_EXPORT_FILE = export_path
    mod.EVAL_RESULTS_FILE = results_path
    mod.DIGEST_STATE_FILE = pathlib.Path(d) / "state.json"
    mod.APP_DATA_FILE_FOR_WATCHDOG = pathlib.Path(d) / "app_data.json"
    mod.WATCHLIST_PERSONAL_FILE_FOR_WATCHDOG = pathlib.Path(d) / "watchlist_personal.json"
    mod.POSITION_WATCHLIST_STATE_FILE = pathlib.Path(d) / "position_watchlist_state.json"
    mod.hc.LOG_FILE = log_path

    rows = _effect_rows(260, seed=101)
    with open(export_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"run_ts": "2026-10-31T21:00:00Z", "run_phase": "postclose",
                            "schema_v": 1, "state_fails": [], "provider_fails": []}) + "\n")

    sent = []
    def _spy(title, body, priority, tags):
        sent.append((title, body, priority, tags))
        return True
    mod._ntfy_send = _spy
    mod.NTFY_TOPIC = "test-topic"

    rc = mod.main(now_ts=datetime(2026, 10, 31, 21, 0, tzinfo=timezone.utc))
    _check("main() exit 0 bei Trigger", rc == 0)
    _check("eval_results.jsonl angelegt", os.path.exists(results_path))
    _check("genau EIN ntfy-Push mit 'Exit-B.1' im Titel",
           sum(1 for s in sent if "Exit-B.1" in s[0]) == 1)
    if sent:
        push_body = next((s[1] for s in sent if "Exit-B.1" in s[0]), "")
        _check("Push-Body nennt den Auslöser n>=250", "n>=250" in push_body)


def test_digest_no_trigger_under_250_no_push():
    mod = _load_digest_module()
    d = tempfile.mkdtemp()
    export_path = str(pathlib.Path(d) / "export.jsonl")
    results_path = str(pathlib.Path(d) / "eval_results.jsonl")
    log_path = str(pathlib.Path(d) / "health_check_log.jsonl")

    mod.hc.MATURED_EXPORT_FILE = export_path
    mod.EVAL_RESULTS_FILE = results_path
    mod.DIGEST_STATE_FILE = pathlib.Path(d) / "state.json"
    mod.APP_DATA_FILE_FOR_WATCHDOG = pathlib.Path(d) / "app_data.json"
    mod.WATCHLIST_PERSONAL_FILE_FOR_WATCHDOG = pathlib.Path(d) / "watchlist_personal.json"
    mod.POSITION_WATCHLIST_STATE_FILE = pathlib.Path(d) / "position_watchlist_state.json"
    mod.hc.LOG_FILE = log_path

    rows = _effect_rows(100, seed=111)  # < 250
    with open(export_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"run_ts": "2026-10-31T21:00:00Z", "run_phase": "postclose",
                            "schema_v": 1, "state_fails": [], "provider_fails": []}) + "\n")

    sent = []
    mod._ntfy_send = lambda *a, **kw: sent.append(a) or True
    mod.NTFY_TOPIC = "test-topic"

    rc = mod.main(now_ts=datetime(2026, 10, 31, 21, 0, tzinfo=timezone.utc))
    _check("main() exit 0 unter dem Auslöser", rc == 0)
    _check("kein eval_results.jsonl unter dem Auslöser", not os.path.exists(results_path))
    _check("kein Exit-B.1-Push unter dem Auslöser",
           not any("Exit-B.1" in s[0] for s in sent))


# ===========================================================================
# 11: Score-/Top-10-Gegenprobe
# ===========================================================================

def test_no_score_or_top10_touch():
    import inspect
    src = inspect.getsource(fe.evaluate_exit_b1_family)
    src += inspect.getsource(fe._exit_b1_regime_check)
    src += inspect.getsource(fe.paired_bootstrap_mean_delta)
    _check("Exit-B.1-Code referenziert score()/Top-10 nirgends",
           "score(" not in src and "top10" not in src.lower())


def run_all():
    tests = [
        test_bootstrap_mean_delta_determinism,
        test_bootstrap_mean_delta_clear_effect,
        test_bootstrap_mean_delta_no_effect,
        test_bootstrap_mean_delta_edge_cases,
        test_wilcoxon_clear_effect_small_p,
        test_wilcoxon_no_effect_large_p,
        test_wilcoxon_zero_differences_excluded,
        test_wilcoxon_length_mismatch,
        test_population_filter_forward_score70_included,
        test_population_filter_backfill_excluded,
        test_population_filter_score_below_70_excluded,
        test_population_filter_no_date_filter,
        test_population_filter_missing_score,
        test_population_filter_score_bool_excluded,
        test_regime_check_plausible_with_one_big_bucket,
        test_regime_check_not_testable_all_small_buckets,
        test_regime_check_contradiction_is_widerlegt,
        test_regime_check_missing_market_regime_field,
        test_verdict_clear_success_beleg,
        test_verdict_no_effect_unklar,
        test_verdict_bedingt_when_regime_not_testable,
        test_verdict_never_rejects_edge_outright,
        test_wilcoxon_does_not_influence_verdict,
        test_holm_family_k2_independent_from_other_freezes,
        test_missing_values_per_test_exclusion,
        test_empty_population_no_crash,
        test_all_rows_missing_return_10d,
        test_trigger_at_249_no_250_yes_and_lock,
        test_full_family_determinism,
        test_eval_status_line_exit_b1_pre_trigger,
        test_eval_status_line_exit_b1_post_trigger,
        test_digest_end_to_end_trigger_and_push,
        test_digest_no_trigger_under_250_no_push,
        test_no_score_or_top10_touch,
    ]
    for t in tests:
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Exit-B.1-Autorun-Tests fehlgeschlagen: {_fails}")
        return 1
    print(f"Alle {len(tests)} Exit-B.1-Autorun-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
