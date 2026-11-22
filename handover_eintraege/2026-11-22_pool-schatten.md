### 22.11.2026 — Pool-Schatten: alle bewerteten Kandidaten je Postclose-Tag (1 PR, Easy-Merge)

- `#?` (Branch `claude/pool-schatten-k7q2`, kein Merge-Hash — Regel a). Easy-Entscheid 21./22.11.2026.
  Neues Modul `pool_schatten.py`; der Postclose-Lauf schreibt nach dem Backtest-Append ALLE
  Kandidaten aus `enriched` nach `pool_schatten/JJJJ-MM.jsonl` (Rang, Top-10 + Regel, Auswahl-Score,
  rang_konsistent, vintage_zeile, watchlist_bypass, code_sha, Merkmale). Nur lesend, kein Abruf;
  Laufzeit-Gate wie Backtest, idempotent, raise-frei. Digest-Zeile + Warnzeile, Workflow-`git add`,
  CLAUDE.md-Abschnitt, open_item `pool-schatten` mit Nutzungsregel (Suchfeld nur Rang 11+).
  Score/Filter/Auswahl/Anzeige/backtest_history.json unverändert; geschützte Zone unberührt.
  Test `scripts/mock_test_pool_schatten.py`.
- **Guardian-Lauf vor Ready:** siehe PR-Bericht.
