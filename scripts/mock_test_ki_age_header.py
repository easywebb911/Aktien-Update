#!/usr/bin/env python3
"""Mock-Test: Alters-Anzeige des KI-Agent-Stands im App-Kopf (02.11.2026).

Easy-Entscheid 02.11.2026 (Stillstands-Diagnose Option b): „· KI HH:MM"
bekommt Alter, Farbe und Datum (wenn nicht heute) — im Browser berechnet.
REIN ANZEIGE. Deterministisch: festes "jetzt" (nowMs injiziert), Berlin-Zeit
fest im Helper, kein Netz, kein Real-State. Läuft auf stdlib (node optional).

  01 Konstanten in config.py (12 h / 24 h) und als JS-Const verdrahtet
  02 Anker = agent_signals.updated, NICHT app_data.generated_at
  03 fehlender Zeitstempel / Fetch-Fehler → ehrlicher Hinweis, nicht versteckt
  04 Farbklassen des Staleness-Banners wiederverwendet (kein zweites System)
  05 ECHTES JS per node: 2 h neutral, 13 h gelb, 25 h rot + Datum,
     Vortag frisch → Datum sichtbar, fehlend/ungültig → „unbekannt",
     Grenzen 11,9 h / 12 h / 24 h, Zukunfts-Zeitstempel → neutral, 49 h → „2 Tage"
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
CFG = (ROOT / "config.py").read_text(encoding="utf-8")

_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        _fails.append(name)


def _fn_block(name: str, end_marker: str) -> str:
    i = SRC.index(f"function {name}(")
    j = SRC.index(end_marker, i)
    return SRC[i:j]


def test_01_constants():
    _check("01 KI_AGENT_AGE_WARN_HOURS = 12 in config.py",
           re.search(r"^KI_AGENT_AGE_WARN_HOURS\s*=\s*12\b", CFG, re.M) is not None)
    _check("01 KI_AGENT_AGE_STALE_HOURS = 24 in config.py",
           re.search(r"^KI_AGENT_AGE_STALE_HOURS\s*=\s*24\b", CFG, re.M) is not None)
    _check("01 Context reicht config-Werte durch",
           '"ki_age_warn_h":  KI_AGENT_AGE_WARN_HOURS' in SRC
           and '"ki_age_stale_h": KI_AGENT_AGE_STALE_HOURS' in SRC)
    _check("01 JS-Const aus Context",
           "const _KI_AGE_WARN_H     = {ki_age_warn_h};" in SRC
           and "const _KI_AGE_STALE_H    = {ki_age_stale_h};" in SRC)


def test_02_anchor():
    i = SRC.index("function renderAgentSignals(data)")
    body = SRC[i:i + 4000]
    _check("02 Kopf-Anzeige liest data.updated", "_renderKiAge(data.updated);" in body)
    _check("02 nicht generated_at", "_renderKiAge(appData.generated_at" not in SRC
           and "_renderKiAge(data.generated_at" not in SRC)
    _check("02 alte Inline-Uhrzeit ohne Alter entfernt",
           "kiEl.textContent = ' · KI ' + kiStr;" not in SRC)


def test_03_missing_honest():
    fn = _fn_block("_kiAgeInfo", "\nfunction _renderKiAge(")
    _check("03 fehlend → „KI-Stand unbekannt“", "' · KI-Stand unbekannt'" in fn)
    rk = _fn_block("_renderKiAge", "\n}}\n")
    _check("03 Anzeige wird nie versteckt", "el.hidden = false;" in rk and "el.hidden = true" not in rk)
    _check("03 Fetch-Fehler → Hinweis", "if (typeof _renderKiAge === 'function') _renderKiAge(null);" in SRC)


def test_04_reuse_classes():
    fn = _fn_block("_kiAgeInfo", "\nfunction _renderKiAge(")
    _check("04 nutzt hdr-staleness-delayed/-stale",
           "'hdr-staleness-delayed'" in fn and "'hdr-staleness-stale'" in fn)
    _check("04 keine neue CSS-Klasse für das Alter", "hdr-kiage" not in SRC)


def _js_function() -> str:
    fn = _fn_block("_kiAgeInfo", "\nfunction _renderKiAge(")
    return fn.replace("{{", "{").replace("}}", "}")


def test_05_node():
    node = shutil.which("node")
    if not node:
        print("     (node nicht vorhanden — Funktionstest übersprungen)")
        return
    now = "2026-11-02T19:00:00Z"            # 20:00 Berlin (Winterzeit)
    after_midnight = "2026-11-03T01:00:00Z"  # 02:00 Berlin
    cases = [
        ("2 h → neutral", "2026-11-02T17:00:00Z", now, " · KI 18:00", ""),
        ("13 h → gelb", "2026-11-02T06:00:00Z", now, " · KI 07:00 (13 h alt)", "hdr-staleness-delayed"),
        ("25 h → rot + Datum", "2026-11-01T18:00:00Z", now, " · KI 01.11. 19:00 (1 Tag alt)", "hdr-staleness-stale"),
        ("49 h → 2 Tage", "2026-10-31T18:00:00Z", now, " · KI 31.10. 19:00 (2 Tage alt)", "hdr-staleness-stale"),
        ("Vortag frisch → Datum sichtbar", "2026-11-02T22:00:00Z", after_midnight, " · KI 02.11. 23:00", ""),
        ("11,9 h → neutral", "2026-11-02T07:06:00Z", now, " · KI 08:06", ""),
        ("genau 12 h → gelb", "2026-11-02T07:00:00Z", now, " · KI 08:00 (12 h alt)", "hdr-staleness-delayed"),
        ("genau 24 h → rot", "2026-11-01T19:00:00Z", now, " · KI 01.11. 20:00 (1 Tag alt)", "hdr-staleness-stale"),
        ("Zukunft (Uhr-Drift) → neutral", "2026-11-02T19:30:00Z", now, " · KI 20:30", ""),
        ("Berlin-Offset aus ISO", "2026-11-02T07:04:00.727373+01:00", now, " · KI 07:04 (12 h alt)", "hdr-staleness-delayed"),
        ("fehlend → unbekannt", None, now, " · KI-Stand unbekannt", "hdr-staleness-delayed"),
        ("leer → unbekannt", "", now, " · KI-Stand unbekannt", "hdr-staleness-delayed"),
        ("ungültig → unbekannt", "kaputt", now, " · KI-Stand unbekannt", "hdr-staleness-delayed"),
    ]
    payload = [[c[1], c[2]] for c in cases]
    code = ("const _KI_AGE_WARN_H = 12; const _KI_AGE_STALE_H = 24;\n" + _js_function() + "\n"
            + "const cs=" + json.dumps(payload) + ";\n"
            + "console.log(JSON.stringify(cs.map(([u,n])=>_kiAgeInfo(u, Date.parse(n)))));")
    out = subprocess.run([node, "-e", code], capture_output=True, text=True)
    if out.returncode != 0:
        _check("05 node läuft", False, out.stderr[-400:])
        return
    got = json.loads(out.stdout)
    for (label, _u, _n, exp_text, exp_cls), g in zip(cases, got):
        _check(f"05 {label}", g == {"text": exp_text, "cls": exp_cls}, repr(g))


def main() -> int:
    for t in (test_01_constants, test_02_anchor, test_03_missing_honest,
              test_04_reuse_classes, test_05_node):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            _check(f"{t.__name__} ohne Exception", False, f"{type(exc).__name__}: {exc}")
    print()
    if _fails:
        print(f"{len(_fails)} FAIL")
        return 1
    print("Alle ki_age_header-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
