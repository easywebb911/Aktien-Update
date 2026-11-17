### 17.11.2026 — Block 1 aus Eintragsdateien + Bot-Workflow (1 PR, neuer Workflow, Manual-Merge)

- `#742` (Branch `claude/block1-eintragsdateien-aba4`, Branch-Commit `395939fc`, kein Merge-Hash — Regel a).
  Easy-Entscheid 17.11. (Weg a): Block-1-Einträge sind eigene Dateien in `handover_eintraege/`
  (`JJJJ-MM-TT_<slug>.md`, erste Zeile `### TT.MM.JJJJ — Titel`, PR-Verweis in Backticks). Der neue
  Bot-Workflow `handover_block1.yml` (push auf main, nur `handover_eintraege/**`) erzeugt den Bereich
  zwischen den Marken `BLOCK1-AUTO-START/END` neu (`scripts/handover_block1.py`): nur dieser Bereich,
  Byte-Vergleich davor/danach gegen origin/main, MD5 der Freeze-Blöcke vor/nach, committet nur
  `SESSION_HANDOVER.md`, keine Kette (GITHUB_TOKEN + Pfadfilter). Altbestand unverändert, Marken
  einmalig darüber. pr-checks: Schritt „Handover Block 1“ (Eintragsdatei gültig, kein `#?`, Bereich
  nicht von Hand geändert). Digest-Zeile „Block 1 hängt nach“; Staleness-Check zählt die Dateien mit.
  CLAUDE.md Block-1-Pflicht auf Dateien umgestellt. Nebenbei: `diagnose_provider_probe.yml`
  count=5 → 10 (Nebenbefund `#737`), open_item `edgar-abrufe-ausfall-1711` mit belegter Ursache.
  Test `scripts/mock_test_handover_block1.py`.
- **Guardian-Lauf vor Ready:** siehe PR-Bericht.
