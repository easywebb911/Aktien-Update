### 23.11.2026 — Optionen Handelszeit: Auslöser nach Tages-/KI-Lauf, verkürzte Handelstage, Warnung (1 PR, Easy-Merge)

- `#?` (Branch `claude/options-intraday-ausloeser-w5c3`, kein Merge-Hash — Regel a). Easy-Entscheid 23.11.2026
  (Wächter 23.11.: seit 17.11. keine Messung, Zeitplan-Slots starteten erst 22–01 UTC). `options_intraday.yml`:
  drei Zeitplan-Slots entfernt, neu `workflow_run` nach „Daily Squeeze Report“ und „KI-Agent Squeeze Monitor“
  (completed, main), Hand-Start bleibt; Auslöser steht im Log. Beleg 09.–23.11.: Laufende im Fenster an 11/11
  Handelstagen (Tageslauf allein 8/11). Höchstens 1 Messung je Handelstag (already_done, unverändert).
  `config.US_EARLY_CLOSE_DAYS` (nur 27.11.2026 + 24.12.2026, NYSE-Seite aus der Sitzung nicht erreichbar),
  Fensterende = Schluss − 30 min, wirkt nur im Gate. Digest: Warnung nach 3 Handelstagen ohne Messung
  (Feiertage zählen nicht) und bei fehlendem Jahres-Eintrag der Liste. open_item `options-intraday-erster-lauf`:
  Wiedervorlage nach 10 Handelstagen mit Messung. Datei/Schema unverändert. Beleg: erste echte Messung.
