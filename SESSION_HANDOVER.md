# Session-Handover — Stand 07.05.2026

## Heute implementiert (chronologisch)
- d0d57e4 — feat: Phase 2 Stufe 3a (Cooldown-Infrastruktur in
  ki_agent.py, KEIN Push-Versand)
- ad52abc — feat: Phase 2 Stufe 3b-1 (Trigger-Auswertung mit
  WOULD-PUSH-Logging, KEIN echter Push)
- 1833ed4 — feat: Phase 2 Stufe 3b-2 (Trigger-Push-Klasse
  scharfgeschaltet, 24h-Cooldown, Eskalation+Warnung bleiben
  noch Logs)
- a6a9209 — fix: price-Feld in watchlist_cards für Ticker mit
  manual_personal-Bypass-only (NUVB/AMC zeigten 0)
- 296a1e7 — feat: Score-Methodik Quick-Win Late-Runner-Penalty
  (Score × 0.85 bei RSI > 75 ODER 2T-Move > 20%)
- 507218c — feat: Score-Methodik Mittel-1 Earliness-Sub-Score
  (compute_earliness_pts, NUR Logging, kein Score-Effekt)

## Aktive Positionen
- GRPN · offen · läuft im Plus
- AMC · offen · läuft im Plus

## Verifikation morgen früh
- Daily-Run regeneriert index.html mit:
  - NUVB/AMC zeigen jetzt Preis und P&L im Position-Panel
  - Late-Runner-Penalty wirkt: TEAD-style 100-Tickers fallen
    auf 85
- ki_agent-Tick logged Earliness-Pts pro Ticker (Mittel-1)
- ki_agent-Tick versendet bei Crit-Triggern echte Pushes
  (3b-2, 24h-Cooldown)

## Geplante Aufgaben
1. Stufe Mittel-2 (Score-Effekt für Earliness) NACH
   Empirik-Auswertung der Logs (mind. 1-2 Daily-Runs Daten)
2. Phase 2 Stufe 3b-3 (Eskalations- + Warnungs-Pushes
   scharfschalten)
3. Phase 2 Stufe 3c (UI-Notification-History)
4. Big-Refactor Zwei-Achsen-Ranking (Setup × Earliness),
   nach 30+ Tagen Earliness-Daten
5. Pre-Market-Volume als Earliness-Erweiterung (low-hanging
   fruit)
6. Phase 3 Exit-Signale (Wiedervorlage 15.05.2026)
7. Score-Aufschlüsselung pro Karte (Phase Y)
8. Immediacy-Score-Feature
9. Bahn A2 (Frontend-Auswertungs-Panel)
10. UX Backtesting "Nur Live"-Modus
11. ⏰ Wiedervorlage 19.05.2026: app_data-recovery +
    POSITIONS_JSON-Secret löschen
12. ⏰ Wiedervorlage 02.06.2026: Chart-Indikatoren
13. ⏰ Wiedervorlage 02.07.2026: Premium-Daten-Stack
14. Phase X — v1-Pfad-Migration
15. Phase 2 Trigger 4-6 (Setup-Erosion, Catalyst, Trend-Bruch)
16. Tier-2-Insight-Builder als Reserve

## Heutige große Themen
- Phase 2 Stufe 3 in 3 Mini-Mini-Stufen (3a, 3b-1, 3b-2)
- NUVB/AMC-Preis-Bug strukturell behoben
- Score-Methodik um Late-Runner-Penalty + Earliness-Sub-Score
  erweitert (TEAD-Phänomen adressiert)

## Architektur-Anker (in CLAUDE.md, hier als Reminder)
- Master-Passwort-Token-Encryption
- Watchlist-Score Single-Source-of-Truth
- v1/v2-Render-Pfad — v2 NICHT autark
- Push-Silence-Filter
- top10_metrics + Phase 2 exit_state
- JSON-Sanitizer
- USD/EUR-Anzeige
- Frontend-Watchlist-Sync
- Phase 2 Push-Pipeline (NEU): exitp2_*-Cooldown-Schema in
  agent_state.json, Trigger-Push 24h aktiv, Eskalation+Warnung
  noch Logs
- Late-Runner-Penalty (NEU): Score × 0.85 bei RSI > 75 ODER
  2T-Move > 20%
- Earliness-Sub-Score (NEU): compute_earliness_pts schreibt
  earliness_pts + breakdown ins Stock-Dict, ohne Score-Effekt
  in Stufe 1; Score-Effekt erst nach Empirik-Verifikation

## Smoke-Test-Status
14/14 grün, Echter f-String-Crash-Test ist Standard-Pflicht.
