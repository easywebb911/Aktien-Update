"""Mock-Tests fuer score()-Multiplier <-> SUB_*_DISPLAY_PTS_MAX-Sync.

Hintergrund: score() und _compute_sub_scores enthalten hartcodierte
Multiplier (z.B. `* 32`, `* 23`, `* 14`, `* 8`) die zu Konstanten in
config.py (SUB_*_DISPLAY_PTS_MAX) in Sync sein muessen. Heute alle
Werte synchron, aber kein Lint-Enforcement. Wenn jemand
SUB_RVOL_DISPLAY_PTS_MAX auf 25 aendert ohne score() mitzupflegen,
driftet Anzeige vs. Berechnung.

Loesung: AST-basierte Source-Inspektion. Test extrahiert alle
Multiplikations-Knoten aus den beiden Funktionen und vergleicht
gefundene Multiplier-Werte mit den deklarierten Konstanten.

Robust gegen spaetere Migration auf "Option A" (Konstanten statt
Literale): Multiplier kann sowohl int-Literal (`* 32`) als auch
Name-Lookup (`* SUB_SHORT_FLOAT_DISPLAY_PTS_MAX`) sein — Test
resolved Names ueber Konstanten-Dict.

Tests:
  1. score() Fall 1: 32 / 23 / 23 / 14 vorhanden (SF/DTC/RVOL/Mom)
  2. score() Fall 2: 30 / 20 vorhanden (separater no-short-Pfad,
     keine SUB_*-Konstante — bleibt hardcoded by design)
  3. _compute_sub_scores: 32 / 23 / 23 / 14 / 8 / 5 vorhanden
  4. FLOAT_WEIGHT == SUB_FLOAT_SIZE_DISPLAY_PTS_MAX (redundante
     Konstanten, muessen identisch sein)
  5. Alle SUB_*_DISPLAY_PTS_MAX-Werte aus config matchen mindestens
     einen Multiplier im Source
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR_SOURCE = (ROOT / "generate_report.py").read_text(encoding="utf-8")
CFG_SOURCE = (ROOT / "config.py").read_text(encoding="utf-8")


def _config_int_constants() -> dict[str, int]:
    """Parse config.py via AST, extrahiere alle int-Konstanten."""
    tree = ast.parse(CFG_SOURCE)
    consts: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, int):
                    consts[tgt.id] = node.value.value
    return consts


CFG = _config_int_constants()


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Funktion {name} nicht gefunden")


def _extract_int_multipliers(fn: ast.FunctionDef) -> list[int]:
    """Sammelt alle int-Werte, die in `expr * INT` oder `expr * NAME` (mit
    Name in config-Konstanten) vorkommen.

    Robust gegen beide Patterns: Literal (`* 32`) und Konstanten-Lookup
    (`* SUB_X_DISPLAY_PTS_MAX`).
    """
    values: list[int] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            # Rechts oder links kann der Multiplier sein
            for operand in (node.right, node.left):
                if isinstance(operand, ast.Constant) and isinstance(operand.value, int):
                    values.append(operand.value)
                elif isinstance(operand, ast.Name) and operand.id in CFG:
                    # Konstanten-Lookup → resolved Wert
                    values.append(CFG[operand.id])
    return values


GR_TREE = ast.parse(GR_SOURCE)
SCORE_FN = _find_function(GR_TREE, "score")
SUB_FN = _find_function(GR_TREE, "_compute_sub_scores")
SCORE_MULTIPLIERS = _extract_int_multipliers(SCORE_FN)
SUB_MULTIPLIERS = _extract_int_multipliers(SUB_FN)


def test_01_score_fall1_multipliers_present() -> None:
    # Fall 1 nutzt vier SUB_*_DISPLAY_PTS_MAX-Werte (SF/DTC/RVOL/Mom).
    # Test ist drift-resistent: liest aktuellen Konstanten-Wert aus
    # config.py und prueft Praesenz im score()-Source. Wenn jemand die
    # Konstante aendert, MUSS score() entsprechend mitgepflegt sein.
    required_constants = [
        "SUB_SHORT_FLOAT_DISPLAY_PTS_MAX",
        "SUB_DTC_DISPLAY_PTS_MAX",
        "SUB_RVOL_DISPLAY_PTS_MAX",
        "SUB_MOMENTUM_DISPLAY_PTS_MAX",
    ]
    for const_name in required_constants:
        cfg_val = CFG.get(const_name)
        assert cfg_val is not None, f"config.{const_name} nicht definiert"
        assert cfg_val in SCORE_MULTIPLIERS, (
            f"DRIFT: config.{const_name} = {cfg_val}, aber score() hat keinen "
            f"Multiplier mit diesem Wert. score()-Multiplier muessen aktualisiert "
            f"werden. Gefundene Multiplier in score(): "
            f"{sorted(set(SCORE_MULTIPLIERS))}")


def test_02_score_fall2_multipliers_present() -> None:
    # Fall 2 (kein-Short-Daten-Pfad): hardcoded 30/20 BY DESIGN,
    # keine SUB_*-Konstanten. Nur Praesenz pruefen.
    assert 30 in SCORE_MULTIPLIERS, (
        f"score() Fall 2 RVOL-Multiplier (30) fehlt. "
        f"Gefunden: {sorted(set(SCORE_MULTIPLIERS))}")
    assert 20 in SCORE_MULTIPLIERS, (
        f"score() Fall 2 Momentum-Multiplier (20) fehlt. "
        f"Gefunden: {sorted(set(SCORE_MULTIPLIERS))}")


def test_03_compute_sub_scores_multipliers_present() -> None:
    # _compute_sub_scores hat die volle Sub-Score-Skalierung. Test
    # drift-resistent (liest aktuelle Konstanten-Werte).
    required_constants = [
        "SUB_SHORT_FLOAT_DISPLAY_PTS_MAX",
        "SUB_DTC_DISPLAY_PTS_MAX",
        "SUB_RVOL_DISPLAY_PTS_MAX",
        "SUB_MOMENTUM_DISPLAY_PTS_MAX",
        "SUB_FLOAT_SIZE_DISPLAY_PTS_MAX",
        "SUB_SI_TREND_DISPLAY_PTS_MAX",
    ]
    for const_name in required_constants:
        cfg_val = CFG.get(const_name)
        assert cfg_val is not None, f"config.{const_name} nicht definiert"
        assert cfg_val in SUB_MULTIPLIERS, (
            f"DRIFT: config.{const_name} = {cfg_val}, aber _compute_sub_scores "
            f"hat keinen Multiplier mit diesem Wert. "
            f"Gefundene Multiplier: {sorted(set(SUB_MULTIPLIERS))}")


def test_04_float_weight_matches_sub_float_size() -> None:
    # Zwei redundante Konstanten fuer Float-Size — muessen identisch sein.
    fw = CFG.get("FLOAT_WEIGHT")
    sf = CFG.get("SUB_FLOAT_SIZE_DISPLAY_PTS_MAX")
    assert fw is not None, "FLOAT_WEIGHT nicht in config.py"
    assert sf is not None, "SUB_FLOAT_SIZE_DISPLAY_PTS_MAX nicht in config.py"
    assert fw == sf, (
        f"FLOAT_WEIGHT ({fw}) != SUB_FLOAT_SIZE_DISPLAY_PTS_MAX ({sf}). "
        "Beide Konstanten muessen identisch sein — Drift bedeutet score() "
        "und Methodik-Display zeigen unterschiedliche Float-Size-Maxima.")


def test_05_all_sub_display_constants_used() -> None:
    # Vollstaendigkeits-Check: jede SUB_*_DISPLAY_PTS_MAX-Konstante muss in
    # mindestens einer der beiden Funktionen als Multiplier auftauchen.
    # Fuer SI-Trend kann es auch ein direkter Dict-Wert sein (siehe Z. 3640
    # in _compute_sub_scores: `{"up": 5, ...}`). SI-Trend-Wert wird hier
    # auch als Konstante-Treffer akzeptiert weil 5 in SUB_MULTIPLIERS landet.
    combined = set(SCORE_MULTIPLIERS) | set(SUB_MULTIPLIERS)
    sub_consts = {name: val for name, val in CFG.items()
                  if name.startswith("SUB_") and name.endswith("_DISPLAY_PTS_MAX")}
    assert sub_consts, "Keine SUB_*_DISPLAY_PTS_MAX-Konstanten in config.py gefunden"
    for name, value in sub_consts.items():
        assert value in combined, (
            f"Konstante {name} = {value} taucht weder in score() noch in "
            f"_compute_sub_scores als Multiplier auf. "
            f"Entweder Konstante ungenutzt (entfernen) oder Multiplier "
            f"fehlt (drift). Combined-Multiplier: {sorted(combined)}")


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        ("01 score() Fall 1: 32/23/23/14",        test_01_score_fall1_multipliers_present),
        ("02 score() Fall 2: 30/20 (hardcoded)",  test_02_score_fall2_multipliers_present),
        ("03 _compute_sub_scores: alle Werte",    test_03_compute_sub_scores_multipliers_present),
        ("04 FLOAT_WEIGHT == SUB_FLOAT_SIZE_..",  test_04_float_weight_matches_sub_float_size),
        ("05 Alle SUB_*-Konstanten genutzt",      test_05_all_sub_display_constants_used),
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
