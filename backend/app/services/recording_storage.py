"""
RecordingStorage — persists Recording objects as JSON files under
backend/storage/recordings/.
"""
import json
import logging
import os
from pathlib import Path
from app.models.recording import Recording

logger = logging.getLogger("playwright_recorder.services.recording_storage")

# Resolve path relative to this file: backend/storage/recordings/
_STORAGE_DIR = Path(__file__).resolve().parents[2] / "storage" / "recordings"


def _ensure_dir() -> None:
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)


class RecordingStorage:
    def save(self, recording: Recording) -> str:
        """Serialize and save recording. Returns absolute file path."""
        _ensure_dir()
        file_path = _STORAGE_DIR / f"{recording.meta.id}.json"
        payload = {
            "version": recording.version,
            "meta": recording.meta.model_dump(by_alias=True),
            "steps": recording.steps,
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.info(f"Recording saved: {file_path}")
        return str(file_path)

    def list_all(self) -> list[dict]:
        """Return a list of recording metadata dicts."""
        _ensure_dir()
        results = []
        for fp in sorted(_STORAGE_DIR.glob("*.json")):
            try:
                with open(fp, encoding="utf-8") as f:
                    data = json.load(f)
                meta = data.get("meta", {})
                meta["step_count"] = sum(
                    len(group) for group in data.get("steps", {}).get("tab-1", [])
                )
                results.append(meta)
            except Exception as e:
                logger.warning(f"Could not read {fp}: {e}")
        return results

    def load(self, recording_id: str) -> dict | None:
        """Load a recording by ID. Returns raw dict or None if not found."""
        _ensure_dir()
        file_path = _STORAGE_DIR / f"{recording_id}.json"
        if not file_path.exists():
            return None
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
