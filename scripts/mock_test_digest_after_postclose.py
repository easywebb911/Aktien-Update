#!/usr/bin/env python3
"""Mock-Test: Digest-Anstoß nach dem Postclose (Easy-Entscheid 17.11.2026).

  1  Digest-Tag beginnt um 21:00 UTC (Postclose-Ende vor/nach Mitternacht →
     gleicher Digest-Tag; Rückfall-Zeitplan am Folgetag sendet nicht doppelt)
  2  Postclose fehlgeschlagen/abgebrochen → crit-Zeile, ⚠️-Titel; Erfolg → nichts
  3  unbekannte/gefährliche Werte werden nicht übernommen
  4  übersprungener Lauf (heute schon gesendet) hält last_successful_run frisch
  5  Ablauf Anstoß (Postclose) → Rückfall-Zeitplan am selben Digest-Tag: genau
     ein Versand
  6  Workflows: Anstoß mit always(), nur Postclose, Werte über env; Digest mit
     concurrency, Inputs, Zeitplan bleibt
  7  gleiche Eingabe → gleiche Nachricht
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
from datetime import datetime, timezone
from unittest import mock

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

FAILS: list[str] = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def _dg():
    spec = importlib.util.spec_from_file_location(
        "health_check_digest_ap", ROOT / "scripts" / "health_check_digest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def U(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


dg = _dg()

# 1 Digest-Tag
check(dg.digest_day(U(2026, 11, 17, 22, 20)) == "2026-11-18", "22:20 UTC → Folgetag")
check(dg.digest_day(U(2026, 11, 18, 4, 9)) == "2026-11-18", "04:09 UTC → gleicher Tag")
check(dg.digest_day(U(2026, 11, 18, 18, 53)) == "2026-11-18", "18:53 UTC (Rückfall spät) → gleicher Tag")
check(dg.digest_day(U(2026, 11, 18, 20, 59)) == "2026-11-18", "20:59 UTC → gleicher Tag")
check(dg.digest_day(U(2026, 11, 18, 21, 0)) == "2026-11-19", "21:00 UTC → Folgetag (Grenze)")

# 2/3 Upstream
f = dg.upstream_fail("failure", "44015119805")
check(f == {"id": "POSTCLOSE", "severity": "crit", "count": 1,
            "detail": "Postclose-Lauf fehlgeschlagen (Run 44015119805) — Digest per Anstoß gesendet"},
      f"failure → crit: {f}")
check(dg.upstream_fail("cancelled", "1")["detail"].startswith("Postclose-Lauf abgebrochen"), "cancelled → abgebrochen")
check(dg.upstream_fail("success", "1") is None and dg.upstream_fail("", "") is None
      and dg.upstream_fail(None, None) is None, "Erfolg / kein Anstoß → nichts")
check(dg.upstream_fail("$(rm)", "1") is None and dg.upstream_fail("failure", "1;x")["detail"].endswith(
      "(Run ?) — Digest per Anstoß gesendet"), "unbekannte Werte nicht übernommen")
body, title, prio, _ = __import__("health_check").format_digest_body(
    [f], [], n_runs=3, last_run_iso=None, digest_date="2026-11-18")
check(title.startswith("⚠️") and prio == "high" and "POSTCLOSE" in body, "crit → ⚠️-Titel, high")


def _run(tmp: pathlib.Path, now, env=None, sent=None, entries=None):
    sent = sent if sent is not None else []
    entries = [{"run_ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "state_fails": []}] if entries is None else entries
    with mock.patch.object(dg, "DIGEST_STATE_FILE", tmp / "state.json"), \
         mock.patch.object(dg, "POSITION_WATCHLIST_STATE_FILE", tmp / "pw.json"), \
         mock.patch.object(dg, "NTFY_TOPIC", "t-x"), \
         mock.patch.object(dg, "_load_jsonl_window", return_value=entries), \
         mock.patch.dict("os.environ", env or {}, clear=False), \
         mock.patch.object(dg, "_ntfy_send", side_effect=lambda *a, **k: sent.append(a) or True):
        rc = dg.main(now_ts=now)
    return rc, sent


# 4/5 Ablauf: Postclose-Anstoß 22:30 UTC Di → Rückfall Mi 15:10 → Postclose Mi 02:00 Do
with tempfile.TemporaryDirectory() as t:
    tmp = pathlib.Path(t)
    sent = []
    _run(tmp, U(2026, 11, 17, 22, 30), {"UPSTREAM_STATUS": "success", "UPSTREAM_RUN": "5"}, sent)
    st1 = json.loads((tmp / "state.json").read_text())
    _run(tmp, U(2026, 11, 18, 15, 10), {"UPSTREAM_STATUS": "", "UPSTREAM_RUN": ""}, sent)
    st2 = json.loads((tmp / "state.json").read_text())
    check(len(sent) == 1 and st1["last_digest_sent"] == "2026-11-18", f"Anstoß 22:30 + Rückfall: ein Versand ({len(sent)})")
    check(st2["last_successful_run"] == "2026-11-18T15:10:00Z", "übersprungener Lauf hält last_successful_run frisch")
    _run(tmp, U(2026, 11, 19, 2, 0), {"UPSTREAM_STATUS": "failure", "UPSTREAM_RUN": "6"}, sent)
    check(len(sent) == 2 and "POSTCLOSE" in sent[1][1] and "fehlgeschlagen" in sent[1][1],
          "Postclose-Fehlschlag am Folgetag → zweiter Digest mit crit")
    check(sent[1][0].startswith("⚠️"), "Titel ⚠️ bei fehlgeschlagenem Postclose")

with tempfile.TemporaryDirectory() as t:
    _, s0 = _run(pathlib.Path(t), U(2026, 11, 19, 2, 0), {"UPSTREAM_STATUS": "failure", "UPSTREAM_RUN": "7"},
                 entries=[])
    check(len(s0) == 1 and "🔴 POSTCLOSE: Postclose-Lauf fehlgeschlagen" in s0[0][1],
          "ohne Lauf-Daten: Postclose-Alarm trotzdem in der Nachricht")
b0, *_ = __import__("health_check").format_digest_body(
    [f], [], n_runs=0, last_run_iso=None, digest_date="2026-11-18")
check("🔴 POSTCLOSE: Postclose-Lauf fehlgeschlagen" in b0, "ohne Lauf-Daten: Alarm auch im Volltext")

# 7 Determinismus
with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
    _, a = _run(pathlib.Path(t1), U(2026, 11, 19, 2, 0), {"UPSTREAM_STATUS": "failure", "UPSTREAM_RUN": "6"})
    _, b = _run(pathlib.Path(t2), U(2026, 11, 19, 2, 0), {"UPSTREAM_STATUS": "failure", "UPSTREAM_RUN": "6"})
    check(a == b, "gleiche Eingabe → gleiche Nachricht")

# 6 Workflows
daily = yaml.safe_load((ROOT / ".github/workflows/daily-squeeze-report.yml").read_text(encoding="utf-8"))
steps = daily["jobs"]["generate-and-deploy"]["steps"]
trig = [s for s in steps if "health_check_digest.yml" in str(s.get("run", ""))]
check(len(trig) == 1, "genau ein Anstoß-Schritt im Daily-Run")
if trig:
    s = trig[0]
    cond = s.get("if", "")
    check("always()" in cond and "'37 21 * * 1-5'" in cond and "'17 21 * * 1-5'" in cond
          and "env.RUN_PHASE == 'postclose'" in cond, "Anstoß: always(), nur Postclose")
    check(s.get("continue-on-error") is True and steps.index(s) == len(steps) - 2
          and steps[-1].get("name") == "Totmann-Ping healthchecks.io",
          "direkt vor dem Totmann-Ping (der bleibt letzter Schritt), continue-on-error")
    check(s["env"]["UPSTREAM_STATUS"] == "${{ job.status }}" and "${{" not in s["run"]
          and "|| true" not in s["run"], "Werte nur über env, kein Verschlucken")
import resolve_run_phase as rrp  # noqa: E402
check(set(rrp.POSTCLOSE_CRONS) == {"37 21 * * 1-5", "17 21 * * 1-5"},
      "Postclose-Crons im Anstoß = POSTCLOSE_CRONS")
check("actions" in daily["permissions"] and daily["permissions"]["actions"] == "write", "Daily darf Workflows starten")
dw = yaml.safe_load((ROOT / ".github/workflows/health_check_digest.yml").read_text(encoding="utf-8"))
on = dw.get("on") or dw.get(True)
check(on["schedule"] == [{"cron": "47 8 * * *"}], "Rückfall-Zeitplan 08:47 bleibt")
inp = on["workflow_dispatch"]["inputs"]
check(inp["upstream_status"]["required"] is False and inp["upstream_run"]["default"] == "", "Inputs optional")
check(dw["concurrency"] == {"group": "health-check-digest", "cancel-in-progress": False}, "concurrency ohne Abbruch")
prep = [s for s in dw["jobs"]["digest"]["steps"] if "--phase prepare" in str(s.get("run", ""))][0]
check(prep["env"]["UPSTREAM_STATUS"] == "${{ inputs.upstream_status }}", "prepare liest Status über env")

print()
if FAILS:
    print(f"{len(FAILS)} FEHLER")
    sys.exit(1)
print("OK — alle Checks grün")
