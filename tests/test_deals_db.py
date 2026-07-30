import sqlite3
from pathlib import Path


def test_insert_deal_creates_record():
    db_path = Path(__file__).resolve().parent / "crm.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("DELETE FROM deals")

    cur.execute(
        "INSERT INTO deals (deal_name, amount, stage) VALUES (?, ?, ?)",
        ("Enterprise Plan", 15000.0, "Negotiation"),
    )
    conn.commit()

    row = cur.execute(
        "SELECT deal_name, amount, stage FROM deals WHERE deal_name = ?",
        ("Enterprise Plan",),
    ).fetchone()

    conn.close()

    assert row is not None
    assert row == ("Enterprise Plan", 15000.0, "Negotiation")
