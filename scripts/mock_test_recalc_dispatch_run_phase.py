"""Mock-Tests für die Client-Side run_phase-Bestimmung im Recalculate-Dispatch.

Hintergrund: PR #132 hat ``workflow_dispatch.inputs.run_phase`` auf
``required: true`` gestellt (UX-Falle „postclose-Default während US-
Session" entschärft). Der Frontend-Recalculate-Button im iPhone sendete
aber kein ``inputs``-Feld → GitHub-API antwortete HTTP 422 und der
Workflow ließ sich gar nicht mehr manuell starten.

Fix in generate_report.py: ``_computeClientRunPhase()`` bestimmt die
Phase (seit 02.11.2026 aus US-Ostküstenzeit) und das Dispatch-Body sendet jetzt
``inputs: {run_phase: <phase>}``. Der Plausibilitäts-Override in
``scripts/resolve_run_phase.py`` bleibt als Safety-Net aktiv.

Spec-Cases (aus dem Auftrag):
  1. 14:00 UTC → premarket  (US-Session)
  2. 22:00 UTC → postclose  (nach Close)
  3. 13:29 UTC → postclose  (vor Open)
  4. 13:30 UTC → premarket  (genau Open — inklusiv)
  5. 20:00 UTC → postclose  (genau Close — exklusiv)

Zusatz:
  6. JS-Source enthält die Funktion und der Dispatch-Body sendet inputs

Ausführung: ``python scripts/mock_test_recalc_dispatch_run_phase.py``.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


sys.path.insert(0, str(ROOT))
from datetime import datetime, timezone  # noqa: E402
import trading_date  # noqa: E402


def _phase_for(hour: int, minute: int, *, month: int = 5, day: int = 13) -> str:
    """Pythonische Nachbildung der JS-Logik in _computeClientRunPhase().

    Seit 02.11.2026 aus US-Ostküstenzeit (EINE Quelle:
    ``trading_date.us_session_state``): Session (09:30–16:00 ET) →
    premarket, sonst postclose. Default-Datum 13.05.2026 = Sommerzeit
    (EDT, Grenzen 13:30/20:00 UTC); Winterfälle mit month=11, day=2
    (EST, Grenzen 14:30/21:00 UTC).
    """
    st = trading_date.us_session_state(
        datetime(2026, month, day, hour, minute, tzinfo=timezone.utc))
    return "premarket" if st == "open" else "postclose"


# === Spec-Cases (Sommerzeit, unverändert gültig) =============================

def test_14_00_utc_premarket():
    assert _phase_for(14, 0) == "premarket", "14:00 UTC sollte premarket sein"


def test_22_00_utc_postclose():
    assert _phase_for(22, 0) == "postclose", "22:00 UTC sollte postclose sein"


def test_13_29_utc_postclose_before_open():
    assert _phase_for(13, 29) == "postclose", (
        "13:29 UTC = 1 Minute vor US-Open → bleibt postclose")


def test_13_30_utc_premarket_at_open():
    assert _phase_for(13, 30) == "premarket", (
        "13:30 UTC = exakt US-Open → premarket (inklusiv)")


def test_20_00_utc_postclose_at_close():
    assert _phase_for(20, 0) == "postclose", (
        "20:00 UTC = exakt US-Close → postclose (exklusiv)")


# === Winterzeit (Fix 02.11.2026) =============================================

def test_winter_edges():
    w = dict(month=11, day=2)
    assert _phase_for(14, 29, **w) == "postclose", "Winter 14:29 UTC = 09:29 ET"
    assert _phase_for(14, 30, **w) == "premarket", "Winter 14:30 UTC = 09:30 ET"
    assert _phase_for(20, 30, **w) == "premarket", "Winter 20:30 UTC = 15:30 ET"
    assert _phase_for(20, 59, **w) == "premarket", "Winter 20:59 UTC = 15:59 ET"
    assert _phase_for(21, 0, **w) == "postclose", "Winter 21:00 UTC = 16:00 ET"
    assert _phase_for(20, 30) == "postclose", "Sommer 20:30 UTC = 16:30 ET"


# === Source-Inspektion ======================================================

def test_js_function_exists_in_generate_report():
    """_computeClientRunPhase muss im JS-Block der Datei existieren."""
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    assert "function _computeClientRunPhase()" in src, (
        "JS-Helper _computeClientRunPhase fehlt in generate_report.py")
    # Seit 02.11.2026: Grenzen über _usSessionStateET (US/Eastern), keine
    # festen UTC-Minuten (810/1200) mehr in der Funktion.
    i = src.index("function _computeClientRunPhase()")
    body = src[i:src.index("}}", i)]
    assert "_usSessionStateET(" in body, "_computeClientRunPhase nutzt _usSessionStateET nicht"
    assert "810" not in body and "1200" not in body and "getUTCHours" not in body, (
        "feste UTC-Grenzen noch in _computeClientRunPhase")
    assert "function _usSessionStateET(d)" in src and "America/New_York" in src


def test_dispatch_body_sends_inputs_run_phase():
    """Der Recalculate-Dispatch-Body muss inputs.run_phase enthalten."""
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    # Auf den Dispatch-Aufruf einschränken (zwischen dispatchWorkflow-Def
    # und dem nächsten triggerKiAgent), um den KI-Agent-Pfad nicht zu treffen.
    match = re.search(
        r"async function dispatchWorkflow\(token\).*?function _enableKiBtn",
        src, re.DOTALL)
    assert match is not None, "dispatchWorkflow-Block nicht gefunden"
    block = match.group(0)
    assert "inputs:" in block and "run_phase:" in block, (
        "dispatchWorkflow-Body sendet kein inputs.run_phase — HTTP 422 droht")
    assert "_computeClientRunPhase()" in block, (
        "dispatchWorkflow nutzt nicht _computeClientRunPhase()")


def test_ki_agent_dispatch_unchanged():
    """KI-Agent-Workflow hat keinen run_phase-Input → kein inputs-Feld nötig."""
    ki_yaml = (ROOT / ".github" / "workflows" / "ki_agent.yml").read_text(
        encoding="utf-8")
    # Falls der ki_agent.yml jemals run_phase bekommt, scheitert dieser Test
    # und der Frontend-Pfad muss synchron angepasst werden.
    assert "run_phase" not in ki_yaml, (
        "ki_agent.yml hat jetzt run_phase — dispatchKiWorkflow muss "
        "ebenfalls inputs senden, sonst HTTP 422")
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    match = re.search(
        r"async function dispatchKiWorkflow\(token\).*?function _kiAgentSuccess",
        src, re.DOTALL)
    assert match is not None, "dispatchKiWorkflow-Block nicht gefunden"
    block = match.group(0)
    # KI-Agent-Pfad bleibt OHNE inputs (kein run_phase im ki_agent.yml)
    assert "inputs:" not in block, (
        "dispatchKiWorkflow sendet inputs, aber ki_agent.yml definiert "
        "keine — entweder Workflow-Input ergänzen oder inputs hier raus")


# === Python-f-String-Safety =================================================

def test_no_unescaped_js_template_vars():
    """CLAUDE.md-Pflichtcheck: keine ${var} ohne {{ }}-Escape im f-String."""
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    hits = re.findall(r"\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}", src)
    assert not hits, (
        f"Unescapte JS-Template-Variablen im f-String gefunden: "
        f"{hits[:5]} (insgesamt {len(hits)})")


# === Runner =================================================================

def main() -> None:
    tests = [
        ("14:00 UTC → premarket",                       test_14_00_utc_premarket),
        ("22:00 UTC → postclose",                       test_22_00_utc_postclose),
        ("13:29 UTC → postclose (vor Open)",            test_13_29_utc_postclose_before_open),
        ("13:30 UTC → premarket (genau Open, inklusiv)", test_13_30_utc_premarket_at_open),
        ("20:00 UTC → postclose (genau Close, exklusiv)", test_20_00_utc_postclose_at_close),
        ("Winterzeit-Kanten 14:30/21:00 UTC",           test_winter_edges),
        ("_computeClientRunPhase existiert in JS",       test_js_function_exists_in_generate_report),
        ("Dispatch-Body sendet inputs.run_phase",         test_dispatch_body_sends_inputs_run_phase),
        ("KI-Agent-Dispatch unverändert (kein inputs)",   test_ki_agent_dispatch_unchanged),
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
