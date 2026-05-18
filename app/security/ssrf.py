import ipaddress
import socket
from urllib.parse import urlparse
import structlog

logger = structlog.get_logger(__name__)

# Private and reserved IP ranges that must never be fetched
BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / AWS metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-grade NAT
    ipaddress.ip_network("198.18.0.0/15"),  # Benchmarking
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

# Blocked hostnames
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.google.com",
}

# Only allow HTTP/HTTPS
ALLOWED_SCHEMES = {"http", "https"}


class SSRFError(Exception):
    """Raised when a URL fails SSRF validation."""
    pass


def validate_url(url: str) -> str:
    """
    Validate a URL against SSRF attacks.
    Returns the validated URL or raises SSRFError.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise SSRFError(f"Failed to parse URL: {url}")

    # Scheme check
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SSRFError(f"Blocked scheme: {parsed.scheme}")

    # Hostname check
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("No hostname in URL")

    hostname_lower = hostname.lower()
    if hostname_lower in BLOCKED_HOSTNAMES:
        raise SSRFError(f"Blocked hostname: {hostname}")

    # Port check — block non-standard ports that might indicate internal services
    port = parsed.port
    if port and port not in (80, 443):
        raise SSRFError(f"Blocked non-standard port: {port}")

    # Resolve hostname to IP and check against blocked ranges
    try:
        resolved_ips = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise SSRFError(f"Cannot resolve hostname: {hostname}")

    for family, _, _, _, sockaddr in resolved_ips:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFError(f"Invalid resolved IP: {ip_str}")

        for network in BLOCKED_NETWORKS:
            if ip in network:
                logger.warning(
                    "ssrf_blocked",
                    url=url,
                    hostname=hostname,
                    resolved_ip=ip_str,
                    blocked_network=str(network),
                )
                raise SSRFError(
                    f"Blocked: {hostname} resolves to private IP {ip_str}"
                )

    return url


