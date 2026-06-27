import logging
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

class BrowserDiscoveryService:
    def __init__(self, max_pages=10):
        self.max_pages = max_pages
        self.discovered_pages = {}
        self.visited_urls = set()
        self.login_successful = None
        self.login_error_message = None

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

    def perform_login(self, page, login_url, username, password):
        """
        Navigates to the login page, identifies common username/password fields,
        fills them, and clicks submit.
        """
        logger.info(f"Attempting login at {login_url}")
        try:
            try:
                page.goto(login_url, wait_until="domcontentloaded", timeout=20000)
                try:
                    page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass
            except Exception as goto_err:
                logger.warning(f"Navigation to login page had an issue/timeout: {goto_err}. Trying to proceed anyway...")
            
            # Common username field selectors
            username_selectors = [
                "input[name='username']", "input[name='email']", "input[id='username']", 
                "input[id='email']", "input[type='email']", "input[type='text']"
            ]
            # Common password field selectors
            password_selectors = [
                "input[type='password']", "input[name='password']", "input[id='password']"
            ]
            # Common submit buttons
            submit_selectors = [
                "button[type='submit']", "input[type='submit']", "button:has-text('Login')", 
                "button:has-text('Sign In')", "button:has-text('Log In')"
            ]

            # Try to find username input
            user_el = None
            for sel in username_selectors:
                try:
                    if page.locator(sel).first.is_visible():
                        user_el = page.locator(sel).first
                        break
                except Exception:
                    continue

            # Try to find password input
            pass_el = None
            for sel in password_selectors:
                try:
                    if page.locator(sel).first.is_visible():
                        pass_el = page.locator(sel).first
                        break
                except Exception:
                    continue

            if user_el and pass_el:
                user_el.fill(username)
                pass_el.fill(password)
                logger.info("Credentials filled in.")
                
                # Click submit
                submitted = False
                for sel in submit_selectors:
                    try:
                        if page.locator(sel).first.is_visible():
                            page.locator(sel).first.click()
                            submitted = True
                            logger.info(f"Clicked login button using selector: {sel}")
                            break
                    except Exception:
                        continue
                
                if not submitted:
                    # Fallback press Enter
                    pass_el.press("Enter")
                    logger.info("Pressed Enter as submit fallback.")

                page.wait_for_timeout(3000) # Wait a bit for transition
                
                # Heuristic check: URL changed or password input disappeared
                still_has_password = False
                for sel in password_selectors:
                    try:
                        if page.locator(sel).first.is_visible():
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
                self.login_error_message = "Login failed: could not find standard username/email and password fields on the login page."
                logger.warning("Could not identify login fields.")
                self.login_successful = False
        except Exception as e:
            self.login_error_message = f"Login failed exception: {str(e)}"
            logger.error(f"Login failed: {e}")
            self.login_successful = False

    def extract_forms(self, page):
        """
        Finds all forms on the current page and extracts fields, action, and method.
        Also finds standalone input elements outside forms and groups them as a virtual form.
        """
        forms_data = []
        try:
            # 1. Standard forms
            forms = page.locator("form").all()
            for idx, form in enumerate(forms):
                form_id = form.get_attribute("id") or form.get_attribute("name") or f"form_{idx}"
                action = form.get_attribute("action") or ""
                method = form.get_attribute("method") or "get"
                
                fields = []
                # Find inputs, selects, textareas inside this form
                inputs = form.locator("input, select, textarea").all()
                for inp in inputs:
                    inp_type = inp.get_attribute("type") or "text"
                    if inp_type.lower() == "hidden":
                        continue
                        
                    inp_name = inp.get_attribute("name")
                    inp_id = inp.get_attribute("id") or ""
                    
                    # Ignore buttons and hidden fields if not needed, but keep names/IDs for filling
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

            # 2. Standalone inputs (not inside any form tag)
            standalone_fields = []
            all_inputs = page.locator("input, select, textarea").all()
            for inp in all_inputs:
                try:
                    # Check if this input has a form ancestor in JS
                    is_inside_form = inp.evaluate("el => el.closest('form') !== null")
                    if is_inside_form:
                        continue
                        
                    inp_type = inp.get_attribute("type") or "text"
                    if inp_type.lower() in ["hidden", "submit", "button", "image"]:
                        continue
                        
                    inp_name = inp.get_attribute("name")
                    inp_id = inp.get_attribute("id") or ""
                    
                    if inp_name or inp_id:
                        standalone_fields.append({
                            "name": inp_name or "",
                            "type": inp_type,
                            "id": inp_id or ""
                        })
                except Exception as eval_err:
                    logger.debug(f"Error checking standalone input element: {eval_err}")
                    
            if standalone_fields:
                forms_data.append({
                    "id": "standalone_fields",
                    "fields": standalone_fields,
                    "action": "",
                    "method": "standalone"
                })
        except Exception as e:
            logger.error(f"Error extracting forms and standalone inputs: {e}")
        return forms_data

    def extract_buttons(self, page):
        """
        Finds buttons and interactive clickable elements (div buttons, custom links, etc.) on the page.
        """
        buttons_data = []
        try:
            buttons = page.locator("button, input[type='button'], input[type='submit'], a.btn, a.button, [role='button'], [onclick]").all()
            for idx, btn in enumerate(buttons):
                # Skip hidden elements
                if not btn.is_visible():
                    continue
                text = btn.inner_text().strip() or btn.get_attribute("value") or ""
                if not text:
                    text = btn.get_attribute("title") or f"Button {idx}"
                
                # Generate a unique and safe selector using browser-side JS
                selector = btn.evaluate("""el => {
                    const getSelector = (element) => {
                        // 1. Try ID (must be unique)
                        if (element.id) {
                            try {
                                if (document.querySelectorAll('#' + CSS.escape(element.id)).length === 1) {
                                    return '#' + element.id;
                                }
                            } catch(e) {}
                        }
                        // 2. Try Name (must be unique)
                        const name = element.getAttribute('name');
                        if (name) {
                            try {
                                const tag = element.tagName.toLowerCase();
                                if (document.querySelectorAll(`${tag}[name="${CSS.escape(name)}"]`).length === 1) {
                                    return `${tag}[name="${name}"]`;
                                }
                            } catch(e) {}
                        }
                        // 3. Fallback to unique XPath
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
        except Exception as e:
            logger.error(f"Error extracting buttons: {e}")
        return buttons_data


    def discover(self, start_url, login_url=None, username=None, password=None, storage_state=None, on_progress=None):
        """
        Performs the complete page discovery using Playwright.
        Registers API listeners early, handles session persistence, and returns
        discovered pages, storage state, and captured api logs.
        """
        logger.info(f"Starting browser discovery for URL: {start_url}")
        import json
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            context_kwargs = {}
            if storage_state:
                try:
                    context_kwargs['storage_state'] = json.loads(storage_state) if isinstance(storage_state, str) else storage_state
                    logger.info("Loaded pre-existing storage state for discovery context.")
                except Exception as parse_err:
                    logger.error(f"Failed to parse storage state JSON: {parse_err}")
            
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            
            # API Interception setup (before any navigation/login)
            api_logs = []
            request_timestamps = {}

            def capture_network_request(request):
                try:
                    if request.resource_type in ['xhr', 'fetch']:
                        import time
                        request_timestamps[request.url] = time.time()
                except Exception:
                    pass

            page.on("request", capture_network_request)

            def capture_network_api(response):
                try:
                    resource_type = response.request.resource_type
                    if resource_type in ['xhr', 'fetch']:
                        import time
                        start_time = request_timestamps.get(response.url)
                        latency = int((time.time() - start_time) * 1000) if start_time else 0

                        body_text = ""
                        try:
                            content_type = response.headers.get("content-type", "").lower()
                            if any(t in content_type for t in ["json", "text", "javascript", "xml"]):
                                body_text = response.text()
                        except Exception:
                            pass

                        # Detect auth type
                        auth_type = None
                        headers = response.request.headers
                        if 'authorization' in headers:
                            auth_type = 'bearer' if 'bearer' in headers['authorization'].lower() else 'custom'
                        elif 'cookie' in headers:
                            auth_type = 'cookie'

                        # Safely retrieve post_data as string or fallback to bytes details if not UTF-8
                        request_body = ""
                        try:
                            request_body = response.request.post_data or ""
                        except Exception:
                            try:
                                post_bytes = response.request.post_data_bytes
                                if post_bytes:
                                    request_body = f"<binary data: {len(post_bytes)} bytes>"
                            except Exception:
                                pass

                        api_logs.append({
                            "method": response.request.method,
                            "url": response.url,
                            "status": response.status,
                            "body": body_text,
                            "latency": latency,
                            "auth_type": auth_type,
                            "request_body": request_body
                        })
                except Exception as net_err:
                    logger.error(f"Error logging network response during crawl: {net_err}")

            page.on("response", capture_network_api)
            
            # Queue of links to visit
            to_visit = [start_url]
            pages_list = []
            
            # Optional login phase
            if login_url and username and password:
                already_logged_in = False
                if storage_state:
                    try:
                        logger.info("Verifying if existing session is valid...")
                        page.goto(start_url, wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(1000)
                        
                        # If we aren't on the login URL and don't see password fields, we are logged in
                        if page.url.split('?')[0].rstrip('/') != login_url.split('?')[0].rstrip('/'):
                            still_has_password = False
                            password_selectors = ["input[type='password']", "input[name='password']", "input[id='password']"]
                            for sel in password_selectors:
                                try:
                                    if page.locator(sel).first.is_visible():
                                        still_has_password = True
                                        break
                                except Exception:
                                    continue
                            if not still_has_password:
                                already_logged_in = True
                                self.login_successful = True
                                logger.info("Already logged in using pre-existing session. Skipping login step.")
                    except Exception as goto_err:
                        logger.warning(f"Failed checking pre-existing session: {goto_err}")
                
                if not already_logged_in:
                    self.perform_login(page, login_url, username, password)
                    if self.login_successful:
                        post_login_url = page.url
                        if post_login_url not in to_visit:
                            to_visit.insert(0, post_login_url)
            
            while to_visit and len(pages_list) < self.max_pages:
                current_url = to_visit.pop(0)
                if current_url in self.visited_urls:
                    continue
                
                self.visited_urls.add(current_url)
                logger.info(f"Crawling page: {current_url}")
                
                if on_progress:
                    try:
                        on_progress(current_url, len(pages_list))
                    except Exception as progress_err:
                        logger.error(f"Error calling progress callback: {progress_err}")
                
                try:
                    page.goto(current_url, wait_until="domcontentloaded", timeout=20000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=3000)
                    except Exception:
                        pass
                    page.wait_for_timeout(2000) # Give extra 2 seconds for JS execution & hydration
                    
                    title = page.title()
                    forms = self.extract_forms(page)
                    buttons = self.extract_buttons(page)
                    
                    pages_list.append({
                        "url": current_url,
                        "title": title,
                        "forms": forms,
                        "buttons": buttons
                    })
                    
                    # 1. Extract link tags on the page for further traversal
                    links = page.locator("a").all()
                    for link in links:
                        href = link.get_attribute("href")
                        if href:
                            absolute_url = urljoin(current_url, href)
                            # Remove query params / hashes for deduplication
                            normalized_url = absolute_url.split('#')[0].split('?')[0]
                            if (self.is_same_domain(normalized_url, start_url, login_url) and 
                                     normalized_url not in self.visited_urls and 
                                     normalized_url not in to_visit):
                                to_visit.append(normalized_url)

                    # 2. Click buttons/interactive elements to find dynamic SPA client-side routes
                    for btn_info in buttons[:15]:  # Check up to 15 buttons per page
                        selector = btn_info.get("selector")
                        text = btn_info.get("text", "").lower()
                        if not selector:
                            continue
                        
                        # Skip typical form submit buttons or logout buttons to prevent session termination
                        if "submit" in text or "submit" in selector:
                            continue
                        if any(logout_kw in text for logout_kw in ["logout", "log out", "signout", "sign out", "exit"]):
                            continue
                        
                        try:
                            button_el = page.locator(selector).first
                            if button_el and button_el.is_visible() and button_el.is_enabled():
                                button_el.click(timeout=1500, force=True)
                                page.wait_for_timeout(600)  # Pause to allow route transition
                                
                                new_url = page.url
                                normalized_new = new_url.split('#')[0].split('?')[0]
                                
                                if (normalized_new != current_url.split('#')[0].split('?')[0] and 
                                        self.is_same_domain(normalized_new, start_url, login_url) and 
                                        normalized_new not in self.visited_urls and 
                                        normalized_new not in to_visit):
                                    to_visit.append(normalized_new)
                                    logger.info(f"Discovered new client-side route via button click: {normalized_new}")
                                
                                # Navigate back to continue clicking other buttons on the original page
                                if page.url != current_url:
                                    page.goto(current_url, wait_until="domcontentloaded", timeout=10000)
                                    page.wait_for_timeout(400)
                        except Exception as click_err:
                            logger.debug(f"Skipping button click check on selector {selector}: {click_err}")
                            try:
                                if page.url != current_url:
                                    page.goto(current_url, wait_until="domcontentloaded", timeout=10000)
                            except Exception:
                                pass
                                
                except Exception as e:
                    logger.error(f"Failed to crawl {current_url}: {e}")
                    
            # Capture final storage state if login was attempted or completed
            captured_storage = None
            try:
                if self.login_successful:
                    captured_storage = json.dumps(context.storage_state())
            except Exception as st_err:
                logger.error(f"Failed to extract storage state from context: {st_err}")
                
            browser.close()
            
            return {
                "pages": pages_list,
                "login_successful": self.login_successful,
                "login_error": self.login_error_message,
                "storage_state": captured_storage,
                "api_logs": api_logs
            }
