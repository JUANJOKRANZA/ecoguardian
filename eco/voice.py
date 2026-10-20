# -*- coding: utf-8 -*-
"""Narrador de EcoGuardian: voz del navegador (speechSynthesis) + frases con variedad.

`narrate()` habla una sola vez por `token` y respeta el interruptor «Narrador» de la sesión.
Las frases están aquí (Python puro) para poder probarlas sin navegador.
"""
from __future__ import annotations

import json
import random
import re
import unicodedata

import streamlit as st
import streamlit.components.v1 as components

CHEER_OK = ["¡Correcto!", "¡Eso es!", "¡Bien hecho!", "¡Exacto!", "¡Excelente!", "¡Muy bien, guardián!", "¡Así se hace!"]
CHEER_STREAK = {3: "¡Racha de tres! ¡Vas en llamas!", 5: "¡Cinco seguidas! ¡Imparable!", 8: "¡Ocho seguidas! ¡Eres una leyenda ecológica!"}
CHEER_BAD = ["¡Uy, casi!", "No era esa.", "¡Ay, por poquito!", "Esta vez no, pero aprendes."]


def _clean(text: str) -> str:
    t = re.sub(r"<[^>]+>|[*_`#]", "", str(text or ""))
    t = "".join(ch for ch in t if unicodedata.category(ch) not in ("So", "Cs", "Cn") and ch not in "\ufe0f\u200d")   # sin emojis
    return re.sub(r"\s+", " ", t).strip()


def speak_script(text: str, rate: float = 1.0, pitch: float = 1.0, cancel: bool = True) -> str:
    """JS autocontenido para un iframe: habla `text` en español."""
    t = json.dumps(_clean(text), ensure_ascii=False).replace("</", "<\\/")
    return ("<script>(function(){try{var s=window.speechSynthesis;if(!s)return;"
            + ("s.cancel();" if cancel else "") +
            f"var u=new SpeechSynthesisUtterance({t});u.lang='es-CO';u.rate={rate};u.pitch={pitch};u.volume=1;"
            "var go=function(){var v=s.getVoices().filter(function(x){return /^es/i.test(x.lang)});"
            "if(v.length){u.voice=v.find(function(x){return /CO|MX|419|US/i.test(x.lang)})||v[0];}s.speak(u);};"
            "if(s.getVoices().length){go()}else{s.onvoiceschanged=function(){s.onvoiceschanged=null;go()};setTimeout(function(){if(!s.speaking)go()},400)}"
            "}catch(e){}})();</script>")


def enabled() -> bool:
    return bool(st.session_state.get("narrator_on", True))


def narrate(text: str, once_key: str | None = None, rate: float = 1.0, pitch: float = 1.0) -> bool:
    """Habla `text` (una sola vez si se da `once_key`). Devuelve True si emitió voz."""
    if not enabled() or not _clean(text):
        return False
    if once_key:
        done = st.session_state.setdefault("_spoken", set())
        if once_key in done:
            return False
        done.add(once_key)
        if len(done) > 400:
            done.clear(); done.add(once_key)
    components.html(speak_script(text, rate, pitch), height=0)
    return True


def toggle_ui(key: str = "narrator_toggle") -> None:
    """Interruptor visible «🎙️ Narrador» (se recuerda en la sesión)."""
    st.session_state.setdefault("narrator_on", True)
    on = st.toggle("🎙️ Narrador", value=st.session_state["narrator_on"], key=key, help="El locutor lee las preguntas y los resultados.")
    st.session_state["narrator_on"] = bool(on)


def cheer(correct: bool, streak: int = 0, rng: random.Random | None = None) -> str:
    r = rng or random
    if correct and streak in CHEER_STREAK:
        return CHEER_STREAK[streak]
    return r.choice(CHEER_OK if correct else CHEER_BAD)


def final_line(hits: int, total: int, points: int | None = None) -> str:
    pct = round(100 * hits / max(1, total))
    if pct >= 90:
        tone = "¡Espectacular! ¡Eres un verdadero guardián del planeta!"
    elif pct >= 70:
        tone = "¡Muy bien! Estás a un paso de ser experto."
    elif pct >= 50:
        tone = "¡Buen intento! Con otra ronda lo dominas."
    else:
        tone = "¡Ánimo! Cada intento te enseña algo nuevo. ¡Vuelve a jugar!"
    extra = f" Ganaste {points} puntos." if points else ""
    return f"¡Fin del juego! Acertaste {hits} de {total}, un {pct} por ciento.{extra} {tone}"


def question_line(prompt: str, kind: str = "mcq", options=None, sides=None) -> str:
    """Lo que dice el locutor al mostrar una pregunta."""
    p = _clean(prompt)
    if kind == "image" and sides:
        return f"{p} Mira bien. A la izquierda, {_clean(sides[0])}. A la derecha, {_clean(sides[1])}. ¿Cuál es la respuesta correcta?"
    if kind == "tf":
        return f"{p} ¿Verdadero o falso?"
    if kind == "match":
        return f"{p} Une cada concepto con su pareja."
    if options:
        letters = "ABCDEF"
        opts = " ".join(f"Opción {letters[i]}: {_clean(o)}." for i, o in enumerate(list(options)[:6]))
        return f"{p} {opts} ¿Cuál es la respuesta correcta?"
    return f"{p} ¿Cuál es la respuesta correcta?"
