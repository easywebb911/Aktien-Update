"""Mock-Tests für ``scripts/check_handover_staleness.py`` (28.09.2026).

Treibt die ECHTEN Kern-Funktionen (``extract_block1_text``,
``extract_highest_doc_pr``, ``compute_staleness``,
``format_staleness_hint``, ``fetch_highest_merged_pr``, ``main``) -- nicht
eine Nachbildung. Die Kern-Logik ist pure (kein I/O), deshalb laufen die
Pflicht-Szenarien direkt gegen feste, deterministische Fixture-Strings/
-Zahlen. ``fetch_highest_merged_pr`` (der einzige I/O-Wrapper) wird via
``unittest.mock`` auf ``subprocess.run`` gepatcht -- KEIN echter
``gh``-Aufruf in der Test-Suite (Exzellenz-Block-Vorgabe: Determinismus).

Pflicht-Szenarien laut Aufgabenstellung:
  (a) Bei simuliertem Rückstand >= 3 erscheint der Hinweis
  (b) Bei Rückstand < 3 erscheint KEIN Hinweis
  (c) Bei simuliertem gh-API-Fehler bleibt der Check fail-soft
      (kein CI-Fail / main() liefert weiterhin 0, klare Fehlermeldung
      statt Absturz)

Zusätzlich (Robustheit):
  (d) Range-Notation ('`#533`-`#536`') liefert den höheren Endpunkt
  (e) Fehlende Block-1-Markierung -> None (fail-soft, kein Crash)
  (f) Negativer/Null-Rückstand (Doku bereits aktuell oder voraus) -> kein Fund
  (g) Schwellen-Grenzfall: Rückstand == threshold-1 kein Fund,
      Rückstand == threshold Fund (exakte Boundary, kein Off-by-one)
  (h) fetch_highest_merged_pr: Erfolgspfad mit validem JSON
  (i) fetch_highest_merged_pr: non-zero exit code -> fail-soft
  (j) fetch_highest_merged_pr: kaputtes JSON -> fail-soft
  (k) fetch_highest_merged_pr: leere Merge-Liste -> fail-soft
  (l) fetch_highest_merged_pr: unerwartetes Schema (fehlendes 'number') -> fail-soft
  (m) fetch_highest_merged_pr: OSError (gh fehlt im Runner-Image) -> fail-soft
  (n) main() end-to-end: Hinweis-Pfad, OK-Pfad, Fehler-Pfad -- alle drei
      liefern exit 0 (main() failt NIE, siehe Docstring des Moduls)
  (o) main() fail-soft, wenn SESSION_HANDOVER.md fehlt
  (p) Regression-Smoke-Test: das echte, aktuell committete
      SESSION_HANDOVER.md im Repo liefert eine PR-Nummer aus Block 1
      (Sanity-Check, dass die Regex tatsächlich auf die Live-Struktur passt)
  (q) Workflow-Wiring: pr-checks.yml hat die neue 'pull-requests: read'-
      Permission UND einen Step, der check_handover_staleness.py aufruft

Kategorie A: reine stdlib (json/pathlib/re/subprocess/sys/unittest.mock) +
pyyaml für die YAML-Struktur-Validierung in (q) (analog mock_test_digest.py,
im Minimal-CI-Install bereits vorhanden). Kein Netzwerk-Zugriff nötig.
"""
from __future__ import annotations

import importlib
import pathlib
import sys
import tempfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

chs = importlib.import_module("check_handover_staleness")

_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK  {name}")
    else:
        _fails.append(f"{name}" + (f" — {detail}" if detail else ""))
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))


def _handover_fixture(block1_body: str, with_block2: bool = True) -> str:
    tail = "\n## 2) AKTIVE POSITIONEN\n\n- Beispiel\n" if with_block2 else ""
    return (
        "# SESSION_HANDOVER.md — Stand 28.09.2026\n\n"
        "Intro-Absatz.\n\n---\n\n"
        "## 1) HEUTE IMPLEMENTIERT (chronologisch, mit Hashes)\n\n"
        f"{block1_body}\n"
        f"{tail}"
    )


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ── (a)/(b) Schwellen-Verhalten über format_staleness_hint ────────────────
def test_a_lag_at_or_above_threshold_produces_hint():
    hint = chs.format_staleness_hint(570, 567, threshold=3)  # lag == 3
    _check("A1 lag==threshold -> Hinweis vorhanden", hint is not None)
    _check("A1 Hinweis nennt beide PR-Nummern",
           hint is not None and "#570" in hint and "#567" in hint, hint)

    hint_bigger = chs.format_staleness_hint(598, 567, threshold=3)  # lag == 31
    _check("A2 großer Rückstand (31) -> Hinweis vorhanden",
           hint_bigger is not None)


def test_b_lag_below_threshold_produces_no_hint():
    hint = chs.format_staleness_hint(568, 567, threshold=3)  # lag == 1
    _check("B1 lag==1 (< threshold 3) -> kein Hinweis", hint is None)

    hint2 = chs.format_staleness_hint(569, 567, threshold=3)  # lag == 2
    _check("B2 lag==2 (< threshold 3) -> kein Hinweis "
           "(heutiger #565/#566-Fall wäre HIER noch kein CI-Hinweis)",
           hint2 is None)


# ── (c) gh-API-Fehler bleibt fail-soft ─────────────────────────────────────
def test_c_gh_api_failure_is_fail_soft_not_crash():
    with mock.patch.object(
            chs.subprocess, "run",
            side_effect=OSError("gh: command not found")):
        number, error = chs.fetch_highest_merged_pr()
    _check("C1 OSError bei gh-Aufruf -> (None, Fehlertext), kein Crash",
           number is None and isinstance(error, str) and error, error)

    # main() darf dabei NICHT abstürzen und muss weiterhin 0 liefern.
    fixture = _handover_fixture("- `#560` (`abc1234`, 22.09.) Beispiel-PR")
    tmp_dir = _write_tmp_handover(fixture)
    try:
        with mock.patch.object(chs, "ROOT", tmp_dir), \
             mock.patch.object(
                 chs.subprocess, "run",
                 side_effect=OSError("gh: command not found")):
            rc = chs.main()
        _check("C2 main() bleibt fail-soft bei gh-Fehler -> exit 0", rc == 0, rc)
    finally:
        _cleanup_tmp(tmp_dir)


# ── Helpers für main()-End-to-End-Tests (Tempdir mit SESSION_HANDOVER.md) ──
def _write_tmp_handover(text: str) -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp(prefix="handover_staleness_test_"))
    (d / chs.HANDOVER_PATH).write_text(text, encoding="utf-8")
    return d


def _cleanup_tmp(d: pathlib.Path) -> None:
    import shutil
    shutil.rmtree(d, ignore_errors=True)


# ── (d)/(e)/(f) extract_highest_doc_pr / compute_staleness Edge-Cases ──────
def test_d_range_notation_yields_higher_endpoint():
    fixture = _handover_fixture(
        "- **NaN-Härtungskette:** `#533`–`#536` + `#557`–`#559` + `#561`.")
    n = chs.extract_highest_doc_pr(fixture)
    _check("D1 Range-Notation -> höchster Endpunkt (561)", n == 561, n)


def test_d2_hex_color_codes_do_not_contaminate_pr_number():
    # Regression (28.09.2026): Block 1 enthält echte CSS-Hex-Codes in
    # Backticks (z.B. Monster-Neutralisierungs-Farbe). Ein naives "#\d+"
    # würde aus "#22c55e" die Ziffern "22" als falsche PR-Nummer lesen --
    # verifiziert gegen die echte Live-Datei (Fund: max ohne \b-Fix
    # inkludierte 22/94 aus genau diesem Muster).
    fixture = _handover_fixture(
        "- **A** — Monster-Farbe neutral-grau (`#22c55e→#94a3b8`) · `#565`"
        " tatsächliche PR-Referenz.")
    n = chs.extract_highest_doc_pr(fixture)
    _check("D2 Hex-Code-Fragmente (22/94) NICHT als PR-Nummer erkannt, "
           "echte Referenz #565 schon", n == 565, n)

    # Gegenprobe: ein Hex-Code mit hohem Ziffern-Präfix würde OHNE den
    # \b-Fix den Rückstand fälschlich verschleiern (highest_doc_pr zu
    # hoch -> lag zu niedrig -> Hinweis bliebe fälschlich aus).
    fixture_danger = _handover_fixture(
        "- Farbwert `#598abc` erwähnt, echte PR-Referenz ist `#561`.")
    n_danger = chs.extract_highest_doc_pr(fixture_danger)
    _check("D3 Gefahr-Fall: Hex-Präfix 598 NICHT als PR-Nummer "
           "übernommen, echte Referenz 561 korrekt", n_danger == 561, n_danger)


def test_e_missing_block1_marker_returns_none():
    text = "# Irgendein Dokument\n\nKein Block-1-Header hier.\n"
    n = chs.extract_highest_doc_pr(text)
    _check("E1 fehlende Block-1-Markierung -> None (fail-soft)", n is None)


def test_f_non_positive_lag_is_not_a_finding():
    _check("F1 lag==0 (identisch) -> compute_staleness liefert 0",
           chs.compute_staleness(567, 567) == 0)
    hint_zero = chs.format_staleness_hint(567, 567, threshold=3)
    _check("F2 lag==0 -> kein Hinweis", hint_zero is None)

    _check("F3 lag negativ (Doku nennt bereits höhere Nummer) -> negativ",
           chs.compute_staleness(560, 567) == -7)
    hint_neg = chs.format_staleness_hint(560, 567, threshold=3)
    _check("F4 negativer lag -> kein Hinweis", hint_neg is None)


def test_g_threshold_boundary_exact():
    below = chs.format_staleness_hint(569, 567, threshold=3)  # lag==2
    at = chs.format_staleness_hint(570, 567, threshold=3)      # lag==3
    _check("G1 lag==threshold-1 -> kein Hinweis (kein Off-by-one)",
           below is None)
    _check("G2 lag==threshold -> Hinweis (Grenze selbst zählt schon)",
           at is not None)


# ── (h)-(m) fetch_highest_merged_pr Fehlerpfade ────────────────────────────
def test_h_fetch_success_path():
    with mock.patch.object(
            chs.subprocess, "run",
            return_value=_FakeCompleted(0, stdout='[{"number": 599}]')):
        number, error = chs.fetch_highest_merged_pr()
    _check("H1 Erfolgspfad -> korrekte Nummer, kein Fehler",
           number == 599 and error is None, (number, error))


def test_i_fetch_nonzero_exit_code_is_fail_soft():
    with mock.patch.object(
            chs.subprocess, "run",
            return_value=_FakeCompleted(1, stdout="", stderr="HTTP 403 rate limited")):
        number, error = chs.fetch_highest_merged_pr()
    _check("I1 non-zero exit -> (None, Fehlertext mit Exit-Code)",
           number is None and "403" in (error or ""), error)


def test_j_fetch_bad_json_is_fail_soft():
    with mock.patch.object(
            chs.subprocess, "run",
            return_value=_FakeCompleted(0, stdout="not-json{{{")):
        number, error = chs.fetch_highest_merged_pr()
    _check("J1 kaputtes JSON -> (None, Fehlertext)",
           number is None and error is not None, error)


def test_k_fetch_empty_list_is_fail_soft():
    with mock.patch.object(
            chs.subprocess, "run",
            return_value=_FakeCompleted(0, stdout="[]")):
        number, error = chs.fetch_highest_merged_pr()
    _check("K1 leere Merge-Liste -> (None, Fehlertext)",
           number is None and error is not None, error)


def test_l_fetch_unexpected_schema_is_fail_soft():
    with mock.patch.object(
            chs.subprocess, "run",
            return_value=_FakeCompleted(0, stdout='[{"unexpected": true}]')):
        number, error = chs.fetch_highest_merged_pr()
    _check("L1 fehlendes 'number'-Feld -> (None, Fehlertext)",
           number is None and error is not None, error)


def test_m_fetch_timeout_is_fail_soft():
    import subprocess as _sp
    with mock.patch.object(
            chs.subprocess, "run",
            side_effect=_sp.TimeoutExpired(cmd="gh", timeout=30)):
        number, error = chs.fetch_highest_merged_pr()
    _check("M1 Timeout -> (None, Fehlertext), kein Crash",
           number is None and error is not None, error)


# ── (n)/(o) main() End-to-End ───────────────────────────────────────────────
def test_n_main_end_to_end_three_paths_all_exit_zero():
    fixture = _handover_fixture("- `#560` (`abc1234`, 22.09.) Beispiel-PR")

    # Pfad 1: Hinweis (großer Rückstand)
    tmp1 = _write_tmp_handover(fixture)
    try:
        with mock.patch.object(chs, "ROOT", tmp1), \
             mock.patch.object(chs, "fetch_highest_merged_pr",
                                return_value=(598, None)):
            rc1 = chs.main()
        _check("N1 main() Hinweis-Pfad -> exit 0", rc1 == 0, rc1)
    finally:
        _cleanup_tmp(tmp1)

    # Pfad 2: OK (kein Rückstand über Schwelle)
    tmp2 = _write_tmp_handover(fixture)
    try:
        with mock.patch.object(chs, "ROOT", tmp2), \
             mock.patch.object(chs, "fetch_highest_merged_pr",
                                return_value=(561, None)):
            rc2 = chs.main()
        _check("N2 main() OK-Pfad -> exit 0", rc2 == 0, rc2)
    finally:
        _cleanup_tmp(tmp2)

    # Pfad 3: gh-Fehler
    tmp3 = _write_tmp_handover(fixture)
    try:
        with mock.patch.object(chs, "ROOT", tmp3), \
             mock.patch.object(chs, "fetch_highest_merged_pr",
                                return_value=(None, "simulierter API-Fehler")):
            rc3 = chs.main()
        _check("N3 main() Fehler-Pfad -> exit 0 (kein CI-Fail)", rc3 == 0, rc3)
    finally:
        _cleanup_tmp(tmp3)


def test_o_main_missing_handover_file_is_fail_soft():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="handover_staleness_test_empty_"))
    try:
        with mock.patch.object(chs, "ROOT", tmp):
            rc = chs.main()
        _check("O1 fehlende SESSION_HANDOVER.md -> exit 0 (fail-soft)", rc == 0, rc)
    finally:
        _cleanup_tmp(tmp)


# ── (p) Regression-Smoke-Test gegen das echte, committete Handover-File ────
def test_p_regression_real_handover_file_parses():
    real_file = ROOT / chs.HANDOVER_PATH
    if not real_file.exists():
        _check("P1 SESSION_HANDOVER.md vorhanden (Smoke-Test)", False,
               "Datei fehlt im Repo-Root")
        return
    text = real_file.read_text(encoding="utf-8")
    n = chs.extract_highest_doc_pr(text)
    _check("P1 echtes SESSION_HANDOVER.md liefert eine PR-Nummer aus Block 1",
           isinstance(n, int) and n > 0, n)


# ── (q) Workflow-Wiring in pr-checks.yml ────────────────────────────────────
def test_q_workflow_wiring():
    try:
        import yaml
    except ImportError:
        _check("Q1 pyyaml verfügbar (Voraussetzung für Wiring-Check)", False,
               "pyyaml nicht installiert -- übersprungen")
        return

    wf_path = ROOT / ".github" / "workflows" / "pr-checks.yml"
    raw = wf_path.read_text(encoding="utf-8")
    doc = yaml.safe_load(raw)

    perms = doc.get("permissions", {})
    _check("Q1 'contents: read' weiterhin vorhanden (unverändert)",
           perms.get("contents") == "read", perms)
    _check("Q2 NEUE Permission 'pull-requests: read' gesetzt",
           perms.get("pull-requests") == "read", perms)

    steps = doc.get("jobs", {}).get("checks", {}).get("steps", [])
    staleness_steps = [
        s for s in steps
        if "check_handover_staleness.py" in str(s.get("run", ""))
    ]
    _check("Q3 genau ein Step ruft check_handover_staleness.py auf",
           len(staleness_steps) == 1, len(staleness_steps))

    if staleness_steps:
        step = staleness_steps[0]
        env = step.get("env", {}) or {}
        _check("Q4 Step setzt GH_TOKEN für die gh-CLI-Authentifizierung",
               "GH_TOKEN" in env, env)


def main() -> int:
    test_a_lag_at_or_above_threshold_produces_hint()
    test_b_lag_below_threshold_produces_no_hint()
    test_c_gh_api_failure_is_fail_soft_not_crash()
    test_d_range_notation_yields_higher_endpoint()
    test_d2_hex_color_codes_do_not_contaminate_pr_number()
    test_e_missing_block1_marker_returns_none()
    test_f_non_positive_lag_is_not_a_finding()
    test_g_threshold_boundary_exact()
    test_h_fetch_success_path()
    test_i_fetch_nonzero_exit_code_is_fail_soft()
    test_j_fetch_bad_json_is_fail_soft()
    test_k_fetch_empty_list_is_fail_soft()
    test_l_fetch_unexpected_schema_is_fail_soft()
    test_m_fetch_timeout_is_fail_soft()
    test_n_main_end_to_end_three_paths_all_exit_zero()
    test_o_main_missing_handover_file_is_fail_soft()
    test_p_regression_real_handover_file_parses()
    test_q_workflow_wiring()

    if _fails:
        print(f"\n{len(_fails)} Test(s) FEHLGESCHLAGEN: {_fails}")
        return 1
    print("\nAlle handover_staleness-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
