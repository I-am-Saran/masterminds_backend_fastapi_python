"""
SSO Service - Microsoft Entra ID (Azure AD) OpenID Connect authentication.
Validates ID tokens (JWKS, tenant, audience, issuer, expiry) and signs in
existing Master Minds users only. No auto-provisioning.
"""

from typing import Any, Dict, Optional

import jwt
import psycopg2
from jwt import PyJWKClient

from config import DB_URL, MS_TENANT_ID, MS_CLIENT_ID

ALLOWED_EMAIL_DOMAINS = ["@cavininfotech.com", "@hepl.com"]
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


class SSOValidationError(Exception):
    """Raised when Microsoft token validation fails."""

    def __init__(self, error: str, message: str):
        self.error = error
        self.message = message
        super().__init__(message)


def validate_email_domain(email: str) -> bool:
    if not email:
        return False
    email_lower = email.lower()
    return any(email_lower.endswith(domain.lower()) for domain in ALLOWED_EMAIL_DOMAINS)


def get_sso_user(
    email: str,
    full_name: str,
    sso_user_id: str,
) -> Optional[Dict[str, Any]]:
    """Look up an existing Master Minds user. Never auto-creates accounts."""
    conn = None
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        cur.execute(
            "SELECT id, email, full_name, tenant_id, is_active FROM users WHERE LOWER(email) = LOWER(%s) LIMIT 1",
            (email,),
        )
        user_row = cur.fetchone()

        if not user_row:
            conn.close()
            return {
                "error": "user_not_found",
                "message": (
                    "Your account is not registered in Master Minds. "
                    "Please use Request Access or contact your administrator."
                ),
            }

        user_id, user_email, user_full_name, user_tenant_id, is_active = user_row

        if not is_active:
            conn.close()
            return {
                "error": "inactive",
                "message": "Your account is inactive. Please contact your administrator.",
            }

        cur.execute(
            """UPDATE users
               SET sso_provider = %s, sso_user_id = %s, last_login = NOW(),
                   login_count = COALESCE(login_count, 0) + 1,
                   updated_at = NOW()
               WHERE id = %s""",
            ("microsoft", sso_user_id, user_id),
        )
        conn.commit()
        conn.close()

        return {
            "user_id": str(user_id),
            "email": user_email,
            "full_name": user_full_name or full_name,
            "tenant_id": str(user_tenant_id) if user_tenant_id else DEFAULT_TENANT_ID,
        }
    except Exception as e:
        print(f"Error in get_sso_user: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return None


def _expected_issuer() -> str:
    return f"https://login.microsoftonline.com/{MS_TENANT_ID}/v2.0"


def _jwks_url() -> str:
    return f"https://login.microsoftonline.com/{MS_TENANT_ID}/discovery/v2.0/keys"


def _decode_microsoft_jwt(id_token: str) -> Dict[str, Any]:
    """Verify Microsoft Entra ID OIDC ID token against JWKS and configured tenant/client."""
    if not MS_TENANT_ID or not MS_CLIENT_ID:
        raise SSOValidationError(
            "sso_not_configured",
            "Microsoft SSO is not configured on the server. Contact your administrator.",
        )

    if not id_token or not id_token.strip():
        raise SSOValidationError("missing_token", "Microsoft sign-in token is required.")

    try:
        signing_key = PyJWKClient(_jwks_url()).get_signing_key_from_jwt(id_token)
    except Exception as exc:
        raise SSOValidationError(
            "invalid_signature",
            f"Unable to verify token signing key: {exc}",
        ) from exc

    try:
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=MS_CLIENT_ID,
            issuer=_expected_issuer(),
            options={"require": ["exp", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise SSOValidationError(
            "token_expired",
            "Microsoft sign-in token has expired. Please sign in again.",
        ) from exc
    except jwt.InvalidAudienceError as exc:
        raise SSOValidationError(
            "invalid_audience",
            "Token audience does not match the application client ID.",
        ) from exc
    except jwt.InvalidIssuerError as exc:
        raise SSOValidationError(
            "invalid_issuer",
            "Token issuer does not match the configured Microsoft tenant.",
        ) from exc
    except jwt.InvalidSignatureError as exc:
        raise SSOValidationError(
            "invalid_signature",
            "Token signature verification failed.",
        ) from exc
    except jwt.DecodeError as exc:
        raise SSOValidationError(
            "invalid_token",
            "Microsoft sign-in token could not be decoded.",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise SSOValidationError(
            "invalid_token",
            f"Microsoft sign-in token is invalid: {exc}",
        ) from exc

    token_tenant = claims.get("tid")
    if not token_tenant:
        raise SSOValidationError(
            "invalid_tenant",
            "Token is missing the tenant ID (tid) claim.",
        )
    if str(token_tenant).lower() != str(MS_TENANT_ID).lower():
        raise SSOValidationError(
            "invalid_tenant",
            "Token tenant ID does not match the configured Microsoft tenant.",
        )

    return claims


def validate_microsoft_token(id_token: str) -> Dict[str, Any]:
    """
    Validate a Microsoft Entra ID OIDC ID token and extract user information.
    Returns a user info dict or an error dict with explicit error codes.
    """
    try:
        claims = _decode_microsoft_jwt(id_token)
    except SSOValidationError as exc:
        return {"error": exc.error, "message": exc.message}

    email = (
        claims.get("email")
        or claims.get("upn")
        or claims.get("preferred_username")
    )
    name = (
        claims.get("name")
        or claims.get("display_name")
        or (email.split("@")[0] if email else "User")
    )

    if not email:
        return {
            "error": "missing_email",
            "message": "Microsoft token does not contain a valid email address.",
        }

    if not validate_email_domain(email):
        return {
            "error": "domain_not_allowed",
            "message": "Only @cavininfotech.com and @hepl.com email addresses are allowed.",
        }

    sso_user_id = claims.get("oid") or claims.get("sub")
    if not sso_user_id:
        return {
            "error": "missing_subject",
            "message": "Microsoft token is missing a user identifier (oid/sub).",
        }

    return {
        "email": email.lower(),
        "full_name": name,
        "sso_user_id": str(sso_user_id),
    }


def authenticate_sso_user(id_token: str) -> Optional[Dict[str, Any]]:
    """
    Authenticate via Microsoft SSO.
    Validates the OIDC ID token, then signs in existing Master Minds users only.
    """
    try:
        user_info = validate_microsoft_token(id_token)

        if user_info.get("error"):
            return user_info

        user_data = get_sso_user(
            user_info["email"],
            user_info["full_name"],
            user_info["sso_user_id"],
        )

        if not user_data:
            return {
                "error": "auth_failed",
                "message": "Unable to complete Microsoft sign-in. Please try again.",
            }

        if user_data.get("error"):
            return user_data

        from services.auth_service import create_jwt_token

        token = create_jwt_token(user_data["user_id"], user_data["email"])

        return {
            "user_id": user_data["user_id"],
            "email": user_data["email"],
            "full_name": user_data["full_name"],
            "tenant_id": user_data["tenant_id"],
            "token": token,
        }
    except Exception as e:
        print(f"Error in authenticate_sso_user: {e}")
        return {
            "error": "auth_failed",
            "message": "Unable to complete Microsoft sign-in. Please try again.",
        }
