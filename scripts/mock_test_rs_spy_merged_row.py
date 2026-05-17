"""Mock-Tests fuer RS-vs-SPY zusammengefuehrte Detail-Zeile (17.05.2026).

Hintergrund: Detail-Sektion zeigte zwei Zeilen mit identischem Wert
für relative Staerke:
- "Rel. Staerke (20T) -11.3% vs. S&P 500 (Aktie -7.3%)"
- "RS vs. SPY (20T) -11.3% (-3 Pkt)"

Beide lasen denselben Datenpunkt rel_strength_20d. Easy hat die
Doppelung bemerkt. Fix: eine Zeile vereint Prozent + Standalone-
Perf + Punkte-Beitrag.

Tests:
  1. _rs_spy_row_html mit perf_20d rendert Aktie-Klammer
  2. _rs_spy_row_html ohne perf_20d rendert nur Punkte-Klammer
  3. _rs_spy_row_html rs_pct=None -> leerer String
  4. Label "RS vs. SPY (20T)" vorhanden
  5. Vorzeichen-Format korrekt (+/-)
  6. Punkte-Format korrekt ("-3 Pkt", "+3 Pkt", "0 Pkt")
  7. Source: alte _rs_row-Variable nicht mehr in generate_report.py
  8. Source: alte "Rel. Staerke (20T)"-Inline-Render nicht mehr da
  9. Source: orphaned _rs20/_p20-Variable im Card-Builder weg
 10. momentum_rows-Konkatenation enthaelt nur _rs_spy_row_ (nicht _rs_row)
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR_TEXT = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _load_helper():
    """Lade nur _rs_spy_row_html + _rs_spy_pts ohne yfinance-Import-Abhaengigkeit.

    Trick: extrahiere die zwei Funktionen direkt aus dem Source-Text und
    fuehre sie in einem isolierten namespace aus.
    """
    ns = {}
    # Minimal-Konstante fuer _rs_spy_pts
    ns["RS_SPY_THRESHOLD_PCT"] = 5.0
    ns["RS_SPY_PTS_MAX"] = 3

    def _extract(name: str) -> str:
        pat = re.compile(rf"^def {name}\(.*?(?=^def |\Z)", re.MULTILINE | re.DOTALL)
        m = pat.search(GR_TEXT)
        assert m, f"{name} nicht gefunden"
        return m.group(0)

    code = _extract("_rs_spy_pts") + "\n" + _extract("_rs_spy_row_html")
    exec(code, ns)
    return ns["_rs_spy_row_html"]


_rs_spy_row_html = _load_helper()


# ── Funktional ──────────────────────────────────────────────────────────────

def test_01_with_perf_20d_renders_aktie_clause() -> None:
    out = _rs_spy_row_html({"rel_strength_20d": -11.3, "perf_20d": -7.3})
    assert "Aktie -7.3%" in out, f"Aktie-Klammer fehlt: {out!r}"
    assert "-3 Pkt" in out, f"Punkte-Beitrag fehlt: {out!r}"


def test_02_without_perf_20d_only_pts_clause() -> None:
    out = _rs_spy_row_html({"rel_strength_20d": 4.5, "perf_20d": None})
    assert "Aktie" not in out, f"Aktie-Klammer faelschlich da: {out!r}"
    # Punkte-Beitrag weiterhin vorhanden
    assert "Pkt" in out, f"Punkte-Klammer fehlt: {out!r}"


def test_03_rs_pct_none_returns_empty() -> None:
    out = _rs_spy_row_html({"rel_strength_20d": None, "perf_20d": -3.0})
    assert out == "", f"Erwartet leerer String, bekam: {out!r}"


def test_04_label_present() -> None:
    out = _rs_spy_row_html({"rel_strength_20d": 2.5, "perf_20d": 5.0})
    assert "<td>RS vs. SPY (20T)</td>" in out, "Label fehlt"


def test_05_signed_format() -> None:
    out_pos = _rs_spy_row_html({"rel_strength_20d": 7.2, "perf_20d": 10.0})
    assert "+7.2%" in out_pos, f"Positives Vorzeichen fehlt: {out_pos!r}"
    out_neg = _rs_spy_row_html({"rel_strength_20d": -2.0, "perf_20d": -1.0})
    assert "-2.0%" in out_neg, f"Negatives Vorzeichen fehlt: {out_neg!r}"


def test_06_pts_format() -> None:
    # Negative
    out = _rs_spy_row_html({"rel_strength_20d": -11.3, "perf_20d": -7.3})
    assert "-3 Pkt" in out
    # Positive
    out = _rs_spy_row_html({"rel_strength_20d": 5.0, "perf_20d": 10.0})
    assert "+3 Pkt" in out
    # Zero (rs=0 -> pts=0)
    out = _rs_spy_row_html({"rel_strength_20d": 0.0, "perf_20d": 0.0})
    assert "0 Pkt" in out


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_07_old_rs_row_variable_removed() -> None:
    # Die Variable _rs_row darf nicht mehr im Code vorkommen
    # (war Trigger fuer die alte "Rel. Staerke (20T)"-Zeile)
    assert "_rs_row" not in GR_TEXT, \
        "_rs_row-Variable noch in generate_report.py (alte Doppel-Anzeige)"


def test_08_old_inline_render_removed() -> None:
    # Inline-Render-Block der alten Zeile darf nicht mehr da sein
    assert "<td>Rel. Stärke (20T)</td>" not in GR_TEXT, \
        "Alter Inline-Render '<td>Rel. Stärke (20T)</td>' noch im Source"
    # Inline-Span "vs. S&P 500" war Teil der alten Zeile
    assert "% vs. S&amp;P 500" not in GR_TEXT, \
        "Alter Inline-Span 'vs. S&P 500' noch im Source"


def test_09_orphaned_locals_removed() -> None:
    # _rs20 und _p20 waren lokale Variablen im Card-Builder, die nur
    # vom alten _rs_row-Block gelesen wurden. Nach Cleanup sind sie
    # ausserhalb des Helpers nicht mehr noetig.
    # Akzeptabel: _p20 = stock.get("perf_20d") IM Helper _rs_spy_row_html.
    occurrences = re.findall(r"\b_p20\s*=", GR_TEXT)
    # Genau 1 Vorkommen (im Helper)
    assert len(occurrences) == 1, \
        f"Erwartet 1 _p20-Assignment (im Helper), gefunden {len(occurrences)}"
    occurrences_rs20 = re.findall(r"\b_rs20\s*=", GR_TEXT)
    assert len(occurrences_rs20) == 0, \
        f"_rs20-Variable noch im Source: {len(occurrences_rs20)} Vorkommen"


def test_10_momentum_rows_concatenation_clean() -> None:
    # Beide momentum_rows-Konkatenationen (v1 + v2) duerfen kein
    # + _rs_row mehr enthalten — nur noch _rs_spy_row_ / rs_spy_row.
    for line in GR_TEXT.splitlines():
        if "momentum_rows =" in line and "_rsi_row" in line:
            assert "_rs_row" not in line, \
                f"momentum_rows enthaelt noch _rs_row: {line.strip()}"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 Mit perf_20d -> Aktie-Klammer",       test_01_with_perf_20d_renders_aktie_clause),
        ("02 Ohne perf_20d -> nur Punkte",         test_02_without_perf_20d_only_pts_clause),
        ("03 rs_pct=None -> leerer String",        test_03_rs_pct_none_returns_empty),
        ("04 Label 'RS vs. SPY (20T)'",             test_04_label_present),
        ("05 Vorzeichen-Format korrekt",            test_05_signed_format),
        ("06 Punkte-Format (-3/+3/0)",              test_06_pts_format),
        ("07 _rs_row-Variable entfernt",            test_07_old_rs_row_variable_removed),
        ("08 Alter Inline-Render entfernt",         test_08_old_inline_render_removed),
        ("09 Orphan _rs20/_p20-Locals weg",         test_09_orphaned_locals_removed),
        ("10 momentum_rows ohne _rs_row",           test_10_momentum_rows_concatenation_clean),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
        except AssertionError as exc:
            print(f"  FAIL {name}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
            failed += 1
    print()
    print(f"Total: {len(tests)} | Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
