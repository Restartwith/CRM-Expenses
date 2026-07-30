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
    cur.execute("DELETE FROM leads")
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

    client.post(
        "/login",
        data={"username": "admin", "password": "password123"},
        follow_redirects=True,
    )
    return client


@pytest.fixture
def regular_user_client(client, db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM leads")
    cur.execute("DELETE FROM users")
    cur.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (
            "maria",
            "scrypt:32768:8:1$at2ye7brAo9xsoOq$d50a4a78b80b5c578b14d786cd28035e9576702da783f95640ea381c3d5ba64ab4607373c96214da37819e47cd161e0beb10f46577c068fad6bf0fd1f1609309",
            "user",
        ),
    )
    conn.commit()
    conn.close()

    client.post(
        "/login",
        data={"username": "maria", "password": "password123"},
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
    assert b"CRM Dashboard" in success_response.data

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
    assert b"CRM Dashboard" in response.data


def test_create_lead_and_list(authenticated_client):
    response = authenticated_client.post(
        "/create-lead",
        data={
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "555-0100",
            "company": "Example Co",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Jane Doe" in response.data
    assert b"Example Co" in response.data


def test_admin_can_view_all_leads(authenticated_client):
    authenticated_client.post(
        "/create-lead",
        data={
            "name": "Admin Lead",
            "email": "admin@example.com",
            "company": "Admin Co",
        },
    )

    response = authenticated_client.get("/leads")
    assert response.status_code == 200
    assert b"Admin Lead" in response.data


def test_regular_user_only_sees_their_own_leads(regular_user_client):
    regular_user_client.post(
        "/create-lead",
        data={
            "name": "User Lead",
            "email": "user@example.com",
            "company": "User Co",
        },
    )

    response = regular_user_client.get("/leads")
    assert response.status_code == 200
    assert b"User Lead" in response.data
    assert b"Admin Lead" not in response.data


def test_reports_page_returns_html(authenticated_client):
    response = authenticated_client.get("/reports")
    assert response.status_code == 200
    assert b"Reports" in response.data
