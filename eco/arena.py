# -*- coding: utf-8 -*-
"""Arena en vivo (estilo Kahoot) con estado autoritativo en el servidor.

Cada sesión de navegador consulta periódicamente `tick()`. Esa función es idempotente y
atómica (BEGIN IMMEDIATE), así que no importa quién la llame primero: la ronda se cierra una
sola vez, aunque la pestaña del docente esté dormida.

Velocidad: la marca de tiempo de cada respuesta es la hora a la que el SERVIDOR procesó el
clic (no la del dispositivo, que se puede manipular). La latencia de red no se compensa.
"""
from __future__ import annotations

import csv
import io
import json
import secrets
import sqlite3

from . import engine, store

MODES = {"aula": "Batalla en el aula", "salon": "Torneo entre salones", "colegio": "Campeonato entre colegios"}
TEAM_MODES = {"salon": "Salón", "colegio": "Colegio"}
SPARES = engine.MAX_REPLAYS


# ── Utilidades ────────────────────────────────────────────────────────────────
def _begin(con) -> None:
    if not con.in_transaction:
        con.execute("BEGIN IMMEDIATE")


def get_room(con, code: str) -> dict | None:
    row = con.execute("SELECT * FROM eco_rooms WHERE code=?", ((code or "").strip(),)).fetchone()
    if not row:
        return None
    room = dict(row)
    room["snapshot"] = json.loads(room["snapshot"])
    room["eligible"] = json.loads(room["eligible"]) if room["eligible"] else None
    room["last_result"] = json.loads(room["last_result"]) if room["last_result"] else None
    room["qtypes"] = json.loads(room["qtypes"])
    return room


def current_index(room: dict) -> int:
    return room["round_no"] - 1 if room["replay"] == 0 else room["rounds"] + room["spare_used"] - 1


def current_question(room: dict) -> dict | None:
    if room["status"] not in ("question", "reveal") or room["round_no"] < 1:
        return None
    idx = current_index(room)
    return room["snapshot"][idx] if 0 <= idx < len(room["snapshot"]) else None


def round_key(room: dict) -> str:
    return f"{room['round_no']}.{room['replay']}"


def deadline_ms(room: dict) -> int:
    return room["phase_started_ms"] + room["seconds"] * 1000


# ── Creación y acceso ─────────────────────────────────────────────────────────
def create_room(con, host: str, *, title: str, mode: str, category: str | None, level: str, qtypes: list[str],
                rounds: int, seconds: int, reveal_seconds: int = 7, tie_ms: int = 0,
                owners=None, allowed_levels=None, allowed_categories=None) -> str:
    if mode not in MODES:
        raise ValueError("Modo de campeonato no válido.")
    if not 3 <= rounds <= 20:
        raise ValueError("Elige entre 3 y 20 rondas.")
    if not 5 <= seconds <= 90:
        raise ValueError("Cada ronda debe durar entre 5 y 90 segundos.")
    qtypes = [t for t in qtypes if t in engine.QTYPES]
    if not qtypes:
        raise ValueError("Selecciona al menos un tipo de pregunta.")
    cats = [category] if category else (allowed_categories or None)
    mixed = level == "Mixta"
    levels = allowed_levels if mixed else [level]
    if levels is not None and not levels:
        raise ValueError("No hay niveles habilitados.")
    if mixed:
        main, _ = store.pick_mixed(con, host, categories=cats, qtypes=qtypes, n=rounds, owners=owners, levels=levels)
    else:
        main, _ = store.pick_for_user(con, host, categories=cats, levels=levels, qtypes=qtypes, n=rounds, owners=owners)
    if len(main) < rounds:
        raise ValueError(f"Solo hay {len(main)} preguntas disponibles con esos filtros; reduce las rondas o amplía categorías, niveles o tipos.")
    spare, _ = store.pick_for_user(con, host, categories=cats, levels=levels, qtypes=qtypes, n=SPARES,
                                   owners=owners, exclude=[q["id"] for q in main])
    snapshot = main + spare
    code = None
    for _ in range(50):
        candidate = f"{secrets.randbelow(900000) + 100000}"
        if not con.execute("SELECT 1 FROM eco_rooms WHERE code=?", (candidate,)).fetchone():
            code = candidate
            break
    if code is None:
        raise RuntimeError("No se pudo generar un PIN único.")
    con.execute(
        "INSERT INTO eco_rooms(code,title,host,mode,category,level,qtypes,rounds,seconds,reveal_seconds,tie_ms,status,round_no,"
        "replay,spare_used,phase_started_ms,snapshot,created_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,'lobby',0,0,0,0,?,?)",
        (code, title.strip()[:80] or "Campeonato EcoGuardian", host, mode, category or "Todas", level, json.dumps(qtypes),
         rounds, seconds, reveal_seconds, max(0, int(tie_ms)), json.dumps(snapshot, ensure_ascii=False), engine.now_ms()))
    con.commit()
    for q in main:
        store.mark_seen(con, host, q["id"], False)
    return code


def join(con, code: str, username: str, display: str, team: str = "") -> str:
    room = get_room(con, code)
    if not room:
        return "no_room"
    if room["status"] == "finished":
        return "finished"
    team = engine.normalize_team(team)
    if room["mode"] in TEAM_MODES and not team:
        return "team_required"
    if room["mode"] == "aula":
        team = ""
    con.execute(
        "INSERT INTO eco_players(code,username,display,team,joined_ms) VALUES(?,?,?,?,?) "
        "ON CONFLICT(code,username) DO UPDATE SET display=excluded.display, team=excluded.team",
        (room["code"], username, display[:40], team, engine.now_ms()))
    con.commit()
    return "ok"


def list_host_rooms(con, host: str, limit: int = 15) -> list[dict]:
    rows = con.execute("SELECT code,title,mode,status,rounds,created_ms FROM eco_rooms WHERE host=? ORDER BY created_ms DESC LIMIT ?",
                       (host, limit)).fetchall()
    return [dict(r) for r in rows]


def players(con, code: str) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT * FROM eco_players WHERE code=? ORDER BY joined_ms", (code,))]


def answer_count(con, room: dict) -> int:
    return con.execute("SELECT COUNT(*) FROM eco_answers WHERE code=? AND round_key=?", (room["code"], round_key(room))).fetchone()[0]


def my_answer(con, room: dict, username: str):
    return con.execute("SELECT correct,points,answer FROM eco_answers WHERE code=? AND round_key=? AND username=?",
                       (room["code"], round_key(room), username)).fetchone()


# ── Control del anfitrión ─────────────────────────────────────────────────────
def start(con, code: str, host: str, now: int | None = None) -> bool:
    now = engine.now_ms() if now is None else now
    _begin(con)
    room = get_room(con, code)
    ok = bool(room and room["host"] == host and room["status"] == "lobby"
              and con.execute("SELECT COUNT(*) FROM eco_players WHERE code=?", (code,)).fetchone()[0] > 0)
    if ok:
        con.execute("UPDATE eco_rooms SET status='question', round_no=1, replay=0, spare_used=0, eligible=NULL, phase_started_ms=? WHERE code=?",
                    (now, code))
    con.commit()
    return ok


def finish(con, code: str, host: str, now: int | None = None) -> None:
    con.execute("UPDATE eco_rooms SET status='finished', finished_ms=? WHERE code=? AND host=? AND status!='finished'",
                (engine.now_ms() if now is None else now, code, host))
    con.commit()


def skip(con, code: str, host: str, now: int | None = None) -> dict | None:
    """El anfitrión adelanta el cierre de la ronda o el paso de la pantalla de resultados."""
    room = get_room(con, code)
    if not room or room["host"] != host:
        return room
    return tick(con, code, now, force=True)


# ── Respuestas ────────────────────────────────────────────────────────────────
def submit(con, code: str, username: str, answer, t_ms: int | None = None) -> str:
    """Registra una respuesta. `t_ms` debe tomarse lo antes posible al recibir el clic."""
    t = t_ms if t_ms is not None else engine.now_ms()
    room = get_room(con, code)
    if not room or room["status"] != "question":
        return "closed"
    if not con.execute("SELECT 1 FROM eco_players WHERE code=? AND username=?", (code, username)).fetchone():
        return "not_player"
    if room["eligible"] is not None and username not in room["eligible"]:
        return "not_eligible"
    elapsed = t - room["phase_started_ms"]
    if elapsed > room["seconds"] * 1000:
        return "late"
    q = current_question(room)
    correct = engine.check(q, answer)
    try:
        con.execute("INSERT INTO eco_answers(code,round_key,username,answer,correct,t_ms,elapsed_ms) VALUES(?,?,?,?,?,?,?)",
                    (code, round_key(room), username, json.dumps(answer, ensure_ascii=False), int(correct), t, max(0, elapsed)))
        con.commit()
    except sqlite3.IntegrityError:
        con.rollback()
        return "dup"
    return "ok"


# ── Máquina de estados ────────────────────────────────────────────────────────
def _is_due(con, room: dict, now: int, force: bool) -> bool:
    if room["status"] == "question":
        if force or now >= deadline_ms(room):
            return True
        expected = len(room["eligible"]) if room["eligible"] is not None else \
            con.execute("SELECT COUNT(*) FROM eco_players WHERE code=?", (room["code"],)).fetchone()[0]
        return expected > 0 and answer_count(con, room) >= expected
    if room["status"] == "reveal":
        return force or now >= room["phase_started_ms"] + room["reveal_seconds"] * 1000
    return False


def tick(con, code: str, now: int | None = None, *, force: bool = False) -> dict | None:
    """Avanza la sala si corresponde. Seguro de llamar desde muchas sesiones a la vez."""
    now = engine.now_ms() if now is None else now
    room = get_room(con, code)
    if not room or not _is_due(con, room, now, force):
        return room
    try:
        _begin(con)
        room = get_room(con, code)               # relee bajo bloqueo: otra sesión pudo adelantarse
        if room and _is_due(con, room, now, force):
            if room["status"] == "question":
                _close_round(con, room, now)
            elif room["status"] == "reveal":
                _advance(con, room, now)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return get_room(con, code)


def _close_round(con, room: dict, now: int) -> None:
    code, q, key = room["code"], current_question(room), round_key(room)
    is_replay = room["replay"] > 0
    rows = con.execute("SELECT username,correct,t_ms,elapsed_ms FROM eco_answers WHERE code=? AND round_key=?", (code, key)).fetchall()
    verdict = engine.resolve_round([{"username": r["username"], "correct": bool(r["correct"]), "t_ms": r["t_ms"]} for r in rows],
                                   room["tie_ms"])
    fastest, tie = verdict["fastest"], verdict["tie"]
    can_replay = (tie and room["replay"] < engine.MAX_REPLAYS and room["rounds"] + room["spare_used"] < len(room["snapshot"]))
    con.execute("UPDATE eco_players SET last_delta=0 WHERE code=?", (code,))
    per_user = {}
    for r in rows:
        correct = bool(r["correct"])
        base = 0 if is_replay else engine.score_answer(q["level"], r["elapsed_ms"], room["seconds"] * 1000, correct)
        bonus = 0
        if r["username"] in fastest:
            if not tie:
                bonus = engine.REFLEX_BONUS
            elif not can_replay:
                bonus = engine.REFLEX_BONUS // len(fastest)      # repeticiones agotadas: se reparte el bono
        pts = base + bonus
        con.execute("UPDATE eco_answers SET points=? WHERE code=? AND round_key=? AND username=?", (pts, code, key, r["username"]))
        con.execute("UPDATE eco_players SET points=points+?, correct=correct+?, last_delta=? WHERE code=? AND username=?",
                    (pts, 1 if (correct and not is_replay) else 0, pts, code, r["username"]))
        per_user[r["username"]] = {"correct": correct, "points": pts}
    result = {"round_key": key, "correct_text": engine.correct_text(q), "explanation": q.get("explanation", ""),
              "level": q["level"], "fastest": fastest, "tie": tie, "replay_next": can_replay,
              "no_correct": not fastest, "per_user": per_user}
    if can_replay:
        con.execute("UPDATE eco_rooms SET status='reveal', phase_started_ms=?, last_result=?, spare_used=spare_used+1, replay=replay+1, eligible=? WHERE code=?",
                    (now, json.dumps(result, ensure_ascii=False), json.dumps(fastest), code))
    else:
        con.execute("UPDATE eco_rooms SET status='reveal', phase_started_ms=?, last_result=? WHERE code=?",
                    (now, json.dumps(result, ensure_ascii=False), code))


def _advance(con, room: dict, now: int) -> None:
    code = room["code"]
    if (room["last_result"] or {}).get("replay_next"):
        con.execute("UPDATE eco_rooms SET status='question', phase_started_ms=? WHERE code=?", (now, code))
    elif room["round_no"] >= room["rounds"]:
        con.execute("UPDATE eco_rooms SET status='finished', finished_ms=? WHERE code=?", (now, code))
    else:
        con.execute("UPDATE eco_rooms SET status='question', round_no=round_no+1, replay=0, eligible=NULL, phase_started_ms=? WHERE code=?",
                    (now, code))


# ── Clasificación ─────────────────────────────────────────────────────────────
def leaderboard(con, code: str) -> list[dict]:
    rows = con.execute("SELECT * FROM eco_players WHERE code=? ORDER BY points DESC, correct DESC, joined_ms ASC", (code,)).fetchall()
    return [{**dict(r), "rank": i + 1} for i, r in enumerate(rows)]


def team_board(con, code: str) -> list[dict]:
    teams: dict[str, dict] = {}
    for p in players(con, code):
        if not p["team"]:
            continue
        t = teams.setdefault(p["team"], {"team": p["team"], "points": 0, "members": 0})
        t["points"] += p["points"]
        t["members"] += 1
    board = sorted(({**t, "avg": round(t["points"] / t["members"], 1)} for t in teams.values()),
                   key=lambda t: (-t["avg"], -t["points"], t["team"]))
    return [{**t, "rank": i + 1} for i, t in enumerate(board)]


def results_csv(con, code: str) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Posición", "Nombre", "Equipo", "Puntos", "Aciertos"])
    for p in leaderboard(con, code):
        writer.writerow([p["rank"], p["display"], p["team"], p["points"], p["correct"]])
    return out.getvalue()
