"""Mock-Tests fuer Score-Delta T-1 (16.05.2026).

Hintergrund: Design-Berater-Empfehlung — prominent zeigen wenn Setup-
Score gegenueber gestern stark gestiegen oder gefallen ist. Easy
entscheidet ob Squeeze "ignition" oder "sterbend".

Hybrid-Stille-Schwelle:
  - |Δ| < 2:  leerer String (kein visueller Laerm bei Mini-Drifts)
  - |Δ| 2..5: dezent grau (.sb-delta-mute)
  - |Δ| ≥ 5:  farbig gruen/rot mit ▲/▼ (.sb-delta-up/-down)
  - |Δ| ≥ 15: zusaetzlich Bold (.sb-delta-strong)

Quelle: s["sparkline"]["scores"] — raw Setup-Scores aus
score_history.json, materialisiert vom Daily-Run.

Tests (Source + pythonische Replikation):
  1. Source: _score_delta_html existiert mit korrekter Signatur
  2. Source: Setup-Row wendet _score_delta_html(s) an
  3. Source: Andere Rows (Conviction/Monster/KI) bekommen KEIN Delta
  4. Source: CSS-Klassen in head.jinja
  5. Replik: |Δ|<2 -> leerer String
  6. Replik: Δ=3 -> mute-Variante
  7. Replik: Δ=7 -> up-Klasse + Farbe + ▲
  8. Replik: Δ=-7 -> down-Klasse + Farbe + ▼
  9. Replik: Δ=18 -> up-Klasse + strong-Modifier
 10. Replik: Δ=-22 -> down-Klasse + strong-Modifier
 11. Replik: Edge: nur 1 Score in History -> leerer String
 12. Replik: Edge: keine sparkline -> leerer String
 13. Replik: Edge: sparkline mit None-scores -> leerer String
 14. Tooltip enthaelt Vortags-Datum und Delta-Wert
 15. aria-label gesetzt
 16. Stille-Schwellen-Grenze: |Δ|=2 -> wird gerendert (>= Schwelle)
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
    assert "def _score_delta_html(s: dict)" in GR, "Helper-Signatur fehlt"


def test_02_setup_row_uses_delta() -> None:
    block = _func_block("def _score_block_inner_html(")
    # _score_delta_html(s) wird aufgerufen + Resultat im Setup-Row-HTML
    assert "_score_delta_html(s)" in block, "Helper-Call fehlt"
    assert "s_delta_html" in block, "Result-Variable fehlt"
    # Setup-Row enthaelt {s_delta_html} zwischen .sb-num und .sb-lbl
    setup_idx = block.find('data-sb="setup"')
    assert setup_idx > 0
    setup_html = block[setup_idx:setup_idx + 500]
    # Reihenfolge sb-num -> s_delta_html -> sb-lbl
    num_pos = setup_html.find("sb-num")
    delta_pos = setup_html.find("{s_delta_html}")
    lbl_pos = setup_html.find("sb-lbl")
    assert num_pos > 0 and delta_pos > 0 and lbl_pos > 0
    assert num_pos < delta_pos < lbl_pos, \
        f"Reihenfolge im Setup-Row falsch: num={num_pos}, delta={delta_pos}, lbl={lbl_pos}"


def test_03_other_rows_no_delta() -> None:
    block = _func_block("def _score_block_inner_html(")
    # Conviction / Monster / KI duerfen KEIN s_delta_html haben
    for sb in ("conviction", "monster", "ki"):
        idx = block.find(f'data-sb="{sb}"')
        if idx < 0:
            continue
        section = block[idx:idx + 500]
        assert "{s_delta_html}" not in section, \
            f"{sb}-Row enthaelt Delta — Phase 1 ist nur Setup-Score"


def test_04_css_classes_in_head_jinja() -> None:
    for cls in (".sb-delta{", ".sb-delta-up{", ".sb-delta-down{",
                ".sb-delta-mute{", ".sb-delta-strong{"):
        assert cls in HJ, f"CSS-Klasse {cls} fehlt in head.jinja"


# ── Pythonische Replikation ─────────────────────────────────────────────────

def _replicate_score_delta(s: dict) -> str:
    """1:1-Replikat der _score_delta_html-Logik."""
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
        css = "sb-delta sb-delta-mute"
    else:
        css = "sb-delta sb-delta-up" if delta > 0 else "sb-delta sb-delta-down"
        if abs_d >= 15:
            css += " sb-delta-strong"
    title = (f"Δ {sign_pref}{delta:.1f} ggü. letztem Daily-Run "
             f"({prev_date}, raw {prev_raw:.1f} → {today_raw:.1f})")
    return (f'<span class="{css}" title="{title}" aria-label="Delta '
            f'{sign_pref}{delta:.1f}">{sign} {sign_pref}{delta:.1f}</span>')


def _stock(scores, dates=None):
    if dates is None:
        dates = [f"1{i}.05.2026" for i in range(len(scores))]
    return {"sparkline": {"scores": scores, "dates": dates}}


def test_05_below_silence_threshold() -> None:
    # |Δ|=0.03 wie CRMD heute
    s = _stock([52.59, 52.62])
    assert _replicate_score_delta(s) == "", "Mini-Drift muss leer sein"
    # |Δ|=1.9 — knapp unter 2
    s2 = _stock([50.0, 51.9])
    assert _replicate_score_delta(s2) == ""


def test_06_mute_variant() -> None:
    # |Δ|=3 → grau
    s = _stock([50.0, 53.0])
    html = _replicate_score_delta(s)
    assert "sb-delta-mute" in html
    assert "sb-delta-up" not in html
    assert "▲" in html
    assert "+3.0" in html


def test_07_up_variant() -> None:
    # |Δ|=7
    s = _stock([50.0, 57.0], dates=["15.05.2026", "16.05.2026"])
    html = _replicate_score_delta(s)
    assert "sb-delta-up" in html
    assert "sb-delta-mute" not in html
    assert "sb-delta-strong" not in html
    assert "▲" in html
    assert "+7.0" in html


def test_08_down_variant() -> None:
    # Δ=-7 (CRMD Earnings-Sell-the-news Pattern)
    s = _stock([75.6, 68.6])
    html = _replicate_score_delta(s)
    assert "sb-delta-down" in html
    assert "▼" in html
    assert "-7.0" in html
    assert "+" not in html.replace("color:", "").replace("aria-label=\"Delta -", "")


def test_09_strong_up() -> None:
    # |Δ|=18 → up + strong
    s = _stock([50.0, 68.0])
    html = _replicate_score_delta(s)
    assert "sb-delta-up" in html
    assert "sb-delta-strong" in html
    assert "+18.0" in html


def test_10_strong_down() -> None:
    # Δ=-22 → down + strong
    s = _stock([80.0, 58.0])
    html = _replicate_score_delta(s)
    assert "sb-delta-down" in html
    assert "sb-delta-strong" in html
    assert "-22.0" in html


def test_11_one_day_history() -> None:
    s = _stock([50.0])
    assert _replicate_score_delta(s) == ""


def test_12_no_sparkline() -> None:
    assert _replicate_score_delta({}) == ""
    assert _replicate_score_delta({"sparkline": None}) == ""


def test_13_invalid_scores() -> None:
    s = {"sparkline": {"scores": [None, "abc"], "dates": ["x", "y"]}}
    # None oder str -> ValueError → leer
    assert _replicate_score_delta(s) == ""


def test_14_tooltip_has_prev_date() -> None:
    s = _stock([50.0, 57.0], dates=["15.05.2026", "16.05.2026"])
    html = _replicate_score_delta(s)
    assert 'title=' in html
    assert "15.05.2026" in html
    assert "ggü. letztem Daily-Run" in html
    assert "+7.0" in html


def test_15_aria_label_set() -> None:
    s = _stock([50.0, 57.0])
    html = _replicate_score_delta(s)
    assert 'aria-label="Delta +7.0"' in html


def test_16_boundary_exact_2() -> None:
    # |Δ|=2.0 → rendert (>= Schwelle) als mute
    s = _stock([50.0, 52.0])
    html = _replicate_score_delta(s)
    assert html != "", "|Δ|=2 muss rendern (Schwelle ist <2 für leer)"
    assert "sb-delta-mute" in html


# ── CLAUDE.md ────────────────────────────────────────────────────────────────

def test_17_claude_md_section() -> None:
    assert "Score-Delta T-1" in CMD, "CLAUDE.md-Sektion fehlt"
    # Schwellen dokumentiert
    assert "|Δ|" in CMD or "Stille-Schwelle" in CMD
    # Folge-PR-Wiedervorlage erwaehnt
    assert "conviction_history" in CMD or "History-Persistenz" in CMD


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 _score_delta_html-Signatur",         test_01_helper_exists),
        ("02 Setup-Row nutzt Helper",             test_02_setup_row_uses_delta),
        ("03 Andere Rows kein Delta",             test_03_other_rows_no_delta),
        ("04 CSS-Klassen in head.jinja",          test_04_css_classes_in_head_jinja),
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
