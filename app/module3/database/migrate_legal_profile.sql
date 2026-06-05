-- Migration: Add legal_user_id column to report_legal_profile table
-- This migration links the legal profile to user accounts

BEGIN;

-- Step 1: Add legal_user_id column if it doesn't exist
ALTER TABLE report_legal_profile
ADD COLUMN IF NOT EXISTS legal_user_id INTEGER UNIQUE;

-- Step 2: Add foreign key constraint
ALTER TABLE report_legal_profile
ADD CONSTRAINT fk_legal_user_id FOREIGN KEY (legal_user_id) 
REFERENCES users(id) ON DELETE CASCADE;

-- Step 3: Ensure the new column is NOT NULL (if needed in future, after data migration)
-- For now, allow NULL to preserve existing data

COMMIT;
