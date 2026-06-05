-- One-time cleanup: align stored defect status/completion dates with PDF closed filtering logic.
-- Context:
-- - DB status constraint only allows: Pending, In Progress, Completed, Delayed.
-- - App treats a case as "Closed" when status = Completed and completed_date <= CURRENT_DATE - 14 days.
-- - This script normalizes historical data and rebuilds completion_dates from defects.

BEGIN;

-- 1) For records manually requested as Closed in audit trail,
-- force completed_date to the auto-close cutoff so they are treated as closed immediately.
WITH close_requested AS (
    SELECT DISTINCT ON (defect_id)
        defect_id::int AS defect_id
    FROM audit_log
    WHERE defect_id IS NOT NULL
      AND details ? 'requested_status'
      AND details->>'requested_status' = 'Closed'
    ORDER BY defect_id, timestamp DESC
)
UPDATE defects d
SET status = 'Completed',
    completed_date = LEAST(
        COALESCE(d.completed_date, CURRENT_DATE - INTERVAL '14 days')::date,
        (CURRENT_DATE - INTERVAL '14 days')::date
    ),
    updated_at = NOW()
FROM close_requested cr
WHERE d.id = cr.defect_id;

-- 2) Defensive cleanup:
-- if a defect is In Progress/Pending/Delayed, it must not keep a completion date.
UPDATE defects
SET completed_date = NULL,
    updated_at = NOW()
WHERE status IN ('Pending', 'In Progress', 'Delayed')
  AND completed_date IS NOT NULL;

-- 3) Rebuild completion_dates from canonical defects table to avoid stale side-table values.
TRUNCATE TABLE completion_dates;

INSERT INTO completion_dates (defect_id, completed_date)
SELECT id, completed_date
FROM defects
WHERE completed_date IS NOT NULL;

COMMIT;
