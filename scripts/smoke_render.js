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

  // ── Szenario 6: Position-Status — Trigger-Block (Phase 2 Stufe 2a) ───
  // Testet ``buildPositionStatus`` mit Mock-exit_state-Daten. Falls die
  // Funktion in der geladenen ``index.html`` (alter Snapshot) noch nicht
  // vorhanden ist, wird sie aus ``generate_report.py`` extrahiert und in
  // jsdom evaluiert — der Test verifiziert immer die ECHTE Implementation,
  // unabhängig vom Stand der ``index.html``.
  await runScenario('buildPositionStatus — Trigger-Block (warn + crit + unavailable)', async () => {
    const dom = await buildDom();
    const win = dom.window;
    // IMMER aus generate_report.py re-evaluieren, damit der Smoke-Test
    // die source-of-truth verifiziert — auch wenn index.html durch Auto-
    // Redeploy zwischenzeitlich eine ältere Version dieser Funktion liefert.
    // Marker-Boundaries wie im Block. ``{{`` / ``}}`` → ``{`` / ``}``
    // (Python-f-String-Brace-Escape).
    const src = fs.readFileSync(
      path.resolve(__dirname, '..', 'generate_report.py'), 'utf8');
    const marker = src.indexOf('// ── Position-Status (Phase 2 — Stufe 2a)');
    const endMarker = src.indexOf('// ── Backtesting-Sektion', marker);
    assert(marker > 0 && endMarker > marker,
      'Position-Status-Block in generate_report.py nicht gefunden');
    const jsRaw = src.slice(marker, endMarker);
    const jsClean = jsRaw.replace(/\{\{/g, '{').replace(/\}\}/g, '}');
    win.eval(jsClean);
    assert(typeof win.buildPositionStatus === 'function',
      'buildPositionStatus nach Eval nicht verfügbar');
    // Alle 3 verfügbaren Trigger aktiv, die 3 unverfügbaren markiert
    win._POSITIONS_DATA = {
      XRX: {
        entry_date: '2026-04-27', entry_price: 4.0, shares: 35,
        exit_state: {
          exit_pressure: 67,
          peak_score_since_entry: 80, peak_pnl_pct_since_entry: 0.27,
          triggers: {
            score_decay: { score: 75, warn: true, crit: false, available: true,
                            details: { drop_3d: 8, drop_5d: 18, drop_7d: null } },
            profit_lock: { score: 100, warn: true, crit: true, available: true,
                            details: { drawdown_from_peak: 0.27,
                                        score_drop_from_peak: 12 } },
            overheated:  { score: 60, warn: true, crit: false, available: true,
                            details: { rsi14: 78, move_2d_pct: 0.22,
                                        move_3d_pct: null } },
            setup_erosion: { score: 0, warn: false, crit: false, available: false,
                              reason: 'kein Entry-Snapshot' },
            catalyst:      { score: 0, warn: false, crit: false, available: false,
                              reason: 'kein Earnings-Lookup' },
            trend_break:   { score: 0, warn: false, crit: false, available: false,
                              reason: 'kein EMA21' },
          },
        },
      },
    };
    const html = win.buildPositionStatus('XRX');
    assert(html && html.length > 0, 'Erwartet Block, bekam leeren String');
    const rowMatches = html.match(/class="ps-row"/g) || [];
    assert(rowMatches.length === 3,
      `Erwartet 3 ps-row (3 verfügbare aktive Trigger), fand ${rowMatches.length}`);
    assert(html.includes('🔴'), 'Crit-Icon fehlt');
    assert(html.includes('🟡'), 'Warn-Icon fehlt');
    assert(html.includes('Score-Verfall'),  'Label score_decay fehlt');
    assert(html.includes('Profit-Lock'),    'Label profit_lock fehlt');
    assert(html.includes('Überhitzung'),    'Label overheated fehlt');
    assert(!html.includes('Setup-Erosion'), 'Unavailable Trigger sichtbar');
    assert(!html.includes('Catalyst'),      'Unavailable Trigger sichtbar');
    assert(!html.includes('Trend-Bruch'),   'Unavailable Trigger sichtbar');
    assert(html.includes('−8 Pkt in 3T'),   'Reason score_decay drop_3d fehlt');
    assert(html.includes('RSI 78'),         'Reason overheated RSI fehlt');
    assert(html.includes('📍 Position-Status'), 'Block-Header fehlt');

    // Phase 2 Stufe 2b-1 — Composite-Zeile "Exit-Druck: X/100"
    assert(html.includes('Exit-Druck: 67/100'),
      `Composite-Zeile fehlt — Mock hatte exit_pressure=67. HTML-Ausschnitt: ${html.slice(0, 500)}`);
    // exit_pressure 67 → mid (30..74) → amber #f59e0b
    assert(html.includes('color:#f59e0b'),
      'Composite-Farbe fehlt für mid-range exit_pressure (erwartet #f59e0b)');
    // ps-pressure-Klasse vorhanden
    assert(html.includes('class="ps-pressure"'), 'CSS-Klasse ps-pressure fehlt');

    // Crit-Range-Test (≥75 → #ef4444)
    win._POSITIONS_DATA.XRX.exit_state.exit_pressure = 88;
    const htmlCrit = win.buildPositionStatus('XRX');
    assert(htmlCrit.includes('Exit-Druck: 88/100'), 'Crit-Range Composite-Zeile fehlt');
    assert(htmlCrit.includes('color:#ef4444'),
      'Crit-Range Farbe fehlt (erwartet #ef4444 bei exit_pressure≥75)');

    // Low-Range-Test (<30 → var(--txt-dim))
    win._POSITIONS_DATA.XRX.exit_state.exit_pressure = 12;
    const htmlLow = win.buildPositionStatus('XRX');
    assert(htmlLow.includes('Exit-Druck: 12/100'), 'Low-Range Composite-Zeile fehlt');
    assert(htmlLow.includes('color:var(--txt-dim)'),
      'Low-Range Farbe fehlt (erwartet var(--txt-dim) bei exit_pressure<30)');

    // Fehlende exit_pressure → Composite-Zeile NICHT gerendert
    delete win._POSITIONS_DATA.XRX.exit_state.exit_pressure;
    const htmlNoEp = win.buildPositionStatus('XRX');
    assert(!htmlNoEp.includes('Exit-Druck:'),
      'Composite-Zeile dürfte ohne exit_pressure NICHT gerendert werden');
    assert(htmlNoEp.includes('class="ps-row"'),
      'Trigger-Rows müssen ohne exit_pressure trotzdem rendern');
    win._POSITIONS_DATA.XRX.exit_state.exit_pressure = 67;   // restore

    // Empty-Pfad 1: Position ohne exit_state → leerer String
    win._POSITIONS_DATA = { XRX: { entry_price: 4.0 } };
    const e1 = win.buildPositionStatus('XRX');
    assert(e1 === '', `Erwartet '' bei fehlendem exit_state, bekam ${JSON.stringify(e1)}`);

    // Empty-Pfad 2: alle Trigger inaktiv (warn=false, crit=false) → leerer String
    win._POSITIONS_DATA = {
      XRX: { exit_state: { triggers: {
        score_decay: { warn: false, crit: false, available: true, details: {} },
        setup_erosion: { warn: false, crit: false, available: false },
      }}},
    };
    const e2 = win.buildPositionStatus('XRX');
    assert(e2 === '', `Erwartet '' bei keinen aktiven Triggern, bekam ${JSON.stringify(e2)}`);

    // Empty-Pfad 3: Ticker nicht in _POSITIONS_DATA → leerer String
    const e3 = win.buildPositionStatus('UNKNOWN');
    assert(e3 === '', `Erwartet '' bei unbekanntem Ticker, bekam ${JSON.stringify(e3)}`);

    dom.window.close();
  });

  console.log('OK: Alle Smoke-Szenarien grün.');
  process.exit(0);
})().catch((e) => {
  console.error('FEHLER: Unerwarteter Fehler im Smoke-Test-Runner.');
  console.error(e && e.stack ? e.stack : e);
  process.exit(1);
});
