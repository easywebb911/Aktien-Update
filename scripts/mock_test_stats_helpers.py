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

from stats_helpers import mann_whitney_u_auc  # noqa: E402


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

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        sys.exit(1)
    print(f"{12 + 2} Tests bestanden (inkl. 2× -b-Suffix).")


if __name__ == "__main__":
    main()
