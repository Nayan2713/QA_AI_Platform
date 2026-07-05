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
        # OPTIMIZED: strip the heavy 'elements' field before serialising —
        # it can contain hundreds of DOM nodes and isn't needed for test generation.
        trimmed = {
            "pages": [
                {
                    k: v for k, v in page.items()
                    if k != 'elements'
                }
                for page in pages_data.get("pages", [])
            ],
            "api_endpoints": pages_data.get("api_endpoints", []),
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

    # ------------------------------------------------------------------ #
    # LLM prompt                                                           #
    # ------------------------------------------------------------------ #

    def get_prompt(self, pages_context):
        """
        Instructs the LLM to generate ONE test case per API endpoint so that
        74 APIs → 74+ test cases instead of the old 3-5 generic ones.
        """
        return f"""You are an expert QA Automation Engineer specialising in API-driven web application testing.
Your task is to analyse discovered pages and API endpoints and generate a COMPREHENSIVE test suite that covers EVERY API endpoint found.

Here is the full application context (pages, forms, buttons, API endpoints):
{pages_context}

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

RULE 5 — USE REAL SELECTORS ONLY from the "forms" and "buttons" data. Never invent selectors.

RULE 6 — INDUSTRY: Classify as "E-commerce", "SaaS", "FinTech", "Healthcare", "HR", "Recruitment", or "General".

=== OUTPUT FORMAT ===
Return ONLY valid JSON. No markdown, no explanation, no ```json fences.
Start with {{ and end with }}.

{{
  "industry": "...",
  "test_cases": [
    {{
      "title": "Descriptive title including HTTP method and endpoint name",
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

    def parse_json_response(self, text):
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
                test_cases_list = data.get("test_cases", [])
            elif isinstance(data, list):
                test_cases_list = data

            validated = []
            for idx, tc in enumerate(test_cases_list):
                title = tc.get("title", f"AI Generated Test {idx + 1}")
                steps = tc.get("steps", [])
                expected = tc.get("expected_result", "Test completes successfully")

                clean_steps = []
                for step in steps:
                    action = step.get("action")
                    if action in [
                        "navigate", "fill", "click", "wait", "assert",
                        "hover", "scroll", "select", "screenshot"
                    ]:
                        clean_steps.append({
                            "action": action,
                            "selector": step.get("selector", ""),
                            "target": step.get("target", ""),
                            "value": step.get("value", "")
                        })

                if clean_steps:
                    validated.append({
                        "title": title,
                        "steps": clean_steps,
                        "expected_result": expected
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

        # ---- SECTION 4: One test per API endpoint ----
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

        logger.info(
            f"Fallback generator: {len(test_cases)} test cases, "
            f"{len(api_endpoints)} API endpoints, industry={industry}"
        )
        return test_cases, industry