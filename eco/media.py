# -*- coding: utf-8 -*-
"""HTML/JS autocontenido para iframes: audio sintetizado, ranking animado, siluetas y avatar narrador.

No se descarga ningún archivo de audio: todo se genera con Web Audio API. Los navegadores solo
reproducen sonido después de un primer gesto del usuario (clic/toque) en la página.
"""
from __future__ import annotations

import json



def _js(value) -> str:
    """JSON seguro para incrustar dentro de <script>."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


# ── Efectos de sonido ─────────────────────────────────────────────────────────
_AUDIO_CORE = """
const AC=window.AudioContext||window.webkitAudioContext;let ctx=null;
function ac(){if(!AC)return null;if(!ctx)ctx=new AC();if(ctx.state==='suspended')ctx.resume().catch(()=>{});return ctx;}
function tone(f,t0,d,type,g,f2){const c=ac();if(!c)return;const o=c.createOscillator(),v=c.createGain();o.type=type||'sine';
o.frequency.setValueAtTime(f,c.currentTime+t0);if(f2)o.frequency.exponentialRampToValueAtTime(f2,c.currentTime+t0+d);
v.gain.setValueAtTime(0.0001,c.currentTime+t0);v.gain.exponentialRampToValueAtTime(g||0.2,c.currentTime+t0+0.02);
v.gain.exponentialRampToValueAtTime(0.0001,c.currentTime+t0+d);o.connect(v).connect(c.destination);o.start(c.currentTime+t0);o.stop(c.currentTime+t0+d+0.05);}
"""

_SFX = {
    "correct": "tone(660,0,.14,'sine',.22);tone(880,.12,.28,'sine',.22);tone(1320,.12,.28,'triangle',.08);",
    "wrong": "tone(180,0,.32,'sawtooth',.14,90);tone(140,.1,.3,'square',.07,70);",
    "tick": "tone(1100,0,.05,'square',.06);",
    "pop": "tone(520,0,.08,'triangle',.15,780);",
    "start": "tone(300,0,.5,'sawtooth',.1,900);tone(600,.35,.35,'triangle',.15,1200);",
    "tie": "tone(520,0,.14,'square',.1);tone(520,.2,.14,'square',.1);tone(780,.4,.3,'triangle',.14);",
    "bell": "tone(1046,0,.35,'sine',.16);tone(1568,.14,.5,'sine',.14);tone(2093,.14,.5,'triangle',.04);",
    "win": "[523,659,784,1047,784,1047].forEach((f,i)=>tone(f,i*.16,.3,'triangle',.2));tone(1319,1,.8,'sine',.18);",
}


def sfx_html(name: str) -> str:
    body = _SFX.get(name, _SFX["pop"])
    return ("<script>(function(){" + _AUDIO_CORE + "function go(){try{" + body + "}catch(e){}}"
            "go();try{window.parent.document.addEventListener('pointerdown',function once(){go();"
            "window.parent.document.removeEventListener('pointerdown',once)},{once:true})}catch(e){}})();</script>")


def leaderboard_html(rows: list[dict], me: str, code: str, show_delta: bool = True) -> tuple[str, int]:
    """Devuelve (html, altura). Las filas se deslizan desde su posición anterior (FLIP) y los puntos suben contando."""
    data = [{"id": r["username"], "name": r["display"], "team": r.get("team", ""), "points": r["points"],
             "delta": r.get("last_delta", 0) if show_delta else 0, "me": r["username"] == me} for r in rows[:10]]
    height = 64 * max(1, len(data)) + 8
    page = """<!doctype html><meta charset='utf-8'><meta name='color-scheme' content='dark'><style>
:root{color-scheme:dark}html,body{margin:0;background:transparent;font-family:'Outfit',system-ui,sans-serif;color:#f4eedb}
#lb{position:relative;width:100%}
.row{position:absolute;left:0;right:0;height:56px;display:flex;align-items:center;gap:12px;padding:0 14px;box-sizing:border-box;border-radius:16px;
background:#10281b;border:1px solid rgba(232,220,194,.28);transition:transform .9s cubic-bezier(.2,.8,.2,1)}
.row.me{border-color:#c5e68a;box-shadow:0 0 0 2px rgba(197,230,138,.35)}
.rk{width:34px;text-align:center;font-weight:800;font-size:1.15rem}.nm{flex:1;min-width:0;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nm small{display:block;font-weight:500;color:#cfd9c7;font-size:.72rem}.pts{font-weight:800;font-variant-numeric:tabular-nums;font-size:1.1rem;color:#c5e68a}
.dl{font-size:.8rem;font-weight:700;color:#0b1f16;background:#c5e68a;border-radius:999px;padding:2px 8px;animation:pop .5s}
@keyframes pop{from{transform:scale(0)}to{transform:scale(1)}}
.r1{background:linear-gradient(90deg,#6b5320,#10281b 70%)}.r2{background:linear-gradient(90deg,#4d5a60,#10281b 70%)}.r3{background:linear-gradient(90deg,#6b4527,#10281b 70%)}
@media(prefers-reduced-motion:reduce){.row{transition:none}}</style><div id='lb'></div><script>
const data=__DATA__,KEY='eg_lb_'+__CODE__,H=64,medals=['🥇','🥈','🥉'];let prev={};
try{prev=JSON.parse(sessionStorage.getItem(KEY)||'{}')}catch(e){}
const box=document.getElementById('lb');box.style.height=(data.length*H)+'px';
data.forEach((d,i)=>{const el=document.createElement('div');el.className='row'+(d.me?' me':'')+(i<3?' r'+(i+1):'');
const mk=(c,t)=>{const s=document.createElement('span');s.className=c;s.textContent=t;return s};
const nm=mk('nm',d.name);if(d.team){const sm=document.createElement('small');sm.textContent=d.team;nm.appendChild(sm)}
const pts=mk('pts','0');el.append(mk('rk',i<3?medals[i]:String(i+1)),nm,pts);if(d.delta>0)el.append(mk('dl','+'+d.delta));
const p=prev[d.id],from=p?p.rank:data.length;el.style.transform='translateY('+(from*H)+'px)';box.appendChild(el);
requestAnimationFrame(()=>requestAnimationFrame(()=>{el.style.transform='translateY('+(i*H)+'px)'}));
const a=p?p.points:0,b=d.points,t0=performance.now();(function step(t){const k=Math.min(1,(t-t0)/900);pts.textContent=Math.round(a+(b-a)*k);if(k<1)requestAnimationFrame(step)})(t0);});
try{const o={};data.forEach((d,i)=>{o[d.id]={rank:i,points:d.points}});sessionStorage.setItem(KEY,JSON.stringify(o))}catch(e){}
</script>"""
    return page.replace("__DATA__", _js(data)).replace("__CODE__", _js(code)), height


# ── Siluetas del reto del globo ───────────────────────────────────────────────
SHAPES = {
    "drop": "<path d='M60 8 C60 8 18 62 18 100 a42 42 0 0 0 84 0 C102 62 60 8 60 8 Z'/>",
    "planet": "<circle cx='60' cy='82' r='54'/>",
    "thermo": "<path d='M48 26 a12 12 0 0 1 24 0 V102 a26 26 0 1 1 -24 0 Z'/>",
    "leaf": "<path d='M20 140 C14 70 56 20 106 16 C108 70 78 128 20 140 Z'/>",
    "bolt": "<path d='M70 8 L24 88 H56 L46 152 L98 66 H66 Z'/>",
    "bottle": "<path d='M50 8 H70 V30 C70 40 90 50 90 70 V140 a10 10 0 0 1 -10 10 H40 a10 10 0 0 1 -10 -10 V70 C30 50 50 40 50 30 Z'/>",
}


def silhouette_svg(shape: str, fraction: float, label: str = "") -> str:
    f = max(0.0, min(1.0, fraction))
    outline = SHAPES.get(shape, SHAPES["drop"])
    y = 160 - 160 * f
    return (f"<svg viewBox='0 0 120 160' width='210' height='280' role='img' aria-label='Silueta inflada al {round(f * 100)} %'>"
            f"<defs><clipPath id='eg-clip'>{outline}</clipPath><linearGradient id='eg-fill' x1='0' y1='0' x2='0' y2='1'>"
            f"<stop offset='0' stop-color='#c5e68a'/><stop offset='1' stop-color='#2f8f5b'/></linearGradient></defs>"
            f"<g clip-path='url(#eg-clip)'><rect x='0' y='0' width='120' height='160' fill='rgba(244,238,219,.08)'/>"
            f"<rect x='0' y='{y:.2f}' width='120' height='{160 * f:.2f}' fill='url(#eg-fill)' style='transition:all .25s'/></g>"
            f"<g fill='none' stroke='#f4eedb' stroke-width='2.6' stroke-linejoin='round'>{outline}</g>"
            f"<text x='60' y='{'92' if f < .92 else '70'}' text-anchor='middle' font-size='17' font-weight='700' fill='#fff' "
            f"stroke='#0b1f16' stroke-width='3' paint-order='stroke'>{label}</text></svg>")


# ── Avatar narrador ───────────────────────────────────────────────────────────
def avatar_html(paragraphs: list[str]) -> str:
    units = []
    for i, para in enumerate(paragraphs):
        for sentence in [s.strip() for s in para.replace("\n", " ").split(". ") if s.strip()]:
            units.append({"p": i, "t": sentence if sentence.endswith((".", "?", "!")) else sentence + "."})
    page = """<!doctype html><meta charset='utf-8'><meta name='color-scheme' content='dark'><style>
:root{color-scheme:dark}*{box-sizing:border-box}html,body{margin:0;background:transparent;font-family:'Outfit',system-ui,sans-serif;color:#f4eedb}
.wrap{display:grid;grid-template-columns:230px 1fr;gap:18px;padding:6px}
@media(max-width:640px){.wrap{grid-template-columns:1fr}}
.stage{background:radial-gradient(circle at 50% 30%,#2a5a3a,#10281b 75%);border:1px solid rgba(232,220,194,.2);border-radius:24px;padding:14px;text-align:center}
svg{width:190px;height:auto;overflow:visible}
.btns{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;justify-content:center}
button{font:600 .95rem 'Outfit',sans-serif;border-radius:12px;border:1px solid rgba(244,238,219,.35);background:rgba(244,238,219,.12);color:#f4eedb;padding:10px 14px;cursor:pointer;min-height:42px}
button.main{background:linear-gradient(180deg,#1f8450,#176b3d);border-color:#4cc088;color:#fff;width:100%;font-size:1rem}
button:hover{filter:brightness(1.15)}button:focus-visible{outline:3px solid #c5e68a;outline-offset:2px}
.ctl{display:flex;gap:8px;align-items:center;font-size:.8rem;color:#cfd9c7;margin-top:8px;justify-content:center}
.tr{background:#10281b;border:1px solid rgba(232,220,194,.2);border-radius:20px;padding:14px 18px;max-height:430px;overflow:auto}
.tr p{margin:0 0 .9rem;line-height:1.65;font-size:1rem;color:#e9e3cd}
.tr span.u{cursor:pointer;border-radius:6px;padding:1px 2px;transition:background .25s}
.tr span.u.on{background:rgba(197,230,138,.3);color:#fff;box-shadow:0 0 0 2px rgba(197,230,138,.25)}
#msg{font-size:.82rem;color:#cfd9c7;margin-top:8px;min-height:1.2em}
@keyframes blink{0%,92%,100%{transform:scaleY(1)}96%{transform:scaleY(.08)}}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
@keyframes talk{0%,100%{transform:scaleY(.4)}50%{transform:scaleY(1.5)}}
@keyframes flap{0%,100%{transform:rotate(0)}50%{transform:rotate(-9deg)}}
@keyframes sway{0%,100%{transform:rotate(-3deg)}50%{transform:rotate(3deg)}}
.owl{animation:bob 3.4s ease-in-out infinite;transform-origin:50% 100%}
.eye{animation:blink 4.5s infinite;transform-box:fill-box;transform-origin:center}
.leaf{animation:sway 3s ease-in-out infinite;transform-box:fill-box;transform-origin:50% 100%}
.jaw{transform-box:fill-box;transform-origin:50% 0}.talking .jaw{animation:talk .28s infinite}
.wing{transform-box:fill-box;transform-origin:50% 10%}.talking .wing{animation:flap .5s infinite}
@media(prefers-reduced-motion:reduce){.owl,.eye,.leaf,.talking .jaw,.talking .wing{animation:none}}
</style>
<div class='wrap'><div class='stage' id='stage'>
<svg viewBox='0 0 200 220' role='img' aria-label='Avatar búho guardián del bosque'><g class='owl'>
<ellipse cx='100' cy='214' rx='52' ry='6' fill='rgba(0,0,0,.35)'/>
<path d='M42 118 C42 70 66 50 100 50 C134 50 158 70 158 118 C158 168 132 206 100 206 C68 206 42 168 42 118 Z' fill='#7a5638'/>
<path d='M70 140 C70 172 84 196 100 196 C116 196 130 172 130 140 C120 150 80 150 70 140 Z' fill='#e8dcc2'/>
<g class='wing'><path d='M44 110 C24 130 28 170 52 184 C56 160 56 136 52 112 Z' fill='#5a3d26'/></g>
<g class='wing' style='transform:scaleX(-1);transform-origin:100px 0'><path d='M44 110 C24 130 28 170 52 184 C56 160 56 136 52 112 Z' fill='#5a3d26'/></g>
<circle cx='78' cy='98' r='27' fill='#f4eedb'/><circle cx='122' cy='98' r='27' fill='#f4eedb'/>
<g class='eye'><circle cx='78' cy='98' r='13' fill='#173a28'/><circle cx='82' cy='93' r='4.5' fill='#fff'/></g>
<g class='eye'><circle cx='122' cy='98' r='13' fill='#173a28'/><circle cx='126' cy='93' r='4.5' fill='#fff'/></g>
<path d='M92 112 L108 112 L100 124 Z' fill='#e8b04b'/>
<g class='jaw'><path d='M93 125 L107 125 L100 134 Z' fill='#c28a57'/></g>
<g class='leaf'><path d='M100 52 C84 40 84 22 100 8 C116 22 116 40 100 52 Z' fill='#79c47e'/><path d='M100 50 V14' stroke='#2f8f5b' stroke-width='2'/></g>
<g class='leaf' style='animation-delay:.4s'><path d='M80 56 C64 50 58 36 66 22 C80 30 86 44 80 56 Z' fill='#5d8f4a'/></g>
<g class='leaf' style='animation-delay:.8s'><path d='M120 56 C136 50 142 36 134 22 C120 30 114 44 120 56 Z' fill='#5d8f4a'/></g>
</g></svg>
<div class='btns'><button class='main' id='play'>🔊 Escuchar explicación del avatar</button>
<button id='pause'>⏸ Pausar</button><button id='stop'>■ Detener</button></div>
<div class='ctl'><label for='rate'>Velocidad</label><input id='rate' type='range' min='.7' max='1.3' step='.05' value='.95'></div>
<div id='msg' aria-live='polite'>Pulsa el botón y escucha al guardián.</div></div>
<div class='tr' id='tr' tabindex='0' aria-label='Transcripción de la explicación'></div></div>
<script>
const PARAS=__PARAS__,UNITS=__UNITS__,synth=window.speechSynthesis;
const tr=document.getElementById('tr'),stage=document.getElementById('stage'),msg=document.getElementById('msg');
const pEls=PARAS.map(()=>{const p=document.createElement('p');tr.appendChild(p);return p}),uEls=[];
UNITS.forEach((u,i)=>{const s=document.createElement('span');s.className='u';s.textContent=u.t+' ';s.onclick=()=>{if(synth)begin(i)};pEls[u.p].appendChild(s);uEls.push(s)});
let cur=0,playing=false,paused=false;
function voice(){const v=synth.getVoices();return v.find(x=>/^es[-_]CO/i.test(x.lang))||v.find(x=>/^es[-_](MX|419|US)/i.test(x.lang))||v.find(x=>/^es/i.test(x.lang))||null}
function mark(i){uEls.forEach(e=>e.classList.remove('on'));if(uEls[i]){uEls[i].classList.add('on');const t=uEls[i].offsetTop-tr.clientHeight/3;tr.scrollTo({top:Math.max(0,t),behavior:'smooth'})}}
function talk(on){stage.classList.toggle('talking',on)}
function say(i){if(!playing)return;if(i>=UNITS.length){end('Fin de la explicación. ¡Gracias por escuchar!');return}
cur=i;mark(i);const u=new SpeechSynthesisUtterance(UNITS[i].t),v=voice();if(v){u.voice=v;u.lang=v.lang}else u.lang='es-CO';
u.rate=parseFloat(document.getElementById('rate').value);u.onstart=()=>talk(true);
u.onend=()=>{if(playing&&!paused)say(i+1)};u.onerror=e=>{if(e.error!=='interrupted'&&e.error!=='canceled'){talk(false);msg.textContent='Tu navegador no pudo reproducir la voz.'}};synth.speak(u)}
function begin(i){if(!synth){msg.textContent='Este navegador no admite locución de voz; puedes leer la transcripción.';return}
synth.cancel();playing=true;paused=false;document.getElementById('pause').textContent='⏸ Pausar';msg.textContent='El guardián está hablando…';setTimeout(()=>say(i),80)}
function end(t){playing=false;paused=false;talk(false);uEls.forEach(e=>e.classList.remove('on'));msg.textContent=t||'Detenido.'}
document.getElementById('play').onclick=()=>begin(0);
document.getElementById('stop').onclick=()=>{if(synth)synth.cancel();end('Detenido.')};
document.getElementById('pause').onclick=function(){if(!synth||!playing)return;if(!paused){paused=true;synth.pause();talk(false);this.textContent='▶ Continuar'}else{paused=false;synth.resume();talk(true);this.textContent='⏸ Pausar'}};
if(synth&&synth.onvoiceschanged!==undefined)synth.onvoiceschanged=()=>{};
window.addEventListener('pagehide',()=>{try{synth.cancel()}catch(e){}});
</script>"""
    return page.replace("__PARAS__", _js(paragraphs)).replace("__UNITS__", _js(units))
