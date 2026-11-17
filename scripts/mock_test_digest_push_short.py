#!/usr/bin/env python3
"""Mock-Test: Digest-Push-Kurzfassung + Volltext-Ablage (17.11.2026).

Befund 16.11.2026: der Montags-Digest war 6189 Bytes lang; ntfy macht aus
Nachrichten > 4096 Bytes einen Anhang „attachment.txt“, der auf ntfy.sh nach
3 h verfällt. Geprüft wird:
  1  Konstanten (Grenze 4096, Deckel mit Abstand, in Bytes)
  2  künstlich überlanger Digest (viele crit/warn mit Umlauten/Emojis):
     Kurzfassung ≤ Deckel, Alarme vollständig ODER Zähler-Hinweis
  3  alle Alarme passen → alle wörtlich, kein Hinweis
  4  ein einzelner Riesen-Alarm → sichtbar gekürzt, gültiges UTF-8
  5  Rangfolge (Status · Alarme · Zähler · Link) + Determinismus
  6  Link nur bei published=True, sonst Hinweis ohne URL
  7  Alarm-Reihenfolge: crit vor warn, State vor Provider, erholt raus
  8  main(phase=prepare): Volltext-Datei + Outbox, kein Versand, kein Topic
  9  send_phase: Kurzfassung mit Link, last_digest_sent gesetzt
 10  Montags-Digest-Nachbau (Wochenblock) → Kurzfassung ≤ Deckel
 11  ApeWisdom-Zähler (Bootstrap raus, Datumsformat)
 12  Workflow: prepare → publish (Worktree, kein || true) → send → state
 13  Positions-Ticker maskiert; Rückfall bei überlangem Kopf nennt Alarme
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
from datetime import datetime, timezone
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import health_check as hc  # noqa: E402

FAILS: list[str] = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print(f"  FAIL {msg}")


def _dg():
    spec = importlib.util.spec_from_file_location(
        "health_check_digest_t", ROOT / "scripts" / "health_check_digest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _b(s: str) -> int:
    return len(s.encode("utf-8"))


HEAD = ["⚠️ Health-Check-Digest 2026-11-17", "🔴 40 crit · 🟡 60 warn · ✅ 0 ok"]
COUNTERS = ["🧪 Freeze-Zähler: n = 150/250", "🧪 SUW (Einstiegstage): n = 5/60",
            "🔍 Wahrheits-Abgleich: 75 Zeilen · 0 Abweichung",
            "📐 Treffer-Score: 10/10 mit Wert",
            "🔎 Datenprüfung Short Float: 1 von 10 auffällig (FGL)"]


def test_1_constants():
    check(hc.NTFY_MESSAGE_LIMIT_BYTES == 4096, "Grenze 4096")
    check(hc.DIGEST_PUSH_MAX_BYTES == hc.NTFY_MESSAGE_LIMIT_BYTES - hc.DIGEST_PUSH_MARGIN_BYTES,
          "Deckel = Grenze − Abstand")
    check(hc.DIGEST_PUSH_MARGIN_BYTES >= 500, "Abstand ≥ 500 Bytes")


def _long_alarms(n_crit=40, n_warn=60):
    out = []
    for i in range(n_crit):
        out.append(f"🔴 S{i:02d}: Prüfung für Kursänderung ä ö ü ß fehlgeschlagen — "
                   f"Detail {'x' * 60} 🚨 Nr. {i}")
    for i in range(n_warn):
        out.append(f"🟡 W{i:02d}: Abdeckung unter Grundlinie (Müller-Größe) {'y' * 40} Nr. {i}")
    return out


def test_2_overlong():
    alarms = _long_alarms()
    link = hc.digest_link_line("2026-11-17", True)
    txt = hc.compose_digest_push(HEAD, alarms, COUNTERS, link)
    check(_b(txt) <= hc.DIGEST_PUSH_MAX_BYTES, f"überlang: {_b(txt)} Bytes > Deckel")
    lines = txt.split("\n")
    more = [l for l in lines if l.startswith("… und ") and l.endswith("weitere Alarme, siehe Link")]
    check(len(more) == 1, "Zähler-Hinweis fehlt")
    included = [l for l in lines if l in alarms]
    n_more = int(more[0].split()[2]) if more else -1
    check(len(included) + n_more == len(alarms), "Hinweis-Zahl stimmt nicht")
    check(included == alarms[:len(included)], "Alarme nicht vollständig/in Reihenfolge")
    check(lines[-1] == link, "Link nicht letzte Zeile")
    check(lines[:2] == HEAD, "Status nicht vorn")
    txt.encode("utf-8").decode("utf-8")


def test_3_all_fit():
    alarms = _long_alarms(2, 3)
    link = hc.digest_link_line("2026-11-17", True)
    txt = hc.compose_digest_push(HEAD, alarms, COUNTERS, link)
    for a in alarms:
        check(a in txt.split("\n"), "Alarm fehlt obwohl Platz")
    check("weitere Alarme" not in txt, "Hinweis ohne Grund")
    for c in COUNTERS:
        check(c in txt, f"Zähler fehlt: {c}")


def test_4_giant_alarm():
    giant = "🔴 S12: " + ("Ü🚨" * 3000)
    link = hc.digest_link_line("2026-11-17", True)
    txt = hc.compose_digest_push(HEAD, [giant, "🟡 S4: kurz"], COUNTERS, link)
    check(_b(txt) <= hc.DIGEST_PUSH_MAX_BYTES, "Riesen-Alarm sprengt Deckel")
    check("(vollständig im Link)" in txt, "Kürzung nicht sichtbar")
    check("… und 1 weitere Alarme, siehe Link" in txt, "Rest-Alarm nicht gezählt")
    txt.encode("utf-8").decode("utf-8")


def test_5_order_determinism():
    alarms = _long_alarms(1, 1)
    link = hc.digest_link_line("2026-11-17", True)
    a = hc.compose_digest_push(HEAD, alarms, COUNTERS, link, prompt_tail="--- P ---\nPROMPT")
    b = hc.compose_digest_push(HEAD, alarms, COUNTERS, link, prompt_tail="--- P ---\nPROMPT")
    check(a == b, "nicht deterministisch")
    lines = a.split("\n")
    idx = [lines.index(x) for x in (HEAD[0], alarms[0], alarms[1], COUNTERS[0], COUNTERS[-1], link)]
    check(idx == sorted(idx), f"Rangfolge falsch: {idx}")
    check("PROMPT" in a, "Diagnose-Prompt fehlt trotz Platz")


def test_6_link():
    ok = hc.digest_link_line("2026-11-17", True)
    check(ok.endswith("/health_check_digests/2026-11-17.txt"), "Link-Pfad")
    check(ok.startswith("vollständiger Digest: https://raw.githubusercontent.com/"), "Link-Host")
    for pub in (False, None):
        h = hc.digest_link_line("2026-11-17", pub)
        check("http" not in h and "nicht abgelegt" in h, f"Hinweis bei published={pub}")


def test_7_alarm_order():
    sf = [{"id": "S5", "severity": "warn", "detail": "w\nzwei"},
          {"id": "S1", "severity": "crit", "detail": "c"},
          {"id": "S3", "severity": "crit", "detail": "erholt", "recovered": True}]
    pf = [{"provider": "finra", "tier": 2, "severity": "warn", "reason": "r"},
          {"provider": "yahoo", "tier": 1, "severity": "crit", "reason": "x"}]
    out = hc.digest_alarm_lines(sf, pf, extra_warn_lines=["⚠️ Abdeckung x"])
    check(out == ["🔴 S1: c", "🔴 yahoo (Tier 1): x", "🟡 S5: w zwei",
                  "🟡 finra (Tier 2): r", "⚠️ Abdeckung x"], f"Reihenfolge: {out}")


WD_LINE = "👁 Position ZZQX ohne Watchlist-Eintrag seit 2 Handelstagen"


def _run_prepare(tmp: pathlib.Path, dg, topic="geheim-topic-xyz"):
    sent = []
    outbox = tmp / "outbox.json"
    with mock.patch.object(dg, "_position_tickers", return_value=["ZZQX"]), \
         mock.patch.object(dg.hc, "position_watchlist_watchdog_lines", return_value=[WD_LINE]), \
         mock.patch.object(dg, "DIGEST_STATE_FILE", tmp / "state.json"), \
         mock.patch.object(dg, "ARCHIVE_DIR", tmp / "health_check_digests"), \
         mock.patch.object(dg, "POSITION_WATCHLIST_STATE_FILE", tmp / "pw.json"), \
         mock.patch.object(dg, "NTFY_TOPIC", topic), \
         mock.patch.object(dg, "_ntfy_send", side_effect=lambda *a, **k: sent.append(a) or True):
        rc = dg.main(now_ts=datetime(2026, 11, 17, 8, 47, tzinfo=timezone.utc),
                     phase="prepare", outbox_path=outbox)
    return rc, sent, outbox


def test_8_prepare():
    dg = _dg()
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        rc, sent, outbox = _run_prepare(tmp, dg)
        check(rc == 0, "prepare rc")
        check(not sent, "prepare darf nicht senden")
        arch = tmp / "health_check_digests" / "2026-11-17.txt"
        check(arch.exists(), "Volltext-Datei fehlt")
        text = arch.read_text(encoding="utf-8") if arch.exists() else ""
        check("Health-Check-Digest 2026-11-17 — vollständig" in text, "Kopfzeile")
        check("geheim-topic-xyz" not in text, "Topic in Ablage")
        check("ZZQX" not in text and "[Position]" in text, "Positions-Ticker im Volltext nicht maskiert")
        ob = outbox.read_text(encoding="utf-8") if outbox.exists() else ""
        check("ZZQX" in ob, "Kurzfassung (privates Topic) soll den Ticker behalten")
        check(ob and "geheim-topic-xyz" not in ob, "Outbox fehlt/enthält Topic")
        st = json.loads((tmp / "state.json").read_text())
        check(st.get("last_digest_sent") != "2026-11-17", "prepare setzt last_digest_sent")


def test_9_send():
    dg = _dg()
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        _, _, outbox = _run_prepare(tmp, dg)
        for pub, expect in ((True, "https://raw.githubusercontent.com/"), (False, "nicht abgelegt")):
            sent = []
            with mock.patch.object(dg, "DIGEST_STATE_FILE", tmp / "state.json"), \
                 mock.patch.object(dg, "NTFY_TOPIC", "geheim-topic-xyz"), \
                 mock.patch.object(dg, "_ntfy_send",
                                   side_effect=lambda *a, **k: sent.append(a) or True):
                rc = dg.send_phase(outbox_path=outbox, published=pub)
            check(rc == 0 and len(sent) == 1, f"send rc/Anzahl pub={pub}")
            body = sent[0][1] if sent else ""
            check(_b(body) <= hc.DIGEST_PUSH_MAX_BYTES, "gesendet über Deckel")
            check(body.split("\n")[-1].startswith("vollständiger Digest: ")
                  and expect in body.split("\n")[-1], f"Linkzeile pub={pub}")
        st = json.loads((tmp / "state.json").read_text())
        check(st.get("last_digest_sent") == "2026-11-17", "last_digest_sent nicht gesetzt")
        # Versand scheitert bei aktivem Topic → Exit 1 (Fail-Visibility).
        with mock.patch.object(dg, "DIGEST_STATE_FILE", tmp / "state2.json"), \
             mock.patch.object(dg, "NTFY_TOPIC", "geheim-topic-xyz"), \
             mock.patch.object(dg, "_ntfy_send", return_value=False):
            check(dg.send_phase(outbox_path=outbox, published=True) == 1, "Fail → Exit 1")
        check(dg.send_phase(outbox_path=tmp / "fehlt.json", published=True) == 0,
              "keine Outbox → Exit 0")


def test_13_mask_and_fallback():
    m = hc.mask_tickers("S3: current_price fehlt bei 2 Position(en): AMC, WOLF; AMCX ok", ["AMC", "WOLF"])
    check(m == "S3: current_price fehlt bei 2 Position(en): [Position], [Position]; AMCX ok",
          f"mask: {m}")
    huge_head = ["⚠️ " + "Kopf" * 2000]
    link = hc.digest_link_line("2026-11-17", True)
    txt = hc.compose_digest_push(huge_head, ["🔴 S1: a", "🟡 S4: b"], COUNTERS, link)
    check(_b(txt) <= hc.DIGEST_PUSH_MAX_BYTES, "Rückfall über Deckel")
    check("… 2 Alarme, siehe Link" in txt and txt.endswith(link), "Rückfall ohne Alarm-Hinweis")


def test_10_monday_rebuild():
    weekly = ["📅 Wochenübersicht:"] + [
        f"  🆕 Offener Punkt Nummer {i}: sehr lange Beschreibung mit Umlauten äöü "
        f"und Zeichen „…“ ({'z' * 50}) (offen)" for i in range(40)]
    body = "\n".join(["✅ Health-Check OK 2026-11-16", "24h ohne Fails. 7 Runs geprüft."]
                     + ["🟡 edgar_8k (Tier 3): 12/12 calls failed"] + weekly)
    check(_b(body) > hc.NTFY_MESSAGE_LIMIT_BYTES, "Fixture nicht überlang")
    dg = _dg()
    parts = dg._push_parts(body, [], [{"provider": "edgar_8k", "tier": 3, "severity": "warn",
                                       "reason": "12/12 calls failed"}],
                           extra_warn_lines=[], counter_lines=COUNTERS)
    txt = dg._short_text({"digest_date": "2026-11-16", **parts}, published=True)
    check(_b(txt) <= hc.DIGEST_PUSH_MAX_BYTES, f"Montag {_b(txt)} Bytes")
    check("Wochenübersicht" not in txt, "Wochenblock gehört in den Volltext")
    check("🟡 edgar_8k (Tier 3): 12/12 calls failed" in txt, "warn fehlt")


def test_11_apewisdom_counter():
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        (tmp / "ap.jsonl").write_text("\n".join(json.dumps(r) for r in [
            {"date": "2026-11-16", "ticker": "AAA", "found": True},
            {"date": "2026-11-16", "ticker": "BBB", "found": False},
            {"date": "2026-11-16", "ticker": "CCC", "found": None},
            {"date": "2026-11-16", "ticker": "DDD", "found": True},
        ]) + "\n", encoding="utf-8")
        (tmp / "bt.json").write_text(json.dumps([
            {"date": "16.11.2026", "ticker": "AAA"},
            {"date": "16.11.2026", "ticker": "AAA"},
            {"date": "16.11.2026", "ticker": "BBB"},
            {"date": "16.11.2026", "ticker": "CCC"},
            {"date": "16.11.2026", "ticker": "DDD", "source": "bootstrap"},
            {"date": "13.11.2026", "ticker": "AAA"},
        ]), encoding="utf-8")
        line = hc.apewisdom_shadow_counter_line(tmp / "ap.jsonl", tmp / "bt.json")
        check(line.startswith("🗣 ApeWisdom-Schatten: 2/500 "), f"Zähler: {line}")
        check("noch keine Daten" in hc.apewisdom_shadow_counter_line(tmp / "x", tmp / "y"),
              "fehlende Datei")


def test_12_workflow():
    import yaml
    wf = yaml.safe_load((ROOT / ".github/workflows/health_check_digest.yml").read_text(encoding="utf-8"))
    steps = wf["jobs"]["digest"]["steps"]
    names = [s.get("name", "") for s in steps]
    def idx(prefix):
        return next(i for i, n in enumerate(names) if n.startswith(prefix))
    i_p, i_pub, i_s, i_c = (idx("Run Health-Check Digest (prepare)"),
                            idx("Publish full digest"), idx("Send digest push"),
                            idx("Commit digest state"))
    check(i_p < i_pub < i_s < i_c, "Schritt-Reihenfolge")
    check("--phase prepare" in steps[i_p]["run"], "prepare-Aufruf")
    pub = steps[i_pub]
    check(pub.get("id") == "publish" and pub.get("continue-on-error") is True, "publish id/coe")
    check("git worktree add" in pub["run"] and "|| true" not in pub["run"],
          "publish: Worktree, kein || true")
    check("reset --hard" not in pub["run"], "publish darf Arbeitsbaum nicht zurücksetzen")
    check("published=true" in pub["run"], "publish-Ausgabe")
    snd = steps[i_s]
    check(snd.get("if") == "always()" and "--phase send" in snd["run"]
          and "steps.publish.outputs.published" in snd["run"], "send-Schritt")
    check("health_check_digests" in steps[i_c]["run"], "State-Commit sichert Ablage")
    check('health_check_digests/${DDATE}.txt' in pub["run"] and "digest_outbox.json" in pub["run"],
          "publish prüft heutige Datei aus der Outbox")
    fail = [s for s in steps if s.get("name", "").startswith("Fail run if full digest")]
    check(fail and "steps.publish.outcome == 'failure'" in fail[0].get("if", ""),
          "roter Lauf bei gescheiterter Ablage")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    tests.sort(key=lambda f: int(f.__name__.split("_")[1]))
    for t in tests:
        print(f"· {t.__name__}")
        t()
    if FAILS:
        print(f"\n{len(FAILS)} FEHLER")
        return 1
    print(f"\nOK — {len(tests)} Tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
