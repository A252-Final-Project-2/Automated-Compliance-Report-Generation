-- Complete database schema initialization for compliance reporting system
-- This script creates all necessary tables for the application

BEGIN;

-- 1. USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    unit VARCHAR(255),
    email VARCHAR(255),
    avatar_url VARCHAR(512),
    role VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. LOGIN ACCOUNTS TABLE (Already created in routes.py, ensure it exists)
CREATE TABLE IF NOT EXISTS login_accounts (
    username VARCHAR(100) PRIMARY KEY,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

DROP INDEX IF EXISTS idx_login_accounts_user_id_unique;

CREATE INDEX IF NOT EXISTS idx_login_accounts_user_id_lookup
    ON login_accounts(user_id)
    WHERE user_id IS NOT NULL;

-- 3. DEFECTS TABLE - Core defect records
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
);

-- 4. REMARKS TABLE - Store remarks for defects
CREATE TABLE IF NOT EXISTS remarks (
    id SERIAL PRIMARY KEY,
    defect_id INTEGER NOT NULL REFERENCES defects(id) ON DELETE CASCADE,
    role VARCHAR(50),
    remark TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 5. COMPLETION DATES TABLE - Track completion dates
CREATE TABLE IF NOT EXISTS completion_dates (
    id SERIAL PRIMARY KEY,
    defect_id INTEGER NOT NULL UNIQUE REFERENCES defects(id) ON DELETE CASCADE,
    completed_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 6. AUDIT LOG TABLE - Audit trail
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    action VARCHAR(255),
    role VARCHAR(50),
    defect_id INTEGER REFERENCES defects(id) ON DELETE SET NULL,
    filename VARCHAR(255),
    new_status VARCHAR(50),
    timestamp TIMESTAMP DEFAULT NOW(),
    details JSONB
);

-- 7. REPORT VERSIONS TABLE (can also be in report metadata setup)
CREATE TABLE IF NOT EXISTS report_versions (
    role TEXT NOT NULL,
    version_no INTEGER NOT NULL,
    generated_at TIMESTAMP NOT NULL,
    language TEXT NOT NULL DEFAULT 'ms',
    report_text TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (role, version_no)
);

-- 8. REPORT HOMEOWNER PROFILE TABLE
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
);

-- 9. REPORT RESPONDENT PROFILE TABLE
CREATE TABLE IF NOT EXISTS report_respondent_profile (
    respondent_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    company_name TEXT NOT NULL,
    person_in_charge TEXT,
    registration_number TEXT,
    email TEXT,
    phone_number TEXT,
    address TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 10. REPORT CLAIM REGISTRY TABLE
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
);

-- CREATE INDEXES FOR BETTER PERFORMANCE
CREATE INDEX IF NOT EXISTS idx_defects_status ON defects(status);
CREATE INDEX IF NOT EXISTS idx_defects_unit ON defects(unit);
CREATE INDEX IF NOT EXISTS idx_defects_user_id ON defects(user_id);
CREATE INDEX IF NOT EXISTS idx_remarks_defect_id ON remarks(defect_id);
CREATE INDEX IF NOT EXISTS idx_completion_dates_defect_id ON completion_dates(defect_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_defect_id ON audit_log(defect_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_login_accounts_user_id ON login_accounts(user_id);

CREATE TABLE IF NOT EXISTS report_legal_profile (
    legal_user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    legal_name TEXT,
    phone_number TEXT,
    email TEXT,
    office_address TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMIT;
