"""Mock-Tests für ``scripts/lint_nan_bypass_fields.py`` (4. CI-Gate, 22.09.2026).

Treibt den ECHTEN Linter (``main()``/``_scan_file()``, nicht eine
Nachbildung) gegen feste, deterministische Fixture-Dateien in einem
Tempdir — NICHT gegen den echten, sich ändernden Repo-Code (Determinismus-
Vorgabe). ``lint.ROOT`` und ``lint._SCAN_FILES`` werden dafür pro Test
temporär umgebogen und danach zuverlässig zurückgesetzt.

Pflicht-Szenarien laut Aufgabenstellung:
  (a) Allowlist-Feld mit ``or 0`` ohne Guard  -> Lint schlägt fehl (exit 1)
  (b) derselbe Fall, aber in der Ausnahmeliste -> Lint besteht (exit 0)
  (c) Nicht-Allowlist-Feld (Zähler) mit ``or 0`` -> Lint besteht (kein FP)

Zusätzlich (Robustheit der zweistufigen Sicherheits-Gegenprobe):
  (d) int(...)-Cast um den ganzen Ausdruck -> kein Fund (ValueError-Guard)
  (e) .get(...) in eine Wrapper-Funktion eingebettet -> kein Fund
  (f) Baseline-Mechanismus (_BASELINE_KNOWN_OPEN, Datei+Zeile+Feld) statt
      _EXCEPTIONS (Funktions-Name+Feld) unterdrückt denselben Fund
  (g) Regression: der echte, aktuelle Repo-Code ist grün (kein neuer,
      unbewachter Fund außerhalb Baseline/Exceptions) — das ist der
      tatsächliche CI-Gate-Zustand, den dieser Linter ab jetzt hält.

Kategorie A: reine stdlib (ast/pathlib/sys/tempfile), keine Drittlibs.
"""
from __future__ import annotations

import importlib
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

lint = importlib.import_module("lint_nan_bypass_fields")

_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK  {name}")
    else:
        _fails.append(f"{name}" + (f" — {detail}" if detail else ""))
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))


class _FixtureRepo:
    """Context-Manager: baut ein Tempdir mit EINER Fixture-Datei, biegt
    ``lint.ROOT``/``lint._SCAN_FILES`` temporär dorthin um, stellt beides
    beim Verlassen zuverlässig wieder her (auch bei Exceptions)."""

    def __init__(self, filename: str, src: str) -> None:
        self.filename = filename
        self.src = src
        self._orig_root = None
        self._orig_scan_files = None
        self._tmpdir = None

    def __enter__(self) -> pathlib.Path:
        self._tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="lint_nan_bypass_test_"))
        (self._tmpdir / self.filename).write_text(self.src, encoding="utf-8")
        self._orig_root = lint.ROOT
        self._orig_scan_files = lint._SCAN_FILES
        lint.ROOT = self._tmpdir
        lint._SCAN_FILES = (self.filename,)
        return self._tmpdir

    def __exit__(self, *exc) -> None:
        lint.ROOT = self._orig_root
        lint._SCAN_FILES = self._orig_scan_files
        if self._tmpdir is not None:
            shutil.rmtree(self._tmpdir, ignore_errors=True)


# ── (a) Allowlist-Feld, kein Guard -> Fund ──────────────────────────────

_SRC_RISKY = '''
def risk_assessment(stock):
    sf = stock.get("short_float") or 0
    return sf
'''


def test_a_allowlist_field_no_guard_fails():
    with _FixtureRepo("generate_report.py", _SRC_RISKY):
        rc = lint.main()
        _check("A allowlist-Feld ohne Guard -> exit 1", rc == 1, f"rc={rc}")


def test_a2_finding_names_correct_field_and_line():
    with _FixtureRepo("generate_report.py", _SRC_RISKY):
        findings = lint._scan_file("generate_report.py")
        _check("A2 genau 1 Fund", len(findings) == 1, repr(findings))
        if findings:
            _, lineno, func_name, field, _ = findings[0]
            _check("A2 Feld korrekt", field == "short_float")
            _check("A2 Funktion korrekt", func_name == "risk_assessment")
            _check("A2 Zeile korrekt", lineno == 3, f"lineno={lineno}")


# ── (b) derselbe Fall, aber in _EXCEPTIONS -> besteht ───────────────────


def test_b_exceptions_suppresses_finding():
    orig_exceptions = lint._EXCEPTIONS
    try:
        lint._EXCEPTIONS = frozenset({
            ("generate_report.py", "risk_assessment", "short_float"),
        })
        with _FixtureRepo("generate_report.py", _SRC_RISKY):
            rc = lint.main()
            _check("B in _EXCEPTIONS -> exit 0", rc == 0, f"rc={rc}")
    finally:
        lint._EXCEPTIONS = orig_exceptions


# ── (c) Nicht-Allowlist-Feld (Zähler) -> kein False Positive ────────────

_SRC_COUNTER = '''
def detect_anomalies(signal):
    n = signal.get("active_triggers") or 0
    return n
'''


def test_c_non_allowlist_field_no_false_positive():
    with _FixtureRepo("generate_report.py", _SRC_COUNTER):
        rc = lint.main()
        findings = lint._scan_file("generate_report.py")
        _check("C Zähler-Feld -> exit 0 (kein FP)", rc == 0, f"rc={rc}")
        _check("C Zähler-Feld -> 0 Funde", len(findings) == 0, repr(findings))


# ── (d) int(...)-Cast-Guard ──────────────────────────────────────────────

_SRC_INT_CAST = '''
def f(signal):
    x = int(signal.get("score") or 0)
    return x
'''


def test_d_int_cast_guard_no_finding():
    with _FixtureRepo("generate_report.py", _SRC_INT_CAST):
        rc = lint.main()
        _check("D int(...)-Cast -> exit 0 (ValueError-Guard bei NaN)",
               rc == 0, f"rc={rc}")


# ── (e) Wrapper-Funktion um .get() ───────────────────────────────────────

_SRC_WRAPPED = '''
def f(stock, safe_float_fn):
    sf = safe_float_fn(stock.get("short_float")) or 0.0
    return sf
'''


def test_e_wrapped_in_function_no_finding():
    with _FixtureRepo("generate_report.py", _SRC_WRAPPED):
        rc = lint.main()
        _check("E .get() in Wrapper-Call eingebettet -> exit 0",
               rc == 0, f"rc={rc}")


# ── (f) Baseline-Mechanismus (Datei+Zeile+Feld statt Funktion+Feld) ─────


def test_f_baseline_suppresses_by_file_line_field():
    orig_baseline = lint._BASELINE_KNOWN_OPEN
    try:
        lint._BASELINE_KNOWN_OPEN = frozenset({
            ("generate_report.py", 3, "short_float"),
        })
        with _FixtureRepo("generate_report.py", _SRC_RISKY):
            rc = lint.main()
            _check("F Baseline (Datei+Zeile+Feld) -> exit 0", rc == 0, f"rc={rc}")
    finally:
        lint._BASELINE_KNOWN_OPEN = orig_baseline


def test_f2_baseline_does_not_suppress_different_line():
    """Baseline ist zeilen-scharf — verschiebt sich der Fund auf eine
    ANDERE Zeile im selben (Datei,Feld), bleibt es ein Fund (bewusst
    fragiler als _EXCEPTIONS, siehe Docstring)."""
    src_shifted = '\n\n' + _SRC_RISKY  # verschiebt die Fund-Zeile um 2
    orig_baseline = lint._BASELINE_KNOWN_OPEN
    try:
        lint._BASELINE_KNOWN_OPEN = frozenset({
            ("generate_report.py", 3, "short_float"),  # alte Zeile
        })
        with _FixtureRepo("generate_report.py", src_shifted):
            rc = lint.main()
            _check("F2 Baseline greift NICHT bei verschobener Zeile -> exit 1",
                   rc == 1, f"rc={rc}")
    finally:
        lint._BASELINE_KNOWN_OPEN = orig_baseline


# ── (g) Regression: echter, aktueller Repo-Code ist grün ────────────────


def test_g_real_repo_is_currently_clean():
    """Kein Fixture-Test — bewusste EINZIGE Ausnahme, die den echten
    Repo-Code prüft: bestätigt den GEGENWÄRTIGEN CI-Gate-Zustand (Baseline
    deckt exakt die 70 bekannten Funde ab). Nicht Teil der isolierten
    Determinismus-Tests oben — dient nur als Smoke-Test, dass main() nach
    Einführung tatsächlich grün ist."""
    rc = lint.main()
    _check("G echter Repo-Code aktuell lint-sauber (Baseline deckt Alt-Bestand)",
           rc == 0, f"rc={rc}")


def main() -> int:
    tests = [
        test_a_allowlist_field_no_guard_fails,
        test_a2_finding_names_correct_field_and_line,
        test_b_exceptions_suppresses_finding,
        test_c_non_allowlist_field_no_false_positive,
        test_d_int_cast_guard_no_finding,
        test_e_wrapped_in_function_no_finding,
        test_f_baseline_suppresses_by_file_line_field,
        test_f2_baseline_does_not_suppress_different_line,
        test_g_real_repo_is_currently_clean,
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
    print(f"Alle {len(tests)} lint_nan_bypass_fields-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
