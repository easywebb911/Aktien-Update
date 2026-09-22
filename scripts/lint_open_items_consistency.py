"""Konsistenz-Check für ``open_items.json`` (Open-Items-Tracker, 22.09.2026).

## Hintergrund

Die "Gute Nacht"-Session-Handover-Regel (CLAUDE.md) ERSETZT
``SESSION_HANDOVER.md`` bei jeder Übergabe komplett, statt zu ergänzen
("alte Inhalte komplett ersetzen, nicht anhängen"). Offene Diagnose-/
Beobachtungspunkte, die nur in der Prosa des alten Handovers standen,
konnten dabei spurlos verloren gehen, wenn sie beim Neuschreiben nicht
bewusst mit übertragen wurden (bestätigtes Beispiel: NYSE-Referer-Probe-
Status, S8-Digest-Timing-Beobachtung -- beide in ``SESSION_HANDOVER.md``
nicht mehr auffindbar).

``open_items.json`` ist die strukturierte Gegenmaßnahme -- aber das
Dateiformat allein löst das Problem nicht (das war schon vorher möglich,
in Prosa). Der eigentliche Mehrwert ist DIESER mechanische Check: er
vergleicht die Item-Liste zwischen der PR-Basis (alte Version) und dem
PR-Kopf (neue Version) und schlägt fehl, wenn ein Item ersatzlos
verschwindet, ohne vorher explizit auf ``"erledigt"`` gesetzt worden zu
sein.

## Erlaubt vs. verboten

- Item bleibt in der Liste, Status ändert sich beliebig
  (``offen`` -> ``beobachtet`` -> ``erledigt``): erlaubt, kein Fund.
- Item wird aus der Liste entfernt, war aber in der ALTEN Version
  bereits ``"erledigt"``: erlaubt (nachträgliches Aufräumen).
- Item wird aus der Liste entfernt, war in der ALTEN Version ``"offen"``
  oder ``"beobachtet"``: **Fund** -- genau der Bug-Modus, den dieser
  Check verhindern soll.

## Architektur: zwei Git-Snapshots, keine Historien-Traversierung

Der Check braucht NUR zwei Datei-Zustände (Basis-Commit der PR vs.
aktueller Arbeitsbaum) -- keine vollständige Git-Historie. Das ist
bewusst so gewählt: eine Lösung, die tiefer in der Git-Historie graben
müsste (z.B. "wann wurde Item X zuletzt gesehen, über beliebig viele
Commits zurück"), wäre hier NICHT nötig und würde unnötige Komplexität
einführen. ``main()`` liest die alte Version via ``git show <ref>:<pfad>``
(``ref`` = Env ``OPEN_ITEMS_BASE_REF``, im Workflow der exakte
PR-Basis-SHA) und vergleicht sie gegen die aktuelle Datei im Arbeitsbaum.

Die Kernlogik (``check_consistency``, ``validate_item_structure``,
``_parse_items``) ist reine, deterministische Funktionen ohne Git-Zugriff
-- so mit festen Fixture-Zuständen testbar (siehe
``scripts/mock_test_lint_open_items_consistency.py``).

## Fail-soft-Fälle (bewusst KEIN Fund, nur Hinweis)

- ``open_items.json`` existiert (noch) nicht -> nichts zu prüfen.
- Die Basis-Ref ist nicht auflösbar oder hat die Datei nicht (z.B. genau
  DIESER PR, der die Datei einführt) -> keine Alt-Version, kein Vergleich
  möglich, nur der Struktur-Check läuft.
- Die Alt-Version ist kaputtes JSON (sollte nicht vorkommen, wenn dieser
  Check selbst schon vorher lief) -> Vergleich übersprungen statt hart
  zu failen (advisory, nicht production-blocking).

## Wartung

``open_items.json`` wird von Claude im selben Fluss gepflegt wie
``SESSION_HANDOVER.md`` -- entweder direkt (Ad-hoc-PR, wenn während der
Session ein neuer Diagnose-Punkt entsteht und PR-pflichtig committet
wird) oder im Rahmen des "Gute Nacht"-Direct-main-Commits (die EINE
dokumentierte Ausnahme vom PR-only-Workflow, siehe CLAUDE.md
"Session-Handover-Regel"). Es gibt KEINEN Cron/Code-Trigger dafür.

## Workflow-Integration: ZWEI Trigger für ZWEI Pflegepfade

Guardian-Finding (22.09.2026): ein Check, der nur auf ``pull_request``
triggert, deckt den "Gute Nacht"-Direct-main-Commit-Pfad NICHT ab --
genau den Pfad, der den ursprünglichen Datenverlust (NYSE-Referer-Probe,
S8-Digest-Timing) verursacht hat. Deshalb zwei Workflows:

- ``.github/workflows/pr-checks.yml`` (Step "Lint open-items
  consistency", ``OPEN_ITEMS_BASE_REF`` = PR-Basis-SHA) -- läuft VOR
  einem Merge, advisory wie die anderen 5 Lints. Deckt den Ad-hoc-PR-
  Pfad.
- ``.github/workflows/open_items_main_push_check.yml`` (``push`` auf
  ``main``, nur bei Änderung an ``open_items.json``, ``OPEN_ITEMS_
  BASE_REF`` = ``github.event.before``) -- deckt den "Gute Nacht"-Pfad.
  **Rein detektiv:** das ``push``-Event feuert erst NACHDEM der Commit
  bereits auf ``main`` liegt -- der Check kann den Verlust nicht
  verhindern, nur sichtbar machen (roter Check-Run auf dem Commit).
  Ein Fund verlangt einen Follow-up-Commit.

Beide bewusst NICHT in ``daily-squeeze-report.yml`` -- diese Datei hat
keinen Bezug zum produktiven Report-Lauf.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OPEN_ITEMS_PATH = "open_items.json"

_VALID_STATUSES = frozenset({"offen", "beobachtet", "erledigt"})
_REQUIRED_FIELDS = ("id", "title", "opened", "description", "status", "status_date")


def _parse_items(raw: str) -> list[dict]:
    """Parst den JSON-Text der Datei -> Liste der Items.

    Wirft ``ValueError``/``json.JSONDecodeError`` bei kaputtem Schema --
    Caller entscheiden bewusst pro Aufrufkontext, ob das hart failen
    (neue/aktuelle Version) oder fail-soft übersprungen werden soll
    (Alt-Version, siehe Docstring oben).
    """
    data = json.loads(raw)
    if not isinstance(data, dict) or "items" not in data:
        raise ValueError(
            f"{OPEN_ITEMS_PATH}: Top-Level muss ein Dict mit 'items'-Key sein."
        )
    items = data["items"]
    if not isinstance(items, list):
        raise ValueError(f"{OPEN_ITEMS_PATH}: 'items' muss eine Liste sein.")
    return items


def validate_item_structure(item: dict) -> list[str]:
    """Strukturelle Validierung EINES Items. Pure, gibt Liste von
    Fehlermeldungen zurück (leer = valide)."""
    if not isinstance(item, dict):
        return [f"Item ist kein Objekt: {item!r}"]

    errors = []
    for field in _REQUIRED_FIELDS:
        if not item.get(field):
            errors.append(
                f"Item {item.get('id', '?')!r}: Pflichtfeld '{field}' fehlt oder ist leer."
            )
    status = item.get("status")
    if status is not None and status not in _VALID_STATUSES:
        errors.append(
            f"Item {item.get('id', '?')!r}: ungültiger Status {status!r} "
            f"(erlaubt: {sorted(_VALID_STATUSES)})."
        )
    return errors


def check_consistency(old_items: list[dict], new_items: list[dict]) -> list[str]:
    """Kern-Check (pure, deterministisch, kein I/O).

    Vergleicht zwei Item-Listen (alte vs. neue Version von
    ``open_items.json``) und meldet jedes Item, das zwischen beiden
    Versionen ersatzlos verschwunden ist, OHNE in der alten Version
    bereits ``status == "erledigt"`` gewesen zu sein.
    """
    old_by_id = {
        item["id"]: item
        for item in old_items
        if isinstance(item, dict) and "id" in item
    }
    new_ids = {
        item["id"] for item in new_items if isinstance(item, dict) and "id" in item
    }

    violations = []
    for item_id, old_item in old_by_id.items():
        if item_id in new_ids:
            continue
        if old_item.get("status") == "erledigt":
            continue
        violations.append(
            f"Item '{item_id}' ({old_item.get('title', '?')!r}) ist ersatzlos "
            f"verschwunden -- Status war {old_item.get('status', '?')!r}, "
            f"nicht 'erledigt'."
        )
    return violations


def _git_show(ref: str, rel_path: str) -> str | None:
    """Liest den Inhalt von ``rel_path`` beim Git-Ref ``ref``.

    Returnt ``None`` (statt zu werfen), wenn die Datei bei ``ref`` nicht
    existiert oder ``ref`` nicht auflösbar ist -- beides ist ein legitimer
    Zustand (z.B. der PR, der die Datei einführt), kein Fehler.
    """
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{rel_path}"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def main() -> int:
    base_ref = os.environ.get("OPEN_ITEMS_BASE_REF", "origin/main")
    new_file = ROOT / OPEN_ITEMS_PATH

    if not new_file.exists():
        print(f"OK: {OPEN_ITEMS_PATH} existiert nicht -- nichts zu prüfen.")
        return 0

    new_raw = new_file.read_text(encoding="utf-8")
    try:
        new_items = _parse_items(new_raw)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"FEHLER: {OPEN_ITEMS_PATH} (neue Version) ist kein gültiges Schema: {exc}")
        return 1

    struct_errors: list[str] = []
    for item in new_items:
        struct_errors.extend(validate_item_structure(item))
    if struct_errors:
        print(f"FEHLER: {len(struct_errors)} Struktur-Problem(e) in {OPEN_ITEMS_PATH}:")
        for err in struct_errors:
            print(f"  - {err}")
        return 1

    old_raw = _git_show(base_ref, OPEN_ITEMS_PATH)
    if old_raw is None:
        print(
            f"OK: keine Alt-Version von {OPEN_ITEMS_PATH} bei '{base_ref}' gefunden "
            f"(neue Datei oder Ref nicht verfügbar) -- Struktur-Check bestanden "
            f"({len(new_items)} Items), Konsistenz-Vergleich übersprungen."
        )
        return 0

    try:
        old_items = _parse_items(old_raw)
    except (ValueError, json.JSONDecodeError) as exc:
        print(
            f"WARNUNG: Alt-Version von {OPEN_ITEMS_PATH} bei '{base_ref}' nicht "
            f"parsebar ({exc}) -- Konsistenz-Vergleich übersprungen (fail-soft)."
        )
        return 0

    violations = check_consistency(old_items, new_items)
    if violations:
        print(f"FEHLER: {len(violations)} Open-Item(s) sind ersatzlos verschwunden:")
        for v in violations:
            print(f"  - {v}")
        print("  -> Status explizit auf 'erledigt' setzen, statt den Punkt zu entfernen.")
        return 1

    print(
        f"OK: {OPEN_ITEMS_PATH} strukturell gültig, kein Item ersatzlos "
        f"verschwunden ({len(new_items)} Items, Basis '{base_ref}')."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
