"""Mock-Tests für den Diagnose-Prompt im crit-Push (09.08.2026).

Bei crit hängt ``format_digest_body`` EINEN fertigen, kopierbaren READ-ONLY-
Diagnose-Prompt an den ntfy-Body (Easy tippt ihn in die Claude-Code-Instanz).
Die harte Linie: die Templates sind NIEMALS Bau-Prompts, Auslöser NUR crit,
und die Alarm-Kette wird nie geschwächt (fail-soft: Prompt-Crash / Body-über-
Limit → crit-Push UNVERÄNDERT wie heute).

Deckt ab:
  1  Skelett: Projekt-Kennzeile (+ falscher-Chat-Stopp) + READ-ONLY-Kopf,
     Fuß „melden statt fixen. Easy entscheidet".
  2  Je crit-fähigem Signal (S1/S2/S3/S9/S10/S12 + Provider-Tier-1) ein
     signalspezifischer Block mit den KONKRETEN Lauf-Werten; unbekannte ID →
     generischer READ-ONLY-Block.
  3  KEIN Bau-Verb (fixe/ändere/baue/ergänze/…) als ANWEISUNG — nur in den
     Prohibitionen („nichts bauen", „Nichts ändern", „melden statt fixen").
  4  Auslöser NUR crit: warn-only / OK / no-data bekommen KEINEN Prompt.
  5  Mehrere crits → EIN kombinierter Prompt (nicht mehrere).
  6  Fail-soft: Builder-Crash → base-Body unverändert; Body-über-Limit → kein
     Prompt angehängt; leere/None-Eingabe → None.
  7  Länge: worst-case (alle crit) unter DIGEST_BODY_SAFE_BYTES < ntfy-4096.

Kategorie A: stdlib only, deterministisch, env-frei.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


# crit-fähige Signale mit synthetischen, aber realistischen detail-/reason-Texten.
_CRIT = {
    "S1":  {"id": "S1", "severity": "crit",
            "detail": "score_history ohne heutigen Eintrag für 3/10 Top-10-Ticker: HTZ, WOLF, INDI"},
    "S2":  {"id": "S2", "severity": "crit",
            "detail": "setup_scores enthält 5 Tickers, Schwelle ≥ 8"},
    "S3":  {"id": "S3", "severity": "crit",
            "detail": "current_price fehlt bei 2 Position(en): AMC, GME"},
    "S9":  {"id": "S9", "severity": "crit",
            "detail": "HTML-Sanity: 2 Fail(s). Erster: article-Count 0, erwartet ≥ 10"},
    "S10": {"id": "S10", "severity": "crit",
            "detail": "MUSS-Feld 'short_float': 24/30 null (80%) in letzten 30 V4-Einträgen — Daten-Pipeline füllt nicht"},
    "S12": {"id": "S12", "severity": "crit",
            "detail": "kein echter postclose-Run (run_phase==tsp=='postclose') seit 3 Werktagen"},
    "PROV": {"provider": "yfinance_batch", "tier": 1, "severity": "crit",
             "reason": "coverage 42% (< 80)"},
}

_BUILD_VERBS = re.compile(
    r"\b(fixe|fixen|ändere|ändern|baue|bauen|ergänze|ergänzen|"
    r"implementiere|implementieren|repariere|reparier)\b", re.IGNORECASE)
# Erlaubte Kontexte: die Prohibitionen im Skelett — kein Bau-BEFEHL.
_PROHIBITION_CTX = ("melden statt fixen", "nichts bauen", "nichts ändern")


def _instruction_build_verbs(text: str) -> list[str]:
    """Bau-Verben, die NICHT in einer Prohibition stehen (= echte Anweisungen)."""
    bad = []
    for m in _BUILD_VERBS.finditer(text):
        ctx = text[max(0, m.start() - 18):m.end() + 8].lower()
        if not any(p in ctx for p in _PROHIBITION_CTX):
            bad.append(ctx)
    return bad


def main() -> int:
    D = "2026-08-09"

    print("=== (1) Skelett: Kopf + Fuß, je Signal ein Prompt ===")
    for k, f in _CRIT.items():
        p = hc.build_diagnose_prompt([f], digest_date=D)
        ok = (p is not None
              and p.startswith("PROJEKT: Squeeze Report")
              and "falscher Chat" in p
              and "READ-ONLY DIAGNOSE, nichts bauen, kein PR" in p
              and p.rstrip().endswith("Easy entscheidet nach dem Bericht."))
        _check(f"{k}: Prompt mit Kopf+Fuß + falscher-Chat-Stopp", ok)

    print("\n=== (2) Signal-spezifischer Kontext mit KONKRETEN Werten ===")
    _check("S3 nennt die betroffenen Ticker (AMC, GME)",
           "AMC, GME" in hc.build_diagnose_prompt([_CRIT["S3"]], digest_date=D))
    _check("S10 nennt das MUSS-Feld + Prozent (short_float, 80%)",
           all(s in hc.build_diagnose_prompt([_CRIT["S10"]], digest_date=D)
               for s in ("short_float", "80%")))
    _check("Provider nennt Provider + Tier + Grund",
           all(s in hc.build_diagnose_prompt([_CRIT["PROV"]], digest_date=D)
               for s in ("yfinance_batch", "Tier 1", "coverage 42%")))
    # signalspezifische Frage (nicht generisch): S3 fragt nach _fetch_position_market_data
    _check("S3-Block stellt die S3-spezifische Frage (_fetch_position_market_data)",
           "_fetch_position_market_data" in hc.build_diagnose_prompt([_CRIT["S3"]], digest_date=D))
    _check("S9-Block fragt nach DOM-Klassen (card-cockpit)",
           "card-cockpit" in hc.build_diagnose_prompt([_CRIT["S9"]], digest_date=D))
    # unbekannte crit-ID → generischer, aber READ-ONLY Block (kein Crash)
    gen = hc.build_diagnose_prompt(
        [{"id": "S99", "severity": "crit", "detail": "neues Signal x"}], digest_date=D)
    _check("Unbekannte crit-ID → generischer Block (nennt S99 + Wert)",
           gen is not None and "S99" in gen and "neues Signal x" in gen)

    print("\n=== (3) KEIN Bau-Verb als Anweisung (nur Prohibitionen) ===")
    combined_all = hc.build_diagnose_prompt(list(_CRIT.values()), digest_date=D)
    bad = _instruction_build_verbs(combined_all)
    _check(f"kombinierter All-Signal-Prompt ohne Bau-Anweisung (Treffer: {bad})", not bad)
    # jeder Einzel-Block ebenfalls sauber
    for k, f in _CRIT.items():
        _check(f"{k}: Einzel-Prompt ohne Bau-Anweisung",
               not _instruction_build_verbs(hc.build_diagnose_prompt([f], digest_date=D)))

    print("\n=== (4) Auslöser NUR crit (warn/OK/no-data promptlos) ===")
    SEP = hc._DIAGNOSE_PROMPT_SEP
    warn3 = [{"id": "S4", "severity": "warn", "detail": "w1"},
             {"id": "S5", "severity": "warn", "detail": "w2"},
             {"id": "S7", "severity": "warn", "detail": "w3"}]
    body_warn, title_warn, _, _ = hc.format_digest_body(
        warn3, [], n_runs=3, last_run_iso="x", digest_date=D)
    _check("warn-only ist Digest-Klasse ABER ohne Prompt",
           title_warn == "⚠️ Health-Check-Digest" and SEP not in body_warn)
    body_ok, _, _, _ = hc.format_digest_body([], [], n_runs=5, last_run_iso="x", digest_date=D)
    body_nd, _, _, _ = hc.format_digest_body([], [], n_runs=0, last_run_iso=None, digest_date=D)
    _check("OK-Klasse ohne Prompt", SEP not in body_ok)
    _check("no-data-Klasse ohne Prompt", SEP not in body_nd)

    print("\n=== (5) crit → EIN kombinierter Prompt (mehrere crits) ===")
    body_crit, _, _, _ = hc.format_digest_body(
        [_CRIT["S3"], _CRIT["S10"]], [_CRIT["PROV"]],
        n_runs=4, last_run_iso="x", digest_date=D)
    _check("crit-Body enthält den Separator", SEP in body_crit)
    _check("genau EIN Prompt-Separator (nicht pro Signal einer)",
           body_crit.count(SEP) == 1)
    _check("EIN Prompt nennt alle drei crits (S3, S10, yfinance_batch)",
           all(s in body_crit for s in ("[S3]", "[S10]", "yfinance_batch")))
    _check("bisherige crit-Zeilen unverändert (S3-detail + Header stehen VOR dem Prompt)",
           body_crit.index("⚠️ Health-Check-Digest") < body_crit.index(SEP)
           and "current_price fehlt" in body_crit.split(SEP)[0])

    print("\n=== (6) Fail-soft (Alarm-Kette nie schwächen) ===")
    _check("build([]) → None", hc.build_diagnose_prompt([], digest_date=D) is None)
    _check("build(None) → None", hc.build_diagnose_prompt(None, digest_date=D) is None)
    _check("_diagnose_block_for(non-dict) → None", hc._diagnose_block_for("x") is None)
    # Builder-Crash → base-Body unverändert
    _orig = hc.build_diagnose_prompt
    try:
        hc.build_diagnose_prompt = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        body_crash, _, _, _ = hc.format_digest_body(
            [_CRIT["S3"]], [], n_runs=3, last_run_iso="x", digest_date=D)
    finally:
        hc.build_diagnose_prompt = _orig
    _check("Builder-Crash → kein Separator, crit-Body intakt (S3 drin)",
           SEP not in body_crash and "current_price fehlt" in body_crash)
    # Body-über-Limit → kein Prompt angehängt (base bleibt)
    big = {"id": "S10", "severity": "crit", "detail": "X" * 5000}
    body_big, _, _, _ = hc.format_digest_body([big], [], n_runs=3, last_run_iso="x", digest_date=D)
    _check("über-Limit → kein Prompt (base-crit-Push bleibt, S10 drin)",
           SEP not in body_big and "S10" in body_big)

    print("\n=== (7) Länge: worst-case unter Limit ===")
    body_worst, _, _, _ = hc.format_digest_body(
        [_CRIT["S1"], _CRIT["S2"], _CRIT["S3"], _CRIT["S9"], _CRIT["S10"], _CRIT["S12"]],
        [_CRIT["PROV"]], n_runs=7, last_run_iso="x", digest_date=D)
    nb = len(body_worst.encode("utf-8"))
    _check(f"worst-case Body ({nb} B) ≤ DIGEST_BODY_SAFE_BYTES ({hc.DIGEST_BODY_SAFE_BYTES})",
           nb <= hc.DIGEST_BODY_SAFE_BYTES)
    _check(f"worst-case Body ({nb} B) < ntfy-Limit 4096", nb < 4096)
    _check("worst-case: Prompt trotzdem angehängt (passt unter Limit)", SEP in body_worst)
    _check("SAFE-Deckel < ntfy-4096 (Sicherheitsabstand)", hc.DIGEST_BODY_SAFE_BYTES < 4096)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle crit-Diagnose-Prompt-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
