"""Hypothesen-Runde November 2026 (H-G, H-I, H-K) — einmalige Freeze-Auswertung.

Setzt den Block „### VORABREGISTRIERUNG — Hypothesen-Runde November 2026
(H-G, H-I, H-K), eingefroren mit dem Merge" aus ``SESSION_HANDOVER.md`` um
(PR #684, gemergt 12.11.2026). Der Block ist die EINZIGE Quelle für Stichprobe,
Ziele, Verfahren, Familie, Floors, Verdikte und Pflichtangaben. Die Konstanten
unten sind wörtlich aus dem Block übernommen; der MD5-Pin stellt sicher, dass
der Block seit dem Bau unverändert ist, und ``read_freeze`` prüft die
wichtigsten Zahlen zusätzlich im Blocktext.

Ablauf von ``run_stage`` — die Reihenfolge IST die Schutz-Mechanik:

  1. Lauf-Ort-Guard (nur GitHub Actions, nur ``refs/heads/main``).
  2. Freeze-Check (Block genau einmal, MD5-Pin, Zahlen-Gegenprobe).
  3. Sperre: Zeile der Familie in ``eval_results.jsonl`` → Abbruch.
     Stufe 2 zusätzlich: Replikation + „Paper C handelbar“ gelaufen, Stufe 1
     gelaufen, mindestens eine Hypothese mit „Beleg“/„bedingt“.
  4. ERST JETZT werden Export, ``outcome_path.jsonl`` und (H-I)
     ``inst_ownership_history.json`` gelesen. Zeilen außerhalb des
     Stufenfensters werden beim Einlesen verworfen (vor jedem Feldzugriff
     außer ``date``/``provenance``). Stufe 1: Zählungen müssen Block E
     entsprechen, sonst Abbruch. Stufe 2: n ≥ 500 je Hypothese, sonst Abbruch.
     In beiden Fällen ist bis hier kein Ergebnis gerechnet.
  5. Auswertung, Anhängen an ``eval_results.jsonl``, EIN ntfy-Push mit den
     Verdikten (keine Ergebniszahlen).

Wiederverwendet (nicht kopiert): ``freeze_eval.bootstrap_auc_ci``,
``freeze_eval.paired_bootstrap_mean_delta``, ``freeze_eval.cluster_double_run``,
``freeze_eval._dedup_rows``, ``freeze_eval._data_hash``,
``freeze_eval._git_commit_hash``, ``freeze_eval._append_results``,
``stats_helpers.mann_whitney_u_auc``, ``stats_helpers.wilcoxon_signed_rank_paired``,
``stats_helpers.multiple_testing_correction``, ``stats_helpers._ranks_with_ties``
und ``stats_helpers._normal_cdf`` (für die im Block wörtlich vorgegebene
einseitige Wilcoxon-Formel; Gegenprobe gegen den zweiseitigen p der Funktion),
``backtest_history.apply_round_trip_haircut`` (Quelltext per AST geladen, weil
``backtest_history`` beim Import yfinance braucht), ``health_check_digest._ntfy_send``.
``freeze_eval.py``/``stats_helpers.py`` werden NICHT verändert.

Aufruf (nur im Workflow ``health_check_digest.yml``, Input ``hypothesen_nov26_s1``)::

    python scripts/hypothesen_nov26_eval.py --run --stage 1

Ohne ``--run`` passiert nichts außer einem Hinweis (Exit 2).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import pathlib
import re
import sys
from datetime import date, datetime, timezone
from typing import Callable, Sequence

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SCRIPTS = pathlib.Path(__file__).resolve().parent
for _p in (str(_ROOT), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config  # noqa: E402
import freeze_eval  # noqa: E402
from stats_helpers import (  # noqa: E402
    _normal_cdf, _ranks_with_ties, mann_whitney_u_auc, multiple_testing_correction,
    wilcoxon_signed_rank_paired)

SCHEMA_V = 1
HANDOVER_FILE = "SESSION_HANDOVER.md"
INST_FILE = "inst_ownership_history.json"
FREEZE_HEADING = ("### VORABREGISTRIERUNG — Hypothesen-Runde November 2026 "
                  "(H-G, H-I, H-K), eingefroren mit dem Merge")
# MD5 des Blocks (Überschrift bis vor die nächste Überschrift der Ebene ≤ 3,
# Zeilen mit "\n" verbunden) nach dem Protokolleintrag 14.11.2026 (PR #701,
# Fix B Halbzeile; vorher 380119ab…, #698 Berichtsdatum Variante A; davor
# 358d23a3…, Protokolleintrag 12.11. abends #685).
FREEZE_BLOCK_MD5 = "057ba27b995f5f654a1eeb946619f860"
FREEZE_DATE = "12.11.2026"
PROTOCOL_REF = ("SESSION_HANDOVER.md, VORABREGISTRIERUNG — Hypothesen-Runde November 2026 "
                "(H-G, H-I, H-K), eingefroren mit dem Merge (PR #684, 12.11.2026)")

# ── Wörtlich aus dem Block ─────────────────────────────────────────────
PROVENANCE = "forward"                                   # A.3
S1_FROM, S1_TO = date(2026, 7, 21), date(2026, 10, 23)  # A.3
S2_FROM = date(2026, 10, 24)                             # A.4
TARGET_PCT = 30.0                                        # A.1
N_BARS = 11                                              # A.1 (bars[0] = D … bars[10])
BOOT_N, BOOT_SEED, CI_LO, CI_HI = 2000, 42, 2.5, 97.5    # A.6
ALPHA = 0.05                                             # A.9 / A.11
FLOOR = 40                                               # B.6 / C.6 / D.5
REGIME_MIN_AUC = 30                                      # C.7 / D.6
REGIME_MIN_PAIRS, REGIME_MIN_NONZERO = 30, 10            # B.7
S2_N_TRIGGER = 500                                       # A.13
REGIMES = ("bull", "bear", "neutral")
# Block E (Zählungen beim Freeze, Stufe 1) — Gegenprobe vor jeder Rechnung.
S1_EXPECTED = {"n_window": 672, "n_usable_a1": 669, "n_hi": 508, "n_hk": 669, "n_hk_ja": 164}

FAMILY = {1: "hyp_nov26_s1", 2: "hyp_nov26_s2"}
HYPS = ("hg", "hi", "hk")
PREREQ_FAMILIES_S2 = ("paper_c_replikation", "paper_c_handelbar")    # A.13
PASS_VERDICTS = ("Beleg", "bedingt")                                  # A.11


class HypAbort(RuntimeError):
    """Kontrollierter Abbruch — es wurde nichts ausgewertet/geschrieben."""


def test_id(hyp: str, stage: int) -> str:
    return f"{hyp}_s{stage}"


# ── 1) Freeze-Block ─────────────────────────────────────────────────────
def extract_freeze_block(handover_text: str) -> str:
    lines = handover_text.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln == FREEZE_HEADING]
    if len(idx) != 1:
        raise HypAbort(f"Freeze-Block nicht eindeutig gefunden ({len(idx)} Treffer).")
    start = idx[0]
    end = start + 1
    while end < len(lines):
        m = re.match(r"^(#{1,6})\s", lines[end])
        if m and len(m.group(1)) <= 3:
            break
        end += 1
    return "\n".join(lines[start:end])


# Zahlen, die im Blocktext (Leerraum normalisiert, ohne **) stehen müssen.
_REQUIRED_SNIPPETS = (
    "Einstieg D von 21.07.2026 bis einschließlich 23.10.2026",
    "Einstieg D ≥ 24.10.2026",
    "Treffer = `g ≥ 30,0`",
    "N = 2000, Seed = 42, 95 % zweiseitig, Perzentil 2,5 / 97,5",
    "`family = \"hyp_nov26_s1\"`, k = 3",
    "α = 0,05, Holm",
    "mindestens 40 Differenzen ≠ 0",
    "prüfbar ab 30 Paaren und 10 Differenzen ≠ 0",
    "mindestens 30 Zeilen",
    "n ≥ 500 verwertbare Zeilen",
    "→ 669 verwertbar",
    "508 verwertbar",
    "ja 164, nein 505",
)


def read_freeze(handover_path) -> str:
    try:
        text = pathlib.Path(handover_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise HypAbort(f"Handover nicht lesbar: {exc!r}") from exc
    block = extract_freeze_block(text)
    md5 = hashlib.md5(block.encode("utf-8")).hexdigest()
    if md5 != FREEZE_BLOCK_MD5:
        raise HypAbort(f"Freeze-Block weicht vom geprüften Stand ab (MD5 {md5} ≠ "
                       f"{FREEZE_BLOCK_MD5}) — kein Lauf ohne Protokolleintrag + Skript-Nachzug.")
    norm = re.sub(r"\s+", " ", block.replace("**", ""))
    missing = [s for s in _REQUIRED_SNIPPETS if s not in norm]
    if missing:
        raise HypAbort(f"Freeze-Block-Gegenprobe fehlgeschlagen: {missing}")
    return md5


# ── 2) Sperre ───────────────────────────────────────────────────────────
def _read_result_rows(results_path) -> list[dict]:
    rows: list[dict] = []
    try:
        with open(results_path, "r", encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except FileNotFoundError:
        pass
    return rows


def check_lock(results_path, stage: int) -> tuple[int, list[str]]:
    """Abbruch bei vorhandener Zeile dieser Stufe. Returnt (Zahl bisheriger
    Bestätigungstest-Zeilen, Hypothesen dieser Stufe)."""
    rows = _read_result_rows(results_path)
    ids = {test_id(h, stage) for h in HYPS}
    for r in rows:
        if r.get("family") == FAMILY[stage] or r.get("test_id") in ids:
            raise HypAbort(f"eval_results.jsonl enthält bereits eine {FAMILY[stage]}-Zeile — "
                           "kein Zweitlauf ohne Protokolleintrag.")
    hyps = list(HYPS)
    if stage == 2:
        fams = {r.get("family") for r in rows}
        missing = [f for f in PREREQ_FAMILIES_S2 if f not in fams]
        if missing:
            raise HypAbort(f"Stufe 2 erst nach {', '.join(missing)} (A.13) — kein Lauf.")
        s1 = {r.get("test_id"): r.get("verdict") for r in rows if r.get("family") == FAMILY[1]}
        if not s1:
            raise HypAbort("Stufe 2 ohne Stufe-1-Ergebnis — kein Lauf.")
        hyps = [h for h in HYPS if s1.get(test_id(h, 1)) in PASS_VERDICTS]
        if not hyps:
            raise HypAbort("Keine Hypothese mit Stufe-1-Verdikt Beleg/bedingt — k = 0, kein Stufe-2-Lauf.")
    return sum(1 for r in rows if r.get("test_id")), hyps


# ── 3) Daten (nur nach Freeze-Check + Sperre) ───────────────────────────
def _parse_dmy(s) -> date | None:
    try:
        return datetime.strptime(str(s), "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return None


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _in_stage(d: date | None, stage: int) -> bool:
    if d is None:
        return False
    return (S1_FROM <= d <= S1_TO) if stage == 1 else (d >= S2_FROM)


def _stream_jsonl(path, stage: int, *, need_provenance: bool):
    """Liest JSONL zeilenweise; behält nur Objekte im Stufenfenster. Alles
    andere wird sofort verworfen (kein Feldzugriff außer date/provenance)."""
    try:
        fh = open(path, "r", encoding="utf-8")
    except OSError as exc:
        raise HypAbort(f"Datei nicht lesbar: {path} ({exc!r})") from exc
    out = []
    with fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if not isinstance(obj, dict):
                continue
            if need_provenance and obj.get("provenance") != PROVENANCE:
                continue
            if not _in_stage(_parse_dmy(obj.get("date")), stage):
                continue
            out.append(obj)
    return out


def _sha256_file(path) -> str | None:
    try:
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def load_stage(stage: int, *, export_path, outcome_path, inst_path) -> dict:
    window = freeze_eval._dedup_rows(_stream_jsonl(export_path, stage, need_provenance=True))
    op = {}
    for z in _stream_jsonl(outcome_path, stage, need_provenance=False):
        op.setdefault((z.get("ticker"), z.get("date")), z)
    try:
        inst_raw = json.loads(pathlib.Path(inst_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HypAbort(f"{inst_path} nicht lesbar: {exc!r}") from exc
    if not isinstance(inst_raw, dict):
        raise HypAbort(f"{inst_path}: unerwartetes Format (kein Objekt).")
    return {"window": window, "op": op, "inst": inst_raw}


# ── 4) Zielgröße (A.1) und Prädiktoren ──────────────────────────────────
def a1_entry(z: dict | None) -> tuple[str | None, dict | None]:
    """(Ausschlussgrund, None) oder (None, {o1, g, hit, bars, z}) nach A.1."""
    if z is None:
        return "zeile_fehlt", None
    if z.get("grund") is not None:
        return f"grund:{z.get('grund')}", None
    bars = z.get("bars")
    if not isinstance(bars, list) or len(bars) != N_BARS or not all(isinstance(b, dict) for b in bars):
        return "bars_unvollstaendig", None
    if not all(_finite(b.get("h")) for b in bars[1:]):
        return "bars_unvollstaendig", None
    o1 = bars[1].get("o")
    if not _finite(o1) or o1 <= 0:
        return "open_tag1_fehlt", None
    g = (max(b["h"] for b in bars[1:]) / o1 - 1) * 100
    return None, {"o1": o1, "g": g, "hit": g >= TARGET_PCT, "bars": bars, "z": z}


def _haircut_fn() -> Callable[[float | None], float | None]:
    """``backtest_history.apply_round_trip_haircut`` ohne den Modul-Import
    (der zieht yfinance). Quelltext der Funktion wird per AST geladen und mit
    ``config.HAIRCUT_ROUND_TRIP_PCT`` ausgeführt — keine zweite Formel."""
    src = (_ROOT / "backtest_history.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "apply_round_trip_haircut"]
    if len(fn) != 1:
        raise HypAbort("apply_round_trip_haircut nicht eindeutig in backtest_history.py gefunden.")
    mod = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
                           fn[0]], type_ignores=[])
    ast.fix_missing_locations(mod)
    ns = {"HAIRCUT_ROUND_TRIP_PCT": config.HAIRCUT_ROUND_TRIP_PCT}
    exec(compile(mod, "backtest_history.py:apply_round_trip_haircut", "exec"), ns)  # noqa: S102
    return ns["apply_round_trip_haircut"]


def _inst_point(inst: dict, ticker, d: date) -> tuple[float | None, int | None, int]:
    """C.2: Punkt mit größtem ``date`` ≤ D. Returnt (Wert, Alter in Tagen,
    Zahl unlesbarer Punktdaten des Tickers)."""
    pts = inst.get(ticker)
    best_d, best_v, bad = None, None, 0
    if not isinstance(pts, list):
        return None, None, 0
    for p in pts:
        if not isinstance(p, dict):
            bad += 1
            continue
        try:
            pd = date.fromisoformat(str(p.get("date")))
        except ValueError:
            bad += 1
            continue
        if pd <= d and (best_d is None or pd > best_d):
            best_d, best_v = pd, p.get("inst_ownership")
    if best_d is None or not _finite(best_v):
        return None, None, bad
    return float(best_v), (d - best_d).days, bad


def build_rows(data: dict) -> dict:
    """Baut je Hypothese die verwendeten Zeilen und Ausschlusszählungen.
    Reine Zuordnung; keine Statistik."""
    excl_a1: dict[str, int] = {}
    base = []
    for r in data["window"]:
        why, e = a1_entry(data["op"].get((r.get("ticker"), r.get("date"))))
        if why:
            excl_a1[why] = excl_a1.get(why, 0) + 1
            continue
        base.append((r, e))
    hg, hi, hk = [], [], []
    ex = {"hg": {}, "hi": {}, "hk": {}}
    hi_age = {"le_7": 0, "gt_7": 0}
    inst_bad = 0
    hk_trunc = 0
    for r, e in base:
        row = dict(r)
        row["_e"] = e
        regime = r.get("market_regime")
        row["_regime"] = regime if regime in REGIMES else "unbekannt"
        c10 = e["bars"][10].get("c")
        if _finite(c10) and c10 > 0:
            row["_hold"] = (c10 / e["o1"] - 1) * 100
            row["_rule"] = TARGET_PCT if e["hit"] else row["_hold"]
            hg.append(row)
        else:
            ex["hg"]["close_tag10_fehlt"] = ex["hg"].get("close_tag10_fehlt", 0) + 1
        d = _parse_dmy(r.get("date"))
        v, age, bad = _inst_point(data["inst"], r.get("ticker"), d)
        inst_bad += bad
        if v is None:
            ex["hi"]["kein_punkt"] = ex["hi"].get("kein_punkt", 0) + 1
        else:
            row_i = dict(row)
            row_i["_x"] = v
            hi_age["le_7" if age <= 7 else "gt_7"] += 1
            hi.append(row_i)
        m = r.get("material_8k_events")
        if not isinstance(m, dict) or m.get("collected") is not True:
            ex["hk"]["nicht_gesammelt"] = ex["hk"].get("nicht_gesammelt", 0) + 1
        else:
            if m.get("truncated") is True:
                hk_trunc += 1
            evs = m.get("events")
            row_k = dict(row)
            row_k["_x"] = 1 if (isinstance(evs, list) and len(evs) > 0) else 0
            hk.append(row_k)
    return {"n_window": len(data["window"]), "excl_a1": excl_a1, "n_usable_a1": len(base),
            "rows": {"hg": hg, "hi": hi, "hk": hk}, "excl": ex, "hi_age": hi_age,
            "inst_unreadable_points": inst_bad, "hk_truncated": hk_trunc}


def check_counts(built: dict, stage: int, hyps: Sequence[str], s1_expected: dict = S1_EXPECTED) -> None:
    """Stufe 1: Zählungen = Block E. Stufe 2: n ≥ 500 je Hypothese (A.13).
    Nur Zeilenzahlen und Prädiktor-Zählungen, kein Ergebnis."""
    if stage == 1:
        got = {"n_window": built["n_window"], "n_usable_a1": built["n_usable_a1"],
               "n_hi": len(built["rows"]["hi"]), "n_hk": len(built["rows"]["hk"]),
               "n_hk_ja": sum(r["_x"] for r in built["rows"]["hk"])}
        if got != s1_expected:
            raise HypAbort(f"Stufe-1-Zählung weicht von Block E ab ({got} statt {s1_expected}) — "
                           "kein Lauf ohne Protokolleintrag.")
        return
    short = {h: len(built["rows"][h]) for h in hyps if len(built["rows"][h]) < S2_N_TRIGGER}
    if short:
        raise HypAbort(f"Stufe-2-Auslöser nicht erreicht (n < {S2_N_TRIGGER}: {short}) — kein Lauf.")


# ── 5) Statistik ────────────────────────────────────────────────────────
def wilcoxon_one_sided(rule: Sequence[float], hold: Sequence[float]) -> dict:
    """B.4 wörtlich: einseitig, Alternative „d nach oben verschoben“.
    W⁺ und Var(W⁺) wie in ``wilcoxon_signed_rank_paired``; Gegenprobe gegen
    deren zweiseitigen p (Abweichung → Abbruch)."""
    ref = wilcoxon_signed_rank_paired(rule, hold)
    d = [a - b for a, b in zip(rule, hold)]
    nz = [x for x in d if x != 0.0]
    n = len(nz)
    out = {"n_nonzero": n, "n_zero_dropped": len(d) - n, "w_plus": ref["w_plus"],
           "p_one_sided": None, "z": None, "p_two_sided_ref": ref["p_two_sided"]}
    if n == 0:
        return out
    ranks, ties = _ranks_with_ties([abs(x) for x in nz])
    w_plus = sum(r for r, x in zip(ranks, nz) if x > 0)
    mean_w = n * (n + 1) / 4.0
    var_w = n * (n + 1) * (2 * n + 1) / 24.0 - sum(t ** 3 - t for t in ties) / 48.0
    if var_w <= 0:
        return out
    if ref["w_plus"] is None or abs(w_plus - ref["w_plus"]) > 1e-9:
        raise HypAbort("Wilcoxon-W⁺ weicht von stats_helpers ab.")
    z_two = max(0.0, abs(w_plus - mean_w) - 0.5) / math.sqrt(var_w)
    p_two = max(0.0, min(1.0, 2.0 * (1.0 - _normal_cdf(z_two))))
    if ref["p_two_sided"] is None or abs(p_two - ref["p_two_sided"]) > 1e-12:
        raise HypAbort("Wilcoxon-Varianz weicht von stats_helpers ab.")
    z = (w_plus - mean_w - 0.5) / math.sqrt(var_w)
    out.update({"w_plus": w_plus, "z": z, "p_one_sided": max(0.0, min(1.0, 1.0 - _normal_cdf(z)))})
    return out


def holm_adjusted(p_in: dict, order: Sequence[str]) -> tuple[dict, dict]:
    """A.15 „Holm-korrigierter p“: Standard-Holm-Adjustierung
    p_adj(i) = max_{j ≤ i} min(1, (k − j)·p_(j)) über die aufsteigend sortierten
    p (j 0-basiert), dazu die Schwelle α/(k − j) je Rang. Entscheidung bleibt bei
    ``multiple_testing_correction`` (Gegenprobe im Aufrufer)."""
    k = len(order)
    srt = sorted(order, key=lambda h: p_in[h])   # stabil wie stats_helpers
    adj, thr, run = {}, {}, 0.0
    for j, h in enumerate(srt):
        run = max(run, min(1.0, (k - j) * p_in[h]))
        adj[h] = run
        thr[h] = ALPHA / (k - j)
    return adj, thr


def _side(v, base) -> int:
    if v is None or v == base:
        return 0
    return 1 if v > base else -1


def regime_auc(rows, hit_key: Callable[[dict], bool], overall_auc) -> tuple[str, dict]:
    """C.7/D.6: prüfbar, wenn beide Gruppen im Regime ≥ 30 Zeilen haben;
    „unbekannt“ nie prüfbar."""
    detail, side0 = {}, _side(overall_auc, 0.5)
    checked, contra = False, False
    for reg in REGIMES + ("unbekannt",):
        rr = [r for r in rows if r["_regime"] == reg]
        a = [r["_x"] for r in rr if hit_key(r)]
        b = [r["_x"] for r in rr if not hit_key(r)]
        if reg == "unbekannt" or len(a) < REGIME_MIN_AUC or len(b) < REGIME_MIN_AUC:
            detail[reg] = {"n_a": len(a), "n_b": len(b), "status": "nicht_pruefbar"}
            continue
        auc = mann_whitney_u_auc(a, b)["auc"]
        s = _side(auc, 0.5)
        ok = side0 == 0 or s == 0 or s == side0
        detail[reg] = {"n_a": len(a), "n_b": len(b), "auc": auc,
                       "status": "plausibel" if ok else "widerlegt"}
        checked, contra = True, contra or not ok
    return ("widerlegt" if contra else "plausibel" if checked else "nicht_pruefbar"), detail


def regime_mean_delta(rows, overall_delta) -> tuple[str, dict]:
    """B.7: prüfbar ab 30 Paaren und 10 Differenzen ≠ 0; „unbekannt“ nie."""
    detail, side0 = {}, _side(overall_delta, 0.0)
    checked, contra = False, False
    for reg in REGIMES + ("unbekannt",):
        rr = [r for r in rows if r["_regime"] == reg]
        nz = sum(1 for r in rr if r["_rule"] - r["_hold"] != 0.0)
        if reg == "unbekannt" or len(rr) < REGIME_MIN_PAIRS or nz < REGIME_MIN_NONZERO:
            detail[reg] = {"n": len(rr), "n_nonzero": nz, "status": "nicht_pruefbar"}
            continue
        md = sum(r["_rule"] for r in rr) / len(rr) - sum(r["_hold"] for r in rr) / len(rr)
        s = _side(md, 0.0)
        ok = side0 == 0 or s == 0 or s == side0
        detail[reg] = {"n": len(rr), "n_nonzero": nz, "mean_delta": md,
                       "status": "plausibel" if ok else "widerlegt"}
        checked, contra = True, contra or not ok
    return ("widerlegt" if contra else "plausibel" if checked else "nicht_pruefbar"), detail


def _auc_block(rows, hit_key) -> dict:
    a = [r["_x"] for r in rows if hit_key(r)]
    b = [r["_x"] for r in rows if not hit_key(r)]
    boot = freeze_eval.bootstrap_auc_ci(a, b, n_iter=BOOT_N, seed=BOOT_SEED, lo_pct=CI_LO, hi_pct=CI_HI)
    return {"n_a": len(a), "n_b": len(b), "auc": boot["point_auc"], "ci_lo": boot["ci_lo"],
            "ci_hi": boot["ci_hi"], "p_two_sided": boot["p_two_sided"], "note": boot["note"]}


def _hg_block(rows, rule_key="_rule", hold_key="_hold") -> dict:
    rule = [r[rule_key] for r in rows]
    hold = [r[hold_key] for r in rows]
    w = wilcoxon_one_sided(rule, hold)
    md = freeze_eval.paired_bootstrap_mean_delta(rule, hold, n_iter=BOOT_N, seed=BOOT_SEED,
                                                 lo_pct=CI_LO, hi_pct=CI_HI)
    return {"n_pairs": len(rows), "wilcoxon": w, "mean_delta": md["point_delta"],
            "ci_lo": md["ci_lo"], "ci_hi": md["ci_hi"], "note": md["note"],
            "n_d_negative": sum(1 for a, b in zip(rule, hold) if a - b < 0)}


def verdict_for(floor_ok: bool, holm_sig: bool, ci_ok: bool, regime_status: str) -> tuple[str, str]:
    """A.8 wörtlich."""
    if not floor_ok:
        return "nicht auswertbar", "Floor verfehlt — p = 1 im Holm-Schritt"
    if not (holm_sig and ci_ok):
        failed = [n for n, ok in (("holm_significant", holm_sig), ("ci_kriterium", ci_ok)) if not ok]
        return "Unklar", f"Kriterien nicht erfüllt: {', '.join(failed)} — keine Widerlegung"
    if regime_status == "plausibel":
        return "Beleg", "(a) Holm, (b) CI-Kriterium und (c) Regime-Split plausibel erfüllt"
    if regime_status == "nicht_pruefbar":
        return "bedingt", "(a)+(b) erfüllt, aber kein Regime prüfbar"
    return "Unklar", "(a)+(b) erfüllt, aber ein prüfbares Regime widerspricht — keine Widerlegung"


def _hit(r) -> bool:
    return r["_e"]["hit"]


def evaluate(built: dict, hyps: Sequence[str], stage: int, *, hashes: dict, md5: str,
             now: datetime, tests_before: int, haircut: Callable) -> list[dict]:
    rows = built["rows"]
    res: dict[str, dict] = {}
    # H-G
    if "hg" in hyps:
        hg = rows["hg"]
        main = _hg_block(hg)
        p = main["wilcoxon"]["p_one_sided"]
        floor_ok = main["wilcoxon"]["n_nonzero"] >= FLOOR
        reg_status, reg_detail = regime_mean_delta(hg, main["mean_delta"])
        # Nur berichtet (B.9): Netto, Vergleich „ab Close D“, Momentum-Hälften.
        net_rows = []
        for r in hg:
            nr, nh = haircut(r["_rule"]), haircut(r["_hold"])
            if _finite(nr) and _finite(nh):
                net_rows.append({"_rule": nr, "_hold": nh})
        cd_rows, cd_excl = [], 0
        for r in hg:
            z = r["_e"]["z"]
            cd, mg, c10 = z.get("close_d"), z.get("max_gain_from_entry_pct"), r["_e"]["bars"][10].get("c")
            if not (_finite(cd) and cd > 0 and _finite(mg) and _finite(c10)):
                cd_excl += 1
                continue
            hold_c = (c10 / cd - 1) * 100
            cd_rows.append({"_hold": hold_c, "_rule": TARGET_PCT if mg >= TARGET_PCT else hold_c})
        with_m = [r for r in hg if _finite(r.get("entry_past_return_5d"))]
        halves = {"n_ohne_momentum": len(hg) - len(with_m)}
        if with_m:
            vals = sorted(r["entry_past_return_5d"] for r in with_m)
            k = len(vals)
            med = vals[k // 2] if k % 2 else (vals[k // 2 - 1] + vals[k // 2]) / 2
            for name, grp in (("niedrig_le_median", [r for r in with_m if r["entry_past_return_5d"] <= med]),
                              ("hoch_gt_median", [r for r in with_m if r["entry_past_return_5d"] > med])):
                halves[name] = {"n": len(grp), "mean_delta": (sum(r["_rule"] - r["_hold"] for r in grp) / len(grp))
                                if grp else None}
            halves["median"] = med

        def _hg_point(rs):
            if not rs:
                return {"mean_delta": None}
            return {"mean_delta": sum(r["_rule"] - r["_hold"] for r in rs) / len(rs)}
        cluster = freeze_eval.cluster_double_run(list(hg), _hg_point, point_key="mean_delta", baseline=0.0)
        res["hg"] = {"p": p, "floor_ok": floor_ok, "ci_ok": main["ci_lo"] is not None and main["ci_lo"] > 0,
                     "reg": (reg_status, reg_detail), "cluster": cluster, "used": hg,
                     "body": {"target": "Gewinnziel +30 % ab Eröffnung Tag 1 vs. Halten bis Schluss Tag 10",
                              "statistic": main, "n_a": None, "n_b": None,
                              "nur_berichtet": {
                                  "netto": dict(_hg_block(net_rows), faktor_hinweis="k = 0,98/1,02"),
                                  "ab_close_d": dict(_hg_block(cd_rows), n_ausgeschlossen=cd_excl),
                                  "momentum_haelften": halves}}}
    for h in ("hi", "hk"):
        if h not in hyps:
            continue
        rs = rows[h]
        main = _auc_block(rs, _hit)
        n_hit = main["n_a"]
        if h == "hi":
            floor_ok = n_hit >= FLOOR
            ci_ok = main["ci_hi"] is not None and main["ci_hi"] < 0.5
        else:
            n_ja = sum(r["_x"] for r in rs)
            floor_ok = n_hit >= FLOOR and n_ja >= FLOOR and (len(rs) - n_ja) >= FLOOR
            ci_ok = main["ci_lo"] is not None and main["ci_lo"] > 0.5
        reg_status, reg_detail = regime_auc(rs, _hit, main["auc"])

        def _net_hit(r):
            v = haircut(r["_e"]["g"])
            return _finite(v) and v >= TARGET_PCT
        net = _auc_block(rs, _net_hit)
        cd_rows = [r for r in rs if _finite(r["_e"]["z"].get("max_gain_from_entry_pct"))]
        cd = _auc_block(cd_rows, lambda r: r["_e"]["z"]["max_gain_from_entry_pct"] >= TARGET_PCT)
        cd["n_ausgeschlossen"] = len(rs) - len(cd_rows)

        def _auc_point(sub):
            a = [r["_x"] for r in sub if _hit(r)]
            b = [r["_x"] for r in sub if not _hit(r)]
            if not a or not b:
                return {"auc": None}
            return {"auc": mann_whitney_u_auc(a, b)["auc"]}
        cluster = freeze_eval.cluster_double_run(list(rs), _auc_point, point_key="auc", baseline=0.5)
        extra = {"netto": net, "ab_close_d": cd}
        if h == "hk":
            ja = [r for r in rs if r["_x"] == 1]
            nein = [r for r in rs if r["_x"] == 0]
            extra["trefferquote"] = {
                "ja": {"n": len(ja), "treffer": sum(1 for r in ja if _hit(r))},
                "nein": {"n": len(nein), "treffer": sum(1 for r in nein if _hit(r))}}
            extra["truncated"] = built["hk_truncated"]
        else:
            extra["punkt_alter_tage"] = built["hi_age"]
            extra["unlesbare_punktdaten"] = built["inst_unreadable_points"]
        res[h] = {"p": main["p_two_sided"], "floor_ok": floor_ok, "ci_ok": ci_ok,
                  "reg": (reg_status, reg_detail), "cluster": cluster, "used": rs,
                  "body": {"target": ("Treffer ab Eröffnung Tag 1 (g ≥ 30) vs. inst_ownership, erwartet AUC < 0,5"
                                      if h == "hi" else
                                      "Treffer ab Eröffnung Tag 1 (g ≥ 30) vs. 8-K ja/nein, erwartet AUC > 0,5"),
                           "statistic": main, "n_a": main["n_a"], "n_b": main["n_b"],
                           "nur_berichtet": extra}}
    order = [h for h in HYPS if h in res]
    p_in = {h: (res[h]["p"] if (res[h]["floor_ok"] and res[h]["p"] is not None) else 1.0) for h in order}
    holm = multiple_testing_correction([p_in[h] for h in order], labels=order, alpha=ALPHA)
    holm_by = {row["label"]: bool(row["holm_reject"]) for row in holm["results"]}
    adj, thr = holm_adjusted(p_in, order)
    if any((adj[h] < ALPHA) != holm_by[h] for h in order):
        raise HypAbort("Holm-adjustierter p widerspricht multiple_testing_correction.")
    commit = freeze_eval._git_commit_hash()
    out = []
    for h in order:
        r = res[h]
        verdict, reason = verdict_for(r["floor_ok"], holm_by[h], r["ci_ok"], r["reg"][0])
        if r["cluster"].get("same_direction") is False:
            reason += " (Cluster-Doppellauf: andere Richtung — nur berichtet, ändert das Verdikt nicht)"
        used = r["used"]
        n_split = sum(1 for u in used if u["_e"]["z"].get("split_im_fenster") is True)
        n_div = sum(1 for u in used if u["_e"]["z"].get("dividende_im_fenster") is True)
        pk = "mean_delta" if h == "hg" else "auc"
        out.append({
            "schema_v": SCHEMA_V,
            "family": FAMILY[stage],
            "test_id": test_id(h, stage),
            "stage": stage,
            "target": r["body"]["target"],
            "freeze_date": FREEZE_DATE,
            "protocol_ref": PROTOCOL_REF,
            "evaluated_at": now.isoformat(),
            "n_window": built["n_window"],
            "excluded_a1": dict(sorted(built["excl_a1"].items())),
            "excluded_hypothesis": dict(sorted(built["excl"][h].items())),
            "n_used": len(used),
            "n_a": r["body"]["n_a"], "n_b": r["body"]["n_b"],
            "floor": FLOOR, "floor_ok": r["floor_ok"],
            "statistic": r["body"]["statistic"],
            "p_raw": r["p"],
            "p_holm_input": p_in[h],
            "p_holm_adjusted": adj[h],
            "holm": {"k": len(order), "alpha": ALPHA, "method": "holm", "labels": order,
                     "schwelle_rang": thr[h],
                     "reject": holm_by[h]},
            "holm_reject": holm_by[h],
            "criteria": {"holm_significant": holm_by[h], "ci_kriterium": r["ci_ok"],
                         "regime_split_status": r["reg"][0]},
            "regime_split": {"status": r["reg"][0], "detail": r["reg"][1]},
            "cluster_double_run": {
                "with": r["cluster"]["with_cluster"].get(pk),
                "without": r["cluster"]["without_cluster"].get(pk),
                "n_cluster_followups_removed": r["cluster"]["n_cluster_followups_removed"],
                "same_direction": r["cluster"]["same_direction"], "nur_berichtet": True},
            "nur_berichtet": r["body"]["nur_berichtet"],
            "n_split_im_fenster": n_split, "n_dividende_im_fenster": n_div,
            "verdict": verdict, "verdict_reason": reason,
            "bootstrap_seed": BOOT_SEED, "bootstrap_n": BOOT_N,
            "ci_method": f"95% zweiseitig, Perzentil {CI_LO}/{CI_HI}",
            "data_hash": freeze_eval._data_hash(used),
            "data_hash_files": hashes,
            "freeze_block_md5": md5,
            "script_commit_hash": commit,
            "confirmatory_tests_before": tests_before,
            "confirmatory_tests_total": tests_before + len(order),
        })
    return out


def push_body(rows: Sequence[dict]) -> str:
    """Nur Verdikte + Gesamtzahl Bestätigungstests — keine Ergebniszahlen."""
    if not rows:
        return "Hypothesen-Runde November 2026: keine Ergebniszeile."
    stage = rows[0]["stage"]
    names = {"hg": "H-G Gewinnziel", "hi": "H-I Inst-Beteiligung", "hk": "H-K 8-K"}
    parts = [f"{names[r['test_id'][:2]]}: {r['verdict']}" for r in rows]
    return (f"Hypothesen-Runde November 2026, Stufe {stage} ausgewertet (einmaliger Lauf). "
            + ". ".join(parts) + f". Bestätigungstests bisher gesamt: "
            f"{rows[0]['confirmatory_tests_total']}. Details in {config.EVAL_RESULTS_FILE}.")


# ── 6) Orchestrierung ───────────────────────────────────────────────────
def _location_guard(env=None) -> None:
    env = os.environ if env is None else env
    if env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REF") != "refs/heads/main":
        raise HypAbort("Lauf nur im GitHub-Workflow auf main erlaubt "
                       "(GITHUB_ACTIONS=true, GITHUB_REF=refs/heads/main).")


def run_stage(stage: int, *, handover_path, results_path, export_path, outcome_path, inst_path,
              now: datetime | None = None, env=None,
              send_push: Callable[[str, str], object] | None = None,
              s1_expected: dict = S1_EXPECTED) -> list[dict]:
    if stage not in (1, 2):
        raise HypAbort(f"Unbekannte Stufe {stage}.")
    _location_guard(env)
    md5 = read_freeze(handover_path)
    tests_before, hyps = check_lock(results_path, stage)
    haircut = _haircut_fn()
    data = load_stage(stage, export_path=export_path, outcome_path=outcome_path, inst_path=inst_path)
    built = build_rows(data)
    check_counts(built, stage, hyps, s1_expected)
    hashes = {"matured_backtest_export.jsonl": _sha256_file(export_path),
              "outcome_path.jsonl": _sha256_file(outcome_path),
              "inst_ownership_history.json": _sha256_file(inst_path)}
    rows = evaluate(built, hyps, stage, hashes=hashes, md5=md5,
                    now=now or datetime.now(timezone.utc), tests_before=tests_before, haircut=haircut)
    freeze_eval._append_results(str(results_path), rows)
    if send_push is not None:
        send_push(f"Freeze-Auswertung: Hypothesen-Runde Nov 2026, Stufe {stage}", push_body(rows))
    return rows


def _default_push(title: str, body: str) -> None:
    import health_check_digest as hcd  # noqa: E402 — lazy, nur im echten Lauf
    hcd._ntfy_send(title, body, "high", "science")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hypothesen-Runde November 2026 — einmalige Freeze-Auswertung")
    ap.add_argument("--run", action="store_true", help="Auswertung wirklich starten")
    ap.add_argument("--stage", type=int, choices=(1, 2), required=False)
    args = ap.parse_args(argv)
    if not args.run or args.stage is None:
        print("Kein Lauf: --run und --stage fehlen. Auswertung nur über den Workflow "
              "health_check_digest.yml (Input hypothesen_nov26_s1).")
        return 2
    try:
        rows = run_stage(args.stage, handover_path=_ROOT / HANDOVER_FILE,
                         results_path=_ROOT / config.EVAL_RESULTS_FILE,
                         export_path=_ROOT / config.MATURED_EXPORT_FILE,
                         outcome_path=_ROOT / config.OUTCOME_PATH_FILE,
                         inst_path=_ROOT / INST_FILE, send_push=_default_push)
    except HypAbort as exc:
        print(f"ABBRUCH (nichts ausgewertet/geschrieben): {exc}")
        return 1
    print(push_body(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
