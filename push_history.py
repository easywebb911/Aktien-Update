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
                 trigger: str | None, body: str, success: bool,
                 suppressed: bool = False,
                 suppress_reason: str | None = None,
                 conviction_score: int | float | None = None) -> None:
    """FIFO-Append eines Push-Versuchs in ``state["push_history"]``.

    Entry-Schema:
      ``{ts, ticker, kind, severity, trigger, body, success,
         suppressed, suppress_reason, conviction_score}``

    Cap = ``PUSH_HISTORY_MAX`` (älteste Einträge werden abgeschnitten).
    Auch fehlgeschlagene Pushes (``success=False``) werden persistiert,
    damit Audit-Trails beim ntfy-Disable / POST-Fehler nachvollziehbar
    bleiben.

    ``suppressed=True`` bedeutet: Push wurde absichtlich nicht an ntfy
    geschickt (z. B. Conviction-Gating). ``success`` ist dann ``False``
    (kein Push erfolgreich), aber ``suppressed`` markiert die Absicht
    statt eines Netzwerk-/Konfig-Fehlers. ``suppress_reason`` liefert
    den Kurz-Code (``"conviction_below_threshold"`` etc.) für die UI.

    ``conviction_score`` ist optional. Bei Anomaly- und Earnings-
    Pushes wird der Wert zum Push-Zeitpunkt mitpersistiert — damit
    spätere Aktivitäts-Berichte sehen können, ob ein Push aktions-
    relevant war oder im Rauschen unterging. Bei Exit-Pushes
    (kind=exit_p2/exit_p1) ist der Wert in der Regel ``None``
    (Conviction misst Substrat des Setups, nicht Exit-Druck).

    FIFO-Cap = 100 macht uns gegen einzelne fehlende Einträge robust bei
    Race zwischen ki_agent und Daily-Run. Last-Write-Wins akzeptiert.
    """
    try:
        conv_int = int(round(conviction_score)) if conviction_score is not None else None
    except (TypeError, ValueError):
        conv_int = None
    entry = {
        "ts":       datetime.now(_BERLIN).isoformat(),
        "ticker":   ticker,
        "kind":     kind,
        "severity": severity,
        "trigger":  trigger,
        "body":     body,
        "success":  bool(success),
        "suppressed":       bool(suppressed),
        "suppress_reason":  suppress_reason if suppressed else None,
        "conviction_score": conv_int,
    }
    hist = state.setdefault("push_history", [])
    hist.append(entry)
    if len(hist) > PUSH_HISTORY_MAX:
        del hist[: len(hist) - PUSH_HISTORY_MAX]
