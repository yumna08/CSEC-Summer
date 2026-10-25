import ipaddress
import secrets
import socket
from typing import Tuple
from urllib.parse import urlparse
from fastapi import Header, HTTPException, status
from app.core.config import (
    ADMIN_API_KEY,
    APPROVED_DOMAINS,
    REQUIRE_ADMIN_AUTH,
)

# Known cloud metadata and link-local ranges
CLOUD_METADATA_IPS = {
    "169.254.169.254",
    "169.254.170.2",
    "metadata.google.internal",
}


def is_ip_allowed(ip_str: str) -> bool:
    """Check if an IP address is public and safe (not loopback, private, multicast, or cloud metadata)."""
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip_str in CLOUD_METADATA_IPS:
            return False
        if ip.is_loopback:
            return False
        if ip.is_private:
            return False
        if ip.is_link_local:
            return False
        if ip.is_multicast:
            return False
        if ip.is_reserved:
            return False
        if ip.is_unspecified:
            return False
        return True
    except ValueError:
        return False


def is_domain_approved(hostname: str) -> bool:
    """Check if hostname matches or is a subdomain of an approved domain."""
    hostname = hostname.lower().strip()
    for domain in APPROVED_DOMAINS:
        if hostname == domain or hostname.endswith("." + domain):
            return True
    return False


def validate_url_security(url: str, check_approved_domain: bool = True) -> Tuple[bool, str]:
    """
    Validate a URL to prevent Server-Side Request Forgery (SSRF) and ensure it belongs to approved domains.
    Returns (is_valid, error_reason).
    """
    if not url or not isinstance(url, str):
        return False, "URL cannot be empty."

    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False, "Malformed URL format."

    if parsed.scheme.lower() not in ("http", "https"):
        return False, "Only HTTP and HTTPS protocols are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL is missing a valid hostname."

    # Prevent embedded userinfo in URL (e.g., http://user:pass@host)
    if parsed.username or parsed.password:
        return False, "Credentials in URLs are not permitted."

    # Check approved domains
    if check_approved_domain and not is_domain_approved(hostname):
        return False, f"Domain '{hostname}' is not in the approved ASTU domain list: {APPROVED_DOMAINS}"

    # Resolve hostname to IP and check for private/loopback/cloud metadata
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        if not addr_info:
            return False, f"Could not resolve host '{hostname}'."

        for entry in addr_info:
            ip = entry[4][0]
            if not is_ip_allowed(ip):
                return False, f"Host '{hostname}' resolves to an unsafe or private IP address."
    except socket.gaierror:
        return False, f"DNS resolution failed for host '{hostname}'."
    except Exception as e:
        return False, f"URL security check failed: {str(e)}"

    return True, ""


def verify_admin_authorization(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")):
    """
    Dependency to verify administrative authorization.
    In production (REQUIRE_ADMIN_AUTH=True or ADMIN_API_KEY set), validates X-Admin-Key header
    using constant-time comparison (secrets.compare_digest) to prevent timing attacks.
    In development, permits access when no key is configured.
    """
    if REQUIRE_ADMIN_AUTH or ADMIN_API_KEY:
        if not ADMIN_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Administrative operations are disabled because ADMIN_API_KEY is not configured.",
            )
        if not x_admin_key or not secrets.compare_digest(x_admin_key, ADMIN_API_KEY):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing administrative authorization key.",
            )
    return True
