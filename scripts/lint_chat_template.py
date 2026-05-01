#!/usr/bin/env python3
"""Lint: prüft templates/chat_script.jinja auf Streu-Backticks im
``_buildSystem()``-Body.

Hintergrund: Bug 1341af9 — Markdown-Code-Notation (``code``) innerhalb
des JS-Template-Literals von ``_buildSystem()`` brach das Literal,
warf einen TypeError mit dem kompletten Prompt als Message und
zeigte ihn als roten Chat-Bubble an. Diese Lint-Regel verhindert
Wiederholungen.

Erwartung: genau 2 Backticks im Function-Body — der öffnende und
der schließende Delimiter des Template-Literals. Jede zusätzliche
Backtick-Zeichen (z.B. Markdown-Code-Notation) bricht das Literal
und produziert einen TypeError zur Laufzeit.

Exit-Code 0 bei Erfolg, 1 bei Fehler (für CI-Integration).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE  = REPO_ROOT / "templates" / "chat_script.jinja"

# Erwartete Anzahl Backticks im _buildSystem-Body: open + close = 2.
EXPECTED_BACKTICKS = 2

# Regex: Function-Body von ``function _buildSystem() {`` bis zur ersten
# Zeile, die nur eine schließende geschweifte Klammer enthält. Lazy
# match (.*?) mit re.DOTALL, re.MULTILINE für ``^`` als Zeilenanfang.
_BODY_RE = re.compile(
    r"function\s+_buildSystem\s*\(\s*\)\s*\{(.*?)^\s*\}",
    re.DOTALL | re.MULTILINE,
)


def _extract_buildsystem_body(src: str) -> str:
    m = _BODY_RE.search(src)
    if not m:
        raise SystemExit(
            "FEHLER: function _buildSystem() {…} im Template nicht gefunden — "
            "Lint-Regex outdated?"
        )
    return m.group(1)


def main() -> int:
    if not TEMPLATE.exists():
        print(f"FEHLER: {TEMPLATE} nicht gefunden", file=sys.stderr)
        return 1

    src  = TEMPLATE.read_text(encoding="utf-8")
    body = _extract_buildsystem_body(src)
    n    = body.count("`")

    if n == EXPECTED_BACKTICKS:
        print(f"OK: {n} Backticks im _buildSystem-Body (Open + Close).")
        return 0

    print(
        f"FEHLER: {n} Backticks im _buildSystem-Body von {TEMPLATE.name} "
        f"(erwartet: {EXPECTED_BACKTICKS}).",
        file=sys.stderr,
    )
    print(
        "Markdown-Code-Notation (``text``) bricht das JS-Template-Literal "
        "und erzeugt einen TypeError zur Laufzeit, der den kompletten "
        "Prompt als Fehlermeldung im Chat anzeigt. Siehe Bug 1341af9.",
        file=sys.stderr,
    )

    # Hilfe: alle Backtick-Positionen im Body listen
    print("\nBacktick-Fundstellen (relativ zum Body-Start):", file=sys.stderr)
    for i, ch in enumerate(body):
        if ch == "`":
            ctx_start = max(0, i - 30)
            ctx_end   = min(len(body), i + 30)
            ctx = body[ctx_start:ctx_end].replace("\n", " ")
            print(f"  Pos {i}: …{ctx}…", file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main())
