-- Fix for: value too long for type character varying(50)
-- Enlarge the urgency column to handle any data issues

BEGIN;

ALTER TABLE defects ALTER COLUMN urgency TYPE VARCHAR(100);

COMMIT;
