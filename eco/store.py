# -*- coding: utf-8 -*-
"""Persistencia en SQLite del banco de preguntas, historial, interruptores y minijuegos."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime

from . import engine, seed

_connector = None


def configure(connector) -> None:
    """La app registra su propia función de conexión (misma base de datos y misma ruta)."""
    global _connector
    _connector = connector


def get_con():
    if _connector is None:
        raise RuntimeError("eco.store no está configurado: llama a store.configure(db_connect)")
    return _connector()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── Esquema ───────────────────────────────────────────────────────────────────
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS eco_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, seed_key TEXT UNIQUE,
        category TEXT NOT NULL, level TEXT NOT NULL, qtype TEXT NOT NULL,
        prompt TEXT NOT NULL, payload TEXT NOT NULL, explanation TEXT NOT NULL DEFAULT '',
        owner TEXT NOT NULL DEFAULT '*', active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL DEFAULT 'sistema')""",
    "CREATE INDEX IF NOT EXISTS ix_eco_q_filter ON eco_questions(active, category, level, qtype)",
    """CREATE TABLE IF NOT EXISTS eco_seen (
        username TEXT NOT NULL, qid INTEGER NOT NULL, seen_at REAL NOT NULL, correct INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(username, qid))""",
    """CREATE TABLE IF NOT EXISTS eco_prefs (
        owner TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL, enabled INTEGER NOT NULL,
        updated_at TEXT NOT NULL, PRIMARY KEY(owner, kind, key))""",
    """CREATE TABLE IF NOT EXISTS eco_minigame (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, game TEXT NOT NULL,
        points INTEGER NOT NULL, detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS eco_rooms (
        code TEXT PRIMARY KEY, title TEXT NOT NULL, host TEXT NOT NULL, mode TEXT NOT NULL,
        category TEXT NOT NULL, level TEXT NOT NULL, qtypes TEXT NOT NULL,
        rounds INTEGER NOT NULL, seconds INTEGER NOT NULL, reveal_seconds INTEGER NOT NULL DEFAULT 7,
        tie_ms INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'lobby',
        round_no INTEGER NOT NULL DEFAULT 0, replay INTEGER NOT NULL DEFAULT 0, spare_used INTEGER NOT NULL DEFAULT 0,
        phase_started_ms INTEGER NOT NULL DEFAULT 0, snapshot TEXT NOT NULL,
        eligible TEXT, last_result TEXT, created_ms INTEGER NOT NULL, finished_ms INTEGER)""",
    """CREATE TABLE IF NOT EXISTS eco_players (
        code TEXT NOT NULL, username TEXT NOT NULL, display TEXT NOT NULL, team TEXT NOT NULL DEFAULT '',
        points INTEGER NOT NULL DEFAULT 0, correct INTEGER NOT NULL DEFAULT 0, last_delta INTEGER NOT NULL DEFAULT 0,
        joined_ms INTEGER NOT NULL, PRIMARY KEY(code, username))""",
    """CREATE TABLE IF NOT EXISTS eco_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, round_key TEXT NOT NULL, username TEXT NOT NULL,
        answer TEXT NOT NULL, correct INTEGER NOT NULL, t_ms INTEGER NOT NULL, elapsed_ms INTEGER NOT NULL,
        points INTEGER NOT NULL DEFAULT 0, UNIQUE(code, round_key, username))""",
]


def migrate(con) -> None:
    for ddl in SCHEMA:
        con.execute(ddl)
    existing = {r[0] for r in con.execute("SELECT seed_key FROM eco_questions WHERE seed_key IS NOT NULL")}
    now = _now()
    for q in seed.build():
        if q["seed_key"] in existing:
            continue
        con.execute(
            "INSERT INTO eco_questions(seed_key,category,level,qtype,prompt,payload,explanation,owner,active,created_at,updated_at,updated_by) "
            "VALUES(?,?,?,?,?,?,?,'*',1,?,?,'sistema')",
            (q["seed_key"], q["category"], q["level"], q["qtype"], q["prompt"],
             json.dumps(q["payload"], ensure_ascii=False), q["explanation"], now, now))
    # EcoParty añade sus tablas sin alterar las tablas existentes.
    from . import party
    party.migrate(con)
    con.commit()


# ── Codificación / validación ─────────────────────────────────────────────────
def decode(row) -> dict:
    payload = json.loads(row["payload"])
    q = {k: row[k] for k in ("id", "category", "level", "qtype", "prompt", "explanation", "owner", "active", "updated_at")}
    q["active"] = bool(q["active"])
    kind = q["qtype"]
    if kind == "mcq":
        q["correct"], q["wrong"] = payload["correct"], list(payload["wrong"])
    elif kind == "tf":
        q["correct"] = bool(payload["correct"])
    elif kind == "image":
        q["a"], q["b"], q["correct"] = payload["a"], payload["b"], payload["correct"]
    elif kind == "match":
        q["pairs"] = [tuple(p) for p in payload["pairs"]]
    return q


def encode_payload(q: dict) -> dict:
    kind = q["qtype"]
    if kind == "mcq":
        return {"correct": q["correct"].strip(), "wrong": [w.strip() for w in q["wrong"] if w and w.strip()]}
    if kind == "tf":
        return {"correct": bool(q["correct"])}
    if kind == "image":
        return {"a": {"emoji": q["a"]["emoji"].strip(), "label": q["a"]["label"].strip()},
                "b": {"emoji": q["b"]["emoji"].strip(), "label": q["b"]["label"].strip()}, "correct": q["correct"]}
    return {"pairs": [[a.strip(), b.strip()] for a, b in q["pairs"]]}


def validate(q: dict) -> list[str]:
    errors: list[str] = []
    if q.get("category") not in engine.CATEGORIES:
        errors.append("Elige una categoría válida.")
    if q.get("level") not in engine.LEVELS:
        errors.append("Elige un nivel válido.")
    kind = q.get("qtype")
    if kind not in engine.QTYPES:
        errors.append("Elige un tipo de pregunta válido.")
        return errors
    prompt = (q.get("prompt") or "").strip()
    if not 8 <= len(prompt) <= 300:
        errors.append("El enunciado debe tener entre 8 y 300 caracteres.")
    if len((q.get("explanation") or "").strip()) > 400:
        errors.append("La explicación admite hasta 400 caracteres.")
    if kind == "mcq":
        correct = (q.get("correct") or "").strip()
        wrong = [w.strip() for w in (q.get("wrong") or []) if w and w.strip()]
        if not correct or len(correct) > 120:
            errors.append("Escribe la respuesta correcta (máx. 120 caracteres).")
        if not 2 <= len(wrong) <= 3:
            errors.append("Escribe entre 2 y 3 respuestas incorrectas.")
        lowered = [correct.lower()] + [w.lower() for w in wrong]
        if len(set(lowered)) != len(lowered):
            errors.append("Las opciones no pueden repetirse.")
        if any(len(w) > 120 for w in wrong):
            errors.append("Cada opción admite hasta 120 caracteres.")
    elif kind == "tf":
        if not isinstance(q.get("correct"), bool):
            errors.append("Indica si la afirmación es verdadera o falsa.")
    elif kind == "image":
        for side in ("a", "b"):
            data = q.get(side) or {}
            if not (data.get("emoji") or "").strip() or len(data["emoji"].strip()) > 8:
                errors.append(f"La imagen {side.upper()} necesita un emoji (máx. 8 caracteres).")
            if not (data.get("label") or "").strip() or len(data["label"].strip()) > 60:
                errors.append(f"La imagen {side.upper()} necesita una etiqueta (máx. 60 caracteres).")
        if (q.get("a") or {}).get("label", "").strip().lower() == (q.get("b") or {}).get("label", "").strip().lower():
            errors.append("Las dos imágenes deben tener etiquetas distintas.")
        if q.get("correct") not in ("a", "b"):
            errors.append("Indica cuál imagen es la correcta.")
    elif kind == "match":
        pairs = [(a.strip(), b.strip()) for a, b in (q.get("pairs") or []) if a.strip() and b.strip()]
        if not 3 <= len(pairs) <= 6:
            errors.append("Un emparejamiento necesita entre 3 y 6 parejas completas.")
        if len({a.lower() for a, _ in pairs}) != len(pairs) or len({b.lower() for _, b in pairs}) != len(pairs):
            errors.append("Los elementos de cada columna no pueden repetirse.")
        if any(len(a) > 80 or len(b) > 80 for a, b in pairs):
            errors.append("Cada elemento admite hasta 80 caracteres.")
    return errors


# ── CRUD ──────────────────────────────────────────────────────────────────────
def add_question(con, q: dict, owner: str, actor: str) -> int:
    errors = validate(q)
    if errors:
        raise ValueError(" ".join(errors))
    now = _now()
    cur = con.execute(
        "INSERT INTO eco_questions(category,level,qtype,prompt,payload,explanation,owner,active,created_at,updated_at,updated_by) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (q["category"], q["level"], q["qtype"], q["prompt"].strip(), json.dumps(encode_payload(q), ensure_ascii=False),
         (q.get("explanation") or "").strip(), owner, 1 if q.get("active", True) else 0, now, now, actor))
    con.commit()
    return cur.lastrowid


def update_question(con, qid: int, q: dict, actor: str) -> None:
    errors = validate(q)
    if errors:
        raise ValueError(" ".join(errors))
    con.execute(
        "UPDATE eco_questions SET category=?,level=?,qtype=?,prompt=?,payload=?,explanation=?,active=?,updated_at=?,updated_by=? WHERE id=?",
        (q["category"], q["level"], q["qtype"], q["prompt"].strip(), json.dumps(encode_payload(q), ensure_ascii=False),
         (q.get("explanation") or "").strip(), 1 if q.get("active", True) else 0, _now(), actor, qid))
    con.commit()


def set_active(con, qid: int, active: bool, actor: str) -> None:
    con.execute("UPDATE eco_questions SET active=?,updated_at=?,updated_by=? WHERE id=?", (1 if active else 0, _now(), actor, qid))
    con.commit()


def delete_question(con, qid: int) -> None:
    con.execute("DELETE FROM eco_questions WHERE id=?", (qid,))
    con.execute("DELETE FROM eco_seen WHERE qid=?", (qid,))
    con.commit()


def get_question(con, qid: int) -> dict | None:
    row = con.execute("SELECT * FROM eco_questions WHERE id=?", (qid,)).fetchone()
    return decode(row) if row else None


def can_edit(q: dict, username: str, role: str) -> bool:
    return role == "admin" or (role == "teacher" and q["owner"] == username)


def list_questions(con, *, categories=None, levels=None, qtypes=None, owners=None, active=None, text="", limit=1000) -> list[dict]:
    sql, args = "SELECT * FROM eco_questions WHERE 1=1", []
    for column, values in (("category", categories), ("level", levels), ("qtype", qtypes), ("owner", owners)):
        if values:
            sql += f" AND {column} IN ({','.join('?' * len(values))})"
            args += list(values)
    if active is not None:
        sql += " AND active=?"
        args.append(1 if active else 0)
    if text and text.strip():
        sql += " AND prompt LIKE ?"
        args.append(f"%{text.strip()}%")
    sql += " ORDER BY category, CASE level WHEN 'Fácil' THEN 1 WHEN 'Intermedio' THEN 2 WHEN 'Avanzado' THEN 3 ELSE 4 END, id LIMIT ?"
    args.append(int(limit))
    return [decode(r) for r in con.execute(sql, args).fetchall()]


def counts_by_category(con, owners=None) -> dict:
    sql, args = "SELECT category, COUNT(*) FROM eco_questions WHERE active=1", []
    if owners:
        sql += f" AND owner IN ({','.join('?' * len(owners))})"
        args += list(owners)
    sql += " GROUP BY category"
    return {c: n for c, n in con.execute(sql, args).fetchall()}


def export_json(questions: list[dict]) -> str:
    keep = ("category", "level", "qtype", "prompt", "explanation", "correct", "wrong", "a", "b", "pairs")
    return json.dumps([{k: q[k] for k in keep if k in q} for q in questions], ensure_ascii=False, indent=2)


def import_json(con, text: str, owner: str, actor: str) -> tuple[int, list[str]]:
    """Importa preguntas desde JSON; devuelve (insertadas, errores por fila)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return 0, [f"JSON inválido: {exc.msg}"]
    if not isinstance(data, list):
        return 0, ["El archivo debe contener una lista de preguntas."]
    ok, problems = 0, []
    for i, item in enumerate(data[:500], 1):
        try:
            if not isinstance(item, dict):
                raise ValueError("no es un objeto")
            item = dict(item)
            if item.get("qtype") == "match":
                item["pairs"] = [tuple(p) for p in item.get("pairs", [])]
            add_question(con, item, owner, actor)
            ok += 1
        except (ValueError, TypeError, KeyError) as exc:
            problems.append(f"Fila {i}: {exc}")
    return ok, problems


# ── Selección sin repetición ──────────────────────────────────────────────────
def mark_seen(con, username: str, qid: int, correct: bool) -> None:
    con.execute(
        "INSERT INTO eco_seen(username,qid,seen_at,correct) VALUES(?,?,?,?) "
        "ON CONFLICT(username,qid) DO UPDATE SET seen_at=excluded.seen_at, correct=excluded.correct",
        (username, qid, time.time(), int(correct)))
    con.commit()


def pick_for_user(con, username: str, *, categories=None, levels=None, qtypes=None, n: int = 10,
                  owners=None, rng=None, exclude=()) -> tuple[list[dict], bool]:
    """Elige `n` preguntas priorizando las que el usuario NUNCA ha visto.

    Cuando se agotan, completa con las vistas hace más tiempo (ciclo de reposición).
    Devuelve (preguntas, hubo_ciclo).
    """
    rng = rng or engine.seeded_rng("pick", username, time.time_ns())
    pool = [q for q in list_questions(con, categories=categories, levels=levels, qtypes=qtypes, owners=owners, active=True)
            if q["id"] not in set(exclude)]
    seen = {r["qid"]: r["seen_at"] for r in con.execute("SELECT qid, seen_at FROM eco_seen WHERE username=?", (username,))}
    unseen = [q for q in pool if q["id"] not in seen]
    old = sorted((q for q in pool if q["id"] in seen), key=lambda q: seen[q["id"]])
    rng.shuffle(unseen)
    picked = unseen[:n]
    cycled = len(picked) < n and bool(old)
    if cycled:
        picked += old[: n - len(picked)]
    rng.shuffle(picked)
    return picked, cycled


def pick_mixed(con, username: str, *, categories=None, qtypes=None, n: int = 8, owners=None,
               levels=None, rng=None) -> tuple[list[dict], bool]:
    """Dificultad creciente: reparte `n` entre los niveles activos de Fácil a Experto."""
    levels = [lv for lv in engine.LEVELS if not levels or lv in levels]
    quotas = [n // len(levels) + (1 if i < n % len(levels) else 0) for i in range(len(levels))]
    result, cycled, used = [], False, []
    for level, quota in zip(levels, quotas):
        if not quota:
            continue
        chunk, cyc = pick_for_user(con, username, categories=categories, levels=[level], qtypes=qtypes,
                                   n=quota, owners=owners, rng=rng, exclude=used)
        used += [q["id"] for q in chunk]
        result += chunk
        cycled = cycled or cyc
    return result, cycled


# ── Interruptores de juegos / niveles / categorías / tipos ───────────────────
def get_prefs(con, owner: str) -> dict:
    return {(r["kind"], r["key"]): bool(r["enabled"])
            for r in con.execute("SELECT kind,key,enabled FROM eco_prefs WHERE owner=?", (owner,))}


def set_pref(con, owner: str, kind: str, key: str, enabled: bool) -> None:
    con.execute(
        "INSERT INTO eco_prefs(owner,kind,key,enabled,updated_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(owner,kind,key) DO UPDATE SET enabled=excluded.enabled, updated_at=excluded.updated_at",
        (owner, kind, key, 1 if enabled else 0, _now()))
    con.commit()


def linked_teachers(con, student: str) -> list[str]:
    """Docentes vinculados: por asignación de EcoAventura o por pertenecer a una de sus salas."""
    found: set = set()
    for sql in ("SELECT teacher FROM eco_student_grants WHERE student=?",
                "SELECT c.teacher FROM classes c JOIN participants p ON p.code=c.code WHERE p.username=?"):
        try:
            found.update(r[0] for r in con.execute(sql, (student,)).fetchall() if r[0])
        except sqlite3.OperationalError:
            continue
    return sorted(found)


def availability(con, username: str, role: str):
    """Devuelve una función `ok(kind, key)` con la disponibilidad efectiva para este usuario.

    Regla: el administrador manda (interruptor maestro). Un docente decide para sus clases.
    Un estudiante ve lo que habilite AL MENOS uno de sus docentes; sin docentes vinculados ve todo lo del administrador.
    Lo que no tiene fila se considera habilitado.
    """
    admin_map = get_prefs(con, "*")
    teacher_maps: list[dict] = []
    if role == "teacher":
        teacher_maps = [get_prefs(con, username)]
    elif role == "student":
        teacher_maps = [get_prefs(con, t) for t in linked_teachers(con, username)]

    def ok(kind: str, key: str) -> bool:
        if not admin_map.get((kind, key), True):
            return False
        if role == "admin" or not teacher_maps:
            return True
        return any(m.get((kind, key), True) for m in teacher_maps)

    return ok


def visible_owners(con, username: str, role: str) -> list[str]:
    """Propietarios cuyas preguntas puede usar este usuario: globales + propias + de sus docentes."""
    owners = {"*", username}
    if role == "student":
        owners.update(linked_teachers(con, username))
    return sorted(owners)


# ── Minijuegos ────────────────────────────────────────────────────────────────
def record_minigame(con, username: str, game: str, points: int, detail: str = "") -> None:
    con.execute("INSERT INTO eco_minigame(username,game,points,detail,created_at) VALUES(?,?,?,?,?)",
                (username, game, int(points), detail[:200], _now()))
    con.commit()


def minigame_best(con, username: str, game: str) -> int:
    row = con.execute("SELECT COALESCE(MAX(points),0) FROM eco_minigame WHERE username=? AND game=?", (username, game)).fetchone()
    return int(row[0])


def user_progress(con, username: str) -> dict:
    row = con.execute("SELECT COUNT(*) n, COALESCE(SUM(correct),0) ok FROM eco_seen WHERE username=?", (username,)).fetchone()
    pts = con.execute("SELECT COALESCE(SUM(points),0) FROM eco_minigame WHERE username=?", (username,)).fetchone()[0]
    return {"seen": int(row["n"]), "correct": int(row["ok"]), "points": int(pts)}
