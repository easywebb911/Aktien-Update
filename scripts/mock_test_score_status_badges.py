"""Mock-Tests für Score-Status-Kennzeichnung + Single-Source (PR B + Konfidenz-
Single-Source-Umbau).

Hintergrund: Die vier Karten-Scores (Setup/Monster/KI/Conviction) tragen ein
Status-Badge; das Methodik-Panel zeigt denselben Validierungs-Status. BEIDE
lesen aus EINER Quelle — ``config.SCORE_STATUS_LABELS`` — damit sie nicht mehr
auseinanderdriften (früher: Panel „robust" vs. Karte „unvalidiert"). Die
Daten-Dimension (n gereift) kommt getrennt aus ``compute_score_confidence``,
das KEINE Validierungs-Aussage (kein ``has_auc``, kein „robust") mehr trägt.

ANTI-DRIFT-KERN: Status-Text lebt NUR in der config-Struktur, jeder Eintrag
trägt ein ``status_date`` (kein undatierter Status), und ``compute_score_
confidence`` enthält keine Validierungs-Literale mehr.

Tests (Source-Inspektion + config-Import — kein yfinance-Import):
  1. SCORE_STATUS_LABELS: 6 Keys, jeder mit non-empty ``status`` (str).
  2. Pflege-Pflicht-Kommentar (PFLEGE-PFLICHT + Re-Test-Termine).
  3. _score_status_badge_html liest den Status aus der config.
  4. KEIN Status-VALUE als Literal im Badge-/Card-Render-Pfad.
  5. Badges im Cockpit verdrahtet.
  6. CSS .cockpit-status-badge + .cockpit-rank-context in head.jinja.
  7. Badge-Styling NEUTRAL (keine Ampelfarbe).
  8. B2 Rang-Kontext nutzt vorhandenen conv_action.
  9. Monster weiterhin neutral.
 10. Badge beschreibt Score, nicht Aktie.
 11. JEDER Eintrag trägt status_date (kein undatierter Status).
 12. Single-Source: compute_score_confidence OHNE has_auc / Validierungs-Tier.
 13. _conf_class liest den Validierungs-Status aus SCORE_STATUS_LABELS.
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

# 4 Karten-Scores + 2 Panel-only (earliness, exit_pressure) = 6 (eine Pflegeliste).
_EXPECTED_KEYS = {"setup", "monster", "ki", "conviction", "earliness", "exit_pressure"}
_CARD_KEYS = {"setup", "monster", "ki", "conviction"}
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _fn_body(name: str) -> str:
    m = re.search(rf"^def {name}\(.*?(?=\n\ndef )", GR_SRC,
                  re.MULTILINE | re.DOTALL)
    assert m, f"{name} nicht gefunden"
    return m.group(0)


def test_01_config_struct_present() -> None:
    labels = getattr(config, "SCORE_STATUS_LABELS", None)
    assert isinstance(labels, dict), "config.SCORE_STATUS_LABELS fehlt/kein dict"
    assert set(labels) == _EXPECTED_KEYS, \
        f"Keys erwartet {_EXPECTED_KEYS}, gefunden {set(labels)}"
    for k, v in labels.items():
        assert isinstance(v, dict), f"{k}: Eintrag kein dict"
        status = v.get("status")
        assert isinstance(status, str) and status.strip(), \
            f"{k}: leerer/kein Status-Text"


def test_02_maintenance_comment() -> None:
    cfg = (ROOT / "config.py").read_text(encoding="utf-8")
    anchor = cfg.find("SCORE_STATUS_LABELS = {")
    head = cfg[max(0, anchor - 2200):anchor]
    for needle in ("PFLEGE-PFLICHT", "review_by", "27.07", "Sept"):
        assert needle in head, f"Pflege-Kommentar ohne '{needle}'"


def test_03_helper_reads_config() -> None:
    assert "def _score_status_badge_html" in GR_SRC, "Helper fehlt"
    body = _fn_body("_score_status_badge_html")
    assert "SCORE_STATUS_LABELS.get(conf_key)" in body and '.get("status")' in body, \
        "_score_status_badge_html liest den Status nicht aus der config-Struktur"


def test_04_no_hardcoded_status_value_in_template() -> None:
    # Die Status-VALUES dürfen NUR in config.py leben. In den Render-Funktionen
    # (_score_status_badge_html + _card_cockpit_html) dürfen sie NICHT als
    # Literal stehen. Voll-Kommentar-Zeilen ausgenommen (dort erklärend erlaubt).
    raw = _fn_body("_score_status_badge_html") + "\n" + _fn_body("_card_cockpit_html")
    scope = "\n".join(ln for ln in raw.splitlines()
                      if not ln.lstrip().startswith("#"))
    for entry in config.SCORE_STATUS_LABELS.values():
        v = entry["status"]
        assert v not in scope, \
            f"Status-Value {v!r} hardcoded im Render-Pfad — Single-Source verletzt"


def test_05_wired_into_cockpit() -> None:
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
    m = re.search(r"\.cockpit-status-badge\{([^}]*)\}", HJ_SRC)
    assert m, ".cockpit-status-badge-Rule nicht gefunden"
    body = m.group(1)
    for signal in ("#22c55e", "#ef4444"):
        assert signal not in body, \
            f"Ampelfarbe {signal} im neutralen Status-Badge — verboten"


def test_08_rank_context_reuses_existing_text() -> None:
    assert 'class="cockpit-rank-context">{conv_action}' in GR_SRC, \
        "Rang-Kontext nutzt nicht den vorhandenen conv_action-Text"
    assert "cockpit-donut-caption" not in GR_SRC, \
        "cockpit-donut-caption noch im Render-Pfad (sollte relocated sein)"


def test_09_monster_still_neutral() -> None:
    assert "_MONSTER_NEUTRAL_COLOR" in GR_SRC, "Monster-Neutral-Farbe entfernt?"
    assert 'conf_key == "monster"' in GR_SRC and \
        "col = _MONSTER_NEUTRAL_COLOR" in GR_SRC, \
        "Monster-Pillar nicht mehr neutral gefärbt"


def test_10_badge_describes_score_not_stock() -> None:
    assert "beschreibt den Score, " in GR_SRC and "nicht die Aktie." in GR_SRC, \
        "Badge-Tooltip stellt Score-vs-Aktie nicht klar"


def test_11_every_entry_has_status_date() -> None:
    # Task-Punkt 9: kein undatierter Status. Jeder Eintrag MUSS ein
    # ISO-status_date tragen (Befund-Datum, nicht Render-Zeit).
    for k, v in config.SCORE_STATUS_LABELS.items():
        sd = v.get("status_date")
        assert isinstance(sd, str) and _ISO_RE.match(sd), \
            f"{k}: status_date fehlt/kein ISO-Datum ({sd!r})"
        # review_by ist entweder None oder ISO.
        rb = v.get("review_by")
        assert rb is None or (isinstance(rb, str) and _ISO_RE.match(rb)), \
            f"{k}: review_by weder None noch ISO ({rb!r})"
        # review_by None → review_cond muss die Bedingung dokumentieren.
        if rb is None:
            assert (v.get("review_cond") or "").strip(), \
                f"{k}: review_by None ohne review_cond-Begründung"


def test_12_single_source_no_validation_in_compute() -> None:
    # EXZELLENZ 1: has_auc darf NIRGENDS still weiterleben; compute liefert nur
    # die Daten-Dimension, KEINE Validierungs-Stufe mehr.
    assert "has_auc" not in GR_SRC, "has_auc lebt noch (Validierungs-Annahme!)"
    body = _fn_body("compute_score_confidence")
    for forbidden in ('"tier"', "'tier'", "robust"):
        assert forbidden not in body, \
            f"compute_score_confidence trägt noch Validierungs-Literal {forbidden!r}"
    # Positiv: liefert die Daten-Dimension.
    assert "data_tier" in body and "n_returns" in body, \
        "compute_score_confidence liefert keine Daten-Dimension mehr"


def test_13_conf_class_reads_single_source() -> None:
    # Karten-Wasserzeichen kommt aus derselben Quelle wie Badge + Panel.
    body = _fn_body("_conf_class")
    assert "SCORE_STATUS_LABELS.get(score_class)" in body, \
        "_conf_class liest den Validierungs-Status nicht aus SCORE_STATUS_LABELS"
    assert "_SCORE_CONFIDENCE" not in body, \
        "_conf_class hängt noch am alten _SCORE_CONFIDENCE-Tier (Drift-Quelle)"


def main() -> None:
    tests = [
        ("01 SCORE_STATUS_LABELS 6 Keys + status",      test_01_config_struct_present),
        ("02 Pflege-Pflicht-Kommentar",                 test_02_maintenance_comment),
        ("03 Helper liest config-Status",               test_03_helper_reads_config),
        ("04 kein Status-Value hardcoded",              test_04_no_hardcoded_status_value_in_template),
        ("05 Badges im Cockpit verdrahtet",             test_05_wired_into_cockpit),
        ("06 CSS-Klassen vorhanden",                    test_06_css_classes_present),
        ("07 Badge-Styling neutral (keine Ampel)",      test_07_badge_style_neutral),
        ("08 Rang-Kontext = vorhandener Text",          test_08_rank_context_reuses_existing_text),
        ("09 Monster weiterhin neutral",                test_09_monster_still_neutral),
        ("10 Badge beschreibt Score, nicht Aktie",      test_10_badge_describes_score_not_stock),
        ("11 jeder Eintrag mit status_date",            test_11_every_entry_has_status_date),
        ("12 Single-Source: kein has_auc/tier in compute", test_12_single_source_no_validation_in_compute),
        ("13 _conf_class liest SCORE_STATUS_LABELS",    test_13_conf_class_reads_single_source),
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
