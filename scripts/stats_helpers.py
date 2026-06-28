"""Statistik-Helfer (pure stdlib) für 30.06.-Auswertungs-Skripte.

Heute enthält: ``mann_whitney_u_auc`` — AUC (= Fläche unter ROC) via
Mann-Whitney-U-Statistik mit Tie-Korrektur und Normal-Approximation des
p-Werts. Vorbau für den Earliness-AUC-Re-Test am 30.06., wiederverwendbar
für künftige Hypothesen-Tests (Cluster-Purge-Doppellauf, Cap-Diagnose).

REIHENFOLGE-DISZIPLIN: Dieses Modul **liest nicht** ``backtest_history.json``
und keine andere Live-Datei. Die Funktion nimmt Listen direkt vom Caller
entgegen — wer auswertet, übergibt explizit. Keine Auto-Auswertung im
Daily-Run-Pfad, keine Imports in ``generate_report``/``ki_agent``/
``health_check`` (nur Konsumenten in ``scripts/``).

Pure stdlib (``math``, kein ``scipy``/``numpy``) — konsistent zu
``expectancy_diagnose.py``.
"""
from __future__ import annotations

import math
from typing import Sequence

__all__ = ["mann_whitney_u_auc"]


def _ranks_with_ties(values: list[float]) -> tuple[list[float], list[int]]:
    """Tie-gemittelte 1-basierte Ränge in Original-Reihenfolge + Liste der
    Tie-Gruppen-Größen (>1) für die Tie-Korrektur der U-Varianz.

    Beispiel: ``[1, 2, 2, 3]`` → Ränge ``[1.0, 2.5, 2.5, 4.0]``,
    Tie-Gruppen ``[2]``.
    """
    n = len(values)
    if n == 0:
        return [], []
    order = sorted(range(n), key=lambda i: values[i])
    ranks: list[float] = [0.0] * n
    tie_sizes: list[int] = []
    i = 0
    while i < n:
        j = i
        # Tie-Block erweitern, solange Werte gleich sind
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        # avg_rank = ((i+1) + (j+1)) / 2  (1-basiert)
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        group_size = j - i + 1
        if group_size > 1:
            tie_sizes.append(group_size)
        i = j + 1
    return ranks, tie_sizes


def _normal_cdf(z: float) -> float:
    """Φ(z) via ``math.erf`` (stdlib), beidseitig stetig."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def mann_whitney_u_auc(group_a: Sequence[float],
                       group_b: Sequence[float]) -> dict:
    """Mann-Whitney-U + AUC für zwei Gruppen (Pure stdlib, deterministisch).

    INTERPRETATION (wichtig — Richtung der AUC):
      ``AUC = P(A > B) + 0.5 * P(A == B)``. AUC = 1.0 → jeder Wert aus A
      ist größer als jeder aus B; AUC = 0.0 → umgekehrt; AUC = 0.5 →
      keine Trennung. Der Caller entscheidet, welche Gruppe „A" ist
      (z.B. „Gewinner" gegen „Verlierer" für Edge-Tests).

    Returnt Dict mit:
      ``n_a``, ``n_b``     — Gruppengrößen.
      ``u``                — U-Statistik für Gruppe A.
      ``auc``              — = ``u / (n_a * n_b)``.
      ``p_two_sided``      — p-Wert der Normal-Approximation der U-
                             Verteilung mit Tie-Korrektur und Stetigkeits-
                             korrektur (±0.5). ``None`` wenn n_a == 0 oder
                             n_b == 0 (AUC undefiniert), oder wenn die
                             tie-korrigierte Varianz auf 0 schrumpft
                             (alle Werte identisch).
      ``note``             — Optionaler Hinweis (z.B. „kleines n").

    CAVEATS:
      - Normal-Approximation gilt grob ab ``min(n_a, n_b) >= 5``. Bei
        kleineren Gruppen wird ``note`` gesetzt; ein exakter Test
        (Permutation/Generating Function) ist nicht implementiert.
      - Stetigkeitskorrektur ±0.5 vor der z-Transform gleicht den
        diskreten Charakter von U an die kontinuierliche Normal-
        Approximation an (zieht p in Richtung „weniger signifikant",
        leicht konservativ).
      - Bei n_a == 0 oder n_b == 0: AUC und p sind ``None``.
      - Bei vollständiger Indifferenz (alle Werte identisch) ist AUC
        per Konvention 0.5, p aber ``None`` (Varianz 0 → undefiniert).
    """
    a = list(group_a)
    b = list(group_b)
    n_a, n_b = len(a), len(b)

    if n_a == 0 or n_b == 0:
        return {"n_a": n_a, "n_b": n_b, "u": None, "auc": None,
                "p_two_sided": None,
                "note": "Mindestens eine Gruppe ist leer — AUC undefiniert."}

    combined = a + b
    ranks, tie_sizes = _ranks_with_ties(combined)

    # R_A = Summe der Ränge in Gruppe A (Indices 0..n_a-1 in combined).
    r_a = sum(ranks[:n_a])

    u_a = r_a - n_a * (n_a + 1) / 2.0
    auc = u_a / (n_a * n_b)

    # Varianz mit Tie-Korrektur (Standardformel):
    #   var_U = n_a*n_b/12 * ((N+1) - sum_t (t^3 - t) / (N*(N-1)))
    N = n_a + n_b
    if N <= 1:
        return {"n_a": n_a, "n_b": n_b, "u": u_a, "auc": auc,
                "p_two_sided": None,
                "note": "Gesamtgröße zu klein für Varianzschätzung."}

    tie_term = sum(t * t * t - t for t in tie_sizes)
    var_u = (n_a * n_b / 12.0) * (
        (N + 1) - tie_term / (N * (N - 1.0))
    )

    if var_u <= 0:
        # Tie-Korrektur kann die Varianz auf 0 ziehen, wenn alle Werte
        # identisch sind (ein einziger Tie-Block über N) — dann ist kein
        # p berechenbar; AUC bleibt 0.5 (vollständige Indifferenz).
        return {"n_a": n_a, "n_b": n_b, "u": u_a, "auc": auc,
                "p_two_sided": None,
                "note": "Alle Werte identisch — Varianz 0, p nicht "
                        "berechenbar."}

    mean_u = n_a * n_b / 2.0
    diff = abs(u_a - mean_u)
    # Stetigkeitskorrektur: ±0.5 vor z-Transform.
    diff_corrected = max(0.0, diff - 0.5)
    z = diff_corrected / math.sqrt(var_u)
    p_two_sided = 2.0 * (1.0 - _normal_cdf(z))
    # Floating-Point-Clamp gegen leicht negative/>1-Drift bei extremen z:
    p_two_sided = max(0.0, min(1.0, p_two_sided))

    note = None
    if min(n_a, n_b) < 5:
        note = (f"min(n_a, n_b) = {min(n_a, n_b)} < 5 — Normal-Approximation "
                "grob, exakter Test nicht implementiert.")

    return {"n_a": n_a, "n_b": n_b, "u": u_a, "auc": auc,
            "p_two_sided": p_two_sided, "note": note}
