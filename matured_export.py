"""Append-only-Export gereifter Backtest-Records (Analyse-only, prune-immun).

Motivation: ``backtest_history.json`` unterliegt dem 90-Tage-Prune
(``BACKTEST_MAX_DAYS`` — Zweck real: client-seitiger Fetch beim Panel-Öffnen +
Repo-Wachstum). Gereifte Forward-Records verfallen damit ab ~90 Tagen — zu wenig
für die Sept-Re-Tests (n≥250) und spätere Hypothesen. Diese Datei TRENNT Anzeige
(geprunetes ``backtest_history.json``) von ANALYSE (prune-immunes
``matured_backtest_export.jsonl``) — Haus-Muster ``si_position_history.json`` /
Backfill-Manifest (eigene Datei überlebt den Prune).

Harte Invarianten:
- **LOOK-AHEAD-SAFE:** ein Record wird EINMALIG exportiert, sobald er gereift ist
  (``return_10d`` gefüllt), und danach NIE wieder angefasst — kein Nachberechnen,
  kein Überschreiben, kein Nachtragen späterer Felder. Fehlt ein Feld zum
  Exportzeitpunkt, bleibt es fehlend (ehrliche Information). Bestehende Zeilen
  werden byte-verbatim übernommen; nur neue Zeilen kommen hinzu.
- **IDEMPOTENZ:** Schlüssel ``(ticker, date)`` — ein Record landet nie zweimal.
- **UMFANG:** ALLE gereiften echten daily-Records (``source != "bootstrap"``),
  KEIN score-Filter (Filterung gehört in die Auswertung, nicht die Persistenz).
- **Herkunft:** Feld ``provenance`` — ``"backfill"`` = einmalige Bestands-
  Übernahme (Records, die beim ERSTEN Export-Lauf schon gereift waren, ihr
  Outcome war zum Import-Zeitpunkt bereits bekannt → In-Sample-Vorsicht);
  ``"forward"`` = im Live-postclose-Betrieb gereift-und-exportiert (Outcome erst
  nach Export-Existenz bekannt → sauberes OoS). Trennung an der Datei ablesbar,
  damit In-Sample/OoS nie versehentlich gepoolt wird.
- **Fail-soft:** raise-frei nach außen; der Caller wrappt zusätzlich. Ein Fehler
  darf den Daily-Run NIE abbrechen.
- **Determinismus:** neue Zeilen pro Batch nach ``(date, ticker)`` sortiert,
  Feld-Reihenfolge stabil (``sort_keys``). Atomarer Write (tmp + os.replace,
  Haus-Muster ``si_position_history`` / ``_save_wiki_ticker_map``) → nie
  halb-geschrieben.

ANALYSE-ONLY: KEIN Frontend-Fetch, NICHT im HTML/Golden, kein Score-/Push-Effekt.
Löschbar ohne Nebenwirkung (niemand liest die Datei im Tool).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

try:  # zentrale Konstanten; Fallback macht das Modul standalone-testbar
    from config import BACKTEST_FILE, MATURED_EXPORT_FILE
except Exception:  # pragma: no cover
    BACKTEST_FILE = "backtest_history.json"
    MATURED_EXPORT_FILE = "matured_backtest_export.jsonl"

log = logging.getLogger(__name__)


def _keyf(ds: str):
    """Sortier-Schlüssel für ``DD.MM.YYYY``; unparsebar → (0,0,0) (ans Ende-frei,
    deterministisch)."""
    try:
        d, m, y = ds.split(".")
        return (int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _load_existing(export_path: str):
    """Return ``(seen_keys:set, raw_lines:list[str])``. Fail-soft: fehlende Datei
    → leer; korrupte Zeile → übersprungen (NICHT in ``seen``, NICHT verbatim
    übernommen → der Record wird, falls noch in der Quelle, sauber neu
    exportiert). os.replace beim Schreiben garantiert, dass eine korrupte Zeile
    praktisch nur durch Fremd-Eingriff entstehen kann."""
    seen: set = set()
    raw: list[str] = []
    try:
        with open(export_path, "r", encoding="utf-8") as fh:
            for line in fh:
                s = line.rstrip("\n")
                if not s.strip():
                    continue
                try:
                    obj = json.loads(s)
                    t, d = obj.get("ticker"), obj.get("date")
                    if t is None or d is None:
                        log.warning("matured_export: Zeile ohne ticker/date übersprungen")
                        continue
                    seen.add((t, d))
                    raw.append(s)
                except (json.JSONDecodeError, TypeError, ValueError):
                    log.warning("matured_export: korrupte Zeile übersprungen (fail-soft)")
                    continue
    except FileNotFoundError:
        pass
    except Exception as exc:  # pragma: no cover
        log.warning("matured_export: Lesen fehlgeschlagen (fail-soft): %s", exc)
    return seen, raw


def _load_source(source_path: str) -> list:
    """Lädt ``backtest_history.json`` fail-soft (leer bei fehlend/korrupt)."""
    try:
        with open(source_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return raw if isinstance(raw, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    except Exception:  # pragma: no cover
        return []


def export_matured_records(history: list | None = None, *,
                           source_path: str | None = None,
                           export_path: str | None = None,
                           now: datetime | None = None) -> int:
    """Exportiert neu-gereifte echte daily-Records append-only nach ``export_path``.

    Kriterien pro Record: ``source != "bootstrap"``, ``return_10d`` gefüllt (=
    gereift), ``(ticker, date)`` noch nicht exportiert. KEIN score-Filter.

    Returnt die Anzahl NEU exportierter Zeilen. Bestehende Zeilen bleiben
    byte-verbatim (kein exportierter Record wird je verändert). Raise-frei genug;
    der Caller wrappt zusätzlich fail-soft.
    """
    export_path = export_path or MATURED_EXPORT_FILE
    if history is None:
        history = _load_source(source_path or BACKTEST_FILE)
    if now is None:
        now = datetime.now(timezone.utc)

    seen, raw_existing = _load_existing(export_path)
    # Bestands-Übernahme (Datei leer/neu) → provenance "backfill"; danach "forward".
    provenance = "backfill" if not seen else "forward"
    ts = now.isoformat()

    new_rows = []
    for e in history:
        if not isinstance(e, dict):
            continue
        if e.get("source") == "bootstrap":      # Bootstrap NICHT exportieren
            continue
        if e.get("return_10d") is None:          # noch nicht gereift
            continue
        t, d = e.get("ticker"), e.get("date")
        if not t or not d:
            continue
        if (t, d) in seen:                       # idempotent (Datei + Batch)
            continue
        seen.add((t, d))
        row = dict(e)                            # Snapshot, wie er JETZT ist
        row["provenance"] = provenance           # Herkunft an der Datei ablesbar
        row["exported_at"] = ts
        new_rows.append(((_keyf(d), t), row))

    if not new_rows:
        return 0

    new_rows.sort(key=lambda x: x[0])            # stabile Sortierung (date, ticker)
    lines = raw_existing + [
        json.dumps(r, sort_keys=True, ensure_ascii=False) for _, r in new_rows
    ]
    # Atomar (tmp + os.replace) → nie halb-geschrieben; bestehende Zeilen verbatim.
    tmp = f"{export_path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, export_path)
    return len(new_rows)
