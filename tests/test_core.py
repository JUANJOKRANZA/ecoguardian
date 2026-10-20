import importlib.util
import sqlite3
from pathlib import Path

import pytest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
spec = importlib.util.spec_from_file_location("ecoguardian_app", APP_PATH)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "test.sqlite3")
    app._READY_DBS.clear()
    con = app.db_connect()
    yield con
    con.close()
    app._READY_DBS.clear()


def make_room(con, code="ABC123", mode="libre", activity="residuos", count=3):
    con.execute(
        "INSERT INTO classes(code,title,created_at,mode,teacher,question_count,activity,review,closed) "
        "VALUES(?,?,?,?,?,?,?,?,0)",
        (code, "Prueba", app.now_iso(), mode, "Docente", count, activity, 1),
    )
    con.execute("INSERT INTO participants(code,name,username) VALUES(?,?,?)", (code, "Estudiante Uno", "student1"))
    con.execute(
        "INSERT INTO accounts(username,display_name,salt,password_hash,role,approved,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        ("student1", "Estudiante Uno", "00" * 16, "hash", "student", 1, app.now_iso()),
    )
    con.commit()


def test_question_order_is_unique_and_respects_count():
    for activity in ("residuos", "auditiva", "ambos"):
        order = app.build_order(activity, 60)
        assert len(order) == 60
        assert len({(item[0], item[1]) for item in order}) == 60


def test_exam_persists_and_rejects_duplicate_answer(db):
    make_room(db, count=3)
    started = app.exam_enter(db, "ABC123", "student1", "Estudiante Uno")
    assert started["result"] == "new"
    state = app.exam_state(db, "ABC123", "student1")
    qtype, q = app.resolve_entry(state["order"][0])
    answer = q["correcta"]
    assert app.exam_answer(db, "ABC123", "student1", 0, answer) == "recorded_ok"
    assert app.exam_answer(db, "ABC123", "student1", 0, answer) == "already"
    db.close()
    reopened = app.db_connect()
    resumed = app.exam_enter(reopened, "ABC123", "student1", "Estudiante Uno")
    assert resumed["result"] == "resumed"
    assert app.exam_state(reopened, "ABC123", "student1")["pos"] == 0
    assert app.exam_next(reopened, "ABC123", "student1", 0) == "advanced"
    reopened.close()


def test_exam_rejects_invalid_answers_and_out_of_range_position(db):
    make_room(db, count=2)
    assert app.exam_enter(db, "ABC123", "student1", "Estudiante Uno")["result"] == "new"
    assert app.exam_answer(db, "ABC123", "student1", 0, "respuesta inventada") == "invalid"
    assert app.exam_answer(db, "ABC123", "student1", 99, "Blanco") == "stale"


def test_membership_and_closed_room_are_enforced(db):
    make_room(db)
    assert app.exam_enter(db, "ABC123", "intruder", "Otra Persona")["result"] == "not_member"
    db.execute("UPDATE classes SET closed=1 WHERE code='ABC123'")
    db.commit()
    assert app.exam_enter(db, "ABC123", "student1", "Estudiante Uno")["result"] == "closed"


def test_password_hash_uses_salt_and_verifies():
    salt, digest = app._password_hash("Clave-de-prueba-2026")
    assert app._verify_password("Clave-de-prueba-2026", salt, digest)
    assert not app._verify_password("clave-incorrecta", salt, digest)


def test_room_completion_and_summary(db):
    make_room(db, count=1)
    app.exam_enter(db, "ABC123", "student1", "Estudiante Uno")
    state = app.exam_state(db, "ABC123", "student1")
    _, q = app.resolve_entry(state["order"][0])
    assert app.exam_answer(db, "ABC123", "student1", 0, q["correcta"]) == "recorded_ok"
    assert app.exam_next(db, "ABC123", "student1", 0) == "finished"
    summary = app.exam_summary(db, "ABC123", "student1")
    assert summary["total"] == 1
    assert summary["hits"] == 1
    assert summary["pct"] == 100
    assert app.exam_enter(db, "ABC123", "student1", "Estudiante Uno")["result"] == "finished"


def test_persistent_login_is_revoked_when_account_role_changes(db, monkeypatch):
    import hashlib
    token = "test-token-with-sufficient-randomness"
    digest = app._token_digest(token)
    db.execute(
        "INSERT INTO accounts(username,display_name,salt,password_hash,role,approved,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        ("admin1", "Admin", "00" * 16, "hash", "student", 1, app.now_iso()),
    )
    db.execute(
        "INSERT INTO auth_sessions(token_hash,username,role,expires_at,created_at) VALUES(?,?,?,?,?)",
        (digest, "admin1", "admin", (app.datetime.now()+app.timedelta(days=1)).isoformat(timespec="seconds"), app.now_iso()),
    )
    db.commit()
    app.st.session_state.clear()
    app.st.query_params.clear()
    app.st.query_params["eg_session"] = token
    app.restore_login()
    assert "auth_user" not in app.st.session_state
    assert app.st.query_params.get("eg_session") is None
    assert db.execute("SELECT 1 FROM auth_sessions WHERE token_hash=?", (digest,)).fetchone() is None


def test_ecoscan_returns_relative_heuristics_not_claimed_ai_confidence():
    from PIL import Image
    result = app.classify_image(Image.new("RGB", (32, 32), (30, 180, 60)))
    assert result["pred"] in app.BINS
    assert set(result["probs"]) == set(app.BINS)
    assert abs(sum(result["probs"].values()) - 1.0) < 1e-6
    assert "color" in result["motivo"].lower()


def test_ecoscan_rejects_oversized_images():
    from PIL import Image
    img = Image.new("RGB", (5001, 4000))
    with pytest.raises(ValueError, match="20 megapíxeles"):
        app.classify_image(img)
