from app.models.recording import Recording, RecordingMeta, RecordingStep


def test_recording_step_to_json_dict_excludes_tab_id():
    step = RecordingStep(id=1, type="CLICK", tab_id="tab-2")
    payload = step.to_json_dict()
    assert "tab_id" not in payload


def test_recording_add_step_groups_by_tab():
    recording = Recording(meta=RecordingMeta(id="r1", title="t1"))
    step = RecordingStep(id=1, type="CLICK", tab_id="tab-2")
    recording.add_step(step)
    assert "tab-2" in recording.steps


def test_recording_step_count_counts_tab_1_groups():
    recording = Recording(meta=RecordingMeta(id="r1", title="t1"))
    recording.add_step(RecordingStep(id=1, type="NAVIGATE", tab_id="tab-1"))
    assert recording.step_count() == 1


def test_click_step_serializes_target_meta_alias():
    step = RecordingStep(
        id=1,
        type="CLICK",
        targetMeta={"tag": "div", "normalizedText": "obgyn", "dataTestId": "dept"},
        tab_id="tab-1",
    )
    payload = step.to_json_dict()
    assert payload["targetMeta"]["tag"] == "div"
    assert payload["targetMeta"]["normalizedText"] == "obgyn"
