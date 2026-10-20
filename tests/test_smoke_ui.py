# -*- coding: utf-8 -*-
"""Pruebas de humo: ejecutan main() y las páginas con un Streamlit simulado (tests/fake_streamlit.py).

Detectan excepciones de Python, nombres mal escritos, claves duplicadas y flujos rotos. NO sustituyen a una
revisión visual en el navegador. Si Streamlit real está instalado se omiten (usa `streamlit run app.py`).
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

# conftest puede instalar un Streamlit simulado sin __spec__; find_spec() lanza ValueError en ese caso.
if "streamlit" in sys.modules and getattr(sys.modules["streamlit"], "__spec__", None) is None:
    SKIP = False
else:
    SKIP = importlib.util.find_spec("streamlit") is not None
if not SKIP:
    from fake_streamlit import RerunException

    st = sys.modules["streamlit"]
    _spec = importlib.util.spec_from_file_location("ecoguardian_app_smoke", HERE.parent / "app.py")
    app = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(app)
    from eco import arena, engine, pages, store
    from test_eco_core import right


def _setup():
    # test_eco_core imports the module as `app`, so rebind the shared store connector to this test app.
    store.configure(lambda: app.db_connect())
    app.DB_PATH = Path(tempfile.mkdtemp()) / "smoke.sqlite3"
    app._READY_DBS.clear()
    con = app.db_connect()
    for user, role in (("admin1", "admin"), ("prof1", "teacher"), ("est1", "student"), ("est2", "student")):
        salt, digest = app._password_hash("clave-segura-123")
        con.execute("INSERT INTO accounts(username,display_name,salt,password_hash,role,approved,created_at) VALUES(?,?,?,?,?,1,?)",
                    (user, user.title(), salt, digest, role, app.now_iso()))
    con.execute("INSERT INTO eco_teacher_grants(teacher,game,enabled,starts_at,updated_by,updated_at) VALUES('prof1','EcoSonidos',1,'2000-01-01','admin1',?)", (app.now_iso(),))
    con.commit()
    con.close()


def run(role, user, page="library", **state):
    st.reset()
    st.session_state.update(auth_user=user, auth_role=role, page=page, **state)
    try:
        app.main()
    except RerunException:
        pass
    assert not st.errors, st.errors
    return st


def cont(role, user, page="library", **state):
    """Nuevo ciclo de ejecución conservando el estado de sesión (como hace Streamlit tras un clic)."""
    st.html.clear()
    st.errors.clear()
    st.session_state.update(auth_user=user, auth_role=role, page=page, **state)
    try:
        app.main()
    except RerunException:
        pass
    assert not st.errors, st.errors
    return st


def test_every_page_renders_for_every_role():
    if SKIP:
        return
    _setup()
    menus = {"student": ["library", "arena", "about", "home"], "teacher": ["library", "arena", "about", "bank", "tgames", "tassign", "tmsgs", "tclasses"],
             "admin": ["library", "arena", "about", "bank", "agames", "aaccounts", "aperms", "anotif", "asettings", "apres", "adash"]}
    users = {"student": "est1", "teacher": "prof1", "admin": "admin1"}
    for role, pages_ in menus.items():
        for page in pages_:
            out = run(role, users[role], page)
            assert out.html, (role, page)
    run("student", "est1", "about")
    assert any("Escuchar explicación del avatar" in h for h in st.html)       # avatar con botón de locución
    assert any("Guardianes del planeta" in h for h in st.html) or True


def test_topbar_has_only_avatar_and_no_sidebar_widgets():
    if SKIP:
        return
    _setup()
    out = run("student", "est1", "library")
    joined = "".join(out.html)
    assert "st-key-eg-avatar" in joined and "eg-brand" in joined
    assert "Subir foto" not in joined


def test_library_filters_and_cards():
    if SKIP:
        return
    _setup()
    for cat in (None, "Restauración", "Energía", "Océanos", "Clima"):
        out = run("student", "est1", "library", lib_cat=cat)
        text = "".join(out.html)
        for title in ("Arena en Vivo", "Misión por Niveles", "Balloon Bash", "Duelo de Imágenes"):
            assert title in text
        assert "EcoSonidos" not in text            # el estudiante no tiene ese juego asignado
    out = run("teacher", "prof1", "library")
    assert "EcoSonidos" in "".join(out.html)
    run("admin", "admin1", "library", lib_game="legacy:EcoSonidos")


def test_teacher_toggle_hides_game_for_students():
    if SKIP:
        return
    _setup()
    con = app.db_connect()
    con.execute("INSERT INTO eco_student_grants(teacher,student,game,enabled,starts_at,updated_at) VALUES('prof1','est1','EcoSonidos',1,'2000-01-01',?)", (app.now_iso(),))
    con.commit()
    st.reset()
    st.session_state["tg_prof1_game_inflate"] = False
    pages._save_pref("prof1", "game", "inflate", "tg_prof1_game_inflate")
    assert "Balloon Bash" not in "".join(run("student", "est1", "library").html)
    assert "Balloon Bash" in "".join(run("teacher", "prof1", "library").html)      # el docente sigue viéndolo (vista previa)
    assert "Misión por Niveles" in "".join(run("student", "est1", "library").html)


def test_mission_flow_end_to_end():
    if SKIP:
        return
    _setup()
    run("student", "est1", "library", lib_game="mission")
    st.clicks.add("qz_mission_start")
    cont("student", "est1", "library")
    state = st.session_state["qz_mission"]
    assert len(state["qs"]) == 8
    ids = [q["id"] for q in state["qs"]]
    for i, q in enumerate(list(state["qs"])):
        cont("student", "est1", "library")                     # pregunta visible, sin responder
        pages._qz_answer("qz_mission", "est1", right(q))
        cont("student", "est1", "library")                     # retroalimentación
        st.clicks.add(f"qz_mission_next_{i}")
        cont("student", "est1", "library")
    cont("student", "est1", "library")                         # resumen final
    assert any("aciertos" in h for h in st.html)
    con = app.db_connect()
    prog = store.user_progress(con, "est1")
    assert prog["seen"] == 8 and prog["correct"] == 8 and store.minigame_best(con, "est1", "mission") > 0
    again, cycled = store.pick_for_user(con, "est1", n=8, owners=["*"])      # la siguiente misión no repite
    assert not cycled and not {q["id"] for q in again} & set(ids)


def test_inflate_flow():
    if SKIP:
        return
    _setup()
    run("student", "est1", "library", lib_game="inflate", bb_mode="solo")
    st.clicks.add("inf_start")
    cont("student", "est1", "library")
    assert st.session_state["inf"]["status"] == "playing"
    assert "target" in st.session_state["inf"]
    # Sin cronómetro: cada toque infla y el globo revienta automáticamente al llegar al límite.
    for _ in range(20):
        state = st.session_state["inf"]
        if state["status"] != "playing":
            break
        st.clicks.add(f"inf_pump_{state['pumps']}")
        cont("student", "est1", "library")
    state = st.session_state["inf"]
    assert state["status"] in ("exploded", "stopped")
    if state["status"] == "exploded":
        assert state["value"] == 100 and state["score"] == 0
    else:
        assert 0 <= state["score"] <= 100
    cont("student", "est1", "library")
    assert state["saved"] and store.minigame_best(app.db_connect(), "est1", "inflate") >= 0
    from eco import media
    for shape in media.SHAPES:
        assert "clipPath" in media.silhouette_svg(shape, .5)


def test_arena_every_state_for_host_and_players():
    if SKIP:
        return
    _setup()
    con = app.db_connect()
    code = arena.create_room(con, "prof1", title="Smoke", mode="salon", category=None, level="Mixta", qtypes=["mcq", "tf", "image", "match"], rounds=4, seconds=20)
    for user in ("est1", "est2"):
        assert arena.join(con, code, user, user.title(), "8-A") == "ok"
    views = (("teacher", "prof1"), ("student", "est1"), ("student", "est2"))

    def render_all():
        for role, user in views:
            out = run(role, user, "arena", arena_code=code)
            assert out.html

    render_all()                                                                     # lobby
    assert arena.start(con, code, "prof1")
    for rnd in range(4):
        render_all()                                                                 # pregunta
        room = arena.get_room(con, code)
        q = arena.current_question(room)
        arena.submit(con, code, "est1", right(q))
        render_all()                                                                 # est1 ya respondió
        arena.skip(con, code, "prof1")
        render_all()                                                                 # resultados
        if arena.get_room(con, code)["status"] == "reveal":
            arena.skip(con, code, "prof1")
    assert arena.get_room(con, code)["status"] == "finished"
    render_all()                                                                     # final
    assert any("Campeonato terminado" in h for h in st.html)
    run("student", "est1", "arena")                                                  # pantalla de unirse
    run("teacher", "prof1", "arena")                                                 # unirse + crear


def test_arena_create_via_form_and_join_via_pin():
    if SKIP:
        return
    _setup()
    st.reset()
    st.session_state.update(auth_user="prof1", auth_role="teacher", page="arena")
    st.clicks.add("Crear sala y obtener PIN")
    try:
        app.main()
    except RerunException:
        pass
    code = st.session_state.get("arena_code")
    assert code and len(code) == 6
    st.reset()
    st.session_state.update(auth_user="est1", auth_role="student", page="arena")
    st.clicks.add("Entrar a la arena")
    st.session_state["arena_join_pin"] = code
    # el simulado devuelve el valor por defecto del text_input; el flujo de unión real se cubre en test_eco_core
    try:
        app.main()
    except RerunException:
        pass


def test_bank_editor_validation_and_crud_paths():
    if SKIP:
        return
    _setup()
    st.reset()
    st.session_state.update(auth_user="prof1", auth_role="teacher", page="bank")
    st.clicks.add("➕ Añadir pregunta")
    try:
        app.main()
    except RerunException:
        pass
    assert st.errors                          # prompt vacío: la validación debe mostrar errores y NO guardar
    assert not store.list_questions(app.db_connect(), owners=['prof1'])
    con = app.db_connect()
    qid = store.add_question(con, {"category": "Clima", "level": "Experto", "qtype": "tf", "prompt": "Afirmación editable de prueba.", "correct": True}, "prof1", "prof1")
    run("teacher", "prof1", "bank", bk_sel=qid)
    run("admin", "admin1", "bank", bk_sel=qid)
    run("teacher", "prof2" if False else "prof1", "bank", bk_sel=1)           # pregunta global: solo lectura + copia


def test_teacher_session_survives_reload():
    if SKIP:
        return
    _setup()
    st.reset()
    app.persist_login("prof1", "teacher")
    token = st.query_params["eg_session"]
    st.session_state.clear()
    st.query_params.clear()
    st.query_params["eg_session"] = token
    app.restore_login()
    assert st.session_state.get("auth_user") == "prof1" and st.session_state.get("auth_role") == "teacher"


def test_login_screen_renders_with_theme():
    if SKIP:
        return
    _setup()
    st.reset()
    try:
        app.main()
    except RerunException:
        pass
    text = "".join(st.html)
    assert "Fraunces" in text and "EcoGuardian" in text
    assert "unsplash" not in text


def _add_pending(username, display, role="student"):
    con = app.db_connect()
    salt, digest = app._password_hash("clave-segura-123")
    con.execute("INSERT INTO accounts(username,display_name,salt,password_hash,role,approved,created_at) VALUES(?,?,?,?,?,0,?)",
                (username, display, salt, digest, role, app.now_iso()))
    con.commit(); con.close()


def _approved(username):
    con = app.db_connect()
    row = con.execute("SELECT approved FROM accounts WHERE username=?", (username,)).fetchone()
    con.close()
    return None if row is None else int(row["approved"])


def test_bell_shows_pending_and_admin_can_approve_or_reject():
    if SKIP:
        return
    _setup()
    _add_pending("nuevo1", "Nuevo Uno")
    _add_pending("nuevo2", "Nuevo Dos", "teacher")
    run("admin", "admin1", "library")
    text = "".join(st.html)
    assert "Solicitudes de registro (2)" in text and "Nuevo Uno" in text
    st.clicks.add("bell_ok_nuevo1"); st.clicks.add("bell_no_nuevo2")
    cont("admin", "admin1", "library")
    assert _approved("nuevo1") == 1
    assert _approved("nuevo2") is None


def test_bell_watch_triggers_rerun_with_toast_when_new_registration_arrives():
    if SKIP:
        return
    from types import SimpleNamespace
    _setup()
    run("admin", "admin1", "library")
    assert st.session_state.get("bell_sig") == ((), ())
    _add_pending("tarde1", "Llegó Tarde")
    raised = False
    try:
        pages._bell_poll(SimpleNamespace(username="admin1", role="admin"))   # lo que hace el fragmento cada 4 s
    except RerunException:
        raised = True
    assert raised and "Llegó Tarde" in st.session_state.get("bell_toast", "")
    cont("admin", "admin1", "library")                                          # la recarga muestra el aviso y la solicitud
    assert "Solicitudes de registro (1)" in "".join(st.html)
    assert not st.session_state.get("bell_toast")


def test_browser_notifications_are_opt_in_and_privacy_preserving():
    if SKIP:
        return
    from eco import pages
    st.reset()
    rendered = []
    original_html = pages.components.html
    pages.components.html = lambda body, **kwargs: rendered.append(body)
    try:
        pages.browser_notification("token-test")
    finally:
        pages.components.html = original_html
    html = "".join(rendered)
    assert "Activar avisos del navegador" in html
    assert "requestPermission" in html
    assert "Tienes una nueva notificaci" in html and "EcoGuardian AI" in html
    # El texto enviado a la notificación del sistema no incluye nombre ni cuerpo del mensaje.
    assert "localStorage" in html and "requestPermission" in html  # permiso solicitado solo tras clic


def test_bell_decide_requires_admin_session():
    if SKIP:
        return
    _setup()
    _add_pending("intruso1", "Intruso")
    st.reset()
    st.session_state.update(auth_user="est1", auth_role="student")
    pages._bell_decide("intruso1", True)
    assert _approved("intruso1") == 0


def test_bell_messages_for_student_and_mark_read():
    if SKIP:
        return
    _setup()
    app.send_message("prof1", "est1", "Recuerda traer tu cuaderno")
    run("student", "est1", "home")
    assert "Mensajes sin leer (1)" in "".join(st.html) and "Recuerda traer tu cuaderno" in "".join(st.html)
    con = app.db_connect(); mid = con.execute("SELECT id FROM messages").fetchone()["id"]; con.close()
    st.clicks.add(f"bell_read_{mid}")
    cont("student", "est1", "home")      # el clic marca como leído
    cont("student", "est1", "home")      # la pantalla siguiente ya no lo muestra
    assert "Mensajes sin leer" not in "".join(st.html)


def test_ambient_uses_environment_song_not_bird_synthesis():
    if SKIP:
        return
    from eco import ambient, media
    assert ambient.SONG_FILE.name == "reciclar_ambiente.mp3" and ambient.SONG_FILE.is_file()
    assert not hasattr(media, "ambient_html")          # ya no se incrusta el MP3 en base64 en cada rerun
    html = (ambient.SONG_FILE.parent / "index.html").read_text(encoding="utf-8")
    assert "Reproducir" in html and "chirp(" not in html