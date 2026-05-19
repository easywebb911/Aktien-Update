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
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
HJ = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")
CMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def _func_block(func_def: str) -> str:
    start = GR.find(func_def)
    assert start > 0, f"Funktion {func_def!r} nicht gefunden"
    end = GR.find("\ndef ", start + 10)
    assert end > start
    return GR[start:end]


# ── _conf_class-Replik (1:1 mit echter Funktion) ────────────────────────────

_CONF_TIER_CLASS = {
    "robust":       "sb-conf-robust",
    "mittel":       "sb-conf-mittel",
    "provisorisch": "sb-conf-prov",
    "heuristisch":  "sb-conf-heur",
}


def _replicate_conf_class(score_class: str, confidence: dict) -> tuple[str, str, str]:
    conf = confidence or {}
    entry = conf.get(score_class) or {}
    tier = entry.get("tier") or "heuristisch"
    css = _CONF_TIER_CLASS.get(tier, "sb-conf-heur")
    if tier == "robust":
        return "sb-conf-robust", "", ""
    label = tier
    note = (entry.get("note") or "").replace('"', "'")
    n = entry.get("n")
    n_str = f" (n={n})" if isinstance(n, int) and n > 0 else ""
    title = f"Konfidenz: {label}{n_str} — {note}" if note else f"Konfidenz: {label}{n_str}"
    aria = f"Konfidenz {label}"
    return css, title, aria


# ── Funktional ───────────────────────────────────────────────────────────────

def test_01_robust_empty_attrs() -> None:
    conf = {"setup": {"tier": "robust", "n": 1263, "note": "Backtest"}}
    css, title, aria = _replicate_conf_class("setup", conf)
    assert css == "sb-conf-robust"
    assert title == "", "robust hat leeren title (keine extra Attribute im HTML)"
    assert aria == ""


def test_02_heuristisch_full_attrs() -> None:
    conf = {"conviction": {"tier": "heuristisch", "n": 0,
                            "note": "Aggregat, keine Backtest-Persistenz"}}
    css, title, aria = _replicate_conf_class("conviction", conf)
    assert css == "sb-conf-heur"
    assert "heuristisch" in title
    assert "Aggregat" in title
    assert aria == "Konfidenz heuristisch"


def test_03_fallback_empty_confidence() -> None:
    css, title, aria = _replicate_conf_class("setup", {})
    assert css == "sb-conf-heur", "Fallback bei leerem Confidence -> heuristisch"
    assert "heuristisch" in title


def test_04_unknown_tier_falls_back() -> None:
    conf = {"ki": {"tier": "experimental"}}   # nicht im Mapping
    css, title, aria = _replicate_conf_class("ki", conf)
    assert css == "sb-conf-heur", \
        "Unbekannte Stufe → konservativer heuristisch-Fallback"


def test_05_title_contains_n_when_present() -> None:
    conf = {"earliness": {"tier": "mittel", "n": 78, "note": "MWU-Test"}}
    css, title, _ = _replicate_conf_class("earliness", conf)
    assert "(n=78)" in title
    assert "mittel" in title


def test_06_title_no_double_quotes() -> None:
    """Note darf keine doppelten Anfuehrungszeichen enthalten — sonst
    bricht das title="..." HTML-Attribut."""
    conf = {"x": {"tier": "heuristisch", "note": 'mit "evil" Quote'}}
    css, title, _ = _replicate_conf_class("x", conf)
    assert '"' not in title, f"Title enthaelt noch Quote: {title!r}"
    assert "'evil'" in title, "Quote-Escape via single-Quote-Replace"


def test_07_aria_label_set() -> None:
    conf = {"ki": {"tier": "heuristisch", "n": 0}}
    _, _, aria = _replicate_conf_class("ki", conf)
    assert aria == "Konfidenz heuristisch"


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
        ("01 robust → leere Attribute",                test_01_robust_empty_attrs),
        ("02 heuristisch → CSS + title + aria",        test_02_heuristisch_full_attrs),
        ("03 Fallback bei leerem _SCORE_CONFIDENCE",   test_03_fallback_empty_confidence),
        ("04 Unbekannte Stufe → heur-Fallback",        test_04_unknown_tier_falls_back),
        ("05 title enthaelt n bei n>0",                test_05_title_contains_n_when_present),
        ("06 Note-Quote-Escape (keine \" im title)",   test_06_title_no_double_quotes),
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
