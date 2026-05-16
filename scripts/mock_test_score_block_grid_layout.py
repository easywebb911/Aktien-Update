"""Mock-Tests fuer Methodik-Listen Grid-Layout-Restrukturierung (16.05.2026).

Hintergrund: PR #185 schaerfte den .sb-lbl-Selektor (Spezifitaets-Fix),
behob aber den iPhone-Layout-Bug NICHT. Wahre Ursache war Flexbox-Math:
.sb-lbl mit flex:1 (flex-basis:0) bekam in oversubscribed Container
0 px Slack, Browser wickelte Label-Text zeichenweise neben Pts-Span.
Visuelles Symptom: „Surobust" / „Emittel" / „KIheuristisch".

Fix (PR-Folge zu #185): .score-block-list li von Flex auf CSS-Grid
umgestellt. 2-Row-Layout: [label][pts] in Row 1, [note] full-width
in Row 2. Label-Spalte ist minmax(0, 1fr), Pts-Spalte ist max-content
(schrumpft nicht).

Tests:
  1. .score-block-list li hat display:grid (nicht mehr flex)
  2. grid-template-areas enthaelt "label pts" und "note note"
  3. grid-template-columns ist minmax(0, 1fr) max-content
  4. .sb-lbl hat grid-area:label
  5. .sb-pts hat grid-area:pts
  6. .sb-note hat grid-area:note
  7. .sb-note text-align ist left (nicht right wie in PR #185)
  8. .sb-lbl hat KEIN flex-basis:0 / flex:1 mehr (Regression-Schutz)
  9. .sb-note hat KEIN flex:1 1 auto mehr (PR-#185-Rollback)
 10. align-items:baseline erhalten
 11. column-gap:8px (vorher gap:8px im Flex)
 12. Karten-Score-Block (.sb-row .sb-lbl) unberuehrt
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HJ = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")


def _block(start_marker: str, span: int = 400) -> str:
    idx = HJ.find(start_marker)
    assert idx > 0, f"{start_marker!r} nicht gefunden"
    return HJ[idx:idx + span]


def test_01_li_uses_grid_not_flex() -> None:
    block = _block(".score-block-list li{")
    # Charakteristischer Start mit display:grid
    assert "display:grid" in block, \
        ".score-block-list li nicht auf display:grid umgestellt"
    # Kein display:flex mehr im li-Block
    end = block.find("}")
    li_rule = block[:end]
    assert "display:flex" not in li_rule, \
        ".score-block-list li hat noch display:flex"


def test_02_grid_template_areas() -> None:
    block = _block(".score-block-list li{")
    # 2-Row-Layout: label pts in Row 1, note span 2 cols in Row 2
    assert '"label pts"' in block, "grid-template-areas: label pts fehlt"
    assert '"note note"' in block, "grid-template-areas: note note fehlt"


def test_03_grid_template_columns() -> None:
    block = _block(".score-block-list li{")
    assert "minmax(0, 1fr) max-content" in block, \
        "grid-template-columns nicht minmax(0, 1fr) max-content"


def test_04_sb_lbl_grid_area_label() -> None:
    # .sb-lbl{...} (nackt, Methodik-Tabelle)
    idx = re.search(r"(?m)^\.sb-lbl\{", HJ)
    assert idx is not None, ".sb-lbl-Definition (Methodik) nicht gefunden"
    block = HJ[idx.start():idx.start() + 200]
    assert "grid-area:label" in block, ".sb-lbl ohne grid-area:label"
    assert "min-width:0" in block, ".sb-lbl ohne min-width:0"


def test_05_sb_pts_grid_area_pts() -> None:
    idx = re.search(r"(?m)^\.sb-pts\{", HJ)
    assert idx is not None
    block = HJ[idx.start():idx.start() + 200]
    assert "grid-area:pts" in block, ".sb-pts ohne grid-area:pts"


def test_06_sb_note_grid_area_note() -> None:
    block = _block(".score-block-list .sb-note{")
    assert "grid-area:note" in block, ".sb-note ohne grid-area:note"


def test_07_sb_note_text_align_left() -> None:
    block = _block(".score-block-list .sb-note{")
    assert "text-align:left" in block, \
        ".sb-note text-align nicht left (sollte left fuer Grid-Vollbreite)"
    assert "text-align:right" not in block, \
        ".sb-note text-align:right noch da (PR #185-Rollback fehlt)"


def test_08_sb_lbl_no_flex_basis_zero() -> None:
    # Regression-Schutz: Pathologie war flex:1 mit basis 0%
    idx = re.search(r"(?m)^\.sb-lbl\{", HJ)
    assert idx is not None
    block = HJ[idx.start():idx.start() + 200]
    end = block.find("}")
    rule = block[:end]
    # Weder die Shorthand flex:1 noch explizite Basis 0%
    assert "flex:1" not in rule, ".sb-lbl hat noch flex:1 (Pathologie-Regression)"
    assert "flex-basis:0" not in rule, ".sb-lbl hat noch flex-basis:0"


def test_09_sb_note_no_flex_grow() -> None:
    # PR #185 hatte flex:1 1 auto auf .sb-note — rollback im Grid-Layout
    block = _block(".score-block-list .sb-note{")
    end = block.find("}")
    rule = block[:end]
    assert "flex:1" not in rule, \
        ".sb-note hat noch flex:1 ... (PR #185-Rollback fehlt)"


def test_10_align_items_baseline_preserved() -> None:
    block = _block(".score-block-list li{")
    assert "align-items:baseline" in block, \
        "align-items:baseline entfernt — Pts-Vertikal-Alignment kaputt"


def test_11_column_gap_8px() -> None:
    block = _block(".score-block-list li{")
    assert "column-gap:8px" in block, "column-gap:8px fehlt"
    assert "row-gap:2px" in block, "row-gap:2px fehlt (minimale Row-Spacing)"


def test_12_card_score_block_untouched() -> None:
    # .sb-row .sb-lbl-Regel aus PR #185 weiterhin intakt
    assert ".sb-row .sb-lbl{" in HJ, \
        ".sb-row .sb-lbl-Scoping aus PR #185 entfernt"
    idx = HJ.find(".sb-row .sb-lbl{")
    block = HJ[idx:idx + 250]
    # Karten-Score-Block-Properties unveraendert
    assert "font-size:.58rem" in block
    assert "text-transform:uppercase" in block
    assert "letter-spacing:.4px" in block


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 li display:grid (nicht flex)",          test_01_li_uses_grid_not_flex),
        ("02 grid-template-areas korrekt",           test_02_grid_template_areas),
        ("03 grid-template-columns korrekt",         test_03_grid_template_columns),
        ("04 .sb-lbl grid-area:label",                test_04_sb_lbl_grid_area_label),
        ("05 .sb-pts grid-area:pts",                  test_05_sb_pts_grid_area_pts),
        ("06 .sb-note grid-area:note",                test_06_sb_note_grid_area_note),
        ("07 .sb-note text-align:left",               test_07_sb_note_text_align_left),
        ("08 .sb-lbl ohne flex:1 (Regression)",       test_08_sb_lbl_no_flex_basis_zero),
        ("09 .sb-note ohne flex:1 (PR-#185-Rollback)", test_09_sb_note_no_flex_grow),
        ("10 align-items:baseline erhalten",          test_10_align_items_baseline_preserved),
        ("11 column-gap:8px + row-gap:2px",           test_11_column_gap_8px),
        ("12 Karten-Score-Block unveraendert",        test_12_card_score_block_untouched),
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
