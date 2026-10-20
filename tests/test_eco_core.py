# -*- coding: utf-8 -*-
"""Pruebas del núcleo ampliado (no requieren Streamlit). Se ejecutan con pytest o con tests/run_standalone.py."""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eco import arena, engine, seed, store  # noqa: E402


def make_db():
    path = Path(tempfile.mkdtemp()) / "t.sqlite3"

    def connect():
        con = sqlite3.connect(path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=15000")
        return con

    store.configure(connect)
    con = connect()
    store.migrate(con)
    return con, connect


def right(q):
    kind = q["qtype"]
    if kind == "mcq":
        return q["correct"]
    if kind == "tf":
        return "Verdadero" if q["correct"] else "Falso"
    if kind == "image":
        return q["correct"]
    return {a: b for a, b in q["pairs"]}


def wrong(q):
    kind = q["qtype"]
    if kind == "mcq":
        return q["wrong"][0]
    if kind == "tf":
        return "Falso" if q["correct"] else "Verdadero"
    if kind == "image":
        return "b" if q["correct"] == "a" else "a"
    pairs = list(q["pairs"])
    return {pairs[0][0]: pairs[1][1], pairs[1][0]: pairs[0][1], **{a: b for a, b in pairs[2:]}}


def make_room(con, host="prof", mode="aula", rounds=3, seconds=10, tie_ms=0, **kw):
    return arena.create_room(con, host, title="Prueba", mode=mode, category=kw.get("category"), level=kw.get("level", "Mixta"),
                             qtypes=kw.get("qtypes", ["mcq", "tf"]), rounds=rounds, seconds=seconds, tie_ms=tie_ms)


# ── Motor ─────────────────────────────────────────────────────────────────────
def test_present_is_deterministic_and_differs_between_users():
    q = {"id": 1, "qtype": "mcq", "prompt": "x" * 10, "correct": "A", "wrong": ["B", "C", "D"]}
    assert engine.present(q, "sala", "ana") == engine.present(q, "sala", "ana")
    orders = {tuple(engine.present(q, "sala", f"user{i}")["options"]) for i in range(40)}
    assert len(orders) > 6          # los estudiantes ven órdenes distintos
    assert all(sorted(o) == ["A", "B", "C", "D"] for o in orders)


def test_check_each_type_by_value_not_position():
    assert engine.check({"qtype": "mcq", "correct": "A", "wrong": ["B", "C"]}, "A")
    assert not engine.check({"qtype": "mcq", "correct": "A", "wrong": ["B", "C"]}, "B")
    assert not engine.check({"qtype": "mcq", "correct": "A", "wrong": ["B", "C"]}, 0)
    assert engine.check({"qtype": "tf", "correct": False}, "Falso")
    assert not engine.check({"qtype": "tf", "correct": False}, "Verdadero")
    assert not engine.check({"qtype": "tf", "correct": True}, "True")
    assert engine.check({"qtype": "image", "correct": "b"}, "b")
    pairs = [("a", "1"), ("b", "2"), ("c", "3")]
    assert engine.check({"qtype": "match", "pairs": pairs}, {"a": "1", "b": "2", "c": "3"})
    assert not engine.check({"qtype": "match", "pairs": pairs}, {"a": "2", "b": "1", "c": "3"})
    assert not engine.check({"qtype": "match", "pairs": pairs}, {"a": "1", "b": "2"})
    assert not engine.check({"qtype": "match", "pairs": pairs}, "a1b2c3")


def test_score_decreases_with_time_and_level_matters():
    fast = engine.score_answer("Fácil", 0, 10_000, True)
    slow = engine.score_answer("Fácil", 9_000, 10_000, True)
    assert fast == 100 and 50 <= slow < fast
    assert engine.score_answer("Experto", 0, 10_000, True) > fast
    assert engine.score_answer("Fácil", 0, 10_000, False) == 0
    assert engine.score_answer("Fácil", 99_000, 10_000, True) == 50


def test_resolve_round_ties():
    a = [{"username": "ana", "correct": True, "t_ms": 1000}, {"username": "beto", "correct": True, "t_ms": 1001},
         {"username": "caro", "correct": False, "t_ms": 900}]
    assert engine.resolve_round(a) == {"fastest": ["ana"], "tie": False}
    a[1]["t_ms"] = 1000
    assert engine.resolve_round(a) == {"fastest": ["ana", "beto"], "tie": True}
    a[1]["t_ms"] = 1004
    assert engine.resolve_round(a, tie_ms=5)["tie"] is True
    assert engine.resolve_round(a, tie_ms=3)["tie"] is False
    assert engine.resolve_round([{"username": "x", "correct": False, "t_ms": 1}]) == {"fastest": [], "tie": False}


# ── Banco ─────────────────────────────────────────────────────────────────────
def test_seed_is_valid_complete_and_idempotent():
    con, _ = make_db()
    n = con.execute("SELECT COUNT(*) FROM eco_questions").fetchone()[0]
    assert n >= 140
    store.migrate(con)
    assert con.execute("SELECT COUNT(*) FROM eco_questions").fetchone()[0] == n
    for cat in engine.CATEGORIES:
        for lvl in engine.LEVELS:
            for qt in engine.QTYPES:
                assert store.list_questions(con, categories=[cat], levels=[lvl], qtypes=[qt]), (cat, lvl, qt)
    for q in store.list_questions(con):
        assert store.validate(q) == [], q["prompt"]


def test_validation_rejects_bad_questions():
    base = {"category": "Clima", "level": "Fácil", "qtype": "mcq", "prompt": "¿Pregunta de prueba válida?", "correct": "A", "wrong": ["B", "C"]}
    assert store.validate(base) == []
    assert store.validate({**base, "wrong": ["B"]})
    assert store.validate({**base, "wrong": ["a", "C"]})            # repetida (sin distinguir mayúsculas)
    assert store.validate({**base, "prompt": "corto"})
    assert store.validate({**base, "level": "Imposible"})
    assert store.validate({"category": "Clima", "level": "Fácil", "qtype": "tf", "prompt": "Afirmación válida aquí.", "correct": "si"})
    assert store.validate({"category": "Clima", "level": "Fácil", "qtype": "match", "prompt": "Une las parejas.", "pairs": [("a", "1"), ("b", "2")]})
    assert store.validate({"category": "Clima", "level": "Fácil", "qtype": "image", "prompt": "¿Cuál es correcta?",
                           "a": {"emoji": "🌳", "label": "Árbol"}, "b": {"emoji": "🌳", "label": "árbol"}, "correct": "a"})


def test_crud_persists_and_respects_ownership():
    con, connect = make_db()
    q = {"category": "Energía", "level": "Avanzado", "qtype": "mcq", "prompt": "¿Qué mide un kilovatio-hora?",
         "correct": "Energía", "wrong": ["Potencia", "Tensión"], "explanation": "kWh es energía."}
    qid = store.add_question(con, q, owner="prof1", actor="prof1")
    con2 = connect()                                    # otra conexión ve el cambio: persistente
    got = store.get_question(con2, qid)
    assert got["owner"] == "prof1" and got["correct"] == "Energía"
    assert store.can_edit(got, "prof1", "teacher") and not store.can_edit(got, "prof2", "teacher") and store.can_edit(got, "x", "admin")
    store.update_question(con, qid, {**q, "level": "Experto", "correct": "Energía eléctrica"}, "prof1")
    assert store.get_question(con2, qid)["level"] == "Experto"
    store.set_active(con, qid, False, "prof1")
    assert store.list_questions(con2, owners=["prof1"], active=True) == []
    store.delete_question(con, qid)
    assert store.get_question(con2, qid) is None


def test_import_export_roundtrip_and_errors():
    con, _ = make_db()
    sample = store.list_questions(con, categories=["Clima"], levels=["Fácil"])
    text = store.export_json(sample)
    ok, problems = store.import_json(con, text, owner="prof9", actor="prof9")
    assert ok == len(sample) and not problems
    ok, problems = store.import_json(con, json.dumps([{"category": "Clima"}, "x"]), owner="prof9", actor="prof9")
    assert ok == 0 and len(problems) == 2
    assert store.import_json(con, "no es json", "p", "p")[0] == 0


def test_pick_never_repeats_until_pool_is_exhausted_then_cycles():
    con, _ = make_db()
    kw = dict(categories=["Océanos"], levels=["Fácil"], qtypes=["mcq", "tf"], owners=["*"])
    pool = len(store.list_questions(con, categories=["Océanos"], levels=["Fácil"], qtypes=["mcq", "tf"], active=True))
    seen_ids = []
    first, cyc = store.pick_for_user(con, "ana", n=3, **kw)
    assert not cyc and len(first) == 3
    for q in first:
        store.mark_seen(con, "ana", q["id"], True)
    seen_ids += [q["id"] for q in first]
    second, cyc = store.pick_for_user(con, "ana", n=3, **kw)
    assert not set(q["id"] for q in second) & set(seen_ids)
    for q in second:
        store.mark_seen(con, "ana", q["id"], False)
    # agotar el banco
    rest, _ = store.pick_for_user(con, "ana", n=pool - 6, **kw)
    for q in rest:
        store.mark_seen(con, "ana", q["id"], True)
    again, cyc = store.pick_for_user(con, "ana", n=4, **kw)
    assert cyc and len(again) == 4                      # ya vio todo: reinicia con las más antiguas
    other, cyc = store.pick_for_user(con, "beto", n=3, **kw)
    assert not cyc                                      # el historial es por estudiante


def test_different_students_get_different_quizzes():
    con, _ = make_db()
    sets = {tuple(sorted(q["id"] for q in store.pick_for_user(con, f"u{i}", categories=["Clima"], levels=["Fácil", "Intermedio"],
                                                              qtypes=["mcq"], n=6, owners=["*"])[0])) for i in range(12)}
    assert len(sets) > 6


def test_pick_mixed_rises_in_difficulty():
    con, _ = make_db()
    qs, _ = store.pick_mixed(con, "ana", categories=["Energía"], qtypes=["mcq", "tf"], n=8, owners=["*"])
    order = [engine.LEVELS.index(q["level"]) for q in qs]
    assert order == sorted(order) and len(qs) == 8 and set(order) == {0, 1, 2, 3}


def test_availability_switches():
    con, _ = make_db()
    con.execute("CREATE TABLE IF NOT EXISTS eco_student_grants (teacher TEXT, student TEXT, game TEXT)")
    con.execute("INSERT INTO eco_student_grants VALUES('prof1','est1','x')")
    con.execute("INSERT INTO eco_student_grants VALUES('prof2','est1','x')")
    con.commit()
    assert store.availability(con, "est1", "student")("level", "Experto")
    store.set_pref(con, "prof1", "level", "Experto", False)
    assert store.availability(con, "est1", "student")("level", "Experto")           # prof2 aún lo permite
    store.set_pref(con, "prof2", "level", "Experto", False)
    assert not store.availability(con, "est1", "student")("level", "Experto")
    assert store.availability(con, "solo", "student")("level", "Experto")           # sin docente: ve todo
    assert not store.availability(con, "prof1", "teacher")("level", "Experto")
    store.set_pref(con, "*", "game", "arena", False)                                # el administrador manda
    assert not store.availability(con, "est1", "student")("game", "arena")
    assert not store.availability(con, "prof1", "teacher")("game", "arena")
    assert store.availability(con, "admin", "admin")("level", "Experto")
    assert "prof1" in store.visible_owners(con, "est1", "student") and "prof2" in store.visible_owners(con, "est1", "student")


# ── Arena ─────────────────────────────────────────────────────────────────────
def setup_room(con, names=("ana", "beto", "caro"), **kw):
    code = make_room(con, **kw)
    for n in names:
        assert arena.join(con, code, n, n.title()) == "ok"
    return code


def test_room_creation_snapshot_and_errors():
    con, _ = make_db()
    code = make_room(con, rounds=5)
    room = arena.get_room(con, code)
    assert len(code) == 6 and code.isdigit() and room["status"] == "lobby"
    assert len(room["snapshot"]) == 5 + engine.MAX_REPLAYS
    assert [engine.LEVELS.index(q["level"]) for q in room["snapshot"][:5]] == sorted(engine.LEVELS.index(q["level"]) for q in room["snapshot"][:5])
    for bad in (dict(rounds=1), dict(seconds=1), dict(qtypes=["nada"]), dict(mode="x")):
        try:
            arena.create_room(con, "prof", **{**dict(title="x", mode="aula", category=None, level="Mixta", qtypes=["mcq"], rounds=3, seconds=10), **bad})
        except ValueError:
            continue
        raise AssertionError(bad)
    try:
        make_room(con, rounds=20, category="Clima", level="Fácil", qtypes=["image"])
    except ValueError as exc:
        assert "preguntas disponibles" in str(exc)
    else:
        raise AssertionError("debió fallar por falta de preguntas")


def test_second_room_by_same_host_avoids_questions_already_used():
    con, _ = make_db()
    a = {q["id"] for q in arena.get_room(con, make_room(con, rounds=6, level="Fácil", qtypes=["mcq", "tf"]))["snapshot"][:6]}
    b = {q["id"] for q in arena.get_room(con, make_room(con, rounds=6, level="Fácil", qtypes=["mcq", "tf"]))["snapshot"][:6]}
    assert not a & b


def test_normal_round_scoring_speed_bonus_and_advance():
    con, _ = make_db()
    code = setup_room(con)
    assert arena.start(con, "otro", 1) is False and arena.start(con, code, "prof", 1_000_000)
    q = arena.current_question(arena.get_room(con, code))
    assert arena.submit(con, code, "ana", right(q), 1_002_000) == "ok"
    assert arena.submit(con, code, "ana", wrong(q), 1_002_500) == "dup"
    assert arena.submit(con, code, "beto", right(q), 1_003_000) == "ok"
    assert arena.tick(con, code, 1_003_100)["status"] == "question"      # falta caro
    assert arena.submit(con, code, "caro", wrong(q), 1_004_000) == "ok"
    room = arena.tick(con, code, 1_004_100)                              # todos respondieron: cierra sin esperar
    assert room["status"] == "reveal" and room["last_result"]["fastest"] == ["ana"] and not room["last_result"]["tie"]
    board = {p["username"]: p for p in arena.leaderboard(con, code)}
    base = lambda ms: engine.score_answer(q["level"], ms, 10_000, True)
    assert board["ana"]["points"] == base(2000) + engine.REFLEX_BONUS
    assert board["beto"]["points"] == base(3000) and board["caro"]["points"] == 0
    assert [p["username"] for p in arena.leaderboard(con, code)] == ["ana", "beto", "caro"]
    assert arena.submit(con, code, "ana", right(q), 1_004_200) == "closed"
    assert arena.tick(con, code, 1_004_100 + 3000)["status"] == "reveal"  # aún dentro del tiempo de resultados
    room = arena.tick(con, code, 1_004_100 + 7000)
    assert room["status"] == "question" and room["round_no"] == 2 and room["replay"] == 0


def test_tick_is_idempotent_across_connections():
    con, connect = make_db()
    code = setup_room(con, names=("ana", "beto"))
    arena.start(con, code, "prof", 1000)
    q = arena.current_question(arena.get_room(con, code))
    arena.submit(con, code, "ana", right(q), 1500)
    other = connect()
    arena.tick(other, code, 1000 + 10_000 + 1)
    arena.tick(con, code, 1000 + 10_000 + 1)
    arena.tick(other, code, 1000 + 10_000 + 2)
    pts = con.execute("SELECT points FROM eco_players WHERE code=? AND username='ana'", (code,)).fetchone()[0]
    assert pts == engine.score_answer(q["level"], 500, 10_000, True) + engine.REFLEX_BONUS   # no se duplicó
    assert arena.get_room(con, code)["status"] == "reveal"


def test_deadline_closes_round_with_no_answers_and_late_is_rejected():
    con, _ = make_db()
    code = setup_room(con)
    arena.start(con, code, "prof", 0)
    q = arena.current_question(arena.get_room(con, code))
    assert arena.submit(con, code, "ana", right(q), 10_001) == "late"
    room = arena.tick(con, code, 10_000)
    assert room["status"] == "reveal" and room["last_result"]["no_correct"]
    assert arena.submit(con, "999999", "ana", "x") == "closed"
    assert arena.submit(con, code, "intruso", "x", 1) == "closed"


def test_exact_tie_replays_round_between_tied_players_only():
    con, _ = make_db()
    code = setup_room(con, tie_ms=0)
    arena.start(con, code, "prof", 0)
    q1 = arena.current_question(arena.get_room(con, code))
    arena.submit(con, code, "ana", right(q1), 2000)
    arena.submit(con, code, "beto", right(q1), 2000)            # mismo milisegundo exacto
    arena.submit(con, code, "caro", right(q1), 5000)
    room = arena.tick(con, code, 5100)
    lr = room["last_result"]
    assert lr["tie"] and lr["replay_next"] and sorted(lr["fastest"]) == ["ana", "beto"]
    pts = {p["username"]: p["points"] for p in arena.leaderboard(con, code)}
    base = lambda ms: engine.score_answer(q1["level"], ms, 10_000, True)
    assert pts["ana"] == pts["beto"] == base(2000)               # sin bono mientras haya empate
    assert pts["caro"] == base(5000)
    room = arena.tick(con, code, 5100 + 7000)                    # fin de resultados: empieza la repetición
    assert room["status"] == "question" and room["round_no"] == 1 and room["replay"] == 1 and sorted(room["eligible"]) == ["ana", "beto"]
    q2 = arena.current_question(room)
    assert q2["id"] != q1["id"]                                  # la repetición usa otra pregunta
    assert arena.submit(con, code, "caro", right(q2), 12_200) == "not_eligible"
    assert arena.submit(con, code, "beto", right(q2), 12_800) == "ok"
    assert arena.submit(con, code, "ana", right(q2), 12_500) == "ok"
    room = arena.tick(con, code, 12_900)                         # ambos respondieron: se cierra
    assert room["last_result"]["fastest"] == ["ana"] and not room["last_result"]["replay_next"]
    pts2 = {p["username"]: p["points"] for p in arena.leaderboard(con, code)}
    assert pts2["ana"] == pts["ana"] + engine.REFLEX_BONUS and pts2["beto"] == pts["beto"]   # solo el ganador suma el bono
    room = arena.tick(con, code, 12_900 + 7000)
    assert room["round_no"] == 2 and room["replay"] == 0 and room["eligible"] is None


def test_tie_replays_are_capped_and_bonus_is_split():
    con, _ = make_db()
    code = setup_room(con, names=("ana", "beto"))
    arena.start(con, code, "prof", 0)
    now = 0
    for replay in range(engine.MAX_REPLAYS + 1):
        room = arena.get_room(con, code)
        q = arena.current_question(room)
        assert room["replay"] == replay
        start = room["phase_started_ms"]
        arena.submit(con, code, "ana", right(q), start + 1000)
        arena.submit(con, code, "beto", right(q), start + 1000)
        room = arena.tick(con, code, start + 1100)
        now = start + 1100
        if replay < engine.MAX_REPLAYS:
            assert room["last_result"]["replay_next"]
            room = arena.tick(con, code, now + 7000)
            assert room["status"] == "question"
        else:
            assert not room["last_result"]["replay_next"] and room["last_result"]["tie"]
    pts = {p["username"]: p["points"] for p in arena.leaderboard(con, code)}
    assert pts["ana"] == pts["beto"]
    assert con.execute("SELECT COALESCE(SUM(points),0) FROM eco_answers WHERE code=? AND round_key='1.3'", (code,)).fetchone()[0] == engine.REFLEX_BONUS


def test_tie_window_makes_near_simultaneous_answers_tie():
    con, _ = make_db()
    code = setup_room(con, names=("ana", "beto"), tie_ms=10)
    arena.start(con, code, "prof", 0)
    q = arena.current_question(arena.get_room(con, code))
    arena.submit(con, code, "ana", right(q), 1000)
    arena.submit(con, code, "beto", right(q), 1008)
    assert arena.tick(con, code, 1100)["last_result"]["tie"]


def test_full_game_finishes_and_exports_results():
    con, _ = make_db()
    code = setup_room(con, rounds=3)
    arena.start(con, code, "prof", 0)
    t = 0
    for n in range(3):
        room = arena.get_room(con, code)
        q = arena.current_question(room)
        s = room["phase_started_ms"]
        arena.submit(con, code, "ana", right(q), s + 500)
        arena.submit(con, code, "beto", wrong(q), s + 600)
        arena.submit(con, code, "caro", right(q), s + 900)
        arena.tick(con, code, s + 1000)
        room = arena.skip(con, code, "prof", s + 1100)           # el anfitrión salta los resultados
        t = s + 1100
    assert room["status"] == "finished"
    board = arena.leaderboard(con, code)
    assert board[0]["username"] == "ana" and board[0]["correct"] == 3 and board[-1]["username"] == "beto"
    csv_text = arena.results_csv(con, code)
    assert csv_text.splitlines()[0].startswith("Posición") and "Ana" in csv_text
    assert arena.join(con, code, "tarde", "Tarde") == "finished"


def test_skip_only_for_host_and_join_rules():
    con, _ = make_db()
    code = setup_room(con, names=("ana",))
    arena.start(con, code, "prof", 0)
    assert arena.skip(con, code, "ana", 100)["status"] == "question"       # un estudiante no puede forzar el cierre
    assert arena.skip(con, code, "prof", 100)["status"] == "reveal"
    assert arena.join(con, "000000", "x", "X") == "no_room"


def test_team_modes_require_team_and_rank_by_average():
    con, _ = make_db()
    code = make_room(con, mode="colegio")
    assert arena.join(con, code, "ana", "Ana") == "team_required"
    assert arena.join(con, code, "ana", "Ana", "  colegio  norte ") == "ok"
    for n, team in (("b1", "Colegio Sur"), ("b2", "Colegio Sur"), ("b3", "Colegio Sur")):
        arena.join(con, code, n, n, team)
    con.execute("UPDATE eco_players SET points=300 WHERE username='ana'")
    con.execute("UPDATE eco_players SET points=150 WHERE username IN ('b1','b2','b3')")
    con.commit()
    board = arena.team_board(con, code)
    assert [t["team"] for t in board] == ["Colegio Norte", "Colegio Sur"]       # promedio, no suma (Sur suma 450 pero promedia 150)
    assert board[0]["avg"] == 300 and board[1]["points"] == 450
    solo = make_room(con, mode="aula")
    arena.join(con, solo, "x", "X", "ignorado")
    assert arena.players(con, solo)[0]["team"] == ""

# ── EcoParty: salas de fiesta de hasta 12 jugadores ───────────────────────────
def test_ecoparty_online_room_capacity_scoring_and_round_progression():
    from eco import party
    con, connect = make_db()
    try:
        party.migrate(con)
        code = party.create_room(con, "host", "Anfitrión", rounds=3, seconds=10)
        assert party.join(con, code, "host", "Anfitrión") == "ok"
        for i in range(1, 12):
            assert party.join(con, code, f"p{i}", f"Jugador {i}") == "ok"
        assert len(party.players(con, code)) == 12
        assert party.join(con, code, "overflow", "Jugador extra") == "full"
        room = party.start(con, code, "host")
        assert room["status"] == "question" and room["round_no"] == 1
        q = room["snapshot"][0]
        assert party.submit(con, code, "p1", q["answer"], room["phase_started_ms"] + 500) == "ok"
        assert party.submit(con, code, "p1", q["answer"], room["phase_started_ms"] + 600) == "duplicate"
        assert party.leaderboard(con, code)[0]["points"] > 0
        # Deadline closes the first round and advances exactly one round.
        room = party.tick(con, code, room["phase_started_ms"] + room["seconds"] * 1000 + 1)
        assert room["round_no"] == 1 and room["status"] == "reveal"
        room = party.tick(con, code, room["phase_started_ms"] + 3501)
        assert room["round_no"] == 2 and room["status"] == "question"
    finally:
        con.close()


def test_ecoparty_rejects_answers_from_nonplayers_and_finished_room():
    from eco import party
    con, connect = make_db()
    try:
        code = party.create_room(con, "host", "Anfitrión", rounds=3, seconds=10)
        party.start(con, code, "host")
        room = party.get_room(con, code)
        assert party.submit(con, code, "stranger", "x", room["phase_started_ms"] + 1) == "not_player"
        for _ in range(3):
            room = party.get_room(con, code)
            room = party.tick(con, code, room["phase_started_ms"] + room["seconds"] * 1000 + 1)
            assert room["status"] == "reveal"
            room = party.tick(con, code, room["phase_started_ms"] + 3501)
        assert room["status"] == "finished"
        assert party.submit(con, code, "host", "x") == "closed"
    finally:
        con.close()


def test_ecoparty_does_not_include_balloon_bash():
    from eco import party
    assert len(party.GAMES) >= 10
    assert all(q.get("type") != "balloon" and q.get("id") != "globo" for q in party.GAMES)
