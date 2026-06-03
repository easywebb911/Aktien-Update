# SESSION_HANDOVER.md — Stand 03.06.2026

## 1) HEUTE IMPLEMENTIERT (mit Hashes)
*(Sammelt 01.06.-Nachtrag → 03.06., chronologisch.)*
- **#307 (Merge c92a4a6) — 01.06.** Handover-Nachtrag #306. Doku, Auto-Merge.
- **#308 (Merge aa848c4) — 01.06.** Borrow-Verifikation #292 als erledigt
  markiert (5 Läufe grün). Doku, Auto-Merge.
- **#309 (Merge e496fbc) — 02.06.** **CTB-Persistenz ins backtest_history.**
  `cost_to_borrow` additiv in `_build_backtest_extension` (Z. 447) + config
  `S10_OBSERVED_FIELDS`. `backtest_schema_version` BLEIBT 4 (kein v5-Bump —
  S10-Loader filtert ==4). None-tolerant (Smallcaps ohne iBorrowDesk).
  Schließt die CTB-Edge-Auswertungs-Vorbedingung. Manueller Merge.
- **#310 (Merge 75a3505) — 02.06.** **`last_successful_gist_pull`-Marker
  (Schritt 1/2).** Neuer State-File `gist_pull_state.json` +
  `_mark_successful_gist_pull` (atomic, fail-soft), AUSSCHLIESSLICH im
  HTTP-Gist-Erfolgszweig von `pull_gist_data.py`. Beide Workflows: `git add
  gist_pull_state.json`. KEIN Health-Check (das war S14, Schritt 2/2 →
  #314). Manueller Merge.
- **#311 (Merge 1459425) — 03.06.** **Dynamische Datenquellen-Anzeige.**
  Methodik-Panel-Liste aus `config.DATASOURCE_LABELS` (Label-Map) +
  `health_check.provider_liveness` (live/stale/disabled aus
  `provider_health.jsonl` + ENABLED-Flags). iBorrowDesk aufgenommen,
  Sektor-ETFs ganz raus, tote Quellen auto-„(aus)/(aktuell keine Daten)".
  Fail-soft auf statisches Fallback-HTML. REIN ANZEIGE. Manueller Merge.
- **#312 (Merge 5828f7ab, Head b7dfd84) — 03.06.** **Outer-Page-Golden-File-
  Test.** `scripts/mock_test_outer_page_golden.py` + committetes
  `tests/golden/report_outer_page.html` (~398 KB). Schnitt ab `<body>`
  (head.jinja-CSS raus, body-`<style>` + JS-Block drin). Fixed-Clock-
  Monkeypatch + Fixtures, NULL Masking. `UPDATE_GOLDEN=1` regeneriert.
  Manueller Merge.
- **#313 (Merge c478e181) — 03.06.** Backtest-Panel-Meta: „… davon N neue
  Einträge". N = Einträge mit jüngstem `date` im daily-Subset (Variante 1,
  datengetrieben, kein Storage). Basis == nDay (voller daily-Bestand,
  `source !== 'bootstrap'`), date `DD.MM.YYYY` parse-sicher nach YYYYMMDD.
  Reine Anzeige, Auto-Merge.
- **#314 (Merge 4deee5a4, Commit 32994a1a) — 03.06.** **S14 Gist-Pull-
  Liveness-Wächter (Schritt 2/2).** Liest `last_successful_gist_pull` →
  **WARN@26h, EINSTUFIG** (`HEALTH_CHECK_S14_MAX_AGE_HOURS=26`, eigene
  Konstante). **None-tolerant** (Datei fehlt / Feld null/unparsbar → SKIP,
  exakt analog S8). **Beide Pfade** (ungated wie S8 → ki_agent-Tick liest
  alten Working-Tree-Marker bei Pull-Fail → ~1h Detektionslatenz statt 1 Tag).
  **COMPOSITE-Liveness:** Detail „Gist-Pull seit N h nicht erfolgreich",
  NICHT „Token tot" (altert auch bei mehrtägigem Cron-Drop). Schließt
  Stille-Tod-Klasse 02.06. (toter GIST_TOKEN → Recovery-Fallback → Geister-
  Positionen). Kanonischer Helper `_iso_marker_age_hours`; `_digest_age_hours`
  (S8) UNANGETASTET (test_12-Source-Contract). 17/17 Tests, Regression grün.
  `pull_gist_data.py` nur Verweis-Kommentar. Manueller Merge.
- **#315 (Merge 26c034c4) — 03.06.** Backtest-Meta-Datums-Anker: „davon N
  neue Einträge **(DD.MM.)**". Datum aus DEMSELBEN `_maxKey`, gegen den N
  filtert (ein Weg, konsistent). **Golden mit-regeneriert** — und dabei
  #313s un-goldenten `_dailyNewSuffix`-Block absorbiert (war im #312-Golden
  nicht drin, weil #313 ohne Golden-Update gemergt → keine PR-CI lief je
  automatisch; bei #315 entdeckt). 1 Hunk im `_btRender`-Block, Rest byte-
  identisch. Auto-Merge.
- **#316 (Merge d1c0b697, Commits 9a1f0868 + 32ba95dc) — 03.06.** **Advisory
  PR-CI.** `.github/workflows/pr-checks.yml` (`on: pull_request`) fährt 5
  deterministische Checks: 4 Lints + Outer-Page-Golden-Test. **ADVISORY**
  (kein required, keine Branch-Protection, `permissions: contents: read`) →
  liefert `check_run`-Signal, blockiert Self-Merge NICHT. **Erstlauf rot**
  (`pip install -r requirements.txt` zog pandas_ta → dessen
  `find_spec("yfinance")` auf dem yfinance-Stub mit `__spec__=None` →
  `ValueError`, nicht vom `except ImportError` gefangen). **Fix 32ba95dc:**
  nur `pip install "jinja2>=3.1.0"` (einziger harter Modul-Level-Dep) →
  pandas_ta absent → ta=None-Pfad, identisch zur Golden-Generierung →
  **grün, alle 5 Checks liefen** (Run #26894466489). CLAUDE.md-Regel für
  output-ändernde PRs ergänzt. Manueller Merge.

## 2) AKTIVE POSITIONEN
*(Stand unverändert seit 01.06 — keine neuen Open/Close-Aktionen diese Session.)*
- **AMC** — Halt-Strategie, `no_exit_alerts=true`. Conv 4, Setup stark
  gefallen. Trailing-Stop −10.2% vom Hoch, score 34. Bewusst gehalten.
- **IONQ** — Conv 25, score 7, pnl +33.2%. Exit-Mechanik flaggt, kein
  Exit-Treiber. Schließung = Chart-/Bauchgefühl-Call.
- Watchlist (6): PDYN, AI, GEMI, CRMD, IONQ, AMC.
- Zuletzt geschlossen (im Journal): INDI +23.1% (22→28.05), CRDF +1.7%
  (19→28.05, ≥70-Bucket-Datenpunkt), RR +11.5% (26.05.).

## 3) VERIFIKATION MORGEN/OFFEN
- **★ S14 (#314) erstmals live:** im nächsten Health-Check-Digest die
  **S14-Zeile** prüfen — bei frischem `gist_pull_state.json`-Marker (ki_agent
  schreibt ihn stündlich) muss S14 **OK** (kein WARN) sein. WARN nur, wenn
  der Marker > 26 h altert. Aktueller Marker (`14:07Z`) ist frisch → S14
  sollte schweigen.
- **★ Backtest-Meta (#313+#315) nach nächstem Report:** im Panel die Zeile
  „… N daily (live gemessen, davon M neue Einträge (DD.MM.))" — M + Datum
  müssen dem jüngsten daily-`date` entsprechen (heute: 10 @ 03.06.).
  iPhone-Sicht nach Daily-Run-Deploy.
- **★ PR-CI (#316) bei nächstem PR:** der erste fremde output-ändernde PR
  zeigt, ob der `check_run` zuverlässig grün/rot liefert. Bereits an #316
  selbst grün-belegt (alle 5 Checks liefen, Run #26894466489).
- **#311 Datenquellen-Anzeige:** nach Daily-Run das Methodik-Panel auf
  iPhone — tote Quellen als „(aus)/(aktuell keine Daten)", iBorrowDesk
  gelistet, kein f-String-Bruch.
- **#309 CTB-Persistenz:** sobald der nächste postclose-Eintrag geschrieben
  ist, hat backtest_history ein `cost_to_borrow`-Feld (None bei Nicht-US/
  Smallcap) → S13 schaltet die CTB-Edge-Zeile von „ungebaut" auf Counts.
- **Borrow-Reparatur (#292) — ✅ VERIFIZIERT (01.06.):** `provider="borrow"`
  grün über 5 Läufe, coverage 100, echte CTB in app_data. (Beleg
  provider_health.jsonl.)
- **report_date→ET (#304) — live seit 01.06.,** an Drift-Tagen prüfen, dass
  S1/S4 nicht fälschlich feuern (ET-Achse konsistent).
- **Backend/Daten-PRs** (#309/#314) → Actions-Log/Digest-Sichtung, kein
  iPhone-UI-Verify. **Frontend-PRs** (#311/#313/#315) → iPhone nach Deploy.

## 4) GEPLANTE AUFGABEN + WIEDERVORLAGEN (mit Daten)
### Health-Check-Härtung — abgeschlossen
- **S14 Schritt 2/2 (#314) ERLEDIGT.** Die Gist-Stille-Tod-Klasse (02.06.)
  ist jetzt überwacht. **Restkante bewusst offen (separater PR):** Body-
  Korruption — HTTP-200 + kaputtes `squeeze_data.json` → `_extract_data`
  kollabiert still auf `{}` → Marker fälschlich frisch. Andere Fehlerklasse
  als Token-Tod; `_extract_data` unberührt gelassen.

### Borrow-Stränge
- **CTB-Persistenz (#309) ERLEDIGT.** CTB fließt jetzt ins backtest_history
  (Feld `cost_to_borrow`, v4, S10_OBSERVED). Damit ist die CTB-Edge-
  Auswertung daten-seitig freigeschaltet (reift über kommende Einträge).
- **B — Borrow-Coverage-Wächter: JETZT BAUBAR.** Vorbedingung ✅ (Borrow grün
  coverage 100 % über 5 Läufe). Schwelle auf bestehende `provider=borrow`-
  coverage in `aggregate_provider_fails` (Tier-2-Konsekutiv-Logik existiert).
  KRITISCH: legitime Smallcap-Pool-Ticker, die iBorrowDesk nicht kennt,
  drücken coverage ECHT → Schwelle muss „Provider tot" von „Pool-Smallcap-
  Lücke" trennen (success_check `cost_to_borrow is not None` + eigener
  `_BORROW_ACCT` seit #292 sind die Basis).
- **Borrow-Naming-Cleanup** (niedrig, nach #292): `IBKR_*` → `IBORROWDESK_*`,
  `STOCKANALYSIS_BORROW_ENABLED` irreführend. Reine Umbenennung.

### Annahmen-Inventur (durchgeführt 01.06., Funde tragen weiter)
- **Split-Labels → GEFIXT (#303).** entry_price-Adjust-Epoche vs. Forward-
  Closes → split-konsistente Basis (`_close_at(0)`).
- **Datums-Attribution → GEFIXT (#304).** Berlin-Mitternachts-Drift →
  ET-Kopplung + 10-Einträge-Korrektur.
- **Score-Versionsmarker → git-verifiziert (unshallow).** KEINE `score()`-
  Änderung 14.–28.05.; einzige v4-Score-Änderung = #292 Borrow (nur
  `borrow_rate>50%`). **Auswertungs-Lösung:** borrow-teure Ticker separat
  behandeln, KEIN Versionsmarker nötig.
- **or-0-Defaults → im v4-Sample 0 Fälle.** Persist-only-None-Fix wäre
  risikolos (Score-Input getrennt), nur bei Bedarf.

### Auswertungs-Regeln (reife-getriggert, NICHT fixer „30.06."-Termin)
Bei erster reifer ≥70-Auswertung: (a) **borrow-teure Ticker (`borrow_rate>50`)
separat** (eigene Score-Def seit #292), (b) bei SF/SI-Analyse `source=none`
**ausfiltern**, (c) **Lücke 28.05.** dokumentieren (Backfill nur partiell).

### Offene Stränge
- **★ γ-2 (RVOL-Normalisierung) — BLOCKIERT, eigenes Projekt.** 4 Vorbedingungen:
  (a) premarket-Datenbasis zu dünn, (b) Cron-Drift absorbiert (#295), Sammlung
  über nächste Werktage, (c) `rel_volume_raw`-Feld UNGEBAUT, (d) Skalierer
  0.10/0.40 ungestützt. Reihenfolge: Daten → Sweep → rel_volume_raw →
  Schwellen → Flip. **Kopplung:** bei Aktivierung BEIDE Soll in
  `CONSISTENCY_EXPECTED_STATE` paaren (EXPECTED_RVOL_NORMALIZATION→True UND
  SCORE_NORMALIZATION_VERSION-Soll→2), sonst S13-Drift.
- **02.06.** Chart-Indikatoren (TTM Squeeze/VWAP/OBV) als Entry-Score-
  Komponenten — nur Entry-Score ab 10.06., NICHT Setup-Score.
- **08.06. (Rechner-Tag):** Backup-/Disaster-Recovery-Diagnose (read-only) —
  nicht-aufholbare Daten (backtest_history.json, score_inflation_log.jsonl,
  score_history.json). VOR 10.06.-Entry-Modul.
- **10.06. ★★★ GROSSPROJEKT HÖCHSTE PRIORITÄT:** Entry-Timing-Modul Start.
  Entry-Score 0–100, 5 Komponenten je 20%. Shadow-Mode
  (`ENTRY_SCORE_PUSH_ENABLED=False`), kein Push bis Entry-AUC reif. Neues
  Modul `entry_score.py` (Pattern wie backtest_history.py). Andock in main()
  NACH apply_score_smoothing, VOR compute_earliness_pts. Schritte: (1)
  Persistenz Roh-Felder ✅ (#259/#260/#279) | (2) 5 Normalisierungs-Funktionen
  (MANUELL) | (3) Persistenz-Spec (AUTO, additiv v4, KEIN v5) | (4) Aggregation
  5×20% (MANUELL) | (5) Cockpit-Pillar (Frontend+iPhone, eng auf ~320px).
  MISSING-DEFAULTS: alle 5 fehlend → neutral 50. NORMALISIERUNG: feste Caps
  starten, NICHT Perzentil (Daten zu dünn). Sobald persistiert → S13 Entry-
  AUC-Zeile auf Counts.
- **UOA-Befund:** uoa_atm_ratio strukturell eng (ATM-Band/Calls/nächste
  Expiration) → reale max 2.46, `ANOMALY_UOA_VOL_OI=10.0` unerreichbar → UOA-
  Push de facto tot. Enge ATM rekalibrieren ODER auf Total-Vol/OI umbauen.
  Code vor 10.06. NICHT anfassen.
- **Drop-Redundanz (aus #295):** GitHub droppt ~20% der Cron-Slots; frühere
  Cron-Zeit löst NUR Drift, NICHT Drops. Echte Lösung: externer Trigger
  (Cloudflare-Worker). Roadmap.
- **Card #10 MERKREGEL:** bei manuellem Dispatch → HTML-Sanity-CRIT → SOFORT
  HTML-Artefakt aus dem Actions-Run ziehen.
- **AMWD / yfinance-Falsch-Delisting beobachten:** 28.05. „possibly delisted"
  trotz handelbar. Bei Muster diagnostizieren.
- **MEMORY-HYGIENE:** Memory voll (30/30). Konsolidieren — #21–#24 (Entry-
  Modul) verdichten. Nach Meilensteinen löschbar.

## 5) STRATEGISCHE ROADMAP
- Entry-Timing-Modul (★★★, 10.06.) — höchste Priorität.
- γ-2 RVOL-Normalisierung (★, blockiert — s. §4).
- **Annahmen-Inventur als wiederkehrende Methode** — systematisches
  Durchleuchten dunkler Ecken (Datengrundlage, stille Defaults, Versions-
  Drift) statt reaktivem Stolpern. Eigene Sitzung pro Runde.
- Phasen-abhängige / perzentil-basierte Schwellen statt fester Absolut-
  Schwellen (an Daten-Reife gekoppelt).
- Borrow-Fee + Utilization in score() (stärkste Squeeze-Prädiktoren) —
  Entscheidung bei reifer CTB-Coverage (Persistenz #309 jetzt da).
- **Externer Trigger / Dead-Man-Switch außerhalb GitHub Actions** — deckt
  Cron-Drops (~20%) per Re-Dispatch UND das Failure-Fate-Problem. MUSS extern
  laufen (Cloudflare-Worker).
- Backup/Disaster-Recovery (Wiedervorlage 08.06.): lokaler git mirror |
  Daten-Export außerhalb GitHub | Spiegel auf anderem Account.
- Konsistenz-Wächter-Ausbau (Projekt C, S13): heute 3 Konstanten; weitere
  stabile getattr-lesbare Flags additiv (Regel: stabil + Schaden-bei-Drift).
- **PR-CI-Ausbau (neu, #316):** die advisory CI fährt heute 5 Checks. Volle
  86-Test-Suite später inkrementell aufnehmen — eigener Entscheid, erst
  Hermetik-Triage (welche Tests sind netzfrei/deterministisch).

## 6) CODE-HYGIENE-BACKLOG (mit Status)
- **★ actions/checkout@v4 → v5** (neu, niedrig): Node-20-Deprecation, GitHub
  zwingt ab **16.06.2026** auf Node 24. `pr-checks.yml` + alle Cron-Workflows
  nutzen `@v4`. Mini-PR VOR 16.06. (rein vorausschauend, heute kein Problem,
  Runs grün).
- **★ rsi14=None-Render-Zweig** (neu, niedrig): Golden-Test deckt nur den
  Nicht-None-rsi14-Render (Fixture 61.0). Den `rsi14=None`-Zweig als zweite
  Fixture abdecken — Fixture-Abdeckung, unabhängig von pandas_ta.
- **★ Volle 86-Test-Suite in CI** (neu, niedrig): heute fährt #316 nur Golden
  + 4 Lints. Inkrementell erweitern nach Hermetik-Triage (eigener Entscheid).
- **CTB-Persistenz** → ERLEDIGT (#309).
- **Doku-Backfill S8–S13** → ERLEDIGT (#300/#301).
- **mock_test_digest 2 Fails** → ERLEDIGT (#302).
- **or-0-Defaults Persist-Fix** (dtc/rvol/Bonus → None) → OFFEN, niedrig, NUR
  bei Bedarf (v4-Sample heute 0 Fälle). Persist-only, kein Score-Touch.
- **finviz Flag-aus + α (Provider rückbauen)** → OFFEN, an Daten-Reife
  gekoppelt. SF-Quote-Pfad ungated.
- v1/v2 → Jinja → OFFEN, niedriger Trading-Wert. (Golden-Test #312 ist
  jetzt das Sicherheitsnetz für eine spätere Migration.)
- Cockpit Stage 3 (.sb-Reste) → VERTAGT (.sb-conf-* live reused).
- S10-Feiertags-Zähler (display-only) → an Decay-Fix koppeln.
- Großer generate_report.py-Split → VERWORFEN (globals-Falle).
- **Stale-Kommentar fetch_stockanalysis_borrow (Z.1608):** sagt „display-only",
  CTB fließt aber als Catalyst-Bonus. Redaktionell, Auto-Merge, niedrig.

## 7) ARCHITEKTUR-ANKER
- **★ PR-CI advisory (NEU, #316):** `.github/workflows/pr-checks.yml`,
  `on: pull_request`, fährt 4 Lints + Outer-Page-Golden. **ADVISORY** —
  KEIN required-status-check, KEINE Branch-Protection (eine Workflow-Datei
  kann sich nicht required machen; required ist eine Repo-Settings-Sache,
  unangetastet). Liefert `check_run`-Signal, blockiert Self-Merge NICHT.
  Install = **nur `jinja2>=3.1.0`** (NICHT requirements.txt — pandas_ta würde
  via `find_spec("yfinance")` am yfinance-Stub `__spec__=None` crashen). Der
  einzige PR-triggernde Workflow; Cron-Workflows unverändert (nur
  schedule/dispatch/push-to-main).
- **★ Outer-Page-Golden (NEU, #312):** `tests/golden/report_outer_page.html`
  ist ein **Render-LOGIK-Netz mit fixen Fixtures**, KEIN Produktions-Daten-
  Abbild. Render-Pfad ist **pandas_ta-invariant** (`_HAS_PANDAS_TA` nur in
  den Fetch-Funktionen `get_yfinance_data`/`_compute_indicators` gelesen, nie
  in `_card`/`generate_html_v1`). Bei output-änderndem PR: Golden-Test lokal +
  `UPDATE_GOLDEN=1` + Golden mit-committen (CLAUDE.md-Regel).
- **★ S14 Gist-Pull-Liveness (NEU, #314):** liest `last_successful_gist_pull`
  (`gist_pull_state.json`, geschrieben NUR im HTTP-Gist-Erfolgszweig von
  `pull_gist_data.py`, #310). WARN@26h, einstufig, None-tolerant (SKIP),
  beide Pfade. COMPOSITE-Liveness (Token-Tod ODER Cron-Drop). Kanonischer
  Parser `_iso_marker_age_hours`; `_digest_age_hours` (S8) behält seine
  Inline-Kopie (test_12-Source-Contract — bei Refactor beachten).
- **★ CTB im backtest_history (NEU, #309):** Feld `cost_to_borrow`, additiv,
  v4 (KEIN v5), S10_OBSERVED (kein MUSS/LAG → kein Smallcap-None-WARN).
- **★ Datenquellen-Anzeige dynamisch (NEU, #311):** `DATASOURCE_LABELS`
  (config, manuelle Label-Map) + `provider_liveness` (health_check, Status
  dynamisch). Bei neuer/entfallener Quelle nur die Map ändern.
- Earliness V2 (DTC, AUC 0.77, wirkt NUR via Conviction — NICHT Setup-score) |
  Phase-2 Exit komplett (6 Trigger) | Live-Polling Cloudflare-Worker
  quote-proxy | Conviction-Schwelle 75 | Token AES-GCM+PBKDF2.
- run_phase steuert: normalize-Short-Circuit, Backtest-Append-Gate (nur
  postclose), anomaly_pushes (nur premarket).
- **report_date + _today_iso = US-Eastern (`America/New_York`) seit #304.**
  Beide MÜSSEN derselben ET-Achse folgen. Header-Timestamp nutzt eigene
  Berlin-ZoneInfo (von der Datums-Achse unabhängig).
- **backtest-T+0-Return-Basis = `_close_at(0)` seit #303** (eine Adjust-
  Epoche, split-konsistent). entry_price-Feld bleibt (Display), nicht mehr
  Return-Basis.
- **„Echter Phasen-Run" nur via score_inflation_log:
  run_phase==trading_session_phase.** Basis für S11/S12.
- S10-Loader filtert `backtest_schema_version==4` (additiv halten!) +
  Wochenend-Filter.
- backtest_history.py eigenes Modul seit #256 (Callable-Injection,
  Idempotenz-Key (ticker, report_date)).
- **S9-CRIT-Exit-Pfad filtert STRIKT id=="S9".** Neue crit-Checks (S12)
  blockieren NICHT. Bei Refactor beibehalten.
- **S8 misst seit #274 last_successful_run (ISO), NICHT last_digest_sent.**
- **Health-Check-Schichten (Stand 03.06.):** S1–S7 State-Invariants | S8
  Digest-Liveness | S9 HTML-Sanity (einziger CRIT-Block-Pfad) | S10 Daten-
  Integrität (v4) | S11/S12 Phasen-Sammel-Frequenz | S13 Daten-Reife-Gate
  (#297) + Konsistenz-Wächter (#298) | **S14 Gist-Pull-Liveness (#314)**.
  Tabellen in CLAUDE.md + spec vollständig **S1–S14**. S2/S3/S6/S8/S14 in
  BEIDEN Pfaden, Rest nur Daily-Run.
- **Konsistenz-Wächter (Projekt C, #298):** CONSISTENCY_EXPECTED_STATE-Dict.
  S13 liest IST via getattr(config,name), warnt pro Drift. Nur stabile
  Konstanten mit Schaden-bei-Drift.
- **Borrow-Quelle = iBorrowDesk-JSON seit #292.** Eigener _BORROW_ACCT.
  fee=0.0-Schutz (is not None). **Persistenz jetzt da (#309).**
- **Token-Session-Wrap (#281):** AES-GCM in IndexedDB (7-Tage-Rolling).
- Cron-Inventar: ki_agent `17 * * * *`, daily premarket `17 6 * * 1-5`,
  postclose `17 21 * * 1-5`, health-digest `47 8 * * *`, watchlist `0 7 * * 0`.
  **Plus: pr-checks `on: pull_request` (kein Cron, #316).**
- **Workflow-Lint-Gate = 4 Lints (seit #306):** chat_template, jsformat_escape,
  score_confidence_isolation, token_crypto. Im Daily-Workflow vor Deploy UND
  jetzt zusätzlich in der advisory PR-CI (#316).
- **squeeze-guardian (#306):** echo-Hook spawnt Agent NICHT. Krypto-Teil =
  Lint (automatisiert); Architektur-Teil = manuelle Modell-Urteil-Routine.

## 8) LESSONS (03.06.2026)
- **CI-Env ≠ local-Env schlägt in BEIDE Richtungen zu (#316):** Meine Sandbox
  hat pandas_ta NICHT → Golden lief lokal grün. Der Runner hatte es (via
  requirements.txt) → `find_spec("yfinance")` auf dem spec-losen Stub →
  ValueError → rot. Der Reflex „requirements.txt für Sicherheit" hat das
  Flaky ERST erzeugt; die Minimal-Deps-Vorgabe war richtig. Lehre: nicht nur
  „local grün" als Beweis nehmen — der erste echte Runner-Lauf ist die
  Wahrheit, und Env-Divergenz kann in BEIDE Richtungen brechen.
- **Golden = Render-LOGIK-Netz, kein Produktions-Daten-Abbild:** Der Golden
  testet mit FIXEN Fixtures die Render-Logik (f-String/JS/Struktur), nicht
  Produktions-Werte. pandas_ta beeinflusst nur Daten-WERTE (rsi14), nie
  Render-LOGIK (`_HAS_PANDAS_TA` lebt allein in der Fetch-Phase). Darum ist
  der ta=None-Golden byte-gleich zum CI-Render und es gibt KEINE Golden-
  Produktions-Divergenz. Bei „testet mein Test wirklich das, was ich denke?"
  immer fragen: testet er Logik (fix) oder Daten (variabel)?
- **Stilles Netz reißt unbemerkt ohne Automatik (#313→#315→#316):** #313
  änderte den Output, das Golden wurde nicht mit-aktualisiert — und weil
  KEIN Workflow den Golden-Test je automatisch fuhr, fiel es erst bei #315
  auf. Ein lokal-only-Test ist nur so gut wie die Disziplin, ihn zu fahren.
  Lehre: ein Regressionsnetz ohne automatischen Auslöser ist ein
  Schrödinger-Netz. #316 (advisory CI) + die CLAUDE.md-Pflichtregel schließen
  die Klasse strukturell — und die CI lieferte in ihrem ALLERERSTEN Einsatz
  bereits Wert (fing die pandas_ta-Inkompatibilität).
- **Beim Golden-Regenerieren NIE blind übermalen (#315):** Vor `UPDATE_GOLDEN`
  den Diff prüfen — #315 zeigte +33/−2 statt der erwarteten 1 Zeile, weil
  #313s Block fehlte. Erst verstehen WARUM der Diff größer ist (legitim:
  un-goldenter #313-Code), dann committen. Ein Golden-Netz, das man blind
  übermalt, ist wertlos.
- **Composite-Liveness ehrlich benennen (#314):** S14 altert bei Token-Tod
  UND bei Cron-Drop — zwei Fehlerklassen. Der Detail-Text sagt darum „Gist-
  Pull seit N h nicht erfolgreich", NICHT „Token tot". Einen Wächter nicht
  schärfer behaupten lassen als er messen kann.
- **Pre-existing Test-Contracts respektieren (#314):** `_digest_age_hours`
  (S8) wurde NICHT zum gemeinsamen Helper umgebaut, weil test_12 die Funktion
  per Source-Inspektion an `state.get("last_successful_run")` im eigenen Body
  bindet. Der neue Parser ist ein SEPARATER `_iso_marker_age_hours` — S8 bleibt
  byte-gleich, Zero-Risk. Lehre: vor einem „sauberen" Refactor prüfen, ob ein
  Test die alte Form per Source-Inspektion festnagelt.
