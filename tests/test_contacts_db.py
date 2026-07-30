import sqlite3
from pathlib import Path


def test_insert_contact_creates_record():
    db_path = Path(__file__).resolve().parent / "crm.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("DELETE FROM contacts")

    cur.execute(
        "INSERT INTO contacts (name, email, phone, company) VALUES (?, ?, ?, ?)",
        ("Alice Smith", "alice@example.com", "555-0101", "Acme Corp"),
    )
    conn.commit()

    row = cur.execute(
        "SELECT name, email, phone, company FROM contacts WHERE email = ?",
        ("alice@example.com",),
    ).fetchone()

    conn.close()

    assert row is not None
    assert row == ("Alice Smith", "alice@example.com", "555-0101", "Acme Corp")
