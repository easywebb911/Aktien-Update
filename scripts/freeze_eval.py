"""Freeze-Auswertungs-Engine (Erratum 22.10.2026) — automatischer, einmaliger
Auslöser für die eingefrorenen Edge-Test-Freezes, sobald ihr jeweiliger
Auslöser (n>=250) erreicht ist.

Betroffene Freezes (SESSION_HANDOVER.md):
  - "VORABREGISTRIERUNG — Setup-Edge-Re-Test (Score-Trennschärfe),
    eingefroren 10.10.2026" + Erratum 10.10.2026 (Test c, Conviction-
    Zusatznutzen) — Tests a, b, c, Holm-Familie k=3.
  - "VORABREGISTRIERUNG — KI-Score-Edge-Test (ki_signal_score),
    eingefroren 13.10.2026" + Erratum 16.10.2026 — Tests a, b, eigene
    Holm-Familie k=2.
  - "ERRATUM 22.10.2026 — Bootstrap-Verfahrensdetails..." legt die bis
    dahin offenen Bootstrap-Details fest: Seed=42, N=2000 (unverändert),
    95% zweiseitiges Perzentil-Intervall (2,5./97,5.), Ausschluss-Regel
    für fehlenden ``conviction_score`` in Test c (Spiegel der KI-Score-
    Regel vom 16.10.2026).
  - "VORABREGISTRIERUNG — eingefroren 05.08.2026" (§4, Exit-B.1-Re-Test,
    Exit-Timing-Hinweis) + "Protokolleintrag 31.10.2026" (drei
    Verfahrens-Lücken geklärt — Δ-Mechanik, Regime-Split-Mechanik,
    Seed — VOR Erreichen von n=250, bei n=242, Ergebnis unbekannt) —
    Tests a (Δ(5d−10d)), b (Δ(3d−10d)), eigene Holm-Familie k=2.
    ANDERS als die zwei obigen Familien: Zielgröße ist eine gepaarte
    pp-Mittelwert-Differenz (kein AUC), Population ist rein
    ``provenance=forward ∧ score≥70`` (KEIN Datums-Filter, Definition A).

ARCHITEKTUR-DISZIPLIN (analog ``scripts/stats_helpers.py``):
  - Reine Funktionen für die Statistik (``bootstrap_auc_ci``,
    ``paired_bootstrap_delta_auc``, ``cluster_double_run``) — kein
    File-I/O, Caller übergibt Zeilen-Listen explizit.
  - ``evaluate_setup_edge_family`` / ``evaluate_ki_score_family`` sind
    ebenfalls reine Funktionen (nehmen bereits eingelesene Export-Zeilen
    entgegen) — testbar mit synthetischen Fixtures, OHNE echte Daten.
  - ``run_due_evaluations`` ist die EINZIGE Stelle mit File-I/O
    (``matured_backtest_export.jsonl`` lesen, ``eval_results.jsonl``
    lesen+schreiben) — wird von ``scripts/health_check_digest.py``
    aufgerufen, fail-soft gewrappt, NUR wenn
    ``config.EVAL_AUTORUN_ENABLED`` True ist.
  - SPERRE / KEIN PEEKING: ``eval_results.jsonl`` ist die Sperre selbst
    — ein Test-ID, das dort bereits eine Zeile hat, wird NIE erneut
    ausgewertet, auch wenn der Auslöser weiterhin erfüllt ist (append-
    only, ein Eintrag pro Test-ID für immer).

KEIN Eingriff in score()/Top-10/Filter/Push/apply_agent_boost/Conviction —
reine Analyse-Persistenz, analog ``backtest_history.py``/
``matured_export.py``. Pure stdlib (``random``, ``hashlib``, ``math``,
``subprocess``) — keine neue Bibliothek.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import pathlib
import random
import subprocess
import sys
from datetime import datetime, timezone
from typing import Callable, Sequence

_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config  # noqa: E402
import health_check as hc  # noqa: E402
from stats_helpers import (  # noqa: E402
    mann_whitney_u_auc, multiple_testing_correction,
    wilcoxon_signed_rank_paired)
from cluster_purge import classify_cluster_records  # noqa: E402

log = logging.getLogger(__name__)

SCHEMA_V = 1

__all__ = [
    "bootstrap_auc_ci", "paired_bootstrap_delta_auc", "paired_bootstrap_mean_delta",
    "cluster_double_run", "auc_test_with_ci", "evaluate_setup_edge_family",
    "evaluate_ki_score_family", "evaluate_exit_b1_family", "run_due_evaluations",
]


# ── Perzentil (identisches R-7/numpy-Default-Verfahren wie
#    scripts/expectancy_diagnose.py:percentile — eigenständige Kopie, um
#    keine Import-Kopplung an eine unabhängige, abgeschlossene Diagnose
#    einzuführen) ───────────────────────────────────────────────────────
def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def _is_finite_number(x) -> bool:
    return (isinstance(x, (int, float)) and not isinstance(x, bool)
            and math.isfinite(x))


# ── Bootstrap-Primitive (Erratum 22.10.2026: N=2000, Seed=42, 95%
#    zweiseitig, Perzentil-Methode 2,5./97,5.) ──────────────────────────
def bootstrap_auc_ci(group_a: Sequence[float], group_b: Sequence[float], *,
                     n_iter: int = config.EVAL_BOOTSTRAP_N,
                     seed: int = config.EVAL_BOOTSTRAP_SEED,
                     lo_pct: float = config.EVAL_BOOTSTRAP_CI_LO,
                     hi_pct: float = config.EVAL_BOOTSTRAP_CI_HI) -> dict:
    """Bootstrap-CI der AUC — unabhängiges Resampling MIT Zurücklegen je
    Gruppe, ``n_iter`` Wiederholungen, fester ``seed``. Punktschätzung ist
    die AUC auf den ORIGINAL-Gruppen (kein Bootstrap-Mittelwert); das CI
    ist das ``[lo_pct, hi_pct]``-Perzentil der Resample-Verteilung.

    Returnt ``{point_auc, ci_lo, ci_hi, p_two_sided, n_a, n_b, n_iter,
    seed, note}``. ``p_two_sided`` ist der Mann-Whitney-p-Wert auf den
    ORIGINAL-Gruppen (NICHT bootstrap-basiert) — das ist der Holm-Input
    (siehe ``multiple_testing_correction``-Aufruf in den
    ``evaluate_*_family``-Funktionen)."""
    a = list(group_a)
    b = list(group_b)
    n_a, n_b = len(a), len(b)
    point = mann_whitney_u_auc(a, b)
    if n_a == 0 or n_b == 0:
        return {"point_auc": None, "ci_lo": None, "ci_hi": None,
                "p_two_sided": None, "n_a": n_a, "n_b": n_b,
                "n_iter": n_iter, "seed": seed,
                "note": "Mindestens eine Gruppe ist leer."}
    rng = random.Random(seed)
    aucs: list[float] = []
    for _ in range(n_iter):
        sample_a = [a[rng.randrange(n_a)] for _ in range(n_a)]
        sample_b = [b[rng.randrange(n_b)] for _ in range(n_b)]
        r = mann_whitney_u_auc(sample_a, sample_b)
        if r["auc"] is not None:
            aucs.append(r["auc"])
    if not aucs:
        return {"point_auc": point["auc"], "ci_lo": None, "ci_hi": None,
                "p_two_sided": point["p_two_sided"], "n_a": n_a, "n_b": n_b,
                "n_iter": n_iter, "seed": seed,
                "note": "Keine gültige Resample-AUC (alle Resamples degeneriert)."}
    aucs.sort()
    return {"point_auc": point["auc"],
            "ci_lo": _percentile(aucs, lo_pct),
            "ci_hi": _percentile(aucs, hi_pct),
            "p_two_sided": point["p_two_sided"],
            "n_a": n_a, "n_b": n_b, "n_iter": n_iter, "seed": seed,
            "note": None}


def auc_test_with_ci(rows: Sequence[dict], *, value_field: str,
                     label_field: str, threshold: float, inclusive: bool,
                     **bootstrap_kwargs) -> dict:
    """Baut Gewinner-/Verlierer-Gruppen aus ``rows`` (Gewinner: ``label_field
    >= threshold`` wenn ``inclusive`` sonst ``> threshold``) und ruft
    ``bootstrap_auc_ci`` auf ``value_field``-Werten. Zeilen mit fehlendem/
    nicht-numerischem ``value_field`` oder ``label_field`` werden
    übersprungen (nicht Teil von n_a/n_b)."""
    winners: list[float] = []
    losers: list[float] = []
    for r in rows:
        v = r.get(value_field)
        lab = r.get(label_field)
        if not _is_finite_number(v) or not _is_finite_number(lab):
            continue
        is_winner = (lab >= threshold) if inclusive else (lab > threshold)
        (winners if is_winner else losers).append(v)
    return bootstrap_auc_ci(winners, losers, **bootstrap_kwargs)


def paired_bootstrap_delta_auc(rows: Sequence[dict], *, score_field_a: str,
                               score_field_b: str, label_field: str,
                               label_threshold: float,
                               n_iter: int = config.EVAL_BOOTSTRAP_N,
                               seed: int = config.EVAL_BOOTSTRAP_SEED,
                               lo_pct: float = config.EVAL_BOOTSTRAP_CI_LO,
                               hi_pct: float = config.EVAL_BOOTSTRAP_CI_HI) -> dict:
    """Gepaarter Bootstrap für ΔAUC = AUC(score_field_a) − AUC(score_field_b)
    (Erratum 10.10.2026, Test c, Punkt 3 — Verfahren wörtlich umgesetzt):

      (a) pro Resample denselben Zeilen-Index resampled (MIT Zurücklegen),
          damit ``score_field_a`` und ``score_field_b`` auf identischen
          Zeilen verglichen werden ("gepaart");
      (b) auf diesem Resample zweimal ``mann_whitney_u_auc`` (Gewinner-
          vs-Verlierer-Split nach ``label_field >= label_threshold``,
          einmal mit ``score_field_a``, einmal mit ``score_field_b``);
      (c) die Differenz der beiden AUCs wird gesammelt.

    ``rows`` MUSS bereits auf die Test-c-Population reduziert sein (Zeilen
    ohne verwertbaren ``score_field_a``-Wert sind VORHER ausgeschlossen —
    Erratum 22.10.2026, Punkt 3). Zeilen mit fehlendem/nicht-numerischem
    ``score_field_b`` oder ``label_field`` werden pro Resample aus dem
    jeweiligen Split entfernt (defensiv — sollte bei korrekt vorgefilterten
    ``rows`` nicht vorkommen, da ``score`` auf Forward-Zeilen praktisch
    immer vorhanden ist).

    Returnt ``{point_delta, ci_lo, ci_hi, auc_a, auc_b, p_two_sided, n,
    n_iter, seed, note}``. ``p_two_sided`` ist der Holm-Input für Test c
    (Erratum 22.10.2026 (b), verbindlich festgelegt — NICHT der p-Wert von
    ``auc_a`` gegen 0,5): der zweiseitige Bootstrap-p-Wert der ΔAUC-
    Verteilung selbst, ``p = min(1, 2 · min(Anteil Resamples mit ΔAUC<=0,
    Anteil Resamples mit ΔAUC>=0))`` — reine Proportion auf der bereits für
    das CI berechneten Resample-Verteilung, kein zweiter Bootstrap-Lauf."""
    n = len(rows)
    labels = [r.get(label_field) for r in rows]
    vals_a = [r.get(score_field_a) for r in rows]
    vals_b = [r.get(score_field_b) for r in rows]

    def _split(idx_list):
        a_win, a_lose, b_win, b_lose = [], [], [], []
        for i in idx_list:
            lab = labels[i]
            if not _is_finite_number(lab):
                continue
            is_winner = lab >= label_threshold
            va, vb = vals_a[i], vals_b[i]
            if _is_finite_number(va):
                (a_win if is_winner else a_lose).append(va)
            if _is_finite_number(vb):
                (b_win if is_winner else b_lose).append(vb)
        return a_win, a_lose, b_win, b_lose

    if n == 0:
        return {"point_delta": None, "ci_lo": None, "ci_hi": None,
                "auc_a": None, "auc_b": None, "p_two_sided": None, "n": 0,
                "n_iter": n_iter, "seed": seed, "note": "Keine Zeilen."}

    a_win, a_lose, b_win, b_lose = _split(range(n))
    auc_a = mann_whitney_u_auc(a_win, a_lose)
    auc_b = mann_whitney_u_auc(b_win, b_lose)
    point_delta = (auc_a["auc"] - auc_b["auc"]
                  if auc_a["auc"] is not None and auc_b["auc"] is not None
                  else None)

    rng = random.Random(seed)
    deltas: list[float] = []
    for _ in range(n_iter):
        resample_idx = [rng.randrange(n) for _ in range(n)]
        aw, al, bw, bl = _split(resample_idx)
        ra = mann_whitney_u_auc(aw, al)
        rb = mann_whitney_u_auc(bw, bl)
        if ra["auc"] is not None and rb["auc"] is not None:
            deltas.append(ra["auc"] - rb["auc"])

    if not deltas:
        return {"point_delta": point_delta, "ci_lo": None, "ci_hi": None,
                "auc_a": auc_a["auc"], "auc_b": auc_b["auc"],
                "p_two_sided": None, "n": n, "n_iter": n_iter, "seed": seed,
                "note": "Keine gültige Resample-Differenz."}
    deltas.sort()
    # Erratum 22.10.2026 (b): p_c = min(1, 2 * min(Anteil <=0, Anteil >=0)).
    n_deltas = len(deltas)
    frac_le0 = sum(1 for d in deltas if d <= 0.0) / n_deltas
    frac_ge0 = sum(1 for d in deltas if d >= 0.0) / n_deltas
    p_two_sided = min(1.0, 2.0 * min(frac_le0, frac_ge0))
    return {"point_delta": point_delta,
            "ci_lo": _percentile(deltas, lo_pct),
            "ci_hi": _percentile(deltas, hi_pct),
            "auc_a": auc_a["auc"], "auc_b": auc_b["auc"],
            "p_two_sided": p_two_sided, "n": n,
            "n_iter": n_iter, "seed": seed, "note": None}


def paired_bootstrap_mean_delta(values_a: Sequence[float], values_b: Sequence[float], *,
                                n_iter: int = config.EVAL_BOOTSTRAP_N,
                                seed: int = config.EVAL_BOOTSTRAP_SEED,
                                lo_pct: float = config.EVAL_BOOTSTRAP_CI_LO,
                                hi_pct: float = config.EVAL_BOOTSTRAP_CI_HI) -> dict:
    """Gepaarter Bootstrap der Mittelwert-Differenz Δ = Mittel(a) − Mittel(b)
    in den ORIGINAL-Einheiten (z. B. Prozentpunkte) — KEIN AUC-Maß.

    §4-Exit-B.1-Protokolleintrag 31.10.2026, Punkt 1 (verbatim umgesetzt):
    pro Resample wird EIN gemeinsamer Zeilen-Index-Vektor (mit
    Zurücklegen) gezogen und auf BEIDE Arrays angewandt — ``values_a[i]``
    und ``values_b[i]`` gehören zur selben Zeile (z. B. ``return_5d``/
    ``return_10d`` derselben Backtest-Zeile), die Paarung bleibt über
    jedes Resample erhalten. Punktschätzung ist Δ auf den ORIGINAL-Arrays
    (kein Bootstrap-Mittelwert). ``values_a``/``values_b`` müssen gleich
    lang sein.

    Der Holm-Input (p-Wert) kommt NICHT aus diesem Bootstrap — das
    Protokoll legt dafür ``mann_whitney_u_auc`` auf den beiden
    UNABHÄNGIGEN Original-Arrays fest (siehe Caller
    ``evaluate_exit_b1_family``). Diese Funktion liefert ausschließlich
    die Δ-Schätzung + ihr Bootstrap-CI.

    Returnt ``{point_delta, ci_lo, ci_hi, n, n_iter, seed, note}``.
    ``note`` bei ungültigem Input (leer, unterschiedliche Länge)."""
    a = list(values_a)
    b = list(values_b)
    n = len(a)
    if n != len(b) or n == 0:
        return {"point_delta": None, "ci_lo": None, "ci_hi": None, "n": n,
                "n_iter": n_iter, "seed": seed,
                "note": "values_a/values_b leer oder unterschiedlich lang."}
    point_delta = sum(a) / n - sum(b) / n
    rng = random.Random(seed)
    deltas: list[float] = []
    for _ in range(n_iter):
        idx = [rng.randrange(n) for _ in range(n)]
        ra = [a[i] for i in idx]
        rb = [b[i] for i in idx]
        deltas.append(sum(ra) / n - sum(rb) / n)
    deltas.sort()
    return {"point_delta": point_delta,
            "ci_lo": _percentile(deltas, lo_pct),
            "ci_hi": _percentile(deltas, hi_pct),
            "n": n, "n_iter": n_iter, "seed": seed, "note": None}


def cluster_double_run(rows: Sequence[dict], eval_fn: Callable[[Sequence[dict]], dict],
                       *, point_key: str, baseline: float) -> dict:
    """Führt ``eval_fn(rows)`` zweimal aus — einmal mit ALLEN Zeilen, einmal
    OHNE Cluster-Folgeeinträge (``classify_cluster_records`` — Erratum/
    Freeze Kriterium (iii): "Cluster-Doppellauf ... liefert dieselbe
    Richtung"). ``rows`` müssen ``ticker``/``date``/``entry_price`` tragen
    (``cluster_purge``-Vertrag). ``point_key`` benennt das Feld im
    ``eval_fn``-Rückgabe-Dict, dessen Vorzeichen relativ zu ``baseline``
    (0,5 für AUC, 0 für ΔAUC) in beiden Läufen verglichen wird."""
    with_result = eval_fn(rows)
    classified = classify_cluster_records(
        [{"ticker": r.get("ticker"), "date": r.get("date"),
          "entry_price": r.get("entry_price")} for r in rows])
    followup_keys = {(c["ticker"], c["date"]) for c in classified
                     if c["is_cluster_followup"]}
    rows_no_cluster = [r for r in rows
                       if (r.get("ticker"), r.get("date")) not in followup_keys]
    without_result = eval_fn(rows_no_cluster)

    p_with = with_result.get(point_key)
    p_without = without_result.get(point_key)
    if p_with is None or p_without is None:
        same_direction = None
    else:
        same_direction = (p_with - baseline > 0) == (p_without - baseline > 0)

    return {
        "with_cluster": with_result,
        "without_cluster": without_result,
        "n_cluster_followups_removed": len(rows) - len(rows_no_cluster),
        "same_direction": same_direction,
    }


# ── Population-Filter (Single-Source-of-Truth-Reuse aus health_check.py
#    wo vorhanden — keine Logik-Duplikation) ───────────────────────────
def _dedup_rows(rows: Sequence[dict]) -> list[dict]:
    """Dedupe nach ``(ticker, date)`` — analog ``_freeze_population_keys``-
    Diszplin, defensiv gegen eine theoretisch mögliche doppelte Export-
    Zeile. Erste Vorkommnis gewinnt, Reihenfolge erhalten."""
    seen: set = set()
    out: list[dict] = []
    for r in rows:
        key = (r.get("ticker"), r.get("date"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _split_by_usable_field(rows: Sequence[dict], field: str) -> tuple[list[dict], list[dict]]:
    """Teilt ``rows`` in (verwertbar, ausgeschlossen) nach
    ``_is_finite_number(row.get(field))`` — Basis für die Ausschluss-Quote-
    Berichterstattung (Erratum 22.10.2026, Punkt 3)."""
    usable, excluded = [], []
    for r in rows:
        (usable if _is_finite_number(r.get(field)) else excluded).append(r)
    return usable, excluded


def _verdict(criteria: dict) -> tuple[str, str]:
    """Verdikt-Logik (Freeze-Grenzen-Klausel, wörtlich übernommen: "Eine
    Punktschätzung allein ist nie ein Beleg" + "ein schwacher Effekt
    bleibt 'unklar', nicht 'keine Edge'"): ALLE Kriterien erfüllt -> Beleg,
    sonst -> Unklar (NIE "keine Edge" — das ist laut Freeze-Text bei
    n≈250 nicht aussprechbar)."""
    if all(criteria.values()):
        return "Beleg", "alle vier Erfolgskriterien erfüllt"
    failed = [k for k, v in criteria.items() if not v]
    return "Unklar", f"Kriterien nicht erfüllt: {', '.join(failed)} — keine Edge-Widerlegung (Freeze-Grenze)"


# ── Setup-Edge/Conviction-Familie (Tests a, b, c — Holm k=3) ───────────
def evaluate_setup_edge_family(export_rows: Sequence[dict], *,
                               freeze_date_str: str | None = None,
                               now: datetime | None = None) -> dict:
    """Komplette, deterministische Auswertung für Tests a (AUC score vs.
    return_5d≥+5%), b (AUC score vs. return_10d>0), c (ΔAUC conviction−
    score, Erratum 10.10.2026). Reine Funktion — ``export_rows`` sind
    bereits eingelesene, UNGEFILTERTE Export-Zeilen."""
    freeze_date_str = freeze_date_str or config.SETUP_EDGE_FREEZE_DATE
    freeze_date = hc._parse_dmy_date(freeze_date_str)
    now = now or datetime.now(timezone.utc)

    pop_rows = _dedup_rows([r for r in export_rows if hc._is_freeze_population_row(r, freeze_date)])
    n_ab = len(pop_rows)

    def eval_a(rs):
        return auc_test_with_ci(rs, value_field="score", label_field="return_5d",
                                threshold=5.0, inclusive=True)

    def eval_b(rs):
        return auc_test_with_ci(rs, value_field="score", label_field="return_10d",
                                threshold=0.0, inclusive=False)

    cluster_a = cluster_double_run(pop_rows, eval_a, point_key="point_auc", baseline=0.5)
    cluster_b = cluster_double_run(pop_rows, eval_b, point_key="point_auc", baseline=0.5)

    # Test c: Population = Test-a/b-Population MINUS Zeilen ohne verwertbaren
    # conviction_score (Erratum 22.10.2026, Punkt 3 — Spiegel der KI-Score-
    # Regel vom 16.10.2026).
    conv_usable, conv_excluded = _split_by_usable_field(pop_rows, "conviction_score")
    n_c = len(conv_usable)
    pct_excluded_c = (len(conv_excluded) / n_ab * 100.0) if n_ab else 0.0

    def eval_c_auc_component(rs):
        # AUC(conviction_score) SELBST — identische Mechanik wie Test a,
        # nur mit conviction_score statt score (Holm-Input für Test c,
        # siehe Erratum 10.10.2026 Punkt 5(iv): "AUC(conviction_score)
        # selbst >= 0,55" als eigenständige Teilgröße).
        return auc_test_with_ci(rs, value_field="conviction_score", label_field="return_5d",
                                threshold=5.0, inclusive=True)

    def eval_c_delta(rs):
        return paired_bootstrap_delta_auc(rs, score_field_a="conviction_score",
                                         score_field_b="score", label_field="return_5d",
                                         label_threshold=5.0)

    cluster_c_auc = cluster_double_run(conv_usable, eval_c_auc_component,
                                       point_key="point_auc", baseline=0.5)
    cluster_c_delta = cluster_double_run(conv_usable, eval_c_delta,
                                         point_key="point_delta", baseline=0.0)

    p_a = cluster_a["with_cluster"]["p_two_sided"]
    p_b = cluster_b["with_cluster"]["p_two_sided"]
    # Erratum 22.10.2026 (b): Holm-Input p_c ist der Bootstrap-p-Wert der
    # ΔAUC-Verteilung SELBST (cluster_c_delta), NICHT der p-Wert von
    # AUC(conviction_score) gegen 0,5 (cluster_c_auc) — vorher war das
    # nirgends wörtlich festgelegt (Guardian-Finding PR #597).
    p_c = cluster_c_delta["with_cluster"]["p_two_sided"]
    holm = multiple_testing_correction([p_a, p_b, p_c], labels=["a", "b", "c"])

    def _holm_sig(label):
        for row in holm.get("results", []):
            if row.get("label") == label:
                return bool(row.get("holm_reject"))
        return False

    auc_a_point = cluster_a["with_cluster"]["point_auc"]
    auc_a_ci_lo = cluster_a["with_cluster"]["ci_lo"]
    criteria_a = {
        "holm_significant": _holm_sig("a"),
        "ci_above_baseline": (auc_a_ci_lo is not None and auc_a_ci_lo > 0.5),
        "cluster_same_direction": bool(cluster_a["same_direction"]),
        "point_above_threshold": (auc_a_point is not None and auc_a_point >= 0.55),
    }
    verdict_a, verdict_a_reason = _verdict(criteria_a)

    auc_b_point = cluster_b["with_cluster"]["point_auc"]
    auc_b_ci_lo = cluster_b["with_cluster"]["ci_lo"]
    criteria_b = {
        "holm_significant": _holm_sig("b"),
        "ci_above_baseline": (auc_b_ci_lo is not None and auc_b_ci_lo > 0.5),
        "cluster_same_direction": bool(cluster_b["same_direction"]),
        "point_above_threshold": (auc_b_point is not None and auc_b_point >= 0.55),
    }
    verdict_b, verdict_b_reason = _verdict(criteria_b)

    auc_conv_point = cluster_c_auc["with_cluster"]["point_auc"]
    delta_point = cluster_c_delta["with_cluster"]["point_delta"]
    delta_ci_lo = cluster_c_delta["with_cluster"]["ci_lo"]
    criteria_c = {
        "holm_significant": _holm_sig("c"),
        "delta_ci_above_zero": (delta_ci_lo is not None and delta_ci_lo > 0.0),
        "cluster_same_direction": bool(cluster_c_auc["same_direction"]) and bool(cluster_c_delta["same_direction"]),
        "point_above_threshold": (delta_point is not None and delta_point >= 0.02
                                  and auc_conv_point is not None and auc_conv_point >= 0.55),
    }
    verdict_c, verdict_c_reason = _verdict(criteria_c)

    return {
        "schema_v": SCHEMA_V,
        "family": "setup_edge_conviction",
        "freeze_date": freeze_date_str,
        "evaluated_at": now.isoformat(),
        "n_ab": n_ab,
        "tests": {
            "a": {
                "test_id": "setup_edge_a", "n": n_ab,
                "n_excluded": 0, "pct_excluded": 0.0,
                "statistic": cluster_a["with_cluster"],
                "cluster_double_run": {
                    "without_cluster_point_auc": cluster_a["without_cluster"]["point_auc"],
                    "n_cluster_followups_removed": cluster_a["n_cluster_followups_removed"],
                    "same_direction": cluster_a["same_direction"],
                },
                "p_raw": p_a, "holm_reject": _holm_reject(holm, "a"),
                "criteria": criteria_a, "verdict": verdict_a, "verdict_reason": verdict_a_reason,
            },
            "b": {
                "test_id": "setup_edge_b", "n": n_ab,
                "n_excluded": 0, "pct_excluded": 0.0,
                "statistic": cluster_b["with_cluster"],
                "cluster_double_run": {
                    "without_cluster_point_auc": cluster_b["without_cluster"]["point_auc"],
                    "n_cluster_followups_removed": cluster_b["n_cluster_followups_removed"],
                    "same_direction": cluster_b["same_direction"],
                },
                "p_raw": p_b, "holm_reject": _holm_reject(holm, "b"),
                "criteria": criteria_b, "verdict": verdict_b, "verdict_reason": verdict_b_reason,
            },
            "c": {
                "test_id": "setup_edge_conviction_c", "n": n_c,
                "n_excluded": len(conv_excluded), "pct_excluded": pct_excluded_c,
                "auc_conviction_component": cluster_c_auc["with_cluster"],
                "delta_statistic": cluster_c_delta["with_cluster"],
                "cluster_double_run": {
                    "auc_same_direction": cluster_c_auc["same_direction"],
                    "delta_same_direction": cluster_c_delta["same_direction"],
                    "n_cluster_followups_removed": cluster_c_delta["n_cluster_followups_removed"],
                },
                "p_raw": p_c, "holm_reject": _holm_reject(holm, "c"),
                "criteria": criteria_c, "verdict": verdict_c, "verdict_reason": verdict_c_reason,
            },
        },
        "holm": holm,
    }


# ── KI-Score-Familie (Tests a, b — eigene Holm-Familie k=2) ────────────
def evaluate_ki_score_family(export_rows: Sequence[dict], *,
                             freeze_date_str: str | None = None,
                             now: datetime | None = None) -> dict:
    """Komplette, deterministische Auswertung für Tests a (AUC ki_signal_
    score vs. return_5d≥+5%), b (AUC ki_signal_score vs. return_10d>0).
    Population + Ausschluss-Regel exakt nach Erratum 16.10.2026
    ("Population — präzisiert"). Eigene Holm-Familie k=2 (Freeze-Punkt 4:
    NICHT mit der Setup/Conviction-Familie zusammengelegt)."""
    freeze_date_str = freeze_date_str or config.KI_SCORE_FREEZE_DATE
    freeze_date = hc._parse_dmy_date(freeze_date_str)
    now = now or datetime.now(timezone.utc)

    candidate_rows = _dedup_rows([r for r in export_rows if hc._is_ki_score_candidate_row(r, freeze_date)])
    pop_rows = [r for r in candidate_rows if hc._is_finite_number(r.get("ki_signal_score"))]
    excluded_rows = [r for r in candidate_rows if not hc._is_finite_number(r.get("ki_signal_score"))]
    n_candidates = len(candidate_rows)
    n_pop = len(pop_rows)
    pct_excluded = (len(excluded_rows) / n_candidates * 100.0) if n_candidates else 0.0

    def eval_a(rs):
        return auc_test_with_ci(rs, value_field="ki_signal_score", label_field="return_5d",
                                threshold=5.0, inclusive=True)

    def eval_b(rs):
        return auc_test_with_ci(rs, value_field="ki_signal_score", label_field="return_10d",
                                threshold=0.0, inclusive=False)

    cluster_a = cluster_double_run(pop_rows, eval_a, point_key="point_auc", baseline=0.5)
    cluster_b = cluster_double_run(pop_rows, eval_b, point_key="point_auc", baseline=0.5)

    p_a = cluster_a["with_cluster"]["p_two_sided"]
    p_b = cluster_b["with_cluster"]["p_two_sided"]
    holm = multiple_testing_correction([p_a, p_b], labels=["a", "b"])

    def _holm_sig(label):
        for row in holm.get("results", []):
            if row.get("label") == label:
                return bool(row.get("holm_reject"))
        return False

    auc_a_point = cluster_a["with_cluster"]["point_auc"]
    auc_a_ci_lo = cluster_a["with_cluster"]["ci_lo"]
    criteria_a = {
        "holm_significant": _holm_sig("a"),
        "ci_above_baseline": (auc_a_ci_lo is not None and auc_a_ci_lo > 0.5),
        "cluster_same_direction": bool(cluster_a["same_direction"]),
        "point_above_threshold": (auc_a_point is not None and auc_a_point >= 0.55),
    }
    verdict_a, verdict_a_reason = _verdict(criteria_a)
    if pct_excluded > 20.0:
        verdict_a_reason += f" (Einschränkung: {pct_excluded:.1f}% der Kandidaten ohne verwertbaren Score ausgeschlossen)"

    auc_b_point = cluster_b["with_cluster"]["point_auc"]
    auc_b_ci_lo = cluster_b["with_cluster"]["ci_lo"]
    criteria_b = {
        "holm_significant": _holm_sig("b"),
        "ci_above_baseline": (auc_b_ci_lo is not None and auc_b_ci_lo > 0.5),
        "cluster_same_direction": bool(cluster_b["same_direction"]),
        "point_above_threshold": (auc_b_point is not None and auc_b_point >= 0.55),
    }
    verdict_b, verdict_b_reason = _verdict(criteria_b)
    if pct_excluded > 20.0:
        verdict_b_reason += f" (Einschränkung: {pct_excluded:.1f}% der Kandidaten ohne verwertbaren Score ausgeschlossen)"

    return {
        "schema_v": SCHEMA_V,
        "family": "ki_score",
        "freeze_date": freeze_date_str,
        "evaluated_at": now.isoformat(),
        "n_candidates": n_candidates,
        "n_pop": n_pop,
        "n_excluded": len(excluded_rows),
        "pct_excluded": pct_excluded,
        "tests": {
            "a": {
                "test_id": "ki_score_a", "n": n_pop,
                "n_excluded": len(excluded_rows), "pct_excluded": pct_excluded,
                "statistic": cluster_a["with_cluster"],
                "cluster_double_run": {
                    "without_cluster_point_auc": cluster_a["without_cluster"]["point_auc"],
                    "n_cluster_followups_removed": cluster_a["n_cluster_followups_removed"],
                    "same_direction": cluster_a["same_direction"],
                },
                "p_raw": p_a, "holm_reject": _holm_reject(holm, "a"),
                "criteria": criteria_a, "verdict": verdict_a, "verdict_reason": verdict_a_reason,
            },
            "b": {
                "test_id": "ki_score_b", "n": n_pop,
                "n_excluded": len(excluded_rows), "pct_excluded": pct_excluded,
                "statistic": cluster_b["with_cluster"],
                "cluster_double_run": {
                    "without_cluster_point_auc": cluster_b["without_cluster"]["point_auc"],
                    "n_cluster_followups_removed": cluster_b["n_cluster_followups_removed"],
                    "same_direction": cluster_b["same_direction"],
                },
                "p_raw": p_b, "holm_reject": _holm_reject(holm, "b"),
                "criteria": criteria_b, "verdict": verdict_b, "verdict_reason": verdict_b_reason,
            },
        },
        "holm": holm,
    }


# ── Exit-B.1-Familie (§4, Tests a/b — Holm k=2, EIGENE Mechanik) ───────
# ANDERS als Setup-Edge/KI-Score: Zielgröße ist eine gepaarte pp-Mittel-
# wert-Differenz (Δ), KEIN AUC. Population hat KEINEN Datums-Filter
# (Definition A: provenance=forward ∧ score≥70, siehe
# hc._is_exit_b1_population_row — Single-Source-of-Truth mit dem
# §4-Zähler). Verfahren exakt nach SESSION_HANDOVER.md §4 +
# "Protokolleintrag 31.10.2026" (drei Lücken im Ur-Text geklärt, VOR
# Erreichen von n=250, bei n=242, Ergebnis unbekannt):
#   - Δ = Mittel(return_Nd) − Mittel(return_10d), gepaarter Bootstrap
#     (``paired_bootstrap_mean_delta``), N=2000, Seed=42.
#   - Holm-p-Input kommt aus ``mann_whitney_u_auc`` auf den beiden
#     UNABHÄNGIGEN Original-Arrays (return_Nd, return_10d) — NICHT aus
#     dem Bootstrap selbst (das Bootstrap-CI ist ein zweites, vom Holm-p
#     unabhängiges Erfolgskriterium).
#   - Kriterium (c) Regime-Split: Vorzeichen von Δ je ``market_regime``-
#     Bucket (bull/bear/neutral) mit n≥10; "plausibel" = kein
#     ausreichend besetzter Bucket mit Gegen-Vorzeichen. Bucket < 10 =
#     "nicht_pruefbar" (zählt NICHT als erfüllt). Fehlt jeder
#     ausreichend besetzte Bucket → Gesamtstatus "nicht_pruefbar";
#     widerspricht mind. ein ausreichend besetzter Bucket → "widerlegt".
#   - Zusatz: Wilcoxon-Signed-Rank auf denselben Paaren läuft IMMER mit,
#     ist aber REIN EXPLORATIV — beeinflusst Verdikt/Holm nicht.


def _exit_b1_regime_check(rows: Sequence[dict], field_a: str, field_b: str,
                          overall_sign: int) -> tuple[str, dict]:
    """Kriterium (c) — Regime-Split-Plausibilität (Protokolleintrag
    31.10.2026, Punkt 2). Returnt ``(status, detail)``:

      ``status`` ∈ {"plausibel", "widerlegt", "nicht_pruefbar"}.
      ``detail`` = ``{regime: {n, mean_delta?, status}}`` pro Bucket.

    Ein Bucket zählt nur mit ``n >= 10`` zum Gesamturteil; kleinere
    Buckets werden als ``"nicht_pruefbar"`` markiert, fließen aber NICHT
    als Widerspruch ein (zu wenig Daten ≠ Gegenbeleg). ``overall_sign``
    ist das Vorzeichen des Gesamt-Δ (1/-1/0) aus der Hauptpopulation."""
    buckets: dict[str, list[tuple[float, float]]] = {"bull": [], "bear": [], "neutral": []}
    for r in rows:
        reg = r.get("market_regime")
        va, vb = r.get(field_a), r.get(field_b)
        if reg in buckets and _is_finite_number(va) and _is_finite_number(vb):
            buckets[reg].append((va, vb))

    detail: dict[str, dict] = {}
    any_checked = False
    any_contradiction = False
    for reg, pairs in buckets.items():
        n = len(pairs)
        if n < 10:
            detail[reg] = {"n": n, "status": "nicht_pruefbar"}
            continue
        mean_delta = sum(p[0] for p in pairs) / n - sum(p[1] for p in pairs) / n
        bucket_sign = 0 if mean_delta == 0 else (1 if mean_delta > 0 else -1)
        agrees = (overall_sign == 0) or (bucket_sign == overall_sign) or bucket_sign == 0
        detail[reg] = {"n": n, "mean_delta": mean_delta,
                      "status": "plausibel" if agrees else "widerlegt"}
        any_checked = True
        if not agrees:
            any_contradiction = True

    if any_contradiction:
        return "widerlegt", detail
    if not any_checked:
        return "nicht_pruefbar", detail
    return "plausibel", detail


def _verdict_exit_b1_test(holm_sig: bool, ci_above_zero: bool,
                          regime_status: str) -> tuple[str, str]:
    """Verdikt-Logik für Exit-B.1 (Protokolleintrag 31.10.2026) — DREI
    mögliche Ausgänge (anders als die generische ``_verdict()`` mit nur
    zwei): "Beleg" / "bedingt" / "Unklar". "bedingt" ist NEU und nur für
    den Fall reserviert, dass (a)+(b) erfüllt sind, aber (c) wegen zu
    dünner Regime-Buckets nicht prüfbar war — ausdrücklich NICHT dasselbe
    wie "erfüllt", aber auch kein "Unklar" (das bleibt für echte
    Kriterien-Fails bzw. einen tatsächlichen Regime-Widerspruch
    reserviert — Freeze-Grenze "nie keine Edge" bleibt in allen drei
    Fällen gewahrt: "bedingt" und "Unklar" sind beide KEINE
    Edge-Widerlegung)."""
    if not (holm_sig and ci_above_zero):
        failed = []
        if not holm_sig:
            failed.append("holm_significant")
        if not ci_above_zero:
            failed.append("ci_above_zero")
        return ("Unklar",
                f"Kriterien nicht erfüllt: {', '.join(failed)} — "
                f"keine Edge-Widerlegung (Freeze-Grenze)")
    if regime_status == "plausibel":
        return "Beleg", "alle drei Erfolgskriterien erfüllt (inkl. Regime-Split plausibel)"
    if regime_status == "nicht_pruefbar":
        return ("bedingt",
                "Holm-signifikant + Bootstrap-CI > 0 erfüllt, Regime-Split "
                "NICHT prüfbar (zu wenig Daten je Bucket) — zählt laut "
                "Protokolleintrag 31.10.2026 NICHT als erfüllt, aber auch "
                "nicht als Widerspruch")
    return ("Unklar",
            "Holm-signifikant + Bootstrap-CI > 0 erfüllt, aber Regime-Split "
            "WIDERLEGT (Gegen-Vorzeichen in einem ausreichend besetzten "
            "Bucket) — keine Edge-Widerlegung (Freeze-Grenze)")


def evaluate_exit_b1_family(export_rows: Sequence[dict], *,
                            now: datetime | None = None) -> dict:
    """Komplette, deterministische Auswertung für §4-Exit-B.1: Test a
    (Δ(5d−10d)), Test b (Δ(3d−10d)). Reine Funktion — ``export_rows``
    sind bereits eingelesene, UNGEFILTERTE Export-Zeilen. Eigene Holm-
    Familie k=2 (NICHT mit Setup-Edge/KI-Score zusammengelegt — exakt
    wie bei den beiden bestehenden Familien gehandhabt)."""
    now = now or datetime.now(timezone.utc)

    pop_rows = _dedup_rows([r for r in export_rows if hc._is_exit_b1_population_row(r)])
    n_pop = len(pop_rows)

    def _build_test(field_a: str, label: str) -> dict:
        usable = [r for r in pop_rows
                 if _is_finite_number(r.get(field_a)) and _is_finite_number(r.get("return_10d"))]
        n_excluded = n_pop - len(usable)
        pct_excluded = (n_excluded / n_pop * 100.0) if n_pop else 0.0
        vals_a = [r[field_a] for r in usable]
        vals_b = [r["return_10d"] for r in usable]

        delta_stat = paired_bootstrap_mean_delta(vals_a, vals_b)
        mw = mann_whitney_u_auc(vals_a, vals_b)
        wilcoxon = wilcoxon_signed_rank_paired(vals_a, vals_b)

        point_delta = delta_stat["point_delta"]
        overall_sign = 0
        if point_delta is not None:
            overall_sign = 1 if point_delta > 0 else (-1 if point_delta < 0 else 0)
        regime_status, regime_detail = _exit_b1_regime_check(
            usable, field_a, "return_10d", overall_sign)

        # Fehlende Werte / degenerierte Population (Schritt-1-Vorgabe "Umgang
        # mit fehlenden Werten"): mann_whitney_u_auc liefert p_two_sided=None
        # bei leerer/entarteter Stichprobe (z. B. alle Werte identisch oder
        # eine Seite leer) — multiple_testing_correction verlangt aber einen
        # float. Fail-safe-Clamp auf p=1.0 ("nie signifikant") statt Crash —
        # konsistent mit der Freeze-Grenze "nie fälschlich Beleg bei
        # fehlenden Daten". Dieser Fall ist bei n≥250 Gesamt-Auslöser nur bei
        # einem extrem hohen Ausschluss-Anteil überhaupt erreichbar.
        p_raw = mw["p_two_sided"] if mw["p_two_sided"] is not None else 1.0
        return {
            "label": label, "n": len(usable), "n_excluded": n_excluded,
            "pct_excluded": pct_excluded,
            "delta_statistic": delta_stat,
            "mann_whitney_holm_input": mw,
            "wilcoxon_exploratory": wilcoxon,
            "regime_split": {"status": regime_status, "detail": regime_detail},
            "p_raw": p_raw,
        }

    test_a = _build_test("return_5d", "Δ(5d−10d)")
    test_b = _build_test("return_3d", "Δ(3d−10d)")

    holm = multiple_testing_correction(
        [test_a["p_raw"], test_b["p_raw"]], labels=["a", "b"])

    def _holm_sig(label: str) -> bool:
        for row in holm.get("results", []):
            if row.get("label") == label:
                return bool(row.get("holm_reject"))
        return False

    def _finish(test: dict, label: str) -> dict:
        ci_lo = test["delta_statistic"]["ci_lo"]
        holm_sig = _holm_sig(label)
        ci_above_zero = (ci_lo is not None and ci_lo > 0.0)
        verdict, reason = _verdict_exit_b1_test(
            holm_sig, ci_above_zero, test["regime_split"]["status"])
        out = dict(test)
        out["test_id"] = f"exit_b1_{label}"
        out["criteria"] = {
            "holm_significant": holm_sig,
            "ci_above_zero": ci_above_zero,
            "regime_split_status": test["regime_split"]["status"],
        }
        out["holm_reject"] = holm_sig
        out["verdict"] = verdict
        out["verdict_reason"] = reason
        return out

    final_a = _finish(test_a, "a")
    final_b = _finish(test_b, "b")

    return {
        "schema_v": SCHEMA_V,
        "family": "exit_b1",
        "freeze_date": "datumsfrei (Auslöser n>=250)",
        "protocol_ref": ("SESSION_HANDOVER.md §4 (Exit-B.1-Re-Test), "
                        "eingefroren 05.08.2026, Protokolleintrag "
                        "31.10.2026 (Δ-/Regime-/Seed-Mechanik geklärt)"),
        "evaluated_at": now.isoformat(),
        "n_pop": n_pop,
        "tests": {"a": final_a, "b": final_b},
        "holm": holm,
    }


def _holm_reject(holm: dict, label: str) -> bool | None:
    for row in holm.get("results", []):
        if row.get("label") == label:
            return bool(row.get("holm_reject"))
    return None


# ── Orchestrierung (File-I/O, Sperre, Trigger-Check) ───────────────────
def _git_commit_hash() -> str | None:
    """Best-effort Commit-Hash für die Audit-Spur — fail-soft (``None``
    bei jedem Fehler, z. B. kein Git-Repo im CI-Checkout). Priorität:
    ``GITHUB_SHA``-Env (Workflow-Kontext, kein Subprozess nötig), sonst
    ``git rev-parse HEAD``."""
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # pragma: no cover — Subprozess-Fehler aller Art
        pass
    return None


def _data_hash(rows: Sequence[dict]) -> str:
    """Deterministischer Hash über die ``(ticker, date)``-Schlüssel der
    tatsächlich verwendeten Zeilen — Audit-Spur, KEIN Inhalt (keine
    Returns im Hash-Input nötig, Schlüssel identifizieren die Zeilen-
    Menge eindeutig gegen die append-only Export-Datei)."""
    keys = sorted(f"{r.get('ticker')}|{r.get('date')}" for r in rows)
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()


def _flatten_family_result(family_result: dict) -> list[dict]:
    """Baut die eval_results.jsonl-Zeilen (eine pro Test-ID) aus dem
    Rückgabe-Dict von ``evaluate_*_family``. Meta-Felder
    (``script_commit_hash``, Bootstrap-Parameter) werden hier ergänzt."""
    commit_hash = _git_commit_hash()
    out = []
    for test_key, test in family_result["tests"].items():
        row = {
            "schema_v": SCHEMA_V,
            "test_id": test["test_id"],
            "family": family_result["family"],
            "freeze_date": family_result["freeze_date"],
            "evaluated_at": family_result["evaluated_at"],
            "n": test["n"],
            "n_excluded": test["n_excluded"],
            "pct_excluded": test["pct_excluded"],
            "p_raw": test["p_raw"],
            "holm_reject": test["holm_reject"],
            "criteria": test["criteria"],
            "verdict": test["verdict"],
            "verdict_reason": test["verdict_reason"],
            "bootstrap_seed": config.EVAL_BOOTSTRAP_SEED,
            "bootstrap_n": config.EVAL_BOOTSTRAP_N,
            "ci_method": f"95% zweiseitig, Perzentil {config.EVAL_BOOTSTRAP_CI_LO}/{config.EVAL_BOOTSTRAP_CI_HI}",
            "script_commit_hash": commit_hash,
        }
        if "protocol_ref" in family_result:
            row["protocol_ref"] = family_result["protocol_ref"]
        # Statistik-Felder je Test-Typ (AUC- vs. ΔAUC- vs. gepaarte-pp-Δ-
        # basiert) additiv.
        for k in ("statistic", "cluster_double_run", "auc_conviction_component",
                 "delta_statistic", "mann_whitney_holm_input",
                 "wilcoxon_exploratory", "regime_split"):
            if k in test:
                row[k] = test[k]
        out.append(row)
    return out


def _load_existing_test_ids(results_path) -> set[str]:
    """Liest die bereits vorhandenen ``test_id``-Werte aus
    ``eval_results.jsonl`` — das IST die Sperre (kein separates Lock-Feld
    nötig: ein Test-ID mit Zeile dort wurde bereits ausgewertet, Punkt).
    Fail-soft: fehlende/kaputte Datei -> leeres Set (kein Lock aktiv)."""
    ids: set[str] = set()
    try:
        with open(results_path, "r", encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                    if isinstance(obj, dict) and obj.get("test_id"):
                        ids.add(obj["test_id"])
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
    except FileNotFoundError:
        pass
    return ids


def summarize_existing_verdict(results_path, test_ids: set[str]) -> str | None:
    """Liest die bereits persistierten Verdikte für ``test_ids`` aus
    ``eval_results.jsonl`` (für die Digest-Zeile einer Familie, die in
    einem FRÜHEREN Lauf schon ausgewertet wurde — der heutige Lauf triggert
    dann nichts Neues mehr, die Zeile soll aber weiterhin den Verdikt
    zeigen, nicht auf das Vor-Auslöser-Format zurückfallen). Fail-soft:
    ``None`` wenn keine passenden Zeilen gefunden werden (sollte bei einem
    tatsächlich gesetzten Lock nicht vorkommen, ist aber kein Crash-Grund)."""
    found: dict[str, str] = {}
    try:
        with open(results_path, "r", encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                if isinstance(obj, dict) and obj.get("test_id") in test_ids:
                    found[obj["test_id"]] = obj.get("verdict", "?")
    except FileNotFoundError:
        return None
    if not found:
        return None
    return "; ".join(f"{tid}: {v}" for tid, v in sorted(found.items()))


def _append_results(results_path, rows: list[dict]) -> None:
    """Append-only, atomarer Write (tmp + os.replace, Haus-Muster
    ``matured_export.py``/``si_position_history``)."""
    lines = []
    try:
        with open(results_path, "r", encoding="utf-8") as fh:
            lines = [ln.rstrip("\n") for ln in fh if ln.strip()]
    except FileNotFoundError:
        pass
    lines.extend(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows)
    tmp = f"{results_path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, results_path)


def run_due_evaluations(*, export_path=None, results_path=None,
                        now: datetime | None = None) -> dict:
    """Prüft ALLE DREI Test-Familien (Setup-Edge/Conviction, KI-Score,
    Exit-B.1) auf ihren Auslöser, wertet eine Familie GENAU EINMAL aus,
    sobald `n>=250` erreicht ist UND noch keine Zeile für ihre Test-IDs
    in ``eval_results.jsonl`` existiert (Sperre). Hängt neue Zeilen an,
    returnt ``{"new_rows": [...], "just_triggered": [family,...],
    "setup_edge_status": (n, target), "ki_score_status": (n, target),
    "exit_b1_status": (n, target)}``. Exit-B.1 nutzt
    ``hc.retest_counter_value()`` als Auslöser-Quelle (Single-Source-of-
    Truth mit dem täglichen §4-Zähler) statt einer eigenen
    Populations-Zähl-Funktion wie die anderen zwei Familien.

    KEIN Eingriff in score()/Top-10/Filter/Push/Conviction. Fail-soft nach
    außen NICHT nötig hier (der Caller in health_check_digest.py wrappt
    bereits try/except) — aber jede interne Degenerierung (leere Datei,
    kaputte Zeile) wird von den Bausteinen selbst abgefangen."""
    export_path = export_path or (_ROOT / config.MATURED_EXPORT_FILE)
    results_path = results_path or (_ROOT / config.EVAL_RESULTS_FILE)
    now = now or datetime.now(timezone.utc)

    result = hc._read_matured_export_rows(str(export_path))
    export_rows = result[1] if result is not None else []

    existing_ids = _load_existing_test_ids(str(results_path))
    new_rows: list[dict] = []
    just_triggered: list[dict] = []

    setup_edge_ids = {"setup_edge_a", "setup_edge_b", "setup_edge_conviction_c"}
    setup_pop = hc._count_setup_edge_freeze_population(str(export_path))
    setup_n = setup_pop[0] if setup_pop is not None else 0
    if (setup_n >= config.SETUP_EDGE_FREEZE_N_TARGET
            and not (setup_edge_ids & existing_ids)):
        family_result = evaluate_setup_edge_family(export_rows, now=now)
        rows = _flatten_family_result(family_result)
        new_rows.extend(rows)
        just_triggered.append({
            "family": "setup_edge_conviction",
            "label": "Setup-Edge/Conviction",
            "verdicts": {t["test_id"]: (t["verdict"], t["verdict_reason"])
                        for t in family_result["tests"].values()},
        })

    ki_ids = {"ki_score_a", "ki_score_b"}
    ki_pop = hc._count_ki_score_freeze_population(str(export_path))
    ki_n = ki_pop[0] if ki_pop is not None else 0
    if (ki_n >= config.KI_SCORE_FREEZE_N_TARGET and not (ki_ids & existing_ids)):
        family_result = evaluate_ki_score_family(export_rows, now=now)
        rows = _flatten_family_result(family_result)
        new_rows.extend(rows)
        just_triggered.append({
            "family": "ki_score",
            "label": "KI-Score",
            "verdicts": {t["test_id"]: (t["verdict"], t["verdict_reason"])
                        for t in family_result["tests"].values()},
        })

    # Exit-B.1 (§4) — datumsfrei, Auslöser n>=250 laut hc.retest_counter_value()
    # (Single-Source-of-Truth, identisch zum täglichen §4-Zähler). Eigene
    # Holm-Familie k=2 (siehe evaluate_exit_b1_family-Modul-Kommentar).
    exit_b1_ids = {"exit_b1_a", "exit_b1_b"}
    exit_b1_pop = hc.retest_counter_value(str(export_path))
    exit_b1_n = exit_b1_pop[0] if exit_b1_pop is not None else 0
    if (exit_b1_n >= hc._RETEST_N_TARGET and not (exit_b1_ids & existing_ids)):
        family_result = evaluate_exit_b1_family(export_rows, now=now)
        rows = _flatten_family_result(family_result)
        new_rows.extend(rows)
        just_triggered.append({
            "family": "exit_b1",
            "label": "Exit-B.1",
            "verdicts": {t["test_id"]: (t["verdict"], t["verdict_reason"])
                        for t in family_result["tests"].values()},
        })

    if new_rows:
        _append_results(str(results_path), new_rows)

    return {
        "new_rows": new_rows,
        "just_triggered": just_triggered,
        "setup_edge_status": (setup_n, config.SETUP_EDGE_FREEZE_N_TARGET),
        "ki_score_status": (ki_n, config.KI_SCORE_FREEZE_N_TARGET),
        "exit_b1_status": (exit_b1_n, hc._RETEST_N_TARGET),
        "setup_edge_locked": bool(setup_edge_ids & existing_ids) or any(
            j["family"] == "setup_edge_conviction" for j in just_triggered),
        "ki_score_locked": bool(ki_ids & existing_ids) or any(
            j["family"] == "ki_score" for j in just_triggered),
        "exit_b1_locked": bool(exit_b1_ids & existing_ids) or any(
            j["family"] == "exit_b1" for j in just_triggered),
    }
