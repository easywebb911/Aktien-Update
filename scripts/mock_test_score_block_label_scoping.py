"""Mock-Tests fuer .sb-lbl CSS-Spezifitaets-Scoping (16.05.2026).

Hintergrund: Konfidenz-Methodik-Tabelle zeigte Overlap zwischen Score-
Klassen-Labels (Setup, Earliness V2, ...) und farbigen Konfidenz-Dots
(🟢 🟡 🟠 🔴). Auf iPhone bei groesserer Schrift unlesbar.

Diagnose: Zwei .sb-lbl-Definitionen mit identischer Spezifitaet (0,1,0):
- Z. 323: .sb-lbl{flex:1;min-width:0}              -> Methodik-Tabelle
- Z. 1054: .sb-lbl{font-size:.58rem; uppercase ...} -> Karten-Score-Block
Z. 1054 stand spaeter -> gewann fuer Methodik-Tabelle -> Labels wurden
tiny+uppercase+letter-spaced+dim, kollidierten visuell mit farbigem Dot
in .sb-pts.

Fix: Z. 1054-Selektor von .sb-lbl auf .sb-row .sb-lbl gescoped.
Spezifitaet (0,2,0) > (0,1,0); greift jetzt nur noch im Score-Block-
Container (Top-10-Karten, immer in .sb-row gewrappt).

Tests:
  1. .sb-row .sb-lbl-Selektor existiert (gescoped)
  2. Z. 323 .sb-lbl-Regel weiterhin vorhanden (Methodik-Tabelle)
  3. Keine doppelte nackte .sb-lbl-Definition mehr (Regression-Schutz)
  4. .score-block-list .sb-note-Regel hinzugefuegt
  5. .sb-note Properties korrekt (flex, text-align, color, font-size)
  6. Score-Block-Properties (uppercase / letter-spacing) noch im Source
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HJ = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")


def test_01_sb_row_lbl_scoped_exists() -> None:
    assert ".sb-row .sb-lbl{" in HJ, \
        ".sb-row .sb-lbl-Selektor fehlt (Scoping-Fix nicht angewandt)"


def test_02_methodik_sb_lbl_rule_preserved() -> None:
    # Z. 323-Regel (Methodik-Tabelle) muss erhalten bleiben
    assert ".sb-lbl{flex:1;min-width:0}" in HJ, \
        "Methodik-Tabellen .sb-lbl-Regel (flex:1) entfernt"


def test_03_no_duplicate_bare_sb_lbl() -> None:
    # Regression-Schutz: nur EINE nackte .sb-lbl{...}-Definition (Z. 323)
    # Pattern findet '.sb-lbl{' am Zeilenanfang ohne Eltern-Selektor
    bare_definitions = [
        m for m in re.finditer(r"(?m)^\.sb-lbl\{", HJ)
    ]
    assert len(bare_definitions) == 1, \
        f"Erwartet 1 nackte .sb-lbl-Definition, gefunden {len(bare_definitions)}"


def test_04_sb_note_rule_added() -> None:
    assert ".score-block-list .sb-note{" in HJ, \
        ".score-block-list .sb-note-Regel fehlt"


def test_05_sb_note_properties_correct() -> None:
    idx = HJ.find(".score-block-list .sb-note{")
    assert idx > 0
    block = HJ[idx:idx + 200]
    # Erwartete Properties laut Spec
    assert "flex:1 1 auto" in block, "sb-note: flex:1 1 auto fehlt"
    assert "min-width:0" in block, "sb-note: min-width:0 fehlt"
    assert "text-align:right" in block, "sb-note: text-align:right fehlt"
    assert "color:var(--txt-dim)" in block, "sb-note: color:var(--txt-dim) fehlt"
    assert "font-size:.72rem" in block, "sb-note: font-size:.72rem fehlt"


def test_06_score_block_props_still_present() -> None:
    # Karten-Score-Block-Optik unveraendert: gleiche Properties,
    # nur Selektor geaendert
    idx = HJ.find(".sb-row .sb-lbl{")
    assert idx > 0
    block = HJ[idx:idx + 250]
    assert "font-size:.58rem" in block, "Score-Block: .58rem entfernt"
    assert "text-transform:uppercase" in block, "Score-Block: uppercase entfernt"
    assert "letter-spacing:.4px" in block, "Score-Block: letter-spacing entfernt"
    assert "font-weight:700" in block, "Score-Block: font-weight:700 entfernt"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 .sb-row .sb-lbl-Scoping existiert",     test_01_sb_row_lbl_scoped_exists),
        ("02 Methodik .sb-lbl (Z. 323) erhalten",    test_02_methodik_sb_lbl_rule_preserved),
        ("03 Keine doppelte nackte .sb-lbl-Reg.",    test_03_no_duplicate_bare_sb_lbl),
        ("04 .sb-note-Regel hinzugefuegt",           test_04_sb_note_rule_added),
        ("05 .sb-note Properties korrekt",           test_05_sb_note_properties_correct),
        ("06 Score-Block-Properties erhalten",       test_06_score_block_props_still_present),
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
