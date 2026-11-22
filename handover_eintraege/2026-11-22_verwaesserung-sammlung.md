### 22.11.2026 — Verwässerung: stilles Kennzeichen sammeln (1 PR, Easy-Merge, protected-ok b)

- `#?` (Branch `claude/verwaesserung-sammlung-h2k9`, kein Merge-Hash — Regel a). Easy-Entscheid 22.11.2026.
  Neues Backtest-Feld `verwaesserung` (Modul `verwaesserung.py`, pure) aus dem submissions-JSON, das
  `material_8k` je Top-10-Ticker schon holt — kein Abruf. Beide Regel-Entwürfe gezählt (eng `424B5`,
  breit `424B`; ET-Datum D−179…D, Annahme ≤ Report-Zeitpunkt), Rohliste 365 Tage, unbekannt = null +
  Grund. `material_8k`: `HttpStatusError` (Grund `http_<code>` nur im neuen Block, bestehende Gründe
  unverändert), gemerkter CIK-Index → Pool-Schatten `cik`/`cik_grund` (schema_v 2). Digest-Zeile +
  Warnzeile. Eingriff in `_append_backtest_entries` nur die Feldzeile + Log-Zeile (Easy-Freigabe
  protected-ok b). Kein Score-/Filter-/Anzeige-/Push-Effekt, Golden byte-gleich. Wiedervorlage
  08.12.2026 (Formular-Zählung). Test `mock_test_verwaesserung.py`. Beleg: erster Postclose.
