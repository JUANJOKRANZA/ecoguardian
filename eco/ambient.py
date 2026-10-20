# -*- coding: utf-8 -*-
"""Música ambiental de EcoGuardian AI: configuración, política de audio y puntos de montaje.

El audio NO vive en Python ni en un iframe de Streamlit: lo gestiona un único <audio loop> en el
documento principal del navegador (eco/web/eco_ambient/controller.js). Python solo le dice, en cada
rerun, si la música está habilitada y en qué modo está («normal», «duck» o «pause» según haya un
juego activo). Los efectos de los juegos son otro audio independiente y no se tocan.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from . import bridge

SONG_TITLE = "Reciclar – El medio ambiente vamos a cuidar"
SONG_FILE = Path(__file__).resolve().parent / "web" / "eco_ambient" / "reciclar_ambiente.mp3"
DEFAULT_VOLUME = 0.10            # volumen inicial: 10 %

POLICY_KEY = "ambient_game_policy"
POLICIES = {"duck": "Atenuar (recomendado)", "pause": "Pausar", "keep": "Mantener"}
DEFAULT_POLICY = "duck"
_POLICY_TO_MODE = {"duck": "duck", "pause": "pause", "keep": "normal"}


def game_active(ss) -> bool:
    """True si el usuario está dentro de un juego o actividad con voz/efectos (según el estado de la sesión)."""
    page = ss.get("page", "library")
    if page == "library" and ss.get("lib_game"):
        return True
    if page == "arena" and ss.get("arena_code"):
        return True
    if page == "home" and (ss.get("student_puff_mode") or ss.get("student_tf_mode") or ss.get("exam_code")):
        return True
    return False


def mode_for(ss) -> str:
    """Modo de la música ambiental: 'normal' (navegación), 'duck' (atenuada) o 'pause' (pausada por el juego)."""
    if not ss.get("sound_on", True) or not game_active(ss):
        return "normal"
    return _POLICY_TO_MODE.get(ss.get(POLICY_KEY, DEFAULT_POLICY), "duck")


def engine(force_off: bool = False) -> None:
    """Instancia sin interfaz (se monta en cada rerun, fuera del menú) que sincroniza el controlador del navegador."""
    enabled = (not force_off) and bool(st.session_state.get("sound_on", True))
    mode = mode_for(st.session_state) if enabled else "normal"
    with st.container(key="eg-ambient-engine"):
        bridge.eco_ambient(ui=False, enabled=enabled, mode=mode, key="eg_ambient_engine")


def panel() -> None:
    """Reproductor visible del apartado «Sonidos y ambiente» (se monta dentro del menú del perfil)."""
    if not SONG_FILE.is_file():
        st.error("No se encontró la canción ambiental (eco/web/eco_ambient/reciclar_ambiente.mp3).")
        return
    if bridge._comp("eco_ambient") is None:
        st.warning("Esta versión de Streamlit no admite el reproductor ambiental. Actualiza Streamlit (>=1.40).")
        return
    bridge.eco_ambient(ui=True, enabled=True, mode=mode_for(st.session_state), key="eg_ambient_panel")


def policy_selector(disabled: bool = False) -> None:
    """Qué hace la música ambiental al entrar en un juego (se mantiene el estado aunque el menú esté cerrado)."""
    st.session_state.setdefault(POLICY_KEY, DEFAULT_POLICY)
    st.radio("Durante los juegos", list(POLICIES), format_func=POLICIES.get, key=POLICY_KEY,
             horizontal=True, disabled=disabled,
             help="Los efectos y las voces de los juegos son independientes de esta música.")
