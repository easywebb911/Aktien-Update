#!/usr/bin/env python3
"""Mock-Test: Stand-Anzeige im Position-Status-Block (open_items
app-data-positions-staleness-ki-agent-tick, Easy-Entscheid 02.11.2026,
Variante A).

Prüft am Golden-HTML (deterministisch, kein Netz, kein Real-State):
  01 Helper ``_psAsofLabel`` existiert und wird in ``ps-head`` gerendert.
  02 Quelle ist ``last_daily_run_ts`` (Daily-Run-Schreibzeit der positions),
     NICHT ``generated_at`` (das überschreibt jeder ki_agent-Tick).
  03 Berlin-Zeitzone, fail-soft (try/catch, leerer String ohne Wert).
  04 Funktional (nur wenn ``node`` vorhanden): ISO-UTC → "Stand TT.MM., HH:MM"
     in Berlin-Zeit; ohne Wert / ungültig → ''.
  05 Keine Exit-/Score-Logik berührt: buildPositionStatus-Trigger-Schleife
     und exit_pressure-Zeile unverändert vorhanden.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden" / "report_outer_page.html"
_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def _extract_fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    depth, j, started = 0, i, False
    while j < len(src):
        c = src[j]
        if c == "{":
            depth += 1; started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return src[i:j + 1]
        j += 1
    raise ValueError(name)


def main() -> int:
    html = GOLDEN.read_text(encoding="utf-8")
    _check("01a _psAsofLabel definiert", "function _psAsofLabel(" in html)
    _check("01b ps-head rendert _psAsofLabel()",
           re.search(r'class="ps-head">📍 Position-Status \$\{_psAsofLabel\(\)\}</div>', html) is not None)
    fn = _extract_fn(html, "_psAsofLabel")
    _check("02a Quelle last_daily_run_ts", "last_daily_run_ts" in fn)
    _check("02b NICHT generated_at", "generated_at" not in fn)
    _check("03a Berlin-Zeitzone", "Europe/Berlin" in fn)
    _check("03b fail-soft try/catch", "try {" in fn and "catch (e)" in fn)
    _check("05 Exit-Druck-Zeile + Trigger-Schleife unverändert vorhanden",
           "Exit-Druck: ${v}/100" in html and "for (const name in triggers)" in html)

    node = shutil.which("node")
    if not node:
        print("  SKIP 04 funktional (kein node im PATH)")
    else:
        js = fn + r"""
        const out = [];
        globalThis.window = {_APP_DATA: {last_daily_run_ts: '2026-11-02T21:41:00Z'}};
        out.push(_psAsofLabel());
        globalThis.window = {_APP_DATA: {}};
        out.push(_psAsofLabel());
        globalThis.window = {_APP_DATA: {last_daily_run_ts: 'kaputt'}};
        out.push(_psAsofLabel());
        globalThis.window = {};
        out.push(_psAsofLabel());
        console.log(JSON.stringify(out));
        """
        res = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
        import json
        try:
            out = json.loads(res.stdout.strip())
        except Exception:
            out = None
        _check("04a UTC 21:41 → Berlin 22:41 (Winterzeit)",
               bool(out) and out[0] == '<span class="ps-asof">Stand 02.11., 22:41</span>',
               f"got {out!r} {res.stderr[:200]}")
        _check("04b ohne/ungültigen/fehlenden Wert → ''",
               bool(out) and out[1:] == ["", "", ""], f"got {out!r}")

    print()
    if _fails:
        print(f"✗ {len(_fails)} FAIL: {_fails}")
        return 1
    print("✓ Positions-Stand-Anzeige-Tests grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
