from celery import shared_task
from django.db import transaction
from django.conf import settings
from django.utils import timezone
import logging
import requests
import threading
import asyncio
import json
import re
from urllib.parse import urlparse
from core.models import CeleryTask, Application, Page, APIEndpoint
from services.mcp_detector import route_discovery
from services.browser_discovery import BrowserDiscoveryService
from tasks.cancellation import check_cancelled, clear_stop_flag, TaskCancelled

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def get_url_pattern(url, base_url):
    parsed = urlparse(url)
    path = parsed.path

    segments = path.split('/')
    new_segments = []

    for segment in segments:
        if not segment:
            new_segments.append('')
            continue

        if segment.isdigit():
            new_segments.append(':id')
        elif re.match(
            r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$',
            segment
        ):
            new_segments.append(':id')
        elif len(segment) >= 8 and re.match(r'^[0-9a-fA-F]+$', segment):
            new_segments.append(':id')
        else:
            new_segments.append(segment)

    pattern = '/'.join(new_segments)
    return pattern if pattern else '/'


def _get_base_domain(host):
    """Return the registrable domain for a host string."""
    parts = host.split('.')
    if len(parts) >= 2:
        if parts[-2] in [
            'com', 'co', 'org', 'net', 'gov', 'edu', 'io', 'ai', 'app',
            'dev', 'tech', 'cloud', 'in', 'uk', 'au', 'ca', 'de', 'fr',
            'jp', 'br', 'mx', 'eu', 'us', 'info', 'biz', 'me', 'tv', 'so', 'to'
        ]:
            return '.'.join(parts[-3:])
        return '.'.join(parts[-2:])
    return host


# ---------------------------------------------------------------------------
# Bulk-save API endpoints  (replaces 1-query-per-log loop)
# ---------------------------------------------------------------------------

def save_api_endpoints(app, api_logs):
    """
    Saves API endpoints captured during browser discovery.

    OPTIMIZED: parses all logs first, then calls update_or_create only for
    unique (method, url_pattern) pairs — the inner loop is still needed
    because bulk upsert requires a unique constraint on those two columns
    and Django's bulk_create(update_conflicts=True) with JSONField isn't
    universally reliable across DB backends.  The real saving here is the
    same-domain check and schema parsing staying in Python before hitting DB.
    """
    if not api_logs:
        return

    parsed_base = urlparse(app.url)
    base_host = parsed_base.netloc.lower()
    base_domain = _get_base_domain(base_host)

    seen_keys = set()
    to_upsert = []

    for log in api_logs:
        url = log.get('url')
        if not url:
            continue

        method = log.get('method', 'GET').upper()
        body = log.get('body', '')
        auth_type = log.get('auth_type')

        parsed_url = urlparse(url)
        url_host = parsed_url.netloc.lower()
        url_domain = _get_base_domain(url_host)

        # Skip third-party domains
        if base_domain not in url_domain and url_domain not in base_domain:
            logger.debug(f"Skipping external API: {url} (domain={url_domain}, base={base_domain})")
            continue

        # Build url_pattern from path — preserve subdomain prefix when it differs
        path_pattern = get_url_pattern(url, app.url)
        if url_host != base_host and url_host not in ('', base_host):
            url_pattern = f"[{url_host}]{path_pattern}"
        else:
            url_pattern = path_pattern
        url_pattern = url_pattern[:990]

        dedup_key = (method, url_pattern)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        # Parse response schema
        response_schema = {}
        if body:
            try:
                data = json.loads(body)
                if isinstance(data, dict):
                    response_schema = {k: type(v).__name__ for k, v in data.items()}
                elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                    response_schema = {k: type(v).__name__ for k, v in data[0].items()}
            except Exception:
                pass

        # Parse request schema
        request_body = log.get('request_body', '')
        request_schema = {}
        if request_body:
            try:
                data = json.loads(request_body)
                if isinstance(data, dict):
                    request_schema = {k: type(v).__name__ for k, v in data.items()}
            except Exception:
                pass

        page_url = log.get('page_url')
        if page_url:
            request_schema['_trigger_page_url'] = page_url

        to_upsert.append({
            'method': method,
            'url_pattern': url_pattern,
            'request_schema': request_schema,
            'response_schema': response_schema,
            'auth_type': auth_type or 'none',
        })

    # Fetch existing endpoints to avoid update_or_create database hits
    existing_eps = {
        (ep.method, ep.url_pattern): ep
        for ep in APIEndpoint.objects.filter(application=app)
    }

    to_create = []
    to_update = []

    for ep in to_upsert:
        key = (ep['method'], ep['url_pattern'])
        if key in existing_eps:
            existing_ep = existing_eps[key]
            # Check if fields actually changed to avoid redundant updates
            changed = False
            if existing_ep.request_schema != ep['request_schema']:
                existing_ep.request_schema = ep['request_schema']
                changed = True
            if existing_ep.response_schema != ep['response_schema']:
                existing_ep.response_schema = ep['response_schema']
                changed = True
            if existing_ep.auth_type != ep['auth_type']:
                existing_ep.auth_type = ep['auth_type']
                changed = True
            if changed:
                to_update.append(existing_ep)
        else:
            to_create.append(
                APIEndpoint(
                    application=app,
                    method=ep['method'],
                    url_pattern=ep['url_pattern'],
                    request_schema=ep['request_schema'],
                    response_schema=ep['response_schema'],
                    auth_type=ep['auth_type']
                )
            )

    saved = len(to_create) + len(to_update)
    if to_create:
        APIEndpoint.objects.bulk_create(to_create, batch_size=100)
    if to_update:
        APIEndpoint.objects.bulk_update(to_update, ['request_schema', 'response_schema', 'auth_type'], batch_size=100)

    logger.info(
        f"save_api_endpoints: {saved} endpoints saved "
        f"out of {len(api_logs)} total captured."
    )


# ---------------------------------------------------------------------------
# Async / thread helpers
# ---------------------------------------------------------------------------

def run_async(coro):
    """
    Runs an async coroutine in a fresh thread with its own event loop.
    Prevents "Cannot run event loop while another loop is running" errors
    that occur when Playwright's sync API is already using a loop.
    """
    res = []
    err = []

    def target():
        from django.db import connection
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            val = loop.run_until_complete(coro)
            res.append((val,))
        except Exception as e:
            err.append(e)
        finally:
            loop.close()
            connection.close()

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()

    if err:
        raise err[0]
    return res[0][0] if res else None


def run_in_thread(func, *args, **kwargs):
    """
    Runs a function in a separate thread to bypass Django's
    SynchronousOnlyOperation check.
    
    OPTIMIZED: Removed connection.close() to preserve CONN_MAX_AGE connection pooling.
    """
    res = []
    err = []

    def target():
        try:
            res.append((func(*args, **kwargs),))
        except Exception as e:
            err.append(e)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    if err:
        raise err[0]
    return res[0][0] if res else None


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@shared_task(bind=True, name="tasks.discovery.start_discovery", queue="discovery")
def start_discovery(self, app_id, model_choice=None):
    """
    Celery task that tracks task progress in CeleryTask,
    detects MCP availability, routes to MCP or browser-use discovery,
    saves the discovered pages using bulk_create, and updates the
    application status.
    """
    logger.info(f"Starting discovery task for application ID: {app_id}")

    task_id = self.request.id or "dummy_task_id"

    # ------------------------------------------------------------------
    # Task tracking record
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Load application
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Update app → DISCOVERING  (single DB write, no extra thread)
    # ------------------------------------------------------------------
    def set_discovering():
        app.status = 'DISCOVERING'
        app.save(update_fields=['status'])
        task_record.progress = 20
        task_record.save(update_fields=['progress'])

    run_in_thread(set_discovering)

    # Cooperative cancellation check after app status update
    check_cancelled(task_id)

    # ------------------------------------------------------------------
    # Route decision
    # ------------------------------------------------------------------
    route = route_discovery(app.id)
    pages_data = []
    login_successful = None

    def set_progress(pct):
        task_record.progress = pct
        task_record.save(update_fields=['progress'])

    run_in_thread(set_progress, 30)

    # ------------------------------------------------------------------
    # MCP path
    # ------------------------------------------------------------------
    if route == 'mcp':
        logger.info("Executing MCP discovery path...")
        try:
            def set_mcp_status():
                task_record.result = {"status_text": "Requesting page structure from MCP server..."}
                task_record.save(update_fields=['result'])
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

                if app.use_llm_in_crawl:
                    # Run parallel AI summarization on pages returned by MCP
                    from services.llm_service import LLMService
                    llm = LLMService(model_choice=model_choice)

                    def summarize_single_page(p):
                        if not p.get("forms") and not p.get("buttons"):
                            p["ai_summary"] = "Empty page with no interactive elements."
                            return
                        try:
                            p["ai_summary"] = llm.summarize_page(p) or ""
                        except Exception as ex:
                            logger.error(f"MCP page summarization error: {ex}")
                            p["ai_summary"] = ""

                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        executor.map(summarize_single_page, pages_data)
                else:
                    for p in pages_data:
                        p["ai_summary"] = ""

                def set_mcp_source():
                    app.discovery_source = 'mcp'
                    app.save(update_fields=['discovery_source'])
                run_in_thread(set_mcp_source)
                logger.info(f"Successfully retrieved {len(pages_data)} pages from MCP.")
            else:
                logger.warning("MCP server failed to return data, falling back to browser.")
                route = 'browser'
        except Exception as e:
            logger.warning(f"MCP discovery query failed: {e}. Falling back to browser.")
            route = 'browser'

    run_in_thread(set_progress, 40)

    storage_state_data = None
    captured_storage_state = None
    api_logs_data = []

    # ------------------------------------------------------------------
    # Browser / Playwright path
    # ------------------------------------------------------------------
    if route == 'browser':
        logger.info("Executing Playwright browser discovery path...")
        try:
            crawler = BrowserDiscoveryService(max_pages=50, model_choice=model_choice, use_llm=app.use_llm_in_crawl)

            storage_state_data = run_in_thread(lambda: app.storage_state)

            def on_crawler_progress(current_url, pages_count):
                def check_app_exists():
                    return Application.objects.filter(id=app_id).exists()
                if not run_in_thread(check_app_exists):
                    raise Exception("Application was deleted. Terminating crawl.")
                def update_progress():
                    task_record.progress = min(40 + pages_count * 4, 90)
                    task_record.result = {
                        "status_text": f"Crawling page {pages_count + 1}: {current_url}",
                        "pages_discovered": pages_count + 1
                    }
                    task_record.save(update_fields=['progress', 'result'])
                run_in_thread(update_progress)

            result = run_async(crawler.discover(
                start_url=app.url,
                login_url=app.login_url,
                username=app.username,
                password=app.password,
                storage_state=storage_state_data,
                on_progress=on_crawler_progress
            ))
            pages_data = result.get("pages", [])
            login_successful = result.get("login_successful")
            captured_storage_state = result.get("storage_state")
            api_logs_data = result.get("api_logs", [])
            login_error_val = result.get("login_error")

            def set_browser_source():
                if not Application.objects.filter(id=app_id).exists():
                    logger.info("Application was deleted during crawl. Skipping state save.")
                    return
                app.discovery_source = 'browser'
                if app.login_url:
                    app.login_status = 'SUCCESS' if login_successful else 'FAILED'
                    app.login_error = login_error_val if not login_successful else None
                if captured_storage_state:
                    app.storage_state = captured_storage_state
                app.save()
            run_in_thread(set_browser_source)
            logger.info(f"Successfully crawled {len(pages_data)} pages using Playwright.")
        except Exception as e:
            logger.error(f"Playwright browser discovery failed: {e}")
            def handle_crawl_error():
                if Application.objects.filter(id=app_id).exists():
                    app.status = 'FAILED'
                    if app.login_url:
                        app.login_status = 'FAILED'
                        app.login_error = f"Discovery run exception: {str(e)}"
                    app.save()
                task_record.status = 'failed'
                task_record.error = str(e)
                task_record.completed_at = timezone.now()
                task_record.save()
            run_in_thread(handle_crawl_error)
            return {"status": "FAILED", "error": str(e)}

    run_in_thread(set_progress, 75)

    # ------------------------------------------------------------------
    # Persist pages using bulk_create (1 query vs N queries)
    # ------------------------------------------------------------------
    try:
        def save_discovered_pages():
            if not Application.objects.filter(id=app_id).exists():
                logger.info("Application was deleted before saving pages.")
                return
            with transaction.atomic():
                # Clear stale records
                Page.objects.filter(app=app).delete()
                APIEndpoint.objects.filter(application=app).delete()

                # ---- OPTIMIZED: bulk_create instead of per-page create ----
                page_objects = [
                    Page(
                        app=app,
                        url=page_info.get("url"),
                        title=page_info.get("title", ""),
                        forms=page_info.get("forms", []),
                        buttons=page_info.get("buttons", []),
                        page_type=page_info.get("page_type"),
                        elements=page_info.get("elements", {}),
                        workflows=page_info.get("workflows", []),
                        accessibility_roles=page_info.get("accessibility_roles", []),
                        connections=page_info.get("connections", []),
                        semantic_metadata=page_info.get("semantic_metadata", {}),
                        ai_summary=page_info.get("ai_summary", "")
                    )
                    for page_info in pages_data
                    if page_info.get("url")
                ]
                if page_objects:
                    Page.objects.bulk_create(page_objects, batch_size=100)

                # Catalog captured APIs
                if api_logs_data:
                    save_api_endpoints(app, api_logs_data)

                # Finalize app status
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
                    "source": app.discovery_source,
                    "apis_cataloged": len(api_logs_data)
                }
                task_record.completed_at = timezone.now()
                task_record.save()

        run_in_thread(save_discovered_pages)

    except TaskCancelled:
        logger.info(f"Discovery task {task_id} cancelled by user.")
        def handle_discovery_cancelled():
            # Reset app to IDLE so user can restart discovery
            if Application.objects.filter(id=app_id).exists():
                app.status = 'IDLE'
                app.save(update_fields=['status'])
            task_record.status = 'failed'
            task_record.error = 'Stopped by user.'
            task_record.completed_at = timezone.now()
            task_record.save()
            clear_stop_flag(task_id)
        run_in_thread(handle_discovery_cancelled)
        return {"status": "CANCELLED", "message": "Discovery stopped by user."}

    except Exception as e:
        logger.error(f"Failed to save pages to DB: {e}")
        def handle_db_error():
            if Application.objects.filter(id=app_id).exists():
                app.status = 'FAILED'
                app.save(update_fields=['status'])
            task_record.status = 'failed'
            task_record.error = str(e)
            task_record.completed_at = timezone.now()
            task_record.save()
            clear_stop_flag(task_id)
        run_in_thread(handle_db_error)
        return {"status": "FAILED", "error": str(e)}

    clear_stop_flag(task_id)
    logger.info(f"Discovery completed for app {app.url}")
    return {
        "status": "SUCCESS",
        "pages_discovered": len(pages_data),
        "source": app.discovery_source
    }
