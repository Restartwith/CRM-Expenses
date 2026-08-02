import sqlite3
from pathlib import Path

import pytest

from crm_app.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def db_path():
    return Path(__file__).resolve().parent / "crm.db"


@pytest.fixture
def authenticated_client(client, db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM expense_splits")
    cur.execute("DELETE FROM expense_tags")
    cur.execute("DELETE FROM expense_fields")
    cur.execute("DELETE FROM savings_goals")
    cur.execute("DELETE FROM incomes")
    cur.execute("DELETE FROM recurring_expenses")
    cur.execute("DELETE FROM expenses")
    cur.execute("DELETE FROM users")
    cur.execute("DELETE FROM sqlite_sequence")
    cur.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (
            "admin",
            "scrypt:32768:8:1$at2ye7brAo9xsoOq$d50a4a78b80b5c578b14d786cd28035e9576702da783f95640ea381c3d5ba64ab4607373c96214da37819e47cd161e0beb10f46577c068fad6bf0fd1f1609309",
            "admin",
        ),
    )
    conn.commit()
    conn.close()

    client.post(
        "/login",
        data={"username": "admin", "password": "password123"},
        follow_redirects=True,
    )
    return client


def test_login_with_correct_credentials_and_denied_with_wrong_credentials(client, db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM users")
    cur.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (
            "admin",
            "scrypt:32768:8:1$at2ye7brAo9xsoOq$d50a4a78b80b5c578b14d786cd28035e9576702da783f95640ea381c3d5ba64ab4607373c96214da37819e47cd161e0beb10f46577c068fad6bf0fd1f1609309",
            "admin",
        ),
    )
    conn.commit()
    conn.close()

    success_response = client.post(
        "/login",
        data={"username": "admin", "password": "password123"},
        follow_redirects=True,
    )
    assert success_response.status_code == 200
    assert b"Expense CRM Dashboard" in success_response.data

    failure_response = client.post(
        "/login",
        data={"username": "admin", "password": "wrong-password"},
        follow_redirects=True,
    )
    assert failure_response.status_code == 200
    assert b"Invalid username or password" in failure_response.data


def test_dashboard(authenticated_client):
    response = authenticated_client.get("/")
    assert response.status_code == 200
    assert b"Expense CRM Dashboard" in response.data


def test_create_expense_and_list(authenticated_client):
    response = authenticated_client.post(
        "/create-expense",
        data={
            "title": "Rent",
            "amount": "15000",
            "category": "Housing",
            "payment_mode": "Bank Transfer",
            "date": "2026-07-31",
            "notes": "Monthly rent",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Rent" in response.data
    assert b"Housing" in response.data


def test_viewer_can_create_expense(client, db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM expenses")
    cur.execute("DELETE FROM users")
    cur.execute("DELETE FROM sqlite_sequence")
    cur.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (
            "viewer",
            "scrypt:32768:8:1$at2ye7brAo9xsoOq$d50a4a78b80b5c578b14d786cd28035e9576702da783f95640ea381c3d5ba64ab4607373c96214da37819e47cd161e0beb10f46577c068fad6bf0fd1f1609309",
            "viewer",
        ),
    )
    conn.commit()
    conn.close()

    client.post(
        "/login",
        data={"username": "viewer", "password": "password123"},
        follow_redirects=True,
    )

    response = client.post(
        "/create-expense",
        data={
            "title": "Groceries",
            "amount": "450",
            "category": "Food",
            "payment_mode": "UPI",
            "date": "2026-07-31",
            "notes": "Daily essentials",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Groceries" in response.data
    assert b"Food" in response.data


def test_create_expense_form_supports_default_zero_and_frequency(authenticated_client):
    form_response = authenticated_client.get("/create-expense")
    assert form_response.status_code == 200
    assert b'value="0.00"' in form_response.data
    assert b'name="frequency"' in form_response.data

    submit_response = authenticated_client.post(
        "/create-expense",
        data={
            "title": "Groceries",
            "amount": "0",
            "category": "Food",
            "payment_mode": "UPI",
            "date": "2026-07-31",
            "frequency": "Monthly",
            "notes": "Household essentials",
        },
        follow_redirects=True,
    )
    assert submit_response.status_code == 200
    assert b"Groceries" in submit_response.data
    assert b"Monthly" in submit_response.data


def test_edit_expense(authenticated_client, db_path):
    authenticated_client.post(
        "/create-expense",
        data={
            "title": "Subscription",
            "amount": "500",
            "category": "Subscriptions",
            "payment_mode": "Card",
            "date": "2026-07-31",
            "notes": "Monthly plan",
        },
        follow_redirects=True,
    )

    conn = sqlite3.connect(db_path)
    expense_id = conn.execute("SELECT id FROM expenses ORDER BY id DESC LIMIT 1").fetchone()[0]
    conn.close()

    edit_page = authenticated_client.get(f"/edit-expense/{expense_id}")
    assert edit_page.status_code == 200
    assert b"Edit Expense" in edit_page.data
    assert b"Subscription" in edit_page.data

    update_response = authenticated_client.post(
        f"/edit-expense/{expense_id}",
        data={
            "title": "Subscription Updated",
            "amount": "550",
            "category": "Subscriptions",
            "payment_mode": "Card",
            "date": "2026-08-01",
            "frequency": "Monthly",
            "notes": "Monthly plan updated",
        },
        follow_redirects=True,
    )
    assert update_response.status_code == 200
    assert b"Subscription Updated" in update_response.data
    assert "₹550.00" in update_response.get_data(as_text=True)


def test_delete_expense(authenticated_client, db_path):
    authenticated_client.post(
        "/create-expense",
        data={
            "title": "Office Lunch",
            "amount": "300",
            "category": "Food",
            "payment_mode": "Cash",
            "date": "2026-07-31",
            "notes": "Team lunch",
        },
        follow_redirects=True,
    )

    conn = sqlite3.connect(db_path)
    expense_id = conn.execute("SELECT id FROM expenses ORDER BY id DESC LIMIT 1").fetchone()[0]
    conn.close()

    delete_response = authenticated_client.post(
        f"/delete-expense/{expense_id}",
        follow_redirects=True,
    )
    assert delete_response.status_code == 200
    assert b"Office Lunch" not in delete_response.data
    assert b"Expense deleted successfully" in delete_response.data


def test_income_override_and_monthly_grouping(authenticated_client):
    authenticated_client.post(
        "/create-expense",
        data={
            "title": "Groceries",
            "amount": "450",
            "category": "Food",
            "payment_mode": "UPI",
            "date": "2026-07-10",
            "notes": "Weekly shop",
        },
        follow_redirects=True,
    )
    authenticated_client.post(
        "/create-expense",
        data={
            "title": "Fuel",
            "amount": "200",
            "category": "Travel",
            "payment_mode": "Card",
            "date": "2026-07-15",
            "notes": "Fuel",
        },
        follow_redirects=True,
    )
    authenticated_client.post(
        "/create-expense",
        data={
            "title": "Hotel",
            "amount": "800",
            "category": "Travel",
            "payment_mode": "Card",
            "date": "2026-08-01",
            "notes": "Weekend stay",
        },
        follow_redirects=True,
    )

    override_response = authenticated_client.post(
        "/preferences",
        json={"income_override": 2500},
    )
    assert override_response.status_code == 200

    dashboard_response = authenticated_client.get("/")
    assert dashboard_response.status_code == 200
    assert b"2,500.00" in dashboard_response.data

    reports_response = authenticated_client.get("/reports")
    assert reports_response.status_code == 200
    assert b"2,500.00" in reports_response.data

    expenses_response = authenticated_client.get("/expenses")
    assert expenses_response.status_code == 200
    assert b"July 2026" in expenses_response.data
    assert b"August 2026" in expenses_response.data
    assert b">2<" in expenses_response.data


def test_reports_heatmap_month_filter(authenticated_client):
    authenticated_client.post(
        "/api/incomes",
        json={
            "source": "Salary",
            "amount": 50000,
            "date": "2026-07-15",
            "notes": "July salary",
        },
    )
    authenticated_client.post(
        "/create-expense",
        data={
            "title": "July Rent",
            "amount": "15000",
            "category": "Housing",
            "payment_mode": "Bank Transfer",
            "date": "2026-07-05",
            "notes": "Rent",
        },
        follow_redirects=True,
    )
    response = authenticated_client.get("/reports?month=2026-07")
    assert response.status_code == 200
    assert b"2026-07" in response.data
    assert b"Income: \xe2\x82\xb930,000.00" not in response.data
    assert b"Spending heatmap" in response.data

    response_aug = authenticated_client.get("/reports?month=2026-08")
    assert response_aug.status_code == 200
    assert b"2026-08" in response_aug.data
    assert b"July Rent" not in response_aug.data


def test_income_display_on_expenses_and_reports(authenticated_client):
    authenticated_client.post(
        "/api/incomes",
        json={
            "source": "Salary",
            "amount": 30000,
            "date": "2026-07-20",
            "notes": "July salary",
        },
    )
    authenticated_client.post(
        "/create-expense",
        data={
            "title": "July Grocery",
            "amount": "2000",
            "category": "Food",
            "payment_mode": "UPI",
            "date": "2026-07-21",
            "notes": "Groceries",
        },
        follow_redirects=True,
    )
    expenses_response = authenticated_client.get("/expenses")
    assert expenses_response.status_code == 200
    assert b"Income: \xe2\x82\xb930,000.00" in expenses_response.data

    reports_response = authenticated_client.get("/reports?month=2026-07")
    assert reports_response.status_code == 200
    assert b"Income: \xe2\x82\xb930,000.00" in reports_response.data


def test_language_switch_uses_hindi_translation(client):
    response = client.get("/set-language/hi", follow_redirects=True)
    assert response.status_code == 200

    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert "लॉगिन".encode("utf-8") in login_page.data


def test_income_can_be_created_and_appears_in_dashboard_summary(authenticated_client):
    income_response = authenticated_client.post(
        "/api/incomes",
        json={
            "source": "Salary",
            "amount": 65000,
            "date": "2026-07-31",
            "notes": "Monthly salary",
        },
    )
    assert income_response.status_code == 200
    assert income_response.get_json()["source"] == "Salary"

    dashboard_response = authenticated_client.get("/")
    assert dashboard_response.status_code == 200
    assert b"Salary" not in dashboard_response.data
    assert b"Total Income" in dashboard_response.data
    assert b"Remaining Balance" in dashboard_response.data


def test_split_expenses_and_analytics_endpoints_work(authenticated_client, db_path):
    expense_response = authenticated_client.post(
        "/create-expense",
        data={
            "title": "Shared dinner",
            "amount": "1200",
            "category": "Food",
            "payment_mode": "UPI",
            "date": "2026-07-31",
            "notes": "Dinner split",
        },
        follow_redirects=True,
    )
    assert expense_response.status_code == 200

    conn = sqlite3.connect(db_path)
    expense_id = conn.execute("SELECT id FROM expenses ORDER BY id DESC LIMIT 1").fetchone()[0]
    conn.close()

    split_response = authenticated_client.post(
        "/api/expenses/split",
        json={
            "expense_id": expense_id,
            "splits": [{"category": "Food", "amount": 600}, {"category": "Travel", "amount": 600, "shared_with": "Friend"}],
        },
    )
    assert split_response.status_code == 200
    assert len(split_response.get_json()["splits"]) == 2

    tags_response = authenticated_client.post(
        "/api/expenses/tags",
        json={"expense_id": expense_id, "tags": ["dinner", "friends"]},
    )
    assert tags_response.status_code == 200

    fields_response = authenticated_client.post(
        "/api/expenses/fields",
        json={"expense_id": expense_id, "fields": [{"name": "location", "value": "Cafe"}]},
    )
    assert fields_response.status_code == 200

    savings_response = authenticated_client.post(
        "/api/savings-goals",
        json={"name": "Trip", "target_amount": 10000, "deadline": "2026-12-31", "current_amount": 2000},
    )
    assert savings_response.status_code == 200

    prediction_response = authenticated_client.get("/api/reports/balance-prediction")
    assert prediction_response.status_code == 200

    comparison_response = authenticated_client.get("/api/reports/category-comparison")
    assert comparison_response.status_code == 200
    assert comparison_response.get_json()


def test_ai_natural_language_endpoints(authenticated_client):
    query_response = authenticated_client.get("/api/ai/query?question=Top%203%20categories%20this%20quarter")
    assert query_response.status_code == 200
    assert query_response.get_json()["answer"]

    insights_response = authenticated_client.get("/api/ai/insights")
    assert insights_response.status_code == 200
    assert insights_response.get_json()["insights"]


def test_shared_dashboard_and_role_based_permissions(client, db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM dashboard_members")
    cur.execute("DELETE FROM expenses")
    cur.execute("DELETE FROM users")
    cur.execute("DELETE FROM sqlite_sequence")
    cur.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        ("admin", "scrypt:32768:8:1$at2ye7brAo9xsoOq$d50a4a78b80b5c578b14d786cd28035e9576702da783f95640ea381c3d5ba64ab4607373c96214da37819e47cd161e0beb10f46577c068fad6bf0fd1f1609309", "admin"),
    )
    cur.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        ("viewer", "scrypt:32768:8:1$at2ye7brAo9xsoOq$d50a4a78b80b5c578b14d786cd28035e9576702da783f95640ea381c3d5ba64ab4607373c96214da37819e47cd161e0beb10f46577c068fad6bf0fd1f1609309", "viewer"),
    )
    cur.execute(
        "INSERT INTO dashboard_members (owner_id, user_id, role) VALUES (?, ?, ?)",
        (1, 2, "viewer"),
    )
    cur.execute(
        "INSERT INTO expenses (title, amount, category, payment_mode, expense_date, notes, owner_id, frequency) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("Shared lunch", 400, "Food", "Cash", "2026-07-31", "Shared", 1, "One-time"),
    )
    conn.commit()
    conn.close()

    client.post("/login", data={"username": "admin", "password": "password123"}, follow_redirects=True)
    admin_response = client.get("/expenses")
    assert admin_response.status_code == 200

    client.post("/login", data={"username": "viewer", "password": "password123"}, follow_redirects=True)
    shared_response = client.get("/expenses")
    assert shared_response.status_code == 200
    assert b"Shared lunch" in shared_response.data

    forbidden_response = client.post(
        "/create-expense",
        data={"title": "Blocked", "amount": "10", "category": "Food", "payment_mode": "Cash", "date": "2026-07-31"},
        follow_redirects=True,
    )
    assert forbidden_response.status_code == 403

    pdf_response = client.get("/reports/export/pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.mimetype == "application/pdf"

    excel_response = client.get("/reports/export/excel")
    assert excel_response.status_code == 200
    assert excel_response.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_recurring_expenses_can_be_created_and_auto_generated(authenticated_client):
    create_response = authenticated_client.post(
        "/api/recurring-expenses",
        json={
            "title": "Rent",
            "amount": 15000,
            "category": "Housing",
            "payment_mode": "Bank Transfer",
            "frequency": "monthly",
            "next_due_date": "2026-08-01",
            "notes": "Monthly rent",
        },
    )
    assert create_response.status_code == 200
    payload = create_response.get_json()
    assert payload["frequency"] == "monthly"
    assert payload["title"] == "Rent"

    list_response = authenticated_client.get("/api/recurring-expenses")
    assert list_response.status_code == 200
    assert len(list_response.get_json()) == 1

    auto_response = authenticated_client.post(
        "/api/recurring-expenses/auto-entry",
        json={"date": "2026-08-01"},
    )
    assert auto_response.status_code == 200
    assert auto_response.get_json()["generated"] >= 1

    expenses_response = authenticated_client.get("/expenses")
    assert expenses_response.status_code == 200
    assert b"Rent" in expenses_response.data


def test_reports_page_returns_html(authenticated_client):
    response = authenticated_client.get("/reports")
    assert response.status_code == 200
    assert b"Expense Reports" in response.data


def test_sensitive_fields_are_encrypted_and_audit_log_is_recorded(authenticated_client, db_path):
    response = authenticated_client.post(
        "/create-expense",
        data={
            "title": "Confidential dinner",
            "amount": "250",
            "category": "Food",
            "payment_mode": "UPI",
            "date": "2026-07-31",
            "notes": "Meeting details",
            "receipt": "Receipt #123",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT notes, receipt_data FROM expenses ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()

    assert row[0] != "Meeting details"
    assert row[1] != "Receipt #123"

    conn = sqlite3.connect(db_path)
    audit_rows = conn.execute("SELECT action, entity_type FROM audit_logs ORDER BY id DESC LIMIT 2").fetchall()
    conn.close()
    assert any(action[0] == "create" for action in audit_rows)


def test_backup_endpoint_creates_archive(authenticated_client):
    response = authenticated_client.get("/api/backup/export")
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
