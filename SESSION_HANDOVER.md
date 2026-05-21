# Session-Handover — Stand 20.05.2026

## Heute implementiert (chronologisch)

- `a5787d6` — feat: Score-Delta T-1 ins Cockpit-Setup-Pillar (additiv, kein
  Cleanup-Ballast)
- `4673859` — Merge PR #236 (Score-Delta Cockpit). Live deployed +
  iPhone-verifiziert (Deltas sichtbar, XPOF/SLS strong). Komplett
  abgeschlossen.
- `f3a8da9` — feat: HTML-Sanity-Check S9 (Frontend-Awareness Phase 1a) →
  **PR #237 (Draft, noch nicht gemerged)**. 4 Dateien:
  `scripts/check_html_assertions.py` + `scripts/mock_test_html_assertions.py`
  neu, `health_check.py` +36/−1, `generate_report.py` +86/−1. Tests:
  11/11 neue + 28/28 bestehende grün. Push-Skip via `sys.exit(1)` → roter
  Step → Commit-Step `if:success()` übersprungen → alter `index.html`
  bleibt live. Sofort-ntfy bei CRIT.
- `cce0350` — chore: CLI-Diagnose `scripts/expectancy_diagnose.py` →
  **PR #238 (Draft, noch nicht gemerged)**. Analyse-only, pure stdlib
  (random + statistics), kein Tool-Eingriff. Berechnet Expectancy +
  Bootstrap-95%-CI pro Bucket × Source × Horizont. Source-Trennung
  daily vs. bootstrap aufgedeckt: kein daily-Bucket hat heute eine
  belastbare Expectancy-Aussage im 5d/t0-Pfad (alle CIs kreuzen die
  Null).

## Aktive Position (im Secret POSITIONS_JSON)

- **AMC** — Halt, `no_exit_alerts=true`
- **IONQ**, **RR** — unverändert
- **CRMD** — ~−5 %, halten

## Verifikation ausstehend

- **PR #237 (HTML-Sanity S9):** VOR Merge lokaler Gesund-Lauf
  (`python generate_report.py` lokal, prüfen dass S9 bei gesundem HTML
  0 Fails meldet und NICHT false-positive blockiert). Gefährlichster
  Fall ist genau das: false-positive blockiert gesunden Daily-Run.
  Danach manueller Easy-Merge (Workflow-Logik + Health-Check =
  manuell-pflichtig per CLAUDE.md-Klassifikation).
- **PR #238 (expectancy_diagnose):** Merge unkritisch (analyse-only,
  Tool wird nur ad-hoc auf CLI ausgeführt), wann immer Easy mag.

## Geplante Aufgaben

- **`last_successful_run`-Cleanup** — separater kleiner PR. Toter Code
  seit 14.05.: wird nur bei 0 Fails gesetzt, steht damit immer `null`;
  S8-Invariant nutzt heute `last_digest_sent` als Liveness-Quelle. Fix:
  Bedingung lockern auf `if n_runs > 0` = echter Liveness-Marker
  unabhängig vom Fail-State. Anlaufstelle:
  `scripts/health_check_digest.py:298`.
- **Sortino + Kelly-Inputs als Spalten** ans `expectancy_diagnose.py`
  hängen (Zahlen-Ausgabe, **KEIN Frontend**). Sortino > Sharpe weil nur
  Abwärts-Vola bestraft = respektiert rechtsschiefe Strategie. Gleiche
  n-Datensperre + Belastbarkeits-Marker wie heute.
- **HTML-Sanity Phase 1b** (später, nach 1a stabil): Pro-Card-
  Vollständigkeit + numerische Setup-Pillar-Validierung + Rest der
  10er-Assertion-Liste.

## Optional / niedrig priorisiert

### Strategische Roadmap & Wiedervorlagen

- **28.05.** — Earliness-AUC Re-Test
- **30.05.** — PR-γ Score-Inflation-Normalisierung
- **02.06.** — Chart-Indikatoren (TTM Squeeze / VWAP / OBV) als
  ENTRY-Score-Komponenten
- **07.06.** — Earliness V3
- **10.06.** — ★★★ **Entry-Timing-Modul START** (höchste Prio)
- **30.06.** — Erste belastbare Backtest-Auswertung. **Neues
  konkretes Kriterium** (ersetzt das alte „n ≈ 100"): daily-≥70-Bucket
  mit Bootstrap-CI, das die Null **NICHT mehr kreuzt**. Erst dann lohnt
  es, Expectancy/Sortino ins Frontend zu schieben + Hit-Rate-SVG zu
  entschärfen. `expectancy_diagnose.py` bis dahin periodisch laufen
  lassen und CI-Schrumpfung beobachten.
- **02.07.** — Premium-Daten-Stack

### Code-Hygiene-Backlog

- ✅ **Cockpit Stage 3 `.sb-`-Cleanup** — erledigt/obsolet (20.05.).
  Audit ergab 0 echte Leichen: alle `.sb-*`-Klassen haben aktive
  Konsumenten (Methodik live, `sb-conf-*` Cockpit live 82×, Fallback-
  Rollback-Pfad). 0 JS-Selektor-Treffer auf den Verdachts-Klassen.
  Kein PR nötig.
- 🔧 **Offen, drei große Engineering-Themen** (niedriger Trading-Wert,
  aber Risiko-Reduzierer):
  - v1/v2-Render → reines Jinja (Outer-Page herauslösen, dann v1
    entfernen)
  - `generate_report.py`-Monolith splitten — wäre Risiko-Reduzierer
    VOR Entry-Timing-Modul-Start 10.06.
  - Template-Engine statt f-strings (eliminiert
    `lint_jsformat_escape.py`-Bugklasse strukturell)

## Architektur-Anker (nicht in CLAUDE.md, wichtig)

- **Score-Delta T-1** (`_cockpit_delta_html`) jetzt live im
  Cockpit-Setup-Pillar. Schwellen `|Δ| < 2` leer / `2–5` grau /
  `≥ 5` farbig ▲▼ / `≥ 15` zusätzlich bold. Quelle:
  `sparkline.scores`. `scripts/mock_test_cockpit_delta.py` riegelt
  Re-Drift ab.
- **HTML-Sanity S9** (nach #237-Merge wirksam): 4 deterministische
  Top-Counts gegen `index.html`, CRIT blockiert `git push`
  (Hybrid-Variante-B), WARN ins JSONL. Severity wird **crit** ab
  `actual ≤ expected/2` ODER wenn `card-cockpit`-Count ≠
  `article`-Count (Layout-Mix-Indikator).
- **Health-Check liest sonst NUR JSONL/Dicts** (S1–S8), niemals das
  HTML — S9 ist die erste Frontend-Awareness-Sonde im Pipeline-Check.
- **Bestehende Anker unverändert:** Earliness V2 (DTC, AUC 0.77),
  Phase-2 Exit (6 Trigger), Live-Polling via Cloudflare-Worker,
  Cockpit-Layout seit #199, Token-Encryption AES-GCM/PBKDF2,
  Service-Worker seit #188 raus.

## Lessons aus dieser Session

- **Draft-vs-Live-Verify:** Draft-PRs sind **nicht** im Live-Deployment.
  Verify auf der Live-Site zeigt immer den `main`-Stand. „Feature
  unsichtbar" bei Draft-Verify ist erwartbar, kein Bug. Vor jedem
  UI-Verify klären: läuft der Code überhaupt im deployten `index.html`?
  Der Daily-Run deployt hartkodiert `ref:main` + `push origin main`
  → kein Pre-Merge-Preview ohne Workflow-Umbau. Verwandt zur
  Token-Phantom-Klasse: vor jedem Revert-Verdacht erst den
  Deployment-Stand prüfen.
- **Falsche Metrik schlägt dünne Daten:** Hit-Rate verzerrt bei
  asymmetrischer Strategie systematisch — 42 % liest sich wie
  Verlierer, obwohl Expectancy positiv sein kann. **Aber** PR #238
  zeigte zugleich: kein daily-Bucket hat heute eine belastbare
  Expectancy (alle 95 %-CIs kreuzen die Null). Lehre: das
  eigentliche Problem ist **Daten-Reife**, nicht die Mathematik.
  Jede Metrik mit zu dünnem `n` verpackt nur Rauschen schöner. Der
  echte Confounder im Backtest ist **Bootstrap-Formel ≠ Live-Formel**
  — nicht V1/V2-Earliness und nicht PR-γ (beide wirken nicht aufs
  `score`-Feld bzw. nur premarket). Bestätigt die Disziplin: wenige
  Trades, bis die Basis sauber ist.
- **Top-10-Fluktuation / Hysterese verworfen:** Hohe Top-10-Rotation
  (50.9 % Eintags-Wonder) ist **gesund, kein Bug**. Diagnose: 74.5 %
  der Exits sind Pool-Dropouts (Stufe-1-Screener-Wankelmut Yahoo /
  Finviz), nur 11 % Score-Überholung, **RVOL nicht der Treiber**
  (88 % der Dropouts erfüllten die RVOL-Schwelle am Exit-Tag noch).
  Hysterese als Hebel **verworfen**: rausgefallene Ticker liefern
  Forward-Return 5d Median **−8.68 %**, Win-Rate 10 %, 76 % kommen
  nie zurück — das Exit-Signal ist statistisch korrekt. Hysterese
  hätte 0–3 Setups „gerettet" + 30+ Verlierer-Karten länger
  sichtbar gemacht. **Mentales Modell:** Top-10 = Such-Stream für
  NEUE Einstiege, NICHT Hold-Liste. Awareness-Bedarf deckt
  `manual_personal` / Watchlist-Add per UI ab (User-im-Loop statt
  Auto-Verklebung). Falls je wieder Thema: Daten sind eindeutig,
  **nicht neu bauen**.
