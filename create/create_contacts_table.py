import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "crm.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

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

conn.commit()
conn.close()

print(f"Contacts table created in {DB_PATH}")
