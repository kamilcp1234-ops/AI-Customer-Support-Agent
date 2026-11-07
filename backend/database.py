
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()


class DuplicateCustomerEmailError(ValueError):
    pass


class DuplicateStaffEmailError(ValueError):
    pass


class ComplaintNotFoundError(LookupError):
    pass


class InvalidComplaintTransitionError(ValueError):
    pass


class InvalidComplaintApprovalError(ValueError):
    pass


class ComplaintNotAcceptedError(ValueError):
    pass


class ResolutionAlreadySelectedError(ValueError):
    pass


# Connect to MySQL
def get_connection():

    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE")
    )


def _close_db_resources(cursor, connection):
    """Close the cursor and connection, even if cursor.close() fails."""
    try:
        if cursor is not None:
            cursor.close()
    finally:
        connection.close()


# Register a customer or find an existing customer
def get_or_create_customer(name, email=None):

    if email is None or not email.strip():
        raise ValueError("Email is required to identify a customer.")

    email = email.strip().lower()

    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT customer_id FROM customers WHERE email = %s",
            (email,)
        )

        customer = cursor.fetchone()
        if customer:
            return customer[0]

        try:
            cursor.execute(
                "INSERT INTO customers (name, email) VALUES (%s, %s)",
                (name, email)
            )
            connection.commit()
            return cursor.lastrowid
        except mysql.connector.IntegrityError:
            # Another request may have inserted this email after our lookup.
            connection.rollback()
            cursor.execute(
                "SELECT customer_id FROM customers WHERE email = %s",
                (email,)
            )
            customer = cursor.fetchone()
            if not customer:
                raise
            return customer[0]
    finally:
        _close_db_resources(cursor, connection)


def get_customer_auth_by_email(email):
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT customer_id, name, email, password_hash
            FROM customers
            WHERE email = %s
            """,
            (email.strip().lower(),)
        )
        return cursor.fetchone()
    finally:
        _close_db_resources(cursor, connection)


def get_customer_by_id(customer_id):
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT customer_id, name, email FROM customers WHERE customer_id = %s",
            (customer_id,)
        )
        return cursor.fetchone()
    finally:
        _close_db_resources(cursor, connection)


def get_staff_auth_by_email(email):
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT staff_id, name, email, password_hash, role, is_active
            FROM staff_accounts
            WHERE email = %s
            """,
            (email.strip().lower(),)
        )
        return cursor.fetchone()
    finally:
        _close_db_resources(cursor, connection)


def get_staff_by_id(staff_id):
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT staff_id, name, email, role, is_active
            FROM staff_accounts
            WHERE staff_id = %s
            """,
            (staff_id,)
        )
        return cursor.fetchone()
    finally:
        _close_db_resources(cursor, connection)


def create_staff_account(name, email, password_hash, role):
    if role not in {"admin", "support"}:
        raise ValueError("Staff role must be admin or support.")

    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO staff_accounts (name, email, password_hash, role)
                VALUES (%s, %s, %s, %s)
                """,
                (name.strip(), email.strip().lower(), password_hash, role)
            )
            connection.commit()
        except mysql.connector.IntegrityError:
            connection.rollback()
            raise DuplicateStaffEmailError from None
        return cursor.lastrowid
    finally:
        _close_db_resources(cursor, connection)


def register_customer_account(name, email, password_hash):
    """Create a new account without attaching credentials to legacy records.

    Email ownership is not verified by this application, so an existing row
    cannot safely be claimed during self-service registration.
    """
    normalized_email = email.strip().lower()
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT customer_id, name, email, password_hash
            FROM customers
            WHERE email = %s
            """,
            (normalized_email,)
        )
        existing = cursor.fetchone()

        if existing:
            raise DuplicateCustomerEmailError

        try:
            cursor.execute(
                """
                INSERT INTO customers (name, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (name.strip(), normalized_email, password_hash)
            )
            connection.commit()
        except mysql.connector.IntegrityError:
            connection.rollback()
            cursor.execute(
                """
                SELECT password_hash
                FROM customers
                WHERE email = %s
                """,
                (normalized_email,)
            )
            if cursor.fetchone():
                raise DuplicateCustomerEmailError
            raise

        return {
            "customer_id": cursor.lastrowid,
            "name": name.strip(),
            "email": normalized_email,
        }
    finally:
        _close_db_resources(cursor, connection)


# Save customer message and AI response
def save_chat_history(customer_id, message, response):

    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        query = """
            INSERT INTO chat_history
            (customer_id, message, response)
            VALUES (%s, %s, %s)
        """
        cursor.execute(query, (customer_id, message, response))
        connection.commit()
    finally:
        _close_db_resources(cursor, connection)


# Test the functions
if __name__ == "__main__":

    customer_id = get_or_create_customer("Rahul", "rahul@example.com")

    print("Customer registered successfully!")
    print("Customer ID:", customer_id)


def save_complaint(customer_id, subject, description):

    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        query = """
            INSERT INTO complaints
            (customer_id, subject, description, status, approval_status)
            VALUES (%s, %s, %s, 'Pending', 'Pending')
        """
        cursor.execute(
            query,
            (customer_id, subject, description)
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        _close_db_resources(cursor, connection)
# Get all complaints
def get_all_complaints(customer_id):

    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT
                complaint_id,
                customer_id,
                subject,
                description,
                status,
                created_at,
                status_updated_at,
                approval_status,
                approval_decided_at,
                rejection_reason,
                resolution,
                resolution_selected_at
            FROM complaints
            WHERE customer_id = %s
            ORDER BY created_at DESC
        """
        cursor.execute(query, (customer_id,))
        return cursor.fetchall()
    finally:
        _close_db_resources(cursor, connection)
# Get dashboard statistics
def get_dashboard_stats(customer_id):

    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT
                (SELECT COUNT(*) FROM complaints
                 WHERE customer_id = %s) AS total_complaints,
                (SELECT COUNT(*) FROM complaints
                 WHERE customer_id = %s
                   AND status IN ('Pending', 'Open')) AS pending_complaints,
                (SELECT COUNT(*) FROM complaints
                 WHERE customer_id = %s AND status = 'In Progress') AS in_progress_complaints,
                (SELECT COUNT(*) FROM complaints
                 WHERE customer_id = %s AND status = 'Resolved') AS resolved_complaints
        """
        cursor.execute(query, (customer_id, customer_id, customer_id, customer_id))
        return cursor.fetchone()
    finally:
        _close_db_resources(cursor, connection)


def get_admin_dashboard_stats():
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM customers) AS total_customers,
                (SELECT COUNT(*) FROM complaints) AS total_complaints,
                (SELECT COUNT(*) FROM complaints
                 WHERE status IN ('Pending', 'Open')) AS pending_complaints,
                (SELECT COUNT(*) FROM complaints
                 WHERE status = 'In Progress') AS in_progress_complaints,
                (SELECT COUNT(*) FROM complaints
                 WHERE status = 'Resolved') AS resolved_complaints
            """
        )
        return cursor.fetchone()
    finally:
        _close_db_resources(cursor, connection)


def get_all_complaints_for_staff():
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                c.complaint_id,
                c.customer_id,
                customer.name AS customer_name,
                customer.email AS customer_email,
                c.subject,
                c.description,
                c.status,
                c.created_at,
                c.status_updated_at,
                c.approval_status,
                c.approval_decided_at,
                c.rejection_reason,
                c.resolution,
                c.resolution_selected_at,
                approval_staff.name AS approval_decided_by,
                staff.name AS status_updated_by
            FROM complaints AS c
            JOIN customers AS customer ON customer.customer_id = c.customer_id
            LEFT JOIN staff_accounts AS staff
                ON staff.staff_id = c.status_updated_by_staff_id
            LEFT JOIN staff_accounts AS approval_staff
                ON approval_staff.staff_id = c.approval_decided_by_staff_id
            ORDER BY c.created_at DESC
            """
        )
        return cursor.fetchall()
    finally:
        _close_db_resources(cursor, connection)


def decide_complaint(complaint_id, decision, staff_id, rejection_reason=None):
    if decision not in {"Accepted", "Rejected"}:
        raise ValueError("Invalid complaint decision.")

    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT approval_status FROM complaints WHERE complaint_id = %s FOR UPDATE",
            (complaint_id,),
        )
        complaint = cursor.fetchone()
        if complaint is None:
            connection.rollback()
            raise ComplaintNotFoundError("Complaint not found.")
        if complaint["approval_status"] != "Pending":
            connection.rollback()
            raise InvalidComplaintApprovalError("Complaint is no longer pending review.")

        cursor.execute(
            """
            UPDATE complaints
            SET approval_status = %s,
                approval_decided_by_staff_id = %s,
                approval_decided_at = CURRENT_TIMESTAMP,
                rejection_reason = %s
            WHERE complaint_id = %s AND approval_status = 'Pending'
            """,
            (
                decision,
                staff_id,
                rejection_reason.strip() if decision == "Rejected" and rejection_reason else None,
                complaint_id,
            ),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            raise InvalidComplaintApprovalError("Complaint decision changed concurrently.")
        connection.commit()
        return {"complaint_id": complaint_id, "approval_status": decision}
    finally:
        _close_db_resources(cursor, connection)


def get_latest_resolution_preference(customer_id):
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT resolution, resolution_selected_at
            FROM complaints
            WHERE customer_id = %s
              AND approval_status = 'Accepted'
              AND resolution IS NOT NULL
            ORDER BY resolution_selected_at DESC, complaint_id DESC
            LIMIT 1
            """,
            (customer_id,),
        )
        return cursor.fetchone()
    finally:
        _close_db_resources(cursor, connection)


def save_complaint_resolution(customer_id, complaint_id, resolution):
    if resolution not in {"Refund", "Replacement", "Voucher"}:
        raise ValueError("Invalid resolution option.")

    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT approval_status, resolution
            FROM complaints
            WHERE complaint_id = %s AND customer_id = %s
            FOR UPDATE
            """,
            (complaint_id, customer_id),
        )
        complaint = cursor.fetchone()
        if complaint is None:
            connection.rollback()
            raise ComplaintNotFoundError("Complaint not found.")
        if complaint["approval_status"] != "Accepted":
            connection.rollback()
            raise ComplaintNotAcceptedError("Complaint has not been accepted.")
        if complaint["resolution"] is not None:
            connection.rollback()
            raise ResolutionAlreadySelectedError("A resolution was already selected.")

        cursor.execute(
            """
            UPDATE complaints
            SET resolution = %s, resolution_selected_at = CURRENT_TIMESTAMP
            WHERE complaint_id = %s AND customer_id = %s
              AND approval_status = 'Accepted' AND resolution IS NULL
            """,
            (resolution, complaint_id, customer_id),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            raise ResolutionAlreadySelectedError("Resolution changed concurrently.")
        connection.commit()
        cursor.execute(
            "SELECT resolution_selected_at FROM complaints WHERE complaint_id = %s",
            (complaint_id,),
        )
        selected = cursor.fetchone() or {}
        return {
            "complaint_id": complaint_id,
            "resolution": resolution,
            "resolution_selected_at": selected.get("resolution_selected_at"),
        }
    finally:
        _close_db_resources(cursor, connection)


def update_complaint_status_by_staff(complaint_id, new_status, staff_id):
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT status, approval_status FROM complaints WHERE complaint_id = %s FOR UPDATE",
            (complaint_id,)
        )
        complaint = cursor.fetchone()
        if complaint is None:
            connection.rollback()
            raise ComplaintNotFoundError("Complaint not found.")

        current_status = complaint["status"]
        if complaint.get("approval_status", "Accepted") != "Accepted":
            connection.rollback()
            raise InvalidComplaintTransitionError("Complaint must be accepted before status updates.")
        valid_transition = (
            current_status in {"Pending", "Open"} and new_status == "In Progress"
        ) or (current_status == "In Progress" and new_status == "Resolved")
        if not valid_transition:
            connection.rollback()
            raise InvalidComplaintTransitionError("Invalid complaint status transition.")

        cursor.execute(
            """
            UPDATE complaints
            SET status = %s,
                status_updated_by_staff_id = %s,
                status_updated_at = CURRENT_TIMESTAMP
            WHERE complaint_id = %s AND status = %s
            """,
            (new_status, staff_id, complaint_id, current_status)
        )
        if cursor.rowcount != 1:
            connection.rollback()
            raise InvalidComplaintTransitionError("Complaint status changed concurrently.")
        connection.commit()
        return {
            "complaint_id": complaint_id,
            "status": new_status,
            "status_updated_by_staff_id": staff_id,
        }
    finally:
        _close_db_resources(cursor, connection)

