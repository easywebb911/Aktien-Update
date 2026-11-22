### 22.11.2026 — squeeze-guardian: fünf Zielfragen + gezieltes Lesen (1 PR, Easy-Merge)

- `#?` (Branch `claude/guardian-ziel-pruefung-q8w2`, kein Merge-Hash — Regel a). Easy-Entscheid 22.11.2026.
  Nur `.claude/agents/squeeze-guardian.md` geändert (144 Zeilen statt 62). Neu: fünf Zielfragen
  a) Ziel belegt, b) echter Beleg bei Datenquellen (zählt nur bei GENAU dieser Abfrage — Endpunkt und
  Parameter; reiner Plan = Warnung „Prüfung im ersten Lauf nötig“), c) stiller Ausfall, d) Öffentlichkeit
  (ganzer Stand, nicht nur Diff), e) Mess-Regeln — je eine Zeile OK / Finding / nicht betroffen; Kontext
  per Grep statt CLAUDE.md + Handover komplett lesen, Zeile „Gelesen“. Beschreibung an die Stehende Regel
  angeglichen, Widerspruch „wie zu fixen“/„keine Fixes“ aufgelöst. STATUS / Findings / Empfehlung
  unverändert (Wächter-Gate G4). Beispiele in der Anleitung bewusst NICHT #735/#748 (die sind nur Probe).
  Proben auf exportiertem Stand ohne `.git`, sonnet und opus: #735 → b) Finding, #748 erster Durchgang →
  d) Finding `wiki_attention.py:78`, #750 → kein Blocker (je ⚠️, Findings nur „Prüfung im ersten Lauf“ +
  Kleinigkeiten). Modell bleibt `sonnet` (Entscheid Easy). Rückweg: Revert der Datei.
