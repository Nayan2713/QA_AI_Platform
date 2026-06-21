import logging
import requests
from celery import shared_task
from django.db import transaction
from django.conf import settings

from core.models import Application, Page
from services.mcp_detector import route_discovery
from services.browser_discovery import BrowserDiscoveryService

logger = logging.getLogger(__name__)

@shared_task(name="tasks.discovery.start_discovery")
def start_discovery(app_id):
    """
    Celery task that detects MCP availability, routes to MCP or browser discovery,
    saves the discovered pages, and updates the application status.
    """
    logger.info(f"Starting discovery task for application ID: {app_id}")
    
    try:
        app = Application.objects.get(id=app_id)
    except Application.DoesNotExist:
        logger.error(f"Application with ID {app_id} does not exist.")
        return {"error": f"Application with ID {app_id} not found."}

    # Update app status to DISCOVERING
    app.status = 'DISCOVERING'
    app.save()

    # Route discovery
    route = route_discovery(app.id)
    pages_data = []
    
    if route == 'mcp':
        logger.info("Executing MCP discovery path...")
        try:
            mcp_url = getattr(settings, 'MCP_SERVER_URL', 'http://localhost:5001')
            # Query the MCP server for app structure. In MCP, we send a JSON-RPC request.
            # Here we send a POST with information about the app url we want to inspect
            response = requests.post(
                f"{mcp_url}/discover", 
                json={"url": app.url, "login_url": app.login_url}, 
                timeout=5
            )
            if response.status_code == 200:
                result = response.json()
                pages_data = result.get("pages", [])
                app.discovery_source = 'mcp'
                logger.info(f"Successfully retrieved {len(pages_data)} pages from MCP.")
            else:
                logger.warning("MCP server failed to return data, falling back to Playwright browser.")
                route = 'browser'
        except Exception as e:
            logger.warning(f"MCP discovery query failed: {e}. Falling back to Playwright.")
            route = 'browser'

    if route == 'browser':
        logger.info("Executing Playwright browser discovery path...")
        try:
            crawler = BrowserDiscoveryService(max_pages=8)
            result = crawler.discover(
                start_url=app.url,
                login_url=app.login_url,
                username=app.username,
                password=app.password
            )
            pages_data = result.get("pages", [])
            app.discovery_source = 'browser'
            logger.info(f"Successfully crawled {len(pages_data)} pages using Playwright.")
        except Exception as e:
            logger.error(f"Playwright browser discovery failed: {e}")
            app.status = 'FAILED'
            app.save()
            return {"status": "FAILED", "error": str(e)}

    # Save pages inside a database transaction
    try:
        with transaction.atomic():
            # Delete old pages to prevent stale records
            Page.objects.filter(app=app).delete()
            
            # Insert newly discovered pages
            for page_info in pages_data:
                Page.objects.create(
                    app=app,
                    url=page_info.get("url"),
                    title=page_info.get("title", ""),
                    forms=page_info.get("forms", []),
                    buttons=page_info.get("buttons", [])
                )
            
            app.status = 'DISCOVERED'
            app.save()
            
    except Exception as e:
        logger.error(f"Failed to save pages to DB: {e}")
        app.status = 'FAILED'
        app.save()
        return {"status": "FAILED", "error": str(e)}

    return {
        "status": "SUCCESS",
        "pages_discovered": len(pages_data),
        "source": app.discovery_source
    }
