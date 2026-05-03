// Manuell ausführen mit `node scripts/smoke_render.js`.
//
// Smoke-Test für die globalen Render-Funktionen wlRender,
// renderAgentSignals und _applySortMode aus index.html. Lädt die
// generierte index.html in jsdom, ruft die Funktionen mit Mock-Daten
// in fünf Szenarien auf und prüft, dass kein Throw passiert + ein
// paar grundlegende DOM-Invarianten erhalten bleiben.
//
// Voraussetzung: jsdom muss installiert sein (z.B. `npm install jsdom`
// im Repo-Root oder global). Es wird bewusst keine package.json
// angelegt — Skript ist isoliertes Tooling.
//
// Exit-Code 0 bei Erfolg, 1 bei jeder Exception (Stack-Trace nach
// stderr).

'use strict';

const fs = require('fs');
const path = require('path');

let JSDOM, VirtualConsole;
try {
  ({ JSDOM, VirtualConsole } = require('jsdom'));
} catch (e) {
  console.error('FEHLER: jsdom nicht installiert. Bitte `npm install jsdom` ausführen.');
  console.error(e && e.stack ? e.stack : e);
  process.exit(1);
}

const INDEX_HTML_PATH = path.resolve(__dirname, '..', 'index.html');

let HTML_SOURCE;
try {
  HTML_SOURCE = fs.readFileSync(INDEX_HTML_PATH, 'utf8');
} catch (e) {
  console.error(`FEHLER: index.html nicht gefunden unter ${INDEX_HTML_PATH}`);
  console.error(e && e.stack ? e.stack : e);
  process.exit(1);
}

function buildDom(setup, opts) {
  opts = opts || {};
  const virtualConsole = new VirtualConsole();
  // Page-internes console.error/warn nicht in unsere stdout/stderr
  // pumpen — wir prüfen nur, dass keine ungefangene Exception aus
  // den Render-Pfaden hochkommt.
  virtualConsole.on('jsdomError', () => {});
  virtualConsole.on('error', () => {});
  virtualConsole.on('warn', () => {});
  virtualConsole.on('info', () => {});
  virtualConsole.on('log', () => {});

  const dom = new JSDOM(HTML_SOURCE, {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    url: 'https://localhost/',
    virtualConsole,
    beforeParse(window) {
      // Fetch ist standardmäßig rejected — wlLoad fällt damit auf den
      // lokalen Pfad zurück und der app_data.json-Fetch (der intern
      // renderAgentSignals triggert) bleibt inert. Über opts.appDataMock
      // kann ein Szenario eine 200-Response für app_data.json injizieren,
      // um renderAgentSignals aus der gekapselten IIFE heraus mit
      // kontrollierten Daten aufzurufen.
      window.fetch = (url) => {
        if (opts.appDataMock && typeof url === 'string' && url.indexOf('app_data.json') >= 0) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve(opts.appDataMock),
          });
        }
        return Promise.reject(new Error('fetch disabled in smoke test'));
      };
      // jsdom liefert kein window.matchMedia. Die Page benutzt es in
      // mehreren IIFEs (Dark-Mode, isMobile-Detection); ohne Polyfill
      // wirft das eine TypeError, die die restlichen Top-Level-IIFEs
      // im selben <script>-Block killt — inkl. der Watchlist-IIFE,
      // die window.wlRender expose. Minimale Stub-Implementierung.
      if (typeof window.matchMedia !== 'function') {
        window.matchMedia = (query) => ({
          matches: false,
          media: query,
          onchange: null,
          addListener: () => {},
          removeListener: () => {},
          addEventListener: () => {},
          removeEventListener: () => {},
          dispatchEvent: () => false,
        });
      }
      // navigator.serviceWorker wird am Ende des Scripts angefasst —
      // jsdom hat es nicht; ohne Stub würde eine TypeError auftauchen,
      // die aber nach den Render-Funktions-Definitionen kommt und
      // daher die Tests nicht blockiert. Stub trotzdem für saubere
      // Logs.
      if (!window.navigator.serviceWorker) {
        try {
          Object.defineProperty(window.navigator, 'serviceWorker', {
            value: { register: () => Promise.reject(new Error('SW disabled')) },
            configurable: true,
          });
        } catch (_) { /* nicht-fatal */ }
      }
      // Optionale, scenario-spezifische Setup-Hook (z.B. localStorage
      // präparieren, bevor die inline-Scripts der Seite laufen).
      if (typeof setup === 'function') {
        try { setup(window); } catch (e) {
          // Setup-Fehler dem Aufrufer sichtbar machen — geht aber
          // erst nach Load durch das übliche Promise-Channel.
          window.__smokeSetupError = e;
        }
      }
    }
  });

  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error('JSDOM load timeout (10s überschritten)'));
    }, 10000);
    dom.window.addEventListener('load', async () => {
      clearTimeout(timer);
      // DOMContentLoaded-Handler (u.a. auto-wlRender) sind async —
      // ein Tick reicht für Microtasks, +50 ms für eventuelle
      // setTimeout(0)-Ketten in der Page.
      await new Promise(r => setTimeout(r, 50));
      if (dom.window.__smokeSetupError) {
        reject(dom.window.__smokeSetupError);
        return;
      }
      resolve(dom);
    }, { once: true });
  });
}

async function runScenario(name, fn) {
  try {
    await fn();
    console.log(`PASS  ${name}`);
  } catch (e) {
    console.error(`FAIL  ${name}`);
    console.error(e && e.stack ? e.stack : e);
    process.exit(1);
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

(async () => {
  // ── Szenario 1: Frischer Ticker (in keiner Datenquelle) ──────────────
  await runScenario('Frischer Ticker (keine Quelle hat Score)', async () => {
    const dom = await buildDom((win) => {
      win.localStorage.setItem('squeeze_watchlist', JSON.stringify(['ZZZNEW']));
    });
    const win = dom.window;
    assert(typeof win.wlRender === 'function', 'window.wlRender fehlt');
    await win.wlRender();
    const grid = win.document.getElementById('wl-cards');
    assert(grid, '#wl-cards fehlt im DOM');
    assert(grid.innerHTML.includes('ZZZNEW'), 'Tile für frischen Ticker nicht gerendert');
    // Score-Fallback bei fehlenden Daten ist „—".
    assert(grid.innerHTML.includes('—'), 'Score-Platzhalter „—" fehlt');
    dom.window.close();
  });

  // ── Szenario 2: Leere WL_TOP10, leere _WL_CARDS, leere WL_SCORES ─────
  // (Watchlist insgesamt leer)
  await runScenario('Leere Watchlist (alle drei Quellen leer)', async () => {
    const dom = await buildDom((win) => {
      win.localStorage.setItem('squeeze_watchlist', JSON.stringify([]));
    });
    const win = dom.window;
    win._WL_CARDS = {};
    await win.wlRender();
    const grid = win.document.getElementById('wl-cards');
    const cnt  = win.document.getElementById('wl-count');
    assert(grid, '#wl-cards fehlt');
    assert(cnt, '#wl-count fehlt');
    assert(grid.innerHTML.trim() === '', 'Grid sollte leer sein');
    assert(cnt.textContent === '0', `wl-count erwartet "0", war "${cnt.textContent}"`);
    dom.window.close();
  });

  // ── Szenario 3: Alle drei Quellen gefüllt ────────────────────────────
  // XRX ist sowohl in WL_TOP10 (als heutiger Top-10-Eintrag im Render)
  // als auch in WL_SCORES (history-Liste). _WL_CARDS wird zusätzlich
  // mit einem abweichenden Score gesetzt — wlRender soll die
  // Reihenfolge WL_TOP10 → _WL_CARDS → WL_SCORES respektieren und
  // keinen Throw produzieren.
  await runScenario('Alle drei Quellen gefüllt (XRX, INDI, NKTX)', async () => {
    const dom = await buildDom((win) => {
      win.localStorage.setItem(
        'squeeze_watchlist',
        JSON.stringify(['XRX', 'INDI', 'NKTX'])
      );
    });
    const win = dom.window;
    win._WL_CARDS = {
      XRX:  { score: 70.0 },
      INDI: { score: 65.5 },
      NKTX: { score: 50.1 },
    };
    await win.wlRender();
    const grid = win.document.getElementById('wl-cards');
    assert(grid, '#wl-cards fehlt');
    for (const t of ['XRX', 'INDI', 'NKTX']) {
      assert(grid.innerHTML.includes(t), `Tile für ${t} nicht gerendert`);
    }
    dom.window.close();
  });

  // ── Szenario 4: Alle Sortier-Modi (setup, monster, ki) ───────────────
  await runScenario('Sortier-Modi setup/monster/ki', async () => {
    const dom = await buildDom();
    const win = dom.window;
    assert(typeof win._applySortMode === 'function', 'window._applySortMode fehlt');
    for (const mode of ['setup', 'monster', 'ki']) {
      win._applySortMode(mode);
      const grid = win.document.querySelector('.cards-grid');
      assert(grid, '.cards-grid fehlt');
      const scoreBlocks = win.document.querySelectorAll('.score-block');
      // Mindestens ein score-block sollte die aktuelle Sort-Klasse tragen.
      let active = 0;
      scoreBlocks.forEach(sb => {
        if (sb.classList.contains('sort-' + mode)) active += 1;
      });
      assert(
        scoreBlocks.length === 0 || active > 0,
        `Sort-Modus "${mode}" — keine .score-block hat sort-${mode}-Klasse`
      );
    }
    dom.window.close();
  });

  // ── Szenario 5: Push-Silenced-Signal mit Badge-Render ────────────────
  // renderAgentSignals ist innerhalb einer IIFE definiert und wird nur
  // vom internen app_data.json-fetch-Handler aufgerufen — wir routen die
  // Mock-Daten daher über die fetch-Stub. Die Page führt dann den
  // produktiven Render-Pfad aus.
  await runScenario('renderAgentSignals — push_silenced Badge', async () => {
    // Ersten Ticker des Snapshots aus dem statischen HTML herausfischen,
    // damit der Test unabhängig von tagesaktuellen Top-10-Wechseln ist.
    const firstTickerMatch = HTML_SOURCE.match(/<article class="card"[^>]*data-ticker="([^"]+)"/);
    assert(firstTickerMatch, 'Keine data-ticker-Karte im HTML gefunden');
    const ticker = firstTickerMatch[1];
    const dom = await buildDom(null, {
      appDataMock: {
        agent_signals: {
          updated: new Date().toISOString(),
          run_info: { market_phase: 'pre-market', signals_active: 1 },
          signals: {
            [ticker]: {
              score: 55,
              push_silenced: true,
              silenced_reason: 'RSI > 80',
              rvol: 2.4,
            },
          },
        },
        watchlist_cards: {},
        score_history: {},
      },
    });
    // Extra-Tick: fetch().then().then() Kette darf settlen.
    await new Promise(r => setTimeout(r, 100));
    const win = dom.window;
    const card = win.document.querySelector(`.card[data-ticker="${ticker}"]`);
    assert(card, `Karte ${ticker} nicht im DOM`);
    const badge = card.querySelector('.push-silenced-badge');
    assert(badge, `push-silenced-badge nicht im DOM für ${ticker}`);
    assert(
      badge.textContent.includes('Bewegung gelaufen'),
      `Badge-Text unerwartet: "${badge.textContent}"`
    );
    assert(
      badge.textContent.includes('RSI > 80'),
      `Silenced-Reason fehlt im Badge: "${badge.textContent}"`
    );
    dom.window.close();
  });

  console.log('OK: Alle Smoke-Szenarien grün.');
  process.exit(0);
})().catch((e) => {
  console.error('FEHLER: Unerwarteter Fehler im Smoke-Test-Runner.');
  console.error(e && e.stack ? e.stack : e);
  process.exit(1);
});
