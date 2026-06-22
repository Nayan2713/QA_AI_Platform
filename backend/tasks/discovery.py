from celery import shared_task
from django.db import transaction
from django.conf import settings
from django.utils import timezone
import logging
import requests
import threading

from core.models import CeleryTask, Application, Page
from services.mcp_detector import route_discovery
from services.browser_discovery import BrowserDiscoveryService

logger = logging.getLogger(__name__)

def run_in_thread(func, *args, **kwargs):
    """
    Runs a function inside a separate thread to bypass Django's SynchronousOnlyOperation check.
    Closes the thread's DB connection afterwards to prevent connection leaks.
    """
    res = []
    err = []
    def target():
        from django.db import connection
        try:
            res.append(func(*args, **kwargs))
        except Exception as e:
            err.append(e)
        finally:
            connection.close()
            
    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    if err:
        raise err[0]
    return res[0]

@shared_task(bind=True, name="tasks.discovery.start_discovery")
def start_discovery(self, app_id):
    """
    Celery task that tracks task progress in CeleryTask,
    detects MCP availability, routes to MCP or browser discovery,
    saves the discovered pages, and updates the application status.
    """
    logger.info(f"Starting discovery task for application ID: {app_id}")
    
    # Create/update task tracking record (runs in celery thread before Playwright is started)
    task_id = self.request.id or "dummy_task_id"
    
    def get_or_create_task():
        obj, created = CeleryTask.objects.get_or_create(
            task_id=task_id,
            defaults={
                'task_type': 'discovery',
                'status': 'progress',
                'progress': 10
            }
        )
        if not created:
            obj.status = 'progress'
            obj.progress = 10
            obj.save()
        return obj

    task_record = run_in_thread(get_or_create_task)
    
    try:
        app = run_in_thread(Application.objects.get, id=app_id)
    except Application.DoesNotExist:
        logger.error(f"Application with ID {app_id} does not exist.")
        def handle_missing_app():
            task_record.status = 'failed'
            task_record.error = f"Application with ID {app_id} not found."
            task_record.completed_at = timezone.now()
            task_record.save()
        run_in_thread(handle_missing_app)
        return {"error": f"Application with ID {app_id} not found."}

    # Update app status to DISCOVERING
    def set_app_discovering():
        app.status = 'DISCOVERING'
        app.save()
        task_record.progress = 20
        task_record.save()
    run_in_thread(set_app_discovering)

    # Route discovery
    route = route_discovery(app.id)
    pages_data = []
    login_successful = None
    
    def set_route_started():
        task_record.progress = 30
        task_record.save()
    run_in_thread(set_route_started)

    if route == 'mcp':
        logger.info("Executing MCP discovery path...")
        try:
            def set_mcp_status():
                task_record.result = {"status_text": "Requesting page structure from MCP server..."}
                task_record.save()
            run_in_thread(set_mcp_status)
            
            mcp_url = getattr(settings, 'MCP_SERVER_URL', 'http://localhost:5001')
            response = requests.post(
                f"{mcp_url}/discover", 
                json={"url": app.url, "login_url": app.login_url}, 
                timeout=5
            )
            if response.status_code == 200:
                result = response.json()
                pages_data = result.get("pages", [])
                
                def set_mcp_source():
                    app.discovery_source = 'mcp'
                    app.save()
                run_in_thread(set_mcp_source)
                logger.info(f"Successfully retrieved {len(pages_data)} pages from MCP.")
            else:
                logger.warning("MCP server failed to return data, falling back to Playwright browser.")
                route = 'browser'
        except Exception as e:
            logger.warning(f"MCP discovery query failed: {e}. Falling back to Playwright.")
            route = 'browser'

    def set_progress_40():
        task_record.progress = 40
        task_record.save()
    run_in_thread(set_progress_40)

    if route == 'browser':
        logger.info("Executing Playwright browser discovery path...")
        try:
            crawler = BrowserDiscoveryService(max_pages=8)
            
            def on_crawler_progress(current_url, pages_count):
                def update_progress():
                    task_record.progress = min(40 + pages_count * 7, 90)
                    task_record.result = {
                        "status_text": f"Crawling page {pages_count + 1}: {current_url}",
                        "pages_discovered": pages_count + 1
                    }
                    task_record.save()
                run_in_thread(update_progress)
                
            result = crawler.discover(
                start_url=app.url,
                login_url=app.login_url,
                username=app.username,
                password=app.password,
                on_progress=on_crawler_progress
            )
            pages_data = result.get("pages", [])
            login_successful = result.get("login_successful")
            
            def set_browser_source():
                app.discovery_source = 'browser'
                if app.login_url:
                    app.login_status = 'SUCCESS' if login_successful else 'FAILED'
                app.save()
            run_in_thread(set_browser_source)
            logger.info(f"Successfully crawled {len(pages_data)} pages using Playwright.")
        except Exception as e:
            logger.error(f"Playwright browser discovery failed: {e}")
            def handle_crawl_error():
                app.status = 'FAILED'
                if app.login_url:
                    app.login_status = 'FAILED'
                app.save()
                task_record.status = 'failed'
                task_record.error = str(e)
                task_record.completed_at = timezone.now()
                task_record.save()
            run_in_thread(handle_crawl_error)
            return {"status": "FAILED", "error": str(e)}

    def set_progress_75():
        task_record.progress = 75
        task_record.save()
    run_in_thread(set_progress_75)

    # Save pages inside a database transaction
    try:
        def save_discovered_pages():
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
                if app.login_url:
                    if app.discovery_source == 'browser':
                        app.login_status = 'SUCCESS' if login_successful else 'FAILED'
                    else:
                        app.login_status = 'SUCCESS'
                else:
                    app.login_status = 'NOT_ATTEMPTED'
                app.save()
                
                task_record.status = 'success'
                task_record.progress = 100
                task_record.result = {
                    "pages_discovered": len(pages_data),
                    "source": app.discovery_source
                }
                task_record.completed_at = timezone.now()
                task_record.save()
        run_in_thread(save_discovered_pages)
            
    except Exception as e:
        logger.error(f"Failed to save pages to DB: {e}")
        def handle_db_error():
            app.status = 'FAILED'
            app.save()
            task_record.status = 'failed'
            task_record.error = str(e)
            task_record.completed_at = timezone.now()
            task_record.save()
        run_in_thread(handle_db_error)
        return {"status": "FAILED", "error": str(e)}

    logger.info(f"Discovery completed for app {app.url}")
    return {
        "status": "SUCCESS",
        "pages_discovered": len(pages_data),
        "source": app.discovery_source
    }
