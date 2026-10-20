# -*- coding: utf-8 -*-
"""Balloon Bash · modo aula dentro de la plataforma (docente = panel proyectado, estudiantes = control)."""
from __future__ import annotations

import streamlit as st

from . import bash_game, bridge, store, voice


def _fragment(run_every: str):
    if hasattr(st, "fragment"):
        return st.fragment(run_every=run_every)
    return lambda fn: fn


def _btn(label: str, **kw):
    try:
        return st.button(label, width="stretch", **kw)
    except TypeError:
        return st.button(label, use_container_width=True, **kw)


def _leave() -> None:
    for k in ("bb_code", "bb_join", "bb_view"):
        st.session_state.pop(k, None)


# ── Docente: sala + panel proyectado ──────────────────────────────────────────
def host_page(ctx) -> None:
    room = bash_game.create_room(ctx.username)
    st.session_state["bb_code"] = room.code
    st.markdown(f"#### 📺 Sala **{room.code}** · proyecta este panel")
    st.caption("Los alumnos entran desde **Biblioteca → Balloon Bash → Unirme con PIN** (en su celular o computador) e ingresan este PIN.")
    c1, c2, c3, c4 = st.columns(4)
    lobby = room.phase == "lobby"
    with c1:
        _btn("Todos vs todos", key="bb_m_ffa", disabled=not lobby, type="primary" if room.mode == "ffa" else "secondary", on_click=room.set_mode, args=("ffa",))
        _btn("Relevos 2 vs 2", key="bb_m_rel", disabled=not lobby, type="primary" if room.mode == "relay" else "secondary", on_click=room.set_mode, args=("relay",))
    with c2:
        _btn("🤖 Bots de prueba", key="bb_bots", disabled=not lobby, on_click=room.add_bots)
        voice.toggle_ui("bb_narrator")
    with c3:
        _btn("▶ Iniciar partida", key="bb_start", type="primary", disabled=room.phase not in ("lobby", "final") or not room.players,
             on_click=room.start)
        _btn("↺ Nueva partida", key="bb_reset", disabled=lobby, on_click=room.reset)
    with c4:
        _btn("✖ Cerrar sala", key="bb_close", on_click=lambda: (bash_game.close_room(room.code), _leave()))

    @_fragment("0.5s")
    def panel():
        r = bash_game.get_room(room.code)
        if not r:
            st.warning("La sala se cerró."); return
        snap = r.snapshot()
        bridge.balloon_host(snap, key=f"bb_host_{r.code}", voice=voice.enabled())
        if snap["phase"] == "final" and not r.saved:
            r.saved = True
            con = store.get_con()
            try:
                for user, pts in r.final_scores().items():
                    store.record_minigame(con, user, "inflate", pts, "Balloon Bash · aula")
            finally:
                con.close()
    panel()


# ── Estudiante: unirse con PIN y controlar ────────────────────────────────────
def play_page(ctx) -> None:
    code = st.session_state.get("bb_join")
    room = bash_game.get_room(code) if code else None
    if not room:
        if code:
            st.warning("Esa sala ya no existe."); _leave()
        pin = st.text_input("PIN de la sala", max_chars=4, key="bb_pin_in", placeholder="Ej.: 4829")
        if _btn("Entrar a la sala", key="bb_join_btn", type="primary"):
            r = bash_game.get_room(pin)
            if not r:
                st.error("No existe una sala con ese PIN.")
            else:
                ok, msg = r.join(ctx.username, ctx.display or ctx.username)
                if ok:
                    st.session_state["bb_join"] = r.code; st.rerun()
                else:
                    st.error(msg)
        return
    st.markdown(f"#### 📱 Sala **{room.code}** · mira SIEMPRE el panel del profesor")
    st.caption("En el celular: sacude hacia abajo (activa el sensor). En computador: barra espaciadora para inflar y Enter para frenar.")

    @_fragment("0.7s")
    def pad():
        r = bash_game.get_room(room.code)
        if not r:
            st.warning("La sala se cerró."); return
        val = bridge.balloon_pad(r.player_view(ctx.username), key=f"bb_pad_{r.code}")
        if isinstance(val, dict):
            seen = f"bb_seen_{r.code}"
            if int(val.get("id", 0)) > st.session_state.get(seen, 0):
                st.session_state[seen] = int(val["id"])
                if val.get("brake"):
                    r.brake(ctx.username)
                elif val.get("pumps"):
                    r.pump(ctx.username, val.get("pumps", 0), val.get("power", 0.6))
    pad()
    st.button("Salir de la sala", key="bb_leave", on_click=_leave)
