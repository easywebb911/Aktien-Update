#!/usr/bin/env python3
"""fix_trading_dates_oneoff.py — Einmal-Korrektur verschobener Handelstag-Labels.

Hintergrund (Wächter-Befund 26.10.2026, siehe trading_date.py + SESSION_
HANDOVER.md): mehrere Sammel-/Persistenz-Pfade datierten neue Einträge mit
``date.today()``/``datetime.now(timezone.utc).date()`` (UTC-Kalenderdatum)
statt dem US/Eastern-Handelstag. Postclose-Läufe, die nach UTC-Mitternacht
feuern (US/Eastern ist dann noch derselbe Handelstag), bekamen dadurch ein
Label, das einen Tag zu weit in der Zukunft liegt.

Dieses Skript korrigiert NUR Bestands-Einträge, bei denen ein echter
Zeitstempel (``ts_utc``/``fetch_ts_utc``) im Datensatz steht — das ist die
einzige Quelle, aus der sich das korrekte Handelstag-Label deterministisch
zurückrechnen lässt (``trading_date.us_trading_date``). Einträge OHNE
Zeitstempel werden NICHT verändert (siehe ``_report_timestampless`` unten) —
bei ihnen lässt sich nicht nachträglich feststellen, welchem Lauf sie
zuzuordnen sind.

Betroffene, KORRIGIERBARE Dateien (JSONL, append-only, Zeitstempel pro
Zeile):
  - news_coverage_history.jsonl   (ts_utc,       Key (date, run_phase))
  - coverage_history.jsonl        (ts_utc,       Key (date, run_phase, quelle, tick_hour))
  - options_chain_raw.jsonl       (fetch_ts_utc, Key (date, ticker))
  - apewisdom_attention_history.jsonl (ts_utc,   Key (date, ticker))

NICHT korrigierbare Dateien (kein Zeitstempel pro Punkt, nur REPORTED —
reine Zählung, siehe Aufruf unten):
  - inst_ownership_history.json / options_oi_history.json /
    reg_sho_history.json / ftd_history.json (Dict-of-Ticker-Listen,
    keine ``ts_utc``-Spur je Punkt — der Code-Fix in generate_report.py/
    reg_sho_history.py/ftd_history.py verhindert NEUE Fehldatierungen,
    Bestand bleibt dort unkorrigiert; anomale Datums-Counts werden hier
    nur REPORTED, siehe ``_report_dict_of_points``).

Sicherheit:
  - Sicherung (*.bak) je korrigierter Datei VOR dem Schreiben (lokal, wird
    NICHT committed — siehe .gitignore-Hinweis im PR-Text).
  - Idempotent: ein zweiter Lauf findet 0 weitere Korrekturen (sobald alle
    "date"-Felder mit ihrem eigenen Zeitstempel übereinstimmen, meldet der
    ET-Vergleich keine Abweichung mehr).
  - Echte Kollision (nach Korrektur zwei Zeilen mit identischem Key, aber
    UNTERSCHIEDLICHEM Inhalt) wird NICHT überschrieben — stattdessen
    gemeldet, beide Zeilen bleiben unverändert stehen.

Aufruf: ``python3 scripts/fix_trading_dates_oneoff.py [--dry-run]``
Exit 0 immer (reines Korrektur-Tool, kein CI-Gate).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trading_date import us_trading_date  # noqa: E402

# (filename, ts_field, key_fields_besides_date)
_CORRECTABLE_JSONL: list[tuple[str, str, tuple[str, ...]]] = [
    ("news_coverage_history.jsonl", "ts_utc", ("run_phase",)),
    ("coverage_history.jsonl", "ts_utc", ("run_phase", "quelle", "tick_hour")),
    ("options_chain_raw.jsonl", "fetch_ts_utc", ("ticker",)),
    ("apewisdom_attention_history.jsonl", "ts_utc", ("ticker",)),
]

# Dict-of-ticker-lists-Dateien ohne Zeitstempel pro Punkt — nur REPORTED.
_REPORT_ONLY_DICT_FILES = [
    "inst_ownership_history.json",
    "options_oi_history.json",
    "reg_sho_history.json",
    "ftd_history.json",
]


def _sha256(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except FileNotFoundError:
        return "—"


def _correct_date(ts_iso: str) -> str | None:
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(ts_iso)
    except (ValueError, TypeError):
        return None
    return us_trading_date(dt).isoformat()


def fix_jsonl(path: pathlib.Path, ts_field: str, extra_key_fields: tuple[str, ...],
             *, dry_run: bool = False) -> dict:
    """Korrigiert ein JSONL-History-File. Returnt Statistik-Dict."""
    stats = {
        "file": path.name, "total": 0, "no_ts": 0, "already_correct": 0,
        "corrected": 0, "collisions": 0, "collision_examples": [],
        "corrected_examples": [], "hash_before": _sha256(path), "hash_after": None,
    }
    if not path.exists():
        stats["hash_after"] = stats["hash_before"]
        return stats

    raw_lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[dict | None] = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            entries.append(None)
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            entries.append(None)   # kaputte Zeile — unverändert durchreichen
    stats["total"] = sum(1 for e in entries if e is not None)

    # Schritt 1: Ziel-Datum je Zeile berechnen (None = keine Aenderung).
    target_dates: list[str | None] = []
    for e in entries:
        if e is None:
            target_dates.append(None)
            continue
        ts = e.get(ts_field)
        if not ts:
            stats["no_ts"] += 1
            target_dates.append(None)
            continue
        new_d = _correct_date(ts)
        if new_d is None:
            stats["no_ts"] += 1
            target_dates.append(None)
            continue
        if new_d == e.get("date"):
            stats["already_correct"] += 1
            target_dates.append(None)
        else:
            target_dates.append(new_d)

    # Schritt 2: Kollisions-Check — nach Korrektur duerfen keine zwei
    # Zeilen denselben vollen Key (date + extra_key_fields) tragen, AUSSER
    # ihr Inhalt ist identisch (reiner Idempotenz-Fall).
    def _full_key(e: dict, date_val) -> tuple:
        return (date_val,) + tuple(e.get(f) for f in extra_key_fields)

    final_keys: dict[tuple, int] = {}   # key -> erster Zeilen-Index
    blocked: set[int] = set()
    for i, e in enumerate(entries):
        if e is None:
            continue
        d = target_dates[i] if target_dates[i] is not None else e.get("date")
        k = _full_key(e, d)
        if k in final_keys:
            j = final_keys[k]
            if entries[j] != e:
                blocked.add(i)
                blocked.add(j)
                if len(stats["collision_examples"]) < 5:
                    stats["collision_examples"].append(
                        {"key": str(k), "line_a": j, "line_b": i})
            # identischer Inhalt (reiner Re-Run-Fall) -> keine Kollision,
            # beide Zeilen bleiben wie sie sind (keine der beiden wird
            # verschoben, falls eine von ihnen das Korrektur-Ziel war).
        else:
            final_keys[k] = i

    out_lines: list[str] = []
    for i, e in enumerate(entries):
        if e is None or target_dates[i] is None or i in blocked:
            out_lines.append(raw_lines[i])
            continue
        e2 = dict(e)
        old_date = e2.get("date")
        e2["date"] = target_dates[i]
        out_lines.append(json.dumps(e2, ensure_ascii=False))
        stats["corrected"] += 1
        if len(stats["corrected_examples"]) < 6:
            stats["corrected_examples"].append(
                {"line": i, "old_date": old_date, "new_date": target_dates[i],
                 "extra": {f: e.get(f) for f in extra_key_fields}})
    stats["collisions"] = len(blocked) // 2 if blocked else 0

    if stats["corrected"] and not dry_run:
        bak = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, bak)
        path.write_text("\n".join(out_lines) + ("\n" if out_lines else ""),
                        encoding="utf-8")
        stats["hash_after"] = _sha256(path)
    else:
        stats["hash_after"] = stats["hash_before"]
    return stats


def report_dict_of_points(path: pathlib.Path) -> dict:
    """Reine Zaehlung fuer Dict-of-Ticker-Listen-Dateien ohne Zeitstempel
    pro Punkt — KEINE Mutation, nur Bericht (siehe Modul-Docstring)."""
    stats = {"file": path.name, "total_points": 0, "exists": path.exists()}
    if not path.exists():
        return stats
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return stats
    total = 0
    from collections import Counter
    date_counts: Counter = Counter()
    for _tk, pts in d.items():
        if not isinstance(pts, list):
            continue
        for p in pts:
            total += 1
            if isinstance(p, dict) and p.get("date"):
                date_counts[p["date"]] += 1
    stats["total_points"] = total
    if date_counts:
        median_n = sorted(date_counts.values())[len(date_counts) // 2]
        anomal = {dt: n for dt, n in date_counts.items()
                  if n > median_n * 1.3}
        stats["median_tickers_per_date"] = median_n
        stats["anomal_dates"] = anomal
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="nur Statistik, keine Datei schreiben")
    args = ap.parse_args()

    print("=== Korrigierbare Dateien (Zeitstempel vorhanden) ===")
    for fname, ts_field, extra in _CORRECTABLE_JSONL:
        stats = fix_jsonl(ROOT / fname, ts_field, extra, dry_run=args.dry_run)
        print(f"\n{fname}:")
        print(f"  total={stats['total']} ohne_ts={stats['no_ts']} "
              f"bereits_korrekt={stats['already_correct']} "
              f"korrigiert={stats['corrected']} kollisionen={stats['collisions']}")
        print(f"  hash_vorher={stats['hash_before']} hash_nachher={stats['hash_after']}")
        for ex in stats["corrected_examples"]:
            print(f"    Zeile {ex['line']}: {ex['old_date']} -> {ex['new_date']} "
                  f"({ex['extra']})")
        for ex in stats["collision_examples"]:
            print(f"    KOLLISION key={ex['key']} Zeilen {ex['line_a']}/{ex['line_b']} "
                  f"— NICHT überschrieben, bitte manuell prüfen")

    print("\n=== Nur-Report (kein Zeitstempel je Punkt — keine Korrektur möglich) ===")
    for fname in _REPORT_ONLY_DICT_FILES:
        stats = report_dict_of_points(ROOT / fname)
        print(f"\n{fname}: total_points={stats.get('total_points', 0)}")
        if stats.get("anomal_dates"):
            print(f"  Median Ticker/Datum={stats.get('median_tickers_per_date')}")
            print(f"  Anomale Datums-Counts (>1.3x Median, vermutlich gemergte "
                  f"Handelstage): {stats['anomal_dates']}")
            print("  -> nicht korrigierbar ohne Zeitstempel; der Code-Fix "
                  "(trading_date.us_trading_date) verhindert neue Faelle.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
