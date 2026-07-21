"""Mock-Tests für Score-Konfidenz — Single-Source-Umbau.

``compute_score_confidence`` liefert seit dem Umbau NUR die DATEN-Dimension
(n gereift + data_tier groß/mittel/klein/keine) — KEINE Validierungs-Stufe
(kein has_auc, kein „robust"). Der Validierungs-STATUS kommt getrennt aus
``config.SCORE_STATUS_LABELS`` (dieselbe Quelle wie die Karten-Badges); das
Panel rendert beide Dimensionen sichtbar getrennt.

Reine Anzeige — CI-Lint ``lint_score_confidence_isolation.py`` erzwingt die
Trennung von der Score-Berechnung.

Tests:
  1. Setup-data_tier je Stichprobengröße (groß/mittel/klein/keine).
  2. Übrige 5 Klassen: n=None, data_tier="keine" (keine eigene Persistenz).
  3. Edge: leeres/None-backtest_history → setup data_tier "keine".
  4. computed_at ISO-UTC.
  5. Top-Level-Keys vollständig (6 Scores + computed_at).
  6. Entry-Felder: {n, data_tier} (KEIN tier/note mehr).
  7. HTML-Render: Validierungs-Status (aus config) + Datenbasis getrennt.
  8. HTML-Render: leeres Dict → Hinweis-Zeile.
  9. HTML-Render: alle 6 Labels.
 10. Isolation-Lint grün.
 11. Methodik-Panel-Placeholder + Foot ehrlich (kein „Stand" über Status).
 12. Workflow integriert Isolation-Lint.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

src = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _extract(func_def: str) -> str:
    pat = rf"^def {re.escape(func_def)}\([\s\S]+?(?=^def\s|^class\s|^# ====|^_[A-Z])"
    m = re.search(pat, src, re.MULTILINE)
    assert m, f"{func_def} nicht in generate_report.py gefunden"
    return m.group(0)


def _extract_assign(name: str) -> str:
    pat = rf"^{re.escape(name)} = \{{[\s\S]+?\n\}}"
    m = re.search(pat, src, re.MULTILINE)
    assert m, f"{name} (dict) nicht gefunden"
    return m.group(0)


class _Log:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def debug(self, *a, **k): pass


ns: dict = {"log": _Log()}
exec(
    "from config import (\n"
    "    SCORE_STATUS_LABELS,\n"
    "    SCORE_CONFIDENCE_N_ROBUST,\n"
    "    SCORE_CONFIDENCE_N_MITTEL,\n"
    "    SCORE_CONFIDENCE_N_PROVISORISCH,\n"
    ")\n"
    "from datetime import datetime\n"
    "from zoneinfo import ZoneInfo\n"
    + _extract("_data_tier") + "\n"
    + _extract("compute_score_confidence") + "\n"
    + _extract_assign("_DATA_TIER_LABEL") + "\n"
    + _extract("_iso_to_de") + "\n"
    + _extract("_score_confidence_rows_html"),
    ns,
)
compute_score_confidence    = ns["compute_score_confidence"]
_score_confidence_rows_html = ns["_score_confidence_rows_html"]


def _bh(n_with_returns: int) -> list[dict]:
    return [
        {"ticker": f"T{i}", "date": "01.01.2026",
         "return_10d": 5.0 if i < n_with_returns else None}
        for i in range(max(n_with_returns, 1))
    ]


# === 1 — Setup data_tier je Stichprobengröße ==============================

def test_setup_data_tier_gross():
    res = compute_score_confidence(_bh(600))
    assert res["setup"]["data_tier"] == "groß", res["setup"]
    assert res["setup"]["n"] == 600


def test_setup_data_tier_mittel():
    res = compute_score_confidence(_bh(100))
    assert res["setup"]["data_tier"] == "mittel", res["setup"]


def test_setup_data_tier_klein():
    res = compute_score_confidence(_bh(10))
    assert res["setup"]["data_tier"] == "klein", res["setup"]


def test_setup_data_tier_keine_when_empty():
    res = compute_score_confidence([])
    assert res["setup"]["data_tier"] == "keine", res["setup"]
    assert res["setup"]["n"] == 0


# === 2 — Übrige 5 Klassen: keine eigene Persistenz ========================

def test_other_scores_no_persistence():
    for bh in (_bh(5000), _bh(0)):
        res = compute_score_confidence(bh)
        for key in ("earliness", "monster", "ki", "conviction", "exit_pressure"):
            assert res[key]["n"] is None, f"{key} n sollte None sein"
            assert res[key]["data_tier"] == "keine", f"{key} data_tier"


# === 3 — Edge-Cases ========================================================

def test_none_backtest_history():
    res = compute_score_confidence(None)
    assert res["setup"]["data_tier"] == "keine"
    assert res["setup"]["n"] == 0


def test_entries_without_return_10d():
    bh = [{"ticker": "T", "date": "01.01.2026", "return_10d": None}] * 1000
    res = compute_score_confidence(bh)
    assert res["setup"]["data_tier"] == "keine", "0 mit Returns → keine"


# === 4 — computed_at =======================================================

def test_computed_at_iso_utc():
    res = compute_score_confidence([])
    ts = res.get("computed_at")
    assert ts is not None
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", ts), ts


# === 5 — Persistenz-Schema =================================================

def test_top_level_keys_complete():
    res = compute_score_confidence(_bh(100))
    expected = {"setup", "earliness", "monster", "ki", "conviction",
                "exit_pressure", "computed_at"}
    assert set(res.keys()) == expected, set(res.keys()) ^ expected


def test_entry_fields_data_dimension_only():
    res = compute_score_confidence(_bh(100))
    for key in ("setup", "earliness", "monster", "ki", "conviction",
                "exit_pressure"):
        assert set(res[key].keys()) == {"n", "data_tier"}, res[key]
        assert "tier" not in res[key] and "note" not in res[key], (
            f"{key} trägt noch Validierungs-Felder")


# === 6 — HTML-Render: zwei Dimensionen getrennt ============================

def test_html_two_dimensions_separated():
    res = compute_score_confidence(_bh(600))
    rows_html, computed_at = _score_confidence_rows_html(res)
    # Validierungs-Status aus config (Single-Source) — Setup = unvalidiert.
    # Icon (kompakt) + Status (fett, vollbreit) in getrennten Spans.
    assert "🔴" in rows_html and "<strong>unvalidiert</strong>" in rows_html, rows_html
    # Daten-Dimension getrennt, mit n + tier.
    assert "Datenbasis: n=600 gereift (groß)" in rows_html, rows_html
    # Befund-Datum aus config (DE-formatiert) — nicht Render-Zeit.
    assert "Befund 30.06.2026" in rows_html, rows_html
    # Panel darf das alte „robust"-Wort NICHT mehr zeigen.
    assert "robust" not in rows_html, "verbranntes Wort 'robust' im Panel"
    assert computed_at == res["computed_at"]


def test_html_empty_confidence_returns_hint():
    rows_html, computed_at = _score_confidence_rows_html({})
    assert "sb-empty" in rows_html, rows_html
    assert computed_at == "—"


def test_html_labels_present():
    res = compute_score_confidence(_bh(100))
    rows_html, _ = _score_confidence_rows_html(res)
    for label in ("Setup-Score", "Earliness V2", "Monster-Score", "KI-Score",
                  "Conviction", "Exit-Druck"):
        assert label in rows_html, f"{label!r} fehlt im HTML"


# === 7 — CI-Lint ===========================================================

def test_isolation_lint_passes():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "lint_score_confidence_isolation.py")],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        f"Isolation-Lint scheitert:\nstdout: {proc.stdout}\nstderr: {proc.stderr}")


# === 8 — Methodik-Panel ====================================================

def test_methodology_panel_honest_foot():
    assert "{score_confidence_rows_html}" in src, "Placeholder fehlt"
    assert "{score_confidence_computed_at}" in src, "computed_at-Placeholder fehlt"
    assert "Konfidenz der Scores" in src
    # Foot ehrlich: kein blankes „Stand: <Render-Zeit>" mehr über den Texten.
    assert "Datenbasis berechnet:" in src, \
        "Panel-Foot benennt den Timestamp nicht ehrlich als Daten-Dimension"


def test_workflow_includes_isolation_lint_step():
    yml = (ROOT / ".github" / "workflows" / "daily-squeeze-report.yml"
           ).read_text(encoding="utf-8")
    assert "lint_score_confidence_isolation.py" in yml
    idx_lint     = yml.find("lint_score_confidence_isolation.py")
    idx_generate = yml.find("Generate squeeze report")
    assert idx_lint < idx_generate, "Isolation-Lint muss VOR Generate laufen"


def main() -> None:
    tests = [
        ("Setup data_tier ≥500 → groß",                 test_setup_data_tier_gross),
        ("Setup data_tier 50–499 → mittel",              test_setup_data_tier_mittel),
        ("Setup data_tier 1–49 → klein",                 test_setup_data_tier_klein),
        ("Setup data_tier 0 → keine",                    test_setup_data_tier_keine_when_empty),
        ("Übrige 5: n=None, keine Persistenz",           test_other_scores_no_persistence),
        ("None-backtest_history graceful",               test_none_backtest_history),
        ("Einträge ohne return_10d zählen nicht",         test_entries_without_return_10d),
        ("computed_at ISO-UTC",                          test_computed_at_iso_utc),
        ("Top-Level-Keys vollständig",                   test_top_level_keys_complete),
        ("Entry-Felder nur {n, data_tier}",              test_entry_fields_data_dimension_only),
        ("HTML: Status + Datenbasis getrennt",           test_html_two_dimensions_separated),
        ("HTML: leeres Dict → Hinweis",                  test_html_empty_confidence_returns_hint),
        ("HTML: 6 Labels vorhanden",                     test_html_labels_present),
        ("Isolation-Lint grün",                          test_isolation_lint_passes),
        ("Methodik-Panel Foot ehrlich",                  test_methodology_panel_honest_foot),
        ("Workflow integriert Isolation-Lint",           test_workflow_includes_isolation_lint_step),
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
