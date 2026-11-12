#!/usr/bin/env python3
"""PreToolUse-Hook: blockt zerstörerische GitHub-/git-Befehle (Easy-Entscheid
nach dem Lösch-Vorfall 12.11.2026, siehe CLAUDE.md „Zerstörerische Befehle“).

Vorfall: an eine Push-Zeile war hinter ``&&`` ein Aufruf angehängt, der das
ganze Repo gelöscht hätte (``gh api -X DELETE repos/<owner>/<repo>``), mit
``2>/dev/null; true`` dahinter. Abgelehnt hat damals nur die Sicherheitsprüfung
des Auto-Modus.

Zweite Schicht neben ``permissions.deny`` in ``.claude/settings.json``: die
Deny-Muster arbeiten auf dem Befehlstext und decken laut Doku keine Pfad-/
``sh -c``-Varianten ab. Dieser Hook prüft die GANZE Befehlszeile (alle
verketteten Teile, auch Text in Anführungszeichen) mit regulären Ausdrücken,
ohne Groß-/Kleinschreibung.

Vertrag (Claude-Code-Doku, Hooks): JSON auf stdin (``tool_name``,
``tool_input``); Exit 2 + Grund auf stderr = Aufruf blockiert. Exit 0 = normaler
Ablauf (Deny-Regeln greifen weiterhin). Interner Fehler: blockt, wenn die
Eingabe eines der Gefahrenwörter enthält, sonst Exit 0.

Erlaubt bleibt bewusst: Dateien per Commit löschen (``git rm``), Lesen per
``gh api`` (GET), normaler Push und ``--force-with-lease`` auf Feature-Branches.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

_I = re.IGNORECASE

# Teilbefehle trennen (für Regeln, die „im selben Teilbefehl“ gelten sollen).
_SPLIT = re.compile(r"&&|\|\||;|\||\n|\$\(|`")

# Regeln auf der GANZEN Zeile (Reihenfolge = Meldungs-Priorität).
_LINE_RULES = [
    (re.compile(r"\bgh\s+repo\s+(delete|edit|rename|archive|unarchive)\b", _I),
     "gh repo delete/edit/rename/archive"),
    (re.compile(r"\bgh\s+secret\s+(delete|remove|set)\b", _I), "gh secret delete/remove/set"),
    (re.compile(r"\bgh\s+variable\s+(delete|set)\b", _I), "gh variable delete/set"),
    (re.compile(r"\bgh\s+workflow\s+disable\b", _I), "gh workflow disable"),
    (re.compile(r"\bgh\s+run\s+delete\b", _I), "gh run delete"),
    (re.compile(r"\bgh\s+ruleset\b(?!\s+(list|view|check)\b)", _I), "gh ruleset (ändernd)"),
    (re.compile(r"\bgh\s+release\s+delete\b", _I), "gh release delete"),
    (re.compile(r"\bgh\s+label\s+delete\b", _I), "gh label delete"),
    (re.compile(r"\bgh\s+cache\s+delete\b", _I), "gh cache delete"),
]

_METHOD_DELETE = re.compile(
    r"(-X\s*=?\s*|--method\s*=?\s*|--request\s*=?\s*|-X)['\"]?DELETE\b", _I)
_METHOD_WRITE = re.compile(
    r"(-X\s*=?\s*|--method\s*=?\s*|--request\s*=?\s*|-X)['\"]?(PUT|PATCH|POST|DELETE)\b", _I)
_FIELD = re.compile(r"(^|\s)(-f|-F|--field|--raw-field|--input)(\s|=)", _I)
_PROTECTED_PATH = re.compile(r"(rulesets|/protection\b|/branches/[^\s]*/protection)", _I)
_GH_API = re.compile(r"\bgh\s+api\b", _I)
_GH_HOST = re.compile(r"api\.github\.com", _I)

_GIT_PUSH = re.compile(r"\bgit\b.*\bpush\b", _I)


def _segments(cmd: str) -> list[str]:
    return [s for s in _SPLIT.split(cmd) if s.strip()]


def _current_branch(cwd: str | None) -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd or None,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _check_push(seg: str, cwd: str | None) -> str | None:
    toks = seg.split()
    try:
        i = next(k for k, t in enumerate(toks) if t.lower() == "push")
    except StopIteration:
        return None
    args = toks[i + 1:]
    opts = [a for a in args if a.startswith("-")]
    refs = [a.strip("'\"") for a in args if not a.startswith("-")]
    low = [o.lower() for o in opts]
    if any(o == "--delete" or o == "-d" for o in low):
        return "git push --delete"
    if any(o == "--mirror" for o in low):
        return "git push --mirror"
    refspecs = refs[1:]                         # erstes Nicht-Option-Argument = Remote
    if any(r.startswith(":") for r in refspecs):
        return "git push :branch (löscht den Ziel-Branch)"
    force = any(o in ("-f", "--force") or o.startswith("--force-with-lease")
                or o.startswith("--force-if-includes") for o in low)
    plus = any(r.startswith("+") for r in refspecs)
    if force or plus:
        def _dest(r):
            r = r.lstrip("+")
            return r.split(":", 1)[1] if ":" in r else r
        dests = [_dest(r) for r in refspecs]
        if any(d in ("main", "refs/heads/main", "master") for d in dests):
            return "git push --force auf main"
        if not refspecs and _current_branch(cwd) in ("main", "master"):
            return "git push --force auf main (aktueller Branch)"
    return None


def check(command: str, cwd: str | None = None) -> str | None:
    """Grund-Text, wenn ``command`` blockiert werden muss, sonst ``None``.
    Pure bis auf den optionalen ``git rev-parse`` für Force-Push ohne Refspec."""
    if not command:
        return None
    for rx, why in _LINE_RULES:
        if rx.search(command):
            return why
    for seg in _segments(command):
        api = _GH_API.search(seg) or (_GH_HOST.search(seg) and re.search(r"\bcurl\b|\bwget\b|\bhttp\b", seg, _I))
        if api and _METHOD_DELETE.search(seg):
            return "API-Aufruf mit Methode DELETE"
        if api and _PROTECTED_PATH.search(seg) and (_METHOD_WRITE.search(seg) or _FIELD.search(seg)):
            return "Änderung an Ruleset/Branch-Schutz per API"
        if _GIT_PUSH.search(seg):
            why = _check_push(seg, cwd)
            if why:
                return why
    return None


# MCP-Werkzeuge: zerstörerische Methoden.
_MCP_DENY = {
    ("mcp__github__actions_run_trigger", "delete_workflow_run_logs"),
}


def check_tool(payload: dict) -> str | None:
    name = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input") or {}
    if name == "Bash":
        return check(str(ti.get("command") or ""), payload.get("cwd"))
    if name.startswith("mcp__"):
        meth = str(ti.get("method") or "")
        if (name, meth) in _MCP_DENY:
            return f"{name} {meth}"
    return None


_DANGER_WORDS = re.compile(r"DELETE|--delete|repo\s+delete|--mirror|--force|rulesets|protection", _I)


def main() -> int:
    raw = sys.stdin.read()
    try:
        why = check_tool(json.loads(raw))
    except Exception:  # noqa: BLE001 — im Zweifel bei Gefahrenwörtern blocken
        why = "Hook-Eingabe nicht prüfbar" if _DANGER_WORDS.search(raw or "") else None
    if why:
        print(f"Blockiert (CLAUDE.md „Zerstörerische Befehle“): {why}. "
              "Solche Schritte macht Easy selbst.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
