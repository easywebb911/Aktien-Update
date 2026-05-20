"""Mock-Test fuer Score-Delta T-1 im Cockpit-Setup-Pillar (20.05.2026).

Hintergrund: Cockpit-Migration PR #199 hat den frueheren ``_score_delta_html``
unsichtbar gemacht, weil das Cockpit-Pillar-Layout nicht durch
``_score_block_inner_html`` gerendert wird. Re-Apply: neuer Helper
``_cockpit_delta_html`` (gleiche Hybrid-Stille-Schwelle wie PR #170),
inline am Setup-Pillar.

Tests:
  1. Replik |Δ|<2 -> leer
  2. Replik |Δ|=3 -> mute
  3. Replik |Δ|=7 -> up + ▲
  4. Replik |Δ|=-7 -> down + ▼
  5. Replik |Δ|=18 -> up + strong
  6. Replik |Δ|=-22 -> down + strong
  7. Edge: 1 Score in History -> leer
  8. Edge: keine sparkline -> leer
  9. Edge: invalid scores (None, str) -> leer
 10. Tooltip enthaelt Vortags-Datum + Delta-Wert
 11. aria-label gesetzt
 12. Schwellen-Grenze |Δ|=2 -> mute (>= Schwelle)
 13. Source: _cockpit_delta_html-Signatur existiert
 14. Source: _card_cockpit_html ruft _cockpit_delta_html(s) auf
 15. Source: setup_delta_html nur fuer Setup-Pillar (conf_key == "setup")
 16. Source: {delta_html} im Pillar-Value-Div eingebunden
 17. Source: CSS-Klassen .cockpit-delta-* in head.jinja
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
HJ = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")


def _func_block(func_def: str) -> str:
    start = GR.find(func_def)
    assert start > 0, f"Funktion {func_def!r} nicht gefunden"
    end = GR.find("\ndef ", start + 10)
    assert end > start
    return GR[start:end]


# ── Pythonische Replikation ─────────────────────────────────────────────────

def _replicate_cockpit_delta(s: dict) -> str:
    """1:1-Replikat der _cockpit_delta_html-Logik."""
    spark  = s.get("sparkline") or {}
    scores = spark.get("scores") or []
    dates  = spark.get("dates")  or []
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
            f'{sign_pref}{delta:.1f}">{sign} {sign_pref}{delta:.1f}</span>')


def _stock(scores, dates=None):
    if dates is None:
        dates = [f"1{i}.05.2026" for i in range(len(scores))]
    return {"sparkline": {"scores": scores, "dates": dates}}


def test_01_below_silence_threshold() -> None:
    assert _replicate_cockpit_delta(_stock([52.59, 52.62])) == ""
    assert _replicate_cockpit_delta(_stock([50.0, 51.9])) == ""


def test_02_mute_variant() -> None:
    html = _replicate_cockpit_delta(_stock([50.0, 53.0]))
    assert "cockpit-delta-mute" in html
    assert "cockpit-delta-up" not in html
    assert "▲" in html
    assert "+3.0" in html


def test_03_up_variant() -> None:
    html = _replicate_cockpit_delta(_stock([50.0, 57.0],
                                          dates=["15.05.2026", "16.05.2026"]))
    assert "cockpit-delta-up" in html
    assert "cockpit-delta-mute" not in html
    assert "cockpit-delta-strong" not in html
    assert "▲" in html
    assert "+7.0" in html


def test_04_down_variant() -> None:
    html = _replicate_cockpit_delta(_stock([75.6, 68.6]))
    assert "cockpit-delta-down" in html
    assert "▼" in html
    assert "-7.0" in html


def test_05_strong_up() -> None:
    html = _replicate_cockpit_delta(_stock([50.0, 68.0]))
    assert "cockpit-delta-up" in html
    assert "cockpit-delta-strong" in html
    assert "+18.0" in html


def test_06_strong_down() -> None:
    html = _replicate_cockpit_delta(_stock([80.0, 58.0]))
    assert "cockpit-delta-down" in html
    assert "cockpit-delta-strong" in html
    assert "-22.0" in html


def test_07_one_day_history() -> None:
    assert _replicate_cockpit_delta(_stock([50.0])) == ""


def test_08_no_sparkline() -> None:
    assert _replicate_cockpit_delta({}) == ""
    assert _replicate_cockpit_delta({"sparkline": None}) == ""


def test_09_invalid_scores() -> None:
    s = {"sparkline": {"scores": [None, "abc"], "dates": ["x", "y"]}}
    assert _replicate_cockpit_delta(s) == ""


def test_10_tooltip_has_prev_date() -> None:
    html = _replicate_cockpit_delta(_stock([50.0, 57.0],
                                          dates=["15.05.2026", "16.05.2026"]))
    assert "title=" in html
    assert "15.05.2026" in html
    assert "ggü. letztem Daily-Run" in html
    assert "+7.0" in html


def test_11_aria_label_set() -> None:
    html = _replicate_cockpit_delta(_stock([50.0, 57.0]))
    assert 'aria-label="Delta +7.0"' in html


def test_12_boundary_exact_2() -> None:
    html = _replicate_cockpit_delta(_stock([50.0, 52.0]))
    assert html != "", "|Δ|=2 muss rendern (Schwelle ist <2 fuer leer)"
    assert "cockpit-delta-mute" in html


# ── Source-Inspektion ───────────────────────────────────────────────────────

def test_13_helper_exists() -> None:
    assert "def _cockpit_delta_html(s: dict)" in GR, \
        "Helper-Signatur fehlt"


def test_14_card_cockpit_calls_helper() -> None:
    block = _func_block("def _card_cockpit_html(")
    assert "_cockpit_delta_html(s)" in block, \
        "_card_cockpit_html ruft _cockpit_delta_html(s) nicht auf"
    assert "setup_delta_html" in block, \
        "Result-Variable setup_delta_html fehlt"


def test_15_delta_only_for_setup_pillar() -> None:
    block = _func_block("def _card_cockpit_html(")
    # Setup-Pillar-only-Gating via conf_key-Vergleich
    assert 'conf_key == "setup"' in block, \
        "Setup-Only-Gating fehlt — Delta wuerde auch auf Monster/KI rendern"
    # delta_html-Variable wird im Loop gesetzt
    m = re.search(r'delta_html\s*=\s*setup_delta_html\s+if\s+conf_key\s*==\s*"setup"',
                  block)
    assert m, "delta_html-Zuweisung im Pillar-Loop falsch oder fehlt"


def test_16_delta_in_pillar_value_div() -> None:
    block = _func_block("def _card_cockpit_html(")
    # Im Pillar-Value-Div: nach {fmt} muss {delta_html} folgen
    assert "{fmt}{delta_html}" in block, \
        "{delta_html} nicht am Pillar-Value-Div angehaengt (sollte nach {fmt})"


def test_17_css_classes_in_head_jinja() -> None:
    for cls in (".cockpit-delta{", ".cockpit-delta-up{",
                ".cockpit-delta-down{", ".cockpit-delta-mute{",
                ".cockpit-delta-strong{"):
        assert cls in HJ, f"CSS-Klasse {cls} fehlt in head.jinja"


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 |Δ|<2 -> leer",                       test_01_below_silence_threshold),
        ("02 |Δ|=3 -> mute",                       test_02_mute_variant),
        ("03 |Δ|=7 -> up + ▲",                test_03_up_variant),
        ("04 |Δ|=-7 -> down + ▼",             test_04_down_variant),
        ("05 |Δ|=18 -> up + strong",               test_05_strong_up),
        ("06 |Δ|=-22 -> down + strong",            test_06_strong_down),
        ("07 1-Tag-History -> leer",                    test_07_one_day_history),
        ("08 Keine sparkline -> leer",                  test_08_no_sparkline),
        ("09 Invalid scores -> leer",                   test_09_invalid_scores),
        ("10 Tooltip enthaelt Vortags-Datum",           test_10_tooltip_has_prev_date),
        ("11 aria-label gesetzt",                       test_11_aria_label_set),
        ("12 Schwellen-Grenze |Δ|=2 -> mute",      test_12_boundary_exact_2),
        ("13 _cockpit_delta_html-Signatur",             test_13_helper_exists),
        ("14 Cockpit ruft Helper auf",                  test_14_card_cockpit_calls_helper),
        ("15 Delta-Gating nur Setup-Pillar",            test_15_delta_only_for_setup_pillar),
        ("16 {delta_html} im Pillar-Value-Div",         test_16_delta_in_pillar_value_div),
        ("17 CSS-Klassen in head.jinja",                test_17_css_classes_in_head_jinja),
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
