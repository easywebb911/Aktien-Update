### 22.11.2026 — Datenprüfung Short Float: FINRA-Antwort gegen Ticker prüfen + HTTP-Status + Totalausfall-Warnung (1 PR, Easy-Merge)

- `#?` (Branch `claude/aktienbasis-ticker-check-m3v6`, kein Merge-Hash — Regel a). Easy-Entscheid 22.11.2026
  (Nebenfund Guardian-Probe #735). `aktienbasis_check.symbol_check`: jede FINRA-Antwortzeile muss zum
  abgefragten Ticker gehören (`_F_SYMBOL`, bisher unbenutzt); fremd → `fremder_ticker`, Feld fehlt →
  `symbol_fehlt`, beides „nicht prüfbar“, nie Kennzeichen, nicht gecacht. HTTP ≠ 200 → `http_<code>` im
  Grund. Cache ohne `symbol_geprueft` wird neu abgerufen. Digest: Warnzeile in den Alarmzeilen, wenn am
  jüngsten Tag ALLE Einträge nicht prüfbar sind (`warn_line`, Lesefehler = Warnung). Dazu Personenname in
  `diagnose_provider_probe.yml:94` durch Platzhalter ersetzt; open_item `sec-13f-count-3` (nur vorgemerkt).
  Kein Score-/Filter-/Anzeige-Effekt außer dem Grund-Text. Test 56 Checks. Beleg: erster Tageslauf nach Merge.
