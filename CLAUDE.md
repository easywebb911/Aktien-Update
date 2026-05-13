# Entwicklungsregeln — Aktien-Update

## Git-Workflow (PR-only)

**ALLE Änderungen** — Code, Doku **und** Config — gehen über Pull Request.

- Branch-Name-Pattern: `claude/<kurze-beschreibung>-<random>`
- User merged manuell via GitHub-Webseite nach Review.
- Direkt-auf-`main` ist **nicht möglich** (Sandbox-Restriktion seit
  09.05.2026: alle `main`-Pushes — auch reine Doku — werden mit
  HTTP 403 abgewiesen). Branch-Pushes funktionieren weiterhin.

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
| `0 10 * * 1-5` (10:00 UTC) | `premarket` | Vorschau, RVOL strukturell unter-skaliert (US-Open ~3,5 h voraus) | Anomaly-Pushes **aktiv** (Aktions-Fenster für die KI-Agent-Ticks) | **kein** Backtest-Eintrag |
| `0 21 * * 1-5` (21:00 UTC) | `postclose` | EOD-konsolidiert = „Wahrheit" | Anomaly-Pushes **aus** (kein abendliches Rauschen) | Backtest-Eintrag wird angelegt |
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
| `schedule` `0 10 * * 1-5` | — | — | `premarket` | — (fester Cron-Mapping) |
| `schedule` `0 21 * * 1-5` | — | — | `postclose` | — (fester Cron-Mapping) |
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
      "entry_snapshot_ts":    "2026-04-27T14:00:00Z"
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
`_compute_exit_state` ein `exit_state`-Dict nach
`app_data["positions"][ticker]["exit_state"]`. Felder:

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

### Pflege

- Bei Schema-Änderung in `closed_trades` (z. B. neues Feld `tags[]`)
  immer simultan: `wlSubmitClose` (Schreiber), `renderTradeJournal`
  (Leser/Anzeige), CLAUDE.md-Schema-Block oben.
- Score-Methodik-Sync-Regel ist **nicht betroffen** — Trade-Journal
  ist außerhalb der Score-Berechnung.
- Migration alter Trades (ohne `max_setup_score` / `duration_days`):
  `renderTradeJournal` rendert `—` bei fehlendem Wert, kein Crash.

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

## Earliness-Indikator (Stufe 1, ohne Score-Effekt)

`compute_earliness_pts(stocks)` misst „leise Akkumulation" — drei
additive Komponenten:

1. **FINRA-Acceleration** (`accel_match`): `si_accelerating` aktiv und
   `change_5d < EARLINESS_MAX_CHANGE_5D_PCT` → `+EARLINESS_ACCEL_PTS` (3).
2. **FINRA-Velocity** (`velocity_match`):
   `si_velocity ≥ EARLINESS_VELOCITY_THRESHOLD` und
   `rsi14 < EARLINESS_MAX_RSI` → `+EARLINESS_VELOCITY_PTS` (2).
3. **Pre-Market-Volume** (`pm_vol_match`):
   `premarket_volume / avg_vol_20d × 100`, gefiltert über
   `change_5d < EARLINESS_MAX_CHANGE_5D_PCT` (Earliness-Charakter wahren)
   **und** `change_overnight ≥ 0` (kein PM-Selloff).
   - `≥ EARLINESS_PM_VOL_HIGH_PCT` (8 %) → `+EARLINESS_PM_VOL_PTS_HIGH` (2)
   - `≥ EARLINESS_PM_VOL_LOW_PCT`  (3 %) → `+EARLINESS_PM_VOL_PTS_LOW`  (1)
   - sonst → 0

Summe gecappt auf `EARLINESS_PTS_MAX = 7` (5 → 7 nach Aufnahme der
PM-Vol-Komponente).

`change_overnight = (cur_open − prev_close) / prev_close × 100`. Bei
fehlendem `cur_open` / `prev_close` / `avg_vol_20d` greift die Bedingung
nicht → `pm_vol_pts = 0` (graceful Fallback, keine Exception).

**Stufe 1 ist reine Persistenz / Beobachtung — `s["score"]` wird
nicht beeinflusst.** Die Werte werden später in Stufe Mittel-2 als
Score-Bonus aktiviert, sobald genug Empirik vorliegt. Bis dahin nur
Logging und optionale UI-Anzeige.

### Datenquelle Pre-Market-Volume

`_fetch_premarket_volumes_batch(tickers) → dict[str, float]` ruft
einmal pro Daily-Run `yf.download(period="1d", interval="1m",
prepost=True)` für alle Top-10-Ticker auf, mappt auf
`America/New_York`-Timezone und summiert das `Volume` zwischen
04:00 und 09:30 ET. Multi- und Single-Ticker-Form werden beide
unterstützt; jeder yfinance-Fehler ergibt `0.0` für den betroffenen
Ticker (Batch-Fail → leeres Dict, Stock-Dict-Default 0.0).

### Felder auf dem Stock-Dict

| Feld | Typ | Bedeutung |
|---|---|---|
| `premarket_volume`     | Float ≥ 0 | PM-Volumen-Snapshot, gesetzt vor `compute_earliness_pts`. Default 0.0 wenn Fetch fehlschlägt. |
| `earliness_pts`        | int 0..`EARLINESS_PTS_MAX` (7) | Summe der drei Sub-Komponenten, gecappt. |
| `earliness_breakdown`  | dict `{accel_match, velocity_match, pm_vol_match}` | **Debug-Feld** — zeigt, *welche* der drei Sub-Bedingungen aktiv waren. Verwechslungsgefahr: nicht mit `_drivers_breakdown` (Drivers-Block-Helper, andere Funktion) verwechseln. |

`earliness_pts` und `earliness_breakdown` werden **immer** geschrieben
(auch bei `pts == 0`), so dass Konsumenten nicht zwischen „nicht
berechnet" und „berechnet, alle Sub-Matches false" unterscheiden müssen.

### Pflege

Bei Aktivierung in Stufe Mittel-2: `earliness_pts` als on-top-Bonus in
`score()` integrieren (analog zu `_float_turnover_pts`), `_compute_sub_scores`
um Sub-Score-Anzeige erweitern, **Score-Methodik-Sektion synchronisieren**,
diese Sektion oben „ohne Score-Effekt" → „mit Score-Effekt" umschreiben.
Beim Hinzufügen weiterer Sub-Komponenten zur Earliness-Logik (z. B.
Insider-Cluster) das `earliness_breakdown`-Dict-Schema und den
PTS_MAX-Cap konsistent in Code, CLAUDE.md und Mock-Tests nachziehen.

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
