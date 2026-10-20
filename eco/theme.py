# -*- coding: utf-8 -*-
"""Tema «Ecológico & Arquitectónico»: bosque profundo, tierra y crema, con paneles de vidrio."""
from __future__ import annotations

import base64
import html

_FOREST_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1600 420' preserveAspectRatio='xMidYMax slice'>
<defs><linearGradient id='g1' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#173a28' stop-opacity='.0'/><stop offset='1' stop-color='#0b1f16' stop-opacity='.95'/></linearGradient>
<pattern id='pine' width='70' height='120' patternUnits='userSpaceOnUse'><path d='M35 4 L58 48 H46 L64 86 H6 L24 48 H12 Z' fill='#0d281b'/><rect x='32' y='86' width='6' height='20' fill='#2a1d12'/></pattern>
<pattern id='pine2' width='54' height='96' patternUnits='userSpaceOnUse' patternTransform='translate(20 0)'><path d='M27 4 L45 40 H36 L50 70 H4 L18 40 H9 Z' fill='#133524'/></pattern></defs>
<path d='M0 250 C220 170 380 260 620 200 S1060 150 1250 215 S1500 190 1600 230 V420 H0 Z' fill='#173a28' opacity='.55'/>
<path d='M0 310 C200 250 420 330 700 280 S1100 240 1300 290 S1520 270 1600 300 V420 H0 Z' fill='#1f4a31' opacity='.5'/>
<rect x='0' y='250' width='1600' height='120' fill='url(#pine2)' opacity='.8'/>
<path d='M0 350 C260 310 520 380 800 340 S1300 320 1600 360 V420 H0 Z' fill='#3a2818'/>
<rect x='0' y='290' width='1600' height='120' fill='url(#pine)' opacity='.95'/>
<path d='M0 385 C300 360 600 405 900 380 S1400 370 1600 392 V420 H0 Z' fill='#2a1d12'/>
<rect width='1600' height='420' fill='url(#g1)'/></svg>"""

_GRAIN_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 .9  0 0 0 0 .85  0 0 0 0 .7  0 0 0 .07 0'/></filter><rect width='100%' height='100%' filter='url(#n)'/></svg>"""


def _data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


FOREST_URI = _data_uri(_FOREST_SVG)
GRAIN_URI = _data_uri(_GRAIN_SVG)

LOGO_SVG = """<svg viewBox='0 0 64 64' xmlns='http://www.w3.org/2000/svg' aria-hidden='true'>
<defs><linearGradient id='lg' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#c5e68a'/><stop offset='1' stop-color='#4cb97b'/></linearGradient></defs>
<path d='M32 3 L57 12 V32 C57 47 46 57 32 61 C18 57 7 47 7 32 V12 Z' fill='#0e2a1c' stroke='url(#lg)' stroke-width='3'/>
<path d='M32 46 C32 33 38 24 49 21 C49 33 43 42 32 46 Z' fill='url(#lg)'/>
<path d='M32 46 C32 36 26 29 17 27 C17 37 22 44 32 46 Z' fill='#79c47e'/>
<path d='M32 48 V26' stroke='#f4eedb' stroke-width='2' stroke-linecap='round'/></svg>"""


def brand_html(tagline: str = "Guardianes del planeta") -> str:
    return (f"<div class='eg-brand'><span class='eg-logo'>{LOGO_SVG}</span>"
            f"<span class='eg-brand-copy'><span class='eg-wordmark'>Eco<b>Guardian</b></span>"
            f"<span class='eg-tag'>{html.escape(tagline)}</span></span></div>")


def avatar_css(photo_b64: str | None, initials: str) -> str:
    """Estilo del botón circular de perfil: foto si existe, iniciales si no."""
    safe = "".join(ch for ch in initials if ch.isalnum())[:2].upper() or "EG"
    if photo_b64:
        return f"<style>.st-key-eg-avatar button{{background-image:url(data:image/jpeg;base64,{photo_b64}) !important;background-size:cover !important;background-position:center !important}}</style>"
    return (f"<style>.st-key-eg-avatar button{{background-image:linear-gradient(135deg,#2f8f5b,#7a5638) !important}}"
            f".st-key-eg-avatar button::after{{content:'{safe}';font-size:1.05rem;font-weight:700;color:#fff;letter-spacing:.02em}}</style>")


def legacy_css() -> str:
    """Estilos de componentes antiguos (canecas, héroe, semáforo) que conservan colores propios."""
    return """<style>
.eg-hero{background:linear-gradient(135deg,rgba(15,42,28,.92),rgba(58,40,24,.85));color:#F4EEDB;border:1px solid rgba(232,220,194,.18);border-radius:20px;padding:26px 30px;display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap;margin-bottom:18px;box-shadow:0 14px 34px rgba(0,0,0,.35)}
.eg-hero h1{margin:0;font-size:2rem;color:#F4EEDB !important}.eg-hero p{margin:6px 0 0;color:#D6E2CC !important;max-width:520px}
.eg-score{text-align:right}.eg-score .n{font-family:'Fraunces',Georgia,serif;font-size:3.2rem;font-weight:700;line-height:1;color:#F4EEDB !important}.eg-score .l{color:#D6E2CC !important}
.eg-card,.eg-panel{border:1px solid rgba(232,220,194,.18);border-radius:16px;padding:16px 18px;background:rgba(12,32,23,.66);color:#F4EEDB;backdrop-filter:blur(12px)}
.eg-bin{border-radius:14px;padding:16px 18px}
.semaforo{background:#1B1F23;border-radius:40px;padding:14px 12px;width:92px;display:flex;flex-direction:column;gap:12px;align-items:center;margin:auto}
.lamp{width:64px;height:64px;border-radius:50%}.bigdb{font-family:'Fraunces',Georgia,serif;font-size:3rem;font-weight:700;line-height:1}
.eg-bin{box-sizing:border-box;min-height:100%;border-radius:16px;padding:18px 17px;box-shadow:0 8px 22px rgba(0,0,0,.3);line-height:1.55;overflow-wrap:anywhere;border:1px solid rgba(18,48,32,.16)}
.eg-bin-kicker{font-size:.68rem;font-weight:800;letter-spacing:.09em;opacity:.88;margin-bottom:10px}.eg-bin-title{display:block;font-size:1.3rem;line-height:1.2;margin-bottom:7px;text-transform:capitalize}
.eg-bin-subtitle{font-weight:750;font-size:.98rem;line-height:1.35;margin-bottom:12px}.eg-bin p{margin:0 0 12px;font-size:.91rem;line-height:1.55}
.eg-bin-detail{border-radius:18px;padding:22px 24px;margin-top:18px;box-shadow:0 10px 28px rgba(0,0,0,.3);line-height:1.65}.eg-bin-detail *{color:inherit !important}
.eg-bin-detail .eg-bin-title{font-size:1.5rem;font-weight:850;text-transform:capitalize;margin-bottom:8px}.eg-bin-detail .eg-bin-subtitle{font-size:1.05rem;font-weight:800;margin-bottom:12px}
.st-key-bin_Blanco button,.st-key-bin_Verde button,.st-key-bin_Negro button,.st-key-bin_Rojo button{min-height:168px !important;height:auto !important;padding:20px 16px !important;border-radius:18px !important;border-width:3px !important;white-space:pre-line !important;line-height:1.55 !important;font-size:1.08rem !important;font-weight:800 !important;box-shadow:0 8px 0 rgba(0,0,0,.25) !important}
.st-key-bin_Blanco button{background:#F1F4F6 !important;border-color:#A7B2BC !important;color:#17252D !important}
.st-key-bin_Verde button{background:#287A3E !important;border-color:#1B5D2D !important;color:#FFFFFF !important}
.st-key-bin_Negro button{background:#292D32 !important;border-color:#111417 !important;color:#FFFFFF !important}
.st-key-bin_Rojo button{background:#B92F35 !important;border-color:#8D2025 !important;color:#FFFFFF !important}
.st-key-bin_Blanco button *{color:#17252D !important}.st-key-bin_Verde button *,.st-key-bin_Negro button *,.st-key-bin_Rojo button *{color:#FFFFFF !important}
@media(max-width:640px){.st-key-bin_Blanco button,.st-key-bin_Verde button,.st-key-bin_Negro button,.st-key-bin_Rojo button{min-height:140px !important;padding:14px 10px !important}}
</style>"""


GLOBAL_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Outfit:wght@400;500;600;700&display=swap');
:root{--f950:#07150e;--f900:#0b1f16;--f800:#11291d;--f700:#173a28;--moss:#5d8f4a;--leaf:#79c47e;--lime:#c5e68a;--bark:#4a3321;--earth:#7a5638;--clay:#c28a57;--sand:#e8dcc2;--cream:#f4eedb;--muted:#cfd9c7;
--glass:rgba(12,32,23,.68);--glass2:rgba(244,238,219,.07);--edge:rgba(232,220,194,.18);color-scheme:dark}
html body .stApp{font-family:'Outfit',system-ui,-apple-system,'Segoe UI',sans-serif;color:var(--cream);
background-color:#0b1f16;
background-image:url(__FOREST__),url(__GRAIN__),radial-gradient(1100px 560px at 10% -8%,rgba(121,196,126,.22),transparent 62%),radial-gradient(900px 520px at 96% 6%,rgba(194,138,87,.20),transparent 62%),linear-gradient(180deg,#0a1d14 0%,#102a1c 48%,#1a150e 100%);
background-repeat:no-repeat,repeat,no-repeat,no-repeat,no-repeat;background-position:center bottom,0 0,0 0,0 0,0 0;background-size:100% min(46vh,420px),180px 180px,auto,auto,auto;background-attachment:fixed}
html body .stApp [data-testid="stHeader"]{background:transparent}
html body .stApp [data-testid="stSidebar"],html body .stApp [data-testid="stSidebarCollapsedControl"]{display:none !important}
.stApp .block-container{max-width:1240px;padding-top:.8rem;padding-bottom:5rem}
.stApp h1,.stApp h2,.stApp h3,.stApp h4{font-family:'Fraunces',Georgia,serif;color:var(--cream);letter-spacing:-.01em}
.stApp [data-testid="stMarkdownContainer"] p,.stApp [data-testid="stMarkdownContainer"] li{line-height:1.62;color:var(--cream)}
.stApp [data-testid="stCaptionContainer"],.stApp [data-testid="stCaptionContainer"] *{color:var(--muted) !important}
.stApp [data-testid="stWidgetLabel"] p,.stApp label p{color:var(--cream) !important}
.stApp a{color:var(--lime)}
.stApp button,.stApp input,.stApp textarea,.stApp select{font-family:inherit}
/* Botones */
html body .stApp .stButton>button:not([class*="st-key-bin_"] *):not([class*="st-key-opt_"] *):not([class*="st-key-next_"] *):not([class*="st-key-ans_"] *),
html body .stApp .stDownloadButton>button,html body .stApp .stFormSubmitButton>button{background:linear-gradient(180deg,rgba(244,238,219,.15),rgba(244,238,219,.06));color:var(--cream);border:1px solid rgba(244,238,219,.30);border-radius:12px;font-weight:600;min-height:2.6rem;transition:transform .15s,border-color .15s,background .15s}
html body .stApp .stButton>button:not([class*="st-key-bin_"] *):not([class*="st-key-opt_"] *):not([class*="st-key-next_"] *):not([class*="st-key-ans_"] *):hover,
html body .stApp .stDownloadButton>button:hover,html body .stApp .stFormSubmitButton>button:hover{border-color:var(--lime);background:rgba(121,196,126,.24);color:#fff;transform:translateY(-1px)}
html body .stApp .stButton>button[kind="primary"]:not([class*="st-key-bin_"] *),html body .stApp .stFormSubmitButton>button[kind="primary"]{background:linear-gradient(180deg,#1f8450,#176b3d);color:#fff;border:1px solid #4cc088}
html body .stApp .stButton>button *,html body .stApp .stFormSubmitButton>button *{color:inherit}
.stApp button:focus-visible,.stApp input:focus-visible,.stApp textarea:focus-visible{outline:3px solid var(--lime) !important;outline-offset:2px}
/* Cristal */
.eg-glass,[data-testid="stExpander"],[data-testid="stMetric"],[data-testid="stForm"],[data-testid="stAlert"]{background:var(--glass);border:1px solid var(--edge);border-radius:16px;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
[data-testid="stMetric"]{padding:14px 16px;box-shadow:0 8px 22px rgba(0,0,0,.28)}
[data-testid="stForm"]{padding:18px}
.stApp [data-testid="stExpander"] summary,.stApp [data-testid="stExpander"] summary *{color:var(--cream)}
.stApp [data-baseweb="tab-list"]{background:var(--glass);border-radius:14px;padding:4px;gap:4px}
.stApp [data-baseweb="tab"]{color:var(--cream);border-radius:10px}.stApp [aria-selected="true"][data-baseweb="tab"]{background:rgba(121,196,126,.25)}
.stApp [data-baseweb="input"],.stApp [data-baseweb="textarea"],.stApp [data-baseweb="select"]>div{background:rgba(7,21,14,.72) !important;border-color:var(--edge) !important;color:var(--cream)}
[data-testid="stPopoverBody"]{background:rgba(10,28,19,.96);border:1px solid var(--edge);border-radius:18px;box-shadow:0 24px 60px rgba(0,0,0,.55);min-width:min(340px,92vw)}
/* Barra superior */
.st-key-eg-topbar{position:sticky;top:.4rem;z-index:999;background:rgba(8,24,16,.84);border:1px solid var(--edge);border-radius:20px;padding:.55rem .9rem;margin-bottom:1.1rem;backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);box-shadow:0 14px 40px rgba(0,0,0,.45)}
.st-key-eg-topbar [data-testid="stHorizontalBlock"]{flex-wrap:nowrap !important;align-items:center;gap:.5rem}
.st-key-eg-topbar [data-testid="stColumn"]{min-width:0 !important}
.st-key-eg-topbar [data-testid="stMarkdownContainer"] p{margin:0}
.eg-brand{display:flex;align-items:center;gap:.7rem;min-width:0}.eg-logo{width:44px;height:44px;flex:0 0 44px;filter:drop-shadow(0 4px 10px rgba(0,0,0,.45))}
.eg-brand-copy{display:flex;flex-direction:column;line-height:1.1;min-width:0}
.eg-wordmark{font-family:'Fraunces',Georgia,serif;font-size:1.3rem;font-weight:600;color:var(--cream);white-space:nowrap}.eg-wordmark b{color:var(--lime);font-weight:700}
.eg-tag{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.st-key-eg-nav [data-testid="stHorizontalBlock"]{overflow-x:auto;scrollbar-width:none}
.st-key-eg-nav button{border-radius:999px !important;white-space:nowrap}
/* Avatar circular (estilo WhatsApp) */
.st-key-eg-avatar{display:flex;justify-content:flex-end}
.st-key-eg-avatar button{width:48px !important;height:48px !important;min-height:48px !important;padding:0 !important;border-radius:50% !important;font-size:0 !important;color:transparent !important;border:2px solid var(--lime) !important;box-shadow:0 0 0 3px rgba(11,31,22,.9),0 0 0 5px rgba(121,196,126,.55) !important;overflow:hidden;display:flex;align-items:center;justify-content:center;transition:transform .15s}
.st-key-eg-avatar button:hover{transform:scale(1.06)}
.st-key-eg-bell,.st-key-eg-bell-on{display:flex;justify-content:flex-end}
.st-key-eg-bell button,.st-key-eg-bell-on button{border-radius:999px !important;min-height:44px !important;padding:0 .85rem !important;white-space:nowrap;font-weight:700}
.st-key-eg-bell button [data-testid="stIconMaterial"],.st-key-eg-bell-on button [data-testid="stIconMaterial"]{display:none !important}
.st-key-eg-bell-on button{border:2px solid #ffca28 !important;background:rgba(255,202,40,.16) !important;animation:egBell 1.6s ease-in-out infinite}
@keyframes egBell{0%,100%{box-shadow:0 0 0 0 rgba(255,202,40,.55)}50%{box-shadow:0 0 0 9px rgba(255,202,40,0)}}
.eg-bell-sec{margin:.6rem 0 .2rem;font-size:.78rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}

.st-key-eg-avatar button svg,.st-key-eg-avatar button [data-testid="stIconMaterial"]{display:none !important}
.eg-menu-head{display:flex;gap:.7rem;align-items:center;padding:.2rem 0 .6rem;border-bottom:1px solid var(--edge);margin-bottom:.5rem}
.eg-menu-name{font-family:'Fraunces',Georgia,serif;font-size:1.1rem;font-weight:700;color:var(--cream)}
.eg-role-badge{display:inline-block;font-size:.7rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:2px 10px;border-radius:999px;background:rgba(197,230,138,.18);color:var(--lime);border:1px solid rgba(197,230,138,.4)}
.st-key-eg-menu button{justify-content:flex-start !important;text-align:left;background:transparent !important;border:1px solid transparent !important;font-weight:500 !important}
.st-key-eg-menu button:hover{background:rgba(121,196,126,.18) !important;border-color:var(--edge) !important;transform:none !important}
/* Biblioteca */
.eg-lib-hero{position:relative;overflow:hidden;border-radius:26px;padding:2.2rem 2rem 1.8rem;margin-bottom:1rem;border:1px solid var(--edge);background:linear-gradient(120deg,rgba(23,58,40,.88),rgba(74,51,33,.78));box-shadow:0 20px 50px rgba(0,0,0,.4)}
.eg-lib-hero h1{margin:0 0 .4rem;font-size:clamp(1.7rem,3.4vw,2.7rem);color:var(--cream)}
.eg-lib-hero p{margin:0;max-width:640px;color:var(--muted);font-size:1.05rem}
.eg-kicker{font-size:.75rem;letter-spacing:.2em;text-transform:uppercase;color:var(--lime);font-weight:700;margin-bottom:.5rem}
.st-key-eg-cats button{border-radius:999px !important}
[class*="st-key-gcard_"]{background:var(--glass);border:1px solid var(--edge);border-radius:22px;padding:14px 14px 10px;backdrop-filter:blur(14px);box-shadow:0 12px 30px rgba(0,0,0,.35);transition:transform .2s,border-color .2s;margin-bottom:.8rem}
[class*="st-key-gcard_"]:hover{transform:translateY(-4px);border-color:rgba(197,230,138,.55)}
.eg-cover{height:128px;border-radius:16px;display:flex;align-items:center;justify-content:center;font-size:3.6rem;margin-bottom:.7rem;position:relative;box-shadow:inset 0 -30px 40px rgba(0,0,0,.25)}
.eg-cover span.badge{position:absolute;top:8px;left:8px;font-size:.68rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;background:rgba(8,24,16,.78);color:var(--lime);padding:3px 10px;border-radius:999px}
.eg-card-title{font-family:'Fraunces',Georgia,serif;font-size:1.2rem;font-weight:700;color:var(--cream);margin-bottom:.2rem}
.eg-card-desc{font-size:.9rem;color:var(--muted);min-height:3.1em;line-height:1.45}
.eg-chip{display:inline-block;font-size:.72rem;font-weight:600;padding:2px 9px;margin:0 4px 4px 0;border-radius:999px;background:var(--glass2);border:1px solid var(--edge);color:var(--cream)}
/* Arena */
.eg-pin{font-family:'Fraunces',Georgia,serif;font-size:clamp(2.6rem,9vw,5rem);font-weight:700;letter-spacing:.18em;color:var(--lime);text-align:center;text-shadow:0 6px 30px rgba(121,196,126,.4)}
.eg-qcard{background:var(--glass);border:1px solid var(--edge);border-radius:24px;padding:1.6rem 1.4rem;text-align:center;margin:.4rem 0 1rem;box-shadow:0 16px 40px rgba(0,0,0,.4)}
.eg-qcard h2{margin:.2rem 0;font-size:clamp(1.2rem,2.6vw,1.9rem);line-height:1.3}
.eg-timer{height:12px;border-radius:999px;background:rgba(244,238,219,.14);overflow:hidden;margin:.4rem 0 .8rem}
.eg-timer>div{height:100%;width:100%;background:linear-gradient(90deg,#c5e68a,#e8b04b,#d2603a);transform-origin:left;border-radius:999px}
@keyframes eg-shrink{from{transform:scaleX(1)}to{transform:scaleX(0)}}
@keyframes eg-pop{0%{transform:scale(.9);opacity:0}100%{transform:scale(1);opacity:1}}
.eg-pop{animation:eg-pop .35s ease-out}
.eg-result{border-radius:22px;padding:1.2rem 1.4rem;text-align:center;margin:.5rem 0 1rem;border:2px solid var(--edge);animation:eg-pop .35s ease-out}
.eg-result.ok{background:rgba(31,122,74,.35);border-color:#4cc088}.eg-result.bad{background:rgba(138,47,45,.38);border-color:#e0756c}.eg-result.tie{background:rgba(194,138,87,.32);border-color:#e8b04b}
.eg-result .big{font-family:'Fraunces',Georgia,serif;font-size:1.7rem;font-weight:700;color:#fff}
.eg-chiprow{display:flex;flex-wrap:wrap;gap:.4rem;justify-content:center}
.eg-player{background:var(--glass2);border:1px solid var(--edge);padding:.35rem .8rem;border-radius:999px;font-weight:600;color:var(--cream);animation:eg-pop .3s}
[class*="st-key-ans_"] button{min-height:84px !important;font-size:1.12rem !important;font-weight:700 !important;border-radius:18px !important;color:#fff !important;border:2px solid rgba(255,255,255,.28) !important;box-shadow:0 6px 0 rgba(0,0,0,.3) !important;white-space:normal !important;line-height:1.3}
[class*="st-key-ans_"] button *{color:#fff !important}
[class*="st-key-ans_0"] button{background:#1f7a4a !important}[class*="st-key-ans_1"] button{background:#a4561f !important}
[class*="st-key-ans_2"] button{background:#0f6f80 !important}[class*="st-key-ans_3"] button{background:#8a2f5d !important}
[class*="st-key-ans_"] button:hover{filter:brightness(1.12);transform:translateY(-2px)}
[class*="st-key-ans_"] button:disabled{opacity:.55}
.eg-vs{display:flex;align-items:center;justify-content:center;height:100%;font-family:'Fraunces',Georgia,serif;font-size:1.6rem;font-weight:700;color:var(--clay)}
.eg-duel{background:var(--glass);border:1px solid var(--edge);border-radius:22px;padding:1rem;text-align:center}
.eg-duel .em{font-size:4.2rem;line-height:1.2}.eg-duel .lb{font-weight:700;color:var(--cream)}
.eg-silhouette{background:var(--glass);border:1px solid var(--edge);border-radius:22px;padding:1rem;text-align:center}
.eg-steps{display:flex;gap:6px;justify-content:center;margin:.5rem 0}
.eg-dot{width:12px;height:12px;border-radius:50%;background:rgba(244,238,219,.2)}.eg-dot.on{background:var(--lime)}.eg-dot.cur{background:var(--clay);transform:scale(1.25)}
/* Acceso */
.eg-login-brand{font-family:'Fraunces',Georgia,serif;font-size:clamp(2.1rem,4vw,3.3rem);font-weight:700;color:var(--cream);line-height:1.1;margin:.5rem 0 1rem}
.eg-login-copy{color:var(--sand);font-size:clamp(1.1rem,1.7vw,1.5rem);line-height:1.4;max-width:540px}
@media(max-width:700px){.eg-brand-copy{display:none}.st-key-eg-topbar [data-testid="stColumn"]:has(.st-key-eg-bell),.st-key-eg-topbar [data-testid="stColumn"]:has(.st-key-eg-bell-on){flex:0 0 74px !important;min-width:74px !important;width:74px !important}.st-key-eg-topbar [data-testid="stColumn"]:has(.st-key-eg-avatar){flex:0 0 60px !important;min-width:60px !important;width:60px !important}.st-key-eg-topbar [data-testid="stColumn"]:has(.eg-brand){flex:0 0 46px !important;min-width:46px !important;width:46px !important}.st-key-eg-nav button{padding:.25rem .6rem !important;font-size:.82rem !important}.eg-tag{display:none}.eg-wordmark{font-size:1.05rem}.eg-logo{width:36px;height:36px;flex-basis:36px}.eg-cover{height:104px}.stApp .block-container{padding-left:.8rem;padding-right:.8rem}}
.st-key-eg-ambient-engine{display:none !important}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms !important;transition-duration:.01ms !important}}
</style>""".replace("__FOREST__", FOREST_URI).replace("__GRAIN__", GRAIN_URI)
