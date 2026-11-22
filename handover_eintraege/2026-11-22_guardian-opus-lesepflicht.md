### 22.11.2026 — squeeze-guardian: Modell opus + belegbare Pflicht-Leseliste (1 PR, Easy-Merge)

- `#756` (Branch `claude/guardian-opus-lesepflicht-t4n8`, kein Merge-Hash — Regel a). Easy-Entscheid 22.11.2026.
  Nur `.claude/agents/squeeze-guardian.md` (150 Zeilen): `model: opus` (vorher sonnet; Proben #754: opus
  fand tiefer). Pflicht-Leseliste P1–P4 (protected-ok-Label-Regel, Zerstörerische Befehle, §7·0a,
  Docstring `lint_protected_zones.py`) mit festen Such-Befehlen; Zeile „Gelesen“ nennt jede Pflichtstelle
  mit `Datei:Zeile` oder „nicht gefunden: <Befehl> → <Ausgabe>“; „Datei nicht vorhanden“ nur mit gezeigtem
  Befehl. Eine Nachschärf-Runde; Proben #735/#748/#750 erneut mit opus (Ergebnis im PR-Text).
  Hinweis: die Agent-Datei wird beim Sitzungsstart geladen — Änderungen greifen erst in neuen Sitzungen.
  Rückweg: Revert der Datei.
