"""US-Handelstag-Vorwärts-Arithmetik + FINRA-Publikations-Kalender.

ZWECK: Deterministische Basis für den ``si_velocity_pub``-Look-Ahead-Filter
(PR-3). Ein SI-Report darf einem Backtest-Record nur zugeordnet werden,
wenn sein Publikations-Datum (``pub_date``) ≤ ``entry_date`` — sonst
Look-Ahead. Diese Modul liefert die pure-stdlib-Berechnung des
Publikations-Datums aus dem FINRA-Settlement-Stichtag.

FINRA-Regel (Rule 4560): Short Interest Reports werden **7 Handelstage
NACH Settlement** öffentlich. Der Offset ist in ``config.
FINRA_PUB_OFFSET_BUSINESS_DAYS`` gekapselt (SR-FINRA-2026-012 plant höhere
Reporting-Frequenz — Offset zentral anpassbar).

HOLIDAY-ROBUSTHEIT: nutzt ``config.US_MARKET_HOLIDAYS`` für die
Vorwärts-Suche. Seit PR #407 ist Karfreitag im Set algorithmisch enthalten
(Meeus-Osterformel) — vor #407 hätte diese Berechnung an Karfreitags-Nähe
einen Business-Day zu früh geliefert (Look-Ahead in die falsche Richtung).

DESIGN-ENTSCHEIDUNG: eigenständiges Modul (kein Import in
``scripts/cluster_purge`` und umgekehrt). ``cluster_purge`` hat einen
strikten Docstring-Vertrag „Kein Import in generate_report/ki_agent/
health_check/backtest_history" (Reihenfolge-Disziplin 30.06.-Auswertung).
Da ``get_finra_short_interest`` in ``generate_report`` das
``finra_publication_date`` konsumiert, gehört der Helper in ein separates
Modul. ``next_trading_day`` unten ist trivial-symmetrisch zu
``cluster_purge.previous_trading_day`` — 4 Zeilen with-Schleife, keine
Test-Diskrepanz möglich (kanonische Business-Day-Iteration).

Pure stdlib (``datetime``, ``config.US_MARKET_HOLIDAYS``, ``config.
FINRA_PUB_OFFSET_BUSINESS_DAYS``), deterministisch.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date, timedelta

# Single-Source ``US_MARKET_HOLIDAYS`` + Offset-Konstante aus config.py.
# Falls das Skript ohne Root-im-sys.path importiert wird (analog cluster_purge),
# Root als Fallback nachreichen.
_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config import (  # noqa: E402
    FINRA_PUB_OFFSET_BUSINESS_DAYS,
    US_MARKET_HOLIDAYS,
)

__all__ = ["next_trading_day", "finra_publication_date"]


def next_trading_day(d: date) -> date:
    """Der nächste US-Handelstag — überspringt Wochenenden UND Feiertage
    (``config.US_MARKET_HOLIDAYS``). Liefert immer einen Werktag, der KEIN
    Feiertag ist. Reine Datums-Arithmetik, kein I/O.

    Trivial-symmetrisch zu ``cluster_purge.previous_trading_day``, aber
    eigenständig implementiert (siehe Modul-Docstring: kein Cross-Import
    wegen Reihenfolge-Disziplin von cluster_purge).

    Beispiele:
      - Fr → Mo (gap 3 Kalendertage, Wochenende übersprungen)
      - Do vor Karfreitag 02.04.2026 → Mo 06.04. (gap 4; Fr 03.04. = Good
        Friday übersprungen, dann Wochenende)
      - Fr 22.05.2026 → Di 26.05. (gap 4; Mo 25.05. = Memorial Day)

    HINWEIS: ``d`` darf selbst ein Wochenende/Feiertag sein — die Funktion
    sucht den nächsten Handelstag NACH ``d``, unabhängig von ``d``s
    eigenem Status.
    """
    candidate = d + timedelta(days=1)
    while candidate.weekday() >= 5 or candidate.isoformat() in US_MARKET_HOLIDAYS:
        candidate += timedelta(days=1)
    return candidate


def finra_publication_date(settlement_date: date,
                            offset: int | None = None) -> date:
    """Berechnet das FINRA-Publikations-Datum aus einem Settlement-Stichtag.

    FINRA Rule 4560: SI-Reports sind ~7 Handelstage nach Settlement
    öffentlich (siehe ``config.FINRA_PUB_OFFSET_BUSINESS_DAYS``).

    Args:
        settlement_date: Der Settlement-Stichtag des SI-Reports
            (``datetime.date``). Selbst zählt NICHT als Handelstag mit —
            gezählt wird der ERSTE Handelstag nach ``settlement_date``.
        offset: Anzahl Handelstage. Default aus
            ``config.FINRA_PUB_OFFSET_BUSINESS_DAYS`` (7). Für Tests
            überschreibbar; im Live-Pfad NICHT anpassen (zentrale
            Konstanten-Semantik).

    Returns:
        ``datetime.date`` des Publikations-Tags. Immer ein Handelstag
        (keine Wochenenden, keine US-Feiertage). Holiday-robust seit
        PR #407 (Karfreitag im ``US_MARKET_HOLIDAYS``-Set algorithmisch).

    Verhalten (Beispiele, Rechnung transparent):
        Settlement Do 26.03.2026 (vor Karfreitag), offset=7:
          +1 Fr 27.03 → +2 Mo 30.03 → +3 Di 31.03 → +4 Mi 01.04 →
          +5 Do 02.04 → (Fr 03.04 = Good Friday, skip) → +6 Mo 06.04 →
          +7 Di 07.04 → **pub_date = 2026-04-07**
        Ohne #407 (Karfreitag fälschlich NICHT im Set) wäre pub_date am
        Mo 06.04.2026 gelandet — 1 Business-Day zu früh, Look-Ahead in
        die falsche Richtung.

        Settlement Fr 15.05.2026 (Memorial-Day-Woche), offset=7:
          +1 Mo 18.05 → +2 Di 19.05 → +3 Mi 20.05 → +4 Do 21.05 →
          +5 Fr 22.05 → (Mo 25.05 = Memorial Day, skip) → +6 Di 26.05 →
          +7 Mi 27.05 → **pub_date = 2026-05-27**

    LOOK-AHEAD-KONVENTION (Docstring einfriert, PFLICHT für si_velocity_pub):
        Das zurückgelieferte Datum ist die GRENZE, ab der der SI-Wert
        öffentlich war. Ein SI-Report R mit ``settlement_date = S`` darf
        einem Backtest-Record mit ``entry_date = E`` NUR zugeordnet werden,
        wenn ``finra_publication_date(S) <= E``. Konservativ: lieber zu
        spät zuordnen als zu früh (verpasst am Sample-Rand ~1 zusätzlichen
        Report, leakt aber nie in die Zukunft).
    """
    if offset is None:
        offset = FINRA_PUB_OFFSET_BUSINESS_DAYS
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")
    current = settlement_date
    for _ in range(offset):
        current = next_trading_day(current)
    return current
