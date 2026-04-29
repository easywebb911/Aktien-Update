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

### Wichtig: niemals `positions.json` committen

`.gitignore` enthält `positions.json`. Bei einem Refactor des `_load_positions()`-Pfads diese Regel beibehalten — die Datei darf nie ins Repo wandern. Bei lokalem Test eine `positions.json` anlegen ist OK; sie wird vom Git ignoriert.
