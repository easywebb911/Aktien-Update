"""Mock-Tests fuer Konfidenz-Wasserzeichen Phase 2 (16.05.2026).

Hintergrund: PR #146 hat Konfidenz-Stufen eingefuehrt (robust/mittel/
provisorisch/heuristisch), bisher nur im Methodik-Panel sichtbar.
Phase 2 macht sie auf der Karte direkt sichtbar via Hybrid-Wasserzeichen:

  - robust:        opacity 1.00, keine Linie
  - mittel:        opacity 0.85, keine Linie
  - provisorisch:  opacity 0.85, durchgehende Unterstreichung
  - heuristisch:   opacity 0.85, gepunktete Unterstreichung

Design-Prinzip: KEINE neue Farben — Color-Blind-safe (nur Opacity + Form-
Code). Gepunktete Linie ist im Webdesign etabliertes Signal fuer
„Tooltip verfuegbar / fragliche Angabe" (analog Rechtschreibpruefung).

Tests:
  1. _conf_class('setup') mit robust -> sb-conf-robust, leerer title
  2. _conf_class('conviction') mit heuristisch -> sb-conf-heur, title da
  3. _conf_class fallback bei leerem _SCORE_CONFIDENCE -> heuristisch
  4. _conf_class bei unbekannter Stufe -> heuristisch (konservativ)
  5. title-Strings haben Note-Text wenn vorhanden
  6. title-Strings sind quoted-safe (kein " in title-Wert)
  7. aria-label ist gesetzt fuer Screenreader
  8. Source: _score_block_inner_html erweitert um sb-conf-X-Klassen
     fuer alle 4 Score-Rows (Conviction/Setup/Monster/KI)
  9. Source: title-Attribut wird in alle Rows injiziert
 10. Source: CSS-Klassen .sb-conf-robust/mittel/prov/heur in head.jinja
 11. Source: gepunktete Linie nur fuer .sb-conf-heur (Hauptsignal)
 12. Source: durchgehende Linie nur fuer .sb-conf-prov
 13. CLAUDE.md: Phase-2-Doku-Block vorhanden
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
HJ = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def _func_block(func_def: str) -> str:
    start = GR.find(func_def)
    assert start > 0, f"Funktion {func_def!r} nicht gefunden"
    end = GR.find("\ndef ", start + 10)
    assert end > start
    return GR[start:end]


# ── ECHTE _conf_class (Single-Source-Umbau) ─────────────────────────────────
# Statt einer Replik wird die ECHTE Funktion aus generate_report.py extrahiert
# und mit einem KONTROLLIERTEN SCORE_STATUS_LABELS ausgeführt (kein Replik-
# Drift). Das Wasserzeichen kommt jetzt aus dem VALIDIERUNGS-Status
# (SCORE_STATUS_LABELS), NICHT mehr aus einer daten-getriebenen Stufe.

def _conf_class_with(labels: dict):
    ns = {"SCORE_STATUS_LABELS": labels}
    exec(_func_block("def _conf_class("), ns)
    return ns["_conf_class"]


# ── Funktional ───────────────────────────────────────────────────────────────

def test_01_validated_empty_attrs() -> None:
    # Zukunfts-Pfad: ein Score mit status_kind=="validated" bekommt KEIN Dimming.
    cc = _conf_class_with({"setup": {"status_kind": "validated", "status": "validiert"}})
    css, title, aria = cc("setup")
    assert css == "sb-conf-robust"
    assert title == "" and aria == "", "validiert → keine Extra-Attribute"


def test_02_unvalidated_full_attrs() -> None:
    cc = _conf_class_with({"conviction": {
        "status": "Aggregat · unvalidiert", "status_date": "2026-06-30"}})
    css, title, aria = cc("conviction")
    assert css == "sb-conf-heur"
    assert "Status:" in title and "Aggregat" in title
    # Karten-Tooltip trägt das ISO-Befund-Datum (das Panel formatiert DE).
    assert "Befund 2026-06-30" in title, f"Befund-Datum fehlt: {title!r}"
    assert aria == "Status Aggregat · unvalidiert"


def test_03_fallback_unknown_key() -> None:
    cc = _conf_class_with({})
    css, title, aria = cc("setup")
    assert css == "sb-conf-heur", "Unbekannt → konservativ gedimmt"
    assert "unvalidiert" in title


def test_04_title_no_double_quotes() -> None:
    """Status darf keine doppelten Anführungszeichen ins title=\"…\" bringen."""
    cc = _conf_class_with({"x": {"status": 'mit "evil" Quote',
                                 "status_date": "2026-01-01"}})
    _, title, _ = cc("x")
    assert '"' not in title, f"Title enthaelt noch Quote: {title!r}"
    assert "'evil'" in title, "Quote-Escape via single-Quote-Replace"


def test_05_reflects_validation_not_data() -> None:
    # Kernbeleg des Single-Source-Umbaus: mit dem ECHTEN config-Setup
    # (unvalidiert) ist Setup NICHT mehr un-gedimmt „robust".
    from config import SCORE_STATUS_LABELS as REAL
    cc = _conf_class_with(REAL)
    css, title, _ = cc("setup")
    assert css == "sb-conf-heur", \
        "Setup muss unter der echten config gedimmt sein (unvalidiert)"
    assert "unvalidiert" in title


def test_06_single_source_not_score_confidence() -> None:
    # Die echte Funktion darf NICHT mehr am alten _SCORE_CONFIDENCE-Tier hängen.
    block = _func_block("def _conf_class(")
    assert "SCORE_STATUS_LABELS.get(score_class)" in block
    assert "_SCORE_CONFIDENCE" not in block, \
        "_conf_class hängt noch am alten Konfidenz-Tier (Drift-Quelle)"


def test_07_aria_label_set() -> None:
    cc = _conf_class_with({"ki": {"status": "heuristisch",
                                  "status_date": "2026-07-15"}})
    _, _, aria = cc("ki")
    assert aria == "Status heuristisch"


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_08_all_rows_have_conf_class() -> None:
    block = _func_block("def _score_block_inner_html(")
    # Conviction, Setup, Monster, KI — jede sb-num bekommt sb-conf-X-Klasse
    assert block.count("{cv_css}") >= 1, "Conviction-Row hat keine conf-Klasse"
    assert block.count("{s_css}")  >= 1, "Setup-Row hat keine conf-Klasse"
    assert block.count("{m_css}")  >= 1, "Monster-Row hat keine conf-Klasse"
    assert block.count("{k_css}")  >= 1, "KI-Row hat keine conf-Klasse"


def test_09_title_attribute_injected() -> None:
    block = _func_block("def _score_block_inner_html(")
    # cv_attrs / s_attrs / m_attrs / k_attrs werden injiziert
    for var in ("cv_attrs", "s_attrs", "m_attrs", "k_attrs"):
        assert "{" + var + "}" in block, f"{var} fehlt im Render"
    # Die _conf_class-Aufrufe sind vorhanden
    assert '_conf_class("conviction")' in block
    assert '_conf_class("setup")' in block
    assert '_conf_class("monster")' in block
    assert '_conf_class("ki")' in block


def test_10_css_classes_in_head_jinja() -> None:
    assert ".sb-conf-robust{" in HJ, "sb-conf-robust CSS fehlt"
    assert ".sb-conf-mittel{" in HJ, "sb-conf-mittel CSS fehlt"
    assert ".sb-conf-prov{" in HJ, "sb-conf-prov CSS fehlt"
    assert ".sb-conf-heur{" in HJ, "sb-conf-heur CSS fehlt"


def test_11_dotted_only_for_heur() -> None:
    # Suche nach dem .sb-conf-heur-Block
    heur_idx = HJ.find(".sb-conf-heur{")
    assert heur_idx > 0
    heur_block = HJ[heur_idx:heur_idx + 250]
    assert "underline dotted" in heur_block, \
        "Heuristisch hat keine gepunktete Unterstreichung"
    assert "cursor:help" in heur_block, "cursor:help fehlt fuer heur"


def test_12_solid_underline_only_for_prov() -> None:
    # Isoliere genau den .sb-conf-prov-Block bis zur naechsten Klasse
    prov_idx = HJ.find(".sb-conf-prov{")
    assert prov_idx > 0
    next_class = HJ.find(".sb-conf-heur{", prov_idx)
    assert next_class > prov_idx
    prov_block = HJ[prov_idx:next_class]
    assert "underline" in prov_block, "Provisorisch hat keine Unterstreichung"
    assert "dotted" not in prov_block, \
        "Provisorisch darf nicht gepunktet sein (= heur)"


def test_13_claude_md_phase2_doc() -> None:
    # Phase-2-Dokumentation muss existieren
    assert "Wasserzeichen" in CMD or "Phase 2" in CMD, \
        "Phase-2-Wasserzeichen-Doku fehlt in CLAUDE.md"
    # sb-conf-X-Klassen erwaehnt
    assert "sb-conf-" in CMD, "CSS-Klassen-Mapping in CLAUDE.md fehlt"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 validiert → leere Attribute",             test_01_validated_empty_attrs),
        ("02 unvalidiert → CSS + Status + Befund",     test_02_unvalidated_full_attrs),
        ("03 Fallback unbekannter Key → gedimmt",      test_03_fallback_unknown_key),
        ("04 Status-Quote-Escape (keine \" im title)", test_04_title_no_double_quotes),
        ("05 spiegelt Validierung, nicht Daten",       test_05_reflects_validation_not_data),
        ("06 Single-Source (kein _SCORE_CONFIDENCE)",  test_06_single_source_not_score_confidence),
        ("07 aria-label gesetzt",                      test_07_aria_label_set),
        ("08 alle 4 Rows mit conf-Klasse",             test_08_all_rows_have_conf_class),
        ("09 title-Attribut injiziert",                test_09_title_attribute_injected),
        ("10 CSS-Klassen in head.jinja",               test_10_css_classes_in_head_jinja),
        ("11 dotted nur fuer heur",                    test_11_dotted_only_for_heur),
        ("12 solid underline nur fuer prov",           test_12_solid_underline_only_for_prov),
        ("13 CLAUDE.md Phase-2-Doku",                  test_13_claude_md_phase2_doc),
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
