"""trading_date.py — Single-Source-of-Truth für das US-Handelstag-Datum.

Diagnose (Wächter 26.10.2026): mehrere Sammel-/Persistenz-Pfade datierten
ihre Einträge mit ``date.today()`` bzw. ``datetime.now(timezone.utc).date()``
— also dem UTC-KALENDERDATUM des Laufs, statt dem US/Eastern-Handelstag, den
der Report tatsächlich abbildet. Der postclose-Lauf (Cron 21:17 UTC) landet
bei GitHub-Actions-Drift regelmäßig NACH Mitternacht UTC, während es in
US/Eastern (UTC-4/-5) noch derselbe Handelstag ist — die UTC-Kalenderdatum-
Variante tickt dann einen Tag zu früh um und verschiebt den Eintrag auf den
FOLGETAG. Belege (SESSION_HANDOVER.md, dieser PR): ``news_coverage_
history.jsonl`` 22./23.10.2026-postclose-Zeilen, ``coverage_history.jsonl``
15 Zeilen, ``options_chain_raw.jsonl`` 28 Zeilen — alle mit ``ts_utc``/
``fetch_ts_utc`` belegt und per ET-Rückrechnung nachgewiesen.

Dieses Modul liefert GENAU EINEN Helper als Ersatz für die abgelösten
``date.today()``-Aufrufe in den betroffenen Sammel-Pfaden (siehe Aufrufer-
Liste im PR-Text). Bewusst KEIN Score-/Filter-/Push-/Exit-/Backtest-Touch —
reine Datums-Berechnung, keine Abhängigkeit zu anderen Projekt-Modulen
(importierbar ohne Zyklus-Risiko, analog ``push_history.py``).

Score-Methodik-Sync: nicht betroffen — reines Infrastruktur-/Logging-Datum,
keine Score-/Filter-/Push-/Exit-/Backtest-Logik berührt (siehe Mini-Stopp-
Prüfung im PR-Text: keine der betroffenen Dateien fließt in score(),
ki_signal_score, Conviction, Top-10, Push, backtest_history,
matured_backtest_export oder freeze_eval ein).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")


def us_trading_date(now_utc: datetime | None = None) -> date:
    """US/Eastern-Kalenderdatum zum Zeitpunkt ``now_utc``.

    ``now_utc`` ist injizierbar (Tests ohne Wall-Clock-Abhängigkeit) und
    darf tz-aware (beliebige Zeitzone) oder naiv sein — ein naiver Wert
    wird als UTC interpretiert (Default-Verhalten von ``datetime.now
    (timezone.utc)`` an den bisherigen Aufrufstellen, unverändert
    übernommen). ``None`` → aktuelle Wall-Clock-Zeit (UTC).

    Dies ist das US-BÖRSEN-Kalenderdatum (Handelstag-Label), NICHT
    notwendigerweise ein tatsächlicher Handelstag (Wochenende/Feiertag
    werden hier NICHT herausgefiltert) — reine Zeitzone-Konvertierung.
    Wochenend-/Feiertags-Logik lebt weiterhin in den jeweiligen Aufrufern
    (z. B. ``run_phase != "postclose"``-Guards, ``_last_workday_before``).
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(_NY).date()


def us_trading_date_iso(now_utc: datetime | None = None) -> str:
    """Wie ``us_trading_date``, aber als ISO-String (``YYYY-MM-DD``) —
    das Format, das alle betroffenen ``report_date_iso``-Parameter
    erwarten."""
    return us_trading_date(now_utc).isoformat()
