-- Run after migrations 001 and 002. No staff credentials are seeded here.
CREATE TABLE staff_accounts (
    staff_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'support') NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE complaints
    ADD COLUMN status_updated_by_staff_id INT NULL,
    ADD COLUMN status_updated_at TIMESTAMP NULL DEFAULT NULL,
    ADD CONSTRAINT fk_complaints_status_staff
        FOREIGN KEY (status_updated_by_staff_id)
        REFERENCES staff_accounts(staff_id);
