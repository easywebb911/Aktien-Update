"""Mock-Tests für den wöchentlichen Lit-Check-Reminder (scripts/lit_reminder.py
+ .github/workflows/lit_reminder.yml).

Verifiziert:
- (A) FUNKTIONAL: main() erzeugt EINEN ntfy-Push mit korrekter Kategorie
      (URL-Pattern, ASCII-Title, Priority, Tag, fixer Body) — requests
      gemockt, kein Netzwerk.
- (B) KATEGORIE-ISOLATION: eigene Kategorie, disjunkt zu Trade-kinds; Priority
      NICHT high/urgent (kein Aktions-Signal-Look).
- (C) TRADE-PIPELINE UNBERÜHRT: das Skript importiert/ruft KEIN push_history/
      _record_push, agent_state, Cooldown, Silence, ki_agent — kein Cooldown-
      Cross, kein History-Write.
- (D) CRON: nur Freitag (day-of-week 5), außerhalb aller Trade-/Job-Cron-Slots;
      Workflow schreibt nichts ins Repo (contents: read, kein git commit/push).

FIXTURE-ONLY, kein Netzwerk, kein Live-State.
"""
from __future__ import annotations

import os
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SCRIPTS = ROOT / "scripts"

_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


# ── (A) Funktionaler Push-Capture ───────────────────────────────────────────
class _FakeResp:
    status_code = 200
    text = ""


class _FakeRequests:
    """Fängt den einzigen erwarteten POST ab."""
    def __init__(self):
        self.calls = []

    def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append({"url": url, "data": data,
                           "headers": headers or {}, "timeout": timeout})
        return _FakeResp()


def _load_lit_reminder_with_fake(topic="lit-test-topic"):
    """Importiert lit_reminder frisch mit gesetztem NTFY_TOPIC + Fake-requests."""
    os.environ["NTFY_TOPIC"] = topic
    # config liest NTFY_TOPIC bei Import aus dem Env → vor Import setzen.
    for mod in ("config", "lit_reminder"):
        sys.modules.pop(mod, None)
    fake = _FakeRequests()
    sys.modules["requests"] = fake  # lit_reminder macht `import requests`
    import importlib
    lr = importlib.import_module("lit_reminder")
    lr.requests = fake              # sicherstellen: Modul-Attr zeigt auf Fake
    return lr, fake


def _test_functional():
    print("── (A) Funktionaler Push-Capture ─────────────────────────────")
    import config
    lr, fake = _load_lit_reminder_with_fake()
    rc = lr.main()
    _check("A1 main() exit 0 bei erfolgreichem Send", rc == 0, f"rc={rc}")
    _check("A2 genau EIN Push gesendet", len(fake.calls) == 1,
           f"calls={len(fake.calls)}")
    if not fake.calls:
        return
    call = fake.calls[0]
    _check("A3 URL-Pattern ntfy.sh/{topic}",
           call["url"] == "https://ntfy.sh/lit-test-topic",
           call["url"])
    body = (call["data"] or b"").decode("utf-8") if isinstance(call["data"], bytes) else str(call["data"])
    _check("A4 Body == fixer Reminder-Text (config)",
           body == config.LIT_REMINDER_BODY, body)
    hdrs = call["headers"]
    # Title ist ASCII-gestrippt (Emoji raus), Kern-Text bleibt.
    _check("A5 Title ASCII-clean (kein Emoji im Header)",
           hdrs.get("Title", "").isascii() and "Lit-Check-Reminder" in hdrs.get("Title", ""),
           hdrs.get("Title"))
    _check("A6 Priority == config (default, kein Aktions-Signal)",
           hdrs.get("Priority") == config.LIT_REMINDER_PRIORITY,
           hdrs.get("Priority"))
    _check("A7 Tag == config (books/📚, disjunkt zu Trade-Tags)",
           hdrs.get("Tags") == config.LIT_REMINDER_TAGS,
           hdrs.get("Tags"))


def _test_category_isolation():
    print("── (B) Kategorie-Isolation ───────────────────────────────────")
    import config
    # Trade-kinds aus push_history / ki_agent (CLAUDE.md Push-Historie-Sektion).
    trade_kinds = {"anomaly", "exit_p1", "exit_p2",
                   "earnings_immediate", "conviction_high"}
    _check("B1 LIT_REMINDER_KIND disjunkt zu Trade-kinds",
           config.LIT_REMINDER_KIND not in trade_kinds,
           config.LIT_REMINDER_KIND)
    _check("B2 Priority nicht high/urgent (kein Aktions-Signal-Look)",
           config.LIT_REMINDER_PRIORITY not in ("high", "urgent", "max"),
           config.LIT_REMINDER_PRIORITY)


def _test_trade_pipeline_untouched():
    print("── (C) Trade-Push-Pipeline unberührt ─────────────────────────")
    src = (SCRIPTS / "lit_reminder.py").read_text(encoding="utf-8")
    # Kein Import/Aufruf von Trade-Push-Gates. Der Docstring nennt diese Namen
    # bewusst zur Isolations-Erklärung — daher NUR auf echte AUFRUF-/IMPORT-
    # Signaturen prüfen (mit "(" bzw. "import"/"from"), nicht auf bloße Namen
    # (sonst triggern die Docstring-Erwähnungen wie "agent_state.json").
    forbidden = [
        "import push_history", "from push_history",
        "_record_push(",
        "is_on_cooldown(", "set_cooldown(",
        "import ki_agent", "from ki_agent",
        "save_state(", "save_signals(",
    ]
    hits = [p for p in forbidden if p in src]
    _check("C1 kein Trade-Pipeline-Import/-Aufruf im Reminder-Skript",
           not hits, f"gefunden: {hits}")
    # Kein git-Write im Workflow (kein Cooldown-/History-/State-Commit).
    yml = (ROOT / ".github/workflows/lit_reminder.yml").read_text(encoding="utf-8")
    _check("C2 Workflow schreibt nichts ins Repo (contents: read)",
           "contents: read" in yml and "contents: write" not in yml)
    _check("C3 Workflow hat keinen git-commit/-push-Step",
           "git commit" not in yml and "git push" not in yml)


def _test_cron_friday():
    print("── (D) Cron nur Freitag, außerhalb Trade-Slots ───────────────")
    yml = (ROOT / ".github/workflows/lit_reminder.yml").read_text(encoding="utf-8")
    import re
    m = re.search(r"cron:\s*'([^']+)'", yml)
    _check("D1 Cron-Eintrag vorhanden", m is not None)
    if not m:
        return
    fields = m.group(1).split()
    _check("D2 5-Feld-Cron", len(fields) == 5, m.group(1))
    minute, hour, dom, mon, dow = fields
    _check("D3 day-of-week == 5 (Freitag)", dow == "5", f"dow={dow}")
    _check("D4 day-of-month/month Wildcard (nur Wochentag steuert)",
           dom == "*" and mon == "*", f"dom={dom} mon={mon}")
    # Kollisionsfreiheit zu Trade-/Job-Slots:
    #  ki_agent :17 (stündlich), daily 06:17/21:17, digest 08:47, watchlist 07:00.
    _check("D5 Minute ≠ 17/47/0 (kein ki_agent/digest/watchlist-Slot)",
           minute not in ("17", "47", "0"), f"minute={minute}")
    _check("D6 Stunde ≠ 6/21/8/7 (kein daily/digest/watchlist-Slot)",
           hour not in ("6", "21", "8", "7"), f"hour={hour}")


def main():
    _test_functional()
    _test_category_isolation()
    _test_trade_pipeline_untouched()
    _test_cron_friday()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (Lit-Reminder: funktionaler Push + Kategorie-"
          "Isolation + Trade-Pipeline unberührt + Freitag-Cron).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
