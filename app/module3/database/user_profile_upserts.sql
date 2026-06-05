-- USER 2 FULL DATA SCRIPT (SQL)

BEGIN;

-- Force homeowner2 to use user_id=2 for login/report linkage.
UPDATE login_accounts
SET user_id = 2,
    role = 'Homeowner',
    is_active = TRUE
WHERE username = 'homeowner2';

-- Resolve actual linked user for homeowner2.
-- This avoids mismatches when login_accounts maps homeowner2 to a different user_id.
CREATE TEMP TABLE tmp_homeowner2_user AS
SELECT la.user_id AS user_id
FROM login_accounts la
WHERE la.username = 'homeowner2'
LIMIT 1;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM tmp_homeowner2_user) THEN
    RAISE EXCEPTION 'homeowner2 is not configured in login_accounts';
  END IF;
END $$;

-- 1) UPSERT USER
INSERT INTO users (id, full_name, unit, email, role)
SELECT user_id, 'Siti Aminah Binti Ali', 'Unit B-12-03, Residensi Harmoni', 'siti.aminah@email.com', 'Homeowner'
FROM tmp_homeowner2_user
ON CONFLICT (id) DO UPDATE
SET full_name = EXCLUDED.full_name,
    unit = EXCLUDED.unit,
    email = EXCLUDED.email,
    role = EXCLUDED.role;

-- 2) UPSERT HOMEOWNER PROFILE FOR USER 2
INSERT INTO report_homeowner_profile
(homeowner_id, name, ic_number, email, phone_number, address, court_location, state_name, claim_amount, item_service, transaction_date, defect_unit, project_name, defect_state, defect_property_address, updated_at)
SELECT
  user_id,
  'Siti Aminah Binti Ali',
  '',
  'siti.aminah@email.com',
  '013-9876543',
  'Unit B-12-03, Residensi Harmoni, Jalan Putra 1, 06000 Jitra, Kedah',
  'Alor Setar',
  'Kedah',
  'RM 18,000.00',
  'Pembaikan Kecacatan Dalam Tempoh DLP',
  '2026-04-10',
  'A-12-08',
  'Residensi Harmoni',
  'Kedah',
  'No.20 Lebuh Pantai, 10300 George Town, Pulau Pinang',
  NOW()
FROM tmp_homeowner2_user
ON CONFLICT (homeowner_id) DO UPDATE
SET name = EXCLUDED.name,
    ic_number = EXCLUDED.ic_number,
    email = EXCLUDED.email,
    phone_number = EXCLUDED.phone_number,
    address = EXCLUDED.address,
    court_location = EXCLUDED.court_location,
    state_name = EXCLUDED.state_name,
    claim_amount = EXCLUDED.claim_amount,
    item_service = EXCLUDED.item_service,
    transaction_date = EXCLUDED.transaction_date,
    defect_unit = EXCLUDED.defect_unit,
    project_name = EXCLUDED.project_name,
    defect_state = EXCLUDED.defect_state,
    defect_property_address = EXCLUDED.defect_property_address,
    updated_at = NOW();

-- 3) OPTIONAL: UPSERT RESPONDENT PROFILE FOR USER 2
-- Use only if user 2 is intended to act as Developer/Legal/Admin in report context.
INSERT INTO report_respondent_profile
(respondent_id, company_name, person_in_charge, registration_number, email, phone_number, address, updated_at)
SELECT
    user_id,
    'Skyline Development Sdn. Bhd.',
    'Daniel Lee',
    '202301001111',
    'penang@skyline.com',
    '014-9988776',
    'No.20 Lebuh Pantai, 10300 George Town, Pulau Pinang',
    NOW()
FROM tmp_homeowner2_user
ON CONFLICT (respondent_id) DO UPDATE
SET company_name = EXCLUDED.company_name,
    person_in_charge = EXCLUDED.person_in_charge,
    registration_number = EXCLUDED.registration_number,
    email = EXCLUDED.email,
    phone_number = EXCLUDED.phone_number,
    address = EXCLUDED.address,
    updated_at = NOW();

DROP TABLE tmp_homeowner2_user;

COMMIT;
