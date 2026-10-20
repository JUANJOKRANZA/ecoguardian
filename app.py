# -*- coding: utf-8 -*-
"""
EcoGuardian AI - Prototipo tecnológico de educación ambiental
=============================================================
Módulos:
  * EcoSilencio -> monitoreo de ruido escolar con semáforo ambiental.
  * EcoScan     -> guía educativa de residuos: blanco, verde, negro y rojo
                   (la caneca roja requiere seguir el protocolo local de manejo especial).
  * Estadísticas -> gráficos, indicadores y puntaje ecológico.

Ejecución:  streamlit run app.py
Arquitectura (resumen): presentación (Streamlit) -> lógica de negocio (funciones
puras: dB, semáforo, clasificador, puntaje) -> estado (st.session_state).
"""
from __future__ import annotations

import io
import base64
import unicodedata
import wave
import sqlite3
import secrets
import html
import os
import hashlib
import hmac
import json
import random
import re
import time
from pathlib import Path
from datetime import datetime, timedelta

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

from eco import about as eco_about  # noqa: F401
from eco import pages as eco_pages, store as eco_store, theme as eco_theme, voice as eco_voice, runner as eco_runner

# ──────────────────────────────────────────────────────────────────────────────
# 1. CONFIGURACIÓN GENERAL Y CONSTANTES
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="EcoGuardian AI", page_icon="🌱", layout="wide")
DB_PATH = Path(__file__).with_name("ecoguardian.sqlite3")

# Colores del semáforo de ruido
NOISE_COLORS = {"Verde": "#2E9E5B", "Amarillo": "#F2B705", "Rojo": "#D64545"}

# Mensajes y recomendaciones por nivel de ruido
NOISE_INFO = {
    "Verde": ("Ruido adecuado",
              "El ambiente favorece la concentración y el aprendizaje. ¡Sigan así!"),
    "Amarillo": ("Ruido moderado",
                 "Bajen el tono de voz y reduzcan el movimiento de sillas. "
                 "Un recordatorio breve del docente suele bastar."),
    "Rojo": ("Ruido excesivo",
             "Pausa activa en silencio durante 1 minuto. El ruido sostenido "
             "afecta la atención, la voz del docente y la salud auditiva."),
}

# Información educativa del código de colores (Resolución 2184 de 2019, Colombia)
BINS = {
    "Blanco": {
        "emoji": "⚪", "hex": "#E9EDF0", "chart": "#AEB9C4", "texto": "#1F2933",
        "titulo": "Residuos aprovechables",
        "desc": "Materiales limpios y secos que pueden volver a la cadena productiva "
                "mediante reciclaje o reutilización.",
        "ejemplos": "Botellas PET, latas, vidrio, papel, cartón, periódico, cuadernos.",
        "consejo": "Enjuágalos y sécalos antes de depositarlos: un residuo sucio "
                   "pierde su valor de reciclaje.",
    },
    "Verde": {
        "emoji": "🟢", "hex": "#287A3E", "chart": "#287A3E", "texto": "#FFFFFF",
        "titulo": "Residuos orgánicos aprovechables",
        "desc": "Restos biodegradables que se transforman en abono mediante "
                "compostaje o lombricultivo.",
        "ejemplos": "Cáscaras de fruta y verdura, restos de comida, café, hojas, poda.",
        "consejo": "No mezcles orgánicos con plástico: el compostaje se contamina "
                   "y todo termina en el relleno sanitario.",
    },
    "Negro": {
        "emoji": "⚫", "hex": "#2B2F33", "chart": "#2B2F33", "texto": "#FFFFFF",
        "titulo": "Residuos no aprovechables",
        "desc": "Materiales que hoy no tienen aprovechamiento viable y van a "
                "disposición final.",
        "ejemplos": "Papel higiénico, servilletas usadas, icopor, colillas, chicle, "
                    "empaques metalizados de snacks, cerámica.",
        "consejo": "La mejor opción es reducir su consumo: elige productos con "
                   "menos empaque.",
    },
    "Rojo": {
        "emoji": "🔴", "hex": "#B92F35", "chart": "#B92F35", "texto": "#FFFFFF",
        "titulo": "Residuos peligrosos o de manejo especial",
        "desc": "Residuos que requieren un protocolo de recolección específico; no deben mezclarse con la basura común.",
        "ejemplos": "Pilas, baterías, medicamentos vencidos y productos químicos, según el programa de recolección disponible.",
        "consejo": "Uso educativo: sigue las indicaciones del colegio y del gestor autorizado. No manipules agujas, químicos ni residuos biológicos; algunos requieren recipientes especializados.",
    },
}

# Palabras clave para reforzar la clasificación (se revisa en este orden:
# primero Negro porque contiene frases como "papel higienico" que incluyen "papel").
KEYWORDS = {
    "Rojo": ["pila", "bateria", "batería", "medicamento vencido", "medicamento caducado",
             "producto quimico", "quimico peligroso", "residuo biologico", "residuo peligroso"],
    "Negro": ["papel higienico", "servilleta", "icopor", "colilla", "chicle", "panal",
              "empaque de snack", "paquete de papas", "ceramica", "bolsa metalizada",
              "envoltura", "pañuelo"],
    "Verde": ["cascara", "fruta", "verdura", "comida", "sobra", "cafe", "hoja",
              "banano", "manzana", "naranja", "huevo", "poda", "pan", "arroz"],
    "Blanco": ["botella", "plastico", "papel", "carton", "vidrio", "lata", "metal",
               "periodico", "cuaderno", "tetra", "revista", "aluminio", "caja"],
}

# Estilos visuales (CSS). Fuente "Sora" para títulos.
CUSTOM_CSS = eco_theme.legacy_css()


# ──────────────────────────────────────────────────────────────────────────────
# 2. LÓGICA DE NEGOCIO (funciones puras, fáciles de probar)
# ──────────────────────────────────────────────────────────────────────────────
def normalize(text: str) -> str:
    """Minúsculas y sin tildes, para comparar palabras clave."""
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def estimate_db(wav_bytes: bytes, offset: float) -> float:
    """
    Estima el nivel de ruido (dB) desde una grabación WAV.
    1) Calcula el valor RMS de la señal (energía promedio).
    2) Lo convierte a dBFS (decibelios respecto al máximo digital).
    3) Suma un 'offset' de calibración para aproximar dB SPL.
    Nota: es una estimación relativa; los navegadores aplican cancelación de
    ruido y control de ganancia, por lo que conviene calibrar con un sonómetro.
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        channels, width, frames = w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(frames)
    if width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128.0
    else:
        raise ValueError("Formato de audio no soportado (use WAV de 8, 16 o 32 bits).")
    if channels > 1:
        data = data[: len(data) // channels * channels].reshape(-1, channels).mean(axis=1)
    rms = float(np.sqrt(np.mean(np.square(data)))) if data.size else 0.0
    dbfs = 20 * np.log10(max(rms, 1e-6))
    return float(np.clip(dbfs + offset, 30, 110))


def noise_level(db: float, green_max: float, yellow_max: float) -> str:
    """Convierte dB en color de semáforo según los umbrales configurables."""
    if db <= green_max:
        return "Verde"
    if db <= yellow_max:
        return "Amarillo"
    return "Rojo"


def classify_by_keyword(text: str) -> str | None:
    """Busca el nombre del objeto en el catálogo de palabras clave."""
    clean = normalize(text)
    for color, words in KEYWORDS.items():
        if any(w in clean for w in words):
            return color
    return None


def classify_image(img: Image.Image, hint: str = "") -> dict:
    """
    Clasificador de residuos (prototipo ligero, sin modelos pesados).
    Analiza la distribución de color en espacio HSV:
      * tonos cálidos/verdes saturados  -> indicio de materia orgánica,
      * tonos neutros claros o colores vivos artificiales -> envases/papel,
      * predominio de zonas oscuras -> residuos no aprovechables.
    Si el usuario escribe qué objeto es, la palabra clave pesa 85 % en el resultado.
    Devuelve {'probs': {color: prob}, 'pred': color, 'motivo': texto}.
    """
    # Limita la carga antes de redimensionar para reducir el riesgo de imágenes enormes.
    if not isinstance(img, Image.Image):
        raise ValueError("El archivo no es una imagen válida.")
    if img.width < 1 or img.height < 1 or img.width * img.height > 20_000_000:
        raise ValueError("La imagen debe tener dimensiones válidas y no superar 20 megapíxeles.")
    small = img.convert("RGB").resize((96, 96))
    hsv = np.asarray(small.convert("HSV"), dtype=np.float32) / 255.0
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]

    dark = float(np.mean(v < 0.25))
    organic = float(np.mean(((h > 0.05) & (h < 0.45)) & (s > 0.25) & (v > 0.2)))
    neutral = float(np.mean((s < 0.2) & (v > 0.6)))
    vivid = float(np.mean(((h >= 0.45) | (h <= 0.05)) & (s > 0.35) & (v > 0.3)))

    # La imagen por sí sola no permite detectar residuos peligrosos con fiabilidad.
    # La cuarta clase solo recibe una probabilidad alta si la descripción aporta una pista.
    raw = np.array([neutral + vivid + 0.05, organic * 1.2 + 0.05,
                    dark * 1.5 + 0.05, 0.02], dtype=float)
    probs = raw / raw.sum()
    motivo = "Análisis de color de la imagen."

    kw = classify_by_keyword(hint) if hint else None
    if kw:
        boost = np.array([1.0 if c == kw else 0.0 for c in BINS])
        probs = 0.85 * boost + 0.15 * probs
        motivo = f"Coincidencia con el objeto descrito («{hint.strip()}») + análisis de color."

    labels = list(BINS)
    return {"probs": dict(zip(labels, probs.tolist())),
            "pred": labels[int(np.argmax(probs))], "motivo": motivo}


def compute_indicators(noise_df: pd.DataFrame, waste_df: pd.DataFrame) -> dict:
    """
    Puntaje ecológico (0-100) = promedio de dos componentes disponibles:
      * Silencio: Verde = 100 pts, Amarillo = 55 pts, Rojo = 0 pts (promedio).
      * Residuos: % de veces que el estudiante eligió la caneca recomendada.
    """
    noise_score = waste_score = None
    pct_green = pct_red = 0.0
    if len(noise_df):
        counts = noise_df["nivel"].value_counts()
        g, y, r = (counts.get(k, 0) for k in ("Verde", "Amarillo", "Rojo"))
        n = len(noise_df)
        noise_score = (g * 100 + y * 55) / n
        pct_green, pct_red = g / n * 100, r / n * 100
    if len(waste_df):
        waste_score = float(waste_df["acierto"].mean() * 100)

    parts = [p for p in (noise_score, waste_score) if p is not None]
    total = float(np.mean(parts)) if parts else 0.0
    if total >= 80:
        rank = "Guardián Oro"
    elif total >= 60:
        rank = "Guardián Plata"
    elif total >= 40:
        rank = "Guardián Bronce"
    else:
        rank = "Semilla en crecimiento"
    return {"total": total, "rank": rank, "noise_score": noise_score,
            "waste_score": waste_score, "pct_green": pct_green, "pct_red": pct_red}


# ──────────────────────────────────────────────────────────────────────────────
# 2B. AULA COMPARTIDA Y JUEGO EDUCATIVO (SQLite)
# ──────────────────────────────────────────────────────────────────────────────
GAME_QUESTIONS = [
    {"objeto":"Botella plástica limpia y seca", "emoji":"🧴", "correcta":"Blanco", "nota":"Los envases aprovechables, limpios y secos van en la caneca blanca."},
    {"objeto":"Cáscara de banano", "emoji":"🍌", "correcta":"Verde", "nota":"Los residuos orgánicos aprovechables pueden ir a la caneca verde."},
    {"objeto":"Servilleta usada", "emoji":"🧻", "correcta":"Negro", "nota":"La servilleta usada es un residuo no aprovechable y va en la caneca negra."},
    {"objeto":"Caja de cartón limpia", "emoji":"📦", "correcta":"Blanco", "nota":"El cartón limpio y seco es aprovechable."},
    {"objeto":"Restos de ensalada", "emoji":"🥗", "correcta":"Verde", "nota":"Los restos de frutas y verduras son residuos orgánicos."},
    {"objeto":"Empaque metalizado de snacks", "emoji":"🍬", "correcta":"Negro", "nota":"Este empaque generalmente no es aprovechable en el sistema ordinario."},
    {"objeto":"Botella de vidrio limpia", "emoji":"🍾", "correcta":"Blanco", "nota":"El vidrio limpio es un material aprovechable. Manipúlalo con cuidado."},
    {"objeto":"Hojas y flores marchitas", "emoji":"🍂", "correcta":"Verde", "nota":"Los restos vegetales pueden aprovecharse mediante compostaje."},
    {"objeto":"Papel higiénico usado", "emoji":"🧻", "correcta":"Negro", "nota":"El papel higiénico usado no se deposita con el papel reciclable."},
    {"objeto":"Jeringa usada (simulación) ", "emoji":"⚠️", "correcta":"Roja", "nota":"¡Alerta de seguridad! Esto es solo una simulación. Nunca manipules una jeringa real; los residuos biosanitarios requieren manejo especializado según el protocolo institucional."},
    {"objeto":"Papel de cuaderno limpio", "emoji":"📄", "correcta":"Blanco", "nota":"El papel limpio y seco es aprovechable."},
    {"objeto":"Cáscaras de huevo", "emoji":"🥚", "correcta":"Verde", "nota":"Los restos orgánicos pueden destinarse al aprovechamiento orgánico."},
]

# Banco adicional para alcanzar 60 residuos distintos. La lista se mezcla por estudiante.
_EXTRA_WASTE = [
("Lata de gaseosa enjuagada","🥫","Blanco","El metal limpio y seco es aprovechable."),
("Periódico seco","📰","Blanco","El papel limpio y seco es aprovechable."),
("Revista vieja","📚","Blanco","El papel y cartón limpios pueden aprovecharse."),
("Botella de detergente vacía y limpia","🧴","Blanco","Los envases plásticos limpios pueden reciclarse según el sistema local."),
("Frasco de vidrio vacío","🫙","Blanco","El vidrio limpio es aprovechable; manipúlalo con cuidado."),
("Caja de cereal limpia","📦","Blanco","El cartón limpio y seco es aprovechable."),
("Hoja de papel impresa por un lado","📄","Blanco","El papel limpio puede aprovecharse."),
("Tubo de cartón de papel de cocina","🧻","Blanco","El cartón limpio y seco es aprovechable."),
("Bolsa de papel limpia","🛍️","Blanco","El papel limpio puede reciclarse."),
("Envase Tetra Pak limpio","🧃","Blanco","Los envases multicapa se separan según las opciones locales de reciclaje."),
("Lata de conserva vacía y limpia","🥫","Blanco","Los envases metálicos limpios son aprovechables."),
("Botella plástica de agua limpia","💧","Blanco","El envase plástico limpio y seco es aprovechable."),
("Cartulina limpia","🗂️","Blanco","El papel y cartón limpios son aprovechables."),
("Caja de huevos de cartón limpia","🥚","Blanco","El cartón limpio puede reciclarse."),
("Papel de regalo sin plástico","🎁","Blanco","El papel limpio puede aprovecharse."),
("Cáscara de naranja","🍊","Verde","Los restos de frutas son orgánicos."),
("Cáscara de mango","🥭","Verde","Los restos de frutas pueden compostarse."),
("Corazón de manzana","🍎","Verde","Los restos de frutas son orgánicos."),
("Cáscara de papa","🥔","Verde","Los restos vegetales son orgánicos."),
("Restos de zanahoria","🥕","Verde","Los restos de verduras son orgánicos."),
("Cáscara de piña","🍍","Verde","Los restos de frutas pueden compostarse."),
("Cáscara de aguacate","🥑","Verde","Los restos vegetales son orgánicos."),
("Borra de café","☕","Verde","Los restos de café son orgánicos."),
("Bolsa de té usada","🍵","Verde","El té usado puede ser orgánico si no contiene componentes no compostables."),
("Cáscara de sandía","🍉","Verde","Los restos de frutas son orgánicos."),
("Restos de arroz","🍚","Verde","Los restos de comida son orgánicos."),
("Pan duro","🍞","Verde","Los restos de comida pueden aprovecharse orgánicamente según el sistema local."),
("Hojas secas de jardín","🍃","Verde","Los restos vegetales pueden compostarse."),
("Flores marchitas","💐","Verde","Los restos de flores son orgánicos."),
("Cáscara de pepino","🥒","Verde","Los restos de verduras son orgánicos."),
("Servilleta limpia contaminada con comida","🧻","Negro","Si está sucia de comida no debe mezclarse con papel reciclable."),
("Pañal desechable usado (simulación)","🧷","Negro","Este residuo no es aprovechable en el reciclaje ordinario."),
("Pañuelo desechable usado","🤧","Negro","El pañuelo usado no se recicla como papel limpio."),
("Chicle masticado","🫧","Negro","El chicle es un residuo no aprovechable."),
("Colilla de cigarrillo","🚬","Negro","La colilla es un residuo no aprovechable; evita fumar."),
("Plato desechable sucio","🍽️","Negro","Si está contaminado y no se aprovecha localmente, va a no aprovechables."),
("Vaso de icopor usado","🥤","Negro","El icopor suele ser no aprovechable en la ruta ordinaria local."),
("Empaque de galletas metalizado","🍪","Negro","Los empaques metalizados flexibles suelen ser no aprovechables."),
("Cinta adhesiva usada","🩹","Negro","La cinta adhesiva no se separa como papel limpio."),
("Esponja de limpieza gastada","🧽","Negro","La esponja usada suele ser un residuo no aprovechable."),
("Cerámica rota (simulación)","🏺","Negro","La cerámica no va con el vidrio reciclable."),
("Bolsa de snacks vacía","🍿","Negro","Los empaques flexibles metalizados suelen ir a no aprovechables."),
("Mascarilla desechable usada (simulación)","😷","Negro","No se recicla como material aprovechable; manipulación higiénica."),
("Papel higiénico usado (simulación)","🧻","Negro","El papel higiénico usado no es reciclable."),
("Algodón usado (simulación)","☁️","Negro","El algodón usado no se recicla en la ruta ordinaria."),
("Guante desechable no contaminado","🧤","Negro","Los guantes desechables suelen ser no aprovechables en el sistema ordinario."),
("Pila usada (simulación)","🔋","Roja","¡Alerta! Las pilas requieren un punto posconsumo especial; no van a canecas ordinarias."),
("Aerosol químico vacío (simulación)","⚠️","Roja","Los envases peligrosos requieren manejo especializado y puntos autorizados."),
("Frasco de medicamento vencido (simulación)","💊","Roja","Los medicamentos vencidos deben ir a puntos de recolección autorizados."),
("Jeringa (simulación, no manipular)","🚨","Roja","Solo simulación: nunca manipules agujas reales; sigue el protocolo institucional."),
("Envase con residuo químico (simulación)","☣️","Roja","Residuo peligroso simulado: requiere gestión especializada, no caneca ordinaria."),
("Lámpara fluorescente rota (simulación)","💡","Roja","Puede contener sustancias peligrosas; requiere recolección especial."),
("Batería hinchada (simulación)","🔋","Roja","Solo simulación: no manipular; requiere gestión especializada."),
]
for _obj, _emoji, _correcta, _nota in _EXTRA_WASTE:
    GAME_QUESTIONS.append({"objeto": _obj, "emoji": _emoji, "correcta": _correcta, "nota": _nota})
# Catálogo final de 60 residuos distintos; conserva ejemplos especiales de seguridad al final.
GAME_QUESTIONS = GAME_QUESTIONS[:55] + GAME_QUESTIONS[-5:]

# Retos de contaminación auditiva. Los escenarios se barajan por estudiante.
NOISE_QUESTIONS = [
 {"objeto":"En el salón varias personas gritan al mismo tiempo.","emoji":"🗣️","correcta":"Reducir el volumen","nota":"Hablar por turnos y con voz moderada ayuda a la concentración."},
 {"objeto":"Una alarma de emergencia suena en el colegio.","emoji":"🚨","correcta":"Seguir el protocolo","nota":"No se debe ignorar una alarma; sigue las indicaciones de seguridad."},
 {"objeto":"Un compañero escucha música con audífonos al máximo volumen.","emoji":"🎧","correcta":"Bajar el volumen","nota":"Un volumen alto puede afectar la audición."},
 {"objeto":"Arrastran las sillas durante toda la clase.","emoji":"🪑","correcta":"Mover con cuidado","nota":"Levantar o mover suavemente las sillas reduce el ruido."},
 {"objeto":"El grupo quiere conversar mientras el profesor explica.","emoji":"🏫","correcta":"Escuchar por turnos","nota":"Evitar conversaciones paralelas mejora la comprensión."},
 {"objeto":"En el patio hay una actividad deportiva con silbato.","emoji":"🏃","correcta":"Usarlo solo cuando haga falta","nota":"Los sonidos fuertes deben limitarse a lo necesario."},
 {"objeto":"Una máquina produce un ruido muy fuerte durante mucho tiempo.","emoji":"⚙️","correcta":"Alejarse y avisar","nota":"Un ruido intenso o prolongado debe reportarse y evaluarse."},
 {"objeto":"El semáforo de ruido está en amarillo.","emoji":"🟡","correcta":"Bajar un poco la voz","nota":"El amarillo indica ruido moderado: es momento de corregirlo."},
 {"objeto":"El semáforo de ruido está en rojo.","emoji":"🔴","correcta":"Reducir el ruido de inmediato","nota":"El rojo indica ruido excesivo según los umbrales configurados."},
 {"objeto":"El semáforo permanece en verde.","emoji":"🟢","correcta":"Mantener el ambiente","nota":"El verde indica que el nivel está dentro del rango configurado."},
 {"objeto":"Una persona siente zumbido después de un sonido fuerte.","emoji":"👂","correcta":"Alejarse del ruido y avisar","nota":"No ignores molestias auditivas; informa a un adulto responsable."},
 {"objeto":"Se va a realizar una actividad grupal en el aula.","emoji":"👥","correcta":"Acordar turnos de palabra","nota":"Los turnos permiten participar sin elevar demasiado la voz."},
 {"objeto":"Un estudiante golpea la mesa para llamar la atención.","emoji":"✋","correcta":"Usar una señal tranquila","nota":"Las señales acordadas evitan golpes y gritos innecesarios."},
 {"objeto":"Se usa un parlante en un espacio cerrado.","emoji":"🔊","correcta":"Mantener volumen moderado","nota":"Ajusta el volumen al espacio y a la actividad."},
 {"objeto":"Hay ruido de obras cerca del aula.","emoji":"🚧","correcta":"Informar y reducir exposición","nota":"Se debe avisar al responsable y protegerse según las normas del lugar."},
]
# Ampliación a 60 retos con situaciones y formulaciones diferentes.
_NOISE_CONTEXTS = [
 ("En una biblioteca escolar", "📚"), ("Durante una evaluación", "📝"), ("En el comedor", "🍽️"),
 ("En un pasillo", "🚶"), ("Durante una exposición", "🎤"), ("En una sala de informática", "💻"),
 ("En una reunión de equipo", "🤝"), ("En el laboratorio", "🧪"), ("En educación física", "⚽"),
 ("Al iniciar la jornada", "🌅"), ("Durante una lectura", "📖"), ("En una actividad artística", "🎨"),
 ("Al salir al descanso", "🔔"), ("En una videollamada", "💻"), ("En un espacio compartido", "🧑‍🤝‍🧑"),
 ("En el aula de música", "🎼"), ("En una fila para ingresar", "🚪"), ("En una feria escolar", "🎪"),
 ("Durante una práctica de ciencias", "🔬"), ("En una cancha cubierta", "🏀"), ("En una lectura grupal", "📚"),
 ("En la oficina escolar", "🏢"), ("En una ceremonia", "🎓"), ("Con parlantes en el aula", "🔈"),
 ("En el transporte escolar", "🚌"), ("En una actividad al aire libre", "🌳"), ("En una clase virtual", "🖥️"),
 ("En el taller de tecnología", "🛠️"), ("En una jornada de limpieza", "🧹"), ("Durante una práctica de baile", "💃"),
 ("En la sala de profesores", "☕"), ("En el auditorio", "🎭"), ("Durante un simulacro", "🦺"),
 ("En un torneo escolar", "🏆"), ("En una actividad de manualidades", "✂️"), ("En una exposición de proyectos", "🧑‍🔬"),
 ("En una reunión de padres", "👨‍👩‍👧"), ("Durante el cambio de clase", "🔔"), ("En una clase de idiomas", "🗣️"),
 ("En el patio central", "🌤️"), ("Durante una explicación importante", "👩‍🏫"), ("En el laboratorio de informática", "⌨️"),
 ("En un club de ciencias", "🧪"), ("En una actividad de debate", "💬"), ("Antes de una prueba", "📋"),
 ("Durante una actividad de orientación", "🧭"),
]
for i, (context, emoji) in enumerate(_NOISE_CONTEXTS):
    base = NOISE_QUESTIONS[i % 15]
    NOISE_QUESTIONS.append({"objeto":f"{context}, observa esta situación: {base['objeto'][0].lower()+base['objeto'][1:]}","emoji":emoji,"correcta":base["correcta"],"nota":base["nota"]})
while len(NOISE_QUESTIONS) < 60:
    base = NOISE_QUESTIONS[len(NOISE_QUESTIONS) % 30]
    NOISE_QUESTIONS.append({**base, "objeto":f"Reto {len(NOISE_QUESTIONS)+1}: {base['objeto']}"})
NOISE_QUESTIONS = NOISE_QUESTIONS[:60]

ALL_BIN_COLORS = ["Roja", "Verde", "Blanca", "Negra"]

# ──────────────────────────────────────────────────────────────────────────────
# 2C. BASE DE DATOS, SEGURIDAD Y MOTOR DEL EXAMEN (sin código de interfaz)
# ──────────────────────────────────────────────────────────────────────────────
POINTS_PER_HIT = 10
MAX_FAILS, LOCK_SECONDS = 5, 300
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,30}$")
BIN_LABEL = {"Roja": "Roja", "Verde": "Verde", "Blanco": "Blanca", "Negro": "Negra"}
BIN_ICON = {"Roja": "☣️", "Verde": "🍃", "Blanco": "♻️", "Negro": "🗑️"}
BIN_WORD = {"Roja": "roja", "Verde": "verde", "Blanco": "blanca", "Negro": "negra"}
ACTIVITY_LABEL = {"residuos": "Clasificación de residuos", "auditiva": "Contaminación auditiva",
                  "ambos": "Taller combinado"}
NOISE_DISTRACTORS = ["Ignorar la situación", "Aumentar el ruido", "No hacer nada", "Gritar para imponerse",
                     "Subir el volumen al máximo", "Seguir como si nada", "Golpear la mesa para llamar la atención",
                     "Esperar a que se arregle solo", "Hablar más fuerte que los demás", "Reírse y seguir igual"]
_READY_DBS: set = set()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _migrate(con) -> None:
    """Crea o actualiza las tablas sin perder datos de versiones anteriores."""
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    con.execute("CREATE TABLE IF NOT EXISTS classes (code TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, mode TEXT NOT NULL, teacher TEXT NOT NULL, question_count INTEGER NOT NULL DEFAULT 10)")
    cols = [r[1] for r in con.execute("PRAGMA table_info(classes)").fetchall()]
    if "question_count" not in cols:
        con.execute("ALTER TABLE classes ADD COLUMN question_count INTEGER NOT NULL DEFAULT 10")
    if "activity" not in cols:
        con.execute("ALTER TABLE classes ADD COLUMN activity TEXT NOT NULL DEFAULT 'residuos'")
    if "review" not in cols:
        con.execute("ALTER TABLE classes ADD COLUMN review INTEGER NOT NULL DEFAULT 0")
    if "closed" not in cols:
        con.execute("ALTER TABLE classes ADD COLUMN closed INTEGER NOT NULL DEFAULT 0")
    con.execute("CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, student TEXT NOT NULL, question TEXT NOT NULL, chosen TEXT NOT NULL, correct TEXT NOT NULL, is_correct INTEGER NOT NULL, points INTEGER NOT NULL, created_at TEXT NOT NULL)")
    acols = [r[1] for r in con.execute("PRAGMA table_info(attempts)").fetchall()]
    for name, ddl in (("username", "TEXT"), ("qpos", "INTEGER"), ("attempt_no", "INTEGER")):
        if name not in acols:
            con.execute(f"ALTER TABLE attempts ADD COLUMN {name} {ddl}")
    # Un mismo intento de una misma pregunta no puede guardarse dos veces (doble clic, dos pestañas...).
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_attempt ON attempts(code, username, qpos, attempt_no)")
    con.execute("CREATE TABLE IF NOT EXISTS accounts (username TEXT PRIMARY KEY, display_name TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'student', approved INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)")
    pcols = [r[1] for r in con.execute("PRAGMA table_info(participants)").fetchall()]
    if not pcols:
        con.execute("CREATE TABLE participants (code TEXT NOT NULL, name TEXT NOT NULL, username TEXT, PRIMARY KEY(code, username), FOREIGN KEY(code) REFERENCES classes(code))")
    elif "username" not in pcols:
        con.execute("ALTER TABLE participants RENAME TO participants_legacy")
        con.execute("CREATE TABLE participants (code TEXT NOT NULL, name TEXT NOT NULL, username TEXT, PRIMARY KEY(code, username), FOREIGN KEY(code) REFERENCES classes(code))")
        con.execute("INSERT INTO participants(code,name,username) SELECT code,name,NULL FROM participants_legacy")
        con.execute("DROP TABLE participants_legacy")
    # Una fila por (sala, estudiante): garantiza UNA sola oportunidad y permite retomar si se recarga la página.
    con.execute("CREATE TABLE IF NOT EXISTS game_sessions (code TEXT NOT NULL, username TEXT NOT NULL, order_json TEXT NOT NULL, pos INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'en_curso', started_at TEXT NOT NULL, finished_at TEXT, PRIMARY KEY(code, username))")
    con.execute("CREATE TABLE IF NOT EXISTS login_guard (key TEXT PRIMARY KEY, fails INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0)")
    con.execute("CREATE TABLE IF NOT EXISTS auth_sessions (token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, role TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS user_profiles (username TEXT PRIMARY KEY, photo BLOB, email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', bio TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT '')")
    profile_cols = [r[1] for r in con.execute("PRAGMA table_info(user_profiles)").fetchall()]
    for name, ddl in (("email", "TEXT NOT NULL DEFAULT ''"), ("phone", "TEXT NOT NULL DEFAULT ''"), ("bio", "TEXT NOT NULL DEFAULT ''")):
        if name not in profile_cols:
            con.execute(f"ALTER TABLE user_profiles ADD COLUMN {name} {ddl}")
    con.execute("CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, username TEXT, created_at TEXT NOT NULL, seen INTEGER NOT NULL DEFAULT 0)")
    con.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT NOT NULL, recipient TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL, read_at TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS puff_rooms (code TEXT PRIMARY KEY, title TEXT NOT NULL, host TEXT NOT NULL, topic TEXT NOT NULL, difficulty TEXT NOT NULL, format TEXT NOT NULL, rounds INTEGER NOT NULL, seconds INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'lobby', round_no INTEGER NOT NULL DEFAULT 0, question_json TEXT NOT NULL, round_started REAL, created_at TEXT NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS puff_players (code TEXT NOT NULL, username TEXT NOT NULL, display_name TEXT NOT NULL, points INTEGER NOT NULL DEFAULT 0, correct INTEGER NOT NULL DEFAULT 0, joined_at TEXT NOT NULL, PRIMARY KEY(code,username))")
    con.execute("CREATE TABLE IF NOT EXISTS puff_answers (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, round_no INTEGER NOT NULL, username TEXT NOT NULL, answer TEXT NOT NULL, is_correct INTEGER NOT NULL, received_at REAL NOT NULL, points INTEGER NOT NULL DEFAULT 0, UNIQUE(code,round_no,username))")
    con.execute("CREATE TABLE IF NOT EXISTS class_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, sender TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL)")
    # Permisos jerárquicos de EcoAventura: el administrador autoriza docentes y estos asignan juegos a sus estudiantes.
    con.execute("CREATE TABLE IF NOT EXISTS eco_teacher_grants (teacher TEXT NOT NULL, game TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, starts_at TEXT NOT NULL, ends_at TEXT, max_minutes INTEGER NOT NULL DEFAULT 20, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(teacher,game))")
    con.execute("CREATE TABLE IF NOT EXISTS eco_student_grants (teacher TEXT NOT NULL, student TEXT NOT NULL, game TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, starts_at TEXT NOT NULL, ends_at TEXT, max_minutes INTEGER NOT NULL DEFAULT 20, updated_at TEXT NOT NULL, PRIMARY KEY(teacher,student,game))")
    eco_store.migrate(con)
    con.execute("CREATE TABLE IF NOT EXISTS eco_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, game TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL)")
    con.commit()


def db_connect():
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    key = str(DB_PATH)
    if key not in _READY_DBS:
        _migrate(con)
        _READY_DBS.add(key)
    return con


eco_store.configure(lambda: db_connect())


# ── Sesión persistente y mensajería ───────────────────────────────────────────
def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def persist_login(username: str, role: str) -> None:
    token = secrets.token_urlsafe(32)
    con = db_connect()
    con.execute("INSERT INTO auth_sessions(token_hash,username,role,expires_at,created_at) VALUES(?,?,?,?,?)",
                (_token_digest(token), username, role, (datetime.now()+timedelta(days=14)).isoformat(timespec="seconds"), now_iso()))
    con.commit(); con.close()
    st.query_params["eg_session"] = token
    st.session_state["auth_user"] = username
    st.session_state["auth_role"] = role

def restore_login() -> None:
    if st.session_state.get("auth_user"):
        return
    token = st.query_params.get("eg_session", "")
    if not token:
        return
    con = db_connect()
    row = con.execute("SELECT username,role,expires_at FROM auth_sessions WHERE token_hash=?", (_token_digest(token),)).fetchone()
    if row and row["expires_at"] > now_iso():
        if st.query_params.get("eg_room"):
            st.session_state["exam_code"] = st.query_params.get("eg_room", "").upper()
        account = con.execute("SELECT approved,role FROM accounts WHERE username=?", (row["username"],)).fetchone()
        # The role stored in a persistent session must still match the account's
        # current role. Revoked/unapproved accounts and stale role grants are revoked.
        valid_account = bool(
            account
            and account["role"] == row["role"]
            and (account["role"] == "admin" or (account["role"] in ("student", "teacher") and account["approved"]))
        )
        if valid_account:
            st.session_state["auth_user"] = row["username"]
            st.session_state["auth_role"] = account["role"]
        else:
            con.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_token_digest(token),))
            con.commit()
            st.query_params.pop("eg_session", None)
            st.query_params.pop("eg_room", None)
    else:
        con.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_token_digest(token),)); con.commit()
        st.query_params.pop("eg_session", None)
        st.query_params.pop("eg_room", None)
    con.close()

def logout() -> None:
    token = st.query_params.get("eg_session", "")
    if token:
        con = db_connect(); con.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_token_digest(token),)); con.commit(); con.close()
    st.query_params.clear()
    for key in list(st.session_state.keys()):
        st.session_state.pop(key, None)
    st.rerun()

def send_message(sender: str, recipient: str, body: str) -> None:
    con = db_connect()
    con.execute("INSERT INTO messages(sender,recipient,body,created_at) VALUES(?,?,?,?)", (sender, recipient, body.strip()[:1000], now_iso()))
    con.commit(); con.close()

# ── Contraseñas y bloqueo contra fuerza bruta ────────────────────────────────
def _password_hash(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 240_000).hex()
    return salt, digest


def _verify_password(password: str, salt: str, expected: str) -> bool:
    _, actual = _password_hash(password, salt)
    return hmac.compare_digest(actual, expected)


def _has_admin() -> bool:
    con = db_connect()
    row = con.execute("SELECT 1 FROM accounts WHERE role='admin' LIMIT 1").fetchone()
    con.close()
    return row is not None


def guard_remaining(key: str) -> int:
    """Segundos que faltan para poder volver a intentar (0 = permitido)."""
    con = db_connect()
    row = con.execute("SELECT locked_until FROM login_guard WHERE key=?", (key,)).fetchone()
    con.close()
    return max(0, int(row["locked_until"] - time.time())) if row else 0


def guard_fail(key: str) -> int:
    """Registra un fallo; al llegar a MAX_FAILS bloquea LOCK_SECONDS. Devuelve fallos acumulados."""
    con = db_connect()
    con.execute("BEGIN IMMEDIATE")
    row = con.execute("SELECT fails, locked_until FROM login_guard WHERE key=?", (key,)).fetchone()
    fails = (row["fails"] if row else 0) + 1
    locked = time.time() + LOCK_SECONDS if fails >= MAX_FAILS else 0
    if locked:
        fails = 0
    con.execute("INSERT INTO login_guard(key,fails,locked_until) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET fails=excluded.fails, locked_until=excluded.locked_until", (key, fails, locked))
    con.commit(); con.close()
    return fails


def guard_clear(key: str) -> None:
    con = db_connect(); con.execute("DELETE FROM login_guard WHERE key=?", (key,)); con.commit(); con.close()


# ── Preguntas y orden ────────────────────────────────────────────────────────
def _bank(qtype: str) -> list:
    return NOISE_QUESTIONS if qtype == "auditiva" else GAME_QUESTIONS


def resolve_entry(entry) -> tuple[str, dict]:
    qtype, idx = entry[0], int(entry[1])
    return qtype, _bank(qtype)[idx]


def build_order(activity: str, count: int, rng=None) -> list:
    """Sorteo impredecible (SystemRandom) de [tipo, índice]. Sin repetidos."""
    rng = rng or random.SystemRandom()
    if activity == "ambos":
        pool = [["residuos", i] for i in range(len(GAME_QUESTIONS))] + [["auditiva", i] for i in range(len(NOISE_QUESTIONS))]
    elif activity == "auditiva":
        pool = [["auditiva", i] for i in range(len(NOISE_QUESTIONS))]
    else:
        pool = [["residuos", i] for i in range(len(GAME_QUESTIONS))]
    count = max(1, min(60, len(pool), int(count)))
    return rng.sample(pool, count)


def option_list(qtype: str, q: dict, seed: str) -> list:
    """Opciones del reto. Las de ruido se mezclan de forma estable (misma mezcla al recargar)."""
    if qtype == "residuos":
        return ["Roja", "Verde", "Blanco", "Negro"]
    rnd = random.Random(seed)
    wrong = [x for x in NOISE_DISTRACTORS if x != q["correcta"]]
    opts = [q["correcta"]] + rnd.sample(wrong, 3)
    rnd.shuffle(opts)
    return opts


def is_locked(mode: str, attempts: list) -> bool:
    """¿El reto ya quedó resuelto y solo se puede pulsar «Siguiente»?"""
    if mode == "restringido":
        return any(a["is_correct"] for a in attempts)
    return len(attempts) > 0


# ── Motor del examen (todas las escrituras son atómicas) ─────────────────────
def exam_enter(con, code: str, username: str, display: str) -> dict:
    room = con.execute("SELECT * FROM classes WHERE code=?", (code,)).fetchone()
    if not room:
        return {"result": "no_room"}
    member = con.execute("SELECT 1 FROM participants WHERE code=? AND (username=? OR (username IS NULL AND name=?))", (code, username, display)).fetchone()
    if not member:
        return {"result": "not_member"}
    con.execute("BEGIN IMMEDIATE")
    s = con.execute("SELECT * FROM game_sessions WHERE code=? AND username=?", (code, username)).fetchone()
    if s and s["status"] == "finalizada":
        con.rollback(); return {"result": "finished"}
    if room["closed"]:
        con.rollback(); return {"result": "closed"}
    if s:
        con.rollback(); return {"result": "resumed", "pos": s["pos"], "total": len(json.loads(s["order_json"]))}
    order = build_order(room["activity"] or "residuos", int(room["question_count"] or 10))
    con.execute("INSERT INTO game_sessions(code,username,order_json,pos,status,started_at) VALUES(?,?,?,?,?,?)", (code, username, json.dumps(order), 0, "en_curso", now_iso()))
    con.commit()
    return {"result": "new", "pos": 0, "total": len(order)}


def exam_state(con, code: str, username: str) -> dict | None:
    s = con.execute("SELECT * FROM game_sessions WHERE code=? AND username=?", (code, username)).fetchone()
    room = con.execute("SELECT * FROM classes WHERE code=?", (code,)).fetchone()
    if not s or not room:
        return None
    order = json.loads(s["order_json"])
    pos = int(s["pos"])
    attempts = [dict(r) for r in con.execute("SELECT chosen,is_correct,attempt_no FROM attempts WHERE code=? AND username=? AND qpos=? ORDER BY attempt_no", (code, username, pos)).fetchall()] if s["status"] == "en_curso" else []
    return {"order": order, "pos": pos, "total": len(order), "status": s["status"], "mode": room["mode"],
            "review": bool(room["review"]), "closed": bool(room["closed"]), "title": room["title"],
            "started_at": s["started_at"], "finished_at": s["finished_at"],
            "attempts": attempts, "locked": is_locked(room["mode"], attempts)}


def exam_answer(con, code: str, username: str, pos: int, chosen: str) -> str:
    """Guarda UNA respuesta. Devuelve: recorded_ok | recorded_bad | stale | already | invalid | closed."""
    con.execute("BEGIN IMMEDIATE")
    s = con.execute("SELECT * FROM game_sessions WHERE code=? AND username=?", (code, username)).fetchone()
    room = con.execute("SELECT * FROM classes WHERE code=?", (code,)).fetchone()
    if not s or not room or s["status"] != "en_curso" or int(s["pos"]) != int(pos):
        con.rollback(); return "stale"
    if room["closed"]:
        con.rollback(); return "closed"
    order = json.loads(s["order_json"])
    # Defend against corrupt/stale session state before indexing the stored order.
    if int(pos) < 0 or int(pos) >= len(order):
        con.rollback()
        return "stale"
    qtype, q = resolve_entry(order[pos])
    if chosen not in option_list(qtype, q, f"{code}|{username}|{pos}"):
        con.rollback(); return "invalid"
    prev = con.execute("SELECT chosen,is_correct FROM attempts WHERE code=? AND username=? AND qpos=? ORDER BY attempt_no", (code, username, pos)).fetchall()
    if is_locked(room["mode"], prev) or chosen in [p["chosen"] for p in prev]:
        con.rollback(); return "already"
    ok = chosen == q["correcta"]
    pts = POINTS_PER_HIT if (ok and not prev) else 0
    name = con.execute("SELECT display_name FROM accounts WHERE username=?", (username,)).fetchone()
    try:
        con.execute("INSERT INTO attempts(code,student,username,qpos,attempt_no,question,chosen,correct,is_correct,points,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (code, name["display_name"] if name else username, username, pos, len(prev) + 1, q["objeto"], chosen, q["correcta"], int(ok), pts, now_iso()))
        con.commit()
    except sqlite3.IntegrityError:
        con.rollback(); return "already"
    return "recorded_ok" if ok else "recorded_bad"


def exam_next(con, code: str, username: str, pos: int) -> str:
    """Pasa al siguiente reto (o finaliza). Solo si el reto actual ya fue resuelto."""
    con.execute("BEGIN IMMEDIATE")
    s = con.execute("SELECT * FROM game_sessions WHERE code=? AND username=?", (code, username)).fetchone()
    room = con.execute("SELECT mode FROM classes WHERE code=?", (code,)).fetchone()
    if not s or not room or s["status"] != "en_curso" or int(s["pos"]) != int(pos):
        con.rollback(); return "stale"
    prev = con.execute("SELECT is_correct FROM attempts WHERE code=? AND username=? AND qpos=?", (code, username, pos)).fetchall()
    if not is_locked(room["mode"], prev):
        con.rollback(); return "not_answered"
    total = len(json.loads(s["order_json"]))
    if pos + 1 >= total:
        con.execute("UPDATE game_sessions SET pos=?, status='finalizada', finished_at=? WHERE code=? AND username=?", (total, now_iso(), code, username))
        con.commit(); return "finished"
    con.execute("UPDATE game_sessions SET pos=? WHERE code=? AND username=?", (pos + 1, code, username))
    con.commit(); return "advanced"


def exam_summary(con, code: str, username: str) -> dict:
    s = con.execute("SELECT * FROM game_sessions WHERE code=? AND username=?", (code, username)).fetchone()
    total = len(json.loads(s["order_json"])) if s else 0
    row = con.execute("SELECT COUNT(*) AS answered, COALESCE(SUM(is_correct),0) AS hits, COALESCE(SUM(points),0) AS pts FROM attempts WHERE code=? AND username=? AND attempt_no=1", (code, username)).fetchone()
    answered, hits, pts = int(row["answered"]), int(row["hits"]), int(row["pts"])
    seconds = None
    if s and s["finished_at"]:
        seconds = int((datetime.fromisoformat(s["finished_at"]) - datetime.fromisoformat(s["started_at"])).total_seconds())
    return {"total": total, "answered": answered, "hits": hits, "misses": answered - hits, "points": pts,
            "pct": round(100 * hits / total) if total else 0, "seconds": seconds}


def exam_review(con, code: str, username: str) -> list:
    return [dict(r) for r in con.execute("SELECT qpos,question,chosen,correct,is_correct FROM attempts WHERE code=? AND username=? AND attempt_no=1 ORDER BY qpos", (code, username)).fetchall()]


def exam_reset(con, code: str, username: str) -> None:
    """Solo el administrador: borra el intento de un estudiante para que pueda repetir."""
    con.execute("BEGIN IMMEDIATE")
    con.execute("DELETE FROM attempts WHERE code=? AND username=?", (code, username))
    con.execute("DELETE FROM game_sessions WHERE code=? AND username=?", (code, username))
    con.commit()


def room_results(con, code: str) -> pd.DataFrame:
    rows = []
    for p in con.execute("SELECT name, username FROM participants WHERE code=? ORDER BY name", (code,)).fetchall():
        u = p["username"]
        s = con.execute("SELECT * FROM game_sessions WHERE code=? AND username=?", (code, u)).fetchone() if u else None
        if not s:
            rows.append({"Estudiante": p["name"], "Usuario": u or "—", "Estado": "Sin iniciar", "Avance": "—", "Aciertos": 0, "Errores": 0, "Precisión %": 0.0, "Puntos": 0, "Tiempo": "—"})
            continue
        sm = exam_summary(con, code, u)
        done = s["status"] == "finalizada"
        secs = sm["seconds"]
        rows.append({"Estudiante": p["name"], "Usuario": u, "Estado": "Finalizada" if done else "En curso",
                     "Avance": f"{sm['answered']}/{sm['total']}", "Aciertos": sm["hits"], "Errores": sm["misses"],
                     "Precisión %": float(sm["pct"]) if done else round(100 * sm["hits"] / max(1, sm["answered"]), 1),
                     "Puntos": sm["points"], "Tiempo": f"{secs // 60:02d}:{secs % 60:02d}" if secs is not None else "—"})
    cols = ["Estudiante", "Usuario", "Estado", "Avance", "Aciertos", "Errores", "Precisión %", "Puntos", "Tiempo"]
    df = pd.DataFrame(rows, columns=cols)
    return df.sort_values(["Puntos", "Aciertos"], ascending=False, kind="stable").reset_index(drop=True) if len(df) else df


def rank_for(pct: int) -> tuple[str, str]:
    if pct >= 90: return "Guardián Legendario", "🏆"
    if pct >= 75: return "Guardián Experto", "🥇"
    if pct >= 60: return "Guardián Aprendiz", "🥈"
    if pct >= 40: return "Explorador Verde", "🥉"
    return "Semilla en crecimiento", "🌱"


def fmt_seconds(secs) -> str:
    return "—" if secs is None else f"{secs // 60:02d}:{secs % 60:02d}"


# ──────────────────────────────────────────────────────────────────────────────
# 2D. INTERFAZ: AUTENTICACIÓN, PANEL DEL DOCENTE Y JUEGO
# ──────────────────────────────────────────────────────────────────────────────
GAME_CSS = """
<style>
@keyframes gm-pop { 0%{transform:scale(.88);opacity:0} 100%{transform:scale(1);opacity:1} }
@keyframes gm-float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-8px)} }
@keyframes gm-shake { 0%,100%{transform:translateX(0)} 25%{transform:translateX(-7px)} 75%{transform:translateX(7px)} }
@keyframes gm-glow { 0%,100%{box-shadow:0 0 0 0 rgba(46,125,79,.45)} 50%{box-shadow:0 0 0 12px rgba(46,125,79,0)} }
.gm-top { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;
          background:#14352A; color:#F2F7F1; border-radius:16px; padding:12px 18px; margin-bottom:10px; }
.gm-top, .gm-top * { color:#F2F7F1; }
.gm-top .gm-chip { color:#fff; }
.gm-top b { font-family:'Sora',sans-serif; }
.gm-chip { background:#2E7D4F; color:#fff; border-radius:999px; padding:3px 12px; font-size:.85rem; font-weight:700; }
.gm-track { position:relative; height:16px; background:#D9E6DA; border-radius:999px; margin:14px 4px 22px 4px; }
.gm-fill { height:100%; border-radius:999px; background:linear-gradient(90deg,#3E9B4F,#9BD66B); transition:width .5s; }
.gm-hero { position:absolute; top:-12px; font-size:1.7rem; transform:translateX(-50%); transition:left .5s; }
.gm-goal { position:absolute; right:-6px; top:-12px; font-size:1.7rem; }
.gm-card { border-radius:22px; padding:26px 22px; text-align:center; color:#fff; animation:gm-pop .35s ease-out;
           box-shadow:0 8px 22px rgba(20,53,42,.25); margin-bottom:14px; }
.gm-card.waste { background:linear-gradient(135deg,#0F4A31,#25774D); }
.gm-card.noise { background:linear-gradient(135deg,#1B3F7E,#2D62B5); }
.gm-card .em { font-size:72px; line-height:1.1; animation:gm-float 2.6s ease-in-out infinite; }
.gm-card .gm-chip { background:rgba(0,0,0,.35); color:#fff; }
.gm-card, .gm-card * { color:#fff; }
.gm-card h3 { color:#fff !important; margin:.4rem 0 .2rem 0; font-size:1.45rem; }
.gm-card .q { font-weight:600; color:#fff !important; }
.gm-lock, .gm-lock * { color:#14301F !important; }
.gm-lock.bad, .gm-lock.bad * { color:#6B1519 !important; }
.gm-lock { border-radius:18px; padding:18px; text-align:center; background:#EAF5EC; color:#18382A;
           border:2px dashed #2E7D4F; animation:gm-pop .3s ease-out; margin-bottom:10px; font-size:1.15rem; font-weight:700; }
.gm-lock.ok { background:#E3F7E8; border-color:#2E9E5B; }
.gm-lock.bad { background:#FDECEC; border-color:#D64545; animation:gm-shake .4s; }
.gm-final { text-align:center; border-radius:24px; padding:30px 18px; color:#fff; animation:gm-pop .5s ease-out;
            background:linear-gradient(135deg,#14352A,#2E7D4F); box-shadow:0 10px 26px rgba(20,53,42,.3); margin-bottom:14px; }
.gm-final .medal { font-size:84px; animation:gm-float 2.4s ease-in-out infinite; }
.gm-final, .gm-final * { color:#fff; }
.gm-final h2 { color:#fff !important; margin:.2rem 0; }
.gm-stars { font-size:2rem; letter-spacing:4px; }
.gm-tiles { display:flex; gap:10px; flex-wrap:wrap; justify-content:center; margin-top:14px; }
.gm-tile { background:rgba(255,255,255,.14); border-radius:14px; padding:10px 18px; min-width:110px; }
.gm-tile .n { font-family:'Sora',sans-serif; font-size:1.7rem; font-weight:700; }
.gm-tile .l { font-size:.8rem; opacity:.85; }
/* Botones de las canecas: colores FIJOS con prioridad sobre las reglas globales de botones */
html body .stApp [class*="st-key-bin_"][class*="_exam_"] button, html body .stApp [class*="st-key-bin_"][class*="_prac_"] button, html body .stApp [class*="st-key-opt_"] button, html body .stApp [class*="st-key-next_"] button { min-height:92px !important; border-radius:18px !important; font-weight:800 !important; font-size:1.1rem !important; border-width:3px !important; border-style:solid !important; transition:transform .12s, box-shadow .12s !important; box-shadow:0 5px 0 rgba(0,0,0,.22) !important; line-height:1.3 !important; }
html body .stApp [class*="st-key-bin_Roja_"] button { background:#B92F35 !important; border-color:#8D2025 !important; color:#FFFFFF !important; }
html body .stApp [class*="st-key-bin_Roja_"] button *, html body .stApp [class*="st-key-bin_Roja_"] button p { color:#FFFFFF !important; }
html body .stApp [class*="st-key-bin_Roja_"] button:hover:not(:disabled), html body .stApp [class*="st-key-bin_Roja_"] button:focus-visible { background:#A12830 !important; border-color:#8D2025 !important; color:#FFFFFF !important; transform:translateY(-3px); }
html body .stApp [class*="st-key-bin_Roja_"] button:hover:not(:disabled) *, html body .stApp [class*="st-key-bin_Roja_"] button:focus-visible * { color:#FFFFFF !important; }
html body .stApp [class*="st-key-bin_Roja_"] button:disabled { background:#B92F35 !important; color:#FFFFFF !important; opacity:.6 !important; box-shadow:none !important; }
html body .stApp [class*="st-key-bin_Verde_"] button { background:#287A3E !important; border-color:#1B5D2D !important; color:#FFFFFF !important; }
html body .stApp [class*="st-key-bin_Verde_"] button *, html body .stApp [class*="st-key-bin_Verde_"] button p { color:#FFFFFF !important; }
html body .stApp [class*="st-key-bin_Verde_"] button:hover:not(:disabled), html body .stApp [class*="st-key-bin_Verde_"] button:focus-visible { background:#1F6A33 !important; border-color:#1B5D2D !important; color:#FFFFFF !important; transform:translateY(-3px); }
html body .stApp [class*="st-key-bin_Verde_"] button:hover:not(:disabled) *, html body .stApp [class*="st-key-bin_Verde_"] button:focus-visible * { color:#FFFFFF !important; }
html body .stApp [class*="st-key-bin_Verde_"] button:disabled { background:#287A3E !important; color:#FFFFFF !important; opacity:.6 !important; box-shadow:none !important; }
html body .stApp [class*="st-key-bin_Blanco_"] button { background:#F1F4F6 !important; border-color:#6B7A86 !important; color:#17252D !important; }
html body .stApp [class*="st-key-bin_Blanco_"] button *, html body .stApp [class*="st-key-bin_Blanco_"] button p { color:#17252D !important; }
html body .stApp [class*="st-key-bin_Blanco_"] button:hover:not(:disabled), html body .stApp [class*="st-key-bin_Blanco_"] button:focus-visible { background:#FFFFFF !important; border-color:#6B7A86 !important; color:#17252D !important; transform:translateY(-3px); }
html body .stApp [class*="st-key-bin_Blanco_"] button:hover:not(:disabled) *, html body .stApp [class*="st-key-bin_Blanco_"] button:focus-visible * { color:#17252D !important; }
html body .stApp [class*="st-key-bin_Blanco_"] button:disabled { background:#F1F4F6 !important; color:#17252D !important; opacity:.6 !important; box-shadow:none !important; }
html body .stApp [class*="st-key-bin_Negro_"] button { background:#292D32 !important; border-color:#0E1114 !important; color:#FFFFFF !important; }
html body .stApp [class*="st-key-bin_Negro_"] button *, html body .stApp [class*="st-key-bin_Negro_"] button p { color:#FFFFFF !important; }
html body .stApp [class*="st-key-bin_Negro_"] button:hover:not(:disabled), html body .stApp [class*="st-key-bin_Negro_"] button:focus-visible { background:#3A4047 !important; border-color:#0E1114 !important; color:#FFFFFF !important; transform:translateY(-3px); }
html body .stApp [class*="st-key-bin_Negro_"] button:hover:not(:disabled) *, html body .stApp [class*="st-key-bin_Negro_"] button:focus-visible * { color:#FFFFFF !important; }
html body .stApp [class*="st-key-bin_Negro_"] button:disabled { background:#292D32 !important; color:#FFFFFF !important; opacity:.6 !important; box-shadow:none !important; }
html body .stApp [class*="st-key-opt_"] button { background:#EEF4FF !important; border-color:#2F6BC0 !important; color:#14284F !important; min-height:76px !important; }
html body .stApp [class*="st-key-opt_"] button *, html body .stApp [class*="st-key-opt_"] button p { color:#14284F !important; }
html body .stApp [class*="st-key-opt_"] button:hover:not(:disabled), html body .stApp [class*="st-key-opt_"] button:focus-visible { background:#D8E7FF !important; border-color:#1F4A8F !important; color:#14284F !important; transform:translateY(-3px); }
html body .stApp [class*="st-key-opt_"] button:hover:not(:disabled) * { color:#14284F !important; }
html body .stApp [class*="st-key-opt_"] button:disabled { background:#EEF4FF !important; color:#14284F !important; opacity:.6 !important; box-shadow:none !important; }
html body .stApp [class*="st-key-next_"] button { background:#176B45 !important; border-color:#0F4F32 !important; color:#FFFFFF !important; min-height:64px !important; font-size:1.2rem !important; }
html body .stApp [class*="st-key-next_"] button *, html body .stApp [class*="st-key-next_"] button p { color:#FFFFFF !important; }
html body .stApp [class*="st-key-next_"] button:hover, html body .stApp [class*="st-key-next_"] button:focus-visible { background:#0F4F32 !important; color:#FFFFFF !important; transform:translateY(-2px); }
html body .stApp [class*="st-key-next_"] button:hover * { color:#FFFFFF !important; }
@media (max-width:640px) { .gm-card .em { font-size:56px; } .gm-card h3 { font-size:1.2rem; } }
</style>
"""

_STRETCH = None


def sbtn(label: str, **kw):
    """Botón a ancho completo compatible con versiones nuevas y antiguas de Streamlit."""
    global _STRETCH
    if _STRETCH is None:
        try:
            r = st.button(label, width="stretch", **kw)
            _STRETCH = {"width": "stretch"}
            return r
        except Exception:
            _STRETCH = {"use_container_width": True}
    return st.button(label, **_STRETCH, **kw)


def show_df(df: pd.DataFrame) -> None:
    try:
        st.dataframe(df, hide_index=True, width="stretch")
    except Exception:
        st.dataframe(df, hide_index=True, use_container_width=True)


def stop_browser_speech():
    """Cancela la narración que pueda seguir sonando al cambiar de reto."""
    st.components.v1.html("""<script>try { if (window.speechSynthesis) { window.speechSynthesis.cancel(); } } catch(e) {}</script>""", height=0)


def speak_browser(message: str):
    """Voz en español; cancela cualquier frase anterior antes de hablar."""
    payload = json.dumps(str(message))
    st.components.v1.html(f"""<script>
    try {{
      if ('speechSynthesis' in window) {{
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance({payload});
        u.lang = 'es-CO'; u.rate = 0.95; u.pitch = 1.0; u.volume = 1.0;
        const voices = window.speechSynthesis.getVoices();
        const spanish = voices.find(v => /^es(-|_)/i.test(v.lang));
        if (spanish) u.voice = spanish;
        window.speechSynthesis.speak(u);
      }}
    }} catch(e) {{}}
    </script>""", height=0)


# ── Acceso ───────────────────────────────────────────────────────────────────
def _lock_message(secs: int) -> str:
    return f"Demasiados intentos fallidos. Espera {max(1, (secs + 59) // 60)} minuto(s) antes de volver a intentar."


def auth_portal():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    col_izq, col_der = st.columns([1.05, 1], gap="large")
    with col_izq:
        st.markdown("<div class='eg-login-brand'>EcoGuardian</div><div class='eg-login-copy'>Únete a la nueva generación de guardianes del planeta.</div><div class='eg-login-sub'>Cultiva tu conocimiento, protege nuestro futuro.</div><div class='eg-login-note'>Plataforma educativa · Acceso autorizado</div>", unsafe_allow_html=True)
    with col_der:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        if not _has_admin():
            st.warning("Primera configuración: crea la cuenta administradora. Esta pantalla requiere una clave inicial de configuración disponible solo para quien inicia el servidor.")
            expected_setup_key = os.environ.get("ECOGUARDIAN_SETUP_KEY", "")
            if not expected_setup_key:
                st.error("Falta la variable de entorno ECOGUARDIAN_SETUP_KEY. Cierra la aplicación y vuelve a abrir iniciar_windows.bat para definir una clave inicial, o configura esa variable en el servicio de alojamiento antes de publicar.")
                return
            with st.form("first_admin_form"):
                setup_key = st.text_input("Clave inicial de configuración", type="password")
                username = st.text_input("Usuario administrador", value="admin")
                display = st.text_input("Nombre del administrador")
                p1 = st.text_input("Crear contraseña (mínimo 12 caracteres)", type="password")
                p2 = st.text_input("Confirmar contraseña", type="password")
                submitted = st.form_submit_button("Crear administrador", type="primary")
            if submitted:
                if guard_remaining("setup"):
                    st.error(_lock_message(guard_remaining("setup")))
                elif not hmac.compare_digest(setup_key.encode(), expected_setup_key.encode()):
                    guard_fail("setup"); st.error("La clave inicial de configuración no coincide.")
                elif len(p1) < 12 or p1 != p2 or not USERNAME_RE.match(username.strip().lower()) or not display.strip():
                    st.error("Completa los campos (usuario de 3 a 30 letras, números, punto, guion) y usa una contraseña de al menos 12 caracteres; ambas deben coincidir.")
                else:
                    salt, digest = _password_hash(p1)
                    con = db_connect(); con.execute("INSERT INTO accounts(username,display_name,salt,password_hash,role,approved,created_at) VALUES(?,?,?,?,?,?,?)", (username.strip().lower(), display.strip()[:60], salt, digest, "admin", 1, now_iso())); con.commit(); con.close()
                    guard_clear("setup")
                    st.success("Administrador creado. Inicia sesión con tus credenciales."); st.rerun()
            return
        tab_admin, tab_student, tab_teacher, tab_register = st.tabs(["🔐 Administrador", "🎓 Ingresar estudiante", "👩‍🏫 Docente", "📝 Crear cuenta"])

        def _login(role: str, username: str, password: str):
            uname = username.strip().lower()
            key = f"{role}:{uname}"
            wait = guard_remaining(key)
            if wait:
                st.error(_lock_message(wait)); return
            con = db_connect(); row = con.execute("SELECT * FROM accounts WHERE username=? AND role=?", (uname, role)).fetchone(); con.close()
            if not row or not _verify_password(password, row["salt"], row["password_hash"]):
                guard_fail(key); st.error("Usuario o contraseña incorrectos."); return
            if not row["approved"]:
                st.warning("Tu cuenta está pendiente de autorización del administrador."); return
            guard_clear(key)
            persist_login(row["username"], role); st.rerun()

        with tab_admin:
            with st.form("admin_login"):
                username = st.text_input("Usuario administrador", key="admin_user")
                password = st.text_input("Contraseña", type="password", key="admin_pass")
                go = st.form_submit_button("Entrar al panel", type="primary")
            if go:
                _login("admin", username, password)
        with tab_student:
            with st.form("student_login"):
                username = st.text_input("Usuario", key="student_login_user")
                password = st.text_input("Contraseña", type="password", key="student_login_pass")
                go = st.form_submit_button("Ingresar", type="primary")
            if go:
                _login("student", username, password)
        with tab_teacher:
            st.caption("Los docentes deben solicitar una cuenta y esperar la aprobación del administrador.")
            with st.form("teacher_login"):
                username = st.text_input("Usuario docente", key="teacher_login_user")
                password = st.text_input("Contraseña docente", type="password", key="teacher_login_pass")
                go = st.form_submit_button("Ingresar como docente", type="primary")
            if go:
                _login("teacher", username, password)
            with st.form("teacher_register"):
                display_t = st.text_input("Nombre completo", key="teacher_reg_name")
                username_t = st.text_input("Crea tu usuario docente", key="teacher_reg_user")
                password_t = st.text_input("Contraseña (mínimo 10 caracteres)", type="password", key="teacher_reg_pass")
                confirm_t = st.text_input("Confirmar contraseña", type="password", key="teacher_reg_confirm")
                submit_t = st.form_submit_button("Solicitar cuenta docente")
            if submit_t:
                uname_t = username_t.strip().lower()
                if not display_t.strip() or len(display_t.strip()) > 60 or not USERNAME_RE.match(uname_t) or len(password_t) < 10 or password_t != confirm_t:
                    st.error("Completa los datos correctamente y confirma una contraseña de al menos 10 caracteres.")
                else:
                    salt_t, digest_t = _password_hash(password_t)
                    try:
                        cx = db_connect(); cx.execute("INSERT INTO accounts(username,display_name,salt,password_hash,role,approved,created_at) VALUES(?,?,?,?,?,?,?)", (uname_t, display_t.strip(), salt_t, digest_t, "teacher", 0, now_iso()))
                        cx.execute("INSERT INTO notifications(kind,title,body,username,created_at) VALUES(?,?,?,?,?)", ("registro_docente", "Nueva solicitud de docente", f"{display_t.strip()} solicitó cuenta docente (@{uname_t}).", uname_t, now_iso()))
                        cx.commit(); cx.close(); st.success("Solicitud enviada. El administrador debe aprobar la cuenta antes de ingresar.")
                    except sqlite3.IntegrityError:
                        st.error("Ese usuario ya existe. Elige otro.")

        with tab_register:
            with st.form("student_register"):
                display = st.text_input("Nombre y apellido")
                username = st.text_input("Crea tu usuario (3 a 30: letras minúsculas, números, punto o guion)")
                password = st.text_input("Crea una contraseña (mínimo 10 caracteres)", type="password")
                confirm = st.text_input("Confirma la contraseña", type="password")
                go = st.form_submit_button("Solicitar acceso")
            if go:
                uname = username.strip().lower()
                if not display.strip() or len(display.strip()) > 60 or not USERNAME_RE.match(uname) or len(password) < 10 or password != confirm:
                    st.error("Completa todos los campos: usuario de 3 a 30 caracteres (letras, números, punto o guion), contraseña de al menos 10 caracteres y confírmala.")
                else:
                    salt, digest = _password_hash(password)
                    try:
                        con = db_connect(); con.execute("INSERT INTO accounts(username,display_name,salt,password_hash,role,approved,created_at) VALUES(?,?,?,?,?,?,?)", (uname, display.strip(), salt, digest, "student", 0, now_iso()))
                        con.execute("INSERT INTO notifications(kind,title,body,username,created_at) VALUES(?,?,?,?,?)", ("registro", "Nuevo registro de estudiante", f"{display.strip()} solicitó acceso con el usuario @{uname}.", uname, now_iso()))
                        con.commit(); con.close()
                        st.success("¡Solicitud enviada! El administrador recibirá una notificación y debe autorizar tu cuenta.")
                    except sqlite3.IntegrityError:
                        st.error("Ese usuario ya existe. Elige otro.")


def admin_accounts_panel():
    st.subheader("👥 Autorización de estudiantes y docentes")
    con = db_connect()
    pending = con.execute("SELECT username,display_name,created_at,role FROM accounts WHERE role IN ('student','teacher') AND approved=0 ORDER BY created_at").fetchall()
    approved = con.execute("SELECT username,display_name,created_at,role FROM accounts WHERE role IN ('student','teacher') AND approved=1 ORDER BY role,display_name").fetchall()
    con.close()
    if pending:
        for row in pending:
            a, b, c = st.columns([3, 1, 1]); a.write(f"**{html.escape(row['display_name'])}** · {('Docente' if row['role']=='teacher' else 'Estudiante')} · `@{row['username']}`")
            if b.button("Autorizar", key="approve_" + row['username']):
                con = db_connect(); con.execute("UPDATE accounts SET approved=1 WHERE username=? AND role IN ('student','teacher')", (row['username'],)); con.commit(); con.close(); st.rerun()
            if c.button("Rechazar", key="reject_" + row['username']):
                con = db_connect(); con.execute("DELETE FROM accounts WHERE username=? AND role IN ('student','teacher') AND approved=0", (row['username'],)); con.commit(); con.close(); st.rerun()
    else:
        st.info("No hay solicitudes pendientes.")
    st.markdown("#### Cuentas autorizadas")
    if approved:
        show_df(pd.DataFrame([dict(r) for r in approved]))
    else:
        st.caption("Todavía no hay estudiantes autorizados.")




ECO_GAMES = {
    "EcoSonidos": "🔊 Reconoce sonidos y aprende a escuchar la naturaleza",
    "EcoPuff Arcade": "♻️ Clasifica residuos con rapidez",
    "EcoRunner": "🏃 Supera misiones ecológicas",
    "EcoRetos": "🧠 Preguntas, memoria y verdadero o falso",
    "EcoReto en Vivo": "⚡ Compite con preguntas ambientales, tiempo y puntuación",
    "EcoVerdadero o Falso": "🌿 Decide si las afirmaciones ambientales son correctas",
}

def _grant_active(row) -> bool:
    if not row or not int(row["enabled"]):
        return False
    now = now_iso()
    return row["starts_at"] <= now and (not row["ends_at"] or row["ends_at"] >= now)

def eco_teacher_allowed(teacher: str, game: str) -> bool:
    con = db_connect()
    row = con.execute("SELECT enabled,starts_at,ends_at FROM eco_teacher_grants WHERE teacher=? AND game=?", (teacher, game)).fetchone()
    con.close()
    return _grant_active(row)

def eco_student_allowed(student: str, game: str) -> bool:
    con = db_connect()
    rows = con.execute("SELECT s.enabled,s.starts_at,s.ends_at,t.enabled AS parent_enabled,t.starts_at AS parent_start,t.ends_at AS parent_end FROM eco_student_grants s JOIN eco_teacher_grants t ON t.teacher=s.teacher AND t.game=s.game WHERE s.student=? AND s.game=?", (student, game)).fetchall()
    con.close()
    now = now_iso()
    return any(bool(r["enabled"]) and bool(r["parent_enabled"]) and r["starts_at"] <= now and (not r["ends_at"] or r["ends_at"] >= now) and r["parent_start"] <= now and (not r["parent_end"] or r["parent_end"] >= now) for r in rows)

def _eco_log(actor, action, target, game, details):
    con = db_connect()
    con.execute("INSERT INTO eco_audit(actor,action,target,game,details,created_at) VALUES(?,?,?,?,?,?)", (actor,action,target,game,details,now_iso()))
    con.commit(); con.close()

def eco_admin_panel():
    st.markdown("## 🛡️ Permisos de EcoAventura")
    st.write("El administrador autoriza los juegos disponibles para cada docente. Si retira este permiso, también se bloquea el acceso de sus estudiantes.")
    con = db_connect()
    teachers = con.execute("SELECT username,display_name FROM accounts WHERE role='teacher' AND approved=1 ORDER BY display_name").fetchall()
    with st.form("eco_admin_grant_form"):
        teacher = st.selectbox("Docente autorizado", options=[r['username'] for r in teachers], format_func=lambda u: next((f"{r['display_name']} (@{u})" for r in teachers if r['username']==u),u)) if teachers else None
        game = st.selectbox("Juego", list(ECO_GAMES))
        enabled = st.checkbox("Habilitar para este docente", value=True)
        c1,c2 = st.columns(2)
        start_date = c1.date_input("Fecha de inicio", value=datetime.now().date())
        duration = c2.selectbox("Vigencia", [1,3,7,15,30,90,365,0], format_func=lambda n: "Hasta retirarlo" if n==0 else f"{n} día(s)")
        max_minutes = st.selectbox("Límite orientativo por sesión (minutos)", [10,15,20,30,45,60,0], format_func=lambda n: "Sin límite" if n==0 else str(n))
        save = st.form_submit_button("Guardar autorización", type="primary", disabled=not bool(teachers))
        if save and teacher:
            start = datetime.combine(start_date, datetime.min.time()).isoformat(timespec="seconds")
            end = (datetime.combine(start_date + timedelta(days=duration), datetime.max.time()).isoformat(timespec="seconds") if duration else None)
            con.execute("INSERT INTO eco_teacher_grants(teacher,game,enabled,starts_at,ends_at,max_minutes,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(teacher,game) DO UPDATE SET enabled=excluded.enabled,starts_at=excluded.starts_at,ends_at=excluded.ends_at,max_minutes=excluded.max_minutes,updated_by=excluded.updated_by,updated_at=excluded.updated_at", (teacher,game,int(enabled),start,end,max_minutes,st.session_state.get('auth_user','admin'),now_iso()))
            con.commit(); _eco_log(st.session_state.get('auth_user','admin'), 'habilitar' if enabled else 'deshabilitar', teacher, game, f"vigencia={duration}; minutos={max_minutes}")
            st.success("Permiso guardado."); st.rerun()
    rows = con.execute("SELECT g.*,a.display_name FROM eco_teacher_grants g LEFT JOIN accounts a ON a.username=g.teacher ORDER BY g.updated_at DESC").fetchall()
    con.close()
    st.markdown("### Autorizaciones vigentes y anteriores")
    if not rows: st.info("Aún no hay permisos de EcoAventura. Habilita un juego para comenzar.")
    for r in rows:
        with st.expander(f"{'🟢' if _grant_active(r) else '🔒'} {r['display_name'] or r['teacher']} · {r['game']}"):
            st.write(f"Estado: {'Activo' if _grant_active(r) else 'Inactivo o vencido'} · Inicio: {r['starts_at']} · Fin: {r['ends_at'] or 'sin vencimiento'} · Límite por sesión: {r['max_minutes'] or 'sin límite'} min")
            if st.button("Retirar permiso ahora", key=f"eco_revoke_{r['teacher']}_{r['game']}"):
                con2=db_connect(); con2.execute("UPDATE eco_teacher_grants SET enabled=0,updated_by=?,updated_at=? WHERE teacher=? AND game=?",(st.session_state.get('auth_user','admin'),now_iso(),r['teacher'],r['game'])); con2.commit(); con2.close()
                _eco_log(st.session_state.get('auth_user','admin'),'revocar',r['teacher'],r['game'],'revocación manual'); st.rerun()
    con = db_connect(); audit=con.execute("SELECT actor,action,target,game,details,created_at FROM eco_audit ORDER BY id DESC LIMIT 50").fetchall(); con.close()
    with st.expander("📋 Registro de auditoría"):
        if audit: st.dataframe([dict(x) for x in audit], use_container_width=True, hide_index=True)
        else: st.caption("Las acciones de permisos aparecerán aquí.")

def eco_teacher_panel(username: str):
    st.markdown("## 🌎 EcoAventura · Asignar juegos")
    con=db_connect()
    grants=con.execute("SELECT game,enabled,starts_at,ends_at,max_minutes FROM eco_teacher_grants WHERE teacher=? ORDER BY game",(username,)).fetchall()
    available=[r for r in grants if _grant_active(r)]
    if not available:
        st.warning("El administrador todavía no te ha habilitado juegos de EcoAventura, o las autorizaciones vencieron.")
        con.close(); return
    students=con.execute("SELECT username,display_name FROM accounts WHERE role='student' AND approved=1 ORDER BY display_name").fetchall()
    if not students:
        st.info("No hay estudiantes autorizados todavía."); con.close(); return
    with st.form("eco_teacher_assign_form"):
        student=st.selectbox("Estudiante",[r['username'] for r in students],format_func=lambda u:next((f"{r['display_name']} (@{u})" for r in students if r['username']==u),u))
        st.markdown("### 🎮 Selecciona los juegos que vas a asignar")
        st.caption("Marca varios juegos a la vez; cada tarjeta funciona como una opción seleccionable.")
        st.radio("Estilo de selección", ["▦ Cuadros", "◉ Círculos"], horizontal=True, label_visibility="collapsed", key="eco_assign_style")
        st.markdown("<style>div[data-testid='stCheckbox']{border:1px solid rgba(80,150,100,.38);border-radius:14px;padding:10px 12px;background:rgba(100,190,120,.07);margin:4px 0;min-height:54px}div[data-testid='stCheckbox']:hover{border-color:#35a66b;background:rgba(100,190,120,.15)}</style>", unsafe_allow_html=True)
        game_options=[]
        game_cols=st.columns(2)
        game_icons={"EcoSonidos":"🔊","EcoPuff Arcade":"♻️","EcoRunner":"🏃","EcoRetos":"🧠","EcoVerdadero o Falso":"🌿"}
        for gi, grant in enumerate(available):
            with game_cols[gi % 2]:
                label=f"{game_icons.get(grant['game'],'🌎')}  {grant['game']} — {ECO_GAMES.get(grant['game'],'Reto ambiental interactivo')}"
                if st.checkbox(label, key=f"eco_pick_game_{grant['game']}"):
                    game_options.append(grant['game'])
        enabled=st.checkbox("Habilitar los juegos seleccionados",value=True)
        c1,c2=st.columns(2); start_date=c1.date_input("Comienza",value=datetime.now().date()); duration=c2.selectbox("Duración",[1,3,7,15,30,0],format_func=lambda n:"Hasta retirarlo" if n==0 else f"{n} día(s)")
        limit=st.selectbox("Máximo de minutos por sesión",[10,15,20,30,45,60,0],format_func=lambda n:"Sin límite" if n==0 else str(n))
        save=st.form_submit_button("Guardar acceso del estudiante",type="primary")
        if save:
            if not game_options:
                st.error("Selecciona al menos un juego antes de guardar.")
            else:
                start=datetime.combine(start_date,datetime.min.time()).isoformat(timespec="seconds")
                con2=db_connect()
                for game in game_options:
                    parent=next((r for r in available if r['game']==game),None)
                    if not parent: continue
                    end=datetime.combine(start_date+timedelta(days=duration),datetime.max.time()).isoformat(timespec="seconds") if duration else None
                    parent_end=parent['ends_at']
                    if parent_end and (not end or end>parent_end): end=parent_end
                    con2.execute("INSERT INTO eco_student_grants(teacher,student,game,enabled,starts_at,ends_at,max_minutes,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(teacher,student,game) DO UPDATE SET enabled=excluded.enabled,starts_at=excluded.starts_at,ends_at=excluded.ends_at,max_minutes=excluded.max_minutes,updated_at=excluded.updated_at",(username,student,game,int(enabled),start,end,limit,now_iso()))
                    _eco_log(username,'asignar' if enabled else 'retirar',student,game,f"vigencia={duration}; minutos={limit}")
                con2.commit(); con2.close()
                st.success(f"Se guardaron {len(game_options)} juego(s) para {student}."); st.rerun()
    con.close()
    con=db_connect(); assigned=con.execute("SELECT g.*,a.display_name FROM eco_student_grants g JOIN accounts a ON a.username=g.student WHERE g.teacher=? ORDER BY g.updated_at DESC",(username,)).fetchall(); con.close()
    st.markdown("### Estudiantes con acceso asignado")
    if not assigned: st.info("Aún no has asignado juegos a estudiantes.")
    for r in assigned:
        with st.expander(f"{'🟢' if _grant_active(r) else '🔒'} {r['display_name']} · {r['game']}"):
            st.write(f"Inicio: {r['starts_at']} · Fin: {r['ends_at'] or 'sin vencimiento'} · Estado: {'activo' if _grant_active(r) else 'inactivo/vencido'}")
            if st.button("Retirar acceso",key=f"eco_student_revoke_{r['student']}_{r['game']}"):
                c=db_connect(); c.execute("UPDATE eco_student_grants SET enabled=0,updated_at=? WHERE teacher=? AND student=? AND game=?",(now_iso(),username,r['student'],r['game'])); c.commit(); c.close(); _eco_log(username,'revocar estudiante',r['student'],r['game'],'revocación manual'); st.rerun()

def _legacy_allowed(username: str, role: str) -> list:
    """Juegos clásicos de EcoAventura permitidos: admin todos; docente por permiso; estudiante por asignación."""
    if role == "admin":
        return list(ECO_GAMES)
    if role == "teacher":
        con = db_connect(); rows = con.execute("SELECT game,enabled,starts_at,ends_at FROM eco_teacher_grants WHERE teacher=?", (username,)).fetchall(); con.close()
        return [r["game"] for r in rows if _grant_active(r) and r["game"] in ECO_GAMES]
    return [g for g in ECO_GAMES if eco_student_allowed(username, g)]


def _eco_play(game: str, username: str, player_role: str):
    st.markdown(f"### 🎮 {game}")
    if game == "EcoReto en Vivo":
        page_eco_reto_en_vivo(username, player_role)
    elif game in ("EcoVerdadero o Falso","EcoRetos"):
        page_true_false()
    elif game=="EcoPuff Arcade":
        page_ecopuff(username,player_role)
    elif game=="EcoSonidos":
        st.write("Escucha la pista y elige qué fenómeno ambiental representa. Puedes repetir el sonido.")
        questions=[("🌧️ Lluvia cayendo",440,"La lluvia aporta agua a los ecosistemas; evita desperdiciarla."),("🐦 Canto de un ave",660,"Las aves ayudan a mantener el equilibrio de los ecosistemas."),("🚨 Alerta de contaminación",330,"El ruido excesivo también afecta a personas y animales.")]
        if 'eco_sound_pos' not in st.session_state: st.session_state['eco_sound_pos']=0; st.session_state['eco_sound_score']=0
        pos=st.session_state['eco_sound_pos']%len(questions); label,freq,explain=questions[pos]
        import math, struct
        sample_rate=22050; duration=.35
        pcm=b''.join(struct.pack('<h',int(10000*math.sin(2*math.pi*freq*i/sample_rate))) for i in range(int(sample_rate*duration)))
        wav=io.BytesIO()
        with wave.open(wav,'wb') as wf: wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sample_rate); wf.writeframes(pcm)
        st.audio(wav.getvalue(),format='audio/wav')
        st.caption("Sonido electrónico demostrativo: en una siguiente mejora se pueden incorporar grabaciones reales con licencias adecuadas.")
        eco_voice.toggle_ui("sonidos_narr")
        eco_voice.narrate("Escucha la pista con atención. ¿Qué representa mejor la pista?", f"sonidos_q_{pos}")
        answer=st.radio("¿Qué representa mejor la pista?",[x[0] for x in questions],key=f"eco_sound_answer_{pos}")
        if st.button("Comprobar respuesta",key=f"eco_sound_check_{pos}"):
            if answer==label: st.session_state['eco_sound_score']+=10; st.success("¡Correcto! +10 puntos")
            else: st.info(f"La respuesta era: {label}")
            st.write(explain)
            eco_voice.narrate(f"{eco_voice.cheer(answer==label)} {'' if answer==label else 'La respuesta era ' + label + '.'} {explain}", f"sonidos_a_{pos}_{st.session_state['eco_sound_score']}")
            if st.button("Siguiente sonido",key=f"eco_sound_next_{pos}"): st.session_state['eco_sound_pos']+=1; st.rerun()
        st.metric("Puntos de esta sesión",st.session_state['eco_sound_score'])
    else:
        eco_runner.runner_page(username)


ECO_RETO_QUESTIONS = [
    {"topic":"Residuos", "level":"Básico", "q":"¿En qué caneca se depositan los residuos aprovechables limpios y secos en Colombia?", "opts":["Blanca", "Verde", "Negra", "Roja"], "answer":"Blanca", "why":"La caneca blanca es para residuos aprovechables limpios y secos, como papel, cartón, vidrio, metales y plásticos."},
    {"topic":"Residuos", "level":"Básico", "q":"¿Dónde van normalmente las cáscaras de frutas para aprovechamiento orgánico?", "opts":["Blanca", "Verde", "Negra", "Roja"], "answer":"Verde", "why":"La caneca verde se destina a residuos orgánicos aprovechables, según la separación establecida en Colombia."},
    {"topic":"Residuos", "level":"Básico", "q":"Una botella plástica está llena de restos de comida. ¿Qué conviene hacer antes de reciclarla?", "opts":["Dejarla sucia", "Vaciarla y limpiarla", "Quemarla", "Enterrarla"], "answer":"Vaciarla y limpiarla", "why":"Los envases deben entregarse vacíos y, cuando corresponda, limpios y secos para facilitar su aprovechamiento."},
    {"topic":"Agua", "level":"Básico", "q":"¿Cerrar la llave mientras te cepillas los dientes ayuda a ahorrar agua?", "opts":["Verdadero", "Falso"], "answer":"Verdadero", "why":"Cerrar la llave mientras no necesitas el agua reduce el desperdicio."},
    {"topic":"Agua", "level":"Intermedio", "q":"¿Cuál es una señal común de una fuga de agua en casa o en la escuela?", "opts":["El medidor se mueve sin consumo", "Las plantas crecen", "Hay luz solar", "El aire está fresco"], "answer":"El medidor se mueve sin consumo", "why":"Si no se está usando agua y el medidor sigue avanzando, puede haber una fuga."},
    {"topic":"Biodiversidad", "level":"Básico", "q":"¿Las abejas y otros polinizadores ayudan a muchas plantas a reproducirse?", "opts":["Verdadero", "Falso"], "answer":"Verdadero", "why":"La polinización permite la reproducción de muchas plantas y contribuye a la producción de alimentos."},
    {"topic":"Biodiversidad", "level":"Intermedio", "q":"¿Qué acción protege mejor la fauna silvestre?", "opts":["Comprar animales silvestres", "No alimentarlos ni capturarlos", "Llevarlos a casa", "Liberar mascotas exóticas"], "answer":"No alimentarlos ni capturarlos", "why":"Observar la fauna sin intervenir reduce el estrés y los riesgos para los animales y las personas."},
    {"topic":"Energía", "level":"Básico", "q":"¿Qué hábito reduce el consumo eléctrico cuando sales de un salón?", "opts":["Dejar todo encendido", "Apagar luces y equipos que no se usan", "Abrir la nevera", "Encender más lámparas"], "answer":"Apagar luces y equipos que no se usan", "why":"Apagar equipos innecesarios reduce el consumo de energía."},
    {"topic":"Energía", "level":"Intermedio", "q":"¿La energía solar es una fuente renovable?", "opts":["Verdadero", "Falso"], "answer":"Verdadero", "why":"La energía solar proviene de la radiación del Sol y se considera renovable."},
    {"topic":"Cambio climático", "level":"Intermedio", "q":"¿Cuál de estas acciones puede ayudar a reducir emisiones en trayectos cortos?", "opts":["Caminar o usar bicicleta", "Usar siempre un carro individual", "Dejar el motor encendido", "Quemar residuos"], "answer":"Caminar o usar bicicleta", "why":"La movilidad activa evita emisiones directas del transporte motorizado."},
    {"topic":"Cambio climático", "level":"Avanzado", "q":"¿Cuál gas contribuye al calentamiento global cuando aumenta por actividades humanas?", "opts":["Dióxido de carbono", "Oxígeno en condiciones normales", "Helio", "Neón"], "answer":"Dióxido de carbono", "why":"El CO₂ es un gas de efecto invernadero cuya concentración aumenta por la quema de combustibles fósiles y la deforestación."},
    {"topic":"Consumo responsable", "level":"Básico", "q":"¿Cuál suele ser la mejor primera opción para reducir residuos?", "opts":["Comprar más empaques", "Reutilizar y evitar lo innecesario", "Mezclar todos los residuos", "Arrojar al río"], "answer":"Reutilizar y evitar lo innecesario", "why":"Prevenir y reducir residuos es preferible a gestionarlos después de generarlos."},
    {"topic":"Consumo responsable", "level":"Intermedio", "q":"¿Qué significa separar residuos en la fuente?", "opts":["Clasificarlos donde se generan", "Mezclarlos y separarlos años después", "Quemarlos", "Arrojarlos al suelo"], "answer":"Clasificarlos donde se generan", "why":"Separarlos desde el lugar donde se producen mejora su aprovechamiento y manejo."},
    {"topic":"Agua", "level":"Avanzado", "q":"¿Por qué no se deben arrojar aceite usado por el desagüe?", "opts":["Puede contaminar el agua y obstruir tuberías", "Purifica los ríos", "Desaparece sin impacto", "Aumenta el oxígeno"], "answer":"Puede contaminar el agua y obstruir tuberías", "why":"El aceite debe recogerse y entregarse a un sistema de gestión adecuado, no verterse al alcantarillado."},
]

def page_eco_reto_en_vivo(username: str, role: str = "student") -> None:
    """EcoReto educativo autoguiado; registra la clasificación final local de cada sesión."""
    con = db_connect()
    con.execute("CREATE TABLE IF NOT EXISTS eco_reto_scores (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, display_name TEXT NOT NULL, topic TEXT NOT NULL, mode TEXT NOT NULL, hits INTEGER NOT NULL, total INTEGER NOT NULL, points INTEGER NOT NULL, seconds REAL NOT NULL, created_at TEXT NOT NULL)")
    con.commit()
    st.markdown("### ⚡ EcoReto en Vivo")
    st.caption("Ronda de preguntas ambientales con puntos, cronómetro por pregunta y retroalimentación. Esta versión es autoguiada; la sala sincronizada con código para competir en varios dispositivos se añadirá en una siguiente etapa.")
    session_key = f"eco_reto_live_{role}_{username}"
    game = st.session_state.get(session_key)
    if not game:
        with st.form(f"eco_reto_setup_{role}_{username}"):
            topic = st.selectbox("Temática", ["Todas", "Residuos", "Agua", "Biodiversidad", "Energía", "Cambio climático", "Consumo responsable"])
            level = st.selectbox("Nivel", ["Todos", "Básico", "Intermedio", "Avanzado"])
            mode = st.radio("Tipo de pregunta", ["Mixto", "Selección múltiple", "Verdadero o falso"], horizontal=True)
            count = st.number_input("Cantidad de preguntas", min_value=3, max_value=14, value=8, step=1)
            seconds = st.select_slider("Tiempo por pregunta", options=[10, 15, 20, 30, 45, 60], value=20)
            start = st.form_submit_button("🚀 Comenzar EcoReto", type="primary")
        if start:
            pool = [q.copy() for q in ECO_RETO_QUESTIONS if (topic == "Todas" or q["topic"] == topic) and (level == "Todos" or q["level"] == level)]
            if mode == "Verdadero o falso":
                pool = [q for q in pool if q["opts"] == ["Verdadero", "Falso"]]
            elif mode == "Selección múltiple":
                pool = [q for q in pool if q["opts"] != ["Verdadero", "Falso"]]
            if not pool:
                st.error("No hay suficientes preguntas para esa combinación. Prueba otra temática, nivel o tipo.")
            else:
                random.shuffle(pool)
                pool = pool[:min(int(count), len(pool))]
                st.session_state[session_key] = {"questions": pool, "pos": 0, "hits": 0, "points": 0, "answers": [], "started": time.time(), "question_started": time.time(), "seconds": int(seconds), "topic": topic, "mode": mode, "done": False}
                st.rerun()
        con.close()
        return
    questions = game["questions"]
    pos = game["pos"]
    if pos >= len(questions):
        game["done"] = True
    if game.get("done"):
        elapsed = max(0.0, time.time() - game["started"])
        total = len(questions)
        pct = round(100 * game["hits"] / total)
        a,b,c = st.columns(3)
        a.metric("Respuestas correctas", f"{game['hits']} / {total}")
        b.metric("Puntuación", game["points"])
        c.metric("Precisión", f"{pct}%")
        st.success("¡Reto completado! Cada respuesta correcta suma puntos; responder rápido aporta una bonificación.")
        if eco_voice.narrate(eco_voice.final_line(game["hits"], total, game["points"]), f"reto_final_{game.get('gid','x')}") and pct >= 80:
            st.balloons()
        if not game.get("saved"):
            account = con.execute("SELECT display_name FROM accounts WHERE username=?", (username,)).fetchone()
            display = account["display_name"] if account else username
            con.execute("INSERT INTO eco_reto_scores(username,display_name,topic,mode,hits,total,points,seconds,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (username, display, game["topic"], game["mode"], game["hits"], total, game["points"], elapsed, now_iso()))
            con.commit(); game["saved"] = True
        st.markdown("#### Resumen de respuestas")
        for idx, item in enumerate(game["answers"], 1):
            st.markdown(f"**{idx}. {html.escape(item['question'])}**  \nTu respuesta: {html.escape(item['chosen'])} · Correcta: {html.escape(item['answer'])}  \n{'✅' if item['correct'] else '❌'} {html.escape(item['why'])}")
        st.markdown("#### 🏆 Mejores resultados")
        scores = con.execute("SELECT display_name,MAX(points) AS points,MAX(hits) AS hits,MIN(seconds) AS seconds FROM eco_reto_scores GROUP BY username ORDER BY points DESC,hits DESC,seconds ASC LIMIT 10").fetchall()
        if scores:
            st.dataframe([{"Jugador": r["display_name"], "Puntos": r["points"], "Aciertos": r["hits"], "Tiempo (s)": round(r["seconds"], 1)} for r in scores], use_container_width=True, hide_index=True)
        if st.button("🔁 Jugar otra ronda", key=f"eco_reto_again_{role}_{username}", type="primary"):
            st.session_state.pop(session_key, None); con.close(); st.rerun()
        con.close(); return
    q = questions[pos]
    elapsed_q = max(0.0, time.time() - game["question_started"])
    st.progress(pos / len(questions), text=f"Pregunta {pos+1} de {len(questions)}")
    a,b,c = st.columns(3)
    a.metric("Puntos", game["points"]); b.metric("Aciertos", game["hits"]); c.metric("Tiempo objetivo", f"{game['seconds']} s")
    st.markdown(f"**Tema: {q['topic']} · Nivel: {q['level']}**")
    st.markdown(f"## {q['q']}")
    eco_voice.toggle_ui("reto_narr")
    if "gid" not in game:
        game["gid"] = secrets.token_hex(3)
    if not (game.get("last_result") and len(game["answers"]) == pos + 1):
        eco_voice.narrate(eco_voice.question_line(q["q"], "tf" if q["opts"] == ["Verdadero", "Falso"] else "mcq", None if q["opts"] == ["Verdadero", "Falso"] else q["opts"]), f"reto_q_{game['gid']}_{pos}")
    if elapsed_q > game["seconds"]:
        st.warning("⏱️ Se agotó el tiempo para esta pregunta. Selecciona la respuesta para continuar; no recibirás bonificación por rapidez.")
    last = game.get("last_result")
    if last and len(game["answers"]) == pos + 1:
        if last["correct"]: st.success(f"¡Correcto! +{last['gained']} puntos")
        else: st.error(f"Respuesta incorrecta. La respuesta correcta era: {last['answer']}")
        st.info(last["why"])
        eco_voice.narrate(f"{eco_voice.cheer(last['correct'])} {'' if last['correct'] else 'La respuesta correcta era: ' + last['answer'] + '.'} {last['why']}", f"reto_a_{game.get('gid','x')}_{pos}")
        if st.button("Siguiente pregunta ▶", key=f"eco_reto_next_{role}_{username}_{pos}", type="primary"):
            game["pos"] += 1; game.pop("last_result", None); game["question_started"] = time.time(); st.rerun()
        con.close(); return
    choice = st.radio("Elige una respuesta", q["opts"], key=f"eco_reto_choice_{role}_{username}_{pos}")
    if st.button("Comprobar respuesta", key=f"eco_reto_check_{role}_{username}_{pos}", type="primary"):
        correct = choice == q["answer"]
        bonus = max(0, int((game["seconds"] - elapsed_q) * 2)) if elapsed_q <= game["seconds"] else 0
        gained = (100 + bonus) if correct else 0
        game["hits"] += int(correct); game["points"] += gained
        game["answers"].append({"question":q["q"], "chosen":choice, "answer":q["answer"], "correct":correct, "why":q["why"], "points":gained})
        game["last_result"] = {"correct":correct,"gained":gained,"why":q["why"],"answer":q["answer"]}
        game["question_started"] = time.time()
        st.rerun()
    con.close()


def student_portal():
    """Mi panel: progreso, salas por PIN de clase, historial y juegos asignados (la barra superior la dibuja eco.pages.shell)."""
    username = st.session_state["auth_user"]
    con = db_connect(); account = con.execute("SELECT display_name FROM accounts WHERE username=? AND approved=1 AND role='student'", (username,)).fetchone(); con.close()
    if not account:
        st.error("Esta cuenta ya no está autorizada."); st.session_state.clear(); st.rerun()
    display = account["display_name"]
    eco_pages.progress_strip(_ctx(username, "student", display))
    nav_a, nav_b = st.columns([1, 1])
    with nav_a:
        if eco_student_allowed(username, "EcoPuff Arcade") and st.button("💥 Abrir EcoPuff", use_container_width=True, key="student_open_puff"):
            st.session_state["student_puff_mode"] = True
    with nav_b:
        if st.session_state.get("student_puff_mode") and st.button("↩ Volver a mi panel", use_container_width=True, key="student_close_puff"):
            st.session_state["student_puff_mode"] = False
            st.rerun()
    if st.session_state.get("student_puff_mode"):
        if not eco_student_allowed(username, "EcoPuff Arcade"):
            st.session_state["student_puff_mode"] = False
            st.warning("El acceso a EcoPuff no está habilitado o venció.")
        else:
            page_ecopuff(username, "student")
            return
    con = db_connect()
    unread = con.execute("SELECT id,sender,body,created_at FROM messages WHERE recipient=? ORDER BY id DESC LIMIT 20", (username,)).fetchall()
    totals = con.execute("SELECT COUNT(*) total, SUM(is_correct) hits, SUM(CASE WHEN is_correct=0 THEN 1 ELSE 0 END) misses, COALESCE(SUM(points),0) points FROM attempts WHERE username=?", (username,)).fetchone()
    rooms = con.execute("SELECT gs.code, c.title, gs.status, gs.pos, c.question_count FROM game_sessions gs JOIN classes c ON c.code=gs.code WHERE gs.username=? ORDER BY gs.started_at DESC LIMIT 10", (username,)).fetchall()
    con.close()
    # Los mensajes privados se muestran en el desplegable compacto de la campana superior.
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Retos respondidos", int(totals["total"] or 0)); m2.metric("Retos ganados", int(totals["hits"] or 0)); m3.metric("Retos perdidos", int(totals["misses"] or 0)); m4.metric("Puntos acumulados", int(totals["points"] or 0))
    if rooms:
        with st.expander("🏆 Mi historial de actividades"):
            for r in rooms:
                st.write(f"**{r['title']}** · Sala `{r['code']}` · {('Finalizada' if r['status']=='finalizada' else 'En curso')} · {min(r['pos'],r['question_count'])}/{r['question_count']} retos")
    code = st.session_state.get("exam_code")
    if st.session_state.get("student_noise_mode"):
        st.markdown(f"<div class='eg-hero'><div><h1>🔊 EcoSilencio</h1><p>Observa el ambiente y ayuda al grupo a recuperar la zona de concentración.</p></div></div>", unsafe_allow_html=True)
        live_noise_monitor(55, 65)
        if st.button("Volver a mi panel", key="student_noise_back"):
            st.session_state["student_noise_mode"] = False; st.rerun()
        return
    if code:
        exam_view(code, username, display)
        return
    st.markdown(f"<div class='eg-hero'><div><h1>🎮 ¡Hola, {html.escape(display)}!</h1><p>Tu espacio de retos ecológicos. Entra a una sala con el PIN de tu docente o practica el cuidado del ambiente sonoro.</p></div></div>", unsafe_allow_html=True)
    if eco_student_allowed(username, "EcoVerdadero o Falso") or eco_student_allowed(username, "EcoRetos"):
        if st.button("🌎 Jugar EcoVerdadero o Falso", type="primary", key="student_tf_open"):
            st.session_state["student_tf_mode"] = True; st.rerun()
    if st.session_state.get("student_tf_mode"):
        if not (eco_student_allowed(username, "EcoVerdadero o Falso") or eco_student_allowed(username, "EcoRetos")):
            st.session_state["student_tf_mode"] = False
            st.warning("El acceso a este juego no está habilitado o venció.")
        else:
            page_true_false()
        if st.button("Volver a mi panel", key="student_tf_back"):
            st.session_state["student_tf_mode"] = False; st.rerun()
        return
    if st.button("🔊 Abrir semáforo de sonido", type="primary", key="student_noise_open"):
        st.session_state["student_noise_mode"] = True; st.rerun()
    with st.form("join_room"):
        pin = st.text_input("PIN de la sala", max_chars=6).strip().upper()
        enter = st.form_submit_button("Entrar a la actividad", type="primary")
    if not enter:
        return
    key = f"pin:{username}"
    wait = guard_remaining(key)
    if wait:
        st.error(_lock_message(wait)); return
    con = db_connect()
    try:
        res = exam_enter(con, pin, username, display)
        summary = exam_summary(con, pin, username) if res["result"] == "finished" else None
    finally:
        con.close()
    r = res["result"]
    if r in ("no_room", "not_member"):
        guard_fail(key)
        st.error("PIN incorrecto, o tu cuenta no está inscrita en esa sala. Revisa el PIN o pídele al docente que te agregue.")
    elif r == "closed":
        st.warning("🔒 Esta sala está cerrada por el docente.")
    elif r == "finished":
        st.warning(f"✅ Ya realizaste esta actividad. Solo se permite un intento por estudiante. Tu resultado: {summary['hits']}/{summary['total']} aciertos ({summary['pct']}%).")
    else:
        guard_clear(key)
        st.session_state["exam_code"] = pin
        st.query_params["eg_room"] = pin
        if r == "resumed":
            st.session_state["exam_notice"] = f"⏳ Ya estabas realizando esta actividad: continúas en el reto {res['pos'] + 1} de {res['total']}. No se reinicia ni se sortea de nuevo."
        else:
            st.session_state["exam_notice"] = "🚀 ¡Comienza tu misión! Tienes una sola oportunidad: si recargas la página, continuarás donde ibas."
        st.rerun()


# ── Piezas visuales del juego ────────────────────────────────────────────────
def _track_html(pos: int, total: int) -> str:
    pct = int(100 * pos / max(1, total))
    return (f"<div class='gm-track'><div class='gm-fill' style='width:{pct}%'></div>"
            f"<div class='gm-hero' style='left:{max(2, min(pct, 98))}%'>🦸</div><div class='gm-goal'>🌍</div></div>")


def _card_html(qtype: str, q: dict, pos: int, total: int) -> str:
    kind = "noise" if qtype == "auditiva" else "waste"
    ask = "¿Qué acción es la más adecuada?" if qtype == "auditiva" else "¿En qué caneca lo depositas?"
    return (f"<div class='gm-card {kind}'><span class='gm-chip'>Reto {pos + 1} de {total}</span>"
            f"<div class='em'>{html.escape(q['emoji'])}</div><h3>{html.escape(q['objeto'])}</h3><div class='q'>{ask}</div></div>")


def render_choices(kind: str, qtype: str, pos: int, options: list, disabled: list, callback, args: tuple) -> None:
    if qtype == "residuos":
        cols = st.columns(4)
        for col, opt in zip(cols, options):
            with col:
                sbtn(f"{BIN_ICON[opt]} {BIN_LABEL[opt]}", key=f"bin_{opt}_{kind}_{pos}", on_click=callback, args=(*args, pos, opt), disabled=opt in disabled)
    else:
        cols = st.columns(2)
        for i, opt in enumerate(options):
            with cols[i % 2]:
                sbtn(opt, key=f"opt_{i}_{kind}_{pos}", on_click=callback, args=(*args, pos, opt), disabled=opt in disabled)


def correct_text(qtype: str, q: dict) -> str:
    if qtype == "auditiva":
        return f"Respuesta recomendada: {q['correcta']}. {q['nota']}"
    return f"La caneca correcta es la {BIN_WORD[q['correcta']]}. {q['nota']}"


def render_final(summary: dict, display: str, review: list | None, show_points: bool, balloon_key: str) -> None:
    title, medal = rank_for(summary["pct"])
    stars = "⭐" * max(1, min(5, round(summary["pct"] / 20))) + "☆" * (5 - max(1, min(5, round(summary["pct"] / 20))))
    tiles = (f"<div class='gm-tile'><div class='n'>{summary['hits']}/{summary['total']}</div><div class='l'>Aciertos</div></div>"
             f"<div class='gm-tile'><div class='n'>{summary['misses']}</div><div class='l'>Errores</div></div>"
             f"<div class='gm-tile'><div class='n'>{summary['pct']}%</div><div class='l'>Precisión</div></div>")
    if show_points:
        tiles += f"<div class='gm-tile'><div class='n'>{summary['points']}</div><div class='l'>Puntos</div></div>"
    if summary.get("seconds") is not None:
        tiles += f"<div class='gm-tile'><div class='n'>{fmt_seconds(summary['seconds'])}</div><div class='l'>Tiempo</div></div>"
    st.markdown(f"<div class='gm-final'><div class='medal'>{medal}</div><h2>¡Misión cumplida, {html.escape(display)}!</h2>"
                f"<div style='font-size:1.2rem;font-weight:700'>{title}</div><div class='gm-stars'>{stars}</div><div class='gm-tiles'>{tiles}</div></div>", unsafe_allow_html=True)
    if not st.session_state.get(balloon_key):
        st.session_state[balloon_key] = True
        if summary["pct"] >= 60:
            st.balloons()
        else:
            st.snow()
        stop_browser_speech()
        speak_browser(f"Misión cumplida. Tuviste {summary['hits']} aciertos de {summary['total']}. Tu precisión fue del {summary['pct']} por ciento. Gracias por cuidar el planeta.")
    if review:
        with st.expander("📋 Revisar mis respuestas"):
            for r in review:
                st.write(("✅" if r["is_correct"] else "❌") + f" **{r['qpos'] + 1}. {r['question']}** — respondiste: {r['chosen']} · correcta: {r['correct']}")


# ── EXAMEN (estudiantes): un intento, progreso guardado en la base de datos ──
def _exam_pick(code: str, username: str, pos: int, chosen: str) -> None:
    con = db_connect()
    try:
        res = exam_answer(con, code, username, pos, chosen)
        if res == "recorded_bad":
            # Guardar explicación completa para narrarla en voz alta tras el rerun.
            state = exam_state(con, code, username)
            if state and state.get("order") and pos < len(state["order"]):
                qtype, q = resolve_entry(state["order"][pos])
                st.session_state["exam_speak"] = "No es correcto. Inténtalo de nuevo. " + correct_text(qtype, q)
            else:
                st.session_state["exam_speak"] = "No es correcto. Inténtalo de nuevo."
        elif res == "recorded_ok":
            st.session_state["exam_speak_ok"] = True
    finally:
        con.close()


def _exam_next(code: str, username: str, pos: int) -> None:
    con = db_connect()
    try:
        exam_next(con, code, username, pos)
    finally:
        con.close()


def exam_view(code: str, username: str, display: str) -> None:
    st.markdown(GAME_CSS, unsafe_allow_html=True)
    stop_browser_speech()
    con = db_connect()
    try:
        state = exam_state(con, code, username)
        if state is None:
            st.session_state.pop("exam_code", None); st.error("No se encontró tu actividad. Vuelve a ingresar el PIN."); st.rerun()
        summary = review = None
        if state["status"] == "finalizada":
            summary = exam_summary(con, code, username)
            review = exam_review(con, code, username) if state["review"] else None
    finally:
        con.close()
    notice = st.session_state.pop("exam_notice", None)
    if notice:
        st.info(notice)
    st.markdown(f"<div class='gm-top'><div>🎮 <b>{html.escape(display)}</b></div><div><span class='gm-chip'>{html.escape(state['title'])}</span> <span class='gm-chip'>PIN {html.escape(code)}</span></div></div>", unsafe_allow_html=True)
    if state["status"] == "finalizada":
        st.success("🔒 Actividad finalizada. Tu intento quedó registrado y no se puede repetir.")
        render_final(summary, display, review, show_points=True, balloon_key=f"exam_balloons_{code}")
        return
    if state["closed"]:
        st.warning("🔒 El docente cerró esta sala. Tu progreso quedó guardado.")
        return
    pos, total, mode = state["pos"], state["total"], state["mode"]
    qtype, q = resolve_entry(state["order"][pos])
    st.markdown(_track_html(pos, total), unsafe_allow_html=True)
    st.markdown(_card_html(qtype, q, pos, total), unsafe_allow_html=True)
    attempts = state["attempts"]
    if state["locked"]:
        if mode == "restringido":
            st.markdown(f"<div class='gm-lock ok'>✅ ¡Correcto!<div style='font-weight:500;font-size:1rem'>{html.escape(correct_text(qtype, q))}</div></div>", unsafe_allow_html=True)
            if st.session_state.pop("exam_speak_ok", False):
                speak_browser("Correcto. " + correct_text(qtype, q))
        else:
            tips = ["¡Misión registrada! 🌿", "¡Buen ritmo, guardián! 🚀", "¡Respuesta guardada! 🔒", "¡Sigue así, héroe del planeta! 🌎"]
            st.markdown(f"<div class='gm-lock'>{tips[pos % len(tips)]}<div style='font-weight:500;font-size:1rem'>Tu respuesta quedó guardada. Los resultados se muestran al finalizar.</div></div>", unsafe_allow_html=True)
        sbtn("🏁 Terminar actividad" if pos + 1 >= total else "Siguiente reto ▶", key=f"next_exam_{pos}", on_click=_exam_next, args=(code, username, pos))
        return
    if attempts:  # modo restringido: ya falló al menos una vez este reto
        st.markdown(f"<div class='gm-lock bad'>❌ Esa respuesta no es correcta. Inténtalo de nuevo (intentos: {len(attempts)}).</div>", unsafe_allow_html=True)
        # En modo restringido se ofrece retroalimentación educativa, no solo un aviso de error.
        st.info("**¿Por qué?** " + correct_text(qtype, q))
        msg = st.session_state.pop("exam_speak", None)
        if msg:
            speak_browser(msg)
    options = option_list(qtype, q, f"{code}|{username}|{pos}")
    render_choices("exam", qtype, pos, options, [a["chosen"] for a in attempts], _exam_pick, (code, username))
    st.caption("Elige con un solo clic. Una vez respondido, el reto queda bloqueado." if mode == "libre" else "Modo restringido: debes acertar para avanzar.")


# ── ENSAYO (administrador): sin base de datos, con puntaje y rachas ──────────
def _prac_start(activity: str, count: int, mode: str) -> None:
    st.session_state["prac"] = {"order": build_order(activity, count), "pos": 0, "att": {}, "points": 0, "streak": 0,
                                "best": 0, "hits": 0, "mode": mode, "seed": secrets.token_hex(4), "done": False, "msg": ""}


def _prac_pick(pos: int, chosen: str) -> None:
    p = st.session_state.get("prac")
    if not p or p["done"] or p["pos"] != pos:
        return
    qtype, q = resolve_entry(p["order"][pos])
    att = p["att"].setdefault(pos, [])
    if chosen not in option_list(qtype, q, f"{p['seed']}|{pos}") or chosen in [a["chosen"] for a in att]:
        return
    if is_locked(p["mode"], att):
        return
    ok = chosen == q["correcta"]
    first = not att
    att.append({"chosen": chosen, "is_correct": int(ok)})
    if ok and first:
        p["streak"] += 1; p["best"] = max(p["best"], p["streak"]); p["hits"] += 1
        bonus = 5 if p["streak"] >= 3 else 0
        p["points"] += POINTS_PER_HIT + bonus
        p["msg"] = f"+{POINTS_PER_HIT + bonus} puntos" + (f" · ¡racha x{p['streak']}! 🔥" if bonus else "")
    elif not ok:
        p["streak"] = 0; p["msg"] = ""
        p["speak"] = "No es correcto. Inténtalo de nuevo. " + correct_text(qtype, q)


def _prac_next(pos: int) -> None:
    p = st.session_state.get("prac")
    if not p or p["done"] or p["pos"] != pos:
        return
    if not is_locked(p["mode"], p["att"].get(pos, [])):
        return
    p["pos"] += 1
    p["msg"] = ""
    if p["pos"] >= len(p["order"]):
        p["done"] = True


def page_notifications():
    st.subheader("🔔 Centro de notificaciones")
    st.caption("Este panel se actualiza automáticamente cada 10 segundos mientras esté abierto.")
    if hasattr(st, "fragment"):
        @st.fragment(run_every="10s")
        def live_notifications():
            con = db_connect()
            pending = con.execute("SELECT username,display_name,created_at FROM accounts WHERE role='student' AND approved=0 ORDER BY created_at DESC").fetchall()
            notes = con.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 50").fetchall()
            con.close()
            a,b = st.columns(2); a.metric("Solicitudes pendientes",len(pending)); b.metric("Notificaciones recientes",len(notes))
            if pending:
                st.markdown("#### Nuevos registros")
                for r in pending:
                    st.markdown(f"**{html.escape(r['display_name'])}** · `@{r['username']}` · {r['created_at']}")
            else: st.success("No hay registros pendientes de autorización.")
            st.markdown("#### Actividad reciente")
            if notes:
                for n in notes:
                    st.markdown(f"**{html.escape(n['title'])}** · {n['created_at']}\n\n{html.escape(n['body'])}")
            else: st.info("Aún no hay notificaciones.")
        live_notifications()
    else:
        if st.button("↻ Actualizar notificaciones"): st.rerun()
        con = db_connect()
        pending = con.execute("SELECT username,display_name,created_at FROM accounts WHERE role='student' AND approved=0 ORDER BY created_at DESC").fetchall()
        notes = con.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 50").fetchall(); con.close()
        st.metric("Solicitudes pendientes",len(pending))
        for r in pending: st.write(f"{r['display_name']} · @{r['username']} · {r['created_at']}")
        for n in notes: st.write(f"{n['title']} · {n['created_at']} — {n['body']}")


def page_practice():
    """Modo ensayo del administrador. No guarda resultados de estudiantes."""
    st.markdown(GAME_CSS, unsafe_allow_html=True)
    stop_browser_speech()
    st.subheader("🎮 EcoReto · modo ensayo")
    st.caption("Aquí practicas con puntaje, rachas y respuestas visibles. Los exámenes reales se crean en «Sala de clase» y solo permiten un intento.")
    p = st.session_state.get("prac")
    if not p:
        with st.form("prac_setup"):
            act = st.selectbox("Actividad", list(ACTIVITY_LABEL.values()))
            cnt = st.number_input("Cantidad de retos", min_value=1, max_value=60, value=10, step=1)
            mode = st.radio("Modo", ["Libre (puedes avanzar con error)", "Restringido (hay que acertar para avanzar)"])
            go = st.form_submit_button("🚀 Iniciar ensayo", type="primary")
        if go:
            key = [k for k, v in ACTIVITY_LABEL.items() if v == act][0]
            _prac_start(key, int(cnt), "restringido" if mode.startswith("Restringido") else "libre")
            st.rerun()
        return
    pos, total = p["pos"], len(p["order"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Puntos", p["points"]); c2.metric("Racha 🔥", p["streak"]); c3.metric("Nivel", p["points"] // 50 + 1)
    if p["done"]:
        summary = {"total": total, "hits": p["hits"], "misses": total - p["hits"], "points": p["points"], "pct": round(100 * p["hits"] / total), "seconds": None}
        render_final(summary, "Guardián", None, True, f"prac_balloons_{p['seed']}")
        if sbtn("🔀 Nuevo ensayo", key="prac_again"):
            st.session_state.pop("prac", None); st.rerun()
        return
    qtype, q = resolve_entry(p["order"][pos])
    st.markdown(_track_html(pos, total), unsafe_allow_html=True)
    st.markdown(_card_html(qtype, q, pos, total), unsafe_allow_html=True)
    att = p["att"].get(pos, [])
    # Narrar el error una sola vez, después de que el usuario selecciona su respuesta.
    speak_msg = p.pop("speak", None)
    if speak_msg:
        speak_browser(speak_msg)
    if is_locked(p["mode"], att):
        ok = bool(att[0]["is_correct"]) if p["mode"] == "libre" else True
        cls, head = ("ok", "✅ ¡Correcto!") if ok else ("bad", "❌ No era esa")
        st.markdown(f"<div class='gm-lock {cls}'>{head} {html.escape(p['msg'])}<div style='font-weight:500;font-size:1rem'>{html.escape(correct_text(qtype, q))}</div></div>", unsafe_allow_html=True)
        sbtn("🏁 Terminar ensayo" if pos + 1 >= total else "Siguiente reto ▶", key=f"next_prac_{pos}", on_click=_prac_next, args=(pos,))
    else:
        if att:
            st.markdown("<div class='gm-lock bad'>❌ Esa no es. Inténtalo de nuevo.</div>", unsafe_allow_html=True)
        render_choices("prac", qtype, pos, option_list(qtype, q, f"{p['seed']}|{pos}"), [a["chosen"] for a in att], _prac_pick, ())
    if sbtn("↩️ Abandonar ensayo", key="prac_quit"):
        st.session_state.pop("prac", None); st.rerun()


# ── Panel del docente ────────────────────────────────────────────────────────
def page_classroom():
    st.subheader("🏫 Sala de clase · panel del docente")
    st.caption("Crea una sala, comparte el PIN y consulta los resultados. Cada estudiante tiene UNA sola oportunidad por sala; si se recarga la página, retoma donde iba.")
    mode = st.radio("Modalidad de juego", ["Libre (permite avanzar y registra errores)", "Restringido (hay que acertar para avanzar)"], horizontal=False)
    teacher = st.text_input("Nombre del docente", key="teacher_name", placeholder="Ej. Profesor Juan")
    title = st.text_input("Nombre de la clase / examen", value="Reto ecológico")
    activity_choice = st.selectbox("Actividad de la sala", ["Clasificación de residuos", "Contaminación auditiva", "Taller combinado (residuos + auditiva)"])
    activity = {"Clasificación de residuos": "residuos", "Contaminación auditiva": "auditiva", "Taller combinado (residuos + auditiva)": "ambos"}[activity_choice]
    count_choice = st.selectbox("Cantidad de retos por estudiante (máximo 60)", ["10", "20", "30", "50", "60", "Personalizado"], index=0)
    custom_count = st.number_input("Número personalizado (máximo 60)", min_value=1, max_value=60, value=15, step=1, disabled=count_choice != "Personalizado")
    question_count = int(custom_count if count_choice == "Personalizado" else count_choice)
    review = st.checkbox("Permitir que el estudiante revise sus respuestas al terminar", value=False,
                         help="Desactívalo si otros compañeros aún no presentan el examen: así no se filtran las respuestas.")
    st.caption(f"Cada participante recibirá {question_count} retos en orden aleatorio distinto; el puntaje no se muestra durante el examen.")
    con = db_connect()
    registered = con.execute("SELECT username, display_name FROM accounts WHERE role='student' AND approved=1 ORDER BY display_name, username").fetchall()
    con.close()
    if registered:
        student_options = {r["username"]: f"{r['display_name']} · @{r['username']}" for r in registered}
        selected_users = st.multiselect("Selecciona los estudiantes para esta sala", options=list(student_options.keys()),
                                        format_func=lambda u: student_options.get(u, u),
                                        help="Solo aparecen estudiantes registrados y autorizados.")
        st.caption(f"Estudiantes autorizados disponibles: {len(registered)} · Seleccionados para esta sala: {len(selected_users)}")
    else:
        selected_users = []
        st.info("Todavía no hay estudiantes autorizados. Pide que se registren y luego aprueba sus cuentas en ‘Autorizar estudiantes’.")
    if st.button("Crear sala de clase", type="primary"):
        if not selected_users:
            st.error("Selecciona al menos un estudiante autorizado para crear la sala.")
        else:
            account_map = {r["username"]: r["display_name"] for r in registered}
            names = [account_map[u] for u in selected_users if u in account_map]
            code = secrets.token_hex(3).upper()
            con = db_connect()
            con.execute("INSERT INTO classes(code,title,created_at,mode,teacher,question_count,activity,review,closed) VALUES(?,?,?,?,?,?,?,?,0)", (code, title.strip() or "Reto ecológico", now_iso(), "restringido" if mode.startswith("Restringido") else "libre", teacher.strip() or "Docente", question_count, activity, int(review)))
            con.executemany("INSERT INTO participants(code,name,username) VALUES(?,?,?)", [(code, account_map[u], u) for u in selected_users if u in account_map])
            con.commit(); con.close()
            st.session_state["active_class_code"] = code
            st.success(f"Sala creada correctamente. PIN de acceso: {code}")
            st.write("**Participantes incluidos:** " + ", ".join(names))
            st.info(f"Actividad asignada: {activity_choice}. Cada estudiante entra con su propia cuenta y este PIN, y solo puede hacerla una vez.")

    code_input = st.text_input("Código de sala para consultar resultados", value=st.session_state.get("active_class_code", ""))
    if st.button("Ver resultados de la sala") or st.session_state.get("results_open") == code_input.strip().upper() != "":
        code = code_input.strip().upper()
        con = db_connect()
        room = con.execute("SELECT * FROM classes WHERE code=?", (code,)).fetchone()
        if not room:
            con.close(); st.session_state.pop("results_open", None)
            st.error("No existe esa sala en esta instalación. Comprueba el código.")
        else:
            st.session_state["results_open"] = code
            df = room_results(con, code)
            details = con.execute("SELECT student, username, qpos+1 AS reto, attempt_no AS intento, question AS pregunta, chosen AS elegida, correct AS correcta, is_correct AS acierto, points AS puntos, created_at AS fecha FROM attempts WHERE code=? ORDER BY id DESC", (code,)).fetchall()
            con.close()
            st.markdown(f"### {room['title']} · código **{code}**")
            st.caption(f"Docente: {room['teacher']} · Modo: {room['mode']} · Actividad: {ACTIVITY_LABEL.get(room['activity'], room['activity'])} · Retos por participante: {room['question_count']} · Estado: {'🔒 cerrada' if room['closed'] else '🟢 abierta'}")
            c1, c2 = st.columns(2)
            if c1.button("🔓 Abrir sala" if room["closed"] else "🔒 Cerrar sala (nadie más responde)", key=f"toggle_{code}"):
                con = db_connect(); con.execute("UPDATE classes SET closed=? WHERE code=?", (0 if room["closed"] else 1, code)); con.commit(); con.close(); st.rerun()
            if len(df):
                done = int((df["Estado"] == "Finalizada").sum())
                st.progress(done / len(df), text=f"{done} de {len(df)} estudiantes han finalizado")
                show_df(df)
                st.download_button("Descargar resultados CSV", df.to_csv(index=False).encode("utf-8-sig"), f"resultados_{code}.csv", "text/csv")
            else:
                st.info("Esta sala no tiene participantes.")
            if details:
                with st.expander("Respuestas individuales (todos los intentos)"):
                    show_df(pd.DataFrame([dict(r) for r in details]))
            started = df[df["Estado"] != "Sin iniciar"] if len(df) else df
            if len(started):
                with st.expander("⚠️ Permitir que un estudiante repita (caso excepcional)"):
                    st.caption("Úsalo solo si hubo una falla técnica comprobada. Se borran sus respuestas y se sortea un examen nuevo.")
                    who = st.selectbox("Estudiante", list(started["Usuario"]), format_func=lambda u: f"{started.loc[started['Usuario'] == u, 'Estudiante'].iloc[0]} (@{u})", key=f"reset_who_{code}")
                    sure = st.checkbox("Confirmo que quiero borrar su intento", key=f"reset_ok_{code}")
                    if st.button("Permitir que repita", disabled=not sure, key=f"reset_btn_{code}"):
                        con = db_connect(); exam_reset(con, code, who); con.close(); st.success("Intento borrado. El estudiante puede volver a entrar con el PIN."); st.rerun()
            st.markdown("#### Acceso de los estudiantes")
            public_url = os.environ.get("ECOGUARDIAN_PUBLIC_URL", "").strip().rstrip("/")
            if public_url:
                st.code(public_url, language=None)
                st.caption("Comparte esta dirección junto con el PIN.")
            else:
                st.info("Comparte la dirección base donde abriste EcoGuardian AI y el PIN de sala. Si usas internet, configura ECOGUARDIAN_PUBLIC_URL para mostrarla aquí.")
            st.code(f"PIN de sala: {code}", language=None)
            st.caption("Los estudiantes deben crear una cuenta, esperar la autorización, iniciar sesión y escribir este PIN.")
            with st.expander("✉️ Enviar PIN o mensaje a estudiantes"):
                recipients = con_placeholder = None
                cx = db_connect()
                room_students = cx.execute("SELECT a.username,a.display_name FROM participants p JOIN accounts a ON a.username=p.username WHERE p.code=? ORDER BY a.display_name", (code,)).fetchall()
                cx.close()
                if room_students:
                    names = {r["username"]:r["display_name"] for r in room_students}
                    chosen_recipients = st.multiselect("Destinatarios", list(names), format_func=lambda u: f"{names[u]} (@{u})", key=f"msg_recipients_{code}")
                    default_msg = f"Hola, tu actividad ya está lista. Entra a EcoGuardian AI y usa el PIN de sala: {code}"
                    body = st.text_area("Mensaje", value=default_msg, max_chars=1000, key=f"msg_body_{code}")
                    if st.button("Enviar mensaje", type="primary", key=f"send_msg_{code}"):
                        if not chosen_recipients or not body.strip(): st.error("Selecciona al menos un estudiante y escribe el mensaje.")
                        else:
                            cx = db_connect()
                            cx.executemany("INSERT INTO messages(sender,recipient,body,created_at) VALUES(?,?,?,?)", [(st.session_state["auth_user"],u,body.strip(),now_iso()) for u in chosen_recipients])
                            cx.commit(); cx.close(); st.success(f"Mensaje enviado a {len(chosen_recipients)} estudiante(s).")
    st.info("Esta versión usa SQLite local; para que los resultados se compartan entre dispositivos por internet, la aplicación debe estar publicada con almacenamiento persistente.")


# ──────────────────────────────────────────────────────────────────────────────
# 3. ESTADO DE LA SESIÓN
# ──────────────────────────────────────────────────────────────────────────────
def init_state() -> None:
    """Crea las estructuras de datos la primera vez que se abre la app."""
    st.session_state.setdefault("noise_log", [])
    st.session_state.setdefault("waste_log", [])


def load_demo_data() -> None:
    """Carga datos ficticios para que las gráficas se vean bien en la exposición."""
    rng = np.random.default_rng(7)
    now = datetime.now()
    aulas = ["Aula 6A", "Aula 7B", "Biblioteca", "Patio"]
    g_max, y_max = st.session_state.get("cfg_green", 55), st.session_state.get("cfg_yellow", 65)
    st.session_state["noise_log"] = []
    for i in range(28):
        aula = aulas[i % 4]
        base = {"Aula 6A": 60, "Aula 7B": 66, "Biblioteca": 42, "Patio": 74}[aula]
        db = float(np.clip(rng.normal(base, 6), 35, 95))
        st.session_state["noise_log"].append({
            "hora": now - timedelta(minutes=5 * (28 - i)), "aula": aula,
            "db": round(db, 1), "nivel": noise_level(db, g_max, y_max), "fuente": "Demo"})
    st.session_state["waste_log"] = []
    for i in range(18):
        rec = list(BINS)[int(rng.integers(0, len(BINS)))]
        correct = bool(rng.random() < 0.7)
        elegida = rec if correct else rng.choice([c for c in BINS if c != rec])
        st.session_state["waste_log"].append({
            "hora": now - timedelta(minutes=9 * (18 - i)), "recomendada": rec,
            "elegida": str(elegida), "acierto": correct, "confianza": round(float(rng.uniform(.5, .9)), 2)})


def get_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve los registros como DataFrames (con columnas aunque estén vacíos)."""
    n = pd.DataFrame(st.session_state["noise_log"],
                     columns=["hora", "aula", "db", "nivel", "fuente"])
    w = pd.DataFrame(st.session_state["waste_log"],
                     columns=["hora", "recomendada", "elegida", "acierto", "confianza"])
    return n, w


# ──────────────────────────────────────────────────────────────────────────────
# 4. COMPONENTES VISUALES REUTILIZABLES
# ──────────────────────────────────────────────────────────────────────────────
def traffic_light_html(active: str) -> str:
    """Dibuja el semáforo: solo la luz activa se enciende."""
    lamps = ""
    for name in ("Rojo", "Amarillo", "Verde"):
        on = name == active
        c = NOISE_COLORS[name]
        glow = f"box-shadow:0 0 26px {c};" if on else ""
        lamps += f'<div class="lamp" style="background:{c};opacity:{1 if on else .16};{glow}"></div>'
    return f'<div class="semaforo">{lamps}</div>'


def hero(indic: dict) -> None:
    """Cabecera con el nombre de la app y el puntaje ecológico actual."""
    st.markdown(f"""
    <div class="eg-hero">
      <div><h1>EcoGuardian AI</h1>
      <p>Menos ruido en el colegio y cada residuo en su caneca. Mide, aprende y mejora.</p></div>
      <div class="eg-score"><div class="n">{indic['total']:.0f}<span style="font-size:1.2rem">/100</span></div>
      <div class="l">Puntaje ecológico · {indic['rank']}</div></div>
    </div>""", unsafe_allow_html=True)


def bin_card(color: str, origen: str = "guia") -> bool:
    """Dibuja una caneca interactiva con clave única por sección."""
    b = BINS[color]
    # El botón es un control Streamlit real: funciona con ratón y teclado.
    return st.button(
        f"{b['emoji']}\nCaneca {color}\n{b['titulo']}\nPulsa para ver información",
        key=f"bin_{origen}_{color}",
        use_container_width=True,
        help=f"Ver información de la caneca {color.lower()}",
    )


def show_bin_details(color: str) -> None:
    """Muestra la ficha de la caneca seleccionada."""
    b = BINS[color]
    border = "2px solid #9AA5AE" if color == "Blanco" else ("2px solid #8D2025" if color == "Rojo" else "1px solid rgba(255,255,255,.16)")
    st.markdown(f"""
    <section class="eg-bin-detail" style="background:{b['hex']};color:{b['texto']};border:{border}">
      <div class="eg-bin-kicker">{b['emoji']} GUÍA DE SEPARACIÓN</div>
      <div class="eg-bin-title">Caneca {color.lower()}</div>
      <div class="eg-bin-subtitle">{b['titulo']}</div>
      <p>{b['desc']}</p>
      <p><strong>Ejemplos</strong><br>{b['ejemplos']}</p>
      <p><strong>Buena práctica</strong><br>{b['consejo']}</p>
    </section>""", unsafe_allow_html=True)
    if st.button("Cerrar información", key=f"close_bin_{color}"):
        st.session_state["selected_bin"] = None
        st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# 5. PÁGINAS
# ──────────────────────────────────────────────────────────────────────────────
def page_home(noise_df, waste_df, indic) -> None:
    st.subheader("Panel general")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mediciones de ruido", len(noise_df))
    c2.metric("Residuos analizados", len(waste_df))
    c3.metric("Tiempo en verde", f"{indic['pct_green']:.0f}%")
    acc = indic["waste_score"]
    c4.metric("Acierto en residuos", f"{acc:.0f}%" if acc is not None else "—")

    left, right = st.columns([1, 2])
    with left:
        last = noise_df.iloc[-1]["nivel"] if len(noise_df) else "Verde"
        st.markdown(traffic_light_html(last), unsafe_allow_html=True)
        st.caption("Última lectura de EcoSilencio" if len(noise_df) else "Sin lecturas aún")
    with right:
        st.markdown("**¿Cómo se calcula el puntaje?**")
        st.write("Promedia dos indicadores: el tiempo que el colegio permanece en un ambiente "
                 "silencioso (EcoSilencio) y el porcentaje de residuos que los estudiantes "
                 "depositan en la caneca correcta (EcoScan).")
        if not len(noise_df) and not len(waste_df):
            st.info("Empieza midiendo ruido o escaneando un residuo. "
                    "Para una demostración rápida usa «Cargar datos de demostración» en el menú lateral.")
    st.markdown("### Código de colores de canecas")
    st.caption("Guía educativa de separación. La caneca roja representa residuos que requieren manejo especial y debe ajustarse al protocolo del colegio.")
    colors = list(BINS)
    # Las canecas son controles reales: al pulsar una se abre su ficha informativa.
    for start in range(0, len(colors), 2):
        cols = st.columns(2, gap="large")
        for col, color in zip(cols, colors[start:start + 2]):
            with col:
                if bin_card(color, origen="panel_resumen"):
                    st.session_state["selected_bin"] = color
    selected_bin = st.session_state.get("selected_bin")
    if selected_bin in BINS:
        show_bin_details(selected_bin)
    else:
        st.caption("Selecciona una caneca para consultar qué residuos van en ella, ejemplos y recomendaciones.")


def live_noise_monitor(green_max: float, yellow_max: float) -> None:
    """Monitor RMS continuo en el navegador; el semáforo y la gráfica se actualizan en vivo."""
    st.caption("El navegador solicitará permiso al micrófono. La medición es relativa/estimada, no un sonómetro certificado.")
    st.info("Importante: localhost solo funciona en el mismo ordenador que ejecuta EcoGuardian AI. Si accedes desde otro equipo del colegio mediante una IP (por ejemplo, http://192.168.x.x:8501), el navegador bloqueará el micrófono. Para estudiantes en otros equipos, el sitio debe abrirse por HTTPS con un certificado de confianza.")
    component = f"""
    <div style="font-family:Arial,sans-serif;color:#20352b;border:1px solid #dce7dd;border-radius:16px;padding:16px;background:#fbfdfb">
      <div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap">
        <button id="start" style="padding:10px 16px;border:0;border-radius:9px;background:#1e7044;color:white;font-weight:bold;cursor:pointer">Activar micrófono en vivo</button>
        <button id="stop" style="padding:10px 16px;border:1px solid #bbb;border-radius:9px;background:white;color:#20352b;cursor:pointer">Detener</button>
        <button id="finish" style="padding:10px 16px;border:0;border-radius:9px;background:#145c3b;color:white;font-weight:bold;cursor:pointer">Finalizar y escuchar diagnóstico</button>
        <span id="status">Micrófono apagado</span>
      </div>
      <div style="display:flex;align-items:center;gap:18px;margin-top:16px;flex-wrap:wrap">
        <div style="background:#202428;border-radius:24px;padding:10px;display:flex;gap:8px;flex-direction:column">
          <div id="red" style="width:42px;height:42px;border-radius:50%;background:#633"></div>
          <div id="yellow" style="width:42px;height:42px;border-radius:50%;background:#665b27"></div>
          <div id="green" style="width:42px;height:42px;border-radius:50%;background:#27543a"></div>
        </div>
        <div><div id="level" style="font-size:30px;font-weight:700">— dB aprox.</div><div id="label" style="font-size:18px;font-weight:700">Esperando activación</div><div id="advice" style="margin-top:6px">Activa el micrófono para iniciar el análisis continuo.</div></div>
      </div>
      <canvas id="chart" height="120" style="width:100%;height:150px;margin-top:14px;border:1px solid #e1e8e1;border-radius:8px"></canvas>
      <div style="font-size:12px;color:#65736a;margin-top:6px">Gráfica en vivo · nivel relativo estimado · verde ≤ {green_max} · amarillo ≤ {yellow_max} · rojo por encima</div>
    </div>
    <script>
    (() => {{
      const $=id=>document.getElementById(id); let stream=null, ctx=null, analyser=null, raf=null, samples=[];
      const canvas=$('chart'), c=canvas.getContext('2d');
      function draw() {{ const w=canvas.clientWidth*devicePixelRatio,h=canvas.clientHeight*devicePixelRatio; if(canvas.width!==w||canvas.height!==h){{canvas.width=w;canvas.height=h;}} c.clearRect(0,0,w,h); c.strokeStyle='#dfe8df'; c.lineWidth=1; for(let i=1;i<4;i++){{c.beginPath();c.moveTo(0,h*i/4);c.lineTo(w,h*i/4);c.stroke();}} c.strokeStyle='#23844c';c.lineWidth=3;c.beginPath(); samples.forEach((v,i)=>{{let x=i/(Math.max(1, samples.length-1))*w;let y=h-(v-30)/80*h;if(i===0)c.moveTo(x,y);else c.lineTo(x,y);}});c.stroke(); }}
      function tick() {{ if(!analyser)return; const data=new Uint8Array(analyser.fftSize);analyser.getByteTimeDomainData(data);let sum=0;for(const v of data){{const n=(v-128)/128;sum+=n*n;}} const rms=Math.sqrt(sum/data.length); const db=Math.max(30,Math.min(110,20*Math.log10(Math.max(rms,0.00001))+90)); const lvl=db<={green_max}?'Verde':db<={yellow_max}?'Amarillo':'Rojo'; $('level').textContent=Math.round(db)+' dB aprox.'; $('label').textContent=lvl==='Verde'?'🟢 Zona de concentración':lvl==='Amarillo'?'🟡 Zona de cuidado':'🔴 Pausa sonora'; $('advice').textContent=lvl==='Verde'?'Excelente, el ambiente está tranquilo.':lvl==='Amarillo'?'Atención: bajen un poco el volumen.':'¡Atención! El ruido está muy alto.'; $('red').style.background=lvl==='Rojo'?'#e53935':'#633';$('yellow').style.background=lvl==='Amarillo'?'#ffca28':'#665b27';$('green').style.background=lvl==='Verde'?'#35c66b':'#27543a';samples.push(db);if(samples.length>90)samples.shift();draw();raf=requestAnimationFrame(tick); }}
      $('start').onclick=async()=>{{try{{if(!window.isSecureContext)throw new Error('Conexión no segura. En este equipo, abre la app por HTTPS. localhost solo funciona en el ordenador donde corre el servidor.');if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia)throw new Error('Este navegador no ofrece acceso al micrófono. Prueba con Chrome o Edge actualizado y verifica los permisos del sitio.');stream=await navigator.mediaDevices.getUserMedia({{audio:{{echoCancellation:false,noiseSuppression:false,autoGainControl:false}}}});ctx=new (window.AudioContext||window.webkitAudioContext)();await ctx.resume();analyser=ctx.createAnalyser();analyser.fftSize=2048;ctx.createMediaStreamSource(stream).connect(analyser);$('status').textContent='Micrófono activo · análisis continuo';cancelAnimationFrame(raf);tick();}}catch(e){{$('status').textContent='No se pudo activar: '+e.message;}}}};
      function stopMic() {{cancelAnimationFrame(raf);analyser=null;if(stream)stream.getTracks().forEach(t=>t.stop());if(ctx)ctx.close();stream=null;ctx=null;$('status').textContent='Micrófono apagado';}}
      $('stop').onclick=()=>{{stopMic();$('label').textContent='Análisis detenido';}};
      $('finish').onclick=()=>{{
        if(!samples.length){{const msg='Todavía no hay mediciones. Activa el micrófono y mide el ambiente antes de finalizar.';$('status').textContent=msg;if('speechSynthesis'in window){{speechSynthesis.cancel();let u=new SpeechSynthesisUtterance(msg);u.lang='es-CO';speechSynthesis.speak(u);}}return;}}
        const avg=samples.reduce((a,b)=>a+b,0)/samples.length;
        const lvl=avg<={green_max}?'Verde':avg<={yellow_max}?'Amarillo':'Rojo';
        const msg=lvl==='Verde'?'Diagnóstico final: el ambiente está tranquilo y es favorable para la concentración. ¡Sigan así.':lvl==='Amarillo'?'Diagnóstico final: el ambiente presenta ruido moderado. Bajen la voz y eviten hablar todos al mismo tiempo.':'Diagnóstico final: el ambiente está demasiado ruidoso. Hagan una pausa sonora, hablen más bajo y vuelvan a medir.';
        $('status').textContent='Medición finalizada · promedio estimado '+Math.round(avg)+' decibelios.';$('advice').textContent=msg;$('label').textContent='Resultado final: '+lvl;stopMic();
        if('speechSynthesis'in window){{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(msg);u.lang='es-CO';u.rate=0.94;u.pitch=1;u.volume=1;speechSynthesis.speak(u);}}
      }};
      window.addEventListener('beforeunload',()=>{{if(stream)stream.getTracks().forEach(t=>t.stop());}});
    }})();
    </script>"""
    st.components.v1.html(component, height=430, scrolling=False)


def page_noise() -> None:
    st.subheader("🔊 EcoSilencio · monitor de ruido")
    g_max, y_max = st.session_state.get("cfg_green", 55), st.session_state.get("cfg_yellow", 65)
    aula = st.text_input("Aula o espacio", value="Aula 6A")
    tab_live, tab_mic, tab_manual = st.tabs(["En vivo", "Muestra de audio", "Ingreso manual / sonómetro"])
    with tab_live:
        live_noise_monitor(g_max, y_max)

    db_value, source = None, ""
    with tab_mic:
        st.caption("Graba 5-10 segundos del ambiente. El audio se procesa en memoria y no se guarda. "
                   "El nivel calculado es una estimación dependiente del micrófono; calibra contra un sonómetro "
                   "si necesitas aproximarte a dB SPL. No es una medición certificada.")
        if hasattr(st, "audio_input"):
            audio = st.audio_input("Grabar ambiente")
            if audio is not None:
                try:
                    db_value = estimate_db(audio.getvalue(), st.session_state.get("cfg_calib", 90))
                    source = "Micrófono"
                except Exception as exc:  # audio corrupto o formato inesperado
                    st.error(f"No se pudo analizar el audio: {exc}")
        else:
            st.warning("Actualiza Streamlit (>= 1.40) para usar el micrófono, o usa el ingreso manual.")
    with tab_manual:
        manual = st.slider("Nivel de ruido (dB)", 30, 110, 55)
        if st.checkbox("Usar este valor"):
            db_value, source = float(manual), "Manual"

    if db_value is not None:
        level = noise_level(db_value, g_max, y_max)
        title, advice = NOISE_INFO[level]
        a, b = st.columns([1, 2])
        with a:
            st.markdown(traffic_light_html(level), unsafe_allow_html=True)
        with b:
            st.markdown(f'<div class="bigdb" style="color:{NOISE_COLORS[level]}">{db_value:.0f} dB</div>',
                        unsafe_allow_html=True)
            st.markdown(f"**{level}: {title}**")
            st.write(advice)
            if st.button("Guardar medición"):
                st.session_state["noise_log"].append({
                    "hora": datetime.now(), "aula": aula, "db": round(db_value, 1),
                    "nivel": level, "fuente": source})
                st.success("Medición guardada. Revisa la pestaña Estadísticas.")
    st.markdown("---")
    st.caption(f"Umbrales activos: Verde ≤ {g_max} dB · Amarillo ≤ {y_max} dB · Rojo > {y_max} dB. "
               "Ajústalos en el menú lateral según la normativa vigente de tu institución.")


def page_scan() -> None:
    st.subheader("♻️ EcoScan · clasificador de residuos")
    st.caption("Abre las opciones para elegir cómo añadir la foto del residuo.")
    image_file = None
    with st.expander("📷 Desplegar opciones de foto", expanded=True):
        photo_mode = st.radio("¿Cómo quieres añadir la imagen?", ["Subir una foto", "Tomar una foto con la cámara"], horizontal=True, key="ecoscan_photo_mode")
        if photo_mode == "Subir una foto":
            image_file = st.file_uploader("Selecciona una foto del residuo", type=["jpg", "jpeg", "png", "webp"], key="ecoscan_upload")
        else:
            image_file = st.camera_input("Enfoca el residuo y toma la foto", key="ecoscan_camera")
    with st.expander("♻️ Guía de canecas", expanded=False):
        for color in BINS:
            bin_card(color, origen="guia_clasificador")
            st.write("")

    if image_file is None:
        st.info("Sube o toma una foto de un residuo para clasificarlo.")
        return

    try:
        img = Image.open(image_file)
        img.load()
    except Exception:
        st.error("No se pudo leer la imagen. Prueba con un archivo JPG o PNG.")
        return

    hint = st.text_input("¿Qué objeto es? (opcional, mejora la precisión)", placeholder="botella, cáscara de banano…")
    result = classify_image(img, hint)
    pred = result["pred"]

    col_img, col_res = st.columns(2)
    with col_img:
        st.image(img, caption="Imagen cargada")
    with col_res:
        st.markdown("**Resultado de EcoScan**")
        bin_card(pred, origen="resultado_clasificador")
        st.caption(result["motivo"])
        # Son puntuaciones relativas de heurísticas visuales, no probabilidades ni confianza de IA.
        probs = pd.DataFrame({"Caneca": list(result["probs"]),
                              "Indicador relativo": [round(p * 100, 1) for p in result["probs"].values()]})
        chart = alt.Chart(probs).mark_bar().encode(
            x=alt.X("Indicador relativo:Q", scale=alt.Scale(domain=[0, 100]), title="Indicador relativo (no confianza)"),
            y=alt.Y("Caneca:N", sort=list(BINS), title=None),
            color=alt.Color("Caneca:N", legend=None,
                            scale=alt.Scale(domain=list(BINS), range=[b["chart"] for b in BINS.values()])),
        ).properties(height=130, width="container")
        st.altair_chart(chart)

    st.markdown("#### Pon a prueba tu criterio")
    st.write("Antes de mirar la respuesta, ¿en qué caneca lo habrías depositado?")
    choice = st.radio("Mi elección", list(BINS), horizontal=True, label_visibility="collapsed")
    if st.button("Registrar en estadísticas"):
        ok = choice == pred
        st.session_state["waste_log"].append({
            "hora": datetime.now(), "recomendada": pred, "elegida": choice,
            "acierto": ok, "confianza": round(result["probs"][pred], 2)})
        (st.success if ok else st.warning)(
            "¡Correcto! Aportas al puntaje ecológico." if ok else
            f"La caneca recomendada era la {pred.lower()}. Revisa la guía y vuelve a intentar.")
    st.warning("EcoScan es experimental: usa reglas de color y palabras clave, no un modelo de IA entrenado. "
               "Los indicadores son relativos, no porcentajes de confianza estadística. Una foto no permite "
               "identificar con seguridad residuos peligrosos; ante la duda, no lo manipules y consulta al docente "
               "o el protocolo local.")


def page_stats(noise_df, waste_df, indic) -> None:
    st.subheader("📊 Estadísticas ambientales")
    if not len(noise_df) and not len(waste_df):
        st.info("Aún no hay datos. Registra mediciones o carga los datos de demostración.")
        return

    k1, k2, k3 = st.columns(3)
    k1.metric("Puntaje ecológico", f"{indic['total']:.0f}/100", indic["rank"], delta_color="off")
    k2.metric("Índice de silencio", f"{indic['noise_score']:.0f}" if indic["noise_score"] is not None else "—")
    k3.metric("Índice de residuos", f"{indic['waste_score']:.0f}" if indic["waste_score"] is not None else "—")

    if len(noise_df):
        st.markdown("### Ruido")
        g_max, y_max = st.session_state.get("cfg_green", 55), st.session_state.get("cfg_yellow", 65)
        line = alt.Chart(noise_df).mark_line(point=True, color="#14352A").encode(
            x=alt.X("hora:T", title="Hora"),
            y=alt.Y("db:Q", title="Nivel (dB)", scale=alt.Scale(domain=[30, 100])),
            tooltip=["aula", "db", "nivel"])
        rules = alt.Chart(pd.DataFrame({"y": [g_max, y_max], "c": ["Verde", "Amarillo"]})).mark_rule(
            strokeDash=[5, 4]).encode(y="y:Q", color=alt.Color(
                "c:N", legend=None, scale=alt.Scale(domain=["Verde", "Amarillo"],
                                                    range=[NOISE_COLORS["Verde"], NOISE_COLORS["Amarillo"]])))
        st.altair_chart((line + rules).properties(height=280, width="container"))

        c1, c2 = st.columns(2)
        counts = noise_df["nivel"].value_counts().reindex(list(NOISE_COLORS), fill_value=0).reset_index()
        counts.columns = ["nivel", "n"]
        with c1:
            st.markdown("**Mediciones por semáforo**")
            st.altair_chart(alt.Chart(counts).mark_bar().encode(
                x=alt.X("nivel:N", sort=list(NOISE_COLORS), title=None), y=alt.Y("n:Q", title="Cantidad"),
                color=alt.Color("nivel:N", legend=None, scale=alt.Scale(
                    domain=list(NOISE_COLORS), range=list(NOISE_COLORS.values())))
            ).properties(height=240, width="container"))
        with c2:
            st.markdown("**Promedio de dB por espacio**")
            by_room = noise_df.groupby("aula", as_index=False)["db"].mean().round(1)
            st.altair_chart(alt.Chart(by_room).mark_bar(color="#4C8C4A").encode(
                x=alt.X("db:Q", title="dB promedio"), y=alt.Y("aula:N", sort="-x", title=None)
            ).properties(height=240, width="container"))

    if len(waste_df):
        st.markdown("### Residuos")
        c1, c2 = st.columns(2)
        dist = waste_df["recomendada"].value_counts().reindex(list(BINS), fill_value=0).reset_index()
        dist.columns = ["caneca", "n"]
        with c1:
            st.markdown("**Residuos por caneca recomendada**")
            st.altair_chart(alt.Chart(dist).mark_arc(innerRadius=55).encode(
                theta="n:Q", color=alt.Color("caneca:N", scale=alt.Scale(
                    domain=list(BINS), range=[b["chart"] for b in BINS.values()]))
            ).properties(height=260))
        with c2:
            st.markdown("**Errores frecuentes** (recomendada vs elegida)")
            errors = waste_df[~waste_df["acierto"]]
            if len(errors):
                st.dataframe(pd.crosstab(errors["recomendada"], errors["elegida"]))
            else:
                st.success("Sin errores registrados. ¡Excelente clasificación!")

    with st.expander("Datos y exportación"):
        if len(noise_df):
            st.download_button("Descargar ruido (CSV)", noise_df.to_csv(index=False).encode("utf-8"),
                               "ecosilencio.csv", "text/csv")
        if len(waste_df):
            st.download_button("Descargar residuos (CSV)", waste_df.to_csv(index=False).encode("utf-8"),
                               "ecoscan.csv", "text/csv")


def admin_project_audio() -> None:
    """Presentación oral del proyecto, exclusiva del panel de administración."""
    st.markdown("## 🎙️ Presentación del proyecto EcoGuardian AI")
    st.write("Espacio para exponer el propósito del proyecto. El audio usa la voz en español disponible en el navegador y no se muestra a estudiantes.")
    script = ("EcoGuardian AI es una propuesta educativa creada para fortalecer la conciencia ambiental dentro de las instituciones educativas. "
              "Integra herramientas para promover el cuidado del entorno, la clasificación responsable de los residuos y la sensibilización frente al ruido en los espacios escolares. "
              "También incorpora EcoAventura, una biblioteca de juegos interactivos que permite aprender mediante retos, sonidos y actividades. "
              "El administrador controla los permisos, los docentes pueden asignar actividades y los estudiantes participan en los juegos autorizados. "
              "El objetivo es convertir el aprendizaje ambiental en una experiencia participativa y motivadora, fomentando hábitos responsables y el compromiso con el planeta. "
              "EcoGuardian AI es una herramienta de apoyo educativo; sus mediciones de ruido son estimaciones y no mediciones certificadas.")
    st.markdown("### Texto de exposición")
    st.info(script)
    escaped=json.dumps(script, ensure_ascii=False)
    html_doc = """<div style='font-family:Arial;padding:8px'><button id='s' style='background:#16794b;color:white;border:0;border-radius:12px;padding:12px 18px;cursor:pointer'>▶ Escuchar presentación</button> <button id='x' style='border:0;border-radius:12px;padding:12px 18px;cursor:pointer'>■ Detener</button><p id='m'>Voz en español del navegador.</p></div><script>const t=__TEXT__;document.getElementById('s').onclick=()=>{if(!('speechSynthesis'in window)){document.getElementById('m').textContent='Síntesis de voz no disponible';return;}speechSynthesis.cancel();let u=new SpeechSynthesisUtterance(t);u.lang='es-CO';u.rate=.92;u.onend=()=>document.getElementById('m').textContent='Presentación finalizada';speechSynthesis.speak(u);document.getElementById('m').textContent='Reproduciendo…'};document.getElementById('x').onclick=()=>{speechSynthesis.cancel();document.getElementById('m').textContent='Audio detenido'};</script>""".replace("__TEXT__", escaped)
    st.components.v1.html(html_doc, height=100)


# ──────────────────────────────────────────────────────────────────────────────
# 6. PUNTO DE ENTRADA
# ──────────────────────────────────────────────────────────────────────────────
def teacher_messages_panel(username: str) -> None:
    st.markdown("## 💬 Mensajes privados")
    con = db_connect()
    students = con.execute("SELECT username,display_name FROM accounts WHERE role='student' AND approved=1 ORDER BY display_name").fetchall()
    with st.form("teacher_private_message"):
        recipient = st.selectbox("Enviar a estudiante", options=[r["username"] for r in students], format_func=lambda u: next((r["display_name"] for r in students if r["username"]==u),u)) if students else None
        body = st.text_area("Mensaje", max_chars=1000)
        send = st.form_submit_button("Enviar")
    if send:
        if not recipient or not body.strip(): st.error("Selecciona un estudiante y escribe un mensaje.")
        else:
            send_message(username, recipient, body.strip())
            con.execute("INSERT INTO notifications(kind,title,body,username,created_at) VALUES(?,?,?,?,?)", ("mensaje", "Nuevo mensaje docente", f"Tienes un mensaje de @{username}.", recipient, now_iso()))
            con.commit(); st.success("Mensaje enviado.")
    rows = con.execute("SELECT recipient,body,created_at FROM messages WHERE sender=? ORDER BY id DESC LIMIT 30", (username,)).fetchall()
    if rows:
        st.markdown("### Mensajes enviados")
        for row in rows: st.caption(f"Para @{row['recipient']} · {row['created_at']}"); st.write(row['body'])
    con.close()


PUFF_ITEMS = [
    {"objeto":"Cáscara de banano","emoji":"🍌","correcta":"Verde","nota":"Los residuos orgánicos aprovechables se separan en la caneca verde según la guía educativa."},
    {"objeto":"Botella plástica limpia y seca","emoji":"🧴","correcta":"Blanco","nota":"Los residuos aprovechables limpios y secos van en la caneca blanca."},
    {"objeto":"Lata de bebida vacía y limpia","emoji":"🥫","correcta":"Blanco","nota":"El metal limpio es aprovechable y se deposita en la caneca blanca."},
    {"objeto":"Servilleta usada","emoji":"🧻","correcta":"Negro","nota":"La servilleta usada es un residuo no aprovechable: caneca negra."},
    {"objeto":"Restos de frutas","emoji":"🍎","correcta":"Verde","nota":"Los restos orgánicos se separan en la caneca verde según el sistema local."},
    {"objeto":"Hoja de papel limpia","emoji":"📄","correcta":"Blanco","nota":"El papel limpio y seco es aprovechable y va en la caneca blanca."},
    {"objeto":"Pañuelo desechable usado","emoji":"🤧","correcta":"Negro","nota":"Un pañuelo usado va con los residuos no aprovechables."},
    {"objeto":"Pila usada (solo pregunta virtual)","emoji":"🔋","correcta":"Roja","nota":"No va en canecas ordinarias: llévala a un punto posconsumo autorizado; la roja aquí es una alerta educativa."},
    {"objeto":"Caja de cartón limpia y seca","emoji":"📦","correcta":"Blanco","nota":"El cartón limpio y seco es aprovechable."},
    {"objeto":"Residuo contaminado con químico (simulación)","emoji":"☣️","correcta":"Roja","nota":"No manipules residuos peligrosos reales; sigue el protocolo local y la gestión especializada."},
]

def page_ecopuff(username: str, role: str) -> None:
    st.markdown("## 💥 EcoPuff · Batalla de canecas")
    st.write("Crea una sala, comparte el código y compite por rondas. La respuesta queda registrada en la base de datos; la primera respuesta correcta recibida por el servidor gana el bono de velocidad.")
    con = db_connect()
    if role in ("admin", "teacher"):
        with st.expander("➕ Crear campeonato / sala", expanded=True):
            with st.form("puff_create_room"):
                title = st.text_input("Nombre del reto", value="EcoPuff: batalla ecológica", max_chars=80)
                topic = st.selectbox("Categoría", ["Separación de residuos", "Contaminación auditiva", "Contaminación visual", "Medio ambiente mixto"])
                difficulty = st.selectbox("Dificultad", ["Fácil", "Intermedia", "Avanzada", "Experta", "Mixta"])
                rounds = st.number_input("Número de rondas", min_value=1, max_value=len(PUFF_ITEMS), value=5)
                seconds = st.slider("Segundos por ronda", 5, 60, 15)
                create = st.form_submit_button("Crear sala y código", type="primary")
            if create:
                code = ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=6))
                deck = random.sample(PUFF_ITEMS, k=min(int(rounds), len(PUFF_ITEMS)))
                con.execute("INSERT INTO puff_rooms(code,title,host,topic,difficulty,format,rounds,seconds,status,round_no,question_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (code,title.strip() or "EcoPuff",username,topic,difficulty,"canecas",len(deck),int(seconds),"lobby",0,json.dumps(deck,ensure_ascii=False),now_iso()))
                con.commit(); st.success(f"Sala creada. Código para compartir: {code}"); st.session_state["puff_host_code"] = code
        own = con.execute("SELECT * FROM puff_rooms WHERE host=? ORDER BY created_at DESC LIMIT 20", (username,)).fetchall()
    else:
        own = []
    with st.expander("🚪 Entrar a una sala", expanded=role == "student"):
        with st.form("puff_join"):
            join_code = st.text_input("Código EcoPuff", max_chars=6).strip().upper()
            join = st.form_submit_button("Entrar / unirme")
        if join:
            room = con.execute("SELECT * FROM puff_rooms WHERE code=?", (join_code,)).fetchone()
            account = con.execute("SELECT display_name FROM accounts WHERE username=?", (username,)).fetchone()
            if not room:
                st.error("No se encontró esa sala. Comprueba el código.")
            else:
                con.execute("INSERT OR IGNORE INTO puff_players(code,username,display_name,joined_at) VALUES(?,?,?,?)", (join_code,username,account["display_name"] if account else username,now_iso()))
                con.commit(); st.session_state["puff_active_code"] = join_code; st.rerun()
    active_code = st.session_state.get("puff_active_code") or st.session_state.get("puff_host_code")
    if active_code:
        room = con.execute("SELECT * FROM puff_rooms WHERE code=?", (active_code,)).fetchone()
        if room:
            st.divider(); st.markdown(f"### {html.escape(room['title'])} · Código `{room['code']}`")
            players = con.execute("SELECT username,display_name,points,correct FROM puff_players WHERE code=? ORDER BY points DESC,correct DESC,joined_at", (active_code,)).fetchall()
            if username != room["host"]:
                acct = con.execute("SELECT display_name FROM accounts WHERE username=?", (username,)).fetchone()
                con.execute("INSERT OR IGNORE INTO puff_players(code,username,display_name,joined_at) VALUES(?,?,?,?)", (active_code,username,acct["display_name"] if acct else username,now_iso())); con.commit()
            st.caption(f"Categoría: {room['topic']} · Dificultad: {room['difficulty']} · {room['rounds']} rondas · {room['seconds']} s por ronda")
            deck = json.loads(room["question_json"])
            if room["status"] == "lobby":
                st.info("Sala en espera. Todos los participantes deben entrar antes de que el anfitrión inicie.")
                if username == room["host"] and st.button("▶️ Iniciar campeonato", type="primary", key="puff_start"):
                    con.execute("UPDATE puff_rooms SET status='live',round_no=1,round_started=? WHERE code=? AND status='lobby'", (time.time(),active_code)); con.commit(); st.rerun()
            elif room["status"] == "live":
                idx = max(0, min(int(room["round_no"])-1, len(deck)-1)); item = deck[idx]
                st.progress((idx+1)/len(deck), text=f"Ronda {idx+1} de {len(deck)}")
                st.markdown(f"# {item['emoji']} ¿En qué caneca va: {item['objeto']}?")
                if username == room["host"]:
                    eco_voice.narrate(f"Ronda {idx+1}. ¿En qué caneca va: {item['objeto']}? Verde, blanca, negra o roja.", f"puff_q_{active_code}_{idx}")
                prior = con.execute("SELECT username,is_correct,points FROM puff_answers WHERE code=? AND round_no=? ORDER BY received_at,id", (active_code,room["round_no"])).fetchall()
                me = next((a for a in prior if a["username"] == username), None)
                if me:
                    st.success("Tu respuesta ya quedó registrada. Espera a que cierre la ronda.")
                else:
                    cols = st.columns(4)
                    for col, bin_name, emoji in zip(cols,["Verde","Blanco","Negro","Roja"],["🟢","⚪","⚫","🔴"]):
                        with col:
                            if st.button(f"{emoji}\n{bin_name}", key=f"puff_{active_code}_{room['round_no']}_{username}_{bin_name}", use_container_width=True):
                                stamp = time.time(); correct = bin_name == item["correcta"]
                                # El servidor registra la respuesta; solo una por jugador/ronda.
                                prior_correct = con.execute("SELECT id FROM puff_answers WHERE code=? AND round_no=? AND is_correct=1 ORDER BY received_at,id LIMIT 1", (active_code,room["round_no"])).fetchone()
                                pts = (100 if not prior_correct else 50) if correct else 0
                                try:
                                    con.execute("INSERT INTO puff_answers(code,round_no,username,answer,is_correct,received_at,points) VALUES(?,?,?,?,?,?,?)", (active_code,room["round_no"],username,bin_name,int(correct),stamp,pts))
                                    con.execute("UPDATE puff_players SET points=points+?,correct=correct+? WHERE code=? AND username=?", (pts,int(correct),active_code,username)); con.commit()
                                except sqlite3.IntegrityError:
                                    pass
                                st.rerun()
                if username == room["host"]:
                    elapsed = time.time() - float(room["round_started"] or time.time())
                    if elapsed >= int(room["seconds"]) or len(prior) >= len(players):
                        st.warning(f"Respuesta: {item['correcta']}. {item['nota']}")
                        eco_voice.narrate(f"Tiempo. La respuesta es la caneca {item['correcta']}. {item['nota']}", f"puff_a_{active_code}_{idx}")
                        if idx+1 < len(deck):
                            if st.button("Siguiente ronda", key="puff_next"):
                                con.execute("UPDATE puff_rooms SET round_no=round_no+1,round_started=? WHERE code=?", (time.time(),active_code)); con.commit(); st.rerun()
                        elif st.button("🏁 Finalizar campeonato", key="puff_finish"):
                            con.execute("UPDATE puff_rooms SET status='finished' WHERE code=?", (active_code,)); con.commit(); st.rerun()
                    else:
                        st.caption(f"Ronda abierta · {max(0,int(room['seconds']-elapsed))} s aprox. · actualiza la página para ver respuestas de otros jugadores.")
                        if st.button("🔄 Actualizar estado", key="puff_refresh"): st.rerun()
                else:
                    st.caption("El anfitrión controla el avance de rondas. Actualiza el estado para ver los cambios.")
                    if st.button("🔄 Actualizar", key="puff_refresh_player"): st.rerun()
            else:
                st.success("🏆 Campeonato finalizado")
                st.dataframe(pd.DataFrame([{"Posición":i+1,"Jugador":p["display_name"],"Puntos":p["points"],"Aciertos":p["correct"]} for i,p in enumerate(players)]), use_container_width=True, hide_index=True)
                if players:
                    st.balloons(); st.markdown(f"### 🥇 Ganador/a: {players[0]['display_name']}")
                    eco_voice.narrate(f"¡Campeonato finalizado! La persona ganadora es {players[0]['display_name']} con {players[0]['points']} puntos. ¡Felicitaciones a todos los guardianes!", f"puff_end_{active_code}")
            # chat de sala persistente
            st.markdown("#### 💬 Chat de la sala")
            with st.form("puff_chat_form"):
                body = st.text_input("Mensaje para participantes de esta sala", max_chars=500)
                send = st.form_submit_button("Enviar mensaje")
            if send and body.strip():
                con.execute("INSERT INTO class_messages(code,sender,body,created_at) VALUES(?,?,?,?)", (active_code,username,body.strip(),now_iso())); con.commit()
            chat = con.execute("SELECT sender,body,created_at FROM class_messages WHERE code=? ORDER BY id DESC LIMIT 20", (active_code,)).fetchall()
            for msg in reversed(chat): st.caption(f"{msg['created_at']} · @{msg['sender']}"); st.write(msg['body'])
    con.close()



# ── Juego educativo: EcoVerdadero o Falso ────────────────────────────────────
TRUE_FALSE_QUESTIONS = [
    ("Separar los residuos facilita su aprovechamiento y reciclaje.", True, "Separarlos correctamente ayuda a recuperar materiales."),
    ("Las pilas usadas deben tirarse siempre en la caneca común.", False, "Las pilas requieren puntos de recolección especiales."),
    ("Cerrar la llave mientras te cepillas los dientes ahorra agua.", True, "Pequeñas acciones reducen el consumo de agua."),
    ("Quemar basura al aire libre no contamina si hay viento.", False, "La quema libera humo y sustancias contaminantes."),
    ("Reutilizar un objeto puede reducir la cantidad de residuos.", True, "Reutilizar alarga la vida útil de los productos."),
    ("Dejar luces encendidas en espacios vacíos ahorra energía.", False, "Apagar luces innecesarias reduce el consumo eléctrico."),
    ("Los residuos orgánicos pueden aprovecharse para hacer compost.", True, "El compostaje transforma residuos orgánicos en abono."),
    ("El aceite de cocina usado debe verterse por el desagüe.", False, "Debe recogerse y entregarse en un punto adecuado."),
    ("Cuidar los árboles contribuye a proteger la biodiversidad.", True, "Los árboles ofrecen hábitat y ayudan a mantener los ecosistemas."),
    ("Un residuo limpio y seco suele ser más fácil de aprovechar.", True, "La separación y las condiciones del material importan."),
    ("El ruido excesivo puede afectar la concentración y la salud auditiva.", True, "Reducir el ruido protege el bienestar de la comunidad."),
    ("Reciclar significa que ya no es necesario reducir ni reutilizar.", False, "Reducir y reutilizar siguen siendo acciones prioritarias."),
]

def page_true_false():
    st.markdown("## 🌎 EcoVerdadero o Falso")
    st.write("Lee cada afirmación ambiental y decide si es verdadera o falsa. Cada acierto vale 10 puntos.")
    if st.button("🔄 Empezar / reiniciar partida", key="tf_restart"):
        st.session_state["tf_order"] = random.sample(range(len(TRUE_FALSE_QUESTIONS)), len(TRUE_FALSE_QUESTIONS))
        st.session_state["tf_pos"] = 0
        st.session_state["tf_score"] = 0
        st.session_state["tf_answered"] = False
        st.session_state["tf_feedback"] = None
    if "tf_order" not in st.session_state:
        st.session_state["tf_order"] = random.sample(range(len(TRUE_FALSE_QUESTIONS)), len(TRUE_FALSE_QUESTIONS))
        st.session_state["tf_pos"] = 0; st.session_state["tf_score"] = 0
        st.session_state["tf_answered"] = False; st.session_state["tf_feedback"] = None
    pos = st.session_state["tf_pos"]
    order = st.session_state["tf_order"]
    st.progress(min(pos / len(order), 1.0))
    st.caption(f"Afirmación {min(pos+1,len(order))} de {len(order)} · Puntaje: {st.session_state['tf_score']} puntos")
    gid = hash(tuple(order))
    eco_voice.toggle_ui("tf_narr")
    if pos >= len(order):
        st.success(f"🏆 ¡Partida terminada! Obtuviste {st.session_state['tf_score']} de {len(order)*10} puntos.")
        st.info("¡Sigue aprendiendo y cuidando el planeta!")
        if eco_voice.narrate(eco_voice.final_line(st.session_state['tf_score'] // 10, len(order), st.session_state['tf_score']), f"tf_final_{gid}"):
            st.balloons()
        return
    statement, correct, explanation = TRUE_FALSE_QUESTIONS[order[pos]]
    st.markdown(f"### {statement}")
    if not st.session_state["tf_answered"]:
        eco_voice.narrate(eco_voice.question_line(statement, "tf"), f"tf_q_{gid}_{pos}")
    if not st.session_state["tf_answered"]:
        c1,c2=st.columns(2)
        if c1.button("✅ Verdadero", use_container_width=True, key=f"tf_true_{pos}"):
            _tf_submit(True, correct, explanation)
        if c2.button("❌ Falso", use_container_width=True, key=f"tf_false_{pos}"):
            _tf_submit(False, correct, explanation)
    else:
        st.markdown(st.session_state["tf_feedback"])
        fb = st.session_state["tf_feedback"] or ""
        eco_voice.narrate(("¡Correcto! " if fb.startswith("✅") else "¡Uy, no exactamente! ") + explanation, f"tf_a_{gid}_{pos}")
        if st.button("Siguiente afirmación ➜", type="primary", key=f"tf_next_{pos}"):
            st.session_state["tf_pos"] += 1; st.session_state["tf_answered"] = False; st.session_state["tf_feedback"] = None; st.rerun()

def _tf_submit(answer, correct, explanation):
    if answer == correct:
        st.session_state["tf_score"] += 10
        st.session_state["tf_feedback"] = f"✅ **¡Correcto! +10 puntos.**\n\n{explanation}"
    else:
        st.session_state["tf_feedback"] = f"❌ **No exactamente.**\n\n{explanation}"
    st.session_state["tf_answered"] = True
    st.rerun()


def _ctx(username: str, role: str, display: str = ""):
    """Contexto que se entrega a las páginas nuevas (evita que importen app.py)."""
    from types import SimpleNamespace
    return SimpleNamespace(
        username=username, role=role, display=display or username, logout=logout,
        legacy_games=ECO_GAMES, legacy_allowed=_legacy_allowed(username, role),
        legacy_play=lambda game: _eco_play(game, username, role),
        guard_remaining=guard_remaining, guard_fail=guard_fail, guard_clear=guard_clear, lock_message=_lock_message)


def _settings_page() -> None:
    st.markdown("## ⚙️ Configuración")
    def _sync(src: str, dst: str):
        st.session_state[dst] = st.session_state[src]
    st.slider("Verde hasta (dB)", 40, 70, st.session_state.get("cfg_green", 55), key="w_green", on_change=_sync, args=("w_green", "cfg_green"))
    st.slider("Amarillo hasta (dB)", 50, 90, st.session_state.get("cfg_yellow", 65), key="w_yellow", on_change=_sync, args=("w_yellow", "cfg_yellow"))
    st.slider("Calibración del micrófono (dB)", 60, 120, st.session_state.get("cfg_calib", 90), key="w_calib",
              help="Súmale este valor al nivel digital. Ajústalo comparando con un sonómetro.", on_change=_sync, args=("w_calib", "cfg_calib"))
    a, b = st.columns(2)
    if a.button("Cargar datos de demostración"):
        load_demo_data(); st.success("Datos de demostración cargados.")
    if b.button("Borrar todos los datos de sesión"):
        st.session_state["noise_log"], st.session_state["waste_log"] = [], []; st.success("Datos borrados.")


def _admin_dashboard() -> None:
    noise_df, waste_df = get_frames()
    indic = compute_indicators(noise_df, waste_df)
    hero(indic)
    sections = ["Inicio", "EcoSilencio", "EcoScan", "Estadísticas", "Sala de clase", "EcoReto", "EcoVerdadero o Falso", "EcoPuff"]
    page = st.radio("Sección", sections, horizontal=True, label_visibility="collapsed", key="adash_section")
    if page == "Inicio":
        page_home(noise_df, waste_df, indic)
    elif page == "EcoSilencio":
        page_noise()
    elif page == "EcoScan":
        page_scan()
    elif page == "Estadísticas":
        page_stats(noise_df, waste_df, indic)
    elif page == "Sala de clase":
        page_classroom()
    elif page == "EcoReto":
        page_practice()
    elif page == "EcoVerdadero o Falso":
        page_true_false()
    else:
        page_ecopuff(st.session_state.get("auth_user", "admin"), "admin")


def _route(ctx) -> None:
    page = st.session_state.get("page", "library")
    role, user = ctx.role, ctx.username
    common = {"library": eco_pages.library_page, "arena": eco_pages.arena_page, "about": eco_pages.about_page}
    if page in common:
        common[page](ctx)
    elif page == "bank" and role in ("teacher", "admin"):
        eco_pages.bank_page(ctx)
    elif role == "student" and page == "home":
        student_portal()
    elif role == "teacher":
        if page == "tgames":
            eco_pages.toggles_panel(ctx)
        elif page == "tassign":
            eco_teacher_panel(user)
        elif page == "tmsgs":
            teacher_messages_panel(user)
        else:
            st.markdown("## 🏫 Mis clases")
            page_classroom()
    elif role == "admin":
        if page == "agames":
            eco_pages.toggles_panel(ctx, master=True)
        elif page == "aaccounts":
            admin_accounts_panel()
        elif page == "aperms":
            eco_admin_panel()
        elif page == "anotif":
            page_notifications()
        elif page == "asettings":
            _settings_page()
        elif page == "apres":
            admin_project_audio()
        else:
            _admin_dashboard()
    else:
        common["library"](ctx)


def main() -> None:
    init_state()
    restore_login()
    st.session_state.setdefault("sound_on", True)
    st.session_state.setdefault("page", "library")
    st.markdown(eco_theme.GLOBAL_CSS, unsafe_allow_html=True)
    if not st.session_state.get("auth_user"):
        eco_pages.ambient(force_off=True)      # al cerrar sesión la música ambiental se detiene
        auth_portal()
        return
    role, username = st.session_state.get("auth_role", "student"), st.session_state.get("auth_user", "")
    con = db_connect(); acc = con.execute("SELECT display_name FROM accounts WHERE username=?", (username,)).fetchone(); con.close()
    ctx = _ctx(username, role, acc["display_name"] if acc else username)
    eco_pages.shell(ctx)
    eco_pages.ambient()
    _route(ctx)


if __name__ == "__main__":
    main()
