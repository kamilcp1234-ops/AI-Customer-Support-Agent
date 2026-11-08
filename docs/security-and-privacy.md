# Security and privacy

## Scope

This is a static, source-based summary of the prototype's current behavior—not a security certification or penetration-test report. Do not treat the application as production-ready for real customer data. Reassess the code and deployment configuration before each deployment.

## Existing safeguards observed in the code

- Passwords are hashed with salted `scrypt`; plaintext passwords are not stored.
- Customer and staff access tokens are signed, expire after one hour, and use separate token salts/types.
- Protected routes reload the account from MySQL; staff access checks active status and an allowed role.
- Customer complaint reads and resolution writes are scoped to the authenticated customer's ID.
- SQL statements use parameterized values for user-supplied data.
- Complaint approval and status updates record staff identity and timestamps.
- AI/provider errors are returned without exposing provider exception details to the client.

These controls are useful foundations, but do not by themselves make the application secure for production.

## Risks and gaps to address

### Authentication and abuse protection

- Customer login distinguishes an unknown email from an incorrect password, enabling account enumeration. Registration also reports duplicate email addresses.
- No rate limiting or lockout was found on login, registration, or chat endpoints. This leaves the API open to password guessing and resource/cost abuse.
- Email ownership verification, password reset, MFA, and customer session revocation are not implemented.
- Tokens remain usable until expiry; there is no general revocation mechanism.

### Staff permissions and audit

- Both `admin` and `support` roles pass the same staff dependency. The reviewed staff routes do not implement separate role-specific permissions.
- Complaint audit fields record approval/status changes, but a general audit log for account and administrative activity is not present.
- The global staff complaint endpoint returns customer-identifying information and the full complaint list without pagination. Limit fields, roles, and result sizes to business need.

### AI and data handling

- Chat messages and recalled memory are sent to external AI/memory providers. Review provider terms, data location, retention, and configuration before sending personal or sensitive data.
- Conversation content and AI responses are retained in MySQL and Hindsight. User-facing opt-out, deletion, and retention controls are not implemented.
- User messages and recalled memories are untrusted input to the model. Prompt instructions are not a security boundary; apply strict validation and authorization in application code for any future tools or external actions.
- The assistant does not perform order lookups, refunds, replacements, or other support actions. A saved resolution preference is not evidence that a refund or other action occurred.

### Deployment and operations

- The repository does not include production deployment configuration, a migration runner, dependency vulnerability automation, or integration testing against a real test database.
- Use HTTPS, managed secrets, least-privilege database credentials, network restrictions, backups, monitoring, and a tested recovery process.
- Add structured logging that avoids passwords, tokens, API keys, and unnecessary customer content. Define retention and access controls for operational logs.
- Add database connection pooling/timeouts, health/readiness checks, bounded provider retry behavior, and incident monitoring before production.

## Recommended remediation order

1. Add rate limits and use consistent login errors.
2. Define and enforce permissions separately for admin and support roles.
3. Add pagination and minimize personal information returned by staff endpoints.
4. Implement account recovery and a session revocation strategy.
5. Define AI-provider data terms, retention, opt-out/deletion, and prompt-injection safeguards.
6. Add deployment hardening, monitoring, migration tracking, and integration/security tests.

## Reporting a security issue

Do not post credentials, customer information, or exploitable details in public issues. Contact the repository maintainer privately to coordinate disclosure. No dedicated security contact or disclosure policy is currently documented.
