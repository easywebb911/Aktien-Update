"""Mock-Tests fuer KI-Analyse Text-Truncation Fix (16.05.2026).

Hintergrund: Easy berichtet bei groesserer Schriftgroesse, dass das
Fazit der KI-Analyse vom iPhone Home-Indicator ueberdeckt wird.

Diagnose: padding-bottom war fest 48px in .ki-analyse-result, skalierte
nicht mit Schriftgroesse. Bei groesserer Schrift wird letzte Zeile vom
iOS-Bottom-Overlay ueberlagert.

Fix: padding in em-Einheiten konvertiert, skaliert proportional zur
Schrift. safe-area-inset-bottom-Floor bleibt fuer iOS-Notch-Sicherheit.

Tests:
  1. .ki-analyse-result padding-bottom = max(3em, env(safe-area))
  2. .ki-analyse-result padding-top/sides nutzt em (statt fest 10px)
  3. env(safe-area-inset-bottom) bleibt als Floor erhalten
  4. Alter padding-bottom-Wert (48px) ist entfernt
  5. .ki-truncated-notice padding in em (Konsistenz)
  6. .ki-analyse-result hat KEINEN max-height-Lock (Container darf wachsen)
  7. font-size in rem (nicht aenderbar in diesem PR, aber Verifikation)
  8. CLAUDE.md erwaehnt em-Skalierung-Hinweis
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HJ = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def _block(start_marker: str) -> str:
    idx = HJ.find(start_marker)
    assert idx > 0, f"{start_marker!r} nicht gefunden"
    return HJ[idx:idx + 400]


def test_01_padding_bottom_em_with_safe_area_floor() -> None:
    block = _block(".ki-analyse-result{")
    assert "padding-bottom:max(3em, env(safe-area-inset-bottom))" in block, \
        "padding-bottom nicht auf max(3em, env(safe-area)) gesetzt"


def test_02_padding_top_sides_em_based() -> None:
    block = _block(".ki-analyse-result{")
    # Top/Sides als 0.7em 14px
    assert "padding:0.7em 14px" in block, \
        "padding-top/sides nicht in em geaendert"


def test_03_safe_area_floor_preserved() -> None:
    block = _block(".ki-analyse-result{")
    assert "env(safe-area-inset-bottom)" in block, \
        "iOS safe-area-floor entfernt"


def test_04_old_48px_removed() -> None:
    block = _block(".ki-analyse-result{")
    assert "max(48px" not in block, \
        "Alter 48px-Wert noch in .ki-analyse-result"
    # Auch alte 10px-Padding-Variante darf nicht mehr im Block sein
    assert "padding:10px 14px" not in block, \
        "Alter padding:10px 14px noch da"


def test_05_truncated_notice_em_padding() -> None:
    block = _block(".ki-truncated-notice{")
    # margin-top + padding in em-Einheiten
    assert "margin-top:0.5em" in block, \
        "ki-truncated-notice margin-top nicht in em"
    assert "padding:0.4em 0.7em" in block, \
        "ki-truncated-notice padding nicht in em"
    # Alter 8px/6px-10px darf nicht mehr da sein
    assert "margin-top:8px" not in block
    assert "padding:6px 10px" not in block


def test_06_no_max_height_lock() -> None:
    # .ki-analyse-result darf KEIN max-height haben (Container muss
    # mit Inhalt wachsen)
    block = _block(".ki-analyse-result{")
    # Erste Regel-Bloecke pruefen (bis zur ersten schliessenden })
    end = block.find("}")
    rule = block[:end]
    assert "max-height" not in rule, \
        "ki-analyse-result hat unerwarteten max-height-Lock"


def test_07_font_size_rem_unchanged() -> None:
    # font-size war .82rem — bleibt unveraendert (nur Padding ist Bug)
    block = _block(".ki-analyse-result{")
    assert "font-size:.82rem" in block, "font-size .82rem entfernt?"


def test_08_claude_md_note() -> None:
    # CLAUDE.md erwaehnt em-Padding-Skalierung-Pattern
    assert ("em-Skalierung" in CMD or
            "em statt px" in CMD or
            "ki-analyse-result" in CMD or
            "Schriftgroessen-Skalierung" in CMD or
            "Schriftgrößen-Skalierung" in CMD), \
        "CLAUDE.md-Hinweis fuer Padding-Skalierung fehlt"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 padding-bottom max(3em, safe-area)",   test_01_padding_bottom_em_with_safe_area_floor),
        ("02 padding-top/sides 0.7em 14px",          test_02_padding_top_sides_em_based),
        ("03 safe-area-Floor erhalten",              test_03_safe_area_floor_preserved),
        ("04 Alter 48px-Wert entfernt",              test_04_old_48px_removed),
        ("05 ki-truncated-notice em-Padding",        test_05_truncated_notice_em_padding),
        ("06 Kein max-height-Lock",                  test_06_no_max_height_lock),
        ("07 font-size .82rem unveraendert",         test_07_font_size_rem_unchanged),
        ("08 CLAUDE.md em-Skalierung-Hinweis",       test_08_claude_md_note),
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
