### 18.11.2026 — EDGAR Fix (a): Fehlergrund sichtbar, sec_ok ehrlich, User-Agent aus Secret (1 PR, Easy-Merge)

- `#748` (Branch `claude/edgar-fix-a-cabb`, Branch-Commit `761f0ab4`, kein Merge-Hash — Regel a).
  Sammelauftrag Punkt 1 (Easy 17./18.11.). `ki_agent.fetch_sec_8k`/`fetch_sec_form4`: jeder Status != 200
  ist Provider-Fehler; Grund (Status + Textanfang bzw. Ausnahme) über `_sec_note_error` als erster Fehler
  je Lauf im Akkumulator → `provider_health.jsonl` „error“ + Digest; eine `log.warning` je Lauf und Quelle.
  8-K-Provider-Fehler → `sec_ok` False. `config.SEC_HEADERS` aus dem Secret `EDGAR_USER_AGENT` (feste
  Kontaktadresse aus dem Quelltext entfernt). Test `mock_test_edgar_fix_a.py`, Test 02 der
  Tier-3-Recalibration angepasst. open_item `edgar-abrufe-ausfall-1711` ergänzt.
- Nachtrag 20.11.2026 (gleicher PR): `wiki_attention._default_ua` nennt nur noch Projektname und Repo-URL
  (persönliche Kontaktadresse entfernt); Test `mock_test_attention_wiki.py` prüft „kein @“. Repo-weiter
  Scan nach adressartigen Angaben: kein weiterer privater Fund (Einordnung im PR-Text). Annahme des
  User-Agents durch Wikimedia: aus der Sitzung nicht prüfbar (Proxy), Nachweis im nächsten Lauf.
- **Guardian-Lauf vor Ready:** siehe PR-Bericht.
