"""Mock-Tests für die Paper-C-Anzeige (Easy-Entscheid 07.11.2026, rein Anzeige).

1. Karten-Zeile „Momentum 5T“: Wert LIVE aus dem Enrichment
   (``price`` gegen ``close_5td_before_entry``), fehlt ein Feld → „—“ (nie 0).
   Liest NIE ``entry_past_return_5d`` (Look-Ahead-Konvention).
2. ``PAPER_C_BADGE`` leer → keine Zeile (Rückweg).
3. Status-Farbe aus ``SCORE_STATUS_LABELS["paper_c"]`` — seit 12.11.2026
   BLAU (pending, Paper C grün → blau) in jeder Phase, derselbe Text ohne
   Beleg-Behauptung; außerhalb Postclose nur der WERT grau (Tooltip).
4. v1 == v2 (``_render_test``) mit Fixture-Stocks inkl. Momentum-Wert.
5. Konfidenz-Panel: Kopfzeile + Zeile „Momentum 5T (Paper C)“.
6. Position-Status: Hoch-seit-Einstieg-Zeile (JS), null-tolerant, Tooltip ohne Beleg.
7. Kein Score-/Filter-/Push-Pfad liest die neuen Helfer.

Kategorie A: deterministisch, keine Netzzugriffe (Stubs wie im Golden-Test).
"""
from __future__ import annotations

import importlib.util
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Golden-Harness wiederverwenden (Stubs, Fixtures, Fixed-Clock).
_spec = importlib.util.spec_from_file_location(
    "golden_harness", ROOT / "scripts" / "mock_test_outer_page_golden.py")
golden = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(golden)
gr = golden.gr

GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


def _fn_body(name: str) -> str:
    m = re.search(rf"^def {name}\(.*?(?=\n\n\ndef |\n\ndef )", GR_SRC, re.MULTILINE | re.DOTALL)
    assert m, name
    return m.group(0)


def test_live_value_from_enrichment():
    f = gr._momentum_5t_live
    check("110/100 → +10 %", abs(f({"price": 110.0, "close_5td_before_entry": 100.0}) - 10.0) < 1e-9)
    check("60/100 → −40 %", abs(f({"price": 60.0, "close_5td_before_entry": 100.0}) + 40.0) < 1e-9)
    for name, s in (("Nenner fehlt", {"price": 5.0}),
                    ("Nenner 0", {"price": 5.0, "close_5td_before_entry": 0.0}),
                    ("Nenner NaN", {"price": 5.0, "close_5td_before_entry": math.nan}),
                    ("Preis fehlt", {"close_5td_before_entry": 4.0}),
                    ("Preis bool", {"price": True, "close_5td_before_entry": 4.0})):
        check(f"{name} → None", f(s) is None)
    # Backtest-Feld wird ignoriert, auch wenn vorhanden.
    check("entry_past_return_5d ignoriert",
          f({"entry_past_return_5d": 99.0}) is None)
    body = _fn_body("_momentum_5t_live") + _fn_body("_momentum_5t_row_html")
    code = "\n".join(l for l in body.splitlines() if not l.strip().startswith(("#", '"', "'"))
                     and "``" not in l)
    check("Helfer liest close_5td_before_entry", 'get("close_5td_before_entry")' in body)
    check("Helfer liest nie entry_past_return_5d",
          'get("entry_past_return_5d")' not in code and '["entry_past_return_5d"]' not in code)
    check("kein Aufruf des Backtest-Helfers", "_compute_entry_past_return_5d(" not in GR_SRC)


NB = "\u00a0"


def _row(stock, phase):
    orig = gr._REPORT_RUN_PHASE
    try:
        gr._REPORT_RUN_PHASE = phase
        return gr._momentum_5t_row_html(stock)
    finally:
        gr._REPORT_RUN_PHASE = orig


TEXT = "höher = größere Spanne inkl. Einstiegstag · ab Einstieg: Test läuft, ~Dez."


def test_row_rendering():
    full = {"price": 110.0, "close_5td_before_entry": 100.0}
    row = _row(full, "postclose")
    check("Postclose: Wert +10,0 % (Komma, geschütztes Leerzeichen)",
          f'<span class="m5t-val">+10,0{NB}%</span>' in row, row)
    check("Postclose: Text ohne Beleg-Behauptung", TEXT in row, row)
    check("Postclose: Status-Farbe BLAU (pending)", "conf-kind-pending" in row)
    check("Postclose: kein Grün", "conf-kind-validated" not in row)
    for bad in ("belegt", "Gipfel", "AUC", "häufiger"):
        check(f"Postclose: kein „{bad}“", bad not in row, row)
    miss = _row({"price": 5.0}, "postclose")
    check("fehlender Wert → „—“", '<span class="m5t-val">—</span>' in miss, miss)
    check("fehlender Wert nie 0", "+0,0" not in miss and "0.0%" not in miss)
    check("keine Schwelle im Text", not re.search(r"ab \d|≥ \d+ ?% Momentum|Schwelle", row))
    # Phasen-Gate (09.11.2026) bleibt für den WERT: außerhalb Postclose grau.
    for phase in ("premarket", None, "", "intraday", "POSTCLOSE"):
        r = _row(full, phase)
        check(f"Phase {phase!r}: Wert grau + Tooltip",
              f'<span class="m5t-val m5t-unfinal" title="unfertiger Tag — gezählt wird '
              f'der Schlusskurs-Wert">+10,0{NB}%</span>' in r, r)
        check(f"Phase {phase!r}: derselbe Text + blauer Punkt, kein Grün",
              TEXT in r and "conf-kind-pending" in r and "conf-kind-validated" not in r, r)
    check("Premarket fehlender Wert → „—“ grau",
          '<span class="m5t-val m5t-unfinal" title=' in _row({"price": 5.0}, "premarket")
          and '>—</span>' in _row({"price": 5.0}, "premarket"))
    check("Default-Phase (nicht gesetzt) = unbekannt → grau",
          gr._REPORT_RUN_PHASE is None
          and "m5t-unfinal" in gr._momentum_5t_row_html(full))
    orig = gr.PAPER_C_BADGE
    try:
        gr.PAPER_C_BADGE = {}
        check("PAPER_C_BADGE leer → keine Zeile (postclose)", _row(full, "postclose") == "")
        check("PAPER_C_BADGE leer → keine Zeile (premarket)", _row(full, "premarket") == "")
    finally:
        gr.PAPER_C_BADGE = orig
    orig_l = gr.SCORE_STATUS_LABELS
    try:
        gr.SCORE_STATUS_LABELS = dict(orig_l, paper_c=dict(orig_l["paper_c"], status_kind="falsified"))
        check("Farbe folgt status_kind", "conf-kind-falsified" in _row(full, "postclose"))
    finally:
        gr.SCORE_STATUS_LABELS = orig_l
    body = _fn_body("_momentum_5t_row_html")
    check("Phase aus _REPORT_RUN_PHASE (keine eigene Uhrzeit-Logik)",
          "_REPORT_RUN_PHASE" in body and "datetime" not in body
          and "us_session_state" not in body and "now(" not in body)
    check("main() setzt _REPORT_RUN_PHASE aus _resolve_run_phase",
          re.search(r'run_phase\s*=\s*_resolve_run_phase\(\)[\s\S]{0,400}'
                    r'globals\(\)\["_REPORT_RUN_PHASE"\]\s*=\s*run_phase', GR_SRC) is not None)
    check("app_data run_phase = dieselbe Variable (Kopfzeilen-Quelle)",
          '"run_phase":       run_phase,' in GR_SRC
          and "_renderRunPhasePill(appData.run_phase" in GR_SRC)


def test_v1_equals_v2_and_cards():
    stocks = golden._fixture_stocks()
    stocks[0]["close_5td_before_entry"] = 4.25   # AAAA: Wert vorhanden
    # BBBB ohne Feld → „—“
    orig = {"datetime": gr.datetime, "lbh": gr._load_backtest_history,
            "lsh": gr._load_score_history, "pl": gr.health_check.provider_liveness}
    try:
        gr.datetime = golden._FixedDateTime
        gr._load_backtest_history = golden._fixture_backtest_history
        gr._load_score_history = golden._fixture_score_history
        gr.health_check.provider_liveness = golden._stub_provider_liveness
        try:
            gr._render_test(stocks, golden._FIXED_REPORT_DATE)
            check("v1 == v2 (_render_test)", True)
        except AssertionError as exc:
            check("v1 == v2 (_render_test)", False, str(exc))
        html_out = gr.generate_html_v1(stocks, golden._FIXED_REPORT_DATE)
    finally:
        gr.datetime = orig["datetime"]
        gr._load_backtest_history = orig["lbh"]
        gr._load_score_history = orig["lsh"]
        gr.health_check.provider_liveness = orig["pl"]
    expect = f"{(5.10 / 4.25 - 1) * 100:+.1f}".replace(".", ",") + NB + "%"
    unf = '<span class="m5t-val m5t-unfinal" title="unfertiger Tag — gezählt wird der Schlusskurs-Wert">'
    check(f"Top-10-Karte AAAA zeigt {expect} (grau, Phase unbekannt)",
          f'{unf}{expect}</span>' in html_out)
    check("Top-10-Karte BBBB zeigt „—“", f'{unf}—</span>' in html_out)
    wl = gr._wl_full_card_html(stocks[0])
    check("Watchlist-Drawer-Karte enthält die Zeile", f'{unf}{expect}</span>' in wl)
    orig_p = gr._REPORT_RUN_PHASE
    try:
        gr._REPORT_RUN_PHASE = "postclose"
        wl_pc = gr._wl_full_card_html(stocks[0])
    finally:
        gr._REPORT_RUN_PHASE = orig_p
    check("Watchlist-Drawer postclose: blau, kein Grün",
          f'<span class="m5t-val">{expect}</span>' in wl_pc and "conf-kind-pending" in wl_pc
          and "conf-kind-validated" not in wl_pc)


def test_panel_rows():
    rows, _ = gr._score_confidence_rows_html({"setup": {"n": 5, "data_tier": "klein"}})
    check("Panel-Kopfzeile Stand 12.11.2026",
          "Stand 12.11.2026: 4 Bestätigungstests, 1 formaler Beleg" in rows
          and "kein Beleg für Gewinn ab Einstieg" in rows)
    check("Panel-Zeile Momentum 5T (Paper C)", "Momentum 5T (Paper C)" in rows)
    check("Panel-Zeile blau", re.search(r"Momentum 5T \(Paper C\).*conf-kind-pending", rows) is not None)
    check("Panel: kein Grün", "conf-kind-validated" not in rows)
    check("Panel: Zahlen aus eval_results (AUC 0,61 [0,56–0,66], n=668)",
          "AUC 0,61 [0,56–0,66], n=668" in rows)
    check("Panel: Spanne inkl. Einstiegstag + kein Beleg ab Einstieg",
          "Spanne Tief→Hoch inkl. Einstiegstag" in rows and "kein Beleg für Gewinn ab Einstieg" in rows)
    check("Setup bleibt nicht grün",
          re.search(r"Setup-Score</span><span class=\"sb-pts\"></span><span class=\"sb-note\">"
                    r"<span class=\"conf-status-dot conf-kind-validated", rows) is None)


def test_position_peak_line_js():
    check("JS _psPeakLine vorhanden", "function _psPeakLine(pos)" in GR_SRC)
    check("liest peak_pnl_pct_since_entry + current_pnl_pct",
          "ex.peak_pnl_pct_since_entry" in GR_SRC and "ex.current_pnl_pct" in GR_SRC)
    check("Handelstage über _isNonTradingDay", "_isNonTradingDay(cur)" in GR_SRC)
    check("null-tolerant „—“", ": '—';" in GR_SRC)
    check("Tooltip-Text ohne Beleg-Behauptung",
          "Bester gemessener Stand ab deinem Einstiegskurs. Kein belegter Vorteil — "
          "handelbare Variante: Test läuft (~Dez.); Ausstiegsregel unbelegt." in GR_SRC
          and "Gipfel ist das belegte" not in GR_SRC)
    check("in buildPositionStatus eingebaut", "const peakLine = _psPeakLine(pos);" in GR_SRC
          and "${{peakLine}}" in GR_SRC)


def test_no_score_path_touch():
    for fn in ("score", "score_bonus", "_compute_sub_scores", "compute_conviction_score",
               "apply_conviction_scores", "_drivers_breakdown", "compute_exit_score"):
        m = re.search(rf"^def {fn}\(.*?(?=\n\ndef )", GR_SRC, re.MULTILINE | re.DOTALL)
        if not m:
            continue
        body = m.group(0)
        check(f"{fn} nutzt keine Paper-C-Anzeige",
              "_momentum_5t" not in body and "PAPER_C_BADGE" not in body)
    ki_src = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
    check("ki_agent unberührt", "_momentum_5t" not in ki_src and "PAPER_C_BADGE" not in ki_src)


def run_all() -> int:
    for t in (test_live_value_from_enrichment, test_row_rendering, test_v1_equals_v2_and_cards,
              test_panel_rows, test_position_peak_line_js, test_no_score_path_touch):
        print(t.__name__)
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Paper-C-Anzeige-Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle Paper-C-Anzeige-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
