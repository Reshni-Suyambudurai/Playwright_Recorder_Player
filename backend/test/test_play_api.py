import pytest

import app.api.play as play_api


@pytest.mark.asyncio
async def test_start_playback_returns_400_without_steps():
    router = play_api.create_play_router()
    endpoint = next(route.endpoint for route in router.routes if route.path == "/start")
    response = await endpoint({})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_stop_playback_returns_404_for_missing_session():
    router = play_api.create_play_router()
    endpoint = next(route.endpoint for route in router.routes if route.path == "/{play_id}")
    response = await endpoint("missing")
    assert response.status_code == 404
