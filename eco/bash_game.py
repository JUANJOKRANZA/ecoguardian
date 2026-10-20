# -*- coding: utf-8 -*-
"""Balloon Bash · modo aula (memorización a ciegas), integrado en EcoGuardian.

Las salas viven en memoria del proceso de Streamlit y se comparten entre todas las sesiones
(docente = panel proyectado, estudiantes = control). No hay servidor aparte.

Unidades: el aire se mide en % del tamaño OBJETIVO (100 = encaja justo). Cada carril tiene una
capacidad oculta (108–130 %); al alcanzarla el recurso revienta.
"""
from __future__ import annotations

import random
import re
import secrets
import threading
import time
from dataclasses import dataclass

LANES = [
    {"id": "leaf", "name": "Hoja", "icon": "🍃"},
    {"id": "drop", "name": "Gota de Agua", "icon": "💧"},
    {"id": "bin", "name": "Cesto de Reciclaje", "icon": "♻️"},
    {"id": "bulb", "name": "Bombilla", "icon": "💡"},
]
DEMO_NAMES = ["Pedro", "Luisa", "Juan", "Ana"]
MEMORIZE_S, INFLATE_S, REVEAL_S, ROUNDS, RELAY_SWAP_S = 4.0, 25.0, 7.0, 3, 4.0
DANGER = 0.85            # temblor al 85 % de la capacidad invisible
MAX_BATCH = 6            # bombeos aceptados por lote del celular
BATCH_GAP = 0.15         # s mínimos entre lotes por jugador
MODES = ("ffa", "relay")
ROOM_TTL_S = 6 * 3600


def clean_name(raw) -> str:
    return re.sub(r"[^\w .\-áéíóúüñÁÉÍÓÚÜÑ]", "", str(raw or ""), flags=re.UNICODE).strip()[:16]


@dataclass
class Player:
    pid: str
    name: str
    lane: int = 0
    slot: int = 0
    bot: bool = False
    last_batch: float = 0.0
    seen: float = 0.0


@dataclass
class LaneState:
    idx: int
    vscale: float          # variación sutil de escala (anti-copia)
    tsize: float           # tamaño de la silueta objetivo en esta ronda
    gain: float
    capacity: float
    air: float = 0.0
    pumps: int = 0
    done: bool = False
    popped: bool = False
    active_slot: int = 0
    baton_at: float = 0.0
    bot_aim: float = 95.0
    bot_next: float = 0.0

    @property
    def size(self) -> float:
        return self.vscale * self.tsize * (0.15 + 0.85 * self.air / 100.0)

    @property
    def tscale(self) -> float:
        return self.vscale * self.tsize

    @property
    def danger(self) -> bool:
        return (not self.done) and self.air >= DANGER * self.capacity


def score_for(pct: float, popped: bool) -> int:
    return 0 if popped else max(0, round(100 - abs(100 - pct) * 3))


def label_for(pct: float, popped: bool) -> str:
    if popped:
        return "¡POPPING!"
    if abs(100 - pct) <= 5:
        return "¡ENCAJÓ!"
    return "¡Faltó aire!" if pct < 100 else "¡Te pasaste!"


class Room:
    def __init__(self, code: str, host: str, rng: random.Random | None = None):
        self.code, self.host = code, host
        self.rng = rng or random.Random(secrets.randbits(64))
        self.mode, self.phase, self.round_no, self.phase_end = "ffa", "lobby", 0, 0.0
        self.players: dict[str, Player] = {}
        self.lanes: list[LaneState] = []
        self.totals: dict[int, int] = {}
        self.results: dict[int, dict] = {}
        self.ann = {"id": 0, "text": ""}            # locutor: el panel habla cuando cambia el id
        self.baton_id = 0
        self.saved = False
        self.created = self.touched = time.monotonic()
        self.lock = threading.RLock()

    # ── utilidades ─────────────────────────────────────────────────────────
    def say(self, text: str) -> None:
        self.ann = {"id": self.ann["id"] + 1, "text": text}

    @property
    def lane_count(self) -> int:
        return 4 if self.mode == "ffa" else 2

    def lane_players(self, lane: int) -> list[Player]:
        return sorted((p for p in self.players.values() if p.lane == lane), key=lambda p: p.slot)

    def lane_label(self, lane: int) -> str:
        return " + ".join(p.name for p in self.lane_players(lane)) or "—"

    def _assign(self) -> None:
        for i, p in enumerate(self.players.values()):
            p.lane, p.slot = (i, 0) if self.mode == "ffa" else (i % 2, i // 2)

    def _is_active(self, p: Player) -> bool:
        if self.phase != "inflate" or p.lane >= len(self.lanes):
            return False
        ln = self.lanes[p.lane]
        return (not ln.done) and (self.mode == "ffa" or len(self.lane_players(p.lane)) < 2 or ln.active_slot == p.slot)

    # ── lobby ──────────────────────────────────────────────────────────────
    def join(self, pid: str, name: str):
        with self.lock:
            name = clean_name(name) or clean_name(pid)
            if pid in self.players:
                return True, ""
            if self.phase != "lobby":
                return False, "La partida ya empezó."
            if len(self.players) >= 4:
                return False, "Sala llena (máximo 4 jugadores)."
            self.players[pid] = Player(pid, name)
            self._assign()
            return True, ""

    def set_mode(self, mode: str) -> None:
        with self.lock:
            if self.phase == "lobby" and mode in MODES:
                self.mode = mode
                self._assign()

    def add_bots(self) -> None:
        with self.lock:
            if self.phase != "lobby":
                return
            taken = {p.name.lower() for p in self.players.values()}
            for n in DEMO_NAMES:
                if len(self.players) < 4 and n.lower() not in taken:
                    self.players["bot_" + n.lower()] = Player("bot_" + n.lower(), n, bot=True)
            self._assign()

    def leaderboard(self) -> list[dict]:
        rows = [{"lane": i, "name": self.lane_label(i), "points": self.totals.get(i, 0)}
                for i in range(self.lane_count) if self.lane_players(i)]
        return sorted(rows, key=lambda r: (-r["points"], r["lane"]))

    # ── flujo ──────────────────────────────────────────────────────────────
    def start(self, now: float | None = None) -> bool:
        with self.lock:
            now = time.monotonic() if now is None else now
            if self.phase not in ("lobby", "final") or not self.players:
                return False
            self.totals, self.round_no, self.saved = {}, 0, False
            self._start_round(now)
            return True

    def final_scores(self) -> dict[str, int]:
        """Puntos por jugador (en relevos, el total del equipo) para guardar al terminar."""
        return {p.pid: self.totals.get(p.lane, 0) for p in self.players.values() if not p.bot}

    def reset(self) -> None:
        with self.lock:
            self.phase, self.round_no, self.lanes, self.totals, self.results = "lobby", 0, [], {}, {}

    def _start_round(self, now: float) -> None:
        self.round_no += 1
        r = self.rng
        self.lanes = [LaneState(i, r.uniform(0.88, 1.12), r.uniform(0.45, 0.78), r.uniform(0.85, 1.15),
                                r.uniform(108, 130), bot_aim=r.uniform(82, 104)) for i in range(self.lane_count)]
        self.results = {}
        self.phase, self.phase_end = "memorize", now + MEMORIZE_S
        self.say("¡Memoriza el tamaño!")

    def _begin_inflate(self, now: float) -> None:
        self.phase, self.phase_end = "inflate", now + INFLATE_S
        for l in self.lanes:
            l.baton_at = now
        self.say("¡A inflar!")

    def _begin_reveal(self, now: float, timeout: bool) -> None:
        self.phase, self.phase_end = "reveal", now + REVEAL_S
        self.say("¡Tiempo!" if timeout else "¡Ronda terminada!")

    def _finish(self, ln: LaneState, popped: bool) -> None:
        if ln.done:
            return
        ln.done, ln.popped = True, popped
        sc = score_for(ln.air, popped)
        self.totals[ln.idx] = self.totals.get(ln.idx, 0) + sc
        self.results[ln.idx] = {"pct": round(ln.air), "popped": popped, "score": sc, "label": label_for(ln.air, popped),
                                "tscale": round(ln.tscale, 3), "size": round(ln.size, 3)}

    # ── acciones de jugadores ──────────────────────────────────────────────
    def _lane_of(self, pid: str):
        p = self.players.get(pid)
        if not p or self.phase != "inflate" or p.lane >= len(self.lanes) or not self._is_active(p):
            return None, None
        return p, self.lanes[p.lane]

    def pump(self, pid: str, n: int = 1, power: float = 0.6, now: float | None = None, bypass_gap: bool = False) -> int:
        with self.lock:
            now = time.monotonic() if now is None else now
            self.tick(now)
            p, ln = self._lane_of(pid)
            if not p or (not bypass_gap and now - p.last_batch < BATCH_GAP):
                return 0
            p.last_batch = now
            try:
                power = min(1.0, max(0.0, float(power)))
                n = max(0, min(MAX_BATCH, int(n)))
            except (TypeError, ValueError):
                return 0
            done = 0
            for _ in range(n):
                ln.air += 3.0 * ln.gain * (0.7 + 0.3 * power) * self.rng.uniform(0.85, 1.15)
                ln.pumps += 1
                done += 1
                if ln.air >= ln.capacity:
                    self._finish(ln, True)
                    break
            return done

    def brake(self, pid: str, now: float | None = None) -> bool:
        with self.lock:
            self.tick(time.monotonic() if now is None else now)
            p, ln = self._lane_of(pid)
            if not p:
                return False
            self._finish(ln, False)
            return True

    # ── reloj (se llama en cada acceso; idempotente) ───────────────────────
    def tick(self, now: float | None = None) -> None:
        with self.lock:
            now = time.monotonic() if now is None else now
            self.touched = now
            if self.phase == "memorize" and now >= self.phase_end:
                self._begin_inflate(now)
            elif self.phase == "inflate":
                self._tick_relay(now)
                self._tick_bots(now)
                timeout = now >= self.phase_end
                if timeout:
                    for l in self.lanes:
                        self._finish(l, False)
                if all(l.done for l in self.lanes):
                    self._begin_reveal(now, timeout)
            elif self.phase == "reveal" and now >= self.phase_end:
                if self.round_no >= ROUNDS:
                    self.phase = "final"
                    self.say("¡Fin del juego!")
                else:
                    self._start_round(now)

    def _tick_relay(self, now: float) -> None:
        if self.mode != "relay":
            return
        for l in self.lanes:
            pl = self.lane_players(l.idx)
            if not l.done and len(pl) > 1 and now - l.baton_at >= RELAY_SWAP_S:
                l.active_slot = (l.active_slot + 1) % len(pl)
                l.baton_at = now
                self.baton_id += 1
                self.say("¡Relevo!")

    def _tick_bots(self, now: float) -> None:
        for p in self.players.values():
            if not p.bot:
                continue
            _, ln = self._lane_of(p.pid)
            if not ln or now < ln.bot_next:
                continue
            ln.bot_next = now + self.rng.uniform(0.18, 0.4)
            if ln.air >= ln.bot_aim:
                self._finish(ln, False)
            else:
                ln.air += 3.0 * ln.gain * 0.9 * self.rng.uniform(0.85, 1.15)
                ln.pumps += 1
                if ln.air >= ln.capacity:
                    self._finish(ln, True)

    # ── vistas ─────────────────────────────────────────────────────────────
    def _turn_name(self, l: LaneState) -> str:
        pl = self.lane_players(l.idx)
        return pl[l.active_slot % len(pl)].name if (self.mode == "relay" and len(pl) > 1 and not l.done) else ""

    def snapshot(self, now: float | None = None) -> dict:
        """Estado para el panel proyectado. En fase ciega: solo tamaños visuales y bandera de peligro;
        porcentajes y puntos aparecen únicamente en carriles ya finalizados."""
        with self.lock:
            now = time.monotonic() if now is None else now
            self.tick(now)
            lanes = [{"lane": i, "res": LANES[i]["id"], "resName": LANES[i]["name"], "icon": LANES[i]["icon"],
                      "players": [p.name for p in self.lane_players(i)]} for i in range(self.lane_count)]
            if self.phase in ("memorize", "inflate", "reveal"):
                for l in self.lanes:
                    d = lanes[l.idx]
                    d.update(size=round(l.size, 3), danger=l.danger, done=l.done, pumps=l.pumps, turn=self._turn_name(l))
                    if self.phase == "memorize":
                        d["tscale"] = round(l.tscale, 3)
                    if l.idx in self.results:
                        d["result"] = self.results[l.idx]
            return {"code": self.code, "mode": self.mode, "phase": self.phase, "round": self.round_no, "rounds": ROUNDS,
                    "remaining": round(max(0.0, self.phase_end - now), 2) if self.phase != "lobby" else 0,
                    "memorizeDur": MEMORIZE_S, "inflateDur": INFLATE_S, "lanes": lanes,
                    "leaderboard": self.leaderboard(), "ann": self.ann}

    def player_view(self, pid: str, now: float | None = None) -> dict:
        """Estado para el celular: JAMÁS incluye silueta, aire ni porcentajes."""
        with self.lock:
            self.tick(time.monotonic() if now is None else now)
            p = self.players.get(pid)
            if not p:
                return {"joined": False}
            done = self.phase == "inflate" and p.lane < len(self.lanes) and self.lanes[p.lane].done
            popped = bool(done and self.lanes[p.lane].popped)
            return {"joined": True, "name": p.name, "phase": self.phase, "mode": self.mode, "round": self.round_no,
                    "active": self._is_active(p), "done": done, "popped": popped, "baton": self.baton_id,
                    "mate": [q.name for q in self.lane_players(p.lane) if q.pid != pid]}


# ── Registro global de salas (compartido por todas las sesiones del servidor) ──
_ROOMS: dict[str, Room] = {}
_REG_LOCK = threading.Lock()


def create_room(host: str, fixed_pin: str | None = None) -> Room:
    with _REG_LOCK:
        _gc()
        for r in _ROOMS.values():                       # un docente, una sala abierta
            if r.host == host:
                return r
        code = fixed_pin if fixed_pin and fixed_pin not in _ROOMS else None
        while not code or code in _ROOMS:
            code = f"{secrets.randbelow(9000) + 1000}"
        _ROOMS[code] = Room(code, host)
        return _ROOMS[code]


def get_room(code: str) -> Room | None:
    return _ROOMS.get(str(code or "").strip())


def close_room(code: str) -> None:
    with _REG_LOCK:
        _ROOMS.pop(str(code), None)


def _gc() -> None:
    now = time.monotonic()
    for c in [c for c, r in _ROOMS.items() if now - r.touched > ROOM_TTL_S]:
        _ROOMS.pop(c, None)
