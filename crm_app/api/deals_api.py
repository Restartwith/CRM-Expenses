from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from crm_app.db import get_db_connection

deal_api = Blueprint("deal_api", __name__)


def deal_to_dict(deal_row):
    return {
        "id": deal_row["id"],
        "deal_name": deal_row["deal_name"],
        "amount": deal_row["amount"],
        "stage": deal_row["stage"],
    }


@deal_api.route("/api/deals", methods=["GET"])
@login_required
def get_deals():
    conn = get_db_connection()
    rows = conn.execute("SELECT id, deal_name, amount, stage FROM deals ORDER BY id DESC").fetchall()
    conn.close()
    return jsonify({"success": True, "data": [deal_to_dict(row) for row in rows]})


@deal_api.route("/api/deals/<int:deal_id>", methods=["GET"])
@login_required
def get_deal(deal_id):
    conn = get_db_connection()
    row = conn.execute("SELECT id, deal_name, amount, stage FROM deals WHERE id = ?", (deal_id,)).fetchone()
    conn.close()
    if row is None:
        return jsonify({"success": False, "error": "Deal not found"}), 404
    return jsonify({"success": True, "data": deal_to_dict(row)})


@deal_api.route("/api/deals", methods=["POST"])
@login_required
def create_deal_api():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "error": "Invalid JSON payload"}), 400

    deal_name = payload.get("deal_name", "").strip()
    if not deal_name:
        return jsonify({"success": False, "error": "Deal name is required"}), 400

    amount = payload.get("amount")
    stage = payload.get("stage", "").strip()

    conn = get_db_connection()
    cursor = conn.execute(
        "INSERT INTO deals (deal_name, amount, stage) VALUES (?, ?, ?)",
        (deal_name, amount, stage),
    )
    conn.commit()
    deal_id = cursor.lastrowid
    row = conn.execute("SELECT id, deal_name, amount, stage FROM deals WHERE id = ?", (deal_id,)).fetchone()
    conn.close()

    return jsonify({"success": True, "message": "Deal created", "data": deal_to_dict(row)}), 201


@deal_api.route("/api/deals/<int:deal_id>", methods=["PUT"])
@login_required
def update_deal(deal_id):
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "error": "Invalid JSON payload"}), 400

    conn = get_db_connection()
    row = conn.execute("SELECT id FROM deals WHERE id = ?", (deal_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"success": False, "error": "Deal not found"}), 404

    deal_name = payload.get("deal_name")
    amount = payload.get("amount")
    stage = payload.get("stage")

    conn.execute(
        "UPDATE deals SET deal_name = COALESCE(?, deal_name), amount = COALESCE(?, amount), stage = COALESCE(?, stage) WHERE id = ?",
        (deal_name, amount, stage, deal_id),
    )
    conn.commit()
    updated = conn.execute("SELECT id, deal_name, amount, stage FROM deals WHERE id = ?", (deal_id,)).fetchone()
    conn.close()

    return jsonify({"success": True, "message": "Deal updated", "data": deal_to_dict(updated)})


@deal_api.route("/api/deals/<int:deal_id>", methods=["DELETE"])
@login_required
def delete_deal(deal_id):
    if current_user.role != "admin":
        return jsonify({"success": False, "error": "Admin access required"}), 403

    conn = get_db_connection()
    row = conn.execute("SELECT id FROM deals WHERE id = ?", (deal_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"success": False, "error": "Deal not found"}), 404

    conn.execute("DELETE FROM deals WHERE id = ?", (deal_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Deal deleted"})
