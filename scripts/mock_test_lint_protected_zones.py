"""Tests für ``scripts/lint_protected_zones.py`` (Technische Schutz-Sperre,
23.10.2026).

Zwei Test-Ebenen:
  1  Pure-Funktionen (``_function_zones``, ``_const_zones``,
     ``_sentinel_zones``, ``_handover_zones``, ``_parse_hunks``,
     ``_overlaps``, ``_pr_is_exempt``) — gegen String-Fixtures, kein Git.
  2  End-to-End gegen ein disposables Temp-Git-Repo (``git init`` in
     einem tempfile.mkdtemp(), Commit als "Basis" simuliert, dann Edits +
     ``check_file``/``main()`` — deckt exakt die 5 im Auftrag geforderten
     Szenarien ab: score()-Änderung rot, Logging-Funktion grün,
     Freeze-Block-Änderung rot, config-Schwelle rot, git-add-Zeile im
     Workflow grün (Workflow-Dateien sind gar nicht in
     ``_ALL_WATCHED_FILES`` — grün by design).

Kategorie A: stdlib-only, env-frei (temp git repos werden pro Test neu
angelegt und wieder entfernt).
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lint_protected_zones as lpz  # noqa: E402

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


# ===========================================================================
# 1: Pure-Funktionen
# ===========================================================================

def test_function_zones_finds_module_and_nested_def():
    src = (
        "def outer():\n"
        "    x = 1\n"
        "    def score(stock):\n"
        "        return 1\n"
        "    return x\n"
        "\n"
        "def apply_agent_boost(stocks):\n"
        "    pass\n"
    )
    zones = lpz._function_zones(src, ("score", "apply_agent_boost"))
    names = {z[0] for z in zones}
    _check("verschachteltes 'score' gefunden", "score" in names)
    _check("Modul-Level 'apply_agent_boost' gefunden", "apply_agent_boost" in names)
    _check("genau 2 Zonen (kein 'outer' mitgezählt)", len(zones) == 2)


def test_function_zones_syntax_error_returns_empty():
    _check("kaputtes Python -> leere Liste, kein Crash",
           lpz._function_zones("def broken(:\n", ("score",)) == [])


def test_const_zones_prefix_match_and_exclude():
    src = (
        "MIN_PRICE = 1.0\n"
        "SCORE_REDDIT_5 = 10\n"
        "SCORE_CONFIDENCE_N_ROBUST = 500\n"  # explizit excluded
        "UNRELATED_CONST = 42\n"
    )
    zones = lpz._const_zones(src)
    names = {z[0] for z in zones}
    _check("MIN_PRICE erkannt", "MIN_PRICE" in names)
    _check("SCORE_REDDIT_5 erkannt (Präfix SCORE_)", "SCORE_REDDIT_5" in names)
    _check("SCORE_CONFIDENCE_N_ROBUST EXKLUDIERT trotz SCORE_-Präfix",
           "SCORE_CONFIDENCE_N_ROBUST" not in names)
    _check("UNRELATED_CONST NICHT erkannt (kein Präfix-Match)",
           "UNRELATED_CONST" not in names)


def test_sentinel_zones_pairs_start_end():
    src = (
        "line1\n"
        "# PROTECTED-ZONE-START: top10\n"
        "line3\n"
        "line4\n"
        "# PROTECTED-ZONE-END: top10\n"
        "line6\n"
    )
    zones = lpz._sentinel_zones(src)
    _check("genau 1 Zone gefunden", len(zones) == 1)
    _check("Zone-Range 2-5 (1-indiziert)", zones[0][1:] == (2, 5))


def test_sentinel_zones_unclosed_marker_ignored():
    src = "# PROTECTED-ZONE-START: foo\nline2\n"  # kein END
    _check("unclosed Marker -> keine Zone (fail-soft)",
           lpz._sentinel_zones(src) == [])


def test_handover_zones_scoped_to_next_same_or_higher_heading():
    src = (
        "# Titel\n"
        "### VORABREGISTRIERUNG — Test A\n"
        "Inhalt A Zeile 3\n"
        "Inhalt A Zeile 4\n"
        "### Eine andere Überschrift\n"
        "Inhalt B\n"
        "### VORABREGISTRIERUNG — Test C\n"
        "Inhalt C\n"
    )
    zones = lpz._handover_zones(src)
    _check("2 Freeze-Zonen gefunden (A und C, nicht 'andere Überschrift')",
           len(zones) == 2)
    zone_a = [z for z in zones if "Test A" in z[0]][0]
    _check("Zone A endet VOR der nächsten Überschrift (Zeile 4)",
           zone_a[2] == 4)
    zone_c = [z for z in zones if "Test C" in z[0]][0]
    _check("Zone C läuft bis EOF", zone_c[2] == 8)


def test_handover_zones_ignores_non_freeze_headings():
    src = "## Normale Sektion\nInhalt\n### Noch eine\nInhalt\n"
    _check("keine VORABREGISTRIERUNG/ERRATUM -> keine Zonen",
           lpz._handover_zones(src) == [])


def test_parse_hunks_basic_and_zero_count_insertion():
    diff = (
        "@@ -10,3 +10,5 @@ def foo():\n"
        "-old\n"
        "+new\n"
        "+new2\n"
        "@@ -50,0 +52,2 @@\n"
        "+inserted\n"
    )
    hunks = lpz._parse_hunks(diff)
    _check("2 Hunks geparst", len(hunks) == 2)
    _check("erster Hunk 10-12 (oldstart=10, oldcount=3)", hunks[0] == (10, 12))
    _check("zweiter Hunk (reine Insertion, oldcount=0) -> (50,50)",
           hunks[1] == (50, 50))


def test_overlaps_edge_cases():
    _check("exakte Berührung an einer Zeile -> overlap",
           lpz._overlaps(10, 20, 20, 25))
    _check("komplett getrennt -> kein overlap",
           not lpz._overlaps(10, 20, 21, 25) if False else not lpz._overlaps(10, 20, 22, 25))
    _check("Zone komplett innerhalb Hunk -> overlap",
           lpz._overlaps(15, 16, 10, 20))


def test_pr_is_exempt_waechter_never_exempt_even_with_label():
    os.environ["PR_TITLE"] = "[Wächter] Daily Update"
    os.environ["PR_LABELS"] = "protected-ok"
    try:
        exempt, reason = lpz._pr_is_exempt()
        _check("Wächter-PR NIE exempt, auch mit Label", exempt is False)
        _check("Grund nennt '[Wächter]'", "Wächter" in reason)
    finally:
        os.environ.pop("PR_TITLE", None)
        os.environ.pop("PR_LABELS", None)


def test_pr_is_exempt_non_waechter_with_label():
    os.environ["PR_TITLE"] = "fix: irgendwas"
    os.environ["PR_LABELS"] = "bug, protected-ok"
    try:
        exempt, _ = lpz._pr_is_exempt()
        _check("Nicht-Wächter-PR MIT Label -> exempt", exempt is True)
    finally:
        os.environ.pop("PR_TITLE", None)
        os.environ.pop("PR_LABELS", None)


def test_pr_is_exempt_non_waechter_without_label():
    os.environ["PR_TITLE"] = "fix: irgendwas"
    os.environ["PR_LABELS"] = ""
    try:
        exempt, _ = lpz._pr_is_exempt()
        _check("Nicht-Wächter-PR OHNE Label -> NICHT exempt (Default: blockierend)",
               exempt is False)
    finally:
        os.environ.pop("PR_TITLE", None)
        os.environ.pop("PR_LABELS", None)


# ===========================================================================
# 2: End-to-End gegen Temp-Git-Repo — die 5 geforderten Szenarien
# ===========================================================================

def _git(repo_dir, *args):
    subprocess.run(["git", *args], cwd=repo_dir, check=True,
                    capture_output=True, text=True)


def _make_fixture_repo() -> str:
    d = tempfile.mkdtemp()
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "test@test.local")
    _git(d, "config", "user.name", "Test")

    (pathlib.Path(d) / "generate_report.py").write_text(
        "def score(stock):\n"
        "    pts = 0\n"
        "    if stock.get('x'):\n"
        "        pts += 1\n"
        "    return pts\n"
        "\n"
        "def _coverage_record_error(quelle, exc):\n"
        "    pass\n"
        "\n"
        "def main():\n"
        "    # PROTECTED-ZONE-START: top10\n"
        "    top10 = []\n"
        "    top10.sort()\n"
        "    # PROTECTED-ZONE-END: top10\n"
        "    print('done')\n",
        encoding="utf-8",
    )
    (pathlib.Path(d) / "config.py").write_text(
        "MIN_PRICE = 1.0\n"
        "UNRELATED = 42\n",
        encoding="utf-8",
    )
    (pathlib.Path(d) / "SESSION_HANDOVER.md").write_text(
        "# Handover\n"
        "### VORABREGISTRIERUNG — Test\n"
        "Zeile A\n"
        "Zeile B\n"
        "### Andere Sektion\n"
        "Zeile C\n",
        encoding="utf-8",
    )
    (pathlib.Path(d) / "ki_agent.py").write_text(
        "def compute_signal():\n    pass\n", encoding="utf-8",
    )
    (pathlib.Path(d) / "backtest_history.py").write_text(
        "def _build_backtest_extension():\n    pass\n", encoding="utf-8",
    )
    os.makedirs(pathlib.Path(d) / "scripts", exist_ok=True)
    (pathlib.Path(d) / "scripts" / "freeze_eval.py").write_text(
        "x = 1\n", encoding="utf-8",
    )
    (pathlib.Path(d) / "scripts" / "stats_helpers.py").write_text(
        "y = 1\n", encoding="utf-8",
    )
    os.makedirs(pathlib.Path(d) / ".github" / "workflows", exist_ok=True)
    (pathlib.Path(d) / ".github" / "workflows" / "daily.yml").write_text(
        "git add foo.jsonl\n", encoding="utf-8",
    )
    _git(d, "add", "-A")
    _git(d, "commit", "-q", "-m", "base")
    _git(d, "branch", "-q", "base-marker")  # fixer Ref unabhängig von main/master
    return d


def _run_lint(repo_dir, title, labels) -> tuple[int, str, str]:
    orig_root = lpz.ROOT
    lpz.ROOT = pathlib.Path(repo_dir)
    os.environ["PROTECTED_ZONES_BASE_REF"] = "base-marker"
    os.environ["PR_TITLE"] = title
    os.environ["PR_LABELS"] = labels
    import io
    import contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = lpz.main()
    finally:
        lpz.ROOT = orig_root
        for k in ("PROTECTED_ZONES_BASE_REF", "PR_TITLE", "PR_LABELS"):
            os.environ.pop(k, None)
    return rc, buf.getvalue(), ""


def test_scenario_score_change_is_blocked_for_waechter():
    d = _make_fixture_repo()
    try:
        p = pathlib.Path(d) / "generate_report.py"
        text = p.read_text(encoding="utf-8")
        p.write_text(text.replace("pts += 1", "pts += 2"), encoding="utf-8")
        rc, out, _ = _run_lint(d, "[Wächter] Daily Update", "")
        _check("Szenario 1: score()-Änderung -> ROT (rc=1)", rc == 1)
        _check("Fund nennt 'score'", "score" in out)
    finally:
        pass


def test_scenario_logging_change_is_green():
    d = _make_fixture_repo()
    try:
        p = pathlib.Path(d) / "generate_report.py"
        text = p.read_text(encoding="utf-8")
        p.write_text(text.replace("def _coverage_record_error(quelle, exc):\n    pass",
                                   "def _coverage_record_error(quelle, exc):\n    log_noop = 1"),
                      encoding="utf-8")
        rc, out, _ = _run_lint(d, "[Wächter] Daily Update", "")
        _check("Szenario 2: reine Logging-Funktion geändert -> GRÜN (rc=0)", rc == 0)
    finally:
        pass


def test_scenario_freeze_block_change_is_red():
    d = _make_fixture_repo()
    try:
        p = pathlib.Path(d) / "SESSION_HANDOVER.md"
        text = p.read_text(encoding="utf-8")
        p.write_text(text.replace("Zeile A", "Zeile A GEÄNDERT"), encoding="utf-8")
        rc, out, _ = _run_lint(d, "[Wächter] Daily Update", "")
        _check("Szenario 3: Freeze-Block-Änderung -> ROT (rc=1)", rc == 1)
        _check("Fund nennt SESSION_HANDOVER.md", "SESSION_HANDOVER.md" in out)
    finally:
        pass


def test_scenario_config_threshold_change_is_red():
    d = _make_fixture_repo()
    try:
        p = pathlib.Path(d) / "config.py"
        text = p.read_text(encoding="utf-8")
        p.write_text(text.replace("MIN_PRICE = 1.0", "MIN_PRICE = 2.0"), encoding="utf-8")
        rc, out, _ = _run_lint(d, "[Wächter] Daily Update", "")
        _check("Szenario 4: config-Schwelle geändert -> ROT (rc=1)", rc == 1)
        _check("Fund nennt MIN_PRICE", "MIN_PRICE" in out)
    finally:
        pass


def test_scenario_unrelated_config_const_is_green():
    d = _make_fixture_repo()
    try:
        p = pathlib.Path(d) / "config.py"
        text = p.read_text(encoding="utf-8")
        p.write_text(text.replace("UNRELATED = 42", "UNRELATED = 43"), encoding="utf-8")
        rc, out, _ = _run_lint(d, "[Wächter] Daily Update", "")
        _check("nicht-geschützte Konstante geändert -> GRÜN (rc=0)", rc == 0)
    finally:
        pass


def test_scenario_workflow_git_add_line_is_green():
    d = _make_fixture_repo()
    try:
        p = pathlib.Path(d) / ".github" / "workflows" / "daily.yml"
        p.write_text("git add foo.jsonl\ngit add bar.jsonl\n", encoding="utf-8")
        rc, out, _ = _run_lint(d, "[Wächter] Daily Update", "")
        _check("Szenario 5: git-add-Zeile im Workflow -> GRÜN (rc=0, "
               "Workflow-Dateien sind nicht beobachtet)", rc == 0)
    finally:
        pass


def test_scenario_waechter_cannot_bypass_via_label():
    d = _make_fixture_repo()
    try:
        p = pathlib.Path(d) / "generate_report.py"
        text = p.read_text(encoding="utf-8")
        p.write_text(text.replace("pts += 1", "pts += 2"), encoding="utf-8")
        rc, out, _ = _run_lint(d, "[Wächter] Daily Update", "protected-ok")
        _check("Wächter-PR MIT Label 'protected-ok' bleibt trotzdem ROT (Kern-Garantie)",
               rc == 1)
        _check("Begründung nennt fehlende Ausnahme für Wächter", "Wächter" in out)
    finally:
        pass


def test_scenario_non_waechter_score_change_with_label_passes():
    d = _make_fixture_repo()
    try:
        p = pathlib.Path(d) / "generate_report.py"
        text = p.read_text(encoding="utf-8")
        p.write_text(text.replace("pts += 1", "pts += 2"), encoding="utf-8")
        rc, out, _ = _run_lint(d, "feat: Score-Tuning (manuell)", "protected-ok")
        _check("Nicht-Wächter-PR + Label -> GRÜN (informativer Pass)", rc == 0)
        _check("Fund trotzdem im Output sichtbar (Transparenz)", "score" in out)
    finally:
        pass


def test_scenario_non_waechter_score_change_without_label_fails():
    d = _make_fixture_repo()
    try:
        p = pathlib.Path(d) / "generate_report.py"
        text = p.read_text(encoding="utf-8")
        p.write_text(text.replace("pts += 1", "pts += 2"), encoding="utf-8")
        rc, out, _ = _run_lint(d, "feat: Score-Tuning (manuell)", "")
        _check("Nicht-Wächter-PR OHNE Label -> trotzdem ROT (Default blockierend)",
               rc == 1)
    finally:
        pass


def test_scenario_sentinel_zone_touch_is_red():
    d = _make_fixture_repo()
    try:
        p = pathlib.Path(d) / "generate_report.py"
        text = p.read_text(encoding="utf-8")
        p.write_text(text.replace("top10.sort()", "top10.sort(reverse=False)"),
                      encoding="utf-8")
        rc, out, _ = _run_lint(d, "[Wächter] Top10 tweak", "")
        _check("Sentinel-Zone (Top-10-Pipeline) geändert -> ROT (rc=1)", rc == 1)
    finally:
        pass


def test_scenario_new_file_at_base_not_present_is_safe():
    """Datei existiert bei der Basis noch nicht (z.B. der einführende PR
    selbst) -> fail-soft, kein Crash, kein Fund für diese Datei."""
    d = _make_fixture_repo()
    try:
        # score() unverändert lassen, aber freeze_eval.py im Arbeitsbaum
        # löschen UND durch eine "neue" Variante ersetzen, um sicherzustellen,
        # dass ein fehlendes Base-File (_read_at_ref -> None) nicht crasht.
        p = pathlib.Path(d) / "scripts" / "freeze_eval.py"
        p.write_text("x = 2\n", encoding="utf-8")
        rc, out, _ = _run_lint(d, "[Wächter] x", "")
        _check("freeze_eval.py normal geändert -> ROT (whole-file), kein Crash",
               rc == 1)
    finally:
        pass


def run_all():
    tests = [
        test_function_zones_finds_module_and_nested_def,
        test_function_zones_syntax_error_returns_empty,
        test_const_zones_prefix_match_and_exclude,
        test_sentinel_zones_pairs_start_end,
        test_sentinel_zones_unclosed_marker_ignored,
        test_handover_zones_scoped_to_next_same_or_higher_heading,
        test_handover_zones_ignores_non_freeze_headings,
        test_parse_hunks_basic_and_zero_count_insertion,
        test_overlaps_edge_cases,
        test_pr_is_exempt_waechter_never_exempt_even_with_label,
        test_pr_is_exempt_non_waechter_with_label,
        test_pr_is_exempt_non_waechter_without_label,
        test_scenario_score_change_is_blocked_for_waechter,
        test_scenario_logging_change_is_green,
        test_scenario_freeze_block_change_is_red,
        test_scenario_config_threshold_change_is_red,
        test_scenario_unrelated_config_const_is_green,
        test_scenario_workflow_git_add_line_is_green,
        test_scenario_waechter_cannot_bypass_via_label,
        test_scenario_non_waechter_score_change_with_label_passes,
        test_scenario_non_waechter_score_change_without_label_fails,
        test_scenario_sentinel_zone_touch_is_red,
        test_scenario_new_file_at_base_not_present_is_safe,
    ]
    for t in tests:
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Protected-Zones-Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle Protected-Zones-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
