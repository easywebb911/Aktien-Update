"""Single-Source-of-Truth für Push-History-Persistenz (Phase 2 Stufe 3c-1).

Das ``_record_push``-Helper hatte zuvor zwei strukturell identische
Duplikate in ``ki_agent.py`` und ``generate_report.py``. Beide Wege
schreiben Berlin-ISO-Timestamps, denselben Schema-Satz und denselben
FIFO-Cap. Diese Datei eliminiert das Drift-Risiko — Schema-Änderungen
müssen nun nur an einer Stelle nachgezogen werden.

Modul-Speicherort: Repo-Root (statt ``scripts/``), weil es zur Laufzeit
in den Daily-Run und ki_agent eingebunden wird, nicht ein Tool-Skript.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from config import PUSH_HISTORY_MAX

_BERLIN = ZoneInfo("Europe/Berlin")


def _record_push(state: dict, ticker: str, kind: str, severity: str,
                 trigger: str | None, body: str, success: bool) -> None:
    """FIFO-Append eines Push-Versuchs in ``state["push_history"]``.

    Entry-Schema:
      ``{ts, ticker, kind, severity, trigger, body, success}``

    Cap = ``PUSH_HISTORY_MAX`` (älteste Einträge werden abgeschnitten).
    Auch fehlgeschlagene Pushes (``success=False``) werden persistiert,
    damit Audit-Trails beim ntfy-Disable / POST-Fehler nachvollziehbar
    bleiben.

    FIFO-Cap = 100 macht uns gegen einzelne fehlende Einträge robust bei
    Race zwischen ki_agent und Daily-Run. Last-Write-Wins akzeptiert.
    """
    entry = {
        "ts":       datetime.now(_BERLIN).isoformat(),
        "ticker":   ticker,
        "kind":     kind,
        "severity": severity,
        "trigger":  trigger,
        "body":     body,
        "success":  bool(success),
    }
    hist = state.setdefault("push_history", [])
    hist.append(entry)
    if len(hist) > PUSH_HISTORY_MAX:
        del hist[: len(hist) - PUSH_HISTORY_MAX]
