# Session-Handover — Stand 11.05.2026 (Ende der Tagesschicht)

## Heute implementiert (chronologisch, alle gemerged via PR)

Dreizehn PRs (#105–#117) seit dem vorletzten Handover-Update (PR #102 vom 10.05. nachmittags). Acht waren bereits in den Tagesabschluss-Updates PR #103/#111 dokumentiert; die heutigen sechs neuen Themen (#112–#117) sind unten als eigene Sub-Sektion am Ende.

### UI-Polish (späte Abend-Session 10.05.)

- `36e7e7e` — feat: SI-Trend-Vergleich-Box mit klaren Labels
  (Trefferquote / Median / Hinweistext) — PR #105
- `5af7510` — fix: Watchlist-Drawer KI-Analyse läuft inline
  (geteilter `_kiAnalyseFromCtx`-Kern), News-Toggle defensiver — PR #106
- `1da0442` — docs: KI-Score-Block in Score-Methodik-Sektion ergänzen — PR #107
- `0e55b5a` — feat: Exit-Druck-Composite-Zeile immer anzeigen — PR #108

### Conviction-Push + Severity-Tiering (späte Abend-Session 10.05.)

- `f4db74c` — feat: Conviction-basierte Push-Trigger (`conviction_high`
  mit Threshold-Crossing-Logik, `prev_conviction_scores`-Persistenz) — PR #109
- `c3d9737` — feat: Severity-Tiering — Conviction high, andere
  Anomaly-Trigger medium — PR #110
- `0245ad1` — docs: handover update after late session 2026-05-10 — PR #111

### Tagesschicht 11.05.2026 — Phase 2 Trigger 5+6 + Push-History-UI + Conviction-Gating

- `1dd2d5d` — fix: change-Feld für Watchlist-only-Tickers aus
  prev_close/price rekonstruieren (Synthetic-Add-Pfad ohne `change`
  initialisierte Frontend mit +0.0 % Momentum) — PR #112
- `166d5bf` — feat: Phase 2 Trigger 6 (trend_break) — EMA21 +
  Sub-Score scharf. EMA21 in `_compute_indicators` via
  `close.ewm(span=21, adjust=False)`, neu in `_hist_stats`-Return-
  Tuple, `_all_metrics`-Builder und Merge bei Z. ~12700. Trigger
  feuert bei Kurs unter EMA21 (50 = warn ≤3 %, 100 = crit >3 %). — PR #113
- `b4d950d` — feat: Phase 2 Stufe 3c-3 — UI Notification-History.
  Hamburger-Menü-Eintrag „Push-Historie" öffnet eigene `info-panel`-
  Sektion analog Trade-Journal (Stats / Filter nach Severity / Kind /
  Ticker / Zeitraum / Liste neueste oben). Datenfluss rein lesend
  aus `window._APP_DATA.push_history`. — PR #114
- `600006e` — feat: Anomaly-Pushes via Conviction-Mindest-Schwelle
  filtern. `ANOMALY_CONVICTION_MIN_THRESHOLD = 50`. `conviction_high`
  selbst ungefiltert. push_history bleibt befüllt (`suppressed=True` +
  `suppress_reason="conviction_below_threshold"`). UI zeigt
  unterdrückte Einträge dezent (Strike-Through-Body, ⊘-Marker). — PR #115
- `89e83fb` — feat: Phase 2 Trigger 5 (catalyst) — Earnings-Fenster
  scharf. Drei-Schichten-Helper (`_fetch_finnhub_next_earnings` →
  `_fetch_yfinance_next_earnings` → kombinierter
  `_fetch_next_earnings_date`). Forward-looking: feuert wenn nächste
  Earnings ≤ `CATALYST_DAYS_WINDOW` (2) Trading-Tage entfernt
  (50 = warn 1–2 Tage, 100 = crit am Earnings-Tag). Spec-Divergenz
  gegenüber alter Stub-Note dokumentiert. — PR #116
- `1842334` — fix: PR #116 Review-Feedback (stacked) — dead
  TypeError-branch entfernt, konkrete Exception-Typen
  (yfinance: `AttributeError/ValueError/KeyError/TypeError`;
  catalyst-Trigger: `TypeError/ValueError`), PR-Nummer in Handover
  korrigiert. — PR #117 (stacked auf PR #116)

## Aktive Positionen (im Gist `squeeze_data.json`)

- **AMC** · offen
- **SABR** · offen · läuft im Plus
- **IONQ** · offen · läuft im Plus

## Verifikation morgen früh (12.05.2026)

- **Catalyst-Trigger Live-Verifikation:** `app_data.json["positions"]["{T}"]["exit_state"]["triggers"]["catalyst"]`
  zeigt für jede offene Position entweder `available=true` mit
  `score=0/50/100` (Earnings-Datum ≤ 2 Trading-Tage → warn/crit;
  >2 Tage → score 0) ODER `available=false` (kein Earnings-Datum
  gefunden) — niemals mehr die alte Stub-Note „kein historischer
  Earnings-Lookup". Stichprobe AMC/SABR/IONQ.
- **FINNHUB_API_KEY-Workflow-Secret prüfen:** Falls in
  `Settings → Secrets and variables → Actions` noch nicht
  vorhanden, eintragen. Ohne Key fällt der Catalyst-Trigger
  ausschließlich auf yfinance zurück (deutlich rate-limit-anfällig
  bei vielen Positionen).
- **Conviction-Formel Tag 2:** heutige Top-10 hatten Conviction
  max ≈ 61 (medium). Ist morgen mindestens ein Setup ≥ 75
  (high-Stufe, grün) erreichbar, oder bleibt die Spitze
  systematisch im medium-Bereich? Daten für 5-Tage-Beobachtung
  sammeln (siehe Wiedervorlage 12.–16.05.).
- **`conviction_high`-Push-Verifikation:** falls ein Setup heute
  bei < 75 stand und morgen ≥ 75 erreicht → erster Hourly-Tick
  feuert „🎯 KAUFSIGNAL …" (severity high, ungefiltert vom
  Conviction-Gating). `agent_state.json["prev_conviction_scores"]`
  zeigt heute-Werte.
- **Push-Suppression-Live-Verifikation:** Sub-50-Conviction-
  Ticker mit aktivem `score_jump` / `rvol_explosion` zeigen in
  der neuen Push-Historie-UI (Hamburger → Push-Historie) eine
  unterdrückte Zeile (`suppressed=true`, Body strike-through,
  ⊘-Marker, gestrichelter Rand) statt eines echten ntfy-Pushes.

## Geplante Aufgaben + Wiedervorlagen

### Offene Aufgaben (kein Termin — nach Priorität)

1. **Phase 2 Trigger 4 (setup_erosion)** — letztes verbleibendes
   Stub im Sechs-Trigger-Framework. Braucht Entry-Snapshot
   (`dtc`/`short_float`/`cost_to_borrow`) am Position-Open-Form
   im Gist, plus Read-Pfad in `_compute_exit_state`. Mittlerer
   Aufwand wegen Schema-Erweiterung + UX-Touch.
2. **Methodik-Asymmetrien Schritt 3** — Konstanten-Extraktion:
   Late-Runner-Penalty- und FINRA-Acceleration-Bonus-Konstanten
   aus `generate_report.py` (`apply_late_runner_penalty`,
   `score_bonus`) in `config.py` rausziehen. Display-Werte werden
   seit PR #99 schon aus `config.py` gelesen — Code-Pfade noch
   nicht. Reine Refactor-PR, kein Verhaltens-Diff.
3. **Methodik-Display-Standardwert-Frage (Doku):** zeigt die
   Methodik-Sektion Standard- oder Maximal-Werte? Anlass:
   `SUB_SI_TREND_DISPLAY_PTS_MAX = 5` vs
   `FINRA_ACCELERATION_BONUS = 7` (bei Beschleunigung). Drei
   Optionen — eigene Session, kein Code-Eilauftrag:
   - **(A)** `SUB_*_DISPLAY_PTS_MAX` auf Maximal-Werte
     erhöhen (Methodik zeigt Worst-Case-Punkte).
   - **(B)** Display um „(N bei Beschleunigung)"-Hinweise
     ergänzen (Standard- und Bonus-Wert sichtbar).
   - **(C)** Status quo (Standard-Werte, Bonus implizit).
4. **Stufe Mittel-2 (Earliness aktiv schalten)** — Score-Effekt
   für Earliness scharfschalten NACH 1–2 Daily-Runs mit
   gefüllter PM-Vol-Komponente. Heute war Earliness in 9/10
   Top-10 = 0 (alle „heißgelaufen").
5. **Backtest-T+0/T+1-Auswertung** — Frontend-Verifikation
   läuft weiter; je Score-Bucket sollten 30+ Tage Live-R-Werte
   für belastbare Mediane vorliegen.
6. **Big-Refactor Zwei-Achsen-Ranking** — nach 30+ Tagen
   Earliness-Daten.
7. **Score-Aufschlüsselung pro Karte** (Phase Y) — eigene
   Detail-Ansicht der Setup-Score-Komponenten pro Stock.
8. **Immediacy-Score-Feature** — orthogonale Achse zu
   Setup/Conviction.
9. **Bahn A2** — Frontend-Auswertungs-Panel (≥ 200 Live-
   Backtest-Einträge erforderlich).
10. **UX Backtesting „Nur Live"-Modus** — Toggle, der
    Bootstrap-Einträge ausblendet.
11. **Phase X — v1-Pfad-Migration** (siehe Code-Hygiene Punkt 2).
12. **Tier-2-Insight-Builder** als Reserve.
13. **ntfy-Priority-Mapping nach Severity** — `_send_anomaly_ntfy`
    sendet aktuell hardcoded `Priority: high`. Wenn das Tiering
    auch auf dem Handy sichtbar werden soll: `severity` an ntfy
    durchreichen.

### Wiedervorlagen mit Termin

- ⏰ **12.05.2026 (Daily-Run-Verifikation)** — Catalyst-Trigger
  + Push-Suppression + Push-Historie-UI (siehe Sektion
  „Verifikation morgen früh").
- ⏰ **12.–16.05.2026 (Conviction-Formel-Beobachtung Tag 2–5)** —
  datenabhängig, kein Code-Job. Falls high-Stufe (≥ 75) über
  fünf Trading-Tage nie erreicht wird, **Conviction-Formel-Re-
  Distribution erwägen:** Setup 33 → 40, Earliness 28 → 14,
  Anomaly 28 → 28, Regime 11 → 18. Entscheidung in eigener
  Session, nicht eilig.
- ⏰ **15.05.2026 — Phase 3 Exit-Signale prüfen** —
  **EIGENSTÄNDIGES Thema, NICHT identisch mit Phase 2 Trigger-
  Framework.** Geplant: IV-basierte Exit-Trigger (Blow-off-Top
  + IV-Crush). Phase 3 wurde noch nicht begonnen.
- ⏰ **19.05.2026** — `app_data`-Recovery-Logik bei nächstem
  Gist-Hiccup verifizieren, dann `POSITIONS_JSON`-Secret löschen.
- ⏰ **02.06.2026** — Chart-Indikatoren prüfen (EMA21 — heute
  via PR #113 schon im Datenmodell — plus VWAP-Position und
  Bollinger-Band-Squeeze als Frontend-Visualisierung).
- ⏰ **02.07.2026** — Premium-Daten-Stack prüfen
  (Polygon/Alpaca/IEX-Anbindung als Backup zu Yahoo/Finviz).

## Strategische Roadmap

### Übergeordnetes Ziel

Squeeze-Früherkennungssystem mit empirisch validierter Edge.
Drei parallele Arbeitsstränge laufen permanent nebeneinander:

- **Bauen** — Code-Erweiterungen (neue Trigger, UI-Ergänzungen,
  Persistenz-Schichten). Aktuell: Phase 2 Trigger 4
  (setup_erosion), Phase 3 Exit-Signale (IV-basiert), Code-
  Hygiene-Backlog Punkte 5/2 + 6/B.
- **Sammeln** — passives Warten auf Backtest-, Earliness- und
  Conviction-Empirik (jeder Daily-Run + ki_agent-Tick füttert
  die History). Aktuell: Conviction-Formel-Verifikation Tag 2–5,
  Setup-Verfall-Symmetrie-Beobachtung, Backtest-Mean-vs-Median-
  Drift.
- **Validieren** — Score-Logik gegen reale R-Werte testen,
  sobald genug Datenpunkte da sind. Aktuell: Daily-Run-Checks
  (Trigger-Verfügbarkeit, Push-Filter-Wirkung), Position-
  Verläufe (AMC/SABR/IONQ), Methodik-Konsistenz-Pflege
  (Score-Methodik-Sync-Regel).

### Drei Zeit-Achsen

**Kurzfristig (Tage bis 1–2 Wochen, aktiv planbar)**

- **Conviction-Score Stage 2** — Plausibilitäts-Beobachtung
  über Trading-Woche; ggf. Komponenten-Gewichte rekalibrieren
  wenn Earliness systematisch 0 bleibt (siehe Wiedervorlage
  12.–16.05.).
- **Conviction-Push-Verifikation** — feuert `conviction_high`
  bei einem Setup, das tatsächlich die 75-Schwelle erreicht?
- **Stufe Mittel-2** — Earliness-Score-Effekt scharfschalten,
  sobald 1–2 Daily-Runs mit drei Komponenten plausible Werte
  zeigen.
- **Phase 3 Exit-Signale** (Wiedervorlage 15.05.2026).
- **Phase 2 Trigger 4 (setup_erosion)** — letztes verbleibendes
  Stub.

**Mittelfristig (Wochen, datenabhängig)**

- **Backtest-Validierung** — Frontend-Auswertung Backtest-T+0/T+1
  funktioniert erst belastbar, sobald je Score-Bucket
  (`<50`/`50–69`/`≥70`) mindestens 30 Tage Live-R-Werte
  vorliegen. Mean-vs-Median-Skew (PR #92/#93) gibt schon heute
  hilfreiche Hinweise auf rechtsschiefe Squeeze-Knaller.
- **Bahn A2** — Frontend-Auswertungs-Panel (≥ 200 Live-Backtest-
  Einträge erforderlich).
- **ntfy-Priority-Mapping nach Severity** — sobald sich das
  Tiering als sinnvoll bestätigt, ntfy-Priority an `severity`
  koppeln.

**Längerfristig (Monate, Empirik-basiert)**

- **Big-Refactor Zwei-Achsen-Ranking** — nach 30+ Tagen
  Earliness-Daten.
- **Premium-Daten-Stack** (Wiedervorlage 02.07.2026).
- **Sektor-Rotation / Marktkontext** — noch nicht im Backlog.

### Lackmus-Test

**Phase 3 Validieren ist der entscheidende Test.** Backtest muss
zeigen: Score ≥ 70 hat einen klar besseren Median-R-Wert nach 5T
als Score < 50.

- **Wenn ja** → Earliness-Score-Aktivierung und Big-Refactor mit
  Rückenwind.
- **Wenn nein** → Score-Komponenten **neu kalibrieren bevor
  weiter gebaut wird**.

Bis der Test laufen kann, ist passives Sammeln der primäre Modus.
Conviction-Score (PR #89/#95) liefert die Aktions-Frage als
zusätzlichen Indikator, ohne die Score-Logik selbst zu verändern —
ein „nur unterstützender" Baustein im Sinne der Roadmap. Der
`conviction_high`-Push (PR #109) macht die Aktions-Achse jetzt
auch außerhalb des Frontends sichtbar; das Severity-Tiering
(PR #110) plus Conviction-Gating (PR #115) trennen Aktions-
Signale von Beobachtungs-Signalen im Push-Stream sauber. Trigger
5 (catalyst, PR #116) und Trigger 6 (trend_break, PR #113) sind
live — nur Trigger 4 (setup_erosion) als letztes Stub im
Phase-2-Exit-Framework offen.

## Code-Hygiene-Backlog

Aus der Diskussion vom 09.05.2026. Status zum 11.05. abends:

- **Punkt 1 — `_record_push`-SSOT** — erledigt via PR #76.
- **Punkt 2 — v1/v2 Render-Pfad in `generate_report.py`:** offen.
  Vollständige Migration zu Jinja (Phase X). Voraussetzung für
  Punkt 3.
- **Punkt 3 — Monolith `generate_report.py` aufsplitten:** offen.
  ~13 000 Zeilen in einer Datei. Hohe Risiko-Operation.
- **Punkt 4 — HTML/JS-im-f-String-Pattern durch Template-Engine
  ersetzen:** offen. Hängt mit Punkt 2 zusammen.
- **Punkt 5 — Score-Methodik-Sync-Regel strukturell absichern**
  - **Schritt 1: erledigt via PR #84 (10.05.2026)**.
  - **Schritt 2 (offen):** `score()` und `_compute_sub_scores()`
    aus denselben `SUB_*_DISPLAY_PTS_MAX`-Konstanten ableiten.
- **Punkt 6 — `_drivers_breakdown` mit `score()` zusammenziehen**
  - **Schritt A: erledigt via PR #83 (10.05.2026)**.
  - **Schritt B (offen):** `score()` und `_compute_sub_scores()`
    aus `DRIVER_CLASSIFICATIONS` ableiten lassen.

## Architektur-Anker (kumuliert + heutige Erweiterungen)

- **`Conviction-Score`** (PR #89, Schritt A + PR #95, Schritt B) —
  vierte Bewertungs-Achse neben Setup/Monster/KI. Vier
  Komponenten: Setup max 33, Earliness max 28, Anomaly max 28,
  Regime (VIX) max 11. Levels: ≥ 75 high (grün), 50–74 medium
  (orange), < 50 low (grau). `compute_conviction_score(stock,
  anomalies_today, vix)` ist pure Funktion;
  `apply_conviction_scores` ist Side-Effect-Wrapper. MUSS VOR
  `generate_html` laufen (PR #96).
- **VIX-Persistenz via `**existing`-Spread** (PR #90) —
  `_write_app_data_json` baut payload jetzt mit
  `{**_existing_app_data, ...explicit}`-Spread.
- **`DRIVER_CLASSIFICATIONS` Hybrid-Schema** (PR #83) — Liste von
  Dict-Einträgen mit primitive ODER Callable-Werten für `label`
  und `weight`.
- **Methodik-Display zeigt bedingte Boni** (PR #98 + #99) — bei
  jeder Komponente mit zusätzlichem Beschleunigungs- oder
  Multiplikator-Pfad reflektiert der Display-String alle
  aktivierbaren Maxima. Pflege-Regel in CLAUDE.md Score-
  Methodik-Sync-Regel-Sektion dokumentiert.
- **Backtest-Panel: Median, Mean, Min/Max, Skew pro Bucket ×
  Horizont** (PRs #81/#86/#88/#92/#93/#94/#105). Vier Sub-Zeilen
  pro Horizont + SI-Trend-Box mit klaren Labels.
- **Trade-Journal Entry-Snapshot** (PR #91) — vier neue Felder
  (`entry_score`, `entry_score_bucket`, `entry_conviction_score`,
  `entry_conviction_level`) beim Position-Open.
- **`prev_conviction_scores`-Persistenz** (PR #109) —
  `agent_state.json["prev_conviction_scores"]` speichert pro
  Ticker den letzten Conviction-Score. `conviction_high` feuert
  nur beim Threshold-Crossing (cur ≥ 75 ∧ prev < 75) —
  Sustained-High unterdrückt.
- **Geteilter `_kiAnalyseFromCtx`-Kern** (PR #106) —
  `runKiAnalyse` (Top-10) und `wlOpenKiAnalyse` (Watchlist-
  Drawer) teilen sich die Anthropic-API-Logik.
- **Severity-Tiering** (PR #110) — semantische Trennung im
  Anomaly-Push-Stream. **high (Aktions-Signal):**
  `conviction_high`, `perfect_storm`, `monster_backup`.
  **medium (Beobachtungs-Signal):** `rvol_explosion`,
  `uoa_extreme`, `score_jump`, `gap_combo`, `edgar_filing`.
- **Exit-Druck-Composite-Render** (PR #108) — Composite-Zeile
  wird immer gezeigt, sobald `exit_pressure` valider Wert ist;
  „ruhig"-Hinweis bei fehlenden Warn-/Crit-Triggern.
- **`change`-Fallback für Watchlist-only-Tickers** (PR #112) —
  in `get_yfinance_batch` wird `change` aus `prev_close`/
  `cur_close` rekonstruiert, wenn nicht vom Screener gesetzt.
  Top-10-`change`-Werte aus `regularMarketChangePercent` werden
  nicht überschrieben.
- **Phase 2 Exit-State — fünf von sechs Trigger live**
  (PRs #113/#115/#116/#117). Aktueller Stand:
  - `score_decay` (30 %) — live
  - `profit_lock` (25 %) — live
  - `overheated` (20 %) — live
  - **`setup_erosion` (15 %) — STUB** (verbleibendes offenes
    Stück, Schema-Erweiterung am Gist nötig)
  - `catalyst` (5 %) — **live seit PR #116** (forward-looking
    Earnings-Lookup, Finnhub primary + yfinance fallback,
    `CATALYST_DAYS_WINDOW = 2` neue Konstante in `config.py`).
    Schwellen: days_until = 0 → crit (100), 0 < days ≤ 2 → warn
    (50), > 2 → kein Trigger. `_fetch_next_earnings_date(ticker,
    today)` ist Single-Source-of-Truth.
  - `trend_break` (5 %) — **live seit PR #113** (EMA21 in
    `_compute_indicators` via `close.ewm(span=21,
    adjust=False)`, durchgereicht via `_all_metrics`).
    Schwellen: price ≥ ma21 → 0, 0 < drop ≤
    `EXIT_TREND_BREAK_CRIT_PCT` (3 %) → 50/warn, drop > 3 % →
    100/crit.
- **`CATALYST_DAYS_WINDOW = 2`** (PR #116) — Konstante in
  `config.py` Phase-2-Trigger-Sektion. Forward-looking Earnings-
  Fenster für Trigger 5.
- **Conviction-Gating für Anomaly-Pushes** (PR #115) — neuer
  Filter zwischen Beobachtungs- und Aktions-Triggern.
  `ANOMALY_CONVICTION_MIN_THRESHOLD = 50` filtert alle Anomaly-
  Trigger AUSSER `conviction_high` (das ist selbst der Aktions-
  Push). Reihenfolge: `vix_pause → silence_filter → cooldown →
  conviction_gate → push`. push_history wird IMMER geschrieben,
  bei unterdrücktem Push mit `suppressed=True` +
  `suppress_reason="conviction_below_threshold"`. Ticker ohne
  Conviction-Score pushen konservativ ungefiltert.
- **`push_history`-Schema-Erweiterung** (PR #115) — neue
  optionale Felder `suppressed: bool` und `suppress_reason:
  str | None`. Backward-kompatibel (Default `False`/`None`).
- **Push-Historie-UI** (PR #114) — Hamburger-Menü-Eintrag
  „Push-Historie" öffnet `info-panel`-Sektion analog Trade-
  Journal. Stats (komplette Historie) + Filter (Zeitraum /
  Severity / Kind / Ticker) + Liste (neueste oben, ⊘-Marker
  für suppressed-Einträge).

## Wichtige Lernerfahrungen

### Aus dieser Tagesschicht (11.05.)

- **Anomaly-Push-Inflation vermeiden durch Conviction-Gating
  (PR #115).** Beobachtungs-Trigger (Anomalien werden detektiert
  und in `push_history` geloggt) und Aktions-Trigger
  (Push-Alert geht raus aufs Handy) sind jetzt sauber getrennt.
  Conviction-Gating filtert nur jene Anomalien zum Push durch,
  deren Conviction-Score eine Schwelle überschreitet. Vermeidet
  Push-Fatigue bei Marginal-Signalen, ohne die Detection-
  Pipeline einzuschränken. UI zeigt unterdrückte Einträge
  weiterhin transparent in der Push-Historie.
- **Sandbox-Force-Push-Limit (heute PR #117 als Stacked-Fix
  notwendig).** Force-Push auf bestehende Feature-Branches mit
  Nicht-`claude/`-Prefix schlägt mit HTTP 403 fehl — auch
  reguläre fast-forward Pushes scheitern nach dem initialen
  Push. `claude/`-Prefix-Branches lassen sich neu erstellen.
  Workaround: Stacked-PR (`claude/...-review-fix` mit
  `base=Feature-Branch`). Beim Merge wandert das Fix-Commit
  in den Original-PR. Beispiel PR #117 → PR #116.
- **Spec-Divergenzen gehören in CLAUDE.md (PR #116 Catalyst).**
  Stub-Note war historisch backward-looking („Earnings ohne
  Reaktion zwischen Entry und heute"), implementiert wurde aber
  forward-looking („Earnings ≤ 2 Trading-Tage ahead"). Diese
  bewusste Entscheidung ist in CLAUDE.md dokumentiert, damit
  zukünftige Sessions sie als Architektur-Entscheidung und
  nicht als Bug interpretieren. Backward-Variante kann später
  als separater Trigger nachgereicht werden, ohne den forward-
  Trigger zu ersetzen.
- **Conviction-Formel-Erkenntnis Tag 1.** Earliness-Komponente
  ist bei Top-10-Setups systematisch 0 (9/10 Top-10 hatten
  RSI > 60 oder change_5d ≥ 5 %, also „heißgelaufen"). Folge:
  high-Stufe (≥ 75) wird kaum erreicht. 3–5 Tage beobachten
  vor möglicher Re-Distribution; Tendenz: Earliness-Cap
  reduzieren, Regime hochziehen.
- **Read-only-Diagnose vor Code-Fix (PR #112).** Vor dem
  change-Feld-Fix Diagnose ohne Code-Änderung: Synthetic-Add-
  Pfad bei Z. 12394 inicialisiert nicht — Top-10-Pfad setzt
  `change` aus `regularMarketChangePercent`. Diagnose hat
  den Fix sofort auf zwei minimale additive Stellen
  fokussiert (`get_yfinance_batch` post-loop + Merge-
  Conditional bei Z. ~12700) statt blind die Pipeline neu
  zu verdrahten.

### Aus vorherigen Sessions (kumuliert, beibehalten)

- **Multi-Session-Arbeit am gleichen Repo vermeiden** —
  Single-Session pro Tag als Defaultregel.
- **Sandbox-Verluste sind erwartbar.** Code-Stand IMMER über
  PR auf GitHub spiegeln — der gemergte main ist die einzige
  verlässliche Persistenz.
- **`main`-Pushes sind blockiert (HTTP 403)** — PR-only-Workflow
  für alle Änderungen.
- **yfinance-Default Multi-Ticker-Form ist `(Field, Ticker)`,
  nicht `(Ticker, Field)`** — bei jedem
  `yf.download(tickers, …)` mit Liste explizit
  `group_by='ticker'` setzen.
- **Pipeline-Reihenfolge ist eine eigene Klasse von Bug.**
  Jede neue Side-Effect-Funktion mit Stock-Dict-Mutation muss
  in der `main()`-Pipeline an der richtigen Stelle einsortiert
  werden, BEVOR der HTML-Render läuft, der die Werte
  konsumiert (Beispiel `apply_conviction_scores`, PR #96).
- **Squeeze-Guardian-Konformitäts-Check nach Multi-PR-Sessions
  ist kein Overhead, sondern Versicherung.**
- **Backtest-Verteilungs-Erkenntnis (10.05.2026) — Median allein
  unterschätzt die Edge.** Squeeze-Renditen sind extrem
  rechtsschief; einzelne Knaller treiben den Mean weit über
  den Median. Mean-Anzeige + Skew-Indikator machen das im
  Panel sichtbar.
- **Conviction-Score-Aufbau: Daten erst, UI danach.** Schritt A
  (Daten ohne UI) erlaubt Plausibilitäts-Verifikation der
  Werte bevor man die UI baut.
- **Frontend-Verifikation in Browser-Konsole (`fetch` +
  `console.log`)** ist schnell und zuverlässig.
- **UI-Lücken kommen oft erst beim echten Nutzen ans Licht.**
  Bei jeder neuen Daten-Pipeline-Sichtbarkeitsregel die Frage
  stellen: „was sieht der User bei leerem/ruhigem Zustand?".
- **Conviction-Push als Aktions-Signal vs. Anomaly-Push als
  Beobachtungs-Signal — semantische Trennung im Severity-
  Tiering (PR #109/#110).** Bei der Einführung eines qualitativ
  neuen Signal-Typs die bestehenden Signale neu einordnen —
  sonst geht das neue Signal im Rauschen unter. PR #115
  vertieft diese Trennung mit dem Conviction-Gating.
