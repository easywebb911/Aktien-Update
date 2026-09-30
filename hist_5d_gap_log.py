"""Persistenz für die von ``_extract_hist_5d`` verworfenen Tage/Zellen
(Folge-PR zu #561, 30.09.2026).

## Hintergrund

PR #561 (25.09.2026, ``642ea1b3``) fügte ``log.warning()``-Zeilen in
``_extract_hist_5d`` (``generate_report.py``) hinzu, um die "batch-weites
yfinance-Datenloch"-Hypothese aus der S10-crit-Diagnose
(``coiled_spring_score``/``vol_stability_5d``/``rvol_buildup_5d`` ~90 %
null) empirisch nachprüfbar zu machen. Diagnose 30.09.2026: diese Zeilen
landen NUR im ephemeren GitHub-Actions-Konsolenoutput -- kein
``actions/upload-artifact``, kein Log-File, kein ``GITHUB_STEP_SUMMARY``
in ``daily-squeeze-report.yml``. Die Diagnose-Absicht des PRs war dadurch
faktisch nicht nutzbar: trotz zwei neuer batch-weiter Ausfälle (28./29.09.,
je 10/10 Ticker 100 % null) konnten die zugrunde liegenden Zell-/Tag-
Details nicht eingesehen werden.

Dieses Modul schreibt DIESELBE Information zusätzlich in eine
persistierte JSONL-Datei. Die bestehenden ``log.warning()``-Aufrufe aus
PR #561 bleiben UNVERÄNDERT (sie funktionieren korrekt, landen nur am
falschen Ort) -- und die All-or-Nothing-Guard-Entscheidung selbst
(welcher Tag verworfen wird, ob ``hist_5d`` am Ende leer ist) ist von
diesem PR in KEINER Weise berührt.

## Warum eine neue Datei statt eine bestehende zu erweitern

Geprüft und verworfen:
- ``score_inflation_log.jsonl`` -- Score-/Sub-Score-/Driver-Schema,
  thematisch Score-Inflation. Ein Zell-/Tag-Gap-Ereignis hat keinen
  Score-Bezug; die Schemata würden sich nur künstlich überlappen.
- ``health_check_log.jsonl`` -- aggregierte State-Invariant-Befunde
  (S1-S14, prozentuale Nullraten), KEIN Zell-/Tag-Detail-Schema. Genau
  DIESE Aggregat-Ebene (S10) hat die Diagnose bereits geliefert --
  der fehlende Mehrwert ist die granulare Einzel-Event-Ebene darunter.

Ein schmales, eigenständiges Log passt zum bereits etablierten Muster
dieses Projekts (``provider_health.jsonl``, ``exit_shadow_log.jsonl``,
``matured_backtest_export.jsonl`` sind ebenfalls je ein eigenständiges,
schmales Schema statt eines geteilten Sammel-Logs).

## Volumen-Abschätzung

``_extract_hist_5d`` läuft ausschließlich im Daily-Run
(``generate_report.py``), NICHT im stündlichen ki_agent-Tick (verifiziert
30.09.2026: kein Aufruf in ``ki_agent.py``, nur ein Kommentar-Verweis) --
also 2×/Werktag. Pro Ticker maximal 6 Zeilen (bis zu 5 Tag-Verwürfe +
1 Zusammenfassung), typischerweise 0 an gesunden Tagen. Die Diagnose
30.09.2026 zeigte ein binäres Tages-Muster (0 % oder 100 % des ~100-200-
Ticker-Pools) -- ein einzelner Ausfall-Tag kann daher kurzfristig
mehrere hundert Zeilen erzeugen, gesunde Tage erzeugen 0. ``CUTOFF_DAYS
= 30`` (identisch zu ``score_inflation_log.py``) hält die Datei dauerhaft
im Rahmen von wenigen tausend Zeilen selbst bei mehreren Ausfall-Tagen
pro Monat.

## Architektur

Identisches Muster zu ``score_inflation_log.py``: Append-only JSONL,
``schema_v``-Marker, atomarer Prune (tmpfile + ``os.replace``), fail-soft
bei ``OSError`` (kein Re-Raise -- der Daily-Run darf niemals wegen dieses
Logs abbrechen).

**Eine bewusste Abweichung:** ``path`` hat hier KEINEN am Funktions-Kopf
gebundenen Default (``path: str = LOG_FILE`` wie in
``score_inflation_log.py``), sondern einen ``None``-Sentinel, der ERST im
Funktionskörper gegen die Modul-Konstante ``LOG_FILE`` aufgelöst wird.
Grund: die Aufrufstellen in ``_extract_hist_5d`` (``generate_report.py``)
rufen ohne ``path``-Argument auf -- die Funktionssignatur von
``_extract_hist_5d`` selbst darf laut Auftrag NICHT verändert werden
(kein neuer Parameter). Ein am Funktions-Kopf gebundener Default würde
sich beim Testen NICHT per ``mock.patch.object(hist_5d_gap_log,
"LOG_FILE", ...)`` umleiten lassen (Python bindet Default-Argumente bei
Funktionsdefinition, nicht bei jedem Aufruf) -- der ``None``-Sentinel
löst das, weil ``LOG_FILE`` dann bei JEDEM Aufruf frisch aus dem Modul-
Namespace gelesen wird. Direkte Aufrufer von ``record_gap``/``prune_log``/
``read_all`` (z. B. Tests, Tools) können weiterhin ``path=...`` explizit
setzen, exakt wie bei ``score_inflation_log.py``.

## Aufruf-Isolation (kein Effekt auf die Guard-Entscheidung)

``_extract_hist_5d`` ist komplett von EINEM äußeren
``try/except Exception`` umschlossen, das bei jedem ungefangenen Fehler
``[]`` zurückliefert. Ohne zusätzliche Absicherung an der Aufrufstelle
könnte ein hypothetischer Fehler in DIESEM Logging-Code die Guard-
Entscheidung selbst verfälschen (ein korrektes Ergebnis würde durch eine
Logging-Exception fälschlich zu einer leeren Liste) -- deshalb wrappt
jede Aufrufstelle in ``generate_report.py`` den ``record_gap()``-Call
zusätzlich in ein eigenes ``try/except Exception: pass`` (Defense-in-
Depth über das interne Fail-Soft von ``record_gap()`` hinaus).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

LOG_FILE = "hist_5d_gap_log.jsonl"
CUTOFF_DAYS = 30  # identisch zu score_inflation_log.py

SCHEMA_V = 1


def record_gap(
    ticker: str,
    reason: str,
    *,
    dropped_day: object = None,
    missing_cells: list[str] | None = None,
    n_days: int | None = None,
    window: int | None = None,
    run_ts: datetime | None = None,
    path: str | None = None,
) -> bool:
    """Append EINE JSONL-Zeile für einen von ``_extract_hist_5d``
    verworfenen Tag oder eine Zusammenfassungs-Warnung.

    ``reason`` entspricht 1:1 einer der drei ``log.warning()``-Call-
    Sites in ``_extract_hist_5d``:

    - ``"nonfinite_cell"``: genau EIN Tag verworfen -- ``dropped_day``
      (Datum/Index der Zeile) und ``missing_cells`` (Liste aus
      ``Volume``/``High``/``Low``/``Close``) gesetzt.
    - ``"insufficient_raw_days"``: weniger als ``window`` Roh-Tage im
      Batch-Fenster -- ``n_days`` = tatsächliche Roh-Tage-Anzahl,
      ``dropped_day``/``missing_cells`` bleiben leer (kein einzelner
      Tag betroffen, der ganze Ticker).
    - ``"insufficient_valid_days"``: weniger als ``window`` valide Tage
      NACH dem Zell-Guard -- ``n_days`` = tatsächliche valide Tage-
      Anzahl.

    Fail-soft: ``OSError`` -> ``False``, KEIN Re-Raise (siehe Modul-
    Docstring "Aufruf-Isolation" -- der Aufrufer wrappt zusätzlich
    selbst in ``try/except``, dies hier ist die zweite
    Verteidigungslinie).
    """
    if run_ts is None:
        run_ts = datetime.now(timezone.utc)
    if path is None:
        path = LOG_FILE
    entry = {
        "schema_v": SCHEMA_V,
        "run_ts": run_ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker": ticker,
        "reason": reason,
        "dropped_day": str(dropped_day) if dropped_day is not None else None,
        "missing_cells": list(missing_cells) if missing_cells else [],
        "n_days": n_days,
        "window": window,
    }
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except OSError as exc:
        log.warning("hist_5d_gap_log: Schreibfehler an %s — übersprungen: %s",
                    path, exc)
        return False


def prune_log(max_days: int = CUTOFF_DAYS, path: str | None = None) -> int:
    """Entferne Einträge älter als ``max_days`` Kalendertage.

    Identisches Muster zu ``score_inflation_log.prune_log``: liest die
    ganze Datei, filtert per ``run_ts`` (ISO, korrekt geparst -- nicht
    lexikographisch), schreibt das Resultat atomar zurück (tmpfile +
    ``os.replace``). Kaputte Zeilen werden NICHT gedroppt (Operator
    entscheidet, bis Manual-Cleanup), Fail-soft bei Schreibfehler
    (Datei bleibt unverändert).
    """
    if path is None:
        path = LOG_FILE
    if not os.path.exists(path):
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    kept: list[str] = []
    n_seen = 0
    n_bad = 0
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                n_seen += 1
                try:
                    obj = json.loads(line)
                    ts_str = obj.get("run_ts", "")
                    ts_str_iso = (ts_str[:-1] + "+00:00"
                                  if ts_str.endswith("Z") else ts_str)
                    ts = datetime.fromisoformat(ts_str_iso)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    n_bad += 1
                    log.warning("hist_5d_gap_log: kaputte Zeile übersprungen "
                                "(behält sie aber bis Manual-Cleanup): %s", exc)
                    kept.append(line)
                    continue
                if ts >= cutoff:
                    kept.append(line)
    except OSError as exc:
        log.warning("hist_5d_gap_log: Prune-Read-Fehler — übersprungen: %s", exc)
        return 0

    n_removed = n_seen - (len(kept) - n_bad)
    if n_removed <= 0:
        return 0

    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            for line in kept:
                fh.write(line + "\n")
        os.replace(tmp_path, path)
    except OSError as exc:
        log.warning("hist_5d_gap_log: Prune-Write-Fehler — Datei unverändert: %s", exc)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return 0
    log.info("hist_5d_gap_log: %d Einträge (älter als %d Tage) geprunt",
              n_removed, max_days)
    return n_removed


def read_all(path: str | None = None) -> list[dict]:
    """Tool-Helper: liest alle Einträge zurück als Liste. Kaputte Zeilen
    werden geskippt (kein Crash). Für CLI-Diagnose und Tests."""
    if path is None:
        path = LOG_FILE
    if not os.path.exists(path):
        return []
    entries: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries
