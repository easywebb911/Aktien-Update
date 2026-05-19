"""Mock-Tests fuer Setup-Score Cursor-Removal + Agent-Dot Tooltip (17.05.2026).

Hintergrund: Easy verwirrt durch zwei UX-Inkonsistenzen:
1. cursor:pointer auf Setup-Score-Zahl ohne Click-Handler (tote CSS-
   Reste aus frueherer Quick-Sort-Funktionalitaet).
2. agent-dot neben Ticker-Name vs quote-live-dot ueber Setup-Score —
   unterschiedliche Dot-Typen, keine Erklaerung.

Loesung: tote CSS-Regeln entfernen + Tooltip auf agent-dot ergaenzen.

Tests:
  1. .sb-row[data-sb="setup"] .sb-num{cursor:pointer} nicht mehr da
  2. :hover/:focus-visible-Regeln fuer Setup-sb-num auch weg
  3. .sb-num-Grundregel (font-size etc.) erhalten
  4. agent-dot bekommt title-Attribut in renderAgentSignals
  5. Andere sb-num-Selektoren (Sort-Mode-Cursor etc.) unberuehrt
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HJ = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def test_01_setup_sb_num_cursor_pointer_removed() -> None:
    assert '.sb-row[data-sb="setup"] .sb-num{cursor:pointer}' not in HJ, \
        "Tote cursor:pointer-Regel auf Setup-Score noch in head.jinja"


def test_02_setup_sb_num_hover_focus_removed() -> None:
    # Die Hover/Focus-visible-Regeln fuer Setup waren nur fuer das
    # historische Click-Pattern noetig — auch entfernen.
    assert '.sb-row[data-sb="setup"] .sb-num:hover' not in HJ, \
        ":hover-Regel auf Setup-sb-num noch da (war Click-Pattern-Rest)"
    assert '.sb-row[data-sb="setup"] .sb-num:focus-visible' not in HJ, \
        ":focus-visible-Regel auf Setup-sb-num noch da"


def test_03_sb_num_base_rule_preserved() -> None:
    # Die generelle .sb-num-Regel (font-size:22px etc.) muss erhalten
    # bleiben — nur die Setup-spezifischen Cursor-Reste sind weg.
    assert ".sb-num{font-weight:400" in HJ and "font-size:22px" in HJ, \
        ".sb-num-Grundregel (font-size etc.) beschaedigt"


def test_04_agent_dot_has_title_attribute() -> None:
    # renderAgentSignals soll dot.title setzen — klaert die Dot-
    # Inkonsistenz fuer Easy
    assert "dot.title" in GR, "agent-dot bekommt kein title-Attribut"
    # Title-Text soll KI-Status erklaeren
    assert "KI-Status" in GR or "KI-Score-Tier" in GR, \
        "agent-dot title-Text erwaehnt nicht KI-Status"


def test_05_other_sb_row_data_sb_selectors_intact() -> None:
    # Andere data-sb-Selektoren (Sort-Mode Conviction/Monster/KI etc.)
    # muessen unveraendert bleiben — wir haben nur Setup-Cursor entfernt.
    # Pruefe Vorkommen der wichtigsten anderen Selektoren.
    other_selectors = [
        '.sb-row[data-sb="conviction"]',
        '.sb-row[data-sb="setup"]',  # ohne :hover oder :focus-visible, aber andere Regeln OK
        '.sb-row[data-sb="monster"]',
        '.sb-row[data-sb="ki"]',
    ]
    for sel in other_selectors:
        assert sel in HJ, f"Selektor {sel} faelschlich entfernt"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 cursor:pointer auf Setup-sb-num weg",   test_01_setup_sb_num_cursor_pointer_removed),
        ("02 :hover/:focus-visible auf Setup weg",    test_02_setup_sb_num_hover_focus_removed),
        ("03 .sb-num-Grundregel erhalten",            test_03_sb_num_base_rule_preserved),
        ("04 agent-dot hat title-Attribut",           test_04_agent_dot_has_title_attribute),
        ("05 Andere data-sb-Selektoren unberuehrt",   test_05_other_sb_row_data_sb_selectors_intact),
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
