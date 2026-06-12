"""Guard-Test für .gitattributes union-Merge-Klassifikation (Kategorie A:
pures stdlib, env-frei, deterministisch, CI-gate-bar).

Schützt die belegte Klassifikation (Resolver-Lücke-Fix 12.06.2026):
- 5 PURE Append-Logs (open "a") bekommen ``merge=union`` → Rebase-Append-
  Konflikte lösen ohne Abort auf.
- ``exit_shadow_log.jsonl`` ist BEWUSST AUSGENOMMEN (Full-Rewrite open "w" +
  Re-Write-by-(ticker,date) + Forward-Backfill → union erzeugte Duplikat-Keys).

Falls jemand die Klassifikation kippt (exit_shadow versehentlich auf union,
oder einen der 5 Append-Logs entfernt), schlägt dieser Test an.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Pure Append-Logs (open(..., "a")) — union-sicher. Beleg pro Datei:
#   score_inflation_log.py:240  · health_check.py:1063 (record_run)
#   health_check.py:1231 (record_provider_call → provider_health + finra)
#   backtest_history.py:575 (_log_vintage_skip)
UNION_FILES = [
    "score_inflation_log.jsonl",
    "health_check_log.jsonl",
    "provider_health.jsonl",
    "finra_history_health.jsonl",
    "vintage_guard_log.jsonl",
]

# Full-Rewrite / keyed Re-Write (open(..., "w"), exit_shadow.py:178) — union
# würde Duplikat-Keys erzeugen → MUSS draußen bleiben.
EXCLUDED_FROM_UNION = "exit_shadow_log.jsonl"

_fails: list[str] = []


def _check(name, cond):
    if cond:
        print(f"  ✓ {name}")
    else:
        _fails.append(name)
        print(f"  ✗ {name}")


def main() -> int:
    ga = ROOT / ".gitattributes"
    _check(".gitattributes existiert", ga.exists())
    text = ga.read_text(encoding="utf-8") if ga.exists() else ""

    # Jede union-sichere Datei hat genau eine merge=union-Regel
    for f in UNION_FILES:
        line_ok = any(
            ln.split() and ln.split()[0] == f and "merge=union" in ln
            for ln in text.splitlines()
            if not ln.lstrip().startswith("#")
        )
        _check(f"{f} → merge=union", line_ok)

    # exit_shadow darf NICHT auf union stehen (in keiner Nicht-Kommentar-Zeile)
    exit_shadow_union = any(
        ln.split() and ln.split()[0] == EXCLUDED_FROM_UNION and "merge=union" in ln
        for ln in text.splitlines()
        if not ln.lstrip().startswith("#")
    )
    _check(f"{EXCLUDED_FROM_UNION} NICHT auf union (Re-Write/Backfill)",
           not exit_shadow_union)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print(f"Alle {len(UNION_FILES) + 2} Gitattributes-Union-Checks bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
