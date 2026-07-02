"""Mock-Tests für ``backtest_history._compute_max_gain_pct`` (Hypothese-C-Vorbau).

FIXTURE-ONLY — kein Kontakt mit ``backtest_history.json`` oder anderen Live-
Dateien. Kein empirischer Vergleich gegen Bestandsdaten (das gehört in die
spätere Hypothese-C-Auswertung, nicht in diesen PR — Reihenfolge-Disziplin).

Zweistufiger Test:
  (A) S10-Whitelist + Schema-v4 + MUSS/LAG-Ausschluss — nur ``config``-Import,
      läuft im stdlib-only CI-Slot (Allowlist).
  (B) Formel-Tests gegen bekannte Peaks + Guards — braucht pandas/yfinance
      (weil ``backtest_history`` yfinance top-level importiert). Wird
      übersprungen wenn pandas nicht installiert (CI-Slot); läuft lokal /
      im Daily-Run-Environment vollständig.

Verifiziert:
- (A) ``max_gain_pct`` in ``S10_OBSERVED_FIELDS`` (Lehre #388 — sonst WARN)
       NICHT in MUSS/LAG (0.0-Semantik-Overload); Schema bleibt v4.
- (B) Formel gegen 5 bekannte Peaks:
      * Rolling low 10 → high 15 = +50 %
      * Flach (100/100) → 0.0
      * Monoton fallend, cummin trackt → korrekter max ratio
      * Später Spike mit Frühest-Low
      * Low sinkt nach Anfangs-Spike (cummin nimmt neuen Low)
- (B) Guards identisch zu ``_compute_max_drawdown``:
      * None → 0.0
      * empty DF → 0.0
      * len<2 → 0.0
      * fehlende Spalten → None
- (B) Spiegel-Symmetrie: gleicher DF liefert Drawdown UND Gain parallel.
- (B) Pure-Function: kein Input-Mutieren, Determinismus.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def _test_s10_and_schema():
    """(A) — läuft ohne pandas, stdlib-only. CI-Slot-Kompatibel."""
    print("── (A) S10-Klassifikation + Schema-v4 (stdlib-only) ──────────")

    _check("A1 max_gain_pct in S10_OBSERVED_FIELDS",
           "max_gain_pct" in config.S10_OBSERVED_FIELDS,
           "sonst feuert _s10_check_unknown_fields WARN am 1. Record (Lehre #388)")

    _check("A2 max_gain_pct NICHT in S10_MUSS_FIELDS",
           "max_gain_pct" not in config.S10_MUSS_FIELDS,
           "0.0-Semantik-Overload — kein sinnvoller MUSS-Check")

    _check("A3 max_gain_pct NICHT in S10_LAG_FIELDS",
           "max_gain_pct" not in config.S10_LAG_FIELDS,
           "rolling-Update, kein Fixed-Lag-Zeitpunkt")

    _check("A4 Spiegel-Konsistenz — auch max_drawdown_pct nur OBSERVED",
           ("max_drawdown_pct" in config.S10_OBSERVED_FIELDS
            and "max_drawdown_pct" not in config.S10_MUSS_FIELDS
            and "max_drawdown_pct" not in config.S10_LAG_FIELDS))

    # Schema-Version — additiv, KEIN v4-Bump. Die Version ist im
    # _append_backtest_entries-Pfad hardcodiert (kein Config-Konstant-Import
    # nötig), also inspizieren wir den Source direkt.
    bh_src = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    _check("A5 Schema-Version bleibt 4 (Source-Inspektion, KEIN Bump)",
           '"backtest_schema_version": 4' in bh_src
           and '"backtest_schema_version": 5' not in bh_src,
           "additive Erweiterung darf keinen Bump erzeugen")

    # A6 — der neue Feld-Name muss im Init-Block der neuen Records auftauchen.
    _check("A6 max_gain_pct wird im _append_backtest_entries-Init geschrieben",
           '"max_gain_pct": 0.0' in bh_src,
           "additive Persistierung im Record-Init fehlt")

    # A7 — Rolling-Update-Guard: alte Records ohne das Feld bleiben unangetastet
    # (Backwards-Compat, analog Drawdown-Pfad).
    _check("A7 Rolling-Update-Guard schützt Alt-Records vor Auto-Backfill",
           '"max_gain_pct" in e' in bh_src,
           "Guard-Bedingung 'max_gain_pct in e' muss den Rolling-Update-Setter schützen")


def _test_formula_and_guards():
    """(B) — braucht pandas + backtest_history-Import (yfinance top-level)."""
    try:
        import pandas as pd  # noqa: F401
        import yfinance  # noqa: F401
        import backtest_history as bh
    except ImportError as exc:
        print(f"── (B) Formel-/Guard-Tests: ÜBERSPRUNGEN — {exc} nicht "
              "verfügbar (CI-Slot stdlib+jinja2+pyyaml). Formel-Verifikation "
              "läuft im Daily-Run-Environment mit pandas.")
        return

    print("── (B) Formel-Tests gegen bekannte Peaks ─────────────────────")

    def _df(highs, lows):
        return pd.DataFrame({"High": highs, "Low": lows})

    # F1: rolling low 10, high 15 → +50%
    df1 = _df(highs=[11.0, 12.0, 15.0], lows=[10.0, 11.0, 13.0])
    r1 = bh._compute_max_gain_pct(df1)
    _check("B-F1 rolling low 10 → high 15 = +50.0", r1 == 50.0, f"got {r1}")

    # F2: konstant → 0.0
    df2 = _df(highs=[100.0, 100.0, 100.0], lows=[100.0, 100.0, 100.0])
    r2 = bh._compute_max_gain_pct(df2)
    _check("B-F2 flach (100/100/100) → 0.0", r2 == 0.0, f"got {r2}")

    # F3: monoton fallend, cummin trackt → Tag 3: (85-80)/80 = 6.25
    df3 = _df(highs=[105.0, 95.0, 85.0], lows=[100.0, 90.0, 80.0])
    r3 = bh._compute_max_gain_pct(df3)
    _check("B-F3 monoton fallend, max ≈ 6.25", r3 == 6.25, f"got {r3}")

    # F4: später Spike; cummin=[50,50,50,50]; High Tag 3 = 90 → (90-50)/50 = 80%
    df4 = _df(highs=[52.0, 58.0, 90.0, 55.0], lows=[50.0, 55.0, 60.0, 52.0])
    r4 = bh._compute_max_gain_pct(df4)
    _check("B-F4 später Spike, Low bleibt 50 → +80.0", r4 == 80.0, f"got {r4}")

    # F5: Low sinkt nach Anfangs-Spike. cummin=[100,80]; Tag 2: (200-80)/80 = 150
    df5 = _df(highs=[110.0, 200.0], lows=[100.0, 80.0])
    r5 = bh._compute_max_gain_pct(df5)
    _check("B-F5 Low sinkt zu 80, High spikt 200 → +150.0", r5 == 150.0,
           f"got {r5}")

    print("── (B) Guards identisch zu _compute_max_drawdown ─────────────")

    _check("B-G1 None → 0.0", bh._compute_max_gain_pct(None) == 0.0,
           f"got {bh._compute_max_gain_pct(None)}")

    r_empty = bh._compute_max_gain_pct(pd.DataFrame({"High": [], "Low": []}))
    _check("B-G2 empty DF → 0.0", r_empty == 0.0, f"got {r_empty}")

    df_1row = _df(highs=[100.0], lows=[95.0])
    _check("B-G3 len<2 → 0.0", bh._compute_max_gain_pct(df_1row) == 0.0,
           f"got {bh._compute_max_gain_pct(df_1row)}")

    df_broken = pd.DataFrame({"Close": [1.0, 2.0]})
    r_broken = bh._compute_max_gain_pct(df_broken)
    _check("B-G4 fehlende Spalten → None", r_broken is None, f"got {r_broken}")

    print("── (B) Spiegel-Symmetrie zu _compute_max_drawdown ────────────")

    # Auf F1: cummax([11,12,15]) = [11,12,15]; Low=[10,11,13].
    # Tag 3: (13-15)/15 = -13.333... → round(2) = -13.33
    dd1 = bh._compute_max_drawdown(df1)
    _check("B-S1 Drawdown auf F1 = -13.33", dd1 == -13.33, f"got {dd1}")

    _check("B-S2 Gain(+50) und Drawdown(-13.33) parallel berechenbar",
           r1 == 50.0 and dd1 == -13.33)

    print("── (B) Pure-Function-Kontrakt ────────────────────────────────")

    df_probe = _df(highs=[11.0, 12.0, 15.0], lows=[10.0, 11.0, 13.0])
    df_probe_copy = df_probe.copy()
    _ = bh._compute_max_gain_pct(df_probe)
    _check("B-P1 Input-DF nicht mutiert", df_probe.equals(df_probe_copy))

    a = bh._compute_max_gain_pct(df1)
    b = bh._compute_max_gain_pct(df1)
    _check("B-P2 Determinismus (a == b)", a == b, f"a={a} b={b}")


def main():
    _test_s10_and_schema()
    _test_formula_and_guards()

    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (max_gain_pct: S10 + Formel + Guards + Spiegel).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
