# backend/services/quality_analyzer.py

import json
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class ResponseQualityAnalyzer:
    @staticmethod
    def check_content_errors(status, body_text):
        """
        Scans status codes and response bodies for error flags and database/server traces.
        """
        if not body_text:
            return None
            
        # Status code >= 400 is already a connection/status error, handled separately.
        if status >= 400:
            return None

        # Check JSON-based structures
        try:
            data = json.loads(body_text)
            if isinstance(data, dict):
                # 1. success = false / success = "false"
                if data.get('success') is False or data.get('success') == 'false':
                    return "API response returned success=false flag."
                
                # 2. explicit error fields
                if 'error' in data or 'errors' in data:
                    err = data.get('error') or data.get('errors')
                    # Make sure it's not None or empty
                    if err:
                        return f"API response contains error field: {err}"
                        
                # 3. status = error / status = fail
                if data.get('status') in ['error', 'fail']:
                    msg = data.get('message') or data.get('detail') or 'Unknown failure message'
                    return f"API status is '{data.get('status')}': {msg}"
        except Exception:
            # Not JSON, check raw text for crash keywords
            lower_body = body_text.lower()
            
            # Check for database errors
            db_kws = ["sql error", "database error", "sqlite3.error", "postgresql error", "mysql error", "syntax error near"]
            if any(kw in lower_body for kw in db_kws):
                return "Database error trace or SQL syntax failure found in response body."
                
            # Check for backend tracebacks
            server_kws = ["traceback (most recent call", "nullpointerexception", "undefined index", "fatal error", "internal server error"]
            if any(kw in lower_body for kw in server_kws):
                return "Internal server exception or crash traceback found in response body."
                
        return None

    @staticmethod
    def get_json_keys(body_text):
        """
        Parses body text and returns a list of sorted keys if it is a JSON object,
        or keys from the first object if it is a list of JSON objects.
        """
        if not body_text:
            return []
        try:
            data = json.loads(body_text)
            if isinstance(data, dict):
                return sorted(list(data.keys()))
            elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                return sorted(list(data[0].keys()))
        except Exception:
            pass
        return []

    @classmethod
    def detect_schema_regression(cls, current_call, previous_calls):
        """
        Compares current JSON keys with keys from the matching call in previous successful run.
        """
        url = current_call.get('url')
        method = current_call.get('method')
        
        # Strip query parameters for matching
        parsed_url = urlparse(url)
        normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        
        current_body = current_call.get('body', '')
        current_keys = cls.get_json_keys(current_body)
        
        if not current_keys:
            return None

        # Find matching call in previous run
        for prev in previous_calls:
            prev_url = prev.get('url', '')
            prev_parsed = urlparse(prev_url)
            prev_normalized = f"{prev_parsed.scheme}://{prev_parsed.netloc}{prev_parsed.path}"
            
            if prev_normalized == normalized_url and prev.get('method') == method:
                prev_body = prev.get('body', '')
                prev_keys = cls.get_json_keys(prev_body)
                
                if prev_keys:
                    # Detect missing fields
                    missing_keys = [k for k in prev_keys if k not in current_keys]
                    if missing_keys:
                        return f"API schema regression: Missing fields {missing_keys} compared to last successful run."
        return None

    @staticmethod
    def is_eligible_for_semantic_check(url, base_url):
        """
        Filters out static assets, third-party trackers/libraries, and analytics
        to prevent overloading the local LLM.
        """
        if not url:
            return False
            
        # If a base URL is specified, restrict semantic checks to matching hostnames (tenant-isolation)
        if base_url:
            try:
                url_host = urlparse(url).hostname
                base_host = urlparse(base_url).hostname
                if not url_host or not base_host:
                    return False
                # Allow exact match or subdomain matches
                if not (url_host == base_host or url_host.endswith('.' + base_host) or base_host.endswith('.' + url_host)):
                    return False
            except Exception:
                return False

        # Exclude common static resource extensions
        path = urlparse(url).path.lower()
        static_exts = ['.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2', '.ttf', '.eot', '.ico', '.json']
        if any(path.endswith(ext) for ext in static_exts):
            return False

        # Exclude analytics, maps, widgets, trackers, etc.
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
        Uses local Ollama LLM to check if the response data is semantically relevant to expected result.
        """
        # Skip checking if body or expectations are missing
        if not body_text or not expected_result:
            return None
            
        # Optimization: Skip small responses (e.g. status status messages or empty sets)
        if len(body_text) < 150:
            return None

        from django.conf import settings
        import requests

        api_url = getattr(settings, 'OLLAMA_API_URL', 'http://localhost:11434/api/generate')
        model = getattr(settings, 'OLLAMA_MODEL', 'qwen:7b')

        # Limit body size to 800 chars to avoid prompt context overload and speed up local inference
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
            response = requests.post(
                api_url,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 50  # Limit output length to 50 tokens to speed up local inference
                    }
                },
                timeout=5  # Fast timeout (5s) to prevent task blocking if Ollama is slow/overloaded
            )
            if response.status_code == 200:
                result_text = response.json().get("response", "").strip()
                lines = [l.strip() for l in result_text.split('\n') if l.strip()]
                if lines:
                    verdict = lines[0].upper()
                    reason = lines[1] if len(lines) > 1 else "LLM did not provide a reason."
                    if "IRRELEVANT" in verdict:
                        return f"API output content does not match expectations: {reason}"
        except Exception as e:
            logger.warning(f"Ollama semantic check failed: {e}")
        return None

    @classmethod
    def analyze_response_quality(cls, current_calls, previous_calls, expected_result=None, base_url=None):
        """
        Runs quality scans and returns a list of detected warnings and errors.
        """
        issues = []
        
        for call in current_calls:
            url = call.get('url')
            method = call.get('method')
            status = call.get('status', 200)
            body = call.get('body', '')
            latency = call.get('latency', 0)  # in milliseconds
            
            # 1. Content Error checks
            content_err = cls.check_content_errors(status, body)
            if content_err:
                issues.append({
                    "url": url,
                    "method": method,
                    "type": "content_error",
                    "issue": content_err
                })
                
            # 2. Latency checks (> 2000ms is flagged as slow API warning)
            if latency > 2000:
                issues.append({
                    "url": url,
                    "method": method,
                    "type": "latency_warning",
                    "issue": f"High response latency detected ({latency}ms)."
                })
                
            # 3. Schema Regression checks (only compared against successful baseline)
            if previous_calls:
                regression = cls.detect_schema_regression(call, previous_calls)
                if regression:
                    issues.append({
                        "url": url,
                        "method": method,
                        "type": "schema_regression",
                        "issue": regression
                    })

        # 4. Semantic Relevance Check (only run on the single largest eligible response to prevent Ollama overload)
        if expected_result:
            eligible_calls = []
            for call in current_calls:
                c_url = call.get('url')
                c_body = call.get('body', '')
                if cls.is_eligible_for_semantic_check(c_url, base_url) and len(c_body) >= 150:
                    eligible_calls.append(call)
            
            if eligible_calls:
                # Sort by body size descending to find the main data payload (e.g. search results list)
                eligible_calls.sort(key=lambda x: len(x.get('body', '')), reverse=True)
                target_call = eligible_calls[0]
                
                t_url = target_call.get('url')
                t_method = target_call.get('method')
                t_body = target_call.get('body', '')
                
                semantic_err = cls.check_semantic_relevance(t_body, expected_result)
                if semantic_err:
                    issues.append({
                        "url": t_url,
                        "method": t_method,
                        "type": "semantic_error",
                        "issue": semantic_err
                    })
                    
        return issues
