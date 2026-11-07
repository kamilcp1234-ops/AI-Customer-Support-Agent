import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from itsdangerous import BadSignature


# Deliberately fake credentials keep tests offline and never expose deployment secrets.
os.environ["GROQ_API_KEY"] = "test-groq-key"
os.environ["HINDSIGHT_BASE_URL"] = "http://127.0.0.1:1"
os.environ["HINDSIGHT_API_KEY"] = "test-hindsight-key"
os.environ["SUPPORTAI_AUTH_SECRET"] = "unit-test-auth-secret-at-least-32-characters"

from fastapi.testclient import TestClient

from backend import auth, database
from backend import ai_agent
from backend.main import app


CUSTOMER = {
    "customer_id": 42,
    "name": "Casey Customer",
    "email": "casey@example.com",
}
STAFF = {
    "staff_id": 7,
    "name": "Sam Support",
    "email": "sam@example.com",
    "role": "support",
    "is_active": True,
}
PASSWORD = "correct-horse-123"


class AuthenticationApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.customer_lookup = patch.object(
            database, "get_customer_by_id", return_value=CUSTOMER
        )
        self.customer_lookup.start()
        self.addCleanup(self.customer_lookup.stop)

    def bearer(self, customer_id=42):
        return {"Authorization": f"Bearer {auth.issue_access_token(customer_id)}"}

    def staff_bearer(self, staff_id=7):
        return {"Authorization": f"Bearer {auth.issue_staff_access_token(staff_id)}"}

    def test_register_hashes_password_and_returns_no_hash(self):
        with patch.object(
            database, "register_customer_account", return_value=CUSTOMER
        ) as register:
            response = self.client.post(
                "/auth/register",
                json={
                    "name": "Casey Customer",
                    "email": " CASEY@EXAMPLE.COM ",
                    "password": PASSWORD,
                    "confirm_password": PASSWORD,
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["customer"]["customer_id"], 42)
        self.assertEqual(response.json()["message"], "Registration successful! Please log in.")
        self.assertNotIn("access_token", response.json())
        self.assertNotIn("password_hash", response.text)
        self.assertNotIn(PASSWORD, response.text)
        args = register.call_args.args
        self.assertEqual(args[1], "casey@example.com")
        self.assertNotEqual(args[2], PASSWORD)
        self.assertTrue(auth.verify_password(PASSWORD, args[2]))

    def test_legacy_email_without_password_cannot_be_claimed(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.fetchone.return_value = {
            "customer_id": 19,
            "name": "Existing Customer",
            "email": "existing@example.com",
            "password_hash": None,
        }
        with patch.object(database, "get_connection", return_value=connection):
            with self.assertRaises(database.DuplicateCustomerEmailError):
                database.register_customer_account(
                    "Submitted Name",
                    " EXISTING@EXAMPLE.COM ",
                    "scrypt$already-hashed",
                )

        self.assertEqual(len(cursor.execute.call_args_list), 1)
        self.assertFalse(connection.commit.called)
        self.assertFalse(connection.rollback.called)

    def test_duplicate_registration_returns_clear_conflict(self):
        with patch.object(
            database,
            "register_customer_account",
            side_effect=database.DuplicateCustomerEmailError(),
        ):
            response = self.client.post(
                "/auth/register",
                json={
                    "name": "Casey",
                    "email": "casey@example.com",
                    "password": PASSWORD,
                    "confirm_password": PASSWORD,
                },
            )
        self.assertEqual(response.status_code, 409)
        self.assertIn("already exists", response.json()["detail"])

    def test_invalid_registration_is_clear_and_does_not_echo_password(self):
        submitted_password = "tiny-secret"
        response = self.client.post(
            "/auth/register",
            json={
                "name": "Casey",
                "email": "not-an-email",
                "password": submitted_password,
                "confirm_password": submitted_password,
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(submitted_password, response.text)
        self.assertIn("valid email", response.text)

    def test_password_length_and_confirmation_are_enforced_without_echo(self):
        short_password = "tiny"
        response = self.client.post(
            "/auth/register",
            json={
                "name": "Casey",
                "email": "casey@example.com",
                "password": short_password,
                "confirm_password": short_password,
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("8 and 128", response.text)
        self.assertNotIn(short_password, response.text)

        mismatch = self.client.post(
            "/auth/register",
            json={
                "name": "Casey",
                "email": "casey@example.com",
                "password": PASSWORD,
                "confirm_password": "another-valid-password",
            },
        )
        self.assertEqual(mismatch.status_code, 422)
        self.assertNotIn(PASSWORD, mismatch.text)
        self.assertNotIn("another-valid-password", mismatch.text)

    def test_login_success_and_incorrect_password(self):
        stored_hash = auth.hash_password(PASSWORD)
        with patch.object(
            database,
            "get_customer_auth_by_email",
            return_value={**CUSTOMER, "password_hash": stored_hash},
        ):
            response = self.client.post(
                "/auth/login",
                json={"email": " CASEY@EXAMPLE.COM ", "password": PASSWORD},
            )
        self.assertEqual(response.status_code, 200)
        token = response.json()["access_token"]
        self.assertEqual(auth.verify_access_token(token), 42)
        self.assertNotIn(stored_hash, response.text)
        self.assertNotIn(PASSWORD, response.text)

        with patch.object(
            database,
            "get_customer_auth_by_email",
            return_value={**CUSTOMER, "password_hash": stored_hash},
        ):
            bad_response = self.client.post(
                "/auth/login",
                json={"email": "casey@example.com", "password": "wrong-password"},
            )
        self.assertEqual(bad_response.status_code, 401)
        self.assertEqual(
            bad_response.json()["detail"],
            "Incorrect password. Please try again.",
        )
        self.assertNotIn("access_token", bad_response.json())
        self.assertNotIn("wrong-password", bad_response.text)

    def test_login_unknown_email_prompts_registration_without_session(self):
        with patch.object(database, "get_customer_auth_by_email", return_value=None):
            response = self.client.post(
                "/auth/login",
                json={"email": "new@example.com", "password": PASSWORD},
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"],
            "Account not found. Please register first.",
        )
        self.assertNotIn("access_token", response.json())

    def test_protected_routes_reject_missing_token(self):
        with patch.object(database, "get_all_complaints") as complaints:
            response = self.client.get("/complaints")
        self.assertEqual(response.status_code, 401)
        complaints.assert_not_called()
        self.assertEqual(self.client.get("/dashboard").status_code, 401)
        self.assertEqual(self.client.post("/chat", json={"message": "Hi"}).status_code, 401)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)

    def test_chat_and_complaints_are_scoped_to_token_customer(self):
        headers = self.bearer(42)
        with (
            patch("backend.main.get_ai_response", return_value="Helpful reply") as ai,
            patch.object(database, "save_chat_history") as save_history,
        ):
            chat_response = self.client.post(
                "/chat",
                headers=headers,
                json={"message": "Where is my order?"},
            )
        self.assertEqual(chat_response.status_code, 200)
        ai.assert_called_once_with("Where is my order?", 42)
        save_history.assert_called_once_with(
            42, "Where is my order?", "Helpful reply"
        )

        with (
            patch.object(database, "get_all_complaints", return_value=[]) as get_complaints,
            patch("backend.main.get_approved_resolution_preference", return_value=None),
        ):
            list_response = self.client.get("/complaints", headers=headers)
        self.assertEqual(list_response.status_code, 200)
        get_complaints.assert_called_once_with(42)

        with patch.object(database, "save_complaint", return_value=88) as save:
            create_response = self.client.post(
                "/complaints",
                headers=headers,
                json={"subject": "Damaged item", "description": "It arrived broken."},
            )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["status"], "Pending")
        self.assertEqual(create_response.json()["approval_status"], "Pending")
        self.assertEqual(
            create_response.json()["message"],
            "Your complaint is awaiting admin review.",
        )
        save.assert_called_once_with(42, "Damaged item", "It arrived broken.")

    def test_customer_status_update_route_is_removed(self):
        response = self.client.put(
            "/complaints/100",
            headers=self.bearer(42),
            json={"status": "Resolved"},
        )
        self.assertEqual(response.status_code, 404)

    def test_new_complaints_are_inserted_as_pending(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.lastrowid = 88
        with patch.object(database, "get_connection", return_value=connection):
            complaint_id = database.save_complaint(42, "Damaged item", "Broken")

        self.assertEqual(complaint_id, 88)
        sql, params = cursor.execute.call_args.args
        self.assertIn("status", sql)
        self.assertIn("'Pending'", sql)
        self.assertEqual(params, (42, "Damaged item", "Broken"))

    def test_complaint_sql_filters_by_customer_id(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        with patch.object(database, "get_connection", return_value=connection):
            database.get_all_complaints(42)
        select_sql, select_params = cursor.execute.call_args.args
        self.assertIn("WHERE customer_id = %s", select_sql)
        self.assertEqual(select_params, (42,))

    def test_database_resources_close_when_queries_fail(self):
        operations = [
            (database.get_or_create_customer, ("Casey", "casey@example.com")),
            (database.get_customer_auth_by_email, ("casey@example.com",)),
            (database.register_customer_account, ("Casey", "casey@example.com", "hash")),
            (database.save_chat_history, (42, "Hi", "Hello")),
            (database.save_complaint, (42, "Subject", "Description")),
            (database.get_all_complaints, (42,)),
            (database.get_dashboard_stats, (42,)),
        ]

        for operation, args in operations:
            with self.subTest(args=args):
                connection = MagicMock()
                cursor = MagicMock()
                connection.cursor.return_value = cursor
                cursor.execute.side_effect = RuntimeError("database internals")
                with patch.object(database, "get_connection", return_value=connection):
                    with self.assertRaisesRegex(RuntimeError, "database internals"):
                        operation(*args)
                cursor.close.assert_called_once()
                connection.close.assert_called_once()

    def test_database_resources_close_when_commits_fail(self):
        operations = [
            (database.get_or_create_customer, ("Casey", "casey@example.com")),
            (database.register_customer_account, ("Casey", "casey@example.com", "hash")),
            (database.save_chat_history, (42, "Hi", "Hello")),
            (database.save_complaint, (42, "Subject", "Description")),
        ]

        for operation, args in operations:
            with self.subTest(args=args):
                connection = MagicMock()
                cursor = MagicMock()
                connection.cursor.return_value = cursor
                cursor.fetchone.return_value = None
                connection.commit.side_effect = RuntimeError("commit internals")
                with patch.object(database, "get_connection", return_value=connection):
                    with self.assertRaisesRegex(RuntimeError, "commit internals"):
                        operation(*args)
                cursor.close.assert_called_once()
                connection.close.assert_called_once()

    def test_connection_closes_even_if_cursor_close_fails(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.close.side_effect = RuntimeError("close internals")
        with patch.object(database, "get_connection", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "close internals"):
                database.save_chat_history(42, "Hi", "Hello")
        connection.close.assert_called_once()

    def test_dashboard_still_works_for_authenticated_customer(self):
        stats = {
            "total_complaints": 3,
            "pending_complaints": 1,
            "in_progress_complaints": 1,
            "resolved_complaints": 1,
        }
        with patch.object(database, "get_dashboard_stats", return_value=stats) as get_stats:
            response = self.client.get("/dashboard", headers=self.bearer())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), stats)
        get_stats.assert_called_once_with(42)

    def test_dashboard_query_scopes_every_count_to_customer(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.fetchone.return_value = {
            "total_complaints": 2,
            "pending_complaints": 1,
            "in_progress_complaints": 0,
            "resolved_complaints": 1,
        }
        with patch.object(database, "get_connection", return_value=connection):
            stats = database.get_dashboard_stats(42)

        sql, params = cursor.execute.call_args.args
        self.assertEqual(params, (42, 42, 42, 42))
        self.assertEqual(sql.count("customer_id = %s"), 4)
        self.assertIn("status IN ('Pending', 'Open')", sql)
        self.assertNotIn("FROM customers)", sql)
        self.assertEqual(stats["total_complaints"], 2)

    def test_hindsight_bank_id_stays_bound_to_customer_id(self):
        memory = MagicMock()
        memory.recall.return_value.results = []
        groq = MagicMock()
        groq.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="A support response."))
        ]
        with (
            patch.object(ai_agent, "memory_client", memory),
            patch.object(ai_agent, "groq_client", groq),
        ):
            answer = ai_agent.get_ai_response("Hello", 42)

        self.assertEqual(answer, "A support response.")
        memory.create_bank.assert_called_once_with(
            bank_id="customer-42",
            name="Customer 42",
        )
        memory.retain.assert_called_once()
        self.assertEqual(memory.retain.call_args.kwargs["bank_id"], "customer-42")

    def test_hindsight_recall_failure_degrades_without_leaking_error(self):
        memory = MagicMock()
        memory.recall.side_effect = RuntimeError("private Hindsight API key")
        groq = MagicMock()
        groq.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="Helpful response."))
        ]
        with (
            patch.object(ai_agent, "memory_client", memory),
            patch.object(ai_agent, "groq_client", groq),
            self.assertLogs(ai_agent.logger, level="WARNING") as logs,
        ):
            answer = ai_agent.get_ai_response("Hello", 42)

        self.assertEqual(answer, "Helpful response.")
        self.assertFalse(memory.retain.called)
        self.assertNotIn("private Hindsight API key", " ".join(logs.output))

    def test_hindsight_retain_failure_does_not_discard_answer(self):
        memory = MagicMock()
        memory.recall.return_value.results = []
        memory.retain.side_effect = RuntimeError("private Hindsight API key")
        groq = MagicMock()
        groq.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="Helpful response."))
        ]
        with (
            patch.object(ai_agent, "memory_client", memory),
            patch.object(ai_agent, "groq_client", groq),
            self.assertLogs(ai_agent.logger, level="WARNING") as logs,
        ):
            answer = ai_agent.get_ai_response("Hello", 42)

        self.assertEqual(answer, "Helpful response.")
        self.assertNotIn("private Hindsight API key", " ".join(logs.output))

    def test_groq_failure_raises_safe_service_error(self):
        memory = MagicMock()
        memory.recall.return_value.results = []
        groq = MagicMock()
        groq.chat.completions.create.side_effect = RuntimeError("private Groq API key")
        with (
            patch.object(ai_agent, "memory_client", memory),
            patch.object(ai_agent, "groq_client", groq),
        ):
            with self.assertRaises(ai_agent.AIServiceUnavailable) as raised:
                ai_agent.get_ai_response("Hello", 42)

        self.assertNotIn("private Groq API key", str(raised.exception))

    def test_chat_ai_and_history_failures_return_safe_errors(self):
        headers = self.bearer()
        with patch(
            "backend.main.get_ai_response",
            side_effect=ai_agent.AIServiceUnavailable("private provider detail"),
        ), patch.object(database, "save_chat_history") as save_history:
            ai_response = self.client.post(
                "/chat", headers=headers, json={"message": "Hello"}
            )

        self.assertEqual(ai_response.status_code, 503)
        self.assertIn("temporarily unavailable", ai_response.json()["detail"])
        self.assertNotIn("private provider detail", ai_response.text)
        save_history.assert_not_called()

        with (
            patch("backend.main.get_ai_response", return_value="Helpful response."),
            patch.object(
                database,
                "save_chat_history",
                side_effect=RuntimeError("private database credentials"),
            ),
        ):
            db_response = self.client.post(
                "/chat", headers=headers, json={"message": "Hello"}
            )

        self.assertEqual(db_response.status_code, 503)
        self.assertIn("could not be saved", db_response.json()["detail"])
        self.assertNotIn("private database credentials", db_response.text)

    def test_admin_and_customer_tokens_are_separate(self):
        customer_token = auth.issue_access_token(42)
        staff_token = auth.issue_staff_access_token(7)
        self.assertEqual(auth.verify_staff_access_token(staff_token), 7)
        with self.assertRaises(BadSignature):
            auth.verify_staff_access_token(customer_token)
        with self.assertRaises(BadSignature):
            auth.verify_access_token(staff_token)

    def test_customer_token_is_rejected_by_every_admin_endpoint(self):
        headers = self.bearer(42)
        with patch.object(database, "get_staff_by_id") as staff_lookup:
            responses = [
                self.client.get("/admin/auth/me", headers=headers),
                self.client.get("/admin/dashboard", headers=headers),
                self.client.get("/admin/complaints", headers=headers),
                self.client.put(
                    "/admin/complaints/88/status",
                    headers=headers,
                    json={"status": "In Progress"},
                ),
            ]
        self.assertEqual([response.status_code for response in responses], [401] * 4)
        staff_lookup.assert_not_called()

    def test_admin_login_issues_staff_only_token(self):
        staff_hash = auth.hash_password(PASSWORD)
        staff_auth = {**STAFF, "password_hash": staff_hash}
        with patch.object(database, "get_staff_auth_by_email", return_value=staff_auth):
            response = self.client.post(
                "/admin/auth/login",
                json={"email": STAFF["email"], "password": PASSWORD},
            )

        self.assertEqual(response.status_code, 200)
        token = response.json()["access_token"]
        self.assertEqual(auth.verify_staff_access_token(token), STAFF["staff_id"])
        with self.assertRaises(BadSignature):
            auth.verify_access_token(token)
        self.assertNotIn(staff_hash, response.text)

    def test_admin_can_access_protected_dashboard_and_complaint_list(self):
        stats = {
            "total_customers": 4,
            "total_complaints": 6,
            "pending_complaints": 2,
            "in_progress_complaints": 2,
            "resolved_complaints": 2,
        }
        complaint = {
            "complaint_id": 88,
            "customer_id": 42,
            "customer_name": CUSTOMER["name"],
            "customer_email": CUSTOMER["email"],
            "subject": "Damaged item",
            "description": "The item arrived broken.",
            "status": "Pending",
            "created_at": "2026-11-07T12:00:00",
            "status_updated_at": None,
            "status_updated_by": None,
        }
        with (
            patch.object(database, "get_staff_by_id", return_value=STAFF),
            patch.object(database, "get_admin_dashboard_stats", return_value=stats),
            patch.object(database, "get_all_complaints_for_staff", return_value=[complaint]),
        ):
            dashboard = self.client.get("/admin/dashboard", headers=self.staff_bearer())
            complaint_list = self.client.get("/admin/complaints", headers=self.staff_bearer())

        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json(), stats)
        self.assertEqual(complaint_list.status_code, 200)
        self.assertEqual(complaint_list.json()["complaints"][0]["customer_email"], CUSTOMER["email"])

    def test_admin_transitions_sync_to_customer_views_and_dashboard(self):
        complaint = {
            "complaint_id": 88,
            "customer_id": 42,
            "customer_name": CUSTOMER["name"],
            "customer_email": CUSTOMER["email"],
            "subject": "Damaged item",
            "description": "The item arrived broken.",
            "status": "Pending",
            "created_at": "2026-11-07T12:00:00",
            "status_updated_at": None,
            "status_updated_by": None,
        }

        def update_status(complaint_id, next_status, staff_id):
            self.assertEqual(complaint_id, complaint["complaint_id"])
            complaint["status"] = next_status
            complaint["status_updated_by_staff_id"] = staff_id
            complaint["status_updated_by"] = STAFF["name"]
            complaint["status_updated_at"] = "2026-11-07T13:00:00"
            return {"complaint_id": complaint_id, "status": next_status}

        def dashboard_stats(customer_id):
            self.assertEqual(customer_id, CUSTOMER["customer_id"])
            status_value = complaint["status"]
            return {
                "total_complaints": 1,
                "pending_complaints": int(status_value in {"Pending", "Open"}),
                "in_progress_complaints": int(status_value == "In Progress"),
                "resolved_complaints": int(status_value == "Resolved"),
            }

        with (
            patch.object(database, "get_staff_by_id", return_value=STAFF),
            patch.object(database, "update_complaint_status_by_staff", side_effect=update_status) as update,
            patch.object(database, "get_all_complaints", side_effect=lambda customer_id: [complaint]),
            patch.object(database, "get_dashboard_stats", side_effect=dashboard_stats),
            patch("backend.main.get_approved_resolution_preference", return_value=None),
        ):
            in_progress = self.client.put(
                "/admin/complaints/88/status",
                headers=self.staff_bearer(),
                json={"status": "In Progress"},
            )
            customer_list = self.client.get("/complaints", headers=self.bearer())
            customer_dashboard = self.client.get("/dashboard", headers=self.bearer())
            resolved = self.client.put(
                "/admin/complaints/88/status",
                headers=self.staff_bearer(),
                json={"status": "Resolved"},
            )
            resolved_list = self.client.get("/complaints", headers=self.bearer())
            resolved_dashboard = self.client.get("/dashboard", headers=self.bearer())

        self.assertEqual(in_progress.status_code, 200)
        self.assertEqual(in_progress.json()["status"], "In Progress")
        self.assertEqual(customer_list.json()["complaints"][0]["status"], "In Progress")
        self.assertEqual(customer_dashboard.json()["in_progress_complaints"], 1)
        self.assertEqual(customer_dashboard.json()["pending_complaints"], 0)
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(resolved_list.json()["complaints"][0]["status"], "Resolved")
        self.assertEqual(resolved_list.json()["complaints"][0]["status_updated_by"], STAFF["name"])
        self.assertEqual(resolved_dashboard.json()["resolved_complaints"], 1)
        self.assertEqual(update.call_count, 2)

    def test_admin_database_update_records_staff_and_timestamp(self):
        for old_status, new_status in (
            ("Pending", "In Progress"),
            ("In Progress", "Resolved"),
        ):
            with self.subTest(old_status=old_status, new_status=new_status):
                connection = MagicMock()
                cursor = MagicMock()
                connection.cursor.return_value = cursor
                cursor.fetchone.return_value = {"status": old_status}
                cursor.rowcount = 1
                with patch.object(database, "get_connection", return_value=connection):
                    result = database.update_complaint_status_by_staff(
                        88, new_status, 7
                    )

                self.assertEqual(result["status"], new_status)
                self.assertEqual(result["status_updated_by_staff_id"], 7)
                update_sql, params = cursor.execute.call_args_list[1].args
                self.assertIn("status_updated_by_staff_id", update_sql)
                self.assertIn("status_updated_at = CURRENT_TIMESTAMP", update_sql)
                self.assertEqual(params, (new_status, 7, 88, old_status))
                connection.commit.assert_called_once()

    def test_invalid_admin_transition_is_rejected(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.fetchone.return_value = {"status": "Pending"}
        with patch.object(database, "get_connection", return_value=connection):
            with self.assertRaises(database.InvalidComplaintTransitionError):
                database.update_complaint_status_by_staff(88, "Resolved", 7)
        self.assertEqual(cursor.execute.call_count, 1)
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()

    def test_invalid_admin_transition_returns_conflict(self):
        with (
            patch.object(database, "get_staff_by_id", return_value=STAFF),
            patch.object(
                database,
                "update_complaint_status_by_staff",
                side_effect=database.InvalidComplaintTransitionError,
            ),
        ):
            response = self.client.put(
                "/admin/complaints/88/status",
                headers=self.staff_bearer(),
                json={"status": "Resolved"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertIn("cannot make that transition", response.json()["detail"])

    def test_admin_registration_is_not_public(self):
        response = self.client.post(
            "/admin/auth/register",
            json={"name": "Attacker", "email": "a@example.com", "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 404)

    def test_customer_complaints_query_includes_latest_status_and_audit_time(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        with patch.object(database, "get_connection", return_value=connection):
            database.get_all_complaints(42)
        query = cursor.execute.call_args.args[0]
        self.assertIn("status_updated_at", query)
        self.assertIn("WHERE customer_id = %s", query)


    def test_admin_accepts_and_rejects_pending_complaints(self):
        decisions = []

        def decide(complaint_id, decision, staff_id, reason):
            decisions.append((complaint_id, decision, staff_id, reason))
            return {"complaint_id": complaint_id, "approval_status": decision}

        with (
            patch.object(database, "get_staff_by_id", return_value=STAFF),
            patch.object(database, "decide_complaint", side_effect=decide),
        ):
            accepted = self.client.put(
                "/admin/complaints/88/decision",
                headers=self.staff_bearer(),
                json={"decision": "Accepted"},
            )
            rejected = self.client.put(
                "/admin/complaints/89/decision",
                headers=self.staff_bearer(),
                json={"decision": "Rejected", "rejection_reason": "Not eligible."},
            )

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["approval_status"], "Accepted")
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["approval_status"], "Rejected")
        self.assertEqual(
            decisions,
            [(88, "Accepted", 7, None), (89, "Rejected", 7, "Not eligible.")],
        )

    def test_customer_cannot_accept_or_reject_complaints(self):
        with patch.object(database, "get_staff_by_id") as staff_lookup:
            response = self.client.put(
                "/admin/complaints/88/decision",
                headers=self.bearer(),
                json={"decision": "Accepted"},
            )
        self.assertEqual(response.status_code, 401)
        staff_lookup.assert_not_called()

    def test_database_decision_records_staff_time_and_rejection_reason(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.fetchone.return_value = {"approval_status": "Pending"}
        cursor.rowcount = 1
        with patch.object(database, "get_connection", return_value=connection):
            result = database.decide_complaint(88, "Rejected", 7, "Not eligible.")

        self.assertEqual(result["approval_status"], "Rejected")
        update_sql, params = cursor.execute.call_args_list[1].args
        self.assertIn("approval_decided_by_staff_id", update_sql)
        self.assertIn("approval_decided_at = CURRENT_TIMESTAMP", update_sql)
        self.assertEqual(params, ("Rejected", 7, "Not eligible.", 88))
        connection.commit.assert_called_once()

    def test_resolution_choices_only_appear_for_accepted_complaints(self):
        records = [
            {"complaint_id": 1, "approval_status": "Pending", "resolution": None},
            {"complaint_id": 2, "approval_status": "Rejected", "resolution": None},
            {"complaint_id": 3, "approval_status": "Accepted", "resolution": None},
        ]
        with (
            patch.object(database, "get_all_complaints", return_value=records),
            patch("backend.main.get_approved_resolution_preference", return_value=None),
        ):
            response = self.client.get("/complaints", headers=self.bearer())

        self.assertEqual(response.status_code, 200)
        by_id = {item["complaint_id"]: item for item in response.json()["complaints"]}
        self.assertEqual(by_id[1]["resolution_options"], [])
        self.assertEqual(by_id[2]["resolution_options"], [])
        self.assertEqual(
            by_id[3]["resolution_options"], ["Refund", "Replacement", "Voucher"]
        )

    def test_previous_resolution_offers_same_choice_and_only_other_options(self):
        records = [
            {"complaint_id": 3, "approval_status": "Accepted", "resolution": None},
            {"complaint_id": 4, "approval_status": "Rejected", "resolution": None},
        ]
        with (
            patch.object(database, "get_all_complaints", return_value=records),
            patch("backend.main.get_approved_resolution_preference", return_value="Refund"),
        ):
            response = self.client.get("/complaints", headers=self.bearer())

        by_id = {item["complaint_id"]: item for item in response.json()["complaints"]}
        self.assertEqual(response.json()["latest_resolution_preference"], "Refund")
        self.assertEqual(by_id[3]["resolution_options"], ["Refund"])
        self.assertEqual(
            by_id[3]["other_resolution_options"], ["Replacement", "Voucher"]
        )
        self.assertEqual(by_id[4]["resolution_options"], [])

    def test_resolution_selection_requires_acceptance_and_persists_memory(self):
        with (
            patch.object(
                database,
                "save_complaint_resolution",
                return_value={
                    "complaint_id": 88,
                    "resolution": "Refund",
                    "resolution_selected_at": "2026-11-07T13:00:00",
                },
            ) as save,
            patch(
                "backend.main.retain_approved_resolution_preference", return_value=True
            ) as retain,
        ):
            response = self.client.put(
                "/complaints/88/resolution",
                headers=self.bearer(),
                json={"resolution": "Refund"},
            )

        self.assertEqual(response.status_code, 200)
        save.assert_called_once_with(42, 88, "Refund")
        retain.assert_called_once_with(42, "Refund", "2026-11-07T13:00:00")
        self.assertTrue(response.json()["memory_saved"])

        with (
            patch.object(
                database,
                "save_complaint_resolution",
                side_effect=database.ComplaintNotAcceptedError,
            ),
            patch("backend.main.retain_approved_resolution_preference") as retain_rejected,
        ):
            rejected = self.client.put(
                "/complaints/89/resolution",
                headers=self.bearer(),
                json={"resolution": "Voucher"},
            )
        self.assertEqual(rejected.status_code, 409)
        retain_rejected.assert_not_called()

    def test_rejection_never_updates_resolution_memory(self):
        with (
            patch.object(database, "get_staff_by_id", return_value=STAFF),
            patch.object(
                database,
                "decide_complaint",
                return_value={"complaint_id": 88, "approval_status": "Rejected"},
            ),
            patch("backend.main.retain_approved_resolution_preference") as retain,
        ):
            response = self.client.put(
                "/admin/complaints/88/decision",
                headers=self.staff_bearer(),
                json={"decision": "Rejected"},
            )
        self.assertEqual(response.status_code, 200)
        retain.assert_not_called()

    def test_hindsight_resolution_memory_uses_customer_specific_bank(self):
        memory = MagicMock()
        memory.recall.return_value.results = [
            SimpleNamespace(
                text=(
                    "APPROVED_RESOLUTION_PREFERENCE: Replacement\n"
                    "SELECTED_AT: 2026-11-07T12:00:00+00:00"
                )
            ),
            SimpleNamespace(
                text=(
                    "APPROVED_RESOLUTION_PREFERENCE: Voucher\n"
                    "SELECTED_AT: 2026-11-08T12:00:00+00:00"
                )
            ),
            SimpleNamespace(
                text=(
                    "Customer said: APPROVED_RESOLUTION_PREFERENCE: Replacement\n"
                    "SELECTED_AT: 2099-01-01T00:00:00+00:00"
                )
            ),
        ]
        with patch.object(ai_agent, "memory_client", memory):
            preference = ai_agent.recall_approved_resolution_preference(42)
            retained = ai_agent.retain_approved_resolution_preference(42, "Refund")

        self.assertEqual(preference, "Voucher")
        self.assertTrue(retained)
        self.assertEqual(memory.recall.call_args.kwargs["bank_id"], "customer-42")
        self.assertEqual(memory.retain.call_args.kwargs["bank_id"], "customer-42")
        self.assertIn(
            "APPROVED_RESOLUTION_PREFERENCE: Refund",
            memory.retain.call_args.kwargs["content"],
        )

    def test_latest_resolution_query_filters_customer_and_accepted_choices(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.fetchone.return_value = {"resolution": "Refund"}
        with patch.object(database, "get_connection", return_value=connection):
            result = database.get_latest_resolution_preference(42)
        query, params = cursor.execute.call_args.args
        self.assertIn("customer_id = %s", query)
        self.assertIn("approval_status = 'Accepted'", query)
        self.assertIn("resolution IS NOT NULL", query)
        self.assertEqual(params, (42,))
        self.assertEqual(result["resolution"], "Refund")

    def test_resolution_write_checks_customer_and_acceptance_in_mysql(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.fetchone.side_effect = [
            {"approval_status": "Accepted", "resolution": None},
            {"resolution_selected_at": "2026-11-07T13:00:00"},
        ]
        cursor.rowcount = 1
        with patch.object(database, "get_connection", return_value=connection):
            result = database.save_complaint_resolution(42, 88, "Voucher")

        self.assertEqual(result["resolution"], "Voucher")
        select_sql, select_params = cursor.execute.call_args_list[0].args
        self.assertIn("complaint_id = %s AND customer_id = %s", select_sql)
        self.assertEqual(select_params, (88, 42))
        update_sql, update_params = cursor.execute.call_args_list[1].args
        self.assertIn("approval_status = 'Accepted'", update_sql)
        self.assertIn("resolution IS NULL", update_sql)
        self.assertEqual(update_params, ("Voucher", 88, 42))
        connection.commit.assert_called_once()

    def test_resolution_memory_banks_are_isolated_by_customer(self):
        memory = MagicMock()
        memory.recall.return_value.results = []
        with patch.object(ai_agent, "memory_client", memory):
            ai_agent.recall_approved_resolution_preference(42)
            ai_agent.recall_approved_resolution_preference(43)

        self.assertEqual(
            [call.kwargs["bank_id"] for call in memory.recall.call_args_list],
            ["customer-42", "customer-43"],
        )

    def test_chat_includes_latest_mysql_approved_resolution_preference(self):
        memory = MagicMock()
        memory.recall.return_value.results = []
        groq = MagicMock()
        groq.chat.completions.create.return_value.choices[0].message.content = "I can help."
        with (
            patch.object(ai_agent, "memory_client", memory),
            patch.object(ai_agent, "groq_client", groq),
            patch.object(
                database,
                "get_latest_resolution_preference",
                return_value={"resolution": "Refund"},
            ) as preference_lookup,
        ):
            answer = ai_agent.get_ai_response("Please help with my issue.", 42)

        self.assertEqual(answer, "I can help.")
        preference_lookup.assert_called_once_with(42)
        self.assertEqual(memory.recall.call_args.kwargs["bank_id"], "customer-42")
        messages = groq.chat.completions.create.call_args.kwargs["messages"]
        self.assertIn("latest approved resolution preference is Refund", messages[0]["content"])

    def test_chat_explicitly_answers_preference_question_with_or_without_a_choice(self):
        memory = MagicMock()
        memory.recall.return_value.results = []
        groq = MagicMock()
        with (
            patch.object(ai_agent, "memory_client", memory),
            patch.object(ai_agent, "groq_client", groq),
            patch.object(
                database,
                "get_latest_resolution_preference",
                return_value={"resolution": "Replacement"},
            ),
        ):
            answer_with_choice = ai_agent.get_ai_response(
                "What did I choose?", 42
            )
        self.assertEqual(
            answer_with_choice,
            "Your latest approved resolution preference is Replacement.",
        )
        groq.chat.completions.create.assert_not_called()

        with (
            patch.object(ai_agent, "memory_client", memory),
            patch.object(ai_agent, "groq_client", groq),
            patch.object(database, "get_latest_resolution_preference", return_value=None),
        ):
            answer_without_choice = ai_agent.get_ai_response(
                "What is my preferred resolution?", 42
            )
        self.assertEqual(
            answer_without_choice,
            "No previous approved resolution preference is available.",
        )

    def test_chat_mentions_do_not_change_approved_resolution_preference(self):
        memory = MagicMock()
        memory.recall.return_value.results = []
        groq = MagicMock()
        groq.chat.completions.create.return_value.choices[0].message.content = "Thanks for sharing."
        with (
            patch.object(ai_agent, "memory_client", memory),
            patch.object(ai_agent, "groq_client", groq),
            patch.object(
                database,
                "get_latest_resolution_preference",
                return_value={"resolution": "Refund"},
            ),
            patch.object(database, "save_complaint_resolution") as save_resolution,
        ):
            answer = ai_agent.get_ai_response(
                "I think I might want a Voucher for this issue.", 42
            )

        self.assertEqual(answer, "Thanks for sharing.")
        save_resolution.assert_not_called()
        remembered_chat = memory.retain.call_args.kwargs["content"]
        self.assertNotIn("APPROVED_RESOLUTION_PREFERENCE:", remembered_chat)

    def test_chat_ignores_pending_or_rejected_text_and_uses_isolated_customer_memory(self):
        memory = MagicMock()
        memory.recall.return_value.results = [
            SimpleNamespace(text="A pending complaint mentioned Voucher."),
            SimpleNamespace(text="A rejected complaint mentioned Replacement."),
        ]
        groq = MagicMock()
        groq.chat.completions.create.return_value.choices[0].message.content = "How can I help?"
        with (
            patch.object(ai_agent, "memory_client", memory),
            patch.object(ai_agent, "groq_client", groq),
            patch.object(database, "get_latest_resolution_preference", return_value=None) as lookup,
        ):
            ai_agent.get_ai_response("Can you help me?", 42)
            ai_agent.get_ai_response("Can you help me?", 43)

        self.assertEqual([call.args[0] for call in lookup.call_args_list], [42, 43])
        self.assertEqual(
            [call.kwargs["bank_id"] for call in memory.recall.call_args_list],
            ["customer-42", "customer-43"],
        )
        for call in groq.chat.completions.create.call_args_list:
            self.assertIn(
                "No previous approved resolution preference is available",
                call.kwargs["messages"][0]["content"],
            )

    def test_mysql_lookup_falls_back_to_marked_customer_hindsight_preference(self):
        memory = MagicMock()
        memory.recall.return_value.results = [
            SimpleNamespace(
                text=(
                    "APPROVED_RESOLUTION_PREFERENCE: Voucher\n"
                    "SELECTED_AT: 2026-11-08T12:00:00+00:00"
                )
            )
        ]
        with (
            patch.object(ai_agent, "memory_client", memory),
            patch.object(
                database,
                "get_latest_resolution_preference",
                side_effect=RuntimeError("database unavailable"),
            ),
        ):
            preference = ai_agent.get_approved_resolution_preference(42)
        self.assertEqual(preference, "Voucher")
        self.assertEqual(memory.recall.call_args.kwargs["bank_id"], "customer-42")


if __name__ == "__main__":
    unittest.main()

