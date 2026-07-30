import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "crm.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute(
    """
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        company TEXT,
        status TEXT NOT NULL,
        owner_id INTEGER
    )
    """
)
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        company TEXT
    )
    """
)
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS deals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        deal_name TEXT NOT NULL,
        amount REAL,
        stage TEXT
    )
    """
)
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL
    )
    """
)

conn.commit()
conn.close()
