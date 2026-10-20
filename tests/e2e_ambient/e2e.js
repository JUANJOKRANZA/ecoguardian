const { chromium } = require(require('child_process').execSync('npm root -g').toString().trim() + '/playwright');
const assert = require('assert');
const EXE = process.env.CHROMIUM_PATH || undefined;   // opcional: ruta a Chromium/Chrome
const URL = 'http://127.0.0.1:8765/';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.log(...a);

async function newPage(browser, args) {
  const ctx = await browser.newContext({ viewport: { width: 400, height: 700 } });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e))); page.on('response', r => { if (r.status() >= 400 && !r.url().includes('favicon')) errs.push(r.status() + ' ' + r.url()); }); page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errs.push(m.text()); });
  await page.goto(URL); page._errs = errs; return page;
}
const A = (o) => Object.assign({ ui: false, enabled: true, mode: 'normal', defaultVolume: 0.1 }, o || {});
const audioState = page => page.evaluate(() => { const a = [...document.querySelectorAll('audio')]; const x = a[0];
  return { count: a.length, paused: x && x.paused, vol: x && x.volume, loop: x && x.loop, t: x && x.currentTime, dur: x && x.duration, err: x && x.error && x.error.code, ready: x && x.readyState }; });
const panel = page => { const f = page.frames().find(f => f !== page.mainFrame() && f.url().includes('index.html') && f.evaluate); return null; };
async function uiFrame(page) { for (let i = 0; i < 50; i++) { for (const f of page.frames()) { if (f === page.mainFrame()) continue; try { if (await f.evaluate(() => document.getElementById('panel') && document.getElementById('panel').style.display === 'block')) return f; } catch (e) {} } await sleep(100); } throw new Error('panel UI no visible'); }
const txt = (f, id) => f.evaluate(i => document.getElementById(i).textContent, id);

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--autoplay-policy=no-user-gesture-required', '--no-sandbox'] });
  let page = await newPage(browser);
  await page.evaluate(a => { mount('eng', a.e); mount('menu', a.u); }, { e: A(), u: A({ ui: true }) });
  let f = await uiFrame(page);
  log('A1 estado inicial:', await txt(f, 'pill'), '|', await txt(f, 'pct'), '| mensaje:', await txt(f, 'msg'));
  assert.strictEqual(await txt(f, 'pct'), '10 %'); assert.strictEqual(await txt(f, 'pill'), 'Pausado');
  // clic real en el botón
  await f.click('#play'); await sleep(1500);
  let s = await audioState(page); log('A2 tras Reproducir:', JSON.stringify(s));
  assert.strictEqual(s.count, 1); assert.strictEqual(s.paused, false); assert.strictEqual(s.loop, true); assert.ok(Math.abs(s.vol - 0.1) < 0.011); assert.ok(s.t > 0.5, 'avanza');
  assert.strictEqual(await txt(f, 'pill'), 'Reproduciendo');
  await page.screenshot({ path: 'shot_playing_400.png' });
  // B volumen real
  await f.evaluate(() => { const v = document.getElementById('vol'); v.value = 60; v.dispatchEvent(new Event('input', { bubbles: true })); });
  s = await audioState(page); log('B volumen 60 →', s.vol, await txt(f, 'pct')); assert.ok(Math.abs(s.vol - 0.6) < 0.011); assert.strictEqual(await txt(f, 'pct'), '60 %');
  // C cerrar y reabrir menú (iframe UI destruido y recreado) + rerun del engine
  const tBefore = (await audioState(page)).t;
  await page.evaluate(() => unmount('menu')); await sleep(800);
  s = await audioState(page); assert.strictEqual(s.paused, false); assert.ok(s.t > tBefore, 'siguió sonando con el menú cerrado');
  await page.evaluate(a => { mount('menu', a); }, A({ ui: true })); f = await uiFrame(page); await sleep(300);
  log('C reabrir perfil:', await txt(f, 'pill'), '|', await txt(f, 'pct')); assert.strictEqual(await txt(f, 'pill'), 'Reproduciendo'); assert.strictEqual(await txt(f, 'pct'), '60 %');
  s = await audioState(page); assert.strictEqual(s.count, 1); assert.ok(s.t > tBefore + 0.3, 'no se reinició: t=' + s.t);
  // D cambio de página: se destruye y recrea el engine varias veces (reruns)
  for (let i = 0; i < 4; i++) { await page.evaluate(a => { unmount('eng'); mount('eng', a); }, A()); await sleep(250); }
  s = await audioState(page); log('D tras 4 reruns:', JSON.stringify(s)); assert.strictEqual(s.count, 1); assert.strictEqual(s.paused, false); assert.ok(s.t > tBefore + 1);
  // E política de juego: atenuar → pausar → mantener
  await page.evaluate(a => rerender('eng', a), A({ mode: 'duck' })); await page.evaluate(a => rerender('menu', a), A({ ui: true, mode: 'duck' })); await sleep(300);
  s = await audioState(page); log('E1 duck:', s.vol, await txt(f, 'pill')); assert.ok(Math.abs(s.vol - 0.15) < 0.011); assert.strictEqual(s.paused, false);
  await page.evaluate(a => { rerender('eng', a); rerender('menu', Object.assign({}, a, { ui: true })); }, A({ mode: 'pause' })); await sleep(300);
  s = await audioState(page); log('E2 pause:', s.paused, await txt(f, 'pill')); assert.strictEqual(s.paused, true); assert.strictEqual(await txt(f, 'pill'), 'En pausa por el juego');
  await page.evaluate(a => { rerender('eng', a); rerender('menu', Object.assign({}, a, { ui: true })); }, A({ mode: 'normal' })); await sleep(800);
  s = await audioState(page); log('E3 normal (salir del juego):', s.paused, s.vol); assert.strictEqual(s.paused, false); assert.ok(Math.abs(s.vol - 0.6) < 0.011);
  // F pausa del usuario y desactivar
  await f.click('#play'); await sleep(300); s = await audioState(page); assert.strictEqual(s.paused, true); assert.strictEqual(await txt(f, 'pill'), 'Pausado');
  await f.click('#play'); await sleep(600); assert.strictEqual((await audioState(page)).paused, false);
  await page.evaluate(a => { rerender('eng', a); unmount('menu'); }, A({ enabled: false })); await sleep(300);
  assert.strictEqual((await audioState(page)).paused, true); log('F desactivar → detenida');
  await page.evaluate(a => { rerender('eng', a); mount('menu', Object.assign({}, a, { ui: true })); }, A({ enabled: true })); f = await uiFrame(page); await sleep(400);
  s = await audioState(page); log('F2 reactivar:', s.paused, await txt(f, 'pill')); assert.strictEqual(s.paused, true); assert.strictEqual(await txt(f, 'pill'), 'Pausado');
  // G bucle: saltar al final
  await f.click('#play'); await sleep(600);
  await page.evaluate(() => { const a = document.querySelector('audio'); a.currentTime = a.duration - 0.6; }); await sleep(2200);
  s = await audioState(page); log('G bucle: t=', s.t.toFixed(2), 'dur=', s.dur.toFixed(1), 'paused=', s.paused); assert.ok(s.t < 5 && s.paused === false, 'volvió al principio y sigue sonando');
  // H logout: engine con enabled false
  await page.evaluate(a => rerender('eng', a), A({ enabled: false })); await sleep(200); assert.strictEqual((await audioState(page)).paused, true); log('H logout → detenida');
  assert.deepStrictEqual(page._errs, [], 'errores de consola: ' + page._errs.join('|'));
  await page.close();

  // I móvil 320 px
  page = await newPage(browser); await page.setViewportSize({ width: 320, height: 640 });
  await page.evaluate(a => { document.getElementById('menu').style.width = '300px'; mount('eng', a.e); mount('menu', a.u); }, { e: A(), u: A({ ui: true }) });
  f = await uiFrame(page); await f.evaluate(() => {}); await page.evaluate(() => { document.querySelector('#menu iframe').style.width = '300px'; }); await sleep(500);
  await page.screenshot({ path: 'shot_mobile_320.png' }); log('I captura móvil guardada');
  await page.close();

  // J error de carga (404 del MP3)
  page = await newPage(browser); await page.route('**/reciclar_ambiente.mp3', r => r.fulfill({ status: 404, body: 'no' }));
  await page.evaluate(a => { mount('eng', a.e); mount('menu', a.u); }, { e: A(), u: A({ ui: true }) }); f = await uiFrame(page); await f.click('#play'); await sleep(1000);
  log('J 404:', await txt(f, 'pill'), '|', await txt(f, 'msg')); assert.strictEqual(await txt(f, 'pill'), 'Error'); assert.ok((await txt(f, 'msg')).includes('No se pudo cargar')); assert.strictEqual((await audioState(page)).paused !== false, true);
  await page.close(); await browser.close();

  // K navegador con autoplay bloqueado (política por defecto, sin gesto)
  const b2 = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox', '--autoplay-policy=document-user-activation-required'] });
  const ctx2 = await b2.newContext({ viewport: { width: 400, height: 700 } });
  await ctx2.addInitScript(() => {
    document.addEventListener('pointerdown', () => { try { top.__allow = true; } catch (e) {} }, true);
    if (window === window.top) { const orig = HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play = function () { if (!window.__allow) { const e = new Error('autoplay bloqueado (emulado)'); e.name = 'NotAllowedError'; return Promise.reject(e); } return orig.call(this); }; }
  });
  page = await ctx2.newPage(); page._errs = []; await page.goto(URL);
  await page.evaluate(a => { mount('eng', a.e); mount('menu', a.u); }, { e: A(), u: A({ ui: true }) }); f = await uiFrame(page); await sleep(800);
  const r = await page.evaluate(() => window.__egAmbient.play()); await sleep(500);
  s = await audioState(page); log('K sin gesto: play() →', r, '| paused=', s.paused, '|', await txt(f, 'pill'), '|', await txt(f, 'msg'));
  assert.strictEqual(r, false); assert.strictEqual(s.paused, true); assert.strictEqual(await txt(f, 'pill'), 'Bloqueado por el navegador');
  await page.screenshot({ path: 'shot_blocked.png' });
  await f.click('#play'); await sleep(1200); s = await audioState(page); log('K2 tras clic real: paused=', s.paused, await txt(f, 'pill')); assert.strictEqual(s.paused, false);
  await b2.close(); log('E2E COMPLETO OK');
})().catch(e => { console.error('FALLO E2E:', e); process.exit(1); });
