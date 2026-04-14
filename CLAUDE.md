# Entwicklungsregeln — Aktien-Update

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
