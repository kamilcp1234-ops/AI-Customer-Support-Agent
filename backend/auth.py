import base64
import hashlib
import hmac
import os
import secrets

from itsdangerous import BadSignature, URLSafeTimedSerializer


SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
TOKEN_MAX_AGE_SECONDS = 60 * 60
TOKEN_SALT = "supportai-auth-v1"
STAFF_TOKEN_SALT = "supportai-staff-auth-v1"


class AuthenticationConfigurationError(RuntimeError):
    pass


def _auth_secret() -> str:
    secret = os.getenv("SUPPORTAI_AUTH_SECRET")
    if not secret or len(secret) < 32:
        raise AuthenticationConfigurationError(
            "Authentication is not configured."
        )
    return secret


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_auth_secret(), salt=TOKEN_SALT)


def _staff_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_auth_secret(), salt=STAFF_TOKEN_SALT)


def issue_access_token(customer_id: int) -> str:
    return _serializer().dumps({"sub": int(customer_id)})


def verify_access_token(token: str, max_age: int = TOKEN_MAX_AGE_SECONDS) -> int:
    payload = _serializer().loads(token, max_age=max_age)
    customer_id = payload.get("sub")
    if not isinstance(customer_id, int) or customer_id <= 0:
        raise BadSignature("Invalid authentication token.")
    return customer_id


def issue_staff_access_token(staff_id: int) -> str:
    return _staff_serializer().dumps({"sub": int(staff_id), "typ": "staff"})


def verify_staff_access_token(
    token: str,
    max_age: int = TOKEN_MAX_AGE_SECONDS,
) -> int:
    payload = _staff_serializer().loads(token, max_age=max_age)
    staff_id = payload.get("sub")
    if payload.get("typ") != "staff" or not isinstance(staff_id, int) or staff_id <= 0:
        raise BadSignature("Invalid staff authentication token.")
    return staff_id


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=64 * 1024 * 1024,
    )
    return (
        "scrypt$" + str(SCRYPT_N) + "$" + str(SCRYPT_R) + "$"
        + str(SCRYPT_P) + "$" + _b64_encode(salt) + "$"
        + _b64_encode(derived_key)
    )


def verify_password(password: str, encoded_hash: str | None) -> bool:
    if encoded_hash is None:
        hashlib.scrypt(
            password.encode("utf-8"),
            salt=b"supportai-auth-dummy",
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=SCRYPT_DKLEN,
            maxmem=64 * 1024 * 1024,
        )
        return False

    try:
        algorithm, n, r, p, salt_text, hash_text = encoded_hash.split("$")
        if algorithm != "scrypt":
            return False
        if (int(n), int(r), int(p)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return False
        expected = _b64_decode(hash_text)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64_decode(salt_text),
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=SCRYPT_DKLEN,
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def normalize_email(email: str) -> str:
    return email.strip().lower()

