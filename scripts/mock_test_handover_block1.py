#!/usr/bin/env python3
"""Mock-Test: Block 1 aus Eintragsdateien (Easy-Entscheid 17.11.2026, Weg a).

  1  Eintragsdateien: gültig/ungültig (Name, Datum, CR, BOM, Überschriften,
     Freeze-Überschrift, Marke im Eintrag, fehlender PR-Verweis, Code-Block)
  2  Erzeugen: deterministisch (byte-gleich), Reihenfolge neueste zuerst
  3  Marken: fehlen / doppelt / vertauscht / außerhalb Block 1 → Abbruch
  4  Bytes außerhalb des Bereichs bleiben identisch; echte Datei: Freeze-MD5 gleich
  5  ZIEL: zwei parallele PRs (je eine Eintragsdatei) lassen sich ohne Rebase
     nacheinander mergen; danach erzeugt der Bot einen Bereich mit beiden
  6  pr-check: Bereich von Hand geändert / '#?' → rot; main hängt nach → nur Hinweis
  7  Digest-Zeile „Block 1 hängt nach“ / None wenn konsistent
  8  Bot-Workflow: nur Pfad handover_eintraege/**, contents: write, kein
     gh workflow run / keine Secrets, committet nur SESSION_HANDOVER.md,
     kein anderer push-Workflow reagiert auf SESSION_HANDOVER.md
  9  pr-checks-Schritt, Staleness zählt Dateien, Nebenbefund count=10
 10  echte Repo-Datei: Bereich passt zum Ordner
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import handover_block1 as hb  # noqa: E402

FAILS: list[str] = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def raises(fn, *a):
    try:
        fn(*a)
    except hb.Block1Error as exc:
        return str(exc)
    return None


GOOD = ("### 18.11.2026 — Titel A (1 PR)\n\n- `#801` (Branch `claude/a`, kein Merge-Hash).\n"
        "  Text mit `#737` und Code:\n  ```\n  # Kommentar im Code\n  ```\n").encode()

# 1 Eintragsdateien
e = hb.parse_entry("2026-11-18_titel-a.md", GOOD)
check(e.pr == 801 and e.date == "2026-11-18", f"gültige Datei gelesen: {e.pr} {e.date}")
check(hb.parse_entry("2026-11-18_y.md", GOOD + b"- zweiter Punkt nennt `#900`\n").pr == 801,
      "eigene PR = Anfang des ersten Aufzählungspunkts, spätere Verweise egal")
check(hb.parse_entry("2026-11-18_x.md", GOOD.replace(b"`#801`", b"`#?`")).pr is None, "'#?' → pr None")
for name, raw, why in [
    ("README.md", GOOD, "Dateiname"),
    ("2026-11-19_x.md", GOOD, "Datum"),
    ("2026-11-18_x.md", GOOD.replace(b"\n", b"\r\n"), "CR"),
    ("2026-11-18_x.md", b"\xef\xbb\xbf" + GOOD, "BOM"),
    ("2026-11-18_x.md", GOOD + b"\n## Neu\n", "Überschrift"),
    ("2026-11-18_x.md", GOOD + b"\n### zweite\n", "Überschrift"),
    ("2026-11-18_x.md", GOOD + b"\n#### VORABREGISTRIERUNG x\n", "VORABREGISTRIERUNG"),
    ("2026-11-18_x.md", GOOD + b"\n<!-- BLOCK1-AUTO-END -->\n", "Marke"),
    ("2026-11-18_x.md", GOOD.replace(b"`#801`", b"#801").replace(b"`#737`", b"#737"), "PR-Verweis"),
    ("2026-11-18_x.md", GOOD + b"\n```\noffen\n", "Code-Block"),
    ("2026-11-18_x.md", b"Titel ohne Raute\n- `#1`\n", "erste Zeile"),
    ("2026-11-18_x.md", b"### 18.11.2026 \xe2\x80\x94 T\n\n- Folge zu `#737`, eigene `#801`\n", "PR-Verweis"),
]:
    msg = raises(hb.parse_entry, name, raw)
    check(msg is not None and why.lower() in msg.lower(), f"abgelehnt ({why}): {msg}")
dup = {"2026-11-18_a.md": GOOD, "2026-11-18_b.md": GOOD}
check("doppelt" in (raises(hb.load_entries_from_files, dup) or ""), "doppelte PR-Nummer abgelehnt")
check(hb.load_entries_from_files({".gitkeep": b""}) == [], ".gitkeep ignoriert")

# 2 Erzeugen deterministisch + Reihenfolge
def mk(date_iso, pr, title):
    d = date_iso.split("-")
    ref = "`#?`" if pr is None else f"`#{pr}`"
    return f"### {d[2]}.{d[1]}.{d[0]} — {title}\n\n- {ref} Text.\n".encode()


files = {"2026-11-18_b.md": mk("2026-11-18", 802, "B"), "2026-11-18_a.md": mk("2026-11-18", 801, "A"),
         "2026-11-17_c.md": mk("2026-11-17", 803, "C"), "2026-11-18_d.md": mk("2026-11-18", None, "D")}
ents = hb.load_entries_from_files(files)
r1 = hb.render_region(ents)
r2 = hb.render_region(list(reversed(hb.load_entries_from_files(dict(reversed(list(files.items())))))))
check(r1 == r2, "gleiche Dateien → byte-gleicher Bereich (Reihenfolge der Eingabe egal)")
pos = [r1.index(t) for t in ("— D", "— B", "— A", "— C")]
check(pos == sorted(pos), "Reihenfolge: Datum ↓, PR ↓ ('#?' oben)")
check(hb.EMPTY_NOTE in hb.render_region([]), "leerer Ordner → Hinweiszeile")

# 3 Marken
BASE = ("# Kopf\n\n## 1) HEUTE IMPLEMENTIERT\n\n" + hb.MARK_START + "\n" + hb.render_region([])
        + hb.MARK_END + "\n\n### 01.01.2026 — Alt\n\n- alt\n\n## 2) AKTIVE POSITIONEN\n\n"
        "### VORABREGISTRIERUNG — X\n\nfest\n")
check(hb.split_handover(BASE)[1] == hb.render_region([]), "Zerlegung findet Bereich")
check("Marken" in raises(hb.split_handover, BASE.replace(hb.MARK_END + "\n", "")), "End-Marke fehlt → Abbruch")
check("Marken" in raises(hb.split_handover, BASE + hb.MARK_START + "\n"), "Start-Marke doppelt → Abbruch")
swapped = BASE.replace(hb.MARK_START, "@@S@@").replace(hb.MARK_END, hb.MARK_START).replace("@@S@@", hb.MARK_END)
check("vor" in raises(hb.split_handover, swapped), "vertauschte Marken → Abbruch")
outside = BASE.replace("## 1) HEUTE IMPLEMENTIERT\n\n", "").replace("# Kopf\n", "# Kopf\n\n## 1) HEUTE X\n\n## 2) Y\n")
check(raises(hb.split_handover, outside) is not None, "Marken außerhalb Block 1 → Abbruch")

# 4 Bytes außerhalb identisch
new = hb.generate(BASE, ents)
check(hb.outside_bytes(new) == hb.outside_bytes(BASE) and new != BASE, "generate: nur Bereich geändert")
check(hb.freeze_block_md5s(new) == hb.freeze_block_md5s(BASE) and len(hb.freeze_block_md5s(BASE)) == 1,
      "Freeze-MD5 unverändert (Fixture)")
real = (ROOT / hb.HANDOVER).read_bytes().decode("utf-8")
real_new = hb.generate(real, ents)
check(hb.outside_bytes(real_new) == hb.outside_bytes(real), "echte Datei: Bytes außerhalb identisch")
check(hb.freeze_block_md5s(real_new) == hb.freeze_block_md5s(real) and len(hb.freeze_block_md5s(real)) >= 10,
      f"echte Datei: {len(hb.freeze_block_md5s(real))} Freeze-MD5 unverändert")
check(hb.generate(real_new, ents) == real_new, "zweiter Lauf ohne Änderung (idempotent)")


# 5 Zwei parallele PRs in einem echten Git-Repo
def git(cwd, *args, ok=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    if ok and r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r


with tempfile.TemporaryDirectory() as t:
    repo = pathlib.Path(t)
    git(repo, "init", "-q", "-b", "main")
    (repo / hb.HANDOVER).write_text(BASE, encoding="utf-8")
    (repo / hb.ENTRY_DIR).mkdir()
    (repo / hb.ENTRY_DIR / ".gitkeep").write_text("")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "basis")
    for br, name, pr in [("pr-a", "2026-11-18_a.md", 811), ("pr-b", "2026-11-18_b.md", 812)]:
        git(repo, "checkout", "-q", "-b", br, "main")
        (repo / hb.ENTRY_DIR / name).write_bytes(mk("2026-11-18", pr, br))
        git(repo, "add", "-A"); git(repo, "commit", "-qm", br)
        rc = hb.pr_check("main", repo)
        check(rc == [], f"{br}: pr-check grün gegen Basis main ({rc})")
    git(repo, "checkout", "-q", "main")
    ma = git(repo, "merge", "--no-ff", "-qm", "merge a", "pr-a", ok=False)
    mb = git(repo, "merge", "--no-ff", "-qm", "merge b", "pr-b", ok=False)
    check(ma.returncode == 0 and mb.returncode == 0,
          "ZIEL: PR A und PR B nacheinander ohne Rebase gemergt (kein Konflikt)")
    check(hb.main(["--check", "--root", str(repo)]) == 1, "vor dem Bot-Lauf: --check meldet Nachhängen")
    dl = hb.digest_line(repo)
    check(dl is not None and "Block 1 hängt nach" in dl and "2 Eintragsdatei" in dl, f"Digest-Zeile: {dl}")
    check(hb.main(["--write", "--root", str(repo)]) == 0, "Bot: --write")
    check(hb.main(["--verify-outside", "main", "--root", str(repo)]) == 0, "Bot: Bytes außerhalb = main")
    check(hb.main(["--check", "--root", str(repo)]) == 0 and hb.digest_line(repo) is None,
          "nach dem Bot-Lauf: konsistent, keine Digest-Zeile")
    txt = (repo / hb.HANDOVER).read_text(encoding="utf-8")
    check(txt.index("— pr-b") < txt.index("— pr-a"), "beide Einträge, neueste PR oben")
    check(git(repo, "status", "--porcelain").stdout.strip() == "M SESSION_HANDOVER.md",
          "Bot ändert nur SESSION_HANDOVER.md")
    git(repo, "commit", "-qam", "bot")
    # 6 pr-check
    git(repo, "checkout", "-q", "-b", "pr-c", "main")
    (repo / hb.HANDOVER).write_text(txt.replace("— pr-a", "— pr-a von Hand"), encoding="utf-8")
    rc = hb.pr_check("main", repo)
    check(any("zwischen den Marken" in x for x in rc), f"Bereich von Hand geändert → rot ({rc})")
    (repo / hb.HANDOVER).write_text(txt.replace("- `#811` Text.", "- `#811` Text.\nZusatz von Hand."), encoding="utf-8")
    rc = hb.pr_check("main", repo)
    check(any("zwischen den Marken" in x for x in rc), f"Zusatzzeile im Bereich → rot ({rc})")
    git(repo, "checkout", "-q", "--", hb.HANDOVER)
    (repo / hb.ENTRY_DIR / "2026-11-19_c.md").write_bytes(mk("2026-11-19", None, "c"))
    rc = hb.pr_check("main", repo)
    check(any("#?" in x for x in rc), f"'#?' → rot ({rc})")
    (repo / hb.ENTRY_DIR / "2026-11-19_c.md").unlink()
    git(repo, "checkout", "-q", "main")
    (repo / hb.ENTRY_DIR / "2026-11-20_d.md").write_bytes(mk("2026-11-20", 813, "d"))
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "merge d ohne Bot")
    git(repo, "checkout", "-q", "-b", "pr-e", "main")
    check(hb.pr_check("main", repo) == [], "main hängt nach → kein Fehler des PR (nur Hinweis)")

# 6b Befund #748: Basis-SHA älter als der main-Stand, mit dem der PR geprüft wird
# (Bot hat nach dem Merge eines anderen PR schon geschrieben) → KEIN Fehler.
with tempfile.TemporaryDirectory() as t:
    repo = pathlib.Path(t)
    git(repo, "init", "-q", "-b", "main")
    (repo / hb.HANDOVER).write_text(BASE, encoding="utf-8")
    (repo / hb.ENTRY_DIR).mkdir()
    (repo / hb.ENTRY_DIR / "2026-11-18_x.md").write_bytes(mk("2026-11-18", 821, "x"))
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "merge x (vor Bot)")
    git(repo, "tag", "basis_alt")
    hb.main(["--write", "--root", str(repo)])
    git(repo, "commit", "-qam", "bot schreibt x")
    (repo / hb.ENTRY_DIR / "2026-11-18_y.md").write_bytes(mk("2026-11-18", 822, "y"))
    rc = hb.pr_check("basis_alt", repo)
    check(rc == [], f"Basis älter als Bot-Commit (Race #748) → kein Fehler ({rc})")

# 6c Guardian #749: weitere Hand-Eingriffe → rot; geänderte Eintragsdatei → erlaubt
with tempfile.TemporaryDirectory() as t:
    repo = pathlib.Path(t)
    git(repo, "init", "-q", "-b", "main")
    (repo / hb.HANDOVER).write_text(BASE, encoding="utf-8")
    (repo / hb.ENTRY_DIR).mkdir()
    for nm, pr in (("2026-11-18_a.md", 831), ("2026-11-18_b.md", 832), ("2026-11-18_c.md", 833)):
        (repo / hb.ENTRY_DIR / nm).write_bytes(mk("2026-11-18", pr, nm[11]))
    hb.main(["--write", "--root", str(repo)])
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "basis mit 3 Einträgen")
    full = (repo / hb.HANDOVER).read_text(encoding="utf-8")
    ents3 = hb.load_entries(repo)
    def _pc(new_txt):
        (repo / hb.HANDOVER).write_text(new_txt, encoding="utf-8")
        r = hb.pr_check("main", repo)
        git(repo, "checkout", "-q", "--", hb.HANDOVER)
        return r
    mid = [e for e in ents3 if e.pr == 832][0]
    r_del = _pc(full.replace(mid.text + "\n\n", ""))
    check(any("fehlt" in x and "2026-11-18_b.md" in x for x in r_del), f"Eintrag mitten drin gelöscht → rot ({r_del})")
    b_, reg_, a_ = hb.split_handover(full)
    r_empty = _pc(b_ + hb.render_region([]) + a_)
    check(r_empty != [], f"Bereich geleert → rot ({r_empty})")
    e1, e3 = [e for e in ents3 if e.pr == 831][0], [e for e in ents3 if e.pr == 833][0]
    r_ord = _pc(full.replace(e3.text, "@@").replace(e1.text, e3.text).replace("@@", e1.text))
    check(r_ord != [], f"Einträge umsortiert → rot ({r_ord})")
    r_intro = _pc(full.replace(hb.INTRO, hb.INTRO + " Von Hand."))
    check(r_intro != [], f"INTRO von Hand geändert → rot ({r_intro})")
    (repo / hb.ENTRY_DIR / "2026-11-18_b.md").write_bytes(mk("2026-11-18", 832, "b geändert"))
    r_mod = hb.pr_check("main", repo)
    check(r_mod == [], f"bestehende Eintragsdatei geändert → erlaubt, Bot zieht nach ({r_mod})")

# 7 Digest-Zeile ohne Verfahren → None
with tempfile.TemporaryDirectory() as t:
    (pathlib.Path(t) / hb.HANDOVER).write_text("# x\n", encoding="utf-8")
    check(hb.digest_line(t) is None, "Handover ohne Marken und ohne Ordner → keine Zeile")

# 8 Bot-Workflow
wf_text = (ROOT / ".github/workflows/handover_block1.yml").read_text(encoding="utf-8")
wf = yaml.safe_load(wf_text)
on = wf.get("on") or wf.get(True)
check(on["push"] == {"branches": ["main"], "paths": ["handover_eintraege/**"]} and "workflow_dispatch" in on,
      "Auslöser: nur push auf main mit Pfad handover_eintraege/** (+ Hand-Start)")
check(wf["permissions"] == {"contents": "write"}, "Rechte: nur contents: write")
check(wf["concurrency"] == {"group": "handover-block1", "cancel-in-progress": False}, "concurrency ohne Abbruch")
run = "\n".join(s.get("run", "") for s in wf["jobs"]["erzeugen"]["steps"])
check("gh workflow" not in run and "secrets." not in wf_text and set(on) == {"push", "workflow_dispatch"},
      "keine Kette: kein gh workflow run, kein Secret/PAT, kein repository_dispatch")
check("git add SESSION_HANDOVER.md" in run and "git add -A" not in run and "git add ." not in run,
      "committet nur SESSION_HANDOVER.md")
for needed in ("--verify-outside origin/main", "--freeze-md5", "--check", "cmp -s", "|| true"):
    present = needed in run
    check(present if needed != "|| true" else not present,
          f"Bot-Schritt {'enthält' if needed != '|| true' else 'ohne'} {needed}")
for f in sorted((ROOT / ".github/workflows").glob("*.yml")):
    d = yaml.safe_load(f.read_text(encoding="utf-8"))
    o = d.get("on") or d.get(True)
    if isinstance(o, dict) and "push" in o and f.name != "handover_block1.yml":
        paths = (o["push"] or {}).get("paths") or []
        check(paths and not any(p in ("SESSION_HANDOVER.md", "**", "*") or p.startswith("SESSION")
                                for p in paths), f"{f.name}: push-Pfade reagieren nicht auf den Bot ({paths})")

# 9 pr-checks / Staleness / Nebenbefund
prc = yaml.safe_load((ROOT / ".github/workflows/pr-checks.yml").read_text(encoding="utf-8"))
st = [s for s in prc["jobs"]["checks"]["steps"] if "handover_block1.py --pr-check" in str(s.get("run", ""))]
check(len(st) == 1 and "${{" not in st[0]["run"], "pr-checks: Schritt 'Handover Block 1' (Wert über env)")
import check_handover_staleness as chs  # noqa: E402
with tempfile.TemporaryDirectory() as t:
    d = pathlib.Path(t)
    (d / "2026-11-18_a.md").write_bytes(mk("2026-11-18", 905, "a"))
    check(chs.extract_highest_entry_file_pr(d) == 905, "Staleness zählt Eintragsdateien")
probe = (ROOT / ".github/workflows/diagnose_provider_probe.yml").read_text(encoding="utf-8")
check("count=5&" not in probe and probe.count("count=10&") == 2, "diagnose_provider_probe: count=10")
check("handover_eintraege/" in (ROOT / "_config.yml").read_text(encoding="utf-8"), "Pages: Ordner ausgeschlossen")

# 10 echte Repo-Datei: Marken gültig, Eintragsdateien gültig, und jeder Eintrag
# im erzeugten Bereich stammt aus dem Ordner. NICHT „Bereich == Ordner“: in einem
# PR liegt die eigene Eintragsdatei schon im Ordner, der Bot schreibt sie erst nach
# dem Merge (sonst wäre dieser Test in jedem PR rot — Befund #743).
_real = (ROOT / hb.HANDOVER).read_bytes().decode("utf-8")
_reg = hb.split_handover(_real)[1]
_ents = hb.load_entries(ROOT)
_blocks = [b for b in _reg.split("\n\n### ") if b.strip()]
_in_region = [("### " + b if not b.startswith("### ") else b).strip() for b in _blocks[1:]]
_texts = {e.text.strip() for e in _ents}
check(all(any(t.startswith(x[:200]) or x.startswith(t[:200]) for t in _texts) for x in _in_region),
      f"echtes Repo: Marken gültig, {len(_in_region)} erzeugte Einträge stammen aus dem Ordner")

print()
if FAILS:
    print(f"{len(FAILS)} FEHLER")
    sys.exit(1)
print("OK — alle Checks grün")
