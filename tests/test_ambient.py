# -*- coding: utf-8 -*-
"""Pruebas de la música ambiental: política de audio, montaje del componente y controlador JS (con Node si existe)."""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import test_smoke_ui as ui  # noqa: E402  (instala/usa el mismo Streamlit simulado)

if not ui.SKIP:
    from eco import ambient, bridge
    st = ui.st

WEB = HERE.parent / "eco" / "web" / "eco_ambient"


def _engine_calls():
    return [kw for name, kw in st.comp_calls if name == "eg_eco_ambient" and kw.get("key") == "eg_ambient_engine"]


def test_song_file_exists_and_is_mp3():
    mp3 = WEB / "reciclar_ambiente.mp3"
    data = mp3.read_bytes()
    assert len(data) > 1_000_000
    assert data[:3] == b"ID3" or data[0] == 0xFF          # cabecera MP3 real


def test_mode_for_policy():
    ss = {"sound_on": True, "page": "library", "lib_game": None}
    assert ambient.mode_for(ss) == "normal"                                    # navegación general
    ss["lib_game"] = "inflate"
    assert ambient.mode_for(ss) == "duck"                                      # política por defecto en juego
    ss[ambient.POLICY_KEY] = "pause"; assert ambient.mode_for(ss) == "pause"
    ss[ambient.POLICY_KEY] = "keep"; assert ambient.mode_for(ss) == "normal"
    ss[ambient.POLICY_KEY] = "pause"; ss["sound_on"] = False
    assert ambient.mode_for(ss) == "normal"
    assert ambient.mode_for({"page": "arena", "arena_code": "123456"}) == "duck"
    assert ambient.mode_for({"page": "home", "exam_code": "X"}) == "duck"
    assert ambient.mode_for({"page": "about"}) == "normal"


def test_engine_mounts_once_per_run_with_state():
    if ui.SKIP:
        return
    st.reset(); st.comp_calls.clear()
    st.session_state.update(sound_on=True, page="library", lib_game=None)
    ambient.engine()
    c = _engine_calls()
    assert len(c) == 1 and c[0]["enabled"] is True and c[0]["mode"] == "normal" and c[0]["ui"] is False
    st.comp_calls.clear(); st.session_state["lib_game"] = "inflate"; ambient.engine()
    assert _engine_calls()[0]["mode"] == "duck"
    st.comp_calls.clear(); st.session_state["sound_on"] = False; ambient.engine()
    assert _engine_calls()[0]["enabled"] is False
    st.comp_calls.clear(); st.session_state["sound_on"] = True; ambient.engine(force_off=True)
    assert _engine_calls()[0]["enabled"] is False                              # sin sesión: música detenida


def test_main_mounts_engine_logged_in_and_out():
    if ui.SKIP:
        return
    ui._setup()
    st.reset(); st.comp_calls.clear()
    try:
        ui.app.main()
    except ui.RerunException:
        pass
    assert _engine_calls() and _engine_calls()[-1]["enabled"] is False          # login: detenida
    ui.run("student", "est1", "library")
    assert _engine_calls() and _engine_calls()[-1]["enabled"] is True
    panels = [kw for n, kw in st.comp_calls if kw.get("key") == "eg_ambient_panel"]
    assert len(panels) == 1 and panels[0]["ui"] is True and panels[0]["defaultVolume"] == 0.10


def test_menu_off_shows_no_player():
    if ui.SKIP:
        return
    ui._setup()
    ui.run("student", "est1", "library", sound_on=False)
    assert not [kw for n, kw in st.comp_calls if kw.get("key") == "eg_ambient_panel"]


def test_page_change_keeps_single_engine_instance_key():
    if ui.SKIP:
        return
    ui._setup()
    keys = set()
    for page in ("library", "arena", "about"):
        ui.run("student", "est1", page)
        keys |= {kw.get("key") for n, kw in st.comp_calls if kw.get("key", "").startswith("eg_ambient")}
        assert len([1 for n, kw in st.comp_calls if kw.get("key") == "eg_ambient_engine"]) == 1
    assert keys == {"eg_ambient_engine", "eg_ambient_panel"}                    # claves estables entre páginas


def test_component_files_are_local_and_safe():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = (WEB / "controller.js").read_text(encoding="utf-8")
    for text in (html, js):
        assert "http://" not in text and "https://" not in text.replace("https://www.w3.org", "")
        assert "eval(" not in text and "document.write" not in text
    assert 'loop' in js and "audio.loop = true" in js
    assert "eg-ambient-audio" in js and "data-eg-ambient" in js


def test_controller_js_behaviour_with_node():
    node = shutil.which("node")
    if not node:
        return
    r = subprocess.run([node, str(HERE / "ambient_controller.test.js")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
