import logging
import os
import json
import asyncio
import re
import time
import requests
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class BrowserDiscoveryService:
    def __init__(self, max_pages=100, model_choice=None, use_llm=False):
        self.max_pages = max_pages
        self.model_choice = model_choice
        self.use_llm = use_llm
        self.discovered_pages = {}
        self.visited_urls = set()
        self.login_successful = None
        self.login_error_message = None
        self.dom_fingerprints = set()

    def is_same_domain(self, url, base_url, login_url=None):
        host1 = urlparse(url).hostname or ""
        host2 = urlparse(base_url).hostname or ""
        host1 = host1.lower()
        host2 = host2.lower()
        if host1 == host2:
            return True
        if host1.endswith('.' + host2) or host2.endswith('.' + host1):
            return True
        if login_url:
            host3 = urlparse(login_url).hostname or ""
            host3 = host3.lower()
            if host1 == host3 or host1.endswith('.' + host3) or host3.endswith('.' + host1):
                return True
        return False

    def get_path_pattern(self, url):
        try:
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
            return '/'.join(new_segments)
        except Exception:
            return url

    async def perform_login(self, page, login_url, username, password):
        """
        Navigates to the login page, identifies common username/password fields,
        fills them, and clicks submit.
        """
        logger.info(f"Attempting login at {login_url}")
        try:
            try:
                await page.goto(login_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(1000)
            except Exception as goto_err:
                logger.warning(f"Navigation to login page had an issue/timeout: {goto_err}. Trying to proceed anyway...")

            # Wait for common login elements to render before querying them
            try:
                await page.wait_for_selector("input[type='password'], input[name='password']", state="visible", timeout=6000)
            except Exception:
                pass

            username_selectors = [
                "input[name='username']", "input[name='email']", "input[name='user']",
                "input[name='login']", "input[name='identifier']",
                "input[id='username']", "input[id='email']", "input[id='user']",
                "input[id='login']", "input[id='identifier']",
                "input[type='email']",
                "input[autocomplete='email']", "input[autocomplete='username']",
                "input[placeholder*='email' i]", "input[placeholder*='username' i]",
                "input[data-testid*='email' i]", "input[data-testid*='user' i]",
                "input[type='text']"
            ]
            password_selectors = [
                "input[type='password']",
                "input[name='password']", "input[name='pass']", "input[name='passwd']",
                "input[id='password']", "input[id='pass']",
                "input[autocomplete='current-password']",
                "input[placeholder*='password' i]",
                "input[data-testid*='password' i]"
            ]
            submit_selectors = [
                "button[type='submit']", "input[type='submit']",
                "button:has-text('Login')", "button:has-text('Log In')",
                "button:has-text('Sign In')", "button:has-text('Sign in')",
                "button:has-text('Continue')", "button:has-text('Next')",
                "button:has-text('Submit')", "button:has-text('Access')",
                "[data-testid*='login' i]", "[data-testid*='submit' i]"
            ]

            user_el = None
            for sel in username_selectors:
                try:
                    if await page.locator(sel).first.is_visible():
                        user_el = page.locator(sel).first
                        break
                except Exception:
                    continue

            pass_el = None
            for sel in password_selectors:
                try:
                    if await page.locator(sel).first.is_visible():
                        pass_el = page.locator(sel).first
                        break
                except Exception:
                    continue

            if user_el and pass_el:
                await user_el.fill(username)
                await pass_el.fill(password)
                logger.info("Credentials filled in.")

                submitted = False
                for sel in submit_selectors:
                    try:
                        if await page.locator(sel).first.is_visible():
                            await page.locator(sel).first.click()
                            submitted = True
                            logger.info(f"Clicked login button using selector: {sel}")
                            break
                    except Exception:
                        continue

                if not submitted:
                    await pass_el.press("Enter")
                    logger.info("Pressed Enter as submit fallback.")

                await page.wait_for_timeout(3000)

                still_has_password = False
                for sel in password_selectors:
                    try:
                        if await page.locator(sel).first.is_visible():
                            still_has_password = True
                            break
                    except Exception:
                        continue

                current_url = page.url
                url_changed = (current_url.split('?')[0].rstrip('/') != login_url.split('?')[0].rstrip('/'))

                if url_changed or not still_has_password:
                    self.login_successful = True
                    logger.info(f"Login successful heuristic passed. Current URL: {current_url}")
                else:
                    self.login_successful = False
                    self.login_error_message = (
                        f"Login failed heuristic: browser stayed on login URL "
                        f"'{current_url}' and password field is still visible."
                    )
                    logger.warning(f"Login failed heuristic triggered. Still on login URL: {current_url}")
            else:
                self.login_error_message = "Login failed: could not find username/email and password fields."
                logger.warning("Could not identify login fields.")
                self.login_successful = False
        except Exception as e:
            self.login_error_message = f"Login failed exception: {str(e)}"
            logger.error(f"Login failed: {e}")
            self.login_successful = False

    async def get_dom_fingerprint(self, page):
        """
        Generates a tag-hierarchy signature of the DOM to skip duplicate structures.
        """
        try:
            fingerprint = await page.evaluate("""() => {
                const tags = [];
                const walk = (node, depth = 0) => {
                    if (!node || depth > 6) return;
                    const tag = node.tagName?.toLowerCase();
                    if (tag && !['script', 'style', 'noscript', 'svg', 'path'].includes(tag)) {
                        tags.push(tag);
                        if (node.children) {
                            for (const child of node.children) {
                                walk(child, depth + 1);
                            }
                        }
                    }
                };
                walk(document.body);
                return tags.join('-');
            }""")
            return fingerprint
        except Exception:
            return ""

    async def extract_forms(self, page):
        forms_data = []
        try:
            contexts = [page]
            for frame in page.frames:
                if frame.url and not frame.url.startswith("javascript:"):
                    contexts.append(frame)

            for ctx in contexts:
                forms = await ctx.locator("form").all()
                for idx, form in enumerate(forms):
                    try:
                        form_id = await form.get_attribute("id") or await form.get_attribute("name") or f"form_{idx}"
                        action = await form.get_attribute("action") or ""
                        method = await form.get_attribute("method") or "get"

                        fields = []
                        inputs = await form.locator("input, select, textarea").all()
                        for inp in inputs:
                            inp_type = await inp.get_attribute("type") or "text"
                            if inp_type.lower() == "hidden":
                                continue
                            inp_name = await inp.get_attribute("name")
                            inp_id = await inp.get_attribute("id") or ""

                            if inp_name or inp_id:
                                fields.append({
                                    "name": inp_name or "",
                                    "type": inp_type,
                                    "id": inp_id or ""
                                })
                        forms_data.append({
                            "id": form_id,
                            "fields": fields,
                            "action": action,
                            "method": method
                        })
                    except Exception:
                        continue

                standalone_fields = []
                all_inputs = await ctx.locator("input, select, textarea").all()
                for inp in all_inputs:
                    try:
                        is_inside_form = await inp.evaluate("el => el.closest('form') !== null")
                        if is_inside_form:
                            continue
                        inp_type = await inp.get_attribute("type") or "text"
                        if inp_type.lower() in ["hidden", "submit", "button", "image"]:
                            continue
                        inp_name = await inp.get_attribute("name")
                        inp_id = await inp.get_attribute("id") or ""
                        if inp_name or inp_id:
                            standalone_fields.append({
                                "name": inp_name or "",
                                "type": inp_type,
                                "id": inp_id or ""
                            })
                    except Exception:
                        continue
                if standalone_fields:
                    forms_data.append({
                        "id": "standalone_fields",
                        "fields": standalone_fields,
                        "action": "",
                        "method": "standalone"
                    })
        except Exception as e:
            logger.error(f"Error extracting forms: {e}")
        return forms_data

    async def extract_buttons(self, page):
        buttons_data = []
        try:
            contexts = [page]
            for frame in page.frames:
                if frame.url and not frame.url.startswith("javascript:"):
                    contexts.append(frame)

            for ctx in contexts:
                buttons = await ctx.locator(
                    "button, input[type='button'], input[type='submit'], a.btn, a.button, [role='button'], [onclick]"
                ).all()
                for idx, btn in enumerate(buttons):
                    try:
                        if not await btn.is_visible():
                            continue
                        text = (await btn.inner_text()).strip() or await btn.get_attribute("value") or ""
                        if not text:
                            text = await btn.get_attribute("title") or f"Button {idx}"

                        selector = await btn.evaluate("""el => {
                            const getSelector = (element) => {
                                if (element.id) {
                                    try {
                                        if (document.querySelectorAll('#' + CSS.escape(element.id)).length === 1) {
                                            return '#' + element.id;
                                        }
                                    } catch(e) {}
                                }
                                const name = element.getAttribute('name');
                                if (name) {
                                    try {
                                        const tag = element.tagName.toLowerCase();
                                        if (document.querySelectorAll(`${tag}[name="${CSS.escape(name)}"]`).length === 1) {
                                            return `${tag}[name="${name}"]`;
                                        }
                                    } catch(e) {}
                                }
                                const getXPath = (el) => {
                                    if (el.id) return `//*[@id="${el.id}"]`;
                                    if (el === document.body) return '/html/body';
                                    let ix = 0;
                                    const siblings = el.parentNode.childNodes;
                                    for (let i = 0; i < siblings.length; i++) {
                                        const sibling = siblings[i];
                                        if (sibling === el) {
                                            return getXPath(el.parentNode) + '/' + el.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                                        }
                                        if (sibling.nodeType === 1 && sibling.tagName === el.tagName) {
                                            ix++;
                                        }
                                    }
                                    return '';
                                };
                                return 'xpath=' + getXPath(element);
                            };
                            return getSelector(el);
                        }""")
                        buttons_data.append({
                            "text": text,
                            "selector": selector
                        })
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Error extracting buttons: {e}")
        return buttons_data

    async def discover_openapi(self, base_url):
        common_paths = [
            "/swagger.json", "/openapi.json", "/api/docs", "/v2/api-docs",
            "/api/swagger.json", "/api/v1/swagger.json", "/api/v2/swagger.json",
            "/api/openapi.json", "/api/v1/openapi.json"
        ]
        parsed_apis = []
        for path in common_paths:
            target_url = urljoin(base_url, path)
            try:
                resp = await asyncio.to_thread(requests.get, target_url, timeout=2.0)
                if resp.status_code == 200:
                    data = resp.json()
                    paths = data.get("paths", {})
                    for api_path, methods in paths.items():
                        for method, val in methods.items():
                            if method.upper() in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']:
                                parsed_apis.append({
                                    "method": method.upper(),
                                    "url": urljoin(base_url, api_path),
                                    "status": 200,
                                    "body": "{}",
                                    "request_body": "{}",
                                    "auth_type": "none"
                                })
                    logger.info(f"OpenAPI endpoints discovered at: {target_url}")
                    break
            except Exception:
                continue
        return parsed_apis

    async def _summarize_page_async(self, page_info):
        try:
            # Skip if there are no forms and buttons on the page
            if not page_info.get("forms") and not page_info.get("buttons"):
                page_info["ai_summary"] = "Empty page with no interactive elements."
                return

            logger.info(f"Triggering background AI summarization for {page_info['url']}...")
            from services.llm_service import LLMService
            llm = LLMService(model_choice=self.model_choice)
            loop = asyncio.get_running_loop()
            summary = await loop.run_in_executor(None, llm.summarize_page, page_info)
            if summary:
                page_info["ai_summary"] = summary
                logger.info(f"AI Summary generated for {page_info['url']}")
            else:
                page_info["ai_summary"] = ""
                logger.warning(f"Failed to generate AI summary for {page_info['url']}")
        except Exception as e:
            logger.error(f"Error in background AI summarization for {page_info['url']}: {e}")

    async def discover(self, start_url, login_url=None, username=None, password=None, storage_state=None, on_progress=None):
        """
        High-performance concurrent async page crawler sharing session contexts.

        Fixes applied vs original:
          1. Storage state is ALWAYS loaded when available, even when credentials
             are also provided — so re-runs reuse the saved session instead of
             logging in from scratch every time.
          2. Session validity is checked before attempting a fresh login, so if
             the stored cookies are still good we skip the login step entirely.
          3. After a successful login the crawler queues links from the
             post-login landing page and does NOT re-navigate to start_url
             (which on many apps redirects back to the login wall).
          4. visited_urls is protected by an asyncio.Lock so the 3 concurrent
             workers cannot visit the same URL twice due to a race condition.
        """
        logger.info(f"Starting browser discovery for URL: {start_url}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"]
            )

            context_kwargs = {
                "viewport": {"width": 1280, "height": 720},
                "ignore_https_errors": True
            }

            # FIX 1: Always load storage_state when available — even when
            # credentials are provided.  We will still re-login below if the
            # stored session turns out to be expired.
            if storage_state:
                try:
                    parsed_state = (
                        json.loads(storage_state)
                        if isinstance(storage_state, str)
                        else storage_state
                    )
                    context_kwargs['storage_state'] = parsed_state
                    logger.info("Loaded pre-existing storage state into browser context.")
                except Exception as parse_err:
                    logger.error(f"Failed parsing storage state: {parse_err}")

            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()
            page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))

            # Shared API log state
            api_logs = []
            request_timestamps = {}
            api_logs_lock = asyncio.Lock()

            async def capture_network_request(request):
                try:
                    if request.resource_type in ['xhr', 'fetch']:
                        request_timestamps[request.url] = time.time()
                except Exception:
                    pass

            async def capture_network_api(response):
                try:
                    url = response.url
                    # 1. Third-party domain check
                    if not self.is_same_domain(url, start_url, login_url):
                        return

                    # 2. Static asset suffix check
                    parsed_url = urlparse(url)
                    path_lower = parsed_url.path.lower()
                    static_extensions = (
                        ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", 
                        ".ico", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", 
                        ".wav", ".json", ".map", ".wasm"
                    )
                    if path_lower.endswith(static_extensions):
                        return

                    # 3. Static/asset host/path keyword check
                    url_lower = url.lower()
                    noise_keywords = [
                        "web-assets", "/_next/", "/static/", "/assets/", "cdn-cgi", "/cdn/", 
                        "fonts.", "analytics", "/rum", "/beacon", "gtag", "googletagmanager", 
                        "doubleclick", "segment.", "sentry", "hotjar"
                    ]
                    if any(kw in url_lower for kw in noise_keywords):
                        return

                    resource_type = response.request.resource_type
                    if resource_type in ['xhr', 'fetch']:
                        start_time = request_timestamps.get(response.url)
                        latency = int((time.time() - start_time) * 1000) if start_time else 0

                        body_text = ""
                        try:
                            raw_bytes = await asyncio.wait_for(response.body(), timeout=2.0)
                            if raw_bytes:
                                # FIX: Always decompress gzip BEFORE checking content-type.
                                # Original code only decompressed when content-type contained
                                # json/text/xml — but many servers (digiprima.com included)
                                # send gzip-compressed responses with other or missing
                                # content-type headers, causing the crash:
                                #   'utf-8' codec can't decode byte 0x8b in position 1'
                                # 0x1f 0x8b is the gzip magic header.
                                if raw_bytes[:2] == b'\x1f\x8b':
                                    import gzip
                                    try:
                                        raw_bytes = gzip.decompress(raw_bytes)
                                    except Exception:
                                        raw_bytes = b""

                                # Only store text-based content as body_text
                                content_type = response.headers.get("content-type", "").lower()
                                is_text = (
                                    any(t in content_type for t in
                                        ["json", "text", "javascript", "xml", "html", "form"])
                                    or not content_type
                                )
                                if is_text and raw_bytes:
                                    body_text = raw_bytes.decode('utf-8', errors='replace')
                        except Exception:
                            pass

                        auth_type = None
                        headers = response.request.headers
                        if 'authorization' in headers:
                            auth_type = 'bearer' if 'bearer' in headers['authorization'].lower() else 'custom'
                        elif 'cookie' in headers:
                            auth_type = 'cookie'

                        request_body = ""
                        try:
                            post_bytes = response.request.post_data_bytes
                            if post_bytes:
                                if post_bytes[:2] == b'\x1f\x8b':
                                    import gzip
                                    try:
                                        post_bytes = gzip.decompress(post_bytes)
                                    except Exception:
                                        pass
                                request_body = post_bytes.decode('utf-8', errors='replace')
                        except Exception:
                            try:
                                request_body = response.request.post_data or ""
                            except Exception:
                                request_body = ""

                        page_url = ""
                        try:
                            page_url = response.frame.url
                        except Exception:
                            pass

                        async with api_logs_lock:
                            api_logs.append({
                                "method": response.request.method,
                                "url": response.url,
                                "status": response.status,
                                "body": body_text,
                                "latency": latency,
                                "auth_type": auth_type,
                                "request_body": request_body,
                                "page_url": page_url
                            })
                except Exception as net_err:
                    logger.error(f"Error logging response: {net_err}")

            page.on("request", capture_network_request)
            page.on("response", capture_network_api)

            # ------------------------------------------------------------------
            # FIX 2: Check if the stored session is still valid BEFORE doing a
            # fresh login.  Navigate to start_url; if we land somewhere other
            # than the login page the session is live and we skip re-login.
            # ------------------------------------------------------------------
            logged_in = False
            post_login_url = None

            if login_url and username and password:
                already_logged_in = False

                if storage_state:
                    try:
                        logger.info("Verifying if stored session is still valid...")
                        await page.goto(start_url, wait_until="domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(1500)

                        current = page.url.split('?')[0].rstrip('/')
                        login_clean = login_url.split('?')[0].rstrip('/')

                        # Check: not redirected back to login AND no password field visible
                        still_on_login = (current == login_clean)
                        has_password = False
                        for sel in ["input[type='password']", "input[name='password']"]:
                            try:
                                if await page.locator(sel).first.is_visible():
                                    has_password = True
                                    break
                            except Exception:
                                pass

                        if not still_on_login and not has_password:
                            already_logged_in = True
                            logged_in = True
                            post_login_url = page.url
                            self.login_successful = True
                            logger.info(f"Stored session is valid — skipping login. Landing: {post_login_url}")
                    except Exception as check_err:
                        logger.warning(f"Session validity check failed: {check_err}")

                if not already_logged_in:
                    logger.info(f"Performing fresh login at {login_url}")
                    await self.perform_login(page, login_url, username, password)
                    if self.login_successful:
                        logged_in = True
                        post_login_url = page.url
                        logger.info(f"Fresh login succeeded. Post-login URL: {post_login_url}")
                    else:
                        logger.warning(f"Login failed: {self.login_error_message}")

            pages_list = []
            to_visit = []

            # ------------------------------------------------------------------
            # FIX 3: After a successful login, extract links from the
            # post-login landing page ONLY.  Do NOT re-navigate to start_url
            # because on most apps start_url redirects unauthenticated users to
            # the login wall, wiping the authenticated session from the queue.
            # ------------------------------------------------------------------
            if logged_in and post_login_url:
                try:
                    logger.info(f"Extracting links from post-login landing page: {post_login_url}")
                    links = await page.locator("a").all()
                    for link in links:
                        try:
                            href = await link.get_attribute("href")
                            if href:
                                abs_url = urljoin(post_login_url, href)
                                norm_url = abs_url.split('#')[0].split('?')[0]
                                if (
                                    self.is_same_domain(norm_url, start_url, login_url)
                                    and norm_url != login_url
                                ):
                                    to_visit.append(norm_url)
                        except Exception:
                            continue
                except Exception as post_login_err:
                    logger.error(f"Failed extracting from post-login page: {post_login_err}")

            else:
                # No auth — start crawl from the public start_url
                try:
                    logger.info(f"No authentication — navigating to start URL: {start_url}")
                    await page.goto(start_url, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(1000)

                    links = await page.locator("a").all()
                    for link in links:
                        try:
                            href = await link.get_attribute("href")
                            if href:
                                abs_url = urljoin(start_url, href)
                                norm_url = abs_url.split('#')[0].split('?')[0]
                                if self.is_same_domain(norm_url, start_url, login_url) and norm_url != login_url:
                                    to_visit.append(norm_url)
                        except Exception:
                            continue
                except Exception as e:
                    logger.error(f"Failed loading start URL: {e}")

            await page.close()

            to_visit_queue = asyncio.Queue()
            initial_url = post_login_url if (logged_in and post_login_url) else start_url
            
            # Workers start directly on initial_url so they run click events and extract all forms/menus
            await to_visit_queue.put((initial_url, "start_url"))
            
            queued_patterns = {self.get_path_pattern(initial_url)}
            for url in to_visit:
                if url != initial_url:
                    pattern = self.get_path_pattern(url)
                    if pattern not in queued_patterns:
                        queued_patterns.add(pattern)
                        await to_visit_queue.put((url, post_login_url if logged_in else start_url))

            visited_urls = self.visited_urls
            visited_patterns = set()
            visited_lock = asyncio.Lock()       # NEW: lock for safe concurrent access
            ai_tasks = []                       # NEW: track background AI summarization tasks
            ai_semaphore = asyncio.Semaphore(2) # Limit local LLM calls to 2 concurrent
            
            if login_url:
                visited_urls.add(login_url)
                visited_patterns.add(self.get_path_pattern(login_url))

            active_workers = 0
            active_workers_lock = asyncio.Lock()

            async def crawl_worker(worker_id):
                nonlocal active_workers
                logger.info(f"Starting crawl worker {worker_id}")
                worker_page = await context.new_page()
                worker_page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
                worker_page.on("request", capture_network_request)
                worker_page.on("response", capture_network_api)

                while len(pages_list) < self.max_pages:
                    try:
                        queue_item = await asyncio.wait_for(to_visit_queue.get(), timeout=1.0)
                        current_url, parent_url = queue_item
                    except asyncio.TimeoutError:
                        async with active_workers_lock:
                            if active_workers == 0:
                                break
                        continue

                    # FIX 4: atomic check-and-mark inside the lock
                    async with visited_lock:
                        pattern = self.get_path_pattern(current_url)
                        if (current_url in visited_urls) or (pattern in visited_patterns):
                            to_visit_queue.task_done()
                            continue
                        visited_urls.add(current_url)
                        visited_patterns.add(pattern)

                    async with active_workers_lock:
                        active_workers += 1

                    logger.info(f"Worker {worker_id} visiting: {current_url} (discovered from {parent_url})")

                    if on_progress:
                        try:
                            on_progress(current_url, len(pages_list))
                        except Exception:
                            pass

                    try:
                        await worker_page.goto(current_url, wait_until="domcontentloaded", timeout=20000)
                        await worker_page.wait_for_timeout(800)

                        # Scroll to trigger lazy-loaded elements
                        await worker_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await worker_page.wait_for_timeout(400)

                        try:
                            await worker_page.wait_for_load_state("networkidle", timeout=1500)
                        except Exception:
                            pass

                        title = await worker_page.title()
                        norm_path = urlparse(current_url).path
                        norm_path_pattern = re.sub(r'\d+', ':id', norm_path)
                        title_key = (title or '')[:40].strip().lower()
                        try:
                            form_count = await worker_page.locator('form').count()
                        except Exception:
                            form_count = 0
                        fingerprint_key = f"{norm_path_pattern}|{title_key}|{form_count}"

                        if fingerprint_key in self.dom_fingerprints:
                            continue
                        self.dom_fingerprints.add(fingerprint_key)

                        forms = await self.extract_forms(worker_page)
                        buttons = await self.extract_buttons(worker_page)

                        page_type = "general"
                        url_lower = current_url.lower()
                        title_lower = title.lower() if title else ""
                        combined = url_lower + " " + title_lower
                        # FIX: check both URL and page title for better coverage
                        if any(kw in combined for kw in ["login", "sign-in", "signin", "log-in"]):
                            page_type = "login"
                        elif any(kw in combined for kw in ["register", "signup", "sign-up", "create account"]):
                            page_type = "signup"
                        elif any(kw in combined for kw in ["checkout", "payment", "billing", "cart"]):
                            page_type = "checkout"
                        elif any(kw in combined for kw in ["dashboard", "admin", "home", "main", "overview"]):
                            page_type = "dashboard"
                        elif any(kw in combined for kw in ["settings", "config", "preferences", "profile", "account"]):
                            page_type = "settings"
                        elif any(kw in combined for kw in ["report", "analytics", "stats", "metric"]):
                            page_type = "report"
                        elif any(kw in combined for kw in ["product", "item", "listing", "shop", "store"]):
                            page_type = "product"
                        elif any(kw in combined for kw in ["contact", "support", "help", "faq"]):
                            page_type = "contact"

                        page_info = {
                            "url": current_url,
                            "title": title,
                            "forms": forms,
                            "buttons": buttons,
                            "page_type": page_type,
                            "elements": {},
                            "workflows": [],
                            "ai_summary": ""
                        }
                        pages_list.append(page_info)

                        # Start background AI summarization in parallel
                        if self.use_llm:
                            async def summarize_with_sem(p_info):
                                async with ai_semaphore:
                                    await self._summarize_page_async(p_info)
                            ai_task = asyncio.create_task(summarize_with_sem(page_info))
                            ai_tasks.append(ai_task)
                        else:
                            page_info["ai_summary"] = ""

                        # Enqueue new links found on this page
                        links = await worker_page.locator("a").all()
                        for link in links:
                            try:
                                href = await link.get_attribute("href")
                                if href:
                                    abs_url = urljoin(current_url, href)
                                    norm_url = abs_url.split('#')[0].split('?')[0]
                                    if self.is_same_domain(norm_url, start_url, login_url):
                                        async with visited_lock:
                                            pattern = self.get_path_pattern(norm_url)
                                            already = (norm_url in visited_urls) or (pattern in visited_patterns)
                                        if not already:
                                            await to_visit_queue.put((norm_url, current_url))
                            except Exception:
                                continue

                        # Proactive interaction: click tabs/menus to trigger dynamic AJAX
                        interactive_elements = await worker_page.locator(
                            "button, [role='tab'], .tab, .menu-item, .nav-link, a[role='button']"
                        ).all()
                        click_count = 0
                        for el in interactive_elements:
                            if click_count >= 20:
                                break
                            try:
                                if await el.is_visible() and await el.is_enabled():
                                    text = (await el.inner_text() or "").strip().lower()
                                    if any(logout_kw in text for logout_kw in [
                                        "logout", "log out", "signout", "sign out", "exit", "delete", "clear"
                                    ]):
                                        continue

                                    await el.click(timeout=1500, force=True)
                                    click_count += 1
                                    await worker_page.wait_for_timeout(800)

                                    new_url = worker_page.url
                                    norm_new = new_url.split('#')[0].split('?')[0]
                                    if norm_new != current_url.split('#')[0].split('?')[0]:
                                        if self.is_same_domain(norm_new, start_url, login_url):
                                            async with visited_lock:
                                                pattern = self.get_path_pattern(norm_new)
                                                already = (norm_new in visited_urls) or (pattern in visited_patterns)
                                            if not already:
                                                logger.info(f"Worker {worker_id} found new route via click: {norm_new}")
                                                await to_visit_queue.put((norm_new, current_url))

                                        # Navigate back so we can click other menu items
                                        try:
                                            await worker_page.goto(current_url, wait_until="domcontentloaded", timeout=20000)
                                            await worker_page.wait_for_timeout(500)
                                        except Exception as nav_err:
                                            logger.warning(
                                                f"Worker {worker_id} failed to navigate back to {current_url} "
                                                f"after click navigation: {nav_err}. Aborting click interaction for this page."
                                            )
                                            break
                            except Exception:
                                continue

                    except Exception as e:
                        try:
                            final_url = worker_page.url
                        except Exception:
                            final_url = current_url

                        if final_url and not self.is_same_domain(final_url, start_url, login_url):
                            logger.warning(
                                f"Worker {worker_id} navigation to {current_url} (discovered from {parent_url}) "
                                f"was redirected to external domain: {final_url}. Skipping."
                            )
                        else:
                            logger.error(
                                f"Worker {worker_id} failed on {current_url} (discovered from {parent_url}): {e}"
                            )

                        # RECOVERY: if the page/browser died, rebuild it — otherwise every
                        # subsequent goto on this dead handle fails instantly and the worker
                        # burns through the whole queue doing nothing.
                        err_text = str(e).lower()
                        if "crash" in err_text or "closed" in err_text or "target" in err_text:
                            logger.warning(f"Worker {worker_id} page died — recreating it.")
                            try:
                                await worker_page.close()
                            except Exception:
                                pass
                            try:
                                worker_page = await context.new_page()
                                worker_page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
                                worker_page.on("request", capture_network_request)
                                worker_page.on("response", capture_network_api)
                                await asyncio.sleep(1)
                            except Exception as recreate_err:
                                logger.error(f"Worker {worker_id} could not recreate page: {recreate_err}. Exiting.")
                                async with active_workers_lock:
                                    active_workers -= 1
                                to_visit_queue.task_done()
                                return
                    finally:
                        async with active_workers_lock:
                            active_workers -= 1
                        to_visit_queue.task_done()

                await worker_page.close()
                logger.info(f"Worker {worker_id} finished and closed.")

            try:
                crawler_max_pages = int(os.environ.get("CRAWLER_MAX_PAGES", "2"))
            except ValueError:
                crawler_max_pages = 2
            logger.info(f"Spawning {crawler_max_pages} concurrent crawl workers (configured via CRAWLER_MAX_PAGES)")

            workers = [crawl_worker(i) for i in range(crawler_max_pages)]
            await asyncio.gather(*workers)

            # Discover OpenAPI/Swagger endpoints
            openapi_apis = await self.discover_openapi(start_url)
            if openapi_apis:
                async with api_logs_lock:
                    api_logs.extend(openapi_apis)

            # Wait for all background AI summarization tasks to complete before concluding discovery
            if ai_tasks:
                logger.info(f"Waiting for {len(ai_tasks)} background page summarization tasks to complete...")
                await asyncio.gather(*ai_tasks, return_exceptions=True)

            # Save final storage state (only if login was successful)
            captured_storage = None
            try:
                if self.login_successful or logged_in:
                    captured_storage = json.dumps(await context.storage_state())
                    logger.info("Captured final storage state after crawl.")
            except Exception as st_err:
                logger.error(f"Failed extracting storage state: {st_err}")

            await browser.close()

            logger.info(
                f"Discovery complete. Pages found: {len(pages_list)}, "
                f"API calls captured: {len(api_logs)}"
            )

            return {
                "pages": pages_list,
                "login_successful": self.login_successful or logged_in,
                "login_error": self.login_error_message,
                "storage_state": captured_storage,
                "api_logs": api_logs
            }