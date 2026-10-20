# -*- coding: utf-8 -*-
"""Componentes bidireccionales de Streamlit SIN paso de compilación (HTML estático en eco/web/).

Hablan el protocolo de componentes con postMessage; si la versión de Streamlit no soporta
`declare_component`, las funciones devuelven None y la página muestra un aviso.
"""
from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

WEB = Path(__file__).resolve().parent / "web"
_CACHE: dict[str, object] = {}


def _comp(folder: str):
    name = "eg_" + folder
    if name not in _CACHE:
        try:
            _CACHE[name] = components.declare_component(name, path=str(WEB / folder))
        except Exception:               # pragma: no cover - versiones sin soporte
            _CACHE[name] = None
    return _CACHE[name]


def balloon_host(snap: dict, key: str, voice: bool = True):
    c = _comp("balloon_host")
    return c(snap=snap, voice=voice, key=key, default=None) if c else None


def balloon_pad(view: dict, key: str):
    c = _comp("balloon_pad")
    return c(view=view, key=key, default=None) if c else None


def eco_runner(narrator: bool, sound: bool, key: str):
    c = _comp("eco_runner")
    return c(narrator=narrator, sound=sound, key=key, default=None) if c else None


def eco_ambient(ui: bool, enabled: bool, mode: str, key: str):
    """Música ambiental persistente. El componente no devuelve datos: controla un único <audio> del documento principal."""
    c = _comp("eco_ambient")
    return c(ui=ui, enabled=enabled, mode=mode, defaultVolume=0.10, autoStart=enabled, key=key, default=None) if c else None
