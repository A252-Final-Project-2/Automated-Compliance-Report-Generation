import os
from datetime import timedelta

from flask import Flask, redirect, url_for, session, request
from werkzeug.exceptions import Forbidden, Unauthorized
from dotenv import load_dotenv


def _load_env_files():
    module_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(module_dir, "..", ".."))
    candidates = [
        os.path.join(project_root, ".env"),
        os.path.join(module_dir, ".env"),
    ]
    for env_path in candidates:
        if os.path.exists(env_path):
            load_dotenv(env_path, override=False)


_load_env_files()

try:
    from .routes import routes
    from .report_data import ensure_profile_encryption_at_rest
    from .database.init import initialize_database
except ImportError:  # pragma: no cover - fallback for direct execution from module3/
    from routes import routes
    from report_data import ensure_profile_encryption_at_rest
    from database.init import initialize_database

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")

# Security-focused cookie/session settings.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
    minutes=int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "120"))
)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True


@app.errorhandler(401)
@app.errorhandler(Unauthorized)
def handle_unauthorized(_error):
    session["auth_error"] = "Please sign in to continue."
    return redirect(url_for("routes.login", next=request.path))


@app.errorhandler(403)
@app.errorhandler(Forbidden)
def handle_forbidden(_error):
    session["auth_error"] = "You do not have permission to access that page."
    return redirect(url_for("routes.login", next=request.path))

if os.getenv("FLASK_ENV", "development").lower() == "production" and app.secret_key == "dev-secret-key-change-me":
    raise RuntimeError("FLASK_SECRET_KEY must be set to a strong value in production.")

# Initialize database schema and ensure all tables exist
try:
    initialize_database()
except Exception as e:
    print(f"Warning: Could not initialize database schema: {e}")
    print("The application will continue, but database operations may fail if tables don't exist.")

# Register routes (PDF export & others)
app.register_blueprint(routes)

# Initialize report metadata once at startup so dashboard requests stay fast.
ensure_profile_encryption_at_rest()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "1") == "1",
    )
