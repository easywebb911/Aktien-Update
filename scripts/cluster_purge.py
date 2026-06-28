"""Cluster-Purge-Helper (pure stdlib) für die 30.06.-Auswertung.

ZWECK (Doppellauf-Disziplin): Der Setup-Score-≥70-Edge-Test am 30.06. wird
gemäß §3 (Diagnose 09.06.) **mit UND ohne** Cluster-Einträge gerechnet —
hält die Edge in beiden, ist sie robust; kippt sie, ist der Schluss zu
verschieben. Dieser Helper liefert das Filter-Predicate für den
„ohne Cluster"-Lauf.

CLUSTER-DEFINITION (Diagnose 09.06., Stufe-(i)-Beleg 30.06.-Vorbereitung):
Ein „Pre-Open-Re-Run" friert den Vortags-Bar ein — yfinance liefert vor
dem heutigen Open noch den letzten verfügbaren Close des Vortags-Handels-
tags → ``s["price"]`` ist exakt der Vortags-Close → ``entry_price``
(round 4 Dezimalen) ist exakt gleich.

  → SIGNATUR: Ein Record ``(ticker, date)`` ist Cluster-FOLGEEINTRAG ⇔
  im selben Bestand existiert ein Record ``(ticker, <vorheriger
  Handelstag>)`` mit exakt gleichem ``entry_price`` (==-Vergleich auf
  4 Dezimalen Floating-Point).

„Vorheriger Handelstag" ist HOLIDAY-ROBUST: Wochenenden UND
US-Feiertage (config.US_MARKET_HOLIDAYS) werden übersprungen. Fr→Mo
(gap 3 Kalendertage) zählt zusammenhängend; Cluster über einen
Feiertag hinweg (z.B. Mi→Mo über Memorial-Day-Mo? — nein, Memorial-Day
ist Mo selbst; korrekt: Fr→Di über einen Mo-Feiertag mit gap 4) wird
korrekt verbunden.

REIHENFOLGE-DISZIPLIN: Dieses Modul liest **keine** ``backtest_history.json``
oder andere Live-Datei. Caller übergibt die Record-Liste explizit
(analog ``stats_helpers.py``). Kein Import in
``generate_report``/``ki_agent``/``health_check``/``backtest_history``.

Pure stdlib (``datetime``, ``config.US_MARKET_HOLIDAYS``), deterministisch.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date, datetime, timedelta
from typing import Sequence

# US_MARKET_HOLIDAYS aus dem Repo-Root-Modul `config.py` — Single-Source
# (etabliert mit #381). Falls dieses Skript ohne Root-im-sys.path importiert
# wird (z.B. aus scripts/ direkt), den Root als Fallback nachreichen.
_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config import US_MARKET_HOLIDAYS  # noqa: E402

__all__ = ["previous_trading_day", "classify_cluster_records"]


# ── Datum-Helfer (holiday-robust) ─────────────────────────────────────────


def previous_trading_day(d: date) -> date:
    """Der vorherige US-Handelstag — überspringt Wochenenden UND
    Feiertage (``config.US_MARKET_HOLIDAYS``). Liefert immer einen
    Werktag, der KEIN Feiertag ist. Reine Datums-Arithmetik, kein I/O.

    Beispiele:
      - Mo → Fr (gap 3 Kalendertage)
      - Di nach Memorial-Day-Mo (2026-05-25) → Fr 22.05. (gap 4)
      - Fr nach Juneteenth (2026-06-19) → Do 18.06. (gap 1, da Fr Feiertag)

    HINWEIS: ``d`` darf selbst ein Wochenende/Feiertag sein — die Funktion
    sucht den vorherigen Handelstag VOR ``d``, unabhängig von ``d``s
    eigenem Status.
    """
    candidate = d - timedelta(days=1)
    while candidate.weekday() >= 5 or candidate.isoformat() in US_MARKET_HOLIDAYS:
        candidate -= timedelta(days=1)
    return candidate


# ── Cluster-Klassifikation ────────────────────────────────────────────────


def _parse_date(s: str) -> date | None:
    """Akzeptiert ``DD.MM.YYYY`` (Backtest-Format) und ``YYYY-MM-DD`` (ISO).
    Returnt ``None`` bei Parse-Fehler — Caller-Verantwortung."""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def classify_cluster_records(records: Sequence[dict]) -> list[dict]:
    """Klassifiziert eine Liste von Backtest-artigen Records nach Cluster-Zugehörigkeit.

    Eingabe-Record-Format (jeder Eintrag muss diese Keys tragen):
      ``ticker`` (str), ``date`` (DD.MM.YYYY oder YYYY-MM-DD),
      ``entry_price`` (float, bereits gerundet auf 4 Dezimalen).
    Andere Felder werden ignoriert (durchgereicht — sind aber nicht im
    Output-Dict enthalten; Caller filtert via Index-Map).

    Algorithmus:
      1. Index ``(ticker, date_obj) → entry_price`` bauen.
      2. Pro Eingabe-Record (in Original-Reihenfolge): vorheriger
         Handelstag via ``previous_trading_day``; nachschlagen im Index;
         exakter ``==``-Vergleich auf ``entry_price``.
      3. ``is_cluster_followup = True`` ⇔ Match.

    Returnt eine Liste in **derselben Reihenfolge** wie ``records``,
    jeweils ein Dict:
      ``ticker``                  — durchgereicht.
      ``date``                    — durchgereicht (Original-String).
      ``entry_price``             — durchgereicht.
      ``is_cluster_followup``     — bool, ``True`` ⇒ würde im Purge entfernt.
      ``prev_trading_day``        — ISO-String oder ``None`` (bei Datum-Parse-Fehler).
      ``matched_against_price``   — float (== ``entry_price``) bei Match,
                                    sonst ``None``.

    Edge-Cases:
      - Datum unparsebar → ``is_cluster_followup=False``,
        ``prev_trading_day=None`` (defensiv: kein false-positive).
      - Vortags-Record fehlt im Bestand → kein Cluster (False).
      - Verschiedene Ticker mit zufällig gleichem ``entry_price`` → kein
        Cluster (Ticker-Match ist Pflicht, Index-Key enthält Ticker).
      - Kette ≥ 3 Tage gleicher Preis: Tag 1 = Erst, Tag 2/3/... = Folge
        (jeder vergleicht gegen seinen unmittelbaren Vortags-Handelstag).
      - ``entry_price`` als Float — ``==``-Vergleich auf gerundete
        4-Dezimal-Werte ist im Bestand exakt (Stufe-(i)-Beleg: 81/115
        pre-#346, 0/36 post-#346, Mid-Bereich 0,7 % Floating-Drift wandert
        in der 4. Stelle und wird korrekt als Nicht-Cluster erkannt).
    """
    # Index für O(1)-Lookup. Bei Same-Day-Duplikaten (sollte durch
    # _append_backtest_entries-Dedup nicht vorkommen, aber defensiv): der
    # spätere Eintrag überschreibt den früheren — Cluster-Erkennung bliebe
    # idempotent (gleicher Wert).
    index: dict[tuple[str, date], float] = {}
    for r in records:
        t = r.get("ticker")
        d_obj = _parse_date(r.get("date", ""))
        ep = r.get("entry_price")
        if t is None or d_obj is None or ep is None:
            continue
        index[(t, d_obj)] = ep

    results: list[dict] = []
    for r in records:
        t = r.get("ticker")
        d_str = r.get("date", "")
        ep = r.get("entry_price")
        d_obj = _parse_date(d_str)
        prev_iso: str | None = None
        matched_price: float | None = None
        is_cluster = False
        if d_obj is not None and t is not None and ep is not None:
            prev = previous_trading_day(d_obj)
            prev_iso = prev.isoformat()
            prev_price = index.get((t, prev))
            if prev_price is not None and prev_price == ep:
                is_cluster = True
                matched_price = prev_price
        results.append({
            "ticker": t,
            "date": d_str,
            "entry_price": ep,
            "is_cluster_followup": is_cluster,
            "prev_trading_day": prev_iso,
            "matched_against_price": matched_price,
        })
    return results
