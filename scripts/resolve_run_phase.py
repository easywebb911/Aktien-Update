"""Single-Source-of-Truth für RUN_PHASE-Resolution im Daily-Run-Workflow.

Resolution-Logik:

1. ``schedule``-Trigger: fester Mapping pro Cron — `0 21 * * 1-5` → postclose,
   alles andere (insb. `0 10 * * 1-5`) → premarket. **Plausibilitäts-Override
   greift hier nicht**, weil Cron-Trigger zeitlich gepinnt sind.

2. ``workflow_dispatch``-Trigger: User-Input wird gegen die aktuelle UTC-Zeit
   plausibilitäts-geprüft:

   - US-Session (13:30 ≤ UTC < 20:00) + `postclose` → **Override auf premarket**.
     Backtest-History würde sonst mit Intraday-Mid-Day-Werten gefüllt.
   - Post-Close (UTC ≥ 20:00) + `premarket` → **Override auf postclose**.
     Backtest-History würde sonst ausbleiben, obwohl konsolidierte Daten da.
   - Pre-US-Session (UTC < 13:30) → kein Override (User-Wahl bleibt).
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
from datetime import datetime, time, timezone

US_SESSION_START = time(13, 30)
US_SESSION_END   = time(20, 0)

_VALID_PHASES = ("premarket", "postclose")


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
        if schedule == "0 21 * * 1-5":
            return "postclose", None
        return "premarket", None

    if event_name != "workflow_dispatch":
        return "premarket", "non_dispatch_fallback"

    chosen = (user_input or "").strip().lower()
    if chosen not in _VALID_PHASES:
        return "premarket", "no_input_fallback"

    now_t = now_utc.time()
    if US_SESSION_START <= now_t < US_SESSION_END:
        if chosen == "postclose":
            return "premarket", "us_session_override"
    elif now_t >= US_SESSION_END:
        if chosen == "premarket":
            return "postclose", "post_close_override"

    return chosen, None


_REASON_TEXTS = {
    "us_session_override": (
        "⚠ Override: workflow_dispatch wurde mit run_phase=postclose getriggert, "
        "aber aktuelle UTC-Zeit liegt in der US-Session (13:30–20:00). "
        "Forciere premarket — Backtest-Pollution wird so vermieden."
    ),
    "post_close_override": (
        "⚠ Override: workflow_dispatch wurde mit run_phase=premarket getriggert, "
        "aber aktuelle UTC-Zeit liegt nach US-Close (≥20:00). "
        "Forciere postclose — Backtest würde sonst trotz EOD-Daten leer bleiben."
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
