#!/usr/bin/env python3
"""Mock-Test: Freeze-Auto-Lauf pausiert (Easy-Entscheid 02.11.2026).

Anlass: return_3d/5d/10d können aus dem laufenden Handelstag stammen —
bis zur Rendite-Diagnose darf KEIN Freeze-Ergebnis erzeugt oder gelesen
werden. Deterministisch, ohne Netz (CI-Stubs aus dem Golden-Test).

  01 config: seit 03.11.2026 wieder True (Wiederaufnahme); Pause-Grund
     bleibt als Mechanik erhalten. Die Pause-Tests unten setzen False lokal.
  02 Digest-main() mit Auslöser ERREICHT (n>=250 in allen drei Familien):
     freeze_eval wird nicht aufgerufen, kein eval_results.jsonl entsteht,
     keine Freeze-Push-Nachricht
  03 Digest-Body: Pause-Zeile vorhanden UND alle drei Zähler-Zeilen laufen
     weiter (n sichtbar, kein „ausgewertet")
  04 Pause-Zeile auch dann, wenn die Zähler-Berechnung scheitert
  05 Gegenprobe: mit True wird bei derselben Fixture die Auswertungs-
     Funktion aufgerufen (der Test prüft also wirklich den Schalter)
  06 s4_sensitivity_eval.main() rechnet bei Pause nicht und schreibt nichts
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import random
import sys
import tempfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from mock_test_outer_page_golden import gr  # noqa: E402,F401  (Heavy-Dep-Stubs)

import config  # noqa: E402

_fails: list[str] = []
NOW = datetime(2026, 11, 3, 8, 47, tzinfo=timezone.utc)


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        _fails.append(name)


def _rows(n: int = 320) -> list[dict]:
    """Export-Zeilen, die ALLE drei Populationen über 250 heben:
    forward + score>=70 (§4), Eintritt ab 12.10.2026 mit ki_signal_score
    und conviction_score (Setup-Edge/Conviction + KI-Score)."""
    rng = random.Random(7)
    out = []
    for i in range(n):
        day = 12 + (i % 15)
        out.append({
            "ticker": f"T{i}", "date": f"{day:02d}.10.2026", "score": 80.0,
            "provenance": "forward", "score_normalization_version": 2,
            "ki_signal_score": rng.uniform(0, 100), "ki_signal_ts": "2026-10-12T12:00:00+00:00",
            "conviction_score": rng.uniform(0, 100),
            "return_3d": rng.gauss(1, 3), "return_5d": rng.gauss(2, 3),
            "return_10d": rng.gauss(1, 3), "market_regime": ("bull", "bear", "neutral")[i % 3],
        })
    return out


def _load_digest():
    spec = importlib.util.spec_from_file_location(
        "_dgst_pause_test", str(ROOT / "scripts" / "health_check_digest.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_digest(enabled: bool, *, break_counters: bool = False):
    mod = _load_digest()
    d = pathlib.Path(tempfile.mkdtemp())
    export = d / "export.jsonl"
    export.write_text("".join(json.dumps(r) + "\n" for r in _rows()), encoding="utf-8")
    results = d / "eval_results.jsonl"
    mod.hc.MATURED_EXPORT_FILE = str(export)
    mod.EVAL_RESULTS_FILE = str(results)
    mod.DIGEST_STATE_FILE = d / "state.json"
    mod.EVAL_AUTORUN_ENABLED = enabled
    calls = {"run": 0, "push": []}
    captured = {}
    sys.modules.pop("freeze_eval", None)
    import freeze_eval as fe_real
    orig_run = fe_real.run_due_evaluations

    def _spy_run(*a, **k):
        calls["run"] += 1
        return orig_run(*a, **k)
    fe_real.run_due_evaluations = _spy_run
    orig_fmt = mod.hc.format_digest_body

    def _spy_fmt(*a, **k):
        res = orig_fmt(*a, **k)
        captured["body"] = res[0]
        return res
    mod.hc.format_digest_body = _spy_fmt
    mod._ntfy_send = lambda title, *a, **k: calls["push"].append(title) or True
    orig_count = mod.hc._count_setup_edge_freeze_population
    if break_counters:
        def _boom(*a, **k):
            raise RuntimeError("Zähler kaputt")
        mod.hc._count_setup_edge_freeze_population = _boom
    try:
        rc = mod.main(now_ts=NOW, dry_run=True)
    finally:
        fe_real.run_due_evaluations = orig_run
        mod.hc.format_digest_body = orig_fmt
        mod.hc._count_setup_edge_freeze_population = orig_count
    return rc, calls, captured.get("body", ""), results


def test_01_config():
    _check("01 EVAL_AUTORUN_ENABLED is True (wieder aktiv seit 03.11.2026)",
           config.EVAL_AUTORUN_ENABLED is True)
    _check("01 Pause-Grund gesetzt", config.EVAL_AUTORUN_PAUSE_REASON == "Rendite-Diagnose")


def test_02_03_paused_with_trigger_reached():
    rc, calls, body, results = _run_digest(False)
    _check("02 Digest läuft durch", rc == 0, str(rc))
    _check("02 freeze_eval.run_due_evaluations NICHT aufgerufen", calls["run"] == 0, str(calls))
    _check("02 kein eval_results.jsonl", not results.exists())
    _check("02 keine Freeze-Push-Nachricht",
           not any("Freeze-Auswertung" in t for t in calls["push"]), str(calls["push"]))
    _check("03 Pause-Zeile im Body",
           "⏸ Freeze-Auto-Lauf pausiert (Grund: Rendite-Diagnose)" in body, body[-600:])
    for label in ("Setup-Edge/Conviction:", "KI-Score:", "Exit-B.1 (§4):"):
        _check(f"03 Zähler-Zeile läuft weiter ({label})", f"🧪 {label} n = " in body, body[-600:])
    _check("03 nirgends „ausgewertet“", "ausgewertet:" not in body)


def test_04_pause_line_survives_counter_crash():
    rc, calls, body, results = _run_digest(False, break_counters=True)
    _check("04 Pause-Zeile trotz Zähler-Fehler", "⏸ Freeze-Auto-Lauf pausiert" in body, body[-400:])
    _check("04 auch dann keine Auswertung", calls["run"] == 0 and not results.exists())


def test_05_gegenprobe_true_would_evaluate():
    rc, calls, body, results = _run_digest(True)
    # Belegt nur, dass der SCHALTER das Tor ist: mit True wird die
    # Auswertungs-Funktion erreicht. Ob sie inhaltlich korrekt auswertet,
    # prüfen mock_test_freeze_eval_autorun.py / mock_test_exit_b1_autorun.py.
    _check("05 mit True wird die Auswertung aufgerufen (Schalter ist das Tor)",
           calls["run"] == 1, str(calls))
    _check("05 mit True keine Pause-Zeile", "⏸" not in body)


def test_06_s4_sensitivity_paused():
    import s4_sensitivity_eval as s4
    before = set(os.listdir(ROOT))
    orig = config.EVAL_AUTORUN_ENABLED
    config.EVAL_AUTORUN_ENABLED = False   # Pause-Verhalten prüfen (Produktion: True)
    try:
        rc = s4.main([])
    finally:
        config.EVAL_AUTORUN_ENABLED = orig
    after = set(os.listdir(ROOT))
    _check("06 s4_sensitivity_eval.main() → 3 (pausiert)", rc == 3, str(rc))
    _check("06 keine neue Datei im Repo", after == before, str(after - before))


def main() -> int:
    for t in (test_01_config, test_02_03_paused_with_trigger_reached,
              test_04_pause_line_survives_counter_crash, test_05_gegenprobe_true_would_evaluate,
              test_06_s4_sensitivity_paused):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            _check(f"{t.__name__} ohne Exception", False, f"{type(exc).__name__}: {exc}")
    print()
    if _fails:
        print(f"{len(_fails)} FAIL")
        return 1
    print("Alle freeze_autorun_pause-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
