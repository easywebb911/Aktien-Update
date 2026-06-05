# SESSION_HANDOVER.md — Stand 05.06.2026

## 1) HEUTE IMPLEMENTIERT (mit Hashes)
*(Diese Session: 03.06.-Abend → 05.06. Hashes aus git log auf main, verifiziert.)*
- **#316 (Merge d1c0b697, Commit 9a1f0868) — 03.06.** **★ Advisory PR-CI
  (NEUER Architektur-Anker).** `.github/workflows/pr-checks.yml`
  (`on: pull_request`) fährt Golden-Test + 4 Lints. **ADVISORY** — kein
  required-status-check, keine Branch-Protection, `permissions: contents:
  read` → liefert `check_run`-Signal, blockiert Self-Merge NICHT. Erstlauf
  rot: `pip install -r requirements.txt` zog pandas_ta → dessen
  `find_spec("yfinance")` crasht am yfinance-Stub (`__spec__=None`). **Fix
  32ba95dc:** nur `pip install "jinja2>=3.1.0"` (pandas_ta absent → ta=None-
  Pfad = Golden-Generierungs-Zustand). Manueller Merge.
- **#317 (Merge eaa8e02d) — 03.06.** Handover-Update Stand 03.06. Doku.
- **#318 (Merge 5b1cd3b7, Commit f957e395) — 04.06.** `actions/checkout`
  **v4 → v5** in allen 9 Workflows (Node-20-Deprecation, GitHub zwingt Node 24
  ab **16.06.2026**). Reiner Versions-Bump, alle Runner `ubuntu-latest`
  (hosted → v2.327.1-Bedingung auto-erfüllt). CI grün auf v5. Auto-Merge.
- **#319 (Merge da272999) — 04.06.** **CLAUDE.md: squeeze-guardian als
  EMPFOHLENER Bonus-Schritt** (nicht zwingend, nicht automatisiert). Routine
  „verbindlich" → „EMPFOHLEN" + Bonus-kein-Gatekeeper-Block (nicht-
  deterministisch, ersetzt NICHT Bedeutungs-Validierung). Frontmatter
  „Wird AUTOMATISCH aufgerufen / MUSS proaktiv" → „modell-initiiert in der
  Session, NICHT automatisch durch Events". Doku.
- **#320 (Merge b9bb2d34; Commits da78ef2a feat + c2c5dafe Relokation +
  be706d4b font-size) — 04.06.** **„N× im Daily-Report" auf der Karte** —
  klein UNTER dem Rang-Badge (`.cockpit-rank-col`/`.rank-freq`, `.65rem`).
  Server-seitig aus `backtest_history` (in main() geladen, KEINE neue
  Persistenz). PFLICHT-Filter `source != 'bootstrap'` (AMC 10 statt 45).
  Modul-Global `_DAILY_REPORT_COUNTS` (kein WL_TOP10-Feld-Leak). Ehrlich
  gelabelt (NICHT „Top-Ten": Pool bis pos 13). Golden mit-regeneriert.
  Auto-Merge-fähig, manuell gemergt.
- **#321 (Merge 209b6660, Commit 9e9d212b) — 04.06.** **rsi14=None-Golden-
  Abdeckung** (Test-Härtung). Fixture-Ticker BBBB auf `rsi14=None` → deckt
  beide RSI-Render-Zweige in einem Golden (AAAA Wert-Zweig, BBBB None-Zweig
  = RSI-Zeile weg + leeres `data-rsi`). Kein Produktionscode. Auto-Merge.
- **#322 (Merge b77d6cf5; Commits 3189406b fix + c864f95d docs) — 04.06.**
  **★ Gist-Body-Sanity → Marker-Gating (S14-Restkante GESCHLOSSEN).** Bei
  HTTP-200 + korruptem/leerem/`truncated` `squeeze_data.json` kollabierte
  `_extract_data` still auf `{positions:{}}` → `_mark_successful_gist_pull`
  fälschlich gesetzt → S14 schwieg. Fix: `_extract_data -> tuple[dict, bool]`,
  `body_ok`-Diskriminator (Entry da · nicht truncated · content nicht-leer ·
  parst zu dict · `positions`-Key als dict — Struktur-PRÄSENZ vor der
  `or "{}"`-Maskierung). `main()`: Marker NUR bei `body_ok`. **SCOPE: nur
  Marker-Gating (Detektion)** — Schreib-/Recovery-/Migrations-Verhalten
  unverändert. **Recovery-Umleitung** (Positionen bei Korruption erhalten)
  bewusst out-of-scope/Folge-PR. **Guardian-Review ✅ OK** (4 Punkte sauber);
  fand 3 stale Doku-Stellen → Doku-Sync (health_check.py, spec ×2, CLAUDE.md).
  10 Fälle bestehen, deterministisch. Manueller Merge.

## 2) AKTIVE POSITIONEN
**Quelle: `app_data.json` (Gist-Mirror, `generated_at=2026-06-05T01:31Z`,
postclose) — der private Gist ist im Sandbox nicht direkt lesbar (kein
GIST_TOKEN). Stand daher = letzter Daily-Run-Materialisierung, NICHT
Live-Gist.** 7 offene Positionen:

| Ticker | Entry | Kurs (akt.) | PnL | exit_pressure | no_exit_alerts |
|---|---|---|---:|---:|---|
| **AMC** | 01.05. @ 1.50 (500) | 1.96 | **+30.7 %** | 37 | **True** (Hold) |
| **IONQ** | 11.05. @ 49.10 (40) | 65.66 | **+33.7 %** | 35 | False |
| **CRMD** | 14.05. @ 7.93 (8) | 8.54 | +7.7 % | 15 | False |
| **GEMI** | 18.05. @ 5.40 (18) | 4.62 | −14.4 % | 20 | False |
| **PDYN** | 20.01. @ 11.52 (150) | 8.16 | −29.2 % | 15 | False |
| **AI** | 01.06. @ 11.00 (10) | 10.58 | −3.8 % | 22 | **False** ⚠ |
| **RBOHF** | 03.06. @ 0.67 (1300) | 0.23 | **−65.7 %** | 21 | False |

**⚠ DISKREPANZ (Verifikation nötig):** Easy nennt **AI als Hold** (Siebel-These
nach Earnings 03.06., keine Exit-Alerts gewünscht) — aber `app_data` zeigt
`no_exit_alerts=False` für AI. **Das Hold-Flag ist im Gist offenbar noch NICHT
gesetzt** → AI bekommt aktuell Exit-Push-Trigger. Easy: `no_exit_alerts: true`
für AI im Gist setzen (Position-Panel) ODER bestätigen, dass Alerts gewollt
sind.

## 3) VERIFIKATION MORGEN/OFFEN
- **★ AI-Hold-Flag (s. §2):** im Gist `no_exit_alerts=true` für AI setzen,
  beim nächsten Daily-Run prüfen, dass app_data es spiegelt → keine
  AI-Exit-Pushes mehr.
- **#322 Gist-Body-Sanity erstmals live:** im Actions-Log des nächsten Pulls
  prüfen, dass bei gesundem Gist `body_ok=True` (Marker gesetzt, kein WARN).
  Bei künftigem korruptem/leerem Body: WARN-Zeile „squeeze_data.json-Body
  unplausibel … Marker NICHT gesetzt" + S14 altert.
- **#316 advisory CI bei jedem PR:** liefert `check_run` (grün/rot); bei
  Output-Change muss `UPDATE_GOLDEN=1` + Golden mit-committet werden.
- **#318 checkout@v5** in den Cron-Workflows: nächste Daily-/ki_agent-Läufe
  müssen weiter grün durchlaufen (v5 = nur Node-Bump, kein Verhaltens-Drift).
- **#320 Karten-Häufigkeit** nach Deploy auf iPhone: „N× im Daily-Report"
  unter der Rang-Badge, `.65rem` lesbar.

## 4) GEPLANTE AUFGABEN + WIEDERVORLAGEN (mit Daten)
### Wiedervorlagen
- **08.06. (Rechner-Tag):** Backup-/Disaster-Recovery-Diagnose (read-only) —
  nicht-aufholbare Daten (backtest_history.json, score_inflation_log.jsonl,
  score_history.json). VOR dem 10.06.-Entry-Modul.
- **10.06. ★★★ Entry-Timing-Modul Bau — Vorarbeit KOMPLETT.** Shadow-Mode
  (`ENTRY_SCORE_PUSH_ENABLED=False`). Andock in main() NACH
  apply_score_smoothing, VOR compute_earliness_pts. Neues Modul
  `entry_score.py`.
- **30.06.:** Backtest-Auswertung + **Conviction-Methodik-Diagnose** +
  **Earliness-Konfidenz-Re-Test** (AUC gegen schema_v4 nach 14–30 d Trend-
  Logging).

### Entry-Modul — Bau-Spezifikation (verifiziert 04.06., bereit für 10.06.)
- **Persistenz aller 5 Komponenten verifiziert** (Schritt 1 läuft): seit-
  Daten gestaffelt, non-null-Muster legitim (keine stillen Schreib-Fehler).
- **rvol_acceleration → `rvol_buildup_5d`** umgestellt (Entscheidung 04.06.):
  echtes Intraday-Anziehen ist mit den Daten **nicht baubar** (nur 2 Routine-
  Snapshots/Tag, premarket stale) — **ehrlich gelabelt** als Tages-Volumen-
  Aufbau, NICHT „intraday". `rvol_buildup_5d` ist schon persistiert (S10_MUSS,
  98 % non-null). Echtes Intraday = eigenes Projekt nach γ-2 (braucht ≥3
  kontrollierte Intra-Session-Snapshots + kalibrierte Normalisierung).
- **Normalisierung: FEST, nicht Perzentil** (Daten zu dünn/Verteilung-
  instabil; Shadow-v1):
  - `anomaly_freshness` → **selbst-normalisiert** (0..1 by construction) → `×100`.
  - `score_delta_t1` → **selbst-gecappt ±15** → `(x+15)/30×100` (symmetrisch).
  - `uoa_atm_ratio` → **feste Cap ~3.5–4** (gut-konditioniert, n=79).
  - `rvol_buildup_5d` → **fix mit Clamp ~5–6** (Outlier max 153 sonst skalen-tötend).
  - `si_trend_5d_slope` → **BUCKETS (5-stufig)** statt linear — Nenner-
    Explosion (max 374, si_old≈0) macht lineare Magnitude unbrauchbar; mehr
    Daten heilen das NICHT (strukturell).

### Annahmen-Inventur Provider (Runde 1 abgeschlossen 04.06., alle 4 von Easy
als kritisch gewichtet) — Bau-Reihenfolge:
1. **Gist-Body-Korruption** → ✅ ERLEDIGT (#322, Detektion). Restkante
   Recovery-Umleitung offen (s. §6).
2. **Yahoo-Screener-Pool-Untergrenze** → OFFEN, baubar. Ein still
   schrumpfender Pool lässt echte Kandidaten nie ins Universum (unsichtbarste
   Klasse, kein Signal). Coverage_pct=None heute → keine Größen-Untergrenze.
3. **FINRA/DTC-Drift** → OFFEN, braucht erst Diagnose. DTC speist Earliness
   (AUC 0.77, stärkstes Signal); nur Call-Erfolg geprüft, keine DTC-Inhalts-
   Sanity.
4. **RVOL-Phasen-Bedeutung** = das **γ-2-Thema** (RVOL-Normalisierung).

### γ-2 (RVOL-Normalisierung) — BLOCKIERT, eigenes Projekt
4 Vorbedingungen: premarket-Datenbasis dünn · Cron-Drift absorbiert (#295) ·
`rel_volume_raw`-Feld ungebaut · Skalierer 0.10/0.40 ungestützt. Reihenfolge:
Daten → Sweep → rel_volume_raw → Schwellen → Flip. Kopplung: bei Aktivierung
BEIDE Soll in `CONSISTENCY_EXPECTED_STATE` paaren (sonst S13-Drift).

### Borrow
- **CTB-Persistenz** ✅ (#309). **Borrow-Coverage-Wächter B baubar** —
  borrow ist Tier-2-registriert, generische `aggregate_provider_fails`-
  Konsekutiv-Logik fängt ihn bereits; nur Diagnose 04.06.: kein sustained-
  Ausfall-Sample → „tot"-Schwelle gegen abwesenden Fehlermodus geraten. Erst
  bei echtem Borrow-Degradationsfall kalibrieren.

## 5) STRATEGISCHE ROADMAP
- Entry-Timing-Modul (★★★, 10.06.).
- **Annahmen-Inventur als wiederkehrende Methode** — Runde 1 (Provider) fertig;
  systematisches Durchleuchten dunkler Ecken statt reaktivem Stolpern.
- γ-2 RVOL-Normalisierung (★, blockiert).
- Phasen-/perzentil-basierte Schwellen statt fester Absolut-Schwellen (an
  Daten-Reife gekoppelt).
- Borrow-Fee + Utilization in score() (stärkste Squeeze-Prädiktoren) — bei
  reifer CTB-Coverage.
- **Externer Trigger / Dead-Man-Switch außerhalb GitHub Actions** — deckt
  Cron-Drops (~20 %) per Re-Dispatch UND das Failure-Fate-Problem. MUSS extern
  (Cloudflare-Worker). Bezieht sich auch auf die JSONL-Resolver-Lücke (s. §6).
- Backup/Disaster-Recovery (08.06.): lokaler git mirror | Daten-Export
  außerhalb GitHub | Spiegel auf anderem Account.
- Konsistenz-Wächter-Ausbau (Projekt C, S13): weitere stabile Flags additiv.
- PR-CI-Ausbau (#316): heute 5 Checks; volle 86-Test-Suite später inkrementell
  (erst Hermetik-Triage).

## 6) CODE-HYGIENE-BACKLOG (mit Status)
- **★ JSONL-Resolver-Lücke** (neu, Diagnose 05.06.): `grep -v '\.json$'` in
  **beiden** Workflows (`ki_agent.yml:93`, `daily-squeeze-report.yml:201`)
  erkennt `.jsonl` NICHT → bei Daily×ki_agent-Überlapp (postclose-Drift landet
  nahe `:17`-Tick) bricht der Rebase ab, sobald `health_check_log.jsonl`/
  `provider_health.jsonl` konfligieren. **main selbstheilend** (nächster
  sauberer Tick / daily-getriggerter ki_agent), **KEIN echter Datenverlust**
  (nur generierte/Append-Logs; score_history/backtest_history/Gist unberührt).
  Kosten: wiederkehrende FAILED-Actions-Mail + 1 Tick Telemetrie übersprungen.
  Fix offen: Pattern auf `.jsonl?$` erweitern — **`--ours`** (einfach, verliert
  1 Tick Append-Zeilen) vs. **Union-Merge** (korrekt, kein Verlust). Workflow-
  Tweak.
- **★ Recovery-Umleitung bei Gist-Body-Korruption** (Folge-PR zu #322): bei
  `body_ok=False` Positionen ERHALTEN (wie `gist is None` → Recovery-Kette)
  statt `positions={}` zu schreiben — Schadens-Vermeidung statt nur Detektion.
  Verhaltens-Change (größer als #322).
- **★ Yahoo-Screener-Pool-Untergrenze** (neu) → s. §4 Inventur Punkt 2.
- **★ FINRA/DTC-Drift-Diagnose** (neu) → s. §4 Inventur Punkt 3.
- **★ available/fee-Knappheits-Proxy** nach Entry-Modul — Borrow-Knappheit
  als Squeeze-Substrat.
- **★ 86-Test-Suite inkrementell in CI** (nach Hermetik-Triage).
- **★ Pre-existing: unescaptes `${price_str}`** `generate_report.py:5797` im
  **toten** `_build_card_ctx`-`else`-Zweig (CARD_COCKPIT_ENABLED=True → nie
  gerendert, heute harmlos). `mock_test_gist_action_token_routing` ist deshalb
  **rot auf main**, die advisory CI (#316) fängt ihn NICHT (fährt nur
  Golden + 4 Lints, nicht diesen Mock-Test). Separater Aufräum-PR.
- **rsi14=None-Fixture** → ERLEDIGT (#321).
- **or-0-Defaults Persist-Fix** (dtc/rvol/Bonus → None) → OFFEN, niedrig, nur
  bei Bedarf (v4-Sample 0 Fälle).
- **finviz Flag-aus + α** → OFFEN, an Daten-Reife gekoppelt.
- **Borrow-Naming-Cleanup** (`IBKR_*` → `IBORROWDESK_*`) → OFFEN, niedrig.
- v1/v2 → Jinja → OFFEN (Golden-Test #312 ist jetzt das Sicherheitsnetz).
- Cockpit Stage 3 (.sb-Reste) → VERTAGT.

## 7) ARCHITEKTUR-ANKER
- **★ Advisory PR-CI (NEU, #316):** `.github/workflows/pr-checks.yml`,
  `on: pull_request`, 4 Lints + Outer-Page-Golden. **NICHT required**, keine
  Branch-Protection → `check_run`-Signal, blockiert Self-Merge nicht. Install
  = **nur `jinja2>=3.1.0`** (NICHT requirements.txt — pandas_ta crasht am
  yfinance-Stub `__spec__=None`). Einziger PR-triggernder Workflow.
- **★ S14 + Gist-Body-Sanity (NEU, #314 + #322):** `last_successful_gist_pull`
  (`gist_pull_state.json`) wird im HTTP-Gist-Erfolgszweig NUR bei `body_ok`
  gesetzt (`_extract_data -> tuple[dict, bool]`, `positions`-Key-Präsenz-
  Diskriminator VOR der `or "{}"`-Maskierung). S14 WARN@26h, beide Pfade,
  None-tolerant. Fängt jetzt Token-Tod UND Body-Korruption. Restkante:
  Recovery-Umleitung (§6).
- **Outer-Page-Golden (#312):** Render-LOGIK-Netz mit fixen Fixtures, KEIN
  Produktions-Daten-Abbild. Render-Pfad **pandas_ta-invariant**
  (`_HAS_PANDAS_TA` nur in Fetch-Funktionen). Bei Output-Change: lokal laufen
  + `UPDATE_GOLDEN=1` + Golden mit-committen (CLAUDE.md-Pflichtregel).
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

## 8) LESSONS (04.–05.06.2026)
- **CI-Env ≠ local-Env schlägt in BEIDE Richtungen zu (#316):** Sandbox OHNE
  pandas_ta → Golden lief lokal grün; Runner MIT pandas_ta → `find_spec`-
  ValueError am spec-losen yfinance-Stub → rot. Der Reflex „requirements.txt
  für Sicherheit" hat das Flaky ERST erzeugt; Minimal-Deps war richtig.
  „Lokal grün" ist kein Beweis — der erste echte Runner-Lauf ist die Wahrheit.
- **Golden = Render-LOGIK-Netz, kein Produktions-Daten-Abbild:** testet mit
  fixen Fixtures die Render-Logik, nicht Werte. pandas_ta beeinflusst nur
  Daten (rsi14), nie Render-Logik → ta=None-Golden byte-gleich zum CI-Render,
  keine Produktions-Divergenz.
- **Guardian-Wert empirisch bestätigt (#322):** der Architektur-Zweitblick
  fing 3 Doku-Inkonsistenzen (Spec/Kommentare sagten „Body-Korruption out-of-
  scope", obwohl der PR sie schloss), die die deterministische CI NICHT fängt.
  Mechanik (CI) vs. Konsistenz/Bedeutung (Guardian/Mensch) — saubere Trennung.
- **Annahmen-Inventur-Faden:** `provider_health` prüft fast überall „Call
  funktioniert / Ticker-Abdeckung", selten „Inhalt korrekt / Einheit stabil /
  Pool groß genug". **borrow** (#292) ist das EINZIGE Vorbild-Muster mit echtem
  Inhalts-`success_check` — Blaupause für die anderen, falls eine Klasse
  kritisch gewichtet wird.
- **Stilles Netz reißt unbemerkt ohne Automatik (#313→#315→#316):** lokal-
  only-Test ist nur so gut wie die Disziplin, ihn zu fahren. #316 (advisory
  CI) + CLAUDE.md-Pflichtregel schließen die Klasse — und die CI lieferte im
  ALLERERSTEN Einsatz Wert (fing die pandas_ta-Inkompatibilität).
- **Selbstheilung kaschiert wiederkehrende Strukturlücken (JSONL-Resolver):**
  der Daily×ki_agent-Konflikt heilt sich jedes Mal selbst — aber erzeugt jedes
  Mal eine FAILED-Mail + überspringt einen Tick. „Selbstheilend" heißt nicht
  „kein Problem"; die wiederkehrende Failure-Mail IST das Symptom.
