### 22.11.2026 — Premarket-Etikett „· Vorschau (Börse offen)“ (1 PR, Easy-Merge)

- `#752` (Branch `claude/premarket-etikett-p4x9`, kein Merge-Hash — Regel a). Easy-Entscheid 22.11.2026.
  Neuer Helfer `_intraday_verspaetet(run_phase, now)` in `generate_report.py`; neues app_data-Feld
  `intraday_verspaetet` (true, wenn ein premarket-Lauf erst zwischen 09:30 und 16:20 ET schreibt).
  Kopfzeilen-Pille: Flag hat Vorrang vor `generated_at` (ki_agent überschreibt es je Tick), Label
  „· Vorschau (Börse offen)“ statt „Intraday-Snapshot“; ohne Flag Altpfad. run_phase, Backtest, Pushes,
  Score, S11 unverändert. Golden neu (nur Pillen-JS). CLAUDE.md-Banner-Abschnitt, open_item
  `zeitplan-verzug-folgen`. Test `scripts/mock_test_runphase_pill.py` (Grenzen, Vorrang, node-Funktionstest).
- **Guardian-Lauf vor Ready:** siehe PR-Bericht.
