-- Run once against the configured MySQL database before starting the
-- authenticated API. Existing customers retain their IDs and NULL hashes.
ALTER TABLE customers
    ADD COLUMN password_hash VARCHAR(255) NULL;

