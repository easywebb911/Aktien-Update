#!/usr/bin/env python3
"""Einmaliger, idempotenter Flanken-Reset: Fehlalarm-``trend_break`` aus
``agent_state.json → exit_push_dedupe[*].last_active`` entfernen.

ANLASS (27.07.2026, NaN-Dichtigkeit): Zwischen dem 25.07. 10:43Z und dem
NaN-Fix meldete ``_exit_p2_trigger_trend_break`` für alle offenen Positionen
``crit=True`` bei ``price=null`` — ein NaN-Close rutschte durch den negierten
Guard (``nan <= 0`` ist False), ``drop_pct`` wurde NaN, beide Schwellen-
Vergleiche waren False, der else-Zweig setzte crit. Der Push-Pfad
(``ki_agent.process_exit_signals``) verlangt ``crit AND available`` — beides
war True, der Fehlalarm passierte das Gate und schrieb sich als
``last_active: ["trend_break"]`` in den Dedupe-State. Solange dieser Eintrag
steht, erzeugt ein **echter** Trendbruch keine frische Flanke mehr.

WICHTIG — dieses Skript ist ein BESCHLEUNIGER, kein Zwang:
``_exit_dedupe_set`` wird in ``process_exit_signals`` **unbedingt** je Tick
aufgerufen ("State persistieren (immer, für konsistente Flanken-Verfolgung)").
Sobald der NaN-Fix greift, verschwindet der falsche crit aus
``crit_triggers`` → ``current_active`` ist leer → ``last_active`` wird beim
nächsten Tick ohnehin auf ``[]`` geschrieben. Das Skript nimmt genau diesen
einen Tick vorweg (z. B. wenn zwischen Merge und nächstem Tick ein echter
Trendbruch fallen könnte).

Eigenschaften:
  • DETERMINISTISCH — nur die namentlich gelisteten Ticker, nur der Eintrag
    ``"trend_break"``; alles andere (andere Trigger, last_push_date,
    esc_alerted, andere Ticker) bleibt unangetastet.
  • IDEMPOTENT — ein zweiter Lauf ändert nichts und schreibt nicht.
  • FAIL-SOFT — fehlende Datei/Feld/korrupter Container → 0 Änderungen, exit 0.

Aufruf:  python scripts/reset_exit_dedupe_trend_break.py [--state PFAD] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# Betroffene Positionen (Stand 27.07.2026). AMC ist bewusst mit aufgeführt,
# obwohl es wegen ``no_exit_alerts: true`` gar keinen Dedupe-Eintrag hat —
# das Skript ist dort ein No-Op und dokumentiert die vollständige Liste.
AFFECTED_TICKERS = ("AMC", "IONQ", "PDYN", "AI", "LENZ", "WOLF")
FALSE_TRIGGER = "trend_break"
DEFAULT_STATE = "agent_state.json"


def reset_dedupe(state: dict,
                 tickers: tuple[str, ...] = AFFECTED_TICKERS,
                 trigger: str = FALSE_TRIGGER) -> list[str]:
    """Entfernt ``trigger`` aus ``last_active`` der gelisteten Ticker.

    Mutiert ``state`` in-place und gibt die Liste der geänderten Ticker
    zurück (leer = nichts zu tun → Idempotenz). Nicht-Dicts / fehlende
    Einträge / fehlende Listen werden übersprungen, nie erzeugt.
    """
    changed: list[str] = []
    dedupe = state.get("exit_push_dedupe")
    if not isinstance(dedupe, dict):
        return changed
    for ticker in tickers:
        entry = dedupe.get(ticker)
        if not isinstance(entry, dict):
            continue
        active = entry.get("last_active")
        if not isinstance(active, list) or trigger not in active:
            continue
        entry["last_active"] = [t for t in active if t != trigger]
        changed.append(ticker)
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state", default=DEFAULT_STATE)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    path = pathlib.Path(args.state)
    if not path.exists():
        print(f"[reset] {path} fehlt — nichts zu tun.")
        return 0
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[reset] {path} nicht lesbar ({exc}) — nichts zu tun.")
        return 0
    if not isinstance(state, dict):
        print("[reset] State ist kein Objekt — nichts zu tun.")
        return 0

    changed = reset_dedupe(state)
    if not changed:
        print("[reset] Keine Änderung nötig (idempotent).")
        return 0
    if args.dry_run:
        print(f"[reset] DRY-RUN — würde bereinigen: {', '.join(changed)}")
        return 0
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print(f"[reset] '{FALSE_TRIGGER}' entfernt bei: {', '.join(changed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
