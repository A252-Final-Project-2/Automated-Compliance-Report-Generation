import os

import psycopg2
from dotenv import load_dotenv


def _load_env_files():
    module_dir = os.path.dirname(__file__)
    module3_dir = os.path.abspath(os.path.join(module_dir, ".."))
    project_root = os.path.abspath(os.path.join(module3_dir, "..", ".."))
    candidates = [
        os.path.join(project_root, ".env"),
        os.path.join(module3_dir, ".env"),
    ]
    for env_path in candidates:
        if os.path.exists(env_path):
            load_dotenv(env_path, override=False)


_load_env_files()


def get_connection():
    app_timezone = os.getenv("APP_TIMEZONE", "Asia/Kuala_Lumpur")
    db_password = os.getenv("DB_PASSWORD")
    if not db_password:
        raise RuntimeError(
            "DB_PASSWORD is not set. Copy app/module3/.env.example to .env and configure your PostgreSQL credentials."
        )

    db_host = os.getenv("DB_HOST", "localhost")
    db_name = os.getenv("DB_NAME", "compliance_db")
    db_user = os.getenv("DB_USER", "postgres")
    db_port = os.getenv("DB_PORT", "5432")

    host_candidates = [db_host]
    if db_host == "host.docker.internal":
        host_candidates.append("localhost")

    last_error = None
    for host in host_candidates:
        try:
            conn = psycopg2.connect(
                host=host,
                database=db_name,
                user=db_user,
                password=db_password,
                port=db_port,
                connect_timeout=5,
            )
            break
        except Exception as exc:
            last_error = exc
    else:
        raise last_error

    try:
        cur = conn.cursor()
        cur.execute("SET TIME ZONE %s", (app_timezone,))
        cur.close()
    except Exception:
        pass

    return conn