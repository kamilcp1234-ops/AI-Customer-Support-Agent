# Setup and operations

This guide describes the current prototype setup. It is not a production deployment recipe.

## Prerequisites

- Python 3.10 or newer
- MySQL server and database
- Groq API key
- Reachable Hindsight service and API key

## Configuration

Create `.env` in the repository root. `backend/main.py` and its modules load environment variables from that location when run from the project root.

| Variable | Required | Purpose |
| --- | --- | --- |
| `MYSQL_HOST` | Yes | MySQL server host |
| `MYSQL_USER` | Yes | MySQL account |
| `MYSQL_PASSWORD` | Yes | MySQL password |
| `MYSQL_DATABASE` | Yes | Database name |
| `GROQ_API_KEY` | Yes | Groq API credential |
| `HINDSIGHT_BASE_URL` | Yes | Hindsight service URL |
| `HINDSIGHT_API_KEY` | Yes | Hindsight API credential |
| `SUPPORTAI_AUTH_SECRET` | Yes | Signs access tokens; must be at least 32 characters |
| `SUPPORT_API_URL` | No | API base URL used by both Streamlit apps; defaults to `http://127.0.0.1:8000` |

Use a unique, high-entropy authentication secret for each environment. Keep secrets in a local, ignored `.env` file for development and in a managed secret store for deployed environments. Never commit secrets or include them in logs, screenshots, or issue reports.

## Install and run locally

From the repository root:

```bash
python -m venv .venv
# Activate the environment for your shell, then:
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload
```

In separate terminals, start the customer and staff interfaces:

```bash
python -m streamlit run frontend/app.py --server.port 8501
python -m streamlit run frontend/admin_app.py --server.port 8502
```

The API's interactive docs are at `http://127.0.0.1:8000/docs` when running locally. For Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`; on macOS/Linux, use `source .venv/bin/activate`.

## Database initialization

There is no automated migration runner or initial schema migration. Back up existing data before schema changes. The following starter schema documents the columns expected by the app for a **fresh** database:

```sql
CREATE DATABASE supportai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE supportai;

CREATE TABLE customers (
    customer_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NULL
);

CREATE TABLE chat_history (
    chat_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    message TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_chat_customer FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);

CREATE TABLE complaints (
    complaint_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    subject VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'Pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_complaint_customer FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
```

For this fresh schema, apply migrations `003_staff_accounts_and_complaint_audit.sql` and `004_complaint_approval_and_resolution.sql` in that order. The base schema already has `password_hash` and Pending complaint status, so do **not** apply migrations 001 or 002 to it.

For a legacy schema, review the SQL and README migration notes carefully. Apply each applicable migration once and in order: 001 adds `customers.password_hash`; 002 adjusts complaint status support; 003 creates staff accounts and status audit fields; 004 adds complaint approval and resolution fields. Existing data may require schema-specific handling. The SQL files are not idempotent and there is no migration-version tracking.

## Provision staff

After the schema is ready, run this command from a trusted machine with database access:

```bash
python -m backend.provision_admin
```

It interactively requests a name, email, role (`admin` or `support`), and a 12–128 character password. Staff registration is not exposed as an API endpoint. Currently both staff roles can access the staff API operations; see [Security and privacy](security-and-privacy.md).

## Tests

```bash
python -m unittest discover -s tests -v
```

The current suite mocks MySQL and the AI/memory providers in its tested paths. Run additional integration tests in a disposable environment before relying on database migrations or deployed service behavior.

## Before deployment

At minimum, use HTTPS, restrict database privileges and network access, use managed secrets, configure provider and database monitoring, and back up data. Add rate limits, email verification and account recovery, data retention/deletion controls, operational logs, database connection pooling, migration management, integration tests, and an incident/recovery process before production use. See [Security and privacy](security-and-privacy.md).
