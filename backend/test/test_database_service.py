import json

import pytest

import app.services.database as db_module
from app.services.database import DatabaseService


@pytest.mark.asyncio
async def test_init_db_creates_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "recorder.db"
    sql_path = tmp_path / "schema.sql"
    sql_path.write_text(
        """
        CREATE TABLE IF NOT EXISTS Users (
          userId TEXT PRIMARY KEY,
          clientId TEXT,
          isActive INTEGER
        );
        CREATE TABLE IF NOT EXISTS Recordings (
          recordId TEXT PRIMARY KEY,
          userId TEXT,
          json TEXT,
          flowName TEXT
        );
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(db_module, "_DB_PATH", db_path)
    monkeypatch.setattr(db_module, "_SQL_PATH", sql_path)
    await DatabaseService().init_db()
    assert db_path.exists()


@pytest.mark.asyncio
async def test_ensure_user_inserts_row(tmp_path, monkeypatch):
    db_path = tmp_path / "recorder.db"
    sql_path = tmp_path / "schema.sql"
    sql_path.write_text(
        """
        CREATE TABLE IF NOT EXISTS Users (userId TEXT PRIMARY KEY, clientId TEXT, isActive INTEGER);
        CREATE TABLE IF NOT EXISTS Recordings (recordId TEXT PRIMARY KEY, userId TEXT, json TEXT, flowName TEXT);
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(db_module, "_DB_PATH", db_path)
    monkeypatch.setattr(db_module, "_SQL_PATH", sql_path)
    svc = DatabaseService()
    await svc.init_db()
    await svc.ensure_user("c1")
    rows = await svc.list_recordings()
    assert isinstance(rows, list)


@pytest.mark.asyncio
async def test_save_recording_persists_data(tmp_path, monkeypatch):
    db_path = tmp_path / "recorder.db"
    sql_path = tmp_path / "schema.sql"
    sql_path.write_text(
        """
        CREATE TABLE IF NOT EXISTS Users (userId TEXT PRIMARY KEY, clientId TEXT, isActive INTEGER);
        CREATE TABLE IF NOT EXISTS Recordings (recordId TEXT PRIMARY KEY, userId TEXT, json TEXT, flowName TEXT);
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(db_module, "_DB_PATH", db_path)
    monkeypatch.setattr(db_module, "_SQL_PATH", sql_path)
    svc = DatabaseService()
    await svc.init_db()
    await svc.ensure_user("c1")
    await svc.save_recording("r1", "c1", {"meta": {"id": "r1"}, "steps": {}}, "flow")
    loaded = await svc.load_recording("r1")
    assert loaded["meta"]["id"] == "r1"


@pytest.mark.asyncio
async def test_list_recordings_returns_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "recorder.db"
    sql_path = tmp_path / "schema.sql"
    sql_path.write_text(
        """
        CREATE TABLE IF NOT EXISTS Users (userId TEXT PRIMARY KEY, clientId TEXT, isActive INTEGER);
        CREATE TABLE IF NOT EXISTS Recordings (recordId TEXT PRIMARY KEY, userId TEXT, json TEXT, flowName TEXT);
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(db_module, "_DB_PATH", db_path)
    monkeypatch.setattr(db_module, "_SQL_PATH", sql_path)
    svc = DatabaseService()
    await svc.init_db()
    await svc.ensure_user("c1")
    await svc.save_recording(
        "r1",
        "c1",
        {"meta": {"description": "d"}, "steps": {"tab-1": [[{"id": 1}]]}},
        "flow",
    )
    rows = await svc.list_recordings()
    assert rows[0]["recordId"] == "r1"


@pytest.mark.asyncio
async def test_load_recording_returns_none_if_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "recorder.db"
    sql_path = tmp_path / "schema.sql"
    sql_path.write_text("CREATE TABLE IF NOT EXISTS Recordings (recordId TEXT PRIMARY KEY, userId TEXT, json TEXT, flowName TEXT);", encoding="utf-8")
    monkeypatch.setattr(db_module, "_DB_PATH", db_path)
    monkeypatch.setattr(db_module, "_SQL_PATH", sql_path)
    svc = DatabaseService()
    await svc.init_db()
    assert await svc.load_recording("missing") is None


@pytest.mark.asyncio
async def test_delete_recording_returns_true_when_deleted(tmp_path, monkeypatch):
    db_path = tmp_path / "recorder.db"
    sql_path = tmp_path / "schema.sql"
    sql_path.write_text(
        """
        CREATE TABLE IF NOT EXISTS Users (userId TEXT PRIMARY KEY, clientId TEXT, isActive INTEGER);
        CREATE TABLE IF NOT EXISTS Recordings (recordId TEXT PRIMARY KEY, userId TEXT, json TEXT, flowName TEXT);
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(db_module, "_DB_PATH", db_path)
    monkeypatch.setattr(db_module, "_SQL_PATH", sql_path)
    svc = DatabaseService()
    await svc.init_db()
    await svc.ensure_user("c1")
    await svc.save_recording("r1", "c1", {"meta": {}, "steps": {}}, "flow")
    deleted = await svc.delete_recording("r1")
    assert deleted is True
