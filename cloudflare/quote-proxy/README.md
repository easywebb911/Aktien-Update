# Quote Proxy (Cloudflare Worker)

Live-Quote-Endpoint für den Aktien-Update-Browser. Proxied
`query1.finance.yahoo.com/v8/finance/chart/{ticker}` mit CORS-Header
und 10-s-Edge-Cache.

## Warum v8 statt v7

Yahoo verlangt seit Mai 2026 für den älteren `/v7/finance/quote`-
Endpoint einen **Crumb-Auth-Token** (HTTP 401 ohne). Der v8-Chart-
Endpoint ist weiterhin öffentlich erreichbar und liefert in `meta`
genau die zwei Felder, die wir brauchen:

- `regularMarketPrice` (Live-Preis)
- `chartPreviousClose` (Vortags-Schluss → daraus rechnen wir
  `change_abs` und `change_pct`)

## Architektur

```
Browser  ──GET /?ticker=DMRC──▶  Cloudflare Worker  ──▶  Yahoo v8 chart
   ▲                                    │
   └──── JSON {ticker, price, …} ───────┘
              + CORS-Header
              + Cache-Control: max-age=10
```

**Single-Ticker pro Request** — v8 ist nicht batch-fähig. Für mehrere
Tickers gleichzeitig macht das Frontend `n` separate Fetches in
`Promise.all` (typisch 1 pro offenem Drawer / aufgeklappter Top-10-
Karte, max ~10 parallel).

Free-Tier: 100 000 Req/Tag. Bei 4 Polls/min × 24 h = 5 760 Req pro
aktivem Drawer; mit 4 parallelen Konsumenten ≈ 23 k Req/Tag — locker
im Limit.

## Request

```
GET /?ticker=AAPL
```

Akzeptierte Param-Namen (Legacy-tolerant): `ticker` (kanonisch),
`symbol`, `symbols` (letzteres nimmt nur den ersten Eintrag — kein
Batch).

Sanitize: nur `A–Z`, `0–9`, `.`, `-` durchgelassen.

## Response (200)

```json
{
  "ticker":       "AAPL",
  "price":        195.84,
  "change":       1.23,
  "change_abs":   2.42,
  "volume":       42150300,
  "market_state": "REGULAR",
  "prev_close":   193.42,
  "ts":           "2026-05-13T20:21:30Z"
}
```

| Feld | Quelle in `meta` | Berechnung |
|---|---|---|
| `ticker` | `meta.symbol` | Yahoo-Echo, fallback Request-Param |
| `price` | `meta.regularMarketPrice` | — |
| `prev_close` | `meta.chartPreviousClose` | — |
| `change_abs` | — | `price − prev_close` |
| `change` | — | `(change_abs / prev_close) × 100` (in %, also Frontend-Vertrag wie früher `change_pct`) |
| `volume` | `meta.regularMarketVolume` | — |
| `market_state` | `meta.marketState` | z.B. `"REGULAR"`, `"PRE"`, `"POST"`, `"CLOSED"` |
| `ts` | — | Server-`new Date().toISOString()` zur Cache-Diagnose |

Felder können `null` sein wenn Yahoo sie nicht liefert (z.B. Penny-
Stocks ohne Volume) — Frontend muss `null` graceful behandeln.

## Response (Error)

```json
{"ticker": null, "error": "yahoo_502"}
```

| HTTP | error-Code | Ursache |
|---|---|---|
| 400 | `ticker_param_required` | leer/nur Sonderzeichen |
| 405 | `method_not_allowed`    | POST/PUT/… statt GET |
| 502 | `yahoo_<status>`        | Yahoo blockt / down |
| 502 | `yahoo_no_meta`         | Schema-Drift (`chart.result[0].meta` fehlt) |
| 502 | `proxy_fail:<msg>`      | Worker-Fetch-Exception |

## Deploy

1. **Wrangler installieren** (Node.js 18+):
   ```bash
   npm install -g wrangler
   ```

2. **Login** (öffnet Browser):
   ```bash
   wrangler login
   ```

3. **Deploy**:
   ```bash
   cd cloudflare/quote-proxy
   wrangler deploy
   ```

   Output zeigt die Worker-URL, z. B.
   `https://quote-proxy.<account>.workers.dev`.

4. **Repo-Secret setzen**: GitHub → Settings → Secrets and variables →
   Actions → New repository secret → Name `QUOTE_PROXY_URL`, Wert die
   kopierte Worker-URL (ohne trailing slash).

5. **Nächster Daily-Run** rendert die URL als JS-Konstante in
   `index.html`. Bis dahin: `window.QUOTE_PROXY_URL === ''` → Polling
   ist no-op (eingebrannte Werte bleiben sichtbar).

## Manueller Test

```bash
curl 'https://quote-proxy.<account>.workers.dev/?ticker=AAPL'
```

Erwartet: JSON mit `price`, `change`, `change_abs`. Bei `error`-Feld
siehe Tabelle oben.

## CORS

`worker.js` erlaubt nur `https://easywebb911.github.io` als Origin
(Liste `ALLOWED_ORIGINS`). Bei Custom-Domain die Liste vor dem Deploy
ergänzen.

## Local Dev

```bash
wrangler dev
# → http://localhost:8787/?ticker=AAPL
```

Lokaler Worker hat dieselbe CORS-Logik. Für Browser-Tests gegen
`http://localhost:8000` (Python http-server) `ALLOWED_ORIGINS` um
`http://localhost:8000` ergänzen.

## Update-Pflege

Bei Cloudflare-Worker-Runtime-Upgrades den `compatibility_date` in
`wrangler.toml` bumpen. Yahoo-Endpoint-Schema kann sich ändern —
Frontend schluckt fehlende Felder graceful (`null`), aber bei
strukturellen Breaks (`chart.result[0].meta` weg) liefert der Proxy
`HTTP 502 yahoo_no_meta`; Frontend zeigt `.quote-live-stale` und die
eingebrannten Werte bleiben sichtbar.
