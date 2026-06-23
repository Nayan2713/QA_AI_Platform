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
            page.goto(login_url, wait_until="networkidle", timeout=10000)
            
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
                    logger.warning(f"Login failed heuristic triggered. Still on login URL: {current_url}")
            else:
                logger.warning("Could not identify login fields.")
                self.login_successful = False
        except Exception as e:
            logger.error(f"Login failed: {e}")
            self.login_successful = False

    def extract_forms(self, page):
        """
        Finds all forms on the current page and extracts fields, action, and method.
        """
        forms_data = []
        try:
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
        except Exception as e:
            logger.error(f"Error extracting forms: {e}")
        return forms_data

    def extract_buttons(self, page):
        """
        Finds buttons and interactive clickable elements on the page.
        """
        buttons_data = []
        try:
            buttons = page.locator("button, input[type='button'], input[type='submit']").all()
            for idx, btn in enumerate(buttons):
                # Skip hidden elements
                if not btn.is_visible():
                    continue
                text = btn.inner_text().strip() or btn.get_attribute("value") or ""
                if not text:
                    text = btn.get_attribute("title") or f"Button {idx}"
                
                # Get a selector. Prefers ID, then name, then class
                btn_id = btn.get_attribute("id")
                btn_name = btn.get_attribute("name")
                btn_class = btn.get_attribute("class")
                
                if btn_id:
                    selector = f"#{btn_id}"
                elif btn_name:
                    selector = f"[name='{btn_name}']"
                elif btn_class:
                    # Strip classes containing colons (e.g. Tailwind modifiers like hover:, focus:, md:)
                    classes = [c for c in btn_class.split() if ':' not in c]
                    if classes:
                        selector = f".{'.'.join(classes)}"
                    else:
                        selector = f"button:has-text('{text}')" if text else f"button >> nth={idx}"
                else:
                    selector = f"button:has-text('{text}')" if text else f"button >> nth={idx}"

                buttons_data.append({
                    "text": text,
                    "selector": selector
                })
        except Exception as e:
            logger.error(f"Error extracting buttons: {e}")
        return buttons_data

    def discover(self, start_url, login_url=None, username=None, password=None, on_progress=None):
        """
        Performs the complete page discovery using Playwright.
        Returns a dict in the unified format.
        """
        logger.info(f"Starting browser discovery for URL: {start_url}")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            
            # Queue of links to visit
            to_visit = [start_url]
            pages_list = []
            
            # Optional login phase
            if login_url and username and password:
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
                    page.goto(current_url, wait_until="load", timeout=15000)
                    page.wait_for_timeout(1000) # Give extra second for JS execution
                    
                    title = page.title()
                    forms = self.extract_forms(page)
                    buttons = self.extract_buttons(page)
                    
                    pages_list.append({
                        "url": current_url,
                        "title": title,
                        "forms": forms,
                        "buttons": buttons
                    })
                    
                    # Extract link tags on the page for further traversal
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
                                
                except Exception as e:
                    logger.error(f"Failed to crawl {current_url}: {e}")
                    
            browser.close()
            
            return {
                "pages": pages_list,
                "login_successful": self.login_successful
            }
