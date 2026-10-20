# -*- coding: utf-8 -*-
"""EcoParty: minijuegos ambientales de fiesta con salas compartidas.

Las salas online guardan estado en la base de datos de la aplicación. Para jugar entre
varios dispositivos, todos deben acceder a la misma instancia y base de datos compartida.
"""
from __future__ import annotations
import json
import secrets
import sqlite3
from . import engine

MAX_PLAYERS = 12
GAMES = [
    {"id":"reciclaje", "title":"¡A separar!", "prompt":"¿Dónde depositas una botella plástica limpia y seca?", "options":["Blanco · aprovechables", "Verde · orgánicos", "Negro · no aprovechables", "Rojo · manejo especial"], "answer":"Blanco · aprovechables", "why":"Los residuos aprovechables limpios y secos van al recipiente blanco en Colombia."},
    {"id":"energia", "title":"Apaga y gana", "prompt":"Sales del salón durante el descanso. ¿Qué acción ahorra energía?", "options":["Dejar luces y ventilador encendidos", "Apagar luces y equipos que no se usan", "Abrir la nevera", "Encender todas las luces"], "answer":"Apagar luces y equipos que no se usan", "why":"Apagar los equipos que no se necesitan reduce el consumo de energía."},
    {"id":"agua", "title":"Guardianes del agua", "prompt":"Mientras te cepillas los dientes, ¿qué haces?", "options":["Dejar correr el agua", "Cerrar la llave", "Llenar la ducha", "Abrir otra llave"], "answer":"Cerrar la llave", "why":"Cerrar la llave evita desperdiciar agua potable."},
    {"id":"biodiversidad", "title":"Reto biodiversidad", "prompt":"¿Cuál es una forma segura de ayudar a los polinizadores?", "options":["Destruir flores silvestres", "Usar más pesticidas", "Sembrar plantas nativas", "Capturar abejas"], "answer":"Sembrar plantas nativas", "why":"Las plantas nativas ofrecen alimento y refugio a los polinizadores."},
    {"id":"clima", "title":"¡Clima relámpago!", "prompt":"¿Cuál de estas acciones ayuda a reducir emisiones?", "options":["Caminar trayectos cortos", "Quemar residuos", "Dejar el motor encendido", "Desperdiciar electricidad"], "answer":"Caminar trayectos cortos", "why":"Caminar trayectos cortos evita emisiones del transporte motorizado."},
    {"id":"reuso", "title":"Reutiliza antes de botar", "prompt":"Una hoja tiene una cara en blanco. ¿Qué puedes hacer?", "options":["Usarla para borradores", "Tirarla de inmediato", "Mojarla", "Quemarla"], "answer":"Usarla para borradores", "why":"Reutilizar papel aprovecha mejor los recursos ya consumidos."},
    {"id":"oceano", "title":"Misión océano", "prompt":"En la playa encuentras un envoltorio plástico. ¿Qué haces?", "options":["Lo dejas en la arena", "Lo lanzas al agua", "Lo recoges si es seguro y lo dispones bien", "Lo entierras"], "answer":"Lo recoges si es seguro y lo dispones bien", "why":"Evitar que los residuos lleguen al mar protege la fauna."},
    {"id":"compost", "title":"Maestros del compost", "prompt":"¿Cuál residuo sirve para compostaje?", "options":["Cáscaras de frutas", "Pilas", "Vidrio roto", "Pañuelos usados"], "answer":"Cáscaras de frutas", "why":"Los restos vegetales pueden convertirse en abono mediante compostaje."},
    {"id":"movilidad", "title":"Eco-movilidad", "prompt":"Para un trayecto corto y seguro, ¿qué opción evita emisiones directas?", "options":["Caminar o ir en bicicleta", "Ir solo en un carro", "Dejar el carro encendido", "Hacer varios viajes separados"], "answer":"Caminar o ir en bicicleta", "why":"La movilidad activa no produce emisiones directas durante el trayecto."},
    {"id":"consumo", "title":"Compra con cabeza", "prompt":"¿Qué hábito ayuda a reducir residuos?", "options":["Llevar botella reutilizable", "Usar un vaso desechable cada vez", "Comprar productos sobreempacados", "Botar lo que aún sirve"], "answer":"Llevar botella reutilizable", "why":"Los artículos reutilizables reducen el uso de productos de un solo uso."},
    {"id":"plantas", "title":"Pulgar verde", "prompt":"¿Qué necesita una planta para crecer saludablemente?", "options":["Agua adecuada, luz y suelo apropiado", "Solo plástico", "Pintura", "Agua con detergente"], "answer":"Agua adecuada, luz y suelo apropiado", "why":"Las plantas necesitan agua, luz, aire y nutrientes en condiciones adecuadas."},
    {"id":"ruido", "title":"Oídos verdes", "prompt":"¿Cuál es una buena práctica para cuidar el ambiente sonoro escolar?", "options":["Gritar en los pasillos", "Bajar la voz y evitar golpes innecesarios", "Poner música al máximo", "Arrastrar muebles"], "answer":"Bajar la voz y evitar golpes innecesarios", "why":"Reducir el ruido mejora la convivencia y favorece la concentración."},
]

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS eco_party_rooms (
        code TEXT PRIMARY KEY, title TEXT NOT NULL, host TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'lobby',
        round_no INTEGER NOT NULL DEFAULT 0, rounds INTEGER NOT NULL, seconds INTEGER NOT NULL,
        phase_started_ms INTEGER NOT NULL DEFAULT 0, snapshot TEXT NOT NULL, created_ms INTEGER NOT NULL,
        finished_ms INTEGER)""",
    """CREATE TABLE IF NOT EXISTS eco_party_players (
        code TEXT NOT NULL, username TEXT NOT NULL, display TEXT NOT NULL, points INTEGER NOT NULL DEFAULT 0,
        joined_ms INTEGER NOT NULL, PRIMARY KEY(code, username))""",
    """CREATE TABLE IF NOT EXISTS eco_party_answers (
        code TEXT NOT NULL, round_no INTEGER NOT NULL, username TEXT NOT NULL, answer TEXT NOT NULL,
        correct INTEGER NOT NULL, elapsed_ms INTEGER NOT NULL, points INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(code, round_no, username))""",
    """CREATE TABLE IF NOT EXISTS eco_party_balloon (
        code TEXT NOT NULL, round_no INTEGER NOT NULL, username TEXT NOT NULL, inflation INTEGER NOT NULL DEFAULT 0,
        exploded INTEGER NOT NULL DEFAULT 0, stopped INTEGER NOT NULL DEFAULT 0, updated_ms INTEGER NOT NULL,
        PRIMARY KEY(code, round_no, username))""",
]

def migrate(con):
    for sql in SCHEMA: con.execute(sql)
    con.commit()

def _room(row):
    if not row: return None
    d = dict(row); d['snapshot'] = json.loads(d['snapshot']); return d

def get_room(con, code):
    return _room(con.execute('SELECT * FROM eco_party_rooms WHERE code=?', ((code or '').strip(),)).fetchone())

def create_room(con, host, display, rounds=8, seconds=15):
    if not 3 <= int(rounds) <= 12: raise ValueError('Elige entre 3 y 12 minijuegos.')
    if not 8 <= int(seconds) <= 45: raise ValueError('Cada reto debe durar entre 8 y 45 segundos.')
    rng = engine.seeded_rng('ecoparty', host, engine.now_ms(), secrets.token_hex(4))
    questions = list(GAMES); rng.shuffle(questions); snapshot = questions[:int(rounds)]
    code = None
    for _ in range(40):
        candidate = f'{secrets.randbelow(900000)+100000}'
        if not con.execute('SELECT 1 FROM eco_party_rooms WHERE code=?', (candidate,)).fetchone(): code = candidate; break
    if not code: raise RuntimeError('No se pudo generar un PIN único. Intenta de nuevo.')
    now = engine.now_ms()
    con.execute('INSERT INTO eco_party_rooms(code,title,host,rounds,seconds,snapshot,created_ms) VALUES(?,?,?,?,?,?,?)',
                (code, 'EcoParty · Reto de fiesta', host, int(rounds), int(seconds), json.dumps(snapshot, ensure_ascii=False), now))
    con.execute('INSERT INTO eco_party_players(code,username,display,joined_ms) VALUES(?,?,?,?)', (code, host, display[:40], now))
    con.commit(); return code

def join(con, code, username, display):
    room = get_room(con, code)
    if not room: return 'no_room'
    if room['status'] != 'lobby': return 'started'
    exists = con.execute('SELECT 1 FROM eco_party_players WHERE code=? AND username=?', (room['code'], username)).fetchone()
    count = con.execute('SELECT COUNT(*) FROM eco_party_players WHERE code=?', (room['code'],)).fetchone()[0]
    if not exists and count >= MAX_PLAYERS: return 'full'
    con.execute('INSERT INTO eco_party_players(code,username,display,joined_ms) VALUES(?,?,?,?) ON CONFLICT(code,username) DO UPDATE SET display=excluded.display',
                (room['code'], username, display[:40], engine.now_ms()))
    con.commit(); return 'ok'

def players(con, code):
    return [dict(r) for r in con.execute('SELECT * FROM eco_party_players WHERE code=? ORDER BY joined_ms', (code,))]

def start(con, code, host):
    con.execute("UPDATE eco_party_rooms SET status='question',round_no=1,phase_started_ms=? WHERE code=? AND host=? AND status='lobby'",
                (engine.now_ms(), code, host)); con.commit()
    return get_room(con, code)

def submit(con, code, username, answer, now=None):
    room = get_room(con, code)
    if not room or room['status'] != 'question': return 'closed'
    if not con.execute('SELECT 1 FROM eco_party_players WHERE code=? AND username=?', (code, username)).fetchone(): return 'not_player'
    elapsed = (engine.now_ms() if now is None else now) - room['phase_started_ms']
    if elapsed > room['seconds'] * 1000: return 'late'
    q = room['snapshot'][room['round_no']-1]
    correct = answer == q['answer']
    points = (100 + max(0, int(50 * (1 - max(0, elapsed)/(room['seconds']*1000))))) if correct else 0
    try:
        con.execute('INSERT INTO eco_party_answers(code,round_no,username,answer,correct,elapsed_ms,points) VALUES(?,?,?,?,?,?,?)',
                    (code, room['round_no'], username, str(answer)[:180], int(correct), max(0, elapsed), points))
        con.execute('UPDATE eco_party_players SET points=points+? WHERE code=? AND username=?', (points, code, username)); con.commit()
    except sqlite3.IntegrityError:
        con.rollback(); return 'duplicate'
    return 'ok'

def tick(con, code, now=None):
    """Avanza fases en servidor; las llamadas repetidas de los jugadores son idempotentes."""
    now = engine.now_ms() if now is None else now
    room = get_room(con, code)
    if not room or room['status'] not in ('question', 'reveal'):
        return room
    if room['status'] == 'question':
        answered = con.execute('SELECT COUNT(*) FROM eco_party_answers WHERE code=? AND round_no=?', (code, room['round_no'])).fetchone()[0]
        total = con.execute('SELECT COUNT(*) FROM eco_party_players WHERE code=?', (code,)).fetchone()[0]
        if now < room['phase_started_ms'] + room['seconds']*1000 and answered < total:
            return room
    elif now < room['phase_started_ms'] + 3500:
        return room
    # Bloqueo y relectura para evitar que dos navegadores avancen la misma fase.
    con.execute('BEGIN IMMEDIATE') if not con.in_transaction else None
    room = get_room(con, code)
    if room and room['status'] == 'question':
        answered = con.execute('SELECT COUNT(*) FROM eco_party_answers WHERE code=? AND round_no=?', (code, room['round_no'])).fetchone()[0]
        total = con.execute('SELECT COUNT(*) FROM eco_party_players WHERE code=?', (code,)).fetchone()[0]
        if now >= room['phase_started_ms'] + room['seconds']*1000 or answered >= total:
            con.execute("UPDATE eco_party_rooms SET status='reveal',phase_started_ms=? WHERE code=? AND status='question'", (now, code))
    elif room and room['status'] == 'reveal' and now >= room['phase_started_ms'] + 3500:
        if room['round_no'] >= room['rounds']:
            con.execute("UPDATE eco_party_rooms SET status='finished',finished_ms=? WHERE code=? AND status='reveal'", (now, code))
        else:
            con.execute("UPDATE eco_party_rooms SET status='question',round_no=round_no+1,phase_started_ms=? WHERE code=? AND status='reveal'", (now, code))
    con.commit()
    return get_room(con, code)

def leaderboard(con, code):
    return [dict(r) for r in con.execute('SELECT display,username,points FROM eco_party_players WHERE code=? ORDER BY points DESC,joined_ms ASC', (code,))]

def my_answer(con, code, round_no, username):
    r = con.execute('SELECT * FROM eco_party_answers WHERE code=? AND round_no=? AND username=?', (code, round_no, username)).fetchone()
    return dict(r) if r else None


def balloon_state(con, code, round_no, username):
    row = con.execute("SELECT * FROM eco_party_balloon WHERE code=? AND round_no=? AND username=?", (code, round_no, username)).fetchone()
    return dict(row) if row else {"inflation": 0, "exploded": 0, "stopped": 0}

def balloon_pump(con, code, username, amount=1):
    """Applies one user action; the server owns the pressure and explosion rule."""
    room = get_room(con, code)
    if not room or room["status"] != "question": return "closed"
    if not con.execute("SELECT 1 FROM eco_party_players WHERE code=? AND username=?", (code, username)).fetchone(): return "not_player"
    q = room["snapshot"][room["round_no"]-1]
    if q.get("type") != "balloon": return "not_balloon"
    if engine.now_ms() > room["phase_started_ms"] + room["seconds"]*1000: return "late"
    current = balloon_state(con, code, room["round_no"], username)
    if current["stopped"]: return "stopped"
    amount = max(1, min(3, int(amount)))
    value = min(110, current["inflation"] + amount * 4)
    exploded = int(value >= 100)
    con.execute("INSERT INTO eco_party_balloon(code,round_no,username,inflation,exploded,stopped,updated_ms) VALUES(?,?,?,?,?,0,?) ON CONFLICT(code,round_no,username) DO UPDATE SET inflation=excluded.inflation,exploded=MAX(eco_party_balloon.exploded,excluded.exploded),updated_ms=excluded.updated_ms", (code, room["round_no"], username, value, exploded, engine.now_ms()))
    con.commit()
    return "exploded" if exploded else "ok"

def balloon_stop(con, code, username):
    room = get_room(con, code)
    if not room or room["status"] != "question": return "closed"
    if not con.execute("SELECT 1 FROM eco_party_players WHERE code=? AND username=?", (code, username)).fetchone(): return "not_player"
    q = room["snapshot"][room["round_no"]-1]
    if q.get("type") != "balloon": return "not_balloon"
    state = balloon_state(con, code, room["round_no"], username)
    if state["stopped"]: return "duplicate"
    # Target zone is 68-82%; closest to 75% wins. Exploding yields zero points.
    points = 0 if state["exploded"] else max(0, 100 - abs(state["inflation"] - 75) * 4)
    try:
        con.execute("INSERT INTO eco_party_answers(code,round_no,username,answer,correct,elapsed_ms,points) VALUES(?,?,?,?,?,?,?)", (code, room["round_no"], username, str(state["inflation"]), int(not state["exploded"] and 68 <= state["inflation"] <= 82), max(0, engine.now_ms()-room["phase_started_ms"]), points))
        con.execute("UPDATE eco_party_players SET points=points+? WHERE code=? AND username=?", (points, code, username))
        con.execute("UPDATE eco_party_balloon SET stopped=1,updated_ms=? WHERE code=? AND round_no=? AND username=?", (engine.now_ms(), code, room["round_no"], username))
        con.commit()
    except sqlite3.IntegrityError:
        con.rollback(); return "duplicate"
    return "ok"
