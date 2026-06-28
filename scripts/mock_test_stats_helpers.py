"""Mock-Tests für ``scripts/stats_helpers.py`` (Mann-Whitney-U + AUC).

FIXTURE-ONLY: KEIN Kontakt mit ``backtest_history.json`` oder anderen
Live-Dateien (Reihenfolge-Disziplin — erst sammeln → auswerten am 30.06.,
nicht in diesem PR vorziehen).

Verifiziert:
- AUC = 1.0 bei perfekter Trennung A > B; AUC = 0.0 bei A < B
- AUC = 0.5 bei identischen Listen
- Hand-nachrechenbarer Fall ``[1,2,3] vs [2,3,4]`` → AUC = 2/9
- Edge-Cases: leere Gruppe (AUC None), alle Werte identisch (p None)
- Tie-Korrektur greift: p-Wert stimmt mit handgerechneter Tie-korrigierter
  Varianz (5.25 ohne Korrektur → 4.95 mit Korrektur) überein
- Kleines n setzt Approx-Caveat-Note
- Determinismus
"""
from __future__ import annotations

import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from stats_helpers import (  # noqa: E402
    mann_whitney_u_auc,
    multiple_testing_correction,
)


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def main():
    # ── Trennkraft-Extreme ────────────────────────────────────────────────
    r = mann_whitney_u_auc([1, 2, 3], [10, 11, 12])
    _check("01 perfekt A<B → AUC=0.0",
           r["auc"] == 0.0,
           f"got AUC={r['auc']}, p={r['p_two_sided']}")

    r = mann_whitney_u_auc([10, 11, 12], [1, 2, 3])
    _check("02 perfekt A>B → AUC=1.0",
           r["auc"] == 1.0,
           f"got AUC={r['auc']}")

    r = mann_whitney_u_auc([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    _check("03 identische Listen → AUC=0.5",
           r["auc"] == 0.5,
           f"got AUC={r['auc']}")

    # ── Hand-nachrechenbarer Fall ─────────────────────────────────────────
    # Pairs (xi, yj) für A=[1,2,3], B=[2,3,4]:
    # (1,2)0  (1,3)0  (1,4)0  (2,2)0.5  (2,3)0  (2,4)0
    # (3,2)1  (3,3)0.5  (3,4)0
    # → Sum = 2.0 → AUC = 2/9
    r = mann_whitney_u_auc([1, 2, 3], [2, 3, 4])
    expected_auc = 2.0 / 9.0
    _check("04 [1,2,3] vs [2,3,4] → AUC = 2/9",
           abs(r["auc"] - expected_auc) < 1e-12,
           f"got AUC={r['auc']:.6f}, expected {expected_auc:.6f}, "
           f"U={r['u']}, p={r['p_two_sided']:.4f}")

    # U-Statistik check: R_A = 1 + 2.5 + 4.5 = 8.0, U = 8 - 3*4/2 = 2.0
    _check("04b U-Statistik = 2.0 (R_A=8, U=R_A-n_a(n_a+1)/2)",
           r["u"] == 2.0, f"got U={r['u']}")

    # ── Edge-Cases ────────────────────────────────────────────────────────
    r = mann_whitney_u_auc([], [1, 2, 3])
    _check("05 leere Gruppe A → AUC=None, p=None",
           r["auc"] is None and r["p_two_sided"] is None
           and r["note"] is not None,
           f"note={r['note']!r}")

    r = mann_whitney_u_auc([1, 2, 3], [])
    _check("06 leere Gruppe B → AUC=None",
           r["auc"] is None and r["p_two_sided"] is None)

    r = mann_whitney_u_auc([3, 3, 3], [3, 3, 3])
    _check("07 alle Werte identisch → AUC=0.5, p=None (Varianz 0)",
           r["auc"] == 0.5 and r["p_two_sided"] is None
           and r["note"] is not None,
           f"AUC={r['auc']}, p={r['p_two_sided']}, note={r['note']!r}")

    r = mann_whitney_u_auc([1], [2])
    _check("08 n=1 je Seite → Note gesetzt (Caveat kleines n)",
           r["note"] is not None and "min" in (r["note"] or "").lower(),
           f"note={r['note']!r}")

    # ── Tie-Korrektur greift (Sanity-Test gegen Hand-Rechnung) ───────────
    # A=[1,2,3], B=[2,3,4] hat 2 Tie-Gruppen Größe 2 (Wert 2 und Wert 3).
    # N=6, n_a=n_b=3.
    # Ohne Tie-Korrektur: var = 3*3*(6+1)/12 = 5.25
    # Mit Tie-Korrektur:
    #   tie_term = (8-2) + (8-2) = 12
    #   var = (9/12) * (7 - 12/(6*5)) = 0.75 * 6.6 = 4.95
    # Erwarteter p (Stetigkeitskorrektur ±0.5):
    #   z = (|2.0 - 4.5| - 0.5) / sqrt(4.95) = 2.0 / 2.22486 = 0.89889
    #   p = 2 * (1 - Φ(0.89889))
    r = mann_whitney_u_auc([1, 2, 3], [2, 3, 4])
    var_with_tie = 4.95
    z_exp = (abs(2.0 - 4.5) - 0.5) / math.sqrt(var_with_tie)
    p_exp = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(z_exp / math.sqrt(2.0))))
    _check("09 Tie-Korrektur: p stimmt mit handgerechneter Tie-Varianz (4.95)",
           abs(r["p_two_sided"] - p_exp) < 1e-9,
           f"got p={r['p_two_sided']:.9f}, expected {p_exp:.9f}")

    # Gegenprobe: Ohne Tie-Korrektur (var=5.25) wäre p ANDERS — so können
    # wir belegen, dass die Korrektur wirklich greift, nicht nur zufällig
    # dasselbe Ergebnis liefert.
    z_no_tie = (abs(2.0 - 4.5) - 0.5) / math.sqrt(5.25)
    p_no_tie = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(z_no_tie / math.sqrt(2.0))))
    _check("09b Gegenprobe: p OHNE Tie-Korrektur (5.25) wäre messbar anders",
           abs(p_no_tie - p_exp) > 1e-3,
           f"p_no_tie={p_no_tie:.6f}, p_with_tie={p_exp:.6f}, "
           f"|Δ|={abs(p_no_tie - p_exp):.6f}")

    # ── Trennkraft + p-Wert konsistent ───────────────────────────────────
    r = mann_whitney_u_auc([1, 2, 3, 4, 5], [100, 200, 300, 400, 500])
    _check("10 perfekte Trennung n=5: AUC=0, p < 0.05 (Stetigkeitskorrektur)",
           r["auc"] == 0.0 and r["p_two_sided"] is not None
           and r["p_two_sided"] < 0.05,
           f"AUC={r['auc']}, p={r['p_two_sided']:.4f}")

    # ── Determinismus ────────────────────────────────────────────────────
    r1 = mann_whitney_u_auc([1, 2, 3], [2, 3, 4])
    r2 = mann_whitney_u_auc([1, 2, 3], [2, 3, 4])
    _check("11 Determinismus: gleicher Input → gleicher Output", r1 == r2)

    # ── Schema-Stabilität ────────────────────────────────────────────────
    keys = {"n_a", "n_b", "u", "auc", "p_two_sided", "note"}
    r = mann_whitney_u_auc([1, 2, 3], [4, 5, 6])
    _check("12 Return-Schema stabil (6 Keys)",
           set(r.keys()) == keys,
           f"got keys={set(r.keys())}")

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  multiple_testing_correction — Bonferroni + Holm (step-down)     ║
    # ╚══════════════════════════════════════════════════════════════════╝

    # ── Lehrbuch-Fall, handgerechnet ──────────────────────────────────────
    # p=[0.01, 0.02, 0.03, 0.04], α=0.05, k=4
    # Bonferroni-Schwelle = 0.05/4 = 0.0125
    #   p=0.01 < 0.0125 → reject     (alle anderen p > 0.0125 → fail)
    # Holm step-down (input bereits aufsteigend):
    #   i=1: 0.01 vs 0.05/4 = 0.0125 → reject
    #   i=2: 0.02 vs 0.05/3 ≈ 0.0167 → 0.02 > 0.0167 → STOP, fail
    #   i=3, i=4: fail (step-down)
    r = multiple_testing_correction([0.01, 0.02, 0.03, 0.04], alpha=0.05)
    _check("13 Bonferroni-Schwelle = α/k (handgerechnet 0.05/4)",
           r["bonferroni_threshold"] == 0.05 / 4,
           f"got {r['bonferroni_threshold']}")
    bonf = [x["bonferroni_reject"] for x in r["results"]]
    _check("14 Bonferroni-Urteile Lehrbuch-Fall = [T,F,F,F]",
           bonf == [True, False, False, False], f"got {bonf}")
    holm = [x["holm_reject"] for x in r["results"]]
    _check("15 Holm-Urteile Lehrbuch-Fall = [T,F,F,F] (step-down nach i=2)",
           holm == [True, False, False, False], f"got {holm}")
    _check("15b n_reject_bonf=1, n_reject_holm=1 (für diesen Fall identisch)",
           r["n_reject_bonf"] == 1 and r["n_reject_holm"] == 1)

    # ── Holm uniformly mächtiger als Bonferroni ──────────────────────────
    # p=[0.01, 0.04], α=0.05, k=2:
    #   Bonferroni-Schwelle 0.025 → nur p=0.01 reject.
    #   Holm: i=1: 0.01 vs 0.025 → reject
    #         i=2: 0.04 vs 0.05  → reject (kein Stopp, 0.04 < 0.05)
    # ⇒ Bonferroni 1 reject, Holm 2 rejects — strikt mehr.
    r = multiple_testing_correction([0.01, 0.04], alpha=0.05)
    bonf = [x["bonferroni_reject"] for x in r["results"]]
    holm = [x["holm_reject"] for x in r["results"]]
    _check("16 Holm > Bonferroni (Mächtigkeitsbeleg): Bonf=[T,F], Holm=[T,T]",
           bonf == [True, False] and holm == [True, True],
           f"bonf={bonf}, holm={holm}")
    _check("16b n_reject: bonf=1, holm=2 (strikte Halbordnung)",
           r["n_reject_bonf"] == 1 and r["n_reject_holm"] == 2)

    # ── Step-down-Stopp greift gegen isoliert-passenden p ────────────────
    # p=[0.01, 0.04, 0.045], α=0.05, k=3 (input sortiert):
    #   i=1: 0.01 vs 0.05/3 ≈ 0.0167 → reject
    #   i=2: 0.04 vs 0.05/2 = 0.025  → 0.04 > 0.025 → STOP, fail
    #   i=3: 0.045 vs 0.05/1 = 0.05 — ISOLIERT würde reject (0.045 < 0.05),
    #        ABER step-down hat gestoppt → fail
    # ⇒ Holm = [T, F, F]. Eine Bug-Variante OHNE step-down gäbe [T, F, T]
    #   → dieser Fall fängt das.
    r = multiple_testing_correction([0.01, 0.04, 0.045], alpha=0.05)
    holm = [x["holm_reject"] for x in r["results"]]
    _check("17 Step-down stoppt nachfolgende auch wenn isoliert <α "
           "(p=0.045 vs threshold 0.05 wird trotz < α NICHT rejected)",
           holm == [True, False, False],
           f"erwartet [T,F,F], got {holm}")

    # ── Label-Rückordnung: unsortierter Input ────────────────────────────
    # p=[0.04, 0.01, 0.06], α=0.05, k=3
    # Sorted: [(0.01,idx=1), (0.04,idx=0), (0.06,idx=2)]
    #   i=1: 0.01 vs 0.0167 → reject (orig_idx=1)
    #   i=2: 0.04 vs 0.025  → STOP, fail (orig_idx=0)
    #   i=3: fail            (orig_idx=2)
    # ⇒ Holm in ORIGINAL-Reihenfolge: [fail, reject, fail]
    # Bug-Variante (sorted-Order zurück) würde [reject, fail, fail] geben
    #   → falsche Zuordnung zu Original-Indices → dieser Fall fängt das.
    r = multiple_testing_correction([0.04, 0.01, 0.06], alpha=0.05)
    holm = [x["holm_reject"] for x in r["results"]]
    bonf = [x["bonferroni_reject"] for x in r["results"]]
    _check("18 Label-Rückordnung Holm (unsortiert): [F,T,F] in ORIGINAL-Order",
           holm == [False, True, False],
           f"erwartet [F,T,F], got {holm}")
    _check("18b Bonferroni-Urteile in Original-Reihenfolge (Sanity)",
           bonf == [False, True, False], f"got {bonf}")
    # Ps stimmen mit Original-Indices überein (kein Reorder im Output):
    ps_out = [x["p"] for x in r["results"]]
    _check("18c Output-Reihenfolge der p-Werte = Input-Reihenfolge",
           ps_out == [0.04, 0.01, 0.06])

    # ── Labels-Parameter wird mitgeführt + Cross-Lookup ──────────────────
    r = multiple_testing_correction([0.04, 0.01, 0.06],
                                    labels=["AUC_setup", "AUC_dtc", "AUC_rvol"],
                                    alpha=0.05)
    labs_out = [x["label"] for x in r["results"]]
    _check("19 Labels in Original-Reihenfolge erhalten",
           labs_out == ["AUC_setup", "AUC_dtc", "AUC_rvol"])
    dtc_entry = next(x for x in r["results"] if x["label"] == "AUC_dtc")
    _check("19b Cross-Lookup AUC_dtc: p=0.01, holm=T, bonf=T (kein Mismatch)",
           dtc_entry["p"] == 0.01
           and dtc_entry["holm_reject"] is True
           and dtc_entry["bonferroni_reject"] is True)

    # ── Edge-Cases ────────────────────────────────────────────────────────
    r = multiple_testing_correction([0.04], alpha=0.05)
    _check("20 k=1: Bonferroni-Schwelle = α (Korrektur entartet)",
           r["bonferroni_threshold"] == 0.05)
    _check("20b k=1: 0.04 < 0.05 → beide reject",
           r["results"][0]["bonferroni_reject"] is True
           and r["results"][0]["holm_reject"] is True)

    r = multiple_testing_correction([], alpha=0.05)
    _check("21 leere Liste → k=0, results=[], n_reject=0",
           r["k"] == 0 and r["results"] == []
           and r["n_reject_bonf"] == 0 and r["n_reject_holm"] == 0)

    # Ties (identische p-Werte): sortiert stable → Original-Reihenfolge.
    # p=[0.01, 0.01, 0.01], α=0.05, k=3
    # Bonferroni-Schwelle 0.0167. Alle 0.01 < 0.0167 → alle reject.
    # Holm: i=1: 0.01 vs 0.0167 → reject; i=2: 0.01 vs 0.025 → reject;
    #       i=3: 0.01 vs 0.05 → reject. Alle reject.
    r = multiple_testing_correction([0.01, 0.01, 0.01], alpha=0.05)
    bonf = [x["bonferroni_reject"] for x in r["results"]]
    holm = [x["holm_reject"] for x in r["results"]]
    _check("22 Ties: alle 3 identischen p=0.01 → alle reject (beide Verfahren)",
           bonf == [True, True, True] and holm == [True, True, True])

    # ── Struktur-Invariante: Holm-Reject-Set ⊇ Bonferroni-Reject-Set ─────
    # Wenn Bonferroni rejected, muss Holm AUCH rejecten (uniformly mächtiger).
    # Mehrere Fixtures durchgehen.
    fixtures = [
        ([0.001, 0.01, 0.02, 0.03, 0.04, 0.06, 0.08], 0.05),
        ([0.005, 0.015], 0.05),
        ([0.001, 0.99], 0.05),
        ([0.04, 0.01, 0.06, 0.005, 0.5], 0.05),
    ]
    invariant_ok = True
    for pvs, alpha in fixtures:
        rr = multiple_testing_correction(pvs, alpha=alpha)
        for entry in rr["results"]:
            if entry["bonferroni_reject"] and not entry["holm_reject"]:
                invariant_ok = False
                break
    _check("23 Invariante: Holm-Reject ⊇ Bonferroni-Reject über 4 Fixtures",
           invariant_ok)

    # ── Labels-Mismatch wirft ValueError ─────────────────────────────────
    try:
        multiple_testing_correction([0.01, 0.02], labels=["nur_einer"])
        ve_raised = False
    except ValueError:
        ve_raised = True
    _check("24 labels-Length-Mismatch → ValueError", ve_raised)

    # ── Determinismus ────────────────────────────────────────────────────
    r1 = multiple_testing_correction([0.04, 0.01, 0.06], alpha=0.05)
    r2 = multiple_testing_correction([0.04, 0.01, 0.06], alpha=0.05)
    _check("25 Determinismus: gleicher Input → gleicher Output", r1 == r2)

    # ── Return-Schema-Stabilität ─────────────────────────────────────────
    r = multiple_testing_correction([0.01, 0.04], alpha=0.05)
    top_keys = {"k", "alpha", "bonferroni_threshold", "results",
                "n_reject_bonf", "n_reject_holm"}
    entry_keys = {"label", "p", "bonferroni_reject", "holm_reject"}
    _check("26 Top-Level Return-Schema (6 Keys)",
           set(r.keys()) == top_keys, f"got {set(r.keys())}")
    _check("26b Pro-Test-Dict-Schema (4 Keys)",
           set(r["results"][0].keys()) == entry_keys,
           f"got {set(r['results'][0].keys())}")

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        sys.exit(1)
    print("Alle Mann-Whitney-/AUC- + Multiple-Testing-Tests bestanden.")


if __name__ == "__main__":
    main()
