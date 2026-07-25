#!/usr/bin/env python3
"""Isolierter Rückweg für ``attention_wiki`` (24.07.2026).

Poppt EXAKT den benannten Top-Level-Key ``attention_wiki`` aus jedem Record in
``backtest_history.json`` UND löscht das zweite Artefakt ``wiki_ticker_map.json``
(die eingefrorene Ticker→QID-Auflösung). **Alle anderen Felder bleiben byte-
identisch** — ``attention_wiki`` wird ausschließlich vom Sammler in
``backtest_history._build_backtest_extension`` geschrieben, ist also eindeutig
(benannter Key, keine Recompute-Kollision, kein Manifest nötig — analog
``purge_material_8k_events.py``).

Alt-Records ohne den Key (vor dem Feature) bleiben unberührt (pop no-op).

Läufe:
  ``python scripts/purge_attention_wiki.py``          → DRY-RUN (Preview).
  ``python scripts/purge_attention_wiki.py --live``   → schreibt/löscht.
  ``--path X`` überschreibt die backtest-Datei, ``--map-path Y`` die Map (Tests).

Serialisierung identisch zu ``_save_backtest_history``
(``json.dump(..., indent=2, ensure_ascii=False)``) → verbleibende Felder werden
bit-genau gleich re-serialisiert.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_KEY = "attention_wiki"

log = logging.getLogger("purge_attention_wiki")


def _default_path() -> str:
    try:
        import config
        return str(config.BACKTEST_FILE)
    except Exception:
        return str(Path(__file__).resolve().parent.parent / "backtest_history.json")


def _default_map_path() -> str:
    try:
        import config
        return str(config.WIKI_ATTENTION_MAP_FILE)
    except Exception:
        return str(Path(__file__).resolve().parent.parent / "wiki_ticker_map.json")


def purge_records(history: list) -> tuple[list, int]:
    """Pure: poppt ``attention_wiki`` aus jedem Record. Mutiert die Dicts
    in-place. Gibt ``(Liste, n_popped)`` zurück."""
    n = 0
    for rec in history:
        if isinstance(rec, dict) and _KEY in rec:
            rec.pop(_KEY, None)
            n += 1
    return history, n


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true",
                   help="Datei tatsächlich schreiben/löschen (sonst Dry-Run).")
    p.add_argument("--path", default=None,
                   help="backtest-Datei (Default: config.BACKTEST_FILE).")
    p.add_argument("--map-path", default=None,
                   help="Ticker-Map (Default: config.WIKI_ATTENTION_MAP_FILE).")
    args = p.parse_args(argv)
    path = args.path or _default_path()
    map_path = args.map_path or _default_map_path()
    mode = "LIVE" if args.live else "DRY-RUN"
    log.info("Modus: %s | Ziel: %s | Map: %s", mode, path, map_path)

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

    map_exists = Path(map_path).exists()
    log.info("Ticker-Map %s%s", map_path,
             " (vorhanden → wird gelöscht)" if map_exists else " (nicht vorhanden)")

    if not args.live:
        log.info("DRY-RUN: nichts geschrieben/gelöscht. Für echt: --live.")
        return 0

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2, ensure_ascii=False)
    log.info("LIVE: '%s' aus %d Records entfernt, Datei geschrieben.",
             _KEY, n_popped)
    if map_exists:
        Path(map_path).unlink()
        log.info("LIVE: Ticker-Map '%s' gelöscht.", map_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
