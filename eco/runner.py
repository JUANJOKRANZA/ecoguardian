# -*- coding: utf-8 -*-
"""EcoRunner: carrera de canecas (juego de acción en canvas dentro de un componente de Streamlit)."""
from __future__ import annotations

import streamlit as st

from . import bridge, store, voice


def runner_page(username: str) -> None:
    st.caption("Corre hacia la caneca correcta antes de que te alcance. 15 residuos, 3 vidas, rachas con bonificación y un locutor que te explica cada error.")
    voice.toggle_ui("runner_narr")
    val = bridge.eco_runner(narrator=voice.enabled(), sound=st.session_state.get("sound_on", True), key="eco_runner_game")
    if val is None and bridge._comp("eco_runner") is None:
        st.warning("Este navegador o versión de Streamlit no admite el juego de acción. Actualiza Streamlit (>=1.40).")
        return
    if isinstance(val, dict) and int(val.get("id", 0)) > st.session_state.get("runner_seen", 0):
        st.session_state["runner_seen"] = int(val["id"])
        con = store.get_con()
        try:
            store.record_minigame(con, username, "ecorunner", int(val.get("score", 0)), f"{int(val.get('hits', 0))}/{int(val.get('total', 0))}")
            best = store.minigame_best(con, username, "ecorunner")
        finally:
            con.close()
        st.session_state["runner_last"] = (int(val.get("score", 0)), best)
    last = st.session_state.get("runner_last")
    if last:
        st.success(f"Última carrera: {last[0]} puntos · Tu mejor marca: {last[1]}")
