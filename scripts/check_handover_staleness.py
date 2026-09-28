"""Handover-Staleness-Hinweis (advisory, 28.09.2026) für ``pr-checks.yml``.

## Hintergrund

``SESSION_HANDOVER.md`` Block 1 ("## 1) HEUTE IMPLEMENTIERT") ist am
28.09.2026 zweimal binnen weniger Stunden hinter ``main`` zurückgefallen:
erst um 31 PRs (behoben in PR #564), dann sofort wieder um 2 PRs
(#565/#566, nachgezogen in #567). Bestehende Absicherung war ausschließlich
Session-Disziplin ("vor jeder Ready-Meldung prüfen") -- kein mechanischer
Check. Dieses Skript schließt NICHT die Lücke selbst (das bleibt
Session-Disziplin, siehe CLAUDE.md), sondern gibt einen zusätzlichen,
externen Hinweis: einen advisory CI-Print bei jedem PR, falls der
Rückstand eine Schwelle überschreitet.

## Zwei Zahlen, zwei Quellen

- **Höchste GEMERGTE PR-Nummer** -- via ``gh pr list --state merged
  --limit 1 --json number`` (GitHub-API, kein Git-Log-Parsing). Diagnose
  28.09.2026 hat eine Git-Fetch-Tiefen-Alternative geprüft und verworfen:
  das Repo hat 4927 Commits, aber nur ~8% davon sind Merge-Commits (Rest
  automatisierte ki_agent-/Daily-Run-Pushes) -- eine feste Fetch-Tiefe
  würde bei steigender Automations-Dichte STILL zu knapp werden (falsches
  "aktuell", kein sichtbarer Fehler). Die API ist O(1) und degradiert
  nicht mit Repo-Wachstum.
- **Höchste in Block 1 ERWÄHNTE PR-Nummer** -- Regex über den Abschnitt
  zwischen ``## 1) HEUTE`` und ``## 2)``. Range-Notationen (z.B.
  "`#533`-`#536`") liefern beide Endpunkte -- für das reine Rückstands-Maß
  reicht die höchste sichtbare Zahl, siehe Diagnose 28.09.2026.

## Schwelle

``HANDOVER_STALENESS_PR_THRESHOLD = 3`` -- Start-Kalibrierung aus echten
Merge-Tagen (22.09.: 1 Merge, 25.09.: 2, 27.09.: 3). Ein normaler
Arbeitstag erreicht bis zu 3 Merges in einer Session, BEVOR Block 1
zwingend nachgezogen sein muss -- die Schwelle liegt knapp darüber, damit
der Hinweis nicht bei jedem Routine-Tag feuert, aber den historischen
31er-Rückstand sicher fängt. Nachjustierbar wie andere Schwellen im
Projekt (z.B. ``STALENESS_FRESH_MAX_HOURS`` in ``config.py``) -- lebt
HIER lokal statt in ``config.py``, weil das eine CI-Tooling-Konstante
ist, keine Runtime-Score-/Filter-/Anzeige-Schwelle (Precedent: alle
``lint_*.py``-Skripte halten ihre eigenen Konstanten lokal, keines
importiert ``config.py``).

## Fail-soft (KEIN CI-Fail, in KEINEM Fall)

Dieser Check ist bewusst weicher als die übrigen 6 Lints in
``pr-checks.yml`` (die bei einem Fund ``exit 1`` liefern und den
Check-Run rot färben): ``main()`` returnt IMMER 0, egal ob (a) kein
Rückstand, (b) Rückstand über Schwelle, oder (c) der ``gh``-Aufruf selbst
fehlschlägt (Netzwerk, Rate-Limit, kaputtes JSON, `gh` fehlt im Runner-
Image). Grund: ein externer API-Abhängigkeits-Fehler soll NIEMALS einen
stillen Falsch-Negativ-Zustand ODER einen blockierenden CI-Fail
erzeugen -- nur einen Hinweis "Check nicht durchführbar" in der Log-
Ausgabe (advisory-Philosophie identisch zu allen anderen ``pr-checks.yml``-
Steps, hier nur konsequent bis zum Exit-Code durchgezogen statt bei einem
Fund zu failen).

## Architektur: pure Kernfunktionen, I/O nur in zwei schmalen Wrappern

``extract_block1_text`` / ``extract_highest_doc_pr`` / ``compute_staleness``
/ ``format_staleness_hint`` sind pure Funktionen ohne I/O -- mit festen
Fixture-Strings/-Zahlen testbar, kein echter ``gh``-Aufruf in der
Test-Suite nötig (siehe ``scripts/mock_test_handover_staleness.py``).
``fetch_highest_merged_pr`` ist der einzige I/O-Wrapper (Subprocess) und
wird in Tests via ``unittest.mock`` auf ``subprocess.run`` gepatcht, nie
real aufgerufen.

## Neue Permission

``pull-requests: read`` ist eine NEUE Rechte-Klasse für
``pr-checks.yml`` (bisher nur ``contents: read``). Bleibt vollständig
lesend -- ``gh pr list`` kann nichts schreiben, mergen oder blockieren;
die Selbstbeschreibung der Workflow-Datei ("kann nichts pushen, mergen
oder blockieren") bleibt wörtlich korrekt.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HANDOVER_PATH = "SESSION_HANDOVER.md"

# Nachjustierbare Schwelle -- siehe Docstring "Schwelle" oben.
HANDOVER_STALENESS_PR_THRESHOLD = 3

_BLOCK1_START_RE = re.compile(r"^## 1\) HEUTE", re.MULTILINE)
_BLOCK1_END_RE = re.compile(r"^## 2\)", re.MULTILINE)
# \b (Wortgrenze) NACH den Ziffern ist Pflicht, nicht kosmetisch: Block 1
# enthält echte CSS-Hex-Farbcodes in Backticks (z.B. "`#22c55e->#94a3b8`",
# PR-History-Eintrag zu #425) -- ein reines "#\d+" würde daraus "22"/"94"
# als falsche PR-Nummern extrahieren (Ziffern-Präfix vor dem ersten
# Hex-Buchstaben). Bei einem künftigen Hex-Code, dessen Ziffern-Präfix
# zufällig >= der echten höchsten PR-Nummer liegt (z.B. "#598abc"), würde
# das den Rückstand fälschlich verschleiern -- genau das stille
# Falsch-Negativ, das dieser Check verhindern soll. Verifiziert gegen die
# echte Live-Datei (28.09.2026): ohne \b matchen 150 Treffer (Max 566,
# kontaminiert durch 22/94), mit \b 145 Treffer (Max weiterhin korrekt
# 566 -- die zwei Hex-Fragmente sind die einzige Differenz).
_PR_NUM_RE = re.compile(r"#(\d+)\b")


def extract_block1_text(handover_text: str) -> str | None:
    """Extrahiert den Block-1-Abschnitt (zwischen '## 1) HEUTE' und der
    nächsten '## 2)'-Überschrift, oder bis Textende, falls keine folgt).

    Returnt ``None``, wenn die Start-Markierung fehlt -- fail-soft
    (unerwartete Handover-Struktur), kein Crash."""
    start_m = _BLOCK1_START_RE.search(handover_text)
    if start_m is None:
        return None
    end_m = _BLOCK1_END_RE.search(handover_text, start_m.end())
    return handover_text[start_m.start(): end_m.start() if end_m else len(handover_text)]


def extract_highest_doc_pr(handover_text: str) -> int | None:
    """Höchste in Block 1 ERWÄHNTE PR-Nummer (pure). Range-Endpunkte
    (z.B. '`#533`-`#536`') zählen beide -- für das Rückstands-Maß reicht
    die höchste sichtbare Zahl. Returnt ``None`` bei fehlendem Block 1
    oder wenn keine ``#NNN``-Nummer gefunden wird."""
    block1 = extract_block1_text(handover_text)
    if block1 is None:
        return None
    numbers = [int(n) for n in _PR_NUM_RE.findall(block1)]
    return max(numbers) if numbers else None


def compute_staleness(highest_merged_pr: int, highest_doc_pr: int) -> int:
    """Pure: Rückstand = höchste gemergte PR-Nummer minus höchste in
    Block 1 erwähnte PR-Nummer. Kann 0 oder negativ sein (Doku bereits
    aktuell, oder erwähnt sogar schon die eigene noch nicht gemergte
    PR-Nummer voraus) -- beides ist kein Fund."""
    return highest_merged_pr - highest_doc_pr


def format_staleness_hint(
    highest_merged_pr: int,
    highest_doc_pr: int,
    threshold: int = HANDOVER_STALENESS_PR_THRESHOLD,
) -> str | None:
    """Pure: liefert die Advisory-Hinweiszeile, oder ``None`` wenn der
    Rückstand unter ``threshold`` liegt (kein Fund)."""
    lag = compute_staleness(highest_merged_pr, highest_doc_pr)
    if lag < threshold:
        return None
    return (
        f"HINWEIS: SESSION_HANDOVER.md Block 1 hinkt main hinterher -- "
        f"höchste gemergte PR #{highest_merged_pr}, höchste in Block 1 "
        f"erwähnte PR #{highest_doc_pr} (Rückstand {lag}, Schwelle "
        f"{threshold}). Kein Blocker -- Block 1 vor der nächsten Ready-"
        f"Meldung nachziehen."
    )


def fetch_highest_merged_pr() -> tuple[int | None, str | None]:
    """I/O: ``gh pr list --state merged --limit 1 --json number``.

    Returnt ``(nummer, fehlertext)``. Bei Erfolg: ``(N, None)``. Bei
    JEDEM Fehlerfall (``gh`` fehlt, Netzwerk, Rate-Limit, kaputtes JSON,
    leere Merge-Liste, unerwartetes Schema) fail-soft: ``(None, <Grund>)``
    -- wirft NIEMALS eine Exception nach außen (siehe ``main()``, das
    diesen Fall als Hinweis statt CI-Fail behandelt)."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "merged", "--limit", "1",
             "--json", "number"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"gh-Aufruf fehlgeschlagen ({exc})"
    if result.returncode != 0:
        detail = (result.stderr or "").strip()[:200]
        return None, f"gh exit {result.returncode}: {detail}"
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return None, f"gh-Ausgabe nicht parsebar ({exc})"
    if not isinstance(data, list) or not data:
        return None, "keine gemergten PRs gefunden (leere Liste)"
    first = data[0]
    number = first.get("number") if isinstance(first, dict) else None
    if not isinstance(number, int):
        return None, f"unerwartetes gh-Antwortschema: {first!r}"
    return number, None


def main() -> int:
    """Returnt IMMER 0 -- dieser Check ist bewusst weicher als die
    übrigen ``pr-checks.yml``-Lints (siehe Docstring "Fail-soft")."""
    handover_file = ROOT / HANDOVER_PATH
    if not handover_file.exists():
        print(f"HINWEIS: {HANDOVER_PATH} nicht gefunden -- "
              f"Staleness-Check übersprungen.")
        return 0

    highest_doc_pr = extract_highest_doc_pr(
        handover_file.read_text(encoding="utf-8"))
    if highest_doc_pr is None:
        print(f"HINWEIS: keine PR-Nummer in Block 1 von {HANDOVER_PATH} "
              f"gefunden -- Staleness-Check nicht durchführbar "
              f"(fail-soft, kein CI-Fail).")
        return 0

    highest_merged_pr, error = fetch_highest_merged_pr()
    if highest_merged_pr is None:
        print(f"HINWEIS: Staleness-Check nicht durchführbar ({error}) -- "
              f"fail-soft, kein CI-Fail.")
        return 0

    hint = format_staleness_hint(highest_merged_pr, highest_doc_pr)
    if hint is None:
        lag = compute_staleness(highest_merged_pr, highest_doc_pr)
        print(f"OK: SESSION_HANDOVER.md Block 1 aktuell genug (Rückstand "
              f"{lag}, Schwelle {HANDOVER_STALENESS_PR_THRESHOLD}) -- "
              f"höchste gemergte PR #{highest_merged_pr}, höchste in "
              f"Block 1 erwähnte PR #{highest_doc_pr}.")
        return 0

    print(hint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
