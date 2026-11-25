### 25.11.2026 — [Wächter] coverage_history.jsonl auf merge=union (1 PR, Self-Merge)

- `#765` (Branch `claude/waechter-coverage-union-k7m2`, kein Merge-Hash — Regel a). Täglicher Wächter-Lauf.
  Befund: Premarket 24.11.2026 (Run 45452185706) brach beim Commit ab — Rebase-Konflikt in
  `coverage_history.jsonl` mit dem KI-Agent-Lauf 17:45 UTC; der Workflow-Auflöser behandelt nur `*.json`.
  Fix: `.gitattributes` + `coverage_history.jsonl merge=union` (reiner Append, `persist_coverage_row`, kein Prune,
  zwei Schreiber); Test `mock_test_gitattributes_union_merge.py` ergänzt. Kein Workflow, keine Funktion, keine Daten.
  Rückweg: Revert.
