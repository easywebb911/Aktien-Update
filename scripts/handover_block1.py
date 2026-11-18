#!/usr/bin/env python3
"""Block 1 von SESSION_HANDOVER.md aus Eintragsdateien erzeugen (17.11.2026).

Hintergrund (Easy-Entscheid 17.11.2026, Weg a): bis dahin schrieb jeder PR
seinen Block-1-Eintrag direkt in ``SESSION_HANDOVER.md`` — an dieselbe Stelle.
Zwei parallele PRs kollidierten dadurch fast immer (Rebase nötig). Seitdem:

* jeder PR legt **eine eigene Datei** ``handover_eintraege/<JJJJ-MM-TT>_<slug>.md``
  an (eigener Dateiname → kein Konflikt zwischen PRs);
* KEIN PR ändert den erzeugten Bereich in ``SESSION_HANDOVER.md``;
* nach dem Merge erzeugt der Bot-Workflow ``handover_block1.yml`` den Bereich
  zwischen den Marken ``<!-- BLOCK1-AUTO-START`` … ``<!-- BLOCK1-AUTO-END`` neu
  und committet NUR ``SESSION_HANDOVER.md``. Der Altbestand darunter bleibt
  unverändert.

Sicherheitsregeln (Easy 17.11.2026):

* Das Skript fasst ausschließlich die Bytes zwischen den Marken an. Alles
  davor und danach wird byte-genau verglichen; bei Abweichung wird nichts
  geschrieben (Exit 1).
* Marken fehlen, sind doppelt, in falscher Reihenfolge oder liegen außerhalb
  von Block 1 (``## 1) HEUTE`` … ``## 2)``) → Abbruch, nichts geschrieben.
* Eintragsdateien dürfen keine Marken, keine ``#``/``##``-Überschriften und
  keine VORABREGISTRIERUNG/ERRATUM-Überschriften enthalten (kein Einschleusen
  von Freeze-Blöcken oder Struktur-Brüchen).
* Gleiche Eintragsdateien → byte-gleicher Bereich (deterministisch, keine
  Zeitstempel).

Aufruf:
  python scripts/handover_block1.py --check        # Exit 1, wenn Bereich ≠ Ordner
  python scripts/handover_block1.py --write        # Bereich neu schreiben (Bot)
  python scripts/handover_block1.py --verify-outside <git-ref>
        # Bytes außerhalb des Bereichs = <git-ref>:SESSION_HANDOVER.md (Bot)
  python scripts/handover_block1.py --freeze-md5   # MD5 aller Freeze-Blöcke
  python scripts/handover_block1.py --pr-check <base-sha>   # pr-checks.yml

Nur Standardbibliothek (läuft im Bot ohne pip install).
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HANDOVER = "SESSION_HANDOVER.md"
ENTRY_DIR = "handover_eintraege"

MARK_START = ("<!-- BLOCK1-AUTO-START — erzeugt von scripts/handover_block1.py aus "
              "handover_eintraege/ (Bot-Workflow handover_block1.yml); nicht von Hand "
              "ändern -->")
MARK_END = "<!-- BLOCK1-AUTO-END -->"
_START_PREFIX = "<!-- BLOCK1-AUTO-START"
_END_PREFIX = "<!-- BLOCK1-AUTO-END"
INTRO = ("*(Einträge ab 17.11.2026 kommen aus `handover_eintraege/` (eine Datei je "
         "PR), neueste zuerst; ältere Einträge stehen darunter.)*")
EMPTY_NOTE = "*(Noch keine Eintragsdateien.)*"

_BLOCK1_START_RE = re.compile(r"^## 1\) HEUTE", re.MULTILINE)
_BLOCK1_END_RE = re.compile(r"^## 2\)", re.MULTILINE)
_FILE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_[a-z0-9][a-z0-9-]*\.md$")
_HEAD_RE = re.compile(r"^### (\d{2})\.(\d{2})\.(\d{4}) — \S.*$")
_PR_RE = re.compile(r"`#(\d+|\?)`")
_BAD_HEADING_RE = re.compile(r"^#{1,2}\s")
_SUB3_RE = re.compile(r"^###\s")
# identisch zu lint_protected_zones._HEADING_RE (Freeze-Blöcke)
_FREEZE_HEADING_RE = re.compile(r"^(#{2,4})\s*(VORABREGISTRIERUNG|ERRATUM)\b")
_ANY_HEADING_RE = re.compile(r"^(#{1,6})\s")


class Block1Error(Exception):
    """Struktur- oder Inhaltsfehler — es wird nichts geschrieben."""


@dataclasses.dataclass(frozen=True)
class Entry:
    name: str
    date: str          # JJJJ-MM-TT
    pr: int | None     # None = "#?" (Nummer noch nicht eingetragen)
    text: str          # Inhalt ohne abschließende Leerzeilen


# ── Eintragsdateien ──────────────────────────────────────────────────────────

def parse_entry(name: str, raw: bytes) -> Entry:
    """Prüft und liest eine Eintragsdatei. Wirft Block1Error mit Grund."""
    m = _FILE_RE.match(name)
    if not m:
        raise Block1Error(f"{name}: Dateiname muss JJJJ-MM-TT_<slug>.md sein "
                          f"(slug: a-z, 0-9, -)")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise Block1Error(f"{name}: BOM nicht erlaubt")
    if b"\r" in raw:
        raise Block1Error(f"{name}: nur LF-Zeilenenden erlaubt (CR gefunden)")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Block1Error(f"{name}: kein UTF-8 ({exc})") from None
    text = text.rstrip("\n")
    if not text.strip():
        raise Block1Error(f"{name}: leer")
    lines = text.split("\n")
    hm = _HEAD_RE.match(lines[0])
    if not hm:
        raise Block1Error(f"{name}: erste Zeile muss '### TT.MM.JJJJ — Titel' sein")
    if (hm.group(3), hm.group(2), hm.group(1)) != m.groups():
        raise Block1Error(f"{name}: Datum in Überschrift ≠ Datum im Dateinamen")
    in_fence = False
    for i, line in enumerate(lines[1:], start=2):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if _START_PREFIX in line or _END_PREFIX in line:
            raise Block1Error(f"{name}:{i}: Marke im Eintrag nicht erlaubt")
        if in_fence:
            continue
        if _BAD_HEADING_RE.match(line) or _SUB3_RE.match(line):
            raise Block1Error(f"{name}:{i}: Überschrift '#', '##' oder weiteres "
                              f"'###' nicht erlaubt (nur die erste Zeile)")
        if _FREEZE_HEADING_RE.match(line):
            raise Block1Error(f"{name}:{i}: VORABREGISTRIERUNG/ERRATUM nicht erlaubt")
    if in_fence:
        raise Block1Error(f"{name}: Code-Block nicht geschlossen")
    if _START_PREFIX in lines[0] or _END_PREFIX in lines[0]:
        raise Block1Error(f"{name}: Marke im Eintrag nicht erlaubt")
    # Eigene PR-Nummer = Anfang des ERSTEN Aufzählungspunkts ("- `#NNN` …"),
    # nicht irgendein späterer Verweis auf andere PRs (Guardian #742).
    bullets = [ln for ln in lines[1:] if ln.startswith("- ")]
    pm = _PR_RE.match(bullets[0][2:]) if bullets else None
    if not pm:
        raise Block1Error(f"{name}: erster Aufzählungspunkt muss mit dem PR-Verweis "
                          f"`#NNN` (oder `#?` im Entwurf) beginnen")
    pr = None if pm.group(1) == "?" else int(pm.group(1))
    return Entry(name=name, date="-".join(m.groups()), pr=pr, text=text)


def load_entries_from_files(files: dict[str, bytes]) -> list[Entry]:
    """files: {dateiname: inhalt}. Dateien mit führendem Punkt werden
    ignoriert (.gitkeep). Fehler werden gesammelt und gemeinsam geworfen."""
    entries, errors = [], []
    for name in sorted(files):
        if name.startswith("."):
            continue
        try:
            entries.append(parse_entry(name, files[name]))
        except Block1Error as exc:
            errors.append(str(exc))
    if errors:
        raise Block1Error("Eintragsdateien fehlerhaft:\n  " + "\n  ".join(errors))
    seen: dict[int, str] = {}
    for e in entries:
        if e.pr is not None:
            if e.pr in seen:
                raise Block1Error(f"PR #{e.pr} doppelt: {seen[e.pr]} und {e.name}")
            seen[e.pr] = e.name
    return entries


def load_entries(root: pathlib.Path) -> list[Entry]:
    d = root / ENTRY_DIR
    files: dict[str, bytes] = {}
    if d.is_dir():
        for p in d.iterdir():
            if p.is_file():
                files[p.name] = p.read_bytes()
            elif not p.name.startswith("."):
                raise Block1Error(f"{ENTRY_DIR}/{p.name}: Unterordner nicht erlaubt")
    return load_entries_from_files(files)


def _sort_key(e: Entry):
    # neueste zuerst: Datum absteigend, dann PR-Nummer absteigend (#? oben),
    # dann Dateiname — vollständig deterministisch.
    return (e.date, float("inf") if e.pr is None else e.pr, e.name)


def render_region(entries: list[Entry]) -> str:
    """Text ZWISCHEN den Markenzeilen (ohne die Marken selbst)."""
    ordered = sorted(entries, key=_sort_key, reverse=True)
    parts = [INTRO] + ([e.text for e in ordered] if ordered else [EMPTY_NOTE])
    return "\n" + "\n\n".join(parts) + "\n\n"


# ── Handover-Struktur ────────────────────────────────────────────────────────

def split_handover(text: str) -> tuple[str, str, str]:
    """(davor inkl. Start-Markenzeile, Bereich, ab End-Markenzeile).
    Wirft Block1Error bei fehlenden/doppelten/falsch liegenden Marken."""
    lines = text.split("\n")
    starts = [i for i, ln in enumerate(lines) if ln.startswith(_START_PREFIX)]
    ends = [i for i, ln in enumerate(lines) if ln.startswith(_END_PREFIX)]
    if len(starts) != 1 or len(ends) != 1:
        raise Block1Error(f"Marken: {len(starts)}× Start, {len(ends)}× Ende "
                          f"(erwartet je genau 1)")
    s, e = starts[0], ends[0]
    if not s < e:
        raise Block1Error("End-Marke steht vor der Start-Marke")
    b1 = _BLOCK1_START_RE.search(text)
    if b1 is None:
        raise Block1Error("Überschrift '## 1) HEUTE' fehlt")
    b2 = _BLOCK1_END_RE.search(text, b1.end())
    b1_line = text.count("\n", 0, b1.start())
    b2_line = text.count("\n", 0, b2.start()) if b2 else len(lines)
    if not (b1_line < s and e < b2_line):
        raise Block1Error("Marken liegen nicht innerhalb von Block 1")
    before = "\n".join(lines[: s + 1]) + "\n"
    region = "\n".join(lines[s + 1: e]) + "\n" if e > s + 1 else ""
    after = "\n".join(lines[e:])
    if before + region + after != text:  # Selbstprüfung der Zerlegung
        raise Block1Error("interne Zerlegung nicht verlustfrei")
    return before, region, after


def generate(text: str, entries: list[Entry]) -> str:
    """Neuer Handover-Text: nur der Bereich zwischen den Marken ersetzt.
    Prüft byte-genau, dass davor/danach unverändert bleiben."""
    before, _region, after = split_handover(text)
    new = before + render_region(entries) + after
    nb, _nr, na = split_handover(new)
    if nb.encode("utf-8") != before.encode("utf-8") or na.encode("utf-8") != after.encode("utf-8"):
        raise Block1Error("Bytes außerhalb des Bereichs würden sich ändern — Abbruch")
    return new


def outside_bytes(text: str) -> tuple[bytes, bytes]:
    before, _r, after = split_handover(text)
    return before.encode("utf-8"), after.encode("utf-8")


def freeze_block_md5s(text: str) -> list[tuple[str, str]]:
    """MD5 je Freeze-Block (VORABREGISTRIERUNG/ERRATUM), gleiche Abgrenzung wie
    lint_protected_zones._handover_zones. Liste in Dateireihenfolge."""
    lines = text.splitlines()
    heads = []
    for i, line in enumerate(lines):
        m = _ANY_HEADING_RE.match(line)
        if m:
            heads.append((i, len(m.group(1)), line.strip()))
    out = []
    for idx, (ln, depth, title) in enumerate(heads):
        if not _FREEZE_HEADING_RE.match(title):
            continue
        end = len(lines)
        for j in range(idx + 1, len(heads)):
            if heads[j][1] <= depth:
                end = heads[j][0]
                break
        block = "\n".join(lines[ln:end])
        out.append((title[:70], hashlib.md5(block.encode("utf-8")).hexdigest()))
    return out


def check_consistency(text: str, entries: list[Entry]) -> str | None:
    """None = Bereich passt zum Ordner, sonst Grund (für Digest/Wächter)."""
    try:
        _b, region, _a = split_handover(text)
    except Block1Error as exc:
        return f"Marken-Fehler: {exc}"
    want = render_region(entries)
    if region == want:
        return None
    missing = [e for e in entries if e.text not in region]
    if missing:
        names = ", ".join(e.name for e in missing[:5])
        more = f" (+{len(missing) - 5})" if len(missing) > 5 else ""
        return f"{len(missing)} Eintragsdatei(en) fehlen im Handover: {names}{more}"
    return "erzeugter Bereich weicht vom Ordner ab (Reihenfolge/Inhalt)"


def digest_line(root: pathlib.Path | str = ROOT) -> str | None:
    """Warnzeile für den Health-Check-Digest; None = alles passt.
    Raise-frei (der Digest darf daran nie scheitern)."""
    root = pathlib.Path(root)
    try:
        path = root / HANDOVER
        if not path.exists():
            return None
        text = path.read_bytes().decode("utf-8")
        if _START_PREFIX not in text and not (root / ENTRY_DIR).is_dir():
            return None  # Verfahren noch nicht eingeführt
        reason = check_consistency(text, load_entries(root))
    except Block1Error as exc:
        reason = str(exc).split("\n")[0]
    except Exception as exc:  # noqa: BLE001 — Digest bleibt robust
        reason = f"Prüfung nicht möglich ({type(exc).__name__})"
    if reason is None:
        return None
    return (f"🟡 Block 1 hängt nach: {reason} — Bot-Lauf handover_block1 prüfen "
            f"(python scripts/handover_block1.py --check)")


# ── git-Hilfen (nur lesend) ──────────────────────────────────────────────────

def _git(args: list[str], root: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, check=False)


def _show(ref: str, rel: str, root: pathlib.Path) -> bytes | None:
    r = _git(["show", f"{ref}:{rel}"], root)
    return r.stdout if r.returncode == 0 else None


def _entry_files_at(ref: str, root: pathlib.Path) -> dict[str, bytes]:
    r = _git(["ls-tree", "--name-only", f"{ref}:{ENTRY_DIR}"], root)
    if r.returncode != 0:
        return {}
    files = {}
    for name in r.stdout.decode("utf-8").split("\n"):
        if name:
            data = _show(ref, f"{ENTRY_DIR}/{name}", root)
            if data is not None:
                files[name] = data
    return files


def pr_check(base: str, root: pathlib.Path) -> list[str]:
    """Fehlerliste für pr-checks.yml (leer = grün)."""
    errs: list[str] = []
    try:
        entries = load_entries(root)
    except Block1Error as exc:
        return [str(exc)]
    for e in entries:
        if e.pr is None:
            errs.append(f"{ENTRY_DIR}/{e.name}: PR-Nummer noch '#?' — vor Ready eintragen")
    cur = (root / HANDOVER).read_bytes().decode("utf-8")
    base_raw = _show(base, HANDOVER, root)
    if base_raw is None:
        return errs + [f"{HANDOVER} auf der Basis nicht lesbar ({base})"]
    base_txt = base_raw.decode("utf-8")
    if _START_PREFIX not in base_txt:
        # Einführender PR: Basis hat noch keine Marken.
        try:
            split_handover(cur)
        except Block1Error as exc:
            errs.append(f"Marken im PR fehlerhaft: {exc}")
        return errs
    try:
        _b1, cur_region, _a1 = split_handover(cur)
    except Block1Error as exc:
        return errs + [f"Marken-Fehler: {exc}"]
    # Hand-Eingriff erkennen OHNE Vergleich mit ``base``: pr-checks prüft den PR
    # gemergt mit dem NEUESTEN main, ``base.sha`` kann aber älter sein (vor einem
    # Bot-Commit) — Befund #748. Gültig ist der Bereich, wenn er exakt die
    # Bot-Erzeugung aus genau den Eintragsdateien ist, deren Text er enthält.
    # Ein von Hand geänderter Eintrag oder fremder Text passt dann nicht mehr.
    shown = [e for e in entries if e.text in cur_region]
    if cur_region != render_region(shown):
        errs.append("Bereich zwischen den Marken ist keine reine Bot-Erzeugung aus den "
                    f"Eintragsdateien (von Hand geändert?) — nur der Bot schreibt dort; "
                    f"Eintrag stattdessen als Datei in {ENTRY_DIR}/ anlegen")
    try:
        base_entries = load_entries_from_files(_entry_files_at(base, root))
        reason = check_consistency(base_txt, base_entries)
    except Block1Error as exc:
        reason = str(exc)
    if reason:
        # Nur Hinweis: zwischen einem Merge und dem Bot-Lauf (≈ 1 min) ist das
        # erwartbar und nicht Schuld dieses PR. Sichtbar wird ein echter
        # Rückstand über den Digest und den Wächter (--check).
        print(f"HINWEIS: main hängt nach (Bot-Lauf handover_block1 prüfen): {reason}")
    return errs


# ── CLI ──────────────────────────────────────────────────────────────────────

def _write_atomic(path: pathlib.Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp_block1")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    g.add_argument("--verify-outside", metavar="REF")
    g.add_argument("--freeze-md5", action="store_true")
    g.add_argument("--pr-check", metavar="BASE")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)
    root = pathlib.Path(a.root)
    path = root / HANDOVER
    try:
        if a.freeze_md5:
            for title, md5 in freeze_block_md5s(path.read_bytes().decode("utf-8")):
                print(f"{md5}  {title}")
            return 0
        if a.pr_check:
            errs = pr_check(a.pr_check, root)
            for e in errs:
                print(f"FEHLER: {e}")
            print("OK: Block-1-Eintragsdateien und Bereich konsistent." if not errs
                  else f"{len(errs)} Fehler.")
            return 1 if errs else 0
        raw = path.read_bytes()
        if b"\r" in raw:
            raise Block1Error(f"{HANDOVER}: CR-Zeilenenden — Abbruch")
        text = raw.decode("utf-8")
        if a.verify_outside:
            old = _show(a.verify_outside, HANDOVER, root)
            if old is None:
                raise Block1Error(f"{a.verify_outside}:{HANDOVER} nicht lesbar")
            if outside_bytes(text) != outside_bytes(old.decode("utf-8")):
                print("FEHLER: Bytes außerhalb des Bereichs weichen ab — nichts committen.")
                return 1
            print("OK: Bytes außerhalb des Bereichs identisch.")
            return 0
        entries = load_entries(root)
        if a.check:
            reason = check_consistency(text, entries)
            if reason:
                print(f"FEHLER: Block 1 hängt nach: {reason}")
                return 1
            print(f"OK: Block 1 passt zum Ordner ({len(entries)} Einträge).")
            return 0
        new = generate(text, entries)
        if new == text:
            print(f"Keine Änderung ({len(entries)} Einträge).")
            return 0
        _write_atomic(path, new.encode("utf-8"))
        if outside_bytes(path.read_bytes().decode("utf-8")) != outside_bytes(text):
            raise Block1Error("Nachprüfung nach dem Schreiben fehlgeschlagen")
        print(f"Bereich neu erzeugt ({len(entries)} Einträge).")
        return 0
    except Block1Error as exc:
        print(f"FEHLER: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
