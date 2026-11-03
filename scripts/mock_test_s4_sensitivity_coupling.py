"""Mock-Test: §4-Sensitivität im selben Lauf wie die Hauptauswertung (03.11.2026).

Easy-Entscheid: Sobald §4 (Exit-B.1) auslöst, läuft ``s4_sensitivity_eval``
direkt nach der Hauptauswertung. Push und Digest nennen NUR das Gesamturteil
(Regel aus dem Protokolleintrag 02.11.2026, ``combine_verdict``) plus beide
Einzel-Verdikte. Scheitert die Sensitivität: kein Ergebnis-Push, sondern die
Zurückhalte-Zeile. Nur synthetische Fixtures, keine echten Renditen.

  01 Auslöser: genau EIN Exit-B.1-Push, Body nennt je Test Gesamturteil +
     „Haupt:“ + „Sensitivität:“; kein Push mit nur dem Hauptergebnis
  02 Gesamturteil = combine_verdict(Haupt, Sensitivität) je Test (aus den
     geschriebenen Dateien nachgerechnet)
  03 Sensitivitäts-Datei liegt neben eval_results.jsonl (Temp-Ordner), nie
     im Repo-Root
  04 Digest-Zeile zeigt das Gesamturteil
  05 Folgetag (gesperrt): kein neuer Push, Zeile zeigt weiter das Gesamturteil
  06 Sensitivität wirft → Push nur mit Zurückhalte-Text, keine Verdikte;
     Digest-Zeile = Zurückhalte-Zeile; keine Sensitivitäts-Datei
  07 Folgetag nach Fehlschlag: weiter Zurückhalte-Zeile, kein Hauptergebnis
  08 „nicht prüfbar“ (Entry-Tag nach FROZEN_UNTIL außerhalb des Gap-Log-
     Fensters) → ebenfalls zurückgehalten
  09 Verfahren unverändert: Sensitivität ruft die eingefrorene
     evaluate_exit_b1_family; freeze_eval.py nicht angefasst (Quelle)
  10 Schalter: EVAL_AUTORUN_ENABLED True; keine Pause-Zeile
  11 Digest-Workflow sichert eval_results_sensitivity.jsonl
"""
from __future__ import annotations

import importlib.util
import json
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
import s4_sensitivity_eval as s4  # noqa: E402

_fails: list[str] = []
NOW = datetime(2026, 10, 31, 21, 0, tzinfo=timezone.utc)
VERDICT_WORDS = ("Beleg", "bedingt", "Unklar")


def _check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        _fails.append(name)


def _rows(n=260, seed=11, dates=("05.10.2026", "01.10.2026", "14.10.2026")):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        out.append({"ticker": f"T{i}", "date": dates[i % len(dates)], "score": 80.0,
                    "provenance": "forward",
                    "return_5d": 4.0 + rng.gauss(0, 1), "return_10d": 1.0 + rng.gauss(0, 1),
                    "return_3d": 3.0 + rng.gauss(0, 1),
                    "market_regime": ("bull", "bear", "neutral")[i % 3]})
    return out


def _digest(d: pathlib.Path, rows=None, *, now=NOW):
    spec = importlib.util.spec_from_file_location(
        "_dgst_s4_coupling", str(ROOT / "scripts" / "health_check_digest.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    export = d / "export.jsonl"
    if rows is not None:
        export.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    log_path = d / "health_check_log.jsonl"
    log_path.write_text(json.dumps({"run_ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "run_phase": "postclose", "schema_v": 1,
                                    "state_fails": [], "provider_fails": []}) + "\n",
                        encoding="utf-8")
    mod.hc.MATURED_EXPORT_FILE = str(export)
    mod.hc.LOG_FILE = str(log_path)
    mod.EVAL_RESULTS_FILE = str(d / "eval_results.jsonl")
    mod.DIGEST_STATE_FILE = d / "state.json"
    mod.APP_DATA_FILE_FOR_WATCHDOG = d / "app_data.json"
    mod.WATCHLIST_PERSONAL_FILE_FOR_WATCHDOG = d / "watchlist_personal.json"
    mod.POSITION_WATCHLIST_STATE_FILE = d / "position_watchlist_state.json"
    mod.NTFY_TOPIC = "test-topic"
    sent: list[tuple] = []
    mod._ntfy_send = lambda title, body, *a, **k: sent.append((title, body)) or True
    captured = {}
    orig_fmt = mod.hc.format_digest_body

    def _spy_fmt(*a, **k):
        res = orig_fmt(*a, **k)
        captured["body"] = res[0]
        return res
    mod.hc.format_digest_body = _spy_fmt
    try:
        rc = mod.main(now_ts=now, force=True)
    finally:
        mod.hc.format_digest_body = orig_fmt
    return rc, sent, captured.get("body", "")


def _exit_pushes(sent):
    return [b for t, b in sent if "Exit-B.1" in t]


def _read(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def test_01_05_trigger_and_lock():
    d = pathlib.Path(tempfile.mkdtemp())
    before_root = set(p.name for p in ROOT.iterdir())
    rc, sent, body = _digest(d, _rows())
    pushes = _exit_pushes(sent)
    _check("01 Digest rc 0", rc == 0, str(rc))
    _check("01 genau EIN Exit-B.1-Push", len(pushes) == 1, str(len(pushes)))
    pb = pushes[0] if pushes else ""
    _check("01 Push nennt je Test Gesamturteil + Haupt + Sensitivität",
           all(f"{t}:" in pb for t in s4.EXIT_B1_TEST_IDS)
           and pb.count("(Haupt:") == 2 and pb.count("Sensitivität:") == 2, pb)
    sens = _read(d / s4.SENS_RESULTS_FILE)
    main = {r["test_id"]: r["verdict"] for r in _read(d / "eval_results.jsonl")
            if r.get("family") == "exit_b1"}
    ok = len(sens) == 2 and all(
        r["main_verdict"] == main[r["test_id"]]
        and r["combined_verdict"] == s4.combine_verdict(main[r["test_id"]], r["verdict"])
        and f"{r['test_id']}: {r['combined_verdict']} (Haupt: {r['main_verdict']}, "
            f"Sensitivität: {r['verdict']})" in pb
        for r in sens)
    _check("02 Gesamturteil = combine_verdict(Haupt, Sensitivität), so im Push", ok)
    _check("02 Sensitivität hat Records ausgeschlossen (01.10. steht in der Liste)",
           sens and sens[0]["sensitivity"]["n_rows_kept"] < sens[0]["sensitivity"]["n_rows_in"])
    _check("03 Sensitivitäts-Datei im Temp-Ordner, nicht im Repo-Root",
           (d / s4.SENS_RESULTS_FILE).exists()
           and set(p.name for p in ROOT.iterdir()) == before_root)
    _check("04 Digest-Zeile zeigt Gesamturteil",
           "Exit-B.1 (§4) ausgewertet:" in body and "(Haupt:" in body, body[-500:])
    rc, sent2, body2 = _digest(d, None, now=NOW.replace(day=31, hour=22))
    _check("05 Folgetag: kein neuer Exit-B.1-Push", _exit_pushes(sent2) == [])
    _check("05 Folgetag: Zeile zeigt weiter das Gesamturteil",
           "Exit-B.1 (§4) ausgewertet:" in body2 and "(Haupt:" in body2, body2[-500:])


def test_06_07_failure():
    d = pathlib.Path(tempfile.mkdtemp())
    orig = s4.run_sensitivity

    def _boom(*a, **k):
        raise RuntimeError("Sensitivität kaputt")
    s4.run_sensitivity = _boom
    try:
        rc, sent, body = _digest(d, _rows())
    finally:
        s4.run_sensitivity = orig
    pushes = _exit_pushes(sent)
    _check("06 genau EIN Exit-B.1-Push, nur Zurückhalte-Text",
           len(pushes) == 1 and pushes[0] == s4.HOLD_BACK_LINE, str(pushes))
    _check("06 kein Push enthält ein Verdikt-Wort zu §4",
           not any(w in b for b in pushes for w in VERDICT_WORDS))
    _check("06 Digest zeigt die Zurückhalte-Zeile, kein §4-Ergebnis",
           s4.HOLD_BACK_LINE in body and "Exit-B.1 (§4) ausgewertet" not in body, body[-500:])
    _check("06 keine Sensitivitäts-Datei", not (d / s4.SENS_RESULTS_FILE).exists())
    _check("06 Hauptergebnis gesperrt gespeichert (Lock)", (d / "eval_results.jsonl").exists())
    rc, sent2, body2 = _digest(d, None, now=NOW.replace(hour=22))
    _check("07 Folgetag: weiter Zurückhalte-Zeile, kein Ergebnis-Push",
           s4.HOLD_BACK_LINE in body2 and _exit_pushes(sent2) == []
           and "Exit-B.1 (§4) ausgewertet" not in body2, body2[-500:])


def test_08_not_checkable():
    d = pathlib.Path(tempfile.mkdtemp())
    later = datetime(2026, 12, 20, 21, 0, tzinfo=timezone.utc)
    # 200 Zeilen nach FROZEN_UNTIL (Setup-Edge bleibt < 250, löst nicht aus)
    # + 60 frühe Zeilen → §4 n=260; Auswertung am 20.12. → Gap-Log-Fenster vorbei.
    rows = _rows(n=200, dates=("02.11.2026", "03.11.2026")) + _rows(n=60, seed=5, dates=("05.10.2026",))
    for i, r in enumerate(rows):
        r["ticker"] = f"X{i}"
    rc, sent, body = _digest(d, rows, now=later)
    pushes = _exit_pushes(sent)
    _check("08 nicht prüfbar → zurückgehalten",
           len(pushes) == 1 and pushes[0] == s4.HOLD_BACK_LINE and s4.HOLD_BACK_LINE in body,
           str(pushes))


def test_09_10_11_static():
    src = (ROOT / "scripts" / "s4_sensitivity_eval.py").read_text(encoding="utf-8")
    _check("09 Sensitivität nutzt die eingefrorene evaluate_exit_b1_family",
           "fe.evaluate_exit_b1_family(kept, now=now)" in src)
    dg = (ROOT / "scripts" / "health_check_digest.py").read_text(encoding="utf-8")
    _check("09 Digest übergibt denselben Zeitpunkt (now_ts) an die Sensitivität",
           "now=now_ts)" in dg and "sensitivity_for_trigger(rows, main_verdicts" in dg)
    _check("10 EVAL_AUTORUN_ENABLED ist True", config.EVAL_AUTORUN_ENABLED is True)
    d = pathlib.Path(tempfile.mkdtemp())
    rc, sent, body = _digest(d, _rows(n=10))
    _check("10 keine Pause-Zeile im Digest", "⏸" not in body)
    wf = (ROOT / ".github" / "workflows" / "health_check_digest.yml").read_text(encoding="utf-8")
    _check("11 Digest-Workflow sichert eval_results_sensitivity.jsonl",
           "git add eval_results_sensitivity.jsonl" in wf)


def main() -> int:
    for t in (test_01_05_trigger_and_lock, test_06_07_failure, test_08_not_checkable,
              test_09_10_11_static):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            _check(f"{t.__name__} ohne Exception", False, f"{type(exc).__name__}: {exc}")
    print()
    if _fails:
        print(f"{len(_fails)} FAIL")
        return 1
    print("Alle s4_sensitivity_coupling-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
