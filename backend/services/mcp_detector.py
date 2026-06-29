import logging
import socket
from urllib.parse import urlparse
from django.conf import settings

logger = logging.getLogger(__name__)


def check_mcp_availability(timeout=0.3):
    """
    Checks if the MCP server is available using a raw socket probe.

    FIX: The original used requests.get() with a 2-second HTTP timeout.
    Every single discovery run wasted 2 seconds here even when MCP was
    never configured. A raw socket probe takes 0.3s and requires no
    HTTP round-trip — it just checks if the port is open.
    """
    url = getattr(settings, 'MCP_SERVER_URL', 'http://localhost:5001')
    logger.info(f"Checking MCP server availability at {url} (timeout={timeout}s)")

    try:
        parsed = urlparse(url)
        host = parsed.hostname or 'localhost'
        port = parsed.port or 5001
        with socket.create_connection((host, port), timeout=timeout) as _:
            logger.info("MCP server port is open.")
            return True
    except Exception as e:
        logger.warning(f"MCP server not reachable: {e}")
        return False


def route_discovery(app_id):
    """
    Decides whether to route discovery through MCP or browser automation.
    Returns 'mcp' or 'browser'.
    """
    if check_mcp_availability():
        logger.info("Routing discovery through MCP.")
        return 'mcp'
    logger.info("MCP not available. Routing discovery through Playwright Browser.")
    return 'browser'