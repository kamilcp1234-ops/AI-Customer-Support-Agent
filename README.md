# SupportAI

**An AI-powered customer-support prototype with persistent customer context and a staff-managed complaint workflow.**

SupportAI combines a FastAPI backend, separate Streamlit customer and staff apps, MySQL storage, Groq-generated responses, and Hindsight memory. It is intended for demonstration and evaluation—not yet as a production-ready, drop-in support platform.

> **Project status:** Prototype. It does not connect to order systems or execute refunds, replacements, shipping, or other real-world support actions. Review [Security and privacy](docs/security-and-privacy.md) before using real customer data.

## What it does

- Customer registration, login, and authenticated support chat.
- Stores chat exchanges and complaints in MySQL.
- Uses a customer-specific Hindsight bank to recall and retain conversation context.
- Lets customers submit complaints, check status, and choose a resolution after staff acceptance.
- Provides a separate staff app to review complaints and update their status.
- Exposes the backend as a documented HTTP API.

## How it fits together

```text
Customer app (Streamlit) ─┐
                           ├─ FastAPI ─ MySQL
Staff app (Streamlit) ─────┘          ├─ Groq API
                                      └─ Hindsight service
```

See [Architecture](docs/architecture.md) for component responsibilities and current limitations.

## Quick start

### Requirements

- Python 3.10 or newer
- MySQL server and a database
- Groq API key
- Reachable Hindsight service and API key

### Install

From the repository root, create and activate a virtual environment, then install dependencies:

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

python -m pip install -r backend/requirements.txt
```

Create a project-root `.env` file and configure the required values:

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_USER=your_database_user
MYSQL_PASSWORD=your_database_password
MYSQL_DATABASE=supportai
GROQ_API_KEY=your_groq_api_key
HINDSIGHT_BASE_URL=https://your-hindsight-service
HINDSIGHT_API_KEY=your_hindsight_api_key
SUPPORTAI_AUTH_SECRET=replace-with-a-random-secret-at-least-32-characters
```

Keep `.env` and all real credentials out of version control. The API requires `SUPPORTAI_AUTH_SECRET` to be at least 32 characters. See [Setup and operations](docs/setup-and-operations.md) for database initialization, migration order, and deployment notes.

### Start the services

Open separate terminals from the project root (with the environment activated in each):

```bash
python -m uvicorn backend.main:app --reload
```

```bash
python -m streamlit run frontend/app.py --server.port 8501
```

```bash
python -m streamlit run frontend/admin_app.py --server.port 8502
```

The API defaults to `http://127.0.0.1:8000`; its interactive API docs are at `http://127.0.0.1:8000/docs`. The customer and staff apps default to that local API address. Set `SUPPORT_API_URL` if the API is hosted elsewhere.

Provision staff accounts from a trusted environment after applying the required database migrations:

```bash
python -m backend.provision_admin
```

This interactive command creates an `admin` or `support` account. Staff use the separate app on port 8502.

## Documentation

- [Architecture and data flow](docs/architecture.md)
- [HTTP API reference](docs/api.md)
- [Setup, database, and operations](docs/setup-and-operations.md)
- [Security, privacy, and known gaps](docs/security-and-privacy.md)

## Run tests

From the repository root:

```bash
python -m unittest discover -s tests -v
```

The current suite mocks MySQL, Groq, and Hindsight for tested paths; it does not replace integration testing with deployed services.

## Important limitations

- No order, shipment, refund, or commerce-system integration.
- Chat records are saved, but there is no chat-history API or UI to restore transcripts after a new Streamlit session.
- Email verification, password reset, rate limiting, data-retention/deletion controls, deployment configuration, and general operational audit logging are not implemented.
- The initial database schema is documented but not managed by a migration runner; migrations are manual and order-sensitive.
- This project has no license file yet. Obtain permission before reusing or redistributing it.

See [Security and privacy](docs/security-and-privacy.md) and [Setup and operations](docs/setup-and-operations.md) before any deployment or use with real customer data.
