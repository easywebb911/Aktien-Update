"""Lint: unescapte ``{...}``-Pattern in f-Strings von generate_report.py.

Hintergrund: Die HTML/JS-Sektion in ``generate_report.py`` ist ein
Python-f-String. Python interpretiert jedes ``{name}`` als Variable-
Lookup. JS-Code, JS-Objektliterale, JS-Destructuring und JS-Kommentare
nutzen geschweifte Klammern intensiv — wenn sie nicht mit ``{{`` und
``}}`` doppelt-escaped sind, crashed der Daily-Run zur Render-Zeit mit
``NameError: name 'xyz' is not defined``.

Crash-Beispiele aus der Praxis:
- PR #135: ``{quote_proxy_url_js}`` legitim, aber Context-Key fehlte
  → ``NameError: 'quote_proxy_url_js' is not defined`` (Fix: PR #137).
- PR #135 (zweite Welle): ``// ticker → {intervalId, scope, indicator}``
  in einem JS-Kommentar → ``NameError: 'intervalId' is not defined``
  (Fix: dieser PR).

Der bestehende Linter ``scripts/lint_chat_template.py`` deckt nur die
Backtick-Balance im Chat-Template ab, nicht die f-String-Escape-Falle.

Strategie:
1. AST-Parse von ``generate_report.py`` → sammle alle Top-Level-Namen
   (Imports, Konstanten, Funktionen, Klassen) plus ``config.py``-Namen.
2. Pro f-String-Funktion (``generate_html_v1``, weitere bei Bedarf):
   sammle lokale Namen aus Body-Assigns + Argumenten.
3. Scan f-String-Bereich line-by-line: jedes nicht-escaped ``{name}``
   wird gegen den kombinierten Scope geprüft. Wenn ``name`` nicht
   bekannt ist → Bug.

Exit-Code 0 = sauber, 1 = mindestens ein Bug. Bug-Liste wird zur
schnellen Diagnose in stdout geloggt mit Zeilennummer + Pattern +
Code-Kontext.

Workflow-Integration: ``.github/workflows/daily-squeeze-report.yml``
ruft das Skript vor ``Generate squeeze report`` auf.
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys
from typing import Iterable

ROOT = pathlib.Path(__file__).resolve().parent.parent


# Funktionen mit großem f-String, die wir scannen wollen. Jede Tuple-
# Form: (function_name, f_string_start_pattern, f_string_end_pattern).
_F_STRING_TARGETS = (
    ("generate_html_v1", 'return f"""', '</html>"""'),
)


def _collect_module_names(src: str, also_from: Iterable[str] = ()) -> set[str]:
    """Sammelt alle Top-Level-Namen (Imports, Konstanten, Funktionen)."""
    tree = ast.parse(src)
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    # Zusätzliche Module-Sources (z.B. config.py — wir kennen den Inhalt
    # nicht über `from config import *`, ergänzen daher manuell).
    for extra_path in also_from:
        try:
            extra_src = pathlib.Path(extra_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        extra_tree = ast.parse(extra_src)
        for node in extra_tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
    return names


def _collect_function_locals(func: ast.FunctionDef) -> set[str]:
    names = {arg.arg for arg in func.args.args}
    for n in ast.walk(func):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                for nn in ast.walk(t):
                    if isinstance(nn, ast.Name):
                        names.add(nn.id)
        elif isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
            names.add(n.target.id)
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            names.add(n.target.id)
        elif isinstance(n, ast.For) and isinstance(n.target, ast.Name):
            names.add(n.target.id)
        # Comprehension-Bindings
        elif isinstance(n, (ast.ListComp, ast.SetComp, ast.GeneratorExp,
                            ast.DictComp)):
            for gen in n.generators:
                if isinstance(gen.target, ast.Name):
                    names.add(gen.target.id)
    return names


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


_VAR_HEAD_RE  = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)")
_FIELD_RE     = re.compile(r"\{([^{}]*)\}")
_PLACEHOLDER  = {"\x00": "{{", "\x01": "}}"}   # nur zur Diagnose


def _scan_fstring(lines: list[str], start_idx: int, end_idx: int,
                  scope: set[str]) -> list[tuple[int, str, str, str]]:
    """Liefert Liste (lineno, var, content, line)."""
    bugs: list[tuple[int, str, str, str]] = []
    for ln in range(start_idx, end_idx):
        line = lines[ln]
        # Escapte {{ und }} mit NUL/SOH ersetzen, damit der Regex nur
        # die einzelnen { ... } findet.
        marked = line.replace("{{", "\x00").replace("}}", "\x01")
        for m in _FIELD_RE.finditer(marked):
            content = m.group(1).strip()
            if not content:
                # Leeres {} — Format-Auto-Index; in unseren f-Strings
                # nicht erwartet, aber kein NameError-Risiko.
                continue
            hv = _VAR_HEAD_RE.match(content)
            if not hv:
                # Pure Format-Spec wie ":.2f" oder Lambda; nicht
                # NameError-relevant.
                continue
            var = hv.group(1)
            if var in scope:
                continue
            bugs.append((ln + 1, var, content[:80], line.rstrip()[:160]))
    return bugs


def main() -> int:
    src_path = ROOT / "generate_report.py"
    src = src_path.read_text(encoding="utf-8")
    lines = src.splitlines()
    tree = ast.parse(src)

    builtins_names = set(dir(__builtins__)) | {"True", "False", "None"}
    module_names = _collect_module_names(src, also_from=[str(ROOT / "config.py")])

    bugs_total: list[tuple[str, int, str, str, str]] = []  # +func-name

    for func_name, fs_start_pat, fs_end_pat in _F_STRING_TARGETS:
        func = _find_function(tree, func_name)
        if not func:
            print(f"WARN: Funktion {func_name} nicht gefunden — überspringe",
                  file=sys.stderr)
            continue
        local_names = _collect_function_locals(func)
        scope = builtins_names | module_names | local_names

        # f-String-Bereich finden
        fs_start = None
        for i in range(func.lineno - 1, len(lines)):
            if fs_start_pat in lines[i]:
                fs_start = i
                break
        if fs_start is None:
            print(f"WARN: f-string-Start '{fs_start_pat}' in {func_name} nicht gefunden",
                  file=sys.stderr)
            continue
        fs_end = None
        for i in range(fs_start + 1, len(lines)):
            if lines[i].rstrip() == fs_end_pat:
                fs_end = i
                break
        if fs_end is None:
            print(f"WARN: f-string-Ende '{fs_end_pat}' in {func_name} nicht gefunden",
                  file=sys.stderr)
            continue

        bugs = _scan_fstring(lines, fs_start, fs_end, scope)
        for ln, var, content, line in bugs:
            bugs_total.append((func_name, ln, var, content, line))

    if not bugs_total:
        print(f"OK: Keine unescapten {{...}}-Pattern in f-Strings gefunden "
              f"({len(_F_STRING_TARGETS)} Funktionen geprüft).")
        return 0

    print(f"FEHLER: {len(bugs_total)} unescapte {{...}}-Pattern in f-Strings:",
          file=sys.stderr)
    for func_name, ln, var, content, line in bugs_total:
        print(f"  {func_name}:{ln}  Variable {var!r} nicht im Scope",
              file=sys.stderr)
        print(f"    Pattern: {{ {content} }}", file=sys.stderr)
        print(f"    Code:    {line}", file=sys.stderr)
    print("\nFix: nicht-Python {...}-Pattern als {{...}} doppelt escapen, "
          "oder die Python-Variable in den Scope bringen.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
