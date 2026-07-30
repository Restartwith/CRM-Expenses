import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "crm.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

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

conn.commit()
conn.close()

print(f"Deals table created in {DB_PATH}")
