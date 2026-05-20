"""CLI-Diagnose: Expectancy + Bootstrap-95%-CI pro Score-Bucket × Source.

Analyse-only — KEIN Frontend, kein Tool-Eingriff, kein Schreibzugriff auf
``backtest_history.json``. Single-Source-of-Truth-Datei wird nur gelesen
und tabellarisch ausgewertet.

Hintergrund: Die heutige Hit-Rate-Anzeige im Backtest-Panel verzerrt bei
asymmetrischer Strategie (Knaller treiben den Erwartungswert). Expectancy
ist die ehrliche Aktions-Metrik — aber der Backtest-Pool ist heute
bootstrap-dominiert (vereinfachte Score-Formel ≠ Live-Score). Dieses
Skript trennt ``source='daily'`` von ``source='bootstrap'`` und zeigt
mit Bootstrap-95%-CI ob der echte Live-Pool im ≥70-Bucket überhaupt
belastbares n hat.

Aufruf::

    python3 scripts/expectancy_diagnose.py

Pure stdlib (json, random, statistics) — keine scipy/numpy-Abhängigkeit.
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path


# ── Konfiguration ──────────────────────────────────────────────────────────

BACKTEST_FILE  = "backtest_history.json"
BOOTSTRAP_ITER = 1000
BOOTSTRAP_CI_LO = 2.5
BOOTSTRAP_CI_HI = 97.5
MIN_N_BELASTBAR = 30
RNG_SEED = 42  # deterministisch — Easy soll reproduzierbare Zahlen sehen

BUCKETS = [
    ("<50",    lambda s: s < 50),
    ("50-69",  lambda s: 50 <= s < 70),
    (">=70",   lambda s: s >= 70),
]

SOURCES = ["daily", "bootstrap", "all"]
HORIZONS = [
    # (Label, t0-Feld, t1-Feld)
    ("5d",  "return_5d",  "return_5d_t1"),
    ("3d",  "return_3d",  "return_3d_t1"),
    ("10d", "return_10d", "return_10d_t1"),
]


# ── Statistik-Helpers ──────────────────────────────────────────────────────


def percentile(sorted_values: list[float], p: float) -> float:
    """Lineares Perzentil (typ. R-7 / numpy.percentile-Default).

    ``sorted_values`` muss aufsteigend sortiert sein. ``p`` in 0..100.
    """
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


def bootstrap_mean_ci(values: list[float],
                       n_iter: int = BOOTSTRAP_ITER,
                       lo_pct: float = BOOTSTRAP_CI_LO,
                       hi_pct: float = BOOTSTRAP_CI_HI,
                       rng: random.Random | None = None
                       ) -> tuple[float, float] | tuple[None, None]:
    """95%-CI auf den Mittelwert via Bootstrap-Resample mit Zurücklegen.

    Returnt (None, None) wenn n < 2.
    """
    n = len(values)
    if n < 2:
        return (None, None)
    if rng is None:
        rng = random.Random()
    means: list[float] = []
    for _ in range(n_iter):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    return (percentile(means, lo_pct), percentile(means, hi_pct))


def compute_stats(returns: list[float], rng: random.Random) -> dict:
    """Kennzahlen + CI für eine Returns-Liste. Fail-soft bei n=0/1."""
    n = len(returns)
    if n == 0:
        return {
            "n": 0, "win_pct": None, "avg_win": None, "avg_loss": None,
            "pf": None, "expectancy": None, "ci_lo": None, "ci_hi": None,
            "median": None,
        }
    wins   = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    avg_win  = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    sum_w = sum(wins)
    sum_l = abs(sum(losses)) if losses else 0.0
    pf = (sum_w / sum_l) if sum_l > 0 else (float("inf") if sum_w > 0 else None)
    expectancy = sum(returns) / n
    median = statistics.median(returns) if n >= 1 else None
    ci_lo, ci_hi = bootstrap_mean_ci(returns, rng=rng)
    return {
        "n":          n,
        "win_pct":    100.0 * len(wins) / n,
        "avg_win":    avg_win,
        "avg_loss":   avg_loss,
        "pf":         pf,
        "expectancy": expectancy,
        "ci_lo":      ci_lo,
        "ci_hi":      ci_hi,
        "median":     median,
    }


# ── Daten-Loader / Filter ──────────────────────────────────────────────────


def load_entries(path: str = BACKTEST_FILE) -> list[dict]:
    p = Path(path)
    if not p.exists():
        sys.exit(f"FEHLER: {path} nicht gefunden im CWD {Path.cwd()}")
    with p.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        sys.exit(f"FEHLER: {path} ist kein JSON-Array")
    return data


def filter_returns(entries: list[dict],
                   bucket_pred,
                   source_filter: str,
                   return_field: str) -> list[float]:
    """Sammle gültige Return-Werte für Bucket × Source × Horizont."""
    out: list[float] = []
    for e in entries:
        score = e.get("score")
        if score is None or not bucket_pred(score):
            continue
        src = e.get("source") or "daily"
        if source_filter != "all" and src != source_filter:
            continue
        v = e.get(return_field)
        if v is None or not isinstance(v, (int, float)):
            continue
        out.append(float(v))
    return out


# ── Ausgabe-Formatierung ───────────────────────────────────────────────────


def fmt_pct(v, width: int = 7, signed: bool = True) -> str:
    if v is None:
        return f"{'—':>{width}}"
    if v == float("inf"):
        return f"{'inf':>{width}}"
    sign = "+" if signed and v >= 0 else ""
    return f"{sign}{v:.2f}%".rjust(width)


def fmt_num(v, width: int = 6, decimals: int = 2) -> str:
    if v is None:
        return f"{'—':>{width}}"
    if v == float("inf"):
        return f"{'inf':>{width}}"
    return f"{v:.{decimals}f}".rjust(width)


def fmt_ci(lo, hi, width: int = 18) -> str:
    if lo is None or hi is None:
        return f"{'—':>{width}}"
    sgn_lo = "+" if lo >= 0 else ""
    sgn_hi = "+" if hi >= 0 else ""
    return f"[{sgn_lo}{lo:.2f}..{sgn_hi}{hi:.2f}]".rjust(width)


def belastbarkeit_label(n: int, ci_lo, ci_hi) -> str:
    """Inline-Marker hinter der Zeile: n-Disziplin + CI-Belastbarkeit."""
    flags = []
    if n < MIN_N_BELASTBAR:
        flags.append(f"n<{MIN_N_BELASTBAR} – nicht belastbar")
    if ci_lo is not None and ci_hi is not None and ci_lo < 0 < ci_hi:
        flags.append("CI kreuzt Null – kein klares Vorzeichen")
    return ("  ⚠ " + " · ".join(flags)) if flags else ""


def render_horizon_block(label: str,
                          entries: list[dict],
                          source: str,
                          return_field: str,
                          rng_seed_offset: int) -> None:
    """Render eine Tabelle: Bucket-Zeilen für 1 Source × 1 Horizont."""
    print(f"\n  {label}")
    print(f"  {'Bucket':<8}{'n':>5}  {'Win%':>6}  "
          f"{'AvgWin':>8}  {'AvgLoss':>8}  {'PF':>6}  "
          f"{'Expectancy':>11}  {'95%-CI':>18}  {'Median':>9}")
    for bkey, bpred in BUCKETS:
        rng = random.Random(RNG_SEED + rng_seed_offset + hash(bkey) % 1000)
        returns = filter_returns(entries, bpred, source, return_field)
        st = compute_stats(returns, rng)
        if st["n"] == 0:
            print(f"  {bkey:<8}{0:>5}  {'—':>6}  {'—':>8}  {'—':>8}  "
                  f"{'—':>6}  {'—':>11}  {'—':>18}  {'—':>9}")
            continue
        line = (
            f"  {bkey:<8}{st['n']:>5}  "
            f"{st['win_pct']:>5.1f}%  "
            f"{fmt_pct(st['avg_win'], 8)}  "
            f"{fmt_pct(st['avg_loss'], 8)}  "
            f"{fmt_num(st['pf'], 6, 2)}  "
            f"{fmt_pct(st['expectancy'], 11)}  "
            f"{fmt_ci(st['ci_lo'], st['ci_hi'], 18)}  "
            f"{fmt_pct(st['median'], 9)}"
        )
        print(line + belastbarkeit_label(st["n"], st["ci_lo"], st["ci_hi"]))


def render_source_block(entries: list[dict], source: str) -> None:
    n_in_src = sum(1 for e in entries
                   if source == "all" or (e.get("source") or "daily") == source)
    print("\n" + "=" * 78)
    print(f"SOURCE = {source}   (Gesamteinträge im Pool: {n_in_src})")
    print("=" * 78)

    # PRIMÄR: 5d / t0
    render_horizon_block(
        label=f"PRIMÄR — {source} · Horizont 5d · t0 (Entry am Signal-Tag)",
        entries=entries, source=source, return_field="return_5d",
        rng_seed_offset=1)
    # Kompakt: 5d/t1, 3d/t0, 10d/t0
    render_horizon_block(
        label=f"{source} · 5d · t1 (Entry am Folgetag)",
        entries=entries, source=source, return_field="return_5d_t1",
        rng_seed_offset=2)
    render_horizon_block(
        label=f"{source} · 3d · t0",
        entries=entries, source=source, return_field="return_3d",
        rng_seed_offset=3)
    render_horizon_block(
        label=f"{source} · 10d · t0",
        entries=entries, source=source, return_field="return_10d",
        rng_seed_offset=4)


# ── Fakten-Zusammenfassung am Ende (NICHT-empfehlend, nur Fakten) ─────────


def summary_block(entries: list[dict]) -> None:
    """Kurzer Fakten-Block: n-Lage + welche daily-Buckets belastbar sind."""
    print("\n" + "=" * 78)
    print("FAKTEN-ZUSAMMENFASSUNG (keine Trade-Empfehlung)")
    print("=" * 78)

    # n-Lage pro Source pro Bucket (mit gültigem 5d-Return als Maßstab)
    rng = random.Random(RNG_SEED + 999)
    print("\n  Pool-Größen pro Source × Bucket (Einträge mit gültigem 5d-Return):")
    print(f"  {'Bucket':<8}  {'daily':>8}  {'bootstrap':>10}  {'all':>8}")
    for bkey, bpred in BUCKETS:
        n_d = len(filter_returns(entries, bpred, "daily",     "return_5d"))
        n_b = len(filter_returns(entries, bpred, "bootstrap", "return_5d"))
        n_a = len(filter_returns(entries, bpred, "all",       "return_5d"))
        print(f"  {bkey:<8}  {n_d:>8}  {n_b:>10}  {n_a:>8}")

    # daily-Buckets mit n >= 30 UND CI != 0 kreuzt
    print("\n  daily-Buckets mit n ≥ 30 UND 95%-CI das NICHT die Null kreuzt"
          " (5d/t0):")
    n_belastbar = 0
    for bkey, bpred in BUCKETS:
        rng_b = random.Random(RNG_SEED + 1 + hash(bkey) % 1000)
        returns = filter_returns(entries, bpred, "daily", "return_5d")
        st = compute_stats(returns, rng_b)
        n = st["n"]
        ci_lo, ci_hi = st["ci_lo"], st["ci_hi"]
        if (n >= MIN_N_BELASTBAR and ci_lo is not None and ci_hi is not None
                and not (ci_lo < 0 < ci_hi)):
            sign = "POSITIV" if (ci_lo > 0) else "NEGATIV"
            print(f"    • {bkey}: n={n}, Expectancy={fmt_pct(st['expectancy']).strip()}, "
                  f"CI={fmt_ci(ci_lo, ci_hi).strip()} → {sign}")
            n_belastbar += 1
    if n_belastbar == 0:
        print("    (keiner)")

    # ≥70-Frage: ja/nein
    rng_70 = random.Random(RNG_SEED + 1 + hash(">=70") % 1000)
    returns_70 = filter_returns(entries, BUCKETS[2][1], "daily", "return_5d")
    st_70 = compute_stats(returns_70, rng_70)
    print()
    if st_70["n"] >= MIN_N_BELASTBAR and st_70["ci_lo"] is not None and \
            not (st_70["ci_lo"] < 0 < st_70["ci_hi"]):
        verdict = (f"Ja — n={st_70['n']} ≥ {MIN_N_BELASTBAR} und 95%-CI "
                   f"{fmt_ci(st_70['ci_lo'], st_70['ci_hi']).strip()} "
                   f"kreuzt die Null nicht.")
    else:
        reasons = []
        if st_70["n"] < MIN_N_BELASTBAR:
            reasons.append(f"n={st_70['n']} < {MIN_N_BELASTBAR}")
        if st_70["ci_lo"] is not None and st_70["ci_hi"] is not None \
                and st_70["ci_lo"] < 0 < st_70["ci_hi"]:
            reasons.append("CI kreuzt Null")
        if not reasons:
            reasons = ["keine Daten"]
        verdict = "Nein — " + " UND ".join(reasons) + "."
    print(f"  Reicht die daily-Datenlage HEUTE für eine belastbare "
          f"Expectancy-Aussage im ≥70-Bucket (Horizont 5d/t0)?")
    print(f"  → {verdict}")


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> int:
    # Repo-Root als CWD voraussetzen — backtest_history.json liegt da
    entries = load_entries(BACKTEST_FILE)
    print(f"Backtest-Diagnose: Expectancy + Bootstrap-95%-CI")
    print(f"Datei: {BACKTEST_FILE} ({len(entries)} Einträge gesamt)")
    print(f"Bootstrap: {BOOTSTRAP_ITER} Resamples, RNG-Seed {RNG_SEED} "
          f"(deterministisch)")
    print(f"n-Schwelle für 'belastbar': {MIN_N_BELASTBAR}")

    for src in SOURCES:
        render_source_block(entries, src)

    summary_block(entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
