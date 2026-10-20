// Prueba del controlador de música ambiental con un DOM/Audio simulados (sin navegador real).
const assert = require('assert');
const path = require('path');
const factory = require(path.join('..', 'eco', 'web', 'eco_ambient', 'controller.js'));

function makeEnv(opts) {
  opts = opts || {};
  const audios = [];
  const doc = {
    body: { appendChild(el) { audios.push(el); el.parentNode = this; }, removeChild(el) { const i = audios.indexOf(el); if (i >= 0) audios.splice(i, 1); } },
    documentElement: {}, head: {},
    createElement() {
      const handlers = {};
      const el = {
        paused: true, ended: false, loop: false, volume: 1, src: '', style: {}, attrs: {}, plays: 0,
        setAttribute(k, v) { this.attrs[k] = v; },
        addEventListener(ev, fn) { (handlers[ev] = handlers[ev] || []).push(fn); },
        removeEventListener() {},
        fire(ev) { (handlers[ev] || []).forEach(f => f()); },
        play() {
          this.plays++;
          if (opts.block) { const e = new Error('blocked'); e.name = 'NotAllowedError'; return Promise.reject(e); }
          this.paused = false; this.fire('play'); this.fire('playing'); return Promise.resolve();
        },
        pause() { if (!this.paused) { this.paused = true; this.fire('pause'); } },
        parentNode: null
      };
      return el;
    },
    getElementById(id) { return audios.find(a => a.id === id) || null; },
    querySelectorAll() { return audios.filter(a => a.attrs && a.attrs['data-eg-ambient']); }
  };
  const store = {};
  const fetches = [];
  const win = {
    localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } },
    fetch(url) { fetches.push(url); return opts.failFetch ? Promise.resolve({ ok: false, status: 404 }) : Promise.resolve({ ok: true, blob: () => Promise.resolve(new Blob(['x'])) }); },
    URL: { createObjectURL: () => 'blob:eg-1', revokeObjectURL() {} },
    Blob
  };
  return { win, doc, audios, store, fetches };
}
const cfg = (c, o) => c.configure(Object.assign({ src: '/component/x/reciclar_ambiente.mp3', enabled: true, mode: 'normal', defaultVolume: 0.1 }, o || {}));
const tick = () => new Promise(r => setImmediate(r));

(async () => {
  // 1. Un único <audio loop>, volumen inicial 10 %, sin duplicados al reinstalar
  let e = makeEnv(); let c = factory(e.win, e.doc);
  cfg(c); await c.play();
  assert.strictEqual(e.audios.length, 1); assert.strictEqual(e.audios[0].loop, true);
  assert.strictEqual(e.audios[0].volume, 0.1); assert.strictEqual(c.getState().playing, true);
  assert.strictEqual(factory(e.win, e.doc), c, 'misma versión → misma instancia');
  cfg(c); cfg(c); cfg(c);
  assert.strictEqual(e.audios.length, 1); assert.strictEqual(e.audios[0].plays, 1, 'reruns no reinician la canción');
  assert.strictEqual(e.fetches.length, 1, 'la canción se descarga una sola vez');

  // 2. El volumen cambia el audio real y se persiste
  c.setVolume(0.55); assert.strictEqual(e.audios[0].volume, 0.55);
  assert.strictEqual(JSON.parse(e.store.eg_ambient_v1).volume, 0.55);
  c.setVolume(7); assert.strictEqual(c.getState().volume, 1); c.setVolume(-3); assert.strictEqual(c.getState().volume, 0);
  c.setVolume(0.3);

  // 3. Pausar y reanudar mantiene volumen
  c.pause(); assert.strictEqual(c.getState().playing, false); await c.play();
  assert.strictEqual(c.getState().playing, true); assert.strictEqual(e.audios[0].volume, 0.3);

  // 4. Atenuación en juego y recuperación
  cfg(c, { mode: 'duck' }); assert.strictEqual(e.audios[0].volume, 0.08); assert.strictEqual(c.getState().playing, true);
  cfg(c, { mode: 'normal' }); assert.strictEqual(e.audios[0].volume, 0.3);

  // 5. Pausa por juego y reanudación automática al salir
  cfg(c, { mode: 'pause' }); assert.strictEqual(c.getState().playing, false); assert.strictEqual(c.getState().gamePaused, true);
  cfg(c, { mode: 'normal' }); await tick(); assert.strictEqual(c.getState().playing, true);
  // pausa por juego NO reanuda si el usuario había pausado
  c.pause(); cfg(c, { mode: 'pause' }); cfg(c, { mode: 'normal' }); await tick(); assert.strictEqual(c.getState().playing, false);

  // 6. Desactivar detiene; al reactivar NO suena sola (pide pulsar reproducir)
  await c.play(); cfg(c, { enabled: false }); assert.strictEqual(c.getState().playing, false);
  cfg(c, { enabled: true }); await tick(); assert.strictEqual(c.getState().playing, false);
  assert.strictEqual(await c.play(), true);

  // 7. Reinicio de sesión del navegador: el volumen guardado se recupera
  let e2 = makeEnv(); e2.store.eg_ambient_v1 = JSON.stringify({ volume: 0.42 });
  let c2 = factory(e2.win, e2.doc); cfg(c2); assert.strictEqual(c2.getState().volume, 0.42);

  // 8. Autoplay bloqueado: no se simula reproducción
  let e3 = makeEnv({ block: true }); let c3 = factory(e3.win, e3.doc); cfg(c3);
  assert.strictEqual(await c3.play(), false);
  const s3 = c3.getState(); assert.strictEqual(s3.blocked, true); assert.strictEqual(s3.playing, false);

  // 9. Error de carga → código de error comprensible, sin sonar
  let e4 = makeEnv({ failFetch: true }); let c4 = factory(e4.win, e4.doc); cfg(c4);
  assert.strictEqual(await c4.play(), false); assert.strictEqual(c4.getState().error, 'load'); assert.strictEqual(c4.getState().playing, false);

  // 10. Suscriptor muerto se descarta sin romper a los demás
  let e5 = makeEnv(); let c5 = factory(e5.win, e5.doc); cfg(c5); let n = 0;
  c5.subscribe(() => { throw new Error('dead object'); }); c5.subscribe(() => { n++; });
  c5.setVolume(0.2); c5.setVolume(0.3); assert.ok(n >= 3);

  // 11. Sin sonido si está deshabilitado desde el inicio
  let e6 = makeEnv(); let c6 = factory(e6.win, e6.doc); cfg(c6, { enabled: false });
  assert.strictEqual(await c6.play(), false); assert.strictEqual(e6.audios.length, 0);

  // 12. Arranque automático al entrar; si se bloquea, arranca con el primer gesto; respeta la pausa del usuario
  let e7 = makeEnv(); let c7 = factory(e7.win, e7.doc); cfg(c7, { autoStart: true }); await tick(); await tick();
  assert.strictEqual(c7.getState().playing, true); assert.strictEqual(e7.audios[0].plays, 1);
  cfg(c7, { autoStart: true }); await tick(); assert.strictEqual(e7.audios[0].plays, 1, 'solo una vez');
  c7.pause(); cfg(c7, { autoStart: true }); await tick(); assert.strictEqual(c7.getState().playing, false);
  let e8 = makeEnv({ block: true }); const lst = {}; e8.doc.addEventListener = (ev, fn) => { lst[ev] = fn; }; e8.doc.removeEventListener = () => {};
  let c8 = factory(e8.win, e8.doc); cfg(c8, { autoStart: true }); await tick(); await tick();
  assert.strictEqual(c8.getState().blocked, true); assert.strictEqual(c8.getState().playing, false); assert.ok(lst.pointerdown, 'espera gesto');

  console.log('controlador: 11 grupos de comprobaciones OK');
})().catch(err => { console.error(err); process.exit(1); });
