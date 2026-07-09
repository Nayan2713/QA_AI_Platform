import json
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Keys that come from HTTP error envelopes — useless as UI assert values
_ERROR_ENVELOPE_KEYS = frozenset({
    'statuscode', 'status_code', 'statusCode',
    'message', 'msg', 'error', 'errors',
    'detail', 'details', 'non_field_errors',
    'code', 'type', 'stack', 'trace', 'traceback',
    'timestamp', 'path', 'exception',
})

# URL path segments that are too generic to assert against page text
_SKIP_SEGMENTS = frozenset({
    'api', 'v1', 'v2', 'v3', 'v4',
    'backend', 'rest', 'public', 'private',
    'internal', 'external', 'graphql',
})


class LLMService:
    def __init__(self, model_choice=None):
        self.model_choice = model_choice
        self.api_url = getattr(settings, 'OLLAMA_API_URL', 'http://localhost:11434/api/generate')
        self.model = getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:7b')

    # ------------------------------------------------------------------ #
    # Public entry point                                                   #
    # ------------------------------------------------------------------ #

    def generate_test_cases(self, pages_data):
        """
        Attempts to generate test cases using the configured LLM.
        Falls back to deterministic template generation if LLM is unreachable.
        Returns (test_cases, industry, was_ai_generated, resolved_model).
        """
        # OPTIMIZED: use 'ai_summary' if present to reduce prompt size by 80-90%.
        # Falls back to forms and buttons only if 'ai_summary' is missing.
        trimmed_pages = []
        for page in pages_data.get("pages", []):
            if page.get("ai_summary"):
                trimmed_pages.append({
                    "url": page.get("url"),
                    "title": page.get("title"),
                    "ai_summary": page.get("ai_summary")
                })
            else:
                trimmed_pages.append({
                    "url": page.get("url"),
                    "title": page.get("title"),
                    "forms": page.get("forms", []),
                    "buttons": page.get("buttons", [])
                })

        trimmed = {
            "pages": trimmed_pages,
            "api_endpoints": pages_data.get("api_endpoints", []),
            "industry": pages_data.get("industry")
        }
        pages_context = json.dumps(trimmed, indent=2)

        # Guard: if context is still huge, drop page details and keep only APIs
        from config.llm_config import estimate_tokens
        token_estimate = estimate_tokens(pages_context)
        if token_estimate > 6000:
            logger.warning(
                f"Context too large ({token_estimate} est. tokens). "
                "Keeping only API endpoints for prompt."
            )
            slim = {
                "pages": [{"url": p.get("url"), "title": p.get("title")} for p in trimmed["pages"]],
                "api_endpoints": trimmed["api_endpoints"],
                "industry": trimmed.get("industry")
            }
            pages_context = json.dumps(slim, indent=2)

        prompt = self.get_prompt(pages_context)

        logger.info(f"Attempting to generate test cases using configured LLM (choice: {self.model_choice})...")

        try:
            from config.llm_config import get_llm, llm_predict
            llm = get_llm(model_choice=self.model_choice)
            
            # Resolve model name:
            if self.model_choice == 'openai':
                resolved_model = "ChatGPT (gpt-4o-mini)"
            elif self.model_choice == 'ollama_groq':
                resolved_model = "Ollama (groq)"
            elif self.model_choice in ('ollama', 'ollama_qwen'):
                resolved_model = f"Ollama ({getattr(llm, 'model', 'Qwen')})"
            else:
                # auto fallback detection
                if getattr(llm, 'model_name', None) == 'gpt-4o-mini':
                    resolved_model = "ChatGPT (gpt-4o-mini)"
                elif 'groq.com' in getattr(llm, 'base_url', ''):
                    resolved_model = "Groq (Llama-3.3-70b)"
                else:
                    resolved_model = f"Ollama ({getattr(llm, 'model', 'Qwen')})"

            raw_text = llm_predict(llm, prompt, model_choice=self.model_choice).strip()
            result = self.parse_json_response(raw_text)
            if result:
                test_cases, industry = result
                logger.info(f"LLM generated {len(test_cases)} test cases using model {resolved_model}.")
                return test_cases, industry, True, resolved_model
            else:
                logger.warning("LLM response was not valid JSON. Falling back to deterministic tests.")
        except Exception as e:
            logger.warning(f"LLM unavailable: {e}. Using deterministic fallback.")

        fallback_cases, industry = self.generate_fallback_test_cases(pages_data)
        logger.info(f"Deterministic fallback generated {len(fallback_cases)} test cases.")
        return fallback_cases, industry, False, "Fallback Template"

    def generate_single_test_case(self, pages_data, title):
        """
        Attempts to generate a single test case for the given title using the configured LLM.
        Returns a dict representing the test case or None on failure.
        """
        trimmed_pages = []
        for page in pages_data.get("pages", []):
            if page.get("ai_summary"):
                trimmed_pages.append({
                    "url": page.get("url"),
                    "title": page.get("title"),
                    "ai_summary": page.get("ai_summary")
                })
            else:
                trimmed_pages.append({
                    "url": page.get("url"),
                    "title": page.get("title"),
                    "forms": page.get("forms", []),
                    "buttons": page.get("buttons", [])
                })

        trimmed = {
            "pages": trimmed_pages,
            "api_endpoints": pages_data.get("api_endpoints", []),
            "industry": pages_data.get("industry")
        }
        pages_context = json.dumps(trimmed, indent=2)

        # Guard: if context is still huge, drop page details and keep only APIs
        from config.llm_config import estimate_tokens
        token_estimate = estimate_tokens(pages_context)
        if token_estimate > 6000:
            logger.warning(
                f"Context too large ({token_estimate} est. tokens). "
                "Keeping only API endpoints and basic page info for prompt."
            )
            slim = {
                "pages": [{"url": p.get("url"), "title": p.get("title")} for p in trimmed["pages"]],
                "api_endpoints": trimmed["api_endpoints"],
                "industry": trimmed.get("industry")
            }
            pages_context = json.dumps(slim, indent=2)

        prompt = f"""You are an expert QA Automation Engineer.
Your task is to analyze the discovered pages and API endpoints and generate ONE single test case that matches the requested title.

Application Context:
{pages_context}

Requested Test Case Title: "{title}"

=== SUPPORTED STEP ACTIONS ===
1. "navigate"   - go to URL.            Keys: "target" (url). selector="" value="".
2. "fill"       - type into input.      Keys: "selector" (CSS), "value" (text). target="".
3. "click"      - click element.        Keys: "selector" (CSS). target="" value="".
4. "wait"       - pause.                Keys: "value" (ms string e.g. "800"). selector="" target="".
5. "assert"     - verify text present.  Keys: "selector" (optional CSS), "value" (expected text). target="".
6. "hover"      - hover over element.   Keys: "selector". target="" value="".
7. "scroll"     - scroll page/element.  Keys: "selector" (optional) or "value" (px). target="".
8. "select"     - choose dropdown.      Keys: "selector", "value" (option label). target="".
9. "screenshot" - capture checkpoint.   Keys: "value" (label). selector="" target="".

=== RULES ===
1. Generate exactly ONE test case.
2. Ensure you use REAL selectors from the page data or summaries provided in the context.
3. Wait times: use "800" for navigation/heavy loads, "500" for quick interactions.

=== OUTPUT FORMAT ===
Return ONLY valid JSON. No markdown, no explanation.

{{
  "title": "{title}",
  "category": "Generic|Industry Flow|Access Control",
  "steps": [
    {{
      "action": "navigate|fill|click|wait|assert|hover|scroll|select|screenshot",
      "selector": "exact CSS selector or empty string",
      "target": "full URL for navigate, else empty string",
      "value": "text for fill/assert/wait/select/scroll, else empty string"
    }}
  ],
  "expected_result": "Specific success description"
}}
"""

        try:
            from config.llm_config import get_llm, llm_predict
            llm = get_llm(model_choice=self.model_choice)
            raw_text = llm_predict(llm, prompt, model_choice=self.model_choice).strip()
            parsed = self.parse_json_response(raw_text, require_assert=False)
            if parsed:
                result, _ = parsed
                if result and len(result) > 0:
                    return result[0]
        except Exception as e:
            logger.warning(f"Failed to generate single test case: {e}")
        return None

    def summarize_page(self, page_data):
        """
        Creates a compact semantic summary of a page's elements to reduce context size.
        """
        prompt = f"""You are an expert QA Automation Engineer.
Your task is to analyze the raw DOM elements (forms and buttons) of a single page and output a highly condensed, semantic summary of its purpose and actionable elements.
This summary will be used later to generate test cases, so you MUST retain all exact CSS selectors for inputs and buttons.

Page URL: {page_data.get('url')}
Page Title: {page_data.get('title')}

Forms:
{json.dumps(page_data.get('forms', []), indent=2)}

Buttons:
{json.dumps(page_data.get('buttons', []), indent=2)}

Output a brief 1-4 sentence description of the page, followed by a bulleted list of actionable elements (inputs, dropdowns, buttons) and their EXACT CSS selectors.
Do not output any JSON, just plain text markdown. Example:
- Email Input: [name="email"]
- Submit Button: button.login-btn
"""
        try:
            from config.llm_config import get_llm, llm_predict
            llm = get_llm(model_choice=self.model_choice)
            raw_text = llm_predict(llm, prompt, model_choice=self.model_choice).strip()
            return raw_text
        except Exception as e:
            logger.warning(f"Failed to summarize page: {e}")
            return None

    # ------------------------------------------------------------------ #
    # LLM prompt                                                           #
    # ------------------------------------------------------------------ #

    def get_prompt(self, pages_context):
        """
        Instructs the LLM to generate ONE test case per API endpoint so that
        74 APIs → 74+ test cases instead of the old 3-5 generic ones.
        """
        try:
            pages_data = json.loads(pages_context)
            detected_industry = pages_data.get("industry") or ", ".join(self._classify_industries(pages_data))
        except Exception:
            detected_industry = "General"

        return f"""You are an expert QA Automation Engineer specialising in API-driven web application testing.
Your task is to analyse discovered pages and API endpoints and generate a COMPREHENSIVE test suite that covers EVERY API endpoint found.

Here is the full application context (pages, forms, buttons, API endpoints):
{pages_context}

Detected Industry: {detected_industry}

=== SUPPORTED STEP ACTIONS ===
1. "navigate"   - go to URL.            Keys: "target" (url). selector="" value="".
2. "fill"       - type into input.      Keys: "selector" (CSS), "value" (text). target="".
3. "click"      - click element.        Keys: "selector" (CSS). target="" value="".
4. "wait"       - pause.                Keys: "value" (ms string e.g. "800"). selector="" target="".
5. "assert"     - verify text present.  Keys: "selector" (optional CSS), "value" (expected text). target="".
6. "hover"      - hover over element.   Keys: "selector". target="" value="".
7. "scroll"     - scroll page/element.  Keys: "selector" (optional) or "value" (px). target="".
8. "select"     - choose dropdown.      Keys: "selector", "value" (option label). target="".
9. "screenshot" - capture checkpoint.   Keys: "value" (label). selector="" target="".

=== CRITICAL GENERATION RULES ===

RULE 1 — COVER EVERY API ENDPOINT:
Generate at least ONE test case for EVERY entry in "api_endpoints".
If there are 74 APIs, generate at least 74 test cases. Do not stop early.

RULE 2 — API TEST CATEGORIES per endpoint:
- GET  → "Verify [Resource] List/Detail loads successfully"
- POST → "Verify Create [Resource] with valid data succeeds" + negative empty-field test
- PUT/PATCH → "Verify Update [Resource] reflects changes"
- DELETE → "Verify Delete [Resource] removes it from list"
- AUTH endpoints → "Verify Unauthenticated access returns 401"

RULE 3 — ASSERT VALUES:
Use keys from response_schema ONLY if they are NOT error-envelope keys.
Error-envelope keys to SKIP: statusCode, status_code, message, error, detail, code, type, stack.
If all schema keys are error-envelope keys, derive the assert value from the URL:
  /api/v1/candidates → assert "Candidates"
  /api/v1/users/:id  → assert "" (empty — detail routes have variable content)

RULE 4 — WAIT TIMES: Use "800" for page loads, "500" for interactions. Do NOT use "1500" or "2000".

RULE 5 — USE REAL SELECTORS ONLY from the page data or summaries. Never invent selectors.

RULE 6 — INDUSTRY: Classify as "E-commerce", "SaaS", "FinTech", "Healthcare", "HR", "Recruitment", or "General".

RULE 7 — INDUSTRY SPECIFIC JOURNEYS:
Prioritize generating the critical journeys for the detected industry ({detected_industry}), on top of the generic test cases:
- E-commerce: Add to cart, checkout, payment, empty-cart checkout, out-of-stock handling, discount coupon.
- FinTech/Banking: 2FA challenge, balance display, transfers with insufficient funds, transaction history, session timeout.
- Healthcare: Appointment booking/cancellation, patient record access control (High Importance, prefix title with [Access Control]), medical form validation.
- Recruitment: Job application submission, resume upload limits, candidate status transition, duplicate application prevention.
- HR: Leave request and approval, payroll display, attendance edit permissions (prefix title with [Access Control]).
- SaaS: User invite, role-permission boundaries (prefix title with [Access Control]), settings persistence, subscription billing state.
Only generate these flows if their required elements are actually present/referenced in the context. Use the same JSON step format.

=== OUTPUT FORMAT ===
Return ONLY valid JSON. No markdown, no explanation, no ```json fences.
Start with {{ and end with }}.

{{
  "industry": "{detected_industry}",
  "test_cases": [
    {{
      "title": "Descriptive title including HTTP method and endpoint name, or the critical industry journey name",
      "category": "Generic|Industry Flow|Access Control (defaults to Generic)",
      "steps": [
        {{
          "action": "navigate|fill|click|wait|assert|hover|scroll|select|screenshot",
          "selector": "exact CSS selector or empty string",
          "target": "full URL for navigate, else empty string",
          "value": "text for fill/assert/wait/select/scroll, else empty string"
        }}
      ],
      "expected_result": "Specific success description"
    }}
  ]
}}
"""

    # ------------------------------------------------------------------ #
    # LLM response parser                                                  #
    # ------------------------------------------------------------------ #

    def parse_json_response(self, text, require_assert=True):
        """
        Strips markdown fences and parses the LLM response as JSON.
        Returns (test_cases, industry) or None on failure.
        """
        cleaned = text.strip()

        # Strip markdown fences
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # Find first { ... last } in case of preamble text
        brace_start = cleaned.find('{')
        brace_end = cleaned.rfind('}')
        if brace_start > 0 and brace_end > brace_start:
            cleaned = cleaned[brace_start:brace_end + 1]

        try:
            data = json.loads(cleaned)
            industry = "General"
            test_cases_list = []

            if isinstance(data, dict):
                industry = data.get("industry", "General")
                # If the dict is just a single test case (from generate_single)
                if "title" in data and "steps" in data and "test_cases" not in data:
                    test_cases_list = [data]
                else:
                    test_cases_list = data.get("test_cases", [])
            elif isinstance(data, list):
                test_cases_list = data

            validated = []
            for idx, tc in enumerate(test_cases_list):
                title = tc.get("title", f"AI Generated Test {idx + 1}")
                steps = tc.get("steps", [])
                expected = tc.get("expected_result", "Test completes successfully")
                category = tc.get("category", "Generic")
                if category not in ["Generic", "Industry Flow", "Access Control"]:
                    category = "Generic"

                # Light guard: reject fabricated API tests
                title_lower = title.lower()
                starts_verify_http = any(title_lower.startswith(f"verify {m}") for m in ["get", "post", "put", "delete"])
                contains_api_indicator = any(ind in title_lower for ind in ["/api/", "/_/", "/backend/", "cdn-cgi"])
                if starts_verify_http and contains_api_indicator:
                    logger.info(f"LLM Parser: Discarding fabricated API test: {title}")
                    continue

                clean_steps = []
                for step in steps:
                    action = step.get("action")
                    if action in [
                        "navigate", "fill", "click", "wait", "assert",
                        "hover", "scroll", "select", "screenshot"
                    ]:
                        if action == "assert":
                            val = step.get("value", "")
                            val_cleaned = str(val).strip().lower()
                            if not val_cleaned or val_cleaned in ["data", "content", "result", "success", "h", "page"]:
                                # Drop meaningless assertion step
                                continue

                        clean_steps.append({
                            "action": action,
                            "selector": step.get("selector", ""),
                            "target": step.get("target", ""),
                            "value": step.get("value", "")
                        })

                # A test that asserts nothing has no value; discard if no remaining asserts
                if require_assert and not any(s["action"] == "assert" for s in clean_steps):
                    logger.info(f"LLM Parser: Discarding test case with no valid assertions: {title}")
                    continue

                validated.append({
                    "title": title,
                    "steps": clean_steps,
                    "expected_result": expected,
                    "category": category
                })

            logger.info(f"Parsed {len(validated)} test cases from LLM response.")
            return validated, industry

        except Exception as e:
            logger.error(f"Failed parsing LLM output: {e}. Raw: {text[:300]}")
        return None

    # ------------------------------------------------------------------ #
    # Helpers for fallback generator                                       #
    # ------------------------------------------------------------------ #

    def _classify_industry(self, pages_data):
        pages = pages_data.get("pages", [])
        combined = " ".join(
            f"{p.get('url', '')} {p.get('title', '')} "
            + " ".join(b.get('text', '') for b in p.get('buttons', []))
            for p in pages
        ).lower()
        combined += " ".join(
            a.get('url_pattern', '') for a in pages_data.get('api_endpoints', [])
        ).lower()

        if any(w in combined for w in ["candidate", "recruit", "job", "hiring", "applicant", "talent"]):
            return "Recruitment"
        if any(w in combined for w in ["employee", "leave", "payroll", "attendance", "hr", "human resource"]):
            return "HR"
        if any(w in combined for w in ["patient", "doctor", "medical", "appointment", "clinic", "health"]):
            return "Healthcare"
        if any(w in combined for w in ["cart", "checkout", "shop", "product", "store", "price", "buy", "order"]):
            return "E-commerce"
        if any(w in combined for w in ["bank", "pay", "card", "finance", "transfer", "transaction", "invoice"]):
            return "FinTech"
        if any(w in combined for w in ["dashboard", "team", "settings", "project", "manage", "admin", "crm"]):
            return "SaaS"
        return "General"

    def _make_fill_value(self, name, inp_id, inp_type):
        """Return a realistic test value for a given form field."""
        name_l = (name or "").lower()
        id_l = (inp_id or "").lower()
        if "email" in name_l or "email" in id_l or inp_type == "email":
            return "testuser@example.com"
        if "password" in name_l or "password" in id_l or inp_type == "password":
            return "Secr3tP@ss123"
        if "phone" in name_l or "mobile" in name_l or inp_type == "tel":
            return "9876543210"
        if "number" in inp_type or "quantity" in name_l or "amount" in name_l:
            return "1"
        if "message" in name_l or "comment" in name_l or "description" in name_l:
            return "Automated test input from QA platform."
        if "subject" in name_l or "title" in name_l:
            return "Automated Test Entry"
        if "name" in name_l or "name" in id_l:
            return "Test User"
        if "date" in name_l or inp_type == "date":
            return "2025-01-15"
        if "url" in name_l or inp_type == "url":
            return "https://example.com"
        return "Automated Test Input"

    def _pick_assert_value(self, api):
        """
        Choose a safe assert value for a test step.

        Root cause of all the 'statusCode' failures:
          APIs were first captured when they returned 401/500 errors.
          The error body {"statusCode": 401, "message": "..."} was saved as
          response_schema. The old code used keys[0] = "statusCode" as the
          assert value, so Playwright looked for "statusCode" in the rendered
          HTML — which it never contains.

        Fix:
          1. Skip error-envelope keys from response_schema.
          2. If no good key, derive a human word from the URL pattern.
          3. For :id routes return "" — detail page content varies by record.
          4. Return "" as last resort — Playwright just verifies page loads.
        """
        response_schema = api.get("response_schema", {})
        url_pattern = api.get("url_pattern", "")

        # Step 1: find a non-error key in response_schema
        if response_schema and isinstance(response_schema, dict):
            good_keys = [
                k for k in response_schema.keys()
                if k.lower() not in _ERROR_ENVELOPE_KEYS
                and not k.startswith("_")
            ]
            if good_keys:
                return good_keys[0]

        # Step 2: detail routes — content is record-specific, skip assert
        if ':id' in url_pattern:
            return ""

        # Step 3: derive from URL last meaningful segment
        segments = [
            s for s in url_pattern.strip('/').split('/')
            if s and s not in _SKIP_SEGMENTS and s != ':id'
        ]
        if segments:
            word = segments[-1].replace('-', ' ').replace('_', ' ')
            if len(word) <= 20:
                return word.title()

        return ""

    def _best_page_for_api(self, api, pages, first_page):
        """Find the page most likely to have triggered this API endpoint."""
        from urllib.parse import urlparse

        trigger_url = api.get("request_schema", {}).get("_trigger_page_url", "")
        url_pattern = api.get("url_pattern", "")

        # 1. Exact trigger page match
        if trigger_url:
            for page in pages:
                if (page["url"].split('#')[0].split('?')[0]
                        == trigger_url.split('#')[0].split('?')[0]):
                    return page
            return {"url": trigger_url, "title": "App Page", "forms": [], "buttons": []}

        # 2. Path substring match (first non-generic segment)
        api_segs = [s for s in url_pattern.strip('/').split('/') if s not in _SKIP_SEGMENTS and s != ':id']
        if api_segs:
            first_seg = api_segs[0]
            for page in pages:
                if first_seg in urlparse(page["url"]).path:
                    return page

        return first_page

    def _site_has(self, pages_data, keywords):
        if not keywords or not pages_data:
            return False
        keywords_lower = [k.lower() for k in keywords]
        
        for page in pages_data.get("pages", []):
            url = page.get("url", "")
            title = page.get("title", "")
            if any(k in url.lower() for k in keywords_lower):
                return True
            if any(k in title.lower() for k in keywords_lower):
                return True
            for btn in page.get("buttons", []):
                btn_text = btn.get("text", "")
                if any(k in btn_text.lower() for k in keywords_lower):
                    return True
                    
        for api in pages_data.get("api_endpoints", []):
            url_pattern = api.get("url_pattern", "")
            if any(k in url_pattern.lower() for k in keywords_lower):
                return True
                
        return False

    def _find_page(self, pages_data, keywords):
        if not pages_data:
            return None
        keywords_lower = [k.lower() for k in keywords]
        exclusions = ["policy", "policies", "terms", "privacy", "legal", "grievance", "faq", "help", "about", "blog", "-agreement"]
        
        for page in pages_data.get("pages", []):
            url = page.get("url", "")
            title = page.get("title", "")
            url_lower = url.lower()
            title_lower = title.lower()
            
            # Exclude informational/policy pages
            if any(ex in url_lower or ex in title_lower for ex in exclusions):
                continue
                
            if any(k in url_lower or k in title_lower for k in keywords_lower):
                return page
        return None

    def _find_button_on_page(self, page, keywords):
        if not page:
            return None
        keywords_lower = [k.lower() for k in keywords]
        for btn in page.get("buttons", []):
            btn_text = btn.get("text", "")
            if any(k in btn_text.lower() for k in keywords_lower):
                return btn.get("selector")
        return None

    def _find_button_anywhere(self, pages_data, keywords):
        if not pages_data:
            return None, None
        keywords_lower = [k.lower() for k in keywords]
        for page in pages_data.get("pages", []):
            sel = self._find_button_on_page(page, keywords)
            if sel:
                return sel, page.get("url", "")
        return None, None

    def _find_form_field_on_page(self, page, keywords):
        if not page:
            return None
        keywords_lower = [k.lower() for k in keywords]
        for form in page.get("forms", []):
            for field in form.get("fields", []):
                name = field.get("name", "")
                fid = field.get("id", "")
                if any(k in name.lower() or k in fid.lower() for k in keywords_lower):
                    return f"#{fid}" if fid else f"input[name='{name}']"
        return None

    def _find_form_field_anywhere(self, pages_data, keywords):
        if not pages_data:
            return None, None
        keywords_lower = [k.lower() for k in keywords]
        for page in pages_data.get("pages", []):
            sel = self._find_form_field_on_page(page, keywords)
            if sel:
                return sel, page.get("url", "")
        return None, None

    # ------------------------------------------------------------------ #
    # Deterministic fallback generator                                     #
    # ------------------------------------------------------------------ #

    def generate_fallback_test_cases(self, pages_data):
        """
        Generates comprehensive test cases without any LLM.

        Sections:
          1. Page load test per discovered page
          2. Positive + negative form submission per form
          3. Button click tests (up to 3 per page)
          4. One targeted test per API endpoint based on HTTP method:
               GET    → navigate + wait + assert schema key + screenshot
               POST   → form-fill + submit (or navigate + assert if no form)
               POST   → negative empty-field test
               PUT/PATCH → update flow
               DELETE → navigate + click delete button (if found)
               AUTH   → 401 scenario stub

        Wait times are kept short (800ms / 500ms) to minimise total run time.
        """
        test_cases = []
        pages = pages_data.get("pages", [])
        api_endpoints = pages_data.get("api_endpoints", [])
        industry = self._classify_industry(pages_data)

        if not pages and not api_endpoints:
            return test_cases, industry

        first_page = pages[0] if pages else {
            "url": "", "title": "App", "forms": [], "buttons": [], "page_type": "general"
        }

        # ---- SECTION 1: Page load tests ----
        for page in pages:
            url = page.get("url", "")
            title = page.get("title", "") or "Page"
            if not url:
                continue
            test_cases.append({
                "title": f"Verify Page Loads: {title}",
                "steps": [
                    {"action": "navigate", "selector": "", "target": url, "value": ""},
                    {"action": "wait", "selector": "", "target": "", "value": "800"},
                    {"action": "assert", "selector": "body", "target": "", "value": title[:30] if title else ""},
                    {"action": "screenshot", "selector": "", "target": "", "value": f"page_{title[:20]}"},
                ],
                "expected_result": f"Page '{title}' loads without errors and content is visible."
            })

        # ---- SECTION 2: Form tests ----
        for page in pages:
            for form in page.get("forms", []):
                form_id = form.get("id", "")
                if not form_id or form_id == "standalone_fields":
                    continue

                fields = form.get("fields", [])
                page_url = page.get("url", "")
                page_title = page.get("title", "") or "Page"

                # Find submit button
                submit_sel = f"#{form_id} button[type='submit']"
                for btn in page.get("buttons", []):
                    bt = btn.get("text", "").lower()
                    if any(k in bt for k in ["submit", "login", "sign in", "save", "create", "add", "send"]):
                        submit_sel = btn.get("selector", submit_sel)
                        break

                # Positive test
                pos_steps = [{"action": "navigate", "selector": "", "target": page_url, "value": ""}]
                for f in fields:
                    sel = f"#{f['id']}" if f.get("id") else f"input[name='{f.get('name', '')}']"
                    pos_steps.append({
                        "action": "fill", "selector": sel, "target": "",
                        "value": self._make_fill_value(f.get("name"), f.get("id"), f.get("type", "text"))
                    })
                pos_steps += [
                    {"action": "click", "selector": submit_sel, "target": "", "value": ""},
                    {"action": "wait", "selector": "", "target": "", "value": "800"},
                    {"action": "assert", "selector": "body", "target": "", "value": ""},
                    {"action": "screenshot", "selector": "", "target": "", "value": f"form_{form_id}_success"},
                ]
                test_cases.append({
                    "title": f"Verify Form Submission (Valid): {form_id} on {page_title}",
                    "steps": pos_steps,
                    "expected_result": f"Form '{form_id}' accepts valid inputs and submits without errors."
                })

                # Negative test (invalid email)
                has_email = any(
                    "email" in (f.get("name") or "").lower()
                    or "email" in (f.get("id") or "").lower()
                    or f.get("type") == "email"
                    for f in fields
                )
                if has_email:
                    neg_steps = [{"action": "navigate", "selector": "", "target": page_url, "value": ""}]
                    for f in fields:
                        sel = f"#{f['id']}" if f.get("id") else f"input[name='{f.get('name', '')}']"
                        name_l = (f.get("name") or "").lower()
                        id_l = (f.get("id") or "").lower()
                        t = f.get("type", "text")
                        val = "not-a-valid-email" if ("email" in name_l or "email" in id_l or t == "email") else ""
                        neg_steps.append({"action": "fill", "selector": sel, "target": "", "value": val})
                    neg_steps += [
                        {"action": "click", "selector": submit_sel, "target": "", "value": ""},
                        {"action": "wait", "selector": "", "target": "", "value": "500"},
                        {"action": "assert", "selector": "body", "target": "", "value": ""},
                    ]
                    test_cases.append({
                        "title": f"Verify Form Validation (Invalid Email): {form_id} on {page_title}",
                        "steps": neg_steps,
                        "expected_result": f"Form '{form_id}' rejects invalid email and shows a validation error."
                    })

        # ---- SECTION 3: Button click tests (up to 3 per page) ----
        for page in pages:
            count = 0
            for btn in page.get("buttons", []):
                if count >= 3:
                    break
                text = btn.get("text", "")
                sel = btn.get("selector", "")
                if not sel or not text:
                    continue
                text_l = text.lower()
                if any(k in text_l for k in ["submit", "login", "sign in", "logout", "delete", "exit"]):
                    continue
                test_cases.append({
                    "title": f"Verify Button '{text[:30]}' on {page.get('title', 'Page')}",
                    "steps": [
                        {"action": "navigate", "selector": "", "target": page["url"], "value": ""},
                        {"action": "wait", "selector": "", "target": "", "value": "800"},
                        {"action": "click", "selector": sel, "target": "", "value": ""},
                        {"action": "wait", "selector": "", "target": "", "value": "500"},
                        {"action": "assert", "selector": "body", "target": "", "value": ""},
                    ],
                    "expected_result": f"Clicking '{text}' triggers expected action without errors."
                })
                count += 1

        # ---- SECTION 4: Industry Flows ----
        pre_section_4_count = len(test_cases)
        if industry == "E-commerce":
            # Flow 1: Add to cart -> checkout -> payment -> confirmation
            if self._site_has(pages_data, ["cart", "checkout", "buy", "add to cart"]):
                add_to_cart_sel, add_page = self._find_button_anywhere(pages_data, ["add to cart", "add to bag", "buy now", "purchase"])
                checkout_sel, _ = self._find_button_anywhere(pages_data, ["checkout", "cart", "bag", "basket", "go to checkout"])
                pay_sel, _ = self._find_button_anywhere(pages_data, ["pay", "purchase", "order", "place order", "submit"])
                if add_to_cart_sel and checkout_sel and pay_sel and add_page:
                    test_cases.append({
                        "title": "Verify Add to Cart and Checkout Journey",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": add_page, "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "click", "selector": add_to_cart_sel, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "500"},
                            {"action": "click", "selector": checkout_sel, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "click", "selector": pay_sel, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "confirm"},
                            {"action": "screenshot", "selector": "", "target": "", "value": "order_confirmation"},
                        ],
                        "expected_result": "Item is successfully added to the cart, payment details submitted, and order confirmation is displayed."
                    })
            
            # Flow 2: Cart total correctness
            if self._site_has(pages_data, ["cart", "total", "price"]):
                cart_page = self._find_page(pages_data, ["cart", "checkout", "basket", "bag"])
                if cart_page:
                    test_cases.append({
                        "title": "Verify Cart Total Correctness",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": cart_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "total"},
                            {"action": "screenshot", "selector": "", "target": "", "value": "cart_total_display"},
                        ],
                        "expected_result": "The cart totals area is present and displays a value correctly."
                    })
                    
            # Flow 3: Empty-cart checkout
            if self._site_has(pages_data, ["checkout", "cart"]):
                cart_page = self._find_page(pages_data, ["cart", "checkout", "basket", "bag"])
                checkout_sel, _ = self._find_button_anywhere(pages_data, ["checkout", "pay", "buy"])
                if cart_page and checkout_sel:
                    test_cases.append({
                        "title": "Verify Empty-Cart Checkout Handling",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": cart_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "click", "selector": checkout_sel, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "500"},
                            {"action": "assert", "selector": "body", "target": "", "value": "empty"},
                        ],
                        "expected_result": "Attempting checkout with an empty cart is blocked and displays empty message."
                    })
                    
            # Flow 4: Out-of-stock handling
            if self._site_has(pages_data, ["stock", "sold out", "unavailable", "product"]):
                prod_page = self._find_page(pages_data, ["sold-out", "soldout", "unavailable", "out-of-stock"])
                btn_sel, btn_page = self._find_button_anywhere(pages_data, ["sold out", "unavailable", "out of stock"])
                target_url = btn_page or (prod_page["url"] if prod_page else None)
                if target_url:
                    test_cases.append({
                        "title": "Verify Out-of-Stock Product Handling",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": target_url, "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "unavailable"},
                        ],
                        "expected_result": "Out of stock or unavailable product status is correctly shown and cannot be added to cart."
                    })
                    
            # Flow 5: Discount code
            if self._site_has(pages_data, ["coupon", "promo", "discount", "code"]):
                coupon_field, field_page = self._find_form_field_anywhere(pages_data, ["coupon", "promo", "discount", "code"])
                apply_btn_sel, _ = self._find_button_anywhere(pages_data, ["apply", "submit", "promo", "coupon", "code"])
                if coupon_field and apply_btn_sel and field_page:
                    test_cases.append({
                        "title": "Verify Discount Code Application",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": field_page, "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "fill", "selector": coupon_field, "target": "", "value": "TESTDISCOUNT"},
                            {"action": "click", "selector": apply_btn_sel, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "discount"},
                        ],
                        "expected_result": "Applying discount code updates the totals or shows a validation message."
                    })

        elif industry == "FinTech":
            # Flow 1: Login with 2FA present
            if self._site_has(pages_data, ["login", "sign in", "otp", "2fa", "verify"]):
                login_page = self._find_page(pages_data, ["login", "sign-in", "signin"])
                username_field = self._find_form_field_on_page(login_page, ["email", "username", "login"])
                password_field = self._find_form_field_on_page(login_page, ["password"])
                login_btn = self._find_button_on_page(login_page, ["login", "sign in", "submit"])
                if login_page and username_field and password_field and login_btn:
                    test_cases.append({
                        "title": "Verify Login with 2FA Challenge",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": login_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "fill", "selector": username_field, "target": "", "value": "testuser@example.com"},
                            {"action": "fill", "selector": password_field, "target": "", "value": "Secr3tP@ss123"},
                            {"action": "click", "selector": login_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "verify"},
                            {"action": "screenshot", "selector": "", "target": "", "value": "2fa_challenge_screen"},
                        ],
                        "expected_result": "Entering correct primary login credentials prompts for the second-factor authentication step."
                    })
                    
            # Flow 2: Balance display
            if self._site_has(pages_data, ["balance", "account"]):
                dash_page = self._find_page(pages_data, ["dashboard", "account", "balance", "portfolio"])
                if dash_page:
                    test_cases.append({
                        "title": "Verify Dashboard Account Balance Display",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": dash_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "balance"},
                            {"action": "screenshot", "selector": "", "target": "", "value": "account_balance_display"},
                        ],
                        "expected_result": "Account balance figure is visible and formatted correctly on the main dashboard page."
                    })
                    
            # Flow 3: Transfer with insufficient funds
            if self._site_has(pages_data, ["transfer", "send", "pay", "amount"]):
                transfer_page = self._find_page(pages_data, ["transfer", "send", "pay", "payment"])
                amount_field = self._find_form_field_on_page(transfer_page, ["amount", "value", "quantity"])
                send_btn = self._find_button_on_page(transfer_page, ["transfer", "send", "pay", "submit"])
                if transfer_page and amount_field and send_btn:
                    test_cases.append({
                        "title": "Verify Transfer and Payment with Insufficient Funds",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": transfer_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "fill", "selector": amount_field, "target": "", "value": "9999999"},
                            {"action": "click", "selector": send_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "exceeds"},
                        ],
                        "expected_result": "Attempting to transfer or pay an amount exceeding the balance is blocked and displays insufficient funds error."
                    })
                    
            # Flow 4: Transaction history integrity
            if self._site_has(pages_data, ["transaction", "history", "statement"]):
                history_page = self._find_page(pages_data, ["transaction", "history", "statement", "ledger"])
                if history_page:
                    test_cases.append({
                        "title": "Verify Transaction History Integrity",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": history_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "transaction"},
                            {"action": "screenshot", "selector": "", "target": "", "value": "transaction_history_display"},
                        ],
                        "expected_result": "Transaction history list or statement items are populated on the page."
                    })
                    
            # Flow 5: Idle session timeout
            if self._site_has(pages_data, ["login", "dashboard", "account"]):
                dash_page = self._find_page(pages_data, ["dashboard", "account"])
                if dash_page:
                    test_cases.append({
                        "title": "Verify Dashboard Session Timeout Protection",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": dash_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "dashboard"},
                            {"action": "wait", "selector": "", "target": "", "value": "500"},
                            {"action": "screenshot", "selector": "", "target": "", "value": "dashboard_session_state"},
                        ],
                        "expected_result": "Protected dashboard session behaves safely and ensures standard re-auth rules are active."
                    })

        elif industry == "Healthcare":
            # Flow 1: Appointment booking + cancellation
            if self._site_has(pages_data, ["appointment", "book", "schedule"]):
                book_page = self._find_page(pages_data, ["appointment", "book", "schedule"])
                book_btn = self._find_button_on_page(book_page, ["book", "schedule", "reserve"])
                cancel_btn = self._find_button_on_page(book_page, ["cancel", "reschedule", "delete"])
                if book_page and book_btn and cancel_btn:
                    test_cases.append({
                        "title": "Verify Appointment Booking and Cancellation Flow",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": book_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "click", "selector": book_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "confirmed"},
                            {"action": "click", "selector": cancel_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "cancel"},
                        ],
                        "expected_result": "Appointment booking registers successfully, and cancellation correctly releases the slot."
                    })
                    
            # Flow 2: Patient record access control (highest value)
            if self._site_has(pages_data, ["patient", "record", "profile", "medical"]):
                record_page = self._find_page(pages_data, ["patient", "record", "profile", "medical"])
                if record_page:
                    base_url = record_page["url"]
                    mod_url = base_url + "99999" if base_url.endswith("/") else base_url + "/99999"
                    test_cases.append({
                        "title": "[Access Control] [HIGH IMPORTANCE] Verify Patient Record Access Control Boundary",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": mod_url, "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "denied"},
                        ],
                        "expected_result": "Accessing a patient record ID that does not belong to the logged-in user is denied/blocked."
                    })
                    
            # Flow 3: Medical form validation
            if self._site_has(pages_data, ["patient", "form", "medical", "date"]):
                form_page = self._find_page(pages_data, ["patient", "form", "medical", "intake"])
                date_field = self._find_form_field_on_page(form_page, ["date", "birth", "dob"])
                submit_btn = self._find_button_on_page(form_page, ["submit", "save", "next"])
                if form_page and date_field and submit_btn:
                    test_cases.append({
                        "title": "Verify Medical Form Validation on Invalid Inputs",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": form_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "fill", "selector": date_field, "target": "", "value": "9999-99-99"},
                            {"action": "click", "selector": submit_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "invalid"},
                        ],
                        "expected_result": "Entering invalid data formats (like an out-of-range date) into the medical form is rejected."
                    })

        elif industry == "Recruitment":
            # Flow 1: Job application submission
            if self._site_has(pages_data, ["apply", "application", "job", "candidate"]):
                job_page = self._find_page(pages_data, ["job", "apply", "career", "vacancy"])
                apply_btn = self._find_button_on_page(job_page, ["apply", "submit", "apply now"])
                if job_page and apply_btn:
                    test_cases.append({
                        "title": "Verify Job Application Submission",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": job_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "click", "selector": apply_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "submit"},
                        ],
                        "expected_result": "Submitting a job application completes successfully and displays confirmation."
                    })
                    
            # Flow 2: Resume upload limits
            if self._site_has(pages_data, ["resume", "upload", "cv", "attach"]):
                upload_page = self._find_page(pages_data, ["upload", "resume", "cv", "apply"])
                upload_field = self._find_form_field_on_page(upload_page, ["resume", "cv", "upload", "file"])
                if upload_page and upload_field:
                    test_cases.append({
                        "title": "Verify Resume Upload Restrictions and File Limits",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": upload_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "fill", "selector": upload_field, "target": "", "value": "invalid_file_type.exe"},
                            {"action": "wait", "selector": "", "target": "", "value": "500"},
                            {"action": "assert", "selector": "body", "target": "", "value": "invalid"},
                        ],
                        "expected_result": "Valid files are accepted while invalid file types or oversized files are rejected."
                    })
                    
            # Flow 3: Candidate status transition
            if self._site_has(pages_data, ["candidate", "status", "stage", "pipeline"]):
                candidate_page = self._find_page(pages_data, ["candidate", "profile", "stage", "pipeline"])
                status_btn = self._find_button_on_page(candidate_page, ["status", "stage", "move", "advance", "hire", "reject"])
                if candidate_page and status_btn:
                    test_cases.append({
                        "title": "Verify Candidate Status Pipeline Transition",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": candidate_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "click", "selector": status_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "stage"},
                            {"action": "screenshot", "selector": "", "target": "", "value": "candidate_stage_updated"},
                        ],
                        "expected_result": "Modifying a candidate's pipeline status stage persists the change correctly."
                    })
                    
            # Flow 4: Duplicate-application prevention
            if self._site_has(pages_data, ["apply", "application", "job"]):
                job_page = self._find_page(pages_data, ["job", "apply", "career"])
                apply_btn = self._find_button_on_page(job_page, ["apply", "submit"])
                if job_page and apply_btn:
                    test_cases.append({
                        "title": "Verify Prevention of Duplicate Job Applications",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": job_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "click", "selector": apply_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "500"},
                            {"action": "click", "selector": apply_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "applied"},
                        ],
                        "expected_result": "Submitting a second application to the same job displays a duplicate application warning."
                    })

        elif industry == "HR":
            # Flow 1: Leave request -> approval
            if self._site_has(pages_data, ["leave", "request", "approve", "time off"]):
                leave_page = self._find_page(pages_data, ["leave", "request", "timeoff", "time-off"])
                request_btn = self._find_button_on_page(leave_page, ["request", "submit", "apply"])
                approve_btn = self._find_button_on_page(leave_page, ["approve", "accept", "confirm"])
                if leave_page and request_btn and approve_btn:
                    test_cases.append({
                        "title": "Verify Leave Request Submission and Approval Journey",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": leave_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "click", "selector": request_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "click", "selector": approve_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "approved"},
                        ],
                        "expected_result": "Submitting a leave request is confirmed, and approval updates status to approved."
                    })
                    
            # Flow 2: Payroll figure display
            if self._site_has(pages_data, ["payroll", "salary", "pay"]):
                payroll_page = self._find_page(pages_data, ["payroll", "salary", "payslip", "pay"])
                if payroll_page:
                    test_cases.append({
                        "title": "Verify Payroll and Salary Figures Display",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": payroll_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "payroll"},
                            {"action": "screenshot", "selector": "", "target": "", "value": "payroll_figures"},
                        ],
                        "expected_result": "Payroll values, payslip details, or salary figures are visible on the payroll dashboard."
                    })
                    
            # Flow 3: Attendance edit permissions (Access Control)
            if self._site_has(pages_data, ["attendance", "timesheet", "clock"]):
                timesheet_page = self._find_page(pages_data, ["attendance", "timesheet", "clock"])
                edit_btn = self._find_button_on_page(timesheet_page, ["edit", "modify", "update timesheet"])
                if timesheet_page and edit_btn:
                    test_cases.append({
                        "title": "[Access Control] Verify Attendance/Timesheet Edit Permissions",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": timesheet_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "click", "selector": edit_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "unauthorized"},
                        ],
                        "expected_result": "Unauthorized edits to timesheets or clock-in records are blocked."
                    })

        elif industry == "SaaS":
            # Flow 1: User invite / onboarding
            if self._site_has(pages_data, ["invite", "member", "team", "user"]):
                team_page = self._find_page(pages_data, ["team", "member", "user", "invite"])
                invite_btn = self._find_button_on_page(team_page, ["invite", "add member", "add user", "send invite"])
                if team_page and invite_btn:
                    test_cases.append({
                        "title": "Verify User Invite and Onboarding Flow",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": team_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "click", "selector": invite_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "success"},
                        ],
                        "expected_result": "The team member invitation flow completes and displays confirmation."
                    })
                    
            # Flow 2: Role-permission boundary (Access Control)
            if self._site_has(pages_data, ["role", "permission", "admin", "settings"]):
                settings_page = self._find_page(pages_data, ["admin", "settings", "security", "roles"])
                restricted_btn = self._find_button_on_page(settings_page, ["save", "update settings", "edit roles"])
                if settings_page and restricted_btn:
                    test_cases.append({
                        "title": "[Access Control] Verify Role-Permission Boundaries and Restricted Actions",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": settings_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "click", "selector": restricted_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "denied"},
                        ],
                        "expected_result": "Restricted settings actions are blocked for low-permission contexts."
                    })
                    
            # Flow 3: Settings persistence
            if self._site_has(pages_data, ["settings", "preferences", "config"]):
                settings_page = self._find_page(pages_data, ["settings", "preferences", "config"])
                setting_field = self._find_form_field_on_page(settings_page, ["settings", "preferences", "name", "theme"])
                save_btn = self._find_button_on_page(settings_page, ["save", "update", "confirm", "save settings"])
                if settings_page and setting_field and save_btn:
                    test_cases.append({
                        "title": "Verify Settings Persistence After Reload",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": settings_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "fill", "selector": setting_field, "target": "", "value": "Test Setting Value"},
                            {"action": "click", "selector": save_btn, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "navigate", "selector": "", "target": settings_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "Test Setting Value"},
                        ],
                        "expected_result": "A changed user setting persists and is correctly shown after navigating away and back."
                    })
                    
            # Flow 4: Subscription / billing state
            if self._site_has(pages_data, ["subscription", "billing", "plan", "upgrade"]):
                billing_page = self._find_page(pages_data, ["billing", "subscription", "plan", "upgrade"])
                if billing_page:
                    test_cases.append({
                        "title": "Verify Subscription and Billing State Display",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": billing_page["url"], "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": "billing"},
                            {"action": "screenshot", "selector": "", "target": "", "value": "billing_plan_state"},
                        ],
                        "expected_result": "The active plan and subscription/billing state is correctly displayed."
                    })

        # ---- SECTION 5: One test per API endpoint ----
        seen_patterns = set()

        for api in api_endpoints:
            method = api.get("method", "GET").upper()
            url_pattern = api.get("url_pattern", "")
            auth_type = api.get("auth_type", "none")

            if not url_pattern:
                continue

            dedup_key = f"{method}:{url_pattern}"
            if dedup_key in seen_patterns:
                continue
            seen_patterns.add(dedup_key)

            # FIX: use _pick_assert_value() which filters error-envelope keys
            assert_val = self._pick_assert_value(api)
            best_page = self._best_page_for_api(api, pages, first_page)
            page_url = best_page.get("url", "")
            page_title = best_page.get("title", "") or "Page"

            # Find a form on the page for POST/PUT tests
            matching_form = None
            for form in best_page.get("forms", []):
                if form.get("id") and form.get("id") != "standalone_fields" and form.get("fields"):
                    matching_form = form
                    break

            screenshot_key = f"get_{url_pattern.replace('/', '_')[:28]}"

            # ---------- GET ----------
            if method in ("GET", "HEAD"):
                test_cases.append({
                    "title": f"Verify GET {url_pattern} — Data Loads on {page_title}",
                    "steps": [
                        {"action": "navigate", "selector": "", "target": page_url, "value": ""},
                        {"action": "wait", "selector": "", "target": "", "value": "800"},
                        {"action": "assert", "selector": "body", "target": "", "value": assert_val},
                        {"action": "screenshot", "selector": "", "target": "", "value": screenshot_key},
                    ],
                    "expected_result": f"GET {url_pattern} returns data and page displays expected content."
                })

                # 401 scenario for auth-protected endpoints
                if auth_type and auth_type != "none":
                    test_cases.append({
                        "title": f"Verify GET {url_pattern} — Returns 401 Without Authentication",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": page_url, "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "500"},
                            {"action": "assert", "selector": "body", "target": "", "value": ""},
                        ],
                        "expected_result": f"Unauthenticated access to GET {url_pattern} is rejected."
                    })

            # ---------- POST ----------
            elif method == "POST":
                if matching_form:
                    fields = matching_form.get("fields", [])
                    form_id = matching_form.get("id", "form")
                    submit_sel = f"#{form_id} button[type='submit']"
                    for btn in best_page.get("buttons", []):
                        bt = btn.get("text", "").lower()
                        if any(k in bt for k in ["submit", "save", "create", "add", "send", "login"]):
                            submit_sel = btn.get("selector", submit_sel)
                            break

                    # Positive POST
                    steps = [{"action": "navigate", "selector": "", "target": page_url, "value": ""}]
                    for f in fields:
                        sel = f"#{f['id']}" if f.get("id") else f"input[name='{f.get('name', '')}']"
                        steps.append({
                            "action": "fill", "selector": sel, "target": "",
                            "value": self._make_fill_value(f.get("name"), f.get("id"), f.get("type", "text"))
                        })
                    steps += [
                        {"action": "click", "selector": submit_sel, "target": "", "value": ""},
                        {"action": "wait", "selector": "", "target": "", "value": "800"},
                        {"action": "assert", "selector": "body", "target": "", "value": assert_val},
                        {"action": "screenshot", "selector": "", "target": "",
                         "value": f"post_{url_pattern.replace('/', '_')[:25]}_ok"},
                    ]
                    test_cases.append({
                        "title": f"Verify POST {url_pattern} — Create With Valid Data",
                        "steps": steps,
                        "expected_result": f"POST {url_pattern} creates resource and returns success."
                    })

                    # Negative POST
                    test_cases.append({
                        "title": f"Verify POST {url_pattern} — Empty Fields Shows Validation Error",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": page_url, "value": ""},
                            {"action": "click", "selector": submit_sel, "target": "", "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "500"},
                            {"action": "assert", "selector": "body", "target": "", "value": ""},
                        ],
                        "expected_result": f"POST {url_pattern} rejects empty payload with validation error."
                    })
                else:
                    test_cases.append({
                        "title": f"Verify POST {url_pattern} — Endpoint Reachable from {page_title}",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": page_url, "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": assert_val},
                        ],
                        "expected_result": f"Page for POST {url_pattern} loads and endpoint is reachable."
                    })

            # ---------- PUT / PATCH ----------
            elif method in ("PUT", "PATCH"):
                if matching_form:
                    fields = matching_form.get("fields", [])
                    form_id = matching_form.get("id", "form")
                    submit_sel = f"#{form_id} button[type='submit']"
                    for btn in best_page.get("buttons", []):
                        bt = btn.get("text", "").lower()
                        if any(k in bt for k in ["update", "save", "edit", "apply", "confirm"]):
                            submit_sel = btn.get("selector", submit_sel)
                            break

                    steps = [{"action": "navigate", "selector": "", "target": page_url, "value": ""}]
                    for f in fields:
                        sel = f"#{f['id']}" if f.get("id") else f"input[name='{f.get('name', '')}']"
                        val = self._make_fill_value(f.get("name"), f.get("id"), f.get("type", "text"))
                        t = f.get("type", "text")
                        if t not in ("email", "password", "tel", "date", "number", "url"):
                            val = f"Updated {val}"
                        steps.append({"action": "fill", "selector": sel, "target": "", "value": val})
                    steps += [
                        {"action": "click", "selector": submit_sel, "target": "", "value": ""},
                        {"action": "wait", "selector": "", "target": "", "value": "800"},
                        {"action": "assert", "selector": "body", "target": "", "value": assert_val},
                    ]
                    test_cases.append({
                        "title": f"Verify {method} {url_pattern} — Update Resource Successfully",
                        "steps": steps,
                        "expected_result": f"{method} {url_pattern} updates resource and confirms change."
                    })
                else:
                    test_cases.append({
                        "title": f"Verify {method} {url_pattern} — Update Accessible from {page_title}",
                        "steps": [
                            {"action": "navigate", "selector": "", "target": page_url, "value": ""},
                            {"action": "wait", "selector": "", "target": "", "value": "800"},
                            {"action": "assert", "selector": "body", "target": "", "value": assert_val},
                        ],
                        "expected_result": f"Page for {method} {url_pattern} loads and allows editing."
                    })

            # ---------- DELETE ----------
            elif method == "DELETE":
                delete_btn = None
                for btn in best_page.get("buttons", []):
                    bt = btn.get("text", "").lower()
                    if any(k in bt for k in ["delete", "remove", "archive", "deactivate"]):
                        delete_btn = btn
                        break

                steps = [
                    {"action": "navigate", "selector": "", "target": page_url, "value": ""},
                    {"action": "wait", "selector": "", "target": "", "value": "800"},
                ]
                if delete_btn:
                    steps += [
                        {"action": "click", "selector": delete_btn["selector"], "target": "", "value": ""},
                        {"action": "wait", "selector": "", "target": "", "value": "800"},
                    ]
                steps.append({"action": "assert", "selector": "body", "target": "", "value": ""})

                test_cases.append({
                    "title": f"Verify DELETE {url_pattern} — Resource Removed Successfully",
                    "steps": steps,
                    "expected_result": f"DELETE {url_pattern} removes the resource and confirms deletion."
                })

            # ---------- Other methods ----------
            else:
                test_cases.append({
                    "title": f"Verify {method} {url_pattern} — Endpoint Accessible",
                    "steps": [
                        {"action": "navigate", "selector": "", "target": page_url, "value": ""},
                        {"action": "wait", "selector": "", "target": "", "value": "800"},
                        {"action": "assert", "selector": "body", "target": "", "value": assert_val},
                    ],
                    "expected_result": f"{method} {url_pattern} is reachable and returns expected response."
                })

        # Tag fallback test categories
        for idx, tc in enumerate(test_cases):
            if idx >= pre_section_4_count:
                title = tc.get("title", "")
                if title.startswith("[Access Control]"):
                    tc["category"] = "Access Control"
                else:
                    tc["category"] = "Industry Flow"
            else:
                tc["category"] = "Generic"

        logger.info(
            f"Fallback generator: {len(test_cases)} test cases, "
            f"{len(api_endpoints)} API endpoints, industry={industry}"
        )
        return test_cases, industry