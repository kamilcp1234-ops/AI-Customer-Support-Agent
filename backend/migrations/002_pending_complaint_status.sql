-- Preserve existing status labels while supporting Pending for new complaints.
-- Nullable keeps any pre-existing NULL values intact during the type change.
ALTER TABLE complaints
    MODIFY COLUMN status VARCHAR(32) NULL DEFAULT 'Pending';
