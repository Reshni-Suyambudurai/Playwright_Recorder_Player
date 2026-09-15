from app.models.playback import PlaySession, PlayStatus


def test_play_session_defaults():
    session = PlaySession(play_id="p1", recording_json={"steps": {}})
    assert session.status == PlayStatus.PENDING
