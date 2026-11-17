### 17.11.2026 — Erkundungsfeld: Ergebnis der Fehl-Analyse (1 Doku-PR)

- `#743` (Branch `claude/fehlanalyse-ergebnis-42ae`, Branch-Commit `b5a1c925`, kein Merge-Hash — Regel a).
  Ergebnis des Laufs „fehlanalyse“ (21:22 UTC, vollständig) ins open_item `erkundungsfeld-plan`:
  471 Fehlfälle, davon 305 am nachgebildeten Filter (rvol 269), 128 ohne SEC-Aktienzahl, 33 Vorfilter,
  2 Rang > 30. Ursache rvol: Nachbau wendet 1,5 hart an, das Tool nur weich (an 58 von 67 Tagen wurde
  die Top-10 aus allen Kandidaten gefüllt). Ein Fix-Vorschlag + eine Wiederholungsmessung, Entscheid Easy.
  Keine Renditen gelesen. Erster Doku-PR im Eintragsdatei-Verfahren (`#742`). Mit-Fix: Test
  `mock_test_handover_block1` Prüfung 10 verlangte „Bereich == Ordner“ und wäre in jedem PR rot
  (eigene Datei liegt vor dem Bot-Lauf schon im Ordner) — jetzt: Marken gültig, Einträge stammen aus dem Ordner.
- **Guardian-Lauf vor Ready:** siehe PR-Bericht.
