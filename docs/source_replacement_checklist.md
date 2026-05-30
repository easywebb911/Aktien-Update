# Datenquellen-Ersatz-Checkliste

## Wann diese Checkliste nutzen
- Ein Health-Digest meldet, dass ein Provider tot/leer ist (stiller Tod)
- Eine Quelle liefert plötzlich 404 / leere Werte / Paywall
- Es wird eine bessere oder gratis Alternative zu einer bestehenden Quelle gesucht

## Schritt 1 — Ist die alte Quelle wirklich tot? (erst prüfen, nicht annehmen)
- [ ] Alte URL im Browser öffnen — 404? Umgeleitet? Leer?
- [ ] Neue/andere URL-Struktur probieren (Quelle hat evtl. nur umgezogen)
- [ ] Werte noch im HTML, nur Parser bricht? → kleiner Fix, kein Quellenwechsel
- [ ] Werte ganz weg / hinter Login / "Pro"-Hinweis? → Quelle tot, Wechsel nötig
- [ ] Bei Pipeline-Verdacht: GitHub-Actions-Log auf echte HTTP-Antwort prüfen
  (200 + leer = Parser/Schema-Drift; 403 = Block; 404 = URL weg)

## Schritt 2 — Kandidaten-Quelle bewerten (die 5 K.-o.-Kriterien)
Für jede mögliche neue Quelle prüfen — ein "Nein" reicht oft zum Aussortieren:
- [ ] GRATIS? (oder bezahlbar — Preis notieren. Kostenpflichtig nur wenn
  empirisch belegter Trading-Wert die Kosten rechtfertigt)
- [ ] KEIN Login nötig? (Login-gebundene Daten kann das Tool nicht scrapen)
- [ ] STATISCHES HTML / echte API? (JS-gerendert = Parser sieht nichts,
  im Browser per "Seitenquelltext anzeigen" prüfen)
- [ ] KEIN Cloudflare-/Bot-Block? (403 / Challenge-Seite = nicht scrapebar)
- [ ] DECKT DEN POOL? (liefert die Quelle auch Smallcaps/unsere Ticker, nicht
  nur Large-Caps?)

## Schritt 3 — Robustheit / Langlebigkeit
- [ ] Update-Frequenz ausreichend? (intraday/täglich vs. nur 2×/Monat)
- [ ] Rate-Limit verträglich? (unsere Last: Top-10 + ~17 KI-Ticks/Tag)
- [ ] Quelle als Scraping-Ziel stabil? (offizielle Datei/API > gescrapte Webseite)
- [ ] Bevorzugen: offizielle Download-Datei oder API VOR HTML-Scraping
  (Lehre: Stockanalysis-HTML war fragiler als der direkte IBKR-Datei-Download)

## Schritt 4 — Vor dem Einbau (Sicherheit)
- [ ] Score-relevant? → Diagnose-first, manueller Merge, Ursache beweisen
- [ ] Persistenz mitbauen (Feld additiv, schema bleibt v4, S10_OBSERVED) —
  sonst sammelt der reparierte Fetcher ins Leere
- [ ] success_check INHALT prüfen lassen (echte Werte, nicht nur Dict-nicht-leer)
  + coverage_pct setzen → stiller Tod wird künftig sichtbar
- [ ] Live-Verifikation NACH Einbau (greift die Quelle real? Werte plausibel?)

## Schritt 5 — Empirisch validieren (nicht auf Verdacht vertrauen)
- [ ] Coverage 60-90 Tage sammeln, BEVOR die Quelle als Edge-Signal gilt
- [ ] Literatur-Stärke ≠ Edge im eigenen gefilterten Universe (Range-Restriction)
- [ ] Erst wenn eigene Daten die Edge belegen → Gewichtung/Investition rechtfertigen

## Bekannte Quellen (Stand 31.05.2026)
- Cost-to-Borrow GRATIS: direkte IBKR-Datei (öffentlich, pipe-getrennt, kein
  Login) + iBorrowDesk (gratis Aufbereitung der IBKR-Daten, CSV, deckt Smallcaps)
- Cost-to-Borrow + Utilization KOSTENPFLICHTIG: ORTEX (API, ~50-200$/Mt),
  Fintel (~15$/Mt, scrapebar aber Cloudflare-Risiko)
- Utilization GRATIS: keine zuverlässige Quelle gefunden (IBKR-Dashboard hat
  sie, aber nur im eingeloggten Terminal)
- Short-Interest: yfinance (nutzen wir bereits), Stockanalysis (SI lebt noch,
  nur Borrow wurde entfernt)

## Lerngeschichte (warum es diese Checkliste gibt)
Stockanalysis-Borrow-Fetcher war ≥16 Tage still tot — HTTP-200, aber alle
Werte None, kein Alarm (laschen success_check). Borrow-Daten wurden von der
öffentlichen Seite hinter Pro-Tier entfernt. Gratis-Ersatz (IBKR-Direktdatei)
lag die ganze Zeit ungenutzt da. Lehre: Quellen still überwachen (Inhalt, nicht
nur HTTP-Status) UND bei Ausfall systematisch Alternativen prüfen statt zu raten.
