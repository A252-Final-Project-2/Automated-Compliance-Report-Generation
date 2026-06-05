-- Fix for: null value in column "id" of relation "defects" violates not-null constraint
-- This script restores the SERIAL sequence for the id column if it was lost

BEGIN;

-- Check if the sequence exists, if not create it
CREATE SEQUENCE IF NOT EXISTS defects_id_seq;

-- Alter the id column to use the SERIAL type properly
-- First, set the sequence as the default for the id column
ALTER TABLE defects 
    ALTER COLUMN id SET DEFAULT nextval('defects_id_seq');

-- Ensure the sequence is owned by the table
ALTER SEQUENCE defects_id_seq OWNED BY defects.id;

-- Update the sequence to start after the highest existing id
SELECT setval('defects_id_seq', COALESCE((SELECT MAX(id) FROM defects), 0) + 1);

COMMIT;
