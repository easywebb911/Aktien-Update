# Entwicklungsregeln — Aktien-Update

## Git-Workflow
- Commits immer direkt auf `main`
- Niemals einen neuen Branch erstellen, außer explizit angewiesen
- Kein Pull Request, kein Branch-Umweg

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

### Quelle: GitHub Secret `POSITIONS_JSON`

Beide Workflows (`daily-squeeze-report.yml`, `ki_agent.yml`) bauen die Datei
in einem Step `Build positions.json from secret` direkt vor dem Python-Run:

```yaml
- name: Build positions.json from secret
  env:
    POSITIONS_JSON: ${{ secrets.POSITIONS_JSON }}
  run: |
    if [ -n "$POSITIONS_JSON" ]; then
      echo "$POSITIONS_JSON" > positions.json
    else
      echo '{}' > positions.json
    fi
```

Secret leer → leeres Dict → `process_exit_signals()` no-op.

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

## Anomalie-Push-System

Der KI-Agent feuert ntfy-Pushes **nicht mehr per Monster≥70-Schwelle**,
sondern bei einer von sechs **Anomalien**. Begründung: User checkt die
Top-10 ohnehin manuell — Push ist für Ereignisse, die sonst übersehen
würden. Jeder Trigger-Typ hat einen eigenen Cooldown via Key-Prefix
``anomaly_<trigger>_<ticker>`` in `agent_state.json`.

| Trigger | Bedingung (alle Konstanten in `config.py`) | Severity |
|---|---|---|
| `rvol_explosion`  | RVOL ≥ `ANOMALY_RVOL_TODAY` (5.0) **und** RVOL ≥ `ANOMALY_RVOL_VS_YESTERDAY` × Vortag (2.0×) | high |
| `uoa_extreme`     | Call-Vol/OI ATM ≥ `ANOMALY_UOA_VOL_OI` (10.0) | high |
| `score_jump`      | Setup heute − gestern (raw aus `score_history`) ≥ `ANOMALY_SCORE_JUMP` (15) | medium |
| `gap_combo`       | gap_pct ≥ `ANOMALY_GAP_PCT` (5 %) **und** state==`strong_hold` **und** RVOL ≥ `ANOMALY_GAP_RVOL` (3.0) | high |
| `perfect_storm`   | active_triggers ≥ `ANOMALY_PERFECT_STORM_TRIGGERS` (4/4) | high |
| `monster_backup`  | monster_score ≥ `ANOMALY_MONSTER_BACKUP` (90) — Sicherheitsnetz für extreme Fälle | high |

Cooldown: `ANOMALY_COOLDOWN_HOURS = 6` pro **(Ticker × Trigger-Typ)**.
Mehrere Anomalien gleichen Tickers in einem Run sind möglich.
Earnings-Sofort-Alert hat Vorrang vor Anomalien (kein Doppel-Push).

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

Aufgebaut von `_build_chat_synthesis_ctx()` in `generate_report.py`,
serialisiert als JSON in `STOCKS_CTX` an den Chat:

| Feld | Inhalt |
|---|---|
| `today_top10[]`     | pro Ticker `setup_today`, `setup_yesterday`, `setup_delta`, `monster_today`, `ki_today`, RVOL, RSI, Earnings-Tage, Sektor, SI-Trend |
| `anomalies_today[]` | `{ticker, trigger, detail}` — `score_jump`, `rvol_high`, `earnings_imminent`, `topten_entry`, `topten_exit` |
| `topten_changes`    | `{new: [...], dropped: [...]}` vs. Vortag |
| `positions[]`       | `entry_date`, `entry_price`, `current_price`, `pnl_pct`, `in_top10`, `setup_today`, `monster_today` |
| `today_date` / `yesterday_date` | DE-Datums-Strings, auf die die Diffs sich beziehen |

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

Im Zweifel: lieber Sync mit kurzem Hinweis im Commit-Body als Drift-Risiko.

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
