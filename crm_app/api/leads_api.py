from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from crm_app.db import get_db_connection

lead_api = Blueprint("lead_api", __name__)


def lead_to_dict(lead_row):
    return {
        "id": lead_row["id"],
        "name": lead_row["name"],
        "email": lead_row["email"],
        "phone": lead_row["phone"],
        "company": lead_row["company"],
        "status": lead_row["status"],
    }


@lead_api.route("/api/leads", methods=["GET"])
@login_required
def get_leads():
    conn = get_db_connection()
    if current_user.role == "admin":
        rows = conn.execute("SELECT id, name, email, phone, company, status FROM leads ORDER BY id DESC").fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, email, phone, company, status FROM leads WHERE owner_id = ? ORDER BY id DESC",
            (int(current_user.get_id()),),
        ).fetchall()
    conn.close()
    return jsonify({"success": True, "data": [lead_to_dict(row) for row in rows]})


@lead_api.route("/api/leads/<int:lead_id>", methods=["GET"])
@login_required
def get_lead(lead_id):
    conn = get_db_connection()
    row = conn.execute("SELECT id, name, email, phone, company, status, owner_id FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    if row is None:
        return jsonify({"success": False, "error": "Lead not found"}), 404
    if current_user.role != "admin" and row["owner_id"] != int(current_user.get_id()):
        return jsonify({"success": False, "error": "Access denied"}), 403
    return jsonify({"success": True, "data": lead_to_dict(row)})


@lead_api.route("/api/leads", methods=["POST"])
@login_required
def create_lead():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "error": "Invalid JSON payload"}), 400

    name = payload.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "error": "Name is required"}), 400

    email = payload.get("email", "").strip()
    phone = payload.get("phone", "").strip()
    company = payload.get("company", "").strip()
    status = payload.get("status", "Open").strip() or "Open"

    conn = get_db_connection()
    cursor = conn.execute(
        "INSERT INTO leads (name, email, phone, company, status, owner_id) VALUES (?, ?, ?, ?, ?, ?)",
        (name, email, phone, company, status, int(current_user.get_id())),
    )
    conn.commit()
    lead_id = cursor.lastrowid
    row = conn.execute("SELECT id, name, email, phone, company, status FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()

    return jsonify({"success": True, "message": "Lead created", "data": lead_to_dict(row)}), 201


@lead_api.route("/api/leads/<int:lead_id>", methods=["PUT"])
@login_required
def update_lead(lead_id):
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "error": "Invalid JSON payload"}), 400

    conn = get_db_connection()
    row = conn.execute("SELECT id, owner_id FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"success": False, "error": "Lead not found"}), 404
    if current_user.role != "admin" and row["owner_id"] != int(current_user.get_id()):
        conn.close()
        return jsonify({"success": False, "error": "Access denied"}), 403

    name = payload.get("name")
    email = payload.get("email")
    phone = payload.get("phone")
    company = payload.get("company")
    status = payload.get("status")

    conn.execute(
        "UPDATE leads SET name = COALESCE(?, name), email = COALESCE(?, email), phone = COALESCE(?, phone), company = COALESCE(?, company), status = COALESCE(?, status) WHERE id = ?",
        (name, email, phone, company, status, lead_id),
    )
    conn.commit()
    updated = conn.execute("SELECT id, name, email, phone, company, status FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    return jsonify({"success": True, "message": "Lead updated", "data": lead_to_dict(updated)})


@lead_api.route("/api/leads/<int:lead_id>", methods=["DELETE"])
@login_required
def delete_lead(lead_id):
    if current_user.role != "admin":
        return jsonify({"success": False, "error": "Admin access required"}), 403

    conn = get_db_connection()
    row = conn.execute("SELECT id FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"success": False, "error": "Lead not found"}), 404

    conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Lead deleted"})
