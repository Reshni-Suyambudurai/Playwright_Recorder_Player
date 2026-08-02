from app.services.session_manager import SessionManager


def test_create_session():
    manager = SessionManager()
    session = manager.create_session()
    assert session.session_id


def test_get_session():
    manager = SessionManager()
    session = manager.create_session()
    assert manager.get_session(session.session_id) is session


def test_remove_session():
    manager = SessionManager()
    session = manager.create_session()
    assert manager.remove_session(session.session_id) is True


def test_list_active_sessions():
    manager = SessionManager()
    session = manager.create_session()
    assert session in manager.list_active_sessions()


def test_list_all_sessions():
    manager = SessionManager()
    session = manager.create_session()
    assert session in manager.list_all_sessions()
