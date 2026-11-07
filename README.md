# SupportAI

SupportAI is a customer support demo that combines a FastAPI service, separate customer and staff Streamlit applications, Groq-powered responses, MySQL records, and Hindsight persistent memory. Customers can chat with the support assistant, register complaints, review their complaints, and see complaint statistics tied to their account. Staff use a separate authenticated dashboard to manage the same complaint records. 

## The problem and the solution

Support conversations often lose customer context between sessions. That can force customers to repeat preferences or explain earlier issues. SupportAI stores chat records in MySQL and uses Hindsight to recall relevant customer-specific memories when generating a later response. Customers also have authenticated accounts and can manage their own complaint records.

The assistant is a demo: it does not connect to order systems or perform refunds, replacements, shipping, or other real-world support actions.

## Features

- Customer registration and login with password hashing and signed, expiring bearer tokens.
- Authenticated AI chat using the Groq API.
- Per-customer Hindsight banks for recalling and retaining conversation context.
- MySQL storage for customer accounts, chat messages and responses, and complaints.
- Customer-scoped complaint lists and dashboard counts, with read-only complaint statuses.
- Streamlit screens for chat, complaints, the customer dashboard, and profile details.
- Separate Admin/Support login, global support dashboard, and complaint queue.
- Staff-only complaint status transitions with staff and timestamp audit fields.

## Architecture

```text
Browser
  └─ Streamlit frontend (frontend/app.py)
       └─ HTTP + bearer token
            └─ FastAPI backend (backend/main.py)
                 ├─ MySQL (accounts, chat history, complaints)
                 ├─ Groq API (support response generation)
                 └─ Hindsight service (customer conversation memory)
```

Both interfaces call the same FastAPI service and use the same MySQL database. The API validates customer and staff tokens separately. Customer IDs come from authenticated customer records; staff roles and active status are rechecked from `staff_accounts` for every admin API request.

## Technology stack

- Python
- FastAPI, Pydantic, Uvicorn
- Streamlit
- Groq Python client
- Hindsight Python client
- MySQL Connector/Python
- `itsdangerous` signed timed tokens and Python `hashlib.scrypt` password hashes
- `unittest` and FastAPI `TestClient`

## Persistent memory and customer isolation

For each chat, `backend/ai_agent.py` builds a Hindsight bank ID as `customer-<customer_id>`. It creates that bank if needed, recalls memories relevant to the current message, includes the recalled text in the Groq prompt, and retains the new customer message and assistant response in the same bank. That stable per-customer bank ID keeps one customer’s recalled conversation context separate from another customer’s context.

MySQL also receives each chat message and response. This codebase does not currently expose a chat-history endpoint or reload saved messages into the Streamlit transcript after a new session. Hindsight recall is the implemented cross-session conversational memory path.

`backend/hindsight_memory.py` is a standalone demonstration script with hard-coded sample content and a shared demo bank. It is not the API’s customer-isolated memory implementation; do not import or run it against real customer data.

## Project structure

```text
.
├── backend/
│   ├── main.py                     # FastAPI routes and request models
│   ├── auth.py                     # Password hashing and timed tokens
│   ├── database.py                 # MySQL access and customer-scoped queries
│   ├── ai_agent.py                 # Groq responses and per-customer memory
│   ├── hindsight_memory.py         # Standalone sample/demo script
│   ├── provision_admin.py          # Interactive staff account provisioning
│   ├── requirements.txt            # Python dependencies
│   ├── migrations/
│   │   ├── 001_add_password_hash.sql
│   │   ├── 002_pending_complaint_status.sql
│   │   ├── 003_staff_accounts_and_complaint_audit.sql
│   │   └── 004_complaint_approval_and_resolution.sql
├── frontend/
│   ├── app.py                      # Customer Streamlit application
│   └── admin_app.py                # Separate Admin/Support application
├── tests/
│   └── test_auth.py                # API, auth, scoping, and memory tests
└── README.md
```

## Prerequisites

- Python 3.10 or newer.
- A running MySQL server and a database for SupportAI.
- A Groq API key and a reachable Hindsight service with its API key.
- Windows PowerShell or a shell with equivalent Python commands.

## Installation

Run commands from the project root.

1. Create and activate a virtual environment:

   ```powershell
   py -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

   On macOS/Linux, use `python3 -m venv venv` and `source venv/bin/activate`.

2. Install dependencies:

   ```powershell
   python -m pip install -r backend/requirements.txt
   ```

3. Create a local `.env` file in the project root and set the variable names listed below. Keep real credentials private and out of source control.

4. Create the MySQL database and tables as described next.

## MySQL setup

The repository contains a migration for `password_hash`, but it does not contain an initial schema migration. The application expects `customers`, `chat_history`, and `complaints` tables with the columns used by `backend/database.py`. For a new database, the following is a compatible starter schema; use your database name in place of `supportai`:

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

For a legacy database, back it up and apply migrations in order, once each: `001_add_password_hash.sql` if `customers.password_hash` is absent, `002_pending_complaint_status.sql` if the complaint status column has not been prepared for Pending, `003_staff_accounts_and_complaint_audit.sql` to create staff accounts and complaint audit fields, and `004_complaint_approval_and_resolution.sql` to add approval decisions and resolution selections. Migration 004 preserves existing complaint rows and puts them into the review queue. Do not rerun an applied migration.

For a fresh database created from the starter schema above, `password_hash` and Pending status are already present; apply migrations 003 and 004 after creating the three base tables. Existing legacy customer rows cannot be claimed through registration because SupportAI has no email verification flow.

The SQL above documents the columns the application uses; adapt types and constraints to the existing database before applying it to production data.

## Environment variable names

The backend loads `.env` using `python-dotenv`. Set these names in the project-root `.env` file; this README intentionally includes no secret values.

| Variable | Used for |
| --- | --- |
| `MYSQL_HOST` | MySQL server host |
| `MYSQL_USER` | MySQL account name |
| `MYSQL_PASSWORD` | MySQL account password |
| `MYSQL_DATABASE` | Database name |
| `GROQ_API_KEY` | Groq API authentication |
| `HINDSIGHT_BASE_URL` | Hindsight service URL |
| `HINDSIGHT_API_KEY` | Hindsight API authentication |
| `SUPPORTAI_AUTH_SECRET` | Signing auth tokens; must be at least 32 characters |
| `SUPPORT_API_URL` | Optional frontend API base URL; defaults to `http://127.0.0.1:8000` |

Never commit `.env`, paste credentials into logs, or put them in issues or screenshots.

## Run the application

Start the API from the project root:

```powershell
python -m uvicorn backend.main:app --reload
```

The API listens at `http://127.0.0.1:8000` by default. FastAPI's interactive docs are available at `http://127.0.0.1:8000/docs`.

In a second terminal with the environment activated, start the customer app on port 8501:

```powershell
python -m streamlit run frontend/app.py --server.port 8501
```

The frontend defaults to the local API URL above. Set `SUPPORT_API_URL` if the API runs elsewhere.

In another terminal, start the separate staff application on port 8502:

```powershell
python -m streamlit run frontend/admin_app.py --server.port 8502
```

The customer and staff applications have separate login pages, sessions, and navigation. Both use the same backend and MySQL complaint rows.

### Provisioning staff accounts

There is no public staff registration endpoint. After applying migrations 003 and 004, provision the first Admin and later Support accounts from a trusted machine with database access:

```powershell
python -m backend.provision_admin
```

The command prompts interactively for name, email, role (`admin` or `support`), and a 12-128 character password. Password input is hidden and the stored value uses the same salted scrypt hashing as customer accounts. Credentials are not seeded or printed. Protect access to the provisioning machine and database.

Staff sign in at the Admin app on port 8502. Customers continue to sign in at port 8501. Staff can review complaints and advance statuses; customers can only view their own complaint status. Customer bearer tokens cannot authorize `/admin/*` endpoints.

## Tests

From the project root, run:

```powershell
python -m unittest discover -s tests -v
```

The current suite uses mocks for MySQL, Groq, and Hindsight; it does not require live service credentials for its tested paths.

## API endpoints

All routes except `/`, `/auth/register`, `/auth/login`, and `/admin/auth/login` require an
`Authorization: Bearer <token>` header. `/admin/auth/login` only issues tokens for staff accounts
that were provisioned securely; it does not provide staff registration.

| Method | Path | Authentication | Description |
| --- | --- | --- | --- |
| `GET` | `/` | No | Health-style welcome response |
| `POST` | `/auth/register` | No | Create an account. JSON fields: `name`, `email`, `password`, `confirm_password`. Returns `201`; an already registered or existing legacy email returns `409`. |
| `POST` | `/auth/login` | No | Sign in with `email` and `password`; returns a bearer token and customer profile. |
| `GET` | `/auth/me` | Yes | Return the authenticated customer profile. |
| `POST` | `/chat` | Yes | Accept `{"message": "..."}`, generate a response with Groq and Hindsight, and save the exchange to MySQL. |
| `POST` | `/complaints` | Yes | Create a complaint from `subject` and `description`; returns its ID and initial `Pending` status. |
| `GET` | `/complaints` | Yes | List only the authenticated customer’s complaints. |
| `PUT` | `/complaints/{complaint_id}/resolution` | Yes | Save one resolution choice for the authenticated customer's accepted complaint. |
| `GET` | `/dashboard` | Yes | Return complaint totals and status counts for the authenticated customer. |
| `POST` | `/admin/auth/login` | No | Sign in with a provisioned staff account; returns a staff-only bearer token. There is no public staff registration route. |
| `GET` | `/admin/auth/me` | Staff | Return the authenticated staff profile. |
| `GET` | `/admin/dashboard` | Staff | Return global customer and complaint totals. |
| `GET` | `/admin/complaints` | Staff | List complaints with customer details and status audit information. |
| `PUT` | `/admin/complaints/{complaint_id}/decision` | Staff | Accept or reject a pending complaint; records staff, time, and optional rejection reason. |
| `PUT` | `/admin/complaints/{complaint_id}/status` | Staff | After acceptance, advance complaint progress from Pending/Open to In Progress, or In Progress to Resolved. |

Registration requires a password from 8 to 128 characters and a matching confirmation. Chat messages may be up to 10,000 characters; complaint subjects are limited to 255 characters and descriptions to 10,000 characters.

## Security measures

- Passwords are stored using salted `scrypt` hashes, not plaintext.
- Auth tokens are signed and expire after one hour; a signing secret of at least 32 characters is required.
- Protected endpoints resolve the customer from the token and scope complaint and dashboard queries to that customer.
- Staff tokens use a separate signing salt and token type; admin routes reload the active staff account and role from MySQL.
- Staff registration is disabled in the API; privileged accounts are created through the interactive provisioning command.
- Admin status updates lock the existing complaint row and record staff ID and update time. Customer APIs do not expose a status update route.
- Approval decisions are staff-only. Resolution selections are customer-owned, require an accepted complaint, and update MySQL before a marked preference is retained in that customer's Hindsight bank.
- SQL uses parameterized statements for user-supplied values.
- Request validation errors avoid echoing password inputs.
- `.gitignore` excludes `.env`; keep credentials in local or managed secret configuration.

Use HTTPS and restricted database credentials when deploying. The app currently has no rate limiting, email verification, password reset flow, or general operational audit log. Complaint status changes record the updating staff account and timestamp.

## Current limitations and future improvements

- **Email ownership:** registration cannot verify email ownership. Existing legacy rows are preserved and blocked from self-service claiming; add a verified recovery/linking flow before enabling account attachment.
- **Admin account recovery:** staff accounts must be provisioned from a trusted shell; there is no self-service staff registration, password reset, or staff management UI.
- **Chat history UI:** messages are saved in MySQL, but the Streamlit transcript is session-local and is not restored from the database.
- **Database setup:** the repository lacks a versioned initial schema migration; only the password-hash migration is included.
- **External service failures:** Groq and Hindsight calls do not yet have a documented retry or recovery workflow.
- **Operations:** add rate limiting, structured safe logging, deployment configuration, health checks for dependencies, and data retention/deletion controls before production use.

