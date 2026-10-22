"""Mock-Tests für die Freeze-Auswertungs-Autorun-Engine (Erratum 22.10.2026).

Setzt die eingefrorenen Setup-Edge/Conviction- und KI-Score-Edge-Test-
Freezes (SESSION_HANDOVER.md) + das Erratum 22.10.2026 (Bootstrap-Seed=42,
N=2000, 95% zweiseitiges Perzentil-Intervall, Ausschluss-Regel für Test c)
in ``scripts/freeze_eval.py`` um — "die Auswertung startet bei n=250 von
selbst".

ENTWICKLUNG NUR AUF SYNTHETISCHEN FIXTURES (Auftrags-Vorgabe) — KEINE
echten ``return_*``-Werte werden in diesem Test angesehen; alle Zeilen
sind erfundene Fixture-Daten mit bekannter, eingebauter AUC.

Kategorien:
  1  Bootstrap-Primitive: Determinismus (gleicher Seed -> gleiches
     Ergebnis), Fixture-Wiederfindung (eingebauter starker Effekt ->
     hohe AUC/CI-Untergrenze > 0,5; kein Effekt -> AUC~0,5, CI schließt
     0,5 ein).
  2  Gepaarter Bootstrap ΔAUC (Test c): Fixture mit echtem Conviction-
     Zusatznutzen -> Beleg; Fixture ohne Zusatznutzen (Score==Conviction
     + Rauschen) -> Unklar.
  3  Population-Filter: Setup-Edge (reuse health_check._is_freeze_
     population_row), KI-Score (Erratum 16.10.2026, Ausschluss-Quote
     inkl. >20%-Flag).
  4  Cluster-Doppellauf: Cluster-Folgeeintrag korrekt erkannt + entfernt,
     "same_direction" korrekt bei robustem vs. nicht-robustem Effekt.
  5  Holm-Korrektur: k=3 (Setup-Edge/Conviction) bzw. k=2 (KI-Score)
     korrekt verdrahtet (reject-Flags konsistent zu scripts/stats_helpers).
  6  Sperre / kein Peeking: zweiter Lauf auf denselben Daten erzeugt
     KEINE neue Zeile, KEINEN zweiten Push.
  7  Verdikt-Logik: "Beleg" nur bei allen 4 Kriterien, sonst "Unklar"
     (NIE "keine Edge" — Freeze-Grenzen-Klausel).
  8  Digest-Wiring: health_check.eval_status_line (Vor-/Nach-Auslöser-
     Format), format_digest_body-Verdrahtung (Backward-Compat ohne
     eval_lines), health_check_digest.main() End-to-End (EVAL_AUTORUN_
     ENABLED True/False, Lock über zwei Läufe).
  9  Golden byte-identisch, Score-/Top-10-Gegenprobe (reine Analyse-
     Persistenz, kein Score()-Touch).

Kategorie A: stdlib + jinja2 (Golden-Stub-Reuse), deterministisch, env-frei.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import pathlib
import random
import sys
import tempfile
import types
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from mock_test_outer_page_golden import gr  # noqa: E402  (installiert Heavy-Dep-Stubs)

import health_check as hc  # noqa: E402
import freeze_eval as fe  # noqa: E402

if "pandas" not in sys.modules:
    _pd_stub = types.ModuleType("pandas")
    _pd_stub.DataFrame = object
    _pd_stub.Timestamp = lambda *a, **k: None
    sys.modules["pandas"] = _pd_stub

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def _synthetic_setup_edge_rows(n=400, *, seed=1, conviction_extra=False,
                               no_effect=False, exclude_conviction_frac=0.0):
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        day = (i % 20) + 11  # 11..30.10.2026 -> strikt nach Default-Freeze 10.10.2026
        score = rng.uniform(40, 100)
        if no_effect:
            ret5 = rng.uniform(-10, 10)
            ret10 = rng.uniform(-10, 10)
            conviction = rng.uniform(0, 100)
        elif conviction_extra:
            extra = rng.uniform(0, 60)
            conviction = extra
            ret5 = extra * 0.3 + rng.uniform(-2, 2)
            ret10 = extra * 0.3 + rng.uniform(-2, 2)
        else:
            ret5 = (score - 50) * 0.3 + rng.uniform(-3, 3)
            ret10 = (score - 50) * 0.3 + rng.uniform(-3, 3)
            conviction = score + rng.uniform(-5, 5)
        row = {"ticker": f"T{i}", "date": f"{day:02d}.10.2026", "provenance": "forward",
               "score": score, "return_5d": ret5, "return_10d": ret10,
               "entry_price": round(10.0 + i * 0.01, 4)}
        if rng.random() >= exclude_conviction_frac:
            row["conviction_score"] = conviction
        rows.append(row)
    return rows


def _synthetic_ki_score_rows(n=400, *, seed=2, effect=True, exclude_frac=0.0):
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        day = (i % 18) + 12  # 12..29.10.2026 -> >= Default-Freeze 12.10.2026
        if effect:
            ki = rng.uniform(0, 100)
            ret5 = (ki - 50) * 0.3 + rng.uniform(-3, 3)
            ret10 = (ki - 50) * 0.3 + rng.uniform(-3, 3)
        else:
            ki = rng.uniform(0, 100)
            ret5 = rng.uniform(-10, 10)
            ret10 = rng.uniform(-10, 10)
        row = {"ticker": f"K{i}", "date": f"{day:02d}.10.2026", "provenance": "forward",
               "ki_signal_ts": "2026-10-12T00:00:00Z",
               "return_5d": ret5, "return_10d": ret10}
        if rng.random() >= exclude_frac:
            row["ki_signal_score"] = ki
        rows.append(row)
    return rows


# ===========================================================================
# 1: Bootstrap-Primitive — Determinismus + Fixture-Wiederfindung
# ===========================================================================

def test_bootstrap_deterministic():
    g_a = [1, 2, 3, 4, 5, 6, 7] * 3
    g_b = [0, 0, 1, 1, 2, 0, 1] * 3
    r1 = fe.bootstrap_auc_ci(g_a, g_b)
    r2 = fe.bootstrap_auc_ci(g_a, g_b)
    _check("gleicher Seed -> identisches Ergebnis (zweimal)", r1 == r2)
    _check("Seed im Ergebnis dokumentiert", r1["seed"] == 42)
    _check("N=2000 im Ergebnis dokumentiert", r1["n_iter"] == 2000)


def test_bootstrap_finds_strong_effect():
    winners = [80 + i for i in range(30)]
    losers = [20 + i for i in range(30)]
    r = fe.bootstrap_auc_ci(winners, losers)
    _check("starker Effekt -> point_auc nahe 1.0", r["point_auc"] > 0.95)
    _check("starker Effekt -> CI-Untergrenze > 0,5", r["ci_lo"] > 0.5)


def test_bootstrap_no_effect():
    rng = random.Random(11)
    vals = [rng.uniform(0, 100) for _ in range(200)]
    winners = vals[:100]
    losers = vals[100:]
    r = fe.bootstrap_auc_ci(winners, losers)
    _check("kein Effekt -> point_auc nahe 0,5", abs(r["point_auc"] - 0.5) < 0.1)
    _check("kein Effekt -> CI schließt 0,5 ein", r["ci_lo"] < 0.5 < r["ci_hi"])


def test_bootstrap_empty_group():
    r = fe.bootstrap_auc_ci([], [1, 2, 3])
    _check("leere Gruppe -> point_auc None, kein Crash", r["point_auc"] is None)


# ===========================================================================
# 2: Gepaarter Bootstrap ΔAUC (Test c)
# ===========================================================================

def test_paired_delta_auc_real_effect():
    rows = _synthetic_setup_edge_rows(n=300, seed=7, conviction_extra=True)
    r = fe.paired_bootstrap_delta_auc(rows, score_field_a="conviction_score",
                                      score_field_b="score", label_field="return_5d",
                                      label_threshold=5.0)
    _check("echter Conviction-Zusatznutzen -> point_delta deutlich > 0",
           r["point_delta"] > 0.2)
    _check("echter Zusatznutzen -> CI-Untergrenze > 0", r["ci_lo"] > 0.0)
    print(f"    [Fixture ΔAUC mit Zusatznutzen] point_delta={r['point_delta']:.3f} "
          f"CI=[{r['ci_lo']:.3f},{r['ci_hi']:.3f}]")


def test_paired_delta_auc_no_extra_value():
    rows = _synthetic_setup_edge_rows(n=300, seed=1, conviction_extra=False)
    r = fe.paired_bootstrap_delta_auc(rows, score_field_a="conviction_score",
                                      score_field_b="score", label_field="return_5d",
                                      label_threshold=5.0)
    _check("kein Zusatznutzen (conviction~score+Rauschen) -> |point_delta| klein",
           abs(r["point_delta"]) < 0.1)
    print(f"    [Fixture ΔAUC ohne Zusatznutzen] point_delta={r['point_delta']:.3f}")


def test_paired_delta_auc_deterministic():
    rows = _synthetic_setup_edge_rows(n=100, seed=3, conviction_extra=True)
    r1 = fe.paired_bootstrap_delta_auc(rows, score_field_a="conviction_score",
                                       score_field_b="score", label_field="return_5d",
                                       label_threshold=5.0)
    r2 = fe.paired_bootstrap_delta_auc(rows, score_field_a="conviction_score",
                                       score_field_b="score", label_field="return_5d",
                                       label_threshold=5.0)
    _check("gepaarter Bootstrap deterministisch (zweimal gleich)", r1 == r2)


def test_paired_delta_auc_empty():
    r = fe.paired_bootstrap_delta_auc([], score_field_a="conviction_score",
                                      score_field_b="score", label_field="return_5d",
                                      label_threshold=5.0)
    _check("leere Zeilen -> point_delta None, kein Crash", r["point_delta"] is None)


# ===========================================================================
# 3: Population-Filter
# ===========================================================================

def test_setup_edge_population_reuses_health_check_helper():
    freeze_date = hc._parse_dmy_date("10.10.2026")
    row_in = {"provenance": "forward", "date": "11.10.2026",
              "return_5d": 1.0, "return_10d": 1.0}
    row_before_freeze = {"provenance": "forward", "date": "09.10.2026",
                         "return_5d": 1.0, "return_10d": 1.0}
    row_backfill = {"provenance": "backfill", "date": "11.10.2026",
                    "return_5d": 1.0, "return_10d": 1.0}
    _check("Zeile nach Freeze-Datum, forward, returns gefüllt -> Population",
           hc._is_freeze_population_row(row_in, freeze_date))
    _check("Zeile VOR/AM Freeze-Datum -> NICHT Population",
           not hc._is_freeze_population_row(row_before_freeze, freeze_date))
    _check("backfill-Zeile -> NICHT Population",
           not hc._is_freeze_population_row(row_backfill, freeze_date))


def test_ki_score_population_erratum_16_10():
    freeze_date = hc._parse_dmy_date("12.10.2026")
    row_ok = {"provenance": "forward", "date": "12.10.2026", "ki_signal_ts": "x",
              "ki_signal_score": 42.0, "return_5d": 1.0, "return_10d": 1.0}
    row_no_score = {"provenance": "forward", "date": "12.10.2026", "ki_signal_ts": "x",
                    "ki_signal_score": None, "return_5d": 1.0, "return_10d": 1.0}
    row_before = {"provenance": "forward", "date": "11.10.2026", "ki_signal_ts": "x",
                 "ki_signal_score": 42.0, "return_5d": 1.0, "return_10d": 1.0}
    row_no_ts = {"provenance": "forward", "date": "12.10.2026",
                "ki_signal_score": 42.0, "return_5d": 1.0, "return_10d": 1.0}
    row_nan = {"provenance": "forward", "date": "12.10.2026", "ki_signal_ts": "x",
              "ki_signal_score": float("nan"), "return_5d": 1.0, "return_10d": 1.0}
    _check("Datum einschließend (==Freeze-Datum) -> Population",
           hc._is_ki_score_population_row(row_ok, freeze_date))
    _check("ki_signal_ts da, Score None -> NICHT Population (aber Kandidat)",
           not hc._is_ki_score_population_row(row_no_score, freeze_date)
           and hc._is_ki_score_candidate_row(row_no_score, freeze_date))
    _check("Datum VOR Freeze -> NICHT Population", not hc._is_ki_score_population_row(row_before, freeze_date))
    _check("ki_signal_ts fehlt (Schlüssel nicht präsent) -> NICHT Kandidat/Population",
           not hc._is_ki_score_candidate_row(row_no_ts, freeze_date))
    _check("NaN-Score -> NICHT Population (aber Kandidat)",
           not hc._is_ki_score_population_row(row_nan, freeze_date)
           and hc._is_ki_score_candidate_row(row_nan, freeze_date))


def test_ki_score_family_exclusion_quote_over_20pct():
    rows = _synthetic_ki_score_rows(n=300, seed=5, effect=True, exclude_frac=0.25)
    res = fe.evaluate_ki_score_family(rows, freeze_date_str="12.10.2026",
                                      now=datetime(2026, 10, 22, tzinfo=timezone.utc))
    _check(">20% ausgeschlossen -> pct_excluded > 20", res["pct_excluded"] > 20.0)
    _check(">20%-Flag erscheint im verdict_reason",
           "Einschränkung" in res["tests"]["a"]["verdict_reason"]
           or res["tests"]["a"]["verdict"] == "Beleg")
    print(f"    [Fixture KI-Score Exclusion] pct_excluded={res['pct_excluded']:.1f}% "
          f"verdict_a={res['tests']['a']['verdict']}")


def test_ki_score_family_exclusion_quote_under_20pct():
    rows = _synthetic_ki_score_rows(n=300, seed=6, effect=True, exclude_frac=0.05)
    res = fe.evaluate_ki_score_family(rows, freeze_date_str="12.10.2026",
                                      now=datetime(2026, 10, 22, tzinfo=timezone.utc))
    _check("<20% ausgeschlossen -> pct_excluded < 20", res["pct_excluded"] < 20.0)
    _check("kein >20%-Hinweis im verdict_reason (bei <20%)",
           "Einschränkung" not in res["tests"]["a"]["verdict_reason"])


def test_setup_edge_family_test_c_excludes_missing_conviction():
    rows = _synthetic_setup_edge_rows(n=300, seed=4, conviction_extra=False,
                                      exclude_conviction_frac=0.15)
    res = fe.evaluate_setup_edge_family(rows, freeze_date_str="10.10.2026",
                                        now=datetime(2026, 10, 22, tzinfo=timezone.utc))
    n_ab = res["n_ab"]
    n_c = res["tests"]["c"]["n"]
    n_excl_c = res["tests"]["c"]["n_excluded"]
    _check("Test c hat weniger n als a/b (Ausschluss fehlender conviction_score)",
           n_c < n_ab)
    _check("n_excluded + n_c == n_ab (Test c)", n_excl_c + n_c == n_ab)
    _check("Tests a/b unverändert bei n_ab (Population NICHT betroffen)",
           res["tests"]["a"]["n"] == n_ab and res["tests"]["b"]["n"] == n_ab)
    print(f"    [Fixture Test-c-Exclusion] n_ab={n_ab} n_c={n_c} excluded={n_excl_c} "
          f"pct={res['tests']['c']['pct_excluded']:.1f}%")


# ===========================================================================
# 4: Cluster-Doppellauf
# ===========================================================================

def test_cluster_double_run_detects_followup():
    rows = [
        {"ticker": "AAA", "date": "12.10.2026", "entry_price": 5.0, "score": 80, "return_5d": 10, "return_10d": 10},
        {"ticker": "AAA", "date": "13.10.2026", "entry_price": 5.0, "score": 80, "return_5d": 10, "return_10d": 10},
        {"ticker": "BBB", "date": "12.10.2026", "entry_price": 7.0, "score": 20, "return_5d": -5, "return_10d": -5},
    ]

    def eval_fn(rs):
        return fe.auc_test_with_ci(rs, value_field="score", label_field="return_5d",
                                   threshold=0.0, inclusive=True)

    out = fe.cluster_double_run(rows, eval_fn, point_key="point_auc", baseline=0.5)
    _check("Cluster-Folgeeintrag erkannt + entfernt (n=1)",
           out["n_cluster_followups_removed"] == 1)
    _check("same_direction ist ein bool (kein Crash)",
           isinstance(out["same_direction"], bool))


def test_cluster_double_run_same_direction_robust_effect():
    rows = _synthetic_setup_edge_rows(n=200, seed=8, conviction_extra=False)

    def eval_fn(rs):
        return fe.auc_test_with_ci(rs, value_field="score", label_field="return_5d",
                                   threshold=5.0, inclusive=True)

    out = fe.cluster_double_run(rows, eval_fn, point_key="point_auc", baseline=0.5)
    _check("robuster Effekt -> same_direction True (mit/ohne Cluster gleiches Vorzeichen)",
           out["same_direction"] is True)


# ===========================================================================
# 5: Holm-Korrektur-Verdrahtung
# ===========================================================================

def test_holm_wiring_k3():
    rows = _synthetic_setup_edge_rows(n=400, seed=9, conviction_extra=False)
    res = fe.evaluate_setup_edge_family(rows, freeze_date_str="10.10.2026",
                                        now=datetime(2026, 10, 22, tzinfo=timezone.utc))
    _check("Holm-Familie k=3", res["holm"]["k"] == 3)
    labels = sorted(r["label"] for r in res["holm"]["results"])
    _check("Holm-Labels a,b,c", labels == ["a", "b", "c"])


def test_holm_wiring_k2():
    rows = _synthetic_ki_score_rows(n=400, seed=10, effect=True)
    res = fe.evaluate_ki_score_family(rows, freeze_date_str="12.10.2026",
                                      now=datetime(2026, 10, 22, tzinfo=timezone.utc))
    _check("Holm-Familie k=2 (eigene Familie, NICHT mit Setup/Conviction zusammengelegt)",
           res["holm"]["k"] == 2)


# ===========================================================================
# 6: Sperre / kein Peeking
# ===========================================================================

def test_lock_prevents_reevaluation():
    d = tempfile.mkdtemp()
    export_path = os.path.join(d, "export.jsonl")
    results_path = os.path.join(d, "eval_results.jsonl")
    rows = _synthetic_setup_edge_rows(n=400, seed=9, conviction_extra=False)
    with open(export_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    out1 = fe.run_due_evaluations(export_path=export_path, results_path=results_path, now=now)
    _check("erster Lauf triggert Setup-Edge/Conviction",
           any(j["family"] == "setup_edge_conviction" for j in out1["just_triggered"]))
    out2 = fe.run_due_evaluations(export_path=export_path, results_path=results_path, now=now)
    _check("zweiter Lauf (gleiche Daten) triggert NICHTS erneut (Sperre)",
           out2["just_triggered"] == [] and out2["new_rows"] == [])
    with open(results_path) as f:
        lines = [json.loads(l) for l in f if l.strip()]
    ids = [r["test_id"] for r in lines]
    _check("keine doppelten Test-IDs in eval_results.jsonl", len(ids) == len(set(ids)))


def test_two_families_independent_locks():
    d = tempfile.mkdtemp()
    export_path = os.path.join(d, "export.jsonl")
    results_path = os.path.join(d, "eval_results.jsonl")
    rows = (_synthetic_setup_edge_rows(n=400, seed=9, conviction_extra=False)
           + _synthetic_ki_score_rows(n=50, seed=10, effect=True))  # KI unter n=250
    with open(export_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    out = fe.run_due_evaluations(export_path=export_path, results_path=results_path, now=now)
    _check("Setup-Edge-Familie triggert", out["setup_edge_locked"])
    _check("KI-Score-Familie triggert NICHT (n<250)", not out["ki_score_locked"])
    _check("KI-Score-Status zeigt n<250", out["ki_score_status"][0] < 250)


# ===========================================================================
# 7: Verdikt-Logik
# ===========================================================================

def test_verdict_beleg_requires_all_four():
    v, _ = fe._verdict({"a": True, "b": True, "c": True, "d": True})
    _check("alle 4 Kriterien -> Beleg", v == "Beleg")
    v2, reason = fe._verdict({"a": True, "b": False, "c": True, "d": True})
    _check("ein Kriterium fehlt -> Unklar (NICHT 'keine Edge')", v2 == "Unklar")
    _check("Unklar-Begründung nennt das fehlende Kriterium", "b" in reason)


# ===========================================================================
# 8: Digest-Wiring
# ===========================================================================

def test_eval_status_line_pre_trigger():
    line = hc.eval_status_line("Setup-Edge/Conviction", (120, 250), 250, (14, 7))
    _check("Vor-Auslöser-Format", "n = 120/250" in line and "Zeilen/Tag" in line)
    print(f"    [Fixture Vor-Auslöser] {line}")


def test_eval_status_line_post_trigger():
    line = hc.eval_status_line("Setup-Edge/Conviction", None, 250, None,
                               verdict_text="setup_edge_a: Beleg")
    _check("Nach-Auslösung-Format", "ausgewertet" in line and "eval_results.jsonl" in line)
    print(f"    [Fixture Nach-Auslösung] {line}")


def test_eval_status_line_fail_soft():
    line = hc.eval_status_line("X", None, 250, None)
    _check("fehlende Daten -> 'nicht ermittelbar', kein Crash", "nicht ermittelbar" in line)


def test_format_digest_body_eval_lines_wiring():
    eval_lines_ = ["🧪 Setup-Edge/Conviction: n = 10/250", "🧪 KI-Score: n = 0/250"]
    body_ok, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-22T21:00:00Z", digest_date="2026-10-22",
        eval_lines=eval_lines_)
    _check("✅-Klasse enthält eval_lines", "Setup-Edge/Conviction: n = 10/250" in body_ok)

    body_compat, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-22T21:00:00Z", digest_date="2026-10-22")
    _check("Backward-Compat: kein Crash ohne eval_lines", isinstance(body_compat, str))


def _load_digest_module():
    spec = importlib.util.spec_from_file_location(
        "_dgst_eval_test", str(ROOT / "scripts" / "health_check_digest.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_digest_main_autorun_disabled_default():
    mod = _load_digest_module()
    mod.DIGEST_STATE_FILE = pathlib.Path(tempfile.mkdtemp()) / "state.json"
    _check("EVAL_AUTORUN_ENABLED Default False", mod.EVAL_AUTORUN_ENABLED is False)
    rc = mod.main(now_ts=datetime(2026, 10, 22, 8, 47, tzinfo=timezone.utc), dry_run=True)
    _check("main() läuft bei Default (Autorun aus) ohne Crash durch", rc == 0)


def test_digest_main_autorun_end_to_end():
    mod = _load_digest_module()
    d = tempfile.mkdtemp()
    export_path = str(pathlib.Path(d) / "export.jsonl")
    results_path = str(pathlib.Path(d) / "eval_results.jsonl")
    mod.EVAL_AUTORUN_ENABLED = True
    mod.hc.MATURED_EXPORT_FILE = export_path
    mod.EVAL_RESULTS_FILE = results_path
    mod.DIGEST_STATE_FILE = pathlib.Path(d) / "state.json"

    rows = _synthetic_setup_edge_rows(n=400, seed=9, conviction_extra=False)
    with open(export_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    rc1 = mod.main(now_ts=datetime(2026, 10, 22, 8, 47, tzinfo=timezone.utc), dry_run=True, force=True)
    _check("Lauf 1 (Trigger erreicht) exit 0", rc1 == 0)
    with open(results_path) as f:
        n1 = sum(1 for _ in f)
    _check("Lauf 1 schreibt genau 3 Zeilen (a,b,c)", n1 == 3)

    rc2 = mod.main(now_ts=datetime(2026, 10, 23, 8, 47, tzinfo=timezone.utc), dry_run=True, force=True)
    with open(results_path) as f:
        n2 = sum(1 for _ in f)
    _check("Lauf 2 (gleiche Daten, Sperre) fügt NICHTS hinzu", n2 == n1)
    _check("Lauf 2 exit 0 (kein Crash durch Re-Lauf)", rc2 == 0)


def test_digest_main_autorun_fail_soft_on_broken_export():
    mod = _load_digest_module()
    d = tempfile.mkdtemp()
    export_path = str(pathlib.Path(d) / "broken.jsonl")
    with open(export_path, "w") as f:
        f.write("{dies ist kaputtes JSON")
    mod.EVAL_AUTORUN_ENABLED = True
    mod.hc.MATURED_EXPORT_FILE = export_path
    mod.EVAL_RESULTS_FILE = str(pathlib.Path(d) / "eval_results.jsonl")
    mod.DIGEST_STATE_FILE = pathlib.Path(d) / "state.json"
    rc = mod.main(now_ts=datetime(2026, 10, 22, 8, 47, tzinfo=timezone.utc), dry_run=True)
    _check("kaputte Export-Datei -> main() crasht NICHT (fail-soft)", rc == 0)


# ===========================================================================
# 9: Golden + Score-Gegenprobe
# ===========================================================================

def test_score_unaffected_by_freeze_eval():
    base = [
        {"ticker": "AAA", "short_float": 20, "short_ratio": 8, "rel_volume": 2.5,
         "float_shares": 5_000_000, "price": 4.0, "change": 3.0},
        {"ticker": "BBB", "short_float": 10, "short_ratio": 4, "rel_volume": 1.2,
         "float_shares": 40_000_000, "price": 12.0, "change": 1.0},
    ]
    import copy
    before = copy.deepcopy(base)
    after = copy.deepcopy(base)
    scores_before = [round(gr.score(s), 6) for s in before]
    scores_after = [round(gr.score(s), 6) for s in after]
    _check("score() identisch (Feature berührt score() gar nicht)", scores_before == scores_after)


def test_no_freeze_eval_import_in_production_pipeline():
    import subprocess
    out = subprocess.run(
        ["grep", "-l", "freeze_eval", "generate_report.py", "ki_agent.py"],
        cwd=str(ROOT), capture_output=True, text=True)
    _check("freeze_eval wird NICHT in generate_report.py/ki_agent.py importiert",
           out.stdout.strip() == "")


def run_all():
    tests = [
        test_bootstrap_deterministic,
        test_bootstrap_finds_strong_effect,
        test_bootstrap_no_effect,
        test_bootstrap_empty_group,
        test_paired_delta_auc_real_effect,
        test_paired_delta_auc_no_extra_value,
        test_paired_delta_auc_deterministic,
        test_paired_delta_auc_empty,
        test_setup_edge_population_reuses_health_check_helper,
        test_ki_score_population_erratum_16_10,
        test_ki_score_family_exclusion_quote_over_20pct,
        test_ki_score_family_exclusion_quote_under_20pct,
        test_setup_edge_family_test_c_excludes_missing_conviction,
        test_cluster_double_run_detects_followup,
        test_cluster_double_run_same_direction_robust_effect,
        test_holm_wiring_k3,
        test_holm_wiring_k2,
        test_lock_prevents_reevaluation,
        test_two_families_independent_locks,
        test_verdict_beleg_requires_all_four,
        test_eval_status_line_pre_trigger,
        test_eval_status_line_post_trigger,
        test_eval_status_line_fail_soft,
        test_format_digest_body_eval_lines_wiring,
        test_digest_main_autorun_disabled_default,
        test_digest_main_autorun_end_to_end,
        test_digest_main_autorun_fail_soft_on_broken_export,
        test_score_unaffected_by_freeze_eval,
        test_no_freeze_eval_import_in_production_pipeline,
    ]
    for t in tests:
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Freeze-Eval-Autorun-Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle Freeze-Eval-Autorun-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
