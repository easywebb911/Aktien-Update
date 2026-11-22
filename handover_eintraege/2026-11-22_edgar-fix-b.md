### 22.11.2026 — EDGAR Fix (b): 8-K/Form 4 per CIK, KI-Score unverändert, Rohdaten (1 PR, Easy-Merge)

- `#753` (Branch `claude/edgar-fix-b-r5t1`, kein Merge-Hash — Regel a). Easy-Entscheid 22.11.2026.
  `ki_agent.fetch_sec_8k`/`fetch_sec_form4` lesen aus `data.sec.gov/submissions` per CIK (ein Abruf je
  Ticker, Tickerliste einmal je Lauf) statt `browse-edgar?CIK=<Ticker>`; neues Hilfsmodul `sec_meldungen.py`
  bildet Präfix, Fenster (Annahmezeit UTC) und Titel exakt nach → `compute_signal` identische Punkte (Freeze).
  Keine CIK / Abruf-Fehler → None mit lesbarem Grund. Rohdaten → `sec_meldungen.jsonl` (kein Score-Leser),
  `ki_agent.yml` committet sie. Fix-(a)-Tests an den neuen Abrufweg angepasst; neuer Test
  `scripts/mock_test_edgar_fix_b.py`. CLAUDE.md, open_items `edgar-abrufe-ausfall-1711` und neu
  `ki-score-titel-boni-tot` (Befund + Wiedervorlage nach Freeze-Abschluss).
- **Guardian-Lauf vor Ready:** siehe PR-Bericht.
