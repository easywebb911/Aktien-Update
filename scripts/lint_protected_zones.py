"""Lint: Technische Schutz-Sperre gegen stille Eingriffe in Score-/Filter-/
Push-/Exit-Logik (23.10.2026, Easy-Entscheid 22.10.2026).

## Hintergrund

Ein täglicher "Wächter"-Agent (Claude Code Remote Session) erstellt und
merged ``[Wächter]``-PRs SELBST — ohne menschliche Freigabe pro PR. Bisher
war die einzige Absicherung gegen einen versehentlichen oder unbeabsichtigt
destruktiven Eingriff in geschützte Logik (Score, Filter, Push, Exit,
Freeze-Auswertung) die Session-Disziplin des Wächters selbst (CLAUDE.md-
Regeln lesen und befolgen). Dieser Lint ist eine MECHANISCHE Zweitsicherung,
unabhängig davon, ob der Wächter seine eigenen Regeln korrekt anwendet.

## Was wird geprüft

Drei Kategorien geschützter Zonen, alle live gegen den AKTUELLEN Stand von
``PROTECTED_ZONES_BASE_REF`` (Default ``origin/main``) berechnet — NIEMALS
hartkodierte Zeilennummern (Lehre aus mehreren ``lint_nan_bypass_fields.py``-
Baseline-Drifts in dieser Session: jede Zeilen-Shift durch spätere PRs würde
sonst den Lint selbst kaputt machen oder blind machen):

1. **Benannte Funktionen** (``_PROTECTED_FUNCTIONS``) — per AST rekursiv
   gesucht (auch verschachtelte ``def``, z. B. ``_detect_recent_squeeze``
   innerhalb ``get_yfinance_batch``). Zeilenbereich = kompletter
   Funktionskörper (``node.lineno`` bis ``node.end_lineno``).
2. **Benannte Konstanten** (``_PROTECTED_CONST_PREFIXES`` minus
   ``_CONST_EXCLUDE``) in ``config.py`` — per AST-Modul-Assign, Präfix-Match
   auf den Zielnamen. Zeilenbereich = die einzelne Zuweisung (kann bei
   Tupel-/Dict-Literalen mehrzeilig sein).
3. **Sentinel-Marker-Zonen** (``# PROTECTED-ZONE-START: <name>`` /
   ``# PROTECTED-ZONE-END: <name>``) in ``generate_report.py`` und
   ``ki_agent.py`` — für inline-Logik in ``main()``, die sich nicht sauber
   in eine eigene Funktion fassen lässt (Top-10-Auswahl + Filter-Pipeline,
   Push-Gate-Entscheidungskette). Siehe "Bekannter Kompromiss" unten.
4. **Freeze-Blöcke/Errata** in ``SESSION_HANDOVER.md`` — per Überschriften-
   Anker (``^#{2,4}\\s*(VORABREGISTRIERUNG|ERRATUM)\\b``), Zeilenbereich von
   der Überschrift bis zur nächsten Überschrift gleicher oder höherer Ebene
   (Standard-Markdown-Abschnitts-Scoping).
5. **Ganze Dateien** (``_PROTECTED_WHOLE_FILES``) — ``scripts/freeze_eval.py``
   und ``scripts/stats_helpers.py``: JEDE Änderung ist ein Fund (keine
   Funktions-/Zeilen-Granularität — diese Dateien SIND die Freeze-
   Auswertungs-Methodik, auch eine "reine Logging-Änderung" dort könnte das
   Ergebnis verschieben).

Der PR-Diff wird über ``git diff --unified=0 <base> -- <datei>`` geholt und
die ``@@ -oldstart,oldcount +newstart,newcount @@``-Hunk-Header geparst — der
ALTE Zeilenbereich (``oldstart`` bis ``oldstart+oldcount-1``) wird gegen jede
geschützte Zone auf Überlappung geprüft. Das ist derselbe Mechanismus für
alle vier Kategorien (Funktion/Konstante/Sentinel/Freeze-Block): "überlappt
der Diff-Hunk einen geschützten Zeilenbereich im Basis-Stand?".

## Bekannter Kompromiss (bewusst, nicht versteckt)

``main()`` in ``generate_report.py`` und ``ki_agent.py`` mischt Score-/
Filter-/Push-Logik UND reine Logging-/Diagnose-Calls in denselben
Codeblöcken (Beispiel: die Top-10-Filter-Pipeline enthält ``log.info``/
``print``-Zeilen zwischen den eigentlichen Filter-Checks). Die Sentinel-
Zonen sind deshalb bewusst GROSSZÜGIG geschnitten — sie schützen auch ein
paar benachbarte Logging-Zeilen mit, weil eine chirurgisch genaue Trennung
nicht robust automatisierbar ist, ohne ständig zu driften. Das ist eine
akzeptierte Überprotektion (lieber ein harmloser False-Positive mehr als
ein Score-Eingriff, der durchrutscht) — siehe PR-Bericht für Details.

## Ausnahme-Modell

Siehe ``_pr_is_exempt()`` — zwei Signale kombiniert (bewusst NICHT nur
eines, Begründung im PR-Text):

- Trägt der PR-Titel das Präfix ``[Wächter]`` → **NIEMALS** Ausnahme, egal
  welches Label gesetzt ist. Das ist die Kern-Garantie dieses Lints.
- Sonst: Label ``protected-ok`` auf dem PR → Ausnahme (informativer Pass,
  Fund wird trotzdem ausgegeben).

## CI-Integration

Neuer Step in der BESTEHENDEN ``.github/workflows/pr-checks.yml`` (kein
neuer Workflow nötig) — direkt nach dem schon vorhandenen "Fetch PR base"-
Step (wird auch vom Open-Items-Consistency-Lint genutzt).

Env-Variablen (vom Workflow gesetzt, siehe dort):
``PROTECTED_ZONES_BASE_REF`` (PR-Basis-SHA), ``PR_TITLE``, ``PR_LABELS``
(komma-separiert).

Exit-Code 0 = OK (kein Fund ODER Fund + gültige Ausnahme), 1 = Fail
(Fund, keine Ausnahme).
"""
from __future__ import annotations

import ast
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ── Kategorie 1: benannte Funktionen (rekursiv, inkl. verschachtelter def) ──
_PROTECTED_FUNCTIONS: dict[str, tuple[str, ...]] = {
    "generate_report.py": (
        "score", "score_bonus", "apply_monster_score", "apply_agent_boost",
        "apply_score_smoothing", "apply_late_runner_penalty",
        "compute_conviction_score", "apply_conviction_scores",
        "compute_earliness_pts", "_earliness_pts_v1", "_earliness_pts_v2",
        "compute_exit_score", "process_exit_signals", "_compute_exit_state",
        "_detect_recent_squeeze", "_float_turnover_pts", "_gap_hold_pts",
        "_rs_spy_pts", "_normalize_rvol", "_compute_sub_scores",
    ),
    "ki_agent.py": (
        "compute_signal", "detect_anomalies", "fetch_uoa_signal",
        "_stocktwits_pts",
    ),
    "backtest_history.py": (
        "_build_backtest_extension", "_append_backtest_entries",
    ),
}

# ── Kategorie 2: benannte Konstanten in config.py ────────────────────────────
# Präfix-Match (robuster als Vollständig-Aufzählung — neue Konstanten mit
# demselben Präfix sind automatisch mit-geschützt, ohne diesen Lint warten zu
# müssen). Siehe PR-Bericht für die vollständige Diagnose-Liste.
_PROTECTED_CONST_PREFIXES: tuple[str, ...] = (
    "MIN_PRICE", "MIN_SHORT_FLOAT", "MIN_REL_VOLUME", "MAX_MARKET_CAP",
    "INTL_SCREENING_ENABLED",
    "ANOMALY_", "EARNINGS_IMMEDIATE_", "EXIT_", "COMBO_", "SCORE_",
    "AGENT_BOOST_", "SQUEEZE_HIST_MALUS_", "FLOAT_TURNOVER_PTS_",
    "GAP_", "RS_SPY_", "SUB_", "EARLINESS_", "RVOL_", "TRIGGER_", "PUSH_",
    "LATE_RUNNER_", "STOCKTWITS_", "UOA_", "FINRA_DAILY_SSR_",
    "KI_SENTIMENT_MAX_SCORE", "CATALYST_", "SETUP_EROSION_",
)
# Display-/Status-Konstanten, die TROTZ passendem Präfix NICHT in die Score-/
# Push-Berechnung einfließen (CLAUDE.md "Score-Konfidenz-Stufen" +
# "Score-Methodik-Sync-Regel" bestätigen das explizit) — bewusste
# Ausnahme, kein Versehen.
_CONST_EXCLUDE: frozenset[str] = frozenset({
    "SCORE_CONFIDENCE_MAX_AGE_DAYS", "SCORE_CONFIDENCE_N_MITTEL",
    "SCORE_CONFIDENCE_N_PROVISORISCH", "SCORE_CONFIDENCE_N_ROBUST",
    "SCORE_STATUS_KINDS", "SCORE_STATUS_LABELS",
    "SCORE_HISTORY_FILE", "SCORE_NORMALIZATION_VERSION",
})

# ── Kategorie 3: Sentinel-Marker-Zonen (main()-Inline-Blöcke) ────────────────
_SENTINEL_FILES: tuple[str, ...] = ("generate_report.py", "ki_agent.py")
_SENTINEL_START_RE = re.compile(r"#\s*PROTECTED-ZONE-START:\s*([A-Za-z0-9_-]+)")
_SENTINEL_END_RE   = re.compile(r"#\s*PROTECTED-ZONE-END:\s*([A-Za-z0-9_-]+)")

# ── Kategorie 4: Freeze-Blöcke/Errata in SESSION_HANDOVER.md ─────────────────
_HANDOVER_FILE = "SESSION_HANDOVER.md"
_HEADING_RE = re.compile(r"^(#{2,4})\s*(VORABREGISTRIERUNG|ERRATUM)\b")
_ANY_HEADING_RE = re.compile(r"^(#{1,6})\s")

# ── Kategorie 5: ganze Dateien ────────────────────────────────────────────────
_PROTECTED_WHOLE_FILES: tuple[str, ...] = (
    "scripts/freeze_eval.py", "scripts/stats_helpers.py",
)

_ALL_WATCHED_FILES: tuple[str, ...] = tuple(sorted(set(
    list(_PROTECTED_FUNCTIONS) + list(_SENTINEL_FILES)
    + ["config.py", _HANDOVER_FILE] + list(_PROTECTED_WHOLE_FILES)
)))


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False,
    )
    return result.stdout


def _read_at_ref(ref: str, rel_path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{rel_path}"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _function_zones(source: str, names: tuple[str, ...]) -> list[tuple[str, int, int]]:
    """Rekursiver AST-Walk — findet JEDE ``def``/``async def`` (auch
    verschachtelt) mit passendem Namen. Gibt [(name, start, end), ...]."""
    zones: list[tuple[str, int, int]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return zones
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            end = getattr(node, "end_lineno", node.lineno)
            zones.append((node.name, node.lineno, end))
    return zones


def _const_zones(source: str) -> list[tuple[str, int, int]]:
    zones: list[tuple[str, int, int]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return zones
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for t in targets:
            if not isinstance(t, ast.Name):
                continue
            name = t.id
            if name in _CONST_EXCLUDE:
                continue
            if any(name.startswith(p) for p in _PROTECTED_CONST_PREFIXES):
                end = getattr(node, "end_lineno", node.lineno)
                zones.append((name, node.lineno, end))
    return zones


def _sentinel_zones(source: str) -> list[tuple[str, int, int]]:
    zones: list[tuple[str, int, int]] = []
    open_markers: dict[str, int] = {}
    for i, line in enumerate(source.splitlines(), start=1):
        m_start = _SENTINEL_START_RE.search(line)
        if m_start:
            open_markers[m_start.group(1)] = i
            continue
        m_end = _SENTINEL_END_RE.search(line)
        if m_end:
            name = m_end.group(1)
            start = open_markers.pop(name, None)
            if start is not None:
                zones.append((f"zone:{name}", start, i))
    return zones


def _handover_zones(source: str) -> list[tuple[str, int, int]]:
    lines = source.splitlines()
    headings: list[tuple[int, int, str]] = []  # (lineno, depth, title)
    for i, line in enumerate(lines, start=1):
        m = _ANY_HEADING_RE.match(line)
        if m:
            headings.append((i, len(m.group(1)), line.strip()))
    zones: list[tuple[str, int, int]] = []
    for idx, (lineno, depth, title) in enumerate(headings):
        if not _HEADING_RE.match(title):
            continue
        end = len(lines)
        for j in range(idx + 1, len(headings)):
            nxt_lineno, nxt_depth, _ = headings[j]
            if nxt_depth <= depth:
                end = nxt_lineno - 1
                break
        zones.append((title[:60], lineno, end))
    return zones


def _parse_hunks(diff_text: str) -> list[tuple[int, int]]:
    """Parst ``@@ -oldstart,oldcount +...`` Header -> [(old_start, old_end)]."""
    hunks: list[tuple[int, int]] = []
    for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))?", diff_text, re.MULTILINE):
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        if count == 0:
            # Reine Insertion — Ankerpunkt ist die Zeile, nach der eingefügt
            # wurde (konservativ: als 1-Zeilen-Fenster behandeln).
            hunks.append((start, start))
        else:
            hunks.append((start, start + count - 1))
    return hunks


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


def _pr_is_exempt() -> tuple[bool, str]:
    title = os.environ.get("PR_TITLE", "")
    labels = [l.strip() for l in os.environ.get("PR_LABELS", "").split(",") if l.strip()]
    is_waechter = title.strip().startswith("[Wächter]") or title.strip().startswith("[Waechter]")
    if is_waechter:
        return False, "PR-Titel beginnt mit '[Wächter]' — KEINE Ausnahme möglich (Kern-Garantie)"
    if "protected-ok" in labels:
        return True, "Label 'protected-ok' gesetzt (Nicht-Wächter-PR)"
    return False, "keine Ausnahme aktiv (kein 'protected-ok'-Label)"


def check_file(rel_path: str, base_ref: str) -> list[dict]:
    base_source = _read_at_ref(base_ref, rel_path)
    if base_source is None:
        return []  # Datei existiert bei der Basis noch nicht -> nichts zu vergleichen

    if rel_path in _PROTECTED_WHOLE_FILES:
        diff_text = _run_git(["diff", "--unified=0", base_ref, "--", rel_path])
        if diff_text.strip():
            return [{
                "file": rel_path, "zone": "GANZE DATEI (Freeze-Methodik)",
                "lines": "alle", "kind": "whole-file",
            }]
        return []

    zones: list[tuple[str, int, int]] = []
    if rel_path in _PROTECTED_FUNCTIONS:
        zones += [("def:" + n, s, e) for n, s, e in
                  _function_zones(base_source, _PROTECTED_FUNCTIONS[rel_path])]
    if rel_path == "config.py":
        zones += [("const:" + n, s, e) for n, s, e in _const_zones(base_source)]
    if rel_path in _SENTINEL_FILES:
        zones += _sentinel_zones(base_source)
    if rel_path == _HANDOVER_FILE:
        zones += [("freeze:" + n, s, e) for n, s, e in _handover_zones(base_source)]

    if not zones:
        return []

    diff_text = _run_git(["diff", "--unified=0", base_ref, "--", rel_path])
    hunks = _parse_hunks(diff_text)
    if not hunks:
        return []

    findings: list[dict] = []
    for zone_name, z_start, z_end in zones:
        for h_start, h_end in hunks:
            if _overlaps(z_start, z_end, h_start, h_end):
                findings.append({
                    "file": rel_path, "zone": zone_name,
                    "lines": f"{z_start}-{z_end}",
                    "hunk": f"{h_start}-{h_end}", "kind": "overlap",
                })
                break  # ein Fund pro Zone reicht
    return findings


def main() -> int:
    base_ref = os.environ.get("PROTECTED_ZONES_BASE_REF", "origin/main")

    changed = _run_git(["diff", "--name-only", base_ref]).splitlines()
    changed_set = {c.strip() for c in changed if c.strip()}

    all_findings: list[dict] = []
    for rel_path in _ALL_WATCHED_FILES:
        if rel_path not in changed_set:
            continue
        all_findings.extend(check_file(rel_path, base_ref))

    if not all_findings:
        print("OK: keine Änderung an geschützten Zonen (Score/Filter/Push/"
              "Exit/Freeze-Methodik) gefunden.")
        return 0

    exempt, exempt_reason = _pr_is_exempt()

    print(f"{'WARNUNG' if exempt else 'FEHLER'}: {len(all_findings)} "
          f"Änderung(en) an geschützten Zonen gefunden:")
    for f in all_findings:
        if f["kind"] == "whole-file":
            print(f"  {f['file']}: {f['zone']} — Datei komplett geändert")
        else:
            print(f"  {f['file']}:{f['lines']} ({f['zone']}) "
                  f"— Diff-Hunk {f['hunk']} überlappt")
    print()
    print(f"Ausnahme-Status: {exempt_reason}")
    if exempt:
        print("-> Fund dokumentiert, Check besteht (Ausnahme aktiv). "
              "Easy prüft den Diff trotzdem vor dem Merge.")
        return 0
    print()
    print("Kein '[Wächter]'-PR darf geschützte Zonen jemals automatisch "
          "passieren — dafür gibt es KEINE Ausnahme (auch nicht per Label).")
    print("Für Nicht-Wächter-PRs: Label 'protected-ok' auf dem PR setzen, "
          "falls der Eingriff beabsichtigt ist. Inhaltliche Freigabe bei "
          "Logik-Änderungen bleibt bei Easy; bei reinen Zähler-/Status-/"
          "Doku-Treffern mit Guardian-Bestätigung darf Code selbst setzen "
          "(CLAUDE.md: protected-ok-Label-Regel).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
