### 18.11.2026 — Block 1: pr-check ohne Basis-Vergleich (Race-Fix, 1 PR)

- `#749` (Branch `claude/block1-prcheck-race-e205`, Branch-Commit `3598c7b7`, kein Merge-Hash — Regel a).
  Befund `#748`: pr-checks prüft den PR gemergt mit dem NEUESTEN main, `base.sha` war aber älter (vor dem
  Bot-Commit zu `#747`) → „PR ändert den erzeugten Bereich“ fälschlich rot. `handover_block1.pr_check`
  vergleicht nicht mehr mit der Basis, sondern prüft, dass der Bereich exakt die Bot-Erzeugung aus den
  Eintragsdateien ist, deren Text er enthält (Hand-Eingriff weiter rot). Test: Race-Fall + Zusatzzeile.
- **Guardian-Lauf vor Ready:** siehe PR-Bericht.
