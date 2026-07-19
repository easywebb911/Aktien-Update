#!/usr/bin/env python3
"""Isolierter Rückweg für ``material_8k_events`` (§6c, B0-1).

Poppt EXAKT den einen benannten Top-Level-Key ``material_8k_events`` aus jedem
Record in ``backtest_history.json``. **Alle anderen Felder bleiben byte-
identisch** — das Feld wird ausschließlich vom Sammler in
``backtest_history._build_backtest_extension`` geschrieben, ist also eindeutig.

WARUM KEIN MANIFEST (anders als ``backfill_entry_past_return_5d.py``):
  Dort war der Rückweg ``--undo`` MIT Manifest nötig, weil der befüllte WERT
  (ein Float) per Recompute rekonstruierbar war → mehrdeutig, welche Records
  der Live-Lauf tatsächlich geschrieben hatte. Hier ist der Rückweg-Anker ein
  **benannter JSON-Key**: ``rec.pop("material_8k_events", None)`` trifft
  ausschließlich dieses Feld — keine Recompute-Kollision, kein Manifest.

Alt-Records ohne den Key (vor dem Feature) bleiben unberührt (pop no-op).

Läufe:
  ``python scripts/purge_material_8k_events.py``          → DRY-RUN (Preview).
  ``python scripts/purge_material_8k_events.py --live``   → schreibt die Datei.
  ``--path X`` überschreibt die Ziel-Datei (Tests).

Serialisierung identisch zu ``_save_backtest_history``
(``json.dump(..., indent=2, ensure_ascii=False)``) → garantiert, dass die
verbleibenden Felder bit-genau gleich re-serialisiert werden.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_KEY = "material_8k_events"

log = logging.getLogger("purge_material_8k_events")


def _default_path() -> str:
    """``config.BACKTEST_FILE`` wenn verfügbar, sonst Repo-Root-Default."""
    try:
        import config
        return str(config.BACKTEST_FILE)
    except Exception:
        return str(Path(__file__).resolve().parent.parent / "backtest_history.json")


def purge_records(history: list) -> tuple[list, int]:
    """Pure: poppt ``material_8k_events`` aus jedem Record. Gibt
    ``(unveränderte-Liste-Referenz, n_popped)`` zurück. Mutiert die Dicts
    in-place (der Aufrufer hat die Liste frisch geladen)."""
    n = 0
    for rec in history:
        if isinstance(rec, dict) and _KEY in rec:
            rec.pop(_KEY, None)
            n += 1
    return history, n


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true",
                   help="Datei tatsächlich schreiben (sonst Dry-Run).")
    p.add_argument("--path", default=None,
                   help="Ziel-Datei (Default: config.BACKTEST_FILE).")
    args = p.parse_args(argv)
    path = args.path or _default_path()
    mode = "LIVE" if args.live else "DRY-RUN"
    log.info("Modus: %s | Ziel: %s", mode, path)

    try:
        with open(path, "r", encoding="utf-8") as fh:
            history = json.load(fh)
    except FileNotFoundError:
        log.error("Datei nicht gefunden: %s", path)
        return 1
    except json.JSONDecodeError as exc:
        log.error("JSON-Parse-Fehler: %s", exc)
        return 1
    if not isinstance(history, list):
        log.error("Unerwartetes Format (kein Array): %s", path)
        return 1

    n_before = sum(1 for r in history if isinstance(r, dict) and _KEY in r)
    _, n_popped = purge_records(history)
    log.info("%d Records mit '%s' gefunden und entfernt.", n_popped, _KEY)
    if n_before != n_popped:
        log.warning("Zähler-Mismatch (before=%d popped=%d) — bitte prüfen.",
                    n_before, n_popped)

    if not args.live:
        log.info("DRY-RUN: keine Datei geschrieben. Für Schreiben: --live.")
        return 0

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2, ensure_ascii=False)
    log.info("LIVE: '%s' aus %d Records entfernt, Datei geschrieben.",
             _KEY, n_popped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
