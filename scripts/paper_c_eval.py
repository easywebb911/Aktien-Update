"""Paper C (Momentum → Gipfel) — einmalige Freeze-Auswertung.

Setzt den Block „### VORABREGISTRIERUNG — Paper C (Momentum → Gipfel),
eingefroren 07.11.2026" aus ``SESSION_HANDOVER.md`` um (PR #660, gemergt
07.11.2026). Der Freeze-Block ist die EINZIGE Quelle für Stichprobe, Ziele
und Verfahrens-Parameter: das Skript liest sie aus dem Block (``read_freeze``)
und bricht ab, wenn der Block fehlt, inhaltlich vom gebauten/getesteten Stand
abweicht (MD5-Pin) oder ein Parameter nicht eindeutig lesbar ist.

Ablauf von ``run_paper_c`` — die Reihenfolge IST die Schutz-Mechanik:

  1. Lauf-Ort-Guard (nur GitHub Actions, nur ``refs/heads/main``).
  2. Freeze-Check (Block finden, MD5-Pin, Parameter lesen).
  3. Sperre: gibt es in ``eval_results.jsonl`` schon eine ``paper_c``-Zeile,
     Abbruch (kein Zweitlauf ohne Protokolleintrag).
  4. ERST JETZT wird der Export geöffnet (``_load_sample``) — und die
     Fenster-Zählung muss der Freeze-Zählung entsprechen (672 / 4), sonst
     Abbruch, bevor irgendein Ergebnis gerechnet wird.
  5. Auswertung, Anhängen an ``eval_results.jsonl``, ein ntfy-Push mit dem
     Verdikt je Ziel (keine Zahlen außer der Zahl bisheriger Bestätigungstests).

Wiederverwendet (nicht kopiert): ``freeze_eval.bootstrap_auc_ci``,
``freeze_eval.cluster_double_run``, ``freeze_eval._dedup_rows``,
``freeze_eval._data_hash``, ``freeze_eval._git_commit_hash``,
``freeze_eval._append_results``, ``stats_helpers.mann_whitney_u_auc``,
``stats_helpers.multiple_testing_correction``,
``health_check._read_matured_export_rows``, ``health_check_digest._ntfy_send``.
``freeze_eval.py``/``stats_helpers.py`` werden NICHT verändert (geschützte
Ganzdateien).

Aufruf (nur im Workflow ``health_check_digest.yml``, Input ``paper_c``)::

    python scripts/paper_c_eval.py --run

Ohne ``--run`` passiert nichts außer einem Hinweis (Exit 2).
"""
from __future__ import annotations

import argparse
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
import health_check as hc  # noqa: E402
from stats_helpers import mann_whitney_u_auc, multiple_testing_correction  # noqa: E402

SCHEMA_V = 1
FAMILY = "paper_c"
TEST_ID_PEAK = "paper_c_gipfel"
TEST_ID_R10 = "paper_c_return_10d"
HANDOVER_FILE = "SESSION_HANDOVER.md"
FREEZE_HEADING = "### VORABREGISTRIERUNG — Paper C (Momentum → Gipfel), eingefroren 07.11.2026"
# MD5 des Freeze-Blocks (Überschrift bis vor die nächste Überschrift der
# Ebene ≤ 3, Zeilen mit "\n" verbunden) im Stand von main nach dem Merge von
# PR #660. Jede Änderung am Block (auch ein Protokolleintrag) → Abbruch; das
# Skript muss dann bewusst nachgezogen und neu geprüft werden.
FREEZE_BLOCK_MD5 = "51e187ad6c7a0fd9ce8bbf8f8166b47c"
PROTOCOL_REF = ("SESSION_HANDOVER.md, VORABREGISTRIERUNG — Paper C (Momentum → Gipfel), "
                "eingefroren 07.11.2026 (PR #660); Holm-Familie Runde November 2026, "
                "Option (iii)")
REGIMES = ("bull", "bear", "neutral")
VERDICT_LABELS = ("Beleg", "bedingt", "Unklar", "nicht auswertbar")


class PaperCAbort(RuntimeError):
    """Kontrollierter Abbruch — es wurde nichts ausgewertet/geschrieben."""


# ── 1) Freeze-Block lesen ───────────────────────────────────────────────
def extract_freeze_block(handover_text: str) -> str:
    """Block ab der Freeze-Überschrift bis vor die nächste Überschrift der
    Ebene ≤ 3 (gleiche Abgrenzung wie der Schutz-Lint). Abbruch, wenn die
    Überschrift fehlt oder nicht eindeutig ist."""
    lines = handover_text.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln == FREEZE_HEADING]
    if len(idx) != 1:
        raise PaperCAbort(f"Freeze-Block 'Paper C' nicht eindeutig gefunden ({len(idx)} Treffer).")
    start = idx[0]
    end = start + 1
    while end < len(lines):
        m = re.match(r"^(#{1,6})\s", lines[end])
        if m and len(m.group(1)) <= 3:
            break
        end += 1
    return "\n".join(lines[start:end])


def _num(s: str) -> float:
    return float(s.replace("+", "").replace("−", "-").replace(",", "."))


# (Name, Regex auf dem normalisierten Blocktext, Umwandlung)
_PARAM_PATTERNS: list[tuple[str, str, Callable]] = [
    ("date_from", r"von (\d\d\.\d\d\.\d{4}) bis einschließlich (\d\d\.\d\d\.\d{4})", None),
    ("provenance", r"Zeilen mit `provenance == \"(\w+)\"`", str),
    ("n_window_at_freeze", r"Zählung beim Freeze \(nur Zeilen, keine Ergebnisse\): (\d+) Zeilen, davon (\d+) ohne `entry_past_return_5d`", None),
    ("peak_threshold", r"Treffer = `max_gain_pct ≥ ([\d,]+)`; Nicht-Treffer = `max_gain_pct < ([\d,]+)`", None),
    ("r10_thresholds", r"Gewinner = `return_10d ≥ ([+\d,]+)`; Verlierer = `return_10d ≤ ([−\d,]+)`", None),
    ("bootstrap", r"N = (\d+), Seed = (\d+), 95 % zweiseitig, Perzentil ([\d,]+) / ([\d,]+)", None),
    ("regime_min", r"in diesem Regime mindestens (\d+) Zeilen hat", int),
    ("floor", r"mindestens (\d+) Treffer bzw\. Gewinner je Ziel", int),
    ("alpha_split", r"der kleinere p wird gegen α/3 ≈ ([\d,]+) geprüft, nur wenn er besteht, der größere gegen 2α/3 ≈ ([\d,]+) \(α = ([\d,]+)\)", None),
    ("net_threshold", r"dieselbe Rechnung mit Treffer = `max_gain_pct_net ≥ ([\d,]+)`", None),
]


def read_freeze(handover_path) -> dict:
    """Liest den Freeze-Block (MD5-Pin) und die Parameter daraus."""
    try:
        text = pathlib.Path(handover_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise PaperCAbort(f"Handover nicht lesbar: {exc!r}") from exc
    block = extract_freeze_block(text)
    md5 = hashlib.md5(block.encode("utf-8")).hexdigest()
    if md5 != FREEZE_BLOCK_MD5:
        raise PaperCAbort(f"Freeze-Block weicht vom geprüften Stand ab (MD5 {md5} ≠ "
                          f"{FREEZE_BLOCK_MD5}) — kein Lauf ohne Protokolleintrag + Skript-Nachzug.")
    norm = re.sub(r"\s+", " ", block.replace("**", ""))
    found: dict = {}
    for name, pat, _conv in _PARAM_PATTERNS:
        hits = re.findall(pat, norm)
        if len(hits) != 1:
            raise PaperCAbort(f"Parameter '{name}' im Freeze-Block nicht eindeutig lesbar ({len(hits)} Treffer).")
        found[name] = hits[0]
    d_from, d_to = found["date_from"]
    n_win, n_epr_missing = found["n_window_at_freeze"]
    p_hit, p_miss = found["peak_threshold"]
    w_thr, l_thr = found["r10_thresholds"]
    b_n, b_seed, b_lo, b_hi = found["bootstrap"]
    a3, a23, alpha = found["alpha_split"]
    params = {
        "date_from": datetime.strptime(d_from, "%d.%m.%Y").date(),
        "date_to": datetime.strptime(d_to, "%d.%m.%Y").date(),
        "provenance": found["provenance"],
        "n_window_at_freeze": int(n_win),
        "n_epr_missing_at_freeze": int(n_epr_missing),
        "peak_threshold": _num(p_hit),
        "r10_win": _num(w_thr),
        "r10_loss": _num(l_thr),
        "bootstrap_n": int(b_n),
        "bootstrap_seed": int(b_seed),
        "ci_lo_pct": _num(b_lo),
        "ci_hi_pct": _num(b_hi),
        "regime_min": int(found["regime_min"]),
        "floor": int(found["floor"]),
        "alpha": _num(alpha),
        "alpha_paper_c": 2 * _num(alpha) / 3,
        "net_threshold": _num(found["net_threshold"]),
        "block_md5": md5,
    }
    if _num(p_hit) != _num(p_miss):
        raise PaperCAbort("Gipfel-Schwelle Treffer/Nicht-Treffer im Block uneinheitlich.")
    # Gegenprobe der gerundeten α-Angaben im Text gegen 2α/3-Holm.
    if (abs(params["alpha"] / 3 - _num(a3)) > 5e-5
            or abs(params["alpha_paper_c"] - _num(a23)) > 5e-5):
        raise PaperCAbort("α-Angaben im Freeze-Block passen nicht zu 2α/3 mit Holm innen.")
    return params


# ── 2) Sperre / Bestätigungstest-Zählung ───────────────────────────────
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


def check_lock(results_path) -> int:
    """Abbruch bei vorhandener paper_c-Zeile; sonst Anzahl bisheriger
    Bestätigungstest-Zeilen (Zeilen mit ``test_id``)."""
    rows = _read_result_rows(results_path)
    for r in rows:
        if r.get("family") == FAMILY or str(r.get("test_id", "")).startswith("paper_c"):
            raise PaperCAbort("eval_results.jsonl enthält bereits eine paper_c-Zeile — "
                              "kein Zweitlauf ohne Protokolleintrag.")
    return sum(1 for r in rows if r.get("test_id"))


# ── 3) Stichprobe (öffnet den Export — NUR nach Freeze-Check + Sperre) ─
def _parse_date(s) -> date | None:
    try:
        return datetime.strptime(str(s), "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return None


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _load_sample(export_path, params: dict) -> tuple[list[dict], list[dict]]:
    """Liest den Export, filtert das Freeze-Fenster, dedupliziert und prüft
    die Fenster-Zählung gegen den Block. Returnt ``(verwendet, ausgeschlossen)``."""
    res = hc._read_matured_export_rows(str(export_path))
    if res is None:
        raise PaperCAbort(f"Export nicht lesbar: {export_path}")
    window = []
    for r in res[1]:
        if r.get("provenance") != params["provenance"]:
            continue
        d = _parse_date(r.get("date"))
        if d is None or not (params["date_from"] <= d <= params["date_to"]):
            continue
        window.append(r)
    window = freeze_eval._dedup_rows(window)
    used = [r for r in window if _finite(r.get("entry_past_return_5d"))]
    excluded = [r for r in window if not _finite(r.get("entry_past_return_5d"))]
    if len(window) != params["n_window_at_freeze"] or len(excluded) != params["n_epr_missing_at_freeze"]:
        raise PaperCAbort(
            f"Stichprobe weicht von der Freeze-Zählung ab (Fenster {len(window)} statt "
            f"{params['n_window_at_freeze']}, ohne entry_past_return_5d {len(excluded)} statt "
            f"{params['n_epr_missing_at_freeze']}) — kein Lauf ohne Protokolleintrag.")
    return used, excluded


# ── 4) Statistik je Ziel ────────────────────────────────────────────────
def _target_groups(rows: Sequence[dict], target: str, params: dict):
    """Teilt in (A = Treffer/Gewinner, B = Nicht-Treffer/Verlierer,
    n_target_excluded). Ziel 2: Zeilen zwischen den Schwellen gehören nicht
    dazu (kein Ausschluss im Sinne fehlender Werte)."""
    a, b, excl = [], [], 0
    for r in rows:
        if target == "peak":
            v = r.get("max_gain_pct")
            if not _finite(v):
                excl += 1
                continue
            (a if v >= params["peak_threshold"] else b).append(r)
        elif target == "net":
            v = r.get("max_gain_pct_net")
            if not _finite(v):
                excl += 1
                continue
            (a if v >= params["net_threshold"] else b).append(r)
        else:
            v = r.get("return_10d")
            if not _finite(v):
                excl += 1
                continue
            if v >= params["r10_win"]:
                a.append(r)
            elif v <= params["r10_loss"]:
                b.append(r)
    return a, b, excl


def _epr(rows):
    return [r["entry_past_return_5d"] for r in rows]


def _side(auc) -> int:
    if auc is None or auc == 0.5:
        return 0
    return 1 if auc > 0.5 else -1


def regime_split(a_rows, b_rows, overall_auc, regime_min: int) -> tuple[str, dict]:
    """Regime prüfbar nur, wenn BEIDE Gruppen im Regime ≥ ``regime_min``
    Zeilen haben. „widerlegt" = ein prüfbares Regime liegt auf der anderen
    Seite von 0,5 als die Gesamt-AUC (AUC genau 0,5 ist keine Gegenrichtung)."""
    detail: dict = {}
    overall_side = _side(overall_auc)
    any_checked = False
    contradiction = False
    for reg in REGIMES:
        ga = [r for r in a_rows if r.get("market_regime") == reg]
        gb = [r for r in b_rows if r.get("market_regime") == reg]
        if len(ga) < regime_min or len(gb) < regime_min:
            detail[reg] = {"n_a": len(ga), "n_b": len(gb), "status": "nicht_pruefbar"}
            continue
        auc = mann_whitney_u_auc(_epr(ga), _epr(gb))["auc"]
        side = _side(auc)
        agrees = overall_side == 0 or side == 0 or side == overall_side
        detail[reg] = {"n_a": len(ga), "n_b": len(gb), "auc": auc,
                       "status": "plausibel" if agrees else "widerlegt"}
        any_checked = True
        contradiction = contradiction or not agrees
    n_other = sum(1 for r in list(a_rows) + list(b_rows) if r.get("market_regime") not in REGIMES)
    detail["_ohne_regime"] = n_other
    if contradiction:
        return "widerlegt", detail
    if not any_checked:
        return "nicht_pruefbar", detail
    return "plausibel", detail


def _target_stats(rows, target: str, params: dict) -> dict:
    a, b, excl = _target_groups(rows, target, params)
    boot = freeze_eval.bootstrap_auc_ci(
        _epr(a), _epr(b), n_iter=params["bootstrap_n"], seed=params["bootstrap_seed"],
        lo_pct=params["ci_lo_pct"], hi_pct=params["ci_hi_pct"])
    return {"a": a, "b": b, "n_target_excluded": excl, "boot": boot}


def _auc_eval_fn(target: str, params: dict):
    def _fn(rows):
        a, b, _ = _target_groups(rows, target, params)
        if not a or not b:
            return {"auc": None}
        return {"auc": mann_whitney_u_auc(_epr(a), _epr(b))["auc"]}
    return _fn


def verdict_for(floor_ok: bool, holm_sig: bool, ci_ok: bool, regime_status: str) -> tuple[str, str]:
    if not floor_ok:
        return "nicht auswertbar", "Floor unterschritten — p = 1 in Holm, kein Urteil"
    if not (holm_sig and ci_ok):
        failed = [n for n, ok in (("holm_significant", holm_sig), ("ci_lo_above_0_5", ci_ok)) if not ok]
        return "Unklar", f"Kriterien nicht erfüllt: {', '.join(failed)} — keine Widerlegung (Freeze-Grenze)"
    if regime_status == "plausibel":
        return "Beleg", "Holm, CI-Untergrenze > 0,5 und Regime-Split plausibel erfüllt"
    if regime_status == "nicht_pruefbar":
        return "bedingt", "Holm + CI erfüllt, aber kein Regime prüfbar (je Gruppe < Mindestgröße)"
    return "Unklar", "Holm + CI erfüllt, aber ein prüfbares Regime widerspricht — keine Widerlegung"


def evaluate(used: Sequence[dict], excluded: Sequence[dict], params: dict, *,
             now: datetime | None = None, tests_before: int = 0) -> list[dict]:
    """Reine Auswertung (keine Datei-/Netz-Zugriffe). Returnt die zwei
    eval_results-Zeilen (eine je Ziel, feste Reihenfolge)."""
    now = now or datetime.now(timezone.utc)
    n_window = len(used) + len(excluded)
    stats = {t: _target_stats(used, t, params) for t in ("peak", "r10")}
    p_inputs = {}
    floor_ok = {}
    for t, s in stats.items():
        floor_ok[t] = len(s["a"]) >= params["floor"]
        p = s["boot"]["p_two_sided"]
        p_inputs[t] = p if (floor_ok[t] and p is not None) else 1.0
    holm = multiple_testing_correction([p_inputs["peak"], p_inputs["r10"]],
                                       labels=["peak", "r10"], alpha=params["alpha_paper_c"])
    holm_by = {row["label"]: bool(row["holm_reject"]) for row in holm["results"]}

    net = _target_stats(used, "net", params)
    net_info = {
        "nachrangig_nicht_bindend": True,
        "n_a": len(net["a"]), "n_b": len(net["b"]),
        "n_ohne_netto": net["n_target_excluded"],
        "auc": net["boot"]["point_auc"], "ci_lo": net["boot"]["ci_lo"],
        "ci_hi": net["boot"]["ci_hi"], "p_two_sided": net["boot"]["p_two_sided"],
        "floor_erreicht": len(net["a"]) >= params["floor"],
        "hinweis": "Netto-Feld erst ab Einstieg 31.08.2026 gefüllt — anderes Zeitfenster",
    }
    commit = freeze_eval._git_commit_hash()
    data_hash = freeze_eval._data_hash(used)
    out = []
    for t, test_id in (("peak", TEST_ID_PEAK), ("r10", TEST_ID_R10)):
        s = stats[t]
        boot = s["boot"]
        ci_ok = boot["ci_lo"] is not None and boot["ci_lo"] > 0.5
        reg_status, reg_detail = regime_split(s["a"], s["b"], boot["point_auc"], params["regime_min"])
        # Cluster-Folgeeinträge über ALLE verwendeten Zeilen bestimmen (Freeze:
        # „Lauf mit allen Zeilen und ohne Cluster-Folgeeinträge"); die
        # Gruppenbildung je Ziel passiert danach in ``_auc_eval_fn``.
        cluster = freeze_eval.cluster_double_run(list(used),
                                                 _auc_eval_fn(t, params),
                                                 point_key="auc", baseline=0.5)
        verdict, reason = verdict_for(floor_ok[t], holm_by[t], ci_ok, reg_status)
        if cluster.get("same_direction") is False:
            reason += " (Einschränkung: Cluster-Doppellauf zeigt andere Richtung — ändert das Verdikt nicht)"
        out.append({
            "schema_v": SCHEMA_V,
            "family": FAMILY,
            "test_id": test_id,
            "target": "max_gain_pct >= 30" if t == "peak" else "return_10d >= +10 vs <= -5",
            "freeze_date": "07.11.2026",
            "protocol_ref": PROTOCOL_REF,
            "evaluated_at": now.isoformat(),
            "n_window": n_window,
            "n_excluded": len(excluded),
            "pct_excluded": round(100.0 * len(excluded) / n_window, 2) if n_window else 0.0,
            "n_target_excluded": s["n_target_excluded"],
            "n_a": len(s["a"]), "n_b": len(s["b"]),
            "floor": params["floor"], "floor_ok": floor_ok[t],
            "statistic": {"auc": boot["point_auc"], "ci_lo": boot["ci_lo"],
                          "ci_hi": boot["ci_hi"], "note": boot["note"]},
            "p_raw": boot["p_two_sided"],
            "p_holm_input": p_inputs[t],
            "holm": {"alpha_paper_c": params["alpha_paper_c"], "method": "holm_k2_innerhalb_2alpha_3",
                     "reject": holm_by[t]},
            "holm_reject": holm_by[t],
            "criteria": {"holm_significant": holm_by[t], "ci_lo_above_0_5": ci_ok,
                         "regime_split_status": reg_status},
            "regime_split": {"status": reg_status, "min_per_group": params["regime_min"],
                             "detail": reg_detail},
            "cluster_double_run": {
                "auc_with": cluster["with_cluster"].get("auc"),
                "auc_without": cluster["without_cluster"].get("auc"),
                "n_cluster_followups_removed": cluster["n_cluster_followups_removed"],
                "same_direction": cluster["same_direction"],
                "nur_berichtet": True},
            "net_supplement": net_info,
            "verdict": verdict,
            "verdict_reason": reason,
            "bootstrap_seed": params["bootstrap_seed"],
            "bootstrap_n": params["bootstrap_n"],
            "ci_method": f"95% zweiseitig, Perzentil {params['ci_lo_pct']}/{params['ci_hi_pct']}, je Gruppe",
            "data_hash": data_hash,
            "freeze_block_md5": params["block_md5"],
            "script_commit_hash": commit,
            "confirmatory_tests_before": tests_before,
            "confirmatory_tests_total": tests_before + 2,
        })
    return out


def push_body(rows: Sequence[dict]) -> str:
    """Nur Verdikte je Ziel + Gesamtzahl Bestätigungstests — keine Ergebniszahlen."""
    by = {r["test_id"]: r["verdict"] for r in rows}
    total = rows[0]["confirmatory_tests_total"] if rows else "?"
    return (f"Paper C ausgewertet (einmaliger Lauf). Ziel 1 (Gipfel): {by.get(TEST_ID_PEAK)}. "
            f"Ziel 2 (10-Tage): {by.get(TEST_ID_R10)}. "
            f"Bestätigungstests bisher gesamt: {total}. Details in {config.EVAL_RESULTS_FILE}.")


# ── 5) Orchestrierung ───────────────────────────────────────────────────
def _location_guard(env=None) -> None:
    env = os.environ if env is None else env
    if env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REF") != "refs/heads/main":
        raise PaperCAbort("Lauf nur im GitHub-Workflow auf main erlaubt "
                          "(GITHUB_ACTIONS=true, GITHUB_REF=refs/heads/main).")


def run_paper_c(*, handover_path, results_path, export_path, now: datetime | None = None,
                env=None, send_push: Callable[[str, str], object] | None = None) -> list[dict]:
    _location_guard(env)
    params = read_freeze(handover_path)
    tests_before = check_lock(results_path)
    used, excluded = _load_sample(export_path, params)
    rows = evaluate(used, excluded, params, now=now, tests_before=tests_before)
    freeze_eval._append_results(str(results_path), rows)
    if send_push is not None:
        send_push("Freeze-Auswertung: Paper C", push_body(rows))
    return rows


def _default_push(title: str, body: str) -> None:
    import health_check_digest as hcd  # noqa: E402 — lazy, nur im echten Lauf
    hcd._ntfy_send(title, body, "high", "science")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Paper C — einmalige Freeze-Auswertung")
    ap.add_argument("--run", action="store_true", help="Auswertung wirklich starten")
    args = ap.parse_args(argv)
    if not args.run:
        print("Kein Lauf: --run fehlt. Paper C wird nur über den Workflow "
              "health_check_digest.yml (Input paper_c) ausgewertet.")
        return 2
    try:
        rows = run_paper_c(handover_path=_ROOT / HANDOVER_FILE,
                           results_path=_ROOT / config.EVAL_RESULTS_FILE,
                           export_path=_ROOT / config.MATURED_EXPORT_FILE,
                           send_push=_default_push)
    except PaperCAbort as exc:
        print(f"ABBRUCH (nichts ausgewertet/geschrieben): {exc}")
        return 1
    print(push_body(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
