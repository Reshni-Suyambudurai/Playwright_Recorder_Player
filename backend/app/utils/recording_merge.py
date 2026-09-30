"""
Utility functions for merging pause steps into original recordings.
Handles step insertion, truncation, and re-indexing.
"""
import logging
from typing import Tuple
from app.models.recording import RecordingStep, Recording

logger = logging.getLogger("playwright_recorder.utils.recording_merge")


def merge_pause_steps_with_reinsertion(
    original_recording: Recording,
    pause_step_insertion_points: dict[int, list[RecordingStep]],
) -> Tuple[dict, int]:
    """
    Merge pause steps into original recording at their insertion points.
    Re-index all steps sequentially: 1, 2, 3, ...
    
    Args:
        original_recording: The original Recording object
        pause_step_insertion_points: Dict mapping step_id -> list of pause steps to insert after it
    
    Returns:
        Tuple of:
        - merged_steps: dict with re-indexed steps in tab-group structure
        - total_steps: total number of steps in merged result
    """
    merged_steps: dict[str, list[list[dict]]] = {}
    step_counter = 1
    pause_step_count = 0

    for tab_id, groups in original_recording.steps.items():
        merged_steps[tab_id] = []
        for group in groups:
            for raw_step in group:
                step = raw_step if isinstance(raw_step, RecordingStep) else RecordingStep.model_validate(raw_step)
                original_step_id = step.id
                reindexed_step = step.model_copy(update={"id": step_counter})
                merged_steps[tab_id].append([reindexed_step.to_json_dict()])
                step_counter += 1

                for pause_step in pause_step_insertion_points.get(original_step_id, []):
                    reindexed_pause_step = pause_step.model_copy(
                        update={"id": step_counter, "pause": False}
                    )
                    merged_steps[tab_id].append([reindexed_pause_step.to_json_dict()])
                    step_counter += 1
                    pause_step_count += 1
                    logger.debug(f"Inserted pause step after original step {original_step_id}")
    
    total_steps = step_counter - 1
    logger.info(f"Merged recording: {total_steps} total steps ({pause_step_count} from pause)")
    
    return merged_steps, total_steps


def count_total_steps(steps_dict: dict) -> int:
    """Count total steps from nested structure."""
    count = 0
    for tab_id, groups in steps_dict.items():
        for group in groups:
            if isinstance(group, list):
                count += len(group)
            elif hasattr(group, '__len__'):
                count += len(group)
    return count


def extract_pause_steps_from_session(
    session_pause_insertion_points: dict[int, list[RecordingStep]]
) -> list[RecordingStep]:
    """Flatten all pause steps from insertion points."""
    all_pause_steps = []
    for step_id in sorted(session_pause_insertion_points.keys()):
        all_pause_steps.extend(session_pause_insertion_points[step_id])
    return all_pause_steps
