"""Mock-Tests für Methodik-Display (versteckte Boni sichtbar gemacht).

Inventur 14.05.2026 fand drei Lücken im Methodik-Block:
  1. Borrow-Rate-Bonus (+8/+15) komplett unsichtbar
  2. Float-Turnover als 3-Tier (3/6/10), Display zeigte nur HIGH
  3. UOA-Aggregat 30 verschluckte die Aufschlüsselung
     ATM-weak (10) / strong (20) + C/P-Bias (10)

Source-Inspektion-Tests gegen die _build_context-Methodik-Zeilen.
Konstanten in config.py bleiben unverändert (nur Display-Strings).

Ausführung: ``python scripts/mock_test_methodology_display.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")

from config import (   # noqa: E402
    FLOAT_TURNOVER_HIGH,
    FLOAT_TURNOVER_LOW,
    FLOAT_TURNOVER_MID,
    FLOAT_TURNOVER_PTS_HIGH,
    FLOAT_TURNOVER_PTS_LOW,
    FLOAT_TURNOVER_PTS_MID,
    IBKR_BORROW_BONUS_EXTREME,
    IBKR_BORROW_BONUS_HOT,
    IBKR_BORROW_HIGH,
    UOA_ATM_STRONG,
    UOA_ATM_WEAK,
    UOA_CP_BIAS,
)


def _methodology_block() -> str:
    """Extrahiert den Methodik-Build-Block (zwischen `_ABBR_RVOL` und
    `_methodology_rows_html`-Ende für timing_rows)."""
    start = SRC.find('_ABBR_RVOL          = ')
    assert start > 0, "Methodik-Block nicht gefunden"
    end_anchor = "methodology_timing_rows = _methodology_rows_html("
    end_idx = SRC.find(end_anchor, start)
    assert end_idx > start, "timing-Block-Ende nicht gefunden"
    # bis zur schließenden Klammer
    close = SRC.find("\n    ])", end_idx)
    return SRC[start:close + 20]


# === 1 — Borrow-Rate-Zeile in Katalysator-Box ============================


def test_borrow_rate_row_present():
    """Borrow-Rate-Zeile in methodology_catalyst_rows."""
    block = _methodology_block()
    assert "Borrow-Rate p.a." in block, (
        "Borrow-Rate-Zeile fehlt in Katalysator-Methodik-Box")


def test_borrow_rate_shows_both_thresholds():
    """Display-Template enthält +N-Interpolation für beide Boni-Konstanten +
    die Schwellen-Texte >50/>100. Wir matchen gegen den RAW f-string-Source
    (mit {KONSTANTE}-Platzhaltern), nicht gegen rendered HTML."""
    block = _methodology_block()
    # f-string-Templates für die +N-Anteile
    assert "+{IBKR_BORROW_BONUS_HOT}" in block, (
        "+{IBKR_BORROW_BONUS_HOT}-Template fehlt im Display")
    assert "+{IBKR_BORROW_BONUS_EXTREME}" in block, (
        "+{IBKR_BORROW_BONUS_EXTREME}-Template fehlt")
    # Schwellen-Templates: int(IBKR_BORROW_HIGH) für 50 %, hardcoded 100 für extrem
    assert "{int(IBKR_BORROW_HIGH)}" in block, (
        "IBKR_BORROW_HIGH-Schwellen-Interpolation fehlt")
    assert "&gt;100" in block, "Schwelle >100 % fehlt"


def test_borrow_rate_uses_constants_not_hardcoded():
    """Display referenziert die Konstanten (keine magischen 8/15-
    Literals außerhalb der f-String-Interpolation)."""
    block = _methodology_block()
    # Anker für die Borrow-Zeile
    borrow_idx = block.find("Borrow-Rate p.a.")
    assert borrow_idx > 0
    borrow_chunk = block[borrow_idx:borrow_idx + 400]
    assert "IBKR_BORROW_BONUS_HOT" in borrow_chunk
    assert "IBKR_BORROW_BONUS_EXTREME" in borrow_chunk


# === 2 — Float-Turnover-Tiers sichtbar ===================================


def test_float_turnover_shows_all_three_tiers():
    """Display-Template referenziert alle 3 Punkt-Konstanten in der
    LOW / MID / HIGH-Reihenfolge. Source-Inspektion ist tolerant gegen
    Multi-line f-String-Fragmentierung (Quote+Newline+Indent zwischen
    den Templates)."""
    block = _methodology_block()
    pat = re.compile(
        r"\{FLOAT_TURNOVER_PTS_LOW\}\s*/\s*\{FLOAT_TURNOVER_PTS_MID\}\s*/"
        r".{0,80}?\{FLOAT_TURNOVER_PTS_HIGH\}",
        re.DOTALL,
    )
    assert pat.search(block), (
        "Float-Turnover-Tier-Templates LOW/MID/HIGH fehlen oder falsche "
        "Reihenfolge")


def test_float_turnover_shows_threshold_ratios():
    """Vol/Float-Schwellen :g-Format-Interpolation für 0.5/1.0/2.0
    via FLOAT_TURNOVER_LOW/MID/HIGH-Konstanten."""
    block = _methodology_block()
    pat = re.compile(
        r"\{FLOAT_TURNOVER_LOW:g\}\s*/\s*\{FLOAT_TURNOVER_MID:g\}\s*/"
        r".{0,80}?\{FLOAT_TURNOVER_HIGH:g\}",
        re.DOTALL,
    )
    assert pat.search(block), (
        "Schwellen-Template :g-Interpolation der drei FLOAT_TURNOVER-"
        "Schwellen fehlt")
    # Render-Smoke: tatsaechlich evaluierter String "0.5/1/2"
    rendered = f"{FLOAT_TURNOVER_LOW:g}/{FLOAT_TURNOVER_MID:g}/{FLOAT_TURNOVER_HIGH:g}"
    assert rendered == "0.5/1/2", (
        f"Konstanten-Werte haben sich geaendert — Test-Erwartung "
        f"war 0.5/1/2, got {rendered!r}")


def test_float_turnover_uses_constants():
    block = _methodology_block()
    fl_idx = block.find('"Float Turnover"')
    assert fl_idx > 0
    chunk = block[fl_idx:fl_idx + 400]
    # alle 6 Konstanten verbaut
    for name in ("FLOAT_TURNOVER_PTS_LOW", "FLOAT_TURNOVER_PTS_MID",
                 "FLOAT_TURNOVER_PTS_HIGH",
                 "FLOAT_TURNOVER_LOW", "FLOAT_TURNOVER_MID",
                 "FLOAT_TURNOVER_HIGH"):
        assert name in chunk, f"{name} nicht in Float-Turnover-Display"


# === 3 — UOA-Aufschlüsselung als <abbr>-Tooltip ===========================


def test_uoa_breakdown_abbr_defined():
    """`_ABBR_UOA_BREAKDOWN`-Konstante existiert und enthaelt
    Templates fuer alle drei Komponenten (weak/strong/Bias).

    Tolerant gegen f-String-Fragmentierung — Source bricht den Tooltip-
    Text über mehrere Quote-Linien um, was substring-matching ohne
    Whitespace-Toleranz verfehlen wuerde."""
    block = _methodology_block()
    assert "_ABBR_UOA_BREAKDOWN" in block, (
        "_ABBR_UOA_BREAKDOWN-Helper fehlt")
    # 1: weak ({UOA_ATM_WEAK} Pkt) — direkt zusammenhaengend
    assert "weak ({UOA_ATM_WEAK} Pkt)" in block, (
        "weak-Komponente fehlt im Tooltip")
    # 2: 'strong' und {UOA_ATM_STRONG} sind durch Quote+Newline+Indent
    # getrennt. Tolerantes Match — bis zu 50 Zeichen Trenn-Text.
    pat_strong = re.compile(
        r"strong\b.{0,50}?\(\{UOA_ATM_STRONG\}\s+Pkt\)",
        re.DOTALL,
    )
    assert pat_strong.search(block), "strong-Komponente fehlt im Tooltip"
    # 3: Call/Put-Bias ({UOA_CP_BIAS} Pkt) — gleicher Trick
    pat_bias = re.compile(
        r"Call/Put-Bias\s*\(\{UOA_CP_BIAS\}\s+Pkt\)",
        re.DOTALL,
    )
    assert pat_bias.search(block), "Bias-Komponente fehlt im Tooltip"


def test_uoa_row_uses_breakdown_abbr():
    """Die UOA-Zeile in catalyst_rows nutzt den neuen <abbr>-Helper."""
    block = _methodology_block()
    # UOA-Zeile findet abbr-Wrap auf die "30"
    uoa_idx = block.find("ATM Vol/OI &amp; C/P-Bias")
    assert uoa_idx > 0
    chunk = block[uoa_idx:uoa_idx + 200]
    assert "_ABBR_UOA_BREAKDOWN" in chunk, (
        "UOA-Zeile nutzt den Tooltip-Helper nicht")


def test_uoa_breakdown_is_abbr_tag():
    """Helper ist als <abbr>-Tag konstruiert (nicht plain text)."""
    block = _methodology_block()
    abbr_def_idx = block.find("_ABBR_UOA_BREAKDOWN = ")
    assert abbr_def_idx > 0
    # Muster: title="..." enthält "ATM Vol/OI"
    pat = re.compile(r'<abbr title="ATM Vol/OI [^"]*">', re.DOTALL)
    assert pat.search(block), "_ABBR_UOA_BREAKDOWN ist kein gültiger <abbr>-Tag"


# === 4 — Backend-Logik unverändert (Vorsichts-Prinzip) ===================


def test_constants_in_config_unchanged():
    """config.py-Werte sind die unveraenderten Inventur-Werte."""
    assert IBKR_BORROW_BONUS_HOT == 8
    assert IBKR_BORROW_BONUS_EXTREME == 15
    assert FLOAT_TURNOVER_PTS_LOW == 3
    assert FLOAT_TURNOVER_PTS_MID == 6
    assert FLOAT_TURNOVER_PTS_HIGH == 10
    assert UOA_ATM_WEAK == 10
    assert UOA_ATM_STRONG == 20
    assert UOA_CP_BIAS == 10


def test_compute_sub_scores_signature_intact():
    """Backend-Score-Logik unveraendert (Vorsichts-Prinzip): wir checken
    dass `_compute_sub_scores` weiterhin existiert und die kritischen
    Konstanten-Reads (IBKR_BORROW_BONUS_*) noch da sind."""
    assert "def _compute_sub_scores" in SRC
    assert "IBKR_BORROW_BONUS_EXTREME" in SRC
    assert "IBKR_BORROW_BONUS_HOT" in SRC


def test_drivers_block_unchanged():
    """Driver-Block der Detail-Card zeigt die Werte bereits korrekt — wir
    haben nichts dort angefasst. Anker-Check: die Borrow-Driver-Eintraege
    mit `float(IBKR_BORROW_BONUS_*)` als weight existieren weiterhin."""
    # Heuristisch: beide Konstanten-Namen mit `float(...)`-Wrapping muessen
    # im SRC vorhanden sein (sind Bestandteil der _drivers_breakdown-Liste).
    assert "float(IBKR_BORROW_BONUS_EXTREME)" in SRC, (
        "IBKR_BORROW_BONUS_EXTREME nicht mehr als Driver-weight referenziert")
    assert "float(IBKR_BORROW_BONUS_HOT)" in SRC, (
        "IBKR_BORROW_BONUS_HOT nicht mehr als Driver-weight referenziert")
    assert "def _drivers_breakdown" in SRC, (
        "_drivers_breakdown-Funktion ist verschwunden")


# === 5 — JS-Template-Var-Pflichtcheck ====================================


def test_no_unescaped_js_template_vars():
    hits = re.findall(r"\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}", SRC)
    assert not hits, f"Unescapte JS-Template-Vars: {hits[:5]}"


# === Runner ==============================================================


def main() -> None:
    tests = [
        # Borrow-Rate
        ("Borrow-Rate-Zeile in Catalyst-Box vorhanden",  test_borrow_rate_row_present),
        ("Borrow-Rate zeigt +8 + +15 + Schwellen",       test_borrow_rate_shows_both_thresholds),
        ("Borrow-Rate referenziert config-Konstanten",   test_borrow_rate_uses_constants_not_hardcoded),
        # Float-Turnover
        ("Float-Turnover 3-Tier-Display (3 / 6 / 10)",   test_float_turnover_shows_all_three_tiers),
        ("Float-Turnover Schwellen 0.5/1/2 sichtbar",    test_float_turnover_shows_threshold_ratios),
        ("Float-Turnover nutzt 6 Konstanten",            test_float_turnover_uses_constants),
        # UOA
        ("_ABBR_UOA_BREAKDOWN definiert + Komponenten",  test_uoa_breakdown_abbr_defined),
        ("UOA-Zeile nutzt _ABBR_UOA_BREAKDOWN",          test_uoa_row_uses_breakdown_abbr),
        ("_ABBR_UOA_BREAKDOWN ist <abbr>-Tag",            test_uoa_breakdown_is_abbr_tag),
        # Vorsichts-Prinzip
        ("config-Konstanten unveraendert",                test_constants_in_config_unchanged),
        ("_compute_sub_scores intact",                    test_compute_sub_scores_signature_intact),
        ("_drivers_breakdown intact",                     test_drivers_block_unchanged),
        # JS-Template-Pflichtcheck
        ("Keine unescapten ${...} im f-String",          test_no_unescaped_js_template_vars),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {name}\n      {exc}")
        except Exception as exc:
            failed += 1
            print(f"  ✗ {name}\n      Unexpected: {type(exc).__name__}: {exc}")
    print()
    if failed:
        print(f"{failed} Test(s) fehlgeschlagen.")
        sys.exit(1)
    print(f"{len(tests)} Tests bestanden.")
    sys.exit(0)


if __name__ == "__main__":
    main()
