import os

from html import escape
from urllib.parse import urlsplit

import pandas as pd
import requests
import streamlit as st


API_BASE_URL = os.getenv("SUPPORT_API_URL", "http://127.0.0.1:8000")
PAGES = [
    ("AI Chat", "chat"),
    ("Dashboard", "dashboard"),
    ("Register Complaint", "register"),
    ("Complaints", "complaints"),
    ("Customer Profile", "profile"),
]

st.set_page_config(
    page_title="SupportAI",
    page_icon="S",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --navy: #101a2c;
        --navy-soft: #1a2940;
        --ink: #182230;
        --muted: #657184;
        --line: #e6eaf0;
        --surface: #ffffff;
        --canvas: #f7f9fc;
        --accent: #2563eb;
    }
    .stApp {
        background: var(--canvas);
        color: var(--ink);
    }
    [data-testid="stHeader"] {
        background: rgba(247, 249, 252, 0.92);
    }
    [data-testid="stSidebar"] {
        background: var(--navy);
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }
    [data-testid="stSidebar"][aria-expanded="true"] {
        min-width: 250px;
        max-width: 250px;
    }
    [data-testid="stSidebar"] > div:first-child {
        background: var(--navy);
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span {
        color: #e7edf7;
    }
    [data-testid="stSidebar"] [data-testid="stButton"] button {
        width: 100%;
        justify-content: flex-start;
        border: 1px solid transparent;
        border-radius: 10px;
        color: #e7edf7;
        background: transparent;
        min-height: 2.7rem;
        text-align: left;
    }
    [data-testid="stSidebar"] [data-testid="stButton"] button:hover {
        background: var(--navy-soft);
        border-color: rgba(255, 255, 255, 0.08);
        color: #ffffff;
    }
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] {
        background: #243752;
        color: #ffffff;
    }
    .brand {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        padding: 0.55rem 0 1.1rem;
        color: #ffffff;
        font-size: 1.2rem;
        font-weight: 700;
        letter-spacing: -0.02em;
    }
    .brand-mark {
        display: grid;
        place-items: center;
        width: 2rem;
        height: 2rem;
        border-radius: 9px;
        background: #2563eb;
        color: white;
        font-size: 1rem;
    }
    .sidebar-caption {
        color: #97a8c1 !important;
        font-size: 0.76rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin: 0.7rem 0 0.35rem;
    }
    .main .block-container {
        max-width: 1440px;
        padding-top: 2rem;
        padding-bottom: 7rem;
    }
    .page-heading {
        margin-bottom: 0.15rem;
        color: var(--ink);
        font-size: 1.9rem;
        font-weight: 700;
        letter-spacing: -0.04em;
    }
    .page-subheading {
        color: var(--muted);
        margin-bottom: 1.5rem;
    }
    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 1rem 1.1rem;
        box-shadow: 0 2px 8px rgba(20, 35, 60, 0.035);
    }
    [data-testid="stChatMessage"] {
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 0.8rem 1rem;
        margin: 0.75rem auto;
        max-width: 920px;
        background: var(--surface);
    }
    [data-testid="stChatInput"] {
        max-width: 920px;
        margin-left: auto;
        margin-right: auto;
    }
    .chat-intro {
        max-width: 820px;
        margin: 12vh auto 2rem;
        text-align: center;
    }
    .chat-intro h1 {
        color: var(--ink);
        font-size: clamp(2rem, 4vw, 3rem);
        letter-spacing: -0.05em;
    }
    .chat-intro p {
        color: var(--muted);
        font-size: 1.05rem;
    }
    .section-card {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 1.2rem;
    }
    @media (max-width: 720px) {
        .main .block-container {
            padding: 1rem 0.8rem 6rem;
        }
        .chat-intro {
            margin-top: 7vh;
        }
        [data-testid="stChatMessage"] {
            padding: 0.65rem 0.8rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def auth_headers():
    token = st.session_state.get("access_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def check_response(response):
    if response.status_code == 401 and st.session_state.get("access_token"):
        clear_session()
        st.session_state.auth_message = "Your session expired. Please log in again."
        st.rerun()
    response.raise_for_status()


def api_get(path: str, timeout: int = 30):
    response = requests.get(
        f"{API_BASE_URL}{path}",
        headers=auth_headers(),
        timeout=timeout,
    )
    check_response(response)
    return response.json()


def api_post(path: str, payload: dict, timeout: int = 30, authenticated=True):
    response = requests.post(
        f"{API_BASE_URL}{path}",
        json=payload,
        headers=auth_headers() if authenticated else {},
        timeout=timeout,
    )
    check_response(response)
    return response.json()


def api_put(path: str, payload: dict, timeout: int = 30):
    response = requests.put(
        f"{API_BASE_URL}{path}",
        json=payload,
        headers=auth_headers(),
        timeout=timeout,
    )
    check_response(response)
    return response.json()


def show_request_error(action: str, error: requests.RequestException):
    detail = ""
    if isinstance(error, requests.HTTPError) and error.response is not None:
        try:
            body = error.response.json()
            detail = body.get("detail") or body.get("error") or ""
            if isinstance(detail, list):
                detail = " ".join(str(item) for item in detail)
        except ValueError:
            detail = ""
    message = f"Could not {action}."
    if detail:
        message = f"{message} {detail}"
    st.error(message)


def go_to_page(page: str):
    st.session_state.current_page = page
    st.rerun()


def clear_session():
    for key in (
        "access_token",
        "profile_name",
        "profile_email",
        "profile_name_input",
        "profile_email_input",
    ):
        st.session_state.pop(key, None)
    st.session_state.messages = []
    st.session_state.current_page = "chat"


def start_session(result: dict):
    customer = result["customer"]
    st.session_state.access_token = result["access_token"]
    st.session_state.profile_name = customer["name"]
    st.session_state.profile_email = customer["email"]
    st.session_state.profile_name_input = customer["name"]
    st.session_state.profile_email_input = customer["email"]
    st.session_state.messages = []
    st.session_state.current_page = "chat"
    st.session_state.pop("auth_message", None)
    st.rerun()


def render_auth_page():
    st.markdown(
        """
        <div class="chat-intro" style="margin-top: 8vh">
            <h1>Welcome to SupportAI</h1>
            <p>Sign in or create an account to continue to your support chat.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.session_state.get("auth_message"):
        st.info(st.session_state.auth_message)

    auth_view = st.session_state.get("auth_view", "login")
    if auth_view == "login":
        with st.form("login_form", clear_on_submit=True):
            email = st.text_input("Login email", placeholder="you@example.com")
            password = st.text_input("Login password", type="password")
            submitted = st.form_submit_button(
                "Login", type="primary", use_container_width=True
            )
        if submitted:
            try:
                result = api_post(
                    "/auth/login",
                    {"email": email, "password": password},
                    authenticated=False,
                )
                start_session(result)
            except requests.RequestException as error:
                detail = ""
                if isinstance(error, requests.HTTPError) and error.response is not None:
                    try:
                        detail = error.response.json().get("detail", "")
                    except ValueError:
                        pass
                if detail in {
                    "Account not found. Please register first.",
                    "Incorrect password. Please try again.",
                }:
                    st.error(detail)
                else:
                    show_request_error("log in", error)
        if st.button("Register", key="go_to_register"):
            st.session_state.auth_view = "register"
            st.rerun()
        current_url = urlsplit(st.context.url)
        hostname = current_url.hostname or "localhost"
        if ":" in hostname:
            hostname = f"[{hostname}]"
        admin_portal_url = escape(
            f"{current_url.scheme or 'http'}://{hostname}:8502", quote=True
        )
        st.markdown(
            f"""
            <style>
                .supportai-admin-portal {{
                    position: fixed;
                    right: 1.5rem;
                    bottom: 1rem;
                    z-index: 1000;
                    padding: 0.55rem 0.85rem;
                    border: 1px solid #dce3ed;
                    border-radius: 999px;
                    background: rgba(255, 255, 255, 0.94);
                    color: #53647a !important;
                    font-size: 0.82rem;
                    font-weight: 600;
                    text-decoration: none !important;
                    box-shadow: 0 4px 16px rgba(16, 26, 44, 0.08);
                }}
                .supportai-admin-portal:hover {{
                    color: #1d4ed8 !important;
                    border-color: #b9cdf7;
                }}
            </style>
            <a class="supportai-admin-portal" href="{admin_portal_url}" target="_blank" rel="noopener noreferrer">
                Admin Portal&nbsp; ↗
            </a>
            """,
            unsafe_allow_html=True,
        )
    else:
        if st.button("Back to Login", key="back_to_login"):
            st.session_state.auth_view = "login"
            st.rerun()

        with st.form("register_form", clear_on_submit=True):
            name = st.text_input("Full name")
            email = st.text_input("Registration email", placeholder="you@example.com")
            password = st.text_input("Create password", type="password")
            confirm_password = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button(
                "Create account", type="primary", use_container_width=True
            )
        if submitted:
            if len(password) < 8:
                st.error("Password must be at least 8 characters.")
            elif password != confirm_password:
                st.error("Passwords do not match.")
            else:
                try:
                    api_post(
                        "/auth/register",
                        {
                            "name": name,
                            "email": email,
                            "password": password,
                            "confirm_password": confirm_password,
                        },
                        authenticated=False,
                    )
                    st.session_state.auth_view = "login"
                    st.session_state.auth_message = "Registration successful! Please log in."
                    st.rerun()
                except requests.RequestException as error:
                    show_request_error("register", error)


def render_sidebar():
    with st.sidebar:
        st.markdown(
            '<div class="brand"><span class="brand-mark">S</span>SupportAI</div>',
            unsafe_allow_html=True,
        )
        if st.button("＋  New Chat", use_container_width=True, type="primary"):
            st.session_state.messages = []
            st.session_state.current_page = "chat"
            st.rerun()

        st.markdown('<div class="sidebar-caption">Workspace</div>', unsafe_allow_html=True)
        for label, page in PAGES:
            prefix = "● " if st.session_state.current_page == page else ""
            if st.button(
                f"{prefix}{label}",
                key=f"nav_{page}",
                use_container_width=True,
            ):
                go_to_page(page)

        st.divider()
        name = st.session_state.profile_name.strip() or "Customer"
        st.caption(f"Profile · {name}")
        if st.button("Logout", key="logout", use_container_width=True):
            clear_session()
            st.rerun()


def render_page_heading(title: str, subtitle: str):
    st.markdown(f'<div class="page-heading">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-subheading">{subtitle}</div>', unsafe_allow_html=True)


def render_chat():
    if not st.session_state.messages:
        st.markdown(
            """
            <div class="chat-intro">
                <h1>How can we help today?</h1>
                <p>Ask a question or describe an issue. Your support conversation is ready.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        render_page_heading("AI Chat", "Your personal customer support conversation.")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Message SupportAI")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        try:
            with st.spinner("SupportAI is thinking..."):
                result = api_post(
                    "/chat",
                    {"message": prompt},
                    timeout=120,
                )
            answer = result["response"]
            st.session_state.messages.append(
                {"role": "assistant", "content": answer}
            )
            with st.chat_message("assistant"):
                st.markdown(answer)
        except (requests.RequestException, KeyError) as error:
            if isinstance(error, requests.RequestException):
                show_request_error("send your message", error)
            else:
                st.error("The support service returned an unexpected response.")


def render_dashboard():
    render_page_heading(
        "Dashboard",
        "An overview of your complaint activity.",
    )
    try:
        stats = api_get("/dashboard")
    except requests.RequestException as error:
        show_request_error("load the dashboard", error)
        return

    metric_cols = st.columns(4)
    metric_cols[0].metric("Total Complaints", stats["total_complaints"])
    metric_cols[1].metric("Pending", stats["pending_complaints"])
    metric_cols[2].metric("In Progress", stats["in_progress_complaints"])
    metric_cols[3].metric("Resolved", stats["resolved_complaints"])

    st.subheader("Recent Complaints")
    try:
        complaints_result = api_get("/complaints")
    except requests.RequestException as error:
        show_request_error("load recent complaints", error)
        complaints_result = None

    recent_complaints = (
        complaints_result.get("complaints", [])[:5]
        if complaints_result is not None
        else None
    )
    if recent_complaints:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": complaint["complaint_id"],
                        "Subject": complaint["subject"],
                        "Status": complaint["status"],
                        "Created": complaint["created_at"],
                    }
                    for complaint in recent_complaints
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    elif recent_complaints is not None:
        st.info("No complaints have been registered yet.")

    st.subheader("Complaint status")
    status_data = pd.DataFrame(
        [
            {"Status": "Pending", "Count": stats["pending_complaints"]},
            {"Status": "In Progress", "Count": stats["in_progress_complaints"]},
            {"Status": "Resolved", "Count": stats["resolved_complaints"]},
        ]
    )
    st.bar_chart(
        status_data,
        x="Status",
        y="Count",
        color="Status",
        horizontal=True,
        height=300,
    )


def render_complaint_form():
    render_page_heading(
        "Register a complaint",
        "Tell us what happened and our team can follow up.",
    )
    st.caption(
        f"Submitting as {st.session_state.profile_name} "
        f"({st.session_state.profile_email})"
    )
    with st.form("complaint_form", clear_on_submit=False):
        subject = st.text_input(
            "Subject",
            placeholder="For example, damaged order",
            key="complaint_subject",
        )
        description = st.text_area(
            "Description",
            placeholder="Describe the issue and any relevant details.",
            height=150,
            key="complaint_description",
        )
        submitted = st.form_submit_button(
            "Submit complaint",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not subject.strip() or not description.strip():
            st.warning("Complete both the subject and description.")
        else:
            try:
                result = api_post(
                    "/complaints",
                    {
                        "subject": subject.strip(),
                        "description": description.strip(),
                    },
                )
                st.success(result.get("message", "Your complaint is awaiting admin review."))
                st.caption(f"Complaint ID: #{result['complaint_id']}")
            except requests.RequestException as error:
                show_request_error("submit the complaint", error)
            except KeyError:
                st.error("The support service returned an unexpected response.")


def render_complaints():
    render_page_heading(
        "Complaints",
        "Review complaint details and their current status.",
    )
    try:
        result = api_get("/complaints")
    except requests.RequestException as error:
        show_request_error("load complaints", error)
        return

    complaints = result.get("complaints", [])
    latest_preference = result.get("latest_resolution_preference")
    st.caption(f"{result.get('total_complaints', len(complaints))} complaints")
    if not complaints:
        st.info("No complaints have been registered yet.")
        return

    for complaint in complaints:
        complaint_id = complaint["complaint_id"]
        current_status = complaint.get("status", "Pending")
        approval_status = complaint.get("approval_status", "Accepted")
        with st.expander(
            f"#{complaint_id}  ·  {complaint['subject']}  ·  {current_status}",
            expanded=False,
        ):
            details_col, status_col = st.columns([2, 1])
            with details_col:
                st.markdown(f"**Customer ID:** {complaint['customer_id']}")
                st.markdown(f"**Description**  \n{complaint['description']}")
                st.caption(f"Created {complaint['created_at']}")
            with status_col:
                st.markdown(f"**Status:** {current_status}")

            st.markdown(f"**Approval status:** {approval_status}")
            if approval_status == "Pending":
                st.info("Your complaint is awaiting admin review.")
            elif approval_status == "Rejected":
                st.error("Your complaint was rejected by the Admin.")
                if complaint.get("rejection_reason"):
                    st.markdown(f"**Rejection reason:** {complaint['rejection_reason']}")
            elif approval_status == "Accepted":
                selected_resolution = complaint.get("resolution")
                if selected_resolution:
                    st.success(f"Your selected resolution: {selected_resolution}")
                    continue

                def save_resolution(choice):
                    try:
                        api_put(
                            f"/complaints/{complaint_id}/resolution",
                            {"resolution": choice},
                        )
                        st.success(f"Your {choice} preference has been saved.")
                        st.rerun()
                    except requests.RequestException as error:
                        show_request_error("save your resolution choice", error)

                other_options_key = f"show_other_resolution_options_{complaint_id}"
                complaint_options = complaint.get("resolution_options", [])
                previous_choice = (
                    latest_preference
                    if latest_preference in complaint_options
                    else None
                )
                if previous_choice:
                    st.info(
                        f"Your previous complaint was accepted, and you selected a "
                        f"{previous_choice}. Would you like the same resolution this time?"
                    )
                    if not st.session_state.get(other_options_key):
                        same_col, other_col = st.columns(2)
                        with same_col:
                            if st.button(
                                f"{previous_choice} - Same as last time",
                                key=f"same_resolution_{complaint_id}",
                                use_container_width=True,
                            ):
                                save_resolution(previous_choice)
                        with other_col:
                            if st.button(
                                "Other options",
                                key=f"other_resolution_{complaint_id}",
                                use_container_width=True,
                            ):
                                st.session_state[other_options_key] = True
                                st.rerun()
                        continue
                    st.caption("Choose a different resolution:")
                    options = complaint.get("other_resolution_options", [])
                else:
                    st.info("Your complaint was accepted. Choose a resolution:")
                    options = complaint_options

                option_cols = st.columns(len(options))
                for option_col, option in zip(option_cols, options):
                    with option_col:
                        if st.button(
                            option,
                            key=f"resolution_{option}_{complaint_id}",
                            use_container_width=True,
                        ):
                            save_resolution(option)


def render_profile():
    render_page_heading(
        "Customer Profile",
        "Your account details are attached to your authenticated session.",
    )
    st.text_input("Name", value=st.session_state.profile_name, disabled=True)
    st.text_input("Email", value=st.session_state.profile_email, disabled=True)
    st.caption("To change your account email, contact support.")


st.session_state.setdefault("current_page", "chat")
st.session_state.setdefault("messages", [])

if st.session_state.get("access_token"):
    try:
        authenticated_customer = api_get("/auth/me")
    except requests.RequestException as error:
        show_request_error("validate your session", error)
        st.stop()

    st.session_state.profile_name = authenticated_customer["name"]
    st.session_state.profile_email = authenticated_customer["email"]
    st.session_state.setdefault("profile_name_input", authenticated_customer["name"])
    st.session_state.setdefault("profile_email_input", authenticated_customer["email"])
    render_sidebar()

    page_renderers = {
        "chat": render_chat,
        "dashboard": render_dashboard,
        "register": render_complaint_form,
        "complaints": render_complaints,
        "profile": render_profile,
    }
    page_renderers.get(st.session_state.current_page, render_chat)()
else:
    st.session_state.current_page = "login"
    render_auth_page()

