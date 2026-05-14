"""Lint: ``score_confidence`` darf NICHT von Score-Berechnungs-Pfaden gelesen
werden.

Hintergrund: Stufe-1-PR (Score-Konfidenz-Tiers) zeigt qualitative
Vertrauens-Stufen im Methodik-Panel. **Reine Anzeige.** Wenn die Stufen
in die Score- oder Conviction-Berechnung einfließen würden, würde das
Tool sich selbst belohnen („hohe Konfidenz → höhere Conviction →
höhere Konfidenz") und die externe Methodik-Bewertung wäre wertlos.

Dieser Linter scannt eine Allow-Liste kritischer Berechnungs-Funktionen
in ``generate_report.py`` und prüft, dass keine davon
``score_confidence`` / ``_SCORE_CONFIDENCE`` / ``compute_score_confidence``
referenziert.

Erweitern bei neuen Score-Berechnungs-Pfaden:
``_FORBIDDEN_FUNCS`` ergänzen.

Exit-Code 0 = OK, 1 = Fail. Bei Fail wird die verbotene Stelle (Funktion +
Zeile + Match) geloggt.

Workflow-Integration: Step im daily-squeeze-report.yml, vor
``Generate squeeze report`` (analog ``lint_jsformat_escape.py``).
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


# Funktionen, die KEINE Score-Konfidenz lesen dürfen. Bei neuen Score-
# Berechnungs-Pfaden ergänzen.
_FORBIDDEN_FUNCS = (
    "compute_conviction_score",
    "apply_conviction_scores",
    "compute_earliness_pts",
    "_earliness_pts_v1",
    "_earliness_pts_v2",
    "score",                       # generate_report.score() (Top-Level)
    "score_bonus",
    "apply_monster_score",
    "apply_agent_boost",
    "apply_late_runner_penalty",
    "apply_score_smoothing",
    "_compute_sub_scores",
    "_drivers_breakdown",
    "compute_exit_score",
    "process_exit_signals",
)

# Pattern, das einen Konfidenz-Reader markiert. Wir matchen sowohl die
# Modul-Variable, das Stock-Dict-Feld als auch die Helper-Funktion.
_READER_PATTERN = re.compile(
    r"_SCORE_CONFIDENCE"                # Modul-Variable
    r"|score_confidence"                # Feld-Lookup oder Variable
    r"|compute_score_confidence",       # Helper-Aufruf
)


def _extract_function_body(src: str, func_name: str) -> tuple[int, str] | None:
    """Liefert ``(start_lineno, body)`` der Funktion oder None.

    Body = von ``def <name>(...):`` bis kurz vor nächste ``^def`` / ``^class``.
    """
    pattern = re.compile(
        rf"^def {re.escape(func_name)}\([\s\S]+?(?=^def\s|^class\s|^# ====)",
        re.MULTILINE,
    )
    m = pattern.search(src)
    if not m:
        return None
    start = m.start()
    pre = src[:start]
    lineno = pre.count("\n") + 1
    return lineno, m.group(0)


def main() -> int:
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")

    bugs: list[tuple[str, int, str]] = []
    for func_name in _FORBIDDEN_FUNCS:
        result = _extract_function_body(src, func_name)
        if not result:
            # Funktion existiert nicht (z.B. umbenannt) — kein Failure,
            # aber Hinweis loggen, damit die Allow-Liste gepflegt bleibt.
            print(f"WARN: {func_name} in generate_report.py nicht gefunden "
                  f"(Allow-Liste prüfen?)", file=sys.stderr)
            continue
        start_line, body = result
        for body_line_idx, line in enumerate(body.splitlines()):
            # Kommentare ignorieren — Wort „score_confidence" darf im
            # Erklär-Text vorkommen, nur nicht im aktiven Code.
            stripped = line.split("#", 1)[0]
            if _READER_PATTERN.search(stripped):
                bugs.append((func_name, start_line + body_line_idx, line.rstrip()))

    if not bugs:
        print(f"OK: Keine Score-Konfidenz-Reader in {len(_FORBIDDEN_FUNCS)} "
              f"Score-Berechnungs-Funktionen.")
        return 0

    print(f"FEHLER: {len(bugs)} Score-Konfidenz-Reader in verbotenen "
          f"Berechnungs-Funktionen:", file=sys.stderr)
    for func_name, ln, line in bugs:
        print(f"  {func_name}:{ln}  {line[:140]}", file=sys.stderr)
    print("\nFix: Score-Konfidenz ist rein anzeigend und darf NICHT in die "
          "Score-Berechnung einfließen (sonst Self-Reinforcement). Den "
          "Reader-Pfad in eine separate Anzeige-Funktion verlagern oder die "
          "Allow-Liste in scripts/lint_score_confidence_isolation.py "
          "anpassen, wenn der Reader bewusst dort gehört.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
