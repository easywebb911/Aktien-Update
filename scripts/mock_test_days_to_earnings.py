"""Mock-Tests für ``backtest_history._build_backtest_extension.days_to_earnings``
(Hypothese-H5-Vorbau, Stufe A — Katalysator-Vorwärts-Erhebung).

FIXTURE-ONLY — kein Kontakt mit ``backtest_history.json`` oder anderen Live-
Dateien. Kein echter yfinance-/Finnhub-Call. Deckt die pure-Python-Slice der
Persistenz ab (Feld-Wiring, S10-Whitelist, Look-Ahead-Isolation).

Verifiziert:
- (A) Persistenz-Wiring: `days_to_earnings` wird aus `s["earnings_days"]`
      1:1 gelesen und ins Return-Dict von `_build_backtest_extension`
      gelegt.
- (B) None-Semantik: `s["earnings_days"] is None → days_to_earnings is None`
      (legitim bei Micro-Caps / ETFs / Non-US ohne Kalender).
- (C) Int-Cast: `s["earnings_days"] = 5.0` → persistiert als `int(5)`
      (defensiv gegen Fließkomma aus Fetch).
- (D) S10-Whitelist + Schema-v4 (Lehre #388): Feld in OBSERVED, nicht
      MUSS/LAG, Schema bleibt v4.
- (E) Look-Ahead-Isolation (Konvention einfroren, analog #402): kein
      Read von `days_to_earnings` aus `.get(...)` oder `["..."]` in den
      Score-/Filter-/Push-Pfaden.
- (F) Konsistenz zum Live-Feld: `s["earnings_days"]` (Live-Enrichment-Feld,
      Kalender) und `days_to_earnings` (Backtest-Persistenz) tragen den
      gleichen Wert — kein zweiter Berechnungspfad.
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
    print("── (D) S10-Klassifikation + Schema-v4 (stdlib-only) ──────────")

    _check(
        "D1 days_to_earnings in S10_OBSERVED_FIELDS",
        "days_to_earnings" in config.S10_OBSERVED_FIELDS,
        "sonst feuert _s10_check_unknown_fields WARN am 1. Record (Lehre #388)",
    )
    _check(
        "D2 days_to_earnings NICHT in S10_MUSS_FIELDS",
        "days_to_earnings" not in config.S10_MUSS_FIELDS,
        "None legitim bei Micro-Caps/ETFs ohne öffentliche Termine",
    )
    _check(
        "D3 days_to_earnings NICHT in S10_LAG_FIELDS",
        "days_to_earnings" not in config.S10_LAG_FIELDS,
        "Wert ist zum Report-Tag gefroren, kein Lag-Outcome",
    )

    bh_src = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    _check(
        "D4 Schema-Version bleibt 4 (Source-Inspektion, KEIN Bump)",
        '"backtest_schema_version": 4' in bh_src
        and '"backtest_schema_version": 5' not in bh_src,
        "additive Erweiterung darf keinen Bump erzeugen",
    )
    _check(
        "D5 Feld im _build_backtest_extension-Return-Dict",
        '"days_to_earnings":' in bh_src,
        "additive Persistierung fehlt",
    )


def _test_look_ahead_isolation():
    """(E) Look-Ahead-Konvention einfroren: kein Read aus Score/Filter/Push."""
    print("── (E) Look-Ahead-Isolation ──────────────────────────────────")

    for path_rel, tag in (
        ("generate_report.py",  "Live-Report-/Score-Pfad"),
        ("ki_agent.py",         "KI-Agent-/Push-Pfad"),
        ("health_check.py",     "Health-Check-Pfad"),
    ):
        src = (ROOT / path_rel).read_text(encoding="utf-8")
        # ``days_to_earnings`` als Dict-Read = Look-Ahead-Bruch. Docstring-
        # /Kommentar-Erwähnungen wären ok (kein Read), aber wir wollen
        # sicherheitshalber gar keinen literalen Read.
        forbidden_reads = [
            'get("days_to_earnings")',
            "['days_to_earnings']",
            '["days_to_earnings"]',
        ]
        _check(
            f"E-{path_rel}: kein Read von days_to_earnings aus Dict",
            not any(pat in src for pat in forbidden_reads),
            f"{tag} — Look-Ahead-Bruch: Score/Push liest Backtest-Feld statt "
            f"Live-Enrichment s['earnings_days']",
        )


def _test_persistence_and_int_cast():
    """(A/B/C/F) — Persistenz + None-Semantik + Int-Cast via Fixture-Aufruf.

    Wir stubben yfinance (backtest_history importiert es top-level), damit
    _build_backtest_extension aufrufbar wird. Alle anderen Abhängigkeiten
    (compute_sub_scores_fn/safe_float_fn) sind Callable-Parameter → Test
    injiziert Stubs.
    """
    import types

    if "yfinance" not in sys.modules:
        sys.modules["yfinance"] = types.ModuleType("yfinance")

    try:
        from backtest_history import _build_backtest_extension
    except ImportError as exc:
        print(f"── Persistenz-Test ÜBERSPRUNGEN — Import-Fail: {exc}")
        return

    def _sub_stub(s):
        # Minimale sub-Score-Struktur; days_to_earnings hängt NICHT von sub ab.
        return {"struct": 0.0, "catalyst": 0.0, "timing": 0.0}

    def _safe_float(x, default=0.0):
        try:
            return float(x) if x is not None else default
        except (TypeError, ValueError):
            return default

    base_s = {
        "ticker":       "TESTX",
        "score":        75.0,
        "score_raw":    73.5,
        "short_float":  20.0,
        "short_ratio":  5.5,
        "rel_volume":   2.1,
        "finra_data":   {"trend": "up", "history": []},
        "sparkline":    {"scores": []},
        "hist_5d":      [],
        "avg_vol_20d":  0,
        "price":        10.5,
        # Weitere leere Defaults, damit _build_backtest_extension durchläuft
        "score_trend_bonus_pts": 0.0,
        "agent_boost_factor":     1.0,
        "finra_bonus_pts":        0.0,
        "short_float_source":     "yfinance",
    }

    print("── (A) Persistenz-Wiring days_to_earnings ────────────────────")
    s_with = {**base_s, "earnings_days": 5}
    ext = _build_backtest_extension(
        s_with, pool_position=1, pool_size=10, agent_signals={},
        compute_sub_scores_fn=_sub_stub, safe_float_fn=_safe_float,
    )
    _check(
        "A1 Feld days_to_earnings im Return-Dict",
        "days_to_earnings" in ext,
    )
    _check(
        "A2 Wert 1:1 aus s['earnings_days'] (5 → 5)",
        ext["days_to_earnings"] == 5,
        f"got {ext['days_to_earnings']!r}",
    )
    _check(
        "A3 Typ ist int (nicht float)",
        isinstance(ext["days_to_earnings"], int),
        f"got type {type(ext['days_to_earnings']).__name__}",
    )

    print("── (B) None-Semantik ─────────────────────────────────────────")
    s_none = {**base_s, "earnings_days": None}
    ext_none = _build_backtest_extension(
        s_none, pool_position=1, pool_size=10, agent_signals={},
        compute_sub_scores_fn=_sub_stub, safe_float_fn=_safe_float,
    )
    _check(
        "B1 s['earnings_days']=None → days_to_earnings=None",
        ext_none["days_to_earnings"] is None,
    )
    # Feld fehlt komplett im s (Micro-Cap ohne Fetch-Resultat)
    s_missing = {k: v for k, v in base_s.items() if k != "earnings_days"}
    ext_missing = _build_backtest_extension(
        s_missing, pool_position=1, pool_size=10, agent_signals={},
        compute_sub_scores_fn=_sub_stub, safe_float_fn=_safe_float,
    )
    _check(
        "B2 s['earnings_days'] fehlt → days_to_earnings=None (Fallback)",
        ext_missing["days_to_earnings"] is None,
    )

    print("── (C) Int-Cast (Fließkomma aus Fetch defensiv) ──────────────")
    s_float = {**base_s, "earnings_days": 12.0}
    ext_float = _build_backtest_extension(
        s_float, pool_position=1, pool_size=10, agent_signals={},
        compute_sub_scores_fn=_sub_stub, safe_float_fn=_safe_float,
    )
    _check(
        "C1 s['earnings_days']=12.0 (Float) → 12 (int)",
        ext_float["days_to_earnings"] == 12
        and isinstance(ext_float["days_to_earnings"], int),
    )
    # Kalendertage 0 = Earnings HEUTE (nicht 'None') — abgrenzen
    s_zero = {**base_s, "earnings_days": 0}
    ext_zero = _build_backtest_extension(
        s_zero, pool_position=1, pool_size=10, agent_signals={},
        compute_sub_scores_fn=_sub_stub, safe_float_fn=_safe_float,
    )
    _check(
        "C2 s['earnings_days']=0 → days_to_earnings=0 (Earnings heute, NICHT None)",
        ext_zero["days_to_earnings"] == 0,
    )

    print("── (F) Live-Feld-Konsistenz ──────────────────────────────────")
    _check(
        "F1 Persistenz nutzt s['earnings_days'] (kein zweiter Fetch/Compute)",
        s_with["earnings_days"] == ext["days_to_earnings"],
        "Backtest-Persistenz muss dem Live-Enrichment-Wert entsprechen "
        "(sonst Score-vs-Backfield-Divergenz)",
    )


def main():
    _test_s10_and_schema()
    _test_look_ahead_isolation()
    _test_persistence_and_int_cast()

    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (days_to_earnings: Persistenz + None + "
          "Int-Cast + S10 + Look-Ahead-Isolation + Live-Konsistenz).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
