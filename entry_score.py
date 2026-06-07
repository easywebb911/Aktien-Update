#!/usr/bin/env python3
"""Entry-Timing-Score (Shadow-Mode) — reine Normalisierungs- + Aggregations-
Logik, KEIN Push / KEINE Anzeige / KEIN Score-/Filter-Effekt.

Bewusst eigenes, abhängigkeits-freies Modul (nur stdlib) — analog
``push_history.py`` / ``score_inflation_log.py``. So ist die Entry-Logik
unabhängig von ``backtest_history.py`` (das yfinance importiert) test- und
CI-gate-bar (``scripts/mock_test_entry_score.py`` läuft auf reinem stdlib).

Aggregiert 5 Komponenten zu einem 0–100-Entry-Score je Top-10-Kandidat.
Grenzen/Caps sind ENTSCHIEDEN (Diagnose n=227, 06.06.2026) — Laufzeit wählt
nichts. Alle Normalisierungen hart geclampt auf [0, 100].

Komponenten + Normalisierung:
  1. anomaly_freshness  → x × 100                         (x∈[0,1] Decay)
  2. score_delta_t1     → (x + 15) / 30 × 100             (symmetrisch ±15)
  3. uoa_atm_ratio      → min(x, 4.0) / 4.0 × 100         (Cap 4.0)
  4. rvol_buildup_5d    → min(x, 6.0) / 6.0 × 100         (Cap 6.0)
       PROXY: Tages-Volumen-Aufbau, NICHT echtes Intraday-rvol_acceleration
       (mit 2 Routine-Snapshots/Tag nicht baubar — ehrlich gelabelt).
  5. si_trend_5d_slope  → 5 Buckets (siehe NORMALIZE_SI_TREND)
       MISST Volumen-MOMENTUM (FINRA daily short VOLUME, Fluss), NICHT
       Short-Interest (Bestand) — ehrlich gelabelt.

Aggregation (Re-Normalisierung, Option B): ungewichteter Durchschnitt über
die EINGEHENDEN Komponenten (Gleichgewichtung, Anti-Overfitting). Fehlende
Komponente (None) fällt raus — KEIN Neutral-50-Auffüllen. 0 eingehende
Komponenten → entry_score = None (ehrlich, kein Fake-Wert).

anomaly_freshness=None — Run-Level-Unterscheidung (Option (c), Entscheidung
06.06.2026), weil ``None`` zwei nicht-feld-trennbare Fälle hat
(backtest_history.py: kein Push-ts → None; agent_state.json fehlt/korrupt →
leere Map → alle None):
  - push_history VERFÜGBAR (Map gefüllt) + anomaly None → Ticker nie gepusht
    → echte 0 (geht in den Schnitt ein, drückt zu Recht).
  - push_history NICHT verfügbar (Map leer) + anomaly None → Daten-Ausfall
    → Komponente fällt raus (kein falscher Malus für alle).
``push_history_available`` wird vom Aufrufer durchgereicht + mitpersistiert,
damit Ausfall-Tage am 30.06. sauber filterbar sind.
"""
from __future__ import annotations

# ── Caps / Bucket-Grenzen (entschieden, exakt — keine Laufzeit-Wahl) ────────
ENTRY_UOA_CAP = 4.0
ENTRY_RVOL_BUILDUP_CAP = 6.0
ENTRY_SCORE_DELTA_HALF_RANGE = 15.0   # (x+15)/30×100
# si_trend_5d_slope-Bucket-Grenzen (≤-Konvention, deterministisch eindeutig):
ENTRY_SI_TREND_EDGES = (-0.8, -0.2, 1.0, 5.0)   # → Scores 0/25/50/75/100


def _clamp_0_100(v: float) -> float:
    return round(max(0.0, min(100.0, v)), 2)


def normalize_anomaly_freshness(x):
    """x∈[0,1] (max(1−age_h/72, 0)) → ×100. None → None."""
    if x is None:
        return None
    return _clamp_0_100(float(x) * 100.0)


def normalize_score_delta_t1(x):
    """(x + 15) / 30 × 100, symmetrisch um 0; Clamp [0,100]. None → None."""
    if x is None:
        return None
    return _clamp_0_100((float(x) + ENTRY_SCORE_DELTA_HALF_RANGE)
                        / (2.0 * ENTRY_SCORE_DELTA_HALF_RANGE) * 100.0)


def normalize_uoa_atm_ratio(x):
    """min(x, 4.0) / 4.0 × 100 (Cap 4.0). None → None."""
    if x is None:
        return None
    return _clamp_0_100(min(float(x), ENTRY_UOA_CAP) / ENTRY_UOA_CAP * 100.0)


def normalize_rvol_buildup_5d(x):
    """min(x, 6.0) / 6.0 × 100 (Cap 6.0). PROXY (Tages-Volumen-Aufbau,
    kein echtes Intraday-Accel). None → None."""
    if x is None:
        return None
    return _clamp_0_100(min(float(x), ENTRY_RVOL_BUILDUP_CAP)
                        / ENTRY_RVOL_BUILDUP_CAP * 100.0)


def normalize_si_trend_5d(x):
    """5-Bucket-Map auf si_trend_5d_slope (Volumen-MOMENTUM, FINRA daily
    short volume — Fluss, nicht Bestand). ≤-Konvention macht jeden Input
    eindeutig; Grenzwerte fallen in den UNTEREN Bucket:
        x ≤ -0.8        → 0
        -0.8 < x ≤ -0.2 → 25
        -0.2 < x ≤ 1.0  → 50
        1.0  < x ≤ 5.0  → 75
        x > 5.0         → 100
    None → None.
    """
    if x is None:
        return None
    e0, e1, e2, e3 = ENTRY_SI_TREND_EDGES
    xf = float(x)
    if xf <= e0:
        return 0.0
    if xf <= e1:
        return 25.0
    if xf <= e2:
        return 50.0
    if xf <= e3:
        return 75.0
    return 100.0


def compute_entry_score(anomaly_freshness, score_delta_t1, uoa_atm_ratio,
                        rvol_buildup_5d, si_trend_5d_slope, *,
                        push_history_available: bool):
    """Aggregiert die 5 normalisierten Komponenten zum Entry-Score.

    Returnt ``(entry_score, components, n_components)``:
      - ``entry_score``: ungewichteter Durchschnitt der eingehenden
        Komponenten, gerundet 2 NK — oder ``None`` bei 0 Eingehenden.
      - ``components``: dict der 5 normalisierten Werte (je 0–100 oder None),
        inkl. der anomaly-(c)-Override (None→0 bei verfügbarer push_history).
      - ``n_components``: Anzahl eingehender (nicht-None) Komponenten 0–5.

    Re-Normalisierung (Option B): fehlende Komponente fällt raus, KEIN
    Neutral-Auffüllen, Gleichgewichtung. anomaly per Option (c) — siehe
    Modul-Docstring.
    """
    components = {
        "anomaly_freshness": normalize_anomaly_freshness(anomaly_freshness),
        "score_delta_t1":    normalize_score_delta_t1(score_delta_t1),
        "uoa_atm_ratio":     normalize_uoa_atm_ratio(uoa_atm_ratio),
        "rvol_buildup_5d":   normalize_rvol_buildup_5d(rvol_buildup_5d),
        "si_trend_5d":       normalize_si_trend_5d(si_trend_5d_slope),
    }
    # Option (c): anomaly None, aber push_history-Map gefüllt → „nie gepusht"
    # = echte 0 (geht in den Schnitt). Bei leerer Map (Daten-Ausfall) bleibt
    # None → fällt raus.
    if components["anomaly_freshness"] is None and push_history_available:
        components["anomaly_freshness"] = 0.0

    incoming = [v for v in components.values() if v is not None]
    n = len(incoming)
    entry_score = round(sum(incoming) / n, 2) if n else None
    return entry_score, components, n
