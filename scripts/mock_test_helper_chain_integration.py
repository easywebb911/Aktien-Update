"""Integrations-Trockenlauf der drei 30.06.-Helfer (#389/#390/#391).

WAS DIES IST: ein Verkettungs-/Schnittstellen-Beleg. Verdrahtet die drei
Helfer in der Reihenfolge, in der sie am 30.06. zusammenspielen werden:
  A. cluster_purge.classify_cluster_records   → Cluster-Folgeeinträge markieren
  B. stats_helpers.mann_whitney_u_auc         → AUC pro Score-Bucket (Doppellauf)
  C. stats_helpers.multiple_testing_correction → Bonferroni/Holm über alle p

Synthetische Fixture mit von Hand konstruierten, bekannten Erwartungswerten.
Adapter-Schritte zwischen den Helfern sind im Test explizit dokumentiert UND
verriegelt — damit am 30.06. klar ist, welcher Caller-Code nötig ist.

WAS DIES NICHT IST: eine Auswertung. KEINE backtest_history.json. KEIN echter
Daten-Kontakt. KEINE Vorlage, in die man am 30.06. nur die echten Daten
einhängt und „fertig" ist. Die Fixture-Zahlen haben keinen Trading-Bezug.

REIHENFOLGE-SCHUTZ: Fixture-only, kein Live-Pfad, kein Edge-Output.

═══ SCHNITTSTELLEN-BEFUNDE (dokumentiert + verriegelt) ═══

ADAPTER A→B (Test 02 verriegelt das Pattern):
  classify_cluster_records gibt nur die SIGNATUR-Felder zurück (ticker,
  date, entry_price, is_cluster_followup, prev_trading_day,
  matched_against_price). Score/Return/manual_personal-Felder bleiben in
  den ORIGINAL-Records. Der Caller MUSS die Cluster-Flags per
  (ticker, date)-Lookup zurückmergen — die Hilfsroutine
  _attach_cluster_flag_to_records zeigt das Pattern. Legitim (Helfer
  hält sich an seinen Scope), aber für den 30.06.-Caller nicht vergessen.

ADAPTER B→C (Test 08 verriegelt das Pattern):
  mann_whitney_u_auc gibt ein dict zurück mit
  p_two_sided=float|None. Der Caller MUSS vor multiple_testing_correction
  die None-Werte filtern (sonst TypeError beim < threshold-Vergleich) und
  parallel die Labels führen. _collect_p_values_for_correction zeigt das
  Pattern.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from cluster_purge import classify_cluster_records           # noqa: E402
from stats_helpers import (                                  # noqa: E402
    mann_whitney_u_auc,
    multiple_testing_correction,
)


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


# ── Adapter-Helfer (ZWECK: zeigen, was der 30.06.-Caller schreiben muss) ──


def _attach_cluster_flag_to_records(records: list[dict],
                                    cluster_results: list[dict]) -> list[dict]:
    """ADAPTER A→B: merged Cluster-Flag per (ticker, date)-Lookup in die
    Original-Records zurück. Returnt eine NEUE Liste (Original unverändert).

    Warum nötig: classify_cluster_records-Output enthält nur Signatur-
    Felder. Score/Return/manual_personal bleiben in den Original-Records.
    """
    idx = {(c["ticker"], c["date"]): c["is_cluster_followup"]
           for c in cluster_results}
    return [
        {**r, "is_cluster_followup": idx.get((r["ticker"], r["date"]), False)}
        for r in records
    ]


def _collect_p_values_for_correction(
        named_auc_results: list[tuple[str, dict]],
) -> tuple[list[float], list[str]]:
    """ADAPTER B→C: sammelt p-Werte + Labels aus AUC-Dict-Ergebnissen.
    Filtert None-Werte (kein gültiger p-Wert; z.B. leere Gruppe oder
    alle Werte identisch) und führt Labels parallel.

    Warum nötig: multiple_testing_correction erwartet eine reine
    p-Wert-Liste; ein None-Eintrag würde im < threshold-Vergleich
    TypeError werfen.
    """
    pvs: list[float] = []
    labs: list[str] = []
    for name, auc_res in named_auc_results:
        p = auc_res.get("p_two_sided")
        if p is None:
            continue
        pvs.append(p)
        labs.append(name)
    return pvs, labs


# ── Test-Helfer (Bucket-Definitionen) ─────────────────────────────────────


def _score_bucket_auc(enriched: list[dict], filter_cluster: bool) -> dict:
    """AUC-Frage Setup-Edge-Test: Score≥70-Bucket-Returns vs <70-Bucket-Returns."""
    recs = ([r for r in enriched if not r["is_cluster_followup"]]
            if filter_cluster else enriched)
    ge70 = [r["return_10d"] for r in recs if r["score"] >= 70]
    lt70 = [r["return_10d"] for r in recs if r["score"] < 70]
    return mann_whitney_u_auc(ge70, lt70)


def _personal_auc(enriched: list[dict], filter_cluster: bool) -> dict:
    """AUC-Frage Watchlist-Doppellauf: Personal-Returns vs Non-Personal."""
    recs = ([r for r in enriched if not r["is_cluster_followup"]]
            if filter_cluster else enriched)
    personal = [r["return_10d"] for r in recs if r["manual_personal"]]
    non_pers = [r["return_10d"] for r in recs if not r["manual_personal"]]
    return mann_whitney_u_auc(personal, non_pers)


# ── Fixture: 7 Records mit bekannten Eigenschaften ────────────────────────
# Konstruktion bewusst klein + hand-rechenbar. min(n_a,n_b)=2 in einigen
# Branches → p-Werte werden NICHT signifikant (Approx-Note gesetzt) — das
# ist Demo-Mechanik, kein Edge-Anspruch. Die echte Auswertung am 30.06. läuft
# auf n=103+ und bekommt damit aussagekräftigere p-Werte.

RECORDS: list[dict] = [
    # Ticker A — Cluster über 3 Handelstage, alle ep=10.0, score=80, +30 return
    {"ticker": "A", "date": "15.06.2026", "entry_price": 10.0,
     "score": 80, "return_10d": 30.0, "manual_personal": True},
    {"ticker": "A", "date": "16.06.2026", "entry_price": 10.0,
     "score": 80, "return_10d": 30.0, "manual_personal": True},
    {"ticker": "A", "date": "17.06.2026", "entry_price": 10.0,
     "score": 80, "return_10d": 30.0, "manual_personal": True},
    # Single B im Score≥70-Bucket (Gewinner, Personal)
    {"ticker": "B", "date": "15.06.2026", "entry_price": 8.0,
     "score": 75, "return_10d": 10.0, "manual_personal": True},
    # Single C im Score≥70-Bucket (Verlierer, Non-Personal)
    {"ticker": "C", "date": "15.06.2026", "entry_price": 6.0,
     "score": 72, "return_10d": -5.0, "manual_personal": False},
    # Single D im Score<70-Bucket (Verlierer, Non-Personal)
    {"ticker": "D", "date": "15.06.2026", "entry_price": 4.0,
     "score": 60, "return_10d": -12.0, "manual_personal": False},
    # Single E im Score<70-Bucket (Gewinner, Non-Personal)
    {"ticker": "E", "date": "15.06.2026", "entry_price": 20.0,
     "score": 55, "return_10d": 15.0, "manual_personal": False},
]


def main():
    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  SCHRITT A — Cluster-Klassifikation                               ║
    # ╚══════════════════════════════════════════════════════════════════╝
    cluster_results = classify_cluster_records(RECORDS)
    cluster_flags = [c["is_cluster_followup"] for c in cluster_results]

    # A erwartet: Tag 1 (15.06) Erst; Tag 2+3 (16/17) Folge.
    # B-E alle Singles → kein Cluster.
    _check("01 SCHRITT A — Cluster-Flags = [F,T,T,F,F,F,F] (A-Cluster erkannt)",
           cluster_flags == [False, True, True, False, False, False, False],
           f"got {cluster_flags}")

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  ADAPTER A→B — Cluster-Flag in Original-Records zurückmergen      ║
    # ╚══════════════════════════════════════════════════════════════════╝
    # BEFUND: classify_cluster_records-Output enthält NUR Signatur-Felder
    # (kein score, kein return_10d, kein manual_personal). Der Caller muss
    # per (ticker, date)-Lookup zurückmergen.
    enriched = _attach_cluster_flag_to_records(RECORDS, cluster_results)

    _check("02 ADAPTER A→B — Score/Return bleiben in Original, "
           "Cluster-Flag wird per Lookup gemerged (kein Datenverlust)",
           enriched[0]["score"] == 80
           and enriched[0]["return_10d"] == 30.0
           and enriched[0]["is_cluster_followup"] is False
           and enriched[1]["is_cluster_followup"] is True
           and enriched[1]["score"] == 80,  # Score erhalten trotz Merge
           f"enriched[0]={enriched[0]}")

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  SCHRITT B — AUC pro Bucket, Doppellauf (with/without Cluster)    ║
    # ╚══════════════════════════════════════════════════════════════════╝
    #
    # AUC-Frage Setup-Edge-Test:
    #   Score≥70-Bucket-Returns  vs.  Score<70-Bucket-Returns
    #
    # WITH Cluster (alle 7 Records):
    #   ≥70: [30, 30, 30, 10, -5]    (n_a=5: A×3 + B + C)
    #   <70: [-12, 15]               (n_b=2: D + E)
    #   Vergleichspaare 5×2=10:
    #     (30,-12)×3 → 3 wins  (30,15)×3 → 3 wins
    #     (10,-12)   → 1 win   (10,15)   → 1 loss
    #     (-5,-12)   → 1 win   (-5,15)   → 1 loss
    #   Wins=8, Losses=2, Ties=0 → AUC = 8/10 = 0.8

    auc_with = _score_bucket_auc(enriched, filter_cluster=False)
    _check("03 SCHRITT B (with Cluster) — Score-Bucket-AUC = 0.8 (hand-gerechnet)",
           abs(auc_with["auc"] - 0.8) < 1e-9,
           f"got AUC={auc_with['auc']}")
    _check("03b AUC-Dict trägt n_a=5, n_b=2 (Bucket-Größen verifizierbar)",
           auc_with["n_a"] == 5 and auc_with["n_b"] == 2)

    # WITHOUT Cluster (Folgeeinträge raus = 5 Records):
    #   ≥70: [30, 10, -5]   (n_a=3: A + B + C)
    #   <70: [-12, 15]      (n_b=2: D + E)
    #   Vergleichspaare 3×2=6:
    #     (30,-12)→win, (30,15)→win,
    #     (10,-12)→win, (10,15)→loss,
    #     (-5,-12)→win, (-5,15)→loss
    #   Wins=4, Losses=2 → AUC = 4/6 ≈ 0.6667

    auc_without = _score_bucket_auc(enriched, filter_cluster=True)
    _check("04 SCHRITT B (without Cluster) — Score-Bucket-AUC = 4/6 ≈ 0.6667",
           abs(auc_without["auc"] - 4/6) < 1e-9,
           f"got AUC={auc_without['auc']}")
    _check("04b n_a sank von 5 auf 3 (Cluster-Folge raus); n_b unverändert",
           auc_without["n_a"] == 3 and auc_without["n_b"] == 2)

    # MECHANIK-BEFUND: Cluster-Kontamination liefert HÖHEREN AUC (0.8 vs 0.667).
    # Das ist genau der Effekt, den der Doppellauf am 30.06. sichtbar machen
    # soll. Hier nur Beleg, dass die Kette diesen Effekt überhaupt zeigt.
    _check("05 Doppellauf-Effekt sichtbar: with > without "
           "(0.8 > 0.667, Cluster-Kontamination erhöht AUC)",
           auc_with["auc"] > auc_without["auc"])

    # ── Personal-Achse (zweiter Doppellauf, manual_personal-Filter) ──────
    #
    # AUC-Frage Watchlist-Doppellauf:
    #   Personal-Returns  vs.  Non-Personal-Returns
    #
    # WITH Cluster (7 Records):
    #   Personal:     [30, 30, 30, 10]  (A×3 + B)
    #   Non-Personal: [-5, -12, 15]     (C + D + E)
    #   Vergleichspaare 4×3=12:
    #     (30,-5)×3, (30,-12)×3, (30,15)×3 = 9 wins
    #     (10,-5),   (10,-12)              = 2 wins
    #     (10,15)                          = 1 loss
    #   Wins=11, Losses=1, Ties=0 → AUC = 11/12 ≈ 0.9167

    pers_with = _personal_auc(enriched, filter_cluster=False)
    _check("06 Personal-Lauf (with Cluster) — AUC = 11/12 ≈ 0.9167",
           abs(pers_with["auc"] - 11/12) < 1e-9,
           f"got AUC={pers_with['auc']}")

    # WITHOUT Cluster:
    #   Personal:     [30, 10]      (A + B)
    #   Non-Personal: [-5, -12, 15] (unverändert)
    #   Vergleichspaare 2×3=6:
    #     (30,-5)→win, (30,-12)→win, (30,15)→win,
    #     (10,-5)→win, (10,-12)→win, (10,15)→loss
    #   Wins=5, Losses=1 → AUC = 5/6 ≈ 0.8333
    pers_without = _personal_auc(enriched, filter_cluster=True)
    _check("07 Personal-Lauf (without Cluster) — AUC = 5/6 ≈ 0.8333",
           abs(pers_without["auc"] - 5/6) < 1e-9,
           f"got AUC={pers_without['auc']}")

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  ADAPTER B→C — p-Werte sammeln, None filtern, Labels parallel     ║
    # ╚══════════════════════════════════════════════════════════════════╝
    # BEFUND: mann_whitney_u_auc-Output ist dict mit p_two_sided=float|None.
    # multiple_testing_correction erwartet reine p-Wert-Liste. Caller muss
    # vor MTC None-Werte filtern (TypeError sonst!) und Labels parallel
    # führen.
    test_outcomes = [
        ("score_ge70_with_cluster",    auc_with),
        ("score_ge70_without_cluster", auc_without),
        ("personal_with_cluster",      pers_with),
        ("personal_without_cluster",   pers_without),
    ]
    p_values, labels = _collect_p_values_for_correction(test_outcomes)

    _check("08 ADAPTER B→C — alle 4 AUCs liefern gültige p_two_sided "
           "(keine None gefiltert) + Labels parallel",
           len(p_values) == 4
           and len(labels) == 4
           and all(p is not None and 0 < p <= 1 for p in p_values),
           f"p_values={[round(p,4) for p in p_values]}, labels={labels}")

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  SCHRITT C — Multiple-Testing-Korrektur                            ║
    # ╚══════════════════════════════════════════════════════════════════╝
    mtc = multiple_testing_correction(p_values, labels=labels, alpha=0.05)

    # Schwellen-Sanity:
    _check("09 SCHRITT C — Bonferroni-Schwelle = α/k = 0.05/4 = 0.0125",
           mtc["bonferroni_threshold"] == 0.05 / 4)

    # Label-Rückordnung: MTC-Output-Labels müssen in Übergabe-Reihenfolge stehen
    result_labels = [e["label"] for e in mtc["results"]]
    _check("10 SCHRITT C — Labels im Output in Übergabe-Reihenfolge "
           "(kein Reorder durch interne Sortierung)",
           result_labels == labels,
           f"got {result_labels}")

    # Holm ⊇ Bonferroni-Invariante (über alle 4 Tests):
    bonf_set = {e["label"] for e in mtc["results"] if e["bonferroni_reject"]}
    holm_set = {e["label"] for e in mtc["results"] if e["holm_reject"]}
    _check("11 SCHRITT C — Invariante: Holm-Reject ⊇ Bonferroni-Reject",
           bonf_set.issubset(holm_set),
           f"bonf={bonf_set}, holm={holm_set}")

    # Wegen kleinem n (min=2 in einigen Branches) sind die p-Werte nicht
    # signifikant. MTC-Anwendung trotzdem mechanisch korrekt. Beleg:
    _check("12 SCHRITT C — Demo-Fixture: alle p > 0 (keine 0er-p)",
           all(p > 0 for p in p_values),
           f"min p = {min(p_values):.4f}")

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  END-TO-END Determinismus                                          ║
    # ╚══════════════════════════════════════════════════════════════════╝
    # Komplette Kette zweimal gegen dasselbe Fixture → identisches Ergebnis.
    cluster_results_2 = classify_cluster_records(RECORDS)
    enriched_2 = _attach_cluster_flag_to_records(RECORDS, cluster_results_2)
    auc_with_2 = _score_bucket_auc(enriched_2, filter_cluster=False)
    pers_with_2 = _personal_auc(enriched_2, filter_cluster=False)
    _check("13 END-TO-END Determinismus: Kette reproduzierbar identisch",
           cluster_results == cluster_results_2
           and auc_with == auc_with_2
           and pers_with == pers_with_2)

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  SCHNITTSTELLEN-SUMMARY (am 30.06.-Caller zu beachten)            ║
    # ╚══════════════════════════════════════════════════════════════════╝
    print()
    print("── SCHNITTSTELLEN-BEFUNDE (für den 30.06.-Caller dokumentiert) ──")
    print("  A→B  Adapter: cluster_results enthält NUR Signatur-Felder")
    print("       → Cluster-Flag per (ticker, date)-Lookup in Original-Records")
    print("       mergen. Demo: _attach_cluster_flag_to_records.")
    print("  B→C  Adapter: AUC-Output ist dict mit p_two_sided=float|None")
    print("       → vor multiple_testing_correction None filtern + Labels")
    print("       parallel führen. Demo: _collect_p_values_for_correction.")
    print("  Beide Adapter sind Caller-Code (Helfer halten sich an Scope) —")
    print("  KEIN Bug, aber für die echte 30.06.-Auswertung nicht vergessen.")

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        sys.exit(1)
    print("Alle Verkettungs-/Schnittstellen-Tests bestanden.")


if __name__ == "__main__":
    main()
