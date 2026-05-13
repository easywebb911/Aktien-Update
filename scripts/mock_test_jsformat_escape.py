"""Mock-Tests für scripts/lint_jsformat_escape.py.

Hintergrund: PR #138 ergänzt einen AST-basierten Linter, der unescapte
``{...}``-Pattern in den f-Strings von ``generate_report.py`` findet.
Dieser Test verifiziert, dass der Linter:

  1. Auf dem aktuellen (gepatchten) Repo-State exit 0 liefert
  2. Einen synthetisch eingefügten Bug-Pattern erkennt + exit 1
  3. Escaping mit doppelten Klammern als korrekt akzeptiert
  4. Legitime Python-Format-Variablen (im Scope) korrekt durchlässt
  5. format-Spec-Felder wie ``{var:.2f}`` ohne False-Positives akzeptiert
  6. Workflow integriert den Lint-Step direkt vor dem Generate-Step

Ausführung: ``python scripts/mock_test_jsformat_escape.py``.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lint_jsformat_escape as lint  # noqa: E402


# === 1 — Aktueller Repo-State ist sauber ===================================

def test_real_repo_passes_lint():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "lint_jsformat_escape.py")],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        f"Linter findet Bugs auf aktuellem main:\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}")


# === 2 — Helper-Funktionen direkt testen ===================================

def test_scan_finds_unescaped_pattern():
    """Synthetisches Snippet mit dem PR-#138-Bug-Pattern."""
    lines = [
        'def fake():',
        '    return f"""<html>',
        '    const x = new Map();   // ticker → {intervalId, scope}',
        '    </html>"""',
    ]
    scope = {"x", "Map", "fake"}  # `intervalId` ist nicht drin
    bugs = lint._scan_fstring(lines, 1, 3, scope)
    assert len(bugs) == 1, bugs
    ln, var, content, line = bugs[0]
    assert var == "intervalId", var


def test_scan_accepts_escaped_pattern():
    """Doppelte Klammern werden korrekt erkannt und ignoriert."""
    lines = [
        'def fake():',
        '    return f"""<html>',
        '    const x = new Map();   // ticker → {{intervalId, scope}}',
        '    </html>"""',
    ]
    scope = {"x", "Map", "fake"}
    bugs = lint._scan_fstring(lines, 1, 3, scope)
    assert bugs == [], bugs


def test_scan_accepts_in_scope_variable():
    """Eine im Scope verfügbare Variable wirft keinen Bug."""
    lines = [
        '    return f"""<div>{report_date}</div>"""',
    ]
    scope = {"report_date"}
    bugs = lint._scan_fstring(lines, 0, 1, scope)
    assert bugs == [], bugs


def test_scan_accepts_format_spec():
    """Format-Specs wie {var:.2f} dürfen kein Bug sein, solange var im Scope."""
    lines = [
        '    return f"""<p>{MAX_MARKET_CAP_B:.0f} Mrd. USD</p>"""',
    ]
    scope = {"MAX_MARKET_CAP_B"}
    bugs = lint._scan_fstring(lines, 0, 1, scope)
    assert bugs == [], bugs


def test_scan_flags_format_spec_with_unknown_var():
    """Format-Spec mit unbekannter Variable wird trotzdem erkannt."""
    lines = [
        '    return f"""<p>{undefined_var:.0f}</p>"""',
    ]
    scope = {"some_other_var"}
    bugs = lint._scan_fstring(lines, 0, 1, scope)
    assert len(bugs) == 1, bugs
    assert bugs[0][1] == "undefined_var", bugs[0]


def test_scan_ignores_empty_braces():
    """``{}`` als auto-index Placeholder ist syntaktisch valide — kein Crash."""
    lines = [
        '    return f"""<div>{}</div>"""',
    ]
    bugs = lint._scan_fstring(lines, 0, 1, set())
    assert bugs == [], bugs


# === 3 — Workflow-Integration ==============================================

def test_workflow_has_lint_step():
    yml = (ROOT / ".github" / "workflows" / "daily-squeeze-report.yml"
           ).read_text(encoding="utf-8")
    assert "lint_jsformat_escape.py" in yml, (
        "Lint-Step lint_jsformat_escape.py fehlt im daily-squeeze-report.yml")
    # Reihenfolge: nach lint_chat_template, vor Generate squeeze report
    idx_chat = yml.find("lint_chat_template.py")
    idx_js   = yml.find("lint_jsformat_escape.py")
    idx_gen  = yml.find("Generate squeeze report")
    assert idx_chat < idx_js < idx_gen, (
        f"Workflow-Reihenfolge falsch: chat-lint@{idx_chat} "
        f"js-lint@{idx_js} generate@{idx_gen}")


# === 4 — _collect_module_names sammelt config.py-Konstanten ================

def test_module_names_include_config_constants():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    names = lint._collect_module_names(
        src, also_from=[str(ROOT / "config.py")])
    # MAX_MARKET_CAP_B ist in config.py definiert und im f-String referenziert
    assert "MAX_MARKET_CAP_B" in names, (
        "config.py-Konstanten werden nicht in den Scope übernommen — "
        "ergibt False-Positives bei legitimem Code")


# === Runner =================================================================

def main() -> None:
    tests = [
        ("Aktueller Repo-State ist Lint-sauber",         test_real_repo_passes_lint),
        ("Helper findet unescapten Bug-Pattern",         test_scan_finds_unescaped_pattern),
        ("Helper akzeptiert {{ }}-Escaping",             test_scan_accepts_escaped_pattern),
        ("Helper akzeptiert Variable im Scope",          test_scan_accepts_in_scope_variable),
        ("Helper akzeptiert Format-Spec mit known var",  test_scan_accepts_format_spec),
        ("Helper flaggt unknown var mit Format-Spec",    test_scan_flags_format_spec_with_unknown_var),
        ("Helper ignoriert leere {} Auto-Index",         test_scan_ignores_empty_braces),
        ("Workflow integriert Lint-Step nach chat-lint", test_workflow_has_lint_step),
        ("config.py-Konstanten im Scope",                test_module_names_include_config_constants),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {name}\n      {exc}")
        except Exception as exc:
            failed += 1
            print(f"  ✗ {name}\n      Unexpected: {type(exc).__name__}: {exc}")
    print()
    if failed:
        print(f"{failed} Test(s) fehlgeschlagen.")
        sys.exit(1)
    print(f"{len(tests)} Tests bestanden.")
    sys.exit(0)


if __name__ == "__main__":
    main()
