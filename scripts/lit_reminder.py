"""Wöchentlicher Lit-Check-Reminder — standalone ntfy-Push (Freitag).

ZWECK: Ein einziger zeitgesteuerter Reminder-Push mit FIXEM Text, der Easy
wöchentlich erinnert, nach neuer Squeeze-Forschung zu schauen. **KEIN
Trade-Bezug, kein Ticker, kein Score, kein Link, kein Zustand.**

ARCHITEKTUR — bewusst KOMPLETT ISOLIERT von der Trade-Push-Pipeline:
  - KEIN Cooldown (`is_on_cooldown`/`set_cooldown` — nicht importiert).
  - KEIN Silence-Filter (der lebt nur in ki_agent.detect_anomalies-Loop).
  - KEINE push_history (`_record_push` — nicht importiert; agent_state.json
    unangetastet).
  - KEIN State-File, KEIN git-Commit (fixer Wochen-Ping = bewusste Repetition,
    keine Dedup nötig). Der Workflow schreibt NICHTS ins Repo.
Damit ist die bestehende Trade-Push-Logik (Severity/Cooldown/History) durch
diesen Reminder strukturell nicht berührbar.

EIGENE KATEGORIE: Titel `LIT_REMINDER_TITLE`, Priority `LIT_REMINDER_PRIORITY`
(bewusst `default` — kein high/urgent Aktions-Signal), Tag `LIT_REMINDER_TAGS`
(`books` = 📚). Disjunkt zu den Trade-Tags (rotating_light/warning) und
Trade-`kind`s (anomaly/exit_p1/exit_p2/earnings_immediate/conviction_high).

ntfy-Mechanik: identisches URL-Pattern wie alle funktionierenden Sender im Tool
(`POST https://ntfy.sh/{topic}` + `data=`-Body + Title/Priority/Tags-Header).
Title MUSS ASCII-only sein (HTTP-Header RFC 7230 latin-1) → Emoji wird gestrippt;
Body bleibt UTF-8 (läuft als `data=`). Faustregel aus CLAUDE.md.

Fail-Visibility: `NTFY_TOPIC` gesetzt UND Send scheitert → exit 1 (GitHub
markiert Run rot + Email). `NTFY_ENABLED=False`/leerer Topic → exit 0 (graceful
no-op). `LIT_REMINDER_ENABLED=False` → exit 0 (Feature-Schalter).
"""
from __future__ import annotations

import logging
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import (  # noqa: E402
    LIT_REMINDER_ENABLED,
    LIT_REMINDER_TITLE,
    LIT_REMINDER_BODY,
    LIT_REMINDER_PRIORITY,
    LIT_REMINDER_TAGS,
    NTFY_ENABLED,
    NTFY_TOPIC,
)

try:                       # requests fehlt in reinen Mock-Test-Slots — dann no-op
    import requests        # noqa: E402
except ImportError:        # pragma: no cover
    requests = None        # type: ignore

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("lit_reminder")


def _ntfy_send(title: str, body: str, priority: str, tags: str) -> bool:
    """Sendet den Reminder via ntfy.sh URL-Pattern. Fail-soft (kein Re-Raise).

    Spiegelt bewusst ``scripts/health_check_digest._ntfy_send`` (bewährtes
    URL-Pattern, ASCII-Title-Strip). KEIN Trade-Pipeline-Aufruf.
    """
    if not NTFY_ENABLED or not NTFY_TOPIC:
        log.info("ntfy disabled — Reminder-Body würde sein:\n%s", body)
        return False
    if requests is None:
        log.warning("requests-Modul fehlt — Reminder-Push übersprungen")
        return False
    # ASCII-clean Title (Header-Constraint). Body bleibt UTF-8.
    title_ascii = title.encode("ascii", "ignore").decode("ascii").strip()
    if not title_ascii:
        title_ascii = "Lit-Check-Reminder"
    headers = {"Title": title_ascii, "Priority": priority}
    if tags:
        headers["Tags"] = tags
    try:
        resp = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        if resp.status_code >= 400:
            log.warning("Reminder-Push HTTP %d (FAIL): %s",
                        resp.status_code, resp.text[:200])
            return False
        log.info("Reminder-Push HTTP %d (OK) — title=%r priority=%s tags=%s",
                 resp.status_code, title_ascii, priority, tags)
        return True
    except Exception as exc:   # pragma: no cover  (Netzwerk-Fehler)
        log.warning("Reminder-Push fehlgeschlagen: %s", exc)
        return False


def main() -> int:
    if not LIT_REMINDER_ENABLED:
        log.info("LIT_REMINDER_ENABLED=False — no-op.")
        return 0
    ok = _ntfy_send(LIT_REMINDER_TITLE, LIT_REMINDER_BODY,
                    LIT_REMINDER_PRIORITY, LIT_REMINDER_TAGS)
    # Fail-Visibility: nur wenn ntfy konfiguriert ist (Topic gesetzt) UND der
    # Send scheiterte → exit 1. Ohne Topic ist der no-op erwartet (kein Fehler).
    if not ok and NTFY_ENABLED and NTFY_TOPIC:
        log.error("Reminder-Push scheiterte trotz konfiguriertem NTFY_TOPIC.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
