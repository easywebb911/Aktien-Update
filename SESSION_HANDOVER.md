# SESSION_HANDOVER.md — Stand 07.06.2026

## 1) HEUTE IMPLEMENTIERT (mit Hashes)
*(Session 06.–07.06. Hashes aus `git log` auf main, verifiziert. Roter Faden:
zuerst die Test-Suite ehrlich + automatisiert machen (CI-Gate), dann der
Kern-Meilenstein **Entry-Score Shadow** — 3 Tage vor Plan.)*

- **#329 (Merge `c2b38921`) — 06.06.** **Schema-Tripwire-Fix.**
  `cost_to_borrow` fehlte in `_test_extended_schema`-`expected_keys`, obwohl
  Prod es schreibt (backtest_history.py) + S10 es kennt → stale Selbsttest
  (rot). Fix: 1 Key additiv. Stellt die Tripwire als scharfen Schema-Wächter
  für den Entry-Bau wieder her (Rot-auf-Rot-Maskierung weg). Manueller Merge.
- **#330 (Merge `bbe23ca3`) — 06.06.** **5 stale Reds → Prod-Ist.**
  digest-cron `21 8`→`47 8`, claude_md_pr_status (post-#316-Text), stocktwits-
  Stub (18.05.-deaktiviert), provider_health_tier3 + card_cockpit_stage1
  (AST-/Harness-robust). Alle als stale bewiesen (Prod korrekt, Test hinkte).
  Test-only, self-merge.
- **#331 (Merge `9988ab23`) — 06.06.** **★ Golden-Liveness-Stub.**
  `outer_page_golden` flippte im Wochenrhythmus, weil `_datasource_rows_html`
  echte `provider_health.jsonl`-Liveness liest (FINRA Wochenend-Stille). Fix:
  Harness stubbt `health_check.provider_liveness` → data-unabhängig. Beweis:
  grün gegen FINRA-still/live/leer. Test-only, self-merge.
- **#332 (Merge `d70c03c8`) — 06.06.** **★ tier2 AST-Härtung.** Die 5
  verbliebenen `_block_around`-String-Gating-Checks (finra run_phase, finnhub/
  stockanalysis emit, ew nan_pct) auf AST-Anker (kwarg / enclosing-if-Segment).
  Zähne-Beweis: feuert noch bei echtem Verstoß. Test-only, self-merge.
- **#333 (Merge `a4d51322`) — 06.06.** **★ CI-Gate Phase 1.** 3 Tests
  (gist_action_token_routing, provider_health ×2) als Einzel-Steps in
  `pr-checks.yml`. Manueller Merge.
- **#334 (Squash `897fdafe`) — 06.06.** **health_check datums-stabil.**
  `run_and_record`-Test fuhr echte S1-S14 gegen reale State-Dateien → am
  Wochenende rot (S8/S11/S12/S14). Fix: State-Quellen auf Tempfile-Fixtures
  + `now_utc` fixiert (analog #331). Zähne erhalten. Test-only, self-merge.
- **#335 (Merge `576dd3ff`; Squash `62bd435a`) — 06.06.** **★ CI-Gate Phase 2 —
  Allowlist-Runner.** `scripts/run_ci_mock_tests.py` bündelt die Kategorie-A-
  Tests in EINEM Step (ersetzt die 4 Einzel-Mock-Test-Steps). **Drift-Guard**
  (failt bei unklassifiziertem Test). Allowlist **76** (3 requests-Tests
  TEMP-EXCLUDED — Sandbox≠CI-Lehre). Manueller Merge.
- **#336 (Merge `39e9b62e`; Squash `cef9b617`) — 07.06.** **★★★ ENTRY-SCORE
  SHADOW-MODE (Kern-Meilenstein, 3 Tage vor Plan).** Neues pures Modul
  `entry_score.py`: 5 Komponenten → 0–100-Score je Top-10-Kandidat, im
  postclose-Backtest-Append berechnet + persistiert. **KEIN Push, keine
  Anzeige, kein Score-/Filter-Effekt.** Guardian ✅. Allowlist 76→**77** (neuer
  `mock_test_entry_score`). Manueller Merge.

## 2) AKTIVE POSITIONEN
**Quelle: `app_data.json`-Positions-Mirror (`run_phase=postclose`,
`generated 2026-06-07T05:34Z`) — der private Gist (kanonisch) ist im Sandbox
NICHT direkt lesbar (kein `GIST_ID`/`GIST_TOKEN`). Stand = letzte Daily-Run-
Materialisierung → bei Abweichung Gist gewinnt.** 9 offene Positionen:

| Ticker | Entry | Shares | no_exit_alerts |
|---|---|---:|---|
| **AMC** | 01.05. @ 1.50 | 500 | **True** (Hold) |
| **IONQ** | 11.05. @ 49.10 | 40 | False |
| **CRMD** | 14.05. @ 7.93 | 8 | False |
| **GEMI** | 18.05. @ 5.40 | 18 | False |
| **PDYN** | 20.01.2025 @ 11.52 | 150 | False |
| **AI** | 01.06. @ 11.00 | 10 | **False** (bewusst) |
| **RBOHF** | 03.06. @ 0.67 | 1300 | False |
| **LFVN** | 05.06. @ 9.06 | 10 | False |
| **GIII** | 05.06. @ 33.71 | 4 | False |

**AI:** Exit-Pushes bewusst akzeptiert (Hold-These Siebel, kein `no_exit_alerts`-
Flag) — kein To-do. Nur AMC trägt das Hold-Flag.

## 3) VERIFIKATION MORGEN (Mo 08.06., erster Handelstag)
- **★★ Erster Entry-Score live** im postclose-Run: in `backtest_history.json`
  prüfen, dass neue Einträge `entry_score` (0–100 oder None), `entry_components`
  (5er-Dict), `entry_n_components` (0–5) und `push_history_available` (bool)
  tragen — rein Shadow (kein Push/Anzeige).
- **FINRA-SSR-Recovery:** die Wochenend-Stille war transient (kein Reg-SHO-File
  Sa/So). Mo wieder healthy in `provider_health.jsonl` (`finra` http=200)?
- **Wochenend-Digest-Fails** (S3 current_price, S7 agent_signals-Drift) von
  selbst aufgelöst nach dem ersten sauberen Mo-Run?
- **Screener-Pool-Floor (#325):** item_count im Normalbereich (~160–239),
  Floor=120 feuert NICHT fälschlich.

## 4) GEPLANTE AUFGABEN + WIEDERVORLAGEN (mit Daten)
- **10.06. — ursprünglicher Entry-Start: KERN FERTIG (#336, 3 Tage früher).**
  Offen NUR noch **Cockpit-Pillar** (Entry-Score-Anzeige im Frontend, eigener
  PR, iPhone-Verify) — **kein Zeitdruck** (erst Daten sammeln, s. §5).
- **30.06. — Backtest-Auswertung (erweitert):**
  - Setup-Score ≥70-Edge (schema_v4) · Earliness-Konfidenz-Re-Test (AUC) ·
    Conviction-Methodik-Diagnose.
    - **Freitag-Cluster-Kontamination (Diagnose 09.06.):** 37,5 % der ≥70-Einträge
      tragen Score mit ~1-Tag-Daten-Versatz (Pre-Open-Re-Run friert Vortags-Bar
      ein; Signatur = `entry_price` exakt == Vortags-`entry_price` desselben
      Tickers). ~halbe Tage über das ganze v4-Fenster, wiederkehrend. **PFLICHT
      für 30.06.:** ≥70-Edge im **DOPPEL-LAUF** rechnen — mit UND ohne die
      detektierbaren Cluster-Einträge. Hält die Edge in beiden → robust, Caveat
      reicht. Kippt sie → Edge-Schluss **VERTAGEN, NICHT filtern** (40 %
      Erstauftritte sind uncheckbar = nicht reparierbarer blinder Fleck).
      `entry_price` selbst ist nur Diagnose-Tabelle (Returns nutzen
      `_close_at(0)`, geschützt); der **Score** ist das Problem (datumstreue
      Auswertungs-Eingabe).
    - **Quellen-Präzisierung (09.06.):** der datumstreue Score-Konsum läuft
      konkret über `health_check.py:619` (S13-≥70-Edge) + die bt-Panel-Buckets.
      KEIN Source-Fix rettet das eingebackene 30.06.-Sample — nur der
      Doppel-Lauf zählt.
  - **NEU: Entry-Shadow-Auswertung** — treffen dünne Scores schlechter (via
    `entry_n_components`)? Ausfall-Tage via `push_history_available=False`
    filtern. anomaly-Cap ggf. re-kalibrieren (n=25 dünn). DANN Push-/Live-
    Entscheidung.
  - FDA-Move-Muster (Wiedervorlage 08.05.).
- **Nach 10.06. — Inventur #3 (niedrig):** der Daily-Run-FINRA-**History**-Fetch
  (speist `si_trend_5d_slope`) ist **UNMONITORED** — `provider_health['finra']`
  überwacht nur den ki_agent-SSR-Fetch. Wächter-PR optional (graceful `None`
  bei FINRA-Tod; kein Blocker).
  - **FINRA-History-Log (#339, ab 09.06.):** `finra_history_health.jsonl` sammelt
    das pfad-eigene Sample (separate Datei, digest-frei). Auswertung ab ~23.06.
    für evidenzbasierte Wächter-Schwelle. **ACHTUNG bei Auswertung:** `coverage_pct`
    ist in **PROZENT** gespeichert, nicht als 0–1-Bruch (transparent abgewichene
    Feldform) — nicht um Faktor 100 verrechnen. Offen separat: Stale-Cache-Frische;
    uncapped si_trend-slope (FIP 08.06. = 521.84, Ausreißer falls roher slope
    statistisch genutzt).
- **08.06. (Rechner-Tag):** Backup-/Disaster-Recovery-Diagnose (read-only) —
  nicht-aufholbare Daten (backtest_history/score_inflation_log/score_history).

## 5) STRATEGISCHE ROADMAP
- **Nordstern unverändert:** Maschine prüft Mechanik, Mensch validiert Bedeutung.
- **NEU heute — Trading-Wert-Disziplin auf BLÖCKE, nicht nur Tasks:** vor jedem
  Arbeitsblock fragen „berührt das Trading/Edge?". Die CI-Gate-Kette
  (#329–#335) war teils **Verzettelung** (Engineering-Selbstzweck) — wertvoll
  fürs Vertrauen in die Suite, aber kein direkter Edge. Lesson: den
  Trading-Wert-Filter auch auf ganze Ketten anwenden.
- **Entry-Modul jetzt im Shadow → Daten sammeln bis 30.06., DANN erst Push-/
  Live-Entscheidung.** Kein vorzeitiges Scharfschalten.
- **Annahmen-Inventur (Runde 1) abgeschlossen:** #1 Gist-Body (#322) ✅, #2
  Screener-Pool (#325) ✅, #3 FINRA/DTC (Wächter optional, s. §4), #4 RVOL-
  Phasen = γ-2 (blockiert).
- γ-2 RVOL-Normalisierung (★, BLOCKIERT): premarket-Daten dünn · Cron-Drift
  #295 · `rel_volume_raw` ungebaut · Skalierer ungestützt. Bei Aktivierung
  beide Soll in `CONSISTENCY_EXPECTED_STATE` paaren (sonst S13-Drift).
- Externer Dead-Man-Switch (Cloudflare-Worker) gegen Cron-Drops (~20 %).
- Borrow-Fee + Utilization in score() (bei reifer CTB-Coverage).

## 6) CODE-HYGIENE-BACKLOG (Status je Punkt)
- **requests-Stub-PR** (die 3 TEMP-EXCLUDED `entry_score_persistence`,
  `health_check_ntfy_url_pattern`, `ntfy_fail_visibility` `requests`-stubben →
  zurück in ALLOWLIST, Gate **77→80**): **OPTIONAL**, Easy: „nicht dringend,
  kein Trading-Wert". TEMP-Kommentar-Nummer verweist auf „#336" (ging an den
  Entry-Score-PR) — bei Bau korrigieren.
- **topten_entry_anomaly / watchlist_drawer_live_momentum** (letzte 2 B-Tests,
  lesen echte Repo-Daten) → stubben für gate-tauglich. Niedrig.
- **Toter v2-else-Zweig entfernen** (Option b) — OPTIONAL, Easys Architektur-
  Entscheidung. Isoliert halten (Lektion #226), Dict-Key `"price_str"` behalten.
- **JSONL-Resolver-Lücke** (`grep -v '\.json$'` in beiden Workflows erkennt
  `.jsonl` nicht): selbstheilend, KEIN Datenverlust (nur Append-Logs). Fix
  `--ours` vs Union-Merge. OFFEN, niedrig.
- **Recovery-Umleitung bei Gist-Body-Korruption** (Folge-PR zu #322): bei
  `body_ok=False` Positionen erhalten statt `{}`. OFFEN.
- **Option A — Pre-Open-Re-Run-Guard** (offen, entkoppelt, kein 30.06.-Zeitdruck):
  Zeit-Gate in `_append_backtest_entries`, das einen postclose-Run VOR Schluss
  der regulären Session des `report_date` NICHT appenden lässt → verhindert
  Freitag-Cluster an der Quelle. Wirkt nur VORWÄRTS (rettet das eingebackene
  30.06.-Sample nicht). Bei 52 % stale-Rate unter recurring Tickern sonst
  Dauer-Verseuchung jedes künftigen Edge-Samples. Score-/Backtest-nah →
  manueller Merge + Guardian + Boundary-Mock-Test. **NICHT** Option B
  (existing_keys-Overwrite) — Clobber-Risiko für ki_agent-gefüllte Forward-Labels
  `return_3d`/`entry_price_t1`. After-Hours-Capture (b) braucht KEINEN Fix mehr:
  P&L erledigt (#338), Rest harmlos.
  - **Vintage-Guard-Erweiterung (Diagnose 09.06.):** M1 (Pre-Open-Re-Run) UND
    M2 (After-Hours-Capture, DBI 8.88) haben DIESELBE Wurzel = **Capture-Timing**
    → EIN wurzel-naher Guard fängt beide als Klasse: Zeit-Gate appendet NICHT,
    wenn der Run vor Session-Schluss des `report_date` läuft (Pre-Open) ODER der
    Preis im Extended-Hours-Fenster gegriffen wurde. Deterministisch, niedrig-FP,
    HÖCHSTER Hygiene-Wert. Optional begleitend **W2 = 14–30 d silent-log** der 3
    uncapped Rohfelder (`si_trend_5d_slope` max 521.84 / `rvol_buildup_5d` max
    153.55 / `rvol_acceleration` max 135.72) — NUR falls die 30.06.-Auswertung
    Rohwerte statt Buckets nutzt (entry-score selbst gecappt).
- **Finnhub-SI-Reserve** (gratis, Key da) als SF-Reserve falls Kette dünn. Niedrig.
- **or-0-Defaults Persist-Fix** · **finviz Flag-aus + α** · **Borrow-Naming
  (`IBKR_*`→`IBORROWDESK_*`)** · **v1/v2→Jinja** · **Cockpit Stage 3 (.sb-Reste)**
  → alle OFFEN, niedrig/vertagt.
- **Volle 86-Suite in CI** (über die 77 hinaus): inkrementell nach Hermetik-
  Triage (die 2 B + 5 ENV + 3 requests-TEMP bleiben außen bzw. brauchen Stubs).
- **ERLEDIGT diese Session:** Schema-Tripwire (#329), 5 stale Reds (#330),
  Golden-Liveness (#331), tier2-String-Gating-AST (#332, schließt den
  „~6 String-Gating-Checks"-Backlog), CI-Gate Phase 1+2 (#333/#335),
  health_check-Stub (#334), Entry-Score Shadow (#336).
- **Security-Backlog (Audit 09.06., alle niedrig/optional):** **M1** CSP-Meta in
  `head.jinja` (Defense-in-depth gegen künftige XSS-Klassen; `connect-src`
  sorgfältig allowlisten, iPhone-Verify; manuell + Guardian). **M3 = EASY-AKTION
  am Konto:** PAT auf fine-grained umstellen (nur dieses Repo + Gist) —
  reduziert Schaden bei künftigem Token-Leak. **M4** Worker-offener-Proxy
  (Quota-DoS, tolerierbar) + **L1** LLM-Error-Sink (trivial): bewusst
  AKZEPTIERT. **CVE-Check** (pip-audit/Dependabot) = Easy extern, Sandbox hat
  kein Netz.

## 7) ARCHITEKTUR-ANKER
**★ NEU diese Session:**
- **★★ Entry-Score (`entry_score.py`, #336):** PURES stdlib-Modul, bewusst
  getrennt von `backtest_history.py`/yfinance → CI-gate-bar ohne yfinance.
  Shadow: nur `backtest_history` schreibt + `_test_extended_schema` prüft die
  4 Felder; KEIN Render-/Push-/Score-Pfad liest sie. Berechnung nur **postclose**
  (`generate_report.py:16334 if run_phase=="postclose"`). **Entry-Entscheidungen
  (gemergt, exakt):** `ENTRY_UOA_CAP=4.0`, `ENTRY_RVOL_BUILDUP_CAP=6.0` (n=227),
  `ENTRY_SI_TREND_EDGES=(-0.8,-0.2,1.0,5.0)` ≤-Konvention → 0/25/50/75/100,
  score_delta `(x+15)/30×100`, anomaly `×100`; Aggregation = **Re-Norm Option B**
  (kein Neutral-50, Gleichgewichtung, 0 Komponenten→None); anomaly-None =
  **Option (c) run-level** (push-Map gefüllt+None→echte 0; Map leer→drop;
  `push_history_available` persistiert). Schema **v4 additiv** (S10 filtert ==4),
  Tripwire #329 scharf.
- **★ CI Allowlist-Runner + Drift-Guard (#335):** `run_ci_mock_tests.py` fährt
  eine STATISCHE Allowlist (77), kein Laufzeit-Glob für die Auswahl; Drift-Guard
  (glob nur dort) failt bei unklassifiziertem Test. Advisory bleibt
  (`permissions: contents: read`). Minimal-Install **jinja2+pyyaml** (BEWUSST
  KEIN requests/pandas_ta — Sandbox≠CI-Lehre, s. §8). EXCLUDED=10 (2 B + 5
  yfinance-ENV + 3 requests-TEMP).
- **★ Screener-Pool-Floor (#325):** `yahoo_screener` Tier-1-Inhalts-Check auf
  ROH-item_count (FLOOR=120), NICHT pool_size (POOL_MIN-Backfill maskiert).
- **★ AST-robuste provider_health-Test-Anker (#327/#332):** Struktur- UND
  String-Gating-Tests ankern per AST (record-call→Try / kwarg / enclosing-if),
  NICHT per Byte-Distanz.

**Bestehende Anker (unverändert):**
- **Advisory PR-CI (#316):** `pr-checks.yml`, `on: pull_request`, NICHT required,
  `check_run`-Signal, blockiert Self-Merge nicht.
- **S14 + Gist-Body-Sanity (#314 + #322):** `last_successful_gist_pull` nur bei
  `body_ok`; S14 WARN@26h; fängt Token-Tod UND Body-Korruption.
- **Outer-Page-Golden (#312):** Render-LOGIK-Netz, fixe Fixtures, pandas_ta-
  invariant; seit #331 auch Liveness-gestubbt (data-unabhängig). Output-Change
  → `UPDATE_GOLDEN` + Golden mit-committen (Pflicht).
- **`_DAILY_REPORT_COUNTS`-Modul-Global (#320)** (kein WL_TOP10-Leak).
- **report_date + _today_iso = US-Eastern (#304).** backtest-T+0 = `_close_at(0)`
  (#303). „Echter Phasen-Run" = run_phase==tsp (S11/S12).
- **S9-CRIT-Exit-Pfad filtert STRIKT id=="S9".**
- **Health-Check-Schichten:** S1–S7 State | S8 Digest-Liveness | S9 HTML-Sanity
  (einziger CRIT-Block) | S10 Daten-Integrität v4 | S11/S12 Phasen-Frequenz |
  S13 Daten-Reife + Konsistenz | S14 Gist-Pull-Liveness.
- **Borrow = iBorrowDesk-JSON (#292), Inhalts-success_check.** CTB persistiert (#309).
- **squeeze-guardian (#306/#319):** echo-Hook spawnt Agent NICHT; Architektur =
  manuelle EMPFOHLENE Routine, Bonus kein Gatekeeper.
- Cron-Inventar: ki_agent `17 * * * *`, daily premarket `17 6 * * 1-5`,
  postclose `17 21 * * 1-5`, health-digest `47 8 * * *`, watchlist `0 7 * * 0`,
  pr-checks `on: pull_request`. checkout@v5.
- **★ Security-Audit 09.06. (read-only, 6 Bereiche) — ERLEDIGT-Teil:** Token-
  Krypto bestätigt **solide** (PBKDF2 600k, AES-GCM, frische IV+Salt pro
  Verschlüsselung, Master-PW nie persistiert). **C1+M2 GEFIXT (#343):** Stored-
  XSS im News-Render + company/sector — `_escH`-Escaping (inkl.
  Anführungszeichen, Attribut-Kontext) + `n.link`-Whitelist `^https?://`
  (Escaping allein stoppt `javascript:` NICHT). Damit ist der **einzige Pfad zu
  echtem Konto-/Token-Schaden** (XSS → sessionStorage-PAT) dicht.
- **★ Privacy-Akzeptanz (Entscheidung c, 09.06., Easy):** Repo public + Gist-ID
  im gerenderten `index.html` → der secret Gist (Positionen/Stückzahlen/
  Watchlist) ist für jeden Page-Besucher **anonym LESBAR** (kein Write, kein
  Token-Zugriff — reines Lese-/Privacy-Risiko). **BEWUSST AKZEPTIERT**, weil:
  (1) Repo-privat bricht Pages auf Free-Plan + Actions-Minuten-Limit, und die
  Pages-Site bliebe ohnehin public (Access-Control erst Enterprise); (2) Strip
  der committeten Mirror-Files **VERWORFEN** nach Diagnose —
  `app_data.positions.exit_state` ist das **EINZIGE** Cross-Run-Ratchet-
  Gedächtnis (peak_score/peak_pnl/prev_exit_pressure, gen `15224/15250`;
  `pull_gist_data.py:192` übernimmt es nicht) → voller Strip = Peak-Reset jeden
  Run = falscher Exit-Druck (**HARD-BREAK, Trading-Schaden**);
  `agent_state.push_history` nicht strippbar (Entry-Score-Input
  `backtest_history.py:533` + ki_agent-FIFO-Gedächtnis); Rest-Strip hätte ≈0
  Gewinn, da dieselben Daten im akzeptierten Gist offen liegen. **NICHT erneut
  vorschlagen ohne neue Lage.** Echte Privatheit nur via Storage-Redesign
  (Option d): auth-gated Store statt URL-lesbarem Gist — optionaler Roadmap-
  Punkt, kein Druck.

## 8) LESSONS (06.–07.06.2026)
- **★ Sandbox ≠ CI-Env:** der Sandbox HAT `requests` (+ pyyaml etc.), der
  Minimal-CI-Install (jinja2+pyyaml) NICHT → „grün geboren" ist NUR gegen einen
  Env beweisbar, in dem ALLE CI-fehlenden Deps blockiert sind, **nie** gegen die
  Sandbox. Der naive 79-Runner war CI-rot (3 requests-Tests), obwohl
  Sandbox-grün. Fix: CI-Sim mit Dep-Blocker vor jedem „grün"-Claim.
- **Diff-Anzeige ≠ finaler Stand:** ein Diff zeigt entfernte Zeilen (`-`), die
  wie noch-aktive Steps aussehen → den FINALEN Datei-Stand greppen, nicht den
  Diff interpretieren (Doppellauf-Fehlalarm bei #335).
- **None ist nicht gleich None:** „keine Daten" (Pipeline-Ausfall) vs „echtes
  Nichts" (legit kein Wert) muss am SCHREIBPFAD unterschieden werden, nicht am
  Feld (Entry-anomaly Option-(c)-Klasse). Per-Feld nicht trennbar → Run-Level-
  Flag + Mini-Stopp für Easys Entscheidung.
- **Trading-Wert-Filter auf BLÖCKE:** die CI-Kette war teils Selbstzweck. Vor
  einer ganzen Arbeitskette fragen „Edge oder Hygiene?", nicht nur pro Task.
- **★ Inhalts-Plausibilität ist eine fehlende Überwachungsschicht (09.06.):**
  S10/Schema/Golden decken Liveness + Null/Schema, aber NICHT Wert-Plausibilität
  (Range/Freeze/Vintage) — belegte Lücke (S10 prüft nur `is None`,
  `health_check.py:404`). Der Freitag-Cluster wurde per ZUFALL gefunden, weil
  keine Schicht ihn fing. **LINIE** für künftige Integritäts-Funde (gegen
  Over-Engineering + Wächter-Block-Lehre 04.06.): Wächter NUR wo (1) der Defekt
  belegt Trading-Entscheidungen/Edge verzerrt UND (2) der Check wurzel-nah +
  niedrig-Falsch-Positiv ist. Sonst Caveat oder silent-log-first. **FP-Baseline:**
  Slow-Update-Freeze (SF/dtc 85 %, score_struct 70 %) ist LEGITIM — kein naiver
  Freeze-Wächter. **Selbst-Begrenzung:** signatur-lose Defekte (plausibel-aber-
  falscher Einzelwert, Korrelations-Inkonsistenz, externe Quell-Korruption) sind
  strukturell unsichtbar — kein Wächter darf vorgeben, alles zu fangen.
