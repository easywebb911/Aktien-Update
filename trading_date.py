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

from datetime import date, datetime, time, timedelta, timezone
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


# ── US-Börsenzeiten (reguläre Session) in US/Eastern — EINE Quelle ─────────
# Fix 02.11.2026: Börsenzeiten standen an mehreren Stellen fest in UTC
# (13:30–20:00 = nur die Sommerzeit-Projektion). Seit der US-Zeitumstellung
# (01.11.2026) öffnet die Börse 14:30 UTC und schließt 21:00 UTC. Die Grenzen
# werden deshalb aus der Ostküstenzeit abgeleitet (DST-korrekt über
# ``zoneinfo``). Wochenenden/Feiertage werden hier bewusst NICHT
# berücksichtigt (unverändert zum bisherigen Verhalten der Aufrufer).
US_SESSION_OPEN_ET  = time(9, 30)
US_SESSION_CLOSE_ET = time(16, 0)
# Ein Tages-Schlusskurs gilt erst als FINAL, wenn der US-Handelstag (ET)
# vorbei ist: an einem Folgetag oder am selben Tag ab 16:20 ET. Die 20 Minuten
# Puffer nach ``US_SESSION_CLOSE_ET`` (16:00) decken die Schlussauktion und
# die verzögerte Konsolidierung der Tageszeile bei Yahoo ab. Wochenenden/
# Feiertage brauchen keine Sonderbehandlung: an solchen Tagen existiert keine
# Tageszeile. Seit 04.11.2026 zugleich die EINE Postclose-Grenze: erst ab hier
# gilt ein Lauf als postclose (``us_session_state`` → "post") und darf
# Backtest-Einträge anlegen (Vintage-Guard in ``backtest_history``).
US_CLOSE_FINAL_ET = time(16, 20)


def us_session_state(now_utc: datetime | None = None) -> str:
    """``"pre"`` (vor 09:30 ET), ``"open"`` (09:30 ≤ ET < 16:00),
    ``"closing"`` (16:00 ≤ ET < ``US_CLOSE_FINAL_ET`` = 16:20: Börse zu,
    Schlusskurs aber noch nicht final) oder ``"post"`` (ab 16:20 ET) zum
    Zeitpunkt ``now_utc`` — gerechnet in US/Eastern (DST-korrekt).
    Fix 04.11.2026: ``"post"`` (= postclose zulässig) beginnt erst bei
    ``US_CLOSE_FINAL_ET``, vorher schon bei 16:00. ``now_utc`` injizierbar;
    naiv = UTC (wie ``us_trading_date``)."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    t = now_utc.astimezone(_NY).time()
    if t < US_SESSION_OPEN_ET:
        return "pre"
    if t < US_SESSION_CLOSE_ET:
        return "open"
    if t < US_CLOSE_FINAL_ET:
        return "closing"
    return "post"


# ── Finaler Schlusskurs (Fix 03.11.2026, Rendite-Diagnose #645) ────────────
# ``US_CLOSE_FINAL_ET`` steht oben bei den Börsenzeiten (seit 04.11.2026 auch
# die Postclose-Grenze in ``us_session_state``).


def last_final_close_date(now_utc: datetime | None = None) -> date:
    """Letztes US-Kalenderdatum (ET), dessen Tages-Schlusskurs zum Zeitpunkt
    ``now_utc`` final ist: der heutige ET-Tag ab ``US_CLOSE_FINAL_ET``,
    sonst der Vortag. Eine Tageszeile mit Datum ``<=`` diesem Wert ist
    abgeschlossen; jüngere Zeilen sind laufend (Intraday) und dürfen nicht
    als Schlusskurs gelten. ``now_utc`` injizierbar; naiv = UTC."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    et = now_utc.astimezone(_NY)
    if et.time() >= US_CLOSE_FINAL_ET:
        return et.date()
    return et.date() - timedelta(days=1)
