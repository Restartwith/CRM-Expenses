from flask import Blueprint, jsonify

lead_api = Blueprint("lead_api", __name__)


@lead_api.route("/api/leads")
def get_leads_api():
    return jsonify({"message": "API Working"})
