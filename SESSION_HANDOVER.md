# SESSION_HANDOVER.md — Stand 05.06.2026

## 1) HEUTE IMPLEMENTIERT (mit Hashes)
*(Diese Session 05.06. Hashes aus `git log` auf main, verifiziert. Roter Faden
des Tages: die CI-Lücke — „CI grün + Guardian grün" ≠ „alle Tests grün",
solange ~81 von 86 Mock-Tests nicht automatisch laufen.)*

- **#324 (Merge `55d7c392`; Commits `39c438b4` chore + `1dab2c36` golden) —
  05.06.** **stockanalysis-SI/SF deaktiviert** (`STOCKANALYSIS_SI_ENABLED=False`,
  config.py:242). SI-Scrape strukturell **tot seit 15.05.** (149/149 Calls
  fail, `http=None`, IBKR-Fehlerklasse) — **Zugriff tot, Quelle lebt**;
  `short_float` trägt faktisch seit ~3 Wochen yfinance, **kein Datenverlust**.
  Borrow-Pfad (`STOCKANALYSIS_BORROW_ENABLED`/iBorrowDesk) **unberührt**.
  Entrauscht den Digest. Datasource-Display „(aktuell keine Daten)" → „(aus)"
  → Golden mit-regeneriert (`1dab2c36`). **Guardian ✅.** Manueller Merge.
- **#325 (Squash `9abe8397`) — 05.06.** **★ Screener-Pool-Untergrenze-Wächter
  (Inventur-Fund #2, NEUER Architektur-Anker).** Fällt der **ROH**-item_count
  des `yahoo_screener` unter `SCREENER_POOL_MIN_FLOOR` (=120, config.py),
  schreibt `record_provider_call` `coverage_pct=0` → Tier-1-Inhalts-Fail →
  Digest. **Check sitzt auf dem ROH-Count, NICHT pool_size** (POOL_MIN-Backfill
  ≥20 maskiert dort jede Schrumpfung). Block im `finally` NACH dem Fetch →
  **reines Monitoring**, kein Eingriff in Pool-Aufbau/Backfill/Scoring.
  FLOOR=120 empirisch geerdet (3-Wochen-Spanne 160–239, All-Time-Min 160,
  ~25 % Marge). None/leer → `_pool_n=0` < Floor → Fail. **Guardian ✅.**
  Manueller Merge.
- **#326 (Merge `937d3e4b`; Commit `7381f7a2`) — 05.06.** **`${price_str}`-
  NameError-Fix im toten v2-else-Zweig** von `_build_card_ctx`
  (generate_report.py:5797). `price_str` war dort nie zugewiesen → liefe der
  Zweig (Flag=False), gäbe es `NameError` (kein XSS, harter Crash). Fix =
  **Name-Auflösung wie v1-Zwilling** (`${s.get("price",0):.2f}`), **kein
  Klammer-Verdoppeln** (das gäbe literal `${price_str}`). Macht
  `mock_test_gist_action_token_routing` #8 grün (war seit 19.05. rot) und den
  Flag=False-**Rollback-Fallback erstmals funktionsfähig**. Dict-Key
  `"price_str"` unverändert (card.jinja konsumiert ihn). Golden byte-identisch
  (toter Code). Manueller Merge.
- **#327 (Squash `e8be4c86`) — 05.06.** **★ AST-robuste provider_health-Test-
  Anker (NEUER Architektur-Anker).** #325 machte 2 provider_health-Tests rot:
  ein +600-Zeichen-Kommentar im finally schob die Struktur-Keywords aus dem
  distanz-basierten `_block_around`-Fenster (finally bei Distanz 812 > 800) —
  **kein Code-Regress**, reine Test-Fragilität. Fix: die **10 strukturellen**
  Tests (try/finally + except-raise) ankern jetzt per **AST**
  (`_provider_record_try` → record_provider_call→umschließende Try,
  `_try_has_except_raise`), distanz-/kommentar-immun. **Negativ-Kontrolle
  belegt höhere Schärfe** (fängt jetzt auch „record im body statt finally", das
  der alte Distanz-Test durchwinkte). provider_health 30/30, tier2 28/28.
  ~6 String-Gating-Checks bleiben bewusst distanz-basiert. **Test-only.**
  Manueller Merge.

## 2) AKTIVE POSITIONEN
**Quelle: `app_data.json`-Positions-Mirror (`run_phase=premarket`,
`generated 2026-06-05T15:08:46Z`) — der private Gist (squeeze_data.json) ist im
Sandbox NICHT direkt lesbar (kein `GIST_ID`/`GIST_TOKEN`, keine lokale Datei).
Stand daher = letzte Daily-Run-Materialisierung, NICHT Live-Gist →
Verifikation nötig.** 8 offene Positionen:

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

**AI: Exit-Pushes bewusst akzeptiert, kein `no_exit_alerts`-Flag.** Easy hat
entschieden, AI trotz Hold-These (Siebel) die Exit-Trigger laufen zu lassen —
**kein To-do, nichts anzupassen.** (Nur AMC trägt das Hold-Flag heute.)

## 3) VERIFIKATION MORGEN/OFFEN
- **★ Screener-Pool-Floor (#325) erstmals LIVE** beim nächsten Daily-Run:
  prüfen, dass der ROH-item_count im Normalbereich (~160–239) liegt und der
  Floor=120 **NICHT fälschlich feuert** (Fehlalarm-Check der frischen
  Schwelle). Im Digest / `provider_health.jsonl` gegenchecken
  (`coverage_pct=100`, kein `pool_below_floor`-Error).
- **Transiente Health-Fails von heute früh heilen:** S3 (`current_price` bei
  Positionen) und S7 (`agent_signals`-Drift) sollten nach dem nächsten sauberen
  Run weg sein → im Digest gegenchecken.
- **#326 price_str:** der Render-Output ist unverändert (toter Zweig) — keine
  visuelle Verifikation nötig; relevant nur falls Flag jemals auf False geht.

## 4) GEPLANTE AUFGABEN + WIEDERVORLAGEN (mit Daten)
### Höchste Backlog-Prio
- **★★ (c) CI-LÜCKE SCHLIESSEN — Wurzel-Befund des Tages.** Nur **5 von 86**
  Mock-Tests laufen automatisch (`pr-checks.yml`). Heute **3× durchgerutscht**:
  `${price_str}` rot seit 19.05. (17 Tage), die 2 #325-Folge-Rote, beide
  unbemerkt bis zur manuellen Diagnose. **Aufnehmen:** provider_health-Tests
  (tier1+tier2) + `${var}`-Grep in `pr-checks.yml`. **ERST nach Grün-Stand**
  (sonst Gate rot geboren — beide sind jetzt grün, also baubar). Mittelfristig
  volle 86-Suite inkrementell nach Hermetik-Triage.

### Wiedervorlagen
- **08.06. (Rechner-Tag):** Backup-/Disaster-Recovery-Diagnose (read-only) —
  nicht-aufholbare Daten (backtest_history.json, score_inflation_log.jsonl,
  score_history.json). VOR dem 10.06.-Entry-Modul.
- **10.06. ★★★ Entry-Timing-Modul-Bau — Vorarbeit KOMPLETT.** Shadow-Mode
  (`ENTRY_SCORE_PUSH_ENABLED=False`). Andock in main() NACH
  `apply_score_smoothing`, VOR `compute_earliness_pts`. Neues Modul
  `entry_score.py`. **TODO beim Bau:** `si_trend_5d_slope` ehrlich als
  Volumen-Momentum labeln (kein Umbau, s. §5).
- **30.06.:** Backtest-Auswertung + **Conviction-Methodik-Diagnose** +
  **Earliness-Konfidenz-Re-Test** (AUC gegen schema_v4 nach 14–30 d Trend-
  Logging).

### Entry-Modul — Bau-Spezifikation (verifiziert 04.06., bereit für 10.06.)
- **Persistenz aller 5 Komponenten verifiziert** (non-null-Muster legitim,
  keine stillen Schreib-Fehler).
- **Normalisierung: FEST, nicht Perzentil** (Daten zu dünn; Shadow-v1):
  - `anomaly_freshness` → selbst-normalisiert (0..1) → `×100`.
  - `score_delta_t1` → selbst-gecappt ±15 → `(x+15)/30×100` (symmetrisch).
  - `uoa_atm_ratio` → feste Cap ~3.5–4 (gut-konditioniert, n=79).
  - `rvol_buildup_5d` → fix mit Clamp ~5–6 (Outlier max 153 sonst skalen-tötend).
  - `si_trend_5d_slope` → BUCKETS (5-stufig) statt linear (Nenner-Explosion
    max 374, si_old≈0 — strukturell, mehr Daten heilen das NICHT).

## 5) STRATEGISCHE ROADMAP
- **Entry-Timing-Modul** (★★★, 10.06.) — Vorarbeit komplett.
- **Annahmen-Inventur Provider abgeschlossen** (Runde 1), 4 kritisch gewichtet,
  Bau-Reihenfolge nach Wichtigkeit:
  1. **Gist-Body-Korruption** → ✅ ERLEDIGT (#322, Detektion). Restkante
     Recovery-Umleitung offen (§6).
  2. **Yahoo-Screener-Pool-Untergrenze** → ✅ ERLEDIGT (#325, Wächter live).
  3. **FINRA/DTC-Drift** → niedrige Prio. Wächter optional, graceful
     Degradation + Shadow; **kein 10.06.-Blocker**.
  4. **RVOL-Phasen-Bedeutung** = das **γ-2-Thema** (RVOL-Normalisierung,
     blockiert, eigenes Projekt).
- **FINRA/DTC (Fund #3) — geklärt:** FINRA-Quelle ist **TÄGLICHES Reg-SHO-Short-
  VOLUMEN**, NICHT bi-monthly Short-Interest. **DTC kommt von yfinance**
  (`shortRatio`), nicht von FINRA → DTC unberührt bei FINRA-Tod.
  `si_trend_5d_slope` speist sich aus dem FINRA-Tages-Short-Volumen (graceful
  `None` bei FINRA-Tod). Monitoring-Lücke real aber **folgenarm** (der Short-
  Volume-Fetch ist nicht in provider_health; `provider_health['finra']` =
  SSR-Fetch). Wächter optional.
- **Entry-Modul Semantik (10.06.):** `si_trend_5d_slope` misst **Short-VOLUMEN-
  Momentum (Fluss)**, NICHT Short-Interest (Bestand). Fluss ist für Entry-TIMING
  richtig (täglich/reaktiv; Bestand träge) — bewusst so, nur **ehrlich labeln**.
- γ-2 RVOL-Normalisierung (★, BLOCKIERT): 4 Vorbedingungen (premarket-Daten
  dünn · Cron-Drift #295 · `rel_volume_raw` ungebaut · Skalierer 0.10/0.40
  ungestützt). Bei Aktivierung BEIDE Soll in `CONSISTENCY_EXPECTED_STATE` paaren
  (sonst S13-Drift).
- **Externer Trigger / Dead-Man-Switch** außerhalb GitHub Actions (Cloudflare-
  Worker) — deckt Cron-Drops (~20 %) + Failure-Fate + JSONL-Resolver-Lücke.
- Phasen-/perzentil-basierte Schwellen (an Daten-Reife gekoppelt).
- Borrow-Fee + Utilization in score() (bei reifer CTB-Coverage).
- Backup/Disaster-Recovery (08.06.): git mirror | Daten-Export | Account-Spiegel.
- PR-CI-Ausbau (#316): heute 5 Checks → volle 86-Suite inkrementell.

## 6) CODE-HYGIENE-BACKLOG (mit Status)
- **String-Gating-Checks (~6) ebenfalls AST-robust machen** — OFFEN, niedrig.
  finnhub/stockanalysis emit (`calls>0`), finra `run_phase`, ew `nan_pct` ×2,
  yfinance_singletons daily-run-side bleiben distanz-basiert (anderes Muster:
  String-Präsenz / If-Test statt try-Struktur; aktuell grün, komfortable
  Margen). Anderes AST-Vehikel nötig (enclosing-If/Segment).
- **★ JSONL-Resolver-Lücke** (Diagnose 05.06.): `grep -v '\.json$'` in beiden
  Workflows (`ki_agent.yml:93`, `daily-squeeze-report.yml:201`) erkennt
  `.jsonl` NICHT → bei Daily×ki_agent-Überlapp bricht der Rebase, sobald
  `health_check_log.jsonl`/`provider_health.jsonl` konfligieren. **main
  selbstheilend, KEIN echter Datenverlust** (nur Append-Logs). Kosten:
  FAILED-Mail + 1 Tick Telemetrie übersprungen. Fix: Pattern auf `.jsonl?$` —
  `--ours` (einfach, verliert 1 Tick) vs. Union-Merge (korrekt). OFFEN, niedrig.
- **Toten v2-else-Zweig entfernen (Option b)** — OPTIONAL, **Easys Architektur-
  Entscheidung** (= Cockpit-Permanenz, Verzicht auf den Flag=False-Rollback-
  Fallback, der durch #326 erst funktionsfähig wurde). **Isoliert halten**
  (Lektion #226: nie Feature+Cleanup bündeln), **Dict-Key `"price_str"`
  behalten** (card.jinja konsumiert ihn).
- **★ Recovery-Umleitung bei Gist-Body-Korruption** (Folge-PR zu #322): bei
  `body_ok=False` Positionen ERHALTEN (wie `gist is None` → Recovery-Kette)
  statt `positions={}`. Verhaltens-Change (größer als #322). OFFEN.
- **Datenquellen-Reserve Finnhub-SI** (gratis, Key vorhanden) als SF-Reserve
  falls die SF-Kette je dünn wird; available/fee-Knappheits-Proxy nach Entry-
  Modul. OFFEN, niedrig.
- **★ 86-Test-Suite inkrementell in CI** (nach Hermetik-Triage) → s. §4 (c).
- **or-0-Defaults Persist-Fix** (dtc/rvol/Bonus → None) → OFFEN, niedrig.
- **finviz Flag-aus + α** → OFFEN, an Daten-Reife gekoppelt.
- **Borrow-Naming-Cleanup** (`IBKR_*` → `IBORROWDESK_*`) → OFFEN, niedrig.
- v1/v2 → Jinja → OFFEN (Golden-Test #312 ist das Sicherheitsnetz).
- Cockpit Stage 3 (.sb-Reste) → VERTAGT.
- **ERLEDIGT diese Session:** `${price_str}` (#326), Screener-Pool-Floor (#325),
  provider_health-Test-Fragilität strukturell (#327, 10 Tests), stockanalysis-
  SI (#324). rsi14=None-Fixture (#321, Vorsession).

## 7) ARCHITEKTUR-ANKER
**★ NEU diese Session:**
- **★ Screener-Pool-Floor (#325):** `yahoo_screener` Tier-1-**Inhalts**-Check
  auf den **ROH-item_count** (`SCREENER_POOL_MIN_FLOOR=120`), NICHT auf
  `pool_size` (POOL_MIN-Backfill ≥20 maskiert Schrumpfung). `coverage_pct`
  binär 100/0; Block im `finally` NACH dem Fetch = reines Monitoring.
  Vorbild: Borrow-Inhalts-Check #292.
- **★ AST-robuste provider_health-Test-Anker (#327):** strukturelle Tests
  ankern per **AST** (`record_provider_call`→umschließende `Try`, `finalbody`
  + `except`-mit-`raise`), NICHT per Zeichendistanz (`before=N`). Distanz-/
  kommentar-immun. Gilt für die **10 strukturellen** Tests; ~6 String-Gating-
  Checks bleiben bewusst distanz-basiert (§6).

**Bestehende Anker (unverändert):**
- **Advisory PR-CI (#316):** `.github/workflows/pr-checks.yml`,
  `on: pull_request`, 4 Lints + Outer-Page-Golden. **NICHT required**, keine
  Branch-Protection → `check_run`-Signal, blockiert Self-Merge nicht. Install
  = **nur `jinja2>=3.1.0`** (NICHT requirements.txt — pandas_ta crasht am
  yfinance-Stub `__spec__=None`). Einziger PR-triggernder Workflow.
- **S14 + Gist-Body-Sanity (#314 + #322):** `last_successful_gist_pull`
  (`gist_pull_state.json`) wird im HTTP-Gist-Erfolgszweig NUR bei `body_ok`
  gesetzt (`_extract_data -> tuple[dict, bool]`, `positions`-Key-Präsenz-
  Diskriminator VOR der `or "{}"`-Maskierung). S14 WARN@26h, beide Pfade,
  None-tolerant. Fängt Token-Tod UND Body-Korruption. Restkante:
  Recovery-Umleitung (§6).
- **Outer-Page-Golden (#312):** Render-LOGIK-Netz mit fixen Fixtures, KEIN
  Produktions-Daten-Abbild. Render-Pfad **pandas_ta-invariant**. Bei
  Output-Change: lokal laufen + `UPDATE_GOLDEN=1` + Golden mit-committen
  (CLAUDE.md-Pflichtregel).
- **`_DAILY_REPORT_COUNTS`-Modul-Global (#320):** Daily-Report-Häufigkeit als
  Global (wie `_SCORE_CONFIDENCE`), NICHT Stock-Dict-Feld → kein WL_TOP10-Leak.
- **report_date + _today_iso = US-Eastern (#304).** Beide derselben ET-Achse.
- **backtest-T+0-Return-Basis = `_close_at(0)` (#303)** (split-konsistent).
- **„Echter Phasen-Run" nur via score_inflation_log: run_phase==tsp.** Basis
  S11/S12.
- **S9-CRIT-Exit-Pfad filtert STRIKT id=="S9".** Neue crit-Checks blockieren
  NICHT.
- **Health-Check-Schichten (Stand 05.06.):** S1–S7 State | S8 Digest-Liveness
  | S9 HTML-Sanity (einziger CRIT-Block) | S10 Daten-Integrität v4 | S11/S12
  Phasen-Frequenz | S13 Daten-Reife + Konsistenz-Wächter | S14 Gist-Pull-
  Liveness (+ Body-Sanity #322). Tabellen CLAUDE.md + spec vollständig S1–S14.
- **Borrow = iBorrowDesk-JSON (#292), Inhalts-success_check** (`cost_to_borrow
  is not None`) — Vorbild-Muster gegen Stille-Tod. CTB persistiert (#309).
- **squeeze-guardian (#306/#319):** echo-Hook spawnt Agent NICHT. Krypto =
  Lint; Architektur = manuelle, EMPFOHLENE (nicht zwingende) Modell-Routine,
  Bonus kein Gatekeeper.
- Cron-Inventar: ki_agent `17 * * * *`, daily premarket `17 6 * * 1-5`,
  postclose `17 21 * * 1-5`, health-digest `47 8 * * *`, watchlist `0 7 * * 0`,
  **pr-checks `on: pull_request`** (kein Cron, #316). checkout@v5 (#318).

## 8) LESSONS (05.06.2026)
- **★ CI-Lücke ist der rote Faden des Tages:** „CI grün + Guardian grün" heißt
  NICHT „alle Tests grün", solange ~81 von 86 Tests nicht automatisch laufen.
  `${price_str}` (17 Tage rot, seit 19.05.) und die #325-Folge-Rote belegen
  dieselbe Klasse — beide nur durch manuelle Diagnose gefunden. Selbst-Lehre:
  ich meldete bei #325 fälschlich „nur price_str rot", weil `tail` 2 ✗-Zeilen
  abschnitt → Behauptung statt Nachweis. Fix: volle Fail-Liste lesen, nicht
  zählen.
- **Blanket-Revert-Falle (price_str-Herkunft):** #226 entfernte den toten
  else-Zweig korrekt, wurde aber wegen Watchlist-Bruch KOMPLETT zurückgerollt
  (#227) → holte den `${price_str}`-Bug zurück. Bestätigt „**nie Feature +
  Cleanup bündeln**".
- **Diagnose-Prämissen prüfen, nicht übernehmen:** die „bi-monthly"-Annahme bei
  FINRA war falsch — die Quelle ist TÄGLICHES Reg-SHO-Short-Volumen; der Code
  korrigierte die Prämisse an echten Daten. Prämisse am Code/Daten verifizieren.
- **Fragiles Test-Muster ≠ Code-Regress (#327):** der distanz-basierte
  `_block_around`-Anker (before=N Zeichen) bricht bei JEDER Kommentar-Änderung
  in der Nähe, obwohl der Code intakt ist. AST-Anker (Struktur statt Distanz)
  ist immun UND schärfer (fängt „record im body statt finally"). Faustregel:
  Struktur-Tests an AST/Marker hängen, nie an Byte-Distanz.
- **Monitoring muss auf der unmaskierten Größe sitzen (#325):** ein Floor auf
  `pool_size` wäre wirkungslos gewesen (POOL_MIN-Backfill maskiert) — der
  ROH-item_count ist die einzig ehrliche Messgröße. „Wo maskiert eine
  Fallback-/Default-Logik das Signal?" vor jedem Wächter fragen.
