"""Mock-Tests für Score-Konfidenz-Stufen (Stufe 1).

Reine Anzeige-Funktion (`compute_score_confidence`), kein Score-/Conviction-
Effekt. Trennung wird vom CI-Lint `scripts/lint_score_confidence_isolation.py`
erzwungen.

Tests:
  1. Alle 4 Stufen werden erreicht (robust / mittel / provisorisch / heuristisch)
     je nach Stichprobengröße
  2. Earliness-Stufe ist hartkodiert "mittel" (datenbelegt 13.05.2026, AUC 0.77)
  3. Monster erbt Setup-Stufe
  4. KI / Conviction / Exit-Druck immer "heuristisch"
  5. Edge: leeres backtest_history → setup landet in heuristisch
  6. computed_at ist ISO-UTC-String
  7. Persistenz-Schema: app_data.json["score_confidence"] enthält die
     Top-Level-Keys (setup/earliness/monster/ki/conviction/exit_pressure/computed_at)
  8. CI-Lint: aktueller Repo-State hat keine Konfidenz-Reader in
     Score-Berechnungs-Funktionen
  9. Source-Inspektion: Methodik-Panel-Block enthält {score_confidence_rows_html}-
     Placeholder
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# === Source-Extraktion =====================================================
# generate_report.py importiert yfinance beim Modul-Load. Wir extrahieren
# nur compute_score_confidence + _score_confidence_rows_html per
# Source-Slice.

src = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _extract(func_def: str) -> str:
    pat = rf"^def {re.escape(func_def)}\([\s\S]+?(?=^def\s|^class\s|^# ====)"
    m = re.search(pat, src, re.MULTILINE)
    assert m, f"{func_def} nicht in generate_report.py gefunden"
    return m.group(0)


helpers_src = (
    _extract("compute_score_confidence")
    + "\n"
    + _extract("_score_confidence_rows_html")
)


class _Log:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def debug(self, *a, **k): pass


ns: dict = {"log": _Log()}
exec(
    "from config import (\n"
    "    SCORE_CONFIDENCE_N_ROBUST,\n"
    "    SCORE_CONFIDENCE_N_MITTEL,\n"
    "    SCORE_CONFIDENCE_N_PROVISORISCH,\n"
    "    SCORE_CONFIDENCE_MAX_AGE_DAYS,\n"
    ")\n"
    "from datetime import datetime\n"
    "from zoneinfo import ZoneInfo\n"
    + helpers_src,
    ns,
)
compute_score_confidence    = ns["compute_score_confidence"]
_score_confidence_rows_html = ns["_score_confidence_rows_html"]


def _bh(n_with_returns: int) -> list[dict]:
    """Synthetisches backtest_history mit gegebener Anzahl gefüllter return_10d."""
    return [
        {"ticker": f"T{i}", "date": "01.01.2026",
         "return_10d": 5.0 if i < n_with_returns else None}
        for i in range(max(n_with_returns, 1))
    ]


# === 1 — Stufen-Mapping pro Stichprobengröße ===============================

def test_setup_robust_when_large_sample():
    """≥ 500 + AUC-Test → robust (Setup-Score hat has_auc=True)."""
    res = compute_score_confidence(_bh(600))
    assert res["setup"]["tier"] == "robust", res["setup"]
    assert res["setup"]["n"] == 600


def test_setup_mittel_50_to_500():
    """50 ≤ n < 500 + AUC → mittel."""
    res = compute_score_confidence(_bh(100))
    assert res["setup"]["tier"] == "mittel", res["setup"]


def test_setup_provisorisch_1_to_49():
    """1 ≤ n < 50 + AUC → provisorisch."""
    res = compute_score_confidence(_bh(10))
    assert res["setup"]["tier"] == "provisorisch", res["setup"]


def test_setup_heuristisch_when_empty():
    """0 Datenpunkte → heuristisch."""
    res = compute_score_confidence([])
    assert res["setup"]["tier"] == "heuristisch", res["setup"]
    assert res["setup"]["n"] == 0


# === 2 — Earliness ist hartkodiert "mittel" ================================

def test_earliness_always_mittel():
    """Earliness V2 Stufe ist heute hartkodiert auf 'mittel' mit n=78
    (Mann-Whitney-U 13.05.2026, AUC 0.77)."""
    res_full   = compute_score_confidence(_bh(2000))
    res_empty  = compute_score_confidence([])
    for r in (res_full, res_empty):
        assert r["earliness"]["tier"] == "mittel", r["earliness"]
        assert r["earliness"]["n"] == 78
        assert r["earliness"].get("auc") == 0.77


# === 3 — Monster erbt Setup ================================================

def test_monster_inherits_setup_tier():
    for n, expected in [(600, "robust"), (100, "mittel"),
                        (10, "provisorisch"), (0, "heuristisch")]:
        res = compute_score_confidence(_bh(n))
        assert res["monster"]["tier"] == res["setup"]["tier"] == expected, (
            f"n={n}: monster {res['monster']['tier']} vs setup {res['setup']['tier']}")


# === 4 — KI / Conviction / Exit_pressure immer heuristisch =================

def test_ki_conviction_exit_always_heuristisch():
    for bh in (_bh(5000), _bh(0)):
        res = compute_score_confidence(bh)
        for key in ("ki", "conviction", "exit_pressure"):
            assert res[key]["tier"] == "heuristisch", (
                f"{key} sollte heuristisch sein, got {res[key]['tier']}")
            assert res[key]["n"] == 0


# === 5 — Edge-Cases ========================================================

def test_none_backtest_history():
    res = compute_score_confidence(None)
    assert res["setup"]["tier"] == "heuristisch"
    assert res["setup"]["n"] == 0


def test_entries_without_return_10d():
    bh = [{"ticker": "T", "date": "01.01.2026", "return_10d": None}] * 1000
    res = compute_score_confidence(bh)
    assert res["setup"]["tier"] == "heuristisch", "0 mit Returns → heuristisch"


def test_computed_at_iso_utc():
    res = compute_score_confidence([])
    ts = res.get("computed_at")
    assert ts is not None
    # ISO-UTC-Format: YYYY-MM-DDTHH:MM:SSZ
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", ts), ts


# === 6 — Persistenz-Schema =================================================

def test_top_level_keys_complete():
    res = compute_score_confidence(_bh(100))
    expected = {"setup", "earliness", "monster", "ki", "conviction",
                "exit_pressure", "computed_at"}
    assert set(res.keys()) == expected, set(res.keys()) ^ expected


def test_entry_fields_have_note():
    res = compute_score_confidence(_bh(100))
    for key in ("setup", "earliness", "monster", "ki", "conviction",
                "exit_pressure"):
        assert "tier" in res[key], key
        assert "n" in res[key], key
        assert "note" in res[key] and res[key]["note"], (
            f"{key} hat keine 'note'")


# === 7 — HTML-Render-Helper ================================================

def test_html_rows_render_all_tiers():
    """4 Stufen-Emoji sollten in einem realistischen Render auftauchen."""
    res = compute_score_confidence(_bh(600))  # Setup→robust, Earliness→mittel,
                                                # KI/Conv/Exit→heuristisch
    rows_html, computed_at = _score_confidence_rows_html(res)
    assert "🟢 robust" in rows_html, rows_html
    assert "🟡 mittel" in rows_html, rows_html
    assert "🔴 heuristisch" in rows_html, rows_html
    # computed_at-Datum aus dem Dict übernommen
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


# === 8 — CI-Lint: keine Konfidenz-Reader in Berechnungs-Pfaden =============

def test_isolation_lint_passes():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "lint_score_confidence_isolation.py")],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        f"Isolation-Lint scheitert (Score-Konfidenz wird in einer "
        f"verbotenen Berechnungs-Funktion gelesen):\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}")


# === 9 — Methodik-Panel-Block-Source-Inspektion ============================

def test_methodology_panel_has_placeholder():
    """Der HTML-Block im Methodik-Panel referenziert den Placeholder."""
    assert "{score_confidence_rows_html}" in src, (
        "Placeholder {score_confidence_rows_html} fehlt im Methodik-Panel-HTML")
    assert "{score_confidence_computed_at}" in src, (
        "Placeholder {score_confidence_computed_at} fehlt")
    # Box-Header
    assert "Konfidenz der Scores" in src


def test_workflow_includes_isolation_lint_step():
    """daily-squeeze-report.yml ruft den Isolation-Lint vor generate auf."""
    yml = (ROOT / ".github" / "workflows" / "daily-squeeze-report.yml"
           ).read_text(encoding="utf-8")
    assert "lint_score_confidence_isolation.py" in yml, (
        "Workflow ruft den Isolation-Lint nicht auf")
    # Reihenfolge: Lint vor Generate
    idx_lint     = yml.find("lint_score_confidence_isolation.py")
    idx_generate = yml.find("Generate squeeze report")
    assert idx_lint < idx_generate, (
        "Isolation-Lint muss VOR dem Generate-Step laufen")


# === Runner =================================================================

def main() -> None:
    tests = [
        ("Setup: ≥ 500 + AUC → robust",                test_setup_robust_when_large_sample),
        ("Setup: 50 ≤ n < 500 → mittel",                test_setup_mittel_50_to_500),
        ("Setup: 1 ≤ n < 50 → provisorisch",            test_setup_provisorisch_1_to_49),
        ("Setup: 0 Datenpunkte → heuristisch",          test_setup_heuristisch_when_empty),
        ("Earliness immer 'mittel' (n=78, AUC 0.77)",   test_earliness_always_mittel),
        ("Monster erbt Setup-Stufe",                    test_monster_inherits_setup_tier),
        ("KI / Conviction / Exit immer heuristisch",    test_ki_conviction_exit_always_heuristisch),
        ("None-backtest_history graceful",              test_none_backtest_history),
        ("Einträge ohne return_10d zählen nicht",        test_entries_without_return_10d),
        ("computed_at ISO-UTC-Format",                  test_computed_at_iso_utc),
        ("Top-Level-Keys vollständig",                  test_top_level_keys_complete),
        ("Entry-Felder: tier/n/note vorhanden",          test_entry_fields_have_note),
        ("HTML-Render: alle 4 Stufen-Emojis",            test_html_rows_render_all_tiers),
        ("HTML-Render: leeres Dict → Hinweis-Zeile",     test_html_empty_confidence_returns_hint),
        ("HTML-Render: 6 Score-Labels vorhanden",        test_html_labels_present),
        ("Isolation-Lint: keine Konfidenz-Reader",       test_isolation_lint_passes),
        ("Methodik-Panel hat Placeholder",               test_methodology_panel_has_placeholder),
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
