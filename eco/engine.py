# -*- coding: utf-8 -*-
"""Reglas puras del juego: categorías, niveles, anti-copia, puntuación y desempates."""
from __future__ import annotations

import hashlib
import random
import re
import time

CATEGORIES = ["Restauración", "Energía", "Océanos", "Clima"]
CAT_ICON = {"Restauración": "🌳", "Energía": "⚡", "Océanos": "🌊", "Clima": "🌡️"}
CAT_BLURB = {
    "Restauración": "Bosques, páramos, humedales y manglares que vuelven a la vida.",
    "Energía": "Del sol, el viento y el agua: cómo movemos el mundo sin dañarlo.",
    "Océanos": "Corales, mareas y criaturas del azul profundo que respiramos y comemos.",
    "Clima": "Qué calienta el planeta, qué lo enfría y qué podemos hacer nosotros.",
}
# Pares de color (inicio, fin) para las portadas de cada categoría.
CAT_COLORS = {
    "Restauración": ("#2f6b3b", "#8bbf5a"),
    "Energía": ("#a8641a", "#e8b04b"),
    "Océanos": ("#0f5d73", "#4fb3bf"),
    "Clima": ("#6b3f2a", "#c9855a"),
}
LEVELS = ["Fácil", "Intermedio", "Avanzado", "Experto"]
LEVEL_ICON = {"Fácil": "🌱", "Intermedio": "🌿", "Avanzado": "🌳", "Experto": "🏔️"}
LEVEL_POINTS = {"Fácil": 100, "Intermedio": 150, "Avanzado": 200, "Experto": 300}
QTYPES = {
    "mcq": "Opción múltiple",
    "tf": "Verdadero / Falso",
    "match": "Emparejamiento",
    "image": "Imágenes enfrentadas",
}
REFLEX_BONUS = 50          # bono por ser el más rápido en acertar
MAX_REPLAYS = 3            # repeticiones máximas de una ronda empatada
DEFAULT_TIE_MS = 0         # empate exacto = mismo milisegundo en el servidor


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def seeded_rng(*parts) -> random.Random:
    """RNG determinista a partir de varias piezas (usuario, sala, pregunta...)."""
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def normalize_team(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())[:30]
    return text.title() if text else ""


# ── Presentación anti-copia ───────────────────────────────────────────────────
def present(q: dict, *seed_parts) -> dict:
    """Vista de una pregunta para UN usuario.

    El orden de las opciones depende de (pregunta, *seed_parts): dos estudiantes de la misma
    sala ven el mismo enunciado pero con las opciones en posiciones distintas, de modo que
    «pulsa la tercera» no sirve para copiar. La corrección se hace por valor, no por posición.
    """
    rng = seeded_rng("present", q["id"], *seed_parts)
    kind = q["qtype"]
    view = {"qtype": kind, "prompt": q["prompt"]}
    if kind == "mcq":
        options = [q["correct"]] + list(q["wrong"])
        rng.shuffle(options)
        view["options"] = options
    elif kind == "tf":
        options = ["Verdadero", "Falso"]
        rng.shuffle(options)
        view["options"] = options
    elif kind == "image":
        sides = [{"id": "a", **q["a"]}, {"id": "b", **q["b"]}]
        rng.shuffle(sides)
        view["sides"] = sides
    elif kind == "match":
        left = [p[0] for p in q["pairs"]]
        right = [p[1] for p in q["pairs"]]
        rng.shuffle(left)
        rng.shuffle(right)
        view["left"], view["right"] = left, right
    return view


def check(q: dict, answer) -> bool:
    """Valida una respuesta en el servidor (nunca se confía en el cliente)."""
    kind = q["qtype"]
    if kind == "mcq":
        return isinstance(answer, str) and answer == q["correct"]
    if kind == "tf":
        return answer in ("Verdadero", "Falso") and (answer == "Verdadero") == bool(q["correct"])
    if kind == "image":
        return answer == q["correct"]
    if kind == "match":
        if not isinstance(answer, dict) or len(answer) != len(q["pairs"]):
            return False
        return all(answer.get(left) == right for left, right in q["pairs"])
    return False


def correct_text(q: dict) -> str:
    kind = q["qtype"]
    if kind == "mcq":
        return q["correct"]
    if kind == "tf":
        return "Verdadero" if q["correct"] else "Falso"
    if kind == "image":
        side = q[q["correct"]]
        return f"{side['emoji']} {side['label']}"
    if kind == "match":
        return " · ".join(f"{a} → {b}" for a, b in q["pairs"])
    return ""


# ── Puntuación y empates ──────────────────────────────────────────────────────
def score_answer(level: str, elapsed_ms: int, limit_ms: int, correct: bool) -> int:
    """Puntos base: entre 50 % y 100 % del valor del nivel según la rapidez."""
    if not correct:
        return 0
    base = LEVEL_POINTS.get(level, 100)
    fraction_left = max(0.0, min(1.0, 1 - elapsed_ms / max(1, limit_ms)))
    return round(base * (0.5 + 0.5 * fraction_left))


def resolve_round(answers: list[dict], tie_ms: int = DEFAULT_TIE_MS) -> dict:
    """Determina quién fue más rápido entre los que acertaron.

    `answers`: [{username, correct, t_ms}] con marcas de tiempo del SERVIDOR.
    Empate = varios aciertos dentro de `tie_ms` milisegundos del más rápido (0 = mismo ms).
    """
    right = sorted((a for a in answers if a["correct"]), key=lambda a: (a["t_ms"], a["username"]))
    if not right:
        return {"fastest": [], "tie": False}
    first = right[0]["t_ms"]
    tied = [a["username"] for a in right if a["t_ms"] - first <= tie_ms]
    return {"fastest": tied, "tie": len(tied) > 1}
