"""Mock-Tests für die NaN-Härtung im Backtest-Schreibpfad (21.09.2026).

BEFUND (Diagnose 21.09.2026, Gruppe-A-Fund #1+#2): ``backtest_history.py``
Z. 1318-1324 (``_append_backtest_entries``, der KANONISCHE Schreibpfad für
``backtest_history.json``) persistierte ``score``/``entry_price``/
``short_float``/``dtc``/``rvol`` über ``round(float(s.get(X) or 0), N)`` —
OHNE ``_safe_float``/``_finite``-Vorguard. Ein NaN (statt eines echt
fehlenden Wertes) lief dadurch unbemerkt als STILLE 0 in das Ground-Truth-
Dataset der laufenden §4-Vorabregistrierung (Exit-B.1, Stand n=134/250).
Derselbe Bug-Pattern parallel in ``_compute_si_slope_5d`` (si_new/si_old,
vorher Z. 411-412) und ``_compute_si_velocity_pub`` (vorher Z. 482-483).

FIX:
  1. ``_append_backtest_entries``: neuer Helper ``_round_finite_or_none()``
     nutzt den bereits injizierten, ECHTEN ``safe_float_fn`` (== die
     produktiv verdrahtete ``generate_report._safe_float``, prüft intern
     ``math.isfinite``) statt ``or 0``. NaN/Inf/None/fehlend -> ``None``
     (NICHT 0). Ein echtes ``0.0`` bleibt unverändert ``0.0`` (kein
     Null-Overload).
  2. ``_compute_si_slope_5d`` / ``_compute_si_velocity_pub``: nutzen jetzt
     die im selben Modul bereits vorhandene, SANKTIONIERTE ``_finite()``-
     Kopie (dokumentiert als bewusstes Duplikat von
     ``generate_report._finite``, siehe deren eigener Docstring) statt
     ``or 0`` für ``si_new``/``si_old``.

KEIN Zirkulär-Import-Risiko: ``_append_backtest_entries`` erhielt
``safe_float_fn`` bereits VOR diesem Fix als injizierten Parameter (siehe
Moduldocstring oben in ``backtest_history.py``) — nur an dieser einen
Stelle ungenutzt. Für ``_compute_si_slope_5d``/``_compute_si_velocity_pub``
wurde BEWUSST NICHT ``safe_float_fn`` per neuer Signatur injiziert — das
hätte zwei pure Funktionen mit eigener, unabhängiger Testsuite angefasst
(``mock_test_si_velocity_pub.py`` ruft ``_compute_si_velocity_pub`` an
13+ Stellen ohne ``safe_float_fn`` auf). Stattdessen die bereits im
selben Modul etablierte, sanktionierte ``_finite()``-Kopie verwendet —
exakt das Muster der 15.08.2026-Geschwister-Fixes
(``_compute_rvol_buildup_5d``/``_compute_vol_stability_5d``).

BESTANDSDATEN UNANGETASTET: dieser Fix härtet ausschließlich den
Schreibpfad für KÜNFTIGE Einträge. Bestehende ``backtest_history.json``-
Records werden NICHT rückwirkend korrigiert (analog PR #533/#534 — Root-
Fix und Bestandskorrektur bewusst getrennte Schritte).

Konsumenten-Check (Exzellenz-Block Punkt 4, vor dem Bau verifiziert,
hier NUR dokumentiert — kein Test nötig, da fremder Code unverändert):
  - ``scripts/expectancy_diagnose.py:filter_returns()`` ist bereits None-
    tolerant (``if score is None: continue``) — kein Zusatz-Guard nötig.
  - ``config.S10_OBSERVED_FIELDS`` enthält score/entry_price/short_float/
    dtc/rvol/si_velocity_pub bereits (keine S10_MUSS/_LAG-Einstufung) —
    kein neuer Digest-Alarm durch gelegentliches None.
  - ``matured_export.py`` kopiert Records als vollständiges ``dict(e)`` —
    None-Werte werden 1:1 mitkopiert, kein Sonderfall nötig.
  - Golden-Test (Outer-Page): unberührt — dessen Fixtures speisen keine
    NaN in diesen Pfad, Happy-Path-Ergebnis bleibt bytegleich.

Kategorie A: yfinance + Nachbar-Drittlibs gestubbt (``backtest_history``
importiert yfinance modulweit; Stub-Set analog
``mock_test_entry_shadow_persist.py``, das denselben End-to-End-Schreibpfad
bereits erfolgreich durchläuft), keine echte pandas-/Netzwerk-Nutzung in
den getesteten Funktionen — CI-gate-bar (stdlib+jinja2+pyyaml).

Tests:
  (A) Source-Inspektion: altes ``or 0``-Muster an allen drei Stellen weg,
      neuer Helper/Guard vorhanden, echter Call-Site nutzt
      ``safe_float_fn=_safe_float`` (Wiring-Beleg).
  (B) ``_compute_si_slope_5d``: NaN in si_new/si_old -> None; gültige
      Werte -> unverändertes Ergebnis (Gegenprobe).
  (C) ``_compute_si_velocity_pub``: dito.
  (D) ``_append_backtest_entries`` END-TO-END (echter Schreibpfad, echte
      ``generate_report._safe_float`` per Source-Extraktion+``exec``,
      keine Neu-Implementierung): ein NaN-Score persistiert als ``None``,
      ein gültiges Werte-Paket (inkl. eines echten ``0.0``) persistiert
      unverändert korrekt gerundet — Null-Overload-Gegenprobe.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sys
import tempfile
import types
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Drittlib-Stubs vor Import (backtest_history importiert yfinance modul-
#    weit; Stub-Set analog mock_test_entry_shadow_persist.py). ─────────────
for _mod_name in ("yfinance", "bs4", "deep_translator", "lxml", "pandas"):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)
sys.modules["yfinance"].download = lambda *a, **kw: None
sys.modules["yfinance"].Ticker = lambda *a, **kw: None
sys.modules["bs4"].BeautifulSoup = lambda *a, **kw: None
sys.modules["deep_translator"].GoogleTranslator = lambda *a, **kw: type(
    "T", (), {"translate": staticmethod(lambda s: s)}
)()

import backtest_history as bh  # noqa: E402
import config  # noqa: E402

ET = ZoneInfo("America/New_York")


def _extract_real_safe_float():
    """Zieht die ECHTE ``generate_report._safe_float`` per Source-
    Extraktion + ``exec`` (keine Neu-Implementierung, kein Import von
    generate_report.py — das würde die volle yfinance/pandas/bs4-
    Importkette top-level ziehen)."""
    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    start_marker = "def _safe_float(v, default: float = 0.0) -> float:"
    start = gr_src.index(start_marker)
    end = gr_src.index("\n\n\n", start)
    block_src = gr_src[start:end]
    ns = {"math": math}
    exec(compile(block_src, "<real_safe_float>", "exec"), ns)
    return ns["_safe_float"]


_real_safe_float = _extract_real_safe_float()


def _baseline_stock(**overrides):
    stock = {
        "ticker": "TEST", "score": 70.0, "price": 10.0,
        "short_float": 25.0, "short_ratio": 5.0, "rel_volume": 2.4,
        "float_shares": 1e8, "avg_vol_20d": 1e6, "hist_5d": [],
        "score_trend_bonus_pts": 0.0, "agent_boost_factor": 1.0,
        "finra_bonus_pts": 0.0, "short_float_source": "yfinance",
        "finra_data": {"trend": "no_data", "history": [],
                       "si_trend_source": "finra"},
        "sparkline": None,
    }
    stock.update(overrides)
    return stock


def _run_append(top10, *, safe_float_fn=None, now_et=None):
    """Ruft den ECHTEN Schreibpfad ``_append_backtest_entries`` in einem
    isolierten Tempdir auf und gibt die geschriebenen Einträge zurück."""
    if safe_float_fn is None:
        safe_float_fn = _real_safe_float
    if now_et is None:
        now_et = datetime(2026, 9, 21, 22, 0, tzinfo=ET)  # postclose, Montag
    report_date = now_et.strftime("%d.%m.%Y")
    for s in top10:
        s.setdefault("bar_date", now_et.strftime("%Y-%m-%d"))

    orig_cwd = os.getcwd()
    tmp_dir = tempfile.mkdtemp(prefix="mock_test_backtest_writepath_")
    try:
        os.chdir(tmp_dir)
        with open("agent_signals.json", "w") as fh:
            json.dump({"signals": {}}, fh)
        with open("backtest_history.json", "w") as fh:
            json.dump([], fh)
        bh._append_backtest_entries(
            top10, report_date, pool_size=len(top10),
            compute_sub_scores_fn=lambda s: {"struct": 0, "catalyst": 0,
                                             "timing": 0},
            safe_float_fn=safe_float_fn,
            now_et=now_et,
        )
        with open("backtest_history.json") as fh:
            return json.load(fh)
    finally:
        os.chdir(orig_cwd)
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK  {name}")
    else:
        _fails.append(f"{name}" + (f" — {detail}" if detail else ""))
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))


# ── (A) Source-Inspektion ───────────────────────────────────────────────


def test_a1_old_or_zero_pattern_gone_at_all_three_sites():
    src = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    old_patterns = [
        'round(float(s.get("score") or 0), 2)',
        'round(float(s.get("price") or 0), 4)',
        'round(float(s.get("short_float") or 0), 2)',
        'round(float(s.get("short_ratio") or 0), 2)',
        'round(float(s.get("rel_volume") or 0), 3)',
        'si_new = pts[0].get("short_interest") or 0',
        'si_old = pts[-1].get("short_interest") or 0',
        'si_new = eligible[0].get("short_interest") or 0',
        'si_old = eligible[n_reports - 1].get("short_interest") or 0',
    ]
    for pat in old_patterns:
        _check(f"A1 altes Muster weg: {pat!r}", pat not in src)


def test_a2_new_helper_and_guards_present():
    src = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    _check("A2 _round_finite_or_none definiert",
           "def _round_finite_or_none(" in src)
    _check("A2 Entry-Dict nutzt _round_finite_or_none für score",
           '"score":         _round_finite_or_none(s.get("score"), 2, safe_float_fn)'
           in src)
    _check("A2 Entry-Dict nutzt _round_finite_or_none für rvol",
           '"rvol":          _round_finite_or_none(s.get("rel_volume"), 3, safe_float_fn)'
           in src)
    _check("A2 _compute_si_slope_5d nutzt _finite() für si_new/si_old",
           "not _finite(si_new) or not _finite(si_old)" in src)


def test_a3_real_call_site_wires_real_safe_float():
    """Der einzige Produktions-Call in generate_report.py reicht die ECHTE
    _safe_float durch — kein Stub, kein Drift zwischen Test und Prod."""
    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    idx = gr_src.index("_n_backtest_appended = _append_backtest_entries(")
    call_block = gr_src[idx:idx + 300]
    _check("A3 Call-Site: safe_float_fn=_safe_float",
           "safe_float_fn=_safe_float" in call_block, call_block)


def test_a4_s10_classification_unchanged():
    """score/entry_price/short_float/dtc/rvol/si_velocity_pub bleiben
    OBSERVED (kein neuer MUSS/LAG-Alarm durch gelegentliches None)."""
    for field in ("score", "entry_price", "rvol", "dtc", "short_float",
                  "si_velocity_pub"):
        _check(f"A4 {field} in S10_OBSERVED_FIELDS",
               field in config.S10_OBSERVED_FIELDS)
        _check(f"A4 {field} NICHT in S10_MUSS_FIELDS",
               field not in config.S10_MUSS_FIELDS)
        _check(f"A4 {field} NICHT in S10_LAG_FIELDS",
               field not in config.S10_LAG_FIELDS)


# ── (B) _compute_si_slope_5d ────────────────────────────────────────────

_FINRA_HIST_5 = [
    {"short_interest": 900_000}, {"short_interest": 920_000},
    {"short_interest": 940_000}, {"short_interest": 960_000},
    {"short_interest": 1_000_000},
]


def test_b1_si_slope_nan_newest_returns_none():
    hist = [{"short_interest": float("nan")}] + _FINRA_HIST_5[1:]
    v = bh._compute_si_slope_5d(hist)
    _check("B1 NaN in si_new (neuester Punkt) -> None", v is None, repr(v))


def test_b2_si_slope_nan_oldest_returns_none():
    hist = _FINRA_HIST_5[:-1] + [{"short_interest": float("nan")}]
    v = bh._compute_si_slope_5d(hist)
    _check("B2 NaN in si_old (ältester Punkt) -> None", v is None, repr(v))


def test_b3_si_slope_valid_values_unchanged():
    v = bh._compute_si_slope_5d(_FINRA_HIST_5)
    expected = round((900_000 - 1_000_000) / 1_000_000, 4)
    _check("B3 gültige Werte -> unverändertes Ergebnis",
           v == expected, f"got={v} want={expected}")


def test_b4_si_slope_missing_field_returns_none():
    hist = [{}] + _FINRA_HIST_5[1:]
    v = bh._compute_si_slope_5d(hist)
    _check("B4 fehlendes short_interest-Feld -> None (nicht 0-Fake)",
           v is None, repr(v))


# ── (C) _compute_si_velocity_pub ────────────────────────────────────────

from datetime import date  # noqa: E402

_ENTRY_DATE = date(2026, 7, 1)
_PUB_HIST = [
    {"short_interest": 900_000, "pub_date": "2026-06-30"},
    {"short_interest": 1_000_000, "pub_date": "2026-06-15"},
]


def test_c1_si_velocity_nan_returns_none():
    hist = [{"short_interest": float("nan"), "pub_date": "2026-06-30"},
            _PUB_HIST[1]]
    v = bh._compute_si_velocity_pub(hist, _ENTRY_DATE, n_reports=2)
    _check("C1 NaN in si_new -> None", v is None, repr(v))


def test_c2_si_velocity_valid_values_unchanged():
    v = bh._compute_si_velocity_pub(_PUB_HIST, _ENTRY_DATE, n_reports=2)
    expected = round((900_000 - 1_000_000) / 1_000_000, 4)
    _check("C2 gültige Werte -> unverändertes Ergebnis",
           v == expected, f"got={v} want={expected}")


# ── (D) _append_backtest_entries — echter Schreibpfad, echte _safe_float ──


def test_d1_nan_score_persists_as_none_not_zero():
    top10 = [_baseline_stock(score=float("nan"))]
    written = _run_append(top10)
    entry = next(e for e in written if e["ticker"] == "TEST")
    _check("D1 NaN-Score persistiert als None (nicht 0)",
           entry["score"] is None, f"score={entry['score']!r}")


def test_d2_nan_short_float_persists_as_none_not_zero():
    top10 = [_baseline_stock(short_float=float("nan"))]
    written = _run_append(top10)
    entry = next(e for e in written if e["ticker"] == "TEST")
    _check("D2 NaN-short_float persistiert als None (nicht 0)",
           entry["short_float"] is None, f"short_float={entry['short_float']!r}")


def test_d3_valid_values_persist_correctly_including_real_zero():
    """Gegenprobe: gültige Werte inkl. eines ECHTEN 0.0 (rel_volume) bleiben
    unverändert korrekt — kein Null-Overload durch den neuen Guard."""
    top10 = [_baseline_stock(score=72.345, price=9.8765, short_float=12.3,
                             short_ratio=4.5, rel_volume=0.0)]
    written = _run_append(top10)
    entry = next(e for e in written if e["ticker"] == "TEST")
    _check("D3 score korrekt gerundet", entry["score"] == round(72.345, 2),
           f"score={entry['score']!r}")
    _check("D3 entry_price korrekt gerundet", entry["entry_price"] == 9.8765,
           f"entry_price={entry['entry_price']!r}")
    _check("D3 short_float korrekt gerundet", entry["short_float"] == 12.3,
           f"short_float={entry['short_float']!r}")
    _check("D3 dtc korrekt gerundet", entry["dtc"] == 4.5,
           f"dtc={entry['dtc']!r}")
    _check("D3 echtes 0.0 (rel_volume) bleibt 0.0, wird NICHT zu None",
           entry["rvol"] == 0.0 and entry["rvol"] is not None,
           f"rvol={entry['rvol']!r}")


def test_d4_missing_field_persists_as_none_not_zero():
    """Ein fehlendes Feld (Key nicht im Stock-Dict) -> None, kein 0-Fake."""
    top10 = [_baseline_stock()]
    del top10[0]["short_float"]
    written = _run_append(top10)
    entry = next(e for e in written if e["ticker"] == "TEST")
    _check("D4 fehlendes short_float-Feld -> None (nicht 0)",
           entry["short_float"] is None, f"short_float={entry['short_float']!r}")


def main() -> int:
    tests = [
        test_a1_old_or_zero_pattern_gone_at_all_three_sites,
        test_a2_new_helper_and_guards_present,
        test_a3_real_call_site_wires_real_safe_float,
        test_a4_s10_classification_unchanged,
        test_b1_si_slope_nan_newest_returns_none,
        test_b2_si_slope_nan_oldest_returns_none,
        test_b3_si_slope_valid_values_unchanged,
        test_b4_si_slope_missing_field_returns_none,
        test_c1_si_velocity_nan_returns_none,
        test_c2_si_velocity_valid_values_unchanged,
        test_d1_nan_score_persists_as_none_not_zero,
        test_d2_nan_short_float_persists_as_none_not_zero,
        test_d3_valid_values_persist_correctly_including_real_zero,
        test_d4_missing_field_persists_as_none_not_zero,
    ]
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001 — Test-Harness, nicht Prod
            _fails.append(f"{t.__name__}: unexpected {type(exc).__name__}: {exc}")
            print(f"  FAIL {t.__name__}: unexpected {type(exc).__name__}: {exc}")

    print()
    if _fails:
        print(f"{len(_fails)} FAIL:")
        for f in _fails:
            print("  -", f)
        return 1
    print(f"Alle {len(tests)} Backtest-Schreibpfad-NaN-Guard-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
