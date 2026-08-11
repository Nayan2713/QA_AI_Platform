"""
services/api_test_service.py

Generates API test cases from discovered APIEndpoint rows using the LLM,
then executes them via httpx (already in requirements).
No browser / Playwright needed — just HTTP calls.
"""

import json
import logging
import time

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

# How long to wait for each API call during test execution
REQUEST_TIMEOUT_SECONDS = int(getattr(settings, 'API_TEST_TIMEOUT', 10))


# ─────────────────────────────────────────────────────────────
# Generation
# ─────────────────────────────────────────────────────────────

class APITestGenerator:
    """
    Asks the LLM to produce APITestCase definitions for each endpoint.
    Falls back to deterministic templates if the LLM is unavailable.
    """

    def __init__(self, llm_service=None):
        self.llm = llm_service

    def generate(self, application) -> list:
        """
        Generate APITestCase objects for all endpoints on `application`.
        Returns list of saved APITestCase instances.
        """
        from core.models import APIEndpoint, APITestCase

        endpoints = list(APIEndpoint.objects.filter(application=application))
        if not endpoints:
            logger.info(f"[APITestGen] No endpoints found for app {application.id}")
            return []

        saved = []
        for endpoint in endpoints:
            cases = self._generate_for_endpoint(application, endpoint)
            for case_data in cases:
                obj, created = APITestCase.objects.get_or_create(
                    application=application,
                    method=case_data['method'],
                    url=case_data['url'],
                    title=case_data['title'],
                    defaults={
                        'api_endpoint': endpoint,
                        'headers': case_data.get('headers', {}),
                        'body': case_data.get('body', {}),
                        'expected_status': case_data.get('expected_status', 200),
                        'expected_body_contains': case_data.get('expected_body_contains', []),
                        'auth_required': case_data.get('auth_required', False),
                        'ai_generated': case_data.get('ai_generated', True),
                    }
                )
                if created:
                    saved.append(obj)
                    logger.info(f"[APITestGen] Created: [{obj.method}] {obj.url}")

        logger.info(f"[APITestGen] Generated {len(saved)} new API test cases for app {application.id}")
        return saved

    def _generate_for_endpoint(self, application, endpoint) -> list:
        """Try LLM first, fall back to templates."""
        if self.llm:
            try:
                return self._llm_generate(application, endpoint)
            except Exception as e:
                logger.warning(f"[APITestGen] LLM failed ({e}), using template fallback")

        return self._template_generate(application, endpoint)

    def _llm_generate(self, application, endpoint) -> list:
        """Ask the LLM for test cases in JSON format."""
        prompt = f"""
You are a QA engineer. Generate API test cases for this endpoint.

Application URL: {application.url}
Endpoint: [{endpoint.method}] {endpoint.url_pattern}
Auth type: {endpoint.auth_type or 'unknown'}
Request schema: {json.dumps(endpoint.request_schema)}
Response schema: {json.dumps(endpoint.response_schema)}

Return ONLY a JSON array. Each element must have:
- title: string
- method: string (GET/POST/PUT/DELETE)
- url: string (full URL using {application.base_url} as base)
- headers: object (include Content-Type if needed)
- body: object (request body if POST/PUT)
- expected_status: integer
- expected_body_contains: array of key names to assert exist in response
- auth_required: boolean

Return 2-3 test cases covering: happy path, unauthorized access (if auth_required), and one edge case.
Return ONLY the JSON array. No explanation.
"""
        response = self.llm.client.chat(
            model=self.llm.model,
            messages=[{'role': 'user', 'content': prompt}],
        )
        text = response.get('message', {}).get('content', '') or ''
        # Strip markdown fences
        text = text.strip().lstrip('```json').lstrip('```').rstrip('```').strip()
        data = json.loads(text)
        for item in data:
            item['ai_generated'] = True
        return data

    def _template_generate(self, application, endpoint) -> list:
        """Deterministic fallback — creates sensible tests without LLM."""
        method = endpoint.method.upper()
        url = endpoint.url_pattern

        # Build a full URL from the application base URL + endpoint pattern
        base = application.base_url.rstrip('/')
        # Replace common path param placeholders like {id} or :id with '1'
        clean_url = url.replace('{id}', '1').replace(':id', '1').replace('<id>', '1')
        full_url = base + clean_url if clean_url.startswith('/') else base + '/' + clean_url

        cases = []

        # Happy path
        cases.append({
            'title': f'{method} {url} — happy path',
            'method': method,
            'url': full_url,
            'headers': {'Content-Type': 'application/json'},
            'body': endpoint.request_schema if method in ('POST', 'PUT', 'PATCH') else {},
            'expected_status': 200 if method == 'GET' else 201 if method == 'POST' else 200,
            'expected_body_contains': list(endpoint.response_schema.keys())[:3],
            'auth_required': bool(endpoint.auth_type),
            'ai_generated': False,
        })

        # Unauthorized access test (if auth is expected)
        if endpoint.auth_type:
            cases.append({
                'title': f'{method} {url} — unauthorized (no token)',
                'method': method,
                'url': full_url,
                'headers': {},
                'body': {},
                'expected_status': 401,
                'expected_body_contains': [],
                'auth_required': False,  # deliberately sending NO auth
                'ai_generated': False,
            })

        return cases


# ─────────────────────────────────────────────────────────────
# Execution
# ─────────────────────────────────────────────────────────────

class APITestExecutor:
    """
    Runs an APITestCase via httpx and records the result in APITestRun.
    """

    def __init__(self, auth_token: str = None):
        """
        auth_token: JWT/Bearer token to attach when test.auth_required is True.
        """
        self.auth_token = auth_token

    def run(self, api_test_case) -> 'APITestRun':
        from core.models import APITestRun

        run = APITestRun.objects.create(
            api_test_case=api_test_case,
            status='RUNNING',
        )

        try:
            result = self._execute(api_test_case)
            self._save_result(run, api_test_case, result)
        except Exception as e:
            logger.exception(f"[APITestExec] Exception running test {api_test_case.id}: {e}")
            run.status = 'FAILED'
            run.error = str(e)
            run.passed = False
            run.failure_reason = f"Executor exception: {e}"
            run.save()

        return run

    def _execute(self, test) -> dict:
        """Make the actual HTTP call and return raw result dict."""
        headers = dict(test.headers or {})

        if test.auth_required and self.auth_token:
            headers['Authorization'] = f'Bearer {self.auth_token}'

        method = test.method.upper()
        body = test.body or {}

        start = time.time()
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
                response = client.request(
                    method=method,
                    url=test.url,
                    headers=headers,
                    json=body if method in ('POST', 'PUT', 'PATCH') and body else None,
                )
            elapsed_ms = (time.time() - start) * 1000

            try:
                resp_body = response.text[:5000]  # cap stored body at 5 KB
            except Exception:
                resp_body = ''

            return {
                'actual_status_code': response.status_code,
                'response_body': resp_body,
                'response_time_ms': round(elapsed_ms, 2),
                'error': '',
            }

        except httpx.RequestError as e:
            elapsed_ms = (time.time() - start) * 1000
            return {
                'actual_status_code': None,
                'response_body': '',
                'response_time_ms': round(elapsed_ms, 2),
                'error': str(e),
            }

    def _save_result(self, run, test, result: dict):
        """Evaluate assertions and persist the run."""
        actual_status = result.get('actual_status_code')
        resp_body = result.get('response_body', '')
        error = result.get('error', '')

        failure_reasons = []

        # 1. Status code assertion
        if actual_status is None:
            failure_reasons.append(f"Request failed: {error}")
        elif actual_status != test.expected_status:
            failure_reasons.append(
                f"Expected status {test.expected_status}, got {actual_status}"
            )

        # 2. Body key assertions
        if test.expected_body_contains and actual_status and actual_status < 300:
            try:
                body_json = json.loads(resp_body)
                for key in test.expected_body_contains:
                    if key not in body_json:
                        failure_reasons.append(f"Response missing expected key: '{key}'")
            except json.JSONDecodeError:
                if test.expected_body_contains:
                    failure_reasons.append("Response body is not valid JSON")

        passed = len(failure_reasons) == 0

        run.actual_status_code = actual_status
        run.response_body = resp_body
        run.response_time_ms = result.get('response_time_ms')
        run.error = error
        run.passed = passed
        run.failure_reason = '; '.join(failure_reasons)
        run.status = 'COMPLETED'
        run.save()

        logger.info(
            f"[APITestExec] {'PASS' if passed else 'FAIL'} — "
            f"[{test.method}] {test.url} "
            f"status={actual_status} time={run.response_time_ms}ms"
        )