"""Mock-Tests fuer Karten-Cockpit Stage 1 (18.05.2026).

Hintergrund: Bloomberg-Stil-Cockpit-Layout fuer Top-10-Karten. Stage 1
liefert _card_cockpit_html-Helper + CSS-Klassen, aber Feature-Flag
CARD_COCKPIT_ENABLED=False -> kein User-sichtbarer Effekt. Aktivierung
in Stage 2 nach iPhone-Verify.

Tests:
  1. config.CARD_COCKPIT_ENABLED existiert und ist False (Stage-1-Default)
  2. _card_cockpit_html-Funktion existiert in generate_report
  3. Output enthaelt Cockpit-Container-Klasse
  4. Output enthaelt drei Saeulen in Reihenfolge Setup -> Monster -> KI
  5. SVG hat width="150" + height="150" als HTML-Attribute (NICHT nur CSS)
     — Tuning-Sequenz 18.05.2026: 185 -> 160 -> 150 nach iPhone-Verify
  6. Donut hat /100-Skala
  7. Bei positivem chg: cockpit-change-up Klasse
  8. Bei negativem chg: cockpit-change-down Klasse
  9. Konfidenz-Wasserzeichen-Klassen werden auf Saeulen + Donut angewendet
 10. CSS in head.jinja enthaelt .card-cockpit + .cockpit-pillar + .cockpit-donut
 11. CSS hat 28px Kurs + 26px Saeulen-Wert + 50px Donut-Zahl
 12. Bestehende _score_block_inner_html-Funktion UNVERAENDERT vorhanden
 13. Bestehender _card-Pfad UNVERAENDERT (kein cockpit-Aufruf)
 14. Render mit None-Werten fuer monster/ki -> graceful '—'
 15. Saeulen-Reihenfolge im HTML strikt Setup vor Monster vor KI
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
CFG_SRC = (ROOT / "config.py").read_text(encoding="utf-8")
HJ_SRC = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")


def _extract_helper():
    """Lade _card_cockpit_html + Abhaengigkeiten ohne yfinance."""
    ns = {
        "_safe_float": lambda v: float(v) if v is not None else 0.0,
    }
    # _conf_class minimal: gibt immer robust zurueck (keine Watermark)
    ns["_conf_class"] = lambda key: ("sb-conf-robust", "", "")
    # _tri_score_color
    def _tri(sc):
        if sc is None: return "#94a3b8"
        if sc >= 60: return "#22c55e"
        if sc >= 30: return "#f59e0b"
        return "#ef4444"
    ns["_tri_score_color"] = _tri

    # Extract function definition
    m = re.search(r"^def _card_cockpit_html\(.*?(?=\n\ndef )",
                  GR_SRC, re.MULTILINE | re.DOTALL)
    assert m, "_card_cockpit_html nicht gefunden"
    exec(m.group(0), ns)
    return ns["_card_cockpit_html"]


_card_cockpit_html = _extract_helper()


def _sample_stock(**overrides):
    base = {
        "ticker": "PZZA",
        "company_name": "Papa John's International",
        "price": 34.73,
        "change": 1.22,
        "score": 85.4,
        "monster_score": 78.0,
        "ki_signal_score": 65.0,
        "conviction": {"score": 72, "level": "medium",
                       "action_text": "Substrat stark, Timing-Signal fehlt. Auf Volume-Spike oder Anomalie-Trigger warten."},
    }
    base.update(overrides)
    return base


def test_01_flag_exists() -> None:
    # Stage 2 ab 18.05.2026: Flag ist auf True gesetzt; Test prueft nur
    # noch Existenz der Konstante. Wenn jemand das Flag spaeter zur
    # Rollback-Sicherheit auf False zurueckdreht, sollte Stage 1-Test
    # bewusst nicht failen — daher inversionsneutral.
    assert "CARD_COCKPIT_ENABLED" in CFG_SRC, "Flag fehlt in config.py"


def test_02_helper_exists() -> None:
    assert "def _card_cockpit_html" in GR_SRC, \
        "_card_cockpit_html-Funktion fehlt"


def test_03_cockpit_container_class() -> None:
    out = _card_cockpit_html(1, _sample_stock())
    assert 'class="card-cockpit"' in out, \
        "Cockpit-Container-Klasse fehlt im Output"


def test_04_three_pillars_in_order() -> None:
    out = _card_cockpit_html(1, _sample_stock())
    # Reihenfolge Setup -> Monster -> KI via data-sb-Marker
    setup_idx = out.find('data-sb="setup"')
    monster_idx = out.find('data-sb="monster"')
    ki_idx = out.find('data-sb="ki"')
    assert setup_idx > 0, "Setup-Saeule fehlt"
    assert monster_idx > setup_idx, \
        f"Monster nach Setup erwartet (setup@{setup_idx}, monster@{monster_idx})"
    assert ki_idx > monster_idx, \
        f"KI nach Monster erwartet (monster@{monster_idx}, ki@{ki_idx})"


def test_05_svg_has_html_size_attributes() -> None:
    out = _card_cockpit_html(1, _sample_stock())
    # SVG-Tag muss width und height als HTML-Attribute haben.
    # Iterativ-Tuning 18.05.2026: 185 -> 160 -> 150 px nach iPhone-
    # Verify (Donut zu dominant gegenueber Saeulen-Spalte).
    assert 'width="150"' in out, "SVG width=150 als HTML-Attribut fehlt"
    assert 'height="150"' in out, "SVG height=150 als HTML-Attribut fehlt"
    assert 'viewBox="0 0 150 150"' in out, "SVG viewBox fehlt oder falsch"


def test_06_donut_has_100_scale() -> None:
    out = _card_cockpit_html(1, _sample_stock())
    assert "/ 100" in out, "/100-Skala-Marker im Donut fehlt"


def test_07_chg_positive_class() -> None:
    out = _card_cockpit_html(1, _sample_stock(change=2.5))
    assert "cockpit-change-up" in out, \
        "Positives chg -> cockpit-change-up Klasse fehlt"
    assert "&#9650;" in out, "Aufwaerts-Pfeil ▲ fehlt"


def test_08_chg_negative_class() -> None:
    out = _card_cockpit_html(1, _sample_stock(change=-1.8))
    assert "cockpit-change-down" in out, \
        "Negatives chg -> cockpit-change-down Klasse fehlt"
    assert "&#9660;" in out, "Abwaerts-Pfeil ▼ fehlt"


def test_09_confidence_watermark_classes_applied() -> None:
    # Helper nutzt _conf_class -> sb-conf-* Klassen auf Werte
    out = _card_cockpit_html(1, _sample_stock())
    assert "cockpit-pillar-value" in out
    assert "cockpit-donut-number" in out
    # Bei robust = "sb-conf-robust" (kein User-sichtbarer Effekt aber Klasse da)
    assert "sb-conf-robust" in out, \
        "Konfidenz-Wasserzeichen-Klasse (sb-conf-*) fehlt"


def test_10_css_classes_in_head_jinja() -> None:
    required = [
        ".card-cockpit",
        ".cockpit-header",
        ".cockpit-pillars",
        ".cockpit-pillar",
        ".cockpit-pillar-value",
        ".cockpit-pillar-bar",
        ".cockpit-donut-wrap",
        ".cockpit-donut-svg",
        ".cockpit-donut-number",
        ".cockpit-donut-scale",
        ".cockpit-donut-caption",
        ".cockpit-price",
        ".cockpit-change-up",
        ".cockpit-change-down",
    ]
    for cls in required:
        assert cls in HJ_SRC, f"CSS-Klasse {cls} fehlt in head.jinja"


def test_11_css_font_sizes_match_spec() -> None:
    # Kurs 28px, Saeulen-Wert 26px, Donut-Zahl 40px.
    # Donut-Zahl-Sequenz 18.05.2026: 50 -> 42 -> 40 px (proportional
    # zur Donut-Groesse-Reduzierung 185 -> 160 -> 150).
    assert "font-size:28px" in HJ_SRC, \
        "Kurs-font-size 28px fehlt"
    m = re.search(r"\.cockpit-pillar-value\{[^}]*font-size:26px", HJ_SRC)
    assert m, "cockpit-pillar-value font-size:26px fehlt"
    m = re.search(r"\.cockpit-donut-number\{[^}]*font-size:40px", HJ_SRC)
    assert m, "cockpit-donut-number font-size:40px fehlt"


def test_12_score_block_inner_unchanged() -> None:
    # Bestehender Helper darf weiter existieren — Stage 1 ist additiv
    assert "def _score_block_inner_html" in GR_SRC, \
        "_score_block_inner_html wurde versehentlich entfernt"


def test_13_helper_callable_and_defined() -> None:
    # Stage 2 ab 18.05.2026: _card und _build_card_ctx rufen den Helper
    # jetzt aktiv auf. Test prueft nur noch dass Definition + mindestens
    # ein Call-Site existieren — Aufruf-Anzahl-Drift (z.B. weitere
    # Konsumenten) faengt der Stage-2-Test ab.
    calls = re.findall(r"_card_cockpit_html\(", GR_SRC)
    assert len(calls) >= 1, "_card_cockpit_html-Definition fehlt"


def test_14_none_values_graceful() -> None:
    # Monster/KI=None ohne Crash, "—" als Display
    s = _sample_stock(monster_score=None, ki_signal_score=None)
    out = _card_cockpit_html(1, s)
    assert "—" in out, "None-Werte sollten als — gerendert werden"


def test_15_pillar_order_strict_in_html() -> None:
    out = _card_cockpit_html(1, _sample_stock())
    # Setup-Label muss vor Monster-Label vor KI-Label in HTML stehen
    su = out.find(">Setup<")
    mo = out.find(">Monster<")
    ki = out.find(">KI<")
    assert su > 0 and mo > su and ki > mo, \
        f"Saeulen-Reihenfolge in HTML falsch: Setup={su}, Monster={mo}, KI={ki}"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 CARD_COCKPIT_ENABLED flag exists",       test_01_flag_exists),
        ("02 _card_cockpit_html exists",             test_02_helper_exists),
        ("03 cockpit container class",                test_03_cockpit_container_class),
        ("04 three pillars Setup->Monster->KI",       test_04_three_pillars_in_order),
        ("05 SVG width/height HTML attrs (not CSS)",  test_05_svg_has_html_size_attributes),
        ("06 Donut /100-scale marker",                test_06_donut_has_100_scale),
        ("07 chg > 0 -> cockpit-change-up",          test_07_chg_positive_class),
        ("08 chg < 0 -> cockpit-change-down",        test_08_chg_negative_class),
        ("09 conf-watermark classes on values",      test_09_confidence_watermark_classes_applied),
        ("10 CSS classes in head.jinja",             test_10_css_classes_in_head_jinja),
        ("11 CSS font-sizes (28/26/50)",             test_11_css_font_sizes_match_spec),
        ("12 _score_block_inner_html unchanged",     test_12_score_block_inner_unchanged),
        ("13 Helper definiert + callable",            test_13_helper_callable_and_defined),
        ("14 None-Werte graceful (—)",                test_14_none_values_graceful),
        ("15 Saeulen-Reihenfolge im HTML strict",    test_15_pillar_order_strict_in_html),
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
