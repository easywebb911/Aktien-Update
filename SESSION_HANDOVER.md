# Session-Handover — Stand 08.05.2026

## Heute implementiert (chronologisch)
- 7f2da3b — feat: Phase 2 Stufe 3b-3a — prev_exit_pressure im
  exit_state persistieren (gestern Abend, schon dokumentiert,
  heute im Daily-Run gegen-verifiziert)
- 0eaba01 — feat: Phase 2 Stufe 3b-3b — Eskalation once-per-cross
  + Warnung 12h scharfgeschaltet (cherry-picked auf main nach
  Branch-/PR-Korrektur, byte-identisches Diff zu 460e226)

## Aktive Positionen
- AMC · offen · läuft im Plus (heutige exit_pressure 43,
  profit_lock=warn)
- SABR · offen · läuft im Plus (heutige exit_pressure 22,
  prev_exit_pressure 20 → sauberer Übergang persistiert,
  3b-3a-Verifikation)

## Heute geschlossen
- GRPN · −16.1 % · Stop-Loss durch Pre-Earnings-Risk-Off
  (+35 % Earnings-Pop danach verpasst). Trade-Journal-Eintrag
  mit These und Lesson manuell im Gist nachgepflegt — Decision
  Quality vs. Outcome Quality bewusst getrennt: Stop war
  regelkonform, Outcome leider unglücklich.

## Verifikation morgen früh
- ki_agent-Tick: bei Composite-Cross (`prev_exit_pressure ≤ 75
  < pressure_v`) echter Eskalations-Push raus mit 🚨 +
  `priority=urgent`, kein Cooldown gesetzt
- ki_agent-Tick: bei `pressure_v` 55–75 echter Warnungs-Push
  raus mit ⚠️ + `priority=high` + 12 h-Cooldown via
  `exitp2_warning_<TICKER>`-Key in `agent_state.json`
- Beide Klassen brauchen aktiv ein Trigger-Event — bisher
  liegen AMC bei pressure=43 und SABR bei pressure=22 beide
  unter Warn-Schwelle (55), daher kein Push-Test heute.
  Trigger-Klasse (24 h) bleibt wie 3b-2 gestern verifiziert.

## Geplante Aufgaben (geordnet)
1. Phase 2 Stufe 3c — UI-Notification-History (nächster
   großer Schritt, da Stufe 3b komplett fertig)
2. Pre-Market-Volume als Earliness-Erweiterung —
   Bestandsaufnahme/Plan komplett (Diff ~50–65 Zeilen,
   Conceptual Risk: `change_overnight ≥ 0`-Filter bei
   Score-Effekt-Stufe mitnehmen)
3. Stufe Mittel-2 (Score-Effekt für Earliness) NACH
   Empirik (1–2 Daily-Runs Earliness-Daten — heute null
   Matches im Top-10, datenbedingt)
4. Trade-Journal-Bugs (NEU heute aufgedeckt):
   a) `wlSubmitClose` schreibt `thesis`/`lesson` als
      Leerstring (UI-Bug oder Form-Submit-Pfad)
   b) `max_setup_score` bleibt `null` bei allen Trades —
      `_SCORE_HISTORY`-Lookup zwischen `entry_date` und
      `exit_date` funktioniert nicht
   c) Trade-Journal-UI-Detail-Ansicht zeigt thesis/lesson
      bei Hover/Tap nicht (klärt sich teils — UI rendert
      sie inline nur wenn nicht-leer)
5. Big-Refactor Zwei-Achsen-Ranking (nach 30+ Tagen
   Earliness-Daten)
6. Phase 3 Exit-Signale (Wiedervorlage 15.05.2026)
7. Score-Aufschlüsselung pro Karte (Phase Y)
8. Immediacy-Score-Feature
9. Bahn A2 (Frontend-Auswertungs-Panel)
10. UX Backtesting „Nur Live"-Modus
11. ⏰ Wiedervorlage 19.05.2026: app_data-recovery +
    `POSITIONS_JSON`-Secret löschen
12. ⏰ Wiedervorlage 02.06.2026: Chart-Indikatoren
13. ⏰ Wiedervorlage 02.07.2026: Premium-Daten-Stack
14. Phase X — v1-Pfad-Migration
15. Phase 2 Trigger 4–6 (Setup-Erosion, Catalyst,
    Trend-Bruch)
16. Tier-2-Insight-Builder als Reserve

## Heutige große Themen
- Phase 2 Stufe 3b komplett fertig (3b-3a + 3b-3b an einem
  Tag): alle drei Push-Klassen scharf. Eskalation läuft
  once-per-cross via `prev_exit_pressure`-Vergleich, Warnung
  12 h-Cooldown, Trigger 24 h-Cooldown.
- Severity klassen-spezifisch: Eskalation urgent/🚨, Warnung
  high/⚠️, Trigger high/rotating_light.
- GRPN-Stop-Loss-Aufarbeitung: Decision Quality vs. Outcome
  Quality klar getrennt, Reflexion ins Trade-Journal.
- Architektur-Regel-Verstoß durch Code (Branch + PR statt
  direkt main) sauber korrigiert via Cherry-pick auf main
  + PR-Close + Branch-Delete (Remote-Delete blockiert mit
  HTTP 403, von User manuell erledigt bzw. zu erledigen).
- Daily-Run-Verifikation aller 6 Punkte gegen 7f2da3b
  vollständig grün — Late-Runner-Penalty mit Byte-Belegen
  (DMRC/PCT/RXT/CADL × 0.85 dokumentiert), `prev_exit_pressure`
  in `app_data` persistiert (SABR zeigte 20→22-Übergang).

## Smoke-Test-Status
14/14 grün, f-String-Crash-Test grün, v1==v2 byte-identisch.
Hinweis: f-String-Crash-Test-Längenzahl ist KEIN
Golden-Vertrag — `generate_html_v1` ist nicht rein (liest
Disk-State + Wallclock), Längen-Drift zwischen Sessions ist
legitim, der Test verifiziert nur „raise / kein-raise".

## Architektur-Anker (in CLAUDE.md, hier als Reminder)
- Master-Passwort-Token-Encryption
- Watchlist-Score Single-Source-of-Truth
- v1/v2-Render-Pfad — v2 NICHT autark
- Push-Silence-Filter
- top10_metrics + Phase 2 exit_state
- JSON-Sanitizer
- USD/EUR-Anzeige
- Frontend-Watchlist-Sync
- **Phase 2 Push-Pipeline (KOMPLETT)**: `exitp2_*`-Cooldown-
  Schema, Trigger 24 h scharf, Eskalation once-per-cross via
  `prev_exit_pressure`, Warnung 12 h scharf, Severity
  klassen-spezifisch (urgent/high/high mit
  rotating_light/warning/rotating_light)
- Late-Runner-Penalty: Score × 0.85 bei RSI > 75 ODER
  2T-Move > 20 %
- Earliness-Sub-Score: `compute_earliness_pts` schreibt
  `earliness_pts` + `breakdown` ins Stock-Dict, ohne
  Score-Effekt in Stufe 1
- `prev_exit_pressure` im exit_state: live in Produktion,
  versorgt 3b-3b once-per-cross-Logik
