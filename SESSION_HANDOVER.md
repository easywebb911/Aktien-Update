# Session-Handover — Stand 10.05.2026 (späte Abend-Session)

## Heute implementiert (chronologisch, alle gemerged via PR)

### Backtest-Panel-Verbesserungen

- `20d19de` — feat: Backtest dünne Buckets (n<20) visuell als statistisch
  unsicher markieren — gemerged via PR #81
- `d64f247` — feat: Backtest Mean-Renditen zusätzlich zu Median anzeigen
  — gemerged via PR #86
- `fa60721` — feat: Backtest Min/Max-Range zusätzlich zu Median und Mean
  anzeigen — gemerged via PR #88
- `a00ab67` — feat: Backtest Mean-vs-Median-Spread-Indikator
  (Verteilungs-Schiefe) — gemerged via PR #92
- `c842536` — feat: Backtest-Skew-Indikator bei n<MIN_BUCKET_N grau
  statt suppress — gemerged via PR #93
- `edc9cfb` — feat: Backtest-Panel UX-Polish (Toggles, Farbe, Bucket-
  Trennung, Stern-Icon) — gemerged via PR #94
- `36e7e7e` — feat: SI-Trend-Vergleich-Box mit klaren Labels
  (Trefferquote / Median / Hinweistext) — gemerged via PR #105

### Phase 2 Stufe 3c-2 — push_history-Spiegel

- `6230fd2` — feat: Phase 2 Stufe 3c-2 — push_history in app_data.json
  materialisieren — gemerged via PR #82

### Code-Hygiene Refactors

- `1721835` — refactor: _drivers_breakdown auf zentrale
  DRIVER_CLASSIFICATIONS-Tabelle umbauen (Punkt 6/A) — PR #83
- `c68d4e5` — refactor: Score-Formel-Box aus SCORE_FORMULA_ITEMS
  auto-generieren (Punkt 5/1) — PR #84
- `d635b99` — docs: Code-Hygiene-Backlog-Status aktualisieren — PR #85

### Conviction-Score-Aufbau

- `acd4597` — docs: Backtest-Verteilungs-Erkenntnis als Lesson verankern
  (Median vs Mean) — gemerged via PR #87
- `6970d27` — feat: Conviction-Score Schritt A — Berechnungs-Logik
  (ohne UI) — gemerged via PR #89
- `0cea357` — fix: vix_current Persistenz im Daily-Run via
  **existing-Spread (analog zu ki_agent) — gemerged via PR #90
- `2431704` — feat: Conviction-Score Schritt B — UI-Integration auf
  Stock-Fliese — gemerged via PR #95
- `3e949d8` — fix: apply_conviction_scores vor generate_html
  (Pipeline-Reihenfolge für UI-Render) — gemerged via PR #96
- `82d8e51` — feat: Conviction-UI Nachschärfung (Sortier-Option, Größe,
  Methodik-Block) — gemerged via PR #97

### Methodik-Asymmetrien

- `d5c59cd` — fix: Methodik-Display zeigt jetzt bedingte Boni
  (SI-Trend-Beschleunigung, Agent-Boost-Bandbreite) — PR #98
- `ee60986` — feat: Methodik-Display Schritt 2 — FINRA-Bonus und
  Late-Runner-Penalty in Boni-Box — gemerged via PR #99
- `1da0442` — docs: KI-Score-Block in Score-Methodik-Sektion ergänzen
  — gemerged via PR #107

### UX-Detail

- `74b5f24` — feat: Trade-Journal Entry-Score-Bucket + Conviction
  snapshot — gemerged via PR #91
- `0c10456` — feat: Trade-Journal 7-Tage-Filter ergänzen — gemerged
  via PR #100

### Tagesabschluss (Doku-Drift-Fix nach Guardian-Check)

- `0b8a6f4` — docs: CLAUDE.md Drivers-Block-Tabelle — Borrow-Rate auf
  zwei Buckets (>100 extreme, >50..100 hot) erweitert — gemerged via
  PR #103. Vom Squeeze-Guardian aufgespürt: Tabelle zeigte nur
  „> 50 %/Jahr", Code (`_drivers_breakdown`) hat aber zwei Schwellen
  mit unterschiedlichen Gewichten.

### Späte Abend-Session — UI-Polish, Conviction-Push, Severity-Tiering

- `5af7510` — fix: Watchlist-Drawer KI-Analyse läuft inline (geteilter
  `_kiAnalyseFromCtx`-Kern), News-Toggle defensiver mit explicit
  attribute-toggle + `scrollIntoView` — gemerged via PR #106
- `0e55b5a` — feat: Exit-Druck-Composite-Zeile immer anzeigen (auch
  bei ruhigen Triggern, dezent „Alle Frühwarn-Signale ruhig"-Hinweis)
  — gemerged via PR #108
- `f4db74c` — feat: Conviction-basierte Push-Trigger (`conviction_high`
  mit Threshold-Crossing-Logik, `prev_conviction_scores`-Persistenz
  in `agent_state.json`) — gemerged via PR #109
- `c3d9737` — feat: Severity-Tiering — Conviction high, andere
  Anomaly-Trigger medium — gemerged via PR #110

## Aktive Positionen (im Gist `squeeze_data.json`)

- **AMC** · offen · läuft im Plus
- **SABR** · offen · läuft im Plus

## Verifikation morgen früh nach erstem Trading-Tag-Daily-Run

- **Conviction-Push:** erreicht ein Setup im Daily-Run conviction ≥ 75,
  feuert beim ersten Hourly-Tick ein `conviction_high`-Push („🎯
  KAUFSIGNAL …")? `agent_state.json["prev_conviction_scores"]` muss
  nach dem ersten Tick die heutigen Werte enthalten — danach gilt
  Threshold-Crossing-Logik (Sustained-High feuert NICHT erneut).
- **Severity-Unterschied im Push-Stream:** Conviction- / Perfect-Storm-
  / Monster-Backup-Pushes erscheinen mit `severity="high"` in
  `push_history`, alle anderen Anomaly-Trigger mit `severity="medium"`.
  Hinweis: ntfy-Priority ist aktuell hardcoded `high` für alle (siehe
  Backlog-Punkt zu ntfy-Priority-Mapping) — Tiering wirkt heute nur
  in der State-Datei + Frontend-Anzeige.
- **Exit-Druck-Composite bei SABR sichtbar:** Watchlist-Tile SABR
  aufklappen → Position-Status-Block mit „Exit-Druck: 26/100" und
  dezenter „Alle Frühwarn-Signale ruhig"-Zeile. AMC zeigt
  zusätzlich 🟡 Profit-Lock-Zeile (unverändert).
- **Watchlist-Toggles funktionieren:** auf jeder Watchlist-Karte
  (auch Nicht-Top-10-Tickern) „Details anzeigen" / „Aktuelle
  Meldungen" / „KI-Analyse" einzeln testen. KI-Analyse läuft
  jetzt inline im Drawer (kein Redirect zur Main-Karte mehr); bei
  Watchlist-Tickern ohne Daten erscheint Graceful-Fallback.
- **Conviction-Werte mit echten VIX und Anomaly-Triggern:** Erreichen
  ≥ 75-Setups jetzt high-Level (grün)? Heutige Top-10 hatten
  durchschnittlich Conviction ~50 (medium), nachdem PR #90 vix_current
  preserviert. Trading-Tag bringt frische RVOL-Spikes → mehr Anomaly-
  Trigger → höhere Conviction-Komponenten.
- **`chg_pct` in `agent_signals.json`:** sollte nicht mehr 0.0 sein
  (Wochenend-Effekt verschwindet — Mo-Fr liefert echte Tagesdifferenz).
- **Backtest-Mediane mit weiteren Tagen Daten:** Bucket-Cards zeigen
  zunehmend stabile Werte; Skew-Indikator dürfte beim ≥ 70-Bucket /
  10T-T+1 weiterhin „rechtsschief" zeigen, jetzt mit n > 11.
- **Earliness-Werte in echten Top-10:** heute waren 9/10 Top-10 zu
  „heißgelaufen" (RSI > 60 oder change_5d ≥ 5 %). Bei einem ruhigeren
  Trading-Tag könnten frühere Setups in der Top-10 erscheinen — mit
  earliness_pts > 0.

## Geplante Aufgaben

1. **Conviction-Formel-Anpassung** — nach 1–2 Trading-Tagen beobachten:
   bleibt Earliness systematisch 0 in der Top-10? Ggf. Earliness-Cap
   28 → 14 (Score-Budget zu Setup oder Anomaly verschieben), oder
   Earliness-Filter weicher (RSI < 65 statt 60, change_5d < 7 statt 5).
   User-Entscheidung nach Empirik.
2. **Phase 2 Stufe 3c-3** — UI Notification-History (NACH 3c-2 = PR #82
   bereits live).
3. **Stufe Mittel-2** — Score-Effekt für Earliness aktivieren NACH
   1–2 Daily-Runs mit gefüllter PM-Vol-Komponente.
4. **Backtest-T+0/T+1-Auswertung** — Frontend-Verifikation läuft
   weiter; je Score-Bucket sollten 30+ Tage Live-R-Werte für
   belastbare Mediane vorliegen.
5. **Big-Refactor Zwei-Achsen-Ranking** — nach 30+ Tagen Earliness-
   Daten.
6. **Phase 3 Exit-Signale** — Wiedervorlage 15.05.2026.
7. **Score-Aufschlüsselung pro Karte** (Phase Y).
8. **Immediacy-Score-Feature**.
9. **Bahn A2** — Frontend-Auswertungs-Panel (≥ 200 Live-Backtest-
   Einträge erforderlich).
10. **UX Backtesting „Nur Live"-Modus**.
11. ⏰ **Wiedervorlage 19.05.2026** — `app_data`-recovery +
    `POSITIONS_JSON`-Secret löschen.
12. ⏰ **Wiedervorlage 02.06.2026** — Chart-Indikatoren.
13. ⏰ **Wiedervorlage 02.07.2026** — Premium-Daten-Stack.
14. **Phase X** — v1-Pfad-Migration (siehe Code-Hygiene Punkt 2).
15. **Phase 2 Trigger 4** — Setup-Erosion (verbleibendes Stub).
    Braucht Entry-Snapshot (dtc/short_float/cost_to_borrow) im Gist
    — Schema-Erweiterung am Position-Open-Form notwendig.
    Trigger 5 (catalyst, forward-looking Earnings-Lookup, Finnhub
    + yfinance-Fallback) ist seit PR #116 live, Trigger 6
    (trend_break, EMA21) seit PR #113.
16. **Tier-2-Insight-Builder** als Reserve.
17. **Methodik-Asymmetrien Schritt 3** — Late-Runner-Penalty- und
    FINRA-Konstanten-Display ist seit PR #99 aus `config.py` gelesen,
    aber `score_bonus()` selbst und `apply_late_runner_penalty()`
    nutzen die Werte unverändert. Sollten weitere bedingte Boni
    eingeführt werden (z. B. neue ki_agent-Multiplikator-Pfade), muss
    der Display-String beide Pfade reflektieren — Pflege-Regel in
    CLAUDE.md Score-Methodik-Sync-Regel-Sektion dokumentiert.
18. **NEU: ntfy-Priority-Mapping nach Severity** — `_send_anomaly_ntfy`
    sendet aktuell hardcoded `Priority: high` an ntfy, unabhängig
    vom Severity-Wert. Für echtes Tiering auf dem Handy müsste ein
    `severity`-Parameter eingeführt und auf ntfy-Priority gemappt
    werden (high → `urgent`, medium → `default`/`high`). Vom
    Squeeze-Guardian in der Konformitäts-Prüfung als bewusstes,
    in CLAUDE.md dokumentiertes Verhalten erkannt — kein Bug, nur
    Backlog-Erweiterung.

## Strategische Roadmap

### Übergeordnetes Ziel

Squeeze-Früherkennungssystem mit empirisch validierter Edge. Drei
parallele Arbeitsstränge:

- **Bauen** — Code-Erweiterungen (neue Trigger, UI-Ergänzungen,
  Persistenz-Schichten).
- **Sammeln** — passives Warten auf Backtest- und Earliness-Empirik
  (jeder Daily-Run + ki_agent-Tick füttert die History).
- **Validieren** — Score-Logik gegen reale R-Werte testen, sobald
  genug Datenpunkte da sind.

### Drei Zeit-Achsen

**Kurzfristig (Tage bis 1–2 Wochen, aktiv planbar)**

- **Conviction-Score Stage 2** — Plausibilitäts-Beobachtung über
  Trading-Woche; ggf. Komponenten-Gewichte rekalibrieren wenn
  Earliness systematisch 0 bleibt.
- **Conviction-Push-Verifikation** — beobachten, ob `conviction_high`-
  Trigger in der ersten Trading-Woche überhaupt feuert; falls 75-
  Schwelle nie erreicht wird, Schwellen-Kalibrierung erwägen.
- **Stufe Mittel-2** — Earliness-Score-Effekt aktivieren, sobald
  1–2 Daily-Runs mit drei Komponenten plausible Werte zeigen.
- **Phase 3 Exit-Signale** (Wiedervorlage 15.05.2026).
- **Phase 2 Stufe 3c-3** — UI-Notification-History.
- **Phase 2 Trigger 4 (setup_erosion)** — von Stub auf echte Daten
  umstellen; trend_break ist seit PR #113 live, catalyst seit
  PR #116.

**Mittelfristig (Wochen, datenabhängig)**

- **Backtest-Validierung** — Frontend-Auswertung Backtest-T+0/T+1
  funktioniert erst belastbar, sobald je Score-Bucket
  (`<50`/`50–69`/`≥70`) mindestens 30 Tage Live-R-Werte vorliegen.
  Mean-vs-Median-Skew (PR #92/#93) gibt schon heute hilfreiche
  Hinweise auf rechtsschiefe Squeeze-Knaller.
- **Bahn A2** — Frontend-Auswertungs-Panel (≥ 200 Live-Backtest-
  Einträge erforderlich).
- **ntfy-Priority-Mapping nach Severity** — sobald sich das Tiering
  als sinnvoll bestätigt, ntfy-Priority an `severity` koppeln.

**Längerfristig (Monate, Empirik-basiert)**

- **Big-Refactor Zwei-Achsen-Ranking** — nach 30+ Tagen Earliness-
  Daten.
- **Premium-Daten-Stack** (Wiedervorlage 02.07.2026).
- **Sektor-Rotation / Marktkontext** — noch nicht im Backlog.

### Lackmus-Test

**Phase 3 Validieren ist der entscheidende Test.** Backtest muss
zeigen: Score ≥ 70 hat einen klar besseren Median-R-Wert nach 5T
als Score < 50.

- **Wenn ja** → Earliness-Score-Aktivierung und Big-Refactor mit
  Rückenwind.
- **Wenn nein** → Score-Komponenten **neu kalibrieren bevor weiter
  gebaut wird**.

Bis der Test laufen kann, ist passives Sammeln der primäre Modus.
Conviction-Score (PR #89/#95) liefert die Aktions-Frage als
zusätzlichen Indikator, ohne die Score-Logik selbst zu verändern —
ein „nur unterstützender" Baustein im Sinne der Roadmap. Der neue
`conviction_high`-Push (PR #109) macht die Aktions-Achse jetzt auch
außerhalb des Frontends sichtbar; das Severity-Tiering (PR #110)
trennt Aktions-Signale von Beobachtungs-Signalen im Push-Stream
sauber.

## Heutige große Themen

- **Backtest-Panel komplett ausgebaut.** Sechs Iterationen vom
  Grau-Dimming dünner Buckets über Mean/Min/Max/Skew-Anzeige bis
  zum UX-Polish (kompakte Toggles, neutrale Hit-Chart-Farbe,
  Bucket-Cards, Akzent-Stern). Verteilungs-Erkenntnis aus
  Lesson #87 wird jetzt visuell direkt im Panel sichtbar.
  SI-Trend-Box bekam in PR #105 klare Labels (Trefferquote /
  Median) + Hinweistext.
- **Conviction-Score in zwei Schritten live gemacht.** Schritt A
  (PR #89) liefert Daten, Schritt B (PR #95) macht sie sichtbar.
  Drei Folge-Fixes nötig: VIX-Persistenz (PR #90), Pipeline-
  Reihenfolge (PR #96), UI-Polish (PR #97). Read-only-Diagnose
  (Daten-Pfad / Pipeline-Order) hat in zwei Fällen Fix-Pfad
  klar gemacht, bevor blind gefixt wurde.
- **Code-Hygiene Punkte 5 & 6 (Schritt 1/A) erledigt.** Score-
  Formel-Display ist auto-generiert aus config-Konstanten;
  DRIVER_CLASSIFICATIONS ist Single-Source-of-Truth für
  `_drivers_breakdown`. Schritt 5/2 und 6/B (Score() aus
  Konstanten / DRIVER_CLASSIFICATIONS ableiten) bleiben offen.
- **Methodik-Asymmetrien systematisch durchgegangen.** Vier
  Diskrepanzen Display ↔ Code identifiziert; alle vier in zwei
  PRs (#98, #99) gefixt. KI-Score-Methodik-Block in PR #107
  ergänzt, damit die vierte Bewertungs-Achse genauso erklärt wird
  wie Setup / Monster / Conviction. Kein Drift mehr zwischen
  Methodik-Sektion und Score-Pfaden.
- **Trade-Journal um Entry-Snapshot und 7-Tage-Filter erweitert.**
  Beim Position-Open werden Score-Bucket + Conviction-Level
  gespeichert; im Journal sichtbar. 7-Tage-Filter zwischen „Alle"
  und „30 Tage" für aktuelle Reflexion.
- **Watchlist-Drawer-UX repariert.** PR #106 hat `wlOpenKiAnalyse`
  von einem Main-Karten-Redirect auf inline-Analyse umgebaut —
  Top-10- und Watchlist-Pfad teilen sich jetzt den extrahierten
  Helper `_kiAnalyseFromCtx`. Bei Nicht-Top-10-Watchlist-Tickern
  Graceful-Fallback. News-Toggle wurde defensiv mit explicit-
  attribute-toggle + `scrollIntoView` verstärkt.
- **Exit-Druck endlich für jede Position sichtbar.** PR #108 zeigt
  die Composite-Pressure-Zeile jetzt immer, sobald `exit_pressure`
  vorliegt — auch bei vollständig ruhigen Triggern. Erkennbar
  „ruhig" vs „kaputt" — bei SABR (alle Trigger unter Schwelle) war
  der Block vorher unsichtbar, jetzt zeigt er „Exit-Druck: 26/100"
  + dezenter „Alle Frühwarn-Signale ruhig"-Hinweis.
- **Conviction-Push als Aktions-Signal eingeführt.** PR #109 fügt
  den neuen Anomaly-Trigger `conviction_high` ein (Threshold-
  Crossing-Logik: cur ≥ 75 UND prev < 75). prev_conviction_scores
  wird in `agent_state.json` persistiert, am Run-Ende neu
  geschrieben. PR #110 hebt das Tiering der gesamten Anomaly-
  Familie an: `conviction_high`, `perfect_storm`, `monster_backup`
  bleiben high; `rvol_explosion`, `uoa_extreme`, `score_jump`,
  `gap_combo`, `edgar_filing` werden medium. Damit ist semantisch
  klar: high = Aktions-Signal, medium = Beobachtungs-Signal.
- **Squeeze-Guardian-Konformitäts-Check zum Sessionende.** Status
  OK für alle Architektur-Invarianten (Conviction-Pipeline-Order,
  VIX-Persistenz, DRIVER_CLASSIFICATIONS-SSOT, Methodik-Sync,
  Token-Encryption, push_history-SSOT, neue
  `prev_conviction_scores`-Persistenz, geteilter
  `_kiAnalyseFromCtx`-Kern, Severity-Tiering-Konsistenz). Ein
  Doku-Drift zur Borrow-Rate-Tabelle in PR #103 sofort gefixt;
  ntfy-Priority-Mapping als bewusste, in CLAUDE.md dokumentierte
  Entscheidung erkannt — kein Bug, Backlog-Punkt.

## Wichtige Lernerfahrungen

- **Multi-Session-Arbeit am gleichen Repo nicht mehr machen.**
  Single-Session pro Tag ist die Defaultregel.
- **Sandbox-Verluste sind erwartbar.** Code-Stand IMMER über PR
  auf GitHub spiegeln — der gemergte main ist die einzige
  verlässliche Persistenz.
- **`main`-Pushes sind in der Sandbox blockiert (HTTP 403).** PR-
  only-Workflow für alle Änderungen, dokumentiert in CLAUDE.md.
- **Git-Diff vor Commit prüfen.** Verhindert versehentliches
  Mit-Committen von Sandbox-Artefakten.
- **yfinance-Default Multi-Ticker-Form ist `(Field, Ticker)`,
  nicht `(Ticker, Field)`.** Bei jedem `yf.download(tickers, …)`
  mit Liste explizit `group_by='ticker'` setzen.
- **Read-only-Diagnose vor blindem Fix lohnt sich.** Mehrfach
  bestätigt: Backtest-Backfill (PR #72), VIX-Persistenz (PR #90),
  Conviction-Pipeline-Order (PR #96), Skew-Suppression-vs-Dimming
  (PR #93), Exit-Druck-Composite-Sichtbarkeit (Diagnose →
  PR #108). Jedes Mal hat ein 5–10-min-Read-only-Check vor dem
  Fix die richtige Stelle isoliert. **Auch bei Refactors gilt:
  Read-only-Pfad-Inspektion bevor man Code bewegt** (Beispiel
  DRIVER_CLASSIFICATIONS-Schema-Konflikt-Klärung, PR #83).
- **Pipeline-Reihenfolge ist eine eigene Klasse von Bug.** Render-
  Code prüft `s["conviction"]`, das von einer separaten Funktion
  gesetzt wird. Wenn die Funktion NACH dem Render läuft, ist das
  Feld leer — kein Crash, kein Log-Eintrag, nur eine stille Lücke
  im UI. Lehre: jede neue Side-Effect-Funktion mit Stock-Dict-
  Mutation muss in der `main()`-Pipeline an der richtigen Stelle
  einsortiert werden, BEVOR der HTML-Render läuft, der die Werte
  konsumiert.
- **Squeeze-Guardian-Konformitäts-Check nach Multi-PR-Sessions ist
  kein Overhead, sondern Versicherung.** Hat am 09.05. einen
  produktiven stillen Datenverlust aufgedeckt, am 10.05. zwei
  Doku-Drifts und einen bewussten Architektur-Trade-off
  (ntfy-Priority hardcoded high) sauber benannt.
- **Backtest-Verteilungs-Erkenntnis (10.05.2026) — Median allein
  unterschätzt die Edge.** Squeeze-Renditen sind extrem
  rechtsschief; einzelne Knaller treiben den Mean weit über den
  Median, ohne dass der Median sie sieht. Score ≥ 70 / 10T-T+1:
  Median +4.1 % vs Mean +12.2 % (3× Spread). Implikation: bei
  asymmetrischer Auszahlungs-Struktur ist Mean der relevantere
  Indikator. Mean-Anzeige (PR #86) + Skew-Indikator (PR #92/#93)
  machen das jetzt direkt im Panel sichtbar.
- **Conviction-Score-Aufbau: Daten erst, UI danach.** Schritt A
  (Daten ohne UI) erlaubt Plausibilitäts-Verifikation der Werte
  bevor man die UI baut. Hat bei Conviction zwei Folge-Fixes
  (VIX-Persistenz, Pipeline-Reihenfolge) entdeckt, die ohne
  diesen Zwischenschritt erst nach UI-Deployment sichtbar
  geworden wären.
- **Frontend-Verifikation in Browser-Konsole (`fetch` +
  `console.log`) ist schnell und zuverlässig.** Mehrfach für
  Conviction-Daten-Inspection und Backtest-Bucket-Replay genutzt.
  Keine zusätzliche Tool-Installation, kein Workflow-Lauf nötig.
- **UI-Lücken kommen oft erst beim echten Nutzen ans Licht.**
  Exit-Druck-Composite-Block existierte schon seit Phase 2 Stufe
  2b-1, aber war bei ruhigen Positionen unsichtbar — User merkte
  erst bei der SABR-Position, dass nichts angezeigt wird, und
  konnte nicht zwischen „ruhig" und „kaputt" unterscheiden.
  Lehre: bei jeder neuen Daten-Pipeline-Sichtbarkeitsregel die
  Frage stellen „was sieht der User bei leerem/ruhigem Zustand?"
  und prüfen, ob das Fehlen einer Anzeige bewusst oder unbeabsichtigt
  ist.
- **Conviction-Push als Aktions-Signal vs. Anomaly-Push als
  Beobachtungs-Signal — semantische Trennung im Severity-Tiering.**
  PR #109 hat `conviction_high` als ersten echten Aktions-Push
  eingeführt. Im selben Atemzug (PR #110) wurde die Severity der
  bestehenden Anomaly-Trigger auf `medium` herabgestuft, damit
  Conviction sich klar abhebt. Lehre: bei der Einführung eines
  qualitativ neuen Signal-Typs die bestehenden Signale neu
  einordnen — sonst geht das neue Signal im Rauschen unter.

## Code-Hygiene-Backlog

Aus der Diskussion vom 09.05.2026. Punkt 1 (`_record_push`-SSOT, PR
#76), Punkt 5 Schritt 1 (Score-Formel-Box auto-generiert, PR #84) und
Punkt 6 Schritt A (DRIVER_CLASSIFICATIONS-Tabelle, PR #83) sind
erledigt. Verbleibende Punkte als Wiedervorlage.

- **Punkt 2 — v1/v2 Render-Pfad in `generate_report.py`:** vollständige
  Migration zu Jinja (Phase X). Voraussetzung für Punkt 3.
- **Punkt 3 — Monolith `generate_report.py` aufsplitten:** ~12 000 Zeilen
  in einer Datei. Hohe Risiko-Operation.
- **Punkt 4 — HTML/JS-im-f-String-Pattern durch Template-Engine
  ersetzen:** hängt mit Punkt 2 zusammen.
- **Punkt 5 — Score-Methodik-Sync-Regel strukturell absichern**
  - **Schritt 1: erledigt via PR #84 (10.05.2026)**.
  - **Schritt 2 (offen):** `score()` und `_compute_sub_scores()` aus
    denselben `SUB_*_DISPLAY_PTS_MAX`-Konstanten ableiten.
- **Punkt 6 — `_drivers_breakdown` mit `score()` zusammenziehen**
  - **Schritt A: erledigt via PR #83 (10.05.2026)**.
  - **Schritt B (offen):** `score()` und `_compute_sub_scores()` aus
    `DRIVER_CLASSIFICATIONS` ableiten lassen.

## Architektur-Anker (eingeführt/geändert in dieser Session)

- **`Conviction-Score`** (PR #89, Schritt A + PR #95, Schritt B) —
  vierte Bewertungs-Achse neben Setup/Monster/KI. Vier Komponenten:
  Setup max 33, Earliness max 28, Anomaly max 28, Regime (VIX) max 11.
  Levels: ≥ 75 high (grün), 50–74 medium (orange), < 50 low (grau).
  `compute_conviction_score(stock, anomalies_today, vix)` ist pure
  Funktion; `apply_conviction_scores` ist Side-Effect-Wrapper.
- **`apply_conviction_scores` muss VOR `generate_html` laufen** (PR #96).
  Render-Code prüft `isinstance(s["conviction"]["score"], (int, float))`
  — ohne Voraufruf wird die Conviction-Row im `_score_block_inner_html`
  übersprungen. Pipeline-Reihenfolge ist Pflicht-Invariante.
- **VIX-Persistenz via `**existing`-Spread** (PR #90) — `_write_app_data_json`
  baut payload jetzt mit `{**_existing_app_data, ...explicit}`-Spread,
  analog zu ki_agent. Bewahrt `vix_current` und alle nicht explizit
  übergebenen Keys zwischen Daily-Run-Schreibvorgängen.
- **`DRIVER_CLASSIFICATIONS` Hybrid-Schema** (PR #83) — Liste von
  Dict-Einträgen mit primitive ODER Callable-Werten für `label` und
  `weight`. Erlaubt dynamische Labels (z. B. „Short Float 23.4 %") und
  dynamische Gewichte (z. B. `min(sf/50, 1) * 32`) aus einer einzigen
  Tabelle, ohne 25 separate Helper-Funktionen.
- **Methodik-Display zeigt bedingte Boni** (PR #98 + #99) — bei jeder
  Komponente mit zusätzlichem Beschleunigungs- oder Multiplikator-
  Pfad reflektiert der Display-String alle aktivierbaren Maxima
  (z. B. „5 Pkt (7 bei Beschleunigung)" für SI-Trend, „×1.05–1.15
  (je KI-Score-Stufe)" für Agent-Boost). Pflege-Regel in CLAUDE.md
  Score-Methodik-Sync-Regel-Sektion dokumentiert.
- **Backtest-Panel: Median, Mean, Min/Max, Skew pro Bucket × Horizont**
  (PRs #81/#86/#88/#92/#93/#94). Vier Sub-Zeilen pro Horizont (M, Ø, R,
  Skew-Hinweis). Grau-Dimming bei n < `MIN_BUCKET_N` (= 20) gilt
  konsistent für alle vier. UX-Polish: kompakte Pill-Toggles statt
  breiter Buttons, neutrale Hit-Chart-Farbe (App-Lila statt Rot/Grün),
  Bucket-Cards mit Border-Top + dezent abgesetztem Hintergrund,
  Best-Median-Stern in Akzent-Lila statt Emoji-Gelb. SI-Trend-Box
  bekam in PR #105 klare Labels (Trefferquote / Median).
- **Trade-Journal Entry-Snapshot** (PR #91) — bei Position-Open werden
  vier neue Felder ins `pos`-Dict geschrieben (`entry_score`,
  `entry_score_bucket`, `entry_conviction_score`, `entry_conviction_level`).
  Beim Close 1:1 ins `closed_trades` durchgereicht; Render im Journal
  als „Score 87 (≥ 70) · Conv 76 (high)"-Zeile. Backwards-compat für
  alte Trades (`—`-Fallback).
- **`prev_conviction_scores`-Persistenz für Threshold-Crossing** (PR #109)
  — `agent_state.json["prev_conviction_scores"]` speichert pro Ticker
  den letzten Conviction-Score (Skalar, nicht Components-Dict). Wird
  am Run-Ende neu geschrieben aus `app_data["conviction_scores"]` und
  beim nächsten Tick als kwarg an `detect_anomalies` durchgereicht.
  Der `conviction_high`-Trigger feuert nur beim Threshold-Crossing
  (cur ≥ 75 ∧ prev < 75) — Sustained-High wird unterdrückt. Standard-
  Cooldown `ANOMALY_COOLDOWN_HOURS` (6 h) als zusätzliche Sicherheit
  gegen Spike-Oszillationen knapp um die Schwelle.
- **Geteilter `_kiAnalyseFromCtx`-Kern** (PR #106) — `runKiAnalyse`
  (Top-10) und `wlOpenKiAnalyse` (Watchlist-Drawer) teilen sich die
  Anthropic-API-Logik (Token-Check, hasResult-Toggle, Prompt-Bau,
  Streaming, Truncation-Hinweis, Fehler-Pfad). Top-10 liest ctx aus
  Article-`data-*`-Attributen, Watchlist liest aus
  `WL_TOP10[ticker]`/`_WL_CARDS[ticker]` und ruft denselben Helper.
  Rerun läuft pro Pfad über separaten Handler (`kaRerun(cardIdx)` vs
  `wlKaRerun(rerunBtn, ticker)`). Schema-Stabilität: bei Änderung
  der ctx-Felder beide Aufrufstellen synchron halten.
- **Severity-Tiering** (PR #110) — semantische Trennung im Anomaly-
  Push-Stream. **high (Aktions-Signal):** `conviction_high`,
  `perfect_storm`, `monster_backup`. **medium (Beobachtungs-Signal):**
  `rvol_explosion`, `uoa_extreme`, `score_jump`, `gap_combo`,
  `edgar_filing`. Severity landet in `push_history` und in der
  CLAUDE.md-Anomaly-Tabelle. **Wichtig:** `_send_anomaly_ntfy`
  sendet aktuell hardcoded `Priority: high` an ntfy, unabhängig vom
  Severity-Wert — das ist in CLAUDE.md explizit als beabsichtigt
  dokumentiert. Für ein echtes Tiering auf dem Handy wäre ein
  `severity`-Parameter in `_send_anomaly_ntfy` nötig (Backlog-Punkt).
- **Exit-Druck-Composite-Render: Composite immer zeigen** (PR #108) —
  `buildPositionStatus` rendert die „Exit-Druck: N/100"-Zeile
  jederzeit, sobald `exit_pressure` ein valider Wert ist. Trigger-
  Zeilen weiterhin nur bei warn/crit. Bei vollständig ruhiger
  Position erscheint dezent „Alle Frühwarn-Signale ruhig" (CSS
  `.ps-quiet`, italic, `--txt-dim`). Render-Bedingung: `pressureLine
  || rows.length > 0`. Damit kann der User „ruhig" von „kaputter
  Pipeline" unterscheiden.
