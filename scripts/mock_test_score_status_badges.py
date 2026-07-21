"""Mock-Tests für Score-Status-Kennzeichnung (PR B "Karten-Status-Ehrlichkeit").

Hintergrund: Jeder der vier Karten-Scores (Setup/Monster/KI/Conviction) trägt
ein kleines Status-Badge, das den EPISTEMISCHEN Stand des SCORES ehrlich zeigt
(unvalidiert / OoS-kollabiert / heuristisch / Aggregat · unvalidiert). Zusätzlich
wird der bereits vorhandene Conviction-Erklärtext prominent in den Kopfbereich
verschoben (Rang-Kontext), damit der Rang sich selbst einordnet.

ANTI-DRIFT-KERN (Wurzel des Panel-„Ende-Aug"-Fehlers nicht wiederholen): die
Badge-Texte kommen aus EINER zentralen config-Struktur (config.SCORE_STATUS_LABELS),
NIE hardcoded im Template. Dieser Test verriegelt genau das.

Tests (reine Source-Inspektion — kein yfinance-Import):
  1. config.SCORE_STATUS_LABELS existiert, genau 4 Keys, alle non-empty str.
  2. Pflege-Pflicht-Kommentar an der Struktur (VERALTEN + Re-Test-Termine).
  3. _score_status_badge_html liest SCORE_STATUS_LABELS (Single-Source).
  4. KEIN Badge-Status-VALUE als Literal im generate_report-Template.
  5. _card_cockpit_html verdrahtet Badges für Pillars + Conviction.
  6. CSS .cockpit-status-badge + .cockpit-rank-context in head.jinja.
  7. Badge-Styling NEUTRAL (keine Ampelfarbe grün/rot im Badge-Rule).
  8. B2: Rang-Kontext nutzt vorhandenen conv_action, donut-caption entfernt.
  9. Monster bleibt optisch zurückgenommen (_MONSTER_NEUTRAL_COLOR).
 10. Badge-Wortlaut beschreibt den SCORE-Status, nicht die Aktie (Tooltip).
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
HJ_SRC = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")

sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("config", ROOT / "config.py")
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)

_EXPECTED_KEYS = {"setup", "monster", "ki", "conviction"}


def test_01_config_struct_present() -> None:
    labels = getattr(config, "SCORE_STATUS_LABELS", None)
    assert isinstance(labels, dict), "config.SCORE_STATUS_LABELS fehlt/kein dict"
    assert set(labels) == _EXPECTED_KEYS, \
        f"Keys erwartet {_EXPECTED_KEYS}, gefunden {set(labels)}"
    for k, v in labels.items():
        assert isinstance(v, str) and v.strip(), f"{k}: leerer/kein Status-Text"


def test_02_maintenance_comment() -> None:
    # Kommentar-Block direkt vor der Struktur muss die Pflege-Pflicht + die
    # Re-Test-Termine benennen (damit der planmäßige Verfall trivial pflegbar
    # bleibt — Wurzel des „Ende-Aug"-Fehlers).
    cfg = (ROOT / "config.py").read_text(encoding="utf-8")
    anchor = cfg.find("SCORE_STATUS_LABELS")
    head = cfg[max(0, anchor - 1400):anchor]
    for needle in ("PFLEGE-PFLICHT", "VERALTEN", "27.07", "Sept"):
        assert needle in head, f"Pflege-Kommentar ohne '{needle}'"


def test_03_helper_reads_config() -> None:
    assert "SCORE_STATUS_LABELS.get(conf_key)" in GR_SRC, \
        "_score_status_badge_html liest nicht aus config.SCORE_STATUS_LABELS"
    assert "def _score_status_badge_html" in GR_SRC, "Helper fehlt"


def _fn_body(name: str) -> str:
    m = re.search(rf"^def {name}\(.*?(?=\n\ndef )", GR_SRC,
                  re.MULTILINE | re.DOTALL)
    assert m, f"{name} nicht gefunden"
    return m.group(0)


def test_04_no_hardcoded_badge_value_in_template() -> None:
    # Die Status-VALUES dürfen NUR in config.py leben. In den beiden
    # relevanten Render-Funktionen (_score_status_badge_html-Helper +
    # _card_cockpit_html-Template) dürfen sie NICHT als Literal stehen —
    # sonst driftet die Anzeige von der Single-Source weg.
    # (Generische Wörter wie „unvalidiert" kommen anderswo legitim vor —
    # daher scope auf genau die zwei Funktionen statt globalem Grep.)
    raw = _fn_body("_score_status_badge_html") + "\n" + _fn_body("_card_cockpit_html")
    # Voll-Kommentar-Zeilen entfernen (dort darf ein Wort wie „unvalidiert" in
    # der Erklärung stehen, z. B. Monster-Neutral-Kommentar) — geprüft wird nur
    # echter Render-Code / String-Literale.
    scope = "\n".join(ln for ln in raw.splitlines()
                      if not ln.lstrip().startswith("#"))
    for v in config.SCORE_STATUS_LABELS.values():
        assert v not in scope, \
            f"Badge-Value {v!r} hardcoded im Render-Pfad — Single-Source verletzt"


def test_05_wired_into_cockpit() -> None:
    # Pillar-Loop + Conviction rufen den Helper.
    assert "status_badge = _score_status_badge_html(conf_key)" in GR_SRC, \
        "Pillar-Badge nicht verdrahtet"
    assert '_score_status_badge_html("conviction")' in GR_SRC, \
        "Conviction-Badge nicht verdrahtet"
    assert "{status_badge}" in GR_SRC and "{conv_status_badge}" in GR_SRC, \
        "Badge-Interpolation fehlt im Cockpit-HTML"


def test_06_css_classes_present() -> None:
    for cls in (".cockpit-status-badge", ".cockpit-rank-context"):
        assert cls in HJ_SRC, f"CSS-Klasse {cls} fehlt in head.jinja"


def test_07_badge_style_neutral() -> None:
    # Das Badge-Rule darf KEINE Ampelfarbe tragen (kein grün=gut / rot=schlecht)
    # — es beschreibt Methodik-Status, nicht Bewertung.
    m = re.search(r"\.cockpit-status-badge\{([^}]*)\}", HJ_SRC)
    assert m, ".cockpit-status-badge-Rule nicht gefunden"
    body = m.group(1)
    for signal in ("#22c55e", "#ef4444"):
        assert signal not in body, \
            f"Ampelfarbe {signal} im neutralen Status-Badge — verboten"


def test_08_rank_context_reuses_existing_text() -> None:
    # B2: NUR Umplatzierung des vorhandenen conv_action — keine neue Klasse.
    assert 'class="cockpit-rank-context">{conv_action}' in GR_SRC, \
        "Rang-Kontext nutzt nicht den vorhandenen conv_action-Text"
    # Alte Donut-Caption ist relocated (nicht mehr im Render-Pfad).
    assert "cockpit-donut-caption" not in GR_SRC, \
        "cockpit-donut-caption noch im Render-Pfad (sollte relocated sein)"


def test_09_monster_still_neutral() -> None:
    assert "_MONSTER_NEUTRAL_COLOR" in GR_SRC, "Monster-Neutral-Farbe entfernt?"
    # Der Pillar-Loop muss Monster weiterhin auf Neutral-Grau setzen.
    assert 'conf_key == "monster"' in GR_SRC and \
        "col = _MONSTER_NEUTRAL_COLOR" in GR_SRC, \
        "Monster-Pillar nicht mehr neutral gefärbt"


def test_10_badge_describes_score_not_stock() -> None:
    # Tooltip-Wortlaut muss klarstellen: Score-Status, NICHT Aktien-Bewertung.
    # (Der f-String bricht die Phrase auf zwei Zeilen um → getrennt prüfen.)
    assert "beschreibt den Score, " in GR_SRC and "nicht die Aktie." in GR_SRC, \
        "Badge-Tooltip stellt Score-vs-Aktie nicht klar"


def main() -> None:
    tests = [
        ("01 config.SCORE_STATUS_LABELS 4 Keys",        test_01_config_struct_present),
        ("02 Pflege-Pflicht-Kommentar",                 test_02_maintenance_comment),
        ("03 Helper liest config (Single-Source)",      test_03_helper_reads_config),
        ("04 kein Badge-Value hardcoded im Template",   test_04_no_hardcoded_badge_value_in_template),
        ("05 Badges im Cockpit verdrahtet",             test_05_wired_into_cockpit),
        ("06 CSS-Klassen vorhanden",                    test_06_css_classes_present),
        ("07 Badge-Styling neutral (keine Ampel)",      test_07_badge_style_neutral),
        ("08 Rang-Kontext = vorhandener Text",          test_08_rank_context_reuses_existing_text),
        ("09 Monster weiterhin neutral",                test_09_monster_still_neutral),
        ("10 Badge beschreibt Score, nicht Aktie",      test_10_badge_describes_score_not_stock),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {name}: {e}")
    print(f"\nTotal: {len(tests)} | Failed: {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
