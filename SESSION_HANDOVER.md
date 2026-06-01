# SESSION_HANDOVER.md — Stand 01.06.2026

## 1) HEUTE IMPLEMENTIERT (mit Hashes)
- **#295 (Merge a48dd11, Commit 2efb295) — 31.05.** premarket-Cron
  8:17 → 6:17 UTC (`17 6 * * 1-5`). GitHub-Actions-Scheduler-Drift
  (variabel +1.8 bis +5.76h, 2/10 Werktage gedroppt). 6:17 absorbiert
  Max-Drift → Ankunft ~12:06 UTC, vor US-Open. Drop-Redundanz bewusst
  NICHT gelöst (separates Thema).
- **#296 (Merge 361dba4) — 31.05.** Cleanup zu #295: Kommentarblock +
  `mock_test_postclose_run.py:136/173` auf `17 6` nachgezogen (schlafender
  False-Positive behoben). Auto-Merge.
- **#297 (Merge 19be8d0, Commit c8a06cf) — 31.05.** Health-Check **S13
  Daten-Reife-Gate** für die drei 30.06.-Auswertungen (Setup-Edge ≥70/
  schema_v4, Entry-AUC, CTB-Edge — je vorhanden/reif_5d/reif_10d).
  config `EXPECTED_RVOL_NORMALIZATION=False`. Rein lesend.
- **#298 (Merge 2da1a0e, Commit 7800494) — 31.05.** **Konsistenz-Wächter
  (Projekt C)** — S13 auf `CONSISTENCY_EXPECTED_STATE`-Dict erweitert
  (3 stabile Flags: RVOL_NORMALIZATION_ENABLED, SCORE_NORMALIZATION_VERSION=1,
  EARLINESS_FORMULA_VERSION=2). Soll-Ist-Drift-Wächter, Fehlerklasse 3.
- **#299 (Merge, Commit ea6350f) — 31.05.** Handover-Update nach #295–#298.
- **#300 (Merge, Commit edd8969) — 31.05.** Health-Check-Tabellen-Backfill
  S8–S13 in CLAUDE.md + `docs/health_check_spec.md` (Tabellen listeten nur
  S1–S7/S8; S9–S13 + Lauf-Spalte ergänzt). Doku, Auto-Merge.
- **#301 (Merge, Commit 1787624) — 31.05.** 2 Doku-vs-Code-Divergenzen
  an Code angeglichen: CLAUDE.md-S8 `last_digest_sent` → `last_successful_run`
  (Code seit #274), spec-S2 „≥10 Tickers" → „≥8" (`HEALTH_CHECK_S2_MIN_TICKERS`).
  Doku, Auto-Merge.
- **#302 (Merge, Commit 1741d95) — 31.05.** mock_test_digest-Staleness-Fix:
  `now_ts` in 2 zeit-relativen Provider-Tests fixiert (Stale-Reset >7d nullte
  Counter bei wall-clock-now). 32/32 grün, deterministisch. Auto-Merge.
- **#303 (Merge, Commit `<via #303>`) — 01.06.** **Split-Label-Fix.**
  backtest-T+0-Return-Basis von gespeichertem `entry_price` (am Entry-Tag
  eingefrorener auto_adjust-Stand) auf `_close_at(0)` aus DEMSELBEN
  Forward-Download umgestellt → eine Adjust-Epoche → split-konsistent.
  Behebt Faktor-Sprung bei Split zwischen Entry und T+N (Alt-Bestand:
  20 Split-Leichen, AIXI r10=1006% etc.; im v4-Sample 0 betroffen).
  NUR Label, kein Score. Nur vorwärts. Manueller Merge.
- **#304 (Teil A 7b99570 + Teil B 1aa36e7) — 01.06.** **report_date-Wurzel-
  Fix + Kohorten-Korrektur.** (A) `report_date` + `_today_iso` Berlin → ET
  (`America/New_York`): ein durch Actions-Drift nach Berlin-Mitternacht
  laufender postclose-Run (22-23 UTC) bekam den nächsten Berlin-Tag obwohl
  er denselben US-Handelstag (16-17 ET) verarbeitet → Fehl-Datierung +
  Dedup-Kollision. `_today_iso` musste mit (speist S1+S4). (B) Rückwirkende
  Korrektur: 10 Einträge (ABSI, HUMA, KSS, LNKS, NMAX, OM, PDYN, PLCE, SERV,
  SPCE) von `date=29.05.` → `28.05.` (waren 28.05.-Kohorte via Commit
  f0ef9077 fälschlich als 29.05. datiert, Returns noch None → vor Schaden
  korrigiert). Nur date-Feld. Manueller Merge.

## 2) AKTIVE POSITIONEN
- **AMC** — Halt-Strategie, no_exit_alerts=true. Conv 4, Setup stark gefallen.
  Trailing-Stop −10.2% vom Hoch, score 34. Bewusst gehalten.
- **IONQ** — Conv 25, score 7, pnl +33.2%. Exit-Mechanik flaggt, kein
  Exit-Treiber. Schließung = Chart-/Bauchgefühl-Call.
- Watchlist (6): PDYN, AI, GEMI, CRMD, IONQ, AMC.
- Zuletzt geschlossen (im Journal): INDI +23.1% (22→28.05), CRDF +1.7%
  (19→28.05, ≥70-Bucket-Datenpunkt), RR +11.5% (26.05.).

## 3) VERIFIKATION MORGEN (erster Werktags-Daily-Run, frühestens Mo 01.06. / Di 02.06.)
- **Borrow-Reparatur (#292) ERSTMALS werktags live:** Actions-Log auf
  `provider="borrow"` + coverage + `daily[-1].date` aktuell prüfen. ~100% =
  iBorrowDesk lebt vom Runner; 0% = Runner-Block → FTP-Fallback. CTB im
  Score sichtbar (Katalysator-Bonus feuert)?
- **report_date→ET (#304) erstmals live:** Actions-Log `=== Squeeze Report
  DD.MM …` muss den US-Handelstag zeigen (an Drift-Tagen ET-Datum, nicht
  Berlin+1). S1/S4 dürfen an Drift-Tagen NICHT mehr fälschlich feuern
  (Achsen jetzt konsistent ET).
- **Split-Label-Fix (#303):** greift automatisch beim nächsten Split-Ticker;
  zusätzlich füllt der nächste ki_agent-Tick die 10 korrigierten 28.05.-
  Einträge (Returns waren None) gegen den korrekten 28.05.-yf-Bar.
- **S13 erstmals live:** 4 `[Daten-Reife 30.06.]`-Zeilen — Setup-Edge ~50/
  reif5=26/reif10=4, Entry/CTB „ungebaut", Konsistenz-Wächter 3× [OK].
- **premarket-Cron 6:17 erstmals werktags:** landet der Run vor 13:30 UTC
  (echter premarket)? score_inflation_log: run_phase==tsp=='premarket'.
- **#297/#298/#303/#304 = Backend/Daten, kein Frontend** → nur Actions-Log-
  Sichtung, kein iPhone-UI-Verify nötig.

## 4) GEPLANTE AUFGABEN + WIEDERVORLAGEN (mit Daten)
### Annahmen-Inventur (durchgeführt 01.06., 4 kritische Funde)
Systematisches Durchleuchten der **Datengrundlage** der Edge-Auswertungen:
- **Split-Labels → GEFIXT (#303).** entry_price-Adjust-Epoche vs. Forward-
  Closes → split-konsistente Basis.
- **Datums-Attribution → GEFIXT (#304).** Berlin-Mitternachts-Drift →
  ET-Kopplung + 10-Einträge-Korrektur.
- **Score-Versionsmarker (Fund 1.1) → git-verifiziert (unshallow).** KEINE
  `score()`-Änderung 14.–28.05.; einzige v4-Score-Berechnungs-Änderung =
  **#292 Borrow** (31.05.), betrifft NUR `borrow_rate>50%`-Ticker. Earliness
  V2 wirkt nur via **Conviction**, NICHT Setup-score (CLAUDE.md belegt
  „ohne Score-Effekt"). Alle anderen 14.–28.05.-Commits = Display/Persist/
  Refactor/Health-Check. **Auswertungs-Lösung:** borrow-teure Ticker separat
  behandeln statt Sample am Stichtag abzuschneiden — KEIN Versionsmarker nötig.
- **or-0-Defaults (Fund 4.2) → im v4-Sample 0 Fälle, brennt nicht.**
  `short_float` + `si_trend` per `short_float_source`/`si_trend_source`-Marker
  als „fehlt" (=`none`) erkennbar → Auswertung MUSS `source=none` ausfiltern.
  `dtc`/`rvol`/Bonus-Felder: kein Marker, „0 vs fehlt" verloren → eigener PR
  (dtc_source/rvol-Flag) **nur bei Bedarf**. Persist-Wert und Score-Input
  sind GETRENNT (Score liest dieselben Dict-Felder vor dem Persist) → ein
  Persist-only-None-Fix wäre risikolos, KEIN Score-Touch.

### Auswertungs-Regeln (reife-getriggert, NICHT mehr fixer „30.06."-Termin)
Reife entscheidet, Gate #297 meldet laufend. Bei der ersten reifen
≥70-Auswertung gelten: (a) **borrow-teure Ticker (`borrow_rate>50`) separat**
behandeln (eigene Score-Definition seit #292), (b) bei SF/SI-Faktor-Analyse
`source=none` **ausfiltern** (sonst „fehlt" als echte 0), (c) **Lücke 28.05.**
dokumentieren (Backfill nur partiell aus score_inflation_log möglich —
volle Faktoren weg, da app_data/agent_signals überschrieben).

### Bestehende offene Stränge
- **★ γ-2 (RVOL-Normalisierung) — BLOCKIERT, eigenes Projekt.** γ-2 in
  KEINEM Commit/Branch (nur γ-1-Marker #248). 4 Vorbedingungen: (a)
  premarket-Datenbasis zu dünn (~3 echte Werktage/10 + Drops), (b) Cron-
  Drift absorbiert (#295), Sammlung erst über nächste Werktage verlässlich,
  (c) `rel_volume_raw`-Feld für Late-Runner-F-3 UNGEBAUT, (d) Skalierer
  0.10/0.40 ungestützt (kein Sweep). Reihenfolge: Daten → Sweep →
  rel_volume_raw → Schwellen → Flip. **Kopplung:** bei Aktivierung in
  `CONSISTENCY_EXPECTED_STATE` BEIDE Soll gepaart (EXPECTED_RVOL_NORMALIZATION
  → True UND SCORE_NORMALIZATION_VERSION-Soll → 2), sonst meldet S13 zurecht
  Drift.
- **B — Borrow-Coverage-Wächter:** WARTET auf ersten echten Werktags-Daily-
  Run (frühestens 01.06.) — Actions-Log auf `provider=borrow` + coverage
  prüfen, DANN B-Schwelle festlegen und bauen (success_check
  `cost_to_borrow is not None`, eigener _BORROW_ACCT seit #292 getrennt).
- **FOLGE-PR Borrow-Persistenz** (klein, hohe Prio vor erster CTB-Auswertung):
  Borrow-Felder additiv ins backtest_history (v4 behalten, S10_OBSERVED,
  atomar). CTB fließt seit #292 in Score, wird noch NICHT persistiert.
  Sobald persistiert, schaltet S13 die CTB-Edge-Zeile von „ungebaut" auf
  Counts.
- **MEMORY-HYGIENE (neu):** Memory ist voll (30/30). Konsolidieren —
  #21–#24 (Entry-Modul) zu 1–2 verdichten. Nach Meilensteinen löschbar:
  mock_test_digest-Notiz (nach diesem Handover-Rewrite erledigt),
  Score-Inflation-Notiz (nach γ-2), Entry-Vorarbeit (nach 10.06.).
- **Annahmen-Inventur als wiederkehrende Methode** (Roadmap, eigene Sitzung):
  systematisch dunkle Ecken durchleuchten statt reaktiv zu stolpern.
- **Drop-Redundanz (aus #295):** GitHub droppt ~20% der Cron-Slots; frühere
  Cron-Zeit löst NUR Drift, NICHT Drops. Echte Lösung: externer Trigger
  (Cloudflare-Worker analog quote-proxy). Roadmap.
- **FOLGE-PR Naming-Cleanup** (niedrig): IBKR_* → IBORROWDESK_*,
  STOCKANALYSIS_BORROW_ENABLED irreführend. Reine Umbenennung.
- **02.06.** Chart-Indikatoren (TTM Squeeze/VWAP/OBV) als Entry-Score-
  Komponenten — nur Entry-Score ab 10.06., NICHT Setup-Score.
- **10.06. ★★★ GROSSPROJEKT HÖCHSTE PRIORITÄT:** Entry-Timing-Modul Start.
  Entry-Score 0–100, 5 Komponenten je 20%. Shadow-Mode, kein Push bis
  Entry-AUC reif. Neues Modul entry_score.py (Pattern wie backtest_history.py).
  Andock in main() NACH apply_score_smoothing, VOR compute_earliness_pts.
  Schritte: (1) Persistenz Roh-Felder ✅ läuft (#259/#260/#279) | (2) 5
  Normalisierungs-Funktionen (MANUELL) | (3) Persistenz-Spec (AUTO, additiv
  v4, KEIN v5) | (4) Aggregation 5×20% (MANUELL) | (5) Cockpit-Pillar
  (Frontend+iPhone, MANUELL, eng auf ~320px). MISSING-DEFAULTS: alle 5
  fehlend → neutral 50. SHADOW-GARANTIE: Flag ENTRY_SCORE_PUSH_ENABLED=False.
  Sobald entry_score persistiert, schaltet S13 die Entry-AUC-Zeile auf Counts.
  NORMALISIERUNG: feste Caps starten, NICHT Perzentil (Daten zu dünn).
- **08.06. (Rechner-Tag — NICHT mit Handy-Nachschauen verwechseln):**
  Backup-/Disaster-Recovery-Diagnose (read-only) — Schwerpunkt nicht-
  aufholbare Daten (backtest_history.json, score_inflation_log.jsonl,
  score_history.json). VOR 10.06.-Entry-Modul.
- **UOA-Befund (entscheiden bei reifer UOA-Komponente):** uoa_atm_ratio
  strukturell eng berechnet (ATM-Band, Calls, nächste Expiration) → reale
  max 2.46, ANOMALY_UOA_VOL_OI=10.0 unerreichbar → UOA-Anomaly-Push de
  facto tot. Entscheidung: enge ATM rekalibrieren ODER auf Total-Vol/OI
  umbauen. Code vor 10.06. NICHT anfassen.
- **Card #10 MERKREGEL:** bei manuellem Dispatch → HTML-Sanity-CRIT →
  SOFORT HTML-Artefakt aus dem Actions-Run ziehen. Einzige fehlende Evidenz.
- **AMWD / yfinance-Falsch-Delisting beobachten:** 28.05. „possibly delisted"
  trotz handelbar. Bei Muster diagnostizieren.

## 5) STRATEGISCHE ROADMAP
- Entry-Timing-Modul (★★★, 10.06.) — höchste Priorität.
- γ-2 RVOL-Normalisierung (★, blockiert — s. Sektion 4).
- **Annahmen-Inventur als wiederkehrende Methode** — systematisches
  Durchleuchten der dunklen Ecken (Datengrundlage, stille Defaults,
  Versions-Drift) statt reaktivem Stolpern. Eigene Sitzung pro Runde.
- Phasen-abhängige / perzentil-basierte Schwellen statt fester Absolut-
  Schwellen (an Daten-Reife gekoppelt).
- Borrow-Fee + Utilization in score() (Literatur: stärkste Squeeze-
  Prädiktoren) — Entscheidung bei reifer CTB-Coverage.
- **Externer Trigger / Dead-Man-Switch außerhalb GitHub Actions** — deckt
  Cron-Drops (~20%) per Re-Dispatch UND das Failure-Fate-Problem (Health-
  Check teilt den Pipeline-Ausfall). MUSS extern laufen (Cloudflare-Worker).
- Backup/Disaster-Recovery (Wiedervorlage 08.06.): lokaler git mirror |
  Daten-Export außerhalb GitHub | Spiegel auf anderem Account.
- Konsistenz-Wächter-Ausbau (Projekt C, S13): heute 3 Konstanten; weitere
  stabile getattr-lesbare Flags additiv aufnehmbar (Aufnahme-Regel: stabil
  + Schaden-bei-Drift; keine Tunables/Crons/Literale).

## 6) CODE-HYGIENE-BACKLOG (mit Status)
- **or-0-Defaults Persist-Fix** (dtc/rvol/Bonus → None bei fehlend) → OFFEN,
  niedrig, NUR bei Bedarf (v4-Sample heute 0 Fälle). Persist-only, kein
  Score-Touch (Score-Input getrennt).
- **Doku-Backfill S8–S13** → ERLEDIGT (#300/#301).
- **mock_test_digest 2 Fails** → ERLEDIGT (#302, Staleness-Fix, 32/32 grün).
- **finviz Flag-aus + α (Provider rückbauen)** → OFFEN, an Daten-Reife
  gekoppelt. γ (Schwellen-Override 100) als Übergang. SF-Quote-Pfad ungated.
- v1/v2 → Jinja → OFFEN, niedriger Trading-Wert.
- Cockpit Stage 3 (.sb-Reste) → VERTAGT (.sb-conf-* live reused).
- S10-Feiertags-Zähler (display-only) → an Decay-Fix koppeln.
- Großer generate_report.py-Split → VERWORFEN (globals-Falle).
- **Stale-Kommentar fetch_stockanalysis_borrow (gen._report.py:1608):**
  sagt „display-only", CTB fließt aber als Catalyst-Bonus. Redaktionell,
  Auto-Merge, niedrig.
- **Borrow-Naming-Cleanup** (niedrig, nach #292): IBKR_* → IBORROWDESK_*.

## 7) ARCHITEKTUR-ANKER
- Earliness V2 (DTC, AUC 0.77, wirkt NUR via Conviction — NICHT Setup-score) |
  Phase-2 Exit komplett (6 Trigger) | Live-Polling Cloudflare-Worker
  quote-proxy.easywebb.workers.dev | Conviction-Schwelle 75 (#123) |
  Token AES-GCM+PBKDF2 (classic ghp_).
- run_phase steuert: normalize-Short-Circuit, Backtest-Append-Gate (nur
  postclose), anomaly_pushes (nur premarket).
- **report_date + _today_iso = US-Eastern (`America/New_York`) seit #304,
  NICHT mehr Berlin.** Wurzel-Fix gegen Mitternachts-Drift-Fehl-Datierung.
  Beide MÜSSEN derselben ET-Achse folgen (today_iso speist S1+S4;
  score_history wird mit report_date gestempelt; backtest_has_today
  vergleicht gegen report_date → wandert mit). Die lokale `berlin`-Variable
  in main() ist entfernt; die Header-Timestamp-Anzeige (Z.~6254) nutzt eine
  eigene, von der Datums-Achse unabhängige Berlin-ZoneInfo-Instanz.
- **backtest-T+0-Return-Basis = `_close_at(0)` (Close am Entry-Index) seit
  #303, NICHT mehr gespeicherter entry_price.** Beide Endpunkte (Entry +
  Forward) aus EINEM auto_adjust-Download → eine Adjust-Epoche → split-
  konsistent. entry_price-FELD bleibt erhalten (Position-/Display-Konsumenten),
  nur nicht mehr Return-Basis. T+1-Pfad war schon konsistent (close_t1).
- **"Echter Phasen-Run" nur via score_inflation_log nachweisbar:
  run_phase==trading_session_phase.** date in backtest_history ist KEIN
  Beweis (Manual-Frühdispatch). Basis für S11/S12.
- S10-Loader filtert backtest_schema_version==4 (additiv halten!).
  Plus Wochenend-Filter (`date.weekday()>=5` raus).
- backtest_history.py eigenes Modul seit #256 (Callable-Injection).
  Idempotenz-Key (ticker, report_date).
- return_5d-Fill = update_backtest_returns() in ki_agent.py (stündlich,
  matcht `date` gegen yf-Trading-Day-Index, idempotent).
- **S9-CRIT-Exit-Pfad (generate_report.py) filtert STRIKT id=="S9".** Neue
  crit-Checks (S12) blockieren NICHT. Bei Refactor id=="S9"-Filter
  UNBEDINGT beibehalten.
- **S8 misst seit #274 last_successful_run (ISO), NICHT last_digest_sent.**
- **Health-Check-Schichten (Stand 01.06.):** S1–S7 State-Invariants | S8
  Digest-Liveness | S9 HTML-Sanity (einziger CRIT-Block-Pfad) | S10 Daten-
  Integrität (MUSS/LAG/Auto-Detect v4) | S11/S12 Phasen-Sammel-Frequenz |
  S13 Daten-Reife-Gate (#297) + Konsistenz-Wächter (#298). Tabellen in
  CLAUDE.md + spec vollständig S1–S13 (Backfill #300/#301).
- **Konsistenz-Wächter (Projekt C, #298):** CONSISTENCY_EXPECTED_STATE-Dict
  in config.py. S13 liest IST via getattr(config,name), warnt pro Drift.
  Aufnahme-Regel: nur stabile getattr-lesbare Konstanten mit Schaden-bei-
  Drift — KEINE Tunables/Crons/Literale.
- **Provider-Schwellen:** Default DIGEST_CONSECUTIVE_THRESHOLD=3, Override-
  Dict {"finviz":100}.
- **Borrow-Quelle = iBorrowDesk-JSON seit #292.** Eigener _BORROW_ACCT
  getrennt von _STOCKANALYSIS_ACCT (SI). fee=0.0-Schutz (is not None).
  Persistenz offen (Folge-PR).
- **Token-Session-Wrap (#281):** Token AES-GCM-gewrappt in IndexedDB
  (7-Tage-Rolling, fail-soft auf Master-PW-Modal). _tokPending FIFO-Queue.
- Cron-Inventar: ki_agent `17 * * * *`, daily premarket `17 6 * * 1-5`,
  postclose `17 21 * * 1-5`, health-digest `47 8 * * *`, watchlist `0 7 * * 0`.
- Service-Worker raus seit #188.

## 8) LESSONS (01.06.2026)
- **Zufallsfund → systematische Suche:** Der γ-Fall war ein zufälliges
  Stolpern (Annahme „γ läuft" stimmte nicht). Die Annahmen-Inventur war
  dann bewusstes Leuchten in dunkle Ecken — die heutigen Funde (Split-
  Labels, Datums-Attribution, Versions-Drift, or-0-Defaults) sind GESUCHT,
  nicht zufällig. Lehre: nach einem stillen Bug nicht nur den einen fixen,
  sondern die ganze Fehler-Klasse systematisch absuchen.
- **Code kennt den Code, nicht die Kritikalität:** Wächter (S13/Projekt C)
  prüfen nur deklarierte Soll-Werte mechanisch. Das Gewichten — WELCHER
  Zustand kritisch ist — ist menschlich (Easy). Nordstern-Trennung:
  Mechanik (Maschine) vs. Bedeutung (Mensch). Ein Wächter, der „alles"
  überwacht, wäre Lärm; die Auswahl der 3 Konstanten war die menschliche
  Wert-Entscheidung.
- **Datum an Fach-Logik koppeln, nicht an Wallclock:** report_date musste
  an den US-HANDELSTAG (ET = die Fach-Semantik des Runs), nicht an die
  Berlin-Wallclock (zufällige Betreiber-Zeitzone). Wallclock-Kopplung
  erzeugte den Mitternachts-Drift-Bug. Generell: Persist-Schlüssel an die
  Domänen-Bedeutung binden, nie an die Ausführungs-Umgebung.
- **Split-konsistente Endpunkte aus EINER Datenquelle:** Zwei Werte
  vergleichen (entry vs. forward), die aus unterschiedlichen Adjust-Epochen
  stammen, ist eine stille Skalen-Falle. Lösung: beide aus demselben
  Download. Gilt für jede Ratio über die Zeit (Returns, Performance).
- **git-Tiefe prüfen vor „verifiziert":** Der flache Clone (87 Commits)
  hätte die „nur #292"-Aussage nicht belegen können — erst `git fetch
  --unshallow` (2555 Commits) machte die 14.–28.05.-Historie git-prüfbar.
  Vor einer Vollständigkeits-Aussage immer die Clone-Tiefe checken.
- **Persist-Wert ≠ Score-Input:** Dieselben Dict-Felder werden an
  getrennten Stellen gelesen (Score VOR dem Persist, Backtest-Persist
  danach). Ein Persist-only-Fix (None statt 0) berührt den Score NICHT —
  die zwei Pfade sauber trennen erlaubt risikolose Daten-Fixes.
