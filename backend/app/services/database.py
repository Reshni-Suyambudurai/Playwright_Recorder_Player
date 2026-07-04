"""
DatabaseService — async SQLite storage for Users and Recordings.
DB file: <workspace_root>/database/recorder.db
Schema:  <workspace_root>/database/schema.sql
"""
import json
import logging
from pathlib import Path
import aiosqlite

logger = logging.getLogger("playwright_recorder.services.database")

# Resolve paths: backend/app/services/ -> up 3 levels -> workspace root
_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
_DB_PATH   = _WORKSPACE_ROOT / "database" / "recorder.db"
_SQL_PATH  = _WORKSPACE_ROOT / "database" / "schema.sql"


class DatabaseService:

    async def init_db(self) -> None:
        """Create database/recorder.db and run schema.sql if tables do not exist."""
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        schema = _SQL_PATH.read_text(encoding="utf-8")
        # Strip comment lines, then split on ";" to get individual statements
        cleaned_lines = [
            line for line in schema.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        cleaned_sql = "\n".join(cleaned_lines)
        statements = [s.strip() for s in cleaned_sql.split(";") if s.strip()]
        async with aiosqlite.connect(_DB_PATH) as db:
            for stmt in statements:
                try:
                    await db.execute(stmt)
                except Exception as e:
                    logger.warning(f"init_db statement skipped ({e}): {stmt[:60]}")
            await db.commit()
        logger.info(f"Database initialised at {_DB_PATH}")

    async def ensure_user(self, client_id: str) -> None:
        """
        Ensure a Users row exists for this clientId.
        userId == clientId (no auth yet). Creates a minimal row if absent.
        """
        async with aiosqlite.connect(_DB_PATH) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                """
                INSERT OR IGNORE INTO Users (userId, clientId, isActive)
                VALUES (?, ?, 1)
                """,
                (client_id, client_id),
            )
            await db.commit()
        logger.debug(f"ensure_user: {client_id}")

    async def save_recording(
        self,
        record_id: str,
        client_id: str,
        recording_json: dict,
        flow_name: str,
    ) -> None:
        """Insert a recording row (json stored as TEXT)."""
        json_str = json.dumps(recording_json, ensure_ascii=False)
        async with aiosqlite.connect(_DB_PATH) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                """
                INSERT OR REPLACE INTO Recordings (recordId, userId, json, flowName)
                VALUES (?, ?, ?, ?)
                """,
                (record_id, client_id, json_str, flow_name),
            )
            await db.commit()
        logger.info(f"Recording saved to DB: {record_id}")

    async def list_recordings(self) -> list[dict]:
        """Return enriched summary rows for all recordings (with description + stepCount)."""
        async with aiosqlite.connect(_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT recordId, userId, flowName, json FROM Recordings ORDER BY rowid DESC"
            )
            rows = await cursor.fetchall()
        result = []
        for row in rows:
            item: dict = {
                "recordId": row["recordId"],
                "userId": row["userId"],
                "flowName": row["flowName"],
                "description": "",
                "stepCount": 0,
                "createdAt": None,
                "updatedAt": None,
            }
            try:
                data = json.loads(row["json"])
                meta = data.get("meta", {})
                item["description"] = meta.get("description", "")
                item["createdAt"] = meta.get("createdAt")
                item["updatedAt"] = meta.get("updatedAt")
                # Count total steps across all tabs
                steps_by_tab: dict = data.get("steps", {})
                total = sum(len(tab_steps) for tab_steps in steps_by_tab.values())
                item["stepCount"] = total
            except Exception:
                pass
            result.append(item)
        return result

    async def load_recording(self, record_id: str) -> dict | None:
        """Return the full parsed JSON for one recording, or None."""
        async with aiosqlite.connect(_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT json FROM Recordings WHERE recordId = ?",
                (record_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row["json"])
