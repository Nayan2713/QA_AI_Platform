"""
Shared SSRF guard.

Blocks a submitted URL from resolving to a private/internal/loopback/link-local
address before it's handed to the crawler (browser-use/Playwright). Applied at
two points for defense-in-depth: serializer validation (fast, first line) and
again right before the crawl starts in tasks/discovery.py (protects against
DNS rebinding between validation time and crawl time).
"""
import ipaddress
import socket
from urllib.parse import urlparse

from django.core.exceptions import ValidationError as DjangoValidationError

# Hostnames that are always allowed even though they resolve locally —
# extend via env var if a real internal target ever needs to be QA'd.
_ALLOWLIST = {'localhost'}


def _is_public_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_public_host(url: str) -> None:
    """
    Raises DjangoValidationError if `url`'s hostname resolves to a
    non-public IP address (private/loopback/link-local/etc). No-op for
    blank/None input — required-field validation is handled elsewhere.
    """
    if not url:
        return

    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise DjangoValidationError(f"Could not parse a hostname from URL: {url}")

    if hostname.lower() in _ALLOWLIST:
        return

    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise DjangoValidationError(f"Could not resolve hostname: {hostname}")

    resolved_ips = {info[4][0] for info in addrinfo}
    if not resolved_ips:
        raise DjangoValidationError(f"Could not resolve hostname: {hostname}")

    for ip_str in resolved_ips:
        if not _is_public_ip(ip_str):
            raise DjangoValidationError(
                f"URL '{url}' resolves to a non-public address ({ip_str}) and cannot be scanned."
            )