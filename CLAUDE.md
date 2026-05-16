# Entwicklungsregeln — Aktien-Update

## Git-Workflow (PR-only)

**ALLE Änderungen** — Code, Doku **und** Config — gehen über Pull Request.

- Branch-Name-Pattern: `claude/<kurze-beschreibung>-<random>`
- Direkt-auf-`main` ist **nicht möglich** (Sandbox-Restriktion seit
  09.05.2026: alle `main`-Pushes — auch reine Doku — werden mit
  HTTP 403 abgewiesen). Branch-Pushes funktionieren weiterhin.

### Auto-Merge-Regel (ab 15.05.2026)

Claude Code mergt PRs **selbst** nach grünem squeeze-guardian + grünen
Tests, Branch danach löschen.

**Ausnahmen — manueller Easy-Merge mit Code-Review-Pflicht:**

- Neue Workflow-Dateien (`.github/workflows/*.yml` neu angelegt)
- Neue JSON-Schemas (neue Top-Level-Keys in `app_data.json`,
  `positions[ticker]`, `closed_trades[i]`, `backtest_history.json`,
  neue JSONL-Schemas)
- Neue API-Integrationen (neue externe Datenquellen)
- Score-/Conviction-/Filter-Logik-Änderungen (`score()`,
  `score_bonus()`, `apply_*`, `compute_*_score`, `_compute_sub_scores`,
  Filter-Schwellen, Conviction-Komponenten-Gewichte)

**Auto-Merge erlaubt für:**

- Doku-PRs (CLAUDE.md, SESSION_HANDOVER, Spec-Updates)
- Frontend-Tweaks (Display-Labels, UI-Refresh, CSS-Anpassungen)
- Workflow-Tweaks innerhalb existierender YAMLs (Cron-Offsets,
  `git add`-Listen, Permission-Fixes)
- Helper-Refactor (Modul-Umzüge, gemeinsame Abstraktionen)
- State-Logging (`log.info`/`log.warning`, Diagnose-Verbesserungen)
- Mock-Test-Erweiterungen
- Backward-compat-Aliase

Im Zweifel: lieber Easy-Merge anfragen als Auto-Merge.

## generate_report.py — Template-Sicherheitsregel

**Die gesamte HTML/JS-Sektion in `generate_report.py` ist ein Python-f-String.**
Das bedeutet: Python interpretiert `{ausdruck}` als Interpolation — auch innerhalb
von JavaScript-Code und JavaScript-Template-Literals.

### Pflichtprüfung nach jeder Änderung am Template

Nach jedem neu hinzugefügten JavaScript-Block **sofort prüfen**:

```bash
grep -n '\${[a-zA-Z_][a-zA-Z0-9_.]*}' generate_report.py
```

Gibt dieses Kommando **irgendeine Zeile** aus → ist ein Bug vorhanden.

### Regel: Alle `${}` in JS-Template-Literals müssen `${{}}` sein

| Kontext | Falsch ❌ | Richtig ✓ |
|---|---|---|
| JS-Template-Literal im f-String | `` `Score ${score}/100` `` | `` `Score ${{score}}/100` `` |
| JS-Template-Literal im f-String | `` `Konfidenz ${confidence}%` `` | `` `Konfidenz ${{confidence}}%` `` |
| Reguläre JS-Objekte / Dicts | `{key: value}` | `{{key: value}}` |
| Alle anderen `{...}` in JS | `if (x > 0) { ... }` | `if (x > 0) {{ ... }}` |

### Warum?

Python's f-String-Parser scannt den gesamten String nach `{...}`.
`${confidence}` wird als `$` + `{confidence}` geparst — Python versucht,
die Python-Variable `confidence` aufzulösen → `NameError: name 'confidence' is not defined`.

### Eingebettetes Prüfskript

```python
# Schnellcheck — in jedem Terminal ausführbar:
python -c "
import re, sys
src = open('generate_report.py').read()
hits = [(i+1, l.strip()) for i, l in enumerate(src.splitlines())
        if re.search(r'\\\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}', l)]
if hits:
    print('FEHLER: Unescapte JS-Template-Variablen gefunden:')
    for ln, txt in hits:
        print(f'  Zeile {ln}: {txt}')
    sys.exit(1)
else:
    print('OK: Keine unescapten JS-Template-Variablen.')
"
```

---

## Lint-Regeln (CI-Gates)

Lint-Skripte unter `scripts/` laufen **vor** den Daily-Run im Workflow.
Ein Lint-Fail bricht den Workflow ab — die kaputte Version wird nicht
deployt.

### `scripts/lint_chat_template.py` — Backticks im Chat-Prompt

Prüft, dass `_buildSystem()` in `templates/chat_script.jinja` **genau
zwei Backticks** enthält (öffnender + schließender Delimiter des JS-
Template-Literals). Jede zusätzliche Backtick — typisch durch
versehentliche Markdown-Code-Notation `` ``code`` `` — bricht das
Literal vorzeitig, wirft einen `TypeError` zur Laufzeit und der
`catch`-Handler in `chatSend` rendert die Error-Message (mit dem
kompletten Prompt-Text) als rotes Chat-Bubble.

**Bug-Verweis:** `1341af9` — Hot-Fix für genau dieses Symptom.

**Workflow-Integration:** Step `Lint chat template` in
`.github/workflows/daily-squeeze-report.yml` läuft direkt vor
`Build positions.json from secret`. Ein-Befehl-Aufruf:

```bash
python scripts/lint_chat_template.py
```

Exit-Code 0 = OK, 1 = Fail. Bei Fail werden alle Backtick-Positionen
im Body relativ zum Body-Start geloggt (Zeilenkontext ±30 Zeichen),
damit man den Übeltäter direkt findet.

### `scripts/lint_jsformat_escape.py` — Unescapte `{...}` in f-Strings

Fängt die zweite Klasse von f-String-Bugs, die der `${var}`-Check oben
**nicht** abdeckt: einzelne `{name}` im JS-Code/-Kommentar/-Destructuring,
die Python als Variable-Lookup interpretiert. Beispiele aus der Praxis:

- PR #135 zweite Welle: `// ticker → {intervalId, scope, indicator}` im
  JS-Kommentar → `NameError: 'intervalId' is not defined` (Fix: PR #138).
- Generisch: `const x = {key: value}` oder `function({a, b}) {...}` —
  alles Python-Format-Trigger ohne Escape.

**Funktionsweise (AST-basiert):**

1. Top-Level-Namen aus `generate_report.py` + `config.py` sammeln
   (Imports, Konstanten, Funktionen, Klassen).
2. Lokale Namen aus dem Funktions-Body (Assigns, For-Targets,
   Comprehension-Bindings, Argumente).
3. f-String-Bereich (`return f"""` bis `</html>"""`) scannen: für jedes
   nicht-mit `{{` escapeden `{name}` prüfen, ob `name` im Scope ist.
4. Wenn nicht: Bug — Var-Name, Pattern und Code-Kontext werden geloggt.

**Welche Funktionen werden geprüft?** Aktuell nur `generate_html_v1`
(das ist der einzige große f-String mit JS-Block). Weitere Targets in
`_F_STRING_TARGETS` ergänzen (Tuple `(func_name, start_pat, end_pat)`).

**Bug-Verweis:** `0b0a229` Daily-Run-Crash am 13.05.2026 Abend (PR #135
introducierte das Pattern, PR #137 hat nur die legitime Variable
gefixt, PR #138 fängt die JS-Kommentar-Klasse).

**Workflow-Integration:** Step `Lint JS-format escape` in
`.github/workflows/daily-squeeze-report.yml` läuft direkt nach
`Lint chat template`. Ein-Befehl-Aufruf:

```bash
python scripts/lint_jsformat_escape.py
```

Exit-Code 0 = OK, 1 = Fail. Bei Fail werden Funktion, Zeilennummer,
Variable und Pattern geloggt.

**Verhältnis zum `${var}`-Check oben:**

| Pattern | Beispiel | Linter |
|---|---|---|
| `${var}` in JS-Template-Literal | `` `Hi ${{name}}` `` | bestehende grep-Pflichtprüfung |
| `{var}` in JS-Code/-Kommentar | `// → {intervalId, scope}` | `lint_jsformat_escape.py` (neu) |

Beide Linter sind komplementär — das grep-Pattern fängt Dollar-Pattern,
der AST-Linter fängt blanke Klammern.

### `scripts/lint_score_confidence_isolation.py` — Konfidenz darf nicht in Score-Berechnung

Stellt sicher, dass die rein anzeigenden Score-Konfidenz-Stufen
(`_SCORE_CONFIDENCE` / `score_confidence` / `compute_score_confidence`)
**niemals** in Score- oder Conviction-Berechnungs-Funktionen gelesen
werden. Würde das passieren, würde sich das Tool selbst belohnen
(„hohe Konfidenz → höhere Conviction → höhere Konfidenz") und die
externe Methodik-Bewertung wäre wertlos.

**Allow-Liste** kritischer Berechnungs-Funktionen in
`_FORBIDDEN_FUNCS` (Stand: 15 Funktionen — `compute_conviction_score`,
`apply_conviction_scores`, `compute_earliness_pts`,
`_earliness_pts_v1/v2`, `score`, `score_bonus`, `apply_monster_score`,
`apply_agent_boost`, `apply_late_runner_penalty`,
`apply_score_smoothing`, `_compute_sub_scores`, `_drivers_breakdown`,
`compute_exit_score`, `process_exit_signals`).

**Workflow-Integration:** Step `Lint score-confidence isolation` in
`.github/workflows/daily-squeeze-report.yml`, direkt nach
`Lint JS-format escape`. Exit-Code 0 = OK, 1 = Fail. Bei Fail wird
Funktion + Zeile + Code-Match geloggt.

Bei neuen Score-Berechnungs-Pfaden die Allow-Liste in
`_FORBIDDEN_FUNCS` ergänzen.

---

## Allgemeine Architektur

- `generate_report.py` erzeugt `index.html` — **niemals `index.html` direkt bearbeiten**
- `ki_agent.py` schreibt `agent_signals.json` + `agent_state.json`
- Alle Schwellen und Konstanten stehen im Konstantenblock ganz oben der jeweiligen Datei
- Workflow-Dateien: `.github/workflows/daily-squeeze-report.yml` und `ki_agent.yml`

---

## Zwei-Run-Architektur (seit 12.05.2026)

Der Daily-Run läuft **zweimal pro Werktag** mit unterschiedlicher
Datenqualität:

| Cron | Phase | Daten | Push-Pipeline | Backtest-History |
|---|---|---|---|---|
| `17 10 * * 1-5` (10:17 UTC) | `premarket` | Vorschau, RVOL strukturell unter-skaliert (US-Open ~3,2 h voraus) | Anomaly-Pushes **aktiv** (Aktions-Fenster für die KI-Agent-Ticks) | **kein** Backtest-Eintrag |
| `17 21 * * 1-5` (21:17 UTC) | `postclose` | EOD-konsolidiert = „Wahrheit" | Anomaly-Pushes **aus** (kein abendliches Rauschen) | Backtest-Eintrag wird angelegt |
| `workflow_dispatch` (manuell) | per User-Input, **required, kein Default** — Plausibilitäts-Override aktiv (siehe unten) | wie oben | wie oben | wie oben |

### Plausibilitäts-Override für workflow_dispatch (seit 13.05.2026)

**Motivation:** Am 13.05.2026 wurden drei manuelle Daily-Run-Trigger
während laufender US-Session abgesetzt — der damalige Default-Wert
`postclose` (im YAML) sorgte für **22 Intraday-Mid-Day-Backtest-Einträge**
(RVOL teils < 0.2, zwei VIX-Snapshots im selben Run). Cleanup via
PR #131. Der Fix unten verhindert die Wiederholung.

Die RUN_PHASE-Resolution lebt jetzt in
`scripts/resolve_run_phase.py` und wird vom Workflow-Step
`Resolve run phase` aufgerufen (schreibt `RUN_PHASE` nach
`$GITHUB_ENV`). Logik:

| Trigger | Input | Aktuelle UTC-Zeit | Resultat | Override-Reason |
|---|---|---|---|---|
| `schedule` `17 10 * * 1-5` | — | — | `premarket` | — (fester Cron-Mapping) |
| `schedule` `17 21 * * 1-5` | — | — | `postclose` | — (fester Cron-Mapping) |
| `workflow_dispatch` | `postclose` | 13:30 ≤ UTC < 20:00 (US-Session) | **`premarket`** | `us_session_override` |
| `workflow_dispatch` | `premarket` | UTC ≥ 20:00 (Post-Close) | **`postclose`** | `post_close_override` |
| `workflow_dispatch` | `premarket` | 13:30 ≤ UTC < 20:00 | `premarket` | — (plausibel) |
| `workflow_dispatch` | `postclose` | UTC ≥ 20:00 | `postclose` | — (plausibel) |
| `workflow_dispatch` | `postclose` / `premarket` | UTC < 13:30 (pre-Open) | unverändert | — (User-Wahl gilt) |
| `workflow_dispatch` | empty / garbage | — | `premarket` | `no_input_fallback` |

US-Session-Grenzen: `US_SESSION_START = 13:30 UTC` (inkl.) =
US-Market-Open, `US_SESSION_END = 20:00 UTC` (exkl.) = US-Market-Close.
Zeitfenster `[13:30, 20:00)` als „US-Session". Die 30-Minuten-Schonfrist
vor Open (13:00–13:30 UTC) ist intentional kein Override-Pfad — wer in
diesem Slot manuell triggert, will typischerweise einen Pre-Open-
Snapshot (= premarket) und kann das frei wählen.

**Cron-Trigger sind vom Override ausgenommen** — der Schedule-Wert
ist YAML-festgelegt und konsistent zur jeweiligen Cron-Zeit, kein
Korrektur-Bedarf.

**Override-Warnungen** landen mit Präfix `⚠ Override:` im
`Resolve run phase`-Step-Log und sind im GitHub-Actions-UI direkt
sichtbar. Der nachfolgende `Generate squeeze report`-Step liest
`${{ env.RUN_PHASE }}` (= aufgelöster Wert), nicht mehr den rohen
User-Input.

**workflow_dispatch-Input ist seit 13.05.2026 `required: true`** und
hat keinen Default mehr — User muss bewusst wählen (zwingt zur
Entscheidung statt unbemerktem Falsch-Default).

Tests: `scripts/mock_test_run_phase_resolution.py` (12 Cases,
inkl. Edge-Boundary 13:29/13:30/20:00 UTC).

### Felder & Persistenz

- **`app_data.json["run_phase"]`** (`premarket` / `postclose`) — vom
  Daily-Run beim Schreiben gesetzt, von `ki_agent.py` beim Tick gelesen
  und via `**existing`-Spread preserviert.
- **`score_inflation_log.jsonl`** — pro Zeile zusätzlich
  `run_phase`-Feld (neben dem bestehenden `trading_session_phase`-Feld,
  das den ET-Wall-Clock-Slot abbildet). `run_phase` ist die Workflow-
  Intention, `trading_session_phase` der tatsächliche ET-Slot zur
  Run-Zeit — beide Felder messen unterschiedliche Dinge und werden
  beide persistiert.
- **`_resolve_run_phase()`** in `generate_report.py` liest `RUN_PHASE`-
  ENV (Workflow setzt das), validiert auf `premarket`/`postclose` und
  fällt bei Garbage auf `premarket` zurück (sicher: kein Backtest-
  Befüllen, kein Schaden).

### Push-Differenzierung (ki_agent.py)

```
run_phase=premarket → anomaly-pushes aktiv + exit-p2 aktiv
run_phase=postclose →                     nur exit-p2 aktiv
```

Eingehängt direkt vor dem `for anom in detect_anomalies(...)`-Loop
(`if not earnings_immediate and not vix_pause and anomaly_pushes_enabled`).
`process_exit_signals()` läuft NACH dem Loop und ist von dieser Gate
NICHT betroffen — Exit-Trigger feuern in beiden Phasen.

### Frontend (Banner)

`_renderRunPhasePill(phase)` ergänzt die Header-Timestamp-Zeile um eine
farbcodierte Pill:

- `premarket` → gelbe „· Pre-Open-Vorschau"-Pill (Hinweis: Daten noch
  nicht final)
- `postclose` → grüne „· Post-Close"-Pill (EOD-Wahrheit)
- fehlendes Feld (alte app_data ohne `run_phase`) → kein Pill (statt
  verwirrendem „Unbekannt"-Label)

### Backtest-Disziplin

`_append_backtest_entries()` wird in `main()` **nur** im
`postclose`-Mode aufgerufen. Bestehende premarket-Einträge in
`backtest_history.json` (vor Einführung der Zwei-Run-Architektur)
bleiben unverändert — kein retroaktiver Cleanup, keine Migration. Die
Backtest-Auswertung kann sie später per `market_regime`/`vix_level`-
Filter bereinigen.

### Failure-Modes

- 21:00-Run fällt aus → app_data behält letzten Stand (run_phase
  bleibt was sie war). Nächster 10:00-Run flippt auf premarket, App
  zeigt „Pre-Open-Vorschau"-Banner — Easy sieht sofort, dass Daten
  älter sind.
- 10:00-Run fällt aus → 21:00-Run liefert volle Wahrheit, kein
  Schaden.
- Beide Runs nutzen denselben Code-Pfad — Unterschied nur durch
  `RUN_PHASE`-ENV-Flag, kein Code-Duplikat.

---

## Conviction-Score (Schritt A — Daten, ohne UI)

Vierte Bewertungs-Achse neben Setup-Score, Monster-Score und KI-Score.
Beantwortet die Aktions-Frage („jetzt einsteigen?") via Aggregation aus
Setup-Qualität, Earliness, aktiven Anomalie-Triggern und Marktphasen-
Konformität (VIX-Regime). **Schritt A liefert nur die Daten** — Anzeige
im Frontend kommt in Schritt B nach Plausibilitäts-Verifikation.

### Komponenten-Gewichte (Summe ≤ 100)

| Komponente | Cap | Berechnung |
|---|---:|---|
| `setup`     | 33 | `setup_score / 100 × 33` (gerundet) |
| `earliness` | 28 | `earliness_pts / EARLINESS_PTS_MAX × 28` (gerundet) |
| `anomaly`   | 28 | 0 / 14 / 28 für 0 / 1 / ≥2 aktive Anomalie-Trigger |
| `regime`    | 11 | VIX < `ANOMALY_VIX_WARN_THRESHOLD` → 11 · VIX < `ANOMALY_VIX_PAUSE_THRESHOLD` → 6 · sonst (oder None) → 0 |

### Action-Text-Mapping

| Score | Level | Text |
|---:|---|---|
| ≥ 75 | high   | „Conviction hoch — Setup, Earliness und Timing konvergieren. Erwartungswert positiv." |
| 50–74 | medium | „Substrat stark, Timing-Signal fehlt. Auf Volume-Spike oder Anomalie-Trigger warten." |
| 30–49 | low    | „Setup gut, aber Phase oder Marktkontext ungünstig. Genau hinschauen." |
| < 30 | low    | „Aktuell kein klares Aktions-Signal." |

Bei fehlenden Anomalie-Daten (`anomalies_today=None`) wird der Text um
`(Anomalie-Daten nicht verfügbar)` ergänzt — kein Crash, nur Hinweis
für Diagnose.

### Pipeline-Aufruf

`apply_conviction_scores(stocks, anomalies_today, vix)` läuft in
`main()` zwischen Step 4 (HTML-Render) und Step 4b
(`_write_app_data_json`). Quellen:

- `anomalies_today` aus `_build_chat_synthesis_ctx(top10, score_history)`
  — gleiche Liste wie der Chat-Kontext, deterministisch.
- `vix` aus `_read_existing_app_data().get("vix_current")` — vom
  letzten ki_agent-Tick gesetzt; bei fehlendem Wert → regime=0.

Pure Funktion `compute_conviction_score(stock, anomalies_today, vix)`
ist Single-Source-of-Truth für die Score-Logik; `apply_*_scores`
schreibt nur ins Stock-Dict.

### Persistenz

`app_data.json["conviction_scores"]: {ticker: {score, components,
action_text, level}}` — separater Top-Level-Key analog zu
`monster_scores`/`setup_scores`. Schritt B konsumiert das im Frontend.

### Coverage-Erweiterung (Phase 1, 16.05.2026)

`apply_conviction_scores` läuft nicht mehr nur über Top-10, sondern
zusätzlich über den **Watchlist-Outsider-Pool**:

```
pool_outsiders = {c for c in enriched
                  if c.get("manual_personal") and c["ticker"] not in top10_tickers}
```

→ heutige Pool-Mitglieder: persönliche Watchlist-Tickers, die NICHT in
der heutigen Top-10 stehen (z. B. CRMD/AMC/IONQ/RR/AI bei Easy am
16.05.2026).

**Vorbedingung Earliness:** `compute_earliness_pts` muss auch über
diesen Pool laufen (sonst ist `earliness_pts=None` → Conviction-Komp.
auf 0 gedeckelt → künstlich niedrige Conviction für Watchlist).
Aufruf direkt nach dem Top-10-`compute_earliness_pts`-Block in
`main()`. Single-Source-of-Truth `_wl_outsiders_for_pool`-Variable
sammelt beide Pipelines.

**Anomalie-Komponente bleibt 0 für Watchlist-Outsider** (KI-Agent-
Anomalien existieren erst nach Phase 2, KI-Agent-Coverage-Erweiterung).
Conviction-Berechnung ist null-tolerant: `anomalies_today=None` →
`anomaly_pts=0` + Hinweis im Action-Text.

**Zweck**: Vorbereitung für **Phase 2** (KI-Agent-Coverage). Conviction-
Gating in `ki_agent.detect_anomalies` (Schwelle `ANOMALY_CONVICTION_MIN_THRESHOLD = 75`)
braucht für jeden zu pushenden Ticker einen `conviction_scores[t]`-
Eintrag. Ohne Coverage-Erweiterung würde Phase 2 ungefilterte Anomaly-
Pushes für Watchlist-Outsider produzieren (Push-Spam-Risiko).

**Persistenz**: `_conviction_scores`-Dict-Sammler in `_write_app_data_json`
iteriert über Top-10 UND Watchlist-Outsider — neue Tickers erscheinen
als zusätzliche Keys im additiven Schema.

### KI-Agent-Coverage (Phase 2, 16.05.2026)

`ki_agent.py:parse_monitored_tickers()` ersetzt den
`parse_top_tickers()`-Aufruf in `main()`. Pool:

```
monitored = parse_top_tickers()              # aus index.html
           ∪ watchlist_personal.json         # persönliche Watchlist
           ∪ positions.json.keys()           # aktive Positionen
```

Heutige Pool-Größe: 10 (Top-10) + 5 (Watchlist) + 0 neue (Positions
sind Subset Watchlist) = ~15 Tickers. Worker-Pool von `max_workers=8`
auf `max_workers=10` erhöht.

**Performance-Impact:** +15-20 s pro KI-Agent-Tick (von ~40-50 s auf
~55-70 s). Stunden-Cron-Slot xx:17 hat reichlich Puffer.

**Push-Spam-Schutz** bleibt 3-fach abgesichert:
1. **Conviction-Gating ≥ 75** (Phase 1 PR #176 hat Coverage gefüllt;
   detect_anomalies liest `app_data["conviction_scores"][ticker]`).
2. **Defensive None-Gating** (Phase 2): wenn `_conv_today is None`
   UND `ticker not in _top10_set` → suppress. Vermeidet Push-Spam
   wenn Phase-1-Coverage für einen Ticker fehlschlägt (Daten-Lücke).
   Top-10 ohne Conviction wird NICHT suppress'd — das wäre ein
   Coverage-Defekt, der vom S2-Health-Check gefangen werden sollte.
3. **6h-Cooldown + Silence-Filter + VIX-Gating** unverändert.

**EDGAR-Filings**: `fetch_edgar_filings(edgar_monitored)` läuft jetzt
auf dem erweiterten Pool — alle Watchlist-Outsider werden auf 13D/G-
Filings gematcht. Variable wurde `edgar_top10` → `edgar_monitored`
umbenannt (Naming-Klarheit, kein Verhaltens-Drift).

**agent_signals.json-Schema**: rein additiv. Watchlist-Outsider
erscheinen als zusätzliche Keys; kein Schema-Versions-Bump.

**Wiedervorlage 30.05.2026**: nach 14 Tagen Live-Daten prüfen, ob
ein zusätzlicher `WATCHLIST_OUTSIDER_CONVICTION_MIN` (z. B. 85)
nötig ist. Hypothese: Conviction-Gating ≥ 75 reicht — die meisten
Watchlist-Outsider haben Substrat unter 75, Pushes feuern nur bei
echten Bewegungen. Bei > 5 zusätzlichen Pushes/Tag im Durchschnitt
→ härtere Schwelle empirisch ableiten.

### Pflege

Bei Änderung der Komponenten-Gewichte (Cap-Werte 33/28/28/11),
Action-Text-Schwellen (75/50/30) oder Anomaly-Bucket-Werte (0/14/28):
diese Sektion + `compute_conviction_score`-Doku synchron halten. Bei
Anpassung der Schwellen-Konstanten in `config.py`
(`ANOMALY_VIX_WARN_THRESHOLD` / `ANOMALY_VIX_PAUSE_THRESHOLD`,
`EARLINESS_PTS_MAX`) wirkt das automatisch — kein zusätzlicher Sync
für die Conviction-Berechnung nötig.

---

## Float Turnover (Timing-Sub-Signal)

`Float Turnover = today_volume / float_shares` ist ein **komplementäres**
Volumen-Signal zu RVOL: misst absolute Marktdurchdringung pro Tag, nicht
relative Abweichung vom 20-Tage-Schnitt.

| Schwelle (Vol/Float) | Punkte |
|---|---:|
| ≥ `FLOAT_TURNOVER_LOW`  (0.5) | +`FLOAT_TURNOVER_PTS_LOW`  (3) |
| ≥ `FLOAT_TURNOVER_MID`  (1.0) | +`FLOAT_TURNOVER_PTS_MID`  (6) |
| ≥ `FLOAT_TURNOVER_HIGH` (2.0) | +`FLOAT_TURNOVER_PTS_HIGH` (10) |

Punkte zählen on-top zum Gesamt-Score (`score()` Fall 1 + Fall 2). Im Sub-
Score-Block ist `SUB_TIMING_MAX` von 25 auf **30** erweitert; RV+Mom-
Normierung bleibt unverändert (Faktor 25/37), Turnover wird unscaled
addiert. Bei fehlendem Float oder Volumen → 0 Punkte (graceful Fallback,
keine Exception).

Helper: `_float_turnover_pts(stock) → (ratio, pts)` ist single source of
truth — sowohl `score()` als auch `_compute_sub_scores()` und die Detail-
Zeile `_float_turnover_row_html()` lesen daraus.

---

## News-Sentiment-Decay

News-Headlines im Katalysator-Sub-Score werden nach Alter gewichtet —
frische Headlines scoren stärker als alte. Quelle ist das `ts`-Feld
(Epoch), das `_rss_news()` aus dem RSS-`pubDate` parsed.

| Tages-Alter | Gewicht (`NEWS_DECAY_WEIGHTS`) |
|---:|---:|
| 0 (heute)       | 1.0 |
| 1 (gestern)     | 0.7 |
| 2 (vorgestern)  | 0.4 |
| 3               | 0.2 |
| ≥ 4             | 0.0 (effektiv ignoriert) |

Edge-Cases:
- Fehlendes / nicht parsebares `ts` → `NEWS_DECAY_FALLBACK` (0.5).
  Lieber halbe Wirkung als gar keine — sonst würden RSS-Items ohne
  pubDate (kommt vor) den Score komplett verfehlen.
- Negative Alter (Clock-Drift, Items aus der „Zukunft") → 1.0.

Anwendung in `_compute_sub_scores()`: pro Match wird `5 × weight` zum
`news_pts` addiert (Cap 10 wie zuvor). Helper `_news_age_weight(item,
now_ts)` ist single source of truth — falls UOA/Insider später ähnliche
Decay-Logik bekommen, dort wiederverwendbar.

### News-Coverage-Pool (seit 15.05.2026)

`get_combined_news` läuft seit Diagnose 15.05.2026 nicht mehr nur über
die Top-10, sondern über:

```
news_pool = {s["ticker"] for s in top10}
         ∪ {c["ticker"] for c in enriched if c.get("manual_personal")}
```

Hintergrund: Position-Halter brauchen News-Awareness auch für Tickers,
die nicht in der heutigen Top-10 stehen. Symptom war ein leerer
„Aktuelle Meldungen"-Drawer auf der CRMD-Watchlist-Karte trotz frischer
Earnings — CRMD war an dem Tag nicht in den Top-10 und `get_combined_news`
ignorierte den Ticker.

Set-Dedup verhindert Doppel-Fetch wenn ein Ticker in beiden Listen
steckt. `max_workers=16` deckt den erweiterten Pool ab. News werden via
`_news_by_ticker`-Dict an alle Stock-Dicts in `enriched` attached —
Top-10-Dicts sind Referenz-equal zu ihren enriched-Pendants, Watchlist-
Outsider bekommen die news via `enriched → _wl_card_payload →
watchlist_cards[ticker].news`.

Laufzeit-Impact: bei 3 typischen Watchlist-Outsidern +1–2 s pro
Daily-Run (jeder Ticker macht 2 sequenzielle HTTP-Calls in einem
Worker-Thread).

---

## Gap & Hold (Timing-Sub-Signal)

Misst Eröffnungsstärke + Tagesverlauf auf EOD-Basis:

```
gap_pct        = (today_open  − yesterday_close) / yesterday_close × 100
hold_threshold = today_open + GAP_HOLD_FACTOR × (today_open − yesterday_close)
```

| Bedingung | State | Pts (`config.py`) |
|---|---|---:|
| `gap_pct < GAP_THRESHOLD_PCT` (3 %) | `no_gap` | 0 |
| close > `hold_threshold` | `strong_hold` | +`GAP_PTS_STRONG_HOLD` (5) |
| close < yesterday_close | `fail` (Bull-Trap) | `GAP_PTS_FAIL` (−3) |
| dazwischen | `weak_hold` | +`GAP_PTS_WEAK_HOLD` (2) |
| Daten fehlen (Open / prev_close / price) | `unknown` | 0 |

Helper: `_gap_hold_pts(stock) → (gap_pct, state, pts)`. Single source of
truth für Score, Sub-Score und Detail-Zeile (`_gap_hold_row_html()`).

`cur_open` und `prev_close` werden in `_hist_stats()` (Batch) und
`get_yfinance_data()` (Singleton-Fallback) extrahiert und in der
Enrichment-Phase auf das Stock-Dict gelegt.

---

## RS vs. SPY (ersetzt RS-vs-Sektor)

Squeezes sind oft idiosynkratisch — die Sektor-ETF-Korrelation ist gering;
der breite Markt-Benchmark trennt Outperformer schärfer. Ab 30.04.2026
fließt nur noch `rel_strength_20d` (= stock_perf_20d − ^GSPC_perf_20d) in
den Timing-Sub-Score.

| Wert | Punkte (linear, symmetrisch) |
|---|---:|
| `rs_pct ≥ RS_SPY_THRESHOLD_PCT` (5 %) | +`RS_SPY_PTS_MAX` (3) |
| `0..+5 %` | linear 0..+3 |
| `−5..0 %` | linear −3..0 |
| `≤ −5 %` | −3 |
| `None` | 0 |

Helper: `_rs_spy_pts(stock) → (rs_pct, pts)`. Die alten `RS_SECTOR_*`-
Konstanten in `config.py` sind als deprecated markiert, ebenso die
Felder `rel_strength_sector` und `sector_etf` im Stock-Dict — beide
werden noch befüllt, aber nicht mehr bewertet. Der Detail-Zeilen-Helper
`_sector_rs_row()` ist nicht mehr verdrahtet (Aufrufstellen ersetzt
durch `_rs_spy_row_html()`).

---

## Position-Tracking (Exit-Signale)

`positions.json` listet offene Positionen für Exit-Score-Berechnung im
Daily-Run. **Wird nicht im Repo gespeichert** (Privacy) — der Workflow
schreibt sie zur Laufzeit aus dem GitHub-Secret `POSITIONS_JSON`.

### Schema

```json
{
  "TICKER": {
    "entry_date":  "YYYY-MM-DD",
    "entry_price": 12.34
  }
}
```

`entry_date` im ISO-Format (Achtung: `score_history.json` nutzt `DD.MM.YYYY`
intern, der Lookup im Code rechnet um). `entry_price` als Float in USD.

### Quelle: privater Gist (Phase 2) mit POSITIONS_JSON-Fallback

Ab Phase 2 ist die kanonische Quelle ein **privater User-Gist**
(siehe Sektion **Position-Tracking (Phase 2 — Gist-Sync)** unten).
Beide Workflows ziehen ``squeeze_data.json`` über
``scripts/pull_gist_data.py`` und materialisieren daraus
``positions.json``:

```yaml
- name: Pull squeeze_data from Gist
  env:
    GIST_ID:        ${{ secrets.GIST_ID }}
    GIST_TOKEN:     ${{ secrets.GIST_TOKEN }}
    POSITIONS_JSON: ${{ secrets.POSITIONS_JSON }}   # Migration-Fallback
  run: python scripts/pull_gist_data.py
```

Reihenfolge der Quellen (in pull_gist_data.py):
1. Gist (``GIST_ID`` + ``GIST_TOKEN`` gesetzt, API erreichbar, Datei
   ``squeeze_data.json`` enthält ``positions``).
2. ``POSITIONS_JSON``-Secret als Migrations-/Fallback-Pfad
   (alte Single-Position-Konfiguration).
3. Leeres Dict → ``process_exit_signals()`` no-op.

Sobald der User die Position in den Gist umgezogen hat, kann das
``POSITIONS_JSON``-Secret entfernt werden — der Code-Pfad bleibt nur
noch für Tests / Forks aktiv.

### Exit-Score-Komponenten (0–100, gewichtet, Cap 100)

| Komponente        | Gewicht | Logik |
|-------------------|--------:|---|
| Trailing-Stop     | **40 %** | Drawdown vom `high_since_entry`. ≥ `EXIT_TRAILING_STOP_PCT` (12 %) → 100, linear darunter |
| Setup-Verfall     | **25 %** | Setup-Score am Entry-Tag (aus `score_history`) vs. heute (aus aktuellem Run). Drop ≥ `EXIT_SETUP_DROP_THRESHOLD` (20 Pkt) → 100 |
| Distribution-Day  | **20 %** | heute RVOL ≥ `EXIT_DISTRIBUTION_RVOL` (3.0×) **und** Tages-PnL < 0 → 100, sonst 0 |
| Time-Decay        | **15 %** | ab `EXIT_TIME_DECAY_DAYS` (10) Tagen ohne Tagesbewegung ≥ `EXIT_TIME_DECAY_MOVE_PCT` (8 %) linear bis Tag 20 → 100 |

Alert-Schwellen + Cooldown (alles in `config.py` konfigurierbar):
- `EXIT_ALERT_THRESHOLD = 60` → ntfy-Push `📉 Exit N | ±N% | top driver`
- `EXIT_PROFIT_TAKE_PCT = 50.0` → ntfy-Push `💰 Profit-Take | +N% seit Entry | Halbe Position?`
- `EXIT_COOLDOWN_HOURS = 4` pro **(Ticker, Alert-Typ)** via Key-Prefix `exit_` / `profit_` in `agent_state.json` (gemeinsame State-Datei mit ki_agent, kollisionssicher durch Prefix)

Implementierung in `generate_report.py`:
- `compute_exit_score(ticker, position, current_data, history)` — pure Funktion
- `process_exit_signals(stocks)` — wird im Daily-Run nach Step 4 (HTML) aufgerufen, leise Fehler

### Setup-Verfall-Symmetrie: raw vs. raw

**Wichtig:** `setup_at_entry` **und** `setup_today` werden beide aus
`score_history` (raw, pre-smoothing) gelesen. `setup_scores` in
`app_data.json` ist **smoothed** und wird nur fürs Frontend (Kachel)
und die Alert-Anzeige genutzt — **nicht** für den Exit-Vergleich.

Hintergrund (Bug, behoben am 02.05.2026): zuvor hatte
`process_exit_signals` `setup_today` aus `setup_today_by_ticker`
(= `s["score"]`, smoothed) gezogen. `setup_at_entry` kommt aber
aus `score_history` (raw). Die Mischung erzeugte Glättungs-Artefakte:
ein Eintages-Spike am Entry-Tag (z. B. INDI raw 91.56 am 27.04. nach
einem Tag) lief gegen den smoothed Wert von heute (61.1 nach drei-
Tage-Glättung) und produzierte einen scheinbaren „Drop" von 30 Pkt,
der größtenteils Mittelung war. Symmetrische raw-vs-raw-Variante
vergleicht heutigen raw-Eintrag aus `score_history.{ticker}[-1]`
mit dem raw-Eintrag am `entry_date`.

### Wichtig: niemals `positions.json` committen

`.gitignore` enthält `positions.json`. Bei einem Refactor des `_load_positions()`-Pfads diese Regel beibehalten — die Datei darf nie ins Repo wandern. Bei lokalem Test eine `positions.json` anlegen ist OK; sie wird vom Git ignoriert.

---

## Position-Tracking (Phase 2 — Gist-Sync)

Watchlist und Position sind ab Phase 2 **entkoppelt**: Watchlist-Ticker
sind nur beobachtet; Position ist optional. Beide Datenstrukturen liegen
in einem **privaten User-Gist**, der vom Browser (lesen + schreiben) und
vom Workflow (nur lesen) angesprochen wird.

### Setup (User-Action, einmalig)

1. `gist.github.com` → **Create secret gist**, Filename
   `squeeze_data.json`, Inhalt:
   ```json
   {
     "watchlist": [],
     "positions": {}
   }
   ```
2. Gist-ID aus der URL kopieren (`gist.github.com/<user>/<id>` → `<id>`).
3. Repo-Secrets setzen:
   - `GIST_ID` = die kopierte ID
   - `GIST_TOKEN` = PAT mit Scope `gist` (oft derselbe wie der bereits
     für Watchlist genutzte PAT, falls dort `gist` schon aktiviert ist)
4. Browser: bestehender PAT im Settings-Panel **muss `gist`-Scope haben**
   (sonst können `gistLoad` / `gistSave` keine API-Calls absetzen — UI
   zeigt dann `⚠ Gist-Sync HTTP 404` und merkt nur lokal). Token wird
   im selben localStorage-Key (`ghpat_squeeze`) gespeichert wie für
   Repo-Watchlist-Sync.
5. Optional: ``POSITIONS_JSON``-Secret nach erfolgreicher Migration
   leeren — der Fallback-Pfad bleibt aber aktiv, falls man später
   ein zweites Repo provisioniert.

### Schema

```json
{
  "watchlist": ["TICKER", ...],
  "positions": {
    "TICKER": {
      "entry_date":           "YYYY-MM-DD",
      "entry_price":          12.34,
      "shares":               35,
      "entry_dtc":            18.36,
      "entry_short_float":    30.56,
      "entry_cost_to_borrow": 20.0,
      "entry_snapshot_ts":    "2026-04-27T14:00:00Z",
      "entry_monster_score":  72.5,
      "entry_ki_score":       80,
      "entry_rvol":           3.2,
      "entry_si_trend":       "up",
      "entry_conviction_components": {
        "setup": 28, "earliness": 21, "anomaly": 14, "regime": 11
      },
      "entry_thesis":         "Trigger: 13D-Filing + DTC 12 + RVOL-Spike."
    }
  }
}
```

`shares` ist neu gegenüber Phase 1 — wird im Frontend für Stück-Anzeige
genutzt. Die Exit-Score-Logik (`compute_exit_score`) ignoriert `shares`
weiterhin (rechnet nur mit `entry_price`).

**Trigger-4-Snapshot (`entry_dtc` / `entry_short_float` /
`entry_cost_to_borrow` / `entry_snapshot_ts`)** ist optional und wird
beim Position-Open im Frontend aus `_APP_DATA.watchlist_cards[ticker]`
gelesen (Quelle: enriched Top-10-Daten). Felder dürfen einzeln `null`
sein (Driver wird bei der Erosion-Berechnung übersprungen, aber andere
Drivers bleiben bewertbar). `entry_snapshot_ts` markiert die Existenz
des Snapshots — fehlt es, ist der Setup-Erosion-Trigger auf
`available=False` mit reason `no_entry_snapshot`, was Bestandspositionen
vor der Schema-Erweiterung (06.05.2026) sauber abgrenzt. Backfill ist
manuell (Position schließen + neu eröffnen).

**Score-Snapshot-Erweiterung (15.05.2026)** — fünf zusätzliche Felder
beim Position-Open auto-snapshottet (alle optional, alle aus
`_APP_DATA`):

| Feld | Quelle | Bedeutung |
|---|---|---|
| `entry_monster_score` | `monster_scores[ticker]` | Setup × KI-Boost-Aggregat zum Entry |
| `entry_ki_score` | `watchlist_cards[ticker].ki_signal_score` | KI-Agent-Score zum Entry |
| `entry_rvol` | `watchlist_cards[ticker].rel_volume` | Volumen-Spike-Magnitude zum Entry |
| `entry_si_trend` | `watchlist_cards[ticker].si_trend` | SI-Trend-Kategorie (`up`/`down`/`sideways`/`no_data`) |
| `entry_conviction_components` | `conviction_scores[ticker].components` | Sub-Objekt `{setup, earliness, anomaly, regime}` mit Conviction-Aufschlüsselung |

Plus User-Freitext `entry_thesis` (optional, max 500 Zeichen) — wird
beim Position-Schließen automatisch in die These-Textarea
**pre-gefüllt** (Cache aus Bug-A-Recovery hat Vorrang vor Pre-Fill).
Wenn beim Schließen editiert, landet der finale Wert im
`closed_trades[i].thesis` (Schema dort unverändert). Bestandspositionen
vor 15.05.2026 haben kein `entry_thesis` — Pre-Fill fällt auf leer,
User füllt manuell wie zuvor.

Soft-Migration für alle Score-Snapshot-Felder: bei Bestandspositionen
sind sie schlicht `undefined`, Render und Auswertung sind null-tolerant.

### Datenfluss

| Akteur | Lesen | Schreiben |
|---|---|---|
| `scripts/pull_gist_data.py` (Workflow) | GET `gists/<GIST_ID>` | `positions.json` + ggf. `watchlist_personal.json` (Materialisierung) |
| `generate_report.py` (Workflow) | `positions.json`, `watchlist_personal.json` | (unverändert — beide Files weiterhin der Read-Pfad im Python-Code) |
| Browser `gistLoad()` | GET `gists/<GIST_ID>` mit User-PAT | Cache `_GIST_DATA` |
| Browser `gistSave(data)` | — | PATCH `gists/<GIST_ID>` mit User-PAT |
| UI-Aktion „Position eröffnen" | `gistLoad()` | `gistSave({...positions: {ticker: {entry_date, entry_price, shares}}})` |
| UI-Aktion „Position schließen" | `gistLoad()` | `gistSave(without ticker in positions)` |
| UI-Aktion „Aus Watchlist entfernen" | `gistLoad()` + bestehender `wlRemoveTicker` | `gistSave(without ticker in watchlist & positions)` + `wlSave` (Repo-Datei) |

`GIST_ID` wird zur Render-Zeit per ENV-Variable in den HTML-Output
injiziert (`const GIST_ID = '…'` ganz oben im JS-Block, sanitized auf
`[A-Za-z0-9]{,64}`). Leerer String → `buildPositionPanel` zeigt
„Position-Tracking inaktiv — Gist nicht konfiguriert".

### Workflow-Steps

```yaml
- name: Pull squeeze_data from Gist
  env:
    GIST_ID:        ${{ secrets.GIST_ID }}
    GIST_TOKEN:     ${{ secrets.GIST_TOKEN }}
    POSITIONS_JSON: ${{ secrets.POSITIONS_JSON }}
  run: python scripts/pull_gist_data.py

- name: Generate squeeze report
  env:
    NTFY_TOPIC:       ${{ secrets.NTFY_TOPIC }}
    EDGAR_USER_AGENT: ${{ secrets.EDGAR_USER_AGENT }}
    GIST_ID:          ${{ secrets.GIST_ID }}   # in HTML embedden
  run: python generate_report.py
```

`pull_gist_data.py` ist **fail-soft**: API down / 401 / Parse-Fehler
führen nicht zum Workflow-Abbruch — der Daily-Run greift dann auf den
`POSITIONS_JSON`-Fallback zurück (Watchlist-File bleibt unangetastet,
weil das in-Repo-File ohnehin als sekundäre Quelle gilt).

### Frontend — Position-Panel in expandierter Watchlist-Karte

`buildPositionPanel(ticker, currentPrice)` rendert je nach State:
- **Position offen:** Entry-Datum, Einstiegskurs, Stückzahl, P&L
  (gegen aktuellen Spot), Buttons „Position schließen" + „Aus
  Watchlist entfernen".
- **Keine Position:** Button „Position eröffnen" → klappt Formular
  mit Datum (heute default), Einstiegskurs (Spot default) und
  Stückzahl auf. Save → `gistSave` + Panel-Refresh.
- **Lädt:** Placeholder, bis `gistLoad()`-Response da ist
  (Async-Refresh via `_refreshPositionPanel(ticker)`).
- **Kein GIST_ID / kein Token:** Hinweis + Settings-Verweis.

Optimistic UI: `gistSave` schreibt erst den Cache, dann den Gist —
die UI bleibt responsiv, Sync-Fehler erscheinen als `⚠ Gist-Sync …`-
Warnung über `_wlWarn()`.

### Pflege

- Schema-Änderungen (z. B. neues Feld `entry_currency`) gleichzeitig
  in `pull_gist_data.py`, `_load_positions()`, `compute_exit_score`
  und `buildPositionPanel` (`pos.entry_*`-Lookups) durchziehen.
- `GIST_FILE = "squeeze_data.json"` ist hartkodiert in
  `scripts/pull_gist_data.py` und im JS — bei Umbenennung beide Stellen
  synchron halten.
- Niemals einen Public-Gist verwenden — Position-Daten sind
  privacy-relevant.

---

## Phase 2 exit_state-Schema (app_data.json)

Pro offener Position schreibt der Daily-Run via
`_build_phase2_positions_payload` ein Position-Sub-Dict nach
`app_data["positions"][ticker]`. Felder (Top-Level):

| Key | Typ | Bedeutung |
|---|---|---|
| `entry_date`, `entry_price`, `shares`, `entry_fx`, `fx_estimated` | aus Gist | Stammdaten beim Position-Open |
| `entry_dtc`, `entry_short_float`, `entry_cost_to_borrow`, `entry_snapshot_ts` | aus Gist (optional) | Trigger-4-Setup-Erosion-Snapshot beim Open |
| **`current_price`** (neu seit 16.05.2026) | float \| None | Aktueller Spot-Preis. Reihenfolge: Top-10-Lookup (`stocks[t].price`) → `_fetch_position_market_data`-yfinance-Singleton-Fallback → `None`. Update-Frequenz: **2× pro Werktag** (premarket 10:17 UTC + postclose 21:17 UTC Daily-Run). KI-Agent-Tick (xx:17) berührt das Feld nicht; `**existing`-Spread in `save_signals` preserviert den letzten Daily-Run-Wert. Stündliche Updates wären separater Folge-PR (KI-Agent-Tick-Erweiterung). |
| `exit_state` | dict | siehe Sub-Schema unten |

`current_price` schließt Health-Check S3 für alle Positionen mit
yfinance-Verfügbarkeit. Bei echtem Fetch-Fehler bleibt das Feld `None`
— S3 meldet dann zurecht (echter Daten-Lücken-Indikator).

### Sub-Schema `exit_state`

(via `_compute_exit_state` befüllt, in `app_data["positions"][ticker]["exit_state"]`)

| Key | Typ | Bedeutung |
|---|---|---|
| `exit_pressure`             | int 0..100  | Composite aus den 6 Trigger-Sub-Scores |
| `triggers`                  | dict        | Sub-Score-Dict pro Trigger (`score_decay`, `profit_lock`, `overheated`, `setup_erosion`, `catalyst`, `trend_break`) |
| `peak_score_since_entry`    | float \| None | ratchet-up-only Setup-Score-Peak seit Entry |
| `peak_pnl_pct_since_entry`  | float \| None | ratchet-up-only PnL-Peak seit Entry (Fraction) |
| `current_score`             | float \| None | heutiger raw Setup-Score |
| `current_pnl_pct`           | float \| None | heutige PnL-Fraction |
| `prev_exit_pressure`        | int \| None   | `exit_pressure` des vorigen Daily-Runs, `None` bei Erstanlage / fehlendem prev_state / nicht-int-castbarem Wert. Wird in Stufe 3b-3 für once-per-cross-Eskalations-Logik gegen den aktuellen `exit_pressure` verglichen. |
| `computed_at`               | str ISO-UTC | Schreib-Zeitstempel |

Read-modify-write durch `_build_phase2_positions_payload`: voriges
`exit_state` aus `prev_app_data` (= `_read_existing_app_data()`)
wird als `prev_state`-Argument an `_compute_exit_state` durchgereicht.
Peak-Felder sind ratchet-up-only; `prev_exit_pressure` ist ein
reines Snapshot-Spiegelfeld (kein Ratchet).

### Trigger-Implementierungs-Status

| Trigger | Gewicht | Status | Daten-Voraussetzung |
|---|---:|---|---|
| `score_decay`   | 30 % | **live** | ≥ 7 Einträge in `score_history` für den Ticker |
| `profit_lock`   | 25 % | **live** | `peak_pnl_pct_since_entry` + `current_pnl_pct` |
| `overheated`    | 20 % | **live** | `rsi14` / `change_2d` / `change_3d` in `top10_metrics` |
| `setup_erosion` | 15 % | **live** | Entry-Snapshot (`entry_dtc` / `entry_short_float` / `entry_cost_to_borrow` / `entry_snapshot_ts`) im Gist + aktuelle Werte aus `s_top` (Top-10-enriched). Drei relative Drops gegen `SETUP_EROSION_WARN_THRESHOLD` (0.30) / `SETUP_EROSION_CRIT_THRESHOLD` (0.50); Combo-Bonus bei ≥ `SETUP_EROSION_COMBO_DRIVERS_MIN` (2) Drivers gleichzeitig in warn. Bestandsposition ohne Snapshot → `available=False` (reason `no_entry_snapshot`). |
| `catalyst`      |  5 % | **live** | Nächstes Earnings-Datum via Finnhub (FINNHUB_API_KEY) → yfinance-Fallback; Trading-Tage bis Earnings ≤ `CATALYST_DAYS_WINDOW` |
| `trend_break`   |  5 % | **live** | `ma21` (EMA21) in `top10_metrics` + `cur_price` aus `_fetch_position_market_data` |

**Spec-Divergenz Trigger 5:** Frühere Stub-Note („Historischer
Earnings-Lookup zwischen Entry und heute") war backward-looking
(Earnings vergangen ohne Reaktion). Die jetzt implementierte
Forward-Variante feuert, wenn die NÄCHSTE Earnings-Veröffentlichung
innerhalb `CATALYST_DAYS_WINDOW` (Default 2) Trading-Tage ahead
liegt — binäres Risiko, vor dem die Position bewusst gesichert
oder geschlossen werden kann. Backward-Variante kann später als
separater Trigger nachgereicht werden, ohne diesen zu ersetzen.

`catalyst`-Schwellen (`config.py`): Sub-Score = 0 wenn keine
Earnings im Fenster, 50 (warn) wenn `0 < days_until ≤
CATALYST_DAYS_WINDOW`, 100 (crit) wenn `days_until == 0`
(Earnings heute). `days_until` zählt Werktage (Mo–Fr), US-
Feiertage werden nicht abgezogen.

Datenfluss: `_fetch_next_earnings_date(ticker, today)` ist
Single-Source-of-Truth — Reihenfolge Finnhub → yfinance. Beide
Quellen leer → `available=False`. Fetcher wird per kwarg in den
Trigger injiziert (Tests mocken ohne Netzwerk).

`trend_break`-Schwellen (`config.py`): Sub-Score = 0 wenn
`price ≥ ma21`, 50 (warn) wenn `0 < drop_pct ≤ EXIT_TREND_BREAK_CRIT_PCT`
(3 %), 100 (crit) wenn `drop_pct > 3 %`. `drop_pct = (ma21 − price) /
ma21 × 100`. EMA21 wird in `_compute_indicators` via
`close.ewm(span=21, adjust=False)` berechnet und im
`results[ticker]`-Dict / merge bei Z. ~12700 als `ma21` mitgeführt.

### Phase-2-Push-Pipeline-Status (Stufe 3b-3b)

Alle drei Klassen in `process_exit_signals` (ki_agent.py) sind
**scharfgeschaltet** — jede mit eigener Drossel-Strategie und
klassen-spezifischer ntfy-Severity. Single Push-Helper
`_send_exit_p2_push(ticker, body, severity="trigger")` verteilt
Priority + Tag inline pro Severity.

| Klasse | Bedingung | Drossel | ntfy-Priority | Tag | Body-Format | Cooldown-Key |
|---|---|---|---|---|---|---|
| **Eskalation** | `prev_exit_pressure ≤ 75 < pressure_v` (once-per-cross) | KEIN Zeit-Cooldown — Cross ist selbst-limitierend | `urgent` | `rotating_light` | `🚨 Exit-Eskalation {T}: pressure {prev}→{now}/100` | — (kein Set) |
| **Warnung** | `55 ≤ pressure_v ≤ 75` | `EXIT_PUSH_WARNING_COOLDOWN_HOURS = 12` h pro Ticker | `high` | `warning` | `⚠️ Exit-Warnung {T}: pressure {now}/100` | `exitp2_warning_{T}` |
| **Trigger** | einzelner `crit=True` (unabhängig von pressure) | `EXIT_PUSH_TRIGGER_COOLDOWN_HOURS = 24` h pro (Ticker × Trigger-Name) | `high` | `rotating_light` | `🔻 Exit-Signal {T}: {name} crit ({details})` | `exitp2_trigger_{T}_{name}` |

Eskalations-Pflichtinvariante: `prev_exit_pressure` ist `None` bei
Erstanlage/unparsbar → **KEIN** Push (sonst würde jede frisch
eröffnete Position über Threshold sofort feuern). Gilt auch wenn
`prev_v > 75` (war bereits über Threshold) — kein erneuter Push,
SKIP-Audit-Log mit `no_cross`-Reason.

Audit-Log-Präfixe: `[exit_p2] SENT|SKIP|FAIL <klasse> <ticker>: …`
in stdout (Workflow-Log). Push-Fail (NTFY-Disabled, POST-Fehler) →
KEIN Cooldown gesetzt, nächster Tick retried.

### Push-History-Persistenz (Stufe 3c-1)

Vier ntfy-Push-Sender sind instrumentiert und persistieren jeden Versuch
(SENT **und** FAIL) als FIFO in `agent_state.json["push_history"]`:

| Sender | Kind | Severity | Trigger-Feld |
|---|---|---|---|
| `_send_anomaly_ntfy` (ki_agent) | `anomaly` | aus `anom["severity"]` | `anom["trigger"]` |
| `_send_exit_p2_push` (ki_agent) | `exit_p2` | `escalation` / `warning` / `trigger` | bei `trigger`-Klasse: Trigger-Name; sonst `null` |
| `send_ntfy_alert` (ki_agent, Earnings) | `earnings_immediate` | `default` | `null` |
| `_send_exit_ntfy` (generate_report) | `exit_p1` | `default` | `exit_alert` / `profit_take` |

Schema pro Eintrag:
`{ts (Berlin-ISO), ticker, kind, severity, trigger, body, success,
suppressed, suppress_reason}`. `suppressed=True` markiert absichtlich
nicht-versendete Pushes (Conviction-Gating); `suppress_reason` enthält
den Kurz-Code (`"conviction_below_threshold"` etc.). Bei `suppressed=False`
ist `suppress_reason=None`.

Cap: `PUSH_HISTORY_MAX = 100` (FIFO, älteste raus). Helper `_record_push`
lebt als Single-Source-of-Truth in `push_history.py` (Repo-Root) und wird
sowohl von `ki_agent.py` als auch von `generate_report.py` per `from
push_history import _record_push` eingezogen — bei Schema-Änderung nur
diese eine Stelle anpassen.

Daily-Summary-E-Mail (`send_daily_summary`) ist **nicht** instrumentiert —
push_history ist auf ntfy-Versand beschränkt, E-Mail-Pfad bleibt außen vor.

State-Race-Robustheit: FIFO-Cap = 100 macht uns gegen einzelne fehlende
Einträge robust bei Race zwischen ki_agent und Daily-Run. Last-Write-Wins
akzeptiert. Im Daily-Run wird der State nur gespeichert, wenn `n_sent > 0`
oder `push_history` in diesem Run gewachsen ist (failed-Push-Audit muss
erhalten bleiben).

### app_data.json-Spiegel (Stufe 3c-2)

`push_history` wird im Daily-Run aus `agent_state.json` nach
`app_data.json` gespiegelt (read-only-Spiegel, identisches Schema,
identische Reihenfolge — keine Filterung, kein Renaming). Quelle bleibt
`agent_state.json`; Stufe 3c-2 liefert nur den Browser-Lese-Pfad ohne
zusätzlichen HTTP-Request. Last-Write-Wins zwischen Daily-Run und
parallelen ki_agent-Ticks akzeptiert. Fail-soft bei fehlender oder
unparsbarer State-Datei → leere Liste, kein Crash.

### UI Notification-History (Stufe 3c-3 — live)

Hamburger-Menü-Eintrag „Push-Historie" öffnet
`<section id="push-history-section">` (analog zu Trade-Journal-Pattern,
gleiche `info-panel`/`info-box`-Klassen, gleiche `.tj-filters`-Optik
für Filter und Stats-Grid für Statistik). Drei Boxen:

- **Stats:** Gesamt-Anzahl, Erfolgsrate, ältester / neuester Eintrag,
  Aufteilung nach Severity (`high` / `medium`), Aufteilung nach `kind`.
  Stats werden aus der **kompletten** push_history berechnet — nicht
  aus der gefilterten Sicht, damit die Erfolgsrate nicht vom aktiven
  Filter abhängt.
- **Filter:** Zeitraum (alle / 24 h / 7 d), Severity (alle / high /
  medium), Art / `kind` (alle / anomaly / exit_p1 / exit_p2 /
  conviction_high / earnings_immediate), Ticker-Free-Text. Default
  „alle" für jeden Slot.
- **Liste:** Eine `.ph-row` pro Eintrag, neueste oben. Format:
  Zeitstempel · Ticker · Severity-Pill (rot/grau) · Trigger-Name ·
  Body (raw — enthält bereits Emojis aus den Sender-Funktionen, keine
  zusätzliche Icon-Logik im Frontend). Bei `success=false` zusätzlich
  ⚠-Indikator.

Render-Funktion `renderPushHistory()` ist rein lesend auf
`window._APP_DATA.push_history` und filtert clientseitig. Bei leeren
Filter-Slots zeigt sie dezenten Hinweis statt verwirrend leerer Liste
(z. B. „Noch keine Exit-P2-Pushes gespeichert" wenn der `kind`-Filter
auf einen nie aktiven Sender zeigt).

CSS lebt in `templates/head.jinja` unter „Push-Historie (Phase 2 Stufe
3c-3)" — eigene `.ph-row`/`.ph-sev-pill`/`.ph-kind-pill`/`.ph-empty`-
Klassen plus eine Mobile-Override-Regel ab 480 px für volle Spalten-
Breite der Filter-Labels.

### Phase 3 Exit-Signal — Blow-off-Top (spec'd, noch nicht implementiert)

Phase 3 ergänzt einen einzelnen Trigger `blowoff_top` für parabolische
Endphasen-Squeezes (50 % in 5 d UND Reversal heute ≤ −5 %). Spec liegt
in ``docs/phase3_exit_spec.md`` — Single-Source-of-Truth für den
späteren Code-Bau. **Implementation erfolgt erst nach Live-Test bei
einer offen-gehaltenen Position in einem CRMD-artigen Setup**, in der
Phase-2-Trigger empirisch zu spät reagiert haben.

IV-Crush war ursprünglich als zweiter Phase-3-Trigger geplant, wurde
aber 15.05.2026 gestrichen (Daten-Limits + geringer Trading-Wert für
Aktien-Halter). Begründung steht in Sektion E der Spec.

---

## Trade-Journal (Phase 2.5)

Erweiterung des Position-Trackings um persistente Erfassung
geschlossener Trades + Statistik-Übersicht. Daten leben im selben
privaten Gist (`squeeze_data.json`), neue Top-Level-Sektion
`closed_trades`. Reines Frontend-Feature — der Daily-Run / KI-Agent
ignoriert `closed_trades` weiterhin (`pull_gist_data.py` zieht es
nicht in eine Materialisierungs-Datei).

### Schema-Erweiterung

```json
{
  "watchlist":     [...],
  "positions":     {...},
  "closed_trades": [
    {
      "ticker":          "INDI",
      "entry_date":      "2026-04-27",
      "entry_price":     3.76,
      "exit_date":       "2026-05-15",
      "exit_price":      4.50,
      "shares":          35,
      "pnl_abs":         25.90,
      "pnl_pct":         19.7,
      "thesis":          "RVOL-Spike + Insider-Buy",
      "lesson":          "zu früh verkauft, lief weiter",
      "max_setup_score": 82,
      "duration_days":   18,
      "closed_at":       "2026-05-15T18:42:11.000Z",
      "entry_fx":         0.92,
      "exit_fx":          0.91,
      "exit_fx_eur":     143.33,
      "realized_pnl_eur": 22.10
    }
  ]
}
```

`thesis` und `lesson` sind optionale Free-Text-Felder. `max_setup_score`
wird beim Schließen aus `window._SCORE_HISTORY[ticker]` ermittelt
(größter Score zwischen `entry_date` und `exit_date`, ISO-Vergleich
nach DE→ISO-Konvertierung). `pnl_abs = (exit_price − entry_price) ×
shares` in USD. `closed_at` ist Browser-Wallclock-ISO für
Reihenfolge-Debug.

#### EUR-Felder (Stufe 3/4, persistiert ab 06.05.2026)

Vier optionale numerische Felder, die den realisierten Gewinn auch
historisch korrekt in EUR rekonstruierbar machen — ohne sie würde der
Trade-Journal-Renderer auf den **aktuellen** `_FX_USD_EUR` zurückfallen
und alte Trades bei FX-Schwankungen falsch darstellen.

| Feld | Typ | Bedeutung |
|---|---|---|
| `entry_fx`         | Float \| None | EUR pro 1 USD zum **Entry-Tag**. Resolution-Kette in `wlSubmitClose` (`generate_report.py:9387-9396`): zuerst `pos.entry_fx` aus dem Gist, sonst Backfill aus `window._POSITIONS_DATA[ticker].entry_fx` (gesetzt vom Daily-Run, `generate_report.py:11294-11301`). `null` wenn beide Quellen leer. |
| `exit_fx`          | Float \| None | EUR pro 1 USD zum **Exit-Zeitpunkt** = aktueller `window._FX_USD_EUR` beim Schließen. `null` wenn FX-Bridge nicht verfügbar. |
| `exit_fx_eur`      | Float \| None | `exit_price × exit_fx × shares`, gerundet auf 2 Nachkommastellen — das EUR-Äquivalent des Verkaufserlöses (Brutto). |
| `realized_pnl_eur` | Float \| None | `exit_fx_eur − (entry_price × entry_fx × shares)`, gerundet auf 2 Nachkommastellen — der tatsächliche EUR-PnL unter Berücksichtigung beider FX-Endpunkte. `null` wenn `entry_fx` oder `exit_fx` fehlt. |

Reader-Helper in `generate_report.py:6333-6354`: `_tjResolveEntryFx`,
`_tjResolveExitFx`, `_tjResolvePnlEur` sind die Single-Source-of-Truth
für die Trade-Journal-Anzeige; alte Trades ohne diese Felder fallen
auf den Live-`_FX_USD_EUR`-Approx zurück (Migrations-Pfad,
dokumentiert in den Helpern).

### Datenfluss

| Akteur | Lesen | Schreiben |
|---|---|---|
| `wlSubmitClose(ticker)` | `gistLoad()` + `_SCORE_HISTORY` | `gistSave({...positions: ohne ticker, closed_trades: [...alt, neu]})` |
| `renderTradeJournal()` | `gistLoad()` (closed_trades) + DOM-Filter | — |
| `pull_gist_data.py` (Workflow) | Gist (komplett) | nur `positions.json` + ggf. `watchlist_personal.json` — `closed_trades` wird ignoriert |

### UI

- **Hamburger-Menü** → neuer Eintrag „Trade-Journal" (Lucide-Icon
  `clipboard-list`), zwischen „Score-Methodik" und „Score-Sortierung".
- **Position-Close-Form** ersetzt den alten ein-Klick-`confirm()`-Dialog:
  `<input type="date">` Verkaufsdatum (default heute),
  `<input type="number">` Verkaufskurs (default Spot),
  `<textarea>` These und Lesson (beide optional). Submit ruft
  `wlSubmitClose(ticker)`.
- **Trade-Journal-Sektion** (`#trade-journal-section`, hidden bis
  geöffnet) — drei `info-box--full`-Karten: Statistik-Grid, Filter
  (Zeitraum + Hit/Miss), Trade-Liste neueste zuerst.

### Statistiken (`renderTradeJournal`)

| Kennzahl | Berechnung |
|---|---|
| Trades | `filtered.length` |
| Hit-Rate | `winners.length / filtered.length × 100` |
| Ø Rendite | Mittelwert aller `pnl_pct` |
| Ø Gewinner / Verlierer | Mittelwert nur positiver / nur negativer `pnl_pct` |
| Summe P&L | `Σ pnl_abs` (USD + EUR-Spiegel via `_FX_USD_EUR`) |
| Bester / Schlechtester | Trade mit `max(pnl_pct)` / `min(pnl_pct)` |
| Setup-Score-Korrelation | Ø `max_setup_score` getrennt für Gewinner / Verlierer |

Filter: Zeitraum (alle / 30 / 90 / 365 d, gegen `exit_date`) und
Ergebnis (alle / Gewinner / Verlierer).

### Knaller-Trade-Label (Phase 2, 16.05.2026)

Markiert einzelne Trades als **Knaller-Hit** (`▲ TOP 10%`) oder
**Knaller-Crash** (`▼ BOT 10%`) basierend auf der Backtest-Bucket-Tail-
Verteilung. Pure Display-Auswertung, keine Score-Logik berührt.

**Definition (Hybrid mit absolutem Floor):**

| Label | Bedingung | Floor | Fallback bei n<30 im Bucket |
|---|---|---|---|
| `▲ TOP 10%` (Hit) | `pnl_pct ≥ P90(return_10d)` im passenden `entry_score_bucket` | `pnl_pct ≥ +10%` | absolute Schwelle `≥ +25%` |
| `▼ BOT 10%` (Crash) | `pnl_pct ≤ P10(return_10d)` im passenden Bucket | `pnl_pct ≤ −10%` | absolute Schwelle `≤ −20%` |

**Bucket-Sync:** Bucket-Grenzen `<50` / `50-69` / `≥70` sind in **drei**
Stellen identisch zu halten:
- `_tjScoreBucket(score)` (Trade-Journal-Klassifikation pro Trade)
- `_btBucketStats(data)` (Backtest-Panel-Aggregation)
- `_tjBucketRef()` (Knaller-Phase-2-Referenz, lazy lazy-async)

Bei Bucket-Grenzen-Änderung alle drei Stellen synchron pflegen.

**Datenquelle:** `backtest_history.json` über `window._BT_DATA`-Bridge
(gesetzt nach `_btData`-Load im Backtest-Panel) — Fallback eigener
`fetch('./backtest_history.json')` wenn Trade-Journal vor dem
Backtest-Panel gerendert wird. `_tjBucketRef` cached das Ergebnis in
`window._TJ_BUCKET_REF._cached = true`.

**Statistik-Zelle „Knaller"** im Stats-Grid (full-width):
`▲ H/W X% · ▼ C/L Y%` (H=Hits, W=Gewinner-total, X=Quote · C=Crashes,
L=Verlierer-total, Y=Quote). Bei <5 Gewinnern: `(n=N zu wenig)` statt
Prozentzahl. Tooltip mit Definitions-Erklärung.

**Per-Trade-UI:** Text-Badge `▲ TOP 10%` (grün) bzw. `▼ BOT 10%` (rot)
direkt nach dem Ticker. CSS-Klassen `.tj-knaller-badge`
+ `.tj-knaller-hit`/`.tj-knaller-crash`. Tooltip enthält konkrete
Bucket-P90/P10-Schwelle und n. Zusätzlich Container-Klasse
`.tj-trade-knaller-hit` / `-crash` für 5-px-Border-Akzent statt 3 px
(bestehende `.tj-trade-win`/`-loss`-Border-Farbe bleibt unverändert).

Badge-Design-Entscheidung (16.05.2026, ersetzt Emoji-Variante aus PR
#172): klar lesbar ohne Tooltip-Hover, konsistent zur restlichen Tool-
Pill-Optik (Conviction-Level, SI-Trend, Run-Phase-Pill), mobile-tauglich.

**Backtest-Referenz-Charakter:** Knaller-Label vergleicht gegen die
**komplette Backtest-Verteilung pro Bucket**, nicht gegen Easy's eigene
Trade-Sammlung. Damit ist die Klassifikation ab Trade #1 nutzbar —
Sample-Size-Effekt nur in der aggregierten Hit-Rate-Statistik
(„statistisch erwartet ≤ 10% deiner Gewinner als Hits"). Bei
`backtest_history.json` heute n=818/327/118 je Bucket → P90/P10
solide berechenbar.

### Pflege

- Bei Schema-Änderung in `closed_trades` (z. B. neues Feld `tags[]`)
  immer simultan: `wlSubmitClose` (Schreiber), `renderTradeJournal`
  (Leser/Anzeige), CLAUDE.md-Schema-Block oben.
- **Bucket-Grenzen-Änderung** (50/70): `_tjScoreBucket`,
  `_btBucketStats` und Bucket-Iteration in `_tjBucketRef` synchron
  halten. Falls neue Bucket-Klasse hinzukommt, auch
  `entry_score_bucket`-Klassifikation für Bestandstrades bedenken
  (kein automatischer Backfill — pro Trade beim Re-Open neu).
- **Knaller-Schwellen-Anpassung** (`_TJ_KNALLER_FLOOR_HIT/CRASH` /
  `_TJ_KNALLER_FALLBACK_HIT/CRASH` / `_TJ_KNALLER_MIN_N`): aktuell als
  JS-Konstanten in `renderTradeJournal`-Umfeld. Bei Bedarf nach
  `config.py` exportieren und via Render-Context durchreichen.
- Score-Methodik-Sync-Regel ist **nicht betroffen** — Trade-Journal
  ist außerhalb der Score-Berechnung. Knaller-Label ebenfalls.
- Migration alter Trades (ohne `max_setup_score` / `duration_days`):
  `renderTradeJournal` rendert `—` bei fehlendem Wert, kein Crash.
  Alte Trades ohne `entry_score_bucket`: Knaller-Klassifikation nutzt
  `entry_score`-Fallback; ohne beides → Bucket=null → Fallback-
  Schwellen.

---

## Score-Delta T-1 (Setup-Score, Phase 1)

Macht den Tagesvergleich des Setup-Scores direkt auf jeder Top-10-
und Watchlist-Drawer-Karte sichtbar — als kleine Span unter dem
Score-Wert. Design-Berater-Empfehlung 16.05.2026: prominent zeigen
wenn Setup-Score gegenüber gestern stark gestiegen oder gefallen ist;
Easy entscheidet ob „Squeeze in Ignition" oder „sterbend".

**Hybrid-Stille-Schwelle (verhindert Mini-Drift-Lärm):**

| |Δ| | Verhalten | CSS-Klasse |
|---|---|---|
| `< 2` | **nichts rendern** | (leerer String) |
| `2..5` (exklusiv) | dezent grau | `.sb-delta-mute` |
| `≥ 5` (positiv) | grün ▲ | `.sb-delta-up` |
| `≥ 5` (negativ) | rot ▼ | `.sb-delta-down` |
| `≥ 15` (zusätzlich) | bold | `.sb-delta-strong` Modifier |

**Quelle**: `s["sparkline"]["scores"]` (raw Setup-Scores aus
`score_history.json`, materialisiert in `apply_score_smoothing`).
Letzte zwei Einträge: `[-2]` = Vortag, `[-1]` = heute. Bei < 2
Einträgen kein Delta.

**Helper `_score_delta_html(s)`** in `generate_report.py` direkt vor
`_score_block_inner_html`. Pure Funktion ohne Side-Effects. Liest aus
`s.sparkline` — kein Threading durch Aufrufer-Pfade nötig. Returnt
`""` bei Edge-Cases (fehlende Sparkline, invalid scores, < 2 Einträge,
|Δ| < 2).

**Wiring**: nur Setup-Row in `_score_block_inner_html` zeigt Delta.
Conviction/Monster/KI-Rows ohne Delta — sie haben **keine
persistierte History** heute. Folge-PR-Idee siehe „Pflege" unten.

**Tooltip-Format**:
```
title="Δ +7.0 ggü. letztem Daily-Run (15.05.2026, raw 50.0 → 57.0)"
aria-label="Delta +7.0"
```

**Phasen-Mismatch**: premarket-heute vs postclose-gestern liefert
strukturell verzerrte Deltas (RVOL-Drift im premarket-Run). Helper
zeigt das ohne Disclaimer an — die Normalisierung adressiert das
Problem in der Berechnung (PR-α/β/γ-Pipeline), nicht in der Anzeige.

### Pflege

- Schwellen-Anpassung (2/5/15): aktuell als JS-/Python-Literal in
  `_score_delta_html` zentralisiert. Bei Änderung sowohl Helper als
  auch CLAUDE.md-Tabelle oben synchron pflegen.
- **Folge-PR-Idee (Phase 2)**: Conviction/Monster/KI-Delta erfordern
  eigene History-Persistenz. Vorschlag: `conviction_history.json`,
  `monster_history.json`, `ki_history.json` analog
  `score_history.json` (Schema `{ticker: [[date, value], ...]}`,
  14-Tage-Cutoff). Helper `_score_delta_html` mehrfach instanziieren
  mit Score-Klasse-Parameter. Vor diesem PR Easy fragen ob Setup-
  Delta nützlich im Alltag.
- Score-Methodik-Sync-Regel: **nicht betroffen** — reines Display-
  Feature, keine Score-Berechnung berührt.

---

## Sparkline-Tooltips mit Driver-Historie

Jeder Sparkline-Punkt zeigt bei Hover (Desktop) bzw. Tap (Mobile)
einen Tooltip mit **Datum**, **Score-Punkten** und der **KI-Treiber-
Historie** für genau diesen Tag. Quelle ist die persistierte
``score_history.json`` — nicht nur der Live-Snapshot.

### Schema-Erweiterung `score_history.json`

Pro Eintrag ein optionales drittes Feld ``drivers`` (Array von
Strings, max 6 Einträge — überzählige werden bei der Persistierung
gestrippt):

```json
{
  "INDI": [
    ["2026-04-27", 82, ["RVOL 3.2×", "Volumen 4.1×", "SEC 8-K", "Reddit +47"]],
    ["2026-04-28", 75]
  ]
}
```

- **3-Tuple:** ``[date, score, drivers[]]`` für Tage mit KI-Agent-Snapshot.
- **2-Tuple:** ``[date, score]`` für Legacy-Einträge oder Tage ohne
  KI-Agent-Daten — Migration ist null-cost: ``_load_score_history``
  liefert ``drivers: []`` als Default.
- Dict-Format ``{"date":..., "score":..., "drivers":[...]}`` ist
  weiterhin akzeptiert (read-only-Kompatibilität).

### Datenfluss

| Komponente | Lesen | Schreiben |
|---|---|---|
| ``apply_agent_boost`` (generate_report.py) | ``agent_signals.json`` | setzt ``s["ki_signal_score"]`` + ``s["ki_signal_drivers"]`` (String ``"X + Y + Z"``) auf jedem Stock mit Signal-Eintrag |
| ``apply_score_smoothing`` | ``s["ki_signal_drivers"]`` | persistiert ``[date, score, drivers[]]`` in ``score_history.json``; re-write wenn Score **oder** Drivers sich seit letztem Run geändert haben (jeder Tick erzeugt frische Snapshots) |
| ``_save_score_history`` | history-Dict | 3-Tuple wenn drivers nicht leer, sonst 2-Tuple (Bytes-Optimierung) |
| Sparkline-Payload (``s["sparkline"]``) | ``score_history`` | Liste ``drivers`` parallel zu ``scores`` und ``dates`` (gleiche Länge) |
| Frontend ``drawSparkline`` | ``data-drivers`` JSON-Attribut auf ``.spark-wrap`` | Tooltip-DOM bei Hit-Rect-Click/Hover |

### Frontend-UI

- **Hit-Areas:** unsichtbares ``<rect class="sp-hit">`` pro Punkt, Höhe
  = volle SVG-Höhe, Breite ``isMobile ? 28 : 22 px``. Erfüllt das
  ≥ 20 px-Touch-Target-Pattern auf Mobile, visueller Punkt bleibt 6 px
  Radius. Trägt JSON-Drivers + Score + Datum als data-Attribute.
- **Tooltip ``.spark-tip``:** sticky positioniert, oberhalb des
  getriggerten Punkts, horizontal zentriert + auf Sparkline-Breite
  geclamped. Inhalt: Header (Datum links, Score rechts farbcodiert
  gleich wie der Punkt), darunter ``<ul>`` mit max 4 Drivers oder
  „Keine KI-Treiber für diesen Tag" wenn Liste leer.
- **Schließen:** Tap außerhalb der ``.spark-wrap`` ODER Esc-Taste.
  Listener pro wrap einmal angebunden via ``wrap._sparkTipBound``-Flag,
  damit mehrere Sparklines auf der Seite unabhängig sind.
- **Live-Sync für rechtesten Punkt:** ``drivers[lastIdx]`` wird beim
  Live-Sync (KI-Agent-Snapshot ≤ 4 h alt) aus ``_AGENT_SIGNALS.signals
  [ticker].drivers`` aktualisiert. Ghost-Pfad pusht eigenen Driver-
  Eintrag, Overwrite-Pfad ersetzt nur wenn Live-Drivers nicht leer
  sind (sonst bleiben die History-Drivers erhalten).

### Pflege

- Bei jeder Schema-Änderung in ``score_history`` (z. B. neues Feld
  ``conf``): gleichzeitig ``_load_score_history``-Normalize,
  ``_save_score_history``-Compact-Pfad, ``apply_score_smoothing``-
  Persist und Sparkline-Payload-Builder (``s["sparkline"]``) anpassen.
- Score-Methodik-Sync ist **nicht betroffen** — Tooltips zeigen nur,
  was der KI-Agent als Drivers berichtet, nicht die Sub-Score-Komponenten.

---

## Master-Passwort-Token-Encryption (Phase 3)

GitHub-PAT liegt nicht mehr im Klartext in `localStorage`. Stattdessen
wird er mit einem User-Master-Passwort AES-GCM-verschlüsselt gespeichert;
der entschlüsselte Token lebt nur in `sessionStorage` während der Tab-
Session und ist mit Tab/Browser-Close weg.

### Storage-Keys

| Key | Storage | Inhalt |
|---|---|---|
| `ghpat_squeeze_encrypted` (`TOK_ENC_KEY`) | localStorage | JSON-Blob `{v, salt, iv, ct}` (alle Base64) |
| `ghpat_squeeze` (`TOK_KEY`) | **sessionStorage** | Klartext-Token, nur während Session |
| `ghpat_squeeze` (`TOK_LEGACY_KEY`) | localStorage | Alter Klartext-Slot vor Phase 3 — wird beim Cold-Start als Migrations-Quelle erkannt und nach Verschlüsselung gelöscht |

`TOK_KEY` und `TOK_LEGACY_KEY` haben denselben String-Wert (`'ghpat_squeeze'`),
liegen aber in unterschiedlichen Storages — `getToken()` liest immer aus
sessionStorage; localStorage-Slot ist nur für Migrations-Detection.

### Krypto-Parameter

- **PBKDF2** mit SHA-256, **600 000 Iterationen**, 16-Byte Salt → 256-Bit-Key.
- **AES-GCM** mit 12-Byte IV, 256-Bit-Key (Auth-Tag inklusive im Ciphertext).
- Salt + IV werden **pro Verschlüsselung neu generiert** (`crypto.getRandomValues`)
  und mit dem Ciphertext zusammen im Blob persistiert.
- Schema-Version `v: 1` im Blob — bei späteren Krypto-Upgrades Pfad für
  Re-Encrypt vorhanden.

### User-Flow / Modale

| Modal | Trigger | Aktion |
|---|---|---|
| **Setup** (`#tok-modal-setup`) | Erst-Setup ohne Token; Settings-Panel `saveGhToken` | Token + Master-Passwort + Bestätigung → Verschlüsseln + `localStorage[TOK_ENC_KEY]` + Session-Token setzen |
| **Unlock** (`#tok-modal-unlock`) | Action benötigt Token + Session leer + Encrypted-Blob da | Master-Passwort → Entschlüsseln → Session-Token setzen → pending Callback ausführen |
| **Migrate** (`#tok-modal-migrate`) | Cold-Start mit Klartext-Token + ohne Encrypted-Blob | Master-Passwort + Bestätigung → Klartext aus localStorage verschlüsseln + Klartext-Slot löschen |

### Orchestrator: `_ensureToken(callback)`

Aufrufer (z. B. `triggerWorkflow`, `triggerKiAgent`) rufen
`_ensureToken(token => doSomething(token))`. Logik:
1. `getToken()` liefert nicht-leer → callback sofort.
2. Sonst Encrypted-Blob vorhanden → Unlock-Modal.
3. Sonst Legacy-Klartext-Token → Migrate-Modal.
4. Sonst Setup-Modal.

`gistLoad` / `gistSave` / `wlLoad` / `wlSave` nutzen das gleiche Pattern
nicht aktiv — sie lesen `getToken()` direkt; bei leerer Session geben sie
silently auf (existierendes Verhalten). Der User wird via Recalculate-/
KI-Agent-/Setup-Aktion zum Unlock geführt.

### Reset-Pfad

- Unlock-Modal-Link **„Token neu eingeben"** (nach 3 Fehlversuchen prominent
  hervorgehoben) → `_clearAllTokens()` → Setup-Modal.
- Settings-Panel-Link **„Token löschen"** → `_clearAllTokens()`.
- `_clearAllTokens()` räumt `localStorage[TOK_ENC_KEY]` + `localStorage[TOK_LEGACY_KEY]`
  + `sessionStorage[TOK_KEY]`.

### 401/403-Handler im Workflow-Dispatch (seit 12.05.2026 mit Soft-Reset)

GitHub-API liefert auch bei gültigem Token gelegentlich 401/403 zurück
(rate-limit, IP-Wechsel, transient — am iPhone besonders häufig wegen
mobiler IPs). Frühere Logik rief sofort `_clearAllTokens()` → User
musste Token + Master-Passwort neu eingeben. Neue Logik:

| Counter-Stand | Aktion bei 401/403 |
|---:|---|
| 1, 2 | `_onTokenAuthFail` → **nur** Session+Memory löschen (Soft-Reset). Encrypted Blob bleibt. Nächste Action öffnet Unlock-Modal (nur Master-Passwort, kein Token-Reentry). |
| 3 (`TOKEN_AUTH_FAIL_HARD_THRESHOLD`) | `_clearAllTokens()` (Hard-Reset). Token ist tatsächlich revoked, nicht transient. User landet im Setup-Modal. |

`_resetTokenAuthFailCount()` wird auf **jeden** erfolgreichen Dispatch
(HTTP 204) aufgerufen — der Counter wird nicht durch eine alte 401/403-
Folge belastet. Counter lebt im `_inMemoryToken`-Scope (Tab-scoped) —
bei Tab-Schließen resettet die Sequenz, bewusst akzeptiert (neuer Tab
= neuer Versuch).

### Keep-Alive-Touch (F5, seit 12.05.2026)

`getToken()` schreibt bei jedem erfolgreichen Token-Read einen
`_tok_keepalive`-Timestamp in `localStorage`. Spekulatives Anti-ITP-
Workaround: Apples 7-Tage-Inaktivitäts-Cleanup soll laut Doku durch
jeden Storage-Write zurückgesetzt werden. Defensiv try/catch — bei
iOS-Storage-Errors lautlos schlucken. Write läuft nur wenn `tok`
nicht leer ist (sonst würde der Counter ohne User-Action resetten).

### iCloud-Schlüsselbund-Integration (F2, seit 12.05.2026)

Token-Modale (Setup / Unlock / Migrate) sind in `<form
onsubmit="return false">`-Wrapper gepackt. Safari + iCloud-Schlüsselbund
erkennen Credential-Felder nur in `<form>`. Submit-Buttons sind
`type="submit"`, Cancel/Skip sind `type="button"`. Jeder Form enthält
einen hidden `<input autocomplete="username" value="squeeze-report-master">`
— Safari verlangt eine Account-Identität, sonst keine Speicher-Bubble.
Master-Passwort-Felder haben `autocomplete="current-password"` (Unlock)
bzw. `autocomplete="new-password"` (Setup, Migrate). Beim nächsten
Unlock-Modal bietet iOS Safari den im Schlüsselbund gespeicherten Wert
automatisch zum Ausfüllen an.

### Pflege

- Bei Änderung der Krypto-Parameter (`_TOK_PBKDF2_ITER` / `_TOK_KEY_BITS` /
  `_TOK_SALT_LEN` / `_TOK_IV_LEN`): Schema-Version `v` in `_encryptToken`
  hochzählen + Migrationspfad in `_decryptToken` ergänzen, sonst werden
  alte Blobs unentschlüsselbar.
- `getToken()` ist der **einzige** Lese-Pfad. Bei Refactor weitere
  `localStorage.getItem(TOK_KEY)`-Aufrufe vermeiden — das Linter-Pattern
  `grep -n 'localStorage.getItem(TOK_KEY)' generate_report.py` sollte
  außerhalb der `_getLegacyPlaintextToken`-Helper leer bleiben.
- Score-Methodik-Sync ist **nicht betroffen** — reines Frontend-Security-
  Feature, keine Score- oder Filter-Logik berührt.

### Gist-Action-Token-Routing (PR-Folge zu #149)

Vier User-Aktionen, die über den privaten Gist persistieren, sind als
„Action-Pfade" durch ``_ensureToken`` gewrappt — bei leerer Session +
Encrypted-Blob öffnet sich das Unlock-Modal, nach Master-Passwort-
Submit läuft der Callback weiter. Vorher liefen sie mit passivem
``getToken()``-Check ins Leere (Toast ohne Modal-Routing oder komplett
silent skip).

| Funktion | User-Action | Vorher (silent/irreführend) | Jetzt |
|---|---|---|---|
| ``wlSubmitPosition`` | Position eröffnen | Toast „Token-Scope prüfen" obwohl Session-Verlust | Unlock-Modal |
| ``wlSubmitClose`` | Position schließen + Trade-Journal | Toast „Token-Scope prüfen" | Unlock-Modal |
| ``wlAddManual`` | Watchlist-Ticker hinzufügen | Silent skip im Gist-Sync, lokal sichtbar aber kein Cross-Device-Sync | Unlock-Modal |
| ``wlRemoveFromExpanded`` | Drawer-Footer „Aus Watchlist entfernen" | Repo-Datei wird gelöscht, **Position bleibt im Gist** (Geister-Position für ``process_exit_signals``) | Unlock-Modal — beide Pfade konsistent |

**Display-Pfad** für Trade-Journal: ``renderTradeJournal`` bekommt
analog ``buildPositionPanel`` (PR #149) drei Token-Zustände — bei
Session-Verlust + Blob da rendert eine Locked-Box mit „Token entsperren"-
Button (Helper ``_unlockFromTradeJournal``). Ohne diesen Fix sah der
User eine leere Statistik und schloss fälschlich „keine Trades"
statt „Daten verschlüsselt".

**``gistLoad``/``gistSave`` selbst bleiben unverändert** —
defensive catch-net (innerer ``if (!token) return null``-Skip), aber
nicht mehr der primäre Pfad für Action-getriebenes UI-Feedback.

**Generische CSS-Klasse** ``.gist-locked-box`` in ``head.jinja`` —
selbe visuelle Sprache wie ``.position-panel-locked``, eigenes
Padding/Margin für ``info-box``-Slot des Trade-Journal-Sections.
Zukünftige Display-Pfade mit Gist-Abhängigkeit können dieselbe Klasse
nutzen.

**DOMContentLoaded-Preload** (``gistLoad().catch(...)``) bleibt
silent — passiv, kein User-Action, kein Modal-Spawn beim Page-Load.

---

## RVOL-Normalisierung (Phase 1 — Helper + Feature-Flag, OFF by default)

Behebt die premarket→postclose-Score-Drift, die in der Score-Inflation-
Empirik 16.05.2026 dokumentiert wurde:

- Mean Drift: +3.87 Pkt
- Median: +1.42 Pkt
- Spitzen: +40.2 Pkt (DMRC 13.05.2026, RVOL 0.4 → 2.4)
- Ursache zu >95 %: 20d-RVOL ist im premarket-Run strukturell unter-
  skaliert (today_vol kumuliert intraday, 20d-Nenner fix).

### 3-PR-Plan

| PR | Scope | Status |
|---|---|---|
| **PR-α** (#166) | Helper `_normalize_rvol` + Konstanten + Feature-Flag, **`RVOL_NORMALIZATION_ENABLED = False`**. Kein Verhaltens-Drift im Default. | aktiv |
| **PR-β** (diese PR) | `score_inflation_log.jsonl` Schema v2: zusätzliches Feld `drivers_raw.rel_volume_normalized` mit hypothetischem Wert (`force_enabled=True`). 14 Tage parallele Datensammlung. | aktiv |
| PR-γ | Aktivierung (`ENABLED = True`) nach Daten-Validierung + ggf. Re-Kalibrierung von `PREMARKET_RVOL_SCALER` (heute 0.10 als Daumenwert). | offen |

### score_inflation_log Schema-Version-Geschichte

| Version | Marker | Zeitraum | Felder zusätzlich zu Vorgänger |
|---|---|---|---|
| **v1** | `schema_v` **fehlt** | 12.05.–16.05.2026 | Original-Format (run_ts, run_phase, ticker, sub_scores, drivers_raw, trading_session_phase) |
| **v2** | `schema_v: 2` | ab 16.05.2026 | `drivers_raw.rel_volume_normalized` (float \| None) |

**Reader-Vertrag:** Diagnose-Tools / Auswertungs-Skripte lesen
`entry.get("schema_v", 1)` — Bestands-Einträge ohne Marker werden
implizit als v1 erkannt. Bei `v >= 2` ist `drivers_raw.rel_volume_normalized`
verfügbar, bei v1 nicht (kein Crash, defensiv via `.get()`).

**Auswertungs-Hinweis (PR-γ-Vorbereitung):** Für die Skalierer-
Re-Kalibrierung pro Ticker den Quotienten
`rel_volume_normalized / rel_volume` über 14 d sammeln — das ist
der effektive Phase-Multiplikator. Bei `run_phase=postclose` ist der
Quotient ≈ 1.0 (kein Effekt). Bei `run_phase=premarket` zeigt er
die Skalierungs-Wirkung; Median-pro-Ticker als ground truth statt
des Daumenwerts 0.10.

### Helper-Signatur-Erweiterung (`force_enabled`)

```python
_normalize_rvol(raw_vol, avg_20d, *, run_phase=None, now_utc=None, force_enabled=False)
```

`force_enabled=True` aktiviert die Normalisierungs-Logik unabhängig
vom globalen `RVOL_NORMALIZATION_ENABLED`-Flag. **Genutzt
ausschließlich vom score_inflation_log-Writer** (Callable-Injection
via `record_top10_inflation(..., normalize_rvol_fn=_normalize_rvol)`).
Andere Konsumenten (3 Call-Sites in `_hist_stats` / `get_yfinance_data`)
lassen den Default `False` — Verhalten unverändert solange
`RVOL_NORMALIZATION_ENABLED=False`.

### Helper-Vertrag (`generate_report.py:_normalize_rvol`)

```python
_normalize_rvol(raw_vol, avg_20d, *, run_phase=None, now_utc=None) -> float
```

| ENABLED | Pfad | Resultat |
|---|---|---|
| `False` (Default) | jeder | `raw_vol / avg_20d` (Status quo) |
| `True`, `run_phase == "postclose"` | Workflow-Override | `raw_vol / avg_20d` (EOD-Wahrheit) |
| `True`, UTC < 13:30 | premarket | `raw_vol / (avg_20d × PREMARKET_RVOL_SCALER)` |
| `True`, 13:30 ≤ UTC < 20:00 | intraday | `raw_vol / (avg_20d × max(hours_elapsed / 6.5, INTRADAY_RVOL_MIN_FRAC))` |
| `True`, UTC ≥ 20:00 | postclose-Wallclock | `raw_vol / avg_20d` |

Edge-Cases: `raw_vol` None/≤0 → 0.0 · `avg_20d` None/≤0 → 0.0 ·
`now_utc` None → `datetime.now(timezone.utc)`.

### Konstanten (config.py)

| Konstante | Default | Zweck |
|---|---|---|
| `RVOL_NORMALIZATION_ENABLED` | `False` | Master-Switch. Default OFF — Aktivierung nur via PR-γ. |
| `PREMARKET_RVOL_SCALER` | `0.10` | Premarket-Volumen typisch ~10 % des Tagesvolumens. Daumenwert. |
| `INTRADAY_RVOL_MIN_FRAC` | `0.10` | Floor gegen Division-Explosion in ersten Minuten nach US-Open. |

### Call-Sites (3 Stellen in `generate_report.py`)

1. `get_yfinance_data` (Singleton-Fallback-Pfad)
2. `_hist_stats` (Batch-Hauptpfad)
3. `_hist_stats` (Singleton-Fallback innerhalb _hist_stats)

Alle drei nutzen `_normalize_rvol(cur_vol, avg_vol_20)` ohne explizite
`run_phase`/`now_utc`-Argumente — der Helper hat sichere Defaults
(`datetime.now(timezone.utc)`) für den ENABLED=True-Pfad.

### Außerhalb des Scope von PR-α

- **ki_agent.py** ist von der Normalisierung **nicht betroffen**.
  `rvol_4d` bleibt der Anomaly-Trigger-Basis-Wert (Disambiguation aus
  PR #165). `rvol_20d` wird in `agent_signals.json` weiterhin
  **unnormalisiert** geloggt — das ist der Rohwert, der in PR-β als
  Empirik-Datenbasis dient.
- **Earliness-V2 Late-Runner-Pfad** liest weiterhin unnormalisiertes
  `rel_volume` aus dem Stock-Dict. Bei Aktivierung in PR-γ muss der
  Pfad explizit auf `rel_volume_raw` umgestellt werden (siehe
  Diagnose-Bericht Schritt 2 F-3).
- **Backtest-History** behält den heutigen Schreib-Pfad (`rvol`-Feld =
  unnormalisiert via `_normalize_rvol(..., ENABLED=False)`).
  Bei PR-γ-Aktivierung wäre eine retroaktive Normalisierung **nicht**
  möglich — Backtest-Auswertungen bleiben pre-cutover-kompatibel.

### Pflege

- **`PREMARKET_RVOL_SCALER`-Re-Kalibrierung** in PR-γ: aus
  `rvol_20d`-Verteilung in `agent_signals.json` über 14 d ableiten;
  Median-Faktor zwischen frühen (10:17 UTC) und späten (21:17 UTC)
  Ticks pro Ticker als ground truth.
- **Markt-Phase-Grenzen** (`_US_OPEN_MIN_UTC = 810`,
  `_US_CLOSE_MIN_UTC = 1200`) sind hartkodiert im Helper als „Single
  Source of Truth" — analog zu `US_SESSION_START/END` im
  `resolve_run_phase`-Skript (CLAUDE.md → Zwei-Run-Architektur). Bei
  Änderung beide synchron halten.
- **Helper-Signatur** ist `*-keyword-only` für `run_phase`/`now_utc`
  — zukünftige Erweiterung (z. B. `ticker`-spezifischer Skalierer)
  kann via Keyword angehängt werden ohne Call-Site-Drift.

---

## RVOL-Definitionen (zwei parallele Formeln, bewusst)

Es existieren zwei RVOL-Berechnungen im Codebase, die unterschiedliche
Fragen beantworten. Eine Vereinheitlichung würde Information vernichten
(Empirik 16.05.2026: 20d/4d-Faktor schwankt zwischen 0.29 und 1.56 je
nach Ticker-Profil — kein linearer Zusammenhang).

| Größe | Ort | Formel | Frage |
|---|---|---|---|
| **`rvol_4d`** (ki_agent) | `ki_agent.py:fetch_yfinance` | `today_vol / mean(letzte 4 Vortage)` | „Hat sich Volumen in den letzten Tagen plötzlich verändert?" — kurzfristiger Trend-Bruch |
| **`rel_volume`** (generate_report, = 20d-Basis) | `generate_report.py:_hist_stats` | `today_vol / mean(letzte 20 Vortage)` | „Ist Volumen heute über üblicher Langzeit-Baseline?" — absolute Anomalie |

### Konsumenten

| Pfad | Liest | Warum |
|---|---|---|
| KI-Agent Score-Komponenten (`TRIGGER_RVOL_2X/4X`, `RVOL_HIGH/EXTREME_THRESHOLD`, `RVOL_VELOCITY_*`, `COMBO_RVOL_MIN`) | `rvol_4d` | Schwellen sind seit Monaten auf 4d-Basis kalibriert; Push-Volumen-stabil |
| KI-Agent Anomaly-Trigger (`ANOMALY_RVOL_TODAY/VS_YESTERDAY`, `ANOMALY_GAP_RVOL`) | `rvol_4d` | Erkennt kurzfristige Trend-Brüche |
| Daily-Run `score()` / `_compute_sub_scores()` Timing-Komponente | `rel_volume` (20d) | Setup-Score misst Baseline-Anomalie |
| Daily-Run `_earliness_pts_v2` Late-Runner-Penalty | `rel_volume` (20d) | „über 5× Langzeit-Schnitt" ist die belastbare Definition |
| Backtest-History `rvol` | `rel_volume` (20d) | Historisch konsistent mit Setup-Score |

### agent_signals.json-Schema (seit 16.05.2026)

```json
{
  "signals": {
    "TICKER": {
      "rvol_4d":  2.3,       // Trigger-Basis (war früher: "rvol")
      "rvol_20d": 1.8,       // additiv, für Empirik/Vergleich (kann None sein)
      ...
    }
  }
}
```

`rvol_4d` ersetzt den früheren Key `rvol`. Frontend-Reader (drei Stellen
in `generate_report.py`: Insights-Chip, Statuszeile, Drawer-RVOL-Zeile)
lesen bevorzugt `rvol_4d` mit Fallback auf `rvol` — backward-kompatibel
für genau einen ki_agent-Tick nach dem Cutover. `rvol_20d` ist
**rein logging**, kein Trigger-Pfad.

### Pflege

- Anomaly-Schwellen-Recalibration bei 4d→20d-Wechsel würde **systematisch
  pro-Ticker driften** (Empirik n=10: Min 0.29×, Max 1.56×) — ein
  pauschaler Multiplikator ist nicht möglich. Falls künftig
  Vereinheitlichung gewünscht: 14 d empirische Datensammlung über
  `rvol_20d`-Logging, dann ticker-spezifische Recalibration.
- Score-Inflation-Empirik (PR-α/β/γ-Pipeline, 16.05.2026) adressiert
  ausschließlich **20d-RVOL-Drift im premarket-Run** — nicht 4d-RVOL
  in ki_agent.
- Bei Schema-Erweiterung am `signal`-Dict in `_process_ticker`-Output:
  CLAUDE.md-Schema-Block oben synchron halten.

---

## Anomalie-Push-System

Der KI-Agent feuert ntfy-Pushes **nicht mehr per Monster≥70-Schwelle**,
sondern bei einer von sechs **Anomalien**. Begründung: User checkt die
Top-10 ohnehin manuell — Push ist für Ereignisse, die sonst übersehen
würden. Jeder Trigger-Typ hat einen eigenen Cooldown via Key-Prefix
``anomaly_<trigger>_<ticker>`` in `agent_state.json`.

| Trigger | Bedingung (alle Konstanten in `config.py`) | Severity |
|---|---|---|
| `rvol_explosion`  | RVOL ≥ `ANOMALY_RVOL_TODAY` (5.0) **und** RVOL ≥ `ANOMALY_RVOL_VS_YESTERDAY` × Vortag (2.0×) | medium |
| `uoa_extreme`     | Call-Vol/OI ATM ≥ `ANOMALY_UOA_VOL_OI` (10.0) | medium |
| `score_jump`      | Setup heute − gestern (raw aus `score_history`) ≥ `ANOMALY_SCORE_JUMP` (15) | medium |
| `gap_combo`       | gap_pct ≥ `ANOMALY_GAP_PCT` (5 %) **und** state==`strong_hold` **und** RVOL ≥ `ANOMALY_GAP_RVOL` (3.0) | medium |
| `perfect_storm`   | active_triggers ≥ `ANOMALY_PERFECT_STORM_TRIGGERS` (4/4) | high |
| `monster_backup`  | monster_score ≥ `ANOMALY_MONSTER_BACKUP` (90) — Sicherheitsnetz für extreme Fälle | high |
| `conviction_high` | `conviction_score ≥ ANOMALY_CONVICTION_HIGH_THRESHOLD` (75) **und** prev-Tick < Schwelle (Threshold-Crossing — Sustained-High feuert NICHT). prev wird in `agent_state["prev_conviction_scores"]` persistiert | high |
| `edgar_filing`    | SC 13D (immer) oder SC 13G (nur `EDGAR_ACTIVIST_FILERS`) in den letzten `EDGAR_LOOKBACK_HOURS` (6 h) | medium |

**Severity-Tiering (Stand 10.05.2026):**

| Severity | Bedeutung | Trigger |
|---|---|---|
| **high** | **Aktions-Signal** — direkter Hinweis, jetzt einsteigen oder hingucken. ntfy-Priority maximal, prominenter Ton. | `conviction_high`, `perfect_storm`, `monster_backup` |
| **medium** | **Beobachtungs-Signal** — etwas bewegt sich, aber noch keine klare Aktions-Empfehlung. ntfy-Priority normal, dezentere Anzeige. | `rvol_explosion`, `uoa_extreme`, `score_jump`, `gap_combo`, `edgar_filing` |

Die Severity wird vom `_send_anomaly_ntfy`-Sender unverändert
durchgereicht (kein Mapping auf ntfy-Priority-Levels im Code derzeit);
sie landet im `push_history`-Eintrag (`kind="anomaly"`, `severity=…`)
und kann von Frontend / Daily-Summary später für Sortierung oder
Filterung genutzt werden.

Cooldown: `ANOMALY_COOLDOWN_HOURS = 6` pro **(Ticker × Trigger-Typ)**.
Mehrere Anomalien gleichen Tickers in einem Run sind möglich.
Earnings-Sofort-Alert hat Vorrang vor Anomalien (kein Doppel-Push).

### Conviction-Gating

Anomaly-Pushes (alle außer `conviction_high` selbst) werden nur an
ntfy gesendet, wenn der Ticker mindestens
`ANOMALY_CONVICTION_MIN_THRESHOLD` (seit 12.05.2026: **75**, vorher 50)
Conviction hat. Damit gehen nur noch „Aktions-Substrate" raus — der
User bekommt keine Pushes mehr für strukturell hohe Monster/Setup-
Scores ohne Earliness/Regime-Rückendeckung. `conviction_high` (≥ 75)
selbst ist ungefiltert (Aktions-Push).

**Coverage (12.05.2026):** Gating greift auf **ALLE** Anomaly-Trigger
inklusive `monster_backup` — einzige Ausnahme ist `conviction_high`,
das selbst der Aktions-Push ist. monster_backup war früher als
„Sicherheitsnetz für extreme Fälle" ungated gedacht, ist aber in der
Praxis die lauteste Klasse (51 % aller Pushes laut Bestandsaufnahme
12.05., dominiert von NVAX/GRPN). Bewusste Architektur-Entscheidung:
bei Conviction < 75 ist ein Setup per Definition kein „extremer Fall",
auch wenn der Monster-Score hoch ist.

**Beziehung zur `ANOMALY_CONVICTION_HIGH_THRESHOLD`-Konstante** (auch
75): Beide bleiben semantisch getrennt:

- `HIGH_THRESHOLD = 75` triggert den `conviction_high`-Aktions-Push
  selbst beim Threshold-Crossing (Setup von < 75 auf ≥ 75).
- `MIN_THRESHOLD = 75` ist das Gating für **alle anderen** Anomaly-
  Trigger (monster_backup, score_jump, rvol_explosion, …).

Bei künftigen Re-Kalibrierungen können beide unabhängig angepasst
werden. Numerisch deckungsgleich aktuell, aber konzeptionell zwei
unterschiedliche Schwellen — kein Konstanten-Merge.

Gating-Reihenfolge im Consumer-Loop:
`vix_pause → cooldown → silence_filter → conviction_gate → push`.

`push_history` wird **immer** geschrieben, auch bei unterdrücktem
Push — mit `suppressed=True` und
`suppress_reason="conviction_below_threshold"`. UI zeigt unterdrückte
Einträge dezent (Strike-Through-Body, ⊘-Marker, gestrichelter Rand).
Ticker ohne Conviction-Score (z. B. nicht in heutigen
`conviction_scores`) pushen konservativ ungefiltert — kein
Filter-Effekt durch fehlende Daten.

### Earnings-Sofort-Alert Per-Event-Dedup (seit 12.05.2026)

Cooldown-Key trägt das **Earnings-Datum**, nicht nur den Ticker:
``earnings_immediate_{ticker}_{DD.MM.YYYY}`` in
``agent_state.json["cooldowns"]``. Cooldown-Dauer
`EARNINGS_IMMEDIATE_COOLDOWN_HOURS` (Default 24h). Vorher nutzte der
Pfad den generischen `is_on_cooldown(ticker)` mit
`ALERT_COOLDOWN_HOURS=2` → derselbe Earnings-Event konnte alle 2h neu
feuern (Bug-Symptom: DMRC 3× Push innerhalb 6h für dasselbe Event am
11./12.05.2026).

Per-Event-Cooldown wird gesetzt sobald der ntfy-Push erfolgreich
abging — nicht erst nach erfolgreichem E-Mail-Versand. Der alte
per-ticker `set_cooldown(ticker)` (für die SMTP-Pipeline) bleibt
zusätzlich aktiv, ist aber nicht mehr die kanonische Dedup-Quelle.
Bei fehlendem ``earnings_date_str`` (Edge-Case: yfinance liefert
das Datum nicht) wird der Push komplett übersprungen — defensiv, weil
ohne Datum kein Dedup-Key bildbar ist.

### push_history-Schema-Erweiterung `conviction_score` (seit 12.05.2026)

Neues optionales Feld in jedem `push_history`-Eintrag. Anomaly- und
Earnings-Pushes schreiben den Conviction-Score zum Push-Zeitpunkt mit
hinein; Exit-Pushes (exit_p1/exit_p2) lassen das Feld auf `None`
(Conviction misst Setup-Substrat, nicht Exit-Druck). Backward-
kompatibel: alte Einträge ohne das Feld bleiben lesbar, Reader sehen
`None`. Single-Source-of-Truth: `push_history.py:_record_push` —
Schema-Änderungen nur dort.

### VIX-Gating

Bei hohem VIX (Krise/Panik) sind Squeeze-Setups oft Bull-Traps —
Pushes werden gating-abhängig **pausiert** oder **gewarnt**:

| VIX-Bereich | Verhalten |
|---|---|
| `> ANOMALY_VIX_PAUSE_THRESHOLD` (35.0) | **alle** Anomalie-Pushes geskippt, Log-Zeile „Anomaly-Pushes pausiert" |
| `> ANOMALY_VIX_WARN_THRESHOLD` (25.0) und ≤ 35 | Pushes laufen, Message-Präfix `⚠️ VIX X.X \|` |
| ≤ 25.0 oder `None` | unverändert |

VIX wird einmal pro KI-Agent-Run via `_fetch_vix_current()` (yfinance
`^VIX`) geholt und in der Modul-Variable `_VIX_CURRENT` zwischengelegt.
`save_signals()` persistiert den Wert als `vix_current` in
`app_data.json` — nur wenn der Fetch erfolgreich war (None würde
sonst den vorigen Wert via `**existing` nicht überschreiben).

**Earnings-Sofort-Alerts werden nicht gegated** — Time-Critical-Pfad,
muss in jeder Marktphase durchkommen.

### SEC EDGAR 13D/13G-Trigger (`edgar_filing`)

Hybrid-Filter über die letzten `EDGAR_LOOKBACK_HOURS` (6 h):

| Filing-Typ | Push-Logik |
|---|---|
| `SC 13D` / `SC 13D/A` | **immer** pushen (aktive Stake-Erklärung — squeeze-relevant unabhängig vom Filer) |
| `SC 13G` / `SC 13G/A` | nur wenn Filer-Name (case-insensitive Substring) eines der `EDGAR_ACTIVIST_FILERS` enthält |

- **Datenquelle:** `EDGAR_RSS_URL` (Atom-Feed, `?action=getcurrent&type=SC+13`).
  Keine Auth nötig, aber SEC verlangt `User-Agent` mit Kontakt-E-Mail.
- **`EDGAR_USER_AGENT` ist GitHub-Secret** (analog zu `POSITIONS_JSON`,
  `NTFY_TOPIC`) — niemals als Klartext im Repo. Konfiguration:
  Repo Settings → Secrets and variables → Actions → New repository
  secret → `EDGAR_USER_AGENT`, Format: `"Name email@domain"`. Beide
  Workflows (`daily-squeeze-report.yml`, `ki_agent.yml`) injizieren das
  Secret als Env-Variable in den Python-Run. `fetch_edgar_filings()`
  liest zur Laufzeit via `os.environ.get("EDGAR_USER_AGENT", default)`.
  Default-Fallback (`Squeeze Report contact@example.com`) funktioniert
  für Tests/Forks, **SEC blockt aber bei produktiven Aufrufen ohne
  korrekten Kontakt-Header**.
- **Cooldown:** `EDGAR_COOLDOWN_HOURS = 24` pro **(Ticker × Filing-Typ)**.
  13D und 13G für denselben Ticker können beide pushen (verschiedene
  Cooldown-Keys), Amendments innerhalb 24 h für denselben Typ
  unterdrückt.
- **Aktivist-Liste pflegen:** `EDGAR_ACTIVIST_FILERS` in `config.py` ist
  Liste mit Substring-Mustern. Erweitern bei neuem Smart-Money-Filer
  (z. B. ein bisher unbekannter Hedge-Fund mit aggressivem Track Record).
- **Fail-soft:** SEC down / 403 / Parse-Fehler / fehlende
  Ticker-Mapping → `fetch_edgar_filings` returnt leere Liste, kein
  EDGAR-Push, andere Anomalie-Trigger laufen unverändert weiter.

Implementierung in `ki_agent.py`:
- `fetch_edgar_filings(top10) → list[dict]` — pure-Funktion, niemals raise.
- `detect_anomalies(...)` akzeptiert `edgar_filings`-Kwarg; pro-Ticker-Anomaly
  setzt `cooldown_key` und `cooldown_hours` selbst (überschreibt
  `ANOMALY_COOLDOWN_HOURS`).

### Datenpfad

- **`uoa_atm_ratio`** und `uoa_cp_ratio` werden in `fetch_uoa_signal()`
  zusätzlich zum Score berechnet und in `agent_signals.signals[ticker]`
  persistiert. `detect_anomalies()` liest direkt — keine String-Parses.
- **`gap_states`** in `app_data.json` (`{ticker: {pct, state}}`) wird vom
  Daily-Report via `_gap_hold_pts()` für jeden Top-10-Ticker geschrieben.
  `save_signals()` (Read-Modify-Write, `**existing`-Spread) preserviert
  das Feld zwischen ki_agent-Ticks.
- **Score-Sprung**: vergleicht `setup_today` (smoothed, aus `setup_scores`)
  gegen den vorletzten Eintrag in `score_history` (raw). Asymmetrisch
  bewusst — der heutige geglättete Wert ist genau das, was die Kachel
  zeigt; gestrige Vergleichsbasis ist der raw Vortags-Run-Score.

### Deprecated

- `ALERT_THRESHOLD_STRONG = 70` ist **kein** Push-Trigger mehr. Konstante
  bleibt für E-Mail-Subject-Logik (`⚡⚡` vs `⚡`-Prefix) erhalten.
- Frühere „Monster ≥ 70 → Push"-Logik in `ki_agent.main()` ist entfernt.

---

## Chat-Verhalten

Der Frontend-Chat (Claude Haiku via `chat_script.jinja`) soll **synthetisieren,
nicht aufzählen** — sonst hat er keinen Mehrwert gegenüber dem sichtbaren
Top-10-Block.

### Antwort-Hierarchie (verbindlich, im System-Prompt verankert)

1. **ZUERST Anomalien** — was hat sich seit gestern geändert? Score-Sprünge,
   neue Top-10-Einsteiger, weggefallene Mitglieder, RVOL-Spitzen, Earnings-
   Nähe. Quelle im Chat-Kontext: `anomalies_today` + `topten_changes`.
2. **DANACH Position-Kontext** (wenn Frage relevant) — PnL, Setup-Verlauf
   der gehaltenen Position, Top-10-Cross-Match. Quelle: `positions`.
3. **Score-Ranking ist Kontext, nicht Antwort.** Wiederhole keine Frontend-
   Tabellen.

### Kritisch-sein ist explizit erlaubt

- Widerspruch zum Top-10-Ranking ist erwünscht, wenn Daten dagegen sprechen
  (fallender Setup-Trend trotz hohem Live-Score, teures IV ohne Katalysator,
  Bull-Trap-Muster, etc.).
- Schwächen offen benennen.
- Wenn keine Position klar überzeugt: das auch sagen — keine Pseudo-
  Empfehlungen.

### Datenquellen im Chat-Kontext

Aufgebaut von `_build_chat_synthesis_ctx(stocks, score_history,
watchlist_cards=None)` in `generate_report.py`, serialisiert als JSON
in `STOCKS_CTX` an den Chat:

| Feld | Inhalt |
|---|---|
| `today_top10[]`     | pro Ticker `setup_today`, `setup_yesterday`, `setup_delta`, `monster_today`, `ki_today`, RVOL, RSI, Earnings-Tage, Sektor, SI-Trend |
| `anomalies_today[]` | `{ticker, trigger, detail}` — `score_jump`, `rvol_high`, `earnings_imminent`, `topten_entry`, `topten_exit` |
| `topten_changes`    | `{new: [...], dropped: [...]}` vs. Vortag |
| `positions[]`       | `entry_date`, `entry_price`, `current_price`, `pnl_pct`, `in_top10`, `in_watchlist_card`, `setup_today`, `monster_today` |
| `today_date` / `yesterday_date` | DE-Datums-Strings, auf die die Diffs sich beziehen |

### Quellen-Priorität für Positions-Felder (current_price / setup_today / monster_today)

Reihenfolge in `_build_chat_synthesis_ctx`:

1. **`stocks` (heutige Top-10)** — wenn der Position-Ticker hier ist:
   `s = by_ticker.get(ticker)`, `in_top10=True`.
2. **`watchlist_cards` (enriched Watchlist-Snapshot)** — Fallback, wenn
   der Ticker nicht in Top-10 ist: `wl = watchlist_cards.get(ticker)`.
   `in_top10=False`, `in_watchlist_card=True`. Dasselbe Dict, das auch
   `app_data.json["watchlist_cards"]` füllt und das Frontend für das
   Position-Panel liest — Single-Source-Konsistenz zwischen Chat-Ctx
   und Position-Panel.
3. **Keine Quelle** — beide Flags `False`, `current_price=None`,
   `setup_today=None`, `monster_today=None`. Das ist die echte
   „ohne aktuellen Kurs"-Lage.

**`in_top10` bleibt strikt** = Membership in heutiger Top-10 — KEIN
Watchlist-Smearing. Sonst verliert die LLM das Signal „aus Top-10
gefallen". `in_watchlist_card` flaggt den Fallback-Pfad explizit, damit
die LLM zwischen „Spot da via Watchlist" und „Spot komplett fehlt"
unterscheiden kann. System-Prompt in `chat_script.jinja:_buildSystem`
instruiert die LLM entsprechend.

**Aufrufer-Pipeline:** `main()` baut `_wl_card_data` VOR `generate_html`
(hochgezogen aus dem ursprünglichen post-Render-Slot, weil der Chat-
Ctx in `_build_context` darauf zugreifen muss). Dasselbe Dict wird
parallel an `_write_app_data_json` weitergereicht — kein doppelter
Build, keine Datenquellen-Drift. `_build_chat_synthesis_ctx`
behält den optionalen `watchlist_cards=None`-Default für
Backward-Compat-Aufrufer (`apply_conviction_scores`-Pfad nutzt nur
`anomalies_today` und braucht den Fallback nicht).

### Hinweise

- KI-Agent-Anomalien (UOA-Vol/OI-Extreme, RVOL-vs-Vortag-Sprung,
  Gap+Hold-Combo) liegen erst im stündlichen ki_agent-Tick auf —
  `anomalies_today` im Chat-Kontext deckt nur die Daily-Run-zugänglichen
  Trigger ab. Für Echtzeit-Info dient der ntfy-Push.
- Chips am Chat-Boden referenzieren jetzt Anomalie-Mover und Position
  statt Top-1-Score-Ticker — siehe `_renderChips()` in `chat_script.jinja`.

### USD/EUR-Anzeige

Alle Kursangaben in Chat **und** KI-Analyse erscheinen zweisprachig im
Format `$4.47 (4,11 €)` (US-Format zuerst, EUR in Klammern mit deutschem
Komma).

- **Quelle:** `app_data.json.fx_usd_eur` (= EUR pro 1 USD, Multiplikator).
- **Fetch:** im Daily-Run via yfinance `EURUSD=X` → invertiert zu
  USD→EUR. Fail-soft: bei Fetch-Fehler wird der vorige Wert aus
  `app_data.json` weiterverwendet, sonst Notnagel `0.92`.
- **Modul-Variable:** `_FX_USD_EUR` in `generate_report.py` (gesetzt in
  `main()` direkt nach SPX-Fetch). `_build_chat_synthesis_ctx()` und
  `_write_app_data_json()` lesen sie ohne Signatur-Plumbing.
- **Frontend-Bridge:** `chat_script.jinja` spiegelt den Wert auf
  `window._FX_USD_EUR`, damit `runKiAnalyse()` (außerhalb der Chat-IIFE)
  zugreifen kann. Der KI-Analyse-System-Prompt enthält den konkreten
  Multiplikator als String und das EUR-Format-Schema.
- **Persistenz nach ki_agent-Tick:** `save_signals()` Read-Modify-Write
  preserviert `fx_usd_eur` im `**existing`-Spread.

---

## Backtest-Schema (Stufe 1 — A2-Validierung)

Drei neue Felder pro `backtest_history.json`-Eintrag, persistiert ab
01.05.2026 für eine **spätere** Auswertung (Bahn A2 ab Juli 2026,
≥ 200 Live-Einträge). Aktuell nur Daten-Persistierung — keine
Frontend-Anzeige, keine Score-Konsequenzen.

| Feld | Typ | Bedeutung | Initialwert |
|---|---|---|---|
| `max_drawdown_pct` | Float (negativ) | Max. Drawdown vom rolling Cummax-High zur Tagestief über die ersten ≤ 10 Handelstage seit Entry | `0.0` (kein Drawdown) |
| `market_regime` | Str | SPY 50-Trading-Day-Trend zum Entry-Tag: `bull` (>+5 %), `bear` (<−5 %), `neutral` | aus `_market_regime_from_spy()` |
| `vix_level` | Float \| None | VIX-Schluss zum Entry-Tag (yfinance `^VIX`) | `_vix_close()`, None bei Fehler |

### Persistenz-Logik

- **Neue Einträge** (heute): `market_regime` + `vix_level` als Snapshot
  zum Entry-Zeitpunkt fest persistiert (immutable). `max_drawdown_pct`
  startet bei `0.0`.
- **Rolling Update** (< 14 Kalendertage alt, ≈ 10 Handelstage): pro
  Daily-Run wird `max_drawdown_pct` über `_compute_max_drawdown()` neu
  berechnet via Batch-yfinance-Download aller aktiven Ticker.
  Idempotent — Ergebnis ist immer der bisher schlechteste Drawdown im
  Fenster. Nach 14 Tagen ist der Wert finalisiert (kein Update mehr).
- **Legacy-Einträge** ohne `max_drawdown_pct`-Feld bleiben unangetastet
  (Backwards-Compat); nur neue Einträge ab Deploy bekommen das Feld.

### Helper

- `_market_regime_from_spy(spy_hist)` — pure, fail-soft → "neutral"
- `_vix_close()` — None bei Fetch-Fehler
- `_compute_max_drawdown(df_window)` — pure, akzeptiert max-10-Tage-Slice

Alle drei Helper landen oben in `_append_backtest_entries`-Region in
`generate_report.py`. SPY wird einmal pro Run gefetcht und an
`_market_regime_from_spy` durchgereicht.

---

## Backtest-Schema (Stufe 4 — Earliness-Trend-Logging, prospektiv)

Vier neue Felder + Schema-Version-Marker pro neuem
`backtest_history.json`-Eintrag, persistiert ab dieser PR. **Reines
Logging** — kein Conviction-Effekt, kein Score-Effekt, kein Frontend-
Render. Zweck: nach 14–30 Tagen Live-Daten ein AUC-Vergleich gegen
`return_10d` für die drei Sub-Signale, die aus der heutigen Diagnose
13.05.2026 nicht rückwirkbar berechenbar waren (SI-Trend 5d-Slope,
RVOL-Build-up 5d, Vol-Stability/Coiled Spring).

### Schema-Version-Marker

`backtest_schema_version` ist die **kumulative Major-Version** des
Schemas:

| Version | Erweiterung | Wirksam ab |
|---:|---|---|
| 1 | Original (date, ticker, score, return_*d, …) | initial |
| 2 | Bahn B (score_struct/catalyst/timing, score_raw, combo_bonus, …) | ~PR #80 |
| 3 | Bahn A2 (max_drawdown_pct, market_regime, vix_level) | 01.05.2026 |
| **4** | **Earliness-Trend-Logging (4 Felder, prospektiv)** | **diese PR** |

Alte Einträge ohne den Marker bleiben unverändert (kein Backfill).
Reader sind null-tolerant via `e.get(...)`-Pattern — Schema-Version-
Check ist optional, nicht Pflicht für die bestehenden Konsumenten.

### Felder pro neuem Eintrag

| Feld | Typ | Bedeutung | None bei … |
|---|---|---|---|
| `si_trend_5d_slope` | Float \| None | `(si_neuestes − si_ältestes) / si_ältestes` über die ersten 5 Punkte in `finra_data.history` (sortiert neueste → älteste). Dimensionslos; > 0 = SI baut auf, < 0 = abnehmend. | < `EARLINESS_TREND_MIN_FINRA_POINTS` Punkten (= 5) oder `si_old ≤ 0` |
| `rvol_buildup_5d` | Float \| None | `mean(rvol_letzte_3T) / mean(rvol_erste_2T)` über das 5-Trading-Tage-Fenster. > 1 = Volumen baut auf, < 1 = abnehmend. | < 5 Tage `hist_5d` oder `avg_vol_20d ≤ 0` oder Division-by-zero |
| `vol_stability_5d` | Float \| None | ATR-Range / Mittelwert-Close über die letzten 5 Tage. Niedrig = stabile Range (Coiled-Spring-Substrat). | < 5 Tage `hist_5d` oder `avg_close ≤ 0` |
| `coiled_spring_score` | Float 0..100 \| None | Composite: `stability_inv × slope_norm × 100`. Niedrige Volatilität (cap `EARLINESS_TREND_VOL_STAB_CAP` = 0.10) **und** positiver SI-Slope (cap `EARLINESS_TREND_SI_SLOPE_CAP` = 0.20) ergeben hohe Werte. | Falls eine der beiden Eingaben None |

### Datenquelle `hist_5d`

`_hist_stats(ticker)` returnt jetzt am Tupel-Ende eine `hist_5d`-Liste
mit den letzten 5 Trading-Tagen als Dicts `{volume, high, low, close}`,
sortiert ältester → neuester. Bei < 5 Tagen → leere Liste. Der Caller
legt das auf das Stock-Dict als `s["hist_5d"]`; `_build_backtest_extension`
konsumiert daraus die Slope-/Buildup-/Stability-Berechnungen.

→ **Keine zusätzlichen yfinance-Calls.** Die Daten stammen aus dem
existierenden `hist_batch`-Download im Daily-Run.

### Pure-Function-Helpers

In `generate_report.py` direkt vor `_build_backtest_extension`:

| Helper | Signatur | Defensive |
|---|---|---|
| `_compute_si_slope_5d(finra_history)` | Liste → Float \| None | < 5 Punkte / `si_old ≤ 0` / fehlende Keys |
| `_compute_rvol_buildup_5d(volumes_5d, avg_vol_20d)` | Liste + Float → Float \| None | < 5 Volumes / avg_vol ≤ 0 / Division-by-zero |
| `_compute_vol_stability_5d(highs, lows, closes)` | Drei Listen → Float \| None | < 5 Werte / avg_close ≤ 0 / TypeError |
| `_compute_coiled_spring_score(vol_stability, si_slope)` | Float + Float → Float 0..100 \| None | Eingaben None / negativer Slope (→ 0 Beitrag) |

Alle Helper sind **pure** (kein State, kein I/O, keine Side-Effects)
und liefern bei jedem Edge-Case `None` zurück — keine Exceptions.

### Konstanten in `config.py`

```python
EARLINESS_TREND_LOG_WINDOW_DAYS    = 5     # 5-Trading-Tage-Fenster
EARLINESS_TREND_MIN_FINRA_POINTS   = 5     # Slope braucht ≥ 5 SI-Werte
EARLINESS_TREND_SI_SLOPE_CAP       = 0.20  # 20 % cap für coiled_spring-Norm
EARLINESS_TREND_VOL_STAB_CAP       = 0.10  # 10 % ATR/Close cap für coiled_spring-Norm
```

### Validierungs-Pfad (nach 14–30 Tagen Live-Daten)

1. `backtest_history.json` filtern auf Einträge mit
   `backtest_schema_version >= 4` UND `return_10d != null`.
2. Buckets: Gewinner (`return_10d ≥ +10 %`), Verlierer (`≤ −5 %`).
3. Mann-Whitney-U pro Sub-Signal: AUC zwischen Gewinner und Verlierer.
4. Falls AUC ≥ 0.70 für eines der vier Signale → Kandidat für
   Aufnahme in Earliness V3 (analog DTC in V2).

### Pflege

- Schwellen-Anpassung (`EARLINESS_TREND_*_CAP`) nur in `config.py`,
  Code-Logik liest rein über Konstanten.
- Bei Schema-Erweiterung: `backtest_schema_version` hochzählen, neuen
  Block in dieser Sektion ergänzen, `_test_extended_schema`-
  `expected_keys` synchron pflegen.
- Reader müssen weiterhin null-tolerant bleiben (`e.get("xyz")`-
  Pattern). Schema-Marker ist informativ, nicht enforcement.

---

## Drivers-Block & Synthese-Zeile (Detail-Ansicht)

Die alte einzeilige `.driver-row` (Risiko-Badge + freie ``short_situation``-
Prosa) ist ersetzt durch einen kategorisierten **Drivers-Block** mit
deterministischer **Synthese-Zeile** darüber. Quelle: rein die bereits
berechneten Score-Komponenten — keine LLM-Calls, kein zweiter Datenpfad.

### Helper-Trio (single source of truth)

- ``_drivers_breakdown(s) → {strengths: [...], risks: [...]}`` — liest
  dieselben Felder wie ``_compute_sub_scores()`` / ``score()``, klassi-
  fiziert jedes aktive Signal als Stärke oder Risiko und ordnet ein
  ``weight`` (Score-Beitrag in Punkten) zu. Sortiert nach ``weight`` desc.
- ``_drivers_synthesis_line(breakdown) → str`` — Format
  ``"Stark: <top-2>. Schwach: <top-2>."``. Liest die bereits sortierte
  Breakdown-Ausgabe — keine zweite Sortierung. Leer, wenn weder
  Stärken noch Risiken aktiv.
- ``_drivers_block_html(s) → str`` — komplettes HTML inkl. Risiko-Badge,
  Synthese-Zeile und zwei Kategorie-Listen (max 5 Items pro Kategorie).
  Leer, wenn beide Listen leer sind.

### Klassifikations-Regeln (deterministisch)

| Signal | Stärke (Bedingung) | Risiko (Bedingung) |
|---|---|---|
| Short Float           | ≥ 15 %             | — |
| Days-to-Cover         | ≥ 5                | — |
| Float-Größe           | ≤ 50 M             | — |
| SI-Trend              | up                 | down |
| Earnings (Tage)       | ≤ 14               | — |
| 13F-Insider           | sec_13f_note vorh. | — |
| Short-Druck-Muster    | ja                 | — |
| Gamma-Squeeze         | possible/likely    | — |
| Borrow-Rate (extrem)  | > 100 %/Jahr (`IBKR_BORROW_BONUS_EXTREME`) | — |
| Borrow-Rate (hot)     | > `IBKR_BORROW_HIGH` (50 %) bis ≤ 100 %/Jahr (`IBKR_BORROW_BONUS_HOT`) | — |
| Put/Call-Ratio        | < 0.5 (bullisch)   | > 1.5 (bärisch) |
| RVOL                  | ≥ 2.0×             | — |
| Momentum (rel. SPY)   | ≥ +5 %             | < −3 % (raw chg) |
| RS vs. SPY            | rs_pts > +0.5      | rs_pts < −0.5 |
| Float-Turnover        | turnover_pts > 0   | — |
| Gap & Hold            | strong_hold        | fail (Bull-Trap) |
| RSI                   | —                  | > 70 (überkauft) |
| Kurs vs. MA50         | —                  | < −5 % |

Keine Signale für Felder, deren Daten fehlen (None / 0) — graceful Fallback,
keine Pseudo-Treiber.

### Wiring

Beide Card-Pfade emittieren denselben HTML-Block:
- v1 (``_card`` f-String): Variable ``drivers_block_html`` ersetzt den
  alten Inline-``<div class="driver-row">``.
- v2 (``_build_card_ctx`` + ``card.jinja``): Key ``drivers_block_html``
  im Render-Context, Template-Stelle ``{{ drivers_block_html }}``.

Render-Test (``_render_test`` mit ``JINJA_RENDER_TEST=1``) muss byte-
identisch v1 == v2 bleiben — beide Pfade rufen dieselbe Helper-Trio.

### CSS-Klassen (in ``templates/head.jinja``)

``.drivers-block`` (Container, border-top), ``.drivers-header``
(Risiko-Badge rechts), ``.drivers-synthesis`` (Akzent-Bar links,
``syn-pos`` / ``syn-neg``-Spans), ``.drivers-cats`` (1-spaltig mobil,
2-spaltig ≥ 480 px), ``.drivers-strengths`` / ``.drivers-risks`` (links
grüner / roter 3 px-Border), ``.drv-w`` (gewichtete Punktzahl,
``tabular-nums``), ``.drv-lbl`` (Treiber-Label).

### Pflege

Bei jeder Änderung an Score-Komponenten (neuer Bonus, geänderter
Schwellenwert) — ``_drivers_breakdown`` mit anpassen, sonst driften
Detail-Ansicht und tatsächlicher Score auseinander. Klassifikations-
Tabelle oben gleichzeitig aktualisieren.

---

## Watchlist-Score Single Source of Truth

Watchlist-Tile (Mini-Ring) UND aufgeklappte Detail-Card müssen IMMER
denselben Setup-Score zeigen. Die displayte Wahrheit ist der
**post-smoothing-Score** (= Wert in ``s["score"]`` nach
``apply_score_smoothing`` + Trend-Bonus + Agent-Boost), exakt wie
in der gerenderten ``card_html`` zu sehen.

### Score-Quellen-Reihenfolge in `wlRender`

```
1. WL_TOP10[t].score         (in-page für heutige Top-10, smoothed)
2. window._WL_CARDS[t].score (app_data.json für Watchlist-Ticker
                              außerhalb Top-10, smoothed)
3. WL_SCORES[t]               (score_history.json Last-Entry, RAW
                              pre-smoothing — nur Fallback wenn weder
                              Top-10 noch Watchlist-Card-Daten da)
```

Helper: ``_wlScoreOf(t)`` in `wlRender` ist die einzige Stelle, wo
diese Priorität angewandt wird. ``buildWlSparkOnly`` nutzt
denselben Branch (für Tickern ohne enrichment-Daten).

### Re-Render-Hook

`wlRender` wird zweimal aufgerufen:
1. Bei `DOMContentLoaded` — vor dem `app_data.json`-Fetch.
   Tile zeigt zunächst WL_TOP10/WL_SCORES (Top-10 sofort korrekt;
   Non-Top-10 zeigt raw history-Score).
2. Nach `app_data.json`-Fetch (`_WL_CARDS` ist gesetzt) — Re-Render
   updated alle Tile-Scores auf den smoothed-Wert.

`window.wlRender = wlRender` exponiert die Funktion aus dem
Watchlist-IIFE.

### Bug-Verweis

Symptom (vor diesem Fix): Tile zeigte 80 (raw aus History), Card
zeigte 48.7 (smoothed). Ursache: `wlRender` las nur `WL_SCORES`
für Non-Top-10-Ticker; die nach Fetch verfügbaren `_WL_CARDS` mit
smoothed Scores wurden ignoriert.

### Pflege

- Score-Field in `_wl_card_payload` (= `_s.get("score", 0)`) ist
  der **smoothed**-Wert. Bei Refactor sicherstellen, dass diese
  Quelle nicht versehentlich auf `score_raw` umgestellt wird —
  sonst wäre das Tile + Card asymmetrisch zur restlichen Anzeige.
- Falls neue WL-Render-Funktionen hinzukommen: dieselbe 3-Stufen-
  Priorität nutzen, nicht direkt `WL_SCORES` lesen.

---

## Watchlist-Drawer Render-Pfad (Stale-Data-Fix Phase 1, 12.05.2026)

Der expandierte Watchlist-Drawer (Detail-Ansicht beim Aufklappen)
wird von `wlExpand(ticker, btn)` (`generate_report.py`-JS, Definition
unter `window.wlExpand = function`) gemanagt. Phase 1 adressiert zwei
Stale-Data-Symptome:

### Stufe 1 — `dataset.loaded`-Cache-Gate ENTFERNT

Vorher blockte ein `if (body.dataset.loaded) { … return; }` direkt
nach dem Open-Check den Re-Render. Folge: nach erstem Open lieferten
folgende Open-Vorgänge die eingefrorene HTML-Body-Snapshot — selbst
wenn `WL_TOP10` / `_WL_CARDS` zwischenzeitlich aktualisiert wurden.

**Nach dem Fix:** bei jedem Drawer-Open läuft
`buildWlDetails(ticker, d)` neu und liest den aktuellen Stand der
JS-Datenquellen. Der `body.dataset.loaded='1'`-Marker bleibt
**erhalten** — er hat keinen Funktions-Bypass mehr, dient aber als
selectorbarer „Drawer ist offen"-Marker für Stufe 2a.

### Stufe 2a — `_WL_CARDS`-Re-Assign nach ki_agent-Tick

Der KI-Agent-Trigger-Success-Handler (`_kiAgentSuccess`,
`generate_report.py:8580+`) fetcht `app_data.json` nach erfolgreichem
Workflow-Lauf und ruft `renderAgentSignals` für die Top-10-DOM-Patches.
Vorher fehlte das **Re-Assign von `window._WL_CARDS`** — folge: jeder
zukünftige Drawer-Open zog die alte Page-Load-Snapshot statt der
ki_agent-Updates.

**Nach dem Fix:** Reihenfolge im Then-Block ist hartcodiert:

1. `window._WL_CARDS = appData.watchlist_cards || {}` — frische
   Drawer-Daten verfügbar machen (null-Fallback robust).
2. `document.querySelectorAll('.wl-body[data-loaded]').forEach(b => delete b.dataset.loaded)` —
   `data-loaded`-Marker auf allen offenen Drawer entfernen. Funktional
   nach Stufe 1 redundant (Cache-Gate ist eh weg), aber forward-
   kompatibel zu Stufe 2c.
3. `renderAgentSignals(data)` — Top-10-DOM-Patches.

### Nicht in Phase 1

- **Stufe 2b** (komplettes Client-Side-Drawer-Render aus Live-Feldern):
  Statt eingefrorenen `card_html`-String würde der Drawer aus
  `_WL_CARDS[t].score`/`.price`/etc. dynamisch neu gebaut. Größerer
  Eingriff, eigene Session falls Phase 1 nicht reicht.
- **Stufe 2c** (auto-Re-Render offener Drawer bei ki_agent-Tick):
  `[data-loaded]`-Marker wird vom Selektor in 2a bereits ausgewertet —
  Stufe 2c würde danach `buildWlDetails` für jeden offenen Drawer
  aufrufen, statt nur das Attribut zu löschen.

### Verifikation

- `python scripts/mock_test_watchlist_drawer_stale_data.py` (Source-
  Inspektion, 9 Tests).
- Manuell am Browser: Drawer öffnen → ki_agent-Trigger ausführen →
  Drawer schließen + neu öffnen → Werte müssen den ki_agent-Updates
  entsprechen, identisch zu den frischen Top-10-Fliesen.

---

## Earliness-Indikator (V2 — DTC-Niveau-Basis, ohne Score-Effekt)

`compute_earliness_pts(stocks)` misst **Squeeze-Reife / Short-Stack-
Druck** — operationalisiert via DTC (Spot, Days-to-Cover). „Earliness"
heißt hier **nicht** „zeitliche Nähe zum Move", sondern „ist das
Substrat reif für eine Bewegung?". Hoher DTC = der Short-Stack ist
bereits aufgebaut = mehr potentieller Squeeze-Brennstoff.

**Datenbeleg (Diagnose 13.05.2026):** Mann-Whitney-U über 14
Trading-Tage, Gewinner (return_10d ≥ +10 %, n=34) vs. Verlierer
(return_10d ≤ −5 %, n=44): DTC liefert **AUC 0.77** (Median 10.05 vs
5.40). Die ursprünglichen V1-Sub-Signale (si_accel, si_velocity,
PM-Volume) sind aus `backtest_history.json` nicht rückwirkbar
berechenbar — werden nicht weiter geführt.

### V2-Formel (aktiv, Default)

`EARLINESS_FORMULA_VERSION = 2`. Skala: 0..`EARLINESS_PTS_MAX` (= 100).

```
DTC-Bucket-Mapping  (s["short_ratio"])
  dtc < 3      →   0 Pkt   bucket=below_3
  3 ≤ dtc < 5  →  25 Pkt   bucket=3_to_5
  5 ≤ dtc < 8  →  50 Pkt   bucket=5_to_8
  8 ≤ dtc < 12 →  75 Pkt   bucket=8_to_12
  dtc ≥ 12     → 100 Pkt   bucket=ge_12

Late-Runner-Penalty   (s["rel_volume"])
  rvol > EARLINESS_LATE_RUNNER_RVOL_MAX (= 5)  →  pts × EARLINESS_LATE_RUNNER_FACTOR (= 0.5)
```

Schwellen in `config.py`: `EARLINESS_DTC_BUCKET_1_MIN = 3.0`,
`_2_MIN = 5.0`, `_3_MIN = 8.0`, `_4_MIN = 12.0`,
`EARLINESS_DTC_BUCKET_PTS = (0, 25, 50, 75, 100)`.

Bei fehlendem `short_ratio` / `rel_volume` → 0.0 als Default → Bucket 0
(graceful Fallback, keine Exception).

### Doppel-Penalty für Late-Runner (bewusst)

Es wirken **zwei eigenständige Late-Runner-Penalties parallel** — bewusste
Doppel-Bestrafung, weil ein Late-Runner zwei Probleme hat (Move schon
gelaufen UND Setup-Hot):

| Penalty | Trigger | Effekt | Implementierung |
|---|---|---|---|
| **Setup-Score-Penalty** (`apply_late_runner_penalty`) | `rsi14 > LATE_RUNNER_RSI_THRESHOLD` (75) ODER `chg2d > LATE_RUNNER_MOVE_2D_THRESHOLD` (20 %) | `s["score"] × LATE_RUNNER_PENALTY` (0.85, also −15 %) | `generate_report.py:2843+` |
| **Earliness-Penalty** (V2-intern) | `rvol > EARLINESS_LATE_RUNNER_RVOL_MAX` (5×) | `earliness_pts × EARLINESS_LATE_RUNNER_FACTOR` (0.5, also −50 %) | `_earliness_pts_v2` |

Beide treffen typischerweise denselben Stock-Typ (RSI hoch + RVOL-Spike
zusammen) — der kombinierte Conviction-Effekt ist beabsichtigt: dieser
Stock soll deutlich tiefer in der Top-10 landen.

### Version-Schalter / Notfall-Rollback

`EARLINESS_FORMULA_VERSION` in `config.py` (= 2 Default). Bei `= 1`
fällt `compute_earliness_pts` auf den alten V1-Pfad zurück (siehe
`_earliness_pts_v1` — `si_accel` + `si_velocity` + PM-Vol-Komponente).
V1-Konstanten bleiben im config als `# V1-only` markiert, neue Pfade
sollen nicht darauf zugreifen.

Rollback-Kriterien (nach 30 Tagen Live-Daten reevaluieren): falls
die DTC-AUC auf < 0.55 einbricht oder Conviction-Median systematisch
> 80 driftet (Push-Inflation zurück), Version-Schalter auf 1 setzen
und Re-Kalibrierung diskutieren.

### Felder auf dem Stock-Dict (V2)

| Feld | Typ | Bedeutung |
|---|---|---|
| `earliness_pts`       | int 0..`EARLINESS_PTS_MAX` (= 100) | DTC-Bucket-Punkte, ggf. halbiert bei Late-Runner |
| `earliness_breakdown` | dict | V2-Keys: `version=2`, `dtc`, `rvol`, `dtc_bucket`, `base_pts`, `late_runner`, `final_pts` |

Bei `EARLINESS_FORMULA_VERSION = 1` enthält `breakdown` die V1-Keys
(`version=1`, `accel_match`, `velocity_match`, `pm_vol_match`).

`earliness_pts` und `earliness_breakdown` werden **immer** geschrieben
(auch bei `pts == 0`), so dass Konsumenten nicht zwischen „nicht
berechnet" und „berechnet, Bucket 0" unterscheiden müssen.

### Conviction-Integration (unverändert)

`compute_conviction_score` normalisiert `earliness_pts /
EARLINESS_PTS_MAX × 28` → Conviction-Earliness-Anteil 0..28. Die
Normalisierung ist **relativ**, der V1/V2-Schalter ist transparent für
diesen Code-Pfad (PTS_MAX ändert sich von 7 auf 100, Quotient bleibt
sinnvoll).

Erwarteter Effekt: Top-10-Median DTC ≈ 10 → `earliness_pts ≈ 75` →
Conviction-Earliness ≈ 21/28 (vorher in V1 systematisch 0/28). Die
Spitzen-Conviction wird häufiger ≥ 75 erreichen — Wirkung wird in der
„Conviction-Formel-Beobachtung Tag 3–6"-Wiedervorlage sichtbar.

### Pflege

- Schwellen-Anpassung (`EARLINESS_DTC_BUCKET_*_MIN`, `_PTS`,
  `EARLINESS_LATE_RUNNER_*`): nur in `config.py`, Code-Logik liest
  rein über Konstanten.
- Bei Erweiterung des V2-`earliness_breakdown`-Schemas (z.B. neues
  Feld `dtc_source`): gleichzeitig Mock-Test
  `scripts/mock_test_earliness_dtc.py` + diese Sektion + CLAUDE.md-
  Conviction-Tabelle prüfen.
- Score-Methodik-Sync-Regel: weiterhin **kein** Score-Effekt aus
  `earliness_pts` (nur via Conviction-Komponente). Bei späterer
  Aktivierung als on-top-Bonus in `score()` (analog `_float_turnover_pts`)
  diese Sektion oben „ohne Score-Effekt" → „mit Score-Effekt"
  umschreiben.
- V1-Pfad (`_earliness_pts_v1`) und V1-Konstanten **nicht entfernen**,
  bevor der Version-Schalter wieder ausgebaut wird — sonst kein
  Rollback-Pfad mehr.

### Bug-Verweis

Vor V2: Mittel-Refactor Stufe 1 lief seit ~30.04.2026 mit Logging-only
und lieferte in Top-10 systematisch `earliness_pts = 0` (V1-Sub-Signale
zu eng kalibriert, vor allem `EARLINESS_MAX_CHANGE_5D_PCT = 5 %` schloss
fast jedes Top-10-Setup aus). Conviction-Median lag deshalb dauerhaft
≈ 50 (medium) — Aktions-Pushes fehlten. V2 löst das datenbelegt.

---

## Score-Methodik-Sync-Regel

Die **Score-Methodik & Filterkriterien**-Sektion in
`generate_report.py:4170+` (gerendert in der Info-Panel-Aufklappbox auf
der Website) **muss synchron mit dem Code bleiben**. Bei JEDER Code-
Änderung, die einen der unten genannten Bereiche berührt, wird die
Sektion **im selben Commit** mit aktualisiert — **ohne dass der User
explizit darum bittet**.

### Betroffene Bereiche

- **Filter-Schwellen**: `MAX_MARKET_CAP_B`, `MIN_SHORT_FLOAT`, `MIN_PRICE`, `MIN_REL_VOLUME`, `INTL_SCREENING_*`, manuelle Watchlist-Bypass-Logik
- **Score-Komponenten + Punkte**: `score()` Fall 1 / Fall 2 (Struktur/Katalysator/Timing-Gewichte), `_compute_sub_scores()` Sub-Score-Caps (`SUB_STRUCT_MAX`, `SUB_CATALYST_MAX`, `SUB_TIMING_MAX`)
- **Boni / Malus**: `COMBO_BONUS`, `SCORE_TREND_BONUS/MALUS`, `AGENT_BOOST_*`, `SQUEEZE_HIST_MALUS_*`, `FLOAT_TURNOVER_PTS_*`, `GAP_PTS_*`, `RS_SPY_PTS_MAX`
- **Monster-Score-Logik**: `apply_monster_score()` Faktoren (×1.20 / ×0.80 / neutral), Cap 100
- **KI-Agent-Boni**: StockTwits-Skala, RVOL High/Velocity, UOA Vol/OI + Call/Put, Gamma Squeeze, Perfect-Storm-Multiplikator, News-Decay-Gewichte, Insider-Punkte, FINRA-SSR
- **Push-Trigger**: `ANOMALY_*`-Schwellen (RVOL, UOA, Score-Sprung, Gap+Hold-Combo, Perfect Storm, Monster-Backup), `EARNINGS_IMMEDIATE_*`, `EXIT_*`-Trigger
- **Datenquellen**: neue API, entfallene Quelle, Provider-Wechsel (Yahoo, Finviz, FINRA, yfinance, Stockanalysis, EarningsWhispers, Sektor-ETFs, StockTwits, ntfy.sh, OpenInsider, SEC, FDA RSS, Anthropic Claude)

### Automatik-Workflow

1. **Diagnostizieren** ob die Code-Änderung die Methodik berührt (Liste oben).
2. **Identifizieren** der betroffenen Zeile(n) in der Sektion (`<li>`-Einträge in den vier `info-box`-Blöcken: Filterkriterien, Score-Formel, Datenquellen, ⚡ KI-Agent).
3. **Anpassen** im selben Commit — Zahlen, Komponenten-Listen, Boni-Reihenfolge, Push-Trigger entsprechend dem neuen Code-Stand.
4. **User nicht explizit fragen** — die Sync ist Pflicht-Bestandteil jedes Methodik-relevanten Commits.
5. **Commit-Body** kurz erwähnen: „Methodik-Sektion aktualisiert" (oder Detail welche Zeile betroffen ist), damit beim Review nachvollziehbar ist.

### Negativliste (kein Sync nötig)

- Reine Refactorings ohne Verhaltensänderung (z. B. Helper extrahieren, Funktion umbenennen)
- Frontend-CSS / Layout-Tweaks
- Workflow-File-Änderungen, die keine Code-Logik betreffen
- Bug-Fixes, die nur das dokumentierte Verhalten herstellen (ohne Schwellen zu ändern)
- Test-/Smoke-Code

### Auto-Generation für Score-Komponenten-Caps (seit 10.05.2026)

Die **Score-Formel-Box** (drei Sub-Score-Listen Struktur / Katalysator /
Timing) wird seit Code-Hygiene Punkt 5, Schritt 1 aus `config.py`-
Konstanten auto-generiert. Bei einer neuen oder geänderten Sub-Score-
Komponente:

- Punkt-Cap in `config.py` ergänzen (Naming: `SUB_<SIGNAL>_DISPLAY_PTS_MAX`,
  bei elif-Buckets `..._LOW`/`..._HIGH`).
- Tupel-Eintrag in der entsprechenden `methodology_*_rows`-Liste
  (`generate_report.py`) referenziert die Konstante per f-String —
  **kein manuelles Pflegen des Display-Werts mehr nötig**.

**Weiterhin manuell synchron** zu halten:

- Filter-Schwellen-Box (Filterkriterien)
- Boni / Malus / Monster-Score-Box (hardcodierte Werte +5 / ±3 / ×1.05 / −3/−5)
- Datenquellen-Liste
- ⚡ KI-Agent-Box

Drift-Schutz für die Sub-Score-Caps ist damit strukturell gesichert,
solange `score()` und `_compute_sub_scores()` mit den gleichen
Konstanten arbeiten. Die Drift zwischen Code und Konstante (`score()`-
Cap weicht von `SUB_*_DISPLAY_PTS_MAX` ab) bleibt manuell zu pflegen —
Schritt B würde `score()` aus den gleichen Konstanten ableiten und
diese letzte Drift-Quelle eliminieren.

### Bedingte Boni — Display-String muss Pfad-Vielfalt zeigen (10.05.2026)

Eine Komponente kann mehrere Punkt-Pfade haben (Standard-Wert UND
Bonus-Bedingung). Der Methodik-Display-String muss **alle aktivierbaren
Maxima** zeigen, sonst unterschätzt er den tatsächlichen Score-Beitrag.

Beispiele aktuell wirksam:

- **SI-Trend** (Struct): `5 Pkt (7 bei Beschleunigung)` — Sub-Score-Cap
  ist 5, aber `score_bonus()` addiert on-top 7 bei `si_accelerating=True`.
- **Agent-Boost** (Boni-Box): `×1.05–1.15 (je KI-Score-Stufe)` — nicht
  nur `×1.05`, sondern Bandbreite.

Pflege-Regel: bei jeder neuen oder geänderten Acceleration-/Multiplikator-
Logik den Display-String entsprechend ergänzen, nicht nur den Standard-
Wert zeigen.

Vollständig in der Boni-/Malus-Box gelistet (Stand 10.05.2026):

- **Kombinations-Bonus** (`COMBO_BONUS = 5`).
- **Score-Trend** (`SCORE_TREND_BONUS = 3`).
- **Agent-Boost** (`apply_agent_boost`, ×1.05–1.15).
- **FINRA Trend-Up Bonus** (`score_bonus()`, +5 / +7 bei Beschleunigung).
- **Historischer Squeeze** (`SQUEEZE_HIST_MALUS_30D / _90D`).
- **Late-Runner-Penalty** (`apply_late_runner_penalty`, ×0.85).

Im Zweifel: lieber Sync mit kurzem Hinweis im Commit-Body als Drift-Risiko.

---

## Score-Konfidenz-Stufen (Stufe 1, rein anzeigend)

Externe Methodik-Bewertung: solange Live-Datenmenge klein ist (heutige
Validierungs-Diagnose 13.05.2026: n=78 für Earliness V2), soll das
Tool transparent kommunizieren, **wie belastbar** die Scores
statistisch sind. Stufe 1 zeigt **eine** qualitative Konfidenz-Stufe
pro Score-Klasse im Methodik-Panel — keine Anzeige auf der Karte,
keine Score-Berechnungs-Beeinflussung.

### Vier Stufen (qualitativ, nicht prozentual)

Bewusste Wahl gegen prozentuale Anzeige — verhindert das
„85 %-Garantie"-Missverständnis.

| Stufe | Emoji | Bedeutung | Trigger |
|---|---|---|---|
| **robust**       | 🟢 | > 500 Backtest-Datenpunkte mit Returns + AUC-Test belegt | Setup-Score (heute n≈1200) |
| **mittel**       | 🟡 | 50–500 Datenpunkte mit AUC, oder ≥ 500 ohne AUC | Earliness V2 (heute), Monster-Score (Komposition) |
| **provisorisch** | 🟠 | 1–50 Datenpunkte mit AUC | (heute keine — Übergangs-Stufe nach Schema-Erweiterung) |
| **heuristisch**  | 🔴 | Keine Validierung, rein theoretisch zusammengesetzt | Conviction, KI-Score, Exit-Druck heute |

### Aktuelle Stufen pro Score (Stand 14.05.2026)

| Score | Tier | n | Anmerkung |
|---|---|---:|---|
| Setup-Score | 🟢 robust | ~1200 | Backtest-Bucket-Auswertung gegen `return_10d` |
| Earliness V2 | 🟡 mittel | 78 | Mann-Whitney-U 13.05.2026 (AUC 0.77); Re-Test in 14–30 d via Trend-Logging (PR #142) |
| Monster-Score | 🟢 robust | ~1200 | erbt Setup-Konfidenz (Komposition) |
| KI-Score | 🔴 heuristisch | 0 | Wirkt nur als Boost-Multiplikator ×1.05–1.15 |
| Conviction | 🔴 heuristisch | 0 | Keine Backtest-Persistenz; Komponenten-Konfidenz (Stufe 2) erst nach Schema-Erweiterung |
| Exit-Druck | 🔴 heuristisch | 0 | Closed-Trades-Snapshot-Schema offen |

### Implementations-Architektur

- **Berechnung**: `compute_score_confidence(backtest_history)` in
  `generate_report.py`. Pure Funktion — kein State, kein I/O,
  Stichprobe ist die übergebene `backtest_history`-Liste.
- **Modul-State**: `_SCORE_CONFIDENCE: dict` (analog `_FX_USD_EUR`).
  Gesetzt in `main()` direkt vor `generate_html` via
  `globals()["_SCORE_CONFIDENCE"] = compute_score_confidence(...)`.
- **HTML-Render**: `_score_confidence_rows_html(confidence)` baut die
  `<li>`-Liste für das Methodik-Panel. Bei leerem Snapshot →
  Hinweis-Zeile statt Crash.
- **Persistenz**: `app_data.json["score_confidence"]` — Frontend kann
  später Stufe 2 (Tooltip auf Conviction-Pill) daraus rendern.
- **Schwellen in `config.py`**: `SCORE_CONFIDENCE_N_ROBUST = 500`,
  `_N_MITTEL = 50`, `_N_PROVISORISCH = 1`,
  `_MAX_AGE_DAYS = 14` (Stale-Hinweis).
- **CI-Lint**: `scripts/lint_score_confidence_isolation.py` erzwingt,
  dass die Konfidenz NICHT in Score-Berechnungs-Pfaden gelesen wird.

### Phase 2 — Hybrid-Wasserzeichen auf der Karte (16.05.2026, live)

Macht die Konfidenz-Stufe pro Score-Klasse direkt auf jeder Top-10-
und Watchlist-Drawer-Karte sichtbar — **ohne neue Farben, ohne
Lesbarkeits-Verlust**.

**Design-Prinzip:** subtiles Dimming (nur opacity 1.00 / 0.85) plus
Unterstreichungs-Form als visuelle Hauptarbeit. Gepunktete Linie ist
im Webdesign etabliertes Signal für „Tooltip verfügbar / fragliche
Angabe" (analog Rechtschreibprüfung in Word). **Color-Blind-safe** —
kein Farb-Code, nur Opacity + Form-Code.

| Tier | CSS-Klasse | Opacity | Unterstreichung | Cursor |
|---|---|---:|---|---|
| robust | `.sb-conf-robust` | 1.00 | keine | default |
| mittel | `.sb-conf-mittel` | 0.85 | keine | default |
| provisorisch | `.sb-conf-prov` | 0.85 | durchgehend dünn | help |
| heuristisch | `.sb-conf-heur` | 0.85 | gepunktet | help |

CSS lebt in `templates/head.jinja` direkt nach den bestehenden
`.sb-*`-Klassen (~Z. 1019).

**Helper `_conf_class(score_class)`** in `generate_report.py` liest
aus dem Modul-State `_SCORE_CONFIDENCE`, liefert `(css_class, title,
aria_label)`. Bei tier=robust sind `title` und `aria_label` leer →
das HTML bekommt keine unnötigen Attribute. Sonst:

- `title="Konfidenz: heuristisch — Wirkt nur als Multiplikator ×1.05–1.15"`
- `aria-label="Konfidenz heuristisch"`

Fallback bei leerem `_SCORE_CONFIDENCE` oder unbekannter Stufe →
`heuristisch` (konservativ, signalisiert „nicht-validiert" statt
fälschlich Vertrauen). Doppelte Anführungszeichen in `note` werden
zu Single-Quotes konvertiert — schützt die `title="..."`-Attribut-
Syntax.

`_score_block_inner_html` wendet die Klasse auf **alle 4 sb-num-
Spans** an (Conviction / Setup / Monster / KI). Watchlist-Drawer-
Karten erben über `_wl_full_card_html` (regex-Stripping, gleiche
Render-Funktion).

**Verhältnis zum CI-Lint** `lint_score_confidence_isolation.py`:
`_score_block_inner_html` und `_conf_class` sind **Render-Funktionen**,
nicht in `_FORBIDDEN_FUNCS`. Konfidenz darf in Render-Pfaden gelesen
werden — verboten ist nur die Score-/Conviction-Berechnung selbst.

**Phase-2-Wiedervorlagen (jetzt umgesetzt):**

- Konfidenz pro Score-Row sichtbar ✓
- Tooltip mit Note ✓
- Color-Blind-sicher ✓

### Nicht in Phase 2 (Folge-PRs)

- **Auto-Hochstufung Earliness** nach 14–30 d Live-Daten:
  `compute_score_confidence` muss dann den Trend-Logging-AUC-Wert
  aus `backtest_history.{backtest_schema_version: 4}` rechnen.
  Aktuell ist die Earliness-Stufe **hartkodiert** auf `mittel` mit
  Hinweis auf den Re-Test-Termin.
- **Validierungs-Auto-Refresh**: bei Stale (≥ `MAX_AGE_DAYS`)
  Hinweis „Konfidenz-Daten veraltet". Logik im Frontend, nicht jetzt.
- **Conviction-Komponenten-Aufschlüsselung im Tooltip**: Conviction-
  Component-Konfidenz (Setup-Anteil vs. Earliness-Anteil) als
  Detail-Tooltip. Erfordert Conviction-Backtest-Persistenz, die
  heute noch fehlt.

### Pflege

- Tier-Schwellen-Anpassung: in `config.py`. Code-Logik liest rein
  über Konstanten.
- Bei neuem Score: `compute_score_confidence`-Return-Dict ergänzen
  + `_score_confidence_rows_html`-`_labels` ergänzen + CLAUDE.md-
  Tabelle oben ergänzen.
- Bei Aufnahme eines neuen Backtest-Schemas, das Conviction-Werte
  persistiert: hardgecodete Heuristik-Stufe für Conviction durch
  Auswertungs-Helper ersetzen.

---

## Navigation (Hamburger-Drawer, universal)

Der Header (`<header class="app-hdr">`) ist `position:sticky;top:0` mit
`padding-top: env(safe-area-inset-top)` für iPhone-Notch. Beim Scrollen
über 5 px setzt JS die Klasse `.scrolled` (dezenter Box-Shadow als
visuelles Feedback). **Identisches Verhalten auf allen Breakpoints** —
Hamburger + Drawer auch auf Desktop, kein zweites Layout. Drawer-Breite
280 px mobile, 320 px ≥ 768 px (`@media`-Override). Desktop-Header-Layout
in einer Zeile: Title (links) | Timestamp (zentriert) | Hamburger (rechts);
auf Mobile wraps der Timestamp in Reihe 2.

### Struktur

- **Hamburger-Button** (`#hamburger-btn`, 44×44 Touch-Target) rechts in
  `.hdr-main`, ersetzt die alten Action-Tile-Blöcke `.hdr-btns` +
  `.hdr-icons`. Icon togglet zwischen `data-lucide="menu"` und `="x"`.
- **`.menu-drawer`** (280 px mobil / 320 px ≥768 px) fährt von oben
  rechts ein (`transform:translateY(-110%)` → `translateY(0)`).
- **`.menu-overlay`** (Backdrop) schließt bei Tap.
- **ESC-Taste** schließt ebenfalls.

### Menü-Inhalt (Reihenfolge fix)

| Position | Icon | Aktion |
|---:|---|---|
| 1 (Primär, cyan) | `refresh-cw`    | `reloadPage()` |
| 2 | `calculator`     | `triggerWorkflow()` |
| 3 | `zap`            | `triggerKiAgent()` |
| 4 | `bar-chart-3`    | `scrollToBacktesting()` (öffnet `#bt-section` + scroll) |
| 5 | `book-open`      | `scrollToMethodology()` (öffnet `details.info-panel` + scroll) |
| 6 | `arrow-up-down`  | Score-Sortierung-Submenu (Setup ✓ / Monster ✓) |
| 7 | `message-circle` | `toggleChat()` |

**Footer-Reihe** (4 Utility-Buttons): `minus` (A−) · `plus` (A+) ·
`settings` · `moon`/`sun` (Theme-Toggle).

**Token-Reset bewusst NICHT im Footer** — `rotate-ccw`-Icon (Refresh-
Pfeil) wurde von Usern für Reload mistappt → Token wurde versehentlich
gelöscht. Reset bleibt über das Settings-Panel zugänglich
(`clearGhToken`-Link). Zusätzlich hat `resetToken()` einen
`confirm()`-Dialog bekommen, falls die Funktion künftig wieder von
irgendwo getriggert wird.

### Score-Sortierung-Submenu

Auswahl persistiert in `localStorage['squeeze_sort_mode']` (unverändert
zur alten Logik). `_applySortMode(mode)` aktualisiert zusätzlich:
- `#menu-sort-current` (Label „Setup" / „Monster")
- `#menu-sort-check-setup` / `#menu-sort-check-monster` (`visibility`)

Submenu-Toggle schließt **nicht** den Drawer — Auswahl ist eine Aktion
INNERHALB des Sub-Menüs. Nach `selectSortMode()` schließt sich das
Submenu, der Drawer bleibt offen.

### Lucide-Icons

CDN: `<script src="https://unpkg.com/lucide@latest" defer>` in
`templates/head.jinja`. Icons via `<i data-lucide="name"></i>`. Aufruf
`lucide.createIcons()` an drei Stellen:
- `DOMContentLoaded`-Event
- `load`-Event (für Fall, dass CDN bei DOMContentLoaded noch nicht da)
- Nach jeder dynamischen Icon-Manipulation (z. B. Hamburger
  `menu`↔`x`-Toggle in `_setMenuOpen`)

Styling: `stroke-width:2`, Größe via Container (`.menu-icon-box i {width:18px}`,
`.hamburger-icon {width:24px}`). Farbe via `currentColor` von Parent.

### Wochenend-Banner

`#non-trading-banner` einzeilig: `⚠️ {reason} — Nächster US-Handelstag:
{date}`. Daten-Quelle-Hinweis impliziert, nicht mehr explizit.

### Bestehende Funktionen unverändert

`reloadPage()`, `triggerWorkflow()`, `triggerKiAgent()`, `toggleChat()`,
`changeFontSize()`, `setSortMode()`, `toggleSettings()`, `resetToken()`,
`toggleBacktesting()` werden vom Drawer aufgerufen, sind aber nicht
umbenannt — Rückwärtskompatibilität für direkte Aufrufer (Polling-Code
etc.). `toggleTheme()` bleibt definiert, ist aber aktuell nicht im
Drawer verlinkt; `theme-btn`-Lookups sind defensive (`if (tb)`).

---

## v1/v2 Render-Pfad

Es existieren zwei Render-Pfade für die HTML-Generierung — **v2 ist
nicht autark** und delegiert am Ende an v1.

- **v1** = f-String in `_card()` + `generate_html_v1()` (Outer-Page).
- **v2** = `templates/card.jinja` via `generate_html_v2()` — rendert
  **nur** die Karten-Snippets und schleust sie als `cards`-Key in
  v1's Context ein. Die letzte Zeile von `generate_html_v2()` ist
  `return generate_html_v1(stocks, report_date, _ctx=ctx_v2)` — die
  komplette umschließende Seite (Header, Watchlist-Section,
  Backtesting, Chat-Glue, JS, Footer) kommt weiterhin aus v1.
- Zusätzlich ruft `_wl_full_card_html()` direkt `_card(0, s)` auf und
  post-processed das HTML mit Regex-Stripping — der Watchlist-Drawer
  hängt also ebenfalls am v1-Pfad.

**Wer v1 löscht, killt v2 mit.** Eine vollständige Migration zu
reinem Jinja erfordert drei Schritte in einem Zug:

1. `templates/page.jinja` für die Outer-Page anlegen (Header,
   Watchlist-Section, Backtesting, Chat-Glue, JS, Footer aus v1's
   f-String herauslösen).
2. `_wl_full_card_html()` ohne Regex-Stripping neu aufbauen
   (eigene `wl_card.jinja` oder direkter Python-HTML-Zusammenbau aus
   dem Card-Context).
3. `generate_html_v2()` autark machen — kein
   `return generate_html_v1(...)` mehr.

Erst danach v1 entfernen. `JINJA_RENDER_TEST` muss vorher die
Outer-Page mit byte-vergleichen können — aktuell deckt der Test nur
die Karten-Snippets ab. Ein prominenter Architektur-Anker direkt vor
`generate_html_v2()` in `generate_report.py` wiederholt diese
Hinweise im Code.

---

## Live-Quote-Polling (Cloudflare-Worker-basiert)

Watchlist-Drawer und expandierte Top-10-Karten pollen Preis + Tages-
gewinn live alle **15 Sekunden** aus yfinance. Datenpfad:

```
Browser  ──GET QUOTE_PROXY_URL?ticker=DMRC──▶  Cloudflare Worker  ──▶  Yahoo v8 chart
   ▲                                                  │
   └────── JSON {ticker, price, change, …} mit CORS ──┘
                  + Edge-Cache 10s
```

**v8 statt v7:** Yahoo verlangt seit Mai 2026 für den v7-Quote-
Endpoint einen Crumb-Auth-Token (HTTP 401 ohne). v8-Chart ist
öffentlich, liefert `meta.regularMarketPrice` + `meta.chartPreviousClose`
— daraus rechnet der Worker `change_abs` und `change` (Tages-Prozent).

**Single-Ticker pro Request:** v8 ist nicht batch-fähig. Mehrere
Tickers parallel = Frontend macht `n` separate Fetches in `Promise.all`
(typisch 1 Fetch pro offenem Drawer / aufgeklappter Top-10-Karte).

### Setup (User-Action, einmalig)

1. `cloudflare/quote-proxy/README.md` durchlesen
2. `wrangler login` + `wrangler deploy` aus `cloudflare/quote-proxy/`
3. Worker-URL kopieren (z.B. `https://quote-proxy.<account>.workers.dev`)
4. Repo-Secret `QUOTE_PROXY_URL` setzen
5. Nächster Daily-Run injiziert die URL als JS-Konstante in `index.html`

Bei leerem `QUOTE_PROXY_URL` ist `_startQuotePoll` no-op — Frontend
bleibt funktional, eingebrannte Werte bleiben sichtbar (kein UI-Bruch).

### URL-Sanitize

`_qp_raw` aus ENV wird gegen
`^https://[A-Za-z0-9.\-]+(/[A-Za-z0-9._\-/]*)?$` validiert. Pfad und
Subdomain erlaubt, aber **kein Query/Anker** (Polling hängt
`?symbols=…` selbst an). Max 256 Zeichen.

### DOM-Patches

`_quotePatchScope(scope, ticker, price, change)` überschreibt
(Argument `change` = Tages-Prozent, kommt 1:1 aus dem Worker-Feld
`change`):

- **Preis**: alle `.price-tag` im scope (Top-10-Header + Drawer-Header)
- **Momentum-Box**: `.metric-box` mit `.m-lbl=Momentum` (`.m-val`-Inhalt
  ersetzen, `change_5d`-Sub-Span konservieren — identische Logik zu
  `_patchWlMomentumLive`)

Andere Felder (Score, RVOL, DTC, Float, SI-Trend) bleiben eingebrannt
— Polling deckt nur die zwei Echtzeit-relevanten Felder ab.

### Lifecycle

| Konsument | Open-Trigger | Close-Trigger |
|---|---|---|
| **Watchlist-Drawer** | `wlExpand(ticker, btn)` mit `opening=true` → `_startQuotePoll(body, ticker)` | `wlExpand` mit `opening=false` → `_stopQuotePoll(ticker)` |
| **Top-10-Karte** | `toggleDetails(id)` mit neuem `open=true` → `_startQuotePoll(card, ticker)` (Live-Dot wird lazy in `.score-block` injiziert beim ersten Open) | `toggleDetails(id)` mit `open=false` → `_stopQuotePoll(ticker)` |

`_quotePollers: Map<ticker, {intervalId, scope}>` — pro Ticker genau
ein Eintrag. Doppel-Open für denselben Ticker stoppt zuerst den
bestehenden Poller, dann startet einen neuen (verhindert
verwaiste Intervalle).

### visibilitychange-Handling

Globaler `visibilitychange`-Listener (lazy via
`_ensureQuoteVisibilityHook`):

- Tab wird **hidden** → alle aktiven Intervalle gestoppt, Indikatoren
  auf `paused` (gedimmtes Grün).
- Tab wird wieder **visible** → sofortiger Fetch + neues Intervall pro
  Eintrag in `_quotePollers`.

Das deckt Tab-Wechsel, Browser-Background, iPhone-Lock-Screen ab —
kein Hintergrund-Verkehr im inaktiven Tab.

### Live-Indikator (`.quote-live-dot`)

8-px-runder Dot, drei Zustände (CSS in `templates/head.jinja`):

| Klasse | Farbe | Bedeutung |
|---|---|---|
| (default, kein Modifier) | `#475569` | Polling noch nicht gestartet / inaktiv |
| `.quote-live-on` | `#22c55e` + Pulse-Animation 2s | Polling aktiv, letzter Fetch erfolgreich |
| `.quote-live-stale` | `#94a3b8` static | Worker/Yahoo nicht erreichbar — eingebrannte Werte stehen sichtbar |
| `.quote-live-paused` | `#22c55e` opacity 0.4 | Tab inaktiv, Polling pausiert |

Bei Fetch-Fehler **kein Toast** (Spec — Push-Müll vermeiden), nur
Indikator-Update.

### Worker-Code

Lebt in `cloudflare/quote-proxy/`. Single-Source-of-Truth für die
Yahoo-Backend-Mapping-Logik:

- `worker.js`: Fetch-Handler, CORS-Allow-List (default
  `https://easywebb911.github.io`), Edge-Cache 10s, max 10 Symbole
  pro Request.
- `wrangler.toml`: minimal-config; account_id auto via `wrangler
  login`, Custom-Domain optional.
- `README.md`: Deploy-Schritte, Free-Tier-Quota-Check, Fail-Modes.

### Quoten-Rechnung

Cloudflare-Workers-Free: 100 000 Req/Tag.
- 1 Drawer × 4 Polls/min × 60 min × 24 h = **5 760 Req/Tag**.
- 4 parallele Drawer × 24 h = **23 040 Req/Tag** — entspannt im Limit.
- Yahoo selbst: Edge-Cache 10s reduziert Backend-Load drastisch
  (Symbol-Sets sind sortiert+dedupliziert für höhere Hit-Rate).

### Pflege

- Bei Schema-Änderung der Worker-Response (`{ticker, price, change,
  change_abs, volume, market_state, prev_close, ts}`): gleichzeitig
  `_quoteFetchOnce` (Browser-Reader) und `worker.js` (Server-Mapper)
  anpassen. Tests in `scripts/mock_test_quote_polling.py` decken
  beide Seiten ab.
- Bei Yahoo-Endpoint-Break (z.B. `chart.result[0].meta` weg): Worker
  antwortet `HTTP 502 yahoo_no_meta`, Frontend zeigt
  `.quote-live-stale` — kein UI-Crash. Diagnose via `wrangler tail`.
- Bei zusätzlichen Live-Feldern (z.B. RSI live): NICHT in dieser
  Architektur — RSI braucht historische Bars, nicht echtzeit-snap.
  Eigener Pfad notwendig.
- Score-Methodik-Sync ist **nicht betroffen** — reines Frontend-
  Anzeige-Feature, keine Score-/Filter-Logik berührt.

---

## Health-Check (Phase 1 — State-Invariants)

Frühwarnsystem für stille Datenausfälle. Pipeline-Code läuft grün,
aber das geschriebene Artefakt verhält sich falsch (Bug-Klasse PR #119
score_history-Pruning, KI-Score-Drift 14.05.2026). Spec ist
**Single-Source-of-Truth** in ``docs/health_check_spec.md`` — diese
Sektion ist nur ein CLAUDE.md-Anker auf das Doku-File.

### Architektur (Phase 1)

- **Modul:** ``health_check.py`` im Repo-Root (analog
  ``score_inflation_log.py``, ``push_history.py``).
- **Persistenz:** ``health_check_log.jsonl`` (append-only, JSONL,
  ``HEALTH_CHECK_CUTOFF_DAYS = 30`` Tage Prune). Atomic
  ``tmp + os.replace``-Write beim Pruning; kaputte Zeilen bleiben
  erhalten.
- **Schema-Marker:** ``schema_v: 1`` pro Eintrag.
- **Alarm-Modus:** silent Logging — kein Push in Phase 1. Phase 3
  liest die Datei und sendet Daily-Digest (08:00 UTC, separater
  Workflow).
- **Hook-Points:** Ende ``main()`` in ``generate_report.py`` (nach
  ``process_exit_signals``) und Ende ``main()`` in ``ki_agent.py``
  (nach ``save_state``). Fail-soft via ``run_and_record`` —
  Daily-Run/KI-Agent crashen nie wegen Health-Check.

### 8 State-Invariants (Phase 1 + S8 ab 16.05.2026)

Voller Detailtext + Schwellen-Tabelle in
``docs/health_check_spec.md``. Hier nur Kurz-Übersicht:

| ID | Severity | Was wird geprüft |
|----|----------|------------------|
| S1 | crit | ``score_history.json`` hat heutigen Eintrag pro Top-10-Ticker |
| S2 | crit | ``app_data.setup_scores`` hat ≥ ``HEALTH_CHECK_S2_MIN_TICKERS`` (8) Tickers |
| S3 | crit | Aktive Positionen haben ``current_price != None`` |
| S4 | warn | ``backtest_history`` wächst nur in ``postclose`` (n_appended-Returnwert) |
| S5 | warn | ``score_inflation_log`` bekommt ≥ ``HEALTH_CHECK_S5_MIN_INFLATION_LINES`` (10) neue Zeilen |
| S6 | warn | ``monster_scores`` ≥ ``HEALTH_CHECK_S6_MIN_MONSTER_NONZERO`` (3) Tickers > 0 |
| S7 | warn | ``agent_signals`` ∩ Top-10 ≥ ``HEALTH_CHECK_S7_MIN_AGENT_OVERLAP`` (5) |
| S8 | warn | ``last_digest_sent`` in ``health_check_digest_state.json`` ist ≤ ``HEALTH_CHECK_S8_MAX_AGE_HOURS`` (26) Stunden alt |

**S8** (16.05.2026) erkennt silent Digest-Push-Fails (gestern 15.05.:
ntfy-Send fehlgeschlagen, Workflow lief grün durch, keine Push-Email).
Wenn ``last_digest_sent`` > 26 h alt ist, wurde mindestens ein geplanter
Cron-Slot verpasst — wird im nächsten Daily-Run als warn protokolliert
und damit im nächsten erfolgreichen Digest-Push sichtbar. Erstaufsetz-
sicher: fehlende Datei / ``null``-Wert → kein Fail.

### ki_agent-Tick-Coverage

Der ki_agent-Hook übergibt ``ki_agent_only=True`` —
``evaluate_state_invariants`` prüft dann **nur S2/S3/S6**:

- **S1** Daily-Run-Output (``score_history.json``-Schreibe).
- **S4** Backtest-Append nur im Daily-Run.
- **S5** ``score_inflation_log``-Persistenz nur im Daily-Run.
- **S7** Tautologie — ki_agent schreibt ``agent_signals.json`` selbst
  und arbeitet per Definition auf der Top-10, die er aus
  ``index.html`` zieht.

### Auto-Trigger des KI-Agent (gegen S7-Drift, 14.05.2026)

``daily-squeeze-report.yml`` triggert am Ende automatisch einen
ki_agent-Tick via ``gh workflow run ki_agent.yml --ref main``
(non-blocking, ``continue-on-error: true``). Brauchst Workflow-
Permission ``actions: write`` zusätzlich zu ``contents: write``.

Damit: jeder Daily-Run-Cron und jeder manuelle ``workflow_dispatch``
und jeder Re-Run nach Code-Merge feuert einen frischen ki_agent-Tick
auf die heutige Top-10 → ``agent_signals.json`` enthält im nächsten
Daily-Run die richtigen Tickers → KI-Score auf allen Karten sichtbar.

S7 ist das Restrisiko-Netz (Trigger fehlgeschlagen / ki_agent-Cron
gedropt / ki_agent crasht silent).

### Pflege

- Schwellen-Anpassung: nur in ``config.py`` (``HEALTH_CHECK_*``-
  Block). Code-Logik liest rein über Konstanten.
- Bei neuer State-Invariant S8: ``evaluate_state_invariants``
  erweitern + Konstante + Spec-Tabelle + Mock-Test pro Fail/Pass-
  Pfad ergänzen + diese CLAUDE.md-Tabelle aktualisieren.
- Schema-Änderung am JSONL-Eintrag: ``SCHEMA_V`` in ``health_check.py``
  hochzählen + Migrations-Pfad im Reader dokumentieren (Phase 3
  Digest-Workflow).
- Score-Methodik-Sync **nicht betroffen** — reines Logging-Feature,
  keine Score-/Filter-Logik berührt.

### Phase 2 — Provider-Health (PR 1: Tier 1)

Ergänzt State-Invariants um Provider-Latenz/Coverage-Telemetrie.
Schema gemäß ``docs/health_check_spec.md`` Z. 86–101, persistiert
in ``provider_health.jsonl`` (Append-Only, 30-Tage-Cutoff analog
``health_check_log.jsonl``).

**Helper in ``health_check.py``:**
- ``record_provider_call(provider, tier, latency_ms, http_status,
  item_count, error, coverage_pct, nan_pct, run_phase, run_ts, path)``
- ``prune_provider_log(max_days, path)``
- ``read_all_provider(path)`` (Diagnose-Helper)
- ``SCHEMA_V_PROVIDER = 1``, ``LOG_FILE_PROVIDER =
  "provider_health.jsonl"``

**PR 1 Scope — vier Tier-1-Provider:**

| Provider-Key | Tier | Quelle | Coverage |
|---|---:|---|---|
| ``yahoo_screener`` | 1 | ``get_yahoo_screener_candidates()`` (1 Call/Daily-Run) | Pool-Größe variabel, ``coverage_pct=null`` |
| ``finviz`` | 1 | Aggregat aus ``get_finviz_candidates`` (v161), ``get_finviz_screener_v111`` (v111), ``_fetch_short_float_finviz`` (Quote-Page-Fallback, N×Top-10). Akkumulator ``_FINVIZ_ACCT`` summiert Latenzen + Item-Counts; main() emittiert 1 Zeile am Ende. | ``item_count = len(v161 ∪ v111)``; ``coverage_pct=null`` |
| ``yfinance_batch`` | 1 | ``get_yfinance_batch(pool_tickers)`` (1 Call/Daily-Run, Z. ~14409) | ``coverage_pct = ok_items / pool_size × 100`` |
| ``yfinance_singletons`` | 1 | 2 Emissions: Daily-Run schreibt 1 Zeile für SPY + FX, KI-Agent schreibt 1 Zeile für VIX. Beide Zeilen tragen denselben Provider-Key. | ``coverage_pct`` pro Zeile: Daily-Run 0/50/100 %, KI-Agent 0 oder 100 %. Phase-3-Digest aggregiert. |

**Konstanten in ``config.py``:**
- ``HEALTH_CHECK_PROVIDER_TIER = {"yahoo_screener": 1, "finviz": 1,
  "yfinance_batch": 1, "yfinance_singletons": 1}`` (Tier 2/3 in
  Folge-PRs ergänzt)
- ``HEALTH_CHECK_PROVIDER_EXPECTED = {"yahoo_screener": None,
  "finviz": None, "yfinance_batch": None, "yfinance_singletons": 3}``
  (``None`` = variabel, Coverage übersprungen)

**Pflege:**
- Bei Schema-Erweiterung am ``provider_health.jsonl``-Eintrag:
  ``SCHEMA_V_PROVIDER`` in ``health_check.py`` hochzählen +
  Reader-Migrationspfad dokumentieren.
- Bei neuem Provider: ``HEALTH_CHECK_PROVIDER_TIER``-Eintrag +
  Instrumentierungs-Spot + Mock-Test (Fail/Pass-Pfad).
- ``yfinance_singletons`` ist ein **Multi-Emitter-Provider**
  (Daily-Run + KI-Agent emittieren je eine Zeile). Bei
  Digest-Workflow (Phase 3) muss die Aggregation pro Tag über
  beide Quellen joinen.
- Score-Methodik-Sync **nicht betroffen**.

**Nicht in PR 1:**
- Tier-2 (FINRA, Finnhub, Stockanalysis, EarningsWhispers) — eigener
  Folge-PR. Tier-2-Trigger-Bedingung „3 in Folge" erfordert
  Counter-State in ``agent_state.json[provider_health_state]``.
- Tier-3 (StockTwits, UOA, News-RSS, EDGAR-Set) — eigener Folge-PR.
- Digest-Workflow 08:00 UTC — Phase 3.

### Phase 2 — Provider-Health (PR 2: Tier 2)

Vier Tier-2-Provider ergänzen die Telemetrie. Trigger-Semantik laut
Spec: „warn, erst bei 3-in-Folge-Fail" (Konsekutiv-Counter persistiert
erst in Phase 3 im Digest-Workflow — PR 2 sammelt nur die Rohdaten).

| Provider-Key | Quelle | Special |
|---|---|---|
| ``finra`` | ``fetch_finra_ssr(tickers)`` — KI-Agent-Tick (ki_agent.py:2805), 3 parallele File-Downloads T/T-1/T-2 als Fallback | run_phase=``ki_agent_tick`` (eigene Zeile pro KI-Agent-Tick) |
| ``finnhub`` | ``_fetch_finnhub_next_earnings(ticker, today)`` — Phase-2-Exit pro offene Position. Wrapper via ``_instrument_provider_call(_FINNHUB_ACCT, …)``. main() emittiert Zeile nur wenn ``_FINNHUB_ACCT["calls"] > 0`` (**call_attempted-Gating**). **Skip-Logging-Fix (16.05.2026):** Wenn ``FINNHUB_API_KEY`` nicht im Env steht, prüft ``_fetch_next_earnings_date`` das vorab und überspringt den Wrapper komplett → ``calls`` bleibt 0 → keine Provider-Zeile. Finnhub ist optionale Premium-Quelle; yfinance-Fallback ist Primärpfad seit Inception. Wiedervorlage: Option B aus Diagnose-Memo 16.05.2026 (Finnhub-Code komplett entfernen) bei nächster Aufräum-Welle. | call_attempted-Gating + Env-Key-Gating |
| ``stockanalysis`` | Aggregat aus ``fetch_borrow_metrics`` (SI-Borrow per Top-10) + ``fetch_stockanalysis_si`` (Short-Int per US-Top-10, ThreadPoolExecutor). Wrapper via ``_instrument_provider_call(_STOCKANALYSIS_ACCT, …)``. main() emittiert Zeile nur wenn ``calls > 0``. Latency-Note: Borrow-Pfad misst ``fetch_borrow_metrics`` inkl. IBKR-Fallback (sub-ms-Lookup, akzeptable Näherung). | ENABLED-Gating (``STOCKANALYSIS_BORROW_ENABLED`` + ``STOCKANALYSIS_SI_ENABLED``) |
| ``earningswhispers`` | ``fetch_earningswhispers_rss()`` — 1× pro Daily-Run (Z. 14328). Inline try/finally, ``nan_pct`` aus Items ohne ``date``-Feld berechnet. | ENABLED-Gating (``EARNINGSWHISPERS_ENABLED``); ``nan_pct``-Persistenz |

**Wrapper-Helper ``_instrument_provider_call(acct, fn, *args, **kw)``**
in ``generate_report.py`` ist Wiederverwendung-Bausstein für alle
per-Call-aggregierten Provider (heute Finnhub + Stockanalysis, in
PR 3 voraussichtlich UOA + StockTwits + News-RSS). Pattern:
``try: result = fn(...); return result; except Exception: raised=True; raise;
finally: record(latency, success)``.

**Success-Heuristik im Helper:** Erfolg = nicht raised AND
``result is not None`` AND (für dict/list/tuple/set: nicht leer; sonst:
truthiness). Damit zählt ein ``return None`` oder ``return {}`` aus
einem fail-soft-Pfad als Failure — sauberes Coverage-Signal.

**Konstanten-Erweiterung in ``config.py``:**
- ``HEALTH_CHECK_PROVIDER_TIER`` ergänzt: finra/finnhub/stockanalysis/
  earningswhispers = 2
- ``HEALTH_CHECK_PROVIDER_EXPECTED``: alle vier mit ``None`` (variable
  Coverage)

**Nicht in PR 2:**
- Konsekutiv-Persistenz (``agent_state.json["provider_health_state"]``
  Counter pro Provider) — Phase 3 (Digest-Workflow)
- Push-Aggregation, ntfy-Trigger bei „3-in-Folge"
- Tier 3 (StockTwits, UOA, News-RSS, 4× EDGAR) — PR 3

### Phase 2 — Provider-Health (PR 3: Tier 3) — Phase 2 abgeschlossen

Sieben Tier-3-Provider ergänzen Tier 1 + 2. Klärung 15.05.2026:
getrennte Provider-Keys statt Spec-Wortlaut-Aggregate für saubere
Coverage-Granularität.

**Helper-Refactor** (PR 3): ``_provider_acct_reset``,
``_provider_acct_record``, ``_instrument_provider_call`` von
``generate_report.py`` nach ``health_check.py`` umgezogen (Reuse
von ``ki_agent.py`` aus). Backward-compat-Aliase in
``generate_report.py`` (Underscore-Prefix bleibt für PR-2-Aufrufer).
``instrument_provider_call`` bekommt optional ``success_check``-
Kwarg für Tier-3-Provider mit reichhaltigen fail-soft-Returns
(``(False, "", None)``, ``{"n_total": 0, …}``, ``(0, [], {})``).

| Provider-Key | Quelle | success_check (seit 16.05.2026) |
|---|---|---|
| ``stocktwits`` | ``fetch_stocktwits_sentiment(ticker)`` in ``_process_ticker`` — KI-Agent-Tick. **Return-Semantik:** Dict bei Erfolg (auch ``n_total=0`` = legitim leer), **None bei HTTP 4xx/5xx/Timeout**. | ``r is not None`` |
| ``uoa`` | ``fetch_uoa_signal(ticker)`` in ``_process_ticker`` — Return-Tuple ``(score, drivers, meta)`` | ``bool(r[1])`` (drivers-Liste non-empty signalisiert detected UOA) |
| ``news_rss`` | ``fetch_yahoo_news`` + 5× ``fetch_rss_news`` in ``_process_ticker``. Gemeinsamer Akkumulator → 1 Zeile pro KI-Agent-Tick für alle 6 RSS-Quellen × N Top-10 = 60+ Calls aggregiert | Default (``len(list) > 0``) |
| ``edgar_13f`` | ``fetch_sec_13f`` im Daily-Run-ThreadPool (US-Top-10, ``SEC_13F_ENABLED``-gated). 1 Zeile pro Daily-Run mit ``run_phase=premarket/postclose`` | Default (``str is not None``) |
| ``edgar_8k`` | ``fetch_sec_8k(ticker)`` in ``_process_ticker`` — Return-Tuple ``(has_8k, sec_title, sec_8k_dt)`` bei Erfolg (auch ``(False, "", None)`` = legitim keine 8-K), **None bei HTTP 403/4xx/5xx/Timeout**. | ``r is not None`` |
| ``edgar_form4`` | ``fetch_sec_form4(ticker)`` in ``_process_ticker`` — Return-Tuple ``(has_form4, form4_title)`` bei Erfolg, **None bei Provider-Fehler**. | ``r is not None`` |
| ``edgar_13d_g`` | ``fetch_edgar_filings(top10)`` — 1× pro KI-Agent-Tick. Liste bei Erfolg (auch ``[]`` = legitim leer), **None bei HTTP non-200 / Parse-Error**. | ``r is not None`` |

**Tier-3-success_check-Recalibration (16.05.2026)** — Hintergrund:
vier Tier-3-Provider (edgar_8k/form4/13d_g/stocktwits) zeigten 100 %
Fail-Rate im Provider-Health-Log, weil die alten success_check-
Lambdas „Daten gefunden" prüften statt „Call funktioniert". Legitim
„kein Filing für Ticker X" wurde als Outage gezählt.

**Neue Semantik:** Fetcher returnen **None** bei echtem Provider-
Fehler (HTTP 403/4xx/5xx, Timeout, Parse-Error). Legitim leer returnt
den bestehenden Default (``(False, "", None)`` / ``[]`` / Dict mit
``n_total=0``). success_check vereinfacht auf ``lambda r: r is not None``
— „Call funktioniert" statt „Daten vorhanden". Caller-Pipeline-Werte
bleiben unverändert via Helper ``_unpack_or_default(result, default)``.

**Wirkung:** Provider-Health-Fail-Rate fällt von 100 % auf den
realistischen Outage-Anteil (Erwartung 0–15 %, je nach Wochenende /
Werktag). Digest-Push zählt nur noch echte Provider-Outages.

**Akkumulator-Architektur** (ki_agent.py):
``_STOCKTWITS_ACCT``, ``_UOA_ACCT``, ``_NEWS_RSS_ACCT``,
``_EDGAR_8K_ACCT``, ``_EDGAR_FORM4_ACCT``, ``_EDGAR_13D_G_ACCT`` —
plus ``_reset_tier3_accumulators()`` am main()-Start.
generate_report.py: ``_EDGAR_13F_ACCT`` analog für den Daily-Run-Pfad.

**EDGAR 403-Behandlung**: SEC-Rate-Limit returnt leere Liste/Tuple →
Default-/Custom-success_check markiert als failure → Record-Eintrag
mit ``http_status=null`` + ``error="N/N calls failed"``. Phase-3-
Digest erkennt das als „3-in-Folge"-Trigger-Kandidat.

**Konstanten-Erweiterung in ``config.py``:**
- ``HEALTH_CHECK_PROVIDER_TIER`` ergänzt: alle 7 Tier-3-Keys = 3
- ``HEALTH_CHECK_PROVIDER_EXPECTED``: alle 7 mit ``None`` (Coverage
  pro-Ticker-variabel)

**Phase 2 ist mit PR 3 abgeschlossen.** Folgendes bleibt für Phase 3:
- Konsekutiv-Counter-State in ``agent_state.json["provider_health_state"]``
- Daily-Digest-Workflow 08:00 UTC mit ntfy-Push
- „3-in-Folge"-Trigger-Logik für Tier 2 + 3 Pushes

### Phase 3 — Daily-Digest-Workflow

Liest täglich um **08:47 UTC** die letzten 24 h aus
``health_check_log.jsonl`` + ``provider_health.jsonl``, aggregiert
State-Fails + Provider-Fails (mit Konsekutiv-Counter für Tier-2/3)
und sendet **einen** ntfy-Push.

**Cron-Offset-Historie:**

| Iteration | Offset | Datum | Ergebnis |
|---|---|---|---|
| Spec | ``0 8 * * *`` | initial | — (nie deployt) |
| #1 | ``13 8 * * *`` | bis 15.05.2026 | gedropt — State-Commit 10:37 UTC statt 08:13 UTC (Drift > 2 h) |
| #2 | ``21 8 * * *`` | 15.–16.05.2026 | gedropt — 08:21-Slot am 16.05. komplett ausgefallen |
| **#3** | **``47 8 * * *``** | **ab 16.05.2026** | aktive Version, deutlich näher zur Stunden-Mitte, analog ki_agent-Pattern |

**Fail-Visibility-Fix (16.05.2026):** Wenn ``_ntfy_send`` False zurück-
gibt UND ``NTFY_TOPIC`` gesetzt ist, beendet ``health_check_digest.py``
mit ``sys.exit(1)``. Der Workflow-Commit-Step trägt ``if: always()``,
damit der State trotzdem persistiert wird (Cooldown-Logik bleibt
intakt). GitHub markiert den Run als failed → Email-Notification an
den User. Vermeidet Silent-Fails wie am 15.05.2026 (ntfy-Send
gescheitert, Workflow grün, kein Push, kein Hinweis).

**Unicode-Encoding-Fix (16.05.2026, Punkt D):** Wahre Ursache des
15./16.05.-Silent-Fails war ein ``UnicodeEncodeError`` im requests-
Stack: Title-Strings wie ``⚠️ Health-Check-Digest`` /
``✅ Health-Check OK`` / ``📭 Health-Check ohne Daten`` enthalten
Emojis. HTTP-Header sind per RFC 7230 latin-1-only — Emojis im
``Title``-Header werfen Exception, ``_ntfy_send`` catched generic
``Exception`` → returnt ``False`` ohne Aufklärung. Fix: Wechsel auf
**ntfy JSON-API** (``POST https://ntfy.sh/`` mit ``{topic, title,
message, priority, tags}`` im JSON-Body). JSON ist immer UTF-8,
kein Header-Encoding. ``tags``-String wird zu Array gesplittet
(``"warning,rotating_light"`` → ``["warning", "rotating_light"]``).

**Komponenten:**

| Datei | Zweck |
|---|---|
| ``.github/workflows/health_check_digest.yml`` | Cron + ``workflow_dispatch``, ``timeout-minutes: 3``, ``permissions: contents: write``, JSON-Konflikt-Recovery analog ki_agent |
| ``scripts/health_check_digest.py`` | Tool-Skript (KEIN Laufzeit-Modul). ``main(now_ts, force, dry_run)`` lädt JSONL-Window, aggregiert, sendet ntfy, schreibt state |
| ``health_check.py`` neue Helper | ``aggregate_state_fails``, ``aggregate_provider_fails(counters, tier_map)``, ``format_digest_body`` — pure |
| ``health_check_digest_state.json`` | State-Datei (separater Slot statt ``agent_state.json``, race-frei) |

**Drei Push-Klassen:**

| Bedingung | Title | Priority | Tags |
|---|---|---|---|
| ≥ 1 crit ODER ≥ 3 warn | ``⚠️ Health-Check-Digest`` | ``high`` | ``warning`` |
| Sonst (0 Fails, n_runs > 0) | ``✅ Health-Check OK`` | ``default`` | — |
| ``n_runs == 0`` (leere JSONL) | ``📭 Health-Check ohne Daten`` | ``high`` | ``warning`` |

OK-Push ist **bewusst täglich**, dient als Liveness-Check für die
Push-Pipeline selbst — wenn er ausbleibt weiß Easy, dass Workflow
oder ntfy hakt.

**State-Datei-Schema ``health_check_digest_state.json``:**

```json
{
  "consecutive_failures": {"finra": 0, "finnhub": 3, ...},
  "last_seen":             {"stocktwits": "2026-05-15T07:17:00Z", ...},
  "last_digest_sent":      "2026-05-15",
  "last_successful_run":   "2026-05-15T07:17:00Z"
}
```

Counter-Storage absichtlich in eigener Datei (statt
``agent_state.json["provider_health_state"]`` laut Spec): die
Spec-Variante hätte Race-Conditions zwischen ki_agent (stündliche
Schreibe), Daily-Run (2× pro Tag) und Digest-Workflow (1× pro Tag)
auf demselben State-Slot erzeugt. Die separate Datei wird nur vom
Digest-Workflow geschrieben → write-once-Pattern.

**Schwellen pro Trigger-Klasse:**

| Klasse | Sofort-Trigger | 3-in-Folge-Trigger |
|---|---|---|
| State S1–S3 (crit) | bei einem Vorkommnis | — |
| State S4–S7 (warn) | — | ≥ 3 Vorkommnisse |
| Provider Tier 1 | ``http_status ≠ 200`` ODER ``coverage_pct < 80`` | — |
| Provider Tier 2/3 | — | ``http_status ≠ 200`` ODER ``coverage_pct < 50``, **3 Konsekutiv-Fails** |

**Konstanten in ``health_check.py``:**
- ``DIGEST_COVERAGE_THRESHOLD_TIER1 = 80.0``
- ``DIGEST_COVERAGE_THRESHOLD_TIER23 = 50.0``
- ``DIGEST_CONSECUTIVE_THRESHOLD = 3`` (3-in-Folge für Tier 2/3)
- ``DIGEST_STALE_DAYS = 7`` (Counter-Reset bei stale provider)

**Mehrfach-Trigger-Schutz:** state-Datei merkt sich
``last_digest_sent`` (YYYY-MM-DD). Zweiter Aufruf am selben Tag (z. B.
manueller ``workflow_dispatch``) skipt — außer ``--force``.

**7-Tage-Drift-Schutz:** Provider, die seit > 7 Tagen nicht in der
JSONL aufgetaucht sind (z. B. weil ``STOCKTWITS_ENABLED=False`` für
längere Zeit), bekommen ihren Counter auf 0 zurückgesetzt.

**Tests:** ``scripts/mock_test_digest.py`` — 31 Cases:
Aggregations-Logik per Invariant, Konsekutiv-Counter (3-in-Folge +
Reset-bei-Erfolg + Stale-Drift), Body-Format (4 Klassen),
``_load_jsonl_window`` Cutoff + kaputte-Zeile-Tolerance, Multi-
Trigger-Schutz, ntfy-POST monkey-patched (kein Netzwerk-Call),
YAML-Validität + Cron-Match + Permissions.

**Phase 3 abgeschlossen — Health-Check-Projekt komplett:**

| Phase | PR | Scope |
|---|---|---|
| 1 | #150 | 7 State-Invariants + Auto-Trigger KI-Agent |
| 2 PR 1 | #152 | Tier-1 Provider-Health (yahoo_screener, finviz, yfinance_batch, yfinance_singletons) |
| 2 PR 2 | #153 | Tier-2 Provider-Health (finra, finnhub, stockanalysis, earningswhispers) + ``_instrument_provider_call``-Helper |
| 2 PR 3 | #154 | Tier-3 Provider-Health (7 getrennte Keys: stocktwits, uoa, news_rss + 4× edgar) + ``success_check``-Param |
| 3 | (dieser PR) | Digest-Workflow + Konsekutiv-Counter + Daily-Push |

---

## Session-Handover-Regel

Wenn der User die Sitzung mit „Gute Nacht" (oder Varianten wie „Schlaf gut",
„Bis morgen", „Feierabend gute Nacht") beendet, **automatisch**
`SESSION_HANDOVER.md` im Repo-Root aktualisieren — alte Inhalte komplett
ersetzen, nicht anhängen — und direkt auf `main` committen mit Message
`docs: handover update after session JJJJ-MM-TT`.

### Struktur (genau diese Reihenfolge)

```markdown
# Session-Handover — Stand TT.MM.JJJJ

## Heute implementiert (chronologisch)
- <commit-hash> — <type>: <kurzbeschreibung>
  (Klammer-Detail bei nicht-trivialen Änderungen)

## Aktive Position (im Secret POSITIONS_JSON)
- Tickerliste falls bekannt aus Session-Kontext

## Verifikation ausstehend
- Punkte die nach nächstem Daily / ki_agent-Tick zu prüfen sind

## Geplante Aufgaben
- Konkret formulierte nächste Schritte aus der Session

## Optional / niedrig priorisiert
- Backlog-Punkte

## Architektur-Anker (nicht in CLAUDE.md, wichtig)
- Neue/geänderte Architektur-Invarianten dieser Session
```

### Regeln

- **Reihenfolge fix:** chronologische Commits → Status (Position, Verifikation) → Backlog (Geplant, Optional) → Architektur-Anker.
- **Architektur-Anker** nur ergänzen, wenn diese Session welche eingeführt oder verändert hat. Bei reinen Bugfixes/Doku-Sessions weglassen.
- **Session ohne Commits:** trotzdem aktualisieren — Datum oben + Hinweis „Session ohne Commits, [Stichpunkte zu Diskussionen]". Backlog-Sektionen bleiben gefüllt, falls relevant.
- **Commit-Liste** mit kompletten 7-stelligen Hashes, Type-Prefix wie im echten Commit (`feat:`, `fix:`, `chore:`, `docs:`, `perf:`).
- **Eigenständig committen** — nicht zusätzlich auf User-Bestätigung warten. „Gute Nacht" ist die Bestätigung.
