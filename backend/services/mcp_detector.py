import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def check_mcp_availability(timeout=2):
    """
    Checks if the Model Context Protocol (MCP) server is available by hitting the MCP_SERVER_URL.
    Uses a strict 2-second timeout.
    """
    url = getattr(settings, 'MCP_SERVER_URL', 'http://localhost:5001')
    logger.info(f"Checking MCP server availability at {url} (timeout={timeout}s)")
    
    try:
        # We can ping a health endpoint or just make a request
        # In a real MCP setup, this might be a JSON-RPC request or SSE connection endpoint.
        # For the MVP, we do a quick check (e.g. GET request or POST with JSON-RPC ping)
        response = requests.get(url, timeout=timeout)
        if response.status_code in [200, 201, 204]:
            logger.info("MCP server detected successfully.")
            return True
        else:
            logger.warning(f"MCP server responded with status: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.warning(f"MCP server not reachable. Error: {e}")
        return False


def route_discovery(app_id):
    """
    Decides whether to route discovery through MCP or use browser automation fallback.
    Returns a string: 'mcp' or 'browser'.
    """
    if check_mcp_availability():
        logger.info("Routing discovery through MCP.")
        return 'mcp'
    else:
        logger.info("MCP not available. Routing discovery through Playwright Browser.")
        return 'browser'
