# Session-Handover — Stand 21.05.2026

## Premium-Ziel

> „Ein System, das sich so weit selbst überwacht, dass meine menschliche
> Aufmerksamkeit komplett frei wird für die Fragen, die nur ich beantworten kann."

**Leitlinie:** KI überwacht die **Mechanik** (Feld leer, Provider down,
Struktur kaputt, Daten-Drift). Mensch validiert die **Bedeutung** (ist die
Edge echt? trägt das Setup? kaufe ich oder schau ich nur?).

**Vorhandene Bausteine (alle live auf `main`):**

- **HTML-Sanity S9 Stufe 1 + 2** (PR #237 + #241) — fängt strukturelle
  DOM-Defekte, blockt Push bei CRIT
- **`quote_proxy` Tier-2-Probe** (PR #242) — fängt Worker-Tod + Yahoo-v8-
  Bruch serverseitig im Daily-Run
- **Health-Check S1–S8** — State-Invariants (score_history, setup_scores,
  current_price, backtest_history-Disziplin, agent_signal-Overlap,
  Digest-Push-Frische)
- **Code als read-only Diagnose-/Rat-Agent** — Easy frägt, Code prüft +
  rät ehrlich, Easy entscheidet

**Geplante Bausteine:**

1. **Daten-Integritäts-Check** — „Feld seit N Tagen 0 % gefüllt → WARN".
   Hätte den `hist_5d`-Bug (PR #244) nach 1 Tag statt 1 Woche gefangen.
2. **Periodische Diagnose-Subagents** — `manual_personal`-Check (sauber
   bleibt?), Backtest-CI-Breite (schrumpft?), Provider-Drift, Confidence-
   Stale-Check.

**Prinzip:** Schicht für Schicht. Jede neue Sonde wird geprüft, bevor die
nächste draufkommt. **Nicht durch „muss gelingen", sondern durch
prüfen-verstehen-entscheiden.**

## Heute implementiert (chronologisch)

- `a5787d6` (gestern) feat: Score-Delta T-1 ins Cockpit-Setup-Pillar
- `4673859` (gestern) Merge PR #236 Cockpit-Delta — iPhone-verifiziert
- **PR #237** HTML-Sanity S9 Stufe 1 (4 Top-Counts, CRIT blockiert
  `git push` via `sys.exit(1)`) — gemerged
- **PR #238** `expectancy_diagnose.py` CLI (Source-Trennung daily/bootstrap +
  Bootstrap-95 %-CI). Befund: **kein daily-Bucket hat heute belastbare
  Expectancy**, alle CIs kreuzen die Null. Tool bleibt ad-hoc-CLI, kein
  Frontend — gemerged
- **PR #241** HTML-Sanity Stufe 2 (Pro-Card-Vollständigkeit + Setup-
  Pillar-Numerik > 0; 7 Gold-Checks, Setup-non-numerisch = IMMER CRIT) —
  gemerged
- **PR #242** `quote_proxy` Tier-2-Provider-Probe (1× pro Daily-Run pingt
  Worker → Yahoo v8; fängt Worker-tot + Yahoo-Bruch; CORS bewusst nicht,
  Browser-only) — gemerged
- **PR #243** `last_successful_run` Liveness-Marker-Fix (toter Code seit
  14.05.: Feld wurde nur bei 0 Fails gesetzt → permanent null. Jetzt
  `n_runs > 0` als Bedingung) — gemerged
- **PR #244** Backtest-Daten-Integrität (2 Bugs):
  - `hist_5d`-Propagation im Enrichment-c.update-Block — fehlte seit PR #142,
    Folge: 3 von 4 Trend-Feldern in `backtest_history.json` zu 0 % gefüllt
    seit 14.05. (`si_trend_5d_slope` lief separat über FINRA-Pfad weiter)
  - Wochenend-Schreibschutz für `_append_backtest_entries` — verhindert
    Akkumulation outcomeloser Sa/So-Einträge (96 Leichen Bestandsaufnahme)
  — gemerged

## Aktive Position (im Secret `POSITIONS_JSON`)

- **AMC** — Halt, `no_exit_alerts=true`
- **IONQ**, **RR** — unverändert
- **CRMD** — ~−5 %, halten

## Verifikation ausstehend

- **PR #244 Live-Verifikation:** beim nächsten postclose-Daily-Run (Werktag,
  21:17 UTC) prüfen, dass die neuen V4-Einträge tatsächlich `rvol_buildup_5d`,
  `vol_stability_5d`, `coiled_spring_score` nicht-null haben. Schnell-Check
  via `python3 -c "import json; bh=json.load(open('backtest_history.json'));
  v4=[e for e in bh if e.get('backtest_schema_version')==4 and e['date']=='<heute>'];
  print({k: sum(1 for e in v4 if e.get(k) is not None) for k in ['rvol_buildup_5d',
  'vol_stability_5d', 'coiled_spring_score']})"`.
- **Wochenend-Schreibschutz #244**: bei nächstem Easy-Sa/So-Trigger via
  `workflow_dispatch` erwartet — Workflow-Log enthält
  `Wochenend-Eintrag (...) übersprungen`, `backtest_history.json` unverändert.

## Geplante Aufgaben + Wiedervorlagen

### Geändert nach #244-Fund

- **~04.06.2026** (statt 28.05.) — **Earliness-AUC erste Schätzung r5d**.
  Grund: `hist_5d`-Bug hielt 3 von 4 Trend-Feldern bis 21.05. auf 0 %.
  AUC-Uhr startet effektiv 21.05. neu (Fix nicht rückwirkend). Kriterium:
  n und Klassen-Balance pro Feld × Horizont **prüfen, BEVOR** AUC gerechnet
  wird (analog Expectancy-Befund #238 — eine schöne Zahl auf zu dünnem n
  ist trügerische Präzision).
- **~14.06.2026** — Earliness-AUC r10d (längerer Outcome-Lag).
- **07.06.2026** — Earliness V3 bleibt im Kalender, **Entscheidung hängt
  an obiger AUC**. Falls 04.06.-Schätzung noch zu dünn → V3 weiter schieben.

### Unverändert

- **30.05.2026** — PR-γ Score-Inflation-Normalisierung (manueller Merge)
- **02.06.2026** — Chart-Indikatoren (TTM Squeeze / VWAP / OBV) als
  ENTRY-Score-Komponenten
- **10.06.2026** — ★★★ **Entry-Timing-Modul START** (höchste Prio,
  mehrwöchig)
- **30.06.2026** — Erste belastbare Backtest-Auswertung
  (daily-≥70-Bucket-CI kreuzt Null nicht mehr — neues Kriterium aus #238)
- **02.07.2026** — Premium-Daten-Stack

### Sonstige geplante Aufgaben

- **HTML-Sanity Phase 1c** (irgendwann nach 1b stabil): Restliche
  10er-Assertion-Liste + Setup-Pillar-Range-Check (z. B. 0–100).
- **Sortino + Kelly-Inputs** als Spalten ans `expectancy_diagnose.py`
  hängen (CLI-Output, **kein Frontend** bis Datenlage trägt).

## Optional / niedrig priorisiert

### Nachzügler (kein Datum, niedrige Prio)

- **Cleanup der 96 Wochenend-Leichen** aus `backtest_history.json` —
  separater JSON-PR, reiner Daten-Eingriff (kein Code).
- **Verifikation #244-Fix im echten Lauf** — siehe „Verifikation
  ausstehend" oben. Sobald grün, hier streichen.

### Code-Hygiene-Backlog

- ✅ Cockpit Stage 3 `.sb`-Cleanup (20.05. ausgeführt, 0 Leichen)
- ✅ **`generate_report.py`-Split — bewertet, großer Split verworfen
  (21.05.2026).** Read-only-Diagnose: kein Split vor Entry-Modul (10.06.)
  nötig oder klug. Gründe: (1) Entry-Modul passt additiv in bestehende
  Score-Pipeline (Pattern wie `apply_conviction_scores`/`apply_monster_score`)
  — kein Split-Voraussetzung. (2) Größter Block `generate_html_v1`
  (6806 Z., 40.8 %) ist ein f-String, mechanisch nicht splittbar ohne
  komplette Jinja-Migration. (3) Kritischer globaler State `_FX_USD_EUR`
  + `_SCORE_CONFIDENCE` (via `globals()`-Trick in `main()` gesetzt, in
  Display gelesen) = stille-Degradations-Falle bei Split. Trading-Wert
  null, Risiko hoch → verworfen.

  **Reihenfolge-Empfehlung:**
  1. **10.06.: Entry-Modul ADDITIV** — `compute_entry_score` +
     `apply_entry_scores` in Score-Pipeline ODER eigene
     `entry_timing.py` nach `health_check.py`-Pattern; neuer
     4. Cockpit-Pillar Setup → Monster → KI → **Entry**. Kein Split.
  2. **Später, separat, kein Druck:** `backtest_history.py` extrahieren
     (428 Z., 1 Cross-Call, Vorbild `score_inflation_log.py`, Risiko
     niedrig). Nicht zwingend.
  3. **Niemals (oder erst nach Nachweis):** `generate_html_v1`-Jinja-
     Vollmigration. Trading-Wert nicht zu rechtfertigen.

  Falls je wieder Thema: Diagnose eindeutig, nicht blind splitten.
- 🔧 Offen (Engineering-Mehrwert, niedriger Trading-Wert):
  - v1/v2-Render → reines Jinja (siehe oben — niemals ohne klaren
    Trading-Wert)
  - Template-Engine statt f-strings (eliminiert
    `lint_jsformat_escape.py`-Bugklasse strukturell)

## Architektur-Anker (nicht in CLAUDE.md, wichtig)

- **HTML-Sanity S9 Stufe 1 + 2** live: 4 Top-Counts (Stufe 1, gemergt
  PR #237) + 7 Pro-Card-Gold-Checks inkl. Setup-Pillar-Numerik (Stufe 2,
  gemergt PR #241). CRIT-Pfad blockiert Push via `sys.exit(1)` →
  `if: success()` greift im Commit-Step. WARN landet im JSONL für
  Phase-3-Digest.
- **Health-Check liest sonst NUR JSONL/Dicts** (S1–S8); S9 ist der einzige
  HTML-Aware-Check.
- **`quote_proxy` Tier-2-Provider** (PR #242): einmal pro Daily-Run wird
  der Cloudflare-Worker mit Bench-Ticker NVDA gepingt. Fängt
  Worker-tot + Yahoo-v8-Bruch (Worker antwortet 200 mit `error`-Feld).
  CORS bewusst nicht — Browser-only-Klasse.
- **Backtest-Schreibpfad** (seit PR #244): `_append_backtest_entries`
  schreibt nur an Trading-Tagen; `hist_5d` propagiert via c.update ins
  Top-10-Stock-Dict → 3 zusätzliche Trend-Felder werden ab nächstem
  Daily-Run real gefüllt.
- **`last_successful_run`** (seit PR #243) = echter Workflow-Lauf-
  Liveness-Marker (gesetzt wenn `n_runs > 0`, unabhängig vom Fail-Count).
  `last_digest_sent` bleibt der ntfy-Push-Marker für S8 — beide Felder
  messen unterschiedliche Dinge.
- **Score-Delta T-1** (`_cockpit_delta_html`) live im Cockpit-Setup-Pillar
  seit PR #236. Schwellen |Δ| < 2 leer · 2–5 grau · ≥ 5 farbig ▲▼ ·
  ≥ 15 bold. Quelle: `sparkline.scores`.
- **Bestehende Anker unverändert:** Earliness V2 (DTC, AUC 0.77),
  Phase-2 Exit (6 Trigger), Live-Polling Cloudflare-Worker,
  Cockpit-Layout seit #199, Token-Encryption AES-GCM/PBKDF2,
  Service-Worker raus seit #188.

## Lessons aus dieser Session

- **`hist_5d`-Bug-Lehre — stiller Tod im Logging:** Pipeline kann
  „erfolgreich" laufen und trotzdem leeren Output produzieren.
  Health-Check meldet grün (S1–S8 prüfen Existenz, nicht Coverage),
  Trend-Felder bleiben 1 Woche lang zu 0 % gefüllt. **Nur die Frage
  „trägt die Datenlage?"** (AUC-Reife-Diagnose) deckte es auf. Daraus
  folgt die geplante Daten-Integritäts-Sonde: „Feld seit N Tagen 0 %
  gefüllt → WARN" hätte den Bug nach 1 Tag statt 1 Woche gefangen.
- **Stufe-3-Browser-Check verworfen:** Headless-Playwright im Workflow
  würde CORS-Drift und JS-Bugs fangen, aber zum Preis von 1–2 d
  Implementations-Aufwand + Selektoren-Wartung bei jeder UI-PR. Das
  heutige 21.05.-CORS-Erlebnis war sofort sichtbar (Frontend-Indicator
  `quote-live-stale`, Tooltip „Live-Quelle nicht erreichbar") — Stage 3
  würde nur den Bemerk-Zeitpunkt um wenige Stunden vorverlegen.
  **Wartungslast > Trading-Wert.** Falls je wieder Thema:
  Frontend-Boot-Self-Check (2–3 h) statt Headless-Browser.
- **Top-10-Fluktuation / Hysterese verworfen:** 50.9 % Eintags-Wonder im
  Top-10 sind **gesund, kein Bug**. 74.5 % der Exits sind Pool-Dropouts
  (Stufe-1-Screener-Wankelmut Yahoo/Finviz), nicht Score-Drift. RVOL
  ist nicht der Treiber (88 % der Dropouts hatten am Exit-Tag noch RVOL ≥
  1.5). Hysterese hätte 0–3 Setups gerettet + 30+ Verlierer-Karten
  länger sichtbar gemacht (rausgefallene Ticker liefern 5d-Forward-
  Median **−8.68 %**). Top-10 = Such-Stream für NEUE Einstiege, NICHT
  Hold-Liste. Awareness-Bedarf deckt `manual_personal`/Watchlist-Add ab.
  Falls je wieder Thema: **nicht neu bauen.**
- **Arbeitsweise: Easy will Ideen GEPRÜFT, nicht bestätigt.** „Nichts
  bauen" ist valides Ergebnis wenn begründet. Schleife: **Idee →
  read-only-Diagnose → bei Trading-Impact Code-um-Rat → verstehen →
  entscheiden.** Confirmation-Bias-Schutz: wenn Easys These und Daten
  kollidieren, gewinnt die Datenseite. Ich melde Widerspruch, ohne
  zu glätten. Belegt heute durch: Hysterese-Verwerf, Stufe-3-Verwerf,
  Frontend-Expectancy-Verwerf (PR #238 zeigt n nicht belastbar).
- **Draft-vs-Live-Verify** (aus 20.05.): Draft-PRs sind nicht im
  Live-Deployment. Vor jedem UI-Verify Deployment-Stand prüfen.
- **Falsche Metrik schlägt dünne Daten** (aus 20.05.): Hit-Rate verzerrt
  bei asymmetrischer Strategie. Aber: jede Metrik mit zu dünnem n
  verpackt nur Rauschen schöner. Echter Confounder im Backtest:
  Bootstrap-Formel ≠ Live-Formel.
