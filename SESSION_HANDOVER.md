# SESSION_HANDOVER.md — Stand 31.05.2026

## 1) HEUTE IMPLEMENTIERT (mit Hashes)
- **#295 (Merge a48dd11, Commit 2efb295) — 31.05.** premarket-Cron
  8:17 → 6:17 UTC (`17 6 * * 1-5`). Diagnose: premarket-Runs landen real
  ~11–14 UTC statt 8:17 — GitHub-Actions-Scheduler-Drift, **variabel
  +1.8 bis +5.76h, 2/10 Werktage ganz gedroppt** (22.05./26.05.). KEIN
  cron-/Zeitzonen-Bug (#253 nutzte bereits korrekten Ausdruck/Datei,
  Offset variabel = Actions-Infra). 6:17 UTC absorbiert die Max-Drift
  5.76h → Ankunft ~12:06 UTC, weiter vor US-Open 13:30 UTC. Einzige
  Änderung: cron-Zeile + Kommentar. postclose (17 21), Health-Digest
  (47 8), Resolver unberührt. **Drop-Redundanz bewusst NICHT gelöst**
  (separates Folge-Thema, ~20% Slot-Drops bleiben). Manueller Merge.
- **#296 (Merge 361dba4) — 31.05.** Cleanup-Folge zu #295. Zwei seit
  #253 veraltete Referenzen auf `17 6 * * 1-5` nachgezogen:
  daily-squeeze-report.yml-Kommentarblock (sagte noch „10:17 UTC …
  ~3,2h vor US-Open") + `mock_test_postclose_run.py:136/173`
  (`assert '17 10 …'` → `'17 6 …'`, Zeile 173 in sorted()-Reihenfolge
  `["17 21 …", "17 6 …"]` — schlafender False-Positive behoben, der bei
  yfinance-Verfügbarkeit gefailt hätte). NICHT angefasst:
  resolve_run_phase.py, CLAUDE.md, mock_test_run_phase_resolution.py
  (value-agnostisch/illustrativ). Auto-Merge (Doku/Test-Hygiene).
- **#297 (Merge 19be8d0, Commit c8a06cf) — 31.05.** Health-Check **S13
  Daten-Reife-Gate** für die drei 30.06.-Auswertungen. Rein lesend,
  kein Score-/Filter-/Schema-Touch. `evaluate_data_maturity_gate()`
  (pure) zählt Stichproben-Reife: Setup-Edge (`score≥70`, `schema_v==4`
  via `_s10_load_v4_entries`), Entry-AUC (`entry_score`), CTB-Edge
  (`cost_to_borrow`) — je vorhanden/reif_5d/reif_10d. Reife =
  return_5d/return_10d not None, **beide getrennt** (30.06.-Auswertung
  noch NICHT als Code codifiziert → keine Definition vorweggenommen).
  Integration in `evaluate_state_invariants` (id S13, nur Daily-Run,
  fail-soft analog S10): loggt Status-Zeilen „laufend" (log.info), Fail
  nur bei Drift. config: `EXPECTED_RVOL_NORMALIZATION=False` (Soll-Haken).
  10 Mock-Tests. Live: Setup-Edge vorhanden=50 reif_5d=26 reif_10d=4.
  Manueller Merge.
- **#298 (Merge 2da1a0e, Commit 7800494) — 31.05.** **Konsistenz-Wächter
  (Projekt C)** — S13 generalisiert vom 1 hartcodierten RVOL-Check auf
  eine Dict-Schleife über drei stabile config-Konstanten. Dritte
  Überwachungs-Schicht (Fehlerklasse 3 „Zustands-Drift"). config:
  `CONSISTENCY_EXPECTED_STATE`-Dict (Single-Source) = {RVOL_NORMALIZATION_
  ENABLED: EXPECTED_RVOL_NORMALIZATION(False), SCORE_NORMALIZATION_VERSION:
  1, EARLINESS_FORMULA_VERSION: 2}. `_consistency_checks()` (pure) liest
  IST live via `getattr(config, name)`, 1 warn-Fail (id S13) pro Drift +
  4. Status-Zeile `name=Ist/Soll [OK|DRIFT]`. Aufnahme-Regel zementiert:
  nur stabile getattr-lesbare Konstanten mit Schaden-bei-stillem-Drift —
  KEINE Tunables/Crons/Literale. 13 Mock-Tests, alle 3 heute [OK].
  Manueller Merge.

## 2) AKTIVE POSITIONEN
- **AMC** — Halt-Strategie, no_exit_alerts=true. Conv 4, Setup stark gefallen.
  Trailing-Stop −10.2% vom Hoch im Exit-Log, score 34. Bewusst gehalten.
- **IONQ** — Conv 25, score 7, pnl +33.2%. Exit-Mechanik flaggt, aber kein
  Exit-Treiber gesetzt. Schließung = Chart-/Bauchgefühl-Call.
- Watchlist (6): PDYN, AI, GEMI, CRMD, IONQ, AMC.
- Zuletzt geschlossen (im Journal): INDI +23.1% (22→28.05), CRDF +1.7%
  (19→28.05, hoher Score/dünner Return = ≥70-Bucket-Datenpunkt), RR +11.5%
  (26.05., catalyst crit).

## 3) VERIFIKATION MORGEN (erster Werktags-Daily-Run nach 31.05., frühestens Mo 01.06.)
- **Borrow-Reparatur (#292) ERSTMALS werktags live:** der heutige manuelle
  Sonntags-Lauf zeigte KEIN `provider="borrow"` (kein Backtest-/Borrow-Pfad
  am Wochenende — erwartbar, KEIN Defekt). Erster echter Werktags-Run:
  Actions-Log auf `provider="borrow"` + coverage + `daily[-1].date` aktuell
  prüfen. coverage ~100% = iBorrowDesk lebt vom Runner; 0% = Runner-Block
  → FTP-Fallback erwägen. CTB im Score sichtbar (Katalysator-Bonus feuert)?
- **S13 erstmals live im Actions-Log:** 4 `[Daten-Reife 30.06.]`-Zeilen
  erwartet — Setup-Edge ~vorhanden=50/reif_5d=26/reif_10d=4 (steigt mit
  jedem postclose), Entry/CTB „ungebaut, n=0", Konsistenz-Wächter 3× [OK]
  (`False/False · 1/1 · 2/2`), keine S13-Drift-Fails.
- **premarket-Cron 6:17 erstmals werktags:** landet der Run jetzt VOR
  13:30 UTC (echter premarket statt `open`-Drift)? score_inflation_log
  prüfen: run_phase==tsp=='premarket'. S11 sollte grün bleiben.
- **iPhone-Verify (#297/#298 sind reine Backend-Logik, kein Frontend):**
  kein UI-Verify nötig — nur Actions-Log-Sichtung.

## 4) GEPLANTE AUFGABEN + WIEDERVORLAGEN (mit Daten)
- **★ γ-2 (RVOL-Normalisierung scharfschalten) — BLOCKIERT, eigenes
  Projekt.** Diagnose 31.05.: γ-2 existiert in KEINEM Commit/Branch
  (nur γ-1-Marker #248 gemergt, reiner Versions-Marker). Vier
  Vorbedingungen offen:
  - (a) **premarket-Datenbasis zu dünn** — nur ~3 echte premarket-
    Werktage in letzten 10 (+ Drops); n=70 all-time. Re-Kalibrierung
    nicht belastbar.
  - (b) **Cron-Drift absorbiert (#295)**, aber verlässliche Sammlung
    erst über die nächsten Werktage (6:17-Cron muss sich beweisen).
  - (c) **`rel_volume_raw`-Feld für Late-Runner-F-3 UNGEBAUT** — existiert
    in keiner .py. Bei Flip liest Late-Runner-Earliness (`EARLINESS_LATE_
    RUNNER_RVOL_MAX=5`) den normalisierten Wert → stiller Bruch.
  - (d) **Skalierer ungestützt** — `PREMARKET_RVOL_SCALER=0.10`
    (Daumenwert), „~0.40 Kipppunkt" nur Handover-Notiz „dünnes n", KEIN
    Sweep im Repo.
  Reihenfolge: Daten sammeln → Sweep → `rel_volume_raw` bauen → Schwellen
  (Late-Runner 5×, Driver/Combo 2.0×, Daily-Anomaly 5.0×) kalibrieren →
  ERST DANN Flip (ENABLED=True + VERSION=2 gepaart). **Folge für 30.06.:
  Setup-Edge-Auswertung auf inflations-bereinigten Daten NICHT möglich
  (n=0 bereinigt); nur unbereinigt (Ranking valide, absolute Edge
  verzerrt) ODER verschieben.**
- **★ γ-2-KOPPLUNG (leicht zu vergessen):** bei Aktivierung BEIDE Soll in
  `CONSISTENCY_EXPECTED_STATE` **gepaart** ziehen — `EXPECTED_RVOL_
  NORMALIZATION` → True UND `SCORE_NORMALIZATION_VERSION`-Soll → 2 (parallel
  zu den echten Flags `RVOL_NORMALIZATION_ENABLED` + `SCORE_NORMALIZATION_
  VERSION`). Sonst meldet S13 zurecht Drift. (Genau der Schutz, den
  Projekt C liefert.)
- **B — Borrow-Coverage-Wächter (Health-Check): WARTET auf erste
  Borrow-Verifikation.** Heutiger Sonntags-Lauf zeigte erwartungsgemäß
  kein `provider="borrow"`. Wiedervorlage: erster echter Werktags-Daily-
  Run nach #292 (frühestens Mo 01.06.) — Actions-Log auf `provider=borrow`
  + coverage + `daily[-1].date` prüfen, DANN B-Schwelle festlegen und
  bauen (success_check `cost_to_borrow is not None`, eigener _BORROW_ACCT
  schon getrennt seit #292).
- **FOLGE-PR Borrow-Persistenz** (klein, hohe Prio vor 30.06.): Borrow-
  Felder additiv ins backtest_history (v4 behalten, NICHT v5 — S10-Loader
  filtert ==4), in S10_OBSERVED_FIELDS, config+backtest_history atomar.
  Grund: CTB fließt seit #292 in Score, wird aber noch NICHT persistiert
  → ohne diesen PR keine CTB-Edge-Auswertung am 30.06. Sobald entry/CTB
  persistiert, schaltet S13 die jeweilige Zeile von „ungebaut" auf Counts.
- **FOLGE-PR Naming-Cleanup** (niedrig): IBKR_* → IBORROWDESK_*,
  STOCKANALYSIS_BORROW_ENABLED-Flag irreführend (Härtung sitzt hinter
  diesem Gate). Reine Umbenennung, Doku-Klasse.
- **Drop-Redundanz (aus #295)** — GitHub droppt ~20% der Cron-Slots;
  frühere Cron-Zeit (#295) löst NUR die Drift, NICHT die Drops. Echte
  Lösung: externer Trigger außerhalb GitHub Actions (Cloudflare-Worker
  analog quote-proxy, der den Daily-Run via workflow_dispatch anstößt,
  wenn der Cron-Slot ausbleibt). Roadmap, kein Druck. Verwandt mit
  externem Dead-Man-Switch (Sektion 5).
- **Doku-Backfill S8–S13** in CLAUDE.md/health_check_spec.md-Tabellen —
  die State-Invariants-Tabelle listet nur S1–S7 (S8–S13 fehlen, schon
  VOR heute lückenhaft). S13 hat additive Spec-Sektion, aber keine
  Tabellen-Zeile. Niedrig, optional, Auto-Merge-Klasse.
- **02.06.** Chart-Indikatoren (TTM Squeeze / VWAP-Distanz / OBV-Divergenz)
  als Entry-Score-Komponenten — NICHT im Setup-Score, nur Entry-Score ab 10.06.
- **10.06. ★★★ GROSSPROJEKT HÖCHSTE PRIORITÄT:** Entry-Timing-Modul Start.
  Entry-Score 0–100 pro Top-10-Kandidat, 5 Komponenten je 20%. Shadow-Mode
  zuerst, kein Push bis Entry-AUC ~30.06. Neues Modul entry_score.py
  (Pattern wie backtest_history.py). Pipeline-Andock in main() NACH
  apply_score_smoothing, VOR compute_earliness_pts. Schritt-Reihenfolge:
  (1) Persistenz Roh-Felder ✅ läuft (#259/#260/#279) | (2) 5 Normalisierungs-
  Funktionen (MANUELLER Merge) | (3) Persistenz-Spec entry_score + components
  + version (AUTO, additiv v4, KEIN v5) | (4) Aggregation 5×20% (MANUELL) |
  (5) Cockpit-Pillar (4. Pillar, Frontend+iPhone, MANUELL, RISIKO eng auf
  ~320px). MISSING-DEFAULTS: alle 5 fehlend → neutral 50. SHADOW-GARANTIE:
  Flag ENTRY_SCORE_PUSH_ENABLED=False, kein _send_-Sender. Sobald entry_score
  persistiert, schaltet S13 die Entry-AUC-Zeile automatisch von „ungebaut"
  auf Counts. NORMALISIERUNG: feste Caps starten, NICHT Perzentil (Daten zu
  dünn, n≥100 nötig). DESIGN-Diagnose 29.05.: si_trend_5d_slope (n=142,
  belastbarst) | rvol_acceleration Pareto cap 3.0 | score_delta_t1 schwach,
  klein gewichten | uoa_atm_ratio Schwellen ~0.75/1.5/2.5 (n=43) |
  anomaly_freshness 95% leer, schwach.
- **30.06.** Erste belastbare Backtest-Auswertung. V2-only ≥70-Bucket
  n≈100 (S13 trackt den Reife-Stand laufend). Re-Visit: Score ≥70 klare
  Edge in Trefferquote UND Mean-Return? Faktor-Vorzeichen re-prüfen. PLUS:
  finviz-Rückbau, Borrow-Fee-Entscheidung, UOA ATM-vs-Total-Entscheidung,
  Cap-vs-Perzentil für alle 5 Entry-Komponenten (auf ECHTEN Verteilungen
  dank #279-Rohfeldern). **ACHTUNG (neu): falls γ-2 bis dahin NICHT scharf,
  ist die Setup-Edge nur unbereinigt auswertbar — explizit dokumentieren.**
- **08.06.2026 (Rechner-Tag — NICHT mit Handy-Nachschauen verwechseln):**
  - **Backup-/Disaster-Recovery-Konzept** (read-only Diagnose) — was liegt
    NUR auf GitHub? Lokaler Clone? Daten-Export? Schwerpunkt nicht-
    aufholbare Daten (backtest_history.json, score_inflation_log.jsonl,
    score_history.json). Terminiert VOR 10.06.-Entry-Modul.
  - **Borrow-Persistenz-PR** (s.o.) + **Borrow-Naming-Cleanup** (s.o.).
- **UOA-Befund (entscheiden 30.06.):** uoa_atm_ratio strukturell eng
  berechnet (ATM-Band ±10%, nur Calls, nächste Expiration) → reale Werte
  max 2.46, obere Schwellen (ANOMALY_UOA_VOL_OI=10.0) unerreichbar →
  UOA-Anomaly-Push de facto tot. Entscheidung 30.06.: enge ATM behalten +
  rekalibrieren ODER auf Total-Vol/OI umbauen. Code vor 10.06. NICHT
  anfassen.
- **Card #10 — MERKREGEL:** Bei manuellem Dispatch → HTML-Sanity-CRIT →
  SOFORT das HTML-Artefakt aus dem Actions-Run ziehen, bevor es weg ist.
  Einzige fehlende Evidenz fürs #10-Mysterium. Cron-Runs sauber.
- **AMWD / yfinance-Falsch-Delisting beobachten:** 28.05. meldete yfinance
  AMWD „possibly delisted" trotz nachweislich handelbar (User bestätigt).
  Kein Delisting, yfinance-Schluckauf. Bei Muster diagnostizieren (greift
  Preis-Fallback oder steht Top-10-Kandidat mit $0.00 da?).
- **GitHub-Ticket #4418923 — AUFGEKLÄRT (29.05.):** 26.05.-Vorfall war ein
  GitHub-Actions-INCIDENT (resolved), KEIN Account-Lock/Abuse/Kompromittierung.
  Sicherheitsmaßnahmen waren vorsichtig-richtig, im Nachhinein nicht nötig.

## 5) STRATEGISCHE ROADMAP
- Entry-Timing-Modul (★★★, 10.06.) — höchste Priorität.
- γ-2 RVOL-Normalisierung (★, blockiert — s. Sektion 4). Vorbedingungs-
  Kette: Daten → Sweep → rel_volume_raw → Schwellen → Flip.
- Phasen-abhängige / perzentil-basierte Schwellen statt fester phasen-
  blinder Absolut-Schwellen (an 30.06. gekoppelt).
- Borrow-Fee + Utilization in score() (laut Literatur stärkste Squeeze-
  Prädiktoren) — Entscheidung 30.06.
- **Externer Trigger / Dead-Man-Switch außerhalb GitHub Actions** — deckt
  ZWEI Probleme: (1) Cron-Drops (~20%, #295-Diagnose) per Re-Dispatch,
  (2) Health-Check teilt das Failure-Fate der Pipeline (beim 26.05.-Vorfall
  schwieg der Wächter mit, weil die ganze Actions-Pipeline ausfiel). MUSS
  extern laufen (Cloudflare-Worker analog quote-proxy). Roadmap, kein Druck.
- γ-2-Pool-Inflation premarket: erst nach mehreren Werktagen echter
  premarket-Daten entscheidbar (ENABLED=False).
- Backup/Disaster-Recovery (Wiedervorlage 08.06.): (a) lokaler git mirror |
  (b) Daten-Export außerhalb GitHub | (c) Spiegel auf anderem Account
  (härtester Hack-Schutz).
- **Konsistenz-Wächter-Ausbau (Projekt C, Schicht 3):** S13-Dict heute
  3 Konstanten. Weitere stabile getattr-lesbare Flags additiv aufnehmbar,
  wenn sie die Aufnahme-Regel erfüllen (stabil + Schaden-bei-Drift).
  Crons/Literale bewusst draußen (S11/S12 + Provider-Health decken die ab).

## 6) CODE-HYGIENE-BACKLOG (mit Status)
- **Doku-Backfill S8–S13** in CLAUDE.md + health_check_spec.md-Tabellen
  (State-Invariants-Tabelle listet nur S1–S7) → OFFEN, niedrig, Auto-Merge.
- **finviz Flag-aus (FINVIZ_SCREENER_ENABLED=False) + α (Provider komplett
  rückbauen)** → OFFEN, an 30.06. gekoppelt. γ (Schwellen-Override 100)
  als Übergang gebaut. SF-Quote-Pfad ungated → bei α mitentfernen.
- **mock_test_digest.py 2 Fails** (Tier-2: „3-in-Folge nötig" + „coverage
  <50 counter/reset") → pre-existing auf origin/main, unabhängig von S13.
  Irgendwann anschauen, niedrig.
- v1/v2 → Jinja Template-Engine → OFFEN, niedriger Trading-Wert.
- Cockpit Stage 3 (.sb-Reste) → VERTAGT (.sb-conf-* live reused = #199-Falle,
  .sb-row/-num Rollback-Fallback).
- S10-Feiertags-Zähler (display-only) → an 30.06.-Decay-Fix koppeln.
- Großer generate_report.py-Split → VERWORFEN (globals-Falle).
- **Stale-Kommentar fetch_stockanalysis_borrow (gen._report.py:1608):**
  sagt „display-only", aber CTB fließt als Catalyst-Bonus. Redaktionell,
  Auto-Merge, niedrig.
- **Borrow-Naming-Cleanup** (niedrig, nach #292): IBKR_* → IBORROWDESK_*,
  STOCKANALYSIS_BORROW_ENABLED irreführend. Reine Umbenennung.

## 7) ARCHITEKTUR-ANKER
- Earliness V2 (DTC, AUC 0.77) | Phase-2 Exit komplett (6 Trigger) |
  Live-Polling Cloudflare-Worker quote-proxy.easywebb.workers.dev |
  Conviction-Schwelle 75 (#123) | Token AES-GCM+PBKDF2 (classic ghp_).
- run_phase steuert: normalize-Short-Circuit, Backtest-Append-Gate (nur
  postclose), anomaly_pushes (nur premarket).
- **"Echter Phasen-Run" nur via score_inflation_log nachweisbar:
  run_phase==trading_session_phase. date in backtest_history ist KEIN
  Beweis (Manual-Frühdispatch möglich).** (Basis für S11/S12.)
- S10-Loader filtert backtest_schema_version==4 (additiv halten!).
- backtest_history.py eigenes Modul seit #256 (Callable-Injection).
  Idempotenz-Key (ticker, report_date), report_date = heute Berlin (hart).
- return_5d-Fill = update_backtest_returns() in ki_agent.py:380 (stündlich,
  indexiert reale yfinance-Bars, idempotent).
- **S9-CRIT-Exit-Pfad (generate_report.py:16128) filtert STRIKT id=="S9".
  Neue crit-Checks (S12) blockieren NICHT. Bei Refactor id=="S9"-Filter
  UNBEDINGT beibehalten — niemals auf severity=="crit" allein umstellen.**
- Health-Check-Reihenfolge: fh.write(html) bei Z.15955 VOR S9-Check (16112).
- Provider-Schwellen: Default DIGEST_CONSECUTIVE_THRESHOLD=3, Override-Dict
  DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES={"finviz":100}.
- Service-Worker raus seit #188.
- **Cron-Inventar (KORRIGIERT 31.05.):** ki_agent `17 * * * *` (24/Tag,
  NICHT phasen-gated), daily premarket **`17 6 * * 1-5`** (war fälschlich
  noch 17 8 — toter Zwischenstand; 6:17 absorbiert Actions-Drift seit
  #295), daily postclose `17 21 * * 1-5`, health-digest `47 8 * * *`,
  watchlist `0 7 * * 0`. GitHub-Actions droppt ~20% der Vormittags-
  Slots + driftet variabel +1.8–5.76h — frühere Cron-Zeit absorbiert
  Drift, NICHT Drops (Drop-Redundanz offen, Sektion 4/5).
- **S8 misst seit #274 last_successful_run (ISO-Timestamp), NICHT mehr
  last_digest_sent (YYYY-MM-DD).** Exklusiv von health_check_digest.py:307
  geschrieben (per Test zementiert). last_digest_sent bleibt für
  _already_sent_today → Zwei-Felder-Architektur bewusst erhalten.
- **Health-Check-Schichten (Stand 31.05.):** S1–S7 State-Invariants |
  S8 Digest-Liveness | S9 HTML-Sanity (einziger CRIT-Block-Pfad) |
  S10 Daten-Integrität (MUSS/LAG/Auto-Detect v4) | S11/S12 Phasen-Sammel-
  Frequenz (premarket warn / postclose crit-reporting) | **S13 (neu) =
  Daten-Reife-Gate (#297, 30.06.-Stichproben laufend) + Konsistenz-Wächter
  (#298, Projekt C, Soll-Ist-Drift über CONSISTENCY_EXPECTED_STATE).**
- **Konsistenz-Wächter (Projekt C, seit #298):** CONSISTENCY_EXPECTED_STATE
  in config.py = Single-Source-Dict {RVOL_NORMALIZATION_ENABLED:
  EXPECTED_RVOL_NORMALIZATION, SCORE_NORMALIZATION_VERSION: 1,
  EARLINESS_FORMULA_VERSION: 2}. S13 (`_consistency_checks`, pure) liest
  IST live via getattr(config, name), warnt pro Drift. AUFNAHME-REGEL:
  nur stabile getattr-lesbare Konstanten mit Schaden-bei-stillem-Drift —
  KEINE Tunables (Conviction-Schwellen), Crons (→ S11/S12), Literale
  (schema_v==4 → AST nötig). γ-2-Kopplung: bei Flip RVOL + SCORE_
  NORMALIZATION_VERSION-Soll gepaart ziehen.
- **Borrow-Quelle = iBorrowDesk-JSON seit 01.06.** (IBKR-.php tot, #292).
  Eigener _BORROW_ACCT getrennt von _STOCKANALYSIS_ACCT (SI), eigene
  record_provider_call(provider="borrow")-Zeile. fee=0.0-Schutz
  (is not None). Persistenz noch offen (Folge-PR, Sektion 4).
- **Token-Session-Wrap (seit #281):** Nach Master-PW-Unlock Token
  AES-GCM-gewrappt in IndexedDB (Store squeeze_session, random Key,
  7-Tage-Rolling, fail-soft auf Master-PW-Modal). _tokPending ist FIFO-
  Queue, KEIN Single-Slot. _clearAllTokens MUSS IDB-Record mitlöschen.

## 8) LESSONS (31.05.2026)
- **Run grün + Feld voll ≠ Zustand korrekt (Fehlerklasse 3 „Zustands-
  Drift"):** Der γ-Fall — Pipeline lief grün, backtest_history-Felder
  voll, aber die ANNAHME „γ läuft" stimmte nicht (γ-2 nie gemergt,
  RVOL_NORMALIZATION_ENABLED=False). Kein bestehender Wächter (S1–S12
  prüfen Ausfälle/Lücken, nicht Erwartungs-Abgleich) hat das gemeldet.
  Antwort: Konsistenz-Wächter (Projekt C, S13) — deklarierte Soll-
  Zustände periodisch gegen IST abgleichen. Lehre: für jede stabile
  Annahme über den Config-Zustand, deren stiller Drift schadet, einen
  Soll-Haken setzen — getattr-lesbar, kein Soll-System.
- **Manuell-vs-Rechner-Tag NICHT mit Handy-Nachschauen verwechseln:**
  Diagnosen, die einen echten Werktags-Daily-Run / Actions-Log brauchen
  (Borrow-Coverage #292, premarket-Cron-Verlässlichkeit, S13-Live), sind
  am Wochenende / per Handy NICHT verifizierbar — der Sonntags-Lauf zeigt
  z.B. KEIN provider=borrow (kein Backtest-Pfad). Solche Verifikationen
  bewusst auf den ersten Werktags-Run datieren, nicht vorzeitig als
  „Defekt" werten.
- **Cron-Tuning absorbiert Drift, nicht Drops:** GitHub-Actions-Scheduler
  driftet variabel (+1.8–5.76h beobachtet) UND droppt Slots (2/10). Eine
  frühere Cron-Zeit (#295: 8:17→6:17) verschiebt das Drift-Fenster, aber
  ~20% Komplett-Drops bleiben — die brauchen einen externen Re-Dispatch-
  Trigger. „cron-Bug" war eine Fehldiagnose-Falle: der Ausdruck war
  korrekt, die Infra unzuverlässig (variabler Offset = nicht Zeitzone).
- **Diagnose-vor-Bau verhindert Phantom-Projekte:** Vor dem γ-2-Bau erst
  read-only geprüft, WAS überhaupt gemergt ist — Ergebnis: γ-2 existiert
  in keinem Commit/Branch, nur der γ-1-Marker. Ohne diese Diagnose wäre
  auf einer falschen Annahme („γ läuft schon") gebaut worden. Gleiches
  Muster bei Projekt C: erst Kandidaten-Inventar (stabil vs. volatil vs.
  nicht-lesbar), dann minimaler Erst-Umfang (3 statt „alles").
