#!/usr/bin/env python3
"""Mock-Test für ``backtest_history._compute_si_velocity_pub`` (PR-3).

KERN-Beweis: der pub_date-Look-Ahead-Filter. Ein Report mit
``settlement_date <= entry_date`` ABER ``pub_date > entry_date`` MUSS
verworfen werden — sonst leakt der Report in die Zukunft (Rule 4560:
Publikation ~7 Handelstage NACH Settlement).

Namens-Disambiguation: ``si_velocity_pub`` (dieser PR) unterscheidet sich
absichtlich vom älteren ``si_velocity``-Displayfeld in
``generate_report.py`` (dort: absolute Shares/Tag über die volle FINRA-
History, kein pub_date-Filter, rein Anzeige + KI-Boost). Beide koexistieren.

Fixture-only, stdlib-only (Source-Extraktion analog
``mock_test_earliness_trend_log`` — vermeidet yfinance-Import aus
``backtest_history.py``). Verifiziert:
  (A) Formel gegen bekannte SI-Reihe (relative Änderung über N=3).
  (B) LOOK-AHEAD-KERN: Report mit pub_date > entry_date ausgeschlossen,
      auch wenn settlement_date <= entry_date (der ganze Zweck von #408).
  (C) None-Semantik (zu wenig Reports, fehlende pub_date, si<=0, entry_date=None).
  (D) Zusatz-Randfälle (Grenzwert pub_date == entry_date, custom N).
  (E) Konsumenten-Isolation: kein Score-/Filter-Read — nur Analyse-Persistenz.
  (F) Schema/S10: ``si_velocity_pub`` in S10_OBSERVED_FIELDS, schema=4.
  (G) Integration in ``_build_backtest_extension``-Signatur (entry_date-Kwarg).

Exit-Code 0 = alle Assertions grün; 1 = Fehler mit klarer Meldung.
"""
from __future__ import annotations

import pathlib
import re
import sys
from datetime import date, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Source-Extraktion (statt Import — stdlib-only, kein yfinance) ─────────
src = (ROOT / "backtest_history.py").read_text(encoding="utf-8")


def _extract(func_def: str) -> str:
    pat = rf"^def {re.escape(func_def)}\([\s\S]+?(?=^def\s|^class\s|^# ====)"
    m = re.search(pat, src, re.MULTILINE)
    assert m, f"{func_def} nicht in backtest_history.py gefunden"
    return m.group(0)


ns: dict = {
    "date":     date,
    "datetime": datetime,
}
exec(
    "from config import SI_VELOCITY_PUB_N_REPORTS\n"
    + _extract("_compute_si_velocity_pub"),
    ns,
)
_compute_si_velocity_pub = ns["_compute_si_velocity_pub"]

from config import (  # noqa: E402
    SI_VELOCITY_PUB_N_REPORTS,
    S10_OBSERVED_FIELDS,
)


def _check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ✓ {label}")
        return
    print(f"  ✗ {label}" + (f" — {detail}" if detail else ""))
    sys.exit(1)


# ── (A) Formel-Verifikation gegen bekannte SI-Reihe ────────────────────────
def test_formula_known_series() -> None:
    print("\n(A) Formel-Verifikation (relative Änderung über N=3, gerundet 4)")

    # SI-Reihe (neueste → älteste): 1_500_000 → 1_400_000 → 1_200_000
    # Erwartete velocity: (1_500_000 - 1_200_000) / 1_200_000 = 0.25 exakt.
    history = [
        {"short_interest": 1_500_000, "settlement_date": "2026-06-15", "pub_date": "2026-06-24"},
        {"short_interest": 1_400_000, "settlement_date": "2026-05-31", "pub_date": "2026-06-10"},
        {"short_interest": 1_200_000, "settlement_date": "2026-05-15", "pub_date": "2026-05-27"},
    ]
    entry = date(2026, 7, 1)  # alle 3 pub_dates <= entry
    v = _compute_si_velocity_pub(history, entry)
    _check("A1: (1.5M − 1.2M) / 1.2M = 0.25", v == 0.25, detail=f"got {v!r}")

    # Fallende SI-Reihe: 800k → 900k → 1_000_000.
    history_falling = [
        {"short_interest": 800_000,   "settlement_date": "2026-06-15", "pub_date": "2026-06-24"},
        {"short_interest": 900_000,   "settlement_date": "2026-05-31", "pub_date": "2026-06-10"},
        {"short_interest": 1_000_000, "settlement_date": "2026-05-15", "pub_date": "2026-05-27"},
    ]
    v_falling = _compute_si_velocity_pub(history_falling, entry)
    _check("A2: (800k − 1M) / 1M = −0.2",
           v_falling == -0.2, detail=f"got {v_falling!r}")

    # Rundungs-Fall.
    history_round = [
        {"short_interest": 1_237_500, "settlement_date": "2026-06-15", "pub_date": "2026-06-24"},
        {"short_interest": 1_100_000, "settlement_date": "2026-05-31", "pub_date": "2026-06-10"},
        {"short_interest": 1_000_000, "settlement_date": "2026-05-15", "pub_date": "2026-05-27"},
    ]
    v_round = _compute_si_velocity_pub(history_round, entry)
    _check("A3: 0.2375 nach round(4)", v_round == 0.2375, detail=f"got {v_round!r}")


# ── (B) LOOK-AHEAD-KERNBEWEIS ──────────────────────────────────────────────
def test_look_ahead_pub_date_filter() -> None:
    print("\n(B) LOOK-AHEAD-KERN: pub_date-Filter schließt Reports aus, "
          "deren settlement <= entry_date, deren pub_date aber > entry_date")

    # Szenario: entry_date = 2026-06-05.
    # R_leak: settlement 2026-05-31 (≤ entry ✓), pub_date 2026-06-10 (> entry ✗)
    #   → Am 05.06. war der Wert NICHT öffentlich. Würde er einfließen → Leak.
    # R2/R3/R4 sind sauber publiziert vor entry.
    # Zahlen so gewählt, dass der Leak-Wert deutlich abweicht (Vorzeichen).
    history_with_leak = [
        {"short_interest": 3_000_000, "settlement_date": "2026-05-31",
         "pub_date": "2026-06-10"},  # R_leak — pub NACH entry, MUSS raus
        {"short_interest": 1_400_000, "settlement_date": "2026-05-15",
         "pub_date": "2026-05-27"},  # R2 — eligible
        {"short_interest": 1_300_000, "settlement_date": "2026-04-30",
         "pub_date": "2026-05-11"},  # R3 — eligible
        {"short_interest": 1_200_000, "settlement_date": "2026-04-15",
         "pub_date": "2026-04-24"},  # R4 — eligible
    ]
    entry = date(2026, 6, 5)

    v_with_filter = _compute_si_velocity_pub(history_with_leak, entry)
    # Korrekt: (R2 − R4) / R4 = (1.4M − 1.2M) / 1.2M ≈ 0.1667
    expected_correct = round((1_400_000 - 1_200_000) / 1_200_000, 4)
    _check("B1: pub_date > entry_date-Filter angewandt, korrekt gerechnet",
           v_with_filter == expected_correct,
           detail=f"got {v_with_filter!r}, expected {expected_correct!r} "
                  f"(aus R2/R3/R4, R_leak sauber verworfen)")

    # Explizite Kontrast-Probe: würde der Filter fehlen, käme
    # (R_leak − R3) / R3 ≈ 1.3077 — sehr weit weg.
    leak_value = round((3_000_000 - 1_300_000) / 1_300_000, 4)
    _check("B2: v_with_filter unterscheidet sich stark vom Leak-Wert",
           v_with_filter != leak_value
           and abs(v_with_filter - leak_value) > 1.0,
           detail=f"filter-value={v_with_filter!r}, leak-value={leak_value!r}")

    # Grenzfall: pub_date == entry_date → <= inclusive → eligible bleibt.
    history_boundary = [
        {"short_interest": 2_000_000, "settlement_date": "2026-05-31",
         "pub_date": "2026-06-10"},  # pub EXAKT == entry — MUSS bleiben
        {"short_interest": 1_400_000, "settlement_date": "2026-05-15",
         "pub_date": "2026-05-27"},
        {"short_interest": 1_200_000, "settlement_date": "2026-04-30",
         "pub_date": "2026-05-11"},
    ]
    entry_boundary = date(2026, 6, 10)
    v_boundary = _compute_si_velocity_pub(history_boundary, entry_boundary)
    expected_boundary = round((2_000_000 - 1_200_000) / 1_200_000, 4)
    _check("B3: pub_date == entry_date bleibt eligible (<= ist inclusive)",
           v_boundary == expected_boundary,
           detail=f"got {v_boundary!r}, expected {expected_boundary!r}")

    # Bonus-Fall: Report mit pub_date > entry_date liegt „in der Mitte"
    # der Historie (nicht nur neuester). Muss trotzdem übersprungen werden;
    # Iteration darf NICHT abbrechen.
    history_middle_leak = [
        {"short_interest": 1_400_000, "settlement_date": "2026-05-15",
         "pub_date": "2026-05-27"},  # eligible (neueste)
        {"short_interest": 9_000_000, "settlement_date": "2026-04-30",
         "pub_date": "2026-06-15"},  # Verzögerte Publikation — MUSS raus
        {"short_interest": 1_300_000, "settlement_date": "2026-04-15",
         "pub_date": "2026-04-24"},  # eligible
        {"short_interest": 1_200_000, "settlement_date": "2026-03-31",
         "pub_date": "2026-04-09"},  # eligible
    ]
    v_middle = _compute_si_velocity_pub(history_middle_leak, date(2026, 6, 5))
    expected_middle = round((1_400_000 - 1_200_000) / 1_200_000, 4)
    _check("B4: mittiger Report mit pub_date > entry_date wird "
           "übersprungen (Iteration bricht nicht ab)",
           v_middle == expected_middle,
           detail=f"got {v_middle!r}, expected {expected_middle!r}")


# ── (C) None-Semantik ──────────────────────────────────────────────────────
def test_none_semantics() -> None:
    print("\n(C) None-Semantik STRIKT (keine 0.0-Overload)")

    history_too_few = [
        {"short_interest": 1_500_000, "pub_date": "2026-06-24"},
        {"short_interest": 1_400_000, "pub_date": "2026-06-10"},
    ]
    v_few = _compute_si_velocity_pub(history_too_few, date(2026, 7, 1))
    _check("C1: nur 2 eligible Reports (N=3) → None",
           v_few is None, detail=f"got {v_few!r}")

    history_all_after = [
        {"short_interest": 1_500_000, "pub_date": "2026-06-24"},
        {"short_interest": 1_400_000, "pub_date": "2026-06-10"},
        {"short_interest": 1_200_000, "pub_date": "2026-05-27"},
    ]
    v_after = _compute_si_velocity_pub(history_all_after, date(2026, 4, 1))
    _check("C2: alle pub_dates > entry_date → 0 eligible → None",
           v_after is None, detail=f"got {v_after!r}")

    history_missing_pub = [
        {"short_interest": 1_500_000, "settlement_date": "2026-06-15"},
        {"short_interest": 1_400_000, "settlement_date": "2026-05-31"},
        {"short_interest": 1_200_000, "settlement_date": "2026-05-15"},
    ]
    v_no_pub = _compute_si_velocity_pub(history_missing_pub, date(2026, 7, 1))
    _check("C3: fehlende pub_date-Felder → 0 eligible → None (konservativ)",
           v_no_pub is None, detail=f"got {v_no_pub!r}")

    history_zero_old = [
        {"short_interest": 1_500_000, "pub_date": "2026-06-24"},
        {"short_interest": 1_400_000, "pub_date": "2026-06-10"},
        {"short_interest": 0,         "pub_date": "2026-05-27"},
    ]
    v_zero = _compute_si_velocity_pub(history_zero_old, date(2026, 7, 1))
    _check("C4: si_oldest = 0 → Division-Guard → None",
           v_zero is None, detail=f"got {v_zero!r}")

    v_no_entry = _compute_si_velocity_pub(
        [{"short_interest": 100, "pub_date": "2026-06-01"}] * 3, None)
    _check("C5: entry_date = None → None",
           v_no_entry is None, detail=f"got {v_no_entry!r}")

    _check("C6: finra_history = None → None",
           _compute_si_velocity_pub(None, date(2026, 7, 1)) is None)
    _check("C7: finra_history = [] → None",
           _compute_si_velocity_pub([], date(2026, 7, 1)) is None)


# ── (D) Zusatz-Randfälle ───────────────────────────────────────────────────
def test_extra_edge_cases() -> None:
    print("\n(D) Zusatz-Randfälle")

    history = [
        {"short_interest": 1_200_000, "pub_date": "2026-06-24"},
        {"short_interest": 1_000_000, "pub_date": "2026-06-10"},
    ]
    v = _compute_si_velocity_pub(history, date(2026, 7, 1), n_reports=2)
    _check("D1: n_reports=2 override → (1.2M − 1M) / 1M = 0.2",
           v == 0.2, detail=f"got {v!r}")

    v_bad = _compute_si_velocity_pub(history, date(2026, 7, 1), n_reports=1)
    _check("D2: n_reports=1 → None (keine Rate)",
           v_bad is None, detail=f"got {v_bad!r}")

    history_garbage = [
        {"short_interest": 1_500_000, "pub_date": "not-a-date"},
        {"short_interest": 1_400_000, "pub_date": "2026-06-10"},
        {"short_interest": 1_300_000, "pub_date": "2026-05-27"},
        {"short_interest": 1_200_000, "pub_date": "2026-05-11"},
    ]
    v_garbage = _compute_si_velocity_pub(history_garbage, date(2026, 7, 1))
    expected = round((1_400_000 - 1_200_000) / 1_200_000, 4)
    _check("D3: kaputte pub_date-Strings still übersprungen",
           v_garbage == expected,
           detail=f"got {v_garbage!r}, expected {expected!r}")


# ── (E) Konsumenten-Isolation ──────────────────────────────────────────────
def test_consumer_isolation() -> None:
    print("\n(E) Konsumenten-Isolation — si_velocity_pub nirgends in "
          "Score/Filter/Push")

    # Namens-Disambiguation: das ältere Display-Feld ``si_velocity`` (ohne
    # ``_pub``-Suffix) existiert bewusst in ``generate_report.py`` (~90-Tage-
    # FINRA-History, absolute Shares/Tag, kein pub_date-Filter). Es bleibt
    # unangetastet. Die Konsumenten-Isolation für PR-3 prüft ausschließlich,
    # dass ``si_velocity_pub`` (Wort-Grenzen strikt) und ``_compute_si_
    # velocity_pub`` NIRGENDS außerhalb des Backtest-Persist-Pfads gelesen
    # werden — sonst wäre der Look-Ahead-freie Analyse-Wert versehentlich
    # ins Live-System geleakt.
    for fname in ("generate_report.py", "ki_agent.py", "health_check.py"):
        p = ROOT / fname
        if not p.exists():
            continue
        src_c = p.read_text(encoding="utf-8")
        for pat in (r"_compute_si_velocity_pub\s*\(",
                    r'["\']si_velocity_pub["\']'):
            hits = re.findall(pat, src_c)
            _check(f"E: {fname} enthält keine {pat!r}-Reads",
                   not hits, detail=f"gefunden: {hits}")


# ── (F) Schema/S10 ─────────────────────────────────────────────────────────
def test_schema_and_s10() -> None:
    print("\n(F) Schema-Konformität + S10-Whitelist")

    _check("F1: si_velocity_pub in S10_OBSERVED_FIELDS",
           "si_velocity_pub" in S10_OBSERVED_FIELDS)

    from config import S10_MUSS_FIELDS, S10_LAG_FIELDS
    _check("F2: si_velocity_pub NICHT in S10_MUSS_FIELDS (LEGITIM leer)",
           "si_velocity_pub" not in S10_MUSS_FIELDS)
    _check("F3: si_velocity_pub NICHT in S10_LAG_FIELDS",
           "si_velocity_pub" not in S10_LAG_FIELDS)

    _check("F4: SI_VELOCITY_PUB_N_REPORTS Konstante existiert und = 3",
           SI_VELOCITY_PUB_N_REPORTS == 3,
           detail=f"got {SI_VELOCITY_PUB_N_REPORTS!r}")

    # Schema bleibt 4 — kein Bump.
    schema_lines = [ln for ln in src.splitlines()
                    if '"backtest_schema_version"' in ln]
    _check("F5: backtest_schema_version bleibt 4 (kein v4→v5-Bump)",
           any(": 4," in ln for ln in schema_lines),
           detail=f"schema_lines={schema_lines}")


# ── (G) Signatur-Integration ───────────────────────────────────────────────
def test_signature_integration() -> None:
    print("\n(G) _build_backtest_extension nimmt entry_date-Kwarg")

    # Signatur per Regex prüfen (Source-Inspektion — kein Import).
    m = re.search(
        r"def _build_backtest_extension\(([\s\S]+?)\) -> dict:",
        src,
    )
    _check("G1: _build_backtest_extension-Signatur gefunden",
           m is not None)
    sig_body = m.group(1)
    _check("G2: entry_date-Kwarg im Signatur-Body",
           "entry_date" in sig_body,
           detail=f"sig={sig_body!r}")
    _check("G3: entry_date-Default ist None (fail-soft)",
           re.search(r"entry_date\s*:[^=]+=\s*None", sig_body) is not None,
           detail=f"sig={sig_body!r}")

    # Aufrufstelle nutzt entry_date=_rd (report_date-Parse).
    _check("G4: _build_backtest_extension-Aufruf reicht entry_date=_rd durch",
           "entry_date=_rd," in src,
           detail="Aufrufstelle in _append_backtest_entries erwartet")

    # Look-Ahead-Konvention im Docstring einfriert.
    src_norm = " ".join(src.split())
    _check("G5: Look-Ahead-Konvention im Helper-Docstring einfriert",
           "NIEMALS als Score-Feature" in src_norm
           and "pub_date <= entry_date" in src_norm)


def main() -> int:
    print("=" * 66)
    print("Mock-Test: si_velocity_pub (PR-3, pub_date-Look-Ahead-Filter)")
    print("=" * 66)
    test_formula_known_series()
    test_look_ahead_pub_date_filter()
    test_none_semantics()
    test_extra_edge_cases()
    test_consumer_isolation()
    test_schema_and_s10()
    test_signature_integration()
    print()
    print("✓ Alle Tests bestanden (Formel + LOOK-AHEAD-KERNBEWEIS + None-"
          "Semantik + Randfälle + Konsumenten-Isolation + Schema/S10 + "
          "Signatur-Integration).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
