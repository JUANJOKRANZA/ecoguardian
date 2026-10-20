/* Audio de Balloon Bash: pistas MP3 HTML5 y efectos reales. */
(function (w) {
  const A = { voiceOn: true, muted: false, activeTrack: null, tensionOn: false, pumpClones: [],
    tracks: {}, effects: {}, masterVolume: 0.34 };
  const base = 'assets/';
  function audio(file, loop, volume) {
    const a = new Audio(base + file); a.preload = 'auto'; a.loop = !!loop; a.volume = volume;
    return a;
  }
  A.tracks.lobby = audio('fun-game.mp3', true, 0.30);
  A.tracks.tension = audio('hitslab-game.mp3', true, 0.23);
  A.tracks.reveal = audio('adventure-loop.mp3', true, 0.20);
  A.effects.pump = audio('balloon-inflate.mp3', false, 0.36);
  // SFX cortos sintetizados solo como respaldo si el navegador no consigue cargar un archivo.
  A.effects.pop = null;
  A.unlock = function () {
    [ ...Object.values(A.tracks), A.effects.pump ].forEach(a => { try { a.load(); } catch (e) {} });
    if (A.activeTrack) A.activeTrack.play().catch(() => {});
  };
  A.setMuted = function (m) {
    A.muted = !!m;
    Object.values(A.tracks).forEach(a => a.muted = A.muted);
    A.effects.pump.muted = A.muted;
    if (A.muted && w.speechSynthesis) w.speechSynthesis.cancel();
  };
  A.bgm = function (on, bpm) {
    if (!on) { Object.values(A.tracks).forEach(a => { a.pause(); }); A.activeTrack = null; return; }
    const wanted = A.tensionOn ? A.tracks.tension : (A.activeTrack === A.tracks.reveal ? A.tracks.reveal : A.tracks.lobby);
    A.playTrack(wanted);
  };
  A.playTrack = function (track) {
    if (!track) return;
    if (A.activeTrack && A.activeTrack !== track) A.activeTrack.pause();
    A.activeTrack = track; track.muted = A.muted;
    if (track.paused) track.play().catch(() => {});
  };
  A.setTempo = function () {};
  A.pump = function () {
    if (A.muted) return;
    // El efecto real dura varios segundos: limitar solapamientos para evitar una masa de audio.
    A.pumpClones = A.pumpClones.filter(a => !a.paused && !a.ended);
    if (A.pumpClones.length >= 2) return;
    const a = A.effects.pump.cloneNode(); a.volume = 0.25; a.muted = A.muted;
    A.pumpClones.push(a); a.play().catch(() => {});
    a.addEventListener('ended', () => { A.pumpClones = A.pumpClones.filter(x => x !== a); }, { once: true });
  };
  A.tension = function (on) {
    A.tensionOn = !!on;
    if (!A.activeTrack || A.activeTrack === A.tracks.lobby || A.activeTrack === A.tracks.tension) {
      if (on) A.playTrack(A.tracks.tension);
      else if (A.activeTrack === A.tracks.tension) A.playTrack(A.tracks.lobby);
    }
  };
  A.pop = function () { A.effectTone('pop'); };
  A.fit = function () { A.effectTone('win'); };
  A.miss = function () { A.effectTone('miss'); };
  A.beep = function () { A.effectTone('beep'); };
  A.effectTone = function (kind) {
    if (A.muted) return;
    try {
      const C = w.AudioContext || w.webkitAudioContext; if (!C) return;
      A.ctx = A.ctx || new C(); if (A.ctx.state === 'suspended') A.ctx.resume();
      const notes = kind === 'win' ? [523,659,784,1046] : kind === 'miss' ? [392,330,262] : kind === 'pop' ? [180,90] : [880];
      notes.forEach((f,i) => { const o=A.ctx.createOscillator(), g=A.ctx.createGain(); o.type='sine'; o.frequency.value=f;
        const t=A.ctx.currentTime+i*0.09; g.gain.setValueAtTime(0.0001,t); g.gain.exponentialRampToValueAtTime(kind==='pop'?0.18:0.06,t+0.015); g.gain.exponentialRampToValueAtTime(0.0001,t+0.16);
        o.connect(g); g.connect(A.ctx.destination); o.start(t); o.stop(t+0.18); });
    } catch(e) {}
  };
  A.say = function (text) {
    if (!text || A.muted || !A.voiceOn || !w.speechSynthesis) return;
    try { w.speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text); u.lang='es-ES'; u.rate=1.02; u.pitch=1; u.volume=1;
      const v=w.speechSynthesis.getVoices().find(x => /^es/i.test(x.lang)); if(v) u.voice=v; w.speechSynthesis.speak(u); } catch(e) {}
  };
  w.Arcade = A;
})(window);
