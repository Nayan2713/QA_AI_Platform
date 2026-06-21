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
Your task is to analyze a website structure and generate functional, executable test cases.

Here is the JSON representing discovered pages, forms, and buttons of the web application:
{pages_context}

Supported actions for each test step:
1. "navigate": Navigation to URL. Parameter keys: "target" (url to open). "selector" and "value" should be empty.
2. "fill": Populate form input fields. Parameter keys: "selector" (CSS selector of input), "value" (text to type). "target" should be empty.
3. "click": Click interactive elements. Parameter keys: "selector" (CSS selector of button/element). "target" and "value" should be empty.
4. "wait": Pause execution. Parameter keys: "value" (millisecond duration string like "1000"). "selector" and "target" should be empty.
5. "assert": Verify content/element existence. Parameter keys: "selector" (selector of text container or container element), "value" (text expected to be present). "target" should be empty.

Generate a JSON array containing 3 to 5 comprehensive test cases. Each test case MUST follow this schema exactly:
{{
  "title": "Descriptive test case title",
  "steps": [
    {{
      "action": "navigate | fill | click | wait | assert",
      "selector": "CSS selector or locator if applicable, else empty string",
      "target": "target url for navigate action, else empty string",
      "value": "value for fill, wait, assert actions, else empty string"
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
                        if action in ["navigate", "fill", "click", "wait", "assert"]:
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
        3. Button interactive checks
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

        # Form submissions fallback tests
        for page_idx, page in enumerate(pages):
            forms = page.get("forms", [])
            for form_idx, form in enumerate(forms):
                form_id = form.get("id", f"form-{form_idx}")
                steps = [{"action": "navigate", "selector": "", "target": page["url"], "value": ""}]
                
                # Fill in inputs
                fields = form.get("fields", [])
                for field in fields:
                    name = field.get("name")
                    inp_type = field.get("type", "text")
                    inp_id = field.get("id")
                    
                    # Compute selector
                    if inp_id:
                        selector = f"#{inp_id}"
                    else:
                        selector = f"input[name='{name}']"
                        
                    # Compute dummy values
                    if "email" in name or inp_type == "email":
                        val = "testuser@example.com"
                    elif "password" in name or inp_type == "password":
                        val = "Secr3tP@ss123"
                    elif "phone" in name or inp_type == "tel":
                        val = "1234567890"
                    elif inp_type == "number":
                        val = "42"
                    else:
                        val = "Automated Test Input"
                        
                    steps.append({
                        "action": "fill",
                        "selector": selector,
                        "target": "",
                        "value": val
                    })
                
                # Add click submit step
                # Look for a button or submit element
                submit_selector = f"form[id='{form_id}'] button[type='submit']"
                if page.get("buttons"):
                    # Check if there is a button selector on this page matching submit
                    for btn in page["buttons"]:
                        if "submit" in btn["selector"] or "login" in btn["text"].lower() or "submit" in btn["text"].lower():
                            submit_selector = btn["selector"]
                            break
                            
                steps.append({"action": "click", "selector": submit_selector, "target": "", "value": ""})
                steps.append({"action": "wait", "selector": "", "target": "", "value": "2000"})
                steps.append({"action": "assert", "selector": "body", "target": "", "value": ""}) # Assert page runs without crashing
                
                test_cases.append({
                    "title": f"Execute Form Submission: {form_id} on Page {page['title'] or 'View'}",
                    "steps": steps,
                    "expected_result": f"Form '{form_id}' is successfully filled and submitted without errors."
                })

        # Test Case 3: Verify Subpage Navigation flow
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
            
        return test_cases
