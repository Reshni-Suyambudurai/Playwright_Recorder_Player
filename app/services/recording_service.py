"""Recording service for saving and managing action recordings"""
import logging
import json
from pathlib import Path
from datetime import datetime
from app.models.recording import Recording

logger = logging.getLogger(__name__)

# Base directory for recordings
RECORDINGS_DIR = Path(__file__).parent.parent / "JSON_Recordings"


class RecordingService:
    """Service for handling action recording and storage"""

    @staticmethod
    def initialize():
        """Initialize recordings directory"""
        try:
            RECORDINGS_DIR.mkdir(exist_ok=True)
            logger.info(f"Recordings directory initialized: {RECORDINGS_DIR}")
        except Exception as e:
            logger.error(f"Failed to initialize recordings directory: {e}")

    @staticmethod
    def save_recording(recording: Recording, title: str, description: str = "", intent: str = "") -> dict:
        """
        Save recording to JSON file with date-based folder structure
        
        Args:
            recording: Recording object with actions
            title: Recording title
            description: Recording description
            intent: Recording intent
            
        Returns:
            dict with status, file_path, and recording_id
        """
        try:
            # Ensure recordings directory exists
            RecordingService.initialize()
            
            # Create date-based subfolder (YYYYMMDD)
            today = datetime.now().strftime("%Y%m%d")
            date_folder = RECORDINGS_DIR / f"recordings_{today}"
            date_folder.mkdir(exist_ok=True)
            
            # Generate filename with timestamp (YYYYMMDD_HHMMSS)
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recording_{timestamp_str}.json"
            file_path = date_folder / filename
            
            # Update recording metadata
            recording.meta.title = title
            recording.meta.description = description
            recording.meta.intent = intent
            recording.meta.updatedAt = int(datetime.now().timestamp() * 1000)
            
            # Convert to dict and save as JSON
            recording_dict = recording.model_dump()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(recording_dict, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Recording saved successfully: {file_path}")
            logger.info(f"Recording ID: {recording.meta.id}")
            logger.info(f"Total actions recorded: {len([action for group in recording.steps.values() for action_group in group for action in action_group])}")
            
            return {
                "status": "success",
                "file_path": str(file_path),
                "recording_id": recording.meta.id,
                "filename": filename,
                "title": title,
                "timestamp": timestamp_str
            }
            
        except Exception as e:
            logger.error(f"Failed to save recording: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    @staticmethod
    def list_recordings(limit: int = 10) -> dict:
        """
        List recent recordings
        
        Args:
            limit: Maximum number of recordings to return
            
        Returns:
            dict with recordings list and total count
        """
        try:
            RecordingService.initialize()
            
            recordings = []
            
            # Search all date folders
            if RECORDINGS_DIR.exists():
                for date_folder in sorted(RECORDINGS_DIR.glob("recordings_*"), reverse=True):
                    for recording_file in sorted(date_folder.glob("recording_*.json"), reverse=True):
                        if len(recordings) >= limit:
                            break
                        
                        try:
                            with open(recording_file, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                recordings.append({
                                    "filename": recording_file.name,
                                    "title": data.get("meta", {}).get("title", "Untitled"),
                                    "id": data.get("meta", {}).get("id"),
                                    "created_at": data.get("meta", {}).get("createdAt"),
                                    "file_path": str(recording_file)
                                })
                        except Exception as e:
                            logger.error(f"Failed to read recording {recording_file}: {e}")
                    
                    if len(recordings) >= limit:
                        break
            
            logger.info(f"Found {len(recordings)} recent recordings")
            
            return {
                "status": "success",
                "count": len(recordings),
                "recordings": recordings
            }
            
        except Exception as e:
            logger.error(f"Failed to list recordings: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "count": 0,
                "recordings": []
            }

    @staticmethod
    def get_recording(recording_id: str) -> dict:
        """
        Get a specific recording by ID
        
        Args:
            recording_id: Recording ID (UUID)
            
        Returns:
            dict with recording data or error
        """
        try:
            RecordingService.initialize()
            
            # Search for recording with matching ID
            if RECORDINGS_DIR.exists():
                for date_folder in RECORDINGS_DIR.glob("recordings_*"):
                    for recording_file in date_folder.glob("recording_*.json"):
                        with open(recording_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if data.get("meta", {}).get("id") == recording_id:
                                logger.info(f"Found recording: {recording_id}")
                                return {
                                    "status": "success",
                                    "recording": data,
                                    "file_path": str(recording_file)
                                }
            
            logger.warning(f"Recording not found: {recording_id}")
            return {
                "status": "error",
                "message": f"Recording with ID {recording_id} not found"
            }
            
        except Exception as e:
            logger.error(f"Failed to get recording {recording_id}: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }
