"""
Database initialization module - ensures all required tables exist with proper schema.
Run this when setting up the application or before running migrations.
"""

import os
import psycopg2
from dotenv import load_dotenv

def _load_env_files():
    """Load environment variables from .env files"""
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

def get_connection():
    """Get database connection"""
    app_timezone = os.getenv("APP_TIMEZONE", "Asia/Kuala_Lumpur")
    db_password = os.getenv("DB_PASSWORD")
    if not db_password:
        raise RuntimeError(
            "DB_PASSWORD is not set. Copy .env.example to .env and configure your PostgreSQL credentials."
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

def initialize_database():
    """Initialize all required database tables"""
    _load_env_files()
    
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Read and execute the schema initialization SQL
        sql_file_path = os.path.join(os.path.dirname(__file__), "init_schema.sql")
        if not os.path.exists(sql_file_path):
            print(f"Warning: SQL schema file not found at {sql_file_path}")
            print("Creating tables directly from Python...")
            _create_tables_from_python(conn, cur)
        else:
            with open(sql_file_path, 'r') as f:
                sql_content = f.read()
            cur.execute(sql_content)

        # Backward-compatible migration for older databases missing avatar_url.
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(512)")
        cur.execute("DROP INDEX IF EXISTS idx_login_accounts_user_id_unique")
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_login_accounts_user_id
            ON login_accounts(user_id)
            WHERE user_id IS NOT NULL
            """
        )
        
        conn.commit()
        print("Database schema initialized successfully! (✔)")
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error initializing database (✖): {e}")
        return False
    finally:
        cur.close()
        conn.close()

def _create_tables_from_python(conn, cur):
    """Fallback: create tables directly from Python if SQL file is not available"""
    
    # Users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(255) NOT NULL,
            unit VARCHAR(255),
            email VARCHAR(255),
            avatar_url VARCHAR(512),
            role VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Login accounts table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS login_accounts (
            username VARCHAR(100) PRIMARY KEY,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("DROP INDEX IF EXISTS idx_login_accounts_user_id_unique")
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_login_accounts_user_id
        ON login_accounts(user_id)
        WHERE user_id IS NOT NULL
        """
    )
    
    # Defects table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS defects (
            id SERIAL PRIMARY KEY,
            unit VARCHAR(255),
            description TEXT,
            reported_date TIMESTAMP,
            status VARCHAR(50) DEFAULT 'Pending',
            completed_date DATE,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            urgency VARCHAR(50),
            deadline DATE,
            remarks TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Remarks table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS remarks (
            id SERIAL PRIMARY KEY,
            defect_id INTEGER NOT NULL REFERENCES defects(id) ON DELETE CASCADE,
            role VARCHAR(50),
            remark TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Completion dates table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS completion_dates (
            id SERIAL PRIMARY KEY,
            defect_id INTEGER NOT NULL UNIQUE REFERENCES defects(id) ON DELETE CASCADE,
            completed_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Audit log table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            action VARCHAR(255),
            role VARCHAR(50),
            defect_id INTEGER REFERENCES defects(id) ON DELETE SET NULL,
            filename VARCHAR(255),
            new_status VARCHAR(50),
            timestamp TIMESTAMP DEFAULT NOW(),
            details JSONB
        )
    """)
    
    # Report versions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS report_versions (
            role TEXT NOT NULL,
            version_no INTEGER NOT NULL,
            generated_at TIMESTAMP NOT NULL,
            language TEXT NOT NULL DEFAULT 'ms',
            report_text TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (role, version_no)
        )
    """)
    
    # Report homeowner profile table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS report_homeowner_profile (
            homeowner_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            ic_number TEXT,
            email TEXT,
            phone_number TEXT,
            address TEXT,
            court_location TEXT,
            state_name TEXT,
            claim_amount TEXT,
            item_service TEXT,
            transaction_date TEXT,
            defect_unit TEXT,
            project_name TEXT,
            defect_state TEXT,
            defect_property_address TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    
    # Report respondent profile table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS report_respondent_profile (
            respondent_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            company_name TEXT NOT NULL,
            person_in_charge TEXT,
            registration_number TEXT,
            email TEXT,
            phone_number TEXT,
            address TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("ALTER TABLE report_homeowner_profile ADD COLUMN IF NOT EXISTS defect_unit TEXT")
    cur.execute("ALTER TABLE report_homeowner_profile ADD COLUMN IF NOT EXISTS project_name TEXT")
    cur.execute("ALTER TABLE report_homeowner_profile ADD COLUMN IF NOT EXISTS defect_state TEXT")
    cur.execute("ALTER TABLE report_homeowner_profile ADD COLUMN IF NOT EXISTS defect_property_address TEXT")
    cur.execute("ALTER TABLE report_respondent_profile ADD COLUMN IF NOT EXISTS person_in_charge TEXT")

    # Report legal profile table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS report_legal_profile (
            legal_user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            legal_name TEXT,
            phone_number TEXT,
            email TEXT,
            office_address TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Report claim registry table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS report_claim_registry (
            claim_id VARCHAR(64) PRIMARY KEY,
            case_key VARCHAR(255) UNIQUE NOT NULL,
            case_number VARCHAR(6) NOT NULL,
            claim_year INTEGER NOT NULL,
            date_filed TIMESTAMP NOT NULL DEFAULT NOW(),
            state VARCHAR(100),
            state_code VARCHAR(20),
            homeowner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            respondent_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    
    # Create indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_defects_status ON defects(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_defects_unit ON defects(unit)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_defects_user_id ON defects(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_remarks_defect_id ON remarks(defect_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_completion_dates_defect_id ON completion_dates(defect_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_defect_id ON audit_log(defect_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_login_accounts_user_id ON login_accounts(user_id)")

if __name__ == "__main__":
    initialize_database()
