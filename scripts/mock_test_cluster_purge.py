"""Mock-Tests für ``scripts/cluster_purge.py`` (Cluster-Purge-Helper).

FIXTURE-ONLY — kein Kontakt mit ``backtest_history.json`` oder anderen
Live-Dateien. Kein Vergleich gegen die 70,4%-/53,6%-/37,5%-Befunde aus der
Stufe-(i)-Diagnose (Quoten gehören in die 30.06.-Auswertung selbst, nicht
in diesen PR — Reihenfolge-Disziplin).

Verifiziert:
- previous_trading_day() — holiday-robust (Memorial Day, Juneteenth),
  Wochenend-Sprung Fr→Mo
- classify_cluster_records():
  * Cluster-Kette ≥3 Tage → 1 Erst- + N-1 Folgeeinträge
  * Ticker-Match Pflicht (verschiedene Ticker, gleicher entry_price ≠ Cluster)
  * Holiday-Robustheit (Cluster über Juneteenth zusammenhängend)
  * Echter Gap (Vortagsrecord fehlt) → KEIN Cluster
  * Float-Präzision: 8.74 vs 8.75 → kein Match (==-Trennung auf 4 Dez.)
  * Edge: leere Liste, Einzelticker ohne Folge, Datum-Parse-Fehler
  * Eingabe-Reihenfolge bleibt im Output erhalten
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from cluster_purge import (  # noqa: E402
    previous_trading_day,
    classify_cluster_records,
)


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def main():
    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  previous_trading_day — holiday-robust                            ║
    # ╚══════════════════════════════════════════════════════════════════╝

    _check("01 Di → Mo (normaler Werktags-Schritt)",
           previous_trading_day(date(2026, 6, 16)) == date(2026, 6, 15))

    _check("02 Mo → Fr (Wochenend-Sprung, gap 3 Kalendertage)",
           previous_trading_day(date(2026, 6, 15)) == date(2026, 6, 12))

    # Juneteenth 2026 = Fr 19.06. → Mo 22.06 muss auf Do 18.06 zurück
    _check("03 Mo 22.06.2026 → Do 18.06 (überspringt Juneteenth Fr 19.06)",
           previous_trading_day(date(2026, 6, 22)) == date(2026, 6, 18),
           f"got {previous_trading_day(date(2026, 6, 22))}")

    # Memorial Day 2026 = Mo 25.05. → Di 26.05 muss auf Fr 22.05 zurück
    _check("04 Di 26.05.2026 → Fr 22.05 (überspringt Memorial-Day Mo 25.05)",
           previous_trading_day(date(2026, 5, 26)) == date(2026, 5, 22),
           f"got {previous_trading_day(date(2026, 5, 26))}")

    # Vor Juneteenth: Fr 19.06 ist Feiertag selbst → previous_trading_day
    # sucht VOR diesem Datum → Do 18.06
    _check("05 Fr 19.06.2026 (Juneteenth selbst) → Do 18.06",
           previous_trading_day(date(2026, 6, 19)) == date(2026, 6, 18))

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  classify_cluster_records — Cluster-Signatur                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    # ── Cluster-Kette ≥3 Tage ────────────────────────────────────────────
    # Ticker X, Mo/Di/Mi zusammenhängend, alle gleicher entry_price
    # → Mo Erst, Di + Mi Folge
    recs = [
        {"ticker": "X", "date": "15.06.2026", "entry_price": 10.0000},
        {"ticker": "X", "date": "16.06.2026", "entry_price": 10.0000},
        {"ticker": "X", "date": "17.06.2026", "entry_price": 10.0000},
    ]
    out = classify_cluster_records(recs)
    cluster_flags = [o["is_cluster_followup"] for o in out]
    _check("06 Cluster-Kette 3 Tage: [Erst, Folge, Folge] = [F, T, T]",
           cluster_flags == [False, True, True],
           f"got {cluster_flags}")
    _check("06b Folge-Einträge verweisen auf korrekte Vortags-Daten",
           out[1]["prev_trading_day"] == "2026-06-15"
           and out[2]["prev_trading_day"] == "2026-06-16",
           f"prev_1={out[1]['prev_trading_day']}, prev_2={out[2]['prev_trading_day']}")
    _check("06c matched_against_price gesetzt bei Cluster, None sonst",
           out[0]["matched_against_price"] is None
           and out[1]["matched_against_price"] == 10.0
           and out[2]["matched_against_price"] == 10.0)

    # ── Ticker-Match Pflicht ─────────────────────────────────────────────
    # Zwei Ticker, zufällig gleicher entry_price → KEIN Cluster
    recs = [
        {"ticker": "X", "date": "15.06.2026", "entry_price": 7.0000},
        {"ticker": "Y", "date": "16.06.2026", "entry_price": 7.0000},
    ]
    out = classify_cluster_records(recs)
    _check("07 Verschiedene Ticker, gleicher entry_price → KEIN Cluster",
           out[1]["is_cluster_followup"] is False,
           f"Y/16.06 cluster={out[1]['is_cluster_followup']}, "
           f"matched={out[1]['matched_against_price']}")

    # ── Holiday-Robustheit: Cluster ÜBER einen Feiertag ──────────────────
    # Ticker Z, Do 18.06.2026 + Mo 22.06.2026 (gap 4 Kalendertage:
    # Fr=Juneteenth, Sa/So). Vortags-Handelstag von Mo 22.06 ist Do 18.06.
    # → wenn entry_price gleich → Mo ist Cluster-Folge.
    recs = [
        {"ticker": "Z", "date": "18.06.2026", "entry_price": 5.1234},
        {"ticker": "Z", "date": "22.06.2026", "entry_price": 5.1234},
    ]
    out = classify_cluster_records(recs)
    _check("08 Cluster ÜBER Juneteenth (gap 4 Kal.-Tage, holiday-übersprungen)",
           out[1]["is_cluster_followup"] is True
           and out[1]["prev_trading_day"] == "2026-06-18",
           f"cluster={out[1]['is_cluster_followup']}, "
           f"prev={out[1]['prev_trading_day']}")

    # ── Echter Gap (Vortags-Handelstag fehlt im Bestand) ─────────────────
    # Ticker A am Mo + Mi (Di-Record FEHLT im Bestand). Mi sucht Di als
    # Vortags-Handelstag — Di nicht im Index → KEIN Cluster (auch nicht
    # gegen Mo, weil previous_trading_day(Mi) = Di, nicht Mo).
    recs = [
        {"ticker": "A", "date": "15.06.2026", "entry_price": 2.5},
        {"ticker": "A", "date": "17.06.2026", "entry_price": 2.5},
    ]
    out = classify_cluster_records(recs)
    _check("09 Echter Gap (Vortags-Handelstag im Bestand fehlt) → KEIN Cluster",
           out[1]["is_cluster_followup"] is False
           and out[1]["prev_trading_day"] == "2026-06-16",
           f"cluster={out[1]['is_cluster_followup']}, "
           f"prev={out[1]['prev_trading_day']}")

    # ── Float-Präzision: 8.74 vs 8.75 → NICHT match ──────────────────────
    # Diagnose-09.06.-Fall: AI 18.05 (8.74) → 19.05 (8.75), Δ=0.01 →
    # sauber als Nicht-Cluster erkannt (Stufe-(i)-Beleg „0,7 % nah aber
    # nicht exakt" sind echte Mini-Bewegungen, keine Cluster).
    recs = [
        {"ticker": "AI", "date": "18.05.2026", "entry_price": 8.74},
        {"ticker": "AI", "date": "19.05.2026", "entry_price": 8.75},
    ]
    out = classify_cluster_records(recs)
    _check("10 Float-Präzision: 8.74 vs 8.75 → KEIN Cluster (saubere ==-Trennung)",
           out[1]["is_cluster_followup"] is False,
           f"got cluster={out[1]['is_cluster_followup']}")

    # ── Eingabe-Reihenfolge bleibt erhalten ──────────────────────────────
    # Records in absichtlich unsortierter Reihenfolge übergeben — Output-
    # Reihenfolge MUSS Input-Reihenfolge entsprechen.
    recs = [
        {"ticker": "B", "date": "17.06.2026", "entry_price": 3.0},   # später
        {"ticker": "B", "date": "15.06.2026", "entry_price": 3.0},   # früher
        {"ticker": "B", "date": "16.06.2026", "entry_price": 3.0},   # mitte
    ]
    out = classify_cluster_records(recs)
    out_dates = [o["date"] for o in out]
    _check("11 Eingabe-Reihenfolge im Output erhalten (unsortierter Input)",
           out_dates == ["17.06.2026", "15.06.2026", "16.06.2026"],
           f"got {out_dates}")
    # Erst-Eintrag (15.06.) hat keinen Vortag im Bestand → KEIN Cluster
    # 16.06. verweist auf 15.06. → Cluster
    # 17.06. verweist auf 16.06. → Cluster
    cluster_by_date = {o["date"]: o["is_cluster_followup"] for o in out}
    _check("11b Cluster-Zuordnung sortier-unabhängig korrekt",
           cluster_by_date == {"15.06.2026": False,
                               "16.06.2026": True,
                               "17.06.2026": True},
           f"got {cluster_by_date}")

    # ── Edge-Cases ───────────────────────────────────────────────────────
    out = classify_cluster_records([])
    _check("12 leere Eingabe → leere Ausgabe", out == [])

    # Einzelticker ohne Folge → kein Cluster (keine prior-Record im Bestand)
    out = classify_cluster_records([
        {"ticker": "C", "date": "15.06.2026", "entry_price": 1.5}
    ])
    _check("13 Einzelticker ohne Folge → kein Cluster",
           len(out) == 1 and out[0]["is_cluster_followup"] is False)

    # Datum-Parse-Fehler → defensiv kein Cluster, prev=None
    out = classify_cluster_records([
        {"ticker": "D", "date": "garbage", "entry_price": 4.2}
    ])
    _check("14 Datum-Parse-Fehler → kein Cluster, prev_trading_day=None",
           out[0]["is_cluster_followup"] is False
           and out[0]["prev_trading_day"] is None,
           f"got cluster={out[0]['is_cluster_followup']}, prev={out[0]['prev_trading_day']}")

    # ISO-Datum (alternatives Format) wird ebenfalls akzeptiert
    recs = [
        {"ticker": "E", "date": "2026-06-15", "entry_price": 9.0},
        {"ticker": "E", "date": "2026-06-16", "entry_price": 9.0},
    ]
    out = classify_cluster_records(recs)
    _check("15 ISO-Datum-Format (YYYY-MM-DD) wird akzeptiert",
           out[1]["is_cluster_followup"] is True)

    # ── Determinismus ────────────────────────────────────────────────────
    recs = [
        {"ticker": "F", "date": "15.06.2026", "entry_price": 6.0},
        {"ticker": "F", "date": "16.06.2026", "entry_price": 6.0},
    ]
    r1 = classify_cluster_records(recs)
    r2 = classify_cluster_records(recs)
    _check("16 Determinismus: gleicher Input → gleicher Output", r1 == r2)

    # ── Output-Schema-Stabilität ─────────────────────────────────────────
    out = classify_cluster_records([
        {"ticker": "G", "date": "15.06.2026", "entry_price": 5.0}
    ])
    expected_keys = {"ticker", "date", "entry_price",
                     "is_cluster_followup", "prev_trading_day",
                     "matched_against_price"}
    _check("17 Output-Schema stabil (6 Keys pro Record)",
           set(out[0].keys()) == expected_keys,
           f"got {set(out[0].keys())}")

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        sys.exit(1)
    print("Alle Cluster-Purge-Tests bestanden.")


if __name__ == "__main__":
    main()
