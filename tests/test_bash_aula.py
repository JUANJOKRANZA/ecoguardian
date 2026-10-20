# -*- coding: utf-8 -*-
"""Balloon Bash (modo aula integrado), EcoRunner y narrador. Se ejecuta con pytest o tests/run_standalone.py."""
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))

from eco import bash_game as bg  # noqa: E402
from eco import voice  # noqa: E402
import test_smoke_ui as ui  # noqa: E402

WEB = HERE.parent / "eco" / "web"


def mkroom(mode="ffa", names=("Pedro", "Luisa", "Juan", "Ana"), seed=1):
    r = bg.Room("4829", "prof1", random.Random(seed)); r.mode = mode
    for n in names:
        r.join(n.lower(), n)
    return r


def inflate(r, t=100.0):
    r.start(t); r.tick(t + bg.MEMORIZE_S + .01)
    return t + bg.MEMORIZE_S + .01


def has_key(o, bad):
    if isinstance(o, dict):
        return any(k in bad or has_key(v, bad) for k, v in o.items())
    if isinstance(o, list):
        return any(has_key(v, bad) for v in o)
    return False


# ── lógica ───────────────────────────────────────────────────────────────────
def test_four_lanes_and_resources():
    r = mkroom(); s = r.snapshot(now=1.0)
    assert [l["resName"] for l in s["lanes"]] == ["Hoja", "Gota de Agua", "Cesto de Reciclaje", "Bombilla"]
    assert [l["players"] for l in s["lanes"]] == [["Pedro"], ["Luisa"], ["Juan"], ["Ana"]]


def test_memorize_then_blind_inflate_no_leaks():
    r = mkroom(); r.start(10.0)
    s = r.snapshot(now=10.5)
    assert s["phase"] == "memorize" and 3 <= s["memorizeDur"] <= 5 and r.ann["text"] == "¡Memoriza el tamaño!"
    assert all("tscale" in l for l in s["lanes"])
    t = inflate(r, 20.0)
    assert r.ann["text"] == "¡A inflar!"
    for i in range(8):
        r.pump("pedro", 3, .8, now=t + i * .3)
    s = r.snapshot(now=t + 3)
    assert s["phase"] == "inflate"
    assert not has_key(s, {"tscale", "pct", "air", "capacity", "score", "result"})      # silueta y números ocultos
    view = r.player_view("pedro")
    assert not has_key(view, {"tscale", "pct", "air", "size", "score", "capacity", "result"})


def test_pop_and_reveal_and_danger():
    r = mkroom(); t = inflate(r)
    ln = r.lanes[0]; ln.air = ln.capacity * .84; assert not ln.danger
    ln.air = ln.capacity * .86; assert ln.danger
    for i in range(60):
        r.pump("pedro", 6, 1, now=t + i)
        if ln.done:
            break
    assert ln.popped
    res = r.snapshot(now=t + 70)["lanes"][0]["result"]
    assert res["popped"] and res["score"] == 0 and res["label"] == "¡POPPING!" and res["pct"] >= 108


def test_brake_scoring_and_double_registration():
    assert bg.score_for(100, False) == 100 and bg.score_for(90, False) == 70 and bg.score_for(120, True) == 0
    r = mkroom(); t = inflate(r)
    r.pump("luisa", 4, .5, now=t + 1)
    assert r.brake("luisa", t + 2) and not r.brake("luisa", t + 3)
    assert r.leaderboard()[0]["points"] == r.totals[1]


def test_timeout_reveal_and_full_game():
    r = mkroom(); now = 0.0; r.start(now); seen = set()
    for _ in range(3000):
        now += .25; r.tick(now); seen.add(r.phase)
        if r.phase == "final":
            break
    assert {"memorize", "inflate", "reveal", "final"} <= seen and r.round_no == bg.ROUNDS
    assert r.ann["text"] == "¡Fin del juego!"


def test_anti_copy_scales_differ_per_lane():
    r = mkroom(); r.start(1.0)
    assert len({round(l.tscale, 3) for l in r.lanes}) == 4
    assert all(.88 <= l.vscale <= 1.12 for l in r.lanes) and len({round(l.capacity, 2) for l in r.lanes}) == 4


def test_relay_2v2_baton():
    r = mkroom("relay"); assert len(r.snapshot(now=1)["lanes"]) == 2 and r.lane_label(0) == "Pedro + Juan"
    t = inflate(r)
    assert r.pump("pedro", 1, .5, now=t + 1) == 1 and r.pump("juan", 1, .5, now=t + 1) == 0
    r.tick(t + bg.RELAY_SWAP_S + .1)
    assert r.ann["text"] == "¡Relevo!"
    assert r.pump("pedro", 1, .5, now=t + 5) == 0 and r.pump("juan", 1, .5, now=t + 5) == 1
    assert not r.brake("pedro", t + 5) and r.brake("juan", t + 5)


def test_batch_limits_phase_guard_and_room_limits():
    r = mkroom(); assert r.pump("pedro", 3, .5, now=5.0) == 0            # fuera de ronda
    t = inflate(r)
    assert r.pump("pedro", 99, .5, now=t + 1) == bg.MAX_BATCH
    assert r.pump("pedro", 3, .5, now=t + 1.01) == 0                      # lotes demasiado juntos
    assert not r.join("extra", "Extra")[0]
    r2 = bg.Room("1", "x"); assert not r2.join("a", "<>")[0] or bg.clean_name("<b>Ana</b>") == "bAnab"


def test_bots_and_final_scores_and_registry():
    r = bg.Room("1", "x", random.Random(3)); r.add_bots(); assert len(r.players) == 4
    now = 0.0; r.start(now)
    for _ in range(3000):
        now += .25; r.tick(now)
        if r.phase == "final":
            break
    assert r.phase == "final" and r.final_scores() == {}                  # los bots no puntúan en la base de datos
    a = bg.create_room("profesor_a"); assert bg.create_room("profesor_a") is a and bg.get_room(a.code) is a
    bg.close_room(a.code); assert bg.get_room(a.code) is None


# ── narrador ─────────────────────────────────────────────────────────────────
def test_voice_phrases_and_cleaning():
    assert "¿Cuál es la respuesta correcta?" in voice.question_line("¿Qué se recicla?", "mcq", ["Vidrio", "Pila"])
    assert "Opción A: Vidrio" in voice.question_line("¿Qué se recicla?", "mcq", ["Vidrio", "Pila"])
    q = voice.question_line("¿Cuál es más grande?", "image", sides=["Ballena", "Delfín"])
    assert "izquierda, Ballena" in q and "derecha, Delfín" in q and q.endswith("¿Cuál es la respuesta correcta?")
    assert "Verdadero o falso" in voice.question_line("Reciclar ayuda.", "tf")
    assert "9 de 10" in voice.final_line(9, 10, 90) and "90 por ciento" in voice.final_line(9, 10)
    assert voice._clean("✅ **¡Bien!** 🌿 <b>ok</b>") == "¡Bien! ok"
    assert voice.cheer(True, 3) == voice.CHEER_STREAK[3]


# ── interfaz (Streamlit simulado) ────────────────────────────────────────────
def _comp(name):
    return [kw for n, kw in ui.st.comp_calls if n == name]


def test_menu_and_host_panel_inside_platform():
    if ui.SKIP:
        return
    ui._setup(); bg._ROOMS.clear()
    html = "".join(ui.run("teacher", "prof1", "library", lib_game="inflate").html)
    assert "Salón (docente)" in html and "Unirme con PIN" in html and "🎈 Solo" in html          # menú de modos
    ui.run("teacher", "prof1", "library", lib_game="inflate", bb_mode="host")
    calls = _comp("eg_balloon_host")
    assert calls and calls[-1]["snap"]["phase"] == "lobby" and len(calls[-1]["snap"]["code"]) == 4
    room = next(iter(bg._ROOMS.values())); assert room.host == "prof1"


def test_student_joins_with_pin_and_pad_controls_the_lane():
    if ui.SKIP:
        return
    ui._setup(); bg._ROOMS.clear()
    room = bg.create_room("prof1"); room.add_bots(); room.players.pop("bot_ana")     # deja un lugar libre
    ui.run("student", "est1", "library", lib_game="inflate", bb_mode="play")
    ui.st.session_state["bb_pin_in"] = room.code
    ui.st.clicks.add("bb_join_btn"); ui.cont("student", "est1", "library")
    assert ui.st.session_state["bb_join"] == room.code and "est1" in room.players
    room.start(); room.tick(__import__("time").monotonic() + bg.MEMORIZE_S + .1)
    t0 = room.phase_end
    ui.st.comp_values[f"bb_pad_{room.code}"] = {"id": 1, "pumps": 3, "power": .8, "brake": False}
    ui.cont("student", "est1", "library")
    lane = room.lanes[room.players["est1"].lane]
    assert lane.pumps >= 3                                                           # los bombeos llegaron del celular
    view = _comp("eg_balloon_pad")[-1]["view"]
    assert view["phase"] == "inflate" and not has_key(view, {"tscale", "pct", "air", "size"})
    ui.st.comp_values[f"bb_pad_{room.code}"] = {"id": 2, "pumps": 0, "power": 0, "brake": True}
    ui.cont("student", "est1", "library")
    assert lane.done
    assert t0 > 0


def test_host_saves_scores_once_at_final():
    if ui.SKIP:
        return
    ui._setup(); bg._ROOMS.clear()
    room = bg.create_room("prof1"); room.join("est1", "Est1"); room.add_bots()
    now = 0.0; room.start(now)
    while room.phase != "final":
        now += .25; room.tick(now)
    ui.run("teacher", "prof1", "library", lib_game="inflate", bb_mode="host"); ui.cont("teacher", "prof1", "library")
    n = ui.app.db_connect().execute("SELECT COUNT(*) FROM eco_minigame WHERE username='est1' AND game='inflate'").fetchone()[0]
    assert n == 1 and room.saved


def test_quiz_games_speak_question_feedback_and_final():
    if ui.SKIP:
        return
    from eco import engine
    ui._setup()
    for game in ("duel", "tf", "mission", "match"):
        ui.run("student", "est1", "library", lib_game=game)
        ui.st.clicks.add(f"qz_{game}_start"); ui.cont("student", "est1", "library")      # crea la partida
        ui.cont("student", "est1", "library")                                            # muestra la 1.ª pregunta
        h = "".join(ui.st.html)
        assert "SpeechSynthesisUtterance" in h, game                                     # el locutor lee la pregunta
        if game == "duel":
            assert "izquierda" in h and "¿Cuál es la respuesta correcta?" in h
        s = ui.st.session_state[f"qz_{game}"]; q = s["qs"][0]
        view = engine.present(q, "est1", s["nonce"], 0)
        if q["qtype"] == "image":
            ans = next(x["id"] for x in view["sides"] if engine.check(q, x["id"]))
        elif q["qtype"] == "match":
            ans = {p[0]: p[1] for p in q["pairs"]}
        else:
            ans = engine.correct_text(q)
        ui.pages._qz_answer(f"qz_{game}", "est1", ans)
        ui.cont("student", "est1", "library")
        h2 = "".join(ui.st.html)
        assert "SpeechSynthesisUtterance" in h2 and "La respuesta correcta" not in h2.split("SpeechSynthesisUtterance")[1][:60], game   # felicita al acertar
    ui.run("student", "est1", "library", lib_game="duel")
    ui.st.clicks.add("qz_duel_start"); ui.cont("student", "est1", "library")
    s = ui.st.session_state["qz_duel"]; s["i"] = len(s["qs"])
    ui.cont("student", "est1", "library")
    assert "Fin del juego" in "".join(ui.st.html)                                        # cierre hablado


def test_narrator_can_be_muted():
    if ui.SKIP:
        return
    ui._setup()
    ui.run("student", "est1", "library", lib_game="duel", narrator_on=False)
    ui.st.clicks.add("qz_duel_start"); ui.cont("student", "est1", "library", narrator_on=False)
    ui.cont("student", "est1", "library", narrator_on=False)
    assert "SpeechSynthesisUtterance" not in "".join(ui.st.html)


def test_ecorunner_is_an_action_game_and_saves_score():
    if ui.SKIP:
        return
    ui._setup()
    from eco import runner
    ui.st.reset(); ui.st.session_state["x"] = 1
    ui.st.comp_values["eco_runner_game"] = {"id": 111, "score": 240, "hits": 12, "total": 15, "best": 6}
    runner.runner_page("est1")
    assert _comp("eg_eco_runner") and _comp("eg_eco_runner")[-1]["narrator"] is True
    assert ui.app.db_connect().execute("SELECT points FROM eco_minigame WHERE username='est1' AND game='ecorunner'").fetchone()[0] == 240
    runner.runner_page("est1")                                                       # mismo id: no duplica
    assert ui.app.db_connect().execute("SELECT COUNT(*) FROM eco_minigame WHERE game='ecorunner'").fetchone()[0] == 1
    src = (ui.HERE.parent / "app.py").read_text(encoding="utf-8")
    assert "eco_runner.runner_page(username)" in src and "eco_runner_choice" not in src


# ── componentes web ──────────────────────────────────────────────────────────
def test_web_components_exist_and_are_valid_js():
    for folder in ("balloon_host", "balloon_pad", "eco_runner"):
        html = (WEB / folder / "index.html").read_text(encoding="utf-8")
        assert "streamlit:componentReady" in html and "streamlit:render" in html
        assert "localStorage" not in html
    assert (WEB / "balloon_host" / "arcade.js").exists()
    host = (WEB / "balloon_host" / "index.html").read_text(encoding="utf-8")
    pad = (WEB / "balloon_pad" / "index.html").read_text(encoding="utf-8")
    assert "tscale" in host and "devicemotion" in pad and "navigator.vibrate" in pad and "Frenar" in pad
    assert "silhouette" not in pad.lower() and "pct" not in pad                       # el móvil no dibuja silueta ni %
    assert "speechSynthesis" in (WEB / "balloon_host" / "arcade.js").read_text(encoding="utf-8")
    if shutil.which("node"):
        for folder in ("balloon_host", "balloon_pad", "eco_runner"):
            js = re.findall(r"<script>(.*?)</script>", (WEB / folder / "index.html").read_text(encoding="utf-8"), re.S)[-1]
            tmp = Path("/tmp") / f"{folder}_check.js"; tmp.write_text(js, encoding="utf-8")
            assert subprocess.run(["node", "--check", str(tmp)], capture_output=True).returncode == 0, folder


def test_no_external_server_left():
    root = HERE.parent
    assert not (root / "balloon_bash").exists() and not list(root.glob("iniciar_balloon_bash.*"))


def test_eco_reto_en_vivo_narrates_question_feedback_and_final():
    if ui.SKIP:
        return
    import time
    ui._setup()
    qs = [dict(q) for q in ui.app.ECO_RETO_QUESTIONS[:2]]
    key = "eco_reto_live_admin_admin1"
    game = {"questions": qs, "pos": 0, "hits": 0, "points": 0, "answers": [], "started": time.time(), "question_started": time.time(), "seconds": 20, "topic": "Todas", "mode": "Mixto"}
    ui.run("admin", "admin1", "library", lib_game="legacy:EcoReto en Vivo", **{key: game})
    h = "".join(ui.st.html)
    assert "SpeechSynthesisUtterance" in h and "respuesta correcta" in h
    q = qs[0]
    game["answers"].append({"question": q["q"], "chosen": q["answer"], "answer": q["answer"], "correct": True, "why": q["why"], "points": 100})
    game["last_result"] = {"correct": True, "gained": 100, "why": q["why"], "answer": q["answer"]}
    ui.cont("admin", "admin1", "library")
    assert "SpeechSynthesisUtterance" in "".join(ui.st.html)
    game["pos"] = len(qs); game.pop("last_result"); game["done"] = True
    ui.cont("admin", "admin1", "library")
    assert "Fin del juego" in "".join(ui.st.html)
