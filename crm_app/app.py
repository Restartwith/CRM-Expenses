import os
import sqlite3
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from werkzeug.security import generate_password_hash

from crm_app.config import Config
from crm_app.api.leads_api import lead_api
from crm_app.api.contacts_api import contact_api
from crm_app.api.deals_api import deal_api
from crm_app.models.user import User

BASE_DIR = Path(__file__).resolve().parent.parent


def resolve_db_path() -> Path:
    env_db_path = os.environ.get("DB_PATH")
    if env_db_path:
        return Path(env_db_path)

    if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
        return Path("/tmp/crm.db")

    if os.environ.get("PYTEST_CURRENT_TEST") is not None or os.environ.get("PYTEST_VERSION") is not None:
        return BASE_DIR / "tests" / "crm.db"

    return BASE_DIR / "database" / "crm.db"


DB_PATH = resolve_db_path()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
app.config.from_object(Config)
app.register_blueprint(lead_api)
app.register_blueprint(contact_api)
app.register_blueprint(deal_api)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


def get_db_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_lead_status_counts():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT status, COUNT(*) as count FROM leads GROUP BY status ORDER BY status"
    ).fetchall()
    conn.close()
    return [{"status": row["status"], "count": row["count"]} for row in rows]


def get_deal_stage_totals():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT stage, COALESCE(SUM(amount), 0) as total FROM deals GROUP BY stage ORDER BY stage"
    ).fetchall()
    conn.close()
    return [{"stage": row["stage"] or "Unspecified", "total": float(row["total"]) or 0.0} for row in rows]


def get_dashboard_counts():
    conn = get_db_connection()
    counts = {
        "leads": conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0],
        "contacts": conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0],
        "deals": conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0],
    }
    conn.close()
    return counts


def init_db():
    conn = get_db_connection()
    conn.execute(
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
    conn.execute(
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_name TEXT NOT NULL,
            amount REAL,
            stage TEXT
        )
        """
    )
    conn.execute(
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


def ensure_leads_owner_column():
    conn = get_db_connection()
    columns = [row[1] for row in conn.execute("PRAGMA table_info(leads)")]
    if "owner_id" not in columns:
        conn.execute("ALTER TABLE leads ADD COLUMN owner_id INTEGER")
        conn.commit()
    conn.close()


init_db()
ensure_leads_owner_column()


@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id, username, password_hash, role FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return User(row["id"], row["username"], row["password_hash"], row["role"])


@app.route("/")
@login_required
def dashboard():
    summary_counts = get_dashboard_counts()
    return render_template("dashboard.html", summary_counts=summary_counts)


@app.route("/create-lead", methods=["GET", "POST"])
@login_required
def create_lead():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        company = request.form.get("company", "").strip()

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO leads (name, email, phone, company, status, owner_id) VALUES (?, ?, ?, ?, ?, ?)",
            (name, email, phone, company, "Open", int(current_user.get_id())),
        )
        conn.commit()
        conn.close()

        return redirect(url_for("leads"))

    return render_template("create_lead.html")


@app.route("/leads")
@login_required
def leads():
    conn = get_db_connection()
    if current_user.role == "admin":
        leads_data = conn.execute(
            "SELECT id, name, email, phone, company, status FROM leads ORDER BY id DESC"
        ).fetchall()
    else:
        leads_data = conn.execute(
            "SELECT id, name, email, phone, company, status FROM leads WHERE owner_id = ? ORDER BY id DESC",
            (int(current_user.get_id()),),
        ).fetchall()
    conn.close()
    return render_template("leads.html", leads=leads_data)


@app.route("/create-contact", methods=["GET", "POST"])
@login_required
def create_contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        company = request.form.get("company", "").strip()

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO contacts (name, email, phone, company) VALUES (?, ?, ?, ?)",
            (name, email, phone, company),
        )
        conn.commit()
        conn.close()

        return redirect(url_for("contacts"))

    return render_template("create_contact.html")


@app.route("/contacts")
@login_required
def contacts():
    conn = get_db_connection()
    contacts_data = conn.execute(
        "SELECT id, name, email, phone, company FROM contacts ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template("contacts.html", contacts=contacts_data)


@app.route("/create-deal", methods=["GET", "POST"])
@login_required
def create_deal():
    if request.method == "POST":
        deal_name = request.form.get("deal_name", "").strip()
        amount = request.form.get("amount", "").strip()
        stage = request.form.get("stage", "").strip()

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO deals (deal_name, amount, stage) VALUES (?, ?, ?)",
            (deal_name, amount or None, stage),
        )
        conn.commit()
        conn.close()

        return redirect(url_for("deals"))

    return render_template("create_deal.html")


@app.route("/deals")
@login_required
def deals():
    conn = get_db_connection()
    deals_data = conn.execute(
        "SELECT id, deal_name, amount, stage FROM deals ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template("deals.html", deals=deals_data)


@app.route("/reports")
@login_required
def reports():
    lead_status_counts = get_lead_status_counts()
    deal_stage_totals = get_deal_stage_totals()
    return render_template(
        "reports.html",
        lead_status_counts=lead_status_counts,
        deal_stage_totals=deal_stage_totals,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db_connection()
        row = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        conn.close()

        if row is not None:
            user = User(row["id"], row["username"], row["password_hash"], row["role"])
            if user.check_password(password):
                login_user(user)
                return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            return render_template(
                "register.html",
                error="Username and password are required.",
            )

        conn = get_db_connection()
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if existing is not None:
            conn.close()
            return render_template(
                "register.html",
                error="Username already exists. Choose a different one.",
            )

        password_hash = generate_password_hash(password)
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, "user"),
        )
        conn.commit()
        conn.close()

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/api/docs")
@login_required
def api_docs():
    return jsonify({
        "success": True,
        "message": "CRM API documentation",
        "endpoints": {
            "leads": {
                "list": "/api/leads",
                "get": "/api/leads/<id>",
                "create": "/api/leads",
                "update": "/api/leads/<id>",
                "delete": "/api/leads/<id>"
            },
            "contacts": {
                "list": "/api/contacts",
                "get": "/api/contacts/<id>",
                "create": "/api/contacts",
                "update": "/api/contacts/<id>",
                "delete": "/api/contacts/<id>"
            },
            "deals": {
                "list": "/api/deals",
                "get": "/api/deals/<id>",
                "create": "/api/deals",
                "update": "/api/deals/<id>",
                "delete": "/api/deals/<id>"
            }
        },
        "notes": {
            "auth": "All endpoints require login.",
            "admin": "Admin role required for delete operations.",
            "request_type": "POST/PUT endpoints expect JSON payloads."
        },
        "swagger_ui": "/api/docs/ui"
    })


@app.route("/api/docs/ui")
@login_required
def api_docs_ui():
    return render_template("swagger_ui.html")


@app.route("/api/openapi.json")
@login_required
def api_openapi():
    return jsonify({
        "openapi": "3.0.3",
        "info": {
            "title": "CRM API",
            "version": "1.0.0",
            "description": "Simple CRM API for leads, contacts, and deals. Requires login and uses session-based authentication."
        },
        "servers": [{"url": "http://127.0.0.1:5000"}],
        "components": {
            "securitySchemes": {
                "cookieAuth": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "session"
                }
            },
            "schemas": {
                "Lead": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "email": {"type": "string", "nullable": true},
                        "phone": {"type": "string", "nullable": true},
                        "company": {"type": "string", "nullable": true},
                        "status": {"type": "string"}
                    },
                    "required": ["id", "name", "status"]
                },
                "Contact": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "email": {"type": "string", "nullable": true},
                        "phone": {"type": "string", "nullable": true},
                        "company": {"type": "string", "nullable": true}
                    },
                    "required": ["id", "name"]
                },
                "Deal": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "deal_name": {"type": "string"},
                        "amount": {"type": "number", "nullable": true},
                        "stage": {"type": "string", "nullable": true}
                    },
                    "required": ["id", "deal_name"]
                }
            }
        },
        "security": [{"cookieAuth": []}],
        "paths": {
            "/api/leads": {
                "get": {
                    "summary": "List leads",
                    "responses": {
                        "200": {
                            "description": "List of lead objects",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "data": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/Lead"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "post": {
                    "summary": "Create a lead",
                    "requestBody": {
                        "required": true,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "email": {"type": "string"},
                                        "phone": {"type": "string"},
                                        "company": {"type": "string"},
                                        "status": {"type": "string"}
                                    },
                                    "required": ["name"]
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {"description": "Lead created"}
                    }
                }
            },
            "/api/leads/{lead_id}": {
                "get": {
                    "summary": "Get a lead",
                    "parameters": [{
                        "name": "lead_id",
                        "in": "path",
                        "required": true,
                        "schema": {"type": "integer"}
                    }],
                    "responses": {"200": {"description": "Lead details"}}
                },
                "put": {
                    "summary": "Update a lead",
                    "parameters": [{
                        "name": "lead_id",
                        "in": "path",
                        "required": true,
                        "schema": {"type": "integer"}
                    }],
                    "requestBody": {
                        "required": true,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "email": {"type": "string"},
                                        "phone": {"type": "string"},
                                        "company": {"type": "string"},
                                        "status": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Lead updated"}}
                },
                "delete": {
                    "summary": "Delete a lead",
                    "parameters": [{
                        "name": "lead_id",
                        "in": "path",
                        "required": true,
                        "schema": {"type": "integer"}
                    }],
                    "responses": {"200": {"description": "Lead deleted"}}
                }
            },
            "/api/contacts": {
                "get": {
                    "summary": "List contacts",
                    "responses": {"200": {"description": "List of contacts"}}
                },
                "post": {
                    "summary": "Create a contact",
                    "requestBody": {
                        "required": true,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "email": {"type": "string"},
                                        "phone": {"type": "string"},
                                        "company": {"type": "string"}
                                    },
                                    "required": ["name"]
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "Contact created"}}
                }
            },
            "/api/contacts/{contact_id}": {
                "get": {
                    "summary": "Get a contact",
                    "parameters": [{
                        "name": "contact_id",
                        "in": "path",
                        "required": true,
                        "schema": {"type": "integer"}
                    }],
                    "responses": {"200": {"description": "Contact details"}}
                },
                "put": {
                    "summary": "Update a contact",
                    "parameters": [{
                        "name": "contact_id",
                        "in": "path",
                        "required": true,
                        "schema": {"type": "integer"}
                    }],
                    "requestBody": {
                        "required": true,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "email": {"type": "string"},
                                        "phone": {"type": "string"},
                                        "company": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Contact updated"}}
                },
                "delete": {
                    "summary": "Delete a contact",
                    "parameters": [{
                        "name": "contact_id",
                        "in": "path",
                        "required": true,
                        "schema": {"type": "integer"}
                    }],
                    "responses": {"200": {"description": "Contact deleted"}}
                }
            },
            "/api/deals": {
                "get": {
                    "summary": "List deals",
                    "responses": {"200": {"description": "List of deals"}}
                },
                "post": {
                    "summary": "Create a deal",
                    "requestBody": {
                        "required": true,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "deal_name": {"type": "string"},
                                        "amount": {"type": "number"},
                                        "stage": {"type": "string"}
                                    },
                                    "required": ["deal_name"]
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "Deal created"}}
                }
            },
            "/api/deals/{deal_id}": {
                "get": {
                    "summary": "Get a deal",
                    "parameters": [{
                        "name": "deal_id",
                        "in": "path",
                        "required": true,
                        "schema": {"type": "integer"}
                    }],
                    "responses": {"200": {"description": "Deal details"}}
                },
                "put": {
                    "summary": "Update a deal",
                    "parameters": [{
                        "name": "deal_id",
                        "in": "path",
                        "required": true,
                        "schema": {"type": "integer"}
                    }],
                    "requestBody": {
                        "required": true,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "deal_name": {"type": "string"},
                                        "amount": {"type": "number"},
                                        "stage": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Deal updated"}}
                },
                "delete": {
                    "summary": "Delete a deal",
                    "parameters": [{
                        "name": "deal_id",
                        "in": "path",
                        "required": true,
                        "schema": {"type": "integer"}
                    }],
                    "responses": {"200": {"description": "Deal deleted"}}
                }
            }
        }
    })


if __name__ == "__main__":
    app.run(debug=True)
