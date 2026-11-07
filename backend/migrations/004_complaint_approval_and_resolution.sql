-- Run once after migrations 001, 002, and 003.
-- Existing complaints remain available and enter the same review queue as
-- new complaints; no complaint or customer data is removed.
ALTER TABLE complaints
    ADD COLUMN approval_status ENUM('Pending', 'Accepted', 'Rejected')
        NOT NULL DEFAULT 'Pending',
    ADD COLUMN approval_decided_by_staff_id INT NULL,
    ADD COLUMN approval_decided_at TIMESTAMP NULL DEFAULT NULL,
    ADD COLUMN rejection_reason TEXT NULL,
    ADD COLUMN resolution ENUM('Refund', 'Replacement', 'Voucher') NULL,
    ADD COLUMN resolution_selected_at TIMESTAMP NULL DEFAULT NULL,
    ADD INDEX idx_complaints_customer_resolution
        (customer_id, approval_status, resolution_selected_at),
    ADD CONSTRAINT fk_complaints_approval_staff
        FOREIGN KEY (approval_decided_by_staff_id)
        REFERENCES staff_accounts(staff_id);
