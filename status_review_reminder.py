"""Status-Drift-Wecker — erinnert an fällige Score-Validierungs-Re-Tests.

ZWECK: Die Status-Texte in ``config.SCORE_STATUS_LABELS`` veralten planmäßig
(Re-Test-Kalender). Dieser Wecker prüft im TÄGLICHEN Daily-Run, ob ein
``review_by``-Datum überschritten ist, und schickt EINE ntfy-Erinnerung.
**Er ändert NICHTS** — kein Score, kein State, kein Repo-Write, keine
Entscheidung. Nur „schau nochmal nach dem Befund".

WARUM HIER (nicht als eigener Workflow): der Prüfpfad MUSS in einem täglich
laufenden Codepfad liegen. ``generate_report.main()`` (Daily-Run, 2×/Werktag)
ruft ``run(now, run_phase)`` — kein neuer Workflow, Workflows unangetastet.

DROSSELUNG (deterministisch, KEIN State-File): der Wecker feuert nur am
``STATUS_REVIEW_WECKER_WEEKDAY`` (Montag) UND nur im ``postclose``-Lauf → in
der Regel 1×/Woche/Score. Bewusst OHNE State-Dedup: ein zweiter postclose-Lauf
am selben Montag (z. B. manueller ``workflow_dispatch`` mit ``postclose``)
würde erneut erinnern — akzeptiert, weil reine Erinnerung ohne Trading-/Daten-
Effekt. Kein Daueralarm im Regelbetrieb (Cron feuert postclose 1×/Tag). (Edge:
fällt der Montag-postclose-Run aus — US-Feiertag —, rutscht die Erinnerung eine
Woche; für Monats-Termine irrelevant.)

ntfy-Mechanik: identisches URL-Pattern wie ``scripts/lit_reminder.py`` /
alle funktionierenden Sender (``POST https://ntfy.sh/{topic}`` + ``data=``-Body
+ Title/Priority/Tags-Header, ASCII-Title-Strip). KEIN Trade-Pipeline-Aufruf
(kein Cooldown, kein Silence-Filter, keine push_history).
"""
from __future__ import annotations

import datetime as _dt
import logging
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import (  # noqa: E402
    SCORE_STATUS_LABELS,
    STATUS_REVIEW_WECKER_ENABLED,
    STATUS_REVIEW_WECKER_WEEKDAY,
    STATUS_REVIEW_WECKER_TITLE,
    STATUS_REVIEW_WECKER_TAGS,
    STATUS_REVIEW_WECKER_PRIORITY,
    NTFY_ENABLED,
    NTFY_TOPIC,
)

try:                       # requests fehlt in reinen Mock-Test-Slots → no-op
    import requests        # noqa: E402
except ImportError:        # pragma: no cover
    requests = None        # type: ignore

log = logging.getLogger("status_review_reminder")


def find_due_reviews(labels: dict, now: _dt.datetime) -> list[dict]:
    """PURE: Liste der Score-Einträge mit gesetztem ``review_by`` < heute.

    Deterministisch, kein I/O. ``review_by=None`` (falsifiziert/datengetrieben)
    wird übersprungen. Ungültiges Datum → übersprungen (fail-soft).
    """
    today = now.date()
    due: list[dict] = []
    for key, entry in (labels or {}).items():
        rb = (entry or {}).get("review_by")
        if not rb:
            continue
        try:
            rb_date = _dt.date.fromisoformat(rb)
        except (TypeError, ValueError):
            continue
        if today > rb_date:
            due.append({
                "score":       key,
                "status":      (entry or {}).get("status", ""),
                "status_date": (entry or {}).get("status_date", ""),
                "review_by":   rb,
            })
    return due


def gate_open(now: _dt.datetime, run_phase: str) -> bool:
    """Deterministisches Wochentag-+Phasen-Gate (Montag + postclose). Im
    Cron-Regelbetrieb 1×/Woche; ohne State-Dedup könnte ein zweiter
    postclose-Lauf am selben Montag erneut feuern (akzeptiert)."""
    return (run_phase == "postclose"
            and now.weekday() == STATUS_REVIEW_WECKER_WEEKDAY)


def _reminder_body(item: dict) -> str:
    return (f"{item['score']}: registrierter Befund vom "
            f"{item['status_date'] or '?'} — Status '{item['status']}'. "
            f"review_by {item['review_by']} überschritten. Bitte Re-Test-Stand "
            f"prüfen und config.SCORE_STATUS_LABELS aktualisieren (Status + "
            f"status_date + review_by). Diese Erinnerung ändert nichts.")


def _ntfy_send(title: str, body: str) -> bool:
    """Sendet via ntfy.sh URL-Pattern (analog lit_reminder). Fail-soft."""
    if not NTFY_ENABLED or not NTFY_TOPIC:
        log.info("ntfy disabled — Wecker-Body:\n%s", body)
        return False
    if requests is None:
        log.warning("requests fehlt — Wecker-Push übersprungen")
        return False
    title_ascii = title.encode("ascii", "ignore").decode("ascii").strip()
    if not title_ascii:
        title_ascii = "Status-Review faellig"
    headers = {"Title": title_ascii, "Priority": STATUS_REVIEW_WECKER_PRIORITY}
    if STATUS_REVIEW_WECKER_TAGS:
        headers["Tags"] = STATUS_REVIEW_WECKER_TAGS
    try:
        resp = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        if resp.status_code >= 400:
            log.warning("Wecker-Push HTTP %d (FAIL): %s",
                        resp.status_code, resp.text[:200])
            return False
        log.info("Wecker-Push HTTP %d (OK) — %s", resp.status_code, title_ascii)
        return True
    except Exception as exc:   # pragma: no cover  (Netzwerk)
        log.warning("Wecker-Push fehlgeschlagen: %s", exc)
        return False


def run(now: _dt.datetime, run_phase: str, *, send_fn=None) -> int:
    """Prüft fällige Reviews und pusht (gedrosselt). Returnt Anzahl Pushes.

    Fail-soft-Vertrag: der Aufrufer (Daily-Run) wrappt zusätzlich in try/except;
    diese Funktion selbst wirft nicht bei fehlenden Feldern. ``send_fn``
    injizierbar für Tests (Default = ntfy).
    """
    if not STATUS_REVIEW_WECKER_ENABLED:
        return 0
    if not gate_open(now, run_phase):
        return 0
    due = find_due_reviews(SCORE_STATUS_LABELS, now)
    sender = send_fn or (lambda item: _ntfy_send(
        f"{STATUS_REVIEW_WECKER_TITLE}: {item['score']}", _reminder_body(item)))
    n_sent = 0
    for item in due:
        try:
            if sender(item):
                n_sent += 1
        except Exception as exc:   # pragma: no cover
            log.warning("Wecker-Send für %s fehlgeschlagen: %s",
                        item.get("score"), exc)
    log.info("Status-Wecker: %d fällig, %d gepusht (Weekday-Gate offen)",
             len(due), n_sent)
    return n_sent
