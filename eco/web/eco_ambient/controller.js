/* EcoGuardian · Ambiente — controlador del audio ambiental.
 *
 * Se ejecuta en el DOCUMENTO PRINCIPAL de Streamlit (lo inyecta index.html), no en el iframe del
 * componente: los iframes se destruyen y se recrean en cada rerun, el documento principal no.
 * Aquí vive un ÚNICO <audio id="eg-ambient-audio" loop>, por eso la canción sobrevive a los
 * cambios de página, a los reruns y al abrir/cerrar el menú del perfil.
 * Solo una recarga completa del navegador (F5) lo reinicia, y entonces el navegador exige
 * un nuevo clic en «Reproducir».
 */
function egAmbientFactory(w, d) {
  'use strict';
  var VERSION = 1;
  var AUDIO_ID = 'eg-ambient-audio';
  var STORE_KEY = 'eg_ambient_v1';
  var DEFAULT_VOLUME = 0.10;
  var DUCK_FACTOR = 0.25;

  var existing = w.__egAmbient;
  if (existing && existing.version === VERSION) return existing;      // sin duplicados
  if (existing && typeof existing.destroy === 'function') {
    try { existing.destroy(); } catch (e) {}
  }

  var audio = null, blobUrl = '', loadingPromise = null, listeners = [];
  var domHandlers = [];
  var st = {
    src: '', enabled: false, mode: 'normal', wantPlay: false, blocked: false,
    loading: false, error: '', volume: DEFAULT_VOLUME, volumeFixed: false
  };

  function clamp(v) {
    v = Number(v);
    if (!isFinite(v)) return DEFAULT_VOLUME;
    return Math.round(Math.min(1, Math.max(0, v)) * 100) / 100;
  }
  function readStored() {
    try {
      var raw = w.localStorage.getItem(STORE_KEY);
      if (raw) { var o = JSON.parse(raw); if (o && typeof o.volume === 'number') return clamp(o.volume); }
    } catch (e) {}
    return null;
  }
  function writeStored() {
    try { w.localStorage.setItem(STORE_KEY, JSON.stringify({ volume: st.volume })); } catch (e) {}
  }
  var stored = readStored();
  if (stored !== null) st.volume = stored;

  function effectiveVolume() { return clamp(st.volume * (st.mode === 'duck' ? DUCK_FACTOR : 1)); }

  function snapshot() {
    var playing = !!audio && !audio.paused && !audio.ended;
    return {
      version: VERSION, enabled: st.enabled, mode: st.mode, volume: st.volume,
      effectiveVolume: effectiveVolume(), playing: playing, wantPlay: st.wantPlay,
      gamePaused: st.enabled && st.wantPlay && st.mode === 'pause',
      ducked: st.mode === 'duck', blocked: st.blocked, loading: st.loading,
      error: st.error, volumeFixed: st.volumeFixed
    };
  }
  function emit() {
    var snap = snapshot();
    listeners = listeners.filter(function (fn) {
      try { fn(snap); return true; } catch (e) { return false; }   // iframe destruido → se descarta
    });
  }

  function applyVolume() {
    if (!audio) return;
    var target = effectiveVolume();
    try { audio.volume = target; } catch (e) {}
    // iOS/iPadOS ignoran audio.volume: se avisa para no aparentar un control que no actúa.
    st.volumeFixed = Math.abs(audio.volume - target) > 0.02;
  }

  function setError(code) { st.error = code; st.loading = false; emit(); }

  function ensureAudio() {
    if (audio) return audio;
    var found = d.querySelectorAll('audio[data-eg-ambient]');
    for (var i = 0; i < found.length; i++) {          // elimina restos de versiones anteriores
      try { found[i].pause(); } catch (e) {}
      if (found[i].parentNode) found[i].parentNode.removeChild(found[i]);
    }
    audio = d.createElement('audio');
    audio.id = AUDIO_ID;
    audio.setAttribute('data-eg-ambient', '1');
    audio.setAttribute('aria-hidden', 'true');
    audio.loop = true;
    audio.preload = 'none';
    audio.style.display = 'none';
    (d.body || d.documentElement).appendChild(audio);
    ['play', 'playing', 'pause'].forEach(function (ev) {
      var h = function () { emit(); };
      audio.addEventListener(ev, h); domHandlers.push([ev, h]);
    });
    var onErr = function () {
      var c = audio.error && audio.error.code;
      setError(c === 3 ? 'decode' : (c === 2 ? 'load' : 'load'));
    };
    audio.addEventListener('error', onErr); domHandlers.push(['error', onErr]);
    applyVolume();
    return audio;
  }

  function load() {
    if (blobUrl) return Promise.resolve(true);
    if (loadingPromise) return loadingPromise;
    if (!st.src) { setError('load'); return Promise.resolve(false); }
    ensureAudio();
    st.loading = true; st.error = ''; emit();
    loadingPromise = w.fetch(st.src, { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.blob(); })
      .then(function (b) {
        blobUrl = w.URL.createObjectURL(new w.Blob([b], { type: 'audio/mpeg' }));
        audio.src = blobUrl;
        st.loading = false; applyVolume(); emit();
        return true;
      })
      .catch(function () { loadingPromise = null; setError('load'); return false; });
    return loadingPromise;
  }

  function tryPlay() {
    ensureAudio(); applyVolume();
    var p;
    try { p = audio.play(); } catch (e) { p = Promise.reject(e); }
    return Promise.resolve(p).then(function () {
      st.blocked = false; st.error = ''; emit(); return true;
    }).catch(function (err) {
      var name = err && err.name;
      if (name === 'NotAllowedError') { st.blocked = true; }          // bloqueo de autoplay: no se simula
      else if (name !== 'AbortError') { st.error = (name === 'NotSupportedError') ? 'decode' : 'play'; }
      emit(); return false;
    });
  }

  function play() {
    if (!st.enabled) return Promise.resolve(false);
    st.wantPlay = true; st.blocked = false; st.error = '';
    if (st.mode === 'pause') { emit(); return Promise.resolve(false); }   // se reanuda al terminar el juego
    ensureAudio();
    if (blobUrl) return tryPlay();
    return load().then(function (ok) { return ok ? tryPlay() : false; });
  }

  function pause() {
    st.userPaused = true; st.wantPlay = false; st.blocked = false;
    if (audio) { try { audio.pause(); } catch (e) {} }
    emit();
  }

  function setVolume(v) {
    st.volume = clamp(v); st.touched = true;
    writeStored(); applyVolume(); emit();
    return st.volume;
  }

  var gestureArmed = false;
  function armGesture() {                       // si el navegador bloquea, arranca con el primer toque/clic/tecla
    if (gestureArmed) return; gestureArmed = true;
    var evs = ['pointerdown', 'keydown', 'touchstart'];
    var h = function () {
      evs.forEach(function (e) { d.removeEventListener(e, h, true); }); gestureArmed = false;
      if (st.enabled && !st.userPaused && !(audio && !audio.paused)) play();
    };
    evs.forEach(function (e) { d.addEventListener(e, h, true); });
  }
  function autoStart() {
    play().then(function (ok) { if (!ok && st.blocked && !st.userPaused) armGesture(); });
  }

  function configure(o) {
    o = o || {};
    if (typeof o.src === 'string' && o.src) st.src = o.src;
    if (stored === null && typeof o.defaultVolume === 'number' && !st.touched) {
      st.volume = clamp(o.defaultVolume);
    }
    var enabled = o.enabled !== false;
    var mode = (o.mode === 'duck' || o.mode === 'pause') ? o.mode : 'normal';
    var prevMode = st.mode, prevEnabled = st.enabled;
    st.enabled = enabled; st.mode = mode;
    if (!enabled) {                                   // desactivado expresamente → se detiene
      st.wantPlay = false; st.blocked = false;
      if (audio) { try { audio.pause(); } catch (e) {} }
    } else if (mode === 'pause' && prevMode !== 'pause') {
      if (audio) { try { audio.pause(); } catch (e) {} }   // política de juego; wantPlay se conserva
    } else if (prevMode === 'pause' && mode !== 'pause' && st.wantPlay) {
      ensureAudio(); applyVolume();
      if (blobUrl) tryPlay(); else load().then(function (ok) { if (ok && st.wantPlay) tryPlay(); });
    }
    applyVolume();
    if (o.autoStart && enabled && !st.autoDone && !st.userPaused) { st.autoDone = true; autoStart(); }
    if (prevMode !== mode || prevEnabled !== enabled) emit();
    return snapshot();
  }

  function subscribe(fn) {
    listeners.push(fn);
    try { fn(snapshot()); } catch (e) {}
    return function () { listeners = listeners.filter(function (x) { return x !== fn; }); };
  }

  function destroy() {
    domHandlers.forEach(function (p) { try { audio.removeEventListener(p[0], p[1]); } catch (e) {} });
    if (audio) { try { audio.pause(); } catch (e) {} if (audio.parentNode) audio.parentNode.removeChild(audio); }
    if (blobUrl) { try { w.URL.revokeObjectURL(blobUrl); } catch (e) {} }
    listeners = []; audio = null; blobUrl = '';
  }

  var api = {
    version: VERSION, DEFAULT_VOLUME: DEFAULT_VOLUME, DUCK_FACTOR: DUCK_FACTOR,
    configure: configure, play: play, pause: pause, setVolume: setVolume,
    preload: function () { return load(); }, getState: snapshot, subscribe: subscribe, destroy: destroy
  };
  w.__egAmbient = api;
  return api;
}
egAmbientFactory.__v = 1;
if (typeof module !== 'undefined' && module.exports) module.exports = egAmbientFactory;
