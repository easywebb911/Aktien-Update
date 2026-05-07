# Session-Handover — Stand 07.05.2026

## Heute implementiert (chronologisch)
- 7f2da3b — feat: Phase 2 Stufe 3b-3a — prev_exit_pressure im
  exit_state persistieren
  (Schema-Erweiterung in _compute_exit_state, Vorbereitung für
  once-per-cross-Eskalation in 3b-3b)

## Aktive Positionen
- GRPN · offen · läuft im Plus (PnL +4.0 %, exit_pressure 20)
- AMC · offen · läuft im Plus (PnL +3.7 %, exit_pressure 39)
- NUVB · offen (PnL +0.8 %, exit_pressure 25)

## Verifikation morgen früh
- Daily-Run regeneriert index.html mit:
  - NUVB/AMC zeigen Preis und P&L im Position-Panel
  - Late-Runner-Penalty wirkt: TEAD-style 100-Tickers fallen
    auf 85
  - prev_exit_pressure-Feld in positions[*].exit_state befüllt
    (NEU 3b-3a) — beim ERSTEN Run nach Deploy ist der Wert
    None, ab dem zweiten Daily-Run erscheint der echte Vorwert
- ki_agent-Tick logged earliness_pts pro Ticker (Mittel-1)
- ki_agent-Tick versendet bei Crit-Triggern echte Pushes
  (3b-2, 24h-Cooldown), exit_cooldowns füllt sich

## Geplante Aufgaben
1. Pre-Market-Volume als Earliness-Erweiterung — Plan vorhanden,
   Diff ~50-65 Zeilen, neuer 1m-prepost-Fetch-Pfad mit Timezone-
   Handling. Wichtiger Conceptual-Risk-Hinweis aus
   Bestandsaufnahme: change_overnight≥0-Filter sollte bei
   Score-Effekt-Stufe (Mittel-2) mit drin sein, sonst Bad-News-
   Panikverkauf als „Earliness" missinterpretierbar.
   START NACH Daily-Run-Verifikation morgen früh.
2. Phase 2 Stufe 3b-3b — Eskalation + Warnung scharfschalten
   (once-per-cross für Eskalation via prev_exit_pressure-
   Vergleich, 12h-Cooldown für Warnung, klassen-spezifische
   ntfy-Severity: urgent für Eskalation, high für Warnung).
   START NACH erfolgreicher Verifikation 3b-3a im Daily-Run.
3. Phase 2 Stufe 3c (UI-Notification-History)
4. Stufe Mittel-2 (Score-Effekt für Earliness) NACH
   Empirik-Auswertung der Logs (mind. 1-2 Daily-Runs Daten)
5. Big-Refactor Zwei-Achsen-Ranking (Setup × Earliness),
   nach 30+ Tagen Earliness-Daten
6. Phase 3 Exit-Signale (Wiedervorlage 15.05.2026)
7. Score-Aufschlüsselung pro Karte (Phase Y)
8. Immediacy-Score-Feature
9. Bahn A2 (Frontend-Auswertungs-Panel)
10. UX Backtesting „Nur Live"-Modus
11. ⏰ Wiedervorlage 19.05.2026: app_data-recovery +
    POSITIONS_JSON-Secret löschen
12. ⏰ Wiedervorlage 02.06.2026: Chart-Indikatoren
13. ⏰ Wiedervorlage 02.07.2026: Premium-Daten-Stack
14. Phase X — v1-Pfad-Migration
15. Phase 2 Trigger 4-6 (Setup-Erosion, Catalyst, Trend-Bruch)
16. Tier-2-Insight-Builder als Reserve

## Heutige große Themen
- Stufe 3b-3 in zwei Mini-Mini-Stufen zerlegt (3b-3a Schema,
  3b-3b Push-Logik) — saubere Variante „perfekte Lösung"
  gewählt: once-per-cross statt Zeit-Cooldown für Eskalation,
  dafür Vorwert-Persistenz im exit_state-Schema nötig
- Read-only-Bestandsaufnahme + Plan-Phase + Längen-Drift-
  Klärung VOR der Implementierung — keine Improvisation,
  jeder Schritt zuerst verifiziert
- Längen-Drift im f-String-Crash-Test (337743 → 337718) als
  Disk-State/Mock-Artefakt entlarvt, kein Code-Drift
  (a7d5921 ist nur Doku, kategorisch ausgeschlossen)
- Pre-Market-Volume-Erweiterung: Bestandsaufnahme + Plan
  komplett, Implementierung auf morgen vertagt nach
  Risiko-Analyse von Code (kein Mini-Add-On, sondern neuer
  Fetch-Pfad mit DST/Timezone-Risiko + Conceptual Risk
  Bad-News-Panikverkauf)

## Architektur-Anker (in CLAUDE.md, hier als Reminder)
- Master-Passwort-Token-Encryption
- Watchlist-Score Single-Source-of-Truth
- v1/v2-Render-Pfad — v2 NICHT autark
- Push-Silence-Filter
- top10_metrics + Phase 2 exit_state
- JSON-Sanitizer
- USD/EUR-Anzeige
- Frontend-Watchlist-Sync
- Phase 2 Push-Pipeline: exitp2_*-Cooldown-Schema in
  agent_state.json, Trigger-Push 24h aktiv (3b-2),
  Eskalation+Warnung noch Logs (3b-3 in Vorbereitung)
- Late-Runner-Penalty: Score × 0.85 bei RSI > 75 ODER
  2T-Move > 20 %
- Earliness-Sub-Score: compute_earliness_pts schreibt
  earliness_pts + breakdown ins Stock-Dict, ohne Score-Effekt
  in Stufe 1; Score-Effekt erst nach Empirik-Verifikation
- Phase 2 exit_state-Schema (NEU 3b-3a): prev_exit_pressure
  als Snapshot des vorigen Daily-Run-Werts persistiert; None
  bei Erstanlage / fehlendem prev_state / nicht-int-castbarem
  Wert. Wird in 3b-3b für once-per-cross-Eskalations-Logik
  gegen den aktuellen exit_pressure verglichen.

## Smoke-Test-Status
14/14 grün, Echter f-String-Crash-Test ist Standard-Pflicht.
Hinweis: f-String-Crash-Test-Längenzahl ist KEIN
Golden-Vertrag — generate_html_v1 ist nicht rein (liest
Disk-State + Wallclock), Längen-Drift zwischen Sessions ist
legitim, der Test verifiziert nur „raise / kein-raise".
