"""trading_date.py — Single-Source-of-Truth für das US-Handelstag-Datum.

Diagnose (Wächter 26.10.2026): mehrere Sammel-/Persistenz-Pfade datierten
ihre Einträge mit ``date.today()`` bzw. ``datetime.now(timezone.utc).date()``
— also dem UTC-KALENDERDATUM des Laufs, statt dem US/Eastern-Handelstag, den
der Report tatsächlich abbildet. Der postclose-Lauf (Cron 21:37 UTC, bis
04.11.2026 21:17) landet bei GitHub-Actions-Drift regelmäßig NACH Mitternacht UTC, während es in
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


# ── Endgültiger Schlusskurs für EINMAL-Felder (Fix 12.11.2026) ─────────────
# Befund (S16, open_item rendite-forward-abendzeile-nicht-final): ab 16:20 ET
# liefert Yahoo für den laufenden Tag teils noch einen vorläufigen Close; ein
# daraus gefülltes Einmal-Feld (return_*, forward_*) wird nie überschrieben.
# Grenze aus Messwerten der Nacht-Probe (diagnose_night_probe): Kurse des
# Tages D gleich der Tag-Referenz um 07:09/07:58/08:15 ET des Folgetags
# (D = 09./10./11.11.2026) und einmal schon um 01:31 ET (D = 11.11.).
# Konservativ: der Close von D gilt ab 07:00 ET des FOLGENDEN KALENDERTAGS
# als endgültig. ``last_final_close_date`` (16:20 ET) bleibt unverändert für
# Pfade, die ihre Werte später ohnehin neu schreiben oder erst nach dem
# Fenster-Ende einfrieren (Rolling-Fenster, Export-Reife).
US_CLOSE_SETTLED_NEXT_DAY_ET = time(7, 0)


def last_settled_close_date(now_utc: datetime | None = None) -> date:
    """Letztes US-Kalenderdatum (ET), dessen Schlusskurs zum Zeitpunkt
    ``now_utc`` ENDGÜLTIG ist: ab ``US_CLOSE_SETTLED_NEXT_DAY_ET`` (07:00 ET)
    der Vortag, davor der Vor-Vortag. Nur ET-Uhrzeit zählt (unabhängig vom
    UTC-Datum des Laufs). Wochenenden/Feiertage brauchen keine Sonderregel:
    an solchen Tagen gibt es keine Tageszeile. ``now_utc`` injizierbar;
    naiv = UTC."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    et = now_utc.astimezone(_NY)
    if et.time() >= US_CLOSE_SETTLED_NEXT_DAY_ET:
        return et.date() - timedelta(days=1)
    return et.date() - timedelta(days=2)


def close_is_settled(day: date, now_utc: datetime | None = None) -> bool:
    """True, wenn der Schlusskurs von ``day`` zum Zeitpunkt ``now_utc``
    endgültig ist (``day <= last_settled_close_date(now_utc)``)."""
    return day <= last_settled_close_date(now_utc)


# ── Handelstag-Fenster (Fix 13.11.2026, open_item max-gain-rolling-fenster-abgeschnitten)
def is_us_trading_day(d: date, holidays) -> bool:
    """Mo–Fr und nicht in ``holidays`` (Menge ISO-Strings, z. B.
    ``config.US_MARKET_HOLIDAYS``). Pure; ``holidays`` wird übergeben, damit
    dieses Modul ohne Projekt-Import bleibt."""
    return d.weekday() < 5 and d.isoformat() not in holidays


def nth_trading_day_after(d: date, n: int, holidays) -> date:
    """Der ``n``-te US-Handelstag NACH ``d`` (``n = 0`` → ``d`` selbst).
    Tag 10 des max_gain-/max_drawdown-Fensters = ``nth_trading_day_after(D, 10)``.
    Hängt nur vom Kalender ab — nicht von Uhrzeit oder Laufzeitpunkt."""
    out = d
    k = 0
    while k < n:
        out += timedelta(days=1)
        if is_us_trading_day(out, holidays):
            k += 1
    return out
