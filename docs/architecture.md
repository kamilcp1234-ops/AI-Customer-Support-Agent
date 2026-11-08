# Architecture and data flow

## System overview

SupportAI is a small, single-service prototype. Two Streamlit applications call one FastAPI backend; the backend owns authentication, MySQL access, AI requests, and complaint workflows.

```text
Browser
  ├─ Customer Streamlit app (frontend/app.py)
  └─ Staff Streamlit app (frontend/admin_app.py)
       │ HTTP requests with bearer tokens
       ▼
  FastAPI service (backend/main.py)
       ├─ MySQL: customers, staff, chat history, complaints
       ├─ Groq: response generation
       └─ Hindsight: customer-specific conversation memory
```

Both apps use `SUPPORT_API_URL` to locate the API; when unset, they use `http://127.0.0.1:8000`. The frontend applications are separate interfaces, not separate backend deployments or databases.

## Main components

- **`backend/main.py`** — API routes, request validation, authentication dependencies, and complaint workflow orchestration.
- **`backend/auth.py`** — scrypt password hashing and signed, expiring customer/staff tokens.
- **`backend/database.py`** — MySQL connection and queries for accounts, chat exchanges, dashboards, and complaints.
- **`backend/ai_agent.py`** — Groq response generation and Hindsight recall/retention.
- **`frontend/app.py`** — customer registration/login, chat, dashboard, complaints, and profile screens.
- **`frontend/admin_app.py`** — staff login, dashboard, complaint review, and status updates.
- **`backend/migrations/`** — manual SQL migrations for legacy schemas and added workflow features.

## Authentication and authorization flow

1. A customer or provisioned staff user signs in through the corresponding login endpoint.
2. The API returns a signed bearer token with a one-hour maximum age. Customer and staff tokens use different salts and token types.
3. Protected API routes verify the token and load the corresponding active account from MySQL.
4. Customer complaint reads and writes use the authenticated customer ID rather than trusting a customer ID supplied by the request.
5. Staff routes use the staff authentication dependency. In the current implementation, both `admin` and `support` roles pass that dependency; see [Security and privacy](security-and-privacy.md).

## Chat and memory flow

For an authenticated chat request, the API derives the customer ID from the token. The AI service recalls from a Hindsight bank named `customer-<customer_id>`, passes the message and recalled context to Groq, and attempts to retain the exchange in memory. The API then saves the user message and generated answer in MySQL.

Approved resolution preferences are also recorded in MySQL and may be retained in customer memory. The database is preferred for retrieving the latest recorded choice, with marked Hindsight memory used as a fallback if the database lookup fails.

## Complaint workflow

1. Customer creates a complaint; it starts with pending status and pending approval.
2. Staff accepts or rejects pending complaints. The decision records the staff account and timestamp; rejection may include a reason.
3. For an accepted complaint, staff can move status from Pending/Open to In Progress, then from In Progress to Resolved.
4. The customer can select a resolution option for an accepted complaint. The selection is scoped to the authenticated customer and written to MySQL before the memory-retention attempt.

## Current boundaries

- The agent does not query customer orders, shipment tracking, or company policy systems.
- It does not perform refunds, replacements, vouchers, or other external support actions; the resolution selection is a recorded preference, not proof an action was completed.
- MySQL stores chat messages, but the UI does not reload prior chat history into a new Streamlit session.
- `backend/hindsight_memory.py` is a standalone sample script, not the API's isolated customer-memory implementation.
- The application has no tenant/workspace model. Customer-specific memory does not provide business-level multi-tenant isolation.
