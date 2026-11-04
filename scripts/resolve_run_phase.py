"""Single-Source-of-Truth für RUN_PHASE-Resolution im Daily-Run-Workflow.

Resolution-Logik:

1. ``schedule``-Trigger: fester Mapping pro Cron — `37 21 * * 1-5` → postclose,
   alles andere (insb. `17 6 * * 1-5`) → premarket. **Plausibilitäts-Override
   greift hier nicht**, weil Cron-Trigger zeitlich gepinnt sind. Seit
   04.11.2026 Minute 37 (vorher `17 21`): 21:37 UTC = 16:37 ET im Winter, also
   immer nach der Postclose-Grenze 16:20 ET (``trading_date.US_CLOSE_FINAL_ET``).
   Der alte String `17 21 * * 1-5` wird für den Übergang (ein noch
   eingereihter Lauf) weiter als postclose erkannt; der Vintage-Guard
   verhindert dann trotzdem Einträge vor 16:20 ET.

2. ``workflow_dispatch``-Trigger: User-Input wird gegen die aktuelle UTC-Zeit
   plausibilitäts-geprüft:

   - US-Session (09:30 ≤ ET < 16:00) + `postclose` → **Override auf premarket**.
     Backtest-History würde sonst mit Intraday-Mid-Day-Werten gefüllt.
   - Schluss noch nicht final (16:00 ≤ ET < 16:20, seit 04.11.2026) +
     `postclose` → **Override auf premarket** (``close_not_final_override``);
     + `premarket` → bleibt premarket.
   - Post-Close (ET ≥ 16:20, ``trading_date.US_CLOSE_FINAL_ET``) +
     `premarket` → **Override auf postclose**.
     Backtest-History würde sonst ausbleiben, obwohl konsolidierte Daten da.
   - Pre-US-Session (ET < 09:30) → kein Override (User-Wahl bleibt).

   Grenzen seit 02.11.2026 in US-Ostküstenzeit (``trading_date.us_session_
   state``, DST-korrekt): Sommer 13:30/20:00 UTC, Winter 14:30/21:00 UTC.
   Vorher standen sie fest auf 13:30/20:00 UTC (nur Sommerzeit richtig).
   - US-Session + `premarket` / Post-Close + `postclose` → kein Override
     (User-Wahl ist plausibel).

Aufruf:
  Im Workflow als eigener Step, schreibt ``RUN_PHASE=<phase>`` nach
  ``$GITHUB_ENV`` und Warnungen nach stdout. Lokaler Aufruf (ohne
  ``GITHUB_ENV``) schreibt nur nach stdout.

Tests: ``scripts/mock_test_run_phase_resolution.py``.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from trading_date import us_session_state  # noqa: E402  (EINE Quelle, ET-basiert)

_VALID_PHASES = ("premarket", "postclose")
# Feste Cron→postclose-Zuordnung. "37 21" ist der aktuelle Postclose-Cron
# (daily-squeeze-report.yml, seit 04.11.2026); "17 21" nur noch für den
# Übergang (bereits eingereihter Lauf des alten Crons).
POSTCLOSE_CRONS = ("37 21 * * 1-5", "17 21 * * 1-5")


def resolve_run_phase(
    event_name: str,
    schedule: str | None,
    user_input: str | None,
    now_utc: datetime,
) -> tuple[str, str | None]:
    """Liefert ``(phase, override_reason)``.

    ``override_reason`` ist None, wenn kein Override stattgefunden hat — sonst
    ein Kurz-Code (``"us_session_override"`` / ``"post_close_override"`` /
    ``"no_input_fallback"``), den der Caller ins Run-Log schreibt.
    """
    if event_name == "schedule":
        if schedule in POSTCLOSE_CRONS:
            return "postclose", None
        return "premarket", None

    if event_name != "workflow_dispatch":
        return "premarket", "non_dispatch_fallback"

    chosen = (user_input or "").strip().lower()
    if chosen not in _VALID_PHASES:
        return "premarket", "no_input_fallback"

    state = us_session_state(now_utc)
    if state == "open":
        if chosen == "postclose":
            return "premarket", "us_session_override"
    elif state == "closing":
        if chosen == "postclose":
            return "premarket", "close_not_final_override"
    elif state == "post":
        if chosen == "premarket":
            return "postclose", "post_close_override"

    return chosen, None


_REASON_TEXTS = {
    "us_session_override": (
        "⚠ Override: workflow_dispatch wurde mit run_phase=postclose getriggert, "
        "aber die aktuelle Zeit liegt in der US-Session (09:30–16:00 ET). "
        "Forciere premarket — Backtest-Pollution wird so vermieden."
    ),
    "post_close_override": (
        "⚠ Override: workflow_dispatch wurde mit run_phase=premarket getriggert, "
        "aber die aktuelle Zeit liegt nach dem finalen Schluss (≥16:20 ET). "
        "Forciere postclose — Backtest würde sonst trotz EOD-Daten leer bleiben."
    ),
    "close_not_final_override": (
        "⚠ Override: workflow_dispatch wurde mit run_phase=postclose getriggert, "
        "aber der Schlusskurs ist noch nicht final (16:00–16:20 ET). "
        "Forciere premarket — Backtest-Einträge erst ab 16:20 ET."
    ),
    "no_input_fallback": (
        "⚠ Fallback: workflow_dispatch ohne run_phase-Input — forciere premarket "
        "(sicher: kein Backtest-Befüllen)."
    ),
    "non_dispatch_fallback": (
        "⚠ Fallback: unbekannter event_name — forciere premarket."
    ),
}


def main() -> int:
    event_name = os.environ.get("EVENT_NAME", "")
    schedule   = os.environ.get("EVENT_SCHEDULE") or None
    user_input = os.environ.get("USER_INPUT") or None
    now_utc    = datetime.now(timezone.utc)

    phase, reason = resolve_run_phase(event_name, schedule, user_input, now_utc)

    print(f"[resolve_run_phase] event={event_name} schedule={schedule!r} "
          f"input={user_input!r} now_utc={now_utc.isoformat()} "
          f"→ phase={phase} reason={reason}")
    if reason:
        print(_REASON_TEXTS.get(reason, f"⚠ Override ({reason})."))

    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as fh:
            fh.write(f"RUN_PHASE={phase}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
