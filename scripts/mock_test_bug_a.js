// Mock-Test für Bug A — thesis/lesson über Validation-Re-Render erhalten.
//
// Spielt in jsdom die ``_POS_PANEL_FORM_STATE``-Logik aus generate_report.py
// nach: Cache-Schreiben durch ``_cacheCloseFormFields`` (vor Re-Render),
// Lesen + HTML-Escape im Render-Pfad, Cache-Clear bei Cancel/Erfolg.
// Die Helper sind hier 1:1 als JS-Strings dupliziert — bei Drift in
// generate_report.py muss dieser Test ebenfalls nachgezogen werden.
//
// Ausführung: ``node scripts/mock_test_bug_a.js``. Exit 0 bei Erfolg,
// 1 bei Assertion-Fail mit Stack-Trace.

'use strict';

const { JSDOM } = require('jsdom');

function assert(cond, msg) {
  if (!cond) throw new Error('ASSERT: ' + msg);
}

function buildDom() {
  const dom = new JSDOM(`<!doctype html><html><body>
    <div id="panel"></div>
  </body></html>`);
  const win = dom.window;

  // Identisch zu generate_report.py — falls dort geändert, hier nachziehen.
  win._POS_PANEL_FORM_STATE = {};

  win._setPanelFormState = function(ticker, state) {
    if (!state) delete win._POS_PANEL_FORM_STATE[ticker];
    else win._POS_PANEL_FORM_STATE[ticker] = state;
  };

  win._cacheCloseFormFields = function(ticker) {
    const th = win.document.getElementById('pos-th-' + ticker);
    const le = win.document.getElementById('pos-le-' + ticker);
    win._setPanelFormState(ticker, {
      thesis: (th && th.value) || '',
      lesson: (le && le.value) || '',
    });
  };

  win._escAttr = function(s) {
    return String(s == null ? '' : s).replace(/[<>&]/g, c => (
      {'<':'&lt;','>':'&gt;','&':'&amp;'})[c]);
  };

  // Minimale Render-Funktion, die den close-form-Block aus
  // buildPositionPanel imitiert — nur die zwei Textareas, die im
  // Bug-A-Pfad relevant sind.
  win.renderCloseForm = function(ticker) {
    const formState = (win._POS_PANEL_FORM_STATE || {})[ticker] || {};
    const thInit = win._escAttr(formState.thesis || '');
    const leInit = win._escAttr(formState.lesson || '');
    const html = `
      <textarea id="pos-th-${ticker}" rows="2">${thInit}</textarea>
      <textarea id="pos-le-${ticker}" rows="2">${leInit}</textarea>
    `;
    win.document.getElementById('panel').innerHTML = html;
  };

  return win;
}

function run() {
  // ── Test 1: Frischer Render — leerer Cache, leere Textareas ──────────
  {
    const win = buildDom();
    win.renderCloseForm('AAPL');
    const th = win.document.getElementById('pos-th-AAPL');
    const le = win.document.getElementById('pos-le-AAPL');
    assert(th && le, 'Textareas nicht gerendert');
    assert(th.value === '', 'thesis sollte initial leer sein, war: ' + JSON.stringify(th.value));
    assert(le.value === '', 'lesson sollte initial leer sein, war: ' + JSON.stringify(le.value));
    console.log('PASS  Test 1: leerer Cache → leere Textareas');
  }

  // ── Test 2: Validation-Fail-Re-Render — User-Eingabe überlebt ────────
  {
    const win = buildDom();
    win.renderCloseForm('TSLA');
    // User tippt These + Lesson
    win.document.getElementById('pos-th-TSLA').value = 'RVOL-Spike + Insider-Buy';
    win.document.getElementById('pos-le-TSLA').value = 'Diesmal Stop tighter setzen';
    // Validation schlägt fehl (z.B. exitDate leer) → cache + re-render
    win._cacheCloseFormFields('TSLA');
    win.renderCloseForm('TSLA');  // simuliert _refreshPositionPanel
    const th = win.document.getElementById('pos-th-TSLA');
    const le = win.document.getElementById('pos-le-TSLA');
    assert(th.value === 'RVOL-Spike + Insider-Buy',
      'thesis verloren, war: ' + JSON.stringify(th.value));
    assert(le.value === 'Diesmal Stop tighter setzen',
      'lesson verloren, war: ' + JSON.stringify(le.value));
    console.log('PASS  Test 2: Validation-Re-Render erhält thesis + lesson');
  }

  // ── Test 3: Cancel löscht Cache ──────────────────────────────────────
  {
    const win = buildDom();
    win.renderCloseForm('NVDA');
    win.document.getElementById('pos-th-NVDA').value = 'Cache mich';
    win._cacheCloseFormFields('NVDA');
    assert(win._POS_PANEL_FORM_STATE['NVDA'].thesis === 'Cache mich',
      'Cache nicht gefüllt');
    // wlCancelCloseForm-Pfad
    win._setPanelFormState('NVDA', null);
    assert(!('NVDA' in win._POS_PANEL_FORM_STATE),
      'Cache nicht gelöscht nach Cancel');
    win.renderCloseForm('NVDA');
    const th = win.document.getElementById('pos-th-NVDA');
    assert(th.value === '', 'thesis sollte nach Cancel leer sein, war: ' + JSON.stringify(th.value));
    console.log('PASS  Test 3: Cancel verwirft Cache');
  }

  // ── Test 4: Erfolgreicher Submit löscht Cache ────────────────────────
  {
    const win = buildDom();
    win.renderCloseForm('AMD');
    win.document.getElementById('pos-th-AMD').value = 'Trade rationale';
    win._cacheCloseFormFields('AMD');
    // wlSubmitClose-Erfolg-Pfad: clear nach gistSave-OK
    win._setPanelFormState('AMD', null);
    assert(!('AMD' in win._POS_PANEL_FORM_STATE),
      'Cache nicht gelöscht nach erfolgreichem Submit');
    console.log('PASS  Test 4: Erfolgreicher Submit verwirft Cache');
  }

  // ── Test 5: HTML-Escape verhindert XSS via thesis ────────────────────
  {
    const win = buildDom();
    win._setPanelFormState('GME', {
      thesis: '<script>alert("x")</script>',
      lesson: 'A & B < C',
    });
    win.renderCloseForm('GME');
    const inner = win.document.getElementById('panel').innerHTML;
    assert(inner.indexOf('<script>alert') === -1,
      'thesis nicht escaped — XSS-Risiko! HTML: ' + inner);
    assert(inner.indexOf('&lt;script&gt;') >= 0,
      'thesis sollte escaped sein, HTML: ' + inner);
    assert(inner.indexOf('A &amp; B &lt; C') >= 0,
      'lesson sollte escaped sein, HTML: ' + inner);
    // textarea liest .value bereits decoded — User sieht den Originaltext
    const th = win.document.getElementById('pos-th-GME');
    assert(th.value === '<script>alert("x")</script>',
      'thesis-Wert nicht roundtrip-fähig: ' + JSON.stringify(th.value));
    console.log('PASS  Test 5: HTML-Escape verhindert XSS, decoded value bleibt');
  }

  // ── Test 6: Pro-Ticker-Isolation ─────────────────────────────────────
  {
    const win = buildDom();
    win._setPanelFormState('A',  { thesis: 'A-thesis', lesson: '' });
    win._setPanelFormState('B',  { thesis: 'B-thesis', lesson: '' });
    win._setPanelFormState('A', null);
    assert(!('A' in win._POS_PANEL_FORM_STATE), 'A sollte gelöscht sein');
    assert(win._POS_PANEL_FORM_STATE['B'].thesis === 'B-thesis',
      'B nicht durch A-Cancel betroffen');
    console.log('PASS  Test 6: Pro-Ticker-Isolation');
  }

  console.log('\nOK: Alle Mock-Tests grün (6/6).');
}

try {
  run();
} catch (e) {
  console.error('FAIL: ' + (e && e.message ? e.message : e));
  if (e && e.stack) console.error(e.stack);
  process.exit(1);
}
