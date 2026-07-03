-- Enable foreign key support
PRAGMA foreign_keys = ON;

-- ==========================================================
-- USER TABLE
-- ==========================================================
CREATE TABLE IF NOT EXISTS Users (
    userId      TEXT PRIMARY KEY,
    userName    TEXT,
    email       TEXT UNIQUE,
    password    TEXT,
    clientId    TEXT,
    isActive    INTEGER NOT NULL DEFAULT 1
);

-- ==========================================================
-- RECORDINGS TABLE
-- ==========================================================
CREATE TABLE IF NOT EXISTS Recordings (
    recordId    TEXT PRIMARY KEY,
    userId      TEXT NOT NULL,
    json        TEXT NOT NULL,
    flowName    TEXT NOT NULL,

    FOREIGN KEY (userId)
        REFERENCES Users(userId)
        ON DELETE CASCADE
);
