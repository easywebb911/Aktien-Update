# Session-Handover — Stand 12.05.2026 (Ende der Tagesschicht)

## Heute implementiert (chronologisch, alle gemerged via PR)

Acht PRs (#119–#126) seit dem letzten Handover-Update vom Ende 11.05.
Tagesthemen: Score-Inflation-Diagnose + Persistenz, Phase 2 Trigger-
Framework komplett, Chat-/Watchlist-Stale-Data-Fixes, Push-Inflation-
Reduktion, Zwei-Run-Architektur, Token-Reentry-Hardening.

| # | Hash (commit) | Merge | Beschreibung |
|---|---|---|---|
| **#119** | `5bd7548` | `0f791f1` | **fix: score_history-Pruning auf datetime.date umstellen** — lexikographischer String-Vergleich auf `DD.MM.YYYY` parsed seit ~01.05. ALLE Mai-Einträge weg (Mai schmolz täglich um eine April-Front statt anzuwachsen). Neuer Helper `_parse_de_date` als SSOT. Smoothing, Trend-Bonus, Sparkline-Tooltips, Score-Sprung-Anomaly wieder funktional. |
| **#120** | `d87bfcd` | `b49072a` | **feat: score_inflation_log.jsonl** — append-only Persistenz für Sub-Score-Diagnose (struct/catalyst/timing + drivers_raw + trading_session_phase). 30-Tage-Cutoff via `datetime.fromisoformat`. Eigenes Modul `score_inflation_log.py` analog `push_history.py`. DST-aware Phase-Mapping. |
| **#121** | `3e07f89` | `234e05b` | **feat: Phase 2 Trigger 4 (setup_erosion)** — letzter Stub im Sechs-Trigger-Framework live. Drei relative Drops (dtc/sf/ctb) gegen `SETUP_EROSION_WARN_THRESHOLD=0.30` / `CRIT=0.50`, Combo-Bonus bei ≥ 2 Drivers. Entry-Snapshot-Schema-Erweiterung im Gist. Bestandspositionen ohne Snapshot → `available=False` (graceful). **Phase 2 jetzt vollständig (alle sechs Trigger live).** |
| **#122** | `ff6f9a2` | `c57cff8` | **fix: Chat-Synthese liest watchlist_cards als Fallback** — Out-of-Top-10-Positionen (SABR/DMRC/IONQ) bekommen Live-Preise aus `_WL_CARDS`. Neues Feld `in_watchlist_card` für LLM-Disambiguierung. System-Prompt instruiert explizit zwischen „Kurs da via Watchlist" und „Kurs fehlt komplett". |
| **#123** | `7d3114d` | `d2a7b71` | **feat: Push-Inflation-Reduktion** — `ANOMALY_CONVICTION_MIN_THRESHOLD` 50 → 75, gilt explizit auch für `monster_backup` (bewusste Architektur-Entscheidung: bei Conviction <75 ist kein „extremer Fall"). `EARNINGS_IMMEDIATE_COOLDOWN_HOURS=24` mit Per-Event-Dedup-Key `earnings_immediate_{ticker}_{date}`. `conviction_score` als Feld in `push_history`. |
| **#124** | `c1678af` | `78aa1bb` | **feat: Zwei-Run-Architektur** — 10:00-UTC-Cron schreibt `run_phase=premarket` (Vorschau, RVOL strukturell unter-skaliert), neuer 21:00-UTC-Cron `run_phase=postclose` (EOD-Wahrheit). Anomaly-Pushes nur in premarket, Backtest-History nur in postclose. Frontend-Pill gelb/grün. ki_agent gating-t Anomaly-Loop am `run_phase`. |
| **#125** | `f7823af` | `4bae2b1` | **fix: Token-Reentry Phase 1** — 401/403-Soft-Reset mit Counter (`TOKEN_AUTH_FAIL_HARD_THRESHOLD=3`); transiente Fails löschen nur Session+Memory, Hard-Reset erst nach 3 aufeinanderfolgenden Fails. iCloud-Schlüsselbund-Integration (`<form>`-Wrapper, autocomplete-Hints, hidden username-Input). Keep-Alive-Touch in `getToken()` resettet ITP-Counter. |
| **#126** | `0edb18d` | `399a2f9` | **fix: Watchlist-Drawer Stale-Data Phase 1** — `dataset.loaded`-Cache-Gate in `wlExpand` entfernt (Drawer rendert bei jedem Open neu), `_WL_CARDS`-Re-Assign nach ki_agent-Trigger-Success. `data-loaded`-Marker bleibt für Stufe 2c (auto-Re-Render offener Drawer). |

## Aktive Positionen (im Gist `squeeze_data.json`)

- **AMC** · offen
- **SABR** · offen
- **IONQ** · offen
- **DMRC** · offen (eröffnet 11.05.)

## Verifikation morgen früh (13.05.2026)

- **Erster echter Post-Close-Run heute 21:00 UTC** → Frontend-Pill
  muss bei Reload grün/„Post-Close" zeigen statt gelb. Banner-Wechsel
  ist visueller Pflicht-Check für die Zwei-Run-Architektur.
- **`score_inflation_log.jsonl`** muss erste Einträge aus dem
  21:00-Run haben: `wc -l score_inflation_log.jsonl` ≥ 10 (=Top-10),
  `head -1 score_inflation_log.jsonl | jq` zeigt
  `"run_phase":"postclose"` + valides Schema.
- **`score_history.json`** muss 13.05.-Einträge **ANHÄNGEN** (nicht
  mehr droppen). Verifikation: `git show <next-daily>:score_history.json
  | python -c '…'` zählt Mai-Datums-Histogramm. Post-PR#119 müssen
  `12.05.` und `13.05.` beide auftauchen, April-Front darf kein
  Wachstum mehr zeigen. **Smoothing/Trend-Bonus damit wieder aktiv.**
- **Push-Volumen**-Tracking: zwischen heute Abend (PR #123-Wirkung)
  und morgen Abend sollte sich von ~10/Tag auf ~2–3/Tag reduzieren.
  NVAX/GRPN-Spam war primär monster_backup unter Conviction 75 →
  jetzt suppressed. Earnings-Sofort-Alerts pro Event nur 1× (statt
  3× wie bei DMRC am 11./12.).
- **iPhone-Token-UX:** beim ersten Unlock-Modal nach Merge muss
  Safari/iCloud-Schlüsselbund „Passwort speichern" anbieten
  (Form-Wrap + autocomplete-Hints sind drin). Zweiter Tab oder
  Reload → Auto-Fill bietet Master-Passwort an.
- **Watchlist-Drawer Stale-Data:** Drawer für AMC öffnen → Werte
  notieren → ki_agent-Trigger anstoßen → Drawer schließen + neu
  öffnen → Werte müssen sich verändert haben (vor Fix: eingefroren).
- **`conviction_high`-Push:** falls morgen ein Setup bei < 75 stand
  und auf ≥ 75 springt → Hourly-Tick muss den Crossing-Push feuern.
  prev_conviction_scores ist persistiert.

## Geplante Aufgaben + Wiedervorlagen

### Offene Aufgaben (kein Termin — nach Priorität)

1. **Conviction-Formel-Re-Distribution** falls high-Stufe (≥ 75) nach
   5 Trading-Tagen Beobachtung (Wiedervorlage 12.–16.05.) **nie**
   erreicht wird: Setup 33 → 40, Earliness 28 → 14, Anomaly 28 → 28,
   Regime 11 → 18. Tendenz aus heutiger Beobachtung: Earliness-Cap
   reduzieren wegen systematischer 0-Werte bei heißgelaufenen Setups.
2. **Score-Inflation-Schwellen-Anpassung** nach 3–5 Tagen
   `score_inflation_log`-Empirik. Vergleich premarket vs. postclose
   für identische Ticker. Option A: rel_volume-Zeitnormierung
   (chirurgisch). Option B: Anomaly-Schwellen für premarket abdämpfen.
   Option C: Status quo, Zwei-Run-Architektur reicht als
   strukturelle Lösung.
3. **Token-Reentry Phase 2** — PWA-Manifest hinzufügen (F3) und/oder
   IndexedDB-Migration für Encrypted-Blob (F4). Nur falls Phase 1
   (Soft-Reset + iCloud-Schlüsselbund + Keep-Alive) nach 1–2 Wochen
   nicht ausreicht.
4. **Watchlist-Drawer Phase 2** — Stufe 2c: `renderAgentSignals`-
   Selektor auf `.wl-card[data-ticker]` erweitern, sodass auch offene
   Drawer-Subbäume Live-Updates bekommen statt nur invalidiert zu
   werden für nächsten Open. Nur falls Phase 1 (Cache-Gate weg +
   `_WL_CARDS`-Re-Assign) nicht reicht.
5. **Methodik-Display-Standardwert-Frage (Doku)** — zeigt die
   Methodik-Sektion Standard- oder Maximal-Werte? Anlass:
   `SUB_SI_TREND_DISPLAY_PTS_MAX=5` vs `FINRA_ACCELERATION_BONUS=7`
   (bei Beschleunigung). Drei Optionen — eigene Session, kein
   Code-Eilauftrag:
   - **(A)** `SUB_*_DISPLAY_PTS_MAX` auf Maximal-Werte erhöhen
   - **(B)** Display um „(N bei Beschleunigung)"-Hinweise ergänzen
   - **(C)** Status quo
6. **Stufe Mittel-2 (Earliness aktiv schalten)** — Score-Effekt für
   `earliness_pts` scharfschalten NACH 1–2 Daily-Runs mit gefüllter
   PM-Vol-Komponente. Heute war Earliness in 9/10 Top-10 = 0.
7. **Backtest-T+0/T+1-Auswertung** — Frontend-Verifikation läuft
   weiter; je Score-Bucket sollten 30+ Tage Live-R-Werte für
   belastbare Mediane vorliegen.
8. **Big-Refactor Zwei-Achsen-Ranking** — nach 30+ Tagen
   Earliness-Daten.
9. **Score-Aufschlüsselung pro Karte** (Phase Y) — eigene
   Detail-Ansicht der Setup-Score-Komponenten pro Stock.
10. **Immediacy-Score-Feature** — orthogonale Achse zu
    Setup/Conviction.
11. **Bahn A2** — Frontend-Auswertungs-Panel (≥ 200 Live-Backtest-
    Einträge erforderlich).
12. **UX Backtesting „Nur Live"-Modus** — Toggle, der Bootstrap-
    Einträge ausblendet.
13. **Phase X — v1-Pfad-Migration** (siehe Code-Hygiene Punkt 2).
14. **ntfy-Priority-Mapping nach Severity** — Lücke nur bei
    `_send_anomaly_ntfy` (hardcoded `Priority: high`). Exit-P2-Sender
    macht das Mapping bereits korrekt.

### Wiedervorlagen mit Termin

- ⏰ **13.05.2026 (Daily-Run-Verifikation)** — alle heutigen Merges
  in der Praxis prüfen (siehe Sektion „Verifikation morgen früh").
- ⏰ **13.–17.05.2026 (Empirik-Sammelphase)** — score_inflation_log-
  Tag-1-bis-5 Daten, Push-Volumen-Tracking pre/post Conviction-75,
  Conviction-Formel-Tag-2-bis-6 (kommt aus Wiedervorlage seit 12.05.,
  Spitze sollte mind. 1× ≥ 75 erreichen, sonst Re-Distribution).
- ⏰ **15.05.2026 — Phase 3 Exit-Signale prüfen** — EIGENSTÄNDIGES
  Thema, NICHT identisch mit Phase-2-Trigger-Framework. Geplant:
  IV-basierte Exit-Trigger (Blow-off-Top + IV-Crush). Phase 3 wurde
  noch nicht begonnen.
- ⏰ **19.05.2026** — `app_data`-Recovery-Logik beim nächsten
  Gist-Hiccup verifizieren, dann `POSITIONS_JSON`-Secret löschen.
- ⏰ **02.06.2026** — Chart-Indikatoren prüfen (EMA21 — heute via
  PR #113 schon im Datenmodell — plus VWAP-Position und
  Bollinger-Band-Squeeze als Frontend-Visualisierung).
- ⏰ **02.07.2026** — Premium-Daten-Stack prüfen
  (Polygon/Alpaca/IEX als Backup zu Yahoo/Finviz).

## Strategische Roadmap

### Übergeordnetes Ziel

Squeeze-Früherkennungssystem mit empirisch validierter Edge.
Drei parallele Arbeitsstränge laufen permanent nebeneinander:

- **Bauen** — Code-Erweiterungen (neue Trigger, UI-Ergänzungen,
  Persistenz-Schichten). Aktuell: Phase 3 Exit-Signale (IV-basiert,
  Wiedervorlage 15.05.), Code-Hygiene-Backlog Punkte 2/3/4/5-2/6-B,
  Token-Reentry Phase 2 falls nötig.
- **Sammeln** — passives Warten auf Backtest-, Earliness-,
  Conviction-, **Score-Inflations-** und **Push-Volumen-Empirik**
  (jeder Daily-Run + ki_agent-Tick füttert die History; ab heute
  Abend zusätzlich `score_inflation_log.jsonl` mit Sub-Score-
  Breakdown). Aktuell: Conviction-Formel-Tag-2-bis-6, Setup-Inflation-
  premarket-vs-postclose-Diff, Push-Volumen-pre/post-Conviction-75.
- **Validieren** — Score-Logik gegen reale R-Werte testen, sobald
  genug Datenpunkte da sind. Aktuell: Daily-Run-Checks (Trigger-
  Verfügbarkeit, Push-Filter-Wirkung, Stale-Data-Drawer), Position-
  Verläufe (AMC/SABR/IONQ/DMRC), Methodik-Konsistenz-Pflege.

### Drei Zeit-Achsen

**Kurzfristig (Tage bis 1–2 Wochen, aktiv planbar)**

- **Score-Inflations-Empirik** auswerten (Wiedervorlage 13.–17.05.).
  premarket-vs-postclose-Vergleich für identische Ticker, Sub-Score-
  Beitrag identifizieren. Danach Entscheidung über Schwellen-Tuning
  vs. rel_volume-Zeitnormierung.
- **Push-Volumen-Tracking** nach Conviction-75-Anhebung. Erwartung
  ~10/Tag → ~2–3/Tag. Falls noch zu laut: monster_backup-Schwelle
  90 → 95 oder Cooldown 6h → 24h.
- **Conviction-Formel-Beobachtung Tag 2–6** (Wiedervorlage
  12.–16.05.). Erreicht die Spitze regelmäßig ≥ 75? Sonst
  Re-Distribution-Vorschlag (siehe Aufgabe 1).
- **Phase 3 Exit-Signale** (Wiedervorlage 15.05.2026).
- **Stufe Mittel-2** — Earliness-Score-Effekt scharfschalten.

**Mittelfristig (Wochen, datenabhängig)**

- **Backtest-Validierung** — Frontend-Auswertung Backtest-T+0/T+1
  funktioniert erst belastbar, sobald je Score-Bucket
  (`<50`/`50–69`/`≥70`) mindestens 30 Tage Live-R-Werte vorliegen.
  Mean-vs-Median-Skew (PR #92/#93) gibt schon heute hilfreiche
  Hinweise auf rechtsschiefe Squeeze-Knaller. **Mit PR #124 fließen
  nur noch postclose-Werte in die Historie** — saubere Datenbasis.
- **Bahn A2** — Frontend-Auswertungs-Panel (≥ 200 Live-Backtest-
  Einträge erforderlich).
- **ntfy-Priority-Mapping nach Severity** — sobald sich das
  Tiering als sinnvoll bestätigt, ntfy-Priority an `severity`
  koppeln (Lücke: nur Anomaly-Sender hardcoded).

**Längerfristig (Monate, Empirik-basiert)**

- **Big-Refactor Zwei-Achsen-Ranking** — nach 30+ Tagen
  Earliness-Daten.
- **Premium-Daten-Stack** (Wiedervorlage 02.07.2026).
- **Sektor-Rotation / Marktkontext** — noch nicht im Backlog.

### Lackmus-Test

**Phase 3 Validieren ist der entscheidende Test.** Backtest muss
zeigen: Score ≥ 70 hat einen klar besseren Median-R-Wert nach 5 T
als Score < 50. Mit der Zwei-Run-Architektur (PR #124) wird die
Backtest-Historie ab heute Abend nur noch mit postclose-Werten
befüllt — vorherige premarket-Einträge bleiben unverändert, müssen
in der Auswertung über `market_regime`/`vix_level`-Filter bereinigt
werden.

- **Wenn ja** → Earliness-Score-Aktivierung und Big-Refactor mit
  Rückenwind.
- **Wenn nein** → Score-Komponenten **neu kalibrieren bevor weiter
  gebaut wird**.

Bis der Test laufen kann, ist passives Sammeln der primäre Modus.
**Mit heute Abend ist Phase 2 vollständig** (alle sechs Exit-
Trigger live) und das Push-System nach Conviction-75 streng
gefiltert — der Push-Stream zeigt jetzt fast ausschließlich
Aktions-Substrate, die Beobachtungs-Trigger sind in der UI sichtbar
ohne Handy-Lärm.

## Code-Hygiene-Backlog

Aus der Diskussion vom 09.05.2026. Status zum 12.05. abends:

- **Punkt 1 — `_record_push`-SSOT** — erledigt via PR #76.
- **Punkt 2 — v1/v2 Render-Pfad in `generate_report.py`:** offen.
  Vollständige Migration zu Jinja (Phase X). Voraussetzung für
  Punkt 3.
- **Punkt 3 — Monolith `generate_report.py` aufsplitten:** offen.
  ~14 000 Zeilen in einer Datei (heute weiter gewachsen durch
  PR #119/#120/#124/#126). Hohe Risiko-Operation.
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

### Heute neu (12.05.2026)

- **`_parse_de_date`-SSOT für DD.MM.YYYY-Cutoff-Vergleiche** (PR #119) —
  `score_history.json`-Pruning vergleicht jetzt `datetime.date`-Objekte
  statt lexikographische Strings. Linter-Pattern für künftige
  Cutoff-Stellen: `grep -n ' cutoff\|>= cutoff'` darf außerhalb von
  `_parse_de_date`-Konsumenten nicht auf DD.MM.YYYY-Strings landen.
  Smoothing, Trend-Bonus, Sparkline, Score-Sprung-Anomaly hängen alle
  am gefixten Pfad.
- **`score_inflation_log.jsonl` als Einzel-Persistenz-Modul**
  (PR #120) — append-only JSONL im Repo-Root, eigenes Modul
  `score_inflation_log.py` analog `push_history.py`-Pattern. 30-Tage-
  Cutoff via korrektem `datetime.fromisoformat`-Vergleich.
  `trading_session_phase` Wall-Clock-ET-abgeleitet, DST-aware.
  `run_phase` als zweites Phasen-Feld (Workflow-Intention vs. ET-Slot).
- **Phase 2 Exit-Framework vollständig — alle sechs Trigger live**
  (PR #121 als Abschluss):
  - `score_decay` (30 %) — live
  - `profit_lock` (25 %) — live
  - `overheated` (20 %) — live
  - `setup_erosion` (15 %) — **live seit PR #121** (`SETUP_EROSION_WARN_THRESHOLD=0.30`,
    `CRIT=0.50`, `COMBO_DRIVERS_MIN=2`, Entry-Snapshot mit `entry_dtc`/
    `entry_short_float`/`entry_cost_to_borrow`/`entry_snapshot_ts` im Gist)
  - `catalyst` (5 %) — live
  - `trend_break` (5 %) — live
- **Chat-Synthese watchlist_cards-aware** (PR #122) —
  `_build_chat_synthesis_ctx(stocks, score_history, watchlist_cards=None)`.
  Positions-Loop: `src = by_ticker.get(ticker) or wl_cards.get(ticker)`.
  Neues Feld `in_watchlist_card` flaggt den Fallback-Pfad. System-
  Prompt instruiert LLM explizit zwischen „Top-10-Kurs", „Watchlist-
  Kurs" und „Kurs fehlt komplett".
- **Conviction-Gating-Schwelle 75** (PR #123) —
  `ANOMALY_CONVICTION_MIN_THRESHOLD=75` (vorher 50) gilt explizit auf
  **alle** Anomaly-Trigger inklusive `monster_backup`. Bei Conviction
  < 75 ist ein Setup per Definition kein „extremer Fall", auch wenn
  Monster-Score hoch. Numerisch deckungsgleich mit
  `ANOMALY_CONVICTION_HIGH_THRESHOLD=75` aber semantisch getrennt
  (HIGH triggert Aktions-Push, MIN gating-t alle anderen).
- **Earnings-Sofort-Alert Per-Event-Dedup** (PR #123) — Cooldown-Key
  `earnings_immediate_{ticker}_{DD.MM.YYYY}` mit
  `EARNINGS_IMMEDIATE_COOLDOWN_HOURS=24`. Ersetzt den alten
  `is_on_cooldown(ticker)`-Pfad mit `ALERT_COOLDOWN_HOURS=2`, der
  Mehrfach-Pushes für dasselbe Earnings-Event zuließ (DMRC 3× am
  11./12.05.).
- **`conviction_score` in `push_history`** (PR #123) — optionales
  int-Feld, von Anomaly- und Earnings-Sendern befüllt, Exit-Sender
  lassen es `None`. Schema-Erweiterung in `push_history.py:_record_push`
  als SSOT.
- **Zwei-Run-Architektur — `run_phase` als steuerndes Feld**
  (PR #124) — `app_data.json["run_phase"]` ∈ `{premarket, postclose}`.
  10:00-UTC-Cron schreibt premarket (Vorschau), 21:00-UTC-Cron
  postclose (EOD-Wahrheit). `_resolve_run_phase()` in
  `generate_report.py` liest `RUN_PHASE`-ENV, validiert, fällt bei
  Garbage auf premarket zurück. `ki_agent.py` liest `run_phase` aus
  `app_data.json` und gating-t den Anomaly-Push-Loop
  (`anomaly_pushes_enabled = (run_phase == "premarket")`).
  `process_exit_signals` läuft in beiden Phasen.
  `_append_backtest_entries` nur im postclose-Mode.
- **`run_phase`-Pill im Header** (PR #124) — `_renderRunPhasePill(phase)`
  rendert farbcodierte Pill: gelb „Pre-Open-Vorschau" / grün
  „Post-Close". Fehlendes Feld → kein Pill.
- **Token-Soft-Reset bei 401/403** (PR #125) —
  `TOKEN_AUTH_FAIL_HARD_THRESHOLD=3` (Module-Scope). Counter 1, 2 →
  nur Session+Memory löschen (Encrypted Blob bleibt → User landet im
  Unlock-Modal). Counter 3 → `_clearAllTokens()` (Hard-Reset, User
  landet im Setup-Modal). `_resetTokenAuthFailCount()` auf jeden HTTP
  204 (success).
- **iCloud-Schlüsselbund-Integration** (PR #125) — drei Token-Modale
  in `<form onsubmit="return false">`-Wrapper. Hidden
  `<input autocomplete="username" value="squeeze-report-master">`
  bindet Master-Passwort an stabilen Account-Identifier. Submit-
  Buttons `type="submit"`, Cancel-Buttons `type="button"`.
- **Keep-Alive-Touch in `getToken()`** (PR #125) — bei jedem
  erfolgreichen Token-Read `localStorage.setItem('_tok_keepalive',
  Date.now())`. Spekulatives Anti-ITP-Workaround (Apples 7-Tage-
  Inaktivitäts-Counter soll auf jedem Storage-Write resetten).
  Defensive try/catch, Write nur wenn `tok` nicht leer.
- **Watchlist-Drawer kein `dataset.loaded`-Cache mehr** (PR #126) —
  `wlExpand` rendert bei jedem Open neu via `buildWlDetails(ticker, d)`.
  Der `body.dataset.loaded='1'`-Marker bleibt erhalten, hat aber
  keinen Funktions-Bypass mehr — dient als selectorbarer „offen"-
  Marker für ki_agent-Trigger-Invalidation.
- **`_WL_CARDS`-Re-Assign nach ki_agent-Tick** (PR #126) — im
  `_kiAgentSuccess`-Then-Block fixe Reihenfolge: erst
  `window._WL_CARDS = appData.watchlist_cards || {}`, dann
  `[data-loaded]`-Invalidation, dann `renderAgentSignals(data)`.
  Stellt sicher, dass Drawer-Renders nach ki_agent-Updates frische
  Daten lesen.

### Kumuliert (Auszug — siehe vorige Handover-Updates für Vollständigkeit)

- **`Conviction-Score`** (PR #89 + PR #95) — vierte Bewertungs-Achse.
  Komponenten Setup 33 / Earliness 28 / Anomaly 28 / Regime 11.
  Levels ≥ 75 high (grün), 50–74 medium (orange), < 50 low (grau).
- **VIX-Persistenz via `**existing`-Spread** (PR #90) — analog im
  Daily-Run und ki_agent, jetzt zusätzlich `run_phase` (PR #124) und
  `_tok_keepalive` (PR #125) via Spread durchgereicht.
- **`DRIVER_CLASSIFICATIONS` Hybrid-Schema** (PR #83), **Methodik-
  Display zeigt bedingte Boni** (PR #98 + #99), **Backtest-Panel
  Median/Mean/Skew** (PRs #81/#86/#88/#92/#93/#94/#105),
  **Severity-Tiering** (PR #110), **Exit-Druck-Composite-Render**
  (PR #108), **`change`-Fallback Watchlist-only** (PR #112),
  **Push-Historie-UI** (PR #114), **`prev_conviction_scores`-
  Persistenz** (PR #109).

## Wichtige Lernerfahrungen

### Aus dieser Tagesschicht (12.05.)

- **Trading-Wert-Filter als Priorisierungs-Prinzip.** Der heutige
  Backlog wurde NICHT nach Engineering-Vollständigkeit sortiert
  (Code-Hygiene, Refactor-Splits) sondern nach konkretem Trading-
  Wert. Prüffrage pro Auftrag: „hilft das bei der nächsten Trade-
  Entscheidung oder ist es Aufräumarbeit?" Alle fünf ursprünglichen
  Schmerzpunkte (Push-Inflation, Score-Inflation, stale Drawer,
  stale Chat, Token-Reentry) heute gelöst — das ist mehr Trading-
  UX-Verbesserung an einem Tag als die letzten zwei Wochen
  Code-Hygiene zusammen.
- **Diagnose vor Fix als Default-Pattern.** Vor jedem größeren
  Eingriff stand heute eine read-only-Bestandsaufnahme. Die hat
  drei strukturelle Bugs aufgedeckt, die mit reinem „Symptom-Fix-
  Mindset" nicht gefunden worden wären:
  - PR #119 (score_history-Pruning) — Symptom „Smoothing fühlt
    sich aus", Ursache lexikographischer DD.MM.YYYY-Vergleich
    droppte Mai-Einträge silently
  - PR #122 (Chat-Synthesis) — Symptom „LLM redet falsch über
    Positions", Ursache zwei verschiedene Lese-Pfade für denselben
    Datenpunkt
  - PR #126 (Watchlist-Drawer) — Symptom „Drawer veraltet vs.
    Top-10", Ursache `dataset.loaded`-Cache-Gate ohne Invalidation
- **Score-Inflation ist real und strukturell, kein Bug.** `rel_volume`
  wächst per Definition über den US-Handelstag (Today-Volume / 20d-
  Avg). Empirie aus app_data-Snapshots: DFDV +17, INDI +12 Punkte
  zwischen US-Open und Pre-Close. Ranking INNERHALB eines Runs bleibt
  valide (alle Ticker betroffen). Absolute Schwellen sind aber
  zeitabhängig. **Zwei-Run-Architektur mit Postclose=Wahrheit ist die
  strukturelle Lösung, nicht Schwellen-Tuning** (PR #124).
- **Lokale Erinnerung im Tool-Tracking veraltet schnell.** Claude
  Code's PR-Status-Cache hängt regelmäßig hinterher nach manuellen
  Easy-Merges. Subscription-Webhook-Events werden manchmal verschluckt.
  Workaround: bei Bedarf explizit „PR #X ist gemerged" mitteilen,
  damit lokaler Branch-Cleanup synchron läuft. Heute zweimal nötig
  (PR #122/#123/#124-Gruppe + PR #125 + PR #126).
- **Bewusste Architektur-Entscheidungen statt vergessenes
  Sicherheitsnetz.** `monster_backup` war historisch als „ungated
  für extreme Fälle" gedacht und so dokumentiert. In der Praxis war
  es die lauteste Push-Klasse (51 % aller Pushes laut heutiger
  Bestandsaufnahme). Klar machen, ob ein scheinbares „Sicherheitsnetz"
  noch echte extreme Fälle abdeckt oder zur lautesten Quelle geworden
  ist — und entsprechend die Architektur explizit umparken. PR #123
  hat das für monster_backup gemacht (jetzt Conviction-gated wie alle
  anderen), CLAUDE.md begründet die Entscheidung.

### Aus vorherigen Sessions (kumuliert, beibehalten)

- **Multi-Session-Arbeit am gleichen Repo vermeiden** — Single-
  Session pro Tag als Defaultregel.
- **Sandbox-Verluste sind erwartbar.** Code-Stand IMMER über PR auf
  GitHub spiegeln — der gemergte main ist die einzige verlässliche
  Persistenz.
- **`main`-Pushes sind blockiert (HTTP 403)** — PR-only-Workflow für
  alle Änderungen.
- **yfinance-Default Multi-Ticker-Form ist `(Field, Ticker)`**, nicht
  `(Ticker, Field)` — bei jedem `yf.download(tickers, …)` mit Liste
  explizit `group_by='ticker'` setzen.
- **Pipeline-Reihenfolge ist eine eigene Klasse von Bug.** Jede neue
  Side-Effect-Funktion mit Stock-Dict-Mutation muss in der `main()`-
  Pipeline an der richtigen Stelle einsortiert werden, BEVOR der
  HTML-Render läuft, der die Werte konsumiert.
- **Squeeze-Guardian-Konformitäts-Check nach Multi-PR-Sessions ist
  kein Overhead, sondern Versicherung.**
- **Backtest-Verteilungs-Erkenntnis (10.05.2026) — Median allein
  unterschätzt die Edge.** Squeeze-Renditen sind extrem rechtsschief;
  einzelne Knaller treiben den Mean weit über den Median.
- **Conviction-Score-Aufbau: Daten erst, UI danach.** Schritt A
  (Daten ohne UI) erlaubt Plausibilitäts-Verifikation der Werte bevor
  man die UI baut.
- **Frontend-Verifikation in Browser-Konsole (`fetch` +
  `console.log`)** ist schnell und zuverlässig.
- **UI-Lücken kommen oft erst beim echten Nutzen ans Licht.** Bei
  jeder neuen Daten-Pipeline-Sichtbarkeitsregel die Frage stellen:
  „was sieht der User bei leerem/ruhigem Zustand?".
- **Conviction-Push als Aktions-Signal vs. Anomaly-Push als
  Beobachtungs-Signal — semantische Trennung im Severity-Tiering**
  (PR #109/#110). Bei der Einführung eines qualitativ neuen
  Signal-Typs die bestehenden Signale neu einordnen — sonst geht
  das neue Signal im Rauschen unter. PR #115 + heutige PR #123
  vertiefen diese Trennung mit dem Conviction-Gating auf 75.
