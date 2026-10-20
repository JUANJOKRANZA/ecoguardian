# -*- coding: utf-8 -*-
"""Interfaz Streamlit de las nuevas funciones. Toda la lógica de reglas vive en engine/store/arena."""
from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import math
import re
import secrets

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from . import about, ambient as ambient_audio, arena, engine, media, party, seed, store, theme, voice
from .engine import CAT_BLURB, CAT_COLORS, CAT_ICON, CATEGORIES, LEVEL_ICON, LEVEL_POINTS, LEVELS, QTYPES

esc = html.escape

# ── Registro de juegos nuevos ─────────────────────────────────────────────────
NEW_GAMES = [
    {"key": "arena", "icon": "🏟️", "title": "Arena en Vivo", "badge": "Campeonato",
     "desc": "Batallas y torneos con PIN de sala: velocidad, reflejos y ranking en tiempo real.", "tags": ["PIN", "Tiempo real", "Equipos"]},
    {"key": "party", "icon": "🎉", "title": "EcoParty", "badge": "Fiesta multijugador",
     "desc": "Minijuegos ambientales, retos relámpago y marcador compartido para hasta 12 jugadores.", "tags": ["Hasta 12", "Local y online", "Tiempo real"]},
    {"key": "mission", "icon": "🎯", "title": "Misión por Niveles", "badge": "Individual",
     "desc": "Cuestionarios únicos para ti: Fácil, Intermedio, Avanzado o Experto, sin repetir preguntas.", "tags": ["4 niveles", "Todos los tipos"]},
    {"key": "tf", "icon": "⚖️", "title": "Verdadero o Falso Relámpago", "badge": "Individual",
     "desc": "Afirmaciones ambientales: ¿mito o realidad? Decide y aprende por qué.", "tags": ["Verdadero / Falso"]},
    {"key": "duel", "icon": "🆚", "title": "Duelo de Imágenes", "badge": "Individual",
     "desc": "Dos imágenes frente a frente: elige la que responde la pregunta.", "tags": ["Imágenes enfrentadas"]},
    {"key": "match", "icon": "🧩", "title": "Parejas Ecológicas", "badge": "Individual",
     "desc": "Une cada concepto con su pareja correcta.", "tags": ["Emparejamiento"]},
    {"key": "inflate", "icon": "🎈", "title": "Balloon Bash", "badge": "Individual",
     "desc": "Infla el globo, siente cómo tiembla y detente antes de que explote. Sin cronómetro.", "tags": ["Sin tiempo", "Control y nervios"]},
]
QUIZ = {"mission": list(QTYPES), "tf": ["tf"], "duel": ["image"], "match": ["match"]}
GAME_TITLE = {g["key"]: g["title"] for g in NEW_GAMES}
LEGACY_ICON = {"EcoSonidos": "🔊", "EcoPuff Arcade": "♻️", "EcoRunner": "🏃", "EcoRetos": "🧠", "EcoReto en Vivo": "⚡", "EcoVerdadero o Falso": "🌿"}

TOP_NAV = [("library", "🎮 Biblioteca"), ("arena", "🏟️ Arena"), ("about", "ℹ️ Acerca de")]
ROLE_MENU = {
    "student": [("home", "🏠 Mi panel"), ("mission", "🎯 Mis misiones")],
    "teacher": [("tclasses", "🏫 Mis clases"), ("tgames", "🎛️ Juegos y niveles"), ("bank", "📚 Banco de preguntas"),
                ("tassign", "🧑‍🎓 Asignar EcoAventura"), ("tmsgs", "💬 Mensajes")],
    "admin": [("adash", "🛠️ Panel de control"), ("aaccounts", "👥 Autorizar cuentas"), ("aperms", "🛡️ Permisos EcoAventura"),
              ("agames", "🎛️ Interruptores maestros"), ("bank", "📚 Banco global"), ("anotif", "🔔 Notificaciones"),
              ("asettings", "⚙️ Configuración"), ("apres", "🎙️ Presentación")],
}
ROLE_LABEL = {"admin": "Administrador", "teacher": "Docente", "student": "Estudiante"}


# ── Utilidades ────────────────────────────────────────────────────────────────
def _btn(label: str, **kw):
    """Botón a ancho completo compatible con versiones nuevas y antiguas de Streamlit."""
    try:
        return st.button(label, width="stretch", **kw)
    except TypeError:
        return st.button(label, use_container_width=True, **kw)


def sound(name: str, token: str = "") -> None:
    if st.session_state.get("sound_on", True):
        components.html(media.sfx_html(name) + (f"<!--{token}-->" if token else ""), height=0)


def ambient(force_off: bool = False) -> None:
    """Sincroniza la música ambiental persistente (ver eco/ambient.py). Se llama en cada rerun, también sin sesión."""
    ambient_audio.engine(force_off=force_off)


def _go(page: str, game: str | None = None) -> None:
    st.session_state["page"] = page
    st.session_state["lib_game"] = game


def _fragment(run_every: str):
    if hasattr(st, "fragment"):
        return st.fragment(run_every=run_every)
    return lambda fn: fn


def _thumb_b64(photo: bytes) -> str:
    key = "thumb_" + hashlib.md5(photo).hexdigest()
    if key not in st.session_state:
        img = Image.open(io.BytesIO(photo)).convert("RGB")
        img.thumbnail((112, 112))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        st.session_state[key] = base64.b64encode(buf.getvalue()).decode("ascii")
    return st.session_state[key]


def _dots(i: int, n: int) -> str:
    cells = "".join(f"<span class='eg-dot {'on' if j < i else 'cur' if j == i else ''}'></span>" for j in range(n))
    return f"<div class='eg-steps'>{cells}</div>"


def _hero(kicker: str, title: str, text: str) -> None:
    st.markdown(f"<div class='eg-lib-hero'><div class='eg-kicker'>{esc(kicker)}</div><h1>{esc(title)}</h1><p>{esc(text)}</p></div>",
                unsafe_allow_html=True)


# ── Barra superior + avatar ───────────────────────────────────────────────────
def shell(ctx) -> None:
    """Barra superior: logotipo, navegación común y SOLO la foto circular de perfil con su menú flotante."""
    con = store.get_con()
    try:
        acc = con.execute("SELECT display_name FROM accounts WHERE username=?", (ctx.username,)).fetchone()
        prof = con.execute("SELECT photo,email,phone,bio FROM user_profiles WHERE username=?", (ctx.username,)).fetchone()
    finally:
        con.close()
    name = (acc["display_name"] if acc else ctx.display or ctx.username).strip() or ctx.username
    photo = bytes(prof["photo"]) if prof and prof["photo"] else None
    initials = "".join(p[0] for p in name.split()[:2]) or "EG"
    st.markdown(theme.avatar_css(_thumb_b64(photo) if photo else None, initials), unsafe_allow_html=True)
    with st.container(key="eg-topbar"):
        c_brand, c_nav, c_bell, c_avatar = st.columns([2.6, 4.6, 1.0, 1.1], vertical_alignment="center", gap="small")
        with c_brand:
            st.markdown(theme.brand_html(), unsafe_allow_html=True)
        with c_nav:
            with st.container(key="eg-nav"):
                cols = st.columns(len(TOP_NAV), gap="small")
                for col, (page, label) in zip(cols, TOP_NAV):
                    with col:
                        _btn(label, key=f"nav_{page}", type="primary" if st.session_state.get("page") == page else "secondary",
                             on_click=_go, args=(page,))
        with c_bell:
            bell(ctx)
        with c_avatar:
            with st.container(key="eg-avatar"):
                with st.popover("\u200b", help="Mi perfil y opciones"):
                    _menu(ctx, name, initials, photo, prof)


# ── Campana de notificaciones (fuera del menú, en tiempo casi real) ──────────
BELL_POLL = "4s"  # cada cuántos segundos se consulta la base de datos


def _bell_data(ctx) -> tuple[list[dict], list[dict]]:
    """Solicitudes de cuenta pendientes (solo administrador) y mensajes sin leer del usuario."""
    pending: list[dict] = []
    msgs: list[dict] = []
    try:
        con = store.get_con()
        try:
            if ctx.role == "admin":
                pending = [dict(r) for r in con.execute(
                    "SELECT username,display_name,role,created_at FROM accounts "
                    "WHERE role IN ('student','teacher') AND approved=0 ORDER BY created_at").fetchall()]
            msgs = [dict(r) for r in con.execute(
                "SELECT id,sender,body,created_at FROM messages WHERE recipient=? AND read_at IS NULL "
                "ORDER BY id DESC LIMIT 20", (ctx.username,)).fetchall()]
        finally:
            con.close()
    except Exception:
        pass
    return pending, msgs


def _bell_sig(pending: list[dict], msgs: list[dict]) -> tuple:
    return (tuple(p["username"] for p in pending), tuple(m["id"] for m in msgs))


def _bell_decide(username: str, approve: bool) -> None:
    """Autoriza o rechaza una cuenta desde la campana. Valida en el servidor que quien actúa es administrador."""
    if st.session_state.get("auth_role") != "admin":
        return
    con = store.get_con()
    try:
        if approve:
            con.execute("UPDATE accounts SET approved=1 WHERE username=? AND role IN ('student','teacher')", (username,))
        else:
            con.execute("DELETE FROM accounts WHERE username=? AND role IN ('student','teacher') AND approved=0", (username,))
        try:
            con.execute("UPDATE notifications SET seen=1 WHERE username=? AND kind IN ('registro','registro_docente')", (username,))
        except Exception:
            pass
        con.commit()
    finally:
        con.close()


def _bell_mark_read(msg_id: int | None, username: str) -> None:
    con = store.get_con()
    try:
        if msg_id is None:
            con.execute("UPDATE messages SET read_at=? WHERE recipient=? AND read_at IS NULL", (store._now(), username))
        else:
            con.execute("UPDATE messages SET read_at=? WHERE id=? AND recipient=? AND read_at IS NULL", (store._now(), msg_id, username))
        con.commit()
    finally:
        con.close()


def _rerun_app() -> None:
    try:
        st.rerun(scope="app")
    except TypeError:
        st.rerun()


def _bell_toast_text(new_pending: list[dict], new_msgs: list[dict]) -> str:
    if len(new_pending) == 1 and not new_msgs:
        p = new_pending[0]
        return f"{p['display_name']} solicitó acceso como {'docente' if p['role'] == 'teacher' else 'estudiante'}."
    if len(new_msgs) == 1 and not new_pending:
        return f"@{new_msgs[0]['sender']} te envió un mensaje."
    return "Ha llegado una notificación nueva."


def browser_notification(token: str = "") -> None:
    """Aviso web opcional mientras el sitio está abierto; no es Web Push para pestañas cerradas.

    El permiso solo se solicita tras pulsar el botón. El mensaje del sistema es deliberadamente
    genérico para no exponer nombres ni contenido de mensajes en la pantalla bloqueada.
    """
    payload = {"token": token, "body": "Tienes una nueva notificación. Abre EcoGuardian AI para verla."}
    payload_json = json.dumps(payload, ensure_ascii=True).replace("</", "<\\/")
    button_style = "display:none" if token else ""
    page = f'''<!doctype html><html><head><meta charset="utf-8"><style>
      body{{margin:0;font:12px system-ui,sans-serif;color:#315246;background:transparent}}
      button{{border:1px solid #b8d9c8;border-radius:9px;padding:7px 10px;background:#f2fbf6;color:#175d40;cursor:pointer}}
      #status{{margin-left:8px;color:#557568}}
      </style></head><body>
      <button id="eg-enable-browser-notifications" type="button" style="{button_style}">Activar avisos del navegador</button><span id="status" role="status" aria-live="polite"></span>
      <script>
      (()=>{{
        const payload={payload_json};
        const enabledKey='eg-browser-notifications-enabled-v1';
        const lastKey='eg-browser-notifications-last-v1';
        let host=window;
        try{{if(window.parent && window.parent.Notification) host=window.parent;}}catch(_e){{}}
        const getStorage=()=>{{try{{return host.localStorage;}}catch(_e){{return window.localStorage;}}}};
        const status=document.getElementById('status');
        const getNotification=()=>host.Notification || window.Notification;
        document.getElementById('eg-enable-browser-notifications').addEventListener('click', async ()=>{{
          const N=getNotification();
          if(!N || !('Notification' in host || 'Notification' in window)){{status.textContent='Este navegador no admite avisos.';return;}}
          try{{
            const permission=await N.requestPermission();
            if(permission==='granted'){{getStorage().setItem(enabledKey,'1');status.textContent='Avisos activados.';}}
            else{{status.textContent='Permiso no concedido; la campana seguirá funcionando.';}}
          }}catch(_e){{status.textContent='El navegador bloqueó el permiso. Usa HTTPS y vuelve a intentarlo.';}}
        }});
        try{{
          const N=getNotification(); const storage=getStorage();
          if(payload.token && N && N.permission==='granted' && storage.getItem(enabledKey)==='1' && storage.getItem(lastKey)!==payload.token){{
            storage.setItem(lastKey,payload.token);
            const note=new N('EcoGuardian AI',{{body:payload.body,tag:'ecoguardian-'+payload.token,renotify:false}});
            note.onclick=()=>{{try{{host.focus();}}catch(_e){{}} note.close();}};
          }}
        }}catch(_e){{/* Las notificaciones web son opcionales; la campana interna no depende de ellas. */}}
      }})();
      </script></body></html>'''
    components.html(page, height=1 if token else 54, scrolling=False)


def _bell_poll(ctx) -> None:
    """Se ejecuta cada pocos segundos en un fragmento: detecta novedades y recarga la pantalla con el aviso."""
    p2, m2 = _bell_data(ctx)
    new_sig = _bell_sig(p2, m2)
    old_sig = st.session_state.get("bell_sig")
    if old_sig is None or new_sig == old_sig:
        return
    fresh_p = [p for p in p2 if p["username"] not in old_sig[0]]
    fresh_m = [m for m in m2 if m["id"] not in old_sig[1]]
    if fresh_p or fresh_m:
        st.session_state["bell_toast"] = _bell_toast_text(fresh_p, fresh_m)
    st.session_state["bell_sig"] = new_sig
    _rerun_app()


def bell(ctx) -> None:
    """Campana visible en la barra superior: contador, aviso emergente, sonido y autorización directa."""
    pending, msgs = _bell_data(ctx)
    n = len(pending) + len(msgs)
    sig = _bell_sig(pending, msgs)
    st.session_state["bell_sig"] = sig  # lo que la pantalla muestra ahora mismo

    # Aviso emergente (abajo) y sonido, programado por el sondeo o al iniciar sesión con pendientes.
    if not st.session_state.get("bell_started"):
        st.session_state["bell_started"] = True
        if n:
            st.session_state["bell_toast"] = f"Tienes {n} notificación{'es' if n != 1 else ''} pendiente{'s' if n != 1 else ''}."
    text = st.session_state.pop("bell_toast", None)
    if text:
        try:
            st.toast(text, icon="🔔")
        except Exception:
            pass
        token = secrets.token_hex(8)
        sound("bell", token=token)
        # Notificación del sistema opcional y sin datos personales; si el navegador la bloquea,
        # el aviso interno y la campana siguen operando normalmente.
        browser_notification(token)

    # Sondeo silencioso: si aparece algo nuevo, se recarga la pantalla para mostrarlo al instante.
    if hasattr(st, "fragment"):
        @st.fragment(run_every=BELL_POLL)
        def _watch():
            _bell_poll(ctx)
        _watch()

    with st.container(key="eg-bell-on" if n else "eg-bell"):
        with st.popover(f"🔔 {n}" if n else "🔔", help="Notificaciones"):
            st.markdown("**Notificaciones**")
            browser_notification()
            st.caption("Los avisos del navegador requieren permiso y HTTPS. La campana de la app sigue funcionando aunque no los actives.")
            if not n:
                st.caption("Todo al día 🌿")
            if pending:
                st.markdown(f"<div class='eg-bell-sec'>Solicitudes de registro ({len(pending)})</div>", unsafe_allow_html=True)
                for p in pending:
                    u = p["username"]
                    st.markdown(f"**{esc(p['display_name'])}** · {'Docente' if p['role'] == 'teacher' else 'Estudiante'} · `@{esc(u)}`")
                    a, b = st.columns(2, gap="small")
                    with a:
                        _btn("✅ Autorizar", key=f"bell_ok_{u}", type="primary", on_click=_bell_decide, args=(u, True))
                    with b:
                        _btn("✖ Rechazar", key=f"bell_no_{u}", on_click=_bell_decide, args=(u, False))
                _btn("Ir al panel de autorizaciones", key="bell_goto_auth", on_click=_go, args=("aaccounts",))
            if msgs:
                st.markdown(f"<div class='eg-bell-sec'>Mensajes sin leer ({len(msgs)})</div>", unsafe_allow_html=True)
                for m in msgs:
                    st.markdown(f"💬 **@{esc(m['sender'])}** · {esc(str(m['created_at'])[:16])}\n\n{esc(m['body'])}")
                    _btn("Marcar como leído", key=f"bell_read_{m['id']}", on_click=_bell_mark_read, args=(m["id"], ctx.username))
                if len(msgs) > 1:
                    _btn("Marcar todos como leídos", key="bell_read_all", on_click=_bell_mark_read, args=(None, ctx.username))


def _menu(ctx, name: str, initials: str, photo: bytes | None, prof) -> None:
    st.markdown(f"<div class='eg-menu-head'><div><div class='eg-menu-name'>{esc(name)}</div>"
                f"<span class='eg-role-badge'>{ROLE_LABEL.get(ctx.role, 'Usuario')}</span>"
                f"<div style='color:var(--muted);font-size:.8rem;margin-top:2px'>@{esc(ctx.username)}</div></div></div>", unsafe_allow_html=True)
    with st.container(key="eg-menu"):
        for page, label in ROLE_MENU.get(ctx.role, []):
            if page == "mission":
                _btn(label, key=f"menu_{page}", on_click=_go, args=("library", "mission"))
            else:
                _btn(label, key=f"menu_{page}", on_click=_go, args=(page,))
    sound_enabled = st.toggle("🔊 Sonidos y ambiente", key="sound_on")
    if sound_enabled:
        ambient_audio.panel()
    else:
        st.caption("Música ambiental desactivada. Activa «Sonidos y ambiente» para volver a escucharla.")
    ambient_audio.policy_selector(disabled=not sound_enabled)
    with st.expander("👤 Mi perfil y foto"):
        _profile_form(ctx, name, photo, prof)
    if _btn("Cerrar sesión", key="menu_logout"):
        ctx.logout()


def _profile_form(ctx, name: str, photo: bytes | None, prof) -> None:
    username = ctx.username
    uploaded = st.file_uploader("Cambiar foto de perfil", type=["png", "jpg", "jpeg", "webp"], key=f"profile_photo_{username}")
    if uploaded is not None:
        try:
            img = Image.open(uploaded).convert("RGB")
            img.thumbnail((512, 512))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=88, optimize=True)
            data = buf.getvalue()
            if not (photo and photo == data):
                con = store.get_con()
                con.execute("INSERT INTO user_profiles(username,photo,updated_at) VALUES(?,?,?) ON CONFLICT(username) "
                            "DO UPDATE SET photo=excluded.photo, updated_at=excluded.updated_at", (username, data, store._now()))
                con.commit()
                con.close()
                st.rerun()
        except Exception:
            st.error("No se pudo leer la imagen. Prueba con JPG o PNG.")
    with st.form(f"profile_details_{username}"):
        new_name = st.text_input("Nombre visible", value=name, max_chars=60)
        email = st.text_input("Correo electrónico (opcional)", value=(prof["email"] if prof else ""), max_chars=120)
        phone = st.text_input("Teléfono (opcional)", value=(prof["phone"] if prof else ""), max_chars=30)
        bio = st.text_area("Presentación", value=(prof["bio"] if prof else ""), max_chars=400)
        if st.form_submit_button("Guardar perfil", type="primary"):
            if not new_name.strip():
                st.error("El nombre no puede quedar vacío.")
            elif email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()):
                st.error("Escribe un correo válido o deja el campo vacío.")
            else:
                con = store.get_con()
                con.execute("UPDATE accounts SET display_name=? WHERE username=?", (new_name.strip(), username))
                con.execute("INSERT INTO user_profiles(username,email,phone,bio,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(username) DO UPDATE "
                            "SET email=excluded.email, phone=excluded.phone, bio=excluded.bio, updated_at=excluded.updated_at",
                            (username, email.strip(), phone.strip(), bio.strip(), store._now()))
                con.commit()
                con.close()
                st.rerun()
    if photo and st.button("Quitar foto", key=f"rm_photo_{username}"):
        con = store.get_con()
        con.execute("UPDATE user_profiles SET photo=NULL, updated_at=? WHERE username=?", (store._now(), username))
        con.commit()
        con.close()
        st.rerun()


# ── Biblioteca ────────────────────────────────────────────────────────────────
def library_page(ctx) -> None:
    game = st.session_state.get("lib_game")
    if game:
        st.button("← Volver a la biblioteca", key="lib_back", on_click=_go, args=("library", None))
        _play(ctx, game)
        return
    con = store.get_con()
    try:
        ok = store.availability(con, ctx.username, ctx.role)
        owners = store.visible_owners(con, ctx.username, ctx.role)
        counts = store.counts_by_category(con, owners)
    finally:
        con.close()
    cats = [c for c in CATEGORIES if ctx.role != "student" or ok("category", c)]
    options = {c: f"{CAT_ICON[c]} {c} · {counts.get(c, 0)}" for c in cats}
    st.session_state.setdefault("lib_cat", None)
    cat = st.session_state.get("lib_cat")
    if cat not in cats:
        cat = None
    _hero(f"{CAT_ICON.get(cat, '🌎')} Biblioteca de juegos" if cat else "🌎 Biblioteca de juegos",
          cat or "Aprende jugando, cuida jugando", CAT_BLURB.get(cat, about.TAGLINE))
    with st.container(key="eg-cats"):
        if hasattr(st, "pills"):
            st.pills("Categoría", cats, selection_mode="single", key="lib_cat", format_func=lambda c: options[c], label_visibility="collapsed")
        else:
            pick = st.radio("Categoría", ["Todas"] + cats, horizontal=True, label_visibility="collapsed")
            st.session_state["lib_cat"] = None if pick == "Todas" else pick
    cat = st.session_state.get("lib_cat")
    c1, c2 = CAT_COLORS.get(cat, ("#4a3321", "#7a5638"))
    entries = [{**g, "kind": "new"} for g in NEW_GAMES]
    for name, desc in ctx.legacy_games.items():
        if name in ctx.legacy_allowed:
            entries.append({"key": f"legacy:{name}", "icon": LEGACY_ICON.get(name, "🌎"), "title": name, "badge": "EcoAventura",
                            "desc": desc, "tags": ["Clásico"], "kind": "legacy"})
    shown = [g for g in entries if g["kind"] == "legacy" or ctx.role != "student" or ok("game", g["key"])]
    cols = st.columns(3, gap="medium")
    for i, g in enumerate(shown):
        with cols[i % 3]:
            with st.container(key=f"gcard_{re.sub('[^A-Za-z0-9]', '_', g['key'])}"):
                locked = g["kind"] == "new" and ctx.role != "student" and not ok("game", g["key"])
                chips = "".join(f"<span class='eg-chip'>{esc(t)}</span>" for t in g["tags"])
                if locked:
                    chips += "<span class='eg-chip'>🔒 Oculto para estudiantes</span>"
                st.markdown(f"<div class='eg-cover' style='background:linear-gradient(135deg,{c1},{c2})'><span class='badge'>{esc(g['badge'])}</span>{g['icon']}</div>"
                            f"<div class='eg-card-title'>{esc(g['title'])}</div><div class='eg-card-desc'>{esc(g['desc'])}</div>{chips}", unsafe_allow_html=True)
                _btn("▶ Jugar ahora", key=f"play_{g['key']}", type="primary", on_click=_go, args=("library", g["key"]))
    if not shown:
        st.info("Tu docente todavía no ha habilitado juegos. ¡Vuelve pronto!")


def _play(ctx, game: str) -> None:
    if game == "arena":
        arena_page(ctx)
    elif game == "party":
        party_page(ctx)
    elif game in QUIZ:
        quiz_page(ctx, game)
    elif game == "inflate":
        inflate_page(ctx)
    elif game.startswith("legacy:"):
        ctx.legacy_play(game.split(":", 1)[1])
    else:
        st.session_state["lib_game"] = None
        st.rerun()


# ── Misiones individuales (anti-copia + sin repetición) ───────────────────────
def _qz_answer(sk: str, username: str, answer) -> None:
    s = st.session_state[sk]
    if s.get("answered") is not None:
        return
    q = s["qs"][s["i"]]
    correct = engine.check(q, answer)
    s["answered"] = {"correct": correct}
    s["res"].append({"id": q["id"], "level": q["level"], "correct": correct, "prompt": q["prompt"], "right": engine.correct_text(q)})
    con = store.get_con()
    try:
        store.mark_seen(con, username, q["id"], correct)
    finally:
        con.close()


def _qz_match_submit(sk: str, username: str, keys: list, lefts: list) -> None:
    vals = [st.session_state.get(k) for k in keys]
    if any(v is None for v in vals):
        st.session_state["qz_warn"] = True
        return
    st.session_state["qz_warn"] = False
    _qz_answer(sk, username, dict(zip(lefts, vals)))


def _streak(res: list) -> int:
    n = 0
    for r in reversed(res):
        if not r["correct"]:
            break
        n += 1
    return n


_QZ_CSS = """<style>
@keyframes eg-shake{0%,100%{transform:translateX(0)}20%{transform:translateX(-9px)}40%{transform:translateX(9px)}60%{transform:translateX(-6px)}80%{transform:translateX(6px)}}
@keyframes eg-vsflash{0%,100%{transform:scale(1);text-shadow:0 0 0 #0000}50%{transform:scale(1.35);text-shadow:0 0 18px #ffb347}}
@keyframes eg-bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
@keyframes eg-glow{0%,100%{box-shadow:0 0 0 #0000}50%{box-shadow:0 0 22px #7cff9b88}}
.eg-result.bad{animation:eg-shake .45s ease-out}
.eg-result.ok .big{display:inline-block;animation:eg-bounce .6s ease-out 2}
.eg-vs{animation:eg-vsflash 1.1s ease-in-out infinite}
.eg-duel{transition:transform .15s,box-shadow .15s}.eg-duel:hover{transform:translateY(-4px) scale(1.03);box-shadow:0 8px 26px #0006}
.eg-duel .em{display:inline-block;animation:eg-bounce 1.6s ease-in-out infinite}
.eg-streak{display:inline-block;margin:.2rem 0 .4rem;padding:.25rem .9rem;border-radius:999px;background:linear-gradient(90deg,#ff8a00,#ff3d00);color:#fff;font-weight:800;animation:eg-glow 1s ease-in-out infinite}
.eg-speak{display:inline-block;margin-left:.6rem;padding:.15rem .7rem;border-radius:999px;background:#ffffff1c;font-size:.85rem}
</style>"""


def _qz_next(sk: str) -> None:
    s = st.session_state[sk]
    s["i"] += 1
    s["answered"] = None


def quiz_page(ctx, key: str) -> None:
    sk, fixed = f"qz_{key}", QUIZ[key]
    s = st.session_state.get(sk)
    con = store.get_con()
    try:
        ok = store.availability(con, ctx.username, ctx.role)
        owners = store.visible_owners(con, ctx.username, ctx.role)
    finally:
        con.close()
    st.markdown(f"## {next(g['icon'] for g in NEW_GAMES if g['key'] == key)} {GAME_TITLE[key]}")
    voice.toggle_ui(f"{sk}_narr")
    if not s:
        levels_ok = [lv for lv in LEVELS if ok("level", lv)]
        cats_ok = [c for c in CATEGORIES if ok("category", c)]
        types_ok = [t for t in fixed if ok("qtype", t)]
        if not (levels_ok and cats_ok and types_ok):
            st.warning("Tu docente desactivó todos los niveles, categorías o tipos de este juego.")
            return
        default_cat = st.session_state.get("lib_cat")
        a, b = st.columns(2)
        cat = a.selectbox("Categoría", ["Todas"] + cats_ok, index=(cats_ok.index(default_cat) + 1) if default_cat in cats_ok else 0, key=f"{sk}_cat")
        level = b.selectbox("Nivel", ["Mixta · de fácil a experto"] + levels_ok, key=f"{sk}_lvl",
                            format_func=lambda v: v if v.startswith("Mixta") else f"{LEVEL_ICON[v]} {v}")
        chosen_types = types_ok
        if len(types_ok) > 1:
            chosen_types = st.multiselect("Tipos de pregunta", types_ok, default=types_ok, format_func=lambda t: QTYPES[t], key=f"{sk}_types") or types_ok
        n = st.slider("Número de preguntas", 4, 15, 8, key=f"{sk}_n")
        st.caption("Cada estudiante recibe una selección y un orden distintos, y no verás una pregunta repetida hasta completar todo el banco.")
        if _btn("🚀 Comenzar", key=f"{sk}_start", type="primary"):
            con = store.get_con()
            try:
                cats = None if cat == "Todas" else [cat]
                if level.startswith("Mixta"):
                    qs, cycled = store.pick_mixed(con, ctx.username, categories=cats or cats_ok, qtypes=chosen_types, n=n, owners=owners, levels=levels_ok)
                else:
                    qs, cycled = store.pick_for_user(con, ctx.username, categories=cats or cats_ok, levels=[level], qtypes=chosen_types, n=n, owners=owners)
            finally:
                con.close()
            if not qs:
                st.error("No hay preguntas con esos filtros. Prueba otra categoría, nivel o tipo.")
            else:
                st.session_state[sk] = {"qs": qs, "i": 0, "res": [], "nonce": secrets.token_hex(4), "cycled": cycled, "answered": None, "saved": False}
                st.rerun()
        return
    qs, i = s["qs"], s["i"]
    if i >= len(qs):
        _qz_summary(ctx, key, sk, s)
        return
    q = qs[i]
    st.markdown(_dots(i, len(qs)), unsafe_allow_html=True)
    if s["cycled"] and i == 0:
        st.info("♻️ ¡Ya viste casi todo el banco! Te repetimos las preguntas que viste hace más tiempo.")
    st.markdown(f"<div class='eg-qcard eg-pop'><span class='eg-chip'>{CAT_ICON[q['category']]} {esc(q['category'])}</span>"
                f"<span class='eg-chip'>{LEVEL_ICON[q['level']]} {esc(q['level'])}</span><span class='eg-chip'>{QTYPES[q['qtype']]}</span>"
                f"<h2>{esc(q['prompt'])}</h2></div>", unsafe_allow_html=True)
    view = engine.present(q, ctx.username, s["nonce"], i)
    ans = s["answered"]
    st.markdown(_QZ_CSS, unsafe_allow_html=True)
    if ans is None:
        sides = [x["label"] for x in view["sides"]] if q["qtype"] == "image" else None
        if voice.narrate(voice.question_line(q["prompt"], q["qtype"], view.get("options"), sides), f"{sk}_q{i}_{s['nonce']}"):
            sound("start", f"{sk}s{i}")
        st.markdown("<span class='eg-speak'>🎙️ El narrador lee la pregunta</span>" if voice.enabled() else "", unsafe_allow_html=True)
        _answer_controls(q, view, sk, ctx.username, f"{sk}_{i}")
    else:
        good = ans["correct"]
        st.markdown(f"<div class='eg-result {'ok' if good else 'bad'}'><div class='big'>{'¡Correcto! +' + str(LEVEL_POINTS[q['level']]) + ' puntos' if good else 'Casi…'}</div>"
                    f"<div>Respuesta: <b>{esc(engine.correct_text(q))}</b></div><div style='margin-top:.4rem'>{esc(q.get('explanation', ''))}</div></div>",
                    unsafe_allow_html=True)
        streak = _streak(s["res"])
        if good and streak >= 2:
            st.markdown(f"<div style='text-align:center'><span class='eg-streak'>🔥 Racha de {streak}</span></div>", unsafe_allow_html=True)
        sound("correct" if good else "wrong", f"{sk}{i}")
        if voice.narrate(f"{voice.cheer(good, streak)} {'' if good else 'La respuesta correcta era: ' + engine.correct_text(q) + '.'} {q.get('explanation', '')}",
                         f"{sk}_a{i}_{s['nonce']}"):
            if good and streak in (3, 5, 8):
                st.balloons()
        _btn("Siguiente ▶" if i + 1 < len(qs) else "Ver resultados 🏁", key=f"{sk}_next_{i}", type="primary", on_click=_qz_next, args=(sk,))


def _answer_controls(q, view, sk: str, username: str, uid: str) -> None:
    kind = q["qtype"]
    if kind in ("mcq", "tf"):
        cols = st.columns(2, gap="medium")
        for idx, option in enumerate(view["options"]):
            with cols[idx % 2]:
                label = option if kind == "mcq" else ("✅ Verdadero" if option == "Verdadero" else "❌ Falso")
                _btn(label, key=f"ans_{idx}_{uid}", on_click=_qz_answer, args=(sk, username, option))
    elif kind == "image":
        left, mid, right = st.columns([5, 1, 5])
        for col, side in ((left, view["sides"][0]), (right, view["sides"][1])):
            with col:
                st.markdown(f"<div class='eg-duel'><div class='em'>{esc(side['emoji'])}</div><div class='lb'>{esc(side['label'])}</div></div>", unsafe_allow_html=True)
                _btn("Elegir", key=f"ans_{0 if side is view['sides'][0] else 1}_{uid}", on_click=_qz_answer, args=(sk, username, side["id"]))
        mid.markdown("<div class='eg-vs'>VS</div>", unsafe_allow_html=True)
    else:
        keys = [f"match_{uid}_{j}" for j in range(len(view["left"]))]
        with st.form(f"form_{uid}"):
            for k, left_item in zip(keys, view["left"]):
                st.selectbox(left_item, view["right"], index=None, placeholder="Elige su pareja…", key=k)
            st.form_submit_button("Comprobar parejas", type="primary", on_click=_qz_match_submit, args=(sk, username, keys, view["left"]))
        if st.session_state.pop("qz_warn", False):
            st.warning("Elige una pareja para cada elemento.")


def _qz_summary(ctx, key: str, sk: str, s: dict) -> None:
    res = s["res"]
    hits = sum(r["correct"] for r in res)
    points = sum(LEVEL_POINTS[r["level"]] for r in res if r["correct"])
    pct = round(100 * hits / max(1, len(res)))
    if not s["saved"]:
        con = store.get_con()
        try:
            store.record_minigame(con, ctx.username, key, points, f"{hits}/{len(res)}")
        finally:
            con.close()
        s["saved"] = True
    medal = "🏆" if pct >= 80 else "🌿" if pct >= 50 else "🌱"
    st.markdown(f"<div class='eg-qcard eg-pop'><div style='font-size:4rem'>{medal}</div><h2>{hits} de {len(res)} aciertos · {pct} %</h2>"
                f"<p>Puntos ganados: <b>{points}</b></p></div>", unsafe_allow_html=True)
    sound("win" if pct >= 60 else "pop", sk)
    if voice.narrate(voice.final_line(hits, len(res), points), f"{sk}_final_{s['nonce']}") and pct >= 80:
        st.balloons()
    if pct >= 80:
        st.success("¡Dominas este nivel! Prueba el siguiente para seguir creciendo.")
    with st.expander("Revisar mis respuestas"):
        for r in res:
            st.markdown(f"{'✅' if r['correct'] else '❌'} **{esc(r['prompt'])}**  \nRespuesta: {esc(r['right'])}")
    a, b = st.columns(2)
    with a:
        _btn("🔁 Jugar otra misión", key=f"{sk}_again", type="primary", on_click=lambda: st.session_state.pop(sk, None))
    with b:
        _btn("Volver a la biblioteca", key=f"{sk}_exit", on_click=lambda: (st.session_state.pop(sk, None), _go("library", None)))


# ── Balloon Bash (juego individual, sin cronómetro) ────────────────────────────
def _balloon_start() -> None:
    st.session_state["inf"] = {
        "value": 0, "target": secrets.randbelow(26) + 65, "status": "playing",
        "score": 0, "pumps": 0, "saved": False, "gid": secrets.token_hex(3),
    }


def _balloon_pump() -> None:
    s = st.session_state.get("inf")
    if not s or s["status"] != "playing":
        return
    # Cada bombeo es un poco impredecible: el jugador debe decidir cuándo parar.
    amount = secrets.randbelow(8) + 5
    s["value"] += amount
    s["pumps"] += 1
    if s["value"] >= 100:
        s["value"] = 100
        s["status"] = "exploded"
        s["score"] = 0


def _balloon_stop() -> None:
    s = st.session_state.get("inf")
    if not s or s["status"] != "playing":
        return
    s["status"] = "stopped"
    # El objetivo secreto cambia en cada partida; premia parar cerca sin reventar.
    distance = abs(s["value"] - s["target"])
    s["score"] = max(0, 100 - distance * 5) if s["value"] < 100 else 0


def _bb_set(mode) -> None:
    st.session_state["bb_mode"] = mode
    if mode is None:
        st.session_state.pop("inf", None); st.session_state.pop("bb_join", None)


def inflate_page(ctx) -> None:
    st.markdown("## 🎈 Balloon Bash")
    mode = st.session_state.get("bb_mode")
    if mode is None:
        st.caption("Elige cómo quieres jugar.")
        a, b, c = st.columns(3, gap="medium")
        with a:
            st.markdown("<div class='eg-card-title'>🎈 Solo</div><div class='eg-card-desc'>Infla el globo a tu ritmo y para antes de que explote.</div>", unsafe_allow_html=True)
            _btn("▶ Jugar solo", key="bb_pick_solo", type="primary", on_click=_bb_set, args=("solo",))
        with b:
            st.markdown("<div class='eg-card-title'>📺 Salón (docente)</div><div class='eg-card-desc'>Memorización a ciegas en el proyector; los alumnos inflan con sus celulares.</div>", unsafe_allow_html=True)
            _btn("📺 Crear sala", key="bb_pick_host", type="primary", disabled=ctx.role == "student", on_click=_bb_set, args=("host",))
        with c:
            st.markdown("<div class='eg-card-title'>📱 Unirme con PIN</div><div class='eg-card-desc'>Usa tu celular o computador como control de la sala.</div>", unsafe_allow_html=True)
            _btn("📱 Unirme", key="bb_pick_play", type="primary", on_click=_bb_set, args=("play",))
        return
    st.button("← Cambiar modo de juego", key="bb_change_mode", on_click=_bb_set, args=(None,))
    if mode == "host" and ctx.role != "student":
        from . import bash_pages; bash_pages.host_page(ctx); return
    if mode == "play":
        from . import bash_pages; bash_pages.play_page(ctx); return
    _balloon_solo(ctx)


def _balloon_solo(ctx) -> None:
    st.caption("Juego individual · Sin cronómetro · Infla con cuidado y decide cuándo parar.")
    s = st.session_state.get("inf")
    if not s:
        st.markdown("""
        <div class="bb-intro">
          <div class="bb-title">¿Hasta dónde te atreves?</div>
          <div class="bb-copy">Cada toque infla el globo un poco más. Cuanto más grande se pone, más se estira y tiembla el personaje. Si te pasas, ¡PUM! No hay reloj: juega a tu ritmo.</div>
          <div class="bb-balloon-mini">🎈</div>
        </div>
        <style>
        .bb-intro{background:linear-gradient(135deg,#142d3d,#285c59);border-radius:24px;padding:26px;text-align:center;color:#fff;margin:8px 0 16px}
        .bb-title{font-size:clamp(1.5rem,3vw,2.3rem);font-weight:900}.bb-copy{max-width:650px;margin:10px auto;line-height:1.55;color:#e8fffa}.bb-balloon-mini{font-size:5rem;animation:bb-float 1.5s ease-in-out infinite}
        @keyframes bb-float{0%,100%{transform:translateY(0) rotate(-5deg)}50%{transform:translateY(-8px) rotate(5deg)}}
        </style>""", unsafe_allow_html=True)
        voice.narrate("Balloon Bash. Infla el globo y detente justo antes de que explote. ¿Te atreves?", "bb_intro")
        _btn("🎈 ¡Empezar Balloon Bash!", key="inf_start", type="primary", on_click=_balloon_start)
        con = store.get_con()
        try: best = store.minigame_best(con, ctx.username, "inflate")
        finally: con.close()
        if best: st.caption(f"Tu mejor puntuación: {best}")
        return

    value = int(s["value"])
    status = s["status"]
    exploded = status == "exploded"
    stopped = status == "stopped"
    if exploded:
        face, reaction, animation = "😱", "¡AAAAH… PUM! ¡El globo explotó!", "bb-pop .35s ease-out both"
    elif stopped:
        face, reaction, animation = ("🕺", "¡Lo lograste! ¡Paraste a tiempo!", "bb-dance .55s ease-in-out infinite") if value >= s["target"]-12 else ("😮‍💨", "¡Uf! Lo paraste… pero te faltó acercarte al límite.", "bb-wobble .6s ease-in-out infinite")
    elif value >= 75:
        face, reaction, animation = "😰💦", "¡Está enorme! ¡Tiembla todo! ¡Decide si paras!", "bb-shake .09s linear infinite"
    elif value >= 45:
        face, reaction, animation = "😬", "¡Uy, uy, uy! Se está poniendo difícil…", "bb-wobble .25s ease-in-out infinite"
    elif value > 0:
        face, reaction, animation = "😤", "¡Sigue inflando… pero no te confíes!", "bb-wobble .7s ease-in-out infinite"
    else:
        face, reaction, animation = "😎", "Todo tranquilo… por ahora.", "bb-wobble 1.2s ease-in-out infinite"

    gid = s.get("gid", "0")
    if exploded:
        voice.narrate("¡Pum! ¡El globo explotó! Inténtalo otra vez y para un poco antes.", f"bb{gid}x")
    elif stopped:
        voice.narrate(f"{reaction} Tu puntuación es {int(s['score'])} de 100.", f"bb{gid}s")
    elif value >= 75:
        voice.narrate("¡Cuidado! ¡Está enorme! ¡Decide si paras!", f"bb{gid}w")
    if exploded:
        sound("wrong", f"bbx{gid}")
    elif stopped and int(s["score"]) >= 60:
        sound("win", f"bbw{gid}")
    balloon_w = max(64, min(260, 64 + value * 1.8))
    balloon_h = max(82, min(310, 82 + value * 2.1))
    st.markdown(f"""
    <style>
    .bb-stage{{background:radial-gradient(circle at 50% 15%,#326a69,#142d3d 72%);border-radius:26px;padding:22px 12px 24px;color:#fff;text-align:center;overflow:hidden;position:relative;min-height:360px}}
    .bb-stage:before{{content:'';position:absolute;inset:0;background:radial-gradient(circle at 15% 20%,#ffffff12 0 2px,transparent 3px),radial-gradient(circle at 80% 70%,#ffffff12 0 2px,transparent 3px);background-size:45px 45px;pointer-events:none}}
    .bb-character{{font-size:clamp(3.2rem,7vw,5.2rem);line-height:1.15;position:relative;display:inline-block;transform-origin:50% 90%;animation:{animation};filter:drop-shadow(0 8px 5px #0004)}}
    .bb-balloon{{width:{balloon_w}px;height:{balloon_h}px;max-width:70vw;margin:12px auto 20px;border-radius:52% 48% 47% 53% / 43% 43% 57% 57%;background:radial-gradient(ellipse at 28% 22%,#fff 0 3%,#ffd8e1 7%,#ff8ba6 23%,#ed426b 67%,#a91d48 100%);box-shadow:inset -17px -18px 25px #78102f66,inset 8px 9px 18px #ffffff66,0 16px 25px #0004;position:relative;transform-origin:50% 100%;animation:{'bb-pop .35s ease-out both' if exploded else animation};transition:width .18s ease,height .18s ease;z-index:1}}
    .bb-balloon:after{{content:'';position:absolute;bottom:-12px;left:calc(50% - 8px);border-left:8px solid transparent;border-right:8px solid transparent;border-top:15px solid #d92d58;filter:drop-shadow(0 3px 2px #0003)}}
    .bb-string{{width:2px;height:35px;background:#f4c5cf;margin:-10px auto 0;opacity:.85}}
    .bb-reaction{{font-size:1.08rem;font-weight:800;margin-top:12px;position:relative}}.bb-meter{{max-width:460px;margin:14px auto 0;background:#ffffff30;border-radius:99px;height:12px;overflow:hidden}}.bb-meter span{{display:block;height:100%;width:{value}%;background:{'#ff4757' if value>=75 else '#ffc857' if value>=45 else '#7de7b0'};border-radius:99px;transition:width .18s}}
    .bb-small{{font-size:.9rem;color:#e0f5f2;margin-top:8px}}@keyframes bb-wobble{{0%,100%{{transform:rotate(-3deg) translateY(0)}}50%{{transform:rotate(3deg) translateY(-3px)}}}}@keyframes bb-shake{{0%,100%{{transform:translateX(-3px) rotate(-4deg)}}50%{{transform:translateX(3px) rotate(4deg)}}}}@keyframes bb-pop{{0%{{transform:scale(1.1);opacity:1}}55%{{transform:scale(1.35);opacity:.8}}100%{{transform:scale(.1);opacity:0}}}}@keyframes bb-dance{{0%,100%{{transform:rotate(-10deg) translateY(0)}}50%{{transform:rotate(10deg) translateY(-12px)}}}}
    </style>
    <div class="bb-stage"><div class="bb-character">{face}</div><div class="bb-balloon"></div><div class="bb-string"></div><div class="bb-reaction">{reaction}</div><div class="bb-meter"><span></span></div><div class="bb-small">Tamaño del globo: {min(value,100)}% · Bombeos: {s['pumps']}</div></div>
    """, unsafe_allow_html=True)

    if status == "playing":
        col1, col2 = st.columns(2)
        with col1: _btn("🎈 ¡Inflar!", key=f"inf_pump_{s['pumps']}", type="primary", on_click=_balloon_pump)
        with col2: _btn("✋ ¡Parar aquí!", key=f"inf_stop_{s['pumps']}", on_click=_balloon_stop)
        st.caption("No hay cuenta atrás. Cada bombeo puede aumentar el tamaño de forma distinta; cuando el globo esté muy grande, también temblará más.")
    else:
        if exploded:
            st.info("¡Se reventó! Esta vez te pasaste. Inténtalo otra vez y para un poco antes.")
            score = 0
        else:
            score = int(s["score"])
            st.success(f"Puntuación: {score}/100 · { '¡Paraste cerca del límite!' if value >= s['target']-12 else 'Puedes acercarte más al límite en el siguiente intento.'}")
        if not s.get("saved"):
            con = store.get_con()
            try: store.record_minigame(con, ctx.username, "inflate", score, "Balloon Bash")
            finally: con.close()
            s["saved"] = True
        _btn("🔁 Jugar otra vez", key="inf_again", type="primary", on_click=_balloon_start)


# ── EcoParty: minijuegos de fiesta y retos ecológicos ─────────────────────────
def _party_leave() -> None:
    st.session_state.pop("party_code", None)
    st.session_state.pop("party_local", None)


def _party_online_submit(code: str, username: str, answer: str) -> None:
    con = store.get_con()
    try:
        party.submit(con, code, username, answer)
    finally:
        con.close()


def party_page(ctx) -> None:
    code = st.session_state.get("party_code")
    if code:
        @_fragment("1s")
        def live_party():
            con = store.get_con()
            try:
                room = party.tick(con, code)
                if not room:
                    st.warning("La sala ya no existe.")
                    st.button("Volver", on_click=_party_leave, key="party_gone_back")
                    return
                people = party.players(con, code)
                is_host = room["host"] == ctx.username
                st.markdown(f"<div class='eg-qcard'><div class='eg-kicker'>🎉 ECOPARTY · {esc(room['title'])}</div><div class='eg-pin'>{esc(room['code'])}</div><p>{len(people)}/{party.MAX_PLAYERS} jugadores · Ronda {min(room['round_no'], room['rounds'])}/{room['rounds']}</p></div>", unsafe_allow_html=True)
                if room['status'] == 'lobby':
                    st.markdown("### 👋 ¡Que se una el grupo!")
                    st.markdown(" · ".join(esc(p['display']) for p in people))
                    st.caption("Comparte el PIN con los demás. Máximo 12 jugadores.")
                    if is_host:
                        st.button("🚀 ¡Empezar la fiesta!", type="primary", disabled=len(people)<2, key="party_start", on_click=_party_start_cb, args=(code, ctx.username))
                    else: st.info("Esperando a que el anfitrión empiece…")
                elif room['status'] == 'question':
                    q = room['snapshot'][room['round_no']-1]
                    st.markdown(f"### {q['title']}")
                    st.markdown(f"## {q['prompt']}")
                    if is_host:   # el dispositivo del anfitrión (proyector) hace de locutor
                        voice.narrate(f"Reto {room['round_no']}. " + (f"{q['prompt']} ¡A inflar!" if q.get("type") == "balloon" else voice.question_line(q['prompt'], "mcq", q['options'])),
                                      f"party_q_{code}_{room['round_no']}")
                    if q.get("type") == "balloon":
                        bstate = party.balloon_state(con, code, room['round_no'], ctx.username)
                        inflation = int(bstate["inflation"])
                        st.markdown(f"""<style>
                        @keyframes eg-wobble {{0%,100%{{transform:rotate(-2deg) translateY(0)}}50%{{transform:rotate(2deg) translateY(-3px)}}}}
                        @keyframes eg-shake {{0%,100%{{transform:translateX(0)}}25%{{transform:translateX(-4px)}}75%{{transform:translateX(4px)}}}}
                        .eg-balloon-stage{{background:linear-gradient(135deg,#142e27,#244b3a);border-radius:22px;padding:22px 12px 16px;text-align:center;color:#fff;overflow:hidden}}
                        .eg-balloon{{width:{max(44,min(190,45+inflation*1.45))}px;height:{max(60,min(220,60+inflation*1.55))}px;margin:12px auto 20px;border-radius:50% 50% 46% 46%;background:radial-gradient(circle at 30% 25%,#fff9 0 5%,#ffbdc9 15%,#f05b7c 70%,#bb2852 100%);box-shadow:inset -12px -10px 20px #8b174855,0 12px 24px #0004;position:relative;animation:{'eg-shake .12s infinite' if inflation >= 65 and not bstate['exploded'] else 'eg-wobble 1.1s infinite'};transition:width .15s,height .15s}}
                        .eg-balloon:after{{content:'';position:absolute;bottom:-10px;left:calc(50% - 7px);border-left:7px solid transparent;border-right:7px solid transparent;border-top:12px solid #df4266}}
                        .eg-avatar{{font-size:54px;line-height:1.15;animation:{'eg-shake .12s infinite' if inflation >= 65 and not bstate['exploded'] else 'none'}}}
                        .eg-balloon-caption{{opacity:.88;font-size:.95rem}}
                        </style><div class='eg-balloon-stage'><div class='eg-avatar'>{'😵‍💫💦' if bstate['exploded'] else ('😰💦' if inflation >= 65 else ('😤' if inflation else '😎'))}</div><div class='eg-balloon'></div><div><b>{'¡PUM! ¡El globo explotó!' if bstate['exploded'] else f'{inflation}% de presión'}</b></div><div class='eg-balloon-caption'>{'Esta ronda ya no se puede salvar.' if bstate['exploded'] else ('¡Está temblando! ¡Detente a tiempo!' if inflation >= 65 else 'Pulsa para inflar; detente cerca del tamaño objetivo.')}</div></div>""", unsafe_allow_html=True)
                        if not bstate["stopped"] and not bstate["exploded"]:
                            c1,c2 = st.columns(2)
                            with c1:
                                if st.button("🎈 ¡Inflar!", type="primary", key=f"party_balloon_pump_{code}_{room['round_no']}"):
                                    party.balloon_pump(con, code, ctx.username, 1); st.rerun()
                            with c2:
                                if st.button("✋ ¡Parar!", key=f"party_balloon_stop_{code}_{room['round_no']}"):
                                    party.balloon_stop(con, code, ctx.username); st.rerun()
                        elif bstate["exploded"] and not bstate["stopped"]:
                            if st.button("Registrar explosión", key=f"party_balloon_burst_{code}_{room['round_no']}"):
                                party.balloon_stop(con, code, ctx.username); st.rerun()
                        mine = party.my_answer(con, code, room['round_no'], ctx.username)
                        if mine: st.success(f"Resultado registrado: {mine['points']} puntos.")
                        st.caption(f"{sum(1 for p in people if party.my_answer(con, code, room['round_no'], p['username']))}/{len(people)} jugadores terminaron · puedes inflar con toques en móvil o clic en PC.")
                        return
                    mine = party.my_answer(con, code, room['round_no'], ctx.username)
                    if mine:
                        st.success("¡Respuesta recibida! Esperando al resto o al final del tiempo…")
                        st.caption(f"Tu puntuación en esta ronda: {mine['points']} puntos")
                    else:
                        with st.form(f"party_answer_{code}_{room['round_no']}"):
                            answer = st.radio("Elige tu respuesta", q['options'], index=None)
                            send = st.form_submit_button("⚡ ¡Responder!", type="primary")
                        if send:
                            if answer is None: st.warning("Elige una respuesta antes de enviar.")
                            else:
                                res = party.submit(con, code, ctx.username, answer)
                                if res == 'ok': st.rerun()
                                elif res == 'duplicate': st.info("Ya respondiste esta ronda.")
                                else: st.warning("No se pudo registrar la respuesta. Intenta actualizar la sala.")
                    st.caption(f"{sum(1 for p in people if party.my_answer(con, code, room['round_no'], p['username']))}/{len(people)} respuestas recibidas · la pantalla se actualiza automáticamente")
                elif room['status'] == 'reveal':
                    q = room['snapshot'][room['round_no']-1]
                    mine = party.my_answer(con, code, room['round_no'], ctx.username)
                    st.markdown(f"### {q['title']} · Resultado")
                    if q.get("type") == "balloon":
                        if mine:
                            st.markdown("## 🎈 Resultado de tu globo")
                            st.markdown(f"**Inflado final:** {esc(mine['answer'])}% · **Puntos:** {mine['points']}")
                            st.markdown("🎉 ¡Precisión de campeonato!" if mine['correct'] else "💥 ¡La próxima vez, detente más cerca del objetivo!")
                        else:
                            st.info("No terminaste de inflar el globo en esta ronda.")
                        st.write(q['why'])
                    else:
                        st.markdown(f"## { '✅' if mine and mine['correct'] else '🌱' } Respuesta correcta: {esc(q['answer'])}")
                        st.write(q['why'])
                        if mine: st.success(f"Sumaste {mine['points']} puntos en este reto." if mine['correct'] else "Esta vez no sumaste puntos. ¡Vamos al siguiente!")
                        else: st.info("No enviaste respuesta en esta ronda.")
                    st.caption("Siguiente reto en unos segundos…")
                    if is_host:
                        voice.narrate("¡Tiempo! " + (f"La respuesta correcta es: {q['answer']}. " if q.get("type") != "balloon" else "") + q['why'], f"party_a_{code}_{room['round_no']}")
                else:
                    st.markdown("## 🏆 ¡Fin de la fiesta!")
                    board = party.leaderboard(con, code)
                    for i, p in enumerate(board, 1): st.markdown(f"**{i}. {esc(p['display'])}** — {p['points']} puntos")
                    if board: st.balloons()
                    if is_host and board:
                        voice.narrate(f"¡Fin de la fiesta! Gana {board[0]['display']} con {board[0]['points']} puntos. ¡Qué gran partida, guardianes!", f"party_end_{code}")
                    st.button("Salir de EcoParty", key="party_finish_leave", on_click=_party_leave)
            finally:
                con.close()
        live_party()
        return

    _hero("🎉 EcoParty", "¡12 jugadores, una sola fiesta!", "Minijuegos rápidos que mezclan reflejos, decisiones ecológicas y competencia amistosa. Juega en una pantalla o conecta dispositivos con un PIN.")
    mode = st.radio("¿Cómo quieren jugar?", ["En línea · cada jugador con su dispositivo", "En el mismo dispositivo · por turnos"], horizontal=True, key="party_mode")
    if mode.startswith("En el mismo"):
        _party_local(ctx)
        return
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("### 🚪 Unirme a una fiesta")
        with st.form("party_join_form"):
            pin = st.text_input("PIN de 6 dígitos", max_chars=6, key="party_join_pin").strip()
            join = st.form_submit_button("Entrar a EcoParty", type="primary")
        if join:
            con = store.get_con()
            try: result = party.join(con, pin, ctx.username, ctx.display or ctx.username)
            finally: con.close()
            if result == 'ok': st.session_state['party_code'] = pin; st.rerun()
            elif result == 'full': st.error("La sala ya tiene 12 jugadores.")
            elif result == 'started': st.warning("La partida ya comenzó; no se pueden añadir jugadores.")
            else: st.error("No encontramos esa sala. Revisa el PIN.")
    with right:
        st.markdown("### ✨ Crear una fiesta")
        with st.form("party_create_form"):
            rounds = st.slider("Número de minijuegos", 3, 12, 8, key="party_rounds")
            seconds = st.slider("Segundos por reto", 8, 45, 15, key="party_seconds")
            create = st.form_submit_button("Crear sala y obtener PIN", type="primary")
        if create:
            con = store.get_con()
            try: new_code = party.create_room(con, ctx.username, ctx.display or ctx.username, rounds, seconds)
            finally: con.close()
            st.session_state['party_code'] = new_code
            st.rerun()
    st.info("Para jugar desde distintos dispositivos, todos deben abrir la misma instalación de EcoGuardian AI. El modo local funciona en una sola pantalla sin conexión adicional.")


def _party_start_cb(code: str, username: str) -> None:
    con = store.get_con()
    try: party.start(con, code, username)
    finally: con.close()


def _party_local(ctx) -> None:
    state = st.session_state.get("party_local")
    if not state:
        with st.form("party_local_setup"):
            names = st.text_area("Nombres de los jugadores (uno por línea, máximo 12)", value="Jugador 1\nJugador 2", height=120)
            rounds = st.slider("Minijuegos", 3, 12, 6, key="party_local_rounds")
            start = st.form_submit_button("🎉 Preparar fiesta", type="primary")
        if start:
            roster = list(dict.fromkeys(n.strip()[:30] for n in names.splitlines() if n.strip()))[:party.MAX_PLAYERS]
            if len(roster) < 2:
                st.warning("Escribe al menos dos nombres diferentes.")
                return
            rng = engine.seeded_rng("local-party", ctx.username, engine.now_ms())
            qs = list(party.GAMES); rng.shuffle(qs)
            st.session_state["party_local"] = {"names": roster, "scores": {n: 0 for n in roster}, "qs": qs[:rounds], "round": 0, "turn": 0, "answers": []}
            st.rerun()
        return
    if state["round"] >= len(state["qs"]):
        st.markdown("## 🏆 ¡EcoParty terminada!")
        board = sorted(state["scores"].items(), key=lambda x: -x[1])
        for i, (name, score) in enumerate(board, 1): st.markdown(f"**{i}. {esc(name)}** — {score} puntos")
        st.balloons()
        voice.narrate(f"¡EcoParty terminada! Gana {board[0][0]} con {board[0][1]} puntos. ¡Felicitaciones, guardianes!", f"plocal_end_{state.setdefault('gid', secrets.token_hex(3))}")
        st.button("Jugar otra vez", key="party_local_again", on_click=lambda: st.session_state.pop("party_local", None))
        return
    q = state["qs"][state["round"]]
    player = state["names"][state["turn"]]
    st.progress(state["round"] / len(state["qs"]), text=f"Minijuego {state['round']+1} de {len(state['qs'])}")
    st.markdown(f"### {q['title']} · Turno de **{esc(player)}**")
    st.markdown(f"## {q['prompt']}")
    voice.toggle_ui("plocal_narr")
    voice.narrate(f"Turno de {player}. " + (f"{q['prompt']} ¡A inflar!" if q.get("type") == "balloon" else voice.question_line(q['prompt'], "mcq", q['options'])),
                  f"plocal_q_{state.setdefault('gid', secrets.token_hex(3))}_{state['round']}_{state['turn']}")
    if q.get("type") == "balloon":
        levels = state.setdefault("balloon_levels", {})
        key = f"{state['round']}:{player}"
        level = int(levels.get(key, 0))
        exploded = level >= 100
        st.markdown("<style>@keyframes local-wobble{0%,100%{transform:rotate(-2deg)}50%{transform:rotate(2deg)}}.local-balloon-stage{background:linear-gradient(135deg,#142e27,#244b3a);padding:20px;border-radius:20px;text-align:center;color:white}.local-avatar{font-size:54px}.local-balloon{margin:14px auto;border-radius:50%;background:radial-gradient(circle at 30% 25%,#fff9 0 5%,#ffbdc9 15%,#f05b7c 70%,#bb2852 100%);box-shadow:inset -12px -10px 20px #8b174855;animation:local-wobble .12s infinite}</style><div class='local-balloon-stage'><div class='local-avatar'>" + ('😵‍💫💦' if exploded else ('😰💦' if level>=65 else ('😤' if level else '😎'))) + "</div><div class='local-balloon' style='width:" + str(max(44,min(190,45+level*1.45))) + "px;height:" + str(max(60,min(220,60+level*1.55))) + "px;animation-duration:" + ('.12s' if level>=65 and not exploded else '1.1s') + "'></div><b>" + ('¡PUM! ¡Explotó!' if exploded else f'{level}% de presión') + "</b><p>" + ('Ronda perdida.' if exploded else ('¡Está temblando! Detente a tiempo.' if level>=65 else 'Infla con cuidado y detente cerca del objetivo.')) + "</p></div>", unsafe_allow_html=True)
        if not exploded and level < 100:
            c1,c2=st.columns(2)
            with c1:
                if st.button("🎈 ¡Inflar!", type="primary", key=f"local_balloon_pump_{state['round']}_{state['turn']}"):
                    level=min(100,level+4); levels[key]=level; state['balloon_levels']=levels; st.session_state['party_local']=state; st.rerun()
            with c2:
                if st.button("✋ ¡Parar!", key=f"local_balloon_stop_{state['round']}_{state['turn']}"):
                    points=max(0,100-abs(level-75)*4) if level<100 else 0
                    state['scores'][player]+=points
                    state['answers'].append({"player":player,"correct":68<=level<=82,"points":points,"inflation":level})
                    if state['turn']+1>=len(state['names']): state['round']+=1; state['turn']=0; state['answers']=[]
                    else: state['turn']+=1
                    st.session_state['party_local']=state; st.rerun()
        else:
            if st.button("💥 Registrar globo reventado", key=f"local_balloon_burst_{state['round']}_{state['turn']}"):
                state['answers'].append({"player":player,"correct":False,"points":0,"inflation":level})
                if state['turn']+1>=len(state['names']): state['round']+=1; state['turn']=0; state['answers']=[]
                else: state['turn']+=1
                st.session_state['party_local']=state; st.rerun()
        st.caption("Modo local: pasa el dispositivo al siguiente jugador cuando termine el turno.")
        return
    with st.form(f"party_local_answer_{state['round']}_{state['turn']}"):
        answer = st.radio("Elige tu respuesta", q['options'], index=None)
        send = st.form_submit_button("Confirmar respuesta", type="primary")
    if send:
        if answer is None: st.warning("Elige una respuesta.")
        else:
            good = answer == q['answer']; points = 100 if good else 0
            state['scores'][player] += points
            state['answers'].append({"player": player, "correct": good, "points": points})
            st.session_state["party_local"] = state
            if state['turn'] + 1 >= len(state['names']):
                state['round'] += 1; state['turn'] = 0; state['answers'] = []
            else: state['turn'] += 1
            st.session_state["party_local"] = state
            st.rerun()
    st.caption("Modo de una sola pantalla: pasen el dispositivo por turnos y no miren las respuestas de los demás.")
    if st.button("Terminar partida", key="party_local_end"):
        state['round'] = len(state['qs']); st.session_state['party_local'] = state; st.rerun()


# ── Arena en vivo ─────────────────────────────────────────────────────────────
def _cb_answer(code: str, user: str, answer) -> None:
    t = engine.now_ms()                       # la marca de tiempo se toma antes que cualquier otra cosa
    con = store.get_con()
    try:
        arena.submit(con, code, user, answer, t)
    finally:
        con.close()


def _cb_match(code: str, user: str, keys: list, lefts: list) -> None:
    t = engine.now_ms()
    vals = [st.session_state.get(k) for k in keys]
    if any(v is None for v in vals):
        st.session_state["arena_warn"] = True
        return
    con = store.get_con()
    try:
        arena.submit(con, code, user, dict(zip(lefts, vals)), t)
    finally:
        con.close()


def _cb_host(action: str, code: str, user: str) -> None:
    con = store.get_con()
    try:
        {"start": arena.start, "skip": arena.skip, "finish": arena.finish}[action](con, code, user)
    finally:
        con.close()


def _cb_leave() -> None:
    st.session_state.pop("arena_code", None)


def arena_page(ctx) -> None:
    code = st.session_state.get("arena_code")
    if code:
        con = store.get_con()
        try:
            room = arena.get_room(con, code)
        finally:
            con.close()
        if room:
            _arena_live(ctx, code)
            return
        st.session_state.pop("arena_code", None)
    _hero("🏟️ Arena en vivo", "Campeonatos al instante", "Entra con el PIN de tu docente o crea tu propia batalla. Responde rápido, acierta y escala en el ranking.")
    can_host = ctx.role in ("teacher", "admin")
    left, right = st.columns(2, gap="large") if can_host else (st.container(), None)
    with left:
        st.markdown("### 🚪 Unirme con un PIN")
        with st.form("arena_join"):
            pin = st.text_input("PIN de la sala (6 dígitos)", max_chars=6).strip()
            team = st.text_input("Tu salón o colegio (solo torneos por equipos)", max_chars=30)
            go = st.form_submit_button("Entrar a la arena", type="primary")
        if go:
            gk = f"arenapin:{ctx.username}"
            wait = ctx.guard_remaining(gk)
            if wait:
                st.error(ctx.lock_message(wait))
            else:
                con = store.get_con()
                try:
                    res = arena.join(con, pin, ctx.username, ctx.display or ctx.username, team)
                finally:
                    con.close()
                if res == "ok":
                    ctx.guard_clear(gk)
                    st.session_state["arena_code"] = pin
                    st.rerun()
                elif res == "team_required":
                    st.warning("Este torneo es por equipos: escribe tu salón o colegio.")
                elif res == "finished":
                    st.info("Ese campeonato ya terminó.")
                else:
                    ctx.guard_fail(gk)
                    st.error("No encontramos esa sala. Revisa el PIN.")
    if can_host:
        with right:
            _arena_create(ctx)


def _arena_create(ctx) -> None:
    st.markdown("### ➕ Crear campeonato")
    con = store.get_con()
    try:
        ok = store.availability(con, ctx.username, ctx.role)
        owners = store.visible_owners(con, ctx.username, ctx.role)
        mine = arena.list_host_rooms(con, ctx.username)
    finally:
        con.close()
    levels_ok, cats_ok = [lv for lv in LEVELS if ok("level", lv)], [c for c in CATEGORIES if ok("category", c)]
    types_ok = [t for t in QTYPES if ok("qtype", t)]
    with st.form("arena_create"):
        title = st.text_input("Nombre del campeonato", value="Batalla ecológica", max_chars=80)
        mode = st.selectbox("Modalidad", list(arena.MODES), format_func=lambda m: arena.MODES[m])
        a, b = st.columns(2)
        cat = a.selectbox("Categoría", ["Todas"] + cats_ok)
        level = b.selectbox("Dificultad", ["Mixta"] + levels_ok, format_func=lambda v: "Mixta · de fácil a experto" if v == "Mixta" else f"{LEVEL_ICON[v]} {v}")
        qtypes = st.multiselect("Tipos de pregunta", types_ok, default=[t for t in ("mcq", "tf", "image") if t in types_ok], format_func=lambda t: QTYPES[t])
        c, d = st.columns(2)
        rounds = c.slider("Rondas", 3, 20, 8)
        seconds = d.slider("Segundos por ronda", 5, 60, 20)
        e, f = st.columns(2)
        tie = e.selectbox("Ventana de empate", [0, 5, 20, 50], format_func=lambda v: "Exacto (mismo milisegundo)" if v == 0 else f"±{v} ms",
                          help="Si dos respuestas correctas llegan dentro de esta ventana, se repite la ronda entre esas personas.")
        reveal = f.slider("Segundos de resultados", 4, 15, 7)
        go = st.form_submit_button("Crear sala y obtener PIN", type="primary")
    if go:
        try:
            con = store.get_con()
            try:
                code = arena.create_room(con, ctx.username, title=title, mode=mode, category=None if cat == "Todas" else cat, level=level,
                                         qtypes=qtypes, rounds=rounds, seconds=seconds, reveal_seconds=reveal, tie_ms=tie, owners=owners,
                                         allowed_levels=levels_ok, allowed_categories=cats_ok)
            finally:
                con.close()
            st.session_state["arena_code"] = code
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    if mine:
        with st.expander("Mis campeonatos recientes"):
            for r in mine:
                x, y = st.columns([4, 1])
                x.markdown(f"**{esc(r['title'])}** · PIN `{r['code']}` · {r['status']}")
                y.button("Abrir", key=f"open_{r['code']}", on_click=lambda c=r["code"]: st.session_state.update(arena_code=c))


def _static_options(q: dict) -> str:
    if q["qtype"] == "mcq":
        items = [q["correct"]] + list(q["wrong"])
        items.sort()
    elif q["qtype"] == "tf":
        items = ["Verdadero", "Falso"]
    elif q["qtype"] == "image":
        items = [f"{q['a']['emoji']} {q['a']['label']}", f"{q['b']['emoji']} {q['b']['label']}"]
    else:
        items = [a for a, _ in q["pairs"]]
    return "<div class='eg-chiprow'>" + "".join(f"<span class='eg-chip'>{esc(i)}</span>" for i in items) + "</div>"


def _arena_live(ctx, code: str) -> None:
    @_fragment("1s")
    def live():
        con = store.get_con()
        try:
            room = arena.tick(con, code)
            if not room:
                st.warning("La sala ya no existe.")
                return
            user, is_host = ctx.username, room["host"] == ctx.username
            status = room["status"]
            ppl = arena.players(con, code)
            title = f"{esc(room['title'])} · {arena.MODES[room['mode']]}"
            if status == "lobby":
                _arena_lobby(ctx, room, ppl, title, is_host)
            elif status == "question":
                _arena_question(ctx, con, room, ppl, title, is_host)
            elif status == "reveal":
                _arena_reveal(ctx, con, room, title, is_host)
            else:
                _arena_final(ctx, con, room, title, is_host)
        finally:
            con.close()
    live()


def _arena_lobby(ctx, room, ppl, title, is_host) -> None:
    st.markdown(f"<div class='eg-qcard'><div class='eg-kicker'>{title}</div><div>Entra con el PIN</div><div class='eg-pin'>{room['code']}</div></div>", unsafe_allow_html=True)
    chips = "".join(f"<span class='eg-player'>{esc(p['display'])}{(' · ' + esc(p['team'])) if p['team'] else ''}</span>" for p in ppl)
    st.markdown(f"<div class='eg-chiprow'>{chips or 'Esperando jugadores…'}</div>", unsafe_allow_html=True)
    st.caption(f"{len(ppl)} jugador(es) conectados · {room['rounds']} rondas · {room['seconds']} s por ronda")
    if is_host:
        st.button("▶ Iniciar campeonato", key="arena_start", type="primary", disabled=not ppl, on_click=_cb_host, args=("start", room["code"], ctx.username))
    else:
        st.info("Esperando a que el anfitrión inicie…")
    st.button("Salir de la sala", key="arena_leave", on_click=_cb_leave)


def _arena_question(ctx, con, room, ppl, title, is_host) -> None:
    q, rk = arena.current_question(room), arena.round_key(room)
    now = engine.now_ms()
    remaining = max(0, arena.deadline_ms(room) - now)
    expected = len(room["eligible"]) if room["eligible"] is not None else len(ppl)
    answered = arena.answer_count(con, room)
    tkey = f"tm_{room['code']}_{rk}"
    if tkey not in st.session_state:                    # HTML idéntico en cada sondeo: la animación CSS no se reinicia
        st.session_state[tkey] = f"<div class='eg-timer'><div style='animation:eg-shrink {remaining / 1000:.2f}s linear forwards'></div></div>"
    tie_tag = " · ⚖️ DESEMPATE" if room["replay"] else ""
    st.markdown(f"<div class='eg-kicker'>{title}</div>", unsafe_allow_html=True)
    st.markdown(f"**Ronda {room['round_no']}/{room['rounds']}{tie_tag}** · {LEVEL_ICON[q['level']]} {q['level']} · ⏱️ {math.ceil(remaining / 1000)} s · 🙋 {answered}/{expected}")
    st.markdown(st.session_state[tkey], unsafe_allow_html=True)
    st.markdown(f"<div class='eg-qcard'><span class='eg-chip'>{QTYPES[q['qtype']]}</span><h2>{esc(q['prompt'])}</h2></div>", unsafe_allow_html=True)
    if is_host:
        voice.narrate(f"Ronda {room['round_no']}. " + voice.question_line(q["prompt"], q["qtype"]), f"arena_q_{room['code']}_{rk}")
        st.markdown(_static_options(q), unsafe_allow_html=True)
        st.caption("Cada estudiante ve las opciones en un orden distinto.")
        st.button("⏭ Cerrar ronda ahora", key="arena_skip", on_click=_cb_host, args=("skip", room["code"], ctx.username))
        return
    if room["eligible"] is not None and ctx.username not in room["eligible"]:
        st.info("⚔️ Duelo de desempate: observa cómo se resuelve.")
        return
    mine = arena.my_answer(con, room, ctx.username)
    if mine:
        st.success("✅ Respuesta enviada. Esperando a los demás…")
        return
    if not any(p["username"] == ctx.username for p in ppl):
        st.warning("No estás inscrito en esta sala.")
        return
    view = engine.present(q, "arena", room["code"], rk, ctx.username)
    uid = f"{room['code']}_{rk.replace('.', '_')}_{ctx.username}"
    kind = q["qtype"]
    if kind in ("mcq", "tf"):
        cols = st.columns(2, gap="medium")
        for idx, option in enumerate(view["options"]):
            with cols[idx % 2]:
                _btn(option if kind == "mcq" else ("✅ Verdadero" if option == "Verdadero" else "❌ Falso"), key=f"ans_{idx}_{uid}",
                     on_click=_cb_answer, args=(room["code"], ctx.username, option))
    elif kind == "image":
        l, m, r = st.columns([5, 1, 5])
        for idx, (col, side) in enumerate(zip((l, r), view["sides"])):
            with col:
                st.markdown(f"<div class='eg-duel'><div class='em'>{esc(side['emoji'])}</div><div class='lb'>{esc(side['label'])}</div></div>", unsafe_allow_html=True)
                _btn("Elegir", key=f"ans_{idx}_{uid}", on_click=_cb_answer, args=(room["code"], ctx.username, side["id"]))
        m.markdown("<div class='eg-vs'>VS</div>", unsafe_allow_html=True)
    else:
        keys = [f"am_{uid}_{j}" for j in range(len(view["left"]))]
        with st.form(f"af_{uid}"):
            for k, item in zip(keys, view["left"]):
                st.selectbox(item, view["right"], index=None, placeholder="Elige su pareja…", key=k)
            st.form_submit_button("Enviar", type="primary", on_click=_cb_match, args=(room["code"], ctx.username, keys, view["left"]))
        if st.session_state.pop("arena_warn", False):
            st.warning("Elige una pareja para cada elemento.")


def _board(con, room, me: str, show_delta: bool = True) -> None:
    rows = arena.leaderboard(con, room["code"])
    page, height = media.leaderboard_html(rows, me, room["code"], show_delta)
    components.html(page, height=height)
    if room["mode"] in arena.TEAM_MODES:
        teams = arena.team_board(con, room["code"])
        if teams:
            st.markdown(f"#### 🏫 Clasificación por {arena.TEAM_MODES[room['mode']].lower()}es (promedio por jugador)")
            for t in teams:
                st.markdown(f"**{t['rank']}. {esc(t['team'])}** — promedio {t['avg']} · total {t['points']} · {t['members']} jugador(es)")


def _arena_reveal(ctx, con, room, title, is_host) -> None:
    lr = room["last_result"] or {}
    mine = (lr.get("per_user") or {}).get(ctx.username)
    st.markdown(f"<div class='eg-kicker'>{title}</div>", unsafe_allow_html=True)
    names = {p["username"]: p["display"] for p in arena.players(con, room["code"])}
    if lr.get("tie") and lr.get("replay_next"):
        who = " y ".join(esc(names.get(u, u)) for u in lr["fastest"])
        st.markdown(f"<div class='eg-result tie'><div class='big'>⚖️ ¡Empate exacto!</div><div>{who} acertaron en el mismo instante. "
                    f"Ronda de desempate con una pregunta nueva.</div></div>", unsafe_allow_html=True)
        if not is_host:
            sound("tie", room["code"] + lr["round_key"])
    else:
        if is_host or not mine:
            cls, head = "ok" if lr.get("fastest") else "bad", "Resultados de la ronda"
        else:
            cls, head = ("ok", f"¡Correcto! +{mine['points']}") if mine["correct"] else ("bad", "Esta vez no")
        fast = ("⚡ Más rápido: " + ", ".join(esc(names.get(u, u)) for u in lr.get("fastest", []))) if lr.get("fastest") else "Nadie acertó esta ronda."
        st.markdown(f"<div class='eg-result {cls}'><div class='big'>{head}</div><div>Respuesta: <b>{esc(lr.get('correct_text', ''))}</b></div>"
                    f"<div>{fast}</div><div style='margin-top:.4rem'>{esc(lr.get('explanation', ''))}</div></div>", unsafe_allow_html=True)
        if not is_host:
            sound("correct" if mine and mine["correct"] else "wrong", room["code"] + lr.get("round_key", ""))
    if is_host and not lr.get("replay_next"):
        top = ", ".join(names.get(u, u) for u in lr.get("fastest", []))
        voice.narrate(f"¡Tiempo! La respuesta correcta es: {lr.get('correct_text', '')}. {lr.get('explanation', '')} " + (f"El más rápido fue {top}." if top else "Nadie acertó esta ronda."),
                      f"arena_a_{room['code']}_{lr.get('round_key', '')}")
    elif is_host:
        voice.narrate("¡Empate exacto! Habrá una ronda de desempate.", f"arena_t_{room['code']}_{lr.get('round_key', '')}")
    _board(con, room, ctx.username)
    if is_host:
        st.button("⏭ Siguiente", key="arena_next", type="primary", on_click=_cb_host, args=("skip", room["code"], ctx.username))
        st.button("🏁 Terminar campeonato", key="arena_end", on_click=_cb_host, args=("finish", room["code"], ctx.username))


def _arena_final(ctx, con, room, title, is_host) -> None:
    st.markdown(f"<div class='eg-qcard eg-pop'><div class='eg-kicker'>{title}</div><div style='font-size:3.4rem'>🏆</div><h2>¡Campeonato terminado!</h2></div>", unsafe_allow_html=True)
    sound("win", room["code"])
    if is_host:
        top = arena.leaderboard(con, room["code"])
        voice.narrate("¡Campeonato terminado! " + (f"¡Felicitaciones a {top[0].get('display') or top[0].get('username')}, que gana con {top[0]['points']} puntos!" if top else ""), f"arena_end_{room['code']}")
    flag = f"balloons_{room['code']}"
    if not st.session_state.get(flag):
        st.session_state[flag] = True
        st.balloons()
    _board(con, room, ctx.username, show_delta=False)
    if is_host:
        st.download_button("⬇️ Descargar resultados (CSV)", arena.results_csv(con, room["code"]), file_name=f"campeonato_{room['code']}.csv", mime="text/csv")
    st.button("Salir de la sala", key="arena_leave_end", on_click=_cb_leave)


# ── Interruptores de juegos, niveles, categorías y tipos ──────────────────────
def _save_pref(owner: str, kind: str, key: str, wkey: str) -> None:
    con = store.get_con()
    try:
        store.set_pref(con, owner, kind, key, bool(st.session_state.get(wkey)))
    finally:
        con.close()


def toggles_panel(ctx, master: bool = False) -> None:
    owner = "*" if master else ctx.username
    st.markdown(f"## 🎛️ {'Interruptores maestros' if master else 'Juegos y niveles de mis clases'}")
    st.write("Activa o desactiva lo que verán " + ("**todos los usuarios**." if master else "**tus estudiantes**.") + " Los cambios se guardan al instante.")
    con = store.get_con()
    try:
        prefs, admin = store.get_prefs(con, owner), store.get_prefs(con, "*")
        per_level = {lv: con.execute("SELECT COUNT(*) FROM eco_questions WHERE active=1 AND level=?", (lv,)).fetchone()[0] for lv in LEVELS}
    finally:
        con.close()

    def toggle(kind: str, key: str, label: str, help_: str | None = None) -> None:
        locked = (not master) and not admin.get((kind, key), True)
        wkey = f"tg_{owner}_{kind}_{key}"
        st.toggle(label + (" · 🔒 desactivado por el administrador" if locked else ""), value=prefs.get((kind, key), True) and not locked,
                  key=wkey, disabled=locked, help=help_, on_change=_save_pref, args=(owner, kind, key, wkey))

    st.markdown("### 🎮 Juegos")
    cols = st.columns(2)
    for i, g in enumerate(NEW_GAMES):
        with cols[i % 2]:
            toggle("game", g["key"], f"{g['icon']} {g['title']}", g["desc"])
    st.markdown("### 🏔️ Niveles de dificultad")
    cols = st.columns(4)
    for col, lv in zip(cols, LEVELS):
        with col:
            toggle("level", lv, f"{LEVEL_ICON[lv]} {lv}", f"{per_level[lv]} preguntas activas")
    st.markdown("### 🌍 Categorías")
    cols = st.columns(4)
    for col, c in zip(cols, CATEGORIES):
        with col:
            toggle("category", c, f"{CAT_ICON[c]} {c}")
    st.markdown("### 🧩 Tipos de pregunta")
    cols = st.columns(4)
    for col, (t, label) in zip(cols, QTYPES.items()):
        with col:
            toggle("qtype", t, label)
    st.caption("Un estudiante ve lo que habilite al menos uno de sus docentes, siempre que el administrador no lo haya desactivado.")


# ── Editor del banco de preguntas ─────────────────────────────────────────────
def bank_page(ctx) -> None:
    admin = ctx.role == "admin"
    st.markdown(f"## 📚 {'Banco global de preguntas' if admin else 'Banco de preguntas'}")
    st.write("Añade, modifica, desactiva o elimina preguntas. Los cambios se guardan en la base de datos y se reflejan en la siguiente partida.")
    con = store.get_con()
    try:
        owners = None if admin else ["*", ctx.username]
        f1, f2, f3, f4 = st.columns(4)
        fcat = f1.multiselect("Categoría", CATEGORIES, key="bk_fcat")
        flvl = f2.multiselect("Nivel", LEVELS, key="bk_flvl")
        ftyp = f3.multiselect("Tipo", list(QTYPES), format_func=lambda t: QTYPES[t], key="bk_ftyp")
        ftxt = f4.text_input("Buscar texto", key="bk_ftxt")
        rows = store.list_questions(con, categories=fcat, levels=flvl, qtypes=ftyp, owners=owners, text=ftxt)
        m = st.columns(5)
        m[0].metric("Preguntas (filtro)", len(rows))
        for col, lv in zip(m[1:], LEVELS):
            col.metric(lv, sum(1 for r in rows if r["level"] == lv and r["active"]))
        with st.expander("📋 Ver listado", expanded=False):
            st.dataframe([{"ID": r["id"], "Categoría": r["category"], "Nivel": r["level"], "Tipo": QTYPES[r["qtype"]], "Pregunta": r["prompt"],
                           "Autor": "Global" if r["owner"] == "*" else r["owner"], "Activa": "Sí" if r["active"] else "No"} for r in rows],
                          hide_index=True)
        labels = {0: "➕ Nueva pregunta"}
        labels.update({r["id"]: f"#{r['id']} · {r['level']} · {QTYPES[r['qtype']]} · {r['prompt'][:70]}{'' if r['active'] else ' (inactiva)'}" for r in rows[:300]})
        sel = st.selectbox("Pregunta a editar", list(labels), format_func=lambda k: labels[k], key="bk_sel")
        current = store.get_question(con, sel) if sel else None
        _question_form(ctx, con, current)
        _import_export(ctx, con, rows)
    finally:
        con.close()


def _question_form(ctx, con, current: dict | None) -> None:
    qid = current["id"] if current else 0
    editable = current is None or store.can_edit(current, ctx.username, ctx.role)
    base = current or {"category": CATEGORIES[0], "level": LEVELS[0], "qtype": "mcq", "prompt": "", "explanation": "", "active": True,
                       "correct": "", "wrong": ["", "", ""], "a": {"emoji": "", "label": ""}, "b": {"emoji": "", "label": ""}, "pairs": []}
    st.markdown("### ✏️ Editar pregunta" if current else "### ➕ Nueva pregunta")
    if not editable:
        st.info("Esta es una pregunta global: puedes verla y crear una copia propia para modificarla.")
        if _btn("📄 Crear copia editable", key=f"bk_copy_{qid}"):
            data = {k: v for k, v in current.items() if k not in ("id", "owner", "updated_at")}
            new_id = store.add_question(con, data, ctx.username, ctx.username)
            st.session_state["bk_sel"] = new_id
            st.rerun()
    k = f"bk_{qid}_"
    a, b, c, d = st.columns(4)
    cat = a.selectbox("Categoría", CATEGORIES, index=CATEGORIES.index(base["category"]), key=k + "cat", disabled=not editable)
    lvl = b.selectbox("Nivel", LEVELS, index=LEVELS.index(base["level"]), key=k + "lvl", disabled=not editable)
    kind = c.selectbox("Tipo", list(QTYPES), index=list(QTYPES).index(base["qtype"]), format_func=lambda t: QTYPES[t], key=k + "kind", disabled=not editable)
    active = d.toggle("Activa", value=bool(base["active"]), key=k + "act", disabled=not editable)
    with st.form(f"bank_form_{qid}_{kind}"):
        prompt = st.text_area("Enunciado", value=base["prompt"], max_chars=300, disabled=not editable)
        q: dict = {"category": cat, "level": lvl, "qtype": kind, "prompt": prompt, "active": active}
        if kind == "mcq":
            q["correct"] = st.text_input("✅ Respuesta correcta", value=base.get("correct", "") if base["qtype"] == "mcq" else "", max_chars=120, disabled=not editable)
            wr = (base.get("wrong") or []) if base["qtype"] == "mcq" else []
            wr = (wr + ["", "", ""])[:3]
            q["wrong"] = [st.text_input(f"❌ Incorrecta {i + 1}", value=wr[i], max_chars=120, disabled=not editable) for i in range(3)]
        elif kind == "tf":
            cur = bool(base.get("correct", True)) if base["qtype"] == "tf" else True
            q["correct"] = st.radio("La afirmación es…", [True, False], index=0 if cur else 1, format_func=lambda v: "Verdadera" if v else "Falsa", horizontal=True, disabled=not editable)
        elif kind == "image":
            src = base if base["qtype"] == "image" else {"a": {"emoji": "", "label": ""}, "b": {"emoji": "", "label": ""}, "correct": "a"}
            x, y = st.columns(2)
            q["a"] = {"emoji": x.text_input("Emoji A", value=src["a"]["emoji"], max_chars=8, disabled=not editable), "label": x.text_input("Etiqueta A", value=src["a"]["label"], max_chars=60, disabled=not editable)}
            q["b"] = {"emoji": y.text_input("Emoji B", value=src["b"]["emoji"], max_chars=8, disabled=not editable), "label": y.text_input("Etiqueta B", value=src["b"]["label"], max_chars=60, disabled=not editable)}
            q["correct"] = st.radio("Imagen correcta", ["a", "b"], index=0 if src["correct"] == "a" else 1, format_func=str.upper, horizontal=True, disabled=not editable)
        else:
            lines = "\n".join(f"{p[0]} = {p[1]}" for p in base.get("pairs", [])) if base["qtype"] == "match" else ""
            text = st.text_area("Parejas (una por línea, «izquierda = derecha»; de 3 a 6)", value=lines, height=150, disabled=not editable)
            q["pairs"] = [tuple(part.strip() for part in line.split("=", 1)) for line in text.splitlines() if "=" in line]
        q["explanation"] = st.text_area("Explicación que verá el estudiante", value=base.get("explanation", ""), max_chars=400, disabled=not editable)
        save = st.form_submit_button("💾 Guardar cambios" if current else "➕ Añadir pregunta", type="primary", disabled=not editable)
    if save:
        errors = store.validate(q)
        if errors:
            for e in errors:
                st.error(e)
        else:
            actor, owner = ctx.username, ("*" if ctx.role == "admin" else ctx.username)
            if current:
                store.update_question(con, qid, q, actor)
                st.success("Pregunta actualizada.")
            else:
                new_id = store.add_question(con, q, owner, actor)
                st.session_state["bk_sel"] = new_id
                st.success("Pregunta añadida al banco.")
                st.rerun()
    if current and editable:
        x, y = st.columns(2)
        if x.button("🗑️ Eliminar definitivamente", key=k + "del"):
            st.session_state[k + "confirm"] = True
        if st.session_state.get(k + "confirm"):
            st.warning("Esta acción no se puede deshacer.")
            if y.button("Sí, eliminar", key=k + "del2", type="primary"):
                store.delete_question(con, qid)
                st.session_state["bk_sel"] = 0
                st.session_state.pop(k + "confirm", None)
                st.rerun()


def _import_export(ctx, con, rows: list[dict]) -> None:
    with st.expander("📦 Importar / exportar (JSON)"):
        st.download_button("⬇️ Exportar el filtro actual", store.export_json(rows), file_name="preguntas_ecoguardian.json", mime="application/json")
        up = st.file_uploader("Importar preguntas desde JSON", type=["json"], key="bk_upload")
        if up is not None and st.button("Importar ahora", key="bk_import", type="primary"):
            ok, problems = store.import_json(con, up.getvalue().decode("utf-8", "replace"), "*" if ctx.role == "admin" else ctx.username, ctx.username)
            st.success(f"{ok} pregunta(s) importadas.")
            for p in problems[:10]:
                st.warning(p)


# ── Acerca de ─────────────────────────────────────────────────────────────────
def about_page(ctx) -> None:
    _hero("ℹ️ Acerca de EcoGuardian", "Guardianes del planeta", about.TAGLINE)
    components.html(media.avatar_html(about.NARRATION), height=560, scrolling=False)
    for title, paragraphs in about.SECTIONS:
        st.markdown(f"### {title}")
        for para in paragraphs:
            st.markdown(para)


def progress_strip(ctx) -> None:
    con = store.get_con()
    try:
        p = store.user_progress(con, ctx.username)
    finally:
        con.close()
    a, b, c = st.columns(3)
    a.metric("Preguntas distintas vistas", p["seen"])
    b.metric("Aciertos", p["correct"])
    c.metric("Puntos en misiones", p["points"])
