### 22.11.2026 — Haiku-Parse-Fehler sichtbar + Sammel-open_item ki-score-schwaechen (1 PR, Self-Merge)

- `#?` (Branch `claude/haiku-zaehler-ki-schwaechen-p7r3`, kein Merge-Hash — Regel a). Easy-Entscheid 22.11.2026,
  Vorschlag A aus der Lese-Diagnose (Haiku-Antwort bei max_tokens=50 abgeschnitten, 85–100 % Parse-Fehler
  je Lauf). `ki_agent`: Zähler Versuche/Erfolge je Lauf, Rohantwort-Anfang (80 Zeichen) beim ersten
  Parse-Fehler, provider_health-Zeile `ki_sentiment` (bestehendes Schema, kein Alarm bei reinen
  Parse-Fehlern); Digest-Zeile „🤖 Haiku: X/N Parse-Fehler“. max_tokens/Prompt/Parser/compute_signal
  unverändert — Test vergleicht `claude_sentiment_score` alt (origin/main) gegen neu in 7 Fällen: gleich.
  open_item `ki-score-schwaechen` (a–d + Prüfnotiz: Setup-Freeze speichert geboosteten Score),
  Wiedervorlage Abschluss KI-Score-Freeze.
