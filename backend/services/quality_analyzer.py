# backend/services/quality_analyzer.py

import json
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _no_llm_configured():
    """
    Fast check: returns True when no LLM gateway is reachable/configured,
    so we can skip the expensive port-probe + network calls entirely.

    FIX: The original code attempted Ollama (1s socket timeout) + LM Studio
    (1s socket timeout) + OpenAI key validation on EVERY test execution even
    when nothing was configured. With 140 tests that wastes ~4-5 minutes
    purely on failed connection attempts.  This helper short-circuits that
    by checking settings first — no network I/O at all.
    """
    try:
        from django.conf import settings
        openai_key = getattr(settings, 'OPENAI_API_KEY', None)
        # Only consider the key valid if it looks like a real key
        has_openai = (
            openai_key
            and str(openai_key).strip().startswith('sk-')
            and len(str(openai_key).strip()) >= 40
        )
        if has_openai:
            return False  # Cloud OpenAI is configured — LLM is available

        # Check if Ollama port is likely open (cached result per process)
        ollama_url = getattr(settings, 'OLLAMA_API_URL', 'http://localhost:11434/api/generate')
        base_url = ollama_url.split('/api')[0]
        local_url = getattr(settings, 'LOCAL_LLM_API_URL', 'http://localhost:1234/v1')

        import socket
        from urllib.parse import urlparse

        for url in [base_url, local_url]:
            try:
                parsed = urlparse(url)
                host = parsed.hostname or 'localhost'
                port = parsed.port or (80 if parsed.scheme == 'http' else 443)
                with socket.create_connection((host, port), timeout=0.3) as _:
                    return False  # something is listening — LLM may be available
            except Exception:
                continue

        return True  # nothing configured or reachable
    except Exception:
        return True  # fail safe: skip LLM check


class ResponseQualityAnalyzer:

    @staticmethod
    def check_content_errors(status, body_text):
        """
        Scans status codes and response bodies for error flags and
        database/server traces.
        """
        if not body_text:
            return None

        # Status >= 400 is already handled as a network failure separately.
        if status >= 400:
            return None

        # Check JSON-based structures
        try:
            data = json.loads(body_text)
            if isinstance(data, dict):
                # success = false
                if data.get('success') is False or data.get('success') == 'false':
                    return "API response returned success=false flag."

                # explicit error fields
                if 'error' in data or 'errors' in data:
                    err = data.get('error') or data.get('errors')
                    if err:
                        return f"API response contains error field: {err}"

                # status = error / fail
                if data.get('status') in ['error', 'fail']:
                    msg = data.get('message') or data.get('detail') or 'Unknown failure'
                    return f"API status is '{data.get('status')}': {msg}"
        except Exception:
            # Not JSON — check raw text for crash keywords
            lower_body = body_text.lower()

            db_kws = [
                "sql error", "database error", "sqlite3.error",
                "postgresql error", "mysql error", "syntax error near"
            ]
            if any(kw in lower_body for kw in db_kws):
                return "Database error trace or SQL syntax failure found in response body."

            server_kws = [
                "traceback (most recent call", "nullpointerexception",
                "undefined index", "fatal error", "internal server error"
            ]
            if any(kw in lower_body for kw in server_kws):
                return "Internal server exception or crash traceback found in response body."

        return None

    @staticmethod
    def get_json_keys(body_text):
        """
        Parses body text and returns a sorted list of keys from the JSON
        object or from the first element of a JSON array.
        """
        if not body_text:
            return []
        try:
            data = json.loads(body_text)
            if isinstance(data, dict):
                return sorted(list(data.keys()))
            elif isinstance(data, list) and data and isinstance(data[0], dict):
                return sorted(list(data[0].keys()))
        except Exception:
            pass
        return []

    @classmethod
    def detect_schema_regression(cls, current_call, previous_calls):
        """
        Compares current JSON keys with keys from the matching call in the
        previous successful run to detect missing fields.
        """
        url = current_call.get('url')
        method = current_call.get('method')

        parsed_url = urlparse(url)
        normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"

        current_body = current_call.get('body', '')
        current_keys = cls.get_json_keys(current_body)

        if not current_keys:
            return None

        for prev in previous_calls:
            prev_url = prev.get('url', '')
            prev_parsed = urlparse(prev_url)
            prev_normalized = f"{prev_parsed.scheme}://{prev_parsed.netloc}{prev_parsed.path}"

            if prev_normalized == normalized_url and prev.get('method') == method:
                prev_body = prev.get('body', '')
                prev_keys = cls.get_json_keys(prev_body)

                if prev_keys:
                    missing_keys = [k for k in prev_keys if k not in current_keys]
                    if missing_keys:
                        return (
                            f"API schema regression: Missing fields {missing_keys} "
                            f"compared to last successful run."
                        )
        return None

    @staticmethod
    def is_eligible_for_semantic_check(url, base_url):
        """
        Filters out static assets, third-party trackers/libraries, and analytics
        to prevent overloading the local LLM.
        """
        if not url:
            return False

        if base_url:
            try:
                url_host = urlparse(url).hostname
                base_host = urlparse(base_url).hostname
                if not url_host or not base_host:
                    return False
                if not (
                    url_host == base_host
                    or url_host.endswith('.' + base_host)
                    or base_host.endswith('.' + url_host)
                ):
                    return False
            except Exception:
                return False

        path = urlparse(url).path.lower()
        static_exts = [
            '.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg',
            '.woff', '.woff2', '.ttf', '.eot', '.ico', '.json'
        ]
        if any(path.endswith(ext) for ext in static_exts):
            return False

        exclude_keywords = [
            'analytics', 'telemetry', 'sentry', 'mixpanel', 'amplitude',
            'hotjar', 'segment', 'logrocket', 'doubleclick', 'facebook',
            'recaptcha', 'chat', 'intercom', 'drift', 'crisp', 'google-analytics'
        ]
        url_lower = url.lower()
        if any(kw in url_lower for kw in exclude_keywords):
            return False

        return True

    @staticmethod
    def check_semantic_relevance(body_text, expected_result):
        """
        Uses the configured LLM to check if the response data is semantically
        relevant to the expected result.

        FIX: Added upfront _no_llm_configured() guard so this method returns
        immediately (no network I/O) when no LLM is set up.  Previously it
        attempted Ollama (1s socket) + LM Studio (1s socket) on every single
        test execution, wasting 2s × 140 tests = ~5 minutes total.
        """
        if not body_text or not expected_result:
            return None

        if len(body_text) < 150:
            return None

        # FIX: fast exit — no network calls when nothing is configured
        if _no_llm_configured():
            return None

        truncated_body = body_text[:800]

        prompt = f"""You are a QA Semantic Auditor.
Your task is to determine if the actual API response data is semantically relevant to the test case's expected result.

Expected Result/Prompt:
"{expected_result}"

Actual API Response Data:
{truncated_body}

Decide whether the actual API response content is semantically relevant to the expected result.
For example:
- If expected result asks for companies/startups, and the response contains standard company items, it is RELEVANT.
- If expected result asks for companies/startups, and the response contains bakeries or food recipes, it is IRRELEVANT.

Respond with exactly "RELEVANT" or "IRRELEVANT" on the first line, followed by a one-sentence reason on the second line. Do not write any markdown code blocks or intro text.
"""
        try:
            from config.llm_config import get_llm, llm_predict
            llm = get_llm()
            result_text = llm_predict(llm, prompt).strip()
            lines = [l.strip() for l in result_text.split('\n') if l.strip()]
            if lines:
                verdict = lines[0].upper()
                reason = lines[1] if len(lines) > 1 else "LLM did not provide a reason."
                if "IRRELEVANT" in verdict:
                    return f"API output content does not match expectations: {reason}"
        except Exception as e:
            logger.warning(f"LLM semantic check failed: {e}")
        return None

    @classmethod
    def check_schema_conformance(cls, call, app, endpoints_cache=None):
        """
        Validates if the API response body conforms to the discovered
        APIEndpoint schema stored during discovery.
        """
        if not app or not call:
            return None

        url = call.get('url')
        method = call.get('method', 'GET').upper()
        body = call.get('body', '')

        if not body:
            return None

        try:
            from tasks.discovery import get_url_pattern
            url_pattern = get_url_pattern(url, app.url)
        except Exception as err:
            logger.debug(f"Failed to generate url pattern for conformance check: {err}")
            return None

        if endpoints_cache is not None:
            endpoint = endpoints_cache.get((method, url_pattern))
        else:
            from core.models import APIEndpoint
            endpoint = APIEndpoint.objects.filter(
                application=app,
                method=method,
                url_pattern=url_pattern
            ).first()

        if not endpoint or not endpoint.response_schema:
            return None

        # FIX: Skip conformance check if schema only contains error-envelope keys —
        # these were captured from 401/500 responses and don't represent real schemas.
        error_keys = {
            'statuscode', 'status_code', 'message', 'error',
            'errors', 'detail', 'code', 'type', 'stack', 'trace'
        }
        schema_keys_lower = {k.lower() for k in endpoint.response_schema.keys()}
        if schema_keys_lower and schema_keys_lower.issubset(error_keys):
            logger.debug(
                f"Skipping schema conformance for {url_pattern} — "
                f"schema only contains error-envelope keys (captured from error response)."
            )
            return None

        try:
            actual_data = json.loads(body)
            expected_schema = endpoint.response_schema

            actual_obj = actual_data
            if isinstance(actual_data, list):
                if not actual_data:
                    return None
                actual_obj = actual_data[0]

            if not isinstance(actual_obj, dict):
                return (
                    f"API schema mismatch: Expected JSON object or array, "
                    f"got {type(actual_data).__name__}."
                )

            missing_fields = []
            type_mismatches = []

            for expected_key, expected_type_name in expected_schema.items():
                if expected_key.lower() in error_keys:
                    continue  # skip error-envelope keys from schema comparison
                if expected_key not in actual_obj:
                    missing_fields.append(expected_key)
                else:
                    actual_val = actual_obj[expected_key]
                    if actual_val is not None:
                        actual_type_name = type(actual_val).__name__
                        if expected_type_name == 'float' and actual_type_name in ['int', 'float']:
                            continue
                        if expected_type_name == 'str' and actual_type_name == 'str':
                            continue
                        if expected_type_name != actual_type_name:
                            type_mismatches.append(
                                f"'{expected_key}' (expected {expected_type_name}, got {actual_type_name})"
                            )

            if missing_fields or type_mismatches:
                reasons = []
                if missing_fields:
                    reasons.append(f"missing fields: {missing_fields}")
                if type_mismatches:
                    reasons.append(f"type mismatches: {', '.join(type_mismatches)}")
                return f"API response schema conformance failure: {'; '.join(reasons)}"

        except Exception:
            pass

        return None

    @classmethod
    def analyze_response_quality(
        cls, current_calls, previous_calls,
        expected_result=None, base_url=None, app=None,
        endpoints_cache=None
    ):
        """
        Runs all quality scans and returns a list of detected warnings and errors.

        FIX: Semantic relevance check now short-circuits immediately when no
        LLM is configured, instead of spending 2s probing dead ports per test.
        """
        issues = []

        for call in current_calls:
            url = call.get('url')
            method = call.get('method')
            status = call.get('status', 200)
            body = call.get('body', '')
            latency = call.get('latency', 0)

            # 1. Content errors
            content_err = cls.check_content_errors(status, body)
            if content_err:
                issues.append({
                    "url": url, "method": method,
                    "type": "content_error", "issue": content_err
                })

            # 2. Latency warnings (> 2000ms)
            if latency > 2000:
                issues.append({
                    "url": url, "method": method,
                    "type": "latency_warning",
                    "issue": f"High response latency detected ({latency}ms)."
                })

            # 3. Schema regression (vs previous successful run)
            if previous_calls:
                regression = cls.detect_schema_regression(call, previous_calls)
                if regression:
                    issues.append({
                        "url": url, "method": method,
                        "type": "schema_regression", "issue": regression
                    })

            # 4. Schema conformance (vs discovered API schema)
            if app:
                conformance_issue = cls.check_schema_conformance(call, app, endpoints_cache=endpoints_cache)
                if conformance_issue:
                    issues.append({
                        "url": url, "method": method,
                        "type": "schema_conformance", "issue": conformance_issue
                    })

        # 5. Semantic relevance — only runs when LLM is actually configured
        if expected_result and not _no_llm_configured():
            eligible_calls = [
                call for call in current_calls
                if cls.is_eligible_for_semantic_check(call.get('url'), base_url)
                and len(call.get('body', '')) >= 150
            ]

            if eligible_calls:
                # Use the largest response body as the main data payload
                eligible_calls.sort(key=lambda x: len(x.get('body', '')), reverse=True)
                target_call = eligible_calls[0]

                semantic_err = cls.check_semantic_relevance(
                    target_call.get('body', ''),
                    expected_result
                )
                if semantic_err:
                    issues.append({
                        "url": target_call.get('url'),
                        "method": target_call.get('method'),
                        "type": "semantic_error",
                        "issue": semantic_err
                    })

        return issues