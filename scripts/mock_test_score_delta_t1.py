"""Mock-Tests fuer Score-Delta T-1 (16.05.2026, migriert 19.05.2026).

Hintergrund: Design-Berater-Empfehlung — prominent zeigen wenn Setup-
Score gegenueber gestern stark gestiegen oder gefallen ist. Easy
entscheidet ob Squeeze "ignition" oder "sterbend".

Hybrid-Stille-Schwelle:
  - |Δ| < 2:  leerer String (kein visueller Laerm bei Mini-Drifts)
  - |Δ| 2..5: dezent grau (.cockpit-delta-mute)
  - |Δ| ≥ 5:  farbig gruen/rot mit ▲/▼ (.cockpit-delta-up/-down)
  - |Δ| ≥ 15: zusaetzlich Bold (.cockpit-delta-strong)

Quelle: s["sparkline"]["scores"] — raw Setup-Scores aus
score_history.json, materialisiert vom Daily-Run.

Migration 19.05.2026: Helper hieß früher _score_delta_html, lebte in
_score_block_inner_html. Beide Funktionen + .sb-delta-* CSS wurden mit
Pre-Cockpit-Fallback entfernt. Logik unverändert, jetzt in
_cockpit_delta_html, im Setup-Pillar von _card_cockpit_html eingebettet,
CSS-Klassen .cockpit-delta-*.

Tests (Source + pythonische Replikation):
  1. Source: _cockpit_delta_html existiert mit korrekter Signatur
  2. Source: Setup-Pillar wendet _cockpit_delta_html(s) an
  3. Source: Andere Pillars (Monster/KI) bekommen KEIN Delta
  4. Source: CSS-Klassen .cockpit-delta-* in head.jinja
  5-16. Replik: Hybrid-Schwellen-Verhalten
  17. CLAUDE.md-Sektion vorhanden
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


# ── Source-Inspektion ────────────────────────────────────────────────────────

def test_01_helper_exists() -> None:
    assert "def _cockpit_delta_html(s: dict)" in GR, "Helper-Signatur fehlt"


def test_02_setup_pillar_uses_delta() -> None:
    block = _func_block("def _card_cockpit_html(")
    # _cockpit_delta_html(s) wird aufgerufen + setup_delta_html-Variable
    assert "_cockpit_delta_html(s)" in block, "Helper-Call fehlt"
    assert "setup_delta_html" in block, "Result-Variable fehlt"
    # Setup-Pillar bekommt delta_html im Pillar-Value
    assert 'conf_key == "setup"' in block, \
        "Setup-spezifische Bedingung fehlt"
    assert "{delta_html}" in block, \
        "delta_html nicht im Pillar-Value-Markup eingebettet"


def test_03_other_pillars_no_delta() -> None:
    block = _func_block("def _card_cockpit_html(")
    # Pillar-Loop hat eine Bedingung 'if conf_key == "setup" else ""'
    # — d.h. nur Setup-Pillar bekommt setup_delta_html, andere ""
    # Wir prüfen direkt das else-leerer-String-Pattern
    assert 'if conf_key == "setup" else ""' in block, \
        "Pillar-Loop sollte nur Setup-Pillar mit Delta versorgen"


def test_04_css_classes_in_head_jinja() -> None:
    for cls in (".cockpit-delta{", ".cockpit-delta-up{",
                ".cockpit-delta-down{", ".cockpit-delta-mute{",
                ".cockpit-delta-strong{"):
        assert cls in HJ, f"CSS-Klasse {cls} fehlt in head.jinja"


# ── Pythonische Replikation ─────────────────────────────────────────────────

def _replicate_cockpit_delta(s: dict) -> str:
    """1:1-Replikat der _cockpit_delta_html-Logik."""
    spark = s.get("sparkline") or {}
    scores = spark.get("scores") or []
    dates = spark.get("dates") or []
    if len(scores) < 2:
        return ""
    try:
        today_raw = float(scores[-1])
        prev_raw  = float(scores[-2])
    except (TypeError, ValueError):
        return ""
    delta = today_raw - prev_raw
    abs_d = abs(delta)
    if abs_d < 2:
        return ""
    prev_date = dates[-2] if len(dates) >= 2 else "—"
    sign      = "▲" if delta > 0 else "▼"
    sign_pref = "+"  if delta > 0 else ""
    if abs_d < 5:
        css = "cockpit-delta cockpit-delta-mute"
    else:
        css = ("cockpit-delta cockpit-delta-up" if delta > 0
               else "cockpit-delta cockpit-delta-down")
        if abs_d >= 15:
            css += " cockpit-delta-strong"
    title = (f"Δ {sign_pref}{delta:.1f} ggü. letztem Daily-Run "
             f"({prev_date}, raw {prev_raw:.1f} → {today_raw:.1f})")
    return (f'<span class="{css}" title="{title}" aria-label="Delta '
            f'{sign_pref}{delta:.1f}">{sign}{sign_pref}{delta:.1f}</span>')


def _stock(scores, dates=None):
    if dates is None:
        dates = [f"1{i}.05.2026" for i in range(len(scores))]
    return {"sparkline": {"scores": scores, "dates": dates}}


def test_05_below_silence_threshold() -> None:
    s = _stock([52.59, 52.62])
    assert _replicate_cockpit_delta(s) == "", "Mini-Drift muss leer sein"
    s2 = _stock([50.0, 51.9])
    assert _replicate_cockpit_delta(s2) == ""


def test_06_mute_variant() -> None:
    s = _stock([50.0, 53.0])
    html = _replicate_cockpit_delta(s)
    assert "cockpit-delta-mute" in html
    assert "cockpit-delta-up" not in html
    assert "▲" in html
    assert "+3.0" in html


def test_07_up_variant() -> None:
    s = _stock([50.0, 57.0], dates=["15.05.2026", "16.05.2026"])
    html = _replicate_cockpit_delta(s)
    assert "cockpit-delta-up" in html
    assert "cockpit-delta-mute" not in html
    assert "cockpit-delta-strong" not in html
    assert "▲" in html
    assert "+7.0" in html


def test_08_down_variant() -> None:
    s = _stock([75.6, 68.6])
    html = _replicate_cockpit_delta(s)
    assert "cockpit-delta-down" in html
    assert "▼" in html
    assert "-7.0" in html


def test_09_strong_up() -> None:
    s = _stock([50.0, 68.0])
    html = _replicate_cockpit_delta(s)
    assert "cockpit-delta-up" in html
    assert "cockpit-delta-strong" in html
    assert "+18.0" in html


def test_10_strong_down() -> None:
    s = _stock([80.0, 58.0])
    html = _replicate_cockpit_delta(s)
    assert "cockpit-delta-down" in html
    assert "cockpit-delta-strong" in html
    assert "-22.0" in html


def test_11_one_day_history() -> None:
    s = _stock([50.0])
    assert _replicate_cockpit_delta(s) == ""


def test_12_no_sparkline() -> None:
    assert _replicate_cockpit_delta({}) == ""
    assert _replicate_cockpit_delta({"sparkline": None}) == ""


def test_13_invalid_scores() -> None:
    s = {"sparkline": {"scores": [None, "abc"], "dates": ["x", "y"]}}
    assert _replicate_cockpit_delta(s) == ""


def test_14_tooltip_has_prev_date() -> None:
    s = _stock([50.0, 57.0], dates=["15.05.2026", "16.05.2026"])
    html = _replicate_cockpit_delta(s)
    assert 'title=' in html
    assert "15.05.2026" in html
    assert "ggü. letztem Daily-Run" in html
    assert "+7.0" in html


def test_15_aria_label_set() -> None:
    s = _stock([50.0, 57.0])
    html = _replicate_cockpit_delta(s)
    assert 'aria-label="Delta +7.0"' in html


def test_16_boundary_exact_2() -> None:
    s = _stock([50.0, 52.0])
    html = _replicate_cockpit_delta(s)
    assert html != "", "|Δ|=2 muss rendern (Schwelle ist <2 für leer)"
    assert "cockpit-delta-mute" in html


# ── CLAUDE.md ────────────────────────────────────────────────────────────────

def test_17_claude_md_section() -> None:
    assert "Score-Delta T-1" in CMD, "CLAUDE.md-Sektion fehlt"
    assert "|Δ|" in CMD or "Stille-Schwelle" in CMD
    assert "conviction_history" in CMD or "History-Persistenz" in CMD


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 _cockpit_delta_html-Signatur",       test_01_helper_exists),
        ("02 Setup-Pillar nutzt Helper",          test_02_setup_pillar_uses_delta),
        ("03 Andere Pillars kein Delta",          test_03_other_pillars_no_delta),
        ("04 CSS-Klassen .cockpit-delta-*",       test_04_css_classes_in_head_jinja),
        ("05 |Δ|<2 → leer",                       test_05_below_silence_threshold),
        ("06 |Δ|=3 → mute",                       test_06_mute_variant),
        ("07 |Δ|=7 → up + ▲",                     test_07_up_variant),
        ("08 |Δ|=-7 → down + ▼",                  test_08_down_variant),
        ("09 |Δ|=18 → up + strong",               test_09_strong_up),
        ("10 |Δ|=-22 → down + strong",            test_10_strong_down),
        ("11 1-Tag-History → leer",               test_11_one_day_history),
        ("12 Keine sparkline → leer",             test_12_no_sparkline),
        ("13 Invalid scores → leer",              test_13_invalid_scores),
        ("14 Tooltip enthaelt Vortags-Datum",     test_14_tooltip_has_prev_date),
        ("15 aria-label gesetzt",                 test_15_aria_label_set),
        ("16 Schwellen-Grenze |Δ|=2 → mute",      test_16_boundary_exact_2),
        ("17 CLAUDE.md-Sektion",                  test_17_claude_md_section),
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
