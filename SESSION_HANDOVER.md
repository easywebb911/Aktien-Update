# Session-Handover — Stand Ende 13.05.2026

## Heute implementiert (chronologisch, alle gemerged via PR)

Die Sitzung startete als Backtest-Pollution-Cleanup und entwickelte
sich zur Folge-Bug-Kaskade rund um die Zwei-Run-Architektur (PR #124),
plus zwei größere Features: Live-Quote-Polling via Cloudflare-Worker
und zwei strukturelle CI-Lints.

- **`41c54ad` PR #131** — `fix: remove 22 polluted backtest entries
  from 2026-05-13`. Manuelle `workflow_dispatch`-Trigger heute Nachmittag
  während laufender US-Session schrieben mit Default `postclose` 22
  Intraday-Mid-Day-Einträge (5 Ticker mit RVOL < 0.2, zwei VIX-Snapshots
  17.99/18.12 im selben Run). Cleanup: alle 13.05.-Einträge raus,
  `app_data.json.run_phase` von `postclose` → `premarket` zurückgesetzt
  (sonst blockte ki_agent weiter Anomaly-Pushes).
- **`19c6cdb` PR #132** — `fix: workflow_dispatch run_phase validation —
  Default raus, Plausibilitäts-Override`. UX-Falle struktureller
  Fix: `daily-squeeze-report.yml` `workflow_dispatch.inputs.run_phase`
  ist jetzt `required: true` ohne Default. Neues Modul
  `scripts/resolve_run_phase.py` (Single-Source-of-Truth für die
  Resolution) wird via Workflow-Step `Resolve run phase` aufgerufen
  und schreibt `RUN_PHASE` nach `$GITHUB_ENV`. Plausibilitäts-Override:
  13:30 ≤ UTC < 20:00 + `postclose` → `premarket`; UTC ≥ 20:00 +
  `premarket` → `postclose`. Cron-Trigger ausgenommen. 12 Mock-Tests.
- **`f60bcec` PR #133** — `fix: Recalculate-Dispatch sendet client-side
  bestimmtes run_phase (HTTP 422 Folge-Bug PR #132)`. PR #132 hatte die
  Frontend-Recalculate-Funktion übersehen: `dispatchWorkflow` schickte
  weiterhin nur `{ref: GH_BRANCH}` ohne `inputs.run_phase` →
  GitHub-API HTTP 422. Neuer JS-Helper `_computeClientRunPhase()`
  bestimmt die Phase aus `new Date().getUTCHours()/getUTCMinutes()`,
  Dispatch-Body sendet `inputs: {run_phase: …}`. KI-Agent-Pfad
  unverändert (kein run_phase-Input im ki_agent.yml).
- **`87beb5b` PR #134** — `fix: Watchlist-Drawer Momentum live aus
  _WL_CARDS.change überschreiben`. Quick-Fix für Easys DMRC-Diagnose:
  Drawer zeigte `+0,8 %` (eingebranntes card_html aus 12:05-UTC-
  Premarket-Run), real waren `+12,9 %` mid-day. Neuer JS-Helper
  `_patchWlMomentumLive(scope, ticker)` überschreibt **nach** dem
  `body.innerHTML`-Insert in `wlExpand` die Momentum-Box mit
  `_WL_CARDS[ticker].change` — andere Felder bleiben eingebrannt.
  10 Mock-Tests.
- **`5082fc7` PR #135** — `feat: Live-Quote-Polling für Watchlist-
  Drawer + Top-10-Detail (Cloudflare-Worker, Yahoo v8)`. Echte
  Echtzeit-Werte alle 15 s. Architektur-Wahl: Cloudflare Worker als
  CORS-Proxy zu Yahoo v8 chart (`/v8/finance/chart/{ticker}` —
  v7-quote verlangt seit Mai 2026 Crumb-Auth und antwortet sonst
  HTTP 401). Worker-Code in `cloudflare/quote-proxy/` (worker.js,
  wrangler.toml, README). Frontend-Polling-Modul in
  `generate_report.py` (start/stop/visibilitychange/DOM-Patch/Live-
  Indikator), Lifecycle in `wlExpand` + `toggleDetails`. Easy hat den
  Worker als `quote-proxy.easywebb.workers.dev` manuell deployed,
  URL als Repo-Secret `QUOTE_PROXY_URL` gesetzt. Initial-Commit
  startete mit v7-Endpoint, force-pushed auf v8 nach Easys
  Deploy-Test (HTTP 401 reproduziert). 16 Mock-Tests.
- **`f2c5198` PR #136** — `fix: redeploy-on-source-change übergibt
  run_phase an gh workflow run (HTTP 422 Folge-Bug PR #132)`. Dritter
  Aufrufer übersehen: `redeploy-on-source-change.yml` rief
  `gh workflow run daily-squeeze-report.yml` ohne `-f run_phase=…` auf
  → Auto-Redeploy nach Source-Pushes schlug fehl. Bash-Logik berechnet
  `NOW_HHMM=$(date -u +%H%M)` und mappt 1330–1959 → `premarket`,
  sonst `postclose`. 7 Mock-Tests.
- **`58759fa` PR #137** — `fix: quote_proxy_url_js im Context-Dict
  eintragen (NameError-Hotfix nach PR #135)`. PR #135 hatte die
  Konstante `const QUOTE_PROXY_URL = '{quote_proxy_url_js}'` im
  JS-Block, aber den Key im `_build_context`-Return-Dict + den
  Unpacker in `generate_html_v1` vergessen. Daily-Run crashte mit
  `NameError: name 'quote_proxy_url_js' is not defined`. Fix:
  Context-Key gesetzt, defensiver `ctx.get(..., "")`-Unpacker.
  10 Mock-Tests.
- **`612ddd2` PR #138** — `fix: unescaptes {intervalId, scope,
  indicator} in JS-Kommentar + neuer AST-Linter (CI-Gate)`. Zweite
  Welle des PR-#135-Bugs: ein JS-Kommentar
  `// ticker → {intervalId, scope, indicator}` blieb unescaped →
  Python interpretierte als Variable. Neuer Linter
  `scripts/lint_jsformat_escape.py` (AST-basiert, ~165 Z.) scannt den
  kompletten `generate_html_v1`-f-String gegen alle Top-Level-Namen
  aus `generate_report.py` + `config.py` plus Locals. Einzige
  Bug-Stelle: Z. 8203, gefixt durch `{{…}}`-Escaping. Workflow-Step
  `Lint JS-format escape` als zweiter CI-Gate neben `Lint chat
  template`. CLAUDE.md dokumentiert beide Linter komplementär.
  9 Mock-Tests.
- **`591792b` PR #139** — `fix: Jekyll-Pages-Build excludiert interne
  Doku ({{...}}-Liquid-Crash nach PR #138)`. PR #138 hatte in
  CLAUDE.md die `{{…}}`-Patterns wörtlich dokumentiert →
  GitHub-Pages-Jekyll-Build crashte mit `Variable '{{ escapeden …'
  was not properly terminated`. Pragmatischer Pfad statt
  `{% raw %}`-Tags: neues `_config.yml` mit `exclude:`-Liste —
  `CLAUDE.md`, `SESSION_HANDOVER.md`, `docs/`, `*.py`, `cloudflare/`,
  `scripts/`, `templates/`, `requirements.txt`, `Gemfile*`. Daten-
  JSONs und `index.html` bleiben Pages-erreichbar. 6 Mock-Tests inkl.
  Drift-Schutz (excludete konkrete Pfade müssen existieren).

---

## Aktive Positionen (im Gist `squeeze_data.json`)

Stand Ende 13.05.2026:

- **AMC**
- **SABR**
- **IONQ**

**Geschlossen heute:** DMRC mit ~+12 % Tagesgewinn verkauft. Trade-
Journal sollte den Eintrag (Entry/Exit-FX, max_setup_score,
duration_days) automatisch persistieren.

---

## Verifikation morgen (14.05.2026)

- **iPhone Live-Polling-Test** — Watchlist-Drawer öffnen für einen
  beobachteten Ticker. Grüner pulsierender `.quote-live-dot` muss
  erscheinen. Alle 15 s muss `.price-tag` (Preis) und die Momentum-
  Box (`.metric-box` mit `.m-lbl=Momentum`) sich aktualisieren.
  Tab wechseln → Dot gedimmt grün (`paused`). Drawer schließen → kein
  weiterer Worker-Request im Network-Tab. Top-10-Karte mit
  „Details anzeigen" → identisches Verhalten, Live-Dot lazy in
  `.score-block` injiziert.
- **Daily-Run heute Abend (21:00 UTC Postclose) + morgen früh
  (10:00 UTC Premarket)** müssen ohne `NameError` durchpassen — PRs
  #137 + #138 sind die Voraussetzung. `Resolve run phase`-Step-Log
  prüfen: `event=schedule`, korrekte Cron→Phase-Mapping.
- **Backtest-History-Sauberkeit** — heute Abend appendet der
  21:00-UTC-Postclose-Cron sauber neue 13.05.-Einträge mit echten
  EOD-Werten. Stichprobe `python -c "import json; d=json.load(open(
  'backtest_history.json')); print(sum(1 for e in d if e['date']==
  '13.05.2026'))"` — Erwartung ~10 (Top-N).
- **Erster voller Tag mit allen Anti-Inflation-Mechanismen** kombiniert:
  Conviction-75-Gating (PR #123, gestern), `run_phase`-Plausibilitäts-
  Override (PR #132, heute), Live-Polling (PR #135, heute). Push-Volumen
  pro Tag im `push_history` prüfen — Erwartung weiter im niedrigen
  einstelligen Bereich.
- **Daily-Run-Dauer beobachten** — heute mehrfach „mehrere Minuten"
  Laufzeit (anekdotisch, nicht aus Logs verifiziert). Falls erneut
  auffällig: Workflow-Step-Timings aus den Actions-Logs ziehen,
  Hauptverdacht sequenzielle API-Calls (Yahoo/Finviz/yfinance).
- **`score_inflation_log.jsonl`** sammelt weiter Daten — pro Daily-Run
  10 Zeilen, premarket-vs-postclose-Diff für identische Ticker. Tag 2
  von 5 ab morgen.

---

## Geplante Aufgaben + Wiedervorlagen

### Offene Aufgaben (nicht datums-getriggert)

- **Health-Check-Workflow Implementierung.** Spec liegt in
  `docs/health_check_spec.md` (PR #130 merged 13.05. mittags). Eigener
  4–6h Code-Slot, separate Session. Sechs State-Invariants + Provider-
  Health für 9 Quellen, 3-Tier-Severity. Spec ist SSOT — Code folgt 1:1.
- **Methodik-Display-Session: Standard- vs Maximal-Werte.** Asymmetrien
  wie `SUB_SI_TREND_DISPLAY_PTS_MAX=5` (Sub-Score-Cap) vs.
  `FINRA_ACCELERATION_BONUS=7` (on-top-Bonus bei Beschleunigung)
  korrekt im Methodik-Render zeigen. Heute schon dokumentiert in
  CLAUDE.md („Bedingte Boni — Display-String muss Pfad-Vielfalt
  zeigen"), Code-Anpassung steht aus.
- **Daily-Run-Dauer-Diagnose.** Step-Timings aus letzten 5 Workflow-
  Runs sammeln, Bottleneck-Hypothese (sequenzielle API-Calls)
  bestätigen. Falls bestätigt: `asyncio` / `concurrent.futures` für
  unabhängige Fetches.

### Wiedervorlagen mit Datum

- **14.05.2026** — iPhone Live-Polling-Test (s.o.), Daily-Run-
  Verifikation der heutigen 9 Merges (NameError-Freiheit).
- **14.–17.05.2026** — Score-Inflation-Empirik Tag 2–5; Conviction-
  Formel-Beobachtung Tag 3–6 (Spitze erreicht regelmäßig ≥ 75?).
- **15.05.2026** — Phase 3 Exit-Signale (Blow-off-Top + IV-Crush;
  Konzept liegt, Code noch nicht begonnen).
- **19.05.2026** — `app_data`-Recovery prüfen +
  `POSITIONS_JSON`-Secret löschen (Gist-Migration ist Ende April
  abgeschlossen, Fallback ist seitdem unaktiv).
- **02.06.2026** — Chart-Indikatoren prüfen (welcher Stand?
  Empirik-Review).
- **02.07.2026** — Premium-Daten-Stack prüfen (Polygon, IEX,
  Alpha Vantage paid-Tier vs. yfinance-Stack).

---

## Strategische Roadmap

### Übergeordnetes Ziel

Squeeze-Früherkennungssystem mit empirisch validierter Edge. Drei
parallele Arbeitsstränge laufen permanent nebeneinander:

- **Bauen** — Code-Erweiterungen (neue Trigger, UI-Ergänzungen,
  Persistenz-Schichten). Aktuell: Phase 3 Exit-Signale (IV-basiert,
  Wiedervorlage 15.05.), Code-Hygiene-Backlog Punkte 2/3/4/5-2/6-B,
  Health-Check-Workflow, Live-Polling-Erweiterung (falls Easy mehr
  Felder live haben will).
- **Sammeln** — passives Warten auf Backtest-, Earliness-, Conviction-,
  **Score-Inflations-** und **Push-Volumen-Empirik** (jeder Daily-Run +
  ki_agent-Tick füttert die History; seit PR #120
  `score_inflation_log.jsonl` mit Sub-Score-Breakdown). Aktuell:
  Conviction-Formel-Tag-3-bis-6, Setup-Inflation-premarket-vs-
  postclose-Diff, Push-Volumen-pre/post-Conviction-75.
- **Validieren** — Score-Logik gegen reale R-Werte testen, sobald genug
  Datenpunkte da sind. Aktuell: Daily-Run-Checks (NameError-Freiheit,
  Trigger-Verfügbarkeit, Push-Filter-Wirkung, Stale-Data-Drawer),
  Position-Verläufe (AMC/SABR/IONQ; DMRC heute geschlossen),
  Methodik-Konsistenz-Pflege.

### Drei Zeit-Achsen

**Kurzfristig (Tage bis 1–2 Wochen, aktiv planbar)**

- **Score-Inflations-Empirik** auswerten (Wiedervorlage 14.–17.05.).
  premarket-vs-postclose-Vergleich für identische Ticker, Sub-Score-
  Beitrag identifizieren. Danach Entscheidung über Schwellen-Tuning
  vs. rel_volume-Zeitnormierung.
- **Push-Volumen-Tracking** nach Conviction-75-Anhebung. Erwartung
  ~10/Tag → ~2–3/Tag. Falls noch zu laut: monster_backup-Schwelle
  90 → 95 oder Cooldown 6h → 24h.
- **Conviction-Formel-Beobachtung Tag 3–6.** Erreicht die Spitze
  regelmäßig ≥ 75? Sonst Re-Distribution-Vorschlag.
- **Phase 3 Exit-Signale** (Wiedervorlage 15.05.2026).
- **Stufe Mittel-2** — Earliness-Score-Effekt scharfschalten.

**Mittelfristig (Wochen, datenabhängig)**

- **Backtest-Validierung** — Frontend-Auswertung Backtest-T+0/T+1
  funktioniert erst belastbar, sobald je Score-Bucket
  (`<50`/`50–69`/`≥70`) mindestens 30 Tage Live-R-Werte vorliegen. Seit
  PR #124 fließen nur noch postclose-Werte in die Historie — saubere
  Datenbasis. Bahn A2 (Frontend-Auswertungs-Panel) erfordert
  ≥ 200 Live-Einträge.
- **ntfy-Priority-Mapping nach Severity** — sobald sich das Tiering als
  sinnvoll bestätigt, ntfy-Priority an `severity` koppeln (Lücke: nur
  Anomaly-Sender hardcoded).

**Längerfristig (Monate, Empirik-basiert)**

- **Big-Refactor Zwei-Achsen-Ranking** — nach 30+ Tagen Earliness-Daten.
- **Premium-Daten-Stack** (Wiedervorlage 02.07.2026).
- **Sektor-Rotation / Marktkontext** — noch nicht im Backlog.

### Lackmus-Test

**Phase 3 Validieren ist der entscheidende Test.** Backtest muss
zeigen: Score ≥ 70 hat einen klar besseren Median-R-Wert nach 5 T als
Score < 50. Mit der Zwei-Run-Architektur (PR #124) wird die Backtest-
Historie nur noch mit postclose-Werten befüllt — vorherige premarket-
Einträge bleiben unverändert, müssen in der Auswertung über
`market_regime`/`vix_level`-Filter bereinigt werden.

- **Wenn ja** → Earliness-Score-Aktivierung und Big-Refactor mit
  Rückenwind.
- **Wenn nein** → Score-Komponenten **neu kalibrieren bevor weiter
  gebaut wird**.

Bis der Test laufen kann, ist passives Sammeln der primäre Modus. Mit
dem heutigen Stand ist Phase 2 vollständig (alle sechs Exit-Trigger
live), Push-System nach Conviction-75 streng gefiltert, Drawer-Live-
Polling über Cloudflare-Worker scharf, zwei CI-Lints gegen f-String-
Klassen-Bugs aktiv.

---

## Code-Hygiene-Backlog

Aus der Diskussion vom 09.05.2026. Status zum Ende 13.05.:

- **Punkt 1 — `_record_push`-SSOT** — erledigt via PR #76.
- **Punkt 2 — v1/v2 Render-Pfad in `generate_report.py`:** **offen.**
  Vollständige Migration zu Jinja (Phase X). Voraussetzung für Punkt 3.
- **Punkt 3 — Monolith `generate_report.py` aufsplitten:** **offen.**
  ~14 200 Zeilen in einer Datei (heute weiter gewachsen durch PRs
  #134/#135/#137/#138). Hohe Risiko-Operation.
- **Punkt 4 — HTML/JS-im-f-String-Pattern durch Template-Engine
  ersetzen:** **offen.** Hängt mit Punkt 2 zusammen. Aktuelle Bug-
  Kaskade (#137 + #138) zeigt die strukturelle Schwäche dieses
  Patterns — dafür gibt's jetzt zwei CI-Linter als Abhilfe, aber die
  Ursache bleibt.
- **Punkt 5 — Score-Methodik-Sync-Regel strukturell absichern**
  - **Schritt 1: erledigt via PR #84 (10.05.2026).**
  - **Schritt 2 (offen):** `score()` und `_compute_sub_scores()` aus
    denselben `SUB_*_DISPLAY_PTS_MAX`-Konstanten ableiten.
- **Punkt 6 — `_drivers_breakdown` mit `score()` zusammenziehen**
  - **Schritt A: erledigt via PR #83 (10.05.2026).**
  - **Schritt B (offen):** `score()` und `_compute_sub_scores()` aus
    `DRIVER_CLASSIFICATIONS` ableiten lassen.

---

## Architektur-Anker (kumuliert + heutige Erweiterungen)

### Heute neu (13.05.2026)

- **Plausibilitäts-Override für `workflow_dispatch.inputs.run_phase`**
  (PR #132) — `scripts/resolve_run_phase.py` ist SSOT. Workflow-Step
  `Resolve run phase` schreibt `RUN_PHASE` nach `$GITHUB_ENV`. US-
  Session-Grenzen: `13:30 UTC` (inkl.) bis `20:00 UTC` (exkl.). Cron-
  Trigger ausgenommen, `workflow_dispatch` mit `required: true` ohne
  Default. Override-Warnungen mit `⚠ Override:`-Präfix im Step-Log.
- **Drei Aufrufer-Konsumenten von `run_phase`** — die strukturelle
  Änderung in PR #132 hatte zwei zunächst übersehene Aufrufer:
  - `daily-squeeze-report.yml` (Workflow-Owner, PR #132)
  - Frontend-Recalculate-Dispatch `dispatchWorkflow` (PR #133) —
    JS-Helper `_computeClientRunPhase()` aus `new Date()`-UTC.
  - `redeploy-on-source-change.yml` (PR #136) — Bash-Logik
    `NOW_HHMM=$(date -u +%H%M)`, mappt 1330–1959 → premarket.
  Linter-Idee für künftige `required`-Änderungen: `grep -rn
  "workflow run daily-squeeze-report\|workflows/daily-squeeze-report"
  .github/ generate_report.py scripts/` und alle Aufrufer
  synchron pflegen.
- **Live-Quote-Polling via Cloudflare-Worker** (PR #135) — Worker-
  Endpoint `quote-proxy.easywebb.workers.dev` (manuell deployed, URL
  als Repo-Secret `QUOTE_PROXY_URL`). Worker-Code in
  `cloudflare/quote-proxy/worker.js` (Yahoo v8 chart-Endpoint —
  v7-quote verlangt seit Mai 2026 Crumb-Auth → HTTP 401). Single-
  Ticker pro Request, Edge-Cache 10 s, CORS-Allow-List für
  `https://easywebb911.github.io`. Frontend-Modul in
  `generate_report.py` direkt nach den GH-Konstanten:
  `_quotePollers: Map<ticker, {intervalId, scope}>`, `_quoteFetchOnce`,
  `_quotePatchScope`, `_quoteSetIndicator`, `_startQuotePoll`,
  `_stopQuotePoll`. Lifecycle in `wlExpand` (Open → start, Close →
  stop) und `toggleDetails` (Top-10-Karte, Live-Dot lazy in
  `.score-block` injiziert). `visibilitychange`-Listener pausiert
  alle aktiven Intervalle bei Tab-hidden, resumed bei Tab-visible —
  kein Background-Traffic. Indikator-States: `.quote-live-on` (grün
  pulsierend), `.quote-live-stale` (grau bei Fehler), `.quote-live-
  paused` (gedimmtes Grün bei Tab-hidden). Bei Fetch-Fehler **kein
  Toast** — laut Spec.
- **`_patchWlMomentumLive`** (PR #134) — Quick-Fix für die Lücke
  zwischen Daily-Run und Polling: überschreibt nach `body.innerHTML`-
  Insert in `wlExpand` die Momentum-Box mit `_WL_CARDS[ticker]
  .change`. `change_5d`-Sub-Span im selben `.m-val` wird konserviert.
  Wird durch Live-Polling überholt, sobald der Drawer offen bleibt —
  bei kurzem Hover-Open ist der Patch der einzige frische Wert.
- **Jekyll-`_config.yml` mit `exclude:`-Liste** (PR #139) — interne
  Doku (`CLAUDE.md`, `SESSION_HANDOVER.md`, `docs/`) wird nicht durch
  Liquid geleitet. Code-/Build-Stack (`*.py`, `cloudflare/`, `scripts/`,
  `templates/`, `requirements.txt`) auch ausgeschlossen. `*.json`-
  Daten-Files explizit **nicht** excluded (Frontend-fetch). Pages-
  Landing-Assets (`README.md`, `index.html`, `service_worker.js`)
  bleiben sichtbar.
- **Zwei komplementäre CI-Lints für f-String-Bugs:**
  - `scripts/lint_chat_template.py` (bestand schon) — Backtick-Balance
    im Chat-Template.
  - `scripts/lint_jsformat_escape.py` (PR #138, **neu**) — AST-basiert,
    scannt den `generate_html_v1`-f-String (Z. 5648–11535) gegen alle
    Top-Level-Namen aus `generate_report.py` + `config.py` plus Locals.
    Findet **unescapte** `{name}`-Patterns, deren `name` nicht im Scope
    ist. Workflow-Step `Lint JS-format escape` zwischen `Lint chat
    template` und `Resolve run phase`. Erweiterbar via
    `_F_STRING_TARGETS`-Tuple-Liste (weitere f-String-Funktionen).
- **Grep-Pflichtprüfung** für `${var}`-JS-Template-Literals (besteht
  seit langem in CLAUDE.md) — komplementär zum AST-Linter. Beide
  Pattern fangen unterschiedliche Bug-Klassen:
  - `${name}` ohne `${{name}}` → Dollar-Pattern-grep
  - `{name}` ohne `{{name}}` (JS-Code/-Kommentar/-Destructuring) →
    AST-Linter

### Kumuliert (Auszug — siehe vorige Handover-Updates für
Vollständigkeit)

- **Zwei-Run-Architektur** (PR #124, 12.05.) —
  `app_data.json["run_phase"]` ∈ `{premarket, postclose}`. 10:00-UTC-
  Cron premarket (Vorschau, Anomaly-Pushes aktiv), 21:00-UTC-Cron
  postclose (EOD-Wahrheit, Backtest-Append). PR #132 (heute) ergänzt
  den Plausibilitäts-Override für manuelle Trigger.
- **`_record_push`-SSOT** (PR #76) — Push-History persistiert
  einheitlich für alle vier ntfy-Sender (`anomaly`, `exit_p1`,
  `exit_p2`, `earnings_immediate`). Schema-Erweiterung
  `conviction_score` via PR #123.
- **`Conviction-Score`** (PR #89 + #95) — vierte Bewertungs-Achse.
  Komponenten Setup 33 / Earliness 28 / Anomaly 28 / Regime 11.
  Threshold-Crossing löst `conviction_high`-Push aus.
- **Conviction-75-Gating** (PR #123, 12.05.) — alle Anomaly-Trigger
  inkl. `monster_backup` werden bei Conviction < 75 unterdrückt.
  `conviction_high` selbst ist ungated.
- **Phase 2 Exit-Framework vollständig — alle sechs Trigger live**
  (Abschluss PR #121, 12.05.): `score_decay` (30 %), `profit_lock`
  (25 %), `overheated` (20 %), `setup_erosion` (15 %), `catalyst`
  (5 %), `trend_break` (5 %).
- **Chat-Synthese watchlist_cards-aware** (PR #122) — Position-Felder
  fallen über `watchlist_cards` zurück, wenn Ticker nicht in Top-10.
- **Earnings-Per-Event-Dedup** (PR #123) — Cooldown-Key
  `earnings_immediate_{ticker}_{DD.MM.YYYY}`,
  `EARNINGS_IMMEDIATE_COOLDOWN_HOURS=24`.
- **Token-Soft-Reset bei 401/403** (PR #125) — Counter 1+2 nur
  Session-Reset, 3 Hard-Reset (`TOKEN_AUTH_FAIL_HARD_THRESHOLD=3`).
  Plus iCloud-Schlüsselbund-Integration via `<form>`-Wrapper +
  hidden username-input, plus Keep-Alive-Touch in `getToken()`.
- **Watchlist-Drawer kein `dataset.loaded`-Cache mehr** (PR #126).
  Drawer rendert bei jedem Open neu via `buildWlDetails`.
- **`_WL_CARDS`-Re-Assign nach ki_agent-Tick** (PR #126) — frische
  Drawer-Daten nach KI-Agent-Run.
- **`_parse_de_date`-SSOT für DD.MM.YYYY-Cutoff-Vergleiche** (PR #119).
- **`score_inflation_log.jsonl`** (PR #120) — append-only JSONL für
  Intra-Day-Score-Inflation-Diagnose, 30-Tage-Cutoff.

---

## Wichtige Lernerfahrungen (13.05.2026)

- **Folge-Bug-Kaskade bei strukturellen `required`-Änderungen.** PR
  #132 hatte drei Aufrufer übersehen (Frontend-Recalculate-Dispatch,
  Redeploy-Workflow, Manual-iPhone-Trigger als Initial-Auslöser).
  Lehre: bei jeder `required`-Änderung an einem Workflow-Input
  **erst grep über alle Aufrufer-Stellen** (`grep -rn "workflow run
  daily-squeeze-report\|workflows/daily-squeeze-report" .github/
  generate_report.py scripts/`), dann erst Schema ändern.
- **Container-Cache veraltet schnell.** Claude Code's Sandbox hatte
  heute zweimal eine veraltete `origin/main`-Referenz (48 h und 2 h
  alt). `git fetch origin main` ist der erste Schritt jeder
  Session-Aufgabe — der GitHub-Stand auf github.com ist die einzige
  Wahrheit.
- **Yahoo v7 API jetzt mit Crumb-Auth.** `/v7/finance/quote` antwortet
  seit Mai 2026 HTTP 401 ohne `crumb`/`cookie`. v8-Chart-Endpoint
  (`/v8/finance/chart/{ticker}`) ist öffentlich erreichbar, aber
  single-ticker pro Request. yfinance-Library nutzt intern wohl
  einen Crumb-Mechanismus, Browser-Direktzugriff hat den nicht.
- **Live-Polling-Architektur via Cloudflare-Worker** ist der saubere
  Browser→Yahoo-Pfad. Free-Tier 100 k Req/Tag reicht locker für 4
  parallele Drawer á 4 Polls/min á 24 h ≈ 23 k Req. Edge-Cache 10 s
  reduziert Yahoo-Backend-Load drastisch. **Polling-Lifecycle muss
  `visibilitychange` respektieren** — sonst läuft Background-Polling
  bei jeder gesperrten iPhone-Session.
- **f-String-Bug-Klasse strukturell verhindern.** Zwei unabhängige
  Linter (`${var}`-grep + `{var}`-AST-Scan) als CI-Gates fangen die
  zwei distinkten Pattern-Klassen. Beide laufen vor dem Generate-
  Step — kaputte Versionen werden nicht deployed.
- **Jekyll vs. interne Doku.** GitHub-Pages-Build parst standardmäßig
  alle `*.md`-Files als Liquid-Templates. Interne Doku mit `{{...}}`-
  Patterns (z.B. Code-Beispiele in CLAUDE.md) muss explizit in
  `_config.yml exclude` — der pragmatische Pfad ist sauberer als jede
  Markdown-Stelle in `{% raw %}` einzuwickeln.
- **Setup-Schritte für externe Services in Service-Folder-README.**
  Cloudflare-Worker-Setup (`wrangler login` + `wrangler deploy` +
  Repo-Secret `QUOTE_PROXY_URL`) ist eine einmalige User-Action —
  gehört in `cloudflare/quote-proxy/README.md`, nicht in CLAUDE.md
  (= Entwicklungsregeln) und nicht in den PR-Body (= ephemer).
  CLAUDE.md verlinkt darauf.
- **PR-Body als Setup-Doku zu unzuverlässig.** Easy fand den Bug in
  PR #135 (v7 → v8) erst beim manuellen Deploy, nicht im Code-Review.
  Lehre: nicht-triviale externe Services brauchen einen Smoke-Test-
  Schritt im README („`curl 'https://quote-proxy.…/?ticker=AAPL'`
  liefert valid JSON mit `price`?"), bevor Repo-Secret gesetzt wird.
- **Bug-Reproduktions-Test als Regression-Guard.** Mock-Test in
  PR #137 enthält explizit den Negativ-Test (f-String ohne Variable
  → `KeyError`). Dokumentiert das ursprüngliche Bug-Verhalten, dass
  ein zukünftiger Refactor die Fix-Stelle nicht wieder entfernt
  ohne den Test zu brechen.
