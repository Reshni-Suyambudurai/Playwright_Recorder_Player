import asyncio

import pytest

import app.api.play as play_api
from app.models.playback import PlaySession
from app.models.playback_contracts import StartPlaybackRequest


@pytest.mark.asyncio
async def test_start_playback_returns_400_without_steps():
    router = play_api.create_play_router()
    endpoint = next(route.endpoint for route in router.routes if route.path == "/start")
    response = await endpoint(StartPlaybackRequest())
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_stop_playback_returns_404_for_missing_session():
    router = play_api.create_play_router()
    endpoint = next(route.endpoint for route in router.routes if route.path == "/{play_id}")
    response = await endpoint("missing")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_shutdown_play_sessions_cancels_and_awaits_tasks():
    task_finished = False

    async def running_playback():
        nonlocal task_finished
        try:
            await asyncio.Event().wait()
        finally:
            task_finished = True

    session = PlaySession(play_id="active", recording_json={"steps": {}})
    session.task = asyncio.create_task(running_playback())
    play_api._play_sessions[session.play_id] = session
    await asyncio.sleep(0)

    count = await play_api.shutdown_play_sessions()

    assert count == 1
    assert session.task.done()
    assert task_finished is True
    assert play_api._play_sessions == {}
