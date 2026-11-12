#!/usr/bin/env python3
"""Lint + Trockentest: Sperren gegen zerstörerische Befehle (Easy-Entscheid
nach dem Lösch-Vorfall 12.11.2026, CLAUDE.md „Zerstörerische Befehle“).

Prüft OHNE einen Befehl auszuführen:
  L1  .claude/settings.json enthält die Pflicht-Deny-Einträge (Rückbau fällt auf).
  L2  PreToolUse-Hook ist registriert (Matcher Bash + mcp__github__) und das
      Skript existiert.
  D1  Deny-Muster-Emulation (Doku: jeder Teilbefehl von &&, ||, ;, |, &,
      Zeilenumbruch, $(…) wird einzeln geprüft; ``*`` = beliebiger Text):
      die wörtliche Vorfall-Zeile vom 12.11.2026 20:59:42 wird abgelehnt.
  H1  Hook (block_destructive.check) blockt die Vorfall-Zeile und weitere
      Gefahren-Formen (Schreibweisen, Position, sh -c, Pfad /usr/bin/gh).
  H2  Hook lässt erlaubte Abläufe durch (Feature-Push mit --force-with-lease,
      gh api GET auf rulesets, git rm + commit, gh pr merge, normaler Push).
  H3  Hook-Prozess: Exit 2 + Grund auf stderr für die Vorfall-Zeile, Exit 0
      für erlaubte; kaputte Eingabe mit Gefahrenwort → Exit 2.
  H4  MCP: actions_run_trigger delete_workflow_run_logs blockiert, run_workflow nicht.
"""
from __future__ import annotations

import fnmatch
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))

import block_destructive as bd  # noqa: E402

_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


# Wörtliche Vorfall-Zeile (Sitzungsprotokoll 12.11.2026 20:59:42 UTC).
INCIDENT = ("git diff origin/main --stat && git push -q --force-with-lease && "
            "git rev-parse HEAD && gh api -X DELETE repos/easywebb911/Aktien-Update "
            "2>/dev/null; true")

REQUIRED_DENY = [
    "Bash(gh api *-X DELETE*)", "Bash(gh api *--method DELETE*)", "Bash(gh api *-XDELETE*)",
    "Bash(gh repo delete*)", "Bash(gh repo edit*)", "Bash(gh repo rename*)",
    "Bash(gh repo archive*)", "Bash(gh secret delete*)", "Bash(gh secret remove*)",
    "Bash(gh workflow disable*)", "Bash(gh run delete*)",
    "Bash(gh api *-X PUT*rulesets*)", "Bash(gh api *-X PUT*protection*)",
    "Bash(git push *--delete*)", "Bash(git push * :*)", "Bash(git push *--mirror*)",
    "Bash(git push *--force* main*)", "Bash(git push * +main*)",
]

BLOCK = [
    INCIDENT,
    "gh api --method DELETE repos/x/y",
    "gh api repos/x/y -X delete",
    "gh api -XDELETE repos/x/y/git/refs/heads/feature",
    "sh -c 'gh api -X DELETE repos/x/y'",
    "/usr/bin/gh api --method=DELETE repos/x/y",
    "echo ok; gh repo delete x/y --yes",
    "gh repo edit x/y --visibility private",
    "gh secret delete NTFY_TOPIC",
    "gh workflow disable outcome_path.yml",
    "gh run delete 123",
    "gh api -X PUT repos/x/y/rulesets/1 -f enforcement=disabled",
    "gh api repos/x/y/branches/main/protection -X DELETE",
    "gh api repos/x/y/rulesets/1 --method PATCH --input r.json",
    "git push origin --delete feature",
    "git push origin :feature",
    "git push --mirror origin",
    "git push --force origin main",
    "git push -f origin HEAD:main",
    "git push origin +main",
    "git -C . push --force-with-lease origin main",
    "curl -X DELETE https://api.github.com/repos/x/y",
]

ALLOW = [
    "git push -u origin claude/feature-x1",
    "git push -q --force-with-lease origin claude/feature-x1",
    "gh api repos/x/y/rulesets/1 --jq .rules",
    "gh api repos/x/y/branches/main --jq .protected",
    "git rm scripts/old.py && git commit -m 'cleanup'",
    "gh pr merge 12 --merge",
    "gh run list --workflow daily.yml",
    "gh workflow run settled_close_measure.yml --ref main",
    "python scripts/mock_test_x.py",
]


def _emulate_deny(command: str, patterns: list[str]) -> str | None:
    """Doku-Regel nachgebildet: Teilbefehle trennen, jeden gegen Bash(...)-
    Muster prüfen (``*`` beliebig, ganzer Text). Konservativ: nur Trennzeichen,
    keine Quote-Analyse."""
    parts = re.split(r"&&|\|\||\|&|;|\||&|\n|\$\(|\)", command)
    for p in parts:
        p = re.sub(r"^\s*(\w+=\S*\s+)*", "", p).strip()
        if not p:
            continue
        for pat in patterns:
            m = re.fullmatch(r"Bash\((.*)\)", pat)
            if m and fnmatch.fnmatchcase(p, m.group(1)):
                return pat
    return None


def test_settings():
    s = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    deny = (s.get("permissions") or {}).get("deny") or []
    missing = [d for d in REQUIRED_DENY if d not in deny]
    check("L1 Pflicht-Deny-Einträge vorhanden", not missing, missing)
    pre = (s.get("hooks") or {}).get("PreToolUse") or []
    cmds = [(h.get("matcher", ""), x.get("command", "")) for h in pre for x in h.get("hooks", [])]
    ok = any("Bash" in m and "mcp__github__" in m and "block_destructive.py" in c for m, c in cmds)
    check("L2 PreToolUse-Hook registriert", ok, cmds)
    check("L2 Hook-Skript vorhanden", (ROOT / ".claude/hooks/block_destructive.py").exists())
    hit = _emulate_deny(INCIDENT, deny)
    check("D1 Vorfall-Zeile 12.11. von Deny-Mustern abgelehnt", hit is not None, hit)
    for c in ALLOW:
        check(f"D1 erlaubt bleibt: {c[:50]}", _emulate_deny(c, deny) is None, _emulate_deny(c, deny))


def test_hook():
    for c in BLOCK:
        check(f"H1 blockt: {c[:60]}", bd.check(c, str(ROOT)) is not None)
    for c in ALLOW:
        check(f"H2 erlaubt: {c[:60]}", bd.check(c, str(ROOT)) is None, bd.check(c, str(ROOT)))
    script = ROOT / ".claude/hooks/block_destructive.py"

    def run(payload_text):
        return subprocess.run([sys.executable, str(script)], input=payload_text,
                              capture_output=True, text=True, timeout=30)
    r = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": INCIDENT}, "cwd": str(ROOT)}))
    check("H3 Vorfall-Zeile: Exit 2 + Grund", r.returncode == 2 and "Blockiert" in r.stderr, (r.returncode, r.stderr))
    r = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": ALLOW[0]}, "cwd": str(ROOT)}))
    check("H3 erlaubt: Exit 0", r.returncode == 0, (r.returncode, r.stderr))
    r = run("{kaputt -X DELETE")
    check("H3 kaputte Eingabe mit Gefahrenwort → Exit 2", r.returncode == 2, r.returncode)
    r = run("{kaputt")
    check("H3 kaputte Eingabe ohne Gefahrenwort → Exit 0", r.returncode == 0, r.returncode)


def test_mcp():
    check("H4 MCP delete_workflow_run_logs blockiert", bd.check_tool(
        {"tool_name": "mcp__github__actions_run_trigger",
         "tool_input": {"method": "delete_workflow_run_logs", "run_id": 1}}) is not None)
    check("H4 MCP run_workflow erlaubt", bd.check_tool(
        {"tool_name": "mcp__github__actions_run_trigger",
         "tool_input": {"method": "run_workflow"}}) is None)


def main() -> int:
    for t in (test_settings, test_hook, test_mcp):
        print(t.__name__)
        t()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle destructive_guard-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
