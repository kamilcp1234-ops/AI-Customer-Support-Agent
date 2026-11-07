import re
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.requests import Request
from starlette.responses import JSONResponse
from itsdangerous import BadSignature, SignatureExpired

from backend import database
from backend import auth
from backend.ai_agent import (
    AIServiceUnavailable,
    get_ai_response,
    get_approved_resolution_preference,
    retain_approved_resolution_preference,
)
from backend.auth import (
    AuthenticationConfigurationError,
    TOKEN_MAX_AGE_SECONDS,
    hash_password,
    issue_access_token,
    normalize_email,
    verify_access_token,
    verify_password,
)


app = FastAPI()
bearer_scheme = HTTPBearer(auto_error=False)
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
RESOLUTION_OPTIONS = ("Refund", "Replacement", "Voucher")


def validate_email(value: str) -> str:
    email = normalize_email(value)
    if len(email) > 150 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    return email


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Name is required.")
        return name

    @field_validator("email")
    @classmethod
    def normalize_registration_email(cls, value: str) -> str:
        return validate_email(value)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_login_email(cls, value: str) -> str:
        return validate_email(value)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)


class ComplaintRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)


class AdminComplaintStatusRequest(BaseModel):
    status: Literal["In Progress", "Resolved"]


class AdminComplaintDecisionRequest(BaseModel):
    decision: Literal["Accepted", "Rejected"]
    rejection_reason: str | None = Field(default=None, max_length=2000)


class ComplaintResolutionRequest(BaseModel):
    resolution: Literal["Refund", "Replacement", "Voucher"]


@app.exception_handler(RequestValidationError)
async def redact_validation_inputs(
    request: Request,
    exc: RequestValidationError,
):
    # Pydantic's default error payload includes the rejected input. Never echo
    # password values back to clients.
    safe_messages = []
    for error in exc.errors():
        location = error.get("loc", ())
        field = str(location[-1]) if location else ""
        error_type = error.get("type", "")
        if field in {"password", "confirm_password"}:
            if error_type == "missing":
                message = "Password is required."
            else:
                message = "Passwords must contain between 8 and 128 characters."
        elif field == "email":
            message = "Enter a valid email address."
        elif field == "confirm_password" or error_type == "value_error":
            message = "Registration details are invalid."
        else:
            message = "Invalid request details."
        if message not in safe_messages:
            safe_messages.append(message)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": safe_messages or ["Invalid request details."]},
    )


def auth_result(customer: dict[str, Any]) -> dict[str, Any]:
    try:
        token = issue_access_token(customer["customer_id"])
    except AuthenticationConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured.",
        )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": TOKEN_MAX_AGE_SECONDS,
        "customer": {
            "customer_id": customer["customer_id"],
            "name": customer["name"],
            "email": customer["email"],
        },
    }


def staff_auth_result(staff: dict[str, Any]) -> dict[str, Any]:
    try:
        token = auth.issue_staff_access_token(staff["staff_id"])
    except AuthenticationConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured.",
        )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": TOKEN_MAX_AGE_SECONDS,
        "staff": {
            "staff_id": staff["staff_id"],
            "name": staff["name"],
            "email": staff["email"],
            "role": staff["role"],
        },
    }


def get_current_customer(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required or session expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized

    try:
        customer_id = verify_access_token(credentials.credentials)
    except SignatureExpired:
        raise unauthorized
    except BadSignature:
        raise unauthorized
    except AuthenticationConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured.",
        )

    customer = database.get_customer_by_id(customer_id)
    if customer is None:
        raise unauthorized
    return customer


def get_current_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Staff authentication required or session expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized

    try:
        staff_id = auth.verify_staff_access_token(credentials.credentials)
    except (SignatureExpired, BadSignature):
        raise unauthorized from None
    except AuthenticationConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured.",
        )

    staff = database.get_staff_by_id(staff_id)
    if staff is None or not staff["is_active"]:
        raise unauthorized
    if staff["role"] not in {"admin", "support"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff role is not authorized for support operations.",
        )
    return staff


@app.get("/")
def home():
    return {"message": "AI Customer Support Agent API is running!"}


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest):
    try:
        customer = database.register_customer_account(
            request.name,
            request.email,
            hash_password(request.password),
        )
    except database.DuplicateCustomerEmailError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    return {
        "message": "Registration successful! Please log in.",
        "customer": {
            "customer_id": customer["customer_id"],
            "name": customer["name"],
            "email": customer["email"],
        },
    }


@app.post("/auth/login")
def login(request: LoginRequest):
    customer = database.get_customer_auth_by_email(request.email)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found. Please register first.",
        )
    stored_hash = customer.get("password_hash")
    if not verify_password(request.password, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password. Please try again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth_result(customer)


@app.get("/auth/me")
def current_customer_profile(
    customer: dict[str, Any] = Depends(get_current_customer),
):
    return {
        "customer_id": customer["customer_id"],
        "name": customer["name"],
        "email": customer["email"],
    }


@app.post("/chat")
def chat(
    request: ChatRequest,
    customer: dict[str, Any] = Depends(get_current_customer),
):
    customer_id = customer["customer_id"]
    try:
        answer = get_ai_response(request.message, customer_id)
    except AIServiceUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The support assistant is temporarily unavailable. Please try again.",
        ) from None

    try:
        database.save_chat_history(customer_id, request.message, answer)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Your message could not be saved. Please try again.",
        ) from None
    return {"customer": customer["name"], "response": answer}


@app.post("/complaints", status_code=status.HTTP_201_CREATED)
def create_complaint(
    request: ComplaintRequest,
    customer: dict[str, Any] = Depends(get_current_customer),
):
    complaint_id = database.save_complaint(
        customer["customer_id"],
        request.subject.strip(),
        request.description.strip(),
    )
    return {
        "message": "Your complaint is awaiting admin review.",
        "complaint_id": complaint_id,
        "customer": customer["name"],
        "status": "Pending",
        "approval_status": "Pending",
    }


@app.get("/complaints")
def get_complaints(
    customer: dict[str, Any] = Depends(get_current_customer),
):
    customer_id = customer["customer_id"]
    complaints = database.get_all_complaints(customer_id)
    latest_preference = get_approved_resolution_preference(customer_id)
    for complaint in complaints:
        if (
            complaint.get("approval_status") == "Accepted"
            and not complaint.get("resolution")
        ):
            if latest_preference in RESOLUTION_OPTIONS:
                complaint["resolution_options"] = [latest_preference]
                complaint["other_resolution_options"] = [
                    option
                    for option in RESOLUTION_OPTIONS
                    if option != latest_preference
                ]
            else:
                complaint["resolution_options"] = list(RESOLUTION_OPTIONS)
                complaint["other_resolution_options"] = []
        else:
            complaint["resolution_options"] = []
            complaint["other_resolution_options"] = []

    return {
        "total_complaints": len(complaints),
        "complaints": complaints,
        "latest_resolution_preference": latest_preference,
    }


@app.put("/complaints/{complaint_id}/resolution")
def select_complaint_resolution(
    complaint_id: int,
    request: ComplaintResolutionRequest,
    customer: dict[str, Any] = Depends(get_current_customer),
):
    try:
        result = database.save_complaint_resolution(
            customer["customer_id"], complaint_id, request.resolution
        )
    except database.ComplaintNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found.",
        ) from None
    except database.ComplaintNotAcceptedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resolution options are available only after admin acceptance.",
        ) from None
    except database.ResolutionAlreadySelectedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A resolution has already been selected for this complaint.",
        ) from None

    memory_saved = retain_approved_resolution_preference(
        customer["customer_id"],
        request.resolution,
        result.get("resolution_selected_at"),
    )
    return {**result, "memory_saved": memory_saved}


@app.post("/admin/auth/login")
def staff_login(request: LoginRequest):
    staff = database.get_staff_auth_by_email(request.email)
    if staff is None:
        verify_password(request.password, None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password(request.password, staff.get("password_hash")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not staff["is_active"] or staff["role"] not in {"admin", "support"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return staff_auth_result(staff)


@app.get("/admin/auth/me")
def current_staff_profile(
    staff: dict[str, Any] = Depends(get_current_staff),
):
    return {
        "staff_id": staff["staff_id"],
        "name": staff["name"],
        "email": staff["email"],
        "role": staff["role"],
    }


@app.get("/admin/dashboard")
def admin_dashboard(
    staff: dict[str, Any] = Depends(get_current_staff),
):
    return database.get_admin_dashboard_stats()


@app.get("/admin/complaints")
def admin_complaints(
    staff: dict[str, Any] = Depends(get_current_staff),
):
    complaints = database.get_all_complaints_for_staff()
    return {"total_complaints": len(complaints), "complaints": complaints}


@app.put("/admin/complaints/{complaint_id}/decision")
def decide_complaint_as_staff(
    complaint_id: int,
    request: AdminComplaintDecisionRequest,
    staff: dict[str, Any] = Depends(get_current_staff),
):
    try:
        result = database.decide_complaint(
            complaint_id,
            request.decision,
            staff["staff_id"],
            request.rejection_reason,
        )
    except database.ComplaintNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found.",
        ) from None
    except database.InvalidComplaintApprovalError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending complaints can be accepted or rejected.",
        ) from None
    return {**result, "approval_decided_by": staff["name"]}


@app.put("/admin/complaints/{complaint_id}/status")
def update_complaint_status_as_staff(
    complaint_id: int,
    request: AdminComplaintStatusRequest,
    staff: dict[str, Any] = Depends(get_current_staff),
):
    try:
        result = database.update_complaint_status_by_staff(
            complaint_id,
            request.status,
            staff["staff_id"],
        )
    except database.ComplaintNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found.",
        ) from None
    except database.InvalidComplaintTransitionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The complaint status cannot make that transition.",
        ) from None
    return {**result, "status_updated_by": staff["name"]}


@app.get("/dashboard")
def dashboard(
    customer: dict[str, Any] = Depends(get_current_customer),
):
    return database.get_dashboard_stats(customer["customer_id"])

