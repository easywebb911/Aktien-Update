"""Mock-Tests fuer Details + News Padding-Skalierung (16.05.2026).

Hintergrund: Easy meldet nach PR #179 (KI-Analyse-Padding-Fix) das
gleiche Truncation-Symptom bei zwei weiteren Sektionen:
- "Details"-Tabelle: max-height fest 1200 px in .details-body.open
- "Aktuelle Meldungen": padding fest 12px in .news-panel

Beide Sektionen werden in Top-10-Karten UND Watchlist-Drawer-Karten
verwendet (gleiche CSS-Klassen via _wl_full_card_html).

Fix: max-height + padding in em-Einheiten skaliert mit Schrift.

ABGRENZUNG: Memory-Z-23-Bug "News leer in CRMD-Watchlist-Drawer" ist
anderer Bug-Klasse (Datenfluss). Durch PR #163 (heute) strukturell
behoben. Wird hier NICHT mitgefixt.

Tests:
  1. .details-body.open max-height enthaelt "150em"
  2. .details-body.open hat KEIN "1200px" mehr
  3. .news-panel padding enthaelt "0.8em"
  4. .news-panel hat KEIN "12px 14px" mehr
  5. .details-body Transition-Property unveraendert
  6. .details-body (closed) max-height: 0 unveraendert
  7. CLAUDE.md em-Skalierung-Sektion erwaehnt neue Stellen
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HJ = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def _block_after(needle: str, span: int = 250) -> str:
    idx = HJ.find(needle)
    assert idx > 0, f"{needle!r} nicht gefunden"
    return HJ[idx:idx + span]


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_01_details_body_open_em() -> None:
    block = _block_after(".details-body.open{")
    assert "max-height:150em" in block, \
        "details-body.open max-height nicht auf 150em umgestellt"


def test_02_details_body_no_1200px() -> None:
    block = _block_after(".details-body.open{", span=100)
    assert "1200px" not in block, \
        "Alter 1200px-Wert noch in .details-body.open"


def test_03_news_panel_em_padding() -> None:
    block = _block_after(".news-panel{", span=150)
    assert "padding:0.8em 14px" in block, \
        "news-panel padding nicht auf 0.8em 14px umgestellt"


def test_04_news_panel_no_12px() -> None:
    block = _block_after(".news-panel{", span=150)
    # Speziell der alte "12px 14px"-padding darf nicht mehr da sein
    assert "padding:12px 14px" not in block, \
        "Alter padding:12px 14px noch in .news-panel"


def test_05_details_transition_preserved() -> None:
    # Transition-Property unveraendert
    idx = HJ.find(".details-body{")
    assert idx > 0
    block = HJ[idx:idx + 250]
    assert "transition:max-height" in block, \
        "Transition-Property entfernt"
    assert ".25s ease" in block, "Transition-Timing veraendert"


def test_06_details_body_closed_unchanged() -> None:
    # collapsed-Zustand bleibt max-height:0
    idx = HJ.find(".details-body{")
    assert idx > 0
    block = HJ[idx:idx + 100]
    assert "max-height:0" in block, "Collapsed-Wert max-height:0 entfernt"
    assert "overflow:hidden" in block, "overflow:hidden entfernt"


def test_07_claude_md_mention() -> None:
    # CLAUDE.md em-Skalierung-Sektion erwähnt neue Stellen
    # (Mindestens .details-body oder .news-panel sollte erwähnt sein)
    assert ".details-body" in CMD or ".news-panel" in CMD or \
           "details-body" in CMD or "news-panel" in CMD, \
        "CLAUDE.md erwähnt neue em-Skalierung-Stellen nicht"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 details-body.open max-height 150em",     test_01_details_body_open_em),
        ("02 Kein 1200px in details-body.open",       test_02_details_body_no_1200px),
        ("03 news-panel padding 0.8em 14px",          test_03_news_panel_em_padding),
        ("04 Kein 12px 14px in news-panel",           test_04_news_panel_no_12px),
        ("05 Transition unveraendert",                test_05_details_transition_preserved),
        ("06 Collapsed-State unveraendert",           test_06_details_body_closed_unchanged),
        ("07 CLAUDE.md em-Skalierung-Erwähnung",      test_07_claude_md_mention),
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
