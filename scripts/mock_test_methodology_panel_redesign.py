"""Mock-Tests fuer Methodik-Panel Accordion-Refactor (16.05.2026).

Hintergrund: Methodik-Panel war ~3500 px lang auf Mobile. Refactor:
12 info-box-Sektionen (11 Original + Karten-Legende A2) werden zu
<details class="info-box methodology-card">-Elementen. Konfidenz
default-open, Rest closed mit Lead-Kernaussage und Caret-Icon.

Tests:
  1. Source: 12 <details class="info-box ... methodology-card">-Tags
     im Methodik-Panel
  2. Source: Konfidenz hat open-Attribut
  3. Source: alle anderen 11 haben kein open-Attribut
  4. Source: Lead-Spans vorhanden fuer alle 12 Sektionen
  5. Source: jede Sektion hat <summary>, <h4> in summary,
     <method-caret>, <method-content>
  6. Source: bestehende Score-Inhalte (Filterkriterien, Score-Formel,
     Conviction-Komponenten, Konfidenz-Rows) sind erhalten
  7. CSS: details.methodology-card-Klassen in head.jinja
  8. CSS: caret-rotation bei [open]
  9. CSS: min-height >= 44px (Mobile Tap-Target)
 10. Source: Section-ID #methodology-section bleibt
 11. Source: bestehende ki-pro-details (Sektion 8) bleibt verschachtelt
 12. Source: methodology-intro vor erstem details
 13. CLAUDE.md: Methodik-Panel-Redesign-Hinweis
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
HJ = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def _methodology_block() -> str:
    """Extrahiert den Methodik-Panel-HTML-Block."""
    start = GR.find('<section class="info-panel" id="methodology-section"')
    assert start > 0
    end = GR.find("</section>", start)
    assert end > start
    return GR[start:end]


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_01_eleven_details_present() -> None:
    block = _methodology_block()
    # 12 details-Tags mit methodology-card (11 Original + Karten-Legende A2)
    matches = re.findall(r'<details class="info-box[^"]*methodology-card', block)
    assert len(matches) == 12, \
        f"Erwarte 12 details-Tags, gefunden {len(matches)}"


def test_02_konfidenz_default_open() -> None:
    block = _methodology_block()
    # Genau 1 details hat open-Attribut
    open_matches = re.findall(r'<details class="info-box[^"]*methodology-card" open>', block)
    assert len(open_matches) == 1, \
        f"Erwarte genau 1 default-open, gefunden {len(open_matches)}"
    # Und es ist die Konfidenz-Sektion: open-tag muss vor <h4>Konfidenz auftauchen
    # Finde Konfidenz-h4-Position
    konf_pos = block.find("<h4>Konfidenz der Scores</h4>")
    assert konf_pos > 0, "Konfidenz-h4 nicht gefunden"
    # Suche nach details-tag direkt vor dem h4 (innerhalb summary)
    before = block[:konf_pos]
    last_details = before.rfind("<details")
    assert last_details > 0
    details_open = block[last_details:konf_pos]
    assert 'methodology-card" open>' in details_open, \
        "Konfidenz-Sektion hat kein open-Attribut"


def test_03_others_not_open() -> None:
    # Inverse: 11 details ohne open + 1 mit open (Karten-Legende A2 default-closed)
    block = _methodology_block()
    closed = re.findall(r'<details class="info-box[^"]*methodology-card">', block)
    assert len(closed) == 11, \
        f"Erwarte 11 default-closed, gefunden {len(closed)}"


def test_04_lead_spans_present() -> None:
    block = _methodology_block()
    leads = re.findall(r'<span class="method-lead">', block)
    assert len(leads) == 12, \
        f"Erwarte 12 method-lead-Spans, gefunden {len(leads)}"


def test_05_summary_structure() -> None:
    block = _methodology_block()
    # 12 outer methodology-card-summary + 1 verschachteltes ki-pro-details-
    # summary (Sektion 8) = 13 total
    assert block.count("<summary>") == 13, \
        f"Erwarte 13 summary-Tags (12 outer + 1 ki-pro-details), gefunden {block.count('<summary>')}"
    assert block.count("</summary>") == 13
    # 12 outer caret-Icons (ki-pro-details hat keine method-caret)
    assert block.count('class="method-caret"') == 12
    # 12 method-content divs
    assert block.count('class="method-content"') == 12


def test_06_existing_score_content_preserved() -> None:
    # Bestehende Score-Methodik-Auto-Generated Rows bleiben
    block = _methodology_block()
    assert "{methodology_struct_rows}" in block, "Struct-Rows fehlen"
    assert "{methodology_catalyst_rows}" in block, "Katalysator-Rows fehlen"
    assert "{methodology_timing_rows}" in block, "Timing-Rows fehlen"
    assert "{score_confidence_rows_html}" in block, "Konfidenz-Rows fehlen"
    # Conviction-Komponenten
    assert "<li><span class=\"sb-lbl\">Setup</span><span class=\"sb-pts\">max 33 Pkt</span>" in block
    assert "<li><span class=\"sb-lbl\">Earliness</span><span class=\"sb-pts\">max 28 Pkt</span>" in block


def test_07_css_classes_in_head_jinja() -> None:
    # Alle relevanten CSS-Klassen / Selektoren
    for needle in (
        "details.methodology-card",
        ".method-lead",
        ".method-caret",
        ".method-content",
        ".methodology-intro",
    ):
        assert needle in HJ, f"CSS-Klasse/-Selektor {needle} fehlt"
    # Summary-Styling: details.methodology-card>summary (Selektor)
    assert "methodology-card>summary" in HJ, \
        "summary-Styling-Selektor fehlt"


def test_08_caret_rotation_on_open() -> None:
    assert ("[open]" in HJ and ".method-caret" in HJ and
            "rotate(180deg)" in HJ), \
        "Caret-Rotation bei [open] fehlt"


def test_09_min_height_44px() -> None:
    # Tap-Target 44px auf Mobile
    assert "min-height:44px" in HJ or "min-height: 44px" in HJ, \
        "Mobile Tap-Target min-height 44px fehlt"


def test_10_section_id_preserved() -> None:
    assert '<section class="info-panel" id="methodology-section"' in GR, \
        "methodology-section-ID entfernt"


def test_11_ki_pro_details_nested_preserved() -> None:
    # Sektion 8 (KI-Agent) hat weiterhin ki-pro-details als verschachteltes
    # Accordion fuer Profi-Details
    block = _methodology_block()
    ki_pos = block.find("<h4>⚡ KI-Agent</h4>")
    assert ki_pos > 0
    # ki-pro-details muss noch im methodology-content auftauchen
    ki_section = block[ki_pos:ki_pos + 6000]
    assert 'details class="ki-pro-details"' in ki_section, \
        "Verschachtelte ki-pro-details fehlt"


def test_12_intro_above_first_details() -> None:
    block = _methodology_block()
    intro_pos = block.find('class="methodology-intro"')
    first_details = block.find('<details class="info-box')
    assert intro_pos > 0, "methodology-intro fehlt"
    assert intro_pos < first_details, \
        "methodology-intro nicht vor erstem details"


def test_13_claude_md_redesign_note() -> None:
    # CLAUDE.md erwaehnt Accordion-Redesign
    assert ("methodology-card" in CMD or
            "<details>" in CMD or
            "Accordion" in CMD or
            "Aufklapp" in CMD), \
        "CLAUDE.md erwaehnt Methodik-Accordion nicht"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 12 details mit methodology-card",          test_01_eleven_details_present),
        ("02 Konfidenz default-open",                   test_02_konfidenz_default_open),
        ("03 Andere 11 default-closed",                 test_03_others_not_open),
        ("04 Lead-Spans alle 12",                       test_04_lead_spans_present),
        ("05 Summary-Struktur",                         test_05_summary_structure),
        ("06 Existing Score-Inhalte erhalten",          test_06_existing_score_content_preserved),
        ("07 CSS-Klassen in head.jinja",                test_07_css_classes_in_head_jinja),
        ("08 Caret-Rotation bei [open]",                test_08_caret_rotation_on_open),
        ("09 min-height 44px (Mobile Tap-Target)",      test_09_min_height_44px),
        ("10 Section-ID erhalten",                      test_10_section_id_preserved),
        ("11 ki-pro-details verschachtelt erhalten",    test_11_ki_pro_details_nested_preserved),
        ("12 methodology-intro vor erstem details",     test_12_intro_above_first_details),
        ("13 CLAUDE.md Redesign-Hinweis",               test_13_claude_md_redesign_note),
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
