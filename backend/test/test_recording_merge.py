import json

from app.models.recording import Recording, RecordingStep
from app.utils.recording_merge import merge_pause_steps_with_reinsertion


def test_merge_inserts_pause_steps_and_reindexes_json_output():
    recording = Recording.model_validate({
        "version": "1.0",
        "meta": {"id": "original", "title": "Original"},
        "steps": {
            "tab-1": [
                [{"id": 7, "type": "CLICK", "button": "left"}],
                [{"id": 12, "type": "TYPE", "text": "after"}],
            ],
        },
    })
    pause_step = RecordingStep(
        id=0,
        type="CLICK",
        button="left",
        coords={"x": 365, "y": 279},
    )

    merged_steps, total_steps = merge_pause_steps_with_reinsertion(
        recording,
        {7: [pause_step]},
    )

    flat_steps = [group[0] for group in merged_steps["tab-1"]]
    assert total_steps == 3
    assert [step["id"] for step in flat_steps] == [1, 2, 3]
    assert [step["type"] for step in flat_steps] == ["CLICK", "CLICK", "TYPE"]
    assert flat_steps[1]["coords"] == {"x": 365, "y": 279}
    json.dumps(merged_steps)