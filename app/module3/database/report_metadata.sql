-- report_metadata.sql
-- Standardized English schema for report metadata.
-- Uses one homeowner profile table, one respondent profile table, and one claim registry.

BEGIN;

DROP TABLE IF EXISTS report_claimant_profile;
DROP TABLE IF EXISTS report_claimant_user_profile;
DROP TABLE IF EXISTS report_homeowner_case_profile;
DROP TABLE IF EXISTS report_respondent_user_profile;
DROP TABLE IF EXISTS report_case_config;
DROP TABLE IF EXISTS report_role_context;
DROP TABLE IF EXISTS report_settings;
DROP TABLE IF EXISTS report_state_codes;
DROP TABLE IF EXISTS tribunal_case_config;
DROP TABLE IF EXISTS report_claim_registry;
DROP TABLE IF EXISTS report_respondent_profile;
DROP TABLE IF EXISTS report_homeowner_profile;

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

CREATE TABLE IF NOT EXISTS report_claim_registry (
	claim_id VARCHAR(64) PRIMARY KEY,
	case_key VARCHAR(255) UNIQUE NOT NULL,
	case_number VARCHAR(6) NOT NULL,
	claim_year INTEGER NOT NULL,
	date_filed TIMESTAMP NOT NULL DEFAULT NOW(),
	state VARCHAR(100) NOT NULL,
	state_code VARCHAR(20) NOT NULL,
	homeowner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
	respondent_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
	created_at TIMESTAMP NOT NULL DEFAULT NOW(),
	updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Auto bootstrap homeowner rows from users table.
INSERT INTO report_homeowner_profile (
	homeowner_id, name, email, phone_number, address, court_location, state_name, claim_amount, item_service, transaction_date
)
SELECT u.id, u.full_name, u.email, NULL, u.unit, NULL, NULL, NULL, 'Pembaikan Kecacatan Dalam Tempoh DLP', NULL
FROM users u
WHERE u.role = 'Homeowner'
  AND NOT EXISTS (
	  SELECT 1 FROM report_homeowner_profile p WHERE p.homeowner_id = u.id
  );

-- Auto bootstrap respondent rows from users table.
INSERT INTO report_respondent_profile (respondent_id, company_name, email, phone_number, address)
SELECT u.id, u.full_name, u.email, NULL, u.unit
FROM users u
WHERE u.role IN ('Developer', 'Legal', 'Admin')
  AND NOT EXISTS (
	  SELECT 1 FROM report_respondent_profile p WHERE p.respondent_id = u.id
  );

COMMIT;
