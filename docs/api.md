# HTTP API reference

The FastAPI application is defined in `backend/main.py`. When running locally, interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

## Authentication

Except for `GET /`, `POST /auth/register`, `POST /auth/login`, and `POST /admin/auth/login`, routes require:

```http
Authorization: Bearer <access_token>
```

Customer and staff access tokens are separate, signed, and expire after one hour. Staff accounts are provisioned through the trusted-shell command `python -m backend.provision_admin`; there is no public staff-registration endpoint.

## Routes

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/` | Public | Basic API welcome response |
| `POST` | `/auth/register` | Public | Create a customer account |
| `POST` | `/auth/login` | Public | Authenticate a customer |
| `GET` | `/auth/me` | Customer | Get the authenticated customer profile |
| `POST` | `/chat` | Customer | Generate and save an AI support exchange |
| `POST` | `/complaints` | Customer | Create a complaint |
| `GET` | `/complaints` | Customer | List the authenticated customer's complaints |
| `PUT` | `/complaints/{complaint_id}/resolution` | Customer | Select a resolution for an accepted complaint |
| `GET` | `/dashboard` | Customer | Get the authenticated customer's complaint counts |
| `POST` | `/admin/auth/login` | Public | Authenticate a provisioned staff account |
| `GET` | `/admin/auth/me` | Staff | Get the authenticated staff profile |
| `GET` | `/admin/dashboard` | Staff | Get global customer and complaint counts |
| `GET` | `/admin/complaints` | Staff | List complaints with customer and staff audit details |
| `PUT` | `/admin/complaints/{complaint_id}/decision` | Staff | Accept or reject a pending complaint |
| `PUT` | `/admin/complaints/{complaint_id}/status` | Staff | Advance an accepted complaint's status |

## Request fields

All request bodies are JSON.

- **Register:** `name`, `email`, `password`, `confirm_password`. Password length is 8–128 characters.
- **Login:** `email`, `password`.
- **Chat:** `message` (1–10,000 characters).
- **Create complaint:** `subject` (up to 255 characters), `description` (up to 10,000 characters).
- **Select resolution:** `resolution` is one of `Refund`, `Replacement`, or `Voucher`.
- **Staff decision:** `decision` is `Accepted` or `Rejected`; optional `rejection_reason` is limited to 2,000 characters.
- **Staff status update:** `status` is `In Progress` or `Resolved`; the API enforces valid transitions.

## Example requests

Register a customer:

```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"name":"Casey Customer","email":"casey@example.com","password":"example-password","confirm_password":"example-password"}'
```

Send an authenticated chat message:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H 'Authorization: Bearer <access_token>' \
  -H 'Content-Type: application/json' \
  -d '{"message":"I need help with my issue."}'
```

Do not use the example password or token in a real deployment.

## Typical status codes

- `200` — request completed.
- `201` — account or complaint created.
- `401` — missing, invalid, expired, or inappropriate token; or failed staff authentication.
- `409` — duplicate account or invalid complaint decision/transition/resolution state.
- `422` — request validation failed.
- `503` — authentication configuration or an AI/chat persistence dependency is unavailable.

Exact response fields and validation behavior are defined by the running API's OpenAPI schema. This API is not currently versioned and list endpoints do not support pagination; both should be addressed before external integrations depend on a stable contract.
