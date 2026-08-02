import json
from pathlib import Path

from app.models.recording import Recording, RecordingMeta, RecordingStep
from app.services import recording_storage
from app.services.recording_storage import RecordingStorage


def test_save_creates_json_file(tmp_path, monkeypatch):
    monkeypatch.setattr(recording_storage, "_STORAGE_DIR", tmp_path)
    storage = RecordingStorage()
    recording = Recording(meta=RecordingMeta(id="r1", title="flow"))
    recording.add_step(RecordingStep(id=1, type="NAVIGATE"))
    path = storage.save(recording)
    assert Path(path).exists()


def test_list_all_returns_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(recording_storage, "_STORAGE_DIR", tmp_path)
    payload = {
        "version": "1.0",
        "meta": {"id": "r1", "title": "flow", "description": "d"},
        "steps": {"tab-1": [[{"id": 1, "type": "NAVIGATE"}]]},
    }
    (tmp_path / "r1.json").write_text(json.dumps(payload), encoding="utf-8")
    rows = RecordingStorage().list_all()
    assert rows[0]["id"] == "r1"


def test_load_returns_dict_when_file_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(recording_storage, "_STORAGE_DIR", tmp_path)
    payload = {"meta": {"id": "r1"}}
    (tmp_path / "r1.json").write_text(json.dumps(payload), encoding="utf-8")
    loaded = RecordingStorage().load("r1")
    assert loaded["meta"]["id"] == "r1"
