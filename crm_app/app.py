import base64
import hashlib
import io
import json
import os
import re
import sqlite3
import zipfile
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from werkzeug.security import generate_password_hash

from crm_app.config import Config
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
app.secret_key = Config.SECRET_KEY


def _get_cipher():
    secret = os.environ.get("FERNET_KEY") or app.secret_key or "crm-expenses-default-key"
    key_material = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


def _encrypt_value(value):
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return ""
    return _get_cipher().encrypt(str(value).encode("utf-8")).decode("utf-8")


def _decrypt_value(value):
    if value in (None, ""):
        return ""
    try:
        return _get_cipher().decrypt(value.encode("utf-8")).decode("utf-8")
    except Exception:
        return value


def log_audit_event(user_id, action, entity_type, entity_id=None, details=None):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, action, entity_type, entity_id, details, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


@app.before_request
def enforce_role_permissions():
    if request.path.startswith("/static") or request.endpoint in {"login", "register", "set_language", "logout"}:
        return None

    if not current_user.is_authenticated:
        return None

    if request.endpoint in {"create_expense", "parse_expense_api", "split_expense_api", "expense_tags_api", "expense_fields_api", "savings_goals_api", "recurring_expenses_api", "incomes_api", "reports"} and request.method != "GET":
        if not can_manage_expenses():
            return jsonify({"error": "Forbidden"}), 403
        return None

    if request.endpoint in {"dashboard", "expenses", "reports", "export_reports", "share_reports"}:
        if not can_view_dashboard():
            return jsonify({"error": "Forbidden"}), 403

    return None

TRANSLATIONS = {
    "en": {
        "dashboard": "Dashboard",
        "expenses": "Expenses",
        "add_expense": "Add Expense",
        "reports": "Reports",
        "logout": "Logout",
        "login": "Login",
        "register": "Register",
        "created_by": "Created by SURAJ SINGH",
        "language": "Language",
        "english": "English",
        "hindi": "हिन्दी",
        "marathi": "मराठी",
        "dashboard_title": "Expense CRM Dashboard",
        "dashboard_subtitle": "A simple workspace to monitor expenses and recent spending at a glance.",
        "add_expense_button": "+ Add Expense",
        "spending_by_category": "Spending by Category",
        "recent_transactions": "Recent Transactions",
        "no_expense_categories": "No expense categories yet.",
        "no_transactions": "No transactions yet.",
        "expense_ledger": "Expense Ledger",
        "expense_ledger_subtitle": "Track your daily and monthly spending clearly.",
        "total_recorded": "Total Recorded",
        "title": "Title",
        "category": "Category",
        "amount": "Amount",
        "payment": "Payment",
        "date": "Date",
        "frequency": "Frequency",
        "notes": "Notes",
        "no_expenses": "No expenses yet. Start by adding your first one.",
        "create_expense_heading": "Add your expense",
        "create_expense_subtitle": "Capture daily or monthly spending in seconds.",
        "view_expenses": "View Expenses",
        "tip": "Tip",
        "tip_text": "Use Monthly for rent, subscriptions, and bills, or Daily for meals, travel, and small purchases.",
        "payment_mode": "Payment mode",
        "save_expense": "Save Expense",
        "update_expense": "Update Expense",
        "edit_expense_heading": "Edit Expense",
        "edit_expense_subtitle": "Update your expense details quickly.",
        "actions": "Actions",
        "back_to_dashboard": "Back to Dashboard",
        "reports_title": "Expense Reports",
        "reports_subtitle": "Monitor your spending structure and financial health at a glance.",
        "financial_snapshot": "Financial Snapshot",
        "total_income": "Total Income",
        "total_expenses": "Total Expenses",
        "remaining_balance": "Remaining Balance",
        "savings": "Savings",
        "no_expense_data": "No expense data yet.",
        "login_title": "Login",
        "username": "Username",
        "password": "Password",
        "dont_have_account": "Don’t have an account?",
        "register_here": "Register here",
        "already_have_account": "Already have an account?",
        "login_here": "Login here",
        "register_title": "Register",
        "register_button": "Register",
        "login_button": "Login",
    },
    "hi": {
        "dashboard": "डैशबोर्ड",
        "expenses": "खर्च",
        "add_expense": "खर्च जोड़ें",
        "reports": "रिपोर्ट्स",
        "logout": "लॉगआउट",
        "login": "लॉगिन",
        "register": "रजिस्टर",
        "created_by": "सुरज सिंह द्वारा निर्मित",
        "language": "भाषा",
        "english": "English",
        "hindi": "हिन्दी",
        "marathi": "मराठी",
        "dashboard_title": "खर्च CRM डैशबोर्ड",
        "dashboard_subtitle": "खर्च और हाल के खर्चों पर एक नज़र रखने के लिए एक सरल स्थान।",
        "add_expense_button": "+ खर्च जोड़ें",
        "spending_by_category": "श्रेणी अनुसार खर्च",
        "recent_transactions": "हाल के लेनदेन",
        "no_expense_categories": "अभी कोई खर्च श्रेणी नहीं है।",
        "no_transactions": "अभी कोई लेनदेन नहीं हैं।",
        "expense_ledger": "खर्च बही",
        "expense_ledger_subtitle": "अपने दैनिक और मासिक खर्चों को स्पष्ट रूप से ट्रैक करें।",
        "total_recorded": "कुल दर्ज किया गया",
        "title": "शीर्षक",
        "category": "श्रेणी",
        "amount": "राशि",
        "payment": "भुगतान",
        "date": "तारीख",
        "frequency": "आवृत्ति",
        "notes": "नोट्स",
        "no_expenses": "अभी कोई खर्च नहीं है। अपनी पहली_ENTRY जोड़ें।",
        "create_expense_heading": "अपना खर्च जोड़ें",
        "create_expense_subtitle": "दैनिक या मासिक खर्चों को कुछ ही सेकंड में दर्ज करें।",
        "view_expenses": "खर्च देखें",
        "tip": "याद रखें",
        "tip_text": "किराया, सदस्यता और बिलों के लिए Monthly का उपयोग करें, या भोजन, यात्रा और छोटी खरीदारी के लिए Daily का उपयोग करें।",
        "payment_mode": "भुगतान तरीका",
        "save_expense": "खर्च सेव करें",
        "update_expense": "खर्च अपडेट करें",
        "edit_expense_heading": "खर्च संपादित करें",
        "edit_expense_subtitle": "तेजी से अपने खर्च के विवरण अपडेट करें।",
        "actions": "कार्य",
        "back_to_dashboard": "डैशबोर्ड पर वापस",
        "reports_title": "खर्च रिपोर्ट्स",
        "reports_subtitle": "अपने खर्चों की संरचना और वित्तीय स्थिति को एक झलक में देखें।",
        "financial_snapshot": "वित्तीय स्नैपशॉट",
        "total_income": "कुल आय",
        "total_expenses": "कुल खर्च",
        "remaining_balance": "शेष शेष राशि",
        "savings": "बचत",
        "no_expense_data": "अभी कोई खर्च डेटा नहीं है।",
        "login_title": "लॉगिन",
        "username": "उपयोगकर्ता नाम",
        "password": "पासवर्ड",
        "dont_have_account": "खाता नहीं है?",
        "register_here": "यहाँ रजिस्टर करें",
        "already_have_account": "पहले से खाता है?",
        "login_here": "यहाँ लॉगिन करें",
        "register_title": "रजिस्टर",
        "register_button": "रजिस्टर",
        "login_button": "लॉगिन",
    },
    "mr": {
        "dashboard": "डॅशबोर्ड",
        "expenses": "खर्च",
        "add_expense": "खर्च जोडा",
        "reports": "अहवाल",
        "logout": "लॉगआउट",
        "login": "लॉगिन",
        "register": "नोंदणी",
        "created_by": "सुरज सिंग यांनी तयार केले",
        "language": "भाषा",
        "english": "English",
        "hindi": "हिन्दी",
        "marathi": "मराठी",
        "dashboard_title": "खर्च CRM डॅशबोर्ड",
        "dashboard_subtitle": "खर्च आणि अलीकडील खर्चांची झटपट पाहणी करणारा एक सोपा विभाग।",
        "add_expense_button": "+ खर्च जोडा",
        "spending_by_category": "श्रेणीनुसार खर्च",
        "recent_transactions": "अलीकडील व्यवहार",
        "no_expense_categories": "अद्याप कोणत्याही खर्च श्रेणी नाहीत।",
        "no_transactions": "अद्याप कोणतेही व्यवहार नाहीत।",
        "expense_ledger": "खर्च लेजर",
        "expense_ledger_subtitle": "तुमचा दैनिक आणि मासिक खर्च स्पष्टपणे ट्रॅक करा।",
        "total_recorded": "एकूण नोंदणीकृत",
        "title": "शीर्षक",
        "category": "श्रेणी",
        "amount": "रक्कम",
        "payment": "पैसे देणे",
        "date": "तारीख",
        "frequency": "वारंवारता",
        "notes": "टिप्पण्या",
        "no_expenses": "अद्याप कोणताही खर्च नाही. तुमचा पहिला खर्च जोडा.",
        "create_expense_heading": "तुमचा खर्च जोडा",
        "create_expense_subtitle": "दैनिक किंवा मासिक खर्च काही सेकंदात नोंद करा.",
        "view_expenses": "खर्च पहा",
        "tip": "टीप",
        "tip_text": "किरा, सदस्यता आणि बिल्ससाठी Monthly वापरा, किंवा भोजन, प्रवास आणि लहान खरेदीसाठी Daily वापरा.",
        "payment_mode": "पैसे देण्याची पद्धत",
        "save_expense": "खर्च जतन करा",
        "update_expense": "खर्च अद्यतनित करा",
        "edit_expense_heading": "खर्च संपादित करा",
        "edit_expense_subtitle": "जलद तुमच्या खर्चाचे तपशील अद्यतनित करा.",
        "actions": "क्रिया",
        "back_to_dashboard": "डॅशबोर्डकडे परत",
        "reports_title": "खर्च अहवाल",
        "reports_subtitle": "तुमच्या खर्चाच्या रचनेची आणि आर्थिक स्थितीची झटपट पाहणी करा।",
        "financial_snapshot": "आर्थिक झलक",
        "total_income": "एकूण उत्पन्न",
        "total_expenses": "एकूण खर्च",
        "remaining_balance": "उर्वरित शिल्लक",
        "savings": "बचत",
        "no_expense_data": "अद्याप कोणतेही खर्च डेटा नाही.",
        "login_title": "लॉगिन",
        "username": "वापरकर्ता नाव",
        "password": "पासवर्ड",
        "dont_have_account": "खाते नाही का?",
        "register_here": "येथे नोंदणी करा",
        "already_have_account": "आधीपासून खाते आहे?",
        "login_here": "येथे लॉगिन करा",
        "register_title": "नोंदणी",
        "register_button": "नोंदणी",
        "login_button": "लॉगिन",
    },
}

SUPPORTED_LANGUAGES = {"en": "English", "hi": "हिन्दी", "mr": "मराठी"}

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


def get_user_language():
    lang = session.get("language", "en")
    return lang if lang in SUPPORTED_LANGUAGES else "en"


@app.context_processor
def inject_translations():
    lang = get_user_language()

    def t(key, default=None):
        return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, default or TRANSLATIONS["en"].get(key, key))

    return {
        "current_language": lang,
        "supported_languages": SUPPORTED_LANGUAGES,
        "t": t,
        "user_preferences": get_user_preferences(),
    }


def get_db_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _get_user_preferences_columns(conn):
    try:
        rows = conn.execute("PRAGMA table_info(user_preferences)").fetchall()
    except sqlite3.OperationalError:
        return []
    return [row["name"] for row in rows]


def get_user_preferences(user_id=None):
    user_id = user_id if user_id is not None else getattr(current_user, "get_id", lambda: None)()
    if not user_id:
        return {"theme": "light", "palette": "default", "contrast": False, "font_scale": 1.0, "income_override": None}
    conn = get_db_connection()
    try:
        columns = _get_user_preferences_columns(conn)
        if not columns:
            return {"theme": "light", "palette": "default", "contrast": False, "font_scale": 1.0, "income_override": None}
        select_columns = ["theme", "palette", "contrast_mode", "font_scale"]
        if "income_override" in columns:
            select_columns.append("income_override")
        query = "SELECT " + ", ".join(select_columns) + " FROM user_preferences WHERE user_id = ?"
        row = conn.execute(query, (int(user_id),)).fetchone()
    finally:
        conn.close()
    if not row:
        return {"theme": "light", "palette": "default", "contrast": False, "font_scale": 1.0, "income_override": None}
    income_override_value = None
    if "income_override" in row.keys() and row["income_override"] is not None:
        income_override_value = float(row["income_override"])
    return {
        "theme": row["theme"] or "light",
        "palette": row["palette"] or "default",
        "contrast": bool(row["contrast_mode"]),
        "font_scale": float(row["font_scale"] or 1.0),
        "income_override": income_override_value,
    }


def save_user_preferences(user_id, preferences):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (int(user_id),))
        columns = _get_user_preferences_columns(conn)
        income_override = preferences.get("income_override")
        income_override_value = None if income_override in (None, "") else float(income_override)
        if "income_override" in columns:
            conn.execute(
                "INSERT INTO user_preferences (user_id, theme, palette, contrast_mode, font_scale, income_override) VALUES (?, ?, ?, ?, ?, ?)",
                (int(user_id), preferences.get("theme", "light"), preferences.get("palette", "default"), 1 if preferences.get("contrast") else 0, float(preferences.get("font_scale", 1.0)), income_override_value),
            )
        else:
            conn.execute(
                "INSERT INTO user_preferences (user_id, theme, palette, contrast_mode, font_scale) VALUES (?, ?, ?, ?, ?)",
                (int(user_id), preferences.get("theme", "light"), preferences.get("palette", "default"), 1 if preferences.get("contrast") else 0, float(preferences.get("font_scale", 1.0))),
            )
        conn.commit()
    finally:
        conn.close()


def get_goal_streaks(owner_id=None):
    owner_id = owner_id if owner_id is not None else getattr(current_user, "get_id", lambda: None)()
    if not owner_id:
        return []
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, name, target_amount, deadline, current_amount FROM savings_goals WHERE owner_id = ? ORDER BY deadline ASC",
        (int(owner_id),),
    ).fetchall()
    conn.close()
    streaks = []
    for row in rows:
        progress = min(1.0, float(row["current_amount"]) / float(row["target_amount"]) if float(row["target_amount"]) else 0.0)
        streak_days = 5 if progress >= 0.5 else 3
        streaks.append({
            "id": row["id"],
            "name": row["name"],
            "badge": "Saved 5 days in a row" if streak_days == 5 else "Steady saver",
            "streak_days": streak_days,
        })
    return streaks


def get_visible_owner_ids(user_id=None):
    if user_id is None:
        user_id = getattr(current_user, "get_id", lambda: None)()
    if not user_id:
        return []
    user_id = int(user_id)
    conn = get_db_connection()
    owner_ids = [user_id]
    rows = conn.execute("SELECT owner_id FROM dashboard_members WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    owner_ids.extend(row["owner_id"] for row in rows)
    return list(dict.fromkeys(owner_ids))


def get_user_role(user_id=None):
    user_id = user_id if user_id is not None else getattr(current_user, "get_id", lambda: None)()
    if not user_id:
        return "viewer"
    conn = get_db_connection()
    row = conn.execute("SELECT role FROM users WHERE id = ?", (int(user_id),)).fetchone()
    conn.close()
    return row["role"] if row else "viewer"


def can_manage_expenses(user_id=None):
    role = get_user_role(user_id)
    if role == "admin":
        return True

    user_id = user_id if user_id is not None else getattr(current_user, "get_id", lambda: None)()
    if not user_id:
        return False

    conn = get_db_connection()
    admin_membership = conn.execute("SELECT 1 FROM dashboard_members WHERE user_id = ? AND role = 'admin'", (int(user_id),)).fetchone()
    shared_membership = conn.execute("SELECT 1 FROM dashboard_members WHERE user_id = ?", (int(user_id),)).fetchone()
    conn.close()

    if admin_membership is not None:
        return True
    if shared_membership is not None:
        return False
    return True


def can_view_dashboard(user_id=None):
    if can_manage_expenses(user_id):
        return True
    user_id = user_id if user_id is not None else getattr(current_user, "get_id", lambda: None)()
    if not user_id:
        return False
    return len(get_visible_owner_ids(user_id)) > 0


def get_visible_expenses(user_id=None):
    user_id = user_id if user_id is not None else getattr(current_user, "get_id", lambda: None)()
    if not user_id:
        return []
    owner_ids = get_visible_owner_ids(user_id)
    if not owner_ids:
        return []
    placeholders = ", ".join("?" for _ in owner_ids)
    conn = get_db_connection()
    rows = conn.execute(
        f"SELECT id, title, amount, category, payment_mode, expense_date, notes, receipt_data, frequency, owner_id FROM expenses WHERE owner_id IN ({placeholders}) ORDER BY expense_date DESC, id DESC",
        owner_ids,
    ).fetchall()
    conn.close()
    return [
        {
            **dict(row),
            "notes": _decrypt_value(row["notes"]),
            "receipt_data": _decrypt_value(row["receipt_data"]),
        }
        for row in rows
    ]


def get_expense_by_id(expense_id, user_id=None):
    user_id = user_id if user_id is not None else getattr(current_user, "get_id", lambda: None)()
    if not user_id:
        return None
    owner_ids = get_visible_owner_ids(user_id)
    if not owner_ids:
        return None
    placeholders = ", ".join("?" for _ in owner_ids)
    conn = get_db_connection()
    row = conn.execute(
        f"SELECT * FROM expenses WHERE id = ? AND owner_id IN ({placeholders})",
        (expense_id, *owner_ids),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {**dict(row), "notes": _decrypt_value(row["notes"]), "receipt_data": _decrypt_value(row["receipt_data"])}


def get_expense_related_values(expense_id, owner_id=None):
    owner_id = owner_id if owner_id is not None else getattr(current_user, "get_id", lambda: None)()
    conn = get_db_connection()
    tag_rows = conn.execute("SELECT tag FROM expense_tags WHERE expense_id = ? AND owner_id = ?", (expense_id, int(owner_id))).fetchall()
    field_rows = conn.execute("SELECT field_name, field_value FROM expense_fields WHERE expense_id = ? AND owner_id = ?", (expense_id, int(owner_id))).fetchall()
    split_rows = conn.execute("SELECT category, amount FROM expense_splits WHERE expense_id = ? AND owner_id = ?", (expense_id, int(owner_id))).fetchall()
    conn.close()
    tags_value = ", ".join(row["tag"] for row in tag_rows)
    custom_fields_value = "; ".join(f"{row['field_name']}:{row['field_value']}" for row in field_rows)
    split_details = "; ".join(f"{row['category']}:{row['amount']}" for row in split_rows)
    return tags_value, custom_fields_value, split_details


def get_dashboard_summary(owner_id=None):
    conn = get_db_connection()
    if owner_id is not None:
        owner_ids = get_visible_owner_ids(owner_id)
        if not owner_ids:
            return {"total_expenses": 0, "expense_count": 0, "income": 0, "remaining_balance": 0, "savings": 0}
        placeholders = ", ".join("?" for _ in owner_ids)
        summary = {
            "total_expenses": conn.execute(f"SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE owner_id IN ({placeholders})", owner_ids).fetchone()[0],
            "expense_count": conn.execute(f"SELECT COUNT(*) FROM expenses WHERE owner_id IN ({placeholders})", owner_ids).fetchone()[0],
            "income": conn.execute(f"SELECT COALESCE(SUM(amount), 0) FROM incomes WHERE owner_id IN ({placeholders})", owner_ids).fetchone()[0],
        }
    else:
        summary = {
            "total_expenses": conn.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses").fetchone()[0],
            "expense_count": conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0],
            "income": conn.execute("SELECT COALESCE(SUM(amount), 0) FROM incomes").fetchone()[0],
        }
    conn.close()

    preferences = get_user_preferences(owner_id) if owner_id is not None else get_user_preferences()
    override = preferences.get("income_override")
    if override is not None:
        summary["income"] = float(override)

    summary["remaining_balance"] = float(summary["income"]) - float(summary["total_expenses"])
    summary["savings"] = summary["remaining_balance"]
    return summary


def get_expense_category_totals(owner_id=None):
    conn = get_db_connection()
    if owner_id is not None:
        owner_ids = get_visible_owner_ids(owner_id)
        if not owner_ids:
            return []
        placeholders = ", ".join("?" for _ in owner_ids)
        rows = conn.execute(
            f"SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE owner_id IN ({placeholders}) GROUP BY category ORDER BY total DESC",
            owner_ids,
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses GROUP BY category ORDER BY total DESC"
        ).fetchall()
    conn.close()
    return [{"category": row["category"], "total": float(row["total"]) or 0.0} for row in rows]


def get_savings_goals(owner_id=None):
    conn = get_db_connection()
    owner_filter = " WHERE owner_id = ?" if owner_id is not None else ""
    params = [owner_id] if owner_id is not None else []
    rows = conn.execute(
        f"SELECT id, name, target_amount, deadline, current_amount FROM savings_goals{owner_filter} ORDER BY deadline ASC",
        params,
    ).fetchall()
    conn.close()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "target_amount": float(row["target_amount"]),
            "deadline": row["deadline"],
            "current_amount": float(row["current_amount"]),
        }
        for row in rows
    ]


def get_spending_heatmap(owner_id=None, month=None):
    month = month or date.today().strftime("%Y-%m")
    conn = get_db_connection()
    if owner_id is not None:
        owner_ids = get_visible_owner_ids(owner_id)
        if not owner_ids:
            return []
        placeholders = ", ".join("?" for _ in owner_ids)
        rows = conn.execute(
            f"SELECT substr(expense_date, 1, 10) as day, COALESCE(SUM(amount), 0) as total FROM expenses WHERE owner_id IN ({placeholders}) AND substr(expense_date, 1, 7) = ? GROUP BY day ORDER BY day",
            owner_ids + [month],
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT substr(expense_date, 1, 10) as day, COALESCE(SUM(amount), 0) as total FROM expenses WHERE substr(expense_date, 1, 7) = ? GROUP BY day ORDER BY day",
            (month,),
        ).fetchall()
    conn.close()
    totals_by_day = {row["day"]: float(row["total"]) or 0.0 for row in rows}
    year, month_number = map(int, month.split("-"))
    days_in_month = monthrange(year, month_number)[1]
    heatmap = []
    for day in range(1, days_in_month + 1):
        value = totals_by_day.get(f"{year:04d}-{month_number:02d}-{day:02d}", 0.0)
        intensity = 0
        if value >= 10000:
            intensity = 4
        elif value >= 5000:
            intensity = 3
        elif value >= 2000:
            intensity = 2
        elif value >= 500:
            intensity = 1
        heatmap.append({"day": day, "total": value, "intensity": intensity})
    return heatmap


def get_monthly_income_totals(owner_id=None):
    conn = get_db_connection()
    if owner_id is not None:
        owner_ids = get_visible_owner_ids(owner_id)
        if not owner_ids:
            conn.close()
            return {}
        placeholders = ", ".join("?" for _ in owner_ids)
        rows = conn.execute(
            f"SELECT substr(income_date, 1, 7) as month, COALESCE(SUM(amount), 0) as total FROM incomes WHERE owner_id IN ({placeholders}) GROUP BY month ORDER BY month DESC",
            owner_ids,
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT substr(income_date, 1, 7) as month, COALESCE(SUM(amount), 0) as total FROM incomes GROUP BY month ORDER BY month DESC"
        ).fetchall()
    conn.close()
    return {row["month"]: float(row["total"]) or 0.0 for row in rows}


def get_monthly_comparison(owner_id=None):
    today = date.today()
    current_month = today.strftime("%Y-%m")
    previous_month_date = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    conn = get_db_connection()
    if owner_id is not None:
        owner_ids = get_visible_owner_ids(owner_id)
        if not owner_ids:
            return []
        placeholders = ", ".join("?" for _ in owner_ids)
        current_rows = conn.execute(
            f"SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE owner_id IN ({placeholders}) AND substr(expense_date, 1, 7) = ? GROUP BY category ORDER BY total DESC",
            owner_ids + [current_month],
        ).fetchall()
        previous_rows = conn.execute(
            f"SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE owner_id IN ({placeholders}) AND substr(expense_date, 1, 7) = ? GROUP BY category ORDER BY total DESC",
            owner_ids + [previous_month_date],
        ).fetchall()
    else:
        current_rows = conn.execute(
            "SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE substr(expense_date, 1, 7) = ? GROUP BY category ORDER BY total DESC",
            (current_month,),
        ).fetchall()
        previous_rows = conn.execute(
            "SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE substr(expense_date, 1, 7) = ? GROUP BY category ORDER BY total DESC",
            (previous_month_date,),
        ).fetchall()
    conn.close()
    previous_map = {row["category"]: float(row["total"]) or 0.0 for row in previous_rows}
    comparison = []
    for row in current_rows:
        category = row["category"]
        current_total = float(row["total"]) or 0.0
        previous_total = previous_map.get(category, 0.0)
        change = current_total - previous_total
        comparison.append({
            "category": category,
            "current": current_total,
            "previous": previous_total,
            "change": change,
        })
    return comparison


def _parse_split_details(raw_text):
    if not raw_text:
        return []
    splits = []
    for part in re.split(r"[;\n]+", raw_text):
        item = part.strip()
        if not item or ":" not in item:
            continue
        category, amount_text = item.split(":", 1)
        try:
            amount = float(amount_text.strip())
        except ValueError:
            continue
        splits.append({"category": category.strip() or "General", "amount": amount})
    return splits


def _parse_tags(raw_text):
    return [tag.strip() for tag in (raw_text or "").split(",") if tag.strip()]


def _parse_custom_fields(raw_text):
    fields = []
    for part in re.split(r"[;\n]+", raw_text or ""):
        item = part.strip()
        if not item or ":" not in item:
            continue
        name, value = item.split(":", 1)
        name = name.strip()
        value = value.strip()
        if name:
            fields.append({"name": name, "value": value})
    return fields


def _extract_amount(text):
    match = re.search(r"(?:₹|rs\.?|rupees?)\s*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    match = re.search(r"\b([0-9]+(?:\.[0-9]+)?)\b", text)
    if match:
        return float(match.group(1))
    return 0.0


def _infer_category(text):
    lowered = text.lower()
    if any(word in lowered for word in ["grocer", "food", "dinner", "lunch", "restaurant", "snack"]):
        return "Food"
    if any(word in lowered for word in ["travel", "taxi", "uber", "flight", "train", "bus", "fuel", "commute"]):
        return "Travel"
    if any(word in lowered for word in ["rent", "housing", "home", "mortgage"]):
        return "Housing"
    if any(word in lowered for word in ["subscription", "renew", "bill", "utility", "internet", "mobile"]):
        return "Subscriptions"
    if any(word in lowered for word in ["shop", "shopping", "clothes", "electronics"]):
        return "Shopping"
    return "General"


def _infer_date(text, fallback=None):
    lowered = text.lower()
    today = date.today()
    if "today" in lowered:
        return today.strftime("%Y-%m-%d")
    if "tomorrow" in lowered:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if "yesterday" in lowered:
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    return fallback or today.strftime("%Y-%m-%d")


def _build_ai_answer(question, owner_id=None):
    question = (question or "").lower()
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE owner_id = ? AND expense_date >= ? GROUP BY category ORDER BY total DESC",
        (owner_id if owner_id is not None else -1, (date.today() - timedelta(days=90)).strftime("%Y-%m-%d")),
    ).fetchall()
    conn.close()
    if "top 3 categories" in question or "top categories" in question:
        top_rows = rows[:3]
        if not top_rows:
            return "No expense data is available yet."
        parts = [f"{row['category']} ₹{float(row['total']):,.2f}" for row in top_rows]
        return f"Top categories this quarter: {', '.join(parts)}."
    if "total spent" in question or "total" in question:
        total = sum(float(row["total"]) for row in rows)
        return f"You have spent ₹{total:,.2f} in the last 90 days."
    return "I can help with summaries like 'Top 3 categories this quarter'."


def _build_insights(owner_id=None):
    summary = get_dashboard_summary(owner_id=owner_id)
    category_totals = get_expense_category_totals(owner_id=owner_id)
    insights = []
    if summary["income"] and summary["total_expenses"] > summary["income"]:
        insights.append("Your spending is above your income. Review discretionary categories first.")
    if any(item["category"].lower() in {"subscriptions", "bills", "utilities"} for item in category_totals):
        insights.append("Switch to annual subscriptions or bundle plans to save about 20%.")
    if len(category_totals) >= 3:
        insights.append("You are spreading spending across several categories; a monthly cap can keep things controlled.")
    if not insights:
        insights.append("Your spending looks balanced. Keep tracking daily to stay on top of it.")
    return insights


def init_db():
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            payment_mode TEXT NOT NULL,
            expense_date TEXT NOT NULL,
            notes TEXT,
            receipt_data TEXT,
            owner_id INTEGER,
            frequency TEXT NOT NULL DEFAULT 'One-time'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recurring_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            payment_mode TEXT NOT NULL,
            frequency TEXT NOT NULL,
            next_due_date TEXT NOT NULL,
            notes TEXT,
            owner_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(expenses)")}
    if "frequency" not in columns:
        conn.execute("ALTER TABLE expenses ADD COLUMN frequency TEXT NOT NULL DEFAULT 'One-time'")
    if "receipt_data" not in columns:
        conn.execute("ALTER TABLE expenses ADD COLUMN receipt_data TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS incomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            amount REAL NOT NULL,
            income_date TEXT NOT NULL,
            notes TEXT,
            owner_id INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expense_splits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            shared_with TEXT,
            owner_id INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expense_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            owner_id INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expense_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            field_value TEXT NOT NULL,
            owner_id INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS savings_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            target_amount REAL NOT NULL,
            deadline TEXT NOT NULL,
            current_amount REAL NOT NULL DEFAULT 0,
            owner_id INTEGER NOT NULL
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            theme TEXT NOT NULL DEFAULT 'light',
            palette TEXT NOT NULL DEFAULT 'default',
            contrast_mode INTEGER NOT NULL DEFAULT 0,
            font_scale REAL NOT NULL DEFAULT 1.0,
            income_override REAL
        )
        """
    )
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(user_preferences)").fetchall()]
    if "income_override" not in columns:
        try:
            conn.execute("ALTER TABLE user_preferences ADD COLUMN income_override REAL")
        except sqlite3.OperationalError:
            pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            details TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


init_db()


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
    if not can_view_dashboard():
        return jsonify({"error": "Forbidden"}), 403
    summary = get_dashboard_summary(owner_id=int(current_user.get_id()))
    category_totals = get_expense_category_totals(owner_id=int(current_user.get_id()))
    recent_expenses = get_visible_expenses(int(current_user.get_id()))[:6]
    preferences = get_user_preferences(int(current_user.get_id()))
    return render_template(
        "dashboard.html",
        summary=summary,
        category_totals=category_totals,
        recent_expenses=recent_expenses,
        preferences=preferences,
    )


@app.route("/create-expense", methods=["GET", "POST"])
@login_required
def create_expense():
    if not can_manage_expenses():
        return jsonify({"error": "Forbidden"}), 403
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        amount = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        payment_mode = request.form.get("payment_mode", "").strip()
        expense_date = request.form.get("date", "").strip() or date.today().strftime("%Y-%m-%d")
        notes = request.form.get("notes", "").strip()
        receipt = request.form.get("receipt", "").strip()
        frequency = request.form.get("frequency", "One-time").strip() or "One-time"
        split_details = request.form.get("split_details", "").strip()
        tags_value = request.form.get("tags", "").strip()
        custom_fields_value = request.form.get("custom_fields", "").strip()

        conn = get_db_connection()
        cursor = conn.execute(
            "INSERT INTO expenses (title, amount, category, payment_mode, expense_date, notes, receipt_data, owner_id, frequency) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, float(amount or 0), category, payment_mode, expense_date, _encrypt_value(notes), _encrypt_value(receipt), int(current_user.get_id()), frequency),
        )
        expense_id = cursor.lastrowid
        for split in _parse_split_details(split_details):
            conn.execute(
                "INSERT INTO expense_splits (expense_id, category, amount, shared_with, owner_id) VALUES (?, ?, ?, ?, ?)",
                (expense_id, split["category"], split["amount"], None, int(current_user.get_id())),
            )
        for tag in _parse_tags(tags_value):
            conn.execute(
                "INSERT INTO expense_tags (expense_id, tag, owner_id) VALUES (?, ?, ?)",
                (expense_id, tag, int(current_user.get_id())),
            )
        for field in _parse_custom_fields(custom_fields_value):
            conn.execute(
                "INSERT INTO expense_fields (expense_id, field_name, field_value, owner_id) VALUES (?, ?, ?, ?)",
                (expense_id, field["name"], field["value"], int(current_user.get_id())),
            )
        conn.commit()
        conn.close()

        log_audit_event(int(current_user.get_id()), "create", "expense", expense_id, json.dumps({"title": title, "category": category}))
        flash(f"Saved {title or 'your expense'} successfully.", "success")
        return redirect(url_for("expenses"))

    return render_template("create_expense.html", today=date.today().strftime("%Y-%m-%d"))


@app.route("/edit-expense/<int:expense_id>", methods=["GET", "POST"])
@login_required
def edit_expense(expense_id):
    if not can_manage_expenses():
        return jsonify({"error": "Forbidden"}), 403
    expense = get_expense_by_id(expense_id)
    if expense is None:
        flash("Expense not found or access denied.", "danger")
        return redirect(url_for("expenses"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        amount = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        payment_mode = request.form.get("payment_mode", "").strip()
        expense_date = request.form.get("date", "").strip() or date.today().strftime("%Y-%m-%d")
        notes = request.form.get("notes", "").strip()
        receipt = request.form.get("receipt", "").strip()
        frequency = request.form.get("frequency", "One-time").strip() or "One-time"
        split_details = request.form.get("split_details", "").strip()
        tags_value = request.form.get("tags", "").strip()
        custom_fields_value = request.form.get("custom_fields", "").strip()

        conn = get_db_connection()
        conn.execute(
            "UPDATE expenses SET title = ?, amount = ?, category = ?, payment_mode = ?, expense_date = ?, notes = ?, receipt_data = ?, frequency = ? WHERE id = ?",
            (title, float(amount or 0), category, payment_mode, expense_date, _encrypt_value(notes), _encrypt_value(receipt), frequency, expense_id),
        )
        conn.execute("DELETE FROM expense_splits WHERE expense_id = ? AND owner_id = ?", (expense_id, int(current_user.get_id())))
        conn.execute("DELETE FROM expense_tags WHERE expense_id = ? AND owner_id = ?", (expense_id, int(current_user.get_id())))
        conn.execute("DELETE FROM expense_fields WHERE expense_id = ? AND owner_id = ?", (expense_id, int(current_user.get_id())))
        for split in _parse_split_details(split_details):
            conn.execute(
                "INSERT INTO expense_splits (expense_id, category, amount, shared_with, owner_id) VALUES (?, ?, ?, ?, ?)",
                (expense_id, split["category"], split["amount"], None, int(current_user.get_id())),
            )
        for tag in _parse_tags(tags_value):
            conn.execute(
                "INSERT INTO expense_tags (expense_id, tag, owner_id) VALUES (?, ?, ?)",
                (expense_id, tag, int(current_user.get_id())),
            )
        for field in _parse_custom_fields(custom_fields_value):
            conn.execute(
                "INSERT INTO expense_fields (expense_id, field_name, field_value, owner_id) VALUES (?, ?, ?, ?)",
                (expense_id, field["name"], field["value"], int(current_user.get_id())),
            )
        conn.commit()
        conn.close()

        log_audit_event(int(current_user.get_id()), "update", "expense", expense_id, json.dumps({"title": title, "category": category}))
        flash(f"Updated {title or 'your expense'} successfully.", "success")
        return redirect(url_for("expenses"))

    tags_value, custom_fields_value, split_details = get_expense_related_values(expense_id, int(current_user.get_id()))
    return render_template(
        "create_expense.html",
        expense=expense,
        today=expense["expense_date"],
        tags_value=tags_value,
        custom_fields_value=custom_fields_value,
        split_details=split_details,
        edit_mode=True,
    )


@app.route("/delete-expense/<int:expense_id>", methods=["POST"])
@login_required
def delete_expense(expense_id):
    if not can_manage_expenses():
        return jsonify({"error": "Forbidden"}), 403
    expense = get_expense_by_id(expense_id)
    if expense is None:
        flash("Expense not found or access denied.", "danger")
        return redirect(url_for("expenses"))

    conn = get_db_connection()
    conn.execute("DELETE FROM expense_splits WHERE expense_id = ? AND owner_id = ?", (expense_id, int(current_user.get_id())))
    conn.execute("DELETE FROM expense_tags WHERE expense_id = ? AND owner_id = ?", (expense_id, int(current_user.get_id())))
    conn.execute("DELETE FROM expense_fields WHERE expense_id = ? AND owner_id = ?", (expense_id, int(current_user.get_id())))
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()

    log_audit_event(int(current_user.get_id()), "delete", "expense", expense_id, json.dumps({"title": expense["title"], "category": expense["category"]}))
    flash("Expense deleted successfully.", "success")
    return redirect(url_for("expenses"))


@app.route("/expenses")
@login_required
def expenses():
    if not can_view_dashboard():
        return jsonify({"error": "Forbidden"}), 403
    owner_id = int(current_user.get_id())
    expenses_data = get_visible_expenses(owner_id)
    preferences = get_user_preferences(owner_id)
    income_override = preferences.get("income_override")
    income_totals = get_monthly_income_totals(owner_id)
    total_amount = sum(float(expense["amount"] or 0) for expense in expenses_data)
    today = date.today()

    def _parse_date(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d")
        except Exception:
            return None

    monthly_groups = {}
    for expense in expenses_data:
        expense_date = expense.get("expense_date") or date.today().strftime("%Y-%m-%d")
        dt = _parse_date(expense_date)
        month_key = dt.strftime("%B %Y") if dt else expense_date
        monthly_groups.setdefault(month_key, []).append(expense)

    def _month_sort_key(item):
        month_str = item[0]
        try:
            return datetime.strptime(month_str, "%B %Y")
        except Exception:
            return datetime.min

    monthly_summary = []
    for month, items in sorted(monthly_groups.items(), key=_month_sort_key, reverse=True):
        dt = _parse_date(items[0].get("expense_date") or date.today().strftime("%Y-%m-%d"))
        month_key = dt.strftime("%Y-%m") if dt else ""
        income_value = income_totals.get(month_key, 0.0)
        if income_override is not None and month_key == today.strftime("%Y-%m"):
            income_value = float(income_override)
        monthly_summary.append({
            "month": month,
            "expenses": items,
            "count": len(items),
            "total_amount": sum(float(item["amount"] or 0) for item in items),
            "income_total": income_value,
        })

    summary = {
        "total_amount": total_amount,
        "expense_count": len(expenses_data),
        "monthly_summary": monthly_summary,
    }
    return render_template("expenses.html", expenses=expenses_data, summary=summary)


@app.route("/reports", methods=["GET", "POST"])
@login_required
def reports():
    if not can_view_dashboard():
        return jsonify({"error": "Forbidden"}), 403
    if request.method == "POST":
        payload = request.form
        name = (payload.get("name") or "").strip()
        target_amount = payload.get("target_amount")
        deadline = (payload.get("deadline") or date.today().strftime("%Y-%m-%d")).strip()
        current_amount = payload.get("current_amount") or 0
        if name and target_amount is not None:
            conn = get_db_connection()
            conn.execute(
                "INSERT INTO savings_goals (name, target_amount, deadline, current_amount, owner_id) VALUES (?, ?, ?, ?, ?)",
                (name, float(target_amount), deadline, float(current_amount or 0), int(current_user.get_id())),
            )
            conn.commit()
            conn.close()
            flash(f"Saved {name} successfully.", "success")
        return redirect(url_for("reports"))

    month = request.args.get("month", date.today().strftime("%Y-%m"))
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        month = date.today().strftime("%Y-%m")

    owner_id = int(current_user.get_id())
    category_totals = get_expense_category_totals(owner_id=owner_id)
    summary = get_dashboard_summary(owner_id=owner_id)
    preferences = get_user_preferences(owner_id)
    income_override = preferences.get("income_override")
    savings_goals = get_savings_goals(owner_id=owner_id)
    heatmap = get_spending_heatmap(owner_id=owner_id, month=month)
    comparison = get_monthly_comparison(owner_id=owner_id)
    income_totals = get_monthly_income_totals(owner_id)
    selected_month_income = income_totals.get(month, 0.0)
    if income_override is not None and month == date.today().strftime("%Y-%m"):
        selected_month_income = float(income_override)
    streaks = get_goal_streaks(owner_id)
    return render_template(
        "reports.html",
        category_totals=category_totals,
        summary=summary,
        savings_goals=savings_goals,
        heatmap=heatmap,
        comparison=comparison,
        today=date.today().strftime("%Y-%m-%d"),
        streaks=streaks,
        preferences=preferences,
        selected_month=month,
        selected_month_income=selected_month_income,
    )


@app.route("/reports/export/<file_format>")
@login_required
def export_reports(file_format):
    if not can_view_dashboard():
        return jsonify({"error": "Forbidden"}), 403

    expenses_data = get_visible_expenses(int(current_user.get_id()))

    if file_format == "pdf":
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = [Paragraph("Expense Report", styles["Title"]), Spacer(1, 12)]
        rows = [["Title", "Category", "Amount", "Date"]]
        rows.extend([[row["title"], row["category"], f"₹{float(row['amount']):,.2f}", row["expense_date"]] for row in expenses_data])
        table = Table(rows, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ]))
        story.append(table)
        doc.build(story)
        buffer.seek(0)
        return send_file(buffer, download_name="expenses.pdf", mimetype="application/pdf")

    if file_format == "excel":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Expenses"
        sheet.append(["Title", "Category", "Amount", "Date", "Notes"])
        for row in expenses_data:
            sheet.append([row["title"], row["category"], float(row["amount"]), row["expense_date"], row["notes"]])
        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        return send_file(output, download_name="expenses.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return jsonify({"error": "Unsupported format"}), 400


@app.route("/share")
@login_required
def share_reports():
    if not can_manage_expenses():
        return jsonify({"error": "Forbidden"}), 403
    return jsonify({"message": "Sharing link ready", "link": url_for("reports", _external=True)})


@app.route("/set-language/<lang>")
def set_language(lang):
    if lang in SUPPORTED_LANGUAGES:
        session["language"] = lang
    else:
        session["language"] = "en"

    next_url = request.args.get("next") or url_for("dashboard")
    return redirect(next_url)


@app.route("/preferences", methods=["POST"])
@login_required
def save_preferences():
    payload = request.form or request.get_json(silent=True) or {}
    preferences = {
        "theme": (payload.get("theme") or "light").strip(),
        "palette": (payload.get("palette") or "default").strip(),
        "contrast": bool(payload.get("contrast")),
        "font_scale": float(payload.get("font_scale") or 1.0),
        "income_override": payload.get("income_override"),
    }
    save_user_preferences(int(current_user.get_id()), preferences)
    return jsonify(preferences)


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
            (username, password_hash, "viewer"),
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


def _normalize_recurring_frequency(frequency):
    return (frequency or "monthly").strip().lower()


@app.route("/api/recurring-expenses", methods=["GET", "POST"])
@login_required
def recurring_expenses_api():
    conn = get_db_connection()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        title = (payload.get("title") or "").strip()
        amount = payload.get("amount")
        category = (payload.get("category") or "General").strip()
        payment_mode = (payload.get("payment_mode") or "Cash").strip()
        frequency = _normalize_recurring_frequency(payload.get("frequency"))
        next_due_date = (payload.get("next_due_date") or date.today().strftime("%Y-%m-%d")).strip()
        notes = (payload.get("notes") or "").strip()

        if not title or amount is None:
            conn.close()
            return jsonify({"error": "title and amount are required"}), 400

        cursor = conn.execute(
            """
            INSERT INTO recurring_expenses (title, amount, category, payment_mode, frequency, next_due_date, notes, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, float(amount), category, payment_mode, frequency, next_due_date, notes, int(current_user.get_id())),
        )
        conn.commit()
        recurring_id = cursor.lastrowid
        conn.close()
        return jsonify({
            "id": recurring_id,
            "title": title,
            "amount": float(amount),
            "category": category,
            "payment_mode": payment_mode,
            "frequency": frequency,
            "next_due_date": next_due_date,
            "notes": notes,
        })

    rows = conn.execute(
        "SELECT id, title, amount, category, payment_mode, frequency, next_due_date, notes FROM recurring_expenses WHERE owner_id = ? ORDER BY next_due_date ASC",
        (int(current_user.get_id()),),
    ).fetchall()
    conn.close()
    return jsonify([
        {
            "id": row["id"],
            "title": row["title"],
            "amount": float(row["amount"]),
            "category": row["category"],
            "payment_mode": row["payment_mode"],
            "frequency": row["frequency"],
            "next_due_date": row["next_due_date"],
            "notes": row["notes"],
        }
        for row in rows
    ])


@app.route("/api/incomes", methods=["GET", "POST"])
@login_required
def incomes_api():
    conn = get_db_connection()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        source = (payload.get("source") or "").strip()
        amount = payload.get("amount")
        income_date = (payload.get("date") or date.today().strftime("%Y-%m-%d")).strip()
        notes = (payload.get("notes") or "").strip()

        if not source or amount is None:
            conn.close()
            return jsonify({"error": "source and amount are required"}), 400

        cursor = conn.execute(
            "INSERT INTO incomes (source, amount, income_date, notes, owner_id) VALUES (?, ?, ?, ?, ?)",
            (source, float(amount), income_date, notes, int(current_user.get_id())),
        )
        conn.commit()
        income_id = cursor.lastrowid
        conn.close()
        return jsonify({
            "id": income_id,
            "source": source,
            "amount": float(amount),
            "date": income_date,
            "notes": notes,
        })

    rows = conn.execute(
        "SELECT id, source, amount, income_date, notes FROM incomes WHERE owner_id = ? ORDER BY income_date DESC, id DESC",
        (int(current_user.get_id()),),
    ).fetchall()
    conn.close()
    return jsonify([
        {
            "id": row["id"],
            "source": row["source"],
            "amount": float(row["amount"]),
            "date": row["income_date"],
            "notes": row["notes"],
        }
        for row in rows
    ])


@app.route("/api/ai/query")
@login_required
def ai_query_api():
    question = request.args.get("question", "")
    return jsonify({"question": question, "answer": _build_ai_answer(question, owner_id=int(current_user.get_id()))})


@app.route("/api/ai/insights")
@login_required
def ai_insights_api():
    return jsonify({"insights": _build_insights(owner_id=int(current_user.get_id()))})


@app.route("/api/expenses/split", methods=["POST"])
@login_required
def split_expense_api():
    payload = request.get_json(silent=True) or {}
    expense_id = payload.get("expense_id")
    splits = payload.get("splits") or []
    if not expense_id or not splits:
        return jsonify({"error": "expense_id and splits are required"}), 400

    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM expenses WHERE id = ? AND owner_id = ?", (expense_id, int(current_user.get_id()))).fetchone()
    if existing is None:
        conn.close()
        return jsonify({"error": "expense not found"}), 404

    created = []
    for split in splits:
        category = (split.get("category") or "General").strip()
        amount = split.get("amount")
        shared_with = (split.get("shared_with") or "").strip() or None
        if not category or amount is None:
            continue
        cursor = conn.execute(
            "INSERT INTO expense_splits (expense_id, category, amount, shared_with, owner_id) VALUES (?, ?, ?, ?, ?)",
            (expense_id, category, float(amount), shared_with, int(current_user.get_id())),
        )
        created.append({"id": cursor.lastrowid, "category": category, "amount": float(amount), "shared_with": shared_with})

    conn.commit()
    conn.close()
    return jsonify({"expense_id": expense_id, "splits": created})


@app.route("/api/expenses/tags", methods=["POST"])
@login_required
def expense_tags_api():
    payload = request.get_json(silent=True) or {}
    expense_id = payload.get("expense_id")
    tags = payload.get("tags") or []
    if not expense_id:
        return jsonify({"error": "expense_id is required"}), 400

    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM expenses WHERE id = ? AND owner_id = ?", (expense_id, int(current_user.get_id()))).fetchone()
    if existing is None:
        conn.close()
        return jsonify({"error": "expense not found"}), 404

    conn.execute("DELETE FROM expense_tags WHERE expense_id = ? AND owner_id = ?", (expense_id, int(current_user.get_id())))
    for tag in tags:
        if tag:
            conn.execute("INSERT INTO expense_tags (expense_id, tag, owner_id) VALUES (?, ?, ?)", (expense_id, str(tag).strip(), int(current_user.get_id())))
    conn.commit()
    conn.close()
    return jsonify({"expense_id": expense_id, "tags": [str(tag).strip() for tag in tags if tag]})


@app.route("/api/expenses/fields", methods=["POST"])
@login_required
def expense_fields_api():
    payload = request.get_json(silent=True) or {}
    expense_id = payload.get("expense_id")
    fields = payload.get("fields") or []
    if not expense_id:
        return jsonify({"error": "expense_id is required"}), 400

    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM expenses WHERE id = ? AND owner_id = ?", (expense_id, int(current_user.get_id()))).fetchone()
    if existing is None:
        conn.close()
        return jsonify({"error": "expense not found"}), 404

    conn.execute("DELETE FROM expense_fields WHERE expense_id = ? AND owner_id = ?", (expense_id, int(current_user.get_id())))
    for field in fields:
        name = (field.get("name") or "").strip()
        value = (field.get("value") or "").strip()
        if name:
            conn.execute("INSERT INTO expense_fields (expense_id, field_name, field_value, owner_id) VALUES (?, ?, ?, ?)", (expense_id, name, value, int(current_user.get_id())))
    conn.commit()
    conn.close()
    return jsonify({"expense_id": expense_id, "fields": fields})


@app.route("/api/savings-goals", methods=["GET", "POST"])
@login_required
def savings_goals_api():
    conn = get_db_connection()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        name = (payload.get("name") or "").strip()
        target_amount = payload.get("target_amount")
        deadline = (payload.get("deadline") or date.today().strftime("%Y-%m-%d")).strip()
        current_amount = payload.get("current_amount", 0)
        if not name or target_amount is None:
            conn.close()
            return jsonify({"error": "name and target_amount are required"}), 400
        cursor = conn.execute(
            "INSERT INTO savings_goals (name, target_amount, deadline, current_amount, owner_id) VALUES (?, ?, ?, ?, ?)",
            (name, float(target_amount), deadline, float(current_amount or 0), int(current_user.get_id())),
        )
        conn.commit()
        goal_id = cursor.lastrowid
        conn.close()
        return jsonify({"id": goal_id, "name": name, "target_amount": float(target_amount), "deadline": deadline, "current_amount": float(current_amount or 0)})

    rows = conn.execute("SELECT id, name, target_amount, deadline, current_amount FROM savings_goals WHERE owner_id = ? ORDER BY deadline ASC", (int(current_user.get_id()),)).fetchall()
    conn.close()
    return jsonify([
        {"id": row["id"], "name": row["name"], "target_amount": float(row["target_amount"]), "deadline": row["deadline"], "current_amount": float(row["current_amount"])}
        for row in rows
    ])


@app.route("/api/reports/balance-prediction")
@login_required
def balance_prediction_api():
    summary = get_dashboard_summary()
    monthly_income = float(summary["income"])
    monthly_expenses = float(summary["total_expenses"])
    predicted_balance = monthly_income - monthly_expenses
    return jsonify({"predicted_balance": predicted_balance})


@app.route("/api/reports/category-comparison")
@login_required
def category_comparison_api():
    category_totals = get_expense_category_totals()
    return jsonify(category_totals)


@app.route("/api/recurring-expenses/auto-entry", methods=["POST"])
@login_required
def recurring_expenses_auto_entry():
    payload = request.get_json(silent=True) or {}
    target_date = (payload.get("date") or date.today().strftime("%Y-%m-%d")).strip()
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, title, amount, category, payment_mode, frequency, next_due_date, notes FROM recurring_expenses WHERE owner_id = ? ORDER BY next_due_date ASC",
        (int(current_user.get_id()),),
    ).fetchall()
    generated = 0
    for row in rows:
        due_date = row["next_due_date"]
        if due_date > target_date:
            continue
        conn.execute(
            "INSERT INTO expenses (title, amount, category, payment_mode, expense_date, notes, receipt_data, owner_id, frequency) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row["title"], float(row["amount"]), row["category"], row["payment_mode"], due_date, _encrypt_value(row["notes"]), None, int(current_user.get_id()), row["frequency"]),
        )
        generated += 1
        next_due = None
        if row["frequency"] == "daily":
            next_due = (date.fromisoformat(due_date) + timedelta(days=1)).strftime("%Y-%m-%d")
        elif row["frequency"] == "weekly":
            next_due = (date.fromisoformat(due_date) + timedelta(days=7)).strftime("%Y-%m-%d")
        elif row["frequency"] == "yearly":
            next_due = (date.fromisoformat(due_date).replace(year=date.fromisoformat(due_date).year + 1)).strftime("%Y-%m-%d")
        else:
            next_due = (date.fromisoformat(due_date).replace(month=date.fromisoformat(due_date).month % 12 + 1)).strftime("%Y-%m-%d")
        conn.execute(
            "UPDATE recurring_expenses SET next_due_date = ? WHERE id = ?",
            (next_due, row["id"]),
        )
    conn.commit()
    conn.close()
    return jsonify({"generated": generated, "date": target_date})


@app.route("/api/backup/export")
@login_required
def backup_export_api():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("database.sqlite", DB_PATH.read_bytes() if DB_PATH.exists() else b"")
        archive.writestr("metadata.json", json.dumps({"exported_at": datetime.utcnow().isoformat()}))
    buffer.seek(0)
    return send_file(buffer, download_name="backup.zip", mimetype="application/zip")


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
