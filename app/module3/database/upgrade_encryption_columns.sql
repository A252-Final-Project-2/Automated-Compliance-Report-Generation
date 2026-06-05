-- Migration: enlarge columns that store encrypted text
-- Run this against the application database to avoid StringDataRightTruncation

BEGIN;

-- Users: encrypted fields may exceed small VARCHAR limits after Fernet encryption
ALTER TABLE users ALTER COLUMN full_name TYPE TEXT;
ALTER TABLE users ALTER COLUMN email TYPE TEXT;
ALTER TABLE users ALTER COLUMN unit TYPE TEXT;

-- Report homeowner profile: encrypted name/address/court_location
ALTER TABLE report_homeowner_profile ALTER COLUMN name TYPE TEXT;
ALTER TABLE report_homeowner_profile ALTER COLUMN address TYPE TEXT;
ALTER TABLE report_homeowner_profile ALTER COLUMN court_location TYPE TEXT;

-- Report respondent profile: encrypted company_name/address
ALTER TABLE report_respondent_profile ALTER COLUMN company_name TYPE TEXT;
ALTER TABLE report_respondent_profile ALTER COLUMN address TYPE TEXT;

COMMIT;

-- Usage: psql -h <host> -U <user> -d <db> -f upgrade_encryption_columns.sql
