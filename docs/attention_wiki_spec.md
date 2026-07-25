# Feld-Spec `attention_wiki` (Single-Source für den Bau)

Wikipedia-Pageviews als point-in-time Attention-Proxy (Svoboda „Fuel × Fuse":
SI × Attention). Forward-only Sammlung, kein Score/Filter/Push. Diese Datei ist
Single-Source — Code folgt ihr, nicht umgekehrt.

Machbarkeit belegt durch die read-only Runner-Probe (PR #474, Run 30173587095):
Disambiguierung 9/9 korrekt zur Firma, Finalität T-1 zum postclose final,
keyless + UA-Pflicht hart (ohne UA HTTP 403), Abdeckung ~47 % en-Artikel
(aktuelle Top-10 ~20 % — der ehrliche Normalfall bei tiefen Micro-Caps).

## 0. Prinzipien
- **Forward-only**, nur **postclose-Top-10-Records** in `backtest_history.json`.
  Kein Score, kein Filter, kein Push — reine S10_OBSERVED-Sammlung.
- **en-only**. de bleibt draußen (Probe: de 31 % ⊂ en 47 % → kaum Extra-Deckung;
  ggf. späteres additives Feld).
- **Rohwerte sind die Wahrheit**: `views_*` + `baseline` werden gespeichert;
  `delta_ratio` ist **nur abgeleitet** und jederzeit ohne Neusammlung revidierbar.
- **`null` ≠ `0`** (nicht verhandelbar): siehe §3.

## 1. Zwei Artefakte (Trennung Mapping ↔ Sammlung, Determinismus)

**(A) `wiki_ticker_map.json`** — der **einmal** aufgelöste, eingefrorene
Ticker→Artikel-Anker (nicht täglich neu suchen):

```json
{ "AI": { "qid": "Q104081972", "title": "C3.ai", "resolved_at": "2026-…Z",
          "issuer_verified": true, "company_name_at_resolve": "C3.ai, Inc.",
          "substrate": "en" },
  "WRLD": { "qid": null, "title": null, "resolved_at": "2026-…Z",
            "issuer_verified": false, "company_name_at_resolve": "World Acceptance",
            "substrate": "none", "reason": "no_p249" },
  "VIA": { "qid": null, "title": null, "resolved_at": "2026-…Z",
           "issuer_verified": false, "company_name_at_resolve": "Via Renewables",
           "substrate": "none", "reason": "issuer_mismatch" } }
```

Auflösung **einmal pro Ticker** beim ersten Eintritt in die postclose-Top-10
nach Feature-Start. Danach eingefroren; Re-Resolution nur per explizitem Purge.

**(B) `backtest_history[i].attention_wiki`** — die **täglich** gesammelten
Pageviews, referenziert (A):

```json
"attention_wiki": {
  "substrate":            "en | none",
  "article_qid":          "str | null",
  "article_title":        "str | null",
  "views_t_minus_1":      "int | null",
  "views_t":              "int | null",
  "views_t_backfilled_at":"str ISO | null",
  "baseline_30d_median":  "float | null",
  "baseline_30d_n":       "int | null",
  "delta_ratio":          "float | null"
}
```

- `substrate` — KATEGORIE, aus (A) übernommen.
- `article_qid` / `article_title` — eingefroren aus (A); Titel ist der
  redirect-stabile Anker für die Pageviews-Abfrage.
- `views_t_minus_1` — Pageviews Tag T-1 (Sammel-Tag). `null` bei `none`.
- `views_t` — Pageviews Entry-Tag T, **nachgetragen am T+1**. `null` bis
  Nachtrag / bei `none`.
- `baseline_30d_median` — Median Tages-Views über 30 Kalendertage **bis T-2**.
- `baseline_30d_n` — wie viele der 30 Tage Daten hatten (Datenqualität).
- `delta_ratio` — **abgeleitet**: `views_t_minus_1 / baseline_30d_median`.

## 2. Ticker-Recycling-Guard (VIA-Fall, Pflicht bei Auflösung)
Beim Auflösen in (A) — dreistufig:
1. **Deterministischer Pfad** (Probe 9/9): Wikidata SPARQL, `P249` (ticker) als
   Qualifier auf `P414` (stock exchange), gefiltert auf US-Börsen
   (NASDAQ `Q82059` / NYSE `Q13677` / NYSE American `Q11705394`).
2. **Plausibilisierung gegen `company_name`** des Tools (enriched Name): Label/
   Alias des Wikidata-Items muss fuzzy zum `company_name` passen. **Mismatch →
   REJECT** (`substrate=none`, `issuer_verified=false`, `reason="issuer_mismatch"`).
   Fängt VIA→Viacom (Ticker recycelt; heute Via Renewables).
3. **Defunct-Guard:** Item mit Auflösungsdatum (`P576 dissolved/abolished`) →
   REJECT (strukturell derselbe VIA-Fang).

Nur wenn (1)+(2)+(3) grün UND enwiki-Sitelink existiert → `substrate="en"`,
sonst `substrate="none"` mit `reason`.

## 3. none-Semantik (hart)
- `substrate="none"` → **alle** `views_*` / `baseline_30d_median` /
  `delta_ratio` = **`null`**, **niemals 0**.
- `0` ist reserviert für einen **gemessenen** Null-View-Tag auf einem gemappten
  Artikel (`substrate=en`).
- `substrate="en"` + `views_t_minus_1=null` = „gemappt, aber Fetch diesen Lauf
  fehlgeschlagen" (transient, retrybar). Die zwei Felder (`substrate` + `views`)
  bewahren die Unterscheidung „unbeobachtbar (none)" vs. „observed 0" vs.
  „fetch-fail (en+null)".
- „0-Wert-in-Auswertung vs. exclude" wird **NICHT** hier entschieden — die
  Rohdaten ermöglichen beide Wege bei der H5-Vorregistrierung.

## 4. Fork-1-Sammel-Logik (T-1 sofort + Tag-T-Nachtrag am T+1) — Probe-belegt
- **postclose Tag T** (Record wird geschrieben): sofort `views_t_minus_1` holen
  (T-1 ist zum postclose final). `baseline_30d_median` über 30 Kalendertage
  **bis T-2** (strikt vor T-1, damit T-1 nicht die eigene Baseline kontaminiert).
  `delta_ratio` ableiten.
- **postclose Tag T+1**: **Nachtrag** `views_t` (Entry-Tag-Attention, näher an
  Svobodas „Fuse"; Tag-T ist am T+1 final). Rolling-One-Shot-Backfill der
  gestrigen Records (Muster wie `max_gain_pct`-Fenster, aber einmalig).
- **Point-in-time sauber:** `views_t_minus_1` nutzt nur bei/vor T verfügbare
  Daten; `views_t` ist Attention **zum** Entry-Tag (nicht Zukunft) — beide liegen
  vor dem Forward-Outcome. Kein Look-Ahead.

## 5. Mechanik (Probe-belegt)
- **UA-Pflicht HART:** Fetcher MUSS beschreibenden User-Agent senden (Probe: 403
  ohne). Keyless.
- **Ein Call** je Range (30d-Baseline in einem Call). Mapping-SPARQL nur
  **einmal** pro Ticker (eingefroren) → kein täglicher Kostenpunkt. Konservatives
  Delay zwischen Calls (Actions-IP-Rate-Limit-Schutz über Wochen). Timing trivial
  im postclose-Budget.
- **Fail-soft (6c-Muster):** HTTP≠200/Timeout/Parse-Fehler → betroffenes Feld
  `null`, `substrate` unverändert, **kein Crash**, Log
  `[attention_wiki] SKIP|FAIL <ticker>: reason`.

## 6. Schema-/Governance
- **S10_OBSERVED_FIELDS** (nicht MUSS/LAG — `none` ist legitim, kein
  Enforcement). `views_t_minus_1`: Past ist Past (kein Reifegrad-Filter);
  `views_t` ist am T+1 fällig (weicher Hinweis möglich, kein Fail).
- **Purge-bar:** benannter Key `attention_wiki` + `wiki_ticker_map.json` →
  Purge-Skript-Muster wie 6c/material_8k. Additiv: Alt-Records ohne Feld sind
  null-tolerant.
- **Look-Ahead-Konvention (wie `entry_past_return_5d`):** `attention_wiki` ist
  **reine Observed/Outcome-Persistenz** — **NIEMALS** als Score-/Filter-/Push-
  Feature gelesen. Falls je live: aus Live-Enrichment lesen, nicht aus dem
  Backtest-Feld (Trainings-/Test-Overlap-Guard). Per Grep-Test verankert.

## 7. Offene Kleinpunkte / Populations-Disziplin
- Baseline `median` (robust). `baseline_30d_n < k` → Baseline `null` (zu dünn)
  statt verzerrt.
- `delta_ratio` bei `baseline_median==0`: `null` (undefiniert), nicht ∞.
- Zweiter abgeleiteter Ratio auf `views_t` optional nachrüstbar (Rohwert liegt vor).
- **`none`-Einträge bleiben eingefroren.** Ein einmal als `substrate="none"`
  aufgelöster Ticker wird NICHT bei jedem Lauf neu gesucht (Determinismus + kein
  täglicher SPARQL-Spam). Eine spätere Re-Resolution (z. B. wenn ein Micro-Cap
  inzwischen einen Wikipedia-Artikel bekommen hat) ist **ausschließlich** eine
  explizite, **datierte Populations-Entscheidung** (eigener Lauf/Skript mit
  Datum im Commit/Log), nie ein stiller Auto-Refresh. So bleibt die
  Sammel-Historie reproduzierbar und der Zeitpunkt jeder Map-Änderung
  nachvollziehbar.
