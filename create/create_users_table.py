import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "crm.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

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

print(f"Users table created in {DB_PATH}")
