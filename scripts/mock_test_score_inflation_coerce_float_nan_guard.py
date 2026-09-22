"""Mock-Tests für die NaN-Härtung + Umbenennung von
``score_inflation_log._safe_float`` -> ``_coerce_float`` (21.09.2026).

BEFUND (Diagnose 21.09.2026, Folge zu PR #557): ``score_inflation_log.py``
enthielt eine LOKALE ``_safe_float()``, die NICHT NaN-sicher war (fing nur
``TypeError``/``ValueError`` — ``float(nan)`` wirft aber keine Exception,
ein NaN-Input lief also unbemerkt als NaN-Float durch statt auf ``default``
zu fallen) — trotz identischem Namen zur ECHTEN, sicheren
``generate_report._safe_float`` (prüft intern ``math.isfinite``). Die
Namensgleichheit täuschte eine Sicherheit vor, die nicht bestand.

FIX: umbenannt auf ``_coerce_float`` (bewusst ohne das Wort "safe") UND um
den fehlenden ``math.isfinite``-Check ergänzt. NaN/Inf fallen jetzt wie
None/nicht-konvertierbare Werte auf ``default``.

ZIRKULÄR-IMPORT EMPIRISCH VERIFIZIERT (nicht nur angenommen, wie vom
Auftrag verlangt): ein Modul-Level ``from generate_report import
_safe_float`` in ``score_inflation_log.py`` wurde probeweise gebaut und
gegen ein echtes ``import generate_report`` (mit gestubbten Drittlibs)
getestet — Ergebnis: ``ImportError: cannot import name '_safe_float' from
partially initialized module 'generate_report' (most likely due to a
circular import)``. Grund: ``generate_report.py`` importiert
``score_inflation_log`` bereits an Zeile 30, lange bevor
``generate_report._safe_float`` an Zeile ~2784 definiert wird. Deshalb
Variante (a) — lokale Funktion umbenennen + härten — statt (b) Import.
Dieses Testfile treibt daher weiterhin NUR die lokale, jetzt korrigierte
Funktion — kein Import-Versuch aus generate_report (der würde denselben
Crash reproduzieren und ist bereits einmalig während der Diagnose belegt,
nicht Teil dieser Testsuite).

SCOPE-HINWEIS (Exzellenz-Block Punkt 2 — transparent, nicht still
entschieden): ``_finra_combo_active()`` (Z. 117-134) wrapped die drei
``_coerce_float(...)``-Aufrufe weiterhin in ein äußeres ``or 0.0``
(Z. 125-127). Das ist HIER bewusst NICHT entfernt — anders als der
PR-#557-Bug in ``backtest_history.py`` (wo ``or 0`` direkt PERSISTIERTE
Ground-Truth-Werte kontaminierte), fließt das Ergebnis hier NUR in eine
Schwellen-Summe (``sf>=30`` etc.) — für ``>=``-Vergleiche MIT POSITIVEM
Schwellenwert ist "unbekannt (None, würde TypeError werfen) -> als 0.0
behandelt" gleichwertig zu "unbekannt -> aus der Summe ausgeschlossen":
beide tragen NICHTS zu ``n_combo`` bei, das Boolean-Ergebnis ist
identisch. Der äußere ``or 0.0`` ist hier zusätzlich ein NOTWENDIGER
Typ-Guard gegen ``None >= int`` (TypeError) — kein Bypass-Bug, sondern
ein korrekter, bewiesener Crash-Schutz. Test C3 unten beweist diese
Äquivalenz explizit (NaN-Input liefert dasselbe Ergebnis wie ein echter
0.0-Input).

GUARDIAN-NUANCE (21.09.2026, nicht blockierend, im Code selbst als
Docstring-Kommentar bei ``_finra_combo_active`` verankert): die
Äquivalenz gilt NUR, weil aktuell ALLE VIER Bedingungen ``>=``-mit-
positivem-Wert sind. Käme künftig eine ``<=``- oder negativ-geschwellte
Bedingung hinzu, würde sie lautlos brechen (NaN-als-0.0 würde dann
fälschlich aktivieren, NaN-als-ausgeschlossen bliebe korrekt) — bei
einer Erweiterung der Combo-Bedingungen erneut prüfen.

WICHTIG — Bestandsaufnahme weiterer ``_safe_float``-artiger Helfer im Repo
(Auftrag: NUR melden, NICHT mitfixen). Ursprünglicher Grep
(``grep -rn "^def _safe_float"``, zeilenanfang-verankert) fand nur
``scripts/mock_test_change2d_nan_hardening.py:163`` (Test-Fixture,
bereits korrekt via ``math.isfinite``, kein Fix nötig) und
``generate_report.py:16774`` (``_to_f``, anders benannt, nutzt bereits
``_finite()``, ebenfalls sicher).

KORREKTUR (Guardian-Review 21.09.2026 — der ursprüngliche Grep hatte
einen blinden Fleck: der ``^def``-Anker übersieht eingerückte/
verschachtelte Definitionen): eine WEITERE, vom ursprünglichen Cross-
Check übersehene Instanz — ``scripts/mock_test_days_to_earnings.py:130``,
eine eingerückte, verschachtelte ``def _safe_float(x, default=0.0):``
(innerhalb ``_test_persistence_and_int_cast``) mit demselben unsicheren
Muster (kein ``math.isfinite``-Check). Wird dort als
``safe_float_fn=_safe_float`` in echte Aufrufe von
``_build_backtest_extension`` (backtest_history.py) injiziert — aktuell
FOLGENLOS, weil kein Testfall in dieser Datei ``safe_float_fn`` mit
einem NaN-Input exerciert. Nur gemeldet, NICHT in diesem PR gefixt
(Sequenz-Regel) — Empfehlung für ein separates Folge-Ticket: denselben
``math.isfinite``-Guard dort nachziehen, bevor die Datei um einen
NaN-Testfall erweitert wird.

Kategorie A: score_inflation_log.py ist reines stdlib (json/logging/math/
os/datetime/typing/zoneinfo) — kein Stub nötig, direkter Import.

Tests:
  (A) Source-Inspektion: alte Funktion/Name weg, neue vorhanden, keine
      generate_report-Importe in dieser Datei.
  (B) ``_coerce_float`` direkt: NaN -> default (None ohne expliziten
      Default, expliziter Default sonst); Inf -> default; gültiger Wert
      unverändert durchgereicht; None -> default; nicht-konvertierbarer
      String -> default.
  (C) ``_finra_combo_active`` END-TO-END: NaN in short_float/short_ratio/
      rel_volume erzeugt NICHT fälschlich ein aktives Combo-Flag (kein
      stiller "immer >= Schwelle"-Bug) UND liefert bewiesen dasselbe
      Ergebnis wie ein echtes 0.0 (Äquivalenz-Test, siehe Scope-Hinweis).
  (D) ``_build_entry`` END-TO-END (echter Schreibpfad ins Log-Zeilen-Dict):
      ein NaN-Score persistiert als der vom Caller angeforderte Default
      (0.0, NICHT eine rohe NaN — das war der eigentliche stille Bug:
      alte Funktion ignorierte den Default bei NaN-Input komplett), ein
      Feld ohne expliziten Default (z.B. rsi14) persistiert bei NaN als
      None (nicht 0.0) — Null-Overload-Gegenprobe mit einem echten 0.0.
"""
from __future__ import annotations

import math
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import score_inflation_log as sil  # noqa: E402

_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK  {name}")
    else:
        _fails.append(f"{name}" + (f" — {detail}" if detail else ""))
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))


def _stub_stock(ticker: str = "TEST", **overrides) -> dict:
    base = {
        "ticker":      ticker,
        "score":       72.5,
        "score_raw":   75.2,
        "score_smoothed": 72.8,
        "rel_volume":  2.31,
        "change_2d":   6.16,
        "change_3d":   11.51,
        "rsi14":       62.4,
        "short_float": 30.56,
        "short_ratio": 18.36,
        "finra_data":  {"trend": "down"},
        "finra_bonus_pts": 5.0,
        "earliness_pts": 3,
        "score_trend_bonus_pts": 0.0,
        "agent_boost_factor": 1.05,
        "late_runner": False,
    }
    base.update(overrides)
    return base


def _stub_sub_scores(stock: dict) -> dict:
    return {
        "struct": 28.3, "catalyst": 12.5, "timing": 22.8,
        "struct_max": 33, "catalyst_max": 32, "timing_max": 30,
        "turnover_pts": 6, "gap_pts": 5, "rs_spy_pts": 2,
    }


# ── (A) Source-Inspektion ───────────────────────────────────────────────


def test_a1_old_name_gone_new_name_present():
    src = (ROOT / "score_inflation_log.py").read_text(encoding="utf-8")
    _check("A1 alte Funktionsdefinition 'def _safe_float(' weg",
           "def _safe_float(" not in src)
    _check("A1 neue Funktionsdefinition 'def _coerce_float(' vorhanden",
           "def _coerce_float(" in src)
    _check("A1 kein Call-Site nutzt noch den alten Namen",
           "_safe_float(" not in src)
    _check("A1 math.isfinite-Check vorhanden",
           "math.isfinite(f)" in src)


def test_a2_no_generate_report_import():
    """Kein Modul-Level-Import aus generate_report — der wurde empirisch
    als zirkulär belegt (siehe Moduldocstring hier + Funktions-Docstring
    in score_inflation_log.py)."""
    src = (ROOT / "score_inflation_log.py").read_text(encoding="utf-8")
    _check("A2 keine 'import generate_report'-Zeile",
           "import generate_report" not in src)
    _check("A2 keine 'from generate_report'-Zeile",
           "from generate_report" not in src)


def test_a3_call_sites_migrated():
    src = (ROOT / "score_inflation_log.py").read_text(encoding="utf-8")
    _check("A3 _finra_combo_active nutzt _coerce_float",
           '_coerce_float(stock.get("short_float", 0)) or 0.0' in src)
    _check("A3 _build_entry (score_total) nutzt _coerce_float",
           '"score_total":    _coerce_float(stock.get("score"), 0.0)' in src)


# ── (B) _coerce_float direkt ────────────────────────────────────────────


def test_b1_nan_no_explicit_default_returns_none():
    v = sil._coerce_float(float("nan"))
    _check("B1 NaN ohne expliziten Default -> None", v is None, repr(v))


def test_b2_nan_with_explicit_default_returns_default():
    v = sil._coerce_float(float("nan"), 0.0)
    _check("B2 NaN mit explizitem Default 0.0 -> 0.0 (nicht NaN selbst)",
           v == 0.0 and not (isinstance(v, float) and math.isnan(v)),
           repr(v))


def test_b3_inf_returns_default():
    v = sil._coerce_float(float("inf"), -1.0)
    _check("B3 +Inf mit Default -1.0 -> -1.0", v == -1.0, repr(v))
    v2 = sil._coerce_float(float("-inf"))
    _check("B3 -Inf ohne expliziten Default -> None", v2 is None, repr(v2))


def test_b4_valid_value_passes_through_unchanged():
    v = sil._coerce_float(42.5)
    _check("B4 gültiger Wert unverändert durchgereicht", v == 42.5, repr(v))
    v2 = sil._coerce_float("13.37")
    _check("B4 gültiger numerischer String -> 13.37", v2 == 13.37, repr(v2))


def test_b5_none_and_garbage_return_default():
    _check("B5 None -> default (None)", sil._coerce_float(None) is None)
    _check("B5 None mit Default 7.0 -> 7.0",
           sil._coerce_float(None, 7.0) == 7.0)
    _check("B5 nicht-konvertierbarer String -> default",
           sil._coerce_float("abc", -9.0) == -9.0)


def test_b6_real_zero_is_not_null_overload():
    """Gegenprobe: ein echtes 0.0 bleibt 0.0, wird NICHT zu default."""
    v = sil._coerce_float(0.0, -1.0)
    _check("B6 echtes 0.0 bleibt 0.0 (kein Null-Overload)", v == 0.0, repr(v))


# ── (C) _finra_combo_active END-TO-END ──────────────────────────────────


def test_c1_nan_short_float_does_not_falsely_activate_combo():
    """NaN in EINEM Feld darf den Combo-Bonus nicht fälschlich auslösen —
    3 der 4 verbleibenden Bedingungen müssten dafür stimmen, hier absichtlich
    nur 2 gültige (dtc>=5, si_trend=up) + 1 NaN-Feld -> n_combo bleibt 2."""
    stock = _stub_stock(short_float=float("nan"), short_ratio=6.0,
                        rel_volume=1.0, finra_data={"trend": "up"})
    result = sil._finra_combo_active(stock)
    _check("C1 NaN short_float -> Combo NICHT fälschlich aktiv (n_combo=2<3)",
           result is False, repr(result))


def test_c2_nan_all_three_numeric_fields_combo_inactive():
    stock = _stub_stock(short_float=float("nan"), short_ratio=float("nan"),
                        rel_volume=float("nan"), finra_data={"trend": "up"})
    result = sil._finra_combo_active(stock)
    _check("C2 NaN in allen 3 numerischen Feldern -> Combo inaktiv "
           "(nur SI-Trend zählt, n_combo=1<3)", result is False, repr(result))


def test_c3_nan_equivalent_to_real_zero_proven():
    """Äquivalenz-Beweis (Scope-Begründung oben): NaN-Input und ein
    ECHTES 0.0 im selben Feld liefern DASSELBE _finra_combo_active-
    Ergebnis, über mehrere Kombinationen hinweg."""
    combos = [
        {"short_ratio": 6.0, "rel_volume": 3.0, "finra_data": {"trend": "up"}},
        {"short_ratio": 2.0, "rel_volume": 0.5, "finra_data": {"trend": "down"}},
        {"short_ratio": 20.0, "rel_volume": 10.0, "finra_data": {"trend": "up"}},
    ]
    all_equal = True
    for extra in combos:
        stock_nan = _stub_stock(short_float=float("nan"), **extra)
        stock_zero = _stub_stock(short_float=0.0, **extra)
        r_nan = sil._finra_combo_active(stock_nan)
        r_zero = sil._finra_combo_active(stock_zero)
        if r_nan != r_zero:
            all_equal = False
    _check("C3 NaN-Input == echtes-0.0-Input-Ergebnis über alle Kombinationen",
           all_equal)


def test_c4_valid_combo_still_activates_regression():
    """Regression: ein echter n_combo>=3-Fall bleibt aktiv (kein
    Kollateralschaden durch die Umbenennung/Härtung)."""
    stock = _stub_stock(short_float=35.0, short_ratio=8.0, rel_volume=3.0,
                        finra_data={"trend": "up"})
    result = sil._finra_combo_active(stock)
    _check("C4 echter n_combo=4>=3-Fall bleibt True", result is True, repr(result))


# ── (D) _build_entry END-TO-END ─────────────────────────────────────────


def test_d1_nan_score_persists_as_requested_default_not_raw_nan():
    """DER eigentliche stille Bug: alte Funktion ignorierte den
    übergebenen Default (0.0) bei NaN und gab die rohe NaN zurück -> eine
    NaN wäre wörtlich in score_inflation_log.jsonl gelandet."""
    stock = _stub_stock(score=float("nan"))
    entry = sil._build_entry(stock, datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc),
                             _stub_sub_scores(stock))
    v = entry["score_total"]
    _check("D1 NaN-Score persistiert als 0.0 (Default), NICHT als rohe NaN",
           v == 0.0 and not (isinstance(v, float) and math.isnan(v)),
           repr(v))


def test_d2_nan_without_explicit_default_persists_as_none():
    """rsi14 hat KEINEN expliziten Default in _build_entry -> NaN muss zu
    None werden, nicht zu 0.0 (kein Null-Overload) und nicht zu roher NaN."""
    stock = _stub_stock(rsi14=float("nan"))
    entry = sil._build_entry(stock, datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc),
                             _stub_sub_scores(stock))
    v = entry["drivers_raw"]["rsi14"]
    _check("D2 NaN-rsi14 (kein expliziter Default) -> None",
           v is None, repr(v))


def test_d3_valid_values_unchanged_regression():
    stock = _stub_stock()
    entry = sil._build_entry(stock, datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc),
                             _stub_sub_scores(stock))
    _check("D3 score_total unverändert", entry["score_total"] == 72.5)
    _check("D3 rsi14 unverändert", entry["drivers_raw"]["rsi14"] == 62.4)
    _check("D3 finra_combo_active weiterhin korrekt (short_float=30.56<30? nein "
           ">=30 True, short_ratio=18.36>=5 True, rel_volume=2.31>=2.0 True, "
           "trend=down -> n_combo=3 -> True)",
           entry["drivers_raw"]["finra_combo_active"] is True)


def test_d4_real_zero_field_not_turned_into_none():
    """Null-Overload-Gegenprobe: ein echtes 0.0 (score_trend_bonus_pts=0.0,
    expliziter Default 0.0 in _build_entry) bleibt 0.0."""
    stock = _stub_stock(score_trend_bonus_pts=0.0)
    entry = sil._build_entry(stock, datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc),
                             _stub_sub_scores(stock))
    v = entry["sub_scores"]["score_trend_bonus"]
    _check("D4 echtes 0.0 (score_trend_bonus) bleibt 0.0, nicht None",
           v == 0.0 and v is not None, repr(v))


def main() -> int:
    tests = [
        test_a1_old_name_gone_new_name_present,
        test_a2_no_generate_report_import,
        test_a3_call_sites_migrated,
        test_b1_nan_no_explicit_default_returns_none,
        test_b2_nan_with_explicit_default_returns_default,
        test_b3_inf_returns_default,
        test_b4_valid_value_passes_through_unchanged,
        test_b5_none_and_garbage_return_default,
        test_b6_real_zero_is_not_null_overload,
        test_c1_nan_short_float_does_not_falsely_activate_combo,
        test_c2_nan_all_three_numeric_fields_combo_inactive,
        test_c3_nan_equivalent_to_real_zero_proven,
        test_c4_valid_combo_still_activates_regression,
        test_d1_nan_score_persists_as_requested_default_not_raw_nan,
        test_d2_nan_without_explicit_default_persists_as_none,
        test_d3_valid_values_unchanged_regression,
        test_d4_real_zero_field_not_turned_into_none,
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
    print(f"Alle {len(tests)} score_inflation_log-_coerce_float-NaN-Guard-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
