import json
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        self.api_url = getattr(settings, 'OLLAMA_API_URL', 'http://localhost:11434/api/generate')
        self.model = getattr(settings, 'OLLAMA_MODEL', 'qwen:7b')

    def generate_test_cases(self, pages_data):
        """
        Attempts to generate test cases using the local Ollama LLM.
        Falls back to deterministic template generation if Ollama is unreachable.
        """
        pages_context = json.dumps(pages_data, indent=2)
        prompt = self.get_prompt(pages_context)

        logger.info(f"Attempting to generate test cases using Ollama model '{self.model}' at {self.api_url}...")
        
        try:
            # Call Ollama API with a 10 second timeout
            response = requests.post(
                self.api_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.2
                    }
                },
                timeout=12
            )
            
            if response.status_code == 200:
                response_data = response.json()
                raw_text = response_data.get("response", "").strip()
                
                # Try parsing the LLM output as JSON
                test_cases = self.parse_json_response(raw_text)
                if test_cases:
                    logger.info(f"Successfully generated {len(test_cases)} tests via Ollama.")
                    return test_cases, True
                else:
                    logger.warning("LLM response was not valid JSON. Falling back to deterministic tests.")
            else:
                logger.warning(f"Ollama server returned status code: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Could not connect to Ollama server: {e}. Falling back to deterministic tests.")
        except Exception as e:
            logger.warning(f"Unexpected LLM error: {e}. Falling back to deterministic tests.")

        # Fallback to local template-based test cases if Ollama failed/was offline
        fallback_cases = self.generate_fallback_test_cases(pages_data)
        logger.info(f"Successfully generated {len(fallback_cases)} fallback tests.")
        return fallback_cases, False

    def get_prompt(self, pages_context):
        return f"""You are an expert QA Automation Engineer.
Your task is to analyze a website structure and its background API endpoints to generate functional, executable test cases.

Here is the JSON representing discovered pages, forms, buttons, and API endpoints triggered by actions on the web application:
{pages_context}

Supported actions for each test step:
1. "navigate": Navigation to URL. Parameter keys: "target" (url to open). "selector" and "value" should be empty.
2. "fill": Populate form input fields. Parameter keys: "selector" (CSS selector of input), "value" (text to type). "target" should be empty.
3. "click": Click interactive elements. Parameter keys: "selector" (CSS selector of button/element). "target" and "value" should be empty.
4. "wait": Pause execution. Parameter keys: "value" (millisecond duration string like "1000"). "selector" and "target" should be empty.
5. "assert": Verify content/element existence or check response outcomes. Parameter keys: "selector" (selector of text container or container element, optional), "value" (text expected to be present, which can be an expected field value from the API endpoint response schema). "target" should be empty.
6. "hover": Hover mouse over element. Parameter keys: "selector" (CSS selector of element). "target" and "value" should be empty.
7. "scroll": Scroll the page or scroll element into view. Parameter keys: "selector" (selector of element to scroll into view, optional) or "value" (vertical pixel count to scroll down, e.g. "500"). "target" should be empty.
8. "select": Select option in dropdown. Parameter keys: "selector" (CSS selector of select element), "value" (value or label to select). "target" should be empty.
9. "screenshot": Manually capture screenshot checkpoint. Parameter keys: "value" (screenshot label, optional). "selector" and "target" should be empty.

CRITICAL INSTRUCTIONS FOR SELECTORS & DATA VALIDATION:
- You MUST generate at least one dedicated test case for EACH and EVERY API endpoint listed under "api_endpoints". Each of these test cases should:
  1. Navigate to the page that triggers this endpoint.
  2. Perform the interaction (form submission or button click) using the correct inputs/selectors.
  3. Include an "assert" step checking that the resulting UI matches the expected API "response_schema" fields.
- Leverage the provided API endpoints request/response schemas to design test cases. For instance, when a form triggers an API endpoint, make assertions checking that the text results match the fields returned in the api_endpoints response schema.
- You MUST only use the exact page URLs, form input field selectors/names/IDs, and button selectors that are listed in the JSON context above. Do not invent or hallucinate any selectors or URLs.
- If a form field has an ID (e.g. "email"), use its ID selector (e.g., "#email"). If it only has a name, use its name attribute selector (e.g., "[name='email']").
- When generating "fill" actions, the "value" you provide MUST be contextually valid for the field type:
  - If the field is an email input (contains 'email' in name/id/type), you MUST fill it with a valid email format, e.g., "testuser@example.com".
  - If the field is a phone number input (contains 'phone', 'mobile', 'tel' in name/id/type), you MUST fill it with a valid numeric phone format, e.g., "1234567890".
  - If the field is a password input, use a valid password like "Secr3tP@ss123".
  - Do NOT fill email fields with personal names, or phone fields with generic text.

Generate a JSON array of comprehensive test cases covering these requirements. Each test case MUST follow this schema exactly:
{{
  "title": "Descriptive test case title",
  "steps": [
    {{
      "action": "navigate | fill | click | wait | assert | hover | scroll | select | screenshot",
      "selector": "CSS selector or locator if applicable, else empty string",
      "target": "target url for navigate action, else empty string",
      "value": "value for fill, wait, assert, scroll, select actions, else empty string"
    }}
  ],
  "expected_result": "Descriptive expected result statement"
}}

CRITICAL: Return ONLY a valid JSON array. Do not wrap the JSON in ```json markdown or include any conversational intro/outro text. The response must start with '[' and end with ']'.
"""

    def parse_json_response(self, text):
        """
        Cleans the LLM response text of markdown wrappers and parses it as a list of dicts.
        """
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        
        cleaned = cleaned.strip()
        
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                # Basic validation of keys
                validated_data = []
                for idx, tc in enumerate(data):
                    title = tc.get("title", f"AI Generated Test {idx+1}")
                    steps = tc.get("steps", [])
                    expected = tc.get("expected_result", "Test completes successfully")
                    
                    clean_steps = []
                    for step in steps:
                        action = step.get("action")
                        if action in ["navigate", "fill", "click", "wait", "assert", "hover", "scroll", "select", "screenshot"]:
                            clean_steps.append({
                                "action": action,
                                "selector": step.get("selector", ""),
                                "target": step.get("target", ""),
                                "value": step.get("value", "")
                            })
                    
                    if clean_steps:
                        validated_data.append({
                            "title": title,
                            "steps": clean_steps,
                            "expected_result": expected
                        })
                return validated_data
        except Exception as e:
            logger.error(f"Failed parsing LLM output: {e}. Output was:\n{text}")
        return None

    def generate_fallback_test_cases(self, pages_data):
        """
        Deterministically constructs test cases when the AI server is not available.
        Analyzes the pages structure and creates:
        1. Site accessibility tests
        2. Form submission tests (for each page's forms)
        3. Standalone inputs tests (inputs outside forms)
        4. Interactive button checks (separate click flows)
        5. Negative/validation form rejects tests
        6. Subpage navigation flows
        """
        test_cases = []
        pages = pages_data.get("pages", [])
        
        if not pages:
            return test_cases

        # Test Case 1: Base Application Navigation and Structure Check
        first_page = pages[0]
        test_cases.append({
            "title": f"Verify Access and Navigation to Homepage: {first_page['title'] or 'Home'}",
            "steps": [
                {"action": "navigate", "selector": "", "target": first_page["url"], "value": ""},
                {"action": "wait", "selector": "", "target": "", "value": "1000"},
                {"action": "assert", "selector": "body", "target": "", "value": first_page["title"][:20] if first_page.get("title") else "html"}
            ],
            "expected_result": f"Homepage loads successfully with page title matches '{first_page['title']}'."
        })

        # Test Case 2: Positive Form submissions fallback tests
        for page_idx, page in enumerate(pages):
            forms = page.get("forms", [])
            for form_idx, form in enumerate(forms):
                form_id = form.get("id", f"form-{form_idx}")
                if form_id == "standalone_fields":
                    continue
                
                steps = [{"action": "navigate", "selector": "", "target": page["url"], "value": ""}]
                fields = form.get("fields", [])
                for field in fields:
                    name = field.get("name")
                    inp_type = field.get("type", "text")
                    inp_id = field.get("id")
                    
                    if inp_id:
                        selector = f"#{inp_id}"
                    else:
                        selector = f"input[name='{name}']"
                        
                    name_lower = (name or "").lower()
                    id_lower = (inp_id or "").lower()
                    
                    if "email" in name_lower or "email" in id_lower or inp_type == "email":
                        val = "testuser@example.com"
                    elif "password" in name_lower or "password" in id_lower or "pass" in name_lower or "pass" in id_lower or inp_type == "password":
                        val = "Secr3tP@ss123"
                    elif "phone" in name_lower or "phone" in id_lower or "mobile" in name_lower or "mobile" in id_lower or "tel" in name_lower or "tel" in id_lower or inp_type == "tel":
                        val = "1234567890"
                    elif "number" in inp_type or "quantity" in name_lower or "amount" in name_lower:
                        val = "42"
                    elif "message" in name_lower or "message" in id_lower or "comment" in name_lower or "comment" in id_lower or "feedback" in name_lower or "feedback" in id_lower:
                        val = "This is an automated test message from the browser agent."
                    elif "subject" in name_lower or "subject" in id_lower:
                        val = "Automated Test Inquiry"
                    else:
                        val = "Automated Test Input"
                        
                    steps.append({
                        "action": "fill",
                        "selector": selector,
                        "target": "",
                        "value": val
                    })
                
                submit_selector = f"form[id='{form_id}'] button[type='submit']"
                if page.get("buttons"):
                    for btn in page["buttons"]:
                        if "submit" in btn["selector"] or "login" in btn["text"].lower() or "submit" in btn["text"].lower():
                            submit_selector = btn["selector"]
                            break
                            
                steps.append({"action": "click", "selector": submit_selector, "target": "", "value": ""})
                steps.append({"action": "wait", "selector": "", "target": "", "value": "2000"})
                steps.append({"action": "assert", "selector": "body", "target": "", "value": ""})
                
                test_cases.append({
                    "title": f"Execute Form Submission: {form_id} on Page {page['title'] or 'View'}",
                    "steps": steps,
                    "expected_result": f"Form '{form_id}' is successfully filled and submitted without errors."
                })

        # Test Case 3: Negative Form validation constraints tests (if email fields exist)
        for page_idx, page in enumerate(pages):
            forms = page.get("forms", [])
            for form_idx, form in enumerate(forms):
                form_id = form.get("id", "")
                if not form_id or form_id == "standalone_fields":
                    continue
                
                steps = [{"action": "navigate", "selector": "", "target": page["url"], "value": ""}]
                fields = form.get("fields", [])
                has_email = False
                for field in fields:
                    name = field.get("name")
                    inp_type = field.get("type", "text")
                    inp_id = field.get("id")
                    selector = f"#{inp_id}" if inp_id else f"input[name='{name}']"
                    
                    name_lower = (name or "").lower()
                    id_lower = (inp_id or "").lower()
                    
                    if "email" in name_lower or "email" in id_lower or inp_type == "email":
                        val = "invalid-email-format"
                        has_email = True
                    else:
                        val = "Test"
                        
                    steps.append({"action": "fill", "selector": selector, "target": "", "value": val})
                
                if not has_email:
                    continue
                    
                submit_selector = f"form[id='{form_id}'] button[type='submit']"
                if page.get("buttons"):
                    for btn in page["buttons"]:
                        if "submit" in btn["selector"] or "login" in btn["text"].lower() or "submit" in btn["text"].lower():
                            submit_selector = btn["selector"]
                            break
                            
                steps.append({"action": "click", "selector": submit_selector, "target": "", "value": ""})
                steps.append({"action": "wait", "selector": "", "target": "", "value": "1000"})
                steps.append({"action": "assert", "selector": "body", "target": "", "value": ""})
                
                test_cases.append({
                    "title": f"Verify Form Validation Constraints: {form_id} on Page {page['title'] or 'View'}",
                    "steps": steps,
                    "expected_result": f"Form '{form_id}' rejects invalid input formats and shows validation feedback."
                })

        # Test Case 4: Standalone non-form fields tests
        for page_idx, page in enumerate(pages):
            forms = page.get("forms", [])
            standalone_form = next((f for f in forms if f.get("id") == "standalone_fields"), None)
            if standalone_form:
                fields = standalone_form.get("fields", [])
                steps = [{"action": "navigate", "selector": "", "target": page["url"], "value": ""}]
                for field in fields:
                    name = field.get("name")
                    inp_type = field.get("type", "text")
                    inp_id = field.get("id")
                    selector = f"#{inp_id}" if inp_id else f"input[name='{name}']"
                    
                    name_lower = (name or "").lower()
                    id_lower = (inp_id or "").lower()
                    if "email" in name_lower or "email" in id_lower or inp_type == "email":
                        val = "testuser@example.com"
                    elif "password" in name_lower or "password" in id_lower or "pass" in name_lower or "pass" in id_lower or inp_type == "password":
                        val = "Secr3tP@ss123"
                    else:
                        val = "Automated Standalone Input"
                        
                    steps.append({"action": "fill", "selector": selector, "target": "", "value": val})
                
                click_selector = ""
                if page.get("buttons"):
                    # Find a button to click that is not a form submit
                    click_selector = page["buttons"][0]["selector"]
                    
                if click_selector:
                    steps.append({"action": "click", "selector": click_selector, "target": "", "value": ""})
                steps.append({"action": "wait", "selector": "", "target": "", "value": "1500"})
                steps.append({"action": "assert", "selector": "body", "target": "", "value": ""})
                
                test_cases.append({
                    "title": f"Verify Standalone Input Fields on Page: {page['title'] or 'View'}",
                    "steps": steps,
                    "expected_result": f"Standalone fields are successfully populated and interactive events triggered."
                })

        # Test Case 5: Button Action Validations (Click Verification)
        for page in pages:
            buttons = page.get("buttons", [])
            for idx, btn in enumerate(buttons[:3]):
                text = btn.get("text", "")
                selector = btn.get("selector", "")
                if not selector or "submit" in text.lower() or "login" in text.lower():
                    continue
                
                test_cases.append({
                    "title": f"Verify Interactive Button Action: Click '{text[:25]}' on {page['title'] or 'Page'}",
                    "steps": [
                        {"action": "navigate", "selector": "", "target": page["url"], "value": ""},
                        {"action": "click", "selector": selector, "target": "", "value": ""},
                        {"action": "wait", "selector": "", "target": "", "value": "1000"},
                        {"action": "assert", "selector": "body", "target": "", "value": ""}
                    ],
                    "expected_result": f"Button '{text}' is clickable and page resolves without console errors."
                })

        # Test Case 6: Verify Subpage Navigation flow
        if len(pages) > 1:
            steps = []
            expected_title = pages[1].get("title", "Subpage")
            steps.append({"action": "navigate", "selector": "", "target": pages[0]["url"], "value": ""})
            steps.append({"action": "navigate", "selector": "", "target": pages[1]["url"], "value": ""})
            steps.append({"action": "wait", "selector": "", "target": "", "value": "1000"})
            steps.append({"action": "assert", "selector": "body", "target": "", "value": expected_title[:20] if expected_title else "html"})
            
            test_cases.append({
                "title": f"Verify Navigation Flow from Homepage to Subpage: {expected_title}",
                "steps": steps,
                "expected_result": f"Browser can successfully navigate from Homepage to subpage {pages[1]['url']}."
            })
            
        # Test Case 7: API Endpoint Verification (ensure each API has a test case)
        api_endpoints = pages_data.get("api_endpoints", [])
        from urllib.parse import urlparse
        
        for api in api_endpoints:
            method = api.get("method", "GET").upper()
            url_pattern = api.get("url_pattern", "")
            if not url_pattern:
                continue
                
            # Try to find a form that triggers this API
            matching_page = None
            matching_form = None
            
            try:
                from tasks.discovery import get_url_pattern
            except Exception:
                get_url_pattern = None
                
            for page in pages:
                forms = page.get("forms", [])
                for form in forms:
                    action = form.get("action", "") or ""
                    if action and get_url_pattern:
                        try:
                            action_pattern = get_url_pattern(action, first_page["url"])
                            if action_pattern and (action_pattern in url_pattern or url_pattern in action_pattern):
                                matching_page = page
                                matching_form = form
                                break
                        except Exception:
                            pass
                if matching_page:
                    break
                    
            if matching_page and matching_form:
                # Generate form submission test case for this specific API
                form_id = matching_form.get("id", "form")
                steps = [{"action": "navigate", "selector": "", "target": matching_page["url"], "value": ""}]
                
                # Fill fields
                fields = matching_form.get("fields", [])
                for field in fields:
                    name = field.get("name")
                    inp_type = field.get("type", "text")
                    inp_id = field.get("id")
                    selector = f"#{inp_id}" if inp_id else f"input[name='{name}']"
                    
                    # Determine a valid value
                    name_lower = (name or "").lower()
                    id_lower = (inp_id or "").lower()
                    if "email" in name_lower or "email" in id_lower or inp_type == "email":
                        val = "testuser@example.com"
                    elif "password" in name_lower or "password" in id_lower or inp_type == "password":
                        val = "Secr3tP@ss123"
                    elif "phone" in name_lower or "phone" in id_lower or inp_type == "tel":
                        val = "1234567890"
                    else:
                        val = "API Test Input"
                        
                    steps.append({"action": "fill", "selector": selector, "target": "", "value": val})
                    
                # Find submit button
                submit_selector = f"form[id='{form_id}'] button[type='submit']"
                if matching_page.get("buttons"):
                    for btn in matching_page["buttons"]:
                        if "submit" in btn["selector"] or "submit" in btn["text"].lower() or "login" in btn["text"].lower():
                            submit_selector = btn["selector"]
                            break
                            
                steps.append({"action": "click", "selector": submit_selector, "target": "", "value": ""})
                steps.append({"action": "wait", "selector": "", "target": "", "value": "2000"})
                
                # Check expected schema keys for assertion
                assert_val = ""
                response_schema = api.get("response_schema", {})
                if response_schema:
                    assert_val = list(response_schema.keys())[0] if isinstance(response_schema, dict) else ""
                    
                steps.append({"action": "assert", "selector": "body", "target": "", "value": assert_val})
                
                test_cases.append({
                    "title": f"Verify API Endpoint [{method}] {url_pattern} via Form Submit",
                    "steps": steps,
                    "expected_result": f"Submitting the form triggers [{method}] {url_pattern} API and returns a successful response."
                })
            else:
                # If no matching form, and it's a GET, try to find the page where it triggers
                best_page = None
                for page in pages:
                    page_path = urlparse(page["url"]).path.strip('/')
                    api_path = url_pattern.strip('/')
                    if page_path and api_path and (page_path in api_path or api_path in page_path):
                        best_page = page
                        break
                if not best_page:
                    best_page = first_page
                    
                steps = [{"action": "navigate", "selector": "", "target": best_page["url"], "value": ""}]
                
                # Check if there is a button on this page that might trigger the API (e.g. Search, Load, Refresh)
                trigger_btn = None
                if best_page.get("buttons"):
                    for btn in best_page["buttons"]:
                        btn_text = btn.get("text", "").lower()
                        if any(kw in btn_text for kw in ["load", "refresh", "search", "get", "fetch", "show"]):
                            trigger_btn = btn
                            break
                if trigger_btn:
                    steps.append({"action": "click", "selector": trigger_btn["selector"], "target": "", "value": ""})
                    steps.append({"action": "wait", "selector": "", "target": "", "value": "1500"})
                    
                # Check expected schema keys for assertion
                assert_val = ""
                response_schema = api.get("response_schema", {})
                if response_schema:
                    assert_val = list(response_schema.keys())[0] if isinstance(response_schema, dict) else ""
                    
                steps.append({"action": "assert", "selector": "body", "target": "", "value": assert_val})
                
                test_cases.append({
                    "title": f"Verify API Endpoint [{method}] {url_pattern} Page Interaction",
                    "steps": steps,
                    "expected_result": f"Visiting the page/triggering interaction invokes the [{method}] {url_pattern} API successfully."
                })
                
        return test_cases

