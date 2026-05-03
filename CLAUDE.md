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
      "entry_date":  "YYYY-MM-DD",
      "entry_price": 12.34,
      "shares":      35
    }
  }
}
```

`shares` ist neu gegenüber Phase 1 — wird im Frontend für Stück-Anzeige
genutzt. Die Exit-Score-Logik (`compute_exit_score`) ignoriert `shares`
weiterhin (rechnet nur mit `entry_price`).

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
      "closed_at":       "2026-05-15T18:42:11.000Z"
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

### 401/403-Handler im Workflow-Dispatch

Wenn GitHub-API mit 401/403 antwortet (Token revoked / abgelaufen /
falsche Scopes), wird `_clearAllTokens()` aufgerufen — der User landet
beim nächsten Action-Trigger im Setup-Modal.

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
| Borrow-Rate           | > 50 %/Jahr        | — |
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
