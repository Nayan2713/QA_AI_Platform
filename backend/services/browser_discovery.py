import logging
import json
import asyncio
import re
import time
import requests
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

class BrowserDiscoveryService:
    def __init__(self, max_pages=100):
        self.max_pages = max_pages
        self.discovered_pages = {}
        self.visited_urls = set()
        self.login_successful = None
        self.login_error_message = None
        self.dom_fingerprints = set()

    def is_same_domain(self, url, base_url, login_url=None):
        netloc1 = urlparse(url).netloc.lower()
        netloc2 = urlparse(base_url).netloc.lower()
        if netloc1 == netloc2:
            return True
        if netloc1.endswith('.' + netloc2) or netloc2.endswith('.' + netloc1):
            return True
        if login_url:
            netloc3 = urlparse(login_url).netloc.lower()
            if netloc1 == netloc3 or netloc1.endswith('.' + netloc3) or netloc3.endswith('.' + netloc1):
                return True
        return False

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
            
            username_selectors = [
                "input[name='username']", "input[name='email']", "input[id='username']", 
                "input[id='email']", "input[type='email']", "input[type='text']"
            ]
            password_selectors = [
                "input[type='password']", "input[name='password']", "input[id='password']"
            ]
            submit_selectors = [
                "button[type='submit']", "input[type='submit']", "button:has-text('Login')", 
                "button:has-text('Sign In')", "button:has-text('Log In')"
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
                    self.login_error_message = f"Login failed heuristic: browser stayed on login URL '{current_url}' and password field is still visible."
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
                buttons = await ctx.locator("button, input[type='button'], input[type='submit'], a.btn, a.button, [role='button'], [onclick]").all()
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
                    logger.info(f"OpenAPI endpoints discovered: {target_url}")
                    break
            except Exception:
                continue
        return parsed_apis

    async def discover(self, start_url, login_url=None, username=None, password=None, storage_state=None, on_progress=None):
        """
        High-performance concurrent async page crawler sharing session contexts.
        """
        logger.info(f"Starting browser discovery for URL: {start_url}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            context_kwargs = {
                "viewport": {"width": 1280, "height": 720},
                "ignore_https_errors": True
            }
            if storage_state and not (login_url and username and password):
                try:
                    context_kwargs['storage_state'] = json.loads(storage_state) if isinstance(storage_state, str) else storage_state
                except Exception as parse_err:
                    logger.error(f"Failed parsing storage state: {parse_err}")
            
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()
            
            # API logs holder
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
                    resource_type = response.request.resource_type
                    if resource_type in ['xhr', 'fetch']:
                        start_time = request_timestamps.get(response.url)
                        latency = int((time.time() - start_time) * 1000) if start_time else 0

                        body_text = ""
                        try:
                            content_type = response.headers.get("content-type", "").lower()
                            if any(t in content_type for t in ["json", "text", "javascript", "xml"]):
                                raw_bytes = await response.body()
                                if raw_bytes.startswith(b'\x1f\x8b'):
                                    import gzip
                                    try:
                                        raw_bytes = gzip.decompress(raw_bytes)
                                    except Exception:
                                        pass
                                body_text = raw_bytes.decode('utf-8', errors='replace')
                        except Exception:
                            pass

                        auth_type = None
                        headers = response.request.headers
                        if 'authorization' in headers:
                            auth_type = 'bearer' if 'bearer' in headers['authorization'].lower() else 'custom'
                        elif 'cookie' in headers:
                            auth_type = 'cookie'

                        request_body = response.request.post_data or ""

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
            
            # 1. Pre-login pass
            logged_in = False
            post_login_url = None
            if login_url and username and password:
                await self.perform_login(page, login_url, username, password)
                if self.login_successful:
                    logged_in = True
                    post_login_url = page.url
                    logger.info(f"Pre-login step finished successfully. Post-login URL: {post_login_url}")
                else:
                    logger.warning(f"Pre-login step failed: {self.login_error_message}")
            
            pages_list = []
            to_visit = []
            
            # Extract links from post-login URL first if logged in
            if logged_in and post_login_url:
                try:
                    logger.info(f"Booting queue from post-login landing URL: {post_login_url}")
                    title = await page.title()
                    forms = await self.extract_forms(page)
                    buttons = await self.extract_buttons(page)
                    
                    pages_list.append({
                        "url": post_login_url,
                        "title": title,
                        "forms": forms,
                        "buttons": buttons,
                        "page_type": "dashboard"
                    })
                    
                    links = await page.locator("a").all()
                    for link in links:
                        try:
                            href = await link.get_attribute("href")
                            if href:
                                abs_url = urljoin(post_login_url, href)
                                norm_url = abs_url.split('#')[0].split('?')[0]
                                if self.is_same_domain(norm_url, start_url, login_url):
                                    to_visit.append(norm_url)
                        except Exception:
                            continue
                except Exception as post_login_err:
                    logger.error(f"Failed extracting from post-login URL: {post_login_err}")

            # Also scan start URL (public page)
            if not pages_list or (start_url.split('#')[0].split('?')[0] != page.url.split('#')[0].split('?')[0]):
                try:
                    logger.info(f"Navigating to start URL: {start_url}")
                    await page.goto(start_url, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(1000)
                    
                    title = await page.title()
                    forms = await self.extract_forms(page)
                    buttons = await self.extract_buttons(page)
                    
                    pages_list.append({
                        "url": start_url,
                        "title": title,
                        "forms": forms,
                        "buttons": buttons,
                        "page_type": "home"
                    })
                    
                    links = await page.locator("a").all()
                    for link in links:
                        try:
                            href = await link.get_attribute("href")
                            if href:
                                abs_url = urljoin(start_url, href)
                                norm_url = abs_url.split('#')[0].split('?')[0]
                                if self.is_same_domain(norm_url, start_url, login_url):
                                    to_visit.append(norm_url)
                        except Exception:
                            continue
                except Exception as e:
                    logger.error(f"Failed loading start URL: {e}")
                    
            # Close original page to clean up context before workers
            await page.close()
            
            # 2. Run 3 Parallel workers
            to_visit_queue = asyncio.Queue()
            for url in to_visit:
                await to_visit_queue.put(url)
                
            visited_urls = self.visited_urls
            visited_urls.add(start_url)
            if login_url:
                visited_urls.add(login_url)
                
            async def crawl_worker(worker_id):
                logger.info(f"Starting crawl worker {worker_id}")
                worker_page = await context.new_page()
                worker_page.on("request", capture_network_request)
                worker_page.on("response", capture_network_api)
                
                while not to_visit_queue.empty() and len(pages_list) < self.max_pages:
                    try:
                        current_url = await asyncio.wait_for(to_visit_queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        break
                        
                    if current_url in visited_urls:
                        to_visit_queue.task_done()
                        continue
                        
                    visited_urls.add(current_url)
                    logger.info(f"Worker {worker_id} visiting: {current_url}")
                    
                    if on_progress:
                        try:
                            on_progress(current_url, len(pages_list))
                        except Exception:
                            pass
                            
                    try:
                        await worker_page.goto(current_url, wait_until="domcontentloaded", timeout=12000)
                        await worker_page.wait_for_timeout(800)
                        
                        # Scroll to trigger lazy elements
                        await worker_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await worker_page.wait_for_timeout(400)
                        
                        fingerprint = await self.get_dom_fingerprint(worker_page)
                        norm_path = urlparse(current_url).path
                        norm_path_pattern = re.sub(r'\d+', ':id', norm_path)
                        fingerprint_key = f"{norm_path_pattern}-{fingerprint}"
                        
                        if fingerprint_key in self.dom_fingerprints:
                            to_visit_queue.task_done()
                            continue
                        self.dom_fingerprints.add(fingerprint_key)
                        
                        title = await worker_page.title()
                        forms = await self.extract_forms(worker_page)
                        buttons = await self.extract_buttons(worker_page)
                        
                        pages_list.append({
                            "url": current_url,
                            "title": title,
                            "forms": forms,
                            "buttons": buttons,
                            "page_type": "dashboard" if any(kw in current_url.lower() for kw in ["dashboard", "admin", "settings", "profile"]) else "general"
                        })
                        
                        # Enqueue new links
                        links = await worker_page.locator("a").all()
                        for link in links:
                            try:
                                href = await link.get_attribute("href")
                                if href:
                                    abs_url = urljoin(current_url, href)
                                    norm_url = abs_url.split('#')[0].split('?')[0]
                                    if (self.is_same_domain(norm_url, start_url, login_url) and 
                                            norm_url not in visited_urls):
                                        await to_visit_queue.put(norm_url)
                            except Exception:
                                continue
                                
                        # Proactive interaction: click tabs, menus, settings buttons to trigger dynamic AJAX
                        interactive_elements = await worker_page.locator("button, [role='tab'], .tab, .menu-item, .nav-link, a[role='button']").all()
                        click_count = 0
                        for el in interactive_elements:
                            if click_count >= 15:
                                break
                            try:
                                if await el.is_visible() and await el.is_enabled():
                                    text = (await el.inner_text() or "").strip().lower()
                                    if any(logout_kw in text for logout_kw in ["logout", "log out", "signout", "sign out", "exit", "delete", "clear"]):
                                        continue
                                    
                                    await el.click(timeout=1500, force=True)
                                    click_count += 1
                                    await worker_page.wait_for_timeout(800)
                                    
                                    new_url = worker_page.url
                                    norm_new = new_url.split('#')[0].split('?')[0]
                                    if norm_new != current_url.split('#')[0].split('?')[0]:
                                        if (self.is_same_domain(norm_new, start_url, login_url) and 
                                                norm_new not in visited_urls):
                                            logger.info(f"Worker {worker_id} found new route via interactive click: {norm_new}")
                                            await to_visit_queue.put(norm_new)
                                        
                                        # Navigate back to original URL so we can continue clicking other menu items
                                        await worker_page.goto(current_url, wait_until="domcontentloaded", timeout=12000)
                                        await worker_page.wait_for_timeout(500)
                            except Exception:
                                continue
                                
                    except Exception as e:
                        logger.error(f"Worker {worker_id} failed on {current_url}: {e}")
                    finally:
                        to_visit_queue.task_done()
                        
                await worker_page.close()
                logger.info(f"Worker {worker_id} closed.")

            workers = [crawl_worker(i) for i in range(3)]
            await asyncio.gather(*workers)
            
            # Check OpenAPI schema Swagger
            openapi_apis = await self.discover_openapi(start_url)
            if openapi_apis:
                async with api_logs_lock:
                    api_logs.extend(openapi_apis)
            
            captured_storage = None
            try:
                if self.login_successful or logged_in:
                    captured_storage = json.dumps(await context.storage_state())
            except Exception as st_err:
                logger.error(f"Failed extracting storage state: {st_err}")
                
            await browser.close()
            
            return {
                "pages": pages_list,
                "login_successful": self.login_successful or logged_in,
                "login_error": self.login_error_message,
                "storage_state": captured_storage,
                "api_logs": api_logs
            }
