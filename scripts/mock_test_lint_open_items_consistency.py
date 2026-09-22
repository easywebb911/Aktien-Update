"""Mock-Tests für ``scripts/lint_open_items_consistency.py`` (22.09.2026).

Treibt die ECHTEN Kern-Funktionen des Linters (``_parse_items``,
``validate_item_structure``, ``check_consistency``, ``main``) -- nicht
eine Nachbildung. Die Kern-Logik ist pure (keine Git-/Dateisystem-Calls),
deshalb laufen die Pflicht-Szenarien (a)/(b)/(c) direkt gegen feste,
deterministische Fixture-Listen (keine echten Git-Commits nötig).

Pflicht-Szenarien laut Aufgabenstellung:
  (a) Datei kann korrekt geparst werden
  (b) Konsistenz-Check schlägt an, wenn ein Item zwischen zwei Versionen
      ERSATZLOS verschwindet (nicht auf 'erledigt' gesetzt)
  (c) Konsistenz-Check schlägt NICHT an, wenn ein Item korrekt auf
      'erledigt' gesetzt wurde (bleibt in der Liste ODER wird danach
      entfernt -- beide Pfade sind laut Spec erlaubt)

Zusätzlich (Robustheit):
  (d) Struktur-Validierung fängt fehlende Pflichtfelder / ungültigen Status
  (e) Item bleibt unverändert (kein Status-Wechsel) -> kein Fund
  (f) main() end-to-end gegen echte Git-Refs (Tempdir mit eigenem Git-Repo,
      zwei Commits) -- bestätigt die Git-Show-Anbindung selbst, nicht nur
      die pure Kernlogik
  (g) main() ist fail-soft, wenn die Basis-Ref nicht auflösbar ist (Fall:
      genau der PR, der die Datei neu einführt)
  (h) main() findet Struktur-Fehler in der NEUEN Version selbst (harter Fail,
      kein fail-soft) -- unabhängig vom Git-Vergleich
  (i) Regression: das echte, aktuell committete ``open_items.json`` im Repo
      ist strukturell gültig (Smoke-Test, kein Git-Diff -- nur Parse+Validate)
  (j) Beide Workflow-Wirings (pr-checks.yml PR-Pfad +
      open_items_main_push_check.yml main-Push-Pfad) sind strukturell
      korrekt verdrahtet -- Guardian-Finding 22.09.2026: pr-checks.yml
      triggert NUR auf ``pull_request`` und deckt damit NICHT den
      "Gute Nacht"-Direct-main-Commit-Pfad (die eine dokumentierte
      Ausnahme vom PR-only-Workflow) ab. Der zweite Workflow schließt
      genau diese Lücke (push-Trigger, ``paths: [open_items.json]``,
      Vergleichsbasis ``github.event.before``).

Kategorie A: reine stdlib (json/pathlib/subprocess/sys/tempfile), keine
Drittlibs -- Ausnahme (j), die pyyaml für YAML-Struktur-Validierung nutzt
(analog ``mock_test_digest.py``, im Minimal-CI-Install bereits vorhanden).
(f)/(g) rufen echtes ``git`` als Subprozess -- lokal wie in CI verfügbar,
aber kein Netzwerk-Zugriff nötig (nur ``git init``/``commit`` in einem
Tempdir).
"""
from __future__ import annotations

import importlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

lint = importlib.import_module("lint_open_items_consistency")

_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK  {name}")
    else:
        _fails.append(f"{name}" + (f" — {detail}" if detail else ""))
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))


def _item(item_id: str, status: str, title: str = "Test-Item") -> dict:
    return {
        "id": item_id,
        "title": title,
        "opened": "2026-09-01",
        "description": "Fixture-Item für den Konsistenz-Check.",
        "status": status,
        "status_date": "2026-09-01",
    }


# ── (a) Datei korrekt parsen ─────────────────────────────────────────────

def test_a_parse_valid_items():
    raw = json.dumps({"schema_v": 1, "note": "x", "items": [_item("nyse-referer", "offen")]})
    items = lint._parse_items(raw)
    _check("A parse -> 1 Item", len(items) == 1, repr(items))
    _check("A parse -> korrekte id", items[0]["id"] == "nyse-referer")


def test_a2_parse_rejects_missing_items_key():
    raised = False
    try:
        lint._parse_items(json.dumps({"schema_v": 1}))
    except ValueError:
        raised = True
    _check("A2 fehlendes 'items' -> ValueError", raised)


def test_a3_parse_rejects_items_not_list():
    raised = False
    try:
        lint._parse_items(json.dumps({"items": {"not": "a list"}}))
    except ValueError:
        raised = True
    _check("A3 'items' kein List -> ValueError", raised)


# ── (b) ersatzloses Verschwinden -> Fund ────────────────────────────────

def test_b_item_disappears_without_erledigt_fires():
    old_items = [_item("nyse-referer", "offen"), _item("s8-timing", "beobachtet")]
    new_items = [_item("s8-timing", "beobachtet")]  # nyse-referer einfach weg
    violations = lint.check_consistency(old_items, new_items)
    _check("B ersatzloses Verschwinden -> genau 1 Fund", len(violations) == 1, repr(violations))
    _check("B Fund nennt betroffene id", "nyse-referer" in violations[0], violations[0] if violations else "")


def test_b2_both_items_disappear_without_erledigt_fires_twice():
    old_items = [_item("a", "offen"), _item("b", "beobachtet")]
    new_items = []
    violations = lint.check_consistency(old_items, new_items)
    _check("B2 beide verschwinden -> 2 Funde", len(violations) == 2, repr(violations))


# ── (c) korrekt auf 'erledigt' gesetzt -> kein Fund ─────────────────────

def test_c_item_marked_erledigt_stays_in_list_no_finding():
    old_items = [_item("nyse-referer", "offen")]
    new_items = [_item("nyse-referer", "erledigt")]
    violations = lint.check_consistency(old_items, new_items)
    _check("C Status -> 'erledigt' (bleibt in Liste) -> kein Fund", violations == [], repr(violations))


def test_c2_item_removed_after_being_erledigt_no_finding():
    old_items = [_item("nyse-referer", "erledigt")]
    new_items = []  # nach Abschluss aufgeräumt -- erlaubt laut Spec
    violations = lint.check_consistency(old_items, new_items)
    _check("C2 bereits 'erledigt' entfernt -> kein Fund", violations == [], repr(violations))


# ── (d) Struktur-Validierung ─────────────────────────────────────────────

def test_d_missing_required_field_detected():
    item = _item("x", "offen")
    del item["description"]
    errors = lint.validate_item_structure(item)
    _check("D fehlendes Pflichtfeld -> Fund", len(errors) == 1, repr(errors))


def test_d2_invalid_status_detected():
    item = _item("x", "irgendwas")
    errors = lint.validate_item_structure(item)
    _check("D2 ungültiger Status -> Fund", any("Status" in e for e in errors), repr(errors))


def test_d3_valid_item_no_errors():
    errors = lint.validate_item_structure(_item("x", "offen"))
    _check("D3 valides Item -> keine Funde", errors == [], repr(errors))


# ── (e) unveränderter Status -> kein Fund ────────────────────────────────

def test_e_unchanged_item_no_finding():
    old_items = [_item("nyse-referer", "offen")]
    new_items = [_item("nyse-referer", "offen")]
    violations = lint.check_consistency(old_items, new_items)
    _check("E unverändertes Item -> kein Fund", violations == [], repr(violations))


# ── (f)/(g) main() end-to-end gegen echtes Git-Repo (Tempdir) ───────────

class _GitFixtureRepo:
    """Baut ein eigenständiges Git-Repo in einem Tempdir mit zwei Commits
    (altes ``open_items.json`` -> neues ``open_items.json``) und biegt
    ``lint.ROOT`` temporär dorthin um. Stellt beides beim Verlassen
    zuverlässig wieder her."""

    def __init__(self, old_content: dict | None, new_content: dict) -> None:
        self.old_content = old_content
        self.new_content = new_content
        self._orig_root = None
        self._tmpdir = None
        self.base_sha = None

    def __enter__(self):
        self._tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="open_items_git_test_"))
        run = lambda *args: subprocess.run(
            args, cwd=str(self._tmpdir), capture_output=True, text=True, check=True
        )
        run("git", "init", "--quiet")
        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test")

        path = self._tmpdir / "open_items.json"
        if self.old_content is not None:
            path.write_text(json.dumps(self.old_content), encoding="utf-8")
            run("git", "add", "open_items.json")
            run("git", "commit", "--quiet", "-m", "old version")
            self.base_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=str(self._tmpdir),
                capture_output=True, text=True, check=True,
            ).stdout.strip()
        else:
            # Kein alter Commit -> base_sha zeigt auf einen leeren Erst-Commit
            # ohne die Datei (simuliert "Ref existiert, Datei aber nicht").
            (self._tmpdir / ".gitkeep").write_text("", encoding="utf-8")
            run("git", "add", ".gitkeep")
            run("git", "commit", "--quiet", "-m", "empty base")
            self.base_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=str(self._tmpdir),
                capture_output=True, text=True, check=True,
            ).stdout.strip()

        path.write_text(json.dumps(self.new_content), encoding="utf-8")
        run("git", "add", "open_items.json")
        run("git", "commit", "--quiet", "-m", "new version")

        self._orig_root = lint.ROOT
        lint.ROOT = self._tmpdir
        return self

    def __exit__(self, *exc) -> None:
        lint.ROOT = self._orig_root
        if self._tmpdir is not None:
            shutil.rmtree(self._tmpdir, ignore_errors=True)


def test_f_main_end_to_end_fires_on_real_git_disappearance():
    old_state = {"schema_v": 1, "items": [_item("nyse-referer", "offen")]}
    new_state = {"schema_v": 1, "items": []}
    with _GitFixtureRepo(old_state, new_state) as repo:
        import os
        os.environ["OPEN_ITEMS_BASE_REF"] = repo.base_sha
        try:
            rc = lint.main()
        finally:
            del os.environ["OPEN_ITEMS_BASE_REF"]
        _check("F main() end-to-end (echtes Git) -> exit 1", rc == 1, f"rc={rc}")


def test_f2_main_end_to_end_passes_on_real_git_erledigt():
    old_state = {"schema_v": 1, "items": [_item("nyse-referer", "offen")]}
    new_state = {"schema_v": 1, "items": [_item("nyse-referer", "erledigt")]}
    with _GitFixtureRepo(old_state, new_state) as repo:
        import os
        os.environ["OPEN_ITEMS_BASE_REF"] = repo.base_sha
        try:
            rc = lint.main()
        finally:
            del os.environ["OPEN_ITEMS_BASE_REF"]
        _check("F2 main() end-to-end (echtes Git, 'erledigt') -> exit 0", rc == 0, f"rc={rc}")


def test_g_main_fail_soft_when_base_has_no_file():
    """Simuliert genau den Fall dieses PRs: die Basis-Ref existiert, hat
    aber (noch) kein open_items.json -> main() darf NICHT failen."""
    new_state = {"schema_v": 1, "items": [_item("nyse-referer", "offen")]}
    with _GitFixtureRepo(None, new_state) as repo:
        import os
        os.environ["OPEN_ITEMS_BASE_REF"] = repo.base_sha
        try:
            rc = lint.main()
        finally:
            del os.environ["OPEN_ITEMS_BASE_REF"]
        _check("G Basis ohne Datei (Einführungs-PR) -> exit 0 (fail-soft)", rc == 0, f"rc={rc}")


def test_g2_main_fail_soft_when_base_ref_unresolvable():
    new_state = {"schema_v": 1, "items": [_item("nyse-referer", "offen")]}
    with _GitFixtureRepo({"schema_v": 1, "items": []}, new_state) as repo:
        import os
        os.environ["OPEN_ITEMS_BASE_REF"] = "does-not-exist-ref-xyz"
        try:
            rc = lint.main()
        finally:
            del os.environ["OPEN_ITEMS_BASE_REF"]
        _check("G2 nicht auflösbare Ref -> exit 0 (fail-soft)", rc == 0, f"rc={rc}")


# ── (h) Struktur-Fehler in neuer Version -> harter Fail ──────────────────

def test_h_main_hard_fails_on_broken_new_schema():
    broken_item = _item("x", "offen")
    del broken_item["title"]
    new_state = {"schema_v": 1, "items": [broken_item]}
    with _GitFixtureRepo(None, new_state) as repo:
        import os
        os.environ["OPEN_ITEMS_BASE_REF"] = repo.base_sha
        try:
            rc = lint.main()
        finally:
            del os.environ["OPEN_ITEMS_BASE_REF"]
        _check("H kaputtes Schema in neuer Version -> exit 1 (hart, kein fail-soft)",
               rc == 1, f"rc={rc}")


# ── (i) Regression: echtes Repo-open_items.json ist valide ──────────────

def test_i_real_repo_file_is_structurally_valid():
    real_path = ROOT / "open_items.json"
    if not real_path.exists():
        _check("I echtes open_items.json existiert", False, "Datei fehlt")
        return
    raw = real_path.read_text(encoding="utf-8")
    try:
        items = lint._parse_items(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        _check("I echtes open_items.json parsebar", False, str(exc))
        return
    errors = []
    for it in items:
        errors.extend(lint.validate_item_structure(it))
    _check("I echtes open_items.json strukturell valide", errors == [], repr(errors))


# ── (j) Workflow-Wiring: PR-Pfad + main-Push-Pfad ────────────────────────

def test_j1_pr_checks_workflow_wires_the_lint():
    import yaml as _yaml
    path = ROOT / ".github" / "workflows" / "pr-checks.yml"
    data = _yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = data["jobs"]["checks"]["steps"]
    names = [s.get("name") for s in steps]
    _check("J1 pr-checks.yml hat 'Lint open-items consistency'-Step",
           "Lint open-items consistency" in names, repr(names))
    lint_step = next(s for s in steps if s.get("name") == "Lint open-items consistency")
    _check("J1b Step nutzt lint_open_items_consistency.py",
           "lint_open_items_consistency.py" in lint_step.get("run", ""),
           lint_step.get("run", ""))
    _check("J1c Step setzt OPEN_ITEMS_BASE_REF via base.sha",
           "base.sha" in lint_step.get("env", {}).get("OPEN_ITEMS_BASE_REF", ""),
           repr(lint_step.get("env")))
    # Guardian-Finding: pr-checks.yml deckt NUR pull_request ab.
    on_block = data.get(True, data.get("on"))
    _check("J1d pr-checks.yml triggert NUR auf pull_request (kein push)",
           set(on_block.keys()) == {"pull_request"}, repr(on_block))


def test_j2_main_push_workflow_exists_and_wired():
    import yaml as _yaml
    path = ROOT / ".github" / "workflows" / "open_items_main_push_check.yml"
    _check("J2 open_items_main_push_check.yml existiert", path.exists())
    if not path.exists():
        return
    data = _yaml.safe_load(path.read_text(encoding="utf-8"))
    on_block = data.get(True, data.get("on"))
    push_cfg = on_block.get("push", {})
    _check("J2b triggert auf push -> branches: [main]",
           push_cfg.get("branches") == ["main"], repr(push_cfg))
    _check("J2c triggert nur bei Änderung an open_items.json",
           push_cfg.get("paths") == ["open_items.json"], repr(push_cfg))
    steps = data["jobs"]["check"]["steps"]
    names = [s.get("name") for s in steps]
    _check("J2d hat 'Lint open-items consistency'-Step",
           "Lint open-items consistency" in names, repr(names))
    lint_step = next(s for s in steps if s.get("name") == "Lint open-items consistency")
    _check("J2e Vergleichsbasis ist github.event.before (Pre-Push-Commit)",
           "event.before" in lint_step.get("env", {}).get("OPEN_ITEMS_BASE_REF", ""),
           repr(lint_step.get("env")))
    _check("J2f permissions sind read-only (rein detektiv, kein Push/Merge)",
           data.get("permissions") == {"contents": "read"}, repr(data.get("permissions")))


def test_j3_both_workflows_together_cover_pr_and_main_push():
    """Zusammen decken beide Workflows genau die zwei Pflegepfade aus dem
    CLAUDE.md-Wartungs-Absatz ab: ad-hoc per PR UND Gute-Nacht-Direct-Commit."""
    import yaml as _yaml
    pr_data = _yaml.safe_load(
        (ROOT / ".github" / "workflows" / "pr-checks.yml").read_text(encoding="utf-8")
    )
    push_path = ROOT / ".github" / "workflows" / "open_items_main_push_check.yml"
    pr_on = set((pr_data.get(True, pr_data.get("on"))).keys())
    push_data = _yaml.safe_load(push_path.read_text(encoding="utf-8"))
    push_on = set((push_data.get(True, push_data.get("on"))).keys())
    _check("J3 PR-Pfad und Push-Pfad sind disjunkt und zusammen vollständig",
           pr_on == {"pull_request"} and push_on == {"push"},
           f"pr_on={pr_on} push_on={push_on}")


def main() -> int:
    tests = [
        test_a_parse_valid_items,
        test_a2_parse_rejects_missing_items_key,
        test_a3_parse_rejects_items_not_list,
        test_b_item_disappears_without_erledigt_fires,
        test_b2_both_items_disappear_without_erledigt_fires_twice,
        test_c_item_marked_erledigt_stays_in_list_no_finding,
        test_c2_item_removed_after_being_erledigt_no_finding,
        test_d_missing_required_field_detected,
        test_d2_invalid_status_detected,
        test_d3_valid_item_no_errors,
        test_e_unchanged_item_no_finding,
        test_f_main_end_to_end_fires_on_real_git_disappearance,
        test_f2_main_end_to_end_passes_on_real_git_erledigt,
        test_g_main_fail_soft_when_base_has_no_file,
        test_g2_main_fail_soft_when_base_ref_unresolvable,
        test_h_main_hard_fails_on_broken_new_schema,
        test_i_real_repo_file_is_structurally_valid,
        test_j1_pr_checks_workflow_wires_the_lint,
        test_j2_main_push_workflow_exists_and_wired,
        test_j3_both_workflows_together_cover_pr_and_main_push,
    ]
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001 — Test-Harness, nicht Prod
            _fails.append(f"{t.__name__}: unexpected {type(exc).__name__}: {exc}")
            print(f"  FAIL {t.__name__}: unexpected {type(exc).__name__}: {exc}")

    print()
    if _fails:
        print(f"{len(_fails)} FAIL:")
        for f in _fails:
            print("  -", f)
        return 1
    print(f"Alle {len(tests)} lint_open_items_consistency-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
