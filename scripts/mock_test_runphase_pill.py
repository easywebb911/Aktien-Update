"""Mock-Tests für _renderRunPhasePill — Intraday-Disambiguation.

Diagnose 15.05.2026: Pill zeigte "Pre-Open-Vorschau" während US-Session
(17:29 UTC). Ursache: run_phase=premarket greift korrekt fuer
Backtest-Schutz, aber Label "Pre-Open-Vorschau" passt semantisch nur
fuer Pre-Open-Runs.

Fix: dritte Anzeige-Klasse via generated_at-Disambiguation:
  premarket + UTC ∈ [13:30, 20:00) → "Intraday-Snapshot"
  premarket + UTC außerhalb         → "Pre-Open-Vorschau"
  postclose                          → "Post-Close"

Tests:
  1. Source-Inspektion: _renderRunPhasePill nimmt 2 Parameter
  2. Source-Inspektion: alle 3 Label-Strings vorhanden
  3. Source-Inspektion: Aufrufer übergibt generatedAt
  4. Pythonische Replikation der 4 Cases (Pre-Open / Intraday /
     Spät-Intraday / Post-Close)
  5. Edge-Case: generatedAt fehlt → graceful fallback auf now
  6. CSS-Klasse: beide premarket-Varianten nutzen hdr-runphase-premarket
"""
from __future__ import annotations

import pathlib
import re
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _function_body(name: str) -> str:
    """Extrahiere _renderRunPhasePill-Body bis zum Anfang der nächsten
    Top-Level-Function-Deklaration (function …/window.… = function)."""
    pat = re.compile(rf"function {re.escape(name)}\([^)]*\)\s*\{{", re.MULTILINE)
    m = pat.search(SRC)
    assert m, f"{name} nicht gefunden"
    start = m.start()
    rest = SRC[m.end():]
    next_decl = re.search(
        r"^\s*(?:function\s+[A-Za-z_]|window\.[A-Za-z_]\w*\s*=)",
        rest, re.MULTILINE)
    end = m.end() + next_decl.start() if next_decl else len(SRC)
    return SRC[start:end]


# === 1 — Signatur & Source-Inspektion =====================================


def test_function_takes_two_parameters():
    body = _function_body("_renderRunPhasePill")
    assert "function _renderRunPhasePill(phase, generatedAt)" in body, (
        "_renderRunPhasePill sollte (phase, generatedAt) signieren")


def test_all_three_labels_present():
    body = _function_body("_renderRunPhasePill")
    assert "Pre-Open-Vorschau" in body
    assert "Intraday-Snapshot" in body, (
        "Neues Label 'Intraday-Snapshot' fehlt im Pill")
    assert "Post-Close" in body


def test_us_session_window_constants_in_logic():
    """Pille prüft UTC-Fenster 13:30–20:00 für Intraday-Klassifikation."""
    body = _function_body("_renderRunPhasePill")
    # UTC-Minuten-of-day-Berechnung
    assert "getUTCHours" in body and "getUTCMinutes" in body, (
        "UTC-Wallclock-Berechnung fehlt")
    # 13:30 = 13*60+30 = 810 min, 20:00 = 20*60 = 1200 min
    assert "13 * 60 + 30" in body, "US-Session-Start (13:30 UTC) fehlt"
    assert "20 * 60" in body, "US-Session-Ende (20:00 UTC) fehlt"


def test_caller_passes_generated_at():
    """_renderRunPhasePill-Aufrufer muss appData.generated_at übergeben."""
    pat = re.compile(
        r"_renderRunPhasePill\(\s*appData\.run_phase\s*,\s*appData\.generated_at\s*\)",
    )
    assert pat.search(SRC), (
        "Aufrufer übergibt appData.generated_at nicht — Intraday-"
        "Disambiguation funktioniert nicht")


def test_both_premarket_variants_use_same_css_class():
    """CSS-Klasse hdr-runphase-premarket muss in beiden premarket-Pfaden
    aktiv sein (gelb = Daten nicht final, in beiden Faellen)."""
    body = _function_body("_renderRunPhasePill")
    # Anzahl der "hdr-runphase-premarket"-add-Calls — sollte 1× sein
    # (gemeinsam fuer beide premarket-Varianten)
    n_premarket_add = body.count("classList.add('hdr-runphase-premarket')")
    assert n_premarket_add == 1, (
        f"hdr-runphase-premarket sollte 1x via classList.add gesetzt sein "
        f"(beide premarket-Varianten teilen es), gefunden {n_premarket_add}x")


def test_graceful_fallback_on_invalid_generated_at():
    """Bei fehlendem/ungueltigem generatedAt muss Code zur Jetzt-Zeit
    fallen (kein '(invalid date)'-Label)."""
    body = _function_body("_renderRunPhasePill")
    assert "new Date(generatedAt)" in body, (
        "generatedAt wird nicht in Date geparsed")
    # Fallback `new Date()` ohne Argument
    assert "new Date()" in body, (
        "Fallback auf jetzt fuer fehlendes generatedAt fehlt")
    # isNaN-Check
    assert "isNaN(t.getTime())" in body, (
        "isNaN-Check fuer invalid Date fehlt — '(invalid date)'-Label "
        "moeglich")


# === 2 — Pythonische Replikation der Label-Logik ==========================


def _label_for(phase: str, generated_at: datetime | None) -> str | None:
    """Replikation der _renderRunPhasePill-Logik in Python.
    Returnt das Label-Suffix oder None (Pill hidden)."""
    if phase == "premarket":
        if generated_at is None or generated_at.tzinfo is None:
            t = generated_at or datetime.now(timezone.utc)
        else:
            t = generated_at
        utc_min = t.hour * 60 + t.minute   # UTC-Minutes-of-day
        in_us = 13 * 60 + 30 <= utc_min < 20 * 60
        return " · Intraday-Snapshot" if in_us else " · Pre-Open-Vorschau"
    if phase == "postclose":
        return " · Post-Close"
    return None


def test_pre_open_run_at_1017_utc():
    """10:17 UTC (regulärer premarket-Cron, vor US-Open) → 'Pre-Open-Vorschau'."""
    t = datetime(2026, 5, 15, 10, 17, tzinfo=timezone.utc)
    assert _label_for("premarket", t) == " · Pre-Open-Vorschau"


def test_intraday_redeploy_at_1729_utc():
    """17:29 UTC (Re-deploy mitten in US-Session) → 'Intraday-Snapshot'."""
    t = datetime(2026, 5, 15, 17, 29, tzinfo=timezone.utc)
    assert _label_for("premarket", t) == " · Intraday-Snapshot"


def test_us_session_boundary_exactly_1330():
    """Genau 13:30 UTC zählt schon zur US-Session (≥-Schwelle)."""
    t = datetime(2026, 5, 15, 13, 30, tzinfo=timezone.utc)
    assert _label_for("premarket", t) == " · Intraday-Snapshot"


def test_us_session_boundary_just_before_1330():
    """13:29 UTC ist noch Pre-Open."""
    t = datetime(2026, 5, 15, 13, 29, tzinfo=timezone.utc)
    assert _label_for("premarket", t) == " · Pre-Open-Vorschau"


def test_us_session_boundary_exactly_2000():
    """Genau 20:00 UTC ist nicht mehr Intraday (< 20:00-Schwelle)."""
    t = datetime(2026, 5, 15, 20, 0, tzinfo=timezone.utc)
    assert _label_for("premarket", t) == " · Pre-Open-Vorschau"


def test_postclose_run_at_2117_utc():
    """21:17 UTC (regulärer postclose-Cron) → 'Post-Close'."""
    t = datetime(2026, 5, 15, 21, 17, tzinfo=timezone.utc)
    assert _label_for("postclose", t) == " · Post-Close"


def test_postclose_during_us_session_still_post_close():
    """Auch wenn postclose ungewöhnlich in US-Session käme — Label
    'Post-Close' bleibt (Override würde es ohnehin auf premarket forcen,
    aber Label-Logik ist generated_at-unabhängig für postclose)."""
    t = datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc)
    assert _label_for("postclose", t) == " · Post-Close"


def test_unknown_phase_hidden():
    """Unbekannte/leere phase → Pill hidden (None-Label-Repräsentation)."""
    t = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    assert _label_for("", t) is None
    assert _label_for("unknown", t) is None


def test_late_intraday_just_before_close():
    """19:59 UTC — last minute der US-Session → noch 'Intraday-Snapshot'."""
    t = datetime(2026, 5, 15, 19, 59, tzinfo=timezone.utc)
    assert _label_for("premarket", t) == " · Intraday-Snapshot"


def test_after_close_late_evening():
    """22:00 UTC (nach US-Close) + premarket → wieder Pre-Open
    (Override hätte normalerweise auf postclose geforced, aber falls
    nicht: Label-Logik fällt auf Pre-Open zurück)."""
    t = datetime(2026, 5, 15, 22, 0, tzinfo=timezone.utc)
    assert _label_for("premarket", t) == " · Pre-Open-Vorschau"


# === 3 — Backend-Unveraendert (Vorsichts-Prinzip) =========================


def test_resolve_run_phase_untouched():
    """Strikt: dieser PR aendert resolve_run_phase.py nicht."""
    path = ROOT / "scripts" / "resolve_run_phase.py"
    src = path.read_text(encoding="utf-8")
    assert "US_SESSION_START = time(13, 30)" in src
    assert "US_SESSION_END   = time(20, 0)" in src
    # Override-Logik intakt
    assert 'return "premarket", "us_session_override"' in src
    assert 'return "postclose", "post_close_override"' in src


def test_redeploy_workflow_run_phase_logic_untouched():
    path = ROOT / ".github" / "workflows" / "redeploy-on-source-change.yml"
    src = path.read_text(encoding="utf-8")
    assert 'if [ "$NOW_HHMM" -ge 1330 ] && [ "$NOW_HHMM" -lt 2000 ]; then' in src
    assert 'RUN_PHASE="premarket"' in src


def test_app_data_writes_generated_at():
    """_write_app_data_json muss generated_at schreiben — Pill-Disambiguation
    haengt davon ab."""
    assert '"generated_at":' in SRC
    pat = re.compile(
        r'"generated_at":\s*datetime\.now\(ZoneInfo\("UTC"\)\)'
        r'\.strftime\([^\)]+\)'
    )
    assert pat.search(SRC), "generated_at-Schreibe-Pattern nicht gefunden"


# === 4 — JS-Pflichtcheck =================================================


def test_no_unescaped_js_template_vars():
    hits = re.findall(r"\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}", SRC)
    assert not hits, f"Unescapte JS-Template-Vars: {hits[:5]}"


# === Runner ===============================================================


def main() -> None:
    tests = [
        # Source-Inspektion
        ("Funktion nimmt (phase, generatedAt)",          test_function_takes_two_parameters),
        ("Alle 3 Label-Strings vorhanden",                test_all_three_labels_present),
        ("US-Session-Konstanten 13:30/20:00 in Logik",    test_us_session_window_constants_in_logic),
        ("Aufrufer übergibt appData.generated_at",        test_caller_passes_generated_at),
        ("Beide premarket-Varianten gleiche CSS-Klasse",  test_both_premarket_variants_use_same_css_class),
        ("graceful fallback auf invalid generated_at",    test_graceful_fallback_on_invalid_generated_at),
        # Pythonische Replikation
        ("10:17 UTC premarket → Pre-Open-Vorschau",       test_pre_open_run_at_1017_utc),
        ("17:29 UTC premarket → Intraday-Snapshot",       test_intraday_redeploy_at_1729_utc),
        ("Boundary 13:30 UTC → Intraday (inkl)",          test_us_session_boundary_exactly_1330),
        ("Boundary 13:29 UTC → noch Pre-Open",             test_us_session_boundary_just_before_1330),
        ("Boundary 20:00 UTC → wieder Pre-Open (exkl)",    test_us_session_boundary_exactly_2000),
        ("21:17 UTC postclose → Post-Close",               test_postclose_run_at_2117_utc),
        ("postclose in US-Session bleibt Post-Close",      test_postclose_during_us_session_still_post_close),
        ("Unbekannte phase → Pill hidden",                  test_unknown_phase_hidden),
        ("19:59 UTC → noch Intraday-Snapshot",              test_late_intraday_just_before_close),
        ("22:00 UTC premarket → wieder Pre-Open",           test_after_close_late_evening),
        # Backend-Unveraendert
        ("resolve_run_phase.py unveraendert",              test_resolve_run_phase_untouched),
        ("redeploy-on-source-change.yml unveraendert",     test_redeploy_workflow_run_phase_logic_untouched),
        ("_write_app_data_json schreibt generated_at",     test_app_data_writes_generated_at),
        # Pflichtcheck
        ("Keine unescapten ${...} im f-String",           test_no_unescaped_js_template_vars),
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
