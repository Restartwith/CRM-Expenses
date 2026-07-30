import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "crm.db"
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")

class Config:
    SECRET_KEY = SECRET_KEY
    SQLALCHEMY_TRACK_MODIFICATIONS = False
