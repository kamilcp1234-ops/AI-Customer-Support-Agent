import os
from html import escape
from urllib.parse import urlsplit

import pandas as pd
import requests
import streamlit as st


API_BASE_URL = os.getenv("SUPPORT_API_URL", "http://127.0.0.1:8000")
REQUEST_TIMEOUT = 30

st.set_page_config(
    page_title="SupportAI Admin",
    page_icon="A",
    layout="wide",
    initial_sidebar_state="expanded",
)


def admin_headers():
    token = st.session_state.get("admin_access_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def clear_admin_session():
    for key in ("admin_access_token", "admin_name", "admin_email", "admin_role"):
        st.session_state.pop(key, None)
    st.session_state.admin_page = "dashboard"


def check_response(response):
    if response.status_code == 401 and st.session_state.get("admin_access_token"):
        clear_admin_session()
        st.session_state.admin_message = "Your staff session expired. Please log in again."
        st.rerun()
    response.raise_for_status()


def api_get(path):
    response = requests.get(
        f"{API_BASE_URL}{path}",
        headers=admin_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    check_response(response)
    return response.json()


def api_put(path, payload):
    response = requests.put(
        f"{API_BASE_URL}{path}",
        json=payload,
        headers=admin_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    check_response(response)
    return response.json()


def show_request_error(action, error):
    detail = ""
    if isinstance(error, requests.HTTPError) and error.response is not None:
        try:
            detail = error.response.json().get("detail", "")
        except ValueError:
            detail = ""
    message = f"Could not {action}."
    if detail:
        message = f"{message} {detail}"
    st.error(message)


def render_login():
    current_url = urlsplit(st.context.url)
    hostname = current_url.hostname or "localhost"
    if ":" in hostname:
        hostname = f"[{hostname}]"
    customer_login_url = escape(
        f"{current_url.scheme or 'http'}://{hostname}:8501", quote=True
    )

    st.markdown(
        """
        <style>
            .admin-login-title { margin: 0 0 0.25rem; color: #14233b; font-size: 2rem; font-weight: 750; }
            .admin-login-subtitle { margin: 0 0 1.25rem; color: #64748b; }
            .admin-illustration { min-height: 390px; display: flex; flex-direction: column; justify-content: center; padding: 1.7rem; border-radius: 20px; background: linear-gradient(145deg, #101a2c, #203c64); color: white; }
            .admin-illustration h2 { margin: 1rem 0 0.4rem; color: white; font-size: 1.65rem; }
            .admin-illustration p { max-width: 28rem; color: #d7e2f2; }
            .admin-back-link { display: inline-block; margin-top: 1rem; color: #315fbb !important; font-size: 0.9rem; font-weight: 600; text-decoration: none !important; }
            .admin-back-link:hover { color: #1d4ed8 !important; text-decoration: underline !important; }
            @media (max-width: 760px) { .admin-illustration { min-height: 250px; } }
        </style>
        """,
        unsafe_allow_html=True,
    )

    illustration_col, form_col = st.columns(
        [1.1, 0.9], gap="large", vertical_alignment="center"
    )
    with illustration_col:
        with st.container(border=True):
            st.markdown(
                """
                <div class="admin-illustration">
                    <svg viewBox="0 0 440 250" role="img" aria-label="Support team managing customer requests" style="width:100%;height:auto;max-height:245px">
                        <defs>
                            <linearGradient id="admin-panel" x1="0" x2="1" y1="0" y2="1">
                                <stop offset="0" stop-color="#ffffff" stop-opacity=".22"/>
                                <stop offset="1" stop-color="#ffffff" stop-opacity=".08"/>
                            </linearGradient>
                        </defs>
                        <rect x="52" y="20" width="336" height="205" rx="22" fill="url(#admin-panel)" stroke="#ffffff" stroke-opacity=".28"/>
                        <rect x="82" y="50" width="135" height="145" rx="12" fill="#ffffff" fill-opacity=".94"/>
                        <rect x="98" y="68" width="103" height="12" rx="6" fill="#dce6f5"/>
                        <rect x="98" y="94" width="79" height="9" rx="4.5" fill="#dce6f5"/>
                        <rect x="98" y="118" width="103" height="31" rx="8" fill="#eaf1ff"/>
                        <circle cx="111" cy="133" r="6" fill="#3b82f6"/>
                        <rect x="123" y="128" width="64" height="9" rx="4.5" fill="#9db6de"/>
                        <rect x="98" y="158" width="103" height="23" rx="7" fill="#edf8f2"/>
                        <circle cx="111" cy="169.5" r="5" fill="#22a06b"/>
                        <rect x="123" y="165" width="55" height="8" rx="4" fill="#9dcab4"/>
                        <circle cx="287" cy="88" r="34" fill="#f6c9a4"/>
                        <path d="M253 83c2-25 18-39 37-39 24 0 38 18 36 42-10-5-18-15-21-22-11 15-29 22-52 19Z" fill="#172b49"/>
                        <path d="M232 205c2-43 23-70 55-70s55 27 57 70" fill="#78a8f4"/>
                        <path d="M263 143l24 25 25-25" fill="#ffffff" fill-opacity=".9"/>
                        <path d="M287 168v36" stroke="#477bc7" stroke-width="5"/>
                        <circle cx="350" cy="54" r="19" fill="#f5c85b"/>
                        <path d="M344 54l5 5 9-11" fill="none" stroke="#243b5c" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <h2>Support that stays in sync</h2>
                    <p>Review customer requests, track progress, and keep every update connected to the same support record.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with form_col:
        with st.container(border=True):
            st.markdown(
                '<div class="admin-login-title">SupportAI</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="admin-login-subtitle">Admin Portal · Staff sign in</div>',
                unsafe_allow_html=True,
            )
            st.markdown("### Welcome back")
            st.caption("Sign in with a provisioned Admin or Support account.")
            if st.session_state.get("admin_message"):
                st.info(st.session_state.admin_message)

            with st.form("staff_login", clear_on_submit=True):
                email = st.text_input("Email", placeholder="staff@example.com")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button(
                    "Admin Login", type="primary", use_container_width=True
                )
            st.markdown(
                f'<a class="admin-back-link" href="{customer_login_url}">← Back to Customer Login</a>',
                unsafe_allow_html=True,
            )

    if submitted:
        try:
            response = requests.post(
                f"{API_BASE_URL}/admin/auth/login",
                json={"email": email, "password": password},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            result = response.json()
            staff = result["staff"]
            st.session_state.admin_access_token = result["access_token"]
            st.session_state.admin_name = staff["name"]
            st.session_state.admin_email = staff["email"]
            st.session_state.admin_role = staff["role"]
            st.session_state.admin_page = "dashboard"
            st.session_state.pop("admin_message", None)
            st.rerun()
        except requests.RequestException as error:
            show_request_error("sign in", error)
        except (KeyError, ValueError):
            st.error("The support service returned an unexpected response.")


def render_sidebar():
    with st.sidebar:
        st.markdown("## SupportAI Admin")
        st.caption(f"{st.session_state.admin_name} · {st.session_state.admin_role.title()}")
        st.divider()
        for label, page in (("Dashboard", "dashboard"), ("Complaints", "complaints")):
            if st.button(
                label,
                key=f"admin_nav_{page}",
                type="primary" if st.session_state.admin_page == page else "secondary",
                use_container_width=True,
            ):
                st.session_state.admin_page = page
                st.rerun()
        st.divider()
        if st.button("Logout", key="admin_logout", use_container_width=True):
            clear_admin_session()
            st.rerun()


def load_admin_data():
    try:
        return api_get("/admin/dashboard"), api_get("/admin/complaints")
    except requests.RequestException as error:
        show_request_error("load admin data", error)
        return None, None


def render_dashboard():
    st.title("Admin Dashboard")
    st.caption("Support activity across all customer accounts.")
    stats, complaint_result = load_admin_data()
    if stats is None:
        return

    metrics = st.columns(5)
    metrics[0].metric("Total Customers", stats["total_customers"])
    metrics[1].metric("Total Complaints", stats["total_complaints"])
    metrics[2].metric("Pending", stats["pending_complaints"])
    metrics[3].metric("In Progress", stats["in_progress_complaints"])
    metrics[4].metric("Resolved", stats["resolved_complaints"])

    complaints = complaint_result.get("complaints", []) if complaint_result else []
    st.subheader("Recent Complaints")
    if complaints:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": item["complaint_id"],
                        "Customer": item["customer_name"],
                        "Subject": item["subject"],
                        "Status": item["status"],
                        "Created": item["created_at"],
                    }
                    for item in complaints[:8]
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No complaints have been registered yet.")

    st.subheader("Complaint Statistics")
    chart_data = pd.DataFrame(
        [
            {"Status": "Pending", "Count": stats["pending_complaints"]},
            {"Status": "In Progress", "Count": stats["in_progress_complaints"]},
            {"Status": "Resolved", "Count": stats["resolved_complaints"]},
        ]
    )
    st.bar_chart(chart_data, x="Status", y="Count", horizontal=True, height=300)


def render_complaints():
    st.title("Complaint Queue")
    st.caption("Review customer details and advance complaint statuses.")
    try:
        result = api_get("/admin/complaints")
    except requests.RequestException as error:
        show_request_error("load complaints", error)
        return

    complaints = result.get("complaints", [])
    st.caption(f"{result.get('total_complaints', len(complaints))} complaints")
    if not complaints:
        st.info("No complaints have been registered yet.")
        return

    pending_complaints = [
        complaint
        for complaint in complaints
        if complaint.get("approval_status", "Accepted") == "Pending"
    ]
    st.subheader("Pending Complaints")
    if not pending_complaints:
        st.info("No complaints are awaiting review.")
    for complaint in pending_complaints:
        complaint_id = complaint["complaint_id"]
        with st.container(border=True):
            st.markdown(f"### Complaint #{complaint_id} · {complaint['subject']}")
            st.caption(f"Approval status: {complaint['approval_status']}")
            customer_col, details_col = st.columns([1, 2])
            with customer_col:
                st.markdown("**Customer**")
                st.write(complaint["customer_name"])
                st.caption(complaint["customer_email"])
            with details_col:
                st.markdown("**Description**")
                st.write(complaint["description"])
            st.caption(f"Submitted {complaint['created_at']}")
            rejection_reason = st.text_area(
                "Rejection reason (optional)",
                key=f"rejection_reason_{complaint_id}",
                max_chars=2000,
            )
            accept_col, reject_col = st.columns(2)
            with accept_col:
                if st.button(
                    "Accept",
                    key=f"accept_complaint_{complaint_id}",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        api_put(
                            f"/admin/complaints/{complaint_id}/decision",
                            {"decision": "Accepted"},
                        )
                        st.success(f"Complaint #{complaint_id} accepted.")
                        st.rerun()
                    except requests.RequestException as error:
                        show_request_error("accept the complaint", error)
            with reject_col:
                if st.button(
                    "Reject",
                    key=f"reject_complaint_{complaint_id}",
                    use_container_width=True,
                ):
                    try:
                        api_put(
                            f"/admin/complaints/{complaint_id}/decision",
                            {
                                "decision": "Rejected",
                                "rejection_reason": rejection_reason.strip() or None,
                            },
                        )
                        st.success(f"Complaint #{complaint_id} rejected.")
                        st.rerun()
                    except requests.RequestException as error:
                        show_request_error("reject the complaint", error)

    processed_complaints = [
        complaint
        for complaint in complaints
        if complaint.get("approval_status", "Accepted") != "Pending"
    ]
    st.subheader("Reviewed Complaints")
    if not processed_complaints:
        st.info("No complaints have been reviewed yet.")

    for complaint in processed_complaints:
        complaint_id = complaint["complaint_id"]
        current_status = complaint["status"]
        approval_status = complaint.get("approval_status", "Accepted")
        with st.expander(
            f"#{complaint_id} · {complaint['subject']} · {current_status}"
        ):
            customer_col, complaint_col, action_col = st.columns([1, 2, 1])
            with customer_col:
                st.markdown("**Customer**")
                st.write(complaint["customer_name"])
                st.caption(complaint["customer_email"])
                st.caption(f"Customer ID: {complaint['customer_id']}")
            with complaint_col:
                st.markdown("**Description**")
                st.write(complaint["description"])
                st.caption(f"Created {complaint['created_at']}")
                st.caption(f"Approval status: {approval_status}")
                if approval_status == "Rejected" and complaint.get("rejection_reason"):
                    st.caption(f"Rejection reason: {complaint['rejection_reason']}")
                if complaint.get("approval_decided_at"):
                    reviewer = complaint.get("approval_decided_by") or "Staff account"
                    st.caption(
                        f"Decision by {reviewer} at {complaint['approval_decided_at']}"
                    )
                if complaint.get("status_updated_at"):
                    updater = complaint.get("status_updated_by") or "Staff account"
                    st.caption(
                        f"Last updated by {updater} at {complaint['status_updated_at']}"
                    )
            with action_col:
                st.markdown(f"**Current status:** {current_status}")
                if approval_status != "Accepted":
                    st.caption("Resolution options are unavailable for rejected complaints.")
                    continue
                next_status = {
                    "Pending": "In Progress",
                    "Open": "In Progress",
                    "In Progress": "Resolved",
                }.get(current_status)
                if next_status:
                    if st.button(
                        f"Mark {next_status}",
                        key=f"admin_update_{complaint_id}",
                        use_container_width=True,
                    ):
                        try:
                            api_put(
                                f"/admin/complaints/{complaint_id}/status",
                                {"status": next_status},
                            )
                            st.success("Complaint status updated.")
                            st.rerun()
                        except requests.RequestException as error:
                            show_request_error("update complaint status", error)
                else:
                    st.caption("This complaint is resolved.")


st.session_state.setdefault("admin_page", "dashboard")
if not st.session_state.get("admin_access_token"):
    render_login()
else:
    try:
        staff = api_get("/admin/auth/me")
    except requests.RequestException as error:
        show_request_error("validate staff session", error)
        st.stop()

    st.session_state.admin_name = staff["name"]
    st.session_state.admin_email = staff["email"]
    st.session_state.admin_role = staff["role"]
    render_sidebar()
    if st.session_state.admin_page == "complaints":
        render_complaints()
    else:
        render_dashboard()
