from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from crm_app.db import get_db_connection

contact_api = Blueprint("contact_api", __name__)


def contact_to_dict(contact_row):
    return {
        "id": contact_row["id"],
        "name": contact_row["name"],
        "email": contact_row["email"],
        "phone": contact_row["phone"],
        "company": contact_row["company"],
    }


@contact_api.route("/api/contacts", methods=["GET"])
@login_required
def get_contacts():
    conn = get_db_connection()
    rows = conn.execute("SELECT id, name, email, phone, company FROM contacts ORDER BY id DESC").fetchall()
    conn.close()
    return jsonify({"success": True, "data": [contact_to_dict(row) for row in rows]})


@contact_api.route("/api/contacts/<int:contact_id>", methods=["GET"])
@login_required
def get_contact(contact_id):
    conn = get_db_connection()
    row = conn.execute("SELECT id, name, email, phone, company FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    conn.close()
    if row is None:
        return jsonify({"success": False, "error": "Contact not found"}), 404
    return jsonify({"success": True, "data": contact_to_dict(row)})


@contact_api.route("/api/contacts", methods=["POST"])
@login_required
def create_contact():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "error": "Invalid JSON payload"}), 400

    name = payload.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "error": "Name is required"}), 400

    email = payload.get("email", "").strip()
    phone = payload.get("phone", "").strip()
    company = payload.get("company", "").strip()

    conn = get_db_connection()
    cursor = conn.execute(
        "INSERT INTO contacts (name, email, phone, company) VALUES (?, ?, ?, ?)",
        (name, email, phone, company),
    )
    conn.commit()
    contact_id = cursor.lastrowid
    row = conn.execute("SELECT id, name, email, phone, company FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    conn.close()

    return jsonify({"success": True, "message": "Contact created", "data": contact_to_dict(row)}), 201


@contact_api.route("/api/contacts/<int:contact_id>", methods=["PUT"])
@login_required
def update_contact(contact_id):
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "error": "Invalid JSON payload"}), 400

    conn = get_db_connection()
    row = conn.execute("SELECT id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"success": False, "error": "Contact not found"}), 404

    name = payload.get("name")
    email = payload.get("email")
    phone = payload.get("phone")
    company = payload.get("company")

    conn.execute(
        "UPDATE contacts SET name = COALESCE(?, name), email = COALESCE(?, email), phone = COALESCE(?, phone), company = COALESCE(?, company) WHERE id = ?",
        (name, email, phone, company, contact_id),
    )
    conn.commit()
    updated = conn.execute("SELECT id, name, email, phone, company FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    conn.close()

    return jsonify({"success": True, "message": "Contact updated", "data": contact_to_dict(updated)})


@contact_api.route("/api/contacts/<int:contact_id>", methods=["DELETE"])
@login_required
def delete_contact(contact_id):
    if current_user.role != "admin":
        return jsonify({"success": False, "error": "Admin access required"}), 403

    conn = get_db_connection()
    row = conn.execute("SELECT id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"success": False, "error": "Contact not found"}), 404

    conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Contact deleted"})
