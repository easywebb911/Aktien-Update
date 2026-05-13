// quote-proxy — Cloudflare Worker
//
// Proxied Yahoo-Finance-Chart-Endpoint (v8) für den Aktien-Update-Browser.
// Hintergrund: yfinance (Python) wird vom Browser nicht direkt erreicht
// (CORS-Block auf query1.finance.yahoo.com). Worker setzt CORS-Header
// und cached 10 s im Cloudflare-Edge.
//
// Endpoint-Wahl: v8 chart statt v7 quote — v7 verlangt seit Mai 2026
// einen Crumb-Auth-Token und antwortet sonst HTTP 401. v8 ist
// öffentlich erreichbar, liefert `meta` mit `regularMarketPrice` und
// `chartPreviousClose`.
//
// Single-Ticker pro Request — v8 ist nicht batch-fähig. Bei mehreren
// Tickers parallel: Frontend macht n separate Fetches mit Promise.all.
//
// Request:  GET /?ticker=DMRC
// Response: {ticker, price, change, change_abs, volume, market_state,
//            prev_close, ts}
//
// Free-Tier: 100k Req/Tag. Bei 4 Polls/min × 24 h = 5 760 Req/Tag pro
// aktivem Drawer — selbst 4 parallele Drawer = ~23 k Req/Tag, locker
// unter dem Limit.
//
// Deploy: siehe ../README.md.

const YAHOO_CHART_BASE = 'https://query1.finance.yahoo.com/v8/finance/chart/';
const YAHOO_PARAMS     = 'range=1d&interval=1m';
const CACHE_TTL_SECONDS = 10;

// CORS — Erlaubte Origins. GitHub-Pages-URL ist hartcodiert; weitere
// Origins (Custom-Domain, lokale Tests) hier ergänzen. Bei nicht
// erlaubtem Origin wird der erste Listeneintrag als Fallback gesendet
// (bricht Browser-Request, deckt Fehler auf).
const ALLOWED_ORIGINS = [
  'https://easywebb911.github.io',
];

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get('Origin') || '';
    const corsOrigin = ALLOWED_ORIGINS.includes(origin)
      ? origin
      : ALLOWED_ORIGINS[0];

    if (request.method === 'OPTIONS') {
      return new Response(null, {status: 204, headers: corsHeaders(corsOrigin)});
    }
    if (request.method !== 'GET') {
      return jsonError(405, 'method_not_allowed', corsOrigin);
    }

    const url = new URL(request.url);
    // Akzeptierte Param-Namen: ?ticker= (kanonisch), ?symbol= und
    // ?symbols= (Legacy-Aliase aus Frontend-Vor-Versionen).
    const rawTicker = (url.searchParams.get('ticker')
                    || url.searchParams.get('symbol')
                    || url.searchParams.get('symbols')
                    || '').toUpperCase();
    const ticker = rawTicker.replace(/[^A-Z0-9.\-]/g, '').split(',')[0];
    if (!ticker) {
      return jsonError(400, 'ticker_param_required', corsOrigin);
    }

    const cacheKey = new Request(
      `${url.origin}${url.pathname}?ticker=${ticker}`,
      {method: 'GET'},
    );
    const cache = caches.default;
    const cached = await cache.match(cacheKey);
    if (cached) {
      return rewrapWithCors(cached, corsOrigin);
    }

    try {
      const yahooUrl = `${YAHOO_CHART_BASE}${encodeURIComponent(ticker)}?${YAHOO_PARAMS}`;
      const res = await fetch(yahooUrl, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (compatible; aktien-update-quote-proxy/1.0)',
          'Accept':     'application/json',
        },
      });
      if (!res.ok) {
        return jsonError(502, `yahoo_${res.status}`, corsOrigin);
      }
      const data = await res.json();
      const meta = data && data.chart && data.chart.result
                && data.chart.result[0] && data.chart.result[0].meta;
      if (!meta) {
        return jsonError(502, 'yahoo_no_meta', corsOrigin);
      }

      const price      = typeof meta.regularMarketPrice === 'number' ? meta.regularMarketPrice : null;
      const prevClose  = typeof meta.chartPreviousClose === 'number' ? meta.chartPreviousClose : null;
      const volume     = typeof meta.regularMarketVolume === 'number' ? meta.regularMarketVolume : null;
      const marketState = typeof meta.marketState === 'string' ? meta.marketState : null;
      const changeAbs  = (price != null && prevClose != null && prevClose !== 0)
                          ? price - prevClose
                          : null;
      const changePct  = (changeAbs != null && prevClose !== 0)
                          ? (changeAbs / prevClose) * 100
                          : null;

      const body = JSON.stringify({
        ticker:       meta.symbol || ticker,
        price:        price,
        change:       changePct,    // change == Tages-Prozent (Frontend-Vertrag)
        change_abs:   changeAbs,
        volume:       volume,
        market_state: marketState,
        prev_close:   prevClose,
        ts:           new Date().toISOString(),
      });
      const response = new Response(body, {
        status: 200,
        headers: {
          ...corsHeaders(corsOrigin),
          'Content-Type':  'application/json',
          'Cache-Control': `public, max-age=${CACHE_TTL_SECONDS}`,
        },
      });
      // Cache-Kopie ohne CORS-Header (Origin-spezifisch beim Re-Wrap).
      const cacheCopy = new Response(body, {
        status: 200,
        headers: {
          'Content-Type':  'application/json',
          'Cache-Control': `public, max-age=${CACHE_TTL_SECONDS}`,
        },
      });
      ctx.waitUntil(cache.put(cacheKey, cacheCopy));
      return response;
    } catch (err) {
      return jsonError(502, `proxy_fail:${err && err.message ? err.message : 'unknown'}`, corsOrigin);
    }
  },
};

function corsHeaders(origin) {
  return {
    'Access-Control-Allow-Origin':  origin,
    'Access-Control-Allow-Methods': 'GET,OPTIONS',
    'Access-Control-Max-Age':       '600',
    'Vary':                         'Origin',
  };
}

function jsonError(status, code, corsOrigin) {
  return new Response(JSON.stringify({ticker: null, error: code}), {
    status,
    headers: {
      ...corsHeaders(corsOrigin),
      'Content-Type': 'application/json',
    },
  });
}

function rewrapWithCors(cached, corsOrigin) {
  const headers = new Headers(cached.headers);
  for (const [k, v] of Object.entries(corsHeaders(corsOrigin))) {
    headers.set(k, v);
  }
  headers.set('X-Cache', 'HIT');
  return new Response(cached.body, {
    status:  cached.status,
    headers,
  });
}
