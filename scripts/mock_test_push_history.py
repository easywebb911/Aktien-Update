"""Mock-Tests für Phase 2 Stufe 3c-1 — Push-History-Persistenz.

Testet ``_record_push`` aus ``ki_agent.py`` (single source of truth für
das FIFO-Schema). Der Helper in ``generate_report.py`` ist strukturell
identisch und wird durch den Smoke-/Workflow-Pfad mitgeprüft.

Ausführung: ``python scripts/mock_test_push_history.py``. Exit 0 bei
Erfolg, 1 bei jedem AssertionError.
"""

import sys
import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ki_agent importiert beim Modul-Load externe Pakete (yfinance, requests …),
# die in dieser Umgebung evtl. nicht verfügbar sind. Wir extrahieren die
# Helper-Definition daher per Source-Slice statt vollem Import.

src = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
m = re.search(
    r"^def _record_push\([\s\S]+?(?=^\ndef\s|\n# ── )",
    src,
    re.MULTILINE,
)
assert m, "_record_push-Block in ki_agent.py nicht gefunden"
helper_src = m.group(0)

# Stub-Modul mit den Abhängigkeiten, die der Helper im echten Modul aus
# Top-Level-Imports zieht. now_berlin → fester ISO-String, damit ts
# deterministisch testbar ist.
ns: dict = {}
exec(
    "from config import PUSH_HISTORY_MAX\n"
    "def now_berlin():\n"
    "    class _N:\n"
    "        def isoformat(self):\n"
    "            return '2026-05-09T18:00:00+02:00'\n"
    "    return _N()\n"
    + helper_src,
    ns,
)
_record_push = ns["_record_push"]
PUSH_HISTORY_MAX = ns["PUSH_HISTORY_MAX"]


def _expect(cond, msg):
    if not cond:
        raise AssertionError("ASSERT: " + msg)


def test_basic_append():
    state: dict = {}
    _record_push(state, "AAPL", "anomaly", "high", "rvol_explosion",
                 "body x", True)
    hist = state["push_history"]
    _expect(len(hist) == 1, "Cap nicht 1 nach erstem Append")
    e = hist[0]
    _expect(e["ticker"]   == "AAPL", "ticker mismatch")
    _expect(e["kind"]     == "anomaly", "kind mismatch")
    _expect(e["severity"] == "high", "severity mismatch")
    _expect(e["trigger"]  == "rvol_explosion", "trigger mismatch")
    _expect(e["body"]     == "body x", "body mismatch")
    _expect(e["success"] is True, "success mismatch")
    _expect(isinstance(e["ts"], str) and "T" in e["ts"], "ts kein ISO")
    print("PASS  test_basic_append")


def test_failed_push_persisted():
    state: dict = {}
    _record_push(state, "TSLA", "exit_p2", "trigger", "profit_lock",
                 "body y", False)
    e = state["push_history"][0]
    _expect(e["success"] is False, "failed Push muss persistiert sein")
    _expect(e["trigger"] == "profit_lock", "trigger fehlt bei failed-Push")
    print("PASS  test_failed_push_persisted")


def test_null_trigger():
    state: dict = {}
    _record_push(state, "NVDA", "earnings_immediate", "default", None,
                 "body z", True)
    e = state["push_history"][0]
    _expect(e["trigger"] is None, "None-Trigger nicht erhalten")
    print("PASS  test_null_trigger")


def test_fifo_cap_trim():
    state: dict = {"push_history": []}
    # 105 Einträge schreiben → erwarte trim auf PUSH_HISTORY_MAX (100)
    for i in range(PUSH_HISTORY_MAX + 5):
        _record_push(state, f"T{i}", "anomaly", "high", "x",
                     f"body {i}", True)
    hist = state["push_history"]
    _expect(len(hist) == PUSH_HISTORY_MAX,
            f"Cap nicht respektiert: {len(hist)} != {PUSH_HISTORY_MAX}")
    # Älteste raus (FIFO): Ticker T0..T4 müssen weg sein, T5..T104 drin.
    _expect(hist[0]["ticker"] == "T5",
            f"FIFO-Order falsch: {hist[0]['ticker']}")
    _expect(hist[-1]["ticker"] == f"T{PUSH_HISTORY_MAX + 4}",
            f"Letzter Eintrag falsch: {hist[-1]['ticker']}")
    print("PASS  test_fifo_cap_trim")


def test_preexisting_history_kept():
    # Wenn der State bereits Einträge hat, müssen sie respektiert werden
    # und der Cap berechnet sich über die Gesamtlänge.
    state: dict = {"push_history": [
        {"ts": "old", "ticker": "OLD", "kind": "exit_p1",
         "severity": "default", "trigger": None, "body": "b", "success": True}
        for _ in range(PUSH_HISTORY_MAX - 1)
    ]}
    _record_push(state, "NEW", "anomaly", "high", "x", "b", True)
    hist = state["push_history"]
    _expect(len(hist) == PUSH_HISTORY_MAX, "Cap-Logik bricht bei Vorbestand")
    _expect(hist[-1]["ticker"] == "NEW", "Neuer Eintrag nicht am Ende")
    _expect(hist[0]["ticker"]  == "OLD", "Vorbestand vorzeitig getrimmt")
    # Nochmal +2 → erste 2 alte Einträge raus.
    _record_push(state, "NEW2", "anomaly", "high", "x", "b", True)
    _record_push(state, "NEW3", "anomaly", "high", "x", "b", True)
    _expect(len(state["push_history"]) == PUSH_HISTORY_MAX,
            "Cap nicht stabil bei mehrfachen Appends")
    _expect(state["push_history"][-1]["ticker"] == "NEW3",
            "FIFO-Tail nach mehrfachem Append falsch")
    print("PASS  test_preexisting_history_kept")


def test_state_idempotent_setdefault():
    # state ohne push_history-Key → setdefault legt Liste an und mutiert
    # den übergebenen Dict (kein Re-Assign nötig).
    state: dict = {"cooldowns": {"x": "y"}}
    _record_push(state, "AMD", "exit_p1", "default", "exit_alert",
                 "b", True)
    _expect("push_history" in state, "push_history nicht angelegt")
    _expect(state["cooldowns"] == {"x": "y"},
            "Andere State-Keys dürfen nicht angefasst werden")
    print("PASS  test_state_idempotent_setdefault")


def main():
    try:
        test_basic_append()
        test_failed_push_persisted()
        test_null_trigger()
        test_fifo_cap_trim()
        test_preexisting_history_kept()
        test_state_idempotent_setdefault()
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"\nOK: Alle Mock-Tests grün (6/6, Cap={PUSH_HISTORY_MAX}).")


if __name__ == "__main__":
    main()
