# Session-Handover — Stand 04.05.2026

## DRINGEND — Vor Phase 2 Stufe 3 erledigen
EUR-Anzeige zusätzlich zu USD in Watchlist-Tiles und
Position-Panel — bei Position-Eröffnung, beim Beobachten
(laufender Wert) und beim Schließen (Verkaufserlös).

Offene Fragen vor Implementierung klären:
- Wechselkurs-Quelle (welche API)?
- Eingefroren beim Entry oder live aktualisiert?
- Display-Format (parallel oder umschaltbar)?

## Heute implementiert (chronologisch)
- dde32d3 — feat: Phase 2 Stufe 1/3 — Exit-Signal-Daten-Pipeline
  (6 Trigger mit Composite-Score, 3 aktiv + 3 als available:false
  markiert für später, Peak-Tracking ratchet-up-only,
  app_data.json["positions"][ticker]["exit_state"]-Schema)
- 14f1584 — feat: Phase 2 Stufe 2a — Position-Status-Block in
  buildPositionStatus, Trigger-Zeilen mit warn/crit-Icons
- ee8dee0 — feat: Phase 2 Stufe 2b-1 — Composite-Anzeige
  "Exit-Druck: X/100" mit Color-Mapping (txt-dim/amber/red)
- 1e3c612 — feat: Phase 2 Stufe 2b-2 — Border-Glow je nach
  Druck-Stufe (additive box-shadow-Komposition, 3D-Look erhalten)
- 92d7e34 — feat: Phase 2 Stufe 2b-3 — Banner "🚨 Exit-Kandidat"
  bei pressure > 75 (XSS-sicher via createElement+textContent,
  has-exit-banner-Parent-Klasse für Watchlist-Tile-Layout)
- 7570cbb — docs: Phase 2 Stufe 3 ins Backlog (Push-Pipeline,
  exitp2_*-Cooldown-Prefix, 2-3 Tage Stabilitäts-Voraussetzung)
- 72b44a0 — fix: KI-Sortierung — NaN-Werte in app_data.json
  brachen den Browser-Fetch komplett. Sanitizer-Helper +
  allow_nan=False in beiden Writern (generate_report.py +
  ki_agent.py), Belt-and-Suspenders gegen Read-Modify-Write-
  Reinfektion via **existing-Spread
- 9fb70c9 — refactor: Methodik-Sektion "Exit-Signal-Berechnung"
  durch lesbare "Wann sollte ich aussteigen?"-Story ersetzt,
  -73/+22 Zeilen, Berechnungs-Logik unverändert

## Aktive Positionen (im Secret POSITIONS_JSON)
- GRPN · offen · läuft im Plus
- AMC · offen · läuft im Plus
- INDI · GESCHLOSSEN am 04.05. mit +13.3% (Trade-Journal)
  · bleibt auf Watchlist als Beobachtung ohne Position

## Verifikation ausstehend
- Beim nächsten Daily-Run morgens 10:00 UTC:
  - exit_state für GRPN/AMC mit plausiblen Composite-Werten?
  - Position-Status-Block sichtbar?
  - Composite-Anzeige korrekt eingefärbt?
  - Border-Glow je nach Druck-Stufe?
  - Banner ggf. bei kritischen Werten?
  - KI-Sortierung im Browser funktioniert?
- Phase 2 Stufe 3 (Push-Pipeline) erst nach 2-3 Tagen
  stabilem UI-Verhalten starten und nach EUR-Ergänzung.

## Geplante Aufgaben
1. EUR-Anzeige (siehe DRINGEND oben)
2. Phase 2 Stufe 3 (Push-Pipeline) — frühestens Donnerstag/
   Freitag, nach UI-Verifikation
3. Phase 3 Exit-Signale (Wiedervorlage 15.05.2026) —
   Blow-off-Top + IV-Crush
4. Score-Aufschlüsselung pro Karte (Phase Y, Backlog)
5. Immediacy-Score-Feature
6. Bahn A2 (Frontend-Auswertungs-Panel) ab Ende Mai
7. UX Backtesting "Nur Live"-Modus
8. Setup-Verfall-Symmetrie weiter beobachten
9. ⏰ Wiedervorlage 02.07.2026: Premium-Daten-Stack prüfen
10. Filter-Flexibilisierung prüfen (Bahn A2)
11. Phase X — v1-Pfad-Migration (drei Schritte zusammen,
    siehe CLAUDE.md-Sektion v1/v2-Render-Pfad)
12. Phase 2 Trigger 4-6 aktivieren sobald Datenquellen da:
    Setup-Erosion, Catalyst, Trend-Bruch

## Optional / niedrig priorisiert
- IBKR Borrow Rate liefert konstant HTTP 404 — Provider-Fallback
- DOUBTFUL Cleanup-Items (rel_strength_sector / sector_etf,
  MIN_REL_VOLUME_INTL)
- Per-Ticker Alert-Lock falls Alert-Loop parallelisiert wird
- Watchlist-Drawer (buildWlDetails) auf neuen Score-Block
- backtest_history.json einmal cachen
- News-Decay-Logik auf UOA / Insider übertragen
- KI-Agent-eigene Anomalien in Chat-Kontext einspeisen
- EDGAR_ACTIVIST_FILERS-Liste über Live-Beobachtung verfeinern
- Smoke-Test-Suite ggf. um weitere kritische Pfade erweitern

## Architektur-Anker (in CLAUDE.md, hier als Reminder)
- Master-Passwort-Token-Encryption (Single-Reader getToken,
  Two-Tier-Storage, versioniertes Krypto-Schema v:1)
- Watchlist-Score Single-Source-of-Truth (3-Stufen-Priorität
  WL_TOP10 → _WL_CARDS → WL_SCORES, defensive _wlScoreOf)
- v1/v2-Render-Pfad — v2 NICHT autark, ruft v1 für Outer-Page
- Push-Silence-Filter (RSI > 75 ODER 2T-Move > 20%, Earnings
  + EDGAR ausgenommen)
- top10_metrics in app_data.json (read-modify-write mit
  **existing-Spread)
- Phase 2 Exit-State (NEU): exit_state pro Position mit
  6 Triggern + Composite-Pressure, Peak-Tracking ratchet-up,
  read-modify-write-Spread bewahrt zwischen ki_agent-Ticks
- JSON-Sanitizer (NEU): NaN/Infinity-Werte werden vor
  json.dump entfernt (allow_nan=False als Belt-and-Suspenders).
  Beide Writer (generate_report._write_app_data_json +
  ki_agent.save_signals) müssen den Sanitizer anwenden, sonst
  Reinfektion via **existing-Spread.

## Smoke-Test-Status
scripts/smoke_render.js: jetzt 6 Szenarien, alle 6 grün.
Heute mehrfach erweitert: Position-Status-Block, Composite-
Score, Border-Glow, Banner — jeweils mit Boundary-Asserts und
Position-Close-Reset-Tests. Smoke-Test extrahiert die JS-
Funktion direkt aus generate_report.py (robust gegen
Render-Verzug der index.html).
