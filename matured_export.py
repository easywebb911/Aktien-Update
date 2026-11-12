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
  (Reife = ``return_10d`` gefüllt UND ``days_old > 14`` Kalendertage — die
  zweite Schranke garantiert, dass die ROLLING-Felder ``max_gain_pct`` /
  ``max_drawdown_pct`` final sind, siehe Kommentar am Gate), und danach NIE
  wieder angefasst — kein Nachberechnen, kein Überschreiben, kein Nachtragen
  späterer Felder. Fehlt ein Feld zum Exportzeitpunkt, bleibt es fehlend
  (ehrliche Information). Bestehende Zeilen werden byte-verbatim übernommen;
  nur neue Zeilen kommen hinzu.
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
from datetime import datetime, timedelta, timezone

import trading_date

try:  # zentrale Konstanten; Fallback macht das Modul standalone-testbar
    from config import (BACKTEST_FILE, MATURED_EXPORT_FILE,
                        ROLLING_WINDOW_GRACE_DAYS, ROLLING_WINDOW_TRADING_DAYS,
                        US_MARKET_HOLIDAYS)
except Exception:  # pragma: no cover
    BACKTEST_FILE = "backtest_history.json"
    MATURED_EXPORT_FILE = "matured_backtest_export.jsonl"
    ROLLING_WINDOW_GRACE_DAYS = 7
    ROLLING_WINDOW_TRADING_DAYS = 10
    US_MARKET_HOLIDAYS = frozenset()

log = logging.getLogger(__name__)


def _keyf(ds: str):
    """Sortier-Schlüssel für ``DD.MM.YYYY``; unparsebar → (0,0,0) (ans Ende-frei,
    deterministisch)."""
    try:
        d, m, y = ds.split(".")
        return (int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _calendar_days_old(ds: str, now: datetime):
    """Kalendertage seit Entry-Datum ``DD.MM.YYYY`` bis ``now`` (UTC-Datum).

    Returnt ``(now.date() - entry).days`` (int) oder ``None`` bei unparsebarem
    Datum — dann wird der Record konservativ NICHT exportiert (fail-safe: lieber
    einen gültigen Record eine Runde später als einen kaputten dauerhaft
    einfrieren)."""
    try:
        d, m, y = ds.split(".")
        entry = datetime(int(y), int(m), int(d)).date()
        return (now.date() - entry).days
    except (ValueError, AttributeError, TypeError):
        return None


def _rolling_window_complete(e: dict, ds: str, now: datetime) -> bool:
    """True, wenn das max_gain-/max_drawdown-Fenster des Eintrags fertig ist:
    ``rolling_window_n >= 11`` (D + 10 vollständige Handelstage) UND der letzte
    finale Schluss liegt nach Tag 10 — oder die Nachfrist nach Tag 10 ist
    vorbei. Unparsebares Datum → False."""
    try:
        dd, mm, yy = ds.split(".")
        edate = datetime(int(yy), int(mm), int(dd)).date()
    except (ValueError, AttributeError, TypeError):
        return False
    end = trading_date.nth_trading_day_after(edate, ROLLING_WINDOW_TRADING_DAYS,
                                             US_MARKET_HOLIDAYS)
    final_cut = trading_date.last_final_close_date(now)
    n = e.get("rolling_window_n")
    # Vollständig = 11 vollständige Zeilen UND Tag 10 schon vor dem letzten
    # finalen Schluss (Halbzeilen-Fix 12.11.2026, gleiche Regel wie
    # backtest_history._rolling_window_is_complete).
    if (isinstance(n, int) and not isinstance(n, bool)
            and n >= ROLLING_WINDOW_TRADING_DAYS + 1 and final_cut > end):
        return True
    return final_cut > end + timedelta(days=ROLLING_WINDOW_GRACE_DAYS)


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

    Kriterien pro Record: ``source != "bootstrap"``, gereift (``return_10d``
    gefüllt UND ``days_old > 14`` Kalendertage → auch Rolling-Felder final),
    ``(ticker, date)`` noch nicht exportiert. KEIN score-Filter.

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
        if e.get("return_10d") is None:          # noch nicht gereift (Outcome-Feld)
            continue
        t, d = e.get("ticker"), e.get("date")
        if not t or not d:
            continue
        # REIFE-GATE #2 (days_old > 14): return_10d allein reicht NICHT. Grund —
        # ``max_gain_pct`` UND ``max_drawdown_pct`` sind ROLLING über die ersten
        # ≤ 10 Handelstage (backtest_history.py: dieselbe ``df_since[:11]``-Slice,
        # dieselbe ``days_old <= 14``-Schranke, EIN Loop → kein Fenster-Divergenz,
        # ``> 14`` deckt beide ab). ``return_10d`` füllt aber schon bei ≥ 10
        # gezählten Mo–Fr (``_trading_days_elapsed``, feiertags-blind) — teils
        # 1–3 Kalendertage BEVOR das max_gain-/max_drawdown-Fenster final ist.
        # Ohne diese zweite Schranke fröre der append-only-Export nicht-finale
        # Peak-Werte DAUERHAFT ein (gemessen 04.08.2026: 23/452 Records drifteten
        # nach return_10d-Fill noch, bis 133 pp, gerichtet auf die Top-Mover —
        # genau die Zielgruppe der Auswertung). Erst ab Kalendertag 15 ist beides
        # ausgereizt und der Snapshot endgültig.
        if "rolling_window_n" in e:
            # Neue Regel (Fix 13.11.2026, open_item max-gain-rolling-fenster-
            # abgeschnitten): erst exportieren, wenn das Rolling-Fenster
            # vollständig ist (11 finale Tageszeilen D..Tag 10) ODER die
            # Nachfrist nach Tag 10 vorbei ist (dann bleibt es, wie es ist —
            # der Wächter S17 zählt solche Zeilen). Uhrzeit-/Kalendertag-
            # unabhängig: Tag 10 aus dem Handelskalender, „final“ über
            # trading_date.last_final_close_date (ET, 16:20).
            if not _rolling_window_complete(e, d, now):
                continue
        else:
            _days_old = _calendar_days_old(d, now)
            if _days_old is None or _days_old <= 14:
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
